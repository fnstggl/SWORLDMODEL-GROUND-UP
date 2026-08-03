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
- step count, wall-clock, and default terminal status.

Terminal-status rule (contract rule R3, CONTRACTS_DESIGN.md): an engine
stop without an evaluator verdict is NEVER a failure.  The runner reports
``'cutoff'`` when the step budget was exhausted and ``'incomplete'`` for
any earlier stop (programmatic termination or an infrastructure error).
Deciding ``'success'`` or ``'failure'`` belongs exclusively to the
caller's external evaluator reading the returned trace.

Model objects are injected parameters; this module performs no LLM calls
of its own and, like the builder, degrades at import time with a clear
ImportError when the optional Concordia package is absent.
"""

from __future__ import annotations

import time
import traceback
from typing import Callable

from sworldmodel.decision.contracts import ConcordiaInitializationPlan

from .builder import BuiltBranch, EVENT_TAG, build_branch

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


def run_built_branch(built: BuiltBranch, *, capture_raw_log: bool = True
                     ) -> dict:
    """Run an already-built branch to termination or its step budget."""
    engine = sequential.Sequential()
    raw_log: list = []
    steps_seen: list = []

    def _record_step(steps_completed: int) -> None:
        steps_seen.append(steps_completed)

    infrastructure_errors: list = []
    started = time.perf_counter()
    try:
        engine.run_loop(
            game_masters=[built.game_master],
            entities=[built.actors[actor_id]
                      for actor_id in built.actor_order],
            premise=built.neutral_premise,
            max_steps=built.max_steps,
            verbose=False,
            log=raw_log if capture_raw_log else None,
            checkpoint_callback=_record_step,
        )
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        infrastructure_errors.append(
            f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
    wall_clock_seconds = time.perf_counter() - started

    steps_completed = max(steps_seen, default=0)
    if infrastructure_errors:
        terminal_status = STATUS_INCOMPLETE
    elif steps_completed >= built.max_steps:
        terminal_status = STATUS_CUTOFF
    else:
        # Stopped early (e.g. the Terminate component fired) without any
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

    return {
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


def run_branch(
    plan: ConcordiaInitializationPlan,
    *,
    actor_models,
    gm_model,
    guard_step: Callable | None = None,
    capture_raw_log: bool = True,
) -> dict:
    """Build one branch from ``plan`` and run it (see module docstring).

    Returns the structured result dictionary described above.  Build-time
    defects (a plan the builder cannot honor) raise immediately; run-time
    engine exceptions are captured in ``infrastructure_errors`` with the
    partial trace preserved, so a broken branch is reported rather than
    silently replaced.
    """
    built = build_branch(plan, actor_models=actor_models, gm_model=gm_model,
                         guard_step=guard_step)
    return run_built_branch(built, capture_raw_log=capture_raw_log)
