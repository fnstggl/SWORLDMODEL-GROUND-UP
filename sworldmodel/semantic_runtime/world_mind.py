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

The response shape is enforced in code, not by the provider:
``validate_world_response`` requires the three fields and rejects every
additional property, and the event and wakes it carries are then checked
by ``envelope.validate_event`` / ``envelope.validate_wakes`` before
anything is committed.
"""
from __future__ import annotations

import difflib
import re

from .envelope import (EnvelopeError, clean_text, contained,
                       validate_event, validate_wakes)


#: How close two descriptions must be before they are the same act said
#: twice.  An exact casefold match caught eleven word-for-word repeats in
#: one corpus and missed roughly forty-six rewordings -- a woman signed one
#: lease twice a minute apart, a call was released twice, a decisive act was
#: committed twice.  A model does not write the same sentence twice; it
#: writes the same event twice.
SAME_ACT = 0.80
_TRIVIAL = re.compile(r"\b(?:the|a|an|his|her|their|its|then|now|just|"
                      r"finally|and|to|of|in|on|at|with|from|by)\b")


def _shape(text: str) -> str:
    """What an event is ABOUT, with the wording sanded off."""
    return " ".join(sorted(set(
        _TRIVIAL.sub(" ", (text or "").casefold()).split())))


_NUMBERS = re.compile(r"\d+|\b(?:first|second|third|fourth|fifth|sixth|"
                      r"seventh|eighth|ninth|tenth|one|two|three|four|five|"
                      r"six|seven|eight|nine|ten)\b", re.I)

#: A capitalised word: a name.  Two events naming different people are
#: about different people, whatever else they share -- "Ruth calls Dev
#: Sandhu, it goes to voicemail" and "Ruth calls Nina Achebe, it goes to
#: voicemail" read as 0.84 identical and are two different phone calls.
#:
#: Sentence-opening words are counted too, which occasionally catches a
#: "She" or a "The".  That errs towards leaving two events alone, and
#: leaving a repeat in the record costs a duplicate line; merging two real
#: acts deletes somebody's afternoon.  The cheap mistake is the one to
#: make.
_NAME = re.compile(r"\b([A-Z][a-z]{2,})\b")


#: Whether the sentence says a thing happened or says it did not.  A bag
#: of sorted tokens cannot see this at all: "he can host" against "he
#: cannot host" scores 0.96, "the booking is going ahead" against "is not
#: going ahead" 0.95 -- and in every such pair the one that would be
#: deleted is the decisive act of the scene.  A negation is a fact about
#: what happened, so it disqualifies a match exactly as a number does.
_NEGATION = re.compile(
    r"\b(?:not|n't|no|never|cannot|can't|won't|wouldn't|couldn't|didn't|"
    r"doesn't|isn't|aren't|wasn't|weren't|hasn't|haven't|without|unable|"
    r"fails?|failed|refuses?|refused|declines?|declined|denies|denied|"
    r"cancels?|cancelled|canceled|unsuccessful|neither|nor)\b", re.I)


def _facts(text: str) -> tuple:
    """The parts of a description that are not wording: who is named, what
    quantities appear, and whether it is saying yes or no.  These are what
    an act is ABOUT; the rest is how it happened to be phrased that time."""
    t = text or ""
    return (sorted(m.group().casefold() for m in _NUMBERS.finditer(t)),
            sorted({m.group(1).casefold() for m in _NAME.finditer(t)}),
            sorted({m.group().casefold().replace("'", "")
                    for m in _NEGATION.finditer(t)}))


def says_the_same_thing(a: str, b: str) -> bool:
    """Close enough to be one act said twice, given that code has already
    established the same person did them for the same audience.

    Wording alone cannot decide this and must not be asked to.  "Dana
    sends a message asking Marcus to confirm the hall" and "Marcus replies
    confirming the hall" score 0.85 against each other -- higher than many
    genuine repeats -- because a bag of words has no verb and no subject.
    Lowering the threshold to catch the repeats deletes the reply, which
    is the decisive act of that scene.

    So identity does the discriminating and wording only finishes the job:
    the caller supplies same-doer and same-audience, this rejects any pair
    that names different people or different quantities, and what is left
    is compared as text.  On the shipped corpus that separates 24 genuine
    repeats -- one call made four times, one banking app checked five --
    from every cross-actor pair, with no false merge.
    """
    if _facts(a) != _facts(b):
        return False
    return difflib.SequenceMatcher(None, _shape(a), _shape(b)).ratio() \
        >= SAME_ACT

WORLD_SYSTEM = """You are the world: physical reality, institutions, \
systems, and the ordinary circumstances that surround people.  You decide \
what CONCRETELY HAPPENS NEXT as an immediate consequence of one trigger.

