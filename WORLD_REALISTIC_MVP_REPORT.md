# World-realistic simulation MVP — what was built, what it fixes, what is still wrong

Branch `codex/world-realistic-simulation-mvp`, off the branch PR #6 was
written into (`codex/single-trajectory-runtime-final-completion`).

Read `WORLD_REALISM_MVP.md` first: it states the vision and the three
missing concepts. This report is the evidence.

---

## 1. What this is for

A question about the social world — *"Will Bo reply to Ada before
Friday?"* — goes to a frozen compiler, which makes a scene. **One**
concrete trajectory is simulated. The answer is read off what actually
happened in it.

The governing rule:

> **LLMs write social meaning. Code controls access, time, identity,
> persistence, causality, scheduling, terminal lineage, and replay.**

Everything below is an application of that rule. Where the answer was
"the model should do this", it is a prompt. Where the answer was "this is
a fact about time, order, identity or access", it is code.

---

## 2. The three things code should have owned and did not

### 2.1 Actions did not occupy time

An event had `after` — when it starts — and nothing about how long it
takes. Measured over the eleven-run shipped corpus:

| what | measured |
|---|---|
| events committing at the same instant as the judgment that made them | 112 / 209 (54%) |
| consecutive events separated by exactly zero simulated time | 40% |
| self-evidenced overlapping pairs in one run | 29 |
| stated activity narrated into one 330-minute window | 479 minutes (1.45× overbooked) |
| runs consuming under 2% of their own window | 6 of 11 |

The worst single case: a woman attends a committee meeting *"from 08:31 to
about 10:30"* and continues reading a thesis chapter at 09:01.

**The fix.** The envelope gains `lasts` beside `after`, and `by` beside
`for`. Code keeps a per-actor instant-they-are-next-free.

- An event by a busy actor is scheduled from when they are free.
- The actor is occupied for `lasts` once it starts.
- Their view says what they are in the middle of and until when.
- **Finishing wakes them** (`own_act_finished`), so occupancy can never
  strand anybody.
- Somebody mid-task is not consulted about the next thing.

`by` and `lasts` are **required**, no defaults. Both were optional first,
and an optional field that code merely consumes is a field a model may
skip for free — which is exactly how durations came to be decorative. A
required field with a clear rejection message gets answered, because the
call is retried saying what was missing.

Both are committed to the ledger, so a record can be audited for whether
anybody was in two places at once.

### 2.2 The world was a reaction function, not a place

The adjudicator had three occasions, every one reactive: a starting event
(14 calls), somebody's attempt (179), an item already in somebody's inbox
(266).

| what | measured |
|---|---|
| exogenous events across the corpus | **0 of 209** |
| runs in which any party outside the compiled cast appears | 1 of 11 |
| deadlines that expired on their own | 1 |
| attempt-events containing any setback | 21 of 135 (16%) |
| of those, "someone did not get round to it" | 21 of 21 |

The world prompt had always said that offices shut and outside parties
chase what they are owed. The machinery never gave it an occasion to say
so.

**The fix.** Before crossing ≥ 1 hour in which nobody in the cast acts,
code asks what happened in it. Code owns only the threshold — *that* the
question is owed. What happened is the world's. Because nobody here did
it, `by` must be null on that turn, enforced by the same identity guard
that stops the world writing somebody's choice during their own
adjudication — which matters most exactly here, since *"meanwhile, what
happened?"* is the widest invitation in the runtime to record a person's
decision as weather. The turn is bounded by the rule that already governs
everything else the world does alone.

### 2.3 An act had no identity, so wording had to decide what was a repeat

78 near-duplicate pairs: one phone call made four times, one banking app
checked five times, one message sent twice a minute apart.

Wording cannot decide this. These two are 0.85 identical as text — higher
than many genuine repeats — because a bag of words has no subject:

> Dana Whitfield sends a message to Marcus Bell asking him to confirm the
> hall is held for the 14th.
>
> Marcus Bell replies to Dana Whitfield's message confirming the hall is
> held for the 14th.

Loosening the threshold to catch the repeats deletes the reply, which is
the whole answer to that scene's question.

