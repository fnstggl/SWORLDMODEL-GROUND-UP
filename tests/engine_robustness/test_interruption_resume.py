"""Interruption and resume (OPERATIONAL_ROBUSTNESS_MATRIX rows 4-5).

A mid-run branch PROCESS is killed -- SIGTERM and, separately, the
unmaskable SIGKILL -- after it atomically persisted its whole-branch
checkpoint.  Death must be bounded, the persisted state must survive
uncorrupted (the atomic tmp+``os.replace`` write is the mechanism), no
process may be orphaned, and a resume from the persisted checkpoint in a
DIFFERENT process must complete the branch byte-identically to an
uninterrupted reference run (pairing with the ``tests/engine_checkpoint``
equivalence gates, which prove the same equality without a kill).
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

import json
import os
import signal
import time

from checkpoint_helpers import (branch_setup, full_signature,
                                load_fixture_one, make_models,
                                prompt_pure_params)
from robustness_helpers import (ENGINE_PYTHON, HERE,
                                assert_no_processes_with_marker, child_env,
                                spawned_child, wait_for_file_line)
from sworldmodel.backends.concordia_local import runner as runner_module
from sworldmodel.counterfactuals.manager import _seeded_branch_scope

CHILD = HERE / "_child_checkpoint_then_hang.py"
CANDIDATE_ID = "concise_relevant"

#: bounded-death budget after the signal (generous; measured below)
DEATH_BUDGET_S = 15.0


@pytest.fixture(scope="module")
def uninterrupted_reference():
    """The uninterrupted 4-step run of the same branch, in this
    process: the byte-comparison target for every resumed leg."""
    fx = load_fixture_one()
    candidate, plan, _branch_id, branch_seed = branch_setup(fx,
                                                            CANDIDATE_ID)
    actor_models, gm_model = make_models(prompt_pure_params(fx), candidate,
                                         branch_seed)
    with _seeded_branch_scope(branch_seed):
        raw = runner_module.run_branch(plan, actor_models=actor_models,
                                       gm_model=gm_model)
    assert raw["terminal_status"] == "cutoff"
    assert raw["infrastructure_errors"] == []
    return {"fx": fx, "signature": full_signature(raw)}


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGKILL],
                         ids=["sigterm", "sigkill"])
def test_killed_branch_process_dies_bounded_and_resumes(
        tmp_path, uninterrupted_reference, sig):
    """Matrix rows 4-5: bounded death under both signals, persisted
    checkpoint intact, no orphans, and a cross-process resume that
    completes byte-identically to the uninterrupted run."""
    out_dir = tmp_path / "branch_state"
    out_dir.mkdir()
    marker = f"robustness-interrupt-{sig.name}-{os.getpid()}"

    with spawned_child([ENGINE_PYTHON, CHILD, out_dir, marker],
                       log_dir=tmp_path / "logs",
                       env=child_env()) as child:
        wait_for_file_line(out_dir / "progress", "CHECKPOINT_PERSISTED",
                           timeout=60.0)
        sent_at = time.monotonic()
        child.signal_group(sig)
        code = child.wait(DEATH_BUDGET_S)
        death_seconds = time.monotonic() - sent_at
        stderr_tail = child.stderr_text()[-800:]

    # Bounded, attributable death: the exact signal, within budget.
    assert code == -int(sig), (
        f"expected death by {sig.name}, got returncode {code}; "
        f"stderr: {stderr_tail}")
    assert death_seconds < DEATH_BUDGET_S
    assert_no_processes_with_marker(marker)

    # The persisted state survived the kill uncorrupted: the atomic
    # write left a complete, parseable, restorable checkpoint.
    blob = json.loads((out_dir / "checkpoint.json")
                      .read_text(encoding="utf-8"))
    cursor = blob["sidecar"]["engine_cursor"]
    assert cursor["steps_completed"] == 2
    assert cursor["remaining_steps"] == 2

    # Cross-process resume: THIS process rebuilds fresh models and
    # continues the killed process's branch to completion.
    fx = uninterrupted_reference["fx"]
    candidate, plan, _branch_id, branch_seed = branch_setup(fx,
                                                            CANDIDATE_ID)
    actor_models, gm_model = make_models(prompt_pure_params(fx), candidate,
                                         branch_seed)
    with _seeded_branch_scope(branch_seed):
        resumed = runner_module.run_branch(
            plan, actor_models=actor_models, gm_model=gm_model,
            resume_from=blob)
    assert resumed["terminal_status"] == "cutoff"
    assert resumed["infrastructure_errors"] == []
    assert resumed["resumed_from_checkpoint"] is True
    assert resumed["resumed_at_step"] == 2
    assert full_signature(resumed) == uninterrupted_reference["signature"]
