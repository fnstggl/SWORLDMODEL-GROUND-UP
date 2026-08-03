"""The lightweight DecisionProblem route: user-supplied candidates, the
one-fixed-schema generator behind the model seam, and end-to-end
plumbing into the existing counterfactual manager.

Directive ("Minimal compiler connection"): candidate generation QUALITY
is not a completion criterion; correct plumbing -- one fixed schema, one
model call, strict parsing, honest provenance, and runnable candidate
sets -- is what these tests prove.  All models are scripted; no live
credentials anywhere.
"""

from __future__ import annotations

import json
import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine compilation suite requires Python >= 3.12 (Concordia "
        "floor); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from compilation_helpers import (SEED, adapt_canary_scene, build_plan,
                                 make_evaluator_spec, make_problem,
                                 scripted_models_for_plan,
                                 RecordingGeneratorModel)
from sworldmodel.compilation import (GENERATOR_PROMPT_TEMPLATE,
                                     GENERATOR_RESPONSE_SCHEMA,
                                     build_generator_prompt,
                                     build_user_candidates,
                                     generate_candidates,
                                     generator_config_hash,
                                     parse_generator_response,
                                     prepare_decision_inputs)
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.decision.contracts import (ContractValidationError,
                                            canonical_time)

USER_ACTIONS = ("Open with the short direct line.",
                "Open with the detailed background line.")
GENERATED_RESPONSE = json.dumps({"candidates": [
    {"summary": "steady opening",
     "action": "Open with the steady, patient line."},
    {"summary": "question opening",
     "action": "Open by asking one clarifying question."},
]})


def _scene_and_problem(**overrides):
    scene = adapt_canary_scene()
    arguments = {"decision_owner": "Alice",
                 "candidate_interventions": USER_ACTIONS}
    arguments.update(overrides)
    problem = make_problem(**arguments)
    return scene, problem


def test_user_supplied_candidates_follow_the_fixed_code_owned_rules():
    scene, problem = _scene_and_problem()
    candidates = build_user_candidates(problem, scene.world)
    assert [candidate.candidate_id for candidate in candidates] \
        == ["user_001", "user_002"]
    for candidate, action in zip(candidates, USER_ACTIONS):
        assert candidate.action == action              # verbatim
        assert candidate.summary == " ".join(action.split())[:120]
        assert candidate.decision_owner == "alice"     # insertion actor
        assert canonical_time(candidate.timing) \
            == canonical_time(scene.world.start_time)
        assert candidate.provenance.source == "user_supplied"
        assert candidate.provenance.generator_config_hash == ""


def test_prepare_decision_inputs_yields_a_manager_ready_pair():
    scene, problem = _scene_and_problem()
    spec = make_evaluator_spec()
    inputs = prepare_decision_inputs(problem, scene.world,
                                     evaluator_spec=spec)
    assert inputs.world is scene.world
    assert [candidate.candidate_id for candidate in inputs.candidates] \
        == ["user_001", "user_002"]
    assert inputs.registry.has_world(scene.world.world_id)
    for candidate in inputs.candidates:
        assert inputs.registry.has_candidate(candidate.candidate_id)

    # The pair drives the EXISTING counterfactual manager end to end.
    def factory(candidate, branch_seed):
        plan = build_plan(inputs.world, evaluator_spec=spec)
        return scripted_models_for_plan(plan,
                                        {"alice": candidate.action})

    run = run_candidates_detailed(
        inputs.world, inputs.candidates, model_factory=factory,
        seed=SEED, max_steps=2, evaluator_spec=inputs.evaluator_spec,
        registry=inputs.registry,
        model_config={"kind": "scripted_test_models"})
    assert len(run.results) == 2
    for candidate, result in zip(inputs.candidates, run.results):
        assert result.candidate_id == candidate.candidate_id
        assert result.infrastructure_errors == ()
        trace = "\n".join(event.description
                          for event in result.event_trace)
        assert candidate.action in trace


def test_owner_must_resolve_to_the_worlds_insertion_actor():
    scene, problem = _scene_and_problem(decision_owner="Bob")
    with pytest.raises(ContractValidationError) as excinfo:
        prepare_decision_inputs(problem, scene.world,
                                evaluator_spec=make_evaluator_spec())
    assert "owner_mismatch" in excinfo.value.codes()
    scene, problem = _scene_and_problem(decision_owner="Nobody Known")
    with pytest.raises(ContractValidationError) as excinfo:
        prepare_decision_inputs(problem, scene.world,
                                evaluator_spec=make_evaluator_spec())
    assert "unknown_reference" in excinfo.value.codes()


def test_route_with_no_candidates_at_all_is_refused():
    scene, problem = _scene_and_problem(candidate_interventions=())
    with pytest.raises(ContractValidationError) as excinfo:
        prepare_decision_inputs(problem, scene.world,
                                evaluator_spec=make_evaluator_spec())
    assert "empty_collection" in excinfo.value.codes()


def test_generation_requires_the_problems_explicit_permission():
    scene, problem = _scene_and_problem(permission=False)
    model = RecordingGeneratorModel(GENERATED_RESPONSE)
    with pytest.raises(ContractValidationError) as excinfo:
        generate_candidates(problem, scene.world, model=model)
    assert "candidate_generation_permission" in excinfo.value.paths()
    assert model.prompts == []  # refused BEFORE any model call
    with pytest.raises(ContractValidationError):
        prepare_decision_inputs(problem, scene.world,
                                evaluator_spec=make_evaluator_spec(),
                                generator_model=model)
    assert model.prompts == []


