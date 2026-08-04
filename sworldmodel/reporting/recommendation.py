"""Recommendation report: the frozen recommendation contract in context.

``build_recommendation_report`` assembles ONE self-contained, fully
deterministic report for a completed decision run:

- the ``DecisionProblem`` verbatim (the product question), with its
  content hash;
- the run's frozen base identity (base plan id + content hash, genesis
  snapshot id, world id);
- the declared ``EvaluatorSpec`` verbatim;
- every ``InterventionCandidate`` verbatim, with per-candidate content
  hashes;
- one branch-evaluation record per candidate, in the caller's candidate
  order: branch id, code-owned branch seed, the explicit terminal status,
  and the CITED outcome metrics (each value carries the exact
  ``event:``/``state:`` references it was computed from);
- the frozen ``RecommendationResult`` computed here through the existing
  ranking engine (``sworldmodel.outcomes.rank_branches``) -- never
  supplied from outside, so no caller can override the measured ordering
  -- with its content hash, the winner, and ``decided_by_metric`` (the
  declared metric that separated the top two, or the disclosed
  tie-break) surfaced at top level.

Deliberately EXCLUDED: wall-clock runtime and token statistics.  They are
diagnostics, not decision content, and embedding them would make the
report's content hash vary between byte-identical runs.  The full
``BranchResult`` objects (which carry them) remain the contract of
record; this report embeds their deterministic evaluation core.

Every report -- freshly built or reloaded from disk -- passes through the
single strict gate :func:`validate_recommendation_report`, which
re-parses each embedded contract through its frozen ``from_dict`` and
re-checks the content hashes and the internal consistency (winner ==
ranking head, ranking values == the cited branch measurements), raising
``ContractValidationError`` with every collected defect.  Nothing is
repaired silently.

Pure stdlib; no LLM anywhere; no scenario vocabulary (the hardcoding
guard scans this package on both interpreters).
"""

from __future__ import annotations

import re

from sworldmodel.decision.contracts import (BranchResult,
                                            ContractValidationError,
                                            DecisionProblem, EvaluatorSpec,
                                            InterventionCandidate,
                                            IssueCollector, MetricValue,
                                            RecommendationResult,
                                            TERMINAL_STATUSES,
                                            ValidationIssue)
from sworldmodel.outcomes import rank_branches

from .common import (canonical_content_hash, canonical_json,
                     require_run_attributes)

RECOMMENDATION_REPORT_VERSION = "recommendation_report_v1"
REPORT_KIND = "decision_recommendation_report"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

_RUN_ATTRIBUTES = ("base_plan", "base_plan_content_hash", "base_snapshot",
                   "branch_ids", "branch_seeds", "results")

_REPORT_KEYS = (
    "report_kind", "report_version", "problem", "problem_content_hash",
    "world_id", "base_plan_id", "base_plan_content_hash",
    "base_snapshot_id", "evaluator_spec", "candidates",
    "candidate_content_hashes", "branch_evaluations", "recommendation",
    "recommendation_content_hash", "winner", "decided_by_metric")

_EVALUATION_KEYS = ("candidate_id", "branch_id", "branch_seed",
                    "terminal_status", "outcome_metrics",
                    "infrastructure_errors", "committed_event_count")


def _fail(path: str, code: str, message: str) -> None:
    raise ContractValidationError([ValidationIssue(path, code, message)])


