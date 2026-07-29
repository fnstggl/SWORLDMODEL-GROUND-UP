# Semantic runtime: completion pass

**Status: INCOMPLETE.** The runtime is mechanically much stronger than it
was and behaviourally much more alive, but three independent reviewers
returned FAIL against the frozen code and one of their findings is
CRITICAL. This report says what was built, what was proved, what was
found, what was fixed, and exactly what is still wrong. It does not claim
completion, and the pull request stays in draft.

The governing rule is unchanged and is the thing being tested:

> **LLMs write social meaning. Code controls access, time, identity,
> persistence, causality, scheduling, terminal lineage, and replay.**

---

## 1. What this pass was

A targeted completion pass on the existing single-trajectory runtime. No
new repository, no redesigned architecture, no second compiler, clock,
event queue, journal, memory system, actor system, replay system or
terminal system. Every change is either a rule in code or a change to one
of the universal prompts, plus two read-only review roles that judge
nothing about the outcome and choose no behaviour.

## 2. The active production call graph

```
question
  -> compiler.compile_scene            (FROZEN, byte-for-byte unchanged)
  -> four-field SceneManifest          {actors, shared_context,
                                        starting_events, resolution}
  -> semantic_runtime.adapter          mechanical instantiation only
  -> sworldmodel.World / Clock / EventQueue    (the existing kernel)
  -> run_trajectory
       world_step   -> world LLM        -> event quality review (read-only)
       actor_step   -> actor LLM        -> actor continuity review (read-only)
       judge        -> judge LLM        -> terminal verifier (independent)
  -> ledger.jsonl persisted FIRST
  -> replay_trajectory(read_ledger(dir))   zero model calls
```

## 3. The six semantic roles, and no others

`grep 'caller.ask("' sworldmodel/semantic_runtime/*.py` returns exactly
six: `world`, `event_review`, `actor`, `continuity`, `judge`, `verifier`.

## 4. Compiler freeze, verified independently

All 24 files under `compiler/` hash to `COMPILER_FREEZE.txt` exactly. I
recomputed this with `git hash-object` rather than trusting the test, and
the freeze-and-integration reviewer recomputed it again independently and
reproduced all 24 entries. `git diff origin/main HEAD -- compiler/` is
empty. No commit on this branch touches `compiler/`.

The freeze test was strengthened this pass: it already refused untracked
and staged changes, and the kernel half is now keyed by path with the file
set checked before the hashes. Previously it looked kernel files up by
hash and skipped any that did not exist, so **deleting a frozen kernel
file passed silently** — the one thing a freeze over a file set exists to
catch.

## 5. No second compiler, WorldSpec, or persistent runtime

Importing `sworldmodel.semantic_runtime` pulls in zero `compiler.*`
modules (asserted by test). Exactly one `World`, one `Clock`, one
`EventQueue` exist in the repository.

## 6. Response schemas, unchanged in shape

- Event envelope gained **only** `follow_up`: `{description, for,
  observed, after, follow_up}`. `event_id`, `t`, `cause`, `source`,
  `trajectory_id` are code-owned and unwritable by any model.
- Actor response gained **only** `next_wake`: `{decision, intentions,
  private_updates, next_wake}`.
- Review responses are exactly `{"verdict": ..., "reason": ...}`.
- No actor-packet field was added to the compiler. Evidence reaches actors
  as natural language inside the existing `private_context`.

## 7. The two read-only review roles

Both see the situation and the proposal, never the resolution, and can
create nothing. Each gets **one** targeted correction; a second failure
abandons that turn or that event rather than killing the run.

- **Actor continuity review** checks two things only: whether the person
  contradicts what they themselves established, and whether they treat as
  fact something that is not. It explicitly does not decide what they
  *should* do — an earlier version refused a negotiator's counteroffer as
  a defect, which is the review deciding the behaviour it exists to check.
- **Event quality review** checks whether the proposed event is a real
  thing that happened, with `ACTOR_TURN_REQUIRED` for a decision put in
  somebody's mouth.

## 8. Grounded wakes: the polling is gone

All geometric polling and widening backoff (5/10/20/40/80/160 minutes) is
deleted, as are automatic "time passed, reconsider" wakes. Every wake
carries a provenance from a fixed vocabulary and a concrete reason, and
one pending wake per `(actor, about, provenance)` replaces rather than
stacks. Verified across all 23 runs: every wake has a valid provenance and
a non-empty reason.

**But see finding C2:** only two of the five declared provenances are
reachable, and the missing `known_deadline` is the reason runs stop early.

## 9. Information boundaries

Verified across all runs by an independent reviewer reading the actual
persisted prompts:

- The resolution appears in **zero** artifacts outside the judge and
  verifier.
- `shared_context` reaches the world only. It is not in any of the 204
  rendered actor views.
- No actor sees another actor's `private_context`, private memories,
  decisions or intentions.
- Wake reasons never reach the woken person.
- The verifier's real prompts carry only the condition, the clock and the
  committed record — never the first judge's verdict, citations or
  explanation.

## 10. Six defects found by live evidence, each with a discriminating test

Every one was found by reading what a run actually did, and every
regression test below was verified to **fail** without its fix.

1. **A thing passed over once could never be noticed again.** The guard
   against asking the world the same question twice compared the record
   and the items but not the clock. Whether attention has arrived is a
   question whose only real input is how long something has been sitting
   there.
2. **Anyone who had not already spoken was inert.** A wake existed only
   where somebody had planned one, so only people who had already acted
   were ever brought back. A message landed in a group chat of four and
   the three who had not been talking were never asked anything again.
   `observed_event` was in the vocabulary and wired to nothing. Arrival is
   now a cause the world owes an answer for.
3. **Finishing your own action left you with no turn.** A man asked to
   confirm a hall booking noticed the message, read it, and checked the
   booking system — and the run stopped there, on Monday morning, and
   jumped to Friday's deadline. He checked the booking *in order to*
   answer her. `action_completion` was also declared and wired to nothing.
4. **The event review had machinery backwards.** It refused "she opens it
   and reviews the document" as interface operation and passed "the
   printer prints it". One run committed a printer printing, the printing
   finishing and a scanner saving a file — three of its five events were
   furniture — while its twin refused every proposal its actor made and
   ended with a woman who had done nothing for two days.
5. **The same event was committed twice.** The duplicate guard checked the
   journal, but events are scheduled at one instant and committed at a
   later one, so two calls made before either landed both checked against
   a record containing neither.
6. **A false NO.** A man texted back "yes, please confirm the Thursday 8am
   slot" within the minute, and the record said nobody had observed it —
   himself included, because he was not among the people it was sent *to*.
   He was its author. The judge read a confirmation nobody was aware of
   and answered that he never confirmed. Authorship is not delivery.

## 11. Deterministic test suite

**248 tests pass** with the runtime frozen, under `PYTHONHASHSEED` 0, 1
and 12345. The suite includes the six regression tests above plus the
pre-existing invariant tests; none were weakened.

## 12. Live evaluation: 23 runs

| run | terminal | events | machinery | acted | wakes | replay |
|---|---|---|---|---|---|---|
| a1_responsive ×4 | YES ×4 | 7–8 | 0–3 | 2/2 | 3–4 | exact |
| a2_unresponsive ×4 | NO ×4 | 3–9 | 0–1 | 2/2 | 3–25 | exact |
| b1_okafor_herrera ×4 | YES ×1, NO ×3 | 1–6 | 0–1 | 1/2 | 0–3 | exact |
| b2_thornbury_lim ×4 | YES ×1, NO ×3 | 2–8 | 0–2 | 1–2/2 | 1–6 | exact |
| c1_against_stereotype | YES | 33 | 0 | 2/2 | 6 | exact |
| case1_cold_email | NO | 1 | 0 | 2/2 | 1 | exact |
| case2_negotiation | YES | 40 | 3 | 2/2 | 104 | exact |
| unseen1_confirm | YES | 2 | 0 | 1/1 | 1 | exact |
| unseen2_feedback | YES | 19 | 4 | 2/2 | 36 | exact |
| case3_group | incomplete / UNRESOLVED | 22 | 0 | 4/4 | 30 | exact |
| unseen4_holiday_deposit | incomplete / UNRESOLVED | 101 | 8 | 4/4 | 250 | exact |

**23 runs, 373 committed events, 10 YES / 11 NO_AT_CUTOFF / 2 incomplete,
23/23 replay exact with 0 model calls, 0 mechanical check failures.**

Interface mechanics fell from 35% of committed events at the start of this
work to **9%** (32/373).

Two things in that table are worth naming.

**The housemates all turn up now.** Four days of four people used to
produce four events, with every wake in the run belonging to the woman who
sent the first message. It is 22 events across all four of them, none of
it machinery, and the three who had not spoken first are woken and
consulted like anybody else. That case is what exposed defect 2 and it is
the direct proof of the repair.

**The safety ceiling behaves as a ceiling, live.** The holiday-deposit run
committed 101 events over 250 wakes with all four people acting, hit the
step ceiling before the horizon, and reported `status = incomplete` with
`UNRESOLVED`. It was **not** converted into YES or NO. That is the rule
the directive requires of a technical guard, demonstrated by a run rather
than asserted by a docstring.

