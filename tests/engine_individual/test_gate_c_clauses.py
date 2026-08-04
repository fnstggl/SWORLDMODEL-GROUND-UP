"""Gate C proof battery: one test per acceptance-gate clause.

Each test is named for the clause of acceptance gate C ("Individual
simulation") it proves, on fixture 1's two-person message decision:

  - private context remains private
        -> test_private_context_stays_private
  - shared context is shared
        -> test_shared_context_is_shared
  - observations reach only intended actors
        -> test_observations_reach_only_intended_actors
  - actor memory persists across multiple turns
        -> test_actor_memory_persists_across_multiple_turns
  - one actor cannot choose another actor's voluntary response
        -> test_actor_cannot_choose_another_actors_voluntary_response
  - the Game Master cannot directly satisfy the success criterion by
    narration
        -> test_gm_cannot_satisfy_success_criterion_by_narration
  - the trajectory reaches success, failure, cutoff, or explicit
    incomplete status
        -> test_trajectory_reaches_explicit_terminal_status_for_all_four
  - artifacts contain the complete causal trace
        -> proven by test_trace_report_carries_the_complete_causal_chain
           (test_individual_slice_scripted.py) and re-exercised by every
           trace-report assertion below
  - repeated executions do not fail mechanically
        -> test_repeated_executions_do_not_fail_mechanically

Scenario worlds that need extra structure (a single-observer starting
event; a narration row textually claiming the outcome) are TEST-OWNED
world variants built strictly through the frozen ``CompiledDecisionWorld``
contract gate -- the frozen fixture file itself is never modified.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine individual-slice suite requires Python >= 3.12 "
        "(Concordia floor); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from individual_helpers import (ACTOR_TURN_ANCHOR, MAX_STEPS,
                                RECIPIENT_CTA, REPLY_AGREE_PHRASE, SEED,
                                SENDER_CTA, RaisingModel,
                                StrictScriptedModel, all_prompt_text,
                                anchored_predicates, aware_rule,
                                fixture_status_rule, load_fixture_one,
                                make_candidate, route_action_map,
                                run_scripted_slice)
from sworldmodel.backends.concordia_local.guard import AVAILABILITY_MARKER
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            TERMINAL_STATUSES)
from sworldmodel.decision.registry import ContractRegistry
from sworldmodel.outcomes import evaluate_branches
from sworldmodel.reporting import (build_trace_report,
                                   report_canonical_json,
                                   trace_report_canonical_json,
                                   validate_trace_report)

#: test-owned canary for the single-observer starting event
RECIPIENT_ONLY_CANARY = "RECIPIENT_ONLY_EVENT_CANARY_7f31"
#: test-owned narration text that textually CLAIMS the success outcome
NARRATED_REPLY_CLAIM = ("Morgan: Reply agreeing to a fifteen-minute "
                        "conversation next week.")


@pytest.fixture(scope="module")
def slice_outcome():
    """One shared scripted slice pass; tests treat it as read-only."""
    return run_scripted_slice()


def _private_texts(fx) -> dict:
    return {actor.actor_id: actor.private_context.strip()
            for actor in fx.world.actors}


def _world_variant(fx, world_id: str, starting_events) \
        -> tuple[CompiledDecisionWorld, ContractRegistry]:
    """A test-owned world built strictly through the frozen contract
    gate: the fixture world with a different id and the given pre-start
    events.  The frozen fixture file is untouched."""
    data = fx.world.to_dict()
    data["world_id"] = world_id
    data["starting_events"] = list(starting_events)
    world = CompiledDecisionWorld.from_dict(data)
    registry = ContractRegistry()
    registry.register_world(world)
    return world, registry


def test_private_context_stays_private(slice_outcome):
    """Neither actor's private context ever reaches the other actor's
    prompts or memory, and it never enters the committed event stream."""
    outcome = slice_outcome
    private = _private_texts(outcome.fx)
    assert private["sender"] and private["recipient"]

    for candidate in outcome.inputs.candidates:
        candidate_id = candidate.candidate_id
        capture = outcome.capture[candidate_id]
        sender_prompts = all_prompt_text(capture["sender"])
        recipient_prompts = all_prompt_text(capture["recipient"])

        # Each actor sees its OWN private context (the test would be
        # vacuous otherwise)...
        assert private["sender"] in sender_prompts
        assert private["recipient"] in recipient_prompts
        # ...and never the other actor's.
        assert private["recipient"] not in sender_prompts
        assert private["sender"] not in recipient_prompts

        raw = outcome.run.runner_records[candidate_id]
        assert not any(private["recipient"] in row
                       for row in raw["actor_memories"]["sender"])
        assert not any(private["sender"] in row
                       for row in raw["actor_memories"]["recipient"])
        for event in raw["committed_events"]:
            assert private["sender"] not in event
            assert private["recipient"] not in event

        # And the causal trace artifact reflects the same containment.
        branch = {b["candidate_id"]: b
                  for b in outcome.trace["branches"]}[candidate_id]
        sender_rows = branch["actor_records"]["sender"]["observations"]
        recipient_rows = branch["actor_records"]["recipient"][
            "observations"]
        assert not any(private["recipient"] in row for row in sender_rows)
        assert not any(private["sender"] in row for row in recipient_rows)


def test_shared_context_is_shared(slice_outcome):
    """The world's shared context reaches BOTH actors: their prompts,
    their recorded observation streams, and the trace artifact."""
    outcome = slice_outcome
    shared = outcome.fx.world.shared_context.strip()
    assert shared

    for candidate in outcome.inputs.candidates:
        candidate_id = candidate.candidate_id
        capture = outcome.capture[candidate_id]
        assert shared in all_prompt_text(capture["sender"])
        assert shared in all_prompt_text(capture["recipient"])
        raw = outcome.run.runner_records[candidate_id]
        for actor_id in ("sender", "recipient"):
            assert any(shared in row
                       for row in raw["actor_memories"][actor_id])
        branch = {b["candidate_id"]: b
                  for b in outcome.trace["branches"]}[candidate_id]
        for actor_id in ("sender", "recipient"):
            rows = branch["actor_records"][actor_id]["observations"]
            assert any(shared in row for row in rows)


def test_observations_reach_only_intended_actors():
    """A pre-start event visible to ONE actor reaches exactly that actor:
    the recipient observes the canary, the sender never does -- while the
    game master's own pre-start record keeps the full event."""
    fx = load_fixture_one()
    world, registry = _world_variant(
        fx, "w_single_observer_check",
        [{"description": ("A private note reading "
                          f"{RECIPIENT_ONLY_CANARY} reaches one desk."),
          "visible_to": ["recipient"],
          "time": "2026-08-03T14:00:00Z"}])
    candidate = make_candidate(
        "observer_check", "Send a plain note asking for a short call.")

    capture: dict = {}

    def factory(cand, branch_seed):
        sender = StrictScriptedModel([(SENDER_CTA, [cand.action])])
        recipient = StrictScriptedModel([(RECIPIENT_CTA, [
            "Morgan notes the situation and continues without responding."
        ])])
        gm = StrictScriptedModel([aware_rule(["Alex", "Morgan"])])
        capture["models"] = {"sender": sender, "recipient": recipient}
        return {"sender": sender, "recipient": recipient}, gm

    run = run_candidates_detailed(
        world, [candidate], model_factory=factory, seed=SEED,
        max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=registry)
    result = run.results[0]
    assert result.infrastructure_errors == ()
    raw = run.runner_records["observer_check"]

    # The intended actor observed the canary (prompt AND memory)...
    recipient_prompts = all_prompt_text(capture["models"]["recipient"])
    assert RECIPIENT_ONLY_CANARY in recipient_prompts
    assert any(RECIPIENT_ONLY_CANARY in row
               for row in raw["actor_memories"]["recipient"])
    # ...the other actor never did, anywhere.
    sender_prompts = all_prompt_text(capture["models"]["sender"])
    assert RECIPIENT_ONLY_CANARY not in sender_prompts
    assert not any(RECIPIENT_ONLY_CANARY in row
                   for row in raw["actor_memories"]["sender"])
    # The GM's pre-start record keeps the event (it IS the world record).
    assert any(RECIPIENT_ONLY_CANARY in event
               for event in raw["committed_events"])

    # The causal trace artifact shows the same asymmetry.
    trace = build_trace_report(run)
    validate_trace_report(trace)
    branch = trace["branches"][0]
    recipient_rows = branch["actor_records"]["recipient"]["observations"]
    sender_rows = branch["actor_records"]["sender"]["observations"]
    assert any(RECIPIENT_ONLY_CANARY in row for row in recipient_rows)
    assert not any(RECIPIENT_ONLY_CANARY in row for row in sender_rows)


