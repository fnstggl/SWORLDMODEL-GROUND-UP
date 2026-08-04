"""Experiment-owned, attribution-anchored outcome predicates.

Experiment-only: this scenario's vocabulary lives here, never in
``sworldmodel/``.

Anchoring
---------
Every predicate reuses the repository's attribution anchor
(``tests/engine_individual/individual_helpers.leading_attribution``,
closed under phases 8-11 review finding F1): a committed row counts only
when it carries the upstream resolved-actor-turn wrapper AND the row's
OWN leading ``Name:`` attribution names the actor the predicate is about,
AND the pattern occurs in THAT actor's attributed content.

Consequence, which is the point of the experiment: success can only be
read off the recipient's own committed turn.  Delivery of the message,
the recipient opening it, game-master narration asserting an outcome,
another actor paraphrasing the recipient, and any evaluator inference all
fail the anchor and are not counted.

Measurement honesty
-------------------
Agreement is measured by explicit surface patterns over free live-model
text.  That is a real limitation and it is reported: a recipient who
agrees in wording no pattern covers is scored ``cutoff``, not success.
Every reading therefore also carries, in the evaluator ledger, the exact
recipient turns that were scanned and the exact pattern that matched --
so a human can check the verdict against the transcript.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _load_anchor():
    """Reuse the repository's attribution-anchor helper (single source of
    truth); it lives in the individual-slice suite.

    Where the engine environment is absent the anchor is unavailable and
    every predicate raises rather than silently measuring with a
    different anchor.
    """
    root = Path(__file__).resolve().parent.parent.parent
    for extra in (root / "tests" / "engine_individual",
                  root / "tests" / "engine_counterfactuals",
                  root / "tests" / "engine_baseline"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    try:
        from individual_helpers import (ACTOR_TURN_ANCHOR,
                                        leading_attribution)
    except ImportError:
        def leading_attribution(description):  # noqa: D401
            raise ImportError(
                "the attribution anchor lives in the individual-slice "
                "suite and needs the pinned engine environment "
                "(Python >= 3.12 with gdm-concordia)")

        return None, leading_attribution
    return ACTOR_TURN_ANCHOR, leading_attribution


ACTOR_TURN_ANCHOR, leading_attribution = _load_anchor()

from sworldmodel.outcomes.metrics import (WHOLE_TRACE_CITATION,  # noqa: E402
                                          event_description,
                                          matching_indices)

#: EXPLICIT agreement to speak / acceptance of the call / a direct
#: instruction to schedule it.  Applied only to the recipient's own
#: attributed content, case-insensitively.
AGREEMENT_PATTERNS = (
    r"\byes\b[^.!?]{0,80}\b(?:call|talk|speak|conversation|twenty|20)\b",
    r"\b(?:happy|glad|willing|open|delighted)\s+to\s+(?:talk|speak|chat|"
    r"connect|do\s+(?:a|the)\s+call|take\s+(?:a|the)\s+call|hop\s+on)",
    r"\bi(?:'|’)?(?:ll| will)\s+(?:take|do|join|make time for)\s+"
    r"(?:the|a|that|this)\s*(?:20|twenty)?[-\s]*(?:minute\s*)?"
    r"(?:call|conversation|chat)",
    r"\b(?:let(?:'|’)?s|let us)\s+(?:do|set up|schedule|book|find|grab)\b",
    r"\b(?:schedule|book|set up|arrange)\s+(?:the|a|this|that)\s*"
    r"(?:20|twenty)?[-\s]*(?:minute\s*)?(?:call|conversation|chat|time|"
    r"slot)",
    r"\b(?:send|share)\s+(?:me\s+)?(?:your\s+|some\s+|a\s+few\s+)?"
    r"(?:times|availability|calendar|slots|windows)\b",
    r"\bagree[sd]?\s+to\s+(?:a|the)\s*(?:20|twenty)?[-\s]*"
    r"(?:minute\s*)?(?:call|conversation|chat)",
    r"\baccept[sd]?\s+(?:the|a)\s*(?:20|twenty)?[-\s]*"
    r"(?:minute\s*)?(?:call|conversation|chat|invitation)",
    r"\b(?:my|his)\s+assistant\s+will\s+(?:reach out|follow up|"
    r"schedule|be in touch)",
    r"\b(?:put|get)\s+(?:it|something|time)\s+on\s+(?:the|my)\s+"
    r"calendar\b",
)

#: EXPLICIT refusal.
DECLINE_PATTERNS = (
    r"\bdeclin\w+",
    r"\b(?:pass(?:es|ed|ing)?)\s+on\b",
    r"\bnot\s+interested\b",
    r"\bno,?\s+(?:thank|thanks)\b",
    r"\b(?:won(?:'|’)?t|will\s+not)\s+(?:be\s+)?(?:taking|take|do|doing|"
    r"schedul\w+|meet\w*)\b",
    r"\b(?:can(?:'|’)?t|cannot|unable\s+to)\s+(?:take|do|make|schedule|"
    r"commit\s+to)\b[^.!?]{0,40}\b(?:call|conversation|chat|meeting)",
    r"\bnot\s+(?:a\s+fit|the\s+right|able\s+to\s+take)\b",
    r"\bdoes\s+not\s+(?:agree|accept)\b",
    r"\bno\s+(?:call|conversation|meeting)\b",
)

#: Substantive engagement short of agreement (used by ``positive_reply``).
ENGAGEMENT_PATTERNS = (
    r"\b(?:send|share|forward)\b[^.!?]{0,60}\bmemo\b",
    r"\binterest(?:ed|ing)\b",
    r"\bcurious\b",
    r"\bintrigu\w+",
    r"\bworth\s+(?:a|the)\s+(?:look|read|conversation|call)\b",
    r"\b(?:tell|show)\s+me\s+more\b",
    r"\bwhat\s+(?:is|are|was|were|does|do|happens?)\b[^?]{0,160}\?",
    r"\bhow\s+(?:did|does|do|much|many)\b[^?]{0,160}\?",
    r"\bwhy\s+(?:is|are|does|do|did)\b[^?]{0,160}\?",
)

_COMPILED = {
    "agreement": tuple((p, re.compile(p, re.IGNORECASE))
                       for p in AGREEMENT_PATTERNS),
    "decline": tuple((p, re.compile(p, re.IGNORECASE))
                     for p in DECLINE_PATTERNS),
    "engagement": tuple((p, re.compile(p, re.IGNORECASE))
                        for p in ENGAGEMENT_PATTERNS),
}


def first_match(kind: str, text: str):
    """``(pattern, matched_text)`` of the first pattern of ``kind`` that
    matches ``text``, or ``None``."""
    for pattern, compiled in _COMPILED[kind]:
        found = compiled.search(text or "")
        if found:
            return pattern, found.group(0)
    return None


def own_turn_content(description: str, actor_name: str):
    """The actor's OWN attributed content in this committed row, or
    ``None`` when the row is not that actor's resolved turn."""
    parsed = leading_attribution(description)
    if parsed is None:
        return None
    name, content = parsed
    if name != actor_name:
        return None
    return content


