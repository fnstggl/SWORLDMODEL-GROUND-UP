# Test Matrix — every suite, what it proves, counts at HEAD

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

Counts below were measured by executing every suite at HEAD `5667596`
(gate-I fold-in; the documentation commits after it change no code or
tests). Two interpreters: **system** = `python3` (3.11, product +
control plane), **engine** = `/home/user/engine-env/bin/python` (3.12,
all three codebases). Exact run commands per suite are in the last
column; the battery rule is §3.

## 1. The suites

### 1.1 Engine suites (ten, engine interpreter)

| Suite | Count at HEAD | What it proves | Gate(s) | Run |
|---|---|---|---|---|
| `tests/engine_contracts/` | 39 | Pinned-upstream behavior contracts, independent of our app code: Concordia actor/GM lifecycle order, SwitchAct dispatch, the `event_resolution_steps` guard seam (rewrite/veto lands before observer queueing), memory persistence, checkpoint key set `{entities, game_masters, raw_log, checkpoint_counter}`, byte-identical deterministic harness; AgentSociety workspace round-trip, per-agent failure isolation, trace spans, token deltas, bounded concurrency | A, F | `/home/user/engine-env/bin/python -m pytest tests/engine_contracts -q` |
| `tests/engine_baseline/` | 64 | Phase 4 hard gate + the agency guard: two manual scenarios end-to-end on the stock engine (3× byte-identical), canary containment incl. RESOLUTION, zero-compiler-import subprocess proof, planner determinism, builder contracts (no YOLO fallback), guard detection classes 1–6 with caught + nearby-shape discriminating pairs, over-block protections, enabled-vs-disabled trace equivalence | C, H | `... -m pytest tests/engine_baseline -q` |
| `tests/engine_counterfactuals/` | 23 | Gate-E invariants: identical base plan hash across branches, single-intervention diff refusal, cross-branch canary isolation, identical-candidate byte identity, order invariance, failure isolation in list position, outcome/plan contract integration, attribution-bound predicates, and the FIXTURE-1 deterministic acceptance (measured winner `concise_relevant`, 3× byte-identical full pipelines) | E | `... -m pytest tests/engine_counterfactuals -q` |
| `tests/engine_compilation/` | 46 | The deterministic compiler adapter + route: field-mapping correctness with no silent discard (per-leaf destination walk), artifact-set loading refusals, information-leak canaries end-to-end through real planner+builder+runner, manual-vs-compiler plan equivalence (differences exactly `{plan_id, world_id, compiler_provenance}`), byte-identical traces from both routes, route/generator strict parsing, import-isolation proofs | C, H | `... -m pytest tests/engine_compilation -q` |
| `tests/engine_distributed/` | 7 | Stage A: local ≡ distributed per-candidate signature equality through real AgentSociety Ray primitives, bounded concurrency (driver window == worker overlap), exactly-once accounting, dual-channel failure isolation, no-silent-loss collection refusals, worker-side seeded-scope equivalence with an RNG-consuming model | F | `... -m pytest tests/engine_distributed -q` |
| `tests/engine_checkpoint/` | 16 | Stage B: whole-branch checkpoint/restore equivalence A=A'=B (two seeds), RNG stream continuity with a naive-re-seed divergence discriminator, no premise redelivery, tampered/incomplete checkpoint refusals, state canonicalization unit proofs, distributed interrupted-resume byte-equality | F | `... -m pytest tests/engine_checkpoint -q` |
| `tests/engine_individual/` | 24 (22 deterministic + 2 live smoke) | Gate C per clause on fixture 1: guard-enforced no-choosing-another's-response, attribution-anchored evaluators defeating GM narration, all four terminal statuses, complete causal trace artifacts (hash-asserted committed examples), repeat stability; deterministic mock-model leg; live DeepSeek smoke leg | C, E | `... -m pytest tests/engine_individual -q` (live legs skip without `DEEPSEEK_API_KEY`) |
| `tests/engine_team/` | 22 | Gate D per clause on fixture 2 (5 actors, 11 steps): pairwise private isolation (20 ordered pairs × 3 branches), meeting fan-out, participant-only follow-ups, authority flip probe, actor-owned votes + guard-blocked proxy vote, GM narration uncitable, multi-round memory, explicit outcomes incl. cutoff, PYTHONHASHSEED 0/5/13 byte-identical repeats | D | `... -m pytest tests/engine_team -q` |
| `tests/engine_scale/` | 16 | Gate G two tiers: fast tier (7) runs partitioning/sparse activation/concurrency probe/failure injection/interrupt+resume/reconciliation-with-negative-tamper-cases/aggregation small-N through the same harness code; verification tier (9, both interpreters) independently recomputes the committed 100/1,000-agent evidence (totals from specs, overlap ceiling from windows, rollup hashes, byte-exact manifest) | G (+F) | `... -m pytest tests/engine_scale -q` |
| `tests/engine_robustness/` | 27 | Gate I: all fourteen scenarios — clean install (committed monitored-probe evidence), cold start, interruption (SIGTERM/SIGKILL) + resume byte-equality, malformed inputs at the run boundary, missing credentials at every layer, model timeout (inner transport seam + outer monitored-runner bound, gap G1 pinned), 7 malformed-output classes fail closed, Ray worker SIGKILL typed/bounded/exactly-once with retry auto-recovery, workspace corruption explicit + restore-from-last-good | I (+A row 1) | `... -m pytest tests/engine_robustness -q` |

