"""The persistent shared world.

The world remembers: entities, properties and quantities, relationships,
information, resources, ongoing actions, scheduled events, completed events,
actor state, and unresolved uncertainty (explicitly labeled `unknown`).

Every state change flows through exactly one funnel -- ``World.apply`` --
which appends an immutable record ``{seq, t, op, data, cause}`` to the ledger
and folds it into state via a pure reducer.  Because reducers are pure over
records, the ledger IS the world's history: replaying it (with zero actor or
LLM calls) reconstructs the exact final state, and a checkpoint is nothing
more than a ledger position.

The kernel's operations are universal mechanics only -- set state, adjust or
transfer objective quantities, create records, send information, establish or
remove relationships, schedule events, move actions through their lifecycle.
No domain verbs live here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import datetime, timedelta

from .actions import ACTION_TRANSITIONS, validate_action_def
from .actors import ActorState, Belief, Commitment, Memory
from .events import (Event, EventQueue, MAX_SAME_INSTANT_DEPTH,
                     SchedulingInPastError, ZeroTimeLoopError)
from .info import Channel
from .simclock import (CONCRETE_BASES, Clock, PROVENANCE_BASES, aware, iso,
                       parse_iso)

_UNSET = object()

#: Operations permitted inside world.ops events and ActionDef effects.  The
#: information lifecycle (create/send/deliver/notice) and the action/event
#: machinery are deliberately NOT here: effects send information only through
#: the channel+attention mechanics (info.send_new) and schedule only
#: labeled future events (event.schedule_in) -- nothing can forge a
#: delivery, force another actor to notice, or rewrite lifecycle state.
ALLOWED_EFFECT_OPS = frozenset({
    "fact.set", "entity.add", "entity.set",
    "resource.set", "resource.adjust", "resource.transfer",
    "relationship.set",
    "process.add", "process.active", "process.rate", "watch.add",
    "actor.memory", "actor.belief", "actor.plan", "actor.emotion",
    "actor.physical", "actor.commit", "actor.commitment_resolved",
    "actor.reconsider",
    "info.send_new", "event.schedule_in",
})


class WorldIntegrityError(RuntimeError):
    """A record violated a kernel invariant (illegal transition, missing
    cause, delivery before sending, duplicate id, ...)."""


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_of(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


class World:
    def __init__(self, start: datetime) -> None:
        self.clock = Clock(start)
        self.start = self.clock.now
        self.queue = EventQueue()
        self.records: list[dict] = []
        self._seq = 0
        self.genesis_sealed = False
        # ------- persistent state (everything reducers touch) -------
        self.entities: dict = {}
        self.facts: dict = {}
        self.relationships: dict = {}
        self.resources: dict = {}          # "holder:name" -> float
        self.processes: dict = {}
        self.watches: dict = {}
        self.channels: dict = {}
        self.infos: dict = {}
        self.actions: dict = {}
        self.actors: dict = {}
        self.action_defs: dict = {}        # verb -> declarative definition (data)
        self.history: list = []            # completed (fired) events
        self.processed_events: set = set()
        self.terminal_result: dict | None = None
        # ------- engine context -------
        self._ctx_time: datetime | None = None
        self._ctx_depth: int = 0
        self._ctx_cause: int | None = None
        self._pending_wakes: list = []
        self.apply("world.genesis", {"start": iso(self.start), "schema": 1}, None)

    # ------------------------------------------------------------------
    # the single mutation funnel
    # ------------------------------------------------------------------
    @property
    def version(self) -> int:
        return self._seq

    def apply(self, op: str, data: dict, cause=_UNSET) -> int:
        if cause is _UNSET:
            cause = self._ctx_cause
        if self.genesis_sealed and cause is None:
            raise WorldIntegrityError(
                f"record {op!r} has no cause; after genesis every state "
                f"transition must name what produced it")
        # deep-copy severs every caller-held reference: a mind (or handler)
        # keeping the dict it passed in can never rewrite the ledger or the
        # state reduced from it afterwards
        data = copy.deepcopy(data)
        rec = {"seq": self._seq + 1, "t": iso(self.clock.now), "op": op,
               "data": data, "cause": cause}
        self._reduce(rec)          # raises -> seq untouched, nothing appended
        self._seq += 1
        self.records.append(rec)
        return self._seq

    def seal_genesis(self) -> int:
        """Mark the end of world construction; from here on, every record
        must carry a cause."""
        seq = self.apply("genesis.sealed", {}, None)
        self.genesis_sealed = True
        return seq

    # ------------------------------------------------------------------
    # scheduling (events are ledger records too)
    # ------------------------------------------------------------------
    def schedule(self, kind: str, data: dict, at: datetime, cause=_UNSET) -> Event:
        at = aware(at)
        if cause is _UNSET:
            cause = self._ctx_cause
        if at < self.clock.now:
            raise SchedulingInPastError(
                f"cannot schedule {kind!r} at {iso(at)}: clock is at {iso(self.clock.now)}")
        if self._ctx_time is not None and at == self._ctx_time:
            depth = self._ctx_depth + 1
            if depth > MAX_SAME_INSTANT_DEPTH:
                raise ZeroTimeLoopError(
                    f"same-instant causal depth exceeded {MAX_SAME_INSTANT_DEPTH} "
                    f"scheduling {kind!r} at {iso(at)}")
        else:
            depth = 0
        seq = self.apply("event.scheduled",
                         {"t": iso(at), "kind": kind, "data": data, "depth": depth}, cause)
        ev = Event(seq=seq, t=at, kind=kind, data=data, cause=cause, depth=depth)
        self.queue.push(ev)
        return ev

    def cancel_event(self, seq: int, reason: str, cause=_UNSET) -> None:
        self.apply("event.cancelled", {"event": seq, "reason": reason}, cause)
        self.queue.cancel(seq)     # ledger first: a refused record cancels nothing

    # ------------------------------------------------------------------
    # information (create -> send -> deliver is kernel mechanics)
    # ------------------------------------------------------------------
    def send_info(self, author: str, recipients: list, channel: str,
                  content: str, data: dict | None = None, cause=_UNSET) -> str:
        if cause is _UNSET:
            cause = self._ctx_cause
        ch = self.channels.get(channel)
        if ch is None:
            raise WorldIntegrityError(f"unknown channel {channel!r}")
        if not content or not isinstance(content, str):
            raise WorldIntegrityError(
                "information requires non-empty textual content")
        iid = f"i{self._seq + 1}"
        cseq = self.apply("info.create",
                          {"id": iid, "author": author, "content": content,
                           "data": data or {}}, cause)
        for to in recipients:
            sseq = self.apply("info.send", {"id": iid, "to": to, "channel": channel}, cseq)
            self.schedule("info.deliver", {"info": iid, "to": to, "channel": channel},
                          self.clock.now + ch.latency.delta, sseq)
        return iid

    # ------------------------------------------------------------------
    # universal operation sequences (used by world.ops events and by
    # completion effects of declarative actions)
    # ------------------------------------------------------------------
    def validate_ops(self, ops: list, acting_actor: str | None = None) -> None:
        """Structural validation of an op sequence -- called BEFORE anything
        is applied (so bad scenario data cannot half-apply), and also at
        authoring time (action.define / event.schedule_in payloads)."""
        for entry in ops:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2 \
                    or not isinstance(entry[1], dict):
                raise WorldIntegrityError(f"malformed op entry {entry!r}")
            op, data = entry[0], entry[1]
            if op not in ALLOWED_EFFECT_OPS:
                raise WorldIntegrityError(
                    f"op {op!r} is not a permitted effect operation "
                    f"(allowed: {sorted(ALLOWED_EFFECT_OPS)})")
            if acting_actor is not None and op.startswith("actor.") \
                    and data.get("actor") != acting_actor:
                raise WorldIntegrityError(
                    f"action effects of {acting_actor!r} may not touch the "
                    f"private state of {data.get('actor')!r}")
            if op == "event.schedule_in":
                if data.get("basis") not in CONCRETE_BASES:
                    raise WorldIntegrityError(
                        f"event.schedule_in requires a concrete provenance "
                        f"basis, got {data.get('basis')!r}")
                if "delay_hours" not in data and "delay_seconds" not in data:
                    raise WorldIntegrityError(
                        "event.schedule_in requires an explicit delay_hours "
                        "or delay_seconds")
                if data.get("kind") not in ("world.ops", "wake.actor"):
                    raise WorldIntegrityError(
                        f"event.schedule_in may only schedule world.ops or "
                        f"wake.actor events, got {data.get('kind')!r}")
                if data.get("kind") == "world.ops":
                    self.validate_ops(data.get("data", {}).get("ops", []),
                                      acting_actor)
                elif not data.get("data", {}).get("actor") \
                        or not data.get("data", {}).get("reason"):
                    raise WorldIntegrityError(
                        "a scheduled wake.actor needs an explicit actor and "
                        "reason -- wake triggers are never defaulted")

    def run_ops(self, ops: list, acting_actor: str | None = None,
                cause=_UNSET) -> None:
        """Execute a list of [op, data] pairs.  Ops are the universal reducer
        operations plus two macros: ``info.send_new`` (create + send
        information) and ``event.schedule_in`` (schedule a future event with
        a provenance-labeled relative delay).  When executed as the effects
        of an actor's action, private-state ops are restricted to that actor,
        and information/attention mechanics cannot be bypassed (delivery and
        noticing are never directly writable as effects)."""
        if cause is _UNSET:
            cause = self._ctx_cause
        self.validate_ops(ops, acting_actor)
        for entry in ops:
            op, data = entry[0], entry[1]
            if op == "info.send_new":
                self.send_info(author=data["author"],
                               recipients=self.resolve_recipients(data["to"]),
                               channel=data["channel"], content=data["content"],
                               data=data.get("data") or {}, cause=cause)
            elif op == "event.schedule_in":
                delay = timedelta(hours=float(data.get("delay_hours", 0)),
                                  seconds=float(data.get("delay_seconds", 0)))
                payload = dict(data.get("data", {}))
                payload.setdefault("note", data.get("note", ""))
                payload.setdefault("delay_basis", data["basis"])
                self.schedule(data["kind"], payload, self.clock.now + delay, cause)
            else:
                self.apply(op, data, cause)

    def resolve_recipients(self, to) -> list:
        """Recipient lists are data: an explicit list of actor ids, or a
        role-based selection {"role_in": [...], "exclude": [...]}, which is a
        universal routing rule, not scenario code."""
        if isinstance(to, list):
            return to
        if isinstance(to, dict) and "role_in" in to:
            excl = set(to.get("exclude", []))
            return [aid for aid, a in sorted(self.actors.items())
                    if a.role in to["role_in"] and aid not in excl]
        raise WorldIntegrityError(f"unsupported recipient selector {to!r}")

    # ------------------------------------------------------------------
    # continuous processes: exact elapsed-time accrual, recorded
    # ------------------------------------------------------------------
    def accrue_to(self, t: datetime, cause=_UNSET) -> None:
        """Fold elapsed time into every active continuous process, as ledger
        records (so replay needs no time arithmetic).  Capacity limits clamp
        accrual (a full tank stops filling)."""
        t = aware(t)
        for pid in sorted(self.processes):
            p = self.processes[pid]
            if not p["active"] or p["rate_per_hour"] == 0:
                continue
            last = parse_iso(p["last_applied"])
            if t <= last:
                continue
            hours = (t - last).total_seconds() / 3600.0
            amount = p["rate_per_hour"] * hours
            current = self.resources.get(_rkey(p["holder"], p["resource"]), 0.0)
            cap = p.get("capacity")
            clamped = False
            if cap is not None and amount > 0:
                clamped_amount = max(0.0, min(amount, float(cap) - current))
                clamped = clamped_amount != amount
                amount = clamped_amount
            elif amount < 0:
                # consumption stops at empty: a drained tank does not go negative
                clamped_amount = max(amount, -max(current, 0.0))
                clamped = clamped_amount != amount
                amount = clamped_amount
            if amount == 0 and not clamped:
                continue
            # a clamped (even zero) accrual is still recorded: it advances
            # last_applied, which is real state ("the tank was full; no
            # production happened in this interval")
            self.apply("process.accrue",
                       {"id": pid, "amount": amount, "clamped": clamped,
                        "from": p["last_applied"], "to": iso(t)}, cause)

    def effective_rate(self, holder: str, resource: str) -> float:
        """Net rate on a resource right now: capacity-pinned positive
        processes contribute nothing (a full tank is not filling)."""
        current = self.resources.get(_rkey(holder, resource), 0.0)
        rate = 0.0
        for p in self.processes.values():
            if not p["active"] or p["holder"] != holder or p["resource"] != resource:
                continue
            r = p["rate_per_hour"]
            cap = p.get("capacity")
            if r > 0 and cap is not None and current >= float(cap) - 1e-9:
                continue
            rate += r
        return rate

    def attainable_ceiling(self, holder: str, resource: str) -> float:
        """The highest level active positive processes can push this resource
        to (inf when any contributing process is uncapped)."""
        caps = []
        for p in self.processes.values():
            if not p["active"] or p["holder"] != holder or p["resource"] != resource:
                continue
            if p["rate_per_hour"] <= 0:
                continue
            if p.get("capacity") is None:
                return math.inf
            caps.append(float(p["capacity"]))
        return max(caps) if caps else -math.inf

    def resource(self, holder: str, name: str) -> float:
        return self.resources.get(f"{holder}:{name}", 0.0)

    def lineage(self, seq: int, limit: int = 200) -> list:
        """Walk the cause chain of a record back to its origin: the explicit
        producer lineage of any state transition or terminal term.  Chains
        are acyclic (a cause always precedes its effect); a truncated walk is
        marked, never silent."""
        by_seq = {r["seq"]: r for r in self.records}
        chain = []
        cur = by_seq.get(seq)
        while cur is not None:
            if len(chain) >= limit:
                chain.append({"truncated": True, "at_seq": cur["seq"]})
                break
            chain.append({"seq": cur["seq"], "t": cur["t"], "op": cur["op"],
                          "data": cur["data"]})
            cur = by_seq.get(cur["cause"]) if cur["cause"] is not None else None
        return chain

    def wake(self, actor_id: str, kind: str, detail: str = "", ref: str | None = None,
             channel: str | None = None, cause=_UNSET) -> None:
        """Queue a wake trigger for the engine to route (consult now, or
        defer if the actor is busy and the action forbids interruption)."""
        if cause is _UNSET:
            cause = self._ctx_cause
        self._pending_wakes.append({"actor": actor_id, "kind": kind, "detail": detail,
                                    "ref": ref, "channel": channel, "cause": cause})

    # ------------------------------------------------------------------
    # reducers: pure folds of records into state, with integrity guards
    # ------------------------------------------------------------------
    def _reduce(self, rec: dict) -> None:
        op, d, t = rec["op"], rec["data"], rec["t"]
        fn = _REDUCERS.get(op)
        if fn is not None:
            fn(self, d, t, rec)

    # ------------------------------------------------------------------
    # snapshots, hashes, replay, resume
    # ------------------------------------------------------------------
    def material_state(self) -> dict:
        """World state proper -- excludes history/clock/version -- used for
        same-instant no-progress (zero-time loop) detection."""
        return {
            "entities": self.entities,
            "facts": self.facts,
            "relationships": self.relationships,
            "resources": self.resources,
            "processes": self.processes,
            "watches": self.watches,
            "infos": self.infos,
            "actions": self.actions,
            "action_defs": self.action_defs,
            "actors": {aid: a.to_dict() for aid, a in sorted(self.actors.items())},
            "terminal": self.terminal_result,
        }

    def snapshot(self) -> dict:
        snap = self.material_state()
        snap.update({
            "start": iso(self.start),
            "now": iso(self.clock.now),
            "version": self._seq,
            "channels": {n: c.to_dict() for n, c in sorted(self.channels.items())},
            "history": self.history,
        })
        # round-trip through JSON: guarantees plain data and no live aliases
        return json.loads(canonical_json(snap))

    def state_hash(self) -> str:
        return sha256_of(self.snapshot())

    def material_hash(self) -> str:
        return sha256_of(json.loads(canonical_json(self.material_state())))

    def dump_ledger(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for rec in self.records:
                f.write(canonical_json(rec) + "\n")

    @staticmethod
    def load_ledger(path: str) -> list:
        with open(path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    @classmethod
    def from_records(cls, records: list, live: bool = False) -> "World":
        """Pure reconstruction from the ledger: zero actor/LLM calls.

        ``live=False``: replay for verification (state only).
        ``live=True``: resume -- additionally rebuilds the pending-event
        queue, processed-event set and clock so execution can continue.
        """
        if not records or records[0]["op"] != "world.genesis":
            raise WorldIntegrityError("ledger must begin with world.genesis")
        if records[0]["data"].get("schema") != 1:
            raise WorldIntegrityError(
                f"unsupported ledger schema {records[0]['data'].get('schema')!r}")
        w = cls.__new__(cls)
        w.clock = Clock(parse_iso(records[0]["data"]["start"]))
        w.start = w.clock.now
        w.queue = EventQueue()
        w.records = []
        w._seq = 0
        w.genesis_sealed = False
        w.entities = {}; w.facts = {}; w.relationships = {}; w.resources = {}
        w.processes = {}; w.watches = {}; w.channels = {}; w.infos = {}
        w.actions = {}; w.actors = {}; w.action_defs = {}; w.history = []
        w.processed_events = set()
        w.terminal_result = None
        w._ctx_time = None; w._ctx_depth = 0; w._ctx_cause = None
        w._pending_wakes = []
        for rec in records:
            w._reduce(rec)
            if rec["op"] == "genesis.sealed":
                w.genesis_sealed = True
            w.records.append(rec)
        w._seq = records[-1]["seq"]
        w.clock.advance_to(parse_iso(records[-1]["t"]))
        if live:
            cancelled = {r["data"]["event"] for r in records if r["op"] == "event.cancelled"}
            for r in records:
                if r["op"] != "event.scheduled":
                    continue
                seq = r["seq"]
                if seq in w.processed_events or seq in cancelled:
                    continue
                w.queue.push(Event(seq=seq, t=parse_iso(r["data"]["t"]),
                                   kind=r["data"]["kind"], data=r["data"]["data"],
                                   cause=r["cause"], depth=r["data"]["depth"]))
        return w


# ---------------------------------------------------------------------------
# the universal reducer table
# ---------------------------------------------------------------------------

def _rkey(holder: str, name: str) -> str:
    return f"{holder}:{name}"


def _need_actor(w: World, aid: str) -> ActorState:
    a = w.actors.get(aid)
    if a is None:
        raise WorldIntegrityError(f"unknown actor {aid!r}")
    return a


def _red_entity_add(w, d, t, rec):
    if d["id"] in w.entities:
        raise WorldIntegrityError(f"duplicate entity {d['id']!r}")
    w.entities[d["id"]] = {"id": d["id"], "kind": d.get("kind", "entity"),
                           "properties": dict(d.get("properties", {}))}


def _red_entity_set(w, d, t, rec):
    if d["id"] not in w.entities:
        raise WorldIntegrityError(f"unknown entity {d['id']!r}")
    w.entities[d["id"]]["properties"][d["prop"]] = d["value"]


def _red_fact_set(w, d, t, rec):
    w.facts[d["key"]] = d["value"]


def _red_relationship_set(w, d, t, rec):
    key = f"{d['src']}|{d['kind']}|{d['dst']}"
    if d.get("value") is None:
        w.relationships.pop(key, None)
    else:
        w.relationships[key] = d["value"]


def _red_resource_set(w, d, t, rec):
    w.resources[_rkey(d["holder"], d["name"])] = float(d["amount"])


def _red_resource_adjust(w, d, t, rec):
    key = _rkey(d["holder"], d["name"])
    w.resources[key] = w.resources.get(key, 0.0) + float(d["delta"])


def _red_resource_transfer(w, d, t, rec):
    amt = float(d["amount"])
    src = _rkey(d["from_holder"], d["name"])
    dst = _rkey(d["to_holder"], d["name"])
    w.resources[src] = w.resources.get(src, 0.0) - amt
    w.resources[dst] = w.resources.get(dst, 0.0) + amt


def _red_channel_add(w, d, t, rec):
    if d["name"] in w.channels:
        raise WorldIntegrityError(f"duplicate channel {d['name']!r}")
    w.channels[d["name"]] = Channel.from_dict(d)


def _red_process_add(w, d, t, rec):
    if d["id"] in w.processes:
        raise WorldIntegrityError(f"duplicate process {d['id']!r}")
    if d.get("basis") not in CONCRETE_BASES:
        raise WorldIntegrityError(
            f"process {d['id']!r} requires a concrete provenance basis "
            f"({sorted(CONCRETE_BASES)}), got {d.get('basis')!r}")
    w.processes[d["id"]] = {
        "id": d["id"], "holder": d["holder"], "resource": d["resource"],
        "rate_per_hour": float(d["rate_per_hour"]), "active": bool(d.get("active", False)),
        "capacity": d.get("capacity"),
        "basis": d["basis"], "note": d.get("note", ""), "last_applied": t,
    }


def _red_action_define(w, d, t, rec):
    if d["verb"] in w.action_defs:
        raise WorldIntegrityError(f"duplicate action definition {d['verb']!r}")
    validate_action_def(d)
    # effects are validated structurally at REGISTRATION time (against the
    # universal allowlist, with "{actor}" standing for the acting actor), so
    # bad scenario data is refused before any run, not at fire time
    for key in ("start_effects", "effects"):
        w.validate_ops(d.get(key) or [], acting_actor="{actor}")
    w.action_defs[d["verb"]] = copy.deepcopy(d)


def _red_process_active(w, d, t, rec):
    p = w.processes[d["id"]]
    p["active"] = bool(d["active"])
    p["last_applied"] = t


def _red_process_rate(w, d, t, rec):
    p = w.processes[d["id"]]
    p["rate_per_hour"] = float(d["rate_per_hour"])
    p["last_applied"] = t


def _red_process_accrue(w, d, t, rec):
    p = w.processes[d["id"]]
    key = _rkey(p["holder"], p["resource"])
    w.resources[key] = w.resources.get(key, 0.0) + float(d["amount"])
    p["last_applied"] = t


def _red_watch_add(w, d, t, rec):
    if d["id"] in w.watches:
        raise WorldIntegrityError(f"duplicate watch {d['id']!r}")
    if d.get("basis") not in PROVENANCE_BASES:
        raise WorldIntegrityError(f"watch {d['id']!r} requires a provenance basis")
    w.watches[d["id"]] = {"id": d["id"], "holder": d["holder"], "resource": d["resource"],
                          "level": float(d["level"]),
                          "on_reach": copy.deepcopy(d.get("on_reach", {})),
                          "basis": d["basis"], "note": d.get("note", ""), "fired": False}


def _red_watch_fired(w, d, t, rec):
    w.watches[d["id"]]["fired"] = True


def _red_actor_add(w, d, t, rec):
    if d["id"] in w.actors:
        raise WorldIntegrityError(f"duplicate actor {d['id']!r}")
    w.actors[d["id"]] = ActorState.from_dict(d)


def _red_actor_belief(w, d, t, rec):
    a = _need_actor(w, d["actor"])
    a.beliefs[d["topic"]] = Belief(d["statement"], d["basis"], parse_iso(t))


def _red_actor_plan(w, d, t, rec):
    _need_actor(w, d["actor"]).plan = d["plan"]


def _red_actor_emotion(w, d, t, rec):
    _need_actor(w, d["actor"]).emotional_state = d["statement"]


def _red_actor_physical(w, d, t, rec):
    _need_actor(w, d["actor"]).physical_state = d["statement"]


def _red_actor_relationship(w, d, t, rec):
    _need_actor(w, d["actor"]).relationships[d["other"]] = d["statement"]


def _red_actor_commit(w, d, t, rec):
    a = _need_actor(w, d["actor"])
    a.commitments[d["id"]] = Commitment(
        d["id"], d["what"], parse_iso(d["at"]) if d.get("at") else None)


def _red_actor_commitment_resolved(w, d, t, rec):
    a = _need_actor(w, d["actor"])
    c = a.commitments.get(d["id"])
    if c is None:
        raise WorldIntegrityError(f"unknown commitment {d['id']!r} for {d['actor']!r}")
    c.resolved = True


def _red_actor_memory(w, d, t, rec):
    a = _need_actor(w, d["actor"])
    a.memories.append(Memory(parse_iso(t), d.get("kind", "note"),
                             d["content"], d.get("source", "")))


def _red_actor_reconsider(w, d, t, rec):
    _need_actor(w, d["actor"]).reconsider = copy.deepcopy(d["conditions"])


def _red_actor_ongoing(w, d, t, rec):
    _need_actor(w, d["actor"]).ongoing_action = d["action"]


def _red_actor_decision(w, d, t, rec):
    a = _need_actor(w, d["actor"])
    a.last_decision_at = parse_iso(t)
    a.unprocessed_info = []
    a.deferred_wakes = []


def _red_actor_wake_deferred(w, d, t, rec):
    a = _need_actor(w, d["actor"])
    a.deferred_wakes.append({"kind": d["kind"], "detail": d.get("detail", ""),
                             "ref": d.get("ref"), "channel": d.get("channel"),
                             "deferred_at": t, "cause": rec["cause"]})


def _red_info_create(w, d, t, rec):
    if d["id"] in w.infos:
        raise WorldIntegrityError(f"duplicate info {d['id']!r}")
    w.infos[d["id"]] = {"id": d["id"], "author": d["author"], "content": d["content"],
                        "data": dict(d.get("data", {})), "created_at": t,
                        "sends": {}, "delivered": {}, "noticed": {}, "unsupported": {}}


def _red_info_send(w, d, t, rec):
    info = w.infos.get(d["id"])
    if info is None:
        raise WorldIntegrityError(f"cannot send info {d['id']!r} before it is created")
    info["sends"][d["to"]] = {"channel": d["channel"], "at": t}


def _red_info_deliver(w, d, t, rec):
    info = w.infos.get(d["id"])
    if info is None:
        raise WorldIntegrityError(f"cannot deliver info {d['id']!r}: never created")
    send = info["sends"].get(d["to"])
    if send is None:
        raise WorldIntegrityError(
            f"cannot deliver info {d['id']!r} to {d['to']!r}: never sent to them")
    if parse_iso(t) < parse_iso(send["at"]):
        raise WorldIntegrityError(
            f"cannot deliver info {d['id']!r} before it was sent")
    if d["to"] in info["delivered"]:
        raise WorldIntegrityError(f"info {d['id']!r} already delivered to {d['to']!r}")
    info["delivered"][d["to"]] = t
    _need_actor(w, d["to"]).available_info.append(d["id"])


def _red_info_notice(w, d, t, rec):
    info = w.infos.get(d["id"])
    aid = d["actor"]
    if info is None or aid not in info["delivered"]:
        raise WorldIntegrityError(
            f"actor {aid!r} cannot notice info {d['id']!r}: not delivered to them")
    if aid in info["noticed"]:
        raise WorldIntegrityError(f"info {d['id']!r} already noticed by {aid!r}")
    info["noticed"][aid] = t
    a = _need_actor(w, aid)
    if d["id"] in a.available_info:
        a.available_info.remove(d["id"])
    a.noticed_info.append(d["id"])
    a.unprocessed_info.append(d["id"])


def _red_info_noticing_unsupported(w, d, t, rec):
    info = w.infos.get(d["id"])
    if info is None:
        raise WorldIntegrityError(f"unknown info {d['id']!r}")
    info["unsupported"][d["actor"]] = d.get("note", "")


def _red_action_propose(w, d, t, rec):
    if d["id"] in w.actions:
        raise WorldIntegrityError(f"duplicate action {d['id']!r}")
    act = copy.deepcopy(d)   # state never aliases ledger records
    act["state"] = "proposed"
    act["proposed_at"] = t
    w.actions[d["id"]] = act


def _red_action_state(w, d, t, rec):
    act = w.actions.get(d["id"])
    if act is None:
        raise WorldIntegrityError(f"unknown action {d['id']!r}")
    old, new = act["state"], d["state"]
    if new not in ACTION_TRANSITIONS.get(old, set()):
        raise WorldIntegrityError(
            f"illegal action transition {old!r} -> {new!r} for {d['id']!r}")
    act["state"] = new
    act[f"{new}_at"] = t
    for k, v in d.items():
        if k not in ("id", "state"):
            act[k] = v


def _red_event_fired(w, d, t, rec):
    seq = d["event"]
    if seq in w.processed_events:
        raise WorldIntegrityError(f"event {seq} fired twice")
    w.processed_events.add(seq)
    w.history.append({"event": seq, "t": t, "kind": d["kind"], "data": d.get("data", {})})


def _red_terminal(w, d, t, rec):
    if w.terminal_result is not None:
        raise WorldIntegrityError("terminal result already recorded")
    w.terminal_result = {"question": d["question"], "answer": d["answer"],
                         "status": d["status"], "at": t}


_REDUCERS = {
    "entity.add": _red_entity_add,
    "entity.set": _red_entity_set,
    "fact.set": _red_fact_set,
    "relationship.set": _red_relationship_set,
    "resource.set": _red_resource_set,
    "resource.adjust": _red_resource_adjust,
    "resource.transfer": _red_resource_transfer,
    "channel.add": _red_channel_add,
    "process.add": _red_process_add,
    "process.active": _red_process_active,
    "process.rate": _red_process_rate,
    "process.accrue": _red_process_accrue,
    "watch.add": _red_watch_add,
    "watch.fired": _red_watch_fired,
    "actor.add": _red_actor_add,
    "actor.belief": _red_actor_belief,
    "actor.plan": _red_actor_plan,
    "actor.emotion": _red_actor_emotion,
    "actor.physical": _red_actor_physical,
    "actor.relationship": _red_actor_relationship,
    "actor.commit": _red_actor_commit,
    "actor.commitment_resolved": _red_actor_commitment_resolved,
    "actor.memory": _red_actor_memory,
    "actor.reconsider": _red_actor_reconsider,
    "actor.ongoing": _red_actor_ongoing,
    "actor.decision": _red_actor_decision,
    "actor.wake_deferred": _red_actor_wake_deferred,
    "info.create": _red_info_create,
    "info.send": _red_info_send,
    "info.deliver": _red_info_deliver,
    "info.notice": _red_info_notice,
    "info.noticing_unsupported": _red_info_noticing_unsupported,
    "action.define": _red_action_define,
    "action.propose": _red_action_propose,
    "action.state": _red_action_state,
    "event.fired": _red_event_fired,
    "terminal": _red_terminal,
    # trace-only ops (event.scheduled, event.cancelled, actor.view,
    # actor.wake, intention.rejected, mind.exchange, checkpoint.saved,
    # genesis.sealed, world.genesis) have no reducer: they are part of the
    # inspectable history but change no state.
}