def recipient_turns(event_trace, actor_name) -> list:
    """Every committed row that is the named actor's own resolved turn,
    as ``{index, event_id, content}`` -- the exact scan set the metrics
    below reason over, preserved in the evaluator ledger."""
    turns = []
    for index, entry in enumerate(event_trace):
        description = event_description(entry)
        content = own_turn_content(description, actor_name)
        if content is None:
            continue
        event_id = getattr(entry, "event_id", None)
        if event_id is None and isinstance(entry, dict):
            event_id = entry.get("event_id")
        turns.append({"index": index, "event_id": event_id,
                      "content": content})
    return turns


def _own_turn_matcher(actor_name: str, kind: str, *, forbid=()):
    """Matcher: the row is ``actor_name``'s own resolved turn AND its
    attributed content matches ``kind``, and matches none of ``forbid``.
    """

    def matcher(description: str) -> bool:
        content = own_turn_content(description, actor_name)
        if content is None:
            return False
        if first_match(kind, content) is None:
            return False
        return all(first_match(other, content) is None for other in forbid)

    matcher.actor_name = actor_name
    matcher.kind = kind
    matcher.forbid = tuple(forbid)
    return matcher


def _exists(matcher):
    def predicate(event_trace, result_dict):
        del result_dict
        matched = matching_indices(event_trace, matcher)
        if matched:
            return True, matched
        return False, (WHOLE_TRACE_CITATION,)

    predicate.matcher = matcher
    return predicate


