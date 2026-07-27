"""The event-driven runtime.

    Authoritative calendar clock
            |
    priority queue of timestamped events
            |
    advance to next event -> apply elapsed-time processes
            |
    apply event consequences -> deliver resulting information
            |
    wake only materially affected actors (or defer, if busy and the
    ongoing action forbids interruption -- never drop a wake)
            |
    validate proposed intentions (stale intentions re-checked at start)
            |
    schedule starts, completions, failures, future reconsideration
            |
    evaluate terminal condition
            |
    repeat

Time jumps between meaningful events, but elapsed time is always real and
exact.  Actors are consulted only with a recorded trigger.  Nothing an actor
returns touches the world except through kernel validation.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .actions import Intention, TemplateError, check_conditions, subst
from .actors import (ACTOR_UPDATE_OPS, ActionView, ActorView, CommitmentView,
                     Decision, InfoView, VerbView)
from .events import Event, ZeroTimeLoopError
from .simclock import Duration, aware, iso, parse_iso
from .world import World, WorldIntegrityError, canonical_json

#: Threshold retarget tolerance: a genuine float-rounding epsilon at datetime
#: microsecond resolution -- NOT a behavioral constant.  Real retargets
#: (rate/quantity changes) always move the projection far more than this.
_WATCH_RETARGET_TOLERANCE = timedelta(milliseconds=1)

#: Projections further out than this are treated as unreachable rather than
#: risking datetime overflow (an implementation bound, ~100 years).
_MAX_PROJECTION_HOURS = 100 * 365 * 24


def _crossed(amount: float, level: float) -> bool:
    """Threshold comparison with a relative float tolerance."""
    return amount >= level - (1e-9 + 1e-9 * abs(level))


@dataclass(frozen=True)
class Terminal:
    """Mechanical outcome evaluation: a question, a hard cutoff instant, and
    an evaluate(world, final) function that must derive its answer from world
    state / event history and cite its producers in 'computed_from'."""
    question: str
    cutoff: datetime
    evaluate: object  # Callable[[World, bool], dict | None]


@dataclass
class Outcome:
    status: str              # "resolved" | "cutoff" | "paused"
    answer: dict | None
    world: World
    metrics: dict = field(default_factory=dict)


class Engine:
    def __init__(self, world: World, minds: dict, terminal: Terminal) -> None:
        self.world = world
        self.minds = minds
        self.terminal = terminal
        self._watch_events: dict = {}   # watch id -> (event seq, t)
        self._starting: dict = {}       # actor id -> True during one consult round
        self.metrics = {"events_processed": 0, "decisions": 0, "intentions": 0,
                        "rejections": 0, "deferred_wakes": 0, "llm_calls": 0}
        for ev in world.queue.pending():
            if ev.kind == "watch.reached":
                self._watch_events[ev.data["watch"]] = (ev.seq, ev.t)

    # ------------------------------------------------------------------
    def run(self, stop_after_events: int | None = None) -> Outcome:
        w = self.world
        cutoff = aware(self.terminal.cutoff)
        if not w.genesis_sealed:
            sealed = w.seal_genesis()
        else:
            sealed = next(r["seq"] for r in w.records if r["op"] == "genesis.sealed")
        if not any(r["op"] == "event.scheduled" and r["data"]["kind"] == "terminal.cutoff"
                   for r in w.records):
            w.schedule("terminal.cutoff", {"question": self.terminal.question},
                       cutoff, cause=sealed)

        answer = None
        status = None
        current_instant: datetime | None = None
        seen_states: dict = {}     # (material hash, kind, data) -> min depth seen
        self._premature = {}       # watch id -> premature fires this instant

        # project thresholds for watches that exist at genesis/resume --
        # a quiet world must still fire its crossings on time
        w._ctx_cause = sealed
        self._reschedule_watches()

        while True:
            ev = w.queue.peek()
            if ev is None or ev.t > cutoff:
                break
            ev = w.queue.pop()
            if ev.seq in w.processed_events:
                raise WorldIntegrityError(f"event {ev.seq} dispatched twice")

            if current_instant is None or ev.t != current_instant:
                current_instant = ev.t
                seen_states = {}
                self._premature = {}
                if ev.t > w.clock.now:
                    w.clock.advance_to(ev.t)
            # zero-time-loop refusal: the same computation (identical material
            # state + identical event kind/payload) recurring DEEPER in a
            # same-instant causal chain can never terminate.  Distinct or
            # sibling (same-depth) inert events are legitimate.
            key = (w.material_hash(), ev.kind, canonical_json(ev.data))
            prev_depth = seen_states.get(key)
            if prev_depth is not None and ev.depth > prev_depth:
                raise ZeroTimeLoopError(
                    f"identical world state re-entered by {ev.kind!r} at "
                    f"{iso(ev.t)} (depth {prev_depth} -> {ev.depth}): "
                    f"zero-time loop")
            if prev_depth is None or ev.depth < prev_depth:
                seen_states[key] = ev.depth

            w._ctx_time, w._ctx_depth = ev.t, ev.depth
            fired = w.apply("event.fired",
                            {"event": ev.seq, "kind": ev.kind, "t": iso(ev.t),
                             "data": ev.data}, cause=ev.seq)
            w._ctx_cause = fired
            w.accrue_to(ev.t)          # continuous change from elapsed time
            try:
                self._dispatch(ev)
            except Exception as e:
                # never leave a poisoned event half-applied in silence: the
                # failure is itself a ledger fact, then the world stops
                # ("wrong worlds should stop", recoverable from an earlier
                # checkpoint, fully inspectable)
                try:
                    w.apply("event.failed",
                            {"event": ev.seq, "kind": ev.kind,
                             "error": f"{type(e).__name__}: {e}"}, cause=fired)
                finally:
                    raise
            self._reschedule_watches()
            self.metrics["events_processed"] += 1

            nxt = w.queue.peek()
            settled = nxt is None or nxt.t != ev.t
            if settled and w._pending_wakes:
                self._consult()
                self._reschedule_watches()   # interrupts can retire watches
                nxt = w.queue.peek()
                settled = nxt is None or nxt.t != ev.t
            if settled and not w._pending_wakes:
                ans = self._evaluate(final=False)
                if ans is not None:
                    answer, status = ans, "resolved"
                    break
                if (stop_after_events is not None
                        and self.metrics["events_processed"] >= stop_after_events
                        and w.queue.peek() is not None):
                    status = "paused"
                    break

        if status == "paused":
            w._ctx_time = None
            w._ctx_cause = None
            return Outcome("paused", None, w, dict(self.metrics))

        terminal_cause = w._ctx_cause
        if answer is None:
            # horizon reached: the terminal.cutoff event has fired, the clock
            # sits at the cutoff, and elapsed-time processes are folded in.
            # The terminal record's producer is that cutoff event -- looked up
            # explicitly so a run resumed after the cutoff fired writes the
            # identical record an uninterrupted run writes.
            terminal_cause = next(
                (r["seq"] for r in reversed(w.records)
                 if r["op"] == "event.fired"
                 and r["data"]["kind"] == "terminal.cutoff"),
                terminal_cause) or sealed
            answer = self._evaluate(final=True)
            if answer is None:
                answer = {"answer": "unresolved",
                          "detail": "the outcome did not resolve before the cutoff",
                          "computed_from": ["terminal.cutoff"]}
            status = "cutoff"

        w.apply("terminal", {"question": self.terminal.question, "answer": answer,
                             "status": status}, cause=terminal_cause)
        w._ctx_time = None
        w._ctx_cause = None
        return Outcome(status, answer, w, dict(self.metrics))

    # ------------------------------------------------------------------
    # event dispatch (kernel mechanics only; domain kinds via adapters)
    # ------------------------------------------------------------------
    def _dispatch(self, ev: Event) -> None:
        w = self.world
        k = ev.kind
        if k == "info.deliver":
            self._deliver(ev)
        elif k == "info.notice":
            self._notice(ev.data["info"], ev.data["actor"])
        elif k == "action.start":
            self._action_start(ev)
        elif k == "action.complete":
            self._action_complete(ev)
        elif k == "wake.actor":
            self._wake_event(ev)
        elif k == "watch.reached":
            self._watch_reached(ev)
        elif k == "world.ops":
            # scheduled scenario events are DATA: sequences of universal ops
            w.run_ops(ev.data.get("ops", []))
        elif k == "terminal.cutoff":
            pass  # evaluation happens in run()
        else:
            raise WorldIntegrityError(f"unknown event kind {k!r}: the kernel "
                                      f"has no scenario-specific event paths")

    # -- information ----------------------------------------------------
    def _deliver(self, ev: Event) -> None:
        w = self.world
        iid, to, channel = ev.data["info"], ev.data["to"], ev.data["channel"]
        w.apply("info.deliver", {"id": iid, "to": to, "channel": channel})
        actor = w.actors[to]
        rule = actor.attention.get(channel)
        if rule is None:
            # No justified noticing behavior: unknown remains unknown.  The
            # information stays available-but-unnoticed; nothing is invented.
            w.apply("info.noticing_unsupported",
                    {"id": iid, "actor": to,
                     "note": f"no attention rule for channel {channel!r}; "
                             f"delivered but noticing behavior is unsupported"})
            return
        nt = rule.notice_time(ev.t)
        w.schedule("info.notice",
                   {"info": iid, "actor": to, "channel": channel,
                    "basis": rule.basis, "note": rule.note}, nt)

    def _notice(self, iid: str, aid: str) -> None:
        w = self.world
        info = w.infos[iid]
        if aid in info["noticed"]:
            # idempotent: overlapping justified mechanisms may both point at
            # the same information; noticing happens once
            w.apply("info.notice_skipped",
                    {"id": iid, "actor": aid, "reason": "already noticed"})
            return
        channel = info["sends"].get(aid, {}).get("channel", "")
        nseq = w.apply("info.notice", {"id": iid, "actor": aid})
        w.apply("actor.memory",
                {"actor": aid, "kind": "observation",
                 "content": f"Noticed message from {info['author']} on {channel}: "
                            f"{info['content']}",
                 "source": iid}, cause=nseq)
        w.wake(aid, "info_noticed",
               detail=f"message from {info['author']} on {channel}",
               ref=iid, channel=channel, cause=nseq)

    def _wake_event(self, ev: Event) -> None:
        w = self.world
        if not ev.data.get("reason"):
            raise WorldIntegrityError(
                "a wake.actor event must carry an explicit reason -- wake "
                "triggers are never defaulted")
        w.wake(ev.data["actor"], ev.data["reason"], ev.data.get("detail", ""))

    # -- actions ---------------------------------------------------------
    def _action_start(self, ev: Event) -> None:
        w = self.world
        aid = ev.data["action"]
        act = w.actions[aid]
        if act["state"] != "scheduled":
            w.apply("action.start_refused", {"id": aid, "state": act["state"],
                                             "reason": "action is not scheduled"})
            return
        actor_id = act["actor"]
        st = w.actors[actor_id]
        if st.ongoing_action is not None:
            w.apply("action.state", {"id": aid, "state": "failed",
                                     "reason": f"actor busy with {st.ongoing_action} "
                                               f"when action was due to start"})
            w.wake(actor_id, "action_failed", detail=f"{act['verb']} could not start: busy",
                   ref=aid)
            return
        defn = w.action_defs[act["verb"]]
        if w.version != act["based_on_version"]:
            # the world moved since the actor observed it: re-validate
            reason = check_conditions(w, actor_id, act.get("params", {}),
                                      defn.get("conditions", []))
            if reason is not None:
                # the full reason (which may cite world values) goes to the
                # LEDGER; the wake detail shown to the actor is value-free --
                # a failure must not leak state the actor cannot observe
                w.apply("action.state", {"id": aid, "state": "failed",
                                         "reason": f"stale intention: {reason}",
                                         "observed_version": act["based_on_version"],
                                         "current_version": w.version})
                w.wake(actor_id, "action_failed",
                       detail=f"{act['verb']} could not start: the situation "
                              f"changed and a precondition no longer holds",
                       ref=aid)
                return
        if act.get("completes_when"):
            cw = act["completes_when"]
            if "resource_at_least" not in cw:
                raise WorldIntegrityError(
                    f"unsupported completion condition {cw!r} for {aid}")
            holder, resname, level = cw["resource_at_least"]
            wid = f"w{w._seq + 1}"
            w.apply("watch.add", {"id": wid, "holder": holder, "resource": resname,
                                  "level": level,
                                  "on_reach": {"complete_action": aid},
                                  "basis": "process_derived",
                                  "note": f"completion condition of action {aid}"})
            w.apply("action.state", {"id": aid, "state": "started", "watch": wid})
        else:
            dur = Duration.from_dict(act["duration"])
            done_at = ev.t + dur.delta
            cev = w.schedule("action.complete", {"action": aid}, done_at)
            w.apply("action.state", {"id": aid, "state": "started",
                                     "completes_at": iso(done_at),
                                     "complete_event": cev.seq})
        w.apply("actor.ongoing", {"actor": actor_id, "action": aid})
        if defn.get("start_effects"):
            ctx = {"actor": actor_id, "action_id": aid,
                   "params": act.get("params", {}), "now": iso(w.clock.now)}
            w.run_ops(subst(defn["start_effects"], ctx), acting_actor=actor_id)

    def _action_complete(self, ev: Event) -> None:
        w = self.world
        aid = ev.data["action"]
        act = w.actions[aid]
        if act["state"] != "started":
            # completion effects can never apply twice / before starting
            w.apply("action.complete_refused",
                    {"id": aid, "state": act["state"],
                     "reason": "action is not in progress"})
            return
        defn = w.action_defs[act["verb"]]
        reason = check_conditions(w, act["actor"], act.get("params", {}),
                                  defn.get("complete_conditions", []))
        if reason is not None:
            w.apply("action.state", {"id": aid, "state": "failed",
                                     "reason": f"failed at completion: {reason}"})
            w.apply("actor.ongoing", {"actor": act["actor"], "action": None})
            w.wake(act["actor"], "action_failed",
                   detail=f"{act['verb']} did not complete: a completion "
                          f"condition failed", ref=aid)
            return
        w.apply("action.state", {"id": aid, "state": "completed"})
        w.apply("actor.ongoing", {"actor": act["actor"], "action": None})
        # the only place consequences land: declared effects, universal ops
        if defn.get("effects"):
            ctx = {"actor": act["actor"], "action_id": aid,
                   "params": act.get("params", {}), "now": iso(w.clock.now)}
            w.run_ops(subst(defn["effects"], ctx), acting_actor=act["actor"])
        w.wake(act["actor"], "action_completed", detail=act["verb"], ref=aid)

    # -- continuous processes / thresholds --------------------------------
    def _watch_reached(self, ev: Event) -> None:
        w = self.world
        wid = ev.data["watch"]
        wch = w.watches[wid]
        self._watch_events.pop(wid, None)
        if wch["fired"]:
            return
        amount = w.resource(wch["holder"], wch["resource"])
        if not _crossed(amount, wch["level"]):
            self._premature[wid] = self._premature.get(wid, 0) + 1
            if self._premature[wid] > 1:
                raise WorldIntegrityError(
                    f"watch {wid} fired prematurely twice at the same "
                    f"instant: threshold projection is inconsistent")
            w.apply("watch.premature", {"id": wid, "amount": amount,
                                        "level": wch["level"]})
            return  # _reschedule_watches will retarget from current rates
        w.apply("watch.fired", {"id": wid})
        reach = wch.get("on_reach", {})
        if "complete_action" in reach:
            aid = reach["complete_action"]
            if w.actions[aid]["state"] == "started":
                w.schedule("action.complete", {"action": aid, "via_watch": wid},
                           w.clock.now)
        if "wake_actor" in reach:
            w.wake(reach["wake_actor"], "world_threshold",
                   detail=f"{wch['holder']}:{wch['resource']} reached {wch['level']}",
                   ref=wid)

    def _reschedule_watches(self) -> None:
        """Keep one pending threshold event per unfired watch, derived from
        current quantities and active rates.  Rate changes retarget or cancel
        it; nothing fires early or is lost."""
        w = self.world
        for wid in sorted(w.watches):
            wch = w.watches[wid]
            if wch["fired"]:
                if wid in self._watch_events:
                    seq, _ = self._watch_events.pop(wid)
                    w.cancel_event(seq, f"watch {wid} no longer active")
                continue
            amount = w.resource(wch["holder"], wch["resource"])
            if _crossed(amount, wch["level"]):
                target = w.clock.now
            else:
                rate = w.effective_rate(wch["holder"], wch["resource"])
                ceiling = w.attainable_ceiling(wch["holder"], wch["resource"])
                if rate <= 0 or wch["level"] > ceiling + 1e-9:
                    target = None   # unreachable under current rates/capacity
                else:
                    hours = (wch["level"] - amount) / rate
                    target = (None if hours > _MAX_PROJECTION_HOURS
                              else w.clock.now + timedelta(hours=hours))
            pending = self._watch_events.get(wid)
            if pending is not None and target is not None \
                    and abs(pending[1] - target) <= _WATCH_RETARGET_TOLERANCE:
                continue
            if pending is not None and target is None:
                w.cancel_event(pending[0], f"watch {wid}: no active process moves "
                                           f"{wch['holder']}:{wch['resource']} toward "
                                           f"{wch['level']}")
                del self._watch_events[wid]
                continue
            if pending is not None:
                w.cancel_event(pending[0], f"watch {wid} retargeted to "
                                           f"{iso(target)} after rate/quantity change")
                del self._watch_events[wid]
            if target is not None:
                nev = w.schedule("watch.reached", {"watch": wid}, target)
                self._watch_events[wid] = (nev.seq, target)

    # ------------------------------------------------------------------
    # consulting actors (the ONLY path from world to mind and back)
    # ------------------------------------------------------------------
    def _matches_reconsider(self, st, reason: dict) -> bool:
        for cond in st.reconsider:
            if cond.get("on") not in ("any", reason["kind"]):
                continue
            if cond.get("channel") and cond["channel"] != reason.get("channel"):
                continue
            return True
        return False

    def _consult(self) -> None:
        w = self.world
        wakes, w._pending_wakes = w._pending_wakes, []
        order: list = []
        by: dict = {}
        for wk in wakes:                      # group per actor, keep
            if wk["actor"] not in by:         # first-trigger order
                by[wk["actor"]] = []
                order.append(wk["actor"])
            by[wk["actor"]].append(wk)
        self._starting = {}
        for aid in order:
            self._consult_actor(aid, by[aid])

    def _consult_actor(self, aid: str, triggers: list) -> None:
        w = self.world
        st = w.actors[aid]
        mind = self.minds.get(aid)
        first_cause = triggers[0]["cause"]
        reasons = [{"kind": t["kind"], "detail": t["detail"], "ref": t["ref"],
                    "channel": t["channel"]} for t in triggers]
        if mind is None:
            w.apply("actor.wake", {"actor": aid, "reasons": reasons,
                                   "routed": "no_mind",
                                   "note": "no mind bound to this actor; wake "
                                           "recorded, no decision possible"},
                    cause=first_cause)
            return
        if st.ongoing_action is not None:
            act = w.actions[st.ongoing_action]
            interruptible = bool(act.get("interruptible"))
            matched = any(self._matches_reconsider(st, r) for r in reasons)
            if not (interruptible and matched):
                denial = ("ongoing action does not permit interruption"
                          if not interruptible else
                          "no reconsideration condition matched this trigger")
                reconsider_at = act.get("completes_at") \
                    or "on action completion (condition-based)"
                for t in triggers:
                    w.apply("actor.wake_deferred",
                            {"actor": aid, "kind": t["kind"], "detail": t["detail"],
                             "ref": t["ref"], "channel": t["channel"],
                             "immediate_wake": False, "queued": True,
                             "denial_reason": denial,
                             "reconsider_at": reconsider_at},
                            cause=t["cause"])
                    self.metrics["deferred_wakes"] += 1
                return
            reasons = [dict(r, interruption_allowed=True) for r in reasons]
        # deliver previously deferred triggers together with the current ones
        deferred = [{"kind": dw["kind"],
                     "detail": f"(deferred at {dw['deferred_at']}) {dw['detail']}",
                     "ref": dw.get("ref"), "channel": dw.get("channel")}
                    for dw in st.deferred_wakes]
        all_reasons = deferred + reasons
        view = self._build_view(st, all_reasons)
        vrec = w.apply("actor.view",
                       {"actor": aid, "world_version": view.world_version,
                        "reasons": all_reasons, "rendered": view.render()},
                       cause=first_cause)
        decision = mind.decide(view)
        exchange = getattr(mind, "last_exchange", None)
        if exchange:
            w.apply("mind.exchange", dict(exchange, actor=aid), cause=vrec)
            mind.last_exchange = None
            self.metrics["llm_calls"] += 1
        self._apply_decision(st, view, decision, vrec, all_reasons)

    def _violation(self, aid: str, what: str, cause: int) -> None:
        self.world.apply("mind.violation", {"actor": aid, "reason": what}, cause=cause)

    def _apply_decision(self, st, view: ActorView, decision, cause: int,
                        reasons: list) -> None:
        w = self.world
        if not isinstance(decision, Decision):
            self._violation(st.id, f"mind returned {type(decision).__name__}, "
                                   f"not a Decision; treated as no-op", cause)
            decision = Decision(note="invalid mind output; no-op")
        dseq = w.apply("actor.decision",
                       {"actor": st.id, "reasons": reasons, "note": decision.note,
                        "intentions": [getattr(i, "verb", "?") for i in decision.intentions],
                        "based_on_version": view.world_version}, cause=cause)
        self.metrics["decisions"] += 1
        for upd in decision.updates:
            try:
                op, data = upd
            except (TypeError, ValueError):
                self._violation(st.id, f"malformed update {upd!r}", dseq)
                continue
            if op not in ACTOR_UPDATE_OPS:
                self._violation(st.id, f"forbidden op {op!r}: minds may only "
                                       f"update their own private state", dseq)
                continue
            if not isinstance(data, dict) or data.get("actor") != st.id:
                self._violation(st.id, f"attempted to modify actor "
                                       f"{data.get('actor') if isinstance(data, dict) else '?'!r} "
                                       f"via {op}", dseq)
                continue
            try:
                w.apply(op, dict(data), cause=dseq)
            except (WorldIntegrityError, ValueError, KeyError) as e:
                self._violation(st.id, f"invalid update {op}: {e}", dseq)
        if decision.interrupt_ongoing and st.ongoing_action is not None:
            act = w.actions[st.ongoing_action]
            if act.get("interruptible"):
                if act.get("complete_event"):
                    w.cancel_event(act["complete_event"],
                                   f"action {act['id']} interrupted", cause=dseq)
                if act.get("watch"):
                    w.apply("watch.fired", {"id": act["watch"],
                                            "note": "action interrupted"}, cause=dseq)
                    self._watch_pending_cancel(act["watch"], dseq)
                w.apply("action.state",
                        {"id": act["id"], "state": "interrupted",
                         "reason": decision.interrupt_reason or "actor chose to stop"},
                        cause=dseq)
                w.apply("actor.ongoing", {"actor": st.id, "action": None}, cause=dseq)
            else:
                w.apply("intention.rejected",
                        {"actor": st.id, "verb": "__interrupt__",
                         "reason": "ongoing action does not permit interruption"},
                        cause=dseq)
                self.metrics["rejections"] += 1
        for intent in decision.intentions:
            self._process_intention(st, intent, dseq, view)
        if decision.wake_me_at is not None:
            when = aware(decision.wake_me_at)
            if when <= w.clock.now:
                self._violation(st.id, f"requested wake at or before the "
                                       f"current instant ({iso(when)})", dseq)
            else:
                w.schedule("wake.actor",
                           {"actor": st.id, "reason": "self_scheduled",
                            "detail": decision.wake_me_reason or "planned reconsideration"},
                           when, cause=dseq)

    def _process_intention(self, st, intent, dseq: int, view: ActorView) -> None:
        w = self.world
        now = w.clock.now
        if not isinstance(intent, Intention):
            self._violation(st.id, f"intention must be an Intention, got "
                                   f"{type(intent).__name__}", dseq)
            return
        reject = None
        defn = w.action_defs.get(intent.verb)
        dur = None
        # an intention may state its own completion condition; otherwise the
        # definition's declared default applies (universal fallback, exactly
        # like the definition's default duration below)
        completes_when = intent.completes_when
        if completes_when is None and defn is not None \
                and defn.get("default_completes_when") is not None:
            try:
                completes_when = subst(defn["default_completes_when"],
                                       {"actor": st.id, "params": intent.params})
            except TemplateError as e:
                reject = f"default completion condition: {e}"
        if reject is not None:
            pass
        elif defn is None:
            reject = f"unknown verb {intent.verb!r}"
        elif st.ongoing_action is not None:
            reject = f"busy with ongoing action {st.ongoing_action}"
        elif self._starting.get(st.id):
            reject = "already starting another action at this instant"
        elif completes_when is not None \
                and "resource_at_least" not in completes_when:
            reject = f"unsupported completion condition {completes_when!r}"
        else:
            reject = check_conditions(w, st.id, intent.params,
                                      defn.get("conditions", []))
            if reject is None:
                dur = intent.duration or (Duration.from_dict(defn["duration"])
                                          if defn.get("duration") else None)
                if dur is None and completes_when is None:
                    reject = ("no duration or completion condition; every action "
                              "needs a provenance-labeled duration")
        if reject is not None:
            w.apply("intention.rejected",
                    {"actor": st.id, "verb": intent.verb, "reason": reject,
                     "based_on_version": view.world_version}, cause=dseq)
            self.metrics["rejections"] += 1
            return
        aid = f"a{w._seq + 1}"
        prop = w.apply("action.propose",
                       {"id": aid, "actor": st.id, "verb": intent.verb,
                        "params": intent.params,
                        "duration": dur.to_dict() if dur else None,
                        "completes_when": completes_when,
                        "interruptible": intent.interruptible,
                        "interruption_note": intent.interruption_note,
                        "note": intent.note,
                        "based_on_version": view.world_version}, cause=dseq)
        sev = w.schedule("action.start", {"action": aid}, now, cause=prop)
        w.apply("action.state", {"id": aid, "state": "scheduled",
                                 "start_event": sev.seq}, cause=prop)
        self.metrics["intentions"] += 1
        self._starting[st.id] = True

    def _watch_pending_cancel(self, wid: str, cause: int) -> None:
        pending = self._watch_events.pop(wid, None)
        if pending is not None:
            self.world.cancel_event(pending[0], f"watch {wid} cancelled", cause=cause)

    # ------------------------------------------------------------------
    def _build_view(self, st, reasons: list) -> ActorView:
        """Defensive-copy snapshot of exactly what this actor may know."""
        w = self.world
        now = w.clock.now
        infos = []
        for iid in st.unprocessed_info:
            info = w.infos[iid]
            infos.append(InfoView(
                id=iid, author=info["author"],
                channel=info["sends"].get(st.id, {}).get("channel", ""),
                content=info["content"], data=copy.deepcopy(info["data"]),
                noticed_at=parse_iso(info["noticed"][st.id])))
        completed = []
        for r in reasons:
            if r["kind"] in ("action_completed", "action_failed",
                             "action_interrupted") and r.get("ref"):
                act = w.actions.get(r["ref"])
                if act:
                    completed.append(ActionView(
                        id=act["id"], verb=act["verb"],
                        params=copy.deepcopy(act.get("params", {})),
                        started_at=parse_iso(act["started_at"]) if act.get("started_at") else None,
                        completes_at=parse_iso(act["completed_at"]) if act.get("completed_at") else None))
        ongoing = None
        if st.ongoing_action:
            act = w.actions[st.ongoing_action]
            ongoing = ActionView(
                id=act["id"], verb=act["verb"],
                params=copy.deepcopy(act.get("params", {})),
                started_at=parse_iso(act["started_at"]) if act.get("started_at") else None,
                completes_at=parse_iso(act["completes_at"]) if act.get("completes_at") else None)
        commitments = tuple(
            CommitmentView(c.id, c.what, c.at)
            for c in sorted(st.commitments.values(),
                            key=lambda c: (c.at is None, c.at or now, c.id))
            if not c.resolved)
        # only verbs whose authority conditions this actor can satisfy are
        # presented as available -- a clerk is not offered the chair's gavel
        verbs = []
        for v, d in sorted(w.action_defs.items()):
            authorized = all(st.role in c.get("roles", [])
                             for c in d.get("conditions", [])
                             if c.get("require") == "role_in")
            if authorized:
                verbs.append(VerbView(v, d.get("description", "")))
        verbs = tuple(verbs)
        return ActorView(
            actor_id=st.id, name=st.name, role=st.role, tz=st.tz, now=now,
            world_version=w.version,
            reasons=tuple(copy.deepcopy(r) for r in reasons),
            new_information=tuple(infos),
            goals=tuple(st.goals), values=tuple(st.values),
            emotional_state=st.emotional_state, physical_state=st.physical_state,
            beliefs=dict(st.beliefs), relationships=dict(st.relationships),
            memories=tuple(st.memories), plan=st.plan,
            reconsider=tuple(copy.deepcopy(st.reconsider)),
            commitments=commitments, ongoing=ongoing, completed=tuple(completed),
            time_since_last_decision=(now - st.last_decision_at
                                      if st.last_decision_at else None),
            available_verbs=verbs)

    # ------------------------------------------------------------------
    def _evaluate(self, final: bool):
        ans = self.terminal.evaluate(self.world, final)
        if ans is None:
            return None
        if not isinstance(ans, dict) or "answer" not in ans or not ans.get("computed_from"):
            raise WorldIntegrityError(
                "terminal answer must be a dict with 'answer' and a non-empty "
                "'computed_from' naming its causal producers")
        return ans
