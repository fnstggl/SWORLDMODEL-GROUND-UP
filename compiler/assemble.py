"""Deterministic assembly: five small discovery documents -> one canonical
world graph.

The discovery calls (compiler/discovery.py) return natural-language
documents with small structured fields and NO identifiers. This module is
the builder the directive describes: it walks those documents in a fixed
order, performs only the small builder operations (define_outcome,
add_causal_step, connect_prerequisite, attach_producer, add_initial_state,
add_information_boundary, add_authority, add_scheduled_event, add_process,
add_uncertainty, exclude_as_irrelevant), and owns every ID, reference and
connection. It makes zero model calls and invents no meaning: every node's
name, meaning and provenance come verbatim from a discovery document, and
anything that does not resolve is refused with the exact defect.

Shape validation reports ALL defects of a document at once, so a targeted
repair of that one discovery step can fix everything in one round.
"""
from __future__ import annotations

from .errors import InvalidReference, SemanticAmbiguity
from .graph import ACTORS, GRAPH_BASES, WorldGraph
from .symbols import slug

# -- closed mappings --------------------------------------------------------

#: Causal-spine step kinds -> node categories. An actor decision becomes an
#: ``action`` (what someone CAN do); nothing here can schedule a decision.
STEP_KINDS = {
    "initial_fact": "state",
    "condition": "state",
    "scheduled_event": "event",
    "actor_decision": "action",
    "organization_action": "action",
    "population_response": "action",
    "process": "process",
    "uncertain_exogenous": "event",
}

#: Producer kinds (discovery STEP 3 vocabulary) -> node categories.
PRODUCER_KINDS = {
    "person": "participant",
    "organization": "organization",
    "external_institution": "organization",
    "institutional_rule": "organization",
    "population": "population",
    "communication_system": "process",
    "operating_process": "process",
    "physical_process": "process",
    "scheduled_event": "event",
}

ANSWER_TYPES = ("boolean", "quantity", "choice")
PROOF_KINDS = ("record", "state", "quantity")


def _prov(item: dict, where: str, defects: list) -> tuple:
    """Per-item provenance is mandatory; sub-fields inherit it."""
    basis = item.get("basis")
    ids = item.get("evidence_ids") or []
    if basis not in GRAPH_BASES:
        defects.append(f"{where}: basis must be one of {GRAPH_BASES}, "
                       f"got {basis!r}")
        return "uncertain", []
    if basis in ("verified", "inferred") and not ids:
        defects.append(f"{where}: {basis!r} claim cites no evidence_ids")
    return basis, list(ids)


def _need(item: dict, keys: tuple, where: str, defects: list) -> bool:
    ok = True
    for k in keys:
        v = item.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            defects.append(f"{where}: missing {k!r}")
            ok = False
    return ok


