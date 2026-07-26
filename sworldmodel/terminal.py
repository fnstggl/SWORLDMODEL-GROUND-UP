"""Declarative terminal conditions.

The runtime's ``Terminal`` takes a Python callable, which is correct for
hand-authored worlds but impossible for a compiled one: a compiler must never
emit code.  This module supplies the missing *universal* capability -- a
terminal expressed entirely as data.

An observation is a mechanical question about world state or event history.
It answers with a value, whether it is satisfied, and the ledger records that
produced it, so ``computed_from`` lineage stays real rather than asserted.

The vocabulary is deliberately tiny and domain-free:

    fact_equals          a recorded fact has a given value
    fact_exists          a recorded fact exists at all
    resource_at_least    an objective quantity reached a level
    resource_measure     read an objective quantity (no threshold)
    belief_topic_exists  an actor holds a belief on a topic
    info_noticed_by      an actor noticed information carrying a tag
    action_completed     an action of some verb completed
    tally_facts          count records matching a key prefix and apply a rule

"Vote count", "delivery total" and "did she read it" are all expressible
here; none of them is a special case in the runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .engine import Terminal
from .simclock import aware

OBSERVATION_KINDS = frozenset({
    "fact_equals", "fact_exists", "resource_at_least", "resource_measure",
    "belief_topic_exists", "info_noticed_by", "action_completed",
    "tally_facts",
})

TALLY_RULES = frozenset({"majority", "count_value", "count_all"})

QUESTION_TYPES = frozenset({"boolean", "quantity", "choice"})


class TerminalSpecError(ValueError):
    """The declarative terminal is malformed or references nothing real."""


@dataclass(frozen=True)
class Observation:
    """One mechanical reading of the world.  ``params`` are kind-specific."""
    kind: str
    params: dict = field(default_factory=dict)
    describe: str = ""

    def __post_init__(self):
        if self.kind not in OBSERVATION_KINDS:
            raise TerminalSpecError(
                f"unknown observation kind {self.kind!r} "
                f"(known: {sorted(OBSERVATION_KINDS)})")
        for req in _REQUIRED_PARAMS[self.kind]:
            if req not in self.params:
                raise TerminalSpecError(
                    f"observation {self.kind!r} requires parameter {req!r}")
        if self.kind == "tally_facts":
            if self.params["rule"] not in TALLY_RULES:
                raise TerminalSpecError(
                    f"tally rule must be one of {sorted(TALLY_RULES)}")
            if self.params["rule"] == "count_value" and "value" not in self.params:
                raise TerminalSpecError("tally rule 'count_value' requires 'value'")

    def to_dict(self) -> dict:
        return {"kind": self.kind, "params": dict(self.params),
                "describe": self.describe}

    @classmethod
    def from_dict(cls, d: dict) -> "Observation":
        return cls(d["kind"], dict(d.get("params", {})), d.get("describe", ""))

    # -- evaluation ----------------------------------------------------
    def read(self, world) -> dict:
        """Return {satisfied, value, producers, detail}."""
        return _READERS[self.kind](self, world)


_REQUIRED_PARAMS = {
    "fact_equals": ("key", "value"),
    "fact_exists": ("key",),
    "resource_at_least": ("holder", "name", "level"),
    "resource_measure": ("holder", "name"),
    "belief_topic_exists": ("actor", "topic"),
    "info_noticed_by": ("actor", "tag"),
    "action_completed": ("verb",),
    "tally_facts": ("key_prefix", "rule"),
}


def _producers(world, op, match) -> list:
    return [f"record:{r['seq']}" for r in world.records
            if r["op"] == op and match(r["data"])]


def _read_fact_equals(obs, world):
    key, want = obs.params["key"], obs.params["value"]
    have = world.facts.get(key, None)
    return {"satisfied": have == want, "value": have,
            "producers": _producers(world, "fact.set",
                                    lambda d: d["key"] == key),
            "detail": f"fact {key!r} is {have!r} (required {want!r})"}


def _read_fact_exists(obs, world):
    key = obs.params["key"]
    present = key in world.facts
    return {"satisfied": present, "value": world.facts.get(key),
            "producers": _producers(world, "fact.set",
                                    lambda d: d["key"] == key),
            "detail": f"fact {key!r} {'exists' if present else 'does not exist'}"}


def _read_resource_at_least(obs, world):
    holder, name = obs.params["holder"], obs.params["name"]
    level = float(obs.params["level"])
    have = world.resource(holder, name)
    return {"satisfied": have >= level - 1e-9, "value": have,
            "producers": _resource_producers(world, holder, name),
            "detail": f"{holder}:{name} is {have:g} (required >= {level:g})"}


def _read_resource_measure(obs, world):
    holder, name = obs.params["holder"], obs.params["name"]
    have = world.resource(holder, name)
    return {"satisfied": True, "value": have,
            "producers": _resource_producers(world, holder, name),
            "detail": f"{holder}:{name} measured at {have:g}"}


def _resource_producers(world, holder, name):
    out = []
    for r in world.records:
        d = r["data"]
        if r["op"] in ("resource.set", "resource.adjust") \
                and d.get("holder") == holder and d.get("name") == name:
            out.append(f"record:{r['seq']}")
        elif r["op"] == "resource.transfer" and d.get("name") == name \
                and holder in (d.get("to_holder"), d.get("from_holder")):
            out.append(f"record:{r['seq']}")
        elif r["op"] == "process.accrue":
            p = world.processes.get(d.get("id"), {})
            if p.get("holder") == holder and p.get("resource") == name:
                out.append(f"record:{r['seq']}")
    return out


def _read_belief_topic_exists(obs, world):
    aid, topic = obs.params["actor"], obs.params["topic"]
    actor = world.actors.get(aid)
    present = bool(actor) and topic in actor.beliefs
    return {"satisfied": present,
            "value": actor.beliefs[topic].statement if present else None,
            "producers": _producers(world, "actor.belief",
                                    lambda d: d.get("actor") == aid
                                    and d.get("topic") == topic),
            "detail": (f"{aid} holds belief on {topic!r}" if present
                       else f"{aid} holds no belief on {topic!r}")}


def _read_info_noticed_by(obs, world):
    aid, tag = obs.params["actor"], obs.params["tag"]
    hits = [i for i in world.infos.values()
            if i["data"].get("tag") == tag and aid in i["noticed"]]
    ids = {i["id"] for i in hits}
    return {"satisfied": bool(hits),
            "value": sorted(ids) or None,
            "producers": _producers(world, "info.notice",
                                    lambda d: d.get("actor") == aid
                                    and d.get("id") in ids),
            "detail": (f"{aid} noticed information tagged {tag!r}: {sorted(ids)}"
                       if hits else
                       f"{aid} has not noticed any information tagged {tag!r}")}


def _read_action_completed(obs, world):
    verb = obs.params["verb"]
    actor = obs.params.get("actor")
    hits = [a for a in world.actions.values()
            if a["verb"] == verb and a["state"] == "completed"
            and (actor is None or a["actor"] == actor)]
    ids = {a["id"] for a in hits}
    return {"satisfied": bool(hits), "value": sorted(ids) or None,
            "producers": _producers(world, "action.state",
                                    lambda d: d.get("id") in ids
                                    and d.get("state") == "completed"),
            "detail": (f"completed {verb!r} actions: {sorted(ids)}" if hits
                       else f"no completed {verb!r} action"
                            + (f" by {actor}" if actor else ""))}


def _read_tally_facts(obs, world):
    prefix = obs.params["key_prefix"]
    rule = obs.params["rule"]
    expected = obs.params.get("expected_count")
    entries = {k: v for k, v in world.facts.items() if k.startswith(prefix)}
    producers = _producers(world, "fact.set",
                           lambda d: d["key"].startswith(prefix))
    counts = {}
    for v in entries.values():
        counts[str(v)] = counts.get(str(v), 0) + 1
    complete = expected is None or len(entries) >= int(expected)
    if rule == "count_all":
        return {"satisfied": complete, "value": len(entries),
                "producers": producers,
                "detail": f"{len(entries)} records matching {prefix!r}"}
    if rule == "count_value":
        want = str(obs.params["value"])
        return {"satisfied": complete, "value": counts.get(want, 0),
                "producers": producers,
                "detail": f"{counts.get(want, 0)} of {len(entries)} records "
                          f"matching {prefix!r} equal {want!r}"}
    # majority
    if not entries:
        return {"satisfied": False, "value": None, "producers": producers,
                "detail": f"no records matching {prefix!r}"}
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    winner = top[0][0]
    tied = len(top) > 1 and top[1][1] == top[0][1]
    value = "tie" if tied else winner
    return {"satisfied": complete, "value": value, "producers": producers,
            "detail": f"tally over {prefix!r}: {counts} -> {value}"
                      + ("" if complete else
                         f" (incomplete: {len(entries)}/{expected})")}


_READERS = {
    "fact_equals": _read_fact_equals,
    "fact_exists": _read_fact_exists,
    "resource_at_least": _read_resource_at_least,
    "resource_measure": _read_resource_measure,
    "belief_topic_exists": _read_belief_topic_exists,
    "info_noticed_by": _read_info_noticed_by,
    "action_completed": _read_action_completed,
    "tally_facts": _read_tally_facts,
}


@dataclass(frozen=True)
class TerminalSpec:
    """A terminal expressed as data.

    ``boolean``  -> resolves "yes" as soon as every observation in
                    ``conditions`` is satisfied; "no" at the cutoff.
    ``quantity`` -> reads ``measure`` at the cutoff (a "how many by X"
                    question is only answerable at X).
    ``choice``   -> reads ``measure`` (normally a majority tally) and
                    resolves as soon as it is complete.
    """
    question: str
    cutoff: datetime
    question_type: str
    conditions: tuple = ()          # boolean: all must hold
    measure: Observation | None = None   # quantity / choice
    yes_detail: str = ""
    no_detail: str = ""

    def __post_init__(self):
        if self.question_type not in QUESTION_TYPES:
            raise TerminalSpecError(
                f"question_type must be one of {sorted(QUESTION_TYPES)}")
        if self.question_type == "boolean" and not self.conditions:
            raise TerminalSpecError(
                "a boolean terminal needs at least one condition observation")
        if self.question_type in ("quantity", "choice") and self.measure is None:
            raise TerminalSpecError(
                f"a {self.question_type} terminal needs a measure observation")
        object.__setattr__(self, "cutoff", aware(self.cutoff))

    # -- evaluation --------------------------------------------------------
    def evaluate(self, world, final: bool):
        if self.question_type == "boolean":
            reads = [(o, o.read(world)) for o in self.conditions]
            if all(r["satisfied"] for _, r in reads):
                producers = [p for _, r in reads for p in r["producers"]]
                return {"answer": "yes",
                        "detail": self.yes_detail or "; ".join(
                            r["detail"] for _, r in reads),
                        "computed_from": producers or ["terminal.cutoff"],
                        "observations": [
                            {"observation": o.to_dict(), "read": r}
                            for o, r in reads]}
            if final:
                unmet = [r["detail"] for _, r in reads if not r["satisfied"]]
                producers = [p for _, r in reads for p in r["producers"]]
                return {"answer": "no",
                        "detail": self.no_detail or
                                  "not satisfied at the cutoff: " + "; ".join(unmet),
                        "computed_from": producers or ["terminal.cutoff"],
                        "observations": [
                            {"observation": o.to_dict(), "read": r}
                            for o, r in reads]}
            return None
        read = self.measure.read(world)
        if self.question_type == "choice":
            if not read["satisfied"] and not final:
                return None
            return {"answer": read["value"] if read["satisfied"] else "no decision",
                    "detail": read["detail"],
                    "computed_from": read["producers"] or ["terminal.cutoff"],
                    "observations": [{"observation": self.measure.to_dict(),
                                      "read": read}]}
        # quantity: a "how many by <deadline>" question resolves at the deadline
        if not final:
            return None
        return {"answer": read["value"], "detail": read["detail"],
                "computed_from": read["producers"] or ["terminal.cutoff"],
                "observations": [{"observation": self.measure.to_dict(),
                                  "read": read}]}

    def to_terminal(self) -> Terminal:
        """Bind into the runtime's Terminal; the engine is unchanged."""
        return Terminal(self.question, self.cutoff, self.evaluate)

    def to_dict(self) -> dict:
        return {"question": self.question, "cutoff": self.cutoff.isoformat(),
                "question_type": self.question_type,
                "conditions": [o.to_dict() for o in self.conditions],
                "measure": self.measure.to_dict() if self.measure else None,
                "yes_detail": self.yes_detail, "no_detail": self.no_detail}

    @classmethod
    def from_dict(cls, d: dict) -> "TerminalSpec":
        from .simclock import parse_iso
        return cls(question=d["question"], cutoff=parse_iso(d["cutoff"]),
                   question_type=d["question_type"],
                   conditions=tuple(Observation.from_dict(o)
                                    for o in d.get("conditions", [])),
                   measure=(Observation.from_dict(d["measure"])
                            if d.get("measure") else None),
                   yes_detail=d.get("yes_detail", ""),
                   no_detail=d.get("no_detail", ""))
