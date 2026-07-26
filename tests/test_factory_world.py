"""Factory world: exact continuous accrual under an operating calendar,
condition-completed actions, threshold retargeting across shift boundaries,
transit delays, and a measured terminal with producer lineage."""
import json
from datetime import timedelta

import pytest

from sworldmodel import Engine, World, at_local, parse_iso
from worlds import factory_world

CH = "America/Chicago"


@pytest.fixture(scope="module")
def outcome():
    w, minds, t = factory_world.build()
    out = Engine(w, minds, t).run()
    return out


def test_delivered_and_remaining_quantities_exact(outcome):
    w = outcome.world
    assert outcome.answer["answer"] == 500.0
    assert w.resource("acme", "widgets") == 500.0
    assert w.resource("carrier", "widgets") == 0.0
    # Mon 8:00-16:00 (320) + Tue 8-16 (320) + Wed 8-16 (320) + Thu 8-12 (160)
    # minus the 500 shipped = 620 on hand at the cutoff
    assert w.resource("factory", "widgets") == pytest.approx(620.0)


def test_accrual_only_while_the_shift_runs(outcome):
    w = outcome.world
    accruals = [r for r in w.records if r["op"] == "process.accrue"]
    total = sum(r["data"]["amount"] for r in accruals)
    assert total == pytest.approx(1120.0)          # 28 shift-hours x 40/h
    # every accrual interval lies inside a single shift window
    for r in accruals:
        frm = parse_iso(r["data"]["from"]).astimezone().astimezone
        start = parse_iso(r["data"]["from"])
        end = parse_iso(r["data"]["to"])
        assert (end - start) <= timedelta(hours=8)
        local_start = start.astimezone(__import__("zoneinfo").ZoneInfo(CH))
        local_end = end.astimezone(__import__("zoneinfo").ZoneInfo(CH))
        assert 8 <= local_start.hour < 16
        assert (8 < local_end.hour < 16 or (local_end.hour == 16
                                            and local_end.minute == 0)
                or local_end.hour == 8)


def test_threshold_projected_cancelled_and_retargeted(outcome):
    w = outcome.world
    scheduled = [r for r in w.records if r["op"] == "event.scheduled"
                 and r["data"]["kind"] == "watch.reached"]
    assert len(scheduled) == 2
    # first projection from Monday 09:45: 430 remaining / 40 per hour = 20:30
    assert parse_iso(scheduled[0]["data"]["t"]) == at_local(2026, 4, 6, 20, 30, tz=CH)
    # retargeted after the overnight stop: Tuesday 12:30
    assert parse_iso(scheduled[1]["data"]["t"]) == at_local(2026, 4, 7, 12, 30, tz=CH)
    cancelled = [r for r in w.records if r["op"] == "event.cancelled"
                 and "watch" in r["data"]["reason"]]
    assert len(cancelled) == 1                     # the 20:30 projection died at 16:00
    fired = next(r for r in w.records if r["op"] == "event.fired"
                 and r["data"]["kind"] == "watch.reached")
    assert parse_iso(fired["t"]) == at_local(2026, 4, 7, 12, 30, tz=CH)


def test_condition_completed_action_lifecycle(outcome):
    w = outcome.world
    act = next(a for a in w.actions.values() if a["verb"] == "fulfill_order")
    assert act["state"] == "completed"
    assert parse_iso(act["started_at"]) == at_local(2026, 4, 6, 9, 45, tz=CH)
    assert parse_iso(act["completed_at"]) == at_local(2026, 4, 7, 12, 30, tz=CH)
    assert act["completes_when"] == {"resource_at_least": ["factory", "widgets", 500]}


def test_transit_delay_and_delivery(outcome):
    w = outcome.world
    transfers = [r for r in w.records if r["op"] == "resource.transfer"]
    to_carrier = next(r for r in transfers if r["data"]["to_holder"] == "carrier")
    to_acme = next(r for r in transfers if r["data"]["to_holder"] == "acme")
    assert parse_iso(to_carrier["t"]) == at_local(2026, 4, 7, 12, 30, tz=CH)
    assert parse_iso(to_acme["t"]) == at_local(2026, 4, 8, 6, 30, tz=CH)  # +18h
    assert w.facts["order:o1:status"] == "delivered"


def test_manager_notices_on_his_own_attention_pattern(outcome):
    w = outcome.world
    confirmation = next(i for i in w.infos.values()
                        if i["data"].get("type") == "delivery")
    # delivered 06:31, but his desk opens at 08:00
    assert parse_iso(confirmation["delivered"]["mo"]) \
        == at_local(2026, 4, 8, 6, 31, tz=CH)
    assert parse_iso(confirmation["noticed"]["mo"]) \
        == at_local(2026, 4, 8, 8, 0, tz=CH)
    assert w.actors["mo"].commitments["c_o1"].resolved


def test_unattended_recipient_stays_unnoticed(outcome):
    w = outcome.world
    confirmation = next(i for i in w.infos.values()
                        if i["data"].get("type") == "delivery")
    assert "acme_contact" in confirmation["delivered"]
    assert "acme_contact" not in confirmation["noticed"]
    unsupported = [r for r in w.records if r["op"] == "info.noticing_unsupported"]
    assert any(r["data"]["actor"] == "acme_contact" for r in unsupported)


def test_terminal_lineage_reaches_back_to_production(outcome):
    ops = [e["op"] for e in
           (outcome.world.lineage(int(outcome.answer["computed_from"][0]
                                      .split(":")[1])))]
    # transfer <- delivery event <- ... back through the causal chain
    assert ops[0] == "resource.transfer"
    assert "event.fired" in ops
    assert len(outcome.answer["lineage"]) > 3


def test_replay_and_determinism(outcome):
    w = outcome.world
    w2, minds2, t2 = factory_world.build()
    Engine(w2, minds2, t2).run()
    assert json.dumps(w.records) == json.dumps(w2.records)
    replayed = World.from_records(w.records)
    assert replayed.state_hash() == w.state_hash()
    assert replayed.terminal_result == w.terminal_result
