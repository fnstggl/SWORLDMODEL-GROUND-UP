#!/usr/bin/env python3
"""Single hook dispatcher for the SWORLDMODEL execution control plane.

Claude Code invokes this one script for every configured hook event. The event
JSON arrives on stdin; ``hook_event_name`` selects the handler.

Response contracts implemented here (verified against the Claude Code 2.1.220
hooks reference -- see ``.claude/HOOKS_README.md``):

===============  ===========================================================
Event            Blocking mechanism
===============  ===========================================================
SessionStart     exit 0 + ``hookSpecificOutput.additionalContext`` (no block)
PreToolUse       exit 0 + ``hookSpecificOutput.permissionDecision = "deny"``
TaskCompleted    exit 2 + reason on stderr
TeammateIdle     exit 2 + reason on stderr
SubagentStop     exit 0 + ``{"decision": "block", "reason": ...}``
Stop             exit 0 + ``{"decision": "block", "reason": ...}``
StopFailure      logging only; output and exit code are ignored by the host
ConfigChange     exit 0 + ``{"decision": "block", "reason": ...}``
===============  ===========================================================

Design rules:

* No network access, ever.
* Bounded work only: git calls have hard timeouts, files are read with caps.
* Completion and safety gates **fail closed**: an internal error becomes a
  block carrying the exact error, never a silent allow.
* Context-only events (SessionStart, StopFailure) **fail safe**: they warn
  loudly but never wedge the session.
* Malformed durable state is always surfaced verbatim, never swallowed.
* ``permissionDecision: "allow"`` is never emitted -- that would bypass the
  normal permission system. Allowing simply means producing no decision.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hook_state as hs  # noqa: E402

MAX_CONTEXT_CHARS = 4000

#: Custom agent types whose contract must be complete before they may stop.
PROTECTED_AGENT_TYPES = frozenset({"implementation-agent", "test-watchdog"})

#: Read-only roles that must always be able to return their findings.
READ_ONLY_AGENT_TYPES = frozenset(
    {"investigation-agent", "adversarial-reviewer", "final-adjudicator"}
)

REVIEWER_OWNER_TYPES = frozenset({"reviewer", "read_only", "adjudicator", "investigator"})

BLOCKING_CONFIG_SOURCES = frozenset({"project_settings", "local_settings"})

EMERGENCY_NOTE = (
    "If the control plane itself is wrong, disable hooks for one session with "
    "`claude --settings '{\"disableAllHooks\": true}'` and fix "
    "`.claude/hooks/gate.py`; do not weaken the durable state to get past a gate."
)


# ---------------------------------------------------------------------------
# Response emitters
# ---------------------------------------------------------------------------


def emit(payload: dict, code: int = 0):
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    return code


def allow() -> int:
    """Allow without overriding the normal permission flow."""
    return 0


def deny_tool(reason: str) -> int:
    return emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def block_decision(event_name: str, reason: str) -> int:
    return emit({"decision": "block", "reason": reason})


def block_exit2(reason: str) -> int:
    sys.stderr.write(reason)
    sys.stderr.flush()
    return 2


def rejection(action: str, governing: str, alternative: str) -> str:
    """Every rejection names the action, the governing state, and the way forward."""
    return (
        f"BLOCKED: {action}\n"
        f"GOVERNING STATE: {governing}\n"
        f"SAFE ALTERNATIVE: {alternative}"
    )


# ---------------------------------------------------------------------------
# Shared state loading
# ---------------------------------------------------------------------------


def external_blocker_recorded(state: dict) -> bool:
    return (
        str(state.get("status", "")).strip().upper() == "EXTERNAL_BLOCKER"
        or state.get("mode") == "external_blocker"
    )


def in_hook_maintenance(state: dict) -> bool:
    return state.get("mode") == "hook_maintenance" or state.get("hook_maintenance") is True


def active_jobs(root: Path) -> list:
    try:
        return hs.read_background_jobs(root).get("active_jobs", [])
    except hs.StateError:
        return []


# ---------------------------------------------------------------------------
# SessionStart
# ---------------------------------------------------------------------------


def _goal_line(root: Path) -> str:
    text = hs.read_text(hs.agent_run_dir(root) / "GOAL.md", default="")
    body: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if body:
                break
            continue
        if stripped.startswith("---"):
            break
        body.append(stripped)
    return " ".join(body) if body else "(GOAL.md is missing or empty)"


def _critical_path_lines(root: Path, limit: int = 8) -> list[str]:
    text = hs.read_text(hs.agent_run_dir(root) / "CRITICAL_PATH.md", default="")
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    return lines[:limit]


def _blocker_lines(root: Path, limit: int = 5) -> list[str]:
    text = hs.read_text(hs.agent_run_dir(root) / "BLOCKERS.md", default="")
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    return lines[:limit]


def handle_session_start(event: dict, root: Path) -> int:
    """Inject a compact, durable orientation summary. Never blocks."""
    warnings: list[str] = []
    lines: list[str] = []

    lines.append("== SWORLDMODEL CONTROL PLANE ==")
    lines.append(f"DURABLE GOAL: {_goal_line(root)}")

    try:
        state = hs.read_run_state(root)
    except hs.StateError as exc:
        state = {}
        warnings.append(
            f"CRITICAL: durable run state is unusable -- {exc}. "
            "Repair .agent-run/RUN_STATE.json before doing any work. "
            "Every safety gate is failing closed until it parses."
        )

    if state:
        lines.append(
            "MODE: {mode} | PHASE: {phase} | STATUS: {status}".format(
                mode=state.get("mode"), phase=state.get("phase"), status=state.get("status")
            )
        )
        lines.append(f"HIGHEST-LEVERAGE BLOCKER: {state.get('highest_leverage_blocker') or 'none recorded'}")
        lines.append(f"NEXT ACTION: {state.get('next_action') or '(not recorded)'}")
        lines.append(
            "OPEN FINDINGS: critical={} high={}".format(
                state.get("open_critical_count", "?"), state.get("open_high_count", "?")
            )
        )
        remaining = state.get("remaining_gates") or []
        if remaining:
            lines.append("REMAINING GATES: " + ", ".join(str(g) for g in remaining[:8]))
        lines.append(f"COMPLETION ALLOWED: {bool(state.get('completion_allowed'))}")
        if hs.master_context_pending(state):
            lines.append(
                "MASTER CONTEXT: Master directive not loaded. Do not begin production implementation."
            )
        else:
            lines.append(f"MASTER CONTEXT: loaded from {state.get('master_directive_path')}")

    try:
        bootstrap = hs.read_bootstrap_status(root)
        lines.append(
            "HOOK BOOTSTRAP: overall={} static={} live={}".format(
                bootstrap.get("overall"),
                bootstrap.get("static_tests"),
                bootstrap.get("live_event_tests"),
            )
        )
    except hs.StateError as exc:
        warnings.append(f"WARNING: HOOK_BOOTSTRAP_STATUS.json unusable -- {exc}")

    running = active_jobs(root)
    if running:
        described = ", ".join(
            f"{j.get('job_id')}({j.get('classification', '?')}/{j.get('state', '?')})" for j in running[:6]
        )
        lines.append(f"ACTIVE BACKGROUND JOBS: {len(running)} -- {described}")
    else:
        lines.append("ACTIVE BACKGROUND JOBS: none")

    if state and state.get("mode") in {"implementation", "frozen_acceptance"}:
        word, detail = hs.continuation_status(root)
        if word == "armed":
            lines.append(f"CONTINUATION: armed {detail}")
        elif word == "malformed":
            warnings.append(f"WARNING: CONTINUATION.json unusable -- {detail}")
            lines.append(
                "CONTINUATION: MALFORMED -- repair and re-arm with .claude/tools/arm_continuation.py"
            )
        else:
            lines.append(
                "CONTINUATION: NOT ARMED -- bound every idle wait: schedule a wakeup and "
                "record it with .claude/tools/arm_continuation.py"
            )

    branch = hs.git_branch(root)
    sha = hs.git_sha(root)
    clean = hs.git_is_clean(root)
    clean_text = {True: "clean", False: "DIRTY", None: "unknown"}[clean]
    lines.append(f"GIT: branch={branch or '?'} sha={(sha or '?')[:12]} worktree={clean_text}")

    blockers = _blocker_lines(root)
    if blockers:
        lines.append("BLOCKERS: " + " | ".join(blockers))

    critical_path = _critical_path_lines(root)
    if critical_path:
        lines.append("CRITICAL PATH:")
        lines.extend(f"  {line}" for line in critical_path)

    lines.append(
        "RULES: read .agent-run/RUN_STATE.json before acting; long jobs go through "
        ".claude/tools/run_monitored.py; completion needs current-SHA receipts; "
        "only PASS or a genuine EXTERNAL_BLOCKER ends the run."
    )

    if warnings:
        lines.append("")
        lines.extend(warnings)

    context = "\n".join(lines)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n... [control-plane summary truncated]"

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    if warnings:
        payload["systemMessage"] = warnings[0]
    return emit(payload)


# ---------------------------------------------------------------------------
# PreToolUse
# ---------------------------------------------------------------------------

EDIT_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "MultiEdit", "ApplyPatch"})
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})


def _edited_paths(tool_input: dict) -> list[str]:
    paths: list[str] = []
    for key in ("file_path", "notebook_path", "path", "filePath"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            paths.append(value)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict):
                for key in ("file_path", "path"):
                    value = edit.get(key)
                    if isinstance(value, str) and value:
                        paths.append(value)
    return paths


def _shell_written_paths(command: str, root: Path) -> list[str]:
    """Paths a shell command writes to: redirection and in-place edit targets.

    Delegates to the shell-aware parser in ``hook_state`` so that a ``>`` or a
    ``sed -i`` appearing inside a quoted string or a heredoc body is treated as
    the data it is, and a real target is still recovered when it is quoted or
    sits behind option arguments.
    """
    return hs.shell_write_targets(command)


def _mode_blocks_category(state: dict, category: str) -> str | None:
    """Return the reason ``category`` may not be modified in the current mode."""
    mode = state.get("mode")

    if category == "control_plane":
        if mode not in hs.HOOK_EDIT_MODES:
            return (
                f"mode is '{mode}'; hook-control files may only be modified in "
                + ", ".join(sorted(hs.HOOK_EDIT_MODES))
            )
        return None

    if category == "upstream_protected":
        return "the path is registered in .agent-run/UPSTREAM_PROTECTED_PATHS.json as pinned upstream source"

    if category in {"agent_run", "test", "doc"}:
        if mode == "frozen_acceptance" and category == "test":
            return "mode is 'frozen_acceptance'; test/evaluator material is frozen for the acceptance run"
        return None

    if category in {"evaluator", "fixture", "prompt"}:
        if mode == "frozen_acceptance":
            return f"mode is 'frozen_acceptance'; {category} material is frozen for the acceptance run"
        if mode == "ready_for_master":
            return "mode is 'ready_for_master'; only the master directive and .agent-run initialization may change"
        return None

    if category == "production":
        if mode == "frozen_acceptance":
            return "mode is 'frozen_acceptance'; production and prompt code is frozen for the acceptance run"
        if mode == "ready_for_master":
            return (
                "mode is 'ready_for_master' and the master-context initialization handshake has not passed; "
                "production implementation is blocked until RUN_STATE.mode validly becomes 'implementation'"
            )
        if mode in {"hook_bootstrap", "hook_live_verification"}:
            return f"mode is '{mode}'; this session builds and verifies the control plane only"
        return None

    return None


def _alternative_for(category: str, state: dict) -> str:
    mode = state.get("mode")
    if category == "control_plane":
        return (
            "Record a hook-maintenance phase first: set RUN_STATE.json mode to 'hook_maintenance' "
            "(with the reason in DECISIONS.md), make the change, re-run "
            "`python3 .claude/tools/validate_control_plane.py`, then restore the previous mode."
        )
    if category == "upstream_protected":
        return (
            "Do not edit pinned upstream source in place. Add an adapter or overlay in project-owned "
            "code, or record an explicit exception in .agent-run/UPSTREAM_PROTECTED_PATHS.json with a "
            "decision entry in .agent-run/DECISIONS.md."
        )
    if mode == "frozen_acceptance":
        return (
            "The acceptance run is frozen at RUN_STATE.frozen_sha. Finish or abandon the frozen run "
            "(set mode back to 'implementation' and record why in .agent-run/DECISIONS.md) before "
            "changing production, prompt, evaluator, or fixture material."
        )
    if mode == "ready_for_master":
        return (
            "Complete the master-context initialization handshake first: write "
            f"{hs.MASTER_DIRECTIVE_PATH}, record its sha256 in RUN_STATE.json, populate "
            "ARCHITECTURE.md / TASK_GRAPH.json / CRITICAL_PATH.md / UPSTREAM_PROTECTED_PATHS.json / "
            "ACCEPTANCE_STATUS.json, run `python3 .claude/tools/validate_control_plane.py`, record the "
            f"'{hs.MASTER_INIT_TASK_ID}' receipt, then set mode to 'implementation'."
        )
    return (
        "Finish the current control-plane phase before touching production code. "
        "See .agent-run/RUN_STATE.json next_action."
    )


def handle_pre_tool_use(event: dict, root: Path) -> int:
    tool_name = str(hs.first_present(event, "tool_name", default="") or "")
    tool_input = hs.first_present(event, "tool_input", default={}) or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    try:
        state = hs.read_run_state(root)
    except hs.StateError as exc:
        return deny_tool(
            rejection(
                f"{tool_name or 'tool'} call",
                f"durable run state is unusable -- {exc}",
                "Repair .agent-run/RUN_STATE.json so it is valid JSON with a supported 'mode', then retry. "
                + EMERGENCY_NOTE,
            )
        )

    mode = state.get("mode")
    governing = f"RUN_STATE.json mode='{mode}' phase='{state.get('phase')}'"

    candidate_paths: list[str] = []
    if tool_name in EDIT_TOOLS:
        candidate_paths = _edited_paths(tool_input)

    command = ""
    if tool_name in SHELL_TOOLS:
        command = str(tool_input.get("command") or "")

        git_reason = hs.destructive_git_reason(command)
        if git_reason:
            return deny_tool(
                rejection(
                    f"{git_reason} (`{command.strip()[:200]}`)",
                    governing + "; the control plane forbids commands that discard committed or working state",
                    "Use a non-destructive equivalent: `git stash push` to set work aside, "
                    "`git revert` to undo a commit, `git checkout -b` to move to a new branch, or "
                    "`git push --force-with-lease` only after a human explicitly authorises it.",
                )
            )

        fs_reason = hs.destructive_filesystem_reason(command, root, state)
        if fs_reason:
            return deny_tool(
                rejection(
                    f"{fs_reason} (`{command.strip()[:200]}`)",
                    governing + "; control-plane and acceptance artifacts are evidence and must not be deleted",
                    "Leave the artifact in place. If it is genuinely obsolete, move it under "
                    ".agent-run/archive/ and record the reason in .agent-run/DECISIONS.md.",
                )
            )

        monitored_reason = hs.requires_monitored_runner(command, tool_input)
        if monitored_reason:
            return deny_tool(
                rejection(
                    f"launching an unmonitored long-running or detached job because {monitored_reason} "
                    f"(`{command.strip()[:200]}`)",
                    governing + "; every long-running job must be observable and bounded",
                    "Run it through the monitored runner, for example:\n"
                    "  python3 .claude/tools/run_monitored.py --job-id <unique-id> "
                    "--classification exploratory --no-progress-timeout 300 --total-timeout 3600 "
                    "-- <your command>\n"
                    "Then inspect .agent-run/BACKGROUND_JOBS.json for its state.",
                )
            )

        candidate_paths.extend(_shell_written_paths(command, root))

    for raw_path in candidate_paths:
        category = hs.classify_path(raw_path, root)
        reason = _mode_blocks_category(state, category)
        if reason:
            rel = hs.normalize_repo_path(raw_path, root)
            return deny_tool(
                rejection(
                    f"modifying {category.replace('_', ' ')} path `{rel}` with {tool_name}",
                    f"{governing}; {reason}",
                    _alternative_for(category, state),
                )
            )

    return allow()


# ---------------------------------------------------------------------------
# TaskCompleted
# ---------------------------------------------------------------------------


def _task_sha(task: dict, root: Path) -> str | None:
    worktree = task.get("worktree")
    if worktree:
        candidate = Path(worktree)
        if not candidate.is_absolute():
            candidate = root / worktree
        if candidate.is_dir():
            return hs.git_sha(candidate)
    return hs.git_sha(root)


def handle_task_completed(event: dict, root: Path) -> int:
    task_id = hs.first_present(event, "task_id", "taskId", "task.id", default=None)
    task_title = hs.first_present(event, "task_title", "taskTitle", "task.title", default="")

    try:
        state = hs.read_run_state(root)
        graph = hs.read_task_graph(root)
    except hs.StateError as exc:
        return block_exit2(
            rejection(
                f"completing task {task_id or task_title or '(unidentified)'}",
                f"durable state is unusable -- {exc}",
                "Repair the offending state file, then retry the completion. " + EMERGENCY_NOTE,
            )
        )

    if not task_id and not task_title:
        return block_exit2(
            rejection(
                "completing a task with no identifier in the hook payload",
                "the TaskCompleted event carried neither task_id nor task_title",
                "Re-issue the completion through the task tools so the task carries an id that exists "
                "in .agent-run/TASK_GRAPH.json.",
            )
        )

    task = hs.find_task(graph, task_id) if task_id else None
    if task is None:
        task = hs.find_task_by_subject(graph, str(task_title))

    if task is None:
        policy = graph.get("unknown_task_policy")
        if policy not in {"allow", "block"}:
            policy = "block" if state.get("mode") in {"implementation", "frozen_acceptance"} else "allow"
        if policy == "block":
            return block_exit2(
                rejection(
                    f"completing task '{task_id or task_title}' which is not in the task graph",
                    f"TASK_GRAPH.json (status={graph.get('status')}) is authoritative in mode "
                    f"'{state.get('mode')}' and contains no such task",
                    "Add the task to .agent-run/TASK_GRAPH.json with its required artifacts, receipts and "
                    "validation commands before marking it complete, or complete the task that does exist.",
                )
            )
        return emit(
            {
                "systemMessage": (
                    f"control-plane note: task '{task_id or task_title}' is not in TASK_GRAPH.json "
                    f"(status={graph.get('status')}). Allowed because unknown_task_policy resolves to "
                    f"'allow' in mode '{state.get('mode')}'. No evidence was verified for it."
                )
            }
        )

    failures: list[str] = []
    current_sha = _task_sha(task, root)

    for artifact in task.get("required_artifacts") or []:
        path = Path(artifact)
        if not path.is_absolute():
            path = root / artifact
        if not path.exists():
            failures.append(f"required artifact is missing: {artifact}")

    for artifact in task.get("required_review_artifacts") or []:
        path = Path(artifact)
        if not path.is_absolute():
            path = root / artifact
        if not path.exists():
            failures.append(f"required review artifact is missing: {artifact}")

    receipts = hs.load_receipts(task.get("id"), root)
    for broken in [r for r in receipts if r.get("_error")]:
        failures.append(f"receipt {broken.get('_path')} is malformed: {broken.get('_error')}")

    selectors = task.get("required_receipts") or []
    for selector in selectors:
        if isinstance(selector, str):
            selector = {"task_id": task.get("id"), "command": selector}
        if not isinstance(selector, dict):
            failures.append(f"malformed required_receipts entry: {selector!r}")
            continue
        want_command = selector.get("command")
        must_pass = selector.get("must_pass", True)
        matches = [
            r
            for r in receipts
            if not r.get("_error") and (want_command is None or r.get("command") == want_command)
        ]
        if not matches:
            failures.append(
                "no receipt found for command {}".format(
                    repr(want_command) if want_command else "(any)"
                )
            )
            continue
        at_sha = [r for r in matches if r.get("git_sha") == current_sha]
        if not at_sha:
            seen = sorted({str(r.get("git_sha"))[:12] for r in matches})
            failures.append(
                "receipt for {} is stale: it records SHA(s) {} but the task SHA is {}".format(
                    repr(want_command) if want_command else "(any command)",
                    ", ".join(seen) or "none",
                    (current_sha or "unknown")[:12],
                )
            )
            continue
        if must_pass and not any(hs.receipt_is_passing(r) for r in at_sha):
            detail = "; ".join(
                "exit_code={} valid={}".format(r.get("exit_code"), r.get("valid")) for r in at_sha[:3]
            )
            failures.append(
                "receipt for {} exists at the current SHA but did not pass ({})".format(
                    repr(want_command) if want_command else "(any command)", detail
                )
            )

    for command in task.get("required_validation_commands") or []:
        passing = [
            r
            for r in receipts
            if not r.get("_error")
            and r.get("command") == command
            and r.get("git_sha") == current_sha
            and hs.receipt_is_passing(r)
        ]
        if not passing:
            failures.append(
                f"no passing receipt at SHA {(current_sha or 'unknown')[:12]} for required validation "
                f"command: {command}"
            )

    blocking = task.get("blocking_critical_findings") or []
    if blocking:
        failures.append(
            "blocking critical findings are unresolved: " + ", ".join(str(f) for f in blocking)
        )

    if task.get("requires_clean_worktree"):
        worktree_root = root
        if task.get("worktree"):
            candidate = Path(task["worktree"])
            worktree_root = candidate if candidate.is_absolute() else root / task["worktree"]
        clean = hs.git_is_clean(worktree_root)
        if clean is False:
            dirty = hs.git_dirty_paths(worktree_root)[:8]
            failures.append(
                "task contract requires a clean worktree but these paths are modified: "
                + ", ".join(dirty)
            )
        elif clean is None:
            failures.append(f"task contract requires a clean worktree but git status failed in {worktree_root}")

    if failures:
        numbered = "\n".join(f"  {i}. {f}" for i, f in enumerate(failures, 1))
        return block_exit2(
            rejection(
                f"marking task '{task.get('id')}' complete with {len(failures)} unmet requirement(s):\n{numbered}",
                f"TASK_GRAPH.json contract for '{task.get('id')}' at SHA {(current_sha or 'unknown')[:12]}; "
                f"RUN_STATE mode='{state.get('mode')}'",
                "Produce the missing evidence, then retry. Record receipts with:\n"
                f"  python3 .claude/tools/record_receipt.py --task-id {task.get('id')} "
                "--command '<exact command>' --exit-code 0 --artifact <path>\n"
                "A receipt only counts when its git_sha equals the SHA the task is being completed at.",
            )
        )

    return allow()


# ---------------------------------------------------------------------------
# TeammateIdle
# ---------------------------------------------------------------------------


def _artifact_missing(paths, root: Path) -> list[str]:
    missing = []
    for artifact in paths or []:
        path = Path(artifact)
        if not path.is_absolute():
            path = root / artifact
        if not path.exists():
            missing.append(str(artifact))
    return missing


def handle_teammate_idle(event: dict, root: Path) -> int:
    teammate = str(
        hs.first_present(event, "teammate_name", "teammateName", "agent_name", default="") or ""
    )

    try:
        state = hs.read_run_state(root)
        graph = hs.read_task_graph(root)
    except hs.StateError as exc:
        return block_exit2(
            rejection(
                f"teammate '{teammate or 'unknown'}' going idle",
                f"durable state is unusable -- {exc}",
                "Repair the offending state file so the control plane can evaluate outstanding work. "
                + EMERGENCY_NOTE,
            )
        )

    if not teammate:
        return allow()

    owned = hs.tasks_owned_by(graph, teammate)
    if not owned:
        return allow()

    reasons: list[str] = []
    for task in owned:
        status = str(task.get("status", "")).lower()
        if status in {"complete", "completed", "done", "abandoned", "cancelled"}:
            continue

        owner_type = str(task.get("owner_type", "")).lower()
        deliverable = str(task.get("deliverable", "")).lower()
        is_reviewer = owner_type in REVIEWER_OWNER_TYPES or deliverable == "report"

        if is_reviewer:
            report = task.get("report_artifact") or task.get("required_review_artifacts")
            report_paths = [report] if isinstance(report, str) else (report or [])
            missing = _artifact_missing(report_paths, root)
            if not report_paths or not missing:
                # A read-only reviewer that has delivered its report may idle.
                continue
            reasons.append(
                f"task '{task.get('id')}' (review) has not delivered its report: " + ", ".join(missing)
            )
            continue

        if status in {"in_progress", "in-progress", "active", "claimed"}:
            reasons.append(f"task '{task.get('id')}' is still {status}")

        missing_artifacts = _artifact_missing(task.get("required_artifacts"), root)
        if missing_artifacts:
            reasons.append(
                f"task '{task.get('id')}' owes artifact(s): " + ", ".join(missing_artifacts)
            )
            if deliverable == "implementation" or owner_type in {"implementation", "implementer"}:
                reasons.append(
                    f"task '{task.get('id')}' was assigned as implementation work; analysis alone does not "
                    "satisfy it"
                )

        current_sha = _task_sha(task, root)
        receipts = hs.load_receipts(task.get("id"), root)
        needs_receipt = bool(task.get("required_receipts") or task.get("required_validation_commands"))
        if needs_receipt:
            passing = [
                r
                for r in receipts
                if not r.get("_error") and r.get("git_sha") == current_sha and hs.receipt_is_passing(r)
            ]
            if not passing:
                reasons.append(
                    f"task '{task.get('id')}' owes a passing test receipt at SHA "
                    f"{(current_sha or 'unknown')[:12]}"
                )

        findings = task.get("blocking_critical_findings") or task.get("assigned_critical_findings") or []
        if findings:
            reasons.append(
                f"task '{task.get('id')}' has unresolved critical finding(s): "
                + ", ".join(str(f) for f in findings)
            )

    if not reasons:
        return allow()

    numbered = "\n".join(f"  {i}. {r}" for i, r in enumerate(reasons, 1))
    return block_exit2(
        rejection(
            f"teammate '{teammate}' going idle with outstanding assigned work:\n{numbered}",
            f"TASK_GRAPH.json ownership for '{teammate}'; RUN_STATE mode='{state.get('mode')}'",
            "Finish the assigned work: produce the missing artifacts, run the required validation and "
            "record its receipt with .claude/tools/record_receipt.py, then set the task status to "
            "'complete'. If the work genuinely belongs to someone else, reassign the task's owner in "
            ".agent-run/TASK_GRAPH.json and say so explicitly.",
        )
    )


# ---------------------------------------------------------------------------
# SubagentStop
# ---------------------------------------------------------------------------


def handle_subagent_stop(event: dict, root: Path) -> int:
    if event.get("stop_hook_active") is True:
        return allow()

    agent_type = str(hs.first_present(event, "agent_type", "agentType", default="") or "")
    agent_id = str(hs.first_present(event, "agent_id", "agentId", default="") or "")

    if agent_type in READ_ONLY_AGENT_TYPES:
        return allow()
    if agent_type not in PROTECTED_AGENT_TYPES:
        return allow()

    try:
        state = hs.read_run_state(root)
        graph = hs.read_task_graph(root)
    except hs.StateError as exc:
        return block_decision(
            "SubagentStop",
            rejection(
                f"protected subagent '{agent_type}' stopping",
                f"durable state is unusable -- {exc}",
                "Report the malformed state file back to the lead instead of stopping silently. "
                + EMERGENCY_NOTE,
            ),
        )

    owned = hs.tasks_owned_by(graph, agent_type) + (
        hs.tasks_owned_by(graph, agent_id) if agent_id else []
    )
    seen: set[str] = set()
    unique_owned = []
    for task in owned:
        if task.get("id") not in seen:
            seen.add(task.get("id"))
            unique_owned.append(task)

    if not unique_owned:
        if state.get("mode") in {"hook_bootstrap", "hook_live_verification", "hook_maintenance", "ready_for_master"}:
            return allow()
        return block_decision(
            "SubagentStop",
            rejection(
                f"protected subagent '{agent_type}' stopping with no assigned contract",
                f"TASK_GRAPH.json has no task owned by '{agent_type}'"
                + (f" or '{agent_id}'" if agent_id else "")
                + f"; RUN_STATE mode='{state.get('mode')}'",
                "A protected implementation agent must be given a task in .agent-run/TASK_GRAPH.json "
                "naming it as owner, with required_artifacts and required_receipts, before it runs. "
                "Report back to the lead that no contract was assigned.",
            ),
        )

    problems: list[str] = []
    for task in unique_owned:
        status = str(task.get("status", "")).lower()
        if status in {"complete", "completed", "done", "abandoned"}:
            continue
        problems.append(f"task '{task.get('id')}' status is '{status or 'unset'}', not complete")
        missing = _artifact_missing(task.get("required_artifacts"), root)
        if missing:
            problems.append(f"task '{task.get('id')}' is missing output: " + ", ".join(missing))
        current_sha = _task_sha(task, root)
        if task.get("required_receipts") or task.get("required_validation_commands"):
            receipts = hs.load_receipts(task.get("id"), root)
            passing = [
                r
                for r in receipts
                if not r.get("_error") and r.get("git_sha") == current_sha and hs.receipt_is_passing(r)
            ]
            if not passing:
                problems.append(
                    f"task '{task.get('id')}' has no passing receipt at SHA {(current_sha or 'unknown')[:12]}"
                )

    if not problems:
        return allow()

    numbered = "\n".join(f"  {i}. {p}" for i, p in enumerate(problems, 1))
    return block_decision(
        "SubagentStop",
        rejection(
            f"protected subagent '{agent_type}' stopping with an incomplete contract:\n{numbered}",
            f"TASK_GRAPH.json contract for '{agent_type}'; RUN_STATE mode='{state.get('mode')}'",
            "Continue working: write the missing code and tests, record the receipt with "
            ".claude/tools/record_receipt.py, and set the task status to 'complete'. Analysis alone does "
            "not complete an implementation contract.",
        ),
    )


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------


def _stop_blockers(state: dict, root: Path) -> list[str]:
    """Return unmet gates preventing this run from stopping. Empty means allow."""
    mode = state.get("mode")

    if external_blocker_recorded(state):
        return []

    if mode == "hook_bootstrap":
        try:
            bootstrap = hs.read_bootstrap_status(root)
        except hs.StateError as exc:
            return [f"HOOK_BOOTSTRAP_STATUS.json is unusable -- {exc}"]
        overall = str(bootstrap.get("overall", ""))
        if overall in {"STATIC_PASS_LIVE_PENDING", "PASS"}:
            return []
        return [
            f"hook bootstrap overall status is '{overall}', not STATIC_PASS_LIVE_PENDING",
            "static_tests={} settings_validation={} monitored_runner_tests={}".format(
                bootstrap.get("static_tests"),
                bootstrap.get("settings_validation"),
                bootstrap.get("monitored_runner_tests"),
            ),
        ]

    if mode == "hook_live_verification":
        try:
            bootstrap = hs.read_bootstrap_status(root)
        except hs.StateError as exc:
            return [f"HOOK_BOOTSTRAP_STATUS.json is unusable -- {exc}"]
        if str(bootstrap.get("overall", "")) == "PASS":
            return []
        return [
            f"hook bootstrap overall status is '{bootstrap.get('overall')}', not PASS",
            "fresh_session_hooks_loaded={} live_event_tests={}".format(
                bootstrap.get("fresh_session_hooks_loaded"), bootstrap.get("live_event_tests")
            ),
        ]

    if mode in {"ready_for_master", "hook_maintenance", "complete", "external_blocker"}:
        return []

    if mode in {"implementation", "frozen_acceptance"}:
        blockers: list[str] = []
        try:
            acceptance = hs.read_acceptance_status(root)
        except hs.StateError as exc:
            return [f"ACCEPTANCE_STATUS.json is unusable -- {exc}"]
        overall = str(acceptance.get("overall", ""))
        if overall != "PASS":
            blockers.append(f"ACCEPTANCE_STATUS.json overall is '{overall}', not PASS")
            for finding in (acceptance.get("open_critical_findings") or [])[:5]:
                blockers.append(f"open critical finding: {finding}")
            for finding in (acceptance.get("open_mandatory_high_findings") or [])[:5]:
                blockers.append(f"open mandatory high finding: {finding}")
            unmet = [
                name
                for name, value in (acceptance.get("gates") or {}).items()
                if str(value).upper() != "PASS"
            ]
            if unmet:
                blockers.append("unmet acceptance gates: " + ", ".join(unmet[:8]))
            # Continuation guarantee (worker_silent_death class): while
            # acceptance is incomplete, a turn may only end if an unexpired
            # wakeup is armed — a silently dead worker must never strand the
            # run past a bounded, recorded deadline.
            word, detail = hs.continuation_status(root)
            if word == "malformed":
                blockers.append(
                    f"CONTINUATION.json is unusable -- {detail}; repair it and re-arm with "
                    ".claude/tools/arm_continuation.py --minutes N --reason '...'"
                )
            elif word == "expired":
                blockers.append(
                    f"the armed continuation expired at {detail} -- every idle wait must be "
                    "bounded while acceptance is incomplete: schedule the next wakeup and "
                    "record it with .claude/tools/arm_continuation.py, or continue the "
                    "highest-leverage in_progress task now"
                )
            elif word == "unarmed":
                blockers.append(
                    "no continuation trigger is armed (.agent-run/CONTINUATION.json) -- every "
                    "idle wait must be bounded while acceptance is incomplete: schedule a "
                    "wakeup, record it with .claude/tools/arm_continuation.py --minutes N "
                    "--reason '...', and keep at least one valid continuation armed until "
                    "acceptance is PASS"
                )
        running = [
            j
            for j in active_jobs(root)
            if str(j.get("classification")) == "frozen_acceptance"
            and str(j.get("state", "")).lower() not in {"finished", "completed", "terminated", "failed"}
        ]
        if running:
            blockers.append(
                "acceptance job(s) still running: "
                + ", ".join(str(j.get("job_id")) for j in running[:5])
                + " -- wait for them and read their final job records before concluding"
            )
        return blockers

    return []


def handle_stop(event: dict, root: Path) -> int:
    if event.get("stop_hook_active") is True:
        # Never recurse: /goal drives continuation, not this hook.
        return allow()

    try:
        state = hs.read_run_state(root)
    except hs.StateError as exc:
        return block_decision(
            "Stop",
            rejection(
                "ending this run",
                f"durable run state is unusable -- {exc}",
                "Repair .agent-run/RUN_STATE.json (valid JSON, supported 'mode', required fields), "
                "then re-evaluate whether the run may end. " + EMERGENCY_NOTE,
            ),
        )

    blockers = _stop_blockers(state, root)
    if not blockers:
        return allow()

    numbered = "\n".join(f"  {i}. {b}" for i, b in enumerate(blockers, 1))
    return block_decision(
        "Stop",
        rejection(
            f"ending this run with unmet gates:\n{numbered}",
            "RUN_STATE.json mode='{}' status='{}' phase='{}'; highest-leverage blocker: {}".format(
                state.get("mode"),
                state.get("status"),
                state.get("phase"),
                state.get("highest_leverage_blocker") or "none recorded",
            ),
            "Continue working on the exact next action recorded in RUN_STATE.json:\n"
            f"  {state.get('next_action') or '(RUN_STATE.next_action is empty -- set it now)'}\n"
            "Only two outcomes end this run: the acceptance gate reaching PASS, or a genuine "
            "EXTERNAL_BLOCKER recorded in RUN_STATE.json with exact evidence, attempted alternatives, "
            "and the exact human action required. A failing test, a scripting bug, or invalid JSON is "
            "not an external blocker -- fix it and keep going.",
        ),
    )


# ---------------------------------------------------------------------------
# StopFailure
# ---------------------------------------------------------------------------


def handle_stop_failure(event: dict, root: Path) -> int:
    """Log the API turn failure. This hook cannot continue or restart anything.

    Output and exit code are ignored by Claude Code for this event; the value is
    the durable record it leaves behind for an external operator.
    """
    record = {
        "schema_version": hs.SCHEMA_VERSION,
        "kind": "claude_code_api_turn_failure",
        "about": "the Claude Code turn ended due to a provider/API failure",
        "simulation_result": "not_applicable",
        "note": "This record describes a provider failure only. It is NOT a simulation or test result.",
        "timestamp": hs.utc_now_iso(),
        "error_type": hs.first_present(event, "error_type", "errorType", default="unknown"),
        "error_message": str(hs.first_present(event, "error_message", "errorMessage", default=""))[:2000],
        "session_id": hs.first_present(event, "session_id", "sessionId", default=None),
        "hook_event_name": event.get("hook_event_name"),
        "permission_mode": event.get("permission_mode"),
    }

    try:
        state = hs.read_run_state(root)
        record.update(
            {
                "mode": state.get("mode"),
                "phase": state.get("phase"),
                "run_status": state.get("status"),
                "highest_leverage_blocker": state.get("highest_leverage_blocker"),
                "next_action": state.get("next_action"),
            }
        )
    except hs.StateError as exc:
        record["state_error"] = str(exc)

    record["branch"] = hs.git_branch(root)
    record["git_sha"] = hs.git_sha(root)

    try:
        hs.append_jsonl(hs.agent_run_dir(root) / "FAILURE_LEDGER.jsonl", record)
    except OSError as exc:
        sys.stderr.write(f"control plane: could not append to FAILURE_LEDGER.jsonl: {exc}\n")

    recovery = {
        "schema_version": hs.SCHEMA_VERSION,
        "status": "RECOVERY_REQUESTED",
        "can_this_hook_restart_the_session": False,
        "explanation": (
            "A StopFailure hook can only record what happened. It cannot continue, retry, or restart "
            "the failed Claude Code session. Recovery requires an external operator or supervisor to "
            "start a new session from the recorded branch and SHA."
        ),
        "failure_type": record.get("error_type"),
        "details": record.get("error_message"),
        "session_id": record.get("session_id"),
        "phase": record.get("phase"),
        "mode": record.get("mode"),
        "branch": record.get("branch"),
        "git_sha": record.get("git_sha"),
        "highest_leverage_blocker": record.get("highest_leverage_blocker"),
        "next_action": record.get("next_action"),
        "timestamp": record["timestamp"],
    }
    try:
        hs.atomic_write_json(hs.agent_run_dir(root) / "RECOVERY_REQUEST.json", recovery)
    except OSError as exc:
        sys.stderr.write(f"control plane: could not write RECOVERY_REQUEST.json: {exc}\n")

    return allow()


# ---------------------------------------------------------------------------
# ConfigChange
# ---------------------------------------------------------------------------


def handle_config_change(event: dict, root: Path) -> int:
    # Live payloads name this field ``source``; ``config_source`` is accepted as
    # an alternate spelling. Reading only the latter made every real change
    # resolve to "unknown", which silently disabled the gate -- an unrecognised
    # source is never one of BLOCKING_CONFIG_SOURCES, so nothing could block.
    source = str(
        hs.first_present(event, "source", "config_source", "configSource", default="unknown")
        or "unknown"
    )
    changes = hs.first_present(event, "config_changes", "configChanges", default=None)

    log_record = {
        "schema_version": hs.SCHEMA_VERSION,
        "kind": "config_change",
        "timestamp": hs.utc_now_iso(),
        "config_source": source,
        "changed_file": hs.first_present(event, "file_path", "filePath", default=None),
        "session_id": hs.first_present(event, "session_id", "sessionId", default=None),
        "git_sha": hs.git_sha(root),
    }
    if source == "unknown":
        log_record["payload_fields"] = sorted(str(k) for k in event)
    if changes is not None:
        try:
            log_record["config_changes"] = json.loads(json.dumps(changes)[:4000])
        except (TypeError, ValueError):
            log_record["config_changes_summary"] = str(changes)[:2000]

    try:
        state = hs.read_run_state(root)
    except hs.StateError as exc:
        log_record["state_error"] = str(exc)
        state = None

    if state is not None:
        log_record["mode"] = state.get("mode")

    try:
        hs.append_jsonl(hs.agent_run_dir(root) / "CONFIG_CHANGES.jsonl", log_record)
    except OSError as exc:
        sys.stderr.write(f"control plane: could not append to CONFIG_CHANGES.jsonl: {exc}\n")

    if source == "policy_settings":
        # Managed policy is administered outside the project; the platform does
        # not permit a project hook to veto it. Log only.
        return emit(
            {
                "systemMessage": (
                    "control plane: managed policy settings changed. This is recorded in "
                    ".agent-run/CONFIG_CHANGES.jsonl; a project hook cannot block a managed policy change."
                ),
                "suppressOutput": True,
            }
        )

    if state is None:
        return block_decision(
            "ConfigChange",
            rejection(
                f"applying a {source} change",
                "durable run state is unusable, so the control plane cannot tell whether this change is "
                "authorised",
                "Repair .agent-run/RUN_STATE.json first, then re-apply the configuration change. "
                + EMERGENCY_NOTE,
            ),
        )

    mode = state.get("mode")
    protected_mode = mode in {"implementation", "frozen_acceptance"}

    # An unidentifiable source must not pass as "not one of the blocking ones".
    # Failing open there is how a renamed payload field silently disables this
    # gate; during a protected mode the conservative answer is to block and say
    # exactly why.
    if source == "unknown" and protected_mode and not in_hook_maintenance(state):
        return block_decision(
            "ConfigChange",
            rejection(
                f"applying a settings change during '{mode}' whose source could not be identified",
                f"RUN_STATE.json mode='{mode}'; the ConfigChange payload carried no recognised "
                f"source field (fields present: {', '.join(sorted(str(k) for k in event)) or 'none'})",
                "Treat this as a control-plane defect, not a routine change: record a "
                "hook-maintenance phase, confirm which payload field Claude Code now uses for the "
                "config source, update handle_config_change to read it, add a regression test, then "
                "re-apply the change.",
            ),
        )

    if source in BLOCKING_CONFIG_SOURCES and protected_mode:
        if in_hook_maintenance(state):
            return allow()
        return block_decision(
            "ConfigChange",
            rejection(
                f"applying a {source} change during '{mode}'",
                f"RUN_STATE.json mode='{mode}' and no hook-maintenance phase is recorded",
                "Enter a recorded hook-maintenance phase first: set RUN_STATE.json mode to "
                "'hook_maintenance' (or set \"hook_maintenance\": true) with the reason in "
                ".agent-run/DECISIONS.md, apply the change, run "
                "`python3 .claude/tools/validate_control_plane.py`, then restore the previous mode.",
            ),
        )

    return allow()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

HANDLERS = {
    "SessionStart": handle_session_start,
    "PreToolUse": handle_pre_tool_use,
    "TaskCompleted": handle_task_completed,
    "TeammateIdle": handle_teammate_idle,
    "SubagentStop": handle_subagent_stop,
    "Stop": handle_stop,
    "StopFailure": handle_stop_failure,
    "ConfigChange": handle_config_change,
}

#: Events whose failure must never wedge the session.
CONTEXT_ONLY_EVENTS = frozenset({"SessionStart", "StopFailure"})

#: How each safety gate signals a block when the dispatcher itself fails.
FAIL_CLOSED_EXIT2 = frozenset({"TaskCompleted", "TeammateIdle"})
FAIL_CLOSED_DECISION = frozenset({"Stop", "SubagentStop", "ConfigChange"})


def is_unhandled_event(event_name: str) -> bool:
    """True for an event this dispatcher has no gate for (including a missing name)."""
    return not event_name or event_name == "unknown" or event_name not in HANDLERS


def fail_closed(event_name: str, message: str) -> int:
    if event_name == "PreToolUse":
        return deny_tool(message)
    if event_name in FAIL_CLOSED_EXIT2:
        return block_exit2(message)
    if event_name in FAIL_CLOSED_DECISION:
        return block_decision(event_name, message)
    return allow()


def main(argv=None) -> int:
    event_name = "unknown"
    try:
        event = hs.read_event()
        event_name = str(event.get("hook_event_name") or "")
        if not event_name:
            raise hs.StateError("<stdin>", "hook event is missing 'hook_event_name'")
        handler = HANDLERS.get(event_name)
        if handler is None:
            # An event we are not configured for should never wedge anything.
            sys.stderr.write(f"control plane: no handler for hook event {event_name!r}\n")
            return 0
        root = hs.project_dir()
        return handler(event, root)
    except hs.StateError as exc:
        message = rejection(
            f"{event_name or 'hook'} processing",
            f"the control plane could not read required input -- {exc}",
            "Fix the reported input or state file and retry. " + EMERGENCY_NOTE,
        )
        if event_name in CONTEXT_ONLY_EVENTS or is_unhandled_event(event_name):
            sys.stderr.write(message + "\n")
            return 0
        return fail_closed(event_name, message)
    except Exception:  # noqa: BLE001 - deliberate catch-all; a gate must not crash open
        detail = traceback.format_exc(limit=6)
        message = rejection(
            f"{event_name or 'hook'} processing",
            "the control-plane hook raised an unexpected error and is failing closed:\n" + detail,
            "Fix .claude/hooks/gate.py (run `python3 -m pytest tests/control_plane -q`). " + EMERGENCY_NOTE,
        )
        if event_name in CONTEXT_ONLY_EVENTS or is_unhandled_event(event_name):
            sys.stderr.write(message + "\n")
            return 0
        return fail_closed(event_name, message)


if __name__ == "__main__":
    sys.exit(main())
