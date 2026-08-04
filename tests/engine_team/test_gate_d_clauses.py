"""Gate D proof battery: one test per acceptance-gate clause.

Each test is named for the clause of acceptance gate D ("Team
simulation") it proves, on fixture 2's five-person team-commitment
decision:

  - at least five actors (active in one simulation, counted from the
    trace)
        -> test_at_least_five_actors_act_across_multiple_rounds
  - private and shared interactions
        -> test_private_information_stays_pairwise_private (private)
        -> test_meeting_round_delivers_same_events_to_every_attendee
           (shared)
        -> test_private_followups_visible_only_to_participants
           (private follow-up conversations after the meeting)
  - authority differences
        -> test_authority_gates_the_outcome_only_from_the_authority_holder
  - actor-owned votes or commitments
        -> test_counted_commitments_cite_actor_authored_turns
        -> test_actor_cannot_cast_another_actors_vote
  - persistent memory / multiple rounds
        -> test_actor_memory_persists_across_rounds
        -> (round structure also asserted in the five-actor test)
  - no omniscient actor context
        -> test_no_actor_context_is_omniscient
  - no Game-Master-forced coalition (and the GM cannot cast votes or
    make commitments on behalf of actors)
        -> test_gm_narration_cannot_cast_votes_or_force_a_coalition
        -> (the guard-side half is the vote-casting test above)
  - explicit final outcome from actor/world events
        -> test_final_outcome_is_explicit_and_never_fabricated
  - repeated execution (slice-level determinism)
        -> test_repeated_full_slice_executions_are_byte_identical

Scenario worlds that need extra structure (a narration row textually
claiming a tally and a coalition) are TEST-OWNED world variants built
strictly through the frozen ``CompiledDecisionWorld`` contract gate --
the frozen fixture file itself is never modified.  Authority, meetings,
and private follow-ups are expressed purely through existing
configuration: scripted turn tables, scripted per-event observer
visibility answers, and attribution-anchored evaluator predicates keyed
to the fixture's declared authority structure (see team_helpers).
"""

from __future__ import annotations

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

from team_helpers import (ACTOR_TURN_ANCHOR, AUTHORITY_NAME,
                          COMMIT_MARKER, FINAL_MARKER,
                          FOLLOWUP_ONE_CANARY, FOLLOWUP_TWO_CANARY,
                          MEMORY_PHRASE, PILOT_ACCEPT_UTTERANCE,
                          PRIVATE_OPS_CANARY, PROBE_TIMING,
                          RECORD_FAILURE_TURN, RECORD_SUCCESS_TURN,
                          ROUND_LENGTH, TEAM_TURNS, VETO_UTTERANCE,
                          actor_names, actor_order,
                          branch_results_by_fixture_id, load_fixture_two,
                          make_candidate, private_context_by_actor,
                          gm_prompts_of, prompts_of,
                          route_ids_by_fixture_id, run_probe,
                          world_variant)
from sworldmodel.backends.concordia_local.guard import AVAILABILITY_MARKER
from sworldmodel.decision.contracts import TERMINAL_STATUSES
from sworldmodel.reporting import (build_trace_report,
                                   report_canonical_json,
                                   trace_report_canonical_json,
                                   validate_trace_report)

#: the identical utterances of the authority probe (spoken verbatim by
#: BOTH the authority holder and a non-authority actor, in different
#: variants; only the authority holder's copy may gate the outcome)
PROBE_VETO_TURN = (VETO_UTTERANCE
                   + " against the unscoped migration request.")
PROBE_COMMIT_TURN = ("State an explicit commitment to the migration "
                     "plan as presented.")
PROBE_ACTION = ("Convene the team and ask for explicit commitments on "
                "the migration plan as presented.")

#: test-owned narration text: it textually contains attribution-shaped
#: vote/commitment claims, the pilot-acceptance utterance, the
#: outcome-recording phrase, and an announced coalition -- everything
#: the predicates look for EXCEPT the resolved-actor-turn anchor
NARRATED_TALLY_CLAIM = (
    "Word circulates that the matter is already settled: "
    '"Sam: Accept the capped pilot." and "Dana: State an explicit '
    'commitment to the pilot." and "Priya: State an explicit commitment '
    'to the pilot." and "Chris: State an explicit commitment to the '
    'pilot." were supposedly heard, a majority coalition has formed, '
    "and the final decision of the team under the declared rule: "
    "adopted.")


def _memories(outcome, route_id: str) -> dict:
    return outcome.run.runner_records[route_id]["actor_memories"]


