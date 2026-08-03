"""THE Stage A gate: local and distributed runs are equivalent.

Directive ("AgentSociety integration sequence", Stage A): the stage
passes only when local and distributed runs return equivalent structured
results under deterministic test models, with Concordia's internal
runtime unchanged.  Proven here on frozen fixture 1 (individual_reply):

- the SAME serializable model spec drives both legs -- the local manager
  gets ``build_scripted_models(params)`` directly, the distributed
  executor ships ``{"model_builder": <dotted name>, "params": params}``
  and every Ray worker rebuilds the models from the spec -- so the
  comparison measures the execution substrate, not two model stacks;
- identical frozen-base identity: base plan content hash, per-candidate
  branch plan hashes, code-owned branch ids and per-branch seeds;
- per-candidate BranchResult signature equality (event trace, terminal
  status, terminal world state, infrastructure errors; token/runtime
  stats and artifact paths excluded -- see
  distributed_helpers.SIGNATURE_KEYS for the documented rule);
- guard-relevant evidence equality from the persisted runner records
  (guard_interventions ride runner_record.json per the recorded
  decision), and the guard never fired on either leg;
- the trace-reading evaluator + declared-metric ranking over the
  DISTRIBUTED results reproduce the fixture's expected_deterministic
  block, the measured winner, and the validation_status flags.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
                                 fixture_predicates, fixture_status_rule,
                                 load_fixture_one, model_spec,
                                 result_signature, scripted_params)
from distributed_model_specs import build_scripted_models
from sworldmodel.backends.agentsociety.branch_executor import \
    run_candidates_distributed
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.decision.validation import validate_semantics
from sworldmodel.outcomes import evaluate_branches, rank_branches

EXPECTED_WINNER = "concise_relevant"


def test_local_and_distributed_results_are_equivalent(distributed_engine,
                                                      tmp_path):
    params = scripted_params(load_fixture_one())

    # LOCAL leg: the Phase 6 manager, models built through the SAME
    # registered builder the workers use.
    fx_local = load_fixture_one()
    local = run_candidates_detailed(
        fx_local.world, fx_local.candidates,
        model_factory=build_scripted_models(params),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx_local.evaluator_spec,
        registry=fx_local.registry,
        model_config={"model_builder": MODEL_BUILDER_REF})

    # DISTRIBUTED leg: fresh fixture load (fresh registry), same seed,
    # same step budget, same spec params.
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

    # Frozen-base identity and code-owned derivations are identical.
    assert dist.base_plan_content_hash == local.base_plan_content_hash
    assert dist.branch_ids == local.branch_ids
    assert dist.branch_seeds == local.branch_seeds
    for candidate_id, plan in local.branch_plans.items():
        assert dist.branch_plans[candidate_id].content_hash() \
            == plan.content_hash(), candidate_id

    # Per-candidate BranchResult signature equality, in caller order.
    assert len(dist.results) == len(local.results) == 3
    signature_table = []
    for local_result, dist_result in zip(local.results, dist.results):
        assert local_result.candidate_id == dist_result.candidate_id
        assert dist_result.infrastructure_errors == ()
        local_signature = result_signature(local_result)
        dist_signature = result_signature(dist_result)
        signature_table.append(
            (dist_result.candidate_id, local_signature == dist_signature))
        assert local_signature == dist_signature, (
            f"{dist_result.candidate_id}: local and distributed "
            f"signatures diverge\nlocal: {local_signature}\n"
            f"distributed: {dist_signature}")
    assert [ok for _cid, ok in signature_table] == [True, True, True]

    # Guard-relevant evidence: the persisted runner records carry the
    # guard_interventions channel, equal to the local run's (and empty --
    # the Game Master wrote nothing on the recipient's behalf).
    for candidate_id in local.branch_ids:
        dist_record = dist.runner_records[candidate_id]
        assert dist_record is not None
        assert dist_record["guard_interventions"] \
            == local.runner_records[candidate_id]["guard_interventions"] \
            == []
        assert dist_record["worker_execution"]["pid"] > 0

    # Artifact paths were attached and point at real collected files.
    for dist_result in dist.results:
        names = sorted(Path(path).name for path in dist_result.artifact_paths)
        assert names == ["branch_result.json", "runner_record.json"]
        for path in dist_result.artifact_paths:
            assert Path(path).is_file(), path

    # Distributed accounting: exactly-once and bounded submission window.
    report = dist.execution_report
    assert report["exactly_once"] is True
    assert report["collected_candidate_ids"] \
        == [candidate.candidate_id for candidate in fx_dist.candidates]
    assert report["driver_max_in_flight"] <= 2
    assert report["parallelism_limit"] == 2
    assert (tmp_path / "run" / "execution_report.json").is_file()


def test_distributed_results_reproduce_fixture_one_measured_winner(
        distributed_engine, tmp_path):
    fx = load_fixture_one()
    dist = run_candidates_distributed(
        fx.world, fx.candidates,
        model_spec=model_spec(scripted_params(fx)),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx.evaluator_spec,
        registry=fx.registry,
        run_dir=tmp_path / "run",
        parallelism=2)

    evaluated = evaluate_branches(
        dist.results, fixture_predicates(),
        evaluator_spec=fx.evaluator_spec,
        status_rule=fixture_status_rule, registry=fx.registry)

    # Per-candidate outcomes == the fixture's expected_deterministic
    # block, exactly, INCLUDING the terminal-status mapping.
    expected = fx.expected_deterministic
    by_id = {result.candidate_id: result for result in evaluated}
    assert set(by_id) == set(expected.per_candidate)
    for candidate_id, expectations in expected.per_candidate.items():
        result = by_id[candidate_id]
        for name, expected_value in expectations.items():
            if name == "terminal_status":
                assert result.terminal_status == expected_value, (
                    f"{candidate_id}: terminal_status "
                    f"{result.terminal_status!r} != {expected_value!r}")
                continue
            metric = result.outcome_metrics[name]
            assert type(metric.value) is type(expected_value)
            assert metric.value == expected_value, (
                f"{candidate_id}.{name}: {metric.value!r} != "
                f"{expected_value!r}")
            assert metric.computed_from, f"{candidate_id}.{name}"

    # Ranking over the DISTRIBUTED results: the fixture's required
    # winner, MEASURED (declared-order secondary resolves the tie; no
    # lexicographic tie-break needed).
    recommendation = rank_branches(
        evaluated, fx.evaluator_spec, provenance_label="deterministic",
        registry=fx.registry)
    assert recommendation.best_candidate_id == expected.ranking_first \
        == EXPECTED_WINNER
    assert [entry.candidate_id for entry in recommendation.ranking] \
        == ["concise_relevant", "urgent_pressure", "long_generic"]
    assert recommendation.validation_status[
        "ranked_by_declared_metrics_in_declared_order"] is True
    assert "tie_break_candidate_id_lexicographic" \
        not in recommendation.validation_status
    validate_semantics(recommendation, fx.registry,
                       branch_results=evaluated,
                       evaluator_spec=fx.evaluator_spec)
