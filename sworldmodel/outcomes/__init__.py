"""Trace-based outcome evaluation and ranking (Phase 6).

Generic engine: this package knows no metric, no scenario, and no model.
The caller supplies metric predicates; every measured value must cite the
recorded events / terminal state it was computed from; ranking follows
the declared evaluator metrics, in their declared order, and nothing
else.  Module map:

- ``metrics``   -- matcher toolkit building CITED readings from the
  recorded event trace (existence / count over caller-supplied text
  matchers, with an explicit whole-trace citation rule for absence).
- ``evaluator`` -- compute ``outcome_metrics`` for one ``BranchResult``
  from injected predicates (optionally selected by the declared
  ``EvaluatorSpec``), with an optional caller-owned terminal-status rule.
- ``ranking``   -- deterministic total order by the declared metrics in
  declared order (primary first, secondaries next, all descending,
  polarity not inferred; candidate_id only as the final disclosed
  tie-break), producing the Phase 3 ``RecommendationResult`` -- and
  REFUSING to produce one (``InterventionNotDeliveredError``) when every
  branch whose delivery was measured failed to deliver its intervention.

Pure stdlib; no LLM anywhere; nothing here overrides a measured value.
"""

from .evaluator import evaluate_branch, evaluate_branches
from .metrics import (WHOLE_TRACE_CITATION, count_metric, event_description,
                      exists_metric, matching_indices, substring_matcher)
from .ranking import InterventionNotDeliveredError, rank_branches

__all__ = [
    "InterventionNotDeliveredError",
    "WHOLE_TRACE_CITATION",
    "count_metric",
    "evaluate_branch",
    "evaluate_branches",
    "event_description",
    "exists_metric",
    "matching_indices",
    "rank_branches",
    "substring_matcher",
]
