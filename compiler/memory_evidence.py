"""Mode B: question-only compilation, no search.

A separate model-memory stage drafts an evidence package in exactly the
same format the frozen packages use, so the compiler architecture does not
change at all. Every claim it produces is marked model_memory_unverified
-- these runs test compiler universality and robustness, not factual
reliability, and must never be presented as verified forecasts. Live
retrieval will later produce the same package format the same way.
"""
from __future__ import annotations

from .errors import InsufficientEvidence, SemanticAmbiguity
from .llm import TruncatedResponse, call_json

_SYSTEM = (
    "You draft an evidence package for a social-simulation compiler, from "
    "your own knowledge only. Every claim you write will be marked "
    "model_memory_unverified -- so write only things you genuinely "
    "believe you know, at the granularity the question needs: who the "
    "real participants and organizations are, their real schedules, "
    "cadences, capacities, procedures and constraints. Do NOT invent "
    "specific people, meetings, votes or numbers you do not actually "
    "know; write fewer, honest claims instead. If you know essentially "
    "nothing usable about the situation, return "
    "{\"insufficient\": \"<why>\"}.\n"
    "Return JSON: {\"claims\": [{\"id\": \"m1\"..., \"claim\": one "
    "factual sentence, \"source\": \"model memory\", \"as_of\": your "
    "best-known date for it, \"visibility\": \"public\"|\"private\"}]}. "
    "Ids are m1, m2, ... in order. No other fields, no nested objects."
)


def draft_memory_evidence(question: dict, call=call_json,
                          model: str = "deepseek-chat") -> tuple:
    """Returns (evidence_package, call_log). The package's claims all carry
    status model_memory_unverified regardless of what the model wrote."""
    user = ("QUESTION: " + str(question.get("question", ""))
            + ("\nDEADLINE: " + str(question["deadline"])
               if question.get("deadline") else "")
            + ("\nRESOLUTION NOTE: " + str(question["resolution_note"])
               if question.get("resolution_note") else ""))
    try:
        doc, raw, usage = call(_SYSTEM, user, model=model)
    except (TruncatedResponse, ValueError) as exc:
        raise SemanticAmbiguity(
            f"the memory-evidence draft was unusable: {exc}",
            {"document": "memory_evidence"})
    log = [{"step": "memory_evidence", "attempt": 0,
            "prompt": {"system": _SYSTEM, "user": user},
            "raw_response": raw, "usage": usage}]
    if isinstance(doc, dict) and doc.get("insufficient"):
        raise InsufficientEvidence(
            "the model declares it knows too little to draft evidence: "
            + str(doc["insufficient"]), {"mode": "question_only"})
    claims = []
    for i, c in enumerate(doc.get("claims") or []):
        text = str(c.get("claim") or "").strip()
        if not text:
            continue
        claims.append({
            "id": f"m{i + 1}",
            "claim": text,
            "source": "model memory (unverified)",
            "as_of": str(c.get("as_of") or "unknown"),
            "status": "model_memory_unverified",
            "visibility": c.get("visibility", "public")})
    if not claims:
        raise InsufficientEvidence(
            "the memory-evidence draft contained no usable claims",
            {"mode": "question_only"})
    return {"claims": claims, "mode": "question_only",
            "warning": "every claim is model_memory_unverified; this run "
                       "tests compiler universality, not factual "
                       "reliability"}, log
