"""Scale-unit agent SOURCE (materialized, never imported, by the scale
harness).

INFRASTRUCTURE TEST ONLY: this agent is a scripted, deliberately shallow
scale-test unit for the Phase 11 societal infrastructure proof --
infrastructure rather than calibrated societal simulation; no population
realism claim.  It makes NO LLM calls and NO network I/O.

``tests/engine_scale/scale_harness.py`` copies this file's exact source
text into ``<workspace>/custom/agents/scale_unit_agent.py`` so
AgentSociety's stock custom-module scanner registers the class inside
every Ray worker process (the same production route the Phase 7 branch
executor proved: driver-side registry writes do not cross the Ray
boundary).  The class satisfies the scanner's acceptance rules: defined
in the file, a direct ``AgentBase`` subclass, no-arg constructible,
overrides ``to_workspace`` / ``ask`` / ``step``, non-empty docstring.

``step(tick, t)`` contract (one shallow scripted action, exactly once):

1. read the write-once ``config.json`` -> ``scale_execution`` mapping
   {schema_version, partition_id, delay_ticks, fail_at_tick} written by
   the harness at workspace creation;
2. read persistent unit state from ``state/unit_state.json`` (seq
   counter + hash chain).  The agent object is reconstructed from the
   workspace for every step (AgentSociety's stateless-record model), so
   any cross-step continuity in the persisted chain PROVES the workspace
   files carried the state;
3. injected-failure mode: when ``fail_at_tick`` is set and
   ``tick >= fail_at_tick``, write the structured error artifact
   ``state/unit_error.json`` atomically (write-once) and raise -- the
   runner's per-agent isolation turns this into ``ok=False`` for this
   agent only (dual-channel failure evidence, driver record + workspace
   artifact).  A failed unit NEVER acts at or after its failure tick, so
   a scheduler that kept invoking it could not silently manufacture
   actions;
4. otherwise: optionally hold the concurrency slot with a non-blocking
   ``asyncio.sleep`` for this tick's configured delay (the overlap-probe
   window -- in-worker timestamps bracket the sleep), then record
   exactly one action: append one JSON line to
   ``state/unit_actions.jsonl`` (single O_APPEND write) and update
   ``state/unit_state.json`` atomically (tmp + ``os.replace``; upstream
   agent persistence is not atomic -- audit caveat U4 -- so every file
   this agent owns is);
5. return a machine-parseable summary
   ``unit_ok|<agent_id>|<tick>|<seq>|<action_id>|<started>|<stopped>``
   consumed by the driver ledger; the workspace files stay the
   authoritative record and the two channels are reconciled exactly.

The hash chain (``chain_n = sha256(chain_{n-1} | action_id | tick)``,
``chain_0 = sha256('unit-genesis|' + partition_id + '|' + agent_id)``)
makes per-agent action history tamper-evident and order-proving: the
reconciliation recomputes it from the action log and compares it with
the persisted state.

Importing this module requires the optional ``agentsociety2`` package
(engine environment); the harness only reads this file's source text and
never imports it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import traceback
from pathlib import Path

_IMPORT_HELP = (
    "tests/engine_scale/scale_agent_template.py requires the optional "
    "'agentsociety2' package (engine environment, Python >= 3.12) with "
    "AGENTSOCIETY_LLM_API_KEY exported. The scale harness only reads this "
    "file's source text; it is imported only by the workspace scanner."
)

try:
    from agentsociety2.agent.base.agent import AgentBase
except ImportError as exc:  # degrade loudly, never partially
    raise ImportError(f"{_IMPORT_HELP} (root cause: {exc!r})") from exc

#: config.json keys the harness writes and this agent requires
_REQUIRED_SPEC_KEYS = ("schema_version", "partition_id", "delay_ticks",
                       "fail_at_tick")

#: evidence file names under the workspace ``state/`` directory
STATE_FILE = "unit_state.json"
ACTIONS_FILE = "unit_actions.jsonl"
ERROR_FILE = "unit_error.json"

#: injected-failure marker prefix (asserted by driver and reconciliation)
FAILURE_MARKER_PREFIX = "SCALE_INJECTED_UNIT_FAILURE_"


def _write_json_atomic(path: Path, payload, *, coerce: bool) -> None:
    """Atomic JSON write: serialize fully, write a same-directory temp
    file, then ``os.replace``."""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2,
                      default=str if coerce else None)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, payload) -> None:
    """Append exactly one JSON line with a single O_APPEND write (no
    interleaving risk; each agent owns its own file anyway)."""
    data = (json.dumps(payload, ensure_ascii=False, sort_keys=True)
            + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def genesis_chain(partition_id: str, agent_id: int) -> str:
    """chain_0 -- also recomputed verbatim by the reconciliation."""
    seed = f"unit-genesis|{partition_id}|{agent_id}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def next_chain(chain: str, action_id: str, tick: int) -> str:
    """chain_n -- also recomputed verbatim by the reconciliation."""
    material = f"{chain}|{action_id}|{tick}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ScaleUnitAgent(AgentBase):
    """Scripted shallow scale-test unit: records exactly one
    tamper-evident action per activated tick (infrastructure test only;
    no population realism claim)."""

    async def to_workspace(self, workspace_path):
        workspace_path = Path(workspace_path)
        if self._workspace_root is None:
            self._bind_workspace(workspace_path)
        self.persist_agent_json(tick=None, t=self._current_time)

    async def ask(self, message, readonly=True, *, t=None):
        return f"scale_unit:{self.id}:{message}"

    # ------------------------------------------------------------------
    # step: one scripted action
    # ------------------------------------------------------------------

    async def step(self, tick, t):
        self._step_count += 1
        self._current_time = t
        started = time.time()
        state_dir = self.workspace_root_path() / "state"
        spec = self._scale_spec()
        partition_id = str(spec["partition_id"])
        tick = int(tick)

        fail_at = spec["fail_at_tick"]
        if fail_at is not None and tick >= int(fail_at):
            self._write_error_artifact(state_dir, partition_id, tick,
                                       int(fail_at), started)
            raise RuntimeError(
                f"{FAILURE_MARKER_PREFIX}{self.id}_tick_{tick}")

        state = self._read_unit_state(state_dir, partition_id)
        delay_s = float(spec["delay_ticks"].get(str(tick), 0) or 0)
        if delay_s > 0:
            # Non-blocking: agents in one batch overlap via asyncio.gather,
            # so the configured concurrency bound is window * batch_size.
            await asyncio.sleep(delay_s)
        stopped = time.time()

        seq = int(state["seq"]) + 1
        action_id = f"{partition_id}:{self.id}:{seq}"
        chain = next_chain(str(state["chain"]), action_id, tick)
        action = {
            "schema_version": 1,
            "action_id": action_id,
            "agent_id": self.id,
            "partition_id": partition_id,
            "tick": tick,
            "seq": seq,
            "chain": chain,
            "pid": os.getpid(),
            "started_unix": started,
            "stopped_unix": stopped,
        }
        _append_jsonl(state_dir / ACTIONS_FILE, action)
        _write_json_atomic(state_dir / STATE_FILE, {
            "schema_version": 1,
            "partition_id": partition_id,
            "agent_id": self.id,
            "seq": seq,
            "chain": chain,
            "last_tick": tick,
        }, coerce=False)
        return (f"unit_ok|{self.id}|{tick}|{seq}|{action_id}"
                f"|{started:.6f}|{stopped:.6f}")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _scale_spec(self) -> dict:
        spec = (self._config or {}).get("scale_execution")
        if not isinstance(spec, dict):
            raise ValueError(
                "workspace config.json carries no 'scale_execution' "
                "mapping; this workspace was not created by the scale "
                "harness")
        missing = [key for key in _REQUIRED_SPEC_KEYS if key not in spec]
        if missing:
            raise ValueError(
                f"scale_execution config is missing required keys: "
                f"{sorted(missing)}")
        if not isinstance(spec["delay_ticks"], dict):
            raise ValueError("scale_execution.delay_ticks must be a mapping "
                             "of tick (string) -> seconds")
        fail_at = spec["fail_at_tick"]
        if fail_at is not None and type(fail_at) is not int:
            raise ValueError(
                "scale_execution.fail_at_tick must be an integer or null, "
                f"got {fail_at!r}")
        return spec

    def _read_unit_state(self, state_dir: Path, partition_id: str) -> dict:
        path = state_dir / STATE_FILE
        if not path.exists():
            return {"seq": 0, "chain": genesis_chain(partition_id, self.id)}
        state = json.loads(path.read_text(encoding="utf-8"))
        if int(state.get("agent_id", self.id)) != self.id:
            raise ValueError(
                f"unit state belongs to agent {state.get('agent_id')!r}, "
                f"not {self.id} -- workspace corruption")
        return state

    def _write_error_artifact(self, state_dir: Path, partition_id: str,
                              tick: int, fail_at: int,
                              started: float) -> None:
        """Write-once structured failure evidence; never masks the raise
        (the driver record carries ok=False regardless)."""
        path = state_dir / ERROR_FILE
        if path.exists():
            return
        try:
            payload = {
                "schema_version": 1,
                "statement": ("infrastructure test only -- injected "
                              "scripted failure; no population realism "
                              "claim"),
                "agent_id": self.id,
                "partition_id": partition_id,
                "tick": tick,
                "fail_at_tick": fail_at,
                "error": f"{FAILURE_MARKER_PREFIX}{self.id}_tick_{tick}",
                "error_type": "RuntimeError",
                "traceback_tail": traceback.format_stack()[-1][:2000],
                "worker_execution": {
                    "pid": os.getpid(),
                    "agent_id": self.id,
                    "tick": tick,
                    "started_unix": started,
                    "stopped_unix": time.time(),
                    "step_count": self._step_count,
                },
            }
            _write_json_atomic(path, payload, coerce=True)
        except Exception:  # noqa: BLE001 - evidence write must not mask
            pass
