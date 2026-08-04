"""End-to-end plumbing of the scenario driver, with a stubbed provider.

This test does NOT produce experiment artifacts and makes no claim about
any real person: it builds a synthetic compiled artifact set with the
scenario's cast names and drives ``runner_peter._run_scenario`` with a
stub in place of the provider, so the whole artifact layout, the freeze
manifest, the step ledgers, the evaluator ledger, and the world/plan
reuse proof are exercised without spending live calls.

The LIVE experiment is the artifact set under
``artifacts/full_trace_validation_20260804/``; nothing this test writes
ever goes there.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

if sys.version_info < (3, 12):
    pytest.skip("harness suite runs in the pinned engine environment "
                "(Python >= 3.12)", allow_module_level=True)

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from experiments.full_trace_validation import (  # noqa: E402
    freeze as freeze_lib, recorder as rec, report as report_lib,
    runner_peter, scenario_peter as scenario)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VECTOR = (REPO_ROOT / "tests" / "engine_compilation" / "vectors"
          / "compiled_scene_artifact")

START = "2026-08-04T12:00:00Z"
CUTOFF = "2026-08-11T12:00:00Z"

#: a stub reply that the experiment's own predicates should score as
#: agreement, so the measurement path is exercised end to end
STUB_RECIPIENT_REPLY = (
    "Peter Thiel replies to the message: yes, happy to talk. Send me a "
    "few times for a 20-minute call next week.")
STUB_SENDER_ACTION = (
    "Beckett Zahedi sends the drafted message and waits for an answer.")


def _synthetic_compiler_dir(target: Path) -> None:
    """A compiled artifact set carrying the scenario's cast names.

    Synthetic INPUT for a plumbing test only -- the live experiment
    compiles its world with the real compiler.
    """
    target.mkdir(parents=True, exist_ok=True)
    for name in ("compiler_metrics.json", "final_scene_manifest.json",
                 "input.json", "validation_report.json"):
        shutil.copy(VECTOR / name, target / name)
    manifest = json.loads(
        (target / "final_scene_manifest.json").read_text(encoding="utf-8"))
    rename = {manifest["actors"][0]["name"]: scenario.DECISION_OWNER_NAME,
              manifest["actors"][1]["name"]: scenario.RECIPIENT_NAME}
    for actor in manifest["actors"]:
        actor["name"] = rename[actor["name"]]
    for event in manifest["starting_events"]:
        event["visible_to"] = [rename.get(name, name)
                               for name in event["visible_to"]]
        event["time"] = START
    (target / "final_scene_manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    data = json.loads((target / "input.json").read_text(encoding="utf-8"))
    data["start"], data["cutoff"] = START, CUTOFF
    (target / "input.json").write_text(json.dumps(data, indent=1),
                                       encoding="utf-8")


def _install(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "artifacts"
    monkeypatch.setattr(runner_peter, "ARTIFACT_ROOT", root)
    monkeypatch.setattr(runner_peter, "SUPPLIED_DIR", root / "peter_supplied")
    monkeypatch.setattr(runner_peter, "GENERATED_DIR",
                        root / "peter_generated")
    monkeypatch.setattr(runner_peter, "SHARED_DIR", root / "shared")
    monkeypatch.setattr(runner_peter, "COMPILER_DIR",
                        root / "peter_supplied" / "compiler")
    monkeypatch.setattr(runner_peter, "RUN_IDENTITY_PATH",
                        root / "shared" / "run_identity.json")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-stub-key-for-plumbing-only")
    _synthetic_compiler_dir(root / "peter_supplied" / "compiler")
    identity = {
        "run_start_utc": START, "cutoff_utc": CUTOFF,
        "compiler_version": "minimal_scene_v1",
        "compiler_out_dir": "synthetic",
        "question": "plumbing question", "context": "plumbing context",
        "evidence_package": "plumbing evidence package",
    }
    (root / "shared").mkdir(parents=True, exist_ok=True)
    (root / "shared" / "run_identity.json").write_text(
        json.dumps(identity), encoding="utf-8")
    return root


def _stub_provider(monkeypatch, *, generator_payload=None):
    def fake(*, api_key, model, messages, max_tokens, timeout_s,
             response_format=None):
        del api_key, model, max_tokens, timeout_s
        prompt = messages[-1]["content"]
        if response_format is not None:
            return json.dumps(generator_payload or {"candidates": []}), {}
        if "Which entities are aware" in prompt:
            return (f"{scenario.DECISION_OWNER_NAME}, "
                    f"{scenario.RECIPIENT_NAME}"), {}
        if scenario.RECIPIENT_NAME in messages[0]["content"]:
            return STUB_RECIPIENT_REPLY, {"prompt_tokens": 1,
                                          "completion_tokens": 1}
        return STUB_SENDER_ACTION, {"prompt_tokens": 1,
                                    "completion_tokens": 1}

    monkeypatch.setattr(rec, "_chat_completion", fake)
    monkeypatch.setattr(rec.time, "sleep", lambda seconds: None)


def test_supplied_scenario_produces_the_complete_artifact_layout(
        tmp_path, monkeypatch):
    root = _install(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    code = runner_peter._run_scenario(
        scenario_id="peter_supplied", out_dir=root / "peter_supplied",
        generated=False, progress=None)
    assert code == 0

    out = root / "peter_supplied"
    for name in ("decision_problem.json", "evidence_manifest.json",
                 "freeze_manifest.json", "evaluator_ledger.json",
                 "recommendation_result.json"):
        assert (out / name).is_file(), name
    assert (out / "adapter" / "adapted_world.json").is_file()
    assert (out / "candidates" / "candidates.json").is_file()

    candidates = json.loads(
        (out / "candidates" / "candidates.json").read_text(encoding="utf-8"))
    assert [c["candidate_id"] for c in candidates] == [
        "user_001", "user_002", "user_003"]
    assert all(c["provenance"]["source"] == "user_supplied"
               for c in candidates)

    for candidate in candidates:
        branch = out / "branches" / candidate["candidate_id"]
        for name in ("llm_calls.jsonl", "step_ledger.jsonl",
                     "observations.jsonl", "guard_ledger.jsonl",
                     "committed_events.jsonl", "branch_result.json",
                     "trace_report.json"):
            assert (branch / name).is_file(), f"{candidate} / {name}"

    frozen = freeze_lib.load_manifest(out / "freeze_manifest.json")
    assert frozen["missing_required_entries"] == []


def test_step_ledger_carries_the_required_per_step_material(tmp_path,
                                                            monkeypatch):
    root = _install(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    runner_peter._run_scenario(scenario_id="peter_supplied",
                               out_dir=root / "peter_supplied",
                               generated=False, progress=None)
    path = (root / "peter_supplied" / "branches" / "user_001"
            / "step_ledger.jsonl")
    rows = [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]
    banner, steps = rows[0], rows[1:]
    assert banner["_artifact_class"] == "AUDITOR_ONLY"
    assert steps, "the branch produced no step records"
    required = ("simulation_time", "active_actor", "actor_private_context",
                "shared_context", "observations_delivered",
                "memory_retrieved", "action_spec", "actor_model_request",
                "actor_raw_response", "attempted_action",
                "game_master_input", "game_master_raw_response",
                "candidate_event_before_guard", "guard",
                "final_committed_event", "recipients",
                "observations_created", "state_hash_after_step",
                "termination_check")
    for record in steps:
        for field in required:
            assert field in record, field
    first = steps[0]
    assert first["active_actor"]["name"] == scenario.DECISION_OWNER_NAME
    assert isinstance(first["actor_model_request"], list)
    assert first["actor_model_request"][0]["call_id"]
    assert first["recipients"]["names"]
    # a field the engine genuinely does not expose is MARKED, not guessed
    assert "unavailable" in first["simulation_time"]


def test_the_evaluator_ledger_cites_only_the_recipients_own_turn(
        tmp_path, monkeypatch):
    root = _install(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    runner_peter._run_scenario(scenario_id="peter_supplied",
                               out_dir=root / "peter_supplied",
                               generated=False, progress=None)
    ledger = json.loads((root / "peter_supplied"
                         / "evaluator_ledger.json").read_text(
                             encoding="utf-8"))
    assert ledger["recipient_actor"] == scenario.RECIPIENT_NAME
    branch = ledger["branches"][0]
    assert set(branch["metrics"]) == {"call_agreed", "positive_reply",
                                      "no_explicit_decline"}
    explanation = branch["predicate_explanation"]
    assert explanation["recipient_name"] == scenario.RECIPIENT_NAME
    for turn in explanation["recipient_own_turns"]:
        assert scenario.RECIPIENT_NAME not in turn["content"][:1], turn
    assert branch["terminal_status"] in ("success", "failure", "cutoff",
                                         "incomplete")


def test_generated_scenario_reuses_the_same_world_and_base_plan(
        tmp_path, monkeypatch):
    root = _install(monkeypatch, tmp_path)
    _stub_provider(monkeypatch, generator_payload={"candidates": [
        {"summary": "option one", "action": "Send the first drafted "
                                            "message inside the window."},
        {"summary": "option two", "action": "Send the second drafted "
                                            "message inside the window."}]})
    assert runner_peter._run_scenario(
        scenario_id="peter_supplied", out_dir=root / "peter_supplied",
        generated=False, progress=None) == 0
    assert runner_peter._run_scenario(
        scenario_id="peter_generated", out_dir=root / "peter_generated",
        generated=True, progress=None) == 0

    proof = json.loads((root / "peter_generated"
                        / "world_reuse_proof.json").read_text(
                            encoding="utf-8"))
    assert proof["compiler_llm_calls_in_this_scenario"] == 0
    for name in runner_peter.REUSED_ENTRIES:
        assert proof["entries"][name]["equal"] is True

    supplied = freeze_lib.load_manifest(
        root / "peter_supplied" / "freeze_manifest.json")
    generated = freeze_lib.load_manifest(
        root / "peter_generated" / "freeze_manifest.json")
    assert freeze_lib.entry_sha(supplied, "compiled_decision_world") == \
        freeze_lib.entry_sha(generated, "compiled_decision_world")
    assert freeze_lib.entry_sha(
        supplied, "concordia_initialization_plan") == \
        freeze_lib.entry_sha(generated, "concordia_initialization_plan")
    # only the problem, the candidate set and the seeds may differ
    assert freeze_lib.entry_sha(supplied, "decision_problem") != \
        freeze_lib.entry_sha(generated, "decision_problem")

    candidates = json.loads((root / "peter_generated" / "candidates"
                             / "candidates.json").read_text(
                                 encoding="utf-8"))
    assert [c["candidate_id"] for c in candidates] == ["gen_001", "gen_002"]
    assert all(c["provenance"]["source"] == "generated" for c in candidates)
    for name in ("generator_prompt.txt", "generator_raw_response.txt",
                 "generator_parsed.json"):
        assert (root / "peter_generated" / name).is_file(), name


def test_a_run_whose_candidates_never_left_the_sender_is_refused(
        tmp_path, monkeypatch):
    """The shape the LIVE Peter run actually produced, driven end to end.

    The stub sender keeps its own fixed line instead of restating the
    candidate it was handed, so no candidate text reaches the recipient.
    The runner must complete -- every ledger, trace, and check written --
    while the RANKING is refused: no winner, the refusal recorded where
    the recommendation would have been, and a report that says so.
    Before defect D2 was closed this same run published a winner.
    """
    root = _install(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    assert runner_peter._run_scenario(
        scenario_id="peter_supplied", out_dir=root / "peter_supplied",
        generated=False, progress=None) == 0
    out = root / "peter_supplied"

    refusal = json.loads(
        (out / "recommendation_result.json").read_text(encoding="utf-8"))
    assert refusal["refused"] is True
    assert refusal["error_type"] == "InterventionNotDeliveredError"
    assert "refusing to rank" in refusal["reason"]
    assert "best_candidate_id" not in refusal
    assert set(refusal["per_branch_delivery"]) == {"user_001", "user_002",
                                                   "user_003"}
    for fact in refusal["per_branch_delivery"].values():
        assert fact["status"] == "not_delivered"
        assert fact["reached_actors"] == []

    ledger = json.loads(
        (out / "evaluator_ledger.json").read_text(encoding="utf-8"))
    assert ledger["ranking"]["refused"] is True
    assert "best_candidate_id" not in ledger["ranking"]
    assert (out / "ranking_refusal.json").is_file()

    # the report generator renders the refusal rather than a comparison
    text = report_lib.build_report(root, out)
    assert text.startswith("# UNCALIBRATED LIVE-MODEL EXPLORATORY "
                           "SIMULATION")
    assert "RANKING REFUSED" in text
    assert "No winner is reported for this scenario" in text
    assert "## 12. " not in text


def test_a_mismatched_world_fails_the_reuse_proof_loudly(tmp_path):
    left = {"entries": {"compiled_decision_world": {"sha256": "aaa"}}}
    right = {"entries": {"compiled_decision_world": {"sha256": "bbb"}}}
    with pytest.raises(AssertionError, match="did not reuse"):
        freeze_lib.assert_entries_equal(left, right,
                                        ("compiled_decision_world",))


def test_instrumentation_proves_no_call_bypassed_the_recorder(
        tmp_path, monkeypatch):
    root = _install(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    runner_peter._run_scenario(scenario_id="peter_supplied",
                               out_dir=root / "peter_supplied",
                               generated=False, progress=None)
    payload = json.loads(
        (root / "shared" / "instrumentation_peter_supplied.json").read_text(
            encoding="utf-8"))
    proof = payload["equality_proof"]
    assert proof["all_equal"] is True
    assert proof["ledger_records_written"] > 0
    master = rec.read_ledger(root / "peter_supplied"
                             / "all_llm_calls.jsonl")
    assert len(master) == proof["ledger_records_written"]
    assert len({record["call_id"] for record in master}) == len(master)
    roles = {record["role"] for record in master}
    assert roles <= {"actor", "game_master"}
