"""THE Stage B gate, distributed leg: a branch interrupted after the
checkpoint step and resumed by a SECOND ``step_agent_batch`` call from
its own workspace equals the uninterrupted distributed run.

Three distributed runs over frozen fixture-1 (all three candidates,
MAX_STEPS=4, rng-draw prompt-pure models rebuilt inside workers from the
serializable spec):

1. UNINTERRUPTED  -- the plain Stage A path (no checkpoint);
2. INTERRUPT+RESUME -- ``run_interrupted_then_resume(checkpoint_after=2)``:
   round 1 halts every branch AT the boundary (checkpoint blob persisted,
   no result -- the driver recognizes the interrupted state explicitly),
   round 2 resumes each branch from its workspace to completion;
3. CHECKPOINT+CONTINUE -- ``run_candidates_distributed(checkpoint_after=2)``:
   one step call persists the blob and completes.

Per-candidate ``BranchResult`` signatures (the Stage A SIGNATURE_KEYS
rule) must be byte-identical across all three runs.  Because the actor
models embed live global-``random`` draws in every committed event and
Ray schedules the two rounds on whatever worker process is free, the
resumed equality also proves RNG stream continuity ACROSS PROCESSES --
the checkpoint serialized the mid-run ``random`` state in one worker and
the continuation restored it in another.  Exactly-once accounting holds
per round and for collection, and every resumed/continued result
references the checkpoint blob in ``artifact_paths``.
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

pytest.importorskip("agentsociety2", exc_type=ImportError)
pytest.importorskip("ray", exc_type=ImportError)
pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from pathlib import Path

from checkpoint_helpers import (CHECKPOINT_AFTER, MAX_STEPS, SEED,
                                load_fixture_one, model_spec,
                                prompt_pure_params)
from checkpoint_model_specs import RNG_DRAW_MARKER
from distributed_helpers import result_signature
from sworldmodel.backends.agentsociety.branch_executor import (
    run_candidates_distributed, run_interrupted_then_resume)
from sworldmodel.backends.concordia_local.checkpoint import (
    validate_checkpoint)

CANDIDATE_IDS = ["long_generic", "concise_relevant", "urgent_pressure"]


def _params():
    return prompt_pure_params(load_fixture_one(),
                              rng_draw_actors=("sender", "recipient"))


def _signatures(run) -> dict:
    return {result.candidate_id: result_signature(result)
            for result in run.results}


def test_interrupted_branch_resumed_from_workspace_equals_uninterrupted(
        checkpoint_engine, tmp_path):
    params = _params()

    # Leg 1: uninterrupted distributed run.
    fx_plain = load_fixture_one()
    plain = run_candidates_distributed(
        fx_plain.world, fx_plain.candidates,
        model_spec=model_spec(params),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx_plain.evaluator_spec,
        registry=fx_plain.registry,
        run_dir=tmp_path / "plain",
        parallelism=2)

    # Leg 2: interrupted at the boundary, resumed by a second batch call.
    interrupted_seen = {}

    def _between_rounds(workspaces):
        # The deliberately interrupted state, observed BETWEEN the two
        # batch calls: checkpoint blob present and valid, no result yet.
        for candidate_id, workspace in workspaces.items():
            state_dir = Path(workspace) / "state"
            blob_path = state_dir / "branch_checkpoint.json"
            assert blob_path.is_file(), candidate_id
            blob = json.loads(blob_path.read_text(encoding="utf-8"))
            validate_checkpoint(blob)
            cursor = blob["sidecar"]["engine_cursor"]
            assert cursor == {"steps_completed": CHECKPOINT_AFTER,
                              "remaining_steps":
                                  MAX_STEPS - CHECKPOINT_AFTER,
                              "premise_delivered": True}
            assert not (state_dir / "branch_result.json").exists()
            assert not (state_dir / "runner_record.json").exists()
            assert not (state_dir / "branch_error.json").exists()
            interrupted_seen[candidate_id] = blob["sidecar"][
                "intervention_identity"]["candidate_id"]

    fx_resume = load_fixture_one()
    resumed = run_interrupted_then_resume(
        fx_resume.world, fx_resume.candidates,
        model_spec=model_spec(params),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx_resume.evaluator_spec,
        registry=fx_resume.registry,
        run_dir=tmp_path / "resume",
        parallelism=2,
        checkpoint_after=CHECKPOINT_AFTER,
        between_rounds_hook=_between_rounds)

    # The interrupt round really interrupted every branch.
    assert interrupted_seen == {cid: cid for cid in CANDIDATE_IDS}

    # Identical frozen-base identity across the legs.
    assert resumed.base_plan_content_hash == plain.base_plan_content_hash
    assert resumed.branch_ids == plain.branch_ids
    assert resumed.branch_seeds == plain.branch_seeds

    # THE gate, distributed leg: byte-identical per-candidate signatures
    # (trace + terminal status/state + errors), including the embedded
    # live RNG draws that crossed the process boundary via the blob.
    plain_signatures = _signatures(plain)
    resumed_signatures = _signatures(resumed)
    assert set(plain_signatures) == set(CANDIDATE_IDS)
    for candidate_id in CANDIDATE_IDS:
        assert resumed_signatures[candidate_id] \
            == plain_signatures[candidate_id], (
                f"{candidate_id}: interrupted+resumed distributed branch "
                "diverged from the uninterrupted distributed run")
        assert f"[{RNG_DRAW_MARKER} " in plain_signatures[candidate_id]

    # The resumed records prove the second call actually RESUMED (not
    # re-ran) the branch, with the guard evidence channel intact.
    for candidate_id in CANDIDATE_IDS:
        record = resumed.runner_records[candidate_id]
        assert record is not None
        assert record["resumed_from_checkpoint"] is True
        assert record["resumed_at_step"] == CHECKPOINT_AFTER
        assert record["steps_completed"] == MAX_STEPS
        assert record["guard_interventions"] \
            == plain.runner_records[candidate_id]["guard_interventions"] \
            == []
        assert record["worker_execution"]["pid"] > 0

    # Checkpoint blob referenced from artifact_paths and valid on disk.
    for result in resumed.results:
        names = sorted(Path(path).name for path in result.artifact_paths)
        assert names == ["branch_checkpoint.json", "branch_result.json",
                         "runner_record.json"]
        blob_path = [path for path in result.artifact_paths
                     if path.endswith("branch_checkpoint.json")][0]
        validate_checkpoint(json.loads(
            Path(blob_path).read_text(encoding="utf-8")))

    # Exactly-once accounting still holds: every candidate submitted
    # once per round, collected exactly once, both rounds bounded.
    report = resumed.execution_report
    assert report["mode"] == "interrupt_resume"
    assert report["exactly_once"] is True
    assert report["checkpoint_after"] == CHECKPOINT_AFTER
    assert report["interrupted_candidate_ids"] == CANDIDATE_IDS
    assert report["collected_candidate_ids"] == CANDIDATE_IDS
    assert [entry["round"] for entry in report["rounds"]] == [1, 2]
    for entry in report["rounds"]:
        assert entry["submitted_candidate_ids"] == CANDIDATE_IDS
        assert entry["driver_max_in_flight"] <= 2
    for candidate_id in CANDIDATE_IDS:
        per_branch = report["per_branch"][candidate_id]
        assert per_branch["checkpoint_file"] is True
        assert per_branch["interrupted_state"]["steps_completed"] \
            == CHECKPOINT_AFTER
        assert per_branch["checkpoint_round"]["harvested_unix"] \
            <= per_branch["submitted_unix"]
    assert (tmp_path / "resume" / "execution_report.json").is_file()


def test_checkpoint_and_continue_in_one_call_matches_and_references_blob(
        checkpoint_engine, tmp_path):
    params = _params()

    fx_plain = load_fixture_one()
    plain = run_candidates_distributed(
        fx_plain.world, fx_plain.candidates,
        model_spec=model_spec(params),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx_plain.evaluator_spec,
        registry=fx_plain.registry,
        run_dir=tmp_path / "plain",
        parallelism=2)

    fx_continue = load_fixture_one()
    continued = run_candidates_distributed(
        fx_continue.world, fx_continue.candidates,
        model_spec=model_spec(params),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx_continue.evaluator_spec,
        registry=fx_continue.registry,
        run_dir=tmp_path / "continue",
        parallelism=2,
        checkpoint_after=CHECKPOINT_AFTER)

    # Persisting the checkpoint mid-branch must not change the result.
    plain_signatures = _signatures(plain)
    continued_signatures = _signatures(continued)
    for candidate_id in CANDIDATE_IDS:
        assert continued_signatures[candidate_id] \
            == plain_signatures[candidate_id], candidate_id

    # The blob exists, validates, and is referenced from artifact_paths;
    # the record carries the capture evidence.
    assert continued.execution_report["checkpoint_after"] \
        == CHECKPOINT_AFTER
    for result in continued.results:
        blob_paths = [path for path in result.artifact_paths
                      if path.endswith("branch_checkpoint.json")]
        assert len(blob_paths) == 1
        validate_checkpoint(json.loads(
            Path(blob_paths[0]).read_text(encoding="utf-8")))
    for candidate_id in CANDIDATE_IDS:
        record = continued.runner_records[candidate_id]
        assert record["checkpoint_captured_at"] == CHECKPOINT_AFTER
        assert record["halted_at_checkpoint"] is False
        assert "checkpoint" not in record  # blob lives in its own file
