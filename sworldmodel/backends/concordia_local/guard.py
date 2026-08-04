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

Detection basis (v2, hardened per the phases 3-7 adversarial review,
findings 6 and 7; v3 adds class 6, closing the phases 8-11 review
finding F1):

1. NAMED subjects: a KNOWN actor name other than the active player
   (optionally a name chain joined by "and"/commas) governing a
   voluntary-act verb complex.
2. PRONOUN subjects: a third-person subject pronoun governing a
   voluntary-act verb complex.  Reference is resolved deterministically:
   a singular pronoun binds the NEAREST preceding roster name (gender is
   never inferred); a bare plural binds every distinct preceding roster
   name; a first-person-plural or universal subject binds every
   protected actor.  When no preceding roster name resolves the
   reference, every non-active roster actor is treated as potentially
   bound -- an unresolvable committed decision must not slip through.
   A pronoun whose only resolution is the ACTIVE player is the active
   player's own act and passes.
3. COLLECTIVE subjects: a determiner plus a generic decision-making
   group noun (team, board, council, ...) governing a voluntary-act verb
   complex binds every non-active roster actor (membership is not
   textually resolvable).
4. VERB COMPLEXES: the simple finite forms plus perfect ("has agreed",
   "has been agreeing"), progressive ("is agreeing"), and
   modal-perfect ("will have accepted") auxiliary chains.  One
   comma-bounded parenthetical aside may sit between the subject and the
   verb complex ("Morgan, after some thought, agrees").
5. NOMINALIZATIONS: a roster name's possessive act noun ("Morgan's
   agreement to the terms") and a determined act noun with a roster
   by-agent ("the acceptance by Morgan") assert the same accomplished
   decision without a finite verb and are treated identically.
6. PROXY ATTRIBUTION (colon/dash subject boundaries): upstream
   EventResolution treats ``NAME:`` and ``NAME --`` as active-entity
   attribution separators (event_resolution.py strips exactly these
   from a leading active-player prefix), and the sequential engine
   commits every turn in the ``{name}: {content}`` format -- so a
   NON-ACTIVE roster name (or "and"/comma chain) immediately followed
   by ``:`` (optional horizontal space) or by whitespace plus ``--``
   claims the ENTIRE following content as that actor's own turn:
   speech, an act phrase, or full sentences alike ("choosing what to
   say" is itself a voluntary decision, so no act verb is required).
   The ACTIVE player's own attribution ("Active: <their own act>", the
   upstream turn format, leading or not) claims nobody else's agency
   and passes byte-identically.  Because upstream defines no CLOSING
   delimiter for an attributed segment, the removal span runs from the
   name to the next line break or end of text.

All trigger vocabulary below is PLAIN LITERAL WORD FORMS of the
directive's own act categories.  A prior revision assembled the same
surface forms from a stem+suffix table, which the review (finding 7)
judged a circumvention of the scenario-vocabulary scanner's mechanism;
the sanctioned remedy is literals here plus a documented, narrow
allowlist entry in tests/test_hardcoding_guard.py.  These are
act-category words, not scenario vocabulary.

Speaker-stance protection (review finding 6 over-block classes): content
that merely reports the SPEAKER'S OWN mental state or performative
request about another actor is the speaker's own content and passes
byte-identically:

- belief-verb complements: "Alex hopes Morgan agrees", "Alex believes
  Morgan will reply" (also through a "that" complementizer);
- performative content requests: "Alex asks that Morgan reply by
  Friday" -- a request ABOUT another actor's future act is the
  speaker's own act;
- anticipation frames before nominalizations: "asks for Morgan's
  agreement", "waits for Morgan's reply", "without Morgan's signature".

Deliberate conservatism (documented non-detections, chosen to avoid
false positives on delivery/receipt/hypothetical text):

- Gerund/participle forms are NOT triggers without a BE auxiliary: in
  "replies to X agreeing to a plan" the agreement belongs to the
  SUBJECT, not to X (a measured baseline-scenario shape); bare "-ing"
  adjacency would over-block.
