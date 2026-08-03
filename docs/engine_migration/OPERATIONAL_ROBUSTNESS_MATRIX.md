# Operational Robustness Matrix (Acceptance Gate I)

Directive gate I (MASTER_IMPLEMENTATION_DIRECTIVE.md, "I. Operational
robustness") names fourteen scenarios and one bar: **failures must be
explicit, bounded, and recoverable where possible.**  This matrix maps
every scenario to its evidence -- existing suite tests are CITED, the
gaps are closed by the new `tests/engine_robustness/` suite -- and gives
the three verdicts per row.  Recorded gaps and limitations are in the
findings section at the end; nothing below is cosmetic.

Ownership: `tests/engine_robustness/` and this document belong to the
`operational-robustness-matrix` task (test-watchdog).  No production
code was changed for this gate; every behavior described is the
behavior that shipped.

How to run the new suite (engine environment; < 2 minutes wall):

    /home/user/engine-env/bin/python -m pytest tests/engine_robustness -q

Under the system Python 3.11 the engine-gated modules skip at collection
and the stdlib evidence tier still runs (3 passed, 8 skipped).

Verdict vocabulary:

- **Explicit** -- the failure surfaces as a typed exception, a typed
  refusal with collected issues, or a structured artifact/record naming
  the failing unit; never a silent `None`, silent skip, or fabricated
  result.
- **Bounded** -- the failure cannot hang the caller or grow without
  limit; a deadline, budget, kill, or immediate refusal bounds it.
- **Recoverable** -- where the design provides recovery, a demonstrated
  re-run/resume/restore path returns to correct operation.

## Summary

| # | Scenario | Evidence (primary) | Explicit | Bounded | Recoverable |
|---|----------|--------------------|----------|---------|-------------|
| 1 | Clean installation | NEW `test_clean_install_evidence.py` (3) + monitored probe job | yes | yes (480 s budget; 23.3 s measured) | n/a (fresh env) |
| 2 | Cold startup | NEW `test_cold_startup.py` (1) | yes | yes (< 60 s asserted) | n/a |
| 3 | Repeated runs | existing determinism/repeat suites (cited) + cold-start signature | yes | yes | n/a |
| 4 | Interruption | NEW `test_interruption_resume.py` (2: SIGTERM, SIGKILL) | yes | yes (15 s death budget) | yes (resume proven) |
| 5 | Resume | existing `tests/engine_checkpoint/` + scale restart (cited) + row 4 | yes | yes | yes |
| 6 | One actor failure | existing cf/individual/distributed/scale isolation tests (cited) | yes | yes | partial (siblings unaffected; branch reported) |
| 7 | One branch failure | existing failure-isolation + no-silent-loss tests (cited) | yes | yes | partial (re-run; failure reported in place) |
| 8 | Malformed candidate | existing contract/route strict-parse (cited) + NEW `test_malformed_inputs.py` (2 of 3) | yes | yes (refused pre-execution) | yes (fix input, resubmit) |
| 9 | Malformed compiled input | existing adapter/contract refusals (cited) + NEW boundary test | yes | yes | yes (fix input, resubmit) |
| 10 | Missing model credentials | NEW `test_missing_credentials.py` (4) | yes | yes (import/call boundary) | yes (set variable, rerun) |
| 11 | Model timeout | NEW `test_model_timeout.py` (2) -- inner seam + **outer bound (recorded gap G1)** | yes | yes at the semantic-runtime seam; **outer-layer only for injected engine models** | yes (retry/rerun) |
| 12 | Model malformed output | NEW `test_model_malformed_output.py` (7) + existing generator/attribution suites | yes / fail-closed | yes (limitation L1 noted) | n/a (measured, never counted) |
| 13 | Ray worker failure | NEW `test_ray_worker_failure.py` (2) | yes (typed `WorkerCrashedError`) | yes (< 30 s asserted; 0.6 s measured) | yes (re-run + auto-retry, exactly-once) |
| 14 | Partial workspace corruption | NEW `test_workspace_corruption.py` (3) + existing tamper suites (cited) | yes (finding F-R1: file naming partial) | yes | yes (restore file / last good checkpoint) |

All test ids below are relative to the repository root; `NEW` marks
tests added by this task in `tests/engine_robustness/`.

---

## Row 1 -- Clean installation

**Evidence.**
NEW `tests/engine_robustness/test_clean_install_evidence.py` (3 tests)
validates the committed structured evidence
`tests/engine_robustness/evidence/clean_install.json`, produced by
`tests/engine_robustness/clean_install_probe.py` under monitored job
`robustness-clean-install` (record:
`.agent-run/jobs/robustness-clean-install/job.json`, state `finished`,
exit 0).  The probe rebuilds the engine environment FROM AN EMPTY VENV
following `third_party/INTEGRATION_METHOD.md` step for step: pinned
checkouts verified at their `third_party/UPSTREAM_LOCK.json` SHAs and
clean; `uv venv --python /usr/bin/python3.12`; editable installs of both
upstreams; the documented `mcp[cli]>=1.13.1,<2` environment pin; the
documented test plugins; the doc's coexistence check under dummy
credentials; then ONE fast engine smoke suite
(`tests/engine_counterfactuals/test_failure_isolation.py`, 2 passed)
inside the fresh environment.  Measured: **23.3 s wall total, 151
packages** (gdm-concordia 2.4.0, agentsociety2 2.8.4, ray 2.56.1,
litellm 1.95.0, mcp 1.29.0 -- matching
`docs/engine_migration/phase0_engine_env_freeze.txt`), venv removed
afterwards.  Timing honesty: 23.3 s reflects a warm local `uv` wheel
cache; a fresh machine pays wheel downloads through the documented
`git+https` / PyPI path instead -- the sequence and outcome are what the
evidence pins, and the recorded budget (480 s, monitored outer bound
540 s) bounds the cached path.

This row is also gate A's "reproducible from a clean environment"
evidence: the environment used by every engine suite is reconstructible
from the lock + the integration doc alone, proven by execution.

**Verdicts.** Explicit: every phase failure is a named failing phase in
the evidence with the command, exit code, and output tail (demonstrated
live: the first probe run failed loudly on a checkout-name mismatch and
recorded exactly which pin failed).  Bounded: per-phase subprocess
timeouts, a recorded total budget, and the monitored runner's
no-progress/total kills above it.  Recoverable: n/a -- a failed install
is discarded and repeated; nothing durable is at risk.

## Row 2 -- Cold startup

**Evidence.**
NEW `tests/engine_robustness/test_cold_startup.py::
test_cold_start_completes_one_branch_from_nothing`: a FRESH engine
interpreter process is given an EMPTY run root and nothing else -- the
child asserts the root is empty, that the local first-run path never
even imports `ray`, runs one complete 1-candidate scripted branch
through the public `run_candidates_detailed`, and writes a structured
report.  The parent asserts exit 0 within 90 s (child-measured wall
< 60 s), `terminal_status == "cutoff"`, 3 committed events, correct
measured metrics, no surviving child processes, and that the fresh
process's branch signature is BYTE-IDENTICAL to the same request run in
the long-lived test process (first run == steady state).

Existing complements: every Phase 11 monitored scale job was itself a
cold start (fresh process, fresh Ray runtime brought up through
`init_dispatchers()`, empty partition roots) -- verified post-hoc by
`tests/engine_scale/test_scale_verification.py::
test_every_monitored_job_finished_with_strong_progress`; the
distributed/scale session fixtures perform the Ray cold bring-up on
every suite run.

**Verdicts.** Explicit: any cold-start defect is a nonzero child exit
with the error on stderr, asserted.  Bounded: 90 s harness kill above a
60 s child assertion.  Recoverable: n/a.

## Row 3 -- Repeated runs

**Evidence (existing, cited).**
- `tests/engine_counterfactuals/test_determinism_and_order.py::
  test_identical_candidates_twice_are_byte_identical` and
  `::test_candidate_order_permutation_changes_nothing` -- identical
  requests byte-identical across repeats and orderings.
- `tests/engine_individual/test_gate_c_clauses.py::
  test_repeated_executions_do_not_fail_mechanically` -- repeated slice
  executions, no mechanical degradation.
- `tests/engine_individual/test_individual_slice_scripted.py::
  test_report_content_hashes_stable_across_two_runs` and
  `::test_committed_example_artifacts_regenerate_byte_identically`.
- `tests/engine_compilation/test_mapping_correctness.py::
  test_same_input_twice_yields_byte_identical_world_and_plan`.
- Scale: the fast-tier reconciliation and the committed 100/1000-agent
  evidence (`tests/engine_scale/test_scale_verification.py`) reconcile
  repeated tick execution exactly (no lost/duplicated actions across
  repeats at scale).

NEW addition: row 2's fresh-process signature equality extends
repetition across PROCESS boundaries (a rerun in a new process
reproduces the prior run byte-for-byte).

**Verdicts.** Explicit/bounded: repeats either reproduce exactly or
fail an equality assertion naming the divergence.  Recoverable: n/a.

## Row 4 -- Interruption

**Evidence.**
NEW `tests/engine_robustness/test_interruption_resume.py::
test_killed_branch_process_dies_bounded_and_resumes[sigterm|sigkill]`:
a real mid-run branch process (subprocess harness,
`_child_checkpoint_then_hang.py`) checkpoints at the Stage B end-of-step
boundary, atomically persists the blob, then stalls; the test kills the
child's WHOLE process group with SIGTERM and -- separately -- with the
unmaskable SIGKILL.  Asserted: death by exactly the sent signal within a
15 s budget; NO surviving process carrying the child's unique marker
(/proc scan); the persisted checkpoint parses and carries the correct
cursor (2 of 4 steps); and a resume IN A DIFFERENT PROCESS completes the
branch with a full-signature byte-match against an uninterrupted
reference run.

Existing complements: the monitored runner's own group-termination and
escalation discipline is adversarially tested in
`tests/control_plane/test_run_monitored.py` (stubborn descendants,
direct-child-dies-first cases); the DELIBERATE interrupt (halt at the
boundary, resume by a second batch call) is proven distributed in
`tests/engine_checkpoint/test_distributed_resume.py::
test_interrupted_branch_resumed_from_workspace_equals_uninterrupted`.

**Verdicts.** Explicit: the returncode names the signal; the kill and
survivor scan are asserted, not assumed.  Bounded: 15 s death budget
(measured well under).  Recoverable: yes -- proven resume to a
byte-identical terminal result from the killed process's persisted
state.

## Row 5 -- Resume

**Evidence (existing, cited).**
- `tests/engine_checkpoint/test_restore_correctness.py` -- no premise
  redelivery, no duplicate seeding, RNG continuity with a NAIVE-resume
  divergence counter-example, refusal outside a seeded scope, tampered/
  incomplete checkpoint refusals (incl. through the Phase 3 snapshot
  contract).
- `tests/engine_checkpoint/test_local_equivalence.py` -- checkpoint/
  restore/continue equals uninterrupted, byte-for-byte, two seeds.
- `tests/engine_checkpoint/test_distributed_resume.py` (both tests) --
  workspace-based interrupt/resume and checkpoint-and-continue through
  the real distributed substrate.
- `tests/engine_scale/test_scale_fast_tier.py::
  test_checkpoint_resume_across_driver_restart` and the committed
  1000-agent evidence (`test_scale_verification.py::
  test_1000_agent_partitions_reconciled_and_resumed`) -- segment B
  resumed in a FRESH PROCESS with a fresh Ray runtime from persisted
  workspaces + a spec-hash-bound driver checkpoint.

NEW addition: row 4 extends resume to state persisted by a process that
was subsequently KILLED (not deliberately halted).

**Verdicts.** Explicit: resume refuses loudly on spec/hash mismatch,
tamper, or missing state (cited tests).  Bounded: yes.  Recoverable:
yes -- this row IS the recovery mechanism, proven equivalent to
uninterrupted execution.

## Row 6 -- One actor failure

**Evidence (existing, cited).**
- `tests/engine_counterfactuals/test_failure_isolation.py::
  test_mid_branch_model_failure_is_reported_and_isolated` -- ONE actor's
  model (the recipient) raises mid-branch: that branch reports
  `terminal_status='incomplete'` with the injected error verbatim in
  `infrastructure_errors` and its partial trace preserved, IN ITS LIST
  POSITION; sibling branches are byte-identical to a run without the
  failing candidate (nothing leaked).
- `tests/engine_individual/test_gate_c_clauses.py::
  test_trajectory_reaches_explicit_terminal_status_for_all_four` -- the
  incomplete-status scenario at the slice level: an actor-model failure
  yields an explicit `incomplete` in the trace report with the error
  recorded, alongside the three healthy statuses.
- Distributed: `tests/engine_distributed/
  test_failure_isolation_distributed.py::
  test_worker_mid_branch_failure_is_isolated_and_dual_channel` -- the
  same injection INSIDE a Ray worker: dual-channel failure evidence
  (driver ok=False + workspace error file + persisted partial result),
  siblings equal to the local reference.
- Scale: `tests/engine_scale/test_scale_fast_tier.py::
  test_injected_failure_is_isolated_and_dual_channel` and the committed
  100/1000-agent evidence -- a failing agent produces a structured error
  artifact, is excluded from later ticks, and neighbors complete.

**Verdicts.** Explicit: typed/recorded per the contract R3 shape (an
engine stop without an evaluator verdict is `incomplete`, never a
fabricated verdict).  Bounded: the failure ends that branch/agent only.
Recoverable: partial by design -- siblings complete; the failed unit is
reported for re-run (rows 4/5/13 prove re-run paths); it is never
silently replaced.

## Row 7 -- One branch failure

**Evidence (existing, cited).**
- `tests/engine_counterfactuals/test_failure_isolation.py` (both
  tests) -- mid-branch failure AND factory failure before any model
  exists: reported in place with `runner_records[cand] is None` for the
  pre-runner case; siblings byte-identical either way.
- `tests/engine_distributed/test_no_silent_loss.py::
  test_deleted_result_file_raises_loudly_naming_the_branch` -- a branch
  whose authoritative result file vanishes is a `CollectionIntegrityError`
  NAMING the branch, never a silent partial success;
  `::test_hook_seam_without_corruption_is_inert` is the negative
  control.
- The distributed dual-channel row-6 test covers the escalated
  mid-branch branch failure (driver channel + error file + partial
  result agreeing).

**Verdicts.** Explicit: failed branches occupy their list position with
recorded errors; collection refuses disagreement loudly.  Bounded: one
branch.  Recoverable: partial -- the failing candidate can be re-run
(fresh run/registry), and the distributed collection never fabricates a
result for it.

## Row 8 -- Malformed candidate

**Evidence (existing, cited).**
- `tests/test_decision_contracts.py` (70-test strict-parse suite; runs
  under BOTH interpreters): per-class missing/unknown/wrong-typed
  fields, enum violations, `test_malformed_llm_garbage_reports_all_errors`
  (every defect collected, none repaired),
  `test_fabricated_candidate_id_is_rejected`, timing-window rejection
  (`test_candidate_timing_outside_horizon_is_rejected`), provenance
  rules (`test_generated_candidate_requires_generator_hash`).
- Route (`tests/engine_compilation/test_decision_route.py`):
  `test_malformed_generator_output_fails_loudly_with_all_defects`
  (non-JSON, schema-violating JSON, empty/extra fields -- one loud
  refusal, no repair, no re-roll),
  `test_owner_must_resolve_to_the_worlds_insertion_actor`,
  `test_route_with_no_candidates_at_all_is_refused`,
  `test_mixed_user_and_generated_candidates_share_one_namespace`.
  (Generated candidate ids are code-owned `gen_NNN`, so a generator
  cannot mint duplicate ids; duplicates can only arrive in the caller's
  list -- covered below.)

**NEW (run-boundary last line of defense).**
`tests/engine_robustness/test_malformed_inputs.py::
test_duplicate_candidate_ids_are_refused_before_any_branch_runs`
(duplicate ids in one request: typed `duplicate_id` refusal of the WHOLE
call with the model factory provably never invoked) and
`::test_empty_candidate_list_and_bad_seed_are_typed_refusals` (empty
list; string seed; boolean seed -- bool is not coerced to int).

**Verdicts.** Explicit: `ContractValidationError` with issue paths and
codes, all defects collected.  Bounded: refused BEFORE any branch
executes.  Recoverable: yes -- fix the input and resubmit; a refused
call registers nothing.

## Row 9 -- Malformed compiled input

**Evidence (existing, cited).**
- Contracts strict parse for `CompiledDecisionWorld` /
  `ConcordiaInitializationPlan` (`tests/test_decision_contracts.py`,
  incl. `test_duplicate_actor_ids_and_names_are_rejected`,
  `test_world_cutoff_must_be_strictly_after_start`, semantics-layer
  world checks).
- Adapter refusals (`tests/engine_compilation/`):
  `test_artifact_set_loading.py::test_missing_required_files_are_refused`
  and `::test_incomplete_or_failed_compiles_are_refused` (a compiler
  output directory missing files or marked failed/incomplete is
  refused, named);
  `test_mapping_correctness.py::
  test_manifest_shape_gate_rejects_unknown_missing_and_wrong_types`,
  `::test_malformed_or_out_of_window_times_fail_loudly`,
  `::test_undecodable_actor_names_fail_loudly_with_all_defects`,
  `::test_unknown_manifest_fields_cannot_be_silently_dropped` (adapter
  reviewer verdict D3: no silent-discard input could be crafted).

**NEW.** `tests/engine_robustness/test_malformed_inputs.py::
test_malformed_world_and_candidate_objects_collect_one_refusal` -- a
non-world object where the compiled world belongs, together with a
non-candidate list entry, is ONE collected refusal naming both fields at
the run boundary.

**Verdicts.** Explicit/bounded/recoverable: as row 8.

## Row 10 -- Missing model credentials

**Evidence.** NEW `tests/engine_robustness/test_missing_credentials.py`
(4 tests), covering every layer of the credential map
(`third_party/INTEGRATION_METHOD.md`, risk R6):

- `test_agentsociety_import_refuses_without_credentials` -- with
  `AGENTSOCIETY_LLM_API_KEY` removed from a subprocess environment,
  `import agentsociety2` refuses AT IMPORT (the documented boundary)
  with `ValueError: AGENTSOCIETY_LLM_API_KEY is required. Please set
  this environment variable...` -- explicit, actionable, and impossible
  to reach mid-run.  (Empirical note: `AGENTSOCIETY_LLM_API_BASE`
  carries an upstream default and does not independently refuse.)
- `test_product_import_survives_and_engine_boundary_names_the_variable`
  -- `import sworldmodel` and the branch-executor module import succeed
  WITHOUT credentials (offline analysis is never blocked); the engine
  bring-up boundary (`_import_engine`) then fails naming
  `AGENTSOCIETY_LLM_API_KEY` before any workspace or branch could
  exist.
- `test_semantic_runtime_transport_names_missing_deepseek_key` --
  `RuntimeCaller` with `DEEPSEEK_API_KEY` unset raises the typed
  `RuntimeTechnicalFailure` naming the variable, instantly (no network
  attempt), with both attempts in the structured per-call log.
- `test_live_smoke_skips_exactly_when_deepseek_key_is_unset` -- skip
  discipline asserted on the live-smoke suite's OWN source (the
  module-level `pytest.mark.skipif` condition is exactly the env-var
  emptiness check) AND by running the file without the key: exactly
  2 skipped with the documented reason, zero passes, zero network.
  With the key set, the suite's flake policy makes an unreachable
  endpoint reportable rather than skippable (its module docstring +
  `LIVE_ENDPOINT_UNREACHABLE` handling).

