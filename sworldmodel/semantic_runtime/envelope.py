"""The smallest possible LLM event envelope, and its validation.

An LLM may propose at most one immediate event per world judgment, using
exactly four fields:

    {"description": "...", "for": ["actor_id"], "observed": true,
     "after": "2 hours"}

description  what concretely happened
for          which actors the resulting information or event is available to
observed     whether EVERY actor in "for" has actually observed it
after        how much simulated time passes before this event occurs

Code adds event_id, exact timestamp, source, caused_by, trajectory_id and
model-call provenance; the LLM never writes those.  Mixed observation
states are impossible by construction -- different states require separate
world adjudications, which is what keeps availability and observation
genuinely distinct.

The duration grammar is universal time bookkeeping ("now", "43 seconds",
"5 minutes", "2 hours", "3 days"), never a social-action vocabulary.
"""
from __future__ import annotations

import re
from datetime import timedelta

#: Provider-native strict schema for a proposed event.
EVENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["description", "for", "observed", "after"],
    "properties": {
        "description": {"type": "string", "minLength": 1},
        "for": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "observed": {"type": "boolean"},
        "after": {"type": "string", "minLength": 1},
    },
}

_UNITS = {"second": 1, "seconds": 1, "sec": 1, "secs": 1,
          "minute": 60, "minutes": 60, "min": 60, "mins": 60,
          "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
          "day": 86400, "days": 86400}
_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-z]+)\s*$", re.I)

#: Bound on a single proposed step: a jump larger than this is a narration
#: of the far future rather than an immediate consequence.
MAX_STEP_DAYS = 30


class EnvelopeError(ValueError):
    """A proposed event or duration is not usable; nothing may be committed."""


def parse_duration(text: str) -> timedelta:
    """'now' | '<number> <unit>' -> timedelta.  Anything else raises."""
    if not isinstance(text, str):
        raise EnvelopeError(f"duration must be a string, got {type(text).__name__}")
    s = text.strip().lower()
    if s in ("now", "immediately", "0", "none"):
        return timedelta(0)
    m = _DURATION_RE.match(s)
    if not m:
        raise EnvelopeError(
            f"unparseable duration {text!r}: use 'now' or '<number> "
            f"<seconds|minutes|hours|days>'")
    value, unit = float(m.group(1)), m.group(2)
    if unit not in _UNITS:
        raise EnvelopeError(
            f"unknown time unit {unit!r} in {text!r}: use seconds, minutes, "
            f"hours or days")
    delta = timedelta(seconds=value * _UNITS[unit])
    if delta > timedelta(days=MAX_STEP_DAYS):
        raise EnvelopeError(
            f"duration {text!r} exceeds the {MAX_STEP_DAYS}-day single-step "
            f"bound: an immediate consequence may not jump the far future")
    if delta < timedelta(0):
        raise EnvelopeError(f"negative duration {text!r}")
    return delta


def validate_event(proposed, known_actor_ids) -> dict:
    """Structural + identity validation of a proposed event envelope.
    Returns the cleaned envelope; raises EnvelopeError (committing
    nothing) on any problem."""
    if not isinstance(proposed, dict):
        raise EnvelopeError("event must be an object")
    unknown = set(proposed) - {"description", "for", "observed", "after"}
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
    return {"description": proposed["description"].strip(),
            "for": clean_for, "observed": proposed["observed"],
            "after": proposed["after"].strip(), "delta": delta}


def validate_wakes(proposed, known_actor_ids) -> list:
    """Wakes are reconsideration triggers, never events."""
    if proposed is None:
        return []
    if not isinstance(proposed, list):
        raise EnvelopeError("wakes must be an array")
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
                    "reason": str(w["reason"]).strip()})
    return out
