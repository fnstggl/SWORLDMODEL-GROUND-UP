# ERRATA -- full-trace validation, 2026-08-04

> **UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION.** Everything in this
> artifact set is an uncalibrated one-shot simulation against a live
> model. Nothing here is a prediction about any real person.

**Dated 2026-08-04, recorded after an independent adversarial audit of the
frozen artifacts.**

This file corrects claims that the committed reports make and their own
committed ledgers disprove. It is written under one rule:

> **No original wording is deleted, softened, or rewritten.** Every
> corrected sentence is quoted here verbatim with its `file:line`, the
> ledger evidence that disproves it, the correction, and the root cause
> in the generator that produced it. The original sentence stays in place
> in the report, carrying a one-line inline marker pointing here. Where a
> judgment was unfavourable it stays exactly as written; only claims that
> the artifacts contradict are corrected.

The audit's own summary of this artifact set is recorded verbatim in
`.agent-run/DECISIONS.md` and is not edited by this file.

Scope of the corrections: **five report claims and one production
string.** No simulation was re-run for any of them; no frozen input was
edited; no recorded model output was altered. Three claims were also
fixed at the generator so they cannot be emitted again (E1, E4, E5), one
in the production engine (E3), and one in the validator (E2).

Errata ids `E1`-`E6` below map one-to-one onto the audit's own finding
ids, which are recorded in `.agent-run/DECISIONS.md` under
"Independent adversarial audit 2026-08-04".

**A note on the `file:line` references.** They are the line numbers the
audit reported, i.e. as of commit `421f6f90`. Adding the errata pointer
at the top of each report shifted every later line down by two, so in the
current files the same sentences are at `+2` (for example
`peter_supplied/UNDER_THE_HOOD_REPORT.md:966` is now line 968). The
original numbers are kept here because they are what the audit cited; the
sentences themselves are unchanged and carry inline markers.

| errata id | audit finding | finding | severity | where the wrong claim is | root cause fixed in |
|---|---|---|---|---|---|
| E1 | **F1** | reports claim the agency guard recorded zero interventions; it fired | HIGH | `peter_supplied/UNDER_THE_HOOD_REPORT.md:966,1003`; `peter_generated/UNDER_THE_HOOD_REPORT.md:1028,1067` | `experiments/full_trace_validation/report.py` |
| E2 | **F2** | "the historical cutoff was enforced mechanically at 3 stages" overstates coverage | HIGH | `a16z_richard_historical/UNDER_THE_HOOD_REPORT.md:5767`; `*/post_fix_rerun/PRE_VS_POST_FIX.md` | `experiments/full_trace_validation/cutoff.py`, `report_a16z.py`, `rerun.py` |
| E3 | **F3** | the production refusal reason states a fact the a16z run disproves | MEDIUM | `sworldmodel/outcomes/ranking.py` (superseded), and every committed `ranking_refusal.json` | `sworldmodel/outcomes/ranking.py` |
| E4 | **F4** | the one verbatim "determined-recipient" proof is a possessive case | MEDIUM | `a16z_richard_historical/post_fix_rerun/PRE_VS_POST_FIX.md:128` (pre-correction) | `experiments/full_trace_validation/runner_rerun_compare.py` |
| E5 | **F6** | 20 guard interventions attributed to defect D3; 19 are | LOW | `a16z_richard_historical/post_fix_rerun/PRE_VS_POST_FIX.md:28,32-36` (pre-correction) | `experiments/full_trace_validation/rerun.py`, `runner_rerun_compare.py` |
| E6 | **F8** | one committed README carried no uncalibrated-simulation banner | LOW | `settling_experiment/harness_shakedown/README.md` | banner added in place |

A seventh item, audit finding **F5** -- the agency guard's missing
`approve`/`authorize` verbs -- was a **code** defect rather than a report
claim. It is recorded in
`sworldmodel/backends/concordia_local/guard.py` (module docstring) and
proven by `tests/engine_baseline/test_agency_guard.py`; it is summarised
at the end of this file because it changes what a future run's guard
ledger will contain.

---

## E1 (HIGH) -- both Peter reports say the guard recorded zero interventions. It fired.

### Original wording, quoted verbatim and NOT deleted

