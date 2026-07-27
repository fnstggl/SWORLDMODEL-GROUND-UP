"""Deterministic graph assembly: canonical ids, alias resolution, duplicate
merging, and strict reference checking.

The builder consumes validated capability instances one at a time (so each
translation call can see everything already declared) and either accepts the
item into the WorldGraph or returns precise errors.  The LLM never creates
cross-references itself: names in, ids out, ambiguity rejected."""
from __future__ import annotations

from .world_graph import WorldGraph

#: Verbs every compiled world provides automatically (see assembly.py).
BUILTIN_VERBS = ("transmit_information", "review_information")

_HOLDER = ("participant", "aggregate")


def add_item(g: WorldGraph, instance: dict, item_ref: str) -> list:
    """Fold one capability instance into the graph -> error list (empty=ok).
    On errors the graph is unchanged (items are validated before mutation)."""
    cap = instance["capability"]
    fields = dict(instance.get("fields", {}))
    fn = _HANDLERS.get(cap)
    if fn is None:
        return [f"{item_ref}: no builder for capability {cap!r}"]
    errors: list = []
    result = fn(g, fields, errors, item_ref)
    if errors:
        return errors
    if result is not None:
        result["item_ref"] = item_ref
    return []


# ---------------------------------------------------------------------------
# reference resolution helpers
# ---------------------------------------------------------------------------

def _resolve_effects(g: WorldGraph, effects: list, errors: list,
                     where: str, external: bool) -> list:
    out = []
    for i, eff in enumerate(effects):
        eff = dict(eff)
        w = f"{where}.effects[{i}]"
        do = eff["do"]
        if do == "send_information":
            to = eff["to"]
            if isinstance(to, list):
                eff["to"] = [g.registry.resolve_or_error(n, ("participant",),
                                                         errors, w)
                             for n in to]
            else:
                known = set(g.roles().values())
                for role in to["roles"]:
                    if role not in known:
                        errors.append(f"{w}: no participant has role {role!r} "
                                      f"(roles: {sorted(known)})")
            eff["channel"] = g.registry.resolve_or_error(
                eff["channel"], ("channel",), errors, w)
            if external:
                eff["author"] = g.registry.resolve_or_error(
                    eff["author"], _HOLDER, errors, w)
        elif do in ("adjust_quantity",):
            eff["holder"] = g.registry.resolve_or_error(
                eff["holder"], _HOLDER, errors, w)
        elif do == "transfer_possession":
            for f in ("from_holder", "to_holder"):
                eff[f] = g.registry.resolve_or_error(eff[f], _HOLDER, errors, w)
        elif do == "set_process_active":
            eff["process"] = g.registry.resolve_or_error(
                eff["process"], ("process",), errors, w)
        elif do == "set_relationship":
            for f in ("src", "dst"):
                if eff[f] != "{actor}":
                    eff[f] = g.registry.resolve_or_error(eff[f], _HOLDER,
                                                         errors, w)
        elif do == "schedule_followup":
            eff["effects"] = _resolve_effects(g, eff["effects"], errors,
                                              f"{w}", external)
        out.append(eff)
    return out


def _resolve_requires(g: WorldGraph, requires: list, errors: list,
                      where: str) -> list:
    out = []
    for i, req in enumerate(requires):
        req = dict(req)
        if req["kind"] == "resource_at_least":
            req["holder"] = g.registry.resolve_or_error(
                req["holder"], _HOLDER, errors, f"{where}.requires[{i}]")
        out.append(req)
    return out


def _resolve_expr(g: WorldGraph, expr: dict, errors: list, where: str) -> dict:
    if "all_of" in expr or "any_of" in expr:
        key = "all_of" if "all_of" in expr else "any_of"
        return {key: [_resolve_expr(g, kid, errors, f"{where}.{key}[{i}]")
                      for i, kid in enumerate(expr[key])]}
    expr = dict(expr)
    kind = expr["check"]
    if kind == "resource_at_least":
        expr["holder"] = g.registry.resolve_or_error(expr["holder"], _HOLDER,
                                                     errors, where)
    elif kind == "information_noticed":
        expr["participant"] = g.registry.resolve_or_error(
            expr["participant"], ("participant",), errors, where)
        if expr.get("author"):
            expr["author"] = g.registry.resolve_or_error(
                expr["author"], _HOLDER, errors, where)
    elif kind == "information_sent":
        expr["sender"] = g.registry.resolve_or_error(
            expr["sender"], _HOLDER, errors, where)
        if expr.get("to"):
            expr["to"] = g.registry.resolve_or_error(
                expr["to"], ("participant",), errors, where)
    elif kind == "action_completed":
        if expr.get("participant"):
            expr["participant"] = g.registry.resolve_or_error(
                expr["participant"], ("participant",), errors, where)
        if expr["verb"] not in g.actions and expr["verb"] not in BUILTIN_VERBS:
            errors.append(f"{where}: action_completed references undefined "
                          f"verb {expr['verb']!r}")
    elif kind in ("record_exists", "count_records_at_least"):
        if expr.get("by"):
            expr["by"] = g.registry.resolve_or_error(
                expr["by"], ("participant",), errors, where)
    return expr


