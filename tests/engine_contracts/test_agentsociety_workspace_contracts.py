"""AgentSociety 2 workspace contracts: create / from_workspace / restore
round-trip for a minimal in-test AgentBase subclass. No Ray.

Pinned upstream: agentsociety2 @ 6e9fc2e79f89f65a3e3d0d7899e380f7394099be.
Verified sources:
  - arg-less __init__ + create/from_workspace/restore contract:
    agentsociety2/agent/base/agent.py:145-208, 233-416
  - AGENT.json initial schema written by create():
    agentsociety2/agent/base/agent.py:256-283
  - config.json is static, "write-once, never rewritten":
    agentsociety2/agent/base/agent.py:250-253 (+ PersonAgent pattern
    agent/person.py:180-197 — to_workspace persists only AGENT.json)
  - post-step AGENT.json shape from build_agent_json:
    agentsociety2/agent/base/agent.py:774-812
  - opaque blobs under state/ are inert to the framework
    (restore reads only config.json + AGENT.json): agent.py:323-329;
    audit AGENTSOCIETY_AUDIT.md §B
  - trace binding in restore via ServiceProxy.trace -> local sharded sink:
    agentsociety2/agent/base/agent.py:618-664; trace/sharded_writer.py:163-171

Offline: dummy env credentials installed by conftest before any agentsociety2
import; env router None; LLM clients None (never called).
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine contracts require Python >= 3.12 (engine env); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("agentsociety2", exc_type=ImportError)

from agentsociety2.agent.base.agent import AgentBase
from agentsociety2.agent.service_proxy import LLMClients, ServiceProxy
from agentsociety2.trace import TraceProxy

T0 = datetime(2026, 1, 1, 8, 0, 0)
T1 = datetime(2026, 1, 1, 9, 0, 0)

OPAQUE_BLOB = b"\x00\x01\xffconcordia-checkpoint-placeholder\x00binary\x7f"


class MiniContractAgent(AgentBase):
    """Minimal in-test agent honoring the arg-less __init__ contract.

    Only the three forced abstracts are overridden (to_workspace / ask /
    step); create / from_workspace / restore are the inherited concrete
    implementations under test.
    """

    async def to_workspace(self, workspace_path: Path) -> None:
        workspace_path = Path(workspace_path)
        if self._workspace_root is None:
            self._bind_workspace(workspace_path)
        self.persist_agent_json(tick=None, t=self._current_time)

    async def ask(self, message: str, readonly: bool = True, *,
                  t: datetime | None = None) -> str:
        return f"mini:{self.id}:{message}"

    async def step(self, tick: int, t: datetime) -> str:
        self._step_count += 1
        self._current_time = t
        with self.trace_span(
            "mini.step", attributes={"agent.step_count": self._step_count}
        ):
            pass
        return f"stepped:{self.id}:{self._step_count}"


def _proxy(trace_dir: Path | None = None) -> ServiceProxy:
    """Real ServiceProxy with null handles (agents here never call services)."""
    return ServiceProxy(
        env=None,
        llm=LLMClients(coder=None, default=None, embedding=None),
        trace=TraceProxy(trace_dir=str(trace_dir)) if trace_dir else None,
        replay=None,
        run_dir=None,
    )


def _create(ws: Path, *, agent_id: int = 7,
            config: dict | None = None) -> tuple[dict, dict]:
    profile = {"id": agent_id, "name": f"probe-{agent_id}", "persona": "terse"}
    config = config if config is not None else {"max_react_turns": 1,
                                                "custom_knob": "K1"}
    MiniContractAgent.create(ws, profile, config)
    return profile, config


def test_create_writes_initial_agent_json_schema_and_dirs(tmp_path):
    ws = tmp_path / "agent_0007"
    profile, config = _create(ws)

    assert (ws / "config.json").is_file()
    assert (ws / "AGENT.json").is_file()
    assert (ws / "state").is_dir()
    assert (ws / "memory").is_dir()

    meta = json.loads((ws / "AGENT.json").read_text(encoding="utf-8"))
    # Exact initial schema written by AgentBase.create (agent.py:256-283).
    assert set(meta.keys()) == {
        "schema_version", "agent_class", "agent_id", "id", "name", "profile",
        "step_count", "current_time", "tick", "visible_skills",
        "activated_skills", "disabled_skills", "default_activated_skills",
        "initialized_at",
    }
    assert meta["schema_version"] == 1
    assert meta["agent_class"] == "MiniContractAgent"
    assert meta["agent_id"] == 7 and meta["id"] == 7
    assert meta["name"] == "probe-7"
    assert meta["profile"] == profile
    assert meta["step_count"] == 0
    assert meta["current_time"] is None and meta["tick"] is None
    assert meta["visible_skills"] == [] and meta["activated_skills"] == []
    assert meta["initialized_at"] is None

    stored_config = json.loads((ws / "config.json").read_text(encoding="utf-8"))
    assert stored_config == config


def test_config_json_write_once_and_step_state_roundtrip(tmp_path):
    ws = tmp_path / "agent_0007"
    _profile, config = _create(ws)
    config_bytes_before = (ws / "config.json").read_bytes()

    async def scenario():
        agent = await MiniContractAgent.from_workspace(ws, _proxy())
        assert agent.id == 7
        assert agent.name == "probe-7"
        answer = await agent.ask("ping")
        assert answer == "mini:7:ping"
        summary = await agent.step(60, T0)
        assert summary == "stepped:7:1"
        await agent.to_workspace(ws)
        await agent.close()

        # Reconstruct a FRESH instance from disk: counters and time restored.
        restored = await MiniContractAgent.from_workspace(ws, _proxy())
        assert restored.id == 7
        assert restored.get_profile()["persona"] == "terse"
        # step_count restored to 1 -> the next step is number 2.
        assert await restored.step(60, T1) == "stepped:7:2"
        # current_time was restored from AGENT.json before this step ran.
        return restored

    asyncio.run(scenario())

    # config.json byte-identical: static, never rewritten by to_workspace.
    assert (ws / "config.json").read_bytes() == config_bytes_before

    # Post-step AGENT.json now follows the build_agent_json shape
    # (agent.py:794-812) with the persisted counters.
    meta = json.loads((ws / "AGENT.json").read_text(encoding="utf-8"))
    assert set(meta.keys()) == {
        "schema_version", "agent_class", "agent_id", "name", "current_time",
        "tick", "step_count", "profile", "workspace", "skills",
        "initialized_at",
    }
    assert meta["schema_version"] == 1
    assert meta["agent_class"] == "MiniContractAgent"
    assert meta["agent_id"] == 7
    assert meta["step_count"] == 1
    assert meta["current_time"] == T0.isoformat()
    assert meta["workspace"]["root"] == str(ws.resolve())


def test_restored_current_time_round_trips_exactly(tmp_path):
    ws = tmp_path / "agent_0003"
    _create(ws, agent_id=3)

    async def scenario():
        agent = await MiniContractAgent.from_workspace(ws, _proxy())
        await agent.step(60, T0)
        await agent.to_workspace(ws)
        restored = await MiniContractAgent.from_workspace(ws, _proxy())
        # Private field inspection is deliberate: this is the exact slot
        # restore() parses from AGENT.json (agent.py:363-371).
        assert restored._step_count == 1
        assert restored._current_time == T0
        return None

    asyncio.run(scenario())


def test_opaque_binary_blob_under_state_survives_restore_and_steps(tmp_path):
    ws = tmp_path / "agent_0009"
    _create(ws, agent_id=9)
    blob_path = ws / "state" / "concordia_checkpoint.bin"
    blob_path.write_bytes(OPAQUE_BLOB)

    async def scenario():
        agent = await MiniContractAgent.from_workspace(ws, _proxy())
        await agent.step(60, T0)
        await agent.to_workspace(ws)
        restored = await MiniContractAgent.from_workspace(ws, _proxy())
        await restored.step(60, T1)
        await restored.to_workspace(ws)
        return None

    asyncio.run(scenario())
    # The framework never scans or rewrites agent-owned state/ files.
    assert blob_path.read_bytes() == OPAQUE_BLOB


def test_restore_binds_trace_writer_from_service_proxy_trace_dir(tmp_path):
    """ServiceProxy carries a TraceProxy; restore -> _bind_workspace builds the
    per-agent JsonlTraceWriter over a local sharded sink (agent.py:618-664),
    and a span emitted in step() lands in trace_<xx>.jsonl."""
    ws = tmp_path / "agent_0011"
    trace_dir = tmp_path / "trace"
    _create(ws, agent_id=11)

    async def scenario():
        agent = await MiniContractAgent.from_workspace(ws, _proxy(trace_dir))
        await agent.step(60, T0)
        await agent.to_workspace(ws)
        return None

    asyncio.run(scenario())

    shard_files = sorted(trace_dir.glob("trace_*.jsonl"))
    assert shard_files, f"no trace shards written under {trace_dir}"
    records = []
    for shard in shard_files:
        for line in shard.read_text(encoding="utf-8").splitlines():
            records.append(json.loads(line))
    mini_spans = [r for r in records if r.get("name") == "mini.step"]
    assert mini_spans, records
    span = mini_spans[0]
    assert span["resource"]["agent.id"] == 11
    assert span["status"]["code"] == "ok"
    assert span["attributes"]["agent.step_count"] == 1


def test_from_workspace_missing_workspace_raises(tmp_path):
    missing = tmp_path / "agent_9999"

    async def scenario():
        with pytest.raises(FileNotFoundError):
            await MiniContractAgent.from_workspace(missing, _proxy())

    asyncio.run(scenario())
