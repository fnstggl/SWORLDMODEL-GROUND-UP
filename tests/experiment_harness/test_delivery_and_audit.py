"""The delivery check and the post-hoc measurement audit.

The delivery check is the harness's guard against the validity failure
this experiment actually found: a scenario can report a winner while the
recipient never saw any candidate. These tests prove the check detects
that condition, does not fire on a healthy scenario, and is applied to
the committed artifacts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from experiments.full_trace_validation import delivery  # noqa: E402

ARTIFACTS = REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
SCENARIOS = ("peter_supplied", "peter_generated")

CANDIDATE = ("Subject: a distinctive subject line for this branch\n\n"
             "This sentence is long enough to count as a distinctive "
             "fragment of the candidate.")


def _rows(*prompts, recipient="R"):
    return [
        {"step": index + 1,
         "active_actor": {"name": recipient, "actor_id": "r"},
         "actor_model_request": [
             {"call_id": f"c{index}",
              "messages": [{"role": "system", "content": "hint"},
                           {"role": "user", "content": prompt}]}]}
        for index, prompt in enumerate(prompts)]


def test_delivery_detects_content_that_did_reach_the_recipient():
    rows = _rows("Observations: " + CANDIDATE)
    result = delivery.check_branch(
        candidate_id="c1", candidate_action=CANDIDATE,
        recipient_name="R", step_ledger_rows=rows)
    assert result["content_delivered_to_recipient"] is True
    assert result["candidate_fragments_found_in_recipient_prompts"] >= 1


def test_delivery_detects_content_that_never_arrived():
    rows = _rows("Observations: something generic and unrelated.")
    result = delivery.check_branch(
        candidate_id="c1", candidate_action=CANDIDATE,
        recipient_name="R", step_ledger_rows=rows)
    assert result["content_delivered_to_recipient"] is False
    assert result["example_fragment_missing"]


def test_identical_recipient_prompts_produce_the_loud_verdict():
    branches = [(f"c{index}", CANDIDATE + f" variant {index}",
                 _rows("identical generic context for every branch"))
                for index in range(3)]
    result = delivery.check_scenario(scenario_id="s",
                                     recipient_name="R", branches=branches)
    assert result["distinct_recipient_first_turn_prompts"] == 1
    assert result["verdict"] == "candidates_never_reached_the_recipient"
    assert "NOT evidence that one candidate is better" in \
        result["interpretation"]


def test_a_healthy_scenario_gets_the_healthy_verdict():
    branches = [(f"c{index}",
                 f"Distinctive candidate body number {index} which is "
                 f"long enough to be a fragment.",
                 _rows(f"Observations: Distinctive candidate body number "
                       f"{index} which is long enough to be a fragment."))
                for index in range(3)]
    result = delivery.check_scenario(scenario_id="s",
                                     recipient_name="R", branches=branches)
    assert result["distinct_recipient_first_turn_prompts"] == 3
    assert result["verdict"] == "candidates_reached_the_recipient"


def test_private_context_leak_check_finds_a_planted_leak():
    rows = _rows("Private setup: R is nobody special.\n"
                 "Observations: S privately believes the deal is doomed "
                 "and has told nobody at all about it.")
    clean = delivery.private_context_leak_check(
        step_ledger_rows=rows,
        private_by_name={"R": "R is nobody special.",
                         "S": "S privately believes the deal is doomed "
                              "and has told nobody at all about it."})
    assert clean["leaks_found"] == 1
    assert clean["findings"][0]["leaked_from"] == "S"
    assert clean["findings"][0]["prompt_owner"] == "R"

    safe = delivery.private_context_leak_check(
        step_ledger_rows=_rows("Private setup: R is nobody special."),
        private_by_name={"R": "R is nobody special.",
                         "S": "S privately believes the deal is doomed "
                              "and has told nobody at all about it."})
    assert safe["leaks_found"] == 0


# ---------------------------------------------------------------------------
# the committed artifacts
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not ARTIFACTS.is_dir(),
                    reason="the live artifact set is not present")
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_scenario_carries_its_delivery_check_and_audit(scenario):
    directory = ARTIFACTS / scenario
    check = json.loads((directory / "candidate_delivery_check.json")
                       .read_text(encoding="utf-8"))
    audit = json.loads((directory / "measurement_audit.json")
                       .read_text(encoding="utf-8"))
    assert check["verdict"] in delivery._INTERPRETATION
    assert check["branch_count"] == 3
    assert check["private_context_leak_check"]["leaks_found"] == 0
    assert audit["status"] == "NOT AN INDEPENDENT MEASUREMENT OF THIS RUN"
    assert audit["written_after_seeing_the_transcripts"] is True


@pytest.mark.skipif(not ARTIFACTS.is_dir(),
                    reason="the live artifact set is not present")
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_report_states_the_delivery_verdict_it_measured(scenario):
    directory = ARTIFACTS / scenario
    check = json.loads((directory / "candidate_delivery_check.json")
                       .read_text(encoding="utf-8"))
    report = (directory / "UNDER_THE_HOOD_REPORT.md").read_text(
        encoding="utf-8")
    assert check["verdict"] in report
    assert "UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION" in report
    assert "This is not a prediction" in report
    contents = report.split("### Contents -- all 20 required points", 1)
    assert len(contents) == 2, "the report has no contents block"
    block = contents[1].split("\n## ", 1)[0]
    for point in range(1, 21):
        assert f"| {point}. |" in block, f"required point {point} missing"
    for heading in ("## 12.", "## 13.", "## 14.", "## 15.", "## 16.",
                    "## 17.", "## 18.", "## 19.", "## 20."):
        assert heading in report, heading
    assert "## 8-11." in report


@pytest.mark.skipif(not ARTIFACTS.is_dir(),
                    reason="the live artifact set is not present")
def test_the_readme_and_instrumentation_agree():
    validation = json.loads(
        (ARTIFACTS / "shared" / "instrumentation_validation.json")
        .read_text(encoding="utf-8"))
    assert validation["equality_proof"]["all_equal"] is True
    values = validation["equality_proof"]["values"]
    assert len(set(values.values())) == 1
    readme = (ARTIFACTS / "README.md").read_text(encoding="utf-8")
    assert str(values["ledger_records_written"]) in readme
    assert "candidates_never_reached_the_recipient" in readme or \
        "candidates_reached_the_recipient" in readme
