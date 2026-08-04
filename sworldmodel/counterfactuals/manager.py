"""Counterfactual branch manager: every candidate from one frozen base.

``run_candidates`` freezes the base ONCE (plan plus genesis snapshot,
module ``snapshot``), derives one branch plan per candidate (module
``branch``: exactly one intervention at the code-owned insertion
boundary, proven by diff), then executes the branches STRICTLY SERIALLY
in the caller's candidate order, each inside its own seeded-determinism
scope with a per-branch seed derived code-owned from
``(seed, candidate_id)``.

Serial on purpose.  The determinism scope patches PROCESS-GLOBAL RNG
entry points -- the ``random`` module state, ``numpy.random.default_rng``
and the numpy legacy global state -- because upstream Concordia draws
from unseeded per-document generators and the global ``random`` module
(CONCORDIA_AUDIT.md section 13), and the only shared mutable global state
between simulations in one process is exactly that RNG state plus logging
(CONCORDIA_AUDIT.md section 12; one Sequential simulation is driven
single-threaded from the caller's thread).  Local THREAD parallelism is
therefore excluded: two branches in one process would interleave draws
from the patched process-global streams and destroy per-branch
reproducibility.  PROCESS-level branch parallelism arrives in Phase 7
through AgentSociety's real worker/dispatcher interfaces -- one complete
branch per worker process -- without touching this module's determinism
contract.  (The scope mirrors the Phase 2-proven test harness
``tests/engine_contracts/det.py``; production code cannot import test
modules, so the equivalent patch lives here.)

Failure containment.  Everything that runs branch-side -- the caller's
model factory, live-object construction, the engine loop -- is isolated
per branch: an exception becomes THAT branch's ``BranchResult`` with the
error recorded in ``infrastructure_errors`` and
``terminal_status='incomplete'`` (contract rule R3: an engine stop
without an evaluator verdict is never a failure), while every other
branch runs unaffected.  A failed branch is always reported in its list
position -- never silently replaced, never dropped.  By contrast,
CONTRACT violations detectable before any branch executes (an unknown or
cross-world candidate, a duplicate identifier, an application that would
change the plan outside the insertion boundary) refuse the whole call
with ``ContractValidationError``: they are invalid requests, not
execution failures.

Models are injected.  ``model_factory(candidate, branch_seed)`` must
return the pair ``(actor_models, gm_model)`` for that branch -- fresh
objects per branch; this package never constructs, configures, or calls
a language model itself, and no LLM exists anywhere in it.

Pure stdlib at import time.  The engine-facing runner (and numpy, which
the seeding scope patches) are imported lazily inside the run call, the
same guarded way the backends package documents; without the optional
engine package the call raises that backend's clear ImportError.
"""

from __future__ import annotations

import contextlib
import random
import traceback
from dataclasses import dataclass

from sworldmodel.decision.contracts import (BranchResult,
                                            CompiledDecisionWorld,
                                            ContractValidationError,
                                            InterventionCandidate,
                                            IssueCollector, SCHEMA_VERSION,
                                            ValidationIssue,
                                            default_intervention_delivery)
from sworldmodel.decision.registry import ContractRegistry
from sworldmodel.decision.validation import validate_semantics

from .branch import apply_intervention, derive_branch_id
from .delivery import compute_intervention_delivery
from .snapshot import (build_base_plan, build_base_snapshot,
                       derive_branch_seed)

#: R3 default status for a branch that could not run to its budget
STATUS_INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class CounterfactualRun:
    """Everything one serial counterfactual run produced.

    ``results`` holds one ``BranchResult`` per candidate in the CALLER'S
    candidate order (failed branches included in place).
    ``runner_records`` maps candidate_id to the raw runner result mapping
    (trace, memories, guard interventions, raw log) for branches whose
    runner returned, and to ``None`` for branches that failed before the
    runner could return -- diagnostics only, never a substitute for the
    contract objects.
    """

    base_plan: object
    base_plan_content_hash: str
    base_snapshot: object
    branch_plans: dict          # candidate_id -> ConcordiaInitializationPlan
    branch_ids: dict            # candidate_id -> branch_id
    branch_seeds: dict          # candidate_id -> int
    results: tuple              # BranchResult, caller's candidate order
    runner_records: dict        # candidate_id -> raw runner dict | None
    registry: ContractRegistry


