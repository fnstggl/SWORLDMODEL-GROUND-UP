"""THE Phase 6 milestone: frozen fixture 1 (individual_reply) end to end.

Pipeline under test (directive, "Manual-fixture acceptance gates"):

    frozen manual fixture -> strict Phase 3 loader -> CompiledDecisionWorld
    -> frozen base plan + genesis snapshot -> three candidate branches
    (exactly one intervention each) -> stock Concordia runs (scripted
    deterministic models, Phase 5 agency guard live) -> trace-based
    outcome evaluation (test-supplied cited predicates) -> primary-metric
    ranking -> RecommendationResult.

Proven here:
  - the frozen fixture FILE is byte-identical to its freeze record
    (sha256 against FIXTURES.sha256, asserted in-test);
  - the scripted recipient implements the fixture's deterministic_script
    mapping keyed on which candidate text the recipient observes;
  - per-candidate outcomes equal the fixture's expected_deterministic
    block exactly, including the terminal-status mapping (cutoff /
    success / failure decided by the trace-reading evaluator, never by
    the runner -- rule R3);
  - the recipient received its OWN turn and the reply event was emitted
    by that turn (the Game Master wrote nothing for the recipient: zero
    agency-guard interventions and the committed reply is attributed to
    the recipient's own committed action);
  - ranking_first == concise_relevant, best == ranking[0], the fixed
    limitation phrase and the 'deterministic' provenance label are
    present, and Phase 3 recommendation semantics validate;
  - THREE clean, byte-identical runs of the ENTIRE pipeline.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine counterfactual suite requires Python >= 3.12 (Concordia "
        "floor); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from cf_helpers import (FIXTURE_ONE_PATH, MAX_STEPS, RECIPIENT_CTA, SEED,
                        all_prompt_text, branch_signature, file_sha256,
                        fixture_model_factory, fixture_predicates,
                        fixture_status_rule, load_fixture_one,
                        recorded_fixture_hash)
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.decision.contracts import REQUIRED_LIMITATION_PHRASE
from sworldmodel.decision.validation import validate_semantics
from sworldmodel.outcomes import evaluate_branches, rank_branches

EXPECTED_WINNER = "concise_relevant"


def _full_pipeline():
    """One complete pipeline pass on a FRESH fixture load (fresh registry,
    fresh scripted models): loader -> manager -> evaluator -> ranking."""
    fx = load_fixture_one()
    capture: dict = {}
    run = run_candidates_detailed(
        fx.world, fx.candidates,
        model_factory=fixture_model_factory(fx, capture=capture),
        seed=SEED, max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry,
        model_config={"kind": "scripted_test_models"})
    evaluated = evaluate_branches(
        run.results, fixture_predicates(),
        evaluator_spec=fx.evaluator_spec,
        status_rule=fixture_status_rule, registry=fx.registry)
    recommendation = rank_branches(
        evaluated, fx.evaluator_spec, provenance_label="deterministic",
        registry=fx.registry)
    return fx, run, evaluated, recommendation, capture


def test_frozen_fixture_file_is_byte_identical_to_freeze_record():
    assert file_sha256(FIXTURE_ONE_PATH) \
        == recorded_fixture_hash("individual_reply.yaml"), (
        "the frozen fixture file individual_reply.yaml no longer matches "
        "its committed freeze record (FIXTURES.sha256)")


def test_fixture_one_deterministic_acceptance():
    fx, run, evaluated, recommendation, capture = _full_pipeline()
    expected = fx.expected_deterministic

    # Three candidate branches, all clean, all from the one frozen base.
    assert len(run.results) == 3
    for result in run.results:
        assert result.infrastructure_errors == ()
    assert run.base_plan_content_hash == run.base_plan.content_hash()

    # Per-candidate outcomes == the fixture's expected_deterministic
    # block, exactly, INCLUDING the terminal-status mapping.
    by_id = {result.candidate_id: result for result in evaluated}
    assert set(by_id) == set(expected.per_candidate)
    for candidate_id, expectations in expected.per_candidate.items():
        result = by_id[candidate_id]
        for name, expected_value in expectations.items():
            if name == "terminal_status":
                assert result.terminal_status == expected_value, (
                    f"{candidate_id}: terminal_status "
                    f"{result.terminal_status!r} != {expected_value!r}")
                continue
            metric = result.outcome_metrics[name]
            assert type(metric.value) is type(expected_value), (
                f"{candidate_id}.{name}: type mismatch")
            assert metric.value == expected_value, (
                f"{candidate_id}.{name}: {metric.value!r} != "
                f"{expected_value!r}")
            assert metric.computed_from, (
                f"{candidate_id}.{name} cites nothing")

    # Citations: positive readings cite the recipient's committed reply
    # event; the no-reply branch cites the recorded whole-trace bound.
    concise = by_id["concise_relevant"]
    reply_refs = concise.outcome_metrics["recipient_reply_sent"] \
        .computed_from
    assert reply_refs == ("event:ev_0002",)
    cited_event = {event.event_id: event.description
                   for event in concise.event_trace}["ev_0002"]
    assert "Morgan: Reply" in cited_event
    long_generic = by_id["long_generic"]
    assert long_generic.outcome_metrics["recipient_reply_sent"] \
        .computed_from == ("state:committed_event_count",)

    # Actor agency: the recipient received its OWN turn (exactly one
    # prompt, carrying its call to action AND the observed candidate
    # text), the reply follows the sender's committed message in commit
    # order, and the agency guard never had to intervene -- the Game
    # Master wrote nothing on the recipient's behalf.
    for candidate in fx.candidates:
        candidate_id = candidate.candidate_id
        recipient_prompts = capture[candidate_id]["recipient"].prompts
        assert len(recipient_prompts) == 1
        assert RECIPIENT_CTA in recipient_prompts[0]
        assert candidate.action in recipient_prompts[0], (
            f"{candidate_id}: the recipient acted without observing the "
            "candidate message")
        record = run.runner_records[candidate_id]
        assert record["guard_interventions"] == []
        trace = by_id[candidate_id].event_trace
        assert len(trace) == 3          # premise + sender + recipient
        assert candidate.action in trace[1].description
        # No cross-candidate text anywhere in this branch's prompts.
        other_actions = [other.action for other in fx.candidates
                         if other.candidate_id != candidate_id]
        prompt_text = all_prompt_text(capture[candidate_id]["sender"]) \
            + all_prompt_text(capture[candidate_id]["recipient"])
        for other_action in other_actions:
            assert other_action not in prompt_text

    # Ranking: the fixture's required winner, MEASURED -- never chosen.
    # The concise-vs-urgent tie on the primary metric (both replied)
    # resolves on the FIRST declared secondary metric, measured from the
    # trace: meeting_scheduled True vs False.  No tie-break was needed,
    # so the tie-break flag is ABSENT from validation_status.
    assert recommendation.best_candidate_id == expected.ranking_first \
        == EXPECTED_WINNER
    assert recommendation.ranking[0].candidate_id \
        == recommendation.best_candidate_id
    assert [entry.candidate_id for entry in recommendation.ranking] \
        == ["concise_relevant", "urgent_pressure", "long_generic"]
    assert by_id["concise_relevant"].outcome_metrics[
        "meeting_scheduled"].value is True
    assert by_id["urgent_pressure"].outcome_metrics[
        "meeting_scheduled"].value is False
    assert "tie_break_candidate_id_lexicographic" \
        not in recommendation.validation_status
    assert recommendation.validation_status[
        "ranked_by_declared_metrics_in_declared_order"] is True
    assert REQUIRED_LIMITATION_PHRASE in recommendation.run_limitations
    assert "Result provenance: deterministic." \
        in recommendation.run_limitations
    assert "compared descending in declared order" \
        in recommendation.run_limitations
    assert "polarity not inferred" in recommendation.run_limitations
    assert "candidate_id in ascending lexicographic order" \
        in recommendation.run_limitations
    assert "not needed in this ranking" in recommendation.run_limitations
    assert recommendation.metric_differences["recipient_reply_sent"] \
        == {"concise_relevant": 0.0, "urgent_pressure": 0.0,
            "long_generic": -1.0}
    assert set(recommendation.downside_outcomes) == set(by_id)

    # Phase 3 semantics of the finished recommendation, re-validated
    # explicitly against the evaluated branch results and declared spec.
    validate_semantics(recommendation, fx.registry,
                       branch_results=evaluated,
                       evaluator_spec=fx.evaluator_spec)


def test_three_clean_identical_runs_of_the_whole_pipeline():
    passes = [_full_pipeline() for _ in range(3)]

    for _fx, run, evaluated, _recommendation, _capture in passes:
        for result in list(run.results) + list(evaluated):
            assert result.infrastructure_errors == ()

    # Byte-identical evaluated results per candidate across all three
    # passes, and one byte-identical recommendation.
    reference_signatures = [branch_signature(result)
                            for result in passes[0][2]]
    reference_recommendation = passes[0][3].canonical_json()
    for _fx, _run, evaluated, recommendation, _capture in passes[1:]:
        assert [branch_signature(result) for result in evaluated] \
            == reference_signatures
        assert recommendation.canonical_json() == reference_recommendation

    # And the frozen base identity is the same in every pass.
    base_hashes = {run.base_plan_content_hash
                   for _fx, run, _evaluated, _rec, _capture in passes}
    assert len(base_hashes) == 1
