"""Verification tier: assert the gate-G reconciliations over the
COMMITTED evidence of the completed monitored scale jobs.

INFRASTRUCTURE TEST ONLY: scripted/shallow scale exercise of the
AgentSociety execution substrate -- infrastructure rather than calibrated
societal simulation; no population realism claim.

This module is pure stdlib + the harness's pure helpers (no engine
imports), so it runs under BOTH the system Python 3.11 product suite and
the pinned engine environment.  It reads only committed files:

- ``tests/engine_scale/evidence/<job-id>/``  (job records, progress
  copies, partition summaries, reconciliations, checkpoints, failure
  artifacts, aggregate outputs)
- ``tests/engine_scale/specs/*.json``        (the declared run specs)
- ``.agent-run/BACKGROUND_JOBS.json``        (the monitored-job registry)
- ``docs/engine_migration/PHASE11_SCALE_EVIDENCE.md``

If the evidence has not been recorded yet, every test SKIPS with a
precise reason instead of failing -- the monitored jobs must run first.
Recomputation, not trust: expected totals are re-derived from the spec
files, the overlap ceiling is re-derived from the committed in-worker
windows, and the aggregate rollup hashes are re-derived from the
committed per-agent hash lists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
EVIDENCE = HERE / "evidence"
SPECS = HERE / "specs"

if str(HERE) not in sys.path:  # direct-invocation safety; conftest also adds
    sys.path.insert(0, str(HERE))

from scale_harness import (INFRA_ONLY_STATEMENT, PartitionSpec,  # noqa: E402
                           max_overlap, sha256_file, sha256_text)

S100_JOB = "phase11-scale100-full"
AGG_JOB = "phase11-scale1000-aggregate"
PARTITIONS = ("p1", "p2", "p3", "p4")
SEG_JOBS = {
    (pid, seg): f"phase11-scale1000-{pid}-seg{seg}"
    for pid in PARTITIONS for seg in ("A", "B")
}
ALL_JOBS = [S100_JOB, *SEG_JOBS.values(), AGG_JOB]

#: schedule-derived expectations (re-derived from the spec files below;
#: these literals document the intent)
S100_EXPECTED_ACTIONS = 394
P_EXPECTED_ACTIONS = {"p1": 600, "p2": 596, "p3": 599, "p4": 600}
TOTAL_EXPECTED_ACTIONS = 2395
S100_FAILURES = {"7": 3, "42": 3, "87": 3}


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(
            f"scale evidence not yet recorded: {path} is absent -- run "
            "the phase-11 monitored scale jobs and commit their evidence "
            "(see docs/engine_migration/PHASE11_SCALE_EVIDENCE.md)")
    return path


def _load(path: Path) -> dict:
    return json.loads(_require(path).read_text(encoding="utf-8"))


def _spec(name: str) -> PartitionSpec:
    return PartitionSpec.load(_require(SPECS / name))


def test_every_monitored_job_finished_with_strong_progress():
    """All ten scale jobs ran through run_monitored.py, finished with
    exit 0, and STRONG progress was recorded -- never a bare live PID,
    never a no-progress or total-timeout kill.

    Strong-progress evidence is ``completed_units`` (the runner's count
    of appended progress-file records), NOT the ``progress_source``
    label: that field records the MOST RECENT signal each poll, so a
    final stdout write after the last progress append can legitimately
    leave it at ``log_movement`` (observed on phase11-scale1000-p2-segA,
    completed_units=14).  A job that never fed the strong channel would
    show ``completed_units`` None/0 and fail here."""
    for job_id in ALL_JOBS:
        record = _load(EVIDENCE / job_id / "job.json")
        assert record["job_id"] == job_id
        assert record["state"] == "finished", (job_id, record["state"])
        assert record["exit_code"] == 0, (job_id, record["exit_code"])
        assert record["classification"] == "exploratory"
        assert record["termination_reason"] is None, (
            job_id, record["termination_reason"])
        units = record["completed_units"]
        assert isinstance(units, (int, float)) and units >= 5, (
            job_id, units)
        assert record["progress_source"] in (
            "progress_file", "completed_units", "log_movement"), (
            job_id, record["progress_source"])
        assert record["no_progress_timeout_s"] >= 240
        assert record["total_timeout_s"] <= 540
        observed = [s["state"] for s in record["observed_states"]]
        assert "progressing" in observed, (job_id, observed)
        progress = _require(EVIDENCE / job_id / "progress.jsonl")
        lines = [json.loads(line) for line in
                 progress.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        assert len(lines) >= units, (job_id, len(lines), units)
        assert lines[-1]["event"] == "job_done", (job_id, lines[-1])


def test_jobs_recorded_in_background_registry():
    _require(EVIDENCE / S100_JOB / "job.json")  # evidence-presence gate
    registry = _load(REPO_ROOT / ".agent-run" / "BACKGROUND_JOBS.json")
    by_id = {j.get("job_id"): j for j in registry.get("completed_jobs", [])}
    for job_id in ALL_JOBS:
        assert job_id in by_id, (
            f"{job_id} missing from BACKGROUND_JOBS.json completed_jobs")
        assert by_id[job_id]["state"] == "finished"


def test_100_agent_run_reconciled_exactly():
    """Gate G: the 100-agent run through the real worker/dispatcher path
    -- exact action accounting, schedule equality, failure isolation."""
    spec = _spec("scale100.json")
    assert spec.agent_count == 100
    assert spec.expected_total_actions() == S100_EXPECTED_ACTIONS

    reconciliation = _load(
        EVIDENCE / S100_JOB / "reconciliation.json")
    assert reconciliation["ok"] is True
    assert reconciliation["violations"] == []
    counts = reconciliation["counts"]
    assert counts["agents"] == 100
    assert counts["actions_total"] == S100_EXPECTED_ACTIONS
    assert counts["expected_actions_total"] == S100_EXPECTED_ACTIONS
    assert counts["ledger_ok_records"] == S100_EXPECTED_ACTIONS
    assert counts["failed_agents"] == sorted(
        int(k) for k in S100_FAILURES)
    assert reconciliation["aggregate_sha256"]["equal"] is True

    summary = _load(EVIDENCE / S100_JOB / "partition_summary.json")
    assert summary["spec_sha256"] == spec.content_sha256()
    per_tick = summary["counts"]["per_tick_actions"]
    for tick in spec.ticks:
        expected = sum(
            1 for a in spec.agent_ids
            if tick in spec.expected_ticks_for(a))
        assert per_tick[str(tick)] == expected, (tick, per_tick)


def test_100_agent_bounded_concurrency_from_recorded_windows():
    """Gate G / phase-7 probe pattern: observed concurrent-slot ceiling
    recomputed HERE from the committed in-worker windows equals the
    configured bound and never exceeds it; slots were really held."""
    spec = _spec("scale100.json")
    summary = _load(EVIDENCE / S100_JOB / "partition_summary.json")
    bound = spec.window * spec.batch_size
    assert summary["concurrency_bound"] == bound
    assert summary["driver_max_in_flight"] <= spec.window

    tick = spec.overlap_assert_tick
    stats = summary["overlap_by_tick"][str(tick)]
    windows = summary["overlap_windows_at_assert_tick"]
    assert stats["n_windows"] == len(windows) == spec.agent_count
    recomputed = max_overlap(windows)
    assert recomputed == stats["max_overlap"]
    assert recomputed <= bound
    assert recomputed == bound
    assert stats["distinct_pids"] >= 2
    delay = spec.delay_ticks[str(tick)]
    for start, stop in windows:
        assert stop - start >= delay * 0.9
    serial_floor = spec.agent_count * delay
    span = max(w[1] for w in windows) - min(w[0] for w in windows)
    assert span < serial_floor * 0.9, (span, serial_floor)


def test_100_agent_sparse_activation_and_failures():
    spec = _spec("scale100.json")
    summary = _load(EVIDENCE / S100_JOB / "partition_summary.json")

    probe = summary["sparse_probe"]
    assert probe["tick"] == spec.probe_tick
    assert probe["unchanged"] is True
    assert probe["mismatched_ids"] == []
    activated = spec.activated_ids(spec.probe_tick)
    assert 0 < len(activated) < spec.agent_count
    assert probe["inactive_count"] == spec.agent_count - len(activated)

    assert summary["failed_agents"].keys() == S100_FAILURES.keys()
    for agent_id, fail_tick in S100_FAILURES.items():
        assert summary["failed_agents"][agent_id]["tick"] == fail_tick
        artifact = _load(
            EVIDENCE / S100_JOB / f"unit_error_{agent_id}.json")
        assert artifact["agent_id"] == int(agent_id)
        assert artifact["tick"] == fail_tick
        assert "SCALE_INJECTED_UNIT_FAILURE_" in artifact["error"]


def test_1000_agent_partitions_reconciled_and_resumed():
    """Gate G: 1,000 scripted/shallow agents as four isolated partitions,
    each interrupted at the declared checkpoint boundary and resumed by a
    SEPARATE monitored job from the persisted workspaces."""
    for pid in PARTITIONS:
        spec = _spec(f"scale1000_{pid}.json")
        assert spec.agent_count == 250
        assert spec.expected_total_actions() == P_EXPECTED_ACTIONS[pid]

        seg_a_job = SEG_JOBS[(pid, "A")]
        seg_b_job = SEG_JOBS[(pid, "B")]
        boundary = spec.segments["A"][1]
        checkpoint_after_a = _load(
            EVIDENCE / seg_a_job / "driver_checkpoint_after_segA.json")
        assert checkpoint_after_a["next_tick"] == boundary + 1
        assert checkpoint_after_a["spec_sha256"] == spec.content_sha256()
        seg_a_failures = {
            a: t for a, t in spec.fail_at.items() if t <= boundary}
        assert {int(k): v["tick"] for k, v in
                checkpoint_after_a["failed_agents"].items()} \
            == seg_a_failures

        reconciliation = _load(
            EVIDENCE / seg_b_job / "reconciliation.json")
        assert reconciliation["ok"] is True
        assert reconciliation["violations"] == []
        counts = reconciliation["counts"]
        assert counts["agents"] == 250
        assert counts["actions_total"] == P_EXPECTED_ACTIONS[pid]
        assert counts["failed_agents"] == sorted(spec.fail_at)
        assert reconciliation["aggregate_sha256"]["equal"] is True
        assert reconciliation["driver_max_in_flight"] <= spec.window

        summary = _load(EVIDENCE / seg_b_job / "partition_summary.json")
        assert summary["spec_sha256"] == spec.content_sha256()
        probe = summary["sparse_probe"]
        assert probe["unchanged"] is True

        for agent_id, fail_tick in spec.fail_at.items():
            assert summary["failed_agents"][str(agent_id)]["tick"] \
                == fail_tick
            artifact = _load(
                EVIDENCE / seg_b_job / f"unit_error_{agent_id}.json")
            assert artifact["agent_id"] == agent_id
            assert artifact["tick"] == fail_tick


def test_1000_agent_aggregate_equals_recorded_actions():
    """Gate G: the collected aggregate equals the union of per-partition
    recorded actions byte-exactly, and the rollup hashes recompute from
    the committed per-agent hash lists."""
    aggregate = _load(EVIDENCE / AGG_JOB / "aggregate_summary.json")
    agg_rec = _load(EVIDENCE / AGG_JOB / "aggregate_reconciliation.json")
    assert agg_rec["ok"] is True
    assert agg_rec["violations"] == []

    totals = aggregate["totals"]
    assert totals["partitions"] == 4
    assert totals["agents"] == 1000
    assert totals["actions_total"] == TOTAL_EXPECTED_ACTIONS
    assert totals["expected_actions_total"] == TOTAL_EXPECTED_ACTIONS
    assert totals["failed_agents_total"] == 3

    hashes = aggregate["aggregate_sha256"]
    assert hashes["equal"] is True
    assert hashes["action_ids_collected_from_ledgers"] \
        == hashes["action_ids_recomputed_from_workspaces"]

    # Recompute the per-agent rollups from the committed summaries.
    rollup_lines = {}
    for pid in PARTITIONS:
        spec = _spec(f"scale1000_{pid}.json")
        summary = _load(
            EVIDENCE / SEG_JOBS[(pid, "B")] / "partition_summary.json")
        entry = aggregate["partitions"][pid]
        assert entry["agents"] == spec.agent_count
        assert entry["actions_total"] == P_EXPECTED_ACTIONS[pid]
        assert entry["action_ids_sha256"] \
            == summary["aggregate_sha256"]["action_ids_from_files"]
        agent_hash_lines = sorted(
            f"{e['agent_id']}:{e['actions_file_sha256']}"
            for e in summary["per_agent"]
            if e["actions_file_sha256"] is not None)
        rollup_lines[pid] = sha256_text("\n".join(agent_hash_lines))
        assert entry["per_agent_rollup_sha256"] == rollup_lines[pid]
    overall = sha256_text("\n".join(
        f"{pid}:{rollup_lines[pid]}" for pid in sorted(rollup_lines)))
    assert hashes["per_agent_rollup_overall"] == overall

    isolation = aggregate["isolation"]
    assert isolation["mode"] == "isolated_partitions_by_design"
    assert isolation["cross_partition_channels"] == []
    assert isolation["agent_ids_disjoint"] is True
    assert isolation["action_ids_unique"] is True
    assert len(set(isolation["workspace_roots"].values())) == 4


def test_evidence_hashes_manifest_is_complete_and_exact():
    manifest = _load(EVIDENCE / "hashes_manifest.json")
    assert INFRA_ONLY_STATEMENT.split(":")[0] in manifest["statement"]
    files = manifest["files"]
    assert files, "empty hashes manifest"
    for rel, expected in files.items():
        path = EVIDENCE / rel
        assert path.exists(), f"manifest names missing file {rel}"
        assert sha256_file(path) == expected, f"hash drift in {rel}"
    on_disk = sorted(
        str(p.relative_to(EVIDENCE)) for p in EVIDENCE.rglob("*")
        if p.is_file() and p.name != "hashes_manifest.json")
    assert on_disk == sorted(files), (
        "evidence files on disk not covered by the manifest")


def test_infrastructure_only_labeling_everywhere():
    """Gate G labeling clause: every evidence artifact and the evidence
    document carry the explicit infrastructure-only statement."""
    _require(EVIDENCE / "hashes_manifest.json")
    for path in sorted(EVIDENCE.rglob("*.json")):
        if path.name == "job.json":
            continue  # runner-owned record; the run itself is labeled
        text = path.read_text(encoding="utf-8")
        assert "INFRASTRUCTURE TEST ONLY" in text \
            or "infrastructure test only" in text, path
    for path in sorted(EVIDENCE.rglob("progress.jsonl")):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert "INFRASTRUCTURE TEST ONLY" in first, path

    doc = _require(REPO_ROOT / "docs" / "engine_migration"
                   / "PHASE11_SCALE_EVIDENCE.md")
    text = doc.read_text(encoding="utf-8")
    assert "INFRASTRUCTURE TEST ONLY" in text
    assert "infrastructure rather than calibrated societal simulation" \
        in text
    assert "no population realism claim" in text