def _trace_branch(outcome, route_id: str) -> dict:
    return {branch["candidate_id"]: branch
            for branch in outcome.trace["branches"]}[route_id]


def _committed_descriptions(result) -> list:
    return [event.description for event in result.event_trace]


# ---------------------------------------------------------------------------
# at least five actors; multiple rounds
# ---------------------------------------------------------------------------

def test_at_least_five_actors_act_across_multiple_rounds(team_slice):
    """Five distinct actors ACT in every branch -- counted from the
    recorded trace (attempts and committed attributed turns), never from
    the configuration -- and every actor acts in at least two distinct
    rotation rounds."""
    outcome = team_slice
    names = actor_names(outcome.fx)
    for branch in outcome.trace["branches"]:
        records = branch["actor_records"]

        # Count ACTING actors from the trace's attempt records.
        acting = {actor_id for actor_id, record in records.items()
                  if record["attempts"]}
        assert len(acting) >= 5
        assert acting == set(names)

        # Count attributed resolved turns from the committed rows.
        rows = [event["description"]
                for event in branch["committed_events"]
                if ACTOR_TURN_ANCHOR in event["description"]]
        turn_authors = {name for name in names.values()
                        if any(f"{name}: " in row for row in rows)}
        assert len(turn_authors) >= 5

        # Multiple rounds: every actor acted in >= 2 distinct rotation
        # rounds of the fixed acting order.
        for actor_id, record in records.items():
            rounds = {(attempt["step"] - 1) // ROUND_LENGTH
                      for attempt in record["attempts"]}
            assert len(rounds) >= 2, (actor_id, rounds)


# ---------------------------------------------------------------------------
# private information (pairwise) and omniscience bound
# ---------------------------------------------------------------------------

def test_private_information_stays_pairwise_private(team_slice):
    """All five actors hold distinct private contexts; for EVERY ordered
    actor pair, one actor's private context never reaches another
    actor's prompts, recorded memory, or trace observation records, and
    never enters the committed event stream -- in every branch."""
    outcome = team_slice
    private = private_context_by_actor(outcome.fx)
    order = actor_order(outcome.fx)
    assert len(set(private.values())) == 5  # five DISTINCT canaries

    for candidate in outcome.inputs.candidates:
        route_id = candidate.candidate_id
        capture = outcome.capture[route_id]
        memories = _memories(outcome, route_id)
        branch = _trace_branch(outcome, route_id)
        prompt_text = {actor_id: prompts_of(capture, actor_id)
                       for actor_id in order}

        for actor_id in order:
            # Non-vacuity: each actor sees its OWN private context.
            assert private[actor_id] in prompt_text[actor_id]
            for other_id in order:
                if other_id == actor_id:
                    continue
                # ...and never any other actor's, anywhere.
                assert private[other_id] not in prompt_text[actor_id], (
                    route_id, actor_id, other_id)
                assert not any(private[other_id] in row
                               for row in memories[actor_id]), (
                    route_id, actor_id, other_id)
                observations = branch["actor_records"][actor_id][
                    "observations"]
                assert not any(private[other_id] in row
                               for row in observations), (
                    route_id, actor_id, other_id)

        for event in outcome.run.runner_records[route_id][
                "committed_events"]:
            for actor_id in order:
                assert private[actor_id] not in event


def test_no_actor_context_is_omniscient(team_slice):
    """No single actor's prompts contain the union of the private
    canaries: the explicit per-actor containment bound is EXACTLY ONE
    private context (its own).  Private-conversation canaries reach only
    their participants, and the game master's model prompts carry no
    private context at all."""
    outcome = team_slice
    private = private_context_by_actor(outcome.fx)
    order = actor_order(outcome.fx)
    route_ids = route_ids_by_fixture_id(outcome)

    for candidate in outcome.inputs.candidates:
        capture = outcome.capture[candidate.candidate_id]
        for actor_id in order:
            text = prompts_of(capture, actor_id)
            contained = [other for other in order
                         if private[other] in text]
            assert contained == [actor_id], (
                candidate.candidate_id, actor_id, contained)
            assert not all(private[other] in text for other in order)
        # The GM model's prompts (the observer questions) never carry
        # any actor's private context.
        gm_text = gm_prompts_of(capture)
        assert not any(private[actor_id] in gm_text
                       for actor_id in order)

    # Conversation canaries: participants only, per branch.
    winner_capture = outcome.capture[route_ids["private_ops_then_pilot"]]
    announce_capture = outcome.capture[route_ids["announce_full_plan"]]
    winner_memories = _memories(outcome,
                                route_ids["private_ops_then_pilot"])
    announce_memories = _memories(outcome,
                                  route_ids["announce_full_plan"])

    def seen(capture, memories, actor_id, canary) -> bool:
        return (canary in prompts_of(capture, actor_id)
                or any(canary in row for row in memories[actor_id]))

    for actor_id in order:
        expected = actor_id in ("proposal_owner", "operations_lead")
        assert seen(winner_capture, winner_memories, actor_id,
                    PRIVATE_OPS_CANARY) is expected, actor_id
        assert seen(announce_capture, announce_memories, actor_id,
                    FOLLOWUP_ONE_CANARY) is expected, actor_id
        expected_two = actor_id in ("budget_owner", "operations_lead")
        assert seen(announce_capture, announce_memories, actor_id,
                    FOLLOWUP_TWO_CANARY) is expected_two, actor_id