**Verdicts.** Explicit: the exact variable is named at every boundary.
Bounded: import-time / first-call refusal; nothing runs first.
Recoverable: yes -- set the variable and rerun.

## Row 11 -- Model timeout

**Evidence.** NEW `tests/engine_robustness/test_model_timeout.py`:

- `test_runtime_caller_deadline_bounds_a_hung_provider` -- the
  INNERMOST EXISTING seam: the semantic-runtime transport
  (`sworldmodel/semantic_runtime/llm.py`) carries a whole-request wall
  deadline (thread-join, deployed 270 s), a socket timeout (90 s), and a
  chunked-read deadline (240 s), asserted present and ordered; the
  mechanism is exercised at a test-scale deadline: a provider blocked
  30 s is cut off by the deadline, retried once, and surfaces as the
  typed `RuntimeTechnicalFailure: ... provider request exceeded ...`
  with both attempts in the structured call log, in < 5 s wall.
  (`sworldmodel/llm_mind.py::_http_json` carries its own 120 s socket
  timeout for the compiler-side path; same transport family, not
  separately exercised.)
- `test_engine_branch_has_no_inner_seam_and_outer_bound_kills_hung_branch`
  -- **recorded gap G1**: the ENGINE BRANCH path (`concordia_local
  .runner` + counterfactual manager driving INJECTED model objects) has
  NO in-branch model-call timeout seam; an injected model that never
  returns hangs the branch.  The absence is PINNED by assertion on the
  entry-point signatures (adding a seam later fails this test until the
  row is rewritten), and the OUTER bound is proven end to end: a real
  branch whose recipient-model call hangs (`_child_hung_branch.py`,
  announced mid-branch) is killed by the monitored runner's no-progress
  bound against a synthetic project tree -- exit 125, job record
  `state=no_progress_timeout`, `process_group_terminated=true`,
  `survivors_after_termination=[]`, termination reason naming the
  configured timeout, and a /proc scan confirming nothing survived.

