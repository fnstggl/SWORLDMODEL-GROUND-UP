# Integration Plan — grounded in the audits

Phases follow the directive exactly; this plan makes each phase concrete with
the verified APIs from `audit_raw/*.md`. Task contracts live in
`.agent-run/TASK_GRAPH.json`; this document is the engineering how.

## Phase 1 — dependency preservation and compatibility (partially proven)

- **Pin method: exact Git dependencies at immutable SHAs** (directive's
  preferred method; both packages install cleanly from checkouts —
  proven in PHASE0_BASELINE.md). `third_party/UPSTREAM_LOCK.json` records
  repo, SHA, method, license, date; `INTEGRATION_METHOD.md` records exact
  environment-recreation commands (local checkout at pinned SHA is primary;
  `pip install git+<fork-url>@<sha>` fallback). No vendored source trees →
  no upstream files inside this repo to drift; `UPSTREAM_PROTECTED_PATHS.json`
  still protects the reserved `third_party/{concordia,agentsociety}/` prefixes
  against accidental divergent copies.
- Environment: `/home/user/engine-env` (Python 3.12.3) with gdm-concordia,
  agentsociety2, `mcp<2` pin, test plugins; triple import coexistence proven.
  `PATCHES.md` states: no upstream modifications exist.
- Gate A inputs: SHAs recorded; upstream suites green in our env (core);
  reproducible install commands; licenses (both Apache-2.0) in
  THIRD_PARTY_NOTICES.md.

## Phase 2 — upstream contract tests (ours, against pinned upstream)

New tests under `tests/engine_contracts/` (new directory → does not disturb
freeze tests; system-python suite excluded via collection guard since these
run in the engine env):
- Concordia: observe/act lifecycle order; component phase machine; GM
  SwitchAct dispatch; EventResolution custom final-step hook (the guard seam)
  actually receives and can rewrite the event; memory persistence;
  checkpoint round-trip equivalence (their checkpoint_test pattern, our
  assertions); deterministic-model + seeded-rng harness produces identical
  two-step traces twice (the gate-E enabling proof).
- AgentSociety: workspace create/restore round-trip; `step_agent_batch` with a
  stub agent — per-agent failure isolation observed from returned results;
  opaque blob under `state/` survives restore; injected TraceProxy produces
  spans; token deltas returned; bounded concurrency observed with
  batch_size=1 (N tasks ≤ num_cpus concurrently).
- Cross: dummy-credential import pattern; `ServiceProxy` pickling with
  `EnvRouterProxy`.

## Phase 3 — contracts + frozen fixtures

`sworldmodel/decision/contracts.py` (stdlib dataclasses + strict validators;
no new runtime deps for the product package): the six directive contracts +
`ConcordiaInitializationPlan`, all with `schema_version`, canonical JSON
serialization, reject-unknown-fields, code-owned IDs/hashes/seeds. Semantic
validation separate from schema validation. Full rejection-test battery from
the directive. Then commit the three manual fixtures
(`tests/fixtures/best_action/*.yaml`) + recorded hashes + expected
deterministic results.

## Phases 4–5 — Concordia local baseline + agency guard

- Fixture 1 (individual_reply shape) and a second, structurally different
  manual scenario, built programmatically: explicit prefab dict (never
  package-wide discovery), entity prefab `basic`/`minimal` per actor with
  private context; GM assembled explicitly: `NextActing` fixed order where
  scripted, `MakeObservation(allow_llm_fallback=False)` + queued initial
  observations, `EventResolution` chain WITHOUT `maybe_inject_narrative_push`,
  deterministic `Terminate` policy + max_steps cutoff; scripted/mock models
  first, seeded-rng harness for determinism; three clean runs each; canary
  strings for private/shared containment; no compiler import (enforced by an
  import-graph test).
