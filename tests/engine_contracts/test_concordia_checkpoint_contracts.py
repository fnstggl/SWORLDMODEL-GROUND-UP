"""Concordia checkpoint contracts: prefab Simulation save/restore round-trip
plus explicit documentation of the sidecar gaps SWORLDMODEL must own.

Pinned upstream: concordia @ 7779a4c9f96bad10816d88c54e4cb17d53ac5222.
Verified sources:
  - Simulation.make_checkpoint_data / load_from_checkpoint:
    concordia/prefabs/simulation/generic.py:333-380, 539-644
  - upstream round-trip test pattern (construct + JSON round-trip):
    concordia/prefabs/simulation/checkpoint_test.py:84-131
  - engine restart-on-resume (premise re-observed, steps=0):
    concordia/environment/engines/sequential.py:242-247

Sidecar gaps (audit CONCORDIA_AUDIT.md §F) asserted here where possible:
checkpoint data carries NO engine cursor (step count/active GM/premise flag)
and NO RNG state — after restore, play() restarts at steps=0 and re-observes
the premise. Suppressing that is the SWORLDMODEL sidecar's responsibility
(record remaining-step budget; pass premise='' on resume; re-seed RNG).

Offline: NoLanguageModel + ones embedder; the default generic-GM resolution
chain touches unseeded RNG (audit §13), so runs execute under the Phase 2
seeding harness (det.seeded_determinism) for stability. State comparisons are
between the saved and the restored simulation, at rest.
"""

from __future__ import annotations

import json
import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine contracts require Python >= 3.12 (Concordia floor); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.prefabs.simulation.generic", exc_type=ImportError)

from concordia.language_model import no_language_model
from concordia.prefabs.entity import minimal as minimal_entity
from concordia.prefabs.game_master import generic as generic_gm
from concordia.prefabs.simulation import generic as simulation_lib
from concordia.typing import prefab as prefab_lib

from det import ones_embedder, seeded_determinism

PREMISE = "CHECKPOINT_PREMISE_MARKER_66b1: Alice and Bob wait in the lobby."
MAX_STEPS = 2
SEED = 20260803


def _make_config() -> prefab_lib.Config:
    """Explicit prefab dict (never package-wide discovery), 2 entities + 1 GM.

    Mirrors upstream checkpoint_test._make_config, with fixed acting order so
    the run shape is scripted rather than LLM-chosen.
    """
    entity_a_params = dict(minimal_entity.Entity().params)
    entity_a_params["name"] = "Alice"
    entity_a_params["randomize_choices"] = False
    entity_b_params = dict(minimal_entity.Entity().params)
    entity_b_params["name"] = "Bob"
    entity_b_params["randomize_choices"] = False

    gm_params = dict(generic_gm.GameMaster().params)
    gm_params["name"] = "default_rules"
    gm_params["acting_order"] = "fixed"

    return prefab_lib.Config(
        prefabs={
            "minimal_entity": minimal_entity.Entity(),
            "generic_gm": generic_gm.GameMaster(),
        },
        instances=[
            prefab_lib.InstanceConfig(
                prefab="minimal_entity",
                role=prefab_lib.Role.ENTITY,
                params=entity_a_params,
            ),
            prefab_lib.InstanceConfig(
                prefab="minimal_entity",
                role=prefab_lib.Role.ENTITY,
                params=entity_b_params,
            ),
            prefab_lib.InstanceConfig(
                prefab="generic_gm",
                role=prefab_lib.Role.GAME_MASTER,
                params=gm_params,
            ),
        ],
        default_premise=PREMISE,
        default_max_steps=MAX_STEPS,
    )


def _make_sim() -> simulation_lib.Simulation:
    return simulation_lib.Simulation(
        config=_make_config(),
        model=no_language_model.NoLanguageModel(),
        embedder=ones_embedder,
    )


def _entity_memories(sim) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for entity in sim.entities:
        component = entity.get_component("__memory__")
        out[entity.name] = list(component.get_all_memories_as_text())
    return out


