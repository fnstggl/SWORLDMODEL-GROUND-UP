"""Round trip: read the LOWERED world back into plain English.

The summary is reconstructed exclusively from the runtime World object and
the lowered terminal spec -- never from the intermediate graph -- so it
shows what the runtime actually contains.  The meaning reviewer compares it
against the approved description; if lowering changed the meaning, the world
must not run."""
from __future__ import annotations

from sworldmodel import World, fmt_local, parse_iso


def _expr_english(expr: dict) -> str:
    if "all_of" in expr:
        return "(" + " AND ".join(_expr_english(k) for k in expr["all_of"]) + ")"
    if "any_of" in expr:
        return "(" + " OR ".join(_expr_english(k) for k in expr["any_of"]) + ")"
    c = expr["check"]
    if c == "fact_equals":
        return f"fact {expr['key']!r} equals {expr['value']!r}"
    if c == "fact_exists":
        return f"fact {expr['key']!r} exists"
    if c == "resource_at_least":
        return (f"quantity {expr['name']!r} at {expr['holder']!r} reaches "
                f"{expr['amount']}")
    if c == "information_noticed":
        extra = "".join([f" from {expr['author']!r}" if expr.get("author") else "",
                         f" of type {expr['info_type']!r}"
                         if expr.get("info_type") else ""])
        return f"{expr['actor']!r} has noticed information{extra}"
    if c == "action_completed":
        who = f" by {expr['actor']!r}" if expr.get("actor") else ""
        return f"action {expr['verb']!r} has completed{who}"
    if c == "count_facts_at_least":
        vals = f" with value in {expr['value_in']}" if expr.get("value_in") else ""
        return (f"at least {expr['amount']} records under "
                f"{expr['prefix']!r}{vals}")
    return repr(expr)


def _ops_english(ops: list) -> list:
    out = []
    for op, data in ops:
        if op == "info.send_new":
            to = data["to"]
            to_s = ", ".join(to) if isinstance(to, list) \
                else f"everyone with role in {to.get('role_in')}"
            out.append(f"sends information (type "
                       f"{data.get('data', {}).get('type')!r}) to {to_s} on "
                       f"{data['channel']!r}")
        elif op == "fact.set":
            out.append(f"records {data['key']!r} = {data['value']!r}")
        elif op == "resource.adjust":
            out.append(f"changes {data['name']!r} at {data['holder']!r} by "
                       f"{data['delta']}")
        elif op == "resource.transfer":
            out.append(f"moves {data['amount']} {data['name']!r} from "
                       f"{data['from_holder']!r} to {data['to_holder']!r}")
        elif op == "process.active":
            out.append(f"turns process {data['id']!r} "
                       f"{'on' if data['active'] else 'off'}")
        elif op == "relationship.set":
            out.append(f"sets relationship {data['src']}-{data['kind']}-"
                       f"{data['dst']}")
        elif op == "event.schedule_in":
            inner = "; ".join(_ops_english(data.get("data", {}).get("ops", [])))
            out.append(f"after {data.get('delay_hours')}h "
                       f"({data.get('note', '')}): {inner}")
        elif op == "actor.memory":
            continue
        else:
            out.append(op)
    return out


