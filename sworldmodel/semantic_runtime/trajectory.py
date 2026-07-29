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
from .journal import (Journal, OP_ACTOR_CALL, OP_CONTINUITY,
                      OP_EVENT_REVIEW, OP_HORIZON, OP_TERMINAL,
                      OP_TURN_ABANDONED, OP_VERIFY,
                      OP_WORLD_CALL)
from .llm import (CallBudgetExceeded, MAX_RETRIES_PER_CALL, RESERVED_FINAL_CALLS,
                  RuntimeCaller, RuntimeTechnicalFailure)
from .views import build_view, render_view

class ActorGroundingError(ValueError):
    """An actor's reply does not follow from what that person has, and one
    targeted correction did not fix it.  Nothing is committed, and code
    does not invent a replacement decision."""


class EventGroundingError(ValueError):
    """A proposed event is not a real thing that happened, and one targeted
    correction did not fix it."""


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
    #: incomplete -- it ran out of steps or calls first, so the horizon was
    #:               never reached and no NO may be claimed
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
    abandoned_turns: int = 0

    def to_dict(self) -> dict:
        return {"status": self.status, "answer": self.answer,
                "reason": self.reason, "steps": self.steps,
                "world_calls": self.world_calls,
                "actor_calls": self.actor_calls,
                "judge_calls": self.judge_calls,
                "review_calls": self.review_calls,
                "abandoned_turns": self.abandoned_turns}


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

    #: A wake exists only for a reason that something in the world gives
    #: it.  There is no polling: the previous version widened an interval
    #: from five minutes to a day and back, which produced 3:50 a.m.
    #: reconsiderations, five wakes in five hours, day-long holes in the
    #: middle of a task, and people who quietly stopped being asked
    #: anything at all.  Time passing is not a reason to think about
    #: something again.  These five are:
    WAKE_PROVENANCE = ("actor_plan",        # they said they would
                       "observed_event",    # something reached them
                       "world_process",     # the world said it would happen
                       "known_deadline",    # a deadline they know is close
                       "action_completion")  # what they started is done

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
    last_call: dict = {"done": False}

    #: one pending wake per (actor, what it is about, what it is for).  A
    #: newer wake for the same purpose replaces the older one rather than
    #: stacking behind it.
    pending_wakes: dict = {}

    def _schedule_wake(actor_id: str, *, after, reason: str, provenance: str,
                       about: str, cause: int) -> bool:
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
            return False
        key = (actor_id, about, provenance)
        old = pending_wakes.get(key)
        if old is not None and old["due"] <= due:
            return False              # already coming, and sooner
        if old is not None:
            world.cancel_event(old["seq"],
                               "replaced by a nearer wake for the same "
                               "purpose", cause)
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
                   self_act_of=None, intention: str | None = None) -> dict | None:
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
            [contained(e["description"]).casefold()
             for e in journal.events()]
            + [contained(e.data["envelope"]["description"]).casefold()
               for e in world.queue.pending() if e.kind == K_EVENT])
        validator = world_mind.make_world_validator(
            set(actor_ids), already_committed=already)
        ask = user
        for attempt in range(2):
            out = caller.ask("world", world_mind.WORLD_SYSTEM, ask, validator,
                             sim_time=_iso_now(world), trigger=trigger_kind)
            traj.world_calls += 1
            since_actor["n"] += 1
            parsed = out["parsed"]
            envelope = parsed["event_checked"]
            if envelope is None:
                break                       # nothing to review
            verdict = _event_review(envelope, trigger_kind=trigger_kind,
                                    trigger_text=trigger_text,
                                    intention=intention, cause=cause,
                                    acting=did_it)
            if verdict["verdict"] == "PASS":
                break
            note("event_rejected", t=_iso_now(world), call_id=out["call_id"],
                 attempt=attempt, verdict=verdict["verdict"],
                 reason=verdict["reason"], rejected=envelope["description"])
            if verdict["verdict"] == "ACTOR_TURN_REQUIRED":
                # The world has written somebody's choice.  It is theirs to
                # make, so it goes back to THEM -- and "them" is the person
                # this step is about, not the person the event was heading
                # towards.  Handing it to the audience sent a rejected
                # "Marcus replies to Dana" to Dana, and a rejected "the
                # representative greets Ethel" to Ethel: in both the actual
                # decider was never asked, and the decision the review had
                # correctly protected simply did not happen.
                #
                # The old filter was inert as well.  journal.observed_by(a)
                # is everything a has ever observed, so its truthiness only
                # said "has this person ever observed anything at all",
                # never the comment's claim that they had the observation
                # that would let them choose.
                who = ([actor_id] if actor_id
                       else list(envelope["for"]))
                if who and attempt == 0:
                    world.apply(OP_WORLD_CALL,
                                {"call_id": out["call_id"],
                                 "trigger": trigger_kind,
                                 "judgment": parsed["judgment"],
                                 "handed_to": who[0],
                                 "trajectory_id": tid}, cause)
                    actor_step(who[0], cause=cause)
                    return None
            if attempt:
                # One correction was not enough.  The world does not get to
                # commit it, and the run does not die over it either: what
                # the world could not say happened, did not happen.
                note("event_abandoned", t=_iso_now(world),
                     call_id=out["call_id"], reason=verdict["reason"],
                     rejected=envelope["description"])
                parsed = dict(parsed, event_checked=None, event=None)
                envelope = None
                break
            # Rewording the same fragment is the failure mode here: a run
            # proposed "she prints it from her printer", was told the
            # machine is not the one acting, and came back with "she
            # prints it from the message".  Both were refused, the whole
            # attempt was destroyed, and a woman who meant to sign a
            # document and send it back did nothing for two days.  What
            # the reviewer wants is the thing the fragment ADDS UP TO.
            ask = (user + f"\n\nYOUR PROPOSED EVENT WAS REJECTED\n"
                          f"{contained(verdict['reason'])}\n"
                          f"Answer again for the same trigger.  Do not "
                          f"reword what you just said: if it was refused "
                          f"as machinery or as one fragment of something "
                          f"larger, give the thing it ADDS UP TO -- what "
                          f"the person was actually doing, finished, in "
                          f"one event, at the time it would really take.  "
                          f"\"event\": null is a correct answer only when "
                          f"nothing has genuinely changed.")
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
                                "did_it": did_it,
                                "source": f"world_call:{out['call_id']}"},
                               due, wseq)
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
        return parsed

    def _event_review(envelope: dict, *, trigger_kind: str,
                      trigger_text: str, intention, cause: int,
                      acting: str | None = None) -> dict:
        """Read-only: is this a real thing that happened?

        It proposes nothing and never sees the resolution.  It exists
        because instruction did not work: the world was told not to
        narrate interface mechanics, given the exact counter-example, and
        half of every committed event in six live runs was still somebody
        operating a phone.
        """
        out = caller.ask("event_review", world_mind.EVENT_REVIEW_SYSTEM,
                         world_mind.event_review_user_prompt(
                             now=_iso_now(world),
                             journal_text=journal.render_for_world(limit=12),
                             trigger_kind=trigger_kind,
                             trigger_text=trigger_text,
                             intention=intention, event=envelope,
                             acting=acting),
                         world_mind.validate_event_review,
                         sim_time=_iso_now(world),
                         trigger=f"event_review:{trigger_kind}")
        traj.review_calls += 1
        world.apply(OP_EVENT_REVIEW,
                    {"call_id": out["call_id"], "trigger": trigger_kind,
                     "verdict": out["parsed"]["verdict"],
                     "reason": out["parsed"]["reason"],
                     "description": envelope["description"],
                     "trajectory_id": tid}, cause)
        verdict = out["parsed"]
        if verdict["verdict"] == "ACTOR_TURN_REQUIRED" \
                and trigger_kind == "actor_intention":
            # This IS their choice: the trigger is the attempt their own
            # model just made.  Handing it back to them asks them to
            # decide something they have decided, and a live run stalled
            # exactly there -- a man who had said "I reply confirming the
            # appointment" was never allowed to have replied.
            verdict = {"verdict": "PASS",
                       "reason": (f"the choice is already theirs: "
                                  f"{verdict['reason']}")}
        note("event_review", t=_iso_now(world), call_id=out["call_id"],
             description=envelope["description"], trigger=trigger_kind,
             **verdict)
        return verdict

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
                          trigger_event_ids=trigger_event_ids)
        rendered = render_view(view)
        held = [m["content"] for m in view["private_memories"]]
        base = actor_mind.actor_user_prompt(rendered)
        user, parsed, out = base, None, None
        for attempt in range(2):
            out = caller.ask("actor", actor_mind.ACTOR_SYSTEM, user,
                             lambda o: actor_mind.validate_actor_response(
                                 o, held_memories=held),
                             sim_time=_iso_now(world),
                             trigger=f"actor:{actor_id}")
            traj.actor_calls += 1
            parsed = out["parsed"]
            verdict = _continuity_review(actor_id, rendered, parsed,
                                         cause=cause)
            if verdict["verdict"] == "PASS":
                break
            note("actor_response_rejected", actor=actor_id,
                 t=_iso_now(world), call_id=out["call_id"], attempt=attempt,
                 reason=verdict["reason"], rejected=parsed)
            if attempt:
                # A second failure is a structured failure -- of the TURN,
                # not of the run.  Code does not invent a replacement
                # decision and does not ask the world to invent one: this
                # person simply did not say anything usable, which is
                # recorded, and the situation carries on without them for
                # now.  Ending the trajectory here threw away
                # twenty-five committed steps over one sentence.
                world.apply(OP_TURN_ABANDONED,
                            {"call_id": out["call_id"], "actor": actor_id,
                             "reason": verdict["reason"],
                             "trajectory_id": tid}, cause)
                note("actor_turn_abandoned", actor=actor_id,
                     t=_iso_now(world), call_id=out["call_id"],
                     reason=verdict["reason"])
                traj.abandoned_turns += 1
                return
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
        # each intention is judged separately: no batching of futures
        for intent in parsed["intentions"]:
            world_step(trigger_kind="actor_intention",
                       trigger_text=f"{actor_id} attempts: {intent}",
                       cause=aseq, actor_id=actor_id, intention=intent)

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
            env_chain["depth"] = 0
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

        if not envelope.get("follow_up"):
            # the world says this event is finished in itself.  Nothing
            # further is asked of it: what happens next is somebody's
            # decision, or a later thing already scheduled, or nothing.
            env_chain["depth"] = 0
            # ... and if the thing that just finished was this person's
            # OWN doing, the decision is theirs and it is due now.  That is
            # what "action_completion" means, and like the arrival rule it
            # was in the vocabulary and wired to nothing.
            #
            # Doing something is almost never the whole of what someone
            # meant to do.  A man who checks the booking system checks it
            # IN ORDER TO answer the question he was asked; a live run left
            # him at exactly that point on Monday morning and jumped to
            # Friday's deadline, and the honest record said he never
            # replied.  He was never asked again.
            #
            # Only when the world says the event is finished.  While it
            # says something still follows -- follow_up -- the person is in
            # the middle of one long thing, and asking them after every
            # fragment of it is what turned another run into a supervisor
            # reading a thesis one page at a time.  Which of the two this
            # is, is the world's judgment, not a counter's.
            if self_act_of:
                actor_step(self_act_of, cause=rec["seq"])
            return
        if env_chain["depth"] >= MAX_ENV_CHAIN:
            env_chain["depth"] = 0
            return
        env_chain["depth"] += 1
        world_step(trigger_kind="event_consequence",
                   trigger_text=envelope["description"], cause=rec["seq"],
                   actor_id=envelope["for"][0] if envelope["for"] else None,
                   concerns=[rec["event_id"]], self_act_of=self_act_of)

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
        if answer.get("disagreement"):
            # two independent readings of the same record reached different
            # conclusions at the horizon.  That is not an answer, and it is
            # not a NO either: it is the run saying so.
            traj.status = "disagreement"
        elif answer["status"] == "YES":
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
            if ev is None or ev.t > cutoff:
                # Nothing grounded is waiting to happen.  Code does not
                # invent activity to fill the gap -- that is what the
                # widening poll did, and it produced 3:50 a.m.
                # reconsiderations of nothing.
                #
                # But an empty queue with days still on the clock is not
                # evidence that nothing happens.  It is evidence that
                # nobody was asked.  Eleven of eleven NO answers in one
                # corpus stopped this way rather than at the horizon: a
                # cold email jumped its entire fortnight in a single
                # record after one step, and a woman one step from sending
                # a signed lease stopped two and a half days early -- and
                # each was reported as though the time had been lived
                # through and nothing had come of it.
                #
                # So before the world goes quiet, everyone still in it is
                # asked once more.  Code decides only THAT they are asked;
                # whether they come back to this, and when, is theirs to
                # say, and it is said the same way it always is -- their
                # own next_wake.  If nobody schedules anything, the
                # silence is now their answer rather than the scheduler's,
                # and the horizon may honestly be claimed.
                if world.clock.now < cutoff and not last_call["done"]:
                    last_call["done"] = True
                    # caused by the last thing that actually happened, so
                    # the chain stays walkable back to the start
                    here = world.records[-1]["seq"] if world.records else 0
                    for aid in actor_ids:
                        actor_step(aid, cause=here, force=True)
                    continue
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
                                     trajectory_id=tid)
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
                pending_wakes.pop((aid, ev.data.get("about"),
                                   ev.data.get("provenance")), None)
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
    except (EnvelopeError, ActorGroundingError, EventGroundingError,
            RuntimeTechnicalFailure, ValueError) as e:
        traj.status = "failed"
        traj.reason = f"{type(e).__name__}: {e}"
        return traj
