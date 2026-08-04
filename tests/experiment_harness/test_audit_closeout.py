"""Regression tests for the 2026-08-04 independent-audit findings.

Every test here pins a claim that a committed report got WRONG, at the
level of the thing that produced the claim rather than the prose.  Each
one was verified to FAIL against the pre-fix tree before the fix landed;
the verification method is stated in each docstring.

Findings covered: F1 (guard-activity claims computed from nothing),
F2 (cutoff phrase arm missed a word order), F3 (production refusal
reason overstated what was measured), F4 (guard-class classifier tested
the output signature before the input signature), F6 (a count difference
published as a causal attribution), F5 (the guard had no
approve/authorize), F8 (a shakedown README with no banner).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import cutoff  # noqa: E402
from experiments.full_trace_validation import report as report_lib  # noqa: E402
from experiments.full_trace_validation import (  # noqa: E402
    runner_rerun_compare as compare_lib)

ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
ERRATA = ARTIFACT_ROOT / "ERRATA.md"

#: the exact prose family the reports used to emit unconditionally
ZERO_INTERVENTION_CLAIM = re.compile(
    r"recorded\s+zero\s+interventions|never\s+needed\s+to\s+intervene"
    r"|guard\s+never\s+fired", re.IGNORECASE)


# ---------------------------------------------------------------------------
# F1: a scenario whose guard ledger fired can never render "zero"
# ---------------------------------------------------------------------------


class _StubArtifacts:
    """The minimum a ``report._findings`` call reads.

    Deliberately hand-built rather than loaded from disk: the point is to
    drive the generator with a guard ledger that DID fire and prove the
    rendered prose follows it.
    """

    def __init__(self, *, guard_fired: bool) -> None:
        self.root = ARTIFACT_ROOT
        self.dir = ARTIFACT_ROOT / "stub_scenario"
        self.scenario_id = "stub"
        self.generated = False
        self.candidates = [{"candidate_id": "c1", "action": "Send it."}]
        self.plan = {"run_limits": {"max_steps": 4}}
        self.instrumentation = {
            "ledger": {"records_written": 4, "distinct_call_ids": 4},
            "equality_proof": {"all_equal": True},
            "unavailable_fields": [],
        }
        self.evaluator = {
            "recipient_actor": "Recipient",
            "branches": [{
                "candidate_id": "c1",
                "predicate_explanation": {
                    "recipient_own_turns": [{"content": "Recipient: sure."}]},
            }],
        }
        self.delivery = {
            "verdict": "candidates_never_reached_the_recipient",
            "interpretation": "nothing reached the recipient",
            "distinct_recipient_first_turn_prompts": 1,
            "recipient_first_turn_prompt_sha256_by_candidate": {"c1": "ab" * 32},
            "branch_count": 1,
            "per_branch": [{"candidate_id": "c1",
                            "candidate_fragments_found_in_recipient_prompts": 0,
                            "candidate_fragments_tested": 3}],
            "private_context_leak_check": {"prompts_checked": 4,
                                           "leaks_found": 0,
                                           "findings": []},
        }
        self.audit = {"branches_where_the_two_readings_disagree": 0,
                      "branch_count": 1}
        guard_block = {"intervened": guard_fired,
                       "explanation": "rewrote it" if guard_fired else "clean"}
        self.steps = {"c1": [{
            "step": 3,
            "active_actor": {"name": "Sender"},
            "recipients": {"names": ["Sender"]},
            "actor_raw_response": {"engine_recorded_value": "Sender waits."},
            "guard": guard_block,
        }]}
        self.guards = {"c1": [{
            "step": 3,
            "intervened": guard_fired,
            "records": ([{"step": 3, "active": "Sender",
                          "affected": ["Recipient"],
                          "original_excerpt": "Sender reads Recipient's reply",
                          "rewritten_excerpt": "Sender reads."}]
                        if guard_fired else []),
        }]}


def test_a_fired_guard_ledger_can_never_render_a_zero_intervention_claim():
    """F1 root cause.

    Pre-fix verification: the same stub, driven through the same
    ``report._findings`` entry point on the pre-fix tree, rendered both
    "the guard never needed to intervene" (section 15) and "recorded zero
    interventions" (section 18) even though ``art.guards`` and
    ``art.steps[*]['guard']`` both say ``intervened=True``.  Those
    sentences were literals; this test failed on both matches.
    """
    text = "\n".join(report_lib._findings(_StubArtifacts(guard_fired=True)))
    assert not ZERO_INTERVENTION_CLAIM.search(text), text[:4000]
    assert "**DID** intervene" in text
    assert "`c1` step 3" in text


def test_a_silent_guard_ledger_still_renders_the_zero_claim():
    """The fix must not simply delete the sentence: a genuinely quiet
    guard still has to be reported as quiet, or the report would lose a
    real fact."""
    text = "\n".join(report_lib._findings(_StubArtifacts(guard_fired=False)))
    assert "recorded **0** interventions" in text


def test_an_absent_guard_ledger_is_not_reported_as_zero():
    """An absent measurement is not a measurement of zero."""
    activity = report_lib.guard_activity(
        type("Empty", (), {"guards": {}, "steps": {}})())
    assert activity["measured"] is False
    sentence = report_lib.guard_activity_sentence(activity)
    assert "not measured" in sentence
    assert not ZERO_INTERVENTION_CLAIM.search(sentence)


@pytest.mark.parametrize("scenario_id", ["peter_supplied", "peter_generated"])
def test_committed_reports_that_carry_the_wrong_claim_carry_the_errata(
        scenario_id):
    """The published wording is PRESERVED, so it must be marked.

    Original sentences are never deleted (the audit judgment stands as
    written); each one that its own ledger disproves carries an inline
    errata marker on the same line, and the report links ERRATA.md at the
    top.
    """
    report = ARTIFACT_ROOT / scenario_id / "UNDER_THE_HOOD_REPORT.md"
    if not report.is_file():
        pytest.skip(f"{scenario_id} has no committed report")
    fired = 0
    for path in sorted(
            (ARTIFACT_ROOT / scenario_id / "branches").glob(
                "*/guard_ledger.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line).get("intervened"):
                fired += 1
    assert fired > 0, "this test only means something when the guard fired"
    text = report.read_text(encoding="utf-8")
    assert "ERRATA.md" in text.splitlines()[2] or "ERRATA" in text[:1200]
    for line in text.splitlines():
        if ZERO_INTERVENTION_CLAIM.search(line):
            assert "ERRATA" in line, (
                "a claim the ledger disproves is published without its "
                f"errata marker: {line[:200]}")


def test_the_errata_exists_and_quotes_the_ledger():
    assert ERRATA.is_file()
    text = ERRATA.read_text(encoding="utf-8")
    for needle in (
            # every audit finding id is cross-referenced
            "**F1**", "**F2**", "**F3**", "**F4**", "**F6**", "**F8**",
            "audit finding **F5**",
            # every corrected sentence is quoted verbatim, not paraphrased
            "recorded zero interventions",
            "never needed to intervene",
            "The historical cutoff was enforced mechanically rather than",
            "every branch ran the counterfactual's independent variable at "
            "the same (undelivered) value",
            "A pre-fix determined-recipient rewrite, verbatim from the "
            "guard ledger",
            "## Agency-guard interventions (defect D3)",
            # the ledger evidence
            "guard_ledger.jsonl",
            "Beckett Zahedi reads Peter Thiel",
            "Beckett Zahedi reads. Thursday works for me",
            "possessive-nominalization",
            "a16z_richard_historical-000067",
            "a16z_richard_historical-000157",
            # the retroactive-refusal disclosure the lead required
            "the corrected validator refuses it",
            "disclosed, non-propagating",
            # the standing judgments are explicitly not touched
            "No realism judgment."):
        assert needle in text, needle


def test_the_errata_states_the_retroactive_refusal_and_the_scope_correction():
    path = (ARTIFACT_ROOT / "a16z_richard_historical"
            / "CUTOFF_SCOPE_CORRECTION.json")
    if not path.is_file():
        pytest.skip("the a16z artifact set is not present")
    payload = json.loads(path.read_text(encoding="utf-8"))
    refusal = payload["what_the_new_arms_do"][
        "retroactively_refuses_the_frozen_input"]
    assert refusal["verdict"].startswith("REFUSED")
    assert refusal["finding_count"] == 3
    assert refusal["matched_texts"] == ["his later a16z employment",
                                        "later a16z employment",
                                        "later a16z work"]
    assert refusal["the_known_sentence_is_the_only_defect"] is True


def test_the_frozen_a16z_problem_is_not_edited_by_this_closeout():
    """The frozen input keeps the user's own sentence, verbatim."""
    problem = json.loads(
        (REPO_ROOT / "experiments" / "full_trace_validation" / "data"
         / "a16z_problem.json").read_text(encoding="utf-8"))
    assert ("Do not include his later a16z employment or later a16z work."
            in problem["relevant_context"])


