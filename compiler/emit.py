"""Deterministic emission: canonical graph + bindings -> the semantic
scenario document.

The eleven-section scenario is no longer authored by a model. It is
GENERATED here, by code, from the canonical world graph and the small
binding results -- and then validated and lowered by the existing
deterministic layers exactly as before. Zero model calls. Anything the
graph cannot express in the runtime's universal vocabulary is refused
with the exact gap, never approximated.

Universal plumbing derived here (the model never restates runtime
mechanics):

* A state produced by a communication channel IS delivered information.
  The sending action gains a send_information effect; every action that
  required the state instead requires having NOTICED the information,
  filled from a parameter whose tag code generates from the one shared
  name. Delivery latency, attention cadence, noticing and wake mechanics
  come from the runtime.
* Scheduled events wake exactly the actors who observe them or whose
  available actions await them, with the event as the recorded reason.
* An action producing a terminal-measured record gets a dedup guard
  (record_absent by the acting participant), so nobody votes twice.
* Every event also records the fact that it occurred, so anything that
  awaits it has a universal precondition to check.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .errors import LoweringGap, SemanticAmbiguity
from .graph import ACTORS, WorldGraph
from .symbols import slug

#: graph basis -> scenario epistemic status
_STATUS = {"verified": "verified", "inferred": "inferred",
           "question_given": "scenario_given", "uncertain": "uncertain",
           "model_memory_unverified": "model_memory_unverified"}

_KIND = {"participant": "person", "organization": "organization",
         "population": "population"}


def _status(basis: str) -> str:
    return _STATUS.get(basis, "uncertain")


def _prov(node) -> dict:
    return {"basis": _status(node.basis),
            "evidence_ids": list(node.evidence_ids),
            "note": (node.meaning or node.name)[:160]}


def _bstat(s: str) -> str:
    """Binding statuses use the graph vocabulary; map to scenario status."""
    return _STATUS.get(s, "uncertain")


def _numeric_status(s: str, inherited_ids) -> str:
    """A concrete number claimed 'verified'/'inferred' must rest on cited
    evidence; when there is none to inherit, the honest label for a
    world-knowledge estimate is model_memory_unverified -- never a
    decorative citation and never 'uncertain' (an uncertain quantity does
    not become a number)."""
    st = _bstat(s)
    if st in ("verified", "inferred") and not inherited_ids:
        return "model_memory_unverified"
    return st


class Emitter:
    def __init__(self, graph: WorldGraph, bindings, question: dict) -> None:
        self.g = graph
        self.b = bindings
        self.question = question
        self.gaps: list = []
        # channel-produced states ARE delivered information
        self.info_states: dict = {}      # state id -> lifecycle
        self._event_times: dict = {}

    # ------------------------------------------------------------------
    def emit(self) -> dict:
        self._derive_info_lifecycles()
        self._unify_substances()
        doc = {
            "resolution": self._resolution(),
            "scope": self._scope(),
            "participants": self._participants(),
            "starting_state": self._starting_state(),
            "communication_routes": self._routes(),
            "information": self._information(),
            "scheduled_events": self._scheduled_events(),
            "processes": self._processes(),
            "action_affordances": self._affordances(),
            "uncertainties": self._uncertainties(),
            "terminal_producers": self._terminal_producers(),
        }
        if self.gaps:
            raise LoweringGap(
                "the canonical world cannot be expressed in the universal "
                "runtime vocabulary",
                {"defects": sorted(set(self.gaps)), "repairable": True})
        return doc

    # ------------------------------------------------------------------
    def _actors(self):
        return [n for c in ACTORS for n in self.g.by_category(c)]

    def _channels(self):
        return [n for n in self.g.by_category("process")
                if n.attrs.get("role") == "channel"]

    def _real_processes(self):
        return [n for n in self.g.by_category("process")
                if n.attrs.get("role") != "channel"]

    def _performer_names(self, action_id: str) -> list:
        return [self.g.node(p).name for p in self.g.performers_of(action_id)]

    # ------------------------------------------------------------------
    def _derive_info_lifecycles(self) -> None:
        """state produced only by channels == information in transit."""
        for st in self.g.by_category("state"):
            producers = self.g.producers_of(st.id)
            if not producers:
                continue
            channels = [p for p in producers
                        if self.g.node(p).category == "process"
                        and self.g.node(p).attrs.get("role") == "channel"]
            if len(channels) != len(producers):
                continue
            senders = []          # actions whose completion sends it
            for e in self.g.prerequisites_of(st.id):
                if self.g.node(e.dst).category == "action":
                    senders.append(e.dst)
            consumers = []        # actions that need to have noticed it
            for other in self.g.by_category("action"):
                for e in self.g.prerequisites_of(other.id):
                    if e.dst == st.id:
                        consumers.append(other.id)
            recipients = sorted({p for c in consumers
                                 for p in self.g.performers_of(c)})
            if not senders:
                self.gaps.append(
                    f"{st.id}: delivered information with no sending action "
                    f"among its prerequisites; nothing can put it in "
                    f"transit")
                continue
            if not recipients:
                self.gaps.append(
                    f"{st.id}: delivered information that no actor's "
                    f"available action awaits; there is no recipient to "
                    f"deliver it to")
                continue
            route = self._shared_route(senders, recipients, channels, st.id)
            self.info_states[st.id] = {
                "tag": st.name, "senders": senders, "consumers": consumers,
                "recipients": recipients, "route": route,
                "content": st.meaning or st.name}

    def _shared_route(self, sender_actions, recipients, channels,
                      where) -> str | None:
        candidates = []
        for ch in sorted(channels):
            ok = True
            for a in sender_actions:
                for p in self.g.performers_of(a):
                    if ch not in {e.dst for e in
                                  self.g.edges_from(p, "sends_to")}:
                        ok = False
            for r in recipients:
                if ch not in {e.dst for e in
                              self.g.edges_from(r, "receives_from")}:
                    ok = False
            if ok:
                candidates.append(ch)
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            self.gaps.append(
                f"{where}: no single channel connects its senders to its "
                f"recipients (senders must sends_to and recipients "
                f"receives_from the same route)")
        else:
            self.gaps.append(
                f"{where}: more than one channel could carry it "
                f"({candidates}); the world must say which")
        return None

    # ------------------------------------------------------------------
    def _unify_substances(self) -> None:
        """One substance, several holders, one runtime quantity name.

        The graph keeps a stock per holder; the runtime keys quantities by
        (holder, name) with a SHARED name, and a transfer moves that name
        between holders. Transfer bindings and process outputs link stocks
        of the same substance; the measured component's name is canonical.
        A holder's stock joins a class only when it is unambiguous (their
        single stock, or an explicit substance/name link)."""
        parent: dict = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            parent[find(a)] = find(b)

        def actor_id(name):
            if not name:
                return None
            for c in ACTORS:
                nid = self.g.maybe(c, name)
                if nid:
                    return nid
            return None

        for bound in (list(self.b.events.values())
                      + list(self.b.actions.values())):
            for rname, spec in sorted((bound.get("amounts") or {}).items()):
                rid = self.g.maybe("resource", rname)
                if rid is None or spec.get("kind") != "transfer":
                    continue
                for side in ("from", "to"):
                    hid = actor_id(spec.get(side))
                    if hid is None:
                        continue
                    held = [rs for rs in self.g.by_category("resource")
                            if rs.attrs.get("holder") == hid]
                    if len(held) == 1:
                        union(held[0].id, rid)
                    else:
                        base = slug(self.g.node(rid).attrs.get("substance")
                                    or self.g.node(rid).name)
                        matches = [rs for rs in held
                                   if slug(rs.attrs.get("substance")
                                           or rs.name) == base]
                        if len(matches) == 1:
                            union(matches[0].id, rid)
        # a process and the stocks it feeds share the substance already
        # (changes edges); nothing to unify there beyond names below
        measured = set(self.g.measured_components())
        groups: dict = {}
        for rs in self.g.by_category("resource"):
            groups.setdefault(find(rs.id), []).append(rs.id)
        self._substance = {}
        for members in groups.values():
            canon = next((m for m in sorted(members) if m in measured),
                         sorted(members)[0])
            for m in members:
                self._substance[m] = self.g.node(canon).name

    def _qty_name(self, rid: str) -> str:
        return self._substance.get(rid, self.g.node(rid).name)

    # ------------------------------------------------------------------
    def _resolution(self) -> dict:
        term = self.g.terminal()
        answer_type = term.attrs.get("answer_type")
        cutoff = (term.attrs.get("cutoff") or {}).get("when")
        obs = []
        for cid in self.g.measured_components():
            node = self.g.node(cid)
            if node.category == "record":
                rule = node.attrs.get("rule")
                if rule:
                    if answer_type == "boolean" and rule == "majority":
                        raise SemanticAmbiguity(
                            "a boolean question cannot be answered by a "
                            "majority tally: any complete set of records "
                            "would read as 'yes' regardless of their "
                            "values. State the value that means yes (rule "
                            "count_value with 'value' and expected_count) "
                            "or make the question a choice.",
                            {"document": "resolution_contract",
                             "defects": [f"proof {node.name!r}: boolean + "
                                         f"majority is unanswerable"],
                             "repairable": True})
                    o = {"observation_type": "tally_of_records",
                         "record_type": node.attrs.get("record_type"),
                         "rule": rule,
                         "description": node.meaning or node.name}
                    if node.attrs.get("expected_count") is not None:
                        o["expected_count"] = node.attrs["expected_count"]
                    if node.attrs.get("value") is not None:
                        o["value"] = node.attrs["value"]
                    if node.attrs.get("subject"):
                        o["subject"] = node.attrs["subject"]
                else:
                    o = {"observation_type": "record_was_made",
                         "record_type": node.attrs.get("record_type"),
                         "description": node.meaning or node.name}
                    if node.attrs.get("subject"):
                        o["subject"] = node.attrs["subject"]
                obs.append(o)
            elif node.category == "state":
                if node.id in self.info_states:
                    life = self.info_states[node.id]
                    for r in life["recipients"]:
                        obs.append({
                            "observation_type":
                                "participant_noticed_information",
                            "participant": self.g.node(r).name,
                            "tag": life["tag"],
                            "description": node.meaning or node.name})
                else:
                    obs.append({"observation_type": "world_fact_is",
                                "about": node.name,
                                "value": str(node.attrs.get("value")
                                             if node.attrs.get("value")
                                             is not None else "true"),
                                "description": node.meaning or node.name})
            elif node.category == "resource":
                holder = node.attrs.get("holder")
                if not holder:
                    self.gaps.append(f"{cid}: measured quantity has no "
                                     f"holder")
                    continue
                base = {"holder": self.g.node(holder).name,
                        "quantity": self._qty_name(cid),
                        "description": node.meaning or node.name}
                if answer_type == "quantity":
                    obs.append({"observation_type": "quantity_measured",
                                **base})
                elif node.attrs.get("amount_at_least") is not None:
                    obs.append({"observation_type": "quantity_reaches",
                                "amount": node.attrs["amount_at_least"],
                                **base})
                else:
                    raise SemanticAmbiguity(
                        "a boolean question observing a quantity needs the "
                        "threshold that means yes (proof field "
                        "'amount_at_least')",
                        {"document": "resolution_contract",
                         "defects": [f"proof {node.name!r}: no "
                                     f"amount_at_least"],
                         "repairable": True})
            else:
                self.gaps.append(f"{cid}: a {node.category} cannot be a "
                                 f"terminal component")
        return {
            "question": self.question.get("question", term.meaning),
            "question_type": answer_type,
            "deadline": cutoff,
            "yes_condition": term.attrs.get("positive_condition", ""),
            "no_condition": term.attrs.get("negative_condition") or "",
            "observed_from": term.meaning,
            "observations": obs,
        }

    # ------------------------------------------------------------------
    def _scope(self) -> dict:
        included = sorted({n.name for n in self._actors()}
                          | {n.name for n in self.g.by_category("process")})
        return {"included": included,
                "excluded": [{"thing": x["name"], "reason": x["why_safe"]}
                             for x in self.g.exclusions]}

    # ------------------------------------------------------------------
    def _participants(self) -> list:
        out = []
        for n in self._actors():
            where = f"participant {n.name!r}"
            entry = {"name": n.name, "kind": _KIND[n.category],
                     "role": n.attrs.get("producer_kind", n.category),
                     "timezone": n.attrs.get("timezone") or "UTC",
                     "causal_relevance": (n.meaning or n.name)[:200],
                     "provenance": _prov(n)}
            avail = n.attrs.get("availability")
            holidays = self._blocked_holidays(n, where)
            if holidays and not avail:
                avail = {"workdays": [0, 1, 2, 3, 4, 5, 6],
                         "open": "00:00", "close": "24:00"}
            if avail:
                entry["availability"] = {
                    "timezone": n.attrs.get("timezone") or "UTC",
                    "workdays": avail.get("workdays"),
                    "open": avail.get("open"), "close": avail.get("close"),
                    **({"holidays": holidays} if holidays else {})}
            attention = []
            for e in self.g.edges_from(n.id, "receives_from"):
                att = e.attrs.get("attention") or {}
                cadence = att.get("cadence_minutes")
                attention.append({
                    "route": self.g.node(e.dst).name,
                    "status": _status(att.get("basis", "inferred")),
                    "description": att.get("meaning", ""),
                    "check_interval_minutes": cadence,
                    "bounded_by_availability": True,
                    "provenance": {"basis": _status(att.get("basis",
                                                            "inferred")),
                                   "evidence_ids": list(n.evidence_ids),
                                   "note": att.get("meaning", "")[:160]}})
            if attention:
                entry["attention"] = attention
            out.append(entry)
        return out

    def _blocked_holidays(self, n, where) -> list:
        """Blocked access windows become calendar holidays. This is only
        faithful when the block covers all the actor's attention -- a
        per-route block beside another live route cannot be expressed."""
        edges = self.g.edges_from(n.id, "receives_from")
        blocked_edges = [e for e in edges
                         if (e.attrs.get("attention") or {}).get("blocked")]
        if not blocked_edges:
            return []
        if len(edges) > len(blocked_edges):
            self.gaps.append(
                f"{where}: a blocked window on one route beside another "
                f"unblocked route cannot be expressed as a calendar; the "
                f"runtime has no per-route holiday")
            return []
        days = set()
        for e in blocked_edges:
            for b in e.attrs["attention"]["blocked"]:
                try:
                    d0 = date.fromisoformat(str(b.get("from"))[:10])
                    d1 = date.fromisoformat(str(b.get("to"))[:10])
                except ValueError:
                    self.gaps.append(f"{where}: blocked window "
                                     f"{b.get('from')!r}..{b.get('to')!r} "
                                     f"is not a date range")
                    continue
                d = d0
                while d <= d1:
                    days.add(d.isoformat())
                    d += timedelta(days=1)
        return sorted(days)

    # ------------------------------------------------------------------
    def _starting_state(self) -> list:
        out = []
        for st in self.g.by_category("state"):
            if not st.attrs.get("initial") or st.id in self.info_states:
                continue
            owners = [e.src for e in self.g.edges_to(st.id, "has_state")]
            actor_owners = [o for o in owners
                            if self.g.node(o).category in ACTORS]
            if owners and not actor_owners:
                continue          # a process's own state; carried by binding
            entry_prov = {"basis": _status(st.basis),
                          "evidence_ids": list(st.evidence_ids),
                          "note": (st.meaning or st.name)[:160]}
            if st.attrs.get("visibility") == "private" and actor_owners:
                for o in actor_owners:
                    out.append({"subject": self.g.node(o).name,
                                "kind": "belief", "topic": st.name,
                                "description": st.meaning or st.name,
                                "visibility": "private",
                                "status": _status(st.basis),
                                "evidence_ids": list(st.evidence_ids),
                                "provenance": entry_prov})
            else:
                out.append({"kind": "fact", "about": st.name,
                            "value": str(st.attrs.get("value")
                                         if st.attrs.get("value") is not None
                                         else "true"),
                            "description": st.meaning or st.name,
                            "status": _status(st.basis),
                            "evidence_ids": list(st.evidence_ids),
                            "provenance": entry_prov})
        for rs in self.g.by_category("resource"):
            if rs.attrs.get("amount") is None:
                continue
            holder = rs.attrs.get("holder")
            if not holder:
                self.gaps.append(f"{rs.id}: an initial quantity with no "
                                 f"holder")
                continue
            out.append({"subject": self.g.node(holder).name,
                        "kind": "quantity",
                        "quantity": {"name": self._qty_name(rs.id),
                                     "holder": self.g.node(holder).name,
                                     "amount": rs.attrs["amount"]},
                        "description": rs.meaning or rs.name,
                        "status": _status(rs.basis),
                        "evidence_ids": list(rs.evidence_ids),
                        "provenance": {"basis": _status(rs.basis),
                                       "evidence_ids":
                                           list(rs.evidence_ids),
                                       "note": (rs.meaning or rs.name)[:160]}})
        return out

    # ------------------------------------------------------------------
    def _routes(self) -> list:
        out = []
        for ch in self._channels():
            bound = self.b.channels.get(ch.id)
            if not bound:
                self.gaps.append(f"{ch.id}: no latency binding for this "
                                 f"route")
                continue
            dstat = _numeric_status(bound.get("status"), ch.evidence_ids)
            out.append({
                "name": ch.name,
                "description": (ch.meaning or ch.name)[:200],
                "delivery_delay": {
                    "description": bound.get("note", ""),
                    "status": dstat,
                    "seconds": bound["delivery_seconds"],
                    "provenance": {"basis": dstat,
                                   "evidence_ids": list(ch.evidence_ids),
                                   "note": bound.get("note", "")[:160]}},
                "provenance": _prov(ch)})
        return out

    # ------------------------------------------------------------------
    def _information(self) -> list:
        out = []
        for info in self.g.by_category("information"):
            sent = info.attrs.get("sent")
            knowers = sorted({e.src for e in
                              self.g.edges_to(info.id, "knows")})
            if sent:
                out.append({
                    "holder": self.g.node(sent["author"]).name,
                    "topic": info.name,
                    "content": info.meaning or info.name,
                    "route": self.g.node(sent["channel"]).name,
                    "already_sent_to": [self.g.node(r).name
                                        for r in sent["to"]],
                    "sent_time": sent["sent_time"],
                    "tag": info.name,
                    "basis": f"already in flight ({_status(info.basis)})",
                    "provenance": _prov(info)})
                knowers = [k for k in knowers if k != sent["author"]]
            for k in knowers:
                out.append({"holder": self.g.node(k).name,
                            "topic": info.name,
                            "content": info.meaning or info.name,
                            "provenance": _prov(info)})
        return out

    # ------------------------------------------------------------------
    def _event_when(self, node, _seen=()) -> datetime | None:
        if node.id in self._event_times:
            return self._event_times[node.id]
        if node.id in _seen:
            self.gaps.append(f"{node.id}: anchored events form a cycle")
            return None
        when = node.attrs.get("when")
        if when:
            try:
                t = datetime.fromisoformat(str(when))
            except ValueError:
                self.gaps.append(f"{node.id}: 'when' {when!r} is not a "
                                 f"calendar time")
                return None
            if t.tzinfo is None:
                self.gaps.append(
                    f"{node.id}: 'when' {when!r} has no utc offset; a real "
                    f"schedule names its timezone")
                return None
            self._event_times[node.id] = t
            return t
        anchors = self.g.edges_from(node.id, "scheduled_at")
        for e in anchors:
            base = self._event_when(self.g.node(e.dst),
                                    _seen + (node.id,))
            if base is None:
                continue
            offset = e.attrs.get("offset_minutes")
            if offset is None:
                self.gaps.append(f"{node.id}: anchored with no "
                                 f"offset_minutes")
                return None
            t = base + timedelta(minutes=float(offset))
            self._event_times[node.id] = t
            return t
        if node.basis == "uncertain" or \
                node.attrs.get("step_kind") == "uncertain_exogenous":
            return None          # uncertainty: never scheduled, never faked
        self.gaps.append(f"{node.id}: an event with no time and no anchor")
        return None

    def _scheduled_events(self) -> list:
        out = []
        for ev in self.g.by_category("event"):
            if ev.basis == "uncertain" or \
                    ev.attrs.get("step_kind") == "uncertain_exogenous":
                continue          # explicitly uncertain: not on the calendar
            t = self._event_when(ev)
            if t is None:
                continue
            effects = [{"change_type": "record_fact", "about": ev.name,
                        "value": "occurred"}]
            bound = self.b.events.get(ev.id) or {}
            for e in (self.g.edges_from(ev.id, "produces")
                      + self.g.edges_from(ev.id, "changes")):
                effects.extend(self._event_effect(ev, self.g.node(e.dst),
                                                  bound))
            wakes = []
            woken = set()
            for e in self.g.edges_to(ev.id, "observes"):
                if e.src not in woken:
                    woken.add(e.src)
                    wakes.append({"participant": self.g.node(e.src).name,
                                  "reason": f"scheduled: {ev.name}"})
            for act in self.g.by_category("action"):
                if any(p.dst == ev.id for p in
                       self.g.prerequisites_of(act.id)):
                    for perf in self.g.performers_of(act.id):
                        if perf not in woken:
                            woken.add(perf)
                            wakes.append(
                                {"participant": self.g.node(perf).name,
                                 "reason": f"scheduled: {ev.name}"})
            out.append({
                "description": f"{ev.name} -- {ev.meaning}"[:200],
                "time": t.isoformat(),
                "basis": f"{_status(ev.basis)}: "
                         + (", ".join(ev.evidence_ids) or "the question"),
                "provenance": _prov(ev),
                "effects": effects,
                **({"wakes": wakes} if wakes else {})})
        out.sort(key=lambda e: (e["time"], e["description"]))
        return out

    def _event_effect(self, ev, target, bound) -> list:
        if target.category == "state":
            if target.id in self.info_states:
                self.gaps.append(
                    f"{ev.id}: a scheduled event cannot deliver "
                    f"{target.id}; delivery belongs to the channel")
                return []
            return [{"change_type": "record_fact", "about": target.name,
                     "value": str(target.attrs.get("value")
                                  if target.attrs.get("value") is not None
                                  else "true")}]
        if target.category == "record":
            spec = (bound.get("record_makers") or {}).get(target.name)
            if not spec:
                self.gaps.append(f"{ev.id}: no binding says who makes the "
                                 f"record {target.name!r}")
                return []
            return [{"change_type": "create_record",
                     "record_type": target.attrs.get("record_type"),
                     "made_by": spec["made_by"],
                     "value": spec.get("value"),
                     "subject": spec.get("subject") or target.name}]
        if target.category == "resource":
            spec = (bound.get("amounts") or {}).get(target.name)
            if not spec:
                self.gaps.append(f"{ev.id}: no binding gives the amount "
                                 f"for {target.name!r}")
                return []
            if spec.get("kind") == "transfer":
                return [{"change_type": "transfer_resource",
                         "quantity": self._qty_name(target.id),
                         "from": spec.get("from"),
                         "to": spec.get("to"), "amount": spec["amount"]}]
            holder = target.attrs.get("holder")
            return [{"change_type": "change_quantity",
                     "quantity": self._qty_name(target.id),
                     "holder": self.g.node(holder).name if holder else
                     spec.get("to") or spec.get("from"),
                     "delta": spec["amount"]}]
        if target.category == "information":
            spec = (bound.get("messages") or {}).get(target.name)
            if not spec:
                self.gaps.append(f"{ev.id}: no binding routes the "
                                 f"information {target.name!r}")
                return []
            return [{"change_type": "send_information",
                     "route": spec["channel"], "from": spec["from"],
                     "to": {"participants": list(spec["to"])},
                     "tag": target.name,
                     "content": spec.get("content", target.meaning),
                     "description": target.meaning or target.name}]
        if target.category == "event":
            return []             # anchoring handled by scheduling itself
        self.gaps.append(f"{ev.id}: cannot express an effect on "
                         f"{target.id} ({target.category})")
        return []

    # ------------------------------------------------------------------
    def _processes(self) -> list:
        out = []
        for pr in self._real_processes():
            bound = self.b.processes.get(pr.id)
            if not bound:
                self.gaps.append(f"{pr.id}: no rate binding for this "
                                 f"process")
                continue
            if bound.get("decorative"):
                continue          # no continuous work; transfers account for it
            targets = [self.g.node(e.dst) for e in
                       self.g.edges_from(pr.id, "changes")
                       + self.g.edges_from(pr.id, "produces")]
            resources = [t for t in targets if t.category == "resource"]
            if not resources:
                self.gaps.append(
                    f"{pr.id}: a continuous process must change a "
                    f"quantity; other continuous meanings have no "
                    f"universal runtime form")
                continue
            rs = resources[0]
            holder = rs.attrs.get("holder")
            if not holder:
                self.gaps.append(f"{pr.id}: its output {rs.id} has no "
                                 f"holder")
                continue
            rstat = _numeric_status(bound.get("rate_status"),
                                    pr.evidence_ids)
            entry = {
                "name": pr.name,
                "owner": self.g.node(holder).name,
                "output_quantity": self._qty_name(rs.id),
                "description": (pr.meaning or pr.name)[:200],
                "rate": {"amount_per_hour": bound["amount_per_hour"],
                         "status": rstat,
                         "note": bound.get("rate_note", "")},
                "provenance": _prov(pr)}
            op = bound.get("operating")
            if op:
                entry["operating_periods"] = {
                    "description": pr.attrs.get("operating_meaning", "")
                    or "operating period",
                    "timezone": op.get("timezone"),
                    "workdays": op.get("workdays"),
                    "start": op.get("start"), "end": op.get("end")}
            out.append(entry)
        return out

    # ------------------------------------------------------------------
    def _affordances(self) -> list:
        measured = set(self.g.measured_components())
        out = []
        for act in self.g.by_category("action"):
            where = f"action {act.name!r}"
            bound = self.b.actions.get(act.id)
            if bound is None:
                self.gaps.append(f"{where}: no binding")
                continue
            performers = self._performer_names(act.id)
            if not performers:
                self.gaps.append(f"{where}: no performers")
                continue
            params, conditions, param_names = [], [], set()

            def _expand(dst_id, seen=()):
                """A producerless non-initial state is a conjunction of
                its prerequisites; condition on the parts that actually
                get written."""
                node = self.g.node(dst_id)
                if node.category == "state" \
                        and not node.attrs.get("initial") \
                        and not self.g.producers_of(dst_id) \
                        and dst_id not in seen:
                    subs = [e2.dst for e2 in
                            self.g.prerequisites_of(dst_id)
                            if e2.attrs.get("necessity", "necessary")
                            == "necessary"]
                    if subs:
                        out = []
                        for s in subs:
                            out.extend(_expand(s, seen + (dst_id,)))
                        return out
                return [dst_id]

            expanded = []
            for e in self.g.prerequisites_of(act.id):
                nec = e.attrs.get("necessity", "necessary")
                if nec == "optional":
                    continue
                if nec == "alternative":
                    self.gaps.append(
                        f"{where}: alternative preconditions (either/or) "
                        f"have no universal runtime form; restate the "
                        f"enabling condition as a single state")
                    continue
                for dst_id in _expand(e.dst):
                    if dst_id not in expanded:
                        expanded.append(dst_id)
            for dst_id in expanded:
                dst = self.g.node(dst_id)
                if dst.id in self.info_states:
                    life = self.info_states[dst.id]
                    pname = slug(life["tag"], "message")[:40]
                    if pname not in param_names:
                        param_names.add(pname)
                        params.append({
                            "name": pname,
                            "description": dst.meaning or dst.name,
                            "fill_from": "noticed_information",
                            "tag": slug(life["tag"], "message")})
                    conditions.append({
                        "condition_type": "has_noticed_information",
                        "from_parameter": pname})
                elif dst.category == "state":
                    conditions.append({
                        "condition_type": "world_fact_is",
                        "about": dst.name,
                        "value": str(dst.attrs.get("value")
                                     if dst.attrs.get("value") is not None
                                     else "true")})
                elif dst.category == "event":
                    conditions.append({
                        "condition_type": "world_fact_is",
                        "about": dst.name, "value": "occurred"})
                elif dst.category == "record":
                    c = {"condition_type": "record_exists",
                         "record_type": dst.attrs.get("record_type")
                         or slug(dst.name, "record")}
                    conditions.append(c)
                elif dst.category == "action":
                    conditions.append({
                        "condition_type": "action_already_completed",
                        "action_label": dst.name})
                elif dst.category == "information":
                    pname = slug(dst.name, "message")[:40]
                    if pname not in param_names:
                        param_names.add(pname)
                        params.append({
                            "name": pname,
                            "description": dst.meaning or dst.name,
                            "fill_from": "noticed_information",
                            "tag": slug(dst.name, "message")})
                    conditions.append({
                        "condition_type": "has_noticed_information",
                        "from_parameter": pname})
                else:
                    self.gaps.append(
                        f"{where}: a precondition on {dst.id} "
                        f"({dst.category}) has no universal form")

            for p in bound.get("parameters") or []:
                pname = slug(p.get("name", ""), "choice")[:40]
                if pname in param_names:
                    continue
                param_names.add(pname)
                params.append({"name": pname,
                               "description": p.get("meaning", "")})
                if p.get("allowed_values"):
                    conditions.append({"condition_type": "parameter_one_of",
                                       "parameter": pname,
                                       "values": [str(v) for v in
                                                  p["allowed_values"]]})
                else:
                    conditions.append({"condition_type":
                                       "parameter_provided",
                                       "parameter": pname})

            effects = []
            for e in (self.g.edges_from(act.id, "produces")
                      + self.g.edges_from(act.id, "changes")):
                effects.extend(self._action_effect(act, self.g.node(e.dst),
                                                   bound, measured,
                                                   conditions, params,
                                                   param_names))
            # completing this action is what puts derived information in
            # transit: the send effect comes from the lifecycle, since the
            # graph records the channel (not the action) as the producer
            for sid, life in sorted(self.info_states.items()):
                if act.id in life["senders"] and life["route"] is not None:
                    effects.append(self._send_for(life, self.g.node(sid)))

            entry = {
                "label": act.name,
                "description": (act.meaning or act.name)[:200],
                "available_to": {"participants": performers},
                "parameters": params,
                "preconditions": conditions,
                "consequences_on_completion": effects,
                "provenance": _prov(act)}
            if bound.get("duration_minutes") is not None:
                dstat = _numeric_status(bound.get("duration_status"),
                                        act.evidence_ids)
                entry["duration"] = {
                    "description": bound.get("duration_note", ""),
                    "status": dstat,
                    "typical_minutes": bound["duration_minutes"],
                    "provenance": {
                        "basis": dstat,
                        "evidence_ids": list(act.evidence_ids),
                        "note": bound.get("duration_note", "")[:160]}}
            out.append(entry)
        return out

    def _action_effect(self, act, target, bound, measured, conditions,
                       params, param_names) -> list:
        where = f"action {act.name!r}"
        if target.id in self.info_states:
            life = self.info_states[target.id]
            if life["route"] is None:
                return []
            return [self._send_for(life, target)]
        if target.category == "state":
            return [{"change_type": "record_fact", "about": target.name,
                     "value": str(target.attrs.get("value")
                                  if target.attrs.get("value") is not None
                                  else "true")}]
        if target.category == "record":
            spec = (bound.get("record_values") or {}).get(target.name) or {}
            value = spec.get("value")
            eff = {"change_type": "create_record",
                   "record_type": target.attrs.get("record_type")
                   or slug(target.name, "record"),
                   "subject": spec.get("subject") or target.name}
            if isinstance(value, dict) and value.get("from_parameter"):
                pname = slug(value["from_parameter"], "choice")[:40]
                if pname not in param_names:
                    self.gaps.append(
                        f"{where}: record value comes from parameter "
                        f"{pname!r} that the binding never declared")
                eff["value_from_parameter"] = pname
            else:
                eff["value"] = value if value is not None else "made"
            if target.id in measured:
                conditions.append({
                    "condition_type": "record_absent",
                    "record_type": eff["record_type"],
                    "made_by_acting_participant": True})
            return [eff]
        if target.category == "resource":
            spec = (bound.get("amounts") or {}).get(target.name)
            if not spec:
                self.gaps.append(f"{where}: no amount bound for "
                                 f"{target.name!r}")
                return []
            if spec.get("kind") == "transfer":
                return [{"change_type": "transfer_resource",
                         "quantity": self._qty_name(target.id),
                         "from": spec.get("from"),
                         "to": spec.get("to"), "amount": spec["amount"]}]
            holder = target.attrs.get("holder")
            return [{"change_type": "change_quantity",
                     "quantity": self._qty_name(target.id),
                     "holder": self.g.node(holder).name if holder
                     else spec.get("to") or spec.get("from"),
                     "delta": spec["amount"]}]
        if target.category == "information":
            consumers = [a.id for a in self.g.by_category("action")
                         if any(p.dst == target.id for p in
                                self.g.prerequisites_of(a.id))]
            recipients = sorted({p for c in consumers
                                 for p in self.g.performers_of(c)})
            if not recipients:
                self.gaps.append(
                    f"{where}: sends {target.id} but no actor's action "
                    f"awaits it; there is no recipient")
                return []
            route = self._shared_route([act.id], recipients,
                                       [e.dst for e in self.g.edges_from(
                                           act.id, "produces")
                                        if self.g.node(e.dst).attrs.get(
                                            "role") == "channel"]
                                       or [c.id for c in self._channels()],
                                       target.id)
            if route is None:
                return []
            content = (bound.get("message_contents") or {}).get(
                target.name) or target.meaning or target.name
            return [{"change_type": "send_information",
                     "route": self.g.node(route).name,
                     "tag": target.name,
                     "content": content,
                     "description": target.meaning or target.name,
                     "to": {"participants": [self.g.node(r).name
                                             for r in recipients]}}]
        if target.category == "event":
            return []
        self.gaps.append(f"{where}: an effect on {target.id} "
                         f"({target.category}) has no universal form")
        return []

    def _send_for(self, life, st) -> dict:
        return {"change_type": "send_information",
                "route": self.g.node(life["route"]).name,
                "tag": life["tag"],
                "content": life["content"],
                "description": st.meaning or st.name,
                "to": {"participants": [self.g.node(r).name
                                        for r in life["recipients"]]}}

    # ------------------------------------------------------------------
    def _uncertainties(self) -> list:
        out = []
        for u in sorted(self.g.uncertainties,
                        key=lambda x: (x["about"], x["meaning"])):
            node = self.g.node(u["about"])
            out.append({"description": f"{u['meaning']} "
                                       f"(about: {node.name})",
                        "type": "causal",
                        "supported_possibilities": [],
                        "evidence_ids": []})
        return out

    # ------------------------------------------------------------------
    def _terminal_producers(self) -> list:
        out = []
        for cid in self.g.measured_components():
            node = self.g.node(cid)
            ways = []
            for p in self.g.producers_of(cid):
                pn = self.g.node(p)
                ways.append(f"{pn.name} ({pn.category})")
            if node.attrs.get("initial") or node.attrs.get("amount") \
                    is not None:
                ways.append("present at the start of the situation")
            if cid in self.info_states:
                life = self.info_states[cid]
                ways = [f"completion of "
                        f"{self.g.node(a).name!r}" for a in life["senders"]]
                ways.append(f"delivery on "
                            f"{self.g.node(life['route']).name!r}"
                            if life["route"] else "delivery")
                ways.extend(f"{self.g.node(r).name} noticing it"
                            for r in life["recipients"])
            out.append({"terminal_component": node.name,
                        "can_be_produced_by": ways})
        return out


def emit_scenario(graph: WorldGraph, bindings, question: dict) -> dict:
    """graph + bindings -> the generated semantic scenario. Deterministic;
    refuses with the exact gap instead of approximating."""
    return Emitter(graph, bindings, question).emit()