def _absent(matcher):
    """True when NOTHING matched (citing the scanned bound), False with
    the offending rows cited."""

    def predicate(event_trace, result_dict):
        del result_dict
        matched = matching_indices(event_trace, matcher)
        if matched:
            return False, matched
        return True, (WHOLE_TRACE_CITATION,)

    predicate.matcher = matcher
    return predicate


def _positive_matcher(actor_name: str):
    """The recipient's own turn showing agreement OR substantive
    engagement, and no explicit decline in the same turn."""

    def matcher(description: str) -> bool:
        content = own_turn_content(description, actor_name)
        if content is None:
            return False
        if first_match("decline", content) is not None:
            return False
        return (first_match("agreement", content) is not None
                or first_match("engagement", content) is not None)

    matcher.actor_name = actor_name
    matcher.kind = "positive_reply"
    return matcher


def build_predicates(recipient_name: str) -> dict:
    """The declared metric predicates, bound to the compiled cast's
    recipient NAME (resolved from the compiled world at run time -- never
    assumed)."""
    if not isinstance(recipient_name, str) or not recipient_name.strip():
        raise ValueError("recipient_name must be the compiled actor name")
    agreement = _own_turn_matcher(recipient_name, "agreement",
                                  forbid=("decline",))
    decline = _own_turn_matcher(recipient_name, "decline")
    return {
        "call_agreed": _exists(agreement),
        "positive_reply": _exists(_positive_matcher(recipient_name)),
        "no_explicit_decline": _absent(decline),
        # not declared in the evaluator spec; used by the status rule and
        # the ledger to distinguish "declined" from "never answered"
        "_explicit_decline": _exists(decline),
    }


def declared_predicates(recipient_name: str) -> dict:
    """Only the metrics the evaluator spec declares."""
    everything = build_predicates(recipient_name)
    return {name: predicate for name, predicate in everything.items()
            if not name.startswith("_")}


def status_rule(metric_values, default_status):
    """Terminal-status verdict from the declared metrics only.

    ``call_agreed`` -> success; an explicit decline (the inverse of
    ``no_explicit_decline``) -> failure; neither by the cutoff -> keep the
    runner's default (``cutoff`` when the step budget was exhausted,
    ``incomplete`` for a technical stop).  R3: the engine never decides
    success or failure itself.
    """
    del default_status
    if metric_values["call_agreed"].value:
        return "success"
    if not metric_values["no_explicit_decline"].value:
        return "failure"
    return None


def explain_metrics(event_trace, recipient_name: str) -> dict:
    """Full human-checkable explanation of every reading: the exact rows
    scanned, and for each metric the pattern that matched (if any)."""
    turns = recipient_turns(event_trace, recipient_name)
    explanation = {
        "recipient_name": recipient_name,
        "anchor": ACTOR_TURN_ANCHOR,
        "committed_rows_scanned": len(list(event_trace)),
        "recipient_own_turns": turns,
        "per_metric": {},
    }
    for metric, kind in (("call_agreed", "agreement"),
                         ("_explicit_decline", "decline")):
        hits = []
        for turn in turns:
            found = first_match(kind, turn["content"])
            if found is None:
                continue
            if kind == "agreement" \
                    and first_match("decline", turn["content"]) is not None:
                continue
            hits.append({"index": turn["index"], "pattern": found[0],
                         "matched_text": found[1]})
        explanation["per_metric"][metric] = {
            "pattern_kind": kind, "hits": hits, "value": bool(hits)}
    positive_hits = []
    for turn in turns:
        if first_match("decline", turn["content"]) is not None:
            continue
        found = (first_match("agreement", turn["content"])
                 or first_match("engagement", turn["content"]))
        if found is not None:
            positive_hits.append({"index": turn["index"],
                                  "pattern": found[0],
                                  "matched_text": found[1]})
    explanation["per_metric"]["positive_reply"] = {
        "pattern_kind": "agreement_or_engagement", "hits": positive_hits,
        "value": bool(positive_hits)}
    explanation["per_metric"]["no_explicit_decline"] = {
        "pattern_kind": "decline (inverted)",
        "hits": explanation["per_metric"]["_explicit_decline"]["hits"],
        "value": not explanation["per_metric"]["_explicit_decline"]["value"]}
    return explanation
