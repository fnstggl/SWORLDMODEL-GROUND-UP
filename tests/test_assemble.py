"""Deterministic assembly: discovery documents in, canonical graph out.
Same documents, same graph; defects reported per document, all at once."""
import pytest

from compiler.assemble import assemble
from compiler.errors import SemanticAmbiguity
from tests.fixtures_discovery import EVIDENCE_IDS, docs


def build():
    return assemble(*docs(), valid_evidence_ids=EVIDENCE_IDS)


def test_toy_world_assembles():
    graph, trace = build()
    assert graph.terminal().attrs["answer_type"] == "boolean"
    assert graph.measured_components() == \
        ["state:alice_has_read_bobs_confirmation"]
    assert {n.name for n in graph.by_category("participant")} == \
        {"Alice Chen", "Bob Marsh"}
    ops = [t["op"] for t in trace]
    assert ops[0] == "define_outcome" and ops[-1] == "finish"


def test_actor_decisions_are_actions_nobody_can_schedule():
    graph, _ = build()
    reply = graph.resolve("action", "bob sends a confirmation", "test")
    assert graph.performers_of(reply) == ["participant:bob_marsh"]
    # no event or schedule produces the action itself
    assert graph.producers_of(reply) == []


def test_the_spine_is_dependencies_not_a_trajectory():
    """The reply requires the request to have been seen; nothing anywhere
    says the reply WILL happen."""
    graph, _ = build()
    reply = graph.resolve("action", "bob sends a confirmation", "test")
    needs = [e.dst for e in graph.prerequisites_of(reply)]
    assert needs == ["state:bob_has_seen_alices_request"]
    assert any(u["about"] == reply for u in graph.uncertainties)


def test_denied_access_is_structure_not_prose():
    """The audit's D8: 'no email access' must land where execution reads."""
    graph, _ = build()
    bob = graph.resolve("participant", "Bob Marsh", "test")
    (edge,) = [e for e in graph.edges_from(bob, "receives_from")]
    blocked = edge.attrs["attention"]["blocked"]
    assert blocked and blocked[0]["from"] == "2026-03-04T00:00:00"


def test_assembly_is_deterministic_and_order_insensitive():
    g1, t1 = build()
    g2, _ = build()
    assert g1.to_dict() == g2.to_dict()
    res, spine, prod, state, unc = docs()
    state["entities"].reverse()
    prod["assignments"].reverse()
    g3, _ = assemble(res, spine, prod, state, unc,
                     valid_evidence_ids=EVIDENCE_IDS)
    d1, d3 = g1.to_dict(), g3.to_dict()
    assert d1["nodes"] == d3["nodes"] and d1["edges"] == d3["edges"]


def test_condition_step_binds_to_proof_component_instead_of_duplicating():
    res, spine, prod, state, unc = docs()
    spine["steps"].append(
        {"name": "alice has read bobs confirmation", "kind": "condition",
         "meaning": "the measured outcome itself",
         "basis": "question_given"})
    g, _ = assemble(res, spine, prod, state, unc,
                    valid_evidence_ids=EVIDENCE_IDS)
    assert len([n for n in g.by_category("state")
                if n.name == "alice has read bobs confirmation"]) == 1


def test_a_happening_cannot_bind_to_the_measured_component():
    res, spine, prod, state, unc = docs()
    spine["steps"].append(
        {"name": "alice has read bobs confirmation",
         "kind": "actor_decision",
         "meaning": "collapsing act and outcome into one node",
         "basis": "uncertain"})
    with pytest.raises(SemanticAmbiguity) as ei:
        assemble(res, spine, prod, state, unc,
                 valid_evidence_ids=EVIDENCE_IDS)
    assert any("separate step" in d for d in ei.value.detail["defects"])


def test_process_producer_for_a_decision_is_refused():
    res, spine, prod, state, unc = docs()
    prod["assignments"][2]["producers"] = [
        {"name": "work email", "kind": "communication_system",
         "meaning": "", "basis": "verified", "evidence_ids": ["e2"]}]
    with pytest.raises(SemanticAmbiguity) as ei:
        assemble(res, spine, prod, state, unc,
                 valid_evidence_ids=EVIDENCE_IDS)
    assert any("cannot decide" in d for d in ei.value.detail["defects"])


