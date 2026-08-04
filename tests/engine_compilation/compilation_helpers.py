"""Test-owned helpers for the compiler-to-Concordia adapter suite.

Import this module AFTER the per-module version/importorskip gates: it
imports ``baseline_helpers`` (tests/engine_baseline), which imports the
Concordia language-model interface available only in the pinned engine
environment (Python >= 3.12).

Canary strings and every piece of scene vocabulary used here are
TEST-OWNED: they live in this directory and the committed vectors only,
never in ``sworldmodel/`` production code (the hardcoding guard scans
production on both interpreters).  The canary actor names Alice and Bob
are the directive's own example names for the information-leak tests.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from baseline_helpers import (REPO_ROOT, StrictScriptedModel,  # noqa: F401
                              all_prompt_text, aware_rule)
from sworldmodel.backends.concordia_local import runner as runner_module
from sworldmodel.backends.concordia_local.planner import (
    ACTOR_CALL_TO_ACTION, build_initialization_plan)
from sworldmodel.compilation import adapt_compiled_scene
from sworldmodel.decision.contracts import (DecisionProblem, EvaluatorSpec,
                                            IssueCollector, SCHEMA_VERSION)

HERE = Path(__file__).resolve().parent
VECTOR_DIR = HERE / "vectors"
EQUIVALENCE_VECTOR_PATH = VECTOR_DIR / "individual_reply_scene.json"
COMPILED_ARTIFACT_VECTOR_DIR = VECTOR_DIR / "compiled_scene_artifact"
#: the live committed artifact set the vector above was copied from
LIVE_ARTIFACT_DIR = (REPO_ROOT / "artifacts" / "simulations"
                     / "case1_cold_email" / "compile")
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "best_action"
FIXTURE_ONE_PATH = FIXTURE_DIR / "individual_reply.yaml"
FIXTURE_HASHES_PATH = FIXTURE_DIR / "FIXTURES.sha256"

SEED = 20260803
#: one full turn per actor under the fixed acting order
MAX_STEPS = 2

# ---------------------------------------------------------------------------
# Canary scene (test-owned vocabulary; directive "Information-leak tests")
# ---------------------------------------------------------------------------

CANARY_START = "2026-08-03T09:00:00Z"
CANARY_CUTOFF = "2026-08-04T09:00:00Z"
PRIVATE_ALICE_CANARY = "PRIVATE_ALICE_CANARY_c41f"
PRIVATE_BOB_CANARY = "PRIVATE_BOB_CANARY_9d2e"
SHARED_CANARY = "SHARED_CANARY_5b87"
EVENT_ALICE_ONLY_CANARY = "EVENT_ALICE_ONLY_CANARY_e604"
RESOLUTION_CANARY = "RESOLUTION_CANARY_a3c9"
PROVENANCE_CANARY = "PROVENANCE_CANARY_71bd"
QUESTION_CANARY = "QUESTION_CANARY_2f60"
BRANCH_ONE_CANARY = "BRANCH_ONE_ACTION_CANARY_08aa"
BRANCH_TWO_CANARY = "BRANCH_TWO_ACTION_CANARY_b355"


def canary_manifest() -> dict:
    """A fresh four-field manifest carrying one unique canary per
    information class."""
    return {
        "actors": [
            {"name": "Alice",
             "private_context": ("Alice privately holds "
                                 f"{PRIVATE_ALICE_CANARY} and waits for "
                                 "the window to open.")},
            {"name": "Bob",
             "private_context": ("Bob privately holds "
                                 f"{PRIVATE_BOB_CANARY} and waits for "
                                 "the window to open.")},
        ],
        "shared_context": (f"Both parties already know {SHARED_CANARY} "
                           "before the window opens."),
        "starting_events": [
            {"time": CANARY_START,
             "description": ("A sealed note containing "
                             f"{EVENT_ALICE_ONLY_CANARY} arrives at one "
                             "desk."),
             "visible_to": ["Alice"]},
        ],
        "resolution": (f"Resolve by the {RESOLUTION_CANARY} criteria, "
                       "read from the recorded history only."),
    }


def adapt_canary_scene(insertion_actor: str = "Alice"):
    """Adapt the canary manifest with canary-bearing compile metadata
    (provenance version and question carry their own canaries)."""
    return adapt_compiled_scene(
        canary_manifest(),
        question=(f"Given {QUESTION_CANARY}, which candidate action "
                  "works best?"),
        start=CANARY_START,
        cutoff=CANARY_CUTOFF,
        insertion_actor=insertion_actor,
        compiler_version=f"vtest_{PROVENANCE_CANARY}",
        evidence_mode="scripted_test_vector",
    )


# ---------------------------------------------------------------------------
# Vector loading
# ---------------------------------------------------------------------------

def load_equivalence_vector() -> dict:
    with open(EQUIVALENCE_VECTOR_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def adapt_equivalence_vector():
    """Adapter-map the hand-written fixture-1 vector."""
    vector = load_equivalence_vector()
    return adapt_compiled_scene(
        vector["manifest"],
        question=vector["question"],
        start=vector["start"],
        cutoff=vector["cutoff"],
        insertion_actor=vector["insertion_actor"],
        compiler_version=vector["compiler_version"],
        evidence_mode=vector["evidence_mode"],
    )


# ---------------------------------------------------------------------------
# Scripted execution of a plan (real planner + builder + runner)
# ---------------------------------------------------------------------------

def make_evaluator_spec(primary: str = "primary_signal",
                        secondary=()) -> EvaluatorSpec:
    issues = IssueCollector()
    spec = EvaluatorSpec.parse(
        {"primary_metric": primary, "secondary_metrics": list(secondary)},
        "evaluator_spec", issues)
    issues.raise_if_any()
    return spec


def build_plan(world, *, max_steps: int = MAX_STEPS,
               evaluator_spec: EvaluatorSpec | None = None):
    return build_initialization_plan(
        world, evaluator_spec or make_evaluator_spec(),
        max_steps=max_steps)


def scripted_models_for_plan(plan, turn_texts=None):
    """One strict scripted model per actor (keyed on its call to action)
    plus the game-master model (keyed on the observer question).

    ``turn_texts`` maps actor_id -> the scripted turn text; the default
    is a neutral single line naming only the actor itself.
    """
    turn_texts = dict(turn_texts or {})
    actor_models = {}
    names = []
    for config in plan.actor_configs:
        names.append(config.name)
        call_to_action = ACTOR_CALL_TO_ACTION.format(name=config.name)
        text = turn_texts.get(
            config.actor_id,
            f"{config.name} quietly reviews the situation and files a "
            "brief note.")
        actor_models[config.actor_id] = StrictScriptedModel(
            [(call_to_action, [text])])
    gm_model = StrictScriptedModel([aware_rule(names)])
    return actor_models, gm_model


def run_plan(plan, turn_texts=None):
    """Build + run one plan with scripted models; returns
    ``(result, actor_models, gm_model)``."""
    actor_models, gm_model = scripted_models_for_plan(plan, turn_texts)
    result = runner_module.run_branch(
        plan, actor_models=actor_models, gm_model=gm_model)
    return result, actor_models, gm_model


def memory_text(result, actor_id: str) -> str:
    return "\n".join(result["actor_memories"][actor_id])


def all_memory_text(result) -> str:
    return "\n".join(
        row for rows in result["actor_memories"].values() for row in rows)


# ---------------------------------------------------------------------------
# DecisionProblem builders (route tests)
# ---------------------------------------------------------------------------

def make_problem(*, problem_id: str = "route_check_problem",
                 decision_owner: str, candidate_interventions=(),
                 permission: bool = False,
                 start: str = CANARY_START, cutoff: str = CANARY_CUTOFF,
                 constraints=(), relevant_context: str = "") \
        -> DecisionProblem:
    return DecisionProblem.from_dict({
        "contract_type": DecisionProblem.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "problem_id": problem_id,
        "decision_owner": decision_owner,
        "desired_outcome": "The counterpart engages with the opening "
                           "action before the window closes.",
        "success_criteria": "Measured by the declared primary_signal "
                            "metric from the recorded trace only.",
        "constraints": list(constraints),
        "time_horizon": {"start": start, "cutoff": cutoff},
        "relevant_context": relevant_context,
        "candidate_interventions": list(candidate_interventions),
        "candidate_generation_permission": permission,
    })


class RecordingGeneratorModel:
    """Duck-typed model seam for the candidate generator: records every
    prompt and returns the configured response text (the production
    route requires only ``sample_text``; any Concordia LanguageModel
    satisfies the same seam)."""

    def __init__(self, response: str):
        self.response = response
        self.prompts: list = []

    def sample_text(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        return self.response


# ---------------------------------------------------------------------------
# Plan comparison (manual-vs-compiler equivalence)
# ---------------------------------------------------------------------------

#: plan fields where the two construction routes legitimately differ;
#: every OTHER field must be byte-equal after the actor-id bijection
DOCUMENTED_PLAN_IDENTITY_FIELDS = ("plan_id", "world_id",
                                   "compiler_provenance")


def name_keyed_id_bijection(world_a, world_b) -> dict:
    """actor_id(world_a) -> actor_id(world_b), keyed on the shared actor
    NAMES (which must match exactly one-to-one)."""
    names_a = {actor.name: actor.actor_id for actor in world_a.actors}
    names_b = {actor.name: actor.actor_id for actor in world_b.actors}
    assert set(names_a) == set(names_b), (
        "the two worlds do not share the same actor-name cast: "
        f"{sorted(names_a)} vs {sorted(names_b)}")
    return {names_a[name]: names_b[name] for name in names_a}


def map_plan_actor_ids(plan_dict: dict, id_map: dict) -> dict:
    """Apply the documented name-keyed bijection to every actor-id
    position of a plan dict (actor_configs, initial_observations keys,
    intervention_insertion)."""
    mapped = copy.deepcopy(plan_dict)
    for config in mapped["actor_configs"]:
        config["actor_id"] = id_map[config["actor_id"]]
    mapped["initial_observations"] = {
        id_map[key]: value
        for key, value in mapped["initial_observations"].items()}
    mapped["intervention_insertion"]["actor_id"] = (
        id_map[mapped["intervention_insertion"]["actor_id"]])
    return mapped


def map_world_actor_ids(world_dict: dict, id_map: dict) -> dict:
    """Apply the same bijection to every actor-id position of a
    ``CompiledDecisionWorld`` dict (actors, visible_to, insertion)."""
    mapped = copy.deepcopy(world_dict)
    for actor in mapped["actors"]:
        actor["actor_id"] = id_map[actor["actor_id"]]
    for event in mapped["starting_events"]:
        event["visible_to"] = [id_map[ref] for ref in event["visible_to"]]
    mapped["intervention_insertion_point"]["actor_id"] = (
        id_map[mapped["intervention_insertion_point"]["actor_id"]])
    return mapped


# ---------------------------------------------------------------------------
# Manifest coverage walking (no-silent-discard proofs)
# ---------------------------------------------------------------------------

def manifest_leaves(manifest: dict):
    """Yield ``(path, kind, value)`` for every leaf of a four-field
    manifest: kind is one of name/private_context/shared_context/
    event_time/event_description/visible_to/resolution."""
    for index, actor in enumerate(manifest["actors"]):
        yield (f"actors[{index}].name", "name", actor["name"])
        yield (f"actors[{index}].private_context", "private_context",
               actor["private_context"])
    yield ("shared_context", "shared_context", manifest["shared_context"])
    for index, event in enumerate(manifest["starting_events"]):
        yield (f"starting_events[{index}].time", "event_time",
               event["time"])
        yield (f"starting_events[{index}].description",
               "event_description", event["description"])
        for ref_index, reference in enumerate(event["visible_to"]):
            yield (f"starting_events[{index}].visible_to[{ref_index}]",
                   "visible_to", reference)
    yield ("resolution", "resolution", manifest["resolution"])
