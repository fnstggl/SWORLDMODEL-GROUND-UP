"""Universal validation of an assembled world.

Backward: every terminal term must have at least one potential producer --
an action effect, a running process, or a scheduled external event.  If
nothing can produce a required step, compilation stops instead of inventing
a producer.

Forward: the world must be alive -- something is scheduled to happen, and a
no-mind dry run of the real engine on a throwaway replica must fire events
without integrity errors.

Integrity: the terminal must be false at genesis; no scheduled external
event may directly write a terminal fact (pre-written outcomes are the
historical failure this compiler exists to prevent); questionable-but-
possibly-real findings are routed to the adversarial reviewer as
needs_review rather than silently accepted or silently dropped."""
from __future__ import annotations

import re

from sworldmodel import Engine, parse_iso

from .lowering import LoweringError, lower
from .world_graph import WorldGraph

DRY_RUN_EVENTS = 12


class Report:
    def __init__(self) -> None:
        self.blocking: list = []
        self.needs_review: list = []
        self.warnings: list = []
        self.dry_run: dict = {}
        #: machine-readable findings a targeted patch translation can fix
        #: without re-describing the whole world
        self.patchable: list = []

    def ok(self) -> bool:
        return not self.blocking

    def to_dict(self) -> dict:
        return {"blocking": self.blocking, "needs_review": self.needs_review,
                "warnings": self.warnings, "dry_run": self.dry_run,
                "patchable": self.patchable}


# ---------------------------------------------------------------------------
# terminal term extraction and producer matching
# ---------------------------------------------------------------------------

def _terms(expr: dict) -> list:
    if "all_of" in expr:
        return [t for k in expr["all_of"] for t in _terms(k)]
    if "any_of" in expr:
        return [t for k in expr["any_of"] for t in _terms(k)]
    return [expr]


def terminal_terms(spec: dict) -> list:
    terms = []
    for key in ("condition", "resolve_when"):
        if spec.get(key):
            terms.extend(_terms(spec[key]))
    if spec["mode"] == "value":
        v = spec["value"]
        if v["read"] == "resource":
            terms.append({"check": "resource_at_least", "holder": v["holder"],
                          "name": v["name"], "amount": None})
        else:
            terms.append({"check": "count_facts_at_least",
                          "prefix": v["prefix"], "amount": None})
    if spec["mode"] == "decision_count":
        terms.append({"check": "count_facts_at_least",
                      "prefix": spec["decision"]["prefix"], "amount": None})
    return terms


def _template_regex(template: str) -> re.Pattern:
    """A fact-key template ('x:{actor}') -> regex matching concrete keys."""
    parts = re.split(r"\{[a-zA-Z_.][a-zA-Z0-9_.]*\}", template)
    return re.compile("^" + ".+".join(re.escape(p) for p in parts) + "$")


def _iter_ops(ops: list):
    for op, data in ops:
        yield op, data
        if op == "event.schedule_in":
            yield from _iter_ops(data.get("data", {}).get("ops", []))


def _all_effect_ops(world) -> list:
    """(source, op, data) for every effect any defined action can apply."""
    out = []
    for verb, d in world.action_defs.items():
        for op, data in _iter_ops(d.get("effects", [])
                                  + d.get("start_effects", [])):
            out.append((f"action {verb!r}", op, data))
    return out


def _scheduled_ops(world) -> list:
    out = []
    for ev in world.queue.pending():
        if ev.kind == "world.ops":
            for op, data in _iter_ops(ev.data.get("ops", [])):
                out.append((f"scheduled event at {ev.t.isoformat()}", op, data))
    return out


def _fact_producers(world, key: str | None, prefix: str | None) -> list:
    hits = []
    for src, op, data in _all_effect_ops(world) + _scheduled_ops(world):
        if op != "fact.set":
            continue
        template = str(data.get("key", ""))
        static = template.split("{", 1)[0]
        if key is not None and _template_regex(template).match(key):
            hits.append(src)
        elif prefix is not None and (static.startswith(prefix)
                                     or prefix.startswith(static)):
            if "{" in template or static.startswith(prefix):
                hits.append(src)
    return hits


def _resource_producers(world, holder: str, name: str) -> list:
    hits = []
    for p in world.processes.values():
        if p["holder"] == holder and p["resource"] == name:
            hits.append(f"process {p['id']!r}")
    for src, op, data in _all_effect_ops(world) + _scheduled_ops(world):
        if op == "resource.adjust" and data.get("holder") == holder \
                and data.get("name") == name:
            hits.append(src)
        elif op == "resource.transfer" and data.get("name") == name \
                and holder in (data.get("from_holder"), data.get("to_holder")):
            hits.append(src)
    return hits


