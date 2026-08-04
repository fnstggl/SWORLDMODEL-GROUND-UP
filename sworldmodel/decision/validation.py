"""Two-stage validation: strict schema, then separate semantics.

``validate_schema`` delegates entirely to each contract's strict
``from_dict`` (unknown fields, missing fields, wrong types, enums, versions,
wrong contract type), optionally enforcing an expected contract class.

``validate_semantics`` checks meaning against the code-owned registry:
references resolve only to registered identifiers, decision ownership
matches the world's single insertion boundary, timing falls inside the
[start, cutoff] window, snapshot manifests account for every serialized
component, metrics cite recorded events or terminal state, and a
recommendation is consistent with the branch results it summarizes.

Both stages collect EVERY defect into one ``ContractValidationError``
(path, code, message per issue).  Nothing is repaired silently.
"""

from __future__ import annotations

from typing import Mapping

from .contracts import (BranchResult, CompiledDecisionWorld,
                        ConcordiaInitializationPlan, ContractValidationError,
                        CONTRACT_CLASSES, DecisionProblem, EvaluatorSpec,
                        InterventionCandidate, IssueCollector,
                        RecommendationResult, SimulationSnapshot,
                        SIDECAR_COMPONENTS, ValidationIssue,
                        _MEASURABLE_TOKEN_RE)
from .registry import ContractRegistry


# ---------------------------------------------------------------------------
# Schema stage
# ---------------------------------------------------------------------------

def validate_schema(data, expected=None):
    """Parse ``data`` strictly into a contract instance.

    ``expected`` may be a contract class or a contract_type string; when
    given, the object is parsed against that class so a different contract
    type supplied by mistake fails with an explicit wrong_contract_type
    issue.  Without ``expected`` the parser dispatches on the embedded
    contract_type field.
    """
    if expected is not None:
        cls = _resolve_class(expected)
        return cls.from_dict(data)
    if not isinstance(data, Mapping):
        raise ContractValidationError([ValidationIssue(
            "", "wrong_type",
            f"expected a mapping, got {type(data).__name__}")])
    raw_type = data.get("contract_type")
    if raw_type not in CONTRACT_CLASSES:
        raise ContractValidationError([ValidationIssue(
            "contract_type", "wrong_contract_type",
            f"{raw_type!r} is not a known contract type; known: "
            f"{', '.join(sorted(CONTRACT_CLASSES))}")])
    return CONTRACT_CLASSES[raw_type].from_dict(data)


def _resolve_class(expected):
    if isinstance(expected, str):
        if expected not in CONTRACT_CLASSES:
            raise ContractValidationError([ValidationIssue(
                "contract_type", "wrong_contract_type",
                f"{expected!r} is not a known contract type")])
        return CONTRACT_CLASSES[expected]
    if isinstance(expected, type) and hasattr(expected, "CONTRACT_TYPE"):
        return expected
    raise ContractValidationError([ValidationIssue(
        "", "wrong_type",
        "expected a contract class or contract_type string")])


# ---------------------------------------------------------------------------
# Semantic stage
# ---------------------------------------------------------------------------

def validate_semantics(obj, registry=None, *, world_id=None,
                       branch_results=None, evaluator_spec=None,
                       constraint_hook=None) -> None:
    """Semantic validation for any contract instance; raises with ALL
    collected issues.  ``registry`` is required wherever identifiers must
    resolve (candidates, snapshots, branch results, recommendations)."""
    issues = IssueCollector()
    if isinstance(obj, CompiledDecisionWorld):
        _world_semantics(obj, issues)
    elif isinstance(obj, InterventionCandidate):
        _candidate_semantics(obj, registry, world_id, constraint_hook,
                             issues)
    elif isinstance(obj, SimulationSnapshot):
        _snapshot_semantics(obj, registry, issues)
    elif isinstance(obj, BranchResult):
        _branch_result_semantics(obj, registry, issues)
    elif isinstance(obj, RecommendationResult):
        _recommendation_semantics(obj, registry, branch_results,
                                  evaluator_spec, issues)
    elif isinstance(obj, DecisionProblem):
        _problem_semantics(obj, registry, world_id, issues)
    elif isinstance(obj, ConcordiaInitializationPlan):
        _plan_semantics(obj, issues)
    else:
        issues.add("", "wrong_type",
                   f"no semantic rules exist for {type(obj).__name__}")
    issues.raise_if_any()


