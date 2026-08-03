"""Adversarial tests for .claude/tools/run_monitored.py.

These use tiny local child programs, never the real simulation corpus, and the
whole file is designed to finish in seconds. Each test asserts on the durable
job record the wrapper leaves behind, because that record is what a later
session actually reads.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import RUN_MONITORED, GIT_ENV, Project  # noqa: E402

# Child programs, kept inline so the tests have no external fixture files.
CHILD_PROGRESS_STDOUT = (
    "import sys, time\n"
    "for i in range(200):\n"
    "    print('unit', i); sys.stdout.flush(); time.sleep(0.05)\n"
)
CHILD_PROGRESS_FILE = (
    "import json, sys, time\n"
    "path = sys.argv[1]\n"
    "for i in range(200):\n"
    "    open(path, 'w').write(json.dumps({'completed_units': i}))\n"
    "    time.sleep(0.05)\n"
)
CHILD_SLEEP = "import time; time.sleep(120)"
CHILD_SPIN = "\nwhile True:\n    pass\n"
CHILD_SPAWNS_DESCENDANTS = (
    "import subprocess, sys, time\n"
    "kids = [subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']) for _ in range(3)]\n"
    "print('spawned', flush=True)\n"
    "time.sleep(120)\n"
)
#: Descendants that ignore SIGTERM. Only SIGKILL escalation clears them, so a
#: wrapper that merely signals the group and returns leaves survivors behind.
CHILD_STUBBORN_DESCENDANTS = (
    "import signal, subprocess, sys, time\n"
    "kid = 'import signal,time\\n"
    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\\n"
    "while True: time.sleep(0.1)'\n"
    "for _ in range(3):\n"
    "    subprocess.Popen([sys.executable, '-c', kid])\n"
    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "print('stubborn group ready', flush=True)\n"
    "while True:\n"
    "    time.sleep(0.1)\n"
)
#: The discriminating case for group termination: the direct child exits on the
#: first SIGTERM while its descendants ignore it. A wrapper that stops waiting
#: as soon as the direct child is reaped declares success and orphans them.
CHILD_DIES_LEAVING_STUBBORN_DESCENDANTS = (
    "import subprocess, sys, time\n"
    "kid = 'import signal,time\\n"
    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\\n"
    "while True: time.sleep(0.1)'\n"
    "for _ in range(3):\n"
    "    subprocess.Popen([sys.executable, '-c', kid])\n"
    "print('parent will die on SIGTERM', flush=True)\n"
    "while True:\n"
    "    time.sleep(0.1)\n"
)
CHILD_PARTIAL_THEN_HANG = (
    "import sys, time\n"
    "print('PARTIAL LOG LINE'); sys.stdout.flush()\n"
    "sys.stderr.write('PARTIAL ERR LINE\\n'); sys.stderr.flush()\n"
    "time.sleep(120)\n"
)


class RunnerTestCase(unittest.TestCase):
    def setUp(self):
        self.project = Project.create()
        self.addCleanup(self.project.destroy)

    def run_monitored(self, job_id, child, *, classification="exploratory", no_progress=2.0,
                      total=30.0, heartbeat=1.0, progress_file=None, extra=(), child_args=(),
                      timeout=90.0, grace=1.0):
        args = [
            sys.executable, str(RUN_MONITORED),
            "--job-id", job_id,
            "--classification", classification,
            "--no-progress-timeout", str(no_progress),
            "--total-timeout", str(total),
            "--heartbeat-interval", str(heartbeat),
            "--grace-period", str(grace),
            *extra,
        ]
        if progress_file:
            args += ["--progress-file", progress_file]
        args += ["--", sys.executable, "-c", child, *child_args]
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project.path)
        env.update(GIT_ENV)
        return subprocess.run(args, capture_output=True, text=True, env=env,
                              cwd=str(self.project.path), timeout=timeout, check=False)

    def record(self, job_id) -> dict:
        path = self.project.path / ".agent-run" / "jobs" / job_id / "job.json"
        self.assertTrue(path.exists(), f"no job record written for {job_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def registry(self) -> dict:
        return self.project.read_state("BACKGROUND_JOBS.json")

    def assert_no_strays(self, record):
        self.assertEqual(record.get("survivors_after_termination"), [],
                         "the whole process group must be gone after termination")


class TestHealthyJobs(RunnerTestCase):
    def test_healthy_process_producing_regular_progress(self):
        proc = self.run_monitored("healthy-stdout", CHILD_PROGRESS_STDOUT, no_progress=3.0, total=2.0)
        self.assertEqual(proc.returncode, 124, proc.stderr)  # bounded by total timeout, never by stall
        record = self.record("healthy-stdout")
        self.assertEqual(record["state"], "hard_timeout")
        self.assertIn("progressing", record["observed_state_names"])
        self.assertNotIn("blocked_no_activity", record["observed_state_names"])
        self.assertEqual(record["progress_source"], "log_movement")

    def test_healthy_process_with_explicit_progress_file(self):
        progress = self.project.path / "progress.json"
        proc = self.run_monitored("healthy-progress", CHILD_PROGRESS_FILE, no_progress=3.0, total=2.0,
                                  progress_file=str(progress), child_args=(str(progress),))
        self.assertEqual(proc.returncode, 124, proc.stderr)
        record = self.record("healthy-progress")
        self.assertIn(record["progress_source"], {"progress_file", "completed_units"})
        self.assertIsNotNone(record["completed_units"])
        self.assertGreater(record["completed_units"], 0)
        self.assertIn("progressing", record["observed_state_names"])

    def test_child_exits_successfully(self):
        proc = self.run_monitored("exit-ok", "print('done')")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        record = self.record("exit-ok")
        self.assertEqual(record["state"], "finished")
        self.assertEqual(record["exit_code"], 0)
        self.assertIn("done", record["stdout_tail"])
        self.assertIsNone(record["termination_reason"])

    def test_child_exits_nonzero(self):
        proc = self.run_monitored("exit-fail", "import sys; sys.stderr.write('boom\\n'); sys.exit(7)")
        self.assertEqual(proc.returncode, 7, proc.stderr)
        record = self.record("exit-fail")
        self.assertEqual(record["state"], "child_failure")
        self.assertEqual(record["exit_code"], 7)
        self.assertIn("boom", record["stderr_tail"])


class TestUnhealthyJobs(RunnerTestCase):
    def test_outputless_sleeping_process_hits_no_progress_timeout(self):
        started = time.monotonic()
        proc = self.run_monitored("idle-hang", CHILD_SLEEP, no_progress=2.0, total=60.0)
        elapsed = time.monotonic() - started
        self.assertEqual(proc.returncode, 125, proc.stderr)
        self.assertLess(elapsed, 20.0, "no-progress timeout must fire promptly")
        record = self.record("idle-hang")
        self.assertEqual(record["state"], "no_progress_timeout")
        self.assertIn("no meaningful progress", record["termination_reason"])
        self.assertIn("blocked_no_activity", record["observed_state_names"])
        self.assert_no_strays(record)

    def test_cpu_bound_infinite_loop_is_detected_and_bounded(self):
        proc = self.run_monitored("cpu-spin", CHILD_SPIN, no_progress=2.0, total=60.0)
        self.assertEqual(proc.returncode, 125, proc.stderr)
        record = self.record("cpu-spin")
        self.assertEqual(record["state"], "no_progress_timeout")
        self.assertIn("probable_cpu_spin", record["observed_state_names"],
                      "a busy loop must be distinguishable from an idle block")
        self.assertNotIn("blocked_no_activity", record["observed_state_names"])
        self.assertGreater(record["cpu_seconds"], 0.5, "CPU time must be tracked")
        self.assert_no_strays(record)

    def test_a_live_pid_alone_is_not_treated_as_health(self):
        """The sleeping child stays alive the whole time and is still terminated."""
        record_proc = self.run_monitored("alive-but-stuck", CHILD_SLEEP, no_progress=2.0, total=60.0)
        self.assertNotEqual(record_proc.returncode, 0)
        record = self.record("alive-but-stuck")
        self.assertTrue(record["process_group_terminated"])
        self.assertEqual(record["child_returncode"], -signal.SIGTERM)

    def test_hard_total_timeout(self):
        proc = self.run_monitored("hard-timeout", CHILD_PROGRESS_STDOUT, no_progress=60.0, total=2.0)
        self.assertEqual(proc.returncode, 124, proc.stderr)
        record = self.record("hard-timeout")
        self.assertEqual(record["state"], "hard_timeout")
        self.assertIn("hard total timeout", record["termination_reason"])
        self.assertLess(record["elapsed_s"], 20.0)
        self.assert_no_strays(record)


class TestProcessGroupHandling(RunnerTestCase):
    def test_child_that_spawns_descendants_is_fully_terminated(self):
        proc = self.run_monitored("descendants", CHILD_SPAWNS_DESCENDANTS, no_progress=2.0, total=60.0)
        self.assertNotEqual(proc.returncode, 0)
        record = self.record("descendants")
        self.assertTrue(record["process_group_terminated"])
        self.assertIn(record["termination_outcome"], {"sigterm", "sigkill", "sigterm_direct", "sigkill_direct"})
        self.assert_no_strays(record)

        diagnostics = Path(record["diagnostics_path"]).read_text(encoding="utf-8")
        self.assertIn("process group members", diagnostics)
        # 1 parent + 3 children were alive when diagnostics were captured.
        self.assertRegex(diagnostics, r"process group members \([2-9]\)")

    def test_sigterm_ignoring_group_is_escalated_to_sigkill(self):
        """Requirement: escalate SIGTERM -> SIGKILL after a bounded grace, and confirm death."""
        started = time.monotonic()
        proc = self.run_monitored("stubborn", CHILD_STUBBORN_DESCENDANTS,
                                  no_progress=2.0, total=60.0, grace=1.0)
        elapsed = time.monotonic() - started
        self.assertNotEqual(proc.returncode, 0)
        record = self.record("stubborn")
        self.assertEqual(record["termination_outcome"], "sigkill",
                         "a group that ignores SIGTERM must be escalated to SIGKILL")
        self.assertEqual(record["survivors_after_termination"], [],
                         "the wrapper must confirm the whole group is gone, not just signal it")
        self.assertLess(elapsed, 30.0, "escalation must happen within a bounded grace period")

    def test_descendants_are_not_orphaned_when_the_parent_dies_first(self):
        """The direct child exiting is not proof the group is gone."""
        proc = self.run_monitored("orphans", CHILD_DIES_LEAVING_STUBBORN_DESCENDANTS,
                                  no_progress=2.0, total=60.0, grace=1.0)
        self.assertNotEqual(proc.returncode, 0)
        record = self.record("orphans")
        self.assertEqual(record["survivors_after_termination"], [],
                         "descendants that ignore SIGTERM must not survive the wrapper")
        self.assertEqual(record["termination_outcome"], "sigkill",
                         "escalation must be driven by the whole group, not the direct child alone")

    def test_diagnostics_are_collected_before_termination(self):
        proc = self.run_monitored("diagnostics", CHILD_SLEEP, no_progress=2.0, total=60.0)
        self.assertNotEqual(proc.returncode, 0)
        record = self.record("diagnostics")
        path = Path(record["diagnostics_path"])
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        self.assertIn("no meaningful progress", text)
        self.assertIn("## ps -g", text)

    def test_partial_logs_survive_termination(self):
        proc = self.run_monitored("partial-logs", CHILD_PARTIAL_THEN_HANG, no_progress=2.0, total=60.0)
        self.assertNotEqual(proc.returncode, 0)
        record = self.record("partial-logs")
        stdout_log = Path(record["stdout_log"])
        stderr_log = Path(record["stderr_log"])
        self.assertIn("PARTIAL LOG LINE", stdout_log.read_text(encoding="utf-8"))
        self.assertIn("PARTIAL ERR LINE", stderr_log.read_text(encoding="utf-8"))
        self.assertIn("PARTIAL LOG LINE", record["stdout_tail"])


class TestJobRegistry(RunnerTestCase):
    def test_job_registry_is_written_atomically(self):
        """A concurrent reader must never observe a partially written registry."""
        registry_path = self.project.agent_run / "BACKGROUND_JOBS.json"
        errors: list[str] = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    text = registry_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                if not text.strip():
                    errors.append("observed an empty registry")
                    continue
                try:
                    json.loads(text)
                except json.JSONDecodeError as exc:
                    errors.append(f"observed a torn registry: {exc}")

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        try:
            self.run_monitored("atomic", CHILD_PROGRESS_STDOUT, no_progress=5.0, total=2.0, heartbeat=1.0)
        finally:
            stop.set()
            thread.join(timeout=5)

        self.assertEqual(errors, [])
        leftovers = list(self.project.agent_run.glob(".BACKGROUND_JOBS.json.*"))
        self.assertEqual(leftovers, [], "atomic writes must not leave temp files behind")

    def test_completed_job_moves_from_active_to_completed(self):
        self.run_monitored("lifecycle", "print('x')")
        registry = self.registry()
        self.assertEqual([j["job_id"] for j in registry["active_jobs"]], [])
        self.assertIn("lifecycle", [j["job_id"] for j in registry["completed_jobs"]])

    def test_duplicate_job_id_is_rejected(self):
        self.project.add_active_job("dupe", pid=os.getpid(),
                                    heartbeat_at=__import__("datetime").datetime.now(
                                        __import__("datetime").timezone.utc).isoformat())
        proc = self.run_monitored("dupe", "print('should not run')")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("DUPLICATE JOB ID", proc.stderr)
        self.assertFalse((self.project.path / ".agent-run" / "jobs" / "dupe" / "stdout.log").exists())

    def test_stale_job_registration_is_diagnosed(self):
        self.project.add_active_job("stale", pid=999999, state="progressing",
                                    heartbeat_at="2020-01-01T00:00:00+00:00")
        proc = self.run_monitored("stale", "print('blocked')")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("STALE REGISTRATION", proc.stderr)
        self.assertIn("--reclaim-stale", proc.stderr)

    def test_stale_registration_can_be_reclaimed_explicitly(self):
        self.project.add_active_job("stale2", pid=999999, heartbeat_at="2020-01-01T00:00:00+00:00")
        proc = self.run_monitored("stale2", "print('reclaimed')", extra=["--reclaim-stale"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("STALE REGISTRATION", proc.stderr)
        self.assertIn("reclaimed", self.record("stale2")["stdout_tail"])

    def test_registration_exists_while_the_job_runs(self):
        """A crash mid-run must still leave the job discoverable in the registry."""
        args = [
            sys.executable, str(RUN_MONITORED), "--job-id", "midrun",
            "--classification", "exploratory", "--no-progress-timeout", "30",
            "--total-timeout", "30", "--heartbeat-interval", "1", "--",
            sys.executable, "-c", CHILD_SLEEP,
        ]
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project.path)
        env.update(GIT_ENV)
        proc = subprocess.Popen(args, cwd=str(self.project.path), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 15
            active = []
            while time.monotonic() < deadline:
                active = [j["job_id"] for j in self.registry()["active_jobs"]]
                if active:
                    break
                time.sleep(0.1)
            self.assertIn("midrun", active)
        finally:
            proc.send_signal(signal.SIGINT)
            proc.communicate(timeout=30)


class TestProvenanceAndRecovery(RunnerTestCase):
    def test_frozen_job_records_exact_sha(self):
        sha = self.project.head_sha()
        proc = self.run_monitored("frozen", "print('frozen run')", classification="frozen_acceptance")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        record = self.record("frozen")
        self.assertEqual(record["git_sha"], sha)
        self.assertEqual(record["classification"], "frozen_acceptance")
        self.assertEqual(record["command"][-1], "print('frozen run')")
        self.assertEqual(record["cwd"], str(self.project.path))
        self.assertTrue(record["started_at"])
        self.assertTrue(record["finished_at"])

    def test_frozen_job_flags_a_dirty_worktree(self):
        self.project.touch("uncommitted.py", "print(1)\n")
        self.run_monitored("frozen-dirty", "print('x')", classification="frozen_acceptance")
        record = self.record("frozen-dirty")
        self.assertFalse(record["worktree_clean_at_start"])
        self.assertIn("DIRTY_WORKTREE", record["frozen_integrity"])

    def test_interruption_leaves_a_recoverable_job_record(self):
        args = [
            sys.executable, str(RUN_MONITORED), "--job-id", "interrupted",
            "--classification", "exploratory", "--no-progress-timeout", "60",
            "--total-timeout", "60", "--heartbeat-interval", "1", "--grace-period", "1", "--",
            sys.executable, "-c", CHILD_SLEEP,
        ]
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project.path)
        env.update(GIT_ENV)
        proc = subprocess.Popen(args, cwd=str(self.project.path), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(2.0)
        proc.send_signal(signal.SIGINT)
        _, stderr = proc.communicate(timeout=30)

        self.assertEqual(proc.returncode, 130, stderr)
        record = self.record("interrupted")
        self.assertEqual(record["state"], "interrupted")
        self.assertTrue(record["recoverable"])
        self.assertTrue(record["process_group_terminated"])
        self.assertEqual(record["survivors_after_termination"], [])
        self.assertTrue(record["finished_at"])
        self.assertIn("interrupted", [j["job_id"] for j in self.registry()["completed_jobs"]])

    def test_missing_child_command_is_a_usage_error(self):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project.path)
        proc = subprocess.run(
            [sys.executable, str(RUN_MONITORED), "--job-id", "x", "--classification", "exploratory"],
            capture_output=True, text=True, env=env, cwd=str(self.project.path), timeout=30, check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no child command", proc.stderr)

    def test_unstartable_child_is_recorded_not_crashed(self):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project.path)
        env.update(GIT_ENV)
        proc = subprocess.run(
            [sys.executable, str(RUN_MONITORED), "--job-id", "nosuch", "--classification", "exploratory",
             "--", "definitely-not-a-real-binary-xyz"],
            capture_output=True, text=True, env=env, cwd=str(self.project.path), timeout=30, check=False,
        )
        self.assertEqual(proc.returncode, 2)
        record = self.record("nosuch")
        self.assertEqual(record["state"], "child_failure")
        self.assertIn("could not start child", record["error"])

    def test_heartbeat_interval_is_clamped_to_thirty_seconds(self):
        self.run_monitored("clamped", "print('x')", heartbeat=600.0)
        self.assertLessEqual(self.record("clamped")["heartbeat_interval_s"], 30.0)


if __name__ == "__main__":
    unittest.main()
