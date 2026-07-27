"""Backward causal proof and forward executability proof over the canonical
world graph.

Backward: every terminal component must be producible by a chain that
recursively reaches real roots -- an initial fact, a scheduled event, an
actor's available choice, an operating process, or an explicitly uncertain
exogenous event. Initialization must not satisfy a trajectory-required
terminal; a report must not replace the process it reports; no actor may
write the terminal directly unless the measured act itself is the terminal.

Forward: from genesis, something must actually be able to happen -- a
scheduled root exists, channels connect real senders to real receivers,
required information can become locally available to the actor whose action
needs it, preconditions are reachable, declared authority covers the
performers, and the terminal can still emerge after genesis.

Two rules come straight from the Phase 0 audit:

* An event whose effects directly produce a terminal-measured component
  must rest on a ``verified`` or ``question_given`` basis. An inferred
  timetable that writes the answer is the model predicting the outcome and
  serializing the prediction as a schedule; inferred chains must be
  simulated by processes and choices, not asserted.
* An action that writes a measured component with no prerequisites is a
  direct terminal write and is refused unless the resolution contract named
  it as the measured act itself (a cast vote IS the vote record).

Both proofs are pure reads: no model calls, no mutation, all defects
reported at once.
"""
from __future__ import annotations

from .errors import InvalidReference, NoCausalProducer, NothingScheduled
from .graph import ACTORS, WorldGraph

#: Root kinds a causal chain may bottom out in.
ROOTS = ("initial_fact", "scheduled_event", "actor_choice", "process",
         "explicit_uncertainty", "initially_known", "initial_resource")

#: Event bases allowed to write a terminal-measured component directly.
SCHEDULE_BASES_FOR_TERMINAL = ("verified", "question_given")


