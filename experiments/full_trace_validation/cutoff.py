"""Mechanical historical-cutoff enforcement for the frozen counterfactual.

Experiment-only.  The a16z scenario is a HISTORICAL counterfactual frozen
on 1 July 2025: nothing published after that date may enter the compiler
prompt, the compiled world, any plan, any actor context, or the evidence
manifest.  A promise not to include such material is worth nothing, so
this module turns the promise into a check that runs over the actual
bytes and refuses the run when it fails.

Two independent arms, both applied to every surface
---------------------------------------------------
``date arm``
    Every date-shaped token in the text is parsed (ISO ``YYYY-MM-DD``,
    ``Month D, YYYY``, ``D Month YYYY``, ``Month YYYY``, and bare
    four-digit years).  A token that resolves to a day AFTER the declared
    simulation window end is a violation; a bare year after the cutoff
    year is a violation.  Days inside ``(cutoff, window_end]`` are
    SIMULATED time, not published sources, so they are recorded as
    window references rather than violations -- the window itself is a
    declared input.
``phrase arm``
    A small, deliberately narrow set of completed-state phrasings that
    could only be known after the cutoff (the eventual real hiring).
    Conditional and prospective wording ("if he joins", "should a16z
    hire") is NOT matched: the whole point of the simulation is to
    explore that possibility, and a validator that blocked it would be
    blocking the experiment rather than the leak.

:data:`POST_CUTOFF_CANARY` is a synthetic string that trips both arms.
``tests/experiment_harness/test_a16z_cutoff.py`` proves the validator
rejects it, and rejects date-only and phrase-only variants, so the
enforcement cannot silently degrade into a no-op.

Nothing here rewrites text.  A violation is reported with its surface,
its exact matched token, and its reason; the caller refuses the run.
"""

from __future__ import annotations

import datetime
import re

#: nothing published after this date may enter the simulation
CUTOFF_DATE = datetime.date(2025, 7, 1)

#: the declared simulation window end; days in (CUTOFF_DATE, WINDOW_END]
#: are simulated time, not published sources
WINDOW_END = datetime.date(2025, 7, 10)

#: a synthetic string that MUST be rejected (proves the arms have teeth)
POST_CUTOFF_CANARY = (
    "POST-CUTOFF CANARY: by 2026-02-11 Richard Zheng now works at a16z, "
    "and the appointment was announced on December 4, 2025.")

#: canary variants that trip exactly one arm each
POST_CUTOFF_CANARY_DATE_ONLY = (
    "A partner memo dated 2025-11-30 records the outcome.")
POST_CUTOFF_CANARY_PHRASE_ONLY = (
    "Richard Zheng currently works at a16z on the New Media team.")

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_ALTERNATION = "|".join(sorted(_MONTHS, key=len, reverse=True))

_ISO_RE = re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b")
_MONTH_DAY_YEAR_RE = re.compile(
    rf"\b(?P<mon>{_MONTH_ALTERNATION})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?"
    rf",?\s+(?P<y>\d{{4}})\b", re.IGNORECASE)
_DAY_MONTH_YEAR_RE = re.compile(
    rf"\b(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<mon>{_MONTH_ALTERNATION})"
    rf"\.?,?\s+(?P<y>\d{{4}})\b", re.IGNORECASE)
_MONTH_YEAR_RE = re.compile(
    rf"\b(?P<mon>{_MONTH_ALTERNATION})\.?\s+(?P<y>\d{{4}})\b", re.IGNORECASE)
_QUARTER_YEAR_RE = re.compile(
    r"\b(?:Q(?P<q>[1-4])\s*(?P<y>\d{4})|(?P<y2>\d{4})\s*Q(?P<q2>[1-4]))\b",
    re.IGNORECASE)
_YEAR_RE = re.compile(r"(?<![\d\-/.])(?P<y>(?:19|20)\d{2})(?![\d\-/.])")

