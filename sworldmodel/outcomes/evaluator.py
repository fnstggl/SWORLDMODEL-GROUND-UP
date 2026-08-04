"""Outcome evaluation: cited metric values for one ``BranchResult``.

Fully generic engine.  The caller supplies the predicates (see
``metrics`` for the predicate contract); when the declared
``EvaluatorSpec`` is passed, EXACTLY its metrics (primary plus
secondaries, by NAME) are computed -- the predicate mapping is treated as
a library and unrelated entries are ignored, while a spec metric without
a predicate is a hard error.  Without a spec, every supplied predicate is
computed.

Citation requirement: every metric value must carry the events / state
it was computed from.  A predicate returns ``(value, citations)``;
integer citations are normalized to ``'event:<event_id>'`` references
against the branch's OWN trace, explicit string references must resolve
against that trace or the branch's terminal world state, and an empty
citation list is rejected -- a metric that cites nothing is not a
measurement.  (Phase 3 semantic validation re-checks the same resolution
on the finished result.)

Terminal-status verdict (contract rule R3): the runner never reports
``success`` or ``failure`` -- that verdict belongs to this layer, reading
the measured metrics.  The caller may pass
``status_rule(metric_values, default_status)``: returning ``None`` keeps
the runner's status; returning a terminal status adopts it.  A branch
with recorded infrastructure errors can never be promoted to ``success``
or ``failure`` -- a broken run has no outcome verdict.

No LLM anywhere.  Nothing here overrides a measured value; the evaluator
only computes and records.
"""

from __future__ import annotations

import math

from sworldmodel.decision.contracts import (BranchResult,
                                            ContractValidationError,
                                            EvaluatorSpec, IssueCollector,
                                            MetricValue, TERMINAL_STATUSES)
from sworldmodel.decision.validation import validate_semantics

_VERDICT_STATUSES = ("success", "failure")


def _check_metric_value(value, path, issues):
    if type(value) is bool:
        return value
    if type(value) in (int, float):
        if isinstance(value, float) and not math.isfinite(value):
            issues.add(path, "invalid_value",
                       "a measured number must be finite")
            return None
        return value
    issues.add(path, "wrong_type",
               "a measured value must be a boolean or a finite number, "
               f"got {type(value).__name__}")
    return None


def _normalize_citations(citations, result: BranchResult, path, issues):
    """Ints -> ``event:<event_id>`` by trace position; strings must be
    resolvable references; order preserved, duplicates collapsed."""
    if isinstance(citations, (str, bytes)) \
            or not hasattr(citations, "__iter__"):
        issues.add(path, "wrong_type",
                   "citations must be a sequence of trace indices and/or "
                   "'event:'/'state:' reference strings, got "
                   f"{type(citations).__name__}")
        return None
    trace = result.event_trace
    event_ids = {event.event_id for event in trace}
    state_keys = set(result.terminal_world_state.keys())
    refs: list = []
    ok = True
    items = list(citations)
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        if type(item) is int:
            if not 0 <= item < len(trace):
                issues.add(item_path, "unknown_reference",
                           f"trace index {item} is outside the recorded "
                           f"trace of {len(trace)} event(s)")
                ok = False
                continue
            refs.append(f"event:{trace[item].event_id}")
            continue
        if isinstance(item, str):
            kind, _, target = item.partition(":")
            if kind == "event" and target in event_ids:
                refs.append(item)
                continue
            if kind == "state" and target in state_keys:
                refs.append(item)
                continue
            issues.add(item_path, "unknown_reference",
                       f"citation {item!r} does not resolve to a recorded "
                       "trace event or terminal state key")
            ok = False
            continue
        issues.add(item_path, "wrong_type",
                   "each citation must be a trace index (int) or an "
                   "'event:'/'state:' reference string, got "
                   f"{type(item).__name__}")
        ok = False
    if not ok:
        return None
    deduped: list = []
    for ref in refs:
        if ref not in deduped:
            deduped.append(ref)
    if not deduped:
        issues.add(path, "empty_collection",
                   "a metric that cites nothing is not a measurement; "
                   "return (value, citations) with at least one citation "
                   "or build the predicate with the matcher API")
        return None
    return tuple(deduped)


def _select_metric_names(predicates, evaluator_spec, issues):
    if evaluator_spec is None:
        if not predicates:
            issues.add("predicates", "empty_collection",
                       "at least one metric predicate is required")
            return ()
        return tuple(sorted(predicates))
    if not isinstance(evaluator_spec, EvaluatorSpec):
        issues.add("evaluator_spec", "wrong_type",
                   "evaluator_spec must be an EvaluatorSpec instance, got "
                   f"{type(evaluator_spec).__name__}")
        return ()
    return evaluator_spec.all_metrics()


