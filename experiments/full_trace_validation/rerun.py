"""Post-fix re-runs: frozen-input verification and pre/post comparison.

Experiment-only.  Four production defects were closed at ``c5a81214``
(agency-guard determiner false positive, silent unresolved-observer drop,
undelivered-intervention ranking, visibility-incoherence warning).  The
standing directive is to restart the affected experiments FROM THEIR
FROZEN INPUTS afterwards, and to keep BOTH artifact sets: the pre-fix
directories are the before half of the record and are never moved,
deleted, or rewritten.

This module supplies the two things a re-run needs beyond the runners
themselves:

1. :func:`verify_frozen_inputs` -- before a single live call, recompute
   the hashes of the inputs the re-run is about to reuse and compare them
   against the entries the PRE-FIX freeze manifest recorded.  A re-run
   that silently used different inputs would produce a before/after
   comparison of two different experiments.
2. :func:`compare_scenarios` / :func:`write_comparison` -- read both
   artifact sets and write ``PRE_VS_POST_FIX.md``: guard interventions,
   unresolved observers now recorded, ``intervention_delivered`` per
   branch, ranked-or-refused, and terminal statuses.

Pure stdlib plus the harness's own freeze helpers; no model, no engine.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import freeze as freeze_lib

#: the frozen-input entries a post-fix re-run must reproduce exactly.
#: These are the entries that describe the INPUTS -- the decision problem,
#: the evidence, the compiler artifact set and how it was produced, the
#: evaluator, the window, the seeds and the model configuration.  The
#: candidate set is deliberately absent: for the generated scenario it is
#: a live OUTPUT of the run, and the comparison reports whether it came
#: back identical rather than requiring it to.
FROZEN_INPUT_ENTRIES = (
    "decision_problem",
    "evidence_manifest",
    "compiler_command_and_config",
    "compiler_inputs",
    "compiler_artifact_dir_aggregate",
    "compiled_decision_world",
    "concordia_initialization_plan",
    "concordia_initialization_plan_content_hash",
    "evaluator_spec",
    "simulation_limits",
    "time_window",
    "branch_seeds",
)


class FrozenInputMismatch(AssertionError):
    """A re-run's inputs do not match the pre-fix freeze manifest."""


def _load(path):
    path = Path(path)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path) -> list:
    path = Path(path)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def verify_frozen_inputs(pre_fix_manifest_path, *, compiler_dir,
                         decision_problem=None,
                         evidence_manifest=None) -> dict:
    """Check, BEFORE any live call, that the re-run's inputs are the
    pre-fix run's inputs.

    The compiler artifact directory is re-hashed from disk; the decision
    problem and evidence manifest are hashed from the objects the re-run
    is about to use.  Anything that does not match raises
    :class:`FrozenInputMismatch` -- a re-run on different inputs is not a
    re-run.
    """
    manifest = freeze_lib.load_manifest(pre_fix_manifest_path)
    checks = []
    aggregate = freeze_lib.hash_directory(compiler_dir)["aggregate"]
    checks.append({
        "entry": "compiler_artifact_dir_aggregate",
        "recorded_by_the_pre_fix_run": freeze_lib.entry_sha(
            manifest, "compiler_artifact_dir_aggregate"),
        "recomputed_now": aggregate,
        "source": str(compiler_dir),
    })
    if decision_problem is not None:
        checks.append({
            "entry": "decision_problem",
            "recorded_by_the_pre_fix_run": freeze_lib.entry_sha(
                manifest, "decision_problem"),
            "recomputed_now": freeze_lib.sha256_json(decision_problem),
            "source": "the payload this re-run is about to run",
        })
    if evidence_manifest is not None:
        checks.append({
            "entry": "evidence_manifest",
            "recorded_by_the_pre_fix_run": freeze_lib.entry_sha(
                manifest, "evidence_manifest"),
            "recomputed_now": freeze_lib.sha256_json(evidence_manifest),
            "source": "the manifest this re-run is about to run",
        })
    for check in checks:
        check["match"] = (check["recorded_by_the_pre_fix_run"]
                          == check["recomputed_now"])
    mismatched = [check for check in checks if not check["match"]]
    payload = {
        "claim": ("this re-run reuses the pre-fix run's frozen inputs; "
                  "every hash below was recomputed now and compared "
                  "against the entry the pre-fix freeze manifest "
                  "recorded"),
        "pre_fix_manifest": str(pre_fix_manifest_path),
        "checks": checks,
        "all_match": not mismatched,
    }
    if mismatched:
        raise FrozenInputMismatch(
            "refusing to run: the inputs do not match the pre-fix freeze "
            "manifest, so this would not be a re-run of the same "
            f"experiment. Mismatched entries: {[c['entry'] for c in mismatched]}")
    return payload


