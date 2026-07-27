"""Actions: universal lifecycle, scenario meaning as data.

Actors *propose* intentions; they never apply consequences themselves.
Every meaningful action moves through:

    proposed -> validated -> scheduled -> started -> in progress
             -> completed / failed / interrupted   -> consequences applied

The kernel knows only universal mechanics: validate authority, validate
preconditions, reserve/adjust/transfer quantities, create records, send
information, establish/remove relationships, schedule events, and move
actions through their lifecycle.

What a verb *means* -- "vote", "reply", "ship an order" -- is an
**ActionDef: plain data** registered in the ledger (`action.define`),
containing who may attempt it, its required conditions, duration provenance,
and completion effects composed from universal operations with `{actor}`
/ `{params.x}` template substitution.  There is no per-verb Python handler
anywhere; a world compiler can emit these definitions as data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .simclock import Duration

#: Legal lifecycle transitions (anything else raises WorldIntegrityError).
ACTION_TRANSITIONS = {
    "proposed": {"scheduled", "rejected"},
    "scheduled": {"started", "failed", "cancelled"},
    "started": {"completed", "failed", "interrupted"},
    # terminal states allow no further transitions:
    "rejected": set(), "completed": set(), "failed": set(),
    "interrupted": set(), "cancelled": set(),
}


@dataclass(frozen=True)
class Intention:
    """What an actor proposes to do.  The world decides what happens."""
    verb: str
    params: dict = field(default_factory=dict)
    duration: Duration | None = None          # how long the actor plans to take
    completes_when: dict | None = None        # e.g. {"resource_at_least": ["factory","widgets",500]}
    interruptible: bool = False               # may this action be broken into?
    interruption_note: str = ""               # provenance for the above claim
    note: str = ""                            # the actor's stated reason


class TemplateError(ValueError):
    pass


def subst(obj, ctx: dict):
    """Substitute ``{actor}``, ``{action_id}``, ``{now}`` and ``{params.x}``
    templates through nested data.

    A string that IS exactly one template resolves to the raw value
    (preserving numbers/dicts/lists); a missing ``params.x`` in that exact
    form resolves to ``None`` (so optional params stay optional).  Templates
    embedded inside longer strings interpolate as text and raise on missing
    parameters."""
    if isinstance(obj, dict):
        return {subst(k, ctx): subst(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [subst(v, ctx) for v in obj]
    if not isinstance(obj, str):
        return obj
    if obj.startswith("{") and obj.endswith("}") and obj.count("{") == 1:
        return _lookup(obj[1:-1], ctx, exact=True)
    out, i = [], 0
    while i < len(obj):
        j = obj.find("{", i)
        if j < 0:
            out.append(obj[i:])
            break
        k = obj.find("}", j)
        if k < 0:
            out.append(obj[i:])
            break
        out.append(obj[i:j])
        val = _lookup(obj[j + 1:k], ctx, exact=False)
        out.append(str(val))
        i = k + 1
    return "".join(out)


def _lookup(path: str, ctx: dict, exact: bool):
    if path.startswith("params."):
        params = ctx.get("params", {})
        key = path[len("params."):]
        if key not in params:
            if exact:
                return None
            raise TemplateError(f"missing parameter {key!r}")
        return params[key]
    if path in ctx:
        return ctx[path]
    raise TemplateError(f"unknown template {{{path}}}")


def check_conditions(world, actor_id: str, params: dict, conditions: list) -> str | None:
    """Universal authority/precondition evaluation over declarative
    conditions.  Returns None if all hold, else the rejection reason."""
    ctx = {"actor": actor_id, "params": params}
    for cond in conditions:
        try:
            c = subst(cond, ctx)
        except TemplateError as e:
            return str(e)
        req = c.get("require")
        if req == "role_in":
            if world.actors[actor_id].role not in c["roles"]:
                return (f"authority: role {world.actors[actor_id].role!r} may not "
                        f"do this (requires one of {c['roles']})")
        elif req == "fact_equals":
            if world.facts.get(c["key"]) != c["value"]:
                return (f"precondition failed: fact {c['key']!r} is "
                        f"{world.facts.get(c['key'])!r}, requires {c['value']!r}")
        elif req == "fact_absent":
            if c["key"] in world.facts:
                return f"precondition failed: fact {c['key']!r} already exists"
        elif req == "actor_exists":
            if c["id"] not in world.actors:
                return f"unknown actor {c['id']!r}"
        elif req == "channel_exists":
            if c["name"] not in world.channels:
                return f"unknown channel {c['name']!r}"
        elif req == "param_nonempty":
            if not params.get(c["param"]):
                return f"missing or empty parameter {c['param']!r}"
        elif req == "param_in":
            if params.get(c["param"]) not in c["values"]:
                return (f"parameter {c['param']!r} must be one of {c['values']}, "
                        f"got {params.get(c['param'])!r}")
        elif req == "noticed_info":
            if c["info"] not in world.actors[actor_id].noticed_info:
                return ("information is local: you have not noticed "
                        f"{c['info']!r}")
        elif req == "resource_at_least":
            if world.resource(c["holder"], c["name"]) < float(c["amount"]) - 1e-9:
                return (f"insufficient {c['name']} at {c['holder']}: have "
                        f"{world.resource(c['holder'], c['name'])}, "
                        f"need {c['amount']}")
        else:
            return f"unknown condition kind {req!r}"
    return None


#: Condition kinds the universal evaluator understands.  A definition using
#: anything else is refused at registration time, not discovered as a
#: permanent mysterious rejection at run time.
KNOWN_CONDITIONS = frozenset({
    "role_in", "fact_equals", "fact_absent", "actor_exists", "channel_exists",
    "param_nonempty", "param_in", "noticed_info", "resource_at_least",
})


def validate_action_def(defn: dict) -> None:
    """Structural validation when a definition is registered."""
    if not defn.get("verb"):
        raise ValueError("action definition requires a verb")
    for key in ("conditions", "start_effects", "effects", "complete_conditions"):
        if key in defn and not isinstance(defn[key], list):
            raise ValueError(f"action.define {defn['verb']!r}: {key} must be a list")
    for key in ("conditions", "complete_conditions"):
        for cond in defn.get(key) or []:
            if not isinstance(cond, dict) or cond.get("require") not in KNOWN_CONDITIONS:
                raise ValueError(
                    f"action.define {defn['verb']!r}: unknown condition "
                    f"{cond!r} (known: {sorted(KNOWN_CONDITIONS)})")
    if "duration" in defn and defn["duration"] is not None:
        Duration.from_dict(defn["duration"])  # raises if provenance is invalid
    dcw = defn.get("default_completes_when")
    if dcw is not None:
        if not isinstance(dcw, dict) or "resource_at_least" not in dcw \
                or not isinstance(dcw["resource_at_least"], (list, tuple)) \
                or len(dcw["resource_at_least"]) != 3:
            raise ValueError(
                f"action.define {defn['verb']!r}: default_completes_when must "
                f"be {{'resource_at_least': [holder, resource, level]}}")
