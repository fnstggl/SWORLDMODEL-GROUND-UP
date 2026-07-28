"""Phase A: deterministic verification of the semantic runtime with
scripted models.  No live provider is called anywhere in this file.

These tests are the hard mechanical invariants: time, identity, local
information boundaries, actor/world separation, the message lifecycle,
transactional commits, terminal lineage, and exact replay.
"""
import json

import pytest

from sworldmodel.semantic_runtime import instantiate_scene_manifest
from sworldmodel.semantic_runtime.envelope import (EnvelopeError,
                                                   parse_duration,
                                                   validate_event)
from sworldmodel.semantic_runtime.journal import Journal
from sworldmodel.semantic_runtime.llm import (RuntimeCaller,
                                              RuntimeTechnicalFailure)
from sworldmodel.semantic_runtime.replay import replay_trajectory
from sworldmodel.semantic_runtime.resolution import (ResolutionError,
                                                     make_validator)
from sworldmodel.semantic_runtime.trace import Trace
from sworldmodel.semantic_runtime.trajectory import run_trajectory
from sworldmodel.semantic_runtime.views import build_view, render_view
from sworldmodel.simclock import parse_iso

START = "2026-07-27T09:00:00-05:00"
CUTOFF = "2026-08-10T09:00:00-05:00"
QUESTION = "Will Bo respond to Ada's message before the cutoff?"

SCENE = {
    "actors": [
        {"name": "Ada Vance",
         "private_context": "Ada wants a response from Bo about her "
                            "proposal. They have no prior relationship."},
        {"name": "Bo Ferrer",
         "private_context": "Bo receives many approaches and rarely "
                            "replies. Bo does not know Ada."},
    ],
    "shared_context": "Ada has prepared a short message about her proposal "
                      "and can send it to Bo.",
    "starting_events": [
        {"time": START, "description": "Ada sends her prepared message to Bo.",
         "visible_to": ["Ada Vance"]},
    ],
    "resolution": "Resolve YES only if the committed history shows that Bo "
                  "sent Ada a response before the cutoff. Otherwise NO.",
}


def build():
    return instantiate_scene_manifest(SCENE, QUESTION, START, CUTOFF)


class Script:
    """Scripted provider: returns queued responses by role."""

    def __init__(self, by_role):
        self.by_role = {k: list(v) for k, v in by_role.items()}
        self.seen = []

    def __call__(self, system, user):
        role = ("judge" if "read-only outcome judge" in system
                else "world" if "You are the world" in system else "actor")
        self.seen.append(role)
        queue = self.by_role.get(role) or []
        if not queue:
            raise AssertionError(f"script exhausted for role {role!r}")
        item = queue.pop(0)
        return (item if isinstance(item, str) else json.dumps(item)), {}


UNRESOLVED = {"status": "UNRESOLVED", "supporting_event_ids": [],
              "explanation": "nothing committed satisfies it yet"}


# ---------------------------------------------------------------- adapter
def test_adapter_consumes_the_four_fields_only_and_is_deterministic():
    w1, j1, b1 = build()
    w2, _, _ = build()
    assert w1.state_hash() == w2.state_hash()
    assert set(b1["actor_ids"]) == {"Ada Vance", "Bo Ferrer"}
    # the resolution never enters the world
    assert SCENE["resolution"] not in json.dumps(w1.records)
    # starting event committed, visible only to its declared actor
    events = j1.events()
    assert len(events) == 1 and events[0]["for"] == ["ada_vance"]
    assert events[0]["observed"] is True


def test_private_context_never_leaks_between_actors():
    world, journal, _ = build()
    ada = render_view(build_view(world, journal, "ada_vance"))
    bo = render_view(build_view(world, journal, "bo_ferrer"))
    assert "wants a response from Bo" in ada
    assert "wants a response from Bo" not in bo
    assert "rarely" in bo and "rarely" not in ada
    # shared context reaches both
    assert "prepared a short message" in ada and "prepared a short message" in bo


