"""Single-trajectory orchestration over the existing kernel.

One concrete trajectory.  No branching, no sampling, no probabilities, no
particles, no aggregation.

    frozen scene -> actors instantiated -> starting events committed
    -> world adjudicates each immediate consequence, one step at a time
    -> code schedules the result on the existing queue and advances the
       existing clock to the next event
    -> code commits the event, then builds strictly local views
    -> observing actors decide what they ATTEMPT
    -> each intention goes to the world separately as its own trigger
    -> the read-only judge reads only committed events
    -> until YES, NO at cutoff, or a structured unresolved result

Everything about time, ordering, identity, immutability, causality and
replay is the kernel's; this module only sequences the semantic calls and
enforces the transactional rule that a failed or invalid response commits
nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sworldmodel.simclock import iso, parse_iso

from . import actor_mind, resolution as resolution_mod, world_mind
from .envelope import EnvelopeError, validate_event, validate_wakes
from .journal import Journal, OP_ACTOR_CALL, OP_TERMINAL, OP_WORLD_CALL
from .llm import CallBudgetExceeded, RuntimeCaller, RuntimeTechnicalFailure
from .views import build_view, render_view

#: kernel queue kinds owned by this layer
K_EVENT = "semantic.event"      # a world-proposed event, due at its instant
K_WAKE = "semantic.wake"        # reconsider an actor's situation


@dataclass
class SemanticTrajectory:
    status: str = "running"     # running | resolved | cutoff | failed
    answer: dict | None = None
    reason: str = ""
    steps: int = 0
    world_calls: int = 0
    actor_calls: int = 0
    judge_calls: int = 0
    records: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"status": self.status, "answer": self.answer,
                "reason": self.reason, "steps": self.steps,
                "world_calls": self.world_calls,
                "actor_calls": self.actor_calls,
                "judge_calls": self.judge_calls}


def _iso_now(world) -> str:
    return iso(world.clock.now)


def run_trajectory(world, journal: Journal, bindings: dict, resolution: str,
                   caller: RuntimeCaller, *, max_steps: int = 60,
                   trace=None) -> SemanticTrajectory:
    """Drive one concrete trajectory to a terminal status."""
    traj = SemanticTrajectory()
    tid = bindings["trajectory_id"]
    cutoff = parse_iso(bindings["cutoff"])
    actor_ids = sorted(world.actors)
    profiles = journal.profiles()

    def note(kind, **data):
        if trace is not None:
            trace.record(kind, **data)

    #: per-actor revisit interval, widened each time a revisit finds that
    #: nothing has changed (pure time bookkeeping; the world still decides
    #: what, if anything, happens)
    backoff: dict = {}

    def _schedule_recheck(actor_id: str, cause: int) -> None:
        hours = backoff.get(actor_id, 1) * 2
        backoff[actor_id] = min(hours, 24)
        due = world.clock.now + timedelta(hours=backoff[actor_id])
        if due <= cutoff:
            world.schedule(K_WAKE,
                           {"actor": actor_id,
                            "reason": "time has passed and something is "
                                      "still sitting unattended"},
                           due, cause)

    # ---------------------------------------------------------------
    def world_step(*, trigger_kind: str, trigger_text: str, cause: int,
                   actor_id: str | None = None) -> dict | None:
        """One immediate-consequence adjudication.  Commits at most one
        event (scheduled at its own instant) and any wakes.  Returns the
        parsed judgment, or None if the world declined to act."""
        user = world_mind.world_user_prompt(
            now=_iso_now(world), shared_context=journal.shared_context(),
            journal_text=journal.render_for_world(), actor_ids=actor_ids,
            trigger_kind=trigger_kind, trigger_text=trigger_text,
            actor_id=actor_id,
            actor_private=profiles.get(actor_id) if actor_id else None,
            available_unobserved=(journal.available_unobserved(actor_id)
                                  if actor_id else None))
        out = caller.ask("world", world_mind.WORLD_SYSTEM, user,
                         world_mind.validate_world_response,
                         sim_time=_iso_now(world), trigger=trigger_kind)
        traj.world_calls += 1
        parsed = out["parsed"]
        # validate EVERYTHING before touching the ledger
        envelope = None
        if parsed["event"] is not None:
            envelope = validate_event(parsed["event"], set(actor_ids))
            due = world.clock.now + envelope["delta"]
            if due < world.clock.now:
                raise EnvelopeError("proposed event moves time backwards")
        wakes = validate_wakes(parsed["wakes"], set(actor_ids))
        # ... then commit atomically
        wseq = world.apply(OP_WORLD_CALL,
                           {"call_id": out["call_id"], "trigger": trigger_kind,
                            "judgment": parsed["judgment"],
                            "trajectory_id": tid}, cause)
        note("world_judgment", call_id=out["call_id"], t=_iso_now(world),
             trigger=trigger_kind, trigger_text=trigger_text,
             judgment=parsed["judgment"],
             event=parsed["event"], wakes=parsed["wakes"])
        if envelope is not None:
            due = world.clock.now + envelope["delta"]
            if due <= cutoff:
                world.schedule(K_EVENT,
                               {"envelope": {k: envelope[k] for k in
                                             ("description", "for",
                                              "observed", "after")},
                                "source": f"world_call:{out['call_id']}"},
                               due, wseq)
            else:
                note("event_beyond_cutoff", call_id=out["call_id"],
                     due=iso(due), description=envelope["description"])
        for w in wakes:
            due = world.clock.now + w["delta"]
            if due <= cutoff:
                world.schedule(K_WAKE, {"actor": w["actor"],
                                        "reason": w["reason"]}, due, wseq)
        return parsed

    # ---------------------------------------------------------------
    def actor_step(actor_id: str, *, cause: int, reasons: list) -> None:
        """Consult one actor, store their private updates, and send each
        intention to the world as its own separate trigger."""
        view = build_view(world, journal, actor_id, reasons=reasons)
        rendered = render_view(view)
        out = caller.ask("actor", actor_mind.ACTOR_SYSTEM,
                         actor_mind.actor_user_prompt(rendered),
                         actor_mind.validate_actor_response,
                         sim_time=_iso_now(world), trigger=f"actor:{actor_id}")
        traj.actor_calls += 1
        parsed = out["parsed"]
        aseq = world.apply(OP_ACTOR_CALL,
                           {"call_id": out["call_id"], "actor": actor_id,
                            "decision": parsed["decision"],
                            "intentions": parsed["intentions"],
                            "trajectory_id": tid}, cause)
        note("actor_view", actor=actor_id, t=_iso_now(world),
             call_id=out["call_id"], rendered=rendered, view=view)
        note("actor_decision", actor=actor_id, t=_iso_now(world),
             call_id=out["call_id"], decision=parsed["decision"],
             intentions=parsed["intentions"],
             private_updates=parsed["private_updates"])
        for upd in parsed["private_updates"]:
            world.apply("actor.memory",
                        {"actor": actor_id, "kind": "private",
                         "content": upd,
                         "source": f"actor_call:{out['call_id']}"}, aseq)
        # each intention is judged separately: no batching of futures
        for intent in parsed["intentions"]:
            world_step(trigger_kind="actor_intention",
                       trigger_text=f"{actor_id} attempts: {intent}",
                       cause=aseq, actor_id=actor_id)

    # ---------------------------------------------------------------
    def judge(*, final: bool, cause: int) -> dict:
        events = journal.events()
        validator = resolution_mod.make_validator(
            {e["event_id"] for e in events}, world.clock.now, cutoff)
        out = caller.ask("judge", resolution_mod.JUDGE_SYSTEM,
                         resolution_mod.judge_user_prompt(
                             resolution, _iso_now(world),
                             [{"event_id": e["event_id"], "t": e["t"],
                               "description": e["description"]}
                              for e in events]),
                         validator, sim_time=_iso_now(world),
                         trigger="terminal_check")
        traj.judge_calls += 1
        parsed = out["parsed"]
        world.apply(OP_TERMINAL, {"call_id": out["call_id"],
                                  "status": parsed["status"],
                                  "supporting_event_ids":
                                      parsed["supporting_event_ids"],
                                  "explanation": parsed["explanation"],
                                  "final": final, "trajectory_id": tid}, cause)
        note("terminal_check", call_id=out["call_id"], t=_iso_now(world),
             final=final, **parsed)
        return parsed

    # ---------------------------------------------------------------
    try:
        genesis_cause = next(r["seq"] for r in reversed(world.records)
                             if r["op"] == "genesis.sealed")
        # the terminal must be false at initialization
        first = judge(final=False, cause=genesis_cause)
        if first["status"] == "YES":
            traj.status = "resolved"
            traj.answer = first
            traj.reason = ("the compiled scene already satisfies its own "
                           "resolution at initialization")
            return traj

        # immediate consequences of the starting events
        for eid in bindings["starting_event_ids"]:
            e = journal.by_id(eid)
            world_step(trigger_kind="starting_event",
                       trigger_text=e["description"], cause=e["seq"])

        while traj.steps < max_steps:
            ev = world.queue.peek()
            if ev is None or ev.t > cutoff:
                break
            ev = world.queue.pop()
            if ev.t > world.clock.now:
                world.clock.advance_to(ev.t)
            fired = world.apply("event.fired",
                                {"event": ev.seq, "kind": ev.kind,
                                 "t": iso(ev.t), "data": ev.data}, ev.seq)
            traj.steps += 1

            if ev.kind == K_EVENT:
                envelope = validate_event(ev.data["envelope"], set(actor_ids))
                rec = journal.commit(envelope, cause=fired,
                                     source=ev.data.get("source", "scheduled"),
                                     trajectory_id=tid)
                note("committed_event", **rec)
                # only actors who ACTUALLY observed it are consulted
                if envelope["observed"]:
                    for aid in envelope["for"]:
                        actor_step(aid, cause=rec["seq"],
                                   reasons=[f"you observed: "
                                            f"{envelope['description']}"])
                # the causal chain continues ONE step: every committed event
                # gets exactly one immediate-consequence adjudication, so
                # something set in motion keeps moving (sent -> arrives ->
                # sits where it could be seen) instead of stopping the
                # moment nobody happens to act.  The world ends the chain by
                # returning no event.
                before = len(journal.events())
                parsed = world_step(
                    trigger_kind="event_consequence",
                    trigger_text=envelope["description"],
                    cause=rec["seq"],
                    actor_id=envelope["for"][0] if envelope["for"] else None)
                progressed = (len(journal.events()) > before
                              or world.queue.peek() is not None)
                if not envelope["observed"] and parsed is not None \
                        and not (parsed["wakes"] or progressed):
                    for aid in envelope["for"]:
                        _schedule_recheck(aid, rec["seq"])
            elif ev.kind == K_WAKE:
                aid = ev.data["actor"]
                pending = journal.available_unobserved(aid)
                if pending:
                    before = len(journal.events())
                    parsed = world_step(
                        trigger_kind="pending_progression",
                        trigger_text=(f"The items listed above are available "
                                      f"to {aid} but not yet observed by "
                                      f"them.  What concretely becomes of "
                                      f"them next?  (Context for revisiting "
                                      f"now: {ev.data['reason']})"),
                        cause=fired, actor_id=aid)
                    # a situation with something still pending is never
                    # abandoned: if the world neither moved it on nor
                    # scheduled its own revisit, code revisits it later on a
                    # widening interval.  This is time bookkeeping, not
                    # meaning -- the world still decides what happens.
                    moved = (len(journal.events()) > before
                             or world.queue.peek() is not None)
                    if parsed is not None and not (parsed["wakes"] or moved):
                        _schedule_recheck(aid, fired)
                else:
                    actor_step(aid, cause=fired,
                               reasons=[ev.data.get("reason", "reconsider")])
            else:
                continue

            checked = judge(final=False, cause=fired)
            if checked["status"] == "YES":
                traj.status = "resolved"
                traj.answer = checked
                return traj

        # horizon: advance to the cutoff and take the final judgment
        if world.clock.now < cutoff:
            world.clock.advance_to(cutoff)
        last_cause = world.records[-1]["seq"]
        final = judge(final=True, cause=last_cause)
        traj.answer = final
        traj.status = "resolved" if final["status"] == "YES" else "cutoff"
        if traj.steps >= max_steps:
            traj.reason = (f"step ceiling {max_steps} reached before the "
                           f"cutoff")
        return traj
    except (EnvelopeError, RuntimeTechnicalFailure, CallBudgetExceeded,
            ValueError) as e:
        traj.status = "failed"
        traj.reason = f"{type(e).__name__}: {e}"
        return traj
