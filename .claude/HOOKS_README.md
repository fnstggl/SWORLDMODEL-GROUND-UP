# SWORLDMODEL execution control plane

This directory holds the deterministic guardrails around long-running,
multi-session, multi-agent implementation work. The point is that certain things
*always* happen, rather than depending on a model choosing to do them.

Everything is Python 3 standard library. No `jq`, no network, no external
service, no supervisor daemon.

---

## 1. Verified hook contract

Verified against **Claude Code 2.1.220** using the official
[hooks reference](https://code.claude.com/docs/en/hooks) and
[hooks guide](https://code.claude.com/docs/en/hooks-guide). Re-verify after a
Claude Code upgrade before trusting this table.

| Event | Matcher support | Matches on | Blocking mechanism used here |
|---|---|---|---|
| `SessionStart` | yes | `startup`, `resume`, `clear`, `compact`, `fork` | none — injects `hookSpecificOutput.additionalContext` |
| `PreToolUse` | yes | tool name | `hookSpecificOutput.permissionDecision = "deny"` + `permissionDecisionReason` |
| `TaskCompleted` | **no** | — | **exit code 2**, reason on stderr |
| `TeammateIdle` | **no** | — | **exit code 2**, reason on stderr — ⚠️ **never emitted on this surface**, see §1.1 |
| `SubagentStop` | yes | agent type (the `name:` in `.claude/agents/*.md`) | `{"decision": "block", "reason": ...}` |
| `Stop` | **no** | — | `{"decision": "block", "reason": ...}` |
| `StopFailure` | yes | error type | **cannot block** — output and exit code are ignored |
| `ConfigChange` | yes | `user_settings`, `project_settings`, `local_settings`, `policy_settings`, `skills` | `{"decision": "block", "reason": ...}` |

Additional verified facts this design depends on:

- **Exit codes.** `0` = success, stdout parsed as JSON. `2` = blocking error,
  stdout ignored, stderr fed back to Claude. Anything else = *non-blocking*
  error. Exit 1 does **not** block — that is why the gate never relies on it.
- **`stop_hook_active`.** Present on `Stop` and `SubagentStop`. It is `true`
  when the hook already triggered a continuation. Claude Code overrides a Stop
  hook after **8** consecutive blocks. `gate.py` returns immediately when the
  flag is set, so it can never spin. The cap is deliberately **not** raised.
- **`${CLAUDE_PROJECT_DIR}`** expands to the project root inside `command`
  strings and is also exported into the hook process environment. `gate.py`
  resolves the project root from that variable, which is what lets the tests
  point it at synthetic project trees.
- **Command hook shape.** `settings.json` → `hooks` → `<Event>` → list of
  `{matcher?, hooks: [{type: "command", command, timeout?, statusMessage?}]}`.
- **Agent teams** need `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, set in
  `.claude/settings.json` → `env`. Supported from v2.1.178; this project runs
  2.1.220. `TaskCompleted` is live-verified here. `TeammateIdle` is **not** —
  see §1.1. The `team_name` field in those payloads is deprecated and is not
  used here.

---

## 1.1 Known limitation — `TeammateIdle` is not emitted here

**Status: `UNAVAILABLE_IN_CLAUDE_CODE_WEB`.** Do not rely on this event.

The table above describes the mechanism `gate.py` *implements*. It does not
promise the host will call it. On this surface — Claude Code on the web /
remote execution (`CLAUDE_CODE_ENTRYPOINT=remote`), version 2.1.220, agent teams
enabled — the host **never emits `TeammateIdle`** for Agent-tool teammates.

Measured twice, most recently at commit `190b04e` against the host's own debug
log (`/tmp/claude-code.log`, `CLAUDE_CODE_DEBUG=true`), which names every hook
Claude Code invokes. A named teammate owning an `in_progress` task with a
missing `required_artifacts` entry — exactly what `handle_teammate_idle` exists
to block — went idle unimpeded. Zero `TeammateIdle` invocations appeared. The
detector was validated in the same window by a positive control: the teammate's
denied `Write` into `.claude/` *was* recorded, so the log does capture hooks
fired in a teammate's context. Every hook invocation in the window reconciles
against a known tool call, so the event did not fire silently either. Full
evidence: `.agent-run/LIVE_VERIFICATION.md` check 4.

The 2.1.220 binary does contain the event name, so this is a missing *emission
path* on this surface, not a missing feature. The registration in
`settings.json` is deliberately kept and the handler is fully covered by the
static suite, so the gate takes effect unchanged wherever the event is emitted.

**What actually prevents silent abandonment here.** Four controls, all
live-verified at `190b04e`:

1. **`TaskCompleted`** — a task cannot be marked complete without its declared
   artifacts and a passing current-SHA receipt. Abandonment dressed up as
   completion is stopped here.
2. **`SubagentStop`** — `implementation-agent` and `test-watchdog` cannot stop
   on an incomplete contract. This covers the protected writer roles.
3. **`Stop`** — the lead cannot end the run with unmet gates, so an abandoned
   task cannot leave the run quietly.
4. **Explicit ownership + lead review** — every task names its owner in
   `TASK_GRAPH.json` before work starts, and the lead reviews each teammate
   return. Unfinished work is visible in durable state whether or not a hook
   fired.

**Residual gap, stated plainly:** an *unprotected* teammate type that abandons
work without claiming completion is caught by ownership and lead review, not by
a hook. Prefer `implementation-agent` or `test-watchdog` for work that must not
be silently dropped — those are the types `SubagentStop` protects.

---

## 2. What each hook does

### `SessionStart` — orientation
Reads `GOAL.md`, `RUN_STATE.json`, `CRITICAL_PATH.md`, `BLOCKERS.md`,
`BACKGROUND_JOBS.json` and the git branch/SHA/cleanliness, then injects a
summary under 4 KB: durable goal, mode/phase/status, highest-leverage blocker,
exact next action, open critical/high counts, active background jobs, whether
completion is allowed, and whether the master directive is loaded. It never
dumps whole files or logs. It **never blocks** and fails safe with a loud
warning if state is unreadable.

### `PreToolUse` — the safety gate
Denies, with the blocked action, the governing state, and the exact safe
alternative:

1. production or prompt edits while mode is `frozen_acceptance`
2. evaluator or fixture edits while mode is `frozen_acceptance`
3. deletion or overwriting of control-plane / acceptance artifacts
4. `git reset --hard` (and `--merge` / `--keep`)
5. destructive `git clean`
6. force pushes (`-f`, `--force`, `--force-with-lease`, `+refspec`)
7. destructive `git checkout -- …`, `git restore`, `git stash drop/clear`,
   `git branch -D`, `git update-ref -d`
8. edits to paths listed in `UPSTREAM_PROTECTED_PATHS.json`
9. edits to hook-control files outside `hook_bootstrap`,
   `hook_live_verification`, `hook_maintenance`
10. background / corpus / scale / load / long-running work outside
    `run_monitored.py`
11. production implementation edits while mode is `ready_for_master` and the
    master-context handshake has not passed

Backgrounding is detected structurally — trailing `&`, `nohup`, `disown`,
`setsid`, detached `screen`/`tmux`, `at`/`batch`, and Claude Code's own
`run_in_background: true` — not by matching specific commands. A detached
command is still allowed when every segment is demonstrably short and harmless
(read-only git, `ls`, `echo`, short `sleep`, …).

### `TaskCompleted` — the evidence gate
Reads the task id, finds it in `TASK_GRAPH.json`, and verifies required
artifacts exist, required receipts exist and passed, **receipt SHA equals the
current task SHA**, blocking critical findings are empty, required review
artifacts exist, and the worktree is clean when the contract demands it. It
validates already-produced receipts; it never runs the expensive suite itself.

An unknown task blocks during `implementation`/`frozen_acceptance` and is
allowed with an explicit `systemMessage` otherwise. Override per-graph with
`"unknown_task_policy": "allow" | "block"`.

### `TeammateIdle` — no silent abandonment ⚠️ NOT ENFORCED ON THIS SURFACE
**This event is never emitted in Claude Code web / remote execution (§1.1), so
the behaviour below is implemented and statically covered but not live.** Treat
it as dormant, not as a guarantee. Silent abandonment is covered here by
`TaskCompleted`, `SubagentStop`, `Stop`, and explicit ownership plus lead
review.

When the event *is* emitted, the handler blocks a teammate from idling only when
it owns an incomplete in-progress task, owes a required artifact, owes a test
receipt, was assigned implementation but produced no artifact, or has unresolved
critical findings. It **allows** idling when owned tasks are complete, when a
read-only reviewer has delivered its report, and when the teammate owns nothing.
No teammate is trapped indefinitely.

### `SubagentStop` — protected implementation contracts
Applies only to `implementation-agent` and `test-watchdog`.
`investigation-agent`, `adversarial-reviewer` and `final-adjudicator` always
return their findings normally — returning a critical finding is their job.
Honours `stop_hook_active`.

### `Stop` — final deterministic guardrail
Not the main looping mechanism; `/goal` is. Logic by mode:

| Mode | May stop when |
|---|---|
| `hook_bootstrap` | bootstrap `overall` is `STATIC_PASS_LIVE_PENDING` or `PASS`, or a genuine external blocker is recorded |
| `hook_live_verification` | bootstrap `overall` is `PASS`, or external blocker |
| `ready_for_master` | always |
| `implementation`, `frozen_acceptance` | `ACCEPTANCE_STATUS.overall == "PASS"` **and** no acceptance job is still running, or `RUN_STATE.status == "EXTERNAL_BLOCKER"` |
| `hook_maintenance`, `complete`, `external_blocker` | always |

A printed completion phrase is never authority. When blocking it reports the
highest-leverage unmet gate, the current blocker, the exact next action, and the
instruction to continue.

### `StopFailure` — logging only
Appends a record to `.agent-run/FAILURE_LEDGER.jsonl` and writes
`.agent-run/RECOVERY_REQUEST.json` with failure type, details, session id,
phase, branch, SHA, highest-leverage blocker, next action, and timestamp.

**What it cannot do:** it cannot continue, retry, or restart the failed session.
Claude Code ignores its output and exit code. Recovery needs a human or an
external supervisor — and no such supervisor is installed by this bootstrap.
Every record carries `"simulation_result": "not_applicable"` so a provider
failure is never mistaken for a simulation outcome.

### `ConfigChange` — protect the control plane
Logs every change to `.agent-run/CONFIG_CHANGES.jsonl`. Blocks
project/local settings changes during `implementation` and `frozen_acceptance`
unless hook maintenance is recorded. Managed **policy** changes are logged only
— the platform does not let a project hook veto them.

---

## 3. Authoritative files

| File | Authority over |
|---|---|
| `.agent-run/GOAL.md` | the durable product objective |
| `.agent-run/RUN_STATE.json` | mode, phase, status, next action, blockers, master-context flags |
| `.agent-run/TASK_GRAPH.json` | task contracts, ownership, required evidence |
| `.agent-run/ACCEPTANCE_STATUS.json` | acceptance gates and the final verdict |
| `.agent-run/HOOK_BOOTSTRAP_STATUS.json` | static vs live hook verification |
| `.agent-run/UPSTREAM_PROTECTED_PATHS.json` | pinned upstream paths |
| `.agent-run/BACKGROUND_JOBS.json` | active and completed monitored jobs |
| `.agent-run/receipts/*.json` | proof that a validation actually ran |
| `.agent-run/FAILURE_LEDGER.jsonl` | provider/API turn failures |
| `CLAUDE.md` (control-plane section) | the static rules |

Static rules live in `CLAUDE.md`. Changing state lives in `.agent-run/`. Do not
mix them.

Supported modes: `hook_bootstrap`, `hook_live_verification`, `ready_for_master`,
`implementation`, `frozen_acceptance`, `hook_maintenance`, `external_blocker`,
`complete`.

---

## 4. Receipts

A receipt is the only accepted evidence that a validation ran:

```json
{
  "schema_version": 1, "task_id": "...", "git_sha": "...", "worktree": "...",
  "command": "...", "exit_code": 0, "started_at": "...", "finished_at": "...",
  "artifact_paths": [], "configuration_hashes": {}, "valid": true
}
```

Record one — preferably by running the command through the tool, so the exit
code is observed rather than asserted:

```bash
python3 .claude/tools/record_receipt.py --task-id my-task --run -- python3 -m pytest tests/control_plane -q
```

Receipts are written to a temp file and `os.replace`d into place, so a reader
never sees a partial receipt. **A receipt whose `git_sha` differs from the SHA a
task is completed at cannot satisfy that task.** Re-record after committing or
rebasing.

---

## 5. Frozen acceptance

Set `RUN_STATE.mode` to `frozen_acceptance` and `frozen_sha` to the exact SHA
being measured. While frozen, `PreToolUse` blocks every production, prompt,
evaluator, fixture, and test edit. Run acceptance jobs with
`--classification frozen_acceptance`; the job record then carries the exact SHA
and a `frozen_integrity` field that flags a dirty worktree. `Stop` refuses to
end the run while any acceptance job is still active.

To exit the freeze, set the mode back to `implementation` and record why in
`.agent-run/DECISIONS.md`.

---

## 6. Entering and leaving `hook_maintenance`

The control plane must not be edited during implementation. To change it:

1. Record the reason in `.agent-run/DECISIONS.md`.
2. Set `RUN_STATE.json` `"mode": "hook_maintenance"` (keep the previous mode in
   `"phase"` so you can restore it). Alternatively keep the mode and set
   `"hook_maintenance": true` — `ConfigChange` honours both.
3. Make the change.
4. Run `python3 .claude/tools/validate_control_plane.py --run-tests`.
5. Restore the previous mode. Record the outcome in `DECISIONS.md`.

---

## 7. Monitored jobs

```bash
python3 .claude/tools/run_monitored.py \
  --job-id nightly-corpus \
  --classification exploratory \
  --no-progress-timeout 600 \
  --total-timeout 7200 \
  --heartbeat-interval 15 \
  --progress-file .agent-run/jobs/nightly-corpus/progress.json \
  -- python3 run_worlds.py --corpus all
```

Exit codes: `0` child succeeded · child's own code on failure · `124` hard
timeout · `125` no-progress timeout · `130` wrapper interrupted · `2` usage
error, duplicate job id, or refused stale registration.

### How hangs are classified

A live PID is **not** evidence of health. Progress is observed, strongest first:
an explicit progress file counter, completed-unit records, then log growth as a
weaker fallback. Combined with process-group CPU time from `/proc`, each tick is
classified as:

| State | Meaning |
|---|---|
| `progressing` | a progress signal advanced recently |
| `alive_but_slow` | some activity, but progress has stalled past half the budget |
| `probable_cpu_spin` | burning ≥ 0.5 cores with no progress — a busy loop |
| `blocked_no_activity` | ~no CPU and no output — deadlock, or waiting on I/O that never comes |
| `process_dead` | no live group members though the wrapper still holds the child |
| `no_progress_timeout` | terminal: exceeded `--no-progress-timeout` |
| `hard_timeout` | terminal: exceeded `--total-timeout` |
| `child_failure` | terminal: child exited nonzero |
| `finished` / `interrupted` | terminal |

Every distinct state the job passed through is kept in `observed_states` /
`observed_state_names` on the final record, so a CPU spin stays distinguishable
from an idle block *after the fact*.

Before terminating anything, the wrapper writes `diagnostics.txt` (process-group
listing, `ps -g`, per-process `/proc` status and `wchan`, log tails). It then
`SIGTERM`s the whole **process group**, waits a bounded grace period, and
escalates to `SIGKILL`, confirming every descendant is gone — not just the
direct child. Partial logs are always preserved.

### Inspecting jobs

```bash
python3 -c "import json;d=json.load(open('.agent-run/BACKGROUND_JOBS.json'));print([ (j['job_id'],j['state']) for j in d['active_jobs']])"
cat .agent-run/jobs/<job-id>/job.json
tail -50 .agent-run/jobs/<job-id>/stdout.log
cat .agent-run/jobs/<job-id>/diagnostics.txt
```

`BACKGROUND_JOBS.json` is updated atomically under a lock file, so a concurrent
reader never sees a torn file. A job whose wrapper was killed leaves a **stale**
active registration; re-running that job id diagnoses it and refuses to start
until you pass `--reclaim-stale`.

---

## 8. Why `/goal`, and why not Ralph

`/goal` is the primary continuation mechanism for the lead session: it keeps a
durable objective in front of the model across many turns. The `Stop` hook is a
deterministic *guardrail*, not a loop driver — it exists to catch a premature
stop, and Claude Code overrides it after 8 consecutive blocks anyway.

Ralph (an external restart supervisor) is not installed and is not required:
`/goal` plus the Stop gate plus durable `.agent-run` state already give
multi-turn continuation and crash-resumable context. **No external supervisor
exists in this repository.** If the API kills a session, nothing here restarts
it; `StopFailure` only records what happened.

---

## 9. Emergency: disabling the hooks

Do this only when the control plane itself is broken. Never weaken durable state
to slip past a gate.

```bash
# one session, nothing written to the repo:
claude --settings '{"disableAllHooks": true}'

# or bypass all project settings for one session:
claude --setting-sources user
```

Then fix `.claude/hooks/gate.py`, run
`python3 -m pytest tests/control_plane -q`, and restart normally.

Do **not** commit `"disableAllHooks": true` — the validator fails on it.

---

## 10. Recovering from malformed durable state

Symptom: every gate blocks and the message names a state file.

1. `python3 .claude/tools/validate_control_plane.py` — the human summary on
   stderr names the offending file and the parse error.
2. `git diff .agent-run/` and `git checkout -- .agent-run/<file>` to restore the
   last committed version.
3. If it was never valid, rebuild the minimum: `RUN_STATE.json` needs
   `schema_version`, `mode` (a supported value), `status`, `phase`,
   `next_action`, `completion_allowed`, plus the six master-context fields.
4. Re-run the validator, then `python3 -m pytest tests/control_plane -q`.

`SessionStart` and `StopFailure` fail *safe* — they warn but never wedge the
session — so you can always start a session and read the warning. Every other
gate fails *closed*.

---

## 11. Fresh-session verification

Static tests prove the scripts behave. They do **not** prove Claude Code
actually loads and fires them. That requires a new session started after the
commit — see `.claude/FRESH_SESSION_VERIFICATION.md`.

## 10. Continuation guarantee (worker_silent_death)

A worker that dies mid-turn without a clean stop emits no event; nothing
wakes the lead. Correction (2026-08-04): while acceptance is incomplete and
mode is `implementation` or `frozen_acceptance`, the `Stop` hook refuses to
let a turn end unless `.agent-run/CONTINUATION.json` holds an unexpired
`armed_until`. Arm it with the sanctioned tool immediately after scheduling
the real wakeup, with the same deadline:

```bash
python3 .claude/tools/arm_continuation.py --minutes 45 \
    --reason "watching spoof-fix worker" --trigger-id trig_xxx --workers spoof-fix
```

`SessionStart` surfaces the armed window (`CONTINUATION: armed until ...`)
or the gap (`CONTINUATION: NOT ARMED`); the validator check
`continuation_armed` fails whenever the requirement is unmet. The record is
informational state, not a scheduler — arming without scheduling the
matching wakeup bounds nothing. Acceptance `PASS` lifts the requirement.
