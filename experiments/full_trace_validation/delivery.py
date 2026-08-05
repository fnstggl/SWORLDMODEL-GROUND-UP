"""Did the candidate actually reach the recipient?

Experiment-only.  A comparison of candidates is only meaningful if the
candidates differ in what the RECIPIENT saw.  This module answers that
question mechanically from the recorded artifacts, so a scenario can
never report a winner without the reader being able to check whether the
winning candidate's text ever entered the recipient's context.

Two independent checks per scenario:

``content_delivery``
    Did any prompt sent to the recipient's model contain distinctive
    text from that branch's candidate?  Distinctive text is taken as the
    candidate's longest whitespace-normalised token runs, so a candidate
    whose action is paraphrased still counts only if real content
    arrived.
``prompt_discrimination``
    Are the recipient's prompts DIFFERENT across branches?  If the
    recipient's first-turn prompt has the same sha256 in every branch,
    then whatever differences the metrics report cannot have been caused
    by the candidates: at that point the run is measuring model sampling
    variation on one identical prompt.

Both results are written to ``candidate_delivery_check.json`` and quoted
in the UNDER_THE_HOOD report.  Neither check changes a metric; they
qualify what a metric can mean.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

#: minimum length of a candidate substring counted as "distinctive"
MIN_FRAGMENT_CHARS = 24
#: how many fragments to test per candidate
MAX_FRAGMENTS = 12

_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    return _WS.sub(" ", (text or "")).strip()


def _sha(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def candidate_fragments(action: str) -> list:
    """Distinctive fragments of one candidate: its longest sentences /
    line runs, whitespace-normalised, longest first."""
    pieces = re.split(r"(?<=[.!?])\s+|\n+", action or "")
    fragments = []
    for piece in pieces:
        piece = normalise(piece)
        if len(piece) >= MIN_FRAGMENT_CHARS:
            fragments.append(piece)
    fragments.sort(key=len, reverse=True)
    return fragments[:MAX_FRAGMENTS]


def recipient_prompts(step_ledger_rows, recipient_name: str) -> list:
    """Every prompt actually sent to the recipient's own model."""
    prompts = []
    for record in step_ledger_rows:
        active = record.get("active_actor")
        if not isinstance(active, dict) or \
                active.get("name") != recipient_name:
            continue
        request = record.get("actor_model_request")
        if not isinstance(request, list):
            continue
        for call in request:
            for message in call.get("messages") or []:
                if message.get("role") != "user":
                    continue
                prompts.append({"step": record["step"],
                                "call_id": call.get("call_id"),
                                "prompt": message.get("content") or ""})
    return prompts


def check_branch(*, candidate_id, candidate_action, recipient_name,
                 step_ledger_rows) -> dict:
    prompts = recipient_prompts(step_ledger_rows, recipient_name)
    fragments = candidate_fragments(candidate_action)
    joined = " ".join(normalise(entry["prompt"]) for entry in prompts)
    delivered = [fragment for fragment in fragments if fragment in joined]
    first_prompt = prompts[0]["prompt"] if prompts else ""
    return {
        "candidate_id": candidate_id,
        "recipient_prompt_count": len(prompts),
        "recipient_first_turn_prompt_sha256": _sha(first_prompt),
        "recipient_first_turn_prompt_chars": len(first_prompt),
        "candidate_fragments_tested": len(fragments),
        "candidate_fragments_found_in_recipient_prompts": len(delivered),
        "example_fragment_found": delivered[0] if delivered else None,
        "example_fragment_missing": (
            None if len(delivered) == len(fragments) or not fragments
            else next(f for f in fragments if f not in joined)),
        "content_delivered_to_recipient": bool(delivered),
        "per_prompt_sha256": [
            {"step": entry["step"], "call_id": entry["call_id"],
             "sha256": _sha(entry["prompt"])} for entry in prompts],
    }