def build_recommendation_report(
    problem: DecisionProblem,
    candidates,
    run,
    evaluated_results,
    evaluator_spec: EvaluatorSpec,
    *,
    provenance_label: str,
    registry=None,
) -> dict:
    """Assemble and validate the recommendation report for one run.

    ``candidates`` and ``evaluated_results`` must be order-aligned with
    ``run.results`` (the caller's candidate order); every branch must
    already carry its cited outcome metrics (evaluate first, report
    second).  The ``RecommendationResult`` is computed HERE through
    ``rank_branches`` with the caller's ``provenance_label`` and optional
    registry.  Raises ``ContractValidationError`` with every collected
    defect; never repairs, never reorders.
    """
    issues = IssueCollector()
    if not isinstance(problem, DecisionProblem):
        issues.add("problem", "wrong_type",
                   "expected a DecisionProblem instance, got "
                   f"{type(problem).__name__}")
    if not isinstance(evaluator_spec, EvaluatorSpec):
        issues.add("evaluator_spec", "wrong_type",
                   "expected an EvaluatorSpec instance, got "
                   f"{type(evaluator_spec).__name__}")
    require_run_attributes(run, _RUN_ATTRIBUTES, issues)
    candidates = tuple(candidates)
    if not candidates:
        issues.add("candidates", "empty_collection",
                   "at least one intervention candidate is required")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, InterventionCandidate):
            issues.add(f"candidates[{index}]", "wrong_type",
                       "expected an InterventionCandidate instance, got "
                       f"{type(candidate).__name__}")
    evaluated_results = tuple(evaluated_results)
    for index, result in enumerate(evaluated_results):
        if not isinstance(result, BranchResult):
            issues.add(f"evaluated_results[{index}]", "wrong_type",
                       "expected a BranchResult instance, got "
                       f"{type(result).__name__}")
    issues.raise_if_any()

    candidate_ids = tuple(c.candidate_id for c in candidates)
    if len(set(candidate_ids)) != len(candidate_ids):
        _fail("candidates", "duplicate_id",
              "candidate identifiers must be unique")
    run_ids = tuple(result.candidate_id for result in run.results)
    evaluated_ids = tuple(result.candidate_id
                          for result in evaluated_results)
    if evaluated_ids != run_ids or candidate_ids != run_ids:
        _fail("evaluated_results", "inconsistent_ranking",
              "candidates, run.results, and evaluated_results must be "
              "order-aligned over the same candidate identifiers; got "
              f"candidates={list(candidate_ids)}, run={list(run_ids)}, "
              f"evaluated={list(evaluated_ids)}")

    base_plan = run.base_plan
    world_id = base_plan.world_id
    recorded_hash = base_plan.content_hash()
    if recorded_hash != run.base_plan_content_hash:
        _fail("run.base_plan_content_hash", "invalid_value",
              "the run's recorded base plan hash "
              f"{run.base_plan_content_hash!r} does not match the base "
              f"plan's actual content hash {recorded_hash!r}")
    for index, result in enumerate(evaluated_results):
        path = f"evaluated_results[{index}]"
        if result.world_id != world_id:
            issues.add(path, "cross_branch_reference",
                       f"branch of world {result.world_id!r} supplied for "
                       f"a report on world {world_id!r}")
        expected_branch = run.branch_ids.get(result.candidate_id)
        if result.branch_id != expected_branch:
            issues.add(f"{path}.branch_id", "cross_branch_reference",
                       f"branch id {result.branch_id!r} does not match the "
                       f"run's recorded {expected_branch!r} for candidate "
                       f"{result.candidate_id!r}")
        seed = run.branch_seeds.get(result.candidate_id)
        if type(seed) is not int:
            issues.add(f"run.branch_seeds.{result.candidate_id}",
                       "missing_field",
                       "the run must record an integer branch seed for "
                       f"candidate {result.candidate_id!r}")
    issues.raise_if_any()

    recommendation = rank_branches(
        evaluated_results, evaluator_spec,
        provenance_label=provenance_label, registry=registry)

    branch_evaluations = []
    for result in evaluated_results:
        branch_evaluations.append({
            "candidate_id": result.candidate_id,
            "branch_id": result.branch_id,
            "branch_seed": run.branch_seeds[result.candidate_id],
            "terminal_status": result.terminal_status,
            "outcome_metrics": {
                name: metric.to_dict()
                for name, metric in result.outcome_metrics.items()},
            "infrastructure_errors": list(result.infrastructure_errors),
            "committed_event_count": len(result.event_trace),
        })

    report = {
        "report_kind": REPORT_KIND,
        "report_version": RECOMMENDATION_REPORT_VERSION,
        "problem": problem.to_dict(),
        "problem_content_hash": problem.content_hash(),
        "world_id": world_id,
        "base_plan_id": base_plan.plan_id,
        "base_plan_content_hash": run.base_plan_content_hash,
        "base_snapshot_id": run.base_snapshot.snapshot_id,
        "evaluator_spec": evaluator_spec.to_dict(),
        "candidates": [candidate.to_dict() for candidate in candidates],
        "candidate_content_hashes": {
            candidate.candidate_id: candidate.content_hash()
            for candidate in candidates},
        "branch_evaluations": branch_evaluations,
        "recommendation": recommendation.to_dict(),
        "recommendation_content_hash": recommendation.content_hash(),
        "winner": recommendation.best_candidate_id,
        "decided_by_metric":
            recommendation.validation_status.get("decided_by_metric"),
    }
    validate_recommendation_report(report)
    return report


def report_canonical_json(report: dict) -> str:
    """Canonical JSON text of one recommendation report."""
    return canonical_json(report)


def report_content_hash(report: dict) -> str:
    """sha256 identity of one recommendation report's canonical JSON."""
    return canonical_content_hash(report)


