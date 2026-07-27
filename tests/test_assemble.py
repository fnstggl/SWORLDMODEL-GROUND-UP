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


def test_condition_binds_via_produces_proof_under_a_different_name():
    """A condition step 'hospital holds N at deadline' declaring it
    produces the proof quantity IS the proof quantity, reworded."""
    res, spine, prod, state, unc = docs()
    spine["steps"][-1] = {
        "name": "the confirmation has been read by alice",
        "kind": "condition",
        "meaning": "the outcome, reworded",
        "produces_proof": ["alice has read bobs confirmation"],
        "prerequisites": [{"step": "bobs confirmation available to alice"}],
        "basis": "question_given"}
    prod["assignments"][-1] = {
        "step": "the confirmation has been read by alice",
        "producers": [{"name": "Alice Chen", "kind": "person",
                       "meaning": "only she can read her own mail",
                       "basis": "verified", "evidence_ids": ["e1"]}]}
    g, _ = assemble(res, spine, prod, state, unc,
                    valid_evidence_ids=EVIDENCE_IDS)
    assert len([n for n in g.by_category("state")
                if "alice has read" in n.name]) == 1


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
    # the intermediate conditions are conjunctions of their prerequisites;
    # only the two performerless actor decisions are genuine defects
    assert len(defects) == 2
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


def test_unknown_uncertainty_subject_is_kept_at_world_level():
    """An uncertainty is an annotation, never a gate: 'the weather' names
    no node, and losing the honesty over naming would be worse."""
    res, spine, prod, state, unc = docs()
    unc["uncertainties"].append({"about": "the weather",
                                 "meaning": "storms may intervene"})
    g, _ = assemble(res, spine, prod, state, unc,
                    valid_evidence_ids=EVIDENCE_IDS)
    kept = [u for u in g.uncertainties if u.get("topic") == "the weather"]
    assert kept and kept[0]["about"] is None


def test_excluding_an_included_thing_is_refused():
    res, spine, prod, state, unc = docs()
    unc["exclusions"].append({"name": "Bob Marsh",
                              "why_safe": "surely irrelevant",
                              "basis": "question_given"})
    with pytest.raises(SemanticAmbiguity):
        assemble(res, spine, prod, state, unc,
                 valid_evidence_ids=EVIDENCE_IDS)


def test_quantity_mechanisms_derive_from_the_prerequisite_chain():
    """A measured quantity whose chain reaches a dispatch event is moved
    BY that event; an actor claiming to 'produce' the quantity operates
    the mechanism instead."""
    res, spine, prod, state, unc = docs()
    res["answer_type"] = "quantity"
    res["proof"] = [{"kind": "quantity", "name": "units at the depot",
                     "holder": "the depot", "unit": "units",
                     "meaning": "stock held at the cutoff"}]
    spine["steps"] = [
        {"name": "units at the depot", "kind": "condition",
         "meaning": "the measured stock",
         # a quantity's parts are contributions, not gates: models mark
         # them optional ('whatever arrives counts') and the mechanism
         # walk must still find the dispatch
         "prerequisites": [{"step": "shipment received",
                            "necessity": "optional"}],
         "basis": "question_given"},
        {"name": "shipment received", "kind": "condition",
         "meaning": "the standing shipment has arrived",
         "prerequisites": [{"step": "tuesday dispatch"}],
         "basis": "inferred", "evidence_ids": ["e1"]},
        {"name": "tuesday dispatch", "kind": "scheduled_event",
         "meaning": "the standing 16:00 dispatch",
         "when": "2026-03-03T16:00:00-05:00",
         "basis": "verified", "evidence_ids": ["e1"]}]
    prod["assignments"] = [
        {"step": "units at the depot",
         "producers": [{"name": "Meyer Logistics", "kind": "organization",
                        "meaning": "runs the dispatches",
                        "basis": "verified", "evidence_ids": ["e1"]}]},
        {"step": "shipment received",
         "unsupported": "conjunction of its prerequisites"}]
    state["entities"] = []
    unc["uncertainties"] = []
    unc["exclusions"] = []
    g, _ = assemble(res, spine, prod, state, unc,
                    valid_evidence_ids=EVIDENCE_IDS)
    comp = g.resolve("resource", "units at the depot", "test")
    ev = g.resolve("event", "tuesday dispatch", "test")
    assert ev in g.producers_of(comp)
    meyer = g.resolve("organization", "Meyer Logistics", "test")
    assert any(e.dst == ev for e in g.edges_from(meyer, "has_authority"))
    from compiler.proofs import backward_causal_proof
    proof = backward_causal_proof(g)
    assert proof["components"][0]["chain"]["via"]["root"] == \
        "scheduled_event"


def test_process_step_with_its_own_process_producer_merges():
    res, spine, prod, state, unc = docs()
    spine["steps"].insert(0, {
        "name": "mail delivery running", "kind": "process",
        "meaning": "the mail system operates continuously",
        "basis": "inferred", "evidence_ids": ["e2"]})
    prod["assignments"].append({
        "step": "mail delivery running",
        "producers": [{"name": "mail delivery running",
                       "kind": "operating_process",
                       "meaning": "the same mechanism",
                       "basis": "inferred", "evidence_ids": ["e2"]}]})
    g, _ = assemble(res, spine, prod, state, unc,
                    valid_evidence_ids=EVIDENCE_IDS)
    assert len([n for n in g.by_category("process")
                if n.name == "mail delivery running"]) == 1
    # ...and a DIFFERENT name is the service that operates the instance
    prod["assignments"][-1]["producers"][0]["name"] = "the postal system"
    g2, _ = assemble(res, spine, prod, state, unc,
                     valid_evidence_ids=EVIDENCE_IDS)
    svc = g2.resolve("organization", "the postal system", "test")
    step = g2.resolve("process", "mail delivery running", "test")
    assert any(e.dst == step
               for e in g2.edges_from(svc, "has_authority"))


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
