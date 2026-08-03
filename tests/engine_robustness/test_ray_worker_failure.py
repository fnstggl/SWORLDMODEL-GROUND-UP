"""Ray worker failure (OPERATIONAL_ROBUSTNESS_MATRIX row 13).

A worker OS PROCESS is SIGKILLed while it executes a step task -- the
substrate-level failure class the in-worker injection suites
(``tests/engine_distributed/test_failure_isolation_distributed.py``,
``tests/engine_scale`` injected failures) deliberately do not cover,
because there the worker process survives and reports.

Proven here, at the same public primitives the branch executor and the
scale harness drive (``step_agent_batch`` on materialized scale-unit
workspaces):

- with retries disabled the killed task surfaces as Ray's TYPED
  ``WorkerCrashedError`` at ``ray.get`` -- explicit and bounded, never a
  hang, never a silent loss (the branch executor's harvest loop catches
  exactly this exception class into its ``task_error`` channel and
  synthesizes the reported-never-hidden failure ``BranchResult``);
- the sibling agent completes unaffected on the surviving/replacement
  worker;
- a RE-RUN of the killed step from the intact workspace succeeds with
  EXACTLY-ONCE file evidence (the killed attempt wrote nothing -- the
  workspace files are written atomically at step end);
- with one retry allowed, a single worker kill AUTO-RECOVERS via Ray's
  task re-execution, still with exactly-once file evidence (idempotent
  workspaces make at-least-once execution safe);
- the packaged task ships no explicit retry override
  (``_default_options == {}``), so production submissions inherit Ray's
  system default task-retry policy -- recorded in the matrix.

Kill discipline: only processes this suite's own Ray runtime spawned are
touched, identified by the ``ray::step_agent_batch`` process title that
exists exactly while OUR submitted task runs, and killed only while our
submission is in flight.
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
pytest.importorskip("ray", exc_type=ImportError)
pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

import os
import signal
import threading
import time
from datetime import datetime
from pathlib import Path

from scale_harness import read_jsonl

AGENT_CLASS = "ScaleUnitAgent"
DELAYED_ID = 31
SIBLING_ID = 32
#: blocking window the target step holds open for the killer thread
DELAY_S = 6.0
CLOCK = datetime(2000, 1, 1)

_TASK_TITLE = "ray::step_agent_batch"


def _step_worker_pids(exclude=frozenset()) -> list:
    """PIDs currently executing a step task of OUR runtime (Ray retitles
    a worker process ``ray::<task>`` exactly while it runs the task)."""
    hits = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) in exclude:
            continue
        try:
            cmd = Path(f"/proc/{entry}/cmdline").read_bytes()
        except OSError:
            continue
        if cmd.replace(b"\0", b" ").decode(
                "utf-8", "replace").startswith(_TASK_TITLE):
            hits.append(int(entry))
    return hits


def _kill_next_step_worker(box: dict, *, settle_s: float = 0.6,
                           timeout_s: float = 30.0) -> None:
    """Killer thread body: SIGKILL the FIRST step-task worker that
    appears (after a short settle so the task is genuinely inside its
    delay), recording what was killed."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        pids = _step_worker_pids(exclude=frozenset(box.get("killed", ())))
        if pids:
            time.sleep(settle_s)
            target = pids[0]
            try:
                os.kill(target, signal.SIGKILL)
                box.setdefault("killed", []).append(target)
                return
            except OSError:
                pass
        time.sleep(0.05)
    box["timeout"] = True


@pytest.fixture(scope="module")
def kill_run(robustness_engine, tmp_path_factory):
    """One materialized two-unit workspace pair for every leg below."""
    ray = robustness_engine["ray"]
    as2_runner = robustness_engine["as2_runner"]
    build_service_proxy = robustness_engine["build_service_proxy"]
    base = tmp_path_factory.mktemp("worker_kill")
    units = base / "units"
    proxy = build_service_proxy(None, run_dir=base / "driver", trace=False,
                                replay=False)

    items = []
    for agent_id, delays in ((DELAYED_ID, {"1": DELAY_S, "2": DELAY_S}),
                             (SIBLING_ID, {})):
        items.append({
            "id": agent_id,
            "profile": {"id": agent_id, "name": f"unit_{agent_id}"},
            "config": {"scale_execution": {
                "schema_version": 1, "partition_id": "workerkill",
                "delay_ticks": delays, "fail_at_tick": None}},
        })
    created = ray.get(as2_runner.create_agents_batch.remote(
        items, str(units), AGENT_CLASS))
    assert created == 2
    return {"ray": ray, "as2_runner": as2_runner, "proxy": proxy,
            "units": units}


