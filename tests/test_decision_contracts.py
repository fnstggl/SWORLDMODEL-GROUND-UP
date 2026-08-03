"""Phase 3 directive battery for the fixed decision/branch contracts.

Every test is discriminating: valid acceptance, missing/unknown fields,
wrong types, invalid enums, fabricated IDs, cross-branch references,
unauthorized/mismatched decision owners, impossible timing, loss-less
round-trips with stable canonical hashes, schema-version fail-closed in
both directions, malformed LLM-style garbage with ALL errors listed,
valid-syntax-invalid-meaning, and one contract type supplied where another
was expected."""

import copy
import json

import pytest

from sworldmodel.decision import (
    BranchResult, CompiledDecisionWorld, ConcordiaInitializationPlan,
    ContractRegistry, ContractValidationError, DecisionProblem,
    EvaluatorSpec, InterventionCandidate, RecommendationResult,
    SimulationSnapshot, validate_schema, validate_semantics)

START = "2026-08-03T14:00:00Z"
MID = "2026-08-03T15:00:00Z"
CUT = "2026-08-10T14:00:00Z"
BEFORE_START = "2026-08-03T13:59:59Z"
AFTER_CUT = "2026-08-10T14:00:01Z"
HEX64 = "ab" * 32

LIMITATIONS = (
    "This run identifies the best-performing action among the candidates "
    "tested in this engineering simulation; result provenance: "
    "deterministic.")


# ---------------------------------------------------------------------------
# Valid builders (deep-copied per call so tests can mutate freely)
# ---------------------------------------------------------------------------

def world_dict(**over):
    data = {
        "contract_type": "compiled_decision_world",
        "schema_version": 1,
        "world_id": "w_0001",
        "actors": [
            {"actor_id": "actor_a", "name": "Avery",
             "private_context": "Wants a affirmative response."},
            {"actor_id": "actor_b", "name": "Blake",
             "private_context": "Responds only to short clear requests."},
        ],
        "shared_context": "Two people share one task.",
        "starting_events": [
            {"description": "A prior exchange occurred.",
             "visible_to": ["actor_a"], "time": MID},
        ],
        "start_time": START,
        "cutoff": CUT,
        "success_criteria":
            "The metric outcome_reached is computed from the trace.",
        "intervention_insertion_point": {"actor_id": "actor_a"},
        "compiler_provenance": {
            "source": "manual_fixture", "version": "v1",
            "evidence_mode": "manual_fixture",
            "artifact_hashes": {"content": HEX64},
        },
    }
    data.update(copy.deepcopy(over))
    return data


def candidate_dict(**over):
    data = {
        "contract_type": "intervention_candidate",
        "schema_version": 1,
        "candidate_id": "cand_one",
        "summary": "Take the direct approach.",
        "action": "Take the direct approach immediately.",
        "decision_owner": "actor_a",
        "timing": MID,
        "constraints": ["stay within the declared bounds"],
        "provenance": {"source": "user_supplied",
                       "generator_config_hash": ""},
    }
    data.update(copy.deepcopy(over))
    return data


def snapshot_dict(**over):
    data = {
        "contract_type": "simulation_snapshot",
        "schema_version": 1,
        "snapshot_id": "snap_0001",
        "world_id": "w_0001",
        "concordia_checkpoint": {
            "entities": {"actor_a": {"state": "..."}},
            "game_masters": {"main": {"state": "..."}},
            "raw_log": [],
            "checkpoint_counter": 0,
        },
        "sidecar": {
            "rng": {"seed": 7},
            "engine_cursor": {"steps_completed": 0,
                              "remaining_budget": 20,
                              "premise_delivered": False},
            "model_config": {"default": "scripted"},
            "compiler_artifact_hash": HEX64,
        },
        "snapshot_manifest": [
            "entities", "game_masters", "raw_log", "checkpoint_counter",
            "sidecar.rng", "sidecar.engine_cursor", "sidecar.model_config",
            "sidecar.compiler_artifact_hash",
        ],
    }
    data.update(copy.deepcopy(over))
    return data