# ---------------------------------------------------------------------------
# a meeting: shared multi-actor interaction
# ---------------------------------------------------------------------------

def test_meeting_round_delivers_same_events_to_every_attendee(team_slice):
    """A meeting is a shared multi-actor round: every attendee observes
    the SAME committed events.  Proven on both meetings of the slice --
    the announce branch's round-1 team meeting (steps 1-5) and the
    winner branch's round-2 pilot meeting (steps 6-10): for each meeting
    turn, all five actors hold an identical delivered observation row,
    and that delivered text sits verbatim inside the single committed
    world-record row."""
    outcome = team_slice
    order = actor_order(outcome.fx)
    route_ids = route_ids_by_fixture_id(outcome)
    results = branch_results_by_fixture_id(outcome)

    meetings = {
        "announce_full_plan": [
            outcome.fx.candidates[0].action,          # step 1 (echoed)
            TEAM_TURNS["announce_full_plan"]["operations_lead"][0],
            TEAM_TURNS["announce_full_plan"]["budget_owner"][0],
            TEAM_TURNS["announce_full_plan"]["product_lead"][0],
            TEAM_TURNS["announce_full_plan"]["neutral_member"][0],
        ],
        "private_ops_then_pilot": [
            TEAM_TURNS["private_ops_then_pilot"]["proposal_owner"][1],
            TEAM_TURNS["private_ops_then_pilot"]["operations_lead"][1],
            TEAM_TURNS["private_ops_then_pilot"]["budget_owner"][1],
            TEAM_TURNS["private_ops_then_pilot"]["product_lead"][1],
            TEAM_TURNS["private_ops_then_pilot"]["neutral_member"][1],
        ],
    }
    for fixture_id, turns in meetings.items():
        memories = _memories(outcome, route_ids[fixture_id])
        committed = _committed_descriptions(results[fixture_id])
        for turn in turns:
            needle = turn.strip()
            delivered = set()
            for actor_id in order:
                rows = [row for row in memories[actor_id]
                        if ACTOR_TURN_ANCHOR in row and needle in row]
                assert len(rows) == 1, (fixture_id, actor_id, needle)
                delivered.add(rows[0])
            # The SAME event text reached every attendee...
            assert len(delivered) == 1, (fixture_id, needle)
            # ...and it is the committed world-record row's content.
            committed_rows = [row for row in committed if needle in row]
            assert len(committed_rows) == 1, (fixture_id, needle)
            delivered_text = delivered.pop()
            assert delivered_text.removeprefix(
                "[observation] ").rstrip() in committed_rows[0]


# ---------------------------------------------------------------------------
# private follow-up conversations
# ---------------------------------------------------------------------------

