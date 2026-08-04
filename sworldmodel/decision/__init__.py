"""Decision and branch contracts: fixed, versioned, code-owned schemas with
strict validation, a code-owned identifier registry, semantic reference
checks, and the strict loader for the frozen manual fixtures.

Pure stdlib.  Scenario content enters only as data (fixtures, compiled
worlds), never as code."""

from .contracts import (BranchResult, CandidateProvenance,
                        CompiledDecisionWorld, CompilerProvenance,
                        ConcordiaInitializationPlan, ContractValidationError,
                        CONTRACT_CLASSES, CANDIDATE_SOURCES, DecisionProblem,
                        EngineCursor, EvaluatorSpec, InterventionCandidate,
                        InterventionInsertionPoint, IssueCollector,
                        MetricValue, PlanActorConfig, RankingEntry,
                        RecommendationResult, REQUIRED_LIMITATION_PHRASE,
                        RESULT_PROVENANCE_LABELS, SCHEMA_VERSION,
                        SIDECAR_COMPONENTS, SimulationSnapshot,
                        SnapshotSidecar, StartingEvent, TERMINAL_STATUSES,
                        TimeHorizon, TraceEvent, ValidationIssue, WorldActor,
                        canonical_time)
from .fixture_loader import (ExpectedDeterministic, FIXTURE_LOADER_VERSION,
                             FIXTURE_SOURCE, LoadedFixture,
                             load_fixture_dict, load_fixture_file)
from .registry import ContractRegistry
from .validation import validate_schema, validate_semantics

__all__ = [name for name in dir() if not name.startswith("_")]