def branch_dict(**over):
    data = {
        "contract_type": "branch_result",
        "schema_version": 1,
        "branch_id": "br_one",
        "candidate_id": "cand_one",
        "world_id": "w_0001",
        "terminal_status": "success",
        "terminal_world_state": {"outcome_reached": True},
        "event_trace": [
            {"event_id": "ev_1", "description": "actor_b responded."},
        ],
        "outcome_metrics": {
            "outcome_reached": {
                "value": True,
                "computed_from": ["event:ev_1", "state:outcome_reached"],
            },
        },
        "infrastructure_errors": [],
        "token_stats": {"prompt_tokens": 0},
        "runtime_stats": {"wall_seconds": 0.5},
        "artifact_paths": ["runs/br_one/trace.json"],
    }
    data.update(copy.deepcopy(over))
    return data


def reco_dict(**over):
    data = {
        "contract_type": "recommendation_result",
        "schema_version": 1,
        "best_candidate_id": "cand_one",
        "ranking": [
            {"candidate_id": "cand_one",
             "metric_values": {"outcome_reached": True}},
            {"candidate_id": "cand_two",
             "metric_values": {"outcome_reached": False}},
        ],
        "metric_differences": {
            "cand_one__vs__cand_two": {"outcome_reached": 1},
        },
        "downside_outcomes": {
            "cand_one": "No downside observed.",
            "cand_two": "No response arrived by the cutoff.",
        },
        "run_limitations": LIMITATIONS,
        "validation_status": {"schema": True, "semantics": True},
    }
    data.update(copy.deepcopy(over))
    return data


def problem_dict(**over):
    data = {
        "contract_type": "decision_problem",
        "schema_version": 1,
        "problem_id": "prob_0001",
        "decision_owner": "actor_a",
        "desired_outcome": "A affirmative response is obtained.",
        "success_criteria": "outcome_reached becomes true before cutoff",
        "constraints": ["respect the stated preferences"],
        "time_horizon": {"start": START, "cutoff": CUT},
        "relevant_context": "Background information.",
        "candidate_interventions": ["Take the direct approach."],
        "candidate_generation_permission": False,
    }
    data.update(copy.deepcopy(over))
    return data


def plan_dict(**over):
    data = {
        "contract_type": "concordia_initialization_plan",
        "schema_version": 1,
        "plan_id": "plan_0001",
        "world_id": "w_0001",
        "actor_configs": [
            {"actor_id": "actor_a", "name": "Avery",
             "private_init_data": "Wants a affirmative response."},
            {"actor_id": "actor_b", "name": "Blake",
             "private_init_data": "Responds only to short requests."},
        ],
        "shared_init_data": "Two people share one task.",
        "gm_config": {"engine": "sequential", "checks_enabled": True},
        "neutral_premise": "Two people begin an exchange.",
        "initial_observations": {"actor_a": ["The task begins."]},
        "gm_initial_events": ["The exchange begins."],
        "run_limits": {"max_steps": 20},
        "intervention_insertion": {"actor_id": "actor_a"},
        "evaluator_spec": {"primary_metric": "outcome_reached",
                           "secondary_metrics": ["response_received"]},
        "compiler_provenance": {
            "source": "manual_fixture", "version": "v1",
            "evidence_mode": "manual_fixture",
            "artifact_hashes": {"content": HEX64},
        },
    }
    data.update(copy.deepcopy(over))
    return data


ALL_CONTRACTS = [
    (DecisionProblem, problem_dict),
    (CompiledDecisionWorld, world_dict),
    (InterventionCandidate, candidate_dict),
    (SimulationSnapshot, snapshot_dict),
    (BranchResult, branch_dict),
    (RecommendationResult, reco_dict),
    (ConcordiaInitializationPlan, plan_dict),
]
IDS = [cls.CONTRACT_TYPE for cls, _ in ALL_CONTRACTS]


def err(fn, *args, **kwargs):
    with pytest.raises(ContractValidationError) as excinfo:
        fn(*args, **kwargs)
    return excinfo.value


