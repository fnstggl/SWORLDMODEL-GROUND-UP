# World compiler — design

Turn ANY natural-language question into the smallest runnable model of the
real situation needed to answer it, lowered onto the existing persistent
runtime.  The compiler builds the stage, the people, the rules, the
information, the processes, the clock, and the finish line.  It never writes
the trajectory: actors choose at simulation time; the runtime determines what
really happens.

This step is scoped to **compilation only**: every compiled world must be
mechanically runnable by the existing engine (proven by a no-mind dry run and
a full validation battery), but full simulations are not run here.

## The layer map (what is hardcoded, and where)

```
L0  kernel laws (sworldmodel/world.py, events.py, simclock.py — UNCHANGED)
    entities/state/quantities/possession/visibility/relationships/events/
    provenance-by-cause; time moves forward; every change has a cause.
L1  universal lifecycles (already in the kernel; one addition)
    information: create -> send -> deliver -> notice -> read
    actions:     proposed -> validated -> started -> completed/failed
    processes:   exact elapsed-time accrual, capacity, thresholds
    terminals:   NEW sworldmodel/terminals.py — declarative outcome specs
                 (data) evaluated mechanically with cited producers, so no
                 compiled world needs a hand-written Python evaluator.
L2  universal capability menu (compiler/capabilities.py — data schemas)
    the ONLY things a compiled world can be made of: participants,
    aggregates, channels, attention, facts, resources, processes, operating
    windows, threshold watches, relationships, beliefs, commitments, action
    definitions built from effect lifecycles, scheduled external events,
    scheduled wakes, uncertainty declarations, exclusions, one terminal.
L3  scenario meaning (DATA ONLY — never code)
    "vote" = authorized action + typed fact record.  "reply" = action +
    information lifecycle.  "shipment" = action/process + possession change.
    No scenario noun or verb appears in compiler/runtime source; a guard
    test enforces it.
```

Effect "macros" in the menu (`send_information`, `record_fact`,
`transfer_resource`, …) are *lifecycle compositions* that deterministic
assembly expands into existing L0 ops.  The kernel op set does not grow.

## Pipeline

```
question + asof date + evidence (model memory | evidence docs)
  1  RESOLUTION      LLM: the exact observable answer condition, horizon,
                     answer mode (yes/no | value | decision count), start
                     instant, modelability verdict.  Normative questions are
                     reframed to observable outcomes, and the reframing is
                     recorded.
  2  DISCOVERY       LLM, small calls, natural language only: participants &
                     aggregates (with exclusions), causal spine (what must
                     be POSSIBLE, backward from the answer), starting state,
                     knowledge boundaries, communication & attention,
                     possible actions, external processes & scheduled
                     events, uncertainty.  No predicted trajectory.
  3  TRANSLATION     LLM, one small item at a time, given the exact rendered
                     capability menu: select ONE capability, fill its small
                     fields, or return UNSUPPORTED.  It may not invent
                     participants, facts, actions, or consequences; every
                     name must already be in the registry.
  4  ASSEMBLY        code: canonical ids, alias resolution, duplicate
                     merging, dangling-reference rejection, lifecycle
                     expansion into genesis ledger ops, provenance mapping.
  5  VALIDATION      code: backward check (every terminal term has a
                     potential producer), forward check (world is alive: a
                     no-mind dry run on a replica fires real events),
                     integrity checks (terminal false at genesis, no
                     pre-written outcome, no dangling authority, bounded
                     size, attention reachability for spine-critical
                     communication).
  6  LOWERING        code, zero LLM calls: genesis records -> World,
                     terminal spec -> Terminal, persona briefs rendered from
                     each actor's OWN state only -> minds wiring.
  7  ROUND TRIP      code: reconstruct a plain-English summary from the
                     lowered World alone + a coverage ledger (every
                     discovered item ends lowered | excluded(reason) |
                     unsupported(reason); load-bearing items may not drop).
  8  REVIEW          adversarial LLM, two separate verdicts: (a) reality —
                     does the described world match the evidence/facts as of
                     the day; (b) meaning — does the round-trip summary
                     match the approved description.  Blocking objections
                     trigger ONE bounded repair round; a second rejection
                     fails the compile with the objections in the report.
  -> WorldBundle     one JSON artifact: description, translations, coverage,
                     genesis records, terminal spec, minds, validation
                     report, round-trip, reviews, full LLM trace.
                     instantiate(bundle) -> (World, minds, Terminal) with
                     zero LLM calls, ready for Engine.run().
```

