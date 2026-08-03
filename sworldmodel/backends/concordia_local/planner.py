"""Deterministic planner: ``CompiledDecisionWorld`` -> ``ConcordiaInitializationPlan``.

A pure function over already-validated contracts.  No LLM is called, no
text is paraphrased, and nothing is defaulted silently: every plan field
is either copied verbatim from the compiled world, carried through from an
explicitly supplied argument, or produced by a fixed code-owned rule that
is spelled out below.

Text carriage rule: every carried text (private context, shared context,
event descriptions) is transferred with its INTERIOR bytes untouched and
only leading/trailing whitespace removed.  This is not paraphrase; it is a
uniform boundary normalization, required because upstream Concordia
reserves the three-newline sequence as an observation delimiter
(``MakeObservation`` appends it; ``ObservationToMemory`` splits on it), so
an un-trimmed trailing newline would fabricate a whitespace-only
observation row in actor memory.

Code-owned mapping rules (v1):

- ``actor_configs``          -- one entry per world actor, declaration order
  preserved; ``private_init_data`` is the actor's ``private_context``
  (end-trimmed, interior verbatim).  Private context appears nowhere else
  in the plan.
- ``shared_init_data``       -- ``world.shared_context`` (end-trimmed,
  interior verbatim).
- ``initial_observations``   -- every actor gets an entry.  Rule: the shared
  context first (when non-blank), then each starting event whose
  ``visible_to`` names the actor, in the world's declared event order, each
  framed as ``[<canonical time>] <description>`` so the recorded timestamp
  travels with the text.
- ``gm_initial_events``      -- every starting event in declared order with
  the same timestamp framing (the game master keeps the full pre-start
  record; actors only ever see their visible subset).
- ``neutral_premise``        -- a fixed neutral opening derived only from the
  world's start time.  It never mentions actors, contexts, criteria, or
  candidates.
- ``run_limits.max_steps``   -- the ``max_steps`` ARGUMENT (a code-owned
  engine-step budget).  It is never derived from the world's cutoff: a
  wall-clock cutoff and an engine-step budget are different quantities.
  The cutoff rides separately as run metadata in
  ``gm_config['cutoff_time']`` (with ``gm_config['start_time']``).
- ``gm_config``              -- the explicit game-master assembly: engine
  name, acting order, the exact component roster, the fixed action spec,
  the event-resolution chain (never the upstream narrative-push step), the
  reserved final guard slot (identity in Phase 4; Phase 5 injects a real
  guard), observer notification, disabled observation fallback, memory
  backend, and the run metadata described above.
- ``evaluator_spec``         -- supplied by the caller and passed through
  untouched.  ``world.success_criteria`` (evaluator-only prose) is
  deliberately NOT copied into the plan: nothing evaluator-facing may ever
  reach an actor or game-master prompt.
- ``compiler_provenance``    -- ``world.compiler_provenance`` verbatim
  (sidecar identity of what produced the world).

Unknown actor references (insertion actor or ``visible_to`` names) must
already have failed Phase 3 schema+semantic validation; this module
re-checks them defensively and raises -- it never repairs.
"""

from __future__ import annotations

import hashlib

from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            ConcordiaInitializationPlan,
                                            EvaluatorSpec, IssueCollector,
                                            SCHEMA_VERSION, canonical_time)
from sworldmodel.decision.validation import validate_semantics

PLANNER_VERSION = "concordia_local_planner_v1"

#: code-owned default engine-step budget (an argument, never a cutoff proxy)
DEFAULT_MAX_STEPS = 8

#: supported acting orders: deterministic fixed rotation, or letting the
#: game master's model choose (the audited upstream ``NextActing`` path)
ACTING_ORDER_FIXED = "fixed"
ACTING_ORDER_GM_CHOICE = "game_master_choice"
ACTING_ORDERS = (ACTING_ORDER_FIXED, ACTING_ORDER_GM_CHOICE)

#: reserved value for the guard slot while no real guard is injected
GUARD_SLOT_IDENTITY = "identity"

#: fixed game-master identity and actor call-to-action (generic by design)
GM_NAME = "rules"
ACTOR_CALL_TO_ACTION = "What does {name} do next?"

#: component roster entries (comma-joined into ``gm_config``); order is the
#: prompt-assembly order of the assembled game master
_GM_ROSTER_CORE = (
    "memory",
    "observation_to_memory",
    "shared_setup",
    "make_observation",
    "next_acting",
    "next_action_spec",
    "event_resolution",
    "terminate",
)


def _frame_event(time_iso: str, description: str) -> str:
    """Code-owned framing: recorded timestamp + end-trimmed description."""
    return f"[{time_iso}] {description.strip()}"


