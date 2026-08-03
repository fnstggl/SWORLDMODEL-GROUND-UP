"""Model malformed output at the runner level
(OPERATIONAL_ROBUSTNESS_MATRIX row 12).

Generator-side malformed output (non-JSON, schema violations) is already
refused loudly by the route
(``tests/engine_compilation/test_decision_route.py::
test_malformed_generator_output_fails_loudly_with_all_defects``); a
raising ACTOR model is already isolated per branch
(``tests/engine_counterfactuals/test_failure_isolation.py``).  These
tests extend row 12 to the remaining actor/GM cases: a model that
RETURNS garbage instead of raising.

The bar is honest, not cosmetic: garbage output is not an execution
failure -- the engine commits it as the actor's turn -- so the required
properties are (a) BOUNDED completion with a valid structured
``BranchResult``, (b) FAIL-CLOSED measurement: no metric ever counts a
turn whose attributed content does not satisfy its predicate, (c) a
garbage GM observer answer FAILS CLOSED on information flow (delivers to
nobody) rather than guessing, and (d) when garbage breaks a strict
downstream consumer, the break surfaces as that branch's explicit
recorded infrastructure error -- reported, never hidden.

Recorded limitation (matrix row 12 notes): no engine-side size cap
exists on INJECTED model output -- a 200 kB reply is committed verbatim
to the trace; the live-model path is bounded upstream by the transport's
``MAX_RESPONSE_BYTES`` (4 MB) and provider ``max_tokens``.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "robustness suite requires Python >= 3.12 (engine env); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

import time

from baseline_helpers import StrictScriptedModel, aware_rule
from cf_helpers import (MAX_STEPS, SEED, SENDER_CTA, SENDER_IDLE_TURN,
                        fixture_predicates, load_fixture_one)
from concordia.language_model import language_model
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.outcomes import evaluate_branches

CANDIDATE_INDEX = 1  # concise_relevant

GARBAGE_PAYLOADS = {
    "empty": "",
    "whitespace": " \n\t \n",
    "control_chars": "\x00\x1b[31mgarbage\x07",
    "json_shaped": '{"not": "an action", "tool_call": []}',
    "oversized_200kb": "x" * 200_000,
}


class FixedOutputModel(language_model.LanguageModel):
    """Returns one fixed payload for every call (a live model gone
    wrong), never raises."""

    def __init__(self, text: str):
        self.text = text

    def sample_text(self, prompt: str, **kwargs) -> str:
        return self.text

    def sample_choice(self, prompt: str, responses, **kwargs):
        return 0, responses[0], {}


def _run_one(fx, factory):
    return run_candidates_detailed(
        fx.world, [fx.candidates[CANDIDATE_INDEX]], model_factory=factory,
        seed=SEED, max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=None)


@pytest.mark.parametrize("payload_id", sorted(GARBAGE_PAYLOADS))
def test_actor_garbage_completes_bounded_with_fail_closed_metrics(
        payload_id):
    """Row 12 (a)+(b): every garbage class from BOTH actor models yields
    a bounded run, a valid contract result, and all-False metrics."""
    payload = GARBAGE_PAYLOADS[payload_id]
    fx = load_fixture_one()

    def factory(candidate, branch_seed):
        del candidate, branch_seed
        return ({"sender": FixedOutputModel(payload),
                 "recipient": FixedOutputModel(payload)},
                StrictScriptedModel([aware_rule(["Alex", "Morgan"])]))

    started = time.monotonic()
    run = _run_one(fx, factory)
    wall = time.monotonic() - started
    result = run.results[0]

    assert wall < 30.0
    assert result.terminal_status == "cutoff"
    assert result.infrastructure_errors == ()
    assert len(result.event_trace) == 3  # premise + one turn per actor
    evaluated = evaluate_branches([result], fixture_predicates())
    assert {name: reading.value
            for name, reading in evaluated[0].outcome_metrics.items()} \
        == {"recipient_reply_sent": False, "meeting_scheduled": False,
            "explicit_decline": False}


def test_gm_garbage_observer_answer_fails_closed_on_delivery():
    """Row 12 (c): a GM that answers the observer question with garbage
    delivers the event to NOBODY (fail closed) instead of guessing; the
    run stays bounded and complete, metrics stay closed.  The control
    leg (correct GM answer) proves the delivery difference is the GM
    answer alone."""
    fx = load_fixture_one()
    candidate = fx.candidates[CANDIDATE_INDEX]
    neutral_turn = ("Morgan continues her scheduled work without opening "
                    "anything new.")

    def factory_with_gm(gm_model):
        def factory(cand, branch_seed):
            del branch_seed
            sender = StrictScriptedModel(
                [(SENDER_CTA, [cand.action, SENDER_IDLE_TURN])])
            recipient = FixedOutputModel(neutral_turn)
            return {"sender": sender, "recipient": recipient}, gm_model
        return factory

    garbage_run = _run_one(
        fx, factory_with_gm(FixedOutputModel("%%% NOT A NAME LIST @@@")))
    control_run = _run_one(
        fx, factory_with_gm(StrictScriptedModel(
            [aware_rule(["Alex", "Morgan"])])))

    for run in (garbage_run, control_run):
        result = run.results[0]
        assert result.terminal_status == "cutoff"
        assert result.infrastructure_errors == ()
        evaluated = evaluate_branches([result], fixture_predicates())
        assert not any(reading.value for reading
                       in evaluated[0].outcome_metrics.values())

    def recipient_saw_candidate_text(run) -> bool:
        record = run.runner_records[candidate.candidate_id]
        return any(candidate.action in row
                   for row in record["actor_memories"]["recipient"])

    assert recipient_saw_candidate_text(control_run) is True
    assert recipient_saw_candidate_text(garbage_run) is False


def test_garbage_breaking_a_strict_consumer_is_an_explicit_branch_error():
    """Row 12 (d): when the GM's garbage starves a STRICT downstream
    model of its scripted needle, the break is that branch's explicit
    recorded infrastructure error with the partial trace preserved --
    reported in place, never hidden, never a hang."""
    fx = load_fixture_one()

    def factory(candidate, branch_seed):
        del branch_seed
        sender = StrictScriptedModel(
            [(SENDER_CTA, [candidate.action, SENDER_IDLE_TURN])])
        recipient = StrictScriptedModel(
            [(candidate.action, ["Reply acknowledging the note."])])
        return ({"sender": sender, "recipient": recipient},
                FixedOutputModel("%%% NOT A NAME LIST @@@"))

    run = _run_one(fx, factory)
    result = run.results[0]
    assert result.terminal_status == "incomplete"
    assert len(result.infrastructure_errors) == 1
    assert "unscripted sample_text call" in result.infrastructure_errors[0]
    assert len(result.event_trace) == 2  # premise + the sender's turn
    evaluated = evaluate_branches([result], fixture_predicates())
    assert not any(reading.value for reading
                   in evaluated[0].outcome_metrics.values())
