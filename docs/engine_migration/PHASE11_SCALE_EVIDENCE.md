# Phase 11 societal infrastructure proof — scale evidence (gate G)

> **INFRASTRUCTURE TEST ONLY**: every run documented here is a
> scripted/shallow scale exercise of the AgentSociety execution
> substrate — **infrastructure rather than calibrated societal
> simulation; no population realism claim.** No LLM call and no network
> I/O occurred anywhere in these runs.

All runs executed at git SHA `05938a3ce15429c33d7954fa17c6235287afd78a`
(branch `claude/concordia-agentsociety-best-action-engine`), foreground
under `.claude/tools/run_monitored.py` (classification `exploratory`,
`--no-progress-timeout 240`, `--total-timeout 540`), with a per-job
`--progress-file` the driver appends per-chunk/per-tick records to
(strong progress; the runner counted them as `completed_units`).
Durable per-job proof is committed under
`tests/engine_scale/evidence/<job-id>/` (`.agent-run/jobs/` is
gitignored runner scratch); `tests/engine_scale/evidence/hashes_manifest.json`
records the sha256 of all 52 evidence files. Every job is registered in
`.agent-run/BACKGROUND_JOBS.json`.

## What ran

Substrate: the REAL AgentSociety worker/dispatcher path proven in Phase
7 — `init_dispatchers()` → `build_service_proxy(env=None, trace=False,
replay=False)` → `create_agents_batch.remote` → `step_agent_batch.remote`
(audit Option 2 primitives), with the test-owned scripted
`ScaleUnitAgent` materialized into `<workspace>/custom/agents/` for the
stock custom-module scanner inside every Ray worker
(`WORKSPACE_PATH` exported before the first init — the env snapshot is
frozen at first init). Driver, agent template, and specs are test-owned:
`tests/engine_scale/{scale_driver.py,scale_harness.py,scale_agent_template.py,specs/}`.

Command shape (partition segment; aggregate mode analogous — exact
argv per job is recorded in each committed `job.json`):

```
python3 .claude/tools/run_monitored.py --job-id <id> \
  --classification exploratory --no-progress-timeout 240 --total-timeout 540 \
  --progress-file <run-root>/driver/progress_<seg>.jsonl \
  -- /home/user/engine-env/bin/python tests/engine_scale/scale_driver.py run \
     --spec tests/engine_scale/specs/<spec>.json --segment <A|B|full> [--resume] \
     --registry-root <run-root> --partition-root <run-root> \
     --progress-file <run-root>/driver/progress_<seg>.jsonl
```

Chunking is the demonstration, not a workaround: the 1,000-agent run is
four isolated 250-agent partitions, each split into two monitored jobs
at the declared checkpoint boundary (segment A: ticks 1–6, create +
run; segment B: ticks 7–12, `--resume` from the persisted workspaces +
driver checkpoint in a **fresh process with a fresh Ray runtime**),
plus one final aggregation job. Run roots: `/home/user/scale_runs/phase11/`.

### Scale-run table

| job id | agents | ticks | wall (s) | cpu (s) | exit | progress units | evidence |
|---|---|---|---|---|---|---|---|
| `phase11-scale100-full` | 100 (1 partition `s100`) | 1–12 (2 full+delay, 10 sparse) | 27.4 | 5.9 | 0 | 18 | `evidence/phase11-scale100-full/` |
| `phase11-scale1000-p1-segA` | 250 (`p1`) | 1–6 | 32.3 | 5.9 | 0 | 14 | `evidence/phase11-scale1000-p1-segA/` |
| `phase11-scale1000-p1-segB` | 250 (`p1`, resume) | 7–12 | 17.1 | 5.9 | 0 | 10 | `evidence/phase11-scale1000-p1-segB/` |
| `phase11-scale1000-p2-segA` | 250 (`p2`) | 1–6 | 25.2 | 6.6 | 0 | 14 | `evidence/phase11-scale1000-p2-segA/` |
| `phase11-scale1000-p2-segB` | 250 (`p2`, resume) | 7–12 | 16.6 | 6.9 | 0 | 10 | `evidence/phase11-scale1000-p2-segB/` |
| `phase11-scale1000-p3-segA` | 250 (`p3`) | 1–6 | 29.2 | 6.2 | 0 | 14 | `evidence/phase11-scale1000-p3-segA/` |
| `phase11-scale1000-p3-segB` | 250 (`p3`, resume) | 7–12 | 29.8 | 6.4 | 0 | 10 | `evidence/phase11-scale1000-p3-segB/` |
| `phase11-scale1000-p4-segA` | 250 (`p4`) | 1–6 | 21.9 | 6.1 | 0 | 14 | `evidence/phase11-scale1000-p4-segA/` |
| `phase11-scale1000-p4-segB` | 250 (`p4`, resume) | 7–12 | 30.7 | 6.9 | 0 | 10 | `evidence/phase11-scale1000-p4-segB/` |
| `phase11-scale1000-aggregate` | 1,000 (read-side) | — | 0.6 | 0.0 | 0 | 7 | `evidence/phase11-scale1000-aggregate/` |

