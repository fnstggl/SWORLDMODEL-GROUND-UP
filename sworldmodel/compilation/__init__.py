"""SWORLDMODEL compilation bridge: existing compiler output -> frozen
decision contracts.

Two deterministic, LLM-free modules:

- :mod:`.existing_compiler_adapter` -- maps one validated compiled scene
  (manifest mapping + compile metadata, or a persisted compiler
  ``out_dir`` artifact set) into a validated ``CompiledDecisionWorld``,
  with a complete provenance/sidecar record of every field the contract
  does not express.  The field-by-field mapping contract is
  docs/engine_migration/COMPILER_TO_CONCORDIA_MAPPING.md.
- :mod:`.decision_route` -- the lightweight ``DecisionProblem`` route:
  user-supplied candidate actions and a minimal one-fixed-schema
  candidate generator behind the existing model seam, producing the
  ``(CompiledDecisionWorld, candidates)`` pair the existing
  counterfactual manager consumes.

The adapter path stops at ``CompiledDecisionWorld``; the proven planner
(``sworldmodel.backends.concordia_local.planner``) and builder own the
rest of the chain.  Importing this package imports neither the compiler
package nor any engine backend.
"""

from .decision_route import (DECISION_ROUTE_VERSION, DEFAULT_MAX_GENERATED,
                             DecisionRunInputs, GENERATOR_PROMPT_TEMPLATE,
                             GENERATOR_RESPONSE_SCHEMA, GENERATOR_VERSION,
                             build_generator_prompt, build_user_candidates,
                             generate_candidates, generator_config_hash,
                             parse_generator_response,
                             prepare_decision_inputs)
from .existing_compiler_adapter import (ADAPTER_VERSION, AdaptedScene,
                                        COMPILED_SCENE_SOURCE,
                                        OPTIONAL_JSON_ARTIFACT_FILES,
                                        REQUIRED_ARTIFACT_FILES,
                                        adapt_compiled_artifacts,
                                        adapt_compiled_scene,
                                        derive_actor_ids)

__all__ = [
    "ADAPTER_VERSION",
    "AdaptedScene",
    "COMPILED_SCENE_SOURCE",
    "DECISION_ROUTE_VERSION",
    "DEFAULT_MAX_GENERATED",
    "DecisionRunInputs",
    "GENERATOR_PROMPT_TEMPLATE",
    "GENERATOR_RESPONSE_SCHEMA",
    "GENERATOR_VERSION",
    "OPTIONAL_JSON_ARTIFACT_FILES",
    "REQUIRED_ARTIFACT_FILES",
    "adapt_compiled_artifacts",
    "adapt_compiled_scene",
    "build_generator_prompt",
    "build_user_candidates",
    "derive_actor_ids",
    "generate_candidates",
    "generator_config_hash",
    "parse_generator_response",
    "prepare_decision_inputs",
]
