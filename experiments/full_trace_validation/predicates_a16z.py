"""Experiment-owned, attribution-anchored predicates for the a16z run.

Experiment-only: this scenario's vocabulary lives here, never in
``sworldmodel/``.

Anchoring
---------
Every textual predicate reuses the repository's attribution anchor (see
:mod:`predicates`): a committed row counts only when it carries the
upstream resolved-actor-turn wrapper AND the row's OWN leading ``Name:``
attribution names the actor the predicate is about, AND the pattern
occurs in THAT actor's attributed content.  Game-master narration, one
actor paraphrasing another, and any evaluator inference all fail the
anchor and are not counted.

The declared primary metric
---------------------------
``valid_offer_accepted`` is a CONJUNCTION over three separately anchored
readings, in the order the user's success criteria require:

1. the People and Compensation Partner's own committed turn authorizes
   the compensation (and does not refuse it in the same turn);
2. the New Media Hiring Lead's own committed turn issues the offer (and
   does not withhold it in the same turn);
3. Richard Zheng's OWN committed turn accepts, at a strictly LATER trace
   position than both of the above, and without an explicit refusal or
   counter in the same turn.

Only Richard's own turn can satisfy (3).  If the game master narrates his
acceptance, or the hiring lead reports it, the anchor rejects the row and
the metric stays false -- which is exactly the property the run is
supposed to test.

The declared secondary metric
-----------------------------
``salary_savings_vs_300k`` is CODE-OWNED.  Its value comes from the
user's own mapping applied to the branch's DECLARED candidate, never from
model text, never from the trace.  The contract requires every metric to
carry a citation, so it cites the scan bound (the terminal-state key
recording the size of the committed stream); the evaluator ledger records
in words that the value was not derived from any event.

Measurement honesty
-------------------
Acceptance, approval, offer issuance and refusal are read by explicit
surface patterns over free live-model text.  That is a real limitation
and it is reported: an actor who accepts in wording no pattern covers is
scored as not accepting.  Every reading carries, in the evaluator ledger,
the exact turns scanned and the exact pattern that matched, so a human
can check the verdict against the transcript.
"""

from __future__ import annotations

import re

from sworldmodel.outcomes.metrics import (WHOLE_TRACE_CITATION,
                                          event_description)

from .predicates import (ACTOR_TURN_ANCHOR,  # noqa: F401
                         own_turn_content, recipient_turns)

#: the compensation approver's own authorization of the terms
APPROVAL_PATTERNS = (
    r"\bapprov\w+",
    r"\bauthori[sz]\w+",
    r"\bsigns?\s+off\b|\bsigned\s+off\b",
    r"\bgreen[-\s]?light\w*",
    r"\bclears?\b[^.!?]{0,40}\b(?:offer|package|compensation|salary|comp|"
    r"band|terms)\b",
    r"\bcleared\b[^.!?]{0,40}\b(?:offer|package|compensation|salary|comp|"
    r"band|terms)\b",
    r"\bconfirms?\b[^.!?]{0,40}\b(?:the\s+)?(?:offer|package|compensation|"
    r"salary)\b[^.!?]{0,40}\b(?:is|are)\s+(?:within|inside|acceptable|"
    r"approved)\b",
)

#: the compensation approver REFUSING in the same turn
APPROVAL_REFUSAL_PATTERNS = (
    r"\b(?:does\s+not|do\s+not|cannot|can\s?not|can(?:'|’)t|will\s+not|"
    r"won(?:'|’)t)\s+(?:approve|authori[sz]e|sign\s+off|clear)\b",
    r"\b(?:declines?|declined|refuses?|refused|rejects?|rejected|denies|"
    r"denied|withholds?|withheld|blocks?|blocked|vetoe?s?|vetoed)\b"
    r"[^.!?]{0,50}\b(?:approval|authori[sz]ation|offer|package|"
    r"compensation|salary|request)\b",
    r"\bnot\s+approved?\b",
    r"\bapproval\s+is\s+(?:withheld|denied|refused)\b",
    r"\bcannot\s+be\s+approved\b",
)

#: the hiring lead ISSUING the offer
OFFER_ISSUE_PATTERNS = (
    r"\b(?:issues?|issued|issuing|extends?|extended|extending|sends?|sent|"
    r"sending|presents?|presented|presenting|makes?|made|making|delivers?|"
    r"delivered|delivering|conveys?|conveyed)\b[^.!?]{0,70}\boffer\b",
    r"\boffers?\b[^.!?]{0,70}\b(?:the\s+)?(?:role|position|job|package|"
    r"annual\s+base|base\s+salary)\b",
    r"\b(?:formal|written|verbal)\s+offer\b",
    r"\boffer\s+letter\b",
    r"\boffers?\s+(?:him|richard|richard\s+zheng)\b",
)

