# Final Architecture — as built

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

This document describes the architecture **as it exists in the code**, not as
planned. Every structural claim names the module that implements it; the
proving tests are indexed in [TEST_MATRIX.md](TEST_MATRIX.md). Where an older
planning document (`INTEGRATION_PLAN.md`, `OWNERSHIP_MAP.md`,
`CONTRACTS_DESIGN.md`) disagrees with this one, this one reflects the code.

## 1. What the system is

SWORLDMODEL is an **intervention-centered best-action simulator**: given one
compiled starting world and several candidate actions for one decision owner,
it runs one isolated social-simulation branch per candidate on the stock
Concordia engine, measures each outcome from the recorded event trace with
cited metrics, and returns the best-performing action **among those tested**.
It never claims a global optimum, and no LLM ever chooses or overrides the
winner (`sworldmodel/outcomes/ranking.py`; the required limitation phrase is
contract-enforced, `sworldmodel/decision/contracts.py::REQUIRED_LIMITATION_PHRASE`).

## 2. Package map (as built)

New engine packages (this pass), all under `sworldmodel/`:

| Package | Role | Import-time deps |
|---|---|---|
| `sworldmodel/decision/` | The six frozen versioned contracts + `ConcordiaInitializationPlan`, strict schema validation (`contracts.py`), semantic validation (`validation.py`), code-owned ID registry (`registry.py`), strict fixture loader (`fixture_loader.py`) | stdlib only |
| `sworldmodel/compilation/` | Deterministic compiler bridge: `existing_compiler_adapter.py` (compiled scene/artifact set → `CompiledDecisionWorld` + sidecar), `decision_route.py` (`DecisionProblem` route, user candidates, one-fixed-schema candidate generator) | stdlib only (one lazy call-time import of `compiler.scene_schema.validate_manifest_shape`) |
| `sworldmodel/backends/concordia_local/` | `planner.py` (world → plan, pure), `builder.py` (plan → live stock Concordia objects), `runner.py` (one branch through `Sequential.run_loop`), `guard.py` (minimum agency guard), `checkpoint.py` (whole-branch capture/restore) | planner: stdlib; builder/runner: optional `gdm-concordia` (Python ≥ 3.12), loud ImportError without it |
| `sworldmodel/counterfactuals/` | `snapshot.py` (one frozen base plan + genesis snapshot, per-branch seed derivation), `branch.py` (exactly one intervention per branch, proven by `diff_plans`), `manager.py` (serial seeded local execution → `BranchResult`s) | stdlib; engine imported lazily in the run path |
| `sworldmodel/backends/agentsociety/` | `branch_executor.py` (distributed execution of complete branches through real AgentSociety primitives; Stage B checkpoint/interrupt/resume), `branch_agent_template.py` (the `AgentBase` subclass source materialized into workspaces) | stdlib + sworldmodel; `agentsociety2`/`ray` imported lazily in the run call |
| `sworldmodel/outcomes/` | `metrics.py` (cited readings from the trace), `evaluator.py` (per-branch `outcome_metrics` from injected predicates), `ranking.py` (declared-order deterministic ranking → `RecommendationResult`) | stdlib only |
| `sworldmodel/reporting/` | `recommendation.py` (recommendation report), `trace_report.py` (complete causal trace report), `common.py` (canonical serialization) — deterministic artifacts, contract-revalidated | stdlib only |

Retained production route (untouched by this pass): `compiler/` — the
natural-language scene compiler (`compile_question.py` CLI,
`compiler/scene_pipeline.py`, `scene_schema.py`, …). Legacy runtime
(quarantined, still physically present, not on the new path):
`sworldmodel/semantic_runtime/` + `run_simulation.py`, the old kernel
resolver `sworldmodel/engine.py`, and `compiler/legacy/` behind
`--compiler legacy`. See
[RESPONSIBILITY_OWNERSHIP.md](RESPONSIBILITY_OWNERSHIP.md) §4 for the exact
upstream / adapter / legacy classification.