**The fix.** Same doer, same audience, same names, same quantities —
*then* wording, at a threshold that can now safely be lower (0.86 → 0.80).
Identity is code-owned and does the discriminating.

Measured over the shipped corpus: **29 genuine repeats separated, no
cross-person pair merged.** Four pairs are blocked by a differing name;
three of those are correct (a call to Dev is not a call to Nina; a
transfer that *has* arrived is not one that *has not*), one is a genuine
repeat left alone. Leaving a duplicate line in the record is the cheap
mistake; merging two real acts deletes somebody's afternoon.

---

## 3. Two smaller holes, also code's

**A view could not say "nothing changed."** It always fell back to *"time
has passed and you are looking at your situation again"*, printed under a
heading reading WHAT HAS CHANGED SINCE YOUR LAST TURN. 208 of 240 no-op
consultations opened by announcing a change that had not happened. It now
says the true thing, under a heading that can be answered with "nothing",
and distinguishes a first look from a later one.

**The continuity reviewer forbade what the actor prompt asks for.**
ACTOR_SYSTEM says *"people wait, chase, ask again"*. CONTINUITY_SYSTEM
answered REVISE when a reply *"does again something they have already
done"* or *"goes over an unchanged question again merely because time has
passed"* — chasing is both. In the corpus, a woman owed £600 never
contacts the person who owes her, and a student waiting on feedback never
follows up once in 31 events. What those rules protected is kept and
stated precisely: doing again something that already *worked*, or
presenting something already done as if for the first time.

---

## 4. Two live defects found by the offline sweep

1. **`WORLD_SYSTEM` still taught the model to emit `follow_up`**, which
   the validator now rejects. Every world judgment that obeyed the prompt
   was rejected, retried, and committed nothing: two calls for nothing.
   A prompt instructing a model to produce something nothing reads is
   worse than dead code — this one shaped the answer into a rejection.

2. **The acceptance checker kept its own copy of the wake vocabulary**,
   listing three provenances the runtime cannot emit and missing one it
   schedules. Every run using the occupancy model would have failed
   acceptance with *"a wake has provenance own_act_finished"*. The
   vocabulary now has one definition, at module scope, and the checker
   imports it. That defect had recurred five times; a vocabulary with two
   homes has no home.

Also deleted, all confirmed unreachable: `MAX_ENV_CHAIN` and its counter
(4 writes, 0 reads), `OP_TURN_ABANDONED`, `abandoned_turns` (a permanent
zero in every metrics file), the `incomplete_review_failure` status
`finish()` cannot produce, `world_step`'s unused `intention` parameter,
and two trace kinds nothing emits.

---

## 5. Measurement: three questions, not one

Two readings of the same corpus came out at 14% and 44% "machinery"
because they were counting different things. `evaluation/interface_mechanics.py`
now reports three numbers, named:

- **who acted** — exact, read off `by`;
- **a device or channel acting on its own** — text heuristic, lower bound;
- **noticing** — an event whose whole content is somebody becoming aware.
  A real human act, but a run made of these is a run about checking
  phones. This is what the 44% was counting.

On the shipped corpus this reproduces both prior figures: **15% device,
42% noticing.**

---

## 6. Corpus on the frozen runtime

<!--CORPUS-->

---

## 7. Adversarial review

<!--REVIEW-->

---

## 8. What is still wrong, stated plainly

<!--REMAINING-->

---

## 9. Deliberately not added

No probabilities, weights, scores, or utilities. No second reviewer to
check the first. No scenario-specific handling. No branching, sampling or
aggregation: still exactly one trajectory.

**No fact store.** No machinery holds *"the support line is shut"*, *"the
deposit is owed"*, *"she promised Wednesday"* — and in one run a support
line answered a day before the scene said it opened, with the actor
herself writing *"the representative asking me to hold doesn't make sense
— maybe I misheard?"*. A structured store of institutional facts is
exactly the class of arbitrary state controlling social behaviour that
this design forbids. The facts are in the scene and in the record;
honouring them is meaning, and meaning is the model's. Recorded as a
known limitation rather than patched.

`lasts` is not a behavioural number. It is the model saying how long its
own event takes, the same way `after` says when it starts, and code
enforcing the consequence.