def test_private_followups_visible_only_to_participants(team_slice):
    """Post-meeting private conversations are visible ONLY to their
    participants.  The announce branch holds two follow-ups after its
    round-1 meeting -- Riley<->Sam (steps 6-7) and Dana<->Sam (step 8)
    -- with distinct canaries; the winner branch holds the pre-meeting
    Riley<->Sam workload conversation (steps 1-2).  Pairwise:
    participants receive each private event; every non-participant's
    prompts, recorded memory, and trace observations stay clean --
    including the proposal owner for the Dana<->Sam consultation.  The
    game master's committed world record retains every private event."""
    outcome = team_slice
    order = actor_order(outcome.fx)
    route_ids = route_ids_by_fixture_id(outcome)
    results = branch_results_by_fixture_id(outcome)

    announce_turns = TEAM_TURNS["announce_full_plan"]
    winner_turns = TEAM_TURNS["private_ops_then_pilot"]
    conversations = {
        "announce_full_plan": [
            (announce_turns["proposal_owner"][1],
             ("proposal_owner", "operations_lead")),
            (announce_turns["operations_lead"][1],
             ("proposal_owner", "operations_lead")),
            (announce_turns["budget_owner"][1],
             ("budget_owner", "operations_lead")),
        ],
        "private_ops_then_pilot": [
            (outcome.fx.candidates[1].action,
             ("proposal_owner", "operations_lead")),
            (winner_turns["operations_lead"][0],
             ("proposal_owner", "operations_lead")),
        ],
    }
    for fixture_id, private_events in conversations.items():
        route_id = route_ids[fixture_id]
        capture = outcome.capture[route_id]
        memories = _memories(outcome, route_id)
        branch = _trace_branch(outcome, route_id)
        committed = _committed_descriptions(results[fixture_id])
        for turn, participants in private_events:
            needle = turn.strip()
            # The committed world record retains the private event
            # (non-vacuity: privacy scopes observation, not existence).
            assert sum(1 for row in committed
                       if ACTOR_TURN_ANCHOR in row and needle in row) \
                == 1, (fixture_id, needle)
            for actor_id in order:
                delivered = [row for row in memories[actor_id]
                             if ACTOR_TURN_ANCHOR in row
                             and needle in row]
                observations = branch["actor_records"][actor_id][
                    "observations"]
                if actor_id in participants:
                    assert delivered, (fixture_id, actor_id, needle)
                else:
                    assert not delivered, (fixture_id, actor_id, needle)
                    assert needle not in prompts_of(capture, actor_id), (
                        fixture_id, actor_id, needle)
                    assert not any(needle in row
                                   for row in observations), (
                        fixture_id, actor_id, needle)

    # The distinct canaries make the pairwise asymmetry explicit: the
    # proposal owner is excluded from the Dana<->Sam consultation.
    announce_capture = outcome.capture[route_ids["announce_full_plan"]]
    assert FOLLOWUP_TWO_CANARY not in prompts_of(announce_capture,
                                                 "proposal_owner")
    assert FOLLOWUP_ONE_CANARY not in prompts_of(announce_capture,
                                                 "budget_owner")


# ---------------------------------------------------------------------------
# authority differences
# ---------------------------------------------------------------------------

def test_authority_gates_the_outcome_only_from_the_authority_holder():
    """The authority holder's veto gates the declared outcome in a way a
    non-authority actor's IDENTICAL utterance does not.  Two probe
    branches swap exactly two turn texts between Sam (the fixture's
    declared operations-lead authority) and Chris (no authority): the
    committed rows differ ONLY in which name is attributed to the veto
    utterance and the third commitment, yet the declared outcome flips
    -- because the evaluator's veto predicate is keyed to the fixture's
    authority structure, not to the words alone."""
    fx = load_fixture_two()
    tables = {
        "authority_holder_veto": {
            "proposal_owner": [None],
            "operations_lead": [PROBE_VETO_TURN],
            "budget_owner": [PROBE_COMMIT_TURN],
            "product_lead": [PROBE_COMMIT_TURN],
            "neutral_member": [PROBE_COMMIT_TURN],
        },
        "same_words_no_authority": {
            "proposal_owner": [None],
            "operations_lead": [PROBE_COMMIT_TURN],
            "budget_owner": [PROBE_COMMIT_TURN],
            "product_lead": [PROBE_COMMIT_TURN],
            "neutral_member": [PROBE_VETO_TURN],
        },
    }
    candidates = [
        make_candidate("authority_holder_veto", PROBE_ACTION,
                       owner="proposal_owner", timing=PROBE_TIMING),
        make_candidate("same_words_no_authority", PROBE_ACTION,
                       owner="proposal_owner", timing=PROBE_TIMING),
    ]
    run, evaluated, _ = run_probe(fx, candidates, tables)
    with_authority, without_authority = evaluated
    assert with_authority.infrastructure_errors == ()
    assert without_authority.infrastructure_errors == ()

    rows_a = _committed_descriptions(with_authority)
    rows_b = _committed_descriptions(without_authority)
    assert len(rows_a) == len(rows_b) == ROUND_LENGTH + 1

    # The two branches differ ONLY in the attribution swap: same row
    # multiset of turn texts, exactly two differing positions.
    differing = [index for index, (row_a, row_b)
                 in enumerate(zip(rows_a, rows_b)) if row_a != row_b]
    assert differing == [2, 5]
    assert f"{AUTHORITY_NAME}: {PROBE_VETO_TURN}" in rows_a[2]
    assert f"{AUTHORITY_NAME}: {PROBE_COMMIT_TURN}" in rows_b[2]
    assert f"Chris: {PROBE_COMMIT_TURN}" in rows_a[5]
    assert f"Chris: {PROBE_VETO_TURN}" in rows_b[5]
    # Non-vacuity: the identical veto utterance occurs in BOTH traces.
    assert sum(1 for row in rows_a if PROBE_VETO_TURN in row) == 1
    assert sum(1 for row in rows_b if PROBE_VETO_TURN in row) == 1

    # Same measured support in both branches (three commitments)...
    assert with_authority.outcome_metrics[
        "explicit_support_commitments"].value == 3
    assert without_authority.outcome_metrics[
        "explicit_support_commitments"].value == 3
    # ...but the veto binds ONLY from the authority holder's own turn.
    veto_a = with_authority.outcome_metrics["veto_exercised"]
    assert veto_a.value is True
    rows_by_id = {event.event_id: event.description
                  for event in with_authority.event_trace}
    for reference in veto_a.computed_from:
        row = rows_by_id[reference.partition(":")[2]]
        assert ACTOR_TURN_ANCHOR in row
        assert f"{AUTHORITY_NAME}: {PROBE_VETO_TURN}" in row
    assert without_authority.outcome_metrics[
        "veto_exercised"].value is False

    # The declared outcome flips on authority alone.
    assert with_authority.outcome_metrics[
        "decision_rule_satisfied"].value is False
    assert with_authority.terminal_status == "failure"
    assert without_authority.outcome_metrics[
        "decision_rule_satisfied"].value is True
    assert without_authority.terminal_status == "success"