class Assembler:
    """Builds the canonical graph. One instance per compilation."""

    def __init__(self, valid_evidence_ids=None) -> None:
        self.graph = WorldGraph(valid_evidence_ids)
        self.trace: list[dict] = []
        self._proof_components: dict[str, str] = {}   # component name -> id
        self._step_ids: dict[str, str] = {}           # step name -> id
        self._deferred_holders: list[tuple] = []      # (resource_id, holder name)

    def _record(self, op: str, inputs: dict, created=(), edges=()) -> None:
        self.trace.append({
            "op": op, "inputs": inputs, "created": sorted(created),
            "edges": sorted([e.src, e.rel, e.dst] for e in edges)})

    # ------------------------------------------------------------------
    # define_outcome
    # ------------------------------------------------------------------
    def define_outcome(self, resolution: dict) -> str:
        d: list = []
        _need(resolution, ("terminal_meaning", "positive_condition"),
              "resolution", d)
        if resolution.get("answer_type") not in ANSWER_TYPES:
            d.append(f"resolution: answer_type must be one of {ANSWER_TYPES}")
        cutoff = resolution.get("cutoff") or {}
        _need(cutoff, ("when", "timezone"), "resolution.cutoff", d)
        proof = resolution.get("proof") or []
        if not proof:
            d.append("resolution: 'proof' must name at least one observable "
                     "record, state or quantity that would prove the outcome")
        basis, ids = _prov(resolution, "resolution", d)
        for i, p in enumerate(proof):
            w = f"resolution.proof[{i}]"
            _need(p, ("name", "meaning"), w, d)
            if p.get("kind") not in PROOF_KINDS:
                d.append(f"{w}: kind must be one of {PROOF_KINDS}")
            if p.get("kind") == "record" and not p.get("record_type"):
                d.append(f"{w}: a record proof needs record_type")
        ambiguities = resolution.get("ambiguities") or []
        if ambiguities:
            d.append("resolution: unresolved ambiguities were declared and "
                     "must stop compilation upstream: " + "; ".join(
                         str(a) for a in ambiguities))
        if d:
            raise SemanticAmbiguity(
                "resolution contract has defects", {"defects": d})

        term_id = self.graph.add_node(
            "terminal", "terminal", resolution["terminal_meaning"], basis, ids,
            attrs={
                "answer_type": resolution["answer_type"],
                "cutoff": dict(cutoff),
                "positive_condition": resolution["positive_condition"],
                "negative_condition": resolution.get("negative_condition"),
                "resolves_from_report": bool(
                    resolution.get("resolves_from_report")),
                "measured_act": resolution.get("measured_act"),
            }, where="resolution")
        created, edges = [term_id], []
        for p in proof:
            cat = {"record": "record", "state": "state",
                   "quantity": "resource"}[p["kind"]]
            attrs = {}
            if p["kind"] == "record":
                attrs = {"record_type": p["record_type"],
                         "subject": p.get("subject"),
                         "rule": p.get("rule"),
                         "value": p.get("value"),
                         "expected_count": p.get("expected_count")}
            elif p["kind"] == "quantity":
                attrs = {"unit": p.get("unit"),
                         "holder_name": p.get("holder"),
                         "holder_kind": p.get("holder_kind",
                                              "organization"),
                         "amount_at_least": p.get("amount_at_least")}
            nid = self.graph.add_node(cat, p["name"], p["meaning"], basis, ids,
                                      attrs=attrs, where="resolution.proof")
            if p["kind"] == "quantity" and p.get("holder"):
                self._deferred_holders.append((nid, p["holder"]))
            edges.append(self.graph.add_edge(nid, "measured_by_terminal",
                                             term_id, where="resolution"))
            self._proof_components[p["name"]] = nid
            created.append(nid)
        self._record("define_outcome",
                     {"answer_type": resolution["answer_type"],
                      "cutoff": cutoff.get("when")}, created, edges)
        return term_id

    # ------------------------------------------------------------------
    # causal spine
    # ------------------------------------------------------------------
    def add_causal_step(self, step: dict) -> str:
        d: list = []
        _need(step, ("name", "meaning"), f"step {step.get('name')!r}", d)
        kind = step.get("kind")
        if kind not in STEP_KINDS:
            d.append(f"step {step.get('name')!r}: kind must be one of "
                     f"{tuple(STEP_KINDS)}, got {kind!r}")
        basis, ids = _prov(step, f"step {step.get('name')!r}", d)
        if kind == "uncertain_exogenous" and basis != "uncertain":
            d.append(f"step {step.get('name')!r}: an uncertain_exogenous "
                     f"step must carry basis 'uncertain', got {basis!r}")
        if d:
            raise SemanticAmbiguity("causal step has defects", {"defects": d})

        name = step["name"]
        # A condition step that IS the measured outcome binds to the proof
        # component instead of duplicating it -- whether it matches by
        # name, or says so via produces_proof (a condition does not
        # "produce" the outcome; it is the outcome under another wording).
        if name not in self._proof_components \
                and kind in ("condition", "initial_fact"):
            declared = list(step.get("produces_proof") or [])
            if len(declared) == 1 and declared[0] in self._proof_components:
                cid = self._proof_components[declared[0]]
                self._step_ids[name] = cid
                self.graph.absorb(cid, step["meaning"], basis, ids,
                                  where=f"step {name!r}")
                if kind == "initial_fact":
                    self.graph.node(cid).attrs["initial"] = True
                self._record("add_causal_step",
                             {"name": name, "kind": kind,
                              "bound_to": cid, "via": "produces_proof"},
                             [], [])
                return cid
        if name in self._proof_components:
            nid = self._proof_components[name]
            cat = self.graph.node(nid).category
            if kind not in ("condition", "initial_fact"):
                raise SemanticAmbiguity(
                    f"step {name!r} has kind {kind!r} but names the terminal "
                    f"proof component {nid}; only a condition can be measured "
                    f"by the terminal -- the {kind} that brings it about must "
                    f"be a separate step")
            self._step_ids[name] = nid
            self.graph.absorb(nid, step["meaning"], basis, ids,
                              where=f"step {name!r}")
            if kind == "initial_fact":
                self.graph.node(nid).attrs["initial"] = True
            self._record("add_causal_step",
                         {"name": name, "kind": kind, "bound_to": nid}, [], [])
            return nid

        cat = STEP_KINDS[kind]
        attrs = {"step_kind": kind}
        if cat == "state":
            attrs["initial"] = (kind == "initial_fact")
        if kind == "scheduled_event":
            when, anchor = step.get("when"), step.get("anchor")
            if not when and not anchor:
                raise SemanticAmbiguity(
                    f"step {name!r}: a scheduled_event needs 'when' (a real "
                    f"calendar time) or 'anchor' (relative to another event); "
                    f"an event with neither is not scheduled",
                    {"defects": [f"step {name!r}: no when/anchor"]})
            attrs["when"] = when
            attrs["anchor"] = anchor
        if step.get("uncertainty"):
            attrs["uncertainty"] = str(step["uncertainty"])
        nid = self.graph.add_node(cat, name, step["meaning"], basis, ids,
                                  attrs=attrs, where=f"step {name!r}")
        self._step_ids[name] = nid
        edges = []
        if step.get("uncertainty"):
            self.graph.add_uncertainty(nid, str(step["uncertainty"]))
        self._record("add_causal_step", {"name": name, "kind": kind},
                     [nid], edges)
        return nid

    def connect_prerequisite(self, step_name: str, prereq: dict) -> None:
        d: list = []
        _need(prereq, ("step",), f"prerequisite of {step_name!r}", d)
        if d:
            raise SemanticAmbiguity("prerequisite has defects", {"defects": d})
        src = self._resolve_step(step_name, f"prerequisite of {step_name!r}")
        dst = self._resolve_step(prereq["step"],
                                 f"prerequisite {prereq['step']!r}")
        src_node = self.graph.node(src)
        if src_node.category == "state" and src_node.attrs.get("initial"):
            raise SemanticAmbiguity(
                f"initial fact {step_name!r} cannot have prerequisites: "
                f"it is already true at genesis")
        e = self.graph.add_edge(
            src, "requires", dst,
            {"necessity": prereq.get("necessity", "necessary"),
             "alt_group": prereq.get("alt_group")},
            where=f"prerequisite of {step_name!r}")
        self._record("connect_prerequisite",
                     {"step": step_name, "requires": prereq["step"]}, [], [e])

    def _resolve_step(self, name: str, where: str) -> str:
        if name in self._step_ids:
            return self._step_ids[name]
        if name in self._proof_components:
            return self._proof_components[name]
        return self.graph.resolve_any(
            ("state", "event", "action", "process", "record", "resource"),
            name, where)

    # ------------------------------------------------------------------
    # producers
    # ------------------------------------------------------------------
    MECHANISM_KINDS = ("scheduled_event", "operating_process",
                      "physical_process", "communication_system")

    def attach_assignment(self, step_name: str, producers: list) -> None:
        """One step's full producer list. When a mechanism (a schedule, a
        process, a channel) is among the producers of a non-action step,
        the actors listed beside it OPERATE that mechanism -- they get
        authority over it, never a derived free choice. Only a step whose
        sole producers are actors is genuinely an actor's doing."""
        step_id = self._resolve_step(step_name,
                                     f"producers for {step_name!r}")
        step = self.graph.node(step_id)
        mechs = [p for p in producers
                 if p.get("kind") in self.MECHANISM_KINDS]
        rest = [p for p in producers
                if p.get("kind") not in self.MECHANISM_KINDS]
        for p in mechs:
            self.attach_producer(step_name, p)
        if mechs and step.category != "action":
            mech_ids = [self.graph.maybe(PRODUCER_KINDS[p["kind"]],
                                         p["name"]) for p in mechs]
            mech_ids = [m for m in mech_ids if m]
            for p in rest:
                d: list = []
                _need(p, ("name", "kind"), f"producer for {step_name!r}", d)
                basis, ids = _prov(p, f"producer for {step_name!r}", d)
                cat = PRODUCER_KINDS.get(p.get("kind"))
                if d or cat not in ACTORS:
                    self.attach_producer(step_name, p)
                    continue
                pid = self.graph.maybe(cat, p["name"])
                created = []
                if pid is None:
                    pid = self.graph.add_node(
                        cat, p["name"], p.get("meaning", ""), basis, ids,
                        attrs={"producer_kind": p["kind"]},
                        where=f"producer for {step_name!r}")
                    created.append(pid)
                else:
                    self.graph.absorb(pid, p.get("meaning", ""), basis,
                                      ids,
                                      where=f"producer for {step_name!r}")
                edges = [self.graph.add_edge(
                    pid, "has_authority", m,
                    {"meaning": p.get("meaning", "operates it")},
                    where=f"producer {step_name!r}") for m in mech_ids]
                self._record("attach_producer",
                             {"step": step_name, "producer": p["name"],
                              "kind": p["kind"], "operates": mech_ids},
                             created, edges)
        else:
            for p in rest:
                self.attach_producer(step_name, p)

    def attach_producer(self, step_name: str, producer: dict) -> None:
        d: list = []
        _need(producer, ("name", "kind"), f"producer for {step_name!r}", d)
        kind = producer.get("kind")
        if kind not in PRODUCER_KINDS:
            d.append(f"producer for {step_name!r}: kind must be one of "
                     f"{tuple(PRODUCER_KINDS)}, got {kind!r}")
        basis, ids = _prov(producer, f"producer for {step_name!r}", d)
        if d:
            raise SemanticAmbiguity("producer has defects", {"defects": d})

        step_id = self._resolve_step(step_name, f"producer for {step_name!r}")
        step = self.graph.node(step_id)
        cat = PRODUCER_KINDS[kind]
        if step.category == "process" and cat == "process":
            # a process step's process producer is either the same
            # mechanism (same name -> merge), an existing service the
            # instance depends on, or a service organization that
            # operates the instance ('the transit is carried out by the
            # Courier service'). All three are connections, not defects.
            existing = self.graph.maybe("process", producer["name"])
            if existing == step_id \
                    or slug(producer["name"]) == step_id.split(":", 1)[1]:
                self.graph.absorb(step_id, producer.get("meaning", ""),
                                  basis, ids,
                                  where=f"producer for {step_name!r}")
                self._record("attach_producer",
                             {"step": step_name,
                              "producer": producer["name"],
                              "kind": kind, "merged": True}, [], [])
                return
            if existing is not None:
                e = self.graph.add_edge(
                    step_id, "requires", existing,
                    where=f"producer {step_name!r}")
                self._record("attach_producer",
                             {"step": step_name,
                              "producer": producer["name"],
                              "kind": kind, "depends_on_service": True},
                             [], [e])
                return
            org = next((self.graph.maybe(c, producer["name"])
                        for c in ACTORS
                        if self.graph.maybe(c, producer["name"])), None)
            created = []
            if org is None:
                org = self.graph.add_node(
                    "organization", producer["name"],
                    producer.get("meaning", ""), basis, ids,
                    attrs={"producer_kind": kind},
                    where=f"producer for {step_name!r}")
                created.append(org)
            else:
                self.graph.absorb(org, producer.get("meaning", ""), basis,
                                  ids, where=f"producer for {step_name!r}")
            e = self.graph.add_edge(
                org, "has_authority", step_id,
                {"meaning": producer.get("meaning", "operates it")},
                where=f"producer {step_name!r}")
            self._record("attach_producer",
                         {"step": step_name, "producer": producer["name"],
                          "kind": kind, "operates_as_service": True},
                         created, [e])
            return
        pid = self.graph.maybe(cat, producer["name"])
        created = []
        if pid is None:
            attrs = {"producer_kind": kind}
            if kind == "communication_system":
                attrs["role"] = "channel"
            if cat == "event":
                when, anchor = producer.get("when"), producer.get("anchor")
                if not when and not anchor:
                    raise SemanticAmbiguity(
                        f"producer for {step_name!r}: a scheduled_event "
                        f"producer needs 'when' or 'anchor'")
                attrs["when"], attrs["anchor"] = when, anchor
            pid = self.graph.add_node(cat, producer["name"],
                                      producer.get("meaning", ""), basis, ids,
                                      attrs=attrs,
                                      where=f"producer for {step_name!r}")
            created.append(pid)
        else:
            self.graph.absorb(pid, producer.get("meaning", ""), basis, ids,
                              where=f"producer for {step_name!r}")

        edges = []
        if step.category == "action":
            if cat not in ACTORS:
                raise SemanticAmbiguity(
                    f"step {step_name!r} is an actor decision; its producer "
                    f"must be a person, organization or population, not a "
                    f"{kind}. A process cannot decide.")
            edges.append(self.graph.add_edge(pid, "can_perform", step_id,
                                             where=f"producer {step_name!r}"))
        elif cat in ACTORS and step.category == "process":
            # an actor "producing" a process operates it: authority, not a
            # derived action -- a process is not brought about, it runs
            edges.append(self.graph.add_edge(
                pid, "has_authority", step_id,
                {"meaning": producer.get("meaning", "operates it")},
                where=f"producer {step_name!r}"))
        elif cat in ACTORS and step.category == "event":
            # an actor named as a scheduled event's producer OPERATES it:
            # the schedule, not the actor, decides that it happens (the
            # event still carries its evidenced time), so this is
            # operatorship -- authority -- never a scheduled decision
            edges.append(self.graph.add_edge(
                pid, "has_authority", step_id,
                {"meaning": producer.get("meaning", "operates it")},
                where=f"producer {step_name!r}"))
        elif cat in ACTORS and step.category == "resource":
            mechanisms = self._nearest_mechanisms(step_id)
            if not mechanisms:
                raise SemanticAmbiguity(
                    f"step {step_name!r} is a measured quantity; "
                    f"{producer['name']!r} cannot simply bring it about. "
                    f"A quantity's value changes only through real "
                    f"mechanisms -- attach the scheduled transfers, "
                    f"dispatches or processes (already in the spine) as "
                    f"its producers")
            # 'the centre produces the stock' means it OPERATES the
            # dispatches in the stock's own causal chain
            for m in mechanisms:
                edges.append(self.graph.add_edge(
                    pid, "has_authority", m,
                    {"meaning": producer.get("meaning", "operates it")},
                    where=f"producer {step_name!r}"))
        elif cat in ACTORS and step.category == "record":
            raise SemanticAmbiguity(
                f"step {step_name!r} is a formal record; if "
                f"{producer['name']!r} truly makes it, the making is an "
                f"actor decision -- add it to the spine as kind "
                f"actor_decision (the act IS the record) -- otherwise "
                f"attach the institutional mechanism that produces it")
        elif cat in ACTORS:
            # A person producing a condition acts through an action. Derive
            # the universal plumbing: actor -can_perform-> action -produces->
            # condition. The action's meaning is exactly the discovery claim.
            act_name = f"bring about: {step_name}"
            act_id = self.graph.maybe("action", act_name)
            derived_meaning = \
                f"{producer['name']} can bring about: {step.meaning}"
            if act_id is None:
                act_id = self.graph.add_node(
                    "action", act_name, derived_meaning,
                    basis, ids, attrs={"derived_from_step": step_name},
                    where=f"producer for {step_name!r}")
                created.append(act_id)
                edges.append(self.graph.add_edge(
                    act_id, "produces", step_id,
                    where=f"producer {step_name!r}"))
                # bringing X about requires what X requires
                for e in self.graph.prerequisites_of(step_id):
                    if e.dst != act_id:
                        edges.append(self.graph.add_edge(
                            act_id, "requires", e.dst, dict(e.attrs),
                            where=f"producer {step_name!r}"))
            else:
                self.graph.absorb(act_id, derived_meaning, basis, ids,
                                  where=f"producer for {step_name!r}")
            edges.append(self.graph.add_edge(pid, "can_perform", act_id,
                                             where=f"producer {step_name!r}"))
        else:
            edges.append(self.graph.add_edge(
                pid, "produces", step_id, where=f"producer {step_name!r}"))
            if cat == "event" and self.graph.node(pid).attrs.get("anchor"):
                anchor = self.graph.node(pid).attrs["anchor"]
                anchor_id = self._resolve_step(
                    anchor.get("event", ""),
                    f"anchor of producer {producer['name']!r}")
                edges.append(self.graph.add_edge(
                    pid, "scheduled_at", anchor_id,
                    {"offset_minutes": anchor.get("offset_minutes"),
                     "meaning": anchor.get("meaning", "")},
                    where=f"producer {step_name!r}"))
        self._record("attach_producer",
                     {"step": step_name, "producer": producer["name"],
                      "kind": kind}, created, edges)

    def link_proof(self, step_name: str, proof_name: str) -> None:
        """A spine step that directly produces a terminal proof component."""
        sid = self._resolve_step(step_name, f"step {step_name!r}")
        if proof_name not in self._proof_components:
            raise SemanticAmbiguity(
                f"step {step_name!r} claims to produce {proof_name!r}, "
                f"which is not a terminal proof component "
                f"({sorted(self._proof_components)})")
        cid = self._proof_components[proof_name]
        if sid == cid:
            return                # the step IS the component; nothing to link
        e = self.graph.add_edge(sid, "produces", cid,
                                where=f"step {step_name!r}")
        self._record("produces_proof",
                     {"step": step_name, "proof": proof_name}, [], [e])

    def mark_unsupported(self, step_name: str, why: str) -> None:
        step_id = self._resolve_step(step_name, "unsupported step")
        node = self.graph.node(step_id)
        # models routinely write 'unsupported: no producer needed' for
        # things that genuinely need none -- initial facts, scheduled
        # events, and conjunction conditions. That is a benign note, not a
        # causal dead end; only a produceable thing with no producer is.
        needs_none = (
            node.attrs.get("initial")
            or node.category in ("event", "process")
            or (node.category == "state"
                and any(e.attrs.get("necessity", "necessary") != "optional"
                        for e in self.graph.prerequisites_of(step_id))))
        key = "no_producer_needed" if needs_none else "unsupported"
        node.attrs[key] = str(why)
        self._record("mark_unsupported",
                     {"step": step_name, "why": why, "benign": needs_none},
                     [], [])

    # ------------------------------------------------------------------
    # starting state and information boundaries
    # ------------------------------------------------------------------
    def add_initial_state(self, entity_name: str, item: dict) -> str:
        d: list = []
        _need(item, ("name", "meaning"), f"initial state of {entity_name!r}", d)
        basis, ids = _prov(item, f"initial state of {entity_name!r}", d)
        if d:
            raise SemanticAmbiguity("initial state has defects", {"defects": d})
        owner = self.graph.resolve_any(
            ACTORS + ("process", "resource"), entity_name,
            f"initial state of {entity_name!r}")
        nid = self.graph.maybe("state", item["name"])
        created = []
        if nid is None:
            nid = self.graph.add_node(
                "state", item["name"], item["meaning"], basis, ids,
                attrs={"initial": True, "value": item.get("value")},
                where=f"initial state of {entity_name!r}")
            created.append(nid)
        else:
            self.graph.absorb(nid, item["meaning"], basis, ids,
                              where=f"initial state of {entity_name!r}")
            node = self.graph.node(nid)
            node.attrs["initial"] = True
            if item.get("value") is not None:
                node.attrs["value"] = item.get("value")
        e = self.graph.add_edge(owner, "has_state", nid,
                                where=f"initial state of {entity_name!r}")
        self._record("add_initial_state",
                     {"entity": entity_name, "state": item["name"]},
                     created, [e])
        return nid

    def add_resource(self, entity_name: str, item: dict) -> str:
        d: list = []
        _need(item, ("name", "meaning"), f"resource of {entity_name!r}", d)
        if item.get("amount") is None:
            d.append(f"resource of {entity_name!r}: missing 'amount'")
        basis, ids = _prov(item, f"resource of {entity_name!r}", d)
        if d:
            raise SemanticAmbiguity("resource has defects", {"defects": d})
        owner = self.graph.resolve_any(ACTORS, entity_name,
                                       f"resource of {entity_name!r}")
        nid = self.graph.maybe("resource", item["name"])
        created = []
        if nid is None:
            nid = self.graph.add_node(
                "resource", item["name"], item["meaning"], basis, ids,
                attrs={"amount": item["amount"], "unit": item.get("unit"),
                       "holder": owner},
                where=f"resource of {entity_name!r}")
            created.append(nid)
        elif self.graph.node(nid).attrs.get("holder") not in (None, owner):
            # the same substance held by two parties is two stocks; code
            # disambiguates the second by its holder instead of refusing
            scoped = f"{item['name']} held by {entity_name}"
            nid = self.graph.maybe("resource", scoped)
            if nid is None:
                nid = self.graph.add_node(
                    "resource", scoped, item["meaning"], basis, ids,
                    attrs={"amount": item["amount"],
                           "unit": item.get("unit"), "holder": owner,
                           "substance": item["name"]},
                    where=f"resource of {entity_name!r}")
                created.append(nid)
        else:
            self.graph.absorb(nid, item["meaning"], basis, ids,
                              where=f"resource of {entity_name!r}")
            node = self.graph.node(nid)
            node.attrs.update({"amount": item["amount"],
                               "unit": item.get("unit") or node.attrs.get("unit"),
                               "holder": owner})
        self._record("add_resource",
                     {"entity": entity_name, "resource": item["name"],
                      "amount": item["amount"]}, created, [])
        return nid

    def add_scheduled_event(self, name: str, item: dict) -> str:
        d: list = []
        _need(item, ("meaning",), f"scheduled event {name!r}", d)
        basis, ids = _prov(item, f"scheduled event {name!r}", d)
        when, anchor = item.get("when"), item.get("anchor")
        if not when and not anchor:
            d.append(f"scheduled event {name!r}: needs 'when' or 'anchor'")
        if d:
            raise SemanticAmbiguity("scheduled event has defects",
                                    {"defects": d})
        nid = self.graph.maybe("event", name)
        created, edges = [], []
        if nid is None:
            nid = self.graph.add_node(
                "event", name, item["meaning"], basis, ids,
                attrs={"when": when, "anchor": anchor,
                       "step_kind": "scheduled_event"},
                where=f"scheduled event {name!r}")
            created.append(nid)
        else:
            self.graph.absorb(nid, item["meaning"], basis, ids,
                              where=f"scheduled event {name!r}")
        if item.get("involves"):
            who = self.graph.resolve_any(ACTORS, item["involves"],
                                         f"scheduled event {name!r}")
            edges.append(self.graph.add_edge(who, "observes", nid,
                                             where=f"scheduled event {name!r}"))
        if anchor:
            anchor_id = self._resolve_step(anchor.get("event", ""),
                                           f"anchor of {name!r}")
            edges.append(self.graph.add_edge(
                nid, "scheduled_at", anchor_id,
                {"offset_minutes": anchor.get("offset_minutes"),
                 "meaning": anchor.get("meaning", "")},
                where=f"scheduled event {name!r}"))
        self._record("add_scheduled_event", {"name": name, "when": when},
                     created, edges)
        return nid

    def add_sent_information(self, entity_name: str, item: dict) -> str:
        """A message already in flight from this entity as the world opens:
        real author, real recipients, real route, real send time."""
        d: list = []
        _need(item, ("name", "meaning", "channel", "sent_time"),
              f"sent information of {entity_name!r}", d)
        basis, ids = _prov(item, f"sent information of {entity_name!r}", d)
        to = item.get("to")
        if not isinstance(to, list) or not to:
            d.append(f"sent information of {entity_name!r}: 'to' must be a "
                     f"non-empty list of recipient names")
        if d:
            raise SemanticAmbiguity("sent information has defects",
                                    {"defects": d})
        w = f"sent information of {entity_name!r}"
        author = self.graph.resolve_any(ACTORS, entity_name, w)
        channel = self.graph.resolve_any(("process",), item["channel"], w)
        recipients = [self.graph.resolve_any(ACTORS, n, w) for n in to]
        iid = self.graph.maybe("information", item["name"])
        created = []
        if iid is None:
            iid = self.graph.add_node(
                "information", item["name"], item["meaning"], basis, ids,
                attrs={"visibility": "private"}, where=w)
            created.append(iid)
        else:
            self.graph.absorb(iid, item["meaning"], basis, ids, where=w)
        node = self.graph.node(iid)
        node.attrs["sent"] = {"author": author, "channel": channel,
                              "to": recipients,
                              "sent_time": item["sent_time"]}
        edges = [self.graph.add_edge(author, "knows", iid, where=w),
                 self.graph.add_edge(author, "sends_to", channel, where=w)]
        self._record("add_sent_information",
                     {"entity": entity_name, "information": item["name"]},
                     created, edges)
        return iid

    def set_entity_pattern(self, entity_name: str, timezone: str | None,
                           availability: dict | None) -> None:
        """The entity's real timezone and working/waking pattern; needed to
        anchor any checking cadence to real hours."""
        owner = self.graph.resolve_any(
            ACTORS, entity_name, f"pattern of {entity_name!r}")
        node = self.graph.node(owner)
        if timezone:
            node.attrs["timezone"] = str(timezone)
        if availability:
            node.attrs["availability"] = {
                "workdays": list(availability.get("workdays") or []),
                "open": availability.get("open"),
                "close": availability.get("close")}
        self._record("set_entity_pattern", {"entity": entity_name}, [], [])

    def add_process(self, name: str, behavior: dict) -> str:
        """Rate and operating behaviour for a process already in the world.
        The meanings stay natural language here; the binding stage maps
        them onto runtime rate/calendar mechanics or refuses."""
        d: list = []
        basis, ids = _prov(behavior, f"process behaviour of {name!r}", d)
        if d:
            raise SemanticAmbiguity("process behaviour has defects",
                                    {"defects": d})
        pid = self.graph.maybe("process", name)
        if pid is None:
            # the entity exists but not as a process: the behaviour claim
            # is a category mismatch -- kept visibly on the actor for the
            # reviewer, never a fatal defect
            actor = self.graph.resolve_any(
                ACTORS, name, f"process behaviour of {name!r}")
            self.graph.node(actor).attrs.setdefault(
                "declared_process_behavior", []).append(
                {k: behavior.get(k) for k in
                 ("meaning", "rate_meaning", "operating_meaning")})
            self._record("add_process",
                         {"name": name,
                          "dropped": "entity is not a process"}, [], [])
            return actor
        self.graph.absorb(pid, behavior.get("meaning", ""), basis, ids,
                          where=f"process behaviour of {name!r}")
        node = self.graph.node(pid)
        for key in ("rate_meaning", "operating_meaning"):
            if behavior.get(key):
                node.attrs[key] = behavior[key]
        self._record("add_process", {"name": name}, [], [])
        return pid

    def add_authority(self, entity_name: str, item: dict) -> None:
        d: list = []
        _need(item, ("over", "meaning"), f"authority of {entity_name!r}", d)
        basis, ids = _prov(item, f"authority of {entity_name!r}", d)
        if d:
            raise SemanticAmbiguity("authority has defects", {"defects": d})
        w = f"authority of {entity_name!r}"
        holder = self.graph.resolve_any(ACTORS, entity_name, w)
        try:
            over = self._resolve_step(item["over"], w)
        except InvalidReference:
            # an authority claim over something no document declared is
            # dropped VISIBLY: it lands on the holder for the reality
            # reviewer to judge, because authority only ever restricts --
            # dropping a claim can never enable a forbidden act
            self.graph.node(holder).attrs.setdefault(
                "dropped_authority_claims", []).append(
                {"over": item["over"], "meaning": item["meaning"]})
            self._record("add_authority",
                         {"entity": entity_name, "over": item["over"],
                          "dropped": "names nothing any document "
                                     "declared"}, [], [])
            return
        node = self.graph.node(over)
        edges = []
        if node.category in ("state", "resource"):
            # authority over a condition is authority over whatever can
            # produce it -- the condition itself is not an act
            producers = self.graph.producers_of(over)
            targets = [p for p in producers
                       if self.graph.node(p).category in
                       ("action", "process", "event")]
            if not targets:
                raise SemanticAmbiguity(
                    f"{w}: {item['over']!r} is a condition with no "
                    f"producer to hold authority over")
        elif node.category in ("action", "record", "process", "event"):
            targets = [over]
        else:
            raise SemanticAmbiguity(
                f"{w}: authority over a {node.category} has no meaning")
        for t in targets:
            edges.append(self.graph.add_edge(
                holder, "has_authority", t, {"meaning": item["meaning"]},
                where=w))
        self._record("add_authority",
                     {"entity": entity_name, "over": item["over"]},
                     [], edges)

    def add_information_boundary(self, entity_name: str, boundary: dict) -> None:
        """Initial knowledge, channel access with attention, and explicit
        non-access. Denial is structure here, not prose: a blocked window
        lands on the receives_from edge the proofs and lowering read."""
        owner = self.graph.resolve_any(
            ACTORS, entity_name, f"information boundary of {entity_name!r}")
        created, edges = [], []
        d: list = []
        for i, item in enumerate(boundary.get("knows") or []):
            w = f"{entity_name!r}.knows[{i}]"
            di: list = []
            _need(item, ("name", "meaning"), w, di)
            basis, ids = _prov(item, w, di)
            if di:
                d.extend(di)
                continue
            iid = self.graph.maybe("information", item["name"])
            if iid is None:
                iid = self.graph.add_node(
                    "information", item["name"], item["meaning"], basis, ids,
                    attrs={"visibility": item.get("visibility", "private")},
                    where=w)
                created.append(iid)
            else:
                self.graph.absorb(iid, item["meaning"], basis, ids, where=w)
            edges.append(self.graph.add_edge(owner, "knows", iid, where=w))
        for i, ch in enumerate(boundary.get("channels") or []):
            w = f"{entity_name!r}.channels[{i}]"
            di = []
            _need(ch, ("name", "meaning"), w, di)
            basis, ids = _prov(ch, w, di)
            role = ch.get("role", "both")
            if role not in ("sender", "receiver", "both"):
                di.append(f"{w}: role must be sender/receiver/both")
            if di:
                d.extend(di)
                continue
            cid = self.graph.maybe("process", ch["name"])
            if cid is None:
                cid = self.graph.add_node(
                    "process", ch["name"], ch["meaning"], basis, ids,
                    attrs={"role": "channel",
                           "latency_meaning": ch.get("latency_meaning")},
                    where=w)
                created.append(cid)
            else:
                self.graph.absorb(cid, ch["meaning"], basis, ids, where=w)
            if role in ("sender", "both"):
                edges.append(self.graph.add_edge(owner, "sends_to", cid,
                                                 where=w))
            if role in ("receiver", "both"):
                att = ch.get("attention") or {}
                edges.append(self.graph.add_edge(
                    owner, "receives_from", cid,
                    {"attention": {
                        "cadence_minutes": att.get("cadence_minutes"),
                        "meaning": att.get("meaning", ""),
                        "calendar_meaning": att.get("calendar_meaning"),
                        "blocked": list(att.get("blocked") or []),
                        "basis": basis,
                    }}, where=w))
        for i, na in enumerate(boundary.get("not_available") or []):
            w = f"{entity_name!r}.not_available[{i}]"
            di = []
            _need(na, ("meaning",), w, di)
            if di:
                d.extend(di)
                continue
            ch_name = na.get("channel")
            if ch_name:
                cid = self.graph.resolve_any(("process",), ch_name, w)
                blocked = {"from": na.get("from"), "to": na.get("to"),
                           "meaning": na["meaning"]}
                merged = False
                for e in self.graph.edges_from(owner, "receives_from"):
                    if e.dst == cid:
                        e.attrs.setdefault("attention", {}).setdefault(
                            "blocked", []).append(blocked)
                        merged = True
                if not merged:
                    raise SemanticAmbiguity(
                        f"{w}: {entity_name!r} has no receives_from access to "
                        f"{ch_name!r} to block; a channel they never receive "
                        f"on needs no denial")
            else:
                node = self.graph.node(owner)
                node.attrs.setdefault("not_available", []).append(
                    {"meaning": na["meaning"],
                     "from": na.get("from"), "to": na.get("to")})
        if d:
            raise SemanticAmbiguity(
                f"information boundary of {entity_name!r} has defects",
                {"defects": d})
        self._record("add_information_boundary", {"entity": entity_name},
                     created, edges)

    # ------------------------------------------------------------------
    # uncertainty and exclusions
    # ------------------------------------------------------------------
    def add_uncertainty(self, item: dict) -> None:
        d: list = []
        _need(item, ("about", "meaning"), "uncertainty", d)
        if d:
            raise SemanticAmbiguity("uncertainty has defects", {"defects": d})
        try:
            about = self.graph.resolve_any(
                ("state", "event", "action", "process", "record",
                 "resource", "participant", "organization", "population"),
                item["about"], "uncertainty")
            self.graph.add_uncertainty(about, item["meaning"])
        except (InvalidReference, SemanticAmbiguity):
            # honest uncertainty about something with no single node (a
            # rate, an arrival timing) is kept verbatim at world level
            self.graph.add_world_uncertainty(item["about"], item["meaning"])
        self._record("add_uncertainty", {"about": item["about"]}, [], [])

    def exclude_as_irrelevant(self, item: dict) -> None:
        d: list = []
        _need(item, ("name", "why_safe"), "exclusion", d)
        basis, ids = _prov(item, f"exclusion {item.get('name')!r}", d)
        if d:
            raise SemanticAmbiguity("exclusion has defects", {"defects": d})
        self.graph.add_exclusion(item["name"], item["why_safe"], basis, ids)
        self._record("exclude_as_irrelevant", {"name": item["name"]}, [], [])

    # ------------------------------------------------------------------
    # finish
    # ------------------------------------------------------------------
    def _nearest_mechanisms(self, node_id: str) -> list:
        """The first event or process on each prerequisite path, walking
        only through condition states. These are the mechanisms that
        directly move a quantity: the dispatch credits the stock; the
        collections behind the dispatch credit a different stock and are
        not descended into. Optional edges are walked too -- a quantity's
        parts are contributions, not gates, and a shipment that MAY
        arrive is exactly what the runtime should simulate."""
        out, seen, frontier = [], set(), [node_id]
        while frontier:
            cur = frontier.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for e in self.graph.prerequisites_of(cur):
                n = self.graph.node(e.dst)
                if n.category in ("event", "process") \
                        and n.attrs.get("role") != "channel":
                    if e.dst not in out:
                        out.append(e.dst)
                elif n.category == "state" and not n.attrs.get("initial"):
                    frontier.append(e.dst)
        return sorted(out)

    def derive_event_anchors(self) -> None:
        """An inferred event that depends on a verified event and carries
        its own time IS an anchored consequence: the verified schedule is
        the root and the inferred part is the offset (a transit, a
        turnaround), computed from the times the discovery itself gave.
        Nothing is invented; the dependency and both instants are the
        model's own claims, restated in the structure the runtime can
        carry honestly."""
        from datetime import datetime
        for ev in self.graph.by_category("event"):
            if ev.basis in ("verified", "question_given") \
                    or not ev.attrs.get("when") or ev.attrs.get("anchor"):
                continue
            try:
                t1 = datetime.fromisoformat(str(ev.attrs["when"]))
            except ValueError:
                continue
            for e in self.graph.prerequisites_of(ev.id):
                if e.attrs.get("necessity", "necessary") == "optional":
                    continue
                base = self.graph.node(e.dst)
                if base.category != "event" or not base.attrs.get("when"):
                    continue
                try:
                    t0 = datetime.fromisoformat(str(base.attrs["when"]))
                except ValueError:
                    continue
                if t1.tzinfo is None or t0.tzinfo is None:
                    continue
                offset = (t1 - t0).total_seconds() / 60.0
                edge = self.graph.add_edge(
                    ev.id, "scheduled_at", base.id,
                    {"offset_minutes": offset,
                     "meaning": f"{ev.name} follows {base.name} by "
                                f"{offset:g} minutes ({ev.basis})"},
                    where=f"anchor of {ev.name!r}")
                self._record("derive_event_anchor",
                             {"event": ev.name, "anchored_to": base.name,
                              "offset_minutes": offset}, [], [edge])
                break

    def derive_quantity_mechanisms(self) -> None:
        """Universal resource plumbing: a quantity with no direct producer
        but whose own prerequisite chain reaches events or processes is
        moved BY those mechanisms -- code connects them; the binding stage
        supplies the amounts from evidence. Nothing is invented: the spine
        itself asserted the dependency."""
        for rs in self.graph.by_category("resource"):
            if self.graph.producers_of(rs.id):
                continue
            for m in self._nearest_mechanisms(rs.id):
                rel = "produces" if self.graph.node(m).category == "event" \
                    else "changes"
                e = self.graph.add_edge(m, rel, rs.id,
                                        where=f"quantity mechanics of "
                                              f"{rs.name!r}")
                self._record("derive_quantity_mechanism",
                             {"resource": rs.name, "mechanism": m}, [], [e])

    def wire_operated_processes(self) -> None:
        """A continuous process with no stock connection, operated by an
        actor who holds exactly one stock, feeds that stock: the drive its
        centre runs collects into the centre's inventory. Deterministic
        connection from the graph's own operatorship and holdings; a
        process whose target stays ambiguous waits for its binding."""
        for pr in self.graph.by_category("process"):
            if pr.attrs.get("role") == "channel":
                continue
            if any(self.graph.node(e.dst).category == "resource"
                   for e in self.graph.edges_from(pr.id, "changes")
                   + self.graph.edges_from(pr.id, "produces")):
                continue
            operators = sorted({
                e.src for e in self.graph.edges_to(pr.id, "has_authority")})
            held = sorted({rs.id for rs in self.graph.by_category("resource")
                           for op in operators
                           if rs.attrs.get("holder") == op})
            if len(held) == 1:
                edge = self.graph.add_edge(
                    pr.id, "changes", held[0],
                    where=f"operated process {pr.name!r}")
                self._record("wire_operated_process",
                             {"process": pr.name, "stock": held[0]},
                             [], [edge])

    def materialize_holders(self) -> None:
        """A measured quantity's holder is a real entity even when it
        produces nothing (a hospital that only receives). It was named by
        the resolution contract, so creating it is connection, not
        invention. Runs after producers so an existing producer wins."""
        for rid, holder_name in self._deferred_holders:
            node = self.graph.node(rid)
            if node.attrs.get("holder"):
                continue
            existing = [nid for c in ACTORS
                        if (nid := self.graph.maybe(c, holder_name))]
            if existing:
                node.attrs["holder"] = existing[0]
                continue
            term = self.graph.terminal()
            hid = self.graph.add_node(
                node.attrs.get("holder_kind", "organization"), holder_name,
                f"holder of {node.name}, named by the resolution contract",
                term.basis, term.evidence_ids,
                where=f"holder of {node.name!r}")
            node.attrs["holder"] = hid
            self._record("materialize_holder",
                         {"resource": node.name, "holder": holder_name},
                         [hid], [])

    def finish(self) -> WorldGraph:
        defects = []
        for rid, holder_name in self._deferred_holders:
            node = self.graph.node(rid)
            if node.attrs.get("holder"):
                continue
            try:
                node.attrs["holder"] = self.graph.resolve_any(
                    ACTORS, holder_name, f"holder of {node.name!r}")
            except (InvalidReference, SemanticAmbiguity) as exc:
                defects.append(str(exc))
        # public information becomes known to every actor in the world
        actors = [n.id for c in ACTORS for n in self.graph.by_category(c)]
        edges = []
        for info in self.graph.by_category("information"):
            if info.attrs.get("visibility") == "public":
                for a in actors:
                    edges.append(self.graph.add_edge(a, "knows", info.id,
                                                     where="public info"))
        if defects:
            raise SemanticAmbiguity("assembly finished with defects",
                                    {"defects": defects})
        self._record("finish", {"actors": len(actors)}, [], edges)
        return self.graph