Existing complement: the monitored runner's health taxonomy and kill
discipline are adversarially tested in
`tests/control_plane/test_run_monitored.py`.

**Verdicts.** Explicit: typed failure at the transport seam; structured
job record at the outer bound.  Bounded: at the semantic-runtime seam
for live-model transport; **for injected engine models, bounded at the
outer layer only (G1)** -- every long engine run in this project is
required to run under the monitored runner (control-plane rule 5), which
is what makes the outer bound an operational guarantee rather than a
hope.  Recoverable: yes -- a killed run's persisted state resumes
(rows 4/5); the transport failure is retried once by design.

## Row 12 -- Model malformed output

**Evidence.** NEW `tests/engine_robustness/
test_model_malformed_output.py` (7 tests) at the runner level, plus the
cited construction-time suites.

The honest bar: an actor model RETURNING garbage is not an execution
failure -- the engine commits it as that actor's turn.  What must hold,
and is asserted:

- `test_actor_garbage_completes_bounded_with_fail_closed_metrics`
  (5 payload classes: empty, whitespace, control characters,
  JSON-shaped garbage, 200 kB oversized): the run completes bounded
  with a valid `BranchResult` (`cutoff`, no infrastructure errors,
  exactly premise + one turn per actor) and EVERY metric measures
  False -- garbage is never counted as success (the attribution-anchored
  evaluators fail closed).
