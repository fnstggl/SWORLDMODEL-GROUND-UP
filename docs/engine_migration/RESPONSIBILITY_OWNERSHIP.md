# Responsibility and Ownership — plain language

> Gate J documentation set:
> [FINAL_ARCHITECTURE](FINAL_ARCHITECTURE.md) ·
> [RESPONSIBILITY_OWNERSHIP](RESPONSIBILITY_OWNERSHIP.md) ·
> [UPSTREAM_COMPONENT_MAP](UPSTREAM_COMPONENT_MAP.md) ·
> [IMPLEMENTATION_LOG](IMPLEMENTATION_LOG.md) ·
> [TEST_MATRIX](TEST_MATRIX.md) ·
> [SOCIETAL_SCALING_PATH](SOCIETAL_SCALING_PATH.md) ·
> [KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md) ·
> [NEXT_REALISM_PHASE](NEXT_REALISM_PHASE.md) ·
> [RUNBOOK](RUNBOOK.md)

Three codebases cooperate. Each owns a distinct job, and no second
implementation competes with an owner. This page says, in plain words, who
owns what, and which code in this repository is exact upstream, which is
adapter code we wrote, and which is legacy kept for reference.

## 1. What Concordia owns

Concordia (Google DeepMind's social-simulation library, pinned at
`7779a4c9f96bad10816d88c54e4cb17d53ac5222`) owns **everything that happens
inside one simulation branch**:

- **The actors.** Each simulated person is a stock Concordia
  `EntityAgentWithLogging` with stock components (memory, observation
  handling, action concatenation). We configure them; we do not reimplement
  them.
- **Actor memory.** What an actor has seen and said lives in Concordia's
  own memory components (`ListMemory` + `ObservationToMemory` +
  `LastNObservations`).
- **The Game Master (GM).** The GM that asks "who acts next?", turns an
  actor's attempt into a resolved event, and delivers observations is a
  stock Concordia entity assembled from stock GM components
  (`SwitchAct`, `MakeObservation`, `NextActing`/`NextActingInFixedOrder`,
  `FixedActionSpec`, `EventResolution`, `Terminate`).
- **Event resolution and the simulation loop.** The turn cycle
  (observe → act → resolve → commit `[event]` → notify observers) is
  upstream `Sequential.run_loop`, unmodified.
- **Per-entity state serialization.** Checkpoint content for actors and the
  GM is whatever Concordia's own public `get_state()` returns, restored
  through its own `set_state()` — we never re-shape it.

In short: **if it is social-simulation mechanics inside one branch, it is
Concordia's code doing it.**

## 2. What AgentSociety owns

AgentSociety 2 (Tsinghua FIB-lab's agent platform, pinned at
`6e9fc2e79f89f65a3e3d0d7899e380f7394099be`) owns **how many branches run at
once and where their state lives**:

- **Workspaces.** Every branch (and every scale-test agent) is a
  workspace-bound agent directory (`config.json`, `AGENT.json`,
  `state/*`) created, reconstructed, and persisted by AgentSociety's stock
  workspace machinery.
- **Ray task execution.** Branches run as AgentSociety's own Ray tasks
  (`create_agents_batch`, `step_agent_batch`) inside worker processes.
- **Dispatchers and Ray bring-up.** `init_dispatchers()` owns the Ray
  runtime and the per-process LLM dispatcher plumbing.
- **Distribution mechanics.** Worker scheduling, per-agent failure records,
  token accounting deltas, and trace spans come from AgentSociety's public
  interfaces (`build_service_proxy`, the agent runner module).
- **The custom-agent extension point.** Our branch agent is a subclass of
  AgentSociety's `AgentBase`, registered through their stock
  `custom/agents/` scanner — their supported extension mechanism, not a
  fork.

In short: **if it is about running many complete simulations, persisting
them, or surviving worker failures, it is AgentSociety's code doing it.**

## 3. What SWORLDMODEL owns

SWORLDMODEL (this repository) owns **the decision problem** — everything
that turns "which action should this person take?" into simulations and a
measured answer:

- **The contracts** (`sworldmodel/decision/`): the fixed, versioned data
  shapes — `DecisionProblem`, `CompiledDecisionWorld`,
  `InterventionCandidate`, `SimulationSnapshot`, `BranchResult`,
  `RecommendationResult`, plus the internal
  `ConcordiaInitializationPlan` — with strict validation that refuses
  rather than repairs.
- **The adapter chain** (`sworldmodel/compilation/`,
  `sworldmodel/backends/concordia_local/planner.py`,`builder.py`,
  `runner.py`): deterministic, LLM-free code that maps a compiled world
  into live stock Concordia objects and drives one branch.
- **The guard seam** (`backends/concordia_local/guard.py`): the minimum
  agency guard installed at Concordia's public `event_resolution_steps`
  extension point, so the GM cannot commit a voluntary decision for a
  different actor.
- **Counterfactuals** (`sworldmodel/counterfactuals/`): one frozen base,
  exactly one intervention per branch, seed derivation, serial local
  execution, failure containment.
- **Outcome measurement and ranking** (`sworldmodel/outcomes/`): cited
  trace-based metrics, declared-order ranking, no LLM override — ever.
- **Reporting** (`sworldmodel/reporting/`): deterministic recommendation
  and causal-trace artifacts.
- **The checkpoint sidecar** (`backends/concordia_local/checkpoint.py`):
  only the state upstream provably does not capture (RNG streams, engine
  cursor, plan identity, model-config identity).
- **The distributed driver** (`backends/agentsociety/branch_executor.py`):
  submission, bounded concurrency, and file-authoritative result
  collection over AgentSociety's primitives (kept by us because the stock
  society driver discards per-agent step results).