def _actions(units: Path, agent_id: int) -> list:
    rows = read_jsonl(units / f"agent_{agent_id:04d}" / "state"
                      / "unit_actions.jsonl")
    return [(row["tick"], row["seq"]) for row in rows]


def test_killed_worker_is_a_typed_bounded_error_and_rerun_recovers(
        kill_run):
    """Row 13: kill -> typed ``WorkerCrashedError`` (bounded); sibling
    completes; re-run succeeds with exactly-once evidence."""
    ray = kill_run["ray"]
    as2_runner = kill_run["as2_runner"]
    proxy = kill_run["proxy"]
    units = kill_run["units"]

    box: dict = {}
    killer = threading.Thread(target=_kill_next_step_worker, args=(box,))
    killer.start()
    ref = as2_runner.step_agent_batch.options(max_retries=0).remote(
        [DELAYED_ID], str(units), AGENT_CLASS, 1, CLOCK, proxy)
    started = time.monotonic()
    with pytest.raises(ray.exceptions.WorkerCrashedError):
        ray.get(ref)
    wall = time.monotonic() - started
    killer.join(timeout=35.0)
    assert not killer.is_alive()
    assert box.get("killed"), "the killer thread never found the worker"
    assert wall < 30.0, f"worker death was not bounded: {wall:.1f}s"

    # The killed attempt left NO partial evidence (atomic end-of-step
    # writes): the workspace records nothing for tick 1 yet.
    assert _actions(units, DELAYED_ID) == []

    # Sibling agent: unaffected, completes on a surviving/replacement
    # worker.
    payload = ray.get(as2_runner.step_agent_batch.remote(
        [SIBLING_ID], str(units), AGENT_CLASS, 1, CLOCK, proxy))
    assert payload["results"][0]["ok"] is True
    assert _actions(units, SIBLING_ID) == [(1, 1)]

    # Re-run of the killed step from the intact workspace: succeeds,
    # exactly once.
    payload = ray.get(as2_runner.step_agent_batch.remote(
        [DELAYED_ID], str(units), AGENT_CLASS, 1, CLOCK, proxy))
    assert payload["results"][0]["ok"] is True
    assert _actions(units, DELAYED_ID) == [(1, 1)]


def test_single_kill_with_retry_budget_auto_recovers_exactly_once(
        kill_run):
    """Row 13 (recovery): with ``max_retries=1`` one worker kill is
    absorbed by Ray's task re-execution -- the caller sees success and
    the workspace still carries exactly-once evidence.  The packaged
    task ships no retry override, so production inherits Ray's default
    task-retry policy (recorded in the matrix)."""
    ray = kill_run["ray"]
    as2_runner = kill_run["as2_runner"]
    proxy = kill_run["proxy"]
    units = kill_run["units"]

    assert getattr(as2_runner.step_agent_batch, "_default_options",
                   None) == {}

    prior = _actions(units, DELAYED_ID)
    next_seq = len(prior) + 1

    box: dict = {}
    killer = threading.Thread(target=_kill_next_step_worker, args=(box,))
    killer.start()
    ref = as2_runner.step_agent_batch.options(max_retries=1).remote(
        [DELAYED_ID], str(units), AGENT_CLASS, 2, CLOCK, proxy)
    payload = ray.get(ref)
    killer.join(timeout=35.0)
    assert not killer.is_alive()
    assert box.get("killed"), "the killer thread never found the worker"

    assert payload["results"][0]["ok"] is True
    assert payload["results"][0]["summary"].startswith(
        f"unit_ok|{DELAYED_ID}|2|{next_seq}|")
    # Exactly-once file evidence across kill + retry: exactly one new
    # tick-2 row appended to whatever the workspace already carried.
    assert _actions(units, DELAYED_ID) == prior + [(2, next_seq)]

    # Nothing of ours is still running a step task.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and _step_worker_pids():
        time.sleep(0.1)
    assert _step_worker_pids() == []
