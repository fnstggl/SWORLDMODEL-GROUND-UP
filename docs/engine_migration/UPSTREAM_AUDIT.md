# Upstream Audit — Concordia and AgentSociety 2

Synthesis of the full read-only audits (2026-08-03). Full cited evidence:
`audit_raw/CONCORDIA_AUDIT.md` and `audit_raw/AGENTSOCIETY_AUDIT.md`.
Audited SHAs: concordia `7779a4c9f96bad10816d88c54e4cb17d53ac5222`
(fnstggl fork of google-deepmind/concordia, gdm-concordia 2.4.0, Apache-2.0);
agentsociety2 `6e9fc2e79f89f65a3e3d0d7899e380f7394099be` (fnstggl fork of
tsinghua-fib-lab/agentsociety, packages/agentsociety2 2.8.4, Apache-2.0).
Executed baselines: Concordia core suite 560 passed / 0 core failures;
AgentSociety2 suite 387 passed / 0 failures (see PHASE0_BASELINE.md).

## Concordia — what we use, exactly

**Runtime loop we adopt unchanged**: `Engine.run_loop` (Sequential first;
Simultaneous available) with the exact per-step order: terminate check → next
game master → observations fan-out to all entities → next_acting +
next_action_spec → `entity.act(spec)` → `resolve()` → **the single event-commit
primitive** `gm.observe('[event] …')` (`engines/sequential.py:170`). GMs and
actors are both `EntityAgentWithLogging` with the phase machine
READY→PRE_ACT→POST_ACT→UPDATE (actors) and SwitchAct dispatch on GM output
types. Construction: prefab-based `prefabs.simulation.generic.Simulation` or
fully programmatic (engines only require `entity_lib.Entity`) — both public,
both test-covered upstream.

**Components usable unchanged for the two-actor gate (Phase 4)**: entity
prefabs `basic`/`minimal` (private per-entity memory banks are structural);
private context via `Constant` goal / `memory_state` preload /
`FormativeMemoriesInitializer` per-player context; shared context via
`shared_memories` or GM premise; initial observations via
`MakeObservation.add_to_queue` / `ObservationQueue`; cutoff via
`max_steps` + `Terminate`/`SceneBasedTerminator`; full trace via `raw_log` +
`SimulationLog` + GM `[event]` memory stream; `dialogic` GM prefab for pure
conversation, `generic` GM for narrative resolution.

**Default-GM unrestricted powers** (documented for later restriction, per the
directive; do not remove before the unmodified baseline works):
1. Invent facts — `MakeObservation` LLM fallback on empty queue
   (`allow_llm_fallback=True` default); SwitchAct YOLO fallbacks; GM
   instructions authorize invention; `WorldState.post_act`.
2. Decide another actor's voluntary choice — RESOLVE chain rewrites events
   freely; `AccountForAgencyOfOthers` is itself LLM-driven and can commit a
   consulted player's action on a Yes; `Conversation` invents lines for
   non-player names; `maybe_inject_narrative_push` licenses NPC volition.
3. Choose observers — `notify_observers=True` open question;
   `SendEventToRelevantPlayers` per-player yes/no.
4. Determine feasibility — no structured system; optional chain steps only.
5. Declare terminal results — generic GM prefab registers **no** terminate
   component, so the LLM YOLO yes/no can end the run any step.
6. Silently introduce causal events — `maybe_inject_narrative_push` is the
   FIRST step of the generic default resolution chain (random complication
   injection on every resolution); MakeObservation fallback events.

**Consequences adopted into our design**:
- Our Phase 4+ GM must be assembled explicitly (component choice is
  configuration, not forking): deterministic terminate component; fixed or
  explicit acting order where required; `event_resolution_steps` without
  `maybe_inject_narrative_push`; `MakeObservation(allow_llm_fallback=False)`
  where invention is not acceptable; observer selection made explicit.
- **Minimum agency guard seam (Phase 5)**: a final entry in
  `EventResolution(event_resolution_steps=[…, guard])` — a public constructor
  parameter; the guard sees the fully-resolved candidate event before observer
  notification and before the engine's `[event]` commit, and can veto/split.
  Fallback seam: engine subclass overriding `resolve()` (the one-line commit
  choke point). No GM fork required. Precedent: `AccountForAgencyOfOthers`.

**Checkpointing** (Stage B basis): `Simulation.make_checkpoint_data()` /
per-step `save_checkpoint` / `load_from_checkpoint` with an identically
constructed Simulation — component-complete (memory banks incl. embeddings,
observation queues, next-acting cursors, raw_log). **Not covered — the
SWORLDMODEL sidecar owns**: RNG state (unseeded per-document numpy rng +
global `random`), engine cursor (steps done, active GM, premise-delivered
flag — resume restarts at steps=0 and re-observes the premise), config/model
identity, measurements. Safe branch point = end-of-step (`checkpoint_callback`).

