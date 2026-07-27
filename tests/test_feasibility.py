"""The deterministic stock walk: scheduled commitments must be covered
by the world's own numbers, shortfalls route one targeted spine repair,
and anything uncomputable suppresses the verdict instead of guessing."""
import pytest

from compiler.binding import Bindings
from compiler.errors import SemanticAmbiguity
from compiler.feasibility import check_transfer_feasibility
from compiler.graph import WorldGraph


def depot_world(opening=15.0):
    g = WorldGraph()
    org = g.add_node("organization", "Northside depot", "the depot",
                     "question_given")
    rs = g.add_node("resource", "parcels", "parcel stock",
                    "question_given",
                    attrs={"holder": org, "amount": opening,
                           "unit": "parcels"})
    return g, org, rs


def dispatch(g, when, name="evening dispatch"):
    return g.add_node("event", name, "sends parcels onward",
                      "question_given", attrs={"when": when})


def test_covered_commitment_passes():
    g, org, rs = depot_world(opening=15.0)
    ev = dispatch(g, "2026-03-02T18:00:00-05:00")
    b = Bindings()
    b.events[ev] = {"amounts": {"parcels": {
        "kind": "transfer", "amount": 10, "from": "Northside depot",
        "to": None}}}
    check_transfer_feasibility(g, b)          # no raise


def test_overdraw_is_a_spine_defect_with_the_numbers():
    g, org, rs = depot_world(opening=15.0)
    ev = dispatch(g, "2026-03-02T18:00:00-05:00")
    b = Bindings()
    b.events[ev] = {"amounts": {"parcels": {
        "kind": "transfer", "amount": 100, "from": "Northside depot",
        "to": None}}}
    with pytest.raises(SemanticAmbiguity) as ei:
        check_transfer_feasibility(g, b)
    detail = ei.value.detail
    assert detail["document"] == "causal_spine"
    assert detail["repairable"] is True
    (defect,) = detail["defects"]
    assert "100" in defect and "15" in defect
    assert "computable stock" in defect


def test_process_accrual_covers_the_commitment():
    g, org, rs = depot_world(opening=15.0)
    ev = dispatch(g, "2026-03-02T18:00:00-05:00")
    pr = g.add_node("process", "sorting line", "produces parcels",
                    "question_given")
    g.add_edge(pr, "changes", rs)
    b = Bindings()
    b.events[ev] = {"amounts": {"parcels": {
        "kind": "transfer", "amount": 100, "from": "Northside depot",
        "to": None}}}
    # 2026-03-02 is a Monday: 09:00-17:00 at 12/hour = 96 by 18:00
    b.processes[pr] = {"amount_per_hour": 12, "rate_status": "verified",
                       "operating": {"timezone": "America/New_York",
                                     "workdays": [0], "start": "09:00",
                                     "end": "17:00",
                                     "from_date": "2026-03-02",
                                     "until_date": "2026-03-02"}}
    check_transfer_feasibility(g, b)          # 15 + 96 >= 100

    # but the same commitment one hour after the window OPENS is short:
    # by 10:00 only 12 have accrued
    early = dispatch(g, "2026-03-02T10:00:00-05:00", name="early dispatch")
    b.events[early] = {"amounts": {"parcels": {
        "kind": "transfer", "amount": 100, "from": "Northside depot",
        "to": None}}}
    with pytest.raises(SemanticAmbiguity):
        check_transfer_feasibility(g, b)


def test_arrivals_fund_later_departures():
    g, org, rs = depot_world(opening=0.0)
    g.add_node("organization", "Hilltop store", "receiver",
               "question_given")
    inbound = dispatch(g, "2026-03-02T09:00:00-05:00", name="delivery in")
    outbound = dispatch(g, "2026-03-02T12:00:00-05:00", name="send on")
    b = Bindings()
    b.events[inbound] = {"amounts": {"parcels": {
        "kind": "transfer", "amount": 30, "from": None,
        "to": "Northside depot"}}}
    b.events[outbound] = {"amounts": {"parcels": {
        "kind": "transfer", "amount": 25, "from": "Northside depot",
        "to": "Hilltop store"}}}
    check_transfer_feasibility(g, b)          # 0 + 30 >= 25

    b.events[outbound]["amounts"]["parcels"]["amount"] = 45
    with pytest.raises(SemanticAmbiguity):
        check_transfer_feasibility(g, b)


def test_unplaceable_event_suppresses_the_verdict():
    g, org, rs = depot_world(opening=0.0)
    timed = dispatch(g, "2026-03-02T18:00:00-05:00")
    untimed = g.add_node("event", "sometime delivery",
                         "arrives at an unstated moment",
                         "question_given")
    b = Bindings()
    b.events[timed] = {"amounts": {"parcels": {
        "kind": "transfer", "amount": 1000, "from": "Northside depot",
        "to": None}}}
    b.events[untimed] = {"amounts": {"parcels": {
        "kind": "transfer", "amount": 1000, "from": None,
        "to": "Northside depot"}}}
    # the inflow cannot be placed in time, so no accusation is computable
    check_transfer_feasibility(g, b)          # no raise


def test_uncovered_decorative_claim_is_a_defect():
    from compiler.feasibility import check_decorative_coverage
    g, org, rs = depot_world(opening=15.0)
    pr = g.add_node("process", "shipment arrival", "delivers the goods",
                    "question_given")
    g.add_edge(pr, "changes", rs)
    b = Bindings()
    b.processes[pr] = {"decorative": True, "why": "transfers carry it"}
    defects = check_decorative_coverage(g, b)
    assert list(defects) == ["process:shipment arrival"]
    assert "false" in defects["process:shipment arrival"]

    # a bound transfer crediting the stock makes the same claim true
    ev = dispatch(g, "2026-03-02T09:00:00-05:00", name="delivery in")
    b.events[ev] = {"amounts": {"parcels": {
        "kind": "transfer", "amount": 30, "from": None,
        "to": "Northside depot"}}}
    assert check_decorative_coverage(g, b) == {}


def test_working_process_covers_a_decorative_sibling():
    from compiler.feasibility import check_decorative_coverage
    g, org, rs = depot_world(opening=0.0)
    working = g.add_node("process", "sorting line", "produces parcels",
                         "question_given")
    wrapper = g.add_node("process", "intake desk", "receives the output",
                         "question_given")
    g.add_edge(working, "changes", rs)
    g.add_edge(wrapper, "changes", rs)
    b = Bindings()
    b.processes[working] = {"amount_per_hour": 5,
                            "rate_status": "verified"}
    b.processes[wrapper] = {"decorative": True, "why": "the line feeds it"}
    assert check_decorative_coverage(g, b) == {}