#: the hiring lead WITHHOLDING the offer in the same turn
OFFER_WITHHOLD_PATTERNS = (
    r"\b(?:does\s+not|do\s+not|will\s+not|won(?:'|’)t|cannot|can\s?not|"
    r"can(?:'|’)t)\s+(?:make|issue|extend|send|present|deliver)\b"
    r"[^.!?]{0,30}\boffer\b",
    r"\bno\s+offer\s+(?:is|will\s+be|has\s+been)\b",
    r"\b(?:withholds?|withheld|holds?\s+(?:back|off)|held\s+off|refrains?"
    r"\s+from|refrained\s+from|delays?|delayed|postpones?|postponed|"
    r"defers?|deferred)\b[^.!?]{0,40}\b(?:the\s+|an\s+|any\s+)?offer\b",
    r"\bwithout\s+(?:making|issuing|extending|sending)\s+(?:an?\s+)?offer\b",
    r"\bmakes?\s+no\s+offer\b",
)

#: Richard's OWN acceptance
ACCEPTANCE_PATTERNS = (
    r"\baccepts?\b[^.!?]{0,60}\b(?:offer|role|position|package|job|terms|"
    r"it)\b",
    r"\baccepted\b[^.!?]{0,60}\b(?:offer|role|position|package|job|terms)\b",
    r"\bi\s+accept\b",
    r"\bsigns?\s+(?:the\s+)?(?:offer|offer\s+letter|contract|agreement|"
    r"paperwork)\b",
    r"\b(?:will|agrees?\s+to)\s+(?:take|join|start)\b[^.!?]{0,40}"
    r"\b(?:role|position|job|offer|team)\b",
    r"\bsays?\s+yes\b[^.!?]{0,40}\b(?:offer|role|position|job)\b",
    r"\byes\b[^.!?]{0,30}\bi(?:'|’)?ll\s+(?:take|join)\b",
    r"\btakes?\s+the\s+(?:role|job|offer|position)\b",
)

#: Richard's OWN explicit refusal
REJECTION_PATTERNS = (
    r"\bdeclin\w+",
    r"\brejects?\b|\brejected\b",
    r"\bturns?\s+(?:it\s+|the\s+offer\s+)?down\b|\bturned\s+down\b",
    r"\bpass(?:es|ed)?\s+on\b",
    r"\bnot\s+accept\w*\b",
    r"\bno,?\s+thank\w*\b",
    r"\bwill\s+not\s+(?:take|join|accept|sign)\b",
    r"\bwon(?:'|’)t\s+(?:take|join|accept|sign)\b",
)

#: Richard's OWN counter / negotiation (recorded, not a declared metric)
COUNTER_PATTERNS = (
    r"\bcounter(?:s|ed|offer|-offer|\s+offer|proposal)\b",
    r"\bnegotiat\w+",
    r"\basks?\s+for\b[^.!?]{0,40}\b(?:more|higher|\$|equity|base)\b",
    r"\bpushes?\s+(?:back|for)\b",
    r"\bif\s+(?:the\s+)?(?:base|salary|number|package)\b[^.!?]{0,40}"
    r"\b(?:were|was|goes?|moved?|rose|increased)\b",
)

#: Richard's OWN delay / deferral (recorded, not a declared metric)
DELAY_PATTERNS = (
    r"\b(?:needs?|wants?|asks?\s+for|requests?)\b[^.!?]{0,25}\btime\b",
    r"\bthink\s+(?:it\s+)?(?:over|about\s+it)\b",
    r"\bgets?\s+back\s+to\s+(?:you|them|him|her)\b",
    r"\bdefers?\b|\bdeferred\b|\bholds?\s+off\b",
    r"\bsleep\s+on\s+it\b",
    r"\bby\s+(?:the\s+)?end\s+of\s+the\s+week\b",
)

_COMPILED = {
    "approval": APPROVAL_PATTERNS,
    "approval_refusal": APPROVAL_REFUSAL_PATTERNS,
    "offer_issue": OFFER_ISSUE_PATTERNS,
    "offer_withhold": OFFER_WITHHOLD_PATTERNS,
    "acceptance": ACCEPTANCE_PATTERNS,
    "rejection": REJECTION_PATTERNS,
    "counter": COUNTER_PATTERNS,
    "delay": DELAY_PATTERNS,
}
_COMPILED = {kind: tuple((pattern, re.compile(pattern, re.IGNORECASE))
                         for pattern in patterns)
             for kind, patterns in _COMPILED.items()}

PATTERN_KINDS = tuple(sorted(_COMPILED))