- `test_gm_garbage_observer_answer_fails_closed_on_delivery` -- a GM
  answering the observer question with garbage delivers the event to
  NOBODY (fail closed on information flow, proven against a correct-GM
  control leg via actor memories); the run stays bounded and complete.
- `test_garbage_breaking_a_strict_consumer_is_an_explicit_branch_error`
  -- when garbage starves a strict downstream model, the break is that
  branch's recorded infrastructure error (`incomplete`, partial trace
  preserved) -- reported in place, never hidden, never a hang.

Existing, cited: generator-side malformed output refusals (row 8's
route test and `test_decision_contracts.py::
test_malformed_llm_garbage_reports_all_errors`); a RAISING actor model
(row 6); and the attribution/spoof family -- output shaped like ANOTHER
actor's turn is rewritten by the agency guard and never counted by the
evaluators (`tests/engine_individual/test_individual_proxy_attribution
.py`, `tests/engine_team/test_team_proxy_attribution.py`,
`tests/engine_counterfactuals/test_predicate_attribution.py`; review
finding F1 closed).

**Recorded limitation L1**: no engine-side size cap exists on INJECTED
model output -- the 200 kB payload is committed verbatim to the trace
(bounded per turn by the step budget, not by size).  The live-model
path is bounded upstream by the transport (`MAX_RESPONSE_BYTES` = 4 MB,
provider `max_tokens`); injected models are trusted test/driver code by
design.

