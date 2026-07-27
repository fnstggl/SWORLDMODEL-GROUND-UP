"""Declarative terminal specifications: the finish line as data.

A terminal spec is plain data describing the exact observable world state
that answers the question -- so a world compiler can emit it and nobody ever
hand-writes a per-question Python evaluator.  Evaluation is mechanical, reads
only world state and the ledger, and cites the producer records
(``computed_from``) for every answer, as the engine requires.

Universal primitives only: facts, resources, information noticing, action
completion, and counts of typed fact records.  Scenario meaning ("a vote was
recorded", "the confirmation was read") is expressed by *which* keys, types
and quantities the compiler chose -- data, never code here.

Spec shape (validated by ``validate_terminal_spec``):

    {"question": str,
     "cutoff": iso instant,
     "mode": "condition" | "value" | "decision_count",
     # condition mode -- resolves "yes" the moment the condition holds:
     "condition": EXPR, "yes_means": str, "no_means": str,
     # value mode -- reports a quantity at the cutoff (or when resolve_when
     # first holds):
     "value": {"read": "resource", "holder": str, "name": str}
            | {"read": "count_facts", "prefix": str},
     # decision_count mode -- counts typed fact records by option:
     "decision": {"prefix": str, "options": [str, ...], "tie": str},
     # optional early resolution for value/decision modes:
     "resolve_when": EXPR}

    EXPR = {"all_of": [EXPR, ...]} | {"any_of": [EXPR, ...]}
         | {"check": "fact_equals", "key": str, "value": any}
         | {"check": "fact_exists", "key": str}
         | {"check": "resource_at_least", "holder": str, "name": str,
            "amount": num}
         | {"check": "information_noticed", "actor": str,
            "author"?: str, "info_type"?: str}
         | {"check": "action_completed", "verb": str, "actor"?: str}
"""
from __future__ import annotations

from .engine import Terminal
from .simclock import parse_iso

CHECK_KINDS = frozenset({
    "fact_equals", "fact_exists", "resource_at_least",
    "information_noticed", "information_sent", "action_completed",
    "count_facts_at_least",
})

MODES = frozenset({"condition", "value", "decision_count"})


class TerminalSpecError(ValueError):
    """The terminal spec is structurally invalid."""


def validate_expr(expr) -> None:
    if not isinstance(expr, dict):
        raise TerminalSpecError(f"terminal expression must be a dict, got {expr!r}")
    if "all_of" in expr or "any_of" in expr:
        key = "all_of" if "all_of" in expr else "any_of"
        kids = expr[key]
        if not isinstance(kids, list) or not kids:
            raise TerminalSpecError(f"{key} requires a non-empty list")
        for kid in kids:
            validate_expr(kid)
        return
    kind = expr.get("check")
    if kind not in CHECK_KINDS:
        raise TerminalSpecError(
            f"unknown terminal check {kind!r} (known: {sorted(CHECK_KINDS)})")
    required = {
        "fact_equals": ("key", "value"),
        "fact_exists": ("key",),
        "resource_at_least": ("holder", "name", "amount"),
        "information_noticed": ("actor",),
        "information_sent": ("author",),
        "action_completed": ("verb",),
        "count_facts_at_least": ("prefix", "amount"),
    }[kind]
    for f in required:
        if f not in expr:
            raise TerminalSpecError(f"terminal check {kind!r} requires field {f!r}")


