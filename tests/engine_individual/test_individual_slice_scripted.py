"""Phase 9 slice, scripted leg: fixture 1's message decision end to end.

Pipeline under test (the compiler-adapter route surface is the entry
seam):

    frozen fixture 1 -> DecisionProblem ("which of these messages most
    increases the chance of a reply / second conversation") ->
    prepare_decision_inputs (route: user-supplied candidates under the
    fixed code-owned rules) -> run_candidates_detailed (one frozen base,
    scripted deterministic models, hardened agency guard live) -> cited
    outcome evaluation -> sworldmodel.reporting.recommendation +
    sworldmodel.reporting.trace_report.

Proven here:
  - the frozen fixture file still matches its freeze record;
  - the fixture's MEASURED winner is reproduced through the route (the
    route's ``user_NNN`` candidates map back to the fixture candidates
    by verbatim action text), with ``decided_by_metric`` naming the
    separating declared metric (``meeting_scheduled``: the primary-metric
    tie between the winner and the pressure candidate splits on the
    first declared secondary, measured from the trace);
  - the recommendation report and causal trace report assemble, pass
    their strict validators, and round-trip through the frozen
    contracts' ``from_dict``/``content_hash`` gates;
  - the trace report carries the complete causal chain (plan hashes,
    seeds, committed events in order, guard interventions, per-actor
    observation/attempt records, terminal world state, evaluator
    citations that resolve against its own rows);
  - both report content hashes are byte-stable across two independent
    full passes (determinism);
  - the committed example artifact pair regenerates byte-identically
    (hash-asserted regression vectors).
"""

from __future__ import annotations

import json
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

from individual_helpers import (FIXTURE_ONE_PATH,
                                RECOMMENDATION_ARTIFACT_PATH,
                                TRACE_ARTIFACT_PATH, ACTOR_TURN_ANCHOR,
                                file_sha256, recorded_fixture_hash,
                                route_action_map, run_scripted_slice)
from sworldmodel.counterfactuals import derive_branch_seed
from sworldmodel.decision.contracts import (DecisionProblem,
                                            InterventionCandidate,
                                            RecommendationResult,
                                            REQUIRED_LIMITATION_PHRASE)
from sworldmodel.reporting import (report_canonical_json,
                                   report_content_hash,
                                   trace_report_canonical_json,
                                   trace_report_content_hash,
                                   validate_recommendation_report,
                                   validate_trace_report)

EXPECTED_FIXTURE_WINNER = "concise_relevant"
EXPECTED_SEPARATING_METRIC = "meeting_scheduled"

#: committed example artifact identities (regression vectors; the files
#: under artifacts/ hold exactly the canonical JSON bytes)
#:
#: DELIBERATE REGENERATION 2026-08-04 (under-the-hood fix batch, defect
#: D2): the recommendation report now discloses per-branch intervention
#: delivery -- one clause per candidate in ``downside_outcomes``, two
#: flags in ``validation_status``, one sentence in ``run_limitations``.
#: The scripted slice's own measurements are unchanged (every branch's
#: sender echoes its candidate, so all three deliver); only the
#: disclosure text is new, so the recommendation artifact was rebuilt
#: from this same slice and its sha256 re-recorded.  The TRACE artifact
#: does not go through ranking and is BYTE-UNCHANGED -- its recorded
#: hash below is the pre-fix one, which is the point: the simulation
#: itself did not move.
EXPECTED_RECOMMENDATION_ARTIFACT_SHA256 = (
    "94e49e873a6636434b83076019f01138874a56bab0031da8f08ba63bbbe33d17")
EXPECTED_TRACE_ARTIFACT_SHA256 = (
    "507eff26f8f4dcaf6dd1fbf24ae1ccde10d0df2a5a65f3df8c2c7c218c8557de")


@pytest.fixture(scope="module")
def slice_outcome():
    """One shared scripted slice pass; tests treat it as read-only."""
    return run_scripted_slice()


def test_frozen_fixture_file_still_matches_freeze_record():
    assert file_sha256(FIXTURE_ONE_PATH) \
        == recorded_fixture_hash("individual_reply.yaml"), (
        "the frozen fixture file individual_reply.yaml no longer matches "
        "its committed freeze record (FIXTURES.sha256)")


