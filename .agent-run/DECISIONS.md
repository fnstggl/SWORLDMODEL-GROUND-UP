# Decisions
## Bootstrap decisions
- Use project-scoped Claude Code hooks.
- Use `/goal` as the primary lead-session continuation mechanism.
- Do not install Ralph for this workflow.
- Store changing execution state under `.agent-run/`.
- Require monitored execution for long-running jobs.
- Do not initialize detailed product architecture before the master directive is loaded.

## Hook maintenance 2026-08-03 -- shell write-target detection must be shell-aware

Entered `hook_maintenance` from `hook_live_verification` (previous mode kept in
`phase`) because live verification exposed a defect in `PreToolUse`.

**Defect.** `gate._shell_written_paths` decided which paths a `Bash` command
writes to by running regexes over the raw command text. Text matching cannot
tell a shell operator from the same characters appearing inside a quoted string
or a heredoc body, and it does not model each tool's argument grammar. Both
error directions were reproduced:

- *False positives* (observed live, twice, within minutes of starting live
  verification): `echo "VAR=${FOO:-<unset>}"` was denied as a write to `}`, and
  a `grep`/heredoc mentioning `sed -i s/a/b/` was denied as a write to `s/a/b`.
  Ordinary read-only commands were blocked.
- *False negatives* (reproduced against a synthetic project in
  `implementation` mode): `sed -i` captured the sed *script* instead of the
  file operand, so the capture fell through to the `production` category, which
  is allowed outside a freeze. `sed -i 's/deny/allow/' .claude/hooks/gate.py`,
  `sed -i 's/a/b/' .claude/settings.json` and an in-place edit of a pinned
  upstream path were all **allowed** -- defeating the hook-control and
  upstream-protection rules that `CLAUDE.md` rule 10 depends on.

**Smallest general cause.** Write-target detection was text matching rather than
shell-aware parsing. One cause, both symptoms.

**Fix.** `hook_state.shell_write_targets` now strips heredoc bodies (stdin data,
not shell syntax) and reuses the module's existing quoting-aware tokenizer, then
reads redirection operators as tokens and extracts real file operands for the
in-place writers (`tee`, `sed -i`, `truncate`), skipping options, option
arguments and the sed script. `gate._shell_written_paths` delegates to it. No
gate was weakened: the change removes false allows as well as false denials.

**Regression coverage.** `tests/control_plane/test_gate.py` gained direct
`shell_write_targets` unit tests plus end-to-end cases for the quoted-mention
false positives, the in-place-edit bypasses, quoted redirect targets, read-only
`sed`, and file-descriptor duplication.

### Outcome of the write-target fix

`tests/control_plane` went from 194 to 211 tests (112 to 141
subtests), all passing under `PYTHONHASHSEED` 0/1/7/42/12345/99991.
`validate_control_plane.py --run-tests` returns PASS. All three reproduction
probes are clean: 0 false positives, 0 missed detections, 0 bypasses. Mode
restored to `hook_live_verification`, and live verification was restarted from
the beginning against the post-fix commit -- no evidence from the pre-fix
configuration was counted.

## Hook maintenance 2026-08-03 -- ConfigChange read a payload field that does not exist

Entered `hook_maintenance` from `hook_live_verification` a second time.

**Defect.** `handle_config_change` resolved the changed-settings source with
`first_present(event, "config_source", "configSource")`. Live payloads captured
in this session name that field **`source`**, so every real change resolved to
`"unknown"`. An unknown source is never in `BLOCKING_CONFIG_SOURCES`, so the
handler fell through to `allow()`: **the ConfigChange gate could not block
anything in live operation.** Two real project-settings edits were logged with
`"config_source": "unknown"` and no `config_changes` key at all.

The static suite passed throughout because its `config_event()` helper built
the synthetic `config_source` spelling -- a shape live payloads never send.
This is exactly the class of defect fresh-session live verification exists to
catch, and it is invisible to static testing by construction.

**Observed live payload:** `session_id`, `transcript_path`, `cwd`, `prompt_id`,
`hook_event_name`, `source`, `file_path`.

**Smallest general cause.** A safety gate identified its subject from an assumed
payload field name and treated "field absent" as "nothing to block" -- failing
*open* on a gate the hooks README declares fail-closed.

**Fix.** Two parts, because the field name alone would leave the same trap set
for the next rename:
1. `handle_config_change` reads `source` first, keeping `config_source` /
   `configSource` as alternates, and now also logs the changed file path.
2. An *unidentifiable* source during `implementation` / `frozen_acceptance`
   (outside recorded hook maintenance) now **blocks**, naming the payload fields
   that were actually present, instead of silently allowing. Outside those
   protected modes it still allows, so nothing is trapped.

**Regression coverage.** `tests/control_plane/test_gate.py` gained a
`live_config_event()` helper built from the captured real payload, and the whole
block/allow matrix is re-run against that shape, plus fail-closed tests for an
unrecognised source and a test that the logged record names the payload fields
when the source cannot be identified.

**Method note.** The payload was captured by temporarily registering a
throwaway diagnostic hook that recorded the raw event JSON, then removing it.
The validator's `settings_hook_shape` check correctly failed while that
temporary hook was registered, because its command used an absolute path rather
than `${CLAUDE_PROJECT_DIR}`. `.claude/settings.json` was restored byte for
byte afterwards (sha256
`ad585f6ae64c10d131664d5818611ed10b6aed0bcbe7df723acf0992ba620582`).

### Outcome of the ConfigChange fix

Static suite green; the deterministic gate matrix runs the whole ConfigChange
block/allow table against BOTH payload shapes. Mode restored to
`hook_live_verification` and live verification restarted from the beginning
against the post-fix commit.

## Finding 2026-08-03 -- TeammateIdle is never emitted in this environment

Not a defect in the hook, and not fixed by changing code: recorded because it
materially limits what the control plane actually guarantees here.

The same diagnostic technique was pointed at `TeammateIdle`. Across three
genuine idles by a named teammate that owned an in-progress task with a missing
required artifact, **zero `TeammateIdle` invocations were observed**. Two
independent detectors agree: the throwaway dumper captured nothing (while
provably writing, verified by a self-test), and the real gate -- registered on
the same event -- never blocked the teammate.

The registration is correct, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set and
reaches the process environment, and the running Claude Code is 2.1.220, exactly
the version `.claude/HOOKS_README.md` claims the contract was verified against.
The README's assertion that `TeammateIdle` is live in this configuration is
therefore **unverified in this remote, non-interactive environment**.

Consequence: the "no silent abandonment" guarantee is not in force for
Agent-tool subagents here. `TeammateIdle`'s handler logic is fully covered by
the harness and by the static suite, but nothing was observed to invoke it.
Clearing this needs an interactive agent-teams session; see
`.agent-run/RUN_STATE.json` `external_blocker`.
