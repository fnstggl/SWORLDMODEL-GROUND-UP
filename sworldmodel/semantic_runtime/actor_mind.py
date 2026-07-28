"""The actor model: one universal prompt for every scenario.

The actor answers exactly one question: given what this person currently
knows, remembers and observes, what do they attempt, and how does their
private understanding change?

They never receive the global journal, unobserved information, another
actor's private memories, the resolution, the YES/NO target, future
scheduled events, or hidden world judgments -- the view handed in is
built by code from their own authorized records alone.

An actor proposes; it never adjudicates.  Claims of success, delivery,
another person's observation, another person's belief, or the terminal
are world consequences and are rejected as intentions.
"""
from __future__ import annotations

#: A person takes a bounded number of actions in one moment.  This is also
#: the budget boundary: every intention costs a world adjudication, so an
#: unbounded list would let the model decide how much the runtime spends.
#: Code controls access; the model writes meaning.
MAX_INTENTIONS_PER_TURN = 3
MAX_PRIVATE_UPDATES_PER_TURN = 6

ACTOR_SYSTEM = """You are one specific person inside a real, ongoing \
situation.  You are not an assistant, not a narrator, and not a \
storyteller: you are this person, living their own day, with their own \
priorities, workload, habits and limits.

You know ONLY what appears in the briefing you are given.  You cannot see \
anyone else's thoughts, you do not know what anyone else has noticed or \
decided, and you cannot see anything you have not personally observed.  \
Time has passed exactly as the briefing says.

You decide only what YOU attempt.  You do NOT decide:
- whether your attempt succeeds;
- whether anyone receives, notices, reads or understands anything;
- what anyone else thinks, feels, believes, or does;
- whether any agreement, outcome or result exists.
Those are consequences the world determines.  State attempts as attempts \
("I write and send X", "I look at Y", "I wait until Z"), never as \
accomplished facts about other people.

Behave like the real person would, including when that is unhelpful: real \
people are busy, distracted, sceptical, forgetful, slow to reply, and \
often do nothing at all.  Doing nothing is a legitimate answer.

Reply with ONLY a JSON object:
{
  "decision": "one or two sentences: what you are deciding and why",
  "intentions": ["a concrete action you attempt now, in your own words"],
  "private_updates": ["a memory, interpretation, belief, plan or \
commitment you now privately hold"]
}
"intentions" may be empty if you attempt nothing right now.
"private_updates" may be empty if nothing about your understanding changed.
Do not include any other fields.  Do not explain your reasoning beyond the \
brief "decision" summary."""


class ActorResponseError(ValueError):
    pass


def validate_actor_response(obj) -> dict:
    if not isinstance(obj, dict):
        raise ActorResponseError("actor response must be an object")
    unknown = set(obj) - {"decision", "intentions", "private_updates"}
    if unknown:
        raise ActorResponseError(
            f"actor response has unexpected fields {sorted(unknown)}")
    if not isinstance(obj.get("decision"), str) or not obj["decision"].strip():
        raise ActorResponseError("decision must be a non-empty string")
    out = {"decision": obj["decision"].strip(), "intentions": [],
           "private_updates": []}
    caps = {"intentions": MAX_INTENTIONS_PER_TURN,
            "private_updates": MAX_PRIVATE_UPDATES_PER_TURN}
    for field in ("intentions", "private_updates"):
        value = obj.get(field, [])
        if value is None:
            value = []
        if not isinstance(value, list):
            raise ActorResponseError(f"{field} must be an array")
        if len(value) > caps[field]:
            raise ActorResponseError(
                f"{field} has {len(value)} entries; at most {caps[field]} "
                f"are accepted in one turn")
        for item in value:
            if not isinstance(item, str):
                raise ActorResponseError(f"{field} entries must be strings")
            if item.strip():
                out[field].append(item.strip())
    return out


def actor_user_prompt(rendered_view: str) -> str:
    return (rendered_view
            + "\n\nGiven only what you know above, what do you attempt now, "
              "and what changes in your own private understanding?  Reply "
              "with ONLY the JSON object.")
