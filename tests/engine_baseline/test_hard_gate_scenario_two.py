"""HARD GATE scenario two: a SECOND manually written scenario with a
different cast and a different type of social interaction, proving the
baseline is not hardcoded to the first example (directive line 1358).

Shape: a three-party scheduling negotiation over a shared laboratory
instrument with a third-party resource constraint -- a requester who
wants a session, an operator who must be present and rejects one day, and
a custodian who owns the calendar (and holds a custodian-only starting
event).  Scenario one was a two-actor message-and-reply exchange with no
starting events; this one exercises three actors, two starting events
with per-actor visibility, multi-round concession, and a commitment
recorded by a third actor.

The world is written INLINE as a CompiledDecisionWorld dict (generic test
vocabulary; production code never sees these words).  Same proofs as
scenario one: three clean byte-identical runs under the shared seeded
harness, memory persistence across >= 2 turns per actor, real turns for
the second and third actors, visibility containment for the
custodian-only event, and a trace-read outcome.
"""

from __future__ import annotations

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

from baseline_helpers import (AWARE_QUESTION_NEEDLE, StrictScriptedModel,
                              all_prompt_text, aware_rule, run_signature)
from sworldmodel.backends.concordia_local import builder, planner, runner
from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            EvaluatorSpec, SCHEMA_VERSION)

SEED = 987654
MAX_STEPS = 6  # two full turns per actor under the fixed order

#: unique token inside the custodian-only starting event (containment probe)
CUSTODIAN_ONLY_TOKEN = "CALWINDOW_TOKEN_42"

WORLD_DICT = {
    "contract_type": "compiled_decision_world",
    "schema_version": SCHEMA_VERSION,
    "world_id": "w_shared_instrument_booking",
    "actors": [
        {"actor_id": "requester", "name": "Priya",
         "private_context": (
             "Priya must finish a sample analysis this week and strongly "
             "prefers Thursday afternoon. PRIV_REQ_TOKEN")},
        {"actor_id": "operator", "name": "Tomas",
         "private_context": (
             "Tomas is the only qualified instrument operator and cannot "
             "supervise any session on Thursday. PRIV_OP_TOKEN")},
        {"actor_id": "custodian", "name": "Vera",
         "private_context": (
             "Vera keeps the instrument calendar and enforces the "
             "one-session-per-afternoon rule. PRIV_CUS_TOKEN")},
    ],
    "shared_context": (
        "A three-person research group shares one analysis instrument "
        "that may only run with a qualified operator present."),
    "starting_events": [
        {"description": (
            "The instrument calendar shows only Wednesday and Thursday "
            f"afternoons still free next week. {CUSTODIAN_ONLY_TOKEN}"),
         "visible_to": ["custodian"],
         "time": "2026-09-01T09:30:00Z"},
        {"description": (
            "Priya asked the group channel for an instrument session "
            "next week. SCHED_REQUEST_POSTED"),
         "visible_to": ["requester", "operator", "custodian"],
         "time": "2026-09-01T10:00:00Z"},
    ],
    "start_time": "2026-09-01T09:00:00Z",
    "cutoff": "2026-09-05T17:00:00Z",
    "success_criteria": (
        "A session_confirmed commitment recorded by the custodian, for a "
        "day the operator accepted, appears in the event trace."),
    "intervention_insertion_point": {"actor_id": "requester"},
    "compiler_provenance": {
        "source": "manual_inline_test",
        "version": "inline_v1",
        "evidence_mode": "manual",
        "artifact_hashes": {},
    },
}

EVALUATOR_SPEC = EvaluatorSpec(
    primary_metric="session_confirmed",
    secondary_metrics=("scheduling_conflict_surfaced",),
)

REQUESTER_TURNS = (
    "asks for the Thursday afternoon session on the shared instrument "
    "SCHED_ASK_1",
    "accepts the Wednesday afternoon slot instead SCHED_ACCEPT_1",
)
OPERATOR_TURNS = (
    "objects that no qualified operator is available on Thursday and "
    "offers Wednesday afternoon instead SCHED_CONFLICT_1",
    "commits to operate the instrument on Wednesday afternoon "
    "SCHED_OPERATOR_OK_1",
)
CUSTODIAN_TURNS = (
    "checks the calendar and pencils in Wednesday afternoon as a hold "
    "SCHED_HOLD_1",
    "records the Wednesday afternoon booking as final "
    "SESSION_CONFIRMED_1",
)

ALL_NAMES = ("Priya", "Tomas", "Vera")


def _fresh_models():
    return {
        "requester": StrictScriptedModel(
            [("What does Priya do next?", list(REQUESTER_TURNS))]),
        "operator": StrictScriptedModel(
            [("What does Tomas do next?", list(OPERATOR_TURNS))]),
        "custodian": StrictScriptedModel(
            [("What does Vera do next?", list(CUSTODIAN_TURNS))]),
        "gm": StrictScriptedModel([aware_rule(ALL_NAMES)]),
    }


def _run_once():
    world = CompiledDecisionWorld.from_dict(WORLD_DICT)
    plan = planner.build_initialization_plan(
        world, EVALUATOR_SPEC, max_steps=MAX_STEPS)
    models = _fresh_models()
    with seeded_determinism(SEED):
        result = runner.run_branch(
            plan,
            actor_models={actor_id: models[actor_id]
                          for actor_id in ("requester", "operator",
                                           "custodian")},
            gm_model=models["gm"],
        )
    return world, plan, models, result