**Verdicts.** Explicit: fail-closed measurement plus recorded
infrastructure errors where consumption breaks.  Bounded: yes (L1
noted).  Recoverable: n/a -- nothing to recover; garbage never corrupts
a verdict.

## Row 13 -- Ray worker failure

**Evidence.** NEW `tests/engine_robustness/test_ray_worker_failure.py`
(2 tests): a worker OS PROCESS is SIGKILLed while executing a
`step_agent_batch` task on materialized scale-unit workspaces (the same
public primitives the branch executor and scale harness drive; the
victim is identified by the `ray::step_agent_batch` process title our
own submission creates, and killed only while our task is in flight).

- `test_killed_worker_is_a_typed_bounded_error_and_rerun_recovers`:
  with retries disabled the kill surfaces at `ray.get` as Ray's TYPED
  `WorkerCrashedError` (< 30 s asserted; ~0.6 s measured) -- never a
  hang, never a silent loss; the killed attempt left NO partial
  workspace evidence (atomic end-of-step writes); the SIBLING agent
  completes on a surviving/replacement worker; a RE-RUN of the killed
  step succeeds with exactly-once file evidence.
- `test_single_kill_with_retry_budget_auto_recovers_exactly_once`: with
  one retry allowed, a single worker kill AUTO-RECOVERS via Ray's task
  re-execution -- caller sees success, workspace still exactly-once
  (idempotent workspaces make at-least-once execution safe); asserted
  afterwards: no step-task worker still running.  The packaged task
  ships no retry override (`_default_options == {}` asserted), so
  production submissions inherit Ray's system default task-retry
  policy: a lone worker crash is normally absorbed transparently, and
  the executor's `task_error` channel (the `except` arm of its harvest
  loop, which synthesizes the reported-never-hidden failure
  `BranchResult`) is the terminal path once retries exhaust.

