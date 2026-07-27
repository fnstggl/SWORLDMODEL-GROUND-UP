"""Backward causal proof and forward executability proof.

The positive case is the assembled toy world; the negative cases are the
audit's real failure shapes: unsupported steps, answers written by inferred
schedules, terminals satisfied at genesis, worlds where nothing is
scheduled, unreachable information, uncovered authority."""
import pytest

from compiler.assemble import assemble
from compiler.errors import (InvalidReference, NoCausalProducer,
                             NothingScheduled)
from compiler.graph import WorldGraph
from compiler.proofs import backward_causal_proof, forward_executability_proof
from tests.fixtures_discovery import EVIDENCE_IDS, docs


def build(mutate=None):
    parts = docs()
    if mutate:
        mutate(*parts)
    return assemble(*parts, valid_evidence_ids=EVIDENCE_IDS)


# ---------------------------------------------------------------------------
# backward
# ---------------------------------------------------------------------------

def test_backward_proof_roots_every_component():
    graph, _ = build()
    proof = backward_causal_proof(graph)
    (comp,) = proof["components"]
    assert comp["component"] == "state:alice_has_read_bobs_confirmation"
    assert comp["chain"]["via"]["root"] == "actor_choice"
    assert proof["genesis_only_components"] == []


def test_unsupported_step_fails_the_proof_with_its_own_words():
    def mutate(res, spine, prod, state, unc):
        prod["assignments"][2] = {
            "step": "bob sends a confirmation",
            "unsupported": "no evidence Bob answers this inbox himself"}
        # with his only step unsupported, Bob is no longer a producer and
        # the starting-state document has nothing to say about him
        del state["entities"][1]
    graph, _ = build(mutate)
    with pytest.raises(NoCausalProducer) as ei:
        backward_causal_proof(graph)
    assert "no evidence Bob answers" in " ".join(
        ei.value.detail["defects"])


def test_an_inferred_schedule_may_not_write_the_answer():
    """The unseen case's shape: the model composes intervals, lands 22
    minutes inside the deadline, and serializes its own conclusion as a
    scheduled event that creates the terminal record."""
    def mutate(res, spine, prod, state, unc):
        res["proof"] = [{"kind": "record", "name": "all fast record",
                         "record_type": "all_fast",
                         "meaning": "the pilots' all-fast log entry"}]
        spine["steps"] = [
            {"name": "arrival completes", "kind": "scheduled_event",
             "meaning": "ship all fast at 23:37, per composed intervals",
             "when": "2026-08-13T23:37:00",
             "produces_proof": ["all fast record"],
             "basis": "inferred", "evidence_ids": ["e1"]}]
        prod["assignments"] = []
        state["entities"] = []
        unc["uncertainties"] = []
        unc["exclusions"] = []
    graph, _ = build(mutate)
    with pytest.raises(NoCausalProducer) as ei:
        backward_causal_proof(graph)
    assert any("must be simulated" in d
               for d in ei.value.detail["defects"])


def test_a_verified_timetable_may():
    """An evidenced commitment (a published shipment schedule) is a real
    basis for a scheduled event, even one the terminal measures."""
    def mutate(res, spine, prod, state, unc):
        res["answer_type"] = "quantity"
        res["proof"] = [{"kind": "quantity", "name": "units delivered",
                         "unit": "units", "holder": "the hospital",
                         "meaning": "usable units received"}]
        spine["steps"] = [
            {"name": "tuesday shipment", "kind": "scheduled_event",
             "meaning": "the standing Tuesday 16:00 dispatch of 150 units",
             "when": "2026-07-21T16:00:00",
             "produces_proof": ["units delivered"],
             "basis": "verified", "evidence_ids": ["e1"]}]
        prod["assignments"] = []
        state["entities"] = [
            {"name": "the hospital",
             "initial_state": [
                 {"name": "hospital operating normally",
                  "meaning": "receiving as usual",
                  "basis": "question_given"}]}]
        unc["uncertainties"] = []
        unc["exclusions"] = []
    graph, _ = build(mutate)
    # the passive holder was materialized from the resolution contract
    assert graph.maybe("organization", "the hospital")
    proof = backward_causal_proof(graph)
    assert proof["components"][0]["chain"]["via"]["root"] == \
        "scheduled_event"


def test_genesis_must_not_satisfy_a_boolean_terminal():
    def mutate(res, spine, prod, state, unc):
        spine["steps"].append(
            {"name": "alice has read bobs confirmation",
             "kind": "initial_fact",
             "meaning": "asserting the outcome already true",
             "basis": "question_given"})
    graph, _ = build(mutate)
    with pytest.raises(NoCausalProducer,
                       match="initialization itself satisfies"):
        backward_causal_proof(graph)


