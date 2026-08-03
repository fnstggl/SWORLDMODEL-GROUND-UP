"""Distributed failure isolation: a branch that fails INSIDE a worker is
reported through BOTH channels and never touches its siblings.

Directive Stage A gate: one failed branch does not stop the others, and
errors are recorded.  The injected failure is a model that raises
MID-BRANCH (after the acting entity's turn already committed an event),
so this also proves the partial-trace preservation path: the branch
agent persists the partial ``branch_result.json`` (runner-captured
infrastructure error, trace up to the failure), writes
``branch_error.json``, and re-raises so the driver's Option 2 per-agent
record reports ok=False -- dual-channel evidence that must AGREE.
Contract rule R3: the broken branch reports ``incomplete``, never an
automatic failure verdict.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "distributed suite requires Python >= 3.12 (engine env); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("agentsociety2", exc_type=ImportError)
pytest.importorskip("ray", exc_type=ImportError)
pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from distributed_helpers import (MAX_STEPS, SEED, load_fixture_one,
                                 model_spec, result_signature,
                                 scripted_params)
from sworldmodel.backends.agentsociety.branch_executor import \
    run_candidates_distributed

FAILING_ID = "concise_relevant"   # the MIDDLE candidate of the fixture
MARKER = f"INJECTED_DISTRIBUTED_FAILURE_{FAILING_ID}"


def test_worker_mid_branch_failure_is_isolated_and_dual_channel(
        distributed_engine, tmp_path):
    fx = load_fixture_one()
    candidate_ids = [candidate.candidate_id for candidate in fx.candidates]
    assert candidate_ids[1] == FAILING_ID

    run_with_failure = run_candidates_distributed(
        fx.world, fx.candidates,
        model_spec=model_spec(
            scripted_params(fx, failing_ids=(FAILING_ID,))),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx.evaluator_spec, registry=fx.registry,
        run_dir=tmp_path / "with_failure", parallelism=2)

    # The failing branch is present IN ITS LIST POSITION -- reported,
    # never replaced or dropped.
    assert [result.candidate_id
            for result in run_with_failure.results] == candidate_ids
    failed = run_with_failure.results[1]
    assert failed.candidate_id == FAILING_ID
    assert failed.terminal_status == "incomplete"
    assert len(failed.infrastructure_errors) == 1
    assert MARKER in failed.infrastructure_errors[0]
    # Mid-branch: the partial trace up to the failure is preserved
    # (premise + the sender's committed turn; the failure hit on the
    # recipient's turn, step 2 of 2) -- exactly the local manager's
    # mid-branch shape.
    assert len(failed.event_trace) == 2
    assert failed.terminal_world_state["steps_completed"] == 1

    # Dual-channel failure evidence, agreeing: driver ok=False AND the
    # workspace error file exists and names the same failure.
    entry = run_with_failure.execution_report["per_branch"][FAILING_ID]
    assert entry["driver_ok"] is False
    assert entry["result_file"] is True
    assert entry["error_file"] is True
    assert entry["failure_evidence"] == "dual_channel"
    assert "infrastructure errors" in entry["driver_error"]
    error_payload = json.loads(
        (Path(entry["workspace"]) / "state" / "branch_error.json")
        .read_text(encoding="utf-8"))
    assert error_payload["phase"] == "captured_by_runner"
    assert error_payload["candidate_id"] == FAILING_ID
    assert any(MARKER in detail for detail in error_payload["details"])
    # The failed branch's artifacts reference all three evidence files.
    assert sorted(Path(path).name for path in failed.artifact_paths) \
        == ["branch_error.json", "branch_result.json",
            "runner_record.json"]
    # The runner record (guard/diagnostics channel) still exists for the
    # failed branch -- the runner returned a partial record.
    assert run_with_failure.runner_records[FAILING_ID] is not None

    # Siblings completed cleanly, unaffected.
    healthy = [run_with_failure.results[0], run_with_failure.results[2]]
    for result in healthy:
        assert result.infrastructure_errors == ()
        assert result.terminal_status == "cutoff"
        assert len(result.event_trace) == 3
        sibling_entry = run_with_failure.execution_report["per_branch"][
            result.candidate_id]
        assert sibling_entry["driver_ok"] is True
        assert sibling_entry["error_file"] is False

    # A distributed run WITHOUT the failing candidate: the siblings are
    # byte-identical (signature keys), proving the failure leaked nothing
    # into them.
    fx_reference = load_fixture_one()
    reference = run_candidates_distributed(
        fx_reference.world,
        [fx_reference.candidates[0], fx_reference.candidates[2]],
        model_spec=model_spec(scripted_params(fx_reference)),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx_reference.evaluator_spec,
        registry=fx_reference.registry,
        run_dir=tmp_path / "without_failure", parallelism=2)
    assert [result.candidate_id for result in reference.results] \
        == [candidate_ids[0], candidate_ids[2]]
    for with_failure, without in zip(healthy, reference.results):
        assert result_signature(with_failure) \
            == result_signature(without), with_failure.candidate_id

    # Exactly-once accounting still holds in the failing run.
    report = run_with_failure.execution_report
    assert report["exactly_once"] is True
    assert report["submitted_candidate_ids"] == candidate_ids
    assert sorted(report["harvested_candidate_ids"]) \
        == sorted(candidate_ids)
    assert report["collected_candidate_ids"] == candidate_ids
