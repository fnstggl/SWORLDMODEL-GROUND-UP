"""Information-leak canaries for ADAPTER-DERIVED worlds, end to end.

Directive ("Information-leak tests"): unique canary strings prove, on a
world produced by the compiler adapter and run through the REAL planner,
builder, and runner with strict scripted models:

- ``PRIVATE_ALICE_CANARY`` appears only in Alice's context and prompts;
- ``PRIVATE_BOB_CANARY`` appears only in Bob's context and prompts;
- ``SHARED_CANARY`` is available to every intended actor;
- an event visible only to Alice never appears in Bob's context;
- ``RESOLUTION_CANARY`` appears in zero actor prompts and zero Game
  Master prompts;
- one branch's intervention never appears in another branch;
- compiler provenance never enters actor reasoning.

Every canary is first asserted PRESENT at its intended destination (no
vacuous absence checks), then absent everywhere it must not reach.
Canary strings are test-owned; production code never carries them.
"""

from __future__ import annotations

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

from compilation_helpers import (BRANCH_ONE_CANARY, BRANCH_TWO_CANARY,
                                 EVENT_ALICE_ONLY_CANARY,
                                 PRIVATE_ALICE_CANARY, PRIVATE_BOB_CANARY,
                                 PROVENANCE_CANARY, QUESTION_CANARY,
                                 RESOLUTION_CANARY, SEED, SHARED_CANARY,
                                 adapt_canary_scene, all_prompt_text,
                                 build_plan, make_evaluator_spec,
                                 memory_text, run_plan,
                                 scripted_models_for_plan)
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.decision.contracts import (InterventionCandidate,
                                            SCHEMA_VERSION)

CANARY_START = "2026-08-03T09:00:00Z"


def _run_canary_scene():
    scene = adapt_canary_scene()
    plan = build_plan(scene.world)
    result, actor_models, gm_model = run_plan(plan)
    assert result["infrastructure_errors"] == []
    assert result["steps_completed"] == 2  # both actors took a turn
    prompts = {actor_id: all_prompt_text(model)
               for actor_id, model in actor_models.items()}
    return scene, plan, result, prompts, all_prompt_text(gm_model)


def test_private_canaries_reach_only_their_own_actor():
    scene, plan, result, prompts, gm_prompts = _run_canary_scene()
    # Present at the intended destination: each actor's own prompt.
    assert PRIVATE_ALICE_CANARY in prompts["alice"]
    assert PRIVATE_BOB_CANARY in prompts["bob"]
    # And nowhere else: not the other actor, not the game master, not
    # the other actor's memory, not any committed event.
    assert PRIVATE_ALICE_CANARY not in prompts["bob"]
    assert PRIVATE_BOB_CANARY not in prompts["alice"]
    assert PRIVATE_ALICE_CANARY not in gm_prompts
    assert PRIVATE_BOB_CANARY not in gm_prompts
    assert PRIVATE_ALICE_CANARY not in memory_text(result, "bob")
    assert PRIVATE_BOB_CANARY not in memory_text(result, "alice")
    assert PRIVATE_ALICE_CANARY not in "\n".join(
        result["committed_events"])
    assert PRIVATE_BOB_CANARY not in "\n".join(result["committed_events"])


def test_shared_canary_reaches_every_intended_actor():
    scene, plan, result, prompts, _gm_prompts = _run_canary_scene()
    for actor_id in ("alice", "bob"):
        assert SHARED_CANARY in prompts[actor_id], actor_id
        assert SHARED_CANARY in memory_text(result, actor_id), actor_id


def test_single_visibility_event_never_reaches_the_other_actor():
    scene, plan, result, prompts, _gm_prompts = _run_canary_scene()
    # Present for the declared observer...
    assert EVENT_ALICE_ONLY_CANARY in prompts["alice"]
    assert EVENT_ALICE_ONLY_CANARY in memory_text(result, "alice")
    # ...and absent from the non-observer's prompts and memory.  (The
    # game master keeps the full pre-start record by design.)
    assert EVENT_ALICE_ONLY_CANARY not in prompts["bob"]
    assert EVENT_ALICE_ONLY_CANARY not in memory_text(result, "bob")
    assert EVENT_ALICE_ONLY_CANARY in "\n".join(
        plan.gm_initial_events)


