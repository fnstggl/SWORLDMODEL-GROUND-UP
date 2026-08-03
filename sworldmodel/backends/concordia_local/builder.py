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
  ``MakeObservation(allow_llm_fallback=False)`` with the plan's initial
  observations pre-queued, ``NextActingInFixedOrder`` (deterministic
  baseline) or ``NextActing`` where the plan says the model chooses,
  ``FixedActionSpec`` for the fixed free-form call to action,
  ``EventResolution(event_resolution_steps=<plan chain> + (guard,),
  notify_observers=<plan>)`` whose FINAL slot is the guard seam
  (identity here in Phase 4; Phase 5 injects the real agency guard), an
  explicit ``Terminate`` component, and a shared game-master memory list.
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


class PlanBuildError(ValueError):
    """A plan cannot be built as declared; nothing is repaired silently."""


def identity_guard_step(document, event_statement: str,
                        active_player_name: str) -> str:
    """Phase 4 guard-seam occupant: passes the resolved event through
    unchanged.  Phase 5 replaces this callable with the agency guard; the
    slot position (final resolution step, pre-commit, pre-observer) is
    already exercised by every baseline run."""
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
    make_observation: object      # MakeObservation (queue handle)
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
) -> BuiltBranch:
    """Construct live Concordia objects exactly as the plan declares.

    ``actor_models`` is either one model object used for every actor or a
    mapping ``actor_id -> model``.  ``gm_model`` drives the game master.
    ``guard_step`` (signature ``(document, event_statement,
    active_player_name) -> str``) occupies the FINAL event-resolution slot;
    when ``None`` the plan's declared ``guard_slot`` must be ``'identity'``
    and :func:`identity_guard_step` is installed.
    """
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

    if guard_step is None:
        if guard_slot != "identity":
            raise PlanBuildError(
                f"plan reserves guard slot {guard_slot!r} but no guard_step"
                " callable was injected")
        guard = identity_guard_step
    else:
        if not callable(guard_step):
            raise PlanBuildError("guard_step must be callable")
        guard = guard_step

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
    make_observation = gm_components.make_observation.MakeObservation(
        model=gm_model,
        player_names=list(names_in_order),
        allow_llm_fallback=False,
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

    # Pre-queue initial observations exactly as the plan orders them.
    for actor_id in actor_order:
        for observation in plan.initial_observations.get(actor_id, ()):
            make_observation.add_to_queue(actor_names[actor_id], observation)

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