def evaluate_branch(
    result: BranchResult,
    predicates,
    *,
    evaluator_spec: EvaluatorSpec | None = None,
    status_rule=None,
    registry=None,
) -> BranchResult:
    """Compute cited outcome metrics for one branch; return the updated
    ``BranchResult`` (the input object is never mutated).

    ``predicates`` maps metric name to the predicate contract described
    in ``metrics``; ``evaluator_spec`` selects which names apply;
    ``status_rule`` optionally decides the terminal-status verdict from
    the measured metrics (see module docstring); ``registry``, when
    given, re-runs Phase 3 semantic validation on the finished result.
    Raises ``ContractValidationError`` with every collected defect.
    """
    issues = IssueCollector()
    if not isinstance(result, BranchResult):
        issues.add("result", "wrong_type",
                   "expected a BranchResult instance, got "
                   f"{type(result).__name__}")
    if not hasattr(predicates, "get") or not hasattr(predicates, "keys"):
        issues.add("predicates", "wrong_type",
                   "predicates must be a mapping of metric name to "
                   f"predicate, got {type(predicates).__name__}")
    if status_rule is not None and not callable(status_rule):
        issues.add("status_rule", "wrong_type",
                   "status_rule must be callable when supplied")
    issues.raise_if_any()

    metric_names = _select_metric_names(predicates, evaluator_spec, issues)
    issues.raise_if_any()

    result_dict = result.to_dict()
    measured: dict = {}
    for name in metric_names:
        path = f"outcome_metrics.{name}"
        predicate = predicates.get(name)
        if predicate is None:
            issues.add(path, "missing_field",
                       f"the declared metric {name!r} has no predicate; "
                       "every declared metric needs an injected predicate")
            continue
        if not callable(predicate):
            issues.add(path, "wrong_type",
                       f"the predicate for {name!r} is not callable")
            continue
        try:
            reading = predicate(result.event_trace, result_dict)
        except ContractValidationError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported with context
            issues.add(path, "invalid_value",
                       f"the predicate for {name!r} raised "
                       f"{type(exc).__name__}: {exc}")
            continue
        if not isinstance(reading, (tuple, list)) or len(reading) != 2:
            issues.add(
                path, "wrong_type",
                f"the predicate for {name!r} must return the pair "
                "(value, citations); a bare value carries no citations "
                f"(got {type(reading).__name__})")
            continue
        raw_value, raw_citations = reading
        value = _check_metric_value(raw_value, f"{path}.value", issues)
        citations = _normalize_citations(
            raw_citations, result, f"{path}.computed_from", issues)
        if value is None or citations is None:
            continue  # the defect was collected above; raised below
        measured[name] = MetricValue(value=value, computed_from=citations)
    issues.raise_if_any()

    final_status = result.terminal_status
    if status_rule is not None:
        verdict = status_rule(dict(measured), result.terminal_status)
        if verdict is not None:
            if verdict not in TERMINAL_STATUSES:
                issues.add("terminal_status", "invalid_enum",
                           f"status_rule returned {verdict!r}; allowed: "
                           f"{', '.join(TERMINAL_STATUSES)} or None")
            elif verdict in _VERDICT_STATUSES \
                    and result.infrastructure_errors:
                issues.add(
                    "terminal_status", "invalid_value",
                    f"status_rule returned {verdict!r} for a branch with "
                    "recorded infrastructure errors; a broken run has no "
                    "outcome verdict")
            else:
                final_status = verdict
        issues.raise_if_any()

    updated = dict(result_dict)
    updated["outcome_metrics"] = {
        name: metric.to_dict() for name, metric in measured.items()}
    updated["terminal_status"] = final_status
    evaluated = BranchResult.from_dict(updated)
    if registry is not None:
        validate_semantics(evaluated, registry)
    return evaluated


def evaluate_branches(
    results,
    predicates,
    *,
    evaluator_spec: EvaluatorSpec | None = None,
    status_rule=None,
    registry=None,
) -> tuple:
    """Serial convenience map of :func:`evaluate_branch` over many
    branches, preserving order."""
    return tuple(
        evaluate_branch(result, predicates, evaluator_spec=evaluator_spec,
                        status_rule=status_rule, registry=registry)
        for result in results)
