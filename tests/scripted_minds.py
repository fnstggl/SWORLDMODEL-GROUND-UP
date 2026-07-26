"""TEST-ONLY scripted minds.

These are part of the acceptance harness, not of the compiler. Each fixture
supplies its own script: an explicit, hand-written list of "when this happens,
attempt that action" rules, authored by whoever wrote the fixture and
deliberately kept separate from anything the semantic compiler produced.

They exist to prove ONE thing: that the compiled runtime objects execute --
that authority, preconditions, durations, information routing and the terminal
all wire up and run. They are not a model of behaviour, and a run driven by
them is NEVER a forecast. Nothing in this file may be used to judge whether a
compiled world is realistic.

There is deliberately no "pick the first available action" policy here: a
generic affordance-taker would silently become a production actor model, which
is exactly what must not exist.
"""
from __future__ import annotations

from datetime import timedelta

from compiler.symbols import slug
from sworldmodel import Decision, Duration, Intention, Mind


class ScriptedMind(Mind):
    """Follows an explicit per-fixture script. Nothing is inferred."""

    def __init__(self, actor_id: str, rules: list, verbs: dict,
                 affordances: dict) -> None:
        self.actor_id = actor_id
        self.rules = rules            # authored by the fixture
        self.verbs = verbs            # affordance label -> compiled verb id
        self.affordances = affordances
        self.fired: set = set()

    def decide(self, view) -> Decision:
        for i, rule in enumerate(self.rules):
            if i in self.fired and not rule.get("repeatable"):
                continue
            bound = self._match(rule, view)
            if bound is None:
                continue
            verb = self.verbs.get(rule["action"])
            if verb is None:
                continue              # this fixture's action is not in this world
            self.fired.add(i)
            spec = self.affordances.get(verb, {})
            return Decision(
                intentions=[Intention(verb, bound,
                                      duration=_duration(spec),
                                      note=rule.get("why", "scripted step"))],
                note=f"scripted rule {i}: {rule.get('why', rule['action'])}")
        return Decision(note="no scripted rule applies to this wake")

    def _match(self, rule: dict, view):
        """Return the parameter dict if this rule fires now, else None."""
        params = dict(rule.get("params") or {})
        trigger = rule.get("trigger", "notices")
        if trigger == "notices":
            want = slug(rule["tag"]) if rule.get("tag") else None
            for iv in view.new_information:
                if want and iv.data.get("tag") != want:
                    continue
                for pname, field in (rule.get("bind_from_notice") or {}).items():
                    params[pname] = iv.id if field == "id" else iv.content
                return params
            return None
        if trigger == "wake_reason":
            kinds = {r["kind"] for r in view.reasons}
            return params if rule.get("reason") in kinds else None
        if trigger == "action_completed":
            for av in view.completed:
                if self.verbs.get(rule.get("after_action")) == av.verb:
                    return params
            return None
        return None


def _duration(spec: dict):
    d = spec.get("duration") or {}
    if not d or d.get("typical_minutes") is None:
        return None
    basis = "verified" if d.get("status") == "verified" else "inferred"
    return Duration(timedelta(minutes=float(d["typical_minutes"])), basis,
                    d.get("description", ""))


def scripted_minds(compiled, script: dict | None = None) -> dict:
    """Build minds from a fixture-supplied script.

    ``script`` maps participant NAME -> list of rules. A participant with no
    script simply never acts, which is the correct default: an actor with no
    authored behaviour must not be given one.
    """
    script = script or {}
    verbs = {a.get("label"): verb for verb, a in compiled.affordances.items()}
    minds = {}
    for aid in compiled.world.actors:
        name = compiled.symbols.display("participant", aid)
        rules = script.get(name) or script.get(aid) or []
        minds[aid] = ScriptedMind(aid, rules, verbs, compiled.affordances)
    return minds