# ---------------------------------------------------------------------------
# actor-owned votes / commitments
# ---------------------------------------------------------------------------

def test_counted_commitments_cite_actor_authored_turns(team_slice):
    """Every counted vote/commitment cites a resolved actor-authored
    turn: in the winner branch the four commitment citations resolve to
    four anchored rows attributed to the four distinct committing
    actors, and each cited row contains that actor's own recorded
    attempt; in the vote branch the single counted vote is Priya's own
    turn."""
    outcome = team_slice
    names = actor_names(outcome.fx)
    results = branch_results_by_fixture_id(outcome)
    route_ids = route_ids_by_fixture_id(outcome)

    winner = results["private_ops_then_pilot"]
    metric = winner.outcome_metrics["explicit_support_commitments"]
    assert metric.value == 4
    rows_by_id = {event.event_id: event.description
                  for event in winner.event_trace}
    branch = _trace_branch(outcome, route_ids["private_ops_then_pilot"])
    attempts_by_actor = {
        actor_id: [attempt["attempt"]
                   for attempt in record["attempts"]]
        for actor_id, record in branch["actor_records"].items()}

    committers = set()
    for reference in metric.computed_from:
        row = rows_by_id[reference.partition(":")[2]]
        assert ACTOR_TURN_ANCHOR in row
        assert COMMIT_MARKER in row
        owners = [actor_id for actor_id, name in names.items()
                  if f"{name}: " in row]
        assert len(owners) == 1, row
        owner = owners[0]
        committers.add(owner)
        # The cited row is the owner's OWN recorded attempt.
        assert any(attempt in row
                   for attempt in attempts_by_actor[owner]), row
    assert committers == {"operations_lead", "budget_owner",
                          "product_lead", "neutral_member"}

    # The declared decision rule cites those same actor-owned rows plus
    # the whole-trace scan bound.
    rule = winner.outcome_metrics["decision_rule_satisfied"]
    assert set(metric.computed_from) <= set(rule.computed_from)
    assert "state:committed_event_count" in rule.computed_from

    # Vote branch: the single counted vote is Priya's own turn.
    vote = results["immediate_binding_vote"]
    vote_metric = vote.outcome_metrics["explicit_support_commitments"]
    assert vote_metric.value == 1
    vote_rows = {event.event_id: event.description
                 for event in vote.event_trace}
    (reference,) = vote_metric.computed_from
    row = vote_rows[reference.partition(":")[2]]
    assert ACTOR_TURN_ANCHOR in row
    assert "Priya: Vote in favor" in row


