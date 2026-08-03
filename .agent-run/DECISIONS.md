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

**Outcome.** `tests/control_plane` went from 194 to 211 tests (112 to 141
subtests), all passing under `PYTHONHASHSEED` 0/1/7/42/12345/99991.
`validate_control_plane.py --run-tests` returns PASS. All three reproduction
probes are clean: 0 false positives, 0 missed detections, 0 bypasses. Mode
restored to `hook_live_verification`, and live verification was restarted from
the beginning against the post-fix commit -- no evidence from the pre-fix
configuration was counted.
