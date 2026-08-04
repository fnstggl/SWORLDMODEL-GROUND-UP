"""The committed a16z artifact set must stay internally consistent.

These tests read only what was committed: they re-derive the freeze
hashes, re-check the branch-input isolation proof, re-check that the
primary metric is only ever cited from the subject's own turn, and
confirm the ledgers partition exactly.  They make the artifacts
falsifiable rather than decorative.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import (branch_diff,  # noqa: E402
                                               freeze as fz, recorder as rec)

ARTIFACTS = (REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
             / "a16z_richard_historical")

pytestmark = pytest.mark.skipif(
    not ARTIFACTS.is_dir(), reason="the live a16z artifact set is not present")


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _jsonl(path):
    return [json.loads(line) for line
            in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def test_the_freeze_manifest_is_complete():
    manifest = fz.load_manifest(ARTIFACTS / "freeze_manifest.json")
    assert manifest["missing_required_entries"] == []


def test_the_recorded_world_hash_still_matches_the_committed_world():
    manifest = fz.load_manifest(ARTIFACTS / "freeze_manifest.json")
    world = _load(ARTIFACTS / "adapter" / "adapted_world.json")
    assert fz.sha256_json(world) == fz.entry_sha(manifest,
                                                 "compiled_decision_world")


def test_the_compiler_artifact_directory_is_unchanged_since_the_freeze():
    manifest = fz.load_manifest(ARTIFACTS / "freeze_manifest.json")
    frozen = manifest["entries"]["compiler_artifact_dir_per_file"]["detail"]
    current = fz.hash_directory(ARTIFACTS / "compiler")["per_file"]
    assert frozen == current


def test_the_accepted_compile_attempt_was_copied_byte_for_byte():
    proof = _load(ARTIFACTS / "compiler_copy_proof.json")
    assert proof["byte_identical_copy"] is True
    attempts = _load(ARTIFACTS / "compiler_attempts"
                     / "compile_attempts.json")
    accepted = attempts["accepted_attempt"]
    assert accepted is not None
    chosen = [entry for entry in attempts["attempts"]
              if entry["attempt"] == accepted]
    assert chosen and chosen[0]["accepted"] is True
    # every attempt is committed, not only the accepted one
    for entry in attempts["attempts"]:
        assert (ARTIFACTS / "compiler_attempts"
                / f"attempt_{entry['attempt']}"
                / "attempt_verdict.json").is_file()


def test_the_cast_is_exactly_the_five_declared_actors():
    from experiments.full_trace_validation import scenario_a16z as scenario

    world = _load(ARTIFACTS / "adapter" / "adapted_world.json")
    names = sorted(actor["name"] for actor in world["actors"])
    assert names == sorted(scenario.REQUIRED_CAST)


def test_every_ledger_record_carries_the_exact_field_set():
    total = 0
    for path in sorted(ARTIFACTS.rglob("*llm_calls.jsonl")):
        for record in rec.read_ledger(path):
            assert set(record) == set(rec.RECORD_FIELDS), path
            assert record["provider"] == rec.PROVIDER
            assert record["model"] == rec.DEEPSEEK_MODEL_ID
            total += 1
    assert total > 0


def test_the_branch_ledgers_are_a_partition_of_the_scenario_ledger():
    master = rec.read_ledger(ARTIFACTS / "all_llm_calls.jsonl")
    master_ids = [record["call_id"] for record in master]
    assert len(master_ids) == len(set(master_ids))
    branch_ids = []
    for path in sorted((ARTIFACTS / "branches").glob("*/llm_calls.jsonl")):
        branch_ids.extend(record["call_id"]
                          for record in rec.read_ledger(path))
    assert sorted(branch_ids) == sorted(master_ids)


def test_the_compile_ledgers_are_a_partition_of_the_attempt_ledgers():
    master = rec.read_ledger(ARTIFACTS / "compiler_attempts"
                             / "all_llm_calls.jsonl")
    master_ids = sorted(record["call_id"] for record in master)
    assert len(master_ids) == len(set(master_ids))
    attempt_ids = []
    for path in sorted((ARTIFACTS / "compiler_attempts").glob(
            "attempt_*/llm_calls.jsonl")):
        attempt_ids.extend(record["call_id"]
                           for record in rec.read_ledger(path))
    assert sorted(attempt_ids) == master_ids


def test_the_instrumentation_equality_proof_holds():
    payload = _load(ARTIFACTS / "instrumentation_validation.json")
    assert payload["equality_proof"]["all_equal"] is True
    values = payload["equality_proof"]["values"]
    assert len(set(values.values())) == 1
    assert values["ledger_records_written"] > 0


def test_the_primary_metric_is_only_cited_from_the_subjects_own_turn():
    evaluator = _load(ARTIFACTS / "evaluator_ledger.json")
    subject = evaluator["subject_actor"]
    anchor = evaluator["attribution_anchor"]
    for branch in evaluator["branches"]:
        metric = branch["metrics"]["valid_offer_accepted"]
        if not metric["value"]:
            continue
        texts = metric["cited_event_texts"]
        assert texts, branch["candidate_id"]
        owners = []
        for text in texts:
            assert anchor in text
            owners.append(text.split(anchor, 1)[1].lstrip().split(":")[0])
        assert subject in owners, owners


def test_the_secondary_metric_matches_the_code_owned_mapping():
    from experiments.full_trace_validation import scenario_a16z as scenario

    evaluator = _load(ARTIFACTS / "evaluator_ledger.json")
    mapping = scenario.salary_savings_mapping()
    for branch in evaluator["branches"]:
        value = branch["metrics"]["salary_savings_vs_300k"]["value"]
        assert value == float(mapping[branch["candidate_key"]])


def test_the_branch_input_isolation_proof_is_reproducible():
    """Re-derive the proof from the committed plans, not from its verdict."""
    proof = _load(ARTIFACTS / "branch_input_diff.json")
    assert proof["verdict"] == "only_the_salary_differs"
    assert proof["residual_differences_after_masking"] == []
    offers = [entry for entry in proof["per_branch"]
              if entry["candidate_id"] in proof["offer_candidate_ids"]]
    masked = {branch_diff.mask_salaries(entry["candidate_action"])
              for entry in offers}
    assert len(masked) == 1, masked
    assert len({entry["plan_sha256"] for entry in offers}) == len(offers)
    assert len({entry["plan_sha256_salary_masked"]
                for entry in offers}) == 1


def test_terminal_statuses_come_from_the_closed_set():
    allowed = {"success", "failure", "cutoff", "incomplete"}
    evaluator = _load(ARTIFACTS / "evaluator_ledger.json")
    for branch in evaluator["branches"]:
        assert branch["terminal_status"] in allowed
        if branch["terminal_status"] in ("success", "failure"):
            assert not branch["infrastructure_errors"]


def test_the_step_attribution_check_is_recorded_and_consistent():
    for path in sorted((ARTIFACTS / "branches").glob(
            "*/step_attribution_check.json")):
        record = _load(path)
        assert record["consistent"] is True, path
        assert record["raw_log_entries"] == \
            record["steps_completed_reported_by_runner"]


def test_the_offer_delivery_check_covers_every_branch():
    evaluator = _load(ARTIFACTS / "evaluator_ledger.json")
    delivery = _load(ARTIFACTS / "offer_delivery_check.json")
    assert delivery["branch_count"] == len(evaluator["branches"])
    recorded = {entry["candidate_id"] for entry in delivery["per_branch"]}
    assert recorded == {branch["candidate_id"]
                        for branch in evaluator["branches"]}
    assert delivery["distinct_subject_first_turn_prompts"] >= 1


def test_the_report_leads_with_the_uncalibrated_label_and_covers_20_points():
    report = (ARTIFACTS / "UNDER_THE_HOOD_REPORT.md").read_text(
        encoding="utf-8")
    assert report.startswith("# UNCALIBRATED LIVE-MODEL EXPLORATORY "
                             "SIMULATION")
    headings = ([f"\n## {number}. " for number in (1, 2, 3, 4, 5, 6, 7)]
                + ["\n## 8-11. "]
                + [f"\n## {number}. " for number in range(12, 21)])
    for heading in headings:
        assert heading in report, heading
    assert "# POST-HOC REAL-OUTCOME COMPARISON" in report
    # the post-hoc comparison must be the LAST section
    assert report.index("# POST-HOC REAL-OUTCOME COMPARISON") > \
        report.index("## 20. ")


def test_the_committed_events_hash_their_own_text():
    for path in sorted((ARTIFACTS / "branches").glob(
            "*/committed_events.jsonl")):
        for row in _jsonl(path):
            assert row["sha256"] == fz.sha256_text(row["text"])
