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

from dataclasses import dataclass
from datetime import timedelta

from sworldmodel.simclock import iso, parse_iso

from . import actor_mind, resolution as resolution_mod, world_mind
from .envelope import EnvelopeError, parse_duration, validate_event
from .journal import (Journal, OP_ACTOR_CALL, OP_HORIZON, OP_TERMINAL,
                      OP_WORLD_CALL)
from .llm import (CallBudgetExceeded, MAX_RETRIES_PER_CALL, RESERVED_FINAL_CALLS,
                  RuntimeCaller, RuntimeTechnicalFailure)
from .views import build_view, render_view

#: How many events may share one exact instant before code stops
#: accepting "no time at all" for the next one.  A hundred events on a
#: single timestamp is not a sequence of events, it is one moment being
#: cut into pieces forever -- a live run did exactly that.  Time is
#: code's to keep, so code moves it on rather than refusing the answer:
#: rejecting the response instead killed whole runs over a duration.
MAX_EVENTS_PER_INSTANT = 3
MIN_STEP_ON_A_CROWDED_INSTANT = timedelta(minutes=1)

#: kernel queue kinds owned by this layer
K_EVENT = "semantic.event"      # a world-proposed event, due at its instant
K_WAKE = "semantic.wake"        # reconsider an actor's situation


def budget_for(*, max_steps: int, actors: int,
               starting_events: int = 0) -> int:
    """A call ceiling that provably sits above the ordinary path.

    A backstop that can fire on a normal run is a step ceiling in disguise
    and turns an honest ``cutoff`` into noise, so it is derived from the
    runtime's own structural caps rather than picked.  One step costs at
    most one environmental consequence, one call per actor who becomes
    aware, one world adjudication per intention each of them may take, and
    one terminal check; every call may additionally be retried once.
    """
    per_turn = 1 + actor_mind.MAX_INTENTIONS_PER_TURN
    per_step = 1 + actors * per_turn + 1
    per_start = 1 + actors * per_turn
    attempts = MAX_RETRIES_PER_CALL + 1
    return (attempts * (max_steps * per_step + starting_events * per_start + 2)
            + RESERVED_FINAL_CALLS)


