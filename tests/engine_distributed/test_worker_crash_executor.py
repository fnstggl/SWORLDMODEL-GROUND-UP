"""Executor-level worker crash: fail-loud-once through the harvest arm.

Integration Reliability review (wave 2) MEDIUM: the executor previously
submitted its Ray tasks bare, inheriting Ray's default silent
``max_retries=3`` on system failure -- a crashed worker was silently
re-executed (double-spend under live models; checkpoint-resume
inversion).  Both submit sites now pin ``.options(max_retries=0)``, so a
worker crash surfaces exactly once as Ray's typed error in the harvest
loop's ``except`` arm (the ``task_error`` channel) and is synthesized as
the reported ``driver_only`` failure ``BranchResult``.

This module drives that arm END TO END through
``run_candidates_distributed``: the target branch's worker OS process is
SIGKILLed while it executes (the previously zero-coverage arm), and the
run must complete with the crash reported in list position, siblings
unaffected (signature-equal to a crash-free reference run), and every
accounting equality intact.

Kill discipline (adapted from
``tests/engine_robustness/test_ray_worker_failure.py``): only a process
our own submission created is touched, identified by the
``ray::step_agent_batch`` process title that exists exactly while the
task runs -- and the kill window is DETERMINISTIC: the target branch's
sender model writes a handshake marker file and then BLOCKS
(``StallOnFirstCallModel``), and with ``parallelism=1`` the target's
task is the only one in flight when the marker appears.

Discrimination (verified by mutation during development): with the
harvest ``except`` arm removed the typed error propagates and this test
fails; with the ``max_retries=0`` pin removed Ray silently re-executes
the killed task to success and the ``task_error``/``driver_only``
assertions fail.
"""

from __future__ import annotations

import sys

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

import os
import signal
import threading
import time
from pathlib import Path

from distributed_helpers import (MAX_STEPS, SEED, load_fixture_one,
                                 model_spec, result_signature,
                                 scripted_params)
from sworldmodel.backends.agentsociety.branch_executor import \
    run_candidates_distributed

#: blocking window the stalled sender holds open for the killer thread
STALL_S = 8.0
_TASK_TITLE = "ray::step_agent_batch"


def _step_worker_pids() -> list:
    """PIDs currently executing a step task of OUR runtime (Ray retitles
    a worker process ``ray::<task>`` exactly while it runs the task)."""
    hits = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            cmd = Path(f"/proc/{entry}/cmdline").read_bytes()
        except OSError:
            continue
        if cmd.replace(b"\0", b" ").decode(
                "utf-8", "replace").startswith(_TASK_TITLE):
            hits.append(int(entry))
    return hits


