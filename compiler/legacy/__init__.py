"""LEGACY multi-stage world compiler (~200 LLM calls per compile).

NOT the production path.  Kept only behind the explicit diagnostic flag
``compile_question.py --compiler legacy`` for comparison; nothing in the
production route imports this package (see PRODUCTION_ROUTE_AUDIT.md), and
it must never be selected automatically.  The canonical compiler is
minimal_scene_v1 (compiler.compile_scene)."""
from .pipeline import CompileResult, compile_question, instantiate

__all__ = ["CompileResult", "compile_question", "instantiate"]
