"""The canonical world graph: closed vocabularies, code-owned IDs,
refuse-don't-guess resolution, provenance at the door, deterministic
serialization."""
import pytest

from compiler.errors import InvalidReference, SemanticAmbiguity
from compiler.graph import (GRAPH_BASES, NODE_CATEGORIES, RELATIONSHIPS,
                            WorldGraph)


def g_with(category="participant", name="Alice", basis="question_given"):
    g = WorldGraph()
    nid = g.add_node(category, name, "a test node", basis)
    return g, nid


def test_vocabularies_are_exactly_the_directive_set():
    assert NODE_CATEGORIES == (
        "participant", "organization", "population", "process", "state",
        "information", "event", "action", "record", "resource", "terminal")
    assert RELATIONSHIPS == (
        "knows", "has_state", "has_authority", "can_perform", "requires",
        "produces", "changes", "sends_to", "receives_from", "observes",
        "scheduled_at", "constrains", "measured_by_terminal")
    assert GRAPH_BASES == ("verified", "inferred", "question_given",
                          "model_memory_unverified", "uncertain")


def test_unknown_category_and_relationship_are_refused():
    g = WorldGraph()
    with pytest.raises(ValueError, match="unknown node category"):
        g.add_node("committee", "Ethics Board", "", "question_given")
    g2, a = g_with()
    b = g2.add_node("action", "vote", "", "question_given")
    with pytest.raises(ValueError, match="unknown relationship"):
        g2.add_edge(a, "votes_on", b)


def test_relation_domains_are_enforced():
    g, alice = g_with()
    bob = g.add_node("participant", "Bob", "", "question_given")
    with pytest.raises(SemanticAmbiguity, match="cannot connect"):
        g.add_edge(alice, "knows", bob)          # knows is about information
    act = g.add_node("action", "reply", "", "question_given")
    ch = g.add_node("process", "email", "", "question_given")
    with pytest.raises(SemanticAmbiguity, match="cannot connect"):
        g.add_edge(ch, "can_perform", act)        # a process cannot decide
    g.add_edge(alice, "can_perform", act)         # an actor can


def test_duplicate_names_are_ambiguous_not_renumbered():
    g, _ = g_with()
    with pytest.raises(SemanticAmbiguity, match="share the name"):
        g.add_node("participant", "Alice", "", "question_given")
    # same name in a different category is a different thing
    g.add_node("information", "Alice", "a dossier about her",
               "question_given")


def test_near_miss_resolution_refuses_with_did_you_mean():
    g, _ = g_with(name="Alice Chen")
    with pytest.raises(InvalidReference, match="did you mean"):
        g.resolve("participant", "Alice Che", "test")


def test_resolve_any_demands_a_unique_match():
    g, _ = g_with(name="processing")
    g.add_node("process", "processing", "", "question_given")
    with pytest.raises(SemanticAmbiguity, match="more than one"):
        g.resolve_any(("participant", "process"), "processing", "test")
    with pytest.raises(InvalidReference, match="nothing named"):
        g.resolve_any(("participant", "process"), "ghost", "test")


def test_provenance_is_checked_at_the_door():
    g = WorldGraph()
    with pytest.raises(SemanticAmbiguity, match="basis must be one of"):
        g.add_node("participant", "A", "", "probably")
    with pytest.raises(SemanticAmbiguity, match="cites no evidence_ids"):
        g.add_node("participant", "B", "", "verified")
    g2 = WorldGraph(valid_evidence_ids={"e1"})
    with pytest.raises(SemanticAmbiguity, match="do not exist"):
        g2.add_node("participant", "C", "", "verified",
                    evidence_ids=["e404"])
    g2.add_node("participant", "D", "", "verified", evidence_ids=["e1"])


def test_requires_necessity_is_validated():
    g = WorldGraph()
    act = g.add_node("action", "sign", "", "question_given")
    st = g.add_node("state", "draft exists", "", "question_given")
    with pytest.raises(ValueError, match="necessity"):
        g.add_edge(act, "requires", st, {"necessity": "maybe"})
    with pytest.raises(ValueError, match="alt_group"):
        g.add_edge(act, "requires", st, {"necessity": "alternative"})


def test_edges_are_idempotent():
    g = WorldGraph()
    act = g.add_node("action", "sign", "", "question_given")
    st = g.add_node("state", "draft exists", "", "question_given")
    g.add_edge(act, "requires", st)
    g.add_edge(act, "requires", st)
    assert len(g.edges) == 1


def test_exactly_one_terminal():
    g = WorldGraph()
    with pytest.raises(SemanticAmbiguity, match="exactly one terminal"):
        g.terminal()
    g.add_node("terminal", "terminal", "", "question_given")
    assert g.terminal().category == "terminal"


def test_excluded_things_cannot_also_exist():
    g, _ = g_with(name="Elena Cruz")
    with pytest.raises(SemanticAmbiguity, match="one or the other"):
        g.add_exclusion("Elena Cruz", "she has no effect", "question_given")
    g.add_exclusion("The city council", "not involved before the cutoff",
                    "question_given")
    assert g.exclusions[0]["name"] == "The city council"


def test_uncertainty_must_be_about_something_real():
    g, nid = g_with()
    g.add_uncertainty(nid, "whether she is available")
    with pytest.raises(InvalidReference):
        g.add_uncertainty("participant:ghost", "about nothing")


def test_serialization_round_trips_and_is_deterministic():
    g = WorldGraph(valid_evidence_ids={"e1"})
    a = g.add_node("participant", "Alice", "asker", "verified", ["e1"])
    act = g.add_node("action", "send request", "she can ask",
                     "question_given")
    g.add_edge(a, "can_perform", act)
    g.add_uncertainty(act, "she may not bother")
    g.add_exclusion("Bob's dog", "does not read email", "question_given")
    d1 = g.to_dict()
    g2 = WorldGraph.from_dict(d1, valid_evidence_ids={"e1"})
    assert g2.to_dict() == d1
    assert d1["nodes"] == sorted(d1["nodes"], key=lambda n: n["id"])


def test_from_dict_re_validates():
    g, _ = g_with()
    d = g.to_dict()
    d["nodes"][0]["provenance"]["basis"] = "probably"
    with pytest.raises(SemanticAmbiguity, match="basis must be one of"):
        WorldGraph.from_dict(d)


def test_removed_names_leave_the_symbol_table():
    """A removed node vanishes entirely: the serialized table names only
    the live world, rebuild is the identity, and the freed name and id
    behave exactly as if never registered."""
    import json

    g = WorldGraph()
    keep = g.add_node("process", "line assembly", "kept", "question_given")
    gone = g.add_node("process", "courier service", "pruned",
                      "question_given")
    g.remove_node(gone)
    d1 = g.to_dict()
    assert "courier service" not in json.dumps(d1)
    assert WorldGraph.from_dict(d1).to_dict() == d1
    # re-registration mints the original id, not a removal-history suffix
    again = g.add_node("process", "courier service", "back",
                       "question_given")
    assert again == gone
    assert g.maybe("process", "line assembly") == keep