The product package remains **stdlib-only** (`dependencies = []`):
`import sworldmodel` works on Python 3.11 without Concordia, AgentSociety,
Ray, or numpy installed; engine-facing modules degrade with loud
ImportErrors only when actually requested (package `__init__` docstrings,
proven by `tests/engine_robustness/test_missing_credentials.py::
test_product_import_survives_and_engine_boundary_names_the_variable`).

## 3. One best-action request, end to end

```
                     ┌────────────────────────────────────────────────┐
 caller input        │  A. WORLD SOURCE (exactly one of)              │
 ─────────────       │  1. frozen manual fixture  (YAML)              │
 DecisionProblem     │     decision/fixture_loader.py (strict)        │
 (decision owner,    │  2. compiled scene / artifact set              │
  desired outcome,   │     compilation/existing_compiler_adapter.py   │
  success criteria,  │     (deterministic, LLM-free, refuses defects) │
  candidates or      └───────────────┬────────────────────────────────┘
  generation                         ▼
  permission)              CompiledDecisionWorld            (frozen contract)
        │                            │
        ▼                            │
 B. ROUTE  compilation/decision_route.py::prepare_decision_inputs
    – validates problem ↔ world (owner must equal the world's single
      insertion actor; never re-targeted)
    – builds user candidates (`user_NNN`) and, only with explicit
      permission + a supplied generator model, generated candidates
      (`gen_NNN`, one fixed schema, one model call, strict parse)
        │
        ▼
 C. BASE FREEZE  counterfactuals/snapshot.py
    – build_base_plan → backends/concordia_local/planner.py
      (pure deterministic mapping; ConcordiaInitializationPlan)
    – build_base_snapshot → SimulationSnapshot (genesis identity:
      plan content hash, seed material, step budget, provenance)
        │
        ▼
 D. BRANCHES  counterfactuals/branch.py — per candidate:
    – apply_intervention: candidate text appended ONLY to the insertion
      actor's initial_observations (the single code-owned boundary)
    – diff_plans proves the branch differs NOWHERE else
    – derive_branch_seed(seed, candidate_id): code-owned per-branch seed
        │
        ├──────────────── LOCAL (serial) ───────────────┐
        ▼                                               ▼
 E1. counterfactuals/manager.py            E2. backends/agentsociety/
     run_candidates[_detailed]                 branch_executor.py
     – strictly serial, each branch            run_candidates_distributed
       inside its own seeded RNG scope         – same preflight, same
     – per-branch failure isolation              plans/seeds; each branch
       (error → that BranchResult,               is ONE complete job via
       siblings unaffected)                      init_dispatchers →
        │                                        create_agents_batch →
        │                                        step_agent_batch (Ray)
        │                                      – file-authoritative
        │                                        collection, dual-channel
        │                                        failure evidence
        └──────────────────┬────────────────────┘
                           ▼
 F. ONE BRANCH  backends/concordia_local/{builder,runner}.py
    – builder: plan → live stock Concordia objects (actors + GM from the
      audited public APIs; guard installed as the FINAL
      event_resolution_steps element; no narrative-push step, no
      model-improvising GM fallback)
    – runner: unmodified upstream Sequential.run_loop to termination or
      the step budget; captures committed [event] stream, per-actor
      memories, raw log, guard_interventions, step/wall stats
    – terminal status: 'cutoff' or 'incomplete' only (rule R3 — an
      engine stop is never a verdict)
                           ▼
 G. RESULTS   decision/contracts.py::BranchResult (one per candidate,
              caller's order, failures reported in place)
                           ▼
 H. OUTCOMES  outcomes/{metrics,evaluator,ranking}.py
    – injected metric predicates read ONLY the recorded trace/terminal
      state; every value cites the events it was computed from
    – optional caller status_rule decides success/failure from measured
      metrics (never from narration; refused on infrastructure errors)
    – rank_branches: declared metrics in declared order, descending,
      polarity never inferred; candidate_id lexicographic only as the
      final DISCLOSED tie-break; RecommendationResult carries the fixed
      limitation phrase ("best ... among the candidates tested")
                           ▼
 I. REPORTS   reporting/{recommendation,trace_report}.py
    – deterministic canonical-JSON artifacts, content-hashed, every
      embedded contract strictly re-validated
```

