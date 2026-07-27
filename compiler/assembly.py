"""Assembly: expand the WorldGraph into a genesis plan of kernel operations.

This is where lifecycle meaning becomes mechanics, deterministically:

    send information   -> info.send_new (create -> send -> deliver -> the
                          recipient MAY notice/read; never forced)
    create record      -> typed fact `record_type:subject[:actor]`, authority
                          via the action's conditions, cause via the ledger
    transfer/adjust    -> conservation-preserving resource ops
    run process        -> process.add + operating windows as scheduled toggles
    perform action     -> declarative ActionDef (authority, preconditions,
                          duration provenance, completion effects)

The output is a *plan*: ordered genesis ops, scheduled events, and the
lowered terminal spec -- inspectable data.  No LLM calls, no invention: if a
piece of meaning cannot be expanded, that is an error, not a guess."""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta

from sworldmodel import BusinessCalendar, at_local, iso, parse_iso, recurring
from sworldmodel.info import AttentionRule
from sworldmodel.simclock import (AmbiguousLocalTime, NonexistentLocalTime,
                                  local_instant)

from .capabilities import LIMITS
from .graph_builder import BUILTIN_VERBS
from .provenance import kernel_basis, kernel_basis_any, prov_note
from .world_graph import WorldGraph

_GENERIC_INFO_TYPE = "message"


def to_instant(local_dt: str, tz: str, notes: list, where: str) -> datetime:
    """'YYYY-MM-DD HH:MM' + zone -> UTC instant, with an explicit, recorded
    daylight-saving policy: a nonexistent wall time moves forward to the
    first existing minute; an ambiguous one takes the first occurrence."""
    naive = datetime.strptime(local_dt, "%Y-%m-%d %H:%M")
    try:
        return local_instant(naive, tz)
    except AmbiguousLocalTime:
        notes.append(f"{where}: {local_dt} {tz} occurs twice (fall-back); "
                     f"using the first occurrence")
        return local_instant(naive, tz, fold=0)
    except NonexistentLocalTime:
        for minutes in range(1, 181):
            try:
                shifted = local_instant(naive + timedelta(minutes=minutes), tz)
            except (NonexistentLocalTime, AmbiguousLocalTime):
                continue
            notes.append(f"{where}: {local_dt} {tz} does not exist "
                         f"(spring-forward); moved to the first existing "
                         f"minute (+{minutes}m)")
            return shifted
        raise


def record_key(eff: dict) -> str:
    """The typed-record fact key.  Per-actor records embed the acting
    participant, so the record preserves who made it."""
    base = f"{eff['record_type']}:{eff['subject']}"
    return base + ":{actor}" if eff.get("per_actor", True) else base


def _num_or_template(v):
    return v if isinstance(v, (int, float)) else str(v)


def expand_effects(effects: list, evidence: list | None,
                   external_author: bool) -> list:
    """Effect macros -> kernel op sequences (the universal expansions)."""
    ops = []
    for eff in effects:
        do = eff["do"]
        if do == "send_information":
            to = eff["to"]
            ops.append(["info.send_new", {
                "author": eff["author"] if external_author else "{actor}",
                "to": to if isinstance(to, list) else {"role_in": to["roles"]},
                "channel": eff["channel"],
                "content": eff["content_template"],
                "data": {"type": eff.get("info_type") or _GENERIC_INFO_TYPE}}])
        elif do == "create_record":
            value = eff.get("choice_template", eff.get("value"))
            ops.append(["fact.set", {"key": record_key(eff), "value": value}])
        elif do == "adjust_quantity":
            ops.append(["resource.adjust", {
                "holder": eff["holder"], "name": eff["resource"],
                "delta": _num_or_template(eff["delta_template"])}])
        elif do == "transfer_possession":
            ops.append(["resource.transfer", {
                "from_holder": eff["from_holder"], "to_holder": eff["to_holder"],
                "name": eff["resource"],
                "amount": _num_or_template(eff["amount_template"])}])
        elif do == "set_process_active":
            ops.append(["process.active", {"id": eff["process"],
                                           "active": eff["active"]}])
        elif do == "set_relationship":
            ops.append(["relationship.set", {
                "src": eff["src"], "kind": eff["kind"], "dst": eff["dst"],
                "value": eff["value"]}])
        elif do == "schedule_followup":
            ops.append(["event.schedule_in", {
                "kind": "world.ops", "delay_hours": eff["delay_hours"],
                "basis": kernel_basis(eff["provenance"]),
                "note": prov_note(eff["provenance"], eff["note"], evidence),
                "data": {"ops": expand_effects(eff["effects"], evidence,
                                               external_author)}}])
        else:  # pragma: no cover -- schema-validated upstream
            raise ValueError(f"unknown effect macro {do!r}")
    return ops


