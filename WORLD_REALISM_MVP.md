# Making it a world: what was missing, and the smallest thing that fixes it

## The vision, so the changes can be judged against it

A question about the social world goes to a frozen compiler, which makes a
scene. **One** concrete trajectory is simulated. The answer is read off
what actually happened in it.

That is only worth anything if three things hold:

1. **The people are real people.** Distinct, evidence-grounded, knowing
   only what they know.
2. **The world behaves like the world.** Things take time. Things go
   wrong. Information moves imperfectly. People are busy. Things happen
   that nobody in the story chose.
3. **The answer is honest.** Supported by committed history, and admitting
   when it does not know.

Code owns what code can own perfectly — identity, time, order, access,
persistence, replay. Models own what only meaning can do — what a person
decides, what concretely follows.

## Three missing concepts

Thirty-five reviewer findings across two rounds, plus two offline reviews
of the eleven-run corpus, come down to three holes. Each one is a thing
code should have owned and did not.

### 1. Actions did not occupy time

An event had `after` — when it starts — and nothing at all about how long
it takes or that the person is busy while doing it.

- **54% of events commit at the same instant as the judgment that made
  them**; 40% of consecutive events are separated by exactly zero
  simulated time.
- **Twenty-nine self-evidenced overlaps in one run.** A woman attends a
  committee meeting "from 08:31 to about 10:30" and continues reading a
  thesis chapter at 09:01. She narrates 479 minutes of activity into a
  330-minute window.
- **A support call rendered as thirty-three events inside three minutes**,
  because nothing cost anything.
- **The world could not say "she is mid-task"**, because there was no such
  state to refer to.

### 2. The world was a reaction function, not a place

The adjudicator had exactly three occasions, every one of them reactive:
a starting event (14 calls), somebody's attempt (179), something already
sitting in somebody's inbox (266). So nothing could happen that a person
in the cast had not chosen.

- **Zero exogenous events in 209.** In ten of eleven runs no party outside
  the compiled cast ever appears.
- **One deadline expired on its own in the entire corpus.**
- **Of 135 events produced by somebody's attempt, 21 contain any setback
  at all, and every one of them is "someone did not get round to it"** —
  precisely the situation the world prompt itself names as unrealistic.

The prompt had always told the world that offices shut and outside parties
chase what they are owed. The machinery never gave it an occasion to say
so.

### 3. An act had no identity, so wording had to decide what was a repeat

Seventy-eight near-duplicate pairs across the corpus: one phone call made
four times, one banking app checked five times, one message sent twice a
minute apart.

Wording cannot decide this and must not be asked to. *"Dana sends a
message asking Marcus to confirm the hall"* and *"Marcus replies
confirming the hall"* are 0.85 identical as text — higher than many
genuine repeats — because a bag of words has no subject and no verb.
Loosening the threshold to catch the repeats deletes the reply, which is
the whole answer to that scene's question. So the threshold was set tight,
and the repeats stood.

This matters more once duration is load-bearing: six restatements of one
reading session each cost real occupancy.

Two smaller holes, also code's:

- **A view could not say "nothing changed."** It always fell back to *"time
  has passed and you are looking at your situation again"*, printed under
  a heading reading WHAT HAS CHANGED SINCE YOUR LAST TURN. 208 of 240 no-op
  consultations opened by announcing a change that had not happened.
- **The horizon test asked about the clock, not about the state**, so
  whether a run could answer NO depended on whether the wake interval
  divided the window.

## The change

### An action occupies its actor

The event envelope gains `lasts` beside `after`, and `by` beside `for`.
Code keeps, per actor, the instant they are next free:

- an event by a busy actor is scheduled from the moment they are free,
  not from now;
- the actor is occupied for `lasts` once it starts;
- their view says what they are in the middle of and until when;
- **finishing wakes them**, so occupancy can never strand anybody;
- somebody mid-task is not consulted about the next thing.

`by` and `lasts` are **required**, with no defaults. Both were optional
first, and an optional field that code merely consumes is a field a model
may skip for free — which is exactly how durations came to be decorative.
A required field with a clear rejection message is answered, because the
call is retried saying what was missing.

Both are committed to the ledger, so a record can be audited for whether
anyone was in two places at once.

| symptom | why it stops |
|---|---|
| two places at once | the second act starts when the first ends |
| fifteen events a minute | a call that lasts twenty minutes occupies twenty |
| decorative durations | `lasts` is load-bearing, so it is answered |
| no sense of being busy | there is a state, and the person is shown it |
| abandoned mid-sentence | finishing is itself a moment, and it wakes them |

### The world gets a turn of its own

Before crossing an hour or more in which nobody in the cast acts, code
asks what happened in it. Code owns only the threshold — *that* the
question is owed. What happened is the world's.

Because nobody here did it, `by` must be null on that turn, enforced by
the same identity guard that stops the world writing somebody's choice
during their own adjudication. That guard matters most exactly here:
"meanwhile, what happened?" is the widest invitation in the runtime to
record a person's decision as weather.

The turn is bounded by the rule that already governs everything else the
world does alone: the turn comes back to people at a bounded rate, whatever
the world is writing.

### An act is identified before it is compared

Same doer, same audience, same names, same quantities — *then* wording.
Identity is code-owned and does the discriminating; wording only finishes
the job. On the shipped corpus that separates 29 genuine repeats from
every cross-person pair, with no false merge.

### The horizon is a state, not an instant

The window has been lived when nothing lands before the deadline, everyone
still in the situation has been asked at this instant, and nobody intends
anything before it. Then NO is available.

Occupancy makes "everyone is free" part of that for nothing: a busy actor
has their own finishing-wake on the queue, so "nothing is scheduled"
already means "nobody is mid-anything".

If the queue simply ran dry, the run stays `incomplete_empty_queue` and
may not answer NO. Two reviewers argue that is too strict; the
disagreement is recorded in the report rather than resolved in the code.

### Delete what is not wired

Every declared-but-unused name goes. That defect class has caused several
separate live defects in this codebase, and a prompt instructing the model
to produce something nothing reads is worse than dead code — in one case
the prompt taught a field the validator now rejects, so two calls were
spent to commit nothing on every world judgment.

## What is deliberately NOT added

No probabilities, weights, scores, or utilities. No second reviewer to
check the first. No scenario-specific handling.

**No fact store.** An offline review found that no machinery holds "the
support line is shut", "the deposit is owed", "she promised Wednesday" —
and that in one run a support line answered a day before the scene said it
opened. A structured store of institutional facts is exactly the class of
arbitrary state controlling social behaviour that this design forbids;
the facts are in the scene and the record, and honouring them is meaning,
which is the model's. It is recorded as a known limitation, not patched.

`lasts` is not a behavioural number. It is the model saying how long its
own event takes, the same way `after` says when it starts, and code
enforcing the consequence.
