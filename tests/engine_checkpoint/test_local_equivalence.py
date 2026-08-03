"""THE Stage B gate, local leg: run-to-checkpoint -> save -> continue
equals restore-the-checkpoint -> continue, byte-for-byte.

Directive ("Stage B: whole-branch persistence and recovery"): the stage
passes only when

    run to checkpoint -> save -> continue to result A
    restore the checkpoint separately -> continue to result B

produce the same deterministic trace and result.  Proven here on the
frozen fixture-1 world with one candidate over MAX_STEPS=4 and the
checkpoint at the end-of-step boundary 2, on the FULL signature
(committed events + shaped trace + GM memory + per-actor memories +
absolute step accounting + terminal status/state + guard interventions +
infrastructure errors), with three legs per seed:

- A  -- uninterrupted run;
- A' -- same call runs to the boundary, captures the checkpoint, and
        continues the SAME live objects to the result;
- B  -- a separately restored run: fresh objects rebuilt from the same
        plan, checkpoint state applied, RNG streams restored, remaining
        budget run with ``premise=''``.

The actor models append one global-``random`` draw per call (see
``checkpoint_model_specs``), so every committed event embeds the evolving
RNG stream: equality across the legs proves the checkpoint carried the
LIVE mid-run RNG state, and repeating the gate under a second independent
seed (which produces a visibly different trace) proves the equality is
not seed-coincidence.  A third leg round-trips the checkpoint blob
through disk bytes before restoring, and the blob's canonical JSON is
byte-stable across the trip.
"""

from __future__ import annotations

import json
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
                                SEED_ALT, branch_setup,
                                checkpoint_identity, full_signature,
                                load_fixture_one, make_models,
                                prompt_pure_params, signature_sha256)
from checkpoint_model_specs import RNG_DRAW_MARKER
from sworldmodel.backends.concordia_local import runner as runner_module
from sworldmodel.backends.concordia_local.checkpoint import (
    checkpoint_canonical_json)
from sworldmodel.counterfactuals.manager import _seeded_branch_scope

CANDIDATE_ID = "concise_relevant"


def _run_three_legs(seed: int, tmp_path=None):
    """Return (raw_A, raw_Aprime, raw_B[, raw_B_disk]) for one seed."""
    fx = load_fixture_one()
    candidate, plan, branch_id, branch_seed = branch_setup(
        fx, CANDIDATE_ID, seed=seed)
    params = prompt_pure_params(fx, rng_draw_actors=("sender", "recipient"))
    identity = checkpoint_identity(candidate, branch_id, branch_seed)

    # Leg A: uninterrupted.
    with _seeded_branch_scope(branch_seed):
        actor_models, gm_model = make_models(params, candidate, branch_seed)
        raw_a = runner_module.run_branch(
            plan, actor_models=actor_models, gm_model=gm_model)

    # Leg A': run to the boundary, capture, continue the same objects.
    with _seeded_branch_scope(branch_seed):
        actor_models, gm_model = make_models(params, candidate, branch_seed)
        raw_ap = runner_module.run_branch(
            plan, actor_models=actor_models, gm_model=gm_model,
            checkpoint_after=CHECKPOINT_AFTER,
            checkpoint_identity=identity)
    checkpoint = raw_ap["checkpoint"]
    assert checkpoint is not None
    assert raw_ap["checkpoint_captured_at"] == CHECKPOINT_AFTER
    assert raw_ap["halted_at_checkpoint"] is False

    # Leg B: restore the checkpoint separately (fresh objects, fresh
    # models) and continue.
    with _seeded_branch_scope(branch_seed):
        actor_models, gm_model = make_models(params, candidate, branch_seed)
        raw_b = runner_module.run_branch(
            plan, actor_models=actor_models, gm_model=gm_model,
            resume_from=checkpoint)
    assert raw_b["resumed_from_checkpoint"] is True
    assert raw_b["resumed_at_step"] == CHECKPOINT_AFTER

    if tmp_path is None:
        return raw_a, raw_ap, raw_b, checkpoint

    # Disk leg: the blob survives a real file round trip byte-stably and
    # restores identically from the loaded copy.
    blob_path = tmp_path / "branch_checkpoint.json"
    blob_path.write_text(json.dumps(checkpoint, sort_keys=True, indent=2),
                         encoding="utf-8")
    loaded = json.loads(blob_path.read_text(encoding="utf-8"))
    assert checkpoint_canonical_json(loaded) \
        == checkpoint_canonical_json(checkpoint)
    with _seeded_branch_scope(branch_seed):
        actor_models, gm_model = make_models(params, candidate, branch_seed)
        raw_b_disk = runner_module.run_branch(
            plan, actor_models=actor_models, gm_model=gm_model,
            resume_from=loaded)
    return raw_a, raw_ap, raw_b, checkpoint, raw_b_disk


