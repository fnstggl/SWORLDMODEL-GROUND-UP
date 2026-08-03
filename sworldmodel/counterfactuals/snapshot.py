"""Frozen base: build the initialization plan once and freeze its identity.

Phase 6 scope (LOCAL phase).  ``build_base_plan`` maps one validated
``CompiledDecisionWorld`` through the Phase 4 planner into the
deterministic ``ConcordiaInitializationPlan`` -- exactly ONCE per run --
and ``build_base_snapshot`` freezes that plan as a Phase 3
``SimulationSnapshot``.  **Base identity is ``plan.content_hash()``**:
every branch of a run derives from this single plan object, whose hash the
snapshot records, and the branch module refuses any derivation that would
change the plan outside the single insertion boundary.

What this snapshot captures -- and what it deliberately does not
----------------------------------------------------------------
Full LIVE-state checkpointing (mid-run entity / game-master component
state through the upstream checkpoint path plus the sidecar) is **Phase 8**
work.  This phase's snapshot is the MINIMAL GENESIS form: it captures,
deterministically and completely, the identity of the frozen starting
point --

- ``concordia_checkpoint.entities``      -- per-actor roster/config
  identity: entity name plus sha256 of the exact actor plan config and of
  the actor's initial observation list;
- ``concordia_checkpoint.game_masters``  -- game-master config identity:
  sha256 of the plan's full ``gm_config`` and of the pre-start event
  record, plus the pre-start event count;
- ``concordia_checkpoint.genesis``       -- the plan identity itself:
  snapshot form marker, ``plan_id``, ``plan.content_hash()``, and the
  world identifier;
- ``sidecar.rng``                        -- the run's base seed material
  and the code-owned per-branch seed derivation rule (see
  :func:`derive_branch_seed`);
- ``sidecar.engine_cursor``              -- the genesis cursor: zero steps
  completed, the plan's full step budget remaining, premise not yet
  delivered;
- ``sidecar.model_config``               -- caller-declared model IDENTITY
  strings only (models themselves are injected objects at run time and are
  never serialized);
- ``sidecar.compiler_artifact_hash``     -- sha256 over the canonical JSON
  of the world's compiler provenance, binding the compiler/fixture
  artifact identity (every artifact hash the provenance names is inside
  the hashed text).

``snapshot_manifest`` lists exactly what is captured: every top-level
checkpoint key plus the four fixed sidecar component names, nothing more
and nothing less -- Phase 3 semantic validation enforces the equality in
both directions.

Pure stdlib.  The planner lives in ``sworldmodel.backends.concordia_local``
and is imported lazily inside the function, the same guarded way the
backends package documents; the planner submodule is itself
stdlib-importable everywhere ``sworldmodel`` is importable.
"""

from __future__ import annotations

import hashlib
import json

from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            ConcordiaInitializationPlan,
                                            ContractValidationError,
                                            EvaluatorSpec, IssueCollector,
                                            SCHEMA_VERSION,
                                            SimulationSnapshot,
                                            SIDECAR_COMPONENTS,
                                            ValidationIssue, _SLUG_RE)
from sworldmodel.decision.registry import ContractRegistry
from sworldmodel.decision.validation import validate_semantics

#: marker naming this snapshot shape (genesis identity, not live state)
SNAPSHOT_FORM = "genesis_v1"

#: the code-owned per-branch seed rule, disclosed inside the snapshot
BRANCH_SEED_RULE = ("int.from_bytes(sha256('<base_seed>|<candidate_id>')"
                    ".digest()[:8], 'big')")


def _fail(path: str, code: str, message: str) -> None:
    raise ContractValidationError([ValidationIssue(path, code, message)])


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def derive_branch_seed(seed: int, candidate_id: str) -> int:
    """Code-owned per-branch seed: ``BRANCH_SEED_RULE`` applied to
    ``(seed, candidate_id)``.

    Deterministic and reproducible (same inputs, same seed forever) while
    giving every candidate distinct seed material, so no branch shares an
    RNG stream with a sibling.
    """
    if type(seed) is not int:
        _fail("seed", "wrong_type",
              f"seed must be an integer, got {type(seed).__name__}")
    if not isinstance(candidate_id, str) or not _SLUG_RE.match(candidate_id):
        _fail("candidate_id", "invalid_id",
              f"candidate identifier {candidate_id!r} must match "
              f"{_SLUG_RE.pattern}")
    digest = hashlib.sha256(
        f"{seed}|{candidate_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def build_base_plan(
    world: CompiledDecisionWorld,
    evaluator_spec: EvaluatorSpec,
    *,
    max_steps: int,
    acting_order: str | None = None,
    agency_guard_enabled: bool = True,
) -> ConcordiaInitializationPlan:
    """Build THE base initialization plan for one counterfactual run.

    A thin, explicit delegation to the Phase 4 planner (imported lazily
    from the backends package): same inputs, byte-identical canonical plan
    JSON, and therefore the same ``content_hash`` -- the base identity all
    branches of the run share.  ``acting_order=None`` uses the planner's
    deterministic default.
    """
    from sworldmodel.backends.concordia_local import planner

    kwargs = {"max_steps": max_steps,
              "agency_guard_enabled": agency_guard_enabled}
    if acting_order is not None:
        kwargs["acting_order"] = acting_order
    return planner.build_initialization_plan(world, evaluator_spec, **kwargs)