Existing complements: in-worker APPLICATION failures (worker survives
and reports) are the distributed dual-channel and scale injections of
rows 6-7; collection-integrity refusals are row 7's no-silent-loss
tests.

**Verdicts.** Explicit: typed exception at the driver; structured
synthesized failure at the executor layer.  Bounded: asserted.
Recoverable: yes -- both automatic (task retry) and manual (re-run from
the intact workspace), with exactly-once evidence both ways.

## Row 14 -- Partial workspace corruption

**Evidence.** NEW `tests/engine_robustness/test_workspace_corruption.py`
(3 tests) driving the REAL AgentSociety step path (the async cores the
Ray tasks wrap) against deliberately corrupted workspace files:

- `test_corrupt_agent_json_is_explicit_isolated_and_restorable`:
  truncated `AGENT.json` -> explicit per-agent `ok=False` (typed JSON
  decode failure) while a healthy agent IN THE SAME BATCH completes
  (isolation); restoring the file recovers the agent with sequence and
  tamper-evident hash-chain continuity intact (the corrupted attempt
  wrote nothing).
- `test_corrupt_state_file_is_explicit_and_restorable`: garbled
  `state/unit_state.json` -> explicit per-agent failure; a state file
  claiming a FOREIGN agent identity is refused with an error literally
  naming "workspace corruption" and the foreign id (the agent
  template's own integrity check); restore -> recovery.
- `test_corrupt_checkpoint_blob_refused_then_recovered_from_last_good`:
  a garbled persisted `branch_checkpoint.json` -> explicit refusal with
  the branch agent's STRUCTURED error artifact (phase
  `setup_or_run`, `error_type` JSONDecodeError, candidate and branch
  ids), no fabricated result; restoring the LAST GOOD checkpoint and
  clearing the error marker resumes the branch to its complete, correct
  terminal result (`resumed_from_checkpoint=true`, absolute step
  accounting) -- recovery-where-possible, demonstrated end to end.

