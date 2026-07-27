"""End-to-end discovery pipeline with a stubbed model: five discovery
answers and four binding answers drive the toy world from question to a
trajectory-produced terminal, with zero real model calls. This is the
proof that code -- not the model -- assembles, connects and executes the
representation."""
import copy
import json
import os

import pytest

from compiler.binding import bind_world
from compiler.assemble import assemble
from compiler.errors import COMPILED, UnsupportedCapability
from compiler.worldcompiler import compile_question
from tests.fixtures_discovery import (EVIDENCE_IDS, PRODUCERS, RESOLUTION,
                                      SPINE, STATE_INFO, UNCERTAINTY, docs)

QUESTION = {
    "question": "Will Alice have read Bob's confirmation before Friday "
                "17:00?",
    "deadline": "2026-03-06T17:00:00-05:00",
    "resolution_note": "Receiving it in an unread inbox does not count.",
}

EVIDENCE = {"claims": [
    {"id": i, "claim": c, "source": "fixture", "status": "verified",
     "visibility": "public", "as_of": "2026-03-01T00:00:00-05:00"}
    for i, c in (
        ("e1", "Alice Chen needs written confirmation from Bob Marsh."),
        ("e2", "Both use the company email system."),
        ("e3", "Alice works Monday to Friday from her desk."),
        ("e4", "Bob checks his inbox about hourly on workdays."),
        ("e5", "Nobody else reads Bob's inbox."),
    )]}

BINDINGS = {
    "alice sends the request": {
        "duration_minutes": 5, "duration_status": "model_memory_unverified",
        "duration_note": "writing a short request email", "parameters": []},
    "bob sends a confirmation": {
        "duration_minutes": 5, "duration_status": "model_memory_unverified",
        "duration_note": "writing a short reply", "parameters": []},
    "alice reads the confirmation": {
        "duration_minutes": 3, "duration_status": "model_memory_unverified",
        "duration_note": "reading a short reply", "parameters": []},
}


def fake_call(system, user, model="stub", **kw):
    def out(doc):
        return doc, json.dumps(doc), {"total_tokens": 0}
    if "STEP 1" in system:
        r = copy.deepcopy(RESOLUTION)
        r["cutoff"]["when"] = "2026-03-06T17:00:00-05:00"
        return out(r)
    if "STEP 2" in system:
        return out(copy.deepcopy(SPINE))
    if "STEP 3" in system:
        return out(copy.deepcopy(PRODUCERS))
    if "STEP 4" in system:
        for ent in STATE_INFO["entities"]:
            if json.dumps(ent["name"]) in system:
                e = copy.deepcopy(ent)
                for c in e.get("commitments") or []:
                    c["when"] = "2026-03-02T09:00:00-05:00"
                return out(e)
        raise AssertionError("unknown entity in: " + system[-200:])
    if "STEP 5" in system:
        return out(copy.deepcopy(UNCERTAINTY))
    if "binding step" in system:
        item = json.loads(user.split("\n\nReturn JSON")[0]
                          .split("):\n", 1)[1])
        if "route" in item:
            return out({"delivery_seconds": 60,
                        "status": "model_memory_unverified",
                        "note": "ordinary corporate email"})
        if "action" in item:
            return out(copy.deepcopy(BINDINGS[item["action"]]))
        raise AssertionError("unexpected binding item: " + user[:200])
    raise AssertionError("unrecognized prompt: " + system[:120])


SCRIPT = {
    "Alice Chen": [
        {"trigger": "wake_reason", "reason": "scheduled_alice_workday_starts",
         "action": "alice sends the request", "why": "fixture step 1"},
        {"trigger": "notices", "tag": "bobs confirmation available to alice",
         "action": "alice reads the confirmation",
         "bind_from_notice": {"bobs_confirmation_available_to_alice": "id"},
         "why": "fixture step 3"},
    ],
    "Bob Marsh": [
        {"trigger": "notices", "tag": "bob has seen alices request",
         "action": "bob sends a confirmation",
         "bind_from_notice": {"bob_has_seen_alices_request": "id"},
         "why": "fixture step 2"},
    ],
}


def run_pipeline(tmp_path, scripts, name="toy"):
    return compile_question(QUESTION, copy.deepcopy(EVIDENCE),
                            str(tmp_path / name), scripts=scripts,
                            call=fake_call)


def test_compiles_and_answers_from_the_trajectory(tmp_path):
    record = run_pipeline(tmp_path, SCRIPT)
    assert record["stage"] == COMPILED
    ans = record["outcome"].answer
    assert ans["answer"] == "yes"
    assert ans["computed_from"], "the answer must cite real ledger records"
    report = json.loads(
        (tmp_path / "toy" / "terminal_producer_report.json").read_text())
    assert report["replay_hash_match"] is True
    assert record["artifact_risk"] is False