def build_base_snapshot(
    plan: ConcordiaInitializationPlan,
    *,
    seed: int,
    model_config: dict | None = None,
    registry: ContractRegistry | None = None,
) -> SimulationSnapshot:
    """Freeze one base plan's genesis identity as a ``SimulationSnapshot``.

    See the module docstring for exactly what is captured.  The snapshot
    is built strictly through the Phase 3 contract gate (``from_dict``)
    and, when a registry is supplied, semantically validated against it.
    Raises ``ContractValidationError`` with every collected defect; never
    repairs.
    """
    issues = IssueCollector()
    if not isinstance(plan, ConcordiaInitializationPlan):
        issues.add("plan", "wrong_type",
                   "expected a ConcordiaInitializationPlan instance, got "
                   f"{type(plan).__name__}")
    if type(seed) is not int:
        issues.add("seed", "wrong_type",
                   f"seed must be an integer, got {type(seed).__name__}")
    if model_config is not None and not isinstance(model_config, dict):
        issues.add("model_config", "wrong_type",
                   "model_config must be a mapping of identity strings, "
                   f"got {type(model_config).__name__}")
    if registry is not None and not isinstance(registry, ContractRegistry):
        issues.add("registry", "wrong_type",
                   "registry must be a ContractRegistry when supplied, got "
                   f"{type(registry).__name__}")
    issues.raise_if_any()

    gm_name = plan.gm_config.get("gm_name")
    if not isinstance(gm_name, str) or not gm_name.strip():
        issues.add("gm_config.gm_name", "missing_field",
                   "the plan's gm_config must name its game master")
    if "max_steps" not in plan.run_limits:
        issues.add("run_limits.max_steps", "missing_field",
                   "the plan must carry the code-owned engine-step budget")
    issues.raise_if_any()

    plan_hash = plan.content_hash()
    entities = {}
    for config in plan.actor_configs:
        observations = list(
            plan.initial_observations.get(config.actor_id, ()))
        entities[config.actor_id] = {
            "name": config.name,
            "actor_config_sha256": _sha256_text(
                _canonical(config.to_dict())),
            "initial_observations_sha256": _sha256_text(
                _canonical(observations)),
        }
    game_masters = {
        gm_name: {
            "gm_config_sha256": _sha256_text(
                _canonical(dict(plan.gm_config))),
            "initial_events_sha256": _sha256_text(
                _canonical(list(plan.gm_initial_events))),
            "initial_event_count": len(plan.gm_initial_events),
        },
    }
    checkpoint = {
        "entities": entities,
        "game_masters": game_masters,
        "genesis": {
            "form": SNAPSHOT_FORM,
            "plan_id": plan.plan_id,
            "plan_content_sha256": plan_hash,
            "world_id": plan.world_id,
        },
    }
    sidecar = {
        "rng": {
            "base_seed": seed,
            "branch_seed_rule": BRANCH_SEED_RULE,
        },
        "engine_cursor": {
            "steps_completed": 0,
            "remaining_budget": plan.run_limits["max_steps"],
            "premise_delivered": False,
        },
        "model_config": dict(model_config or {}),
        "compiler_artifact_hash": _sha256_text(
            plan.compiler_provenance.canonical_json()),
    }
    manifest = sorted(checkpoint) + list(SIDECAR_COMPONENTS)
    snapshot_id = "s_" + _sha256_text("|".join((
        SNAPSHOT_FORM, plan_hash, str(seed),
        _canonical(dict(model_config or {})))))[:16]

    snapshot = SimulationSnapshot.from_dict({
        "contract_type": SimulationSnapshot.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "world_id": plan.world_id,
        "concordia_checkpoint": checkpoint,
        "sidecar": sidecar,
        "snapshot_manifest": manifest,
    })
    if registry is not None:
        validate_semantics(snapshot, registry)
    return snapshot