# ---------------------------------------------------------------------------
# F2: the cutoff phrase arm and the leaked sentence
# ---------------------------------------------------------------------------


LEAKED = "Do not include his later a16z employment or later a16z work."


def test_the_leaked_sentence_is_now_rejected_by_the_phrase_arm():
    """F2 root cause.

    Pre-fix verification: this exact assertion was run against the
    pre-fix ``cutoff.py`` and PASSED the scan (``clean is True``) --
    the phrase arm's only possessive pattern was
    ``\\bhis\\s+(?:role|job|position|work)\\s+at\\s+a16z\\b``, which
    fixes the word order and cannot match ``his later a16z employment``.
    """
    record = cutoff.scan_text("leak", LEAKED)
    assert record["clean"] is False
    assert {finding["arm"] for finding in record["violations"]} == {"phrase"}
    assert "his later a16z employment" in {
        finding["matched_text"] for finding in record["violations"]}


def test_the_superseded_pattern_really_could_not_match_it():
    """The discriminator: the OLD pattern set, run directly, misses it.

    This pins WHY the leak got through, so a future edit that reverts to
    the old ordering fails here rather than silently reopening it.
    """
    superseded = r"\bhis\s+(?:role|job|position|work)\s+at\s+a16z\b"
    assert re.search(superseded, LEAKED, re.IGNORECASE) is None
    assert superseded not in cutoff.POST_CUTOFF_PHRASE_PATTERNS