def check_scenario(*, scenario_id, recipient_name, branches) -> dict:
    """``branches`` is an iterable of ``(candidate_id, action, rows)``."""
    per_branch = [check_branch(candidate_id=candidate_id,
                               candidate_action=action,
                               recipient_name=recipient_name,
                               step_ledger_rows=rows)
                  for candidate_id, action, rows in branches]
    first_hashes = {entry["candidate_id"]:
                    entry["recipient_first_turn_prompt_sha256"]
                    for entry in per_branch}
    distinct = len(set(first_hashes.values()))
    any_delivered = any(entry["content_delivered_to_recipient"]
                        for entry in per_branch)
    verdict = "candidates_reached_the_recipient"
    if not any_delivered and distinct <= 1:
        verdict = "candidates_never_reached_the_recipient"
    elif not any_delivered:
        verdict = "no_candidate_text_reached_the_recipient"
    elif distinct <= 1:
        verdict = "recipient_saw_identical_first_turn_context"
    return {
        "scenario_id": scenario_id,
        "recipient_actor": recipient_name,
        "per_branch": per_branch,
        "recipient_first_turn_prompt_sha256_by_candidate": first_hashes,
        "distinct_recipient_first_turn_prompts": distinct,
        "branch_count": len(per_branch),
        "verdict": verdict,
        "interpretation": _INTERPRETATION[verdict],
    }


_INTERPRETATION = {
    "candidates_reached_the_recipient": (
        "distinctive candidate text appeared in the recipient's own "
        "prompts and the recipient's first-turn context differed by "
        "branch, so a measured difference between branches can be "
        "attributed to the candidates."),
    "candidates_never_reached_the_recipient": (
        "NO distinctive candidate text ever appeared in a prompt sent to "
        "the recipient's model, AND the recipient's first-turn prompt was "
        "byte-identical in every branch. Any difference the metrics "
        "report therefore cannot have been caused by the candidates: at "
        "that point the run measures live-model sampling variation on one "
        "identical prompt. The ranking is NOT evidence that one candidate "
        "is better than another."),
    "no_candidate_text_reached_the_recipient": (
        "no distinctive candidate text reached the recipient, although "
        "the recipient's first-turn prompts did differ; any measured "
        "difference must be traced to that other difference, not to the "
        "candidate content."),
    "recipient_saw_identical_first_turn_context": (
        "some candidate text reached the recipient later in the branch, "
        "but the recipient's FIRST turn ran on identical context in every "
        "branch; differences arising at that first turn are sampling "
        "variation, not candidate effects."),
}


def private_context_leak_check(*, step_ledger_rows, private_by_name) -> dict:
    """Did any actor's prompt contain ANOTHER actor's private context?

    Computed, not asserted: every recorded prompt is compared against
    every other actor's private context, both verbatim and by its longest
    distinctive fragments.
    """
    fragments_by_name = {name: candidate_fragments(text)
                         for name, text in private_by_name.items()}
    findings = []
    checked = 0
    for record in step_ledger_rows:
        active = record.get("active_actor")
        if not isinstance(active, dict):
            continue
        owner = active.get("name")
        request = record.get("actor_model_request")
        if not isinstance(request, list):
            continue
        for call in request:
            for message in call.get("messages") or []:
                if message.get("role") != "user":
                    continue
                prompt = normalise(message.get("content") or "")
                checked += 1
                for other, fragments in fragments_by_name.items():
                    if other == owner:
                        continue
                    hits = [fragment for fragment in fragments
                            if fragment in prompt]
                    if hits:
                        findings.append({
                            "step": record["step"], "prompt_owner": owner,
                            "leaked_from": other,
                            "fragment": hits[0][:160]})
    return {"prompts_checked": checked, "leaks_found": len(findings),
            "findings": findings}


def load_step_ledger(path) -> list:
    """Step records from one branch ledger (the auditor banner dropped)."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if "_artifact_class" in record:
            continue
        rows.append(record)
    return rows
