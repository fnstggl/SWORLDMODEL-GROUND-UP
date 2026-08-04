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
  final guard slot with its explicit enabled flag (the Phase 5 agency
  guard occupies the slot by default; ``agency_guard_enabled=False``
  reserves it with the identity step -- the flag is a scalar because the
  Phase 3 plan contract validates ``gm_config`` as a scalar map), observer
  notification, disabled observation fallback, memory backend, and the run
  metadata described above.
- ``evaluator_spec``         -- supplied by the caller and passed through
  untouched.  ``world.success_criteria`` (evaluator-only prose) is
  deliberately NOT copied into the plan: nothing evaluator-facing may ever
  reach an actor or game-master prompt.
- ``compiler_provenance``    -- ``world.compiler_provenance`` verbatim
  (sidecar identity of what produced the world).

Unknown actor references (insertion actor or ``visible_to`` names) must
already have failed Phase 3 schema+semantic validation; this module
re-checks them defensively and raises -- it never repairs.

Reserved-marker refusal: world-authored text carrying upstream's
resolved-turn framing string (:data:`RESERVED_EVENT_MARKER`) is refused
loudly at plan build -- see :func:`_refuse_reserved_marker` for the full
threat model and the soundness argument.  Refusal, never sanitization:
author text is never stripped or reworded.
"""

from __future__ import annotations

import hashlib

from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            ConcordiaInitializationPlan,
                                            EvaluatorSpec, IssueCollector,
                                            SCHEMA_VERSION, canonical_time)
from sworldmodel.decision.validation import validate_semantics

from .guard import GUARD_SLOT_VALUE

PLANNER_VERSION = "concordia_local_planner_v2"

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

#: upstream's RESERVED resolved-turn framing string.  The pinned
#: Concordia event-resolution component stamps every resolved actor turn
#: with exactly this prefix before commit
#: (concordia/components/game_master/event_resolution.py:
#: ``putative_action = f'Putative event to resolve: {putative_action}'``),
#: and downstream attribution -- which actor OWNS a committed row --
#: anchors on it.  It is engine structural machinery, never author
#: vocabulary: world-authored or candidate text carrying it is refused
#: loudly before any simulation (:func:`_refuse_reserved_marker`;
#: candidate belt in ``sworldmodel.counterfactuals.manager._preflight``
#: and ``sworldmodel.compilation.decision_route``).  This constant is
#: THE single production definition; test suites cross-check their
#: anchor against it.
RESERVED_EVENT_MARKER = "Putative event to resolve:"

#: conservative comparison form of the marker: casefolded, interior
#: whitespace runs collapsed to single spaces -- so trivial obfuscations
#: ("Putative  event to resolve:", case changes, newlines/tabs between
#: the words) are refused too
_RESERVED_MARKER_COLLAPSED = " ".join(
    RESERVED_EVENT_MARKER.split()).casefold()


def contains_reserved_event_marker(text) -> bool:
    """True when ``text`` carries :data:`RESERVED_EVENT_MARKER` in any
    trivially obfuscated form: matching is case-insensitive and every
    run of whitespace collapses to one space before comparison.
    Non-strings never match (type gates live at the contract layer)."""
    if not isinstance(text, str):
        return False
    return _RESERVED_MARKER_COLLAPSED in " ".join(text.split()).casefold()


def _refuse_reserved_marker(world, neutral_premise, issues) -> None:
    """Refuse (never sanitize) authored text carrying the reserved
    upstream resolved-turn framing string.

    Threat model.  The committed event stream has an unguarded narration
    channel: starting-event descriptions are committed verbatim through
    ``game_master.observe(...)`` (builder pre-start seeding) and the
    agency guard rides only ``event_resolution_steps``, so it never sees
    them.  A world-authored description embedding
    ``<marker> <Name>: <deed>`` would be indistinguishable, to any
    marker-anchored attribution, from the named actor's own resolved
    turn -- success could be narrated into existence with zero actor
    participation (the Simulation Reality review CRITICAL).  The marker
    has NO legitimate use in authored text, so the fix is refusal at
    this chokepoint, pre-simulation, naming the marker, the offending
    field, and its index -- never silent stripping, which would alter
    author text and hide the attack.

    Coverage.  The scanned sources -- the shared context, every actor's
    private context, every starting-event description, plus the
    code-owned neutral premise (defensive: it is derived only from the
    start time) -- are the COMPLETE origin set of every plan text
    destined for the committed stream or actor delivery:
    ``shared_init_data`` and ``private_init_data`` are those contexts
    end-trimmed; ``gm_initial_events`` and ``initial_observations`` are
    fixed ``[<canonical time>] <description>`` framings of the same
    scanned texts (a canonical timestamp cannot carry the marker).
    Candidate text enters later, at the insertion boundary, and is
    refused by the candidate preflight
    (``counterfactuals.manager._preflight``) and the decision route.

    Soundness of first-occurrence anchor parsing (downstream).  With
    both chokepoints in place the marker cannot enter a committed row
    from authored narration or candidate text.  The remaining writer
    surface is the runtime actor channel, and it is closed by the
    runner's committed-stream discrimination
    (``runner.is_engine_committed_row`` /
    ``runner.committed_event_rows``): a row is committed only when the
    engine's own ``[event]`` stamp leads the row's head framing, so the
    raw ``[putative_event]`` attempt row -- written BEFORE the
    resolution chain, never guard-rewritten, and carrying no engine
    stamp ahead of the actor's text -- can never enter the committed
    stream no matter what tags or markers the actor embeds (the
    Concordia Semantics CRITICAL: substring matching admitted exactly
    that row); and rows an actor could MINT through the upstream
    three-newline observation-delimiter split are refused wholesale by
    the runner's count-invariant integrity check
    (``runner._verify_committed_stream_integrity``), which fails the
    whole branch loudly rather than expose a poisoned stream.  Every
    row in a RETURNED committed stream is therefore an engine-stamped
    RESOLVED row: the engine wrote its head framing (stamping the
    marker first) and its content passed the resolution chain, where
    actor text asserting another actor's voluntary act is
    guard-rewritten before commit.  An actor's action may embed a
    marker copy, but in a committed row only strictly AFTER the
    engine's own stamp.  First-occurrence anchor parsing therefore
    always binds to the row's true active player.
    """
    scan = [("shared_context", world.shared_context),
            ("neutral_premise", neutral_premise)]
    for index, actor in enumerate(world.actors):
        scan.append((f"actors[{index}].private_context",
                     actor.private_context))
    for index, event in enumerate(world.starting_events):
        scan.append((f"starting_events[{index}].description",
                     event.description))
    for path, text in scan:
        if contains_reserved_event_marker(text):
            issues.add(
                path, "reserved_marker",
                "authored text carries the reserved upstream "
                f"resolved-turn framing string {RESERVED_EVENT_MARKER!r} "
                "(matched case-insensitively with whitespace runs "
                "collapsed); that marker is stamped by the engine's "
                "event resolution on every resolved actor turn and "
                "anchors actor attribution, so world-authored text may "
                "never carry it -- refused before any simulation; "
                "remove the marker from this field")

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
    agency_guard_enabled: bool = True,
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
    if type(agency_guard_enabled) is not bool:
        issues.add("agency_guard_enabled", "invalid_value",
                   "agency_guard_enabled must be a boolean (the explicit "
                   "plan-level switch for the reserved final guard slot)")
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
    neutral_premise = f"The simulation window opens at {start_iso}."

    # Reserved-marker refusal (Simulation Reality CRITICAL): no authored
    # text destined for the committed stream or actor delivery may carry
    # upstream's resolved-turn framing string.  Loud, collected, and
    # pre-simulation; see _refuse_reserved_marker for the full argument.
    _refuse_reserved_marker(world, neutral_premise, issues)
    issues.raise_if_any()

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
        "guard_slot": (GUARD_SLOT_VALUE if agency_guard_enabled
                       else GUARD_SLOT_IDENTITY),
        "agency_guard_enabled": agency_guard_enabled,
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
        str(max_steps), acting_order, str(agency_guard_enabled)))
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
        "neutral_premise": neutral_premise,
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
            "event_resolution_chain", "guard_slot", "agency_guard_enabled",
            "notify_observers", "observation_fallback", "memory_backend",
            "history_length", "intervention_boundary", "start_time",
            "cutoff_time")
