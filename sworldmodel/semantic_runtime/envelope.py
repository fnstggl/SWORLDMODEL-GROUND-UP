"""The smallest possible LLM event envelope, and its validation.

An LLM may propose at most one immediate event per world judgment, using
exactly four fields:

    {"description": "...", "for": ["actor_id"], "observed": true,
     "after": "2 hours", "follow_up": false}

description  what concretely happened
for          which actors the resulting information or event is available to
observed     whether EVERY actor in "for" has actually observed it
after        how much simulated time passes before this event occurs
follow_up    whether this leaves ONE unresolved environmental consequence
             that should be worked out next -- a thing in transit has one,
             a thing that is finished does not.  Code used to guess this
             from the shape of the event and guessed wrong in both
             directions: it asked "and then?" about someone putting their
             phone down, and stopped asking about a message still on its
             way.

Code adds event_id, exact timestamp, source, caused_by, trajectory_id and
model-call provenance; the LLM never writes those.  Mixed observation
states are impossible by construction -- different states require separate
world adjudications, which is what keeps availability and observation
genuinely distinct.

The duration grammar is universal time bookkeeping ("now", "43 seconds",
"5 minutes", "2 hours", "3 days"), never a social-action vocabulary.

The shape is enforced HERE, in code, not by the provider: the transport
asks only for a JSON object, so ``validate_event`` is the single place
that requires the four fields, fixes their types, rejects every additional
property, and rejects unknown actor ids.  Nothing reaches the ledger that
did not pass through it.
"""
from __future__ import annotations

import re
from datetime import timedelta

#: Bound on wakes proposed in one judgment.  Like the intention cap, this
#: is a budget boundary: every wake becomes a scheduled step, so an
#: unbounded list would let the model decide how long the runtime runs.
MAX_WAKES_PER_JUDGMENT = 4


#: A sentence or two.  Every model-written string is one, and a ceiling on
#: them is the only thing standing between a merely verbose model and an
#: unbounded run: the call budget counts calls, not characters.
MAX_TEXT_CHARS = 2000


def clean_text(text: str, *, field: str) -> str:
    """A model-written string, made storable.

    Text that cannot be encoded (a lone surrogate, say) is not a strange
    edge case: it passes every "is this a non-empty string" check, then
    destroys the artifact write at the end of a completed run.  It is
    repaired here, at the validation boundary, before anything is
    committed -- along with control characters, which belong to no
    sentence anyone wrote.
    """
    if len(text) > MAX_TEXT_CHARS:
        raise EnvelopeError(
            f"{field} is {len(text)} characters; at most {MAX_TEXT_CHARS} "
            f"are accepted -- say it in a sentence or two")
    repaired = text.encode("utf-8", "replace").decode("utf-8")
    return "".join(c for c in repaired if c >= " " or c in "\t\n")


def contained(text) -> str:
    """Model-written text, made safe to place inside a code-owned prompt.

    Every prompt this runtime builds is a sequence of code-owned ALL-CAPS
    section headings with data underneath, and model-written strings are
    data.  Flattening all whitespace guarantees such a string can never
    begin a line it does not begin: it cannot open a forged section, forge
    an entry in another section, or split itself across the structure.
    """
    s = "" if text is None else str(text)
    return " ".join(s.split()) or "(empty)"


_UNITS = {"second": 1, "seconds": 1, "sec": 1, "secs": 1,
          "minute": 60, "minutes": 60, "min": 60, "mins": 60,
          "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
          "day": 86400, "days": 86400,
          "week": 604800, "weeks": 604800}
#: one "<number> <unit>" part; a duration is one or more of them, because
#: people (and models) write "1 hour 30 minutes" as naturally as "90
#: minutes" and both mean the same amount of time
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)\s*([a-z]+)")
#: what may sit BETWEEN parts.  A minus sign is deliberately not one of
#: them: time in this runtime only ever moves forward, so "-5 minutes" is
#: a rejection rather than five minutes.
_SEPARATORS = ("and", "&", "+")

#: Bound on a single proposed step: a jump larger than this is a narration
#: of the far future rather than an immediate consequence.
MAX_STEP_DAYS = 30


class EnvelopeError(ValueError):
    """A proposed event or duration is not usable; nothing may be committed."""


def parse_duration(text: str) -> timedelta:
    """'now' | one or more '<number> <unit>' parts -> timedelta.

    Anything else raises.  This is time bookkeeping and nothing else: it
    understands amounts of time, never what the time is for.
    """
    if not isinstance(text, str):
        raise EnvelopeError(f"duration must be a string, got {type(text).__name__}")
    s = text.strip().lower()
    if s in ("now", "immediately", "0", "none"):
        return timedelta(0)
    parts = _DURATION_PART.findall(s)
    leftover = [t for t in re.split(r"[\s,]+", _DURATION_PART.sub(" ", s)) if t]
    if not parts or any(t not in _SEPARATORS for t in leftover):
        raise EnvelopeError(
            f"unparseable duration {text!r}: use 'now', '<number> "
            f"<seconds|minutes|hours|days>', or several such parts such as "
            f"'1 hour 30 minutes'")
    seconds = 0.0
    for value, unit in parts:
        if unit not in _UNITS:
            raise EnvelopeError(
                f"unknown time unit {unit!r} in {text!r}: use seconds, "
                f"minutes, hours or days")
        seconds += float(value) * _UNITS[unit]
    try:
        delta = timedelta(seconds=seconds)
    except OverflowError:
        raise EnvelopeError(
            f"duration {text!r} is not an amount of time anything could "
            f"take") from None
    if delta > timedelta(days=MAX_STEP_DAYS):
        raise EnvelopeError(
            f"duration {text!r} exceeds the {MAX_STEP_DAYS}-day single-step "
            f"bound: an immediate consequence may not jump the far future")
    return delta