def test_route_reproduces_the_fixture_measured_winner(slice_outcome):
    outcome = slice_outcome
    mapping = route_action_map(outcome.fx, outcome.inputs)
    expected = outcome.fx.expected_deterministic

    # The route produced exactly the fixture's three actions as
    # user-supplied candidates in declaration order.
    assert [c.candidate_id for c in outcome.inputs.candidates] \
        == ["user_001", "user_002", "user_003"]
    for candidate in outcome.inputs.candidates:
        assert candidate.provenance.source == "user_supplied"
        assert candidate.decision_owner == "sender"

    # Per-candidate measured outcomes equal the fixture's frozen
    # expectations exactly, INCLUDING the terminal-status mapping.
    by_id = {result.candidate_id: result for result in outcome.evaluated}
    for route_id, fixture_id in mapping.items():
        result = by_id[route_id]
        assert result.infrastructure_errors == ()
        expectations = expected.per_candidate[fixture_id]
        for name, expected_value in expectations.items():
            if name == "terminal_status":
                assert result.terminal_status == expected_value, (
                    f"{fixture_id}: terminal_status "
                    f"{result.terminal_status!r} != {expected_value!r}")
                continue
            metric = result.outcome_metrics[name]
            assert metric.value == expected_value \
                and type(metric.value) is type(expected_value), (
                    f"{fixture_id}.{name}: {metric.value!r} != "
                    f"{expected_value!r}")
            assert metric.computed_from, f"{fixture_id}.{name} cites nothing"

    # The MEASURED winner is the fixture's required winner, and the
    # separating declared metric is named for the reader.
    winner_route_id = outcome.report["winner"]
    assert mapping[winner_route_id] == EXPECTED_FIXTURE_WINNER \
        == expected.ranking_first
    assert outcome.report["decided_by_metric"] \
        == EXPECTED_SEPARATING_METRIC
    assert outcome.recommendation.validation_status["decided_by_metric"] \
        == EXPECTED_SEPARATING_METRIC
    # Non-vacuity of the separation: primary tied between the top two,
    # split on the first declared secondary, measured from the trace.
    ranked = [entry.candidate_id
              for entry in outcome.recommendation.ranking]
    top, runner_up = ranked[0], ranked[1]
    assert by_id[top].outcome_metrics["recipient_reply_sent"].value \
        is by_id[runner_up].outcome_metrics["recipient_reply_sent"].value \
        is True
    assert by_id[top].outcome_metrics["meeting_scheduled"].value is True
    assert by_id[runner_up].outcome_metrics["meeting_scheduled"].value \
        is False
    assert "tie_break_candidate_id_lexicographic" \
        not in outcome.recommendation.validation_status
    assert REQUIRED_LIMITATION_PHRASE \
        in outcome.recommendation.run_limitations
    assert "Result provenance: deterministic." \
        in outcome.recommendation.run_limitations


def test_recommendation_report_validates_and_round_trips(slice_outcome):
    report = slice_outcome.report
    validate_recommendation_report(report)

    # Frozen-contract round-trips: every embedded contract re-parses
    # through its strict from_dict and reproduces its recorded hash.
    problem = DecisionProblem.from_dict(report["problem"])
    assert problem.content_hash() == report["problem_content_hash"]
    assert problem.content_hash() == slice_outcome.problem.content_hash()
    recommendation = RecommendationResult.from_dict(
        report["recommendation"])
    assert recommendation.content_hash() \
        == report["recommendation_content_hash"]
    for raw in report["candidates"]:
        candidate = InterventionCandidate.from_dict(raw)
        assert candidate.content_hash() \
            == report["candidate_content_hashes"][candidate.candidate_id]

    # Run identity is bound in: base plan + genesis snapshot + seeds.
    assert report["base_plan_content_hash"] \
        == slice_outcome.run.base_plan_content_hash
    assert report["base_snapshot_id"] \
        == slice_outcome.run.base_snapshot.snapshot_id
    for entry in report["branch_evaluations"]:
        assert entry["branch_seed"] \
            == slice_outcome.run.branch_seeds[entry["candidate_id"]]

    # A serialized copy re-validates identically (reload path).
    reloaded = json.loads(report_canonical_json(report))
    validate_recommendation_report(reloaded)
    assert report_content_hash(reloaded) == report_content_hash(report)


