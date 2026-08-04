"""Test-owned helpers for the gate-I operational-robustness suite.

Import this module AFTER the per-module version/importorskip gates in
engine-gated test modules; the subprocess utilities themselves are pure
stdlib and safe anywhere.

Subprocess discipline (suite constraint: no orphaned children, ever):

- every child is spawned with ``start_new_session=True`` so it leads its
  own process group, and every spawn goes through :func:`spawned_child`,
  whose ``finally`` block SIGKILLs the whole group and reaps the direct
  child regardless of how the test exited;
- every child command carries a UNIQUE MARKER argv token, and tests end
  by asserting :func:`assert_no_processes_with_marker` -- a /proc scan
  proving nothing carrying the marker survived (the same evidence rule
  the monitored runner applies: a live PID is never health, and an
  absent PID set is the only acceptable end state).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

#: the pinned engine interpreter every engine child runs under
ENGINE_PYTHON = "/home/user/engine-env/bin/python"

#: the monitored runner (outer timeout bound of record; driven against a
#: SYNTHETIC project tree via CLAUDE_PROJECT_DIR, never the real one)
RUN_MONITORED = REPO_ROOT / ".claude" / "tools" / "run_monitored.py"

#: default hard ceiling a test-owned child may run before the harness
#: kills it and fails the test (bounded-by-construction)
CHILD_HARD_TIMEOUT_S = 120.0


def child_env(**overrides) -> dict:
    """A copy of this process's environment with offline dummy LLM
    credentials guaranteed present, the repository importable, and any
    ``None``-valued override REMOVED from the child environment."""
    env = dict(os.environ)
    env.setdefault("AGENTSOCIETY_LLM_API_KEY", "dummy")
    env.setdefault("AGENTSOCIETY_LLM_API_BASE", "http://localhost:9")
    env.setdefault("AGENTSOCIETY_TRACE_WRITER_ASYNC", "0")
    parts = [part for part in
             env.get("PYTHONPATH", "").split(os.pathsep) if part]
    for extra in (str(HERE), str(REPO_ROOT / "tests" / "engine_contracts"),
                  str(REPO_ROOT / "tests" / "engine_baseline"),
                  str(REPO_ROOT / "tests" / "engine_counterfactuals"),
                  str(REPO_ROOT / "tests" / "engine_checkpoint"),
                  str(REPO_ROOT)):
        if extra not in parts:
            parts.append(extra)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = str(value)
    return env


class spawned_child:
    """Context manager owning one child process group end to end.

    Spawns ``argv`` with ``start_new_session=True`` (the child leads its
    own group), captures stdout/stderr to files under ``log_dir``, and on
    exit ALWAYS escalates SIGKILL to the whole group and reaps the direct
    child, so no test path can orphan descendants.
    """

    def __init__(self, argv, *, log_dir: Path, env: dict | None = None,
                 cwd: Path | None = None):
        self.argv = [str(part) for part in argv]
        self.log_dir = Path(log_dir)
        self.env = env if env is not None else child_env()
        self.cwd = cwd
        self.proc: subprocess.Popen | None = None
        self.stdout_path = self.log_dir / "child_stdout.log"
        self.stderr_path = self.log_dir / "child_stderr.log"
        self._handles = []

    def __enter__(self) -> "spawned_child":
        self.log_dir.mkdir(parents=True, exist_ok=True)
        out = open(self.stdout_path, "wb", buffering=0)
        err = open(self.stderr_path, "wb", buffering=0)
        self._handles = [out, err]
        self.proc = subprocess.Popen(
            self.argv,
            stdout=out,
            stderr=err,
            stdin=subprocess.DEVNULL,
            env=self.env,
            cwd=str(self.cwd) if self.cwd else None,
            start_new_session=True,
        )
        return self

    def __exit__(self, *exc) -> bool:
        try:
            if self.proc is not None and self.proc.poll() is None:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except OSError:
                    pass
            if self.proc is not None:
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    pass
        finally:
            for handle in self._handles:
                handle.close()
        return False

    # -- convenience -----------------------------------------------------
    def signal_group(self, sig) -> None:
        os.killpg(self.proc.pid, sig)

    def wait(self, timeout: float):
        return self.proc.wait(timeout=timeout)

    def stdout_text(self) -> str:
        return self.stdout_path.read_text(encoding="utf-8",
                                          errors="replace")

    def stderr_text(self) -> str:
        return self.stderr_path.read_text(encoding="utf-8",
                                          errors="replace")


def run_child(argv, *, log_dir: Path, env: dict | None = None,
              cwd: Path | None = None,
              timeout: float = CHILD_HARD_TIMEOUT_S):
    """Run a child to completion under the hard harness timeout; returns
    ``(returncode, stdout_text, stderr_text)``.  A child that outlives
    ``timeout`` is group-killed and reported as a harness failure by the
    caller's assertion on the returncode (None becomes -9)."""
    with spawned_child(argv, log_dir=log_dir, env=env, cwd=cwd) as child:
        try:
            code = child.wait(timeout)
        except subprocess.TimeoutExpired:
            code = None
        out = child.stdout_text()
        err = child.stderr_text()
    return code, out, err


def processes_with_marker(marker: str) -> list:
    """PIDs (other than this process) whose /proc cmdline carries the
    marker token."""
    own = os.getpid()
    hits = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == own:
            continue
        try:
            cmd = Path(f"/proc/{entry}/cmdline").read_bytes()
        except OSError:
            continue
        if marker.encode("utf-8") in cmd:
            hits.append(int(entry))
    return hits


def assert_no_processes_with_marker(marker: str, *,
                                    settle_s: float = 5.0) -> None:
    """No process carrying the marker may survive (bounded settle for
    zombie reaping); failing this means a test orphaned a child."""
    deadline = time.monotonic() + settle_s
    while time.monotonic() < deadline:
        if not processes_with_marker(marker):
            return
        time.sleep(0.1)
    survivors = processes_with_marker(marker)
    assert not survivors, (
        f"processes carrying marker {marker!r} survived the test: "
        f"{survivors}")


def wait_for_file_line(path: Path, needle: str, *,
                       timeout: float = 60.0) -> None:
    """Block (bounded) until ``path`` contains a line carrying
    ``needle``; raises AssertionError with diagnostics on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            if needle in text:
                return
        time.sleep(0.05)
    existing = (path.read_text(encoding="utf-8", errors="replace")
                if path.exists() else "<missing>")
    raise AssertionError(
        f"{needle!r} never appeared in {path} within {timeout}s; "
        f"content: {existing[:500]!r}")


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
