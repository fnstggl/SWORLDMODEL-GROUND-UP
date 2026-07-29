# Semantic runtime: completion plan

The architecture stays exactly as it is:

```
question -> frozen compiler -> four-field scene -> mechanical adapter
         -> existing persistent kernel -> code-built local views
         -> actor LLM intentions -> separate world LLM consequences
         -> natural-language journal and memories -> read-only terminal
         -> exact zero-LLM replay
```

Nothing here adds a runtime, a compiler, a clock, a queue, a journal, a
memory system, a replay system or a terminal system. Every fix below is
either a **rule in code** or a **change to one of the three universal
prompts**, plus two new **read-only review roles** that judge nothing about
the outcome and choose no behaviour.

The governing rule is unchanged:

> **LLMs write social meaning. Code controls access, time, identity,
> persistence, causality, scheduling, terminal lineage and replay.**

---

## What the previous round actually established

The mechanical half is done and independently verified: the compiler is
frozen and hash-checked on disk, no second runtime exists, information
boundaries hold under attack, the resolution reaches only the judge, and
all six runs replay exactly from the persisted ledger with zero measured
provider calls against a check that five tests prove can fail.

The behavioural half failed its quality gate. Every defect below is taken
from a named finding in
`artifacts/semantic_runtime_v1_baseline/QUALITY_*.md` or
`*_REVIEW.md`, with the trace that produced it.

---

## The two new review roles

Prompt instructions alone failed twice — measurably, not arguably. The
world was told not to narrate interface mechanics, given the exact
counter-example, and half of all committed events were still somebody
operating a phone. So two checks move from instruction to enforcement.

Both are **read-only**. Neither chooses behaviour. Neither sees the
resolution, the question or the cutoff. Each returns a two-field verdict
and, on REVISE, its exact reason goes back to the *same* call as a single
targeted correction, exactly like the existing envelope validation.

### ACTOR CONTINUITY REVIEW — `actor_mind.py`

Sees: that actor's own private context, their observations, their own
prior committed actions, their memories and plans, the current time, and
the proposed response. Nothing else.

```json
{"verdict": "PASS" | "REVISE", "reason": "..."}
```

REVISE when the actor contradicts a still-current memory without saying
what changed, repeats an action already completed, repeats a materially
identical private update, reverses a plan with no grounded reason, reasons
from information it does not possess, invents a specific person or fact,
ignores a directly relevant defining constraint, proposes someone else's
action as its own intention, behaves as a generic placeholder despite
material evidence, imitates a stereotype the evidence does not support, or
reconsiders an unchanged issue merely because time passed.

### EVENT QUALITY REVIEW — `world_mind.py`

Sees: the trigger, the relevant prior events, the actor intention that
caused this event if there was one, the proposed event, the current time.

```json
{"verdict": "PASS" | "REVISE" | "ACTOR_TURN_REQUIRED", "reason": "..."}
```

`ACTOR_TURN_REQUIRED` is the one that closes the hole no verb list could:
the proposed event contains a **new voluntary human choice** the actor has
not made. Code then hands the turn to that actor if they have the
observation that would let them choose, and otherwise requires the world to
revise back to the last environmental step.

Neither review is a closed verb list, a capability menu or an action
vocabulary. Both are natural-language semantic judgments about *this*
event, and both are blind to what answer the run is heading towards.

---

## Defect map

Each row: the observed failure, its root cause in the active production
path, the smallest universal fix, and why the fix is not scenario logic.

### 1. Generic, interchangeable actors

**Observed** — "the entire difference between Mark Cuban and Jordan Reyes
is a one-sentence blurb"; all 127 actor calls used one system prompt and
the people were interchangeable.

**Root cause** — `adapter.py` stores `private_context` verbatim, and the
evaluation scenes gave it one sentence per person. The runtime has nothing
to differentiate with.

**Fix** — no compiler schema change. Evaluation questions carry each
person's evidence in the question text, so the frozen compiler writes it
into `private_context` naturally; `views.render_view` labels it
**AUTHORITATIVE ACTOR EVIDENCE**; the actor prompt says supplied evidence
is authoritative and overrides vague associations. The same prompt works
whether the packet is one sentence or twelve lines.