**Determinism**: NOT reachable via public configuration alone. With
`NoLanguageModel`/`MockModel`, multiple-choice answers are still shuffled by
unseeded `np.random.default_rng()` per `InteractiveDocument`, plus global
`random` in GM components; `randomize_choices=False` exists for actors'
`ConcatActComponent` but not for SwitchAct GM paths. Deterministic tests
(gate E) therefore seed/patch `np.random.default_rng` and `random` at branch
boundaries in **our test harness** (not in upstream source), set
`randomize_choices=False` where exposed, and use scripted/fixed-response
models. This is a test-harness responsibility, recorded in the risk register.

**Offline models**: `NoLanguageModel`, `RandomChoiceLanguageModel` (seedable),
`testing/mock_model.MockModel`; the whole upstream core suite runs offline.

**Dependencies**: Python ≥3.12 (hard floor), setup.py install, core deps
absl/numpy≥1.26/pandas/tenacity/etc.; Apache-2.0. Fork-specific defect: the
fork's added `ScriptedByEntityModel` breaks no-arg prefab enumeration used by
`examples/` tests (20 failures, examples-only; core unaffected).

## AgentSociety 2 — what we use, exactly

**Reality check vs docs** (verified): no TraceActor / replay actor — trace and
replay are per-process sharded append sinks; only long-lived actor is the
EnvRouterActor; `examples/advanced/01_custom_agent.py` is stale vs the current
arg-less `AgentBase.__init__` API. Trust the audit, not the docs.

**Branch-executor integration choice (Stage A)** — ranked by the audit:
- **Option 1 (chosen for Stage A/B)**: custom `AgentBase` subclass whose
  `step()` runs one complete Concordia branch; driven by `AgentSociety`.
  One branch = one agent = one workspace. Stock machinery exercised:
  `create_agents_batch`, `step_agent_batch` (Ray tasks, per-agent try/except
  isolation, asyncio.gather in-batch), workspace persistence, society
  checkpoint/resume (`SOCIETY.json`/`SOCIETY_STEP.json`, atomic), per-task
  token deltas, per-agent trace writers.
- **Option 2 (kept for the equivalence harness)**: direct public primitives —
  `init_dispatchers()` → `build_service_proxy(...)` → `create_agents_batch.remote`
  → `step_agent_batch.remote` — returns per-job `{ok|error}` + token_stats to
  the driver directly.
- Option 3 (env-module jobs) rejected: serializes all jobs through one actor
  process; codegen sandbox actively hostile to opaque jobs.

**Known caveats our executor must own** (all verified):
1. `AgentSociety.step()` **discards per-agent results** — BranchResults are
   collected from branch workspaces (files we write atomically), and/or via
   Option 2 driver-side results; never inferred from "the run completed".
2. Tracing requires **injecting** `build_service_proxy(..., trace=True)` —
   the society's self-built proxy sets trace=False.
3. `AGENT.json` writes are **non-atomic** upstream — all SWORLDMODEL-owned
   artifacts (BranchResult, checkpoints) use tmp+`os.replace`; `AGENT.json`
   treated as best-effort metadata.
4. Concurrency bounds for minutes-long jobs: `batch_size=1` +
   `AGENTSOCIETY_LLM_RAY_MAX_WORKERS` = desired parallelism (in-batch gather
   is unbounded); per-process LLM AIMD semaphore (init 16, min 1, uncapped up)
   is the LLM brake.
5. Custom agent registration: file under `custom/agents/` discovered by the
   registry; set `WORKSPACE_PATH` explicitly for Ray workers.
6. Opaque blobs: supported — write bytes directly under the agent workspace
   `state/` (e.g. `state/concordia_checkpoint.json`); framework never scans it.
7. Import-time requirement: `AGENTSOCIETY_LLM_API_KEY` must be set (dummy OK
   for offline) or `import agentsociety2` raises at module load.
8. No Ray-less society path; `ray.init` is local single-node;
   shared-filesystem assumption (single node) for workspaces.
9. Env router is mandatory for `AgentSociety` — a trivial concurrency-safe
   `EnvBase` module suffices for branch execution (branches don't need env
   tools); pass `EnvRouterProxy` over the actor, never an in-process router
   through the Ray boundary.
10. `mcp` dependency must be pinned `<2` in the environment (floating bound
    resolves to incompatible mcp 2.x).

**Failure modes to test (gate I)**: silent per-agent failure drop (we collect
explicitly); Ray cluster death mid-run; LLM unreachable (LLMDispatchError with
`rate_limit_like` flag — provider failures are never simulated outcomes);
corrupted `AGENT.json` (permanent silent per-agent failure — detect via our
own result files); atomic society checkpoints fail resume loudly.

## Integration-level comparison (directive requirement)

- **Branch-level execution** (AgentSociety distributes complete Concordia
  simulations): fully supported today by public APIs on both sides; preserves
  stock Concordia exactly; chosen for this pass.
- **Actor-/partition-level execution** (AgentSociety reconstructs Concordia
  actors): would require representing live Concordia component objects inside
  AgentSociety workspaces and crossing Ray boundaries per actor turn — far
  more invasive, no supported seam identified; deferred per the directive's
  later-gated stage, to be justified only by a measured failed requirement of
  branch-level execution.