Proving tests, end to end: fixture 1
`tests/engine_counterfactuals/test_fixture1_deterministic_acceptance.py`
(measured winner `concise_relevant`, three byte-identical full-pipeline
runs), fixture 2 `tests/engine_team/` (5 actors, 11 engine steps, authority
and votes), the compiler route `tests/engine_compilation/` (manual-vs-
compiler plan equivalence and byte-identical traces), the individual slice
`tests/engine_individual/` (scripted + mock + live smoke), distributed
equivalence `tests/engine_distributed/test_stage_a_equivalence.py`.

### 3.1 Insertion boundary (the only place a candidate enters)

`CompiledDecisionWorld.intervention_insertion_point` names one actor.
`counterfactuals/branch.py::apply_intervention` appends the candidate's
action text to exactly that actor's `initial_observations` after the base
plan is frozen; `diff_plans` (called on every branch build) raises if the
branch plan differs from the base plan anywhere outside the insertion path
prefix. Cross-branch leakage is canary-tested
(`tests/engine_counterfactuals/test_base_isolation.py`,
`tests/engine_compilation/test_information_leaks.py`).

### 3.2 Guard seam (minimum agency guard)

`backends/concordia_local/guard.py` is a deterministic plain callable with
the audited upstream `event_resolution_steps` signature. The builder appends
it as the FINAL element of the `EventResolution` chain, so it sees the fully
resolved candidate event before observer notification and before the
`[event]` commit. Default-on via the plan (`agency_guard_enabled`,
`PLANNER_VERSION = concordia_local_planner_v2`); the identity step occupies
the slot when disabled; an injected `guard_step` replaces it outright.
Detection classes (v3), rewrite rule (never inventing content), and the
honestly documented residuals are in the guard module docstring; residuals
are summarized in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §2. Rewrites
are recorded as `guard_interventions` in the runner record (distributed:
persisted as `state/runner_record.json`, referenced from
`BranchResult.artifact_paths`).

## 4. Checkpoint / restore path (Stage B, as built)

One checkpoint == one complete branch, captured only at the engine's
end-of-step boundary (`backends/concordia_local/checkpoint.py`):

- **What Concordia serializes itself**: every entity's `get_state()`
  (act component + every context component, including full memory banks,
  observation queues, next-acting cursors, event-resolution state,
  terminate flag), restored through the same public `set_state` path. The
  blob's top level mirrors the upstream payload shape
  (`entities` / `game_masters` / `raw_log`).
- **Deliberate deviation from the plan-era docs**: upstream
  `Simulation.make_checkpoint_data()` / `load_from_checkpoint` are NOT
  used — they exist only on the prefab `generic.Simulation` wrapper, and
  this backend builds `EntityAgentWithLogging` objects directly from a
  validated plan. The component-state API those helpers are built on is
  used instead; reconstruction identity is the PLAN, enforced by
  `sidecar.plan_content_hash` at restore.
- **SWORLDMODEL sidecar** (exactly the state the audit proved upstream does
  not capture): evolving `random`-module state, numpy legacy state, seed
  material, engine cursor (steps completed / remaining budget /
  premise-delivered — resume passes `premise=''` because upstream re-observes
  the premise otherwise), model-config identity strings (model OBJECTS are
  never serialized; restore requires behaviorally prompt-pure models),
  intervention identity, plan/artifact hashes, and accumulated
  `guard_interventions`.