def test_actor_memory_persists_across_multiple_turns():
    """Over FOUR engine steps (two full rotations) the recipient's later
    turn is prompted with its own earlier observation and committed
    action -- and its scripted second action explicitly references the
    first (the reference text exists nowhere in turn one's script)."""
    fx = load_fixture_one()
    candidate = fx.candidates[1]  # the concise fixture message
    first_reply = f"Reply {REPLY_AGREE_PHRASE} next week."
    followup = ("Confirm the agreed fifteen-minute conversation and "
                "propose Tuesday morning.")

    capture: dict = {}

    def factory(cand, branch_seed):
        sender = StrictScriptedModel([(SENDER_CTA, [
            cand.action, "Alex waits patiently for a response."])])
        recipient = StrictScriptedModel([(RECIPIENT_CTA, [
            first_reply, followup])])
        gm = StrictScriptedModel([aware_rule(["Alex", "Morgan"])])
        capture["models"] = {"sender": sender, "recipient": recipient}
        return {"sender": sender, "recipient": recipient}, gm

    run = run_candidates_detailed(
        fx.world, [candidate], model_factory=factory, seed=SEED,
        max_steps=4, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)
    result = run.results[0]
    assert result.infrastructure_errors == ()
    assert result.terminal_status == "cutoff"

    # The recipient acted TWICE; its second prompt carries its own
    # first-turn action and the sender's message -- memory persisted
    # across turns (turn one's content was only ever delivered before
    # turn one, so its presence at turn two IS persistence).
    recipient_prompts = capture["models"]["recipient"].prompts
    assert len(recipient_prompts) == 2
    assert first_reply in recipient_prompts[1]
    assert first_reply not in recipient_prompts[0]
    assert candidate.action.strip() in recipient_prompts[1]

    # Commit order in the trace: premise, sender, recipient turn one,
    # sender again, recipient turn two.  The second action references
    # the agreement introduced in turn one ('fifteen-minute
    # conversation' text), and appears nowhere before step four.
    descriptions = [event.description for event in result.event_trace]
    assert len(descriptions) == 5
    assert first_reply in descriptions[2]
    assert followup in descriptions[4]
    assert "fifteen-minute conversation" in followup
    assert not any(followup in text for text in descriptions[:4])

    # The causal trace artifact records both attempts with their steps.
    trace = build_trace_report(run)
    validate_trace_report(trace)
    attempts = trace["branches"][0]["actor_records"]["recipient"][
        "attempts"]
    assert [attempt["step"] for attempt in attempts] == [2, 4]
    assert attempts[0]["attempt"] == first_reply
    assert attempts[1]["attempt"] == followup