def summarize(world: World, terminal_spec: dict, plan: dict) -> str:
    """The complete English reconstruction of the lowered world."""
    lines = []
    start, cutoff = plan["start"], plan["cutoff"]
    lines.append(f"The world begins at {start} and is observed until "
                 f"{cutoff}.")
    lines.append("")
    lines.append("PARTICIPANTS (deciding actors):")
    for aid, st in sorted(world.actors.items()):
        lines.append(f"- {st.name} ({aid}) -- {st.role} -- tz {st.tz}")
        for g in st.goals:
            lines.append(f"    goal: {g}")
        for v in st.values:
            lines.append(f"    disposition: {v}")
        if st.plan:
            lines.append(f"    currently: {st.plan}")
        for topic, b in sorted(st.beliefs.items()):
            lines.append(f"    knows [{topic}]: {b.statement} ({b.basis})")
        for cid, c in sorted(st.commitments.items()):
            when = fmt_local(c.at, st.tz) if c.at else "no fixed time"
            lines.append(f"    committed: {c.what} (due {when})")
        if st.attention:
            for ch, rule in sorted(st.attention.items()):
                if rule.check_every:
                    mins = int(rule.check_every.total_seconds() // 60)
                    cadence = f"checks every {mins} minutes"
                else:
                    cadence = "continuously attentive"
                window = "at any hour" if rule.calendar is None else \
                    (f"{rule.calendar.open_time:%H:%M}-"
                     f"{rule.calendar.close_time:%H:%M} "
                     f"{rule.calendar.tz}, days {sorted(rule.calendar.workdays)}")
                lines.append(f"    attends {ch!r}: {cadence}, {window} "
                             f"({rule.note})")
        else:
            lines.append("    attends no channel: information sent to them "
                         "stays delivered-but-unnoticed")
    if world.entities:
        lines.append("")
        lines.append("OTHER THINGS IN THE WORLD:")
        for eid, e in sorted(world.entities.items()):
            lines.append(f"- {e['properties'].get('name', eid)} ({eid}), "
                         f"{e['kind']}: {e['properties'].get('note', '')}")
    if world.channels:
        lines.append("")
        lines.append("CHANNELS AND ROUTES:")
        for name, ch in sorted(world.channels.items()):
            lines.append(f"- {name}: delivery latency "
                         f"{ch.latency.delta.total_seconds():.0f}s "
                         f"({ch.latency.note})")
        routes = sorted(k for k in world.facts if k.startswith("route:"))
        for r in routes:
            _, ch, src, dst = r.split(":", 3)
            lines.append(f"    {src} can reach {dst} on {ch}")
    quantities = sorted(world.resources)
    if quantities:
        lines.append("")
        lines.append("QUANTITIES AT START:")
        for key in quantities:
            lines.append(f"- {key} = {world.resources[key]}")
    if world.processes:
        lines.append("")
        lines.append("ONGOING PROCESSES:")
        for pid, p in sorted(world.processes.items()):
            cap = f", capacity {p['capacity']}" if p.get("capacity") else ""
            lines.append(f"- {pid}: {p['holder']}:{p['resource']} at "
                         f"{p['rate_per_hour']}/h{cap}, "
                         f"{'running' if p['active'] else 'idle'} at start "
                         f"({p['note']})")
    if world.watches:
        lines.append("")
        lines.append("THRESHOLD WATCHES:")
        for wid, wch in sorted(world.watches.items()):
            lines.append(f"- {wch['holder']}:{wch['resource']} reaching "
                         f"{wch['level']} -> {wch.get('on_reach')}")
    facts = sorted(k for k in world.facts if not k.startswith("route:"))
    if facts:
        lines.append("")
        lines.append("FACTS TRUE AT START:")
        for k in facts:
            lines.append(f"- {k} = {world.facts[k]!r}")
    if world.relationships:
        lines.append("")
        lines.append("RELATIONSHIPS:")
        for key, val in sorted(world.relationships.items()):
            lines.append(f"- {key.replace('|', ' -')}: {val}")
    lines.append("")
    lines.append("WHAT ACTORS CAN ATTEMPT (never a prediction that they "
                 "will):")
    for verb, d in sorted(world.action_defs.items()):
        roles = [c["roles"] for c in d.get("conditions", [])
                 if c.get("require") == "role_in"]
        who = f"roles {roles[0]}" if roles else "any participant"
        if d.get("duration"):
            takes = f"takes ~{d['duration']['seconds'] / 60:.0f} min"
        elif d.get("default_completes_when"):
            h, r, lvl = d["default_completes_when"]["resource_at_least"]
            takes = f"completes when {h}:{r} reaches {lvl}"
        else:
            takes = "duration chosen by the actor"
        lines.append(f"- {verb} ({who}; {takes}): {d.get('description', '')}")
        effs = _ops_english(d.get("effects", []))
        if effs:
            lines.append(f"    on completion: {'; '.join(effs)}")
    pending = world.queue.pending()
    if pending:
        lines.append("")
        lines.append("ALREADY SCHEDULED (independent of anyone's choices):")
        for ev in pending:
            if ev.kind == "wake.actor":
                lines.append(f"- {ev.t.isoformat()}: {ev.data.get('actor')} "
                             f"attends ({ev.data.get('detail', '')})")
            else:
                note = ev.data.get("note", "")
                effs = "; ".join(_ops_english(ev.data.get("ops", [])))
                lines.append(f"- {ev.t.isoformat()}: {note or ev.kind} "
                             f"[{effs}]")
    lines.append("")
    lines.append("THE FINISH LINE:")
    lines.append(f"Question: {terminal_spec['question']}")
    mode = terminal_spec["mode"]
    if mode == "condition":
        lines.append(f"YES the moment: "
                     f"{_expr_english(terminal_spec['condition'])}")
        lines.append(f"YES means: {terminal_spec.get('yes_means', '')}")
        lines.append(f"NO at the cutoff means: "
                     f"{terminal_spec.get('no_means', '')}")
    elif mode == "value":
        v = terminal_spec["value"]
        what = (f"quantity {v['name']!r} at {v['holder']!r}"
                if v["read"] == "resource"
                else f"count of records under {v['prefix']!r}")
        lines.append(f"The answer is the {what} at the cutoff.")
    else:
        d = terminal_spec["decision"]
        lines.append(f"The answer is the majority among records under "
                     f"{d['prefix']!r} (options {d['options']}, tie -> "
                     f"{d.get('tie')}).")
    if terminal_spec.get("resolve_when"):
        lines.append(f"Resolved early when: "
                     f"{_expr_english(terminal_spec['resolve_when'])}")
    lines.append(f"Hard cutoff: {terminal_spec['cutoff']}.")
    return "\n".join(lines)
