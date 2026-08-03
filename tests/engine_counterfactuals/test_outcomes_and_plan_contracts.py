"""Engine-free contracts of the Phase 6 layers (both interpreters).

``sworldmodel/outcomes`` and the plan-level half of
``sworldmodel/counterfactuals`` are pure stdlib, so their contracts are
proven here WITHOUT the engine package and run in the system suite too:

- matcher predicates return cited readings (matches cite events, absence
  cites the recorded whole-trace bound);
- the evaluator rejects uncited metrics, unresolvable citations, missing
  predicates for declared metrics, and any success/failure verdict on a
  branch with recorded infrastructure errors; it never mutates its input;
- ranking is a deterministic total order on the declared primary metric
  with the disclosed candidate_id tie-break, and refuses unevaluated
  branches, duplicate candidates, and unknown provenance labels;
- branch construction appends exactly one intervention at the insertion
  boundary (loader -> planner path, no engine), and diff_plans pinpoints
  stray changes;
- per-branch seed and branch-id derivations are code-owned, distinct,
  and reproducible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sworldmodel.counterfactuals import (apply_intervention,
                                         build_base_plan, derive_branch_id,
                                         derive_branch_seed, diff_plans)
from sworldmodel.decision.contracts import (BranchResult,
                                            ConcordiaInitializationPlan,
                                            ContractValidationError,
                                            EvaluatorSpec, IssueCollector,
                                            REQUIRED_LIMITATION_PHRASE,
                                            SCHEMA_VERSION)
from sworldmodel.outcomes import (WHOLE_TRACE_CITATION, count_metric,
                                  evaluate_branch, exists_metric,
                                  rank_branches, substring_matcher)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_ONE = (REPO_ROOT / "tests" / "fixtures" / "best_action"
               / "individual_reply.yaml")

SPEC = EvaluatorSpec.parse(
    {"primary_metric": "marker_seen",
     "secondary_metrics": ["marker_count"]}, "spec", IssueCollector())


def _branch_result(candidate_id, trace_texts, *, errors=()):
    return BranchResult.from_dict({
        "contract_type": BranchResult.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "branch_id": f"br_unit_{candidate_id}",
        "candidate_id": candidate_id,
        "world_id": "w_unit_probe",
        "terminal_status": "cutoff",
        "terminal_world_state": {"committed_event_count": len(trace_texts)},
        "event_trace": [
            {"event_id": f"ev_{index:04d}", "description": text}
            for index, text in enumerate(trace_texts)],
        "outcome_metrics": {},
        "infrastructure_errors": list(errors),
        "token_stats": {},
        "runtime_stats": {},
        "artifact_paths": [],
    })


def _predicates():
    return {
        "marker_seen": exists_metric(substring_matcher("UNIT_MARKER")),
        "marker_count": count_metric(substring_matcher("UNIT_MARKER")),
    }


def test_matcher_predicates_cite_matches_and_absence():
    hit = _branch_result("cand_hit",
                         ["opening line", "carries UNIT_MARKER here",
                          "closing line", "UNIT_MARKER again"])
    result = evaluate_branch(hit, _predicates(), evaluator_spec=SPEC)
    assert result.outcome_metrics["marker_seen"].value is True
    assert result.outcome_metrics["marker_seen"].computed_from \
        == ("event:ev_0001", "event:ev_0003")
    assert result.outcome_metrics["marker_count"].value == 2

    miss = _branch_result("cand_miss", ["opening line", "closing line"])
    result = evaluate_branch(miss, _predicates(), evaluator_spec=SPEC)
    assert result.outcome_metrics["marker_seen"].value is False
    assert result.outcome_metrics["marker_seen"].computed_from \
        == (WHOLE_TRACE_CITATION,)
    # The input object was never mutated (a fresh result was returned).
    assert miss.outcome_metrics == {}


def test_evaluator_rejects_uncited_and_unresolvable_metrics():
    result = _branch_result("cand_a", ["only line"])
    with pytest.raises(ContractValidationError) as excinfo:
        evaluate_branch(result, {"marker_seen": lambda trace, rd: True,
                                 "marker_count": _predicates()[
                                     "marker_count"]},
                        evaluator_spec=SPEC)
    assert any("citations" in issue.message
               for issue in excinfo.value.issues)

    with pytest.raises(ContractValidationError) as excinfo:
        evaluate_branch(
            result,
            {"marker_seen": lambda trace, rd: (True, ["event:no_such"]),
             "marker_count": _predicates()["marker_count"]},
            evaluator_spec=SPEC)
    assert "unknown_reference" in excinfo.value.codes()

    with pytest.raises(ContractValidationError) as excinfo:
        evaluate_branch(result, {"marker_seen": _predicates()["marker_seen"]},
                        evaluator_spec=SPEC)
    assert "missing_field" in excinfo.value.codes()


def test_evaluator_status_rule_and_broken_branch_refusal():
    healthy = _branch_result("cand_a", ["carries UNIT_MARKER"])
    promoted = evaluate_branch(
        healthy, _predicates(), evaluator_spec=SPEC,
        status_rule=lambda metrics, default: (
            "success" if metrics["marker_seen"].value else None))
    assert promoted.terminal_status == "success"

    kept = evaluate_branch(
        _branch_result("cand_b", ["nothing here"]), _predicates(),
        evaluator_spec=SPEC,
        status_rule=lambda metrics, default: (
            "success" if metrics["marker_seen"].value else None))
    assert kept.terminal_status == "cutoff"

    broken = _branch_result("cand_c", ["carries UNIT_MARKER"],
                            errors=["injected infrastructure error"])
    with pytest.raises(ContractValidationError) as excinfo:
        evaluate_branch(broken, _predicates(), evaluator_spec=SPEC,
                        status_rule=lambda metrics, default: "success")
    assert "invalid_value" in excinfo.value.codes()


def test_ranking_declared_metric_order_and_refusals():
    evaluated = [
        evaluate_branch(_branch_result(candidate_id, texts), _predicates(),
                        evaluator_spec=SPEC)
        for candidate_id, texts in (
            ("cand_late", ["carries UNIT_MARKER"]),
            ("cand_early", ["carries UNIT_MARKER", "UNIT_MARKER again"]),
            ("cand_none", ["nothing"]),
        )]
    recommendation = rank_branches(evaluated, SPEC,
                                   provenance_label="deterministic")
    # Primary metric is True for cand_late and cand_early (a tie): the
    # DECLARED secondary metric resolves it, measured and descending
    # (marker_count 2 > 1) -- cand_early first, no tie-break involved.
    assert [entry.candidate_id for entry in recommendation.ranking] \
        == ["cand_early", "cand_late", "cand_none"]
    assert recommendation.best_candidate_id == "cand_early"
    assert REQUIRED_LIMITATION_PHRASE in recommendation.run_limitations
    assert "Result provenance: deterministic." \
        in recommendation.run_limitations
    assert "compared descending in declared order" \
        in recommendation.run_limitations
    assert "polarity not inferred" in recommendation.run_limitations
    assert "candidate_id in ascending lexicographic order" \
        in recommendation.run_limitations
    assert "not needed in this ranking" in recommendation.run_limitations
    # A fully measured ranking carries NO tie-break flag.
    assert "tie_break_candidate_id_lexicographic" \
        not in recommendation.validation_status
    assert recommendation.validation_status[
        "ranked_by_declared_metrics_in_declared_order"] is True
    assert recommendation.metric_differences["marker_seen"]["cand_none"] \
        == -1.0
    # The measured secondary tradeoff is reported, extremes annotated,
    # no polarity invented.
    assert "marker_count=0 (strict minimum among candidates tested)" \
        in recommendation.downside_outcomes["cand_none"]
    assert "marker_count=2 (strict maximum among candidates tested)" \
        in recommendation.downside_outcomes["cand_early"]

    with pytest.raises(ContractValidationError) as excinfo:
        rank_branches([_branch_result("cand_raw", ["text"])], SPEC,
                      provenance_label="deterministic")
    assert "missing_field" in excinfo.value.codes()

    with pytest.raises(ContractValidationError) as excinfo:
        rank_branches(evaluated + [evaluated[0]], SPEC,
                      provenance_label="deterministic")
    assert "duplicate_id" in excinfo.value.codes()

    with pytest.raises(ContractValidationError) as excinfo:
        rank_branches(evaluated, SPEC, provenance_label="guesswork")
    assert "invalid_enum" in excinfo.value.codes()


def test_ranking_secondary_metrics_apply_in_declared_order():
    """The FIRST declared secondary decides a primary tie even when a
    later secondary would reverse it: declaration order IS the user's
    stated priority, and no polarity or weight is invented."""
    spec = EvaluatorSpec.parse(
        {"primary_metric": "marker_seen",
         "secondary_metrics": ["alpha_count", "beta_count"]},
        "spec", IssueCollector())
    predicates = {
        "marker_seen": exists_metric(substring_matcher("UNIT_MARKER")),
        "alpha_count": count_metric(substring_matcher("ALPHA_MARKER")),
        "beta_count": count_metric(substring_matcher("BETA_MARKER")),
    }
    evaluated = [
        evaluate_branch(_branch_result(candidate_id, texts), predicates,
                        evaluator_spec=spec)
        for candidate_id, texts in (
            # alpha 2, beta 0
            ("cand_x", ["carries UNIT_MARKER", "ALPHA_MARKER one",
                        "ALPHA_MARKER two"]),
            # alpha 1, beta 5 -- beta would reverse the order if it
            # outranked the FIRST declared secondary
            ("cand_y", ["carries UNIT_MARKER", "ALPHA_MARKER one",
                        "BETA_MARKER 1", "BETA_MARKER 2", "BETA_MARKER 3",
                        "BETA_MARKER 4", "BETA_MARKER 5"]),
        )]
    recommendation = rank_branches(evaluated, spec,
                                   provenance_label="deterministic")
    assert [entry.candidate_id for entry in recommendation.ranking] \
        == ["cand_x", "cand_y"]
    assert "tie_break_candidate_id_lexicographic" \
        not in recommendation.validation_status


def test_ranking_final_candidate_id_tie_break_is_flagged():
    """ONLY when candidates tie on EVERY declared metric does the final
    code-owned candidate_id tie-break decide -- and then it is flagged
    in validation_status and disclosed as applied."""
    twins = [
        evaluate_branch(_branch_result(candidate_id,
                                       ["carries UNIT_MARKER"]),
                        _predicates(), evaluator_spec=SPEC)
        for candidate_id in ("cand_twin_b", "cand_twin_a")]
    recommendation = rank_branches(twins, SPEC,
                                   provenance_label="deterministic")
    assert [entry.candidate_id for entry in recommendation.ranking] \
        == ["cand_twin_a", "cand_twin_b"]
    assert recommendation.validation_status[
        "tie_break_candidate_id_lexicographic"] is True
    assert "applied in this ranking" in recommendation.run_limitations


def test_branch_plan_construction_without_engine():
    yaml = pytest.importorskip("yaml")
    del yaml
    from sworldmodel.decision.fixture_loader import load_fixture_file
    fx = load_fixture_file(str(FIXTURE_ONE))
    base = build_base_plan(fx.world, fx.evaluator_spec, max_steps=4)
    candidate = fx.candidates[1]
    branch = apply_intervention(base, candidate)
    changed = diff_plans(base, branch)
    assert changed == ("initial_observations.sender[1]",)
    assert branch.plan_id == base.plan_id
    assert branch.initial_observations["sender"][-1].endswith(
        candidate.action)
    # A tampered plan is pinpointed exactly.
    import copy
    data = copy.deepcopy(base.to_dict())
    data["neutral_premise"] += " tampered"
    tampered = ConcordiaInitializationPlan.from_dict(data)
    assert diff_plans(base, tampered) == ("neutral_premise",)


def test_seed_and_branch_id_derivations_are_code_owned():
    seed_a = derive_branch_seed(20260803, "cand_a")
    seed_b = derive_branch_seed(20260803, "cand_b")
    assert seed_a != seed_b
    assert derive_branch_seed(20260803, "cand_a") == seed_a
    assert derive_branch_seed(1, "cand_a") != seed_a

    branch_id = derive_branch_id("w_unit_probe", "cand_a")
    assert branch_id.startswith("br_") and len(branch_id) == 19
    assert derive_branch_id("w_unit_probe", "cand_a") == branch_id
    assert derive_branch_id("w_unit_probe", "cand_b") != branch_id
    with pytest.raises(ContractValidationError):
        derive_branch_id("Not A Slug", "cand_a")
    with pytest.raises(ContractValidationError):
        derive_branch_seed(True, "cand_a")