- **Evidence discipline**: receipts, monitored job records, frozen
  fixtures, and this documentation set.

In short: **if it is about the question, the candidates, the comparison, or
the proof, it is SWORLDMODEL code doing it.**

The directive's integration principle, as built:

```
SWORLDMODEL creates counterfactual branches
        ↓
AgentSociety schedules complete branches
        ↓
Concordia runs each complete local simulation
        ↓
AgentSociety collects BranchResults (file-authoritative, dual-channel)
        ↓
SWORLDMODEL compares measured outcomes
```

## 4. Which code is exact upstream, which is adapter, which is legacy

### 4.1 Exact upstream (pinned SHAs, zero patches)

**No upstream source file lives in this repository, and none was modified
anywhere.** Both engines are installed from complete checkouts pinned to
immutable SHAs (`third_party/UPSTREAM_LOCK.json`):

| Upstream | Pinned SHA | License |
|---|---|---|
| Concordia (`gdm-concordia` 2.4.0) | `7779a4c9f96bad10816d88c54e4cb17d53ac5222` | Apache-2.0 |
| AgentSociety 2 (`agentsociety2` 2.8.4) | `6e9fc2e79f89f65a3e3d0d7899e380f7394099be` | Apache-2.0 |

`third_party/PATCHES.md` states — and continuous enforcement verifies —
**"No upstream modifications exist."** Both pinned SHAs were independently
verified byte-identical to their upstreams' main HEADs at audit time
(`docs/engine_migration/reviews/PHASE_0_2_BOUNDARY_REVIEW.md` C1). The
checkouts are inside the write-block perimeter in every mode, and the
control-plane validator re-verifies each checkout sits clean at its
recorded SHA on every run (`UPSTREAM_LOCK.json.integrity_enforcement`).
The only compatibility measures are environment-level, not source patches:
the `mcp>=1.13.1,<2` version pin, dummy `AGENTSOCIETY_LLM_*` variables for
offline use, and upstream-required test plugins (`third_party/PATCHES.md`).

The exact upstream components we call, and where:
[UPSTREAM_COMPONENT_MAP.md](UPSTREAM_COMPONENT_MAP.md).

### 4.2 Adapter code (written in this pass, SWORLDMODEL-owned)

All new engine code listed in [FINAL_ARCHITECTURE.md](FINAL_ARCHITECTURE.md)
§2: `sworldmodel/decision/`, `sworldmodel/compilation/`,
`sworldmodel/backends/concordia_local/`, `sworldmodel/counterfactuals/`,
`sworldmodel/backends/agentsociety/`, `sworldmodel/outcomes/`,
`sworldmodel/reporting/`. These call upstream **public** interfaces only
and contain no copied upstream code. They are scenario-generic: the
hardcoding guard (`tests/test_hardcoding_guard.py`) scans `sworldmodel/`
and `compiler/` on both interpreters and forbids scenario vocabulary in
production code (one narrow, exactness-tested per-file word allowance:
`{vote, voting}` for `guard.py`).

### 4.3 Retained production route (pre-existing, unchanged)

The natural-language **scene compiler** remains the production compile
route, untouched by this pass: `compile_question.py`,
`compiler/scene_pipeline.py`, `scene_schema.py`, `scene_llm.py`,
`scene_prompts.py`, `scene_validate.py`, `scene_guards.py`,
`scene_adapter.py`, `scene_resolution.py`. The new
`sworldmodel/compilation/` package consumes its **output artifacts**
(`final_scene_manifest.json` + metadata); the single production-code link
is a lazy call-time import of `compiler.scene_schema.validate_manifest_shape`
(the shape gate), proven the only one by AST walk and fresh-interpreter
probe (`tests/engine_compilation/test_mapping_correctness.py`).

### 4.4 Legacy (quarantined, physically present, not on the new path)

Classified in `OWNERSHIP_AND_REPLACEMENT_MAP.md` and unchanged in posture
by this pass:

- `sworldmodel/semantic_runtime/` + `run_simulation.py` — the unreliable
  runtime this project replaces. Still present; the directive forbids
  deleting the legacy path before the replacement passes final acceptance.
  Not imported by any new engine package: the Phase 4 subprocess import
  proof shows zero `compiler`/`semantic_runtime` modules in the engine
  execution path (`tests/engine_baseline/test_no_compiler_import.py`).
- `sworldmodel/engine.py` (the old kernel resolver) and the kernel-demo
  era modules (`checkpoint.py`, `artifacts.py`, `llm_mind.py`,
  `run_worlds.py`, `worlds/`) — reachable only from legacy entry points
  and their own tests. Note: `sworldmodel/__init__.py` still eagerly
  imports the legacy kernel modules (pre-existing, recorded in the Phase 4
  import-proof docstring); importing the package does not execute any
  legacy simulation.
- `compiler/legacy/` — the old multi-stage compiler, already behind
  `--compiler legacy`.
- Kernel modules (`world.py`, `simclock.py`, `events.py`, `actors.py`,
  `info.py`, `actions.py`) — retained as the compiler's genesis-time
  self-check substrate (no event-loop execution on the compile path).

**Rule kept throughout:** no new engine module imports the legacy runtime,
and no legacy resolver touches a Concordia event. The two worlds share only
the frozen contracts and the compiler's output artifacts.

## 5. Ownership during the run (who wrote what)

Single-writer discipline per `.agent-run/TASK_GRAPH.json`: one primary
writer owned each subsystem per phase (`implementation-agent` for
production code, `test-watchdog` for monitored evidence and the
robustness/scale suites, read-only reviewers for findings, the lead for
fold-ins and dispositions). The full phase-by-phase record with commits and
receipts: [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).