@pytest.mark.parametrize("text", [
    "his a16z role",
    "his later a16z work",
    "their subsequent a16z tenure",
    "later a16z position",
    "his employment at a16z",
    "his role at a16z",
    "her eventual a16z career",
])
def test_the_widened_family_is_rejected(text):
    assert cutoff.scan_text("bad", text)["clean"] is False, text


@pytest.mark.parametrize("text", [
    "If Richard Zheng joins a16z, the New Media team gains capacity.",
    "Should a16z decide to hire him in July 2025, the role starts soon.",
    "a16z is considering whether to make an offer.",
    "Public evidence indicates a16z New Media is intended to provide "
    "in-house creative production and owned-channel distribution.",
    "The New Media Hiring Lead owns the hiring action at a16z.",
    "The a16z New Media team is being formed.",
    "a16z New Media work would include launch strategy.",
    "Richard would report into the a16z New Media team if he accepted.",
    "His role at Aviato was Head of Marketing.",
    "Later, a16z published a job description.",
    "a16z may later decide to hire.",
])
def test_the_widening_did_not_start_blocking_legitimate_wording(text):
    """Conservatism check: prospective, conditional and non-a16z-tenure
    wording must still pass, or the validator would be blocking the
    experiment instead of the leak."""
    assert cutoff.scan_text("ok", text)["clean"] is True, text


def test_the_scope_correction_records_the_re_verified_numbers():
    path = (ARTIFACT_ROOT / "a16z_richard_historical"
            / "CUTOFF_SCOPE_CORRECTION.json")
    if not path.is_file():
        pytest.skip("the a16z artifact set is not present")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["leaked_sentence"] == LEAKED
    assert payload["origin"]["present_in_frozen_input"] is True
    assert payload["what_the_old_arms_did"][
        "superseded_pattern_matches_the_leaked_sentence"] is False
    assert payload["what_the_new_arms_do"][
        "leaked_sentence_now_rejected"] is True
    for run in ("pre_fix_run", "post_fix_rerun"):
        block = payload["did_it_propagate"][run]
        assert block["actor_and_gm_prompts_scanned"] == 360
        assert block["model_responses_scanned"] == 180
        assert block["prompt_violations"] == 0
        assert block["response_violations"] == 0


def test_the_scope_correction_is_reproducible_from_the_committed_files():
    """It is a derived artifact, so it must re-derive byte-equal."""
    path = (ARTIFACT_ROOT / "a16z_richard_historical"
            / "CUTOFF_SCOPE_CORRECTION.json")
    if not path.is_file():
        pytest.skip("the a16z artifact set is not present")
    from experiments.full_trace_validation import cutoff_scope

    committed = json.loads(path.read_text(encoding="utf-8"))
    assert cutoff_scope.build_payload() == committed


