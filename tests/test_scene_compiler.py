"""minimal_scene_v1: schema strictness, the hard semantic-call budget,
deterministic validation/normalization, adapter privacy and visibility,
the natural-language resolution wrapper, and scripted end-to-end compiles."""
import json

import pytest

from sworldmodel import Engine

from compiler.scene_adapter import instantiate_scene
from compiler.scene_llm import (CompilerCallBudgetExceeded,
                                MAX_SEMANTIC_CALLS, SceneCaller)
from compiler.scene_pipeline import compile_scene, instantiate_compiled
from compiler.scene_resolution import NLResolution, build_nl_terminal
from compiler.scene_schema import validate_manifest_shape
from compiler.scene_validate import validate_scene

START = "2026-07-27T09:00:00-05:00"
CUTOFF = "2026-08-10T09:00:00-05:00"
QUESTION = "Will Person B respond to Person A's message before the cutoff?"

MANIFEST = {
    "actors": [
        {"name": "Person A",
         "private_context": "A wants a response from B about A's proposal. "
                            "They have no prior relationship."},
        {"name": "Person B",
         "private_context": "B receives many approaches and sometimes "
                            "responds to short specific ones. B does not "
                            "know A."},
    ],
    "shared_context": "A has prepared a short message about the proposal "
                      "and can send it to B through an established channel.",
    "starting_events": [
        {"time": START, "description": "A sends the prepared message to B.",
         "visible_to": ["Person A"]},
    ],
    "resolution": "Resolve YES only if the persistent event history shows "
                  "that B actually sent A a response before the cutoff. "
                  "Otherwise resolve NO at the cutoff.",
}

APPROVE = {"verdict": "APPROVE", "defects": []}


class Script:
    def __init__(self, responses):
        self.responses = [r if isinstance(r, str) else json.dumps(r)
                          for r in responses]
        self.n = 0

    def __call__(self, system, user):
        if self.n >= len(self.responses):
            raise AssertionError(f"script exhausted after {self.n} calls")
        r = self.responses[self.n]
        self.n += 1
        return r, {"prompt_tokens": 10, "completion_tokens": 5}


def compile_scripted(responses, **kw):
    caller = SceneCaller(transport=Script(responses))
    return compile_scene(QUESTION, START, CUTOFF, caller=caller, **kw), caller


# ------------------------------------------------------------------ schema
def test_schema_rejects_extra_and_missing_fields():
    bad = dict(MANIFEST, extra_field=1)
    assert any("unknown top-level" in e for e in validate_manifest_shape(bad))
    bad = {k: v for k, v in MANIFEST.items() if k != "resolution"}
    assert any("missing required" in e for e in validate_manifest_shape(bad))
    bad = json.loads(json.dumps(MANIFEST))
    bad["actors"][0]["habits"] = "checks messages hourly"
    assert any("unknown fields" in e for e in validate_manifest_shape(bad))
    bad = json.loads(json.dumps(MANIFEST))
    bad["starting_events"][0]["time"] = "2026-07-27 09:00"   # naive
    assert any("timezone-aware" in e for e in validate_manifest_shape(bad))
    assert validate_manifest_shape(MANIFEST) == []


# ------------------------------------------------------------------ budget
def test_budget_enforced_before_the_fourth_call():
    caller = SceneCaller(transport=Script([APPROVE] * 10))
    for i in range(MAX_SEMANTIC_CALLS):
        caller.semantic_call(f"slot{i}", "s", "u")
    with pytest.raises(CompilerCallBudgetExceeded):
        caller.semantic_call("slot_over", "s", "u")
    assert caller.metrics()["semantic_calls"] == MAX_SEMANTIC_CALLS


def test_every_provider_request_is_logged_with_tokens():
    caller = SceneCaller(transport=Script([MANIFEST]))
    caller.semantic_call("call_1_scene", "sys", "usr")
    m = caller.metrics()
    assert m["provider_requests"] == 1
    assert m["total_prompt_tokens"] == 10
    assert caller.requests[0]["system"] == "sys"
    assert caller.requests[0]["response"]


