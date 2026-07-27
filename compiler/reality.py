"""The independent causal-reality review of the canonical world.

The reviewer never sees a giant hand-authored runtime document: it sees
the deterministic rendering of the canonical graph -- the compiled
structure itself -- next to the question and the complete evidence, plus
what the backward and forward proofs established mechanically. It judges
reality, in the directive's order:

  1. terminal faithful to the question;  2. spine complete;
  3. right producers;                    4. materially missing actors;
  5. decorative inclusions;              6. unsupported claims as verified;
  7. uncertainty preserved;              8. exclusions causally safe;
  9. terminal can emerge from the trajectory, not initialization.

(Point 10, round-trip preservation, is the separate post-lowering
equivalence review.)

Verdicts: APPROVE; TARGETED_REVISION with exact defects, each naming the
discovery document that owns it; REJECT_INSUFFICIENT_EVIDENCE;
REJECT_WRONG_WORLD. One targeted revision round per document, then the
world stands or falls as reviewed -- never rerolled.
"""
from __future__ import annotations

import json

from .discovery import render_evidence, render_question
from .errors import (InsufficientEvidence, RealityReviewRejected,
                     SemanticAmbiguity)
from .llm import TruncatedResponse, call_json
from .roundtrip import describe_graph

VERDICTS = ("APPROVE", "TARGETED_REVISION", "REJECT_INSUFFICIENT_EVIDENCE",
            "REJECT_WRONG_WORLD")

DOCUMENTS = ("resolution_contract", "causal_spine", "producer_assignments",
             "starting_state_and_information", "uncertainty_and_exclusions")

_SYSTEM = (
    "You are the independent causal-reality reviewer of a compiled world. "
    "You receive a question, the COMPLETE frozen evidence, the compiled "
    "world's structure, and what its mechanical proofs established. Judge "
    "whether this world is a truthful, causally complete account of the "
    "real situation -- not whether it is well formatted.\n"
    "Judge in this order:\n"
    "1. Is the terminal faithful to the question and its resolution note?\n"
    "2. Is the backward causal chain complete -- no missing necessary "
    "step between the world's start and the terminal?\n"
    "3. Are the correct producers attached -- the people, schedules and "
    "processes the evidence actually supports?\n"
    "4. Is any materially important actor or process missing?\n"
    "5. Is anything included that is decorative -- unable to affect the "
    "answer?\n"
    "6. Is any claim treated as verified that the evidence does not "
    "state?\n"
    "7. Is real uncertainty preserved rather than silently resolved? A "
    "world may legitimately reach its cutoff unresolved; a committed, "
    "evidenced future event is a correct scheduled event, and an actor's "
    "open choice must appear as an available action, never as a "
    "schedule.\n"
    "8. Are the declared exclusions causally safe?\n"
    "9. Can the terminal emerge from what happens after genesis, rather "
    "than from initialization?\n"
    "Judge the single best-supported reading of the evidence; residual "
    "uncertainty belongs in the uncertainty section, not in extra "
    "branches. The terminal's reading of the question was settled by an "
    "adjudicated resolution step: challenge it ONLY by quoting the exact "
    "clause of the resolution note it contradicts. The runtime enforces "
    "stock physics itself -- a transfer cannot move stock that is not "
    "there, and processes accrue on real calendars -- so do not demand "
    "explicit checker or comparison mechanisms for what the physics "
    "already enforces.\n"
    "Return JSON exactly: {\"verdict\": \"APPROVE\" | "
    "\"TARGETED_REVISION\" | \"REJECT_INSUFFICIENT_EVIDENCE\" | "
    "\"REJECT_WRONG_WORLD\", \"reasoning\": a short paragraph, "
    "\"causal_path\": [the steps of the best-supported route to the "
    "terminal, one line each], \"defects\": [{\"document\": one of "
    + json.dumps(list(DOCUMENTS)) + ", \"what\": the exact defect, "
    "\"why_material\": how it would change what the simulation "
    "produces}]}.\n"
    "Use TARGETED_REVISION only for defects that change what the "
    "simulation would produce, and name the document each belongs to. "
    "Use REJECT_INSUFFICIENT_EVIDENCE when no truthful world can be "
    "built from this evidence at all. Use REJECT_WRONG_WORLD when the "
    "world misdescribes the situation beyond targeted revision. "
    "APPROVE requires defects to be empty."
)