Existing, cited: checkpoint PAYLOAD tamper (semantic corruption of a
parseable blob -- flipped hashes, wrong plan, missing keys) is refused
loudly by `tests/engine_checkpoint/test_restore_correctness.py::
test_tampered_checkpoints_are_refused_loudly` (incl. through the
Phase 3 snapshot contract); action-log tamper (edited/lost/duplicated
rows breaking the hash chain) is caught by
`tests/engine_scale/test_scale_fast_tier.py::
test_reconciliation_catches_lost_and_duplicated_actions`; a DELETED
result file is row 7's loud collection refusal.

**Verdicts.** Explicit: yes, with **finding F-R1** (below) on file
naming.  Bounded: one agent/branch; batches never abort wholesale.
Recoverable: yes -- restore the file / the last good checkpoint and
re-step, demonstrated.

---

## Findings, recorded gaps, and limitations

**G1 (row 11, gap, bounded-at-the-outer-layer).**  No in-branch
model-call timeout seam exists for INJECTED engine models: neither
`run_branch` / `run_built_branch` nor `run_candidates_detailed` accepts
a timeout, and an injected model that never returns hangs its branch.
The semantic-runtime and compiler transports carry real deadlines
(90/240/270 s; 120 s), so LIVE model calls through those paths are
bounded innermost; for the engine path the bound is the monitored
runner's no-progress/total kill, which control-plane rule 5 makes
mandatory for every long run.  The gap's absence is pinned by a
signature assertion so a future seam forces this row to be rewritten
and tested directly.  Not patched here: production changes are outside
this task's charter.

