"""Restore correctness: no premise redelivery, no duplicate seeding, RNG
continuity with a discriminating counter-example, and loud refusal of
tampered or incomplete checkpoints (including through the Phase 3
snapshot contract).

The RNG discriminator (directive: random state must be part of the
persisted branch): the actor models append one global-``random`` draw
per call, so the committed events of steps 3-4 depend on the stream
position reached at the boundary.  A NAIVE resume -- rebuild + set_state
inside a freshly seeded scope but WITHOUT restoring the captured
``random`` state -- restarts the stream at position 0 and demonstrably
diverges from the uninterrupted run; the proper resume restores
``random.setstate`` and matches byte-for-byte.  The naive control uses
the SAME rebuilt objects machinery (``checkpoint.restore_branch`` +
``runner.run_built_branch``), so the only difference between the two
legs is the RNG restoration itself.
"""

from __future__ import annotations

import copy
import json
import random
import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "checkpoint suite requires Python >= 3.12 (engine env); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from checkpoint_helpers import (CHECKPOINT_AFTER, MAX_STEPS, SEED,
                                branch_setup, checkpoint_identity,
                                full_signature, load_fixture_one,
                                make_models, prompt_pure_params)
from checkpoint_model_specs import RNG_DRAW_MARKER
from sworldmodel.backends.concordia_local import checkpoint as cp_lib
from sworldmodel.backends.concordia_local import runner as runner_module
from sworldmodel.counterfactuals.manager import _seeded_branch_scope
from sworldmodel.counterfactuals.snapshot import (build_base_plan,
                                                  build_base_snapshot,
                                                  build_live_snapshot)
from sworldmodel.decision.contracts import (ContractValidationError,
                                            SimulationSnapshot)
from sworldmodel.decision.validation import validate_semantics

CANDIDATE_ID = "concise_relevant"


@pytest.fixture(scope="module")
def captured_run():
    """One uninterrupted run (A) plus one checkpoint-and-continue run
    (A') and its checkpoint, with rng-draw models, at SEED."""
    fx = load_fixture_one()
    candidate, plan, branch_id, branch_seed = branch_setup(fx, CANDIDATE_ID)
    params = prompt_pure_params(fx, rng_draw_actors=("sender", "recipient"))
    identity = checkpoint_identity(candidate, branch_id, branch_seed)

    with _seeded_branch_scope(branch_seed):
        actor_models, gm_model = make_models(params, candidate, branch_seed)
        raw_a = runner_module.run_branch(
            plan, actor_models=actor_models, gm_model=gm_model)
    with _seeded_branch_scope(branch_seed):
        actor_models, gm_model = make_models(params, candidate, branch_seed)
        raw_ap = runner_module.run_branch(
            plan, actor_models=actor_models, gm_model=gm_model,
            checkpoint_after=CHECKPOINT_AFTER,
            checkpoint_identity=identity)
    assert raw_ap["checkpoint"] is not None
    return {
        "fx": fx, "candidate": candidate, "plan": plan,
        "branch_id": branch_id, "branch_seed": branch_seed,
        "params": params, "raw_a": raw_a, "raw_ap": raw_ap,
        "checkpoint": raw_ap["checkpoint"],
    }


def _resume(captured, *, restore_rng: bool) -> dict:
    """Resume through the SAME rebuilt-object machinery, with the RNG
    restoration as the single controlled difference."""
    plan = captured["plan"]
    with _seeded_branch_scope(captured["branch_seed"]):
        actor_models, gm_model = make_models(
            captured["params"], captured["candidate"],
            captured["branch_seed"])
        if restore_rng:
            return runner_module.run_branch(
                plan, actor_models=actor_models, gm_model=gm_model,
                resume_from=captured["checkpoint"])
        restored = cp_lib.restore_branch(
            plan, captured["checkpoint"], actor_models=actor_models,
            gm_model=gm_model)
        # NAIVE control: rebuild + set_state, but the freshly seeded
        # scope's random stream is left at position 0.
        return runner_module.run_built_branch(
            restored.built,
            step_cell=[restored.steps_completed],
            guard_interventions=list(restored.guard_interventions),
            steps_already_completed=restored.steps_completed,
            initial_raw_log=restored.raw_log)


