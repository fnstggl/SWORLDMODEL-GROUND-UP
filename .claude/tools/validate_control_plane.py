#!/usr/bin/env python3
"""Validate the execution control plane.

Emits a machine-readable JSON result on **stdout** and a concise human-readable
summary on **stderr**, so both are available from one run::

    python3 .claude/tools/validate_control_plane.py            # human on stderr
    python3 .claude/tools/validate_control_plane.py > out.json # machine on stdout

Exit code is 0 when every check passes, 1 otherwise.

The validator distinguishes three valid initialization levels and applies a
different bar to each:

``hook_bootstrap``
    Bootstrap schemas and placeholders are valid; master implementation content
    is intentionally pending.
``ready_for_master``
    Static and live hook verification passed; bootstrap placeholders remain
    valid; production implementation is still blocked.
``implementation``
    The exact master directive exists and its recorded hash matches, every
    implementation state file is initialized, nothing is still marked
    ``MASTER_DIRECTIVE_PENDING``, and a valid master-context initialization
    receipt exists.

A placeholder that is valid during bootstrap therefore becomes a *failure* once
the mode is ``implementation``.
"""

from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import hook_state as hs  # noqa: E402

REQUIRED_HOOK_EVENTS = (
    "SessionStart",
    "PreToolUse",
    "TaskCompleted",
    "TeammateIdle",
    "SubagentStop",
    "Stop",
    "StopFailure",
    "ConfigChange",
)

#: Values of ``live_event_tests`` that may accompany ``overall: PASS``.
#:
#: ``PASS_WITH_DOCUMENTED_LIMITATION`` exists because a hook event can be
#: correctly implemented, correctly registered, statically covered, and still
#: never be emitted by the host on a given surface. That is a property of the
#: environment, not a defect in the control plane, and it must be recordable
#: without either lying (claiming PASS for an event that never fired) or
#: deadlocking the run forever on something no amount of local work can fix.
#: It is only accepted alongside an explicit, checked declaration -- see
#: ``check_bootstrap_status_consistent``.
LIVE_EVENT_TESTS_PASS_VALUES = ("PASS", "PASS_WITH_DOCUMENTED_LIMITATION")

#: Statuses a declared documented limitation may carry in ``live_checks``.
DOCUMENTED_LIMITATION_STATUSES = ("UNAVAILABLE_IN_CLAUDE_CODE_WEB",)

#: Fields every entry of ``documented_limitations`` must carry.
DOCUMENTED_LIMITATION_FIELDS = ("hook_event", "status", "reason", "fallback_controls")

REQUIRED_FILES = (
    "CLAUDE.md",
    ".claude/settings.json",
    ".claude/hooks/gate.py",
    ".claude/hooks/hook_state.py",
    ".claude/hooks/README.md",
    ".claude/tools/run_monitored.py",
    ".claude/tools/validate_control_plane.py",
    ".claude/tools/record_receipt.py",
    ".claude/tools/README.md",
    ".claude/HOOKS_README.md",
    ".claude/FRESH_SESSION_VERIFICATION.md",
    ".claude/agents/implementation-agent.md",
    ".claude/agents/investigation-agent.md",
    ".claude/agents/test-watchdog.md",
    ".claude/agents/adversarial-reviewer.md",
    ".claude/agents/final-adjudicator.md",
    ".agent-run/GOAL.md",
    ".agent-run/ARCHITECTURE.md",
    ".agent-run/RUN_STATE.json",
    ".agent-run/TASK_GRAPH.json",
    ".agent-run/CRITICAL_PATH.md",
    ".agent-run/DECISIONS.md",
    ".agent-run/BLOCKERS.md",
    ".agent-run/FAILURE_LEDGER.jsonl",
    ".agent-run/BACKGROUND_JOBS.json",
    ".agent-run/ACCEPTANCE_STATUS.json",
    ".agent-run/HOOK_BOOTSTRAP_STATUS.json",
    ".agent-run/HANDOFF.md",
    ".agent-run/UPSTREAM_PROTECTED_PATHS.json",
    ".agent-run/receipts/.gitkeep",
    "tests/control_plane/test_gate.py",
    "tests/control_plane/test_run_monitored.py",
    "tests/control_plane/test_validate_control_plane.py",
)