def compare_freeze_manifests(pre_path, post_path,
                             entries=FROZEN_INPUT_ENTRIES) -> dict:
    """Entry-by-entry comparison of the two freeze manifests.

    Reports rather than asserts: an entry only one side recorded is
    listed as such, so a manifest that legitimately grew (the settling
    experiment's arm entries, say) does not read as a mismatch.
    """
    pre = freeze_lib.load_manifest(pre_path)
    post = freeze_lib.load_manifest(post_path)
    rows = []
    for name in entries:
        left = pre.get("entries", {}).get(name, {}).get("sha256")
        right = post.get("entries", {}).get(name, {}).get("sha256")
        rows.append({"entry": name, "pre_fix": left, "post_fix": right,
                     "identical": bool(left) and left == right,
                     "recorded_by_both": bool(left) and bool(right)})
    return {
        "entries": rows,
        "all_identical": all(row["identical"] for row in rows),
        "entries_that_differ": [row["entry"] for row in rows
                                if not row["identical"]],
    }


def _guard_facts(scenario_dir) -> dict:
    """Guard interventions across every branch of one scenario."""
    scenario_dir = Path(scenario_dir)
    per_branch = {}
    records = []
    for path in sorted(scenario_dir.glob("branches/*/guard_ledger.jsonl")):
        branch = path.parent.name
        rows = _jsonl(path)
        fired = [row for row in rows if row.get("intervened")]
        per_branch[branch] = len(fired)
        for row in fired:
            for record in row.get("records") or ():
                records.append({
                    "branch": branch,
                    "step": record.get("step"),
                    "active": record.get("active"),
                    "affected": record.get("affected"),
                    "original_excerpt": record.get("original_excerpt"),
                    "rewritten_excerpt": record.get("rewritten_excerpt"),
                })
    return {"per_branch": per_branch,
            "total": sum(per_branch.values()),
            "records": records}


def _branch_facts(scenario_dir) -> dict:
    """Per-branch contract facts: terminal status, the delivery fact the
    D2 fix added, and the unresolved observer names the D1 fix records.

    A pre-fix branch result carries NEITHER new field. That absence is
    reported as ``not measured (the field did not exist)`` rather than as
    a value, because reporting it as ``not_delivered`` would claim a
    measurement the pre-fix run never made.
    """
    scenario_dir = Path(scenario_dir)
    branches = {}
    for path in sorted(scenario_dir.glob("branches/*/branch_result.json")):
        data = _load(path) or {}
        branch = path.parent.name
        delivery = data.get("intervention_delivered")
        observers = data.get("unresolved_observers")
        branches[branch] = {
            "terminal_status": data.get("terminal_status"),
            "intervention_delivered": (
                delivery.get("status") if isinstance(delivery, dict)
                else None),
            "intervention_delivered_reason": (
                delivery.get("reason") if isinstance(delivery, dict)
                else None),
            "intervention_delivered_field_present": delivery is not None,
            "unresolved_observers": (list(observers)
                                     if isinstance(observers, list) else None),
            "unresolved_observer_count": (len(observers)
                                          if isinstance(observers, list)
                                          else None),
            "unresolved_observers_field_present": observers is not None,
            "committed_event_count": len(data.get("event_trace") or []),
        }
    return branches