`artifacts/full_trace_validation_20260804/peter_supplied/UNDER_THE_HOOD_REPORT.md:966`
and
`artifacts/full_trace_validation_20260804/peter_generated/UNDER_THE_HOOD_REPORT.md:1028`:

> No branch produced a self-serving outcome for the sender: no actor
> narrated a result it did not own, and the guard never needed to
> intervene (section 10).

`artifacts/full_trace_validation_20260804/peter_supplied/UNDER_THE_HOOD_REPORT.md:1003`
and
`artifacts/full_trace_validation_20260804/peter_generated/UNDER_THE_HOOD_REPORT.md:1067`:

> **No actor decision was made for another actor.** The agency guard is
> enabled and recorded zero interventions in this scenario, and
> inspection of the committed stream shows why: no actor's turn asserted
> the other's choice as an accomplished fact. The recipient's acceptance
> is authored by the recipient's own model; the evaluator's attribution
> anchor requires exactly that.

### The ledger evidence that disproves it

`peter_supplied/branches/user_001/guard_ledger.jsonl`, step 3, verbatim:

```json
{"step": 3, "intervened": true,
 "explanation": "the minimum agency guard detected event text asserting
   another actor's voluntary decision and rewrote it into
   attempt-plus-availability form; affected actors: Peter Thiel"}
```

Counted across the committed ledgers:

| scenario | branch | rows | `intervened: true` |
|---|---|---|---|
| `peter_supplied` | `user_001` | 4 | **1** (step 3) |
| `peter_supplied` | `user_002` | 4 | 0 |
| `peter_supplied` | `user_003` | 4 | 0 |
| `peter_generated` | `gen_001` | 4 | **1** (step 3) |
| `peter_generated` | `gen_002` | 4 | **1** (step 3) |
| `peter_generated` | `gen_003` | 4 | 0 |

The same report files already render the truth about 500 lines earlier,
from the same run's step ledger:

- `peter_supplied/UNDER_THE_HOOD_REPORT.md:467` -- ``**10. Guard.** intervened = `True` -- the minimum agency guard detected event text asserting another actor's voluntary decision and rewrote it into attempt-plus-availability form; affected actors: Peter Thiel``
- `peter_generated/UNDER_THE_HOOD_REPORT.md:534` and `:707` -- the same line, twice.

### Correction

The agency guard **DID** intervene in both Peter scenarios: once in
`peter_supplied` (branch `user_001`, step 3) and twice in
`peter_generated` (branches `gen_001` and `gen_002`, step 3). The claim
"recorded zero interventions" is false for both scenarios, and the claim
"the guard never needed to intervene" is false for both.

What survives of the surrounding paragraph: the recipient's acceptance
*is* authored by the recipient's own model, and the evaluator's
attribution anchor does require that. The guard firing does not
contradict either -- it is the mechanism that made them true in the
branches where it fired.

### The rewrite destroyed content, and that is the more important half

The `peter_supplied` `user_001` step-3 intervention removed the ACTIVE
actor's own text. Verbatim from the guard ledger and the step ledger:

**Before the guard** (the actor's own committed turn, untruncated, from
`peter_supplied/branches/user_001/step_ledger.jsonl` step 3):

> Beckett Zahedi reads Peter Thiel's reply, then immediately compiles the
> replay logs and failure cases into a single, clearly-labeled archive
> [...]

**After the guard** (`final_committed_event`, verbatim):

> [observation] [event] Event: Putative event to resolve:  Beckett
> Zahedi: Beckett Zahedi reads. Thursday works for me—I'll send a
> calendar invite for 20 minutes." Peter Thiel is now able to observe
> this and to respond in their own turn.

The active actor's own sentence was cut at `reads.` and what followed was
deleted.

**Classification, stated precisely because the two classes are easy to
confuse:** this is the **possessive-nominalization** class
(`reads <Name>'s reply`), which the guard's own module docstring
documents as a *deliberate* stateless conservatism -- without history, a
reference to a decision that really happened is indistinguishable from an
invented one. It is **NOT** the determined-recipient (D3) class that the
2026-08-04 fix batch closed. The current guard still rewrites this
sentence, by design. See E4 for what happens when the two classes are
conflated.

### Root cause

