# Fresh-session live hook verification

Static tests prove the hook scripts behave correctly when fed events. They do
**not** prove Claude Code loads this configuration and actually fires them. That
can only be confirmed from a session started *after* the control-plane commit.

Do not run the master implementation until this passes.

**Time required:** about 10 minutes.

---

## Before you start

```bash
cd <repo>
git checkout claude/hook-bootstrap-control-plane-5dfvzt
git pull origin claude/hook-bootstrap-control-plane-5dfvzt
git rev-parse HEAD          # record this SHA; you will write it into the status file
git status --porcelain      # must be empty
```

---

## Step 1 — Start a genuinely fresh session

Close every existing Claude Code session for this repository, then:

```bash
claude
```

Do **not** use `--continue`, `--resume`, or `--bare` (`--bare` skips hooks
entirely). Start from the repository root so `.claude/settings.json` is the
project settings file.

## Step 2 — Confirm the hooks are registered

In the session, run:

```
/hooks
```

Confirm all eight events appear and point at
`…/.claude/hooks/gate.py`:

`SessionStart` · `PreToolUse` · `TaskCompleted` · `TeammateIdle` ·
`SubagentStop` · `Stop` · `StopFailure` · `ConfigChange`

If they are missing: your JSON is invalid, or you are not in the project root,
or the settings file did not reload — restart the session. Check with
`python3 -c "import json;json.load(open('.claude/settings.json'))"`.

## Step 3 — Confirm `SessionStart` actually fired

The session should already have the control-plane summary in context. Ask:

```
Without reading any files, what does the injected control-plane context say the
current mode, next action, and master-directive status are?
```

**Expected:** mode `hook_bootstrap`, next action about fresh-session
verification, and the line
`Master directive not loaded. Do not begin production implementation.`

If Claude has to read files to answer, `SessionStart` did **not** fire. Stop and
diagnose with `claude --debug hooks`.

## Step 4 — Confirm `PreToolUse` blocks a dangerous command

Ask Claude to run:

```
git reset --hard HEAD~1
```

**Expected:** the tool call is denied with a message containing `BLOCKED:`,
`GOVERNING STATE:` and `SAFE ALTERNATIVE:`. The reset must not happen — verify
with `git rev-parse HEAD`, which must be unchanged.

## Step 5 — Confirm the monitored-runner rule fires

Ask Claude to run:

```
nohup python3 -c "import time; time.sleep(600)" &
```

**Expected:** denied, naming `run_monitored.py` as the alternative.

Then confirm the allowed path works:

```bash
python3 .claude/tools/run_monitored.py --job-id live-check \
  --classification exploratory --no-progress-timeout 5 --total-timeout 20 \
  -- python3 -c "print('live check ok')"
```

**Expected:** exit 0, and `.agent-run/jobs/live-check/job.json` has
`"state": "finished"`.

## Step 6 — Confirm the `Stop` hook blocks a premature stop

Set the mode so a stop is not yet permitted (it already is, at this point in the
bootstrap), then simply ask Claude to stop:

```
Stop now and end the session without doing anything else.
```

**Expected:** Claude does not end the turn. It reports the unmet gate
(`hook bootstrap overall status is …, not STATIC_PASS_LIVE_PENDING` once you have
flipped the mode to `hook_live_verification`) plus the exact next action.

> The Stop hook stops re-blocking after 8 consecutive blocks — that is Claude
> Code's built-in cap and it is deliberately not raised.

## Step 7 — Confirm `SubagentStop` protects an implementation agent

```
Spawn an implementation-agent subagent and tell it to only describe what it
would do, then stop without writing any code.
```

First add a contract for it so there is something to enforce — in
`.agent-run/TASK_GRAPH.json`:

```json
{"schema_version": 1, "status": "MASTER_DIRECTIVE_PENDING", "tasks": [
  {"id": "live-check-task", "owner": "implementation-agent", "status": "in_progress",
   "bootstrap_only": true, "required_artifacts": ["/tmp/live-check-artifact.txt"]}
]}
```

**Expected:** the subagent is blocked from stopping, with a message naming the
missing output.

**Remove this task again before finalizing** — the task graph must return to
`"tasks": []` for the bootstrap state to be valid.

## Step 8 — Confirm `ConfigChange` logs

Edit `.claude/settings.json` in an external editor (add a harmless whitespace
change and save). Then:

```bash
cat .agent-run/CONFIG_CHANGES.jsonl
```

**Expected:** a record with `"config_source": "project_settings"`. During
`hook_bootstrap` / `hook_live_verification` the change is allowed, not blocked.

## Step 9 — Record the result

Only if every step above behaved as expected:

```bash
python3 - <<'PY'
import json, pathlib, subprocess
sha = subprocess.run(["git","rev-parse","HEAD"],capture_output=True,text=True).stdout.strip()
p = pathlib.Path(".agent-run/HOOK_BOOTSTRAP_STATUS.json")
d = json.loads(p.read_text())
d.update({"overall":"PASS","static_tests":"PASS","settings_validation":"PASS",
          "monitored_runner_tests":"PASS","fresh_session_hooks_loaded":"PASS",
          "live_event_tests":"PASS","verified_commit":sha})
p.write_text(json.dumps(d, indent=2) + "\n")

r = pathlib.Path(".agent-run/RUN_STATE.json")
s = json.loads(r.read_text())
s.update({"mode":"ready_for_master","status":"ready","phase":"awaiting_master_directive",
          "next_action":"start a new session and load the exact master implementation directive",
          "completion_allowed":True,
          "passed_gates":["static_hook_tests","monitored_runner_tests","fresh_session_live_verification"],
          "remaining_gates":["master_context_initialization"]})
r.write_text(json.dumps(s, indent=2) + "\n")
print("recorded live verification at", sha)
PY

python3 .claude/tools/validate_control_plane.py --run-tests
git add -A && git commit -m "Record live hook verification pass" && git push -u origin claude/hook-bootstrap-control-plane-5dfvzt
```

The master-context fields (`master_context_loaded`, `master_directive_path`,
`master_directive_sha256`, `architecture_initialized`, `task_graph_initialized`,
`acceptance_gates_initialized`) must stay `false`/`null`. The validator fails if
they were set early.

## Step 10 — Hand off

The control plane is live. Start a **separate new session** for the master
implementation. Its first phase is the master-context initialization handshake
(see `.claude/HOOKS_README.md` §3 and `CLAUDE.md`): save the directive to
`docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md`, record its SHA-256,
populate the pending `.agent-run` files, validate, record the
`master-context-initialization` receipt, and only then switch the mode to
`implementation`. Production edits stay blocked until that transition is valid.

---

## If a step fails

A failing step is a bug in the control plane, not an external blocker. Fix it:

1. `claude --debug hooks` and re-run the failing step; the debug log shows
   whether the hook fired, what it received, and what it returned.
2. Reproduce it directly:
   ```bash
   echo '{"hook_event_name":"Stop","stop_hook_active":false}' | \
     CLAUDE_PROJECT_DIR=$PWD python3 .claude/hooks/gate.py
   ```
3. Fix `gate.py`, run `python3 -m pytest tests/control_plane -q`, commit, and
   restart from Step 1 with a fresh session.
