"""Causal trace report: the COMPLETE recorded causal chain of one run.

``build_trace_report`` produces one deterministic artifact holding, for
every branch of a counterfactual run, everything needed to audit HOW the
measured outcome came about -- read exclusively from the run record and
the strict branch contracts, never recomputed and never paraphrased:

- **initialization identity**: base plan id + content hash, genesis
  snapshot id, the run's base seed, and per branch the branch plan id +
  content hash and the code-owned branch seed;
- **committed events, in commit order**: the branch's ``event_trace``
  verbatim (code-owned event ids + committed descriptions) -- the only
  licensed source of outcomes;
- **guard interventions**: every agency-guard rewrite record the runner
  captured (step, active player, affected actors, original and rewritten
  excerpts);
- **actor records**: per actor, the observation rows the actor actually
  received (its recorded memory stream, in order) and its attempts (the
  acted text per engine step, extracted from the runner's raw log entity
  records); attempts by entities outside the plan roster are surfaced in
  ``unattributed_attempts``, never dropped;
- **terminal state**: the explicit terminal status, steps completed, the
  terminal world state verbatim, and every recorded infrastructure error;
- **evaluator citations**: each measured metric with the exact
  ``event:``/``state:`` references it was computed from, re-resolved here
  against this same report's committed events and terminal state -- a
  citation that does not resolve refuses the report.

A branch that failed before its runner could return has
``runner_record_available = false`` and carries its (empty) contract
trace plus the recorded errors -- reported in place, never dropped.

Deterministic serialization: the canonical JSON form (sorted keys,
compact, ASCII) is the hashing base, so mapping order can never leak
into the bytes; wall-clock runtime and token statistics are deliberately
excluded (diagnostics, not causal content -- and they would make the
hash vary between byte-identical runs).  Every report, freshly built or
reloaded, passes the single strict gate :func:`validate_trace_report`.

Pure stdlib; no LLM anywhere; no scenario vocabulary (the hardcoding
guard scans this package on both interpreters).
"""

from __future__ import annotations

import copy
import re

from sworldmodel.decision.contracts import (BranchResult,
                                            ContractValidationError,
                                            IssueCollector, MetricValue,
                                            TERMINAL_STATUSES,
                                            ValidationIssue)

from .common import (canonical_content_hash, canonical_json,
                     require_run_attributes)

TRACE_REPORT_VERSION = "trace_report_v1"
REPORT_KIND = "causal_trace_report"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
#: upstream raw-log key naming the acting entity of one engine step
_ENTITY_KEY_RE = re.compile(r"^Entity \[(.+)\]$")

_RUN_ATTRIBUTES = ("base_plan", "base_plan_content_hash", "base_snapshot",
                   "branch_plans", "branch_ids", "branch_seeds", "results",
                   "runner_records")

_REPORT_KEYS = ("report_kind", "report_version", "world_id",
                "base_plan_id", "base_plan_content_hash",
                "base_snapshot_id", "base_seed", "branches")

_BRANCH_KEYS = (
    "candidate_id", "branch_id", "branch_seed", "branch_plan_id",
    "branch_plan_content_hash", "terminal_status", "steps_completed",
    "runner_record_available", "committed_events", "guard_interventions",
    "actor_records", "unattributed_attempts", "terminal_world_state",
    "infrastructure_errors", "evaluation_citations")

_GUARD_RECORD_KEYS = ("step", "active", "affected", "original_excerpt",
                      "rewritten_excerpt")


def _fail(path: str, code: str, message: str) -> None:
    raise ContractValidationError([ValidationIssue(path, code, message)])