`experiments/full_trace_validation/report.py`. Sections 15 and 18 emitted
those two sentences as **literal strings**, computed from nothing at all,
while section 10 rendered `intervened` per step from the ledger. A
summary about a measurement was not derived from that measurement.

Fixed: `report.py` now loads `branches/<candidate>/guard_ledger.jsonl`
into `ScenarioArtifacts.guards`, and every guard sentence in the report
is produced by `report.guard_activity()` / `guard_activity_sentence()`
from that ledger cross-checked against the step ledger. A scenario whose
ledger contains an intervention cannot reach the "zero" wording -- the
words are not on that branch of the function. A scenario with no guard
ledger at all is reported as *not measured*, never as zero.

Regression tests (`tests/experiment_harness/test_audit_closeout.py`):

- `test_a_fired_guard_ledger_can_never_render_a_zero_intervention_claim`
- `test_a_silent_guard_ledger_still_renders_the_zero_claim`
- `test_an_absent_guard_ledger_is_not_reported_as_zero`
- `test_committed_reports_that_carry_the_wrong_claim_carry_the_errata`

The committed reports are **not** regenerated: they are the record of
what was published. Each wrong sentence now carries an inline
`[ERRATA E1]` marker and each report links this file at the top.

---

## E2 (HIGH) -- a post-cutoff sentence reached the a16z compiler prompt, and "enforced at 3 stages" overstated the coverage

### Original wording, quoted verbatim and NOT deleted

`artifacts/full_trace_validation_20260804/a16z_richard_historical/UNDER_THE_HOOD_REPORT.md:5767`:

> 3. The historical cutoff was enforced mechanically rather than
> promised, at 3 stages, with a canary that the validator rejects.

`artifacts/full_trace_validation_20260804/a16z_richard_historical/post_fix_rerun/PRE_VS_POST_FIX.md` (pre-correction):

> The counterfactual is set before 2025-07-01, so the boundary is
> enforced mechanically at three stages plus a canary the validator must
> reject.

### The evidence that disproves it

`a16z_richard_historical/compiler/call_1_prompt.txt:136` contains, inside
the `USER-PROVIDED CONTEXT:` block:

> Do not include his later a16z employment or later a16z work.

That sentence asserts the post-cutoff **outcome** of the very
counterfactual being simulated: it presupposes that a16z employment
exists. It passed `pre_compile`, `pre_simulation` and `post_run_prompts`,
all three of which reported `clean: true`.

Origin: the sentence is **USER-SUPPLIED**, not engine-generated. It is in
`experiments/full_trace_validation/data/a16z_problem.json`, field
`relevant_context`. The harness carried the user's own context verbatim
into the compiler prompt, which is the designed behaviour; the defect is
that the validator did not stop it.

Why the validator missed it: its phrase arm had exactly one pattern for
this family,
`\bhis\s+(?:role|job|position|work)\s+at\s+a16z\b`, which fixes the word
order to `<possessive> <noun> at a16z`. The supplied sentence uses the
adjectival ordering `<possessive> later a16z <noun>`. The date arm was
never relevant: there is no date-shaped token in the sentence.

### Correction

Replace "enforced mechanically ... at 3 stages" with:

> The historical cutoff **check ran** mechanically rather than being
> promised, at 3 stages, over the real bytes, with a canary the validator
> rejects. That is a statement about the check running, **not** about its
> coverage. Enforcement is only as wide as the validator's arms, and one
> user-supplied sentence passed all three stages because the phrase arm
> lacked its word order.

Specifically:

- **what was covered:** every enforced surface was scanned with both arms
  over real bytes at three stages; the canary is rejected; the compiled
  world, base plan, candidates and branch-input diff are clean under both
  the old and the widened arms.
- **what was NOT covered:** the possessive/adjectival orderings of
  `later a16z <noun>`. One sentence in that family was present in the
  user-supplied context and passed.
- **an additional scope edge found while re-scanning:** the enforced
  `pre_compile` surfaces are the *harness-supplied inputs* (problem,
  evidence, question, context, package, scope note), not the fully
  *assembled* compiler prompt. The assembled prompt additionally contains
  the compiler's own fixed instruction template, whose illustrative
  deadline-arithmetic example carries the dates `2026-07-15` and
  `2026-09-13`. Those are template examples that make no claim about this
  counterfactual, but they are post-cutoff date tokens in a prompt
  byte-stream that no stage scanned. Disclosed, not repaired.

