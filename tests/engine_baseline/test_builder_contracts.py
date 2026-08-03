"""Builder contracts: the guard seam is wired, and nothing is defaulted
silently.

The Phase 2 contract suite proved the UPSTREAM seam (a final
``event_resolution_steps`` callable sees the fully-resolved candidate
event pre-commit and pre-observer).  This module proves OUR builder
actually wires that seam from the plan: identity occupies the final slot
by default (Phase 4), and an injected callable (the Phase 5 shape) runs
once per resolution and rewrites the committed event.

It also pins the builder's refusal behavior: unsupported settings,
missing models, roster inconsistencies, the upstream narrative-push step,
and an enabled observation fallback are ERRORS -- never silently
repaired, defaulted, or ignored.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine baseline requires Python >= 3.12 (Concordia floor); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from det import seeded_determinism  # tests/engine_contracts (via conftest)

from baseline_helpers import StrictScriptedModel, aware_rule
from sworldmodel.backends.concordia_local import builder, planner, runner
from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            ConcordiaInitializationPlan,
                                            EvaluatorSpec, SCHEMA_VERSION)

SEED = 13579

WORLD_DICT = {
    "contract_type": "compiled_decision_world",
    "schema_version": SCHEMA_VERSION,
    "world_id": "w_guard_probe",
    "actors": [
        {"actor_id": "first_party", "name": "Ada",
         "private_context": "Ada opens the exchange."},
        {"actor_id": "second_party", "name": "Bo",
         "private_context": "Bo answers briefly."},
    ],
    "shared_context": "Ada and Bo share one open request.",
    "starting_events": [],
    "start_time": "2026-09-02T08:00:00Z",
    "cutoff": "2026-09-04T18:00:00Z",
    "success_criteria": "A recorded_decision event appears in the trace.",
    "intervention_insertion_point": {"actor_id": "first_party"},
    "compiler_provenance": {
        "source": "manual_inline_test",
        "version": "inline_v1",
        "evidence_mode": "manual",
        "artifact_hashes": {},
    },
}
SPEC = EvaluatorSpec(primary_metric="recorded_decision",
                     secondary_metrics=())
MAX_STEPS = 2


def _plan(**kwargs):
    world = CompiledDecisionWorld.from_dict(WORLD_DICT)
    return planner.build_initialization_plan(world, SPEC,
                                             max_steps=MAX_STEPS, **kwargs)


def _models():
    return {
        "first_party": StrictScriptedModel(
            [("What does Ada do next?", ["opens with request REQ_1"])]),
        "second_party": StrictScriptedModel(
            [("What does Bo do next?", ["answers request REQ_1 with OK_1"])]),
        "gm": StrictScriptedModel([aware_rule(["Ada", "Bo"])]),
    }


def _actor_models(models):
    return {"first_party": models["first_party"],
            "second_party": models["second_party"]}


# ---------------------------------------------------------------------------
# Guard seam wiring
# ---------------------------------------------------------------------------


def test_identity_guard_occupies_final_slot_by_default():
    plan = _plan()
    assert plan.gm_config["guard_slot"] == "identity"
    models = _models()
    built = builder.build_branch(plan, actor_models=_actor_models(models),
                                 gm_model=models["gm"])
    assert built.guard_step is builder.identity_guard_step
    # And the identity function is what its name says.
    assert builder.identity_guard_step(None, "unchanged text", "Ada") == (
        "unchanged text")


def test_injected_guard_runs_once_per_resolution_and_rewrites_the_commit():
    plan = _plan()
    calls = []

    def recording_guard(document, event_statement, active_player_name):
        calls.append({"event": event_statement,
                      "active_player": active_player_name})
        return event_statement + " [SEAM_STAMP_77]"

    models = _models()
    with seeded_determinism(SEED):
        result = runner.run_branch(
            plan, actor_models=_actor_models(models),
            gm_model=models["gm"], guard_step=recording_guard)

    assert result["infrastructure_errors"] == []
    assert result["steps_completed"] == MAX_STEPS
    # One guard call per resolved step, with the active player attached.
    assert [call["active_player"] for call in calls] == ["Ada", "Bo"]
    assert "REQ_1" in calls[0]["event"]
    # The guard's return value is inside every committed turn event, and
    # observers received the stamped statement (notify runs post-chain).
    committed_turns = [row for row in result["committed_events"]
                       if "REQ_1" in row or "OK_1" in row]
    assert len(committed_turns) == 2
    assert all("[SEAM_STAMP_77]" in row for row in committed_turns)
    stamped_observations = [
        row for row in result["actor_memories"]["second_party"]
        if "[SEAM_STAMP_77]" in row]
    assert stamped_observations, (
        "observers must receive the guarded statement, not the raw one")


def test_guard_slot_mismatch_is_refused():
    plan = _plan()
    data = plan.to_dict()
    data["gm_config"]["guard_slot"] = "agency_guard_v1"
    modified = ConcordiaInitializationPlan.from_dict(data)
    models = _models()
    with pytest.raises(builder.PlanBuildError, match="guard slot"):
        builder.build_branch(modified, actor_models=_actor_models(models),
                             gm_model=models["gm"])


# ---------------------------------------------------------------------------
# No silent defaults, no silent repairs
# ---------------------------------------------------------------------------


def _modified_plan(**gm_config_overrides):
    data = _plan().to_dict()
    data["gm_config"].update(gm_config_overrides)
    return ConcordiaInitializationPlan.from_dict(data)


def test_narrative_push_step_is_refused_by_name():
    plan = _modified_plan(
        event_resolution_chain="maybe_inject_narrative_push")
    models = _models()
    with pytest.raises(builder.PlanBuildError, match="forbidden"):
        builder.build_branch(plan, actor_models=_actor_models(models),
                             gm_model=models["gm"])


def test_unknown_chain_step_is_an_error_not_ignored():
    plan = _modified_plan(event_resolution_chain="no_such_step_xyz")
    models = _models()
    with pytest.raises(builder.PlanBuildError, match="unknown"):
        builder.build_branch(plan, actor_models=_actor_models(models),
                             gm_model=models["gm"])


def test_enabled_observation_fallback_is_refused():
    plan = _modified_plan(observation_fallback=True)
    models = _models()
    with pytest.raises(builder.PlanBuildError, match="invent"):
        builder.build_branch(plan, actor_models=_actor_models(models),
                             gm_model=models["gm"])


def test_missing_actor_model_is_refused():
    plan = _plan()
    models = _models()
    with pytest.raises(builder.PlanBuildError, match="second_party"):
        builder.build_branch(
            plan, actor_models={"first_party": models["first_party"]},
            gm_model=models["gm"])


def test_missing_gm_model_is_refused():
    plan = _plan()
    models = _models()
    with pytest.raises(builder.PlanBuildError, match="gm_model"):
        builder.build_branch(plan, actor_models=_actor_models(models),
                             gm_model=None)


def test_roster_shared_setup_mismatch_is_refused():
    plan = _plan()
    data = plan.to_dict()
    roster = data["gm_config"]["component_roster"].split(",")
    roster.remove("shared_setup")
    data["gm_config"]["component_roster"] = ",".join(roster)
    modified = ConcordiaInitializationPlan.from_dict(data)
    models = _models()
    with pytest.raises(builder.PlanBuildError, match="shared_setup"):
        builder.build_branch(modified, actor_models=_actor_models(models),
                             gm_model=models["gm"])


def test_missing_required_roster_component_is_refused():
    plan = _plan()
    data = plan.to_dict()
    roster = data["gm_config"]["component_roster"].split(",")
    roster.remove("terminate")
    data["gm_config"]["component_roster"] = ",".join(roster)
    modified = ConcordiaInitializationPlan.from_dict(data)
    models = _models()
    with pytest.raises(builder.PlanBuildError, match="terminate"):
        builder.build_branch(modified, actor_models=_actor_models(models),
                             gm_model=models["gm"])


def test_non_plan_input_is_refused():
    models = _models()
    with pytest.raises(builder.PlanBuildError, match="instance"):
        builder.build_branch(_plan().to_dict(),
                             actor_models=_actor_models(models),
                             gm_model=models["gm"])


def test_unsupported_engine_and_missing_config_key_are_refused():
    plan = _modified_plan(engine="simultaneous")
    models = _models()
    with pytest.raises(builder.PlanBuildError, match="sequential"):
        builder.build_branch(plan, actor_models=_actor_models(models),
                             gm_model=models["gm"])

    data = _plan().to_dict()
    del data["gm_config"]["notify_observers"]
    stripped = ConcordiaInitializationPlan.from_dict(data)
    with pytest.raises(builder.PlanBuildError, match="notify_observers"):
        builder.build_branch(stripped, actor_models=_actor_models(models),
                             gm_model=models["gm"])