class _Rootedness:
    """Memoized 'can this node ever hold/occur' over the graph."""

    def __init__(self, graph: WorldGraph) -> None:
        self.g = graph
        self.memo: dict = {}

    def rooted(self, node_id: str, _visiting: frozenset = frozenset()):
        """Returns a root tree dict, or None if unreachable. Cycles are
        unreachable unless broken by an external root."""
        if node_id in self.memo:
            return self.memo[node_id]
        if node_id in _visiting:
            return None                       # cycle via this path
        visiting = _visiting | {node_id}
        n = self.g.node(node_id)
        result = None

        if n.category == "state" and n.attrs.get("initial"):
            # an initial fact is true at genesis regardless of any marker
            result = {"node": node_id, "root": "initial_fact"}
        elif n.category == "state" \
                and (n.attrs.get("conjunction")
                     or n.attrs.get("no_producer_needed")) \
                and not self.g.producers_of(node_id) \
                and any(e.attrs.get("necessity", "necessary") != "optional"
                        for e in self.g.prerequisites_of(node_id)):
            # an EXPLICIT conjunction holds exactly when its parts hold;
            # its parts' producers do the causal work. The flag matters: a
            # state whose producer an ablation removed is broken, not a
            # conjunction.
            result = self._with_requires(
                n, {"node": node_id, "derived_condition": True}, visiting)
        elif n.attrs.get("unsupported") \
                and not self.g.producers_of(node_id):
            result = None                     # explicitly unsupported: honest dead end
        elif n.category == "state":
            result = self._via_producers_and_requires(n, visiting)
        elif n.category == "event":
            if n.basis == "uncertain" or \
                    n.attrs.get("step_kind") == "uncertain_exogenous":
                result = {"node": node_id, "root": "explicit_uncertainty"}
            elif n.attrs.get("when"):
                result = self._with_requires(
                    n, {"node": node_id, "root": "scheduled_event"}, visiting)
            elif n.attrs.get("anchor"):
                anchors = self.g.edges_from(node_id, "scheduled_at")
                sub = [t for e in anchors
                       if (t := self.rooted(e.dst, visiting))]
                if sub:
                    result = self._with_requires(
                        n, {"node": node_id, "root": "scheduled_event",
                            "anchored_to": sub[0]["node"]}, visiting)
        elif n.category == "action":
            if self.g.performers_of(node_id):
                result = self._with_requires(
                    n, {"node": node_id, "root": "actor_choice"}, visiting)
        elif n.category == "process":
            result = self._with_requires(
                n, {"node": node_id, "root": "process"}, visiting)
        elif n.category == "information":
            if self.g.edges_to(node_id, "knows"):
                result = {"node": node_id, "root": "initially_known"}
            else:
                result = self._via_producers_and_requires(n, visiting)
        elif n.category == "record":
            result = self._via_producers_and_requires(n, visiting)
        elif n.category == "resource":
            if n.attrs.get("amount") is not None:
                result = {"node": node_id, "root": "initial_resource"}
            else:
                result = self._via_producers_and_requires(n, visiting)

        # A positive answer is valid regardless of what was mid-traversal;
        # a negative found while other nodes were in progress may only mean
        # "not via this path", so it must not be cached.
        if result is not None or not _visiting:
            self.memo[node_id] = result
        return result

    def _via_producers_and_requires(self, n, visiting):
        producers = self.g.producers_of(n.id)
        chains = []
        for p in producers:
            t = self.rooted(p, visiting)
            if t is not None:
                chains.append(t)
        if not chains:
            return None
        base = {"node": n.id, "via": chains[0]}
        return self._with_requires(n, base, visiting)

    def _with_requires(self, n, base, visiting):
        """All necessary prerequisites (and one per alternative group) must
        themselves be rooted."""
        needed, groups = [], {}
        for e in self.g.prerequisites_of(n.id):
            nec = e.attrs.get("necessity", "necessary")
            if nec == "necessary":
                needed.append(e.dst)
            elif nec == "alternative":
                groups.setdefault(e.attrs.get("alt_group"), []).append(e.dst)
        prereq_trees = []
        for dst in needed:
            t = self.rooted(dst, visiting)
            if t is None:
                return None
            prereq_trees.append(t)
        for group, members in sorted(groups.items()):
            sub = [t for m in members if (t := self.rooted(m, visiting))]
            if not sub:
                return None
            prereq_trees.append({"alt_group": group, "satisfied_by": sub[0]})
        if prereq_trees:
            base = dict(base)
            base["prerequisites"] = prereq_trees
        return base

    def why_not(self, node_id: str, _visiting: frozenset = frozenset()) -> list:
        """Precise reasons a node is unreachable, for refusal messages."""
        if node_id in _visiting:
            return [f"{node_id}: circular requirement with no external root"]
        visiting = _visiting | {node_id}
        n = self.g.node(node_id)
        if self.rooted(node_id) is not None:
            return []
        if n.attrs.get("unsupported"):
            teach = ""
            if n.category in ("resource", "record"):
                teach = (". A measured quantity or record is never a "
                         "conjunction: its value only changes through "
                         "real mechanisms -- attach the scheduled "
                         "transfers, processes or actions that change it "
                         "as its producers")
            return [f"{n.id}: explicitly marked unsupported "
                    f"({n.attrs['unsupported']}){teach}"]
        reasons = []
        if n.category == "action" and not self.g.performers_of(node_id):
            reasons.append(f"{n.id}: an action nobody can_perform")
        if n.category == "event" and not (
                n.attrs.get("when") or n.attrs.get("anchor")
                or n.basis == "uncertain"):
            reasons.append(f"{n.id}: an event with no schedule, no anchor "
                           f"and no declared uncertainty")
        if n.category in ("state", "record", "information", "resource") \
                and not n.attrs.get("initial") \
                and n.attrs.get("amount") is None:
            producers = self.g.producers_of(node_id)
            prereqs = [e for e in self.g.prerequisites_of(node_id)
                       if e.attrs.get("necessity", "necessary")
                       != "optional"]
            if not producers and not prereqs:
                reasons.append(f"{n.id}: nothing in the world produces it")
            else:
                for p in producers:
                    reasons.extend(self.why_not(p, visiting))
        for e in self.g.prerequisites_of(node_id):
            if e.attrs.get("necessity", "necessary") == "necessary" \
                    and self.rooted(e.dst) is None:
                reasons.extend(self.why_not(e.dst, visiting))
        return reasons or [f"{n.id}: unreachable"]


# ---------------------------------------------------------------------------
# backward causal proof
# ---------------------------------------------------------------------------

