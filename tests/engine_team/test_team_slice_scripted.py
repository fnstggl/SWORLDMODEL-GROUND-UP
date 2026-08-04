"""Phase 10 slice, scripted leg: fixture 2's team decision end to end.

Pipeline under test (the compiler-adapter route surface is the entry
seam):

    frozen fixture 2 -> DecisionProblem ("which of Riley's approaches
    most increases the chance the declared decision rule is satisfied")
    -> prepare_decision_inputs (route: user-supplied candidates under
    the fixed code-owned rules) -> run_candidates_detailed (one frozen
    base, five scripted actors over eleven engine steps, scripted
    per-event observer visibility, hardened agency guard live) -> cited
    outcome evaluation -> sworldmodel.reporting.recommendation +
    sworldmodel.reporting.trace_report.

Proven here:
  - the frozen fixture file still matches its freeze record;
  - the scripted turn tables faithfully realize the frozen fixture's
    ``deterministic_script`` behavior flags (commit / veto per actor per
    candidate);
  - the fixture's MEASURED winner is reproduced through the route (the
    route's ``user_NNN`` candidates map back to the fixture candidates
    by verbatim action text), with every frozen per-candidate
    expectation exact -- including the terminal-status mapping -- and
    ``decided_by_metric`` naming the primary metric that separated the
    winner;
  - the recommendation report and causal trace report assemble, pass
    their strict validators, and round-trip through the frozen
    contracts' ``from_dict``/``content_hash`` gates;
  - the trace report carries the complete causal chain for a
    five-actor, two-round branch (plan hashes, seeds, twelve committed
    events in order, per-actor observation/attempt records at the fixed
    rotation steps, empty guard interventions, terminal world state,
    resolvable evaluator citations);
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
        "engine team-slice suite requires Python >= 3.12 (Concordia "
        "floor); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from team_helpers import (ACTOR_TURN_ANCHOR, COMMIT_MARKER,
                          EXPECTED_ATTEMPT_STEPS, FIXTURE_TWO_PATH,
                          RECOMMENDATION_ARTIFACT_PATH, TEAM_MAX_STEPS,
                          TEAM_TURNS, TRACE_ARTIFACT_PATH, file_sha256,
                          load_fixture_two, recorded_fixture_hash,
                          route_action_map, turn_flags)
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

EXPECTED_FIXTURE_WINNER = "private_ops_then_pilot"
EXPECTED_SEPARATING_METRIC = "decision_rule_satisfied"

#: committed example artifact identities (regression vectors; the files
#: under artifacts/ hold exactly the canonical JSON bytes)
EXPECTED_RECOMMENDATION_ARTIFACT_SHA256 = (
    "6770b1053ef5b516fb561a0d596a2924ad6d821e35e9de81741ccf9adfc7e474")
EXPECTED_TRACE_ARTIFACT_SHA256 = (
    "dd2df61b33a7eb8e0df5526a7c8572ef8e1214a7788471b53c47ac8a25ff76c4")


def test_frozen_fixture_file_still_matches_freeze_record():
    assert file_sha256(FIXTURE_TWO_PATH) \
        == recorded_fixture_hash("team_commitment.yaml"), (
        "the frozen fixture file team_commitment.yaml no longer matches "
        "its committed freeze record (FIXTURES.sha256)")


def test_turn_tables_realize_the_frozen_deterministic_script():
    """The scripted turn tables are the harness realization of the
    fixture's ``deterministic_script`` scaffolding: for every candidate
    and every scripted actor, the table's measured behavior flags equal
    the frozen script's declared ``commit`` / ``veto_exercised`` flags,
    and the proposal owner's first turn is always the branch's inserted
    candidate action verbatim (the ``None`` echo slot)."""
    fx = load_fixture_two()
    script = fx.deterministic_script
    assert sorted(TEAM_TURNS) \
        == sorted(candidate.candidate_id for candidate in fx.candidates)
    for fixture_id, table in TEAM_TURNS.items():
        flags = turn_flags(fixture_id)
        assert table["proposal_owner"][0] is None
        for actor_id, leaf in script.items():
            expected_commit = bool(leaf[fixture_id]["commit"])
            assert flags[actor_id]["commit"] is expected_commit, (
                f"{fixture_id}.{actor_id}: turn table commit flag "
                f"{flags[actor_id]['commit']} != frozen script "
                f"{expected_commit}")
            expected_veto = bool(
                leaf[fixture_id].get("veto_exercised", False))
            assert flags[actor_id]["veto"] is expected_veto, (
                f"{fixture_id}.{actor_id}: turn table veto flag "
                f"{flags[actor_id]['veto']} != frozen script "
                f"{expected_veto}")
        # Nobody outside the frozen script's actors commits or vetoes.
        for actor_id, actor_flags in flags.items():
            if actor_id not in script:
                assert actor_flags == {"commit": False, "veto": False}


def test_route_reproduces_the_fixture_measured_winner(team_slice):
    outcome = team_slice
    mapping = route_action_map(outcome.fx, outcome.inputs)
    expected = outcome.fx.expected_deterministic

    # The route produced exactly the fixture's three actions as
    # user-supplied candidates in declaration order.
    assert [c.candidate_id for c in outcome.inputs.candidates] \
        == ["user_001", "user_002", "user_003"]
    for candidate in outcome.inputs.candidates:
        assert candidate.provenance.source == "user_supplied"
        assert candidate.decision_owner == "proposal_owner"

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
            assert metric.computed_from, \
                f"{fixture_id}.{name} cites nothing"

    # The MEASURED winner is the fixture's required winner, decided by
    # the PRIMARY declared metric (the decision rule itself separated
    # the winner from the runner-up).
    winner_route_id = outcome.report["winner"]
    assert mapping[winner_route_id] == EXPECTED_FIXTURE_WINNER \
        == expected.ranking_first
    assert outcome.report["decided_by_metric"] \
        == EXPECTED_SEPARATING_METRIC
    assert outcome.recommendation.validation_status["decided_by_metric"] \
        == EXPECTED_SEPARATING_METRIC
    ranked = [entry.candidate_id
              for entry in outcome.recommendation.ranking]
    top, runner_up = ranked[0], ranked[1]
    assert by_id[top].outcome_metrics[
        "decision_rule_satisfied"].value is True
    assert by_id[runner_up].outcome_metrics[
        "decision_rule_satisfied"].value is False
    assert "tie_break_candidate_id_lexicographic" \
        not in outcome.recommendation.validation_status
    assert REQUIRED_LIMITATION_PHRASE \
        in outcome.recommendation.run_limitations
    assert "Result provenance: deterministic." \
        in outcome.recommendation.run_limitations


def test_recommendation_report_validates_and_round_trips(team_slice):
    report = team_slice.report
    validate_recommendation_report(report)

    # Frozen-contract round-trips: every embedded contract re-parses
    # through its strict from_dict and reproduces its recorded hash.
    problem = DecisionProblem.from_dict(report["problem"])
    assert problem.content_hash() == report["problem_content_hash"]
    assert problem.content_hash() == team_slice.problem.content_hash()
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
        == team_slice.run.base_plan_content_hash
    assert report["base_snapshot_id"] \
        == team_slice.run.base_snapshot.snapshot_id
    for entry in report["branch_evaluations"]:
        assert entry["branch_seed"] \
            == team_slice.run.branch_seeds[entry["candidate_id"]]

    # A serialized copy re-validates identically (reload path).
    reloaded = json.loads(report_canonical_json(report))
    validate_recommendation_report(reloaded)
    assert report_content_hash(reloaded) == report_content_hash(report)


def test_trace_report_carries_the_complete_causal_chain(team_slice):
    outcome = team_slice
    trace = outcome.trace
    validate_trace_report(trace)

    run = outcome.run
    assert trace["base_plan_content_hash"] == run.base_plan_content_hash
    assert trace["base_plan_id"] == run.base_plan.plan_id
    assert trace["base_snapshot_id"] == run.base_snapshot.snapshot_id
    assert trace["base_seed"] \
        == run.base_snapshot.sidecar.rng["base_seed"]

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

        # Committed events, in commit order, verbatim from the
        # contract: the neutral premise plus all eleven resolved turns.
        assert branch["committed_events"] \
            == [event.to_dict() for event in result.event_trace]
        assert branch["committed_events"] == raw["event_trace"]
        assert len(branch["committed_events"]) == TEAM_MAX_STEPS + 1
        assert branch["steps_completed"] == raw["steps_completed"] \
            == TEAM_MAX_STEPS

        # Guard interventions verbatim (none needed in the clean slice).
        assert branch["guard_interventions"] \
            == raw["guard_interventions"] == []

        # Per-actor observation and attempt records: every actor has
        # its recorded observation stream and acted at exactly its
        # fixed-rotation steps; each attempt is inside its committed
        # anchored row.
        records = branch["actor_records"]
        assert sorted(records) == sorted(EXPECTED_ATTEMPT_STEPS)
        rows = [event["description"]
                for event in branch["committed_events"]]
        for actor_id, record in records.items():
            assert record["observations"] \
                == raw["actor_memories"][actor_id]
            steps = [attempt["step"] for attempt in record["attempts"]]
            assert steps == EXPECTED_ATTEMPT_STEPS[actor_id]
            for attempt in record["attempts"]:
                row = rows[attempt["step"]]  # premise shifts rows by 1
                assert ACTOR_TURN_ANCHOR in row
                assert attempt["attempt"] in row
                assert f"{record['name']}: " in row
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

    # The winning branch's commitment citations point at anchored
    # actor-attributed rows carrying the commitment marker.
    winner_branch = {branch["candidate_id"]: branch
                     for branch in trace["branches"]}[
                         outcome.report["winner"]]
    cited = winner_branch["evaluation_citations"][
        "explicit_support_commitments"]
    descriptions = {event["event_id"]: event["description"]
                    for event in winner_branch["committed_events"]}
    assert len(cited["computed_from"]) == 4
    for reference in cited["computed_from"]:
        row = descriptions[reference.partition(":")[2]]
        assert ACTOR_TURN_ANCHOR in row
        assert COMMIT_MARKER in row


def test_report_content_hashes_stable_across_two_runs(
        team_slice, team_slice_second):
    assert report_content_hash(team_slice_second.report) \
        == report_content_hash(team_slice.report)
    assert report_canonical_json(team_slice_second.report) \
        == report_canonical_json(team_slice.report)
    assert trace_report_content_hash(team_slice_second.trace) \
        == trace_report_content_hash(team_slice.trace)
    assert trace_report_canonical_json(team_slice_second.trace) \
        == trace_report_canonical_json(team_slice.trace)


def test_committed_example_artifacts_regenerate_byte_identically(
        team_slice):
    """The committed artifact pair is a hash-asserted regression vector:
    the slice must keep producing exactly these bytes."""
    regenerated_report = report_canonical_json(team_slice.report)
    regenerated_trace = trace_report_canonical_json(team_slice.trace)

    committed_report = RECOMMENDATION_ARTIFACT_PATH.read_text(
        encoding="utf-8")
    committed_trace = TRACE_ARTIFACT_PATH.read_text(encoding="utf-8")
    assert committed_report == regenerated_report
    assert committed_trace == regenerated_trace

    assert file_sha256(RECOMMENDATION_ARTIFACT_PATH) \
        == EXPECTED_RECOMMENDATION_ARTIFACT_SHA256 \
        == report_content_hash(team_slice.report)
    assert file_sha256(TRACE_ARTIFACT_PATH) \
        == EXPECTED_TRACE_ARTIFACT_SHA256 \
        == trace_report_content_hash(team_slice.trace)

    # The committed artifacts also re-validate as loaded documents.
    validate_recommendation_report(json.loads(committed_report))
    validate_trace_report(json.loads(committed_trace))
