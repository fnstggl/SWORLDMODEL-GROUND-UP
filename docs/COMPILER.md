# The semantic world compiler

The compiler turns a natural-language question plus a frozen evidence
package into an executable world for the unchanged runtime, or stops with
an exact, honest explanation of why it cannot. The governing principle:

> THE MODEL DISCOVERS THE CAUSAL WORLD.
> CODE ASSEMBLES, CONNECTS AND EXECUTES ITS REPRESENTATION.

The compiler defines the stage and the possibilities — what exists, what
is initially true, what actors and processes MAY do, what constraints
apply, what information can move, what causal routes can reach the
terminal, what remains uncertain, and what counts as the answer. It never
decides which choices actors will make or which possible route will occur.

## The default pipeline (`compiler/worldcompiler.py`)

    question (+ frozen evidence, or a Mode B memory draft)
      -> five small discovery calls          discovery.py   (model)
      -> deterministic assembly              assemble.py    (code)
      -> backward causal proof               proofs.py      (code)
      -> forward executability proof         proofs.py      (code)
      -> independent causal-reality review   reality.py     (model)
      -> item-at-a-time binding              binding.py     (model)
      -> deterministic emission              emit.py        (code)
      -> contract validation + lowering      schema.py / lower.py (code)
      -> semantic round-trip equivalence     roundtrip.py   (model check)
      -> causal challenge red team           challenge.py   (code)
      -> the existing runtime, unchanged
      -> terminal read from the trajectory, with exact replay

The retired one-shot whole-scenario pipeline (`pipeline.py`) remains
importable behind `compile_cases.py --legacy` for comparison only. The
eleven-section semantic scenario still exists — as a code-generated
artifact (`generated_semantic_scenario.json`), never a model-authored
interface.

## Discovery: five small calls (`discovery.py`)

Each call answers one narrow question and returns a small local result
with per-item provenance (`verified` / `inferred` / `question_given` /
`model_memory_unverified` / `uncertain`; cited where required). No call
maintains global references, and no call is asked for runtime operations,
IDs, payloads or enums.

1. **Resolution** — what externally observable state, record or quantity
   resolves the question, at what cutoff. Declared ambiguities get one
   adjudication round: quote the clause of the question, resolution note
   or evidence that settles the reading, or it stands and the case stops
   `AMBIGUOUS_QUESTION`. A false refusal is treated as seriously as a
   false compile.
2. **Backward causal spine** — possible and necessary dependencies, never
   a predicted trajectory. Actor choices appear as available decisions;
   only evidenced calendar items are scheduled events.
3. **Producer assignment** — who or what can produce each step, or an
   explicit `unsupported`. Prerequisites express ordering, not mechanism:
   the measured step needs the real mechanisms that change it.
4. **Starting state and information boundaries** — one call per entity:
   initial state, resources, commitments, authority, knowledge, channels
   with attention cadences, and explicit non-access windows.
5. **Uncertainty and exclusions** — what stays open (a world may
   legitimately reach its cutoff unresolved) and what is left out, with
   why each exclusion is causally safe.

Repair policy: at most one targeted repair per step at discovery time
(shape defects), one per document at assembly time (cross-reference
defects, routed to the document that owns them), and one reality-review
revision per document. Every repair replays the step's own prompt with
its previous answer and the exact defects — never a reroll — and a
repaired step is never counted as a first-pass success.

## The canonical world graph (`graph.py`, `assemble.py`)

Code owns one canonical graph with closed universal vocabularies:

- node categories: participant, organization, population, process, state,
  information, event, action, record, resource, terminal
- relationships: knows, has_state, has_authority, can_perform, requires,
  produces, changes, sends_to, receives_from, observes, scheduled_at,
  constrains, measured_by_terminal

Code creates every object once, generates stable IDs, resolves names with
refuse-don't-guess exactness (with did-you-mean), merges repeated
mentions order-free, attaches provenance, and records every builder
operation in an assembly trace. Structural rules the graph enforces:

- An actor decision is an `action` reachable only through `can_perform`;
  nothing can schedule a decision.
- An actor named as a scheduled event's or mechanism's producer OPERATES
  it (`has_authority`); only a step whose sole producers are actors is an
  actor's doing.
- A producerless condition with prerequisites is an explicit CONJUNCTION:
  it holds when its parts hold; its parts' producers do the causal work.
- Denied information access is edge structure (blocked windows on
  `receives_from`), not prose.
- A measured quantity's holder is materialized as a real entity (named by
  the resolution contract) and receives its own starting-state discovery.

