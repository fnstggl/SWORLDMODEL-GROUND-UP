"""Interventions that never reach the world must not produce a ranking.

Defect closed here (2026-08-04 under-the-hood validation, defect D2).
Two live runs ranked six branches each and both rankings were invalid for
the same reason: the candidate text never reached any actor except the
one it was handed to.  The engine's intervention boundary is deliberately
narrow -- the candidate is appended to the INSERTION actor's initial
observations and to nothing else -- so under a free-choice sender the
intervention propagates only if that actor's own model chooses to enact
it.  When it does not, every branch's recipient runs on byte-identical
context and the "differences" the metrics report are model sampling
variation on one prompt.  Nothing in the engine noticed; a confident
winner was published.

Proven in two layers:

- ``sworldmodel.counterfactuals.delivery`` computes, per branch and from
  that branch's OWN recorded artifacts, whether a distinctive fragment of
  the candidate reached a non-insertion actor -- including the
  distinctive-context refinement that stops shared compiler boilerplate
  from registering as delivery (the shared check over-reported 36 hits
  where 0 were real);
- ``sworldmodel.outcomes.ranking`` REFUSES to name a winner when every
  measured branch failed to deliver, ranks normally when some delivered,
  and carries the per-branch fact into the report either way.  A result
  set where delivery was never measured is not refused: an absent
  measurement is not a measured "no".
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine counterfactual suite requires Python >= 3.12 "
        "(Concordia floor); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from baseline_helpers import StrictScriptedModel, aware_rule
from cf_helpers import (MAX_STEPS, RECIPIENT_CTA, RECIPIENT_SILENT_TURN,
                        SEED, SENDER_CTA, SENDER_IDLE_TURN,
                        fixture_predicates, fixture_status_rule,
                        load_fixture_one, make_candidate)
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.counterfactuals.delivery import (
    METHOD, candidate_fragments, compute_intervention_delivery)
from sworldmodel.decision.contracts import (BranchResult,
                                            DELIVERY_DELIVERED,
                                            DELIVERY_NOT_COMPUTED,
                                            DELIVERY_NOT_DELIVERED,
                                            SCHEMA_VERSION,
                                            default_intervention_delivery,
                                            delivery_status)
from sworldmodel.outcomes import (InterventionNotDeliveredError,
                                  evaluate_branches, rank_branches)

#: a candidate long enough to fingerprint (the check needs >= 24-char runs)
DELIVERED_ACTION = ("Send the note asking for a fifteen-minute "
                    "conversation about the shared proposal.")
SILENT_ACTION = ("Send the considered note asking for a short "
                 "conversation about the shared proposal instead.")


# ---------------------------------------------------------------------------
# Unit: fragments and the distinctive-context refinement
# ---------------------------------------------------------------------------


def test_fragments_are_deterministic_and_length_bounded():
    fragments = candidate_fragments(
        "Short. " + DELIVERED_ACTION + "\n" + SILENT_ACTION)
    assert fragments == candidate_fragments(
        "Short. " + DELIVERED_ACTION + "\n" + SILENT_ACTION)
    assert "Short." not in fragments          # under the minimum length
    assert all(len(fragment) >= 24 for fragment in fragments)
    # longest first, ties lexicographic -- a fixed total order
    assert fragments == sorted(fragments, key=lambda p: (-len(p), p))


# ---------------------------------------------------------------------------
# End to end: one delivering branch and one silent branch
# ---------------------------------------------------------------------------


def _run_pair():
    """Two branches from one base: an ECHOING sender (the candidate text
    enters the committed world and reaches the recipient) and a
    CONTENT-BLIND sender (the candidate never leaves the insertion
    actor)."""
    fx = load_fixture_one()
    candidates = [make_candidate("user_001", DELIVERED_ACTION),
                  make_candidate("user_002", SILENT_ACTION)]

    def factory(candidate, branch_seed):
        del branch_seed
        if candidate.candidate_id == "user_001":
            sender = StrictScriptedModel(
                [(SENDER_CTA, [candidate.action, SENDER_IDLE_TURN])])
        else:
            sender = StrictScriptedModel(
                [(SENDER_CTA, [SENDER_IDLE_TURN, SENDER_IDLE_TURN])])
        recipient = StrictScriptedModel(
            [(RECIPIENT_CTA, [RECIPIENT_SILENT_TURN])])
        gm = StrictScriptedModel([aware_rule(["Alex", "Morgan"])])
        return {"sender": sender, "recipient": recipient}, gm

    run = run_candidates_detailed(
        fx.world, candidates, model_factory=factory, seed=SEED,
        max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)
    evaluated = evaluate_branches(
        run.results, fixture_predicates(),
        evaluator_spec=fx.evaluator_spec,
        status_rule=fixture_status_rule, registry=fx.registry)
    return fx, run, {result.candidate_id: result for result in evaluated}


def test_delivery_is_measured_per_branch_from_the_branch_itself():
    _fx, _run, results = _run_pair()

    delivered = results["user_001"].intervention_delivered
    assert delivered["status"] == DELIVERY_DELIVERED
    assert delivered["reason"] == "reached_non_insertion_actor"
    assert delivered["insertion_actor"] == "sender"
    assert delivered["reached_actors"] == ["recipient"]
    assert delivered["fragments_tested"] >= 1
    assert delivered["fragments_found"] >= 1
    assert delivered["reached_committed_world"] is True
    assert delivered["method"] == METHOD

    silent = results["user_002"].intervention_delivered
    assert silent["status"] == DELIVERY_NOT_DELIVERED
    assert silent["reason"] == "no_distinctive_fragment_reached_any_other_actor"
    assert silent["reached_actors"] == []
    assert silent["reached_committed_world"] is False
    # the silent branch's own insertion actor DID receive it (the boundary
    # works) -- the fact is about everyone else
    assert silent["insertion_actor"] == "sender"


def test_a_branch_result_carries_delivery_through_the_contract_gate():
    _fx, _run, results = _run_pair()
    for result in results.values():
        rebuilt = BranchResult.from_dict(result.to_dict())
        assert rebuilt.intervention_delivered \
            == result.intervention_delivered
        assert rebuilt == result


# ---------------------------------------------------------------------------
# Unit: the distinctive-context refinement (the 36-vs-0 over-report)
# ---------------------------------------------------------------------------


def test_boilerplate_already_in_the_world_does_not_count_as_delivery():
    """A candidate whose whole text is ALREADY in every actor's pre-run
    context cannot be evidence that the intervention propagated.

    Without this refinement the check finds the fragment in the
    recipient's own memory (it was seeded there before the run) and
    reports delivery that never happened -- the exact over-report the
    live harness measured, 36 reported and 0 real.
    """
    fx = load_fixture_one()
    shared = fx.world.shared_context.strip()
    assert len(shared) >= 24, "fixture must have fingerprintable context"
    candidate = make_candidate("user_001", shared)

    from sworldmodel.counterfactuals import build_base_plan
    from sworldmodel.counterfactuals.branch import apply_intervention
    base = build_base_plan(fx.world, fx.evaluator_spec, max_steps=MAX_STEPS)
    plan = apply_intervention(base, candidate)

    fact = compute_intervention_delivery(
        candidate=candidate, plan=plan,
        # the recipient's memory literally contains the shared context
        actor_memories={"sender": [shared], "recipient": [shared]},
        committed_events=[shared])
    assert fact["status"] == DELIVERY_NOT_COMPUTED
    assert fact["reason"] == "no_distinctive_candidate_fragments"
    assert fact["fragments_tested"] == 0


# ---------------------------------------------------------------------------
# Ranking: refuse when nothing was delivered
# ---------------------------------------------------------------------------


def _with_delivery(result, status, reason="synthetic"):
    fact = default_intervention_delivery()
    fact["status"] = status
    fact["reason"] = reason
    data = result.to_dict()
    data["intervention_delivered"] = fact
    return BranchResult.from_dict(data)


def test_ranking_refuses_when_no_measured_branch_delivered():
    fx, _run, results = _run_pair()
    undelivered = [_with_delivery(result, DELIVERY_NOT_DELIVERED,
                                  "no_distinctive_fragment_reached_any_"
                                  "other_actor")
                   for result in results.values()]
    with pytest.raises(InterventionNotDeliveredError) as excinfo:
        rank_branches(undelivered, fx.evaluator_spec,
                      provenance_label="deterministic",
                      registry=fx.registry)
    message = str(excinfo.value)
    # The refusal states the exact reason and names every measured branch.
    assert "refusing to rank" in message
    assert "2 measured branches" in message
    for candidate_id in ("user_001", "user_002"):
        assert candidate_id in message
    assert "independent variable" in message


def test_ranking_proceeds_and_discloses_when_some_branches_delivered():
    fx, _run, results = _run_pair()
    recommendation = rank_branches(
        list(results.values()), fx.evaluator_spec,
        provenance_label="deterministic", registry=fx.registry)
    assert recommendation.best_candidate_id in ("user_001", "user_002")
    status = recommendation.validation_status
    assert status["intervention_delivery_measured"] is True
    assert status["all_measured_branches_delivered_their_intervention"] \
        is False
    # per-branch fact carried into the report
    assert "intervention delivery: delivered" \
        in recommendation.downside_outcomes["user_001"]
    assert "intervention delivery: not_delivered" \
        in recommendation.downside_outcomes["user_002"]
    assert "Intervention delivery differs by branch" \
        in recommendation.run_limitations
    assert "not delivered by user_002" in recommendation.run_limitations


def test_ranking_is_not_refused_when_delivery_was_never_measured():
    """Backwards compatibility AND honesty: a result set carrying no
    measurement is ranked, with the absence disclosed -- never refused as
    if it had measured a 'no'."""
    fx, _run, results = _run_pair()
    unmeasured = [_with_delivery(result, DELIVERY_NOT_COMPUTED,
                                 "not_measured")
                  for result in results.values()]
    assert all(delivery_status(result) == DELIVERY_NOT_COMPUTED
               for result in unmeasured)
    recommendation = rank_branches(
        unmeasured, fx.evaluator_spec, provenance_label="deterministic",
        registry=fx.registry)
    assert recommendation.best_candidate_id
    assert recommendation.validation_status[
        "intervention_delivery_measured"] is False
    assert "delivery was not measured for any branch" \
        in recommendation.run_limitations


def test_every_branch_delivering_is_reported_as_such():
    fx, _run, results = _run_pair()
    delivered = [_with_delivery(result, DELIVERY_DELIVERED,
                                "reached_non_insertion_actor")
                 for result in results.values()]
    recommendation = rank_branches(
        delivered, fx.evaluator_spec, provenance_label="deterministic",
        registry=fx.registry)
    assert recommendation.validation_status[
        "all_measured_branches_delivered_their_intervention"] is True
    assert "Every branch's intervention was measured to reach an actor" \
        in recommendation.run_limitations


def test_a_result_predating_the_field_reads_as_not_computed():
    """Historical construction sites omit the field entirely; they must
    parse, default, and never trigger the refusal."""
    fx, _run, results = _run_pair()
    legacy_payloads = []
    for result in results.values():
        data = result.to_dict()
        del data["intervention_delivered"]
        del data["unresolved_observers"]
        legacy_payloads.append(BranchResult.from_dict(data))
    for legacy in legacy_payloads:
        assert legacy.intervention_delivered \
            == default_intervention_delivery()
        assert legacy.unresolved_observers == ()
        assert delivery_status(legacy) == DELIVERY_NOT_COMPUTED
    recommendation = rank_branches(
        legacy_payloads, fx.evaluator_spec,
        provenance_label="deterministic", registry=fx.registry)
    assert recommendation.best_candidate_id
    assert SCHEMA_VERSION == 1