def test_actor_cannot_cast_another_actors_vote():
    """A scripted attempt by one actor to cast another actor's vote is
    blocked by the hardened agency guard BEFORE commit: the asserted
    vote is removed, the availability sentence is appended, the
    escalation is recorded, the affected actor still takes its own turn,
    and the vote/commitment metric counts ONLY the affected actor's own
    later commitment -- never the asserted one."""
    fx = load_fixture_two()
    asserted_clause = "Dana votes in favor immediately."
    tables = {
        "agency_probe": {
            "proposal_owner": [
                "Present the revised plan to the team. "
                + asserted_clause],
            "operations_lead": [
                "Listen to the presentation and take notes on the "
                "operations impact."],
            "budget_owner": [
                "State an explicit commitment to the revised plan "
                "after hearing the presentation."],
            "product_lead": [
                "Note the customer impact of the revised plan."],
            "neutral_member": ["Observe the discussion quietly."],
        },
    }
    candidates = [make_candidate(
        "agency_probe", "Present the revised plan and gather responses.",
        owner="proposal_owner", timing=PROBE_TIMING)]
    run, evaluated, capture = run_probe(fx, candidates, tables)
    result = evaluated[0]
    assert result.infrastructure_errors == ()
    raw = run.runner_records["agency_probe"]

    # The committed proposal-owner event lost the asserted vote and
    # gained the availability sentence naming the affected actor.
    owner_event = result.event_trace[1].description
    assert asserted_clause not in owner_event
    assert "Present the revised plan to the team." in owner_event
    assert f"Dana {AVAILABILITY_MARKER}" in owner_event
    for event in raw["committed_events"]:
        assert asserted_clause not in event

    # Exactly one escalation record, fully attributed.
    interventions = raw["guard_interventions"]
    assert len(interventions) == 1
    record = interventions[0]
    assert record["step"] == 1
    assert record["active"] == "Riley"
    assert record["affected"] == ["Dana"]
    assert "Dana votes" in record["original_excerpt"]
    assert AVAILABILITY_MARKER in record["rewritten_excerpt"]

    # The affected actor then received ITS OWN turn and its committed
    # action is its scripted choice.
    dana_model = capture["agency_probe"]["actors"]["budget_owner"]
    assert len(dana_model.prompts) == 1
    dana_event = result.event_trace[3].description
    assert "Dana: State an explicit commitment to the revised plan" \
        in dana_event

    # The commitment metric counts EXACTLY Dana's own turn.
    metric = result.outcome_metrics["explicit_support_commitments"]
    assert metric.value == 1
    rows_by_id = {event.event_id: event.description
                  for event in result.event_trace}
    (reference,) = metric.computed_from
    assert rows_by_id[reference.partition(":")[2]] == dana_event

    # The escalation is part of the causal trace artifact.
    trace = build_trace_report(run, evaluated)
    validate_trace_report(trace)
    assert trace["branches"][0]["guard_interventions"] == interventions


# ---------------------------------------------------------------------------
# no GM-cast votes, no GM-forced coalition
# ---------------------------------------------------------------------------

def test_gm_narration_cannot_cast_votes_or_force_a_coalition(team_slice):
    """A Game-Master narration row textually announcing a vote tally, a
    pilot acceptance, a recorded outcome, and a formed coalition must
    not be citable for any outcome predicate: every metric measures
    False/zero against the whole-trace scan bound and the branch stays
    'cutoff' -- even though every actor OBSERVED the narration.  (In
    this build the GM's narration channels are the neutral premise and
    the pre-start event record; the resolution chain has no
    narrative-push step and the observation queue never invents text.)
    Control: in the shared slice's winner branch the same predicates
    measure True citing the owning actors' resolved turns."""
    fx = load_fixture_two()
    world, registry = world_variant(
        fx, "w_gm_narration_check",
        [{"description": NARRATED_TALLY_CLAIM,
          "visible_to": list(actor_order(fx)),
          "time": "2026-08-04T09:05:00Z"}])
    tables = {
        "narration_check": {
            "proposal_owner": [
                "Open the scheduled discussion and invite responses on "
                "the migration question."],
            "operations_lead": [
                "Note the rumor and wait for the actual discussion "
                "before responding."],
            "budget_owner": ["Ask where the rumor originated."],
            "product_lead": [
                "Wait for concrete responses from the discussion."],
            "neutral_member": ["Observe the discussion quietly."],
        },
    }
    candidates = [make_candidate(
        "narration_check",
        "Open the discussion on the migration question.",
        owner="proposal_owner", timing=PROBE_TIMING)]
    run, evaluated, _ = run_probe(fx, candidates, tables, world=world,
                                  registry=registry)
    result = evaluated[0]
    assert result.infrastructure_errors == ()

    # Non-vacuity: the claiming narration IS in the committed trace and
    # was OBSERVED by all five actors -- yet it is a narration row, not
    # a resolved actor turn.
    narration_rows = [event.description for event in result.event_trace
                      if "a majority coalition has formed"
                      in event.description]
    assert len(narration_rows) == 1
    assert ACTOR_TURN_ANCHOR not in narration_rows[0]
    assert COMMIT_MARKER in narration_rows[0]
    assert PILOT_ACCEPT_UTTERANCE in narration_rows[0]
    assert FINAL_MARKER in narration_rows[0]
    memories = run.runner_records["narration_check"]["actor_memories"]
    for actor_id in actor_order(fx):
        assert any("a majority coalition has formed" in row
                   for row in memories[actor_id]), actor_id

    # No predicate counted the narration: everything measures False /
    # zero, citing the whole-trace scan bound; no coalition or outcome
    # was forced -- the branch ends 'cutoff', not a fabricated verdict.
    whole_trace = ("state:committed_event_count",)
    metrics = result.outcome_metrics
    assert metrics["explicit_support_commitments"].value == 0
    assert metrics["explicit_support_commitments"].computed_from \
        == whole_trace
    assert metrics["pilot_accepted"].value is False
    assert metrics["final_decision_recorded"].value is False
    assert metrics["decision_rule_satisfied"].value is False
    assert metrics["veto_exercised"].value is False
    assert result.terminal_status == "cutoff"

    # Control: the shared slice's winner branch measures True on the
    # same predicates, citing the owning actors' OWN resolved turns.
    winner = branch_results_by_fixture_id(team_slice)[
        "private_ops_then_pilot"]
    rows_by_id = {event.event_id: event.description
                  for event in winner.event_trace}
    pilot = winner.outcome_metrics["pilot_accepted"]
    assert pilot.value is True
    for reference in pilot.computed_from:
        row = rows_by_id[reference.partition(":")[2]]
        assert ACTOR_TURN_ANCHOR in row
        assert f"{AUTHORITY_NAME}: {PILOT_ACCEPT_UTTERANCE}" in row


