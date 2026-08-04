"""HARD GATE scenario one: the frozen individual_reply fixture's BASELINE
world through stock Concordia, end to end.

Directive ("Hard gate: prove Concordia independently", lines 1337-1359):
no compiler, no evidence retrieval, no LLM-generated actors or world
fields, no AgentSociety, no candidate interventions -- the compiled world
of the frozen fixture (loaded by the strict Phase 3 loader, fixture file
untouched), deterministic scripted models, and Concordia's real actor /
memory / game-master / engine code.

Proven here:
  1. observation -> actor attempt -> GM resolution -> second actor
     response -> persistent state -> outcome trace, in commit order;
  2. THREE clean runs with byte-identical traces under the seeded
     determinism harness (det.py, shared with tests/engine_contracts);
  3. private context stays private, shared context reaches both actors,
     and evaluator/resolution text reaches ZERO actor or game-master
     prompts (canary strings injected IN-TEST into a rebuilt world dict --
     the frozen fixture file is never edited);
  4. the runner's result dict feeds the Phase 3 BranchResult contract
     as-is (schema-strict from_dict), with the outcome computed ONLY from
     the returned event trace.

Wrapper note (Phase 2 findings addendum, item 4): the engine commits
``[event] {EventResolution pre_act_label}: {chain output}`` and an empty
chain's output keeps upstream's ``Putative event to resolve:`` framing, so
every trace assertion here uses marker containment, never full-string
equality.
"""

from __future__ import annotations

import copy
import json
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

from baseline_helpers import (AWARE_QUESTION_NEEDLE, REPO_ROOT,
                              StrictScriptedModel, all_prompt_text,
                              aware_rule, run_signature)
from sworldmodel.backends.concordia_local import builder, planner, runner
from sworldmodel.decision.contracts import (BranchResult,
                                            CompiledDecisionWorld,
                                            EvaluatorSpec, SCHEMA_VERSION)
from sworldmodel.decision.fixture_loader import load_fixture_file

FIXTURE_PATH = (REPO_ROOT / "tests" / "fixtures" / "best_action"
                / "individual_reply.yaml")
SEED = 20260803
MAX_STEPS = 4  # two full turns per actor under the fixed order

SENDER_TURNS = (
    "writes to Morgan naming one concrete reason the work matters to her "
    "and asking for a short conversation MSG_ALPHA",
    "thanks Morgan and confirms the agreed short conversation MSG_BETA",
)
RECIPIENT_TURNS = (
    "replies to Alex agreeing to a short conversation, citing MSG_ALPHA "
    "as the reason it seems worthwhile",
    "adds a reminder for the agreed slot and restates acceptance of "
    "MSG_BETA",
)


@pytest.fixture(scope="module")
def fixture_one():
    fx = load_fixture_file(str(FIXTURE_PATH))
    # Frozen-fixture identity guards: this scenario is written against the
    # exact frozen cast.
    assert fx.world.actor_ids() == ("sender", "recipient")
    names = {actor.actor_id: actor.name for actor in fx.world.actors}
    assert names == {"sender": "Alex", "recipient": "Morgan"}
    assert fx.world.starting_events == ()
    return fx


def _fresh_models():
    return {
        "sender": StrictScriptedModel(
            [("What does Alex do next?", list(SENDER_TURNS))]),
        "recipient": StrictScriptedModel(
            [("What does Morgan do next?", list(RECIPIENT_TURNS))]),
        "gm": StrictScriptedModel([aware_rule(["Alex", "Morgan"])]),
    }


def _run_once(world, evaluator_spec):
    plan = planner.build_initialization_plan(
        world, evaluator_spec, max_steps=MAX_STEPS)
    models = _fresh_models()
    with seeded_determinism(SEED):
        result = runner.run_branch(
            plan,
            actor_models={"sender": models["sender"],
                          "recipient": models["recipient"]},
            gm_model=models["gm"],
        )
    return plan, models, result


def _evaluate_reply_from_trace(event_trace, recipient_name: str) -> dict:
    """External-evaluator stand-in: reads ONLY the returned event trace."""
    reply_events = [
        entry for entry in event_trace
        if f"{recipient_name}:" in entry["description"]
        and "agreeing" in entry["description"]]
    return {
        "recipient_reply_sent": bool(reply_events),
        "evidence_event_ids": [entry["event_id"] for entry in reply_events],
    }


# ---------------------------------------------------------------------------
# End-to-end flow + three clean runs
# ---------------------------------------------------------------------------


