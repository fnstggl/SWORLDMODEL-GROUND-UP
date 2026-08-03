#!/usr/bin/env python3
"""Monitored job runner: the only supported way to run a long or detached job.

Every long-running command in this project goes through this wrapper so that a
job can never silently hang for hours. The wrapper owns the child's process
group, watches for *meaningful* progress rather than mere liveness, classifies
what kind of unhealthy it is, collects diagnostics before killing anything, and
always leaves a structured, recoverable job record behind.

Usage::

    python3 .claude/tools/run_monitored.py \
        --job-id nightly-corpus \
        --classification exploratory \
        --no-progress-timeout 600 \
        --total-timeout 7200 \
        --heartbeat-interval 15 \
        --progress-file .agent-run/jobs/nightly-corpus/progress.json \
        -- python3 run_worlds.py --corpus all

Exit codes:

====  =====================================================================
0     child exited 0
2     usage error, duplicate job id, or refused stale registration
124   hard total timeout; process group was terminated
125   no-progress timeout; process group was terminated
130   the wrapper itself was interrupted; process group was terminated
n     the child's own nonzero exit code
====  =====================================================================

A live PID is never treated as evidence of health, and the wrapper never calls
an unbounded ``wait()``.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import hook_state as hs  # noqa: E402

CLASSIFICATIONS = ("exploratory", "frozen_acceptance")

STATE_STARTING = "starting"
STATE_PROGRESSING = "progressing"
STATE_ALIVE_BUT_SLOW = "alive_but_slow"
STATE_PROBABLE_CPU_SPIN = "probable_cpu_spin"
STATE_BLOCKED_NO_ACTIVITY = "blocked_no_activity"
STATE_PROCESS_DEAD = "process_dead"
STATE_NO_PROGRESS_TIMEOUT = "no_progress_timeout"
STATE_HARD_TIMEOUT = "hard_timeout"
STATE_CHILD_FAILURE = "child_failure"
STATE_FINISHED = "finished"
STATE_INTERRUPTED = "interrupted"

EXIT_USAGE = 2
EXIT_HARD_TIMEOUT = 124
EXIT_NO_PROGRESS = 125
EXIT_INTERRUPTED = 130

MAX_HEARTBEAT_INTERVAL = 30.0
CPU_SPIN_CORES = 0.5  # sustained CPU use above this with no progress looks like a spin
CPU_IDLE_CORES = 0.01
CLOCK_TICKS = float(os.sysconf("SC_CLK_TCK")) if hasattr(os, "sysconf") else 100.0


# ---------------------------------------------------------------------------
# Registry (BACKGROUND_JOBS.json) -- atomic, lock-guarded
# ---------------------------------------------------------------------------


class _Lock:
    """Advisory lock around the shared job registry."""

    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+")
        try:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass  # best effort on platforms without flock
        return self

    def __exit__(self, *exc):
        if self.handle is not None:
            try:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
            self.handle.close()
            self.handle = None
        return False


def registry_path(root: Path) -> Path:
    return hs.agent_run_dir(root) / "BACKGROUND_JOBS.json"


def read_registry(root: Path) -> dict:
    data = hs.read_json(
        registry_path(root),
        default={"schema_version": hs.SCHEMA_VERSION, "active_jobs": [], "completed_jobs": []},
    )
    if not isinstance(data, dict):
        raise hs.StateError(registry_path(root), "expected a JSON object")
    data.setdefault("schema_version", hs.SCHEMA_VERSION)
    data.setdefault("active_jobs", [])
    data.setdefault("completed_jobs", [])
    return data


def mutate_registry(root: Path, mutator):
    """Apply ``mutator`` to the registry under a lock and write it atomically."""
    with _Lock(hs.agent_run_dir(root) / "BACKGROUND_JOBS.lock"):
        data = read_registry(root)
        result = mutator(data)
        hs.atomic_write_json(registry_path(root), data)
        return result


# ---------------------------------------------------------------------------
# Process inspection
# ---------------------------------------------------------------------------


def pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def _read_proc_stat(pid: int):
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8", errors="replace") as handle:
            raw = handle.read()
    except OSError:
        return None
    close = raw.rfind(")")
    if close == -1:
        return None
    head = raw[: raw.find("(")].strip()
    tail = raw[close + 2 :].split()
    try:
        return {
            "pid": int(head),
            "state": tail[0],
            "pgrp": int(tail[2]),
            "utime": int(tail[11]),
            "stime": int(tail[12]),
        }
    except (IndexError, ValueError):
        return None


def process_group_cpu_seconds(pgid: int) -> float | None:
    """Total CPU seconds consumed by every live process in the group."""
    if not os.path.isdir("/proc"):
        return None
    total = 0
    found = False
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None
    for entry in entries:
        if not entry.isdigit():
            continue
        stat = _read_proc_stat(int(entry))
        if stat and stat["pgrp"] == pgid:
            total += stat["utime"] + stat["stime"]
            found = True
    if not found:
        return None
    return total / CLOCK_TICKS


def process_group_members(pgid: int, include_zombies: bool = False) -> list[int]:
    """Live PIDs in the group. Zombies are excluded: they hold no resources."""
    members: list[int] = []
    if not os.path.isdir("/proc"):
        return members
    try:
        entries = os.listdir("/proc")
    except OSError:
        return members
    for entry in entries:
        if not entry.isdigit():
            continue
        stat = _read_proc_stat(int(entry))
        if not stat or stat["pgrp"] != pgid:
            continue
        if not include_zombies and stat.get("state") == "Z":
            continue
        members.append(stat["pid"])
    return sorted(members)


# ---------------------------------------------------------------------------
# Progress observation
# ---------------------------------------------------------------------------


class ProgressObserver:
    """Observes meaningful progress, strongest signal first.

    1. an explicit progress file carrying a completed-unit counter (strong)
    2. completed-unit records appended as lines to the progress file (strong)
    3. log file growth (weak fallback -- output alone is not real progress,
       but it is better evidence than a live PID)
    """

    def __init__(self, progress_file: Path | None, log_paths: list[Path]):
        self.progress_file = progress_file
        self.log_paths = log_paths
        self.units = None
        self.progress_fingerprint = None
        self.log_size = -1
        self.source = "none"

    def _read_units(self):
        if not self.progress_file or not self.progress_file.exists():
            return None, None
        try:
            stat = self.progress_file.stat()
            raw = self.progress_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None, None
        fingerprint = (stat.st_mtime_ns, stat.st_size)
        units = None
        text = raw.strip()
        if text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                units = len([line for line in text.splitlines() if line.strip()])
            else:
                if isinstance(data, dict):
                    for key in ("completed_units", "completed", "units_done", "progress", "done"):
                        if isinstance(data.get(key), (int, float)):
                            units = float(data[key])
                            break
                elif isinstance(data, (int, float)):
                    units = float(data)
        return units, fingerprint

    def _log_size(self) -> int:
        total = 0
        for path in self.log_paths:
            try:
                total += path.stat().st_size
            except OSError:
                pass
        return total

    def poll(self) -> tuple[bool, bool]:
        """Return ``(strong_progress, weak_progress)`` since the previous poll."""
        strong = False
        units, fingerprint = self._read_units()
        if fingerprint is not None and fingerprint != self.progress_fingerprint:
            self.progress_fingerprint = fingerprint
            strong = True
            self.source = "progress_file"
        if units is not None and self.units is not None and units > self.units:
            strong = True
            self.source = "completed_units"
        if units is not None:
            self.units = units

        size = self._log_size()
        weak = self.log_size >= 0 and size > self.log_size
        if weak and not strong:
            self.source = "log_movement"
        self.log_size = size
        return strong, weak


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def collect_diagnostics(pgid: int, pid: int, artifact_dir: Path, reason: str) -> str:
    """Best-effort snapshot taken *before* anything is terminated."""
    lines = [f"# diagnostics: {reason}", f"# captured_at: {hs.utc_now_iso()}", f"# pgid={pgid} pid={pid}", ""]

    members = process_group_members(pgid)
    lines.append(f"## process group members ({len(members)}): {members}")

    try:
        proc = subprocess.run(
            ["ps", "-o", "pid,ppid,pgid,stat,etime,time,%cpu,%mem,args", "-g", str(pgid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        lines.append("## ps -g")
        lines.append(proc.stdout or proc.stderr or "(no output)")
    except (OSError, subprocess.SubprocessError) as exc:
        lines.append(f"## ps unavailable: {exc}")

    for member in members[:10]:
        lines.append(f"## /proc/{member}")
        for name in ("status", "wchan", "cmdline"):
            try:
                with open(f"/proc/{member}/{name}", "r", encoding="utf-8", errors="replace") as handle:
                    content = handle.read(2000).replace("\x00", " ")
            except OSError as exc:
                lines.append(f"  {name}: unavailable ({exc.strerror})")
                continue
            if name == "status":
                keep = [
                    line
                    for line in content.splitlines()
                    if line.split(":")[0] in {"Name", "State", "Threads", "VmRSS", "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches"}
                ]
                lines.append("  " + " | ".join(keep))
            else:
                lines.append(f"  {name}: {content.strip()[:400]}")

    text = "\n".join(lines) + "\n"
    try:
        hs.atomic_write_text(artifact_dir / "diagnostics.txt", text)
    except OSError:
        pass
    return text


def tail_file(path: Path, limit: int = 2000) -> str:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Termination
# ---------------------------------------------------------------------------


def _group_gone(pgid: int, proc: subprocess.Popen) -> bool:
    """True only when the direct child is reaped *and* no group member survives.

    The direct child exiting is not enough: descendants it spawned stay in the
    same process group and would otherwise outlive the wrapper.
    """
    proc.poll()  # reap the direct child so it stops appearing as a zombie
    return proc.returncode is not None and not process_group_members(pgid)


def terminate_group(pgid: int, proc: subprocess.Popen, grace: float) -> str:
    """SIGTERM the whole group, escalate to SIGKILL after a bounded grace.

    Waits on the *entire* group, not just the direct child, so a command that
    forks descendants cannot leave orphans behind.
    """
    if _group_gone(pgid, proc):
        return "already_exited"

    try:
        os.killpg(pgid, signal.SIGTERM)
        outcome = "sigterm"
    except OSError:
        outcome = "sigterm_direct"
        try:
            proc.terminate()
        except OSError:
            pass

    deadline = time.monotonic() + max(0.5, grace)
    while time.monotonic() < deadline:
        if _group_gone(pgid, proc):
            return outcome
        time.sleep(0.05)

    try:
        os.killpg(pgid, signal.SIGKILL)
        outcome = "sigkill"
    except OSError:
        outcome = "sigkill_direct"
        try:
            proc.kill()
        except OSError:
            pass

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if _group_gone(pgid, proc):
            break
        time.sleep(0.05)
    return outcome


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1 :]
    return argv, []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_monitored.py",
        description="Run a child command under progress monitoring with bounded timeouts.",
    )
    parser.add_argument("--job-id", required=True, help="unique identifier for this job")
    parser.add_argument("--classification", required=True, choices=CLASSIFICATIONS)
    parser.add_argument("--no-progress-timeout", type=float, default=600.0,
                        help="seconds without meaningful progress before termination")
    parser.add_argument("--total-timeout", type=float, default=7200.0,
                        help="hard wall-clock ceiling in seconds")
    parser.add_argument("--heartbeat-interval", type=float, default=15.0,
                        help="seconds between heartbeat writes (clamped to <= 30)")
    parser.add_argument("--progress-file", default=None,
                        help="file the child updates with completed-unit records")
    parser.add_argument("--artifact-dir", default=None,
                        help="directory for logs, diagnostics and the job record")
    parser.add_argument("--cwd", default=None, help="working directory for the child")
    parser.add_argument("--grace-period", type=float, default=10.0,
                        help="seconds between SIGTERM and SIGKILL")
    parser.add_argument("--poll-interval", type=float, default=0.2, help="internal poll cadence")
    parser.add_argument("--reclaim-stale", action="store_true",
                        help="take over a stale registration for the same job id")
    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _write_record(artifact_dir: Path, record: dict) -> None:
    hs.atomic_write_json(artifact_dir / "job.json", record)


def _finalize(root: Path, artifact_dir: Path, record: dict) -> None:
    """Write the final record and move the job out of the active registry."""
    _write_record(artifact_dir, record)

    def mutate(data):
        data["active_jobs"] = [j for j in data["active_jobs"] if j.get("job_id") != record["job_id"]]
        data["completed_jobs"] = [
            j for j in data["completed_jobs"] if j.get("job_id") != record["job_id"]
        ]
        data["completed_jobs"].append(record)
        if len(data["completed_jobs"]) > 200:
            data["completed_jobs"] = data["completed_jobs"][-200:]

    mutate_registry(root, mutate)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    own_args, child_cmd = split_argv(argv)
    parser = build_parser()
    args = parser.parse_args(own_args)

    if not child_cmd:
        parser.error("no child command given; put it after '--'")

    root = hs.project_dir()
    heartbeat_interval = min(max(1.0, args.heartbeat_interval), MAX_HEARTBEAT_INTERVAL)
    artifact_dir = Path(args.artifact_dir) if args.artifact_dir else hs.jobs_dir(root) / args.job_id
    if not artifact_dir.is_absolute():
        artifact_dir = root / artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)

    progress_file = None
    if args.progress_file:
        progress_file = Path(args.progress_file)
        if not progress_file.is_absolute():
            progress_file = root / args.progress_file

    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    heartbeat_path = artifact_dir / "heartbeat.json"

    # ---- duplicate / stale registration -------------------------------
    existing = None
    for job in read_registry(root).get("active_jobs", []):
        if job.get("job_id") == args.job_id:
            existing = job
            break

    if existing is not None:
        pid = int(existing.get("pid") or 0)
        beat = hs.parse_iso(str(existing.get("heartbeat_at") or ""))
        age = None
        if beat is not None:
            age = (
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc) - beat
            ).total_seconds()
        alive = pid_alive(pid)
        stale = (not alive) or (age is not None and age > max(90.0, heartbeat_interval * 4))
        if not stale:
            sys.stderr.write(
                f"run_monitored: DUPLICATE JOB ID '{args.job_id}' is already active "
                f"(pid={pid}, heartbeat {age if age is None else round(age, 1)}s ago). "
                "Choose a different --job-id or wait for the running job to finish.\n"
            )
            return EXIT_USAGE
        diagnosis = (
            f"run_monitored: STALE REGISTRATION for job '{args.job_id}': "
            f"pid={pid} alive={alive}, last heartbeat "
            f"{'never' if age is None else str(round(age, 1)) + 's ago'}, "
            f"recorded state={existing.get('state')!r}. The previous wrapper did not finalize "
            "(it was killed, the machine restarted, or the job record was interrupted)."
        )
        if not args.reclaim_stale:
            sys.stderr.write(diagnosis + " Re-run with --reclaim-stale to take it over.\n")
            return EXIT_USAGE
        sys.stderr.write(diagnosis + " Reclaiming because --reclaim-stale was given.\n")

        def _drop(data):
            data["active_jobs"] = [j for j in data["active_jobs"] if j.get("job_id") != args.job_id]

        mutate_registry(root, _drop)

    # ---- provenance ---------------------------------------------------
    child_cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd().resolve()
    started_at = hs.utc_now_iso()
    start_monotonic = time.monotonic()
    git_sha = hs.git_sha(root)
    worktree_clean = hs.git_is_clean(root)

    record = {
        "schema_version": hs.SCHEMA_VERSION,
        "job_id": args.job_id,
        "classification": args.classification,
        "state": STATE_STARTING,
        "command": child_cmd,
        "command_string": " ".join(child_cmd),
        "cwd": str(child_cwd),
        "git_sha": git_sha,
        "git_branch": hs.git_branch(root),
        "worktree_clean_at_start": worktree_clean,
        "frozen_integrity": (
            "OK"
            if args.classification != "frozen_acceptance" or worktree_clean
            else "DIRTY_WORKTREE: evidence from this run is not tied to a single unchanged SHA"
        ),
        "started_at": started_at,
        "no_progress_timeout_s": args.no_progress_timeout,
        "total_timeout_s": args.total_timeout,
        "heartbeat_interval_s": heartbeat_interval,
        "deadline_no_progress_at": None,
        "hard_deadline_at": None,
        "artifact_dir": str(artifact_dir),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "progress_file": str(progress_file) if progress_file else None,
        "pid": None,
        "pgid": None,
        "heartbeat_at": started_at,
        "progress_source": "none",
        "cpu_seconds": 0.0,
        "exit_code": None,
        "finished_at": None,
    }

    # Register before spawning so a crash still leaves a recoverable record.
    def _register(data):
        data["active_jobs"] = [j for j in data["active_jobs"] if j.get("job_id") != args.job_id]
        data["active_jobs"].append(record)

    mutate_registry(root, _register)
    _write_record(artifact_dir, record)

    stdout_handle = open(stdout_path, "wb", buffering=0)
    stderr_handle = open(stderr_path, "wb", buffering=0)

    try:
        proc = subprocess.Popen(
            child_cmd,
            cwd=str(child_cwd),
            stdout=stdout_handle,
            stderr=stderr_handle,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # child leads its own process group
            close_fds=True,
        )
    except OSError as exc:
        stdout_handle.close()
        stderr_handle.close()
        record.update(
            {
                "state": STATE_CHILD_FAILURE,
                "exit_code": EXIT_USAGE,
                "finished_at": hs.utc_now_iso(),
                "error": f"could not start child: {exc}",
            }
        )
        _finalize(root, artifact_dir, record)
        sys.stderr.write(f"run_monitored: could not start child: {exc}\n")
        return EXIT_USAGE

    try:
        pgid = os.getpgid(proc.pid)
    except OSError:
        pgid = proc.pid

    record.update({"pid": proc.pid, "pgid": pgid, "state": STATE_PROGRESSING})

    observer = ProgressObserver(progress_file, [stdout_path, stderr_path])
    observer.poll()

    last_progress = start_monotonic
    last_weak = start_monotonic
    last_heartbeat = 0.0
    last_cpu = process_group_cpu_seconds(pgid) or 0.0
    last_cpu_time = start_monotonic
    cpu_rate = 0.0
    state = STATE_PROGRESSING
    interrupted = {"flag": False}
    observed_states: list[dict] = []

    def note_state(current: str, now_monotonic: float) -> None:
        """Record each distinct health classification the job passed through.

        The final record carries the whole sequence, so 'probable_cpu_spin
        followed by no_progress_timeout' stays distinguishable from a plain
        idle hang after the job is over.
        """
        if observed_states and observed_states[-1]["state"] == current:
            observed_states[-1]["until_elapsed_s"] = round(now_monotonic - start_monotonic, 3)
            return
        observed_states.append(
            {
                "state": current,
                "at": hs.utc_now_iso(),
                "elapsed_s": round(now_monotonic - start_monotonic, 3),
                "until_elapsed_s": round(now_monotonic - start_monotonic, 3),
                "cpu_cores": round(cpu_rate, 3),
                "seconds_since_progress": round(now_monotonic - last_progress, 3),
            }
        )

    def _on_signal(signum, _frame):
        interrupted["flag"] = True

    previous_handlers = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            previous_handlers[sig] = signal.signal(sig, _on_signal)
        except (OSError, ValueError):
            pass

    def heartbeat(now_monotonic: float, force: bool = False):
        nonlocal last_heartbeat
        if not force and now_monotonic - last_heartbeat < heartbeat_interval:
            return
        last_heartbeat = now_monotonic
        elapsed = now_monotonic - start_monotonic
        record.update(
            {
                "state": state,
                "heartbeat_at": hs.utc_now_iso(),
                "elapsed_s": round(elapsed, 3),
                "seconds_since_progress": round(now_monotonic - last_progress, 3),
                "progress_source": observer.source,
                "completed_units": observer.units,
                "cpu_seconds": round(last_cpu, 3),
                "cpu_cores_recent": round(cpu_rate, 3),
                "process_group_size": len(process_group_members(pgid)),
                "deadline_no_progress_at": round(args.no_progress_timeout - (now_monotonic - last_progress), 3),
                "hard_deadline_at": round(args.total_timeout - elapsed, 3),
            }
        )
        try:
            hs.atomic_write_json(heartbeat_path, record)
            _write_record(artifact_dir, record)

            def _touch(data):
                for index, job in enumerate(data["active_jobs"]):
                    if job.get("job_id") == args.job_id:
                        data["active_jobs"][index] = dict(record)
                        return
                data["active_jobs"].append(dict(record))

            mutate_registry(root, _touch)
        except (OSError, hs.StateError):
            pass

    termination_reason = None
    exit_code = None

    try:
        while True:
            now = time.monotonic()
            returncode = proc.poll()

            if returncode is not None:
                state = STATE_FINISHED if returncode == 0 else STATE_CHILD_FAILURE
                exit_code = returncode
                observer.poll()
                break

            if interrupted["flag"]:
                state = STATE_INTERRUPTED
                termination_reason = "wrapper received SIGINT/SIGTERM"
                break

            strong, weak = observer.poll()
            if strong:
                last_progress = now
                last_weak = now
            elif weak:
                last_progress = now
                last_weak = now

            if now - last_cpu_time >= 1.0:
                current_cpu = process_group_cpu_seconds(pgid)
                if current_cpu is not None:
                    cpu_rate = (current_cpu - last_cpu) / (now - last_cpu_time)
                    last_cpu = current_cpu
                last_cpu_time = now

            elapsed = now - start_monotonic
            since_progress = now - last_progress

            if elapsed >= args.total_timeout:
                state = STATE_HARD_TIMEOUT
                termination_reason = (
                    f"hard total timeout: {elapsed:.1f}s elapsed >= --total-timeout {args.total_timeout}s"
                )
                break

            if since_progress >= args.no_progress_timeout:
                state = STATE_NO_PROGRESS_TIMEOUT
                termination_reason = (
                    f"no meaningful progress for {since_progress:.1f}s "
                    f">= --no-progress-timeout {args.no_progress_timeout}s "
                    f"(last progress source: {observer.source}, cpu {cpu_rate:.2f} cores)"
                )
                break

            if not process_group_members(pgid) and proc.poll() is None:
                state = STATE_PROCESS_DEAD
            elif since_progress < args.no_progress_timeout * 0.5:
                state = STATE_PROGRESSING
            elif cpu_rate >= CPU_SPIN_CORES:
                state = STATE_PROBABLE_CPU_SPIN
            elif cpu_rate <= CPU_IDLE_CORES and (now - last_weak) >= args.no_progress_timeout * 0.5:
                state = STATE_BLOCKED_NO_ACTIVITY
            else:
                state = STATE_ALIVE_BUT_SLOW

            note_state(state, now)
            heartbeat(now)
            time.sleep(max(0.02, min(args.poll_interval, 1.0)))
    finally:
        for sig, handler in previous_handlers.items():
            try:
                signal.signal(sig, handler)
            except (OSError, ValueError):
                pass

    diagnostics_text = ""
    termination_outcome = None
    if termination_reason is not None:
        diagnostics_text = collect_diagnostics(pgid, proc.pid, artifact_dir, termination_reason)
        termination_outcome = terminate_group(pgid, proc, args.grace_period)
        exit_code = {
            STATE_HARD_TIMEOUT: EXIT_HARD_TIMEOUT,
            STATE_NO_PROGRESS_TIMEOUT: EXIT_NO_PROGRESS,
            STATE_INTERRUPTED: EXIT_INTERRUPTED,
        }.get(state, 1)

    stdout_handle.close()
    stderr_handle.close()

    finished = hs.utc_now_iso()
    total_elapsed = time.monotonic() - start_monotonic
    final_cpu = process_group_cpu_seconds(pgid)
    record.update(
        {
            "state": state,
            "exit_code": exit_code,
            "child_returncode": proc.returncode,
            "finished_at": finished,
            "elapsed_s": round(total_elapsed, 3),
            "termination_reason": termination_reason,
            "termination_outcome": termination_outcome,
            "process_group_terminated": termination_outcome is not None,
            "survivors_after_termination": process_group_members(pgid) if termination_outcome else [],
            "cpu_seconds": round(final_cpu if final_cpu is not None else last_cpu, 3),
            "completed_units": observer.units,
            "progress_source": observer.source,
            "observed_states": observed_states,
            "observed_state_names": sorted({entry["state"] for entry in observed_states}),
            "diagnostics_path": str(artifact_dir / "diagnostics.txt") if diagnostics_text else None,
            "stdout_tail": tail_file(stdout_path, 1500),
            "stderr_tail": tail_file(stderr_path, 1500),
            "recoverable": True,
        }
    )
    _finalize(root, artifact_dir, record)

    summary = (
        f"run_monitored: job '{args.job_id}' state={state} exit={exit_code} "
        f"elapsed={total_elapsed:.1f}s cpu={record['cpu_seconds']}s "
        f"record={artifact_dir / 'job.json'}"
    )
    sys.stderr.write(summary + "\n")
    if termination_reason:
        sys.stderr.write(f"run_monitored: {termination_reason}\n")

    return int(exit_code if exit_code is not None else 1)


if __name__ == "__main__":
    sys.exit(main())
