"""Model call #1: question + frozen evidence -> semantic scenario.

The model describes meaning. It never writes identifiers, payloads or code;
the contract it is given is generated from schema.py, and everything it
returns is structurally validated before anything is built.
"""
from __future__ import annotations

import json
import re

from .errors import InsufficientEvidence, SemanticAmbiguity
from .llm import TruncatedResponse, call_json
from .schema import (check_evidence_sufficiency, check_provenance,
                     contract_document, validate)

SYSTEM = """You reconstruct the smallest real-world situation that can decide a question.

You are given a question, a resolution deadline, and a FROZEN EVIDENCE PACKAGE.
The evidence package is your ONLY source of facts. You may reason from it, and
you may make clearly-labelled inferences about ordinary human and operational
behaviour, but you must never assert a fact it does not support.

Include only what can MATERIALLY CHANGE THE ANSWER. A world that is too big is
as wrong as one that is too small.

{contract}

If the evidence cannot support a world that could decide this question, return
exactly {{"insufficient_evidence": "<what is missing and why it is decisive>"}}
instead of a scenario. Refusing is a correct answer.
"""

USER = """QUESTION
{question}

RESOLUTION DEADLINE
{deadline}

WHAT COUNTS AS THE ANSWER
{resolution_note}

FROZEN EVIDENCE PACKAGE
{evidence}

Build the smallest causally sufficient world that can decide this question,
as one JSON object with the required sections. Cite the evidence ids that
support each participant and each starting fact.
"""


def build_scenario(question: dict, evidence: dict, revision_defects=None,
                   previous=None, model: str = "deepseek-chat") -> tuple:
    """Return (semantic_scenario, raw_response, prompt)."""
    user = USER.format(
        question=question["question"],
        deadline=question["deadline"],
        resolution_note=question.get("resolution_note", ""),
        evidence=json.dumps(evidence, indent=2, sort_keys=True))
    if revision_defects:
        user += ("\n\nYOUR PREVIOUS SCENARIO WAS REVIEWED AND MUST BE CORRECTED.\n"
                 "Defects found by an independent reviewer:\n"
                 + "\n".join(f"- [{d.get('kind','defect')}] {d.get('detail','')}"
                             for d in revision_defects)
                 + "\n\nYour previous scenario:\n"
                 + json.dumps(previous, indent=2, sort_keys=True)
                 + "\n\nReturn a corrected COMPLETE scenario. Fix exactly these "
                   "defects; do not rebuild the parts that were not criticised.")
    system = SYSTEM.format(contract=contract_document())
    try:
        doc, raw, usage = call_json(system, user, model=model)
    except TruncatedResponse as e:
        raise SemanticAmbiguity(str(e), {"repairable": True})
    except json.JSONDecodeError as e:
        raise SemanticAmbiguity(
            f"the reply was not valid JSON ({e}). Return one complete JSON "
            f"object and nothing else.", {"repairable": True})
    # keep the raw reply reachable even when validation refuses it, so a
    # refusal can be inspected rather than merely reported
    build_scenario.last_raw = raw
    build_scenario.last_prompt = {"system": system, "user": user}
    build_scenario.last_usage = usage

    if "insufficient_evidence" in doc and len(doc) == 1:
        raise InsufficientEvidence(str(doc["insufficient_evidence"]),
                                   {"declared_by": "semantic compiler"})
    _reject_runtime_syntax(doc)
    validate(doc)
    check_provenance(doc, evidence)
    check_evidence_sufficiency(doc, evidence)
    return doc, raw, {"system": system, "user": user}, usage


#: Substrings that betray the model writing runtime internals instead of
#: meaning. Their presence is a contract violation, not a style problem.
FORBIDDEN_KEYS = (
    "seq", "cause", "world_version", "depth", "microstep", "queue",
    "op", "ops", "effect_payload", "record_id", "event_id", "ledger",
    "require", "params", "actor_id", "channel_id", "verb",
)
#: {something} in authored prose means the model tried to write a payload
#: template instead of describing meaning.
_TEMPLATE_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_.]*\}")

FORBIDDEN_VALUE_MARKERS = (
    "fact.set", "resource.set", "resource.adjust", "resource.transfer",
    "info.send_new", "event.schedule_in", "actor.belief", "actor.memory",
    "process.active", "action.define", "world.ops", "wake.actor",
    "def ", "import ", "lambda ", "world.apply",
)


def _reject_runtime_syntax(doc, path="") -> None:
    """The compiler boundary is enforced, not trusted."""
    if isinstance(doc, dict):
        for k, v in doc.items():
            if k in FORBIDDEN_KEYS:
                raise SemanticAmbiguity(
                    f"the scenario contains runtime-internal field {k!r} at "
                    f"{path or 'root'}; the semantic layer may only describe "
                    f"meaning", {"path": path, "field": k})
            _reject_runtime_syntax(v, f"{path}.{k}" if path else k)
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            _reject_runtime_syntax(v, f"{path}[{i}]")
    elif isinstance(doc, str):
        if _TEMPLATE_RE.search(doc):
            token = _TEMPLATE_RE.search(doc).group(0)
            field = path.rsplit(".", 1)[-1]
            raise SemanticAmbiguity(
                f"the text at {path} contains {token!r}. Braces are NOT "
                f"placeholders here -- that text is stored literally, so a "
                f"reader would see {token!r} in the message. Fix it one of two "
                f"ways: (a) if the value is known, write the actual words "
                f"instead of {token!r}; or (b) if it really comes from the "
                f"action's parameter, remove {token!r} from the text and add "
                f'"{field}_from_parameter": "<the parameter name>" beside '
                f'"{field}" instead.',
                {"path": path, "text": doc[:200], "repairable": True})
        low = doc.lower()
        for marker in FORBIDDEN_VALUE_MARKERS:
            if marker in low:
                raise SemanticAmbiguity(
                    f"the scenario contains runtime syntax {marker!r} at "
                    f"{path}; describe the meaning instead",
                    {"path": path, "text": doc[:200]})
