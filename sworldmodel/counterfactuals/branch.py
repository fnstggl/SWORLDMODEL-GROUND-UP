"""Branch construction: exactly one intervention at the insertion boundary.

Insertion mechanism (the one the Phase 4 planner defined): every base plan
carries ``gm_config['intervention_boundary'] = 'first_turn_observation'``
and ``intervention_insertion.actor_id`` naming the single acting entity.
``apply_intervention`` appends the candidate's action text -- followed by
each declared candidate constraint, in declared order -- to that actor's
``initial_observations`` entry, each framed exactly like the planner
frames pre-start events: ``[<canonical timing>] <text>`` (interior bytes
verbatim; only boundary whitespace trimmed, the planner's uniform
end-trim rule).  The upstream observation queue delivers the whole initial
list to the actor before its first turn, so the intervention becomes the
acting entity's initial observation / action context at t0.  Nothing is
added to any other actor's observations, to the game master's pre-start
record, or to any shared field.

Isolation invariant: a branch plan differs from its base ONLY under
``initial_observations.<insertion actor>``.  :func:`diff_plans` computes
the exact changed leaf paths between two plans' canonical dict forms, and
``apply_intervention`` re-derives that diff and REFUSES (never repairs)
any application that would touch anything else -- including the plan
identity fields: the branch keeps the BASE ``plan_id`` because the plan
identity is the shared genesis; branch identity is the code-owned
``branch_id`` (:func:`derive_branch_id`, sha256 over
``<world_id>|<candidate_id>``), registered through the Phase 3 registry by
the manager.

Pure stdlib; no engine import anywhere in this module.
"""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime

from sworldmodel.decision.contracts import (ConcordiaInitializationPlan,
                                            ContractValidationError,
                                            InterventionCandidate,
                                            IssueCollector, ValidationIssue,
                                            _SLUG_RE, canonical_time)
from sworldmodel.decision.validation import validate_semantics


def _fail(path: str, code: str, message: str) -> None:
    raise ContractValidationError([ValidationIssue(path, code, message)])


def derive_branch_id(world_id: str, candidate_id: str) -> str:
    """Code-owned branch identifier for the (world, candidate) pairing."""
    issues = IssueCollector()
    for path, value in (("world_id", world_id),
                        ("candidate_id", candidate_id)):
        if not isinstance(value, str) or not _SLUG_RE.match(value):
            issues.add(path, "invalid_id",
                       f"identifier {value!r} must match {_SLUG_RE.pattern}")
    issues.raise_if_any()
    digest = hashlib.sha256(
        f"{world_id}|{candidate_id}".encode("utf-8")).hexdigest()
    return "br_" + digest[:16]


def insertion_path_prefix(plan: ConcordiaInitializationPlan) -> str:
    """The single dict path a branch may differ from its base under."""
    if not isinstance(plan, ConcordiaInitializationPlan):
        _fail("plan", "wrong_type",
              "expected a ConcordiaInitializationPlan instance, got "
              f"{type(plan).__name__}")
    return f"initial_observations.{plan.intervention_insertion.actor_id}"


def frame_insertion_text(time_iso: str, text: str) -> str:
    """The planner's event framing rule, applied to intervention text:
    recorded timestamp plus the end-trimmed text (interior verbatim)."""
    return f"[{time_iso}] {text.strip()}"


def insertion_observation_texts(candidate: InterventionCandidate) -> tuple:
    """The exact observation lines one candidate contributes, in order:
    the action first, then each declared constraint, all framed with the
    candidate's canonical timing."""
    if not isinstance(candidate, InterventionCandidate):
        _fail("candidate", "wrong_type",
              "expected an InterventionCandidate instance, got "
              f"{type(candidate).__name__}")
    time_iso = canonical_time(candidate.timing)
    lines = [frame_insertion_text(time_iso, candidate.action)]
    for constraint in candidate.constraints:
        lines.append(frame_insertion_text(time_iso, constraint))
    return tuple(lines)


def _diff_trees(base, branch, path: str, changed: list) -> None:
    if type(base) is not type(branch):
        changed.append(path)
        return
    if isinstance(base, dict):
        for key in sorted(set(base) | set(branch)):
            key_path = f"{path}.{key}" if path else key
            if key not in base or key not in branch:
                changed.append(key_path)
            else:
                _diff_trees(base[key], branch[key], key_path, changed)
        return
    if isinstance(base, list):
        for index in range(max(len(base), len(branch))):
            item_path = f"{path}[{index}]"
            if index >= len(base) or index >= len(branch):
                changed.append(item_path)
            else:
                _diff_trees(base[index], branch[index], item_path, changed)
        return
    if base != branch:
        changed.append(path)


