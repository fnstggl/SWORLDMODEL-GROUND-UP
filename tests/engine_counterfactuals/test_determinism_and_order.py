"""Phase 6 determinism and order invariance.

Directive hard invariants: identical candidates under deterministic test
actors must produce identical results; candidate order must not change
results or the ranking; per-branch seed material is code-owned,
reproducible, and distinct per candidate.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine counterfactual suite requires Python >= 3.12 (Concordia "
        "floor); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from cf_helpers import (MAX_STEPS, SEED, branch_signature,
                        fixture_model_factory, fixture_predicates,
                        fixture_status_rule, load_fixture_one)
from sworldmodel.counterfactuals import (derive_branch_seed,
                                         run_candidates_detailed)
from sworldmodel.outcomes import evaluate_branches, rank_branches


def _run(fx, candidates, capture=None):
    return run_candidates_detailed(
        fx.world, candidates,
        model_factory=fixture_model_factory(fx, capture=capture),
        seed=SEED, max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)


def _evaluate_and_rank(fx, results):
    evaluated = evaluate_branches(
        results, fixture_predicates(), evaluator_spec=fx.evaluator_spec,
        status_rule=fixture_status_rule, registry=fx.registry)
    recommendation = rank_branches(
        evaluated, fx.evaluator_spec, provenance_label="deterministic",
        registry=fx.registry)
    return evaluated, recommendation


def test_identical_candidates_twice_are_byte_identical():
    fx = load_fixture_one()
    first = _run(fx, fx.candidates)
    second = _run(fx, fx.candidates)

    assert first.base_plan_content_hash == second.base_plan_content_hash
    assert first.base_snapshot.content_hash() \
        == second.base_snapshot.content_hash()
    for result_a, result_b in zip(first.results, second.results):
        assert result_a.infrastructure_errors == ()
        assert branch_signature(result_a) == branch_signature(result_b), (
            f"branch {result_a.candidate_id} was not reproduced "
            "byte-identically")

    evaluated_a, rec_a = _evaluate_and_rank(fx, first.results)
    evaluated_b, rec_b = _evaluate_and_rank(fx, second.results)
    for result_a, result_b in zip(evaluated_a, evaluated_b):
        assert branch_signature(result_a) == branch_signature(result_b)
    assert rec_a.canonical_json() == rec_b.canonical_json()


def test_candidate_order_permutation_changes_nothing():
    fx = load_fixture_one()
    ordered = list(fx.candidates)
    permuted = [ordered[2], ordered[0], ordered[1]]

    run_ordered = _run(fx, ordered)
    run_permuted = _run(fx, permuted)

    # Same frozen base regardless of the candidate list.
    assert run_ordered.base_plan_content_hash \
        == run_permuted.base_plan_content_hash
    assert run_ordered.base_snapshot.content_hash() \
        == run_permuted.base_snapshot.content_hash()

    # Results follow the CALLER'S order (reporting order)...
    assert [result.candidate_id for result in run_ordered.results] \
        == [candidate.candidate_id for candidate in ordered]
    assert [result.candidate_id for result in run_permuted.results] \
        == [candidate.candidate_id for candidate in permuted]

    # ...but every per-candidate result is byte-identical either way.
    by_id_ordered = {result.candidate_id: result
                     for result in run_ordered.results}
    by_id_permuted = {result.candidate_id: result
                      for result in run_permuted.results}
    assert set(by_id_ordered) == set(by_id_permuted)
    for candidate_id, result in by_id_ordered.items():
        assert branch_signature(result) \
            == branch_signature(by_id_permuted[candidate_id]), (
            f"candidate order changed branch {candidate_id}")

    # And the ranking is identical from either input order.
    _evaluated_a, rec_a = _evaluate_and_rank(fx, run_ordered.results)
    _evaluated_b, rec_b = _evaluate_and_rank(fx, run_permuted.results)
    assert rec_a.canonical_json() == rec_b.canonical_json()


def test_per_branch_seed_material_is_distinct_and_reproducible():
    fx = load_fixture_one()
    candidate_ids = [candidate.candidate_id for candidate in fx.candidates]

    # Code-owned derivation: reproducible, distinct per candidate.
    seeds = {candidate_id: derive_branch_seed(SEED, candidate_id)
             for candidate_id in candidate_ids}
    assert len(set(seeds.values())) == len(seeds)
    for candidate_id in candidate_ids:
        assert derive_branch_seed(SEED, candidate_id) == seeds[candidate_id]

    # The manager hands exactly those seeds to the model factory, and the
    # same seeds again on a rerun.
    capture_a: dict = {}
    capture_b: dict = {}
    run_a = _run(fx, fx.candidates, capture=capture_a)
    run_b = _run(fx, fx.candidates, capture=capture_b)
    for candidate_id in candidate_ids:
        assert run_a.branch_seeds[candidate_id] == seeds[candidate_id]
        assert capture_a[candidate_id]["seed"] == seeds[candidate_id]
        assert capture_b[candidate_id]["seed"] == seeds[candidate_id]
    assert run_a.branch_seeds == run_b.branch_seeds

    # The recorded seed material in the frozen snapshot names the base
    # seed and the derivation rule.
    sidecar_rng = run_a.base_snapshot.sidecar.rng
    assert sidecar_rng["base_seed"] == SEED
    assert "sha256" in sidecar_rng["branch_seed_rule"]
