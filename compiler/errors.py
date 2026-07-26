"""Explicit compilation outcomes.

Every stop has a stage, so a failure names the layer that is broken instead
of collapsing into "compilation failed".  Nothing is ever silently repaired.
"""
from __future__ import annotations


class CompilationStop(Exception):
    """Compilation stopped at a named stage, with the exact reason."""

    stage = "UNKNOWN"

    def __init__(self, reason: str, detail: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or {}

    def to_dict(self) -> dict:
        return {"stage": self.stage, "reason": self.reason, "detail": self.detail}


class InsufficientEvidence(CompilationStop):
    """The evidence package cannot support a causally sufficient world."""
    stage = "INSUFFICIENT_EVIDENCE"


class SemanticAmbiguity(CompilationStop):
    """The semantic scenario is internally ambiguous (e.g. two participants
    share a name, or a reference matches more than one thing)."""
    stage = "SEMANTIC_AMBIGUITY"


class RealityReviewRejected(CompilationStop):
    """The independent reviewer refused the scenario."""
    stage = "REALITY_REVIEW_REJECTED"


class LoweringGap(CompilationStop):
    """The scenario expresses a meaning the universal runtime cannot carry.
    Refused rather than approximated."""
    stage = "LOWERING_GAP"


class InvalidReference(CompilationStop):
    """A name refers to something that does not exist in the scenario."""
    stage = "INVALID_REFERENCE"


class NoCausalProducer(CompilationStop):
    """A terminal component has nothing in the world that could produce it."""
    stage = "NO_CAUSAL_PRODUCER"


class NothingScheduled(CompilationStop):
    """The world has no executable root event: time would never advance."""
    stage = "NOTHING_SCHEDULED"


COMPILED = "COMPILED"

ALL_STAGES = (
    "INSUFFICIENT_EVIDENCE", "SEMANTIC_AMBIGUITY", "REALITY_REVIEW_REJECTED",
    "LOWERING_GAP", "INVALID_REFERENCE", "NO_CAUSAL_PRODUCER",
    "NOTHING_SCHEDULED", COMPILED,
)
