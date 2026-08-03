"""Partial workspace corruption (OPERATIONAL_ROBUSTNESS_MATRIX row 14).

Complements the existing corruption coverage -- checkpoint PAYLOAD
tamper refusals (``tests/engine_checkpoint/test_restore_correctness.py::
test_tampered_checkpoints_are_refused_loudly``) and action-log tamper
detection at reconciliation (``tests/engine_scale/test_scale_fast_tier
.py::test_reconciliation_catches_lost_and_duplicated_actions``) -- with
the WORKSPACE-FILE variants: truncated/garbled ``AGENT.json``, garbled
agent state files, and a garbled persisted branch-checkpoint blob,
driven through the REAL AgentSociety step path (the same async cores the
Ray tasks wrap, in-process).

Required properties: every corruption surfaces as an EXPLICIT per-agent
failure record (never a silent skip, never a batch abort taking healthy
agents down), the corrupted agent's evidence names what is knowable, and
RECOVERY works where the design provides it -- restore the file / the
last good checkpoint and re-step to completion.

Recorded finding F-R1 (matrix row 14 notes): the per-agent
driver-channel error for a corrupted workspace FILE is the raw
``JSONDecodeError`` repr -- it names the agent (record id, workspace)
but not WHICH file is corrupt; only the branch agent's own error file
adds phase/candidate/branch identity, and ``AGENT.json`` corruption
fails before the agent exists, so no agent-side artifact can be
written.  Explicit and isolated: yes; file-naming: partial.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "robustness suite requires Python >= 3.12 (engine env); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("agentsociety2", exc_type=ImportError)
pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from checkpoint_helpers import (CHECKPOINT_AFTER, MAX_STEPS, branch_setup,
                                load_fixture_one, model_spec,
                                prompt_pure_params)
from robustness_helpers import load_json
from sworldmodel.backends.agentsociety import branch_executor

CLOCK = datetime(2000, 1, 1)


def _engine_modules():
    from agentsociety2.agent import runner as as2_runner
    from agentsociety2.agent.service_proxy import build_service_proxy
    from agentsociety2.registry import get_agent_module_class, get_registry
    return as2_runner, build_service_proxy, get_registry, \
        get_agent_module_class


def _bind_workspace(monkeypatch, root: Path, get_registry,
                    get_agent_module_class, class_name: str):
    """Point the (path-security-guarded) registry at this test's root;
    monkeypatch restores WORKSPACE_PATH and the registry binding cannot
    outlive the suite's directory teardown."""
    monkeypatch.setenv("WORKSPACE_PATH", str(root))
    get_registry().set_workspace(root)
    cls = get_agent_module_class(class_name)
    assert cls is not None and cls.__name__ == class_name


def _step(as2_runner, units: Path, class_name: str, ids, tick: int,
          proxy) -> list:
    """Drive the REAL step path in-process (the exact async core the Ray
    task wraps), returning the per-agent records."""
    return asyncio.run(as2_runner._step_agent_batch_async(
        list(ids), str(units), class_name, tick, CLOCK, proxy))


