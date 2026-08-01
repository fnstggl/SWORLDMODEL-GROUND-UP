"""How much of a run is people, and how much is machinery.

Three different questions, reported separately because conflating them is
how two readings of the same corpus came out at 14% and 44%.

**Who acted.**  Exact, and the only one that is: every committed event
carries ``by``, so the split between "a person in this situation did
this" and "nobody here did" is read off the record rather than guessed
from prose.

**A device or channel acting on its own** -- a message travelling between
servers, a notification appearing, an app loading, a screen lighting up.
Real things, but a world made mostly of them is a world about software.
Matched on the SUBJECT of the sentence: an earlier version keyed on a
phrase list and counted essentially one preposition.

**Noticing** -- an event whose whole content is somebody becoming aware.
A person opening their inbox IS a person doing something, so it is not
machinery; but a run in which half the events are people checking their
phones is a run about attention rather than about a situation.  This is
the category the 44% hand-count was counting and the 14% script was not.

The last two are text heuristics and are LOWER BOUNDS: they catch what
they match and nothing else.  Only the first is exact.

All of this is MEASUREMENT, not control.  Nothing in the runtime reads
it, no prompt is told about it, no behaviour is weighted by it.  It
exists so a claim about how human a trajectory looks can be checked
instead of asserted.
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
    r"is (?:now )?available|remains? unread|sits? unread|stays? unread|"
    r"is (?:now )?posted|is (?:now )?showing|goes through|is (?:now )?live"
    r")\b", re.I)

#: An event whose whole content is somebody becoming aware of something.
#: A real human act, and not machinery -- but counted, because a run made
#: of these is a run about checking phones.
NOTICING = re.compile(
    r"\b(?:sees?|saw|notices?|noticed|reads?(?! (?:out|aloud))|spots?|"
    r"checks?|checked|glances?|looks? at|opens? (?:the |her |his |their )?"
    r"(?:inbox|email|e-mail|phone|app|message|chat|thread|notification)|"
    r"picks? up (?:her|his|their) phone|hears?|listens?)\b", re.I)

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


def is_noticing(description: str) -> bool:
    """The whole content is somebody becoming aware of something."""
    return bool(NOTICING.search(description or ""))


def measure(run_dir: str) -> dict:
    events = [json.loads(l) for l in
              open(os.path.join(run_dir, "journal.jsonl"), encoding="utf-8")
              if l.strip()]
    mech = [e for e in events if is_mechanics(e["description"])]
    noticing = [e for e in events if is_noticing(e["description"])]
    # exact, off the record: `by` is null when nobody in this situation
    # did it -- the environment, an outside party, or the scene's own
    # premise.  Older runs predate the field and report None.
    has_by = [e for e in events if "by" in e]
    authored = [e for e in has_by if e.get("by")]

    def share(n):
        return round(n / len(events), 3) if events else 0.0
    return {"run": os.path.basename(run_dir.rstrip("/")),
            "events": len(events),
            "mechanics": len(mech), "mechanics_share": share(len(mech)),
            "noticing": len(noticing), "noticing_share": share(len(noticing)),
            "authored_by_an_actor": len(authored) if has_by else None,
            "authored_share": share(len(authored)) if has_by else None,
            "examples": [e["description"][:100] for e in mech[:3]]}


if __name__ == "__main__":
    import sys
    total = mech = notice = authored = with_by = 0
    print(f"{'run':<28} {'device':>10} {'noticing':>10} {'a person':>10}")
    for d in sorted(sys.argv[1:]):
        if not os.path.exists(os.path.join(d, "journal.jsonl")):
            continue
        m = measure(d)
        total += m["events"]
        mech += m["mechanics"]
        notice += m["noticing"]
        if m["authored_by_an_actor"] is not None:
            authored += m["authored_by_an_actor"]
            with_by += m["events"]
        auth = ("-" if m["authored_share"] is None
                else f"{m['authored_share']:.0%}")
        print(f"{m['run']:<28} {m['mechanics']:>3}/{m['events']:<3} "
              f"{m['mechanics_share']:>4.0%} {m['noticing_share']:>9.0%} "
              f"{auth:>10}")
    if total:
        auth = f"{authored / with_by:.0%}" if with_by else "-"
        print(f"{'TOTAL':<28} {mech:>3}/{total:<3} {mech / total:>4.0%} "
              f"{notice / total:>9.0%} {auth:>10}")
