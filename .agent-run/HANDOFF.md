# Handoff

Mode `implementation`, phase `compiler_to_concordia_adapter`, branch
`claude/concordia-agentsociety-best-action-engine` (draft PR #9, unmerged by
design). Phases 0-8 + guard hardening COMPLETE with per-task completion
evidence and receipts; phases 3-7 adversarial review findings all closed
(reviews/PHASE_3_7_BOUNDARY_REVIEW.md).

## Position

- Phase 8 (whole-branch checkpoint/restore, Stage B): complete; A=A'=B
  signature equality under two seeds; p2/p7 Ray-suite receipts re-recorded
  clean at the fold-in; worker-RNG distributed equivalence candidate landed
  (review D5).
- Agency-guard hardening (findings 6+7): complete at a4112f6 -- all four
  evasion classes detected with nearby-shape non-over-block proofs;
  hardcoding-guard allowlist narrowed to per-file word allowances.
- IN FLIGHT: compiler-to-Concordia adapter (implementation subagent, sole
  writer of sworldmodel/compilation/ + docs/engine_migration/
  COMPILER_TO_CONCORDIA_MAPPING.md + tests/engine_compilation/). The agent
  was paused 12:25-16:46Z by a rejected baseline command (see incident
  below) and has been resumed with monitored-run instructions.

## 2026-08-03 incident: "engine DoD baseline before changes"

Diagnosis: the adapter subagent's pre-change engine-DoD baseline (bare
foreground 5-suite pytest) was rejected by the permission layer at
12:25:40Z; no process ever spawned (no PID/PGID, BACKGROUND_JOBS
active=[], zero matching processes in ps, no log, no heartbeat); the
subagent paused silently for 4h20m. There was nothing for run_monitored
timeouts to stop because the monitor was never engaged -- multi-suite
engine pytest matched no long-running pattern (hook maintenance #5 in
DECISIONS.md fixed that classification, with regression tests), and a
permission-paused subagent emits no completion signal (lead now arms a
send_later liveness check when launching writer agents).

Result: bounded baseline re-run through run_monitored.py with per-test
strong progress (pytest -v teed into --progress-file), no-progress and
total timeouts -- see BACKGROUND_JOBS.json `engine-dod-baseline-pre-adapter`
for the record; the adapter agent resumed from durable state (no new
worker, no new lead session).

## On wake / fresh session

1. Read RUN_STATE.json; run the validator. If the only failure is
   master-receipt SHA staleness, re-record per DECISIONS "Receipt
   re-record protocol".
2. If the adapter subagent is idle: check its transcript tail before
   assuming it is working; resume it with a message rather than spawning a
   second writer (single-writer rule).
3. After the adapter folds in: Phase 9 individual vertical slice
   (DEEPSEEK_API_KEY is set -- live-model smoke leg is feasible via
   Concordia's OpenAI-compatible wrapper behind the model_builder seam),
   then Phase 10 team slice, Phase 11 monitored scale proofs
   (run_monitored is now MANDATORY for multi-suite engine batteries --
   single-suite iteration stays direct), operational-robustness matrix,
   final docs, Phase 12 frozen acceptance + remaining reviewer roles +
   final adjudication.

Suites at last verification: control plane 138/95/25 green; engine DoD 134
at a4112f6 (guard receipt, clean worktree); system suite 681 passed / 25
skipped + the known master-receipt staleness item. Upstream checkouts
verified clean at pins continuously. No background jobs. No open
critical/high findings.

## Continuation guarantee (2026-08-04, hook-maintenance #5)

Whenever you arm a liveness wakeup (send_later / trigger), ALSO run:
  python3 .claude/tools/arm_continuation.py --minutes N --reason "..." \
      --trigger-id trig_xxx --workers <names>
with the same deadline. The Stop hook now refuses idle turn-ends in
implementation/frozen_acceptance while acceptance is incomplete unless an
unexpired continuation is armed; SessionStart shows the window; the
validator check continuation_armed enforces it out-of-band. Re-arm on every
wake; acceptance PASS lifts the requirement.