# ---------------------------------------------------------------------------
# the fixed assembly order
# ---------------------------------------------------------------------------

def _collect(defects: list, fn, *args) -> None:
    """Run one builder op, harvesting its defects instead of stopping, so a
    whole discovery document's problems surface in one refusal and one
    targeted repair round can fix them all."""
    try:
        fn(*args)
    except (SemanticAmbiguity, InvalidReference) as exc:
        listed = exc.detail.get("defects") if isinstance(exc.detail, dict) \
            else None
        defects.extend(listed or [exc.reason])


def _raise_if(defects: list, which: str) -> None:
    if defects:
        raise SemanticAmbiguity(
            f"the {which} document has defects",
            {"document": which, "defects": defects, "repairable": True})


def assemble(resolution: dict, spine: dict, producers: dict,
             state_info: dict, uncertainty: dict,
             valid_evidence_ids=None) -> tuple:
    """Discovery documents -> (WorldGraph, assembly trace).

    Fixed order: outcome, spine steps, prerequisites, producers, starting
    state and boundaries, uncertainty and exclusions. Deterministic: same
    documents, same graph, same trace. Defects are reported per document,
    all at once, naming the document a targeted repair should go to.
    """
    a = Assembler(valid_evidence_ids)
    a.define_outcome(resolution)

    d: list = []
    steps = spine.get("steps") or []
    if not steps:
        raise SemanticAmbiguity(
            "causal spine has no steps: nothing connects the terminal to "
            "the world", {"document": "causal_spine",
                          "defects": ["spine.steps is empty"],
                          "repairable": True})
    for step in steps:
        _collect(d, a.add_causal_step, step)
    for step in steps:
        if step.get("name") not in a._step_ids:
            continue                     # its creation already failed above
        for prereq in step.get("prerequisites") or []:
            _collect(d, a.connect_prerequisite, step["name"], prereq)
        for proof_name in step.get("produces_proof") or []:
            _collect(d, a.link_proof, step["name"], proof_name)
    _raise_if(d, "causal_spine")

    d = []
    for assignment in producers.get("assignments") or []:
        name = assignment.get("step")
        if not name:
            d.append("producer assignment missing 'step'")
            continue
        if assignment.get("unsupported"):
            _collect(d, a.mark_unsupported, name, assignment["unsupported"])
            continue
        plist = assignment.get("producers") or []
        if not plist:
            continue      # explicit none-needed; the post-check enforces
        _collect(d, a.attach_assignment, name, plist)
    # Derived plumbing first: anchors and quantity mechanisms count as
    # real producers for the check below.
    a.derive_event_anchors()
    a.derive_quantity_mechanisms()
    # Every causal step must now be producible or honestly unsupported.
    for name, sid in sorted(a._step_ids.items()):
        node = a.graph.node(sid)
        if node.attrs.get("unsupported"):
            continue
        if node.category == "action" and not a.graph.performers_of(sid):
            d.append(f"step {name!r}: an actor decision with nobody who "
                     f"can_perform it")
        elif node.category in ("state", "record", "resource") \
                and not node.attrs.get("initial") \
                and node.attrs.get("amount") is None \
                and not a.graph.producers_of(sid):
            if any(e.attrs.get("necessity", "necessary") != "optional"
                   for e in a.graph.prerequisites_of(sid)):
                # a condition WITH prerequisites is a conjunction: it
                # needs no producer of its own. The flag is explicit so
                # that an ablation which strips a real producer can never
                # be mistaken for a conjunction.
                node.attrs["conjunction"] = True
            else:
                d.append(f"step {name!r}: no producer is attached and it "
                         f"is not marked unsupported")
    _raise_if(d, "producer_assignments")
    a.materialize_holders()

    d = []
    for entity in state_info.get("entities") or []:
        name = entity.get("name")
        if not name:
            d.append("starting-state entity missing 'name'")
            continue
        if not any(a.graph.maybe(c, name) for c in
                   ACTORS + ("process", "resource")):
            # a stale projection: this entity was discovered against an
            # earlier producers document and the world no longer contains
            # it. Skipping is honest; inventing a node for it is not.
            a._record("skip_stale_entity", {"entity": name}, [], [])
            continue
        if entity.get("timezone") or entity.get("availability"):
            _collect(d, a.set_entity_pattern, name, entity.get("timezone"),
                     entity.get("availability"))
        for item in entity.get("initial_state") or []:
            _collect(d, a.add_initial_state, name, item)
        for item in entity.get("resources") or []:
            _collect(d, a.add_resource, name, item)
        for item in entity.get("commitments") or []:
            item = dict(item)
            item.setdefault("involves", name)
            _collect(d, a.add_scheduled_event,
                     item.get("name") or item.get("meaning", ""), item)
        for item in entity.get("sent_information") or []:
            _collect(d, a.add_sent_information, name, item)
        for item in entity.get("authority") or []:
            _collect(d, a.add_authority, name, item)
        if entity.get("process_behavior"):
            _collect(d, a.add_process, name, entity["process_behavior"])
        boundary = {k: entity.get(k) for k in
                    ("knows", "channels", "not_available")}
        if any(boundary.values()):
            _collect(d, a.add_information_boundary, name, boundary)
    _raise_if(d, "starting_state_and_information")
    a.wire_operated_processes()

    d = []
    for item in uncertainty.get("uncertainties") or []:
        _collect(d, a.add_uncertainty, item)
    for item in uncertainty.get("exclusions") or []:
        _collect(d, a.exclude_as_irrelevant, item)
    _raise_if(d, "uncertainty_and_exclusions")

    graph = a.finish()
    return graph, a.trace
