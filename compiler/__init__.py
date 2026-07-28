"""SWORLDMODEL world compilation.

Production path: **minimal_scene_v1** -- two semantic LLM calls normally
(scene construction + independent adversarial review), three maximum (one
targeted correction), then deterministic validation and direct
instantiation into the persistent runtime.  The scene manifest has exactly
four fields: actors (name + private_context), shared_context,
starting_events, resolution.

The legacy multi-stage compiler lives in ``compiler.legacy`` and is
reachable ONLY via the explicit ``--compiler legacy`` diagnostic flag --
importing this package does not import it."""
from .scene_llm import SceneCaller
from .scene_pipeline import (COMPILER_VERSION, SceneCompileResult,
                             compile_scene, instantiate_compiled)

__all__ = ["COMPILER_VERSION", "SceneCaller", "SceneCompileResult",
           "compile_scene", "instantiate_compiled"]
