"""The committed live artifact set must stay internally consistent.

These tests read only what was committed: they re-derive the freeze
hashes, re-check the world/plan equality between the two scenarios, and
confirm every ledger record still carries the exact field set. They make
the artifacts falsifiable rather than decorative.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import (freeze as fz,  # noqa: E402
                                               recorder as rec)

ARTIFACTS = REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
SUPPLIED = ARTIFACTS / "peter_supplied"
GENERATED = ARTIFACTS / "peter_generated"

pytestmark = pytest.mark.skipif(
    not ARTIFACTS.is_dir(), reason="the live artifact set is not present")

REUSED = ("compiler_artifact_dir_aggregate", "compiled_decision_world",
          "concordia_initialization_plan",
          "concordia_initialization_plan_content_hash", "evaluator_spec",
          "compiler_inputs", "time_window", "evidence_items",
          "engine_simulation_limits")


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_the_two_scenarios_share_one_world_and_one_base_plan():
    left = fz.load_manifest(SUPPLIED / "freeze_manifest.json")
    right = fz.load_manifest(GENERATED / "freeze_manifest.json")
    proof = fz.assert_entries_equal(left, right, REUSED)
    assert all(entry["equal"] for entry in proof.values())
    # and the scenario delta really is only the declared one
    assert fz.entry_sha(left, "decision_problem") != \
        fz.entry_sha(right, "decision_problem")
    assert fz.entry_sha(left, "candidate_set") != \
        fz.entry_sha(right, "candidate_set")


def test_the_recorded_world_hash_still_matches_the_committed_world():
    for directory in (SUPPLIED, GENERATED):
        manifest = fz.load_manifest(directory / "freeze_manifest.json")
        world = _load(directory / "adapter" / "adapted_world.json")
        # the frozen entry hashed the contract's canonical json; the
        # committed adapter/adapted_world.json is that json parsed, so
        # re-canonicalising it must reproduce the same digest
        assert fz.sha256_json(world) == fz.entry_sha(
            manifest, "compiled_decision_world")


def test_the_compiler_artifact_directory_is_unchanged_since_the_freeze():
    manifest = fz.load_manifest(SUPPLIED / "freeze_manifest.json")
    frozen = manifest["entries"]["compiler_artifact_dir_per_file"]["detail"]
    current = fz.hash_directory(SUPPLIED / "compiler")["per_file"]
    # the harness wrote its own call ledger into the compiler directory
    # AFTER the compiler finished but BEFORE the freeze, so the frozen
    # set is the complete set
    assert set(frozen) == set(current)
    assert frozen == current


def test_every_ledger_record_carries_the_exact_field_set():
    total = 0
    for path in sorted(ARTIFACTS.rglob("*llm_calls.jsonl")):
        for record in rec.read_ledger(path):
            assert set(record) == set(rec.RECORD_FIELDS), path
            assert record["provider"] == rec.PROVIDER
            assert record["model"] == rec.DEEPSEEK_MODEL_ID
            assert isinstance(record["retry"], int)
            assert record["request_sha256"]
            total += 1
    assert total > 0


def test_the_branch_ledgers_are_a_partition_of_the_scenario_ledger():
    for directory in (SUPPLIED, GENERATED):
        master = rec.read_ledger(directory / "all_llm_calls.jsonl")
        master_ids = [record["call_id"] for record in master]
        assert len(master_ids) == len(set(master_ids))
        branch_ids = []
        for path in sorted((directory / "branches").glob(
                "*/llm_calls.jsonl")):
            branch_ids.extend(record["call_id"]
                              for record in rec.read_ledger(path))
        extra = sorted(
            (directory / "generator_llm_calls.jsonl",))
        for path in extra:
            if path.is_file():
                branch_ids.extend(record["call_id"]
                                  for record in rec.read_ledger(path))
        assert sorted(branch_ids) == sorted(master_ids)


def test_success_is_only_ever_cited_from_the_recipients_own_turn():
    for directory in (SUPPLIED, GENERATED):
        evaluator = _load(directory / "evaluator_ledger.json")
        recipient = evaluator["recipient_actor"]
        anchor = evaluator["attribution_anchor"]
        for branch in evaluator["branches"]:
            metric = branch["metrics"]["call_agreed"]
            if not metric["value"]:
                continue
            assert metric["cited_event_texts"], branch["candidate_id"]
            for text in metric["cited_event_texts"]:
                assert anchor in text
                head = text.split(anchor, 1)[1].lstrip()
                assert head.startswith(recipient + ":"), head[:120]


def test_terminal_statuses_come_from_the_closed_set():
    allowed = {"success", "failure", "cutoff", "incomplete"}
    for directory in (SUPPLIED, GENERATED):
        evaluator = _load(directory / "evaluator_ledger.json")
        for branch in evaluator["branches"]:
            assert branch["terminal_status"] in allowed
            if branch["terminal_status"] in ("success", "failure"):
                assert not branch["infrastructure_errors"]


def test_the_step_attribution_check_is_recorded_and_consistent():
    for directory in (SUPPLIED, GENERATED):
        for path in sorted((directory / "branches").glob(
                "*/step_attribution_check.json")):
            record = _load(path)
            assert record["consistent"] is True, path
            assert record["actor_calls_recorded"] == \
                record["steps_completed_reported_by_runner"]
            assert record["raw_log_entries"] == \
                record["steps_completed_reported_by_runner"]
