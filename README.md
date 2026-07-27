# SWORLDMODEL — ground-up kernel + world compiler

The smallest working core of SWORLDMODEL: a **persistent shared world**, a
**realistic, event-driven, real-calendar time engine**, and a **universal
world compiler** that turns ANY natural-language question into the smallest
runnable model of the real situation needed to answer it.

No scenario is hardcoded anywhere. The kernel knows only universal
mechanics; the compiler knows only universal lifecycles; scenario meaning
("vote", "reply", "ship an order") is **data** produced at compile time.

## The world compiler

```
python3 compile_question.py "your question" [--asof YYYY-MM-DD]
        [--docs evidence/your_docs.json] [--out artifacts/compiled/name]
```

Three strictly separated stages (see COMPILER_DESIGN.md):

1. **Describe** (LLM, small calls, natural language only): the exact
   observable answer condition, then — backward from it — participants,
   aggregates, communication and attention, starting state and knowledge
   boundaries, possible actions, external processes and scheduled events,
   uncertainty, exclusions.  What CAN happen, never what WILL happen.
2. **Translate** (LLM, one small item at a time): each item onto a closed
   capability menu (rendered from the same tables that validate the
   output): select one capability, fill its small fields, or return
   UNSUPPORTED.  No invented names, facts, or consequences.
3. **Assemble + validate + lower** (deterministic code, zero LLM):
   canonical ids, alias resolution, lifecycle expansion into kernel ops,
   backward check (every terminal term has a producer), forward check
   (no-mind dry run of the real engine), integrity checks (terminal false
   at genesis, no pre-written outcomes), English round-trip read back from
   the lowered world, and two adversarial reviews (reality vs. evidence;
   meaning preservation).  Blocking findings get one repair round; a second
   failure is a structured refusal, never a crash.

Evidence modes: `model_memory` (claims labeled `model_memory_unverified` /
`inferred`) or `evidence_docs` (`--docs`; `verified` requires a document
citation — see `evidence/*.json` for the acceptance fixtures).

The result is a **WorldBundle** (`bundle.json`): genesis ledger, declarative
terminal spec, per-actor identity briefs, coverage ledger, validation
report, reviews, and the full LLM trace.  `compiler.instantiate(bundle)`
rebuilds `(World, minds, Terminal)` with zero LLM calls, ready for
`Engine(world, minds, terminal).run()` — running full simulations is the
next step, not this one.

## Layout

```
sworldmodel/            the kernel (stdlib-only Python 3.11+)
  simclock.py           authoritative tz-aware clock; elapsed vs calendar
                        arithmetic; DST gap/overlap handling (strict);
                        per-entity business calendars; Duration + provenance
  events.py             immutable Event; deterministic queue (t, depth, seq);
                        unique ids; cancellation; no-past scheduling;
                        zero-time-loop bounds
  world.py              persistent shared state; ONE mutation funnel
                        (apply -> reducer + append-only ledger); world
                        version; continuous processes with exact elapsed-time
                        accrual and capacity; universal ops incl. info.send_new
                        / event.schedule_in macros; replay & resume by pure
                        ledger fold; producer lineage
  actors.py             private qualitative ActorState (beliefs, goals,
                        emotions, relationships, commitments, append-only
                        timestamped memories, plan, reconsideration
                        conditions); ActorView (defensive copies, local info
                        only); Mind interface returning intentions, never
                        consequences
  info.py               channels with latency provenance; AttentionRule with
                        mandatory provenance; noticing never defaulted
  actions.py            universal action lifecycle; declarative ActionDef
                        (authority conditions, preconditions, effects) with
                        template substitution -- scenario verbs as data
  engine.py             the event loop: advance -> accrue -> consequences ->
                        deliver -> wake-with-reason (or defer) -> validate ->
                        schedule -> terminal; stale-intention re-validation;
                        busy-actor interruption policy; repeated-state loop
                        detection
  checkpoint.py         exact save/resume from ledger position (verified by
                        hash); nothing fires or applies twice
  llm_mind.py           Phase B: DeepseekMind behind the same Mind interface
  artifacts.py          under-the-hood artifact projections of the ledger
worlds/                 hand-authored test fixtures (data + scripted minds)
  adapters.py           shared action definitions (send/read message) -- data
  email_world.py        two-person message interaction (NY/LA, weekend, DST)
  committee_world.py    small-group decision (release -> briefing -> votes)
  factory_world.py      operational process with quantities (shifts,
                        thresholds, transit)
tests/                  89 tests: temporal edge cases, kernel invariants,
                        world properties, checkpoint/resume, replay, Phase B
run_worlds.py           runs everything, verifies, writes artifacts/<world>/
artifacts/              committed run artifacts (ledgers, views, hashes...)
```

