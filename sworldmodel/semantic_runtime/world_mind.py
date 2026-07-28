"""The world model: one universal prompt for every scenario.

The world answers exactly one question: given the current real situation
and ONE concrete trigger, what immediately and realistically happens next?

It adjudicates soft reality -- whether an available item reaches someone's
attention, whether an attempted action concretely succeeds, how long
ordinary human activity takes, whether something interrupts it, what
immediate observable result occurs, who can access that result, and
whether it has already been observed.

It never chooses what an actor intends, never narrates several future
stages at once, never produces probabilities or weights, never sees the
resolution, and never steers toward an outcome.
"""
from __future__ import annotations

from .envelope import EVENT_SCHEMA

WORLD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["judgment", "event", "wakes"],
    "properties": {
        "judgment": {"type": "string", "minLength": 1},
        "event": {"anyOf": [EVENT_SCHEMA, {"type": "null"}]},
        "wakes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["actor", "after", "reason"],
                "properties": {
                    "actor": {"type": "string", "minLength": 1},
                    "after": {"type": "string", "minLength": 1},
                    "reason": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

WORLD_SYSTEM = """You are the world: physical reality, institutions, \
systems, and the ordinary circumstances that surround people.  You decide \
what CONCRETELY HAPPENS NEXT as an immediate consequence of one trigger.

Your one job is the next immediate step -- nothing further.  Never narrate \
a chain of future stages in one answer.  If someone attempts to send \
something, the immediate consequence is the sending, not the receiving, \
the noticing, the reading, the reaction, or the outcome.  Each of those is \
a separate later step you will be asked about separately.

Keep these genuinely distinct.  Information can exist, then be sent, then \
arrive somewhere a person could see it, then actually reach their \
attention, then actually be read, then be understood.  Arriving is NOT \
noticing.  Noticing is NOT reading.  People miss things, postpone them, \
skim them, forget them, and never get to them at all.

You decide circumstances; you never decide what a person intends or \
chooses.  You may determine that someone is busy, interrupted, away, or \
that something goes wrong -- but whether they decide to act is theirs.

Attention is a concrete situated event, never a chance: judge from the \
actual circumstances in front of you (what else is happening, how much \
they have to deal with, when they would plausibly be looking) and state \
what in fact happens.  Never give percentages, odds, likelihoods, scores \
or weights.  Never sample or randomise.

Be realistic rather than convenient.  Ordinary human activity takes real \
time; things fail, stall and get delayed; nothing should happen merely \
because it would move the situation along.

Reply with ONLY a JSON object:
{
  "judgment": "one or two sentences grounded in the current situation",
  "event": {
    "description": "the single immediate concrete event, in plain language",
    "for": ["actor_id"],
    "observed": false,
    "after": "43 seconds"
  },
  "wakes": [
    {"actor": "actor_id", "after": "2 hours",
     "reason": "why this person's situation should be revisited then"}
  ]
}
"event" may be null when nothing concrete happens yet.
"wakes" may be empty.
"for" lists the actor ids the event or its information becomes AVAILABLE \
to.  "observed" is true only if EVERY listed actor has actually observed \
it already; if some have and some have not, emit the event for one group \
now and let the rest be judged separately later.
"after" is how much simulated time passes before this event occurs: "now", \
"43 seconds", "5 minutes", "2 hours", or "3 days".
Use exactly the actor ids given to you.  Do not add any other fields."""


def world_user_prompt(*, now: str, shared_context: str, journal_text: str,
                      actor_ids: list, trigger_kind: str, trigger_text: str,
                      actor_id: str | None = None,
                      actor_private: str | None = None,
                      available_unobserved: list | None = None) -> str:
    parts = [f"CURRENT TIME\n{now}", "",
             f"BACKGROUND (true for this situation)\n{shared_context}", "",
             f"ACTOR IDS YOU MAY USE\n{', '.join(actor_ids)}", "",
             f"WHAT HAS CONCRETELY HAPPENED SO FAR\n{journal_text}", ""]
    if actor_id:
        parts += [f"THE PERSON THIS CONCERNS\n{actor_id}"
                  + (f"\ntheir circumstances: {actor_private}"
                     if actor_private else ""), ""]
    if available_unobserved:
        parts.append("ITEMS AVAILABLE TO THEM THAT THEY HAVE NOT YET "
                     "OBSERVED")
        for e in available_unobserved:
            parts.append(f"- [{e['t']}] ({e['event_id']}) {e['description']}")
        parts.append("")
    parts += [f"THE TRIGGER YOU MUST JUDGE ({trigger_kind})\n{trigger_text}",
              "",
              "What immediately and concretely happens next?  One step "
              "only.  Reply with ONLY the JSON object."]
    return "\n".join(parts)


class WorldResponseError(ValueError):
    pass


def validate_world_response(obj) -> dict:
    if not isinstance(obj, dict):
        raise WorldResponseError("world response must be an object")
    unknown = set(obj) - {"judgment", "event", "wakes"}
    if unknown:
        raise WorldResponseError(
            f"world response has unexpected fields {sorted(unknown)}")
    if not isinstance(obj.get("judgment"), str) or not obj["judgment"].strip():
        raise WorldResponseError("judgment must be a non-empty string")
    return {"judgment": obj["judgment"].strip(),
            "event": obj.get("event"),
            "wakes": obj.get("wakes") or []}
