"""The semantic world compiler.

question + frozen evidence -> semantic scenario (model) -> independent review
(model) -> deterministic lowering (no model) -> the existing runtime.

The runtime is not re-implemented anywhere here; this package only builds
worlds for it.
"""
from .errors import (ALL_STAGES, COMPILED, CompilationStop, InsufficientEvidence,
                     InvalidReference, LoweringGap, NoCausalProducer,
                     NothingScheduled, RealityReviewRejected, SemanticAmbiguity)
from .lower import CompiledWorld, Lowerer, lower
from .minds import CompiledLLMMind, MechanicalMind, llm_minds, mechanical_minds
from .schema import (CHANGE_TYPES, OBSERVATION_TYPES, PRECONDITION_TYPES,
                     SECTIONS, contract_document, validate)
from .symbols import SymbolTable, fact_key, slug

__all__ = [n for n in dir() if not n.startswith("_")]
