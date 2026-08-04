"""Concordia Game Master contracts: explicit-component GM, sequential engine
per-step order effects, and the EventResolution custom-final-step guard seam.

Pinned upstream: concordia @ 7779a4c9f96bad10816d88c54e4cb17d53ac5222.
Verified sources for the contracts asserted here:
  - engine per-step order + single event-commit primitive
    gm.observe('[event] ...'): concordia/environment/engines/sequential.py:148-335
  - SwitchAct dispatch on reserved component keys:
    concordia/components/game_master/switch_act.py:274-338
  - EventResolution custom chain, each step
    (InteractiveDocument, event_str, active_player_name) -> str, last output IS
    the event statement; observer notification runs AFTER the chain:
    concordia/components/game_master/event_resolution.py:40-247, 1282-1308
  - MakeObservation queue + allow_llm_fallback=False:
    concordia/components/game_master/make_observation.py:85-266
  - NextActingInFixedOrder / FixedActionSpec:
    concordia/components/game_master/next_acting.py:257-336, 712-758
  - Terminate component: concordia/components/game_master/terminate.py:25-66

THE GUARD SEAM (load-bearing for Phase 5): a custom final callable appended to
``event_resolution_steps`` receives the fully-resolved candidate event BEFORE
the engine's '[event]' commit and before observer notification, and whatever
it returns is what gets committed. Proven below by rewrite, veto, and
observer-queue inspection.

Offline: scripted deterministic models subclassing the public LanguageModel
interface (test-owned code — not an upstream edit). No network.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine contracts require Python >= 3.12 (Concordia floor); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential", exc_type=ImportError)

from concordia.agents import entity_agent_with_logging
from concordia.associative_memory import basic_associative_memory
from concordia.components import agent as agent_components
from concordia.components import game_master as gm_components
from concordia.environment.engines import sequential
from concordia.language_model import language_model
from concordia.typing import entity as entity_lib

from det import ones_embedder

MEMORY_KEY = agent_components.memory.DEFAULT_MEMORY_COMPONENT_KEY
MAKE_OBS_KEY = gm_components.make_observation.DEFAULT_MAKE_OBSERVATION_COMPONENT_KEY
NEXT_ACTING_KEY = gm_components.next_acting.DEFAULT_NEXT_ACTING_COMPONENT_KEY
NEXT_ACTION_SPEC_KEY = (
    gm_components.next_acting.DEFAULT_NEXT_ACTION_SPEC_COMPONENT_KEY
)
TERMINATE_KEY = gm_components.terminate.DEFAULT_TERMINATE_COMPONENT_KEY
RESOLUTION_KEY = gm_components.event_resolution.DEFAULT_RESOLUTION_COMPONENT_KEY
EVENT_TAG = gm_components.event_resolution.EVENT_TAG  # '[event]'
PUTATIVE_EVENT_TAG = gm_components.event_resolution.PUTATIVE_EVENT_TAG

ALICE_ACTION = "greets Bob warmly and proposes lunch"
BOB_ACTION = "nods back and accepts the lunch proposal"


class ScriptedRuleModel(language_model.LanguageModel):
    """Deterministic offline model: prompt-content-keyed canned text.

    ``sample_text`` returns the answer of the first (needle, answer) rule whose
    needle occurs in the prompt, else ``default``. ``sample_choice`` always
    returns index 0. Subclasses the public LanguageModel interface in OUR test
    code — upstream is untouched.
    """

    def __init__(self, rules=(), default: str = ""):
        self._rules = list(rules)
        self._default = default
        self.text_prompts: list[str] = []

    def sample_text(self, prompt: str, **kwargs) -> str:
        self.text_prompts.append(prompt)
        for needle, answer in self._rules:
            if needle in prompt:
                return answer
        return self._default

    def sample_choice(self, prompt: str, responses, **kwargs):
        return 0, responses[0], {}


def _make_entity(name: str, model: language_model.LanguageModel):
    """Minimal REAL entity: concat act + associative memory + observations."""
    bank = basic_associative_memory.AssociativeMemoryBank(
        sentence_embedder=ones_embedder
    )
    entity = entity_agent_with_logging.EntityAgentWithLogging(
        agent_name=name,
        act_component=agent_components.concat_act_component.ConcatActComponent(
            model=model,
            randomize_choices=False,
            prefix_entity_name=False,
        ),
        context_components={
            MEMORY_KEY: agent_components.memory.AssociativeMemory(memory_bank=bank),
            "observation_to_memory": (
                agent_components.observation.ObservationToMemory()
            ),
            "recent": agent_components.observation.LastNObservations(
                history_length=100
            ),
        },
    )
    return entity, bank


def _make_gm(
    model: language_model.LanguageModel,
    player_names,
    *,
    event_resolution_steps=(),
    notify_observers: bool = False,
):
    """Assemble a GM exactly as the audit prescribes for Phase 4+:

    EntityAgentWithLogging + SwitchAct + explicit components:
    MakeObservation(allow_llm_fallback=False), NextActingInFixedOrder,
    EventResolution(custom steps, notify_observers as given), Terminate,
    FixedActionSpec — configuration, not forking.
    """
    bank = basic_associative_memory.AssociativeMemoryBank(
        sentence_embedder=ones_embedder, allow_duplicates=True
    )
    make_observation = gm_components.make_observation.MakeObservation(
        model=model, player_names=list(player_names), allow_llm_fallback=False
    )
    terminate = gm_components.terminate.Terminate()
    components = {
        MEMORY_KEY: agent_components.memory.AssociativeMemory(memory_bank=bank),
        "observation_to_memory": agent_components.observation.ObservationToMemory(),
        MAKE_OBS_KEY: make_observation,
        NEXT_ACTING_KEY: gm_components.next_acting.NextActingInFixedOrder(
            sequence=list(player_names)
        ),
        NEXT_ACTION_SPEC_KEY: gm_components.next_acting.FixedActionSpec(
            action_spec=entity_lib.free_action_spec(
                call_to_action="What does {name} do?"
            )
        ),
        TERMINATE_KEY: terminate,
        RESOLUTION_KEY: gm_components.event_resolution.EventResolution(
            model=model,
            event_resolution_steps=tuple(event_resolution_steps),
            notify_observers=notify_observers,
        ),
    }
    gm = entity_agent_with_logging.EntityAgentWithLogging(
        agent_name="rules",
        act_component=gm_components.switch_act.SwitchAct(
            model=model, entity_names=list(player_names)
        ),
        context_components=components,
    )
    return gm, bank, make_observation, terminate


def _entity_rules():
    return [
        ("What does Alice do?", ALICE_ACTION),
        ("What does Bob do?", BOB_ACTION),
    ]


def _event_rows(bank) -> list[str]:
    return [m for m in bank.get_all_memories_as_text() if EVENT_TAG in m]


# ---------------------------------------------------------------------------
# Sequential engine per-step order effects with two real entities
# ---------------------------------------------------------------------------


def test_sequential_run_order_effects_and_event_commit():
    entity_model = ScriptedRuleModel(_entity_rules())
    gm_model = ScriptedRuleModel()
    alice, alice_bank = _make_entity("Alice", entity_model)
    bob, bob_bank = _make_entity("Bob", entity_model)
    gm, gm_bank, make_observation, _terminate = _make_gm(
        gm_model, ["Alice", "Bob"]
    )

    # Queued initial observations (audit: MakeObservation.add_to_queue is the
    # supported initial-observation channel).
    make_observation.add_to_queue("Alice", "ALPHA_BRIEF: you owe Bob a reply.")
    make_observation.add_to_queue("Bob", "BETA_BRIEF: expect a message from Alice.")

    engine = sequential.Sequential()
    engine.run_loop(
        game_masters=[gm],
        entities=[alice, bob],
        premise="",
        max_steps=2,
        verbose=False,
        log=None,
    )

    # (1) Entities received exactly their own queued observations.
    alice_memories = list(alice_bank.get_all_memories_as_text())
    bob_memories = list(bob_bank.get_all_memories_as_text())
    assert any("ALPHA_BRIEF" in m for m in alice_memories), alice_memories
    assert not any("BETA_BRIEF" in m for m in alice_memories)
    assert any("BETA_BRIEF" in m for m in bob_memories), bob_memories
    assert not any("ALPHA_BRIEF" in m for m in bob_memories)

    # (2) Observation delivery precedes the act: the prompt that produced
    # Alice's action already contained her queued observation.
    alice_prompts = [
        p for p in entity_model.text_prompts if "What does Alice do?" in p
    ]
    assert alice_prompts, entity_model.text_prompts
    assert "ALPHA_BRIEF" in alice_prompts[0]

    # (3) Fixed acting order: step 1 Alice, step 2 Bob; each action string
    # reached resolution and was committed with the [event] tag.
    rows = list(gm_bank.get_all_memories_as_text())
    putative = [m for m in rows if PUTATIVE_EVENT_TAG in m]
    events = _event_rows(gm_bank)
    assert len(putative) == 2 and len(events) == 2, rows
    assert "Alice:" in putative[0] and ALICE_ACTION in putative[0]
    assert "Bob:" in putative[1] and BOB_ACTION in putative[1]
    assert ALICE_ACTION in events[0]
    assert BOB_ACTION in events[1]


def test_terminate_component_ends_loop_before_max_steps():
    entity_model = ScriptedRuleModel(_entity_rules())
    alice, _ = _make_entity("Alice", entity_model)
    bob, _ = _make_entity("Bob", entity_model)
    gm, gm_bank, _make_obs, terminate = _make_gm(
        ScriptedRuleModel(), ["Alice", "Bob"]
    )

    def stop_after_two(steps_done: int) -> None:
        # checkpoint_callback fires at end-of-step with the incremented step
        # count (sequential.py:361-362); Terminate.terminate() is the public
        # programmatic termination switch (terminate.py:55-56).
        if steps_done >= 2:
            terminate.terminate()

    sequential.Sequential().run_loop(
        game_masters=[gm],
        entities=[alice, bob],
        premise="",
        max_steps=50,
        verbose=False,
        log=None,
        checkpoint_callback=stop_after_two,
    )
    assert len(_event_rows(gm_bank)) == 2


def test_max_steps_caps_the_loop():
    entity_model = ScriptedRuleModel(_entity_rules())
    alice, _ = _make_entity("Alice", entity_model)
    bob, _ = _make_entity("Bob", entity_model)
    gm, gm_bank, _make_obs, _terminate = _make_gm(
        ScriptedRuleModel(), ["Alice", "Bob"]
    )

    sequential.Sequential().run_loop(
        game_masters=[gm],
        entities=[alice, bob],
        premise="",
        max_steps=3,
        verbose=False,
        log=None,
    )
    assert len(_event_rows(gm_bank)) == 3


def test_premise_is_committed_as_event_before_first_step():
    entity_model = ScriptedRuleModel(_entity_rules())
    alice, _ = _make_entity("Alice", entity_model)
    bob, _ = _make_entity("Bob", entity_model)
    gm, gm_bank, _make_obs, _terminate = _make_gm(
        ScriptedRuleModel(), ["Alice", "Bob"]
    )

    sequential.Sequential().run_loop(
        game_masters=[gm],
        entities=[alice, bob],
        premise="PREMISE_MARK: Alice and Bob share an office.",
        max_steps=1,
        verbose=False,
        log=None,
    )
    events = _event_rows(gm_bank)
    # premise commit (sequential.py:243-246) + one resolved step event.
    assert len(events) == 2
    assert "PREMISE_MARK" in events[0]
    assert ALICE_ACTION in events[1]


# ---------------------------------------------------------------------------
# THE GUARD SEAM: custom final event_resolution_steps callable
# ---------------------------------------------------------------------------


def test_guard_step_receives_candidate_pre_commit_and_rewrites_the_commit():
    guard_calls: list[dict] = []
    entity_model = ScriptedRuleModel(_entity_rules())
    alice, _ = _make_entity("Alice", entity_model)
    bob, _ = _make_entity("Bob", entity_model)

    gm_bank_ref: list = []  # filled after _make_gm; closure reads it.

    def upstream_step(document, event: str, active_player_name: str) -> str:
        # A benign non-final chain step, to prove chaining feeds the guard.
        return event + " (weather: clear)"

    def guard(document, event: str, active_player_name: str) -> str:
        bank = gm_bank_ref[0]
        committed_events_now = [
            m for m in bank.get_all_memories_as_text() if EVENT_TAG in m
        ]
        guard_calls.append(
            {
                "event": event,
                "active_player": active_player_name,
                "committed_events_at_call_time": committed_events_now,
            }
        )
        return event + " [GUARD_STAMP_58f2]"

    gm, gm_bank, _make_obs, _terminate = _make_gm(
        ScriptedRuleModel(),
        ["Alice", "Bob"],
        event_resolution_steps=(upstream_step, guard),
    )
    gm_bank_ref.append(gm_bank)

    sequential.Sequential().run_loop(
        game_masters=[gm],
        entities=[alice, bob],
        premise="",
        max_steps=1,
        verbose=False,
        log=None,
    )

    # The guard ran exactly once, as the FINAL chain step, and saw the
    # fully-resolved candidate (including the prior step's rewrite) plus the
    # active player name — signature (document, event, active_player_name).
    assert len(guard_calls) == 1
    call = guard_calls[0]
    assert call["active_player"] == "Alice"
    assert ALICE_ACTION in call["event"]
    assert "(weather: clear)" in call["event"]
    # PRE-COMMIT: at guard call time nothing carried the [event] tag yet.
    assert call["committed_events_at_call_time"] == []

    # The guard's RETURN VALUE is what the engine committed as [event].
    events = _event_rows(gm_bank)
    assert len(events) == 1
    assert "[GUARD_STAMP_58f2]" in events[0]
    assert ALICE_ACTION in events[0]


def test_guard_step_can_veto_with_a_different_statement():
    veto_text = "Nothing is decided; the proposal awaits Bob's own turn. [VETOED_9a1c]"
    entity_model = ScriptedRuleModel(_entity_rules())
    alice, _ = _make_entity("Alice", entity_model)
    bob, _ = _make_entity("Bob", entity_model)

    def veto_guard(document, event: str, active_player_name: str) -> str:
        return veto_text

    gm, gm_bank, _make_obs, _terminate = _make_gm(
        ScriptedRuleModel(),
        ["Alice", "Bob"],
        event_resolution_steps=(veto_guard,),
    )
    sequential.Sequential().run_loop(
        game_masters=[gm],
        entities=[alice, bob],
        premise="",
        max_steps=1,
        verbose=False,
        log=None,
    )
    events = _event_rows(gm_bank)
    assert len(events) == 1
    assert "[VETOED_9a1c]" in events[0]
    # The vetoed candidate action text is NOT in the committed event...
    assert ALICE_ACTION not in events[0]
    # ...while the attempt is still visible as a [putative_event] audit row.
    putative = [
        m for m in gm_bank.get_all_memories_as_text() if PUTATIVE_EVENT_TAG in m
    ]
    assert len(putative) == 1 and ALICE_ACTION in putative[0]


def test_guard_rewrite_happens_before_observer_notification():
    """With notify_observers=True, observers are queued AFTER the chain runs
    (event_resolution.py:219-236) — so they receive the GUARDED statement."""
    entity_model = ScriptedRuleModel(_entity_rules())
    alice, _ = _make_entity("Alice", entity_model)
    bob, _ = _make_entity("Bob", entity_model)

    def guard(document, event: str, active_player_name: str) -> str:
        return event + " [GUARDED_FOR_OBSERVERS_c4d7]"

    gm_model = ScriptedRuleModel([("Which entities are aware", "Bob")])
    gm, _gm_bank, make_observation, _terminate = _make_gm(
        gm_model,
        ["Alice", "Bob"],
        event_resolution_steps=(guard,),
        notify_observers=True,
    )
    sequential.Sequential().run_loop(
        game_masters=[gm],
        entities=[alice, bob],
        premise="",
        max_steps=1,
        verbose=False,
        log=None,
    )
    queue_state = make_observation.get_state()["queue"]
    assert "Bob" in queue_state, queue_state
    queued_for_bob = queue_state["Bob"]
    assert len(queued_for_bob) == 1
    assert "[GUARDED_FOR_OBSERVERS_c4d7]" in queued_for_bob[0]
    assert ALICE_ACTION in queued_for_bob[0]
