"""Concordia actor contracts: component lifecycle, memory persistence, ActionSpec.

Pinned upstream: concordia @ 7779a4c9f96bad10816d88c54e4cb17d53ac5222.
Verified sources for the contracts asserted here:
  - phase machine + act/observe order: concordia/agents/entity_agent.py:154-216,
    concordia/typing/entity_component.py:39-87
  - buffered memory commit at UPDATE: concordia/components/agent/memory.py:113-222
  - ObservationToMemory '[observation]' write: concordia/components/agent/observation.py:30-59
  - ActionSpec validation + dict round-trip: concordia/typing/entity.py:73-152

Offline: NoLanguageModel + trivial embedder; no network, no credentials.
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

pytest.importorskip("concordia.agents.entity_agent", exc_type=ImportError)

import numpy as np
from concordia.agents import entity_agent
from concordia.agents import entity_agent_with_logging
from concordia.associative_memory import basic_associative_memory
from concordia.components import agent as agent_components
from concordia.language_model import no_language_model
from concordia.typing import entity as entity_lib
from concordia.typing import entity_component

from det import ones_embedder

MEMORY_KEY = agent_components.memory.DEFAULT_MEMORY_COMPONENT_KEY  # '__memory__'

FREE_SPEC = entity_lib.free_action_spec(call_to_action="What does {name} do next?")


class PhaseRecorder(entity_component.ContextComponent):
    """Records (hook, entity phase at call time) for every lifecycle hook."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, entity_component.Phase]] = []

    def _record(self, hook: str) -> None:
        self.events.append((hook, self.get_entity().get_phase()))

    def pre_act(self, action_spec: entity_lib.ActionSpec) -> str:
        self._record("pre_act")
        return ""

    def post_act(self, action_attempt: str) -> str:
        self._record("post_act")
        return ""

    def pre_observe(self, observation: str) -> str:
        self._record("pre_observe")
        return ""

    def post_observe(self) -> str:
        self._record("post_observe")
        return ""

    def update(self) -> None:
        self._record("update")

    def get_state(self) -> entity_component.ComponentState:
        return {}

    def set_state(self, state: entity_component.ComponentState) -> None:
        del state


class BankProbe(entity_component.ContextComponent):
    """Reads the raw memory BANK (not the component) at observe-phase hooks.

    Phase barriers guarantee all pre_observe/post_observe calls complete before
    UPDATE begins (entity_agent.py:190-216), so what this probe sees at
    POST_OBSERVE is a race-free statement about commit timing.
    """

    def __init__(self, bank: basic_associative_memory.AssociativeMemoryBank,
                 needle: str) -> None:
        super().__init__()
        self._bank = bank
        self._needle = needle
        self.seen_at: dict[str, bool] = {}

    def _bank_has_needle(self) -> bool:
        return any(self._needle in m for m in self._bank.get_all_memories_as_text())

    def pre_observe(self, observation: str) -> str:
        self.seen_at["pre_observe"] = self._bank_has_needle()
        return ""

    def post_observe(self) -> str:
        self.seen_at["post_observe"] = self._bank_has_needle()
        return ""

    def get_state(self) -> entity_component.ComponentState:
        return {}

    def set_state(self, state: entity_component.ComponentState) -> None:
        del state


def _make_memory_agent(name: str = "Alex"):
    """Identically-constructible agent with a real associative memory stack."""
    model = no_language_model.NoLanguageModel()
    bank = basic_associative_memory.AssociativeMemoryBank(
        sentence_embedder=ones_embedder
    )
    agent = entity_agent_with_logging.EntityAgentWithLogging(
        agent_name=name,
        act_component=agent_components.concat_act_component.ConcatActComponent(
            model=model, randomize_choices=False
        ),
        context_components={
            MEMORY_KEY: agent_components.memory.AssociativeMemory(memory_bank=bank),
            "observation_to_memory": (
                agent_components.observation.ObservationToMemory()
            ),
            "recent": agent_components.observation.LastNObservations(
                history_length=10
            ),
        },
    )
    return agent, bank


