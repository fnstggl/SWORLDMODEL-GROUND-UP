"""The post-fix re-run machinery: frozen-input verification, output
redirection, and the pre/post comparison.

A re-run only means something if it ran the SAME inputs and wrote
somewhere NEW. These tests cover both halves plus the reading of the
comparison itself, including the guard-class census whose whole job is to
avoid confusing a fixed defect with a documented behaviour.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import freeze as freeze_lib  # noqa: E402
from experiments.full_trace_validation import rerun as rerun_lib  # noqa: E402
from experiments.full_trace_validation import (  # noqa: E402
    runner_rerun_compare as compare_lib)

ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
SCENARIOS = ("peter_supplied", "peter_generated", "a16z_richard_historical")


# ---------------------------------------------------------------------------
# frozen-input verification
# ---------------------------------------------------------------------------


def _manifest(tmp_path, **entries) -> Path:
    manifest = freeze_lib.FreezeManifest(scenario_id="s", note="n")
    for name, value in entries.items():
        manifest.add_json(name, value)
    path = tmp_path / "freeze_manifest.json"
    manifest.write(path, require_complete=False)
    return path


def test_verification_passes_on_identical_inputs(tmp_path):
    compiler = tmp_path / "compiler"
    compiler.mkdir()
    (compiler / "a.json").write_text('{"x": 1}', encoding="utf-8")
    aggregate = freeze_lib.hash_directory(compiler)["aggregate"]
    problem = {"problem_id": "p"}
    path = _manifest(tmp_path, decision_problem=problem)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["entries"]["compiler_artifact_dir_aggregate"] = {
        "sha256": aggregate, "kind": "directory"}
    data["entry_order"].append("compiler_artifact_dir_aggregate")
    path.write_text(json.dumps(data), encoding="utf-8")

    result = rerun_lib.verify_frozen_inputs(
        path, compiler_dir=compiler, decision_problem=problem)
    assert result["all_match"] is True
    assert {check["entry"] for check in result["checks"]} == {
        "compiler_artifact_dir_aggregate", "decision_problem"}


def test_verification_refuses_a_changed_decision_problem(tmp_path):
    compiler = tmp_path / "compiler"
    compiler.mkdir()
    (compiler / "a.json").write_text('{"x": 1}', encoding="utf-8")
    aggregate = freeze_lib.hash_directory(compiler)["aggregate"]
    path = _manifest(tmp_path, decision_problem={"problem_id": "p"})
    data = json.loads(path.read_text(encoding="utf-8"))
    data["entries"]["compiler_artifact_dir_aggregate"] = {
        "sha256": aggregate, "kind": "directory"}
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(rerun_lib.FrozenInputMismatch):
        rerun_lib.verify_frozen_inputs(
            path, compiler_dir=compiler,
            decision_problem={"problem_id": "DIFFERENT"})


def test_verification_refuses_a_changed_compiler_directory(tmp_path):
    compiler = tmp_path / "compiler"
    compiler.mkdir()
    (compiler / "a.json").write_text('{"x": 1}', encoding="utf-8")
    path = _manifest(tmp_path, decision_problem={"problem_id": "p"})
    data = json.loads(path.read_text(encoding="utf-8"))
    data["entries"]["compiler_artifact_dir_aggregate"] = {
        "sha256": "0" * 64, "kind": "directory"}
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(rerun_lib.FrozenInputMismatch) as excinfo:
        rerun_lib.verify_frozen_inputs(path, compiler_dir=compiler)
    assert "compiler_artifact_dir_aggregate" in str(excinfo.value)


# ---------------------------------------------------------------------------
# output redirection: a re-run must not write the pre-fix directories
# ---------------------------------------------------------------------------


def test_peter_rerun_redirects_writes_and_keeps_frozen_reads():
    runner = pytest.importorskip(
        "experiments.full_trace_validation.runner_peter",
        reason="the runner imports the engine environment")
    frozen_compiler = runner.COMPILER_DIR
    frozen_identity = runner.RUN_IDENTITY_PATH
    frozen_supplied = runner.FROZEN_SUPPLIED_DIR
    try:
        runner.set_rerun_output("supplied")
        assert runner.SUPPLIED_DIR == frozen_supplied / "post_fix_rerun"
        assert runner.GENERATED_DIR == (runner.FROZEN_GENERATED_DIR
                                        / "post_fix_rerun")
        assert runner.SHARED_DIR == (frozen_supplied / "post_fix_rerun"
                                     / "shared")
        # the frozen inputs are still read from the pre-fix locations
        assert runner.COMPILER_DIR == frozen_compiler
        assert runner.RUN_IDENTITY_PATH == frozen_identity
        assert "post_fix_rerun" not in str(frozen_compiler)
        runner.set_rerun_output("generated")
        assert runner.SHARED_DIR == (runner.FROZEN_GENERATED_DIR
                                     / "post_fix_rerun" / "shared")
    finally:
        runner.SUPPLIED_DIR = frozen_supplied
        runner.GENERATED_DIR = runner.FROZEN_GENERATED_DIR
        runner.SHARED_DIR = runner.FROZEN_SHARED_DIR
        runner.RERUN_OUTPUT = False


def test_a16z_rerun_redirects_writes_and_keeps_frozen_reads():
    runner = pytest.importorskip(
        "experiments.full_trace_validation.runner_a16z",
        reason="the runner imports the engine environment")
    frozen = runner.FROZEN_SCENARIO_DIR
    frozen_compiler = runner.COMPILER_DIR
    frozen_attempts = runner.ATTEMPTS_DIR
    frozen_identity = runner.RUN_IDENTITY_PATH
    try:
        runner.set_rerun_output()
        assert runner.SCENARIO_DIR == frozen / "post_fix_rerun"
        assert runner.COMPILER_DIR == frozen_compiler
        assert runner.ATTEMPTS_DIR == frozen_attempts
        assert runner.RUN_IDENTITY_PATH == frozen_identity
        assert "post_fix_rerun" not in str(frozen_compiler)
    finally:
        runner.SCENARIO_DIR = frozen
        runner.RERUN_OUTPUT = False


def test_rerun_never_recompiles():
    runner = pytest.importorskip(
        "experiments.full_trace_validation.runner_a16z",
        reason="the runner imports the engine environment")
    with pytest.raises(SystemExit):
        runner.main(["--phase", "compile", "--rerun"])


# ---------------------------------------------------------------------------
# the guard-class census
# ---------------------------------------------------------------------------


def _facts(records):
    return {"guard": {"records": records}}


def test_census_recognises_the_determiner_truncation_the_fix_closed():
    census = compare_lib._guard_class_census(_facts([{
        "affected": ["People and Compensation Partner"],
        "original_excerpt": "NMHL sends a message to the People and "
                            "Compensation Partner: \"the base is\"",
        "rewritten_excerpt": "NMHL sends a message to the. People and "
                             "Compensation Partner is now able to observe"}]))
    assert census["determined_recipient_object_slot_the_D3_fix_closed"] == 1
    assert census["possessive_nominalization_documented_conservatism"] == 0


def test_census_separates_the_documented_possessive_class():
    census = compare_lib._guard_class_census(_facts([{
        "affected": ["Peter Thiel"],
        "original_excerpt": "Beckett Zahedi reads Peter Thiel's reply, "
                            "then compiles the logs",
        "rewritten_excerpt": "Beckett Zahedi reads. Peter Thiel is now "
                             "able to observe this"}]))
    assert census["determined_recipient_object_slot_the_D3_fix_closed"] == 0
    assert census["possessive_nominalization_documented_conservatism"] == 1


def test_census_refuses_to_guess_a_truncated_record():
    """The runner caps guard excerpts at 120 characters. A record whose
    class is not visible in the excerpt is counted as unclassifiable, not
    guessed into a bucket."""
    long_text = "x" * 130
    census = compare_lib._guard_class_census(_facts([{
        "affected": ["Someone Else"],
        "original_excerpt": long_text,
        "rewritten_excerpt": long_text}]))
    assert census["unclassifiable_from_the_120_character_excerpt"] == 1
    assert census["determined_recipient_object_slot_the_D3_fix_closed"] == 0
    assert census["possessive_nominalization_documented_conservatism"] == 0
    assert census["total"] == 1


# ---------------------------------------------------------------------------
# the committed comparison artifacts
# ---------------------------------------------------------------------------


def _post_dir(scenario_id) -> Path:
    return ARTIFACT_ROOT / scenario_id / "post_fix_rerun"


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_the_pre_fix_artifacts_are_still_there(scenario_id):
    """The whole point of writing to post_fix_rerun/ is that the pre-fix
    record survives untouched."""
    pre = ARTIFACT_ROOT / scenario_id
    if not (pre / "evaluator_ledger.json").is_file():
        pytest.skip(f"{scenario_id} has no committed pre-fix artifacts")
    assert (pre / "freeze_manifest.json").is_file()
    assert (pre / "recommendation_report.json").is_file()
    assert sorted(path.name for path in (pre / "branches").iterdir())


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_the_rerun_verified_its_frozen_inputs(scenario_id):
    post = _post_dir(scenario_id)
    if not (post / "frozen_input_verification.json").is_file():
        pytest.skip(f"{scenario_id} has no committed re-run")
    payload = json.loads(
        (post / "frozen_input_verification.json").read_text(encoding="utf-8"))
    assert payload["all_match"] is True
    assert {check["entry"] for check in payload["checks"]} >= {
        "compiler_artifact_dir_aggregate", "decision_problem",
        "evidence_manifest"}


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_the_comparison_document_exists_and_states_the_ranking(scenario_id):
    post = _post_dir(scenario_id)
    if not (post / "PRE_VS_POST_FIX.md").is_file():
        pytest.skip(f"{scenario_id} has no committed re-run")
    text = (post / "PRE_VS_POST_FIX.md").read_text(encoding="utf-8")
    payload = json.loads(
        (post / "pre_vs_post_fix.json").read_text(encoding="utf-8"))
    assert "## Ranking" in text
    assert payload["post_fix"]["ranking"]["outcome"] in ("REFUSED",
                                                         "PRODUCED")
    assert payload["post_fix"]["ranking"]["outcome"] in text
    assert "UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION" in text
    # the frozen inputs the comparison claims are identical really are
    assert payload["frozen_input_comparison"]["all_identical"] is True


def test_the_a16z_determiner_rewrites_are_gone():
    """The headline the D3 fix predicted: the 20 content-destroying
    rewrites disappear."""
    post = _post_dir("a16z_richard_historical")
    if not (post / "pre_vs_post_fix.json").is_file():
        pytest.skip("the a16z re-run is not committed")
    payload = json.loads(
        (post / "pre_vs_post_fix.json").read_text(encoding="utf-8"))
    assert payload["guard_interventions_pre"] == 20
    assert payload["guard_interventions_post"] == 0
    census = payload["guard_class_census"]
    assert census["pre_fix"][
        "determined_recipient_object_slot_the_D3_fix_closed"] >= 1
    assert census["post_fix"]["total"] == 0


def test_the_a16z_rerun_records_the_unresolved_observers():
    """The D1 defect was that a non-matching observer name vanished with
    no trace. It must now be counted and named."""
    post = _post_dir("a16z_richard_historical")
    if not (post / "pre_vs_post_fix.json").is_file():
        pytest.skip("the a16z re-run is not committed")
    payload = json.loads(
        (post / "pre_vs_post_fix.json").read_text(encoding="utf-8"))
    assert payload["unresolved_observers_pre"]["measured"] is False
    post_obs = payload["unresolved_observers_post"]
    assert post_obs["measured"] is True
    assert post_obs["total"] > 0
    assert set(post_obs["by_reason"]) <= {
        "no_roster_match", "ambiguous_roster_match", "not_a_string",
        "blank_after_normalization"}


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_the_rerun_instrumentation_counters_agree(scenario_id):
    post = _post_dir(scenario_id)
    if not (post / "pre_vs_post_fix.json").is_file():
        pytest.skip(f"{scenario_id} has no committed re-run")
    payload = json.loads(
        (post / "pre_vs_post_fix.json").read_text(encoding="utf-8"))
    assert payload["post_fix"]["instrumentation"]["all_equal"] is True
    assert payload["post_fix"]["instrumentation"]["errors"] == 0