def _ranking_facts(scenario_dir) -> dict:
    scenario_dir = Path(scenario_dir)
    refusal = _load(scenario_dir / "ranking_refusal.json")
    result = _load(scenario_dir / "recommendation_result.json")
    if refusal is not None or (isinstance(result, dict)
                               and result.get("refused")):
        payload = refusal if refusal is not None else result
        return {"outcome": "REFUSED",
                "reason": payload.get("reason"),
                "best_candidate_id": None}
    if isinstance(result, dict) and result.get("best_candidate_id"):
        return {"outcome": "PRODUCED",
                "reason": None,
                "best_candidate_id": result.get("best_candidate_id")}
    return {"outcome": "UNKNOWN", "reason": None, "best_candidate_id": None}


def _delivery_facts(scenario_dir) -> dict:
    scenario_dir = Path(scenario_dir)
    for name in ("candidate_delivery_check.json",
                 "offer_delivery_check.json"):
        data = _load(scenario_dir / name)
        if isinstance(data, dict):
            return {"check": name,
                    "verdict": data.get("verdict"),
                    "distinct_recipient_first_turn_prompts": data.get(
                        "distinct_recipient_first_turn_prompts")
                    or data.get("distinct_subject_first_turn_prompts")}
    return {"check": None, "verdict": None,
            "distinct_recipient_first_turn_prompts": None}


def _cutoff_facts(scenario_dir) -> dict:
    """The historical-cutoff enforcement record, when the scenario has
    one (only the a16z counterfactual does)."""
    data = _load(Path(scenario_dir) / "historical_cutoff_validation.json")
    if not isinstance(data, dict):
        return {}
    prompts = data.get("post_run_prompts") or {}
    responses = data.get("post_run_model_responses") or {}
    return {
        "enforced_stages": data.get("enforced_stages"),
        "overall_clean": data.get("overall_clean"),
        "pre_simulation_clean": (data.get("pre_simulation") or {}).get(
            "clean"),
        "pre_simulation_surface_count": (data.get("pre_simulation")
                                         or {}).get("surface_count"),
        "post_run_prompts_clean": prompts.get("clean"),
        "post_run_prompt_violations": prompts.get("violation_count"),
        "post_run_response_findings": responses.get("violation_count"),
        "canary_rejected": (data.get("canary") or {}).get(
            "rejected_by_the_validator"),
        "pre_compile_stage": data.get("pre_compile_stage"),
    }


def _isolation_facts(scenario_dir) -> dict:
    data = _load(Path(scenario_dir) / "branch_input_diff.json")
    if not isinstance(data, dict):
        return {}
    return {"verdict": data.get("verdict"),
            "claim": data.get("claim")}


def _instrumentation_facts(scenario_dir, scenario_id=None) -> dict:
    """This scenario's own recorder instrumentation.

    The Peter runs put it in the artifact root's shared directory and the
    a16z run puts it beside the scenario, so both locations are searched
    -- the alternative is reporting ``None`` for a number that exists.
    """
    scenario_dir = Path(scenario_dir)
    candidates = (sorted(scenario_dir.glob("instrumentation_*.json"))
                  + sorted(scenario_dir.glob("shared/instrumentation_*.json")))
    if scenario_id:
        for parent in (scenario_dir.parent, scenario_dir.parent.parent):
            candidates.append(
                parent / "shared" / f"instrumentation_{scenario_id}.json")
    for path in candidates:
        if path.name == "instrumentation_validation.json":
            continue
        data = _load(path)
        if isinstance(data, dict) and "equality_proof" in data:
            ledger = data.get("ledger") or {}
            return {
                "source": str(path),
                "live_calls": ledger.get("records_written"),
                "errors": ledger.get("records_with_error"),
                "retries": ledger.get("records_that_were_retries"),
                "per_role": ledger.get("per_role"),
                "all_equal": (data["equality_proof"] or {}).get("all_equal"),
            }
    return {}


