"""Phase 6 base isolation: one frozen base, branches differ ONLY at the
insertion boundary, and no branch can see another branch's material.

Directive hard invariants exercised here: all candidates begin from the
same base snapshot hash; only the intervention differs between candidate
branches; no branch may modify or retrieve another branch's state or
memories; the registry refuses identifier joins across worlds.
"""

from __future__ import annotations

import json
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

from cf_helpers import (MAX_STEPS, SEED, all_prompt_text, load_fixture_one,
                        make_candidate, simple_model_factory)
from sworldmodel.counterfactuals import (apply_intervention,
                                         build_base_plan, diff_plans,
                                         insertion_path_prefix,
                                         run_candidates_detailed)
from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            ContractValidationError,
                                            SIDECAR_COMPONENTS)

CANARY_A = "BRANCH_A_CANARY_7c31"
CANARY_B = "BRANCH_B_CANARY_92e4"


def _canary_candidates():
    return (
        make_candidate(
            "canary_probe_a",
            "Choose the first prepared option and include the marker "
            f"{CANARY_A} in the outgoing note."),
        make_candidate(
            "canary_probe_b",
            "Choose the second prepared option and include the marker "
            f"{CANARY_B} in the outgoing note."),
    )


def _canary_factory(capture):
    return simple_model_factory(
        {
            "canary_probe_a": (
                CANARY_A, f"Morgan acknowledges the note carrying {CANARY_A}."),
            "canary_probe_b": (
                CANARY_B, f"Morgan acknowledges the note carrying {CANARY_B}."),
        },
        capture=capture)


def test_single_base_plan_and_insertion_only_diffs():
    fx = load_fixture_one()
    factory = simple_model_factory({
        candidate.candidate_id: (candidate.action,
                                 "Morgan takes note of the message.")
        for candidate in fx.candidates})
    run = run_candidates_detailed(
        fx.world, fx.candidates, model_factory=factory,
        seed=SEED, max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)

    # ONE frozen base: the recorded hash is the plan's own content hash,
    # and rebuilding the base from the world alone reproduces it exactly
    # (the base depends on no candidate).
    assert run.base_plan_content_hash == run.base_plan.content_hash()
    rebuilt = build_base_plan(fx.world, fx.evaluator_spec,
                              max_steps=MAX_STEPS)
    assert rebuilt.content_hash() == run.base_plan_content_hash

    # The frozen snapshot records exactly that identity, and its manifest
    # lists exactly what is captured (checkpoint keys + sidecar).
    genesis = run.base_snapshot.concordia_checkpoint["genesis"]
    assert genesis["plan_content_sha256"] == run.base_plan_content_hash
    assert run.base_snapshot.world_id == fx.world.world_id
    expected_manifest = set(run.base_snapshot.concordia_checkpoint) \
        | set(SIDECAR_COMPONENTS)
    assert set(run.base_snapshot.snapshot_manifest) == expected_manifest

    # Every branch differs from the base ONLY under the insertion path:
    # exactly the appended observation of the branch's own candidate.
    prefix = insertion_path_prefix(run.base_plan)
    assert prefix == "initial_observations.sender"
    for candidate in fx.candidates:
        candidate_id = candidate.candidate_id
        branch_plan = run.branch_plans[candidate_id]
        changed = diff_plans(run.base_plan, branch_plan)
        assert changed == ("initial_observations.sender[1]",), (
            f"branch {candidate_id} changed unexpected paths: {changed}")
        added = branch_plan.initial_observations["sender"][-1]
        assert added == f"[2026-08-03T14:05:00Z] {candidate.action}"
        # The branch keeps the BASE plan identity; branch identity is the
        # registered branch_id.
        assert branch_plan.plan_id == run.base_plan.plan_id
        assert run.registry.branch_binding(
            run.branch_ids[candidate_id]) \
            == (fx.world.world_id, candidate_id)


def test_apply_intervention_refuses_wrong_owner_and_stray_changes():
    fx = load_fixture_one()
    base_plan = build_base_plan(fx.world, fx.evaluator_spec,
                                max_steps=MAX_STEPS)
    wrong_owner = make_candidate(
        "wrong_owner_probe",
        "Act through the receiving side instead of the declared owner.",
        owner="recipient")
    with pytest.raises(ContractValidationError) as excinfo:
        apply_intervention(base_plan, wrong_owner)
    assert "owner_mismatch" in excinfo.value.codes()

    out_of_window = make_candidate(
        "late_probe", "Act after the recorded window has closed.",
        timing="2026-09-01T00:00:00Z")
    with pytest.raises(ContractValidationError) as excinfo:
        apply_intervention(base_plan, out_of_window)
    assert "timing_out_of_range" in excinfo.value.codes()


def test_cross_branch_canary_never_reaches_a_sibling_branch():
    fx = load_fixture_one()
    candidates = _canary_candidates()
    capture: dict = {}
    run = run_candidates_detailed(
        fx.world, candidates, model_factory=_canary_factory(capture),
        seed=SEED, max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)
    results = {result.candidate_id: result for result in run.results}
    for result in run.results:
        assert result.infrastructure_errors == ()

    pairs = (("canary_probe_a", CANARY_A, "canary_probe_b", CANARY_B),
             ("canary_probe_b", CANARY_B, "canary_probe_a", CANARY_A))
    for own_id, own_canary, other_id, other_canary in pairs:
        own_models = capture[own_id]
        # Sanity: the canary genuinely entered its OWN branch end to end
        # (sender observation, recipient prompt, committed trace).
        assert own_canary in all_prompt_text(own_models["sender"])
        assert own_canary in all_prompt_text(own_models["recipient"])
        own_trace = json.dumps(
            [event.to_dict() for event in results[own_id].event_trace])
        assert own_canary in own_trace

        # Isolation: the OTHER branch's canary appears in NO prompt of
        # this branch's models, in NO memory, in NO trace, in NO plan.
        for role in ("sender", "recipient", "gm"):
            assert other_canary not in all_prompt_text(own_models[role]), (
                f"{other_id}'s canary leaked into {own_id}'s {role} prompts")
        record = run.runner_records[own_id]
        record_text = json.dumps({
            "actor_memories": record["actor_memories"],
            "gm_memory": record["gm_memory"],
            "committed_events": record["committed_events"],
        })
        assert other_canary not in record_text, (
            f"{other_id}'s canary leaked into {own_id}'s memories/trace")
        assert other_canary not in own_trace
        assert other_canary not in run.branch_plans[own_id].canonical_json()
        # The shared frozen base contains NEITHER canary.
        assert own_canary not in run.base_plan.canonical_json()


def test_registry_refuses_cross_world_branch_references():
    fx = load_fixture_one()
    other_world_data = fx.world.to_dict()
    other_world_data["world_id"] = "w_cross_world_probe"
    other_world = CompiledDecisionWorld.from_dict(other_world_data)

    def must_not_execute(candidate, branch_seed):
        raise AssertionError(
            "no branch may execute for a cross-world candidate")

    with pytest.raises(ContractValidationError) as excinfo:
        run_candidates_detailed(
            other_world, [fx.candidates[0]],
            model_factory=must_not_execute, seed=SEED,
            max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
            registry=fx.registry)
    assert "cross_branch_reference" in excinfo.value.codes()
