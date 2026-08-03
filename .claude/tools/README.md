# `.claude/tools/`

Operator-facing tools. Standard library only; no `jq`, no network, no daemon.

| Tool | Purpose |
|---|---|
| `run_monitored.py` | the only supported way to run a long or detached job |
| `record_receipt.py` | write an atomic, SHA-bound evidence receipt |
| `validate_control_plane.py` | verify the whole control plane is coherent |

## `run_monitored.py`

```bash
python3 .claude/tools/run_monitored.py \
  --job-id nightly-corpus --classification exploratory \
  --no-progress-timeout 600 --total-timeout 7200 --heartbeat-interval 15 \
  --progress-file .agent-run/jobs/nightly-corpus/progress.json \
  -- python3 run_worlds.py --corpus all
```

Owns the child's process group, watches for *meaningful* progress rather than
liveness, classifies how a job is unhealthy, captures diagnostics before killing
anything, terminates the entire group (SIGTERM → bounded grace → SIGKILL), and
always leaves a structured record at `.agent-run/jobs/<job-id>/job.json`.

Exit codes: `0` success · child's own code on failure · `124` hard timeout ·
`125` no-progress timeout · `130` interrupted · `2` usage / duplicate job id /
refused stale registration.

Have the child write completed-unit counts to `--progress-file` — a JSON object
with `completed_units` (or `completed` / `units_done` / `progress` / `done`), or
one line per completed unit. Log growth alone is a weaker fallback signal.

Hang classification and job inspection: `.claude/HOOKS_README.md` §7.

## `record_receipt.py`

Prefer `--run`, so the exit code and timestamps are observed rather than
asserted:

```bash
python3 .claude/tools/record_receipt.py --task-id my-task --run -- \
  python3 -m pytest tests/control_plane -q
```

Recording an already-finished run:

```bash
python3 .claude/tools/record_receipt.py --task-id my-task \
  --command 'python3 -m pytest tests/control_plane -q' --exit-code 0 \
  --artifact artifacts/report.json --config-hash settings=.claude/settings.json
```

Exits nonzero when the recorded run failed, so a caller cannot mistake a
recorded failure for success. A declared-but-missing artifact marks the receipt
`valid: false`. **A receipt only counts at the SHA it was produced at.**

## `validate_control_plane.py`

```bash
python3 .claude/tools/validate_control_plane.py               # human -> stderr
python3 .claude/tools/validate_control_plane.py > result.json # machine -> stdout
python3 .claude/tools/validate_control_plane.py --run-tests   # execute the suites
```

Checks required files, JSON validity, the eight hook events and their script
paths, Python compilation, agent frontmatter, test status, that no production
file changed, that `CLAUDE.md` kept its preexisting content, git context, and
that the bootstrap status is internally consistent.

It also enforces the three initialization levels — `hook_bootstrap`,
`ready_for_master`, `implementation` — so a placeholder that is valid during
bootstrap becomes a failure once the mode is `implementation`.

Exit code 0 = PASS, 1 = FAIL. Without `--run-tests` it trusts receipts and marks
a receipt from an older SHA as `STALE` (informational); with `--run-tests` it
runs the suites itself and that result is authoritative.
