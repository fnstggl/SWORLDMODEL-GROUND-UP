# Cross-Scenario Findings

**UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION**

Three live-model decision experiments run through the complete production
path, with every visible model call recorded. Model: `deepseek-chat`
requested; provider served `deepseek-v4-flash` throughout (recorded in each
`provider_probe.json`). Nothing here predicts Peter Thiel, a16z, or Richard
Zheng. Read `ERRATA.md` first — it corrects two claims the reports made that
their own ledgers disprove.

Scope note: this document answers the thirteen required cross-scenario
questions. Evidence is cited by path; every number was either computed by the
harness and independently recomputed by the adversarial auditor, or computed
by the auditor from raw ledgers. Where the two disagreed, the raw ledger wins
and the disagreement is stated.

---

## 1. Did the production compiler create usable worlds from these requests?

**Yes — and both worlds carry the same structural defect.** The compiler
produced a runnable 2-actor world (Beckett Zahedi, Peter Thiel) and a runnable
5-actor world (the a16z committee plus Richard Zheng), each with cast, private
context, shared context, starting events and an insertion boundary that the
adapter and planner accepted without repair.

Two things it got right are worth stating, because they are the behaviours a
compiler is most tempted to fake: it **refused to invent** the private facts
the evidence manifest classifies UNKNOWN (calendar, inbox behaviour, internal
opinions, salary bands), and in the a16z run its **deadline guard correctly
rejected three malformed inputs** — the harness's scope note said "on or before
1 July 2025", which the production guard read as a narrower decision deadline.
The production guard was right and the experiment input was wrong; the aborted
attempt is kept at `a16z_richard_historical/superseded/`.

The defect: both worlds describe a message-send event visible only to its
sender (`peter_supplied/compiler/final_scene_manifest.json:13-21`,
`visible_to: ["Beckett Zahedi"]`). In an engine where `visible_to` is the only
mechanism that puts a pre-start fact into an actor's context, that produces a
world where the send happened and the recipient can never learn of it. It is
not an LLM slip: `compiler/scene_prompts.py:127-128` ships that exact shape as
a literal exemplar, so it is systematic across cold-outreach worlds. Nothing
in the compiler, adapter or planner validated the coherence. This pass adds a
recorded warning (`heuristic_visibility_incoherence`), not a refusal.

## 2. Did the adapter preserve all relevant compiler information?

**Yes — verified, and it was the leading suspect that got eliminated.** The
root-cause investigation compared `adapter/adapted_world.json` against
`compiler/final_scene_manifest.json` field by field and found the mapping
faithful, including the `visible_to` sets that caused the delivery failure
(`existing_compiler_adapter.py:259-290`). A controlled probe (variant B)
widened visibility at the adapter layer and delivered **zero** additional
candidate text, which is what eliminated "adapter mapping loss" as a
sufficient cause. The auditor independently confirmed the four adapter files
are byte-identical across the two Peter scenarios and both re-runs.

## 3. Did Concordia actors receive the correct private and shared information?

**Yes.** Computed, not asserted, and then recomputed independently by the
auditor from `adapter/base_plan.json` private blocks against every raw prompt:

| run | naive leak count | distinctive leak count |
|---|---|---|
| Peter (both scenarios, pre- and post-fix) | 0 | **0** |
| a16z (both runs) | 36 | **0** |

The 36 are an artefact worth understanding: they are the New Media Strategy
Partner and the Creative Production Lead tripping each other's *byte-identical
compiler boilerplate* ("Advisory role in the hiring process.", etc.). No actor
ever saw another actor's distinctive private text. The naive check
over-reports on any cast that shares boilerplate; the distinctive-content
refinement is the correct reading and has been promoted into production
(`sworldmodel/counterfactuals/delivery.py:154`).

## 4. Did the Game Master resolve attempts without deciding other actors' choices?

**Yes on the core claim — with two real defects around it, both now fixed.**
The auditor scanned every committed event in all six runs for `<other actor>
<voluntary verb>` where that actor is not the active one, excluding the
guard's own availability sentence: **0 hits, all six runs.** No committed event
has the GM or another actor deciding someone's voluntary act.

The defects were in the machinery protecting that property, not in the
property itself:

- **The guard was destroying legitimate content.** A determiner before a
  roster name in the recipient slot defeated the object-position exemption:
  `... sends a message to the People and Compensation Partner: "$150,000"`
  became `... sends a message to the.` with the quoted content deleted. 20/20
  interventions in the a16z run were this false positive — 4,194 characters of
  actor-authored text removed. All 20 were false positives on reading the
  originals; **no true positive was ever lost**. Fixed; the post-fix a16z run
  records 0 interventions, 19 of the 20 explained by replay through the fixed
  guard and 1 by a possessive case the fix deliberately does not cover.
- **The GM's observer answers were being dropped silently.** A free-text name
  that did not match the roster created a phantom queue key and the event
  vanished with no error — `add("@PeterThiel")` then `get_and_clear("Peter
  Thiel")` returns `[]`. This killed `gen_003`, the one branch whose sender
  *did* enact its candidate. Fixed at our seam (zero upstream patches); the
  a16z re-run now **records 39 unresolved observer names** (24× `"Hiring
  Lead"`, 15× `"hiring lead"`) where the pre-fix run had no trace at all. The
  fix makes the loss visible; it does not guess a recipient.

One gap the auditor found in the negative space, also now closed: the guard's
protected-verb list had **no `approve` or `authorize`** — in a scenario about
compensation approval, the most load-bearing proxy attribution available
(`"the People and Compensation Partner approves them"` narrated by the hiring
lead) passed untouched. It never materialised in the runs, but zero
interventions was consistent with a working guard *and* with a blind one.

## 5. Did the evaluator count only events that actually happened?

**Yes.** All 68 metric citations were re-checked by the auditor: every
`event:` id exists in that branch's own `committed_events.jsonl`; every
`state:` key is the declared scan bound; every cited event text appears
verbatim in the committed trace; every committed event's own `sha256`
verifies. All 17 event citations carry the resolved-turn anchor **and** a
leading `Name:` naming the subject actor — **0 anchored to a game master, a
narrator, or another actor**. Delivery, opening, GM narration and paraphrase
cannot satisfy a metric by construction.

One declared exception, disclosed loudly by the report that uses it:
`salary_savings_vs_300k` is **code-owned** from the declared candidate, cites
the scan bound rather than an event, and the a16z report says of the resulting
ranking that it "would have been the winner without running the simulation at
all."

A measurement honesty note that belongs here: the Peter evaluator's frozen
patterns **miss** real acceptance phrasings (`"I'll give you 20 minutes on
Thursday"`, `"Thursday works"`). The harness did **not** retune the evaluator
after seeing the outputs — that would be tuning to the outcome. It published a
labelled second reading in `measurement_audit.json` instead, which disagrees
with the declared reading on 2 of 3 branches per scenario.

## 6. Did the candidate generator work?

**Mechanically, yes.** One live call, raw response preserved byte-identically
in `generator_raw_response.txt` and in the ledger, hash verified, three
candidates parsed, `rejected_fields_or_parse_errors: null`, no supplied-candidate
text anywhere in the generator prompt. The auditor verified all three generated
`action` and `summary` strings appear verbatim at the matching index in the
single recorded response — nothing hand-authored.

**The current implementation performs one-shot generation, not iterative
best-action search.** No candidate search exists in this system.

## 7. Were its candidates meaningfully distinct?

**Yes in wording, but they differ in *kind* from the supplied set, and that
has a measurement consequence nobody had noticed.** Pairwise action Jaccard:
generated 0.14–0.38 (slightly *more* internally distinct than the supplied
0.29–0.30), cross-set 0.06–0.12.