# ---------------------------------------------------------------------------
# F3: the production refusal reason
# ---------------------------------------------------------------------------


class _DeliveryFact:
    """The two attributes ``_refuse_when_nothing_was_delivered`` reads."""

    def __init__(self, candidate_id: str) -> None:
        self.candidate_id = candidate_id
        self.intervention_delivered = {
            "status": "not_delivered",
            "reason": "no_distinctive_fragment_reached_any_other_actor"}


def _refusal_message():
    from sworldmodel.outcomes import InterventionNotDeliveredError
    from sworldmodel.outcomes.ranking import _refuse_when_nothing_was_delivered

    try:
        _refuse_when_nothing_was_delivered(
            [_DeliveryFact("c1"), _DeliveryFact("c2")])
    except InterventionNotDeliveredError as exc:
        return str(exc)
    raise AssertionError("the delivery gate did not refuse")


def test_the_refusal_reason_no_longer_claims_the_variable_never_varied():
    """F3 root cause.

    Pre-fix verification: the same call on the pre-fix tree produced
    "...so every branch ran the counterfactual's independent variable at
    the same (undelivered) value..." and "...an artifact of model
    sampling on identical downstream context...", both of which the
    frozen a16z run disproves -- the hiring lead's own turn put $150,000
    into one branch's compensation-partner prompt (recorded call
    a16z_richard_historical-000067) and $300,000 into another's (-000157).
    This test failed on both substrings.
    """
    message = _refusal_message()
    assert "at the same (undelivered) value" not in message
    assert "identical downstream context" not in message
    assert "refusing to rank" in message


def test_the_refusal_reason_states_exactly_what_was_measured():
    message = _refusal_message()
    assert ("no distinctive fragment of any branch's candidate was found "
            "in any actor's own context except the insertion actor's"
            in message)
    assert "NOT a finding that the branches were identical downstream" in message
    assert "restate the variable in its own words" in message


def test_the_a16z_counterexample_is_still_true_in_the_frozen_artifacts():
    """The fact that makes the old wording false, re-derived from the
    committed call ledger rather than quoted from the audit."""
    calls = (ARTIFACT_ROOT / "a16z_richard_historical" / "all_llm_calls.jsonl")
    if not calls.is_file():
        pytest.skip("the a16z artifact set is not present")
    wanted = {"a16z_richard_historical-000067": "$150,000",
              "a16z_richard_historical-000157": "$300,000"}
    seen = {}
    for line in calls.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("call_id") not in wanted:
            continue
        text = "\n".join(message.get("content") or "" for message in
                         row["request"]["messages"])
        seen[row["call_id"]] = (row.get("actor_name"),
                                wanted[row["call_id"]] in text)
    assert set(seen) == set(wanted), seen
    for call_id, (actor_name, present) in seen.items():
        assert actor_name == "People and Compensation Partner", seen
        assert present is True, seen


# ---------------------------------------------------------------------------
# F4 / F6: the guard-class classifier and the D3 attribution
# ---------------------------------------------------------------------------


def _facts(records):
    return {"guard": {"records": records}}


def test_a_possessive_whose_rewrite_ends_in_a_determiner_is_possessive():
    """F4 root cause.

    Pre-fix verification: the pre-fix classifier tested the dangling
    determiner FIRST, so this record -- whose INPUT is a possessive and
    whose OUTPUT happens to end in "the." -- was counted in the D3
    bucket.  The two asserts below were inverted on the pre-fix tree.
    This is the real a16z ``user_001`` step 11 record, verbatim.
    """
    census = compare_lib._guard_class_census(_facts([{
        "branch": "user_001", "step": 11,
        "affected": ["People and Compensation Partner"],
        "original_excerpt":
            "Putative event to resolve:  New Media Hiring Lead: New Media "
            "Hiring Lead reviews the People and Compensation Partner’s l",
        "rewritten_excerpt":
            "Putative event to resolve:  New Media Hiring Lead: New Media "
            "Hiring Lead reviews the. People and Compensation Partner is"}]))
    assert census["possessive_nominalization_documented_conservatism"] == 1
    assert census["determined_recipient_object_slot_the_D3_fix_closed"] == 0