@contextlib.contextmanager
def _seeded_branch_scope(seed: int):
    """Deterministic RNG scope for ONE branch (see module docstring).

    Seeds the stdlib ``random`` module and, when numpy is importable
    (it always is wherever the engine backend runs), patches
    ``numpy.random.default_rng`` so every no-argument call returns a
    fresh generator seeded with ``seed``, and re-seeds the numpy legacy
    global state.  All state is restored on exit.  Process-global by
    nature -- the reason branch execution is serial.
    """
    python_state = random.getstate()
    random.seed(seed)
    numpy_random = None
    original_default_rng = None
    legacy_state = None
    try:
        import numpy
        numpy_random = numpy.random
    except ImportError:
        numpy_random = None
    if numpy_random is not None:
        original_default_rng = numpy_random.default_rng
        legacy_state = numpy_random.get_state()

        def _seeded_default_rng(seed_arg=None, *args, **kwargs):
            if seed_arg is None and not args and not kwargs:
                return original_default_rng(seed)
            return original_default_rng(seed_arg, *args, **kwargs)

        numpy_random.default_rng = _seeded_default_rng
        numpy_random.seed(seed % (2 ** 32))
    try:
        yield
    finally:
        random.setstate(python_state)
        if numpy_random is not None:
            numpy_random.default_rng = original_default_rng
            numpy_random.set_state(legacy_state)


def _result_from_runner(raw: dict, branch_id: str, candidate_id: str,
                        world_id: str, *, candidate=None,
                        plan=None) -> BranchResult:
    """Shape one raw runner result into a strict ``BranchResult``.

    ``outcome_metrics`` starts empty: measuring outcomes belongs to the
    separate evaluation layer (``sworldmodel.outcomes``), which returns an
    updated result carrying cited metric values.

    Two additive facts ride along, both computed from THIS branch's own
    recorded artifacts and never from a sibling: the
    ``intervention_delivered`` fact (module ``delivery`` -- did the
    branch's candidate text reach any actor other than the insertion
    actor?) and the runner's ``unresolved_observers`` records (observer
    names the game master emitted that resolve to no roster entity).
    """
    if raw.get("world_id") != world_id:
        raise ContractValidationError([ValidationIssue(
            "world_id", "cross_branch_reference",
            f"the runner reported world {raw.get('world_id')!r} for a "
            f"branch of world {world_id!r}")])
    delivery = default_intervention_delivery()
    if candidate is not None and plan is not None:
        delivery = compute_intervention_delivery(
            candidate=candidate, plan=plan,
            actor_memories=raw.get("actor_memories"),
            committed_events=raw.get("committed_events"))
    return BranchResult.from_dict({
        "contract_type": BranchResult.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "branch_id": branch_id,
        "candidate_id": candidate_id,
        "world_id": world_id,
        "terminal_status": raw["terminal_status"],
        "terminal_world_state": raw["terminal_world_state"],
        "event_trace": raw["event_trace"],
        "outcome_metrics": {},
        "infrastructure_errors": raw["infrastructure_errors"],
        "token_stats": raw["token_stats"],
        "runtime_stats": raw["runtime_stats"],
        "artifact_paths": [],
        "intervention_delivered": delivery,
        "unresolved_observers": list(raw.get("unresolved_observers") or []),
    })


def _failure_result(branch_id: str, candidate_id: str, world_id: str,
                    exc: BaseException) -> BranchResult:
    """The reported (never hidden) shape of a branch that failed before
    the runner could return: no trace, no metrics, the error verbatim."""
    detail = (f"{type(exc).__name__}: {exc}\n"
              f"{traceback.format_exc()}")
    return BranchResult.from_dict({
        "contract_type": BranchResult.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "branch_id": branch_id,
        "candidate_id": candidate_id,
        "world_id": world_id,
        "terminal_status": STATUS_INCOMPLETE,
        "terminal_world_state": {},
        "event_trace": [],
        "outcome_metrics": {},
        "infrastructure_errors": [detail],
        "token_stats": {},
        "runtime_stats": {},
        "artifact_paths": [],
    })