- Agency guard: final `event_resolution_steps` callable owned by
  `sworldmodel/backends/concordia_local/` — detects a voluntary decision by a
  non-active actor in the candidate event, and rewrites to the attempt-only
  form (delivery without decision), forcing the affected actor's own turn.
  Discriminating tests: forced-reply event is split; mechanical consequence
  passes through untouched; loop still completes.

## Phase 6 — counterfactual manager (local)

`counterfactuals/`: build base world once → freeze `SimulationSnapshot`
(Concordia checkpoint blob + sidecar: seed state, step budget, config
identity, compiler artifact hash) → per candidate: fresh Simulation from the
same plan + snapshot, apply exactly one InterventionCandidate at the
code-owned insertion point (queued observation/event to the acting entity at
t0), run, collect `BranchResult` from the trace; identical-candidate
determinism and cross-branch canary isolation tests; candidate-order
invariance test.

## Compiler adapter (after fixtures pass)

`compilation/existing_compiler_adapter.py`: `final_scene_manifest.json` +
`input.json` → CompiledDecisionWorld → deterministic
ConcordiaInitializationPlan (pure function, no LLM). Field mapping per the
directive's table with real source paths (audit §(b)); `starting_events[].time`
and provenance ride the SWORLDMODEL sidecar; `resolution` goes only to the
evaluator spec (RESOLUTION_CANARY proves containment). Manual-fixture vs
compiler-produced equivalence test. COMPILER_TO_CONCORDIA_MAPPING.md documents
every field with validation + tests.

## Phase 7 — AgentSociety branch executor (Stage A)

`backends/agentsociety/branch_executor.py` + custom agent
`custom/agents/concordia_branch_agent.py` (registered via the custom scanner;
`WORKSPACE_PATH` set): one branch per agent; `step()` deserializes the
ConcordiaInitializationPlan + candidate from `config.json`/`state/`, runs the
complete Concordia simulation in-process, writes `state/branch_result.json`
atomically. Trivial concurrency-safe `EnvBase` module for the mandatory
router; injected ServiceProxy with trace=True; batch_size=1;
`AGENTSOCIETY_LLM_RAY_MAX_WORKERS` = branch parallelism. Local-vs-distributed
equivalence under deterministic models via the Option 2 primitives harness.
Failure isolation: one deliberately failing branch; others complete; failure
visible in collected BranchResults.

## Phase 8 — whole-branch persistence (Stage B)

Branch agent checkpoints the complete Concordia simulation
(`make_checkpoint_data()` + sidecar) to `state/` at a step boundary; releases;
restore path constructs the same Simulation config and `load_from_checkpoint`,
passes `premise=''`, remaining-step budget from sidecar, re-seeds rng from
sidecar. Stage gate: run-to-checkpoint → continue vs restore → continue
produce the same deterministic trace and result.

## Phases 9–11 — vertical slices + infrastructure proof

- Phase 9: fixture 1 end-to-end through the full path (compiler-produced
  world allowed now), deterministic ranking `concise_relevant` first; live
  smoke when credentialed.
- Phase 10: fixture 2 (five actors, decision rule, veto); deterministic
  Candidate-2 success; GM never casts votes (guard tests).
- Phase 11 (Stage C): 100 concurrent/batched jobs + 1,000 scripted/shallow
  jobs through the branch executor with scripted models; monitored runner
  with explicit progress source (completed/total units from collected
  BranchResult files); interruption + resume; injected failures; aggregate
  equality (results == sum of per-branch records); labeled
  SYNTHETIC INFRASTRUCTURE TEST.

## Phase 12 — frozen final acceptance

Per the directive and `.claude/HOOKS_README.md` §5: freeze SHA, mode
`frozen_acceptance`, full suite from the beginning through `run_monitored.py`,
reviewers, adjudicator, ACCEPTANCE_STATUS gates.

## Explicitly deferred

Actor-level distribution, partitions, calibration, population realism, action
search, evidence retrieval — per the directive's later-gated stages.
