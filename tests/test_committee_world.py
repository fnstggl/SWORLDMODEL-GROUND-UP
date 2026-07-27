"""Committee world: scheduled releases, briefing latency, information
locality changing a vote, authority enforcement, mechanical tally."""
import json
from datetime import timedelta

import pytest

from sworldmodel import Engine, World, at_local, check_conditions, parse_iso
from worlds import committee_world
from worlds.committee_world import CAST_VOTE, PROPOSE_MOTION

MX = "America/Mexico_City"


@pytest.fixture(scope="module")
def outcome():
    w, minds, t = committee_world.build()
    out = Engine(w, minds, t).run()
    return out


def test_outcome_hold_2_1_with_fran_traveling(outcome):
    assert outcome.status == "resolved"
    assert outcome.answer["answer"] == "hold"
    assert "hold 2-1" in outcome.answer["detail"]
    # producers are the vote records themselves
    assert len(outcome.answer["computed_from"]) == 3


def test_votes_are_validated_actions_not_engine_magic(outcome):
    w = outcome.world
    votes = [a for a in w.actions.values() if a["verb"] == "cast_vote"]
    assert len(votes) == 3 and all(v["state"] == "completed" for v in votes)
    ballots = {r["producer"]: r["value"] for r in w.find_records("vote")}
    assert ballots == {"dana": "hold", "eli": "cut", "fran": "hold"}
    # each ballot carries its own authority provenance and producing event
    for r in w.find_records("vote"):
        assert r["authority"] and r["producing_event"] and r["subject"]


def test_briefing_timing_and_attention_patterns(outcome):
    w = outcome.world
    briefing = next(i for i in w.infos.values()
                    if i["data"].get("type") == "briefing")
    # release 08:00 + 5s wire + 4h preparation + 30s email latency
    assert parse_iso(briefing["delivered"]["eli"]) \
        == at_local(2026, 6, 24, 12, 0, 35, tz=MX)
    # eli checks half-hourly -> 12:30; dana's assistant batches hourly -> 13:00
    assert parse_iso(briefing["noticed"]["eli"]) == at_local(2026, 6, 24, 12, 30, tz=MX)
    assert parse_iso(briefing["noticed"]["dana"]) == at_local(2026, 6, 24, 13, 0, tz=MX)


def test_information_locality_fran_never_saw_the_briefing(outcome):
    w = outcome.world
    briefing = next(i for i in w.infos.values()
                    if i["data"].get("type") == "briefing")
    assert "fran" in briefing["delivered"]        # it reached her inbox
    assert "fran" not in briefing["noticed"]      # she never saw it
    # and her belief still carries the stale basis
    assert w.actors["fran"].beliefs["inflation"].basis == "May CPI report"
    assert "below" not in w.actors["fran"].beliefs["inflation"].statement


def test_terminal_flips_when_fran_is_present():
    w, minds, t = committee_world.build(fran_traveling=False)
    out = Engine(w, minds, t).run()
    assert out.answer["answer"] == "cut"
    assert "cut 2-1" in out.answer["detail"]
    ballots = {r["producer"]: r["value"] for r in w.find_records("vote")}
    assert ballots["fran"] == "cut"               # same person, informed vote


def test_authority_and_double_vote_guards():
    w, minds, t = committee_world.build()
    w.apply("fact.set", {"key": "meeting_open", "value": True}, None)
    # a non-chair cannot put a motion on the floor
    reason = check_conditions(w, "eli", {"motion": "x"},
                              PROPOSE_MOTION["conditions"])
    assert reason and "authority" in reason
    # the analyst cannot vote
    w.apply("fact.set", {"key": "motion", "value": "x"}, None)
    reason = check_conditions(w, "gus", {"motion": "x", "choice": "hold"},
                              CAST_VOTE["conditions"])
    assert reason and "authority" in reason
    # nobody votes twice
    w.apply("record.add", {"record_type": "vote", "producer": "eli",
                           "subject": "x", "value": "cut"}, None)
    reason = check_conditions(w, "eli", {"motion": "x", "choice": "cut"},
                              CAST_VOTE["conditions"])
    assert reason and "already exists" in reason


def test_meeting_wakes_are_scheduled_commitments(outcome):
    w = outcome.world
    meeting_decisions = [
        r for r in w.records if r["op"] == "actor.decision"
        and any(x["kind"] == "scheduled_commitment" for x in r["data"]["reasons"])]
    assert {r["data"]["actor"] for r in meeting_decisions} == {"dana", "eli", "fran"}
    assert all(parse_iso(r["t"]) == at_local(2026, 6, 25, 10, 0, tz=MX)
               for r in meeting_decisions)


def test_replay_and_determinism(outcome):
    w = outcome.world
    w2, minds2, t2 = committee_world.build()
    Engine(w2, minds2, t2).run()
    assert json.dumps(w.records) == json.dumps(w2.records)
    replayed = World.from_records(w.records)
    assert replayed.state_hash() == w.state_hash()
    assert replayed.terminal_result == w.terminal_result
