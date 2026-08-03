"""Runner: drive one branch through Concordia's stock sequential engine.

``run_branch`` builds live objects from a validated plan (via
``builder.build_branch``), runs the unmodified upstream
``Sequential.run_loop`` to termination or the plan's step budget, and
captures everything the Phase 3 ``BranchResult`` builder needs:

- the committed ``[event]`` stream (game-master memory rows, in commit
  order) and the same stream shaped as ``event_trace`` entries with
  code-owned event identifiers;
- per-actor memory texts;
- the engine's raw log (one entry per step);
- step count, wall-clock, and default terminal status;
- ``guard_interventions``: one record per agency-guard rewrite (shape
  ``{step, active, affected, original_excerpt, rewritten_excerpt}``,
  excerpts capped at 120 characters).  Recorded only for the DEFAULT
  builder-constructed guard: an explicitly injected ``guard_step`` owns
  its own reporting, and the identity guard never rewrites, so the list
  is empty in both of those configurations.

Terminal-status rule (contract rule R3, CONTRACTS_DESIGN.md): an engine
stop without an evaluator verdict is NEVER a failure.  The runner reports
``'cutoff'`` when the step budget was exhausted and ``'incomplete'`` for
any earlier stop (programmatic termination or an infrastructure error).
Deciding ``'success'`` or ``'failure'`` belongs exclusively to the
caller's external evaluator reading the returned trace.

Whole-branch checkpoint/resume (Phase 8, Stage B) rides the same entry
points as surgical extensions; the state machinery itself lives in the
sibling ``checkpoint`` module:

- ``run_branch(..., checkpoint_after=k, checkpoint_identity={...})``
  stops the stock engine cleanly at the end-of-step boundary ``k`` (the
  audited safe branch point -- ``max_steps`` is the clean mechanism, the
  loop is never interrupted mid-step), captures the complete branch as a
  JSON-canonical checkpoint INCLUDING the live mid-run RNG state, and by
  default CONTINUES the same objects to the terminal result (a second
  ``run_loop`` call with ``premise=''`` and the remaining budget; the
  extra loop-boundary terminate query is a pure component passthrough,
  state-neutral, which the Stage B equivalence gate proves empirically).
  ``halt_at_checkpoint=True`` stops at the boundary instead (the
  distributed interrupt case).  The result then carries ``checkpoint``
  and ``checkpoint_captured_at`` keys.  If the run terminates or fails
  BEFORE the requested boundary, no checkpoint exists and both keys are
  ``None`` -- a checkpoint is never fabricated off-boundary.
- ``run_branch(..., resume_from=checkpoint)`` rebuilds the branch from
  the SAME plan via ``checkpoint.restore_branch`` (initial seeding
  skipped -- the restored component state already contains it), restores
  the captured RNG streams into the caller's ACTIVE seeded scope, and
  runs the remaining budget with ``premise=''`` so the opening premise is
  never re-observed.  Step accounting, terminal status, and
  guard-intervention evidence are ABSOLUTE (restored cursor + saved
  evidence + continuation), so an uninterrupted run and a
  checkpoint/restore/continue run report byte-identical traces, memories,
  and statuses under deterministic models.

Model objects are injected parameters; this module performs no LLM calls
of its own and, like the builder, degrades at import time with a clear
ImportError when the optional Concordia package is absent.
"""

from __future__ import annotations

import hashlib
import time
import traceback
from typing import Callable

from sworldmodel.decision.contracts import ConcordiaInitializationPlan

from .builder import BuiltBranch, EVENT_TAG, build_branch
from . import checkpoint as checkpoint_lib

_IMPORT_HELP = (
    "sworldmodel.backends.concordia_local.runner requires the optional "
    "'gdm-concordia' engine package (Python >= 3.12). Install it in the "
    "engine environment to use this backend; 'import sworldmodel' and the "
    "planner submodule work without it."
)

try:
    from concordia.environment.engines import sequential
except ImportError as exc:  # degrade loudly, never partially
    raise ImportError(f"{_IMPORT_HELP} (root cause: {exc!r})") from exc

#: default terminal statuses this runner may report (R3: never a failure)
STATUS_CUTOFF = "cutoff"
STATUS_INCOMPLETE = "incomplete"


def committed_event_rows(gm_memory_rows) -> list:
    """The committed event stream: every game-master memory row carrying
    the upstream ``[event]`` tag, in insertion (commit) order."""
    return [row for row in gm_memory_rows if EVENT_TAG in row]


