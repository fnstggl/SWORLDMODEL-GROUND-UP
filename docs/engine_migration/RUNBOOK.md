# Runbook — operating the best-action engine

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

Everything below was executed as written while producing this document
(2026-08-03, HEAD `5667596`); outputs shown are real.

## 1. The two interpreters

| Name | Path | Python | Runs |
|---|---|---|---|
| system | `python3` | 3.11 | product package (stdlib-only), contracts, compiler suite, control plane; engine-gated suites skip cleanly |
| engine | `/home/user/engine-env/bin/python` | 3.12.3 | all three codebases (sworldmodel + pinned Concordia + pinned AgentSociety 2) |

All commands assume the repository root as cwd:
`cd /home/user/SWORLDMODEL-GROUND-UP`.

## 2. Environment setup

### 2.1 Recreate the engine environment (clean install)

Authoritative procedure: `third_party/INTEGRATION_METHOD.md` (pins:
`third_party/UPSTREAM_LOCK.json`). Summary:

```bash
# 1. venv on Python 3.12
uv venv /home/user/engine-env --python /usr/bin/python3.12
# 2. pinned upstreams, editable from the clean checkouts at their SHAs
#    (network fallback: the git+https@<sha> forms in the method doc)
uv pip install -p /home/user/engine-env/bin/python -e /home/user/concordia
uv pip install -p /home/user/engine-env/bin/python -e /home/user/agentsociety2/packages/agentsociety2
# 3. the one environment pin (upstream source unchanged)
uv pip install -p /home/user/engine-env/bin/python "mcp[cli]>=1.13.1,<2"
# 4. test plugins the upstream suites require
uv pip install -p /home/user/engine-env/bin/python pytest pytest-xdist pytest-timeout pytest-asyncio anyio
```

This exact sequence is proven executable from an EMPTY venv by the
monitored clean-install probe: 23.3 s wall (warm wheel cache), 151
packages, versions matching `docs/engine_migration/phase0_engine_env_freeze.txt`
(`tests/engine_robustness/evidence/clean_install.json`, validated by
`test_clean_install_evidence.py`; matrix row 1).

### 2.2 Setup check (run this first)

```bash
env -u DEEPSEEK_API_KEY AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=http://localhost:9 \
  /home/user/engine-env/bin/python -c "import concordia, agentsociety2; import sys; sys.path.insert(0, '/home/user/SWORLDMODEL-GROUND-UP'); import sworldmodel; print('coexistence OK')"
```

Verified output: `coexistence OK`. Import resolution rule: pytest (root
`conftest.py`) and `python -c` from the repo root resolve `sworldmodel`
automatically; a standalone script FILE gets the script's directory on
`sys.path`, not the cwd, so scripts keep the explicit
`sys.path.insert(0, "/home/user/SWORLDMODEL-GROUND-UP")` lines shown in
the worked examples.

### 2.3 Credentials (all optional for offline work)

| Variable | Needed by | Without it |
|---|---|---|
| `AGENTSOCIETY_LLM_API_KEY` (+ optional `_API_BASE`, `_MODEL`) | `import agentsociety2` (module import time) | import refuses naming the variable; set `dummy` for offline (test conftests do this) |
| `DEEPSEEK_API_KEY` | compiler LLM transport; the live-model smoke legs | live legs skip with the exact documented reason; everything deterministic runs |
| `AGENTSOCIETY_LLM_RAY_MAX_WORKERS` | worker parallelism ceiling (scale jobs used 4) | Ray CPU budget default |

Full credential map: `third_party/INTEGRATION_METHOD.md` ("Credential map").

## 3. Running a best-action request — fixture route (worked example)

The committed frozen fixture 1 (`tests/fixtures/best_action/
individual_reply.yaml`; freeze record `FIXTURES.sha256`) through the full
local pipeline. Save as e.g. `/tmp/worked_example.py` and run
`/home/user/engine-env/bin/python /tmp/worked_example.py` from the repo
root:

```python
import sys
from pathlib import Path

REPO = Path("/home/user/SWORLDMODEL-GROUND-UP")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "engine_baseline"))
sys.path.insert(0, str(REPO / "tests" / "engine_counterfactuals"))

# Test-owned scripted models + cited predicates for fixture 1
# (scenario vocabulary lives in tests, never in production code).
from cf_helpers import (MAX_STEPS, SEED, fixture_model_factory,
                        fixture_predicates, fixture_status_rule,
                        load_fixture_one)
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.outcomes import evaluate_branches, rank_branches

# 1. Frozen fixture -> strict loader -> CompiledDecisionWorld + candidates.
fx = load_fixture_one()
print(f"world_id={fx.world.world_id}  candidates="
      f"{[c.candidate_id for c in fx.candidates]}")

# 2. One frozen base plan + genesis snapshot; one branch per candidate
#    (exactly one intervention each); serial seeded deterministic runs
#    through the stock Concordia engine with the agency guard live.
run = run_candidates_detailed(
    fx.world, fx.candidates,
    model_factory=fixture_model_factory(fx),
    seed=SEED, max_steps=MAX_STEPS,
    evaluator_spec=fx.evaluator_spec, registry=fx.registry,
    model_config={"kind": "scripted_test_models"})
print(f"base_plan_hash={run.base_plan_content_hash[:16]}...")

# 3. Trace-based outcome evaluation: every metric cites the recorded
#    events it was computed from; verdicts come from measured metrics
#    (rule R3), never from the engine stop reason.
evaluated = evaluate_branches(
    run.results, fixture_predicates(),
    evaluator_spec=fx.evaluator_spec,
    status_rule=fixture_status_rule, registry=fx.registry)

# 4. Deterministic ranking by the declared metrics in declared order.
recommendation = rank_branches(
    evaluated, fx.evaluator_spec,
    provenance_label="deterministic", registry=fx.registry)

for result in evaluated:
    metrics = {name: metric.value
               for name, metric in result.outcome_metrics.items()}
    print(f"  {result.candidate_id}: status={result.terminal_status} "
          f"metrics={metrics}")
print(f"best_candidate_id={recommendation.best_candidate_id}")
print(f"decided_by={recommendation.validation_status.get('decided_by_metric')}")
assert recommendation.best_candidate_id \
    == fx.expected_deterministic.ranking_first
print("matches the fixture's frozen expected ranking_first: OK")
```

Verified output (byte-for-byte, this run):

```
world_id=w_5097c466f123  candidates=['long_generic', 'concise_relevant', 'urgent_pressure']
base_plan_hash=37714b4a99d543ca...
  long_generic: status=cutoff metrics={'recipient_reply_sent': False, 'meeting_scheduled': False, 'explicit_decline': False}
  concise_relevant: status=success metrics={'recipient_reply_sent': True, 'meeting_scheduled': True, 'explicit_decline': False}
  urgent_pressure: status=failure metrics={'recipient_reply_sent': True, 'meeting_scheduled': False, 'explicit_decline': True}
best_candidate_id=concise_relevant
decided_by=meeting_scheduled
matches the fixture's frozen expected ranking_first: OK
```

The same pipeline with full assertions (byte-identity across three runs,
citations, guard evidence) is the acceptance test — the canonical
single-suite verification:

```bash
/home/user/engine-env/bin/python -m pytest tests/engine_counterfactuals/test_fixture1_deterministic_acceptance.py -q
```

Extensions from here: report artifacts via
`sworldmodel.reporting.build_recommendation_report` /
`build_trace_report` (worked usage: `tests/engine_individual/
test_individual_slice_scripted.py`; committed examples under
`tests/engine_individual/artifacts/`); the `DecisionProblem` route with
user/generated candidates via
`sworldmodel.compilation.prepare_decision_inputs` (worked usage:
`tests/engine_compilation/test_decision_route.py`); distributed execution
via `sworldmodel.backends.agentsociety.branch_executor.
run_candidates_distributed` with a `model_spec` (worked usage:
`tests/engine_distributed/test_stage_a_equivalence.py`).

## 4. Running a best-action request — compiler-artifact route

The committed verbatim copy of a REAL production compile
(`tests/engine_compilation/vectors/compiled_scene_artifact/`, a guard
test keeps it byte-identical to `artifacts/simulations/case1_cold_email/compile/`).
From the repo root (the adapter lazily imports the production shape gate
`compiler.scene_schema.validate_manifest_shape`, so the repo must be
importable):

```python
import os, sys
sys.path.insert(0, "/home/user/SWORLDMODEL-GROUND-UP")
os.chdir("/home/user/SWORLDMODEL-GROUND-UP")   # relative vector path + compiler shape gate

from sworldmodel.compilation import adapt_compiled_artifacts

adapted = adapt_compiled_artifacts(
    "tests/engine_compilation/vectors/compiled_scene_artifact",
    insertion_actor="Jordan Reyes")   # the decision owner, caller-supplied
world = adapted.world                  # a validated CompiledDecisionWorld
print(world.world_id, [(a.actor_id, a.name) for a in world.actors])
```