def test_direct_terminal_write_requires_the_measured_act():
    """The merger shape: one invented affordance with no prerequisites
    that writes the measured record."""
    def mutate(res, spine, prod, state, unc):
        res["proof"] = [{"kind": "record", "name": "board approval",
                         "record_type": "approval",
                         "meaning": "the board's recorded approval"}]
        spine["steps"] = [
            {"name": "record board approval", "kind": "actor_decision",
             "meaning": "the board can record an approval",
             "produces_proof": ["board approval"],
             "basis": "uncertain", "evidence_ids": []}]
        prod["assignments"] = [
            {"step": "record board approval",
             "producers": [{"name": "the board", "kind": "organization",
                            "meaning": "the acquiring board",
                            "basis": "inferred", "evidence_ids": ["e1"]}]}]
        state["entities"] = []
        unc["uncertainties"] = []
        unc["exclusions"] = []
    graph, _ = build(mutate)
    with pytest.raises(NoCausalProducer) as ei:
        backward_causal_proof(graph)
    assert any("write the answer directly" in d
               for d in ei.value.detail["defects"])
    # ...but a vote IS the vote record: naming it as the measured act is
    # legitimate, provided the act has real prerequisites elsewhere.
    def mutate2(res, spine, prod, state, unc):
        mutate(res, spine, prod, state, unc)
        res["measured_act"] = "record board approval"
    graph2, _ = build(mutate2)
    proof = backward_causal_proof(graph2)
    assert proof["components"][0]["producers"] == \
        ["action:record_board_approval"]


def test_uncertain_roots_are_reported_for_the_unresolved_path():
    def mutate(res, spine, prod, state, unc):
        spine["steps"][2]["kind"] = "uncertain_exogenous"
        spine["steps"][2]["basis"] = "uncertain"
        # an uncertain exogenous event has no producer: it may simply occur
        del prod["assignments"][2]
        # Bob is then no producer at all; his boundary has nothing to say
        del state["entities"][1]
    graph, _ = build(mutate)
    proof = backward_causal_proof(graph)
    assert proof["components_rooted_in_uncertainty"] == \
        ["state:alice_has_read_bobs_confirmation"]


# ---------------------------------------------------------------------------
# forward
# ---------------------------------------------------------------------------

def test_forward_proof_finds_roots_channels_and_info_paths():
    graph, _ = build()
    proof = forward_executability_proof(graph)
    assert proof["scheduled_roots"] == ["event:alice_workday_starts"]
    (ch,) = proof["channels"]
    assert set(ch["senders"]) == {"participant:alice_chen",
                                  "participant:bob_marsh"}
    assert proof["emergent_components"] == \
        ["state:alice_has_read_bobs_confirmation"]


def test_a_world_with_nothing_scheduled_is_refused():
    def mutate(res, spine, prod, state, unc):
        state["entities"][0].pop("commitments")
    graph, _ = build(mutate)
    with pytest.raises(NothingScheduled, match="never advance"):
        forward_executability_proof(graph)


def test_authority_must_cover_a_performer():
    def mutate(res, spine, prod, state, unc):
        state["entities"][1]["authority"] = [
            {"over": "alice reads the confirmation",
             "meaning": "only Bob may authorize reading (a broken world)",
             "basis": "question_given"}]
    graph, _ = build(mutate)
    with pytest.raises(InvalidReference) as ei:
        forward_executability_proof(graph)
    assert any("nobody authorized" in d
               for d in ei.value.detail["defects"])


def test_required_information_must_be_reachable():
    """An actor whose action needs information they can never receive."""
    g = WorldGraph()
    g.add_node("terminal", "terminal", "", "question_given",
               attrs={"answer_type": "boolean"})
    outcome = g.add_node("state", "deal closed", "", "question_given")
    g.add_edge(outcome, "measured_by_terminal", "terminal:terminal")
    p = g.add_node("participant", "Dana", "", "question_given")
    q = g.add_node("participant", "Eli", "", "question_given")
    act = g.add_node("action", "counter-sign", "", "question_given")
    g.add_edge(p, "can_perform", act)
    g.add_edge(act, "produces", outcome)
    info = g.add_node("information", "the signed draft", "",
                      "question_given")
    g.add_edge(act, "requires", info)
    send = g.add_node("action", "circulate draft", "", "question_given")
    g.add_edge(q, "can_perform", send)
    g.add_edge(send, "produces", info)
    g.add_node("event", "closing day", "", "question_given",
               attrs={"when": "2026-05-01T09:00:00"})
    with pytest.raises(InvalidReference) as ei:
        forward_executability_proof(g)
    assert any("locally available" in d
               for d in ei.value.detail["defects"])
    # give Dana a channel Eli can send on and the same world executes
    ch = g.add_node("process", "courier", "", "question_given",
                    attrs={"role": "channel"})
    g.add_edge(p, "receives_from", ch)
    g.add_edge(q, "sends_to", ch)
    proof = forward_executability_proof(g)
    assert proof["information_paths"][0]["how"] == "via process:courier"