def test_actor_cannot_choose_another_actors_voluntary_response():
    """A sender turn asserting the recipient's voluntary act is rewritten
    by the hardened agency guard BEFORE commit: the assertion is removed,
    the availability sentence is appended, the escalation is recorded,
    and the recipient still takes its own turn."""
    fx = load_fixture_one()
    candidate = make_candidate(
        "agency_probe", "Send the planned note and assume agreement.")
    asserted_clause = "Morgan agrees to the plan immediately."

    capture: dict = {}

    def factory(cand, branch_seed):
        sender = StrictScriptedModel([(SENDER_CTA, [
            f"Send the planned note. {asserted_clause}"])])
        recipient = StrictScriptedModel([(RECIPIENT_CTA, [
            "Morgan reads the note carefully and considers it."])])
        gm = StrictScriptedModel([aware_rule(["Alex", "Morgan"])])
        capture["models"] = {"sender": sender, "recipient": recipient}
        return {"sender": sender, "recipient": recipient}, gm

    run = run_candidates_detailed(
        fx.world, [candidate], model_factory=factory, seed=SEED,
        max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)
    result = run.results[0]
    assert result.infrastructure_errors == ()
    raw = run.runner_records["agency_probe"]

    # The committed sender event lost the asserted decision and gained
    # the availability sentence naming the affected actor.
    sender_event = result.event_trace[1].description
    assert asserted_clause not in sender_event
    assert "Send the planned note." in sender_event
    assert AVAILABILITY_MARKER in sender_event
    assert f"Morgan {AVAILABILITY_MARKER}" in sender_event
    # No committed event anywhere asserts the recipient's decision.
    for event in raw["committed_events"]:
        assert asserted_clause not in event

    # Exactly one escalation record, fully attributed.
    interventions = raw["guard_interventions"]
    assert len(interventions) == 1
    record = interventions[0]
    assert record["step"] == 1
    assert record["active"] == "Alex"
    assert record["affected"] == ["Morgan"]
    assert "Morgan agrees" in record["original_excerpt"]
    assert AVAILABILITY_MARKER in record["rewritten_excerpt"]

    # The recipient then received ITS OWN turn and its committed action
    # is its scripted choice, not the sender's assertion.
    recipient_prompts = capture["models"]["recipient"].prompts
    assert len(recipient_prompts) == 1
    assert "reads the note carefully" in result.event_trace[2].description

    # The escalation is part of the causal trace artifact.
    trace = build_trace_report(run)
    validate_trace_report(trace)
    assert trace["branches"][0]["guard_interventions"] == interventions


