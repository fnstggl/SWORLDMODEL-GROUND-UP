"""Shallow deterministic backup guards for two defect classes.

Both guards are BACKUPS: the independent reviewer (Call 2) is the primary
detector because only it can read paraphrase, tense, and complex natural
language.  Code here handles only the unambiguous, mechanically decidable
cases, and stays deliberately conservative so a legitimate scene is never
blocked by a heuristic.

1. PREWRITTEN OUTCOME -- a starting event that already satisfies the YES
   condition.  Detected by near-identical content wording between a
   starting event and a clause of the resolution.  Full coverage of every
   resolution clause is an error (the simulation would have nothing left
   to determine); partial coverage is a warning that Call 2 adjudicates,
   since a partially-satisfying event is legitimate exactly when the
   question says it already happened -- a judgement code cannot make.

2. QUESTION WINDOW -- the compile cutoff bounds how long the runtime may
   run; it must never silently replace a narrower deadline stated by the
   question.  Only unambiguous forms are parsed ("within N days/weeks/
   hours", "before/by <date>"); anything subtler is Call 2's job.

No scenario vocabulary appears here: the guards operate on generic word
overlap and time arithmetic.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# 1. prewritten-outcome guard
# ---------------------------------------------------------------------------

#: Function words carry no evidence of WHICH event is described.
_STOP = frozenset("""
a an the of to in on at by for with from into over under and or but if that
this these those it its is are was were be been being will would shall
should may might can could do does did have has had not no nor than then
there their them they he she his her him you your we our us as so such any
all each both about after before during within least most more less very
just only also more per via
""".split())

#: Boilerplate that appears in nearly every resolution and would otherwise
#: inflate similarity between unrelated scenes.
_RES_BOILERPLATE = re.compile(
    r"resolve[sd]?\s+(?:yes|no)|otherwise|persistent event history|"
    r"event history|history shows?|shows? that|at the cutoff|"
    r"before the cutoff|hard cutoff|the simulation|only if|"
    r"as recorded in|according to", re.I)

_CLAUSE_SPLIT = re.compile(r"\s+and\s+|\s+as well as\s+|;|\bplus\b", re.I)


def content_words(text: str) -> set:
    """Lowercase content words with light suffix stripping."""
    out = set()
    for w in re.findall(r"[a-z0-9]+", str(text).lower()):
        if w in _STOP or len(w) <= 2:
            continue
        for suf in ("ing", "ied", "ed", "es", "s"):
            if len(w) > 4 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.add(w)
    return out


def resolution_clauses(resolution: str) -> list:
    """The resolution's required parts, boilerplate removed."""
    body = _RES_BOILERPLATE.sub(" ", resolution)
    parts = [p.strip(" ,.;:") for p in _CLAUSE_SPLIT.split(body)]
    clauses = [(p, content_words(p)) for p in parts if len(content_words(p)) >= 2]
    if not clauses:
        w = content_words(body)
        clauses = [(body.strip(), w)] if w else []
    return clauses


def _covers(event_words: set, clause_words: set) -> bool:
    """Does this event say the same thing as this clause?  Requires the
    clause to be almost entirely accounted for by the event AND the event
    to be mostly about the clause (so a broad event does not 'cover'
    everything by accident)."""
    if not event_words or not clause_words:
        return False
    coverage = len(event_words & clause_words) / len(clause_words)
    precision = len(event_words & clause_words) / len(event_words)
    return coverage >= 0.8 and precision >= 0.6


def prewritten_outcome_findings(events: list, resolution: str) -> tuple:
    """-> (errors, warnings).  Near-identical wording only; Call 2 owns
    paraphrase and the already-happened judgement."""
    clauses = resolution_clauses(resolution)
    if not clauses:
        return [], []
    matched: dict = {}
    for i, e in enumerate(events):
        ew = content_words(e["description"])
        for ci, (ctext, cw) in enumerate(clauses):
            if _covers(ew, cw):
                matched.setdefault(ci, []).append((i, ctext))
    if not matched:
        return [], []
    if len(matched) == len(clauses):
        idxs = sorted({i for hits in matched.values() for i, _ in hits})
        return ([f"starting_events{idxs} already state the entire YES "
                 f"condition in near-identical wording: the outcome would be "
                 f"complete at genesis and the simulation would determine "
                 f"nothing"], [])
    warns = []
    for ci, hits in sorted(matched.items()):
        for i, ctext in hits:
            warns.append(
                f"starting_events[{i}] closely matches part of the "
                f"resolution ({ctext[:70]!r}): legitimate ONLY if the "
                f"question states this already happened before the start "
                f"-- flagged for review")
    return [], warns