def scenario_facts(scenario_dir, scenario_id=None) -> dict:
    """Everything the pre/post comparison reads from one artifact set."""
    return {
        "directory": str(scenario_dir),
        "guard": _guard_facts(scenario_dir),
        "branches": _branch_facts(scenario_dir),
        "ranking": _ranking_facts(scenario_dir),
        "delivery": _delivery_facts(scenario_dir),
        "cutoff": _cutoff_facts(scenario_dir),
        "branch_input_isolation": _isolation_facts(scenario_dir),
        "instrumentation": _instrumentation_facts(scenario_dir, scenario_id),
    }


def unresolved_observer_summary(scenario_dir) -> dict:
    """Every non-resolving observer name the D1 fix recorded, counted.

    The pre-fix run has no such record at all -- that is the defect: the
    event was dropped with no error and no trace.
    """
    counts: dict = {}
    reasons: dict = {}
    total = 0
    facts = _branch_facts(scenario_dir)
    measured = False
    for branch in facts.values():
        entries = branch.get("unresolved_observers")
        if entries is None:
            continue
        measured = True
        for entry in entries:
            name = entry.get("observer_name")
            counts[name] = counts.get(name, 0) + 1
            reason = entry.get("reason")
            reasons[reason] = reasons.get(reason, 0) + 1
            total += 1
    return {"measured": measured, "total": total,
            "by_name": dict(sorted(counts.items(),
                                   key=lambda item: (-item[1], item[0]))),
            "by_reason": dict(sorted(reasons.items()))}


def compare_scenarios(*, scenario_id, pre_dir, post_dir,
                      freeze_comparison=None, notes=()) -> dict:
    pre = scenario_facts(pre_dir, scenario_id)
    post = scenario_facts(post_dir, scenario_id)
    return {
        "scenario_id": scenario_id,
        "pre_fix": pre,
        "post_fix": post,
        "guard_interventions_pre": pre["guard"]["total"],
        "guard_interventions_post": post["guard"]["total"],
        "guard_interventions_removed": (pre["guard"]["total"]
                                        - post["guard"]["total"]),
        "unresolved_observers_pre": unresolved_observer_summary(pre_dir),
        "unresolved_observers_post": unresolved_observer_summary(post_dir),
        "frozen_input_comparison": freeze_comparison,
        "notes": list(notes),
    }


def session_call_accounting(instrumentation_paths) -> dict:
    """Sum the recorded provider calls across a set of runs.

    Every number is read from a recorder ``instrumentation`` artifact --
    the same file whose three independent counters (network boundary,
    seam attempts, ledger writes) must already agree -- so the total is
    computed from the evidence rather than tallied by hand.  Any run
    whose counters do NOT agree is listed separately instead of being
    folded into a total that would then mean nothing.
    """
    runs = []
    total = errors = retries = 0
    disagreeing = []
    for path in sorted(instrumentation_paths):
        data = _load(path)
        if not isinstance(data, dict) or "ledger" not in data:
            continue
        ledger = data["ledger"]
        equal = bool((data.get("equality_proof") or {}).get("all_equal"))
        runs.append({
            "source": str(path),
            "experiment_id": ledger.get("experiment_id"),
            "calls": ledger.get("records_written"),
            "errors": ledger.get("records_with_error"),
            "retries": ledger.get("records_that_were_retries"),
            "counters_agree": equal,
        })
        if not equal:
            disagreeing.append(str(path))
            continue
        total += ledger.get("records_written") or 0
        errors += ledger.get("records_with_error") or 0
        retries += ledger.get("records_that_were_retries") or 0
    return {
        "claim": ("every provider request these runs issued, summed from "
                  "the per-run recorder instrumentation; a run whose three "
                  "counters disagree is excluded from the total and named"),
        "runs": runs,
        "total_recorded_calls": total,
        "total_errors": errors,
        "total_retries": retries,
        "runs_with_disagreeing_counters": disagreeing,
        "note": ("one-token provider health probes are issued OUTSIDE the "
                 "simulation and are deliberately NOT in these ledgers; "
                 "each run records its own in provider_probe.json"),
    }


