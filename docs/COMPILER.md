# The semantic world compiler

Turns a question plus a **frozen evidence package** into a world the existing
runtime can execute. The runtime is not re-implemented, extended per scenario,
or bypassed anywhere.

```
question.json + evidence_package.json      hand-frozen; no live retrieval
        │
        ├─ compiler/semantic.py    MODEL CALL 1 — meaning only
        │      semantic_scenario.json  (10 sections, natural language inside)
        │
        ├─ compiler/review.py      MODEL CALL 2 — independent, read-only
        │      reality_review.json     APPROVE | REVISE | REJECT_INSUFFICIENT_EVIDENCE
        │      (at most ONE targeted revision, never a reroll)
        │
        ├─ compiler/lower.py       ZERO MODEL CALLS
        │      symbol_table.json, lowering_trace.jsonl
        │      → World, TerminalSpec, minds
        │
        └─ sworldmodel/engine.py   UNCHANGED
               event ledger → terminal derived from the trajectory
```

## What the model may and may not write

It writes **meaning**: who matters, what is true at the start, who knows what,
what is scheduled, what continues over time, what people can attempt, what
remains uncertain, and what exact reading answers the question.

It may not write identifiers, field names, event ids, sequence numbers, queue
priorities, causal depth, world versions, runtime operation names, effect
payloads, expression trees, replay records or code. That boundary is
**enforced, not trusted**: `semantic.py` rejects runtime-internal field names,
runtime operation names in prose, and `{template}` syntax anywhere in the
document.

Scenario meaning is carried by three small fixed vocabularies the model
*selects from*. Code binds them onto universal runtime operations:

| semantic change | runtime operation |
|---|---|
| `record_fact` | `fact.set` |
| `set_quantity` / `change_quantity` | `resource.set` / `resource.adjust` |
| `transfer_resource` | `resource.transfer` |
| `send_information` | `info.send_new` |
| `set_relationship` | `relationship.set` |
| `schedule_future_event` | `event.schedule_in` |
| `start_process` / `stop_process` | `process.active` |
| `record_private_note` | `actor.memory` / `actor.belief` |

Preconditions map the same way onto the runtime's `KNOWN_CONDITIONS`, and
terminal observations onto the eight `Observation` kinds. "Vote", "reply" and
"ship" are *labels on affordances* built from these — there is no scenario verb
anywhere in the kernel, and a test asserts the runtime vocabulary stays
domain-free.

## The one runtime addition

`sworldmodel/terminal.py` — a **declarative** terminal. The runtime's
`Terminal` takes a Python callable, which a compiler can never emit. The
`TerminalSpec` expresses the same thing as data over eight universal
observation kinds (`fact_equals`, `fact_exists`, `resource_at_least`,
`resource_measure`, `belief_topic_exists`, `info_noticed_by`,
`action_completed`, `tally_facts`), each returning the ledger records that
produced its reading. It is tested independently, including proof that it
reproduces all three hand-written terminals' answers exactly.

Two smaller additions: `actor_in` (identity-based authority, alongside the
existing role-based `role_in`) and `{{ }}` escaping in template substitution,
so authored prose containing braces can never be mistaken for a payload
template.

## What lowering refuses

`lower.py` invents nothing. It stops, with the stage named, when:

| stage | meaning |
|---|---|
| `INSUFFICIENT_EVIDENCE` | the scenario cites evidence the package does not contain, or the model declined to build a world |
| `SEMANTIC_AMBIGUITY` | malformed contract, duplicate names, naive timestamps, an action with no completion rule or two |
| `REALITY_REVIEW_REJECTED` | the independent reviewer refused, or defects survived one revision |
| `LOWERING_GAP` | a meaning the universal runtime cannot carry — an *uncertain* duration, rate or delivery delay asked to become a concrete number |
| `INVALID_REFERENCE` | a name resolving to nothing, or an action referencing a parameter it never declares (a permanently dead action) |
| `NO_CAUSAL_PRODUCER` | nothing in the world could produce what the terminal reads — **including a terminal already satisfied by the starting state** |
| `NOTHING_SCHEDULED` | no event at or before the deadline; time would never advance |
| `COMPILED` | a world that can actually run and be answered |

Three of these deserve emphasis because they encode stated principles:

- **The trajectory must produce the answer.** A boolean terminal that is
  already true at genesis is refused: that is an initialization value, not an
  outcome.
- **Unknown stays unknown.** If the evidence cannot justify how someone would
  notice something, no attention rule is created; the information is delivered
  and remains unnoticed, and a terminal depending on it has no producer.
- **No invented numbers.** Every duration, rate, latency and cadence carries a
  provenance basis, and `uncertain` may never become a number.

## Bounded repair, and why it is bounded

Two repair rounds exist, each capped at one attempt and fully recorded:

1. **Reality-review revision** — the reviewer's blocking defects go back to
   the semantic compiler once. If defects survive, the run stops. There is no
   rerolling with fresh seeds until something passes.
2. **Structural repair** — a *mechanical* refusal (`INVALID_REFERENCE`,
   `SEMANTIC_AMBIGUITY`, or a pre-answered terminal) is handed back verbatim
   with a directive fix instruction, exactly as a compiler reports an error.
   Substantive stops (`LOWERING_GAP`, `NOTHING_SCHEDULED`, and every other
   `NO_CAUSAL_PRODUCER`) are never repaired — those mean the world genuinely
   cannot answer its own question.

Both are recorded in artifacts (`revision.json`, `structural_repair.json`) and
counted in `metrics.json`, so a case that needed help cannot look like one that
did not.

## Minds

Stage 1 uses `MechanicalMind`: on each wake it proposes the first affordance
whose parameters it can fill from its own local view. It is universal and
deliberately unintelligent — it proves the compiled world is **executable** and
that the causal path reaches the terminal. It does not model what a real person
would choose, and every fidelity review says so.

Stage 2 swaps in `CompiledLLMMind` over the *identical* compiled world, so
behaviour changes while world construction is held fixed.

Neither can reach the world, clock, queue, terminal or another actor; both
receive an `ActorView` and return a `Decision`, and everything they return
passes the same kernel validation.

## Known limitations of this step

- **One trajectory.** Uncertainty is recorded in the scenario's
  `uncertainties` section but not branched over. The reviewer is explicitly
  scoped to judge the best-supported single course of events, because under a
  "anything could slip" standard no world would ever compile.
- **Reachability is not proven.** The producer check verifies that something
  *could* produce each terminal reading; it does not prove an affordance is
  actually reachable, which is undecidable in general. A world can compile and
  still answer "no" because nobody managed to act.
- **`participant_holds_belief` is a weak observation.** It is satisfied by any
  belief on the topic, so the pre-answered check exists specifically to stop
  it silently reading initialization as an outcome. Prefer
  `action_was_completed` or `participant_noticed_information`.
- **No live retrieval, no calibration.** Evidence is hand-frozen by design, and
  nothing here measures forecast accuracy.
