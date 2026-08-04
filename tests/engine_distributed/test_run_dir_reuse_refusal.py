"""Atomic run_dir claim: reuse is refused loudly, nothing is overwritten.

Integration Reliability review (wave 2) MEDIUM: the run_dir freshness
guard was an exists-check followed by ``mkdir(exist_ok=True)`` -- a
TOCTOU window in which two runs could both pass the check and then
silently overwrite each other's workspace ``config.json`` through
upstream ``create_agents_batch`` (which rewrites the file
unconditionally).  The claim is now ATOMIC: ``mkdir(exist_ok=False)``
on the branches root, with ``FileExistsError`` converted into the
executor's typed loud refusal.  Consequences proven here:

- sequential reuse (run once, run again into the same run_dir) refuses
  with the typed error and leaves every byte of the first run's
  evidence untouched;
- an existing branches root is refused even when EMPTY (the pre-fix
  guard accepted that shape, which is exactly the state a concurrent
  claimant observes inside the race window -- atomicity means exists at
  all == owned by someone else);
- both public entry points share the claim
  (``run_interrupted_then_resume`` refuses the used run_dir the same
  way, before any Ray work).
"""

from __future__ import annotations

import hashlib
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

from pathlib import Path

from distributed_helpers import (MAX_STEPS, SEED, load_fixture_one,
                                 model_spec, scripted_params)
from sworldmodel.backends.agentsociety.branch_executor import (
    DistributedExecutionError, run_candidates_distributed,
    run_interrupted_then_resume)

#: the refusal wording that distinguishes the ATOMIC claim from the old
#: exists-then-mkdir guard
ATOMIC_REFUSAL_NEEDLE = "already exists"


def _tree_digest(root: Path) -> dict:
    """path -> sha256 for every file under ``root`` (byte-level
    no-overwrite evidence)."""
    digests = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digests[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    return digests


def test_second_run_into_same_run_dir_is_refused_without_overwrite(
        distributed_engine, tmp_path):
    fx = load_fixture_one()
    run_dir = tmp_path / "claimed_run"
    first = run_candidates_distributed(
        fx.world, fx.candidates,
        model_spec=model_spec(scripted_params(fx)),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx.evaluator_spec, registry=fx.registry,
        run_dir=run_dir, parallelism=2)
    assert [result.candidate_id for result in first.results] \
        == [candidate.candidate_id for candidate in fx.candidates]

    branches_root = run_dir / "branches"
    before = _tree_digest(branches_root)
    assert before, "the first run produced no workspace evidence"

    # Sequential reuse: typed refusal from the atomic claim.
    with pytest.raises(DistributedExecutionError,
                       match=ATOMIC_REFUSAL_NEEDLE):
        run_candidates_distributed(
            fx.world, fx.candidates,
            model_spec=model_spec(scripted_params(fx)),
            seed=SEED, max_steps=MAX_STEPS,
            evaluator_spec=fx.evaluator_spec, registry=fx.registry,
            run_dir=run_dir, parallelism=2)

    # The other entry point refuses the used run_dir identically (the
    # claim precedes any Ray/worker activity).
    with pytest.raises(DistributedExecutionError,
                       match=ATOMIC_REFUSAL_NEEDLE):
        run_interrupted_then_resume(
            fx.world, fx.candidates,
            model_spec=model_spec(scripted_params(fx)),
            seed=SEED, max_steps=MAX_STEPS,
            evaluator_spec=fx.evaluator_spec, registry=fx.registry,
            run_dir=run_dir, parallelism=2,
            checkpoint_after=1)

    # NO overwrite: every byte of the first run's evidence is intact.
    assert _tree_digest(branches_root) == before


def test_existing_even_empty_branches_root_is_refused_atomically(
        tmp_path):
    """The race-window shape: an empty branches root (what a concurrent
    claimant's mkdir just created, or an interrupted earlier claim left
    behind) is refused -- the pre-fix emptiness check accepted it and
    proceeded to overwrite.  The refusal fires before any Ray work, so
    no engine runtime is needed."""
    fx = load_fixture_one()
    run_dir = tmp_path / "raced_run"
    (run_dir / "branches").mkdir(parents=True)

    with pytest.raises(DistributedExecutionError,
                       match=ATOMIC_REFUSAL_NEEDLE):
        run_candidates_distributed(
            fx.world, fx.candidates,
            model_spec=model_spec(scripted_params(fx)),
            seed=SEED, max_steps=MAX_STEPS,
            evaluator_spec=fx.evaluator_spec, registry=fx.registry,
            run_dir=run_dir, parallelism=2)

    # The claim refused without touching the directory.
    assert list((run_dir / "branches").iterdir()) == []