def build_trace_report(run, evaluated_results=None) -> dict:
    """Assemble and validate the causal trace report for one run.

    ``evaluated_results``, when supplied, must be order-aligned with
    ``run.results`` and is the authoritative per-branch contract view
    (it carries the evaluator's cited metrics and terminal-status
    verdict); without it the run's own (unevaluated) results are
    reported, with empty ``evaluation_citations``.  Raises
    ``ContractValidationError`` with every collected defect; never
    repairs.
    """
    issues = IssueCollector()
    require_run_attributes(run, _RUN_ATTRIBUTES, issues)
    issues.raise_if_any()

    results = tuple(run.results if evaluated_results is None
                    else evaluated_results)
    if not results:
        _fail("run.results", "empty_collection",
              "a trace report needs at least one branch result")
    for index, result in enumerate(results):
        if not isinstance(result, BranchResult):
            issues.add(f"results[{index}]", "wrong_type",
                       "expected a BranchResult instance, got "
                       f"{type(result).__name__}")
    issues.raise_if_any()
    run_ids = tuple(result.candidate_id for result in run.results)
    result_ids = tuple(result.candidate_id for result in results)
    if result_ids != run_ids:
        _fail("evaluated_results", "inconsistent_ranking",
              "evaluated_results must be order-aligned with run.results "
              f"over the same candidates; got {list(result_ids)} vs "
              f"{list(run_ids)}")

    base_plan = run.base_plan
    world_id = base_plan.world_id
    recorded_hash = base_plan.content_hash()
    if recorded_hash != run.base_plan_content_hash:
        _fail("run.base_plan_content_hash", "invalid_value",
              "the run's recorded base plan hash "
              f"{run.base_plan_content_hash!r} does not match the base "
              f"plan's actual content hash {recorded_hash!r}")
    base_seed = run.base_snapshot.sidecar.rng.get("base_seed")
    if type(base_seed) is not int:
        _fail("run.base_snapshot.sidecar.rng.base_seed", "missing_field",
              "the run's genesis snapshot must record the integer base "
              "seed")

    branches = []
    for result in results:
        branches.append(_branch_entry(run, result, world_id, issues))
    issues.raise_if_any()

    report = {
        "report_kind": REPORT_KIND,
        "report_version": TRACE_REPORT_VERSION,
        "world_id": world_id,
        "base_plan_id": base_plan.plan_id,
        "base_plan_content_hash": run.base_plan_content_hash,
        "base_snapshot_id": run.base_snapshot.snapshot_id,
        "base_seed": base_seed,
        "branches": branches,
    }
    validate_trace_report(report)
    return report


def _branch_entry(run, result: BranchResult, world_id: str,
                  issues: IssueCollector) -> dict:
    candidate_id = result.candidate_id
    path = f"branches.{candidate_id}"
    if result.world_id != world_id:
        issues.add(path, "cross_branch_reference",
                   f"branch of world {result.world_id!r} supplied for a "
                   f"report on world {world_id!r}")
    branch_plan = run.branch_plans.get(candidate_id)
    if branch_plan is None:
        issues.add(f"{path}.branch_plan", "missing_field",
                   "the run records no branch plan for candidate "
                   f"{candidate_id!r}")
        return {}
    expected_branch = run.branch_ids.get(candidate_id)
    if result.branch_id != expected_branch:
        issues.add(f"{path}.branch_id", "cross_branch_reference",
                   f"branch id {result.branch_id!r} does not match the "
                   f"run's recorded {expected_branch!r}")
    branch_seed = run.branch_seeds.get(candidate_id)
    if type(branch_seed) is not int:
        issues.add(f"{path}.branch_seed", "missing_field",
                   "the run must record an integer branch seed")

    raw = run.runner_records.get(candidate_id)
    committed_events = [event.to_dict() for event in result.event_trace]
    if raw is not None:
        if raw.get("event_trace") != committed_events:
            issues.add(
                f"{path}.committed_events", "invalid_value",
                "the runner record's event trace does not equal the "
                "branch contract's event trace; a trace report must "
                "never disagree with the contract of record")
        guard_interventions = copy.deepcopy(
            raw.get("guard_interventions", []))
        steps_completed = raw.get("steps_completed")
        if type(steps_completed) is not int or steps_completed < 0:
            issues.add(f"{path}.steps_completed", "wrong_type",
                       "the runner record must carry an integer step "
                       "count >= 0")
    else:
        guard_interventions = []
        steps_completed = None

    actor_records, unattributed = _actor_records(
        run.base_plan, raw, f"{path}.actor_records", issues)

    return {
        "candidate_id": candidate_id,
        "branch_id": result.branch_id,
        "branch_seed": branch_seed,
        "branch_plan_id": branch_plan.plan_id,
        "branch_plan_content_hash": branch_plan.content_hash(),
        "terminal_status": result.terminal_status,
        "steps_completed": steps_completed,
        "runner_record_available": raw is not None,
        "committed_events": committed_events,
        "guard_interventions": guard_interventions,
        "actor_records": actor_records,
        "unattributed_attempts": unattributed,
        "terminal_world_state": copy.deepcopy(result.terminal_world_state),
        "infrastructure_errors": list(result.infrastructure_errors),
        "evaluation_citations": {
            name: metric.to_dict()
            for name, metric in result.outcome_metrics.items()},
    }


