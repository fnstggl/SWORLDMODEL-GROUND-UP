"""Adversarial kernel invariants, exercised through tiny generic worlds built
from the same universal machinery as the demonstration worlds."""
import json
import pytest
from datetime import timedelta

from sworldmodel import (ActorState, AttentionRule, Decision, Duration, Engine,
                        Event, EventQueue, Intention, Mind, SchedulingInPastError,
                        Terminal, World, WorldIntegrityError, ZeroTimeLoopError,
                        at_local, iso)

T0 = at_local(2026, 5, 4, 9, 0, tz="UTC")

DO_WORK = {"verb": "do_work", "description": "focused work block",
           "conditions": [], "effects": []}
TAKE_ITEM = {
    "verb": "take_item", "description": "take one item from the store",
    "conditions": [{"require": "resource_at_least", "holder": "store",
                    "name": "item", "amount": 1}],
    "start_effects": [["resource.adjust", {"holder": "store", "name": "item",
                                           "delta": -1}]],
    "effects": [["resource.adjust", {"holder": "{actor}", "name": "item",
                                     "delta": 1}]],
}
BOSS_ONLY = {"verb": "issue_order", "description": "give an order (boss only)",
             "conditions": [{"require": "role_in", "roles": ["boss"]}],
             "effects": [["fact.set", {"key": "order_given", "value": True}]]}


def micro_world(defs=(DO_WORK,), actors=("a1", "a2"), reconsider=None):
    w = World(T0)
    w.apply("channel.add", {"name": "radio",
                            "latency": {"seconds": 0, "basis": "verified",
                                        "note": "test: instantaneous channel"}},
            None)
    for d in defs:
        w.apply("action.define", d, None)
    for aid in actors:
        st = ActorState(
            id=aid, name=aid, role="worker", tz="UTC",
            attention={"radio": AttentionRule(None, None, "verified",
                                              "test: continuously attentive")},
            reconsider=list(reconsider or []))
        w.apply("actor.add", st.to_dict(), None)
    w.apply("resource.set", {"holder": "store", "name": "item", "amount": 1}, None)
    return w


def terminal_at(hours=8, question="test terminal"):
    def evaluate(world, final):
        if final:
            return {"answer": "done", "computed_from": ["terminal.cutoff"]}
        return None
    return Terminal(question, T0 + timedelta(hours=hours), evaluate)


class ScriptMind(Mind):
    """Returns queued decisions in order; records every view it was shown."""
    def __init__(self, decisions):
        self.queue = list(decisions)
        self.views = []

    def decide(self, view):
        self.views.append(view)
        return self.queue.pop(0) if self.queue else Decision(note="idle")


def wake(w, actor, at, **data):
    w.schedule("wake.actor", dict({"actor": actor, "reason": "scheduled",
                                   "detail": "test wake"}, **data), at, None)


# ---------------------------------------------------------------------------
# queue & scheduling invariants
# ---------------------------------------------------------------------------

def test_event_ids_unique_and_duplicate_push_refused():
    q = EventQueue()
    ev = Event(seq=1, t=T0, kind="x", data={}, cause=None, depth=0)
    q.push(ev)
    with pytest.raises(ValueError, match="unique"):
        q.push(ev)


def test_same_time_ordering_is_deterministic():
    q = EventQueue()
    for seq, depth in ((5, 0), (3, 1), (4, 0), (9, 2)):
        q.push(Event(seq=seq, t=T0, kind="x", data={}, cause=None, depth=depth))
    order = [(e.depth, e.seq) for e in (q.pop(), q.pop(), q.pop(), q.pop())]
    assert order == [(0, 4), (0, 5), (1, 3), (2, 9)]      # (t, depth, seq)


def test_no_scheduling_in_the_past():
    w = micro_world()
    with pytest.raises(SchedulingInPastError):
        w.schedule("wake.actor", {"actor": "a1", "reason": "scheduled"},
                   T0 - timedelta(seconds=1), None)