def _table(rows, headers) -> list:
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def build_comparison(payload: dict) -> str:
    pre = payload["pre_fix"]
    post = payload["post_fix"]
    branches = sorted(set(pre["branches"]) | set(post["branches"]))
    lines = [
        f"# Pre-fix vs post-fix -- `{payload['scenario_id']}`",
        "",
        "> **UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION.** Both runs "
        "below are uncalibrated one-shot simulations against a live "
        "model. Nothing here is a prediction about any real person.",
        "",
        "The pre-fix run is preserved exactly as it was recorded; this "
        "re-run was written to `post_fix_rerun/` and nothing in the "
        "pre-fix directory was moved, deleted, or rewritten. Live model "
        "sampling is not reproducible at temperature 0, so the two runs "
        "are NOT expected to produce identical text -- what is compared "
        "is the ENGINE behaviour the four fixes were supposed to change.",
        "",
        "## Frozen inputs",
        "",
    ]
    freeze = payload.get("frozen_input_comparison")
    if freeze:
        lines.append(
            "Every input entry below was hashed by the pre-fix run and "
            "re-hashed by this re-run:")
        lines.append("")
        lines.extend(_table(
            [(row["entry"],
              "`" + str(row["pre_fix"])[:16] + "`" if row["pre_fix"]
              else "(not recorded)",
              "`" + str(row["post_fix"])[:16] + "`" if row["post_fix"]
              else "(not recorded)",
              "yes" if row["identical"] else "NO")
             for row in freeze["entries"]],
            ["entry", "pre-fix sha256", "post-fix sha256", "identical"]))
        lines.append("")
        if freeze["entries_that_differ"]:
            lines.append("Entries that are NOT identical: `"
                         + "`, `".join(freeze["entries_that_differ"])
                         + "`. Each is explained in the notes below.")
        else:
            lines.append("Every frozen input entry is byte-identical.")
        lines.append("")
    lines.extend([
        "## Agency-guard interventions (defect D3)",
        "",
        "The determiner false positive truncated a sentence at the "
        "determiner and deleted the ACTIVE actor's own quoted content "
        "whenever it addressed a determined recipient "
        "(`sends a message to THE <role name>: \"...\"`).",
        "",
        f"- pre-fix: **{payload['guard_interventions_pre']}** guard "
        "interventions",
        f"- post-fix: **{payload['guard_interventions_post']}** guard "
        "interventions",
        f"- change: **{-payload['guard_interventions_removed']:+d}**",
        "",
        "The raw count is not by itself the D3 measurement: the guard has "
        "other, deliberate detection classes that the fix did not touch, "
        "and live sampling changes how often each one is triggered. The "
        "class split is in the notes at the end of this document.",
        "",
    ])
    if pre["guard"]["per_branch"] or post["guard"]["per_branch"]:
        lines.extend(_table(
            [(branch,
              pre["guard"]["per_branch"].get(branch, "-"),
              post["guard"]["per_branch"].get(branch, "-"))
             for branch in branches],
            ["branch", "pre-fix interventions", "post-fix interventions"]))
        lines.append("")
    lines.extend([
        "## Per-branch contract facts",
        "",
        "`intervention_delivered` and `unresolved_observers` are the two "
        "fields the fixes ADDED to `BranchResult`. The pre-fix run "
        "carries neither: that is reported as *not measured*, never as a "
        "value, because claiming a measurement the pre-fix run never made "
        "would be the same error the fixes exist to prevent.",
        "",
    ])
    rows = []
    for branch in branches:
        left = pre["branches"].get(branch, {})
        right = post["branches"].get(branch, {})
        rows.append((
            branch,
            left.get("terminal_status") or "-",
            right.get("terminal_status") or "-",
            "not measured" if not left.get(
                "intervention_delivered_field_present")
            else f"`{left.get('intervention_delivered')}`",
            "not measured" if not right.get(
                "intervention_delivered_field_present")
            else f"`{right.get('intervention_delivered')}`",
            "not recorded" if not left.get(
                "unresolved_observers_field_present")
            else str(left.get("unresolved_observer_count")),
            "not recorded" if not right.get(
                "unresolved_observers_field_present")
            else str(right.get("unresolved_observer_count")),
        ))
    lines.extend(_table(rows, [
        "branch", "terminal (pre)", "terminal (post)",
        "delivered (pre)", "delivered (post)",
        "unresolved observers (pre)", "unresolved observers (post)"]))
    lines.extend([
        "",
        "## Unresolved observer names (defect D1)",
        "",
        "Upstream `ObservationQueue.add` creates a queue key for whatever "
        "string the game master's free-text observer answer produced, so a "
        "name that matches no roster entity was dropped with no error and "
        "no record. The fix rosters a validated observer seam and records "
        "every non-resolving name verbatim. Nothing about routing changed "
        "-- only the silence.",
        "",
    ])
    pre_obs = payload.get("unresolved_observers_pre") or {}
    post_obs = payload.get("unresolved_observers_post") or {}
    lines.append(
        "- pre-fix: **not recorded at all** (the field did not exist; a "
        "dropped observer left no trace)"
        if not pre_obs.get("measured")
        else f"- pre-fix: **{pre_obs.get('total')}** recorded")
    lines.append(
        f"- post-fix: **{post_obs.get('total', 0)}** non-resolving observer "
        "names recorded"
        if post_obs.get("measured")
        else "- post-fix: not recorded")
    lines.append("")
    if post_obs.get("by_name"):
        lines.extend(_table(
            [(f"`{name}`", count) for name, count in
             post_obs["by_name"].items()],
            ["observer name the game master produced", "occurrences"]))
        lines.append("")
        lines.append("Resolution reasons: `"
                     + "`, `".join(f"{reason}={count}" for reason, count
                                   in post_obs["by_reason"].items()) + "`.")
        lines.append("")
        lines.append(
            "Every one of these events was DROPPED -- before and after the "
            "fix. The fix does not deliver them (delivering an event to a "
            "guessed actor is a worse failure than not delivering it); it "
            "makes the loss visible instead of silent.")
        lines.append("")
    elif post_obs.get("measured"):
        lines.append(
            "No observer name failed to resolve in this re-run, so no "
            "event was dropped by this path.")
        lines.append("")
    lines.extend([
        "## Ranking",
        "",
        f"- pre-fix: **{pre['ranking']['outcome']}**"
        + (f" (winner `{pre['ranking']['best_candidate_id']}`)"
           if pre["ranking"]["best_candidate_id"] else ""),
        f"- post-fix: **{post['ranking']['outcome']}**"
        + (f" (winner `{post['ranking']['best_candidate_id']}`)"
           if post["ranking"]["best_candidate_id"] else ""),
        "",
    ])
    if post["ranking"]["outcome"] == "REFUSED":
        lines.extend([
            "The refusal is the correct result, not a failure of the "
            "re-run. `sworldmodel.outcomes.ranking` refuses to name a "
            "winner when no measured branch delivered its intervention to "
            "any actor other than the insertion actor -- which is exactly "
            "what the pre-fix run did while publishing a winner anyway. "
            "The engine's verbatim reason:",
            "",
            "```",
            str(post["ranking"]["reason"] or ""),
            "```",
            "",
        ])
    lines.extend([
        "## Delivery check",
        "",
    ])
    lines.extend(_table(
        [("verdict", f"`{pre['delivery']['verdict']}`",
          f"`{post['delivery']['verdict']}`"),
         ("distinct recipient first-turn prompts",
          pre["delivery"]["distinct_recipient_first_turn_prompts"],
          post["delivery"]["distinct_recipient_first_turn_prompts"])],
        ["measure", "pre-fix", "post-fix"]))
    lines.append("")
    if post["cutoff"]:
        cut_pre = pre["cutoff"]
        cut_post = post["cutoff"]
        lines.extend([
            "## Historical cutoff re-verification",
            "",
            "The counterfactual is set before 2025-07-01, so the boundary "
            "is enforced mechanically at three stages plus a canary the "
            "validator must reject.",
            "",
        ])
        lines.extend(_table(
            [("enforced stages", f"`{cut_pre.get('enforced_stages')}`",
              f"`{cut_post.get('enforced_stages')}`"),
             ("pre-simulation scan clean",
              cut_pre.get("pre_simulation_clean"),
              cut_post.get("pre_simulation_clean")),
             ("pre-simulation surfaces scanned",
              cut_pre.get("pre_simulation_surface_count"),
              cut_post.get("pre_simulation_surface_count")),
             ("post-run prompt violations",
              cut_pre.get("post_run_prompt_violations"),
              cut_post.get("post_run_prompt_violations")),
             ("post-run model-response findings (advisory)",
              cut_pre.get("post_run_response_findings"),
              cut_post.get("post_run_response_findings")),
             ("canary rejected by the validator",
              cut_pre.get("canary_rejected"),
              cut_post.get("canary_rejected")),
             ("overall clean", cut_pre.get("overall_clean"),
              cut_post.get("overall_clean"))],
            ["stage", "pre-fix", "post-fix"]))
        lines.append("")
        if cut_post.get("pre_compile_stage"):
            lines.append(
                "The pre-compile stage is not repeated: this re-run reuses "
                "the original compile phase's frozen compiler artifact "
                "directory byte-for-byte (see "
                "`frozen_input_verification.json`), and that phase's scan "
                "is recorded at `"
                + str(cut_post["pre_compile_stage"].get("recorded_in"))
                + "`.")
            lines.append("")
    if post["branch_input_isolation"]:
        lines.extend([
            "## Branch-input isolation",
            "",
            f"- pre-fix verdict: "
            f"`{pre['branch_input_isolation'].get('verdict')}`",
            f"- post-fix verdict: "
            f"`{post['branch_input_isolation'].get('verdict')}`",
            "",
        ])
    if post["instrumentation"]:
        lines.extend([
            "## Instrumentation",
            "",
        ])
        lines.extend(_table(
            [("live calls", pre["instrumentation"].get("live_calls"),
              post["instrumentation"].get("live_calls")),
             ("errors", pre["instrumentation"].get("errors"),
              post["instrumentation"].get("errors")),
             ("retries", pre["instrumentation"].get("retries"),
              post["instrumentation"].get("retries")),
             ("three counters agree",
              pre["instrumentation"].get("all_equal"),
              post["instrumentation"].get("all_equal"))],
            ["measure", "pre-fix", "post-fix"]))
        lines.append("")
    if payload.get("notes"):
        lines.extend(["## Notes", ""])
        lines.extend(f"- {note}" for note in payload["notes"])
        lines.append("")
    return "\n".join(lines) + "\n"


def write_comparison(out_dir, payload: dict) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pre_vs_post_fix.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    path = out_dir / "PRE_VS_POST_FIX.md"
    path.write_text(build_comparison(payload), encoding="utf-8")
    return path


__all__ = ["FROZEN_INPUT_ENTRIES", "FrozenInputMismatch",
           "verify_frozen_inputs", "compare_freeze_manifests",
           "scenario_facts", "unresolved_observer_summary",
           "compare_scenarios", "session_call_accounting",
           "build_comparison", "write_comparison"]