Your one job is the next immediate step -- nothing further.  Never narrate \
a chain of future stages in one answer.  If someone attempts to send \
something, the immediate consequence is the sending, not the receiving, \
the noticing, the reading, the reaction, or the outcome.  Each of those is \
a separate later step you will be asked about separately.

DELIVERY IS NOT YOURS AND YOU NEVER NARRATE IT.  Whether something has been sent, has arrived, is sitting where somebody could see it, or has been seen by them is recorded by the machinery, on the thing itself.  Never write that a message arrives, lands in an inbox, is delivered, appears on a screen, buzzes, shows a notification, is still unread, is still waiting, or remains where it was.  None of those are events; they are the state of an item, and it is already known.

What you DO decide about attention is whether a person's notice actually reaches something -- "she sees it while clearing her messages", "he does not look at his phone all afternoon".  That is a fact about the person's circumstances and it is yours.  The arriving is not.

ONE MEANINGFUL THING, NOT ITS PIECES.  When somebody does something, the event is the whole of what they did, at the scale another person would describe it: "she signs the lease and sends it back", not opening the file, clicking print, the printer starting, the printer finishing, signing, opening the scanner, the scanner saving, attaching, and pressing send.  Those are not nine events.  They are one thing a person did.

If an attempt only partly comes off, say so as one event -- "she signs it but cannot get the scanner to work" -- rather than splitting it.

A LIVE EXCHANGE IS ONE EVENT, NOT A TRANSCRIPT.  When two people are talking to each other -- by telephone, face to face, in any back-and-forth where each hears the other as they speak -- the event is the exchange and what came of it: "she talks it through with him and he walks her through the setting", with "lasts" the length of the conversation.  It is NEVER a sequence of one answering, one greeting, one listening, one hearing what the other just said, one asking a question, one hearing the reply.  Those are not events; they are the inside of a conversation, and nobody recounts a conversation that way.

While two people are talking, each hears the other as it happens.  An exchange is "observed": true for both, and there is no separate step in which what one of them said reaches the other.  If the exchange does not finish the matter -- somebody is put on hold, or goes away to try something -- say what was reached as one event and let the rest be a later step.

You decide circumstances; you never decide what a person intends or \
chooses.  You may determine that someone is busy, interrupted, away, or \
that something goes wrong -- but whether they decide to act is theirs.

THE STOP RULE, which matters more than finishing the story: the moment the \
next thing that would happen depends on a person CHOOSING it, you stop.  \
Never write that someone opens, reads, answers, agrees, refuses, accepts, \
decides, goes, buys, signs, or acts on something.  Those are their \
decisions and they will be asked separately.  When something reaches a \
person's awareness, emit exactly that -- "X notices Y" with "observed": \
true for that person -- and nothing after it.  If awareness has not \
happened, keep the event "observed": false and describe only what the \
environment did.

WHEN INFORMATION MOVES, THE EVENT MUST CARRY IT.  "She replies that she \
can host on Saturday", never "she replies".  "He answers that the price \
is too high", never "he answers".  An event nobody could learn anything \
from is not information moving, and whoever observes it will know exactly \
what you wrote and nothing more.

Things go wrong in ordinary ways that have nothing to do with anyone's \
attention: something is misread or misunderstood, something breaks or is \
lost, a plan is cancelled, someone is unwell, an arrangement falls \
through.  People and organisations OUTSIDE the list of actors act too -- \
they chase, they follow up, they close their books, they carry on without \
waiting.  Say so when that is what would really happen.  A situation in \
which the only thing that ever goes wrong is that somebody did not get \
round to it is not a realistic situation.

TIME NOBODY HERE IS SPENDING.  Sometimes you are asked what happened \
across a stretch of time in which none of these people did anything.  \
That is the world's own turn, and the answer is not always "nothing": \
offices open and shut, deadlines pass, other people chase what they are \
owed, weather and transport and machines carry on, third parties make \
their own arrangements.  Answer with what the SITUATION did while these \
people were not acting on it -- and because nobody here did it, "by" is \
null.  If genuinely nothing happened that anyone here would ever find \
out about, say so in "judgment" and return "event": null.