# -------------------------------------------------------------- validation
def test_alias_merge_and_duplicate_event_collapse():
    m = json.loads(json.dumps(MANIFEST))
    m["actors"].append({"name": "  person a ",
                        "private_context": "extra note about A."})
    m["starting_events"].append(dict(m["starting_events"][0]))
    scene, report, errors, warnings = validate_scene(m, START, CUTOFF)
    assert errors == []
    assert len(scene["actors"]) == 2
    assert "extra note about A." in scene["actors"][0]["private_context"]
    assert len(scene["starting_events"]) == 1
    assert report["merged_or_collapsed"] >= 2


def test_visible_to_short_form_resolves_only_when_unambiguous():
    m = json.loads(json.dumps(MANIFEST))
    m["actors"][0]["name"] = "Tomás García"
    m["starting_events"][0]["visible_to"] = ["Tomás"]
    scene, report, errors, _ = validate_scene(m, START, CUTOFF)
    assert errors == []
    assert scene["starting_events"][0]["visible_to"] == ["Tomás García"]
    assert any("resolved to the one declared actor" in n
               for n in report["notes"])
    # two candidates -> ambiguity is an error, never a guess
    m["actors"].append({"name": "Tomás Rivera", "private_context": "other"})
    _, _, errors, _ = validate_scene(m, START, CUTOFF)
    assert any("is ambiguous between" in e for e in errors)


def test_unknown_visible_to_and_late_events_fail():
    m = json.loads(json.dumps(MANIFEST))
    m["starting_events"][0]["visible_to"] = ["Person Z"]
    _, _, errors, _ = validate_scene(m, START, CUTOFF)
    assert any("does not resolve" in e for e in errors)
    m = json.loads(json.dumps(MANIFEST))
    m["starting_events"][0]["time"] = "2026-09-01T09:00:00-05:00"
    _, _, errors, _ = validate_scene(m, START, CUTOFF)
    assert any("after the cutoff" in e for e in errors)


def test_pre_start_event_clamps_and_substring_names_warn():
    m = json.loads(json.dumps(MANIFEST))
    m["starting_events"][0]["time"] = "2026-07-20T09:00:00-05:00"
    m["actors"].append({"name": "Person B Senior",
                        "private_context": "a distinct person."})
    scene, report, errors, warnings = validate_scene(m, START, CUTOFF)
    assert errors == []
    assert scene["starting_events"][0]["time"].startswith("2026-07-27")
    assert any("contain one another" in w for w in warnings)
    assert len(scene["actors"]) == 3          # never merged on a guess


def test_resolution_as_occurred_event_is_rejected():
    m = json.loads(json.dumps(MANIFEST))
    m["starting_events"].append({
        "time": START, "description": m["resolution"],
        "visible_to": ["Person A"]})
    _, _, errors, _ = validate_scene(m, START, CUTOFF)
    assert any("must not already be an occurred event" in e for e in errors)


def test_hostile_invisibles_offsets_and_bad_frames():
    """Agent D regressions: zero-width names/resolutions are empty; equal
    instants in different offsets are exact duplicates; malformed caller
    start/cutoff returns errors instead of raising; ws-variant resolution
    still matches an occurred event."""
    m = json.loads(json.dumps(MANIFEST))
    m["actors"].append({"name": "​", "private_context": "ghost"})
    _, _, errors, _ = validate_scene(m, START, CUTOFF)
    assert any("normalizes to empty" in e for e in errors)
    m = json.loads(json.dumps(MANIFEST))
    m["resolution"] = "​​"
    _, _, errors, _ = validate_scene(m, START, CUTOFF)
    assert any("resolution is empty" in e for e in errors)
    m = json.loads(json.dumps(MANIFEST))
    m["starting_events"].append(dict(m["starting_events"][0],
                                     time="2026-07-27T14:00:00Z"))
    scene, _, errors, _ = validate_scene(m, START, CUTOFF)   # same instant
    assert errors == [] and len(scene["starting_events"]) == 1
    for bad_start in ("2026-07-27T09:00", "sideways", "2026-13-45T99:99"):
        _, _, errors, _ = validate_scene(
            json.loads(json.dumps(MANIFEST)), bad_start, CUTOFF)
        assert any("invalid start/cutoff" in e for e in errors), bad_start
    m = json.loads(json.dumps(MANIFEST))
    m["resolution"] = "A  sends the   prepared message to B."
    m["starting_events"][0]["description"] = "A sends the prepared message to B."
    _, _, errors, _ = validate_scene(m, START, CUTOFF)
    assert any("must not already be an occurred event" in e for e in errors)