def _actor_records(base_plan, raw, path, issues):
    """Per-actor observation rows and per-step attempts, extracted
    deterministically from the runner record; entities outside the plan
    roster are surfaced separately, never dropped."""
    records = {}
    for config in base_plan.actor_configs:
        records[config.actor_id] = {"name": config.name,
                                    "observations": [], "attempts": []}
    unattributed = []
    if raw is None:
        return records, unattributed

    memories = raw.get("actor_memories", {})
    if not isinstance(memories, dict):
        issues.add(f"{path}.observations", "wrong_type",
                   "the runner record's actor_memories must be a mapping")
        return records, unattributed
    for actor_id, rows in memories.items():
        if actor_id not in records:
            issues.add(f"{path}.{actor_id}", "unknown_reference",
                       f"the runner recorded memory for {actor_id!r}, "
                       "which is not a plan-configured actor")
            continue
        records[actor_id]["observations"] = [str(row) for row in rows]

    name_to_id = {config.name: config.actor_id
                  for config in base_plan.actor_configs}
    for entry_index, entry in enumerate(raw.get("raw_log", ())):
        if not isinstance(entry, dict):
            issues.add(f"{path}.raw_log[{entry_index}]", "wrong_type",
                       "raw log entries must be mappings")
            continue
        step = entry.get("Step")
        for key in sorted(entry):
            match = _ENTITY_KEY_RE.match(key)
            if match is None:
                continue
            block = entry[key]
            act = block.get("__act__") if isinstance(block, dict) else None
            if not isinstance(act, dict):
                continue
            attempt = act.get("Value")
            if not isinstance(attempt, str):
                issues.add(
                    f"{path}.raw_log[{entry_index}]", "wrong_type",
                    f"the acted value for entity {match.group(1)!r} is "
                    f"not a string ({type(attempt).__name__}); refusing "
                    "to fabricate an attempt record")
                continue
            record = {"step": step if type(step) is int else None,
                      "attempt": attempt}
            actor_id = name_to_id.get(match.group(1))
            if actor_id is None:
                unattributed.append({"entity": match.group(1), **record})
            else:
                records[actor_id]["attempts"].append(record)
    return records, unattributed


def trace_report_canonical_json(report: dict) -> str:
    """Canonical JSON text of one trace report."""
    return canonical_json(report)


def trace_report_content_hash(report: dict) -> str:
    """sha256 identity of one trace report's canonical JSON."""
    return canonical_content_hash(report)