def backward_causal_proof(graph: WorldGraph) -> dict:
    term = graph.terminal()
    components = graph.measured_components()
    if not components:
        raise NoCausalProducer(
            "the terminal measures nothing: no state, record or resource "
            "carries a measured_by_terminal edge")

    r = _Rootedness(graph)
    failures, proof_components, warnings = [], [], []
    genesis_only = []

    for cid in components:
        node = graph.node(cid)
        tree = r.rooted(cid)
        if tree is None:
            failures.extend(r.why_not(cid))
            continue
        producers = graph.producers_of(cid)
        producer_cats = sorted({graph.node(p).category for p in producers})

        # report-vs-process (structural half): a component produced only by
        # communication channels is a delivery, not the underlying act.
        channel_only = producers and all(
            graph.node(p).category == "process"
            and graph.node(p).attrs.get("role") == "channel"
            for p in producers)
        if channel_only and not term.attrs.get("resolves_from_report"):
            failures.append(
                f"{cid}: produced only by communication channels; a report "
                f"or delivery cannot replace the process it reports unless "
                f"the question explicitly resolves from the report")

        # direct terminal write by an actor
        measured_act = term.attrs.get("measured_act")
        measured_act_id = graph.maybe("action", measured_act) \
            if measured_act else None
        for p in producers:
            pn = graph.node(p)
            if pn.category == "action" and p != measured_act_id:
                necessary = [e for e in graph.prerequisites_of(p)
                             if e.attrs.get("necessity", "necessary")
                             != "optional"]
                if not necessary:
                    failures.append(
                        f"{cid}: action {p} writes this terminal component "
                        f"with no prerequisites; an actor cannot write the "
                        f"answer directly unless the resolution contract "
                        f"names that act as the measured terminal "
                        f"(measured_act={measured_act!r})")
            if pn.category == "event" \
                    and pn.basis not in SCHEDULE_BASES_FOR_TERMINAL:
                failures.append(
                    f"{cid}: scheduled event {p} (basis {pn.basis!r}) writes "
                    f"this terminal component; an inferred or unverified "
                    f"schedule may not assert the answer -- inferred chains "
                    f"must be simulated, not scheduled")

        initially_true = bool(node.attrs.get("initial"))
        if initially_true and not producers:
            genesis_only.append(cid)
        proof_components.append({
            "component": cid, "chain": tree,
            "producers": producers, "producer_categories": producer_cats,
            "initially_true": initially_true,
            "immutable_after_genesis": initially_true and not producers})

    if failures:
        raise NoCausalProducer(
            "terminal production fails the backward causal proof",
            {"defects": sorted(set(failures)), "repairable": True})

    if term.attrs.get("answer_type") == "boolean":
        initially_true = [c["component"] for c in proof_components
                          if c["initially_true"]]
        if initially_true and len(initially_true) == len(components):
            raise NoCausalProducer(
                "initialization itself satisfies the terminal: every "
                "measured component is already true at genesis, so the "
                "answer exists before anything happens",
                {"components": initially_true})
        if initially_true:
            warnings.append(
                f"components already true at genesis: {initially_true}; "
                f"the answer must not hinge on them alone")

    uncertain_roots = sorted(
        {c["component"] for c in proof_components
         if _tree_has_root(c["chain"], "explicit_uncertainty")})

    return {"terminal": term.id,
            "components": proof_components,
            "genesis_only_components": genesis_only,
            "components_rooted_in_uncertainty": uncertain_roots,
            "warnings": warnings}


def _tree_has_root(tree, kind: str) -> bool:
    if not isinstance(tree, dict) or not tree:
        return False
    if tree.get("root") == kind:
        return True
    for key in ("via", "satisfied_by"):
        sub = tree.get(key)
        if isinstance(sub, dict) and sub and _tree_has_root(sub, kind):
            return True
    return any(_tree_has_root(t, kind)
               for t in tree.get("prerequisites") or [])


# ---------------------------------------------------------------------------
# forward executability proof
# ---------------------------------------------------------------------------

