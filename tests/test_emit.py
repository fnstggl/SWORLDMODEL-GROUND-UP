"""Deterministic emission: the vote shape (records from actor choices),
the boolean+majority refusal, and the numeric-provenance honesty rule."""
import copy

import pytest

from compiler.assemble import assemble
from compiler.binding import Bindings
from compiler.emit import emit_scenario
from compiler.errors import SemanticAmbiguity
from compiler.lower import lower
from tests.fixtures_discovery import EVIDENCE_IDS, docs

QUESTION = {"question": "Is the request approved before Friday?"}


def vote_docs():
    """A minimal committee: one member may cast an approve/reject vote at
    a scheduled session; the terminal counts approve votes."""
    res, spine, prod, state, unc = docs()
    res["answer_type"] = "boolean"
    res["cutoff"] = {"when": "2026-03-06T17:00:00-05:00",
                     "timezone": "America/New_York", "meaning": "cutoff"}
    res["positive_condition"] = "An approve vote is on record."
    res["proof"] = [{"kind": "record", "name": "the vote record",
                     "record_type": "vote", "rule": "count_value",
                     "value": "approve", "expected_count": 1,
                     "meaning": "the member's recorded vote"}]
    spine["steps"] = [
        {"name": "session opens", "kind": "scheduled_event",
         "meaning": "the scheduled voting session begins",
         "when": "2026-03-02T10:00:00-05:00",
         "basis": "verified", "evidence_ids": ["e1"]},
        {"name": "member casts a vote", "kind": "actor_decision",
         "meaning": "the member may vote approve or reject, or not vote",
         "prerequisites": [{"step": "session opens"}],
         "produces_proof": ["the vote record"],
         "uncertainty": "the member may not vote at all",
         "basis": "uncertain", "evidence_ids": []},
    ]
    prod["assignments"] = [
        {"step": "member casts a vote",
         "producers": [{"name": "Dr. Osei", "kind": "person",
                        "meaning": "the voting member",
                        "basis": "verified", "evidence_ids": ["e1"]}]}]
    state["entities"] = [
        {"name": "Dr. Osei", "timezone": "America/New_York",
         "availability": {"workdays": [0, 1, 2, 3, 4],
                          "open": "09:00", "close": "17:00"}}]
    unc["uncertainties"] = [{"about": "member casts a vote",
                             "meaning": "she may abstain entirely"}]
    unc["exclusions"] = []
    return res, spine, prod, state, unc


def vote_bindings(graph):
    b = Bindings()
    act = graph.resolve("action", "member casts a vote", "test")
    b.actions[act] = {
        "duration_minutes": 1,
        "duration_status": "model_memory_unverified",
        "duration_note": "casting a vote takes moments",
        "parameters": [{"name": "choice",
                        "meaning": "the vote being cast",
                        "allowed_values": ["approve", "reject"]}],
        "record_values": {"the vote record":
                          {"value": {"from_parameter": "choice"},
                           "subject": "the request"}}}
    return b


def test_actor_choice_becomes_a_parameterized_record():
    graph, _ = assemble(*vote_docs(), valid_evidence_ids=EVIDENCE_IDS)
    doc = emit_scenario(graph, vote_bindings(graph), QUESTION)
    (aff,) = doc["action_affordances"]
    assert aff["available_to"]["participants"] == ["Dr. Osei"]
    (rec,) = aff["consequences_on_completion"]
    assert rec["change_type"] == "create_record"
    assert rec["value_from_parameter"] == "choice"
    kinds = {c["condition_type"] for c in aff["preconditions"]}
    # the ballot constrains options; the session gates timing; nobody
    # votes twice
    assert {"parameter_one_of", "world_fact_is",
            "record_absent"} <= kinds
    # and the whole thing lowers through the unchanged deterministic layer
    compiled = lower(doc, QUESTION["question"])
    assert "member_casts_a_vote" in compiled.world.action_defs


def test_nothing_schedules_the_vote_itself():
    graph, _ = assemble(*vote_docs(), valid_evidence_ids=EVIDENCE_IDS)
    doc = emit_scenario(graph, vote_bindings(graph), QUESTION)
    for ev in doc["scheduled_events"]:
        for eff in ev["effects"]:
            assert eff["change_type"] != "create_record"


def test_boolean_majority_tally_is_refused_with_repair_guidance():
    res, spine, prod, state, unc = vote_docs()
    res["proof"][0]["rule"] = "majority"
    res["proof"][0].pop("value")
    graph, _ = assemble(res, spine, prod, state, unc,
                        valid_evidence_ids=EVIDENCE_IDS)
    with pytest.raises(SemanticAmbiguity, match="majority tally") as ei:
        emit_scenario(graph, vote_bindings(graph), QUESTION)
    assert ei.value.detail["document"] == "resolution_contract"