### It did NOT propagate -- independently re-verified

Every committed surface of both a16z runs was re-scanned **individually**
(not flattened per branch) with the widened arms:

| run | actor + GM prompts scanned | prompt violations | model responses scanned | response violations |
|---|---|---|---|---|
| pre-fix run | **360** | **0** | **180** | **0** |
| post-fix re-run | **360** | **0** | **180** | **0** |

The only surfaces carrying the sentence are the ones that echo the user's
own `relevant_context` verbatim: `decision_problem.json`,
`adapter/adapter_sidecar.json`, the two `compiler/call_*_prompt.txt`
files, and (pre-fix) `recommendation_report.json`. `adapter/adapted_world.json`
and `adapter/base_plan.json` are clean in both runs, so the sentence did
not survive compilation into the simulated world. No actor and no game
master ever saw it.

Full numbers, per-surface findings and the method are recorded in
`a16z_richard_historical/CUTOFF_SCOPE_CORRECTION.json`, which is
re-derivable from the committed files by
`python -m experiments.full_trace_validation.cutoff_scope`.

### Root cause

`experiments/full_trace_validation/cutoff.py`. The phrase arm's pattern
set is now widened to cover the family in both orderings, restricted to
completed-tenure nouns (`employment|work|role|job|position|tenure|career|
title|stint`) behind a possessive or a `later`/`subsequent`/`eventual`
modifier. Nouns that are the *subject* of the simulation (`hire`,
`hiring`, `offer`, `appointment`, `decision`) are deliberately excluded
so prospective and conditional wording still passes.

### The corrected validator, applied retroactively, REFUSES the frozen input

Stated without softening, because it is the honest characterization of
what this artifact set contains:

> **Applied to the frozen a16z `DecisionProblem` as it was actually run,
> the corrected validator refuses it.** `cutoff.assert_clean` raises
> `HistoricalCutoffViolation` with three findings -- `his later a16z
> employment`, `later a16z employment`, `later a16z work` -- all from the
> one user-supplied sentence. The a16z pre-simulation gate therefore
> returns exit 6 and will not run the scenario end to end.
>
> **The completed run consequently carries a disclosed, non-propagating
> post-cutoff assertion in its compiler-facing context surface.** It is
> disclosed here and in `CUTOFF_SCOPE_CORRECTION.json`; it is
> non-propagating by the 360-prompt / 180-response re-scan above and by
> the clean compiled world; and it is not repaired, because repairing it
> would mean editing the user's own frozen input.

Neither the gate nor the pattern is relaxed to make this go away:

- the widened patterns are **not** weakened;
- `experiments/full_trace_validation/data/a16z_problem.json` is **not**
  edited, sanitized, or re-authored -- it is the user's own text and the
  frozen input of a completed experiment;
- the tests that previously asserted "the frozen decision problem is
  cutoff-clean" now assert the **specific expected violation** instead
  (`tests/experiment_harness/test_a16z_cutoff.py::
  test_the_frozen_decision_problem_carries_exactly_the_one_known_leak`),
  pinned to that exact matched-text set so the leak can never silently
  disappear, and a companion test proves the known sentence is the ONLY
  thing wrong by removing it in memory and re-scanning clean;
- both directions are asserted: the input surface's violation is expected
  and pinned, while the propagation surfaces (every actor prompt, every
  game-master prompt, every model response, the compiled world, the base
  plan, the branch-input diff, the candidates) must stay clean
  (`test_the_leak_did_not_reach_any_actor_or_game_master_surface`,
  `test_no_committed_a16z_artifact_carries_post_cutoff_material`);
- the end-to-end plumbing tests in
  `tests/experiment_harness/test_a16z_scenario.py` -- which exercise the
  harness machinery, not the frozen input's cutoff status -- drive the
  runner with an in-memory copy of the problem that has the one known
  sentence removed, and assert up front that the sentence is still
  present in the frozen file. The gate is untouched: delete that fixture
  and those tests refuse exactly as a real run now would.

The a16z simulation was **not** re-run: the leak is disclosed, it did not
propagate, and re-running would replace frozen evidence with new
evidence.