# ---------------------------------------------------------------------------
# persistent memory across multiple rounds
# ---------------------------------------------------------------------------

def test_actor_memory_persists_across_rounds(team_slice):
    """An actor's round-2 action provably references round-1 private
    content: in the winner branch Sam's step-7 meeting turn cites the
    one-sprint cost cap that exists ONLY in Sam's own step-2 private
    conversation turn.  Prompt-capture proof: Sam's second prompt
    carries the full round-1 private turn and the phrase; Sam's first
    prompt does not (the phrase did not exist yet), and no other
    actor's round-1 prompt ever saw it."""
    outcome = team_slice
    route_id = route_ids_by_fixture_id(outcome)["private_ops_then_pilot"]
    capture = outcome.capture[route_id]
    result = branch_results_by_fixture_id(outcome)[
        "private_ops_then_pilot"]
    round_one_private_turn = TEAM_TURNS["private_ops_then_pilot"][
        "operations_lead"][0]
    round_two_reference_turn = TEAM_TURNS["private_ops_then_pilot"][
        "operations_lead"][1]
    assert MEMORY_PHRASE in round_one_private_turn
    assert MEMORY_PHRASE in round_two_reference_turn

    # Sam acted twice (rounds one and two).  The second prompt carries
    # Sam's OWN round-1 private turn, the inserted candidate action it
    # replied to, and the memory phrase -- content only ever delivered
    # before round one's end, so its presence at round two IS
    # persistence.
    sam_prompts = capture["actors"]["operations_lead"].prompts
    assert len(sam_prompts) == 2
    assert round_one_private_turn in sam_prompts[1]
    assert outcome.fx.candidates[1].action in sam_prompts[1]
    assert MEMORY_PHRASE in sam_prompts[1]
    assert MEMORY_PHRASE not in sam_prompts[0]

    # The phrase exists in EXACTLY two committed rows: Sam's private
    # round-1 turn and Sam's own round-2 anchored reference to it.
    descriptions = _committed_descriptions(result)
    phrase_rows = [index for index, row in enumerate(descriptions)
                   if MEMORY_PHRASE in row]
    assert phrase_rows == [2, 7]
    assert f"{AUTHORITY_NAME}: " in descriptions[7]
    assert ACTOR_TURN_ANCHOR in descriptions[7]
    assert round_two_reference_turn in descriptions[7]

    # No OTHER actor's round-1 prompt ever contained the phrase (it was
    # private until Sam's own public round-2 disclosure).
    for actor_id in ("budget_owner", "product_lead", "neutral_member"):
        first_prompt = capture["actors"][actor_id].prompts[0]
        assert MEMORY_PHRASE not in first_prompt, actor_id

    # And the trace records Sam's two attempts at rotation steps 2/7.
    branch = _trace_branch(outcome, route_id)
    steps = [attempt["step"] for attempt in
             branch["actor_records"]["operations_lead"]["attempts"]]
    assert steps == [2, 7]