def first_match(kind: str, text: str):
    """``(pattern, matched_text)`` of the first pattern of ``kind`` that
    matches ``text``, or ``None``."""
    for pattern, compiled in _COMPILED[kind]:
        found = compiled.search(text or "")
        if found:
            return pattern, found.group(0)
    return None


def _hit(event_trace, actor_name, kind, forbid=()):
    """``(index, matched)`` of the FIRST row that is ``actor_name``'s own
    resolved turn and matches ``kind`` without matching ``forbid``."""
    for index, entry in enumerate(event_trace):
        content = own_turn_content(event_description(entry), actor_name)
        if content is None:
            continue
        found = first_match(kind, content)
        if found is None:
            continue
        if any(first_match(other, content) is not None for other in forbid):
            continue
        return index, {"index": index, "pattern": found[0],
                       "matched_text": found[1], "content": content}
    return None, None


def _all_hits(event_trace, actor_name, kind, forbid=()):
    hits = []
    for index, entry in enumerate(event_trace):
        content = own_turn_content(event_description(entry), actor_name)
        if content is None:
            continue
        found = first_match(kind, content)
        if found is None:
            continue
        if any(first_match(other, content) is not None for other in forbid):
            continue
        hits.append({"index": index, "pattern": found[0],
                     "matched_text": found[1]})
    return hits


def read_offer_chain(event_trace, *, approver_name, hiring_lead_name,
                     subject_name) -> dict:
    """The full authority chain reading for one branch's committed trace.

    Pure reading: computes the three anchored positions and the derived
    verdict, and returns everything a human needs to check it.
    """
    approval_index, approval = _hit(event_trace, approver_name, "approval",
                                    forbid=("approval_refusal",))
    offer_index, offer = _hit(event_trace, hiring_lead_name, "offer_issue",
                              forbid=("offer_withhold",))
    authorized_at = None
    if approval_index is not None and offer_index is not None:
        authorized_at = max(approval_index, offer_index)

    acceptance = None
    acceptance_index = None
    if authorized_at is not None:
        for index, entry in enumerate(event_trace):
            if index <= authorized_at:
                continue
            content = own_turn_content(event_description(entry),
                                       subject_name)
            if content is None:
                continue
            found = first_match("acceptance", content)
            if found is None:
                continue
            if first_match("rejection", content) is not None:
                continue
            acceptance_index = index
            acceptance = {"index": index, "pattern": found[0],
                          "matched_text": found[1], "content": content}
            break

    rejections = _all_hits(event_trace, subject_name, "rejection")
    return {
        "approver_name": approver_name,
        "hiring_lead_name": hiring_lead_name,
        "subject_name": subject_name,
        "compensation_authorized": approval,
        "offer_issued": offer,
        "authorization_complete_at_index": authorized_at,
        "approval_preceded_offer": (
            None if approval_index is None or offer_index is None
            else approval_index < offer_index),
        "subject_acceptance_after_authorization": acceptance,
        "subject_acceptance_index": acceptance_index,
        "subject_acceptance_anywhere": _all_hits(
            event_trace, subject_name, "acceptance", forbid=("rejection",)),
        "subject_rejections": rejections,
        "subject_counters": _all_hits(event_trace, subject_name, "counter"),
        "subject_delays": _all_hits(event_trace, subject_name, "delay"),
        "valid_offer_accepted": acceptance_index is not None,
    }


def valid_offer_accepted_predicate(*, approver_name, hiring_lead_name,
                                   subject_name):
    """The declared primary metric, bound to the compiled cast's names."""

    def predicate(event_trace, result_dict):
        del result_dict
        chain = read_offer_chain(event_trace, approver_name=approver_name,
                                 hiring_lead_name=hiring_lead_name,
                                 subject_name=subject_name)
        if not chain["valid_offer_accepted"]:
            return False, (WHOLE_TRACE_CITATION,)
        citations = (chain["compensation_authorized"]["index"],
                     chain["offer_issued"]["index"],
                     chain["subject_acceptance_after_authorization"]["index"])
        return True, tuple(sorted(set(citations)))

    predicate.metric = "valid_offer_accepted"
    return predicate


def salary_savings_predicate(savings_by_candidate_id):
    """The declared secondary metric: CODE-OWNED, never text-derived.

    The value is the user's own mapping applied to the branch's declared
    candidate.  The citation is the scan bound, because the value was not
    computed from any event -- recorded in words in the evaluator ledger
    so no reader can mistake it for a trace reading.
    """
    table = {str(key): float(value)
             for key, value in dict(savings_by_candidate_id).items()}

    def predicate(event_trace, result_dict):
        del event_trace
        candidate_id = result_dict.get("candidate_id")
        if candidate_id not in table:
            raise KeyError(
                f"no code-owned salary mapping for candidate "
                f"{candidate_id!r}; the mapping is declared before the run "
                "and may never be inferred")
        return table[candidate_id], (WHOLE_TRACE_CITATION,)

    predicate.metric = "salary_savings_vs_300k"
    predicate.table = dict(table)
    return predicate