Never put a clock time or a date inside an event.  The time is recorded \
separately, by the machinery, and it is authoritative; anything you write \
about what time it is will contradict it.

The event you emit must be the thing your own judgment just described.  \
If your judgment says someone arrives home in the morning, the event is \
that arrival -- not something else, somewhere else, later.

Do not contradict what is already in the record: if a message has already \
arrived somewhere, it cannot arrive somewhere else later, and nothing that \
has been committed can be undone or rewritten.

Do not restate the record either.  If what you are about to write is \
already there in different words, that step has HAPPENED -- writing it \
again would make the same thing occur twice.  Move to whatever genuinely \
has not happened yet, or return "event": null.

What you are shown about a person's own circumstances is background for \
YOUR judgment.  Never repeat it, quote it, or restate it inside an event: \
an event says what visibly happened, not what someone privately thinks, \
plans, feels or is secretly dealing with.

Attention is a concrete situated event, never a chance: judge from the \
actual circumstances in front of you (what else is happening, how much \
they have to deal with, when they would plausibly be looking) and state \
what in fact happens.  Never give percentages, odds, likelihoods, scores \
or weights.  Never sample or randomise.

Be realistic rather than convenient.  Ordinary human activity takes real \
time; things fail, stall and get delayed; nothing should happen merely \
because it would move the situation along.

HOW LONG IT TAKES.  Two different questions, and both are yours.

"after" is the wait before it starts.  "lasts" is how long it then takes.  \
Waiting three hours for somebody to get to their messages is "after": 3 \
hours, "lasts": a couple of minutes.  A support call answered straight \
away and running half an hour is "after": now, "lasts": 30 minutes.

Judge both from the situation in front of you.  Anything a person does \
takes as long as a person takes to do it; automatic steps are quick.  Use \
"now" for "after" only when the event genuinely begins the moment its \
cause happens.

Because a person is occupied for "lasts", a sequence of things somebody \
does one after another cannot overlap -- and you do not need to arrange \
that, the machinery does it.  Say how long each thing really takes and \
the order looks after itself.

IF NOTHING CONCRETE CHANGES, RETURN "event": null.  Never emit an event \
that merely restates that something is still sitting there, still unread, \
still waiting, or that someone is still busy -- that is not an event, it \
is the absence of one.  Say it in "judgment" and schedule a wake for when \
the situation might genuinely differ.

