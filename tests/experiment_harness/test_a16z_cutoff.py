"""The historical cutoff is enforced, and the enforcement has teeth.

Pure stdlib: runs on either interpreter.  The a16z scenario is a
counterfactual frozen on 2025-07-01, so a validator that quietly degraded
into a no-op would invalidate the whole experiment without anyone
noticing.  These tests prove both arms reject their canary, prove the
real frozen inputs pass, and prove prospective wording is NOT blocked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import cutoff  # noqa: E402

ARTIFACTS = (REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
             / "a16z_richard_historical")
PROBLEM = (REPO_ROOT / "experiments" / "full_trace_validation" / "data"
           / "a16z_problem.json")


def test_the_canary_is_rejected_by_both_arms():
    """THE canary test: a post-cutoff string must never pass."""
    record = cutoff.scan_text("canary", cutoff.POST_CUTOFF_CANARY)
    assert record["clean"] is False
    arms = {finding["arm"] for finding in record["violations"]}
    assert arms == {"date", "phrase"}, record["violations"]
    with pytest.raises(cutoff.HistoricalCutoffViolation):
        cutoff.assert_clean({"canary": cutoff.POST_CUTOFF_CANARY})


def test_each_arm_rejects_its_own_canary_alone():
    date_only = cutoff.scan_text("d", cutoff.POST_CUTOFF_CANARY_DATE_ONLY)
    assert date_only["clean"] is False
    assert {f["arm"] for f in date_only["violations"]} == {"date"}

    phrase_only = cutoff.scan_text("p",
                                   cutoff.POST_CUTOFF_CANARY_PHRASE_ONLY)
    assert phrase_only["clean"] is False
    assert {f["arm"] for f in phrase_only["violations"]} == {"phrase"}


def test_the_canary_is_caught_inside_a_nested_structure():
    """A leak buried in a nested payload is still a leak."""
    payload = {"actors": [{"name": "x", "private_context":
                           ["ok", {"note": cutoff.POST_CUTOFF_CANARY}]}]}
    with pytest.raises(cutoff.HistoricalCutoffViolation):
        cutoff.assert_clean({"compiled_world": payload})


@pytest.mark.parametrize("text", [
    "The window opens on 2025-07-01T16:00:00Z and closes 2025-07-10.",
    "Richard Zheng graduated from high school in 2025.",
    "If Richard Zheng joins a16z, the New Media team gains capacity.",
    "Should a16z decide to hire him in July 2025, the role starts soon.",
    "a16z is considering whether to make an offer.",
    "Aviato hired him as Head of Marketing in 2024.",
])
def test_pre_cutoff_and_prospective_wording_passes(text):
    assert cutoff.scan_text("ok", text)["clean"] is True, text


@pytest.mark.parametrize("text", [
    "On 2025-07-11 the committee met again.",
    "The decision was announced in August 2025.",
    "By Q4 2025 the team had grown.",
    "A memo from 2026 records the outcome.",
    "He has already joined a16z full time.",
    "a16z hired Richard Zheng for the role.",
])
def test_post_cutoff_wording_is_rejected(text):
    assert cutoff.scan_text("bad", text)["clean"] is False, text


def test_the_frozen_decision_problem_is_pre_cutoff():
    problem = json.loads(PROBLEM.read_text(encoding="utf-8"))
    report = cutoff.scan_surfaces({"decision_problem": problem})
    assert report["clean"] is True, report["violations"]
    # the window end is recognised as simulated time, not a source date
    assert any("2025-07-10" in entry["resolved_day"]
               for entry in report["window_references"])


def test_the_scenario_scope_note_and_evidence_are_pre_cutoff():
    from experiments.full_trace_validation import scenario_a16z as scenario

    surfaces = {"scope_note": scenario.SCOPE_NOTE,
                "evidence_items": scenario.evidence_items()}
    report = cutoff.scan_surfaces(surfaces)
    assert report["clean"] is True, report["violations"]


@pytest.mark.skipif(not ARTIFACTS.is_dir(),
                    reason="the live a16z artifact set is not present")
def test_the_committed_run_recorded_a_clean_enforced_scan():
    record = json.loads(
        (ARTIFACTS / "historical_cutoff_validation.json").read_text(
            encoding="utf-8"))
    assert record["pre_simulation"]["clean"] is True
    assert record["post_run_prompts"]["clean"] is True, \
        record["post_run_prompts"]["violations"][:5]
    assert record["canary"]["rejected_by_the_validator"] is True


@pytest.mark.skipif(not ARTIFACTS.is_dir(),
                    reason="the live a16z artifact set is not present")
def test_no_committed_a16z_artifact_carries_post_cutoff_material():
    """Re-derived from the files on disk, not from the recorded verdict.

    Model RESPONSES are excluded: the harness cannot stop a live model
    emitting post-cutoff text, and those findings are reported (section
    17c) rather than asserted away.  Everything the harness controls --
    the problem, the evidence, the compiled world, the plans, the
    candidates -- must be clean.
    """
    surfaces = {}
    for name in ("decision_problem.json", "evidence_manifest.json",
                 "branch_input_diff.json"):
        surfaces[name] = json.loads(
            (ARTIFACTS / name).read_text(encoding="utf-8"))
    for name in ("adapted_world.json", "base_plan.json"):
        surfaces[name] = json.loads(
            (ARTIFACTS / "adapter" / name).read_text(encoding="utf-8"))
    surfaces["candidates.json"] = json.loads(
        (ARTIFACTS / "candidates" / "candidates.json").read_text(
            encoding="utf-8"))
    report = cutoff.scan_surfaces(surfaces)
    assert report["clean"] is True, report["violations"][:5]
