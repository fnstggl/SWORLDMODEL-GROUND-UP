"""Whole-branch checkpoint/restore for the local Concordia backend (Stage B).

One checkpoint == one complete branch persisted as a single unit, exactly
as the directive's Stage B requires.  The state that Concordia itself can
serialize is captured through Concordia's OWN component-state API -- every
entity's ``get_state()`` (act component + every context component,
including full memory banks, observation queues, next-acting cursors,
event-resolution state, and the terminate flag; upstream
``concordia/agents/entity_agent.py:218-255`` at the pinned SHA) -- and is
restored through the same ``set_state`` path.  Nothing re-implements or
re-shapes Concordia component state: the per-entity blobs in the
checkpoint ARE the objects upstream returned.

Why not ``Simulation.make_checkpoint_data``: that helper exists only on
the prefab ``generic.Simulation`` wrapper (CONCORDIA_AUDIT.md section 8).
This backend's builder constructs ``EntityAgentWithLogging`` objects and
the game master DIRECTLY from a validated plan -- there is no prefab
``Simulation``/``Config`` object to hand back to ``load_from_checkpoint``.
The audited component-level API those prefab helpers are built ON is fully
available on our objects and is used here; the checkpoint's top level
mirrors the upstream payload shape (``entities`` / ``game_masters`` /
``raw_log`` keyed by entity name) so the Phase 3 snapshot contract's
required-key validation holds unchanged.  Where the prefab blob stores
``prefab_type``/``entity_params`` for re-instantiation, this checkpoint
stores nothing: reconstruction identity is the PLAN, bound by
``sidecar.plan_content_hash`` and enforced at restore.

The sidecar carries exactly the state the audit proved the upstream path
does NOT capture (CONCORDIA_AUDIT.md section F; Phase 2 finding #6 pinned
the upstream key set ``{entities, game_masters, raw_log,
checkpoint_counter}`` -- no engine cursor, no RNG):

- ``rng.python_random``      -- the full evolving global ``random`` module
  state (``random.getstate()`` serialized to pure JSON).  GM components
  and test models draw from this stream mid-run, so a resumed branch must
  continue the SAME stream, not a re-seeded one.
- ``rng.numpy_legacy``       -- the numpy legacy global state (seeded at
  branch-scope entry; captured for completeness even though the audited
  component set never draws from it mid-run).
- ``rng.seed_material``      -- the per-branch seed the caller's
  seeded-determinism scope was entered with.  Under that scope's patched
  factory every no-argument ``numpy.random.default_rng()`` call returns a
  FRESH generator seeded with this value (see
  ``sworldmodel/counterfactuals/manager.py::_seeded_branch_scope``), so
  the numpy factory carries NO evolving state between calls -- only the
  seed material must match at resume, which :func:`restore_rng` verifies
  against the ACTIVE scope with a side-effect-free draw comparison.
- ``engine_cursor``          -- steps completed, remaining step budget,
  and ``premise_delivered=True``: the upstream engine restarts
  ``run_loop`` at ``steps=0`` and re-observes the premise on resume
  (``sequential.py:242-247``), so the runner must pass ``premise=''`` and
  the remaining budget instead.
- ``model_config_identity``  -- caller-declared model identity strings
  (model OBJECTS are injected parameters and are never serialized;
  restoring a branch requires models whose behavior is a pure function of
  the prompt and the restored RNG scope -- live API models are stateless
  per call by nature, deterministic test models must be built
  prompt-pure).
- ``intervention_identity``  -- candidate/branch identifiers when the
  caller supplied them.
- ``plan_content_hash`` / ``artifact_hash`` -- the exact branch plan and
  compiler-provenance identity; restore refuses any plan whose hashes do
  not match byte-for-byte.
- ``runner_evidence.guard_interventions`` -- the agency-guard rewrite
  records accumulated before the boundary (runner-level evidence that no
  component state carries), so a resumed run reports the complete list.

Serialization notes (documented per the directive's type-tagging ask):
``random.getstate()`` is ``(version:int, tuple[int x 625], gauss_next:
None|float)``; it is stored as ``{"version", "internal_state": [ints],
"gauss_next"}`` and rebuilt with exact tuple/int types in
:func:`restore_python_rng_state`.  The numpy legacy state's uint32 key
vector is stored as a plain int list and rebuilt as ``dtype=uint32``.
Every checkpoint is validated to be strictly JSON-representable with a
stable canonical form (``json.dumps(json.loads(x)) == x``) at capture
time, so the blob survives disk/workspace round trips byte-identically.

Cross-process canonical form: upstream serializes set-derived state as
``list(<set>)`` -- specifically ``AssociativeMemoryBank.get_state``'s
``stored_hashes`` (``basic_associative_memory.py:56-73``) -- whose order
is salted per process, so the same semantic state could serialize to
different bytes in different Ray workers.  Capture therefore sorts every
such list (``_canonicalize_state_tree``), and the restore fidelity check
compares the canonicalized forms byte-for-byte.  The objects this
backend builds carry only ``ListMemory`` (order-preserving; the builder
refuses other memory backends), so today the pass is a defensive
invariant rather than an active repair.

Safe boundary: checkpoints are captured only at the engine's end-of-step
``checkpoint_callback`` boundary (the audited safe branch point,
``sequential.py:361-362``); the runner enforces this by using
``max_steps`` as the clean stop mechanism.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass

from sworldmodel.decision.contracts import ConcordiaInitializationPlan

from .builder import MEMORY_KEY, BuiltBranch, build_branch

_IMPORT_HELP = (
    "sworldmodel.backends.concordia_local.checkpoint requires the optional "
    "'gdm-concordia' engine package (Python >= 3.12). Install it in the "
    "engine environment to use this backend; 'import sworldmodel' and the "
    "planner submodule work without it."
)

try:  # numpy is a hard dependency of the pinned Concordia package
    import numpy
except ImportError as exc:  # degrade loudly, never partially
    raise ImportError(f"{_IMPORT_HELP} (root cause: {exc!r})") from exc

#: checkpoint payload schema version (bump on any shape change)
CHECKPOINT_SCHEMA_VERSION = 1

#: backend identity stamped into every checkpoint
ENGINE_BACKEND = "concordia_local_sequential_v1"

#: recorded numpy default_rng discipline (see module docstring)
NUMPY_FACTORY_DISCIPLINE = (
    "default_rng() returns a fresh generator seeded with seed_material on "
    "every call (seeded branch scope); no evolving default_rng state "
    "exists between calls")

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

#: fixed sidecar entries every checkpoint manifest lists
_SIDECAR_MANIFEST = (
    "sidecar.rng.seed_material",
    "sidecar.rng.python_random",
    "sidecar.rng.numpy_legacy",
    "sidecar.rng.numpy_default_rng_discipline",
    "sidecar.engine_cursor",
    "sidecar.model_config_identity",
    "sidecar.intervention_identity",
    "sidecar.plan_content_hash",
    "sidecar.artifact_hash",
    "sidecar.runner_evidence.guard_interventions",
)


class CheckpointError(ValueError):
    """A checkpoint cannot be captured, validated, or restored as asked;
    nothing is repaired or defaulted silently."""


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


#: state-dict keys whose upstream value is ``list(<set>)`` -- the list
#: order is salted per process (PYTHONHASHSEED), so a checkpoint written
#: in one process and re-serialized in another could differ in bytes
#: while being semantically identical.  Known instance:
#: ``AssociativeMemoryBank.get_state`` serializes ``stored_hashes`` as
#: ``list(self._stored_hashes)`` and ``set_state`` rebuilds the set
#: (``concordia/associative_memory/basic_associative_memory.py:56-73`` at
#: the pinned SHA), so sorting is lossless.  Our builder's objects carry
#: only ``ListMemory`` (order-preserving plain lists; the builder refuses
#: every other ``memory_backend``), so this is a defensive guarantee for
#: any future roster that introduces an associative bank.
_SET_DERIVED_LIST_KEYS = frozenset({"stored_hashes"})


def _canonicalize_state_tree(value, parent_key: str | None = None):
    """Return ``value`` with every set-derived list (see
    ``_SET_DERIVED_LIST_KEYS``) sorted, recursively, so serialized entity
    state is byte-canonical across processes.  Applied to every captured
    state AND to both sides of the restore fidelity comparison; all other
    ordering is preserved verbatim."""
    if isinstance(value, dict):
        return {key: _canonicalize_state_tree(item, key)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        items = [_canonicalize_state_tree(item) for item in value]
        if parent_key in _SET_DERIVED_LIST_KEYS \
                and all(isinstance(item, str) for item in items):
            return sorted(items)
        return items
    return value


def checkpoint_canonical_json(checkpoint: dict) -> str:
    """The canonical byte form of one checkpoint (stable across load/dump
    round trips; validated at capture time)."""
    return _canonical(checkpoint)


# ---------------------------------------------------------------------------
# RNG state export/restore (the scope-machinery extension: the seeded
# branch scope in counterfactuals.manager seeds these streams at entry;
# these helpers export and restore their MID-RUN state at a boundary)
# ---------------------------------------------------------------------------

def export_python_rng_state() -> dict:
    """Serialize ``random.getstate()`` to a pure-JSON structure."""
    version, internal_state, gauss_next = random.getstate()
    return {
        "algorithm": "python_random_MT19937",
        "version": int(version),
        "internal_state": [int(word) for word in internal_state],
        "gauss_next": gauss_next if gauss_next is None else float(gauss_next),
    }


def restore_python_rng_state(payload) -> None:
    """Rebuild the exact ``random.setstate`` tuple (type-exact: int
    version, tuple of ints, ``None`` or float) and install it."""
    if not isinstance(payload, dict):
        raise CheckpointError(
            "rng.python_random must be a mapping, got "
            f"{type(payload).__name__}")
    for key in ("version", "internal_state", "gauss_next"):
        if key not in payload:
            raise CheckpointError(
                f"rng.python_random is missing required key {key!r}")
    internal = payload["internal_state"]
    if not isinstance(internal, (list, tuple)) \
            or not all(type(word) is int for word in internal):
        raise CheckpointError(
            "rng.python_random.internal_state must be a list of integers")
    gauss_next = payload["gauss_next"]
    if gauss_next is not None and not isinstance(gauss_next, (int, float)):
        raise CheckpointError(
            "rng.python_random.gauss_next must be null or a number")
    try:
        random.setstate((
            int(payload["version"]),
            tuple(int(word) for word in internal),
            None if gauss_next is None else float(gauss_next),
        ))
    except (TypeError, ValueError) as exc:
        raise CheckpointError(
            f"random.setstate rejected the serialized state: {exc}") from exc


def export_numpy_legacy_state() -> dict:
    """Serialize the numpy legacy global state to pure JSON."""
    algorithm, keys, pos, has_gauss, cached_gaussian = \
        numpy.random.get_state()
    return {
        "algorithm": str(algorithm),
        "keys": [int(key) for key in keys],
        "pos": int(pos),
        "has_gauss": int(has_gauss),
        "cached_gaussian": float(cached_gaussian),
    }


def restore_numpy_legacy_state(payload) -> None:
    """Rebuild and install the numpy legacy global state (uint32 keys)."""
    if not isinstance(payload, dict):
        raise CheckpointError(
            "rng.numpy_legacy must be a mapping, got "
            f"{type(payload).__name__}")
    for key in ("algorithm", "keys", "pos", "has_gauss", "cached_gaussian"):
        if key not in payload:
            raise CheckpointError(
                f"rng.numpy_legacy is missing required key {key!r}")
    try:
        numpy.random.set_state((
            str(payload["algorithm"]),
            numpy.array(payload["keys"], dtype=numpy.uint32),
            int(payload["pos"]),
            int(payload["has_gauss"]),
            float(payload["cached_gaussian"]),
        ))
    except (TypeError, ValueError) as exc:
        raise CheckpointError(
            "numpy.random.set_state rejected the serialized state: "
            f"{exc}") from exc


def verify_active_seed_discipline(seed_material: int) -> None:
    """Prove the ACTIVE process is inside a seeded branch scope whose
    numpy factory discipline matches ``seed_material``.

    Side-effect free: the patched factory returns a fresh generator per
    call (consuming nothing from any evolving stream), so comparing one
    draw from a no-argument factory call against one draw from an
    explicitly seeded generator is a pure probe.  Outside the scope the
    no-argument call is entropy-seeded and the comparison fails, loudly
    naming the requirement.
    """
    if type(seed_material) is not int:
        raise CheckpointError(
            "rng.seed_material must be an integer, got "
            f"{type(seed_material).__name__}")
    implicit = numpy.random.default_rng().integers(0, 2 ** 63)
    explicit = numpy.random.default_rng(seed_material).integers(0, 2 ** 63)
    if int(implicit) != int(explicit):
        raise CheckpointError(
            "the active process is not inside a seeded branch scope for "
            f"seed_material={seed_material}: numpy.random.default_rng() "
            "is not patched to that seed. Resume must run inside the same "
            "seeded-determinism scope the branch was captured under "
            "(counterfactuals.manager._seeded_branch_scope or the "
            "engine-contract det harness).")


def restore_rng(checkpoint: dict) -> None:
    """Restore BOTH captured RNG streams inside the active seeded scope:
    verify the numpy factory discipline against the recorded seed
    material, then install the exact python ``random`` and numpy legacy
    states captured at the boundary."""
    rng = checkpoint["sidecar"]["rng"]
    verify_active_seed_discipline(rng["seed_material"])
    restore_python_rng_state(rng["python_random"])
    restore_numpy_legacy_state(rng["numpy_legacy"])


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def _entity_state_manifest(section: str, states: dict) -> list:
    out = []
    for name in sorted(states):
        state = states[name]
        out.append(f"{section}.{name}.act_component")
        for key in sorted(state.get("context_components", {})):
            out.append(f"{section}.{name}.context_components.{key}")
    return out


def _build_manifest(entities: dict, game_masters: dict) -> list:
    manifest = _entity_state_manifest("entities", entities)
    manifest.extend(_entity_state_manifest("game_masters", game_masters))
    manifest.append("raw_log")
    manifest.extend(_SIDECAR_MANIFEST)
    return manifest


def _check_identity_strings(mapping, path: str) -> dict:
    if not isinstance(mapping, dict):
        raise CheckpointError(
            f"{path} must be a mapping of identity strings, got "
            f"{type(mapping).__name__}")
    for key, value in mapping.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise CheckpointError(
                f"{path} entries must map string names to string values; "
                f"got {key!r}: {type(value).__name__}")
    return dict(mapping)


def capture_checkpoint(
    built: BuiltBranch,
    *,
    steps_completed: int,
    remaining_steps: int,
    seed_material: int,
    plan_content_hash: str,
    artifact_hash: str,
    raw_log=(),
    guard_interventions=(),
    intervention_identity=None,
    model_config_identity=None,
) -> dict:
    """Capture one live branch as a complete, JSON-canonical checkpoint.

    Must be called at rest at an end-of-step boundary (the runner's
    ``checkpoint_after`` mechanism guarantees this).  RNG states are
    exported HERE -- at the boundary -- so the caller must not consume
    global randomness between the engine stop and this call.
    """
    if not isinstance(built, BuiltBranch):
        raise CheckpointError(
            "capture_checkpoint expects the builder's BuiltBranch, got "
            f"{type(built).__name__}")
    if type(steps_completed) is not int or steps_completed < 1:
        raise CheckpointError(
            "steps_completed must be an integer >= 1 (a checkpoint exists "
            "only at a completed end-of-step boundary)")
    if type(remaining_steps) is not int or remaining_steps < 1:
        raise CheckpointError(
            "remaining_steps must be an integer >= 1: a checkpoint with "
            "nothing left to run cannot be resumed and is refused")
    if steps_completed + remaining_steps != built.max_steps:
        raise CheckpointError(
            f"engine cursor arithmetic broken: {steps_completed} completed "
            f"+ {remaining_steps} remaining != step budget "
            f"{built.max_steps}")
    if type(seed_material) is not int:
        raise CheckpointError(
            "seed_material must be the integer branch seed the active "
            f"scope was entered with, got {type(seed_material).__name__}")
    for label, value in (("plan_content_hash", plan_content_hash),
                         ("artifact_hash", artifact_hash)):
        if not isinstance(value, str) or not _HEX64_RE.match(value):
            raise CheckpointError(
                f"{label} must be a 64-character lowercase hex sha256, "
                f"got {value!r}")
    identity = _check_identity_strings(intervention_identity or {},
                                       "intervention_identity")
    model_identity = _check_identity_strings(model_config_identity or {},
                                             "model_config_identity")

    entities = {}
    for actor_id in built.actor_order:
        name = built.actor_names[actor_id]
        entities[name] = _canonicalize_state_tree(
            built.actors[actor_id].get_state())
    gm_name = built.game_master.name
    game_masters = {gm_name: _canonicalize_state_tree(
        built.game_master.get_state())}

    checkpoint = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "engine_backend": ENGINE_BACKEND,
        "plan_id": built.plan_id,
        "world_id": built.world_id,
        "entities": entities,
        "game_masters": game_masters,
        "raw_log": list(raw_log),
        "sidecar": {
            "rng": {
                "seed_material": seed_material,
                "python_random": export_python_rng_state(),
                "numpy_legacy": export_numpy_legacy_state(),
                "numpy_default_rng_discipline": NUMPY_FACTORY_DISCIPLINE,
            },
            "engine_cursor": {
                "steps_completed": steps_completed,
                "remaining_steps": remaining_steps,
                "premise_delivered": True,
            },
            "model_config_identity": model_identity,
            "intervention_identity": identity,
            "plan_content_hash": plan_content_hash,
            "artifact_hash": artifact_hash,
            "runner_evidence": {
                "guard_interventions": list(guard_interventions),
            },
        },
        "manifest": _build_manifest(entities, game_masters),
    }

    # Normalize to pure JSON types (upstream states may contain tuples,
    # which serialize losslessly to lists for set_state) and prove the
    # canonical form is stable; anything non-JSON fails HERE, loudly.
    try:
        first = _canonical(checkpoint)
    except (TypeError, ValueError) as exc:
        raise CheckpointError(
            "checkpoint is not JSON-serializable; a non-JSON value "
            f"reached the state capture: {exc}") from exc
    normalized = json.loads(first)
    if _canonical(normalized) != first:
        raise CheckpointError(
            "checkpoint canonical JSON is not round-trip stable")
    validate_checkpoint(normalized)
    return normalized


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_checkpoint(checkpoint) -> None:
    """Strict structural validation of one checkpoint payload.  A missing
    or tampered key refuses loudly; nothing is repaired."""
    if not isinstance(checkpoint, dict):
        raise CheckpointError(
            f"checkpoint must be a mapping, got "
            f"{type(checkpoint).__name__}")
    required = ("schema_version", "engine_backend", "plan_id", "world_id",
                "entities", "game_masters", "raw_log", "sidecar", "manifest")
    missing = [key for key in required if key not in checkpoint]
    if missing:
        raise CheckpointError(
            f"checkpoint is missing required keys: {sorted(missing)}")
    unknown = sorted(set(checkpoint) - set(required))
    if unknown:
        raise CheckpointError(
            f"checkpoint carries unknown keys: {unknown}")
    if checkpoint["schema_version"] != CHECKPOINT_SCHEMA_VERSION:
        raise CheckpointError(
            f"unsupported checkpoint schema_version "
            f"{checkpoint['schema_version']!r}; this backend reads version "
            f"{CHECKPOINT_SCHEMA_VERSION}")
    if checkpoint["engine_backend"] != ENGINE_BACKEND:
        raise CheckpointError(
            f"checkpoint was captured by backend "
            f"{checkpoint['engine_backend']!r}, not {ENGINE_BACKEND!r}")
    for section in ("entities", "game_masters"):
        blob = checkpoint[section]
        if not isinstance(blob, dict) or not blob:
            raise CheckpointError(
                f"checkpoint.{section} must be a non-empty mapping of "
                "entity name -> component state")
        for name, state in blob.items():
            if not isinstance(state, dict) \
                    or "act_component" not in state \
                    or not isinstance(state.get("context_components"), dict):
                raise CheckpointError(
                    f"checkpoint.{section}[{name!r}] is not an upstream "
                    "EntityState (act_component + context_components)")
    if not isinstance(checkpoint["raw_log"], list):
        raise CheckpointError("checkpoint.raw_log must be a list")

    sidecar = checkpoint["sidecar"]
    if not isinstance(sidecar, dict):
        raise CheckpointError("checkpoint.sidecar must be a mapping")
    sidecar_required = ("rng", "engine_cursor", "model_config_identity",
                        "intervention_identity", "plan_content_hash",
                        "artifact_hash", "runner_evidence")
    missing = [key for key in sidecar_required if key not in sidecar]
    if missing:
        raise CheckpointError(
            f"checkpoint.sidecar is missing required keys: "
            f"{sorted(missing)}")

    rng = sidecar["rng"]
    if not isinstance(rng, dict):
        raise CheckpointError("sidecar.rng must be a mapping")
    for key in ("seed_material", "python_random", "numpy_legacy",
                "numpy_default_rng_discipline"):
        if key not in rng:
            raise CheckpointError(
                f"sidecar.rng is missing required key {key!r}")
    if type(rng["seed_material"]) is not int:
        raise CheckpointError("sidecar.rng.seed_material must be an integer")

    cursor = sidecar["engine_cursor"]
    if not isinstance(cursor, dict):
        raise CheckpointError("sidecar.engine_cursor must be a mapping")
    for key in ("steps_completed", "remaining_steps", "premise_delivered"):
        if key not in cursor:
            raise CheckpointError(
                f"sidecar.engine_cursor is missing required key {key!r}")
    if type(cursor["steps_completed"]) is not int \
            or cursor["steps_completed"] < 1:
        raise CheckpointError(
            "engine_cursor.steps_completed must be an integer >= 1")
    if type(cursor["remaining_steps"]) is not int \
            or cursor["remaining_steps"] < 1:
        raise CheckpointError(
            "engine_cursor.remaining_steps must be an integer >= 1")
    if cursor["premise_delivered"] is not True:
        raise CheckpointError(
            "engine_cursor.premise_delivered must be exactly True: a "
            "checkpoint exists only after the opening premise was "
            "delivered, and resume must never redeliver it")

    for label in ("plan_content_hash", "artifact_hash"):
        value = sidecar[label]
        if not isinstance(value, str) or not _HEX64_RE.match(value):
            raise CheckpointError(
                f"sidecar.{label} must be a 64-character lowercase hex "
                f"sha256, got {value!r}")
    _check_identity_strings(sidecar["model_config_identity"],
                            "sidecar.model_config_identity")
    _check_identity_strings(sidecar["intervention_identity"],
                            "sidecar.intervention_identity")
    evidence = sidecar["runner_evidence"]
    if not isinstance(evidence, dict) \
            or not isinstance(evidence.get("guard_interventions"), list):
        raise CheckpointError(
            "sidecar.runner_evidence.guard_interventions must be a list")

    expected_manifest = _build_manifest(checkpoint["entities"],
                                        checkpoint["game_masters"])
    if checkpoint["manifest"] != expected_manifest:
        missing = sorted(set(expected_manifest) - set(checkpoint["manifest"]))
        extra = sorted(set(checkpoint["manifest"]) - set(expected_manifest))
        raise CheckpointError(
            "checkpoint manifest does not account for the serialized "
            f"components exactly (missing: {missing}, unknown: {extra})")
    try:
        text = _canonical(checkpoint)
    except (TypeError, ValueError) as exc:
        raise CheckpointError(
            f"checkpoint is not JSON-serializable: {exc}") from exc
    if _canonical(json.loads(text)) != text:
        raise CheckpointError(
            "checkpoint canonical JSON is not round-trip stable")


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

@dataclass
class RestoredBranch:
    """A rebuilt branch with the checkpoint state applied, plus the
    run-continuation context the runner needs."""

    built: BuiltBranch
    steps_completed: int
    remaining_steps: int
    seed_material: int
    guard_interventions: list
    raw_log: list
    checkpoint: dict


def _adopt_memory_backing_list(entity, handle: list) -> None:
    """Re-point the entity's ListMemory at OUR capture handle, entirely
    through the public component API.

    Upstream ``ListMemory.set_state`` re-points its internal bank at a NEW
    list (``components/agent/memory.py:264-269`` at the pinned SHA), which
    would silently orphan the ``BuiltBranch`` backing-list handles the
    runner collects results from.  Repair: read the restored rows back
    through ``get_all_memories_as_text()``, fill the original handle in
    place, and hand the handle itself to ``set_state`` (which adopts a
    list argument by reference).  No private upstream attribute is
    touched, and the post-restore fidelity check below re-verifies the
    full state equality afterwards.
    """
    component = entity.get_component(MEMORY_KEY)
    rows = list(component.get_all_memories_as_text())
    handle.clear()
    handle.extend(rows)
    component.set_state({"memory_bank": handle})


def _apply_entity_state(entity, saved_state: dict, label: str,
                        memory_handle: list) -> None:
    """Apply one saved EntityState through upstream ``set_state`` and
    verify byte-exact fidelity (upstream swallows per-component set_state
    exceptions into log lines -- ``entity_agent.py:218-245`` -- so the
    only trustworthy success signal is ``get_state()`` equality)."""
    live_keys = set(entity.get_state().get("context_components", {}))
    saved_keys = set(saved_state.get("context_components", {}))
    if live_keys != saved_keys:
        raise CheckpointError(
            f"{label}: checkpoint component keys {sorted(saved_keys)} do "
            f"not match the rebuilt entity's {sorted(live_keys)}; the "
            "plan and checkpoint disagree about the component roster")
    entity.set_state(saved_state)
    _adopt_memory_backing_list(entity, memory_handle)
    # Byte comparison over the canonicalized forms: set-derived list
    # order (process-hash-salted upstream) is normalized on BOTH sides,
    # every other byte must match exactly.
    live = _canonicalize_state_tree(entity.get_state())
    saved = _canonicalize_state_tree(saved_state)
    if _canonical(live) != _canonical(saved):
        differing = []
        for key in sorted(saved_keys):
            if _canonical(live["context_components"][key]) != _canonical(
                    saved["context_components"][key]):
                differing.append(key)
        if _canonical(live["act_component"]) != _canonical(
                saved["act_component"]):
            differing.append("act_component")
        raise CheckpointError(
            f"{label}: state application was not faithful; differing "
            f"components: {differing} (upstream set_state swallows "
            "per-component errors, so this equality check is the gate)")


def restore_branch(
    plan: ConcordiaInitializationPlan,
    checkpoint: dict,
    *,
    actor_models,
    gm_model,
    guard_step=None,
    guard_escalate=None,
) -> RestoredBranch:
    """Rebuild the branch from its plan and apply the checkpoint state.

    The rebuild goes through the same :func:`builder.build_branch` path as
    the original run with ``skip_initial_seeding=True`` -- the initial
    observations and pre-start game-master events live inside the restored
    component state and must NOT be seeded a second time.  RNG restoration
    is deliberately separate (:func:`restore_rng`): the runner installs it
    immediately before the engine continues so nothing can perturb the
    stream in between.
    """
    validate_checkpoint(checkpoint)
    if not isinstance(plan, ConcordiaInitializationPlan):
        raise CheckpointError(
            "restore_branch expects a ConcordiaInitializationPlan, got "
            f"{type(plan).__name__}")
    sidecar = checkpoint["sidecar"]
    plan_hash = plan.content_hash()
    if sidecar["plan_content_hash"] != plan_hash:
        raise CheckpointError(
            "checkpoint/plan identity mismatch: checkpoint was captured "
            f"from plan hash {sidecar['plan_content_hash']} but the "
            f"supplied plan hashes to {plan_hash}; restoring a different "
            "plan is refused")
    artifact_hash = hashlib.sha256(
        plan.compiler_provenance.canonical_json().encode("utf-8")).hexdigest()
    if sidecar["artifact_hash"] != artifact_hash:
        raise CheckpointError(
            "checkpoint/plan compiler-artifact identity mismatch: "
            f"{sidecar['artifact_hash']} != {artifact_hash}")
    if checkpoint["plan_id"] != plan.plan_id \
            or checkpoint["world_id"] != plan.world_id:
        raise CheckpointError(
            "checkpoint plan/world identifiers do not match the supplied "
            f"plan ({checkpoint['plan_id']}/{checkpoint['world_id']} vs "
            f"{plan.plan_id}/{plan.world_id})")
    cursor = sidecar["engine_cursor"]
    budget = plan.run_limits["max_steps"]
    if cursor["steps_completed"] + cursor["remaining_steps"] != budget:
        raise CheckpointError(
            f"engine cursor arithmetic broken: {cursor['steps_completed']} "
            f"+ {cursor['remaining_steps']} != plan step budget {budget}")

    built = build_branch(
        plan, actor_models=actor_models, gm_model=gm_model,
        guard_step=guard_step, guard_escalate=guard_escalate,
        skip_initial_seeding=True)

    expected_names = {built.actor_names[actor_id]
                      for actor_id in built.actor_order}
    saved_names = set(checkpoint["entities"])
    if saved_names != expected_names:
        raise CheckpointError(
            f"checkpoint entity names {sorted(saved_names)} do not match "
            f"the plan's actor names {sorted(expected_names)}")
    gm_name = built.game_master.name
    if set(checkpoint["game_masters"]) != {gm_name}:
        raise CheckpointError(
            "checkpoint game-master names "
            f"{sorted(checkpoint['game_masters'])} do not match the "
            f"plan's game master {gm_name!r}")

    for actor_id in built.actor_order:
        name = built.actor_names[actor_id]
        _apply_entity_state(
            built.actors[actor_id], checkpoint["entities"][name],
            f"entity {name!r}", built.actor_memory_lists[actor_id])
    _apply_entity_state(
        built.game_master, checkpoint["game_masters"][gm_name],
        f"game master {gm_name!r}", built.gm_memory_list)

    return RestoredBranch(
        built=built,
        steps_completed=cursor["steps_completed"],
        remaining_steps=cursor["remaining_steps"],
        seed_material=sidecar["rng"]["seed_material"],
        guard_interventions=[
            dict(entry) for entry in
            sidecar["runner_evidence"]["guard_interventions"]],
        raw_log=[entry for entry in checkpoint["raw_log"]],
        checkpoint=checkpoint,
    )