def test_gm_cannot_satisfy_success_criterion_by_narration(slice_outcome):
    """A Game-Master-authored narration row textually CLAIMING the reply
    must not count as success: the evaluator's success metric binds only
    to actor-attributed resolved turns, so the narration branch measures
    False (and stays 'cutoff'), while in the control branch every
    success citation resolves to the recipient's OWN committed turn.

    (In this build the GM's only narration channels are the neutral
    premise and the pre-start event record -- the event-resolution chain
    has no narrative-push step and the observation queue never invents
    text -- so the pre-start record IS the GM narration channel.)"""
    fx = load_fixture_one()
    world, registry = _world_variant(
        fx, "w_gm_narration_check",
        [{"description": f"A confident rumor circulates: {NARRATED_REPLY_CLAIM}",
          "visible_to": ["sender", "recipient"],
          "time": "2026-08-03T14:00:00Z"}])
    candidate = make_candidate(
        "narration_check", "Send a modest note asking for consideration.")

    def factory(cand, branch_seed):
        sender = StrictScriptedModel([(SENDER_CTA, [cand.action])])
        recipient = StrictScriptedModel([(RECIPIENT_CTA, [
            "Morgan files the note away and continues her scheduled work "
            "without responding."])])
        gm = StrictScriptedModel([aware_rule(["Alex", "Morgan"])])
        return {"sender": sender, "recipient": recipient}, gm

    run = run_candidates_detailed(
        world, [candidate], model_factory=factory, seed=SEED,
        max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=registry)
    evaluated = evaluate_branches(
        run.results, anchored_predicates(),
        evaluator_spec=fx.evaluator_spec,
        status_rule=fixture_status_rule, registry=registry)
    result = evaluated[0]
    assert result.infrastructure_errors == ()

    # Non-vacuity: the claiming narration IS in the committed trace...
    narration_rows = [event.description for event in result.event_trace
                      if NARRATED_REPLY_CLAIM in event.description]
    assert len(narration_rows) == 1
    # ...and it is a narration row, not a resolved actor turn.
    assert ACTOR_TURN_ANCHOR not in narration_rows[0]

    # The success metric did NOT count it: measured False, citing the
    # whole-trace scan bound, and the verdict stays the runner's cutoff.
    reply_metric = result.outcome_metrics["recipient_reply_sent"]
    assert reply_metric.value is False
    assert reply_metric.computed_from == ("state:committed_event_count",)
    assert result.outcome_metrics["meeting_scheduled"].value is False
    assert result.terminal_status == "cutoff"

    # Control: in the shared slice's winning branch the metric is True
    # and EVERY citation resolves to the recipient's own resolved turn.
    control = slice_outcome
    winner_result = {r.candidate_id: r for r in control.evaluated}[
        control.report["winner"]]
    winner_metric = winner_result.outcome_metrics["recipient_reply_sent"]
    assert winner_metric.value is True
    rows_by_id = {event.event_id: event.description
                  for event in winner_result.event_trace}
    for reference in winner_metric.computed_from:
        kind, _, target = reference.partition(":")
        assert kind == "event"
        row = rows_by_id[target]
        assert ACTOR_TURN_ANCHOR in row
        assert "Morgan: Reply" in row