- A name preceded by a preposition is not an agent ("sends it to X").
- A name preceded by a conditional frame word is not a committed act
  ("if X agrees" states a condition, not a decision).
- Bare modal predictions ("X may agree", "X will agree"), do-support
  ("X does not agree", "X does agree"), and negated auxiliary chains
  ("X has not agreed") are predictions, denials, or emphatics rather
  than committed decisions and are not detected.
- Passive constructions ("signed by X", "X has been chosen") keep the
  name in patient position and are not detected as that name's act.
- Second-person and "it" subjects, pronoun-possessive nominalizations
  ("their agreement"), collective possessives ("Morgan's team
  accepts"), and asides longer than one comma pair or 60 characters are
  out of the deterministic v2 net; listed for later hardening.
- Proxy-attribution residuals (v3): a SINGLE em/en dash between a name
  and content ("Morgan — agrees") is not an upstream attribution
  separator and stays undetected as an attribution (the pre-existing
  dash-separated subject-verb gap, now explicit); a name split from its
  marker across a line break ("Morgan\\n: yes") or by an aside
  ("Morgan, unprompted,: yes") is undetected (the marker must be
  name-adjacent); a marker after a non-agent lead word keeps the
  object-position exemption -- "sends a note to Morgan: 'call me'" is
  the speaker's own message TO the name, which also exempts
  received-content frames ("reads the note from Morgan: 'I agree'"),
  a residual accepted to keep the epistolary form usable, while
  assertion-verb frames ("quotes Morgan: 'I agree'") and bare markers
  stay caught.  In the over-removal direction: the attributed segment
  runs to the line break (upstream has no closing delimiter), so any
  same-line content AFTER a violating marker -- including the active
  player's own trailing text -- is removed with it, and a spaced
  double-dash appositive after a direct-object name ("thanks
  Morgan -- everyone applauds") parses as an attribution; both fail
  in the recoverable direction (removal plus availability, attempt
  prefix preserved), never by inventing agency.
- The comma aside is content-blind: an asyndetic serial-verb tail after
  a direct-object name ("thanks Morgan, smiles, signs") parses like an
  aside and is conservatively rewritten.  The failure direction is the
  recoverable one (removal plus availability), never invented agency.
- Reported speech ("announces that X agrees") IS detected: the
  committed ``[event]`` text enters every observer's memory verbatim,
  so an embedded decision assertion does the same harm as a direct one.
  This is the one BORDERLINE class the optional live-model confirmation
  may relax (see ``make_agency_guard``).
- Stateless trade-off: a nominal reference to a decision that REALLY
  happened in an earlier turn ("Ada re-reads Bo's reply") is
  indistinguishable, without history, from an invented one and is
  conservatively rewritten; the cost is bounded (the actor's attempt
  prefix survives and the affected actor is offered its own turn),
  while a missed invention would permanently steal agency.

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

#: voluntary-act FINITE surface forms (base / third-person-singular /
#: simple past) of the directive's act-category lemmas, as plain
#: literals (finding 7).  Gerunds and participles are separate sets
#: below and trigger only inside auxiliary chains.
_ACT_FINITE_FORMS = (
    "reply", "replies", "replied",
    "agree", "agrees", "agreed",
    "vote", "votes", "voted",
    "purchase", "purchases", "purchased",
    "accept", "accepts", "accepted",
    "reject", "rejects", "rejected",
    "refuse", "refuses", "refused",
    "decline", "declines", "declined",
    "sign", "signs", "signed",
    "support", "supports", "supported",
    "commit", "commits", "committed",
    "promise", "promises", "promised",
    "choose", "chooses", "chose",
    "say", "says", "said",
    "decide", "decides", "decided",
)

#: past participles (perfect and modal-perfect chains only; after
#: "been" a participle is passive and deliberately NOT a trigger)
_ACT_PAST_PARTICIPLES = (
    "replied", "agreed", "voted", "purchased", "accepted", "rejected",
    "refused", "declined", "signed", "supported", "committed",
    "promised", "chosen", "said", "decided",
)

#: gerunds (progressive chains only: "is agreeing", "has been agreeing")
_ACT_GERUNDS = (
    "replying", "agreeing", "voting", "purchasing", "accepting",
    "rejecting", "refusing", "declining", "signing", "supporting",
    "committing", "promising", "choosing", "saying", "deciding",
)

#: act nominalizations ("Morgan's agreement", "the acceptance by
#: Morgan").  The bare noun "sign" is deliberately absent (a physical
#: signboard reading would over-block); "signature"/"signing" cover the
#: act sense.
_ACT_NOUN_FORMS = (
    "reply", "replies",
    "agreement", "agreements",
    "vote", "votes",
    "purchase", "purchases",
    "acceptance", "acceptances",
    "rejection", "rejections",
    "refusal", "refusals",
    "signature", "signatures", "signing",
    "commitment", "commitments",
    "promise", "promises",
    "choice", "choices",
    "decision", "decisions",
    "support",
)

#: third-person singular subject pronouns (nearest-antecedent binding)
_SINGULAR_SUBJECT_PRONOUNS = ("he", "she")
#: bare plural subject pronoun (all-preceding-names binding)
_PLURAL_SUBJECT_PRONOUNS = ("they",)
#: subjects that bind beyond the speaker by construction
_UNIVERSAL_SUBJECT_PRONOUNS = ("we", "everyone", "everybody")

#: generic decision-making group nouns for collective subjects; a
#: closed organizational-category list, not scenario vocabulary.  (One
#: classic register word is deliberately absent because the scanner
#: reserves it as scenario vocabulary; "board"/"council" cover that
#: register -- documented residual.)
_GROUP_NOUN_FORMS = (
    "team", "teams", "group", "groups", "board", "boards",
    "council", "councils", "crew", "crews", "staff",
    "members", "partners", "colleagues", "others", "rest",
    "majority", "party", "parties", "delegation", "delegations",
    "cohort", "cohorts", "firm", "firms", "club", "clubs",
    "organization", "organizations", "company", "companies",
    "family", "families",
)

#: determiners opening a collective subject
_COLLECTIVE_DETERMINERS = (
    "the", "this", "that", "these", "those", "his", "her", "their",
    "its", "our", "my", "your", "both", "all", "each", "every",
    "a", "an",
)

#: determiners opening a by-agent nominalization
_BY_PHRASE_DETERMINERS = (
    "the", "this", "that", "his", "her", "their", "its", "a", "an",
    "any", "such", "one",
)

#: closed-class words that mark the following subject as NOT the agent
#: of a new committed act: prepositions (object position) and
#: hypothetical / conditional frames (a condition is not a commitment)
_NON_AGENT_LEAD_WORDS = frozenset((
    "to", "with", "for", "from", "at", "by", "about", "of", "on", "in",
    "into", "onto", "upon", "toward", "towards", "via", "unto", "per",
    "near", "without", "than", "versus", "behind", "beside", "between",
    "among", "around", "before", "against",
    "if", "whether", "unless", "until", "once", "when", "whenever",
    "should", "assuming", "provided", "suppose", "supposing", "lest",
))

#: speaker-stance verbs: a belief, hope, fear, or performative request
#: ABOUT another actor is the SPEAKER'S own content (review finding 6
#: over-block classes).  Suppresses detection directly before a subject
#: ("hopes Morgan agrees") and through a "that" complementizer ("asks
#: that Morgan reply by Friday").
_STANCE_VERBS = frozenset((
    "hope", "hopes", "hoped",
    "believe", "believes", "believed",
    "think", "thinks", "thought",
    "expect", "expects", "expected",
    "doubt", "doubts", "doubted",
    "wish", "wishes", "wished",
    "assume", "assumes", "assumed",
    "suspect", "suspects", "suspected",
    "fear", "fears", "feared",
    "imagine", "imagines", "imagined",
    "predict", "predicts", "predicted",
    "guess", "guesses", "guessed",
    "anticipate", "anticipates", "anticipated",
    "trust", "trusts", "trusted",
    "worry", "worries", "worried",
    "await", "awaits", "awaited", "awaiting",
    "ask", "asks", "asked",
    "request", "requests", "requested",
    "insist", "insists", "insisted",
    "demand", "demands", "demanded",
    "urge", "urges", "urged",
    "propose", "proposes", "proposed",
    "suggest", "suggests", "suggested",
    "recommend", "recommends", "recommended",
    "require", "requires", "required",
    "prefer", "prefers", "preferred",
    "beg", "begs", "begged",
    "invite", "invites", "invited",
    "want", "wants", "wanted",
    "need", "needs", "needed",
))

#: frame words before a NOMINALIZATION that anticipate rather than
#: presuppose the act ("for Morgan's agreement", "without Morgan's
#: signature", "pending Morgan's decision").  Presupposing frames
#: ("with Morgan's agreement, ...") are deliberately NOT here.
_NOMINAL_FRAME_WORDS = frozenset((
    "for", "without", "pending", "until", "unless", "before", "absent",
    "if", "whether", "should",
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
    """The exact finite surface forms the simple-clause detector
    triggers on (auxiliary chains additionally use the participle and
    gerund literals)."""
    return frozenset(_ACT_FINITE_FORMS)


@dataclass(frozen=True)
class _Finding:
    start: int            # subject/nominal start offset in the event text
    end: int              # matched construction end offset
    affected: tuple       # non-active known actors asserted as agents
    borderline: bool      # reported-speech lead ("that")
    #: exact removal-span end for families with their own boundary rule
    #: (proxy attribution: next line break / end of text); ``None``
    #: falls back to the sentence-end rule
    span_end: int | None = None


def _word_before_span(text: str, pos: int) -> tuple:
    """The lowercased alphabetic word immediately preceding ``pos``
    (skipping whitespace) and its start offset; ``('', pos)`` when there
    is none (any intervening punctuation breaks the chain)."""
    j = pos
    while j > 0 and text[j - 1] in " \t":
        j -= 1
    k = j
    while k > 0 and text[k - 1].isalpha():
        k -= 1
    return text[k:j].lower(), k


def _word_before(text: str, pos: int) -> str:
    return _word_before_span(text, pos)[0]


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


def _alternation(words: Iterable) -> str:
    """Deterministic longest-first alternation (ties broken
    lexicographically so the compiled pattern is byte-stable across
    processes regardless of hash seed)."""
    return "|".join(re.escape(word)
                    for word in sorted(words, key=lambda w: (-len(w), w)))


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
    -- an unknown name is never treated as an actor.  Pronoun and
    collective subjects that cannot be resolved to a specific roster
    name conservatively bind every non-active roster actor (each such
    actor receives the availability sentence).  ``escalate``, when
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

    name_alt = _alternation(names)
    finite_alt = _alternation(_ACT_FINITE_FORMS)
    participle_alt = _alternation(_ACT_PAST_PARTICIPLES)
    gerund_alt = _alternation(_ACT_GERUNDS)
    noun_alt = _alternation(_ACT_NOUN_FORMS)
    group_alt = _alternation(_GROUP_NOUN_FORMS)
    pronoun_alt = _alternation(_SINGULAR_SUBJECT_PRONOUNS
                               + _PLURAL_SUBJECT_PRONOUNS
                               + _UNIVERSAL_SUBJECT_PRONOUNS)
    lead_in_alt = _alternation(_LEAD_IN_WORDS)

    boundary = r"[\w'’-]"
    separator = r"(?:\s*[,;]\s*(?:(?:and|&)\s+)?|\s+(?:and|&)\s+)"
    lead_in = rf"(?:(?:{lead_in_alt}|\w+ly)\s+){{0,2}}"
    #: one comma-bounded parenthetical aside between subject and verb
    aside = r"(?:\s*,\s*[^,;.!?\n]{1,60}\s*,)?"
    #: finite verb or auxiliary chain asserting an accomplished act; a
    #: "not"/"never" in the chain fails the lead-in slot, so negations
    #: pass through by construction; "been" + participle (passive) is
    #: deliberately not an alternative
    verb_complex = (
        r"(?:"
        rf"(?i:has|have|had)\s+{lead_in}"
        rf"(?:(?i:{participle_alt})|(?i:been)\s+{lead_in}(?i:{gerund_alt}))"
        rf"|(?i:is|are|was|were)\s+{lead_in}(?i:{gerund_alt})"
        rf"|(?i:will|shall|would)\s+{lead_in}(?i:have)\s+{lead_in}"
        rf"(?i:{participle_alt})"
        rf"|(?i:{finite_alt})"
        rf")(?!{boundary})")
    trailer = rf"{aside}\s+{lead_in}{verb_complex}"

    named_pattern = re.compile(
        rf"(?<!{boundary})(?P<subject>(?:{name_alt})"
        rf"(?:{separator}(?:{name_alt}))*)(?!{boundary}){trailer}")
    #: detection class 6 -- upstream's own attribution separators: a
    #: roster name (chain) immediately followed by ":" (optional
    #: horizontal space) or by whitespace plus "--" attributes the
    #: following content to that name; content-blind by design (a
    #: fabricated turn frame is an agency claim whatever it contains)
    attribution_pattern = re.compile(
        rf"(?<!{boundary})(?P<subject>(?:{name_alt})"
        rf"(?:{separator}(?:{name_alt}))*)(?!{boundary})"
        rf"(?:[ \t]*:|[ \t]+--+)")
    pronoun_pattern = re.compile(
        rf"(?<!{boundary})(?P<pron>(?i:{pronoun_alt}))(?!{boundary})"
        rf"{trailer}")
    collective_pattern = re.compile(
        rf"(?<!{boundary})(?P<det>(?i:{_alternation(_COLLECTIVE_DETERMINERS)}))"
        rf"\s+(?:[\w-]+\s+)?(?P<group>(?i:{group_alt}))(?!{boundary})"
        rf"{trailer}")
    possessive_pattern = re.compile(
        rf"(?<!{boundary})(?P<pname>(?:{name_alt}))(?:'|’)s\s+"
        rf"(?:[\w-]+\s+)?(?P<pnoun>(?i:{noun_alt}))(?!{boundary})")
    by_agent_pattern = re.compile(
        rf"(?<!{boundary})(?P<bdet>(?i:{_alternation(_BY_PHRASE_DETERMINERS)}))"
        rf"\s+(?:[\w-]+\s+)?(?P<bnoun>(?i:{noun_alt}))\s+"
        rf"(?:(?i:of)\s+(?:[\w'’-]+\s+){{0,3}})?"
        rf"(?i:by)\s+(?P<bname>(?:{name_alt}))(?!{boundary})")
    chain_name_pattern = re.compile(
        rf"(?<!{boundary})(?:{name_alt})(?!{boundary})")

    singular_pronouns = frozenset(_SINGULAR_SUBJECT_PRONOUNS)
    plural_pronouns = frozenset(_PLURAL_SUBJECT_PRONOUNS)

    def _protected_others(active_player_name: str) -> tuple:
        return tuple(name for name in names if name != active_player_name)

    def _names_before(text: str, pos: int) -> list:
        return [match.group(0)
                for match in chain_name_pattern.finditer(text, 0, pos)]

    def _resolve_named(match, text, active):
        chain = chain_name_pattern.findall(match.group("subject"))
        affected = []
        for chain_name in chain:
            if chain_name != active and chain_name not in affected:
                affected.append(chain_name)
        return tuple(affected)

    def _resolve_pronoun(match, text, active):
        word = match.group("pron").lower()
        if word in singular_pronouns:
            prior = _names_before(text, match.start())
            if prior:
                nearest = prior[-1]
                # Nearest-antecedent binding; the active player's own
                # anaphora is the active player's own act.
                return () if nearest == active else (nearest,)
            return _protected_others(active)
        if word in plural_pronouns:
            prior = _names_before(text, match.start())
            distinct = []
            for prior_name in prior:
                if prior_name != active and prior_name not in distinct:
                    distinct.append(prior_name)
            # A plural bound only by the active player is not plausibly
            # the active player alone; fall back to every protected
            # actor rather than let an unresolved plural slip through.
            return tuple(distinct) or _protected_others(active)
        # we / universal quantifiers bind beyond the speaker by
        # construction.
        return _protected_others(active)

    def _resolve_collective(match, text, active):
        return _protected_others(active)

    def _resolve_possessive(match, text, active):
        pname = match.group("pname")
        return () if pname == active else (pname,)

    def _resolve_by_agent(match, text, active):
        bname = match.group("bname")
        return () if bname == active else (bname,)

    verb_rules = (
        (named_pattern, _resolve_named),
        (pronoun_pattern, _resolve_pronoun),
        (collective_pattern, _resolve_collective),
    )
    nominal_rules = (
        (possessive_pattern, _resolve_possessive),
        (by_agent_pattern, _resolve_by_agent),
    )

    def _attribution_segment_end(match, text) -> int:
        # Upstream defines no closing delimiter for an attributed
        # segment: everything after the marker up to the next line
        # break (or end of text) is the named actor's claimed content.
        cut = text.find("\n", match.end())
        return len(text) if cut == -1 else cut

    def _scan(pattern, resolve, text, active, frame_words,
              span_end_fn=None):
        findings = []
        pos = 0
        while True:
            match = pattern.search(text, pos)
            if match is None:
                return findings
            lead_word, lead_start = _word_before_span(text, match.start())
            before_that = (_word_before(text, lead_start)
                           if lead_word == "that" else "")
            suppressed = (
                lead_word in frame_words
                or lead_word in _STANCE_VERBS
                or before_that in _STANCE_VERBS)
            affected = () if suppressed else resolve(match, text, active)
            if not affected:
                # Not a violation AT THIS START (suppressed frame, the
                # active player's own act, or nobody to protect) -- but
                # a greedy match that began at a non-agent ("... to X,
                # and X agrees") may still CONTAIN the real clause
                # subject, so resume just past the start, not past the
                # whole match.
                pos = match.start() + 1
                continue
            findings.append(_Finding(
                start=match.start(),
                end=match.end(),
                affected=affected,
                borderline=lead_word in _BORDERLINE_LEAD_WORDS,
                span_end=(None if span_end_fn is None
                          else span_end_fn(match, text)),
            ))
            pos = match.end()

    def _detect(event_statement: str, active_player_name: str) -> list:
        findings = []
        # Class 6 first: an attribution marker claims everything after
        # it, so its span subsumes any verb/nominal finding inside.
        findings.extend(_scan(attribution_pattern, _resolve_named,
                              event_statement, active_player_name,
                              _NON_AGENT_LEAD_WORDS,
                              span_end_fn=_attribution_segment_end))
        for pattern, resolve in verb_rules:
            findings.extend(_scan(pattern, resolve, event_statement,
                                  active_player_name,
                                  _NON_AGENT_LEAD_WORDS))
        for pattern, resolve in nominal_rules:
            findings.extend(_scan(pattern, resolve, event_statement,
                                  active_player_name,
                                  _NOMINAL_FRAME_WORDS))
        findings.sort(key=lambda finding: (finding.start, finding.end))
        return findings

    def _rewrite(event_statement: str, findings: list) -> str:
        spans = [( _clause_start(event_statement, finding.start),
                   finding.span_end if finding.span_end is not None
                   else _sentence_end(event_statement, finding.end))
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