def test_three_clean_runs_end_to_end_byte_identical(fixture_one):
    runs = []
    for _attempt in range(3):
        runs.append(_run_once(fixture_one.world,
                              fixture_one.evaluator_spec))

    # Three CLEAN runs: no infrastructure errors, full budget consumed,
    # default status per R3 is 'cutoff' (never an automatic failure).
    for _plan, _models, result in runs:
        assert result["infrastructure_errors"] == []
        assert result["steps_completed"] == MAX_STEPS
        assert result["terminal_status"] == "cutoff"

    # Byte-identical traces across all three runs under the seeded harness.
    signatures = {run_signature(result) for _plan, _models, result in runs}
    assert len(signatures) == 1, (
        "the three clean runs did not produce byte-identical traces")

    plan, models, result = runs[0]

    # --- plan rule: the sender's initial observation IS the shared context.
    shared = fixture_one.world.shared_context.strip()
    assert plan.initial_observations["sender"] == (shared,)
    assert plan.initial_observations["recipient"] == (shared,)

    # --- observation precedes the actor attempt: the prompt that produced
    # Alex's first action already contained the shared-context observation.
    sender_prompts = models["sender"].prompts
    assert len(sender_prompts) == 2
    assert shared in sender_prompts[0]
    assert "What does Alex do next?" in sender_prompts[0]

    # --- actor attempt -> GM resolution, in commit order, via the real
    # putative-event machinery.
    gm_rows = result["gm_memory"]
    putative_alex = [i for i, row in enumerate(gm_rows)
                     if builder.PUTATIVE_EVENT_TAG in row
                     and "Alex:" in row and "MSG_ALPHA" in row]
    committed_alpha = [i for i, row in enumerate(gm_rows)
                       if builder.EVENT_TAG in row and "MSG_ALPHA" in row]
    assert putative_alex and committed_alpha
    assert putative_alex[0] < committed_alpha[0], (
        "the committed [event] must follow the [putative_event] attempt")

    # --- the second actor received an ACTUAL turn: Morgan's reply enters
    # as her own putative event and she was called exactly twice.
    putative_morgan = [i for i, row in enumerate(gm_rows)
                       if builder.PUTATIVE_EVENT_TAG in row
                       and "Morgan:" in row]
    assert putative_morgan, "the recipient never took an actor turn"
    assert committed_alpha[0] < putative_morgan[0], (
        "the recipient's turn must follow the committed first message")
    recipient_prompts = models["recipient"].prompts
    assert len(recipient_prompts) == 2
    # Her reply was INFORMED: the observed committed event (not just the
    # raw putative text) was in her prompt before she acted.
    assert "MSG_ALPHA" in recipient_prompts[0]

    # --- committed event stream: premise first, then the four turns in
    # fixed acting order.
    committed = result["committed_events"]
    assert len(committed) == 5
    assert plan.neutral_premise in committed[0]
    for row, marker in zip(committed[1:], (
            "MSG_ALPHA", "citing MSG_ALPHA", "MSG_BETA",
            "acceptance of MSG_BETA")):
        assert marker in row

    # --- persistent state across turns: both actors' second-turn prompts
    # contain first-turn material, and their memories carry both rounds.
    assert "citing MSG_ALPHA" in sender_prompts[1], (
        "the sender's second turn lost the recipient's reply")
    assert "MSG_ALPHA" in recipient_prompts[1]
    assert "MSG_BETA" in recipient_prompts[1], (
        "the recipient's second turn lost the sender's follow-up")
    for actor_id in ("sender", "recipient"):
        memory_text = json.dumps(result["actor_memories"][actor_id])
        assert "MSG_ALPHA" in memory_text
        assert "MSG_BETA" in memory_text

    # --- raw engine log captured: one structured entry per step.
    assert len(result["raw_log"]) == MAX_STEPS

    # --- model-call exactness: the YOLO-free roster makes exactly one GM
    # model call per step (the observer question) and one call per actor
    # turn; anything else would have raised inside StrictScriptedModel.
    assert len(models["gm"].prompts) == MAX_STEPS
    assert all(AWARE_QUESTION_NEEDLE in prompt
               for prompt in models["gm"].prompts), (
        "every GM model call must be the observer question -- there is no "
        "other model-facing GM path in this roster")


def test_outcome_is_read_from_trace_and_feeds_branch_result(fixture_one):
    _plan, _models, result = _run_once(fixture_one.world,
                                       fixture_one.evaluator_spec)

    outcome = _evaluate_reply_from_trace(result["event_trace"], "Morgan")
    assert outcome["recipient_reply_sent"] is True
    assert outcome["evidence_event_ids"], (
        "a trace-read outcome must cite the events it was computed from")

    branch_result = BranchResult.from_dict({
        "contract_type": BranchResult.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        # Baseline world only -- no candidate was applied; the identifier
        # says so.  (Semantic registry binding of branch/candidate ids is
        # Phase 6 work; this proves the runner output SHAPE feeds the
        # contract's strict schema gate.)
        "branch_id": "b_scenario_one_baseline",
        "candidate_id": "baseline_world_only",
        "world_id": result["world_id"],
        "terminal_status": result["terminal_status"],
        "terminal_world_state": result["terminal_world_state"],
        "event_trace": result["event_trace"],
        "outcome_metrics": {
            "recipient_reply_sent": {
                "value": outcome["recipient_reply_sent"],
                "computed_from": [
                    f"event:{event_id}"
                    for event_id in outcome["evidence_event_ids"]],
            },
        },
        "infrastructure_errors": result["infrastructure_errors"],
        "token_stats": result["token_stats"],
        "runtime_stats": result["runtime_stats"],
        "artifact_paths": [],
    })
    assert branch_result.terminal_status == "cutoff"
    assert branch_result.outcome_metrics["recipient_reply_sent"].value is True
    # R3: the runner never converted an engine stop into a failure; the
    # 'success'/'failure' verdict belongs to the external evaluator alone.
    assert result["terminal_status"] in ("cutoff", "incomplete")

    # Wall-clock and step stats are present and sane.
    stats = result["runtime_stats"]
    assert stats["steps_completed"] == MAX_STEPS
    assert stats["wall_clock_seconds"] >= 0