def validate_trace_report(report) -> None:
    """The single strict gate every trace report passes through.

    Verifies the exact key sets, the terminal-status enum, unique branch
    and candidate identifiers, unique committed-event identifiers, the
    guard-record shape, the actor-record shape, and -- centrally -- that
    every evaluation citation resolves to a committed event or terminal
    state key OF THIS SAME REPORT.  Raises ``ContractValidationError``
    with every collected defect.
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
    if report["report_version"] != TRACE_REPORT_VERSION:
        issues.add("report_version", "version_mismatch",
                   f"expected {TRACE_REPORT_VERSION!r}, got "
                   f"{report['report_version']!r}")
    for path in ("world_id", "base_plan_id", "base_snapshot_id"):
        if not isinstance(report[path], str) or not report[path].strip():
            issues.add(path, "wrong_type",
                       f"{path} must be a non-empty string")
    if not isinstance(report["base_plan_content_hash"], str) \
            or not _HEX64_RE.match(report["base_plan_content_hash"]):
        issues.add("base_plan_content_hash", "invalid_value",
                   "must be a 64-character lowercase hex sha256")
    if type(report["base_seed"]) is not int:
        issues.add("base_seed", "wrong_type",
                   "base_seed must be an integer")

    branches = report["branches"]
    if not isinstance(branches, list) or not branches:
        issues.add("branches", "wrong_type",
                   "expected a non-empty list of branch entries")
    issues.raise_if_any()

    candidate_ids = []
    branch_ids = []
    for index, branch in enumerate(branches):
        _check_branch(branch, f"branches[{index}]", issues)
        if isinstance(branch, dict):
            candidate_ids.append(branch.get("candidate_id"))
            branch_ids.append(branch.get("branch_id"))
    if len(set(candidate_ids)) != len(candidate_ids):
        issues.add("branches", "duplicate_id",
                   "branch candidate identifiers must be unique")
    if len(set(branch_ids)) != len(branch_ids):
        issues.add("branches", "duplicate_id",
                   "branch identifiers must be unique")
    issues.raise_if_any()

    # The whole report must serialize canonically (deterministic bytes).
    canonical_json(report)


def _check_branch(branch, path, issues) -> None:
    if not isinstance(branch, dict):
        issues.add(path, "wrong_type",
                   f"expected mapping, got {type(branch).__name__}")
        return
    for key in branch:
        if key not in _BRANCH_KEYS:
            issues.add(f"{path}.{key}", "unknown_field",
                       f"unknown branch field {key!r}")
    missing = [key for key in _BRANCH_KEYS if key not in branch]
    if missing:
        issues.add(path, "missing_field",
                   f"branch fields missing: {', '.join(missing)}")
        return

    if branch["terminal_status"] not in TERMINAL_STATUSES:
        issues.add(f"{path}.terminal_status", "invalid_enum",
                   f"{branch['terminal_status']!r} is not a terminal "
                   f"status; allowed: {', '.join(TERMINAL_STATUSES)}")
    for key in ("candidate_id", "branch_id", "branch_plan_id"):
        if not isinstance(branch[key], str) or not branch[key].strip():
            issues.add(f"{path}.{key}", "wrong_type",
                       f"{key} must be a non-empty string")
    if not isinstance(branch["branch_plan_content_hash"], str) \
            or not _HEX64_RE.match(branch["branch_plan_content_hash"]):
        issues.add(f"{path}.branch_plan_content_hash", "invalid_value",
                   "must be a 64-character lowercase hex sha256")
    if type(branch["branch_seed"]) is not int:
        issues.add(f"{path}.branch_seed", "wrong_type",
                   "branch_seed must be an integer")
    available = branch["runner_record_available"]
    if type(available) is not bool:
        issues.add(f"{path}.runner_record_available", "wrong_type",
                   "runner_record_available must be a boolean")
        available = None
    steps = branch["steps_completed"]
    if available is True and (type(steps) is not int or steps < 0):
        issues.add(f"{path}.steps_completed", "wrong_type",
                   "steps_completed must be an integer >= 0 when the "
                   "runner record is available")
    if available is False and steps is not None:
        issues.add(f"{path}.steps_completed", "invalid_value",
                   "steps_completed must be null when no runner record "
                   "exists; a step count is never fabricated")
    if not isinstance(branch["infrastructure_errors"], list):
        issues.add(f"{path}.infrastructure_errors", "wrong_type",
                   "infrastructure_errors must be a list")

    event_ids = _check_committed_events(
        branch["committed_events"], f"{path}.committed_events", issues)
    _check_guard_records(branch["guard_interventions"],
                         f"{path}.guard_interventions", issues)
    _check_actor_records(branch["actor_records"],
                         f"{path}.actor_records", issues)
    if not isinstance(branch["unattributed_attempts"], list):
        issues.add(f"{path}.unattributed_attempts", "wrong_type",
                   "unattributed_attempts must be a list")
    state = branch["terminal_world_state"]
    if not isinstance(state, dict):
        issues.add(f"{path}.terminal_world_state", "wrong_type",
                   "terminal_world_state must be a mapping")
        state = {}
    _check_citations(branch["evaluation_citations"], event_ids,
                     set(state.keys()), f"{path}.evaluation_citations",
                     issues)


def _check_committed_events(events, path, issues):
    if not isinstance(events, list):
        issues.add(path, "wrong_type",
                   "committed_events must be a list")
        return set()
    event_ids = []
    for index, event in enumerate(events):
        event_path = f"{path}[{index}]"
        if not isinstance(event, dict) \
                or sorted(event) != ["description", "event_id"]:
            issues.add(event_path, "wrong_type",
                       "each committed event is a mapping with exactly "
                       "'event_id' and 'description'")
            continue
        if not isinstance(event["event_id"], str) \
                or not isinstance(event["description"], str):
            issues.add(event_path, "wrong_type",
                       "event_id and description must be strings")
            continue
        event_ids.append(event["event_id"])
    if len(set(event_ids)) != len(event_ids):
        issues.add(path, "duplicate_id",
                   "committed event identifiers must be unique")
    return set(event_ids)


def _check_guard_records(records, path, issues) -> None:
    if not isinstance(records, list):
        issues.add(path, "wrong_type",
                   "guard_interventions must be a list")
        return
    for index, record in enumerate(records):
        record_path = f"{path}[{index}]"
        if not isinstance(record, dict) \
                or sorted(record) != sorted(_GUARD_RECORD_KEYS):
            issues.add(record_path, "wrong_type",
                       "each guard record is a mapping with exactly "
                       f"{', '.join(_GUARD_RECORD_KEYS)}")
            continue
        if type(record["step"]) is not int or record["step"] < 1:
            issues.add(f"{record_path}.step", "wrong_type",
                       "guard record step must be an integer >= 1")
        if not isinstance(record["active"], str):
            issues.add(f"{record_path}.active", "wrong_type",
                       "guard record active player must be a string")
        affected = record["affected"]
        if not isinstance(affected, list) or not affected \
                or not all(isinstance(name, str) for name in affected):
            issues.add(f"{record_path}.affected", "wrong_type",
                       "guard record affected must be a non-empty list "
                       "of actor names")
        for key in ("original_excerpt", "rewritten_excerpt"):
            if not isinstance(record[key], str):
                issues.add(f"{record_path}.{key}", "wrong_type",
                           f"guard record {key} must be a string")


def _check_actor_records(records, path, issues) -> None:
    if not isinstance(records, dict) or not records:
        issues.add(path, "wrong_type",
                   "actor_records must be a non-empty mapping keyed by "
                   "actor identifier")
        return
    for actor_id, record in records.items():
        record_path = f"{path}.{actor_id}"
        if not isinstance(record, dict) \
                or sorted(record) != ["attempts", "name", "observations"]:
            issues.add(record_path, "wrong_type",
                       "each actor record is a mapping with exactly "
                       "'name', 'observations', and 'attempts'")
            continue
        if not isinstance(record["name"], str) or not record["name"]:
            issues.add(f"{record_path}.name", "wrong_type",
                       "actor name must be a non-empty string")
        observations = record["observations"]
        if not isinstance(observations, list) \
                or not all(isinstance(row, str) for row in observations):
            issues.add(f"{record_path}.observations", "wrong_type",
                       "observations must be a list of strings")
        attempts = record["attempts"]
        if not isinstance(attempts, list):
            issues.add(f"{record_path}.attempts", "wrong_type",
                       "attempts must be a list")
            continue
        for index, attempt in enumerate(attempts):
            attempt_path = f"{record_path}.attempts[{index}]"
            if not isinstance(attempt, dict) \
                    or sorted(attempt) != ["attempt", "step"]:
                issues.add(attempt_path, "wrong_type",
                           "each attempt is a mapping with exactly "
                           "'step' and 'attempt'")
                continue
            if not isinstance(attempt["attempt"], str):
                issues.add(f"{attempt_path}.attempt", "wrong_type",
                           "the attempt text must be a string")
            if attempt["step"] is not None \
                    and type(attempt["step"]) is not int:
                issues.add(f"{attempt_path}.step", "wrong_type",
                           "the attempt step must be an integer or null")


def _check_citations(citations, event_ids, state_keys, path,
                     issues) -> None:
    if not isinstance(citations, dict):
        issues.add(path, "wrong_type",
                   "evaluation_citations must be a mapping keyed by "
                   "metric name")
        return
    local = IssueCollector()
    for name, raw in citations.items():
        metric_path = f"{path}.{name}"
        metric = MetricValue.parse(raw, metric_path, local)
        if metric is None:
            continue
        for ref_index, ref in enumerate(metric.computed_from):
            kind, _, target = ref.partition(":")
            if kind == "event" and target in event_ids:
                continue
            if kind == "state" and target in state_keys:
                continue
            local.add(f"{metric_path}.computed_from[{ref_index}]",
                      "unknown_reference",
                      f"citation {ref!r} does not resolve to a committed "
                      "event or terminal state key of this report")
    issues.extend(local.items)