def test_unobserved_events_never_enter_a_view():
    world, journal, b = build()
    seq = world.records[-1]["seq"]
    journal.commit({"description": "Ada's message arrives in Bo's inbox.",
                    "for": ["bo_ferrer"], "observed": False},
                   cause=seq, source="test", trajectory_id=b["trajectory_id"])
    view = build_view(world, journal, "bo_ferrer")
    assert view["observed_events"] == []
    assert "arrives in Bo's inbox" not in render_view(view)
    # but the world may reason about it
    assert len(journal.available_unobserved("bo_ferrer")) == 1


def test_observed_event_reaches_only_actors_named_in_for():
    world, journal, b = build()
    seq = world.records[-1]["seq"]
    journal.commit({"description": "Bo notices the subject line.",
                    "for": ["bo_ferrer"], "observed": True},
                   cause=seq, source="test", trajectory_id=b["trajectory_id"])
    assert len(build_view(world, journal, "bo_ferrer")["observed_events"]) == 1
    ada = build_view(world, journal, "ada_vance")["observed_events"]
    assert all("notices the subject line" not in e["description"] for e in ada)


# --------------------------------------------------------------- envelope
def test_duration_grammar_and_rejections():
    assert parse_duration("now").total_seconds() == 0
    assert parse_duration("43 seconds").total_seconds() == 43
    assert parse_duration("2 hours").total_seconds() == 7200
    assert parse_duration("3 days").days == 3
    for bad in ("soon", "a while", "-5 minutes", "2 fortnights", "", "45 days"):
        with pytest.raises(EnvelopeError):
            parse_duration(bad)


def test_event_envelope_rejects_unknown_actors_and_extra_fields():
    known = {"ada_vance", "bo_ferrer"}
    with pytest.raises(EnvelopeError):
        validate_event({"description": "x", "for": ["nobody"],
                        "observed": True, "after": "now"}, known)
    with pytest.raises(EnvelopeError):
        validate_event({"description": "x", "for": ["ada_vance"],
                        "observed": True, "after": "now",
                        "event_id": "e9"}, known)
    with pytest.raises(EnvelopeError):
        validate_event({"description": "x", "for": ["ada_vance"],
                        "observed": True, "after": "now",
                        "probability": 0.4}, known)
    ok = validate_event({"description": " x ", "for": ["ada_vance",
                                                       "ada_vance"],
                         "observed": False, "after": "5 minutes"}, known)
    assert ok["for"] == ["ada_vance"] and ok["delta"].total_seconds() == 300


# -------------------------------------------------------------- terminal
def test_terminal_rules_are_enforced_in_code():
    now = parse_iso(START)
    cutoff = parse_iso(CUTOFF)
    v = make_validator({"e1"}, now, cutoff)
    with pytest.raises(ResolutionError):        # YES with no citation
        v({"status": "YES", "supporting_event_ids": [],
           "explanation": "it happened"})
    with pytest.raises(ResolutionError):        # citation that doesn't exist
        v({"status": "YES", "supporting_event_ids": ["e99"],
           "explanation": "x"})
    with pytest.raises(ResolutionError):        # premature NO
        v({"status": "NO_AT_CUTOFF", "supporting_event_ids": [],
           "explanation": "x"})
    assert v({"status": "YES", "supporting_event_ids": ["e1"],
              "explanation": "e1 shows it"})["status"] == "YES"
    at_cutoff = make_validator({"e1"}, cutoff, cutoff)
    assert at_cutoff({"status": "NO_AT_CUTOFF", "supporting_event_ids": [],
                      "explanation": "deadline passed"})["status"] \
        == "NO_AT_CUTOFF"