# ---------------------------------------------------------------------------
# Canary containment (in-test world rebuild; frozen fixture file untouched)
# ---------------------------------------------------------------------------

PRIVATE_A_CANARY = "PRIVATE_A_CANARY_5efc"
PRIVATE_B_CANARY = "PRIVATE_B_CANARY_a9d1"
SHARED_CANARY = "SHARED_CANARY_77e2"
RESOLUTION_CANARY = "RESOLUTION_CANARY_31bb"
RESOLUTION_CANARY_METRIC = "resolution_canary_31bb"


def _canary_world_and_spec(fx):
    """Rebuild the loaded world WITH canaries as pure test data.

    ``to_dict`` -> deepcopy -> edit -> strict ``from_dict``: the frozen
    fixture file and the loaded contract object stay untouched.
    """
    data = copy.deepcopy(fx.world.to_dict())
    for actor in data["actors"]:
        if actor["actor_id"] == "sender":
            actor["private_context"] += f" {PRIVATE_A_CANARY}"
        elif actor["actor_id"] == "recipient":
            actor["private_context"] += f" {PRIVATE_B_CANARY}"
    data["shared_context"] += f" {SHARED_CANARY}"
    data["success_criteria"] += f" {RESOLUTION_CANARY}"
    world = CompiledDecisionWorld.from_dict(data)
    spec = EvaluatorSpec(
        primary_metric=fx.evaluator_spec.primary_metric,
        secondary_metrics=tuple(fx.evaluator_spec.secondary_metrics)
        + (RESOLUTION_CANARY_METRIC,),
    )
    return world, spec


def test_canary_containment_private_shared_resolution(fixture_one):
    world, spec = _canary_world_and_spec(fixture_one)
    # Sanity: the canaries really entered the pipeline inputs.
    assert RESOLUTION_CANARY in world.success_criteria
    assert SHARED_CANARY in world.shared_context

    plan, models, result = _run_once(world, spec)
    assert result["infrastructure_errors"] == []

    sender_text = all_prompt_text(models["sender"])
    recipient_text = all_prompt_text(models["recipient"])
    gm_text = all_prompt_text(models["gm"])
    all_memories = json.dumps(result["actor_memories"], sort_keys=True)
    gm_rows_text = json.dumps(result["gm_memory"])

    # Private canaries: ONLY in the owning actor's prompts; in no other
    # actor's prompts, in no memory row, in no game-master material.
    assert PRIVATE_A_CANARY in sender_text
    assert PRIVATE_A_CANARY not in recipient_text
    assert PRIVATE_A_CANARY not in gm_text
    assert PRIVATE_A_CANARY not in all_memories
    assert PRIVATE_A_CANARY not in gm_rows_text

    assert PRIVATE_B_CANARY in recipient_text
    assert PRIVATE_B_CANARY not in sender_text
    assert PRIVATE_B_CANARY not in gm_text
    assert PRIVATE_B_CANARY not in all_memories
    assert PRIVATE_B_CANARY not in gm_rows_text

    # Shared canary reaches BOTH actors (initial observation per the plan
    # rules).
    assert SHARED_CANARY in sender_text
    assert SHARED_CANARY in recipient_text

    # Resolution/evaluator canaries reach ZERO actor or GM prompts, and no
    # memory: neither the success-criteria prose canary nor the evaluator
    # metric slug.
    for canary in (RESOLUTION_CANARY.lower(), RESOLUTION_CANARY_METRIC):
        for haystack in (sender_text, recipient_text, gm_text,
                         all_memories, gm_rows_text):
            assert canary not in haystack.lower(), (
                f"evaluator-facing text {canary!r} leaked into a prompt or "
                "memory")

    # The plan carries the evaluator METRIC (passthrough for the external
    # evaluator) but never the success-criteria prose.
    plan_json = plan.canonical_json()
    assert RESOLUTION_CANARY_METRIC in plan_json
    assert RESOLUTION_CANARY not in plan_json
