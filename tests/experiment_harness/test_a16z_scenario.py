"""End-to-end plumbing and measurement rules of the a16z scenario.

This test does NOT produce experiment artifacts and makes no claim about
any real person or firm: it builds a SYNTHETIC compiled artifact set
carrying the scenario's five declared role names and drives
``runner_a16z.phase_branches`` with a stub in place of the provider, so
the whole artifact layout, the freeze manifest, the branch-input
isolation proof, the offer-delivery check, the step ledgers and the
evaluator ledger are exercised without spending live calls.

The LIVE experiment is the artifact set under
``artifacts/full_trace_validation_20260804/a16z_richard_historical/``;
nothing this test writes ever goes there.
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
    branch_diff, freeze as freeze_lib, offer_delivery,
    predicates_a16z as predicates, recorder as rec, runner_a16z,
    scenario_a16z as scenario)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VECTOR = (REPO_ROOT / "tests" / "engine_compilation" / "vectors"
          / "compiled_scene_artifact")

START = "2025-07-01T16:00:00Z"
CUTOFF = "2025-07-10T12:00:00Z"
ANCHOR = predicates.ACTOR_TURN_ANCHOR

#: stub replies exercising the full authority chain
STUB_BY_ACTOR = {
    scenario.DECISION_OWNER_NAME:
        "The New Media Hiring Lead extends the formal offer for the New "
        "Media role to Richard Zheng and states the annual base salary.",
    scenario.COMP_PARTNER_NAME:
        "The People and Compensation Partner approves the compensation "
        "terms for the New Media role.",
    scenario.STRATEGY_PARTNER_NAME:
        "The New Media Strategy Partner reviews the distribution plan and "
        "shares a view on sequencing.",
    scenario.CREATIVE_LEAD_NAME:
        "The Creative Production Lead reviews the production schedule.",
    scenario.SUBJECT_NAME:
        "Richard Zheng accepts the offer and says he will sign the offer "
        "letter.",
}


def _synthetic_manifest() -> dict:
    """A SYNTHETIC compiled scene with the five declared role names.

    Test input only.  The live experiment compiles its world with the
    real compiler; nothing here is a claim about anyone.
    """
    return {
        "actors": [
            {"name": scenario.DECISION_OWNER_NAME,
             "private_context": "The New Media Hiring Lead owns the hiring "
                                "action for the New Media role."},
            {"name": scenario.STRATEGY_PARTNER_NAME,
             "private_context": "The New Media Strategy Partner advises on "
                                "distribution strategy and cannot issue an "
                                "offer."},
            {"name": scenario.CREATIVE_LEAD_NAME,
             "private_context": "The Creative Production Lead advises on "
                                "production capacity and cannot issue an "
                                "offer."},
            {"name": scenario.COMP_PARTNER_NAME,
             "private_context": "The People and Compensation Partner "
                                "approves or rejects compensation terms."},
            {"name": scenario.SUBJECT_NAME,
             "private_context": "Richard Zheng decides alone whether to "
                                "accept, reject, counter, or delay."},
        ],
        "shared_context": ("A test scene: a role-based hiring committee is "
                           "considering a New Media role, frozen on "
                           "2025-07-01."),
        "starting_events": [
            {"time": START,
             "description": "The committee convenes to consider the New "
                            "Media role.",
             "visible_to": [scenario.DECISION_OWNER_NAME,
                            scenario.STRATEGY_PARTNER_NAME,
                            scenario.CREATIVE_LEAD_NAME,
                            scenario.COMP_PARTNER_NAME]},
        ],
        "resolution": ("Resolve YES only if the persistent event history "
                       "shows Richard Zheng accepting an authorized offer "
                       "before the cutoff. Otherwise resolve NO."),
    }


def _synthetic_compiler_dir(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in ("compiler_metrics.json", "input.json",
                 "validation_report.json"):
        shutil.copy(VECTOR / name, target / name)
    (target / "final_scene_manifest.json").write_text(
        json.dumps(_synthetic_manifest(), indent=1), encoding="utf-8")
    data = json.loads((target / "input.json").read_text(encoding="utf-8"))
    data["start"], data["cutoff"] = START, CUTOFF
    data["question"] = "plumbing question"
    (target / "input.json").write_text(json.dumps(data, indent=1),
                                       encoding="utf-8")


#: the ONE post-cutoff sentence the 2026-08-04 audit found inside the
#: user-supplied ``relevant_context`` of the frozen problem (finding F2).
#: It is quoted here, never edited in the frozen file: the frozen input is
#: the record of a completed run and rewriting it would change the frozen
#: ``decision_problem`` hash.
KNOWN_POST_CUTOFF_SENTENCE = (
    " Do not include his later a16z employment or later a16z work.")


def _plumbing_problem_path(tmp_path: Path) -> Path:
    """A copy of the frozen problem with the KNOWN leak sentence removed.

    Since the cutoff phrase arm was widened (audit finding F2), the real
    frozen problem is -- correctly -- REFUSED by the pre-simulation gate,
    because its user-supplied ``relevant_context`` really does contain a
    post-cutoff assertion.  That refusal is the finding, and it is pinned
    by ``test_a16z_cutoff.py``.

    These plumbing tests exercise the harness MACHINERY (artifact layout,
    freeze manifest, isolation proof, ledgers, delivery check), not the
    frozen input's cutoff status, so they drive it with a problem whose
    single known bad sentence is removed.  The gate itself is untouched:
    remove this copy and the tests would refuse exactly as the real run
    now would.
    """
    data = json.loads(scenario.PROBLEM_PATH.read_text(encoding="utf-8"))
    assert KNOWN_POST_CUTOFF_SENTENCE in data["relevant_context"], (
        "the frozen problem no longer contains the sentence this fixture "
        "removes; re-derive the fixture rather than silently diverging")
    data["relevant_context"] = data["relevant_context"].replace(
        KNOWN_POST_CUTOFF_SENTENCE, "")
    path = tmp_path / "a16z_problem_without_the_known_leak.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _install(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "artifacts"
    scenario_dir = root / scenario.EXPERIMENT_ID
    monkeypatch.setattr(scenario, "PROBLEM_PATH",
                        _plumbing_problem_path(tmp_path))
    monkeypatch.setattr(runner_a16z, "ARTIFACT_ROOT", root)
    monkeypatch.setattr(runner_a16z, "SCENARIO_DIR", scenario_dir)
    monkeypatch.setattr(runner_a16z, "COMPILER_DIR",
                        scenario_dir / "compiler")
    monkeypatch.setattr(runner_a16z, "ATTEMPTS_DIR",
                        scenario_dir / "compiler_attempts")
    monkeypatch.setattr(runner_a16z, "RUN_IDENTITY_PATH",
                        scenario_dir / "run_identity.json")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-stub-key-for-plumbing-only")
    _synthetic_compiler_dir(scenario_dir / "compiler")
    identity = {
        "window_start_utc": START, "window_cutoff_utc": CUTOFF,
        "historical_cutoff": "2025-07-01",
        "compiler_version": "minimal_scene_v1",
        "compiler_status": "compiled", "compiler_reason": "",
        "compiler_metrics": {"semantic_slots": 2,
                             "evidence_mode": "evidence_package"},
        "compiler_out_dir": "synthetic", "compile_attempts": 1,
        "accepted_attempt": 1,
        "compiled_cast_in_declaration_order": list(scenario.REQUIRED_CAST),
        "question": "plumbing question",
        "context": "plumbing context",
        "evidence_package": "plumbing evidence package",
    }
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / "run_identity.json").write_text(json.dumps(identity),
                                                    encoding="utf-8")
    # stand-ins for the compile phase's own outputs, so the audit phase
    # (which reads them) can run without a compile
    (scenario_dir / "environment.json").write_text(
        json.dumps(runner_a16z._environment()), encoding="utf-8")
    (scenario_dir / "model_configuration.json").write_text(
        json.dumps(runner_a16z._model_configuration()), encoding="utf-8")
    (scenario_dir / "compiler_copy_proof.json").write_text(
        json.dumps({"byte_identical_copy": True, "accepted_attempt": 1}),
        encoding="utf-8")
    (scenario_dir / "instrumentation_compile.json").write_text(
        json.dumps({"ledger": {"records_written": 0, "per_role": {},
                               "records_with_error": 0,
                               "records_that_were_retries": 0}}),
        encoding="utf-8")
    attempts = scenario_dir / "compiler_attempts"
    attempts.mkdir(parents=True, exist_ok=True)
    (attempts / "compile_attempts.json").write_text(json.dumps({
        "acceptance_criteria": scenario.compile_acceptance_criteria(),
        "accepted_attempt": 1,
        "attempts": [{"attempt": 1, "compiler_status": "compiled",
                      "accepted": True, "rejection_reasons": [],
                      "compiled_cast_in_declaration_order":
                          list(scenario.REQUIRED_CAST)}]}),
        encoding="utf-8")
    (scenario_dir / "compiler" / "llm_calls.jsonl").write_text(
        "", encoding="utf-8")
    return scenario_dir


#: the declared candidate texts, used by the stub to decide whether the
#: insertion actor ENACTS its intervention (see ``_stub_provider``)
CANDIDATE_ACTIONS = tuple(
    scenario.build_problem_payload()["candidate_interventions"])


def _stub_provider(monkeypatch, *, accept: bool = True,
                   enact_candidate: bool = True):
    """Stub the provider for the whole run.

    ``enact_candidate`` selects the two shapes a real run can take, and
    they are NOT interchangeable since defect D2 was closed:

    - ``True``  -- the insertion actor restates the candidate it was
      handed, so the intervention reaches the rest of the cast, the
      branches genuinely differ downstream, and a ranking is produced;
    - ``False`` -- the insertion actor keeps its own fixed line, the
      candidate never leaves it, and ``outcomes.ranking`` REFUSES to name
      a winner.  This is what the live run actually did.
    """
    def fake(*, api_key, model, messages, max_tokens, timeout_s,
             response_format=None):
        del api_key, model, max_tokens, timeout_s, response_format
        prompt = messages[-1]["content"]
        if "Which entities are aware" in prompt:
            return ", ".join(scenario.REQUIRED_CAST), {}
        system = messages[0]["content"]
        for name, reply in STUB_BY_ACTOR.items():
            if f"You are {name}," in system:
                if name == scenario.SUBJECT_NAME and not accept:
                    return ("Richard Zheng declines the offer and will not "
                            "take the role."), {"prompt_tokens": 1}
                if enact_candidate and name == scenario.DECISION_OWNER_NAME:
                    for action in CANDIDATE_ACTIONS:
                        if action in prompt:
                            reply = f"{reply} {action}"
                            break
                return reply, {"prompt_tokens": 1, "completion_tokens": 1}
        return "The rules engine notes the step.", {}

    monkeypatch.setattr(rec, "_chat_completion", fake)
    monkeypatch.setattr(rec.time, "sleep", lambda seconds: None)


# ---------------------------------------------------------------------------
# code-owned binding and metrics
# ---------------------------------------------------------------------------


def test_the_candidate_binding_is_verified_against_the_frozen_text():
    binding = scenario.candidate_key_by_index()
    assert list(binding.values()) == list(scenario.SALARY_MAPPING_KEYS)
    ids = [f"user_{index + 1:03d}" for index in range(6)]
    savings = scenario.savings_by_candidate_id(ids)
    assert savings["user_001"] == 300000.0    # no-offer baseline
    assert savings["user_006"] == 0.0         # $300k offer saves nothing
    assert savings["user_002"] == 200000.0    # $100k offer


def test_the_salary_metric_never_reads_the_trace():
    predicate = predicates.salary_savings_predicate({"user_002": 200000.0})
    value, citations = predicate([], {"candidate_id": "user_002"})
    assert value == 200000.0
    assert citations == ("state:committed_event_count",)
    # a trace full of other numbers cannot move it
    noisy = [{"event_id": "ev_0000",
              "description": f"{ANCHOR} X: the base is $999,999."}]
    assert predicate(noisy, {"candidate_id": "user_002"})[0] == 200000.0
    with pytest.raises(KeyError):
        predicate([], {"candidate_id": "user_009"})


def _row(name, content):
    return {"event_id": "ev", "description": f"{ANCHOR} {name}: {content}"}


def test_valid_offer_accepted_needs_the_whole_authority_chain_in_order():
    predicate = predicates.valid_offer_accepted_predicate(
        approver_name=scenario.COMP_PARTNER_NAME,
        hiring_lead_name=scenario.DECISION_OWNER_NAME,
        subject_name=scenario.SUBJECT_NAME)
    approve = _row(scenario.COMP_PARTNER_NAME,
                   "approves the compensation terms.")
    offer = _row(scenario.DECISION_OWNER_NAME,
                 "extends the formal offer to Richard Zheng.")
    accept = _row(scenario.SUBJECT_NAME, "accepts the offer.")

    value, citations = predicate([approve, offer, accept], {})
    assert value is True and len(citations) == 3

    # acceptance BEFORE the authorization is complete does not count
    assert predicate([accept, approve, offer], {})[0] is False
    # a missing approval does not count
    assert predicate([offer, accept], {})[0] is False
    # a missing offer does not count
    assert predicate([approve, accept], {})[0] is False


def test_only_the_subjects_own_turn_can_satisfy_the_primary_metric():
    predicate = predicates.valid_offer_accepted_predicate(
        approver_name=scenario.COMP_PARTNER_NAME,
        hiring_lead_name=scenario.DECISION_OWNER_NAME,
        subject_name=scenario.SUBJECT_NAME)
    approve = _row(scenario.COMP_PARTNER_NAME, "approves the compensation.")
    offer = _row(scenario.DECISION_OWNER_NAME, "extends the formal offer.")
    # game-master narration: no attribution anchor at all
    narrated = {"event_id": "ev", "description":
                "[observation] [event] Richard Zheng accepts the offer."}
    # another actor claiming it: the row's leading attribution is the lead
    paraphrase = _row(scenario.DECISION_OWNER_NAME,
                      "reports that Richard Zheng accepts the offer.")
    assert predicate([approve, offer, narrated], {})[0] is False
    assert predicate([approve, offer, paraphrase], {})[0] is False
    scan = predicates.authority_violation_scan(
        [approve, offer, narrated, paraphrase],
        subject_name=scenario.SUBJECT_NAME)
    assert scan["candidate_violation_count"] == 2


def test_the_status_rule_maps_an_explicit_refusal_to_failure():
    class _Metric:
        def __init__(self, value):
            self.value = value

    rule = predicates.make_status_rule(subject_rejected=True)
    assert rule({"valid_offer_accepted": _Metric(False)}, "cutoff") \
        == "failure"
    assert rule({"valid_offer_accepted": _Metric(True)}, "cutoff") \
        == "success"
    quiet = predicates.make_status_rule(subject_rejected=False)
    assert quiet({"valid_offer_accepted": _Metric(False)}, "cutoff") is None


# ---------------------------------------------------------------------------
# branch isolation
# ---------------------------------------------------------------------------


def _plan_pair(actor_id, left_text, right_text):
    base = {"initial_observations": {actor_id: ["shared line"]},
            "gm_config": {"start_time": START}}
    left = {"initial_observations": {actor_id: ["shared line", left_text]},
            "gm_config": {"start_time": START}}
    right = {"initial_observations": {actor_id: ["shared line", right_text]},
             "gm_config": {"start_time": START}}
    return base, left, right


def test_the_isolation_proof_passes_a_salary_only_difference():
    base, left, right = _plan_pair(
        "lead", "[t] Offer the fixed package at $100,000.",
        "[t] Offer the fixed package at $250,000.")
    proof = branch_diff.build_branch_input_diff(
        base_plan_dict=base,
        branch_plan_dicts={"user_002": left, "user_005": right},
        candidates_by_id={
            "user_002": {"candidate_id": "user_002",
                         "action": "Offer the fixed package at $100,000.",
                         "summary": "Offer at $100,000."},
            "user_005": {"candidate_id": "user_005",
                         "action": "Offer the fixed package at $250,000.",
                         "summary": "Offer at $250,000."}},
        offer_candidate_ids=["user_002", "user_005"],
        baseline_candidate_id="user_001",
        insertion_actor_id="lead",
        declared_salary_by_candidate_id={"user_002": "$100,000",
                                         "user_005": "$250,000"})
    assert proof["verdict"] == "only_the_salary_differs"
    assert proof["residual_differences_after_masking"] == []
    assert proof["checks"]["every_branch_plan_distinct_before_masking"]


def test_the_isolation_proof_catches_a_non_salary_difference():
    """Negative control: the proof must have teeth."""
    base, left, right = _plan_pair(
        "lead", "[t] Offer the fixed package at $100,000.",
        "[t] Offer the fixed package at $250,000 with extra equity.")
    proof = branch_diff.build_branch_input_diff(
        base_plan_dict=base,
        branch_plan_dicts={"user_002": left, "user_005": right},
        candidates_by_id={
            "user_002": {"candidate_id": "user_002",
                         "action": "Offer the fixed package at $100,000.",
                         "summary": "a"},
            "user_005": {"candidate_id": "user_005",
                         "action": "Offer the fixed package at $250,000 "
                                   "with extra equity.",
                         "summary": "a"}},
        offer_candidate_ids=["user_002", "user_005"],
        baseline_candidate_id="user_001",
        insertion_actor_id="lead",
        declared_salary_by_candidate_id={"user_002": "$100,000",
                                         "user_005": "$250,000"})
    assert proof["verdict"] == "OTHER_DIFFERENCES_FOUND"
    assert proof["residual_differences_after_masking"]


def test_the_isolation_proof_catches_a_change_outside_the_boundary():
    base, left, _right = _plan_pair(
        "lead", "[t] Offer at $100,000.", "[t] Offer at $250,000.")
    tampered = json.loads(json.dumps(left))
    tampered["gm_config"]["start_time"] = "2025-07-02T00:00:00Z"
    proof = branch_diff.build_branch_input_diff(
        base_plan_dict=base, branch_plan_dicts={"user_002": tampered},
        candidates_by_id={"user_002": {"candidate_id": "user_002",
                                       "action": "Offer at $100,000.",
                                       "summary": "a"}},
        offer_candidate_ids=["user_002"], baseline_candidate_id="user_001",
        insertion_actor_id="lead",
        declared_salary_by_candidate_id={"user_002": "$100,000"})
    assert proof["verdict"] == "OTHER_DIFFERENCES_FOUND"
    assert proof["per_branch"][0][
        "plan_paths_outside_the_insertion_boundary"]


# ---------------------------------------------------------------------------
# offer delivery
# ---------------------------------------------------------------------------


def test_salary_variants_cover_the_forms_a_model_might_use():
    forms = set(offer_delivery.salary_variants("$150,000"))
    assert {"$150,000", "150,000", "150000", "150k", "$150k"} <= forms


def test_a_contaminated_token_is_not_counted_as_delivery():
    rows = [{"step": 1,
             "active_actor": {"name": scenario.SUBJECT_NAME},
             "actor_model_request": [{"call_id": "c1", "messages": [
                 {"role": "user",
                  "content": "You earned $100,000 per video shoot."}]}],
             "observations_delivered": {}}]
    record = offer_delivery.check_offer_branch(
        candidate_id="user_002", candidate_action="Offer at $100,000.",
        subject_name=scenario.SUBJECT_NAME, step_ledger_rows=rows,
        committed_texts=[], declared_salary="$100,000",
        baseline_prompt_text="You earned $100,000 per video shoot.",
        static_world_text="")
    assert record["salary_found_in_subject_prompts"]
    assert record["contaminated_token"] is True
    assert record["offer_reached_the_subject"] is False


# ---------------------------------------------------------------------------
# end-to-end plumbing (stubbed provider)
# ---------------------------------------------------------------------------


def test_the_branch_phase_produces_the_complete_artifact_layout(
        tmp_path, monkeypatch):
    out = _install(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    monkeypatch.setattr(scenario, "MAX_STEPS", 6)
    assert runner_a16z.phase_branches(progress=None) == 0

    for name in ("decision_problem.json", "evidence_manifest.json",
                 "freeze_manifest.json", "evaluator_ledger.json",
                 "recommendation_result.json", "branch_input_diff.json",
                 "historical_cutoff_validation.json"):
        assert (out / name).is_file(), name
    assert (out / "adapter" / "adapted_world.json").is_file()
    assert (out / "candidates" / "candidates.json").is_file()

    candidates = json.loads(
        (out / "candidates" / "candidates.json").read_text(encoding="utf-8"))
    assert [entry["candidate_id"] for entry in candidates] == [
        f"user_{index:03d}" for index in range(1, 7)]
    assert all(entry["provenance"]["source"] == "user_supplied"
               for entry in candidates)

    for entry in candidates:
        branch = out / "branches" / entry["candidate_id"]
        for name in ("llm_calls.jsonl", "step_ledger.jsonl",
                     "observations.jsonl", "guard_ledger.jsonl",
                     "committed_events.jsonl", "branch_result.json",
                     "trace_report.json"):
            assert (branch / name).is_file(), f"{entry} / {name}"

    frozen = freeze_lib.load_manifest(out / "freeze_manifest.json")
    assert frozen["missing_required_entries"] == []
    isolation = json.loads(
        (out / "branch_input_diff.json").read_text(encoding="utf-8"))
    assert isolation["verdict"] == "only_the_salary_differs"


def test_the_evaluator_ledger_reads_only_attributed_turns(tmp_path,
                                                          monkeypatch):
    out = _install(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    monkeypatch.setattr(scenario, "MAX_STEPS", 6)
    runner_a16z.phase_branches(progress=None)
    ledger = json.loads(
        (out / "evaluator_ledger.json").read_text(encoding="utf-8"))
    assert ledger["subject_actor"] == scenario.SUBJECT_NAME
    for branch in ledger["branches"]:
        assert set(branch["metrics"]) == {"valid_offer_accepted",
                                          "salary_savings_vs_300k"}
        assert branch["terminal_status"] in ("success", "failure", "cutoff",
                                             "incomplete")
        metric = branch["metrics"]["valid_offer_accepted"]
        if metric["value"]:
            texts = metric["cited_event_texts"]
            assert texts
            owners = []
            for text in texts:
                assert ANCHOR in text
                owners.append(text.split(ANCHOR, 1)[1].lstrip().split(":")[0])
            assert scenario.SUBJECT_NAME in owners
        savings = branch["metrics"]["salary_savings_vs_300k"]["value"]
        assert savings == float(scenario.salary_savings_mapping()[
            branch["candidate_key"]])


def test_a_run_whose_offers_never_left_the_hiring_lead_is_refused(
        tmp_path, monkeypatch):
    """The shape the LIVE run actually produced, driven end to end.

    The insertion actor keeps its own fixed line instead of restating the
    candidate, so no offer reaches anyone else.  The runner must complete
    -- writing every ledger, trace, and check -- while the RANKING is
    refused: no winner in ``recommendation_result.json``, the refusal in
    the evaluator ledger, and a report that says so instead of rendering
    a comparison that does not exist.  Before defect D2 was closed this
    same run published a confident winner.
    """
    out = _install(monkeypatch, tmp_path)
    _stub_provider(monkeypatch, enact_candidate=False)
    monkeypatch.setattr(scenario, "MAX_STEPS", 6)
    assert runner_a16z.phase_branches(progress=None) == 0
    assert runner_a16z.phase_audit(progress=None) == 0

    refusal = json.loads(
        (out / "recommendation_result.json").read_text(encoding="utf-8"))
    assert refusal["refused"] is True
    assert refusal["error_type"] == "InterventionNotDeliveredError"
    assert "refusing to rank" in refusal["reason"]
    assert "best_candidate_id" not in refusal
    assert set(refusal["per_branch_delivery"]) == {
        f"user_{index + 1:03d}" for index in range(6)}
    for fact in refusal["per_branch_delivery"].values():
        assert fact["status"] == "not_delivered"
        assert fact["reached_actors"] == []

    # the same refusal is the evaluator ledger's ranking block ...
    ledger = json.loads(
        (out / "evaluator_ledger.json").read_text(encoding="utf-8"))
    assert ledger["ranking"]["refused"] is True
    assert "best_candidate_id" not in ledger["ranking"]
    assert (out / "ranking_refusal.json").is_file()

    # ... and the report states it, under the mandatory banner, without
    # rendering the comparison sections.
    report = (out / "UNDER_THE_HOOD_REPORT.md").read_text(encoding="utf-8")
    assert report.startswith("# UNCALIBRATED LIVE-MODEL EXPLORATORY "
                             "SIMULATION")
    assert "RANKING REFUSED" in report
    assert "No winner is reported for this run" in report
    assert "## 12. " not in report

    # every per-branch artifact still exists: the refusal removes the
    # winner and nothing else
    for index in range(6):
        branch = out / "branches" / f"user_{index + 1:03d}"
        for name in ("step_ledger.jsonl", "committed_events.jsonl",
                     "branch_result.json", "trace_report.json"):
            assert (branch / name).is_file(), f"{branch.name}/{name}"


def test_the_audit_phase_writes_delivery_and_report(tmp_path, monkeypatch):
    out = _install(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    monkeypatch.setattr(scenario, "MAX_STEPS", 6)
    runner_a16z.phase_branches(progress=None)
    assert runner_a16z.phase_audit(progress=None) == 0
    for name in ("offer_delivery_check.json", "UNDER_THE_HOOD_REPORT.md"):
        assert (out / name).is_file(), name
    delivery = json.loads(
        (out / "offer_delivery_check.json").read_text(encoding="utf-8"))
    assert delivery["subject_actor"] == scenario.SUBJECT_NAME
    assert delivery["branch_count"] == 6
    assert delivery["verdict"] in offer_delivery.INTERPRETATION
    report = (out / "UNDER_THE_HOOD_REPORT.md").read_text(encoding="utf-8")
    assert report.startswith("# UNCALIBRATED LIVE-MODEL EXPLORATORY "
                             "SIMULATION")
    for heading in ("## 1. ", "## 12. ", "## 20. ",
                    "# POST-HOC REAL-OUTCOME COMPARISON"):
        assert heading in report, heading


def test_instrumentation_proves_no_call_bypassed_the_recorder(tmp_path,
                                                              monkeypatch):
    out = _install(monkeypatch, tmp_path)
    _stub_provider(monkeypatch)
    monkeypatch.setattr(scenario, "MAX_STEPS", 6)
    runner_a16z.phase_branches(progress=None)
    payload = json.loads(
        (out / f"instrumentation_{scenario.EXPERIMENT_ID}.json").read_text(
            encoding="utf-8"))
    proof = payload["equality_proof"]
    assert proof["all_equal"] is True
    assert proof["ledger_records_written"] > 0
    master = rec.read_ledger(out / "all_llm_calls.jsonl")
    assert len(master) == proof["ledger_records_written"]
    assert len({record["call_id"] for record in master}) == len(master)
    assert {record["role"] for record in master} <= {"actor", "game_master"}


def test_a_wrong_compiled_cast_is_refused_not_repaired(tmp_path,
                                                       monkeypatch):
    out = _install(monkeypatch, tmp_path)
    manifest = _synthetic_manifest()
    manifest["actors"].append({"name": "Outside Recruiter",
                               "private_context": "An extra actor."})
    (out / "compiler" / "final_scene_manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    _stub_provider(monkeypatch)
    with pytest.raises(SystemExit, match="not the declared five actors"):
        runner_a16z.phase_branches(progress=None)


def test_the_compile_attempt_gate_rejects_a_prewritten_outcome():
    manifest = _synthetic_manifest()
    manifest["starting_events"].append({
        "time": START, "visible_to": [scenario.SUBJECT_NAME],
        "description": "The offer has been made to Richard Zheng."})
    verdict = runner_a16z.evaluate_compile_attempt("compiled", "", manifest)
    assert verdict["accepted"] is False
    assert "no_prewritten_outcome_in_starting_events" in \
        verdict["rejection_reasons"]


def test_the_compile_attempt_gate_does_not_fire_on_a_negated_statement():
    """Regression: 'no offer has been made' is the OPPOSITE of a
    prewritten outcome, and the first live compile run was rejected three
    times because the gate could not tell the difference."""
    manifest = _synthetic_manifest()
    manifest["starting_events"].append({
        "time": START, "visible_to": [scenario.SUBJECT_NAME],
        "description": "The simulation begins with the hiring process in "
                       "its initial state: no offer has been prepared, "
                       "authorized, issued, or discussed with Richard "
                       "Zheng."})
    verdict = runner_a16z.evaluate_compile_attempt("compiled", "", manifest)
    assert verdict["prewritten_outcome_findings"] == []
    assert verdict["accepted"] is True, verdict["rejection_reasons"]


def test_the_compiler_inputs_state_no_decision_deadline():
    """Regression: the scope note's knowledge-horizon wording must not be
    parsed by the production window guard as a narrower DECISION deadline.
    The first live compile run failed three times on exactly that."""
    from datetime import datetime, timezone

    from compiler.scene_guards import question_deadline

    payload = scenario.build_problem_payload()
    deadline = question_deadline(
        scenario.compiler_question(payload),
        scenario.compiler_context(payload),
        datetime(2025, 7, 1, 16, 0, tzinfo=timezone.utc))
    assert deadline == (None, None, None), deadline


def test_the_compile_attempt_gate_rejects_a_wrong_cast():
    manifest = _synthetic_manifest()
    manifest["actors"] = manifest["actors"][:4]
    verdict = runner_a16z.evaluate_compile_attempt("compiled", "", manifest)
    assert verdict["accepted"] is False
    assert "cast_is_exactly_the_declared_five" in \
        verdict["rejection_reasons"]


def test_the_compile_attempt_gate_accepts_a_clean_manifest():
    verdict = runner_a16z.evaluate_compile_attempt(
        "compiled", "", _synthetic_manifest())
    assert verdict["accepted"] is True, verdict["rejection_reasons"]
    assert verdict["compiled_cast_in_declaration_order"] == list(
        scenario.REQUIRED_CAST)
