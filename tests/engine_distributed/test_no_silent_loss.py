"""No silent loss: a vanished branch result is a LOUD collection error.

Audit finding (AGENTSOCIETY_AUDIT.md section 9): the stock society driver
discards per-agent step results, so a lost branch would be silent there.
This executor keeps the driver channel AND treats the workspace files as
authoritative; when the driver says ok=True but the authoritative
``branch_result.json`` is missing (simulated corruption via the
``pre_collect_hook`` test seam), collection must raise a
``CollectionIntegrityError`` naming the branch and the missing file --
never return a partial success.
"""

from __future__ import annotations

import sys

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
                                 model_spec, scripted_params)
from sworldmodel.backends.agentsociety.branch_executor import (
    CollectionIntegrityError, run_candidates_distributed)


def test_deleted_result_file_raises_loudly_naming_the_branch(
        distributed_engine, tmp_path):
    fx = load_fixture_one()
    victim = fx.candidates[1].candidate_id
    deleted = []

    def delete_one_result(workspaces):
        target = workspaces[victim] / "state" / "branch_result.json"
        assert target.is_file(), (
            "test-hook precondition: the branch wrote its result before "
            "the simulated corruption")
        target.unlink()
        deleted.append(str(target))

    with pytest.raises(CollectionIntegrityError) as excinfo:
        run_candidates_distributed(
            fx.world, fx.candidates,
            model_spec=model_spec(scripted_params(fx)),
            seed=SEED, max_steps=MAX_STEPS,
            evaluator_spec=fx.evaluator_spec, registry=fx.registry,
            run_dir=tmp_path / "corrupted", parallelism=2,
            pre_collect_hook=delete_one_result)

    assert len(deleted) == 1
    message = str(excinfo.value)
    assert victim in message
    assert "branch_result.json" in message
    assert "ok=True" in message
    assert "partial success" in message


def test_hook_seam_without_corruption_is_inert(distributed_engine,
                                              tmp_path):
    fx = load_fixture_one()
    candidate_ids = [candidate.candidate_id for candidate in fx.candidates]
    observed = []

    def record_only(workspaces):
        observed.append({cid: str(path)
                         for cid, path in workspaces.items()})

    run = run_candidates_distributed(
        fx.world, fx.candidates,
        model_spec=model_spec(scripted_params(fx)),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx.evaluator_spec, registry=fx.registry,
        run_dir=tmp_path / "clean", parallelism=2,
        pre_collect_hook=record_only)

    assert len(observed) == 1
    assert sorted(observed[0]) == sorted(candidate_ids)
    assert [result.candidate_id for result in run.results] == candidate_ids
    for result in run.results:
        assert result.infrastructure_errors == ()
    assert run.execution_report["exactly_once"] is True
