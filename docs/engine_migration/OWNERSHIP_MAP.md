# Ownership Map — one authoritative owner per responsibility

From the master directive's ownership table, made concrete by the audits
(exact classes/APIs verified in `audit_raw/*.md`). One owner per
responsibility; no second implementation may compete.

| Responsibility | Owner | Concrete mechanism (verified API) |
|---|---|---|
| Local simulation runtime loop | **Concordia** | `concordia.environment.engines.sequential.Sequential.run_loop` (Simultaneous available later) |
| Actor observation lifecycle | **Concordia** | `EntityAgent.observe` phase machine; `MakeObservation` + `ObservationQueue` |
| Actor action lifecycle | **Concordia** | `EntityAgent.act` with `ActionSpec`; entity prefabs `basic`/`minimal` |
| Local action resolution | **Concordia Game Master** | `SwitchAct` + `EventResolution(event_resolution_steps=…)`; single commit primitive `gm.observe('[event] …')` |
| Actor memory and components | **Concordia** | per-entity `AssociativeMemoryBank` / `ListMemory` + agent components |
| Local shared narrative state | **Concordia GM memory** | shared GM memory bank (`allow_duplicates=True`) |
| Minimum agency guard | **SWORLDMODEL adapter layer** (thin) | final `event_resolution_steps` entry (public param); fallback: engine subclass around `resolve()`; never a GM fork |
| Outer distributed orchestration | **AgentSociety 2** | `AgentSociety` + `step_agent_batch` Ray tasks; custom branch-agent subclass of `AgentBase` |
| Whole-branch persistence and recovery | **AgentSociety workspaces** storing complete Concordia checkpoints | Concordia `make_checkpoint_data`/`load_from_checkpoint` blob + SWORLDMODEL sidecar, written atomically under `agents/agent_NNNN/state/` |
| LLM concurrency | **AgentSociety dispatcher** | `LLMClient` + `AdaptiveSemaphore` (AIMD) per process; litellm Router |
| Infrastructure tracing and failure isolation | **AgentSociety 2** | sharded trace sinks (injected `TraceProxy`), per-agent try/except in `step_agent_batch`; BranchResult collection owned by SWORLDMODEL because the society driver discards per-agent results |
| Starting-world compilation | **Existing SWORLDMODEL compiler** | `compiler.scene_pipeline.compile_scene` (minimal_scene_v1), unchanged |
| Evidence input and grounding boundary | **SWORLDMODEL** | compiler evidence-package block; `evidence_mode` metric |
| Compiler→engine translation | **SWORLDMODEL** (new, deterministic) | `CompiledDecisionWorld → ConcordiaInitializationPlan → validated Concordia objects`; no LLM calls |
| Counterfactual branching and comparison | **SWORLDMODEL** (new) | counterfactual manager: frozen base snapshot, one intervention per branch, explicit metrics, ranking |
| Outcome evaluation | **SWORLDMODEL** (new, code-owned) | trace/world-state evaluators; false-at-genesis + cite-committed-events rules ported from `NLResolution` spec; LLM may explain, never override |
| Fixed product contracts | **SWORLDMODEL** | DecisionProblem, CompiledDecisionWorld, InterventionCandidate, SimulationSnapshot, BranchResult, RecommendationResult (+ ConcordiaInitializationPlan) |
| Determinism control in tests | **SWORLDMODEL test harness** | seeded rng patching at branch boundaries + `randomize_choices=False` + scripted models (upstream source untouched) |
| Behavioral calibration | **Later pass** | explicitly out of scope |

Single-writer rule: the implementation-agent owning a subsystem in
`.agent-run/TASK_GRAPH.json` is the only writer of that subsystem's files
during its task; reviewers are read-only.