def test_cancellation_prevents_firing():
    w = micro_world()
    ev = wake(w, "a1", T0 + timedelta(hours=1))
    ev = [e for e in w.queue.pending() if e.kind == "wake.actor"][0]
    w.cancel_event(ev.seq, "test cancel", None)
    Engine(w, {"a1": ScriptMind([])}, terminal_at()).run()
    fired = [r for r in w.records if r["op"] == "event.fired"
             and r["data"]["kind"] == "wake.actor"]
    assert fired == []


def test_event_cannot_fire_twice():
    w = micro_world()
    wake(w, "a1", T0 + timedelta(hours=1))
    Engine(w, {"a1": ScriptMind([])}, terminal_at()).run()
    fired = {r["data"]["event"] for r in w.records if r["op"] == "event.fired"}
    assert len(fired) == len([r for r in w.records if r["op"] == "event.fired"])
    with pytest.raises(WorldIntegrityError, match="twice"):
        w.apply("event.fired", {"event": max(fired), "kind": "x", "t": iso(w.clock.now),
                                "data": {}}, cause=1)


# ---------------------------------------------------------------------------
# zero-time loops
# ---------------------------------------------------------------------------

def _nested_zero_delay(depth, mutate=False):
    data = {"ops": [], "note": "innermost"}
    for i in range(depth):
        ops = [["event.schedule_in", {"kind": "world.ops", "delay_hours": 0,
                                      "basis": "verified", "note": "chain",
                                      "data": data}]]
        if mutate:
            ops.insert(0, ["fact.set", {"key": f"step{i}", "value": i}])
        data = {"ops": ops, "note": f"layer {i}"}
    return data


def test_zero_time_loop_by_repeated_identical_state():
    w = micro_world()
    w.schedule("world.ops", _nested_zero_delay(10, mutate=False),
               T0 + timedelta(hours=1), None)
    with pytest.raises(ZeroTimeLoopError, match="identical world state"):
        Engine(w, {}, terminal_at()).run()


def test_zero_time_loop_by_depth_bound():
    w = micro_world()
    w.schedule("world.ops", _nested_zero_delay(80, mutate=True),
               T0 + timedelta(hours=1), None)
    with pytest.raises(ZeroTimeLoopError, match="depth"):
        Engine(w, {}, terminal_at()).run()


# ---------------------------------------------------------------------------
# stale intentions, authority, insufficient resources
# ---------------------------------------------------------------------------

def take_intent():
    return Intention("take_item", {},
                     duration=Duration(timedelta(minutes=1), "actor_chosen",
                                       "grabbing it"))


def test_stale_intention_rejected_when_world_moved():
    w = micro_world(defs=(TAKE_ITEM,))
    wake(w, "a1", T0 + timedelta(hours=1))
    wake(w, "a2", T0 + timedelta(hours=1))
    m1, m2 = ScriptMind([Decision(intentions=[take_intent()])]), \
             ScriptMind([Decision(intentions=[take_intent()])])
    Engine(w, {"a1": m1, "a2": m2}, terminal_at()).run()
    states = sorted(a["state"] for a in w.actions.values())
    assert states == ["completed", "failed"]
    failed = next(a for a in w.actions.values() if a["state"] == "failed")
    assert failed["reason"].startswith("stale intention")
    assert failed["observed_version"] < failed["current_version"]
    assert w.resource("store", "item") == 0
    # exactly one actor holds the item; effects were applied exactly once
    assert w.resource("a1", "item") + w.resource("a2", "item") == 1


def test_unauthorized_action_rejected():
    w = micro_world(defs=(BOSS_ONLY,))
    wake(w, "a1", T0 + timedelta(hours=1))
    mind = ScriptMind([Decision(intentions=[Intention(
        "issue_order", {}, duration=Duration(timedelta(minutes=1),
                                             "actor_chosen", "test"))])])
    Engine(w, {"a1": mind}, terminal_at()).run()
    rej = [r for r in w.records if r["op"] == "intention.rejected"]
    assert len(rej) == 1 and "authority" in rej[0]["data"]["reason"]
    assert "order_given" not in w.facts