def validate_event(proposed, known_actor_ids) -> dict:
    """Structural + identity validation of a proposed event envelope.
    Returns the cleaned envelope; raises EnvelopeError (committing
    nothing) on any problem."""
    if not isinstance(proposed, dict):
        raise EnvelopeError("event must be an object")
    unknown = set(proposed) - {"description", "for", "observed", "after",
                               "by", "lasts"}
    if unknown:
        raise EnvelopeError(
            f"event has fields the model may not write: {sorted(unknown)} "
            f"(event_id, time, cause and provenance are code-owned)")
    for f in ("description", "for", "observed", "after"):
        if f not in proposed:
            raise EnvelopeError(f"event is missing required field {f!r}")
    if not isinstance(proposed["description"], str) \
            or not proposed["description"].strip():
        raise EnvelopeError("event.description must be a non-empty string")
    if not isinstance(proposed["observed"], bool):
        raise EnvelopeError("event.observed must be true or false")
    # WHOSE action this is, if it is anybody's.  Null means the
    # environment did it -- a train is late, a shop closes, something
    # arrives.  An actor id means that person acted, and code checks that
    # against whose attempt was being adjudicated: the world resolving
    # Ada's attempt may not decide that BO chose something, because that
    # is Bo's turn to take.  Identity, not keywords.
    # HOW LONG IT TAKES, not just when it starts.  Without this an event
    # is a point, a person is never busy, and 65% of a corpus happened at
    # the same instant as its cause: durations were decorative, so they
    # were not answered.  Code makes it load-bearing -- the actor is
    # occupied for this long -- which is the only reason to get it right.
    lasts = proposed.get("lasts", "0 seconds")
    if not isinstance(lasts, str) or not lasts.strip():
        raise EnvelopeError("event.lasts must be a duration like "
                            "\"20 minutes\"")
    try:
        span = parse_duration(lasts)
    except EnvelopeError:
        raise
    if span.total_seconds() < 0:
        raise EnvelopeError("event.lasts cannot be negative")

    by = proposed.get("by")
    if by is not None:
        if not isinstance(by, str):
            raise EnvelopeError("event.by must be an actor id or null")
        by = by.strip()
        if by not in known_actor_ids:
            raise EnvelopeError(
                f"event.by names {by!r}, who is not in this situation")
    audience = proposed["for"]
    if not isinstance(audience, list) \
            or any(not isinstance(a, str) for a in audience):
        raise EnvelopeError("event.for must be an array of actor ids")
    clean_for = []
    for a in audience:
        aid = a.strip()
        if aid not in known_actor_ids:
            raise EnvelopeError(
                f"event.for names an unknown actor {a!r}; known actors are "
                f"{sorted(known_actor_ids)}")
        if aid not in clean_for:
            clean_for.append(aid)
    delta = parse_duration(proposed["after"])
    return {"description": clean_text(proposed["description"].strip(),
                                      field="event.description"),
            "for": clean_for, "observed": proposed["observed"],
            "after": proposed["after"].strip(),
            "lasts": lasts.strip(), "span": span,
            "by": by, "delta": delta}


def validate_wakes(proposed, known_actor_ids) -> list:
    """Wakes are reconsideration triggers, never events.

    A wake carries TIME ONLY.  Its ``reason`` is recorded for tracing and
    is shown to no one: anything a person is entitled to know has to be an
    event they observed, which is why this channel cannot be used to tell
    an actor anything.
    """
    if proposed is None:
        return []
    if not isinstance(proposed, list):
        raise EnvelopeError("wakes must be an array")
    if len(proposed) > MAX_WAKES_PER_JUDGMENT:
        raise EnvelopeError(
            f"{len(proposed)} wakes proposed; at most "
            f"{MAX_WAKES_PER_JUDGMENT} are accepted in one judgment")
    out = []
    for i, w in enumerate(proposed):
        if not isinstance(w, dict):
            raise EnvelopeError(f"wakes[{i}] must be an object")
        unknown = set(w) - {"actor", "after", "reason"}
        if unknown:
            raise EnvelopeError(f"wakes[{i}] has unexpected fields "
                                f"{sorted(unknown)}")
        actor = str(w.get("actor", "")).strip()
        if actor not in known_actor_ids:
            raise EnvelopeError(
                f"wakes[{i}].actor is unknown: {w.get('actor')!r}")
        if not str(w.get("reason", "")).strip():
            raise EnvelopeError(f"wakes[{i}].reason must be non-empty")
        out.append({"actor": actor, "delta": parse_duration(w.get("after", "")),
                    "after": str(w.get("after")).strip(),
                    "reason": clean_text(str(w["reason"]).strip(),
                                         field=f"wakes[{i}].reason")})
    return out