def _require_registry(registry, issues) -> bool:
    if isinstance(registry, ContractRegistry):
        return True
    issues.add("", "unregistered_id",
               "semantic reference resolution requires the code-owned "
               "registry, but none was supplied")
    return False


def _measurable_criteria(text, path, issues) -> None:
    if not text.strip():
        issues.add(path, "invalid_value",
                   "success criteria must not be empty")
        return
    if not _MEASURABLE_TOKEN_RE.search(text.lower()):
        issues.add(path, "invalid_value",
                   "success criteria must reference at least one "
                   "measurable identifier-like term")


def _world_semantics(world: CompiledDecisionWorld, issues) -> None:
    actor_ids = set(world.actor_ids())
    insertion = world.intervention_insertion_point.actor_id
    if insertion not in actor_ids:
        issues.add("intervention_insertion_point.actor_id",
                   "unknown_reference",
                   f"insertion actor {insertion!r} is not a declared actor")
    horizon = world.horizon()
    for index, event in enumerate(world.starting_events):
        for ref_index, ref in enumerate(event.visible_to):
            if ref not in actor_ids:
                issues.add(
                    f"starting_events[{index}].visible_to[{ref_index}]",
                    "unknown_reference",
                    f"{ref!r} does not resolve to a declared actor")
        if not horizon.contains(event.time):
            issues.add(f"starting_events[{index}].time",
                       "timing_out_of_range",
                       "event time must fall inside [start_time, cutoff]")
    _measurable_criteria(world.success_criteria, "success_criteria", issues)


def _candidate_semantics(candidate: InterventionCandidate, registry,
                         world_id, constraint_hook, issues) -> None:
    if not _require_registry(registry, issues):
        return
    if world_id is None and registry.has_candidate(candidate.candidate_id):
        world_id = registry.candidate_world(candidate.candidate_id)
    if world_id is None:
        issues.add("candidate_id", "unregistered_id",
                   "cannot resolve the candidate's owning world: pass "
                   "world_id or register the candidate first")
        return
    if not registry.has_world(world_id):
        issues.add("world_id", "unregistered_id",
                   f"world {world_id!r} is not registered")
        return
    owner = candidate.decision_owner
    if owner not in registry.world_actor_ids(world_id):
        issues.add("decision_owner", "unknown_reference",
                   f"decision owner {owner!r} is not an actor of world "
                   f"{world_id!r}")
    else:
        insertion = registry.world_insertion_actor(world_id)
        if owner != insertion:
            issues.add(
                "decision_owner", "owner_mismatch",
                f"decision owner {owner!r} does not match the world's "
                f"declared insertion actor {insertion!r}; a candidate may "
                "not act through a different actor")
    horizon = registry.world_horizon(world_id)
    if not horizon.contains(candidate.timing):
        issues.add("timing", "timing_out_of_range",
                   "candidate timing must fall inside [start, cutoff] of "
                   f"world {world_id!r}")
    if constraint_hook is not None:
        for message in constraint_hook(candidate):
            issues.add("constraints", "constraint_violation", str(message))


def _snapshot_semantics(snapshot: SimulationSnapshot, registry,
                        issues) -> None:
    if _require_registry(registry, issues) \
            and not registry.has_world(snapshot.world_id):
        issues.add("world_id", "unregistered_id",
                   f"world {snapshot.world_id!r} is not registered")
    expected = set(snapshot.concordia_checkpoint.keys())
    expected.update(SIDECAR_COMPONENTS)
    declared = set(snapshot.snapshot_manifest)
    for missing in sorted(expected - declared):
        issues.add("snapshot_manifest", "manifest_incomplete",
                   f"serialized component {missing!r} is missing from the "
                   "manifest")
    for extra in sorted(declared - expected):
        issues.add("snapshot_manifest", "unknown_reference",
                   f"manifest names {extra!r} but no such component was "
                   "serialized")