def validate_recommendation_report(report) -> None:
    """The single strict gate every recommendation report passes through.

    Verifies structure (exact key set), re-parses every embedded contract
    through its frozen ``from_dict``, re-computes and compares every
    content hash, and re-checks internal consistency: the winner is the
    ranking head, ``decided_by_metric`` matches the recommendation's own
    record, the ranked candidates are exactly the reported candidates,
    and every ranking metric value equals the cited branch measurement it
    summarizes.  Raises ``ContractValidationError`` with every collected
    defect.
    """
    issues = IssueCollector()
    if not isinstance(report, dict):
        _fail("", "wrong_type",
              f"expected a report mapping, got {type(report).__name__}")
    for key in report:
        if key not in _REPORT_KEYS:
            issues.add(key, "unknown_field",
                       f"unknown report field {key!r}")
    for key in _REPORT_KEYS:
        if key not in report:
            issues.add(key, "missing_field",
                       f"required report field {key!r} is missing")
    issues.raise_if_any()

    if report["report_kind"] != REPORT_KIND:
        issues.add("report_kind", "invalid_value",
                   f"expected {REPORT_KIND!r}, got "
                   f"{report['report_kind']!r}")
    if report["report_version"] != RECOMMENDATION_REPORT_VERSION:
        issues.add("report_version", "version_mismatch",
                   f"expected {RECOMMENDATION_REPORT_VERSION!r}, got "
                   f"{report['report_version']!r}")
    issues.raise_if_any()

    # Embedded contracts: strict from_dict round-trip + hash equality.
    problem = _parse_embedded(DecisionProblem, report["problem"],
                              "problem", issues)
    if problem is not None \
            and problem.content_hash() != report["problem_content_hash"]:
        issues.add("problem_content_hash", "invalid_value",
                   "recorded problem hash does not match the embedded "
                   "problem's content hash")
    spec = _parse_spec(report["evaluator_spec"], issues)
    recommendation = _parse_embedded(RecommendationResult,
                                     report["recommendation"],
                                     "recommendation", issues)
    if recommendation is not None and recommendation.content_hash() \
            != report["recommendation_content_hash"]:
        issues.add("recommendation_content_hash", "invalid_value",
                   "recorded recommendation hash does not match the "
                   "embedded recommendation's content hash")

    candidates = []
    raw_candidates = report["candidates"]
    if not isinstance(raw_candidates, list) or not raw_candidates:
        issues.add("candidates", "wrong_type",
                   "expected a non-empty list of embedded candidates")
    else:
        for index, raw in enumerate(raw_candidates):
            candidate = _parse_embedded(InterventionCandidate, raw,
                                        f"candidates[{index}]", issues)
            if candidate is not None:
                candidates.append(candidate)
    hash_map = report["candidate_content_hashes"]
    if not isinstance(hash_map, dict):
        issues.add("candidate_content_hashes", "wrong_type",
                   "expected a mapping of candidate_id to sha256")
    elif len(candidates) == len(raw_candidates):
        expected_ids = [c.candidate_id for c in candidates]
        if sorted(hash_map) != sorted(expected_ids):
            issues.add("candidate_content_hashes", "unknown_reference",
                       "hash map keys must be exactly the embedded "
                       "candidate identifiers")
        else:
            for candidate in candidates:
                if hash_map[candidate.candidate_id] \
                        != candidate.content_hash():
                    issues.add(
                        f"candidate_content_hashes."
                        f"{candidate.candidate_id}", "invalid_value",
                        "recorded candidate hash does not match the "
                        "embedded candidate's content hash")
    issues.raise_if_any()

    for path in ("world_id", "base_plan_id", "base_snapshot_id"):
        if not isinstance(report[path], str) or not report[path].strip():
            issues.add(path, "wrong_type",
                       f"{path} must be a non-empty string")
    if not isinstance(report["base_plan_content_hash"], str) \
            or not _HEX64_RE.match(report["base_plan_content_hash"]):
        issues.add("base_plan_content_hash", "invalid_value",
                   "must be a 64-character lowercase hex sha256")

    # Internal consistency: winner, decided_by_metric, id alignment.
    ranked_ids = [entry.candidate_id for entry in recommendation.ranking]
    if report["winner"] != recommendation.best_candidate_id:
        issues.add("winner", "inconsistent_ranking",
                   f"winner {report['winner']!r} does not match the "
                   "embedded recommendation's best_candidate_id "
                   f"{recommendation.best_candidate_id!r}")
    if ranked_ids and recommendation.best_candidate_id != ranked_ids[0]:
        issues.add("recommendation", "inconsistent_ranking",
                   "best_candidate_id must equal the first ranking entry")
    recorded_decider = recommendation.validation_status.get(
        "decided_by_metric")
    if not isinstance(recorded_decider, str) or not recorded_decider:
        issues.add("recommendation.validation_status.decided_by_metric",
                   "missing_field",
                   "the embedded recommendation must record which "
                   "declared metric (or disclosed tie-break) decided the "
                   "ordering")
    if report["decided_by_metric"] != recorded_decider:
        issues.add("decided_by_metric", "inconsistent_ranking",
                   f"decided_by_metric {report['decided_by_metric']!r} "
                   "does not match the embedded recommendation's record "
                   f"{recorded_decider!r}")
    candidate_ids = [c.candidate_id for c in candidates]
    if sorted(ranked_ids) != sorted(candidate_ids):
        issues.add("recommendation", "inconsistent_ranking",
                   f"ranked candidates {sorted(ranked_ids)} are not the "
                   f"reported candidates {sorted(candidate_ids)}")

    evaluations = _check_branch_evaluations(
        report["branch_evaluations"], candidate_ids, issues)
    issues.raise_if_any()

    # Ranking values must equal the cited branch measurements: the
    # recommendation summarizes measurements, it never overrides them.
    metric_names = spec.all_metrics()
    by_candidate = {entry["candidate_id"]: entry for entry in evaluations}
    for index, entry in enumerate(recommendation.ranking):
        evaluation = by_candidate.get(entry.candidate_id)
        if evaluation is None:
            continue
        for name in metric_names:
            ranked_value = entry.metric_values.get(name)
            measured = evaluation["outcome_metrics"].get(name)
            if measured is None:
                issues.add(
                    f"branch_evaluations.{entry.candidate_id}"
                    f".outcome_metrics.{name}", "missing_field",
                    f"declared metric {name!r} has no cited measurement "
                    "in the branch evaluation record")
                continue
            if measured.value != ranked_value \
                    or type(measured.value) is not type(ranked_value):
                issues.add(
                    f"ranking[{index}].metric_values.{name}",
                    "invalid_value",
                    f"ranking value {ranked_value!r} does not equal the "
                    f"cited branch measurement {measured.value!r}")
    issues.raise_if_any()

    # The whole report must serialize canonically (deterministic bytes).
    canonical_json(report)


