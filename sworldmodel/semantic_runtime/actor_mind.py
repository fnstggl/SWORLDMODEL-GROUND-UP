"""The actor model: one universal prompt for every scenario.

The actor answers exactly one question: given what this person currently
knows, remembers and observes, what do they attempt, and how does their
private understanding change?

They never receive the global journal, unobserved information, another
actor's private memories, the resolution, the YES/NO target, future
scheduled events, or hidden world judgments -- the view handed in is
built by code from their own authorized records alone.

An actor proposes; it never adjudicates.  Nothing an actor writes is ever
committed as something that happened: an intention is handed to the world
as an ATTEMPT and the world decides what, if anything, came of it, and
only committed events can satisfy the question.

Whether the response is GROUNDED -- consistent with this person's own
evidence, memory and prior actions -- is checked by the read-only
continuity review at the bottom of this module.  It is not a second actor:
it chooses nothing, proposes nothing, and never sees the resolution.  It
reads what this actor was given and what this actor replied, and says
whether the reply follows from it.
"""
from __future__ import annotations

from .envelope import (EnvelopeError, clean_text, contained,
                       parse_duration)

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

What you are told about yourself under AUTHORITATIVE ACTOR EVIDENCE is \
true and takes precedence.  Where it says what you do, what you are \
dealing with, how you usually behave, what you have already done or what \
you are committed to, that is what is so -- even where a general \
impression of someone in your position would suggest otherwise.  Do not \
behave like a generic average person when your own evidence says \
something more specific.

Do not play a caricature.  Do not exaggerate anything associated with \
your name, your job, your age, where you are from, your standing or your \
role, and do not invent traits, habits, catchphrases, preferences, \
relationships or history that your evidence does not give you.  Who you \
are can help you read an ambiguous situation; it never overrides what you \
have actually been told.

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

Stay consistent with what you have already decided, remembered, \
committed to and tried.  Change course only because something changed: a \
new observation, a remembered fact that now matters, a real deadline \
materially closer, an earlier action finishing or failing, a genuine \
conflict between your own goals, or a reconsideration you can ground in \
what you already have.  Time passing by itself is not a reason to reverse \
a decision, and it is not a reason to go over an unchanged question \
again.

Do not mention a specific person, organisation, fact, message, \
commitment or event unless it is in your evidence, in something you \
actually observed, in your own earlier actions, or in your own memories.  \
Never invent a named person.

Do not settle a situation sooner than you really would.  If there is \
still time, there is still time: people wait, chase, ask again, put it \
off, and leave things open until they actually have to decide.  Calling \
something off, giving up on it, or announcing it cannot happen is itself \
a decision with consequences -- make it only at the point where you truly \
would, not the first time it looks difficult.

If you attempt more than one thing, they must be genuinely different \
things.  Saying the same thing twice in different words is one action, \
not two.

Say what you attempt at the scale you would tell someone about it \
afterwards -- "I put it in my diary for Thursday", not opening the diary, \
typing the entry and closing it again.  Never describe the mechanics of \
using a thing.

Reply with ONLY a JSON object:
{
  "decision": "one or two sentences: what you are deciding and why",
  "intentions": ["a concrete action you attempt now, in your own words"],
  "private_updates": ["a memory, interpretation, belief, plan or \
commitment you now privately hold"],
  "next_wake": null
}
"next_wake" is how you come back to something later, and it exists only \
for a real plan or commitment: {"after": "1 day", "reason": "look at the \
counteroffer tomorrow morning after sleeping on it"}.  Say WHAT you will \
revisit and why that time means something.  Never ask to "reconsider \
later" or to check again in general -- that is not a plan, and it will be \
refused.  Use null when you have no such plan.
"intentions" may be empty if you attempt nothing right now.
"private_updates" may be empty if nothing about your understanding changed.
Do not include any other fields.  Do not explain your reasoning beyond the \
brief "decision" summary."""


class ActorResponseError(ValueError):
    pass


def validate_actor_response(obj, *, held_memories=()) -> dict:
    """Structural validation, plus the one thing exact matching can do
    about repetition: a private update this person already holds, word for
    word, is not a new belief and is dropped."""
    if not isinstance(obj, dict):
        raise ActorResponseError("actor response must be an object")
    unknown = set(obj) - {"decision", "intentions", "private_updates",
                          "next_wake"}
    if unknown:
        raise ActorResponseError(
            f"actor response has unexpected fields {sorted(unknown)}")
    if not isinstance(obj.get("decision"), str) or not obj["decision"].strip():
        raise ActorResponseError("decision must be a non-empty string")
    try:
        decision = clean_text(obj["decision"].strip(), field="decision")
    except EnvelopeError as e:
        raise ActorResponseError(str(e)) from None
    out = {"decision": decision, "intentions": [], "private_updates": [],
           "next_wake": validate_next_wake(obj.get("next_wake"))}
    already = {contained(m).casefold() for m in held_memories}
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
            if not item.strip():
                continue
            try:
                text = clean_text(item.strip(), field=field)
            except EnvelopeError as e:
                raise ActorResponseError(str(e)) from None
            if field == "private_updates" \
                    and contained(text).casefold() in already:
                continue          # they already believe this, word for word
            if field == "private_updates":
                already.add(contained(text).casefold())
            out[field].append(text)
    return out


def validate_next_wake(proposed):
    """A plan to come back to something, or nothing.

    Code owns the instant, the cause and the provenance; the actor owns
    only how long and why.  "Reconsider later" is not a plan and is
    refused here rather than becoming a poll.
    """
    if proposed in (None, "", {}):
        return None
    if not isinstance(proposed, dict):
        raise ActorResponseError("next_wake must be an object or null")
    unknown = set(proposed) - {"after", "reason"}
    if unknown:
        raise ActorResponseError(
            f"next_wake has unexpected fields {sorted(unknown)}")
    reason = str(proposed.get("reason", "")).strip()
    if not reason:
        raise ActorResponseError("next_wake needs a reason: what will you "
                                 "revisit, and why then?")
    try:
        parse_duration(str(proposed.get("after", "")))
        reason = clean_text(reason, field="next_wake.reason")
    except EnvelopeError as e:
        raise ActorResponseError(str(e)) from None
    return {"after": str(proposed["after"]).strip(), "reason": reason}


def actor_user_prompt(rendered_view: str) -> str:
    """The closing question asks for the plan as well as the action.

    Nothing else brings a person back to a situation: there is no timer
    anywhere in this runtime, by design.  If someone with unfinished
    business does not say when they will next look at it, they do not look
    at it again, and the situation stops -- one live negotiation ended
    after three steps with twelve days still to run.
    """
    return (rendered_view
            + "\n\nGiven only what you know above: what do you attempt now, "
              "what changes in your own private understanding, and -- if "
              "this is not finished for you -- when will you next come back "
              "to it, and why then?  If you genuinely expect to think about "
              "this again, say so in \"next_wake\"; nothing else will bring "
              "it back to you.  Reply with ONLY the JSON object.")


# ------------------------------------------------- the continuity review
#: A read-only check that a proposed response actually follows from what
#: this person has.  It is not a second actor: it proposes nothing,
#: chooses nothing, and never sees the resolution, the question, the
#: cutoff, another actor's private state or any future event.  Prompt
#: instruction alone did not hold -- people repeated completed actions,
#: reversed plans for no reason, and waited eight turns for a housemate
#: who did not exist -- and none of those are things a validator can see,
#: because seeing them means reading the sentence.
CONTINUITY_SYSTEM = """You check one thing: whether what this person just \
said follows from what this person actually has.