def test_uncited_numeric_estimates_carry_the_honest_label():
    graph, _ = assemble(*vote_docs(), valid_evidence_ids=EVIDENCE_IDS)
    b = vote_bindings(graph)
    act = graph.resolve("action", "member casts a vote", "test")
    # the binding claims 'inferred' but the action cites no evidence: the
    # number is a world-knowledge estimate and must say so
    b.actions[act]["duration_status"] = "inferred"
    doc = emit_scenario(graph, b, QUESTION)
    (aff,) = doc["action_affordances"]
    assert aff["duration"]["status"] == "model_memory_unverified"


# ---------------------------------------------------------------------------
# same-holder substance identity: the binder's verdict merges or keeps apart
# ---------------------------------------------------------------------------

def stock_docs():
    """A depot's opening stock is declared under one name while the
    terminal measures the same goods under another; a scheduled delivery
    transfers more in."""
    res, spine, prod, state, unc = docs()
    res["answer_type"] = "quantity"
    res["cutoff"] = {"when": "2026-03-06T17:00:00-05:00",
                     "timezone": "America/New_York", "meaning": "cutoff"}
    res["positive_condition"] = "The depot's parcel count at the cutoff."
    res["proof"] = [{"kind": "quantity",
                     "name": "parcels counted at the depot",
                     "meaning": "the number of parcels the depot holds",
                     "unit": "parcels", "holder": "Northside depot",
                     "holder_kind": "organization"}]
    spine["steps"] = [
        {"name": "morning delivery", "kind": "scheduled_event",
         "meaning": "a van delivers 20 parcels to the depot",
         "when": "2026-03-02T10:00:00-05:00",
         "produces_proof": ["parcels counted at the depot"],
         "basis": "verified", "evidence_ids": ["e1"]}]
    prod["assignments"] = []
    state["entities"] = [
        {"name": "Northside depot", "timezone": "America/New_York",
         "availability": {"workdays": [0, 1, 2, 3, 4],
                          "open": "09:00", "close": "17:00"},
         "resources": [{"name": "stored parcels",
                        "meaning": "parcels already on the depot floor",
                        "amount": 15, "unit": "parcels",
                        "basis": "verified", "evidence_ids": ["e2"]}]}]
    unc["uncertainties"] = []
    unc["exclusions"] = []
    return res, spine, prod, state, unc


def stock_bindings(graph, same=None):
    b = Bindings()
    ev = graph.resolve("event", "morning delivery", "test")
    b.events[ev] = {"amounts": {"parcels counted at the depot":
                                {"kind": "transfer", "amount": 20,
                                 "from": None, "to": "Northside depot"}}}
    if same is not None:
        depot = graph.resolve("organization", "Northside depot", "test")
        b.substance_identities.append(
            {"holder": depot,
             "a": graph.resolve("resource", "stored parcels", "test"),
             "b": graph.resolve("resource", "parcels counted at the depot",
                                "test"),
             "same": same, "why": "test"})
    return b


def _quantity_names(doc):
    starting = {e["quantity"]["name"] for e in doc["starting_state"]
                if e.get("kind") == "quantity"}
    (obs,) = doc["resolution"]["observations"]
    return starting, obs["quantity"]


def test_unconfirmed_same_holder_stocks_stay_apart():
    graph, _ = assemble(*stock_docs(), valid_evidence_ids=EVIDENCE_IDS)
    doc = emit_scenario(graph, stock_bindings(graph), QUESTION)
    starting, measured = _quantity_names(doc)
    # nothing established identity, so the opening stock keeps its own
    # name and the measured quantity keeps its own
    assert measured not in starting


def test_binder_confirmed_identity_merges_the_stocks():
    graph, _ = assemble(*stock_docs(), valid_evidence_ids=EVIDENCE_IDS)
    doc = emit_scenario(graph, stock_bindings(graph, same=True), QUESTION)
    starting, measured = _quantity_names(doc)
    # one substance: the opening balance, the measured total and the
    # delivery all speak of the same runtime quantity
    assert measured in starting
    (ev,) = doc["scheduled_events"]
    (eff,) = [e for e in ev["effects"]
              if e["change_type"] == "transfer_resource"]
    assert eff["quantity"] == measured


def test_binder_denied_identity_keeps_the_stocks_apart():
    graph, _ = assemble(*stock_docs(), valid_evidence_ids=EVIDENCE_IDS)
    doc = emit_scenario(graph, stock_bindings(graph, same=False), QUESTION)
    starting, measured = _quantity_names(doc)
    assert measured not in starting
