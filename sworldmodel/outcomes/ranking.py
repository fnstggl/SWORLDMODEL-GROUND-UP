"""Deterministic ranking: the declared metrics, in declared order, and
nothing else.

``rank_branches`` orders evaluated branch results by the DECLARED
evaluator metrics ONLY and produces the Phase 3 ``RecommendationResult``.
The rank key is the declared metric sequence itself: the primary metric
first, then each SECONDARY metric in the ``EvaluatorSpec``'s declared
order, every component compared descending -- highest value first,
booleans as 1/0, polarity NOT inferred (the user's declaration supplies
both the metrics and their priority order; this module invents neither
direction nor weight).  Only when two candidates are exactly tied on
EVERY declared metric does the final code-owned tie-break apply:
``candidate_id`` in ascending lexicographic order.  That final tie-break
is disclosed verbatim in the result's ``run_limitations`` text and is
flagged in ``validation_status`` ONLY when it actually decided an
adjacent ordering, so no reader can mistake a tie-break for a measured
difference -- and a fully measured ranking visibly carries no such flag.
No other input, no heuristic, and no model influences the order; the
winner is the computed ordering's head, never an override.

Secondary metrics are never weighted or aggregated: when criteria
conflict the result returns the measured tradeoff (the directive forbids
invented weights).  Concretely:

- ``metric_differences``  -- for every declared metric, each candidate's
  numeric distance from the ranking winner's value on that metric
  (winner's own entry is 0.0; booleans as 1/0);
- ``downside_outcomes``   -- per candidate, the measured secondary values
  verbatim, annotated with which are the strict minimum / maximum across
  the candidates tested.  No polarity is assumed: whether a high or a low
  value is bad belongs to the declared metrics' meaning, which this
  generic engine does not know; both extremes are surfaced so each
  candidate's worst-case position in either direction is visible.

``run_limitations`` carries the mandatory fixed limitation phrase and
exactly the caller-declared result-provenance label (``deterministic``,
``live_model``, or ``synthetic_infrastructure``).

Pure stdlib; no LLM anywhere.
"""

from __future__ import annotations

import json

from sworldmodel.decision.contracts import (BranchResult,
                                            EvaluatorSpec, IssueCollector,
                                            RESULT_PROVENANCE_LABELS,
                                            REQUIRED_LIMITATION_PHRASE,
                                            RecommendationResult,
                                            SCHEMA_VERSION)
from sworldmodel.decision.validation import validate_semantics


def _rank_key(value) -> float:
    return (1.0 if value else 0.0) if type(value) is bool else float(value)


def _render_value(value) -> str:
    return json.dumps(value)


def _limitations_text(primary: str, provenance_label: str,
                      tie_break_used: bool) -> str:
    tie_note = (", applied in this ranking" if tie_break_used
                else "; not needed in this ranking")
    return (
        f"Result provenance: {provenance_label}. This result identifies "
        f"the {REQUIRED_LIMITATION_PHRASE} under the declared evaluator "
        "metrics, computed only from recorded simulation traces; it is "
        "not a guarantee of real-world outcome. Ranking uses the "
        f"declared metrics only: the primary metric ({primary}) first, "
        "then each secondary metric compared descending in declared "
        "order (highest value first; polarity not inferred); any "
        "remaining exact tie is broken by candidate_id in ascending "
        f"lexicographic order (code-owned final tie-break{tie_note}).")


def _downside_text(candidate_id: str, values_by_metric: dict,
                   secondaries: tuple) -> str:
    if not secondaries:
        return ("no secondary metrics declared; only the primary metric "
                "was measured for this candidate")
    parts: list = []
    for name in secondaries:
        value = values_by_metric[name][candidate_id]
        key = _rank_key(value)
        others = [_rank_key(other)
                  for cid, other in values_by_metric[name].items()
                  if cid != candidate_id]
        marks: list = []
        if others and all(key < other for other in others):
            marks.append("strict minimum among candidates tested")
        if others and all(key > other for other in others):
            marks.append("strict maximum among candidates tested")
        rendered = f"{name}={_render_value(value)}"
        if marks:
            rendered += f" ({'; '.join(marks)})"
        parts.append(rendered)
    return "measured secondary outcomes: " + ", ".join(parts)


