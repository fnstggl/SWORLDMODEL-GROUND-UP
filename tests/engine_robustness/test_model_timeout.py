"""Model timeout (OPERATIONAL_ROBUSTNESS_MATRIX row 11).

Two layers, matching what actually exists in the code:

1. INNERMOST EXISTING SEAM -- the semantic-runtime transport
   (``sworldmodel.semantic_runtime.llm.RuntimeCaller``) carries a
   whole-request wall deadline (thread-join), a socket timeout, and a
   chunked-read deadline.  A provider call that blocks past the deadline
   becomes a typed ``RuntimeTechnicalFailure`` naming the timeout, with
   every attempt in the structured per-call log.  (``llm_mind._http_json``
   carries its own 120s socket timeout for the compiler-side path.)

2. HONESTLY RECORDED GAP + OUTER BOUND -- the ENGINE BRANCH path
   (``concordia_local.runner`` driving injected model objects) has NO
   in-branch model-call timeout seam: an injected model that never
   returns hangs the branch.  The gap is pinned by assertion here (so a
   future seam flags this row for update) and the matrix records it; the
   proven bound is the OUTER layer -- the monitored runner's no-progress
   kill terminates the whole process group boundedly and leaves a
   structured job record naming the timeout, which this test drives
   end-to-end against a synthetic project tree.
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

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

import inspect
import os
import threading
import time

from robustness_helpers import (ENGINE_PYTHON, HERE, RUN_MONITORED,
                                assert_no_processes_with_marker, child_env,
                                load_json, run_child)

HUNG_BRANCH_CHILD = HERE / "_child_hung_branch.py"


def test_runtime_caller_deadline_bounds_a_hung_provider(monkeypatch):
    """Matrix row 11 (inner seam): a provider request that blocks past
    the configured whole-request deadline is terminated by the deadline
    mechanism and surfaces as a typed failure naming the timeout, with
    both attempts logged; the deployed deadlines exist and are ordered
    socket < read < whole-request."""
    from sworldmodel.semantic_runtime import llm as llm_mod

    # The deployed constants are real and sanely ordered.
    assert 0 < llm_mod.SOCKET_TIMEOUT_S < llm_mod.TOTAL_READ_DEADLINE_S \
        < llm_mod.TOTAL_REQUEST_DEADLINE_S

    # Exercise the MECHANISM at a test-scale deadline: the blocked call
    # is bounded by the thread-join deadline, not by the block duration.
    monkeypatch.setattr(llm_mod, "TOTAL_REQUEST_DEADLINE_S", 0.4)
    caller = llm_mod.RuntimeCaller()
    release = threading.Event()

    def hanging_request(system, user):
        release.wait(30.0)
        return "{}", {}

    caller._do_request = hanging_request
    started = time.monotonic()
    with pytest.raises(llm_mod.RuntimeTechnicalFailure) as excinfo:
        caller.ask("probe", "system", "user", lambda obj: obj)
    wall = time.monotonic() - started
    release.set()  # unblock the two abandoned worker threads

    assert wall < 5.0, f"deadline did not bound the call: {wall:.1f}s"
    assert "provider request exceeded" in str(excinfo.value)
    assert len(caller.calls) == 2
    for entry in caller.calls:
        assert entry["validation"].startswith("TimeoutError:")
        assert "provider request exceeded" in entry["validation"]


def test_engine_branch_has_no_inner_seam_and_outer_bound_kills_hung_branch(
        tmp_path):
    """Matrix row 11 (gap + outer bound): the engine branch entry points
    expose no timeout parameter (the pinned gap), and a branch whose
    injected model call never returns is killed by the monitored
    runner's no-progress bound -- whole process group terminated, no
    survivors, structured job record naming the timeout."""
    from sworldmodel.backends.concordia_local import runner as runner_module
    from sworldmodel.counterfactuals import manager as manager_module

    # Pin the gap: if an in-branch timeout seam is ever added, this
    # assertion fails and matrix row 11 must be rewritten.
    for entry_point in (runner_module.run_branch,
                        runner_module.run_built_branch,
                        manager_module.run_candidates_detailed):
        parameters = inspect.signature(entry_point).parameters
        assert not any("timeout" in name for name in parameters), (
            f"{entry_point.__name__} grew a timeout seam; update "
            "OPERATIONAL_ROBUSTNESS_MATRIX row 11 and test the seam "
            "directly")

    # Outer bound, end to end, against a SYNTHETIC project tree (the
    # documented CLAUDE_PROJECT_DIR test seam -- the real control plane
    # is never touched).
    project = tmp_path / "synthetic_project"
    (project / ".agent-run").mkdir(parents=True)
    marker = f"robustness-hung-branch-{os.getpid()}"
    env = child_env(CLAUDE_PROJECT_DIR=project)

    code, out, err = run_child(
        [sys.executable, RUN_MONITORED,
         "--job-id", marker,
         "--classification", "exploratory",
         "--no-progress-timeout", "4",
         "--total-timeout", "90",
         "--grace-period", "2",
         "--heartbeat-interval", "1",
         "--", ENGINE_PYTHON, HUNG_BRANCH_CHILD, marker],
        log_dir=tmp_path / "logs", env=env, timeout=110.0)

    assert code == 125, (
        f"expected the no-progress exit code 125, got {code};\n"
        f"stderr: {err[-1200:]}")
    record = load_json(project / ".agent-run" / "jobs" / marker
                       / "job.json")
    assert record["state"] == "no_progress_timeout"
    assert record["process_group_terminated"] is True
    assert record["survivors_after_termination"] == []
    assert "no meaningful progress" in record["termination_reason"]
    assert "--no-progress-timeout 4" in record["termination_reason"]
    # The branch genuinely reached the hanging model call before the
    # kill: the hang was mid-branch, not a startup failure.
    assert "BRANCH_STARTING" in record["stdout_tail"]
    assert "BRANCH_MODEL_CALL_HANGING" in record["stdout_tail"]
    assert "UNREACHABLE_COMPLETION" not in record["stdout_tail"]
    assert_no_processes_with_marker(marker)