**F-R1 (row 14, low).**  A corrupted workspace FILE surfaces on the
driver channel as the raw `JSONDecodeError` repr in the per-agent
record: the failure names the AGENT (record id -> workspace directory)
but not WHICH file is corrupt.  The branch agent's own error artifact
adds phase/candidate/branch identity when its step is reachable;
`AGENT.json` corruption fails before the agent object exists
(upstream `from_workspace`), so only the driver record reports.
Explicit and isolated: yes.  File-naming: partial -- diagnosis requires
opening the named agent's workspace.  Upstream (pinned agentsociety2)
owns the reporting seam; recorded, not patched.

**L1 (row 12, limitation).**  No engine-side size cap on injected model
output; a 200 kB reply becomes a 200 kB committed event.  Live-model
paths are bounded upstream by transport caps (4 MB body ceiling,
provider `max_tokens`).  Injected models are trusted driver/test code
by design; recorded for operators embedding untrusted model wrappers.

**Note (row 13).**  `step_agent_batch` ships no explicit `max_retries`,
so Ray's system default task-retry policy applies to worker crashes:
single crashes normally self-heal (proven exactly-once safe by the
atomic end-of-step workspace writes); exhausted retries surface as the
typed error the executor's `task_error` channel converts into a
reported failure result.

**Note (row 10).**  `AGENTSOCIETY_LLM_API_BASE` does not independently
refuse at import (upstream ships a default); only
`AGENTSOCIETY_LLM_API_KEY` is the hard import-time requirement.  The
integration doc's dummy-key requirement matches observed behavior.

## Suite inventory (new tests)

`tests/engine_robustness/` -- 27 tests, < 90 s wall in the engine
environment (3 tests + 8 module skips under system Python 3.11):

| Module | Tests | Rows |
|--------|-------|------|
| `test_clean_install_evidence.py` | 3 | 1 (+ gate A) |
| `test_cold_startup.py` | 1 | 2 (+ 3) |
| `test_interruption_resume.py` | 2 | 4-5 |
| `test_malformed_inputs.py` | 3 | 8-9 |
| `test_missing_credentials.py` | 4 | 10 |
| `test_model_malformed_output.py` | 7 | 12 |
| `test_model_timeout.py` | 2 | 11 |
| `test_ray_worker_failure.py` | 2 | 13 |
| `test_workspace_corruption.py` | 3 | 14 |

Support (not collected): `conftest.py`, `robustness_helpers.py`,
`robustness_model_specs.py`, `_child_cold_start.py`,
`_child_checkpoint_then_hang.py`, `_child_hung_branch.py`,
`clean_install_probe.py`, `evidence/clean_install.json`.