def validate_terminal_spec(spec: dict) -> None:
    if not isinstance(spec, dict):
        raise TerminalSpecError("terminal spec must be a dict")
    if not spec.get("question"):
        raise TerminalSpecError("terminal spec requires a question")
    if not spec.get("cutoff"):
        raise TerminalSpecError("terminal spec requires a cutoff instant")
    parse_iso(spec["cutoff"])
    mode = spec.get("mode")
    if mode not in MODES:
        raise TerminalSpecError(f"terminal mode must be one of {sorted(MODES)}")
    if mode == "condition":
        if "condition" not in spec:
            raise TerminalSpecError("condition mode requires a condition")
        validate_expr(spec["condition"])
    elif mode == "value":
        v = spec.get("value")
        if not isinstance(v, dict) or v.get("read") not in ("resource", "count_facts"):
            raise TerminalSpecError(
                "value mode requires value.read of 'resource' or 'count_facts'")
        need = ("holder", "name") if v["read"] == "resource" else ("prefix",)
        for f in need:
            if not v.get(f):
                raise TerminalSpecError(f"value.read {v['read']!r} requires {f!r}")
    elif mode == "decision_count":
        d = spec.get("decision")
        if not isinstance(d, dict) or not d.get("prefix") \
                or not isinstance(d.get("options"), list) or not d["options"]:
            raise TerminalSpecError(
                "decision_count mode requires decision.prefix and decision.options")
    if "resolve_when" in spec and spec["resolve_when"] is not None:
        validate_expr(spec["resolve_when"])


# ---------------------------------------------------------------------------
# mechanical evaluation with cited producers
# ---------------------------------------------------------------------------

def _fact_producers(world, key: str) -> list:
    return [r["seq"] for r in world.records
            if r["op"] == "fact.set" and r["data"].get("key") == key]

def _resource_producers(world, holder: str, name: str) -> list:
    out = []
    for r in world.records:
        op, d = r["op"], r["data"]
        if op in ("resource.set", "resource.adjust") \
                and d.get("holder") == holder and d.get("name") == name:
            out.append(r["seq"])
        elif op == "resource.transfer" and d.get("name") == name \
                and holder in (d.get("from_holder"), d.get("to_holder")):
            out.append(r["seq"])
        elif op == "process.accrue":
            p = world.processes.get(d.get("id"))
            if p and p["holder"] == holder and p["resource"] == name:
                out.append(r["seq"])
    return out

def _noticed_matches(world, actor: str, author, info_type) -> list:
    """(seq of the info.notice record, info id) for each noticed match."""
    out = []
    for r in world.records:
        if r["op"] != "info.notice" or r["data"].get("actor") != actor:
            continue
        info = world.infos.get(r["data"]["id"])
        if info is None:
            continue
        if author is not None and info["author"] != author:
            continue
        if info_type is not None and info["data"].get("type") != info_type:
            continue
        out.append((r["seq"], info["id"]))
    return out


def _sent_matches(world, author: str, to, info_type) -> list:
    """seqs of info.send records where `author` sent (optionally to a
    specific recipient, optionally of a given type)."""
    out = []
    for r in world.records:
        if r["op"] != "info.send":
            continue
        info = world.infos.get(r["data"]["id"])
        if info is None or info["author"] != author:
            continue
        if to is not None and r["data"].get("to") != to:
            continue
        if info_type is not None and info["data"].get("type") != info_type:
            continue
        out.append(r["seq"])
    return out

def _completed_matches(world, verb: str, actor) -> list:
    out = []
    for r in world.records:
        if r["op"] != "action.state" or r["data"].get("state") != "completed":
            continue
        act = world.actions.get(r["data"].get("id"))
        if act is None or act.get("verb") != verb:
            continue
        if actor is not None and act.get("actor") != actor:
            continue
        out.append(r["seq"])
    return out


