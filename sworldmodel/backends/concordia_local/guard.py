"""Minimum agency guard: the final event-resolution chain step.

Directive rule ("Immediate minimum agency guard"): the Game Master may
describe mechanical or nonvoluntary consequences, but it may not
permanently commit a voluntary decision for a DIFFERENT actor without
giving that actor its own turn.  Voluntary decisions include: replying,
agreeing, voting, purchasing, accepting, rejecting, refusing, declining,
signing, supporting, committing, promising, choosing, deciding, and
choosing what to say.

Seam (CONCORDIA_AUDIT.md section E, option 1 -- no upstream fork): the
guard is a plain callable with the audited ``event_resolution_steps``
signature ``(interactive_document, event_statement, active_player_name)
-> str``.  The builder appends it as the FINAL chain element, so it sees
the fully resolved candidate event before observer notification and
before the engine's ``[event]`` commit.  The upstream in-repo precedent
is ``AccountForAgencyOfOthers`` (event_resolution.py) -- but that step is
LLM-driven and unseeded-shuffle nondeterministic; this guard is
DETERMINISTIC CODE in its default path (pure string analysis, no model
call, no document write, no randomness).

Detection basis
    A KNOWN actor name other than the active player occurring as the
    grammatical agent of a voluntary-act assertion: the name (optionally
    a name chain joined by "and"/commas, optionally followed by up to two
    generic adverb-like lead-in tokens) immediately governing a FINITE
    voluntary-act verb form.  Verb forms are generated from a curated
    stem + suffix paradigm table covering the directive's act-category
    lemmas (reply, agree, vote, purchase, accept, reject, refuse,
    decline, sign, support, commit, promise, choose, say, decide) in
    base, third-person-singular, and simple-past form.  These are
    act-category words, not scenario vocabulary; the table stores stems
    and suffixes so the assembled surface forms exist only at runtime.

Deliberate conservatism (documented non-detections, chosen to avoid
false positives on delivery/receipt/hypothetical text):

- Gerund/participle forms are NOT triggers: in "replies to X agreeing
  to a plan" the agreement belongs to the SUBJECT, not to X (a measured
  baseline-scenario shape); bare "-ing" adjacency would over-block.
- A name preceded by a preposition is not an agent ("sends it to X").
- A name preceded by a conditional frame word is not a committed act
  ("if X agrees" states a condition, not a decision).
- Modal/auxiliary constructions ("X may agree", "X has agreed",
  "X does not agree") are not detected in v1; they are predictions,
  perfects, and negations rather than the canonical simple-finite GM
  overreach ("..., and X agrees ...").  Listed for later hardening.
- Passive agents ("signed by X") are not detected in v1.
- Reported speech ("announces that X agrees") IS detected: the committed
  ``[event]`` text enters every observer's memory verbatim, so an
  embedded decision assertion does the same harm as a direct one.  This
  is the one BORDERLINE class the optional live-model confirmation may
  relax (see ``make_agency_guard``).

Rewrite rule (never inventing content, never deciding for the actor in
either direction):

1. the active player's attempt text before the offending clause is
   preserved verbatim (only boundary whitespace/linking punctuation is
   trimmed and terminal punctuation normalized);
2. the asserted other-actor decision clause is removed through the end
   of its sentence;
3. one neutral availability sentence per affected actor is appended:
   the actor is now able to observe what happened and to respond in
   their own turn.

Escalation: an optional ``escalate(event_in, event_out, active_player,
affected_actors)`` callable fires on every rewrite so the runner can
record guard interventions next to the trace.

This module is pure stdlib (``re`` + ``dataclasses``) and importable
everywhere ``sworldmodel`` is importable; it never imports Concordia.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

#: the ``gm_config['guard_slot']`` value naming this guard as the
#: reserved final resolution step (planner emits it; builder checks it)
GUARD_SLOT_VALUE = "agency_guard_v1"

#: containment marker of the availability sentence (tests assert on it)
AVAILABILITY_MARKER = "is now able to observe"

_AVAILABILITY_TEMPLATE = ("{name} is now able to observe this and to "
                          "respond in their own turn.")

#: voluntary-act verb morphology: (stem, suffixes) -> finite surface
#: forms (base / third-person-singular / simple-past), assembled at
#: runtime.  Gerunds are deliberately not generated (see module
#: docstring).  Irregular past forms carry their own stem row.
_ACT_FORM_PARADIGMS = (
    ("repl", ("y", "ies", "ied")),
    ("agree", ("", "s", "d")),
    ("vot", ("e", "es", "ed")),
    ("purchas", ("e", "es", "ed")),
    ("accept", ("", "s", "ed")),
    ("reject", ("", "s", "ed")),
    ("refus", ("e", "es", "ed")),
    ("declin", ("e", "es", "ed")),
    ("sign", ("", "s", "ed")),
    ("support", ("", "s", "ed")),
    ("commit", ("", "s", "ted")),
    ("promis", ("e", "es", "ed")),
    ("choos", ("e", "es")),
    ("chos", ("e",)),
    ("say", ("", "s")),
    ("said", ("",)),
    ("decid", ("e", "es", "ed")),
)

#: closed-class words that mark the following name as NOT the agent of a
#: new committed act: prepositions (object position) and hypothetical /
#: conditional frames (a condition is not a commitment)
_NON_AGENT_LEAD_WORDS = frozenset((
    "to", "with", "for", "from", "at", "by", "about", "of", "on", "in",
    "into", "onto", "upon", "toward", "towards", "via", "unto", "per",
    "near", "without", "than", "versus", "behind", "beside", "between",
    "among", "around", "before", "against",
    "if", "whether", "unless", "until", "once", "when", "whenever",
    "should", "assuming", "provided", "suppose", "supposing", "lest",
))

#: lead words marking a BORDERLINE finding (reported speech): detected by
#: default; the optional live-model confirmation may relax exactly these
_BORDERLINE_LEAD_WORDS = frozenset(("that",))

#: connective / subordinator tokens eaten backwards from a finding so the
#: removal starts at the clause boundary, keeping the attempt prefix clean
_CLAUSE_LINK_WORDS = frozenset((
    "and", "but", "then", "so", "while", "whereupon", "meanwhile",
    "after", "because", "whereas", "that", "which", "who", "whom", "as",
))

#: generic adverb-like tokens allowed between the subject chain and the
#: verb form (plus any single token ending in "ly"); at most two
_LEAD_IN_WORDS = ("both", "all", "also", "then", "now", "first",
                  "finally", "again", "still", "each")

#: characters accepted as a piece's own terminal punctuation (no period
#: appended after these); the colon covers the upstream attempt frame
_TERMINAL_CHARS = ".!?…:\"')]’”"

#: linking punctuation stripped from a kept piece's trailing boundary
_STRIP_TRAIL_CHARS = " \t,;-–—"


def voluntary_act_forms() -> frozenset:
    """The exact finite surface forms the detector triggers on."""
    return frozenset(stem + suffix
                     for stem, suffixes in _ACT_FORM_PARADIGMS
                     for suffix in suffixes)


@dataclass(frozen=True)
class _Finding:
    start: int            # subject-chain start offset in the event text
    end: int              # verb-form end offset
    affected: tuple       # non-active known actors asserted as agents
    borderline: bool      # reported-speech lead ("that")


def _word_before(text: str, pos: int) -> str:
    """The lowercased alphabetic word immediately preceding ``pos``
    (skipping whitespace), or '' when there is none."""
    j = pos
    while j > 0 and text[j - 1] in " \t":
        j -= 1
    k = j
    while k > 0 and text[k - 1].isalpha():
        k -= 1
    return text[k:j].lower()


def _clause_start(text: str, pos: int) -> int:
    """Walk backwards from the subject start over linking punctuation and
    connective words so removal begins at the clause boundary."""
    i = pos
    while True:
        j = i
        while j > 0 and text[j - 1] in " \t":
            j -= 1
        if j > 0 and text[j - 1] in ",;-–—":
            i = j - 1
            continue
        k = j
        while k > 0 and text[k - 1].isalpha():
            k -= 1
        word = text[k:j].lower()
        if word and word in _CLAUSE_LINK_WORDS:
            i = k
            continue
        return i


def _sentence_end(text: str, pos: int) -> int:
    """First sentence terminator at or after ``pos`` (the terminator and
    any trailing closing quotes are consumed; a newline is not)."""
    i = pos
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            return i
        if ch in ".!?":
            i += 1
            while i < len(text) and text[i] in "\"')]’”":
                i += 1
            return i
        i += 1
    return len(text)


def _merge_spans(spans: Sequence) -> list:
    merged: list = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _clean_piece(piece: str) -> str:
    """Boundary normalization only: strip edges, drop dangling linking
    punctuation, ensure the piece ends in terminal punctuation.  Interior
    bytes are untouched (the attempt stays verbatim)."""
    p = piece.strip()
    p = p.rstrip(_STRIP_TRAIL_CHARS)
    if not p:
        return ""
    if p[-1] not in _TERMINAL_CHARS:
        p += "."
    return p


def make_agency_guard(
    actor_names: Iterable,
    *,
    model=None,
    use_llm_confirmation: bool = False,
    escalate: Callable | None = None,
) -> Callable:
    """Build the deterministic agency-guard chain step for one branch.

    ``actor_names`` is the branch's KNOWN actor roster (Concordia entity
    names as they appear in event text); only these actors are protected
    -- an unknown name is never treated as an actor.  ``escalate``, when
    given, is called as ``escalate(event_in, event_out, active_player,
    affected_actors)`` after every rewrite (never on passthrough).

    ``model`` + ``use_llm_confirmation=True`` enable the OPTIONAL
    live-model relaxation: when at least one finding is borderline
    (reported speech), ONE yes/no question is posed through the passed
    resolution document (the audited seam surface owns the document and
    its model; the ``model`` object gates the feature and is reserved for
    a dedicated-document variant).  A "no" answer drops only the
    borderline findings.  The deterministic default path is complete
    without any of this and never touches the document.
    """
    names = tuple(actor_names)
    if not names:
        raise ValueError("actor_names must name at least one known actor")
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                "every actor name must be a non-blank string, got "
                f"{name!r}")
    if len(set(names)) != len(names):
        raise ValueError("actor names must be unique")
    if escalate is not None and not callable(escalate):
        raise ValueError("escalate must be callable when provided")
    if type(use_llm_confirmation) is not bool:
        raise ValueError("use_llm_confirmation must be a boolean")
    if use_llm_confirmation and model is None:
        raise ValueError(
            "use_llm_confirmation=True requires a model object; the "
            "deterministic path needs neither")

    name_alt = "|".join(
        re.escape(name) for name in sorted(names, key=len, reverse=True))
    verb_alt = "|".join(
        re.escape(form)
        for form in sorted(voluntary_act_forms(), key=len, reverse=True))
    lead_in_alt = "|".join(_LEAD_IN_WORDS)
    boundary = r"[\w'’-]"
    separator = r"(?:\s*[,;]\s*(?:(?:and|&)\s+)?|\s+(?:and|&)\s+)"
    subject = (rf"(?P<subject>(?:{name_alt})"
               rf"(?:{separator}(?:{name_alt}))*)")
    lead_in = rf"(?:(?:{lead_in_alt}|\w+ly)\s+){{0,2}}"
    event_pattern = re.compile(
        rf"(?<!{boundary}){subject}\s+{lead_in}"
        rf"(?P<verbform>(?i:{verb_alt}))(?!{boundary})")
    chain_name_pattern = re.compile(
        rf"(?<!{boundary})(?:{name_alt})(?!{boundary})")

    def _detect(event_statement: str, active_player_name: str) -> list:
        findings = []
        pos = 0
        while True:
            match = event_pattern.search(event_statement, pos)
            if match is None:
                return findings
            chain = chain_name_pattern.findall(match.group("subject"))
            affected = []
            for chain_name in chain:
                if (chain_name != active_player_name
                        and chain_name not in affected):
                    affected.append(chain_name)
            lead_word = _word_before(event_statement, match.start())
            if not affected or lead_word in _NON_AGENT_LEAD_WORDS:
                # Not a violation AT THIS START (the active player's own
                # choice, an object position, or a hypothetical frame) --
                # but a greedy comma chain that began at a non-agent
                # ("... to X, and X agrees") may still CONTAIN the real
                # clause subject, so resume just past the start, not past
                # the whole match.
                pos = match.start() + 1
                continue
            findings.append(_Finding(
                start=match.start(),
                end=match.end(),
                affected=tuple(affected),
                borderline=lead_word in _BORDERLINE_LEAD_WORDS,
            ))
            pos = match.end()

    def _rewrite(event_statement: str, findings: list) -> str:
        spans = [( _clause_start(event_statement, finding.start),
                   _sentence_end(event_statement, finding.end))
                 for finding in findings]
        pieces = []
        cursor = 0
        for start, end in _merge_spans(spans):
            pieces.append(event_statement[cursor:start])
            cursor = end
        pieces.append(event_statement[cursor:])
        cleaned = [piece for piece in (_clean_piece(p) for p in pieces)
                   if piece]
        affected_order: list = []
        for finding in findings:
            for name in finding.affected:
                if name not in affected_order:
                    affected_order.append(name)
        availability = [_AVAILABILITY_TEMPLATE.format(name=name)
                        for name in affected_order]
        return " ".join(cleaned + availability)

    def agency_guard(document, event_statement, active_player_name):
        """Final resolution step: pass mechanical/receipt/own-choice text
        through byte-identically; rewrite asserted other-actor decisions
        into attempt-plus-availability form."""
        if not isinstance(event_statement, str) or not event_statement.strip():
            return event_statement
        findings = _detect(event_statement, active_player_name)
        if not findings:
            return event_statement
        if (use_llm_confirmation and model is not None
                and any(finding.borderline for finding in findings)
                and hasattr(document, "yes_no_question")):
            borderline_names: list = []
            for finding in findings:
                if finding.borderline:
                    for name in finding.affected:
                        if name not in borderline_names:
                            borderline_names.append(name)
            committed_fact = document.yes_no_question(
                "The candidate event mentions "
                + ", ".join(borderline_names)
                + " making a choice inside reported speech. Does the "
                  "event record that choice as an accomplished fact "
                  "rather than as something merely claimed or proposed?")
            if not committed_fact:
                findings = [finding for finding in findings
                            if not finding.borderline]
            if not findings:
                return event_statement
        rewritten = _rewrite(event_statement, findings)
        if rewritten == event_statement:
            return event_statement
        affected_all: list = []
        for finding in findings:
            for name in finding.affected:
                if name not in affected_all:
                    affected_all.append(name)
        if escalate is not None:
            escalate(event_statement, rewritten, active_player_name,
                     tuple(affected_all))
        return rewritten

    agency_guard.actor_names = names
    agency_guard.guard_slot_value = GUARD_SLOT_VALUE
    return agency_guard
