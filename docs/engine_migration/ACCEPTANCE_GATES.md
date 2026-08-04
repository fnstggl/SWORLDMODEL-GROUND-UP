# Acceptance Gates — test mapping

The ten mandatory gates (A–J) from the master directive, with the concrete
evidence each requires. Machine state: `.agent-run/ACCEPTANCE_STATUS.json`
(definitions there mirror the directive verbatim; this file adds the test
mapping). Evidence = current-SHA receipts + artifacts; long/scale runs via
`.claude/tools/run_monitored.py` with explicit progress sources.

| Gate | Proven by |
|---|---|
| A. Upstream integrity | `third_party/UPSTREAM_LOCK.json` SHAs == audited SHAs; no upstream file modified (integrity check vs pinned checkouts); PATCHES.md accurate (initially: none); upstream suites green in the engine env (baseline jobs); integration code lives only under this repo; INTEGRATION_METHOD.md recreate commands re-executed clean in Phase 12 |
| B. Baseline reliability | Existing compiler suite (`tests/test_scene_compiler.py` + retained tests) green at every phase receipt; full suite 3× consecutive clean runs at the frozen SHA; no xfail/skip added without a DECISIONS entry; structured error artifact test for branch failures (deliberate failing branch produces `branch_result.json` with explicit error, never absence) |
| C. Individual simulation | Phase 4 hard-gate evidence (two manual scenarios × 3 clean runs, scripted + mock models); canary tests (PRIVATE_*/SHARED_*/RESOLUTION_CANARY, per-event visibility); memory persistence across turns test; agency-guard discriminating tests (forced reply split; GM narration cannot satisfy the success criterion — evaluator reads events only); explicit terminal status test (success/failure/cutoff/incomplete); live-model smoke runs recorded when credentials exist, else recorded as credential-gated with deterministic evidence complete |
| D. Team simulation | Fixture 2 runs: ≥5 actors, private + shared interactions, authority (declared decision rule + veto), actor-owned commitments (vote events emitted only by actor turns — guard test), multi-round trace, no-omniscience canaries, explicit recorded outcome from events |
| E. Counterfactual correctness | Same-base-snapshot hash assertion across branches; single-intervention diff test (branch inputs differ only at insertion point); cross-branch canary leak test; identical-candidate determinism (seeded harness) — twice-run equality; candidate-order permutation invariance; serial ≡ parallel results; ranking computed by code from metrics (test: evaluator output is the ranking input; no LLM ranking path exists — import/graph assertion); report language "best among tested candidates" asserted in RecommendationResult rendering |
| F. AgentSociety integration | Stage A tests: real `step_agent_batch`/workspaces exercised (no local substitute — reviewer checks imports); restore round-trip; bounded concurrency measurement; deliberate branch failure isolated; token/runtime stats collected into BranchResults; local ≡ distributed equivalence under deterministic models; clean shutdown leaves valid workspaces; Stage B checkpoint/resume equivalence |
| G. Societal infrastructure | Phase 11 monitored jobs: 100-job and 1,000-job runs with progress sources (completed/total/current unit/last-progress); sparse activation inspectable (per-branch activity records; not all agents step every tick in the shallow-society variant); zero duplicated/lost jobs (ID accounting: expected set == collected set, exactly once); injected failures isolated; aggregate == sum of recorded per-branch outcomes; SYNTHETIC INFRASTRUCTURE TEST labeling asserted in report artifacts |
| H. Simulation semantics | Adversarial reviewer report (simulation-reality reviewer) over actual traces: qualitative reasoning, actor-owned voluntary decisions, GM not final decider, no invented social weights (hardcoding guard extended to new packages + reviewer), no unobservable information (canaries + trace review), outcomes counted only from trace/world state, intervention-centered structure |
| I. Operational robustness | Failure-injection matrix: clean install (recreate env from INTEGRATION_METHOD), cold start, repeated runs, interrupt + resume (society-level and monitored-job-level), one actor failure, one branch failure, malformed candidate (schema + semantic rejection), malformed compiled input, missing credentials (clear error, no crash-loop), model timeout (wrapper + branch wall-clock), model malformed output (bounded retry then explicit branch failure), Ray worker kill, corrupted `AGENT.json`/workspace (detected via missing/invalid BranchResult, isolated) |
| J. Documentation | The nine directive-mandated docs exist and answer the directive's plain-language questions; RUNBOOK reproduces env + one end-to-end run |

Completion rule (unchanged from the directive): every gate PASS at one frozen
final SHA, complete suite re-run from the beginning at that SHA, all reviewer
reports in, zero verified critical findings, final adjudicator PASS —
recorded in ACCEPTANCE_STATUS.json before the run may end.