Reply with ONLY a JSON object:
{
  "judgment": "one or two sentences grounded in the current situation",
  "event": {
    "description": "the single immediate concrete event, in plain language",
    "for": ["actor_id"],
    "observed": false,
    "after": "43 seconds",
    "lasts": "20 minutes",
    "by": "actor_id"
  },
  "wakes": [
    {"actor": "actor_id", "after": "2 hours",
     "reason": "why this person's situation should be revisited then"}
  ]
}
"after" is when it STARTS, measured from now.  "lasts" is how long it \
OCCUPIES the person doing it -- a phone call lasts as long as the call, \
signing a form lasts a minute, a message takes a moment to write.  It is \
not decoration: that person can do nothing else until it is over, and if \
you say a call lasts twenty minutes then nothing else of theirs happens \
for twenty minutes.  "0 seconds" is right only for something instant.
"by" is WHOSE action this is: the actor id of the person who did it, or null when the environment or somebody outside this situation did it.  It must be the person whose attempt you were asked about; if what would happen next is a DIFFERENT person choosing something, stop and return "event": null, because that choice is theirs to make and they will be asked.
"event" may be null when nothing concrete happens yet.
"wakes" may be empty.
"for" lists the actor ids the event or its information becomes AVAILABLE \
to -- which is usually the person it is heading TOWARDS, not the person \
who set it in motion.  If something is travelling to someone, the next \
step is it arriving where THEY could encounter it, listed for them with \
"observed": false.  "observed" is true only if EVERY listed actor has \
actually observed it already; if some have and some have not, emit the \
event for one group now and let the rest be judged separately later.
When you are shown items that are available to someone but not yet \
observed, decide what concretely becomes of them next: they may move \
further along, they may reach that person's attention, or they may simply \
sit there untouched while that person deals with other things.  Any of \
those is a legitimate answer; say which one actually happens.
"after" is how much simulated time passes before this event occurs: "now", \
"43 seconds", "5 minutes", "2 hours", or "3 days".
Every one of the six event fields is required.  Use exactly the actor ids \
given to you.  Do not add any other fields."""


def world_user_prompt(*, now: str, shared_context: str, journal_text: str,
                      actor_ids: list, trigger_kind: str, trigger_text: str,
                      actor_id: str | None = None,
                      actor_private: str | None = None,
                      available_unobserved: list | None = None) -> str:
    """Code writes every heading; model-written text is contained inside
    the single line code gives it (``journal_text`` is already rendered
    line by line by the journal itself)."""
    parts = [f"CURRENT TIME\n{now}", "",
             f"BACKGROUND (true for this situation)\n"
             f"{contained(shared_context)}", "",
             f"ACTOR IDS YOU MAY USE\n{', '.join(actor_ids)}", "",
             f"WHAT HAS CONCRETELY HAPPENED SO FAR\n{journal_text}", ""]
    if actor_id:
        parts += [f"THE PERSON THIS CONCERNS\n{actor_id}"
                  + (f"\ntheir circumstances (background for your judgment "
                     f"only, never to be repeated in an event): "
                     f"{contained(actor_private)}"
                     if actor_private else ""), ""]
    if available_unobserved:
        parts.append("ITEMS AVAILABLE TO THEM THAT THEY HAVE NOT YET "
                     "OBSERVED")
        for e in available_unobserved:
            parts.append(f"- [{e['t']}] ({e['event_id']}) "
                         f"{contained(e['description'])}")
        parts.append("")
    parts += [f"THE TRIGGER YOU MUST JUDGE ({trigger_kind})\n"
              f"{contained(trigger_text)}",
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
    try:
        judgment = clean_text(obj["judgment"].strip(), field="judgment")
    except EnvelopeError as e:
        raise WorldResponseError(str(e)) from None
    return {"judgment": judgment,
            "event": obj.get("event"),
            "wakes": obj.get("wakes") or []}


def make_world_validator(known_actor_ids, *, already_committed=()):
    """The whole response, checked in one place, before the caller returns.

    Envelope and wake validation live INSIDE the validated call so that an
    unusable event gets exactly the same single retry as unparseable JSON,
    instead of ending the run.  The checked forms are returned alongside
    the raw ones (raw for the trace, checked for the runtime); both are
    JSON-safe, so the durations stay as their original text and code
    re-parses them at the moment it schedules.
    """

    def validate(obj) -> dict:
        parsed = validate_world_response(obj)
        env = (validate_event(parsed["event"], known_actor_ids)
               if parsed["event"] is not None else None)
        duplicate = None
        same = None
        if env is not None:
            # Same act = same doer, same audience, same thing said.  The
            # first two are code-owned identity and do the discriminating;
            # only then does wording get a vote.  Comparing text alone had
            # to be set so tight that it missed a call made four times and
            # a banking app checked five, because loosening it merged
            # "Dana asks Marcus to confirm" with "Marcus replies
            # confirming" -- two different people, one of them the
            # decisive act of the scene.
            # ... and RECENTLY.  Doing the same thing again days later is
            # not a repeat, it is doing it again -- chasing, ringing back,
            # asking a second time.  With no time bound this rule deleted
            # exactly that, cancelling out the reviewer change that had
            # just stopped a reviewer refusing it.  The caller supplies
            # which of the record is near enough to still be the same act.
            here = (env.get("by"), tuple(env["for"]),
                    contained(env["description"]))
            same = next((d for d in already_committed
                         if d[0] == here[0] and d[1] == here[1]
                         and says_the_same_thing(here[2], d[2])), None)
        if same is not None:
            # Word for word, this has already happened.  One live run
            # committed "she reads the next portion of the results
            # section" nine times, and the week that produced its NO was
            # a loop.  The same thing cannot occur twice, so nothing
            # occurs: the judgment and the wakes stand, the event does
            # not.  Refusing the whole answer would kill the run over it.
            duplicate, env = env["description"], None
        wakes = validate_wakes(parsed["wakes"], known_actor_ids)
        parsed["event_checked"] = (
            None if env is None
            else {k: env[k] for k in ("description", "for", "observed",
                                      "after", "lasts", "by")})
        parsed["wakes_checked"] = [{"actor": w["actor"], "after": w["after"],
                                    "reason": w["reason"]} for w in wakes]
        parsed["duplicate_dropped"] = duplicate
        return parsed

    return validate