# ------------------------------------------- prewritten-outcome regressions
# The five cases the defect class requires.  The deterministic guard is a
# BACKUP for near-identical wording; paraphrase and the already-happened
# judgement belong to Call 2 (proved separately in the Call-3 tests).
AND_RESOLUTION = ("Resolve YES only if the persistent event history shows "
                  "that the chief executive posted the launch announcement "
                  "and a design partner reposted the launch announcement "
                  "before the cutoff. Otherwise resolve NO.")


def scene_with(events, resolution=AND_RESOLUTION):
    return {"actors": [{"name": "Person A", "private_context": "a"},
                       {"name": "Person B", "private_context": "b"}],
            "shared_context": "the shared situation",
            "starting_events": [dict(e, visible_to=e.get("visible_to",
                                                         ["Person A"]))
                                for e in events],
            "resolution": resolution}


def test_prewrite_full_outcome_is_an_error():
    m = scene_with([
        {"time": START, "description": "The chief executive posted the "
                                       "launch announcement."},
        {"time": START, "description": "A design partner reposted the "
                                       "launch announcement."}])
    _, _, errors, _ = validate_scene(m, START, CUTOFF, question="q?")
    assert any("entire YES condition" in e for e in errors)


def test_prewrite_one_half_of_an_and_outcome_is_flagged():
    m = scene_with([{"time": START,
                     "description": "The chief executive posted the launch "
                                    "announcement."}])
    _, _, errors, warnings = validate_scene(m, START, CUTOFF, question="q?")
    assert errors == []                      # Call 2 adjudicates half-matches
    assert any("closely matches part of the resolution" in w
               for w in warnings)


def test_prewrite_paraphrase_is_left_to_the_reviewer():
    """A paraphrase must NOT be blocked by the shallow guard -- code cannot
    read paraphrase, so it stays silent and Call 2 owns the judgement."""
    m = scene_with([{"time": START,
                     "description": "The company's founder puts the v4 news "
                                    "live on social media."}])
    _, _, errors, warnings = validate_scene(m, START, CUTOFF, question="q?")
    assert errors == []
    assert not any("closely matches" in w for w in warnings)


def test_prewrite_explicitly_given_event_still_only_warns():
    """When the question says it already happened, the event is legitimate;
    the guard must never hard-error on a partial match."""
    m = scene_with([{"time": START,
                     "description": "The chief executive posted the launch "
                                    "announcement."}])
    _, _, errors, _ = validate_scene(
        m, START, CUTOFF,
        question="The chief executive posted the launch announcement this "
                 "morning. Will a design partner repost it by Friday?")
    assert errors == []


def test_legitimate_starting_event_is_not_flagged():
    m = scene_with([{"time": START,
                     "description": "The quarterly planning cycle opens and "
                                    "the team receives its brief."}])
    _, _, errors, warnings = validate_scene(m, START, CUTOFF, question="q?")
    assert errors == []
    assert not any("closely matches" in w for w in warnings)


# ------------------------------------------------ question-window regressions
def window_scene(resolution):
    return {"actors": [{"name": "Person A", "private_context": "a"}],
            "shared_context": "the shared situation",
            "starting_events": [],
            "resolution": resolution}


def test_window_absolute_deadline_must_appear_in_resolution():
    q = "Will the committee schedule the hearing before September 13, 2026?"
    bad = window_scene("Resolve YES if the history shows the hearing was "
                       "scheduled before 2026-09-30. Otherwise NO.")
    _, _, errors, _ = validate_scene(bad, "2026-07-15T09:00:00+00:00",
                                     "2026-09-30T09:00:00+00:00", question=q)
    assert any("narrower than the compile cutoff" in e for e in errors)
    good = window_scene("Resolve YES if the history shows the hearing was "
                        "scheduled before 2026-09-13. Otherwise NO at the "
                        "cutoff.")
    _, _, errors, _ = validate_scene(good, "2026-07-15T09:00:00+00:00",
                                     "2026-09-30T09:00:00+00:00", question=q)
    assert errors == []