def test_trace_report_carries_the_complete_causal_chain(slice_outcome):
    outcome = slice_outcome
    trace = outcome.trace
    validate_trace_report(trace)

    run = outcome.run
    assert trace["base_plan_content_hash"] == run.base_plan_content_hash
    assert trace["base_plan_id"] == run.base_plan.plan_id
    assert trace["base_snapshot_id"] == run.base_snapshot.snapshot_id
    assert trace["base_seed"] == run.base_snapshot.sidecar.rng["base_seed"]

    by_id = {result.candidate_id: result for result in outcome.evaluated}
    for branch in trace["branches"]:
        candidate_id = branch["candidate_id"]
        result = by_id[candidate_id]
        raw = run.runner_records[candidate_id]
        assert branch["runner_record_available"] is True

        # Initialization identity: branch plan hash + code-owned seed.
        plan = run.branch_plans[candidate_id]
        assert branch["branch_plan_content_hash"] == plan.content_hash()
        assert branch["branch_seed"] == derive_branch_seed(
            trace["base_seed"], candidate_id)
        assert branch["branch_id"] == run.branch_ids[candidate_id]

        # Committed events, in commit order, verbatim from the contract.
        assert branch["committed_events"] \
            == [event.to_dict() for event in result.event_trace]
        assert branch["committed_events"] == raw["event_trace"]
        assert len(branch["committed_events"]) == 3  # premise + 2 turns
        assert branch["steps_completed"] == raw["steps_completed"] == 2

        # Guard interventions verbatim (none needed in the clean slice).
        assert branch["guard_interventions"] \
            == raw["guard_interventions"] == []

        # Per-actor observation and attempt records: every actor has its
        # recorded observation stream and exactly one acted attempt.
        records = branch["actor_records"]
        assert sorted(records) == ["recipient", "sender"]
        for actor_id, record in records.items():
            assert record["observations"] \
                == raw["actor_memories"][actor_id]
            assert len(record["attempts"]) == 1
        assert records["sender"]["name"] == "Alex"
        assert records["recipient"]["name"] == "Morgan"
        assert records["sender"]["attempts"][0]["step"] == 1
        assert records["recipient"]["attempts"][0]["step"] == 2
        # The recipient's attempt is what its committed turn resolves to.
        recipient_attempt = records["recipient"]["attempts"][0]["attempt"]
        assert recipient_attempt in branch["committed_events"][2][
            "description"]
        assert branch["unattributed_attempts"] == []

        # Terminal world state verbatim; citations resolve to this same
        # report's rows.
        assert branch["terminal_world_state"] \
            == result.terminal_world_state
        event_ids = {event["event_id"]
                     for event in branch["committed_events"]}
        for name, metric in branch["evaluation_citations"].items():
            assert metric["computed_from"], f"{candidate_id}.{name}"
            for reference in metric["computed_from"]:
                kind, _, target = reference.partition(":")
                if kind == "event":
                    assert target in event_ids
                else:
                    assert kind == "state"
                    assert target in branch["terminal_world_state"]

    # The winning branch's success-metric citation points at the
    # recipient's OWN resolved turn (actor-attributed row).
    winner_branch = {branch["candidate_id"]: branch
                     for branch in trace["branches"]}[
                         outcome.report["winner"]]
    cited = winner_branch["evaluation_citations"]["recipient_reply_sent"]
    descriptions = {event["event_id"]: event["description"]
                    for event in winner_branch["committed_events"]}
    for reference in cited["computed_from"]:
        row = descriptions[reference.partition(":")[2]]
        assert ACTOR_TURN_ANCHOR in row
        assert "Morgan: Reply" in row


def test_report_content_hashes_stable_across_two_runs(slice_outcome):
    second = run_scripted_slice()
    assert report_content_hash(second.report) \
        == report_content_hash(slice_outcome.report)
    assert report_canonical_json(second.report) \
        == report_canonical_json(slice_outcome.report)
    assert trace_report_content_hash(second.trace) \
        == trace_report_content_hash(slice_outcome.trace)
    assert trace_report_canonical_json(second.trace) \
        == trace_report_canonical_json(slice_outcome.trace)


def test_committed_example_artifacts_regenerate_byte_identically(
        slice_outcome):
    """The committed artifact pair is a hash-asserted regression vector:
    the slice must keep producing exactly these bytes."""
    regenerated_report = report_canonical_json(slice_outcome.report)
    regenerated_trace = trace_report_canonical_json(slice_outcome.trace)

    committed_report = RECOMMENDATION_ARTIFACT_PATH.read_text(
        encoding="utf-8")
    committed_trace = TRACE_ARTIFACT_PATH.read_text(encoding="utf-8")
    assert committed_report == regenerated_report
    assert committed_trace == regenerated_trace

    assert file_sha256(RECOMMENDATION_ARTIFACT_PATH) \
        == EXPECTED_RECOMMENDATION_ARTIFACT_SHA256 \
        == report_content_hash(slice_outcome.report)
    assert file_sha256(TRACE_ARTIFACT_PATH) \
        == EXPECTED_TRACE_ARTIFACT_SHA256 \
        == trace_report_content_hash(slice_outcome.trace)

    # The committed artifacts also re-validate as loaded documents.
    validate_recommendation_report(json.loads(committed_report))
    validate_trace_report(json.loads(committed_trace))