All ten: state `finished`, `termination_reason` null (no no-progress or
total-timeout kills). One `run_monitored` semantics observation recorded
for reviewers: `progress_source` is the *most recent* signal, so a final
stdout write after the last progress append can leave it at
`log_movement` (seen on `p2-segA`, `completed_units=14`); the durable
strong-progress evidence is `completed_units`.

### The numbers

- **100-agent run** (`s100`, spec sha `682f9a0a8246cea5…`): 12 ticks;
  ticks 1–2 full activation with a 0.25 s held slot per step (tick 1 =
  warm-up holding slots, tick 2 = timed probe); ticks 3–12 sparse
  (stride 5 → 20 of 100 per tick); injected failures agents 7/42/87 at
  tick 3; **394 actions recorded, expected 394**, exactly once; action-id
  aggregate sha `bc2ee5bd52feb52b…` identical from driver ledger and
  workspace files.
- **Concurrency (100-agent probe)**: configured bound = window 3 ×
  batch 4 = **12**; observed in-worker overlap ceiling **12** (== bound,
  never above), 3 distinct worker pids, driver max in flight 3 ≤ window
  (window deliberately below the 4-CPU Ray budget → the ceiling is
  code-enforced), wall span 2.34 s vs 25 s serial floor, every window ≥
  0.9 × delay. Windows committed in `partition_summary.json`; the
  verification tier recomputes the ceiling from them.
- **1,000-agent run**: 4 × 250 agents, ids 1001–1250 / 2001–2250 /
  3001–3250 / 4001–4250 (disjoint); 12 sparse ticks (stride 5 → 50 of
  250 per tick, ~600 actions per partition); shallow steps (no delay);
  window 4, batch 5. Actions: p1 **600/600**, p2 **596/596** (2
  injected failures), p3 **599/599** (1 injected failure), p4
  **600/600**. Aggregate: **2,395 / 2,395 expected** from 1,000 agents;
  collected-vs-recomputed action-id sha `ad4675e8faf59c96…` **byte-equal**;
  full-record workspace sha `c6f2ce31bc873a87…`; per-agent rollup sha
  `5eb6350b1f697d82…`.
- **Failure injection**: p2 agents 2004/2009 failed at tick 6 (segment
  A) — the resumed segment-B job excluded them at their next scheduled
  tick 11 (failure state carried across the process boundary via the
  driver checkpoint); p3 agent 3014 failed at tick 11 (inside the
  resumed job). Every failure produced a structured
  `state/unit_error.json` artifact (committed copies:
  `unit_error_<id>.json`) AND a driver `ok=False` record — dual-channel,
  reconciled. Batch mates and all other partitions completed unaffected
  (exact per-partition totals above).

## Gate G clause → evidence