# ---------------------------------------------------------------------------
# explicit final outcome from actor/world events
# ---------------------------------------------------------------------------

def test_final_outcome_is_explicit_and_never_fabricated(team_slice):
    """The declared outcome derives from committed actor turns only,
    with an explicit terminal status from the closed set: the winner
    measures success, both losing branches measure failure, and the
    outcome-recording row is the proposal owner's OWN anchored turn in
    every branch.  A cutoff variant -- the meeting ends without
    commitments, veto, or recording -- keeps the runner's 'cutoff'
    status: no outcome is fabricated."""
    outcome = team_slice
    results = branch_results_by_fixture_id(outcome)

    expected_status = {"private_ops_then_pilot": "success",
                       "announce_full_plan": "failure",
                       "immediate_binding_vote": "failure"}
    recording_turn = {"private_ops_then_pilot": RECORD_SUCCESS_TURN,
                      "announce_full_plan": RECORD_FAILURE_TURN,
                      "immediate_binding_vote": RECORD_FAILURE_TURN}
    for fixture_id, result in results.items():
        assert result.terminal_status in TERMINAL_STATUSES
        assert result.terminal_status == expected_status[fixture_id]

        # The explicit outcome record is Riley's OWN resolved turn, and
        # the metric cites exactly that row.
        metric = result.outcome_metrics["final_decision_recorded"]
        assert metric.value is True
        rows_by_id = {event.event_id: event.description
                      for event in result.event_trace}
        (reference,) = metric.computed_from
        row = rows_by_id[reference.partition(":")[2]]
        assert ACTOR_TURN_ANCHOR in row
        assert f"Riley: {recording_turn[fixture_id]}" in row

        # Every decision-rule citation is an anchored actor turn or the
        # whole-trace scan bound -- never a narration row.
        for reference in result.outcome_metrics[
                "decision_rule_satisfied"].computed_from:
            kind, _, target = reference.partition(":")
            if kind == "event":
                assert ACTOR_TURN_ANCHOR in rows_by_id[target]
            else:
                assert reference == "state:committed_event_count"

    # Cutoff variant: a meeting that ends without resolution.
    fx = load_fixture_two()
    tables = {
        "cutoff_probe": {
            "proposal_owner": [
                "Open the discussion and ask for reactions to the "
                "migration question."],
            "operations_lead": [
                "Ask how the operations load would be scoped before "
                "taking any position."],
            "budget_owner": [
                "Ask for the cost figures before taking any position."],
            "product_lead": [
                "Describe the customer pain without taking a position."],
            "neutral_member": ["Observe the discussion quietly."],
        },
    }
    candidates = [make_candidate(
        "cutoff_probe", "Open the discussion and gather reactions.",
        owner="proposal_owner", timing=PROBE_TIMING)]
    _, evaluated, _ = run_probe(fx, candidates, tables)
    unresolved = evaluated[0]
    assert unresolved.infrastructure_errors == ()
    assert unresolved.terminal_status == "cutoff"
    assert unresolved.terminal_status in TERMINAL_STATUSES
    metrics = unresolved.outcome_metrics
    assert metrics["explicit_support_commitments"].value == 0
    assert metrics["veto_exercised"].value is False
    assert metrics["final_decision_recorded"].value is False
    assert metrics["decision_rule_satisfied"].value is False

    # Across the slice and the cutoff variant, every observed status is
    # an explicit member of the closed set.
    statuses = {result.terminal_status for result in results.values()}
    statuses.add(unresolved.terminal_status)
    assert statuses == {"success", "failure", "cutoff"}
    assert statuses <= set(TERMINAL_STATUSES)


# ---------------------------------------------------------------------------
# repeated execution
# ---------------------------------------------------------------------------

def test_repeated_full_slice_executions_are_byte_identical(
        team_slice, team_slice_second):
    """The full slice twice in one process: zero infrastructure errors
    and byte-identical canonical artifacts."""
    for outcome in (team_slice, team_slice_second):
        for result in list(outcome.run.results) + list(outcome.evaluated):
            assert result.infrastructure_errors == ()
        for branch in outcome.trace["branches"]:
            assert branch["terminal_status"] in TERMINAL_STATUSES
    assert report_canonical_json(team_slice.report) \
        == report_canonical_json(team_slice_second.report)
    assert trace_report_canonical_json(team_slice.trace) \
        == trace_report_canonical_json(team_slice_second.trace)