def test_insufficient_resources_rejected_at_proposal():
    w = micro_world(defs=(TAKE_ITEM,))
    w.apply("resource.set", {"holder": "store", "name": "item", "amount": 0}, None)
    wake(w, "a1", T0 + timedelta(hours=1))
    mind = ScriptMind([Decision(intentions=[take_intent()])])
    Engine(w, {"a1": mind}, terminal_at()).run()
    rej = [r for r in w.records if r["op"] == "intention.rejected"]
    assert len(rej) == 1 and "insufficient" in rej[0]["data"]["reason"]


# ---------------------------------------------------------------------------
# busy actors: preserve, defer, interrupt only by explicit policy
# ---------------------------------------------------------------------------

def _busy_world(interruptible, reconsider):
    w = micro_world(defs=(DO_WORK,), reconsider=reconsider)
    wake(w, "a1", T0 + timedelta(hours=1))
    # a message arrives 10 minutes into a1's hour-long work block
    w.schedule("world.ops",
               {"ops": [["info.send_new", {"author": "a2", "to": ["a1"],
                                           "channel": "radio",
                                           "content": "urgent: call me",
                                           "data": {}}]],
                "note": "incoming message mid-action"},
               T0 + timedelta(hours=1, minutes=10), None)
    work = Intention("do_work", {}, duration=Duration(timedelta(minutes=60),
                                                      "actor_chosen", "test"),
                     interruptible=interruptible,
                     interruption_note="test policy")
    return w, work


def test_busy_actor_wake_is_deferred_not_lost():
    w, work = _busy_world(interruptible=False, reconsider=None)
    mind = ScriptMind([Decision(intentions=[work]),
                       Decision(note="finished; catching up")])
    Engine(w, {"a1": mind}, terminal_at()).run()
    deferred = [r for r in w.records if r["op"] == "actor.wake_deferred"]
    assert len(deferred) == 1
    d = deferred[0]["data"]
    assert d["denial_reason"] == "ongoing action does not permit interruption"
    assert d["queued"] is True and d["immediate_wake"] is False
    assert d["reconsider_at"]                    # when reconsideration happens
    # at completion the actor is consulted with BOTH the completion and the
    # deferred trigger, and the noticed message is in their view
    final_view = mind.views[-1]
    kinds = {r["kind"] for r in final_view.reasons}
    assert "action_completed" in kinds and "info_noticed" in kinds
    assert any(iv.content == "urgent: call me" for iv in final_view.new_information)
    # the message was noticed (preserved), not lost
    assert w.infos and all("a1" in i["noticed"] for i in w.infos.values())


def test_interruption_only_with_explicit_policy_and_condition():
    w, work = _busy_world(interruptible=True,
                          reconsider=[{"on": "info_noticed", "channel": "radio",
                                       "note": "expects urgent calls"}])
    mind = ScriptMind([Decision(intentions=[work]),
                       Decision(interrupt_ongoing=True,
                                interrupt_reason="urgent call takes priority"),
                       Decision(note="handled")])
    Engine(w, {"a1": mind}, terminal_at()).run()
    acts = list(w.actions.values())
    assert acts[0]["state"] == "interrupted"
    assert acts[0]["reason"] == "urgent call takes priority"
    assert w.actors["a1"].ongoing_action is None
    # its pending completion event was cancelled, not fired
    cancelled = [r for r in w.records if r["op"] == "event.cancelled"]
    assert any("interrupted" in r["data"]["reason"] for r in cancelled)


def test_interruptible_without_matching_condition_still_defers():
    w, work = _busy_world(interruptible=True, reconsider=None)
    mind = ScriptMind([Decision(intentions=[work]), Decision(note="done")])
    Engine(w, {"a1": mind}, terminal_at()).run()
    deferred = [r for r in w.records if r["op"] == "actor.wake_deferred"]
    assert len(deferred) == 1
    assert "no reconsideration condition" in deferred[0]["data"]["denial_reason"]


