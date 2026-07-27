# COMPILER WORLD AUDIT — Phase 0 forensic audit of all semantic-compiler case artifacts

Audited: branch `claude/semantic-world-compiler-li1tsy`, HEAD `b14d86e`, working tree clean.
Read-only audit. Nothing was rerun, regenerated, or repaired. All paths are repo-relative
under `/home/user/SWORLDMODEL-GROUND-UP/` unless absolute. Supplementary evidence:
`/tmp/claude-0/-home-user/b5fbfb0e-accb-58f6-a3d0-bf0bed4e1e2e/scratchpad/run2.log` … `run11.log`
(stdout of successive `compile_cases.py` runs) and `git log`/`git show` of the eight commits that
committed artifact snapshots.

Method note: every claim below cites an artifact path plus a JSON pointer, line, or verbatim
excerpt. Where a question cannot be answered from the artifacts, that is stated explicitly.
The test suite was NOT executed (running it risks LLM calls via `tests/test_llm_phase_b.py` and
would write cache files into the repo); commit `d9b4e49` claims "163 passing" — unverified here.

---

## 0. Provenance and artifact integrity (read this before trusting any single file)

### 0.1 Run ↔ commit map (recovered from git + run logs)

| run log | approx time | committed at | notes |
|---|---|---|---|
| run1 (no log) | ~23:20 | `b359d7a` | first snapshot; `summary.json` had only 2 rows (traffic NO_CAUSAL_PRODUCER, ethics INVALID_REFERENCE) |
| run2 | 23:21 | `4798524` | driver crashed mid-run: `AttributeError: 'str' object has no attribute 'get'` in `_fidelity_review` (run2.log) |
| run3 | 23:24 | — | traffic_study answered **'yes' (resolved)** — the only evidence-correct boolean answer ever produced |
| run4 | 23:26 | — | ethics + merger both REALITY_REVIEW_REJECTED; run truncated |
| run5 | 23:37 | `72a71b1` | unseen crashed the driver: `json.decoder.JSONDecodeError: Unterminated string … (char 29993)` (truncated LLM reply) |
| run6 | 23:45 | `e730af1`/`0dbb5c7` | four cases die on "no provenance block" contract errors |
| run7 | 23:51 | — | traffic dies NO_CAUSAL_PRODUCER (terminal pre-satisfied belief) — a good guard firing |
| run8 | 23:52 | — | `IndentationError: unexpected indent` in compile_cases.py — the driver itself was broken by an edit (fixed by `8959dfb`) |
| run9 | 00:03 | `542f77e`-era | log carries the hand annotation: `[BAD] insufficient_merger INSUFFICIENT_EVIDENCE … <- refused on a contract slip, NOT because the evidence is insufficient` |
| run10 | 00:14 | `a7d24d9` | blood 315.0; traffic 'no'; wage 'no'; ethics + unseen die on the tally-`record_type` validator |
| run11 | 00:21 | `b14d86e` | the "latest run" of record: blood REJECTED, ethics COMPILED 'no', merger REJECTED, traffic 'no', unseen LOWERING_GAP, wage 'no' |

### 0.2 Stale-artifact contamination — every case directory mixes runs

The pipeline writes into a fixed `artifacts/compiled/<case>/` directory and never clears it, so
files from different runs (and different code versions) coexist. Verified by mtime and git:

- `artifacts/compiled/blood_units/`: `semantic_scenario.json`, `reality_review.json`,
  `revision.json`, `compilation_diagnostics.json`, `metrics.json` are run11 (REJECTED);
  but `approved_scenario.json`, `terminal_result.json` (answer 315.0), `event_ledger.jsonl`,
  `runtime_world_snapshot.json`, `lowering_trace.jsonl`, `symbol_table.json`,
  `terminal_producer_report.json`, `reality_fidelity_review.md` are run10 leftovers
  (`git show b14d86e --stat` touches only the first group). **The directory simultaneously
  asserts "this world was rejected as untruthful" and "this world ran and answered 315.0."**
- `artifacts/compiled/ethics_committee/`: `revision.json` mtime 23:55:16 vs run11 files
  00:16–00:17; `contract_repair.json` 23:47; `structural_repair.json` 23:48;
  `contract_repairs.jsonl` 00:07:57 — four different runs in one directory. Run11's own
  `metrics.json` (`revision_calls: 1`, `reviewer_calls: 1`) proves `revision.json` cannot be
  run11's (a review-revision implies `reviewer_calls: 2`).
- `artifacts/compiled/traffic_study/`: `contract_repairs.jsonl` 00:09:31 (run10-era) and
  `revision.json`, `contract_repair.json`, `structural_repair.json` all stale next to run11 output
  (`metrics.json`: `semantic_calls: 1, revision_calls: 0`).
- `artifacts/compiled/unseen/`: `revision.json` (81 KB) is from run9's rejection
  (run11 `metrics.json` has `reviewer_calls: 1` and a first-review verdict APPROVE).
- Singular `contract_repair.json` / `structural_repair.json` files are written by **no current
  code** (`git grep "contract_repair.json" -- '*.py'` → empty); they are legacy formats from the
  pre-`0014e06` repair code. The legacy format stored `first_error` + `raw_response` +
  `repaired_scenario` (before/after); the current `*_repairs.jsonl` stores **only the error** —
  an artifact-completeness regression: the current format cannot show what a repair changed.

### 0.3 Coverage of the artifact list named in the audit spec

| spec name | actual artifact | status |
|---|---|---|
| question.json / evidence_package.json | same names | present, all 6 cases |
| raw semantic model responses | `semantic_call.json` (`{"prompt": {system,user}, "raw_response": …}`) | present, all 6 |
| semantic_scenario.json | same | present, all 6 (post-repair state only; pre-repair overwritten in place) |
| approved_scenario.json | same | present where `_finish` ran (ethics, traffic, wage; blood_units copy is stale run10). Absent for insufficient_merger and unseen **because the pipeline stopped** before `_finish` — legitimate |
| reality_review.json | same | present for 5 cases. **Absent for insufficient_merger because nothing records it**: `compiler/review.py:128-131` raises `RealityReviewRejected` on a REJECT verdict *before* `pipeline.py:124` writes the file. The digested verdict/reasoning/defects survive only inside `compilation_diagnostics.json:/detail/review`; the reviewer's raw response is lost |
| revision + repair artifacts | `revision.json`, `contract_repairs.jsonl`, `structural_repairs.jsonl` (+ legacy singular files) | present but cross-run contaminated (0.2). The second review's raw response is never persisted (`pipeline.py:138-140` stores `result2` fields only). The structural-repair LLM call's raw response is never persisted (only the triggering error) |
| symbol_table.json / lowering_trace.jsonl / runtime_world_snapshot.json / terminal_producer_report.json / terminal result | same names (`terminal_result.json`) | present for compiled cases; blood_units copies stale (run10). Absent for merger/unseen **because the pipeline stopped** |
| runtime trace references | `event_ledger.jsonl`, `state_transitions.jsonl`, `actor_wakes.jsonl`, `actor_views.jsonl`, `action_lifecycle.jsonl`, `information_lifecycle.jsonl`, `intentions.jsonl`, `intention_rejections.jsonl`, `replay_verification.json` | present for compiled cases; matches the hand-authored Phase 1 reference sets (`artifacts/phase_b_email_llm/` has the same family) |
| metrics | `metrics.json` + `runtime_metrics.json` | present; several counters wrong (§1.3) |

---

## 1. The pipeline as verified against the code (three claims in the system description are false in practice)

The described shape — semantic call → independent review (≤1 revision) → bounded mechanical
repair (budget 3) → deterministic lowering → scripted-minds runtime → declarative TerminalSpec —
is structurally present (`compiler/pipeline.py`, `compile_cases.py`). Deviations that matter:

1. **"Deterministic lowering with zero LLM calls" is false at the pipeline level.**
   `compiler/lower.py` itself makes zero model calls (verified — no llm import). But
   `pipeline.py:_finish` (lines 221–243) wraps `lower()` in a repair loop that calls
   `build_scenario(...)` — a full LLM call — on `InvalidReference`/`SemanticAmbiguity`/
   `NoCausalProducer`, up to `MAX_MECHANICAL_REPAIRS = 3` times, and the timer started at line
   221 bills those calls to `metrics["lowering_ms"]`. Hence
   `artifacts/compiled/ethics_committee/metrics.json` `"lowering_ms": 22100.9` and
   `wage_talks/metrics.json` `"lowering_ms": 18291.6` — 22 s and 18 s of "zero-model-call
   lowering" that are actually LLM repair calls.
2. **"Contract repair" is a reroll, not a repair.** In the stage-1 loop, `pipeline.py:95-97`
   calls `build_scenario(question, evidence, revision_defects=defects, previous=None, …)` —
   the previous scenario is *not* passed. The model re-authors the entire world from scratch
   with the error text appended. `docs/COMPILER.md` ("There is no rerolling with fresh seeds
   until something passes"; "each capped at one attempt") is contradicted by the code
   (budget 3, reroll semantics). The lowering-stage repair (line 231) does pass
   `previous=scenario`, but it mutates the scenario **after review approval** and the result is
   never re-reviewed (§6, cause 4).
3. **Repaired-after-approval worlds are labeled "approved."** `approved_scenario.json` is
   written in `_finish` *after* the repair loop (`pipeline.py:248`), so it can contain content no
   reviewer ever saw: ethics run11's reviewer approved a 4-participant scenario
   (`structural_repairs.jsonl`: "no participant named 'Manufacturer' (declared participants:
   ['Dr. Helen Osei', 'Dr. Raj Patel', 'Sister Margaret Doyle', 'Tomas Lindqvist'])" at
   00:17:45, *after* `reality_review.json` at 00:17:23); the executed world has 5.

### 1.3 Smaller mechanical defects in the pipeline itself (all verified)

- `pipeline.py:302-303` is dead code (unreachable duplicate `_wj` + `return` after line 300's
  `return record`); line 214's stage-3 comment is mis-indented to column 0 — residue of the same
  class of sloppy edit that produced run8's `IndentationError`.
- REJECT path undercounts: `insufficient_merger/metrics.json` shows `"reviewer_calls": 0` and
  tokens 6751 (= semantic call only) although a real reviewer call produced the rejection —
  `review()` raises before `pipeline.py:122-123` increments/counts.
- The driver prints `"from 1 producing records"` when `computed_from` is
  `['terminal.cutoff']` — a placeholder, not a record (`compile_cases.py:83-85`;
  `traffic_study/terminal_result.json:/answer/computed_from`).
- `compile_cases.py:100-114` marks any COMPILED case `[OK]` regardless of the answer: run11's
  summary shows `[OK ] traffic_study … answer='no'` for a case whose evidence supports 'yes'
  (§3.3) and whose run3 artifact *did* answer 'yes'. There is no expected-answer oracle anywhere
  in the repo (`EXPECTED_REFUSAL` is the only expectation).
- `pipeline.py:_fidelity_review` line 365 hardcodes: "Actors here are the deterministic
  MechanicalMind: on each wake they take the first affordance…" — false since `f1afed7`;
  `compiler/minds.py:5-10` states "There is deliberately no built-in 'take the first available
  action' policy." Every committed `reality_fidelity_review.md` carries this false sentence, plus
  boilerplate ("Information was delivered on real routes with real latency…") asserted even for
  worlds with zero routes (`blood_units/reality_fidelity_review.md`).
- `docs/COMPILER.md` drift: says "10 sections" (`schema.py` SECTIONS has 11 and the contract
  says "All eleven sections"); lists observation kind `tally_facts` (code has `tally_records` and
  `record_exists`, 9 kinds in `sworldmodel/terminal.py:43-47`); names `structural_repair.json`
  (current code writes `structural_repairs.jsonl`); documents the deleted MechanicalMind.
- The `24:00` calendar fix (`lower.py:_clock_time`, HEAD `b14d86e`, 00:23:48) was committed
  *after* the last run (00:21) — the committed `unseen` failure is against code that no longer
  exists, and the fix has never been exercised by a case run (a unit test exists:
  `tests/test_time.py:128`).

---

## 2. Run-to-run variance (evidence: run logs + committed summaries)

Same inputs, `temperature: 0.0` (`compiler/llm.py:30`), model `deepseek-chat`:

| case | outcomes observed across runs 1–11 |
|---|---|
| blood_units | COMPILED 315.0 ×7 → INSUFFICIENT_EVIDENCE (run5) → COMPILED ×2 → **REALITY_REVIEW_REJECTED (run11)** |
| ethics_committee | INVALID_REFERENCE, INSUFFICIENT_EVIDENCE ×3, REALITY_REVIEW_REJECTED, SEMANTIC_AMBIGUITY ×2, NO_CAUSAL_PRODUCER, **COMPILED 'no' (run11)** — six distinct failure stages before one success |
| insufficient_merger | model-declared INSUFFICIENT_EVIDENCE (runs 2,3), reviewer REJECTED (runs 4,5,7,10,11), contract-slip false refusals (runs 6,9 — the run9 log itself brands one `<- refused on a contract slip`) |
| traffic_study | 'yes' (resolved) run3 → crash run2, NO_CAUSAL_PRODUCER run7, SEMANTIC_AMBIGUITY run5 → **'no' (cutoff) runs 6,9,10,11** |
| unseen | driver crash (run5, truncation), INSUFFICIENT_EVIDENCE ×2, REALITY_REVIEW_REJECTED (run9), SEMANTIC_AMBIGUITY (run10), **LOWERING_GAP (run11)** |
| wage_talks | SEMANTIC_AMBIGUITY (template braces) runs 3,7; INSUFFICIENT_EVIDENCE runs 6,9; **COMPILED 'no' runs 10,11** |

Two sources, both visible in artifacts: (a) provider nondeterminism at temperature 0 — the same
prompt yields structurally different worlds (blood run10: 1 process + 12 events; blood run11:
0 processes + 8 pre-multiplied batch events); (b) the contract/validator itself changed between
runs (`cd4a0e9` provenance inheritance, `a7d24d9` template/typed-record mismatch, `b14d86e`
24:00), so run N and run N+1 were graded by different rulebooks. Run-to-run answer flips on
identical evidence (traffic 'yes'→'no') were never surfaced by the harness.

---

## 3. Per-case audits

Answers are numbered per the audit spec (Q1–Q15).

### 3.1 blood_units — latest run REJECTED; stale COMPILED (315.0) artifacts alongside

Inputs: `blood_units/question.json` ("How many usable blood units will the regional hospital
have received by Friday noon?"), `evidence_package.json` e1–e10 (drive 12 units/hr 9–17 M–F;
centre 40 @ Mon 9:00; hospital 15; Tue/Thu 16:00 shipments of 150; ~3 h transit; supervisor
Cruz has no control). Hand arithmetic from the evidence: 15 + 150 + 150 = **315** at Friday noon.

- **Q1 outcome believed to answer.** Run10 (stale, executed): `quantity_measured` of
  `usable_blood_units` held by St. Vincent at cutoff → 315.0
  (`terminal_result.json:/answer/answer`). Run11 (rejected): same measure
  (`semantic_scenario.json:/resolution/observations/0`).
- **Q2 causal pathway believed.** Initial 15 + two 150-unit transfers; centre stock fed by
  collections. Run10: continuous process `collection drive` @12/hr with operating periods
  (`approved_scenario.json:/processes/0`) + fixed `transfer_resource` 150 at Tue/Thu 16:00.
  Run11: the same arithmetic pre-computed — `/scheduled_events/0` "Monday collection drive
  produces units" `{"change_type":"change_quantity","delta":96,…}` (12×8 pre-multiplied), etc.
- **Q3 included.** Two organizations (centre, hospital). Run10 also included redundant
  start/stop events duplicating `operating_periods` (10 events toggling the process the lowerer
  already toggles — harmless double control, `approved_scenario.json:/scheduled_events/0-9`).
- **Q4 excluded.** Elena Cruz (e10) — **justified** exclusion, documented:
  `approved_scenario.json:/scope/excluded/2` "She oversees receipts but does not affect
  quantities." Exclusion safety here is genuinely good.
