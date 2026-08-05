"""The settling experiment's deterministic pieces.

No live call, no engine run: these cover the arm construction, the forced
observer-routing control, the enactment reading, and the verdict rule --
the parts a reader has to trust when reading ``SETTLING_RESULT.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.full_trace_validation import settling
from experiments.full_trace_validation import report_settling

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
FROZEN_WORLD = ARTIFACT_ROOT / "peter_supplied" / "adapter" / \
    "adapted_world.json"


def _frozen_world():
    contracts = pytest.importorskip(
        "sworldmodel.decision.contracts",
        reason="the contract layer needs the engine environment")
    if not FROZEN_WORLD.is_file():
        pytest.skip("the frozen Peter world artifact is not present")
    return contracts.CompiledDecisionWorld.from_dict(
        json.loads(FROZEN_WORLD.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# arm construction
# ---------------------------------------------------------------------------


def test_arm_a_is_the_frozen_world_untouched():
    world = _frozen_world()
    assert settling.arm_world(world, "a") is world


def test_arm_b_differs_only_in_starting_events():
    world = _frozen_world()
    arm_b = settling.arm_world(world, "b")
    assert arm_b.starting_events == ()
    difference = settling.arm_difference(world, arm_b)
    assert difference["fields_that_differ"] == ["starting_events"]
    assert difference["identical_except_starting_events"] is True
    # the identity fields a comparison depends on are untouched
    assert arm_b.world_id == world.world_id
    assert arm_b.shared_context == world.shared_context
    assert [a.to_dict() for a in arm_b.actors] == \
           [a.to_dict() for a in world.actors]
    assert arm_b.intervention_insertion_point.to_dict() == \
           world.intervention_insertion_point.to_dict()
    # and it is a real contract instance, not a patched object
    assert arm_b.content_hash() != world.content_hash()


def test_arm_b_refuses_a_world_with_nothing_to_remove():
    world = _frozen_world()
    arm_b = settling.arm_world(world, "b")
    with pytest.raises(settling.ForcedObserverControlError):
        settling.arm_world(arm_b, "b")


def test_unknown_arm_is_refused():
    world = _frozen_world()
    with pytest.raises(ValueError):
        settling.arm_world(world, "c")


# ---------------------------------------------------------------------------
# the forced observer-routing control
# ---------------------------------------------------------------------------


class _Cursor:
    step = 1

    def on_gm_call(self):
        return self.step


class _FakeForcedGM(settling.ForcedRosterObserverGM):
    """The control's own logic with the network parent stubbed out.

    ``__init__`` is bypassed deliberately: the parent builds a recorded
    live model, and this test is about which prompts the control
    intercepts, not about the transport.
    """

    def __init__(self, roster_names, control_log):  # noqa: D107
        self.roster_names = tuple(roster_names)
        self.control_log = control_log
        self.branch_id = "br_test"
        self.cursor = _Cursor()
        self.fell_through = []

    def _super_sample_text(self, prompt, **kwargs):
        self.fell_through.append(prompt)
        return "LIVE"

    # stand in for RecordedDeepSeekChatModel.sample_text
    def sample_text(self, prompt, *, max_tokens=None, terminators=(),
                    **kwargs):
        if settling.OBSERVER_QUESTION in (prompt or ""):
            answer = self.forced_answer
            self.control_log.append({
                "branch_id": self.branch_id,
                "step": self.cursor.on_gm_call(),
                "intercepted_question": settling.OBSERVER_QUESTION,
                "forced_answer": answer,
                "prompt_tail": (prompt or "")[-400:],
                "provider_called": False,
            })
            return answer
        return self._super_sample_text(prompt, max_tokens=max_tokens,
                                       terminators=terminators, **kwargs)


def test_observer_question_matches_upstream_verbatim():
    """The control keys off upstream's own question string. If upstream
    reworded it the control would silently stop firing, so the string is
    pinned against the pinned upstream source."""
    upstream = Path("/home/user/concordia/concordia/components/game_master"
                    "/event_resolution.py")
    if not upstream.is_file():
        pytest.skip("the pinned upstream checkout is not present")
    text = upstream.read_text(encoding="utf-8")
    # upstream wraps the question across two source lines
    assert "Which entities are aware of the event? Answer with a " in text
    assert "comma-separated list of entity names." in text
    assert settling.OBSERVER_QUESTION == (
        "Which entities are aware of the event? Answer with a "
        "comma-separated list of entity names.")


def test_forced_control_answers_the_full_roster():
    log = []
    model = _FakeForcedGM(("Beckett Zahedi", "Peter Thiel"), log)
    prompt = ("Event that occurred: something.\nQuestion: "
              + settling.OBSERVER_QUESTION + "\nAnswer: ")
    assert model.sample_text(prompt) == "Beckett Zahedi, Peter Thiel"
    assert len(log) == 1
    assert log[0]["provider_called"] is False
    assert log[0]["forced_answer"] == "Beckett Zahedi, Peter Thiel"
    assert model.fell_through == []


def test_forced_control_does_not_touch_any_other_call():
    log = []
    model = _FakeForcedGM(("Beckett Zahedi", "Peter Thiel"), log)
    assert model.sample_text("What happened next?") == "LIVE"
    assert log == []
    assert model.fell_through == ["What happened next?"]


def test_forced_answer_splits_into_exact_roster_names():
    """Upstream splits the answer on ``,`` and strips ``' .,'``; the
    forced answer must therefore resolve by the EXACT-match path of the
    roster-validated observer seam, not by any looser path."""
    builder = pytest.importorskip(
        "sworldmodel.backends.concordia_local.builder",
        reason="the observer seam needs the engine environment")
    roster = ("Beckett Zahedi", "Peter Thiel")
    log = []
    model = _FakeForcedGM(roster, log)
    answer = model.forced_answer
    pieces = [piece.strip(" .,") for piece in answer.split(",")]
    assert pieces == list(roster)
    resolver = builder.RosterValidatedMakeObservation.resolve_observer_name
    for piece in pieces:
        # bound method call on a minimal stand-in carrying the roster maps
        stub = type("S", (), {
            "_exact": {name: name for name in roster},
            "_folded": {name.casefold(): [name] for name in roster}})()
        assert resolver(stub, piece) == (piece, "exact")


def test_forced_control_refuses_an_empty_roster():
    """Broadcasting to nobody would silently reproduce the routing
    failure the control exists to remove."""
    with pytest.raises(settling.ForcedObserverControlError):
        settling.validate_roster(())
    with pytest.raises(settling.ForcedObserverControlError):
        settling.validate_roster(["Beckett Zahedi", "  "])
    assert settling.validate_roster(["A", "B"]) == ("A", "B")


# ---------------------------------------------------------------------------
# the enactment reading
# ---------------------------------------------------------------------------


CANDIDATE = ("Subject: 7.24x more useful work per GPU dollar\n\n"
             "I built a supervisory optimizer for GPU fleets that "
             "produced 7.24x more SLA-safe goodput per dollar. "
             "Would you be open to a 20-minute call next week?")


def test_enactment_true_when_the_sender_reproduces_a_fragment():
    turn = ("Beckett Zahedi sends the email: \"I built a supervisory "
            "optimizer for GPU fleets that produced 7.24x more SLA-safe "
            "goodput per dollar.\"")
    check = settling.enactment_check(first_turn_text=turn,
                                     candidate_action=CANDIDATE)
    assert check["sender_enacted_candidate_verbatim"] is True
    assert check["fragments_reproduced_in_sender_first_turn"] >= 1
    assert check["example_reproduced"]


def test_enactment_false_when_the_sender_only_waits():
    turn = ("Beckett Zahedi waits for Peter Thiel's reply, checking his "
            "inbox periodically but not sending any follow-up.")
    check = settling.enactment_check(first_turn_text=turn,
                                     candidate_action=CANDIDATE)
    assert check["sender_enacted_candidate_verbatim"] is False
    assert check["fragments_reproduced_in_sender_first_turn"] == 0
    assert check["example_not_reproduced"]


def test_enactment_false_on_a_paraphrase():
    """A paraphrase is deliberately NOT counted as enactment; the
    limitation is stated in the result document."""
    turn = ("Beckett Zahedi emails Peter about a GPU scheduler that made "
            "fleets far more efficient and asks for twenty minutes.")
    check = settling.enactment_check(first_turn_text=turn,
                                     candidate_action=CANDIDATE)
    assert check["sender_enacted_candidate_verbatim"] is False


def test_enactment_handles_a_missing_turn():
    check = settling.enactment_check(first_turn_text=None,
                                     candidate_action=CANDIDATE)
    assert check["sender_enacted_candidate_verbatim"] is False
    assert check["longest_shared_run_chars"] == 0
    assert check["candidate_token_overlap_ratio"] == 0.0


def test_overlap_numbers_separate_waiting_from_sending_own_words():
    """The content-blind overlap numbers exist because the binary
    reading reports 'waited' and 'sent, in its own words' identically."""
    waited = ("Beckett Zahedi waits for a reply, checking his inbox "
              "periodically but not sending any follow-up.")
    own_words = ("Beckett Zahedi tightens the subject line to \"Aurelius: "
                 "7.24x GPU goodput/$\" and sends the email to Peter "
                 "Thiel through the established channel.")
    waited_check = settling.enactment_check(first_turn_text=waited,
                                            candidate_action=CANDIDATE)
    sent_check = settling.enactment_check(first_turn_text=own_words,
                                          candidate_action=CANDIDATE)
    assert waited_check["sender_enacted_candidate_verbatim"] is False
    assert sent_check["sender_enacted_candidate_verbatim"] is False
    assert sent_check["candidate_token_overlap_ratio"] > \
        waited_check["candidate_token_overlap_ratio"]


def test_longest_common_substring_is_exact():
    assert settling.longest_common_substring_chars("abcdef", "zzcdezz") == 3
    assert settling.longest_common_substring_chars("", "abc") == 0
    assert settling.longest_common_substring_chars("abc", "") == 0
    assert settling.longest_common_substring_chars("abc", "abc") == 3


def test_token_overlap_is_symmetric_and_bounded():
    left = "the quick brown fox"
    right = "the lazy brown dog"
    value = settling.token_overlap_ratio(left, right)
    assert value == settling.token_overlap_ratio(right, left)
    assert 0.0 < value < 1.0
    assert settling.token_overlap_ratio(left, left) == 1.0
    assert settling.token_overlap_ratio("", left) == 0.0


def test_sender_first_turn_picks_the_first_successful_sender_call():
    calls = [
        {"role": "game_master", "actor_name": None, "call_id": "c0"},
        {"role": "actor", "actor_name": "Beckett Zahedi", "call_id": "c1",
         "step": 1, "error": "503", "response_raw": None},
        {"role": "actor", "actor_name": "Beckett Zahedi", "call_id": "c2",
         "step": 1, "error": None, "response_raw": "the real turn"},
        {"role": "actor", "actor_name": "Peter Thiel", "call_id": "c3",
         "step": 2, "error": None, "response_raw": "recipient turn"},
    ]
    first = settling.sender_first_turn(calls, "Beckett Zahedi")
    assert first["call_id"] == "c2"
    assert first["text"] == "the real turn"


def test_sender_first_turn_reports_absence_rather_than_inventing():
    first = settling.sender_first_turn([], "Beckett Zahedi")
    assert first["text"] is None
    assert "unavailable" in first


# ---------------------------------------------------------------------------
# the verdict rule
# ---------------------------------------------------------------------------


def _aggregate(enact_a, enact_b, n=3):
    def arm(letter, hits):
        label, note = settling.ARMS[letter]
        return {
            "arm": letter, "arm_label": label, "arm_note": note,
            "reps_recorded": n,
            "sender_enacted_candidate_verbatim": {
                "n": n, "hits": hits, "rate": hits / n if n else None},
            "candidate_text_in_recipient_prompts": {
                "n": n, "hits": hits, "rate": hits / n if n else None},
            "intervention_delivered_status": ["not_delivered"] * n,
            "ranking": ["REFUSED"] * n,
            "terminal_status": ["cutoff"] * n,
            "unresolved_observer_count": [0] * n,
            "guard_interventions": [0] * n,
            "forced_observer_interceptions": [4] * n,
            "longest_shared_run_chars": [12] * n,
            "candidate_token_overlap_ratio": [0.1] * n,
            "provider_served": ["deepseek-v4-flash"],
            "live_calls": 4 * n, "live_call_errors": 0,
            "live_call_retries": 0,
            "sender_first_turns": [{"rep": i + 1, "text": "t"}
                                   for i in range(n)],
            "recipient_first_turn_prompt_sha256": ["h"] * n,
        }
    return {
        "label": "L", "generated_at": "now",
        "environment": {"repository_sha": "abc"},
        "model_configuration": {"provider": "deepseek",
                                "model": "deepseek-chat"},
        "candidate_id": "user_001", "reps_per_arm_declared": n,
        "arms": {"a": arm("a", enact_a), "b": arm("b", enact_b)},
        "totals": {"live_calls": 8 * n, "live_call_errors": 0,
                   "live_call_retries": 0},
    }


def test_verdict_r3_when_arm_b_never_enacts():
    result = report_settling.verdict(_aggregate(0, 0))
    assert result["survived"] == "R3"
    assert "0/3" in result["arm_b_enactment"]
    assert "engine semantic change" in result["practical_fix"]


def test_verdict_r1_strong_when_arm_b_enacts_more():
    result = report_settling.verdict(_aggregate(0, 3))
    assert result["survived"] == "R1_strong"
    assert result["practical_fix"] == "compiler prompt hygiene"


def test_verdict_r3_when_both_arms_enact_equally():
    result = report_settling.verdict(_aggregate(3, 3))
    assert result["survived"] == "R3"
    assert "same rate" in result["reason"]


def test_verdict_undetermined_without_reps():
    result = report_settling.verdict(_aggregate(0, 0, n=0))
    assert result["survived"] == "UNDETERMINED"


def test_result_document_states_the_verdict_and_the_limitation(tmp_path):
    aggregate = _aggregate(0, 0)
    path = report_settling.write_result(tmp_path, aggregate)
    text = path.read_text(encoding="utf-8")
    assert "R3 survived" in text
    assert "n = 3 per arm is small" in text
    assert "says nothing about Peter Thiel" in text
    assert report_settling.RUN_LABEL in text
    readme = report_settling.write_readme(tmp_path, aggregate)
    assert "R3 survived" in readme.read_text(encoding="utf-8")
