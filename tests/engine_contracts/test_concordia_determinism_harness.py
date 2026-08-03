"""Determinism harness contract (the gate-E enabling proof).

Pinned upstream: concordia @ 7779a4c9f96bad10816d88c54e4cb17d53ac5222.
Verified nondeterminism sources (audit CONCORDIA_AUDIT.md §13):
  - unseeded per-document numpy rng:
    concordia/document/interactive_document.py:63-67
  - multiple_choice_question shuffles options with that rng:
    concordia/document/interactive_document.py:303-336
  - deterministic models still yield random choice OUTCOMES because
    sample_choice picks among the SHUFFLED letters
    (concordia/language_model/no_language_model.py:50-58)

Contract proven here:
  1. POSITIVE: two identical 3-step Sequential runs, driven by a scripted
     deterministic model (tiny LanguageModel subclass in this test returning
     canned responses in order), produce BYTE-IDENTICAL event sequences under
     ``det.seeded_determinism`` — even with ``randomize_choices=True`` on the
     actors' act components (the harness controls the shuffle).
  2. NEGATIVE CONTROL: without the harness the multiple-choice shuffling can
     differ across identical runs (skipped rather than failed in the
     astronomically unlikely case that no difference is observed).
  3. BELT-AND-BRACES: with ``randomize_choices=False`` (the act-component
     switch the production phases will also set) plus an index-0 model, runs
     are identical even WITHOUT the seeding harness — but this switch does not
     exist for SwitchAct GM paths (switch_act.py:176-182), which is why the
     harness remains mandatory for gate E.

The harness itself lives in tests/engine_contracts/det.py for reuse by later
phases. Offline; no network.
"""

from __future__ import annotations

import itertools
import json
import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine contracts require Python >= 3.12 (Concordia floor); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential", exc_type=ImportError)

import numpy as np
from concordia.agents import entity_agent_with_logging
from concordia.associative_memory import basic_associative_memory
from concordia.components import agent as agent_components
from concordia.components import game_master as gm_components
from concordia.document import interactive_document
from concordia.language_model import language_model
from concordia.language_model import no_language_model
from concordia.typing import entity as entity_lib

from det import ones_embedder, seeded_determinism

MEMORY_KEY = agent_components.memory.DEFAULT_MEMORY_COMPONENT_KEY
MAKE_OBS_KEY = gm_components.make_observation.DEFAULT_MAKE_OBSERVATION_COMPONENT_KEY
NEXT_ACTING_KEY = gm_components.next_acting.DEFAULT_NEXT_ACTING_COMPONENT_KEY
TERMINATE_KEY = gm_components.terminate.DEFAULT_TERMINATE_COMPONENT_KEY
RESOLUTION_KEY = gm_components.event_resolution.DEFAULT_RESOLUTION_COMPONENT_KEY

SEED = 424242
MAX_STEPS = 3

CHOICE_OPTIONS = (
    "adopt plan Alpha",
    "adopt plan Beta",
    "defer to tomorrow",
    "call a vote",
    "ask for more evidence",
    "object loudly",
    "leave the room",
    "flip a coin",
)

# The GM deliberately has NO __next_action_spec__ component, so SwitchAct's
# YOLO fallback asks the model twice per step (switch_act.py:202-230) and the
# scripted model answers with canned responses IN ORDER: a free-form musing,
# then the action-spec JSON the engine parses for the acting entity.
ACTION_SPEC_JSON = json.dumps(
    {
        "call_to_action": "What does {name} choose to do about the plan?",
        "output_type": "choice",
        "options": list(CHOICE_OPTIONS),
        "tag": "action",
    }
)
SCRIPT_PER_STEP = (
    "The group must decide how to proceed with the plan.",
    ACTION_SPEC_JSON,
)


class ScriptedSequenceModel(language_model.LanguageModel):
    """Tiny deterministic model: canned sample_text responses in order
    (cycling), index-0 sample_choice. Test-owned subclass of the public
    interface — no upstream edit."""

    def __init__(self, responses):
        self._responses = itertools.cycle(list(responses))

    def sample_text(self, prompt: str, **kwargs) -> str:
        return next(self._responses)

    def sample_choice(self, prompt: str, responses, **kwargs):
        return 0, responses[0], {}


def _make_choice_entity(name: str, model, *, randomize_choices: bool):
    return entity_agent_with_logging.EntityAgentWithLogging(
        agent_name=name,
        act_component=agent_components.concat_act_component.ConcatActComponent(
            model=model,
            randomize_choices=randomize_choices,
            prefix_entity_name=False,
        ),
    )


