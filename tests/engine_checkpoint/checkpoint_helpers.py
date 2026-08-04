"""Driver-side helpers for the Phase 8 checkpoint/resume suite.

Import this module AFTER the per-module version/importorskip gates: it
imports the fixture-1 toolkits (``cf_helpers`` -> ``baseline_helpers``),
which import the Concordia language-model interface available only in
the pinned engine environment (Python >= 3.12).

Scenario vocabulary stays where it always lived -- the frozen fixture
and the test-owned toolkits; this module only extends the fixture-1
script with two extra PROMPT-PURE turns so a four-step run exists (the
Stage B gate checkpoints at step 2 of 4).  Prompt-purity (single-response
rules keyed on needles that only appear in later-step prompts) is what
makes fresh model objects position-correct on resume; see
``checkpoint_model_specs``.
"""

from __future__ import annotations

import hashlib
import json

from baseline_helpers import AWARE_QUESTION_NEEDLE
from cf_helpers import (SEED, SENDER_CTA,  # noqa: F401
                        load_fixture_one, make_candidate)
from checkpoint_model_specs import (CANDIDATE_ACTION_TOKEN,
                                    build_prompt_pure_models)
from sworldmodel.counterfactuals.branch import (apply_intervention,
                                                derive_branch_id)
from sworldmodel.counterfactuals.snapshot import (build_base_plan,
                                                  derive_branch_seed)

#: the dotted reference the distributed leg ships to workers
MODEL_BUILDER_REF = "checkpoint_model_specs:build_prompt_pure_models"

#: four engine steps (two full turns per actor under the fixed order):
#: the gate checkpoints at the end-of-step boundary 2 and continues to 4
MAX_STEPS = 4
CHECKPOINT_AFTER = 2

#: an independent second seed proving the equivalence is not
#: seed-coincidence (the gate holds under both; with rng-draw models the
#: two seeds produce visibly different traces)
SEED_ALT = 913026

#: the two extra prompt-pure turns extending the fixture script to four
#: steps (texts are guard-neutral: each actor acts about itself)
ALEX_FOLLOWUP_TURN = ("Alex notes the outcome and prepares a two-line "
                     "agenda for the follow-up.")
MORGAN_SECOND_TURN = ("Morgan files the thread and returns to scheduled "
                     "work.")
#: Morgan's step-2 turn when the fixture script says 'none'
MORGAN_SILENT_TURN = ("Morgan files the message away and continues her "
                     "scheduled work without responding.")


def fixture_candidate(fx, candidate_id: str):
    matches = [candidate for candidate in fx.candidates
               if candidate.candidate_id == candidate_id]
    assert len(matches) == 1, candidate_id
    return matches[0]


def prompt_pure_params(fx, *, rng_draw_actors=()) -> dict:
    """Serializable prompt-pure params for ``build_prompt_pure_models``
    covering fixture-1 at MAX_STEPS=4.

    Rule design (first match wins; every response is a single string):

    - Alex step 1: no Morgan turn exists yet -> the call-to-action rule
      answers with the branch candidate's action (token-substituted).
      Steps 3+: Morgan's step-2 turn text is in Alex's observation
      context -> the matching Morgan-turn needle answers the follow-up.
    - Morgan step 2: only the branch's own candidate action text is in
      context -> that candidate's scripted response (fixture
      deterministic_script; 'none' -> the silent turn).  Step 4: Alex's
      follow-up text is in context -> the closing turn.
    - GM: the observer question, everyone aware (fixture actor names in
      declared order).
    """
    script = fx.deterministic_script["recipient"]
    alex_rules = [[MORGAN_SILENT_TURN, ALEX_FOLLOWUP_TURN]]
    morgan_rules = [[ALEX_FOLLOWUP_TURN, MORGAN_SECOND_TURN]]
    for candidate in fx.candidates:
        response = script[candidate.candidate_id]["response"].strip()
        text = MORGAN_SILENT_TURN if response == "none" else response
        if text != MORGAN_SILENT_TURN:
            alex_rules.append([text, ALEX_FOLLOWUP_TURN])
        morgan_rules.append([candidate.action, text])
    alex_rules.append([SENDER_CTA, CANDIDATE_ACTION_TOKEN])
    observer_names = ", ".join(actor.name for actor in fx.world.actors)
    params = {
        "actor_rules": {"sender": alex_rules, "recipient": morgan_rules},
        "gm_rules": [[AWARE_QUESTION_NEEDLE, observer_names]],
    }
    if rng_draw_actors:
        params["rng_draw_actors"] = list(rng_draw_actors)
    return params


def model_spec(params) -> dict:
    return {"model_builder": MODEL_BUILDER_REF, "params": params}


def make_models(params, candidate, branch_seed):
    """Driver-side models through the SAME registered builder the
    workers use (single source of truth)."""
    return build_prompt_pure_models(params)(candidate, branch_seed)


def branch_setup(fx, candidate_id: str, *, seed: int = SEED,
                 max_steps: int = MAX_STEPS):
    """One branch's frozen identity: (candidate, branch plan, branch id,
    branch seed), derived exactly like the managers derive them."""
    candidate = fixture_candidate(fx, candidate_id)
    base_plan = build_base_plan(fx.world, fx.evaluator_spec,
                                max_steps=max_steps)
    plan = apply_intervention(base_plan, candidate)
    branch_id = derive_branch_id(fx.world.world_id, candidate.candidate_id)
    branch_seed = derive_branch_seed(seed, candidate.candidate_id)
    return candidate, plan, branch_id, branch_seed


def checkpoint_identity(candidate, branch_id: str, branch_seed: int) -> dict:
    return {
        "seed_material": branch_seed,
        "candidate_id": candidate.candidate_id,
        "branch_id": branch_id,
        "model_config": {"model_builder": MODEL_BUILDER_REF},
    }


#: raw runner-result fields covered by the Stage B full signature: the
#: complete trace (committed events + shaped trace + raw GM memory), all
#: actor memories, absolute step accounting, terminal status/state, guard
#: interventions, and infrastructure errors.  DELIBERATELY EXCLUDED:
#: ``raw_log`` (its per-step ``make_observation`` sub-dicts are keyed in
#: thread-pool completion order and its step numbers are segment-local --
#: the documented exclusion the Phase 4/6/7 signatures already use),
#: ``runtime_stats`` (wall clock), ``run_metadata`` (plan constants), and
#: the checkpoint/resume metadata keys themselves.
FULL_SIGNATURE_KEYS = ("plan_id", "world_id", "committed_events",
                       "event_trace", "gm_memory", "actor_memories",
                       "steps_completed", "max_steps", "terminal_status",
                       "terminal_world_state", "guard_interventions",
                       "infrastructure_errors")


def full_signature(raw: dict) -> str:
    """Byte-comparable canonical signature of one raw runner result."""
    return json.dumps({key: raw[key] for key in FULL_SIGNATURE_KEYS},
                      sort_keys=True)


def signature_sha256(raw: dict) -> str:
    return hashlib.sha256(full_signature(raw).encode("utf-8")).hexdigest()