REQUIRED_JSON_FILES = (
    ".claude/settings.json",
    ".agent-run/RUN_STATE.json",
    ".agent-run/TASK_GRAPH.json",
    ".agent-run/ACCEPTANCE_STATUS.json",
    ".agent-run/HOOK_BOOTSTRAP_STATUS.json",
    ".agent-run/UPSTREAM_PROTECTED_PATHS.json",
    ".agent-run/BACKGROUND_JOBS.json",
)

PYTHON_SOURCES = (
    ".claude/hooks/gate.py",
    ".claude/hooks/hook_state.py",
    ".claude/tools/run_monitored.py",
    ".claude/tools/record_receipt.py",
    ".claude/tools/validate_control_plane.py",
    "tests/control_plane/test_gate.py",
    "tests/control_plane/test_run_monitored.py",
    "tests/control_plane/test_validate_control_plane.py",
)

AGENT_FILES = (
    ".claude/agents/implementation-agent.md",
    ".claude/agents/investigation-agent.md",
    ".claude/agents/test-watchdog.md",
    ".claude/agents/adversarial-reviewer.md",
    ".claude/agents/final-adjudicator.md",
)

HOOK_TEST_TASK = "control-plane-hook-tests"
RUNNER_TEST_TASK = "control-plane-monitored-runner-tests"

#: Path categories that must never appear in the audited diff, by run mode.
#: During hook bootstrap the branch may only add control-plane material.
#: Once the master-context handshake has passed (``implementation`` and the
#: modes that follow it), changing production, evaluator, fixture, and prompt
#: code is the point of the run and only pinned upstream source stays
#: inviolable. A ``frozen_acceptance`` batch is measured against the frozen
#: SHA instead of the branch base and freezes tests too (HOOKS_README §5).
BOOTSTRAP_FORBIDDEN_CATEGORIES = frozenset(
    {"production", "upstream_protected", "evaluator", "fixture", "prompt"}
)
IMPLEMENTATION_FORBIDDEN_CATEGORIES = frozenset({"upstream_protected"})
FROZEN_FORBIDDEN_CATEGORIES = frozenset(
    {"production", "upstream_protected", "evaluator", "fixture", "prompt", "test"}
)
#: Back-compat alias for the original bootstrap-era constant name.
FORBIDDEN_CHANGE_CATEGORIES = BOOTSTRAP_FORBIDDEN_CATEGORIES

_POST_HANDSHAKE_MODES = frozenset(
    {"implementation", "hook_maintenance", "complete", "external_blocker"}
)


def _forbidden_categories_for_mode(mode: str) -> frozenset:
    if mode in _POST_HANDSHAKE_MODES:
        return IMPLEMENTATION_FORBIDDEN_CATEGORIES
    if mode == "frozen_acceptance":
        return FROZEN_FORBIDDEN_CATEGORIES
    return BOOTSTRAP_FORBIDDEN_CATEGORIES


class Result:
    def __init__(self):
        self.checks: list[dict] = []

    def add(self, name: str, ok: bool, detail: str = "", severity: str = "error", **extra):
        entry = {"check": name, "ok": bool(ok), "detail": detail, "severity": severity}
        entry.update(extra)
        self.checks.append(entry)
        return ok

    def note(self, name: str, detail: str, **extra):
        return self.add(name, True, detail, severity="info", **extra)

    @property
    def failures(self):
        return [c for c in self.checks if not c["ok"] and c["severity"] == "error"]

    @property
    def warnings(self):
        return [c for c in self.checks if not c["ok"] and c["severity"] == "warning"]


# ---------------------------------------------------------------------------
# Minimal YAML frontmatter parser (no third-party dependency)
# ---------------------------------------------------------------------------


