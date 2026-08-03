# Architecture State

Status: INITIALIZED_FROM_MASTER_DIRECTIVE
Source of authority: `docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md`
(sha256 `ac863c8355fab544fc79c8a440ed643b8b0879147209134868985dec67a0cdbb`).
This file is a faithful operational summary. Where this summary and the
directive disagree, the directive wins.

## What is being built

An intervention-centered best-action simulator. The unreliable SWORLDMODEL
semantic runtime is **replaced** — not extended — by an execution architecture
built from the exact, already-working upstream codebases:

- **Concordia** (google-deepmind/concordia; fork fnstggl/concordia,
  pinned baseline `7779a4c9f96bad10816d88c54e4cb17d53ac5222`)
- **AgentSociety 2** (tsinghua-fib-lab/agentsociety; fork fnstggl/agentsociety2,
  pinned baseline `6e9fc2e79f89f65a3e3d0d7899e380f7394099be`)
- **SWORLDMODEL-GROUND-UP** implementation base: latest main containing the
  merged verified control plane, `87f8c3d29cc7901d0d7d6ed835190cbde6fb3059`.

(Baseline SHAs above are the local fork checkouts recorded at initialization;
Phase 0 re-records and freezes the exact audited SHAs, and Phase 1 pins them in
`third_party/UPSTREAM_LOCK.json`, which then becomes the pin of record.)

## Production call path (fixed)

```
DecisionProblem
→ load or compile CompiledDecisionWorld
→ initialize Concordia
→ apply one InterventionCandidate
→ run the complete Concordia branch
→ produce BranchResult
→ optionally schedule complete branches through AgentSociety
→ compare BranchResults
→ produce RecommendationResult
```

The recommendation is computed from the resulting simulated world state and
event history. A final LLM may explain results but may not override them. The
system reports "best among tested candidates", never a global optimum.

## Responsibility ownership (one authoritative owner each)

| Responsibility | Initial owner |
|---|---|
| Local simulation runtime loop | Concordia engine |
| Actor observation lifecycle | Concordia |
| Actor action lifecycle | Concordia EntityAgent |
| Local action resolution | Concordia Game Master |
| Actor memory and components | Concordia |
| Local shared narrative state | Concordia Game Master memory |
| Outer distributed orchestration | AgentSociety 2 |
| Initial whole-branch persistence and recovery | AgentSociety workspaces storing complete Concordia checkpoints |
| LLM concurrency | AgentSociety dispatcher |
| Infrastructure tracing and failure isolation | AgentSociety 2 |
| Starting-world compilation | Existing SWORLDMODEL compiler |
| Evidence input and grounding boundary | SWORLDMODEL |
| Counterfactual branching and comparison | New SWORLDMODEL layer |
| Behavioral calibration | Later pass (not this run) |

Hard rules derived from the directive:

- One local runtime: Concordia. One live actor-memory system per branch:
  Concordia. One local action resolver: the Concordia Game Master. One
  distributed job/concurrency layer: AgentSociety 2. One counterfactual
  comparison layer: SWORLDMODEL.
- The old SWORLDMODEL runtime must not run underneath, beside, or after
  Concordia; Concordia actions must not pass back through the old world
  resolver. The old runtime is quarantined behind a legacy flag only after the
  new engine passes every acceptance gate; it is not deleted in this pass.
- Upstream code is preserved as complete, unchanged units (pinned git deps,
  submodules, or complete vendored snapshots). No selected-file pseudo-forks,
  no monkey-patching, no from-memory reimplementation. `third_party/`
  (UPSTREAM_LOCK.json, THIRD_PARTY_NOTICES.md, INTEGRATION_METHOD.md,
  PATCHES.md) records the pins; PATCHES.md initially records zero patches.

## Integration sequence

1. **Hard gate before compiler integration**: prove Concordia end-to-end with
   two literal, manually written fixtures (no compiler import, no evidence
   retrieval, no LLM-generated world fields, no AgentSociety).
2. **Concordia local backend**: stock or minimally wrapped Concordia runs one
   complete branch; then one thin **minimum agency guard** (the Game Master
   may not permanently commit a voluntary decision for another actor without
   giving that actor its own turn) — an adapter/validator/event-splitter, not
   a Game Master fork.
3. **Counterfactual manager**: freeze one base snapshot; clone per candidate;
   apply exactly one intervention per branch; no cross-branch state; explicit
   trace-based outcome evaluation and ranking.
4. **AgentSociety Stage A** — branch-level distributed execution: AgentSociety
   schedules complete, self-contained Concordia simulations as independent
   jobs. No actor-level distribution.
5. **AgentSociety Stage B** — whole-branch persistence/recovery: each complete
   Concordia branch checkpoints as one opaque versioned unit in an
   AgentSociety workspace; save/restore equivalence must be deterministic.
6. **AgentSociety Stage C** — infrastructure-only scale proof: 100 concurrent
   or batched jobs, 1,000 lightweight scripted/shallow jobs, bounded
   concurrency, failure isolation, interrupt/resume, complete result
   collection. Infrastructure only — never claimed as societal realism.
7. **Compiler connection** (only after frozen manual fixtures pass):
   deterministic `CompiledDecisionWorld → ConcordiaInitializationPlan →
   validated Concordia objects` adapter, documented field-by-field in
   `docs/engine_migration/COMPILER_TO_CONCORDIA_MAPPING.md`, proven by
   information-leak (canary) and mapping-correctness tests.

Explicitly out of scope this pass: causal/household/community partitions,
cross-partition synchronization, distributed Game Masters, actor-level
reconstruction through AgentSociety, one global Game Master, calibration,
population realism, full action search.

## Fixed SWORLDMODEL-owned contracts

Versioned, code-owned schemas: `DecisionProblem`, `CompiledDecisionWorld`,
`InterventionCandidate`, `SimulationSnapshot`, `BranchResult`,
`RecommendationResult`, plus the code-owned `ConcordiaInitializationPlan`.
Code owns structure, IDs, hashes, timestamps, seeds, provenance, statuses.
The LLM fills only bounded semantic fields. Strict schema validation, then
separate semantic validation; invalid objects are rejected, never silently
repaired. No scenario-specific schemas. No arbitrary quantitative social
mechanics (no invented persuasion/trust/influence weights).

## Package shape (recommended by the directive)

`sworldmodel/` with `decision/`, `compilation/`, `backends/concordia_local/`,
`backends/agentsociety/`, `counterfactuals/`, `outcomes/`, `reporting/`,
`legacy/existing_runtime/`. Actual layout may differ where cleaner, but the
separation of responsibilities is preserved.

## Control plane

The committed, live-verified hook control plane (`.claude/**`,
`.agent-run/**`, `tests/control_plane/`) is authoritative and is not
recreated, bypassed, or edited outside a recorded `hook_maintenance` phase.
Long-running work goes through `.claude/tools/run_monitored.py`. Evidence is
current-SHA receipts recorded with `.claude/tools/record_receipt.py`.
