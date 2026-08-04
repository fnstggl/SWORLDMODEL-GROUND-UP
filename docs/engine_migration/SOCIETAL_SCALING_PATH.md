# Societal Scaling Path — from proven infrastructure to larger populations

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

**INFRASTRUCTURE ONLY.** Everything proven at scale in this pass is an
exercise of the execution substrate — scripted, deliberately shallow
agents. It demonstrates that the machinery can carry a population; it
demonstrates **nothing** about how a real population behaves. That
labeling rides in every scale artifact and is test-enforced
(`tests/engine_scale/test_scale_verification.py::
test_infrastructure_only_labeling_everywhere`). No population realism
claim is made anywhere in this document.

## 1. What is proven today (the floor to build on)

Evidence: `PHASE11_SCALE_EVIDENCE.md`, `tests/engine_scale/` (16 tests),
ten monitored jobs with 52 committed evidence files.

| Capability | Proven form |
|---|---|
| 100 agents, one partition | 12 ticks, 394/394 actions reconciled exactly once; concurrency ceiling observed == configured bound (12), never above |
| 1,000 agents, partitioned | 4 isolated 250-agent partitions × 2 segments; 2,395/2,395 actions; aggregate action-id hash byte-equal recomputed from raw workspaces |
| Bounded concurrency | Code-enforced window (driver in-flight ≤ window; in-worker overlap ceiling == configured bound), recomputed from committed windows |
| Sparse activation | Declared modular schedule (stride 5 → 20/100 and 50/250 per tick); activation/exclusion lists ledgered per tick; non-activated workspaces hash-identical across a probe tick |
| Persistent workspaces | Agents reconstructed from workspace files every step; tamper-evident per-agent hash chains recompute from genesis across ticks, segments, AND processes |
| Checkpoint/resume | Segment B resumed in a fresh process with a fresh Ray runtime from persisted workspaces + a spec-hash-bound driver checkpoint; resume refusal negatively proven for spec mismatch, wrong continuation tick, missing units root, and workspace-count mismatch (`test_scale_fast_tier.py::test_resume_refuses_*`) |
| Failure isolation | Injected per-agent failures (incl. across the resume boundary) produce dual-channel structured evidence; batch mates and other partitions complete byte-exactly |
| No lost/duplicated actions | Exact reconciliation both directions (driver ledger ↔ workspace files), plus negative controls proving the reconciliation REFUSES a dropped and a duplicated action |
| Aggregation | Aggregate outcomes recomputed equal to the underlying recorded actions (hash equality, both directions) |
| Real substrate | Stock `init_dispatchers` → `build_service_proxy` → `create_agents_batch` / `step_agent_batch` Ray path — the same public primitives the branch executor uses ([UPSTREAM_COMPONENT_MAP.md](UPSTREAM_COMPONENT_MAP.md) §2) |

Complementing it at branch scale: whole-branch checkpoint/restore
equivalence and distributed interrupted-resume
(`tests/engine_checkpoint/`), and the operational robustness rows
(interruption, Ray worker kill, workspace corruption —
`OPERATIONAL_ROBUSTNESS_MATRIX.md` rows 4, 13, 14).

## 2. The architecture's scaling model (as built)

Two orthogonal axes, deliberately kept separate:

1. **Branch axis (the product axis).** One best-action request = N
   candidate branches, each a COMPLETE self-contained Concordia
   simulation distributed as one AgentSociety job (Stage A). Branch count
   scales with worker processes; nothing inside a branch changes.
2. **Population axis (the infrastructure axis).** Many agents inside the
   AgentSociety substrate, partitioned into isolated units, sparsely
   activated, workspace-persistent, checkpoint-resumable (Stage C).

The proven partitioning model is **isolation-first**: disjoint agent-id
ranges, disjoint workspace roots, globally unique action ids, an explicit
`isolation` record in the aggregate
(`mode: isolated_partitions_by_design`, `cross_partition_channels: []`).
Partitions of 250 agents per monitored job segment ran in ~30 s against a
540 s ceiling — an order of magnitude of headroom per job on this host.

