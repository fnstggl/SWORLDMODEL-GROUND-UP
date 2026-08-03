"""Bounded concurrency, exactly-once id accounting, token stats, traces.

Directive Stage A gates: multiple branches run concurrently, concurrency
limits are respected, traces / token use / runtime are recorded.  Method
(Phase 2 lesson reused): a throwaway warm-up run first spins up the Ray
worker pool -- cold worker starts serialize and would measure startup
lag, not scheduling -- then the timed run's overlap is computed from
IN-WORKER step timestamps persisted by each branch agent, so the
assertions are about actual execution windows, not scheduler
bookkeeping.  The submit-window bound is enforced by the executor in
code (at most ``parallelism`` single-branch tasks in flight), never by
trusting the Ray CPU budget alone.
"""

from __future__ import annotations

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
                                 make_candidate, model_spec,
                                 read_trace_records, scripted_params)
from sworldmodel.backends.agentsociety.branch_executor import \
    run_candidates_distributed

#: blocking sleep per ACTOR-model call; each branch makes two actor-model
#: calls (one full turn per actor at MAX_STEPS=2), so every branch holds
#: its slot for >= 2 * DELAY_S of scripted work
DELAY_S = 0.75
BRANCH_WORK_S = 2 * DELAY_S
PARALLELISM = 2
BRANCH_COUNT = 4


def _synthetic_candidates():
    candidates = []
    for index in range(1, BRANCH_COUNT + 1):
        candidates.append(make_candidate(
            f"probe_option_{index}",
            f"Send message variant number {index} carrying the "
            f"distinctive token vt{index}x."))
    return candidates


def test_parallelism_window_accounting_tokens_and_traces(
        distributed_engine, tmp_path):
    fx = load_fixture_one()
    candidates = _synthetic_candidates()
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    response = "Takes note of the message and continues the scheduled work."

    # Warm-up round: spin up the worker pool (throwaway timings).  It
    # MUST carry the same blocking delay as the timed round: zero-delay
    # warm branches are all absorbed by the single already-import-warm
    # worker before the scheduler dispatches to a prestarted cold one, so
    # the second worker would pay its first-task import cost INSIDE the
    # timed round and serialize it (measured here; the Phase 2 suite
    # learned the same lesson with sleeping probe agents).
    warm = run_candidates_distributed(
        fx.world, candidates,
        model_spec=model_spec(scripted_params(
            fx, candidates, recipient_response=response,
            delay_s=DELAY_S)),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx.evaluator_spec, registry=fx.registry,
        run_dir=tmp_path / "warm", parallelism=PARALLELISM)
    for result in warm.results:
        assert result.infrastructure_errors == ()

    # Timed round: same branches, blocking per-call delay.
    timed = run_candidates_distributed(
        fx.world, candidates,
        model_spec=model_spec(scripted_params(
            fx, candidates, recipient_response=response,
            delay_s=DELAY_S)),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx.evaluator_spec, registry=fx.registry,
        run_dir=tmp_path / "timed", parallelism=PARALLELISM)
    for result in timed.results:
        assert result.infrastructure_errors == ()
    report = timed.execution_report

    # Observed concurrency: never above the limit, and exactly at the
    # limit in the warmed steady state (parallelism actually happened).
    assert report["parallelism_limit"] == PARALLELISM
    assert report["driver_max_in_flight"] <= PARALLELISM
    assert report["measured_windows"] == BRANCH_COUNT
    per_branch = report["per_branch"]
    windows = [(per_branch[cid]["worker_started_unix"],
                per_branch[cid]["worker_stopped_unix"])
               for cid in candidate_ids]
    assert report["worker_max_overlap"] <= PARALLELISM, (report, windows)
    assert report["worker_max_overlap"] == PARALLELISM, (report, windows)

    # Arithmetic bounds from in-worker clocks: every branch really held
    # its slot for the scripted work, four branches over two slots cannot
    # beat 2 * BRANCH_WORK_S of wall span, and full serialization would
    # need ~4 * BRANCH_WORK_S (so the span must stay clearly below it).
    for cid in candidate_ids:
        entry = per_branch[cid]
        assert entry["worker_stopped_unix"] - entry["worker_started_unix"] \
            >= BRANCH_WORK_S * 0.9, entry
    span = max(stop for _start, stop in windows) \
        - min(start for start, _stop in windows)
    assert span >= 2 * BRANCH_WORK_S * 0.85, (span, sorted(windows))
    assert span < 4 * BRANCH_WORK_S * 0.95, (
        "serialized execution", span, sorted(windows))

    # Worker identity recorded; 4 branches over 2 slots need >= 2 workers.
    pids = {per_branch[cid]["worker_pid"] for cid in candidate_ids}
    assert all(isinstance(pid, int) and pid > 0 for pid in pids)
    assert 2 <= len(pids) <= BRANCH_COUNT, pids

    # Exactly-once id accounting, end to end.
    assert report["exactly_once"] is True
    assert report["expected_candidate_ids"] == candidate_ids
    assert report["submitted_candidate_ids"] == candidate_ids
    assert sorted(report["harvested_candidate_ids"]) \
        == sorted(candidate_ids)
    assert report["collected_candidate_ids"] == candidate_ids

    # Token stats present with the audited shape: scripted models make
    # zero LLM calls, so every drained per-branch delta map is exactly
    # empty -- present, typed, and honest.
    for result in timed.results:
        assert result.token_stats == {}
    assert report["token_stats_total"] == {}

    # Trace shard files exist, are non-empty, and carry one ok-status
    # branch.execute span per branch, emitted from inside the workers.
    trace_dir = Path(report["trace_dir"])
    shards = sorted(trace_dir.glob("trace_*.jsonl"))
    assert shards and any(shard.stat().st_size > 0 for shard in shards)
    spans = [record for record in read_trace_records(trace_dir)
             if record.get("name") == "branch.execute"]
    assert {span["resource"]["agent.id"] for span in spans} \
        == {1, 2, 3, 4}
    assert {span["attributes"]["branch.candidate_id"] for span in spans} \
        == set(candidate_ids)
    assert all(span["status"]["code"] == "ok" for span in spans)