def test_steps_without_producers_are_refused_together():
    res, spine, prod, state, unc = docs()
    prod["assignments"] = prod["assignments"][:1]
    with pytest.raises(SemanticAmbiguity) as ei:
        assemble(res, spine, prod, state, unc,
                 valid_evidence_ids=EVIDENCE_IDS)
    defects = ei.value.detail["defects"]
    assert ei.value.detail["document"] == "producer_assignments"
    assert len(defects) >= 3          # seen-request, reply, availability...
    assert ei.value.detail["repairable"] is True


def test_person_producing_a_condition_gets_a_derived_action():
    res, spine, prod, state, unc = docs()
    prod["assignments"][1]["producers"] = [
        {"name": "Bob Marsh", "kind": "person",
         "meaning": "Bob notices things himself.",
         "basis": "inferred", "evidence_ids": ["e2"]}]
    g, _ = assemble(res, spine, prod, state, unc,
                    valid_evidence_ids=EVIDENCE_IDS)
    derived = g.resolve("action", "bring about: bob has seen alices request",
                        "test")
    assert g.performers_of(derived) == ["participant:bob_marsh"]
    assert "state:bob_has_seen_alices_request" in [
        e.dst for e in g.edges_from(derived, "produces")]


def test_initial_facts_cannot_have_prerequisites():
    res, spine, prod, state, unc = docs()
    spine["steps"][0] = {
        "name": "alice sends the request", "kind": "initial_fact",
        "meaning": "pretending the act already happened",
        "prerequisites": [{"step": "bob sends a confirmation"}],
        "basis": "question_given"}
    with pytest.raises(SemanticAmbiguity) as ei:
        assemble(res, spine, prod, state, unc,
                 valid_evidence_ids=EVIDENCE_IDS)
    assert any("already true at genesis" in d
               for d in ei.value.detail["defects"])


def test_declared_ambiguities_stop_assembly():
    res, spine, prod, state, unc = docs()
    res["ambiguities"] = ["'read' could mean opened or fully read"]
    with pytest.raises(SemanticAmbiguity) as ei:
        assemble(res, spine, prod, state, unc,
                 valid_evidence_ids=EVIDENCE_IDS)
    assert any("must stop compilation" in d
               for d in ei.value.detail["defects"])


def test_defects_are_reported_per_document_all_at_once():
    res, spine, prod, state, unc = docs()
    spine["steps"][0]["basis"] = "probably"
    spine["steps"][2]["kind"] = "decision"
    with pytest.raises(SemanticAmbiguity) as ei:
        assemble(res, spine, prod, state, unc,
                 valid_evidence_ids=EVIDENCE_IDS)
    joined = " ".join(ei.value.detail["defects"])
    assert "probably" in joined and "decision" in joined
    assert ei.value.detail["document"] == "causal_spine"


def test_unknown_uncertainty_subject_is_refused():
    res, spine, prod, state, unc = docs()
    unc["uncertainties"].append({"about": "the weather",
                                 "meaning": "storms may intervene"})
    with pytest.raises(SemanticAmbiguity, match="uncertainty_and_exclusions"):
        assemble(res, spine, prod, state, unc,
                 valid_evidence_ids=EVIDENCE_IDS)


def test_excluding_an_included_thing_is_refused():
    res, spine, prod, state, unc = docs()
    unc["exclusions"].append({"name": "Bob Marsh",
                              "why_safe": "surely irrelevant",
                              "basis": "question_given"})
    with pytest.raises(SemanticAmbiguity):
        assemble(res, spine, prod, state, unc,
                 valid_evidence_ids=EVIDENCE_IDS)


def test_process_behavior_lands_on_the_process_node():
    res, spine, prod, state, unc = docs()
    state["entities"].append(
        {"name": "work email",
         "process_behavior": {
             "meaning": "the mail system runs continuously",
             "rate_meaning": "delivery within about a minute",
             "operating_meaning": "always on",
             "basis": "verified", "evidence_ids": ["e2"]}})
    g, _ = assemble(res, spine, prod, state, unc,
                    valid_evidence_ids=EVIDENCE_IDS)
    ch = g.node(g.resolve("process", "work email", "test"))
    assert ch.attrs["operating_meaning"] == "always on"


def test_trace_records_every_operation_with_its_results():
    _, trace = build()
    producers = [t for t in trace if t["op"] == "attach_producer"]
    assert any(t["created"] for t in producers)      # Alice created once
    assert all(t["edges"] for t in producers)        # every attach connects
    boundary = [t for t in trace
                if t["op"] == "add_information_boundary"]
    assert len(boundary) == 2