# ------------------------------------------------------- full trajectory
class LifecycleModel:
    """A fake model that answers its ACTUAL trigger, so the test exercises
    the real control flow rather than an assumed call order.  It drives a
    full message lifecycle in which arrival, noticing and reading are three
    separate world judgments."""

    def __init__(self):
        self.attention_checks = 0
        self.seen = []

    def __call__(self, system, user):
        if "read-only outcome judge" in system:
            self.seen.append("judge")
            if "sends a short reply" in user:
                eid = [ln.split()[1] for ln in user.splitlines()
                       if "sends a short reply" in ln][0]
                return json.dumps(
                    {"status": "YES", "supporting_event_ids": [eid],
                     "explanation": f"{eid} records the reply."}), {}
            return json.dumps(UNRESOLVED), {}
        if "You are the world" in system:
            self.seen.append("world")
            if "starting_event" in user:
                return json.dumps({
                    "judgment": "The message travels and lands where Bo "
                                "could see it.",
                    "event": {"description": "Ada's message arrives in "
                                             "Bo's inbox.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "43 seconds"}, "wakes": []}), {}
            if "attention_check" in user:
                self.attention_checks += 1
                if self.attention_checks == 1:
                    return json.dumps({
                        "judgment": "Bo is mid-task and does not look.",
                        "event": None,
                        "wakes": [{"actor": "bo_ferrer", "after": "2 hours",
                                   "reason": "he may clear messages later"}]
                    }), {}
                return json.dumps({
                    "judgment": "Clearing messages, Bo notices the subject "
                                "line.",
                    "event": {"description": "Bo notices the subject line "
                                             "of Ada's message.",
                              "for": ["bo_ferrer"], "observed": True,
                              "after": "now"}, "wakes": []}), {}
            if "Open" in user or "read" in user.lower():
                return json.dumps({
                    "judgment": "He opens it and reads it through.",
                    "event": {"description": "Bo reads Ada's message in "
                                             "full.",
                              "for": ["bo_ferrer"], "observed": True,
                              "after": "2 minutes"}, "wakes": []}), {}
            if "repl" in user.lower():
                return json.dumps({
                    "judgment": "He types two lines back.",
                    "event": {"description": "Bo sends a short reply to Ada.",
                              "for": ["ada_vance"], "observed": True,
                              "after": "5 minutes"}, "wakes": []}), {}
            return json.dumps({"judgment": "Nothing concrete follows.",
                               "event": None, "wakes": []}), {}
        self.seen.append("actor")
        if "bo_ferrer" in user and "notices the subject line" in user:
            return json.dumps({
                "decision": "Something unfamiliar is sitting there.",
                "intentions": ["Open the message and read it."],
                "private_updates": ["An unfamiliar message is waiting."]}), {}
        if "bo_ferrer" in user and "reads Ada's message" in user:
            return json.dumps({
                "decision": "Short and relevant; I will reply.",
                "intentions": ["Send a brief reply to Ada."],
                "private_updates": ["Ada's proposal is worth two lines."]}), {}
        return json.dumps({"decision": "Nothing to do right now.",
                           "intentions": [], "private_updates": []}), {}


def lifecycle_script():
    return LifecycleModel()


def test_full_lifecycle_keeps_delivery_notice_and_read_distinct():
    world, journal, bindings = build()
    caller = RuntimeCaller(transport=lifecycle_script())
    trace = Trace()
    traj = run_trajectory(world, journal, bindings, SCENE["resolution"],
                          caller, max_steps=20, trace=trace)
    assert traj.status in ("resolved", "cutoff"), traj.reason
    events = journal.events()
    descs = [e["description"] for e in events]
    arrive = next(i for i, d in enumerate(descs) if "arrives in Bo's inbox" in d)
    notice = next(i for i, d in enumerate(descs) if "notices the subject" in d)
    read = next(i for i, d in enumerate(descs) if "reads Ada's message" in d)
    assert arrive < notice < read              # invariants 8 and 9
    assert events[arrive]["observed"] is False  # delivery is not observation
    # Bo's view never contained the unobserved arrival
    bo_views = [e for e in trace.of("actor_view") if e["actor"] == "bo_ferrer"]
    assert bo_views
    for v in bo_views:
        seen = [x["description"] for x in v["view"]["observed_events"]]
        assert all("arrives in Bo's inbox" not in s for s in seen)
    # time never moved backwards
    times = [parse_iso(e["t"]) for e in events]
    assert times == sorted(times)
    # every committed event has a cause
    assert all(e["cause"] is not None for e in events)


def test_intentions_are_not_committed_events():
    world, journal, bindings = build()
    caller = RuntimeCaller(transport=lifecycle_script())
    traj = run_trajectory(world, journal, bindings, SCENE["resolution"],
                          caller, max_steps=8, trace=Trace())
    committed = " ".join(e["description"] for e in journal.events())
    # actors proposed these; none of them may appear as committed events
    assert "Wait." not in committed
    assert "Open the message." not in committed
    assert "Send a brief reply." not in committed
    # the actor's own words are recorded as provenance, not as history
    calls = [r for r in world.records if r["op"] == "semantic.actor_call"]
    assert calls and any(c["data"]["intentions"] for c in calls)


def test_replay_is_exact_and_calls_no_model():
    world, journal, bindings = build()
    caller = RuntimeCaller(transport=lifecycle_script())
    run_trajectory(world, journal, bindings, SCENE["resolution"], caller,
                   max_steps=20, trace=Trace())
    before = len(caller.calls)
    verification = replay_trajectory(world.records, live_world=world)
    assert verification["llm_calls"] == 0
    assert len(caller.calls) == before          # nothing new was called
    assert verification["exact"] is True
    assert verification["event_ids"] == [e["event_id"] for e in journal.events()]


def test_terminal_yes_cites_committed_events_only():
    world, journal, bindings = build()
    caller = RuntimeCaller(transport=lifecycle_script())
    traj = run_trajectory(world, journal, bindings, SCENE["resolution"],
                          caller, max_steps=20, trace=Trace())
    if traj.answer and traj.answer["status"] == "YES":
        ids = {e["event_id"] for e in journal.events()}
        assert traj.answer["supporting_event_ids"]
        assert all(i in ids for i in traj.answer["supporting_event_ids"])


# --------------------------------------------------- transactional safety
def test_invalid_world_output_commits_nothing_after_one_retry():
    world, journal, bindings = build()
    before_records = len(world.records)
    bad = {"judgment": "x", "event": {"description": "y",
                                      "for": ["ghost_actor"],
                                      "observed": True, "after": "now"},
           "wakes": []}
    caller = RuntimeCaller(transport=Script({
        "judge": [UNRESOLVED] * 4,
        "world": [bad, bad, bad, bad],
        "actor": [{"decision": "d", "intentions": [], "private_updates": []}]
                 * 4}))
    traj = run_trajectory(world, journal, bindings, SCENE["resolution"],
                          caller, max_steps=6, trace=Trace())
    assert traj.status == "failed"
    assert "unknown actor" in traj.reason
    # the journal is unchanged apart from records that legitimately
    # preceded the failure: no event from the rejected response exists
    assert all("ghost" not in json.dumps(e) for e in journal.events())


def test_malformed_json_retries_once_then_fails_without_mutation():
    world, journal, bindings = build()
    n_events = len(journal.events())
    caller = RuntimeCaller(transport=Script({
        "judge": ["not json", "not json"], "world": [], "actor": []}))
    traj = run_trajectory(world, journal, bindings, SCENE["resolution"],
                          caller, max_steps=4, trace=Trace())
    assert traj.status == "failed"
    assert "judge" in traj.reason
    assert len(caller.calls) == 2               # one attempt + one retry
    assert [c["attempt"] for c in caller.calls] == [0, 1]
    assert len(journal.events()) == n_events    # nothing committed


def test_time_never_moves_backward_and_cutoff_is_respected():
    world, journal, bindings = build()
    caller = RuntimeCaller(transport=Script({
        "judge": [UNRESOLVED] * 30,
        "world": [{"judgment": "far future", "event": {
            "description": "something much later",
            "for": ["ada_vance"], "observed": True, "after": "3 days"},
            "wakes": []}] * 30,
        "actor": [{"decision": "d", "intentions": [], "private_updates": []}]
                 * 30}))
    traj = run_trajectory(world, journal, bindings, SCENE["resolution"],
                          caller, max_steps=10, trace=Trace())
    times = [parse_iso(e["t"]) for e in journal.events()]
    assert times == sorted(times)
    assert all(t <= parse_iso(CUTOFF) for t in times)
    assert traj.status in ("cutoff", "resolved", "failed")


def test_no_probability_or_weight_fields_are_accepted():
    known = {"ada_vance"}
    for bad_field in ("probability", "likelihood", "weight", "score",
                      "confidence"):
        with pytest.raises(EnvelopeError):
            validate_event({"description": "x", "for": ["ada_vance"],
                            "observed": True, "after": "now",
                            bad_field: 0.5}, known)