# ---------------------------------------------------------------------------
# 1. Component lifecycle order
# ---------------------------------------------------------------------------


def test_act_lifecycle_phase_order():
    recorder = PhaseRecorder()
    agent = entity_agent.EntityAgent(
        agent_name="Ada",
        act_component=agent_components.concat_act_component.ConcatActComponent(
            model=no_language_model.NoLanguageModel(), randomize_choices=False
        ),
        context_components={"recorder": recorder},
    )
    assert agent.get_phase() == entity_component.Phase.READY

    action = agent.act(FREE_SPEC)
    assert isinstance(action, str)
    assert recorder.events == [
        ("pre_act", entity_component.Phase.PRE_ACT),
        ("post_act", entity_component.Phase.POST_ACT),
        ("update", entity_component.Phase.UPDATE),
    ]
    assert agent.get_phase() == entity_component.Phase.READY


def test_observe_lifecycle_phase_order():
    recorder = PhaseRecorder()
    agent = entity_agent.EntityAgent(
        agent_name="Ada",
        act_component=agent_components.concat_act_component.ConcatActComponent(
            model=no_language_model.NoLanguageModel(), randomize_choices=False
        ),
        context_components={"recorder": recorder},
    )
    agent.observe("A message arrived.")
    assert recorder.events == [
        ("pre_observe", entity_component.Phase.PRE_OBSERVE),
        ("post_observe", entity_component.Phase.POST_OBSERVE),
        ("update", entity_component.Phase.UPDATE),
    ]
    assert agent.get_phase() == entity_component.Phase.READY


def test_every_component_sees_all_phases_in_order():
    """Two independent recording components each see the same ordered phases."""
    rec_a, rec_b = PhaseRecorder(), PhaseRecorder()
    agent = entity_agent.EntityAgent(
        agent_name="Ada",
        act_component=agent_components.concat_act_component.ConcatActComponent(
            model=no_language_model.NoLanguageModel(), randomize_choices=False
        ),
        context_components={"rec_a": rec_a, "rec_b": rec_b},
    )
    agent.observe("hello")
    agent.act(FREE_SPEC)
    expected = [
        ("pre_observe", entity_component.Phase.PRE_OBSERVE),
        ("post_observe", entity_component.Phase.POST_OBSERVE),
        ("update", entity_component.Phase.UPDATE),
        ("pre_act", entity_component.Phase.PRE_ACT),
        ("post_act", entity_component.Phase.POST_ACT),
        ("update", entity_component.Phase.UPDATE),
    ]
    assert rec_a.events == expected
    assert rec_b.events == expected


def test_phase_machine_rejects_invalid_transition():
    with pytest.raises(ValueError):
        entity_component.Phase.READY.check_successor(entity_component.Phase.POST_ACT)
    # Valid successors do not raise.
    entity_component.Phase.READY.check_successor(entity_component.Phase.PRE_ACT)
    entity_component.Phase.READY.check_successor(entity_component.Phase.PRE_OBSERVE)


# ---------------------------------------------------------------------------
# 2. Memory persistence
# ---------------------------------------------------------------------------


def test_observation_lands_in_bank_only_after_update_phase():
    needle = "MEMO_NEEDLE_7731"
    model = no_language_model.NoLanguageModel()
    bank = basic_associative_memory.AssociativeMemoryBank(
        sentence_embedder=ones_embedder
    )
    probe = BankProbe(bank, needle)
    agent = entity_agent.EntityAgent(
        agent_name="Alex",
        act_component=agent_components.concat_act_component.ConcatActComponent(
            model=model, randomize_choices=False
        ),
        context_components={
            MEMORY_KEY: agent_components.memory.AssociativeMemory(memory_bank=bank),
            "observation_to_memory": (
                agent_components.observation.ObservationToMemory()
            ),
            "probe": probe,
        },
    )
    assert bank.get_all_memories_as_text() == []

    agent.observe(f"Alex noticed {needle} on the desk.")

    # Buffered during the observe phases; committed by AssociativeMemory.update()
    # during the UPDATE phase (components/agent/memory.py:216-222).
    assert probe.seen_at["pre_observe"] is False
    assert probe.seen_at["post_observe"] is False
    memories = bank.get_all_memories_as_text()
    assert any(needle in m for m in memories), memories
    # ObservationToMemory prefixes the observation tag (observation.py:58).
    assert any(m.startswith("[observation] ") and needle in m for m in memories)