def _played_and_checkpointed():
    """Run one simulation to completion and JSON-round-trip its checkpoint."""
    sim = _make_sim()
    with seeded_determinism(SEED):
        sim.play(premise=PREMISE, max_steps=MAX_STEPS)
    checkpoint = sim.make_checkpoint_data()
    loaded = json.loads(json.dumps(checkpoint))  # upstream test pattern
    return sim, checkpoint, loaded


def test_play_to_completion_then_checkpoint_restore_matches_saved_state():
    sim1, _checkpoint, loaded = _played_and_checkpointed()

    saved_entity_memories = _entity_memories(sim1)
    saved_gm_memories = list(sim1.game_master_memory_bank.get_all_memories_as_text())
    # The run demonstrably produced state.
    assert any(PREMISE in m for m in saved_gm_memories), saved_gm_memories

    sim2 = _make_sim()  # fresh, identically configured
    assert sim2.game_master_memory_bank.get_all_memories_as_text() == []
    sim2.load_from_checkpoint(loaded)

    # Entity memory text matches the saved state, per entity.
    restored_entity_memories = _entity_memories(sim2)
    assert set(restored_entity_memories) == {"Alice", "Bob"}
    assert restored_entity_memories == saved_entity_memories

    # GM memory text matches the saved state.
    restored_gm_memories = list(
        sim2.game_master_memory_bank.get_all_memories_as_text()
    )
    assert restored_gm_memories == saved_gm_memories

    # Raw log rides the checkpoint.
    assert sim2.get_raw_log() == loaded["raw_log"]

    # Same names on both sides.
    assert {e.name for e in sim2.entities} == {e.name for e in sim1.entities}
    assert {g.name for g in sim2.game_masters} == {g.name for g in sim1.game_masters}


def test_checkpoint_has_no_engine_cursor_or_rng_state_sidecar_gap():
    """The checkpoint is component-complete but NOT process-complete.

    Assert the exact top-level shape so any upstream change that starts
    persisting an engine cursor is caught, and document what the SWORLDMODEL
    sidecar must therefore own (audit §F).
    """
    _sim, checkpoint, _loaded = _played_and_checkpointed()

    # Exact top-level keys: no 'steps', no 'active_game_master', no
    # 'premise_delivered', no 'rng' — the engine cursor and RNG state are
    # simply absent, so play() after restore restarts at steps=0.
    assert set(checkpoint.keys()) == {
        "entities",
        "game_masters",
        "raw_log",
        "checkpoint_counter",
    }
    forbidden_cursor_fields = {
        "steps",
        "step",
        "engine",
        "active_game_master",
        "premise_delivered",
        "rng",
        "random_state",
    }
    assert forbidden_cursor_fields.isdisjoint(checkpoint.keys())

    for name, blob in checkpoint["entities"].items():
        assert set(blob.keys()) == {
            "prefab_type",
            "entity_params",
            "components",
            "component_info",
        }, (name, blob.keys())
    for name, blob in checkpoint["game_masters"].items():
        assert set(blob.keys()) == {
            "prefab_type",
            "entity_params",
            "role",
            "components",
            "component_info",
        }, (name, blob.keys())


def test_play_after_restore_redelivers_premise_proving_engine_restart():
    """Behavioural proof of the sidecar gap: a resumed play() re-observes the
    premise (sequential.py:243-246) because nothing in the checkpoint says it
    was already delivered. The sidecar must pass premise='' on resume."""
    sim1, _checkpoint, loaded = _played_and_checkpointed()
    saved_gm_memories = sim1.game_master_memory_bank.get_all_memories_as_text()
    assert (
        sum(PREMISE in m for m in saved_gm_memories) == 1
    ), saved_gm_memories

    sim2 = _make_sim()
    sim2.load_from_checkpoint(loaded)
    restored_rows = sim2.game_master_memory_bank.get_all_memories_as_text()
    assert sum(PREMISE in m for m in restored_rows) == 1

    with seeded_determinism(SEED + 1):
        sim2.play(premise=PREMISE, max_steps=1)

    rows_after_resume = sim2.game_master_memory_bank.get_all_memories_as_text()
    # The premise event row now appears TWICE (GM bank allows duplicates):
    # the restored one plus the re-delivered one — the engine restarted from
    # zero rather than resuming its cursor.
    assert sum(PREMISE in m for m in rows_after_resume) == 2, rows_after_resume