def test_stage_b_gate_three_way_equivalence_and_disk_round_trip(tmp_path):
    raw_a, raw_ap, raw_b, checkpoint, raw_b_disk = _run_three_legs(
        SEED, tmp_path)

    # The run demonstrably exercised the discriminating machinery: four
    # absolute steps, cutoff, and every committed actor turn embeds a
    # live global-random draw.
    for raw in (raw_a, raw_ap, raw_b, raw_b_disk):
        assert raw["steps_completed"] == MAX_STEPS
        assert raw["terminal_status"] == "cutoff"
        assert raw["infrastructure_errors"] == []
        draw_events = [event for event in raw["committed_events"]
                       if RNG_DRAW_MARKER in event]
        assert len(draw_events) == MAX_STEPS, raw["committed_events"]

    # THE gate: A == A' == B == B(disk), byte-for-byte on the full
    # signature.
    sig_a = full_signature(raw_a)
    assert full_signature(raw_ap) == sig_a, (
        "continue-after-checkpoint diverged from the uninterrupted run")
    assert full_signature(raw_b) == sig_a, (
        "restore-and-continue diverged from the uninterrupted run")
    assert full_signature(raw_b_disk) == sig_a, (
        "restore from the disk round-tripped blob diverged")

    # The checkpoint blob is JSON-canonical and stable.
    text = checkpoint_canonical_json(checkpoint)
    assert checkpoint_canonical_json(json.loads(text)) == text


def test_stage_b_gate_holds_under_an_independent_seed():
    """Repeat the three-way gate under a different seed: equality again,
    while the two seeds' traces differ -- so the leg equality cannot be
    seed-coincidence (the trace demonstrably depends on the seed
    material and the evolving stream the checkpoint carried)."""
    raw_a1, raw_ap1, raw_b1, _cp1 = _run_three_legs(SEED)
    raw_a2, raw_ap2, raw_b2, _cp2 = _run_three_legs(SEED_ALT)

    sig_seed1 = full_signature(raw_a1)
    sig_seed2 = full_signature(raw_a2)
    assert full_signature(raw_ap1) == sig_seed1
    assert full_signature(raw_b1) == sig_seed1
    assert full_signature(raw_ap2) == sig_seed2
    assert full_signature(raw_b2) == sig_seed2
    assert sig_seed1 != sig_seed2, (
        "the two seeds produced identical traces -- the rng-draw "
        "discriminator is not actually consuming seed-dependent "
        "randomness, so the equality above would be vacuous")

    # Evidence hashes for the stage record (assertion doubles as the
    # printable A/A'/B triple per seed).
    triple_seed1 = (signature_sha256(raw_a1), signature_sha256(raw_ap1),
                    signature_sha256(raw_b1))
    triple_seed2 = (signature_sha256(raw_a2), signature_sha256(raw_ap2),
                    signature_sha256(raw_b2))
    assert len(set(triple_seed1)) == 1, triple_seed1
    assert len(set(triple_seed2)) == 1, triple_seed2
    assert triple_seed1[0] != triple_seed2[0]
    print(f"STAGE_B_LOCAL_EVIDENCE seed={SEED} A=A'=B={triple_seed1[0]}")
    print(f"STAGE_B_LOCAL_EVIDENCE seed={SEED_ALT} "
          f"A=A'=B={triple_seed2[0]}")


def test_checkpoint_blob_shape_mirrors_upstream_and_carries_sidecar():
    """The blob's top level mirrors the audited upstream checkpoint
    shape (entities/game_masters/raw_log keyed by entity name) plus the
    SWORLDMODEL sidecar and per-component manifest."""
    _raw_a, raw_ap, _raw_b, checkpoint = _run_three_legs(SEED)

    assert set(checkpoint) == {"schema_version", "engine_backend",
                               "plan_id", "world_id", "entities",
                               "game_masters", "raw_log", "sidecar",
                               "manifest"}
    assert set(checkpoint["entities"]) == {"Alex", "Morgan"}
    for state in checkpoint["entities"].values():
        assert set(state) == {"act_component", "context_components"}
    assert list(checkpoint["game_masters"]) == ["rules"]

    sidecar = checkpoint["sidecar"]
    assert sidecar["engine_cursor"] == {
        "steps_completed": CHECKPOINT_AFTER,
        "remaining_steps": MAX_STEPS - CHECKPOINT_AFTER,
        "premise_delivered": True,
    }
    assert sidecar["intervention_identity"]["candidate_id"] == CANDIDATE_ID
    assert len(sidecar["rng"]["python_random"]["internal_state"]) == 625
    assert len(sidecar["rng"]["numpy_legacy"]["keys"]) == 624
    # Every serialized component is listed.
    manifest = checkpoint["manifest"]
    for name, state in checkpoint["entities"].items():
        assert f"entities.{name}.act_component" in manifest
        for key in state["context_components"]:
            assert f"entities.{name}.context_components.{key}" in manifest
    assert "sidecar.rng.python_random" in manifest
    assert "sidecar.engine_cursor" in manifest
    assert "raw_log" in manifest
    # Boundary evidence rides the blob: the raw log covers exactly the
    # pre-boundary steps, and the continued run kept extending its own.
    assert len(checkpoint["raw_log"]) == CHECKPOINT_AFTER
    assert len(raw_ap["raw_log"]) == MAX_STEPS