def eval_expr(world, expr) -> tuple[bool, list]:
    """Evaluate an EXPR -> (holds, producer record seqs)."""
    if "all_of" in expr:
        seqs: list = []
        for kid in expr["all_of"]:
            ok, s = eval_expr(world, kid)
            if not ok:
                return False, []
            seqs.extend(s)
        return True, seqs
    if "any_of" in expr:
        for kid in expr["any_of"]:
            ok, s = eval_expr(world, kid)
            if ok:
                return True, s
        return False, []
    kind = expr["check"]
    if kind == "fact_equals":
        if world.facts.get(expr["key"]) == expr["value"]:
            return True, _fact_producers(world, expr["key"])[-1:]
        return False, []
    if kind == "fact_exists":
        if expr["key"] in world.facts:
            return True, _fact_producers(world, expr["key"])[-1:]
        return False, []
    if kind == "resource_at_least":
        amount = world.resource(expr["holder"], expr["name"])
        if amount >= float(expr["amount"]) - 1e-9:
            return True, _resource_producers(world, expr["holder"], expr["name"])[-1:]
        return False, []
    if kind == "information_noticed":
        matches = _noticed_matches(world, expr["actor"], expr.get("author"),
                                   expr.get("info_type"))
        if matches:
            return True, [matches[-1][0]]
        return False, []
    if kind == "information_sent":
        matches = _sent_matches(world, expr["author"], expr.get("to"),
                                expr.get("info_type"))
        if matches:
            return True, matches[-1:]
        return False, []
    if kind == "action_completed":
        matches = _completed_matches(world, expr["verb"], expr.get("actor"))
        if matches:
            return True, matches[-1:]
        return False, []
    if kind == "count_facts_at_least":
        counts, seqs = _counts(world, expr["prefix"],
                               options=expr.get("value_in"))
        if sum(counts.values()) >= float(expr["amount"]):
            return True, seqs[-8:]
        return False, []
    raise TerminalSpecError(f"unknown check {kind!r}")


def _counts(world, prefix: str, options=None) -> tuple[dict, list]:
    counts: dict = {}
    seqs: list = []
    for key in sorted(world.facts):
        if not key.startswith(prefix):
            continue
        val = world.facts[key]
        if options is not None and val not in options:
            continue
        counts[val] = counts.get(val, 0) + 1
        seqs.extend(_fact_producers(world, key)[-1:])
    return counts, seqs


def build_terminal(spec: dict) -> Terminal:
    """Compile a validated terminal spec into an engine Terminal.  The
    evaluator is a pure function of world state + ledger; zero LLM calls."""
    validate_terminal_spec(spec)
    mode = spec["mode"]
    cutoff = parse_iso(spec["cutoff"])
    resolve_when = spec.get("resolve_when")

    def evaluate(world, final: bool):
        if mode == "condition":
            ok, seqs = eval_expr(world, spec["condition"])
            if ok:
                return {"answer": "yes",
                        "detail": spec.get("yes_means", "the condition held"),
                        "computed_from": [f"record:{s}" for s in seqs]}
            if final:
                return {"answer": "no",
                        "detail": spec.get("no_means",
                                           "the condition never held before the cutoff"),
                        "computed_from": ["terminal.cutoff"]}
            return None
        ready = final
        gate_seqs: list = []
        if not ready and resolve_when is not None:
            ready, gate_seqs = eval_expr(world, resolve_when)
        if not ready:
            return None
        if mode == "value":
            v = spec["value"]
            if v["read"] == "resource":
                amount = world.resource(v["holder"], v["name"])
                seqs = _resource_producers(world, v["holder"], v["name"])
                detail = f"{v['holder']}:{v['name']} = {amount}"
            else:
                counts, seqs = _counts(world, v["prefix"])
                amount = sum(counts.values())
                detail = f"{amount} fact record(s) under {v['prefix']!r}"
            src = [f"record:{s}" for s in (gate_seqs + seqs)[-8:]]
            return {"answer": amount, "detail": detail,
                    "computed_from": src or ["terminal.cutoff"]}
        d = spec["decision"]
        counts, seqs = _counts(world, d["prefix"], options=d["options"])
        if not counts:
            return {"answer": d.get("none", "no_decision"),
                    "detail": f"no records under {d['prefix']!r} before the cutoff",
                    "computed_from": ["terminal.cutoff"]}
        top = max(counts.values())
        winners = sorted(o for o, c in counts.items() if c == top)
        answer = winners[0] if len(winners) == 1 else d.get("tie", "tie")
        return {"answer": answer,
                "detail": f"counts: {counts}",
                "computed_from": [f"record:{s}" for s in (gate_seqs + seqs)[-8:]]}

    return Terminal(spec["question"], cutoff, evaluate)