# ---------------------------------------------------------------------------
# 2. question-window guard
# ---------------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
_NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
             "twelve": 12, "fourteen": 14, "twenty": 20, "twenty-four": 24,
             "thirty": 30, "forty-eight": 48, "sixty": 60, "seventy-two": 72,
             "ninety": 90}
_UNITS = {"hour": "hours", "day": "days", "week": "weeks"}

_WITHIN_RE = re.compile(
    r"\bwithin\s+(?:the\s+)?(\d+|" + "|".join(_NUMWORDS) + r")[\s-]*"
    r"(hour|day|week)s?\b", re.I)
_BEFORE_RE = re.compile(
    r"\b(?:before|by|no later than|not later than)\s+(?:the\s+)?"
    r"(\d{4}-\d{2}-\d{2}|"
    r"(?:" + "|".join(_MONTHS) + r")\s+\d{1,2}(?:,?\s+\d{4})?|"
    r"\d{1,2}\s+(?:" + "|".join(_MONTHS) + r")(?:,?\s+\d{4})?)", re.I)

_ISO_IN_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}")
_MONTHDAY_IN_TEXT = re.compile(
    r"(?:(" + "|".join(_MONTHS) + r")\s+(\d{1,2})|"
    r"(\d{1,2})\s+(" + "|".join(_MONTHS) + r"))(?:,?\s+(\d{4}))?", re.I)


def _dates_in(text: str, default_year: int) -> list:
    """Every date mentioned in a text (ISO or month-name), as dates."""
    out = []
    for m in _ISO_IN_TEXT.finditer(text):
        try:
            out.append(datetime.fromisoformat(m.group(0)).date())
        except ValueError:
            pass
    for m in _MONTHDAY_IN_TEXT.finditer(text):
        mon = (m.group(1) or m.group(4) or "").lower()
        day = m.group(2) or m.group(3)
        if not mon or not day:
            continue
        year = int(m.group(5)) if m.group(5) else default_year
        try:
            out.append(datetime(year, _MONTHS[mon], int(day)).date())
        except ValueError:
            pass
    return out


def question_deadline(question: str, context: str | None, start: datetime):
    """The deadline the QUESTION itself states, if it states one in an
    unambiguous form -> (deadline_date, evidence, kind) or (None, None,
    None).  Subtler windows are Call 2's responsibility."""
    text = f"{question}\n{context or ''}"
    m = _WITHIN_RE.search(text)
    if m:
        raw = m.group(1).lower()
        n = int(raw) if raw.isdigit() else _NUMWORDS.get(raw)
        if n:
            unit = _UNITS[m.group(2).lower()]
            return ((start + timedelta(**{unit: n})).date(),
                    f"within {n} {unit}", "relative")
    m = _BEFORE_RE.search(text)
    if m:
        dates = _dates_in(m.group(1), start.year)
        if dates:
            return dates[0], m.group(0).strip(), "absolute"
    return None, None, None


def window_findings(question: str, context: str | None, resolution: str,
                    start: datetime, cutoff: datetime) -> list:
    """Error when the question states a deadline strictly narrower than the
    compile cutoff and the resolution shows no trace of it."""
    deadline, evidence, kind = question_deadline(question, context, start)
    if deadline is None:
        return []
    if deadline >= (cutoff - timedelta(days=1)).date():
        return []                    # not narrower than the cutoff: nothing to lose
    for d in _dates_in(resolution, start.year):
        if abs((d - deadline).days) <= 1:
            return []                # the resolution names the question's date
    if kind == "relative":
        n, unit = evidence.split()[1], evidence.split()[2]
        # the window may be restated in digits or in words ("2"/"two")
        spellings = [re.escape(n)] + [re.escape(w) for w, v in _NUMWORDS.items()
                                      if str(v) == n]
        if re.search(rf"\b(?:{'|'.join(spellings)})[\s-]*{unit[:-1]}",
                     resolution, re.I):
            return []                # the resolution restates the window itself
    return [f"the question states the deadline {evidence!r} "
            f"({deadline.isoformat()}), which is narrower than the compile "
            f"cutoff {cutoff.date().isoformat()}, but the resolution "
            f"references neither: the cutoff must never silently replace "
            f"the question's own window"]