Engine total at HEAD: **284** (with the live legs executed; 282 passed +
2 skipped without `DEEPSEEK_API_KEY`). This equals the ten-suite
monitored battery `robustness-final-dod` (§3).

### 1.2 Control-plane suites (three, system interpreter)

These prove the **evidence machinery itself** (hooks, monitored runner,
validator) — the layer every receipt and job record in this project
depends on.

| Suite | Count at HEAD | What it proves | Run |
|---|---|---|---|
| `tests/control_plane/test_gate.py` | 138 (+95 subtests) | PreToolUse/TaskCompleted/SubagentStop/Stop/ConfigChange gate behavior: shell-aware write-target detection, upstream-checkout protection in every mode, frozen-mode rules, long-running classification incl. the multi-suite engine battery rule, receipt-exemption bounds | `python3 -m pytest tests/control_plane/test_gate.py -q` |
| `tests/control_plane/test_run_monitored.py` | 25 | The monitored runner: registry entries, heartbeats, progress sources, no-progress/total timeouts, process-group termination incl. stubborn descendants, exit-code taxonomy | `python3 -m pytest tests/control_plane/test_run_monitored.py -q` |
| `tests/control_plane/test_validate_control_plane.py` | 95 passed + 1 known failure (+364 subtests) | Validator checks: structure, mode-aware change audit, upstream checkout integrity, receipt discipline (`phase_receipt_discipline`, chronological newest), bootstrap consistency. The single failing end-to-end subtest at HEAD is the **documented** `initialization_level` master-receipt staleness (review F3: a committed receipt is always one commit behind; the Phase 12 freeze pins it at the frozen SHA) | `python3 -m pytest tests/control_plane/test_validate_control_plane.py -q` |

### 1.3 System suite (system interpreter)

| Suite | Count at HEAD | What it proves | Gate(s) | Run |
|---|---|---|---|---|
| `tests` (everything) | **697 passed, 49 skipped, 459 subtests, 1 known failure** | Gate B regression floor: the existing compiler suite and retained kernel/legacy tests unchanged-green; the Phase 3 contract + fixture-loader suites (both interpreters); the hardcoding guard; the stdlib tiers of the engine suites (engine-gated modules skip cleanly at collection on 3.11 — the 49 skips); the control-plane suites. The 1 failure is exactly the documented `initialization_level` staleness above | B | `python3 -m pytest tests -q` |
| `tests/test_hardcoding_guard.py` | 3 | No scenario vocabulary in production code (`SCAN_ROOTS = ("compiler", "sworldmodel")`); per-file word allowances exact, never broader than file content (guard.py: `{vote, voting}`) | H | `python3 -m pytest tests/test_hardcoding_guard.py -q` (also green under the engine interpreter) |

### 1.4 Upstream baseline suites (gate A/B baselines, engine environment)

Run unmodified from inside the pinned checkouts (their tests write
scratch to cwd). Recorded results, `docs/engine_migration/PHASE0_BASELINE.md`
§3 + monitored job records `.agent-run/jobs/phase0-*`:

| Suite | Result | What it proves | Run |
|---|---|---|---|
| Concordia full repo | **560 passed core, 0 core failures** (18 failures + 2 errors confined to `examples/`, an upstream defect at the pinned HEAD — `UPSTREAM_LOCK.json.known_issues`; off our path) | The engine we adopt is healthy, unmodified, in our environment | `cd /home/user/concordia && /home/user/engine-env/bin/python -m pytest -q --timeout=120` |
| AgentSociety2 package tests | **387 passed, 0 failed** (offline, dummy credentials) | The distribution substrate is healthy, unmodified, in our environment | `cd /home/user/agentsociety2 && env AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=http://localhost:9 /home/user/engine-env/bin/python -m pytest packages/agentsociety2/tests -q` |

## 2. Gate → suite index

