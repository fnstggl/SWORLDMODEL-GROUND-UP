"""Deterministic lowering: semantic scenario -> runtime world.

This layer makes ZERO model calls and invents ZERO meaning. It resolves
names to identifiers, binds the semantic change/precondition/observation
vocabularies onto the runtime's universal operations, and instantiates the
world through the runtime's ordinary public interface.

If the scenario expresses something the universal runtime cannot carry, this
layer raises LOWERING_GAP. It never approximates, never supplies a missing
duration or rate, never adds an actor or consequence that was not described,
and never converts an uncertainty into a default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sworldmodel import (ActorState, AttentionRule, BusinessCalendar, World,
                         parse_iso, recurring)
from sworldmodel.terminal import Observation, TerminalSpec

from .errors import (InvalidReference, LoweringGap, NoCausalProducer,
                     NothingScheduled, SemanticAmbiguity)
from .symbols import SymbolTable, fact_key, slug

#: epistemic status -> runtime provenance basis. "uncertain" is deliberately
#: absent: an uncertain quantity may not become a concrete number.
STATUS_BASIS = {"verified": "verified", "inferred": "inferred"}


@dataclass
class CompiledWorld:
    world: World
    terminal_spec: TerminalSpec
    symbols: SymbolTable
    affordances: dict = field(default_factory=dict)   # verb -> semantic affordance
    trace: list = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


class Lowerer:
    def __init__(self, doc: dict, question: str = "") -> None:
        self.doc = doc
        self.question = question
        self.sym = SymbolTable()
        self.trace: list = []
        # producer index: canonical target -> [descriptions]
        self.producers: dict = {}
        self.affordances: dict = {}
        self.attention_routes: dict = {}   # actor id -> {channel ids}

    # ------------------------------------------------------------------
    def log(self, step: str, **kw) -> None:
        self.trace.append({"step": step, **kw})

    def produced(self, target: str, by: str) -> None:
        self.producers.setdefault(target, []).append(by)

    # ------------------------------------------------------------------
    def lower(self) -> CompiledWorld:
        doc = self.doc
        res = doc["resolution"]
        cutoff = self._time(res["deadline"], "resolution.deadline")
        start = self._start_time(cutoff)

        world = World(start)
        self.world = world
        self.cutoff = cutoff
        self.log("start", start=start.isoformat(), cutoff=cutoff.isoformat())

        self._register_names()
        self._preflight()
        self._lower_routes()
        self._lower_participants()
        self._lower_starting_state()
        self._lower_information()
        self._lower_processes()
        self._lower_affordances()
        self._lower_scheduled_events()
        spec = self._lower_terminal()

        self._verify_schedulable()
        self._verify_producers(spec)
        self._verify_not_already_answered(spec)

        diagnostics = {
            "actors": sorted(world.actors),
            "channels": sorted(world.channels),
            "action_defs": sorted(world.action_defs),
            "processes": sorted(world.processes),
            "scheduled_root_events": len(world.queue.pending()),
            "producer_index": {k: len(v) for k, v in sorted(self.producers.items())},
        }
        return CompiledWorld(world=world, terminal_spec=spec, symbols=self.sym,
                             affordances=self.affordances, trace=self.trace,
                             diagnostics=diagnostics)

    # ------------------------------------------------------------------
    # names first, so every later reference resolves or refuses
    # ------------------------------------------------------------------
    def _register_names(self) -> None:
        for p in self.doc["participants"]:
            self.sym.register("participant", p["name"])
        for r in self.doc.get("communication_routes") or []:
            if "name" not in r:
                raise SemanticAmbiguity("communication_routes entry has no name")
            self.sym.register("route", r["name"])
        for pr in self.doc.get("processes") or []:
            self.sym.register("process", pr["name"])
            if not self.sym.has("quantity", pr["output_quantity"]):
                self.sym.register("quantity", pr["output_quantity"])
        for s in self.doc.get("starting_state") or []:
            q = s.get("quantity")
            if q and not self.sym.has("quantity", q.get("name", "")):
                self.sym.register("quantity", q["name"])
        for a in self.doc["action_affordances"]:
            self.sym.register("affordance", a["label"])
        self.log("symbols", table=self.sym.to_dict())

    # ------------------------------------------------------------------
    # preflight: report EVERY unresolvable reference at once
    # ------------------------------------------------------------------
    def _preflight(self) -> None:
        """Collect all reference defects in one pass.

        Reporting them one at a time makes a scenario with several missing
        declarations impossible to fix in a single bounded repair round, so
        the whole document is checked before anything is built.
        """
        errs: list = []

        def want(kind, name, where):
            if name in (None, ""):
                errs.append(f"{where}: empty {kind} reference")
            elif not self.sym.has(kind, name):
                known = self.sym.names(kind)
                errs.append(f"{where}: no {kind} named {name!r} "
                            f"(declared {kind}s: {known})")

        def scan_changes(changes, where, declared_params=None):
            for i, ch in enumerate(changes or []):
                if not isinstance(ch, dict):
                    errs.append(f"{where}: change #{i} is not an object")
                    continue
                w = f"{where}.change[{ch.get('change_type', '?')}]"
                ct = ch.get("change_type")
                if ct in ("set_quantity", "change_quantity"):
                    want("participant", ch.get("holder"), w)
                    want("quantity", ch.get("quantity"), w)
                elif ct == "transfer_resource":
                    want("participant", ch.get("from"), w)
                    want("participant", ch.get("to"), w)
                    want("quantity", ch.get("quantity"), w)
                elif ct == "send_information":
                    want("route", ch.get("route"), w)
                    if ch.get("from"):
                        want("participant", ch["from"], w)
                    to = ch.get("to") or {}
                    for n in (to.get("participants") or []):
                        want("participant", n, w)
                elif ct == "set_relationship":
                    want("participant", ch.get("from"), w)
                    want("participant", ch.get("to"), w)
                elif ct in ("start_process", "stop_process"):
                    want("process", ch.get("process"), w)
                elif ct == "record_private_note" and ch.get("participant"):
                    want("participant", ch["participant"], w)
                scan_changes(ch.get("effects"), w, declared_params)

        for p in self.doc["participants"]:
            for rel in p.get("relationships") or []:
                want("participant", rel.get("to"),
                     f"participants[{p['name']!r}].relationships")
            for att in p.get("attention") or []:
                want("route", att.get("route"),
                     f"participants[{p['name']!r}].attention")

        for i, s in enumerate(self.doc.get("starting_state") or []):
            w = f"starting_state[{i}]"
            kind = s.get("kind", "fact")
            if kind in ("belief", "relationship") or s.get("subject"):
                want("participant", s.get("subject"), w)
            if kind == "relationship":
                want("participant", s.get("other"), w)
            if kind == "quantity":
                q = s.get("quantity") or {}
                want("participant", q.get("holder"), w)

        for i, inf in enumerate(self.doc.get("information") or []):
            w = f"information[{i}]"
            want("participant", inf.get("holder"), w)
            for n in inf.get("already_sent_to") or []:
                want("participant", n, w)
            if inf.get("already_sent_to"):
                want("route", inf.get("route"), w)

        for i, pr in enumerate(self.doc.get("processes") or []):
            w = f"processes[{i}] ({pr.get('name')!r})"
            want("participant", pr.get("owner"), w)
            want("quantity", pr.get("output_quantity"), w)

        for i, ev in enumerate(self.doc.get("scheduled_events") or []):
            w = f"scheduled_events[{i}] ({ev.get('description')!r})"
            scan_changes(ev.get("effects"), w)
            for wk in ev.get("wakes") or []:
                want("participant", wk.get("participant"), f"{w}.wakes")

        roles = {p.get("role") for p in self.doc["participants"]}
        for i, a in enumerate(self.doc["action_affordances"]):
            w = f"action_affordances[{i}] ({a.get('label')!r})"
            av = a.get("available_to") or {}
            for n in av.get("participants") or []:
                want("participant", n, w)
            for r in av.get("roles") or []:
                if r not in roles:
                    errs.append(f"{w}: available_to names role {r!r} that no "
                                f"participant holds (roles: "
                                f"{sorted(x for x in roles if x)})")
            for c in a.get("preconditions") or []:
                if c.get("condition_type") == "has_quantity_at_least":
                    want("participant", c.get("holder"), w)
                    want("quantity", c.get("quantity"), w)
            scan_changes(a.get("consequences_on_completion"), w)
            try:
                self._check_parameter_references(a, w)
            except InvalidReference as e:
                errs.append(e.reason)

        for i, o in enumerate(self.doc["resolution"].get("observations") or []):
            w = f"resolution.observations[{i}]"
            ot = o.get("observation_type")
            if ot in ("participant_holds_belief", "participant_noticed_information"):
                want("participant", o.get("participant"), w)
            elif ot in ("quantity_reaches", "quantity_measured"):
                want("participant", o.get("holder"), w)
                want("quantity", o.get("quantity"), w)
            elif ot == "action_was_completed":
                want("affordance", o.get("action_label"), w)
                if o.get("participant"):
                    want("participant", o["participant"], w)

        if errs:
            raise InvalidReference(
                f"{len(errs)} reference defect(s) -- every party, route, "
                f"quantity, process and parameter must be declared before it "
                f"is used:\n  - " + "\n  - ".join(errs),
                {"defects": errs})
        self.log("preflight_ok", participants=len(self.doc["participants"]))

    # ------------------------------------------------------------------
    def _participant(self, name, where) -> str:
        return self.sym.resolve("participant", name, where)

    def _route(self, name, where) -> str:
        return self.sym.resolve("route", name, where)

    def _quantity(self, name, where) -> str:
        if not self.sym.has("quantity", name):
            raise InvalidReference(
                f"{where}: quantity {name!r} was never introduced by any "
                f"starting_state entry or process",
                {"known": self.sym.names("quantity")})
        return self.sym.maybe("quantity", name)

    def _time(self, text: str, where: str) -> datetime:
        try:
            return parse_iso(text)
        except Exception as e:
            raise SemanticAmbiguity(
                f"{where}: {text!r} is not an ISO timestamp with a time zone "
                f"offset ({e}); every instant must be unambiguous")

    def _start_time(self, cutoff: datetime) -> datetime:
        """The world begins at the earliest thing that must be able to happen."""
        cands = []
        for ev in self.doc.get("scheduled_events") or []:
            cands.append(self._time(ev["time"], "scheduled_events[].time"))
        for inf in self.doc.get("information") or []:
            if inf.get("sent_time"):
                cands.append(self._time(inf["sent_time"], "information[].sent_time"))
        for pr in self.doc.get("processes") or []:
            op = pr.get("operating_periods") or {}
            if op.get("from_date"):
                tz = op.get("timezone") or "UTC"
                cands.append(self._time(f"{op['from_date']}T00:00:00"
                                        + _offset_for(tz, op["from_date"]),
                                        "processes[].operating_periods.from_date"))
        if not cands:
            raise NothingScheduled(
                "no scheduled event, in-flight information or operating period "
                "gives the world a starting instant; nothing could ever happen")
        earliest = min(cands)
        if earliest > self.cutoff_guard(cutoff):
            raise SemanticAmbiguity(
                f"everything described happens after the deadline "
                f"({earliest.isoformat()} > {cutoff.isoformat()})")
        return earliest

    @staticmethod
    def cutoff_guard(cutoff):
        return cutoff

    # ------------------------------------------------------------------
    def _lower_routes(self) -> None:
        for r in self.doc.get("communication_routes") or []:
            where = f"communication_routes[{r['name']!r}]"
            ident = self.sym.maybe("route", r["name"])
            delay = r.get("delivery_delay") or {}
            status = delay.get("status")
            if status not in STATUS_BASIS:
                raise LoweringGap(
                    f"{where}: delivery_delay.status must be 'verified' or "
                    f"'inferred' (got {status!r}); an uncertain delivery delay "
                    f"cannot become a concrete number",
                    {"route": r["name"]})
            seconds = delay.get("seconds")
            if seconds is None:
                raise LoweringGap(
                    f"{where}: delivery_delay has no 'seconds'; the runtime "
                    f"needs a real latency, and this layer will not invent one")
            self.world.apply("channel.add", {
                "name": ident,
                "latency": {"seconds": float(seconds),
                            "basis": STATUS_BASIS[status],
                            "note": delay.get("description", "")}}, None)
            self.log("route", id=ident, name=r["name"], seconds=float(seconds),
                     basis=STATUS_BASIS[status])

    # ------------------------------------------------------------------
    def _calendar(self, avail: dict, where: str) -> BusinessCalendar | None:
        if not avail:
            return None
        tz = avail.get("timezone")
        if not tz:
            return None
        try:
            return BusinessCalendar(
                tz=tz,
                workdays=frozenset(avail.get("workdays", [0, 1, 2, 3, 4])),
                open_time=time.fromisoformat(avail.get("open", "09:00")),
                close_time=time.fromisoformat(avail.get("close", "17:00")),
                holidays=frozenset(date.fromisoformat(d)
                                   for d in avail.get("holidays", []) or []))
        except Exception as e:
            raise LoweringGap(f"{where}: availability is not usable as a "
                              f"calendar ({e})")

    def _lower_participants(self) -> None:
        for p in self.doc["participants"]:
            where = f"participants[{p['name']!r}]"
            pid = self.sym.maybe("participant", p["name"])
            tz = p.get("timezone") or "UTC"
            avail = dict(p.get("availability") or {})
            avail.setdefault("timezone", tz)
            cal = self._calendar(avail, where)
            attention = {}
            for att in p.get("attention") or []:
                route = self._route(att.get("route", ""), f"{where}.attention")
                status = att.get("status")
                if status not in STATUS_BASIS:
                    # uncertain noticing is NOT modeled as a rule: the message
                    # will be delivered and remain unnoticed, which is honest
                    self.log("attention_omitted", participant=pid, route=route,
                             reason=f"noticing status {status!r} is not "
                                    f"verified or inferred")
                    continue
                interval = att.get("check_interval_minutes")
                if interval is not None and cal is None:
                    raise LoweringGap(
                        f"{where}: a checking cadence needs the participant's "
                        f"availability (working hours) to anchor it")
                attention[route] = AttentionRule(
                    calendar=cal if interval is not None or att.get("bounded_by_availability")
                    else None,
                    check_every=timedelta(minutes=float(interval)) if interval else None,
                    basis=STATUS_BASIS[status],
                    note=att.get("description") or "attention pattern")
                self.attention_routes.setdefault(pid, set()).add(route)
            st = ActorState(
                id=pid, name=p["name"], role=p.get("role", ""), tz=tz,
                attention=attention,
                goals=list(p.get("goals") or []),
                values=list(p.get("values") or []),
                emotional_state=p.get("initial_emotional_state", ""),
                physical_state=p.get("initial_physical_state", ""),
                plan=p.get("initial_plan", ""))
            self.world.apply("actor.add", st.to_dict(), None)
            for rel in p.get("relationships") or []:
                other = self._participant(rel.get("to", ""), f"{where}.relationships")
                self.world.apply("actor.relationship",
                                 {"actor": pid, "other": other,
                                  "statement": rel.get("description", "")}, None)
            self.log("participant", id=pid, name=p["name"], role=p.get("role"),
                     tz=tz, attention=sorted(attention))

    # ------------------------------------------------------------------
    def _lower_starting_state(self) -> None:
        for i, s in enumerate(self.doc.get("starting_state") or []):
            where = f"starting_state[{i}]"
            kind = s.get("kind", "fact")
            if kind == "quantity":
                q = s.get("quantity") or {}
                holder = self._participant(q.get("holder", ""), where)
                name = self._quantity(q.get("name", ""), where)
                if q.get("amount") is None:
                    raise LoweringGap(f"{where}: quantity has no amount")
                self.world.apply("resource.set", {
                    "holder": holder, "name": name,
                    "amount": float(q["amount"])}, None)
                self.produced(f"resource:{holder}:{name}",
                              f"{where}: initial quantity")
                self.log("starting_quantity", holder=holder, name=name,
                         amount=float(q["amount"]))
            elif kind == "belief":
                subject = self._participant(s.get("subject", ""), where)
                topic = slug(s.get("topic") or s.get("description", ""), "topic")
                self.world.apply("actor.belief", {
                    "actor": subject, "topic": topic,
                    "statement": s.get("description", ""),
                    "basis": s.get("status", "inferred") + ": "
                             + ", ".join(s.get("evidence_ids") or []) }, None)
                self.produced(f"belief:{subject}:{topic}",
                              f"{where}: initial belief")
                self.log("starting_belief", actor=subject, topic=topic)
            elif kind == "relationship":
                src = self._participant(s.get("subject", ""), where)
                dst = self._participant(s.get("other", ""), where)
                self.world.apply("relationship.set", {
                    "src": src, "kind": slug(s.get("relationship_kind", "related")),
                    "dst": dst, "value": s.get("description", "")}, None)
                self.log("starting_relationship", src=src, dst=dst)
            else:  # public fact
                key = slug(s.get("about") or s.get("description", ""), "fact")
                self.world.apply("fact.set",
                                 {"key": key,
                                  "value": s.get("value", s.get("description", ""))},
                                 None)
                self.produced(f"fact:{key}", f"{where}: initial fact")
                self.log("starting_fact", key=key)

    # ------------------------------------------------------------------
    def _lower_information(self) -> None:
        """Initial knowledge, and information already in flight."""
        for i, inf in enumerate(self.doc.get("information") or []):
            where = f"information[{i}]"
            holder = self._participant(inf.get("holder", ""), where)
            topic = slug(inf.get("topic") or inf.get("content", ""), "topic")
            self.world.apply("actor.belief", {
                "actor": holder, "topic": topic,
                "statement": inf.get("content", ""),
                "basis": inf.get("basis", "held at the start of the situation")},
                None)
            self.produced(f"belief:{holder}:{topic}", f"{where}: initial knowledge")
            sent_to = inf.get("already_sent_to") or []
            if not sent_to:
                self.log("initial_knowledge", actor=holder, topic=topic)
                continue
            # already in flight: a real send at a real time on a real route
            route = self._route(inf.get("route", ""), where)
            sent_time = self._time(inf.get("sent_time", ""), f"{where}.sent_time")
            recipients = [self._participant(n, where) for n in sent_to]
            tag = slug(inf.get("tag") or inf.get("topic") or "message", "message")
            ops = [["info.send_new", {
                "author": holder, "to": recipients, "channel": route,
                "content": inf.get("content", ""),
                "data": {"tag": tag, "description": inf.get("content", "")}}]]
            self.world.schedule("world.ops",
                                {"ops": ops,
                                 "note": f"{inf.get('content','')[:60]} "
                                         f"(already sent: {inf.get('basis','')})"},
                                sent_time, None)
            for r in recipients:
                self._note_info_producer(r, tag, route, f"{where}: already sent")
            self.log("information_in_flight", tag=tag, route=route,
                     to=recipients, at=sent_time.isoformat())

    def _note_info_producer(self, actor_id: str, tag: str, route: str,
                            by: str) -> None:
        """Information can only be NOTICED if that actor actually attends the
        route it arrives on. Recording this distinction is what lets the
        producer check refuse a terminal that depends on unsupported noticing."""
        if route in self.attention_routes.get(actor_id, set()):
            self.produced(f"info:{actor_id}:{tag}", by)
        else:
            self.log("info_deliverable_but_unnoticed", actor=actor_id, tag=tag,
                     route=route,
                     reason="no justified attention rule for this route")

    # ------------------------------------------------------------------
    def _lower_processes(self) -> None:
        for i, pr in enumerate(self.doc.get("processes") or []):
            where = f"processes[{i}] ({pr['name']!r})"
            pid = self.sym.maybe("process", pr["name"])
            holder = self._participant(pr["owner"], where)
            qty = self._quantity(pr["output_quantity"], where)
            rate = pr["rate"]
            status = rate.get("status")
            if status not in STATUS_BASIS:
                raise LoweringGap(
                    f"{where}: rate.status is {status!r}; an uncertain rate "
                    f"cannot become a number. Model it as an uncertainty "
                    f"instead of a process.")
            periods = pr.get("operating_periods") or {}
            initially_active = bool(pr.get("initially_active", not periods))
            self.world.apply("process.add", {
                "id": pid, "holder": holder, "resource": qty,
                "rate_per_hour": float(rate["amount_per_hour"]),
                "active": initially_active,
                "capacity": pr.get("capacity"),
                "basis": STATUS_BASIS[status],
                "note": rate.get("note") or pr.get("description", "")}, None)
            self.produced(f"resource:{holder}:{qty}", f"{where}: continuous process")
            self.log("process", id=pid, holder=holder, quantity=qty,
                     rate=float(rate["amount_per_hour"]), active=initially_active)
            if periods:
                self._schedule_operating_periods(pid, periods, where)

    def _schedule_operating_periods(self, pid: str, periods: dict, where: str) -> None:
        tz = periods.get("timezone")
        if not tz:
            raise LoweringGap(f"{where}: operating_periods needs a timezone")
        try:
            start_t = time.fromisoformat(periods["start"])
            end_t = time.fromisoformat(periods["end"])
        except Exception as e:
            raise LoweringGap(f"{where}: operating_periods start/end unusable ({e})")
        workdays = frozenset(periods.get("workdays", [0, 1, 2, 3, 4]))
        holidays = frozenset(date.fromisoformat(d)
                             for d in periods.get("holidays", []) or [])
        # the window is the simulation window: from the world's start to the
        # deadline. Not invented -- it is exactly the period being simulated.
        d0 = self.world.start.astimezone(_zone(tz)).date()
        d1 = self.cutoff.astimezone(_zone(tz)).date()
        for t in recurring(tz, start_t, d0, d1, workdays, holidays):
            if t < self.world.start or t > self.cutoff:
                continue
            self.world.schedule("world.ops", {
                "ops": [["process.active", {"id": pid, "active": True}]],
                "note": f"{periods.get('description', 'operating period')} begins"},
                t, None)
        for t in recurring(tz, end_t, d0, d1, workdays, holidays):
            if t < self.world.start or t > self.cutoff:
                continue
            self.world.schedule("world.ops", {
                "ops": [["process.active", {"id": pid, "active": False}]],
                "note": f"{periods.get('description', 'operating period')} ends"},
                t, None)
        self.log("operating_periods", process=pid, tz=tz,
                 start=str(start_t), end=str(end_t), workdays=sorted(workdays))

    # ------------------------------------------------------------------
    # affordances -> declarative action definitions
    # ------------------------------------------------------------------
    def _check_parameter_references(self, a: dict, where: str) -> None:
        """An affordance whose conditions or effects reference a parameter it
        never declares can never fire. That is a dead action, not a subtle
        one -- refuse it at compile time instead of shipping a world where it
        silently always fails."""
        declared = {p.get("name") for p in (a.get("parameters") or [])
                    if isinstance(p, dict)}
        used = set()
        for c in a.get("preconditions") or []:
            if c.get("condition_type") == "has_noticed_information":
                used.add(c.get("from_parameter", "information"))
            if c.get("condition_type") in ("parameter_provided", "parameter_one_of"):
                used.add(c.get("parameter"))
            for k, v in c.items():
                if k.endswith("_from_parameter"):
                    used.add(v)

        def scan(changes):
            for ch in changes or []:
                for k, v in ch.items():
                    if k.endswith("_from_parameter"):
                        used.add(v)
                to = ch.get("to")
                if isinstance(to, dict) and to.get("from_parameter"):
                    used.add(to["from_parameter"])
                scan(ch.get("effects"))

        scan(a.get("consequences_on_completion"))
        missing = sorted(x for x in used if x and x not in declared)
        if missing:
            raise InvalidReference(
                f"{where}: references parameter(s) {missing} that the action "
                f"never declares, so it could never be performed. Declare them "
                f"in 'parameters' (with 'fill_from': 'noticed_information' and "
                f"the tag of the message being responded to, where that is what "
                f"they mean).",
                {"declared": sorted(x for x in declared if x), "used": sorted(used)})

    def _lower_affordances(self) -> None:
        for i, a in enumerate(self.doc["action_affordances"]):
            where = f"action_affordances[{i}] ({a['label']!r})"
            self._check_parameter_references(a, where)
            verb = self.sym.maybe("affordance", a["label"])
            conditions = self._authority(a["available_to"], where)
            for c in a.get("preconditions") or []:
                conditions.append(self._lower_condition(c, where))
            effects = [self._lower_change(e, where, actor_scope=True)
                       for e in a.get("consequences_on_completion") or []]
            defn = {"verb": verb, "description": a["label"]
                    + (f" -- {a['description']}" if a.get("description") else ""),
                    "conditions": conditions, "effects": effects}
            if a.get("duration"):
                d = a["duration"]
                status = d.get("status")
                if status not in STATUS_BASIS:
                    raise LoweringGap(
                        f"{where}: duration.status is {status!r}. An action of "
                        f"unknown length must declare a completion_condition "
                        f"instead of a made-up duration.")
                minutes = d.get("typical_minutes")
                if minutes is None:
                    raise LoweringGap(
                        f"{where}: duration has no typical_minutes and this "
                        f"layer will not invent one")
                defn["duration"] = {"seconds": float(minutes) * 60,
                                    "basis": STATUS_BASIS[status],
                                    "note": d.get("description", "")}
            self.world.apply("action.define", defn, None)
            self.produced(f"action:{verb}", f"{where}: affordance")
            self.affordances[verb] = a
            self.log("affordance", verb=verb, label=a["label"],
                     conditions=len(conditions), effects=len(effects),
                     completion=("duration" if a.get("duration")
                                 else "completion_condition"))

    def _authority(self, available_to: dict, where: str) -> list:
        if available_to.get("participants"):
            return [{"require": "actor_in",
                     "actors": [self._participant(n, where)
                                for n in available_to["participants"]]}]
        if available_to.get("roles"):
            roles = list(available_to["roles"])
            known = {p.get("role") for p in self.doc["participants"]}
            missing = [r for r in roles if r not in known]
            if missing:
                raise InvalidReference(
                    f"{where}: available_to names role(s) {missing} that no "
                    f"participant holds", {"known_roles": sorted(known - {None})})
            return [{"require": "role_in", "roles": roles}]
        raise SemanticAmbiguity(
            f"{where}: available_to must name participants or roles")

    def _lower_condition(self, c: dict, where: str) -> dict:
        ct = c["condition_type"]
        if ct == "actor_has_role":
            return {"require": "role_in", "roles": list(c["roles"])}
        if ct == "world_fact_is":
            return {"require": "fact_equals",
                    "key": self._fact_key(c, where),
                    "value": self._maybe_param(c, "value")}
        if ct == "world_fact_absent":
            return {"require": "fact_absent", "key": self._fact_key(c, where)}
        if ct == "has_noticed_information":
            param = c.get("from_parameter", "information")
            return {"require": "noticed_info", "info": "{params.%s}" % param}
        if ct == "has_quantity_at_least":
            return {"require": "resource_at_least",
                    "holder": self._participant(c["holder"], where),
                    "name": self._quantity(c["quantity"], where),
                    "amount": float(c["amount"])}
        if ct == "parameter_provided":
            return {"require": "param_nonempty", "param": c["parameter"]}
        if ct == "parameter_one_of":
            return {"require": "param_in", "param": c["parameter"],
                    "values": list(c["values"])}
        raise LoweringGap(f"{where}: condition_type {ct!r} has no universal form")

    def _fact_key(self, c: dict, where: str) -> str:
        about = c.get("about")
        if not about:
            raise SemanticAmbiguity(f"{where}: fact condition needs 'about'")
        return fact_key(self.sym, about, c.get("scope", "global"))

    @staticmethod
    def _literal(value):
        """Model-authored prose is DATA, never a template. Braces in it are
        escaped so the runtime cannot interpret them as substitutions."""
        if isinstance(value, str) and ("{" in value or "}" in value):
            return value.replace("{", "{{").replace("}", "}}")
        return value

    @classmethod
    def _maybe_param(cls, obj: dict, field_name: str):
        src = obj.get(f"{field_name}_from_parameter")
        if src:
            return "{params.%s}" % src          # generated by this layer
        return cls._literal(obj.get(field_name))

    # ------------------------------------------------------------------
    # semantic change -> universal runtime operation
    # ------------------------------------------------------------------
    def _lower_change(self, ch: dict, where: str, actor_scope: bool) -> list:
        ct = ch["change_type"]
        if ct == "record_fact":
            about = ch.get("about")
            if not about:
                raise SemanticAmbiguity(f"{where}: record_fact needs 'about'")
            scope = ch.get("scope", "global")
            if scope == "per_actor" and not actor_scope:
                raise LoweringGap(
                    f"{where}: a per-actor record needs an acting participant; "
                    f"scheduled world events have none")
            key = fact_key(self.sym, about, scope)
            self.produced(f"fact:{key}", f"{where}: record_fact")
            return ["fact.set", {"key": key, "value": self._maybe_param(ch, "value")}]

        if ct in ("set_quantity", "change_quantity"):
            holder = self._participant(ch["holder"], where)
            name = self._quantity(ch["quantity"], where)
            self.produced(f"resource:{holder}:{name}", f"{where}: {ct}")
            if ct == "set_quantity":
                return ["resource.set", {"holder": holder, "name": name,
                                         "amount": self._maybe_param(ch, "amount")}]
            return ["resource.adjust", {"holder": holder, "name": name,
                                        "delta": self._maybe_param(ch, "delta")}]

        if ct == "transfer_resource":
            src = self._participant(ch["from"], where)
            dst = self._participant(ch["to"], where)
            name = self._quantity(ch["quantity"], where)
            self.produced(f"resource:{dst}:{name}", f"{where}: transfer")
            self.produced(f"resource:{src}:{name}", f"{where}: transfer")
            return ["resource.transfer",
                    {"from_holder": src, "to_holder": dst, "name": name,
                     "amount": self._maybe_param(ch, "amount")}]

        if ct == "send_information":
            return self._lower_send(ch, where, actor_scope)

        if ct == "set_relationship":
            return ["relationship.set",
                    {"src": self._participant(ch["from"], where),
                     "kind": slug(ch.get("relationship_kind", "related")),
                     "dst": self._participant(ch["to"], where),
                     "value": self._literal(ch.get("description"))}]

        if ct == "schedule_future_event":
            delay = ch.get("delay") or {}
            status = delay.get("status")
            if status not in STATUS_BASIS:
                raise LoweringGap(
                    f"{where}: schedule_future_event delay.status is {status!r}; "
                    f"an uncertain delay cannot become a concrete schedule")
            if delay.get("hours") is None:
                raise LoweringGap(
                    f"{where}: schedule_future_event has no delay.hours")
            nested = [self._lower_change(e, where + " (delayed)", actor_scope)
                      for e in ch.get("effects") or []]
            if not nested:
                raise LoweringGap(
                    f"{where}: schedule_future_event has no effects; it would "
                    f"schedule nothing")
            return ["event.schedule_in",
                    {"kind": "world.ops", "delay_hours": float(delay["hours"]),
                     "basis": STATUS_BASIS[status],
                     "note": delay.get("description", ""),
                     "data": {"ops": nested,
                              "note": ch.get("description", "")}}]

        if ct in ("start_process", "stop_process"):
            pid = self.sym.resolve("process", ch["process"], where)
            return ["process.active", {"id": pid, "active": ct == "start_process"}]

        if ct == "record_private_note":
            if actor_scope:
                actor = "{actor}"
            else:
                if not ch.get("participant"):
                    raise LoweringGap(
                        f"{where}: a private note in a world event must name "
                        f"whose memory it enters")
                actor = self._participant(ch["participant"], where)
            content = self._maybe_param(ch, "content")
            if ch.get("topic"):
                topic = slug(ch["topic"], "topic")
                if actor != "{actor}":
                    self.produced(f"belief:{actor}:{topic}", f"{where}: private note")
                else:
                    for aid in self.sym.ids("participant"):
                        self.produced(f"belief:{aid}:{topic}",
                                      f"{where}: private note by the acting party")
                return ["actor.belief", {"actor": actor, "topic": topic,
                                         "statement": content,
                                         "basis": ch.get("basis", "own reasoning")}]
            return ["actor.memory", {"actor": actor, "kind": "note",
                                     "content": content,
                                     "source": self._literal(ch.get("source", ""))}]

        raise LoweringGap(f"{where}: change_type {ct!r} has no universal form")

    def _lower_send(self, ch: dict, where: str, actor_scope: bool) -> list:
        route = self._route(ch.get("route", ""), where)
        tag = slug(ch.get("tag") or ch.get("description") or "message", "message")
        if actor_scope:
            author = "{actor}"
        else:
            if not ch.get("from"):
                raise LoweringGap(
                    f"{where}: information sent by a world event must name its "
                    f"author")
            author = self._participant(ch["from"], where)
        to = ch.get("to") or {}
        recipients_for_index = []
        if to.get("from_parameter"):
            recipient_spec = ["{params.%s}" % to["from_parameter"]]
            recipients_for_index = [a for a in self.sym.ids("participant")]
        elif to.get("participants"):
            recipient_spec = [self._participant(n, where) for n in to["participants"]]
            recipients_for_index = recipient_spec
        elif to.get("roles"):
            roles = list(to["roles"])
            recipient_spec = {"role_in": roles}
            if to.get("exclude_acting_participant"):
                recipient_spec["exclude"] = ["{actor}"]
            recipients_for_index = [
                self.sym.maybe("participant", p["name"])
                for p in self.doc["participants"] if p.get("role") in roles]
        else:
            raise SemanticAmbiguity(
                f"{where}: send_information needs recipients "
                f"(participants, roles or from_parameter)")
        for r in recipients_for_index:
            self._note_info_producer(r, tag, route, f"{where}: send_information")
        return ["info.send_new",
                {"author": author, "to": recipient_spec, "channel": route,
                 "content": self._maybe_param(ch, "content"),
                 "data": {"tag": tag,
                          "description": self._literal(ch.get("description", ""))}}]

    # ------------------------------------------------------------------
    def _lower_scheduled_events(self) -> None:
        for i, ev in enumerate(self.doc.get("scheduled_events") or []):
            where = f"scheduled_events[{i}] ({ev['description']!r})"
            t = self._time(ev["time"], where)
            if t > self.cutoff:
                self.log("scheduled_event_after_deadline", description=ev["description"],
                         at=t.isoformat())
                continue
            ops = [self._lower_change(e, where, actor_scope=False)
                   for e in ev.get("effects") or []]
            if ops:
                self.world.schedule("world.ops",
                                    {"ops": ops,
                                     "note": f"{ev['description']} "
                                             f"(basis: {ev['basis']})"}, t, None)
            for wk in ev.get("wakes") or []:
                who = self._participant(wk.get("participant", ""), f"{where}.wakes")
                reason = wk.get("reason")
                if not reason:
                    raise LoweringGap(
                        f"{where}: a wake must state why the participant is "
                        f"being brought in; reasons are never defaulted")
                self.world.schedule("wake.actor",
                                    {"actor": who, "reason": slug(reason, "scheduled"),
                                     "detail": wk.get("reason")}, t, None)
            self.log("scheduled_event", description=ev["description"],
                     at=t.isoformat(), ops=len(ops), wakes=len(ev.get("wakes") or []))

    # ------------------------------------------------------------------
    def _lower_terminal(self) -> TerminalSpec:
        res = self.doc["resolution"]
        obs = [self._lower_observation(o, f"resolution.observations[{i}]")
               for i, o in enumerate(res["observations"])]
        qt = res["question_type"]
        if qt == "boolean":
            return TerminalSpec(
                question=self.question or res.get("question", ""),
                cutoff=self.cutoff, question_type="boolean",
                conditions=tuple(obs),
                yes_detail=res.get("yes_condition", ""),
                no_detail=res.get("no_condition", ""))
        if len(obs) != 1:
            raise SemanticAmbiguity(
                f"a {qt} question needs exactly one observation to read, got "
                f"{len(obs)}")
        return TerminalSpec(
            question=self.question or res.get("question", ""),
            cutoff=self.cutoff, question_type=qt, measure=obs[0])

    def _lower_observation(self, o: dict, where: str) -> Observation:
        ot = o["observation_type"]
        desc = o.get("description", "")
        if ot == "participant_holds_belief":
            return Observation("belief_topic_exists",
                               {"actor": self._participant(o["participant"], where),
                                "topic": slug(o["topic"], "topic")}, desc)
        if ot == "participant_noticed_information":
            return Observation("info_noticed_by",
                               {"actor": self._participant(o["participant"], where),
                                "tag": slug(o["tag"], "message")}, desc)
        if ot == "world_fact_is":
            return Observation("fact_equals",
                               {"key": self._fact_key(o, where),
                                "value": o.get("value")}, desc)
        if ot == "world_fact_exists":
            return Observation("fact_exists",
                               {"key": self._fact_key(o, where)}, desc)
        if ot == "quantity_reaches":
            return Observation("resource_at_least",
                               {"holder": self._participant(o["holder"], where),
                                "name": self._quantity(o["quantity"], where),
                                "level": float(o["amount"])}, desc)
        if ot == "quantity_measured":
            return Observation("resource_measure",
                               {"holder": self._participant(o["holder"], where),
                                "name": self._quantity(o["quantity"], where)}, desc)
        if ot == "action_was_completed":
            params = {"verb": self.sym.resolve("affordance", o["action_label"], where)}
            if o.get("participant"):
                params["actor"] = self._participant(o["participant"], where)
            return Observation("action_completed", params, desc)
        if ot == "tally_of_records":
            params = {"key_prefix": fact_key(self.sym, o["about"], "per_actor")
                      .replace("{actor}", ""),
                      "rule": o["rule"]}
            if o.get("expected_count") is not None:
                params["expected_count"] = int(o["expected_count"])
            if o.get("value") is not None:
                params["value"] = o["value"]
            return Observation("tally_facts", params, desc)
        raise LoweringGap(f"{where}: observation_type {ot!r} has no universal form")

    # ------------------------------------------------------------------
    def _verify_schedulable(self) -> None:
        pending = self.world.queue.pending()
        live = [e for e in pending if e.t <= self.cutoff]
        if not live:
            raise NothingScheduled(
                "no event is scheduled at or before the deadline: the world "
                "would never advance and no actor would ever be consulted",
                {"pending": len(pending)})
        self.log("schedulable", root_events=len(live),
                 first=min(e.t for e in live).isoformat())

    def _verify_not_already_answered(self, spec: TerminalSpec) -> None:
        """The trajectory must produce the answer -- never initialization.

        A boolean terminal that is already satisfied by the starting state has
        not been measured by the simulation at all; it was written into the
        world before time began.
        """
        if spec.question_type != "boolean":
            return
        already = spec.evaluate(self.world, final=False)
        if already is not None:
            satisfied = [o for o in spec.conditions if o.read(self.world)["satisfied"]]
            raise NoCausalProducer(
                "the terminal is already satisfied by the starting state, so "
                "the simulation would not decide anything: "
                + "; ".join(o.read(self.world)["detail"] for o in satisfied)
                + ". A condition that is true before the world runs is an "
                  "initialization value, not an outcome.",
                {"already_satisfied": [o.to_dict() for o in satisfied],
                 "hint": "if the question is whether something HAPPENS, observe "
                         "the action that produces it (action_was_completed) or "
                         "the information actually noticed "
                         "(participant_noticed_information); do not observe a "
                         "belief topic the participant already holds at the start"})
        self.log("terminal_not_preanswered", conditions=len(spec.conditions))

    def _verify_producers(self, spec: TerminalSpec) -> None:
        """Every terminal reading must have something in the world that could
        actually produce it. This is what catches a world that cannot answer
        its own question."""
        obs = list(spec.conditions) + ([spec.measure] if spec.measure else [])
        missing = []
        for o in obs:
            target = _observation_target(o)
            if target is None:
                continue
            if target.endswith(":*"):    # tally prefix
                prefix = target[:-1]
                if any(k.startswith(prefix) for k in self.producers):
                    continue
            elif target in self.producers:
                continue
            missing.append({"observation": o.to_dict(), "needs": target})
        if missing:
            raise NoCausalProducer(
                "the terminal reads state that nothing in this world can "
                "produce: " + "; ".join(
                    f"{m['observation']['kind']} needs {m['needs']}"
                    for m in missing),
                {"missing": missing,
                 "available_producers": sorted(self.producers)})
        self.log("producers_verified", observations=len(obs))


def _observation_target(o: Observation) -> str | None:
    p = o.params
    if o.kind in ("fact_equals", "fact_exists"):
        return f"fact:{p['key']}"
    if o.kind in ("resource_at_least", "resource_measure"):
        return f"resource:{p['holder']}:{p['name']}"
    if o.kind == "belief_topic_exists":
        return f"belief:{p['actor']}:{p['topic']}"
    if o.kind == "info_noticed_by":
        return f"info:{p['actor']}:{p['tag']}"
    if o.kind == "action_completed":
        return f"action:{p['verb']}"
    if o.kind == "tally_facts":
        return f"fact:{p['key_prefix']}*"
    return None


def _zone(tz: str):
    from zoneinfo import ZoneInfo
    return ZoneInfo(tz)


def _offset_for(tz: str, day: str) -> str:
    from zoneinfo import ZoneInfo
    dt = datetime.fromisoformat(f"{day}T00:00:00").replace(tzinfo=ZoneInfo(tz))
    off = dt.utcoffset() or timedelta(0)
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def lower(doc: dict, question: str = "") -> CompiledWorld:
    return Lowerer(doc, question).lower()