def _info_senders(world, target: str, author, info_type) -> list:
    """Ways information could reach `target`: scenario sends plus the
    universal transmit path (any participant holding a route)."""
    role = world.actors[target].role if target in world.actors else None
    hits = []
    for src, op, data in _all_effect_ops(world) + _scheduled_ops(world):
        if op != "info.send_new":
            continue
        to = data.get("to")
        reaches = (isinstance(to, list)
                   and any(t == target or t == "{params.to}" for t in to)) \
            or (isinstance(to, dict) and role in to.get("role_in", []))
        if not reaches:
            continue
        d_type = data.get("data", {}).get("type")
        if info_type is not None and d_type not in (info_type,
                                                    "{params.info_type}"):
            continue
        if author is not None:
            a = data.get("author")
            if a != author and a != "{actor}":
                continue
        hits.append(src)
    # the universal transmit path needs a real route
    senders = [author] if author else sorted(world.actors)
    for s in senders:
        for key in world.facts:
            if key.startswith("route:") and key.endswith(f":{s}:{target}"):
                hits.append(f"route {key!r}")
    return hits


def _attended_channels(world, actor_id: str) -> set:
    st = world.actors.get(actor_id)
    return set(st.attention) if st else set()


# ---------------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------------

def validate_world(graph: WorldGraph, plan: dict) -> Report:
    rep = Report()
    try:
        world, terminal, _ = lower(plan)
    except (LoweringError, Exception) as e:
        rep.blocking.append(f"lowering failed: {e}")
        return rep
    spec = plan["terminal_spec"]

    # -- integrity: terminal must not be pre-resolved -------------------
    try:
        if terminal.evaluate(world, False) is not None:
            rep.blocking.append(
                "the terminal condition is already true at genesis: the "
                "compiled world contains its own answer")
    except Exception as e:
        rep.blocking.append(f"terminal evaluation failed at genesis: {e}")
        return rep

    # -- integrity: no scheduled event writes a terminal fact -----------
    fact_terms = [(t.get("key"), t.get("prefix"))
                  for t in terminal_terms(spec)
                  if t["check"] in ("fact_equals", "fact_exists",
                                    "count_facts_at_least")]
    for src, op, data in _scheduled_ops(world):
        if op != "fact.set":
            continue
        key = str(data.get("key", ""))
        for tkey, tprefix in fact_terms:
            if (tkey is not None and key == tkey) \
                    or (tprefix is not None and key.startswith(tprefix)):
                rep.blocking.append(
                    f"{src} writes terminal fact {key!r} directly: outcomes "
                    f"must be produced by the trajectory, never pre-written "
                    f"into the schedule")

    # -- backward: every terminal term has a potential producer ---------
    for t in terminal_terms(spec):
        c = t["check"]
        if c in ("fact_equals", "fact_exists"):
            if world.facts.get(t.get("key")) is not None:
                continue      # exists at start (equality may differ later)
            if not _fact_producers(world, t["key"], None):
                rep.blocking.append(
                    f"terminal term {c} {t['key']!r}: nothing in the world "
                    f"can produce this fact (no action effect, no scheduled "
                    f"event)")
        elif c == "count_facts_at_least":
            if not _fact_producers(world, None, t["prefix"]):
                rep.blocking.append(
                    f"terminal term counting {t['prefix']!r}: nothing can "
                    f"create records under this prefix")
        elif c == "resource_at_least":
            producers = _resource_producers(world, t["holder"], t["name"])
            if t.get("amount") is not None \
                    and world.resource(t["holder"], t["name"]) >= t["amount"]:
                continue
            if not producers:
                rep.blocking.append(
                    f"terminal term on {t['holder']}:{t['name']}: no process, "
                    f"action, or scheduled event moves this quantity")
        elif c == "information_noticed":
            target = t["actor"]
            senders = _info_senders(world, target, t.get("author"),
                                    t.get("info_type"))
            if not senders:
                rep.blocking.append(
                    f"terminal term: no way exists for information"
                    f"{' from ' + repr(t['author']) if t.get('author') else ''}"
                    f" to reach {target!r} (no scenario send, no route)")
            elif not _attended_channels(world, target):
                rep.blocking.append(
                    f"terminal term: {target!r} attends no channel, so they "
                    f"can never notice the information the answer depends "
                    f"on; give a provenance-labeled attention pattern or "
                    f"model why they truly never look")
                rep.patchable.append({"kind": "no_attention",
                                      "actor": target,
                                      "channels": sorted(world.channels)})
        elif c == "action_completed":
            defn = world.action_defs.get(t["verb"])
            if defn is None:
                rep.blocking.append(f"terminal term: verb {t['verb']!r} is "
                                    f"not defined")
                continue
            roles = [cond["roles"] for cond in defn.get("conditions", [])
                     if cond.get("require") == "role_in"]
            if roles:
                allowed = {aid for aid, st in world.actors.items()
                           if st.role in roles[0]}
                if not allowed:
                    rep.blocking.append(
                        f"terminal term: no participant is authorized to "
                        f"attempt {t['verb']!r} (requires role in {roles[0]})")
                elif t.get("actor") and t["actor"] not in allowed:
                    rep.blocking.append(
                        f"terminal term: {t['actor']!r} is not authorized "
                        f"to attempt {t['verb']!r}")

    # -- forward: the world is alive ------------------------------------
    cutoff = parse_iso(plan["cutoff"])
    upcoming = [ev for ev in world.queue.pending() if ev.t < cutoff]
    if not upcoming:
        rep.blocking.append(
            "dead world: nothing is scheduled to happen before the cutoff, "
            "so no actor can ever be woken and no process is ever observed")
        rep.patchable.append({"kind": "dead_world"})
    for aid, st in sorted(world.actors.items()):
        wakeable = bool(st.attention) \
            or any(ev.kind == "wake.actor" and ev.data.get("actor") == aid
                   for ev in world.queue.pending()) \
            or any(w.get("on_reach", {}).get("wake_actor") == aid
                   for w in world.watches.values())
        if not wakeable:
            rep.needs_review.append(
                f"participant {aid!r} has no attention pattern, no scheduled "
                f"wake, and no watch: they will never act unless something "
                f"else is added -- is that the real situation?")
            if world.channels:
                rep.patchable.append({"kind": "no_attention", "actor": aid,
                                      "channels": sorted(world.channels)})

    # -- forward: authority sanity for every defined verb ---------------
    for verb, d in sorted(world.action_defs.items()):
        roles = [c["roles"] for c in d.get("conditions", [])
                 if c.get("require") == "role_in"]
        if roles and not any(st.role in roles[0]
                             for st in world.actors.values()):
            rep.blocking.append(f"action {verb!r} requires role in "
                                f"{roles[0]} but no participant has such a "
                                f"role: a dead action pretending to matter")

    # -- integrity: chance encoded as fact pre-writes outcomes -----------
    for key in sorted(world.facts):
        low = key.lower()
        if any(w in low for w in ("probability", "likelihood", "chance",
                                  "odds")):
            rep.blocking.append(
                f"fact {key!r} encodes a numeric chance: the runtime is "
                f"deterministic and such facts pre-write the outcome -- "
                f"declare the uncertainty instead and let the trajectory "
                f"decide")

    # -- integrity: scheduled quantity movement on terminal resources ---
    res_terms = {(t["holder"], t["name"]) for t in terminal_terms(spec)
                 if t["check"] == "resource_at_least"}
    for src, op, data in _scheduled_ops(world):
        if op in ("resource.adjust", "resource.transfer"):
            holder_hits = {data.get("holder"), data.get("from_holder"),
                           data.get("to_holder")}
            for holder, name in res_terms:
                if data.get("name") == name and holder in holder_hits:
                    rep.needs_review.append(
                        f"{src} moves the terminal quantity "
                        f"{holder}:{name} on a fixed schedule -- confirm this "
                        f"is a real already-committed change, not a "
                        f"pre-written outcome")

    # -- dynamic: no-mind dry run on a throwaway replica ----------------
    try:
        replica, term2, _ = lower(plan)
        out = Engine(replica, {}, term2).run(stop_after_events=DRY_RUN_EVENTS)
        rep.dry_run = {"status": out.status,
                       "events_fired": out.metrics["events_processed"],
                       "final_answer": out.answer}
        if out.metrics["events_processed"] == 0:
            rep.blocking.append("dry run fired zero events: the world cannot "
                                "move at all")
        if out.status == "resolved":
            rep.needs_review.append(
                f"the terminal resolved during a no-decision dry run "
                f"(answer: {out.answer}): the outcome may not depend on any "
                f"actor's choices -- confirm the question is really about "
                f"scheduled/process dynamics")
    except Exception as e:
        rep.blocking.append(f"dry run crashed: {type(e).__name__}: {e}")
        rep.dry_run = {"status": "crashed", "error": str(e)}

    return rep
