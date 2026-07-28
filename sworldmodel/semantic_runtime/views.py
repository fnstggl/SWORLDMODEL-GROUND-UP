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

There is no free-text channel into a view.  Even the line explaining why
the actor is being consulted now is composed by code out of that actor's
OWN observed records: callers pass event ids, not prose, so nothing the
world wrote can enter a view except through an event the code has already
established this actor observed.
"""
from __future__ import annotations

from .envelope import contained
from .journal import Journal

#: what an actor is told when they are simply being consulted again after
#: time has passed -- a wake carries no information, only timing
ELAPSED_TIME_REASON = ("time has passed and you are looking at your "
                       "situation again")


def build_view(world, journal: Journal, actor_id: str, *,
               trigger_event_ids=()) -> dict:
    """The complete and only input a given actor's model receives."""
    st = world.actors[actor_id]
    observed = journal.observed_by(actor_id)
    memories = [{"t": m.t.isoformat(), "kind": m.kind, "content": m.content}
                for m in st.memories if m.kind == "private"]
    # the "why now" line is looked up in this actor's own observed events;
    # an id they did not observe simply produces nothing
    by_id = {e["event_id"]: e for e in observed}
    reasons = [f"you observed: {by_id[eid]['description']}"
               for eid in (trigger_event_ids or []) if eid in by_id]
    if not reasons:
        reasons = [ELAPSED_TIME_REASON]
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
        "reasons": reasons,
    }


def render_view(view: dict) -> str:
    """The stable natural-language rendering handed to the actor model.

    Every heading is written here, by code.  Every value that came from a
    model is passed through ``contained`` first, so it occupies exactly the
    one line code gave it and cannot forge a section of its own.
    """
    parts = [
        "CURRENT TIME", view["now"], "",
        "WHO YOU ARE",
        f"{contained(view['name'])} (your identity in this situation: "
        f"{view['actor_id']})",
        contained(view["private_context"]) if view["private_context"]
        else "(no further private context)", "",
        "SHARED CONTEXT",
        contained(view["shared_context"]) if view["shared_context"]
        else "(none)", "",
        "WHAT YOU HAVE OBSERVED",
    ]
    if view["observed_events"]:
        for e in view["observed_events"]:
            parts.append(f"- {e['t']}: {contained(e['description'])}")
    else:
        parts.append("- (you have not observed anything yet)")
    parts += ["", "YOUR PRIVATE MEMORIES, BELIEFS, AND PLANS"]
    if view["private_memories"]:
        for m in view["private_memories"]:
            parts.append(f"- {contained(m['content'])}")
    else:
        parts.append("- (none yet)")
    if view["reasons"]:
        parts += ["", "WHY YOU ARE CONSIDERING THINGS NOW"]
        for r in view["reasons"]:
            parts.append(f"- {contained(r)}")
    return "\n".join(parts)