| Gate G clause | Evidence |
|---|---|
| 100-agent shared/partitioned test succeeds | `evidence/phase11-scale100-full/{job.json,reconciliation.json}` (`ok: true`, 394/394); verification test `test_100_agent_run_reconciled_exactly` |
| 1,000-agent scripted/shallow test succeeds | 8 partition-segment jobs + `evidence/phase11-scale1000-aggregate/aggregate_reconciliation.json` (`ok: true`, 2395/2395); `test_1000_agent_partitions_reconciled_and_resumed` |
| Actors are not all activated every tick without cause | Declared modular schedule in the committed specs (stride 5); per-tick `tick_plan` activation lists in every driver ledger; per-tick action counts in summaries (20/100 and 50/250 on sparse ticks) |
| Sparse activation can be inspected | `tick_plan` ledger events (activation + exclusion lists); `sparse_probe` result in summaries: all non-activated workspaces hashed byte-identical across the probe tick (80/100 and 200/250 inactive, `unchanged: true`); `test_100_agent_sparse_activation_and_failures` |
| No action is dropped or duplicated | Exact reconciliation: per-agent contiguous seq, strictly increasing ticks, tamper-evident hash chain recomputed from genesis, driver-ledger↔workspace-file identity both directions, totals == schedule-derived expectation; fast tier proves the reconciliation REFUSES a dropped and a duplicated action (`test_reconciliation_catches_lost_and_duplicated_actions`) |
| Injected failures do not terminate unaffected partitions | p2/p3 failures; same-batch mates ok; p1/p4 byte-exact expected totals; failing agents' partitions completed; `test_injected_failure_is_isolated_and_dual_channel` (fast) + committed `unit_error_*.json` + summaries |
| Aggregate outcomes equal the underlying recorded actions | `aggregate_summary.json` `aggregate_sha256.equal: true` — collected (driver ledgers) vs recomputed (raw workspace records) canonical action-id lists byte-equal; rollup hashes recomputed from committed per-agent hashes in `test_1000_agent_aggregate_equals_recorded_actions` |
| Cross-partition communication is explicit and traceable | This run used **isolated partitions by design**: `aggregate_summary.json` `isolation` block records `mode: isolated_partitions_by_design`, `cross_partition_channels: []`, disjoint agent-id ranges, disjoint workspace roots, globally unique action ids — the explicit record that nothing was exchanged |
| System labels this as infrastructure, not calibrated societal simulation | The statement rides in EVERY artifact: specs, unit `config.json`, manifests, checkpoints, ledgers' companion summaries, reconciliations, aggregates, progress `job_start` lines, this document, and the suite docstrings; enforced by `test_infrastructure_only_labeling_everywhere` |
| Bounded concurrency (Phase 11 list) | Configured bound 12 == observed ceiling, recomputed from committed windows (`test_100_agent_bounded_concurrency_from_recorded_windows`) |
| Persistent workspaces (Phase 11 list) | Agents are reconstructed from workspace files every step; hash chains recompute across ticks, segments, AND processes (`test_checkpoint_resume_across_driver_restart`, resumed monitored jobs); `AGENT.json` `step_count` == recorded actions per agent |
| Checkpoint/resume (Phase 11 list) | `driver_checkpoint_after_segA.json` (`next_tick: 7`, carried failure state) per partition + segB jobs resuming with `--resume` in fresh processes; spec-hash-bound resume refusal on mismatch |
| AgentSociety distributed execution (Phase 11 list) | Stock `init_dispatchers` Ray bring-up, stock `create_agents_batch`/`step_agent_batch` Ray tasks, stock registry scanner resolving the custom agent inside workers (worker probe in each `partition_manifest.json`) |

## Test tiers

- **Fast tier** (`tests/engine_scale/test_scale_fast_tier.py`): 7 tests,
  small-N (10+8 agents, 2 partitions) through the SAME harness code
  paths — partitioning, sparse activation, held-slot concurrency probe
  (bound 4), failure injection, interrupt+resume, reconciliation
  including the negative tamper cases, aggregation. ~25 s including Ray
  init; runs in the nine-suite DoD battery; skips at collection on
  Python < 3.12.
- **Verification tier** (`tests/engine_scale/test_scale_verification.py`):
  9 tests, pure stdlib (runs under BOTH interpreters), asserts the
  gate-G reconciliations over the committed evidence with independent
  recomputation (expected totals from the spec files, overlap ceiling
  from the committed windows, rollup hashes from the per-agent hash
  lists, byte-exact manifest). Skips with a precise reason if the
  evidence is absent.

## Residual limits (honest scope)

- Single-host Ray (4 CPUs, `AGENTSOCIETY_LLM_RAY_MAX_WORKERS=4` for the
  scale jobs; the shared pytest suites keep the sibling agreement of 2).
  Multi-host placement is out of scope here.
- Partition size 250 per monitored job (~30 s each) — far inside the
  540 s job ceiling; chosen for headroom, not necessity. Halving is the
  documented fallback if a future host is slower.
- The 1,000-agent steps are DELIBERATELY shallow (append-one-record
  agents, no delay); the 100-agent run's probe ticks are the
  concurrency measurement. Depth of reasoning is explicitly not the
  subject of this phase.
- Partitions are isolated by design; no cross-partition messaging
  exists to trace. If a future phase adds an explicit channel, it must
  extend the aggregation's `isolation` record with the channel's own
  ledger.
- `trace=False`/`replay=False` for scale runs: the driver ledger +
  workspace files are the (reconciled, dual-channel) evidence; the
  TraceProxy path at branch scale is already covered by
  `tests/engine_distributed`.

**INFRASTRUCTURE TEST ONLY — infrastructure rather than calibrated societal simulation; no population realism claim.**
