"""Minds for compiled worlds.

This package contains exactly ONE mind: ``CompiledLLMMind``, the live actor.

There is deliberately no built-in "take the first available action" policy.
Such a thing would be a production actor model in all but name, and any run it
drove would look like a forecast without being one. Phase 1 runtime
integration instead uses test-only scripted minds that each acceptance fixture
supplies for itself (see ``tests/scripted_minds.py``); those prove the
compiled objects execute, and nothing more.

The mind cannot reach the world, the clock, the queue or another actor: it
receives only an ActorView and returns only a Decision, as the runtime
requires, and everything it returns passes kernel validation.
"""
from __future__ import annotations

from sworldmodel.llm_mind import DeepseekMind


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


def llm_minds(compiled, doc: dict, **kw) -> dict:
    by_name = {}
    for p in doc["participants"]:
        pid = compiled.symbols.maybe("participant", p["name"])
        if pid:
            by_name[pid] = p
    return {aid: CompiledLLMMind(aid, part, **kw)
            for aid, part in by_name.items()}