def make_registry():
    registry = ContractRegistry()
    world = CompiledDecisionWorld.from_dict(world_dict())
    registry.register_world(world)
    cand_one = InterventionCandidate.from_dict(candidate_dict())
    cand_two = InterventionCandidate.from_dict(
        candidate_dict(candidate_id="cand_two"))
    registry.register_candidate(cand_one, world.world_id)
    registry.register_candidate(cand_two, world.world_id)
    registry.register_branch("br_one", world.world_id, "cand_one")
    registry.register_branch("br_two", world.world_id, "cand_two")
    return registry, world


# ---------------------------------------------------------------------------
# Valid acceptance and round-trips
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls,builder", ALL_CONTRACTS, ids=IDS)
def test_valid_object_accepted(cls, builder):
    obj = cls.from_dict(builder())
    assert obj.CONTRACT_TYPE == cls.CONTRACT_TYPE
    assert obj.to_dict()["contract_type"] == cls.CONTRACT_TYPE
    assert obj.to_dict()["schema_version"] == 1


@pytest.mark.parametrize("cls,builder", ALL_CONTRACTS, ids=IDS)
def test_round_trip_is_loss_less_and_hash_stable(cls, builder):
    obj = cls.from_dict(builder())
    again = cls.from_dict(obj.to_dict())
    assert again == obj
    # canonical serialization -> parse -> rebuild -> identical hash
    reparsed = cls.from_dict(json.loads(obj.canonical_json()))
    assert reparsed == obj
    assert reparsed.canonical_json() == obj.canonical_json()
    assert reparsed.content_hash() == obj.content_hash()
    assert len(obj.content_hash()) == 64


def test_canonical_json_is_sorted_and_compact():
    text = CompiledDecisionWorld.from_dict(world_dict()).canonical_json()
    assert ": " not in text and ", " not in text
    top_keys = list(json.loads(text))
    assert top_keys == sorted(top_keys)


def test_from_dict_never_mutates_the_input():
    data = branch_dict()
    frozen = copy.deepcopy(data)
    BranchResult.from_dict(data)
    assert data == frozen


def test_non_utc_offset_is_canonicalized_not_altered_in_meaning():
    data = world_dict(start_time="2026-08-03T16:00:00+02:00")
    world = CompiledDecisionWorld.from_dict(data)
    assert world.to_dict()["start_time"] == START
    assert world == CompiledDecisionWorld.from_dict(world.to_dict())


# ---------------------------------------------------------------------------
# Missing / unknown / wrong type / enum rejection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls,builder", ALL_CONTRACTS, ids=IDS)
def test_every_missing_required_field_is_rejected(cls, builder):
    for field in builder():
        data = builder()
        del data[field]
        exc = err(cls.from_dict, data)
        assert "missing_field" in exc.codes(), field
        assert any(field in path for path in exc.paths()), field


@pytest.mark.parametrize("cls,builder", ALL_CONTRACTS, ids=IDS)
def test_unknown_field_is_rejected(cls, builder):
    data = builder()
    data["unexpected_extra"] = 1
    exc = err(cls.from_dict, data)
    assert "unknown_field" in exc.codes()
    assert any("unexpected_extra" in path for path in exc.paths())


def test_unknown_nested_field_is_rejected():
    data = world_dict()
    data["actors"][0]["mood"] = "hopeful"
    exc = err(CompiledDecisionWorld.from_dict, data)
    assert "unknown_field" in exc.codes()
    assert any("actors[0].mood" in path for path in exc.paths())


@pytest.mark.parametrize("cls,builder,field,bad", [
    (CompiledDecisionWorld, world_dict, "actors", "not_a_list"),
    (CompiledDecisionWorld, world_dict, "shared_context", 3),
    (InterventionCandidate, candidate_dict, "constraints", "solo"),
    (SimulationSnapshot, snapshot_dict, "concordia_checkpoint", []),
    (BranchResult, branch_dict, "event_trace", {}),
    (RecommendationResult, reco_dict, "ranking", 3),
    (DecisionProblem, problem_dict, "time_horizon", START),
    (ConcordiaInitializationPlan, plan_dict, "run_limits", []),
], ids=str)
def test_wrong_type_is_rejected(cls, builder, field, bad):
    exc = err(cls.from_dict, builder(**{field: bad}))
    assert "wrong_type" in exc.codes()
    assert any(field in path for path in exc.paths())