# ---------------------------------------------------------------------------
# built-in universal actions (every compiled world has them)
# ---------------------------------------------------------------------------

def builtin_action_defs() -> list:
    transmit = {
        "verb": "transmit_information",
        "description": ("Compose and send information to one participant you "
                        "can actually reach. params: to (participant id), "
                        "channel (channel id), content (the text), info_type "
                        "(optional short label like 'reply' or "
                        "'confirmation'). Composing takes the time you state; "
                        "delivery latency comes from the channel; the "
                        "recipient may or may not notice it."),
        "conditions": [
            {"require": "actor_exists", "id": "{params.to}"},
            {"require": "channel_exists", "name": "{params.channel}"},
            {"require": "param_nonempty", "param": "content"},
            {"require": "fact_equals",
             "key": "route:{params.channel}:{actor}:{params.to}",
             "value": True},
        ],
        "effects": [
            ["info.send_new", {"author": "{actor}", "to": ["{params.to}"],
                               "channel": "{params.channel}",
                               "content": "{params.content}",
                               "data": {"type": "{params.info_type}"}}],
            ["actor.memory", {"actor": "{actor}", "kind": "note",
                              "content": "Sent information to {params.to} on "
                                         "{params.channel}: {params.content}",
                              "source": "{action_id}"}],
        ],
        "duration": {"seconds": 600, "basis": "inferred",
                     "note": "typical time to compose a short message; the "
                             "actor may state their own duration"},
    }
    review = {
        "verb": "review_information",
        "description": ("Read information you have noticed, in full. params: "
                        "info (the information id), content (its text, for "
                        "your own record). Reading takes time."),
        "conditions": [{"require": "noticed_info", "info": "{params.info}"}],
        "effects": [
            ["actor.memory", {"actor": "{actor}", "kind": "note",
                              "content": "Read information {params.info} in "
                                         "full: {params.content}",
                              "source": "{params.info}"}],
        ],
        "duration": {"seconds": 300, "basis": "inferred",
                     "note": "reading a short document; the actor may state "
                             "their own duration"},
    }
    return [transmit, review]


def lower_action(node: dict, evidence: list | None) -> dict:
    f = node["fields"]
    conditions = []
    if f.get("allowed_roles"):
        conditions.append({"require": "role_in", "roles": f["allowed_roles"]})
    for p in f.get("params") or []:
        if p.get("required", True):
            conditions.append({"require": "param_nonempty", "param": p["name"]})
        if p.get("one_of"):
            conditions.append({"require": "param_in", "param": p["name"],
                               "values": p["one_of"]})
    for req in f.get("requires") or []:
        k = req["kind"]
        if k == "fact_equals":
            conditions.append({"require": "fact_equals", "key": req["key"],
                               "value": req["value"]})
        elif k == "fact_absent":
            conditions.append({"require": "fact_absent", "key": req["key"]})
        elif k == "noticed_information":
            conditions.append({"require": "noticed_info",
                               "info": "{params.%s}" % req["param"]})
        elif k == "resource_at_least":
            conditions.append({"require": "resource_at_least",
                               "holder": req["holder"], "name": req["resource"],
                               "amount": req["amount"]})
    for eff in f["effects"]:
        if eff.get("do") == "create_record" and eff.get("once", True):
            conditions.append({"require": "fact_absent", "key": record_key(eff)})
    effects = expand_effects(f["effects"], evidence, external_author=False)
    effects.append(["actor.memory", {
        "actor": "{actor}", "kind": "note",
        "content": f"Completed {node['verb']}.", "source": "{action_id}"}])
    defn = {"verb": node["verb"], "description": f["description"],
            "conditions": conditions, "effects": effects,
            "interruptible": bool(f.get("interruptible", False))}
    if f.get("duration_minutes") is not None:
        defn["duration"] = {
            "seconds": float(f["duration_minutes"]) * 60.0,
            "basis": kernel_basis(f["provenance"]),
            "note": prov_note(f["provenance"], f["note"], evidence)}
    if f.get("completes_when"):
        cw = f["completes_when"]
        defn["default_completes_when"] = {
            "resource_at_least": [cw["holder"], cw["resource"],
                                  _num_or_template(cw["amount"])]}
    return defn