Regression tests (`tests/experiment_harness/test_audit_closeout.py`):
`test_the_leaked_sentence_is_now_rejected_by_the_phrase_arm`,
`test_the_superseded_pattern_really_could_not_match_it`,
`test_the_widened_family_is_rejected`,
`test_the_widening_did_not_start_blocking_legitimate_wording`,
`test_the_scope_correction_records_the_re_verified_numbers`,
`test_the_scope_correction_is_reproducible_from_the_committed_files`.
`tests/experiment_harness/test_a16z_cutoff.py` additionally pins the
frozen problem's ONE known violation exactly, so any *second* one fails.

---

## E3 (MEDIUM) -- the production refusal reason states a fact the a16z run disproves

### Original wording, quoted verbatim and NOT deleted

`sworldmodel/outcomes/ranking.py` (superseded at this commit; still the
verbatim `reason` string inside every committed
`*/ranking_refusal.json` and quoted in every
`*/post_fix_rerun/PRE_VS_POST_FIX.md` "Ranking" section):

```
refusing to rank: not one of the 6 measured branches delivered its intervention to any actor other than the insertion actor, so every branch ran the counterfactual's independent variable at the same (undelivered) value and the measured differences cannot have been caused by the candidates. A winner computed from these branches would be an artifact of model sampling on identical downstream context, not a comparison. [...]
```

The two clauses that are false are
`every branch ran the counterfactual's independent variable at the same (undelivered) value`
and
`an artifact of model sampling on identical downstream context`.

### The evidence that disproves it

In the frozen a16z run the insertion actor is `new_media_hiring_lead`.
The independent variable (annual base salary) **did** vary in a
NON-insertion actor's own prompt, because the hiring lead restated it in
its own words and the game master routed that turn onward. From
`a16z_richard_historical/all_llm_calls.jsonl`, both calls to the
`People and Compensation Partner` at step 4:

- call `a16z_richard_historical-000067` (branch `br_31985e007dc3038a`):
  > [observation] Putative event to resolve:  New Media Hiring Lead: New
  > Media Hiring Lead reviews the fixed package details and drafts a
  > formal offer for Richard Zheng at **$150,000** base salary, then
  > sends it to the People and Compensation Partner for approval [...]
- call `a16z_richard_historical-000157` (branch `br_8e3417c31c45ffa6`):
  > [observation] Putative event to resolve:  New Media Hiring Lead: New
  > Media Hiring Lead reviews the fixed package details and drafts the
  > offer for Richard Zheng at **$300,000** base salary [...]

So the independent variable did not hold "the same (undelivered) value"
everywhere, and the downstream context was not "identical". The delivery
check was still right: it searches for **distinctive candidate
fragments**, and no candidate's own text reached any non-insertion actor.
An uncontrolled paraphrase is not the candidate.

### Correction

The **refusal decision is correct and unchanged.** Only its justification
was wrong. The corrected production string states exactly what was
measured:

> refusing to rank: not one of the N measured branches delivered its
> intervention to any actor other than the insertion actor. That is
> exactly and only what was measured: no distinctive fragment of any
> branch's candidate was found in any actor's own context except the
> insertion actor's. It is NOT a finding that the branches were identical
> downstream, and NOT a finding that the counterfactual's independent
> variable held the same value everywhere -- the insertion actor is free
> to restate the variable in its own words, and such a paraphrase can
> reach other actors without carrying any distinctive candidate fragment
> with it. The narrower conclusion is the one that blocks a ranking: no
> measured difference between these branches can be attributed to the
> candidates, because no candidate itself reached an actor downstream of
> the insertion. [...]

### Why the committed `ranking_refusal.json` files are NOT regenerated

The `reason` field of a `ranking_refusal.json` is a **record of what the
engine emitted during a frozen run**, not a derived summary. Re-deriving
it with today's string would make the artifact claim the run said
something it did not say -- the same class of error this errata exists to
correct. The eleven committed refusal files therefore keep the superseded
wording, and this entry is their correction. The same applies to the
verbatim quotation of that string in each `PRE_VS_POST_FIX.md`.

### Root cause

`sworldmodel/outcomes/ranking.py::_refuse_when_nothing_was_delivered`
(message), `InterventionNotDeliveredError` (docstring), the module
docstring's delivery-gate paragraph, and the experiment-side
`experiments/full_trace_validation/report.py::_refused_report`, all of
which asserted a conclusion wider than the measurement supports.

