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

Phase 8 addition (additive only): :func:`build_live_snapshot` freezes a
REAL mid-run whole-branch checkpoint -- produced by
``sworldmodel.backends.concordia_local.checkpoint`` -- as the LIVE form
of the same contract, replacing the genesis-identity placeholders with
the actual per-entity component state, raw log, live RNG state, and real
engine cursor, cross-checked against the run's genesis snapshot.  The
genesis builder above is unchanged.

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

#: marker naming the Phase 8 live-state snapshot shape (real mid-run
#: checkpoint payload replacing the genesis-identity placeholder)
LIVE_SNAPSHOT_FORM = "live_v1"

#: the checkpoint schema version :func:`build_live_snapshot` accepts
#: (produced by ``sworldmodel.backends.concordia_local.checkpoint``;
#: pinned here as a literal so this module stays pure stdlib)
LIVE_CHECKPOINT_SCHEMA_VERSION = 1

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


def _live_fail(path: str, code: str, message: str) -> None:
    _fail(path, code, message)


def _require_mapping(value, path: str) -> dict:
    if not isinstance(value, dict):
        _live_fail(path, "wrong_type",
                   f"expected mapping, got {type(value).__name__}")
    return value


def build_live_snapshot(
    checkpoint: dict,
    base_snapshot: SimulationSnapshot,
    *,
    registry: ContractRegistry | None = None,
) -> SimulationSnapshot:
    """Freeze one REAL mid-run whole-branch checkpoint as a Phase 3
    ``SimulationSnapshot`` (the live-state variant of the genesis form).

    ``checkpoint`` is the payload produced by
    ``sworldmodel.backends.concordia_local.checkpoint.capture_checkpoint``
    (schema version pinned by :data:`LIVE_CHECKPOINT_SCHEMA_VERSION`);
    this function treats it as an opaque, already-canonical JSON blob and
    only (a) verifies its identity against the run's genesis
    ``base_snapshot`` and (b) maps it into the frozen contract shape:

    - ``concordia_checkpoint.entities`` / ``.game_masters`` -- the REAL
      per-entity component state, verbatim (upstream ``get_state``
      payloads keyed by entity name), replacing the genesis hash-identity
      placeholders and satisfying the contract's required-key validation;
    - ``concordia_checkpoint.raw_log``    -- the engine raw log up to the
      boundary, verbatim;
    - ``concordia_checkpoint.live``       -- the live-form identity block:
      form marker, checkpoint schema version, plan/world identity, the
      checkpoint's own per-component manifest (the directive's "explicit
      snapshot manifest listing every serialized component", carried with
      the live state), the base snapshot binding, the intervention
      identity, and the runner guard-evidence record;
    - ``sidecar.rng``                     -- the LIVE captured RNG state
      (python ``random`` full state and the numpy legacy state as
      canonical JSON strings -- the contract's scalar-map shape -- plus
      the integer seed material and the numpy factory discipline note);
    - ``sidecar.engine_cursor``           -- the real mid-run cursor
      (steps completed, remaining budget, premise delivered);
    - ``sidecar.model_config`` / ``.compiler_artifact_hash`` -- from the
      checkpoint sidecar, cross-checked against the base snapshot.

    Refused loudly (never repaired): a checkpoint of another world or
    another compiler artifact than the base snapshot's; a base snapshot
    that is not the genesis form; a seed that contradicts the base
    snapshot's disclosed per-branch seed rule (checked whenever the
    checkpoint carries its candidate identity); malformed or missing
    checkpoint sections.
    """
    issues = IssueCollector()
    if not isinstance(base_snapshot, SimulationSnapshot):
        issues.add("base_snapshot", "wrong_type",
                   "expected a SimulationSnapshot instance, got "
                   f"{type(base_snapshot).__name__}")
    if registry is not None and not isinstance(registry, ContractRegistry):
        issues.add("registry", "wrong_type",
                   "registry must be a ContractRegistry when supplied, got "
                   f"{type(registry).__name__}")
    issues.raise_if_any()

    genesis = base_snapshot.concordia_checkpoint.get("genesis")
    if not isinstance(genesis, dict) \
            or genesis.get("form") != SNAPSHOT_FORM:
        found = genesis.get("form") if isinstance(genesis, dict) else genesis
        _live_fail("base_snapshot", "invalid_value",
                   "base_snapshot must be the run's genesis snapshot "
                   f"(form {SNAPSHOT_FORM!r}); got {found!r}")

    checkpoint = _require_mapping(checkpoint, "checkpoint")
    if checkpoint.get("schema_version") != LIVE_CHECKPOINT_SCHEMA_VERSION:
        _live_fail("checkpoint.schema_version", "invalid_value",
                   "unsupported checkpoint schema version "
                   f"{checkpoint.get('schema_version')!r}; this builder "
                   f"reads version {LIVE_CHECKPOINT_SCHEMA_VERSION}")
    for key in ("entities", "game_masters", "raw_log", "sidecar",
                "manifest", "plan_id", "world_id", "engine_backend"):
        if key not in checkpoint:
            _live_fail(f"checkpoint.{key}", "missing_field",
                       f"checkpoint payload must carry {key!r}")
    entities = _require_mapping(checkpoint["entities"],
                                "checkpoint.entities")
    game_masters = _require_mapping(checkpoint["game_masters"],
                                    "checkpoint.game_masters")
    if not entities or not game_masters:
        _live_fail("checkpoint", "empty_collection",
                   "checkpoint entities and game_masters must be "
                   "non-empty")
    cp_sidecar = _require_mapping(checkpoint["sidecar"],
                                  "checkpoint.sidecar")
    for key in ("rng", "engine_cursor", "model_config_identity",
                "intervention_identity", "plan_content_hash",
                "artifact_hash", "runner_evidence"):
        if key not in cp_sidecar:
            _live_fail(f"checkpoint.sidecar.{key}", "missing_field",
                       f"checkpoint sidecar must carry {key!r}")
    rng = _require_mapping(cp_sidecar["rng"], "checkpoint.sidecar.rng")
    for key in ("seed_material", "python_random", "numpy_legacy",
                "numpy_default_rng_discipline"):
        if key not in rng:
            _live_fail(f"checkpoint.sidecar.rng.{key}", "missing_field",
                       f"checkpoint rng block must carry {key!r}")
    if type(rng["seed_material"]) is not int:
        _live_fail("checkpoint.sidecar.rng.seed_material", "wrong_type",
                   "seed_material must be an integer")
    cursor = _require_mapping(cp_sidecar["engine_cursor"],
                              "checkpoint.sidecar.engine_cursor")
    for key in ("steps_completed", "remaining_steps", "premise_delivered"):
        if key not in cursor:
            _live_fail(f"checkpoint.sidecar.engine_cursor.{key}",
                       "missing_field",
                       f"engine cursor must carry {key!r}")

    # Identity cross-checks against the genesis base snapshot.
    if checkpoint["world_id"] != base_snapshot.world_id:
        _live_fail("checkpoint.world_id", "cross_branch_reference",
                   f"checkpoint world {checkpoint['world_id']!r} is not "
                   f"the base snapshot's world "
                   f"{base_snapshot.world_id!r}")
    if cp_sidecar["artifact_hash"] \
            != base_snapshot.sidecar.compiler_artifact_hash:
        _live_fail("checkpoint.sidecar.artifact_hash",
                   "cross_branch_reference",
                   "checkpoint compiler-artifact identity "
                   f"{cp_sidecar['artifact_hash']!r} does not match the "
                   "base snapshot's "
                   f"{base_snapshot.sidecar.compiler_artifact_hash!r}")
    if checkpoint["plan_id"] != genesis.get("plan_id"):
        _live_fail("checkpoint.plan_id", "cross_branch_reference",
                   f"checkpoint plan {checkpoint['plan_id']!r} is not the "
                   f"base snapshot's plan {genesis.get('plan_id')!r}")
    base_rng = dict(base_snapshot.sidecar.rng)
    candidate_id = _require_mapping(
        cp_sidecar["intervention_identity"],
        "checkpoint.sidecar.intervention_identity").get("candidate_id")
    if candidate_id is not None and "base_seed" in base_rng:
        expected_seed = derive_branch_seed(base_rng["base_seed"],
                                           candidate_id)
        if rng["seed_material"] != expected_seed:
            _live_fail("checkpoint.sidecar.rng.seed_material",
                       "invalid_value",
                       f"seed material {rng['seed_material']} contradicts "
                       "the base snapshot's disclosed per-branch rule "
                       f"(expected {expected_seed} for candidate "
                       f"{candidate_id!r})")

    live_checkpoint = {
        "entities": entities,
        "game_masters": game_masters,
        "raw_log": checkpoint["raw_log"],
        "live": {
            "form": LIVE_SNAPSHOT_FORM,
            "checkpoint_schema_version": LIVE_CHECKPOINT_SCHEMA_VERSION,
            "engine_backend": checkpoint["engine_backend"],
            "plan_id": checkpoint["plan_id"],
            "plan_content_sha256": cp_sidecar["plan_content_hash"],
            "world_id": checkpoint["world_id"],
            "component_manifest": list(checkpoint["manifest"]),
            "base_snapshot_id": base_snapshot.snapshot_id,
            "intervention_identity": dict(
                cp_sidecar["intervention_identity"]),
            "runner_evidence": cp_sidecar["runner_evidence"],
        },
    }
    sidecar = {
        "rng": {
            "seed_material": rng["seed_material"],
            "python_random_state": _canonical(rng["python_random"]),
            "numpy_legacy_state": _canonical(rng["numpy_legacy"]),
            "numpy_default_rng_discipline": str(
                rng["numpy_default_rng_discipline"]),
        },
        "engine_cursor": {
            "steps_completed": cursor["steps_completed"],
            "remaining_budget": cursor["remaining_steps"],
            "premise_delivered": cursor["premise_delivered"],
        },
        "model_config": dict(cp_sidecar["model_config_identity"]),
        "compiler_artifact_hash": cp_sidecar["artifact_hash"],
    }
    manifest = sorted(live_checkpoint) + list(SIDECAR_COMPONENTS)
    snapshot_id = "s_" + _sha256_text("|".join((
        LIVE_SNAPSHOT_FORM,
        cp_sidecar["plan_content_hash"],
        str(cursor["steps_completed"]),
        _sha256_text(_canonical(rng["python_random"])),
        base_snapshot.snapshot_id)))[:16]

    snapshot = SimulationSnapshot.from_dict({
        "contract_type": SimulationSnapshot.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "world_id": checkpoint["world_id"],
        "concordia_checkpoint": live_checkpoint,
        "sidecar": sidecar,
        "snapshot_manifest": manifest,
    })
    if registry is not None:
        validate_semantics(snapshot, registry)
    return snapshot