# ---------------------------------------------------------------------------
# terminal lowering (names already resolved to ids by the builder)
# ---------------------------------------------------------------------------

def lower_expr(expr: dict) -> dict:
    if "all_of" in expr or "any_of" in expr:
        key = "all_of" if "all_of" in expr else "any_of"
        return {key: [lower_expr(kid) for kid in expr[key]]}
    kind = expr["check"]
    if kind in ("fact_equals", "fact_exists"):
        out = {"check": kind, "key": expr["key"]}
        if kind == "fact_equals":
            out["value"] = expr["value"]
        return out
    if kind == "resource_at_least":
        return {"check": "resource_at_least", "holder": expr["holder"],
                "name": expr["resource"], "amount": expr["amount"]}
    if kind == "information_noticed":
        out = {"check": "information_noticed", "actor": expr["participant"]}
        if expr.get("author"):
            out["author"] = expr["author"]
        if expr.get("info_type"):
            out["info_type"] = expr["info_type"]
        return out
    if kind == "action_completed":
        out = {"check": "action_completed", "verb": expr["verb"]}
        if expr.get("participant"):
            out["actor"] = expr["participant"]
        return out
    if kind == "record_exists":
        base = f"{expr['record_type']}:{expr['subject']}"
        if expr.get("by"):
            key = f"{base}:{expr['by']}"
            if expr.get("choice") is not None:
                return {"check": "fact_equals", "key": key,
                        "value": expr["choice"]}
            return {"check": "fact_exists", "key": key}
        out = {"check": "count_facts_at_least", "prefix": base + ":",
               "amount": 1}
        if expr.get("choice") is not None:
            out["value_in"] = [expr["choice"]]
        return out
    if kind == "count_records_at_least":
        out = {"check": "count_facts_at_least",
               "prefix": f"{expr['record_type']}:{expr['subject']}:",
               "amount": expr["amount"]}
        if expr.get("choice") is not None:
            out["value_in"] = [expr["choice"]]
        return out
    raise ValueError(f"unknown terminal check {kind!r}")


def lower_terminal(g: WorldGraph, notes: list) -> dict:
    f = g.terminal["fields"]
    cutoff = to_instant(f["cutoff_local"], f["tz"], notes, "terminal.cutoff")
    spec = {"question": f["question_restated"], "cutoff": iso(cutoff),
            "mode": f["mode"]}
    if f.get("yes_means"):
        spec["yes_means"] = f["yes_means"]
    if f.get("no_means"):
        spec["no_means"] = f["no_means"]
    if f["mode"] == "condition":
        spec["condition"] = lower_expr(f["condition"])
    elif f["mode"] == "value":
        v = f["value"]
        if v["read"] == "resource":
            spec["value"] = {"read": "resource", "holder": v["holder"],
                             "name": v["resource"]}
        else:
            spec["value"] = {"read": "count_facts",
                             "prefix": f"{v['record_type']}:{v['subject']}:"}
    else:
        d = f["decision"]
        spec["decision"] = {"prefix": f"{d['record_type']}:{d['subject']}:",
                            "options": d["options"],
                            "tie": d.get("tie", "tie")}
    if f.get("resolve_when"):
        spec["resolve_when"] = lower_expr(f["resolve_when"])
    return spec


