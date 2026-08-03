# SWORLDMODEL-GROUND-UP

Project instructions for Claude Code.

<!-- ===== BEGIN CONTROL PLANE (managed by .claude/hooks; edit only during a recorded hook_maintenance phase) ===== -->

## Execution control plane

Durable, changing state lives in `.agent-run/`. This section holds only the
static rules. Do not record status, blockers, or progress here.

1. **`.agent-run/GOAL.md` is the durable product objective.** It survives
   compaction and session restart. Do not rewrite it.
2. **Read the current run state before acting.** Every session reads
   `.agent-run/RUN_STATE.json` (mode, phase, next action, completion) before
   doing anything else. The `SessionStart` hook injects a summary; the file is
   authoritative.
3. **There is one highest-leverage blocker at a time.** It is recorded in
   `RUN_STATE.highest_leverage_blocker`. Work it before anything else.
4. **One primary writer owns each tightly coupled subsystem.** Two agents must
   never write the same subsystem concurrently. Ownership lives in
   `.agent-run/TASK_GRAPH.json`.
5. **Long-running commands must use `.claude/tools/run_monitored.py`.** Never
   launch a background, corpus, scale, load, or long test with `&`, `nohup`,
   `disown`, a detached session, or `run_in_background`. The `PreToolUse` hook
   blocks it.
6. **Frozen acceptance runs prohibit production, prompt, fixture, and evaluator
   changes.** While mode is `frozen_acceptance`, that material is immutable —
   evidence only means something if the thing measured did not change.
7. **Task completion requires current-SHA evidence receipts.** A task is
   complete when its declared artifacts exist and a passing receipt exists whose
   `git_sha` equals the SHA being completed at. A receipt against another SHA
   cannot satisfy completion. Record receipts with
   `.claude/tools/record_receipt.py`.
8. **Critical findings are work to resolve, not reasons to stop.** Finding a
   serious problem means the run continues; it does not license termination.
9. **Only `PASS` or a genuine `EXTERNAL_BLOCKER` permits the master run to
   terminate.** An external blocker requires the exact blocker, direct evidence,
   the alternatives attempted, and the exact human action required. A failing
   test, a scripting bug, invalid JSON, or a missing package is **not** an
   external blocker — fix it and continue.
10. **Do not modify the control plane during implementation.** `.claude/**` and
    this section are changed only inside an explicitly recorded
    `hook_maintenance` phase (see `.claude/HOOKS_README.md`).

### Before any production implementation

`RUN_STATE.json` mode must have validly transitioned to `implementation` through
the master-context initialization handshake. While
`master_context_loaded` is false: **the master directive is not loaded — do not
begin production implementation.** See `.claude/HOOKS_README.md`.

### Reference

- Hook behaviour and recovery: `.claude/HOOKS_README.md`
- Fresh-session verification: `.claude/FRESH_SESSION_VERIFICATION.md`
- Validate everything: `python3 .claude/tools/validate_control_plane.py`

<!-- ===== END CONTROL PLANE ===== -->