def test_boolean_is_not_silently_coerced_to_integer():
    exc = err(BranchResult.from_dict,
              branch_dict(token_stats={"prompt_tokens": True}))
    assert "wrong_type" in exc.codes()


def test_integer_is_not_silently_coerced_to_boolean():
    exc = err(DecisionProblem.from_dict,
              problem_dict(candidate_generation_permission=1))
    assert "wrong_type" in exc.codes()


def test_invalid_terminal_status_enum_is_rejected():
    exc = err(BranchResult.from_dict, branch_dict(terminal_status="vibes"))
    assert "invalid_enum" in exc.codes()
    assert any("terminal_status" in path for path in exc.paths())


def test_invalid_candidate_source_enum_is_rejected():
    exc = err(InterventionCandidate.from_dict, candidate_dict(
        provenance={"source": "invented", "generator_config_hash": ""}))
    assert "invalid_enum" in exc.codes()


def test_generated_candidate_requires_generator_hash():
    exc = err(InterventionCandidate.from_dict, candidate_dict(
        provenance={"source": "generated", "generator_config_hash": ""}))
    assert "invalid_value" in exc.codes()


def test_malformed_identifier_is_rejected():
    exc = err(CompiledDecisionWorld.from_dict, world_dict(world_id="W 1!"))
    assert "invalid_id" in exc.codes()


def test_duplicate_actor_ids_and_names_are_rejected():
    data = world_dict()
    data["actors"].append({"actor_id": "actor_a", "name": "Avery",
                           "private_context": "A duplicate."})
    exc = err(CompiledDecisionWorld.from_dict, data)
    assert exc.codes().count("duplicate_id") == 2


def test_snapshot_checkpoint_requires_engine_keys():
    data = snapshot_dict()
    del data["concordia_checkpoint"]["game_masters"]
    exc = err(SimulationSnapshot.from_dict, data)
    assert "missing_field" in exc.codes()
    assert any("game_masters" in path for path in exc.paths())


def test_snapshot_artifact_hash_shape_is_enforced():
    data = snapshot_dict()
    data["sidecar"]["compiler_artifact_hash"] = "abc123"
    exc = err(SimulationSnapshot.from_dict, data)
    assert "invalid_value" in exc.codes()


def test_snapshot_rng_must_not_be_empty():
    data = snapshot_dict()
    data["sidecar"]["rng"] = {}
    exc = err(SimulationSnapshot.from_dict, data)
    assert "empty_collection" in exc.codes()


def test_metric_reference_shape_is_enforced_at_schema_level():
    data = branch_dict()
    data["outcome_metrics"]["outcome_reached"]["computed_from"] = ["vibes"]
    exc = err(BranchResult.from_dict, data)
    assert "invalid_value" in exc.codes()


def test_metric_must_cite_at_least_one_reference():
    data = branch_dict()
    data["outcome_metrics"]["outcome_reached"]["computed_from"] = []
    exc = err(BranchResult.from_dict, data)
    assert "empty_collection" in exc.codes()


def test_evaluator_secondary_must_not_repeat_primary():
    data = plan_dict()
    data["evaluator_spec"]["secondary_metrics"] = ["outcome_reached"]
    exc = err(ConcordiaInitializationPlan.from_dict, data)
    assert "duplicate_id" in exc.codes()


# ---------------------------------------------------------------------------
# Datetime and timing rules
# ---------------------------------------------------------------------------

def test_naive_datetime_is_rejected():
    exc = err(CompiledDecisionWorld.from_dict,
              world_dict(start_time="2026-08-03T14:00:00"))
    assert "naive_datetime" in exc.codes()


def test_malformed_datetime_is_rejected():
    exc = err(InterventionCandidate.from_dict,
              candidate_dict(timing="soon after lunch"))
    assert "invalid_datetime" in exc.codes()


def test_world_cutoff_must_be_strictly_after_start():
    exc = err(CompiledDecisionWorld.from_dict, world_dict(cutoff=START))
    assert "invalid_value" in exc.codes()
    assert any("cutoff" in path for path in exc.paths())