def test_resolution_canary_reaches_no_actor_and_no_gm_prompt():
    scene, plan, result, prompts, gm_prompts = _run_canary_scene()
    # Non-vacuity: the canary IS in the world's evaluator-only field.
    assert RESOLUTION_CANARY in scene.world.success_criteria
    # Zero actor prompts, zero game-master prompts, zero memory rows,
    # and not one byte of the initialization plan.
    for actor_id, text in prompts.items():
        assert RESOLUTION_CANARY not in text, actor_id
        assert RESOLUTION_CANARY not in memory_text(result, actor_id)
    assert RESOLUTION_CANARY not in gm_prompts
    assert RESOLUTION_CANARY not in plan.canonical_json()


def test_compiler_provenance_never_enters_actor_reasoning():
    scene, plan, result, prompts, gm_prompts = _run_canary_scene()
    # Non-vacuity: provenance rides the world AND the plan sidecar
    # field, and the question hash rides the provenance.
    assert PROVENANCE_CANARY in scene.world.compiler_provenance.version
    assert PROVENANCE_CANARY in plan.canonical_json()
    # It never reaches any prompt or memory.
    for actor_id, text in prompts.items():
        assert PROVENANCE_CANARY not in text, actor_id
        assert PROVENANCE_CANARY not in memory_text(result, actor_id)
    assert PROVENANCE_CANARY not in gm_prompts
    # The compile QUESTION is sidecar metadata too: hashed into
    # provenance, carried in the adapter sidecar, and equally absent
    # from every prompt.
    assert QUESTION_CANARY in scene.sidecar["compile_inputs"]["question"]
    for actor_id, text in prompts.items():
        assert QUESTION_CANARY not in text, actor_id
    assert QUESTION_CANARY not in gm_prompts
    assert QUESTION_CANARY not in plan.canonical_json()


def _canary_candidate(candidate_id: str, marker: str):
    return InterventionCandidate.from_dict({
        "contract_type": InterventionCandidate.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "summary": f"open with {marker}",
        "action": f"Open the exchange with the line {marker}.",
        "decision_owner": "alice",
        "timing": CANARY_START,
        "constraints": [],
        "provenance": {"source": "user_supplied",
                       "generator_config_hash": ""},
    })


def test_one_branch_intervention_never_appears_in_another_branch():
    scene = adapt_canary_scene()
    spec = make_evaluator_spec()
    candidates = (_canary_candidate("branch_one", BRANCH_ONE_CANARY),
                  _canary_candidate("branch_two", BRANCH_TWO_CANARY))
    capture: dict = {}

    def factory(candidate, branch_seed):
        plan = build_plan(scene.world, evaluator_spec=spec)
        actor_models, gm_model = scripted_models_for_plan(
            plan, {"alice": candidate.action})
        capture[candidate.candidate_id] = (actor_models, gm_model)
        return actor_models, gm_model

    run = run_candidates_detailed(
        scene.world, candidates, model_factory=factory, seed=SEED,
        max_steps=2, evaluator_spec=spec,
        model_config={"kind": "scripted_test_models"})
    for result in run.results:
        assert result.infrastructure_errors == ()

    markers = {"branch_one": BRANCH_ONE_CANARY,
               "branch_two": BRANCH_TWO_CANARY}
    for candidate_id, (actor_models, gm_model) in capture.items():
        own_marker = markers[candidate_id]
        other_markers = [marker for key, marker in markers.items()
                         if key != candidate_id]
        branch_text = "\n".join(
            [all_prompt_text(model) for model in actor_models.values()]
            + [all_prompt_text(gm_model)])
        # Non-vacuity: the branch's own intervention IS observed by its
        # insertion actor.
        assert own_marker in all_prompt_text(actor_models["alice"])
        for other in other_markers:
            assert other not in branch_text, candidate_id
    # And the recorded traces stay disjoint as well.
    by_id = {result.candidate_id: result for result in run.results}
    trace_one = "\n".join(event.description
                          for event in by_id["branch_one"].event_trace)
    trace_two = "\n".join(event.description
                          for event in by_id["branch_two"].event_trace)
    assert BRANCH_ONE_CANARY in trace_one
    assert BRANCH_TWO_CANARY in trace_two
    assert BRANCH_TWO_CANARY not in trace_one
    assert BRANCH_ONE_CANARY not in trace_two