But the supplied candidates are finished email *bodies*, while the generated
ones are procedural *instructions* ("Draft and send an email… ensuring the body
is 45-85 words"). One generated candidate switches channel entirely to a public
post plus DM — which no declared constraint forbids. The consequence, found by
the auditor: each generated candidate yields **1** testable distinctive
fragment against the supplied set's **5–6**, so scenario 2's delivery check
runs at roughly **one-fifth the statistical power** of scenario 1's. Both raw
counts are printed; the asymmetry was never discussed until now.

## 8. Did the supplied and generated Peter candidates produce materially different trajectories?

**No. Neither reached the recipient at all.** This is the headline finding of
the whole validation.

Across all six branches (three supplied + three generated) the recipient's
first-turn prompt has **exactly one distinct hash**. Zero candidate fragments,
and zero of 11–28 sliding 30-character windows of the candidate text, appear
in any recipient prompt — verified in four separate runs, recomputed by the
auditor from raw ledgers rather than from the harness's own check.

So the pre-fix "winners" (`user_002`, `gen_001`) were **live-model sampling
variation on one identical prompt**, not evidence that any email outperformed
another. The engine now refuses to rank in this state.

**Why**, established by a five-variant deterministic probe plus a two-arm live
experiment: the intervention is *suggested to* the insertion actor, never
*enacted in* the world (`branch.py:187-208` is the only write path and it
actively refuses any wider effect). It propagates only if the sender's own
model chooses to restate it. Every accepted test suite scripts the sender to
**echo** the candidate — `cf_helpers.py:137-141` says so in its own docstring —
so this dependency had never been exercised with a free-choice sender.

The live settling experiment then refuted the cheap fix. Removing the
pre-narrated send **did** change behaviour (sender waits 3/3 in Arm A, sends
3/3 in Arm B, content-blind overlap rising 0.085 → 0.153) but verbatim
enactment stayed at **0/3 in both arms**: the sender writes its own message.
Compiler hygiene is worth having and is not the fix.

## 9. Did the team simulation preserve authority and private information?

**Private information: yes** (0 distinctive leaks across 5 actors, §3).
**Authority: partially, and the deviations are recorded rather than smoothed.**

- No actor ever decided another's voluntary act in a committed event (§4).
- But in the two branches that completed the authority chain, **approval
  followed issuance** — the compensation partner approved after the offer was
  already out, inverting the declared model. The declared model was never
  enforced by construction; it was only described in context.
- Richard produced 0 acceptances, 0 refusals, 5 counter-shaped turns.
- The guard could not have caught the approval-theft shape had it occurred
  (§4, F5), so "zero interventions" was weaker evidence than it looked. Now
  fixed.

## 10. Did salary alone remain isolated across the hiring branches?

**Yes — independently reconstructed.** The auditor rebuilt each branch plan
from `base_plan.json` plus the recorded inserted line and re-hashed it: all six
unmasked hashes match the recorded ones exactly (proving the recorded plans
really are base+insert), and after masking currency figures the five offer
plans **collapse to a single hash** and compare equal pairwise across the whole
tree. The only path that differs from base is
`initial_observations.new_media_hiring_lead[2]`. No other field — title, scope,
reporting line, benefits, equity, autonomy, resources, start expectations —
varies anywhere.

## 11. Which outputs looked like grounded behavioural reasoning?

The strongest cases are constraint-following that tracks the actor's **private**
context rather than the genre. Verbatim, Arm B rep 2:

> Beckett Zahedi reviews the draft one more time, tightens the subject line to
> "Aurelius: 7.24× GPU goodput/$ **(replay only, not prod-validated)**" and the
> opening line to "**I'm not asking for money—I want your criticism**," then
> sends the email…

Both edits satisfy private constraints the actor actually held ("must not be
represented as production-proven"; "wants criticism… not an immediate
investment") and **neither phrase is in the candidate text**. Similarly, the
recipient in `peter_supplied/user_001`:

> "Send me the replay logs and the failure cases. **I'll give you 20 minutes on
> Thursday if the data holds up.**"

The condition attaches to the specific epistemic weakness of the pitch — the
replay-vs-production gap — rather than to generic caution. That is responsive.

## 12. Which outputs looked like sophisticated role-play?

**Quantitatively dominant.** In the a16z run, **34% of actor turns (31 of 90)
pre-fix and 40% (36 of 90) post-fix are exact duplicates of a previous turn by
the same actor in the same branch** — the model re-emitting text that was fed
back as an observation. One Peter recipient turn appears at committed rows 3
and 5 byte-for-byte, and the evaluator cites **the same string twice** as its
evidence for `call_agreed`.

Alongside that: invented facts in classified-UNKNOWN territory —

> He schedules the 20-minute call for the following week, blocking it on his
> calendar as "Aurelius critique."

— where the compiler correctly refused to invent calendar availability and the
actor model invented it at run time. `no_explicit_decline` is `True` in **6/6**
branches: a cold email from an unknown 17-year-old producing a 6/6 engagement
rate is the assistant-helpfulness prior, not a base rate. The a16z committee's
first turns cluster at 0.18–0.54 pairwise Jaccard in one "I need to see the
full package and benchmarking before I can approve" register.

One measurement subtlety worth preserving: the a16z run found 7 repeated
cross-actor n-grams and, before calling them model register, **split them by
author** — all 7 were *engine*-authored (the guard's availability sentence),
**0 model-authored**. Counting them would have been a false finding.

Every report states these role-play signatures about itself in its own §16.

## 13. What exact realism work should come next?

Ordered by what the evidence actually supports, not by ambition.

1. **Decide the intervention semantics — enacted or suggested.** This is the
   blocker for every counterfactual claim this system might make, and it is a
   *product* decision with two valid answers, not a bug to be patched. Today an
   intervention is a private suggestion the treated actor may ignore, so the
   independent variable can vanish before it reaches anyone. Making it an
   enacted committed event authored by the insertion actor (with a code-owned
   declared audience) is the only remedy that survives measurement — but it
   removes the decision owner's freedom to decline, which changes what a
   counterfactual *means* here. **Not implemented in this pass, deliberately.**
2. **Compiler visibility coherence.** Promote the new warning to a validation
   with a refusal path, and fix the prompt exemplar at
   `scene_prompts.py:127-128` that teaches the sender-only send event. Proven to
   change sender behaviour; proven insufficient alone.
3. **Evidence grounding.** Every claim in these manifests is USER_SUPPLIED,
   TEST_ASSUMPTION or UNKNOWN; the a16z manifest is deliberately
   `PUBLICLY_VERIFIED = 0` because verifying a claim about a real person from
   2026 risks importing post-cutoff material. Grounding needs a retrieval path
   with source dates enforced at the contract layer.
4. **Observed / inferred / latent state separation.** The contracts have no
   first-class fields for it; the classification currently lives only in the
   experiment's evidence manifest and cannot constrain what an actor may know.
5. **Behavioural calibration.** The self-repetition rate, the uniform warmth,
   and the invented-detail rate are measurable today and none is calibrated
   against anything. Calibration needs a reference distribution before it needs
   a model change.
6. **Representative population construction**, then **confidence calibration**,
   then **full action search** — none of which should start before (1) is
   decided, because all three multiply whatever the intervention semantics are.

---

## What this validation legitimately establishes

1. **The recording is sound.** Every visible model call at the three seams is
   on disk with prompt, raw response, params and verifying hashes; 1,146
   records with every request/response `sha256` recomputed and **0 mismatches**;
   independent counters agree; **0 credential occurrences across 666 committed
   files** scanned with a live key in the environment. One out-of-band path
   (one-token health probes) is disclosed and carries no simulation content.
2. **The counterfactual plumbing is what it claims.** Two scenarios share one
   compiled world byte-for-byte. Six salary branches collapse to one hash under
   masking with no stray field. Branch plans differ only at the insertion
   boundary.
3. **The measurement is anchored where it says.** Every metric resolves to a
   committed event in its own branch, attributed to the actor the metric is
   about.
4. **The negative results are real**, reproduced across four runs and a
   controlled two-arm live experiment, and they now cause the engine to
   **refuse** rather than to rank.

## What it does not establish

1. **Anything about the counterfactual.** Delivery failed in all six runs, so
   no branch comparison in this artifact set carries information about candidate
   quality.
2. **Anything about behavioural realism.** 34–40% verbatim self-repetition,
   invented calendars and 6/6 uniform warmth are role-play signatures.
3. **That the historical cutoff held as stated.** A post-cutoff sentence from
   the user-supplied context reached the a16z compiler prompt (`ERRATA.md` E2).
   It did **not** propagate — 360 actor/GM prompts and 180 responses clean in
   both runs, verified twice independently — but the "enforced at 3 stages"
   claim was false as written, and the corrected validator now **retroactively
   refuses that frozen input**.
4. **That the reports' prose matched their ledgers.** Two of three claimed the
   guard never fired when it fired three times between them (`ERRATA.md` E1).
   Where narrative and artifact disagree, **the artifacts are right** — that is
   the single most important thing to carry forward from this exercise.