## 13. Evidence sensitivity: the matched pairs

One run per arm cannot tell a real difference from an ordinary one — the
first pass had pair B answering YES under one set of names and NO under
the other, and it read like the names had done it. Four runs of each arm:

| arm | YES rate |
|---|---|
| same two names, **responsive** evidence | **4/4** |
| same two names, **avoiding** evidence | **0/4** |
| Okafor / Herrera | 1/4 |
| Thornbury / Lim | 1/4 |

- **Same names, opposite evidence separates completely.** Behaviour tracks
  the evidence.
- **Different names, same evidence answers at exactly the same rate.**
  Behaviour does not track the names. The first-pass split was the
  variance the question has on its own.
- **Evidence against the stereotype:** an 81-year-old who wrote the shop's
  stock-control software and had already configured the terminal herself
  got a 33-event trajectory with **zero** machinery events and was treated
  throughout as the competent engineer her evidence describes.

The control has one limitation I did not hand-edit away: the compiler
produced a one-clause difference in `shared_context` between the B arms.
The **actor-facing** evidence is byte-identical after name substitution,
and actors never see `shared_context`, so the control holds where it
matters — but it is not a perfect control and I am not claiming it is.

The rate itself is the thing to be unhappy about. A woman who has signed
and returned every document within a day, and said on Monday she was
ready, gets there in one run out of four. That is not about her name; see
finding C1.

## 14. Independent adversarial review

Six reviewers ran against the frozen code and the fresh artifacts. Three
returned PASS, three returned FAIL.

| reviewer | verdict |
|---|---|
| freeze and integration | **PASS** |
| replay, determinism, persistence | **PASS** |
| information boundary | **FAIL** (1 HIGH) |
| universality and bloat | **FAIL** (1 HIGH) |
| actor / world separation | **FAIL** (2 HIGH) |
| time, causality, terminal | **FAIL** (1 CRITICAL, 2 HIGH) |

Reports are in `artifacts/semantic_runtime/reviews/*.json`.

### Fixed this pass

- **Information boundary, HIGH — a sender saw the far end of what they
  sent.** My own authorship fix leaked: "your own action is not news to
  you" is inherited down the consequence chain and I let "you know you did
  this" ride along with it, so a negotiator was told as authoritative
  observed fact that her offer had reached the other man's phone and that
  he had not looked at it — across 67 of her 75 turns. The two facts now
  travel separately. Regression test added.
- **Separation, HIGH — the rejected decision went to the wrong person.**
  When the review caught the world writing somebody's choice, the turn was
  handed to the event's *audience*, which is usually whoever the thing was
  heading towards: a rejected "Marcus replies to Dana" went to Dana. The
  actual decider was never asked, so the decision the review had correctly
  protected simply did not happen. It now goes to the person the step is
  about. The filter it replaced was inert anyway.
- **Separation, MEDIUM — the review could not tell whose choice it was
  reading.** It is now told whose attempt it is judging.

### NOT fixed — the honest blockers

**C1 (CRITICAL). A final NO is licensed over time the trajectory never
simulated.** The main loop breaks when the event queue is empty *or* the
next event is past the cutoff, and does not distinguish them; the closing
judgment then advances the clock to the horizon and permits NO_AT_CUTOFF.
Measured across the corpus: **11 of 11 NO runs stopped with an empty
queue, not at the horizon** — `case1_cold_email` jumped the entire 14-day
window in one record after a single step; `b1_okafor_herrera__r3` stopped
one step from the send with 2.5 days left. NO_AT_CUTOFF is a claim about a
whole window justified only by the absence of events across it, and in
these runs most of that window was never simulated. An empty queue with
days left is not evidence that nothing happens; it is evidence that nobody
was asked. **The suggested fix is to treat an empty queue before the
cutoff as a truncation, so such a run reports `incomplete` and may not
answer NO.** I did not apply it because it changes the status of half the
corpus and needs a full re-evaluation, not a patch at the end of a pass.

**C2 (HIGH). Three of five wake provenances are wired to nothing.** Only
`world_process` and `actor_plan` are ever scheduled (140 and 82 across 222
wakes; the other three: zero). `observed_event` and `action_completion`
exist as immediate turns rather than scheduled wakes, so for those the
label is stale documentation. `known_deadline` is different: **nothing
anywhere brings a person back because a deadline they know about is
approaching**, and the cutoff never enters any prompt. This is the direct
cause of C1.

