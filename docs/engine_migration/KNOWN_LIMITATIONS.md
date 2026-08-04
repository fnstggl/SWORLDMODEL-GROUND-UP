# Known Limitations — consolidated and honest

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

Every recorded limitation, gap, residual, and disclosed trust boundary,
each with its impact and workaround. Sources: the guard docstring
(`sworldmodel/backends/concordia_local/guard.py`),
`OPERATIONAL_ROBUSTNESS_MATRIX.md` findings, the three boundary reviews
(`reviews/`), `.agent-run/DECISIONS.md`, and
`.agent-run/FAILURE_LEDGER.jsonl`. The product-level NOT-proven list
(realism, calibration, optimality) is in
[FINAL_ARCHITECTURE.md](FINAL_ARCHITECTURE.md) §9 and is not repeated
item-for-item here.

## 1. Scope of every claim

The engine's correctness claims are **deterministic-model claims**: byte
identity, isolation, equivalence, and measured winners are proven under
scripted/mock models. Live-model runs execute the same code path but are
inherently non-deterministic; they carry smoke-level structural
assertions only (§6.1). No real-world accuracy of any kind is claimed.

## 2. Agency guard — documented residual gaps (deterministic detector)

The guard blocks the Game Master from committing voluntary decisions for
non-active actors via six detection classes (guard.py docstring, v3).
Its failure direction is chosen deliberately: over-detection removes text
and offers the affected actor its own turn (recoverable); under-detection
would permanently steal agency. Residuals, all recorded in the docstring:

| Residual | Impact | Mitigation / workaround |
|---|---|---|
| Second-person and "it" subjects; do-support emphatics ("X does agree"); bare-modal futures ("X will agree"); pronoun-possessive nominalizations ("their agreement"); collective possessives ("Morgan's team accepts"); asides longer than one comma pair / 60 chars | A committed event phrased in these shapes could assert another actor's decision undetected | Listed for later hardening; on the DEFAULT constrained path the GM authors no event text (scripted resolution chains; `MakeObservation` fallback disabled), so only actor-authored shapes occur; evaluator anchors independently refuse to COUNT anything not attributed to the acting actor's own turn |
| Proxy-attribution residuals (v3): single em/en dash ("Morgan — agrees"); name split from its marker by a line break or aside; markers after non-agent lead words ("reads the note from Morgan: 'I agree'" — kept usable for epistolary content) | Same as above, narrower | Same as above; assertion-verb frames ("quotes Morgan: 'I agree'") and bare markers stay caught |
| Over-removal direction: attributed segments run to the line break (upstream defines no closing delimiter), so same-line content after a violating marker is removed with it; asyndetic serial-verb tails ("thanks Morgan, smiles, signs") rewritten conservatively | Legitimate active-player text can be trimmed | Recoverable by design: attempt prefix preserved + availability sentence; never invented agency |
| Stateless nominal trade-off: a reference to a decision that REALLY happened earlier ("Ada re-reads Bo's reply") is indistinguishable from an invented one and is conservatively rewritten | Occasional unnecessary rewrite in multi-round scenarios | Bounded cost (attempt survives; affected actor gets its turn); a history-aware guard is future work |
| Reported speech ("announces that X agrees") IS detected — the one borderline class | Verbose rewrites when actors truthfully report others' past decisions | The optional single yes/no live-model confirmation seam (`make_agency_guard`) may relax this later |
| Unresolvable pronoun/collective subjects bind EVERY non-active roster actor | Verbose availability sentences on large rosters | Deliberate: an unresolvable committed decision must not slip through |

## 3. Operational robustness findings (gate I, recorded not patched)

From `OPERATIONAL_ROBUSTNESS_MATRIX.md`:

