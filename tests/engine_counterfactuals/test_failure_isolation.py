"""Phase 6 failure isolation: a broken branch is reported, never hidden,
and never touches its siblings.

Directive hard invariant: branch failures must be reported rather than
silently replaced.  Contract rule R3: an engine stop without an evaluator
verdict is never an automatic failure -- the broken branch reports
``incomplete`` plus its recorded infrastructure errors.
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

from cf_helpers import (MAX_STEPS, SEED, branch_signature, load_fixture_one,
                        simple_model_factory)
from sworldmodel.counterfactuals import run_candidates_detailed

FAILING_ID = "concise_relevant"   # the MIDDLE candidate of the fixture


def _response_map(fx):
    return {
        candidate.candidate_id: (candidate.action,
                                 "Morgan takes note of the message.")
        for candidate in fx.candidates}


def test_mid_branch_model_failure_is_reported_and_isolated():
    fx = load_fixture_one()
    candidate_ids = [candidate.candidate_id for candidate in fx.candidates]
    assert candidate_ids[1] == FAILING_ID

    # Run A: three candidates, the middle one's RECIPIENT model raises
    # mid-branch (after the sender's turn already committed an event).
    run_with_failure = run_candidates_detailed(
        fx.world, fx.candidates,
        model_factory=simple_model_factory(
            _response_map(fx), raising={FAILING_ID}),
        seed=SEED, max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)

    # The failing branch is present IN ITS LIST POSITION -- reported,
    # never replaced or dropped.
    assert [result.candidate_id for result in run_with_failure.results] \
        == candidate_ids
    failed = run_with_failure.results[1]
    assert failed.candidate_id == FAILING_ID
    assert failed.terminal_status == "incomplete"
    assert len(failed.infrastructure_errors) == 1
    assert f"INJECTED_BRANCH_FAILURE_{FAILING_ID}" \
        in failed.infrastructure_errors[0]
    # Mid-branch: the partial trace up to the failure is preserved
    # (premise + the sender's committed turn; the failure hit on the
    # recipient's turn, step 2 of 2).
    assert len(failed.event_trace) == 2
    assert failed.terminal_world_state["steps_completed"] == 1

    # Siblings completed cleanly, unaffected.
    healthy = [run_with_failure.results[0], run_with_failure.results[2]]
    for result in healthy:
        assert result.infrastructure_errors == ()
        assert result.terminal_status == "cutoff"
        assert len(result.event_trace) == 3

    # Run B: the same run WITHOUT the failing candidate -- the siblings
    # are byte-identical, proving the failure leaked nothing into them.
    run_without = run_candidates_detailed(
        fx.world, [fx.candidates[0], fx.candidates[2]],
        model_factory=simple_model_factory(_response_map(fx)),
        seed=SEED, max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)
    for with_failure, without in zip(healthy, run_without.results):
        assert branch_signature(with_failure) == branch_signature(without)


def test_model_factory_exception_is_isolated_too():
    fx = load_fixture_one()
    clean_factory = simple_model_factory(_response_map(fx))

    def factory(candidate, branch_seed):
        if candidate.candidate_id == FAILING_ID:
            raise RuntimeError("FACTORY_FAILURE_BEFORE_MODELS")
        return clean_factory(candidate, branch_seed)

    run = run_candidates_detailed(
        fx.world, fx.candidates, model_factory=factory, seed=SEED,
        max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)

    failed = run.results[1]
    assert failed.candidate_id == FAILING_ID
    assert failed.terminal_status == "incomplete"
    assert "FACTORY_FAILURE_BEFORE_MODELS" \
        in failed.infrastructure_errors[0]
    assert failed.event_trace == ()          # nothing ran
    assert run.runner_records[FAILING_ID] is None

    reference = run_candidates_detailed(
        fx.world, [fx.candidates[0], fx.candidates[2]],
        model_factory=clean_factory, seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx.evaluator_spec, registry=fx.registry)
    assert branch_signature(run.results[0]) \
        == branch_signature(reference.results[0])
    assert branch_signature(run.results[2]) \
        == branch_signature(reference.results[1])