def _merge_lists(target: dict, fields: dict, keys: tuple) -> None:
    for k in keys:
        seen = list(target.get(k) or [])
        for v in fields.get(k) or []:
            if v not in seen:
                seen.append(v)
        target[k] = seen


# ---------------------------------------------------------------------------
# per-capability builders (mutate the graph only when error-free)
# ---------------------------------------------------------------------------

def _b_participant(g, f, errors, ref):
    existing = g.registry.resolve(f["name"])
    if existing is not None:
        kind = g.registry.kind_of(existing)
        if kind != "participant":
            errors.append(f"{ref}: {f['name']!r} already declared as a {kind}")
            return None
        node = g.participants[existing]
        _merge_lists(node, f, ("aliases", "goals", "traits"))
        if f.get("role") and f["role"] != node["role"]:
            g.notes.append(f"{ref}: kept role {node['role']!r} for "
                           f"{node['name']!r}; ignored duplicate declaration "
                           f"as {f['role']!r}")
        return node
    pid = g.registry.add(f["name"], f.get("aliases") or [], "participant")
    node = {"id": pid, "name": f["name"], "aliases": f.get("aliases") or [],
            "role": f["role"], "tz": f.get("tz") or "UTC",
            "goals": f.get("goals") or [], "traits": f.get("traits") or [],
            "plan": f.get("plan") or "", "why_needed": f.get("why_needed", "")}
    if not f.get("tz"):
        g.notes.append(f"{ref}: no time zone given for {f['name']!r}; "
                       f"defaulted to UTC (labeled inferred)")
    g.participants[pid] = node
    return node


def _b_aggregate(g, f, errors, ref):
    existing = g.registry.resolve(f["name"])
    if existing is not None:
        kind = g.registry.kind_of(existing)
        if kind != "aggregate":
            errors.append(f"{ref}: {f['name']!r} already declared as a {kind}")
            return None
        node = g.aggregates[existing]
        _merge_lists(node, f, ("aliases",))
        return node
    aid = g.registry.add(f["name"], f.get("aliases") or [], "aggregate")
    node = {"id": aid, "name": f["name"], "aliases": f.get("aliases") or [],
            "kind": f["kind"], "note": f.get("note", "")}
    g.aggregates[aid] = node
    return node


def _b_channel(g, f, errors, ref):
    existing = g.registry.resolve(f["name"])
    if existing is not None:
        if g.registry.kind_of(existing) == "channel":
            return g.channels[existing]
        errors.append(f"{ref}: {f['name']!r} already declared as a "
                      f"{g.registry.kind_of(existing)}")
        return None
    cid = g.registry.add(f["name"], [], "channel")
    node = {"id": cid, "name": cid,
            "latency_seconds": f["latency_seconds"],
            "provenance": f["provenance"], "note": f["note"],
            "open_to_all": bool(f.get("open_to_all", False))}
    g.channels[cid] = node
    return node


def _b_route(g, f, errors, ref):
    node = {
        "sender": g.registry.resolve_or_error(f["sender"], ("participant",),
                                              errors, ref),
        "recipient": g.registry.resolve_or_error(f["recipient"],
                                                 ("participant",), errors, ref),
        "channel": g.registry.resolve_or_error(f["channel"], ("channel",),
                                               errors, ref),
        "provenance": f["provenance"], "note": f["note"]}
    if errors:
        return None
    g.routes.append(node)
    return node


def _b_attention(g, f, errors, ref):
    pid = g.registry.resolve_or_error(f["participant"], ("participant",),
                                      errors, ref)
    cid = g.registry.resolve_or_error(f["channel"], ("channel",), errors, ref)
    if errors:
        return None
    node = dict(f, participant=pid, channel=cid)
    existing = next((a for a in g.attention
                     if a["participant"] == pid and a["channel"] == cid), None)
    if existing is not None:
        # a none_known placeholder may be UPGRADED by a real pattern (that
        # is what a patch pass does); a real pattern is never overwritten
        if existing["mode"] == "none_known" and f["mode"] != "none_known":
            g.attention.remove(existing)
            g.notes.append(f"{ref}: upgraded none_known attention of "
                           f"{pid} on {cid} to a declared pattern")
        else:
            errors.append(f"{ref}: attention for this participant+channel "
                          f"is already declared")
            return None
    g.attention.append(node)
    return node


def _b_fact(g, f, errors, ref):
    if any(x["key"] == f["key"] for x in g.facts):
        errors.append(f"{ref}: fact {f['key']!r} already declared")
        return None
    node = dict(f)
    g.facts.append(node)
    return node


def _b_resource(g, f, errors, ref):
    hid = g.registry.resolve_or_error(f["holder"], _HOLDER, errors, ref)
    if errors:
        return None
    if any(r["holder"] == hid and r["resource"] == f["resource"]
           for r in g.resources):
        errors.append(f"{ref}: quantity {f['resource']!r} at "
                      f"{f['holder']!r} already declared")
        return None
    node = dict(f, holder=hid)
    g.resources.append(node)
    return node