- **G1 — no in-branch model-call timeout seam for injected engine
  models.** `run_branch`/`run_candidates_detailed` accept no timeout; an
  injected model that never returns hangs its branch. Impact: a hung
  injected model is bounded ONLY by the outer monitored-runner
  no-progress/total kill — which control-plane rule 5 makes mandatory for
  every long run, and which the matrix proves kills the hang (exit 125,
  no survivors). Live-model transports carry their own inner deadlines
  (90/240/270 s semantic-runtime; 120 s compiler path). The seam's
  absence is pinned by a signature assertion so adding one forces the
  matrix row to be rewritten. Workaround: always run long engine work
  under `.claude/tools/run_monitored.py` ([RUNBOOK.md](RUNBOOK.md) §6).
- **F-R1 — corrupted-workspace driver error names the agent, not the
  file.** The per-agent record carries a raw `JSONDecodeError` repr;
  which FILE is corrupt requires opening the named agent's workspace
  (the branch agent's own error artifact adds identity when its step is
  reachable; `AGENT.json` corruption fails before the agent exists).
  Upstream-pinned reporting seam; recorded, not patched. Workaround:
  matrix row 14's diagnosis procedure.
- **L1 — no engine-side size cap on injected model output.** A 200 kB
  injected reply becomes a 200 kB committed event (bounded per turn by
  the step budget, not by size). Live paths are transport-bounded (4 MB
  body ceiling, provider `max_tokens`). Injected models are trusted
  driver/test code by design; operators embedding untrusted model
  wrappers must bound output themselves.

## 4. Simulation-mechanics notes (recorded behavior, by design or upstream)

- **Last-step events are queued but never delivered** (DECISIONS, Phase
  10): a branch's FINAL-step committed event reaches the world record and
  the GM memory, but the run ends before the next observation fan-out, so
  it reaches no actor memory. Impact: assertions/predicates about actor
  MEMORY must be designed around delivered steps; the event trace itself
  is complete. Not a bug — the upstream loop shape.
- **Local branch execution is strictly serial** (manager docstring): the
  seeded scope patches process-global RNG, so in-process parallelism
  would destroy reproducibility. Branch parallelism is process-level via
  the distributed executor, proven equivalent.
- **Checkpoint restore requires behaviorally prompt-pure models**: model
  internals are never serialized; a model whose behavior depends on
  hidden mutable state would break resume equivalence (structurally
  enforced in the checkpoint suite's model spec; live API models are
  stateless per call by nature).
- **Adapter contract narrowings** (COMPILER_TO_CONCORDIA_MAPPING.md §6,
  all loud refusals, never silent): observer-less starting events
  (`visible_to: []`) are refused (frozen contract requires ≥1 observer);
  undecodable actor names are refused, never fabricated; the compile
  question has no world/plan slot (hash + sidecar; its semantic home is
  `DecisionProblem`); `visible_to` resolution is exact-match only.
- **`gm_config` is a scalar map** (frozen Phase 3 contract), so the guard
  configuration is the scalar pair `agency_guard_enabled`/`guard_slot`
  rather than a nested object (DECISIONS, Phase 5).
- **Planner end-trim rule**: carried texts lose leading/trailing
  whitespace only (upstream reserves the three-newline observation
  delimiter); interior bytes verbatim.
