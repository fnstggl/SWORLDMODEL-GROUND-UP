"""Shared fixtures for the control-plane tests.

Every test drives the real scripts as subprocesses against a synthetic project
tree pointed at by ``CLAUDE_PROJECT_DIR``. Nothing here stubs the code under
test: the hooks parse real JSON from real stdin and read real files.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / ".claude" / "hooks" / "gate.py"
RUN_MONITORED = REPO_ROOT / ".claude" / "tools" / "run_monitored.py"
RECORD_RECEIPT = REPO_ROOT / ".claude" / "tools" / "record_receipt.py"
VALIDATOR = REPO_ROOT / ".claude" / "tools" / "validate_control_plane.py"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "control-plane-test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "control-plane-test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

DEFAULT_RUN_STATE = {
    "schema_version": 1,
    "mode": "hook_bootstrap",
    "status": "implementing",
    "phase": "control_plane_bootstrap",
    "frozen_sha": None,
    "highest_leverage_blocker": None,
    "next_action": "complete static hook validation",
    "open_critical_count": 0,
    "open_high_count": 0,
    "running_background_jobs": [],
    "passed_gates": [],
    "remaining_gates": ["static_hook_tests"],
    "completion_allowed": False,
    "master_context_loaded": False,
    "master_directive_path": None,
    "master_directive_sha256": None,
    "architecture_initialized": False,
    "task_graph_initialized": False,
    "acceptance_gates_initialized": False,
}

DEFAULT_BOOTSTRAP_STATUS = {
    "schema_version": 1,
    "overall": "IN_PROGRESS",
    "static_tests": "NOT_RUN",
    "settings_validation": "NOT_RUN",
    "monitored_runner_tests": "NOT_RUN",
    "fresh_session_hooks_loaded": "PENDING",
    "live_event_tests": "PENDING",
    "verified_commit": None,
}

DEFAULT_ACCEPTANCE_STATUS = {
    "schema_version": 1,
    "overall": "NOT_STARTED",
    "final_frozen_sha": None,
    "final_adjudicator": "NOT_RUN",
    "open_critical_findings": [],
    "open_mandatory_high_findings": [],
    "gates": {},
}


class Project:
    """A throwaway git-backed project tree with control-plane state."""

    def __init__(self, path: Path):
        self.path = path
        self.agent_run = path / ".agent-run"

    # -- construction ---------------------------------------------------

    @classmethod
    def create(cls) -> "Project":
        path = Path(tempfile.mkdtemp(prefix="cp-test-"))
        project = cls(path)
        (project.agent_run / "receipts").mkdir(parents=True, exist_ok=True)
        (path / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
        project.write_state("RUN_STATE.json", DEFAULT_RUN_STATE)
        project.write_state("HOOK_BOOTSTRAP_STATUS.json", DEFAULT_BOOTSTRAP_STATUS)
        project.write_state("ACCEPTANCE_STATUS.json", DEFAULT_ACCEPTANCE_STATUS)
        project.write_state("TASK_GRAPH.json", {"schema_version": 1, "status": "MASTER_DIRECTIVE_PENDING", "tasks": []})
        project.write_state("BACKGROUND_JOBS.json", {"schema_version": 1, "active_jobs": [], "completed_jobs": []})
        project.write_state(
            "UPSTREAM_PROTECTED_PATHS.json",
            {"schema_version": 1, "status": "MASTER_DIRECTIVE_PENDING", "repositories": [], "protected_paths": []},
        )
        project.write_text("GOAL.md", "# Goal\n\nBuild the working foundation.\n")
        project.write_text("ARCHITECTURE.md", "# Architecture State\nStatus: MASTER_DIRECTIVE_PENDING\n")
        project.write_text("CRITICAL_PATH.md",
                           "# Critical Path\nStatus: MASTER_DIRECTIVE_PENDING\n\n1. Complete static hook validation.\n")
        project.write_text("BLOCKERS.md", "# Blockers\n\nnone.\n")
        (project.agent_run / "FAILURE_LEDGER.jsonl").write_text("", encoding="utf-8")
        project._git_init()
        return project

    def destroy(self):
        shutil.rmtree(self.path, ignore_errors=True)

    def _git(self, *args, check=True):
        env = dict(os.environ)
        env.update(GIT_ENV)
        return subprocess.run(
            ["git", *args], cwd=str(self.path), capture_output=True, text=True, env=env,
            check=check, timeout=30,
        )

    def _git_init(self):
        self._git("init", "-q", "-b", "main")
        (self.path / "seed.txt").write_text("seed\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "seed")

    def commit_all(self, message="change"):
        (self.path / "seed.txt").write_text(f"{message}\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", message)
        return self.head_sha()

    def head_sha(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()

    # -- state helpers --------------------------------------------------

    def write_state(self, name: str, obj):
        self.agent_run.mkdir(parents=True, exist_ok=True)
        (self.agent_run / name).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")

    def read_state(self, name: str):
        return json.loads((self.agent_run / name).read_text(encoding="utf-8"))

    def write_text(self, name: str, text: str):
        self.agent_run.mkdir(parents=True, exist_ok=True)
        (self.agent_run / name).write_text(text, encoding="utf-8")

    def write_raw(self, name: str, text: str):
        (self.agent_run / name).write_text(text, encoding="utf-8")

    def set_mode(self, mode: str, **extra):
        state = self.read_state("RUN_STATE.json")
        state["mode"] = mode
        state.update(extra)
        self.write_state("RUN_STATE.json", state)

    def set_bootstrap(self, **fields):
        status = self.read_state("HOOK_BOOTSTRAP_STATUS.json")
        status.update(fields)
        self.write_state("HOOK_BOOTSTRAP_STATUS.json", status)

    def set_acceptance(self, **fields):
        status = self.read_state("ACCEPTANCE_STATUS.json")
        status.update(fields)
        self.write_state("ACCEPTANCE_STATUS.json", status)

    def set_tasks(self, tasks, **graph_fields):
        graph = {"schema_version": 1, "status": "MASTER_DIRECTIVE_PENDING", "tasks": tasks}
        graph.update(graph_fields)
        self.write_state("TASK_GRAPH.json", graph)

    def add_receipt(self, task_id: str, *, sha=None, exit_code=0, valid=True, command="pytest -q", **extra):
        receipt = {
            "schema_version": 1,
            "task_id": task_id,
            "git_sha": sha if sha is not None else self.head_sha(),
            "worktree": str(self.path),
            "command": command,
            "exit_code": exit_code,
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:10+00:00",
            "artifact_paths": [],
            "configuration_hashes": {},
            "valid": valid,
        }
        receipt.update(extra)
        name = f"{task_id}__{receipt['git_sha'][:12]}__{len(list((self.agent_run / 'receipts').glob('*.json')))}.json"
        (self.agent_run / "receipts" / name).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return receipt

    def touch(self, relative: str, content: str = "x\n") -> Path:
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def arm_continuation(self, minutes: float = 45, reason: str = "test wakeup",
                         expired: bool = False, **extra):
        """Write a CONTINUATION.json armed ``minutes`` into the future (or the
        past, with ``expired=True``) — the worker_silent_death sentinel record."""
        import datetime as dt

        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        delta = dt.timedelta(minutes=minutes)
        until = now - delta if expired else now + delta
        payload = {
            "schema_version": 1,
            "armed_at": now.isoformat(),
            "armed_until": until.isoformat(),
            "minutes": minutes,
            "reason": reason,
            "trigger_id": None,
            "workers": [],
        }
        payload.update(extra)
        self.write_state("CONTINUATION.json", payload)

    def add_active_job(self, job_id: str, classification="exploratory", state="progressing", **extra):
        registry = self.read_state("BACKGROUND_JOBS.json")
        job = {"job_id": job_id, "classification": classification, "state": state}
        job.update(extra)
        registry["active_jobs"].append(job)
        self.write_state("BACKGROUND_JOBS.json", registry)


class HookResult:
    def __init__(self, proc: subprocess.CompletedProcess):
        self.exit_code = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr
        try:
            self.json = json.loads(proc.stdout) if proc.stdout.strip() else {}
        except json.JSONDecodeError:
            self.json = {}

    # -- assertions helpers ---------------------------------------------

    @property
    def permission_decision(self):
        return (self.json.get("hookSpecificOutput") or {}).get("permissionDecision")

    @property
    def permission_reason(self) -> str:
        return (self.json.get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")

    @property
    def decision(self):
        return self.json.get("decision")

    @property
    def reason(self) -> str:
        return self.json.get("reason", "")

    @property
    def additional_context(self) -> str:
        return (self.json.get("hookSpecificOutput") or {}).get("additionalContext", "")

    @property
    def denied(self) -> bool:
        return self.permission_decision == "deny"

    @property
    def blocked(self) -> bool:
        """True when the hook blocked, by whichever mechanism this event uses."""
        return self.exit_code == 2 or self.decision == "block" or self.denied

    @property
    def message(self) -> str:
        """All human-readable text the hook produced, whichever channel it used."""
        return "\n".join([self.stderr, self.permission_reason, self.reason, self.stdout])

    def __repr__(self):
        return f"<HookResult exit={self.exit_code} blocked={self.blocked} stdout={self.stdout[:200]!r} stderr={self.stderr[:200]!r}>"


def run_gate(project: Project, event: dict, timeout: float = 30.0) -> HookResult:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project.path)
    env.update(GIT_ENV)
    proc = subprocess.run(
        [sys.executable, str(GATE)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project.path),
        timeout=timeout,
        check=False,
    )
    return HookResult(proc)


def run_tool(project: Project, script: Path, args, timeout: float = 120.0, cwd=None):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project.path)
    env.update(GIT_ENV)
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd or project.path),
        timeout=timeout,
        check=False,
    )