Verified output (byte-for-byte, this run):

```
w_a5a3fbfaa4cd [('jordan_reyes', 'Jordan Reyes'), ('mark_cuban', 'Mark Cuban')]
```

From `world` onward the flow is identical to §3: pair it with a
`DecisionProblem` through `prepare_decision_inputs`, or hand it straight
to `run_candidates_detailed` with candidates. To produce a FRESH artifact
set instead of using the committed vector, run the unchanged production
compiler (`python3 compile_question.py …`, requires `DEEPSEEK_API_KEY`)
and point `adapt_compiled_artifacts` at its out_dir; a set from a failed
or incomplete compile is refused loudly
(`COMPILER_TO_CONCORDIA_MAPPING.md` §6.5). Field-by-field mapping
semantics: that document, normative.

## 5. Running the test suites

Exact per-suite commands and counts: [TEST_MATRIX.md](TEST_MATRIX.md) §1.
Quick reference:

```bash
# system interpreter
python3 -m pytest tests -q                          # everything (~70 s); expect ONLY the documented
                                                    # initialization_level staleness red between fold-ins
python3 -m pytest tests/test_hardcoding_guard.py -q # scenario-vocabulary guard (3)
python3 -m pytest tests/control_plane -q            # evidence machinery (~60 s)

# engine interpreter, one suite at a time (single-suite runs stay direct)
/home/user/engine-env/bin/python -m pytest tests/engine_contracts -q        # 39, ~45 s (Ray leg)
/home/user/engine-env/bin/python -m pytest tests/engine_baseline -q         # 64, ~5 s
/home/user/engine-env/bin/python -m pytest tests/engine_counterfactuals -q  # 23, ~6 s
/home/user/engine-env/bin/python -m pytest tests/engine_compilation -q      # 46, ~3 s
/home/user/engine-env/bin/python -m pytest tests/engine_distributed -q      # 7, ~45 s
/home/user/engine-env/bin/python -m pytest tests/engine_checkpoint -q       # 16, ~40 s
/home/user/engine-env/bin/python -m pytest tests/engine_individual -q       # 24 (2 live legs skip without DEEPSEEK_API_KEY), ~35 s
/home/user/engine-env/bin/python -m pytest tests/engine_team -q             # 22, ~10 s
/home/user/engine-env/bin/python -m pytest tests/engine_scale -q            # 16, ~40 s
/home/user/engine-env/bin/python -m pytest tests/engine_robustness -q       # 27, ~90 s
```