#: guard-intervention excerpt cap (characters)
_EXCERPT_LIMIT = 120


def _validate_checkpoint_request(built: BuiltBranch, checkpoint_after,
                                 halt_at_checkpoint, checkpoint_identity,
                                 steps_already_completed) -> None:
    """Refuse malformed or ambiguous checkpoint/resume combinations
    up front; nothing is reconciled silently."""
    if type(steps_already_completed) is not int \
            or steps_already_completed < 0 \
            or steps_already_completed >= built.max_steps:
        raise ValueError(
            "steps_already_completed must be an integer in "
            f"[0, {built.max_steps}), got {steps_already_completed!r}")
    if checkpoint_after is None:
        if halt_at_checkpoint:
            raise ValueError(
                "halt_at_checkpoint requires checkpoint_after; halting "
                "without a declared boundary is ambiguous")
        if checkpoint_identity is not None:
            raise ValueError(
                "checkpoint_identity requires checkpoint_after; identity "
                "without a capture request is ambiguous")
        return
    if steps_already_completed:
        raise ValueError(
            "re-checkpointing a resumed run is not supported: "
            "checkpoint_after cannot be combined with a resume (capture "
            "checkpoints only on the original run)")
    if type(checkpoint_after) is not int \
            or not 1 <= checkpoint_after < built.max_steps:
        raise ValueError(
            "checkpoint_after must be an integer end-of-step boundary in "
            f"[1, {built.max_steps}), got {checkpoint_after!r}")
    if not isinstance(checkpoint_identity, dict):
        raise ValueError(
            "checkpoint_after requires checkpoint_identity: a mapping "
            "with the integer 'seed_material' the active seeded scope "
            "was entered with, the 'plan_content_hash' and "
            "'artifact_hash' of the branch plan, and optionally "
            "'candidate_id'/'branch_id'/'model_config' identity strings")
    for key in ("seed_material", "plan_content_hash", "artifact_hash"):
        if key not in checkpoint_identity:
            raise ValueError(
                f"checkpoint_identity is missing required key {key!r}")
    unknown = sorted(set(checkpoint_identity)
                     - {"seed_material", "plan_content_hash",
                        "artifact_hash", "candidate_id", "branch_id",
                        "model_config"})
    if unknown:
        raise ValueError(
            f"checkpoint_identity carries unknown keys: {unknown}")