def test_window_relative_days_resolved_from_start():
    q = "Will the transport committee schedule a public hearing within 60 days?"
    bad = window_scene("Resolve YES if a hearing is scheduled before the "
                       "cutoff on 2026-09-30. Otherwise NO.")
    _, _, errors, _ = validate_scene(bad, "2026-07-15T09:00:00+00:00",
                                     "2026-09-30T09:00:00+00:00", question=q)
    assert any("within 60 days" in e for e in errors)
    good = window_scene("Resolve YES if a hearing is scheduled on or before "
                        "2026-09-13 (60 days from the start). Otherwise NO.")
    _, _, errors, _ = validate_scene(good, "2026-07-15T09:00:00+00:00",
                                     "2026-09-30T09:00:00+00:00", question=q)
    assert errors == []


def test_window_relative_weeks_and_restated_phrase_accepted():
    q = "Will the studio send any decision within two weeks?"
    good = window_scene("Resolve YES if the studio sent a decision within "
                        "two weeks of the start. Otherwise NO.")
    _, _, errors, _ = validate_scene(good, "2026-07-15T09:00:00+00:00",
                                     "2026-09-30T09:00:00+00:00", question=q)
    assert errors == []
    bad = window_scene("Resolve YES if the studio sent a decision before "
                       "2026-09-30. Otherwise NO.")
    _, _, errors, _ = validate_scene(bad, "2026-07-15T09:00:00+00:00",
                                     "2026-09-30T09:00:00+00:00", question=q)
    assert errors and "narrower" in errors[0]


def test_window_equal_to_cutoff_is_legitimate():
    q = "Will the board approve the merger within 14 days?"
    scene = window_scene("Resolve YES if the board approved the merger "
                         "before the cutoff. Otherwise NO at the cutoff.")
    _, _, errors, _ = validate_scene(scene, "2026-08-15T09:00:00+00:00",
                                     "2026-08-29T09:00:00+00:00", question=q)
    assert errors == []          # the question's window IS the cutoff


def test_window_absent_from_question_never_fires():
    q = "Will the landlord reply to the tenant's message?"
    scene = window_scene("Resolve YES if the landlord replied before the "
                         "cutoff. Otherwise NO.")
    _, _, errors, _ = validate_scene(scene, START, CUTOFF, question=q)
    assert errors == []


# ----------------------------------------------------------------- adapter
def build_world():
    scene, _, errors, _ = validate_scene(
        json.loads(json.dumps(MANIFEST)), START, CUTOFF)
    assert errors == []
    return instantiate_scene(scene, QUESTION, START, CUTOFF)


def test_private_context_stays_private_and_visibility_is_enforced():
    world, bindings = build_world()
    a, b = bindings["actor_ids"]["Person A"], bindings["actor_ids"]["Person B"]
    a_mem = " ".join(m.content for m in world.actors[a].memories)
    b_mem = " ".join(m.content for m in world.actors[b].memories)
    assert "no prior relationship" in a_mem
    assert "no prior relationship" not in b_mem       # A's private context
    assert "does not know A" in b_mem
    assert "does not know A" not in a_mem             # B's private context
    assert "established channel" in a_mem and "established channel" in b_mem
    # run the starting event: only Person A (declared visible) perceives it
    res = NLResolution(QUESTION, MANIFEST["resolution"], CUTOFF, "w_test")
    out = Engine(world, {}, build_nl_terminal(res)).run(stop_after_events=4)
    assert out.metrics["events_processed"] >= 1
    a_noticed = world.actors[a].noticed_info
    b_all = (world.actors[b].noticed_info + world.actors[b].available_info)
    assert len(a_noticed) == 1
    assert b_all == []                                # not visible to B


def test_instantiation_is_deterministic_and_replayable():
    w1, _ = build_world()
    w2, _ = build_world()
    assert w1.state_hash() == w2.state_hash()
    replayed = w1.__class__.from_records(
        json.loads(json.dumps(w1.records)))
    assert replayed.state_hash() == w1.state_hash()


# -------------------------------------------------------------- resolution
def test_nl_terminal_false_at_genesis_and_pending_at_cutoff():
    world, _ = build_world()
    res = NLResolution(QUESTION, MANIFEST["resolution"], CUTOFF, "w_test")
    term = build_nl_terminal(res)
    assert term.evaluate(world, False) is None        # false at genesis
    out = Engine(world, {}, term).run()
    assert out.answer["answer"] == "unresolved_pending_judgment"


