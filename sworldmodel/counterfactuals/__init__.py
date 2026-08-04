"""Counterfactual branch manager (Phase 6, local execution).

One frozen base, one intervention per branch, serial deterministic runs,
explicit failure reporting.  Module map:

- ``snapshot`` -- build the base initialization plan ONCE (via the Phase 4
  planner) and freeze its genesis identity as a Phase 3
  ``SimulationSnapshot``; code-owned per-branch seed derivation.
- ``branch``   -- apply exactly one ``InterventionCandidate`` at the plan's
  single code-owned insertion boundary; ``diff_plans`` proves the branch
  differs nowhere else; code-owned ``branch_id`` derivation.
- ``manager``  -- ``run_candidates``: serial, seeded, isolated execution of
  every candidate branch into Phase 3 ``BranchResult`` objects.

This package is pure stdlib and scenario-agnostic: models and metric
predicates are injected by the caller, no LLM is ever created or called
here, and the engine-facing backend (``sworldmodel.backends`` --
``concordia_local``) is imported lazily inside the run path only.
"""

from .branch import (apply_intervention, derive_branch_id, diff_plans,
                     insertion_path_prefix)
from .manager import (CounterfactualRun, run_candidates,
                      run_candidates_detailed)
from .snapshot import (build_base_plan, build_base_snapshot,
                       derive_branch_seed)

__all__ = [
    "CounterfactualRun",
    "apply_intervention",
    "build_base_plan",
    "build_base_snapshot",
    "derive_branch_id",
    "derive_branch_seed",
    "diff_plans",
    "insertion_path_prefix",
    "run_candidates",
    "run_candidates_detailed",
]