def test_problem_horizon_cutoff_before_start_is_rejected():
    exc = err(DecisionProblem.from_dict, problem_dict(
        time_horizon={"start": CUT, "cutoff": START}))
    assert "invalid_value" in exc.codes()


# ---------------------------------------------------------------------------
# Version gate: fail closed in BOTH directions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls,builder", ALL_CONTRACTS, ids=IDS)
@pytest.mark.parametrize("version,direction", [(0, "OLDER"), (99, "NEWER")])
def test_schema_version_mismatch_fails_closed(cls, builder, version,
                                              direction):
    exc = err(cls.from_dict, builder(schema_version=version))
    assert "version_mismatch" in exc.codes()
    message = str(exc)
    assert direction in message and "refusing" in message


def test_schema_version_boolean_is_rejected():
    exc = err(BranchResult.from_dict, branch_dict(schema_version=True))
    assert "wrong_type" in exc.codes()


# ---------------------------------------------------------------------------
# Wrong contract type supplied where another is expected
# ---------------------------------------------------------------------------

def test_wrong_contract_type_supplied_is_rejected():
    exc = err(InterventionCandidate.from_dict, world_dict())
    assert "wrong_contract_type" in exc.codes()
    assert "compiled_decision_world" in str(exc)


def test_validate_schema_enforces_expected_class():
    exc = err(validate_schema, world_dict(), InterventionCandidate)
    assert "wrong_contract_type" in exc.codes()


def test_validate_schema_dispatches_on_contract_type():
    obj = validate_schema(world_dict())
    assert isinstance(obj, CompiledDecisionWorld)
    obj = validate_schema(branch_dict(), "branch_result")
    assert isinstance(obj, BranchResult)


def test_validate_schema_rejects_unknown_contract_type():
    exc = err(validate_schema, {"contract_type": "mystery_contract"})
    assert "wrong_contract_type" in exc.codes()


def test_validate_schema_rejects_non_mapping():
    exc = err(validate_schema, "not a mapping")
    assert "wrong_type" in exc.codes()


# ---------------------------------------------------------------------------
# Malformed LLM output: every error listed, nothing repaired
# ---------------------------------------------------------------------------

def test_malformed_llm_garbage_reports_all_errors():
    garbage = {
        "contract_type": "branch_result",
        "schema_version": 1,
        "branch_id": 42,                      # wrong type
        "candidate_id": ["cand_one"],         # wrong type
        "terminal_status": "victorious",      # invalid enum
        "helpful_extra_field": "trust me",    # unknown field
        "confidence": 0.99,                   # unknown field
        # world_id, terminal_world_state, event_trace, outcome_metrics,
        # infrastructure_errors, token_stats, runtime_stats,
        # artifact_paths all missing
    }
    exc = err(BranchResult.from_dict, garbage)
    codes = set(exc.codes())
    assert {"wrong_type", "invalid_enum", "unknown_field",
            "missing_field"} <= codes
    assert len(exc.issues) >= 10
    for issue in exc.issues:
        assert issue.path and issue.code and issue.message


def test_issue_objects_carry_path_code_and_message():
    exc = err(CompiledDecisionWorld.from_dict, world_dict(world_id=7))
    issue = next(i for i in exc.issues if i.code == "wrong_type")
    assert issue.path == "world_id"
    assert "world_id" in str(exc) and "wrong_type" in str(exc)


# ---------------------------------------------------------------------------
# Registry: code-owned identifiers only
# ---------------------------------------------------------------------------

def test_registry_registration_and_lookup():
    registry, world = make_registry()
    assert registry.has_world("w_0001")
    assert registry.has_candidate("cand_one")
    assert registry.has_branch("br_one")
    assert registry.branch_binding("br_one") == ("w_0001", "cand_one")
    assert registry.world_insertion_actor("w_0001") == "actor_a"
    assert registry.has_actor("w_0001", "actor_b")
    assert not registry.has_actor("w_0001", "actor_ghost")


def test_registry_rejects_duplicate_registration():
    registry, world = make_registry()
    exc = err(registry.register_world, world)
    assert "duplicate_id" in exc.codes()
    exc = err(registry.register_candidate,
              InterventionCandidate.from_dict(candidate_dict()), "w_0001")
    assert "duplicate_id" in exc.codes()
    exc = err(registry.register_branch, "br_one", "w_0001", "cand_one")
    assert "duplicate_id" in exc.codes()