def test_every_stage_artifact_is_written(tmp_path):
    run_pipeline(tmp_path, SCRIPT)
    for name in ("question.json", "evidence_package.json",
                 "resolution_contract.json", "causal_spine.json",
                 "producer_assignments.json",
                 "starting_state_and_information.json",
                 "uncertainty_and_exclusions.json",
                 "canonical_world_graph.json", "assembly_trace.jsonl",
                 "backward_causal_proof.json",
                 "forward_executability_proof.json",
                 "generated_semantic_scenario.json", "approved_scenario.json",
                 "symbol_table.json", "lowering_trace.jsonl",
                 "runtime_world_snapshot.json",
                 "terminal_producer_report.json", "model_calls.jsonl",
                 "metrics.json", "run_manifest.json"):
        assert (tmp_path / "toy" / name).exists(), name


def test_call_accounting_is_honest(tmp_path):
    record = run_pipeline(tmp_path, SCRIPT)
    m = record["metrics"]
    # 4 fixed steps + 2 entities; 3 actions + 1 channel
    assert m["discovery_calls"] == 6
    assert m["binding_calls"] == 4
    assert all(m["first_pass_by_step"].values())
    assert m["repairs_by_step"] == {}
    # model time is billed to the model, never to lowering
    assert m["lowering_ms"] < 5000
    calls = [json.loads(l) for l in
             (tmp_path / "toy" / "model_calls.jsonl").read_text()
             .splitlines()]
    assert len(calls) == 10
    assert all(c["raw_response"] for c in calls)


def test_generated_scenario_is_deterministic(tmp_path):
    run_pipeline(tmp_path, SCRIPT, "a")
    run_pipeline(tmp_path, SCRIPT, "b")
    sa = (tmp_path / "a" / "generated_semantic_scenario.json").read_text()
    sb = (tmp_path / "b" / "generated_semantic_scenario.json").read_text()
    assert sa == sb


def test_the_scenario_never_prewrites_the_trajectory(tmp_path):
    run_pipeline(tmp_path, SCRIPT)
    doc = json.loads((tmp_path / "toy" /
                      "generated_semantic_scenario.json").read_text())
    # the only scheduled event is the evidenced workday anchor; no event
    # creates records, moves quantities or sends the answer
    for ev in doc["scheduled_events"]:
        for eff in ev["effects"]:
            assert eff["change_type"] == "record_fact"
    # every send and every fact write lives on an affordance the actor may
    # or may not take
    assert len(doc["action_affordances"]) == 3
    labels = {a["label"] for a in doc["action_affordances"]}
    assert labels == {"alice sends the request", "bob sends a confirmation",
                      "alice reads the confirmation"}


def test_an_unscripted_world_answers_no_with_a_loud_flag(tmp_path):
    record = run_pipeline(tmp_path, {})
    assert record["stage"] == COMPILED
    assert record["outcome"].answer["answer"] == "no"
    assert record["artifact_risk"] is True
    fidelity = (tmp_path / "toy" / "reality_fidelity_review.md").read_text()
    assert "READ THIS ANSWER WITH CARE" in fidelity


def test_a_proof_failure_routes_one_repair_to_the_producers(tmp_path):
    """First producers answer wrongly marks a needed step unsupported; the
    backward proof refuses; its one repair replays the producers prompt
    with the proof's defects and the corrected answer compiles."""
    state = {"producer_attempts": 0}

    def flaky(system, user, model="stub", **kw):
        if "STEP 3" in system:
            state["producer_attempts"] += 1
            if state["producer_attempts"] == 1:
                doc = copy.deepcopy(PRODUCERS)
                doc["assignments"][2] = {
                    "step": "bob sends a confirmation",
                    "unsupported": "it results from other steps"}
                return doc, json.dumps(doc), {"total_tokens": 0}
        return fake_call(system, user, model, **kw)

    record = compile_question(QUESTION, copy.deepcopy(EVIDENCE),
                              str(tmp_path / "toy"), scripts=SCRIPT,
                              call=flaky)
    assert record["stage"] == COMPILED
    assert state["producer_attempts"] == 2
    assert record["metrics"]["assembly_repairs"] == \
        ["producer_assignments"]
    assert record["outcome"].answer["answer"] == "yes"


def test_unsupported_binding_refuses_with_the_item_named():
    graph, _ = assemble(*docs(), valid_evidence_ids=EVIDENCE_IDS)

    def refuse_channels(system, user, model="stub", **kw):
        if '"route"' in user:
            doc = {"unsupported": "no latency model for carrier pigeons"}
        else:
            doc = {"duration_minutes": 5,
                   "duration_status": "model_memory_unverified",
                   "duration_note": "estimate", "parameters": []}
        return doc, json.dumps(doc), {"total_tokens": 0}

    with pytest.raises(UnsupportedCapability) as ei:
        bind_world(graph, call=refuse_channels)
    items = ei.value.detail["items"]
    assert items and "carrier pigeons" in items[0]["reason"]


def test_directory_is_cleared_between_runs(tmp_path):
    (tmp_path / "toy").mkdir()
    stale = tmp_path / "toy" / "terminal_result.json"
    stale.write_text('{"stale": true}')
    run_pipeline(tmp_path, SCRIPT)
    data = json.loads((tmp_path / "toy" /
                       "terminal_result.json").read_text())
    assert "stale" not in data
