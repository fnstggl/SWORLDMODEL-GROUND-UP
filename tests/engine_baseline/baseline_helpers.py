"""Test-owned helpers for the engine-baseline suite (engine env only).

Import this module AFTER the per-module version/importorskip gates: it
imports the Concordia language-model interface, which only exists in the
pinned engine environment (Python >= 3.12).
"""

from __future__ import annotations

import json
from pathlib import Path

from concordia.language_model import language_model

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: the exact observer question EventResolution asks (event_resolution.py,
#: notify_observers block) -- the ONLY scripted GM model path in this suite
AWARE_QUESTION_NEEDLE = "Which entities are aware of the event?"


class StrictScriptedModel(language_model.LanguageModel):
    """Deterministic, STRICT scripted model (test-owned subclass of the
    public upstream interface; upstream is untouched).

    ``rules`` is a sequence of ``(needle, responses)`` pairs.
    ``sample_text`` records the prompt, finds the FIRST rule whose needle
    occurs in the prompt, and returns its next response in order (once a
    single response remains it repeats, so per-step recurring questions
    like the observer query stay scriptable).

    Strictness is the point:
    - an unmatched prompt raises AssertionError -- any unscripted model
      call (an upstream YOLO fallback, an unexpected component path)
      fails the test loudly instead of silently degrading determinism;
    - ``sample_choice`` always raises -- no multiple-choice model path may
      execute anywhere in the YOLO-free baseline (that is where upstream's
      unseeded option shuffling lives).
    """

    def __init__(self, rules):
        self._rules = []
        for needle, responses in rules:
            responses = list(responses)
            if not needle or not responses:
                raise ValueError(
                    "each rule needs a non-empty needle and at least one "
                    "response")
            self._rules.append((needle, responses))
        self.prompts: list = []

    def sample_text(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        for needle, responses in self._rules:
            if needle in prompt:
                if len(responses) > 1:
                    return responses.pop(0)
                return responses[0]
        raise AssertionError(
            "unscripted sample_text call reached the model; prompt head: "
            f"{prompt[:400]!r}")

    def sample_choice(self, prompt: str, responses, **kwargs):
        raise AssertionError(
            "sample_choice was called: the YOLO-free baseline must never "
            f"take a multiple-choice model path; prompt head: "
            f"{prompt[:200]!r}")


def aware_rule(names) -> tuple:
    """GM rule answering the observer question with a fixed name list."""
    return (AWARE_QUESTION_NEEDLE, [", ".join(names)])


def run_signature(result) -> str:
    """Byte-comparable trace signature of one runner result.

    Covers the committed event stream, the full per-actor memories, the
    shaped event trace, the step count, and the terminal status.  The raw
    engine log is deliberately excluded from BYTE comparison: its per-step
    ``make_observation`` sub-dicts are keyed by entity name in thread-pool
    completion order (sequential.py fan-out), so key ORDER is not part of
    the deterministic trace contract.
    """
    return json.dumps(
        {
            "committed_events": result["committed_events"],
            "event_trace": result["event_trace"],
            "actor_memories": result["actor_memories"],
            "steps_completed": result["steps_completed"],
            "terminal_status": result["terminal_status"],
        },
        sort_keys=True,
    )


def all_prompt_text(model: StrictScriptedModel) -> str:
    """Every prompt a scripted model received, joined for containment
    assertions."""
    return "\n\n<<<PROMPT>>>\n\n".join(model.prompts)