# ---------------------------------------------------------------------------
# Premise / seeding correctness
# ---------------------------------------------------------------------------

def test_restored_run_never_reobserves_premise_or_reseeds_observations(
        captured_run):
    raw_a = captured_run["raw_a"]
    raw_b = _resume(captured_run, restore_rng=True)
    plan = captured_run["plan"]

    # The opening premise event exists EXACTLY once in both runs -- the
    # upstream engine would deliver it again on a naive re-play
    # (sequential.py:243-246); premise='' on resume suppresses that.
    premise = plan.neutral_premise
    assert sum(premise in row for row in raw_a["gm_memory"]) == 1
    assert sum(premise in row for row in raw_b["gm_memory"]) == 1

    # The intervention insertion observation (the sender's t0 candidate
    # text) appears exactly once in the sender's memory on both sides --
    # restore did NOT re-queue the initial observations.
    insertion_needle = captured_run["candidate"].action.strip()
    for raw in (raw_a, raw_b):
        sender_rows = raw["actor_memories"]["sender"]
        t0_rows = [row for row in sender_rows
                   if insertion_needle in row
                   and RNG_DRAW_MARKER not in row]
        assert len(t0_rows) == 1, sender_rows

    # No duplicate memory rows anywhere: per-actor row multisets match
    # the uninterrupted run exactly (byte-level, order included).
    assert raw_b["actor_memories"] == raw_a["actor_memories"]
    assert raw_b["gm_memory"] == raw_a["gm_memory"]


# ---------------------------------------------------------------------------
# RNG continuity: the discriminating counter-example
# ---------------------------------------------------------------------------

def test_naive_reseed_diverges_and_restored_rng_matches(captured_run):
    raw_a = captured_run["raw_a"]
    naive = _resume(captured_run, restore_rng=False)
    proper = _resume(captured_run, restore_rng=True)

    # The proper resume IS the uninterrupted run, byte-for-byte.
    assert full_signature(proper) == full_signature(raw_a)

    # The naive control ran cleanly to completion...
    assert naive["infrastructure_errors"] == []
    assert naive["steps_completed"] == MAX_STEPS
    # ...but its post-boundary events embed draws from a RESTARTED
    # stream: the trace visibly diverges, so the discriminator has real
    # power and the equality above is not vacuous.
    assert full_signature(naive) != full_signature(raw_a), (
        "the naive re-seeded resume matched the uninterrupted run -- "
        "the discriminator no longer consumes evolving global random "
        "and cannot prove RNG state restoration")

    # Divergence localized exactly where it must be: the pre-boundary
    # events (restored verbatim from the checkpoint) are identical, the
    # post-boundary events differ only in the embedded draws.
    boundary = CHECKPOINT_AFTER + 1  # premise event + 2 committed turns
    assert naive["committed_events"][:boundary] \
        == raw_a["committed_events"][:boundary]
    assert naive["committed_events"][boundary:] \
        != raw_a["committed_events"][boundary:]

    # And the naive control's post-boundary draws equal the STREAM HEAD
    # draws (positions 1..n of a fresh seed) -- direct evidence the
    # stream restarted rather than continuing.
    random.seed(captured_run["branch_seed"])
    head_draws = [str(random.getrandbits(32)) for _ in range(2)]
    post_boundary_text = "\n".join(naive["committed_events"][boundary:])
    for draw in head_draws:
        assert f"[{RNG_DRAW_MARKER} {draw}]" in post_boundary_text


