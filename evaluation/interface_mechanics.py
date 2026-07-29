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

#: Phrases that describe a channel or a device acting on its own.  Kept
#: deliberately narrow: a person sending, reading, opening or replying is
#: NOT machinery, even though a device is involved.
MECHANISM = re.compile(
    r"\b("
    r"arrives? in|arrived in|lands? in|delivered to|"
    r"travels? (?:to|from|through)|is (?:sent|transmitted|routed|relayed)"
    r" (?:from|to|through|via) [^.]*server|"
    r"email server|mail server|through the network|"
    r"notification (?:appears?|is (?:displayed|shown|generated|pushed))|"
    r"push notification|badge|"
    r"(?:app|application|screen|page|inbox|client|interface) (?:loads?|"
    r"opens?|refreshes?|displays?|shows?|syncs?)|"
    r"appears? (?:in|on) (?:the |their |his |her )?"
    r"(?:inbox|screen|feed|chat|thread|timeline)|"
    r"is (?:now )?(?:visible|available) (?:in|on|to)|"
    r"marked as (?:read|delivered|unread)|"
    r"(?:message|email|text) (?:is )?queued"
    r")\b", re.I)


def is_mechanics(description: str) -> bool:
    return bool(MECHANISM.search(description or ""))


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
