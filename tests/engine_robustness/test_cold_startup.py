"""Cold startup (OPERATIONAL_ROBUSTNESS_MATRIX row 2; repeated-runs
row 3 gains fresh-process reproducibility evidence).

A FRESH engine-interpreter process given an EMPTY run root -- no
preexisting Ray runtime, no workspaces, no caches, no prior state of any
kind -- must initialize cleanly and complete a 1-candidate scripted
branch, and its result must be byte-identical (branch signature) to the
same request executed in this long-lived test process: first-run
behavior equals steady-state behavior.
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

import os

from cf_helpers import (MAX_STEPS, SEED, branch_signature,
                        fixture_model_factory, load_fixture_one)
from robustness_helpers import (ENGINE_PYTHON, HERE,
                                assert_no_processes_with_marker, child_env,
                                load_json, run_child)
from sworldmodel.counterfactuals import run_candidates_detailed

CHILD = HERE / "_child_cold_start.py"


def test_cold_start_completes_one_branch_from_nothing(tmp_path):
    """Matrix row 2: clean init + one completed scripted branch in a
    fresh process with an empty run root, bounded, without Ray, with the
    result reproducing the steady-state signature exactly."""
    run_root = tmp_path / "run_root"
    run_root.mkdir()
    marker = f"robustness-cold-start-{os.getpid()}"

    code, out, err = run_child(
        [ENGINE_PYTHON, CHILD, run_root, marker],
        log_dir=tmp_path / "logs", env=child_env(), timeout=90.0)
    assert code == 0, (
        f"cold-start child failed (exit {code});\nstdout: {out[-800:]}\n"
        f"stderr: {err[-1500:]}")
    assert "COLD_START_OK" in out
    assert_no_processes_with_marker(marker)

    report = load_json(run_root / "cold_start_report.json")
    assert report["run_root_was_empty"] is True
    assert report["ray_imported"] is False
    assert report["candidate_id"] == "concise_relevant"
    assert report["terminal_status"] == "cutoff"
    assert report["infrastructure_errors"] == []
    assert report["event_count"] == 3
    assert report["wall_seconds"] < 60.0
    # Fixture-1's concise_relevant candidate scripts a real reply plus
    # the scheduled follow-up: metrics measured in the fresh process.
    assert report["metric_values"] == {
        "recipient_reply_sent": True,
        "meeting_scheduled": True,
        "explicit_decline": False,
    }

    # Steady-state reference in THIS long-lived process: identical
    # request, identical signature -- first-run equals steady-state, and
    # a second (fresh-process) execution of the same request reproduced
    # the first byte-for-byte (repeated-runs evidence at process level).
    fx = load_fixture_one()
    reference = run_candidates_detailed(
        fx.world, [fx.candidates[1]],
        model_factory=fixture_model_factory(fx), seed=SEED,
        max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)
    assert report["branch_signature"] \
        == branch_signature(reference.results[0])