def test_rng_state_helpers_round_trip_exactly():
    random.seed(4242)
    random.random()  # advance the stream mid-way
    before = random.getstate()
    payload = json.loads(json.dumps(cp_lib.export_python_rng_state()))
    random.random()  # perturb
    cp_lib.restore_python_rng_state(payload)
    assert random.getstate() == before

    import numpy
    numpy.random.seed(4242)
    numpy.random.random()
    legacy_before = numpy.random.get_state()
    legacy_payload = json.loads(
        json.dumps(cp_lib.export_numpy_legacy_state()))
    numpy.random.random()
    cp_lib.restore_numpy_legacy_state(legacy_payload)
    after = numpy.random.get_state()
    assert after[0] == legacy_before[0]
    assert list(after[1]) == list(legacy_before[1])
    assert after[2:] == legacy_before[2:]


def test_resume_outside_a_seeded_scope_is_refused(captured_run):
    """The numpy draw discipline is scope-provided; resuming without the
    scope would silently lose it, so the restore refuses loudly."""
    with pytest.raises(cp_lib.CheckpointError,
                       match="seeded branch scope"):
        cp_lib.restore_rng(captured_run["checkpoint"])


# ---------------------------------------------------------------------------
# Tampered / missing-key refusals
# ---------------------------------------------------------------------------

def _mutated(checkpoint, mutate):
    blob = copy.deepcopy(checkpoint)
    mutate(blob)
    return blob


def test_tampered_checkpoints_are_refused_loudly(captured_run):
    checkpoint = captured_run["checkpoint"]
    plan = captured_run["plan"]

    def restore(blob):
        with _seeded_branch_scope(captured_run["branch_seed"]):
            actor_models, gm_model = make_models(
                captured_run["params"], captured_run["candidate"],
                captured_run["branch_seed"])
            cp_lib.restore_branch(plan, blob, actor_models=actor_models,
                                  gm_model=gm_model)

    # Missing top-level section.
    with pytest.raises(cp_lib.CheckpointError, match="entities"):
        cp_lib.validate_checkpoint(
            _mutated(checkpoint, lambda b: b.pop("entities")))
    # Unsupported schema version.
    with pytest.raises(cp_lib.CheckpointError, match="schema_version"):
        cp_lib.validate_checkpoint(
            _mutated(checkpoint,
                     lambda b: b.update(schema_version=99)))
    # Missing RNG stream.
    with pytest.raises(cp_lib.CheckpointError, match="python_random"):
        cp_lib.validate_checkpoint(
            _mutated(checkpoint,
                     lambda b: b["sidecar"]["rng"].pop("python_random")))
    # Premise flag tampered: resume would redeliver the premise.
    with pytest.raises(cp_lib.CheckpointError, match="premise"):
        cp_lib.validate_checkpoint(
            _mutated(checkpoint, lambda b: b["sidecar"][
                "engine_cursor"].update(premise_delivered=False)))
    # Manifest no longer accounts for a serialized component.
    with pytest.raises(cp_lib.CheckpointError, match="manifest"):
        cp_lib.validate_checkpoint(
            _mutated(checkpoint, lambda b: b["entities"]["Alex"][
                "context_components"].update(injected_component={})))
    # Cross-plan restore refused by content hash.
    with pytest.raises(cp_lib.CheckpointError, match="plan"):
        restore(_mutated(checkpoint, lambda b: b["sidecar"].update(
            plan_content_hash="0" * 64)))
    # Broken cursor arithmetic refused at restore.
    with pytest.raises(cp_lib.CheckpointError, match="arithmetic"):
        restore(_mutated(checkpoint, lambda b: b["sidecar"][
            "engine_cursor"].update(steps_completed=3)))
    # A checkpoint with nothing left to run cannot be resumed.
    with pytest.raises(cp_lib.CheckpointError, match="remaining"):
        cp_lib.validate_checkpoint(
            _mutated(checkpoint, lambda b: b["sidecar"][
                "engine_cursor"].update(steps_completed=MAX_STEPS,
                                        remaining_steps=0)))


