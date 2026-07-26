"""Minds for compiled worlds.

Stage 1 uses ``MechanicalMind``: a deterministic policy that, when woken,
proposes the first affordance whose parameters it can fill from its own local
view. It is universal (it works for any compiled world) and deliberately not
intelligent -- its job is to prove that the compiled world is *executable*
and that the causal path to the terminal actually runs. Any rejection it
earns is recorded by the world, which is exactly the external-authority
behaviour we want to see exercised.

Stage 2 swaps in ``CompiledLLMMind`` over the identical compiled world, so
behaviour changes while world construction is held fixed.

Neither mind can reach the world, the clock, the queue or another actor: both
receive only an ActorView and return only a Decision, as the runtime requires.
"""
from __future__ import annotations

from datetime import timedelta

from sworldmodel import Decision, Duration, Intention, Mind
from sworldmodel.llm_mind import DeepseekMind

from .symbols import slug


class MechanicalMind(Mind):
    """Deterministic affordance-taker. Proves executability, not realism."""

    def __init__(self, actor_id: str, affordances: dict, order: list) -> None:
        self.actor_id = actor_id
        self.affordances = affordances     # verb -> semantic affordance
        self.order = order                 # verbs, in scenario declaration order
        self.attempted: set = set()

    def decide(self, view) -> Decision:
        offered = {v.verb for v in view.available_verbs}
        for verb in self.order:
            if verb not in offered:
                continue
            spec = self.affordances.get(verb, {})
            params = self._fill(spec, view)
            if params is None:
                continue
            key = (verb, tuple(sorted((k, str(v)) for k, v in params.items())))
            if key in self.attempted:
                continue           # do not re-propose an identical intention
            self.attempted.add(key)
            return Decision(
                intentions=[Intention(verb, params,
                                      duration=self._duration(spec),
                                      note=f"taking the available action: "
                                           f"{spec.get('label', verb)}")],
                note=f"mechanical policy: first available affordance "
                     f"({spec.get('label', verb)})")
        return Decision(note="no affordance available whose parameters I can fill")

    # -- parameter filling from LOCAL view only -------------------------
    def _fill(self, spec: dict, view):
        params = {}
        for p in spec.get("parameters") or []:
            name = p.get("name")
            if not name:
                return None
            value = self._value_for(p, view)
            if value is None:
                return None
            params[name] = value
        return params

    def _value_for(self, p: dict, view):
        source = p.get("fill_from")
        if source in ("noticed_information", "noticed_information_content"):
            # tags are written as human phrases and stored slugified, so match
            # on the canonical form rather than the raw text
            want = slug(p["tag"]) if p.get("tag") else None
            for iv in view.new_information:
                if want and iv.data.get("tag") != want:
                    continue
                return (iv.content if source.endswith("content") else iv.id)
            return None
        if p.get("allowed_values"):
            return p["allowed_values"][0]      # deterministic, not meaningful
        if p.get("default_value") is not None:
            return p["default_value"]
        if p.get("value_from_information_field"):
            field = p["value_from_information_field"]
            for iv in view.new_information:
                if field in iv.data:
                    return iv.data[field]
            return None
        return None

    @staticmethod
    def _duration(spec: dict):
        d = spec.get("duration") or {}
        if not d or d.get("typical_minutes") is None:
            return None                        # completion-condition action
        basis = "verified" if d.get("status") == "verified" else "inferred"
        return Duration(timedelta(minutes=float(d["typical_minutes"])), basis,
                        d.get("description", ""))


class CompiledLLMMind(DeepseekMind):
    """Stage 2: the same compiled world, decided by a live model.

    The persona brief is assembled from the scenario's own description of
    this participant -- nothing the model is told comes from outside the
    compiled world.
    """

    def __init__(self, actor_id: str, participant: dict, **kw) -> None:
        brief = _persona_brief(participant)
        super().__init__(actor_id, participant.get("name", actor_id),
                         persona_brief=brief, **kw)


def _persona_brief(p: dict) -> str:
    lines = [f"You are {p.get('name')}, {p.get('role', '')}.".strip()]
    if p.get("identity_brief"):
        lines.append(p["identity_brief"])
    if p.get("causal_relevance"):
        lines.append(f"Your part in this situation: {p['causal_relevance']}")
    for label, key in (("Your goals", "goals"),
                       ("How you tend to act", "values")):
        vals = p.get(key) or []
        if vals:
            lines.append(f"{label}:\n" + "\n".join(f"- {v}" for v in vals))
    return "\n".join(lines)


def mechanical_minds(compiled) -> dict:
    """One MechanicalMind per participant that has at least one affordance."""
    order = list(compiled.affordances)
    minds = {}
    for aid in compiled.world.actors:
        minds[aid] = MechanicalMind(aid, compiled.affordances, order)
    return minds


def llm_minds(compiled, doc: dict, **kw) -> dict:
    by_name = {}
    for p in doc["participants"]:
        pid = compiled.symbols.maybe("participant", p["name"])
        if pid:
            by_name[pid] = p
    return {aid: CompiledLLMMind(aid, part, **kw)
            for aid, part in by_name.items()}