@dataclass
class SemanticTrajectory:
    #: running    -- still going
    #: resolved   -- committed events satisfy the resolution
    #: cutoff     -- the trajectory reached the horizon and did not
    #: incomplete -- it ran out of steps or calls first, so the horizon was
    #:               never reached and no NO may be claimed
    #: failed     -- a technical failure.  No RESPONSE is ever partially
    #:               committed: a rejected one writes nothing at all.
    #:               Records written by calls that had already completed
    #:               within the same step do remain, because those things
    #:               really did happen before the failure.
    status: str = "running"
    answer: dict | None = None
    reason: str = ""
    steps: int = 0
    world_calls: int = 0
    actor_calls: int = 0
    judge_calls: int = 0

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

    #: one pending revisit per person.  Without this they stack: several
    #: are scheduled before the first fires, so the interval never widens
    #: and someone is revisited every couple of simulated minutes forever.
    recheck_pending: set = set()

    def _schedule_recheck(actor_id: str, cause: int) -> None:
        # ten minutes, then twenty, then forty, up to a day.  It starts
        # short because some situations move in minutes and it widens
        # because most do not; either way it walks to the horizon.
        if actor_id in recheck_pending:
            return
        minutes = backoff.get(actor_id, 5) * 2
        backoff[actor_id] = min(minutes, 24 * 60)
        due = world.clock.now + timedelta(minutes=backoff[actor_id])
        if due <= cutoff:
            recheck_pending.add(actor_id)
            world.schedule(K_WAKE,
                           {"actor": actor_id,
                            "reason": "time has passed and something is "
                                      "still sitting unattended"},
                           due, cause)

    # ---------------------------------------------------------------
    def world_step(*, trigger_kind: str, trigger_text: str, cause: int,
                   actor_id: str | None = None, concerns=(),
                   self_act_of=None) -> dict | None:
        """One immediate-consequence adjudication.  Commits at most one
        event (scheduled at its own instant) and any wakes.  Returns the
        parsed judgment, or None if the world declined to act."""
        # an event produced by adjudicating someone's own attempt is that
        # person's own doing, and so is whatever follows from it: the
        # queue carries that fact so the commit rule can tell it apart
        # from something happening TO them
        if trigger_kind == "actor_intention":
            self_act_of = actor_id
        user = world_mind.world_user_prompt(
            now=_iso_now(world), shared_context=journal.shared_context(),
            journal_text=journal.render_for_world(), actor_ids=actor_ids,
            trigger_kind=trigger_kind, trigger_text=trigger_text,
            actor_id=actor_id,
            actor_private=profiles.get(actor_id) if actor_id else None,
            available_unobserved=(journal.available_unobserved(actor_id)
                                  if actor_id else None))
        # the validator checks the response AND its event AND its wakes, so
        # an unusable one is retried once inside the call and nothing here
        # is reached until everything is known good
        crowded = sum(1 for e in journal.events()
                      if e["t"] == _iso_now(world)) >= MAX_EVENTS_PER_INSTANT
        out = caller.ask("world", world_mind.WORLD_SYSTEM, user,
                         world_mind.make_world_validator(set(actor_ids)),
                         sim_time=_iso_now(world), trigger=trigger_kind)
        traj.world_calls += 1
        since_actor["n"] += 1
        parsed = out["parsed"]
        envelope = parsed["event_checked"]
        wakes = parsed["wakes_checked"]
        # commit atomically
        wseq = world.apply(OP_WORLD_CALL,
                           {"call_id": out["call_id"], "trigger": trigger_kind,
                            "judgment": parsed["judgment"],
                            "trajectory_id": tid}, cause)
        note("world_judgment", call_id=out["call_id"], t=_iso_now(world),
             trigger=trigger_kind, trigger_text=trigger_text,
             judgment=parsed["judgment"],
             event=parsed["event"], wakes=parsed["wakes"])
        if envelope is not None:
            delta = parse_duration(envelope["after"])
            if crowded and not delta.total_seconds():
                # this instant is already full; the next thing takes at
                # least a moment, whatever the world says
                delta = MIN_STEP_ON_A_CROWDED_INSTANT
                note("duration_floored", call_id=out["call_id"],
                     t=_iso_now(world), description=envelope["description"])
            due = world.clock.now + delta
            if due <= cutoff:
                world.schedule(K_EVENT,
                               {"envelope": dict(envelope),
                                # the already-available items this step was
                                # asked about: if the answer turns out to
                                # be that attention reached them, they stop
                                # being pending at THAT instant, not now
                                "concerns": list(concerns),
                                "self_act_of": self_act_of,
                                "source": f"world_call:{out['call_id']}"},
                               due, wseq)
            else:
                note("event_beyond_cutoff", call_id=out["call_id"],
                     due=iso(due), description=envelope["description"])
        for w in wakes:
            due = world.clock.now + parse_duration(w["after"])
            if due <= cutoff:
                # the reason is recorded for tracing and shown to no one:
                # a wake is timing, never information (see validate_wakes)
                world.schedule(K_WAKE, {"actor": w["actor"],
                                        "reason": w["reason"]}, due, wseq)
        return parsed

    # ---------------------------------------------------------------
    def actor_step(actor_id: str, *, cause: int, trigger_event_ids=()) -> None:
        """Consult one actor, store their private updates, and send each
        intention to the world as its own separate trigger.

        Only event IDS are passed in: the view code looks them up in this
        actor's own observed records, so nothing can reach a person through
        the fact that they were consulted.
        """
        view = build_view(world, journal, actor_id,
                          trigger_event_ids=trigger_event_ids)
        rendered = render_view(view)
        out = caller.ask("actor", actor_mind.ACTOR_SYSTEM,
                         actor_mind.actor_user_prompt(rendered),
                         actor_mind.validate_actor_response,
                         sim_time=_iso_now(world), trigger=f"actor:{actor_id}")
        traj.actor_calls += 1
        since_actor["n"] = 0
        news_at_turn[actor_id] = news.get(actor_id, 0)
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

    #: How many times in a row the runtime asks "and then?" about
    #: something nobody has noticed.  Once: a thing that was sent arrives,
    #: and there it sits.  Asking again produced the third event of every
    #: message -- "it remains unread" -- which is not an event at all but
    #: the absence of one.  Whether it is ever noticed is a question about
    #: a later moment, and later moments are what wakes are for.
    MAX_ENV_CHAIN = 1
    env_chain = {"depth": 0}

    #: The world may not run this many steps in a row without a single
    #: person being consulted.  The rule that people decide what people do
    #: is a prompt instruction, and a prompt instruction is not a
    #: guarantee: one live run committed thirty-three consecutive events
    #: of one man typing, none of them his own model's doing, and the
    #: budget was gone before anyone was asked anything.  Whatever the
    #: world writes, the turn comes back to people at a bounded rate.
    MAX_WORLD_RUN = 6
    since_actor = {"n": 0}

    #: how many things each person has LEARNED -- events delivered to them
    #: that were not their own doing -- and how many they had learned when
    #: they were last consulted.
    news: dict = {}
    news_at_turn: dict = {}

    def _has_learned_something(actor_id: str) -> bool:
        return news.get(actor_id, 0) > news_at_turn.get(actor_id, -1)

    def _hand_back_the_turn(actors, rec) -> None:
        """The world has been running on its own for too long.

        Someone who has learned something gets their say now.  Someone in
        the middle of their own long task has not: consulting them again
        immediately is what turned one live run into a supervisor reading
        a thesis one page at a time, forty minutes of simulated time and
        the whole step budget gone.  For them, time passes instead, on the
        widening interval -- which is what being deep in something looks
        like from outside.
        """
        since_actor["n"] = 0
        env_chain["depth"] = 0
        for aid in actors:
            if _has_learned_something(aid):
                actor_step(aid, cause=rec["seq"])
            else:
                _schedule_recheck(aid, rec["seq"])

    def _after_commit(rec: dict, envelope: dict, self_act_of=None) -> None:
        """The single post-commit rule, identical for starting events and
        world-produced events: awareness hands the turn to the person;
        otherwise the environment continues, bounded.

        A person's OWN action completing is not news to them -- they did
        it -- so it does not hand them another turn.  Without this the
        actor and the world play catch: he acts, watches himself act,
        decides again, all inside the same instant, forever.  One live run
        spent its whole budget on a man debugging a line of code while the
        question it was asked went nowhere.  What happens instead is what
        happens in life: time passes, and he comes back to things.
        """
        others = [a for a in envelope["for"] if a != self_act_of]
        if envelope["observed"] and others:
            # somebody LEARNED something: their turn, and nothing further
            env_chain["depth"] = 0
            for aid in others:
                news[aid] = news.get(aid, 0) + 1
                actor_step(aid, cause=rec["seq"],
                           trigger_event_ids=[rec["event_id"]])
            return
        # nobody new learned anything.  If this was a person's own doing,
        # they get no fresh turn -- but the world must still say what
        # became of what they did, or a message they sent would simply
        # stop where it was sent.
        waiting = envelope["for"] or ([self_act_of] if self_act_of else [])
        if since_actor["n"] >= MAX_WORLD_RUN and waiting:
            # the world has been going by itself for too long: whatever it
            # has been writing, the people in it get to speak
            _hand_back_the_turn(waiting, rec)
            return
        if env_chain["depth"] >= MAX_ENV_CHAIN:
            env_chain["depth"] = 0
            for aid in waiting:
                _schedule_recheck(aid, rec["seq"])
            return
        env_chain["depth"] += 1
        before = len(journal.events())
        parsed = world_step(
            trigger_kind="event_consequence",
            trigger_text=envelope["description"], cause=rec["seq"],
            actor_id=envelope["for"][0] if envelope["for"] else None,
            concerns=[rec["event_id"]], self_act_of=self_act_of)
        progressed = (len(journal.events()) > before
                      or world.queue.peek() is not None)
        if parsed is not None and not (parsed["wakes"] or progressed):
            for aid in waiting:
                _schedule_recheck(aid, rec["seq"])

    # ---------------------------------------------------------------
    def judge(*, final: bool, cause: int, reserved: bool = False) -> dict:
        """``final`` says the cutoff has been reached, so UNRESOLVED is not
        available.  ``reserved`` says this is the judgment that closes the
        run and must be paid for out of the held-back allowance -- which is
        true of EVERY closing judgment, including the one that closes a run
        because the budget ran out.  Deriving one from the other would make
        the closing judgment of a budget-exhausted run unaffordable, and
        the truncation rule below unreachable."""
        events = journal.events()
        validator = resolution_mod.make_validator(
            {e["event_id"] for e in events}, world.clock.now, cutoff,
            final=final)
        out = caller.ask("judge", resolution_mod.JUDGE_SYSTEM,
                         resolution_mod.judge_user_prompt(
                             resolution, _iso_now(world),
                             [{"event_id": e["event_id"], "t": e["t"],
                               "description": e["description"],
                               "for": e["for"],
                               "observed_by": e["observed_by"]}
                              for e in events], final=final),
                         validator, sim_time=_iso_now(world),
                         trigger="terminal_check", reserved=reserved)
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

    def finish(reason: str, *, truncated: bool = False) -> SemanticTrajectory:
        """The one way a run ends without failing.

        A run that actually reached the cutoff is judged AT the cutoff, and
        that judgment is YES or NO.  A run that stopped early because it
        ran out of steps or calls is a different thing entirely: the
        trajectory never reached the horizon, so nothing is known about
        what would have happened in the time that was not simulated.  Such
        a run is reported as incomplete and may still return YES on what it
        did commit -- but it may never return NO, because that would turn a
        budget artifact into an answer.
        """
        if not truncated and world.clock.now < cutoff:
            world.clock.advance_to(cutoff)
            # the advance itself is recorded.  A clock moved without a
            # record is a clock the ledger cannot reproduce, and if the
            # closing judgment then fails, the run becomes unreplayable
            # through no fault of the record.
            world.apply(OP_HORIZON, {"cutoff": iso(cutoff),
                                     "trajectory_id": tid},
                        world.records[-1]["seq"])
        answer = judge(final=not truncated, cause=world.records[-1]["seq"],
                       reserved=True)
        traj.answer = answer
        if answer["status"] == "YES":
            traj.status = "resolved"
        else:
            traj.status = "incomplete" if truncated else "cutoff"
        traj.reason = reason
        return traj

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

        #: how many events had been committed when the terminal was last
        #: asked; re-asking without a new one cannot change the answer
        judged_after = {"events": len(journal.events())}

        # starting events follow the same post-commit rule as any other
        # committed event: whoever is aware of one gets their turn, and
        # anything nobody is aware of continues environmentally
        for eid in bindings["starting_event_ids"]:
            e = journal.by_id(eid)
            envelope = {"description": e["description"], "for": e["for"],
                        "observed": e["observed"]}
            world_step(trigger_kind="starting_event",
                       trigger_text=e["description"], cause=e["seq"])
            if envelope["observed"] and envelope["for"]:
                for aid in envelope["for"]:
                    actor_step(aid, cause=e["seq"], trigger_event_ids=[eid])

        while traj.steps < max_steps and not caller.budget_exhausted():
            ev = world.queue.peek()
            if ev is None and world.clock.now < cutoff:
                # nothing is scheduled, but the question is still open and
                # the people in it still have days in front of them.
                # Silence is not the end of a situation: time keeps
                # passing, on a widening interval, and each of them gets
                # to look at where things stand again.  Code decides only
                # WHEN they look; whether anything comes of it is theirs.
                for aid in actor_ids:
                    _schedule_recheck(aid, world.records[-1]["seq"])
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
                # attention reaching someone settles the items this step was
                # asked about: they are that person's business now, not a
                # pending question to be asked again
                if envelope["observed"]:
                    for eid in ev.data.get("concerns") or []:
                        for aid in envelope["for"]:
                            if journal.mark_observed(
                                    eid, aid, cause=rec["seq"],
                                    source=f"observed_via:{rec['event_id']}"):
                                note("item_observed", event_id=eid, actor=aid,
                                     t=_iso_now(world), via=rec["event_id"])
                _after_commit(rec, envelope,
                              self_act_of=ev.data.get("self_act_of"))
            elif ev.kind == K_WAKE:
                aid = ev.data["actor"]
                recheck_pending.discard(aid)
                pending = journal.available_unobserved(aid)
                if pending and since_actor["n"] >= MAX_WORLD_RUN:
                    _hand_back_the_turn([aid], {"seq": fired})
                elif pending:
                    before = len(journal.events())
                    parsed = world_step(
                        trigger_kind="pending_progression",
                        trigger_text=(f"The items listed above are available "
                                      f"to {aid} but not yet observed by "
                                      f"them.  What concretely becomes of "
                                      f"them next?  (Context for revisiting "
                                      f"now: {ev.data['reason']})"),
                        cause=fired, actor_id=aid,
                        concerns=[e["event_id"] for e in pending])
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
                    # nothing is pending for them; they are simply being
                    # consulted again because time has passed.  The world's
                    # stated reason stays in the ledger and never reaches
                    # them -- a person learns things only by observing them.
                    actor_step(aid, cause=fired)
            else:
                continue

            # only committed events can satisfy a resolution, so asking
            # again when nothing has been committed since the last answer
            # cannot change it -- it only spends the budget
            if len(journal.events()) != judged_after["events"]:
                judged_after["events"] = len(journal.events())
                checked = judge(final=False, cause=fired)
                if checked["status"] == "YES":
                    traj.status = "resolved"
                    traj.answer = checked
                    return traj

        if traj.steps >= max_steps:
            return finish(f"step ceiling {max_steps} reached at "
                          f"{_iso_now(world)}, before the cutoff",
                          truncated=True)
        if caller.budget_exhausted():
            return finish(f"call ceiling {caller.max_calls} reached at "
                          f"{_iso_now(world)}, before the cutoff",
                          truncated=True)
        return finish("")
    except CallBudgetExceeded as e:
        # the backstop is a horizon, not a failure: calls are held in
        # reserve precisely so a run that spends its budget mid-step still
        # gets an honest judgment of the trajectory it actually produced.
        # It is a TRUNCATION, so it is judged where it stopped and may not
        # answer NO over time it never simulated.
        try:
            return finish(f"call ceiling reached mid-step at "
                          f"{_iso_now(world)}: {e}", truncated=True)
        except (EnvelopeError, RuntimeTechnicalFailure, CallBudgetExceeded,
                ValueError) as e2:
            traj.status = "failed"
            traj.reason = f"{type(e2).__name__} after budget horizon: {e2}"
            return traj
    except (EnvelopeError, RuntimeTechnicalFailure, ValueError) as e:
        traj.status = "failed"
        traj.reason = f"{type(e).__name__}: {e}"
        return traj