## Failure modes designed against

| # | failure mode | mitigation |
|---|---|---|
| 1 | LLM emits malformed / off-schema JSON | per-call schema validation with repair retries (error echoed back), bounded; then that item is UNSUPPORTED or the compile fails with a structured report — never a crash |
| 2 | translator invents names/facts/consequences | closed capability schemas (unknown fields rejected), name registry (unknown reference -> rejection + one corrective retry -> UNSUPPORTED), effects only via lifecycle macros |
| 3 | duplicate/aliased participants ("Cuban" vs "Mark Cuban") | discovery declares canonical names + aliases first; builder resolves exact/case/alias matches; ambiguity is a rejection, never a guess |
| 4 | pre-written trajectory (the historical failure) | description stage is forbidden to predict; mechanical checks: terminal must evaluate false at genesis; no genesis-scheduled event may write a terminal-read fact; reviewers reject narrative futures |
| 5 | dead worlds (nothing can ever happen) | static: >= 1 genesis event strictly before the cutoff, every action's authority matches an existing actor, spine-critical noticing needs an attention rule; dynamic: no-mind dry run on a replica must fire events without error |
| 6 | silent invented durations/latencies/rates | every number carries provenance {verified, question_given, inferred, model_memory_unverified, uncertain}; `uncertain` never becomes a concrete number (validation refuses); kernel bases preserve the label in notes |
| 7 | uncertainty silently becoming fact | dedicated uncertainty declarations survive into the bundle and round-trip; the reality reviewer receives them; unmodelled noticing stays delivered-but-unnoticed (kernel guarantees) |
| 8 | unmodelable/normative questions | resolution must either produce an observable proxy (recorded reframing) or refuse with a reason — a structured outcome, not an error |
| 9 | scale explosion (a legislature, an audience) | resolution picks the smallest faithful world: few pivotal actors + aggregates as entities/resources/processes; hard caps on actors/entities/events |
| 10 | prompt injection via question or evidence docs | question/docs are data inside delimited blocks; structural schema validation is the real guard; capability menu is closed |
| 11 | reviewer rubber-stamping | two separate reviews with structured objection lists (severity, target); blocking objections force repair or failure — no combined "looks good" |
| 12 | meaning drift during lowering | round-trip summary is rendered from the World object alone and diffed (coverage ledger) against the approved description; material drift fails the compile |
| 13 | network failures | bounded retries with exponential backoff; then structured compile failure |
| 14 | compile nondeterminism | temperature 0; every exchange recorded in the bundle trace; instantiate(bundle) replays with zero LLM calls |
| 15 | outcome-critical noticing with no evidence | flagged needs_review; the reality reviewer must explicitly accept "this person may never see it" or demand a labeled inferred attention rule — the compiler never invents one |

## Evidence modes (both implemented)

* `model_memory` — the description stage uses what the model knows as of the
  asof date; every real-world claim is labeled `model_memory_unverified` or
  `inferred`; `verified` is not allowed without a document.
* `evidence_docs` — caller supplies documents; `verified` claims must cite a
  doc id (deterministically enforced); claims beyond the docs must be
  labeled `inferred`/`uncertain`; the reality reviewer receives the docs.

## What the compiler never does

It never chooses an actor's future decision, never writes a reply/vote/
shipment into the schedule, never invents a producer for a step nothing can
produce (it stops instead), and never lets an unverified claim wear a
`verified` label.