# ---------------------------------------------------------------------------
# action lifecycle: no completion before start, no double effects
# ---------------------------------------------------------------------------

def test_completion_before_start_is_refused():
    w = micro_world(defs=(DO_WORK,))
    w.apply("action.propose",
            {"id": "aX", "actor": "a1", "verb": "do_work", "params": {},
             "duration": {"seconds": 60, "basis": "verified", "note": "t"},
             "based_on_version": w.version}, None)
    w.schedule("action.complete", {"action": "aX"}, T0 + timedelta(hours=1), None)
    Engine(w, {}, terminal_at()).run()
    assert w.actions["aX"]["state"] == "proposed"
    refused = [r for r in w.records if r["op"] == "action.complete_refused"]
    assert len(refused) == 1


def test_completion_effects_cannot_apply_twice():
    w = micro_world(defs=(TAKE_ITEM,))
    start_at = T0 + timedelta(hours=1)
    w.apply("action.propose",
            {"id": "aY", "actor": "a1", "verb": "take_item", "params": {},
             "duration": {"seconds": 60, "basis": "verified", "note": "t"},
             "based_on_version": w.version}, None)
    sev = w.schedule("action.start", {"action": "aY"}, start_at, None)
    w.apply("action.state", {"id": "aY", "state": "scheduled",
                             "start_event": sev.seq}, None)
    # an extra, illegitimate completion event at the same instant as the real one
    w.schedule("action.complete", {"action": "aY"},
               start_at + timedelta(seconds=60), None)
    Engine(w, {"a1": ScriptMind([])}, terminal_at()).run()
    assert w.actions["aY"]["state"] == "completed"
    refused = [r for r in w.records if r["op"] == "action.complete_refused"]
    assert len(refused) == 1
    # the effect (a1 gains the item) applied exactly once
    assert w.resource("a1", "item") == 1


# ---------------------------------------------------------------------------
# information lifecycle guards
# ---------------------------------------------------------------------------

def test_delivery_requires_creation_and_sending():
    w = micro_world()
    with pytest.raises(WorldIntegrityError, match="never created"):
        w.apply("info.deliver", {"id": "ghost", "to": "a1", "channel": "radio"}, None)
    w.apply("info.create", {"id": "i_x", "author": "a2", "content": "hi",
                            "data": {}}, None)
    with pytest.raises(WorldIntegrityError, match="never sent"):
        w.apply("info.deliver", {"id": "i_x", "to": "a1", "channel": "radio"}, None)
    with pytest.raises(WorldIntegrityError, match="not delivered"):
        w.apply("info.notice", {"id": "i_x", "actor": "a1"}, None)


def test_unsupported_noticing_stays_unknown():
    w = micro_world()
    # a1 gets a channel they have no attention rule for
    w.apply("channel.add", {"name": "fax",
                            "latency": {"seconds": 0, "basis": "verified",
                                        "note": "test"}}, None)
    w.schedule("world.ops",
               {"ops": [["info.send_new", {"author": "a2", "to": ["a1"],
                                           "channel": "fax", "content": "memo",
                                           "data": {}}]],
                "note": "message on an unattended channel"},
               T0 + timedelta(hours=1), None)
    mind = ScriptMind([])
    Engine(w, {"a1": mind}, terminal_at()).run()
    unsupported = [r for r in w.records if r["op"] == "info.noticing_unsupported"]
    assert len(unsupported) == 1
    info = list(w.infos.values())[0]
    assert "a1" in info["delivered"] and "a1" not in info["noticed"]
    assert mind.views == []                       # the actor was never invented awake


# ---------------------------------------------------------------------------
# mind containment: private state, aliasing, forbidden ops
# ---------------------------------------------------------------------------

