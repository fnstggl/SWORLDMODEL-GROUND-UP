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
`for`. Code keeps, per actor, the **union of the intervals they are in** —
not a single next-free instant, which an intermediate build tried and
which produced 510 overlapping pairs, because acts are not scheduled in
the order they happen.

- An act goes in the first gap that fits it: `[start, start+lasts)`.
- The *wait* before an act is not occupancy; only the act itself is.
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

Eleven scenes, re-run from the frozen compiler's own artifacts so every
difference from the baseline is the runtime's. Frozen runtime `b7e56b1`;
summary at `artifacts/semantic_runtime/mvp/corpus_summary.json`.

| | baseline `final_v6` | this corpus |
|---|---|---|
| runs completing | 11/11 | 11/11 |
| committed events | 209 | 239 |
| **one person doing two things at once** | not measurable | **0** |
| consecutive events at zero simulated time | 40% | **29%** |
| repeats the duplicate rule did not catch | 29 | **10** |
| consultations producing nothing | 60% | **39%** |
| **events nobody in the cast chose** | **0** | **27** |
| the world's own turns taken | 0 | 28 |
| a device or channel acting on its own | 15% | 10% |
| replay exact, zero model calls | 11/11 | **11/11** |
| ledger integrity problems | 0 | **0** |
| terminals | 8 YES, **0 NO**, 3 other | 8 YES, **1 NO**, 2 incomplete |

Cost: 1,627 provider calls for 239 committed events, 6.8 per event.

**Zero overlaps is the result the occupancy model exists for**, and it is
exact rather than heuristic: every event carries `by` and `lasts`, so the
check is arithmetic on the record. An intermediate build of this same
model produced 510 overlapping pairs across 360 events; that is what the
measurement is worth.

### The one NO, audited

`evidence_avoiding` is the scene built to be a NO — Marcus has not
answered Dana's last four messages, told a colleague he is avoiding her,
and is on leave with his phone off until the following Tuesday.

```
Mon 08:00  Dana sends a message asking him to confirm the hall
Mon 08:00  it becomes available to Marcus, but his phone is off
Fri 10:00  Dana sends a follow-up asking if he has had a chance
```

At that point Marcus's own next moves are Sept 12, 13 and 14 and Dana's
are Sept 12 and 14 — every one past the Friday 17:00 cutoff. **Both
actors have a known next move beyond the deadline**, which is the horizon
rule, and 94% of the window was lived. NO is available and NO is the
answer.

Every NO in the shipped corpus — eleven of eleven — came instead from the
queue running dry, over windows that were 92-99% unlived. This is the
first honest one.

Note also the third line: Dana **chases**. That is the behaviour the
continuity reviewer used to refuse as "does again something they have
already done".

### What the corpus still shows

- `holiday_deposit` reaches the step ceiling at 128 events and is
  reported `incomplete_step_limit`, which is honest but is not an answer.
  It is the largest scene (four actors, a real deadline, money moving)
  and it is the one that most needs a higher ceiling or fewer calls per
  event.
- 29% of consecutive events still share an instant. Occupancy stops one
  person overlapping themselves; it does not stop two people acting in
  the same second, and nothing should — but some of these are still
  narration granularity rather than simultaneity.
- 10 repeats survive the duplicate rule, all of them more than an hour
  apart, which is where the rule deliberately stops so that chasing
  survives.

---

## 7. Adversarial review

Two independent read-only reviewers, neither of which produced any of the
trajectories it judged, working from the frozen code and the corpus. Every
finding came with a script and its real output; nothing was accepted as
speculative.

**24 findings. Six were serious, and every one of them was introduced by
this phase's own work.**

| what it did | fixed by |
|---|---|
| the wait *before* an act counted as doing it, so an act queued for Wednesday made its actor busy from Monday — and anything pushed past the cutoff was deleted | occupancy is the interval `[start, start+lasts)` |
| a `lasts` running past the deadline manufactured a NO: `7h58m` gave incomplete, `8h` gave NO | the horizon is per-actor and raised only by somebody *saying* what happens next |
| the identity guard was a null-check, and the world's own turn *requires* the null — a run returned YES on a decision whose owner was consulted zero times | the cast's names are code-owned, so naming one on the world's own turn hands them the turn |
| the dedup merged negations: "he can host"/"he cannot host" at 0.96 | negation joins numbers and names as a disqualifier |
| the world ran 54 consecutive adjudications with nobody consulted, against a limit of 6 | the counter clears only if somebody was actually asked |
| a contested YES was accepted on its third identical outing | a refuted claim may not be re-proposed until its evidence changes |

Three further defects were found by the corpus rather than by either
reviewer or the test suite, which is the fact worth recording: **510
overlapping pairs** from tracking one interval instead of all of them; a
**three-hour CPU spin** where a zero-length interval made the free-slot
search loop without advancing; and a finished 84-event trajectory
returning a **technical failure with no answer** because a truncated run's
NO was refused twice rather than narrowed.

Every one of those passed a green test suite. Each now has a
discriminating test: the out-of-order scheduling case, the nil-duration
act under a twenty-second alarm, and the insisted-on NO.

---

## 8. What is still wrong, stated plainly

### Accepted, with reasons

**`by: null` on an act a person really chose.** Code can require the field
to be answered and can check a named cast member against whose turn it is.
It cannot tell whether a null is honest without reading prose. The
world's own turn — the widest opening — is closed by the name check; the
other triggers are not.

**Starting events are unguarded by the identity rule.** They have no
adjudicating actor, being the scene's own premise, and they come from the
frozen compiler. Three of 239 events.

**The restatement refusal can still delete an exogenous event** proposed
on the attention trigger. Tightening it risks reviving the defect this
whole branch exists to remove — a valid action deleted — so it stays as
it is and is recorded here instead.

**No fact store.** Nothing holds "the support line is shut", "the deposit
is owed", "she promised Wednesday". In one baseline run a support line
answered a day before the scene said it opened, with the actor herself
writing *"the representative asking me to hold doesn't make sense — maybe
I misheard?"*. A structured store of institutional facts is exactly the
class of arbitrary state controlling social behaviour that this design
forbids. The facts are in the scene and in the record; honouring them is
meaning, and meaning is the model's.

**The empty-queue rule stays strict.** A run whose queue simply ran dry
may not answer NO, even having lived most of its window. Two reviewers
argued this is too strict. It is the rule that removed eleven false NOs,
so it stays, and the disagreement is recorded rather than resolved.

### What I would not claim

That the test suite is sufficient. Five of the defects fixed in this
phase were found by running the corpus against a green suite. The suite
now has a test for each, but the corpus is what has actually been finding
things, and a merge decision should rest on the corpus rather than on
`pytest`.

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