def _branch_result_semantics(result: BranchResult, registry, issues) -> None:
    if not _require_registry(registry, issues):
        return
    if not registry.has_world(result.world_id):
        issues.add("world_id", "unregistered_id",
                   f"world {result.world_id!r} is not registered")
    if not registry.has_candidate(result.candidate_id):
        issues.add("candidate_id", "unregistered_id",
                   f"candidate {result.candidate_id!r} is not registered")
    elif registry.has_world(result.world_id) \
            and registry.candidate_world(result.candidate_id) \
            != result.world_id:
        issues.add("candidate_id", "cross_branch_reference",
                   f"candidate {result.candidate_id!r} is registered to a "
                   "different world")
    if not registry.has_branch(result.branch_id):
        issues.add("branch_id", "unregistered_id",
                   f"branch {result.branch_id!r} is not registered")
    else:
        bound_world, bound_candidate = registry.branch_binding(
            result.branch_id)
        if (bound_world, bound_candidate) \
                != (result.world_id, result.candidate_id):
            issues.add(
                "branch_id", "cross_branch_reference",
                f"branch {result.branch_id!r} is registered for world "
                f"{bound_world!r} / candidate {bound_candidate!r}, but this "
                f"result cites world {result.world_id!r} / candidate "
                f"{result.candidate_id!r}")
    event_ids = {event.event_id for event in result.event_trace}
    state_keys = set(result.terminal_world_state.keys())
    for name, metric in result.outcome_metrics.items():
        for ref_index, ref in enumerate(metric.computed_from):
            kind, _, target = ref.partition(":")
            if kind == "event" and target not in event_ids:
                issues.add(
                    f"outcome_metrics.{name}.computed_from[{ref_index}]",
                    "unknown_reference",
                    f"metric cites event {target!r} which is not in the "
                    "recorded trace")
            elif kind == "state" and target not in state_keys:
                issues.add(
                    f"outcome_metrics.{name}.computed_from[{ref_index}]",
                    "unknown_reference",
                    f"metric cites state key {target!r} which is not in "
                    "the terminal world state")


def _scalar_values_consistent(left, right) -> bool:
    if (type(left) is bool) != (type(right) is bool):
        return False
    return left == right


def _rank_key(value) -> float:
    if type(value) is bool:
        return 1.0 if value else 0.0
    return float(value)