## The proofs (`proofs.py`)

Backward: every terminal component must be producible by chains that
recursively reach real roots — initial facts, scheduled events, available
actor choices, operating processes, or explicit uncertainty. Genesis must
not satisfy a boolean terminal; a report cannot replace the process it
reports; no actor may write the answer directly unless the resolution
contract names that act as the measured terminal; and an event whose
effects write a terminal component must rest on a `verified` or
`question_given` schedule — an inferred timetable that asserts the answer
is refused, because inferred chains must be simulated, not scheduled.

Forward: a scheduled root exists, channels connect real senders to real
receivers, required information can become locally available to the actor
whose action needs it, preconditions are reachable, declared authority
covers a performer, and the terminal can still emerge after genesis.

## Review, binding, emission

**Reality review** (`reality.py`) — an independent reviewer reads the
deterministic rendering of the compiled structure (never a hand-authored
document) beside the question, the complete evidence, and what the proofs
established, and judges nine points in order: terminal faithfulness,
spine completeness, producers, missing actors, decorative inclusions,
unsupported claims, uncertainty preservation, exclusion safety, and
emergence after genesis. Verdicts: APPROVE, TARGETED_REVISION (defects
name their documents), REJECT_INSUFFICIENT_EVIDENCE, REJECT_WRONG_WORLD.

**Binding** (`binding.py`) — one item at a time against the complete
universal capability catalog, filling only the residue code cannot derive
(durations, latencies, rates, amounts, record makers and values, message
contents) or returning UNSUPPORTED — which stops the case
`UNSUPPORTED_CAPABILITY`, naming every gap at once. Numeric estimates
with no evidence to inherit carry the honest `model_memory_unverified`
label. A mechanism that does no continuous work may declare itself
decorative rather than invent a rate.

**Emission** (`emit.py`) — zero model calls. Universal plumbing is
derived in code: a state produced by a channel IS delivered information
(send → latency → attention → notice, with code-owned tags on both
sides); scheduled events wake exactly the actors who observe them or
whose actions await them; an action producing a measured record gets a
dedup guard; one substance held by several parties unifies to one runtime
quantity that transfers move; conjunction preconditions expand to the
parts that actually get written; blocked windows become calendar
holidays. Boolean+majority tallies are refused with repair guidance.
Anything inexpressible is refused with the exact gap — never
approximated.

## After lowering

**Round-trip** (`roundtrip.py`) — the runtime world is rendered back from
its own snapshot and an independent reviewer compares approved vs lowered
meaning: anything but EQUIVALENT is `LOWERING_MISMATCH` and the world
does not run.

**Challenge** (`challenge.py`) — ten deterministic red-team checks:
participant/process/route ablations re-run the backward proof without the
node; genesis/report/direct-write invariants; causally disconnected
elements; inferred exact times beside zero declared uncertainty;
serialization identity; exact replay after execution.

## Modes and honesty

- **Mode A** (frozen evidence) isolates compiler correctness.
- **Mode B** (question-only, `memory_evidence.py`) drafts an evidence
  package from model memory in the same format; every claim is marked
  `model_memory_unverified`, and such runs test universality, never
  factual reliability. Live retrieval will later produce the same package
  format without changing the compiler contract.
- Failure stages are exact: `AMBIGUOUS_QUESTION`,
  `INSUFFICIENT_EVIDENCE`, `SEMANTIC_AMBIGUITY`,
  `REALITY_REVIEW_REJECTED`, `NO_CAUSAL_PRODUCER`, `NOTHING_SCHEDULED`,
  `UNSUPPORTED_CAPABILITY`, `INVALID_REFERENCE`, `LOWERING_GAP`,
  `LOWERING_MISMATCH` — plus `UNRESOLVED_UNCERTAINTY` as a legitimate
  run outcome that is never reported as "no".
- The output directory is cleared per run; model time is billed to the
  model, never to lowering; every prompt and raw response is logged even
  on failure; script label drift is loud; a negative answer from an
  unexercised world is flagged in the record, the fidelity review and the
  driver verdict, and hand-derived `expectation.json` oracles fail cases
  whose compiled answer contradicts the evidence.

## Scripted and live minds

Fixture scripts (test harness only) prove compiled worlds execute; they
are never forecasts. The compiled world is frozen to
`approved_scenario.json`; `--reuse` re-lowers the identical world with
zero model calls so scripted-mind and live-LLM-mind runs compare the same
world. A script whose labels do not match the compiled world is refused
at construction.
