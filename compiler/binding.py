"""The controlled semantic-binding stage.

Between discovery and deterministic lowering sits one tightly controlled
translation step: for each semantic item -- one action, one channel, one
process, one event -- an LLM is shown the complete list of universal
runtime capabilities and the item's own graph context, and fills in ONLY
the small residue fields code cannot derive (a duration, a latency, a
rate, an amount, message content, who makes a record). It selects from
the catalog, fills small fields, or returns UNSUPPORTED. It cannot add
actors, facts, events, schedules, consequences, processes or uncertainty
resolutions: everything it returns is validated against the graph, and
anything else is refused.

Code derives the rest of the plumbing deterministically in the emitter:
message tags, noticed-information parameters, fact keys, preconditions
from requires edges, record dedup guards, wakes and recipients.

One targeted repair per item, tracked; a repaired binding is not a
first-pass success.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json

from .errors import (InvalidReference, LoweringGap, SemanticAmbiguity,
                     UnsupportedCapability)
from .graph import WorldGraph
from .llm import TruncatedResponse, call_json
from .schema import CHANGE_TYPES

STATUSES = ("verified", "inferred", "question_given",
            "model_memory_unverified")

_CATALOG = (
    "THE COMPLETE UNIVERSAL CAPABILITY LIST (there are no others; anything "
    "that cannot be expressed with these is UNSUPPORTED):\n"
    + "\n".join(f"- {k}: {v}" for k, v in CHANGE_TYPES.items())
    + "\nDurations, latencies and rates are concrete numbers with a "
      "status: \"verified\" when the item's evidence states the number, "
      "\"inferred\" when it follows from the item's evidence, "
      "\"question_given\" when the question fixes it, and "
      "\"model_memory_unverified\" when it is your own real-world "
      "estimate (an ordinary email takes minutes to write; corporate "
      "email delivers in seconds) -- that label is always allowed here "
      "and is the honest default for practice-based estimates. A "
      "genuinely unknowable number stays unknown: return null rather "
      "than inventing precision."
)

_RULES = (
    "You are the binding step of a world compiler. You translate ONE "
    "semantic item into the small fields named below -- nothing else. You "
    "must not invent new facts, participants, actions, events, schedules "
    "or consequences, and you must not resolve declared uncertainty. Use "
    "only names that appear in the item's context. If the item's meaning "
    "cannot be carried faithfully by the universal capabilities, return "
    "{\"unsupported\": \"<exact reason>\"}. Reply with a single JSON "
    "object.\n" + _CATALOG
)


@dataclass
class Bindings:
    actions: dict = field(default_factory=dict)
    channels: dict = field(default_factory=dict)
    processes: dict = field(default_factory=dict)
    events: dict = field(default_factory=dict)
    calls: list = field(default_factory=list)
    repairs: dict = field(default_factory=dict)
    tokens: int = 0
    unsupported: list = field(default_factory=list)


def _ask(item_id: str, user: str, validator, b: Bindings, call,
         model: str) -> dict | None:
    """One binding item: call, validate, at most one targeted repair.
    Returns None when the model declares the item unsupported."""
    doc, raw, defects = None, "", []
    for attempt in (0, 1):
        prompt = user if attempt == 0 else (
            user + "\n\nYOUR PREVIOUS ANSWER:\n" + raw
            + "\n\nEXACT DEFECTS -- fix ONLY these and return the complete "
              "corrected object:\n" + "\n".join(f"- {d}" for d in defects))
        try:
            doc, raw, usage = call(_RULES, prompt, model=model)
            parse_error = None
        except (TruncatedResponse, ValueError) as exc:
            doc, raw, usage = None, "", {}
            parse_error = f"reply unusable: {exc}"
        b.calls.append({"item": item_id, "attempt": attempt,
                        "prompt": {"system": _RULES, "user": prompt},
                        "raw_response": raw, "usage": usage})
        b.tokens += (usage or {}).get("total_tokens", 0)
        if parse_error:
            defects = [parse_error]
        elif isinstance(doc, dict) and doc.get("unsupported"):
            b.unsupported.append({"item": item_id,
                                  "reason": str(doc["unsupported"])})
            return None
        else:
            defects = validator(doc)
        if not defects:
            if attempt:
                b.repairs[item_id] = b.repairs.get(item_id, 0) + 1
            return doc
    raise SemanticAmbiguity(
        f"binding of {item_id} is still defective after one targeted repair",
        {"document": f"binding[{item_id}]", "defects": defects,
         "repairable": False})


def _status_ok(doc, key, defects, required=True):
    s = doc.get(key)
    if s is None and not required:
        return
    if s not in STATUSES:
        defects.append(f"{key} must be one of {STATUSES}, got {s!r}")


def _num(doc, key, defects, required=True, minimum=None):
    v = doc.get(key)
    if v is None:
        if required:
            defects.append(f"{key} is missing")
        return
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        defects.append(f"{key} must be a number, got {v!r}")
    elif minimum is not None and v < minimum:
        defects.append(f"{key} must be >= {minimum}")


def _describe_action(graph: WorldGraph, node) -> dict:
    """Everything the binding call may know about one action."""
    return {
        "action": node.name, "meaning": node.meaning,
        "performed_by": [graph.node(p).name
                         for p in graph.performers_of(node.id)],
        "needs": [{"what": graph.node(e.dst).name,
                   "category": graph.node(e.dst).category,
                   "meaning": graph.node(e.dst).meaning}
                  for e in graph.prerequisites_of(node.id)],
        "brings_about": [{"what": graph.node(e.dst).name,
                          "category": graph.node(e.dst).category,
                          "meaning": graph.node(e.dst).meaning,
                          "record_type": graph.node(e.dst).attrs.get(
                              "record_type"),
                          "holder": graph.node(e.dst).attrs.get("holder")}
                         for e in graph.edges_from(node.id, "produces")
                         + graph.edges_from(node.id, "changes")],
    }


def bind_world(graph: WorldGraph, evidence: dict | None = None,
               call=call_json, model: str = "deepseek-chat",
               into: Bindings | None = None) -> Bindings:
    """Bind every action, channel, process and record/resource-writing
    event. Raises UnsupportedCapability at the end if any item has no
    faithful universal form -- after trying them all, so the refusal names
    every gap at once. Pass ``into`` to keep the verbatim call log even
    when binding fails. The evidence rides along in every prompt: a
    number the evidence states must be cited from it, never guessed and
    never nulled for want of sight."""
    b = into if into is not None else Bindings()
    ev_text = ""
    if evidence:
        from .discovery import render_evidence
        ev_text = render_evidence(evidence) + "\n\n"

    for node in graph.by_category("action"):
        ctx = _describe_action(graph, node)
        wants_amounts = [t for t in ctx["brings_about"]
                         if t["category"] == "resource"]
        wants_records = [t for t in ctx["brings_about"]
                         if t["category"] == "record"]
        wants_info = [t for t in ctx["brings_about"]
                      if t["category"] == "information"]
        ask = (
            "THE ITEM (an action an actor may choose; it will NOT be "
            "scheduled):\n" + json.dumps(ctx, indent=1)
            + "\n\nReturn JSON with exactly these fields:\n"
            "  duration_minutes: number, how long performing it really "
            "takes; null ONLY if genuinely unknowable\n"
            "  duration_status: status for that number\n"
            "  duration_note: one line of real-world grounding\n"
            "  parameters: list of {\"name\", \"meaning\", "
            "\"allowed_values\": list ONLY when the real world restricts "
            "the options (a ballot's choices) -- never to pin a predicted "
            "value} for choices the actor makes when performing it; [] if "
            "none\n"
            + ("  record_values: for each record it creates, {record name: "
               "{\"value\": the value recorded, or "
               "{\"from_parameter\": parameter name} when the actor's own "
               "choice is what gets recorded, \"subject\": what it is "
               "about}}\n" if wants_records else "")
            + ("  amounts: for each resource it changes, {resource name: "
               "{\"kind\": \"transfer\"|\"adjust\", \"amount\": number, "
               "\"from\": holder name (transfer only), \"to\": holder "
               "name (transfer only)}}\n" if wants_amounts else "")
            + ("  message_contents: for each information it sends, "
               "{information name: one-sentence content}\n"
               if wants_info else ""))
        doc = _ask(f"action:{node.name}", ask, lambda d: _v_action(
            d, wants_records, wants_amounts, wants_info), b, call, model)
        if doc is not None:
            b.actions[node.id] = doc

    for node in graph.by_category("process"):
        if node.attrs.get("role") == "channel":
            senders = sorted({graph.node(e.src).name for e in
                              graph.edges_to(node.id, "sends_to")})
            ask = (ev_text + "THE ITEM (a communication route):\n"
                   + json.dumps({"route": node.name,
                                 "meaning": node.meaning,
                                 "latency_meaning":
                                     node.attrs.get("latency_meaning"),
                                 "used_by": senders}, indent=1)
                   + "\n\nReturn JSON exactly:\n"
                   "  delivery_seconds: number, realistic one-way delivery "
                   "latency\n"
                   "  status: status for that number\n"
                   "  note: one line of grounding")
            doc = _ask(f"channel:{node.name}", ask, _v_channel, b, call,
                       model)
            if doc is not None:
                b.channels[node.id] = doc
        else:
            outputs = [{"what": graph.node(e.dst).name,
                        "category": graph.node(e.dst).category,
                        "holder": graph.node(e.dst).attrs.get("holder")}
                       for e in graph.edges_from(node.id, "changes")
                       + graph.edges_from(node.id, "produces")]
            actors = sorted(n.name for c in ("participant", "organization",
                                             "population")
                            for n in graph.by_category(c))
            ask = (ev_text + "THE ITEM (a continuous process):\n"
                   + json.dumps({"process": node.name,
                                 "meaning": node.meaning,
                                 "rate_meaning":
                                     node.attrs.get("rate_meaning"),
                                 "operating_meaning":
                                     node.attrs.get("operating_meaning"),
                                 "outputs": outputs,
                                 "participants_in_world": actors}, indent=1)
                   + "\n\nReturn JSON exactly:\n"
                   "  amount_per_hour: number, the supported rate\n"
                   "  rate_status: status for that number\n"
                   "  rate_note: one line of grounding\n"
                   "  operating: {\"timezone\": IANA zone, \"workdays\": "
                   "[Monday=0..Sunday=6], \"start\": \"HH:MM\", \"end\": "
                   "\"HH:MM\"} or null if it runs continuously\n"
                   "  output_resource: {\"name\": the quantity it "
                   "accumulates, \"holder\": which listed participant's "
                   "stock it feeds} -- null only if 'outputs' above "
                   "already names a quantity\n"
                   "If this mechanism does no continuous quantitative "
                   "work (a role, or a wrapper around receiving/holding "
                   "that the transfers already account for), return "
                   "{\"decorative\": true, \"why\": one sentence} "
                   "instead.")
            doc = _ask(f"process:{node.name}", ask, _v_process, b, call,
                       model)
            if doc is not None:
                b.processes[node.id] = doc

    for node in graph.by_category("event"):
        targets = [{"what": graph.node(e.dst).name,
                    "category": graph.node(e.dst).category,
                    "record_type": graph.node(e.dst).attrs.get(
                        "record_type"),
                    "holder": graph.node(e.dst).attrs.get("holder")}
                   for e in graph.edges_from(node.id, "produces")
                   + graph.edges_from(node.id, "changes")]
        residue = [t for t in targets
                   if t["category"] in ("record", "resource",
                                        "information")]
        if not residue:
            continue
        actors = sorted(n.name for c in ("participant", "organization",
                                         "population")
                        for n in graph.by_category(c))
        ask = (ev_text + "THE ITEM (an external scheduled event; nobody decides it, "
               "it happens on its schedule):\n"
               + json.dumps({"event": node.name, "meaning": node.meaning,
                             "when": node.attrs.get("when"),
                             "brings_about": targets,
                             "participants_in_world": actors}, indent=1)
               + "\n\nReturn JSON exactly:\n"
               + ("  record_makers: for each record it creates, {record "
                  "name: {\"made_by\": participant name, \"value\": what "
                  "is recorded, \"subject\": what about}}\n"
                  if any(t["category"] == "record" for t in residue)
                  else "")
               + ("  amounts: for each resource it changes, {resource "
                  "name: {\"kind\": \"transfer\"|\"adjust\", \"amount\": "
                  "number, \"from\": holder, \"to\": holder}}\n"
                  if any(t["category"] == "resource" for t in residue)
                  else "")
               + ("  messages: for each information it delivers, "
                  "{information name: {\"from\": sender name, \"to\": "
                  "[recipient names], \"channel\": route name, "
                  "\"content\": one sentence}}\n"
                  if any(t["category"] == "information" for t in residue)
                  else ""))
        doc = _ask(f"event:{node.name}", ask,
                   lambda d: _v_event(d, residue), b, call, model)
        if doc is not None:
            b.events[node.id] = doc

    if b.unsupported:
        raise UnsupportedCapability(
            "semantic items with no faithful universal runtime form",
            {"items": b.unsupported, "calls": len(b.calls)})
    return b


def _v_action(doc, wants_records, wants_amounts, wants_info) -> list:
    d = []
    if not isinstance(doc, dict):
        return ["reply must be a JSON object"]
    _num(doc, "duration_minutes", d, required=False, minimum=0)
    if doc.get("duration_minutes") is not None:
        _status_ok(doc, "duration_status", d)
    if not isinstance(doc.get("parameters", []), list):
        d.append("parameters must be a list")
    for p in doc.get("parameters") or []:
        if not str(p.get("name") or "").strip():
            d.append("every parameter needs a name")
    if wants_records:
        rv = doc.get("record_values") or {}
        for t in wants_records:
            if t["what"] not in rv:
                d.append(f"record_values must cover {t['what']!r}")
    if wants_amounts:
        am = doc.get("amounts") or {}
        for t in wants_amounts:
            spec = am.get(t["what"])
            if not spec:
                d.append(f"amounts must cover {t['what']!r}")
                continue
            if spec.get("kind") not in ("transfer", "adjust"):
                d.append(f"amounts[{t['what']!r}].kind must be "
                         f"transfer or adjust")
            _num(spec, "amount", d)
    if wants_info:
        mc = doc.get("message_contents") or {}
        for t in wants_info:
            if not str(mc.get(t["what"]) or "").strip():
                d.append(f"message_contents must cover {t['what']!r}")
    return d


def _v_channel(doc) -> list:
    d = []
    if not isinstance(doc, dict):
        return ["reply must be a JSON object"]
    _num(doc, "delivery_seconds", d, minimum=0)
    _status_ok(doc, "status", d)
    return d


def _v_process(doc) -> list:
    d = []
    if not isinstance(doc, dict):
        return ["reply must be a JSON object"]
    if doc.get("decorative"):
        if not str(doc.get("why") or "").strip():
            d.append("a decorative marking needs 'why'")
        return d
    _num(doc, "amount_per_hour", d, minimum=0)
    _status_ok(doc, "rate_status", d)
    op = doc.get("operating")
    if op:
        if not str(op.get("timezone") or "").strip():
            d.append("operating.timezone is missing")
        if not isinstance(op.get("workdays"), list):
            d.append("operating.workdays must be a list")
        for k in ("start", "end"):
            if not str(op.get(k) or "").strip():
                d.append(f"operating.{k} is missing (HH:MM)")
    orr = doc.get("output_resource")
    if orr is not None:
        for k in ("name", "holder"):
            if not str(orr.get(k) or "").strip():
                d.append(f"output_resource.{k} is missing")
    return d


def connect_process_outputs(graph: WorldGraph, b: Bindings) -> None:
    """Deterministic connection, zero model calls: a process whose graph
    node does not yet change a quantity is wired to the stock its binding
    names. Resolution is holder-first (a holder's single stock needs no
    name match); anything unresolvable is a refusal, not a guess."""
    defects = []
    for pid, bound in sorted(b.processes.items()):
        if bound.get("decorative"):
            continue
        node = graph.node(pid)
        has_resource = any(
            graph.node(e.dst).category == "resource"
            for e in graph.edges_from(pid, "changes")
            + graph.edges_from(pid, "produces"))
        if has_resource:
            continue
        orr = bound.get("output_resource")
        if not orr:
            defects.append(
                f"{pid}: a continuous process must feed a quantity, but "
                f"neither the graph nor its binding names one")
            continue
        try:
            holder = graph.resolve_any(
                ("participant", "organization", "population"),
                orr["holder"], f"output of {pid}")
        except (InvalidReference, SemanticAmbiguity) as exc:
            defects.append(str(exc))
            continue
        held = [rs for rs in graph.by_category("resource")
                if rs.attrs.get("holder") == holder]
        from .symbols import slug as _slug
        match = [rs for rs in held
                 if _slug(orr["name"]) in rs.id or rs.id.endswith(
                     _slug(orr["name"]))]
        target = (held[0] if len(held) == 1 else
                  match[0] if len(match) == 1 else None)
        if target is None:
            defects.append(
                f"{pid}: cannot identify {orr['name']!r} held by "
                f"{orr['holder']!r} among {[r.id for r in held]}; if the "
                f"holder's opening stock of it was never declared, add it "
                f"to their starting-state resources")
            continue
        graph.add_edge(pid, "changes", target.id,
                       where=f"output of {pid}")
    if defects:
        raise LoweringGap(
            "process outputs cannot be connected to real stocks",
            {"defects": defects, "repairable": True,
             "document": "starting_state_and_information"})


def _v_event(doc, residue) -> list:
    d = []
    if not isinstance(doc, dict):
        return ["reply must be a JSON object"]
    for t in residue:
        if t["category"] == "record":
            spec = (doc.get("record_makers") or {}).get(t["what"])
            if not spec or not str(spec.get("made_by") or "").strip():
                d.append(f"record_makers must name made_by for "
                         f"{t['what']!r}")
        elif t["category"] == "resource":
            spec = (doc.get("amounts") or {}).get(t["what"])
            if not spec:
                d.append(f"amounts must cover {t['what']!r}")
            else:
                if spec.get("kind") not in ("transfer", "adjust"):
                    d.append(f"amounts[{t['what']!r}].kind must be "
                             f"transfer or adjust")
                _num(spec, "amount", d)
        elif t["category"] == "information":
            spec = (doc.get("messages") or {}).get(t["what"])
            if not spec:
                d.append(f"messages must cover {t['what']!r}")
            else:
                if not str(spec.get("from") or "").strip():
                    d.append(f"messages[{t['what']!r}] needs 'from'")
                if not isinstance(spec.get("to"), list) or not spec["to"]:
                    d.append(f"messages[{t['what']!r}] needs recipient "
                             f"list 'to'")
                if not str(spec.get("channel") or "").strip():
                    d.append(f"messages[{t['what']!r}] needs 'channel'")
    return d