def test_registry_rejects_unregistered_references():
    registry, _ = make_registry()
    exc = err(registry.register_candidate,
              InterventionCandidate.from_dict(
                  candidate_dict(candidate_id="cand_new")), "w_ghost")
    assert "unregistered_id" in exc.codes()
    exc = err(registry.register_branch, "br_new", "w_0001", "cand_ghost")
    assert "unregistered_id" in exc.codes()
    exc = err(registry.register_branch, "Bad Branch!", "w_0001", "cand_one")
    assert "invalid_id" in exc.codes()


def test_registry_rejects_cross_world_branch_binding():
    registry, _ = make_registry()
    other = CompiledDecisionWorld.from_dict(world_dict(world_id="w_0002"))
    registry.register_world(other)
    registry.register_candidate(InterventionCandidate.from_dict(
        candidate_dict(candidate_id="cand_other")), "w_0002")
    exc = err(registry.register_branch, "br_mix", "w_0001", "cand_other")
    assert "cross_branch_reference" in exc.codes()


# ---------------------------------------------------------------------------
# Semantic validation: fabricated IDs, cross-branch, ownership, timing
# ---------------------------------------------------------------------------

def test_fabricated_candidate_id_is_rejected():
    registry, _ = make_registry()
    result = BranchResult.from_dict(branch_dict(candidate_id="cand_ghost"))
    exc = err(validate_semantics, result, registry)
    assert "unregistered_id" in exc.codes()


def test_fabricated_branch_and_world_ids_are_rejected():
    registry, _ = make_registry()
    result = BranchResult.from_dict(
        branch_dict(branch_id="br_ghost", world_id="w_ghost"))
    exc = err(validate_semantics, result, registry)
    codes = exc.codes()
    assert codes.count("unregistered_id") >= 2


def test_cross_branch_reference_is_rejected():
    registry, _ = make_registry()
    # br_one is bound to cand_one; citing it with cand_two is cross-branch
    result = BranchResult.from_dict(branch_dict(candidate_id="cand_two"))
    exc = err(validate_semantics, result, registry)
    assert "cross_branch_reference" in exc.codes()


def test_candidate_of_another_world_is_rejected():
    registry, _ = make_registry()
    other = CompiledDecisionWorld.from_dict(world_dict(world_id="w_0002"))
    registry.register_world(other)
    registry.register_candidate(InterventionCandidate.from_dict(
        candidate_dict(candidate_id="cand_other")), "w_0002")
    result = BranchResult.from_dict(branch_dict(candidate_id="cand_other"))
    exc = err(validate_semantics, result, registry)
    assert "cross_branch_reference" in exc.codes()


def test_branch_semantics_requires_a_registry():
    result = BranchResult.from_dict(branch_dict())
    exc = err(validate_semantics, result, None)
    assert "unregistered_id" in exc.codes()


def test_valid_branch_result_passes_semantics():
    registry, _ = make_registry()
    validate_semantics(BranchResult.from_dict(branch_dict()), registry)


def test_metric_citing_unrecorded_event_or_state_is_rejected():
    registry, _ = make_registry()
    data = branch_dict()
    data["outcome_metrics"]["outcome_reached"]["computed_from"] = [
        "event:ev_ghost", "state:missing_key"]
    exc = err(validate_semantics, BranchResult.from_dict(data), registry)
    assert exc.codes().count("unknown_reference") == 2


def test_mismatched_decision_owner_is_rejected():
    registry, world = make_registry()
    candidate = InterventionCandidate.from_dict(
        candidate_dict(candidate_id="cand_new", decision_owner="actor_b"))
    exc = err(validate_semantics, candidate, registry,
              world_id=world.world_id)
    assert "owner_mismatch" in exc.codes()


def test_unknown_decision_owner_is_rejected():
    registry, world = make_registry()
    candidate = InterventionCandidate.from_dict(
        candidate_dict(candidate_id="cand_new",
                       decision_owner="actor_ghost"))
    exc = err(validate_semantics, candidate, registry,
              world_id=world.world_id)
    assert "unknown_reference" in exc.codes()


