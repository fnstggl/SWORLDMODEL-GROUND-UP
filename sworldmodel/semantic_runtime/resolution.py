"""The read-only terminal judge.

This is the ONLY role that ever sees the compiled resolution.  It reads
committed journal events and the current time, and returns a status with
the event ids that support it.  It cannot create, modify or delete
anything: the runtime passes it plain copies and commits nothing from its
answer except the check record itself.

Code enforces what the judge may conclude:
- YES must cite at least one committed event, and every cited id must
  exist;
- intentions, private memories and world judgments can never satisfy YES,
  because only committed journal events are ever shown to it;
- NO_AT_CUTOFF cannot be returned before the cutoff instant;
- UNRESOLVED cannot be returned AT the cutoff: the horizon is where a
  question stops being open, so the final judgment is YES or NO;
- the terminal is false at initialization unless the compiled scene
  already describes a resolved question.

All of that lives in ``make_validator`` below, in code.  The provider is
asked only for a JSON object; the required fields, the fixed status
vocabulary and the rejection of every additional property are enforced
here, on the response, before any terminal record is written.
"""
from __future__ import annotations

from datetime import datetime

from .envelope import EnvelopeError, clean_text, contained

STATUSES = ("YES", "UNRESOLVED", "NO_AT_CUTOFF")

JUDGE_SYSTEM = """You are a strict, read-only outcome judge.  You are given \
a resolution condition, the current time, and the complete list of events \
that have actually been committed as having occurred.  You decide only \
whether the committed events satisfy the resolution.

Rules:
- Judge ONLY from the committed events shown.  Something someone intended, \
planned, believed, or was likely to do does NOT count.  If the required \
thing has not concretely occurred in the list, it has not happened.
- Each event states who it reached and whether that person actually \
observed it.  Something that merely arrived where someone COULD see it has \
not been seen by them; if the resolution requires a person to know, \
notice, read or learn something, only an event they actually observed can \
satisfy it.
- Answer "YES" only when committed events satisfy the resolution, and cite \
the exact event ids that show it.
- Answer "UNRESOLVED" when the required events have not (yet) occurred and \
the deadline has not passed.
- Answer "NO_AT_CUTOFF" only when the deadline stated in the resolution has \
actually passed without the required events occurring.
- You may not invent, modify or infer events.

Reply with ONLY a JSON object:
{"status": "YES" | "UNRESOLVED" | "NO_AT_CUTOFF",
 "supporting_event_ids": ["e12"],
 "explanation": "one sentence citing the committed events"}"""


class ResolutionError(ValueError):
    pass


def judge_user_prompt(resolution: str, now: str, events: list, *,
                      final: bool = False) -> str:
    lines = [f"CURRENT TIME\n{now}", "",
             f"THE RESOLUTION CONDITION\n{resolution}", ""]
    if final:
        lines += ["THIS IS THE FINAL JUDGMENT: THE DEADLINE HAS BEEN "
                  "REACHED.",
                  "\"UNRESOLVED\" is not available now.  Either the "
                  "committed events below satisfy the resolution, which is "
                  "\"YES\", or the deadline has arrived without them, which "
                  "is \"NO_AT_CUTOFF\".", ""]
    lines += ["COMMITTED EVENTS (the complete record of what has actually "
              "occurred)"]
    if events:
        for e in events:
            who = ", ".join(e.get("for") or []) or "no one"
            by = e.get("observed_by") or []
            seen = ("observed by " + ", ".join(by) if by
                    else f"reached {who} but NOT observed by anyone")
            lines.append(f"- {e['event_id']} [{e['t']}] "
                         f"{contained(e['description'])} | {seen}")
    else:
        lines.append("- (nothing has been committed yet)")
    lines += ["", "Judge the resolution now.  Reply with ONLY the JSON "
                  "object."]
    return "\n".join(lines)


def make_validator(known_event_ids, now: datetime, cutoff: datetime, *,
                   final: bool = False):
    """Code-side enforcement of what the judge is permitted to conclude."""

    def validate(obj) -> dict:
        if not isinstance(obj, dict):
            raise ResolutionError("judge response must be an object")
        unknown = set(obj) - {"status", "supporting_event_ids", "explanation"}
        if unknown:
            raise ResolutionError(f"unexpected fields {sorted(unknown)}")
        status = obj.get("status")
        if status not in STATUSES:
            raise ResolutionError(f"status must be one of {list(STATUSES)}")
        ids = obj.get("supporting_event_ids") or []
        if not isinstance(ids, list) or any(not isinstance(i, str)
                                            for i in ids):
            raise ResolutionError("supporting_event_ids must be a string array")
        if not isinstance(obj.get("explanation"), str) \
                or not obj["explanation"].strip():
            raise ResolutionError("explanation must be a non-empty string")
        for i in ids:
            if i not in known_event_ids:
                raise ResolutionError(
                    f"cited event {i!r} does not exist in the committed "
                    f"journal")
        if status == "YES" and not ids:
            raise ResolutionError(
                "YES must cite at least one committed event that produced it")
        if status == "NO_AT_CUTOFF" and now < cutoff:
            raise ResolutionError(
                f"NO_AT_CUTOFF is not permitted before the cutoff "
                f"({now.isoformat()} < {cutoff.isoformat()})")
        if final and status == "UNRESOLVED":
            raise ResolutionError(
                "this is the judgment AT the cutoff: the question is "
                "either satisfied by committed events (YES) or it is not "
                "(NO_AT_CUTOFF); UNRESOLVED is not available")
        try:
            explanation = clean_text(obj["explanation"].strip(),
                                     field="explanation")
        except EnvelopeError as e:
            raise ResolutionError(str(e)) from None
        return {"status": status, "supporting_event_ids": list(ids),
                "explanation": explanation}

    return validate
