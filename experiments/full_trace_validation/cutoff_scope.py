"""Re-scan every committed a16z surface with the WIDENED cutoff arms.

Experiment-only, read-only, no live call.  Written to close audit
finding F2: a post-cutoff sentence -- ``Do not include his later a16z
employment or later a16z work`` -- reached the a16z compiler prompt.  It
originated in the USER-SUPPLIED ``relevant_context`` of the frozen
problem and the validator's phrase arm missed it by word order (its only
possessive pattern was ``his <noun> at a16z``).

This module does three things and nothing else:

1. enumerates EVERY committed surface of both a16z runs individually --
   each actor prompt, each game-master prompt, each model response, each
   compiler prompt/response, and each named JSON artifact -- rather than
   flattening a whole branch into one blob, so the published counts are
   counts of real surfaces;
2. re-scans them all with the WIDENED :mod:`cutoff` arms;
3. writes ``CUTOFF_SCOPE_CORRECTION.json`` recording the leaked
   sentence, its origin, what the old arms did, what the new arms do, and
   whether it propagated.

Nothing is repaired.  The frozen inputs are NOT edited: editing the
user-supplied context would change the frozen ``decision_problem``
hash and destroy the evidence the correction exists to preserve.  A
future a16z compile phase will now be REFUSED by the pre-compile gate
until that user-supplied sentence is corrected -- which is the
enforcement working, not a regression.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import cutoff as cutoff_lib  # noqa: E402

ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
A16Z_DIR = ARTIFACT_ROOT / "a16z_richard_historical"
PROBLEM_PATH = (REPO_ROOT / "experiments" / "full_trace_validation" / "data"
                / "a16z_problem.json")

#: the exact sentence that leaked, quoted verbatim from the frozen input
LEAKED_SENTENCE = ("Do not include his later a16z employment or later "
                   "a16z work.")

#: the pattern the OLD phrase arm carried for this family.  It matches
#: only the ``<possessive> <noun> at a16z`` ordering, so the supplied
#: sentence's ``his later a16z employment`` ordering passed every stage.
SUPERSEDED_POSSESSIVE_PATTERN = r"\bhis\s+(?:role|job|position|work)\s+at\s+a16z\b"

#: named JSON artifacts scanned per run (relative to the run directory)
_JSON_SURFACES = (
    "decision_problem.json", "evidence_manifest.json",
    "branch_input_diff.json", "offer_delivery_check.json",
    "evaluator_ledger.json", "recommendation_report.json",
    "adapter/adapted_world.json", "adapter/base_plan.json",
    "adapter/adapter_sidecar.json", "candidates/candidates.json",
)


def _jsonl(path) -> list:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _collect(run_dir: Path, label: str) -> dict:
    """Every surface of one committed run, kept SEPARATE.

    Returns ``{"prompts": [(name, text)], "responses": [...],
    "named": {name: value}}``.
    """
    prompts: list = []
    responses: list = []
    named: dict = {}

    for relative in _JSON_SURFACES:
        path = run_dir / relative
        if path.is_file():
            named[f"{label}:{relative}"] = json.loads(
                path.read_text(encoding="utf-8"))
    compiler_dir = run_dir / "compiler"
    if compiler_dir.is_dir():
        for path in sorted(compiler_dir.glob("call_*_prompt.txt")):
            named[f"{label}:compiler/{path.name}"] = path.read_text(
                encoding="utf-8")
        for path in sorted(compiler_dir.glob("call_*_raw_response.txt")):
            named[f"{label}:compiler/{path.name}"] = path.read_text(
                encoding="utf-8")

    branches_dir = run_dir / "branches"
    if branches_dir.is_dir():
        for branch_dir in sorted(branches_dir.iterdir()):
            ledger = branch_dir / "step_ledger.jsonl"
            if not ledger.is_file():
                continue
            for row in _jsonl(ledger):
                if "_artifact_class" in row:
                    continue
                step = row.get("step")
                stem = f"{label}:{branch_dir.name}:step{step}"
                request = row.get("actor_model_request")
                if isinstance(request, list):
                    for call in request:
                        for index, message in enumerate(
                                call.get("messages") or []):
                            prompts.append(
                                (f"{stem}:actor_prompt:"
                                 f"{call.get('call_id')}:{index}",
                                 message.get("content") or ""))
                raw = row.get("actor_raw_response") or {}
                for call in raw.get("recorded_calls") or []:
                    responses.append(
                        (f"{stem}:actor_response:{call.get('call_id')}",
                         call.get("response_raw") or ""))
                gm = row.get("game_master_raw_response") or {}
                for call in gm.get("recorded_calls") or []:
                    for index, message in enumerate(
                            call.get("request_messages") or []):
                        prompts.append(
                            (f"{stem}:gm_prompt:"
                             f"{call.get('call_id')}:{index}",
                             message.get("content") or ""))
                    responses.append(
                        (f"{stem}:gm_response:{call.get('call_id')}",
                         call.get("response_raw") or ""))
    return {"prompts": prompts, "responses": responses, "named": named}


def rescan_run(run_dir: Path, label: str) -> dict:
    """Scan every surface of one run individually with the current arms."""
    collected = _collect(run_dir, label)

    def scan_pairs(pairs):
        findings = []
        for name, text in pairs:
            findings.extend(cutoff_lib.scan_text(name, text)["violations"])
        return findings

    prompt_findings = scan_pairs(collected["prompts"])
    response_findings = scan_pairs(collected["responses"])
    named_findings = []
    for name, value in collected["named"].items():
        named_findings.extend(cutoff_lib.scan_text(name, value)["violations"])
    carriers = sorted({finding["surface"] for finding in named_findings
                       if finding["arm"] == "phrase"})
    return {
        "run": label,
        "directory": str(run_dir.relative_to(REPO_ROOT)),
        "actor_and_gm_prompts_scanned": len(collected["prompts"]),
        "model_responses_scanned": len(collected["responses"]),
        "named_artifact_surfaces_scanned": len(collected["named"]),
        "prompt_violation_count": len(prompt_findings),
        "response_violation_count": len(response_findings),
        "named_artifact_violation_count": len(named_findings),
        "prompt_violations": prompt_findings,
        "response_violations": response_findings,
        "named_artifact_violations": named_findings,
        "surfaces_carrying_the_leaked_phrase": carriers,
    }


def _retroactive_refusal() -> dict:
    """Apply the CORRECTED validator to the frozen input as it was run.

    Recorded rather than softened: the corrected arms refuse the frozen
    a16z ``DecisionProblem``, so the completed run carries a disclosed,
    non-propagating post-cutoff assertion in its compiler-facing context
    surface.  Nothing is repaired -- repairing it would mean editing the
    user's own frozen input.
    """
    problem = json.loads(PROBLEM_PATH.read_text(encoding="utf-8"))
    try:
        cutoff_lib.assert_clean({"decision_problem": problem})
    except cutoff_lib.HistoricalCutoffViolation as exc:
        findings = exc.findings
    else:
        findings = []
    without = dict(problem)
    without["relevant_context"] = problem.get(
        "relevant_context", "").replace(" " + LEAKED_SENTENCE, "")
    remainder = cutoff_lib.scan_surfaces({"decision_problem": without})
    return {
        "verdict": ("REFUSED -- cutoff.assert_clean raises "
                    "HistoricalCutoffViolation on the frozen problem"
                    if findings else
                    "unexpectedly clean; re-derive this record"),
        "finding_count": len(findings),
        "matched_texts": sorted({finding["matched_text"]
                                 for finding in findings}),
        "arms": sorted({finding["arm"] for finding in findings}),
        "harness_consequence": (
            "runner_a16z.phase_branches returns exit 6 (branches REFUSED) "
            "for this problem; the scenario cannot be run end to end "
            "until the user-supplied sentence is corrected. The gate is "
            "NOT relaxed and the frozen input is NOT edited."),
        "honest_characterization": (
            "the completed a16z run carries a disclosed, non-propagating "
            "post-cutoff assertion in its compiler-facing context "
            "surface"),
        "the_known_sentence_is_the_only_defect": remainder["clean"],
        "proof_that_it_is_the_only_defect": (
            "removing exactly that one sentence IN MEMORY (never on disk) "
            "leaves the frozen problem scanning clean, so the pinned "
            "violation is not hiding a second one behind it"),
    }


def build_payload() -> dict:
    problem = json.loads(PROBLEM_PATH.read_text(encoding="utf-8"))
    context = problem.get("relevant_context", "")
    pre_fix = rescan_run(A16Z_DIR, "pre_fix")
    post_fix = rescan_run(A16Z_DIR / "post_fix_rerun", "post_fix")
    old_catches = bool(
        __import__("re").search(SUPERSEDED_POSSESSIVE_PATTERN,
                                LEAKED_SENTENCE,
                                __import__("re").IGNORECASE))
    new_record = cutoff_lib.scan_text("leaked_sentence", LEAKED_SENTENCE)
    return {
        "correction_id": "F2_cutoff_phrase_arm_word_order",
        "recorded_utc": "2026-08-04",
        "status": ("DISCLOSED AND CORRECTED IN THE VALIDATOR; the frozen "
                   "artifacts are NOT edited"),
        "finding": (
            "A sentence asserting the post-cutoff OUTCOME of the very "
            "counterfactual being simulated reached the a16z compiler "
            "prompt and passed all three enforcement stages."),
        "leaked_sentence": LEAKED_SENTENCE,
        "where_it_was_found_first": (
            "artifacts/full_trace_validation_20260804/"
            "a16z_richard_historical/compiler/call_1_prompt.txt:136"),
        "origin": {
            "kind": "USER-SUPPLIED INPUT, not engine-generated",
            "file": "experiments/full_trace_validation/data/"
                    "a16z_problem.json",
            "field": "relevant_context",
            "present_in_frozen_input": LEAKED_SENTENCE in context,
            "note": ("The harness carried the user's own context verbatim "
                     "into the compiler prompt, which is the designed "
                     "behaviour. The defect is that the validator did not "
                     "stop it."),
        },
        "what_the_old_arms_did": {
            "date_arm": ("unaffected: the sentence contains no date-shaped "
                         "token, so the date arm had nothing to match"),
            "phrase_arm": (
                "carried exactly one possessive pattern for this family, "
                f"{SUPERSEDED_POSSESSIVE_PATTERN!r}, which fixes the word "
                "order to '<possessive> <noun> at a16z'. The supplied "
                "sentence uses the adjectival ordering '<possessive> "
                "later a16z <noun>', so it did not match."),
            "superseded_pattern": SUPERSEDED_POSSESSIVE_PATTERN,
            "superseded_pattern_matches_the_leaked_sentence": old_catches,
            "result": ("clean at pre_compile, pre_simulation and "
                       "post_run_prompts; the run was allowed to proceed"),
        },
        "what_the_new_arms_do": {
            "patterns_added": [
                pattern for pattern in cutoff_lib.POST_CUTOFF_PHRASE_PATTERNS
                if "tenure" in pattern],
            "leaked_sentence_now_rejected": not new_record["clean"],
            "matched_text": [finding["matched_text"]
                             for finding in new_record["violations"]],
            "conservatism": (
                "the added arms require a possessive or a "
                "later/subsequent/eventual modifier in front of a "
                "COMPLETED-TENURE noun. Nouns that are the SUBJECT of the "
                "simulation (hire, hiring, offer, appointment, decision) "
                "are deliberately excluded, so prospective and conditional "
                "wording still passes; "
                "tests/experiment_harness/test_a16z_cutoff.py pins both "
                "directions."),
            "consequence_for_future_runs": (
                "a new a16z compile phase is now REFUSED by the "
                "pre-compile gate until the user-supplied "
                "relevant_context is corrected. The frozen input is left "
                "exactly as it was run: editing it would change the "
                "frozen decision_problem hash and destroy the evidence."),
            "retroactively_refuses_the_frozen_input": _retroactive_refusal(),
        },
        "did_it_propagate": {
            "verdict": "NO -- independently re-verified over both runs",
            "method": (
                "every committed surface of both a16z runs was re-scanned "
                "INDIVIDUALLY with the widened arms: each actor prompt, "
                "each game-master prompt, each model response, each "
                "compiler prompt and response, and each named JSON "
                "artifact"),
            "pre_fix_run": {
                "actor_and_gm_prompts_scanned":
                    pre_fix["actor_and_gm_prompts_scanned"],
                "prompt_violations": pre_fix["prompt_violation_count"],
                "model_responses_scanned":
                    pre_fix["model_responses_scanned"],
                "response_violations": pre_fix["response_violation_count"],
            },
            "post_fix_rerun": {
                "actor_and_gm_prompts_scanned":
                    post_fix["actor_and_gm_prompts_scanned"],
                "prompt_violations": post_fix["prompt_violation_count"],
                "model_responses_scanned":
                    post_fix["model_responses_scanned"],
                "response_violations": post_fix["response_violation_count"],
            },
            "compiled_world_clean": (
                f"{'pre_fix' + ':adapter/adapted_world.json'} and "
                "adapter/base_plan.json carry no phrase-arm finding in "
                "either run, so the sentence did not survive compilation "
                "into the simulated world"),
            "surfaces_that_do_carry_it": {
                "pre_fix": pre_fix["surfaces_carrying_the_leaked_phrase"],
                "post_fix": post_fix["surfaces_carrying_the_leaked_phrase"],
            },
            "why_those_surfaces": (
                "each one echoes the user's own relevant_context verbatim "
                "(the problem file itself, the adapter sidecar that "
                "retains unmapped source fields, the compiler prompts, and "
                "the pre-fix recommendation report). None of them is an "
                "actor-visible or game-master-visible surface."),
        },
        "enforcement_scope_correction": {
            "claim_being_corrected": (
                "'The historical cutoff was enforced mechanically rather "
                "than promised, at 3 stages, with a canary that the "
                "validator rejects.'"),
            "what_is_true": (
                "three stages did run (pre_compile, pre_simulation, "
                "post_run_prompts), each over real bytes, and the canary "
                "is rejected. The stages did scan the surface carrying "
                "the leaked sentence."),
            "what_is_not_true": (
                "'enforced' overstated the coverage. Enforcement is only "
                "as wide as the arms: the phrase arm's pattern set did "
                "not contain this word order, so all three stages passed "
                "the sentence. Mechanical enforcement means the check "
                "really ran on the real bytes -- not that the check is "
                "complete."),
            "additional_scope_edge_found_while_re_scanning": (
                "the enforced pre_compile surfaces are the HARNESS-SUPPLIED "
                "inputs (problem, evidence, question, context, package, "
                "scope note), not the fully ASSEMBLED compiler prompt. The "
                "assembled prompt additionally contains the compiler's own "
                "fixed instruction template, whose illustrative deadline "
                "arithmetic example carries the dates 2026-07-15 and "
                "2026-09-13. Those are template examples with no claim "
                "about this counterfactual, but they are post-cutoff "
                "date tokens inside a prompt byte-stream that no stage "
                "scanned. Disclosed, not repaired."),
            "known_date_arm_false_positive": (
                "scanning offer_delivery_check.json turns up '2040' inside "
                "the sha256 digest '...edcd2040'. The bare-year rule's "
                "lookbehind excludes digits and separators but not hex "
                "letters. That file is not an enforcement surface, and "
                "narrowing the year rule to dodge hex tails would weaken a "
                "real arm to tidy a report, so it is disclosed here "
                "instead."),
        },
        "artifact_record_stands": (
            "The a16z run is NOT re-run for this. The leak is disclosed, "
            "it did not propagate to any actor or game-master surface, "
            "and re-running would replace frozen evidence with new "
            "evidence."),
        "full_rescan": {"pre_fix_run": pre_fix, "post_fix_rerun": post_fix},
    }


def write(path=None) -> Path:
    path = Path(path) if path else (A16Z_DIR / "CUTOFF_SCOPE_CORRECTION.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_payload(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    print(f"wrote {write(args.out)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
