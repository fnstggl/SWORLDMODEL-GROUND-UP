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