Regression tests (`tests/experiment_harness/test_audit_closeout.py`):
`test_the_refusal_reason_no_longer_claims_the_variable_never_varied`,
`test_the_refusal_reason_states_exactly_what_was_measured`,
`test_the_a16z_counterexample_is_still_true_in_the_frozen_artifacts`.

---

## E4 (MEDIUM) -- the one verbatim proof of the D3 fix is a possessive case the fix does not cover

### Original wording, quoted verbatim and NOT deleted

`a16z_richard_historical/post_fix_rerun/PRE_VS_POST_FIX.md:128`
(pre-correction):

> A pre-fix determined-recipient rewrite, verbatim from the guard ledger:
> `Putative event to resolve:  New Media Hiring Lead: New Media Hiring
> Lead reviews the. People and Compensation Partner is` -- the sentence
> was cut at the determiner and the active actor's own content after it
> was deleted.

And, from the same document's notes (pre-correction):

> Guard interventions split by class -- pre-fix: 2 determined-recipient
> (the class D3 closed), 0 possessive nominalization [...], 18
> unclassifiable from the 120-character excerpt the runner records, 0
> other, 20 total.

### The evidence that disproves it

That quoted record is `a16z_richard_historical/branches/user_001/guard_ledger.jsonl`
step 11. Its untruncated pre-guard text, from the same branch's
`step_ledger.jsonl` step 11 `actor_raw_response`:

> New Media Hiring Lead reviews **the People and Compensation Partner's
> latest reply**, then sends a concise confirmation: "Got it—no offer to
> Richard Zheng until after July 10; [...]"

`Partner's ... reply` is the **possessive nominalization** class, not the
determined-recipient object slot. Replaying that exact text through the
CURRENT (post-D3-fix) guard confirms it: the guard **still rewrites it**.
The record only looked like a D3 case because its *output* ends in
`reviews the.`, and the classifier tested the output signature before the
input signature.

The genuine determined-recipient example in the same run is
`branches/user_003/guard_ledger.jsonl` step 15:

> Putative event to resolve:  Richard Zheng: Richard Zheng sends a brief,
> direct email to the. New Media Strategy Partner

### Correction

- The verbatim example published as the proof of the class D3 closed is
  a **possessive** case (`user_001` step 11) that the current guard still
  rewrites, by design.
- The genuine D3 example is `user_003` step 15.
- The class split published as "2 determined-recipient / 0 possessive /
  18 unclassifiable" is wrong in all three numbers. The correct split,
  computed from the untruncated pre-guard text, is **19
  determined-recipient / 1 possessive / 0 unclassifiable**.

### Root cause

`experiments/full_trace_validation/runner_rerun_compare.py::_guard_class_census`
tested the dangling-determiner pattern (an *output* property) before the
possessive test (an *input* property). The two are not mutually
exclusive: a possessive rewrite whose removal span begins just after a
determiner also ends in `the.`.

Fixed three ways: the possessive test now runs FIRST; the census
reconstructs the UNTRUNCATED pre-guard text from the step ledger
(`_full_pre_guard_texts`) instead of relying on the runner's
120-character excerpt, which had hidden the deciding word in 18 of 20
records; and where the roster is available the D3 test is a **replay**
through the current guard rather than a signature guess.

The comparison documents ARE regenerated for this, because they are
derived analysis over unchanged inputs rather than a record of what a run
emitted; the pre-correction wording is preserved verbatim above and in
git history.

Regression tests (`tests/experiment_harness/test_audit_closeout.py`):
`test_a_possessive_whose_rewrite_ends_in_a_determiner_is_possessive`,
`test_a_genuine_determined_recipient_record_still_lands_in_D3`,
`test_the_census_uses_the_untruncated_text_when_it_is_available`.

---

## E5 (LOW) -- 20 guard interventions attributed to defect D3; 19 are

### Original wording, quoted verbatim and NOT deleted

`a16z_richard_historical/post_fix_rerun/PRE_VS_POST_FIX.md:28,32-36`
(pre-correction):