def parse_frontmatter(text: str):
    """Parse simple ``key: value`` YAML frontmatter. Returns ``(data, error)``."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, "file does not begin with a '---' frontmatter fence"
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return None, "frontmatter fence is never closed"
    data: dict[str, str] = {}
    for raw in lines[1:end]:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t", "-")):
            continue  # nested value; not needed by the fields we validate
        if ":" not in line:
            return None, f"frontmatter line is not 'key: value': {line!r}"
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip()
    if end + 1 >= len(lines) or not "\n".join(lines[end + 1 :]).strip():
        return None, "agent definition has an empty body"
    return data, None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_files(root: Path, result: Result):
    missing = [p for p in REQUIRED_FILES if not (root / p).exists()]
    result.add(
        "required_files_exist",
        not missing,
        "all present" if not missing else "missing: " + ", ".join(missing),
        missing=missing,
    )


def check_json_parses(root: Path, result: Result):
    bad = []
    for rel in REQUIRED_JSON_FILES:
        path = root / rel
        if not path.exists():
            bad.append(f"{rel} (missing)")
            continue
        raw = path.read_text(encoding="utf-8")
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            # A strict parse failure also covers every comment form: the json
            # module rejects // and /* */ outright, so a file that parses here
            # provably contains no comments. Scanning the raw text for those
            # character pairs is redundant and false-positives on URLs inside
            # legitimate string values (e.g. monitored-job commands).
            bad.append(f"{rel} (line {exc.lineno}: {exc.msg})")
    result.add("json_files_parse", not bad, "all parse as strict JSON" if not bad else "; ".join(bad))

    ledger = root / ".agent-run/FAILURE_LEDGER.jsonl"
    if ledger.exists():
        bad_lines = []
        for number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                bad_lines.append(f"line {number}: {exc.msg}")
        result.add(
            "failure_ledger_is_valid_jsonl",
            not bad_lines,
            "valid JSONL" if not bad_lines else "; ".join(bad_lines),
        )


def check_settings(root: Path, result: Result):
    path = root / ".claude/settings.json"
    if not path.exists():
        result.add("settings_hooks_configured", False, ".claude/settings.json is missing")
        return
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result.add("settings_hooks_configured", False, f"settings.json is not valid JSON: {exc.msg}")
        return

    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        result.add("settings_hooks_configured", False, "settings.json has no 'hooks' object")
        return

    missing_events = [e for e in REQUIRED_HOOK_EVENTS if e not in hooks]
    result.add(
        "settings_has_required_events",
        not missing_events,
        "all 8 events configured" if not missing_events else "missing events: " + ", ".join(missing_events),
        configured_events=sorted(hooks.keys()),
    )

    referenced: list[str] = []
    shape_problems: list[str] = []
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            shape_problems.append(f"{event}: expected a list of matcher groups")
            continue
        for group in entries:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                shape_problems.append(f"{event}: each entry needs a 'hooks' list")
                continue
            for hook in group["hooks"]:
                if not isinstance(hook, dict):
                    shape_problems.append(f"{event}: hook entry is not an object")
                    continue
                if hook.get("type") != "command":
                    shape_problems.append(f"{event}: unexpected hook type {hook.get('type')!r}")
                    continue
                command = hook.get("command", "")
                if "${CLAUDE_PROJECT_DIR}" not in command:
                    shape_problems.append(f"{event}: command does not use ${{CLAUDE_PROJECT_DIR}}")
                referenced.append(command)

    result.add("settings_hook_shape", not shape_problems,
               "all hooks are command hooks with ${CLAUDE_PROJECT_DIR}" if not shape_problems
               else "; ".join(shape_problems))

    # Match the placeholder wherever it appears, including inside quotes, so a
    # quoted path is still checked rather than silently skipped.
    import re

    missing_scripts = []
    found_any = False
    for command in referenced:
        for match in re.finditer(r"\$\{CLAUDE_PROJECT_DIR\}/([^\s'\"]+)", command):
            found_any = True
            rel = match.group(1)
            if not (root / rel).exists():
                missing_scripts.append(rel)
    ok = not missing_scripts and (found_any or not referenced)
    result.add(
        "settings_script_paths_exist",
        ok,
        "all referenced scripts exist" if ok
        else ("missing: " + ", ".join(sorted(set(missing_scripts))) if missing_scripts
              else "no ${CLAUDE_PROJECT_DIR}-relative script path could be extracted from the hook commands"),
    )

    env = settings.get("env") or {}
    result.add(
        "agent_teams_enabled",
        env.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS") == "1",
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 is set in settings.env",
        severity="warning",
    )
    if settings.get("disableAllHooks"):
        result.add("hooks_not_disabled", False, "settings.json sets disableAllHooks=true")
    else:
        result.note("hooks_not_disabled", "disableAllHooks is not set")


def check_python_compiles(root: Path, result: Result):
    failures = []
    with tempfile.TemporaryDirectory() as cache:
        for rel in PYTHON_SOURCES:
            path = root / rel
            if not path.exists():
                failures.append(f"{rel} (missing)")
                continue
            try:
                py_compile.compile(str(path), cfile=str(Path(cache) / (rel.replace("/", "_") + "c")),
                                   doraise=True)
            except py_compile.PyCompileError as exc:
                failures.append(f"{rel}: {exc.msg}")
    result.add("python_sources_compile", not failures,
               "all compile" if not failures else "; ".join(failures))


def check_agents(root: Path, result: Result):
    problems = []
    names = []
    for rel in AGENT_FILES:
        path = root / rel
        if not path.exists():
            problems.append(f"{rel} (missing)")
            continue
        data, error = parse_frontmatter(path.read_text(encoding="utf-8"))
        if error:
            problems.append(f"{rel}: {error}")
            continue
        for field in ("name", "description"):
            if not data.get(field):
                problems.append(f"{rel}: required frontmatter field '{field}' is missing")
        name = data.get("name", "")
        if ":" in name:
            problems.append(f"{rel}: name may not contain ':' (reserved for plugin scoping)")
        expected = Path(rel).stem
        if name and name != expected:
            problems.append(f"{rel}: name {name!r} does not match the SubagentStop matcher {expected!r}")
        names.append(name)
    result.add("agent_definitions_parse", not problems,
               "all agent definitions parse with required frontmatter" if not problems else "; ".join(problems),
               agent_names=names)


def _receipt_status(root: Path, task_id: str):
    head = hs.git_sha(root)
    receipts = [r for r in hs.load_receipts(task_id, root) if not r.get("_error")]
    if not receipts:
        return "NO_RECEIPT", None
    passing = [r for r in receipts if hs.receipt_is_passing(r)]
    if not passing:
        return "FAILED", receipts[-1]
    at_head = [r for r in passing if r.get("git_sha") == head]
    if at_head:
        return "PASS", at_head[-1]
    return "STALE", passing[-1]


def _test_command(target: str) -> list:
    """Prefer pytest, fall back to the suite's own ``unittest`` entry point.

    The control-plane suites are plain ``unittest`` and run correctly either
    way. A container without pytest installed must not read as a *failing* test
    run -- that reports a missing dependency as broken code, which is exactly
    the kind of false signal the evidence rules exist to prevent.
    """
    probe = subprocess.run([sys.executable, "-c", "import pytest"],
                           capture_output=True, check=False)
    if probe.returncode == 0:
        return [sys.executable, "-m", "pytest", target, "-q"]
    return [sys.executable, target]


def check_tests(root: Path, result: Result, run_tests: bool):
    if run_tests:
        for task_id, target in ((HOOK_TEST_TASK, "tests/control_plane/test_gate.py"),
                                (RUNNER_TEST_TASK, "tests/control_plane/test_run_monitored.py")):
            command = _test_command(target)
            try:
                proc = subprocess.run(command, cwd=str(root), capture_output=True, text=True,
                                      timeout=900, check=False)
                ok = proc.returncode == 0
                tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-1:] or [""]
                detail = f"{' '.join(command)} -> exit {proc.returncode}: {tail[0][:200]}"
            except (OSError, subprocess.SubprocessError) as exc:
                ok, detail = False, f"could not run {' '.join(command)}: {exc}"
            label = "hook_tests_passed" if task_id == HOOK_TEST_TASK else "monitored_runner_tests_passed"
            result.add(label, ok, detail, mode="executed")
        return

    for task_id, label in ((HOOK_TEST_TASK, "hook_tests_passed"),
                           (RUNNER_TEST_TASK, "monitored_runner_tests_passed")):
        status, receipt = _receipt_status(root, task_id)
        detail = {
            "PASS": "passing receipt at the current SHA",
            "STALE": "passing receipt exists but records an older SHA "
                     f"({str((receipt or {}).get('git_sha'))[:12]}); re-run with --run-tests to re-verify",
            "FAILED": "a receipt exists but it did not pass",
            "NO_RECEIPT": f"no receipt for task '{task_id}'; run with --run-tests or record one with "
                          ".claude/tools/record_receipt.py",
        }[status]
        result.add(label, status in {"PASS", "STALE"}, detail,
                   severity="error" if status in {"FAILED", "NO_RECEIPT"} else "info",
                   receipt_status=status, mode="receipt")


def check_no_production_changes(root: Path, result: Result, base: str | None):
    try:
        state = hs.read_run_state(root)
    except hs.StateError:
        state = {}
    mode = str(state.get("mode") or "")
    forbidden = _forbidden_categories_for_mode(mode)

    base_ref = base
    if base_ref is None and mode == "frozen_acceptance":
        frozen = state.get("frozen_sha")
        if not frozen:
            result.add(
                "no_production_files_changed",
                False,
                "mode is 'frozen_acceptance' but RUN_STATE.frozen_sha is not set; "
                "the frozen scope cannot be verified",
                mode=mode,
                forbidden_categories=sorted(forbidden),
            )
            return
        base_ref = str(frozen)
    if base_ref is None:
        base_ref = _default_base(root)
    if base_ref is None:
        result.add("no_production_files_changed", True,
                   "no comparable base ref found; skipped", severity="warning",
                   mode=mode, forbidden_categories=sorted(forbidden))
        return

    changed = set()
    diff = hs._git(root, "diff", "--name-only", f"{base_ref}...HEAD")
    if diff:
        changed.update(l for l in diff.splitlines() if l.strip())
    changed.update(hs.git_dirty_paths(root))

    offenders = []
    for path in sorted(changed):
        category = hs.classify_path(path, root)
        if category in forbidden:
            offenders.append(f"{path} ({category})")

    result.add(
        "no_production_files_changed",
        not offenders,
        f"mode={mode or 'unknown'}: compared against {base_ref}; "
        f"no {'/'.join(sorted(forbidden))} paths changed"
        if not offenders
        else f"mode={mode or 'unknown'}: these forbidden-category paths changed "
             f"(forbidden: {'/'.join(sorted(forbidden))}): " + ", ".join(offenders),
        base_ref=base_ref,
        mode=mode,
        forbidden_categories=sorted(forbidden),
        changed_paths=sorted(changed),
    )


def _default_base(root: Path):
    for ref in ("origin/main", "origin/master", "main", "master"):
        if hs._git(root, "rev-parse", "--verify", "--quiet", ref):
            merge_base = hs._git(root, "merge-base", "HEAD", ref)
            if merge_base:
                return merge_base
    return None


def check_claude_md_preserved(root: Path, result: Result, base: str | None):
    base_ref = base or _default_base(root)
    path = root / "CLAUDE.md"
    if base_ref is None:
        result.add("claude_md_preserved", True, "no base ref; skipped", severity="warning")
        return
    original = hs._git(root, "show", f"{base_ref}:CLAUDE.md")
    if original is None:
        result.note("claude_md_preserved",
                    "no CLAUDE.md existed at the base commit; this file is newly created")
        return
    if not path.exists():
        result.add("claude_md_preserved", False, "CLAUDE.md existed at the base commit but is now missing")
        return
    current = path.read_text(encoding="utf-8")
    missing = [l for l in original.splitlines() if l.strip() and l not in current]
    result.add("claude_md_preserved", not missing,
               "every preexisting CLAUDE.md line is still present"
               if not missing else f"{len(missing)} preexisting line(s) were removed, e.g. {missing[0][:120]!r}")


def check_git_context(root: Path, result: Result):
    branch = hs.git_branch(root)
    sha = hs.git_sha(root)
    status = hs.git_status_porcelain(root)
    result.note("git_context_recorded",
                f"branch={branch} sha={sha} dirty_paths={0 if not status else len(status.splitlines())}",
                branch=branch, git_sha=sha,
                dirty_paths=[] if not status else hs.git_dirty_paths(root))


def _documented_limitation_problems(status: dict, live) -> list:
    """Hold ``PASS_WITH_DOCUMENTED_LIMITATION`` to a declared, checkable shape.

    Every entry of ``live_checks`` must be ``PASS`` unless a limitation
    explicitly names it. A limitation must name a hook event this control plane
    still registers, carry a recognised status that *matches* that event's
    ``live_checks`` entry, give a reason, and list the controls covering the gap
    instead. Without those, the escape hatch would just be a way to wave through
    an unverified hook.
    """
    problems = []
    checks = status.get("live_checks")
    if checks is not None and not isinstance(checks, dict):
        return ["live_checks must be a JSON object"]
    declared = status.get("documented_limitations")

    if live != "PASS_WITH_DOCUMENTED_LIMITATION":
        if declared:
            problems.append(
                f"documented_limitations is declared but live_event_tests={live!r}; "
                "record PASS_WITH_DOCUMENTED_LIMITATION or remove the declaration"
            )
        for name, value in sorted((checks or {}).items()):
            if value != "PASS":
                problems.append(f"live_checks.{name}={value!r} but overall is PASS")
        return problems

    if not isinstance(declared, list) or not declared:
        return [
            "live_event_tests is PASS_WITH_DOCUMENTED_LIMITATION but "
            "documented_limitations is missing or empty"
        ]

    excused = set()
    for index, entry in enumerate(declared):
        where = f"documented_limitations[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where} must be a JSON object")
            continue
        for field in DOCUMENTED_LIMITATION_FIELDS:
            if not entry.get(field):
                problems.append(f"{where}.{field} is missing or empty")
        event = entry.get("hook_event")
        declared_status = entry.get("status")
        if event and event not in REQUIRED_HOOK_EVENTS:
            problems.append(f"{where}.hook_event={event!r} is not a control-plane hook event")
        if declared_status and declared_status not in DOCUMENTED_LIMITATION_STATUSES:
            problems.append(f"{where}.status={declared_status!r} is not a recognised limitation status")
        if entry.get("fallback_controls") is not None and not isinstance(
            entry.get("fallback_controls"), list
        ):
            problems.append(f"{where}.fallback_controls must be a list")
        if event and isinstance(checks, dict):
            if event not in checks:
                problems.append(f"{where}.hook_event={event!r} has no live_checks entry")
            elif checks[event] != declared_status:
                problems.append(
                    f"{where}.status={declared_status!r} does not match "
                    f"live_checks.{event}={checks[event]!r}"
                )
        if event:
            excused.add(event)

    for name, value in sorted((checks or {}).items()):
        if value != "PASS" and name not in excused:
            problems.append(
                f"live_checks.{name}={value!r} is not PASS and is not a documented limitation"
            )
    return problems


def check_bootstrap_status_consistent(root: Path, result: Result):
    try:
        status = hs.read_bootstrap_status(root)
    except hs.StateError as exc:
        result.add("bootstrap_status_consistent", False, str(exc))
        return
    overall = str(status.get("overall"))
    problems = []
    if overall == "STATIC_PASS_LIVE_PENDING":
        for field in ("static_tests", "settings_validation", "monitored_runner_tests"):
            if status.get(field) != "PASS":
                problems.append(f"{field}={status.get(field)!r} but overall is STATIC_PASS_LIVE_PENDING")
        for field in ("fresh_session_hooks_loaded", "live_event_tests"):
            if status.get(field) != "PENDING":
                problems.append(f"{field}={status.get(field)!r}; live verification must still be PENDING")
    elif overall == "PASS":
        for field in ("static_tests", "settings_validation", "monitored_runner_tests",
                      "fresh_session_hooks_loaded"):
            if status.get(field) != "PASS":
                problems.append(f"{field}={status.get(field)!r} but overall is PASS")
        live = status.get("live_event_tests")
        if live not in LIVE_EVENT_TESTS_PASS_VALUES:
            problems.append(f"live_event_tests={live!r} but overall is PASS")
        if not status.get("verified_commit"):
            problems.append("overall is PASS but verified_commit is not recorded")
        problems.extend(_documented_limitation_problems(status, live))
    elif overall not in {"IN_PROGRESS", "EXTERNAL_BLOCKER", "FAIL"}:
        problems.append(f"unrecognised overall value {overall!r}")
    result.add("bootstrap_status_consistent", not problems,
               f"overall={overall} is internally consistent" if not problems else "; ".join(problems))


def check_initialization_level(root: Path, result: Result):
    """Apply the bar appropriate to the current mode.

    Bootstrap placeholders are valid in ``hook_bootstrap`` and
    ``ready_for_master`` and become failures in ``implementation``.
    """
    try:
        state = hs.read_run_state(root)
    except hs.StateError as exc:
        result.add("run_state_valid", False, str(exc))
        return
    result.note("run_state_valid", f"mode={state.get('mode')} status={state.get('status')} "
                                   f"phase={state.get('phase')}")

    mode = state.get("mode")
    problems = hs.master_context_problems(root, state)

    if mode in {"hook_bootstrap", "hook_live_verification"}:
        pending_ok = all(
            not state.get(f) for f in ("master_context_loaded", "architecture_initialized",
                                       "task_graph_initialized", "acceptance_gates_initialized")
        ) and state.get("master_directive_path") is None and state.get("master_directive_sha256") is None
        result.add("initialization_level", pending_ok,
                   "level=hook_bootstrap: placeholders are valid and master-context fields are correctly pending"
                   if pending_ok
                   else "master-context fields must all remain false/null during hook bootstrap",
                   level="hook_bootstrap")
        graph = hs.read_json(root / ".agent-run/TASK_GRAPH.json", default={}) or {}
        leftover = [t.get("id") for t in graph.get("tasks", [])
                    if not t.get("bootstrap_only")]
        result.add("no_speculative_tasks", not leftover,
                   "task graph holds no speculative implementation tasks" if not leftover
                   else "non-bootstrap tasks present during bootstrap: " + ", ".join(map(str, leftover)))

    elif mode == "ready_for_master":
        result.add("initialization_level", True,
                   "level=ready_for_master: placeholders remain valid; production implementation stays blocked"
                   + (f" ({len(problems)} master-context precondition(s) still unmet, as expected)" if problems else ""),
                   level="ready_for_master", outstanding_master_context=problems)

    elif mode in {"implementation", "frozen_acceptance"}:
        result.add("initialization_level", not problems,
                   "level=implementation: master context is fully initialized" if not problems
                   else "mode is '%s' but the master-context handshake is incomplete: %s"
                        % (mode, "; ".join(problems)),
                   level="implementation", outstanding_master_context=problems)

    else:
        result.note("initialization_level", f"mode={mode}: no initialization-level bar applies", level=mode)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(root: Path, run_tests: bool, base: str | None) -> Result:
    result = Result()
    check_files(root, result)
    check_json_parses(root, result)
    check_settings(root, result)
    check_python_compiles(root, result)
    check_agents(root, result)
    check_tests(root, result, run_tests)
    check_no_production_changes(root, result, base)
    check_claude_md_preserved(root, result, base)
    check_git_context(root, result)
    check_bootstrap_status_consistent(root, result)
    check_initialization_level(root, result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate the SWORLDMODEL control plane.")
    parser.add_argument("--run-tests", action="store_true",
                        help="execute the control-plane test suites instead of trusting receipts")
    parser.add_argument("--base", default=None, help="git ref to diff against for the change audit")
    parser.add_argument("--project-dir", default=None)
    args = parser.parse_args(argv)

    root = Path(args.project_dir).resolve() if args.project_dir else hs.project_dir()
    result = run(root, args.run_tests, args.base)

    ok = not result.failures
    payload = {
        "schema_version": hs.SCHEMA_VERSION,
        "tool": "validate_control_plane",
        "project_dir": str(root),
        "generated_at": hs.utc_now_iso(),
        "overall": "PASS" if ok else "FAIL",
        "failure_count": len(result.failures),
        "warning_count": len(result.warnings),
        "checks": result.checks,
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")

    lines = [f"control plane: {'PASS' if ok else 'FAIL'} ({root})"]
    for check in result.checks:
        if check["ok"] and check["severity"] == "info":
            mark = "  ."
        elif check["ok"]:
            mark = "  +"
        elif check["severity"] == "warning":
            mark = "  ~"
        else:
            mark = "  X"
        lines.append(f"{mark} {check['check']}: {check['detail']}")
    if not ok:
        lines.append(f"  {len(result.failures)} failing check(s) must be fixed.")
    sys.stderr.write("\n".join(lines) + "\n")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