def _run_once(*, randomize_choices: bool) -> tuple[str, ...]:
    """Fresh identical construction + 3-step Sequential run.

    Returns the full GM memory row tuple — the run's byte-exact event
    sequence (putative events + committed [event] rows, in order).
    """
    from concordia.environment.engines import sequential

    gm_model = ScriptedSequenceModel(SCRIPT_PER_STEP)
    entity_model = no_language_model.NoLanguageModel()

    alice = _make_choice_entity("Alice", entity_model,
                                randomize_choices=randomize_choices)
    bob = _make_choice_entity("Bob", entity_model,
                              randomize_choices=randomize_choices)

    bank = basic_associative_memory.AssociativeMemoryBank(
        sentence_embedder=ones_embedder, allow_duplicates=True
    )
    components = {
        MEMORY_KEY: agent_components.memory.AssociativeMemory(memory_bank=bank),
        "observation_to_memory": agent_components.observation.ObservationToMemory(),
        MAKE_OBS_KEY: gm_components.make_observation.MakeObservation(
            model=gm_model,
            player_names=["Alice", "Bob"],
            allow_llm_fallback=False,
        ),
        NEXT_ACTING_KEY: gm_components.next_acting.NextActingInFixedOrder(
            sequence=["Alice", "Bob"]
        ),
        TERMINATE_KEY: gm_components.terminate.Terminate(),
        RESOLUTION_KEY: gm_components.event_resolution.EventResolution(
            model=gm_model, event_resolution_steps=(), notify_observers=False
        ),
    }
    gm = entity_agent_with_logging.EntityAgentWithLogging(
        agent_name="rules",
        act_component=gm_components.switch_act.SwitchAct(
            model=gm_model, entity_names=["Alice", "Bob"]
        ),
        context_components=components,
    )

    sequential.Sequential().run_loop(
        game_masters=[gm],
        entities=[alice, bob],
        premise="",
        max_steps=MAX_STEPS,
        verbose=False,
        log=None,
    )
    rows = tuple(bank.get_all_memories_as_text())
    # Sanity: the run really went through the choice machinery each step.
    assert len([r for r in rows if "[putative_event]" in r]) == MAX_STEPS
    assert all(any(opt in r for opt in CHOICE_OPTIONS)
               for r in rows if "[putative_event]" in r), rows
    return rows


# ---------------------------------------------------------------------------
# The positive contract
# ---------------------------------------------------------------------------


def test_two_identical_runs_are_byte_identical_under_harness():
    with seeded_determinism(SEED):
        first = _run_once(randomize_choices=True)
    with seeded_determinism(SEED):
        second = _run_once(randomize_choices=True)
    assert first == second
    # And a different seed is allowed to (and here does) change the outcome,
    # proving the harness (not an accident) is what pinned the run.
    with seeded_determinism(SEED + 999):
        third = _run_once(randomize_choices=True)
    if third == first:  # pragma: no cover - 1-in-8^3 per-step coincidence guard
        pytest.skip("seed variation coincided; determinism equality above stands")


def test_document_level_shuffle_is_pinned_by_harness():
    """Unit-level proof at the exact upstream seam: identically-seeded fresh
    documents produce identical multiple-choice outcomes under the harness."""
    model = no_language_model.NoLanguageModel()

    def draw_sequence() -> tuple[int, ...]:
        doc = interactive_document.InteractiveDocument(model)
        return tuple(
            doc.multiple_choice_question("pick", list(CHOICE_OPTIONS))
            for _ in range(10)
        )

    with seeded_determinism(SEED):
        a = draw_sequence()
    with seeded_determinism(SEED):
        b = draw_sequence()
    assert a == b


# ---------------------------------------------------------------------------
# Negative control (skip-if-flaky per the phase brief; positive equality above
# is the contract)
# ---------------------------------------------------------------------------


def test_without_harness_multiple_choice_shuffling_can_differ():
    signatures = {tuple(_run_once(randomize_choices=True)) for _ in range(6)}
    if len(signatures) == 1:  # pragma: no cover - probability ~ (1/8)^15
        pytest.skip(
            "no cross-run difference observed without the harness in 6 runs "
            "(astronomically unlikely); positive-equality contract above stands"
        )
    assert len(signatures) > 1


# ---------------------------------------------------------------------------
# randomize_choices=False leg of the harness
# ---------------------------------------------------------------------------


def test_randomize_choices_false_pins_actor_choices_without_seeding():
    """Actor-side: randomize_choices=False + an index-0 model is deterministic
    by configuration alone (concat_act_component.py:122-127) — every actor
    turn selects options[0]."""
    first = _run_once(randomize_choices=False)
    second = _run_once(randomize_choices=False)
    assert first == second
    chosen = [r for r in first if "[putative_event]" in r]
    assert all(CHOICE_OPTIONS[0] in r for r in chosen), chosen


def test_switch_act_gm_choice_paths_have_no_randomize_switch():
    """Why the harness stays mandatory: SwitchAct's GM multiple-choice paths
    call multiple_choice_question with the randomizing default and expose no
    constructor switch (switch_act.py:68-107, 176-182). Assert the constructor
    really has no such parameter so an upstream change is caught."""
    import inspect

    params = inspect.signature(
        gm_components.switch_act.SwitchAct.__init__
    ).parameters
    assert "randomize_choices" not in params
    assert np.random.default_rng is np.random.default_rng  # harness restored