def subject_rejection_hits(event_trace, subject_name) -> list:
    """Every row that is the subject's OWN turn carrying an explicit
    refusal.  Not a declared metric: the status rule uses it to tell an
    explicit refusal apart from silence."""
    return _all_hits(event_trace, subject_name, "rejection")


def declared_predicates(*, approver_name, hiring_lead_name, subject_name,
                        savings_by_candidate_id) -> dict:
    """Exactly the metrics the evaluator spec declares."""
    return {
        "valid_offer_accepted": valid_offer_accepted_predicate(
            approver_name=approver_name, hiring_lead_name=hiring_lead_name,
            subject_name=subject_name),
        "salary_savings_vs_300k": salary_savings_predicate(
            savings_by_candidate_id),
    }


#: the status rule in words, recorded verbatim in the evaluator ledger
STATUS_RULE_TEXT = (
    "valid_offer_accepted -> success; otherwise the subject's OWN "
    "explicit refusal -> failure; otherwise the runner's default (cutoff "
    "when the step budget was exhausted, incomplete for a technical "
    "stop). R3: the engine never decides success or failure itself.")


def make_status_rule(*, subject_rejected: bool):
    """Terminal-status verdict for ONE branch (see :data:`STATUS_RULE_TEXT`).

    The refusal reading is computed from that branch's own committed
    trace before evaluation and bound here, because the evaluator hands a
    status rule only the DECLARED metric values and the user's declared
    spec has exactly two metrics.
    """

    def status_rule(metric_values, default_status):
        del default_status
        if metric_values["valid_offer_accepted"].value:
            return "success"
        if subject_rejected:
            return "failure"
        return None

    status_rule.subject_rejected = bool(subject_rejected)
    return status_rule


def explain_metrics(event_trace, *, approver_name, hiring_lead_name,
                    subject_name, savings_value) -> dict:
    """Full human-checkable explanation of every reading: the exact turns
    scanned per actor, and for each metric how it was decided."""
    chain = read_offer_chain(event_trace, approver_name=approver_name,
                             hiring_lead_name=hiring_lead_name,
                             subject_name=subject_name)
    per_actor = {}
    for name in (approver_name, hiring_lead_name, subject_name):
        per_actor[name] = recipient_turns(event_trace, name)
    return {
        "anchor": ACTOR_TURN_ANCHOR,
        "committed_rows_scanned": len(list(event_trace)),
        "own_turns_by_actor": per_actor,
        "authority_chain": chain,
        "per_metric": {
            "valid_offer_accepted": {
                "value": chain["valid_offer_accepted"],
                "requires": (
                    "the compensation approver's own turn authorizes AND "
                    "the hiring lead's own turn issues the offer AND the "
                    "subject's own turn accepts at a strictly later trace "
                    "position"),
                "compensation_authorized": chain["compensation_authorized"],
                "offer_issued": chain["offer_issued"],
                "subject_acceptance":
                    chain["subject_acceptance_after_authorization"],
            },
            "salary_savings_vs_300k": {
                "value": savings_value,
                "source": ("CODE-OWNED: the user's declared mapping applied "
                           "to this branch's declared candidate. Not read "
                           "from the trace, not parsed from model text."),
            },
        },
    }


def authority_violation_scan(event_trace, *, subject_name,
                             protected_kinds=("acceptance", "rejection",
                                              "counter")) -> dict:
    """Did anything other than the subject's OWN turn commit the subject's
    voluntary decision?

    Scans every committed row whose leading attribution is NOT the subject
    (game-master narration and other actors' turns alike) for text that
    asserts the subject accepting, rejecting or countering.  A hit is a
    candidate authority violation and is reported verbatim; the guard
    ledger is the other half of the picture.
    """
    findings = []
    for index, entry in enumerate(event_trace):
        description = event_description(entry)
        own = own_turn_content(description, subject_name)
        if own is not None:
            continue
        if subject_name not in description:
            continue
        for kind in protected_kinds:
            found = first_match(kind, description)
            if found is None:
                continue
            findings.append({
                "index": index, "kind": kind, "pattern": found[0],
                "matched_text": found[1],
                "row_excerpt": description[:400],
                "note": ("this row names the subject and carries "
                         f"{kind} wording, but the row is NOT the "
                         "subject's own attributed turn; it can never "
                         "satisfy the primary metric")})
            break
    return {"subject_name": subject_name,
            "rows_scanned": len(list(event_trace)),
            "candidate_violations": findings,
            "candidate_violation_count": len(findings)}