Do NOT combine `engine_contracts` and `engine_distributed` in one pytest
session ([KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §7.4). Upstream
baseline suites: [TEST_MATRIX.md](TEST_MATRIX.md) §1.4 (run from inside
the checkouts).

## 6. The monitored runner (mandatory for long work)

Any battery naming two or more `tests/engine_*` directories, any scale/
corpus/load run, and every frozen-acceptance batch MUST run through the
monitored runner (hook-enforced; never `&`, `nohup`, or detached
sessions). Shape (real example — the 100-agent scale job,
`PHASE11_SCALE_EVIDENCE.md`):

```bash
python3 .claude/tools/run_monitored.py --job-id <unique-id> \
  --classification exploratory \
  --no-progress-timeout 240 --total-timeout 540 \
  --progress-file <path the child appends per-unit records to> \
  -- <exact child command>
```

- `--classification` is `exploratory` or `frozen_acceptance`.
- The child should append a record per completed unit to
  `--progress-file` (strong progress); the runner also watches log
  movement and CPU. Durable strong-progress evidence is the job record's
  `completed_units` field.
- Outcomes land in the registry `.agent-run/BACKGROUND_JOBS.json` and the
  per-job `job.json` (state `finished`/`no_progress_timeout` (exit 125)/
  `hard_timeout` (124)/`child_failure`; `process_group_terminated`,
  `survivors_after_termination`).
- Bounded receipt runs are the one exemption: `record_receipt.py --run`
  with an explicit `--timeout` (§7).

## 7. Reading the evidence

**Reports (per run).** The recommendation report and complete causal
trace report are canonical JSON built by `sworldmodel/reporting/`;
committed examples: `tests/engine_individual/artifacts/
individual_reply_{recommendation_report,trace_report}.json` (and the
team pair under `tests/engine_team/artifacts/`). The trace report
carries plan hashes, seeds, committed events in commit order, guard
interventions, per-actor records, terminal state, and re-resolved metric
citations — read it to answer "why did this candidate win".

**Distributed run artifacts (per branch workspace).**
`state/branch_result.json` (the strict BranchResult),
`state/runner_record.json` (raw runner record incl. guard
interventions), `state/branch_error.json` (only on failure),
`state/branch_checkpoint.json` (when checkpointing was requested).

**Receipts.** `.agent-run/receipts/<task>__<sha12>__<ts>.json` — each
records the exact command, exit code, git SHA, worktree cleanliness, and
optional `configuration_hashes`. A receipt counts only at its recorded
SHA (or via matching content hashes). Record one:

```bash
python3 .claude/tools/record_receipt.py --task-id <task> --timeout 300 \
  --config-hash "NAME=path/to/artifact" \
  --run -- <exact validation command>
```

**Job records.** Registry: `.agent-run/BACKGROUND_JOBS.json`. Committed
durable copies: `tests/engine_scale/evidence/<job-id>/job.json` (+
ledgers, 52 files hash-manifested) and
`tests/engine_robustness/evidence/clean_install.json`.

## 8. Checkpoint / resume

- **Local**: `run_branch(..., checkpoint_after=k)` checkpoints at the
  end-of-step boundary and continues (or halts with
  `halt_at_checkpoint=True`); `run_branch(..., resume_from=blob)`
  resumes inside an active seeded scope. Worked usage:
  `tests/engine_checkpoint/test_local_equivalence.py`.
- **Distributed**: `run_candidates_distributed(..., checkpoint_after=k)`
  persists `state/branch_checkpoint.json` per branch;
  `run_interrupted_then_resume(...)` drives halt-at-checkpoint then
  fresh-batch resume from the workspaces. Worked usage:
  `tests/engine_checkpoint/test_distributed_resume.py`.
- Restores refuse loudly on plan-hash mismatch, tamper, or resuming
  outside a seeded scope; a resumed run's evidence (steps, statuses,
  guard records) is ABSOLUTE, proven byte-equal to uninterrupted
  execution. Models at restore must be behaviorally prompt-pure
  ([FINAL_ARCHITECTURE.md](FINAL_ARCHITECTURE.md) §4).

## 9. Common failures → where to look

`docs/engine_migration/OPERATIONAL_ROBUSTNESS_MATRIX.md` is the
authoritative per-scenario reference (evidence + verdicts per row):

| Symptom | Matrix row | First move |
|---|---|---|
| Fresh env won't build / imports fail | 1 (clean install) | re-run §2.1 exactly; compare against `clean_install.json` phases |
| First run slow or wedged | 2 (cold start) | a healthy cold start completes a 1-candidate branch < 60 s |
| Two runs differ | 3 (repeated runs) | diff branch signatures; confirm scripted models + same seed; live runs are expected to differ (§1 of KNOWN_LIMITATIONS) |
| Process killed mid-run | 4–5 (interruption/resume) | resume from the persisted checkpoint; byte-equality is the proven bar |
| One actor/branch errored | 6–7 | the failure is IN the results (`infrastructure_errors`, `terminal_status='incomplete'`, `branch_error.json`); siblings are valid; re-run the one candidate |
| Request refused before any run | 8–9 (malformed inputs) | read the collected `ContractValidationError` issues; fix input; nothing was registered |
| `AGENTSOCIETY_LLM_API_KEY is required` / `RuntimeTechnicalFailure` naming a variable | 10 (credentials) | set the named variable (dummy suffices offline for agentsociety2) |
| Run hangs on a model call | 11 (timeout; gap G1) | the monitored runner's no-progress bound is the enforcement — check the job record (exit 125), then resume |
| Garbage model output | 12 | it is committed as that actor's turn and measures False (fail-closed); strict-consumer breaks surface as that branch's recorded error |
| `WorkerCrashedError` | 13 (Ray worker) | typed, bounded (< 30 s); single crashes normally auto-retry; workspaces are exactly-once safe; re-run the step |
| `CollectionIntegrityError` / corrupt workspace file | 7, 14 | open the named agent/branch workspace; restore the file or last good checkpoint and re-step (demonstrated recovery path) |
| Validator red `initialization_level` only | — | the documented master-receipt staleness ([KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §5); re-record per DECISIONS "Receipt re-record protocol" |