def review_reality(question: dict, evidence: dict, graph, backward: dict,
                   forward: dict, call=call_json,
                   model: str = "deepseek-chat", bindings=None) -> tuple:
    """Returns (result, log). The result's verdict is one of VERDICTS;
    defects (for TARGETED_REVISION) each name their discovery document."""
    proofs_note = {
        "backward": {
            "components_rooted_in_uncertainty":
                backward.get("components_rooted_in_uncertainty", []),
            "genesis_only_components":
                backward.get("genesis_only_components", []),
            "warnings": backward.get("warnings", [])},
        "forward": {"scheduled_roots": forward.get("scheduled_roots", []),
                    "warnings": forward.get("warnings", [])},
    }
    user = (render_question(question) + "\n\n" + render_evidence(evidence)
            + "\n\n" + describe_graph(graph, question, bindings)
            + "\n\nWHAT THE MECHANICAL PROOFS ESTABLISHED:\n"
            + json.dumps(proofs_note, indent=1)
            + "\n\nNOTE: rates, latencies, durations and amounts are "
              "filled in AFTER this review by the binding stage; judge "
              "whether the RIGHT mechanisms exist and connect causally, "
              "not whether their numbers are attached yet. A route listed "
              "as dead (no sender) can carry nothing and is already "
              "flagged mechanically: it only matters if something in the "
              "causal chain depends on it.")
    try:
        doc, raw, usage = call(_SYSTEM, user, model=model)
    except (TruncatedResponse, ValueError) as exc:
        raise RealityReviewRejected(
            f"the reality review reply was unusable: {exc}")
    log = [{"step": "reality_review", "attempt": 0,
            "prompt": {"system": _SYSTEM, "user": user},
            "raw_response": raw, "usage": usage}]
    verdict = (doc or {}).get("verdict")
    if verdict not in VERDICTS:
        raise RealityReviewRejected(
            f"the reality review returned no usable verdict ({verdict!r})",
            {"raw": str(doc)[:400]})
    defects = []
    for d in doc.get("defects") or []:
        entry = {"document": d.get("document"),
                 "what": str(d.get("what", "")),
                 "why_material": str(d.get("why_material", ""))}
        if entry["document"] not in DOCUMENTS:
            entry["document"] = "causal_spine"
        defects.append(entry)
    result = {"verdict": verdict,
              "reasoning": str(doc.get("reasoning", "")),
              "causal_path": [str(s) for s in doc.get("causal_path") or []],
              "defects": defects}
    return result, log


def raise_for(result: dict) -> None:
    """Convert a rejecting verdict into its exact compilation stop.

    A REJECT_WRONG_WORLD whose every finding names the document that owns
    it is, in substance, a targeted revision -- the reviewer judged the
    defects revisable by enumerating them. It is downgraded to one
    revision round (logged); a second rejection stands."""
    if result["verdict"] == "REJECT_INSUFFICIENT_EVIDENCE":
        raise InsufficientEvidence(
            result["reasoning"] or "the evidence cannot support a truthful "
            "world", {"review": result, "declared_by": "reality reviewer"})
    if result["verdict"] == "REJECT_WRONG_WORLD" and result["defects"]:
        result = dict(result, downgraded_from="REJECT_WRONG_WORLD")
        raise SemanticAmbiguity(
            "the reality review found document-tagged defects "
            "(REJECT_WRONG_WORLD downgraded to one targeted revision)",
            {"review": result, "repairable": True,
             "defects": [f"[{d['document']}] {d['what']} -- "
                         f"{d['why_material']}" for d in result["defects"]]})
    if result["verdict"] == "REJECT_WRONG_WORLD":
        raise RealityReviewRejected(
            result["reasoning"] or "the world misdescribes the situation",
            {"review": result})
    if result["verdict"] == "TARGETED_REVISION":
        raise SemanticAmbiguity(
            "the reality review requires targeted revision",
            {"review": result, "repairable": True,
             "defects": [f"[{d['document']}] {d['what']} -- "
                         f"{d['why_material']}" for d in result["defects"]]})
