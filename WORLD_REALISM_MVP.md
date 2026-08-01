# Making it a world: what was missing, and the smallest thing that fixes it

## The vision, so the changes can be judged against it

A question about the social world goes to a frozen compiler, which makes a
scene. **One** concrete trajectory is simulated. The answer is read off
what actually happened in it.

That is only worth anything if three things hold:

1. **The people are real people.** Distinct, evidence-grounded, knowing
   only what they know.
2. **The world behaves like the world.** Things take time. Things go
   wrong. Information moves imperfectly. People are busy.
3. **The answer is honest.** Supported by committed history, and admitting
   when it does not know.

Code owns what code can own perfectly — identity, time, order, access,
persistence, replay. Models own what only meaning can do — what a person
decides, what concretely follows.

## One missing concept

Thirty-five reviewer findings across two rounds are mostly symptoms of a
single hole: **actions do not occupy time.**

An event has `after` — when it starts — and nothing at all about how long
it takes or that the person is busy while doing it. Everything follows:

- **65% of events are simultaneous with their cause** (132 of 202 in the
  current corpus). Duration is decorative, so the model does not bother.
- **Actors are in two places at once.** A thirty-minute call and a signing
  two minutes later, with nothing to notice the overlap.
- **Fifteen events in one minute**, and a phone call rendered as
  thirty-three micro-steps, because nothing costs anything.
- **The world cannot say "she is mid-task"**, because there is no such
  state to refer to.
- **The horizon cannot be judged**, because "everyone is free and nothing
  is pending" is not representable.

Two further structural holes, smaller but real:

- **People are consulted when nothing has changed.** 60% of turns produce
  no intention; one actor received 55 consecutive turns and 185 model
  calls to commit 2 events.
- **The horizon test asks about the clock, not about the state**, so
  whether a run can answer NO depends on whether the wake interval divides
  the window.

## The change

### 1. An action occupies its actor

The event envelope gains `lasts` beside `after`. Code keeps, per actor,
the instant they are next free, and:

- an event by a busy actor is scheduled from the moment they are free,
  not from now;
- the actor is busy for `lasts` once it starts;
- a person's view says what they are in the middle of and until when.

This is code owning time, which is its job. It is one field and one dict.

What it buys, without any prompt telling the model to behave:

| symptom | why it stops |
|---|---|
| two places at once | the second act starts when the first ends |
| fifteen events a minute | a call that lasts twenty minutes occupies twenty |
| decorative durations | `lasts` is load-bearing, so it is answered |
| no sense of being busy | there is a state, and the person is shown it |
| micro-step narration | splitting an act costs the same time as not splitting it, and gains nothing |

### 2. A person is consulted when something has changed

A turn happens when they observed something new, their own plan came due,
something they started finished, or the world went quiet and everyone is
being asked once. Not otherwise. A wake that finds nothing new does not
spend a call.

### 3. The horizon is a state, not an instant

The window has been lived when: nothing is scheduled before the cutoff,
every actor is free, every actor has been asked at this instant, and
nobody intends anything before the deadline. Then NO is available.

If any of those is false — something is still pending, someone is still
busy, someone has not been asked — the run is `incomplete_empty_queue` and
may not answer NO.

This satisfies what the strict rule was protecting: no NO is ever claimed
over time nobody simulated. It removes the part that was an artifact —
whether the clock happened to land on the cutoff second.

### 4. Delete what is not wired

Every declared-but-unused name goes. That defect class has already caused
three separate live defects in this codebase, and a prompt instructing the
model to compute something nothing reads is worse than dead code: it
shapes the answer for nothing.

## What is deliberately NOT added

No probabilities, weights, scores, or utilities. No second reviewer to
check the first. No scenario-specific handling. `lasts` is not a
behavioural number — it is the model saying how long its own event takes,
the same way `after` says when it starts, and code enforcing the
consequence.