You are given their own evidence, what they have observed, what they have \
already decided and tried, what they currently believe and plan, the time, \
and their proposed reply.  You are given nothing else, and there is \
nothing else to consider.

WHAT YOU ARE NOT DOING, and this matters more than the rest: you are not \
deciding what they should do.  A person may CHOOSE anything their \
situation allows.  Naming a price, forming a plan, changing their mind \
about what they want, deciding to wait, deciding to push, deciding to \
give up -- none of these need to be authorised by their evidence, because \
choosing is the one thing that is entirely theirs.  A choice you would \
not have made, or would not have made yet, is not a defect.  Neither is \
being unhelpful, slow, stubborn, uninterested, mistaken or inactive.

You are checking two things only: whether they CONTRADICT what they \
themselves have already established, and whether they treat as FACT \
something that is not.

CHASING IS NOT A DEFECT.  Doing a thing again because the thing you were \
waiting on still has not happened is what people do -- following up, \
ringing back, asking a second time, sending another message.  It is a \
choice, and choices are theirs.  What is a defect is presenting it as \
the first time, or doing again something that already WORKED.

Answer REVISE when the reply:
- contradicts something they still believe, without saying what changed;
- does again something that already succeeded, or presents something they \
have already done as though they were doing it for the first time;
- says again, in different words, something they already believe;
- abandons or reverses a plan they still hold, without anything having \
happened that would explain it -- not merely a plan you would have kept;
- states as fact something they were never told and never observed -- what \
someone else has done, said, decided or is thinking, or what has happened \
elsewhere.  A guess they clearly hold as a guess is fine; people guess;
- names a specific person, organisation or event that appears nowhere in \
what they have;
- ignores a constraint of theirs that directly bears on this;
- attempts something that is actually someone else's action to take;
- reads as a generic person going through the motions when their own \
evidence says something more specific;
- plays up a stereotype their evidence does not support.

Answer PASS otherwise, and when in doubt answer PASS.  A plan changed \
because of something they observed is not a defect: that is what \
observing is for.  Do not reason about what their evidence "implies" they \
would want or do; that is theirs to say, not yours to infer.

Reply with ONLY a JSON object:
{"verdict": "PASS" | "REVISE", "reason": "one sentence: the exact defect, \
or what makes it consistent"}"""


def continuity_user_prompt(rendered_view: str, response: dict) -> str:
    lines = [rendered_view, "", "THE REPLY THEY PROPOSE",
             f"decision: {contained(response['decision'])}"]
    for i in response["intentions"]:
        lines.append(f"attempts: {contained(i)}")
    for u in response["private_updates"]:
        lines.append(f"now privately holds: {contained(u)}")
    if response.get("next_wake"):
        lines.append(f"plans to come back after "
                     f"{contained(response['next_wake']['after'])}: "
                     f"{contained(response['next_wake']['reason'])}")
    lines += ["", "Does this follow from what they have?  Reply with ONLY "
                  "the JSON object."]
    return "\n".join(lines)


class ContinuityError(ValueError):
    pass


def validate_continuity(obj) -> dict:
    if not isinstance(obj, dict):
        raise ContinuityError("continuity review must be an object")
    unknown = set(obj) - {"verdict", "reason"}
    if unknown:
        raise ContinuityError(f"unexpected fields {sorted(unknown)}")
    if obj.get("verdict") not in ("PASS", "REVISE"):
        raise ContinuityError('verdict must be "PASS" or "REVISE"')
    reason = str(obj.get("reason", "")).strip()
    if not reason:
        raise ContinuityError("reason must be a non-empty string")
    try:
        reason = clean_text(reason, field="reason")
    except EnvelopeError as e:
        raise ContinuityError(str(e)) from None
    return {"verdict": obj["verdict"], "reason": reason}
