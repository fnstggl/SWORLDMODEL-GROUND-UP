# Single-trajectory runtime: final completion report

**Corpus SHA:** `37dccff` — **INVALIDATED**, see §13.
**Current SHA:** `25b7f05`
**Baseline:** merged `main` at `26b5203` (PR #5)
**Draft PR:** https://github.com/fnstggl/SWORLDMODEL-GROUND-UP/pull/6
**Recommendation: DO NOT MERGE YET.** See §14.

Every table below is generated from artifacts, not written by hand. The
previous report had three per-run numbers wrong in the flattering
direction and a reviewer had to catch them.

---

## 1. Why this pass exists

PR #5 was merged into `main` despite its own report saying INCOMPLETE and
its final quality gate returning FAIL. Thirteen reviewers had found **9
CRITICAL and 26 HIGH** findings; two returned PASS.

Four reviewers independently converged on one chain. The adjudicator's
words:

> The system has no reliable way to let a person finish an ordinary
> action. The event-quality review holds two rules that cannot both be
> satisfied for any act done through a device (atomic → "the machine did
> it"; combined → "several stages at once"), so the decisive act gets
> deleted; the actor repeats it and is refused by the continuity reviewer
> for repeating; the queue empties; the clock is teleported to the
> horizon; and the absence of the act that was just destroyed is reported
> as the answer. **It is one defect wearing three costumes.**

The response to that is not a better prompt and not a third reviewer. It
is to take away the power to delete a valid action.

## 2. What was removed

- **The event-quality reviewer, from the hot path, with its correction
  loop.** In one merged run it PASSed and REVISEd the byte-identical
  string four calls apart. The same lease scene on byte-identical
  evidence answered YES three times and NO three times, and the flip was
  the reviewer rather than the world.
- **The `follow_up` → `event_consequence` transport chain**, and with it
  the arrivals, notifications, buzzing phones and still-unread messages.
  Two independent counts put that chain at 42–44% of the merged corpus.
- **Three wake provenances** (`observed_event`, `known_deadline`,
  `action_completion`) that no code path could produce — zero occurrences
  across 1,087 wakes.
- **Two exception classes** never raised anywhere.
- `EVENT_REVIEW_SYSTEM`, `validate_event_review`, `OP_EVENT_REVIEW`.

## 3. What was narrowed

- **The continuity reviewer cannot delete a turn.** One correction, then
  the original reply stands, recorded as `OVERRULED`. It was the second
  half of the chain in §1: it refused a woman for repeating an attempt
  whose event the *other* reviewer had just destroyed.
- **The attention question may only be answered with attention.** An
  answer that does not mark the concerned person as observing changes no
  information state; it is the arrival narrated again, and it is refused
  structurally — by what the event does, not by its words.

## 4. What was added

- **`OP_ATTEMPT`.** An intention becomes a code-owned object with an
  `attempt_id` before it reaches the world, and the committed consequence
  carries that id. A YES can no longer rest on a chain whose decisive step
  nobody took.
- **`by` on the event envelope.** The world declares whose action an event
  is. If that is not the actor whose attempt was being adjudicated,
  control routes to that person and nothing is committed. Identity, not
  keywords, not a reviewer reading prose.
- **Explicit terminal statuses:** `incomplete_empty_queue`,
  `incomplete_step_limit`, `incomplete_call_limit`.
- **`structural_refusals.jsonl`** — what code refused and why, since there
  is no semantic gate left to log.

## 5. The active call graph

```
question
  -> compiler.compile_scene                 FROZEN, 24/24 files unchanged
  -> four-field SceneManifest
  -> semantic_runtime.adapter               mechanical instantiation
  -> sworldmodel World / Clock / EventQueue the existing kernel
  -> run_trajectory
       actor_step   -> actor LLM      -> continuity check (cannot delete)
                    -> OP_ATTEMPT (code-owned id)
       world_step   -> world LLM      -> deterministic validator only
                    -> structural checks: by-identity, attention-only
       judge        -> judge LLM
                    -> verifier LLM   (once per candidate answer)
  -> ledger.jsonl persisted FIRST
  -> replay_trajectory(read_ledger(dir))    zero model calls
```

## 6. Production LLM roles

Five, and `grep 'caller.ask("'` returns exactly these: `actor`, `world`,
`continuity`, `judge`, `verifier`. The sixth — `event_review` — is gone.
Per step the hot path passes through **4** semantic gates where it passed
through **5**. My earlier "6 → 4" was wrong: the sixth role was never
per-step. The removed reviewer was 11.9% of hot-path calls, not the
"roughly half" I claimed.

## 7. Code-owned state transitions

`journal.event` · `journal.observed` · `semantic.actor_profile` ·
`semantic.actor_call` · `semantic.attempt` · `semantic.world_call` ·
`semantic.terminal_check` · `semantic.horizon_reached` ·
`semantic.continuity_review` · `semantic.terminal_verification` ·
`semantic.actor_turn_abandoned`

Delivery and availability are **not** among them as events: they are
`for` and `observed_by` on the item itself.

## 8. Before and after

| | merged main | this branch |
|---|---|---|
| runtime lines | 3,362 | 3,194 |
| hot-path semantic gates per step | 5 | 4 |
| machinery share of committed events (script) | 52% | 14% |
| machinery share (reviewer hand count) | — | **44%** — see §13 |
| tracked artifact files | 4,190 | 1,199 |
| deterministic tests | 253 | 264 |
| declared-but-unreachable wake provenances | 3 | 0 |
| never-raised exception classes | 2 | 0 |

## 9. The frozen corpus

`artifacts/final_v6/`, all on `37dccff`, no code touched while any run was
in flight. Generated by `evaluation/summarise_runs.py`:

| run | terminal | events | machinery | acted | wakes | replay |
|---|---|---|---|---|---|---|
| anti_stereotype | YES | 26 | 3 | 2/2 | 28 | exact |
| cold_email | incomplete_empty_queue | 2 | 1 | 2/2 | 54 | exact |
| evidence_avoiding | incomplete_empty_queue | 3 | 2 | 2/2 | 7 | exact |
| evidence_responsive | YES | 7 | 1 | 2/2 | 6 | exact |
| feedback_deadline | YES | 31 | 3 | 2/2 | 28 | exact |
| group_coordination | YES | 26 | 2 | 4/4 | 81 | exact |
| holiday_deposit | incomplete_empty_queue | 91 | 11 | 4/4 | 135 | exact |
| lease_other_names | YES | 4 | 0 | 1/2 | 1 | exact |
| lease_return | YES | 10 | 6 | 1/2 | 3 | exact |
| negotiation | YES | 7 | 0 | 2/2 | 2 | exact |
| plumber_confirm | YES | 2 | 1 | 1/1 | 1 | exact |

**11 runs · 209 events · machinery 14% · 8 YES · 0 NO_AT_CUTOFF · 3
incomplete_empty_queue · 11/11 replay exact with 0 model calls · 0
mechanical check failures.**

Baseline for comparison (`artifacts/baseline_main/`, 5 runs on merged
main): 77 events, **52% machinery**, 2 YES, 2 NO_AT_CUTOFF (both the
empty-queue kind), 1 incomplete.

The lease case that PR #5's corpus resolved 1-in-4 resolves YES here under
both name sets — `lease_return` and `lease_other_names`. `group_coordination`
resolves YES with all four housemates acting, where merged main spent 250
steps on notification churn and never reached its horizon.

## 10. Root causes, and what each cost

| root cause | cost in the merged corpus | repair |
|---|---|---|
| a semantic gate could delete a valid action | the decisive act of a scenario, and its absence became the answer | gate removed from hot path |
| a second gate refused the retry | the person then did nothing for two days | cannot delete a turn |
| transport narrated as events | 42–44% of the record | chain deleted; delivery is item state |
| empty queue → clock jump → NO | 11 of 11 NOs, one over an unlived fortnight | explicit INCOMPLETE statuses |
| consequences unbound to attempts | a YES resting on a step nobody took | `OP_ATTEMPT` + `attempt_id` |
| the world authoring others' choices | committed as history, cited in YES | `by` + identity routing |
| declared-but-unwired vocabulary | three separate live defects | deleted |

## 11. Regression tests

`tests/test_runtime_completion.py` — 15 tests written against merged main;
**9 verified failing on `26b5203`**, covering: empty queue returning NO ·
clock jumping to cutoff · incomplete translated into NO · device state
committed as narrative · duplicate physical actions · a valid attempt
deleted by a semantic reviewer · inconsistent treatment of identical text ·
a consequence with no attempt id · the world authoring another person's
choice. The remaining six passed on main and are guards: horizon honestly
reached · recipient seeing information early · sender learning
recipient-side attention · verifier returning NO early · replay detecting
mutation/deletion/reordering/forgery · exactly one runtime path.

264 tests pass under `PYTHONHASHSEED` 0, 1 and 12345.

## 12. Compiler freeze

24 of 24 files under `compiler/` hash byte-for-byte to
`COMPILER_FREEZE.txt`, recomputed rather than trusted. No commit on this
branch touches `compiler/`.

## 13. Reviewer verdicts, and what they found in my own work

Four independent read-only reviewers ran against `37dccff`. Reports in
`artifacts/semantic_runtime/reviews_v2/`.

| reviewer | verdict | CRITICAL | HIGH |
|---|---|---|---|
| bloat and universality | **FAIL** | 2 | 4 |
| terminal honesty | **FAIL** | 1 | 3 |
| event meaning and realism | **FAIL** | 2 | 4 |
| boundary, separation, replay | **FAIL** | 1 | 4 |

**Four FAILs. This is not complete.** What they got right, and what I have
since fixed:

**The zero-NO diagnosis in my own §14 was wrong.** I blamed a missing wake
provenance. Two reviewers independently reproduced the real cause: every
scheduling site refuses an instant past the cutoff, so the beyond-deadline
signal was computed and discarded, and `NO_AT_CUTOFF` was reachable only
when the wake interval happened to divide the window. A wake every two days
over a fortnight answered NO; every three days answered incomplete, with
*identical world behaviour*. Fixed, with a test over seven intervals that
all now agree.

**"The ORIGINAL reply stands" was false.** My comment said it; the loop
broke with the retry in hand, so what survived was the reply rewritten
under an instruction naming a contradiction — the more distorted of the
two, and one the reviewer had refused anyway. All five OVERRULED verdicts
in the corpus were correct diagnoses of contradictions that were then
committed. Fixed.

**The identity guard ran on one path in three.** Gated on `did_it`, which
is set for attempts only, so 37% of committed events came through
`starting_event` and `pending_progression` unchecked. A reviewer committed
*"Bo reads Ada's proposal, decides to accept it, and replies agreeing to
her terms"* through that path — `by` honestly naming Bo — before Bo's model
had been called once, and `choice_returned_to_its_owner` fired zero times
in eleven runs. Fixed.

**An incomplete run could still answer NO** when a step ceiling landed
exactly on the cutoff instant. Fixed: truncation forbids NO outright.

**The machinery headline is wrong again.** The hand count is **44%**, not
14%: `interface_mechanics.py` counts named people acting — including
`Aisha scans the signed lease and sends the email`, the event one YES cites
— and misses every near-duplicate. This metric has now been corrected once
and is still not trustworthy. **Do not quote 14%.** The honest statement is
that the *notification bookkeeping* is genuinely gone (baseline
`group_coordination` was 40+ of 56 events of phones buzzing; the new one is
26 events in which a reluctant host emerges) but ~22% of the record is the
same act re-committed under different words, which the exact-string dedupe
cannot catch.

### Still open, not fixed

- **CRITICAL — conditional intentions execute unconditionally and out of
  order.** `holiday_deposit`: "If confirmed, transfer £400" fired 30
  seconds *before* the check it was conditioned on, that check said the
  money had not arrived, and the £400 was never resolved. The turn's
  intentions are dispatched as independent world steps. This is my bug and
  it is the old failure relocated.
- **CRITICAL — the attention refusal deleted 12.6% of world answers**,
  including substantive acts the world prompt authorises. The power to
  delete a valid answer moved from the LLM into code rather than leaving.
- **HIGH — replay cannot detect mutation of the persisted ledger.** A
  reviewer rewrote every event description and terminal record and
  `reverify_replay.py` still reported `exact=True`, because it copies that
  boolean from a file beside the ledger and no semantic op has a kernel
  reducer. "11/11 replay exact" is therefore not re-derivable.
- **HIGH — the sender still learns recipient-side delivery**
  (`evidence_avoiding/e44`), and the test named for that guarantee is dead
  code that asserts nothing inside an `if` that is never true.
- **HIGH — near-duplicate suppression does not exist**, and the test
  certifying it passes because its run makes exactly one world call.
- **HIGH — no event carries a duration**, so actors are in two places at
  once; `feedback_deadline`'s YES rests on a self-contradicting record.
- **HIGH — a 55-turn no-op actor** in `cold_email` (185 calls, 2 events).
- **A disagreement I did not resolve.** Two reviewers argue the
  empty-queue rule overcorrects: the three refused runs lived 92%, 98.8%
  and 99.2% of their windows with every actor asked and declining, and two
  had their actors' post-deadline plans silently deleted. The directive
  states the rule as non-negotiable, so I honoured it and recorded the
  objection rather than overriding either. **This is the user's call.**

## 14. Recommendation

**DO NOT MERGE.** Four reviewers returned FAIL with 6 CRITICAL and 15 HIGH
findings between them. Five findings are repaired above; the rest are not.

**The frozen corpus is invalidated.** The repairs in §13 changed production
code after `37dccff`, so every number in §9 predates them and must not be
quoted as evidence for the current SHA. Per the directive, the candidate
batch is discarded and the corpus must be rerun from the beginning on
`25b7f05` before any completion claim. I have not done that rerun.

Two further reasons independent of the reviewers:

**Zero NO_AT_CUTOFF is honest, not good.** Every NO the merged runtime
produced was the empty-queue kind, and those cases are labelled
`incomplete_empty_queue` now, which is what they always were. But the
runtime therefore cannot presently carry a trajectory to its deadline, so
it cannot presently produce a *legitimate* NO either. Two of the three
incompletes stop within hours of their cutoff — `holiday_deposit` at
22:26 against a 22:59 deadline. Nothing yet brings a person back because a
deadline they know about is approaching; that was `known_deadline`, and
deleting it as dead vocabulary was right, but the gap it named is real and
still open.

**The completion conditions in the directive are not all met.** Met:
compiler frozen; one runtime path; all deterministic tests pass; no
scenario-specific path; empty queue always INCOMPLETE; NO_AT_CUTOFF
mechanically impossible before cutoff; delivery code-owned; machinery no
longer dominates; every consequence cites a cause; identity-enforced
choice ownership; replay exact with zero model calls; artifacts no longer
bloat the diff; every artifact from one frozen SHA. Not yet met: a
legitimate NO is unreachable in practice; `holiday_deposit` still spends
91 events and ends incomplete; and the reviewer verdicts in §13 are
outstanding.

A mix of PASS and FAIL is not complete, and neither is a runtime that can
only answer one way.
