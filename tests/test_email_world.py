"""Email world: exact real-calendar timing (weekend + DST), information
locality, durations, wake economy, persistence, and history-dependent
terminal."""
import json
from datetime import timedelta

import pytest

from sworldmodel import Engine, World, at_local, elapsed, parse_iso
from worlds import email_world

LA = "America/Los_Angeles"
NY = "America/New_York"


@pytest.fixture(scope="module")
def outcome():
    w, minds, t = email_world.build()
    out = Engine(w, minds, t).run()
    return out


def recs(w, op):
    return [r for r in w.records if r["op"] == op]


def test_resolves_yes(outcome):
    assert outcome.status == "resolved"
    assert outcome.answer["answer"] == "yes"
    assert outcome.answer["computed_from"]


def test_time_progresses_correctly_across_weekend_and_dst(outcome):
    w = outcome.world
    deliveries = [r for r in recs(w, "info.deliver") if r["data"]["to"] == "bob"]
    notices = [r for r in recs(w, "info.notice") if r["data"]["actor"] == "bob"]
    assert len(deliveries) == 1 and len(notices) == 1
    delivered = parse_iso(deliveries[0]["t"])
    noticed = parse_iso(notices[0]["t"])
    # sent Friday 21:10 ET + 8 min composing + 30 s latency
    assert delivered == at_local(2026, 3, 6, 21, 18, 30, tz=NY)
    # noticed Monday 09:00 Pacific -- after the weekend AND spring-forward
    assert noticed == at_local(2026, 3, 9, 9, 0, tz=LA)
    # exact elapsed time: 61h41m30s, one hour SHORTER than wall arithmetic
    # because 2026-03-08 02:00-03:00 never existed
    assert elapsed(delivered, noticed) == timedelta(hours=61, minutes=41, seconds=30)


def test_information_is_local(outcome):
    w = outcome.world
    bob_notice_t = parse_iso(next(r["t"] for r in recs(w, "info.notice")
                                  if r["data"]["actor"] == "bob"))
    # Bob produces nothing -- no decision, belief, or intention -- before he
    # actually noticed the message
    for r in w.records:
        if r["op"] in ("actor.decision", "actor.belief", "action.propose") \
                and r["data"].get("actor") == "bob" \
                and r["seq"] > 1:
            if r["op"] == "actor.belief" and r["data"]["topic"] == "q2_numbers":
                continue  # his own genesis belief
            assert parse_iso(r["t"]) >= bob_notice_t
    # Bob's reply content came from HIS belief, not from any world fact
    reply = next(i for i in w.infos.values() if i["data"].get("type") == "reply")
    assert "$4.2M" in reply["content"]
    assert "$4.2M" not in json.dumps(w.facts)


def test_actions_take_their_stated_time(outcome):
    w = outcome.world
    for act in w.actions.values():
        assert act["state"] == "completed"
        took = parse_iso(act["completed_at"]) - parse_iso(act["started_at"])
        assert took == timedelta(seconds=act["duration"]["seconds"])
        assert act["duration"]["basis"] in ("verified", "inferred", "actor_chosen",
                                            "process_derived", "immediate", "unknown")
    reply_send = next(a for a in w.actions.values()
                      if a["verb"] == "send_message" and a["actor"] == "bob")
    assert parse_iso(reply_send["completed_at"]) - parse_iso(reply_send["started_at"]) \
        == timedelta(minutes=12)


def test_actors_wake_only_for_reasons(outcome):
    w = outcome.world
    decisions = recs(w, "actor.decision")
    by_actor = {}
    for r in decisions:
        assert r["data"]["reasons"], "wake without a recorded trigger"
        by_actor.setdefault(r["data"]["actor"], []).append(r)
    # no polling: alice decides exactly 4 times, bob exactly 3
    assert len(by_actor["alice"]) == 4
    assert len(by_actor["bob"]) == 3


def test_state_persists(outcome):
    w = outcome.world
    bob = w.actors["bob"]
    assert bob.beliefs["q2_numbers"].statement.startswith("The final Q2")
    assert bob.beliefs["alice_request"]
    alice = w.actors["alice"]
    assert alice.beliefs["q2_confirmed"]
    assert alice.commitments["c1"].resolved
    assert len(alice.memories) >= 3 and len(bob.memories) >= 3


def test_consequences_enter_the_world(outcome):
    w = outcome.world
    infos = list(w.infos.values())
    assert len(infos) == 2                      # question + reply
    reply = next(i for i in infos if i["data"].get("type") == "reply")
    assert "alice" in reply["delivered"] and "alice" in reply["noticed"]


def test_terminal_depends_on_what_actually_happened():
    w, minds, t = email_world.build(reply=False)
    out = Engine(w, minds, t).run()
    assert out.status == "cutoff"
    assert out.answer["answer"] == "no"
    # Bob read it and believes Alice asked -- but never replied, so the
    # mechanical answer flips
    assert w.actors["bob"].beliefs["alice_request"]


def test_replay_and_determinism(outcome):
    w = outcome.world
    w2, minds2, t2 = email_world.build()
    Engine(w2, minds2, t2).run()
    assert json.dumps(w.records) == json.dumps(w2.records)
    replayed = World.from_records(w.records)
    assert replayed.state_hash() == w.state_hash()
    assert replayed.terminal_result == w.terminal_result