def test_dead_routes_are_reported():
    def mutate(res, spine, prod, state, unc):
        state["entities"][0]["channels"][0]["role"] = "sender"
        state["entities"][1]["channels"][0]["role"] = "sender"
        state["entities"][1].pop("not_available")
    graph, _ = build(mutate)
    proof = forward_executability_proof(graph)
    assert any("dead" in w for w in proof["warnings"])


def test_threshold_of_optional_contributions_roots_through_its_parts():
    """'At least 3 of 5 vote yes' -- every part optional, none necessary.
    The condition roots iff some contribution can actually happen; the
    tally itself is the simulation's outcome."""
    from compiler.graph import WorldGraph
    from compiler.proofs import _Rootedness

    g = WorldGraph()
    voter = g.add_node("participant", "Ada", "a voter", "question_given")
    vote = g.add_node("action", "ada votes yes", "casts a yes vote",
                      "question_given")
    g.add_edge(voter, "can_perform", vote)
    cond = g.add_node("state", "enough yes votes",
                      "at least three of five vote yes",
                      "question_given",
                      attrs={"conjunction": True})
    g.add_edge(cond, "requires", vote, {"necessity": "optional"})
    r = _Rootedness(g)
    tree = r.rooted(cond)
    assert tree is not None
    assert tree.get("threshold_of") == [vote]

    # with no performable contribution the threshold cannot come about,
    # and the reasons surface the part, not the marker
    g2 = WorldGraph()
    v2 = g2.add_node("action", "ada votes yes", "casts a yes vote",
                     "question_given")
    c2 = g2.add_node("state", "enough yes votes",
                     "at least three of five vote yes", "question_given",
                     attrs={"conjunction": True,
                            "unsupported": "conjunction of prerequisites"})
    g2.add_edge(c2, "requires", v2, {"necessity": "optional"})
    r2 = _Rootedness(g2)
    assert r2.rooted(c2) is None
    reasons = r2.why_not(c2)
    assert any("nobody can_perform" in x for x in reasons)


def test_an_orphan_measured_record_teaches_produces_proof_and_routes():
    from compiler.graph import WorldGraph
    from compiler.proofs import backward_causal_proof
    from compiler.errors import NoCausalProducer

    g = WorldGraph()
    g.add_node("terminal", "terminal", "how many voted yes",
               "question_given", attrs={"answer_type": "quantity",
                                        "cutoff": {"when": "x"}})
    rec = g.add_node("record", "vote record", "cast votes on record",
                     "question_given", attrs={"record_type": "vote"})
    g.add_edge(rec, "measured_by_terminal", "terminal:terminal")
    with pytest.raises(NoCausalProducer) as ei:
        backward_causal_proof(g)
    (defect,) = ei.value.detail["defects"]
    assert "produces_proof" in defect
    assert ei.value.detail["document"] == "causal_spine"


def test_population_held_authority_covers_individual_performers():
    from compiler.graph import WorldGraph
    from compiler.proofs import forward_executability_proof

    g = WorldGraph()
    g.add_node("terminal", "terminal", "is it adopted", "question_given",
               attrs={"answer_type": "boolean", "cutoff": {"when": "x"}})
    body = g.add_node("population", "council members", "the collective",
                      "question_given")
    ada = g.add_node("participant", "Ada Lin", "a member",
                     "question_given")
    ev = g.add_node("event", "session opens", "the session",
                    "question_given",
                    attrs={"when": "2026-09-08T19:00:00-04:00"})
    act = g.add_node("action", "bring about: vote taken",
                     "moves the vote", "question_given")
    st = g.add_node("state", "vote taken", "the vote happened",
                    "question_given")
    g.add_edge(st, "measured_by_terminal", "terminal:terminal")
    g.add_edge(act, "produces", st)
    g.add_edge(ada, "can_perform", act)
    g.add_edge(body, "has_authority", act)
    forward_executability_proof(g)      # collective authority: no block


def test_counted_records_accept_prerequisite_free_contributions():
    """Each cast vote writes one entry of a counted record; the tally is
    the terminal's own arithmetic, so no single act writes THE answer."""
    from compiler.graph import WorldGraph
    from compiler.proofs import backward_causal_proof

    g = WorldGraph()
    g.add_node("terminal", "terminal", "how many vote yes",
               "question_given", attrs={"answer_type": "quantity",
                                        "cutoff": {"when": "x"}})
    rec = g.add_node("record", "vote record", "votes on record",
                     "question_given",
                     attrs={"record_type": "vote", "rule": "count_value",
                            "value": "yes"})
    g.add_edge(rec, "measured_by_terminal", "terminal:terminal")
    ada = g.add_node("participant", "Ada Lin", "a member",
                     "question_given")
    act = g.add_node("action", "ada votes yes", "casts a yes vote",
                     "question_given")
    g.add_edge(ada, "can_perform", act)
    g.add_edge(act, "produces", rec)
    backward_causal_proof(g)          # no direct-write refusal