def build_initialization_plan(
    world: CompiledDecisionWorld,
    evaluator_spec: EvaluatorSpec,
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
    acting_order: str = ACTING_ORDER_FIXED,
) -> ConcordiaInitializationPlan:
    """Map one validated world to its deterministic initialization plan.

    Same inputs -> byte-identical canonical plan JSON (and therefore the
    same ``plan_id`` and ``content_hash``).  Raises
    ``ContractValidationError`` with every collected defect; never repairs.
    """
    issues = IssueCollector()
    if not isinstance(world, CompiledDecisionWorld):
        issues.add("world", "wrong_type",
                   "expected a CompiledDecisionWorld instance, got "
                   f"{type(world).__name__}")
    if not isinstance(evaluator_spec, EvaluatorSpec):
        issues.add("evaluator_spec", "wrong_type",
                   "expected an EvaluatorSpec instance, got "
                   f"{type(evaluator_spec).__name__}")
    if type(max_steps) is not int or max_steps < 1:
        issues.add("max_steps", "invalid_value",
                   "max_steps must be an integer >= 1 (a code-owned "
                   "engine-step budget; it is never derived from the "
                   "world's cutoff)")
    if acting_order not in ACTING_ORDERS:
        issues.add("acting_order", "invalid_enum",
                   f"{acting_order!r} is not a supported acting order; "
                   f"allowed: {', '.join(ACTING_ORDERS)}")
    issues.raise_if_any()

    # Defensive re-checks of references Phase 3 validation already gates on.
    actor_ids = set(world.actor_ids())
    insertion_actor = world.intervention_insertion_point.actor_id
    if insertion_actor not in actor_ids:
        issues.add("intervention_insertion_point.actor_id",
                   "unknown_reference",
                   f"insertion actor {insertion_actor!r} is not a declared "
                   "actor (this world should have failed Phase 3 "
                   "validation)")
    for index, event in enumerate(world.starting_events):
        for ref_index, ref in enumerate(event.visible_to):
            if ref not in actor_ids:
                issues.add(
                    f"starting_events[{index}].visible_to[{ref_index}]",
                    "unknown_reference",
                    f"{ref!r} is not a declared actor (this world should "
                    "have failed Phase 3 validation)")
    issues.raise_if_any()

    start_iso = canonical_time(world.start_time)
    cutoff_iso = canonical_time(world.cutoff)
    shared = world.shared_context.strip()
    shared_present = bool(shared)

    framed_events = tuple(
        (event, _frame_event(canonical_time(event.time), event.description))
        for event in world.starting_events)

    initial_observations = {}
    for actor in world.actors:
        observations = []
        if shared_present:
            observations.append(shared)
        for event, framed in framed_events:
            if actor.actor_id in event.visible_to:
                observations.append(framed)
        initial_observations[actor.actor_id] = observations

    roster = [name for name in _GM_ROSTER_CORE
              if name != "shared_setup" or shared_present]

    gm_config = {
        "engine": "sequential",
        "gm_name": GM_NAME,
        "acting_order": acting_order,
        "component_roster": ",".join(roster),
        "action_spec_output_type": "free",
        "action_spec_call_to_action": ACTOR_CALL_TO_ACTION,
        "event_resolution_chain": "",
        "guard_slot": GUARD_SLOT_IDENTITY,
        "notify_observers": True,
        "observation_fallback": False,
        "memory_backend": "list",
        "history_length": 100,
        "intervention_boundary": "first_turn_observation",
        "start_time": start_iso,
        "cutoff_time": cutoff_iso,
    }

    plan_identity = "|".join((
        PLANNER_VERSION, world.content_hash(), evaluator_spec.content_hash(),
        str(max_steps), acting_order))
    plan_id = "p_" + hashlib.sha256(
        plan_identity.encode("utf-8")).hexdigest()[:16]

    plan = ConcordiaInitializationPlan.from_dict({
        "contract_type": ConcordiaInitializationPlan.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id,
        "world_id": world.world_id,
        "actor_configs": [
            {"actor_id": actor.actor_id, "name": actor.name,
             "private_init_data": actor.private_context.strip()}
            for actor in world.actors],
        "shared_init_data": shared,
        "gm_config": gm_config,
        "neutral_premise": (
            f"The simulation window opens at {start_iso}."),
        "initial_observations": initial_observations,
        "gm_initial_events": [framed for _event, framed in framed_events],
        "run_limits": {"max_steps": max_steps},
        "intervention_insertion": {"actor_id": insertion_actor},
        "evaluator_spec": evaluator_spec.to_dict(),
        "compiler_provenance": world.compiler_provenance.to_dict(),
    })
    validate_semantics(plan)
    return plan


def required_gm_config_keys() -> tuple:
    """The exact ``gm_config`` keys every v1 plan carries (introspection
    helper for builders and tests; the builder consumes each explicitly)."""
    return ("engine", "gm_name", "acting_order", "component_roster",
            "action_spec_output_type", "action_spec_call_to_action",
            "event_resolution_chain", "guard_slot", "notify_observers",
            "observation_fallback", "memory_backend", "history_length",
            "intervention_boundary", "start_time", "cutoff_time")