- **Q5 from evidence.** Rates, hours, stocks, shipment days, 150-unit size (e9 verifies the fixed
  150), all with correct citations (e.g. `/processes/0/provenance` = e2,e3).
- **Q6 inferred.** That shipments always move exactly 150 (evidence e7 "available stock" + e9
  "each move 150" — consistent here because stock ≥ 150 at both dispatches in the run10 world).
- **Q7 invented.** Nothing material invented in run10. Run11 invented an *ordering*: daily
  collections as 17:00 batch events, contradicting continuous collection (second review defect).
- **Q8 uncertainty preserved.** None — `uncertainties: []` in both versions. e8's "about 3
  hours" transit is the one inferred quantity.
- **Q9 uncertainty silently resolved.** The 3-hour transit was *erased*: run10's transfer fires
  at dispatch (event ledger `seq 47`, `t 2026-07-21T23:00:00+00:00` = 16:00 PDT) while the same
  event's description says "arrives at hospital at 7:00 PM (3 hours later)"
  (`approved_scenario.json:/scheduled_events/10/description`). Run11 went further:
  `/scheduled_events/3` "Tuesday shipment arrival (3 hours later, but transfer already happened
  at dispatch; arrival is implicit…)" — an event with **no effects** that admits the collapse in
  prose. Harmless for this deadline; answer-flipping for any deadline between 16:00 and 19:00.
- **Q10 world understanding correct?** **Yes, substantially** — in every run including the
  rejected one. Run11's rejecting reviewer computed the correct answer itself:
  `reality_review.json:/causal_path/3` "By Friday noon, hospital has 15 + 150 + 150 = 315 units".