def forward_executability_proof(graph: WorldGraph) -> dict:
    r = _Rootedness(graph)
    failures, warnings = [], []

    # 1. something can actually happen from genesis
    scheduled = [n.id for n in graph.by_category("event")
                 if n.attrs.get("when")
                 or (n.attrs.get("anchor") and r.rooted(n.id))]
    operating = [n.id for n in graph.by_category("process")
                 if n.attrs.get("role") != "channel"]
    if not scheduled and not operating:
        raise NothingScheduled(
            "no scheduled event and no operating process: time would never "
            "advance and no actor would ever be woken",
            {"events": [n.id for n in graph.by_category("event")],
             "processes": [n.id for n in graph.by_category("process")]})

    # anchored events must chain to a real schedule
    for n in graph.by_category("event"):
        if n.attrs.get("anchor") and r.rooted(n.id) is None:
            failures.append(
                f"{n.id}: anchored to something that can never occur "
                f"({n.attrs['anchor'].get('event')!r})")

    # 2. channels connect real senders to real receivers
    channels = []
    for ch in graph.by_category("process"):
        if ch.attrs.get("role") != "channel":
            continue
        senders = sorted({e.src for e in graph.edges_to(ch.id, "sends_to")})
        receivers = sorted({e.src for e in
                            graph.edges_to(ch.id, "receives_from")})
        channels.append({"channel": ch.id, "senders": senders,
                         "receivers": receivers})
        if not senders or not receivers:
            warnings.append(
                f"{ch.id}: a route with "
                f"{'no senders' if not senders else 'no receivers'} is dead "
                f"and can carry nothing")

    # 3. required information can become locally available
    info_paths = []
    for act in graph.by_category("action"):
        needs = [e.dst for e in graph.prerequisites_of(act.id)
                 if graph.node(e.dst).category == "information"
                 and e.attrs.get("necessity", "necessary") != "optional"]
        if not needs:
            continue
        for performer in graph.performers_of(act.id):
            p_channels = {e.dst for e in
                          graph.edges_from(performer, "receives_from")}
            p_knows = {e.dst for e in graph.edges_from(performer, "knows")}
            p_observes = {e.dst for e in
                          graph.edges_from(performer, "observes")}
            for info in needs:
                if info in p_knows:
                    info_paths.append({"action": act.id, "actor": performer,
                                       "information": info,
                                       "how": "initially_known"})
                    continue
                if r.rooted(info) is None:
                    failures.append(
                        f"{act.id}: requires {info}, which nothing in the "
                        f"world can produce")
                    continue
                producers = graph.producers_of(info)
                observed = [p for p in producers if p in p_observes]
                if observed:
                    info_paths.append({"action": act.id, "actor": performer,
                                       "information": info,
                                       "how": f"observes {observed[0]}"})
                    continue
                if not p_channels:
                    failures.append(
                        f"{act.id}: performer {performer} needs {info} but "
                        f"receives on no channel and observes none of its "
                        f"producers; the information can never become "
                        f"locally available to them")
                    continue
                # someone able to produce or holding the information must be
                # able to send on a channel the performer receives from
                senders_ok = []
                for ch in sorted(p_channels):
                    ch_senders = {e.src for e in
                                  graph.edges_to(ch, "sends_to")}
                    holders = {e.src for e in graph.edges_to(info, "knows")}
                    prod_actors = set()
                    for p in producers:
                        pn = graph.node(p)
                        if pn.category == "action":
                            prod_actors.update(graph.performers_of(p))
                        elif pn.category in ACTORS:
                            prod_actors.add(p)
                    if ch_senders & (holders | prod_actors):
                        senders_ok.append(ch)
                if senders_ok:
                    info_paths.append({"action": act.id, "actor": performer,
                                       "information": info,
                                       "how": f"via {senders_ok[0]}"})
                else:
                    failures.append(
                        f"{act.id}: no channel {performer} receives from has "
                        f"a sender who holds or can produce {info}")
    # Blocked-window coverage of attention needs real calendar arithmetic
    # and is verified at lowering, not here.

    # 4. every action's necessary preconditions are reachable
    for act in graph.by_category("action"):
        if not graph.performers_of(act.id):
            failures.append(f"{act.id}: an action nobody can_perform can "
                            f"never run")
            continue
        if r.rooted(act.id) is None:
            failures.extend(r.why_not(act.id))

    # 5. authority declared over an action must cover a performer
    for act in graph.by_category("action"):
        holders = sorted({e.src for e in
                          graph.edges_to(act.id, "has_authority")})
        if holders:
            performers = set(graph.performers_of(act.id))
            if not performers & set(holders):
                failures.append(
                    f"{act.id}: authority over it is held by {holders} but "
                    f"its performers are {sorted(performers)}; nobody "
                    f"authorized can actually do it")

    # 6. non-channel processes must change something
    for pr in graph.by_category("process"):
        if pr.attrs.get("role") == "channel":
            continue
        outputs = graph.edges_from(pr.id, "changes") \
            + graph.edges_from(pr.id, "produces")
        if not outputs:
            warnings.append(f"{pr.id}: a process that changes nothing is "
                            f"decorative")

    # 7. the terminal can still emerge after genesis
    term = graph.terminal()
    components = graph.measured_components()
    emergent = [c for c in components
                if r.rooted(c) is not None and (
                    graph.producers_of(c)
                    or not graph.node(c).attrs.get("initial"))]
    if not emergent and term.attrs.get("answer_type") == "boolean":
        failures.append(
            "no measured component can change after genesis; the terminal "
            "cannot emerge from the trajectory")

    if failures:
        raise InvalidReference(
            "the world cannot execute from genesis",
            {"defects": sorted(set(failures)), "repairable": True})

    return {"scheduled_roots": scheduled,
            "operating_processes": operating,
            "channels": channels,
            "information_paths": sorted(
                info_paths, key=lambda p: (p["action"], p["actor"],
                                           p["information"])),
            "parameter_binding": "deferred to the binding stage",
            "emergent_components": emergent,
            "warnings": sorted(set(warnings))}