def test_generator_uses_one_fixed_schema_and_exactly_one_model_call():
    scene, problem = _scene_and_problem(permission=True)
    model = RecordingGeneratorModel(GENERATED_RESPONSE)
    candidates = generate_candidates(problem, scene.world, model=model)
    assert len(model.prompts) == 1              # exactly one call
    prompt = model.prompts[0]
    # The fixed schema is embedded verbatim; the problem's own fields
    # (and only problem fields) parameterize the fixed template.
    assert json.dumps(GENERATOR_RESPONSE_SCHEMA, sort_keys=True,
                      indent=1) in prompt
    assert problem.desired_outcome in prompt
    assert problem.success_criteria in prompt
    for action in USER_ACTIONS:
        assert action in prompt                 # already-supplied list
    # No world-private material enters the generator prompt.
    for actor in scene.world.actors:
        assert actor.private_context not in prompt
    # Deterministic assembly: same problem -> byte-identical prompt,
    # and the one fixed template is the single source of the prompt.
    assert build_generator_prompt(problem) == prompt
    assert "{schema}" in GENERATOR_PROMPT_TEMPLATE
    assert "{max_candidates}" in GENERATOR_PROMPT_TEMPLATE
    assert [candidate.candidate_id for candidate in candidates] \
        == ["gen_001", "gen_002"]


def test_generated_candidates_carry_generated_provenance_and_hash():
    scene, problem = _scene_and_problem(permission=True)
    model = RecordingGeneratorModel(GENERATED_RESPONSE)
    candidates = generate_candidates(problem, scene.world, model=model)
    expected_hash = generator_config_hash()
    assert expected_hash == generator_config_hash()  # stable identity
    for candidate in candidates:
        assert candidate.provenance.source == "generated"
        assert candidate.provenance.generator_config_hash \
            == expected_hash
        assert candidate.decision_owner == "alice"
    # The hash binds the FIXED configuration: a different cap is a
    # different configuration identity.
    assert generator_config_hash(2) != expected_hash


def test_fenced_json_is_accepted_as_mechanical_extraction():
    scene, problem = _scene_and_problem(permission=True)
    fenced = "```json\n" + GENERATED_RESPONSE + "\n```"
    candidates = generate_candidates(
        problem, scene.world, model=RecordingGeneratorModel(fenced))
    assert len(candidates) == 2


def test_malformed_generator_output_fails_loudly_with_all_defects():
    scene, problem = _scene_and_problem(permission=True)

    def refuse(response):
        with pytest.raises(ContractValidationError) as excinfo:
            generate_candidates(problem, scene.world,
                                model=RecordingGeneratorModel(response))
        return excinfo.value

    # Not JSON at all.
    error = refuse("Here are my thoughts on the matter.")
    assert "not valid JSON" in str(error)
    # Wrong root shape.
    error = refuse(json.dumps(["a", "b"]))
    assert "wrong_type" in error.codes()
    # Unknown extra field, missing required field.
    error = refuse(json.dumps({"candidates": [], "confidence": 1}))
    assert "unknown_field" in error.codes()
    # Empty candidate list.
    error = refuse(json.dumps({"candidates": []}))
    assert "empty_collection" in error.codes()
    # Over the fixed cap.
    error = refuse(json.dumps({"candidates": [
        {"summary": f"s{i}", "action": f"take path {i}"}
        for i in range(4)]}))
    assert "above the fixed limit" in str(error)
    # Item defects are ALL collected (blank string + unknown field +
    # missing field across two items in one refusal).
    error = refuse(json.dumps({"candidates": [
        {"summary": "", "action": "take the first path",
         "extra": "surplus"},
        {"summary": "second"}]}))
    codes = error.codes()
    assert "invalid_value" in codes
    assert "unknown_field" in codes
    assert "missing_field" in codes
    # Unterminated code fence.
    error = refuse("```json\n{\"candidates\": []}")
    assert "code fence" in str(error)
    # No usable text.
    error = refuse("   ")
    assert "no usable text" in str(error)


def test_generated_route_runs_through_the_manager_end_to_end():
    scene, problem = _scene_and_problem(candidate_interventions=(),
                                        permission=True)
    spec = make_evaluator_spec()
    inputs = prepare_decision_inputs(
        problem, scene.world, evaluator_spec=spec,
        generator_model=RecordingGeneratorModel(GENERATED_RESPONSE))
    assert [candidate.candidate_id for candidate in inputs.candidates] \
        == ["gen_001", "gen_002"]

    def factory(candidate, branch_seed):
        plan = build_plan(inputs.world, evaluator_spec=spec)
        return scripted_models_for_plan(plan,
                                        {"alice": candidate.action})

    run = run_candidates_detailed(
        inputs.world, inputs.candidates, model_factory=factory,
        seed=SEED, max_steps=2, evaluator_spec=spec,
        registry=inputs.registry,
        model_config={"kind": "scripted_test_models"})
    for candidate, result in zip(inputs.candidates, run.results):
        assert result.infrastructure_errors == ()
        trace = "\n".join(event.description
                          for event in result.event_trace)
        assert candidate.action in trace


def test_mixed_user_and_generated_candidates_share_one_namespace():
    scene, problem = _scene_and_problem(permission=True)
    inputs = prepare_decision_inputs(
        problem, scene.world, evaluator_spec=make_evaluator_spec(),
        generator_model=RecordingGeneratorModel(GENERATED_RESPONSE))
    assert [candidate.candidate_id for candidate in inputs.candidates] \
        == ["user_001", "user_002", "gen_001", "gen_002"]
    sources = [candidate.provenance.source
               for candidate in inputs.candidates]
    assert sources == ["user_supplied", "user_supplied",
                       "generated", "generated"]
    for candidate in inputs.candidates:
        assert inputs.registry.has_candidate(candidate.candidate_id)