## 3. The path to larger populations

Each step below is engineering extrapolation from the proven floor —
**none of it is implemented or proven** unless marked otherwise.

### 3.1 More agents, same design (no new architecture)

The proven design scales horizontally by adding partitions and job
segments: the 1,000-agent run IS 4 × 250 chunked into monitored jobs at a
declared checkpoint boundary, and nothing in the harness binds partition
count. Costs grow linearly in jobs; per-partition reconciliation and the
rollup hash chain already compose across partitions (the aggregate job).
Practical next checkpoints would be 10k agents = 40 such partitions.
What was actually measured stops at 1,000; claims beyond that are
extrapolation.

### 3.2 Deeper agents (bounded by the model budget, not the substrate)

The scale agents were deliberately shallow (append-one-record steps; the
100-agent run's held-slot probe ticks are the concurrency measurement).
Depth — real Concordia reasoning per agent — multiplies per-step cost by
model latency; the substrate's bounded-concurrency and sparse-activation
mechanics are the control surface. The 100-agent probe's held-slot design
exists precisely so depth can be dialed in later without changing the
harness. Not exercised with live models at scale in this pass.

### 3.3 Multi-host distribution (not started)

Everything ran single-host Ray (4 CPUs;
`AGENTSOCIETY_LLM_RAY_MAX_WORKERS=4` for scale jobs). Multi-host
placement is upstream-supported Ray territory but untested here; the
executor's env-snapshot handling (`WORKSPACE_PATH` before first init)
and workspace-root layout would need re-validation per host
([KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §6.3).

### 3.4 Cross-partition interaction (explicitly future, explicitly gated)

The proven runs exchange NOTHING between partitions, by design, and say
so in a machine-checked record. If a future phase adds a cross-partition
channel, the committed aggregation contract already states the price: the
channel must extend the aggregate's `isolation` record with its own
ledger (`PHASE11_SCALE_EVIDENCE.md`, "Residual limits"). Beyond that, the
master directive gates ANY societal partition system on a separate design
and acceptance review answering, at minimum: why whole-branch execution
is insufficient (a concrete failed requirement, not "seems useful"); how
the population is divided; which Game Master owns each event; how events
cross partitions; how shared facts stay consistent; how simultaneous
changes are ordered; how actors are activated; how state conflicts are
detected; and how the distributed result is validated
(`MASTER_IMPLEMENTATION_DIRECTIVE.md`, "Later gated stage").

### 3.5 Actor-level persistence (explicitly future, same gate)

Stage B persists branches as WHOLE units on purpose. Persisting and
reconstructing individual Concordia actors through AgentSociety
workspaces is the later-gated stage, permitted only when measured
evidence shows whole-branch execution cannot support a required use case
(same directive section). No such evidence exists today — whole-branch
handling met every requirement this pass tested.

## 4. What the current evidence does NOT support

Stated plainly, so nobody cites the scale runs for more than they are:

1. **No population realism.** Scripted agents executing a schedule prove
   throughput, isolation, persistence, and accounting — not behavior.
   Nothing about how 1,000 real people would act is evidenced anywhere.
2. **No emergent social dynamics.** Partitions were isolated; no
   inter-agent influence at scale was even attempted.
3. **No live-model scale economics.** All scale runs were LLM-free (zero
   network I/O); token/latency behavior at 100+ live agents is unmeasured.
4. **No multi-host operation.** Single host, 4 CPUs.
5. **No claim past 1,000 agents.** Larger numbers in §3 are engineering
   extrapolation, clearly labeled.
6. **A disclosed trust boundary in the big-run evidence**: the committed
   large-run reconciliation equalities are self-attested fields whose raw
   unit ledgers live outside the repo; the reconciliation CODE path has
   live small-N negative controls and the rollup chain is recomputed from
   committed summaries (review finding F4, accepted two-tier design —
   [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §5).

The realism work that must precede ANY population-level product claim is
[NEXT_REALISM_PHASE.md](NEXT_REALISM_PHASE.md).