## How a step of the world works

```
peek next event (t, same-instant depth, seq)      <- single authoritative order
advance the clock to t (never backwards)
fold elapsed time into continuous processes        <- recorded accruals, exact
apply the event's consequences                     <- universal ops only
deliver information (channel latency)              <- delivered != noticed
schedule noticing (justified rules only, else
  delivered-but-unnoticed: unknown stays unknown)
collect wake triggers; for each affected actor:
  busy + no interruption right  -> defer (recorded), never dropped
  otherwise                     -> consult with reasons + local view only
mind returns Decision           -> kernel validates EVERYTHING:
  private-state ops (self only), intentions (authority/preconditions),
  durations (provenance required), future wakes
validated intentions -> action.start events; starts re-validate if the
  world version moved (stale intentions fail, recorded)
actions complete/fail/interrupt later -> declared effects land -> new events
evaluate terminal (mechanical, must cite producers)
repeat until resolved or the scheduled cutoff event fires
```

Every state change is a ledger record `{seq, t, op, data, cause}`. The ledger
is the only source of truth: **replay** is a pure fold (zero actor/LLM
calls) that reconstructs the exact final state hash and terminal result; a
**checkpoint** is a ledger position plus verification hash, and a resumed run
is byte-identical to an uninterrupted one (tested at interruption intervals
of 1, 3 and 7 events for all three worlds).

## Running

```
python3 -m pytest tests/ -q          # 89 tests, ~6s, stdlib only
python3 run_worlds.py                # narrative + artifacts (add --skip-llm
                                     # to skip the live Deepseek actor)
```

Phase B uses `DEEPSEEK_API_KEY` from the environment.

## What the three worlds prove

| requirement | where proven |
|---|---|
| state persists | beliefs/memories/quantities carried across days, tests in every world |
| time progresses correctly | weekend + spring-forward gap = 61h41m30s elapsed; calendar-vs-elapsed tests |
| information is local | Fran votes on a stale belief; Bob acts only after noticing; reply content comes from his belief |
| actors wake for real reasons | every decision record carries triggers; exact wake counts asserted |
| actions take time | started/completed separated by provenance-labeled durations |
| consequences enter the world | replies, votes, shipments are records caused by completed actions |
| terminal depends on what happened | committee flips hold 2-1 / cut 2-1 with Fran's travel; producers cited |
| replay reconstructs everything | final-state hash + terminal equality, per world, deterministic |

## Honest limitations (this step, by design)

- Scripted Phase A minds are shallow keyword policies -- they exist to prove
  the kernel, not to be intelligent. Phase B replaces exactly one of them
  with a live model behind the same interface.
- Attention rules model checking routines with labeled provenance; real
  attention is burstier. Where no justified rule exists the kernel leaves
  information unnoticed rather than inventing behavior.
- One live actor only; no world compiler yet (world construction is
  hand-authored data here); terminal evaluators are hand-written mechanical
  functions per question.

Per-world reality-fidelity reviews live in
`artifacts/<world>/reality_fidelity_review.md`.
