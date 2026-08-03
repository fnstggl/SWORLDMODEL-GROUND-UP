"""Dotted-name model-spec registry for the distributed suite (test-owned).

This module is the serializable-model seam's test half: the executor
ships ``{"model_builder": "distributed_model_specs:build_scripted_models",
"params": {...}}`` into every branch workspace, and each Ray WORKER
imports this module by that dotted name (the suite conftest puts this
directory on PYTHONPATH before ``init_dispatchers()`` so the captured job
config lets workers import it) and rebuilds the models from the params
alone.  The DRIVER-side local runs in the equivalence tests build their
model factory through the SAME builder, so local-vs-distributed
equivalence measures the execution substrate, not two hand-written model
stacks.

Everything here is deterministic and offline; params are pure JSON.
``ScriptedRuleModel`` reproduces the proven baseline-toolkit semantics
(tests/engine_baseline/baseline_helpers.py::StrictScriptedModel): first
rule whose needle occurs in the prompt answers; a multi-response rule
pops responses in order until one remains; an unmatched prompt or any
``sample_choice`` call fails loudly.  It is self-contained (no
baseline_helpers import) because workers only have THIS directory and the
repository root on their path.

Scenario vocabulary (fixture actor names, call-to-action lines, script
responses) never lives here -- it arrives through params built by the
tests from the frozen fixture.
"""

from __future__ import annotations

import time

from concordia.language_model import language_model

#: response placeholder replaced by the branch candidate's action text
CANDIDATE_ACTION_TOKEN = "__CANDIDATE_ACTION__"


class ScriptedRuleModel(language_model.LanguageModel):
    """Deterministic strict scripted model over ``(needle, responses)``
    rules; optional blocking per-call delay for concurrency probes."""

    def __init__(self, rules, *, delay_s: float = 0.0):
        self._rules = []
        for needle, responses in rules:
            responses = list(responses)
            if not needle or not responses:
                raise ValueError("each rule needs a non-empty needle and "
                                 "at least one response")
            self._rules.append((needle, responses))
        self._delay_s = float(delay_s or 0.0)
        self.prompts: list = []

    def sample_text(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        if self._delay_s:
            # Deliberate BLOCKING sleep: occupies this worker's task slot
            # for the wall-clock duration (concurrency-bound probe).
            time.sleep(self._delay_s)
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
            "sample_choice was called: the deterministic distributed suite "
            "must never take a multiple-choice model path; prompt head: "
            f"{prompt[:200]!r}")


class MidRunFailingModel(language_model.LanguageModel):
    """Raises on every call: injected mid-branch failure inside a worker
    (the failure-isolation proofs)."""

    def __init__(self, marker: str):
        self.marker = marker

    def sample_text(self, prompt: str, **kwargs) -> str:
        raise RuntimeError(self.marker)

    def sample_choice(self, prompt: str, responses, **kwargs):
        raise RuntimeError(self.marker)


def _substituted(rules, candidate):
    """Fresh rule lists per model instance (multi-response rules mutate),
    with the candidate-action token substituted."""
    out = []
    for needle, responses in rules:
        out.append((needle,
                    [candidate.action if response == CANDIDATE_ACTION_TOKEN
                     else response for response in responses]))
    return out


def build_scripted_models(params):
    """The registered builder: ``builder(params)`` returns the local
    manager's model-provider contract
    ``provider(candidate, branch_seed) -> (actor_models, gm_model)``.

    params (pure JSON)::

        {
          "actor_rules": {actor_id: [[needle, [response, ...]], ...]},
          "gm_rules": [[needle, [response, ...]], ...],
          "delay_s": optional float -- blocking sleep per ACTOR-model call,
          "failing": optional {
              "actor": actor_id whose model raises,
              "candidate_ids": [candidate_id, ...] to fail,
              "marker_prefix": str prepended to the candidate id,
          },
        }
    """
    failing = params.get("failing") or {}
    failing_actor = failing.get("actor")
    failing_ids = frozenset(failing.get("candidate_ids") or ())
    marker_prefix = str(failing.get("marker_prefix") or
                        "INJECTED_DISTRIBUTED_FAILURE_")
    delay_s = float(params.get("delay_s") or 0.0)

    def provider(candidate, branch_seed):
        del branch_seed  # scripted behavior is fully rule-determined
        actor_models = {}
        for actor_id, rules in params["actor_rules"].items():
            if actor_id == failing_actor \
                    and candidate.candidate_id in failing_ids:
                actor_models[actor_id] = MidRunFailingModel(
                    marker_prefix + candidate.candidate_id)
            else:
                actor_models[actor_id] = ScriptedRuleModel(
                    _substituted(rules, candidate), delay_s=delay_s)
        gm_model = ScriptedRuleModel(_substituted(params["gm_rules"],
                                                  candidate))
        return actor_models, gm_model

    return provider
