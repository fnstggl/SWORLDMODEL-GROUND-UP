"""Causal challenge tests: ablations must actually bite."""
from compiler.assemble import assemble
from compiler.challenge import challenge_world
from compiler.proofs import backward_causal_proof
from tests.fixtures_discovery import EVIDENCE_IDS, docs


def build(mutate=None):
    parts = docs()
    if mutate:
        mutate(*parts)
    return assemble(*parts, valid_evidence_ids=EVIDENCE_IDS)[0]


def test_removing_a_load_bearing_actor_breaks_the_terminal():
    graph = build()
    report = challenge_world(graph)
    (pa,) = [c for c in report["checks"]
             if c["id"] == "participant_ablation"]
    assert "Bob Marsh" in pa["necessary_for_terminal"]
    assert "Alice Chen" in pa["necessary_for_terminal"]


def test_blocking_the_only_route_breaks_dependent_actions():
    graph = build()
    report = challenge_world(graph)
    (ra,) = [c for c in report["checks"] if c["id"] == "route_ablation"]
    assert ra["routes"]["work email"] != "no action depends on it"
    assert "bob sends a confirmation" in ra["routes"]["work email"]


def test_ablation_is_not_fooled_by_accidental_conjunctions():
    """Stripping a real producer must break the proof; only an EXPLICIT
    conjunction may root through its prerequisites."""
    graph = build()
    d = graph.to_dict()
    ch = graph.resolve("process", "work email", "test")
    d["nodes"] = [n for n in d["nodes"] if n["id"] != ch]
    d["edges"] = [e for e in d["edges"] if ch not in (e["src"], e["dst"])]
    from compiler.errors import NoCausalProducer
    from compiler.graph import WorldGraph
    import pytest
    with pytest.raises(NoCausalProducer):
        backward_causal_proof(WorldGraph.from_dict(d, EVIDENCE_IDS))


def test_an_explicit_conjunction_roots_through_its_parts():
    def mutate(res, spine, prod, state, unc):
        spine["steps"].insert(4, {
            "name": "the exchange is complete", "kind": "condition",
            "meaning": "both messages have been delivered",
            "prerequisites": [
                {"step": "bob has seen alices request"},
                {"step": "bobs confirmation available to alice"}],
            "basis": "inferred", "evidence_ids": ["e2"]})
        prod["assignments"].append({
            "step": "the exchange is complete",
            "unsupported": "a conjunction of its parts; no mechanism of "
                           "its own"})
    graph = build(mutate)
    node = graph.node(graph.resolve("state", "the exchange is complete",
                                    "test"))
    assert node.attrs.get("no_producer_needed")
    backward_causal_proof(graph)          # roots fine through the parts


def test_invariants_and_identity_pass_on_a_sound_world():
    report = challenge_world(build())
    by_id = {c["id"]: c for c in report["checks"]}
    assert by_id["terminal_at_genesis"]["result"] == "pass"
    assert by_id["direct_terminal_write"]["result"] == "pass"
    assert by_id["perturbation_invariance"]["result"] == "pass"
    assert report["failed"] == []