**Not scenario logic** — the runtime never parses the packet. It is
natural language in, natural language out.

### 2. Stereotyping and caricature

**Observed** — risk, not yet measured: the public-figure runs lean on
pretrained persona rather than supplied evidence.

**Fix** — actor prompt: do not imitate a caricature; do not exaggerate
stereotypes attached to a public identity, occupation, age, nationality,
status or role; identity may disambiguate but supplied evidence overrides
it. Continuity review REVISEs unsupported stereotype behaviour. Matched-pair
tests (§9 of the directive) measure it: same evidence + different names
must not diverge.

### 3. Contradictions and reversals

**Observed** — Tomas both "unlocks my phone and opens the group chat" and
"puts my phone away without opening the group chat"; Dmitri accepts 1050
twice, the second time with "I have decided to accept 1050" already in his
own memory.

**Root cause** — nothing checked a response against the actor's own
history. `build_view` gained `own_actions` last round, which helped and did
not fix it.

**Fix** — continuity review, which sees exactly that history.

### 4. Reconsideration without new information

**Observed** — a supervisor consulted every few simulated minutes, each
time producing the next page of a chapter.

**Root cause** — `_schedule_recheck` geometric backoff plus the
`MAX_WORLD_RUN` hand-back consulted people who had learned nothing.

**Fix** — delete geometric polling entirely (§10 below). An actor wakes
only for a grounded reason. Continuity review REVISEs "reconsiders an
unchanged issue because time passed".

### 5. Repeated or duplicate memories

**Observed** — private updates restating unchanged state.

**Fix** — continuity review REVISEs a materially identical private update;
`actor_mind.validate_actor_response` additionally drops an update that is
byte-identical (after containment) to one this actor already holds.

### 6. Actors ignoring defining evidence

**Observed** — Aline's only distinguishing constraint (a hiring-committee
week) appeared in zero of twenty decisions.

**Fix** — evidence is labelled authoritative and rendered first;
continuity review REVISEs ignoring a directly relevant defining constraint.

### 7. Invented people and facts

**Observed** — Bea spent eight consecutive turns waiting for "Finn", a
housemate who does not exist.

**Root cause** — `event.for` is validated against the actor roster; free
text is not, and cannot be by a validator.

**Fix** — continuity review (actor side) and event-quality review (world
side) both REVISE an unsupported named person or fact. This is the class of
defect that needs a reader, which is why it needs a review role.

### 8. Meaningless device and interface activity

**Observed** — 53 of 184 committed events in the final v1 runs, 37 of 72 in
the largest; one diary entry took eight events.

**Root cause** — no code check, and the prompt ban was ignored. My
attempted structural fix (do not ask the world what became of something its
doer already knows) broke message delivery, because *"she sends the
message"* and *"he puts his phone down"* are the same shape.

**Fix** — event-quality review, which reads the sentence. Plus the
`follow_up` flag (§12 of the directive), so the world states whether its
event leaves an unresolved environmental consequence rather than code
guessing from structure.

### 9. Non-events in the journal

**Observed** — "the email remains unread", committed repeatedly.

**Fix** — event-quality review REVISEs unchanged-state narration; `null` is
explicitly normal and never counts as evidence for NO.

### 10. Arbitrary geometric wake timing

**Observed** — 5/10/20/40/80/160-minute polling produced 3:50 a.m. turns,
five wakes in five hours, day-long holes mid-task, and silently dropped
actors.

**Root cause** — `trajectory._schedule_recheck` and the queue-empty refill.

**Fix** — delete both. A wake exists only with **provenance**: `actor_plan`,
`observed_event`, `world_process`, `known_deadline`, or `action_completion`.
One pending wake per (actor, causal item, purpose); a newer one for the same
purpose replaces the older. Actors may request a future wake with a stated
plan (`next_wake`), never "reconsider later". If nothing grounded remains
before the cutoff, advance to the cutoff and judge honestly — do not invent
activity.

### 11. Unrealistic interaction speed

**Observed** — a 500-unit price gap closed in 65 minutes; a twelve-day
window resolved in 97; two YES answers both inside 65 simulated minutes.

**Fix** — grounded wakes (no polling means no artificial tempo), plus
event-quality review REVISEing unsupported timing, plus the existing
crowded-instant floor.