- **Q11 failed mainly in serialization?** **Yes (run11).** Correct understanding serialized as
  end-of-day batches (`/scheduled_events/1` Tue 17:00 delta 96 *after* the 16:00 shipment),
  which the second review correctly called out
  (`compilation_diagnostics.json:/detail/remaining_defects/0`: "Tuesday and Thursday collection
  events are scheduled at 5pm, after the 4pm shipment…"). One-revision budget exhausted → world
  rejected despite correct arithmetic.
- **Q12 lowering preserved approved meaning?** Run10: yes for every structured field (verified
  numbers in `event_ledger.jsonl`, `replay_verification.json` hash match). It also faithfully
  preserved the dispatch-time error, because the *meaning* ("arrival 19:00") lived only in prose.
- **Q13 lowering added/removed/altered causal behavior?** No. (The `operating_periods` +
  explicit start/stop duplication originates in the scenario, not the lowerer.)
- **Q14 could the terminal genuinely emerge after genesis?** No, in the interesting sense: the
  world contains **0 affordances** in both versions; no actor can do anything. The number
  emerges only from scheduled transfers + process accrual — pure clockwork.
- **Q15 predetermined / unexercised / trajectory-produced?** **Predetermined.** The trajectory
  merely evaluates arithmetic fixed at authoring time. (For a quantity question the
  `_verify_not_already_answered` guard does not apply — `lower.py:1039` returns early for
  non-boolean — so a fully precomputed quantity world compiles by design.)

Repair history: `contract_repairs.jsonl` (single line, mtime 00:16-era):
"processes['blood collection drive'].rate: basis 'verified' cites no evidence_ids" — the rate
*was* e2 (note said "From e2"); the nested-object citation demand was a **contract bug**, fixed
architecturally by `cd4a0e9` provenance inheritance. Classification: fixed a
contract/documentation bug, not a model error. Reviewer verdicts: run11 round 1 flagged the
Friday collection listed in `terminal_producers` as *critical* (a bookkeeping-list error that
could not change the produced number — contra `review.py:81` "Use REVISE only for defects that
change what the simulation would produce"); the genuinely causal 17:00/16:00 ordering flaw
surfaced only in round 2, after the budget was spent. The rejection burned a correct answer on
defect-severity misallocation plus the one-revision rule.

### 3.2 ethics_committee — COMPILED (run11), answer 'no' at cutoff; the most emergence-capable world, unexercised

Inputs: `ethics_committee/question.json` (does the committee approve at the 12 March meeting;
resolution_note: majority of votes cast; "If the required votes are not cast before the meeting
ends, there is no decision"), evidence e1–e14 (3 voters; Lindqvist safety review; favourable
10 Mar data; Doyle on retreat with **no email contact** but attends in person, e12).

- **Q1 outcome believed to answer.** A majority tally of typed `vote` records:
  `semantic_scenario.json:/resolution/observations/0`
  `{"observation_type":"tally_of_records","record_type":"vote","rule":"majority","expected_count":3,…}`,
  question_type `boolean`.
- **Q2 pathway believed.** Bulletin (scheduled event, 10 Mar 08:00) → Lindqvist wakes, prepares
  and sends review → Osei/Patel notice by email → meeting-start fact (12 Mar 14:00 event) →
  chair puts motion (affordance) → members vote (affordance, `create_record`) → tally.
- **Q3 included.** 5 participants (3 voters, Lindqvist, Manufacturer — the last added by
  post-approval repair), 3 routes (hospital email 60 s, manufacturer bulletins, meeting room),
  4 starting beliefs/facts encoding e9–e11 stances.
- **Q4 excluded.** `scope/excluded`: other hospital business; therapy/patient details — safe.
  Materially *missing*: any mechanism for Doyle to receive the safety assessment at the meeting
  (paper copy / verbal summary), i.e. exactly the gap the *stale* run-era reviewer flagged
  (`revision.json:/defects_addressed/0`, 23:55) and run11's reviewer did not.
- **Q5 from evidence.** Meeting time, membership, majority rule, email latency, stances,
  Lindqvist's tasking; provenance citations present and correct throughout.
- **Q6 inferred.** Review takes half a day; hourly email checks ("several times during the
  working day" → `check_interval_minutes: 60`); 1-minute vote duration (e14).
- **Q7 invented without support.** The review's *conclusion*:
  `/action_affordances/0/consequences_on_completion/0/content` = "Safety review incorporating
  updated data, **concluding therapy is acceptably safe**." The evidence (e5) documents lower
  adverse events, not Lindqvist's professional verdict. The stale second-round reviewer had
  called precisely this "unsupported_assumption / major" (`revision.json:/defects_addressed/1`);
  run11's approving reviewer raised nothing.
- **Q8 uncertainty preserved.** None — `uncertainties: []`.
- **Q9 uncertainty silently resolved.** (a) The review conclusion (above). (b) Doyle's
  information access, resolved in the *wrong direction*:
  `/participants/2/attention/0` = `{"route":"hospital email","description":"On retreat from 10
  to 12 March, no email access.","status":"verified","check_interval_minutes":null,
  "bounded_by_availability":false}`. Under `sworldmodel/info.py:45-47`
  (`check_every=None` = "continuously attentive while the calendar is open", `calendar=None` =
  any hour), the compiled Doyle is **continuously attentive to hospital email at all hours** —
  the exact inverse of the stated meaning, which lives only in the description prose.
- **Q10 world understanding correct?** Substantially yes at the meaning level (participants,
  cascade, votes-as-records, meeting mechanics all right; the reviewer's causal path matches the
  evidence, including "Doyle does not receive email (on retreat, no email access)" —
  `reality_review.json:/causal_path/5`).
- **Q11 failed mainly in serialization?** **Yes.** Three serialization failures sit on top of a
  sound understanding: the Doyle attention inversion (Q9b); the `boolean` + `tally/majority`
  terminal (below); the review-conclusion baked into a consequence.
- **Q12 lowering preserved approved meaning?** It preserved the *structured* content faithfully
  — including the inverted attention rule. It also accepted a terminal binding that cannot carry
  the question's meaning: for `question_type: "boolean"`,
  `sworldmodel/terminal.py:_read_tally_records` (lines 220–254) sets `satisfied = complete`
  (records ≥ `expected_count`) and *never compares the majority value to anything* — three
  REJECT votes would satisfy the observation and `TerminalSpec.evaluate` (lines 306–317) would
  answer **"yes" (= "The committee approves")**. The yes/no meaning is not encodable in this
  binding; the correct encoding was `question_type: "choice"` (which returns the winning value)
  or `count_value`. Neither `schema.py:validate` nor `lower.py:_lower_terminal` refuses
  boolean+majority — a silent meaning-altering acceptance.
- **Q13 lowering added/removed/altered causal behavior?** Altered observable meaning per Q12;
  causal dynamics otherwise preserved (wakes fired correctly: `actor_wakes.jsonl` shows
  Lindqvist woken 10 Mar 13:00 UTC with `info_noticed`, all three members woken at meeting
  start).
- **Q14 could the terminal genuinely emerge after genesis?** **Yes — the best of all six.**
  Motion and votes are affordances with actor-chosen parameters
  (`/action_affordances/2/parameters/0` `allowed_values: ["approve","reject"]`), gated by real
  preconditions (`motion put`, `record_absent` per voter). Nothing schedules the outcome.
- **Q15 predetermined / unexercised / trajectory-produced?** **Mechanically unexercised.** No
  fixture script exists (`cases/ethics_committee/` has no `scripted_minds.py`); every wake ended
  "no scripted rule applies to this wake" (`actor_wakes.jsonl`, all 4 records); 0 of 3
  affordances ever ran (`reality_fidelity_review.md`: "Never performed by anyone:
  ['prepare_and_send_safety_review', 'put_motion_to_approve', 'vote']" + the READ-WITH-CARE
  warning). The reported 'no' (`terminal_result.json:/answer/answer`, `computed_from:
  ['terminal.cutoff']`) additionally contradicts the case's own resolution_note, which requires
  "no decision" when votes aren't cast — the unresolved concept exists in the runtime
  (`errors.py:62-66`, `TerminalSpec.uncertain_paths`) but only covers unnoticed-information
  paths, not never-acted paths.

Repair history: (run10-era) `contract_repairs.jsonl` ×2 — both "'tally_of_records' needs a
'record_type' … SAME string as the create_record" — the contract/validator mismatch fixed by
`a7d24d9`; contract-bug class. (run11) `structural_repairs.jsonl` ×1 — undeclared 'Manufacturer'
participant; genuine model slip, mechanically real fix (participant added), **but the reviewer
approved the pre-repair scenario and never saw the repaired one**, and the reviewer itself had
missed the undeclared participant (its own checklist item 3, `review.py:35-37`). Reviewer
quality: run11's APPROVE reasoning contains an unresolved self-contradiction about Osei's vote
("she votes reject because she lacks current safety data (she has it, but …" —
`reality_review.json:/reasoning`) and `defects: []`.

### 3.3 traffic_study — COMPILED (run11), answer 'no' at cutoff; evidence supports 'yes'; run3 artifact proved 'yes'

Inputs: `traffic_study/question.json` (will Reyes have *read* the finalized study before the
meeting; resolution_note: "Receiving it in an unread inbox does not count"), evidence e1–e10
(reviewer sign-off committed by 10:00 Feb 18; Santos emails within the hour of sign-off, checks
hourly; email ~1 min; Reyes checks every ~2 h, reads studies in full, 60–90 min). Evidence-chain
answer: **yes**, comfortably (study in Reyes's hands Wednesday; meeting Thursday 19:00).

- **Q1 outcome believed to answer.** Run11: that Reyes *noticed* the study —
  `semantic_scenario.json:/resolution/observations/0`
  `{"observation_type":"participant_noticed_information","participant":"Alma Reyes","tag":"finalized study"}`.
- **Q2 pathway believed.** Scheduled sign-off (Feb 18 10:00, `/scheduled_events/0`) → Santos
  notices (hourly attention) → affordance "send finalized study" (noticed-information parameter,
  20-min duration) → email 60 s → Reyes's 2-hourly attention notices it.
- **Q3 included.** Reyes, Santos, external reviewer; city email route; the in-flight sign-off.
- **Q4 excluded (materially relevant).** **The reading step.** Run11 has no reading affordance
  and no reading-duration anywhere, although the question and resolution_note are *about*
  reading. Earlier runs modeled it: run3 had `['send finalized study','start reading study']`
  with a `quantity_reaches` observation (pages-read), run6 had
  `['send the finalized study','read the finalized study']` with
  `action_was_completed('read the finalized study')` (git `4798524`, `0dbb5c7` scenario
  versions). The terminal *weakened across rerolls* — noticed+pages → read-completed → noticed
  only — with no mechanism noticing the drift.
- **Q5 from evidence.** All times, cadences, durations, route latency; correct ids.
- **Q6 inferred.** 20-min compose/send duration ("inferred", fine); hourly/2-hourly cadence
  quantifications of e10/e6.
- **Q7 invented.** Nothing material (run11).
- **Q8 uncertainty preserved.** None (`uncertainties: []`).
- **Q9 silently resolved.** "She reads it before the meeting" — the load-bearing step — resolved
  by *defining it away* (terminal = noticed).
- **Q10 world understanding correct?** Yes — every run's understanding of the chain was right;
  the reviewer's approved causal path is exactly the evidence chain and ends "Reyes reads the
  60-page study (60-90 minutes) before the meeting at 7:00 PM"
  (`reality_review.json:/causal_path/4`).
- **Q11 failed mainly in serialization?** Yes: the world cannot represent the path's final step
  (no read affordance), and the terminal does not mean what the resolution_note demands. The
  reviewer approved a path the compiled world cannot take — terminal-faithfulness went
  unreviewed.
- **Q12/Q13 lowering.** Faithful; 1.3 ms; no additions/removals
  (`lowering_trace.jsonl`, `symbol_table.json` consistent with scenario; replay hash true).
- **Q14 emergence possible?** The two-hop chain (send → notice) could genuinely emerge; with
  the run3/run6 worlds, reading could too.
- **Q15 predetermined / unexercised / trajectory-produced?** **Unexercised, and the answer is a
  harness artifact.** `cases/traffic_study/scripted_minds.py` matches on the exact authored
  affordance label `"send the finalized study"`; run11's world named it `"send finalized study"`.
  `tests/scripted_minds.py:decide` silently skips unknown labels
  (`verb = self.verbs.get(rule["action"]); if verb is None: continue`), so at Santos's one wake
  — where he had *noticed the sign-off* — the decision was "no scripted rule applies to this
  wake" (`actor_wakes.jsonl`, seq 26). No send, no notice, `answer: no` from
  `['terminal.cutoff']`. The fidelity review fired its warning ("READ THIS ANSWER WITH CARE…
  reflects the limits of the authored script"), yet `summary.json` reports the case `[OK]`.
  Run3's 'yes' (git `4798524`: `answer: yes`, `computed_from: ['record:50','record:8','record:68']`)
  was produced by the then-existing built-in MechanicalMind (`git show 4798524:compiler/minds.py`,
  `class MechanicalMind`), which `f1afed7` deliberately deleted as "a production actor model in
  all but name" — after which the only case with a script never matched its world again.

Repair history: run11 `contract_repairs.jsonl` ×1 — `information[0]: no provenance` — model slip
against the (post-inheritance) contract; trivially fixed by reroll. Stale singular
`contract_repair.json` (23:47) shows the pre-inheritance contract demanding provenance blocks on
`attention`/`delivery_delay`/`duration` nested objects — contract-bug class, later fixed by
`cd4a0e9`. Stale `structural_repair.json` (`0014e06`-era): `within_time_window needs 'after'
and/or 'before'` — genuine model slip, LLM-repaired (legacy file preserves `repaired_scenario`).
Run7's `NO_CAUSAL_PRODUCER: the terminal is already satisfied by the starting state …
alma_reyes holds belief on 'content_of_finalized_riverside…'` (run7.log) is the pre-answered
guard working correctly — a compiler guard catching a real defect.

### 3.4 wage_talks — COMPILED (runs 10–11), answer 'no' at cutoff; evidence supports 'yes'

Inputs: `wage_talks/question.json` (signed wage agreement before the strike deadline), evidence
e1–e11 (authorities 4.0–4.5 overlap; Bright prepared to come down to 4.5 (e10); Wozniak moves to
4.5 only after the union comes down (e9); mediated session 29 Oct 10:00; e11: "An agreement is
recorded as accepted when a negotiator accepts the other side's tabled offer at the table").

- **Q1 outcome believed to answer.** Two acceptance records:
  `/resolution/observations/0-1` — `record_was_made(record_type "agreement", subject "wage
  increase", made_by Yolanda Bright)` AND `(… made_by Dennis Wozniak)`, both required for YES.
- **Q2 pathway believed.** Session-start event sets `session_started` fact and wakes both
  negotiators → union tables 4.5 → employer notices → employer tables 4.5 or accepts → union
  accepts → records exist.
- **Q3 included.** Exactly the two negotiators; one route ("bargaining table", 0 s); 6 starting
  facts/beliefs (standing 3.5/5, authorities, dispositions).
- **Q4 excluded (materially relevant).** The mediator (present in e9's mechanism) and any
  possibility of tabling values other than 4.5 (below). Union membership/ratification excluded —
  defensible given e3's pre-granted authority.
- **Q5 from evidence.** Session time, authorities, standing positions, 45-min caucus durations,
  at-the-table immediacy (0-s route).
- **Q6 inferred.** That both sides act at the session (from e9/e10 dispositions).
- **Q7 invented.** The *restriction* of the action space:
  `/action_affordances/0/parameters/0` `{"name":"demand_value","allowed_values":["4.5"]}` plus
  precondition `parameter_one_of … ["4.5"]`, and the mirror on the employer side
  (`/action_affordances/1`). No evidence says these are the only tabulable numbers — e10 says
  Bright is *prepared to go to* 4.5, not that 4.6 is physically impossible.
- **Q8 uncertainty preserved.** None (`uncertainties: []`) — "will they actually move at the
  table" is the question's real uncertainty and it appears nowhere.
- **Q9 silently resolved.** The negotiation space (Q7), and the terminal over-resolution:
  requiring records from *both* sides contradicts e11's rule that one side's acceptance of the
  other's tabled offer records the agreement. The reviewer's own approved causal path —
  "Bright accepts at table … Both create agreement records" (`reality_review.json:/causal_path`)
  — never has Wozniak performing `employer accepts demand`, i.e. **the approved path cannot
  satisfy the approved terminal** (only that affordance creates his record).
- **Q10 world understanding correct?** The convergence-at-4.5 reading is right and
  evidence-grounded. The mechanics of *recording* (e11) were misunderstood or overwritten.
- **Q11 failed mainly in serialization?** Substantially: intentions serialized as the only
  physics (rails), acceptance rule serialized as dual-record, message contents hardcoded.
  A contributing *pipeline* cause is documented in `contract_repairs.jsonl`: attempt 1 rejected
  `"Offer of {offer_value}% wage increase"`, attempt 2 rejected
  `"Union demands {demand_value} wage increase."` — after two anti-template refusals the model
  emitted literal `"4.5"` strings everywhere and shrank `allowed_values` to match. The
  anti-template rule's repair pressure manufactured constants out of parameters.
- **Q12/Q13 lowering.** Faithful to the structured scenario (4 affordances, records,
  preconditions; `terminal_producer_report.json:/replay_hash_match: true`). `lowering_ms`
  18291.6 is mostly the structural-repair LLM call (§1.1).
- **Q14 emergence possible?** Sequence yes (table → notice → accept via noticed-information
  parameters — well-formed message-response patterns); *values* no (rails). Partially
  predetermined possibility space.
- **Q15 predetermined / unexercised / trajectory-produced?** **Unexercised** (no script;
  `reality_fidelity_review.md`: "Never performed by anyone: ['employer_accepts_demand',
  'employer_tables_revised_offer', 'union_accepts_offer', 'union_tables_revised_demand']", both
  participants idle, READ-WITH-CARE warning). 'no' from `['terminal.cutoff']` against an
  evidence-expected 'yes'; `summary.json` `[OK]`.

Repair history: contract repairs ×2 (template braces — model slips against a rule whose design
then backfired, see Q11); structural repair ×1
(`action_affordances[1]` references undeclared parameter `union_demand_notice` — genuine model
slip, caught by `lower.py:_check_parameter_references` preflight, LLM-repaired, never
re-reviewed). Stale `contract_repair.json` preserves the older, third variant
(`{wage_percent}`) from run3 — the same slip class recurring across runs.

### 3.5 insufficient_merger — REALITY_REVIEW_REJECTED (expected refusal): the control case, working

Inputs: `insufficient_merger/question.json` (board approval before end of quarter), evidence of
deliberate insufficiency (e1–e4: two companies, one anonymous "understood to have held talks"
report, no public statements).

- **Q1/Q2.** The scenario proposed observing a `board approval` record producible by one
  invented affordance (`record board approval`); no events, no schedule — it could never run
  (`semantic_scenario.json`: `scheduled_events: []` would also have hit NOTHING_SCHEDULED).
- **Q3/Q4.** One participant (the board); everything else absent — appropriately, since the
  evidence contains nothing else.
- **Q5–Q7.** Only e1/e2-level identity facts came from evidence; the affordance and the
  `board_approval_status` starting fact were scenario constructions, which the reviewer
  correctly identified: "The scenario invents a board action affordance and a starting state (no
  approval recorded) that are not contradicted, but the core question … cannot be answered"
  (`compilation_diagnostics.json:/detail/review/reasoning`).
- **Q8.** **The only non-empty `uncertainties` section in all six cases** —
  `/uncertainties/0-1`: "Whether the board will ever meet or vote…", "Whether the board has the
  authority to approve acquisitions." Honest.
- **Q9.** None silently resolved.
- **Q10–Q13.** Understanding correct (that the question is undecidable); no lowering occurred
  (stopped at review) — `approved_scenario.json`, `symbol_table.json`, runtime artifacts absent
  *because the pipeline stopped*, which is correct.
- **Q14/Q15.** Not applicable (no world was built); the refusal itself was
  **substantive and trajectory-independent** — the right outcome for this fixture, and
  `compile_cases.py:104-110` correctly demands a substantive stage for expected refusals.
- Defects here are pipeline-side: `metrics.json` `reviewer_calls: 0` (a reviewer call happened);
  reviewer tokens uncounted; no `reality_review.json` (§0.3); and across runs the refusal
  *mechanism* is unstable — model-declared (runs 2–3), reviewer-rejected (4,5,7,10,11),
  contract-slip false refusal (6, 9 — the latter flagged in the run9 log itself). The
  contract-slip variants would have counted as failures of the fixture had the driver's
  substantive-refusal check (`0dbb5c7`) not been added.
- Repair history: run11 `contract_repairs.jsonl` ×1 (`record_was_made` needs `record_type`) —
  model slip, repaired by reroll.

### 3.6 unseen — LOWERING_GAP (run11): a fully pre-written world killed by a calendar convention

Inputs: `unseen/question.json` (will MV Rhine Meridian be recorded **all fast** at Berth 8 by
23:59 EDT 2026-08-13; resolution_note enumerates the NO branches: overnight at anchorage,
next-morning berthing, wrong berth, pilot-report-governs), 15 claims (tides, standing orders,
berth occupied by Cape Ferrol, crane moves remaining, gang shifts, departure standards,
24-h dispatch watch, inferred mobilization intervals e13, 2025 transit-time records e14).

- **Q1 outcome believed to answer.** Two `record_was_made` observations for
  `all_fast_record` by the Pilots Association and by the terminal
  (`semantic_scenario.json:/resolution/observations/0-1`) — a faithful reading of the
  resolution_note's two-log requirement.
- **Q2 pathway believed.** A minute-by-minute chain of 10 scheduled events
  (`/scheduled_events/0-9`): Cape Ferrol last container 18:10 → lashing 18:50 → pilot 19:00 →
  unmoored 19:25 → stern clear 19:35 → berth declared clear 19:37 → inbound pilot boards 19:47 →
  anchor aweigh 20:17 → sea buoy 20:32 → **"Rhine Meridian all fast at Berth 8 (3h05m after sea
  buoy)" at 23:37 with effects that `create_record` the two all-fast records**
  (`/scheduled_events/9/effects/0-1`). `/terminal_producers/0/produced_by` says it outright:
  `"scheduled_events[9].effects[0]"`.
- **Q3 included.** 13 participants (ships, pilots association, terminal, agent, towing, line
  handlers, 5 named individuals, and — added by mechanical repair — 'NOAA Tides' as a
  *participant*), 5 routes, 19 starting facts.
- **Q4 excluded (materially relevant).** Every decision point and every failure mode the
  resolution_note names. **0 action_affordances, 0 processes** — pilots who order nothing,
  a dispatcher who dispatches nothing, a superintendent who supervises nothing. The people are
  scenery; the timeline is the actor.
- **Q5 from evidence.** The constraint facts (tide 19:58, moves remaining, crane rate, shift
  times, departure standards, transit times) — richly and mostly correctly cited.
- **Q6 inferred.** Every chained interval (e13 is explicitly `inferred` in the evidence).
- **Q7 invented without support.** The *certainty*: each inferred interval became an exact
  minute; their 5.5-hour composition became a scheduled fact landing 22 minutes inside the
  deadline. No slack, no variance, no alternative branch.
- **Q8 uncertainty preserved.** None — `uncertainties: []`, in the one case whose question *is*
  the uncertainty ("does the chain slip past 23:59?").
- **Q9 silently resolved.** All of it: the answer to the question was computed by the authoring
  model and serialized as event 9. The reviewer endorsed the arithmetic step by step and found
  `defects: []` ("the verified 3h05m transit from sea buoy yields all fast at 23:37 EDT, well
  before the 23:59 EDT deadline… no unsupported assumptions" —
  `reality_review.json:/reasoning`; twelve causal_path steps that are the same subtraction
  restated).
- **Q10 world understanding correct?** The *constraint analysis* may well be right — it is the
  most sophisticated modeling in the repo. But as a **world** it is not an account of a
  situation; it is a proof sketch formatted as a schedule. Materially: understanding of the
  domain good, understanding of the task (define possibility, not outcome) absent.
- **Q11 failed mainly in serialization?** The pre-writing is the deep failure (understanding of
  what a scenario is); the *stop* was mechanical: the model wrote
  `/participants/0/availability` `{"open":"00:00","close":"24:00","workdays":[0-6]}` for the
  ship, and run-11 code (`a7d24d9`) refused: `compilation_diagnostics.json:/reason` =
  "participants['MV Rhine Meridian']: availability is not usable as a calendar (hour must be in
  0..23)". `"24:00"` is the ordinary way to write end-of-day; HEAD (`b14d86e`) normalizes it
  (`lower.py:_clock_time`) — fix committed after the final run, never exercised by a case.
- **Q12/Q13 lowering.** Never completed. Note the stop was misclassifiable: `LOWERING_GAP` is in
  `compile_cases.py:SUBSTANTIVE_REFUSALS` (lines 25–26), so this formatting-convention gap would
  have counted as a *substantive* refusal had this been an expected-refusal case.
- **Q14 could the terminal emerge after genesis?** **No — by construction.** With zero
  affordances, nothing any mind did could have changed anything; the terminal record is created
  by the schedule.
- **Q15 predetermined / unexercised / trajectory-produced?** **Predetermined**, in the most
  literal form in the audit: the terminal's producing event *is* the answer, authored in
  advance.
- Artifact answerability note: Q12–Q15 for the *runtime* cannot be answered from run11 artifacts
  because none exist (pipeline stopped) — the judgments above are from the scenario itself,
  which fully determines them.

Repair history: run11 `contract_repairs.jsonl` ×1 (information[0-1] no provenance — model slip,
rerolled); `structural_repairs.jsonl` ×1 with 3 defects — attention route 'Telephone' undeclared;
`starting_state[7]/[8]` reference undeclared 'NOAA Tides' — genuine model slips caught by
preflight; the LLM repair *added NOAA Tides to participants* (present in
`/participants/12`) to satisfy the checker; never re-reviewed. Run5's truncation crash
(unterminated string at 30 KB) exposed a real transport bug, genuinely fixed by `72a71b1`
(`TruncatedResponse` + repair-instruction "Return a SMALLER world"). Run9's rejected review and
81 KB `revision.json` are stale residue in the same directory.

---

## 4. Defect register and layer classification

Layer legend: EV=EVIDENCE_FAILURE, WU=WORLD_UNDERSTANDING_FAILURE,
SS=SEMANTIC_SERIALIZATION_FAILURE, DA=DETERMINISTIC_ASSEMBLY_FAILURE, LO=LOWERING_FAILURE,
RT=RUNTIME_FAILURE. "Arch" = architectural (pattern spanning cases / caused by
pipeline design) vs case-specific. "Rev" = did the reviewer catch it. "Repair" = genuinely
fixed / contract-bug fix / reworded-to-pass / not-fixed.

| # | defect | layer | artifact + pointer/excerpt | arch? | rev? | repair |
|---|---|---|---|---|---|---|
| D1 | Entire trajectory pre-written as scheduled events incl. the answer record | WU | `unseen/semantic_scenario.json:/scheduled_events/9/effects/0`, `/terminal_producers/0/produced_by:"scheduled_events[9].effects[0]"` | arch (pattern) | no — endorsed (`defects: []`) | not fixed |
| D2 | All uncertainty annihilated in a question about timing risk | WU | `unseen/semantic_scenario.json:/uncertainties: []` vs question.json resolution_note NO-branches | arch (5 of 6 cases have `uncertainties: []`) | no | not fixed |
| D3 | Negotiation space collapsed to the predicted values (will≡can) | WU | `wage_talks/semantic_scenario.json:/action_affordances/0/parameters/0/allowed_values:["4.5"]` (+ employer mirror, + `parameter_one_of`) | arch (pattern) | no — approved | not fixed |
| D4 | Reading step (the question's subject) dropped from the world | WU | `traffic_study/semantic_scenario.json` — no read affordance; resolution = noticed-only vs resolution_note "unread inbox does not count" | case (but terminal-drift across rerolls is arch) | no — approved a path with a step the world lacks | not fixed |
| D5 | Review conclusion pre-decided inside consequence | WU | `ethics_committee/semantic_scenario.json:/action_affordances/0/consequences_on_completion/0/content` "…concluding therapy is acceptably safe" | arch (outcome-in-consequence pattern) | caught in a *stale* run (`revision.json:/defects_addressed/1`), missed in run11 | not fixed |
| D6 | Continuous collection serialized as end-of-day batches that miss same-day shipment | SS | `blood_units/semantic_scenario.json:/scheduled_events/1` (Tue 17:00, delta 96) vs `/scheduled_events/2` (16:00 shipment); `compilation_diagnostics.json:/detail/remaining_defects/0` | case | yes — round 2 | not fixed (run rejected) |
| D7 | 3-h transit collapsed; transfer fires at dispatch while prose says arrival | SS | `blood_units/approved_scenario.json:/scheduled_events/10/description` ("arrives at 7:00 PM") vs `event_ledger.jsonl seq 47 t=…23:00:00+00:00`; run11 `/scheduled_events/3` "arrival is implicit", empty effects | arch (prose-vs-structure) | no — approved | not fixed |
| D8 | Doyle "no email access" encoded as continuous always-on attention | SS | `ethics_committee/semantic_scenario.json:/participants/2/attention/0` + `sworldmodel/info.py:45-47` semantics | arch (prose-vs-structure; schema cannot express "no access in window") | no — reviewer *narrated the prose meaning* while approving the inverse structure | not fixed |
| D9 | boolean question bound to majority-tally ⇒ any 3 votes = "yes" | SS+LO (accepted binding) | `ethics_committee/semantic_scenario.json:/resolution` (`question_type:"boolean"` + `rule:"majority"`); `sworldmodel/terminal.py:220-254` (`satisfied = complete`) | arch (expressible, meaningless, unrefused) | no | not fixed; never exercised (nobody voted) |
| D10 | Terminal requires both-side records vs e11 one-acceptance rule; approved causal path cannot satisfy approved terminal | SS | `wage_talks/semantic_scenario.json:/resolution/observations/0-1` vs evidence e11; `reality_review.json:/causal_path` (no Wozniak-accepts step) | case | no | not fixed |
| D11 | Template braces in authored content (×3 distinct runs/variants) | SS (mechanical) | `wage_talks/contract_repairs.jsonl` attempts 1–2 (`{offer_value}`, `{demand_value}`); stale `contract_repair.json` (`{wage_percent}`) | arch (recurring) | n/a (validator) | "fixed" by hardcoding literals — reworded-to-pass, and it *fed D3* |
| D12 | Undeclared references (Manufacturer; NOAA Tides ×2; route 'Telephone'; param `union_demand_notice`; empty `within_time_window`) | SS (mechanical) | `ethics_committee/structural_repairs.jsonl`, `unseen/structural_repairs.jsonl`, `wage_talks/structural_repairs.jsonl`, stale `traffic_study/structural_repair.json` | arch (recurring slip class) | no (reviewer missed all; preflight caught all) | genuinely fixed mechanically, but post-approval and unreviewed |
| D13 | Pre-answered terminal (belief already held) | SS | run7.log: `NO_CAUSAL_PRODUCER: … alma_reyes holds belief on 'content_of_finalized_riverside…'` | arch (belief-observation weakness, known in contract) | no — caught by the **lowerer** | fixed by reroll in later runs |
| D14 | Provenance demanded on every nested object, unachievable pre-inheritance; refusals of honest scenarios | DA (contract bug) | `blood_units/contract_repairs.jsonl` ("rate: basis 'verified' cites no evidence_ids" — note says "From e2"); run6.log ×4 cases; stale `traffic_study/contract_repair.json` (attention/delivery_delay/duration blocks) | arch | n/a | genuinely fixed by `cd4a0e9` (contract fix, not model fix) |
| D15 | Contract/validator mismatch on typed records (tally `record_type` loop) | DA (contract bug) | `ethics_committee/contract_repairs.jsonl` ×2 identical errors; run10.log ethics + unseen | arch | n/a | genuinely fixed by `a7d24d9` |
| D16 | `24:00` refused as calendar time | LO | `unseen/compilation_diagnostics.json:/reason`; fix `b14d86e` post-dates last run | arch (convention gap) | n/a | fixed in code, unvalidated by any run |
| D17 | REJECT path: reviewer_calls=0, tokens uncounted, reality_review.json never written | DA | `insufficient_merger/metrics.json`; `review.py:128-131` vs `pipeline.py:122-124` | arch | n/a | not fixed |
| D18 | LLM calls inside "lowering", billed to lowering_ms | DA | `ethics_committee/metrics.json:"lowering_ms": 22100.9`; `pipeline.py:221-243` | arch | n/a | not fixed |
| D19 | Contract repair rerolls world from scratch (`previous=None`) | DA | `pipeline.py:95-97`; observable as whole-world drift between repair attempts (blood run11 vs run10 structure) | arch | n/a | not fixed |
| D20 | Post-approval mutation without re-review; "approved_scenario" ≠ reviewed scenario | DA | `pipeline.py:223-248`; ethics (+Manufacturer), wage (+param), unseen (+NOAA Tides) | arch | n/a | not fixed |
| D21 | Stale-artifact contamination of every case directory; rejected case shows stale COMPILED answer | DA | §0.2 (blood_units terminal_result.json vs compilation_diagnostics.json) | arch | n/a | not fixed |
| D22 | Driver/format churn broke runs: fidelity crash (run2), truncation crash (run5), IndentationError (run8) | DA | run2/run5/run8 logs; fixes `8959dfb`, `72a71b1` | arch | n/a | genuinely fixed |
| D23 | `[OK]` verdict for compiled-but-false answers; placeholder counted as "producing record"; no expected-answer oracle | DA | `compile_cases.py:100-114`, `:83-85`; summary.json rows for traffic/wage/ethics | arch | n/a | not fixed |
| D24 | Fidelity boilerplate asserts falsehoods (MechanicalMind; routes/latency claims for route-less worlds) | DA | `pipeline.py:365`; `blood_units/reality_fidelity_review.md` | arch | n/a | not fixed |
| D25 | Doc drift: COMPILER.md 10-vs-11 sections, `tally_facts`, "capped at one attempt", `structural_repair.json`, MechanicalMind section | DA | `docs/COMPILER.md` vs `schema.py:15-18`, `terminal.py:43-47`, `pipeline.py:33`, `minds.py:5-10` | arch | n/a | not fixed |
| D26 | Script coupling by model-authored strings; silent no-op on drift; flipped an evidence-'yes' to 'no' for 4 runs | RT | `cases/traffic_study/scripted_minds.py` ("send the finalized study") vs `action_lifecycle.jsonl` verb `send_finalized_study`; `actor_wakes.jsonl` "no scripted rule applies" at an `info_noticed` wake | arch | n/a (fidelity warning fired; summary ignored it) | not fixed |
| D27 | Unexercised worlds resolve to 'no' at cutoff; 'unresolved' path too narrow (info-noticing only); 'no decision' unreachable | RT | `terminal.py:318-347` (blocked-only unresolved); `ethics_committee/terminal_result.json` 'no' vs resolution_note "there is no decision"; `errors.py:62-66` states the principle the runtime then violates for action-gaps | arch | n/a | not fixed |
| D28 | Five of six worlds ran/would run with no minds at all (no scripts exist except traffic's) | RT | `cases/*/` listing (only `traffic_study/scripted_minds.py`); fidelity reviews' idle lists | arch | n/a | not fixed |

Not found (checked): EVIDENCE_FAILURE — the six hand-frozen packages are internally consistent,
correctly id'd, and (for merger) deliberately insufficient; no case artifact contradicts its
package. Runtime-engine defects — none found: ledgers replay (`replay_verification.json` /
`replay_hash_match: true` in all compiled cases), accrual and transfer arithmetic verified by
hand for blood run10 (315.0 correct), wakes and noticing fired per attention rules.

### Defect counts by primary layer

| layer | count | items |
|---|---|---|
| EVIDENCE_FAILURE | 0 | — |
| WORLD_UNDERSTANDING_FAILURE | 5 | D1 D2 D3 D4 D5 |
| SEMANTIC_SERIALIZATION_FAILURE | 8 | D6 D7 D8 D9* D10 D11 D12 D13 |
| DETERMINISTIC_ASSEMBLY_FAILURE | 12 | D14 D15 D17 D18 D19 D20 D21 D22 D23 D24 D25 + (D16's misclassification as substantive) |
| LOWERING_FAILURE | 2 | D16, D9* (acceptance side of the meaningless boolean/majority binding) |
| RUNTIME_FAILURE | 3 | D26 D27 D28 |

\* D9 straddles serialization (wrong `question_type` chosen) and lowering (binding accepted);
counted once each side, flagged.

The headline: **the assembly/pipeline layer produced more distinct defects than the model
layers combined**, and roughly 70% of all observed run *stops* across runs 2–11 were
contract-compliance churn (provenance shape, braces, record_type strings, truncation, driver
bugs) rather than anything about the world.

---

## 5. The five most common architectural causes

1. **The scenario language invites writing the future instead of the stage.**
   `scheduled_events` accepts arbitrary effects — including `create_record` of the answer
   (unseen D1) and pre-multiplied outcome deltas (blood D6/D7); affordance
   `parameters`/`preconditions` can pin actors to predicted values (wage D3); consequences can
   embed judgments (ethics D5). Nothing in `schema.py` or `lower.py` distinguishes
   "world-caused" from "actor-decided" happenings, and the reviewer doctrine actively blesses
   it (`review.py:53-58`: a committed future event that "could slip" is NOT a defect; "Real
   commitments are the correct basis for a scheduled event"). Five of six scenarios have
   `uncertainties: []`.
2. **Meaning lives in prose; execution reads structure; nothing compares them.**
   "No email access" beside an always-on attention encoding (D8); "arrives at 7:00 PM" beside a
   16:00 effect (D7); "arrival is implicit" beside an empty event (blood run11). The reviewer
   reads the prose, the lowerer reads the fields, and both sign off on opposite meanings.
3. **The reviewer judges narrative plausibility, not the compiled meaning.** It approved causal
   paths containing steps the world cannot take (traffic D4: "Reyes reads the 60-page study";
   wage D10: missing Wozniak-accepts), missed undeclared participants its checklist names
   (`review.py:35-37` vs D12), never once checked terminal-vs-resolution_note binding (D4, D9,
   D10), and misallocated severity (blood run11: `terminal_producers` bookkeeping = "critical",
   while the real ordering flaw waited for round 2 and the one-revision budget killed a correct
   world). Its genuinely good moments — merger rejection, blood round-2 ordering catch — are
   narrative-level too.
4. **Repair mutates worlds outside the review loop, on a contract that was itself the most
   common defect.** Contract repair rerolls from scratch (`previous=None`, D19); structural
   repair LLM-edits an approved world with no re-review (D20); the repair pressure itself
   distorted content (braces→hardcoded 4.5, D11→D3); and the two biggest slip classes
   (nested provenance D14, tally record_type D15) were bugs in the contract/validator, fixed by
   editing the compiler, not the scenarios — i.e. the compiler spent most of its repair budget
   arguing with itself.
5. **Negative answers by default, with no oracle to notice.** Worlds run with no minds (D28) or
   silently mismatched scripts (D26), fall to cutoff, and the boolean terminal converts
   "nothing happened" into "no" (D27) — against the codebase's own stated principle
   (`errors.py:62-66`) and the cases' own resolution notes. The driver then prints `[OK]`
   (D23). Four consecutive runs reported an evidence-false 'no' for traffic_study without any
   signal except a paragraph inside a Markdown file.

---

## 6. What is worth preserving, and what should be simplified or deleted

### Worth preserving (with the evidence that earned it)

- **`compiler/lower.py`'s discipline.** Genuinely zero model calls in the module; refuses to
  invent numbers (`delivery_delay has no 'seconds'; … this layer will not invent one`); the
  all-at-once preflight (`_preflight` collects every dangling reference — caught D12 every
  time); producer verification (`_verify_producers`) and the pre-answered-terminal guard
  (`_verify_not_already_answered`) caught real world defects (run7 traffic, run9 ethics) that
  the LLM reviewer missed. Deterministic, evidenced, and honest.
- **The declarative TerminalSpec with real lineage.** Observations return the ledger records
  that produced them; `computed_from` cites actual seqs (blood run10: records 7/47/68 = the
  initial set + two transfers); `replay_verification.json` hash-matches in every compiled case.
  The `unresolved ≠ no` concept (`uncertain_paths`) is the right idea — it is merely too narrow
  (D27).
- **`compiler/symbols.py`** — exact-match resolution that refuses near-misses with a
  did-you-mean (`resolve`: "no {kind} named {name!r}; did you mean …? References must match
  exactly") — the reason D12-class slips die loudly instead of silently.
- **Provenance-as-requirement with inheritance** (post-`cd4a0e9`). The honesty rule ("the
  compiler may not introduce an unlabelled factual assumption") is right; inheritance made it
  achievable; the surviving artifacts show correct, checkable citations in most sections.
- **The per-stage artifact trail + fidelity self-critique.** `contract_repairs.jsonl` /
  `structural_repairs.jsonl` record verbatim errors; the fidelity review's exercise-check
  ("READ THIS ANSWER WITH CARE… reflects the limits of the authored script") fired correctly in
  all three unexercised COMPILED cases. The *reporting* exists; the *gating* doesn't.
- **The independent-reviewer position and the REJECT path's substance.** insufficient_merger's
  rejection reasoning is exactly right, repeatedly, across runs. The reviewer's *placement* is
  sound; its *brief* is wrong (§5.3).
- **The deletion of the built-in MechanicalMind on principle** (`minds.py:5-10`) — the reasoning
  ("a run it drove would look like a forecast without being one") is correct. What failed was
  shipping no replacement contract for exercising worlds (D26/D28), not the deletion.
- **The substantive-refusal check** in the driver (`SUBSTANTIVE_REFUSALS` +
  `model_declared_insufficient`) — it correctly demoted run9's contract-slip refusal; it needs
  `LOWERING_GAP` removed from the substantive set (D16 shows a formatting gap counted as
  substantive).

### Should be simplified or deleted

- **Fixture scripts coupled by model-authored strings** (`tests/scripted_minds.py` label/tag
  exact match): delete or rebind to compiler-stable identifiers. This single mechanism produced
  four runs of false negatives (D26).
- **The 674-line monolithic contract** (`schema.py:contract_document`): most run failures were
  compliance with its shape rules, not world errors. Split machine-checkable shape (sections,
  enums, references) from meaning; stop demanding that an LLM hand-satisfy string-equality
  constraints (`record_type`, tags) that the lowerer could resolve or the validator could
  autofill deterministically. Reconsider the anti-template rule: its repair loop manufactured
  hardcoded constants (D11→D3); `content_from_parameter` already exists — accept braces and
  rewrite them mechanically instead of bouncing the whole document.
- **`scheduled_events` as an unrestricted effects channel**: outcome-writing effects
  (`create_record` of the terminal's record type, terminal-feeding quantity deltas) inside
  scheduled events should be refused or forced through affordances — this is the enforcement
  half of the refactor's central rule (compiler defines what CAN happen).
- **boolean+`tally_of_records/majority`** binding (D9): refuse at validation, or auto-rewrite to
  `choice`. Also `participant_holds_belief` (already distrusted by the contract itself) and the
  ignored `made_by` field inside actor-scope `create_record`.
- **The repair loops in their current form**: contract repair should pass `previous` (repair,
  not reroll); structural repair must trigger re-review or be constrained to reference-only
  edits; every repair should persist before/after (the deleted legacy singular format did this
  better than the current jsonl).
- **Fixed shared output directories**: per-run subdirectories or a manifest with run ids;
  the blood_units directory currently asserts two contradictory outcomes at once (D21).
- **Dead/false text**: `pipeline.py:302-303` dead code; the `_fidelity_review` MechanicalMind
  and routes boilerplate (D24); COMPILER.md's stale sections (D25); `lowering_ms` accounting
  (D18); the REJECT-path artifact loss and metrics undercount (D17).
- **The `[OK]`/summary logic**: gate on (a) expected answers where the fixture knows them,
  (b) the already-computed `artifact_risk` flag, (c) `run_status`/exercise coverage — all three
  signals already exist and are ignored (D23).

---

## 7. Three representative complete examples

1. **A mostly correct world — blood_units run10** (`approved_scenario.json` +
   `terminal_result.json` + `event_ledger.jsonl`, all stale-but-committed). Two organizations,
   one verified-rate process with operating periods, two evidence-fixed transfers; lowered
   faithfully; replayed bit-identically; produced 315.0 — the same number hand arithmetic gives
   from e2–e9. Its flaws are the system's flaws in miniature: zero affordances (a calculator,
   not a world), transit collapsed to dispatch time (D7), and it was later rejected (run11) for
   a worse serialization of the same correct understanding.
2. **A semantically incorrect world — ethics_committee run11 compiled world**
   (`semantic_scenario.json` = `approved_scenario.json`, `runtime_world_snapshot.json`).
   Executed world where: Doyle is continuously attentive to the email she evidentially cannot
   read (D8, inverted meaning); the boolean terminal would answer "approve" for any three votes
   including 3× reject (D9); the review's conclusion is pre-decided in a consequence (D5); and
   the reported 'no' contradicts the case's own "no decision" rule (D27). Every individual
   piece passed review, validation, lowering, and execution.
3. **A correct idea broken during serialization — traffic_study run11**
   (`semantic_scenario.json`, `reality_review.json`, `actor_wakes.jsonl`,
   `terminal_result.json`). The causal understanding was right in every run — the run11 reviewer
   restated the correct chain ending in Reyes reading before the meeting — and run3's artifact
   (git `4798524`) proves the idea executes end-to-end to 'yes'. Run11 serialized it with the
   reading step deleted and the terminal weakened to "noticed" (D4), then the runtime harness
   dropped the one causal action over a two-word label difference (D26), yielding an
   evidence-false 'no' stamped `[OK]`.

— end of audit —