def _parse_embedded(cls, raw, path, issues):
    try:
        return cls.from_dict(raw)
    except ContractValidationError as exc:
        issues.extend(ValidationIssue(f"{path}.{issue.path}", issue.code,
                                      issue.message)
                      for issue in exc.issues)
        return None


def _parse_spec(raw, issues):
    local = IssueCollector()
    spec = EvaluatorSpec.parse(raw, "evaluator_spec", local)
    issues.extend(local.items)
    if spec is None:
        issues.raise_if_any()
    return spec


def _check_branch_evaluations(raw, candidate_ids, issues):
    """Strictly parse the per-candidate evaluation records; returns the
    entries with ``outcome_metrics`` parsed into ``MetricValue``."""
    if not isinstance(raw, list) or not raw:
        issues.add("branch_evaluations", "wrong_type",
                   "expected a non-empty list of evaluation records")
        return []
    entries = []
    seen_ids = []
    for index, entry in enumerate(raw):
        path = f"branch_evaluations[{index}]"
        if not isinstance(entry, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(entry).__name__}")
            continue
        for key in entry:
            if key not in _EVALUATION_KEYS:
                issues.add(f"{path}.{key}", "unknown_field",
                           f"unknown evaluation field {key!r}")
        missing = [key for key in _EVALUATION_KEYS if key not in entry]
        if missing:
            issues.add(path, "missing_field",
                       f"evaluation fields missing: {', '.join(missing)}")
            continue
        parsed = dict(entry)
        seen_ids.append(entry["candidate_id"])
        if entry["terminal_status"] not in TERMINAL_STATUSES:
            issues.add(f"{path}.terminal_status", "invalid_enum",
                       f"{entry['terminal_status']!r} is not a terminal "
                       f"status; allowed: {', '.join(TERMINAL_STATUSES)}")
        if type(entry["branch_seed"]) is not int:
            issues.add(f"{path}.branch_seed", "wrong_type",
                       "branch_seed must be an integer")
        if type(entry["committed_event_count"]) is not int \
                or entry["committed_event_count"] < 0:
            issues.add(f"{path}.committed_event_count", "wrong_type",
                       "committed_event_count must be an integer >= 0")
        if not isinstance(entry["infrastructure_errors"], list):
            issues.add(f"{path}.infrastructure_errors", "wrong_type",
                       "infrastructure_errors must be a list")
        metrics_raw = entry["outcome_metrics"]
        if not isinstance(metrics_raw, dict):
            issues.add(f"{path}.outcome_metrics", "wrong_type",
                       "outcome_metrics must be a mapping")
            continue
        parsed_metrics = {}
        local = IssueCollector()
        for name, value in metrics_raw.items():
            metric = MetricValue.parse(
                value, f"{path}.outcome_metrics.{name}", local)
            if metric is not None:
                parsed_metrics[name] = metric
        issues.extend(local.items)
        parsed["outcome_metrics"] = parsed_metrics
        entries.append(parsed)
    if sorted(seen_ids) != sorted(candidate_ids):
        issues.add("branch_evaluations", "inconsistent_ranking",
                   f"evaluation records cover {sorted(seen_ids)} but the "
                   f"reported candidates are {sorted(candidate_ids)}")
    return entries