| Gate | Evidenced by |
|---|---|
| A upstream integrity | `engine_contracts`; upstream baseline suites; validator `upstream_checkouts_integrity` on every run; robustness row 1 (clean install from lock + method doc); `third_party/*` |
| B baseline reliability | system suite (compiler regression floor unchanged-green); contract suites both interpreters; 3×-clean-run repeats inside `engine_baseline`/`engine_counterfactuals`/`engine_team` |
| C individual simulation | `engine_baseline`, `engine_individual`, `engine_compilation` (canaries) |
| D team simulation | `engine_team` |
| E counterfactual correctness | `engine_counterfactuals`, `engine_individual` (isolation/determinism riding the slice), frozen fixtures |
| F agentsociety integration | `engine_contracts` (AS2 contracts), `engine_distributed`, `engine_checkpoint`, `engine_scale` (real path at scale) |
| G societal infrastructure | `engine_scale` + the ten committed monitored scale jobs (§3) |
| H simulation semantics | `engine_baseline` (guard), `engine_compilation` (leaks), proxy-attribution modules in `engine_individual`/`engine_team`/`engine_counterfactuals`, hardcoding guard, + the reviewer reports (`reviews/`) |
| I operational robustness | `engine_robustness` + `OPERATIONAL_ROBUSTNESS_MATRIX.md` |
| J documentation | this documentation set; RUNBOOK worked example executed ([RUNBOOK.md](RUNBOOK.md) §4) |

## 3. The monitored-job evidence tier (batteries and scale runs)

**Battery rule (control plane, enforced by hook):** a pytest invocation
naming **two or more** `tests/engine_*` directories is a long-running
battery and MUST run through `.claude/tools/run_monitored.py` (or as a
bounded `record_receipt.py --run` with an explicit `--timeout`). Single-
suite runs (§1 commands) stay direct. Origin: the silent-pause incident
([IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) §15).

Monitored batteries of record (registry `.agent-run/BACKGROUND_JOBS.json`;
all `finished`, exit 0):

| Job id | Suites | Passed | Recorded at |
|---|---|---|---|
| `engine-dod-baseline-pre-adapter` | 5 engine suites | 134 | `9218c1d` (post-incident bounded re-run) |
| `adapter-final-dod` | 6 | 180 | `a03ee51` |
| `phase9-final-dod` | 7 | 200 | `460d502` |
| `phase10-pre-commit-battery`, `phase10-final-dod` | 8 | 219 | `6d946e8` |
| `phase11-final-dod` | 9 | 235 | `cf091a6` era |
| `review811-nine-suite` | 9 (independent reviewer reproduction) | 235 | `c80787e` era |
| `f1-fix-dod-2` | post-F1 battery | 254 | `1f8404b` era (`f1-fix-dod` exit 2 kept: the pre-fix red run) |
| `robustness-final-dod` | 10 | 284 | `2404226` era |

Monitored scale/robustness runs with **committed** durable evidence:

- Ten Phase 11 scale jobs (`phase11-scale100-full`,
  `phase11-scale1000-p{1..4}-seg{A,B}`, `phase11-scale1000-aggregate`) —
  all exit 0, no timeout terminations; per-job `job.json` + ledgers under
  `tests/engine_scale/evidence/` (52 files,
  `hashes_manifest.json`); clause map in `PHASE11_SCALE_EVIDENCE.md`.
- `robustness-clean-install` — the from-empty-venv rebuild probe;
  committed evidence `tests/engine_robustness/evidence/clean_install.json`,
  validated by `test_clean_install_evidence.py`.
- Phase 0 upstream baselines (`phase0-*`) — job records under
  `.agent-run/jobs/`.

Receipts: every completed phase task has a passing current-SHA receipt
under `.agent-run/receipts/` (task → receipt mapping in
`.agent-run/TASK_GRAPH.json` `completion_evidence`; validator check
`phase_receipt_discipline` enforces clean-worktree or content-hash
continuity). How to read receipts and job records: [RUNBOOK.md](RUNBOOK.md) §7.

## 4. Flake policy and known failures

- **Zero tolerated flakes.** The one flake ever observed (~1/8, upstream
  set-order serialization under PYTHONHASHSEED) was root-caused and
  killed, with reproducing seeds recorded
  (`FAILURE_LEDGER.jsonl::hash-order-sensitive-state-comparison`);
  determinism-sensitive suites are exercised under PYTHONHASHSEED 0/5/13.
- **The only expected red at an arbitrary HEAD** is the
  `initialization_level` validator staleness (§1.2), self-healing at each
  fold-in and pinned at the Phase 12 frozen SHA.
- **Environment constraint**, not a product defect: do not combine
  `tests/engine_contracts` and `tests/engine_distributed` in ONE pytest
  session ([KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §7.4); the
  DoD battery ordering avoids it, single-suite runs are unaffected.
- Live smoke legs skip (never fail) without `DEEPSEEK_API_KEY`, with the
  skip condition itself asserted
  (`engine_robustness/test_missing_credentials.py`).