def _preflight(world, candidates, model_factory, seed,
               registry) -> ContractRegistry:
    """Validate the whole request and bind identifiers BEFORE any branch
    executes; collects every defect into one refusal.

    Includes the candidate-side reserved-marker belt: a candidate whose
    summary, action, or constraint text carries upstream's resolved-turn
    framing string (``planner.RESERVED_EVENT_MARKER``) is refused here,
    before any plan is derived -- candidate text is inserted verbatim
    into the insertion actor's initial observations, and the reserved
    marker has no legitimate use in candidate text.  The world-side
    chokepoint (and the full threat model / soundness argument) lives in
    ``backends.concordia_local.planner._refuse_reserved_marker``.  The
    planner module is pure stdlib and imported lazily, matching this
    package's documented lazy-backend idiom (``snapshot.build_base_plan``).
    """
    # Lazy import: pure stdlib, importable wherever sworldmodel is.
    from sworldmodel.backends.concordia_local.planner import (
        RESERVED_EVENT_MARKER, contains_reserved_event_marker)

    issues = IssueCollector()
    if not isinstance(world, CompiledDecisionWorld):
        issues.add("world", "wrong_type",
                   "expected a CompiledDecisionWorld instance, got "
                   f"{type(world).__name__}")
    if not callable(model_factory):
        issues.add("model_factory", "wrong_type",
                   "model_factory must be callable: models are injected "
                   "parameters, never defaulted")
    if type(seed) is not int:
        issues.add("seed", "wrong_type",
                   f"seed must be an integer, got {type(seed).__name__}")
    if registry is not None and not isinstance(registry, ContractRegistry):
        issues.add("registry", "wrong_type",
                   "registry must be a ContractRegistry when supplied, "
                   f"got {type(registry).__name__}")
    if not candidates:
        issues.add("candidates", "empty_collection",
                   "at least one intervention candidate is required")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, InterventionCandidate):
            issues.add(f"candidates[{index}]", "wrong_type",
                       "expected an InterventionCandidate instance, got "
                       f"{type(candidate).__name__}")
    issues.raise_if_any()

    candidate_ids = [candidate.candidate_id for candidate in candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        issues.add("candidates", "duplicate_id",
                   "candidate identifiers must be unique within one run; "
                   "an identical candidate re-run is a new call, not a "
                   "duplicate list entry")
    for index, candidate in enumerate(candidates):
        texts = [("summary", candidate.summary),
                 ("action", candidate.action)]
        texts.extend(
            (f"constraints[{constraint_index}]", constraint)
            for constraint_index, constraint
            in enumerate(candidate.constraints))
        for field, text in texts:
            if contains_reserved_event_marker(text):
                issues.add(
                    f"candidates[{index}].{field}", "reserved_marker",
                    "candidate text carries the reserved upstream "
                    "resolved-turn framing string "
                    f"{RESERVED_EVENT_MARKER!r} (matched "
                    "case-insensitively with whitespace runs collapsed); "
                    "the marker is engine machinery that anchors actor "
                    "attribution and has no legitimate use in candidate "
                    "text -- refused before any branch executes")
    issues.raise_if_any()

    registry = registry if registry is not None else ContractRegistry()
    if not registry.has_world(world.world_id):
        registry.register_world(world)
    for index, candidate in enumerate(candidates):
        candidate_id = candidate.candidate_id
        if registry.has_candidate(candidate_id):
            bound_world = registry.candidate_world(candidate_id)
            if bound_world != world.world_id:
                issues.add(
                    f"candidates[{index}]", "cross_branch_reference",
                    f"candidate {candidate_id!r} is registered to world "
                    f"{bound_world!r}, not {world.world_id!r}; a branch "
                    "may not join identifiers across worlds")
            continue
        try:
            # Validate BEFORE registering so a refused call leaves no
            # invalid candidate behind in the registry.
            validate_semantics(candidate, registry,
                               world_id=world.world_id)
            registry.register_candidate(candidate, world.world_id)
        except ContractValidationError as exc:
            issues.extend(exc.issues)
    issues.raise_if_any()
    return registry


def run_candidates_detailed(
    world: CompiledDecisionWorld,
    candidates,
    *,
    model_factory,
    seed: int,
    max_steps: int,
    evaluator_spec,
    acting_order: str | None = None,
    agency_guard_enabled: bool = True,
    model_config: dict | None = None,
    registry: ContractRegistry | None = None,
) -> CounterfactualRun:
    """Run every candidate branch serially from ONE frozen base; return
    the full run record (see :class:`CounterfactualRun`).

    Order of operations: pre-flight validation of the whole request ->
    base plan built once -> base snapshot frozen -> every branch plan
    derived and every branch id registered -> serial, seeded, isolated
    execution.  Identical inputs produce identical results regardless of
    candidate list order, because each branch's plan, id, and seed depend
    only on (base, candidate) -- never on siblings.
    """
    candidates = tuple(candidates)
    registry = _preflight(world, candidates, model_factory, seed, registry)

    base_plan = build_base_plan(
        world, evaluator_spec, max_steps=max_steps,
        acting_order=acting_order,
        agency_guard_enabled=agency_guard_enabled)
    base_hash = base_plan.content_hash()
    base_snapshot = build_base_snapshot(
        base_plan, seed=seed, model_config=model_config, registry=registry)

    branch_plans: dict = {}
    branch_ids: dict = {}
    branch_seeds: dict = {}
    for candidate in candidates:
        candidate_id = candidate.candidate_id
        branch_id = derive_branch_id(world.world_id, candidate_id)
        if registry.has_branch(branch_id):
            bound = registry.branch_binding(branch_id)
            if bound != (world.world_id, candidate_id):
                raise ContractValidationError([ValidationIssue(
                    "branch_id", "cross_branch_reference",
                    f"branch {branch_id!r} is already registered for "
                    f"world {bound[0]!r} / candidate {bound[1]!r}")])
        else:
            registry.register_branch(branch_id, world.world_id,
                                     candidate_id)
        branch_ids[candidate_id] = branch_id
        branch_plans[candidate_id] = apply_intervention(base_plan, candidate)
        branch_seeds[candidate_id] = derive_branch_seed(seed, candidate_id)

    # Engine import is deliberately here: a missing engine package fails
    # the call with the backend's clear ImportError before any branch
    # "runs" vacuously.
    from sworldmodel.backends.concordia_local import runner as runner_module

    results: list = []
    runner_records: dict = {}
    for candidate in candidates:
        candidate_id = candidate.candidate_id
        branch_id = branch_ids[candidate_id]
        branch_seed = branch_seeds[candidate_id]
        raw = None
        try:
            provided = model_factory(candidate, branch_seed)
            try:
                actor_models, gm_model = provided
            except (TypeError, ValueError):
                raise ContractValidationError([ValidationIssue(
                    "model_factory", "wrong_type",
                    "model_factory must return the pair (actor_models, "
                    f"gm_model), got {type(provided).__name__}")])
            with _seeded_branch_scope(branch_seed):
                raw = runner_module.run_branch(
                    branch_plans[candidate_id],
                    actor_models=actor_models,
                    gm_model=gm_model)
            result = _result_from_runner(
                raw, branch_id, candidate_id, world.world_id,
                candidate=candidate, plan=branch_plans[candidate_id])
        except Exception as exc:  # noqa: BLE001 - reported, never hidden
            raw = None
            result = _failure_result(branch_id, candidate_id,
                                     world.world_id, exc)
        validate_semantics(result, registry)
        results.append(result)
        runner_records[candidate_id] = raw

    return CounterfactualRun(
        base_plan=base_plan,
        base_plan_content_hash=base_hash,
        base_snapshot=base_snapshot,
        branch_plans=branch_plans,
        branch_ids=branch_ids,
        branch_seeds=branch_seeds,
        results=tuple(results),
        runner_records=runner_records,
        registry=registry)


def run_candidates(
    world: CompiledDecisionWorld,
    candidates,
    *,
    model_factory,
    seed: int,
    max_steps: int,
    evaluator_spec,
    acting_order: str | None = None,
    agency_guard_enabled: bool = True,
    model_config: dict | None = None,
    registry: ContractRegistry | None = None,
) -> list:
    """Serial deterministic counterfactual execution: one ``BranchResult``
    per candidate, in the caller's candidate order (failures reported in
    place).  Thin wrapper over :func:`run_candidates_detailed`."""
    run = run_candidates_detailed(
        world, candidates, model_factory=model_factory, seed=seed,
        max_steps=max_steps, evaluator_spec=evaluator_spec,
        acting_order=acting_order,
        agency_guard_enabled=agency_guard_enabled,
        model_config=model_config, registry=registry)
    return list(run.results)
