"""Dotted-name model-spec registry for the checkpoint suite (test-owned).

The Stage B restore contract requires models whose behavior is a pure
function of ``(prompt, active RNG scope)`` -- a resumed branch rebuilds
its model objects FRESH, so any hidden per-model position counter (like a
multi-response rule popping answers) would silently desynchronize the
continuation.  This module therefore enforces PROMPT-PURITY structurally:
every rule carries exactly ONE response (checked at build time), and step
differentiation comes from needles that only appear in later-step prompts
(earlier turns' committed events ride the actors' observation context).

``PROMPT-PURE + RNG`` variant: ``rng_draw_actors`` names actors whose
model appends one global-``random`` 32-bit draw to every response --
``"<response> [rng-draw <n>]"`` -- making the committed event stream a
function of the EVOLVING global random stream.  That is the Stage B
discriminator: a resumed run only reproduces the uninterrupted run if the
checkpoint restored ``random``'s mid-run state; a naive re-seed restarts
the stream and diverges visibly in the trace.

Workers import this module by dotted name
(``checkpoint_model_specs:build_prompt_pure_models``); the suite conftest
puts this directory on PYTHONPATH before ``init_dispatchers()``.  The
module is self-contained (no helper-toolkit imports) because workers only
have this directory and the repository root on their path.
"""

from __future__ import annotations

import random

from concordia.language_model import language_model

#: response placeholder replaced by the branch candidate's action text
CANDIDATE_ACTION_TOKEN = "__CANDIDATE_ACTION__"

#: marker wrapped around every appended global-random draw
RNG_DRAW_MARKER = "rng-draw"


class PromptPureScriptedModel(language_model.LanguageModel):
    """Deterministic strict scripted model whose output is a pure
    function of the prompt: first rule whose needle occurs in the prompt
    answers with its SINGLE response; an unmatched prompt or any
    ``sample_choice`` call fails loudly.

    ``draw_rng=True`` appends one global-``random`` draw per call (the
    Stage B RNG-continuity discriminator; see the module docstring).
    """

    def __init__(self, rules, *, draw_rng: bool = False):
        self._rules = []
        for needle, response in rules:
            if not needle or not isinstance(response, str) or not response:
                raise ValueError(
                    "each prompt-pure rule needs a non-empty needle and "
                    "exactly one non-empty response string (no response "
                    "sequences: position counters would break resume)")
            self._rules.append((needle, response))
        self._draw_rng = bool(draw_rng)
        self.prompts: list = []

    def sample_text(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        for needle, response in self._rules:
            if needle in prompt:
                if self._draw_rng:
                    draw = random.getrandbits(32)
                    return f"{response} [{RNG_DRAW_MARKER} {draw}]"
                return response
        raise AssertionError(
            "unscripted sample_text call reached the model; prompt head: "
            f"{prompt[:400]!r}")

    def sample_choice(self, prompt: str, responses, **kwargs):
        raise AssertionError(
            "sample_choice was called: the deterministic checkpoint suite "
            "must never take a multiple-choice model path; prompt head: "
            f"{prompt[:200]!r}")


def _substituted(rules, candidate):
    """Fresh rule pairs with the candidate-action token substituted in
    needles and responses."""
    out = []
    for needle, response in rules:
        needle = candidate.action if needle == CANDIDATE_ACTION_TOKEN \
            else needle
        response = candidate.action if response == CANDIDATE_ACTION_TOKEN \
            else response
        out.append((needle, response))
    return out


def build_prompt_pure_models(params):
    """The registered builder: ``builder(params)`` returns the local
    manager's model-provider contract
    ``provider(candidate, branch_seed) -> (actor_models, gm_model)``.

    params (pure JSON)::

        {
          "actor_rules": {actor_id: [[needle, response], ...]},
          "gm_rules": [[needle, response], ...],
          "rng_draw_actors": optional [actor_id, ...] whose models append
              one global-random draw per call,
        }
    """
    draw_actors = frozenset(params.get("rng_draw_actors") or ())

    def provider(candidate, branch_seed):
        del branch_seed  # behavior is (prompt, active-RNG-scope)-pure
        actor_models = {}
        for actor_id, rules in params["actor_rules"].items():
            actor_models[actor_id] = PromptPureScriptedModel(
                _substituted(rules, candidate),
                draw_rng=actor_id in draw_actors)
        gm_model = PromptPureScriptedModel(
            _substituted(params["gm_rules"], candidate))
        return actor_models, gm_model

    return provider
