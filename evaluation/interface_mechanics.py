"""How much of a run is people, and how much is machinery.

An event is "interface mechanics" when what it records is a device or a
channel doing its job rather than a person doing something: a message
travelling between servers, a notification appearing, an app loading, a
screen lighting up.  Those things are real, but a world made mostly of
them is a world about software rather than about people.

This is a MEASUREMENT, not a control.  Nothing in the runtime reads it,
no prompt is told about it, and no behaviour is weighted by it.  It exists
so that a claim about how human a trajectory looks can be checked instead
of asserted.
"""
from __future__ import annotations

import json
import os
import re

#: A device or channel is the one acting.  Matched on the SUBJECT, not on
#: whether a device is mentioned anywhere -- an earlier version keyed on a
#: phrase list and counted essentially one preposition, reporting 7% where
#: an independent classification by subject found 43%.  A measure that
#: licenses the claim it was built to test is worse than no measure.
DEVICE = (r"(?:the |a |an |his |her |their |[A-Z][a-z]+'s )?"
          r"(?:e?mail|message|text|reply|email|letter|document|file|"
          r"pdf|attachment|notification|banner|alert|app|application|"
          r"screen|page|inbox|phone|laptop|computer|printer|scanner|"
          r"terminal|system|network|server|client|chat|thread|call)s?")

#: The device doing something on its own.
SUBJECT_IS_A_DEVICE = re.compile(
    DEVICE + r"[^.]{0,60}?\b(?:"
    r"arrives?|arrived|lands?|is deliver|are deliver|was deliver|"
    r"travels?|is sent|are sent|is transmitted|is routed|is relayed|"
    r"is queued|reaches|appears?|pops? up|buzzes|rings?|vibrates?|"
    r"lights? up|displays?|shows?|loads?|opens? on|refreshes?|syncs?|"
    r"downloads?|uploads?|prints?|scans?|saves?|finishes? print|"
    r"finishes? scan|becomes? visible|is (?:now )?visible|"
    r"is (?:now )?available|remains? unread|sits? unread|stays? unread"
    r")\b", re.I)

#: A restatement that nothing has changed.  Not an event: the absence of
#: one, which the world prompt and the event review both forbid by name.
NO_CHANGE = re.compile(
    r"\b(?:remains?|stays?|sits?|is still|are still|continues? to (?:sit|"
    r"wait|remain)|has not (?:yet )?(?:been )?(?:noticed|seen|read|opened|"
    r"acted)|does not notice|did not notice|without (?:opening|noticing|"
    r"reading)|still (?:unread|unseen|unopened|waiting|sitting))\b",
    re.I)


def is_mechanics(description: str) -> bool:
    """A device acting on its own, or a statement that nothing changed."""
    d = description or ""
    return bool(SUBJECT_IS_A_DEVICE.search(d) or NO_CHANGE.search(d))


def measure(run_dir: str) -> dict:
    events = [json.loads(l) for l in
              open(os.path.join(run_dir, "journal.jsonl"), encoding="utf-8")
              if l.strip()]
    mech = [e for e in events if is_mechanics(e["description"])]
    return {"run": os.path.basename(run_dir.rstrip("/")),
            "events": len(events),
            "mechanics": len(mech),
            "share": round(len(mech) / len(events), 3) if events else 0.0,
            "examples": [e["description"][:100] for e in mech[:3]]}


if __name__ == "__main__":
    import sys
    total = mech = 0
    for d in sorted(sys.argv[1:]):
        if not os.path.exists(os.path.join(d, "journal.jsonl")):
            continue
        m = measure(d)
        total += m["events"]
        mech += m["mechanics"]
        print(f"{m['run']:<28} {m['mechanics']:>3}/{m['events']:<3} "
              f"{m['share']:.0%}")
    if total:
        print(f"{'TOTAL':<28} {mech:>3}/{total:<3} {mech / total:.0%}")
