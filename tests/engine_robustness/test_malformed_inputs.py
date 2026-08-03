"""Malformed candidate / malformed compiled input at the RUN boundary
(OPERATIONAL_ROBUSTNESS_MATRIX rows 8-9).

The strict-parse contract suites (``tests/test_decision_contracts.py``),
the fixture loader, the adapter refusal suites
(``tests/engine_compilation``), and the generator malformed-output test
already refuse malformed material at construction time; these tests pin
the LAST line of defense -- the manager's pre-flight -- refusing
malformed requests that carry otherwise-well-formed objects, BEFORE any
branch executes and with every defect collected into one typed refusal.
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

from cf_helpers import MAX_STEPS, SEED, load_fixture_one, make_candidate
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.decision.contracts import ContractValidationError


def test_duplicate_candidate_ids_are_refused_before_any_branch_runs():
    """Matrix row 8: the same candidate id twice in one request is a
    typed ``duplicate_id`` refusal of the WHOLE call; the model factory
    is never invoked, so no branch ran for a half-valid request."""
    fx = load_fixture_one()
    twin_a = make_candidate("twin", "Send a brief note about the deadline.")
    twin_b = make_candidate("twin", "Send a different note entirely.")
    calls = []

    def counting_factory(candidate, branch_seed):
        calls.append(candidate.candidate_id)
        raise AssertionError("no branch may execute for a refused request")

    with pytest.raises(ContractValidationError) as excinfo:
        run_candidates_detailed(
            fx.world, [fx.candidates[0], twin_a, twin_b],
            model_factory=counting_factory, seed=SEED,
            max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
            registry=fx.registry)
    assert "duplicate_id" in excinfo.value.codes()
    assert calls == []


def test_malformed_world_and_candidate_objects_collect_one_refusal():
    """Matrix rows 8-9: a non-world object where the compiled world
    belongs plus a non-candidate object in the list surface as ONE
    collected typed refusal naming both fields -- never a partial run,
    never a silent None."""
    fx = load_fixture_one()

    def factory(candidate, branch_seed):  # pragma: no cover - refused
        raise AssertionError("unreachable")

    with pytest.raises(ContractValidationError) as excinfo:
        run_candidates_detailed(
            {"world_id": "not_a_world"}, [fx.candidates[0], object()],
            model_factory=factory, seed=SEED, max_steps=MAX_STEPS,
            evaluator_spec=fx.evaluator_spec)
    codes = excinfo.value.codes()
    paths = [issue.path for issue in excinfo.value.issues]
    assert "wrong_type" in codes
    assert "world" in paths
    assert "candidates[1]" in paths


def test_empty_candidate_list_and_bad_seed_are_typed_refusals():
    """Matrix row 8: an empty candidate list and a non-integer seed are
    each explicit typed refusals at the boundary (a boolean seed is
    refused too -- bool is not silently accepted as int)."""
    fx = load_fixture_one()

    def factory(candidate, branch_seed):  # pragma: no cover - refused
        raise AssertionError("unreachable")

    with pytest.raises(ContractValidationError) as excinfo:
        run_candidates_detailed(
            fx.world, [], model_factory=factory, seed=SEED,
            max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
            registry=fx.registry)
    assert "empty_collection" in excinfo.value.codes()

    for bad_seed in ("20260803", True):
        with pytest.raises(ContractValidationError) as excinfo:
            run_candidates_detailed(
                fx.world, [fx.candidates[0]], model_factory=factory,
                seed=bad_seed, max_steps=MAX_STEPS,
                evaluator_spec=fx.evaluator_spec, registry=fx.registry)
        assert "wrong_type" in excinfo.value.codes()
        assert any(issue.path == "seed" for issue in excinfo.value.issues)