def test_trajectory_reaches_explicit_terminal_status_for_all_four(
        slice_outcome):
    """Four scripted scenarios, one per terminal status: the fixture's
    three candidates measure success / failure / cutoff, and an injected
    mid-branch model failure yields an explicit 'incomplete' with the
    error recorded and the partial trace preserved."""
    outcome = slice_outcome
    mapping = route_action_map(outcome.fx, outcome.inputs)
    by_fixture_id = {mapping[result.candidate_id]: result
                     for result in outcome.evaluated}
    assert by_fixture_id["concise_relevant"].terminal_status == "success"
    assert by_fixture_id["urgent_pressure"].terminal_status == "failure"
    assert by_fixture_id["long_generic"].terminal_status == "cutoff"

    # Scenario four: the recipient's model fails mid-branch.
    fx = load_fixture_one()
    candidate = make_candidate(
        "incomplete_check", "Send a note into an unreliable channel.")

    def factory(cand, branch_seed):
        sender = StrictScriptedModel([(SENDER_CTA, [cand.action])])
        recipient = RaisingModel("GATE_C_INJECTED_MODEL_FAILURE")
        gm = StrictScriptedModel([aware_rule(["Alex", "Morgan"])])
        return {"sender": sender, "recipient": recipient}, gm

    run = run_candidates_detailed(
        fx.world, [candidate], model_factory=factory, seed=SEED,
        max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)
    result = run.results[0]
    assert result.terminal_status == "incomplete"
    assert any("GATE_C_INJECTED_MODEL_FAILURE" in error
               for error in result.infrastructure_errors)
    # The partial trace up to the failure is preserved, never discarded.
    assert len(result.event_trace) == 2  # premise + sender turn
    trace = build_trace_report(run)
    validate_trace_report(trace)
    assert trace["branches"][0]["terminal_status"] == "incomplete"

    # Every observed status is an EXPLICIT member of the closed set.
    statuses = {result.terminal_status
                for result in outcome.evaluated} | {"incomplete"}
    assert statuses == set(TERMINAL_STATUSES)


def test_repeated_executions_do_not_fail_mechanically():
    """The same scenario three times in one process: zero infrastructure
    errors and byte-identical artifacts every time."""
    passes = [run_scripted_slice() for _ in range(3)]
    for outcome in passes:
        for result in list(outcome.run.results) + list(outcome.evaluated):
            assert result.infrastructure_errors == ()
        for branch in outcome.trace["branches"]:
            assert branch["terminal_status"] in TERMINAL_STATUSES

    reference_report = report_canonical_json(passes[0].report)
    reference_trace = trace_report_canonical_json(passes[0].trace)
    for outcome in passes[1:]:
        assert report_canonical_json(outcome.report) == reference_report
        assert trace_report_canonical_json(outcome.trace) \
            == reference_trace