### 12. Actors disappearing before deadlines

**Observed** — a father signed a permission slip at 06:07, left a voicemail
at 06:59, and was never consulted again; the run skipped through the school
office opening and answered NO.

**Root cause** — three suppression mechanisms, fixed in v1; the residue is
that a person with no grounded wake simply has none.

**Fix** — `known_deadline` provenance: when the scene's own horizon
approaches and an actor has an unfinished commitment, that is a grounded
wake, not polling. Test: no actor is silently dropped before a known
deadline.

### 13. `shared_context` omniscience

**Observed** — Cuban's prompt read "you have not observed anything yet" and
he named the sender of an email nobody had delivered, because
`shared_context` contained Jordan's private intent. Present in **all six**
v1 runs.

**Root cause** — `views.build_view` puts `shared_context` in every actor
view.

**Fix** — remove it from actor views entirely. The world keeps it (it *is*
the background world). Anything an actor needs must arrive through their
own `private_context`, a starting event visible to them, or an observed
event. Permanent test: a distinctive phrase placed only in
`shared_context` appears in world prompts and in **no** actor prompt.

### 14. The world making human decisions

**Observed** — 56 of 163 committed events across v1 runs were person-choices
the world wrote; a world response narrating "Bo reads, decides, agrees and
replies" committed verbatim and produced YES with Bo's model never
consulted.

**Fix** — `ACTOR_TURN_REQUIRED`. Negative and continuation choices count:
"does not reply", "chooses not to ask", "continues writing" are decisions.

### 15. Intentions converted too easily into success

**Fix** — event-quality review REVISEs an event that grants more success
than the intention supports; the world prompt keeps the one-stage rule.

### 16/17. YES bias, and the NO bias before it

**Observed** — v1 first answered NO on every run lasting over a day
(suppression), then after the fix answered YES on five of six.

**Root cause of the residue** — a YES halts the run at the instant the
judge flips, while a NO must reach the cutoff. Sound for a monotone
question, but it means no YES is ever stress-tested.

**Fix** — the independent **terminal verifier** (§20 of the directive): a
candidate YES *or* NO_AT_CUTOFF must be confirmed by a second read-only
judgment that never sees the first one's explanation. Disagreement before
the cutoff continues the run when a grounded future event exists, and
otherwise returns a structured disagreement. No tuning toward balance:
the target is causal neutrality, not equal counts.

### 18. Premature terminal resolution

**Observed** — `unseen1_confirm` was judged YES at initialization on one
run and UNRESOLVED at initialization on another, same scene.

**Fix** — the initialization check is a terminal like any other and must
also pass the verifier before it can end a run.

### 19. Repeated event chains

**Fix** — exact duplicate suppression is already in (v1); event-quality
review adds near-duplicates, which exact matching cannot see.

### 20. Incomplete runs from step exhaustion

**Fix** — the causes above (device events, non-events, polling, duplicates)
are what consumed the steps. The ceiling stays external: if genuinely
reached, `INCOMPLETE`, never YES or NO, recording simulated time reached,
time remaining, call counts and the reason.

### 21-23. Compiler integration, universality, replay

Unchanged and already proven; the freeze test is strengthened to also catch
staged changes, alternate compiler imports and compiler-critical kernel
files. New review records must survive replay, which means new ledger ops
and their projections.

---

## Deterministic tests to add

Per §24 of the directive: actor distinction and continuity (10 tests),
event quality (10), time and wakes (9), information (7), neutrality and
terminal (8), replay and integration (8). Existing tests are not weakened;
the suite runs after every stage.

## Live evaluation

The same six cases, same questions, same provider (`deepseek-chat`), plus
Group A (rich synthetic actors, ≥3 scenarios), Group B (public-figure
diagnostic), Group C (matched pairs). Then freeze, then two
implementation-blind unseen cases from an independent agent.

## Completion condition

Every condition in §31 of the directive, judged by thirteen independent
reviewers on fresh artifacts, with a final adjudicator issuing PASS/REVISE/
FAIL per run per dimension. One FAIL means not complete, the PR stays
draft, and the blocker is stated plainly rather than hidden behind a green
test suite.
