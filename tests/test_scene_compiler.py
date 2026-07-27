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
