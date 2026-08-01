"""Code-only actor-local view construction.

No LLM builds or filters a view.  Code selects authorized records by exact
actor identity and stored visibility state, then renders their text into a
stable template.  There is no semantic search, vector retrieval, salience
weighting, importance scoring or relevance ranking here -- selection is
mechanical:

    actor_id in event["for"]  AND  event["observed"] is True

Everything else about the actor (identity, their own evidence, their own
memories, their own prior actions, the current simulated time) is added by
identity, never by interpretation.

The compiled ``shared_context`` is NOT here.  It is the world's
background, written by the compiler as an outside description of the
situation, and in six live runs every one of them leaked something
through it: a man with "you have not observed anything yet" in his prompt
named the sender of an email nobody had delivered, because the sender's
own plan was in that block.  An actor learns a public fact the way people
do -- from their own evidence, from a starting event they could see, or
from something they observed.

There is no free-text channel into a view.  Even the line explaining why
the actor is being consulted now is composed by code out of that actor's
OWN observed records: callers pass event ids, not prose, so nothing the
world wrote can enter a view except through an event the code has already
established this actor observed.
"""
from __future__ import annotations

from sworldmodel.simclock import iso, parse_iso

from .envelope import contained
from .journal import Journal, OP_ACTOR_CALL

#: what an actor is told when they are simply being consulted again after
#: time has passed -- a wake carries no information, only timing
ELAPSED_TIME_REASON = ("time has passed and you are looking at your "
                       "situation again")


def build_view(world, journal: Journal, actor_id: str, *,
               trigger_event_ids=(), busy_until=None) -> dict:
    """The complete and only input a given actor's model receives."""
    st = world.actors[actor_id]
    # What they are in the middle of.  A person who is on a call knows they
    # are on a call, and answers differently because of it.  Without this
    # the runtime knew somebody was occupied and the person did not.
    now = world.clock.now
    occupied = (iso(busy_until) if busy_until and busy_until > now else None)
    # What they have observed -- but NOT the world's account of the far
    # end of something they sent.
    #
    # The author of an event is recorded as having observed it, because a
    # person knows what they did and the judge needs that (a man's own
    # confirming text once read as observed by nobody, and the judge
    # answered that he never confirmed).  But the world writes the sending
    # and where it landed in one event, so granting the whole text handed a
    # woman, as authoritative observed fact, that her message had not been
    # delivered because the other person's phone was off -- the one thing
    # she could not know.
    #
    # They still know they did it: their own attempt is rendered below,
    # from their own call records.  What is withheld is the world's
    # description of the far end.
    observed = [e for e in journal.observed_by(actor_id)
                if actor_id in e["for"]]
    memories = [{"t": m.t.isoformat(), "kind": m.kind, "content": m.content}
                for m in st.memories if m.kind == "private"]
    # What this person has already decided and attempted, read from their
    # OWN call records.  Without it they have no memory of their own
    # actions: one live run had a man send the same offer twice two
    # seconds apart, another had someone put their phone away and open it
    # again in the same breath, and a third had a supervisor announce she
    # had "just" opened a file she opened a day earlier.  A person
    # remembers what they did.
    did = [{"t": r["t"], "decision": r["data"]["decision"],
            "intentions": list(r["data"]["intentions"])}
           for r in world.records
           if r["op"] == OP_ACTOR_CALL and r["data"]["actor"] == actor_id]
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
        "observed_events": [{"event_id": e["event_id"], "t": e["t"],
                             "description": e["description"]}
                            for e in observed],
        "private_memories": memories,
        "own_actions": did,
        "reasons": reasons,
        "busy_until": occupied,
    }


def _when(stamp: str) -> str:
    """An instant as a person would hold it: the day of the week, then the
    clock.

    A bare ISO string is not a fact anybody has.  Every scene's evidence is
    written in weekdays -- "away until Friday", "the deadline is Thursday
    at five" -- and the people in it were given a timestamp and left to do
    the calendar themselves.  They got it wrong constantly: a man decided
    10:17 was past the noon deadline he had set himself and went off to
    list his kiln elsewhere while the acceptance sat unread on his phone;
    another believed an hour had passed when it had been a day.  The
    reviewer whose job is to catch that agreed with them, because it was
    reading the same bare string and doing the same arithmetic.

    Time is code's to keep.  Handing somebody a number and asking them to
    derive the weekday from it is handing them a chance to be wrong about
    what day it is, which is not a thing people are wrong about.
    """
    try:
        t = parse_iso(stamp)
    except Exception:
        return stamp
    return f"{stamp} ({t.strftime('%A')})"


def render_view(view: dict) -> str:
    """The stable natural-language rendering handed to the actor model.

    Every heading is written here, by code.  Every value that came from a
    model is passed through ``contained`` first, so it occupies exactly the
    one line code gave it and cannot forge a section of its own.
    """
    parts = [
        "CURRENT TIME", _when(view["now"]), "",
        "WHO YOU ARE",
        f"{contained(view['name'])} (your identity in this situation: "
        f"{view['actor_id']})",
        "", "AUTHORITATIVE ACTOR EVIDENCE",
        contained(view["private_context"]) if view["private_context"]
        else "(nothing further about you)", "",
        "WHAT YOU HAVE ACTUALLY OBSERVED",
    ]
    if view["observed_events"]:
        for e in view["observed_events"]:
            parts.append(f"- {_when(e['t'])}: "
                         f"{contained(e['description'])}")
    else:
        parts.append("- (you have not observed anything yet)")
    parts += ["", "WHAT YOU HAVE ALREADY DECIDED AND TRIED"]
    if view.get("own_actions"):
        for a in view["own_actions"]:
            attempts = "; ".join(contained(i) for i in a["intentions"]) \
                or "nothing"
            parts.append(f"- {a['t']}: {contained(a['decision'])} "
                         f"-> you attempted: {attempts}")
    else:
        parts.append("- (you have not done anything yet)")
    parts += ["", "YOUR CURRENT MEMORIES, BELIEFS, PLANS, AND COMMITMENTS"]
    if view["private_memories"]:
        for m in view["private_memories"]:
            parts.append(f"- {contained(m['content'])}")
    else:
        parts.append("- (none yet)")
    if view.get("busy_until"):
        parts += ["", "WHAT YOU ARE IN THE MIDDLE OF RIGHT NOW",
                  f"You are occupied until {view['busy_until']}.  Whatever "
                  f"you decide to do next begins after that, not now."]
    if view["reasons"]:
        parts += ["", "WHAT HAS CHANGED SINCE YOUR LAST TURN"]
        for r in view["reasons"]:
            parts.append(f"- {contained(r)}")
    return "\n".join(parts)