# ---------------------------------------------------------------------------
# the genesis plan
# ---------------------------------------------------------------------------

def assemble(g: WorldGraph, start_iso: str, evidence_of=lambda ref: None):
    """WorldGraph -> (plan, errors).  The plan is pure data; on any error the
    plan is unusable and compilation stops with the reasons."""
    errors: list = []
    notes: list = list(g.notes)
    start = parse_iso(start_iso)
    if g.terminal is None:
        return None, ["no terminal was set; a world without a finish line "
                      "cannot answer anything"]
    tspec = lower_terminal(g, notes)
    cutoff = parse_iso(tspec["cutoff"])
    if cutoff <= start:
        errors.append(f"cutoff {tspec['cutoff']} is not after the start "
                      f"{start_iso}")
    if cutoff - start > timedelta(days=LIMITS["horizon_days"]):
        errors.append(f"horizon exceeds {LIMITS['horizon_days']} days; model "
                      f"a nearer observable resolution")
    if len(g.participants) > LIMITS["participants"]:
        errors.append(f"{len(g.participants)} participants exceeds the "
                      f"limit of {LIMITS['participants']}; aggregate the rest")
    if errors:
        return None, errors

    ops: list = []
    schedules: list = []

    def ev(node):
        return evidence_of(node.get("item_ref"))

    # channels ---------------------------------------------------------
    for cid in sorted(g.channels):
        ch = g.channels[cid]
        ops.append(["channel.add", {
            "name": cid,
            "latency": {"seconds": float(ch["latency_seconds"]),
                        "basis": kernel_basis(ch["provenance"]),
                        "note": prov_note(ch["provenance"], ch["note"],
                                          ev(ch))}}])
    # aggregates -------------------------------------------------------
    for aid in sorted(g.aggregates):
        a = g.aggregates[aid]
        ops.append(["entity.add", {"id": aid, "kind": a["kind"],
                                   "properties": {"name": a["name"],
                                                  "note": a["note"]}}])
    # facts ------------------------------------------------------------
    for fact in g.facts:
        ops.append(["fact.set", {"key": fact["key"], "value": fact["value"]}])
    # routes (the "can actually reach" facts) --------------------------
    route_keys = set()
    for cid in sorted(g.channels):
        if g.channels[cid]["open_to_all"]:
            for src in sorted(g.participants):
                for dst in sorted(g.participants):
                    if src != dst:
                        route_keys.add(f"route:{cid}:{src}:{dst}")
    for r in g.routes:
        route_keys.add(f"route:{r['channel']}:{r['sender']}:{r['recipient']}")
    for key in sorted(route_keys):
        ops.append(["fact.set", {"key": key, "value": True}])
    # resources --------------------------------------------------------
    for r in g.resources:
        ops.append(["resource.set", {"holder": r["holder"],
                                     "name": r["resource"],
                                     "amount": float(r["amount"])}])
    # processes (+ windows decide initial activity) --------------------
    window_cals: dict = {}
    for w in g.windows:
        try:
            cal = BusinessCalendar(
                tz=w["tz"], workdays=frozenset(w["workdays"]),
                open_time=dtime.fromisoformat(w["start_time"]),
                close_time=dtime.fromisoformat(w["end_time"]))
        except Exception as e:
            errors.append(f"operating window for {w['process']}: {e}")
            continue
        window_cals.setdefault(w["process"], []).append((w, cal))
    for pid in sorted(g.processes):
        p = g.processes[pid]
        active = bool(p["active_at_start"])
        if pid in window_cals:
            active = any(cal.is_open(start) for _, cal in window_cals[pid])
            notes.append(f"process {pid}: initial activity derived from its "
                         f"operating window at the start instant "
                         f"({'open' if active else 'closed'})")
        data = {"id": pid, "holder": p["owner"], "resource": p["resource"],
                "rate_per_hour": float(p["rate_per_hour"]), "active": active,
                "basis": kernel_basis(p["provenance"]),
                "note": prov_note(p["provenance"], p["note"], ev(p))}
        if p.get("capacity") is not None:
            data["capacity"] = float(p["capacity"])
        ops.append(["process.add", data])
    # threshold watches ------------------------------------------------
    for i, w in enumerate(g.watches):
        ops.append(["watch.add", {
            "id": f"tw{i + 1}", "holder": w["holder"],
            "resource": w["resource"], "level": float(w["level"]),
            "on_reach": {"wake_actor": w["wake_participant"]},
            "basis": kernel_basis_any(w["provenance"]),
            "note": prov_note(w["provenance"], w["note"], ev(w))}])
    # action definitions ----------------------------------------------
    for defn in builtin_action_defs():
        ops.append(["action.define", defn])
    for verb in sorted(g.actions):
        ops.append(["action.define", lower_action(g.actions[verb],
                                                  ev(g.actions[verb]))])
    # participants -----------------------------------------------------
    attention_by_actor: dict = {}
    for a in g.attention:
        if a["mode"] == "none_known":
            notes.append(f"attention of {a['participant']} on "
                         f"{a['channel']}: none_known -- information on this "
                         f"channel will remain delivered-but-unnoticed")
            continue
        cal = None
        if a["mode"] == "periodic" or (a["mode"] == "continuous"
                                       and a.get("open_time")):
            cal = {"tz": a.get("tz") or "UTC",
                   "workdays": a.get("workdays") or [0, 1, 2, 3, 4],
                   "open": a.get("open_time") or "09:00",
                   "close": a.get("close_time") or "17:00"}
        check_every = (float(a["check_every_minutes"]) * 60.0
                       if a["mode"] == "periodic" else None)
        if cal is not None:
            o = dtime.fromisoformat(cal["open"])
            c = dtime.fromisoformat(cal["close"])
            window = (c.hour * 60 + c.minute) - (o.hour * 60 + o.minute)
            if window <= 0:
                errors.append(f"attention of {a['participant']} on "
                              f"{a['channel']}: the window "
                              f"{cal['open']}-{cal['close']} is empty")
                continue
            if check_every is not None and check_every > window * 60.0:
                # "at least once per <window day>": within the kernel's
                # calendar semantics that is a cadence of one full window --
                # a faithful clamp, recorded, never silent
                notes.append(f"attention of {a['participant']} on "
                             f"{a['channel']}: cadence "
                             f"{check_every / 60:.0f}m exceeds the daily "
                             f"window; clamped to once per working window")
                check_every = float(window * 60)
        rule = {"calendar": cal,
                "check_every_seconds": check_every,
                "basis": kernel_basis(a["provenance"]),
                "note": prov_note(a["provenance"], a["note"], ev(a))}
        try:
            AttentionRule.from_dict(rule)     # fail at compile, not at run
        except ValueError as e:
            errors.append(f"attention of {a['participant']} on "
                          f"{a['channel']}: {e}")
            continue
        attention_by_actor.setdefault(a["participant"], {})[a["channel"]] = rule
    private_rel: dict = {}
    for rel in g.relationships:
        if rel["src"] in g.participants:
            private_rel.setdefault(rel["src"], {})[rel["dst"]] = rel["note"]
    for pid in sorted(g.participants):
        p = g.participants[pid]
        ops.append(["actor.add", {
            "id": pid, "name": p["name"], "role": p["role"], "tz": p["tz"],
            "attention": attention_by_actor.get(pid, {}),
            "goals": p["goals"], "values": p["traits"], "plan": p["plan"],
            "relationships": private_rel.get(pid, {})}])
    # beliefs ----------------------------------------------------------
    for b in g.beliefs:
        ops.append(["actor.belief", {
            "actor": b["participant"], "topic": b["topic"],
            "statement": b["statement"],
            "basis": prov_note(b["provenance"], b.get("note", ""), ev(b))}])
    # commitments ------------------------------------------------------
    for i, c in enumerate(g.commitments):
        when = to_instant(c["due_local"], c["tz"], notes,
                          f"commitment of {c['participant']}")
        ops.append(["actor.commit", {"actor": c["participant"],
                                     "id": f"c{i + 1}", "what": c["what"],
                                     "at": iso(when)}])
        if c.get("wake", True):
            if when < start:
                errors.append(f"commitment {c['what']!r} of "
                              f"{c['participant']} falls due before the "
                              f"start; past obligations belong in beliefs "
                              f"or facts")
            elif when <= cutoff:
                schedules.append({"kind": "wake.actor",
                                  "data": {"actor": c["participant"],
                                           "reason": "scheduled_commitment",
                                           "detail": f"c{i + 1}: {c['what']}"},
                                  "at": iso(when)})
    # world-level relationships ---------------------------------------
    for rel in g.relationships:
        ops.append(["relationship.set", {"src": rel["src"], "kind": rel["kind"],
                                         "dst": rel["dst"],
                                         "value": rel["note"]}])
    # operating windows -> scheduled activity toggles ------------------
    for pid, wins in sorted(window_cals.items()):
        for w, cal in wins:
            for kind_flag, hhmm in (("open", w["start_time"]),
                                    ("close", w["end_time"])):
                t = dtime.fromisoformat(hhmm)
                for inst in recurring(w["tz"], t, start.date() - timedelta(days=1),
                                      cutoff.date() + timedelta(days=1),
                                      workdays=frozenset(w["workdays"])):
                    if inst < start or inst > cutoff:
                        continue
                    schedules.append({
                        "kind": "world.ops",
                        "data": {"ops": [["process.active",
                                          {"id": pid,
                                           "active": kind_flag == "open"}]],
                                 "note": f"operating window {kind_flag} for "
                                         f"{pid}"},
                        "at": iso(inst)})
    # scheduled external events ---------------------------------------
    for e in g.external_events:
        f = e["fields"]
        when = to_instant(f["at_local"], f["tz"], notes,
                          f"external event {f['name']}")
        if when < start:
            errors.append(f"external event {f['name']!r} is scheduled before "
                          f"the start instant; things already past belong in "
                          f"starting facts")
            continue
        if when > cutoff:
            notes.append(f"external event {f['name']!r} falls after the "
                         f"cutoff; kept (it cannot affect the answer)")
        schedules.append({
            "kind": "world.ops",
            "data": {"ops": expand_effects(f["effects"], ev(e),
                                           external_author=True),
                     "note": prov_note(f["provenance"], f["note"], ev(e))},
            "at": iso(when)})
    # scheduled wakes --------------------------------------------------
    for wk in g.wakes:
        when = to_instant(wk["at_local"], wk["tz"], notes,
                          f"wake of {wk['participant']}")
        if when < start:
            errors.append(f"scheduled wake of {wk['participant']} is before "
                          f"the start instant")
            continue
        schedules.append({"kind": "wake.actor",
                          "data": {"actor": wk["participant"],
                                   "reason": "planned_attention",
                                   "detail": wk["reason"]},
                          "at": iso(when)})

    schedules.sort(key=lambda s: (s["at"], s["kind"]))
    if len(ops) + len(schedules) > LIMITS["genesis_events"]:
        errors.append(f"genesis would contain {len(ops) + len(schedules)} "
                      f"records, over the {LIMITS['genesis_events']} bound; "
                      f"the world must be smaller (coarser windows, fewer "
                      f"objects)")
    if errors:
        return None, errors
    plan = {"start": start_iso, "cutoff": tspec["cutoff"], "ops": ops,
            "schedules": schedules, "terminal_spec": tspec, "notes": notes}
    return plan, []
