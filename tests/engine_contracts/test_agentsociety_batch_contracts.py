"""AgentSociety 2 batch execution contracts over real (local) Ray.

Pinned upstream: agentsociety2 @ 6e9fc2e79f89f65a3e3d0d7899e380f7394099be.
Route: audit AGENTSOCIETY_AUDIT.md §A Option 2 — the direct public primitives
``init_dispatchers()`` -> ``build_service_proxy(...)`` ->
``create_agents_batch.remote`` -> ``step_agent_batch.remote``, which return
per-agent {ok|error} + token_stats to the driver (exactly the records
``AgentSociety.step`` discards, society.py:621-628).

Custom-agent registration route (least invasive; documented in conftest):
the probe agent file lives under ``<WORKSPACE_PATH>/custom/agents/`` and Ray
workers resolve it through the registry's WORKSPACE_PATH scan
(agent/runner.py:67-94; registry/base.py:170-196; env passthrough
config/llm_dispatcher.py:551-567). A driver-side monkeypatch registration
would not cross the Ray process boundary, so it is not used.

Verified sources:
  - step_agent_batch returns {"results": [{"id","ok","summary"|"error"}...],
    "token_stats": ...} with per-agent try/except isolation:
    agentsociety2/agent/runner.py:109-140, 267-311
  - create_agents_batch writes workspaces without driver-side instances:
    agentsociety2/agent/runner.py:143-152, 314-336
  - failed agent's to_workspace is skipped (workspace stays at previous
    step's state): agentsociety2/agent/runner.py:119-131
  - trace requires injecting a proxy built with trace enabled:
    agentsociety2/agent/service_proxy.py:171-252 (the society's own proxy
    sets trace=False, society.py:341-355)

Offline: dummy creds from conftest; ServiceProxy env=None (accepted by the
factory signature — env is an untyped handle slot; the probe agent never
calls ask_env, and AgentBase.restore skips skill discovery when env is None,
agent.py:408-416). Skips with the exact error if Ray cannot start.
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

T0 = datetime(2026, 1, 2, 9, 0, 0)


def _read_trace_records(trace_dir):
    records = []
    for shard in sorted(trace_dir.glob("trace_*.jsonl")):
        for line in shard.read_text(encoding="utf-8").splitlines():
            records.append(json.loads(line))
    return records


def _items(specs):
    return [
        {
            "id": agent_id,
            "profile": {"id": agent_id, "name": f"probe-{agent_id}"},
            "config": dict(config),
        }
        for agent_id, config in specs
    ]


def test_driver_registry_resolves_custom_agent_via_scanner(ray_engine):
    """Sanity precondition with a readable failure mode: the custom/ scanner
    route registers the probe agent under its class name."""
    from agentsociety2.registry import get_agent_module_class

    cls = get_agent_module_class(ray_engine["agent_class_name"])
    assert cls is not None, (
        "custom/agents scanner did not register ContractProbeAgent under "
        f"WORKSPACE_PATH={ray_engine['workspace_root']}"
    )
    assert cls.__name__ == "ContractProbeAgent"
    assert getattr(cls, "_is_custom", False) is True


def test_batch_create_step_token_stats_and_trace(ray_engine, tmp_path):
    import ray
    from agentsociety2.agent import runner
    from agentsociety2.agent.service_proxy import build_service_proxy

    run_dir = tmp_path / "run"
    agents_root = run_dir / "agents"
    agents_root.mkdir(parents=True)

    proxy = build_service_proxy(
        None, run_dir=run_dir, trace=True, replay=False
    )
    assert proxy.trace is not None and proxy.trace.trace_dir  # injected trace

    created = ray.get(
        runner.create_agents_batch.remote(
            _items([(1, {"behavior": "ok"}), (2, {"behavior": "ok"})]),
            str(agents_root),
            ray_engine["agent_class_name"],
        )
    )
    assert created == 2
    for agent_id in (1, 2):
        ws = agents_root / f"agent_{agent_id:04d}"
        assert (ws / "AGENT.json").is_file() and (ws / "config.json").is_file()

    out = ray.get(
        runner.step_agent_batch.remote(
            [1, 2],
            str(agents_root),
            ray_engine["agent_class_name"],
            60,
            T0,
            proxy,
        )
    )

    # (a) both agents stepped ok, with summaries, order preserved.
    assert set(out.keys()) == {"results", "token_stats"}
    by_id = {r["id"]: r for r in out["results"]}
    assert set(by_id) == {1, 2}
    for agent_id in (1, 2):
        assert by_id[agent_id]["ok"] is True, by_id[agent_id]
        assert by_id[agent_id]["summary"] == f"stepped:{agent_id}:1"

    # (c) token accounting key is present (empty here — no LLM calls).
    assert isinstance(out["token_stats"], dict)

    # Workspace evidence written inside the worker survives on shared disk.
    for agent_id in (1, 2):
        ws = agents_root / f"agent_{agent_id:04d}"
        step_file = ws / "state" / "step_0001.json"
        assert step_file.is_file()
        payload = json.loads(step_file.read_text(encoding="utf-8"))
        assert payload["id"] == agent_id
        assert payload["t"] == T0.isoformat()
        meta = json.loads((ws / "AGENT.json").read_text(encoding="utf-8"))
        assert meta["step_count"] == 1
        assert meta["current_time"] == T0.isoformat()

    # (d) injected TraceProxy produced spans from inside the Ray workers.
    records = _read_trace_records(run_dir / "trace")
    step_spans = [r for r in records if r.get("name") == "contract.step"]
    assert step_spans, f"no contract.step spans under {run_dir / 'trace'}"
    assert {r["resource"]["agent.id"] for r in step_spans} == {1, 2}
    assert all(r["status"]["code"] == "ok" for r in step_spans)


def test_failing_agent_is_isolated_and_reported_to_driver(ray_engine, tmp_path):
    import ray
    from agentsociety2.agent import runner
    from agentsociety2.agent.service_proxy import build_service_proxy

    run_dir = tmp_path / "run"
    agents_root = run_dir / "agents"
    agents_root.mkdir(parents=True)
    proxy = build_service_proxy(None, run_dir=run_dir, trace=True, replay=False)

    ray.get(
        runner.create_agents_batch.remote(
            _items([(3, {"behavior": "ok"}), (4, {"behavior": "fail"})]),
            str(agents_root),
            ray_engine["agent_class_name"],
        )
    )
    out = ray.get(
        runner.step_agent_batch.remote(
            [3, 4],
            str(agents_root),
            ray_engine["agent_class_name"],
            60,
            T0,
            proxy,
        )
    )

    by_id = {r["id"]: r for r in out["results"]}
    # (b) failure isolation, driver-visible via Option 2 primitives:
    assert by_id[3]["ok"] is True
    assert by_id[3]["summary"] == "stepped:3:1"
    assert by_id[4]["ok"] is False
    assert "CONTRACT_PROBE_FAILURE agent 4" in by_id[4]["error"]
    assert "token_stats" in out

    # The failed agent's to_workspace was skipped: its workspace remains at
    # the pre-step state (runner.py:119-131) — no step evidence, step_count 0.
    ws_ok = agents_root / "agent_0003"
    ws_bad = agents_root / "agent_0004"
    assert (ws_ok / "state" / "step_0001.json").is_file()
    assert not (ws_bad / "state" / "step_0001.json").exists()
    bad_meta = json.loads((ws_bad / "AGENT.json").read_text(encoding="utf-8"))
    assert bad_meta["step_count"] == 0

    # A later batch over the same ids shows the same isolation repeatedly
    # (the bad agent fails every tick, silently from the society's viewpoint;
    # visible here only because Option 2 returns the records).
    out2 = ray.get(
        runner.step_agent_batch.remote(
            [3, 4],
            str(agents_root),
            ray_engine["agent_class_name"],
            60,
            datetime(2026, 1, 2, 10, 0, 0),
            proxy,
        )
    )
    by_id2 = {r["id"]: r for r in out2["results"]}
    assert by_id2[3]["ok"] is True and by_id2[3]["summary"] == "stepped:3:2"
    assert by_id2[4]["ok"] is False


def test_service_proxy_with_trace_survives_ray_pickling(ray_engine, tmp_path):
    """The exact proxy object handed to the tasks round-trips Ray's
    serialization (dataclass of handles only, service_proxy.py:101-135)."""
    import ray
    from agentsociety2.agent.service_proxy import build_service_proxy

    proxy = build_service_proxy(None, run_dir=tmp_path, trace=True, replay=False)
    restored = ray.get(ray.put(proxy))
    assert restored.env is None
    assert restored.trace is not None
    assert restored.trace.trace_dir == proxy.trace.trace_dir
    assert restored.llm.default is not None
    assert restored.take_token_stats() == {}