> ## Agency-guard interventions (defect D3)
>
> The determiner false positive truncated a sentence at the determiner
> and deleted the ACTIVE actor's own quoted content whenever it addressed
> a determined recipient (`sends a message to THE <role name>: "..."`).
>
> - pre-fix: **20** guard interventions
> - post-fix: **0** guard interventions
> - change: **-20**

### The evidence that disproves it

Replaying each of the 20 pre-fix interventions' reconstructed pre-guard
text through the current guard:

| outcome | count |
|---|---|
| passes the current guard byte-identically -- explained by the D3 fix | **19** |
| still rewritten by the current guard -- NOT attributable to D3 | **1** (`user_001` step 11, the possessive case of E4) |
| not replayable (no recorded raw response) | 0 |

### Correction

19 of the 20 pre-fix interventions are explained by the D3 fix. The
twentieth is the possessive-nominalization class, which the fix did not
touch and was not supposed to; its absence from the re-run is live
sampling, not the fix. A count falling from 20 to 0 across two live runs
is a count, not an attribution.

### Root cause

`experiments/full_trace_validation/rerun.py::build_comparison` published
the intervention count under a heading naming defect D3, which reads as
an attribution. Fixed: the heading no longer names D3, the section states
in bold that "that change is a count, not an attribution", and the
document now carries a replay-derived attribution
(`_d3_replay_attribution`) alongside the count.

Regression tests (`tests/experiment_harness/test_audit_closeout.py`):
`test_the_a16z_d3_attribution_is_replayed_not_subtracted`,
`test_the_committed_comparison_publishes_the_replayed_attribution`.

---

## E6 (LOW) -- a committed README without the uncalibrated-simulation banner

`settling_experiment/harness_shakedown/README.md` was the one committed
README in this artifact set that did not carry the
`UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION` banner. The banner is
added in place, dated, with the reason. No other content of that file is
changed.

Regression test:
`tests/experiment_harness/test_audit_closeout.py::test_every_committed_experiment_readme_carries_the_banner`,
which walks every `README.md` under this artifact root.

---

## Not an errata item, but it changes what future guard ledgers contain

The audit demonstrated, with an executed control against both the pre-fix
and post-fix guard, that the minimum agency guard had **no word for
granting permission**:

> New Media Hiring Lead prepares terms; the People and Compensation
> Partner approves them.

passed the guard byte-identically. In a scenario about compensation
approval that is the most load-bearing proxy attribution the scenario
invites.

`approve`/`approves`/`approved` and `authorize`/`authorizes`/`authorized`
are now in the guard's finite act-form set, with the matching participles
and gerunds so that `has approved` and `is approving` behave identically.
The act *nouns* (`approval`, `authorization`) are deliberately NOT added
and are listed as a documented residual in the guard's module docstring.

This does **not** change any committed artifact: no run is re-executed.
It changes what a future run's guard ledger will contain, which is why it
is recorded here beside the corrections.

Proof: `tests/engine_baseline/test_agency_guard.py` --
`test_the_reported_f5_control_sentence_is_caught`,
`test_approval_granted_for_another_actor_is_rewritten`,
`test_approval_in_an_auxiliary_chain_is_caught`,
`test_an_actor_approving_on_its_own_turn_still_passes`,
`test_approval_nearby_shapes_are_not_over_blocked`,
`test_approve_and_authorize_are_in_all_three_inflection_sets`,
`test_the_approval_verbs_do_not_disturb_the_clean_control_run`.

---

## What this errata deliberately does NOT change

- **No realism judgment.** Every assessment in each report's sections 15,
  16 and 18 about how the model behaved -- the verbatim self-repetition,
  the invented calendar facts, the uniformly warm recipient, the 6/6
  `no_explicit_decline` rate, the game master's wrong awareness rulings --
  stands exactly as written. The audit judged the machine-generated layer
  sound and the hand-written summary layer wrong in two places; only
  those two places, and the derived-analysis errors they exposed, are
  corrected.
- **No frozen input**, no recorded model output, no recorded call ledger,
  no freeze manifest, no `ranking_refusal.json`, and no
  `UNDER_THE_HOOD_REPORT.md` sentence.
- **No re-run.** The a16z simulation in particular is not re-executed:
  its cutoff leak is disclosed and non-propagating, and re-running would
  replace frozen evidence.