@pytest.mark.parametrize("timing", [BEFORE_START, AFTER_CUT])
def test_candidate_timing_outside_horizon_is_rejected(timing):
    registry, world = make_registry()
    candidate = InterventionCandidate.from_dict(
        candidate_dict(candidate_id="cand_new", timing=timing))
    exc = err(validate_semantics, candidate, registry,
              world_id=world.world_id)
    assert "timing_out_of_range" in exc.codes()


@pytest.mark.parametrize("timing", [START, CUT])
def test_candidate_timing_at_window_bounds_is_accepted(timing):
    registry, world = make_registry()
    candidate = InterventionCandidate.from_dict(
        candidate_dict(candidate_id="cand_new", timing=timing))
    validate_semantics(candidate, registry, world_id=world.world_id)


def test_constraint_hook_violations_are_reported():
    registry, world = make_registry()
    candidate = InterventionCandidate.from_dict(
        candidate_dict(candidate_id="cand_new"))
    exc = err(validate_semantics, candidate, registry,
              world_id=world.world_id,
              constraint_hook=lambda c: ["breaks a declared bound"])
    assert "constraint_violation" in exc.codes()


# ---------------------------------------------------------------------------
# Valid syntax, invalid meaning
# ---------------------------------------------------------------------------

def test_world_with_unknown_visibility_reference_fails_semantics_only():
    data = world_dict()
    data["starting_events"][0]["visible_to"] = ["actor_ghost"]
    world = CompiledDecisionWorld.from_dict(data)  # schema passes
    exc = err(validate_semantics, world, None)
    assert "unknown_reference" in exc.codes()


def test_world_event_time_outside_window_fails_semantics():
    data = world_dict()
    data["starting_events"][0]["time"] = AFTER_CUT
    world = CompiledDecisionWorld.from_dict(data)
    exc = err(validate_semantics, world, None)
    assert "timing_out_of_range" in exc.codes()


def test_world_insertion_actor_must_be_declared():
    world = CompiledDecisionWorld.from_dict(world_dict(
        intervention_insertion_point={"actor_id": "actor_ghost"}))
    exc = err(validate_semantics, world, None)
    assert "unknown_reference" in exc.codes()


def test_blank_success_criteria_fails_semantics():
    world = CompiledDecisionWorld.from_dict(
        world_dict(success_criteria="   ??? "))
    exc = err(validate_semantics, world, None)
    assert "invalid_value" in exc.codes()


def test_snapshot_manifest_must_match_serialized_components():
    registry, _ = make_registry()
    incomplete = snapshot_dict()
    incomplete["snapshot_manifest"].remove("sidecar.rng")
    exc = err(validate_semantics,
              SimulationSnapshot.from_dict(incomplete), registry)
    assert "manifest_incomplete" in exc.codes()
    padded = snapshot_dict()
    padded["snapshot_manifest"].append("phantom_component")
    exc = err(validate_semantics,
              SimulationSnapshot.from_dict(padded), registry)
    assert "unknown_reference" in exc.codes()


def test_valid_snapshot_passes_semantics():
    registry, _ = make_registry()
    validate_semantics(SimulationSnapshot.from_dict(snapshot_dict()),
                       registry)


def test_plan_semantics_reject_unknown_actor_references():
    plan = ConcordiaInitializationPlan.from_dict(plan_dict(
        initial_observations={"actor_ghost": ["Sees the start."]},
        intervention_insertion={"actor_id": "actor_ghost"}))
    exc = err(validate_semantics, plan, None)
    assert exc.codes().count("unknown_reference") == 2


def test_problem_owner_resolution_against_world():
    registry, world = make_registry()
    named = DecisionProblem.from_dict(problem_dict(decision_owner="Avery"))
    validate_semantics(named, registry, world_id=world.world_id)
    ghost = DecisionProblem.from_dict(problem_dict(decision_owner="Nobody"))
    exc = err(validate_semantics, ghost, registry, world_id=world.world_id)
    assert "unknown_reference" in exc.codes()


# ---------------------------------------------------------------------------
# RecommendationResult rules
# ---------------------------------------------------------------------------