- **Candidate-generator prompt carries problem-side success criteria by
  design** (`decision_route.GENERATOR_PROMPT_TEMPLATE`): the generator
  sees `DecisionProblem.success_criteria` (problem-side prose, never the
  world's evaluator-side criteria or any world-private text), so a
  GENERATED action's text may echo criteria-derived wording — and that
  text is then inserted verbatim as the decision owner's own t0
  insertion observation. This is the documented information flow of
  generation, not a leak of evaluator internals; user-supplied
  candidates are unaffected.
- **`_seeded_default_rng` is per-branch deterministic, not
  stream-independent** (`counterfactuals/manager.py`): inside one
  branch's seeded scope, EVERY no-argument `numpy.random.default_rng()`
  call returns a fresh generator seeded with the SAME branch seed —
  upstream's per-document generators therefore draw identical streams
  within a branch rather than statistically independent ones. Chosen for
  reproducibility and branch isolation (each branch has its own derived
  seed); callers needing independent streams pass explicit seeds.
- **Distributed branch tasks never self-heal worker crashes (by
  design, wave-2 fix)**: the branch executor submits every Ray step
  task with `.options(max_retries=0)`, so a crashed worker (SIGKILL,
  OOM) surfaces exactly once as a typed `task_error` and a synthesized
  `driver_only` failure `BranchResult` -- never a silent Ray
  re-execution (which would double-spend live model calls and could
  invert the deliberate interrupt/resume protocol on a workspace
  already carrying a checkpoint blob). Recovery is an explicit re-run
  into a FRESH run_dir: the branches-root claim is atomic
  (`mkdir(exist_ok=False)`) and any existing directory -- even an
  empty one -- is refused loudly, never overwritten
  (OPERATIONAL_ROBUSTNESS_MATRIX.md row 13).
- **Committed-stream discrimination and integrity refusal (Concordia
  Semantics CRITICAL, fixed)**: the runner's committed stream is
  ENGINE-STAMP PREFIX-anchored (`runner.is_engine_committed_row`) --
  the raw `[putative_event]` actor-attempt row never commits regardless
  of embedded `[event]` text -- and a count-invariant check
  (`runner._verify_committed_stream_integrity`) refuses the WHOLE
  branch, loudly and typed (`CommittedStreamIntegrityError`, reported
  through the standard failure paths with no trace and no metrics),
  when actor text MINTS extra tag-bearing memory rows through the
  upstream three-newline observation-delimiter split. Operational
  consequence: a (live) actor model that emits `[event]` /
  `[putative_event]` at a three-newline segment boundary fails its
  branch rather than risking a spoofed committed stream; benign
  multiline actor text is unaffected.
- **Reserved-marker refusal (Simulation Reality CRITICAL, fixed)**:
  upstream's resolved-turn framing string (`Putative event to resolve:`,
  stamped by event resolution and anchoring actor attribution) is
  RESERVED — world-authored text (premise, contexts, starting-event
  descriptions/observations) and candidate text carrying it, in any
  case/whitespace-obfuscated form, is refused loudly pre-simulation at
  the planner chokepoint plus the candidate preflight/route
  (`planner.RESERVED_EVENT_MARKER`; error code `reserved_marker`).
  Narration can therefore never spoof a resolved actor turn; the
  refusal is a hard authoring constraint, never a silent rewrite.

## 5. Evidence trust boundaries (disclosed, accepted)