def _evaluate_from_trace(event_trace) -> dict:
    """External-evaluator stand-in: reads ONLY the returned event trace."""
    confirmed = [entry for entry in event_trace
                 if "Vera:" in entry["description"]
                 and "SESSION_CONFIRMED_1" in entry["description"]]
    conflict = [entry for entry in event_trace
                if "Tomas:" in entry["description"]
                and "SCHED_CONFLICT_1" in entry["description"]]
    return {
        "session_confirmed": bool(confirmed),
        "scheduling_conflict_surfaced": bool(conflict),
        "confirmed_ids": [entry["event_id"] for entry in confirmed],
    }


def test_three_clean_runs_end_to_end_byte_identical():
    runs = [_run_once() for _attempt in range(3)]

    for _world, _plan, _models, result in runs:
        assert result["infrastructure_errors"] == []
        assert result["steps_completed"] == MAX_STEPS
        assert result["terminal_status"] == "cutoff"

    signatures = {run_signature(result)
                  for _world, _plan, _models, result in runs}
    assert len(signatures) == 1, (
        "the three clean runs did not produce byte-identical traces")

    world, plan, models, result = runs[0]

    # --- plan visibility rules: the custodian-only event reaches ONLY the
    # custodian's initial observations; the group event reaches all three.
    assert any(CUSTODIAN_ONLY_TOKEN in obs
               for obs in plan.initial_observations["custodian"])
    for actor_id in ("requester", "operator"):
        assert not any(CUSTODIAN_ONLY_TOKEN in obs
                       for obs in plan.initial_observations[actor_id])
        assert any("SCHED_REQUEST_POSTED" in obs
                   for obs in plan.initial_observations[actor_id])

    # Starting-event order and timestamps are preserved in the GM record.
    assert len(plan.gm_initial_events) == 2
    assert plan.gm_initial_events[0].startswith("[2026-09-01T09:30:00Z]")
    assert CUSTODIAN_ONLY_TOKEN in plan.gm_initial_events[0]
    assert plan.gm_initial_events[1].startswith("[2026-09-01T10:00:00Z]")

    # --- fixed acting order, six real turns, each actor twice.
    committed = result["committed_events"]
    # 2 pre-start events + premise + 6 resolved turns
    assert len(committed) == 9
    turn_markers = ("SCHED_ASK_1", "SCHED_CONFLICT_1", "SCHED_HOLD_1",
                    "SCHED_ACCEPT_1", "SCHED_OPERATOR_OK_1",
                    "SESSION_CONFIRMED_1")
    for row, marker in zip(committed[3:], turn_markers):
        assert marker in row, (marker, row)

    # Second and third actors took ACTUAL turns (their own putative
    # events, not GM fiat).
    gm_rows = result["gm_memory"]
    for name, marker in (("Tomas", "SCHED_CONFLICT_1"),
                         ("Vera", "SCHED_HOLD_1")):
        assert any(builder.PUTATIVE_EVENT_TAG in row and f"{name}:" in row
                   and marker in row for row in gm_rows), (
            f"{name} never took a real actor turn")

    # --- memory persistence across two turns for EVERY actor: the second
    # turn's prompt still contains the actor's first-round material.
    persistence_probes = {
        "requester": "SCHED_ASK_1",
        "operator": "SCHED_CONFLICT_1",
        "custodian": "SCHED_HOLD_1",
    }
    for actor_id, marker in persistence_probes.items():
        prompts = models[actor_id].prompts
        assert len(prompts) == 2, (actor_id, len(prompts))
        assert marker in prompts[1], (
            f"{actor_id} lost its own first-round material by turn two")
        memory_text = json.dumps(result["actor_memories"][actor_id])
        assert marker in memory_text

    # The concession chain is informed: the requester's second turn saw
    # the operator's objection; the operator's second turn saw the
    # requester's acceptance.
    assert "SCHED_CONFLICT_1" in models["requester"].prompts[1]
    assert "SCHED_ACCEPT_1" in models["operator"].prompts[1]

    # --- visibility containment at run time: the custodian-only token
    # stayed out of the other actors' prompts and memories (it never
    # entered any committed turn text in this script).
    for actor_id in ("requester", "operator"):
        assert CUSTODIAN_ONLY_TOKEN not in all_prompt_text(models[actor_id])
        assert CUSTODIAN_ONLY_TOKEN not in json.dumps(
            result["actor_memories"][actor_id])
    assert CUSTODIAN_ONLY_TOKEN in all_prompt_text(models["custodian"])

    # Private contexts stay with their owners.
    for owner, token in (("requester", "PRIV_REQ_TOKEN"),
                         ("operator", "PRIV_OP_TOKEN"),
                         ("custodian", "PRIV_CUS_TOKEN")):
        assert token in all_prompt_text(models[owner])
        for other in ("requester", "operator", "custodian"):
            if other != owner:
                assert token not in all_prompt_text(models[other])
        assert token not in all_prompt_text(models["gm"])
        assert token not in json.dumps(result["gm_memory"])

    # --- GM model exactness: one observer question per step, nothing else.
    assert len(models["gm"].prompts) == MAX_STEPS
    assert all(AWARE_QUESTION_NEEDLE in prompt
               for prompt in models["gm"].prompts)


def test_outcome_is_read_from_trace():
    _world, _plan, _models, result = _run_once()
    outcome = _evaluate_from_trace(result["event_trace"])
    assert outcome["session_confirmed"] is True
    assert outcome["scheduling_conflict_surfaced"] is True
    assert outcome["confirmed_ids"], (
        "a trace-read outcome must cite the events it was computed from")
    # The confirming commitment was recorded by the custodian's own turn,
    # visible in the trace as the final resolved event.
    last_event = result["event_trace"][-1]
    assert "SESSION_CONFIRMED_1" in last_event["description"]
    assert outcome["confirmed_ids"] == [last_event["event_id"]]
    # R3: the engine stop is 'cutoff' (budget), never an automatic
    # failure; success here was decided by the trace evaluator above.
    assert result["terminal_status"] == "cutoff"