def test_run_limitations_requires_fixed_phrase():
    exc = err(RecommendationResult.from_dict, reco_dict(
        run_limitations="deterministic run; everything went fine."))
    assert "missing_phrase" in exc.codes()


def test_run_limitations_requires_provenance_label():
    exc = err(RecommendationResult.from_dict, reco_dict(
        run_limitations="This identifies the best-performing action among "
                        "the candidates tested in this simulation."))
    assert "missing_phrase" in exc.codes()


def test_provenance_label_must_be_a_whole_token():
    exc = err(RecommendationResult.from_dict, reco_dict(
        run_limitations="The best-performing action among the candidates "
                        "tested was found deterministically."))
    assert "missing_phrase" in exc.codes()


def test_best_candidate_must_equal_ranking_head():
    registry, _ = make_registry()
    reco = RecommendationResult.from_dict(
        reco_dict(best_candidate_id="cand_two"))
    exc = err(validate_semantics, reco, registry)
    assert "inconsistent_ranking" in exc.codes()


def test_recommendation_with_fabricated_candidate_is_rejected():
    registry, _ = make_registry()
    data = reco_dict()
    data["ranking"][1]["candidate_id"] = "cand_ghost"
    data["downside_outcomes"] = {"cand_one": "None observed."}
    exc = err(validate_semantics,
              RecommendationResult.from_dict(data), registry)
    assert "unregistered_id" in exc.codes()


def branch_results_pair():
    one = BranchResult.from_dict(branch_dict())
    two_data = branch_dict(branch_id="br_two", candidate_id="cand_two",
                           terminal_status="cutoff")
    two_data["outcome_metrics"]["outcome_reached"]["value"] = False
    two_data["terminal_world_state"] = {"outcome_reached": False}
    two = BranchResult.from_dict(two_data)
    return one, two


def test_recommendation_consistent_with_branch_results_passes():
    registry, _ = make_registry()
    reco = RecommendationResult.from_dict(reco_dict())
    validate_semantics(reco, registry,
                       branch_results=branch_results_pair(),
                       evaluator_spec=EvaluatorSpec(
                           primary_metric="outcome_reached",
                           secondary_metrics=()))


def test_recommendation_value_mismatch_with_branch_results_is_rejected():
    registry, _ = make_registry()
    data = reco_dict()
    data["ranking"][1]["metric_values"]["outcome_reached"] = True  # lie
    exc = err(validate_semantics, RecommendationResult.from_dict(data),
              registry, branch_results=branch_results_pair())
    assert "inconsistent_ranking" in exc.codes()


def test_recommendation_candidate_set_mismatch_is_rejected():
    registry, _ = make_registry()
    one, _two = branch_results_pair()
    exc = err(validate_semantics,
              RecommendationResult.from_dict(reco_dict()), registry,
              branch_results=[one])
    assert "inconsistent_ranking" in exc.codes()


def test_ranking_must_follow_declared_primary_metric():
    registry, _ = make_registry()
    data = reco_dict(best_candidate_id="cand_two")
    data["ranking"] = [data["ranking"][1], data["ranking"][0]]  # worse first
    exc = err(validate_semantics, RecommendationResult.from_dict(data),
              registry,
              evaluator_spec=EvaluatorSpec(primary_metric="outcome_reached",
                                           secondary_metrics=()))
    assert "inconsistent_ranking" in exc.codes()


def test_ranking_entry_missing_primary_metric_is_rejected():
    registry, _ = make_registry()
    data = reco_dict()
    data["ranking"][0]["metric_values"] = {"side_note": 1}
    exc = err(validate_semantics, RecommendationResult.from_dict(data),
              registry,
              evaluator_spec=EvaluatorSpec(primary_metric="outcome_reached",
                                           secondary_metrics=()))
    assert "missing_field" in exc.codes()


def test_downside_outcomes_must_reference_ranked_candidates():
    registry, _ = make_registry()
    data = reco_dict()
    data["downside_outcomes"]["cand_ghost"] = "Imagined problem."
    exc = err(validate_semantics, RecommendationResult.from_dict(data),
              registry)
    assert "unknown_reference" in exc.codes()