def test_nl_terminal_judge_recognizes_occurred_event_and_must_cite():
    world, bindings = build_world()

    def judge(records, resolution, question):
        hits = [r["seq"] for r in records
                if r["op"] == "event.fired"
                and "sends the prepared message" in json.dumps(r["data"])]
        if hits:
            return {"answer": "observed", "detail": "the send occurred",
                    "event_seqs": hits}
        return None

    res = NLResolution(QUESTION, MANIFEST["resolution"], CUTOFF, "w_test")
    term = build_nl_terminal(res, judge=judge)
    assert term.evaluate(world, False) is None        # nothing fired yet
    out = Engine(world, {}, term).run()
    assert out.answer["answer"] == "observed"
    assert out.answer["computed_from"]
    # a judge citing nonexistent records is refused
    bad_term = build_nl_terminal(res, judge=lambda r, x, q: {
        "answer": "observed", "event_seqs": [999999]})
    world2, _ = build_world()
    with pytest.raises(Exception):
        Engine(world2, {}, bad_term).run()


# ------------------------------------------------------------- end to end
def test_scripted_first_pass_compile(tmp_path):
    result, caller = compile_scripted([MANIFEST, APPROVE],
                                      out_dir=str(tmp_path / "case"))
    assert result.status == "compiled", result.reason
    assert result.metrics["semantic_calls"] == 2
    assert result.metrics["compiler_version"] == "minimal_scene_v1"
    assert result.metrics["evidence_mode"] == "model_memory_unverified"
    for fname in ("input.json", "call_1_prompt.txt", "call_1_raw_response.txt",
                  "scene_manifest.json", "call_2_prompt.txt",
                  "call_2_raw_response.txt", "scene_review.json",
                  "final_scene_manifest.json", "normalization_report.json",
                  "validation_report.json", "runtime_bindings.json",
                  "initialized_world_snapshot.json",
                  "starting_event_ledger.jsonl", "actor_initial_views.json",
                  "genesis_resolution_check.json", "compiler_metrics.json"):
        assert (tmp_path / "case" / fname).exists(), fname
    world, term, bindings = instantiate_compiled(str(tmp_path / "case"))
    assert world.actors and term.evaluate(world, False) is None


def test_scripted_corrected_compile():
    revise = {"verdict": "REVISE", "defects": [
        {"path": "actors[1].private_context",
         "problem": "invented an exact checking time",
         "correction": "remove the exact time"}]}
    corrected = json.loads(json.dumps(MANIFEST))
    corrected["actors"][1]["private_context"] = \
        "B receives many approaches. B does not know A."
    result, caller = compile_scripted([MANIFEST, revise, corrected])
    assert result.status == "corrected"
    assert result.metrics["semantic_calls"] == 3
    assert result.metrics["repaired_compile"] is True


def test_revise_to_call3_carries_defects_and_changes_only_that_field():
    """The full REVISE -> Call 3 contract: the exact defect list and the
    exact original manifest reach Call 3, the correction touches only the
    defective field, the corrected scene validates and instantiates,
    exactly three semantic stages are used, and no fourth call occurs."""
    prewritten = json.loads(json.dumps(MANIFEST))
    prewritten["starting_events"].append({
        "time": START, "description": "B sends A a response.",
        "visible_to": ["Person B"]})
    defects = [{"path": "starting_events[1]",
                "problem": "This event completes the requested outcome, but "
                           "the question does not say it already happened.",
                "correction": "Remove this event; begin before B responds."}]
    revise = {"verdict": "REVISE", "defects": defects}
    corrected = json.loads(json.dumps(MANIFEST))     # offending event gone
    captured = []

    class Recorder(Script):
        def __call__(self, system, user):
            captured.append((system, user))
            return super().__call__(system, user)

    caller = SceneCaller(transport=Recorder([prewritten, revise, corrected]))
    result = compile_scene(QUESTION, START, CUTOFF, caller=caller)

    assert result.status == "corrected", result.reason
    assert caller.metrics()["semantic_calls"] == 3
    assert caller.semantic_slots == ["call_1_scene", "call_2_review",
                                     "call_3_correction"]
    # the exact defect list and the exact original manifest reached Call 3
    c3_user = captured[2][1]
    assert defects[0]["problem"] in c3_user
    assert defects[0]["correction"] in c3_user
    assert "B sends A a response." in c3_user
    # only the defective field changed
    assert result.manifest["actors"] == MANIFEST["actors"]
    assert result.manifest["shared_context"] == MANIFEST["shared_context"]
    assert result.manifest["resolution"] == MANIFEST["resolution"]
    assert len(result.manifest["starting_events"]) == 1
    # the corrected scene really instantiates, and no fourth call is possible
    world, _ = instantiate_scene(result.manifest, QUESTION, START, CUTOFF)
    assert len(world.actors) == 2
    with pytest.raises(CompilerCallBudgetExceeded):
        caller.semantic_call("call_4", "s", "u")