- **F4 — two-tier scale evidence** (review #3, accepted): the committed
  100/1,000-agent reconciliation equalities are self-attested fields; the
  raw unit ledgers live outside the repo
  (`/home/user/scale_runs/phase11/`). Mitigations: the reconciliation
  CODE path has live small-N negative controls (a dropped/duplicated real
  action line → refusal naming the agent), and the rollup hash chain is
  recomputed from committed summaries. Impact: trusting the big-run
  numbers means trusting the committed artifacts of ten monitored jobs,
  not re-executing them from raw ledgers in-repo.
- **F3 — master-receipt staleness at HEAD**: a committed receipt is
  always one commit behind, so exactly one validator check
  (`initialization_level`) and its end-to-end subtest read red at an
  arbitrary HEAD. Mechanical and documented; self-heals at each fold-in;
  the Phase 12 freeze ends with the receipt re-recorded at the frozen
  SHA. Impact: expect exactly this one red in `python3 -m pytest tests
  -q` between fold-ins; anything else is a real failure.
- **`.agent-run/jobs/` is runner scratch** (gitignored beyond phase-0):
  durable job evidence is what was deliberately committed
  (`tests/engine_scale/evidence/`, `tests/engine_robustness/evidence/`)
  plus the `.agent-run/BACKGROUND_JOBS.json` registry.
- **`run_monitored` `progress_source` shows the most recent signal**: a
  trailing stdout write can leave it at `log_movement` even when
  `completed_units` advanced; the durable strong-progress evidence is
  `completed_units` (recorded observation, Phase 11).

## 6. Environment and distribution limits

1. **Live-model non-determinism**: live smoke asserts execution
   structure (5 passing executions per test, zero transport retries,
   bounded wall time), not output quality or realism. Provider aliasing
   observed: requested `deepseek-chat`, endpoint served
   `deepseek-v4-flash` (recorded in the smoke output). Retry-once
   policy with `LIVE_ENDPOINT_UNREACHABLE` distinguished as an
   infrastructure error.
2. **Python floors**: Concordia requires ≥ 3.12; the engine environment
   is 3.12.3. On system 3.11, engine-gated suites skip cleanly at
   collection; the product package itself stays importable (stdlib-only).
3. **Single-host Ray**, 4 CPUs (`AGENTSOCIETY_LLM_RAY_MAX_WORKERS=4` for
   scale jobs; sibling agreement of 2 in shared pytest suites).
   Multi-host placement untested
   ([SOCIETAL_SCALING_PATH.md](SOCIETAL_SCALING_PATH.md) §3.3).
4. **Ray job env snapshot freezes at first `init_dispatchers()`**
   (upstream behavior, Phase 2/7 findings): later
   `WORKSPACE_PATH`/`PYTHONPATH` exports never reach workers. One Ray
   owner per process segment; the executor adopts an existing init's
   workspace rather than repointing it. Operational consequence: export
   `WORKSPACE_PATH` before first init, or let the executor own the init.
5. **`import agentsociety2` requires `AGENTSOCIETY_LLM_API_KEY` at
   module import** (upstream; dummy value sufficient offline). The
   engine bring-up boundary names the variable before any workspace
   exists; `import sworldmodel` never needs it.
6. **Upstream examples-only failures at the pinned Concordia SHA** (20
   under `examples/`, `ScriptedByEntityModel` no-arg enumeration break):
   off our path — we never enumerate prefabs package-wide
   (`UPSTREAM_LOCK.json.known_issues`).
7. **`sworldmodel/__init__.py` eagerly imports the legacy kernel
   modules** (pre-existing; recorded in the Phase 4 import-proof
   docstring). Importing the package executes no legacy simulation; the
   engine path itself is proven free of `compiler`/`semantic_runtime`
   modules by subprocess proof.

## 7. Test-environment constraints (not product defects)

1. See §4 first bullet for last-step delivery (affects test design).
2. **PYTHONHASHSEED sensitivity is guarded, not assumed away**:
   determinism suites run under seeds 0/5/13 after the one historical
   flake was killed at its root
   (`FAILURE_LEDGER.jsonl::hash-order-sensitive-state-comparison`).
3. **Live smoke legs skip without `DEEPSEEK_API_KEY`** (2 tests), with
   the skip condition itself asserted.
4. **Do not combine `tests/engine_contracts` and
   `tests/engine_distributed` in one pytest session**: the distributed
   suite can adopt the contracts suite's workspace through the frozen
   Ray env snapshot + worker registry cache (reproduced pre-phase-8 at
   `db41689`; recorded in DECISIONS Phase 8). Workaround: run suites
   separately (the DoD battery ordering also avoids it).
5. **The multi-suite battery rule**: pytest naming ≥ 2 `tests/engine_*`
   directories must go through the monitored runner (hook-enforced;
   origin incident in [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md)
   §15).

## 8. Control-plane limitation (affects operating this repo, not the engine)

**`TeammateIdle` is never emitted on Claude Code web/remote surfaces**
(proven from the host's own debug log with a validated positive control;
recorded as `UNAVAILABLE_IN_CLAUDE_CODE_WEB` in
`.agent-run/RUN_STATE.json.environment_limitations`). The "no silent
abandonment" guarantee therefore rests on the four verified fallback
controls (TaskCompleted, SubagentStop, Stop, explicit task ownership +
lead review), not on that hook. Impact: none on the engine; operators of
the agent workflow should not claim TeammateIdle protection here.