def test_a_genuine_determined_recipient_record_still_lands_in_D3():
    """The ordering fix must not empty the D3 bucket: this is the real
    a16z ``user_003`` step 15 record, which IS the class D3 closed."""
    census = compare_lib._guard_class_census(_facts([{
        "branch": "user_003", "step": 15,
        "affected": ["New Media Strategy Partner"],
        "original_excerpt":
            "Putative event to resolve:  Richard Zheng: Richard Zheng sends "
            "a brief, direct email to the New Media Strategy Partner: ",
        "rewritten_excerpt":
            "Putative event to resolve:  Richard Zheng: Richard Zheng sends "
            "a brief, direct email to the. New Media Strategy Partner "}]))
    assert census["determined_recipient_object_slot_the_D3_fix_closed"] == 1
    assert census["possessive_nominalization_documented_conservatism"] == 0


def test_the_census_uses_the_untruncated_text_when_it_is_available():
    """The 120-character cap hid the act noun that decides the class."""
    record = {"branch": "b", "step": 1,
              "affected": ["Peter Thiel"],
              "original_excerpt": "Beckett Zahedi reads Peter Thiel" + "x" * 90,
              "rewritten_excerpt": "Beckett Zahedi reads." + "x" * 100}
    blind = compare_lib._guard_class_census(_facts([record]))
    assert blind["possessive_nominalization_documented_conservatism"] == 0
    informed = compare_lib._guard_class_census(
        _facts([record]),
        {("b", 1): "Beckett Zahedi reads Peter Thiel's reply, then waits."})
    assert informed["possessive_nominalization_documented_conservatism"] == 1
    assert informed["classified_from_untruncated_text"] == 1


def test_the_a16z_d3_attribution_is_replayed_not_subtracted():
    """F6 root cause.

    Pre-fix verification: the committed document published all 20 pre-fix
    interventions under a "(defect D3)" heading with "change: -20",
    because the count fell to zero.  Replaying each intervention's
    reconstructed pre-guard text through the current guard shows 19 --
    ``user_001`` step 11 is a possessive that the current guard STILL
    rewrites, so its absence from the re-run is sampling, not the fix.
    """
    pre_dir = ARTIFACT_ROOT / "a16z_richard_historical"
    if not (pre_dir / "branches").is_dir():
        pytest.skip("the a16z artifact set is not present")
    attribution = compare_lib._d3_replay_attribution(
        pre_dir, compare_lib._roster(pre_dir))
    assert attribution["pre_fix_interventions"] == 20
    assert attribution["explained_by_the_D3_fix"] == 19
    assert attribution["still_rewritten_by_the_current_guard"] == 1
    assert attribution["unreplayable_no_recorded_raw_response"] == 0
    still = attribution["still_rewritten_records"][0]
    assert (still["branch"], still["step"]) == ("user_001", 11)


def test_the_committed_comparison_publishes_the_replayed_attribution():
    path = (ARTIFACT_ROOT / "a16z_richard_historical" / "post_fix_rerun"
            / "pre_vs_post_fix.json")
    if not path.is_file():
        pytest.skip("the a16z re-run is not committed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    attribution = payload["d3_replay_attribution"]
    assert attribution["explained_by_the_D3_fix"] == 19
    assert attribution["still_rewritten_by_the_current_guard"] == 1
    census = payload["guard_class_census"]["pre_fix"]
    assert census["possessive_nominalization_documented_conservatism"] == 1
    assert census["determined_recipient_object_slot_the_D3_fix_closed"] == 19
    assert census["unclassifiable_from_the_120_character_excerpt"] == 0
    assert census["classified_by_replaying_through_the_current_guard"] is True
    text = (path.parent / "PRE_VS_POST_FIX.md").read_text(encoding="utf-8")
    # the verbatim D3 example is the GENUINE determined-recipient case
    # (user_003 step 15), not the possessive one the audit caught
    assert "Richard Zheng sends a brief, direct email to the." in text
    assert "A pre-fix POSSESSIVE rewrite" in text


# ---------------------------------------------------------------------------
# F8: the shakedown banner
# ---------------------------------------------------------------------------


def test_every_committed_experiment_readme_carries_the_banner():
    missing = []
    for path in sorted(ARTIFACT_ROOT.rglob("README.md")):
        if "UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION" not in \
                path.read_text(encoding="utf-8"):
            missing.append(str(path.relative_to(REPO_ROOT)))
    assert missing == [], missing