- **Cross-process canonical form**: upstream serializes set-derived state as
  `list(set)` with per-process hash-salted order; capture sorts such lists
  (`_canonicalize_state_tree`) and restore compares canonicalized forms
  byte-for-byte. (Today's builder only produces order-preserving
  `ListMemory`, so this is a pinned defensive invariant —
  `tests/engine_checkpoint/test_state_canonicalization.py`.)
- **Restore trust rule**: upstream `EntityAgent.set_state` swallows
  component exceptions and `ListMemory.set_state` re-points its bank at the
  argument list; `restore_branch` therefore refills the original handle and
  enforces post-restore `get_state()` byte-equality as the only trusted
  success signal.

Proven equivalence: run-to-checkpoint/save/continue (A), restore/continue
(A'), and disk-round-tripped restore (B) are full-signature byte-equal under
two seeds, with an RNG-divergence discriminator showing a naive re-seed
resume visibly diverges (`tests/engine_checkpoint/`); the distributed
interrupted-resume run is byte-equal to the uninterrupted distributed run
(`test_distributed_resume.py`). Workspaces persist the blob as
`state/branch_checkpoint.json` (opaque versioned artifact scheduled/stored
by the executor, produced/consumed only by `checkpoint.py` inside workers).

## 5. Model seam

Models are **injected, never constructed** by the engine packages:

- **Local**: `run_candidates*(model_factory=...)` where
  `model_factory(candidate, branch_seed) -> (actor_models, gm_model)` —
  fresh objects per branch (`counterfactuals/manager.py`).
- **Distributed**: a serializable spec, never a live object:
  `model_spec = {"model_builder": "package.module:attribute",
  "params": {...}}`; workers import the dotted reference and call
  `builder(params)` to obtain the same provider contract
  (`backends/agentsociety/branch_executor.py`). The key is `model_builder`
  by recorded decision (DECISIONS, Phase 7 notes).
- **Deterministic tests**: strict scripted models (unmatched prompt fails
  loudly) and a hash-derived mock model with no scenario knowledge
  (test-owned, e.g. `tests/engine_baseline/baseline_helpers.py`,
  `tests/engine_individual/`).
- **Live**: the same seam with an API-backed builder; the Phase 9 smoke leg
  drove DeepSeek (`base https://api.deepseek.com`, requested
  `deepseek-chat`; endpoint served `deepseek-v4-flash`), gated on
  `DEEPSEEK_API_KEY` (`tests/engine_individual/test_individual_slice_live_smoke.py`).
- The GM has **no model-improvising fallback**: every `SwitchAct` dispatch
  key is present and `MakeObservation(allow_llm_fallback=False)`; on the
  scripted baseline, `sample_choice` provably never fires
  (`tests/engine_baseline/`).

Separate transports that already carry deadlines: the semantic-runtime /
compiler LLM transports (`sworldmodel/semantic_runtime/llm.py`,
`sworldmodel/llm_mind.py`). Injected engine models have **no in-branch
timeout seam** (recorded gap G1 — see
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §3).

## 6. Seeds and determinism (as built)

- One caller seed per run; per-branch seeds are code-owned:
  `derive_branch_seed(seed, candidate_id)` (`counterfactuals/snapshot.py`).
- Each branch executes inside `_seeded_branch_scope(branch_seed)`
  (`counterfactuals/manager.py`): seeds the stdlib `random` module, patches
  `numpy.random.default_rng` so every no-argument call yields a fresh
  generator seeded with the branch seed, and re-seeds the numpy legacy
  state; all restored on exit. This is required because upstream Concordia
  draws from unseeded per-document generators and the global `random`
  module (audit_raw/CONCORDIA_AUDIT.md §13).
- **Local execution is strictly serial by design**: the scope patches
  process-global RNG state, so two branches in one process would interleave
  draws. Branch parallelism is process-level, through AgentSociety workers
  (one complete branch per worker), where each worker enters the same scope
  — proven equivalent to local serial execution byte-for-byte
  (`tests/engine_distributed/test_stage_a_equivalence.py`), including a
  candidate whose model consumes per-document RNG
  (`test_worker_rng_equivalence.py`).
- `ConcatActComponent(randomize_choices=False)`; deterministic acting order
  (`NextActingInFixedOrder`) on the deterministic paths.
- Determinism holds across process boundaries and hash seeds: repeats are
  byte-identical under `PYTHONHASHSEED` 0/5/13 (team suite), across fresh
  processes (`tests/engine_robustness/test_cold_startup.py`), and across
  checkpoint/resume (§4).
- Scope of the claim: determinism is proven for **scripted/mock model
  runs**. Live-model runs are inherently non-deterministic and carry
  smoke-level assertions only ([KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §6).

## 7. Distributed execution (Stage A, as built)

`run_candidates_distributed` mirrors the local manager exactly up to the
execution substrate (same preflight, same frozen base, same branch plans and
seeds — it deliberately reuses `manager._preflight`,
`manager._result_from_runner`, `manager._seeded_branch_scope` as the single
source of truth; a recorded SWORLDMODEL-internal private-name reuse, see
[UPSTREAM_COMPONENT_MAP.md](UPSTREAM_COMPONENT_MAP.md) §4), then:

- brings up real AgentSociety: `init_dispatchers()` →
  `build_service_proxy(env=None, trace=...)` →
  `create_agents_batch.remote` → `step_agent_batch.remote` with
  single-branch batches (audit "Option 2" primitives — the ones that return
  per-agent ok/error records and token deltas);
- materializes the branch-agent class source into
  `<workspace>/custom/agents/` and exports `WORKSPACE_PATH` (+ PYTHONPATH)
  **before** `init_dispatchers()` because the Ray job env snapshot freezes
  at first init; when Ray is already up, it adopts the captured
  `WORKSPACE_PATH` and runs a one-task worker probe before submitting;
- enforces concurrency **in code** with a submit-window loop over
  `ray.wait` (at most `parallelism` in flight), and measures observed
  worker overlap from in-worker timestamps;
- collects file-authoritatively with dual-channel agreement: ok=True
  requires `state/branch_result.json` + `state/runner_record.json` and no
  error file; ok=False requires `state/branch_error.json`; any disagreement
  is a `CollectionIntegrityError` naming the branch; every candidate
  submitted exactly once and harvested exactly once.

## 8. Reports, traces, and evidence artifacts

- `build_recommendation_report(problem, candidates, run, evaluated,
  evaluator_spec, provenance_label=...)` → the decision artifact: problem,
  frozen base identity, candidates, per-branch cited evaluations, and the
  `RecommendationResult` computed through the real ranking engine.
- `build_trace_report(...)` → the complete causal trace: plan hashes and
  seeds, committed events in commit order, guard interventions, per-actor
  observation/attempt records, terminal world state, and evaluator
  citations re-resolved against the report's own rows.
- Both are canonical-JSON, content-hashed, deterministic (no wall-clock
  content); committed examples are hash-asserted to regenerate byte-
  identically (`tests/engine_individual/artifacts/`,
  `tests/engine_team/artifacts/`).
- Run-evidence layers outside reports: current-SHA receipts
  (`.agent-run/receipts/`, recorded via `.claude/tools/record_receipt.py`),
  monitored job records (`.agent-run/BACKGROUND_JOBS.json` registry;
  committed durable copies under `tests/engine_scale/evidence/` and
  `tests/engine_robustness/evidence/`). How to read them:
  [RUNBOOK.md](RUNBOOK.md) §7.

## 9. What has been proven — and what has NOT

**Proven** here means: a named test or receipt exists at the current HEAD.
The full suite-by-suite index is [TEST_MATRIX.md](TEST_MATRIX.md).

Proven in this pass:

1. **Exact upstream engines, zero patches.** Both upstreams pinned and
   verified unchanged continuously (`third_party/UPSTREAM_LOCK.json`,
   `third_party/PATCHES.md`, validator check `upstream_checkouts_integrity`).
2. **A best-action request runs end to end, deterministically.** Frozen
   fixture and compiled-artifact routes both produce measured winners with
   cited metrics and byte-identical repeated runs
   (`tests/engine_counterfactuals/`, `tests/engine_compilation/`,
   `tests/engine_individual/`, `tests/engine_team/`).
3. **Actor agency is protected.** The GM cannot commit another actor's
   voluntary decision (guard default-on; discriminating caught/nearby-shape
   tests; proxy-attribution class closed after review finding F1) — within
   the documented detector residuals.
4. **Information containment.** Private/shared/event-visibility/resolution/
   provenance canaries end to end through the real planner+builder+runner
   (`tests/engine_compilation/test_information_leaks.py`,
   `tests/engine_baseline/`).
5. **Counterfactual correctness invariants.** One frozen base, single-
   intervention diffs, cross-branch isolation, identical-candidate byte
   identity, order invariance, failure isolation in place
   (`tests/engine_counterfactuals/`).
6. **Team semantics.** 5-actor scenario with pairwise private isolation,
   meeting fan-out, participant-only follow-ups, an authority flip probe,
   actor-owned votes with a guard-blocked proxy vote
   (`tests/engine_team/`).
7. **Local ≡ distributed** under deterministic models, byte-for-byte, with
   exactly-once accounting, bounded concurrency, and dual-channel failure
   evidence (`tests/engine_distributed/`).
8. **Whole-branch checkpoint/restore equivalence** (A=A'=B, two seeds, RNG
   continuity, interrupted distributed resume) (`tests/engine_checkpoint/`).
9. **100-agent and 1,000-agent infrastructure runs** with exact
   reconciliation, sparse activation, injected-failure isolation, and
   fresh-process checkpoint/resume — **infrastructure only**
   (`tests/engine_scale/`, `PHASE11_SCALE_EVIDENCE.md`).
10. **Operational robustness** across the fourteen gate-I scenarios,
    failures explicit/bounded/recoverable-where-possible, with three
    recorded findings (`tests/engine_robustness/`,
    `OPERATIONAL_ROBUSTNESS_MATRIX.md`).
11. **The pipeline executes against a live model endpoint** (DeepSeek
    smoke: 2 tests, 5 passing executions each, zero transport retries) —
    execution, not realism
    (`tests/engine_individual/test_individual_slice_live_smoke.py`).

**NOT proven** in this pass (claiming otherwise would be false):

1. **No real-world predictive accuracy.** No branch outcome has been
   validated against reality; nothing here is calibrated.
2. **No population realism at any scale.** The 100/1,000-agent runs are
   scripted/shallow infrastructure exercises by construction and are
   labeled as such in every artifact (test-enforced).
3. **No live-model output quality.** Live runs assert structure and
   bounded execution only; they are non-deterministic and their content
   realism is unmeasured.
4. **No global optimum.** Ranking is best-among-tested-candidates under
   the declared metrics; candidate search does not exist.
5. **No evidence grounding.** Compiled worlds are not validated against
   real-world evidence; the compiler's `evidence` input rides the sidecar
   untouched.
6. **No observed/inferred/latent state separation, no confidence
   calibration, no representative population construction, no
   human-behavior calibration** — all deferred by the directive to the
   later realism phase ([NEXT_REALISM_PHASE.md](NEXT_REALISM_PHASE.md)).
7. **No multi-host distribution and no cross-partition interaction** —
   single-host Ray; scale partitions were isolated by design
   ([SOCIETAL_SCALING_PATH.md](SOCIETAL_SCALING_PATH.md)).

Consolidated limitations with impact and workarounds:
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).