def test_malformed_output_retries_same_slot_then_fails_structurally():
    """One technical retry per slot, same task and schema, every attempt
    logged with its raw body, no silent salvage of partial JSON."""
    truncated = '{"actors": [{"name": "A", "private_context": "x"}'
    caller = SceneCaller(transport=Script([truncated, truncated]))
    result = compile_scene(QUESTION, START, CUTOFF, caller=caller)
    assert result.status == "failed"
    assert "TECHNICAL_FAILURE" in result.reason
    assert caller.metrics()["semantic_calls"] == 1      # one slot consumed
    assert caller.metrics()["provider_requests"] == 2   # initial + one retry
    assert [r["attempt"] for r in caller.requests] == [0, 1]
    assert all(r["response"] == truncated for r in caller.requests)
    assert all(r["error"] for r in caller.requests)
    # the retry re-sent the identical task and schema
    assert caller.requests[0]["system"] == caller.requests[1]["system"]
    assert caller.requests[0]["user"] == caller.requests[1]["user"]
    assert result.manifest is None                      # nothing salvaged


def test_scripted_abstention_is_structured():
    abstain = {"verdict": "ABSTAIN", "defects": [
        {"path": "scene", "problem": "no identifiable decision-maker",
         "correction": "more context required"}]}
    result, _ = compile_scripted([MANIFEST, abstain])
    assert result.status == "abstained"
    assert "decision-maker" in result.reason


def test_empty_cast_is_a_structured_abstention_not_schema_failure():
    m = {"actors": [], "shared_context": "nothing to build",
         "starting_events": [],
         "resolution": "UNRESOLVABLE: no identifiable decision-maker."}
    result, caller = compile_scripted([m])
    assert result.status == "abstained"
    assert "empty cast" in result.reason
    assert caller.metrics()["semantic_calls"] == 1


def test_compiler_declared_unresolvable_abstains():
    m = json.loads(json.dumps(MANIFEST))
    m["resolution"] = "UNRESOLVABLE: pure factual lookup with no social " \
                      "decision to simulate."
    result, caller = compile_scripted([m])
    assert result.status == "abstained"
    assert caller.metrics()["semantic_calls"] == 1     # no review of nothing


def test_budget_exceeded_is_a_structured_failure():
    revise = {"verdict": "REVISE", "defects": [
        {"path": "x", "problem": "p", "correction": "c"}]}
    # correction returns another REVISE-shaped review?  no -- correction slot
    # returns a manifest; make it invalid so nothing downstream hides the
    # budget: script a 4th-call attempt by feeding revise twice
    caller = SceneCaller(transport=Script([MANIFEST, revise, MANIFEST,
                                           APPROVE]))
    result = compile_scene(QUESTION, START, CUTOFF, caller=caller)
    assert result.status == "corrected"                # 3 calls exactly, ok
    caller2 = SceneCaller(transport=Script([MANIFEST] * 10))
    for i in range(MAX_SEMANTIC_CALLS):
        caller2.semantic_call(f"s{i}", "a", "b")
    r = compile_scene(QUESTION, START, CUTOFF, caller=caller2)
    assert r.status == "failed"
    assert "COMPILER_CALL_BUDGET_EXCEEDED" in r.reason


def test_malformed_provider_output_fails_structurally():
    result, _ = compile_scripted(["this is not json", "still not json"])
    assert result.status == "failed"
    assert "TECHNICAL_FAILURE" in result.reason
    result, _ = compile_scripted([{"actors": [{"name": "A",
                                               "private_context": "x"}],
                                   "shared_context": "x",
                                   "starting_events": [], "resolution": "r",
                                   "extra": 1}])
    assert result.status == "failed"
    assert "SCHEMA_INVALID" in result.reason
