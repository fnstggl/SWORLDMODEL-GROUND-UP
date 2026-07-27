"""Semantic round-trip verification.

After lowering, the runtime world is deterministically rendered back into
a human-readable description -- who and what exists, initial state,
information boundaries, scheduled roots, affordances, process behaviour,
and the terminal observation -- and an independent reviewer compares it
against the same rendering of the approved canonical graph. A world whose
lowered meaning is materially different from its approved meaning must
not run.

The renderings are code, deterministic and total: every actor, rule,
event, action and observation appears, so the reviewer sees the compiled
truth rather than a summary of intentions. This is the check that catches
the audit's D8 class -- prose saying "no email access" beside structure
meaning "continuously attentive" -- because only structure is rendered.
"""
from __future__ import annotations

import json

from .errors import LoweringMismatch
from .graph import ACTORS, WorldGraph
from .llm import TruncatedResponse, call_json

VERDICTS = ("EQUIVALENT", "MEANING_CHANGED", "MATERIAL_OMISSION",
            "UNSUPPORTED_ADDITION")


def _j(x) -> str:
    return json.dumps(x, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# the approved side: the canonical graph, rendered
# ---------------------------------------------------------------------------

def describe_graph(graph: WorldGraph, question: dict,
                   bindings=None) -> str:
    def bound(kind, node_id):
        if bindings is None:
            return {}
        return getattr(bindings, kind, {}).get(node_id) or {}

    out = ["# Approved causal world (canonical graph)",
           f"\nQUESTION: {question.get('question', '')}",
           "\nStocks are mutable ledger quantities: processes accrue into "
           "them and transfers move them, deducting the source and "
           "crediting the destination atomically. The runtime enforces "
           "this conservation itself."]
    term = graph.terminal()
    out.append(f"\n## Terminal\n- {term.meaning}")
    out.append(f"- answer_type: {term.attrs.get('answer_type')}; cutoff: "
               f"{_j(term.attrs.get('cutoff'))}")
    out.append(f"- positive: {term.attrs.get('positive_condition')}")
    if term.attrs.get("negative_condition"):
        out.append(f"- negative: {term.attrs.get('negative_condition')}")
    for cid in graph.measured_components():
        n = graph.node(cid)
        out.append(f"- measured: {n.name} ({n.category}) -- {n.meaning} "
                   f"[{_j({k: v for k, v in n.attrs.items() if v is not None})}]")
        producers = graph.producers_of(cid)
        if producers:
            out.append(f"  producible by: "
                       f"{', '.join(graph.node(p).name for p in producers)}")
        if n.category == "resource":
            holder = n.attrs.get("holder")
            for rs in graph.by_category("resource"):
                if rs.id != cid and rs.attrs.get("holder") == holder \
                        and rs.attrs.get("amount") is not None:
                    out.append(
                        f"  opening stock counted: {rs.attrs['amount']} "
                        f"{rs.attrs.get('unit') or ''} already held by "
                        f"{graph.node(holder).name if holder else '?'} "
                        f"(one substance; unified at lowering)")
            upstream, seen, frontier = [], set(), list(producers)
            while frontier:
                cur = frontier.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                node2 = graph.node(cur)
                if node2.category == "process" and cur not in producers:
                    upstream.append(node2.name)
                for e in graph.edges_from(cur, "requires") \
                        + graph.edges_from(cur, "scheduled_at"):
                    frontier.append(e.dst)
                for p2 in graph.producers_of(cur):
                    frontier.append(p2)
            if upstream:
                out.append(f"  fed upstream through its chain by: "
                           f"{', '.join(sorted(set(upstream)))}")

    out.append("\n## Who and what exists")
    for cat in ACTORS:
        for n in graph.by_category(cat):
            out.append(f"- {n.name} ({cat}, basis {n.basis}): {n.meaning}")
            if n.attrs.get("timezone") or n.attrs.get("availability"):
                out.append(f"  pattern: tz={n.attrs.get('timezone')}, "
                           f"availability={_j(n.attrs.get('availability'))}")
            for e in graph.edges_from(n.id, "receives_from"):
                att = e.attrs.get("attention") or {}
                out.append(f"  receives from {graph.node(e.dst).name}: "
                           f"cadence={att.get('cadence_minutes')} min, "
                           f"blocked={_j(att.get('blocked') or [])} "
                           f"({att.get('meaning', '')})")
            for e in graph.edges_from(n.id, "sends_to"):
                out.append(f"  can send on {graph.node(e.dst).name}")
            for e in graph.edges_from(n.id, "knows"):
                out.append(f"  initially knows: {graph.node(e.dst).name}")
            if n.attrs.get("not_available"):
                out.append(f"  NOT available: "
                           f"{_j(n.attrs['not_available'])}")
            if n.attrs.get("dropped_authority_claims"):
                out.append(f"  claimed authority over things no document "
                           f"declared (claims dropped): "
                           f"{_j(n.attrs['dropped_authority_claims'])}")

    out.append("\n## Initial state")
    for n in graph.by_category("state"):
        if n.attrs.get("initial"):
            out.append(f"- {n.name} = "
                       f"{n.attrs.get('value', 'true')} -- {n.meaning}")
    for n in graph.by_category("resource"):
        if n.attrs.get("amount") is not None:
            holder = n.attrs.get("holder")
            out.append(f"- {graph.node(holder).name if holder else '?'} "
                       f"holds {n.attrs['amount']} "
                       f"{n.attrs.get('unit') or ''} of {n.name}")

    out.append("\n## Channels")
    for n in graph.by_category("process"):
        if n.attrs.get("role") == "channel":
            bd = bound("channels", n.id)
            latency = (f"{bd['delivery_seconds']}s delivery"
                       if bd.get("delivery_seconds") is not None
                       else n.attrs.get("latency_meaning"))
            out.append(f"- {n.name}: {n.meaning} (latency: {latency})")

    out.append("\n## Scheduled external events")
    for n in graph.by_category("event"):
        if n.basis == "uncertain" or \
                n.attrs.get("step_kind") == "uncertain_exogenous":
            out.append(f"- UNCERTAIN, never scheduled: {n.name} -- "
                       f"{n.meaning}")
            continue
        when = n.attrs.get("when") or f"anchored: {_j(n.attrs.get('anchor'))}"
        out.append(f"- {when}: {n.name} -- {n.meaning} (basis {n.basis})")
        bd = bound("events", n.id)
        for e in graph.edges_from(n.id, "produces") \
                + graph.edges_from(n.id, "changes"):
            tgt = graph.node(e.dst)
            spec = (bd.get("amounts") or {}).get(tgt.name)
            if spec and spec.get("kind") == "transfer":
                label = tgt.attrs.get("substance") or tgt.name
                measured_note = (" -- this credits the measured stock"
                                 if tgt.id in graph.measured_components()
                                 else "")
                out.append(f"  transfers {spec.get('amount')} units of "
                           f"{label} from {spec.get('from')} to "
                           f"{spec.get('to')} (source deducted, "
                           f"destination credited{measured_note})")
            elif spec:
                out.append(f"  adjusts {tgt.name} by "
                           f"{spec.get('amount')}")
            else:
                out.append(f"  brings about: {tgt.name}")

    out.append("\n## What actors CAN do (never scheduled)")
    for n in graph.by_category("action"):
        performers = [graph.node(p).name for p in graph.performers_of(n.id)]
        out.append(f"- {n.name} (by {', '.join(performers) or 'NOBODY'}): "
                   f"{n.meaning}")
        for e in graph.prerequisites_of(n.id):
            out.append(f"  needs [{e.attrs.get('necessity')}]: "
                       f"{graph.node(e.dst).name}")
        for e in graph.edges_from(n.id, "produces") \
                + graph.edges_from(n.id, "changes"):
            out.append(f"  brings about: {graph.node(e.dst).name}")

    out.append("\n## Continuous processes")
    for n in graph.by_category("process"):
        if n.attrs.get("role") != "channel":
            bd = bound("processes", n.id)
            if bd.get("decorative"):
                out.append(f"- {n.name}: declared decorative -- "
                           f"{bd.get('why', '')}")
                continue
            rate = (f"{bd['amount_per_hour']}/hour"
                    if bd.get("amount_per_hour") is not None
                    else n.attrs.get("rate_meaning"))
            op = (_j(bd.get("operating")) if bd.get("operating")
                  else n.attrs.get("operating_meaning"))
            out.append(f"- {n.name}: {n.meaning} "
                       f"(rate: {rate}; operating: {op})")
            for e in graph.edges_from(n.id, "changes") \
                    + graph.edges_from(n.id, "produces"):
                out.append(f"  accrues into: {graph.node(e.dst).name}")

    out.append("\n## Preserved uncertainty")
    for u in sorted(graph.uncertainties,
                    key=lambda x: (x["about"] or "", x.get("topic") or "",
                                   x["meaning"])):
        about = (graph.node(u["about"]).name if u.get("about")
                 else u.get("topic", "the world"))
        out.append(f"- {about}: {u['meaning']}")
    out.append("\n## Deliberately excluded")
    for x in graph.exclusions:
        out.append(f"- {x['name']}: {x['why_safe']}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# the lowered side: the runtime world, rendered from its own state
# ---------------------------------------------------------------------------

def describe_runtime(compiled) -> str:
    snap = compiled.world.snapshot()
    spec = compiled.terminal_spec.to_dict()
    out = ["# Runtime world (reconstructed from the lowered state)"]

    out.append(f"\n## Terminal\n- question_type: {spec.get('question_type')}"
               f"; cutoff: {spec.get('cutoff')}")
    for o in (spec.get("conditions") or []) + \
            ([spec["measure"]] if spec.get("measure") else []):
        out.append(f"- observes: {_j(o)}")
    for up in spec.get("uncertain_paths") or []:
        out.append(f"- may stay unresolved: {_j(up)}")

    out.append("\n## Actors")
    for aid, a in sorted((snap.get("actors") or {}).items()):
        out.append(f"- {a.get('name', aid)} (id {aid}, role "
                   f"{a.get('role', '')}, tz {a.get('tz')})")
        for route, rule in sorted((a.get("attention") or {}).items()):
            out.append(f"  attends {route}: {_j(rule)}")
        for topic, b in sorted((a.get("beliefs") or {}).items()):
            out.append(f"  believes [{topic}]: "
                       f"{_j(b)[:180]}")

    out.append("\n## Channels")
    for name, ch in sorted((snap.get("channels") or {}).items()):
        out.append(f"- {name}: {_j(ch)}")

    out.append("\n## Facts at genesis")
    for k, v in sorted((snap.get("facts") or {}).items()):
        out.append(f"- {k} = {_j(v)}")

    out.append("\n## Quantities at genesis")
    for key, amount in sorted((snap.get("resources") or {}).items()):
        holder, _, name = str(key).partition(":")
        out.append(f"- {holder} holds {amount} of {name or key}")

    out.append("\n## Scheduled queue at genesis")
    out.append("(feasibility of each scheduled transfer -- source stock "
               "sufficiency under the evidenced rates and timings -- was "
               "verified at compile time by a deterministic stock walk: "
               "opening stock plus process accrual minus earlier outflows "
               "covers each commitment at its moment. The approving "
               "reality review saw the same numbers; the queue therefore "
               "carries the commitments unconditionally)")
    for ev in sorted(compiled.world.queue.pending(),
                     key=lambda e: (str(e.t), e.seq)):
        data = getattr(ev, "data", {}) or {}
        note = data.get("note") or data.get("reason") or ""
        ops = []
        for op in (data.get("ops") or []):
            if isinstance(op, list) and len(op) > 1 \
                    and isinstance(op[1], dict) and op[1].get("id"):
                ops.append(f"{op[0]}:{op[1]['id']}")
            elif isinstance(op, list):
                ops.append(op[0])
            else:
                ops.append(str(op))
        out.append(f"- {ev.t}: {ev.kind} {ops} {note[:140]}")

    out.append("\n## Action definitions (what actors MAY do)")
    for verb, d in sorted((snap.get("action_defs") or {}).items()):
        out.append(f"- {verb}: {d.get('description', '')[:160]}")
        for c in d.get("conditions") or []:
            out.append(f"  requires: {_j(c)}")
        for eff in d.get("effects") or []:
            out.append(f"  on completion: {_j(eff)[:220]}")
        if d.get("duration"):
            out.append(f"  duration: {_j(d['duration'])}")

    out.append("\n## Processes")
    out.append("('active' is only the state at genesis: a process with "
               "operating periods starts inactive and the scheduled "
               "'operating period begins/ends' entries in the queue above "
               "switch it on and off; its work accrues while switched on)")
    for pid, p in sorted((snap.get("processes") or {}).items()):
        out.append(f"- {pid}: {_j(p)}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# the independent comparison
# ---------------------------------------------------------------------------

_REVIEW_SYSTEM = (
    "You are an independent equivalence reviewer for a world compiler. "
    "You receive two descriptions of what should be the SAME world: the "
    "approved causal world, and the runtime world reconstructed from the "
    "compiled state. Judge whether the runtime world MEANS the same thing "
    "-- ignore naming, identifier, formatting and ordering differences, "
    "and ignore mechanical re-expression (a condition rendered as a fact "
    "check, information delivery rendered as send/notice mechanics, one "
    "shared quantity name for one substance). An evidenced standing "
    "schedule lowers as unconditional: its prerequisite edges are "
    "feasibility derivations verified at compile time by the causal "
    "proofs and the approving reality review, not runtime gates -- that "
    "is mechanical re-expression, not an omission. Report only MATERIAL "
    "differences: meaning that changed (an attention pattern inverted, a "
    "value or time altered, authority moved), something approved that is "
    "missing and would change what can happen, or something present that "
    "the approved world does not support.\n"
    "Return JSON exactly: {\"verdict\": \"EQUIVALENT\" | "
    "\"MEANING_CHANGED\" | \"MATERIAL_OMISSION\" | "
    "\"UNSUPPORTED_ADDITION\", \"findings\": [{\"what\": one sentence, "
    "\"where\": which side and section, \"material_because\": one "
    "sentence}]} -- findings empty when EQUIVALENT."
)


def review_equivalence(graph_md: str, runtime_md: str, call=call_json,
                       model: str = "deepseek-chat", log: list | None = None,
                       attempt: int = 0) -> tuple:
    """Returns (review dict, call log). Raises LoweringMismatch when the
    lowered meaning is materially different -- such a world must not run.
    Pass ``log`` to keep the verbatim call record even when the verdict
    raises; ``attempt`` numbers a re-review after a targeted rebind."""
    user = (graph_md + "\n\n=====\n\n" + runtime_md)
    if log is None:
        log = []
    try:
        doc, raw, usage = call(_REVIEW_SYSTEM, user, model=model)
    except (TruncatedResponse, ValueError) as exc:
        log.append({"step": "semantic_equivalence_review",
                    "attempt": attempt,
                    "prompt": {"system": _REVIEW_SYSTEM, "user": user},
                    "raw_response": "", "usage": {}})
        raise LoweringMismatch(
            f"the equivalence review reply was unusable: {exc}")
    log.append({"step": "semantic_equivalence_review", "attempt": attempt,
                "prompt": {"system": _REVIEW_SYSTEM, "user": user},
                "raw_response": raw, "usage": usage})
    verdict = (doc or {}).get("verdict")
    if verdict not in VERDICTS:
        raise LoweringMismatch(
            f"the equivalence review returned no usable verdict "
            f"({verdict!r})", {"raw": str(doc)[:400]})
    review = {"verdict": verdict, "findings": doc.get("findings") or []}
    if verdict != "EQUIVALENT":
        raise LoweringMismatch(
            f"the lowered world does not mean what the approved world "
            f"means ({verdict})",
            {"verdict": verdict, "findings": review["findings"],
             "repairable": False})
    return review, log
