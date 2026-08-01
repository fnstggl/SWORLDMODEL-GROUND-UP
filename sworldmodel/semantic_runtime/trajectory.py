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
from .envelope import (EnvelopeError, contained, parse_duration,
                       validate_event)
from .journal import (Journal, OP_ACTOR_CALL, OP_ATTEMPT, OP_CONTINUITY,
                      OP_HORIZON, OP_TERMINAL, OP_VERIFY, OP_WORLD_CALL)
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

#: How much unlived time has to lie ahead before code asks the world what
#: happened in it.  "Meanwhile, elsewhere" is not a question you can ask
#: about the next ninety seconds; an hour is the smallest stretch over
#: which a situation can move on its own.  Code owns only the threshold --
#: that the question is owed at all -- never the answer.
UNLIVED_TIME_WORTH_ASKING_ABOUT = timedelta(hours=1)

#: kernel queue kinds owned by this layer
K_EVENT = "semantic.event"      # a world-proposed event, due at its instant
K_WAKE = "semantic.wake"        # reconsider an actor's situation

#: A wake exists only for a reason that something in the world gives it.
#: There is no polling: an earlier version widened an interval from five
#: minutes to a day and back, which produced 3:50 a.m. reconsiderations,
#: five wakes in five hours, day-long holes in the middle of a task, and
#: people who quietly stopped being asked anything at all.  Time passing is
#: not a reason to think about something again.  These three are:
#:
#: DEFINED ONCE, at module scope, because this exact vocabulary has now
#: drifted five separate times -- names declared here and wired to nothing,
#: and a copy in the acceptance checker listing three values the runtime
#: cannot emit while missing one it does.  A vocabulary with two homes has
#: no home.
WAKE_PROVENANCE = ("actor_plan",         # they said they would
                   "world_process",      # the world said it would happen
                   "own_act_finished")   # what they were doing is done


def budget_for(*, max_steps: int, actors: int,
               starting_events: int = 0) -> int:
    """A call ceiling that provably sits above the ordinary path.

    A backstop that can fire on a normal run is a step ceiling in disguise
    and turns an honest ``cutoff`` into noise, so it is derived from the
    runtime's own structural caps rather than picked.  One step costs at
    most one environmental consequence, one call per actor who becomes
    aware, one world adjudication per intention each of them may take, and
    one terminal check; every call may additionally be retried once.

    An actor turn and a world event each carry a read-only review, and a
    rejected one is asked again, so a turn costs up to four calls rather
    than one and an adjudication up to four rather than two.  A candidate
    answer costs a second, independent reading.
    """
    per_turn = 2 * (2 + 2 * actor_mind.MAX_INTENTIONS_PER_TURN)
    per_step = 2 + actors * per_turn + 2
    per_start = 2 + actors * per_turn
    attempts = MAX_RETRIES_PER_CALL + 1
    return (attempts * (max_steps * per_step + starting_events * per_start + 2)
            + RESERVED_FINAL_CALLS)


