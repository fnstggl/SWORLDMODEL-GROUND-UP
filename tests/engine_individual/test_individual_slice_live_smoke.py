"""Phase 9 slice, LIVE-MODEL smoke leg (DeepSeek chat API).

The directive requires "multiple live-model smoke runs when credentials
are available": TWO independent slice passes (different seeds) drive the
same route -> manager -> outcomes -> reporting pipeline with a minimal
test-owned Concordia ``LanguageModel`` over the DeepSeek
OpenAI-compatible endpoint (individual_helpers.DeepSeekChatModel;
base https://api.deepseek.com, model deepseek-chat, temperature 0,
bounded tokens, generous per-call timeout).

Cost/latency bounds: 2 actors, 2 candidates, max_steps=2 per branch
(~4-6 live calls per branch).

Assertions are MECHANICAL ONLY -- live output is never asserted
semantically or for determinism:

  - every branch reaches an EXPLICIT terminal status from the closed set;
  - the causal trace artifact is complete and validates (committed
    events present wherever the runner returned, actor records, guard
    escalations recorded if any);
  - the recommendation report validates and carries the mandatory
    'live_model' provenance label;
  - per-call evidence (served model id, elapsed seconds) is recorded.

Flake policy: a run whose branches carry live-TRANSPORT evidence (the
``LIVE_ENDPOINT_UNREACHABLE`` marker the model wrapper records) is
retried exactly once; a second transport failure FAILS the test with the
exact recorded network evidence -- with the key set, an unreachable
endpoint is reportable, never skippable, and clearly distinguished from
an assertion failure.
"""

from __future__ import annotations

import os
import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine individual-slice suite requires Python >= 3.12 "
        "(Concordia floor); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DEEPSEEK_API_KEY"),
    reason="DEEPSEEK_API_KEY is not set; live-model smoke leg needs "
           "credentials")

import time
from dataclasses import dataclass

from individual_helpers import (DEEPSEEK_MODEL_ID, anchored_predicates,
                                fixture_status_rule, live_factory_builder,
                                load_fixture_one, make_slice_problem,
                                transport_failures)
from sworldmodel.compilation.decision_route import prepare_decision_inputs
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.decision.contracts import (RecommendationResult,
                                            TERMINAL_STATUSES)
from sworldmodel.outcomes import evaluate_branches
from sworldmodel.reporting import (build_recommendation_report,
                                   build_trace_report,
                                   validate_recommendation_report,
                                   validate_trace_report)

LIVE_MAX_STEPS = 2
LIVE_CANDIDATE_COUNT = 2


@dataclass(frozen=True)
class LiveOutcome:
    evaluated: tuple
    recommendation: RecommendationResult
    report: dict
    trace: dict


def _one_live_pass(seed, evidence):
    """One full live slice pass.  Returns ``(outcome, transport)``:
    when any branch carries live-transport evidence, ``outcome`` is None
    and ``transport`` holds the recorded errors (evaluation is not
    attempted over transport-broken branches -- the retry policy owns
    them)."""
    api_key = os.environ["DEEPSEEK_API_KEY"]
    fx = load_fixture_one()
    actions = [candidate.action
               for candidate in fx.candidates[:LIVE_CANDIDATE_COUNT]]
    problem = make_slice_problem(fx, actions=actions)
    inputs = prepare_decision_inputs(
        problem, fx.world, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)
    capture: dict = {}
    run = run_candidates_detailed(
        inputs.world, inputs.candidates,
        model_factory=live_factory_builder(
            fx, capture, api_key=api_key, evidence=evidence),
        seed=seed, max_steps=LIVE_MAX_STEPS,
        evaluator_spec=inputs.evaluator_spec, registry=inputs.registry,
        model_config={"kind": "live_model_smoke",
                      "model": DEEPSEEK_MODEL_ID})
    transport = transport_failures(run.results)
    if transport:
        return None, transport
    evaluated = evaluate_branches(
        run.results, anchored_predicates(),
        evaluator_spec=inputs.evaluator_spec,
        status_rule=fixture_status_rule, registry=inputs.registry)
    report = build_recommendation_report(
        problem, inputs.candidates, run, evaluated,
        inputs.evaluator_spec, provenance_label="live_model",
        registry=inputs.registry)
    trace = build_trace_report(run, evaluated)
    outcome = LiveOutcome(
        evaluated=tuple(evaluated),
        recommendation=RecommendationResult.from_dict(
            report["recommendation"]),
        report=report, trace=trace)
    return outcome, ()


def _smoke_run(seed):
    """One smoke run with the retry-once transport policy; returns
    (outcome, evidence, wall_seconds, attempts_used)."""
    last_transport = None
    for attempt in (1, 2):
        evidence: list = []
        started = time.perf_counter()
        outcome, transport = _one_live_pass(seed + attempt - 1, evidence)
        wall = time.perf_counter() - started
        if not transport:
            return outcome, evidence, wall, attempt
        last_transport = transport
    pytest.fail(
        "live endpoint unreachable after one retry (NETWORK evidence, "
        "not an assertion failure); recorded infrastructure errors:\n"
        + "\n---\n".join(last_transport))


def _assert_mechanical(outcome, evidence):
    # Explicit terminal statuses from the closed set, per branch.
    assert len(outcome.evaluated) == LIVE_CANDIDATE_COUNT
    for result in outcome.evaluated:
        assert result.terminal_status in TERMINAL_STATUSES

    # Both artifacts validate structurally (citations resolve, guard
    # records well-formed, actor records complete).
    validate_recommendation_report(outcome.report)
    validate_trace_report(outcome.trace)
    assert "Result provenance: live_model." \
        in outcome.recommendation.run_limitations
    assert isinstance(outcome.report["decided_by_metric"], str)

    # Complete causal trace wherever the runner returned: the premise
    # commits before any model call, so a runner-returned branch always
    # carries committed events; guard escalations (if any) are recorded
    # next to the trace, never dropped.
    for branch in outcome.trace["branches"]:
        if branch["runner_record_available"]:
            assert len(branch["committed_events"]) >= 1
            assert isinstance(branch["guard_interventions"], list)
            records = branch["actor_records"]
            assert sorted(records) == ["recipient", "sender"]
        else:
            # A branch that never reached the runner must say so
            # explicitly and carry its recorded errors.
            assert branch["terminal_status"] == "incomplete"
            assert branch["infrastructure_errors"]

    # Live-call evidence was recorded: the endpoint served a model for
    # every call, with sane latency figures.
    assert evidence, "no live model call was recorded"
    for record in evidence:
        assert record["served_model"], record
        assert record["elapsed_s"] >= 0.0

    return {
        "calls": len(evidence),
        "served_models": sorted({r["served_model"] for r in evidence}),
        "statuses": [r.terminal_status for r in outcome.evaluated],
    }


def test_live_smoke_run_one():
    outcome, evidence, wall, attempts = _smoke_run(seed=20260803)
    summary = _assert_mechanical(outcome, evidence)
    print(f"\n[live smoke 1] requested_model={DEEPSEEK_MODEL_ID} "
          f"summary={summary} wall_s={wall:.1f} attempts={attempts}")


def test_live_smoke_run_two():
    outcome, evidence, wall, attempts = _smoke_run(seed=913026)
    summary = _assert_mechanical(outcome, evidence)
    print(f"\n[live smoke 2] requested_model={DEEPSEEK_MODEL_ID} "
          f"summary={summary} wall_s={wall:.1f} attempts={attempts}")
