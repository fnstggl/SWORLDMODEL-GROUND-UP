"""Code-only actor-local view construction.

No LLM builds or filters a view.  Code selects authorized records by exact
actor identity and stored visibility state, then renders their text into a
stable template.  There is no semantic search, vector retrieval, salience
weighting, importance scoring or relevance ranking here -- selection is
mechanical:

    actor_id in event["for"]  AND  event["observed"] is True

Everything else about the actor (identity, compiler-provided private
context, immutable shared context, their own private memories, the current
simulated time) is added by identity, never by interpretation.
"""
from __future__ import annotations

from .journal import Journal


def build_view(world, journal: Journal, actor_id: str, *,
               reasons: list | None = None) -> dict:
    """The complete and only input a given actor's model receives."""
    st = world.actors[actor_id]
    observed = journal.observed_by(actor_id)
    memories = [{"t": m.t.isoformat(), "kind": m.kind, "content": m.content}
                for m in st.memories if m.kind == "private"]
    return {
        "actor_id": actor_id,
        "name": st.name,
        "now": world.clock.now.isoformat(),
        "private_context": journal.profiles().get(actor_id, ""),
        "shared_context": journal.shared_context(),
        "observed_events": [{"event_id": e["event_id"], "t": e["t"],
                             "description": e["description"]}
                            for e in observed],
        "private_memories": memories,
        "reasons": list(reasons or []),
    }


def render_view(view: dict) -> str:
    """The stable natural-language rendering handed to the actor model."""
    parts = [
        "CURRENT TIME", view["now"], "",
        "WHO YOU ARE",
        f"{view['name']} (your identity in this situation: "
        f"{view['actor_id']})",
        view["private_context"] or "(no further private context)", "",
        "SHARED CONTEXT",
        view["shared_context"] or "(none)", "",
        "WHAT YOU HAVE OBSERVED",
    ]
    if view["observed_events"]:
        for e in view["observed_events"]:
            parts.append(f"- {e['t']}: {e['description']}")
    else:
        parts.append("- (you have not observed anything yet)")
    parts += ["", "YOUR PRIVATE MEMORIES, BELIEFS, AND PLANS"]
    if view["private_memories"]:
        for m in view["private_memories"]:
            parts.append(f"- {m['content']}")
    else:
        parts.append("- (none yet)")
    if view["reasons"]:
        parts += ["", "WHY YOU ARE CONSIDERING THINGS NOW"]
        for r in view["reasons"]:
            parts.append(f"- {r}")
    return "\n".join(parts)
