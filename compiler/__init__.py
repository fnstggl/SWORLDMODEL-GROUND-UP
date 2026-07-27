"""The world compiler: natural-language question -> smallest runnable model
of the real situation, lowered onto the sworldmodel runtime.

Three layers, strictly separated:

1. LLM describes the possible world in natural language (never its future).
2. LLM translates one small item at a time into the closed capability menu
   (select a capability, fill its small fields, or return UNSUPPORTED).
3. Deterministic code assembles, validates, lowers, round-trips, and has the
   result adversarially reviewed.  Zero scenario meaning lives in code.
"""
from .pipeline import CompileResult, compile_question, instantiate

__all__ = ["CompileResult", "compile_question", "instantiate"]
