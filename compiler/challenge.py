"""Causal challenge tests: every compiled world is red-teamed by code.

Ten checks, all deterministic, all zero-model-call. A ``fail`` blocks
execution; a ``report`` is recorded as explicitly non-material with its
reason. The checks re-derive rather than trust: ablations rebuild the
graph without a node and re-run the backward proof, so a participant or
process whose absence changes nothing is named decorative -- and one
whose absence breaks the terminal is confirmed necessary.
"""
from __future__ import annotations

from .errors import NoCausalProducer
from .graph import ACTORS, WorldGraph
from .proofs import backward_causal_proof

CHECKS = (
    "participant_ablation", "process_ablation", "route_ablation",
    "terminal_at_genesis", "report_vs_process", "causally_disconnected",
    "direct_terminal_write", "silent_uncertainty_resolution",
    "perturbation_invariance", "exact_replay",
)


def _without(graph: WorldGraph, drop: set) -> WorldGraph | None:
    """Rebuild the graph without some nodes (and their edges)."""
    d = graph.to_dict()
    d["nodes"] = [n for n in d["nodes"] if n["id"] not in drop]
    keep = {n["id"] for n in d["nodes"]}
    d["edges"] = [e for e in d["edges"]
                  if e["src"] in keep and e["dst"] in keep]
    d["uncertainties"] = [u for u in d["uncertainties"]
                          if u["about"] in keep]
    try:
        return WorldGraph.from_dict(d, graph.valid_evidence_ids)
    except Exception:
        return None


def _proof_holds(graph: WorldGraph | None) -> bool:
    if graph is None:
        return False
    try:
        backward_causal_proof(graph)
        return True
    except NoCausalProducer:
        return False


def _reaches_terminal(graph: WorldGraph, node_id: str) -> bool:
    """Forward reachability along causal edges into the measured set."""
    measured = set(graph.measured_components())
    seen, frontier = set(), [node_id]
    while frontier:
        cur = frontier.pop()
        if cur in seen:
            continue
        seen.add(cur)
        if cur in measured:
            return True
        for e in graph.edges_from(cur):
            if e.rel in ("produces", "changes", "can_perform", "sends_to",
                         "has_authority", "scheduled_at"):
                frontier.append(e.dst)
        # something that a later step requires contributes through it
        for e in graph.edges_to(cur, "requires"):
            frontier.append(e.src)
        for e in graph.edges_to(cur, "receives_from"):
            frontier.append(e.src)
        for e in graph.edges_to(cur, "knows"):
            frontier.append(e.src)
    return False


def challenge_world(graph: WorldGraph) -> dict:
    """Checks 1-9 (10, exact replay, is asserted by the runner after the
    world runs). Returns the report; raises nothing -- the caller decides
    on ``fail`` entries."""
    checks = []

    # 1. remove each participant individually
    necessary, decorative = [], []
    for cat in ACTORS:
        for n in graph.by_category(cat):
            still = _proof_holds(_without(graph, {n.id}))
            (decorative if still else necessary).append(n.name)
    checks.append({
        "id": "participant_ablation",
        "result": "report",
        "necessary_for_terminal": sorted(necessary),
        "world_survives_without": sorted(decorative),
        "note": "survival without a participant is not itself a defect "
                "(a passive holder, an operator of a scheduled event); "
                "it is named so the reviewer can judge inclusion"})

    # 2. disable each process individually
    proc = {}
    for n in graph.by_category("process"):
        proc[n.name] = "terminal unreachable without it" \
            if not _proof_holds(_without(graph, {n.id})) \
            else "terminal still producible"
    checks.append({"id": "process_ablation", "result": "report",
                   "processes": proc})

    # 3. block each information route individually
    routes = {}
    for n in graph.by_category("process"):
        if n.attrs.get("role") != "channel":
            continue
        without = _without(graph, {n.id})
        broken = []
        if without is not None:
            for act in graph.by_category("action"):
                needs_info = any(
                    graph.node(e.dst).category == "information"
                    or (graph.node(e.dst).category == "state"
                        and graph.producers_of(e.dst) == [n.id])
                    for e in graph.prerequisites_of(act.id))
                if needs_info and not _proof_holds(without):
                    broken.append(act.name)
        routes[n.name] = sorted(set(broken)) or "no action depends on it"
    checks.append({"id": "route_ablation", "result": "report",
                   "routes": routes})

    # 4 + 5 + 7: re-assert what the backward proof enforces, as invariants
    try:
        proof = backward_causal_proof(graph)
        for cid in ("terminal_at_genesis", "report_vs_process",
                    "direct_terminal_write"):
            checks.append({"id": cid, "result": "pass",
                           "enforced_by": "backward_causal_proof"})
    except NoCausalProducer as exc:
        proof = None
        for cid in ("terminal_at_genesis", "report_vs_process",
                    "direct_terminal_write"):
            checks.append({"id": cid, "result": "fail",
                           "reason": exc.reason,
                           "defects": exc.detail.get("defects", [])})

    # 6. elements with no causal path to the terminal
    disconnected = sorted(
        n.name for cat in ACTORS + ("process", "action", "event")
        for n in graph.by_category(cat)
        if not _reaches_terminal(graph, n.id))
    checks.append({
        "id": "causally_disconnected",
        "result": "report" if disconnected else "pass",
        "elements": disconnected,
        "note": "included but unable to affect the answer; the reviewer "
                "judges whether inclusion is decorative"})

    # 8. has uncertainty been silently replaced by determinism?
    exact_inferred = [
        {"event": n.name, "when": n.attrs.get("when"), "basis": n.basis}
        for n in graph.by_category("event")
        if n.attrs.get("when")
        and n.basis in ("inferred", "model_memory_unverified")]
    checks.append({
        "id": "silent_uncertainty_resolution",
        "result": "report" if (exact_inferred
                               and not graph.uncertainties) else "pass",
        "declared_uncertainties": len(graph.uncertainties),
        "exact_times_not_from_evidence": exact_inferred,
        "note": "an inferred exact time beside zero declared uncertainty "
                "is where silent resolution hides"})

    # 9. perturbation invariance: serialization round-trip is identity
    d1 = graph.to_dict()
    d2 = WorldGraph.from_dict(d1, graph.valid_evidence_ids).to_dict()
    checks.append({"id": "perturbation_invariance",
                   "result": "pass" if d1 == d2 else "fail",
                   "note": "ids and ordering are code-owned; rebuild must "
                           "be the identity"})

    failed = sorted(c["id"] for c in checks if c["result"] == "fail")
    return {"checks": checks, "failed": failed,
            "exact_replay": "asserted by the runner after execution"}
