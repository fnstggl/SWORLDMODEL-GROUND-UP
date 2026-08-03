"""Fast tier: the SAME harness code paths as the monitored scale jobs,
at small N, through the REAL AgentSociety worker/dispatcher primitives.

INFRASTRUCTURE TEST ONLY: scripted/shallow scale exercise of the
AgentSociety execution substrate -- infrastructure rather than calibrated
societal simulation; no population realism claim.

One module-scoped mini-scenario run (two isolated partitions, sparse
modular schedule, a warm-up-then-timed concurrency probe with held
slots, one injected mid-run failure, a driver-checkpoint interrupt +
resume, full reconciliation, and cross-partition aggregation) feeds every
clause test below, so the fast tier stays well under a minute while
still executing create_agents_batch / step_agent_batch / the submit
window / the ledger / the reconciliation exactly as the 100- and
1000-agent monitored jobs do.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "scale fast tier requires Python >= 3.12 (engine env); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("agentsociety2", exc_type=ImportError)
pytest.importorskip("ray", exc_type=ImportError)

from scale_harness import (ACTIONS_FILE, DRIVER_DIRNAME, ERROR_FILE,
                           FAILURE_MARKER_PREFIX, INFRA_ONLY_STATEMENT,
                           LEDGER_FILE, CHECKPOINT_FILE, PartitionSpec,
                           RECONCILIATION_FILE, SUMMARY_FILE, STATE_FILE,
                           ScaleReconciliationError, aggregate_partitions,
                           genesis_chain, max_overlap, next_chain,
                           read_jsonl, reconcile_partition, run_partition,
                           unit_dir)

#: concurrency probe geometry: bound = window * batch = 4 concurrently
#: held slots; tick 1 is the warm-up (SAME blocking delay -- a zero-cost
#: warm-up is absorbed by one worker and the timed tick then measures a
#: cold-start serialization, the recorded Phase 2/7 lesson), tick 2 is
#: the timed tick the reconciliation asserts on.
FA_DELAY_S = 0.4

FA_SPEC = PartitionSpec(
    partition_id="fa",
    first_agent_id=101,
    agent_count=10,
    ticks_from=1,
    ticks_to=6,
    stride=3,
    batch_size=2,
    window=2,
    full_ticks=(1, 2),
    delay_ticks={"1": FA_DELAY_S, "2": FA_DELAY_S},
    fail_at={105: 3},
    probe_tick=4,
    overlap_assert_tick=2,
    segments={"A": (1, 4), "B": (5, 6)},
)

FB_SPEC = PartitionSpec(
    partition_id="fb",
    first_agent_id=201,
    agent_count=8,
    ticks_from=1,
    ticks_to=6,
    stride=3,
    batch_size=3,
    window=2,
    full_ticks=(1,),
    delay_ticks={},
    fail_at={},
    probe_tick=None,
    overlap_assert_tick=None,
    segments={},
)

#: schedule-derived expectations, asserted EXACTLY below
FA_EXPECTED_ACTIONS = 31
FB_EXPECTED_ACTIONS = 22


@pytest.fixture(scope="module")
def fast_run(scale_engine, tmp_path_factory):
    """Execute the whole mini-scenario once; every test asserts on it."""
    base = tmp_path_factory.mktemp("scale_fast_run")
    fa_root = base / "fa"
    fb_root = base / "fb"
    progress = base / "progress.jsonl"

    # Partition fa, segment A (create + ticks 1..4: warm-up, timed probe,
    # injected failure at tick 3, sparse probe at tick 4)...
    stats_a = run_partition(
        FA_SPEC, registry_root=scale_engine["registry_root"],
        partition_root=fa_root, tick_from=1, tick_to=4,
        progress_path=progress)
    # ...then a DELIBERATE stop at the checkpoint boundary and a resume
    # from the persisted workspaces + driver checkpoint (ticks 5..6),
    # which also runs the full reconciliation at the final tick.
    stats_b = run_partition(
        FA_SPEC, registry_root=scale_engine["registry_root"],
        partition_root=fa_root, tick_from=5, tick_to=6, resume=True,
        progress_path=progress)

    # Independent partition fb in one uninterrupted run.
    stats_fb = run_partition(
        FB_SPEC, registry_root=scale_engine["registry_root"],
        partition_root=fb_root, progress_path=progress)

    aggregate = aggregate_partitions(
        [(FA_SPEC, fa_root), (FB_SPEC, fb_root)], base / "aggregate",
        progress_path=progress)

    return {
        "base": base,
        "fa_root": fa_root,
        "fb_root": fb_root,
        "aggregate_dir": base / "aggregate",
        "aggregate": aggregate,
        "stats_a": stats_a,
        "stats_b": stats_b,
        "stats_fb": stats_fb,
        "progress": progress,
    }


def _driver(root) -> Path:
    return Path(root) / DRIVER_DIRNAME


def _summary(root) -> dict:
    return json.loads((_driver(root) / SUMMARY_FILE)
                      .read_text(encoding="utf-8"))


def _reconciliation(root) -> dict:
    return json.loads((_driver(root) / RECONCILIATION_FILE)
                      .read_text(encoding="utf-8"))


def test_persistent_workspaces_and_exact_counts(fast_run):
    """Workspace files are the authoritative, tamper-evident record:
    hash chains recompute from genesis, AGENT.json step_count matches,
    and totals equal the declared schedule exactly."""
    for spec, root, expected in (
            (FA_SPEC, fast_run["fa_root"], FA_EXPECTED_ACTIONS),
            (FB_SPEC, fast_run["fb_root"], FB_EXPECTED_ACTIONS)):
        reconciliation = _reconciliation(root)
        assert reconciliation["ok"] is True
        assert reconciliation["violations"] == []
        assert reconciliation["counts"]["actions_total"] == expected
        assert reconciliation["counts"]["expected_actions_total"] \
            == expected
        assert spec.expected_total_actions() == expected

        units_root = Path(root) / "units"
        for agent_id in spec.agent_ids:
            state_dir = unit_dir(units_root, agent_id) / "state"
            actions = read_jsonl(state_dir / ACTIONS_FILE)
            chain = genesis_chain(spec.partition_id, agent_id)
            for action in actions:
                chain = next_chain(chain, action["action_id"],
                                   action["tick"])
                assert action["chain"] == chain
            meta = json.loads(
                (unit_dir(units_root, agent_id) / "AGENT.json")
                .read_text(encoding="utf-8"))
            assert meta["step_count"] == len(actions)
            if actions:
                state = json.loads(
                    (state_dir / STATE_FILE).read_text(encoding="utf-8"))
                assert state["seq"] == len(actions)
                assert state["chain"] == chain


def test_bounded_concurrency_probe(fast_run):
    """Configured bound = window x batch; the timed tick's observed
    overlap (recomputed here from the committed in-worker windows) hits
    the bound exactly, never exceeds it, spans clearly below the serial
    floor, and every window really held its slot."""
    summary = _summary(fast_run["fa_root"])
    bound = FA_SPEC.window * FA_SPEC.batch_size
    assert summary["concurrency_bound"] == bound == 4
    assert summary["driver_max_in_flight"] <= FA_SPEC.window

    stats = summary["overlap_by_tick"][str(FA_SPEC.overlap_assert_tick)]
    assert stats["n_windows"] == FA_SPEC.agent_count
    assert stats["max_overlap"] <= bound
    assert stats["max_overlap"] == bound
    assert stats["distinct_pids"] >= 2

    windows = summary["overlap_windows_at_assert_tick"]
    assert len(windows) == FA_SPEC.agent_count
    recomputed = max_overlap(windows)
    assert recomputed == stats["max_overlap"] == bound
    for start, stop in windows:
        assert stop - start >= FA_DELAY_S * 0.9
    serial_floor = FA_SPEC.agent_count * FA_DELAY_S
    span = max(w[1] for w in windows) - min(w[0] for w in windows)
    assert span < serial_floor * 0.9, (span, serial_floor)


def test_sparse_activation_is_inspectable_and_inactive_do_no_work(fast_run):
    """The per-tick activation lists are recorded in the ledger, match
    the declared schedule, actions exist EXACTLY at the scheduled ticks,
    and the probe proves non-activated workspaces did not change."""
    ledger = read_jsonl(_driver(fast_run["fa_root"]) / LEDGER_FILE)
    plans = {r["tick"]: r for r in ledger if r["event"] == "tick_plan"}
    assert sorted(plans) == list(FA_SPEC.ticks)

    # Declared schedule == recorded activation lists (failure-adjusted).
    for tick in FA_SPEC.ticks:
        scheduled = FA_SPEC.activated_ids(tick)
        expected_excluded = [a for a in scheduled
                             if a in FA_SPEC.fail_at
                             and FA_SPEC.fail_at[a] < tick]
        assert sorted(plans[tick]["activated"]) == sorted(
            a for a in scheduled if a not in expected_excluded)
        assert sorted(plans[tick]["excluded_failed"]) \
            == sorted(expected_excluded)

    # Sparse ticks really are sparse: a declared strict subset acts.
    sparse_tick = 4
    assert plans[sparse_tick]["activated"] \
        == [a for a in FA_SPEC.agent_ids if (a + sparse_tick) % 3 == 0]
    assert 0 < len(plans[sparse_tick]["activated"]) < FA_SPEC.agent_count

    # Probe: every non-activated workspace hashed identical across the
    # probe tick.
    probes = [r for r in ledger if r["event"] == "sparse_probe_result"]
    assert len(probes) == 1
    assert probes[0]["tick"] == FA_SPEC.probe_tick
    assert probes[0]["unchanged"] is True
    assert probes[0]["mismatched_ids"] == []
    assert probes[0]["inactive_count"] == FA_SPEC.agent_count - len(
        plans[FA_SPEC.probe_tick]["activated"])

    # File side: per-agent action ticks equal the declared schedule.
    units_root = fast_run["fa_root"] / "units"
    for agent_id in FA_SPEC.agent_ids:
        actions = read_jsonl(
            unit_dir(units_root, agent_id) / "state" / ACTIONS_FILE)
        assert [a["tick"] for a in actions] \
            == FA_SPEC.expected_ticks_for(agent_id)


def test_injected_failure_is_isolated_and_dual_channel(fast_run):
    """The injected agent fails mid-run with a structured artifact; its
    batch mates and every other agent complete unaffected; the driver
    excludes it from later ticks; no survivor action is lost or
    duplicated (the exact reconciliation already passed)."""
    failing = 105
    fail_tick = FA_SPEC.fail_at[failing]
    units_root = fast_run["fa_root"] / "units"

    # Workspace channel: structured error artifact with the marker.
    artifact = json.loads(
        (unit_dir(units_root, failing) / "state" / ERROR_FILE)
        .read_text(encoding="utf-8"))
    assert artifact["agent_id"] == failing
    assert artifact["tick"] == fail_tick
    assert FAILURE_MARKER_PREFIX in artifact["error"]
    assert artifact["worker_execution"]["pid"] > 0

    # Driver channel: exactly one ok=False record, at the failure tick,
    # with the same marker; batch mates in the SAME batch are ok.
    ledger = read_jsonl(_driver(fast_run["fa_root"]) / LEDGER_FILE)
    failure_records = []
    for record in ledger:
        if record["event"] != "batch_result":
            continue
        for result in record["results"]:
            if result["id"] == failing and not result["ok"]:
                failure_records.append((record, result))
    assert len(failure_records) == 1
    record, result = failure_records[0]
    assert record["tick"] == fail_tick
    assert FAILURE_MARKER_PREFIX in result["error"]
    mates = [r for r in record["results"] if r["id"] != failing]
    assert mates and all(m["ok"] for m in mates)

    # The failed agent never acts at or after its failure tick, and the
    # driver excluded it from every later scheduled tick.
    actions = read_jsonl(
        unit_dir(units_root, failing) / "state" / ACTIONS_FILE)
    assert [a["tick"] for a in actions] == [1, 2]
    plans = {r["tick"]: r for r in ledger if r["event"] == "tick_plan"}
    assert failing in plans[6]["excluded_failed"]
    assert failing not in plans[6]["activated"]

    # Survivors: full expected action count (nothing lost to the
    # failure), asserted via the exact totals.
    reconciliation = _reconciliation(fast_run["fa_root"])
    assert reconciliation["counts"]["actions_total"] \
        == FA_EXPECTED_ACTIONS
    assert reconciliation["counts"]["failed_agents"] == [failing]


def test_checkpoint_resume_across_driver_restart(fast_run):
    """Segment A stopped at the checkpoint boundary; segment B resumed
    from the persisted workspaces + driver checkpoint (fresh
    run_partition invocation) and agents carried their hash-chain state
    across the boundary seamlessly."""
    assert fast_run["stats_a"]["ticks_completed"] == [1, 2, 3, 4]
    assert fast_run["stats_b"]["resume"] is True
    assert fast_run["stats_b"]["ticks_completed"] == [5, 6]

    checkpoint = json.loads(
        (_driver(fast_run["fa_root"]) / CHECKPOINT_FILE)
        .read_text(encoding="utf-8"))
    assert checkpoint["next_tick"] == FA_SPEC.ticks_to + 1
    assert checkpoint["spec_sha256"] == FA_SPEC.content_sha256()
    assert sorted(checkpoint["failed_agents"]) == ["105"]

    # An agent acting in BOTH segments: contiguous seq and a chain that
    # recomputes across the boundary (state genuinely came from disk).
    units_root = fast_run["fa_root"] / "units"
    agent_id = 102  # sparse ticks {3, 6}: one action per segment
    actions = read_jsonl(
        unit_dir(units_root, agent_id) / "state" / ACTIONS_FILE)
    assert [a["tick"] for a in actions] == [1, 2, 3, 6]
    assert [a["seq"] for a in actions] == [1, 2, 3, 4]
    chain = genesis_chain(FA_SPEC.partition_id, agent_id)
    for action in actions:
        chain = next_chain(chain, action["action_id"], action["tick"])
    assert actions[-1]["chain"] == chain


def test_reconciliation_catches_lost_and_duplicated_actions(fast_run,
                                                            tmp_path):
    """The exact reconciliation is worth exactly what it refuses: drop
    one recorded action (a LOST action) or append one again (a
    DUPLICATED action) and it must fail, naming the agent."""
    source = fast_run["fb_root"]
    victim = 204

    lost_root = tmp_path / "lost"
    shutil.copytree(source, lost_root)
    actions_path = unit_dir(lost_root / "units", victim) \
        / "state" / ACTIONS_FILE
    lines = actions_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2
    actions_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(ScaleReconciliationError) as excinfo:
        reconcile_partition(FB_SPEC, lost_root)
    assert str(victim) in str(excinfo.value)

    dup_root = tmp_path / "dup"
    shutil.copytree(source, dup_root)
    actions_path = unit_dir(dup_root / "units", victim) \
        / "state" / ACTIONS_FILE
    lines = actions_path.read_text(encoding="utf-8").splitlines()
    actions_path.write_text("\n".join(lines + [lines[-1]]) + "\n",
                            encoding="utf-8")
    with pytest.raises(ScaleReconciliationError) as excinfo:
        reconcile_partition(FB_SPEC, dup_root)
    assert str(victim) in str(excinfo.value)


def test_partitions_isolated_and_aggregate_equals_recorded_actions(
        fast_run):
    """Partitions are isolated by design (disjoint ids, disjoint roots,
    no channel); the aggregate equals the union of per-partition recorded
    actions byte-exactly, recomputed from the raw workspace records; and
    every evidence artifact carries the infrastructure-only statement."""
    aggregate = fast_run["aggregate"]
    assert aggregate["aggregate_sha256"]["equal"] is True
    assert aggregate["aggregate_sha256"][
        "action_ids_collected_from_ledgers"] == aggregate[
        "aggregate_sha256"]["action_ids_recomputed_from_workspaces"]
    assert aggregate["totals"]["actions_total"] \
        == FA_EXPECTED_ACTIONS + FB_EXPECTED_ACTIONS
    assert aggregate["totals"]["agents"] \
        == FA_SPEC.agent_count + FB_SPEC.agent_count
    assert aggregate["totals"]["failed_agents_total"] == 1

    isolation = aggregate["isolation"]
    assert isolation["mode"] == "isolated_partitions_by_design"
    assert isolation["cross_partition_channels"] == []
    assert isolation["agent_ids_disjoint"] is True
    assert isolation["action_ids_unique"] is True
    assert set(FA_SPEC.agent_ids).isdisjoint(FB_SPEC.agent_ids)
    roots = set(isolation["workspace_roots"].values())
    assert len(roots) == 2

    # Labeling clause: the statement rides in EVERY evidence artifact --
    # summaries, reconciliations, manifest, checkpoint, aggregate files,
    # and each unit's write-once config.
    artifacts = [
        _driver(fast_run["fa_root"]) / SUMMARY_FILE,
        _driver(fast_run["fa_root"]) / RECONCILIATION_FILE,
        _driver(fast_run["fa_root"]) / "partition_manifest.json",
        _driver(fast_run["fa_root"]) / CHECKPOINT_FILE,
        _driver(fast_run["fb_root"]) / SUMMARY_FILE,
        fast_run["aggregate_dir"] / "aggregate_summary.json",
        fast_run["aggregate_dir"] / "aggregate_reconciliation.json",
        unit_dir(fast_run["fa_root"] / "units", 101) / "config.json",
    ]
    for path in artifacts:
        text = path.read_text(encoding="utf-8")
        assert INFRA_ONLY_STATEMENT.split(":")[0] in text, path
        assert "no population realism claim" in text, path