def rank_branches(
    results,
    evaluator_spec: EvaluatorSpec,
    *,
    provenance_label: str,
    registry=None,
) -> RecommendationResult:
    """Rank evaluated branches and build the ``RecommendationResult``.

    Every result must carry a measured value for EVERY declared metric
    (evaluate first, rank second); candidate identifiers must be unique.
    ``registry``, when given, joins the Phase 3 semantic validation of
    the finished recommendation, which is always run against the supplied
    results and spec before returning.  Raises
    ``ContractValidationError`` with every collected defect.
    """
    issues = IssueCollector()
    results = tuple(results)
    if not results:
        issues.add("results", "empty_collection",
                   "at least one evaluated branch result is required")
    for index, result in enumerate(results):
        if not isinstance(result, BranchResult):
            issues.add(f"results[{index}]", "wrong_type",
                       "expected a BranchResult instance, got "
                       f"{type(result).__name__}")
    if not isinstance(evaluator_spec, EvaluatorSpec):
        issues.add("evaluator_spec", "wrong_type",
                   "evaluator_spec must be an EvaluatorSpec instance, got "
                   f"{type(evaluator_spec).__name__}")
    if provenance_label not in RESULT_PROVENANCE_LABELS:
        issues.add("provenance_label", "invalid_enum",
                   f"{provenance_label!r} is not a result-provenance "
                   f"label; allowed: "
                   f"{', '.join(RESULT_PROVENANCE_LABELS)}")
    issues.raise_if_any()

    candidate_ids = [result.candidate_id for result in results]
    if len(set(candidate_ids)) != len(candidate_ids):
        issues.add("results", "duplicate_id",
                   "one evaluated result per candidate: duplicate "
                   "candidate identifiers were supplied")
    metric_names = evaluator_spec.all_metrics()
    for index, result in enumerate(results):
        for name in metric_names:
            if name not in result.outcome_metrics:
                issues.add(
                    f"results[{index}].outcome_metrics.{name}",
                    "missing_field",
                    f"candidate {result.candidate_id!r} carries no "
                    f"measured value for declared metric {name!r}; "
                    "evaluate every branch before ranking")
    issues.raise_if_any()

    # Rank key: every DECLARED metric in declared order (primary first,
    # then the secondaries), each compared descending; candidate_id is
    # the FINAL code-owned tie-break and decides only a full-key tie.
    primary = evaluator_spec.primary_metric

    def _declared_key(result) -> tuple:
        return tuple(_rank_key(result.outcome_metrics[name].value)
                     for name in metric_names)

    ordered = sorted(
        results,
        key=lambda result: tuple(
            -component for component in _declared_key(result)
        ) + (result.candidate_id,))
    declared_keys = [_declared_key(result) for result in ordered]
    tie_break_used = any(declared_keys[i] == declared_keys[i + 1]
                         for i in range(len(declared_keys) - 1))

    values_by_metric = {
        name: {result.candidate_id: result.outcome_metrics[name].value
               for result in ordered}
        for name in metric_names}
    best = ordered[0]
    best_values = {name: _rank_key(values_by_metric[name][best.candidate_id])
                   for name in metric_names}
    metric_differences = {
        name: {candidate_id: _rank_key(value) - best_values[name]
               for candidate_id, value in values_by_metric[name].items()}
        for name in metric_names}
    downside_outcomes = {
        result.candidate_id: _downside_text(
            result.candidate_id, values_by_metric,
            evaluator_spec.secondary_metrics)
        for result in ordered}

    # The final tie-break is FLAGGED only when it actually decided an
    # adjacent ordering; a fully measured ranking carries no such flag.
    validation_status = {
        "schema_validated": True,
        "semantics_validated": True,
        "ranked_by_declared_metrics_in_declared_order": True,
        "all_branches_free_of_infrastructure_errors": all(
            not result.infrastructure_errors for result in results),
    }
    if tie_break_used:
        validation_status["tie_break_candidate_id_lexicographic"] = True

    recommendation = RecommendationResult.from_dict({
        "contract_type": RecommendationResult.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "best_candidate_id": best.candidate_id,
        "ranking": [
            {"candidate_id": result.candidate_id,
             "metric_values": {
                 name: result.outcome_metrics[name].value
                 for name in metric_names}}
            for result in ordered],
        "metric_differences": metric_differences,
        "downside_outcomes": downside_outcomes,
        "run_limitations": _limitations_text(primary, provenance_label,
                                             tie_break_used),
        "validation_status": validation_status,
    })
    validate_semantics(recommendation, registry, branch_results=results,
                       evaluator_spec=evaluator_spec)
    return recommendation
