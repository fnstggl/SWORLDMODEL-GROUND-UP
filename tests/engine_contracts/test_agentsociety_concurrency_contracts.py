"""AgentSociety 2 bounded-concurrency contract over real (local) Ray.

Pinned upstream: agentsociety2 @ 6e9fc2e79f89f65a3e3d0d7899e380f7394099be.
Contract (audit AGENTSOCIETY_AUDIT.md §11): the Ray CPU budget
``ray.init(num_cpus=Config.LLM_RAY_MAX_WORKERS)`` caps concurrent
``step_agent_batch`` tasks (each task takes 1 CPU by Ray default), so with
AGENTSOCIETY_LLM_RAY_MAX_WORKERS=2 (set by conftest before import;
config.py:304, llm_dispatcher.py:589-596) and batch_size=1, at most two
minutes-long jobs run at once. This is the Phase 7 branch-parallelism knob:
``batch_size=1`` + LLM_RAY_MAX_WORKERS = desired parallelism.

Method: 4 single-agent batches whose step() BLOCK-sleeps ~1.2s and records
wall-clock (start, stop) into their own workspaces. Overlap is computed from
those in-step timestamps, so the assertion is about actual step execution
windows, not scheduler bookkeeping. Strict contract: overlap <= 2. The
lower bound wall-span >= 2 * sleep is arithmetic (4 sleeps over <= 2 slots),
not a scheduling race.

Skips (from the shared fixture) with the exact error if Ray cannot start.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine contracts require Python >= 3.12 (engine env); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("agentsociety2", exc_type=ImportError)
pytest.importorskip("ray", exc_type=ImportError)

SLEEP_S = 1.2
AGENT_IDS = (21, 22, 23, 24)
T0 = datetime(2026, 1, 3, 9, 0, 0)


def _max_overlap(windows: list[tuple[float, float]]) -> int:
    """Max number of simultaneously open (start, stop) windows.

    Ties are processed stop-before-start, so back-to-back handoffs at the
    same timestamp do not count as overlap (scheduling-slack tolerance).
    """
    events: list[tuple[float, int]] = []
    for start, stop in windows:
        events.append((start, +1))
        events.append((stop, -1))
    events.sort(key=lambda e: (e[0], e[1]))  # -1 sorts before +1 at ties
    current = peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def test_num_cpus_bounds_concurrent_single_agent_batches(ray_engine, tmp_path):
    import ray

    assert ray.cluster_resources().get("CPU") == float(ray_engine["num_cpus"])

    from agentsociety2.agent import runner
    from agentsociety2.agent.service_proxy import build_service_proxy
    from agentsociety2.config.config import Config

    # The knob under test really came from the env var conftest installed.
    assert Config.LLM_RAY_MAX_WORKERS == ray_engine["num_cpus"] == 2

    run_dir = tmp_path / "run"
    agents_root = run_dir / "agents"
    agents_root.mkdir(parents=True)
    proxy = build_service_proxy(None, run_dir=run_dir, trace=False, replay=False)

    items = [
        {
            "id": agent_id,
            "profile": {"id": agent_id, "name": f"probe-{agent_id}"},
            "config": {"behavior": "ok", "sleep_s": SLEEP_S},
        }
        for agent_id in AGENT_IDS
    ]
    assert ray.get(
        runner.create_agents_batch.remote(
            items, str(agents_root), ray_engine["agent_class_name"]
        )
    ) == len(AGENT_IDS)

    # Warm-up round: Ray worker processes cold-start serially (measured: a
    # 6s gap serialized an unwarmed round), which is startup lag, not the
    # scheduling contract. One throwaway round spins up the worker pool so
    # the timed round below measures steady-state scheduling.
    ray.get([
        runner.step_agent_batch.remote(
            [agent_id], str(agents_root), ray_engine["agent_class_name"], 59, T0, proxy,
        )
        for agent_id in AGENT_IDS
    ])

    # 4 batches of ONE agent each, submitted together (timed round).
    refs = [
        runner.step_agent_batch.remote(
            [agent_id],
            str(agents_root),
            ray_engine["agent_class_name"],
            60,
            T0,
            proxy,
        )
        for agent_id in AGENT_IDS
    ]
    outs = ray.get(refs)

    for agent_id, out in zip(AGENT_IDS, outs):
        (result,) = out["results"]
        assert result["id"] == agent_id
        assert result["ok"] is True, result

    windows: list[tuple[float, float]] = []
    pids = set()
    for agent_id in AGENT_IDS:
        payload = json.loads(
            (
                agents_root / f"agent_{agent_id:04d}" / "state" / "step_0002.json"
            ).read_text(encoding="utf-8")
        )
        assert payload["stop"] - payload["start"] >= SLEEP_S * 0.9
        windows.append((payload["start"], payload["stop"]))
        pids.add(payload["pid"])

    observed_overlap = _max_overlap(windows)
    # THE bounded-concurrency contract: never more than num_cpus=2 in flight.
    assert observed_overlap <= 2, (observed_overlap, sorted(windows))

    # Arithmetic lower bound: 4 sleeps of SLEEP_S over <= 2 slots cannot fit
    # in less than 2 * SLEEP_S of wall time (measured from in-step clocks).
    span = max(stop for _, stop in windows) - min(start for start, _ in windows)
    assert span >= 2 * SLEEP_S * 0.95, (span, sorted(windows))

    # Parallelism actually happened (reviewer finding: the upper bound alone
    # would pass a dispatcher that serializes everything). With 4 x SLEEP_S of
    # in-step work, two slots must overlap at some point AND the wall span
    # must be strictly less than fully-serial execution.
    assert observed_overlap == 2, (observed_overlap, sorted(windows))
    assert span < 4 * SLEEP_S * 0.95, ("serialized execution", span, sorted(windows))