def _kill_after_marker(marker_path: Path, box: dict, *,
                       settle_s: float = 0.3,
                       timeout_s: float = 60.0) -> None:
    """Killer thread body: wait for the in-worker handshake marker, then
    SIGKILL the (single) step-task worker.  With ``parallelism=1`` the
    marker guarantees the target's task is the only one in flight."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and not marker_path.exists():
        time.sleep(0.05)
    if not marker_path.exists():
        box["timeout"] = "marker never appeared"
        return
    time.sleep(settle_s)  # the worker is inside its blocking sleep
    while time.monotonic() < deadline:
        pids = _step_worker_pids()
        if pids:
            box["observed_pids"] = list(pids)
            for target in pids:
                try:
                    os.kill(target, signal.SIGKILL)
                    box.setdefault("killed", []).append(target)
                except OSError:
                    pass
            if box.get("killed"):
                return
        time.sleep(0.05)
    box["timeout"] = "no step worker appeared after the marker"


def test_sigkilled_worker_surfaces_once_typed_and_synthesized(
        distributed_engine, tmp_path):
    """The zero-coverage arm, end to end: SIGKILL -> typed task_error ->
    synthesized driver_only failure in list position; siblings
    signature-equal to a crash-free reference; accounting intact."""
    fx = load_fixture_one()
    candidate_ids = [candidate.candidate_id for candidate in fx.candidates]
    target_id = candidate_ids[1]
    marker_dir = tmp_path / "handshake"
    marker_dir.mkdir()
    marker_path = marker_dir / f"{target_id}.stalled"

    params = scripted_params(fx)
    params["stall"] = {
        "actor": "sender",
        "candidate_ids": [target_id],
        "marker_dir": str(marker_dir),
        "sleep_s": STALL_S,
    }

    box: dict = {}
    killer = threading.Thread(target=_kill_after_marker,
                              args=(marker_path, box))
    killer.start()
    try:
        run = run_candidates_distributed(
            fx.world, fx.candidates,
            model_spec=model_spec(params),
            seed=SEED, max_steps=MAX_STEPS,
            evaluator_spec=fx.evaluator_spec, registry=fx.registry,
            run_dir=tmp_path / "crash_run", parallelism=1)
    finally:
        killer.join(timeout=90.0)
    assert not killer.is_alive()
    assert box.get("killed"), f"killer thread never killed: {box}"
    # Deterministic window: exactly the target's task was in flight.
    assert len(box.get("observed_pids", [])) == 1, box

    # The crashed branch is present IN ITS LIST POSITION as the
    # synthesized reported-never-hidden failure shape.
    assert [result.candidate_id for result in run.results] == candidate_ids
    crashed = run.results[1]
    assert crashed.candidate_id == target_id
    assert crashed.terminal_status == "incomplete"
    assert len(crashed.infrastructure_errors) == 1
    assert crashed.infrastructure_errors[0].startswith("driver: ")
    assert "WorkerCrashedError" in crashed.infrastructure_errors[0]
    assert list(crashed.event_trace) == []
    assert dict(crashed.outcome_metrics) == {}
    assert list(crashed.artifact_paths) == []
    assert run.runner_records[target_id] is None

    # Typed harvest channel + driver_only evidence: the kill left NO
    # workspace files (atomic end-of-step writes), so the driver record
    # is the only failure evidence -- exactly the documented shape.
    entry = run.execution_report["per_branch"][target_id]
    assert entry["channel"] == "task_error"
    assert entry["driver_ok"] is False
    assert "WorkerCrashedError" in entry["driver_error"]
    assert entry["failure_evidence"] == "driver_only"
    assert entry["result_file"] is False
    assert entry["record_file"] is False
    assert entry["error_file"] is False
    state_dir = Path(entry["workspace"]) / "state"
    assert not (state_dir / "branch_result.json").exists()
    assert not (state_dir / "branch_error.json").exists()

    # Siblings completed cleanly, unaffected.
    healthy = [run.results[0], run.results[2]]
    for result in healthy:
        assert result.infrastructure_errors == ()
        assert result.terminal_status == "cutoff"
        sibling_entry = run.execution_report["per_branch"][
            result.candidate_id]
        assert sibling_entry["driver_ok"] is True
        assert sibling_entry["channel"] != "task_error"

    # Signature equality against a crash-free reference run of the same
    # sibling candidates: the crash leaked nothing into them.
    fx_reference = load_fixture_one()
    reference = run_candidates_distributed(
        fx_reference.world,
        [fx_reference.candidates[0], fx_reference.candidates[2]],
        model_spec=model_spec(scripted_params(fx_reference)),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx_reference.evaluator_spec,
        registry=fx_reference.registry,
        run_dir=tmp_path / "reference_run", parallelism=1)
    for with_crash, without in zip(healthy, reference.results):
        assert result_signature(with_crash) \
            == result_signature(without), with_crash.candidate_id

    # Exactly-once ACCOUNTING equalities all hold in the crash run.
    report = run.execution_report
    assert report["exactly_once"] is True
    assert report["submitted_candidate_ids"] == candidate_ids
    assert sorted(report["harvested_candidate_ids"]) \
        == sorted(candidate_ids)
    assert report["collected_candidate_ids"] == candidate_ids

    # Nothing of ours is still running a step task.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and _step_worker_pids():
        time.sleep(0.1)
    assert _step_worker_pids() == []
