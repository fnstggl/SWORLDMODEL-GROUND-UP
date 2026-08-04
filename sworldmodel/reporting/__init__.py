"""Reporting (Phase 9): deterministic decision artifacts for one run.

Two artifact builders over the counterfactual run record and the frozen
Phase 3 contracts -- assembly and serialization only; nothing here runs a
simulation, calls a model, measures an outcome, or overrides a ranking:

- ``recommendation`` -- the recommendation report: the DecisionProblem,
  the frozen base identity, the candidates, the per-branch cited
  evaluations, and the ``RecommendationResult`` computed through the
  existing ranking engine, all content-hashed and strictly re-validated
  through the frozen contracts' ``from_dict`` gates.
- ``trace_report`` -- the complete causal trace: initialization plan
  hashes and seeds, committed events in commit order, guard
  interventions, per-actor observation and attempt records, terminal
  world state, and evaluator citations re-resolved against the report's
  own trace rows.

Both artifacts are deterministic by construction (canonical JSON, no
wall-clock content, no set-order leaks) and scenario-generic (the
hardcoding guard scans this package on both interpreters).  Pure stdlib.
"""

from .recommendation import (RECOMMENDATION_REPORT_VERSION,
                             build_recommendation_report,
                             report_canonical_json, report_content_hash,
                             validate_recommendation_report)
from .trace_report import (TRACE_REPORT_VERSION, build_trace_report,
                           trace_report_canonical_json,
                           trace_report_content_hash,
                           validate_trace_report)

__all__ = [
    "RECOMMENDATION_REPORT_VERSION",
    "TRACE_REPORT_VERSION",
    "build_recommendation_report",
    "build_trace_report",
    "report_canonical_json",
    "report_content_hash",
    "trace_report_canonical_json",
    "trace_report_content_hash",
    "validate_recommendation_report",
    "validate_trace_report",
]
