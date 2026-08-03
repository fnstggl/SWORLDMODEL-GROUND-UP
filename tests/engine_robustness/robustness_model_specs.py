"""Deterministic hostile-model builders for the robustness suite.

Self-contained (imports only the Concordia language-model interface) so
subprocess children -- and, if ever needed, Ray workers -- can import it
by dotted name with only this directory and the repository root on their
path, mirroring ``distributed_model_specs`` / ``checkpoint_model_specs``.

``HangingModel`` is the model-timeout scenario's stimulus: its first
``sample_text`` call announces itself on stdout (so an outer monitor can
see the branch reached the model call) and then blocks forever.  The
production engine backend deliberately has NO in-branch model-call
timeout seam (matrix row 11 records this); the monitored runner's
no-progress kill is the outer bound the timeout test proves.
"""

from __future__ import annotations

import sys
import threading

from concordia.language_model import language_model


class HangingModel(language_model.LanguageModel):
    """Announces the first call, then blocks forever (never returns)."""

    def __init__(self, announce: str = "HANGING_MODEL_CALL_REACHED"):
        self._announce = announce
        self._announced = False

    def _hang(self):
        if not self._announced:
            self._announced = True
            print(self._announce, flush=True)
            sys.stdout.flush()
        threading.Event().wait()  # no timeout: blocks until killed

    def sample_text(self, prompt: str, **kwargs) -> str:
        self._hang()
        raise AssertionError("unreachable")  # pragma: no cover

    def sample_choice(self, prompt: str, responses, **kwargs):
        self._hang()
        raise AssertionError("unreachable")  # pragma: no cover


class ScriptedEchoModel(language_model.LanguageModel):
    """Minimal strict scripted model: first ``(needle, response)`` rule
    whose needle occurs in the prompt answers; unmatched prompts fail
    loudly (mirrors the proven baseline-toolkit semantics without
    importing it, keeping this module worker-safe)."""

    def __init__(self, rules):
        self._rules = [(needle, response) for needle, response in rules]

    def sample_text(self, prompt: str, **kwargs) -> str:
        for needle, response in self._rules:
            if needle in prompt:
                return response
        raise AssertionError(
            "unscripted sample_text call; prompt head: "
            f"{prompt[:300]!r}")

    def sample_choice(self, prompt: str, responses, **kwargs):
        raise AssertionError("sample_choice must never be reached")