def test_hostile_mind_cannot_escape_its_authority():
    w = micro_world(defs=(DO_WORK,))
    wake(w, "a1", T0 + timedelta(hours=1))
    hostile = ScriptMind([Decision(
        updates=[("actor.belief", {"actor": "a2", "topic": "hacked",
                                   "statement": "x", "basis": "x"}),
                 ("fact.set", {"key": "hacked", "value": True}),
                 ("resource.adjust", {"holder": "a1", "name": "item",
                                      "delta": 100}),
                 ("actor.belief", {"actor": "a1", "topic": "fine",
                                   "statement": "legitimate self-update",
                                   "basis": "own reasoning"})],
        intentions=[Intention("nonexistent_verb", {}),
                    Intention("do_work", {})],       # no duration -> rejected
        wake_me_at=T0 - timedelta(hours=1),          # past -> refused
        note="hostile")])
    Engine(w, {"a1": hostile}, terminal_at()).run()
    violations = [r["data"]["reason"] for r in w.records
                  if r["op"] == "mind.violation"]
    assert len(violations) == 4                      # a2-belief, fact.set, resource, past wake
    assert "hacked" not in w.actors["a2"].beliefs    # other actor untouched
    assert "hacked" not in w.facts                   # shared state untouched
    assert w.resource("a1", "item") == 0             # quantities untouched
    assert "fine" in w.actors["a1"].beliefs          # legitimate update applied
    rejections = [r["data"]["reason"] for r in w.records
                  if r["op"] == "intention.rejected"]
    assert any("unknown verb" in r for r in rejections)
    assert any("duration" in r for r in rejections)


def test_view_is_defensively_copied_and_contains_no_other_actor():
    w = micro_world(defs=(DO_WORK,))
    w.apply("actor.belief", {"actor": "a2", "topic": "secret",
                             "statement": "a2's private thought",
                             "basis": "private"}, None)
    wake(w, "a1", T0 + timedelta(hours=1))
    mind = ScriptMind([Decision(note="peek")])
    Engine(w, {"a1": mind}, terminal_at()).run()
    view = mind.views[0]
    assert view.actor_id == "a1"
    assert "secret" not in view.beliefs              # no leakage of a2's state
    assert "a2's private thought" not in view.render()
    # mutating the view must not touch the world
    view.beliefs["injected"] = "x"
    view.relationships["a2"] = "corrupted"
    assert "injected" not in w.actors["a1"].beliefs
    assert w.actors["a1"].relationships == {}


def test_every_wake_has_a_trigger_and_every_record_a_cause():
    w = micro_world(defs=(DO_WORK,))
    wake(w, "a1", T0 + timedelta(hours=1))
    Engine(w, {"a1": ScriptMind([])}, terminal_at()).run()
    sealed_at = next(r["seq"] for r in w.records if r["op"] == "genesis.sealed")
    for r in w.records:
        if r["seq"] > sealed_at:
            assert r["cause"] is not None, f"uncaused record {r}"
    for r in w.records:
        if r["op"] == "actor.decision":
            assert r["data"]["reasons"], "decision without a wake reason"
    with pytest.raises(WorldIntegrityError, match="cause"):
        w.apply("fact.set", {"key": "x", "value": 1}, None)


def test_terminal_must_cite_producers():
    w = micro_world()
    bad = Terminal("q", T0 + timedelta(hours=1),
                   lambda world, final: {"answer": 1} if final else None)
    with pytest.raises(WorldIntegrityError, match="computed_from"):
        Engine(w, {}, bad).run()


def test_unknown_event_kind_refused():
    w = micro_world()
    w.schedule("mystery.event", {}, T0 + timedelta(hours=1), None)
    with pytest.raises(WorldIntegrityError, match="no scenario-specific"):
        Engine(w, {}, terminal_at()).run()


def test_actor_snapshots_share_no_mutable_references():
    w = micro_world()
    snap1 = w.snapshot()
    w.apply("actor.belief", {"actor": "a1", "topic": "t", "statement": "s",
                             "basis": "b"}, None)
    snap2 = w.snapshot()
    assert snap1["actors"]["a1"]["beliefs"] == {}    # old snapshot unaffected
    assert "t" in snap2["actors"]["a1"]["beliefs"]
    snap2["facts"]["poison"] = True
    assert "poison" not in w.facts