# ---------------------------------------------------------------------------
# Phase 3 snapshot semantics over the REAL checkpoint
# ---------------------------------------------------------------------------

def test_live_snapshot_carries_real_state_and_validates(captured_run):
    fx = captured_run["fx"]
    checkpoint = captured_run["checkpoint"]
    base_plan = build_base_plan(fx.world, fx.evaluator_spec,
                                max_steps=MAX_STEPS)
    base_snapshot = build_base_snapshot(base_plan, seed=SEED,
                                        registry=fx.registry)

    snapshot = build_live_snapshot(checkpoint, base_snapshot,
                                   registry=fx.registry)
    assert isinstance(snapshot, SimulationSnapshot)
    # The REAL component state replaced the genesis identity
    # placeholder: full memory text rides the snapshot.
    alex_state = snapshot.concordia_checkpoint["entities"]["Alex"]
    memory_blob = alex_state["context_components"]["__memory__"]
    assert captured_run["candidate"].action.strip() \
        in memory_blob["memory_bank"]
    live = snapshot.concordia_checkpoint["live"]
    assert live["form"] == "live_v1"
    assert live["base_snapshot_id"] == base_snapshot.snapshot_id
    # The directive's per-component manifest rides the live block.
    assert live["component_manifest"] == checkpoint["manifest"]
    # The contract sidecar carries the live cursor and RNG material.
    assert snapshot.sidecar.engine_cursor.steps_completed \
        == CHECKPOINT_AFTER
    assert snapshot.sidecar.engine_cursor.remaining_budget \
        == MAX_STEPS - CHECKPOINT_AFTER
    assert snapshot.sidecar.engine_cursor.premise_delivered is True
    assert snapshot.sidecar.rng["seed_material"] \
        == captured_run["branch_seed"]
    restored_state = json.loads(snapshot.sidecar.rng["python_random_state"])
    assert restored_state \
        == checkpoint["sidecar"]["rng"]["python_random"]
    # Full semantic validation (manifest equality in both directions).
    validate_semantics(snapshot, fx.registry)


def test_live_snapshot_required_keys_and_manifest_enforced(captured_run):
    fx = captured_run["fx"]
    checkpoint = captured_run["checkpoint"]
    base_plan = build_base_plan(fx.world, fx.evaluator_spec,
                                max_steps=MAX_STEPS)
    base_snapshot = build_base_snapshot(base_plan, seed=SEED,
                                        registry=fx.registry)
    snapshot = build_live_snapshot(checkpoint, base_snapshot,
                                   registry=fx.registry)
    good = snapshot.to_dict()

    # Phase 3 required-key validation holds against the live blob shape.
    missing_entities = copy.deepcopy(good)
    del missing_entities["concordia_checkpoint"]["entities"]
    with pytest.raises(ContractValidationError):
        SimulationSnapshot.from_dict(missing_entities)

    # Manifest completeness is enforced in both directions.
    incomplete = copy.deepcopy(good)
    incomplete["snapshot_manifest"].remove("raw_log")
    with pytest.raises(ContractValidationError):
        validate_semantics(SimulationSnapshot.from_dict(incomplete),
                           fx.registry)
    unknown = copy.deepcopy(good)
    unknown["snapshot_manifest"].append("phantom_component")
    with pytest.raises(ContractValidationError):
        validate_semantics(SimulationSnapshot.from_dict(unknown),
                           fx.registry)

    # Builder-level identity refusals: another world's base snapshot and
    # a contradicted per-branch seed.
    with pytest.raises(ContractValidationError):
        build_live_snapshot(
            _mutated(checkpoint,
                     lambda b: b.update(world_id="w_0000000000000000")),
            base_snapshot)
    with pytest.raises(ContractValidationError):
        build_live_snapshot(
            _mutated(checkpoint, lambda b: b["sidecar"]["rng"].update(
                seed_material=1)),
            base_snapshot)