**C3 (HIGH). The world still authors people's decisions.** Enforcement is
the prompt plus the LLM reviewer, with no code guard — and the reviewer
passes them. Live: `case2_negotiation` e721 "Dmitri opens the messaging
app and reads the unread messages from Priya" on a `pending_progression`
trigger, cited in that run's YES. Code cannot identify an event's subject
without parsing language, so this belongs to the reviewer; telling it
whose attempt it is judging (done) is a mitigation, not a fix.

**C4 (HIGH). The verifier's validator enforces no clock rule**, so
NO_AT_CUTOFF is accepted before the cutoff — live in
`a1_responsive__r2` four days early, destroying a correct YES.
One-parameter fix, not applied because it lands mid-evaluation.

**C5 (MEDIUM). `MAX_EVENTS_PER_INSTANT` measures the wrong instant** — the
one the world was asked at, not the one the event lands on. Reproduced: 4
events on one instant.

**C6 (MEDIUM). The reserved final-call allowance cannot pay for the
closing judgment** (2 reserved against up to 4 attempts once the verifier
is counted).

**C7. Granularity is uncontrolled.** The world sometimes decomposes an act
into micro-fragments and the trajectory runs out of room before the
meaningful outcome. `b2_thornbury_lim` spent 8 events on "notices",
"opens and sees", "signs with a pen" (twice, not byte-identical so the
duplicate guard missed it) and never reached sending. `c1` packed 15
events into its first minute — never more than 3 per *exact* instant, so
the guard never tripped, because "instant" is second-resolution. This is
the main reason pair B's YES rate is 1/4.

## 15. Artifacts

21 per run: `ledger.jsonl` (authoritative, written first),
`journal.jsonl`, `compiled_scene.json`, `initial_actor_states.json`,
`event_queue.jsonl`, `actor_views.jsonl` (every actor's entire prompt),
`actor_exchanges.jsonl`, `actor_memory_updates.jsonl`,
`world_exchanges.jsonl`, `world_judgments.jsonl`, `terminal_checks.jsonl`,
`terminal_verifications.jsonl`, `actor_continuity_reviews.jsonl`,
`event_quality_reviews.jsonl`, `grounded_wakes.jsonl`,
`review_exchanges.jsonl`, `compile_runtime_bindings.json`,
`terminal_result.json`, `runtime_metrics.json`,
`replay_verification.json`, `trajectory.md`.

Re-checkable by anyone: `evaluation/verify_run.py`,
`evaluation/reverify_replay.py`, `evaluation/summarise_runs.py`,
`evaluation/interface_mechanics.py`, `evaluation/matched_pair_result.py`.

## 16. Numeric constants

The universality reviewer inventoried every numeric constant in the
runtime and reached the same conclusion I did: **no arbitrary numerical
variable controls social behaviour**, and it holds structurally rather
than by accident — nothing numeric a model writes is ever read back as a
number. Every constant is a transport parameter, a parse bound, a
recursion bound, a clock-granularity guard, or a call ceiling. Every
comparison in `trajectory.py` is a clock ordering, a change detector, a
cardinality test, or a counter against a technical ceiling.

No probabilities, likelihoods, weights, scores, utilities, particles,
branches, aggregation, random draws, retrieval, evidence search, quantity
registers, scenario routers, capability menus or fixed action
vocabularies exist anywhere in the runtime.

## 17. What is not done

- **Seven of the thirteen required reviewers did not run**: actor realism,
  causal realism, information and timing, terminal independence, device
  and event meaning, evidence sensitivity, and the final quality-gate
  adjudicator. Six ran.
- **The corpus mixes two code versions.** Twenty-one runs predate the
  reviewer fixes in §14; `case3_group` and `unseen4_holiday_deposit` were
  run afterwards. No run predates the six fixes in §10.
- **No implementation-blind unseen cases from an independent agent** were
  authored post-freeze this pass.
- **Group A (≥3 rich synthetic-actor scenarios) and Group B (public-figure
  diagnostic)** were not run as separate named groups.

## 18. The verdict

The runtime is mechanically sound in the areas that were independently
proved: the compiler is frozen, replay is exact from the persisted ledger
with zero model calls across all 23 runs, the resolution reaches only the
two roles allowed to see it, time never moves backwards, every event has a
real cause, and no number decides how anybody behaves.

It is not behaviourally complete. Half the corpus reaches its answer by
running out of things to do rather than by reaching the horizon, and the
mechanism that would prevent that — a wake because a deadline is coming —
is declared in the vocabulary and connected to nothing.

**One FAIL means the semantic runtime is not complete. There are four.**
The pull request stays in draft, and the blocker is stated above rather
than hidden behind a green test suite.