def run_built_branch(built: BuiltBranch, *, capture_raw_log: bool = True,
                     step_cell: list | None = None,
                     guard_interventions: list | None = None,
                     checkpoint_after: int | None = None,
                     halt_at_checkpoint: bool = False,
                     checkpoint_identity: dict | None = None,
                     steps_already_completed: int = 0,
                     initial_raw_log: list | None = None) -> dict:
    """Run an already-built branch to termination or its step budget.

    ``step_cell`` (a single-element mutable list) and
    ``guard_interventions`` are the runner-side halves of the guard
    escalation wiring created by :func:`run_branch`: the engine's
    checkpoint callback keeps ``step_cell[0]`` at the completed-step
    count so the escalation closure can stamp each intervention with the
    in-progress step number, and the shared ``guard_interventions`` list
    is returned in the result.  Both default to ``None`` for direct
    callers, which yields an empty ``guard_interventions`` entry.

    Checkpoint/resume extensions (see the module docstring):
    ``checkpoint_after`` (absolute end-of-step boundary) with
    ``checkpoint_identity`` captures the branch mid-run and, unless
    ``halt_at_checkpoint``, continues to the terminal result;
    ``steps_already_completed > 0`` marks a RESUMED run (state already
    applied by ``checkpoint.restore_branch``): the premise is not
    re-observed, only the remaining budget runs, and all reported step
    numbers are absolute.  ``initial_raw_log`` carries the restored raw
    log so the resumed result's log covers the whole branch.  On a
    resume the caller must pre-seed ``guard_interventions`` with the
    checkpoint's saved evidence and ``step_cell`` with the cursor.
    """
    _validate_checkpoint_request(built, checkpoint_after,
                                 halt_at_checkpoint, checkpoint_identity,
                                 steps_already_completed)
    engine = sequential.Sequential()
    raw_log: list = list(initial_raw_log) if initial_raw_log else []
    steps_seen: list = []
    resumed = steps_already_completed > 0

    def _make_recorder(base: int):
        def _record_step(segment_steps: int) -> None:
            steps_seen.append(base + segment_steps)
            if step_cell is not None:
                step_cell[0] = base + segment_steps
        return _record_step

    def _run_segment(premise: str, budget: int, base: int) -> None:
        engine.run_loop(
            game_masters=[built.game_master],
            entities=[built.actors[actor_id]
                      for actor_id in built.actor_order],
            premise=premise,
            max_steps=budget,
            verbose=False,
            log=raw_log if capture_raw_log else None,
            checkpoint_callback=_make_recorder(base),
        )

    infrastructure_errors: list = []
    checkpoint_payload = None
    halted = False
    started = time.perf_counter()
    try:
        first_premise = "" if resumed else built.neutral_premise
        first_base = steps_already_completed
        if checkpoint_after is not None:
            first_budget = checkpoint_after - first_base
        else:
            first_budget = built.max_steps - first_base
        _run_segment(first_premise, first_budget, first_base)

        reached = max(steps_seen, default=steps_already_completed)
        if checkpoint_after is not None and reached >= checkpoint_after:
            # At rest at the audited end-of-step boundary: capture the
            # complete branch INCLUDING the live RNG streams.  Nothing
            # touches global randomness between the engine stop above and
            # this capture.
            checkpoint_payload = checkpoint_lib.capture_checkpoint(
                built,
                steps_completed=checkpoint_after,
                remaining_steps=built.max_steps - checkpoint_after,
                seed_material=checkpoint_identity["seed_material"],
                plan_content_hash=checkpoint_identity["plan_content_hash"],
                artifact_hash=checkpoint_identity["artifact_hash"],
                raw_log=raw_log if capture_raw_log else (),
                guard_interventions=(list(guard_interventions)
                                     if guard_interventions is not None
                                     else []),
                intervention_identity={
                    key: checkpoint_identity[key]
                    for key in ("candidate_id", "branch_id")
                    if key in checkpoint_identity},
                model_config_identity=checkpoint_identity.get(
                    "model_config") or {},
            )
            if halt_at_checkpoint:
                halted = True
            else:
                _run_segment("", built.max_steps - checkpoint_after,
                             checkpoint_after)
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        infrastructure_errors.append(
            f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
    wall_clock_seconds = time.perf_counter() - started

    steps_completed = max(steps_seen, default=steps_already_completed)
    if infrastructure_errors:
        terminal_status = STATUS_INCOMPLETE
    elif steps_completed >= built.max_steps:
        terminal_status = STATUS_CUTOFF
    else:
        # Stopped early (e.g. the Terminate component fired, or a
        # deliberate halt at the checkpoint boundary) without any
        # evaluator verdict: incomplete, never an automatic failure (R3).
        terminal_status = STATUS_INCOMPLETE

    gm_memory_rows = list(built.gm_memory_list)
    committed = committed_event_rows(gm_memory_rows)
    event_trace = [
        {"event_id": f"ev_{index:04d}", "description": row}
        for index, row in enumerate(committed)]
    actor_memories = {
        actor_id: list(built.actor_memory_lists[actor_id])
        for actor_id in built.actor_order}

    result = {
        "plan_id": built.plan_id,
        "world_id": built.world_id,
        "terminal_status": terminal_status,
        "steps_completed": steps_completed,
        "max_steps": built.max_steps,
        "run_metadata": dict(built.run_metadata),
        "committed_events": committed,
        "event_trace": event_trace,
        "gm_memory": gm_memory_rows,
        "actor_memories": actor_memories,
        "raw_log": raw_log,
        "guard_interventions": (list(guard_interventions)
                                if guard_interventions is not None else []),
        "infrastructure_errors": infrastructure_errors,
        "token_stats": {},
        "runtime_stats": {
            "wall_clock_seconds": wall_clock_seconds,
            "steps_completed": steps_completed,
        },
        "terminal_world_state": {
            "steps_completed": steps_completed,
            "committed_event_count": len(committed),
            "actor_memory_counts": {
                actor_id: len(rows)
                for actor_id, rows in actor_memories.items()},
        },
    }
    # Checkpoint/resume metadata rides the result ONLY when the feature
    # was requested, keeping the default result shape byte-stable.
    if checkpoint_after is not None:
        result["checkpoint"] = checkpoint_payload
        result["checkpoint_captured_at"] = (
            checkpoint_after if checkpoint_payload is not None else None)
        result["halted_at_checkpoint"] = halted
    if resumed:
        result["resumed_from_checkpoint"] = True
        result["resumed_at_step"] = steps_already_completed
    return result


def run_branch(
    plan: ConcordiaInitializationPlan,
    *,
    actor_models,
    gm_model,
    guard_step: Callable | None = None,
    capture_raw_log: bool = True,
    checkpoint_after: int | None = None,
    halt_at_checkpoint: bool = False,
    checkpoint_identity: dict | None = None,
    resume_from: dict | None = None,
) -> dict:
    """Build one branch from ``plan`` and run it (see module docstring).

    Returns the structured result dictionary described above.  Build-time
    defects (a plan the builder cannot honor) raise immediately; run-time
    engine exceptions are captured in ``infrastructure_errors`` with the
    partial trace preserved, so a broken branch is reported rather than
    silently replaced.

    When no ``guard_step`` is injected, the runner wires an escalation
    recorder into the builder-constructed agency guard so every rewrite
    is reported in the result's ``guard_interventions`` list.

    Checkpoint/resume (Phase 8): ``checkpoint_after`` requires a
    ``checkpoint_identity`` mapping carrying at least the integer
    ``seed_material`` of the active seeded scope (the plan hashes are
    computed here and injected); ``resume_from`` takes a checkpoint dict
    previously captured FROM THE SAME PLAN and continues it -- combining
    the two is refused as ambiguous.  Resume restores the captured RNG
    streams immediately before the engine continues; the models supplied
    for a resume are fresh injected objects and must be behaviorally
    prompt-pure (see the checkpoint module docstring).
    """
    if resume_from is not None and (
            checkpoint_after is not None or halt_at_checkpoint
            or checkpoint_identity is not None):
        raise ValueError(
            "resume_from cannot be combined with checkpoint_after / "
            "halt_at_checkpoint / checkpoint_identity: resuming and "
            "re-capturing in one call is ambiguous and unsupported")
    if checkpoint_after is not None:
        if not isinstance(checkpoint_identity, dict) \
                or "seed_material" not in checkpoint_identity:
            raise ValueError(
                "checkpoint_after requires checkpoint_identity with at "
                "least the integer 'seed_material' of the active seeded "
                "scope")
        if type(checkpoint_identity["seed_material"]) is not int:
            raise ValueError(
                "checkpoint_identity['seed_material'] must be an integer")
        checkpoint_identity = dict(checkpoint_identity)
        checkpoint_identity["plan_content_hash"] = plan.content_hash()
        checkpoint_identity["artifact_hash"] = hashlib.sha256(
            plan.compiler_provenance.canonical_json().encode(
                "utf-8")).hexdigest()

    guard_interventions: list = []
    step_cell: list = [0]

    def _record_intervention(event_in, event_out, active_player,
                             affected_actors) -> None:
        guard_interventions.append({
            "step": step_cell[0] + 1,
            "active": active_player,
            "affected": list(affected_actors),
            "original_excerpt": event_in[:_EXCERPT_LIMIT],
            "rewritten_excerpt": event_out[:_EXCERPT_LIMIT],
        })

    escalate = _record_intervention if guard_step is None else None
    if resume_from is None:
        built = build_branch(
            plan, actor_models=actor_models, gm_model=gm_model,
            guard_step=guard_step, guard_escalate=escalate)
        return run_built_branch(built, capture_raw_log=capture_raw_log,
                                step_cell=step_cell,
                                guard_interventions=guard_interventions,
                                checkpoint_after=checkpoint_after,
                                halt_at_checkpoint=halt_at_checkpoint,
                                checkpoint_identity=checkpoint_identity)

    restored = checkpoint_lib.restore_branch(
        plan, resume_from, actor_models=actor_models, gm_model=gm_model,
        guard_step=guard_step, guard_escalate=escalate)
    # Absolute continuation context: saved guard evidence and cursor are
    # pre-seeded so the continuation appends with correct step numbers.
    guard_interventions.extend(restored.guard_interventions)
    step_cell[0] = restored.steps_completed
    # Restore the captured RNG streams as the LAST action before the
    # engine continues (verifies the active scope's factory discipline).
    checkpoint_lib.restore_rng(restored.checkpoint)
    return run_built_branch(
        restored.built, capture_raw_log=capture_raw_log,
        step_cell=step_cell, guard_interventions=guard_interventions,
        steps_already_completed=restored.steps_completed,
        initial_raw_log=restored.raw_log if capture_raw_log else None)
