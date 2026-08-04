"""Planner determinism and mapping-rule contracts.

The planner is a pure stdlib function (no Concordia import), but this
module carries the same version gate as the rest of the baseline suite:
the engine environment is where the Phase 4 evidence is recorded, and the
system 3.11 product suite must skip this directory cleanly.

Proven here:
  1. same CompiledDecisionWorld (by VALUE, including a dict-round-tripped
     rebuild) -> byte-identical canonical plan JSON, stable content_hash,
     stable plan_id;
  2. ``run_limits['max_steps']`` is exactly the code-owned ARGUMENT, and
     the world's cutoff rides separately as run METADATA
     (``gm_config['cutoff_time']``): both present, different fields,
     different kinds -- changing the step budget never touches the cutoff
     and vice versa;
  3. the code-owned observation rules (shared context to every actor,
     ``visible_to`` filtering, declared event order, timestamp framing,
     end-trim boundary rule);
  4. evaluator-facing prose (world.success_criteria) never enters the
     plan; the evaluator spec rides as a passthrough;
  5. invalid inputs and unknown actor references are rejected with
     collected issues, never repaired.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine baseline requires Python >= 3.12 (evidence is recorded in "
        "the engine environment); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

from pathlib import Path

from sworldmodel.backends.concordia_local import planner
from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            ContractValidationError,
                                            ConcordiaInitializationPlan,
                                            EvaluatorSpec, SCHEMA_VERSION,
                                            canonical_time)
from sworldmodel.decision.fixture_loader import load_fixture_file

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_PATH = (REPO_ROOT / "tests" / "fixtures" / "best_action"
                / "individual_reply.yaml")


@pytest.fixture(scope="module")
def fixture_one():
    return load_fixture_file(str(FIXTURE_PATH))


EVENT_WORLD_DICT = {
    "contract_type": "compiled_decision_world",
    "schema_version": SCHEMA_VERSION,
    "world_id": "w_two_party_exchange",
    "actors": [
        {"actor_id": "first_party", "name": "Ada",
         "private_context": "Ada wants a decision this week.\n"},
        {"actor_id": "second_party", "name": "Bo",
         "private_context": "Bo prefers to defer decisions."},
    ],
    "shared_context": "Ada and Bo share one open request.  \n",
    "starting_events": [
        {"description": "A note visible only to Bo arrived. BO_ONLY\n",
         "visible_to": ["second_party"],
         "time": "2026-09-02T08:30:00Z"},
        {"description": "A group announcement was posted. GROUP_NOTE",
         "visible_to": ["first_party", "second_party"],
         "time": "2026-09-02T09:00:00Z"},
    ],
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

EVENT_WORLD_SPEC = EvaluatorSpec(primary_metric="recorded_decision",
                                 secondary_metrics=())


def test_same_world_gives_byte_identical_plan(fixture_one):
    plan_a = planner.build_initialization_plan(
        fixture_one.world, fixture_one.evaluator_spec, max_steps=7)
    plan_b = planner.build_initialization_plan(
        fixture_one.world, fixture_one.evaluator_spec, max_steps=7)
    assert plan_a.canonical_json() == plan_b.canonical_json()
    assert plan_a.content_hash() == plan_b.content_hash()
    assert plan_a.plan_id == plan_b.plan_id

    # Purity over VALUE, not object identity: a dict-round-tripped rebuild
    # of the same world yields the same plan bytes.
    rebuilt_world = CompiledDecisionWorld.from_dict(
        fixture_one.world.to_dict())
    plan_c = planner.build_initialization_plan(
        rebuilt_world, fixture_one.evaluator_spec, max_steps=7)
    assert plan_c.canonical_json() == plan_a.canonical_json()

    # And the plan itself round-trips its own strict schema gate.
    reparsed = ConcordiaInitializationPlan.from_dict(plan_a.to_dict())
    assert reparsed.canonical_json() == plan_a.canonical_json()


def test_max_steps_is_a_parameter_and_cutoff_is_metadata(fixture_one):
    plan = planner.build_initialization_plan(
        fixture_one.world, fixture_one.evaluator_spec, max_steps=5)

    # Both present...
    assert plan.run_limits["max_steps"] == 5
    assert plan.gm_config["cutoff_time"] == canonical_time(
        fixture_one.world.cutoff)
    assert plan.gm_config["start_time"] == canonical_time(
        fixture_one.world.start_time)

    # ...and distinct: an integer step budget vs an ISO-8601 wall-clock
    # instant; changing one never changes the other.
    assert type(plan.run_limits["max_steps"]) is int
    assert isinstance(plan.gm_config["cutoff_time"], str)
    assert str(plan.run_limits["max_steps"]) not in plan.gm_config[
        "cutoff_time"].replace("2026", "")  # no numeric coupling

    other = planner.build_initialization_plan(
        fixture_one.world, fixture_one.evaluator_spec, max_steps=9)
    assert other.run_limits["max_steps"] == 9
    assert other.gm_config["cutoff_time"] == plan.gm_config["cutoff_time"]
    # The budget is part of the plan identity.
    assert other.plan_id != plan.plan_id
    assert other.content_hash() != plan.content_hash()

    # The default is a code-owned constant, not derived from the horizon:
    # the fixture's window spans seven days, yet the default budget is the
    # module constant regardless of the window.
    default_plan = planner.build_initialization_plan(
        fixture_one.world, fixture_one.evaluator_spec)
    assert default_plan.run_limits["max_steps"] == planner.DEFAULT_MAX_STEPS


def test_observation_rules_visibility_order_and_framing():
    world = CompiledDecisionWorld.from_dict(EVENT_WORLD_DICT)
    plan = planner.build_initialization_plan(world, EVENT_WORLD_SPEC,
                                             max_steps=4)

    shared = "Ada and Bo share one open request."  # end-trimmed
    bo_only = "[2026-09-02T08:30:00Z] A note visible only to Bo arrived. BO_ONLY"
    group = "[2026-09-02T09:00:00Z] A group announcement was posted. GROUP_NOTE"

    # Shared context first for every actor; then the visible events in the
    # world's declared order with timestamp framing; end-trim applied.
    assert plan.initial_observations["first_party"] == (shared, group)
    assert plan.initial_observations["second_party"] == (shared, bo_only,
                                                         group)
    # The GM record carries EVERY starting event, in declared order.
    assert plan.gm_initial_events == (bo_only, group)
    # Private init data is end-trimmed, interior verbatim.
    by_id = {config.actor_id: config for config in plan.actor_configs}
    assert by_id["first_party"].private_init_data == (
        "Ada wants a decision this week.")
    assert plan.shared_init_data == shared
    # Declaration order of actors is preserved.
    assert tuple(config.actor_id for config in plan.actor_configs) == (
        "first_party", "second_party")


def test_evaluator_prose_never_enters_the_plan(fixture_one):
    plan = planner.build_initialization_plan(
        fixture_one.world, fixture_one.evaluator_spec, max_steps=4)
    plan_json = plan.canonical_json()
    # The loader-generated success_criteria prose stays OUT of the plan...
    assert fixture_one.world.success_criteria not in plan_json
    # ...while the evaluator spec rides as a structured passthrough.
    assert plan.evaluator_spec == fixture_one.evaluator_spec
    # And private context appears in actor_configs ONLY: not in the shared
    # data, the premise, the GM events, or any other actor's entry.
    for actor in fixture_one.world.actors:
        private = actor.private_context.strip()
        occurrences = plan_json.count(
            private.replace("\n", "\\n").replace('"', '\\"'))
        assert occurrences == 1, (
            f"private context of {actor.actor_id!r} must appear exactly "
            f"once (its own actor_config), found {occurrences}")


def test_rejections_are_collected_never_repaired(fixture_one):
    world = fixture_one.world
    spec = fixture_one.evaluator_spec

    with pytest.raises(ContractValidationError) as err:
        planner.build_initialization_plan(world, spec, max_steps=0)
    assert "invalid_value" in err.value.codes()

    with pytest.raises(ContractValidationError) as err:
        planner.build_initialization_plan(world, spec, max_steps="4")
    assert "invalid_value" in err.value.codes()

    with pytest.raises(ContractValidationError) as err:
        planner.build_initialization_plan(world, spec,
                                          acting_order="alphabetical")
    assert "invalid_enum" in err.value.codes()

    with pytest.raises(ContractValidationError) as err:
        planner.build_initialization_plan(world.to_dict(), spec)
    assert "wrong_type" in err.value.codes()

    with pytest.raises(ContractValidationError) as err:
        planner.build_initialization_plan(world, {"primary_metric": "x"})
    assert "wrong_type" in err.value.codes()

    # Multiple defects are collected in ONE error.
    with pytest.raises(ContractValidationError) as err:
        planner.build_initialization_plan(world.to_dict(), None,
                                          max_steps=-1,
                                          acting_order="alphabetical")
    assert len(err.value.issues) == 4


def test_unknown_insertion_actor_is_rejected_defensively():
    # Schema-valid but semantically broken world (Phase 3 semantic
    # validation would reject it; the planner re-checks and refuses).
    data = dict(EVENT_WORLD_DICT)
    data["intervention_insertion_point"] = {"actor_id": "ghost_party"}
    world = CompiledDecisionWorld.from_dict(data)
    with pytest.raises(ContractValidationError) as err:
        planner.build_initialization_plan(world, EVENT_WORLD_SPEC)
    assert "unknown_reference" in err.value.codes()