def _b_process(g, f, errors, ref):
    oid = g.registry.resolve_or_error(f["owner"], _HOLDER, errors, ref)
    if g.registry.resolve(f["name"]) is not None:
        errors.append(f"{ref}: name {f['name']!r} already declared")
    if errors:
        return None
    pid = g.registry.add(f["name"], [], "process")
    node = dict(f, id=pid, owner=oid)
    g.processes[pid] = node
    return node


def _b_window(g, f, errors, ref):
    pid = g.registry.resolve_or_error(f["process"], ("process",), errors, ref)
    if errors:
        return None
    node = dict(f, process=pid)
    g.windows.append(node)
    return node


def _b_watch(g, f, errors, ref):
    node = dict(
        f,
        holder=g.registry.resolve_or_error(f["holder"], _HOLDER, errors, ref),
        wake_participant=g.registry.resolve_or_error(
            f["wake_participant"], ("participant",), errors, ref))
    if errors:
        return None
    g.watches.append(node)
    return node


def _b_relationship(g, f, errors, ref):
    node = dict(f,
                src=g.registry.resolve_or_error(f["src"], _HOLDER, errors, ref),
                dst=g.registry.resolve_or_error(f["dst"], _HOLDER, errors, ref))
    if errors:
        return None
    g.relationships.append(node)
    return node


def _b_belief(g, f, errors, ref):
    pid = g.registry.resolve_or_error(f["participant"], ("participant",),
                                      errors, ref)
    if errors:
        return None
    node = dict(f, participant=pid)
    g.beliefs.append(node)
    return node


def _b_commitment(g, f, errors, ref):
    pid = g.registry.resolve_or_error(f["participant"], ("participant",),
                                      errors, ref)
    if errors:
        return None
    node = dict(f, participant=pid)
    node.setdefault("wake", True)
    g.commitments.append(node)
    return node


def _b_action(g, f, errors, ref):
    verb = f["verb"]
    if verb in g.actions or verb in BUILTIN_VERBS:
        errors.append(f"{ref}: verb {verb!r} already defined")
        return None
    roles = set(g.roles().values())
    for role in f.get("allowed_roles") or []:
        if role not in roles:
            errors.append(f"{ref}: allowed_roles includes {role!r} but no "
                          f"participant has that role (roles: {sorted(roles)})")
    resolved = dict(f)
    resolved["effects"] = _resolve_effects(g, f["effects"], errors, ref,
                                           external=False)
    resolved["requires"] = _resolve_requires(g, f.get("requires") or [],
                                             errors, ref)
    if "completes_when" in f:
        cw = dict(f["completes_when"])
        cw["holder"] = g.registry.resolve_or_error(cw["holder"], _HOLDER,
                                                   errors, ref)
        resolved["completes_when"] = cw
    if errors:
        return None
    node = {"verb": verb, "fields": resolved}
    g.actions[verb] = node
    return node


def _b_external(g, f, errors, ref):
    resolved = dict(f)
    resolved["effects"] = _resolve_effects(g, f["effects"], errors, ref,
                                           external=True)
    if errors:
        return None
    node = {"fields": resolved}
    g.external_events.append(node)
    return node


def _b_wake(g, f, errors, ref):
    pid = g.registry.resolve_or_error(f["participant"], ("participant",),
                                      errors, ref)
    if errors:
        return None
    node = dict(f, participant=pid)
    g.wakes.append(node)
    return node


def _b_uncertainty(g, f, errors, ref):
    node = dict(f)
    g.uncertainties.append(node)
    return node


def _b_exclusion(g, f, errors, ref):
    node = dict(f)
    g.exclusions.append(node)
    return node


def _b_terminal(g, f, errors, ref):
    if g.terminal is not None:
        errors.append(f"{ref}: the terminal is already set; exactly one "
                      f"set_terminal is allowed")
        return None
    resolved = dict(f)
    for key in ("condition", "resolve_when"):
        if key in f and f[key] is not None:
            resolved[key] = _resolve_expr(g, f[key], errors, f"{ref}.{key}")
    if f["mode"] == "value" and f.get("value", {}).get("read") == "resource":
        v = dict(f["value"])
        v["holder"] = g.registry.resolve_or_error(v["holder"], _HOLDER,
                                                  errors, f"{ref}.value")
        resolved["value"] = v
    if errors:
        return None
    node = {"fields": resolved}
    g.terminal = node
    return node


_HANDLERS = {
    "add_participant": _b_participant,
    "add_aggregate": _b_aggregate,
    "add_channel": _b_channel,
    "add_channel_access": _b_route,
    "add_attention": _b_attention,
    "add_fact": _b_fact,
    "add_resource": _b_resource,
    "add_process": _b_process,
    "add_operating_window": _b_window,
    "add_threshold_watch": _b_watch,
    "add_relationship": _b_relationship,
    "add_belief": _b_belief,
    "add_commitment": _b_commitment,
    "define_action": _b_action,
    "schedule_external_event": _b_external,
    "schedule_wake": _b_wake,
    "declare_uncertainty": _b_uncertainty,
    "declare_exclusion": _b_exclusion,
    "set_terminal": _b_terminal,
}