def test_get_state_set_state_round_trips_memory_to_fresh_agent():
    agent_a, bank_a = _make_memory_agent()
    agent_a.observe("Alex received a short email from Morgan.")
    agent_a.observe("Alex saw the number 12345 on the whiteboard.")
    agent_a.act(FREE_SPEC)

    state = agent_a.get_state()
    memories_a = list(bank_a.get_all_memories_as_text())
    assert len(memories_a) == 2

    # Fresh, identically-constructed agent (set_state contract:
    # typing/entity_component.py:128-160).
    agent_b, bank_b = _make_memory_agent()
    assert bank_b.get_all_memories_as_text() == []
    agent_b.set_state(state)

    memories_b = list(bank_b.get_all_memories_as_text())
    assert memories_b == memories_a
    # And the restored agent's own get_state matches what it was given.
    assert agent_b.get_state() == state


def test_state_dict_shape_is_engine_serializable():
    agent_a, _ = _make_memory_agent()
    agent_a.observe("one observation")
    state = agent_a.get_state()
    assert set(state.keys()) == {"act_component", "context_components"}
    assert MEMORY_KEY in state["context_components"]
    # Memory component state carries bank + uncommitted buffer
    # (components/agent/memory.py:134-139).
    assert set(state["context_components"][MEMORY_KEY].keys()) == {
        "memory_bank",
        "buffer",
    }


# ---------------------------------------------------------------------------
# 3. ActionSpec validation + round-trip
# ---------------------------------------------------------------------------


def test_choice_spec_membership_enforced():
    spec = entity_lib.choice_action_spec(
        call_to_action="Will {name} reply?", options=("Yes", "No")
    )
    spec.validate("Yes")
    spec.validate("No")
    with pytest.raises(ValueError):
        spec.validate("Maybe")


def test_choice_spec_requires_options_and_rejects_duplicates():
    with pytest.raises(ValueError):
        entity_lib.choice_action_spec(call_to_action="Pick one")  # no options
    with pytest.raises(ValueError):
        entity_lib.choice_action_spec(
            call_to_action="Pick one", options=("a", "a")
        )


def test_options_forbidden_for_free_spec_and_float_validates():
    with pytest.raises(ValueError):
        entity_lib.free_action_spec(
            call_to_action="Say something", options=("a", "b")
        )
    float_spec = entity_lib.float_action_spec(call_to_action="How much?")
    float_spec.validate("3.25")
    with pytest.raises(ValueError):
        float_spec.validate("not-a-number")


def test_free_spec_round_trips_to_dict_from_dict():
    spec = entity_lib.free_action_spec(
        call_to_action="What does {name} say?", tag="speech"
    )
    restored = entity_lib.action_spec_from_dict(spec.to_dict())
    assert restored == spec

    choice = entity_lib.choice_action_spec(
        call_to_action="Choose", options=("x", "y", "z"), tag="action"
    )
    choice_restored = entity_lib.action_spec_from_dict(choice.to_dict())
    assert choice_restored == choice
    assert choice_restored.options == ("x", "y", "z")
    choice_restored.validate("y")


def test_engine_action_spec_string_round_trip():
    """The GM-side JSON serialization used by the engine parses back exactly."""
    from concordia.environment import engine as engine_lib

    spec = entity_lib.choice_action_spec(
        call_to_action="Will {name} attend?", options=("Yes", "No"), tag="action"
    )
    assert engine_lib.action_spec_parser(engine_lib.action_spec_to_string(spec)) == spec


def test_embedder_smoke_uses_numpy():
    # Guard that the shared test embedder stays trivially deterministic.
    assert np.array_equal(ones_embedder("anything"), np.ones(3))
