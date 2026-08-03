# `.claude/hooks/`

One dispatcher, one shared library. There are deliberately **not** seven mostly
duplicated scripts.

| File | Role |
|---|---|
| `gate.py` | the single entry point for all eight configured hook events |
| `hook_state.py` | shared durable-state, atomic-IO, git, receipt and classification logic |

`.claude/settings.json` points every event at `gate.py`; the dispatcher selects
a handler from `hook_event_name`.

## Invariants

- **Standard library only.** A hook must never fail because a virtualenv was not
  active.
- **No network calls, ever.** Enforced by a test that greps both files.
- **Bounded work.** Git runs as a subprocess with a hard timeout; files are read
  with size caps.
- **Fail closed on safety and completion gates** (`PreToolUse`, `TaskCompleted`,
  `TeammateIdle`, `SubagentStop`, `Stop`, `ConfigChange`): an internal error
  becomes a block that carries the exact error. A bare crash would exit 1, which
  Claude Code treats as *non-blocking*, so `main()` catches everything and
  converts it into the correct blocking response for that event.
- **Fail safe on context-only events** (`SessionStart`, `StopFailure`): warn
  loudly, never wedge the session.
- **Never swallow malformed state.** `hook_state.StateError` carries the path and
  the parse error, and it always reaches the model.
- **Never emit `permissionDecision: "allow"`.** That would bypass the normal
  permission system. Allowing means producing no decision at all.

## Every rejection has three parts

```
BLOCKED: <the exact action>
GOVERNING STATE: <the durable state that forbids it>
SAFE ALTERNATIVE: <what to do instead>
```

A gate that blocks without telling the model how to proceed just causes thrash.

## Working on these files

They may only be edited while `RUN_STATE.mode` is `hook_bootstrap`,
`hook_live_verification`, or `hook_maintenance` — `PreToolUse` blocks it
otherwise. See `.claude/HOOKS_README.md` §6.

```bash
python3 -m pytest tests/control_plane/test_gate.py -q
python3 .claude/tools/validate_control_plane.py

# drive a single event by hand:
echo '{"hook_event_name":"SessionStart","source":"startup"}' \
  | CLAUDE_PROJECT_DIR=$PWD python3 .claude/hooks/gate.py
```

Full event contract and per-hook behaviour: `.claude/HOOKS_README.md`.
