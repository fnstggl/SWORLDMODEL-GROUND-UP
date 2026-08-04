"""POST-HOC measurement audit -- written AFTER reading the transcripts.

Experiment-only, and deliberately kept OUT of the declared evaluator.

The declared predicates in :mod:`predicates` were frozen before the run
and are what actually measured both scenarios.  Reading the recorded
transcripts afterwards showed the declared pattern set is
under-inclusive: it misses plain acceptances such as "I'll give you 20
minutes on Thursday" and "Thursday works", and it misses engagement
expressed as a bare request for data ("Send me the replay logs and the
failure cases").

Two honest options existed: change the evaluator and re-run, or leave the
measured run exactly as it ran and publish a labelled second reading.
Re-running after seeing the outcomes would be tuning the evaluator to the
result, so this module takes the second option.

**Nothing here is an independent measurement of this run.**  These
patterns were written with the transcripts in front of the author.  They
answer only: "how much of the declared evaluator's reading was an artifact
of pattern coverage?"  Treat the numbers as a bound on evaluator
fragility, never as an outcome.
"""

from __future__ import annotations

import re

from .predicates import (first_match, own_turn_content,  # noqa: F401
                         recipient_turns)

AUDIT_VERSION = "post_hoc_measurement_audit_v1"

WRITTEN_AFTER_SEEING_THE_TRANSCRIPTS = True

#: broader acceptance forms observed in the recorded transcripts, plus the
#: obvious neighbours of each
BROAD_AGREEMENT_PATTERNS = (
    r"\b(?:i(?:'|’)?ll|i\s+will)\s+give\s+you\s+(?:\d+|twenty|ten|"
    r"fifteen|thirty)\s*(?:minutes|min)\b",
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"next\s+week|this\s+week|tomorrow)\s+works\b",
    r"\bhappy\s+to\s+(?:talk|take\s+the\s+call|speak|chat|connect)\b",
    r"\bsend\s+(?:me\s+)?(?:a\s+)?calendar\s+invite\b",
    r"\bblock(?:ing|s|ed)?\s+it\s+on\s+(?:his|my|the)\s+calendar\b",
    r"\bschedules?\s+the\s+(?:\d+|twenty)[-\s]*minute\s+call\b",
    r"\b(?:let(?:'|’)?s|let us)\s+(?:do|set up|schedule|book|find|grab)\b",
    r"\byes\b[^.!?]{0,80}\b(?:call|talk|speak|conversation)\b",
)

#: acceptance that is CONDITIONAL on something the sender must still do
CONDITIONAL_MARKERS = (
    r"\bif\s+the\s+data\s+holds\s+up\b",
    r"\bif\s+(?:it|they|the\s+\w+)\s+(?:holds?|checks?\s+out|survives?)\b",
    r"\bbefore\s+(?:the\s+call|then)\b",
    r"\bsend\s+me\s+the\b",
)

#: substantive engagement short of any acceptance
BROAD_ENGAGEMENT_PATTERNS = (
    r"\bsend\s+me\s+the\b",
    r"\bshare\s+the\b",
    r"\b(?:replay\s+logs?|failure\s+cases?|architecture\s+doc|"
    r"replay-test\s+data|memo)\b",
    r"\binterest(?:ed|ing)\b",
    r"\bcurious\b",
    r"\bintrigu\w+",
    r"\b(?:poke\s+holes|come\s+with\s+questions|scrutin\w+)\b",
)

_COMPILED = {
    "broad_agreement": tuple((p, re.compile(p, re.IGNORECASE))
                             for p in BROAD_AGREEMENT_PATTERNS),
    "conditional": tuple((p, re.compile(p, re.IGNORECASE))
                         for p in CONDITIONAL_MARKERS),
    "broad_engagement": tuple((p, re.compile(p, re.IGNORECASE))
                              for p in BROAD_ENGAGEMENT_PATTERNS),
}


def _match(kind, text):
    for pattern, compiled in _COMPILED[kind]:
        found = compiled.search(text or "")
        if found:
            return {"pattern": pattern, "matched_text": found.group(0)}
    return None


def audit_branch(event_trace, recipient_name, declared_metrics) -> dict:
    """A second reading of ONE branch's committed trace.

    Same attribution anchor as the declared evaluator (only the
    recipient's own committed turns are read); only the pattern set is
    broader.
    """
    turns = recipient_turns(event_trace, recipient_name)
    per_turn = []
    for turn in turns:
        content = turn["content"]
        per_turn.append({
            "index": turn["index"],
            "content": content,
            "broad_agreement": _match("broad_agreement", content),
            "conditional_marker": _match("conditional", content),
            "broad_engagement": _match("broad_engagement", content),
            "declared_agreement": first_match("agreement", content),
            "declared_engagement": first_match("engagement", content),
            "declared_decline": first_match("decline", content),
        })
    broad_agreed = any(entry["broad_agreement"] for entry in per_turn)
    conditional = any(entry["broad_agreement"] and
                      entry["conditional_marker"] for entry in per_turn)
    broad_engaged = any(entry["broad_engagement"] or
                        entry["broad_agreement"] for entry in per_turn)
    declared_agreed = bool(declared_metrics.get("call_agreed"))
    declared_positive = bool(declared_metrics.get("positive_reply"))
    return {
        "recipient_turns": per_turn,
        "audit_reading": {
            "any_acceptance_form": broad_agreed,
            "acceptance_was_conditional": conditional,
            "any_substantive_engagement": broad_engaged,
        },
        "declared_reading": {
            "call_agreed": declared_agreed,
            "positive_reply": declared_positive,
        },
        "disagreement": {
            "acceptance": broad_agreed != declared_agreed,
            "engagement": broad_engaged != declared_positive,
        },
    }


def audit_scenario(branch_audits) -> dict:
    disagreements = sum(
        1 for entry in branch_audits.values()
        if entry["disagreement"]["acceptance"]
        or entry["disagreement"]["engagement"])
    return {
        "audit_version": AUDIT_VERSION,
        "written_after_seeing_the_transcripts":
            WRITTEN_AFTER_SEEING_THE_TRANSCRIPTS,
        "status": "NOT AN INDEPENDENT MEASUREMENT OF THIS RUN",
        "purpose": ("bound how much of the declared evaluator's reading "
                    "was an artifact of pattern coverage"),
        "branches": branch_audits,
        "branches_where_the_two_readings_disagree": disagreements,
        "branch_count": len(branch_audits),
    }