#: completed-state phrasings that presuppose the post-cutoff outcome.
#: Narrow on purpose: prospective and conditional wording must pass.
POST_CUTOFF_PHRASE_PATTERNS = (
    r"\b(?:has|had|have)\s+(?:already\s+)?joined\b[^.!?]{0,40}a16z",
    r"\balready\s+(?:works?|working|joined|joins|employed)\b[^.!?]{0,40}"
    r"a16z",
    r"\b(?:now|currently|today|since)\s+(?:works?|working|employed|leads?|"
    r"heads?|runs?|is\s+(?:at|with|part\s+of))\b[^.!?]{0,40}a16z",
    r"\bwas\s+hired\s+by\b[^.!?]{0,40}a16z",
    r"\b(?:has|had)\s+been\s+hired\b[^.!?]{0,40}a16z",
    r"\ba16z\s+(?:hired|announced\s+the\s+hire\s+of|brought\s+on)\b"
    r"[^.!?]{0,40}(?:richard|zheng)",
    r"\b(?:accepted|signed)\s+(?:the\s+)?a16z\s+offer\b",
    r"\bhis\s+(?:role|job|position|work)\s+at\s+a16z\b",
    r"POST-CUTOFF\s+CANARY",
)

_COMPILED_PHRASES = tuple((pattern, re.compile(pattern, re.IGNORECASE))
                          for pattern in POST_CUTOFF_PHRASE_PATTERNS)


class HistoricalCutoffViolation(AssertionError):
    """Post-cutoff material reached a surface that must be pre-cutoff.

    Carries every collected finding; the run is refused, never repaired.
    """

    def __init__(self, findings) -> None:
        self.findings = list(findings)
        detail = "; ".join(
            f"{finding['surface']}: {finding['reason']} "
            f"({finding['matched_text']!r})" for finding in self.findings[:8])
        super().__init__(
            f"{len(self.findings)} post-cutoff violation(s): {detail}")


def _safe_date(year: int, month: int, day: int):
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _classify_day(day: datetime.date):
    """``(verdict, reason)`` for one fully resolved calendar day."""
    if day <= CUTOFF_DATE:
        return "clean", "on or before the 2025-07-01 knowledge cutoff"
    if day <= WINDOW_END:
        return "window", (
            "inside the declared simulation window "
            f"({CUTOFF_DATE.isoformat()} .. {WINDOW_END.isoformat()}): "
            "simulated time, not a published source")
    return "violation", (
        f"resolves to {day.isoformat()}, after the declared simulation "
        f"window end {WINDOW_END.isoformat()}; no material published after "
        f"the {CUTOFF_DATE.isoformat()} cutoff may enter this counterfactual")


def _date_findings(text: str) -> tuple:
    """``(violations, window_references, clean_tokens)`` for one string."""
    violations: list = []
    windows: list = []
    clean: list = []
    consumed: list = []

    def record(match, day, granularity):
        verdict, reason = _classify_day(day)
        entry = {"matched_text": match.group(0), "span": list(match.span()),
                 "resolved_day": day.isoformat(), "granularity": granularity,
                 "reason": reason}
        if verdict == "violation":
            violations.append(entry)
        elif verdict == "window":
            windows.append(entry)
        else:
            clean.append(entry)
        consumed.append(match.span())

    for match in _ISO_RE.finditer(text):
        day = _safe_date(int(match.group("y")), int(match.group("m")),
                         int(match.group("d")))
        if day is not None:
            record(match, day, "day")
    for regex in (_MONTH_DAY_YEAR_RE, _DAY_MONTH_YEAR_RE):
        for match in regex.finditer(text):
            day = _safe_date(int(match.group("y")),
                             _MONTHS[match.group("mon").lower().rstrip(".")],
                             int(match.group("d")))
            if day is not None:
                record(match, day, "day")

    def overlaps(span):
        return any(span[0] < end and start < span[1]
                   for start, end in consumed)

    for match in _MONTH_YEAR_RE.finditer(text):
        if overlaps(match.span()):
            continue
        month = _MONTHS[match.group("mon").lower().rstrip(".")]
        year = int(match.group("y"))
        # A month resolves to its FIRST day: "August 2025" could mean any
        # day in August, and its earliest day already decides the verdict.
        day = _safe_date(year, month, 1)
        if day is not None:
            record(match, day, "month")
    for match in _QUARTER_YEAR_RE.finditer(text):
        if overlaps(match.span()):
            continue
        year = int(match.group("y") or match.group("y2"))
        quarter = int(match.group("q") or match.group("q2"))
        day = _safe_date(year, 1 + 3 * (quarter - 1), 1)
        if day is not None:
            record(match, day, "quarter")
    for match in _YEAR_RE.finditer(text):
        if overlaps(match.span()):
            continue
        year = int(match.group("y"))
        # A bare year resolves to its FIRST day: "2026" is post-cutoff
        # whichever day is meant, while a bare "2025" cannot be placed
        # after the cutoff without inventing a month.
        day = _safe_date(year, 1, 1)
        if day is not None:
            record(match, day, "year")
    return tuple(violations), tuple(windows), tuple(clean)


