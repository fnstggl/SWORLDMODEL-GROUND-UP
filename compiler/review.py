"""Model call #2: independent reality review.

A separate call, given the question, the evidence and the proposed scenario,
whose only job is to judge whether that scenario is a truthful and sufficient
account of the real situation. The scenario's author does not certify its own
work, and the reviewer cannot edit anything -- it returns a verdict and exact
defects, and at most one targeted revision follows.
"""
from __future__ import annotations

import json

from .errors import RealityReviewRejected
from .llm import call_json

VERDICTS = ("APPROVE", "REVISE", "REJECT_INSUFFICIENT_EVIDENCE")

DEFECT_KINDS = (
    "missing_participant", "missing_external_process", "wrong_information_access",
    "unsupported_assumption", "missing_causal_link", "wrong_resolution_rule",
    "excessive_unnecessary_detail", "terminal_has_no_producer",
)

SYSTEM = """You are an independent reviewer. You did not build this world and you
must not defend it. Judge only whether the proposed scenario is a truthful,
sufficient account of the real situation described by the evidence.

Check, in order:
1. Is every important object either supported by the evidence or explicitly
   marked uncertain? Is anything asserted that the evidence CONTRADICTS or
   plainly does not support?
2. Was any participant, schedule, duration, rate, authority or consequence
   INVENTED -- present in the scenario but traceable to no claim, and not
   labelled "inferred" or "uncertain"?
3. Is any participant or external process missing WITHOUT WHICH the answer
   cannot be produced? Was all causally important evidence represented?
4. Does anyone know something they could not actually know, or fail to be
   given something they plainly would have?
5. Can the stated resolution actually be produced by TRAJECTORY EVENTS rather
   than by initialization? Trace the path explicitly. A terminal that is
   already true in starting_state is a defect.
6. Is this the SMALLEST causally sufficient world? Are the excluded actors and
   processes genuinely unable to change the answer?
7. Is unresolved uncertainty PRESERVED rather than forced to resolve? A
   scenario that quietly assumes an uncertain step happens, in order to make
   the question answerable, is defective. Leaving it uncertain -- so the run
   may end "unresolved" -- is correct.

=== WHAT THIS SIMULATION IS, SO YOU JUDGE IT ON ITS OWN TERMS ===
This run simulates ONE trajectory: the course of events best supported by the
evidence. Branching over alternative timelines is deliberately not part of it.

So the following are NOT defects, and you must not raise them as such:
- that a scheduled or committed future event "could slip". If the evidence
  says a party committed to a time, or documents their standing practice,
  taking them at their word is the best-supported reading. Real commitments
  are the correct basis for a scheduled event.
- that a person "might not" follow an attention or work pattern the evidence
  documents.
- that some other outcome is conceivable. Only ONE trajectory is being run.
Residual uncertainty of this kind belongs in the scenario's "uncertainties"
section. If it is material and the scenario has NOT recorded it there, that is
at most a MINOR defect ("record this uncertainty"), never critical or major.

Raise a CRITICAL or MAJOR defect only when the scenario would produce a WRONG
OR UNPRODUCIBLE answer, that is when:
- it asserts something the evidence contradicts;
- a causally necessary participant, process, event or action is missing;
- someone is given, or denied, information they would not really have;
- the terminal cannot actually be produced by anything in the scenario;
- a number is labelled "verified" that the evidence does not document.

Return ONE JSON object:
{{"verdict": "APPROVE" | "REVISE" | "REJECT_INSUFFICIENT_EVIDENCE",
  "reasoning": "<your trace of how the answer would be produced, or why it cannot be>",
  "causal_path": ["<step>", "..."],
  "defects": [{{"kind": "<one of: {kinds}>",
                "detail": "<exact, actionable>",
                "severity": "critical" | "major" | "minor"}}]}}

Use REVISE only for defects that change what the simulation would produce.
Use REJECT_INSUFFICIENT_EVIDENCE when no amount of rearranging could make this
evidence decide the question. If it is sound, APPROVE with an empty defect list
-- do not invent defects to appear rigorous.
"""

USER = """QUESTION
{question}

RESOLUTION DEADLINE
{deadline}

WHAT COUNTS AS THE ANSWER
{resolution_note}

FROZEN EVIDENCE PACKAGE
{evidence}

PROPOSED SEMANTIC SCENARIO
{scenario}
"""


def review(question: dict, evidence: dict, scenario: dict,
           model: str = "deepseek-chat") -> tuple:
    user = USER.format(
        question=question["question"], deadline=question["deadline"],
        resolution_note=question.get("resolution_note", ""),
        evidence=json.dumps(evidence, indent=2, sort_keys=True),
        scenario=json.dumps(scenario, indent=2, sort_keys=True))
    system = SYSTEM.format(kinds=", ".join(DEFECT_KINDS))
    out, raw, usage = call_json(system, user, model=model)

    verdict = out.get("verdict")
    if verdict not in VERDICTS:
        # an unusable verdict is itself a review failure, not something to
        # guess around
        raise RealityReviewRejected(
            f"reviewer returned an unusable verdict {verdict!r}",
            {"raw": raw[:2000]})
    result = {
        "verdict": verdict,
        "reasoning": out.get("reasoning", ""),
        "causal_path": out.get("causal_path", []),
        "defects": [d for d in out.get("defects", []) or []
                    if isinstance(d, dict)],
    }
    if verdict == "REJECT_INSUFFICIENT_EVIDENCE":
        raise RealityReviewRejected(
            out.get("reasoning", "reviewer judged the evidence insufficient"),
            {"review": result})
    return result, raw, {"system": system, "user": user}, usage


def blocking_defects(result: dict) -> list:
    return [d for d in result.get("defects", [])
            if d.get("severity") in ("critical", "major")]
