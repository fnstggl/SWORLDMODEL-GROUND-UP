"""Worker-side seeded-RNG equivalence (phases 3-7 review finding D5).

The Stage A equivalence proof used RNG-blind scripted models, so nothing
distinguished a worker that entered ``_seeded_branch_scope`` from one
that did not -- deleting the seeded scope from the branch template would
have passed every test.  Here the recipient's model appends one
global-``random`` 32-bit draw to every response, making each committed
event -- and therefore the branch signature -- a function of the evolving
per-branch seeded stream:

- the LOCAL leg draws inside the driver-side scope
  (``sworldmodel.counterfactuals.manager._seeded_branch_scope``);
- the DISTRIBUTED leg draws inside the branch template's worker-side
  scope, in separate Ray worker processes;
- byte-equal signatures therefore PROVE both scopes seed the same
  per-branch stream (seed material ``sha256(seed|candidate_id)``).

An unseeded (or deleted) worker scope draws from ambient process
randomness and diverges immediately, which is exactly the regression
this test exists to catch.
"""

from __future__ import annotations

import re
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

from distributed_helpers import (MAX_STEPS, MODEL_BUILDER_REF, SEED,
                                 load_fixture_one, model_spec,
                                 result_signature, scripted_params)
from distributed_model_specs import build_scripted_models
from sworldmodel.backends.agentsociety.branch_executor import \
    run_candidates_distributed
from sworldmodel.counterfactuals import run_candidates_detailed

RNG_DRAW_PATTERN = re.compile(r"\[rng-draw (\d+)\]")


def _rng_params():
    params = scripted_params(load_fixture_one())
    params["rng_draw_actors"] = ["recipient"]
    return params


def _branch_draws(result) -> tuple:
    """Every rng draw committed into this branch's event trace, in order."""
    return tuple(
        int(match) for event in result.to_dict()["event_trace"]
        for match in RNG_DRAW_PATTERN.findall(event["description"]))


def test_rng_consuming_models_are_equivalent_across_substrates(
        distributed_engine, tmp_path):
    params = _rng_params()

    fx_local = load_fixture_one()
    local = run_candidates_detailed(
        fx_local.world, fx_local.candidates,
        model_factory=build_scripted_models(params),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx_local.evaluator_spec,
        registry=fx_local.registry,
        model_config={"model_builder": MODEL_BUILDER_REF})

    fx_dist = load_fixture_one()
    dist = run_candidates_distributed(
        fx_dist.world, fx_dist.candidates,
        model_spec=model_spec(params),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx_dist.evaluator_spec,
        registry=fx_dist.registry,
        run_dir=tmp_path / "run",
        parallelism=2,
        model_config={"model_builder": MODEL_BUILDER_REF})

    # Same frozen base, same code-owned branch identity and seeds.
    assert dist.base_plan_content_hash == local.base_plan_content_hash
    assert dist.branch_ids == local.branch_ids
    assert dist.branch_seeds == local.branch_seeds

    # Byte-equal signatures WITH the trace now a function of the seeded
    # stream: the worker-side scope provably seeds what the driver-side
    # scope seeds.
    assert len(dist.results) == len(local.results) == 3
    for local_result, dist_result in zip(local.results, dist.results):
        assert local_result.candidate_id == dist_result.candidate_id
        assert dist_result.infrastructure_errors == ()
        assert result_signature(local_result) \
            == result_signature(dist_result), dist_result.candidate_id

    # The proof must not pass vacuously: every branch actually committed
    # rng draws, and the per-branch draw sequences are pairwise distinct
    # (different branch seeds -> different streams), so the suffixes are
    # genuine functions of the per-branch seed, not constants.
    draw_sequences = {}
    for dist_result in dist.results:
        draws = _branch_draws(dist_result)
        assert draws, (f"{dist_result.candidate_id}: no rng draws reached "
                       "the committed event trace")
        draw_sequences[dist_result.candidate_id] = draws
    sequences = list(draw_sequences.values())
    for i in range(len(sequences)):
        for j in range(i + 1, len(sequences)):
            assert sequences[i] != sequences[j], (
                "two branches produced identical draw sequences; the "
                "suffixes are not per-branch-seed dependent:\n"
                f"{draw_sequences}")

    assert dist.execution_report["exactly_once"] is True
