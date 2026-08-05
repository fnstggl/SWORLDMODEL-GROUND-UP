"""Builder: ``ConcordiaInitializationPlan`` -> live stock Concordia objects.

Uses only the audited public upstream APIs (CONCORDIA_AUDIT.md sections A,
3, and E); nothing upstream is forked or patched:

- actors: ``EntityAgentWithLogging`` with
  ``ConcatActComponent(randomize_choices=False)``, a ``Constant`` component
  carrying the actor's private init data, ``LastNObservations``,
  ``ObservationToMemory``, and ``ListMemory`` over a plain per-actor list
  (the embedder-free upstream memory; associative retrieval is not needed
  by this baseline).
- game master: ``EntityAgentWithLogging`` with ``SwitchAct`` and the
  EXPLICIT component roster named by ``plan.gm_config['component_roster']``:
  :class:`RosterValidatedMakeObservation` (an
  ``allow_llm_fallback=False`` ``MakeObservation`` subclass that resolves
  every game-master-authored observer name against the branch roster and
  RECORDS the ones that do not resolve instead of letting upstream key
  them into a queue nobody reads) with the plan's initial
  observations pre-queued, ``NextActingInFixedOrder`` (deterministic
  baseline) or ``NextActing`` where the plan says the model chooses,
  ``FixedActionSpec`` for the fixed free-form call to action,
  ``EventResolution(event_resolution_steps=<plan chain> + (guard,),
  notify_observers=<plan>)`` whose FINAL slot is the guard seam -- by
  default the Phase 5 minimum agency guard built from the plan's actor
  roster (``guard.make_agency_guard``); the identity step occupies the
  slot only when the plan says ``agency_guard_enabled=False``, and an
  explicitly injected ``guard_step`` callable replaces the slot occupant
  outright -- an explicit ``Terminate`` component, and a shared
  game-master memory list.
  Because every SwitchAct dispatch key is present, the game master has no
  model-improvising ("YOLO") fallback path.

Language-model objects are constructor parameters -- this module never
creates, configures, or calls a model itself.  The upstream narrative-push
resolution step is refused by name: it may never enter the chain.

This module needs the optional ``gdm-concordia`` package (Python >= 3.12).
When that package is absent the import below fails immediately with a
clear ImportError, while ``import sworldmodel`` and the planner submodule
keep working everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

from sworldmodel.decision.contracts import ConcordiaInitializationPlan

from .guard import GUARD_SLOT_VALUE, make_agency_guard

_IMPORT_HELP = (
    "sworldmodel.backends.concordia_local.builder requires the optional "
    "'gdm-concordia' engine package (Python >= 3.12). Install it in the "
    "engine environment to use this backend; 'import sworldmodel' and the "
    "planner submodule work without it."
)

try:
    from concordia.agents import entity_agent_with_logging
    from concordia.components import agent as agent_components
    from concordia.components import game_master as gm_components
    from concordia.typing import entity as entity_lib
except ImportError as exc:  # degrade loudly, never partially
    raise ImportError(f"{_IMPORT_HELP} (root cause: {exc!r})") from exc

MEMORY_KEY = agent_components.memory.DEFAULT_MEMORY_COMPONENT_KEY
MAKE_OBS_KEY = (
    gm_components.make_observation.DEFAULT_MAKE_OBSERVATION_COMPONENT_KEY)
NEXT_ACTING_KEY = (
    gm_components.next_acting.DEFAULT_NEXT_ACTING_COMPONENT_KEY)
NEXT_ACTION_SPEC_KEY = (
    gm_components.next_acting.DEFAULT_NEXT_ACTION_SPEC_COMPONENT_KEY)
TERMINATE_KEY = gm_components.terminate.DEFAULT_TERMINATE_COMPONENT_KEY
RESOLUTION_KEY = (
    gm_components.event_resolution.DEFAULT_RESOLUTION_COMPONENT_KEY)
EVENT_TAG = gm_components.event_resolution.EVENT_TAG
PUTATIVE_EVENT_TAG = gm_components.event_resolution.PUTATIVE_EVENT_TAG

#: upstream resolution steps that may NEVER be placed in the chain
FORBIDDEN_CHAIN_STEPS = ("maybe_inject_narrative_push",)

#: roster name -> reserved SwitchAct component key (fixed-name components)
_ROSTER_TO_KEY = {
    "memory": MEMORY_KEY,
    "observation_to_memory": "observation_to_memory",
    "shared_setup": "shared_setup",
    "make_observation": MAKE_OBS_KEY,
    "next_acting": NEXT_ACTING_KEY,
    "next_action_spec": NEXT_ACTION_SPEC_KEY,
    "event_resolution": RESOLUTION_KEY,
    "terminate": TERMINATE_KEY,
}
_REQUIRED_ROSTER = ("memory", "observation_to_memory", "make_observation",
                    "next_acting", "next_action_spec", "event_resolution",
                    "terminate")

PRIVATE_SETUP_LABEL = "Private setup"
SHARED_SETUP_LABEL = "Shared setup"

#: upstream's broadcast keyword: ``ObservationQueue.add`` fans an event
#: out to every player when the entity name casefolds to exactly this
#: (make_observation.py at the pinned SHA).  Preserved verbatim.
OBSERVER_BROADCAST_KEYWORD = "all"

#: boundary characters stripped from a game-master-authored observer name
#: before matching.  Upstream's call site already strips ``' .,'``
#: (event_resolution.py); this superset additionally removes the mention
#: sigil and quoting/bracketing punctuation a free-text answer picks up.
_OBSERVER_STRIP_CHARS = " \t\r\n.,;:!?'\"“”‘’`()[]{}<>*_-@#"

#: excerpt cap for the event text recorded next to an unresolved observer
_OBSERVER_EXCERPT_LIMIT = 120


def normalize_observer_name(text: str) -> str:
    """Conservative normalization of one game-master-authored observer
    name: outer whitespace and boundary punctuation (including a leading
    ``@``) removed.  Interior bytes are untouched -- nothing is
    abbreviated, expanded, or guessed."""
    if not isinstance(text, str):
        return ""
    return text.strip().strip(_OBSERVER_STRIP_CHARS).strip()


def _fold_observer_name(text: str) -> str:
    """Case- and whitespace-insensitive comparison form of a name."""
    return " ".join(normalize_observer_name(text).split()).casefold()


class PlanBuildError(ValueError):
    """A plan cannot be built as declared; nothing is repaired silently."""


class ObserverRoutingError(RuntimeError):
    """An observer-routing request the seam refuses to honor."""


class RosterValidatedMakeObservation(
        gm_components.make_observation.MakeObservation):
    """``MakeObservation`` that never drops an observer name SILENTLY.

    Defect closed (2026-08-04 under-the-hood validation).  Upstream
    ``EventResolution`` asks the game-master model, in free text, "Which
    entities are aware of the event?" and hands each comma-separated
    fragment to ``ObservationQueue.add`` (event_resolution.py at the
    pinned SHA).  ``ObservationQueue.add`` CREATES A KEY for whatever
    string it is given, so a name that does not match a roster entity
    lands in a phantom queue nobody ever reads: the event is dropped with
    no error and no record.  Verified directly against the pinned
    upstream -- ``add("@PeterThiel", ...)`` then
    ``get_and_clear("Peter Thiel")`` returns ``[]``.  In the live runs
    this killed the one branch whose sender actually enacted its
    candidate.

    The seam is OURS, not upstream's: this subclass is what the builder
    rosters, so ``add_to_queue`` -- the single entry point upstream uses
    -- resolves the name against the branch's own roster first:

    - exact match on the name as given, then on the normalized form
      (:func:`normalize_observer_name`), then a case- and
      whitespace-folded match that is used only when it is UNAMBIGUOUS;
    - upstream's ``all`` broadcast keyword keeps its upstream meaning;
    - anything else is RECORDED VERBATIM in :attr:`unresolved_observers`
      and not enqueued.

    Deliberately NOT fuzzy: no prefix, token-overlap, or edit-distance
    matching.  Delivering an event to the wrong actor is a worse failure
    than not delivering it, and the recorded evidence makes the
    non-delivery visible instead of silent.  Delivery semantics are
    therefore unchanged; only the silence is.
    """

    def __init__(self, *args, roster_names, **kwargs):
        super().__init__(*args, **kwargs)
        names = tuple(roster_names)
        if not names:
            raise ObserverRoutingError(
                "roster_names must name at least one entity: an observer "
                "seam with no roster can resolve nothing")
        self._roster_names = names
        self._exact = {name: name for name in names}
        folded: dict = {}
        for name in names:
            folded.setdefault(_fold_observer_name(name), []).append(name)
        self._folded = folded
        self._unresolved_observers: list = []

    @property
    def roster_names(self) -> tuple:
        return self._roster_names

    @property
    def unresolved_observers(self) -> list:
        """Every non-resolving observer name this branch saw, in order."""
        return [dict(entry) for entry in self._unresolved_observers]

    def resolve_observer_name(self, entity_name):
        """``(canonical_name | None, reason)`` for one observer name.

        ``canonical_name`` is always a roster name (or upstream's
        broadcast keyword); ``reason`` names the resolution path taken so
        an unresolved record says WHY.
        """
        if not isinstance(entity_name, str):
            return None, "not_a_string"
        if entity_name in self._exact:
            return self._exact[entity_name], "exact"
        normalized = normalize_observer_name(entity_name)
        if not normalized:
            return None, "blank_after_normalization"
        if normalized in self._exact:
            return self._exact[normalized], "exact_after_normalization"
        folded = _fold_observer_name(normalized)
        if folded == OBSERVER_BROADCAST_KEYWORD:
            return OBSERVER_BROADCAST_KEYWORD, "broadcast_keyword"
        matches = self._folded.get(folded, ())
        if len(matches) == 1:
            return matches[0], "case_folded"
        if len(matches) > 1:
            return None, "ambiguous_roster_match"
        return None, "no_roster_match"

    def add_to_queue(self, entity_name, event: str):
        """Roster-validated enqueue: resolved names route exactly as
        upstream routes them; a non-resolving name is recorded, never
        silently keyed into a queue nobody reads."""
        resolved, reason = self.resolve_observer_name(entity_name)
        if resolved is None:
            raw = entity_name if isinstance(entity_name, str) \
                else repr(entity_name)
            self._unresolved_observers.append({
                "observer_name": raw,
                "normalized": normalize_observer_name(raw),
                "reason": reason,
                "event_excerpt": (event or "")[:_OBSERVER_EXCERPT_LIMIT],
            })
            return
        super().add_to_queue(resolved, event)

    def get_state(self):
        state = dict(super().get_state())
        state["unresolved_observers"] = [
            dict(entry) for entry in self._unresolved_observers]
        return state

    def set_state(self, state) -> None:
        super().set_state(state)
        restored = state.get("unresolved_observers", ())
        self._unresolved_observers = [dict(entry) for entry in restored]


def identity_guard_step(document, event_statement: str,
                        active_player_name: str) -> str:
    """Identity guard-seam occupant: passes the resolved event through
    unchanged.  Since Phase 5 the agency guard occupies the slot by
    default; this step is installed only when the plan explicitly says
    ``agency_guard_enabled=False`` (the Phase 4 baseline shape), keeping
    the slot position (final resolution step, pre-commit, pre-observer)
    exercised in every configuration."""
    del document, active_player_name
    return event_statement


@dataclass
class BuiltBranch:
    """Live Concordia objects for one branch plus capture handles."""

    plan_id: str
    world_id: str
    actor_order: tuple            # actor_ids in acting/declaration order
    actor_names: dict             # actor_id -> entity name
    actors: dict                  # actor_id -> EntityAgentWithLogging
    actor_memory_lists: dict      # actor_id -> the plain backing list
    game_master: object
    gm_memory_list: list          # the shared GM backing list
    make_observation: object      # RosterValidatedMakeObservation handle
    terminate: object             # Terminate (programmatic stop handle)
    guard_step: Callable
    neutral_premise: str
    max_steps: int
    run_metadata: dict = field(default_factory=dict)


def _require_config(gm_config: Mapping, key: str):
    if key not in gm_config:
        raise PlanBuildError(
            f"gm_config is missing required key {key!r}; the builder never "
            "invents a value for an absent setting")
    return gm_config[key]


def _resolve_chain(chain_value: str) -> tuple:
    """Resolve the plan's comma-joined resolution-step names to upstream
    callables.  Empty string -> empty chain.  The narrative-push step is
    refused by name; unknown names are errors, never ignored."""
    if not isinstance(chain_value, str):
        raise PlanBuildError(
            "gm_config['event_resolution_chain'] must be a comma-joined "
            f"string of step names, got {type(chain_value).__name__}")
    names = [name.strip() for name in chain_value.split(",") if name.strip()]
    steps = []
    for name in names:
        if name in FORBIDDEN_CHAIN_STEPS:
            raise PlanBuildError(
                f"resolution step {name!r} is forbidden in this backend: "
                "it injects model-invented complications into committed "
                "events")
        step = getattr(gm_components.event_resolution, name, None)
        if not callable(step):
            raise PlanBuildError(
                f"unknown event resolution step {name!r}; only public "
                "callables of the upstream event_resolution module may be "
                "named")
        steps.append(step)
    return tuple(steps)


def _resolve_actor_model(actor_models, actor_id: str):
    if isinstance(actor_models, Mapping):
        if actor_id not in actor_models:
            raise PlanBuildError(
                f"actor_models mapping has no model for actor {actor_id!r};"
                " every configured actor needs an explicit model object")
        model = actor_models[actor_id]
    else:
        model = actor_models
    if model is None:
        raise PlanBuildError(
            f"no language model supplied for actor {actor_id!r}; model "
            "objects are constructor parameters, never defaulted")
    return model


def build_branch(
    plan: ConcordiaInitializationPlan,
    *,
    actor_models,
    gm_model,
    guard_step: Callable | None = None,
    guard_escalate: Callable | None = None,
    skip_initial_seeding: bool = False,
) -> BuiltBranch:
    """Construct live Concordia objects exactly as the plan declares.

    ``actor_models`` is either one model object used for every actor or a
    mapping ``actor_id -> model``.  ``gm_model`` drives the game master.

    The FINAL event-resolution slot is filled from the plan:
    ``agency_guard_enabled=True`` (the default the planner emits) builds
    the minimum agency guard from the plan's actor-name roster;
    ``False`` installs :func:`identity_guard_step`.  The plan's declared
    ``guard_slot`` string must agree with the flag -- a mismatch is an
    error, never reconciled silently.  An explicitly injected
    ``guard_step`` callable (signature ``(document, event_statement,
    active_player_name) -> str``) REPLACES the slot occupant outright
    (test/diagnostic wiring).

    ``guard_escalate`` is forwarded as the ``escalate`` hook of the
    builder-constructed agency guard (the runner uses it to record guard
    interventions).  It applies ONLY to that constructed guard: combined
    with an injected ``guard_step`` it is refused as ambiguous, and with
    a disabled guard the identity step never rewrites, so the hook is
    inert by construction.

    ``skip_initial_seeding=True`` exists for exactly one caller -- the
    Phase 8 checkpoint restore path (``checkpoint.restore_branch``) --
    and skips the two initial-seeding effects (pre-queuing the plan's
    initial observations and delivering the pre-start game-master event
    record): a restored branch receives that state, as evolved, from the
    checkpoint's component state, and seeding it again would duplicate
    observations and memory rows.  Every other caller must leave the
    default ``False``.
    """
    if type(skip_initial_seeding) is not bool:
        raise PlanBuildError("skip_initial_seeding must be a boolean")
    if not isinstance(plan, ConcordiaInitializationPlan):
        raise PlanBuildError(
            "build_branch expects a ConcordiaInitializationPlan instance, "
            f"got {type(plan).__name__}")
    if gm_model is None:
        raise PlanBuildError(
            "gm_model is required; model objects are constructor "
            "parameters, never defaulted")
    if "max_steps" not in plan.run_limits:
        raise PlanBuildError(
            "run_limits must carry the code-owned 'max_steps' engine-step "
            "budget")
    if plan.run_limits["max_steps"] < 1:
        raise PlanBuildError("run_limits['max_steps'] must be >= 1")

    gm_config = plan.gm_config
    engine_name = _require_config(gm_config, "engine")
    if engine_name != "sequential":
        raise PlanBuildError(
            f"unsupported engine {engine_name!r}: this backend builds for "
            "the stock sequential engine only")
    gm_name = _require_config(gm_config, "gm_name")
    acting_order = _require_config(gm_config, "acting_order")
    roster_value = _require_config(gm_config, "component_roster")
    spec_output_type = _require_config(gm_config, "action_spec_output_type")
    call_to_action = _require_config(gm_config, "action_spec_call_to_action")
    chain_value = _require_config(gm_config, "event_resolution_chain")
    guard_slot = _require_config(gm_config, "guard_slot")
    notify_observers = _require_config(gm_config, "notify_observers")
    observation_fallback = _require_config(gm_config, "observation_fallback")
    memory_backend = _require_config(gm_config, "memory_backend")
    history_length = _require_config(gm_config, "history_length")
    start_time = _require_config(gm_config, "start_time")
    cutoff_time = _require_config(gm_config, "cutoff_time")

    if spec_output_type != "free":
        raise PlanBuildError(
            f"unsupported action_spec_output_type {spec_output_type!r}: "
            "v1 builds free-form actor turns only")
    if memory_backend != "list":
        raise PlanBuildError(
            f"unsupported memory_backend {memory_backend!r}: v1 uses the "
            "upstream embedder-free ListMemory")
    if type(history_length) is not int or history_length < 1:
        raise PlanBuildError(
            "gm_config['history_length'] must be an integer >= 1")
    if observation_fallback is not False:
        raise PlanBuildError(
            "gm_config['observation_fallback'] must be False: the game "
            "master may never invent observations for an empty queue")
    if type(notify_observers) is not bool:
        raise PlanBuildError(
            "gm_config['notify_observers'] must be a boolean")

    roster = [name.strip() for name in roster_value.split(",")
              if name.strip()]
    unknown = [name for name in roster if name not in _ROSTER_TO_KEY]
    if unknown:
        raise PlanBuildError(
            "component_roster names unknown components: "
            + ", ".join(sorted(unknown)))
    if len(set(roster)) != len(roster):
        raise PlanBuildError("component_roster contains duplicates")
    missing = [name for name in _REQUIRED_ROSTER if name not in roster]
    if missing:
        raise PlanBuildError(
            "component_roster is missing required components: "
            + ", ".join(missing))
    shared_in_roster = "shared_setup" in roster
    shared_present = bool(plan.shared_init_data.strip())
    if shared_in_roster != shared_present:
        raise PlanBuildError(
            "component_roster and shared_init_data disagree: 'shared_setup'"
            " must be rostered exactly when shared_init_data is non-blank")

    agency_guard_enabled = _require_config(gm_config, "agency_guard_enabled")
    if type(agency_guard_enabled) is not bool:
        raise PlanBuildError(
            "gm_config['agency_guard_enabled'] must be a boolean")
    expected_guard_slot = (GUARD_SLOT_VALUE if agency_guard_enabled
                           else "identity")
    if guard_slot != expected_guard_slot:
        raise PlanBuildError(
            f"plan declares guard slot {guard_slot!r} but "
            f"agency_guard_enabled={agency_guard_enabled!r} requires "
            f"{expected_guard_slot!r}; the builder never reconciles the "
            "two silently")
    if guard_escalate is not None and not callable(guard_escalate):
        raise PlanBuildError("guard_escalate must be callable when provided")
    if guard_step is not None:
        if not callable(guard_step):
            raise PlanBuildError("guard_step must be callable")
        if guard_escalate is not None:
            raise PlanBuildError(
                "guard_escalate applies only to the builder-constructed "
                "agency guard; combining it with an injected guard_step "
                "is ambiguous")

    chain = _resolve_chain(chain_value)

    # ---------------- actors ----------------
    actor_order = tuple(config.actor_id for config in plan.actor_configs)
    actor_names = {config.actor_id: config.name
                   for config in plan.actor_configs}
    names_in_order = [actor_names[actor_id] for actor_id in actor_order]
    if len(set(names_in_order)) != len(names_in_order):
        raise PlanBuildError(
            "actor names must be unique: Concordia addresses entities by "
            "name")

    # ---------------- final guard slot ----------------
    if guard_step is not None:
        guard = guard_step
    elif agency_guard_enabled:
        guard = make_agency_guard(names_in_order, escalate=guard_escalate)
    else:
        guard = identity_guard_step

    actors = {}
    actor_memory_lists = {}
    for config in plan.actor_configs:
        model = _resolve_actor_model(actor_models, config.actor_id)
        backing_list: list = []
        actor = entity_agent_with_logging.EntityAgentWithLogging(
            agent_name=config.name,
            act_component=(
                agent_components.concat_act_component.ConcatActComponent(
                    model=model,
                    randomize_choices=False,
                    prefix_entity_name=False,
                )),
            context_components={
                "private_setup": agent_components.constant.Constant(
                    state=config.private_init_data,
                    pre_act_label=PRIVATE_SETUP_LABEL,
                ),
                MEMORY_KEY: agent_components.memory.ListMemory(
                    memory_bank=backing_list),
                "observation_to_memory": (
                    agent_components.observation.ObservationToMemory()),
                "recent_observations": (
                    agent_components.observation.LastNObservations(
                        history_length=history_length)),
            },
        )
        actors[config.actor_id] = actor
        actor_memory_lists[config.actor_id] = backing_list

    # ---------------- game master ----------------
    gm_memory_list: list = []
    make_observation = RosterValidatedMakeObservation(
        model=gm_model,
        player_names=list(names_in_order),
        allow_llm_fallback=False,
        roster_names=tuple(names_in_order),
    )
    terminate = gm_components.terminate.Terminate()
    if acting_order == "fixed":
        next_acting = gm_components.next_acting.NextActingInFixedOrder(
            sequence=list(names_in_order))
    elif acting_order == "game_master_choice":
        next_acting = gm_components.next_acting.NextActing(
            model=gm_model, player_names=list(names_in_order))
    else:
        raise PlanBuildError(
            f"unsupported acting_order {acting_order!r}; allowed: 'fixed', "
            "'game_master_choice'")

    built_components = {
        "memory": (MEMORY_KEY, agent_components.memory.ListMemory(
            memory_bank=gm_memory_list)),
        "observation_to_memory": (
            "observation_to_memory",
            agent_components.observation.ObservationToMemory()),
        "shared_setup": (
            "shared_setup",
            agent_components.constant.Constant(
                state=plan.shared_init_data,
                pre_act_label=SHARED_SETUP_LABEL)),
        "make_observation": (MAKE_OBS_KEY, make_observation),
        "next_acting": (NEXT_ACTING_KEY, next_acting),
        "next_action_spec": (
            NEXT_ACTION_SPEC_KEY,
            gm_components.next_acting.FixedActionSpec(
                action_spec=entity_lib.free_action_spec(
                    call_to_action=call_to_action))),
        "event_resolution": (
            RESOLUTION_KEY,
            gm_components.event_resolution.EventResolution(
                model=gm_model,
                event_resolution_steps=chain + (guard,),
                notify_observers=notify_observers,
            )),
        "terminate": (TERMINATE_KEY, terminate),
    }
    gm_context_components = {}
    for name in roster:
        key, component = built_components[name]
        gm_context_components[key] = component

    game_master = entity_agent_with_logging.EntityAgentWithLogging(
        agent_name=gm_name,
        act_component=gm_components.switch_act.SwitchAct(
            model=gm_model, entity_names=list(names_in_order)),
        context_components=gm_context_components,
    )

    if not skip_initial_seeding:
        # Pre-queue initial observations exactly as the plan orders them.
        for actor_id in actor_order:
            for observation in plan.initial_observations.get(actor_id, ()):
                make_observation.add_to_queue(actor_names[actor_id],
                                              observation)

        # Give the game master the pre-start event record.
        for framed_event in plan.gm_initial_events:
            game_master.observe(f"{EVENT_TAG} {framed_event}")

    return BuiltBranch(
        plan_id=plan.plan_id,
        world_id=plan.world_id,
        actor_order=actor_order,
        actor_names=actor_names,
        actors=actors,
        actor_memory_lists=actor_memory_lists,
        game_master=game_master,
        gm_memory_list=gm_memory_list,
        make_observation=make_observation,
        terminate=terminate,
        guard_step=guard,
        neutral_premise=plan.neutral_premise,
        max_steps=plan.run_limits["max_steps"],
        run_metadata={"start_time": start_time, "cutoff_time": cutoff_time},
    )