def _recommendation_semantics(result: RecommendationResult, registry,
                              branch_results, evaluator_spec,
                              issues) -> None:
    ranked_ids = [entry.candidate_id for entry in result.ranking]
    if ranked_ids and result.best_candidate_id != ranked_ids[0]:
        issues.add(
            "best_candidate_id", "inconsistent_ranking",
            f"best_candidate_id {result.best_candidate_id!r} must equal the "
            f"first ranking entry {ranked_ids[0]!r}; the winner is the "
            "computed ordering's head, never an override")
    if isinstance(registry, ContractRegistry):
        for index, candidate_id in enumerate(ranked_ids):
            if not registry.has_candidate(candidate_id):
                issues.add(f"ranking[{index}].candidate_id",
                           "unregistered_id",
                           f"candidate {candidate_id!r} is not registered")
    for candidate_id in result.downside_outcomes:
        if candidate_id not in ranked_ids:
            issues.add(f"downside_outcomes.{candidate_id}",
                       "unknown_reference",
                       f"{candidate_id!r} is not a ranked candidate")
    if branch_results is not None:
        by_candidate: dict = {}
        for branch_result in branch_results:
            if branch_result.candidate_id in by_candidate:
                issues.add(
                    "ranking", "cross_branch_reference",
                    f"two branch results supplied for candidate "
                    f"{branch_result.candidate_id!r}")
            by_candidate[branch_result.candidate_id] = branch_result
        if set(by_candidate) != set(ranked_ids):
            issues.add(
                "ranking", "inconsistent_ranking",
                f"ranked candidates {sorted(ranked_ids)} do not match the "
                f"supplied branch results {sorted(by_candidate)}")
        for index, entry in enumerate(result.ranking):
            branch_result = by_candidate.get(entry.candidate_id)
            if branch_result is None:
                continue
            for metric_name, value in entry.metric_values.items():
                recorded = branch_result.outcome_metrics.get(metric_name)
                if recorded is None:
                    issues.add(
                        f"ranking[{index}].metric_values.{metric_name}",
                        "unknown_reference",
                        f"metric {metric_name!r} is not present in the "
                        "branch result for this candidate")
                elif not _scalar_values_consistent(value, recorded.value):
                    issues.add(
                        f"ranking[{index}].metric_values.{metric_name}",
                        "inconsistent_ranking",
                        f"ranking cites {value!r} but the branch result "
                        f"measured {recorded.value!r}")
    if evaluator_spec is not None:
        if not isinstance(evaluator_spec, EvaluatorSpec):
            issues.add("", "wrong_type",
                       "evaluator_spec must be an EvaluatorSpec")
        else:
            primary = evaluator_spec.primary_metric
            keys = []
            for index, entry in enumerate(result.ranking):
                if primary not in entry.metric_values:
                    issues.add(
                        f"ranking[{index}].metric_values", "missing_field",
                        f"declared primary metric {primary!r} is absent "
                        "from this ranking entry")
                else:
                    keys.append(_rank_key(entry.metric_values[primary]))
            if len(keys) == len(result.ranking) \
                    and any(keys[i] < keys[i + 1]
                            for i in range(len(keys) - 1)):
                issues.add(
                    "ranking", "inconsistent_ranking",
                    f"ranking is not ordered by the declared primary "
                    f"metric {primary!r} (non-increasing order required)")
            # Full declared-order re-validation (review finding D4-low): the
            # complete key is (primary, *secondaries in declared order,
            # candidate_id ascending); an ordering that honors the primary but
            # inverts a declared secondary must fail here, not only at
            # construction time.
            declared = (primary,) + tuple(evaluator_spec.secondary_metrics)
            full_keys = []
            for entry in result.ranking:
                if all(name in entry.metric_values for name in declared):
                    full_keys.append(
                        (tuple(_rank_key(entry.metric_values[name])
                               for name in declared),
                         entry.candidate_id))
            if len(full_keys) == len(result.ranking):
                for i in range(len(full_keys) - 1):
                    higher, lower = full_keys[i], full_keys[i + 1]
                    if higher[0] < lower[0] or (
                            higher[0] == lower[0]
                            and higher[1] > lower[1]):
                        issues.add(
                            "ranking", "inconsistent_ranking",
                            "ranking violates the declared metric order "
                            f"between positions {i} and {i + 1} (declared "
                            f"sequence {list(declared)}, candidate_id "
                            "ascending as the final tie-break)")
                        break


def _problem_semantics(problem: DecisionProblem, registry, world_id,
                       issues) -> None:
    _measurable_criteria(problem.success_criteria, "success_criteria",
                         issues)
    if isinstance(registry, ContractRegistry) and world_id is not None:
        if not registry.has_world(world_id):
            issues.add("", "unregistered_id",
                       f"world {world_id!r} is not registered")
        elif registry.resolve_actor_reference(
                world_id, problem.decision_owner) is None:
            issues.add(
                "decision_owner", "unknown_reference",
                f"decision owner {problem.decision_owner!r} does not "
                f"resolve to an actor of world {world_id!r}")


def _plan_semantics(plan: ConcordiaInitializationPlan, issues) -> None:
    actor_ids = {config.actor_id for config in plan.actor_configs}
    for actor_id in plan.initial_observations:
        if actor_id not in actor_ids:
            issues.add(f"initial_observations.{actor_id}",
                       "unknown_reference",
                       f"{actor_id!r} is not a configured actor")
    insertion = plan.intervention_insertion.actor_id
    if insertion not in actor_ids:
        issues.add("intervention_insertion.actor_id", "unknown_reference",
                   f"insertion actor {insertion!r} is not a configured "
                   "actor")