def test_corrupt_agent_json_is_explicit_isolated_and_restorable(
        tmp_path, monkeypatch):
    """Row 14: truncated ``AGENT.json`` -> explicit per-agent ok=False
    (typed JSON decode failure) while a healthy agent IN THE SAME BATCH
    completes; restoring the file recovers the agent with its state
    continuity intact (seq continues, no gap, no duplicate)."""
    import scale_harness

    as2_runner, build_service_proxy, get_registry, \
        get_agent_module_class = _engine_modules()
    root = tmp_path / "ws"
    root.mkdir()
    scale_harness.materialize_scale_agent(root)
    _bind_workspace(monkeypatch, root, get_registry,
                    get_agent_module_class, "ScaleUnitAgent")
    proxy = build_service_proxy(None, run_dir=root / "driver", trace=False,
                                replay=False)
    units = root / "units"
    items = [{"id": agent_id,
              "profile": {"id": agent_id, "name": f"unit_{agent_id}"},
              "config": {"scale_execution": {
                  "schema_version": 1, "partition_id": "corrupt",
                  "delay_ticks": {}, "fail_at_tick": None}}}
             for agent_id in (21, 22)]
    created = asyncio.run(as2_runner._create_agents_batch_async(
        items, str(units), "ScaleUnitAgent"))
    assert created == 2

    records = _step(as2_runner, units, "ScaleUnitAgent", [21, 22], 1,
                    proxy)
    assert [record["ok"] for record in records] == [True, True]

    agent_json = units / "agent_0021" / "AGENT.json"
    good = agent_json.read_text(encoding="utf-8")
    agent_json.write_text(good[: len(good) // 2], encoding="utf-8")

    records = _step(as2_runner, units, "ScaleUnitAgent", [21, 22], 2,
                    proxy)
    by_id = {record["id"]: record for record in records}
    assert by_id[21]["ok"] is False
    assert "JSONDecodeError" in by_id[21]["error"]
    assert by_id[22]["ok"] is True  # isolation: the batch never aborts

    # Recovery: restore the file, re-step; state continuity holds (the
    # corrupted attempt wrote nothing).
    agent_json.write_text(good, encoding="utf-8")
    records = _step(as2_runner, units, "ScaleUnitAgent", [21], 3, proxy)
    assert records[0]["ok"] is True
    actions = scale_harness.read_jsonl(
        units / "agent_0021" / "state" / "unit_actions.jsonl")
    assert [(row["tick"], row["seq"]) for row in actions] == [(1, 1),
                                                              (3, 2)]

    state = load_json(units / "agent_0021" / "state" / "unit_state.json")
    chain = scale_harness.genesis_chain("corrupt", 21)
    for row in actions:
        chain = scale_harness.next_chain(chain, row["action_id"],
                                         row["tick"])
    assert state["chain"] == chain  # hash-chain continuity across the
    # corruption-and-restore cycle


def test_corrupt_state_file_is_explicit_and_restorable(tmp_path,
                                                       monkeypatch):
    """Row 14: a garbled ``state/unit_state.json`` -> explicit per-agent
    failure; restoring the file recovers.  A state file claiming a
    FOREIGN agent identity is refused with an error naming the
    corruption (the template's own integrity check)."""
    import scale_harness

    as2_runner, build_service_proxy, get_registry, \
        get_agent_module_class = _engine_modules()
    root = tmp_path / "ws"
    root.mkdir()
    scale_harness.materialize_scale_agent(root)
    _bind_workspace(monkeypatch, root, get_registry,
                    get_agent_module_class, "ScaleUnitAgent")
    proxy = build_service_proxy(None, run_dir=root / "driver", trace=False,
                                replay=False)
    units = root / "units"
    items = [{"id": 23, "profile": {"id": 23, "name": "unit_23"},
              "config": {"scale_execution": {
                  "schema_version": 1, "partition_id": "corrupt2",
                  "delay_ticks": {}, "fail_at_tick": None}}}]
    assert asyncio.run(as2_runner._create_agents_batch_async(
        items, str(units), "ScaleUnitAgent")) == 1
    assert _step(as2_runner, units, "ScaleUnitAgent", [23], 1,
                 proxy)[0]["ok"] is True

    state_path = units / "agent_0023" / "state" / "unit_state.json"
    good = state_path.read_text(encoding="utf-8")

    state_path.write_text("{ definitely not json", encoding="utf-8")
    record = _step(as2_runner, units, "ScaleUnitAgent", [23], 2, proxy)[0]
    assert record["ok"] is False
    assert "JSONDecodeError" in record["error"]

    foreign = json.loads(good)
    foreign["agent_id"] = 9999
    state_path.write_text(json.dumps(foreign), encoding="utf-8")
    record = _step(as2_runner, units, "ScaleUnitAgent", [23], 3, proxy)[0]
    assert record["ok"] is False
    assert "workspace corruption" in record["error"]
    assert "9999" in record["error"]

    state_path.write_text(good, encoding="utf-8")
    record = _step(as2_runner, units, "ScaleUnitAgent", [23], 4, proxy)[0]
    assert record["ok"] is True


def test_corrupt_checkpoint_blob_refused_then_recovered_from_last_good(
        tmp_path, monkeypatch):
    """Row 14 (recovery-where-possible, end to end): a garbled persisted
    branch-checkpoint blob is an explicit refusal carrying the branch
    agent's structured error file (phase + candidate + branch identity);
    restoring the LAST GOOD checkpoint and clearing the error marker
    resumes the branch to its complete, correct terminal result."""
    as2_runner, build_service_proxy, get_registry, \
        get_agent_module_class = _engine_modules()
    root = tmp_path / "ws"
    root.mkdir()
    branch_executor.materialize_branch_agent(root)
    _bind_workspace(monkeypatch, root, get_registry,
                    get_agent_module_class,
                    branch_executor.AGENT_CLASS_NAME)
    proxy = build_service_proxy(None, run_dir=root / "driver", trace=False,
                                replay=False)

    fx = load_fixture_one()
    candidate, plan, branch_id, branch_seed = branch_setup(
        fx, "concise_relevant")
    config = branch_executor._branch_execution_config(
        branch_id=branch_id, world_id=fx.world.world_id,
        candidate=candidate, plan=plan,
        model_spec=model_spec(prompt_pure_params(fx)),
        branch_seed=branch_seed, max_steps=MAX_STEPS,
        checkpoint_after=CHECKPOINT_AFTER, halt_at_checkpoint=True)
    units = root / "branches"
    items = [{"id": 1, "profile": {"id": 1, "name": "branch_1"},
              "config": {"branch_execution": config}}]
    assert asyncio.run(as2_runner._create_agents_batch_async(
        items, str(units), branch_executor.AGENT_CLASS_NAME)) == 1

    agent_class = branch_executor.AGENT_CLASS_NAME
    state = units / "agent_0001" / "state"
    blob_path = state / "branch_checkpoint.json"
    error_path = state / "branch_error.json"

    # Round 1: run to the boundary and halt with the blob persisted.
    record = _step(as2_runner, units, agent_class, [1], 1, proxy)[0]
    assert record["ok"] is True
    assert record["summary"] == "branch_checkpointed:1:concise_relevant"
    good_blob = blob_path.read_text(encoding="utf-8")

    # Corrupt the blob mid-payload; the resume is an explicit refusal
    # with the agent's structured error artifact.
    blob_path.write_text(good_blob[: len(good_blob) // 3] + "GARBLED{{{",
                         encoding="utf-8")
    record = _step(as2_runner, units, agent_class, [1], 2, proxy)[0]
    assert record["ok"] is False
    assert "JSONDecodeError" in record["error"]
    error = load_json(error_path)
    assert error["phase"] == "setup_or_run"
    assert error["error_type"] == "JSONDecodeError"
    assert error["candidate_id"] == "concise_relevant"
    assert error["branch_id"] == branch_id
    # No result was fabricated for the refused resume.
    assert not (state / "branch_result.json").exists()

    # Recovery: restore the last good checkpoint, clear the error
    # marker, re-step -> the branch resumes and COMPLETES correctly.
    blob_path.write_text(good_blob, encoding="utf-8")
    os.unlink(error_path)
    record = _step(as2_runner, units, agent_class, [1], 3, proxy)[0]
    assert record["ok"] is True
    assert record["summary"] == "branch_ok:1:concise_relevant"
    result = load_json(state / "branch_result.json")
    assert result["terminal_status"] == "cutoff"
    assert result["infrastructure_errors"] == []
    assert result["terminal_world_state"]["steps_completed"] == MAX_STEPS
    runner_record = load_json(state / "runner_record.json")
    assert runner_record["resumed_from_checkpoint"] is True
    assert runner_record["resumed_at_step"] == CHECKPOINT_AFTER