def diff_plans(base: ConcordiaInitializationPlan,
               branch: ConcordiaInitializationPlan) -> tuple:
    """The exact leaf paths where two plans' canonical dicts differ.

    Path syntax: dot-joined mapping keys with ``[index]`` list positions
    (e.g. ``initial_observations.<actor>[2]``).  Added, removed, and
    replaced leaves all count as changes; comparison is type-strict (a
    boolean never equals an integer).  Returned sorted for determinism.
    """
    issues = IssueCollector()
    for path, value in (("base", base), ("branch", branch)):
        if not isinstance(value, ConcordiaInitializationPlan):
            issues.add(path, "wrong_type",
                       "expected a ConcordiaInitializationPlan instance, "
                       f"got {type(value).__name__}")
    issues.raise_if_any()
    changed: list = []
    _diff_trees(base.to_dict(), branch.to_dict(), "", changed)
    return tuple(sorted(changed))


def apply_intervention(
    base_plan: ConcordiaInitializationPlan,
    candidate: InterventionCandidate,
) -> ConcordiaInitializationPlan:
    """Derive one branch plan: the base plus EXACTLY ONE intervention.

    The candidate's decision owner must be the plan's declared insertion
    actor and its timing must fall inside the plan's recorded
    [start, cutoff] window (defensive re-checks of what Phase 3 semantic
    validation already gates on).  After construction the derived plan is
    strictly re-validated and diffed against the base: any changed path
    outside ``initial_observations.<insertion actor>`` refuses the
    application outright.  Never repairs, never widens.
    """
    issues = IssueCollector()
    if not isinstance(base_plan, ConcordiaInitializationPlan):
        issues.add("base_plan", "wrong_type",
                   "expected a ConcordiaInitializationPlan instance, got "
                   f"{type(base_plan).__name__}")
    if not isinstance(candidate, InterventionCandidate):
        issues.add("candidate", "wrong_type",
                   "expected an InterventionCandidate instance, got "
                   f"{type(candidate).__name__}")
    issues.raise_if_any()

    insertion_actor = base_plan.intervention_insertion.actor_id
    if candidate.decision_owner != insertion_actor:
        issues.add(
            "candidate.decision_owner", "owner_mismatch",
            f"candidate {candidate.candidate_id!r} acts through "
            f"{candidate.decision_owner!r} but the plan's single insertion "
            f"boundary belongs to {insertion_actor!r}; a candidate may not "
            "act through a different actor")
    start_raw = base_plan.gm_config.get("start_time")
    cutoff_raw = base_plan.gm_config.get("cutoff_time")
    if isinstance(start_raw, str) and isinstance(cutoff_raw, str):
        try:
            start = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            cutoff = datetime.fromisoformat(
                cutoff_raw.replace("Z", "+00:00"))
        except ValueError:
            start = cutoff = None
        if start is not None and cutoff is not None \
                and not (start <= candidate.timing <= cutoff):
            issues.add("candidate.timing", "timing_out_of_range",
                       "candidate timing must fall inside the plan's "
                       "[start_time, cutoff_time] window")
    issues.raise_if_any()

    data = copy.deepcopy(base_plan.to_dict())
    observations = data["initial_observations"].get(insertion_actor)
    if observations is None:
        _fail(f"initial_observations.{insertion_actor}", "missing_field",
              "the base plan carries no observation entry for its "
              "insertion actor; every planner-built plan has one")
    data["initial_observations"][insertion_actor] = (
        list(observations) + list(insertion_observation_texts(candidate)))

    branch_plan = ConcordiaInitializationPlan.from_dict(data)
    validate_semantics(branch_plan)

    prefix = insertion_path_prefix(base_plan)
    changed = diff_plans(base_plan, branch_plan)
    stray = tuple(path for path in changed
                  if path != prefix and not path.startswith(prefix + "["))
    if stray:
        raise ContractValidationError([ValidationIssue(
            path, "invalid_value",
            "applying the candidate would change the plan outside the "
            f"insertion boundary {prefix!r}; refusing the branch")
            for path in stray])
    if not changed:
        _fail(prefix, "invalid_value",
              "applying the candidate changed nothing; a branch must "
              "differ from its base at the insertion boundary")
    return branch_plan