@dataclass
class SemanticTrajectory:
    #: running    -- still going
    #: resolved   -- committed events satisfy the resolution
    #: cutoff     -- the trajectory reached the horizon and did not
    #: incomplete_empty_queue -- nothing was scheduled and the horizon was
    #:               never reached, so most of the window was never lived
    #: incomplete_step_limit  -- ran out of steps first
    #: incomplete_call_limit  -- ran out of calls first
    #: (all three: the horizon was never reached, so no NO may be claimed)
    #: disagreement -- two independent readings of the record disagreed at
    #:               the horizon, so no answer is claimed
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
    review_calls: int = 0

    def to_dict(self) -> dict:
        return {"status": self.status, "answer": self.answer,
                "reason": self.reason, "steps": self.steps,
                "world_calls": self.world_calls,
                "actor_calls": self.actor_calls,
                "judge_calls": self.judge_calls,
                "review_calls": self.review_calls}


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

    #: how many things each person has LEARNED -- events delivered to them
    #: that were not their own doing -- and how many they had learned when
    #: they were last consulted.
    news: dict = {}
    news_at_turn: dict = {}
    last_turn_t: dict = {}

    #: What was last asked about somebody's unopened items: the instant it
    #: was asked at, how much had happened by then, and which items.
    #:
    #: Asking the same question twice AT THE SAME INSTANT buys the same
    #: answer twice.  Asking it again LATER does not: whether attention has
    #: reached something is a question whose only real input is how long it
    #: has been sitting there, so an hour later is a different question
    #: with a legitimately different answer.  An earlier version of this
    #: compared only the record and the items, which made a message that
    #: was once passed over unnoticeable forever after -- a cold email that
    #: nobody could ever open, and a housemate thread nobody could ever
    #: come back to.
    last_progression: dict = {}

    #: (actor, event) pairs whose arrival has already been put to the
    #: world once.  An arrival is a single cause and is answered once; what
    #: happens to the item after that is the business of whatever wake the
    #: world's own answer scheduled.
    arrivals_asked: dict = {}

    #: Whether everyone has been asked once more with the queue empty and
    #: the horizon still ahead.  Once, not repeatedly: a second sweep with
    #: nothing changed in between would be the same question again, and
    #: the point is to make sure people were asked, not to keep asking.
    #: The instant of the last sweep, not a latch.  Latching it to the
    #: first empty queue spent the whole guarantee at whatever moment that
    #: happened to be -- typically minutes into a window of days, before
    #: anybody had anything to react to -- and an empty queue at hour one
    #: and at hour three hundred were then treated alike.
    #:
    #: A different moment is a different question, and that needs no
    #: threshold to say: if the sweep produced nothing the clock has not
    #: moved and the run ends, and if it produced something the clock
    #: moved to reach it.
    last_call: dict = {"at": None}

    #: The instant at which the world was last asked what becomes of the
    #: time ahead of it.  Once per instant: a second asking at the same
    #: moment is the same question.
    asked_about_the_gap: dict = {"at": None}

    #: Whether the loop stopped because the future it could see lay beyond
    #: the deadline -- the horizon honestly reached -- rather than because
    #: there was no future at all.
    reached_horizon: dict = {"yes": False}

    #: When each person is next free.  An action occupies the person doing
    #: it, and this is the whole of that idea.
    #:
    #: Without it an event was a point: sixty-five per cent of a corpus
    #: happened at the same instant as its cause, a woman signed a lease
    #: two minutes into a thirty-minute call, and a support call arrived as
    #: thirty-three events inside three minutes.  Duration was decorative,
    #: so it was not answered.  Made load-bearing, it is answered, and
    #: everything downstream of "people can only do one thing at a time"
    #: follows without a prompt asking for it.
    busy_until: dict = {}

    #: Somebody's own stated next move lies past the deadline.  Two
    #: reviewers independently found that the beyond-cutoff signal was
    #: computed and thrown away, which left NO_AT_CUTOFF reachable only
    #: when the last scheduled instant happened to divide the window
    #: exactly -- a wake every two days over a fortnight answered NO, and
    #: every three days answered incomplete, with identical world
    #: behaviour.  The horizon is a fact about the state, not about
    #: arithmetic.
    intends_after_cutoff: dict = {"yes": False}

    #: one pending wake per (actor, what it is about, what it is for).  A
    #: newer wake for the same purpose replaces the older one rather than
    #: stacking behind it.
    pending_wakes: dict = {}

    def _schedule_wake(actor_id: str, *, after, reason: str, provenance: str,
                       about: str, cause: int,
                       keep_latest: bool = False) -> bool:
        """Code owns the instant, the cause and the identity.  The reason
        is natural language from whoever asked for it, and is recorded for
        tracing only -- it never reaches the person, because a wake is
        scheduling, not information."""
        if provenance not in WAKE_PROVENANCE:
            raise EnvelopeError(
                f"a wake needs grounded provenance, one of "
                f"{list(WAKE_PROVENANCE)}; got {provenance!r}")
        delta = after if isinstance(after, timedelta) else parse_duration(after)
        due = world.clock.now + delta
        if due > cutoff or due <= world.clock.now:
            # A "later" that falls past the deadline is not nothing: it is
            # somebody saying their next move is after the question closes,
            # which is precisely the evidence that nothing more happens
            # inside the window.  It used to be dropped silently, and the
            # run then reported that nothing had been scheduled.
            if due > cutoff:
                note("wake_beyond_cutoff", actor=actor_id, t=_iso_now(world),
                     due=iso(due), reason=reason, provenance=provenance)
                intends_after_cutoff["yes"] = True
            return False
        # ONE pending revisit per person per kind of reason -- not per
        # person per reason per whatever prompted the asking.  Keying on
        # the trigger as well meant the same world callback about the same
        # man, asked for under two different triggers, sat in the queue
        # twice at the same instant; and a person's "I'll look again later"
        # minted a fresh key every turn, so plans stacked.  Somebody has
        # one next moment they come back to something, and every turn they
        # take is a chance to say when that is.
        key = (actor_id, provenance)
        old = pending_wakes.get(key)
        if old is not None:
            # For most purposes the sooner wake is the one worth keeping.
            # For "you have finished what you were doing" it is the later
            # one: somebody who starts a second thing is not free when the
            # first ends, and keeping the earlier wake would ask them
            # mid-task and then never ask them again.
            already_right = (old["due"] >= due if keep_latest
                             else old["due"] <= due)
            if already_right:
                return False
            world.cancel_event(old["seq"],
                               "replaced by a better-timed wake for the "
                               "same purpose", cause)
        ev = world.schedule(K_WAKE,
                            {"actor": actor_id, "reason": reason,
                             "provenance": provenance, "about": about},
                            due, cause)
        pending_wakes[key] = {"due": due, "seq": ev.seq}
        note("wake_scheduled", actor=actor_id, t=_iso_now(world),
             due=iso(due), provenance=provenance, about=about, reason=reason)
        return True

    # ---------------------------------------------------------------
    def world_step(*, trigger_kind: str, trigger_text: str, cause: int,
                   actor_id: str | None = None, concerns=(),
                   self_act_of=None, attempt_id: str | None = None,
                   not_before=None) -> dict | None:
        """One immediate-consequence adjudication.  Commits at most one
        event (scheduled at its own instant) and any wakes.  Returns the
        parsed judgment, or None if the world declined to act."""
        # an event produced by adjudicating someone's own attempt is that
        # person's own doing, and so is whatever follows from it: the
        # queue carries that fact so the commit rule can tell it apart
        # from something happening TO them
        # ... and, separately, whether THIS event is the direct product of
        # that attempt.  The two are not the same thing and conflating them
        # leaked: "your own action is not news to you" is inherited down
        # the chain, but "you know you did this" must not be, or the sender
        # of a message ends up recorded as having observed its arrival at
        # the other end -- including whether the other person noticed it,
        # which is the one thing they cannot know.  A negotiator was told,
        # as authoritative observed fact, that her offer had reached the
        # other party's phone and he had not looked at it.
        did_it = actor_id if trigger_kind == "actor_intention" else None
        # Whose turn this adjudication belongs to, for the identity guard.
        # The guard used to be gated on did_it, so it ran on attempts only
        # -- and 37% of committed events came in through starting_event and
        # pending_progression, where the world could write a named person's
        # decision as history before that person had ever been consulted.
        adjudicating_for = actor_id
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
        # what is already SCHEDULED for this instant counts as much as what
        # has already landed on it.  Counting only the journal let a chain
        # queue several events at one timestamp before any of them
        # committed, and each one measured an instant that still looked
        # empty -- so the cap was read three times as not yet reached and
        # six things happened in the same minute.
        here = _iso_now(world)
        crowded = (sum(1 for e in journal.events() if e["t"] == here)
                   + sum(1 for e in world.queue.pending()
                         if e.kind == K_EVENT
                         and e.t == world.clock.now)) \
            >= MAX_EVENTS_PER_INSTANT
        # "Already happened" has to include what is already ON ITS WAY to
        # happening, for the same reason the crowd count does: an event is
        # scheduled first and committed when its instant arrives, so two
        # calls made before either lands both saw a journal without the
        # other's event in it.  One run committed "Marcus notices the
        # message in his inbox" twice, a minute apart, having checked
        # against a record that did not yet contain either of them.
        already = frozenset(
            [(e.get("by"), tuple(e["for"]), contained(e["description"]))
             for e in journal.events()]
            + [(e.data["envelope"].get("by"),
                tuple(e.data["envelope"]["for"]),
                contained(e.data["envelope"]["description"]))
               for e in world.queue.pending() if e.kind == K_EVENT])
        validator = world_mind.make_world_validator(
            set(actor_ids), already_committed=already)
        # ONE call.  No semantic gate, no correction loop.
        #
        # There used to be a read-only reviewer here that judged whether a
        # proposed event "is a real thing that happened", with one
        # correction and then destruction.  It held two rules no act done
        # through a device could satisfy at once -- atomic got "the machine
        # is the one acting", combined got "several stages at once" -- so
        # the decisive act of a scenario was deleted, the person was then
        # refused by the OTHER reviewer for repeating it, the queue
        # emptied, and the absence of the act that had just been destroyed
        # became the final answer.  In one run it PASSed and REVISEd the
        # byte-identical string four calls apart.  The same lease scene on
        # byte-identical evidence answered YES three times and NO three
        # times, and the flip was the reviewer, not the world.
        #
        # Everything it was legitimately catching -- schema, actor ids,
        # duplicates, impossible durations, unknown fields -- is decidable
        # and is decided in make_world_validator, in code, the same way
        # every time.  What is left over is realism judgment, and that
        # belongs offline where it can be wrong without deleting anybody's
        # afternoon.
        out = caller.ask("world", world_mind.WORLD_SYSTEM, user, validator,
                         sim_time=_iso_now(world), trigger=trigger_kind)
        traj.world_calls += 1
        since_actor["n"] += 1
        parsed = out["parsed"]
        envelope = parsed["event_checked"]

        # A restatement that nothing changed is not an event.
        #
        # This used to say "the attention question may only be answered
        # with attention", and it deleted 58 world answers across eleven
        # runs -- among them "Marcus Bell replies to Dana Whitfield that
        # the hall is confirmed for the 14th", which is the decisive act of
        # that scenario, and "Ethel calls the vendor's support line".  I
        # removed a model's power to delete a valid action and handed a
        # slightly narrower version of it to code, which a reviewer caught
        # and which is the same mistake.
        #
        # What is genuinely not an event is the item's own state narrated
        # again: nobody did it (`by` is null) and nobody's notice reached
        # anything.  If a PERSON did something, it happened, whatever
        # question prompted the answer.
        if envelope is not None and trigger_kind == "pending_progression" \
                and actor_id and envelope.get("by") is None \
                and not (envelope["observed"] and actor_id in envelope["for"]):
            note("restatement_refused", t=_iso_now(world),
                 call_id=out["call_id"], actor=actor_id,
                 rejected=envelope["description"])
            parsed = dict(parsed, event_checked=None, event=None)
            envelope = None

        # The one boundary code still enforces on the world's answer, and
        # it is enforced by IDENTITY rather than by opinion: an attempt
        # belongs to exactly one person, and a consequence in which
        # somebody ELSE makes a voluntary choice is that person's turn to
        # take, not this one's to record.
        if envelope is not None and (adjudicating_for is not None
                                     or trigger_kind == "elapsed_world"):
            # Only where there IS somebody whose turn this is.  A starting
            # event has no adjudicating actor -- it is the scene's own
            # premise unfolding -- so there is no attempt for `by` to
            # contradict, and routing every authored event there deleted
            # the premise itself.  That leaves starting events unguarded;
            # they are 9 of 195 committed events in the corpus and they
            # come from the frozen compiler, and the report says so rather
            # than claiming otherwise.
            #
            # On the world's OWN turn there is no adjudicating actor by
            # construction, and that is exactly when the guard matters
            # most: "meanwhile, what happened?" is an invitation to write
            # somebody's decision as weather.  Nobody here did it is the
            # definition of that turn, so any named doer hands it back.
            by = envelope.get("by")
            chooser = (by if by and by != adjudicating_for else None)
            if chooser is not None:
                note("choice_returned_to_its_owner", t=_iso_now(world),
                     call_id=out["call_id"], actor=chooser,
                     rejected=envelope["description"])
                world.apply(OP_WORLD_CALL,
                            {"call_id": out["call_id"],
                             "trigger": trigger_kind,
                             "judgment": parsed["judgment"],
                             "handed_to": chooser,
                             "trajectory_id": tid}, cause)
                actor_step(chooser, cause=cause)
                return None
        wakes = parsed["wakes_checked"]
        if parsed.get("duplicate_dropped"):
            note("duplicate_event_dropped", call_id=out["call_id"],
                 t=_iso_now(world), description=parsed["duplicate_dropped"])
        # commit atomically
        wseq = world.apply(OP_WORLD_CALL,
                           {"call_id": out["call_id"], "trigger": trigger_kind,
                            "judgment": parsed["judgment"],
                            "trajectory_id": tid}, cause)
        note("world_judgment", call_id=out["call_id"], t=_iso_now(world),
             trigger=trigger_kind, trigger_text=trigger_text,
             judgment=parsed["judgment"],
             event=parsed["event"], wakes=parsed["wakes"])
        landed_at = None
        if envelope is not None:
            delta = parse_duration(envelope["after"])
            if crowded and not delta.total_seconds():
                # this instant is already full; the next thing takes at
                # least a moment, whatever the world says
                delta = MIN_STEP_ON_A_CROWDED_INSTANT
                note("duration_floored", call_id=out["call_id"],
                     t=_iso_now(world), description=envelope["description"])
            due = world.clock.now + delta
            # ... and not before the person doing it is free.  This is the
            # whole of "one thing at a time": a second act cannot start in
            # the middle of the first.
            doer = envelope.get("by")
            if doer and busy_until.get(doer) and busy_until[doer] > due:
                note("waited_until_free", call_id=out["call_id"],
                     t=_iso_now(world), actor=doer,
                     free_at=iso(busy_until[doer]),
                     description=envelope["description"])
                due = busy_until[doer]
            # A person doing two things does the first one first.  Within
            # one turn each attempt lands no earlier than the one before
            # it: the intentions were dispatched in order, but the events
            # they produced fired from a time-ordered queue, so a shorter
            # second attempt overtook a longer first.  A woman transferred
            # 400 pounds thirty seconds BEFORE the check she had made it
            # conditional on -- and that check then said the money had not
            # arrived.  Ordering is code's, and this is what it is for.
            if not_before is not None and due < not_before:
                due = not_before
                note("ordered_after_earlier_attempt", call_id=out["call_id"],
                     t=_iso_now(world), due=iso(due),
                     description=envelope["description"])
            if due <= cutoff:
                world.schedule(K_EVENT,
                               {"envelope": dict(envelope),
                                # the already-available items this step was
                                # asked about: if the answer turns out to
                                # be that attention reached them, they stop
                                # being pending at THAT instant, not now
                                "concerns": list(concerns),
                                "self_act_of": self_act_of,
                                "did_it": did_it,
                                "attempt_id": attempt_id,
                                "source": f"world_call:{out['call_id']}"},
                               due, wseq)
                landed_at = due
                if doer:
                    # durations stay as their original text through the
                    # JSON-safe envelope; code re-parses at the moment it
                    # needs them, the same way `after` is handled
                    ends = due + parse_duration(
                        envelope.get("lasts") or "0 seconds")
                    busy_until[doer] = ends
                    # ... and finishing something is a moment in a person's
                    # life.  A twenty-minute call ends, and the person who
                    # made it is back.  Without this the occupancy model
                    # could only ever stop somebody -- they went quiet
                    # mid-task and nothing ever brought them back, which is
                    # the shape of "abandoned mid-sentence" the corpus is
                    # full of.  The wake is grounded in a concrete fact, not
                    # in an interval code invented.
                    if ends > world.clock.now:
                        _schedule_wake(
                            doer, after=ends - world.clock.now,
                            reason="what you were doing has finished",
                            provenance="own_act_finished", about="free",
                            cause=wseq, keep_latest=True)
            else:
                note("event_beyond_cutoff", call_id=out["call_id"],
                     due=iso(due), description=envelope["description"])
        for w in wakes:
            # the world asking to be called back is a real process it has
            # said will happen.  The reason is recorded and shown to no
            # one: a wake is scheduling, never information.
            _schedule_wake(w["actor"], after=w["after"], reason=w["reason"],
                           provenance="world_process",
                           about=trigger_kind, cause=wseq)
        parsed = dict(parsed, landed_at=landed_at)
        return parsed

    def actor_step(actor_id: str, *, cause: int, trigger_event_ids=(),
                   force: bool = False) -> None:
        """Consult one actor, check that the reply follows from what they
        have, store their private updates, ground any plan they made, and
        send each intention to the world as its own separate trigger.

        Only event IDS are passed in: the view code looks them up in this
        actor's own observed records, so nothing can reach a person through
        the fact that they were consulted.

        Nobody is consulted twice at the same instant having learned
        nothing in between -- that is not a second thought, it is the same
        thought asked twice.
        """
        # ``force`` is the last call, and only the last call.  The guard
        # below is right that asking somebody twice at one instant having
        # learned nothing is the same thought asked twice -- but "the
        # world is about to go quiet with the deadline still ahead" is not
        # the same question as the one they just answered, and it lands at
        # the same instant as their last turn almost by definition, so the
        # guard suppressed it exactly where it was needed.
        if not force and last_turn_t.get(actor_id) == _iso_now(world) \
                and news_at_turn.get(actor_id) == news.get(actor_id, 0):
            return
        last_turn_t[actor_id] = _iso_now(world)
        view = build_view(world, journal, actor_id,
                          trigger_event_ids=trigger_event_ids,
                          busy_until=busy_until.get(actor_id))
        rendered = render_view(view)
        held = [m["content"] for m in view["private_memories"]]
        base = actor_mind.actor_user_prompt(rendered)
        user, parsed, out = base, None, None
        first = None            # what they said before any correction
        for attempt in range(2):
            out = caller.ask("actor", actor_mind.ACTOR_SYSTEM, user,
                             lambda o: actor_mind.validate_actor_response(
                                 o, held_memories=held),
                             sim_time=_iso_now(world),
                             trigger=f"actor:{actor_id}")
            traj.actor_calls += 1
            parsed = out["parsed"]
            if first is None:
                first, first_out = parsed, out
            verdict = _continuity_review(actor_id, rendered, parsed,
                                         cause=cause)
            if verdict["verdict"] == "PASS":
                break
            # A REFUSED TURN IS STILL A TURN.
            #
            # This used to abandon the turn on a second failure, and the
            # abandonment was the second half of the chain that produced
            # the shipped runtime's worst answers: the event reviewer
            # deleted a woman's attempt to sign and return a lease, she
            # attempted it again, and this reviewer refused her for
            # repeating -- so she did nothing for two days and the
            # absence became the answer.  It also invented calendar facts
            # and fed them back into the person's next prompt.
            #
            # It gets ONE correction, and if the correction does not
            # satisfy it the ORIGINAL reply stands.  A read-only check
            # that cannot be satisfied must not be able to silence
            # somebody; the record notes that it objected, and the person
            # still gets to have said what they said.
            note("actor_response_rejected", actor=actor_id,
                 t=_iso_now(world), call_id=out["call_id"], attempt=attempt,
                 reason=verdict["reason"], rejected=parsed)
            if attempt:
                world.apply(OP_CONTINUITY,
                            {"call_id": out["call_id"], "actor": actor_id,
                             "verdict": "OVERRULED",
                             "reason": verdict["reason"],
                             "trajectory_id": tid}, cause)
                # ... and it is the FIRST reply that stands, not the
                # corrected one.  Breaking here with the retry in hand kept
                # the more distorted of the two: a reply rewritten under an
                # instruction naming a contradiction, which the reviewer
                # then refused anyway.  A reviewer that cannot be satisfied
                # must not get to choose the version either.
                parsed, out = first, first_out
                break
            user = (base + f"\n\nYOUR PREVIOUS REPLY DID NOT FOLLOW FROM WHAT "
                           f"YOU HAVE\n{contained(verdict['reason'])}\n"
                           f"Reply again, as this person, fixing exactly "
                           f"that.  Change nothing else.")
        since_actor["n"] = 0
        news_at_turn[actor_id] = news.get(actor_id, 0)
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
             private_updates=parsed["private_updates"],
             next_wake=parsed["next_wake"])
        for upd in parsed["private_updates"]:
            world.apply("actor.memory",
                        {"actor": actor_id, "kind": "private",
                         "content": upd,
                         "source": f"actor_call:{out['call_id']}"}, aseq)
        if parsed["next_wake"]:
            # They said they would come back to something.  That, and the
            # world saying a process will happen, are the only kinds of
            # "later" this runtime has.
            _schedule_wake(actor_id, after=parsed["next_wake"]["after"],
                           reason=parsed["next_wake"]["reason"],
                           provenance="actor_plan",
                           about=f"plan:{out['call_id']}", cause=aseq)
        # Each intention becomes a CODE-OWNED OBJECT before it reaches the
        # world, and the consequence the world returns is stamped with its
        # id.  Previously the world received prose and returned prose, and
        # nothing bound a committed consequence to the attempt it came
        # from -- so a YES could rest on a chain whose decisive step was
        # never taken by anybody.  No batching of futures: one attempt,
        # one adjudication.
        # ... in the order the person stated them.  A later attempt lands
        # no earlier than the one before it, because a person doing two
        # things does the first one first -- and because the second is
        # often conditional on the first.
        floor = None
        for n, intent in enumerate(parsed["intentions"]):
            attempt_id = f"a{out['call_id']}.{n}"
            aid_seq = world.apply(OP_ATTEMPT, {
                "attempt_id": attempt_id, "actor": actor_id,
                "description": contained(intent),
                "trajectory_id": tid}, aseq)
            result = world_step(
                trigger_kind="actor_intention",
                trigger_text=f"{actor_id} attempts: {intent}",
                cause=aid_seq, actor_id=actor_id,
                attempt_id=attempt_id, not_before=floor)
            if result and result.get("landed_at") is not None:
                floor = result["landed_at"]

    def _continuity_review(actor_id: str, rendered: str, parsed: dict,
                           *, cause: int) -> dict:
        """Read-only: does this reply follow from what this person has?

        It is not a second actor.  It proposes nothing and chooses
        nothing, and it sees only what this person was given and what this
        person replied -- never the resolution, never anyone else's
        private state, never a future event.
        """
        out = caller.ask("continuity", actor_mind.CONTINUITY_SYSTEM,
                         actor_mind.continuity_user_prompt(rendered, parsed),
                         actor_mind.validate_continuity,
                         sim_time=_iso_now(world),
                         trigger=f"continuity:{actor_id}")
        traj.review_calls += 1
        world.apply(OP_CONTINUITY,
                    {"call_id": out["call_id"], "actor": actor_id,
                     "verdict": out["parsed"]["verdict"],
                     "reason": out["parsed"]["reason"],
                     "trajectory_id": tid}, cause)
        note("continuity_review", actor=actor_id, t=_iso_now(world),
             call_id=out["call_id"], **out["parsed"])
        return out["parsed"]

    #: The world may not run this many steps in a row without a single
    #: person being consulted.  The rule that people decide what people do
    #: is a prompt instruction, and a prompt instruction is not a
    #: guarantee: one live run committed thirty-three consecutive events
    #: of one man typing, none of them his own model's doing, and the
    #: budget was gone before anyone was asked anything.  Whatever the
    #: world writes, the turn comes back to people at a bounded rate.
    MAX_WORLD_RUN = 6
    since_actor = {"n": 0}

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
        for aid in actors:
            if _has_learned_something(aid):
                actor_step(aid, cause=rec["seq"])
            # someone who has learned nothing gets nothing: they are in
            # the middle of their own business, and coming back to it is
            # for them to plan, not for the clock to force

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
        learned = bool(envelope["observed"] and others)
        if learned:
            # somebody LEARNED something: their turn
            for aid in others:
                news[aid] = news.get(aid, 0) + 1
                actor_step(aid, cause=rec["seq"],
                           trigger_event_ids=[rec["event_id"]])
        # ... and, independently of that, the world may have said this
        # event leaves something unresolved.  Both can be true at once: a
        # message that reaches one person can still be on its way to
        # another, and treating them as alternatives left things stopped
        # where they were sent.
        # whoever this concerns, INCLUDING the person whose doing it was:
        # someone who sends a thing to someone else is still waiting on it
        waiting = list(dict.fromkeys(
            list(envelope["for"]) + ([self_act_of] if self_act_of else [])))
        if since_actor["n"] >= MAX_WORLD_RUN and waiting and not learned:
            # the world has been going by itself for too long: whatever it
            # has been writing, the people in it get to speak
            _hand_back_the_turn(waiting, rec)
            return
        # Something has ARRIVED for people who have not seen it.  That
        # arrival is itself a cause, and the world owes an answer for it:
        # what becomes of this, for this person?
        #
        # Without this rule, the only way an unopened item ever got
        # attention was a wake -- and a wake only existed if the person had
        # already acted and planned one.  Anybody who had not yet spoken
        # was therefore inert for the whole run: a message landed in a
        # group chat of four, and the three who had not already been
        # talking were never asked anything again.  One live run committed
        # four events over four days for that reason, and every wake in it
        # belonged to the one person who had spoken first.
        #
        # Code decides only THAT the question is owed, and to whom.  When
        # it is answered, and what the answer is, stays with the world:
        # any interval code picked here would be a number of its own
        # invention deciding when people notice things.
        unseen = [a for a in envelope["for"]
                  if a != self_act_of and not envelope["observed"]]
        for aid in unseen:
            if arrivals_asked.get((aid, rec["event_id"])):
                continue
            arrivals_asked[(aid, rec["event_id"])] = True
            if since_actor["n"] >= MAX_WORLD_RUN:
                break
            world_step(
                trigger_kind="pending_progression",
                trigger_text=(f"This has just arrived for {aid}, who has "
                              f"not seen it.  What concretely becomes of "
                              f"it for them?"),
                cause=rec["seq"], actor_id=aid,
                concerns=[rec["event_id"]])

        # THE TRANSPORT CHAIN IS GONE.
        #
        # "follow_up" meant "this event leaves something in transit", and
        # the consequence chain it drove is where the arrivals, the
        # notifications, the buzzing phones and the still-unread messages
        # came from -- 44% of the merged corpus was that chain talking to
        # itself.  Delivery is not a story; it is the state of an item, and
        # the item already carries it: who it reached is ``for``, whether
        # they have seen it is ``observed_by``.  Nothing needs to narrate
        # that, so nothing is asked to.
        #
        # What survives is the part that was always real: when the thing
        # that just happened was somebody's OWN doing, the next decision is
        # theirs and it is due now.  A man who checks a booking system
        # checks it IN ORDER TO answer the question he was asked, and a
        # live run left him at exactly that point on Monday morning and
        # jumped to Friday's deadline.
        #
        # ... unless what they are doing is still going on.  Somebody
        # twenty seconds into a thirty-minute call is not deciding what to
        # do next; they are on the call.  Asking anyway is how one actor
        # collected fifty-five consecutive turns and a hundred and eighty-
        # five model calls to commit two events.  They are brought back the
        # moment it ends, by the wake scheduled where the occupancy was set
        # -- so this costs nobody their turn, it only moves it to when they
        # are actually free to take it.
        if self_act_of:
            if busy_until.get(self_act_of, world.clock.now) > world.clock.now:
                note("still_mid_task", actor=self_act_of, t=_iso_now(world),
                     free_at=iso(busy_until[self_act_of]))
                return
            actor_step(self_act_of, cause=rec["seq"])
        return

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
            final=final, truncated=not final)
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
        if parsed["status"] == "UNRESOLVED":
            return parsed            # nothing is being claimed yet
        # A candidate answer is checked by an independent second reading of
        # the same record, which is never told what the first one said.  A
        # YES used to end a run the instant one judge flipped, so no YES
        # was ever tested against anything.
        second = _verify(cause=cause, final=final)
        agreed = (second["status"] == parsed["status"])
        note("terminal_verification", t=_iso_now(world), agreed=agreed,
             first=parsed["status"], second=second["status"],
             explanation=second["explanation"])
        if agreed:
            return parsed
        # they disagree, so nothing is claimed: the run carries on if there
        # is anything left to happen, and says so plainly if there is not
        return {"status": "UNRESOLVED",
                "supporting_event_ids": [],
                "explanation": (f"two independent readings of the record "
                                f"disagree ({parsed['status']} against "
                                f"{second['status']}), so no answer is "
                                f"claimed"),
                "disagreement": True}

    def _verify(*, cause: int, final: bool = False) -> dict:
        events = journal.events()
        out = caller.ask("verifier", resolution_mod.VERIFIER_SYSTEM,
                         resolution_mod.verifier_user_prompt(
                             resolution, _iso_now(world),
                             [{"event_id": e["event_id"], "t": e["t"],
                               "description": e["description"],
                               "for": e["for"],
                               "observed_by": e["observed_by"]}
                              for e in events], final=final),
                         resolution_mod.make_verifier_validator(
                             {e["event_id"] for e in events},
                             world.clock.now, cutoff, final=final),
                         sim_time=_iso_now(world), trigger="terminal_verify",
                         reserved=True)
        traj.review_calls += 1
        world.apply(OP_VERIFY, {"call_id": out["call_id"],
                                "status": out["parsed"]["status"],
                                "supporting_event_ids":
                                    out["parsed"]["supporting_event_ids"],
                                "explanation": out["parsed"]["explanation"],
                                "trajectory_id": tid}, cause)
        return out["parsed"]

    def finish(reason: str, *, incomplete: str = "") -> SemanticTrajectory:
        """The one way a run ends without failing.

        A run that actually reached the cutoff is judged AT the cutoff, and
        that judgment is YES or NO.  A run that stopped early is a
        different thing entirely: the trajectory never reached the horizon,
        so nothing is known about what would have happened in the time that
        was not simulated.  Such a run is reported as incomplete and may
        still return YES on what it did commit -- but it may never return
        NO, because that would turn a budget artifact into an answer.

        ``incomplete`` names WHY, and an empty queue is one of the reasons.
        It did not used to be.  Every NO in the shipped corpus -- eleven of
        eleven -- was produced by the queue running dry and the clock then
        being advanced across a window nobody had lived: a cold email
        jumped its whole fortnight in a single record after one step.  An
        empty queue with days left is not evidence that nothing happens.
        It is evidence that nothing was scheduled, which is a fact about
        the scheduler.
        """
        truncated = bool(incomplete)
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
        if answer.get("disagreement"):
            # two independent readings of the same record reached different
            # conclusions at the horizon.  That is not an answer, and it is
            # not a NO either: it is the run saying so.
            traj.status = "disagreement"
        elif answer["status"] == "YES":
            traj.status = "resolved"
        else:
            traj.status = incomplete if truncated else "cutoff"
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
            if ev is None or ev.t > cutoff:
                # Two situations the merged runtime treated alike, and
                # they are not alike.
                #
                # The queue is EMPTY: nothing will ever happen again, so
                # the rest of the window is not going to be simulated by
                # anybody.  Eleven of eleven NO answers in the shipped
                # corpus stopped this way and were reported as deadlines
                # that had passed -- a cold email jumped its whole
                # fortnight in one record after a single step.  That is
                # incomplete, and it is settled below rather than here.
                #
                # The next thing is BEYOND THE CUTOFF: the world has said
                # what the future holds and none of it lands before the
                # deadline.  Nothing more happens in the window because
                # nothing more was going to, which is the horizon honestly
                # reached, and NO is available.
                #
                # Before either, everyone still in the situation is asked
                # once more.  Code decides only THAT they are asked; when
                # they come back is theirs to say, in their own next_wake.
                if world.clock.now < cutoff \
                        and last_call["at"] != world.clock.now:
                    last_call["at"] = world.clock.now
                    # caused by the last thing that actually happened, so
                    # the chain stays walkable back to the start
                    here = world.records[-1]["seq"] if world.records else 0
                    for aid in actor_ids:
                        actor_step(aid, cause=here, force=True)
                    continue
                # THE HORIZON, DEFINED BY THE STATE.
                #
                # Nothing lands before the deadline, everyone still in the
                # situation has been asked at this instant, and nobody
                # intends anything before it.  That is the window lived
                # out: what remains is time in which nothing was going to
                # happen, which is a real thing that happens.
                #
                # Not "did the clock land on the cutoff second".  That is
                # what it used to be, and it made the honest NO a matter of
                # whether the wake interval divided the window.
                # A KNOWN future beyond the deadline is not an empty
                # queue: somebody has said what happens next and it happens
                # after the question closes, so nothing more lands inside
                # the window and NO is available.
                #
                # A queue that is simply empty stays INCOMPLETE, per the
                # rule.  Two reviewers argued that is too strict -- three
                # runs that lived 92-99% of their windows and had every
                # actor decline were refused a NO -- and that disagreement
                # is recorded in the report rather than resolved here.
                reached_horizon["yes"] = (ev is not None
                                          or intends_after_cutoff["yes"])
                break
            # THE WORLD'S OWN TURN.
            #
            # About to cross a stretch of time in which nobody here does
            # anything.  Until now the adjudicator had exactly three
            # occasions, all reactive -- a starting event, somebody's
            # attempt, something sitting in somebody's inbox -- so nothing
            # could ever happen that a person in the cast had not chosen.
            # Across 209 committed events in the shipped corpus there were
            # zero events from outside it: no office shut, no deadline bit
            # on its own, nobody chased what they were owed, and the one
            # thing that ever went wrong was that somebody had not got
            # round to it.  The prompt has always told the world that
            # outside parties act; the machinery never gave it an occasion
            # to say so.
            #
            # Code decides only THAT the question is owed, and only for
            # time long enough for the question to mean anything.  What
            # happened in it is the world's.  Once per instant: if the
            # answer puts something inside the gap, the loop comes back
            # round and lives it.
            if ev.t - world.clock.now >= UNLIVED_TIME_WORTH_ASKING_ABOUT \
                    and asked_about_the_gap["at"] != world.clock.now:
                asked_about_the_gap["at"] = world.clock.now
                world_step(
                    trigger_kind="elapsed_world",
                    trigger_text=(
                        f"Nobody here does anything between now and "
                        f"{iso(ev.t)}.  What concretely happens in that time "
                        f"that none of these people brought about?"),
                    cause=world.records[-1]["seq"])
                continue
            ev = world.queue.pop()
            if ev.t > world.clock.now:
                world.clock.advance_to(ev.t)
            fired = world.apply("event.fired",
                                {"event": ev.seq, "kind": ev.kind,
                                 "t": iso(ev.t), "data": ev.data}, ev.seq)
            traj.steps += 1

            if ev.kind == K_EVENT:
                envelope = validate_event(ev.data["envelope"], set(actor_ids))
                # One person noticing is not everyone noticing.  A world
                # that declares a group has all seen something -- "they
                # are all checking their phones at this moment", said over
                # a night-shift worker and a man who is away -- has
                # decided the one thing it may not.  Attention is
                # per-person, so the group keeps it as available and each
                # of them is judged separately; the one whose own doing it
                # is, of course, knows.
                doer = ev.data.get("self_act_of")
                if envelope["observed"] and len(envelope["for"]) > 1:
                    note("group_observation_split", t=_iso_now(world),
                         description=envelope["description"],
                         had=list(envelope["for"]), kept=doer)
                    envelope = dict(envelope, observed=False)
                rec = journal.commit(envelope, cause=fired,
                                     source=ev.data.get("source", "scheduled"),
                                     trajectory_id=tid,
                                     attempt_id=ev.data.get("attempt_id"))
                note("committed_event", **rec)
                # A person knows what they themselves just did, whoever it
                # was addressed to.  Requiring them to be among the people
                # it reached left a man's own text message recorded as
                # something nobody was aware of, himself included: he was
                # not one of its recipients, he was its author.  The judge
                # read a confirmation that no one had observed and answered
                # that he never confirmed.
                #
                # ``did_it``, not ``self_act_of``: only what came directly
                # out of their own attempt.  What FOLLOWS from it happens
                # at the far end and is not theirs to see -- inheriting the
                # grant down the chain told a woman that her offer had
                # reached the other man's phone and that he had not looked
                # at it, which is exactly what she could not know.
                did = ev.data.get("did_it")
                if did and not envelope["observed"]:
                    if journal.mark_observed(rec["event_id"], did,
                                             cause=rec["seq"],
                                             source="own_doing",
                                             by_own_doing=True):
                        rec = dict(rec, observed=did in envelope["for"])
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
                # this wake has arrived, so it is no longer pending and a
                # later one for the same purpose may be scheduled
                pending_wakes.pop((aid, ev.data.get("provenance")), None)
                pending = journal.available_unobserved(aid)
                asked = last_progression.get(aid)
                here = (_iso_now(world), len(journal.events()),
                        tuple(e["event_id"] for e in pending))
                # same instant, same record, same items: the identical
                # question.  A later instant is not the same question --
                # time is exactly what makes attention arrive.
                unchanged = pending and asked == here
                if pending and since_actor["n"] >= MAX_WORLD_RUN:
                    _hand_back_the_turn([aid], {"seq": fired})
                elif unchanged:
                    note("progression_skipped", actor=aid, t=_iso_now(world),
                         items=[e["event_id"] for e in pending])
                    actor_step(aid, cause=fired)
                elif pending:
                    last_progression[aid] = here
                    world_step(
                        trigger_kind="pending_progression",
                        trigger_text=(f"The items listed above are available "
                                      f"to {aid} but not yet observed by "
                                      f"them.  What concretely becomes of "
                                      f"them next?"),
                        cause=fired, actor_id=aid,
                        concerns=[e["event_id"] for e in pending])
                    # ... and the person themselves gets their look.  A
                    # wake spent entirely on what is sitting in someone's
                    # inbox leaves the person out of their own life: they
                    # may have something else entirely to do about this.
                    actor_step(aid, cause=fired)
                elif ev.data.get("provenance") == "world_process":
                    # The world said this would happen and asked to be
                    # brought back for it.  Provenance was being read only
                    # to clear the pending key and never to decide
                    # anything, so a world process that reached nobody's
                    # inbox came back to the PERSON instead of to the
                    # world -- and the person had nothing to look at.
                    #
                    # A cold email travelled towards a man who was not in
                    # its audience, so nothing was ever pending for him;
                    # the wake fired five minutes later, the world was
                    # never asked whether the email had arrived, and he
                    # was shown "you have not observed anything yet".  One
                    # committed event, and a NO over a fortnight.
                    world_step(
                        trigger_kind="pending_progression",
                        trigger_text=(
                            f"Earlier you judged that something was still "
                            f"going on here, and asked to be brought back "
                            f"to it now: {contained(ev.data.get('reason') or '')}  "
                            f"What concretely has become of it?"),
                        cause=fired, actor_id=aid)
                    actor_step(aid, cause=fired)
                else:
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
                          incomplete="incomplete_step_limit")
        if caller.budget_exhausted():
            return finish(f"call ceiling {caller.max_calls} reached at "
                          f"{_iso_now(world)}, before the cutoff",
                          incomplete="incomplete_call_limit")
        if world.clock.now < cutoff and not reached_horizon["yes"]:
            # THE RULE.  The queue emptied and the horizon never arrived,
            # so the rest of the window was never simulated and nothing
            # may be claimed about it.  Not a sweep, not a mitigation: a
            # status.  (A run whose next scheduled thing falls beyond the
            # cutoff is the other case and keeps its NO -- there, the
            # world said what the future held and none of it landed
            # before the deadline.)
            return finish(f"nothing further was scheduled at "
                          f"{_iso_now(world)}, and the cutoff "
                          f"{iso(cutoff)} was never reached",
                          incomplete="incomplete_empty_queue")
        return finish("")
    except CallBudgetExceeded as e:
        # the backstop is a horizon, not a failure: calls are held in
        # reserve precisely so a run that spends its budget mid-step still
        # gets an honest judgment of the trajectory it actually produced.
        # It is a TRUNCATION, so it is judged where it stopped and may not
        # answer NO over time it never simulated.
        try:
            return finish(f"call ceiling reached mid-step at "
                          f"{_iso_now(world)}: {e}",
                          incomplete="incomplete_call_limit")
        except (EnvelopeError, RuntimeTechnicalFailure, CallBudgetExceeded,
                ValueError) as e2:
            traj.status = "failed"
            traj.reason = f"{type(e2).__name__} after budget horizon: {e2}"
            return traj
    except (EnvelopeError, RuntimeTechnicalFailure, ValueError) as e:
        traj.status = "failed"
        traj.reason = f"{type(e).__name__}: {e}"
        return traj