def _phrase_findings(text: str) -> tuple:
    findings: list = []
    for pattern, compiled in _COMPILED_PHRASES:
        for match in compiled.finditer(text):
            findings.append({
                "matched_text": match.group(0)[:160],
                "span": list(match.span()),
                "pattern": pattern,
                "reason": ("completed-state phrasing that presupposes an "
                           "outcome only knowable after the "
                           f"{CUTOFF_DATE.isoformat()} cutoff")})
    return tuple(findings)


def scan_text(surface: str, text) -> dict:
    """Scan ONE named surface; returns a structured record (never raises).

    ``text`` may be any JSON-shaped value: mappings, sequences, strings
    and scalars are all flattened to text so a claim buried in a nested
    structure is scanned exactly like a top-level string.
    """
    flat = flatten_text(text)
    date_violations, windows, clean = _date_findings(flat)
    phrase_violations = _phrase_findings(flat)
    violations = [{"surface": surface, "arm": "date", **entry}
                  for entry in date_violations]
    violations += [{"surface": surface, "arm": "phrase", **entry}
                   for entry in phrase_violations]
    return {
        "surface": surface,
        "characters_scanned": len(flat),
        "violations": violations,
        "window_references": [{"surface": surface, **entry}
                              for entry in windows],
        "pre_cutoff_date_tokens": [{"surface": surface, **entry}
                                   for entry in clean],
        "clean": not violations,
    }


def flatten_text(value) -> str:
    """Every string anywhere in ``value``, joined with newlines."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    parts: list = []
    if isinstance(value, dict):
        for key, item in value.items():
            parts.append(str(key))
            parts.append(flatten_text(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            parts.append(flatten_text(item))
    else:
        parts.append(str(value))
    return "\n".join(part for part in parts if part)


def scan_surfaces(surfaces) -> dict:
    """Scan an ordered ``{surface_name: value}`` mapping."""
    records = [scan_text(name, value) for name, value in surfaces.items()]
    violations = [entry for record in records
                  for entry in record["violations"]]
    return {
        "cutoff_date": CUTOFF_DATE.isoformat(),
        "simulation_window_end": WINDOW_END.isoformat(),
        "arms": {
            "date": ("every date-shaped token is resolved to a calendar "
                     "day; a day after the window end is a violation"),
            "phrase": ("narrow completed-state phrasings that presuppose "
                       "the post-cutoff outcome"),
        },
        "phrase_patterns": list(POST_CUTOFF_PHRASE_PATTERNS),
        "surfaces_scanned": [record["surface"] for record in records],
        "surface_count": len(records),
        "per_surface": records,
        "violations": violations,
        "violation_count": len(violations),
        "window_references": [entry for record in records
                              for entry in record["window_references"]],
        "clean": not violations,
    }


def assert_clean(surfaces) -> dict:
    """Scan and REFUSE the run when anything post-cutoff is present."""
    report = scan_surfaces(surfaces)
    if not report["clean"]:
        raise HistoricalCutoffViolation(report["violations"])
    return report
