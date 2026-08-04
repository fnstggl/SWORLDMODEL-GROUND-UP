"""Direct tests for every control path in .claude/hooks/gate.py.

Each test pipes a synthetic hook event into the real dispatcher and asserts on
the real response. Both the allow path and the block path are covered for every
configured event.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import Project, run_gate  # noqa: E402


class GateTestCase(unittest.TestCase):
    def setUp(self):
        self.project = Project.create()
        self.addCleanup(self.project.destroy)

    def gate(self, event):
        return run_gate(self.project, event)


# ---------------------------------------------------------------------------
# SessionStart
# ---------------------------------------------------------------------------


class TestSessionStart(GateTestCase):
    EVENT = {"hook_event_name": "SessionStart", "source": "startup", "session_id": "s1"}

    def test_valid_state_produces_concise_context(self):
        result = self.gate(self.EVENT)
        self.assertEqual(result.exit_code, 0)
        context = result.additional_context
        self.assertTrue(context, "SessionStart must inject additionalContext")
        for expected in ("DURABLE GOAL", "MODE:", "NEXT ACTION", "COMPLETION ALLOWED",
                         "ACTIVE BACKGROUND JOBS", "OPEN FINDINGS", "GIT:"):
            self.assertIn(expected, context)
        self.assertLess(len(context), 4200, "SessionStart context must stay compact")

    def test_reports_master_directive_not_loaded_while_pending(self):
        context = self.gate(self.EVENT).additional_context
        self.assertIn("Master directive not loaded. Do not begin production implementation.", context)

    def test_reports_highest_leverage_blocker_and_active_jobs(self):
        self.project.set_mode("implementation", highest_leverage_blocker="runtime clock drift")
        self.project.add_active_job("corpus-1", classification="frozen_acceptance")
        context = self.gate(self.EVENT).additional_context
        self.assertIn("runtime clock drift", context)
        self.assertIn("corpus-1", context)

    def test_missing_optional_file_does_not_crash(self):
        (self.project.agent_run / "CRITICAL_PATH.md").unlink()
        (self.project.agent_run / "BLOCKERS.md").unlink()
        result = self.gate(self.EVENT)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("DURABLE GOAL", result.additional_context)

    def test_malformed_critical_state_produces_explicit_warning(self):
        self.project.write_raw("RUN_STATE.json", "{ this is not json")
        result = self.gate(self.EVENT)
        self.assertEqual(result.exit_code, 0, "SessionStart must fail safe, never wedge the session")
        self.assertIn("CRITICAL", result.additional_context)
        self.assertIn("RUN_STATE.json", result.additional_context)
        self.assertIn("systemMessage", result.json)

    def test_unsupported_mode_is_surfaced_not_swallowed(self):
        self.project.set_mode("not_a_real_mode")
        result = self.gate(self.EVENT)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("unsupported mode", result.additional_context)


# ---------------------------------------------------------------------------
# PreToolUse
# ---------------------------------------------------------------------------


def edit_event(path, tool="Edit"):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"file_path": path}}


def bash_event(command, **tool_input):
    payload = {"command": command}
    payload.update(tool_input)
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": payload}


class TestPreToolUse(GateTestCase):
    def assert_denied(self, result, *fragments):
        self.assertTrue(result.denied, f"expected deny, got {result!r}")
        reason = result.permission_reason
        self.assertIn("BLOCKED:", reason)
        self.assertIn("GOVERNING STATE:", reason)
        self.assertIn("SAFE ALTERNATIVE:", reason)
        for fragment in fragments:
            self.assertIn(fragment, reason)

    def assert_allowed(self, result):
        self.assertEqual(result.exit_code, 0, f"expected allow, got {result!r}")
        self.assertNotEqual(result.permission_decision, "deny", f"expected allow, got {result!r}")

    # -- allow paths ----------------------------------------------------

    def test_ordinary_edit_allowed_outside_freeze(self):
        self.project.set_mode("implementation")
        self.assert_allowed(self.gate(edit_event("sworldmodel/kernel.py")))

    def test_read_only_git_commands_allowed(self):
        self.project.set_mode("implementation")
        for command in ("git status --porcelain", "git log --oneline -5", "git diff HEAD~1",
                        "git rev-parse HEAD", "git show HEAD:README.md"):
            with self.subTest(command=command):
                self.assert_allowed(self.gate(bash_event(command)))

    def test_monitored_long_job_allowed(self):
        self.project.set_mode("implementation")
        command = (".claude/tools/run_monitored.py --job-id corpus-1 --classification exploratory "
                   "-- python3 run_worlds.py --corpus all")
        self.assert_allowed(self.gate(bash_event(f"python3 {command}")))

    def test_short_harmless_background_command_allowed(self):
        self.project.set_mode("implementation")
        self.assert_allowed(self.gate(bash_event("echo warming &")))

    def test_agent_run_state_edit_allowed_during_bootstrap(self):
        self.assert_allowed(self.gate(edit_event(".agent-run/RUN_STATE.json")))

    # -- block paths ----------------------------------------------------

    def test_production_edit_blocked_during_freeze(self):
        self.project.set_mode("frozen_acceptance")
        self.assert_denied(self.gate(edit_event("sworldmodel/kernel.py")),
                           "frozen_acceptance", "production")

    def test_prompt_edit_blocked_during_freeze(self):
        self.project.set_mode("frozen_acceptance")
        self.assert_denied(self.gate(edit_event("sworldmodel/prompts/system.txt")), "frozen_acceptance")

    def test_evaluator_edit_blocked_during_freeze(self):
        self.project.set_mode("frozen_acceptance")
        self.assert_denied(self.gate(edit_event("evaluation/score_runs.py")),
                           "frozen_acceptance", "evaluator")

    def test_fixture_edit_blocked_during_freeze(self):
        self.project.set_mode("frozen_acceptance")
        self.assert_denied(self.gate(edit_event("worlds/committee.json")), "frozen_acceptance")

    def test_deleting_acceptance_artifacts_blocked(self):
        self.project.set_mode("frozen_acceptance")
        self.assert_denied(self.gate(bash_event("rm -rf .agent-run/receipts")), "deletion")

    def test_deleting_evidence_blocked_in_every_mode(self):
        for mode in ("hook_bootstrap", "implementation", "frozen_acceptance", "ready_for_master"):
            for target in (".agent-run/receipts", ".agent-run/RUN_STATE.json",
                           ".agent-run/FAILURE_LEDGER.jsonl", ".claude/hooks/gate.py"):
                with self.subTest(mode=mode, target=target):
                    self.project.set_mode(mode)
                    self.assert_denied(self.gate(bash_event(f"rm -rf {target}")), "deletion")

    def test_ephemeral_job_scratch_may_be_cleaned_outside_a_freeze(self):
        """The runner recreates .agent-run/jobs/; the durable record lives in the registry."""
        for mode in ("hook_bootstrap", "implementation"):
            with self.subTest(mode=mode):
                self.project.set_mode(mode)
                self.assert_allowed(self.gate(bash_event("rm -rf .agent-run/jobs/old-run")))

    def test_job_scratch_is_protected_during_a_freeze(self):
        self.project.set_mode("frozen_acceptance")
        self.assert_denied(self.gate(bash_event("rm -rf .agent-run/jobs/accept-1")),
                           "frozen acceptance job artifacts")

    def test_git_reset_hard_blocked(self):
        self.project.set_mode("implementation")
        self.assert_denied(self.gate(bash_event("git reset --hard HEAD~3")), "git reset")

    def test_destructive_git_clean_blocked(self):
        self.project.set_mode("implementation")
        self.assert_denied(self.gate(bash_event("git clean -fdx")), "git clean")

    def test_force_push_blocked(self):
        self.project.set_mode("implementation")
        for command in ("git push --force origin main", "git push -f origin main",
                        "git push origin +main:main", "git push --force-with-lease"):
            with self.subTest(command=command):
                self.assert_denied(self.gate(bash_event(command)), "force push")

    def test_destructive_checkout_and_restore_blocked(self):
        self.project.set_mode("implementation")
        for command in ("git checkout -- sworldmodel/", "git restore sworldmodel/kernel.py",
                        "git stash drop", "git branch -D feature"):
            with self.subTest(command=command):
                self.assert_denied(self.gate(bash_event(command)))

    def test_upstream_modification_blocked(self):
        self.project.set_mode("implementation")
        self.project.write_state("UPSTREAM_PROTECTED_PATHS.json", {
            "schema_version": 1, "status": "INITIALIZED",
            "repositories": [{"name": "concordia", "commit": "abc123"}],
            "protected_paths": ["vendor/concordia", "vendor/agentsociety/**"],
        })
        self.assert_denied(self.gate(edit_event("vendor/concordia/engine.py")), "upstream")
        self.assert_denied(self.gate(edit_event("vendor/agentsociety/sim/core.py")), "upstream")

    def test_external_upstream_checkout_write_blocked_in_every_mode(self):
        """Pinned checkouts OUTSIDE the repo are inviolable too.

        Regression for the adversarial-review HIGH finding: the real engine
        checkouts classified as 'external', which no mode blocks, so an
        editable-install source edit produced no repo diff and fired no hook.
        """
        import tempfile
        checkout = tempfile.mkdtemp(prefix="fake-upstream-")
        self.addCleanup(lambda: __import__("shutil").rmtree(checkout, ignore_errors=True))
        self.project.write_state("UPSTREAM_PROTECTED_PATHS.json", {
            "schema_version": 1, "status": "INITIALIZED",
            "repositories": [
                {"name": "concordia", "local_checkout": checkout,
                 "baseline_sha_at_initialization": "abc123"}
            ],
            "protected_paths": [],
        })
        for mode in ("implementation", "frozen_acceptance"):
            with self.subTest(mode=mode):
                if mode == "frozen_acceptance":
                    self.project.set_mode(mode, frozen_sha="deadbeef")
                else:
                    self.project.set_mode(mode)
                self.assert_denied(
                    self.gate(edit_event(f"{checkout}/concordia/engine.py")), "upstream")
        # No over-blocking: an unrelated external path stays allowed.
        self.project.set_mode("implementation")
        self.assert_allowed(self.gate(edit_event("/tmp/unrelated-scratch.txt")))

    def test_audit_exempt_protected_path_still_blocked_for_writes(self):
        """audit_exempt affects only the validator's branch-diff audit."""
        self.project.set_mode("implementation")
        self.project.write_state("UPSTREAM_PROTECTED_PATHS.json", {
            "schema_version": 1, "status": "INITIALIZED", "repositories": [],
            "protected_paths": [{"path": "third_party/LOCK.json", "audit_exempt": True}],
        })
        self.assert_denied(self.gate(edit_event("third_party/LOCK.json")), "upstream")

    def test_frozen_acceptance_blocks_test_edits(self):
        """Tests (including tests/fixtures/**) are frozen during acceptance."""
        self.project.set_mode("frozen_acceptance", frozen_sha="deadbeef")
        self.assert_denied(self.gate(edit_event("tests/test_semantics.py")), "frozen")
        self.assert_denied(
            self.gate(edit_event("tests/fixtures/best_action/individual_reply.yaml")), "frozen")

    def test_hook_control_edit_blocked_outside_maintenance_modes(self):
        self.project.set_mode("implementation")
        self.assert_denied(self.gate(edit_event(".claude/hooks/gate.py")), "hook-control")
        self.assert_denied(self.gate(edit_event(".claude/settings.json")), "hook-control")
        self.assert_denied(self.gate(edit_event("CLAUDE.md")), "hook-control")

    def test_hook_control_edit_allowed_in_each_maintenance_mode(self):
        for mode in ("hook_bootstrap", "hook_live_verification", "hook_maintenance"):
            with self.subTest(mode=mode):
                self.project.set_mode(mode)
                self.assert_allowed(self.gate(edit_event(".claude/hooks/gate.py")))

    def test_unmonitored_background_job_blocked(self):
        self.project.set_mode("implementation")
        cases = [
            bash_event("nohup python3 run_worlds.py > out.log 2>&1 &"),
            bash_event("python3 run_worlds.py &"),
            bash_event("setsid python3 run_worlds.py"),
            bash_event("python3 run_worlds.py", run_in_background=True),
            bash_event("tmux new-session -d 'python3 run_worlds.py'"),
        ]
        for event in cases:
            with self.subTest(command=event["tool_input"]["command"]):
                self.assert_denied(self.gate(event), "run_monitored.py")

    def test_long_running_workload_blocked_even_in_foreground(self):
        self.project.set_mode("implementation")
        for command in ("python3 run_worlds.py --corpus all",
                        "python3 bench_runtime.py",
                        "python3 run_simulation.py --n-agents 1000",
                        "python3 scale_test.py",
                        "pytest tests/ --load-test"):
            with self.subTest(command=command):
                self.assert_denied(self.gate(bash_event(command)), "run_monitored.py")

    def test_multi_engine_suite_battery_requires_monitor(self):
        """Regression for the silent-agent-pause incident: the engine DoD
        battery ran as bare foreground pytest with no registry entry,
        heartbeat, progress, or timeout. Two or more distinct engine suite
        directories in one pytest invocation now require the monitor."""
        self.project.set_mode("implementation")
        dod = ("/home/user/engine-env/bin/python -m pytest tests/engine_checkpoint "
               "tests/engine_distributed tests/engine_counterfactuals "
               "tests/engine_baseline tests/engine_contracts -q")
        self.assert_denied(self.gate(bash_event(dod)), "run_monitored.py")
        self.assert_denied(self.gate(bash_event(
            "pytest tests/engine_baseline tests/engine_contracts -q")), "run_monitored.py")
        # The exact rejected incident shape (trailing pipe) is still caught.
        self.assert_denied(self.gate(bash_event(dod + " 2>&1 | tail -5")), "run_monitored.py")
        # env-prefixed form is still caught.
        self.assert_denied(self.gate(bash_event(
            "env RAY_DEDUP_LOGS=0 python3 -m pytest tests/engine_baseline "
            "tests/engine_contracts -q")), "run_monitored.py")

    def test_single_engine_suite_pytest_stays_direct(self):
        """Quick iteration must not be taxed: one suite directory, or many
        files within one suite, is not a battery."""
        self.project.set_mode("implementation")
        self.assert_allowed(self.gate(bash_event(
            "/home/user/engine-env/bin/python -m pytest tests/engine_baseline -q")))
        self.assert_allowed(self.gate(bash_event(
            "pytest tests/engine_baseline/test_agency_guard.py "
            "tests/engine_baseline/test_builder_contracts.py -q")))

    def test_monitored_or_bounded_receipt_battery_allowed(self):
        self.project.set_mode("implementation")
        self.assert_allowed(self.gate(bash_event(
            "python3 .claude/tools/run_monitored.py --job-id dod --classification "
            "exploratory --no-progress-timeout 240 --total-timeout 480 -- "
            "/home/user/engine-env/bin/python -m pytest tests/engine_baseline "
            "tests/engine_contracts -q")))
        # record_receipt --run with an explicit --timeout is bounded and
        # evidence-producing; the receipt protocol wraps the battery.
        self.assert_allowed(self.gate(bash_event(
            "python3 .claude/tools/record_receipt.py --task-id t --timeout 600 --run -- "
            "/home/user/engine-env/bin/python -m pytest tests/engine_baseline "
            "tests/engine_contracts -q")))

    def test_receipt_exemption_is_per_segment_and_needs_timeout(self):
        self.project.set_mode("implementation")
        # A bounded receipt run cannot smuggle a bare battery behind ';'.
        self.assert_denied(self.gate(bash_event(
            "python3 .claude/tools/record_receipt.py --task-id t --timeout 5 --run -- true; "
            "pytest tests/engine_baseline tests/engine_contracts -q")), "run_monitored.py")
        # record_receipt's --timeout default is None: without the flag the
        # child is unbounded, so the exemption must not apply.
        self.assert_denied(self.gate(bash_event(
            "python3 .claude/tools/record_receipt.py --task-id t --run -- "
            "python3 -m pytest tests/engine_baseline tests/engine_contracts -q")), "run_monitored.py")

    def test_shell_redirection_into_protected_path_blocked(self):
        self.project.set_mode("implementation")
        for command in ("echo broken > .claude/settings.json",
                        "echo broken >> .claude/settings.json",
                        "cat x 2> .claude/settings.json"):
            with self.subTest(command=command):
                self.assert_denied(self.gate(bash_event(command)), "hook-control")

    def test_trailing_angle_bracket_does_not_capture_the_next_line(self):
        """An e-mail address in a heredoc must not read as a redirect target."""
        self.project.set_mode("implementation")
        commit = (
            "git commit -F - <<'MSG'\n"
            "Add a thing\n"
            "\n"
            "Co-Authored-By: Someone <someone@example.invalid>\n"
            "Claude-Session: https://example.invalid/session\n"
            "MSG"
        )
        self.assert_allowed(self.gate(bash_event(commit)))

    def test_arrow_in_quoted_code_is_not_a_redirect(self):
        """'->' inside a quoted program must not be read as a shell redirect."""
        self.project.set_mode("implementation")
        self.assert_allowed(self.gate(bash_event(
            "python3 -c \"print(f'{a} -> {b}')\"")))
        self.assert_allowed(self.gate(bash_event("python3 -c 'x = lambda v: v => 1'")))

    def test_quoted_mention_of_a_write_is_not_a_write(self):
        """Text that merely *contains* shell-write syntax must not be blocked.

        Every case here denied a harmless read-only command during live hook
        verification, back when write targets were found by matching raw text.
        """
        self.project.set_mode("frozen_acceptance")
        for command in (
            'echo "VAR=${FOO:-<unset>}"',
            'python3 -c "print(1 if 2 > 1 else 0)"',
            "grep -n 'tee|sed -i|truncate' tests/control_plane/test_gate.py",
            'echo "run: sed -i s/a/b/ sworldmodel/kernel.py"',
            "python3 -c 'print(\"a > b\")'",
        ):
            with self.subTest(command=command):
                self.assert_allowed(self.gate(bash_event(command)))

    def test_heredoc_body_is_data_not_shell(self):
        self.project.set_mode("frozen_acceptance")
        command = (
            "python3 - <<'PY'\n"
            "open('sworldmodel/kernel.py')\n"
            "print('sed -i s/a/b/ sworldmodel/kernel.py')\n"
            "print('redirect > sworldmodel/kernel.py')\n"
            "PY"
        )
        self.assert_allowed(self.gate(bash_event(command)))

    def test_in_place_edit_of_protected_paths_blocked_outside_a_freeze(self):
        """Outside a freeze only control-plane and upstream paths block.

        A mis-parsed target silently degrades to the 'production' category,
        which is allowed in `implementation` -- so parsing the real file operand
        is what makes these rules enforceable at all.
        """
        self.project.set_mode("implementation")
        self.project.write_state("UPSTREAM_PROTECTED_PATHS.json", {
            "schema_version": 1, "status": "INITIALIZED",
            "repositories": [{"name": "concordia", "commit": "abc123"}],
            "protected_paths": ["vendor/concordia"],
        })
        for command, fragment in (
            ("sed -i 's/deny/allow/' .claude/hooks/gate.py", "hook-control"),
            ("sed -i 's/a/b/' .claude/settings.json", "hook-control"),
            ("sed -i.bak -e s/a/b/ CLAUDE.md", "hook-control"),
            ("python3 gen.py | tee .claude/settings.json", "hook-control"),
            # Caught one rule earlier, by the evidence-deletion guard.
            ("truncate -s 0 .claude/settings.json", "deletion of control plane state"),
            ("sed -i 's/a/b/' vendor/concordia/engine.py", "upstream"),
        ):
            with self.subTest(command=command):
                self.assert_denied(self.gate(bash_event(command)), fragment)

    def test_quoted_redirect_target_is_still_detected(self):
        self.project.set_mode("implementation")
        for command in ('echo broken > ".claude/settings.json"',
                        "echo broken > '.claude/settings.json'",
                        "echo broken >.claude/settings.json"):
            with self.subTest(command=command):
                self.assert_denied(self.gate(bash_event(command)), "hook-control")

    def test_read_only_sed_is_not_a_write(self):
        self.project.set_mode("implementation")
        for command in ("sed -n 1,5p .claude/settings.json",
                        "sed -e s/a/b/ .claude/settings.json"):
            with self.subTest(command=command):
                self.assert_allowed(self.gate(bash_event(command)))

    def test_file_descriptor_duplication_is_not_a_write(self):
        self.project.set_mode("frozen_acceptance")
        for command in ("pytest -q 2>&1", "python3 x.py 2>&1 | head -5"):
            with self.subTest(command=command):
                self.assert_allowed(self.gate(bash_event(command)))

    def test_production_edit_blocked_during_ready_for_master(self):
        self.project.set_mode("ready_for_master")
        result = self.gate(edit_event("sworldmodel/kernel.py"))
        self.assert_denied(result, "ready_for_master")
        self.assertIn("master-context initialization handshake", result.permission_reason)

    def test_master_directive_and_state_writable_during_ready_for_master(self):
        self.project.set_mode("ready_for_master")
        self.assert_allowed(self.gate(edit_event("docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md")))
        self.assert_allowed(self.gate(edit_event(".agent-run/ARCHITECTURE.md")))

    def test_malformed_state_fails_closed(self):
        self.project.write_raw("RUN_STATE.json", "{oops")
        result = self.gate(edit_event("sworldmodel/kernel.py"))
        self.assertTrue(result.denied, "a safety gate must fail closed on malformed state")
        self.assertIn("RUN_STATE.json", result.permission_reason)


# ---------------------------------------------------------------------------
# TaskCompleted
# ---------------------------------------------------------------------------


def completed_event(task_id, title=""):
    return {"hook_event_name": "TaskCompleted", "task_id": task_id, "task_title": title}


class TestTaskCompleted(GateTestCase):
    def base_task(self, **overrides):
        task = {
            "id": "t1",
            "subject": "implement thing",
            "owner": "implementation-agent",
            "owner_type": "subagent",
            "status": "in_progress",
            "dependencies": [],
            "required_artifacts": [],
            "required_receipts": [{"task_id": "t1", "command": "pytest -q", "must_pass": True}],
            "required_validation_commands": [],
            "blocking_critical_findings": [],
        }
        task.update(overrides)
        return task

    def test_valid_current_sha_receipt_allows_completion(self):
        self.project.set_tasks([self.base_task()])
        self.project.add_receipt("t1", command="pytest -q", exit_code=0, valid=True)
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 0, result)

    def test_missing_receipt_blocks(self):
        self.project.set_tasks([self.base_task()])
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("no receipt found", result.stderr)

    def test_failed_receipt_blocks(self):
        self.project.set_tasks([self.base_task()])
        self.project.add_receipt("t1", command="pytest -q", exit_code=1, valid=True)
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("did not pass", result.stderr)

    def test_receipt_marked_invalid_blocks(self):
        self.project.set_tasks([self.base_task()])
        self.project.add_receipt("t1", command="pytest -q", exit_code=0, valid=False)
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("did not pass", result.stderr)

    def test_stale_sha_receipt_blocks(self):
        self.project.set_tasks([self.base_task()])
        stale = self.project.head_sha()
        self.project.add_receipt("t1", command="pytest -q", sha=stale)
        self.project.commit_all("moved on")
        self.assertNotEqual(stale, self.project.head_sha())
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("stale", result.stderr)
        self.assertIn(stale[:12], result.stderr)

    def test_missing_artifact_blocks(self):
        self.project.set_tasks([self.base_task(required_artifacts=["artifacts/report.json"])])
        self.project.add_receipt("t1", command="pytest -q")
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("required artifact is missing", result.stderr)

    def test_present_artifact_allows(self):
        self.project.set_tasks([self.base_task(required_artifacts=["artifacts/report.json"])])
        self.project.touch("artifacts/report.json", "{}\n")
        self.project.add_receipt("t1", command="pytest -q")
        self.assertEqual(self.gate(completed_event("t1")).exit_code, 0)

    def test_missing_review_artifact_blocks(self):
        self.project.set_tasks([self.base_task(required_review_artifacts=["reviews/adversarial.md"])])
        self.project.add_receipt("t1", command="pytest -q")
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("required review artifact is missing", result.stderr)

    def test_unresolved_critical_finding_blocks(self):
        self.project.set_tasks([self.base_task(blocking_critical_findings=["F-17 clock drift"])])
        self.project.add_receipt("t1", command="pytest -q")
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("F-17", result.stderr)

    def test_required_validation_command_without_receipt_blocks(self):
        self.project.set_tasks([self.base_task(required_receipts=[],
                                               required_validation_commands=["pytest tests/kernel -q"])])
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("pytest tests/kernel -q", result.stderr)

    def test_dirty_worktree_blocks_when_contract_requires_clean(self):
        self.project.set_tasks([self.base_task(requires_clean_worktree=True)])
        self.project.add_receipt("t1", command="pytest -q")
        self.project.touch("untracked_change.py", "print(1)\n")
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("clean worktree", result.stderr)

    def test_unknown_task_blocks_during_implementation(self):
        self.project.set_mode("implementation")
        self.project.set_tasks([])
        result = self.gate(completed_event("ghost-task"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("not in the task graph", result.stderr)

    def test_unknown_task_allowed_with_explicit_note_during_bootstrap(self):
        self.project.set_tasks([])
        result = self.gate(completed_event("ad-hoc-task"))
        self.assertEqual(result.exit_code, 0)
        self.assertIn("not in TASK_GRAPH.json", result.json.get("systemMessage", ""))
        self.assertIn("No evidence was verified", result.json.get("systemMessage", ""))

    def test_unknown_task_policy_is_honoured_explicitly(self):
        self.project.set_tasks([], unknown_task_policy="block")
        self.assertEqual(self.gate(completed_event("ad-hoc-task")).exit_code, 2)

    def test_task_matched_by_title_when_id_absent(self):
        self.project.set_tasks([self.base_task(required_receipts=[])])
        result = self.gate({"hook_event_name": "TaskCompleted", "task_title": "implement thing"})
        self.assertEqual(result.exit_code, 0)

    def test_missing_identifier_blocks(self):
        result = self.gate({"hook_event_name": "TaskCompleted"})
        self.assertEqual(result.exit_code, 2)
        self.assertIn("no identifier", result.stderr)

    def test_malformed_receipt_is_surfaced_not_ignored(self):
        self.project.set_tasks([self.base_task()])
        (self.project.agent_run / "receipts" / "broken.json").write_text("{not json", encoding="utf-8")
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("malformed", result.stderr)

    def test_malformed_task_graph_fails_closed(self):
        self.project.write_raw("TASK_GRAPH.json", "{[")
        result = self.gate(completed_event("t1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("TASK_GRAPH.json", result.stderr)


# ---------------------------------------------------------------------------
# TeammateIdle
# ---------------------------------------------------------------------------


def idle_event(name):
    return {"hook_event_name": "TeammateIdle", "teammate_name": name}


class TestTeammateIdle(GateTestCase):
    def test_teammate_with_incomplete_owned_task_is_blocked(self):
        self.project.set_tasks([{
            "id": "t1", "owner": "builder", "owner_type": "teammate", "status": "in_progress",
            "required_artifacts": [], "required_receipts": [],
        }])
        result = self.gate(idle_event("builder"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("still in_progress", result.stderr)
        self.assertIn("SAFE ALTERNATIVE:", result.stderr)

    def test_teammate_owing_artifact_is_blocked(self):
        self.project.set_tasks([{
            "id": "t1", "owner": "builder", "owner_type": "teammate", "status": "pending",
            "deliverable": "implementation", "required_artifacts": ["src/thing.py"],
        }])
        result = self.gate(idle_event("builder"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("owes artifact", result.stderr)
        self.assertIn("analysis alone does not satisfy it", result.stderr)

    def test_teammate_owing_receipt_is_blocked(self):
        self.project.set_tasks([{
            "id": "t1", "owner": "builder", "owner_type": "teammate", "status": "pending",
            "required_artifacts": [], "required_validation_commands": ["pytest -q"],
        }])
        result = self.gate(idle_event("builder"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("owes a passing test receipt", result.stderr)

    def test_teammate_with_unresolved_critical_finding_is_blocked(self):
        self.project.set_tasks([{
            "id": "t1", "owner": "builder", "owner_type": "teammate", "status": "pending",
            "required_artifacts": [], "assigned_critical_findings": ["F-3"],
        }])
        result = self.gate(idle_event("builder"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("F-3", result.stderr)

    def test_teammate_with_complete_task_is_allowed(self):
        self.project.set_tasks([{
            "id": "t1", "owner": "builder", "owner_type": "teammate", "status": "complete",
            "required_artifacts": ["src/never_written.py"],
        }])
        self.assertEqual(self.gate(idle_event("builder")).exit_code, 0)

    def test_reviewer_with_delivered_report_is_allowed(self):
        self.project.touch("reviews/review.md", "# findings\n")
        self.project.set_tasks([{
            "id": "r1", "owner": "reviewer-1", "owner_type": "reviewer", "status": "in_progress",
            "report_artifact": "reviews/review.md",
        }])
        self.assertEqual(self.gate(idle_event("reviewer-1")).exit_code, 0)

    def test_reviewer_without_delivered_report_is_blocked(self):
        self.project.set_tasks([{
            "id": "r1", "owner": "reviewer-1", "owner_type": "reviewer", "status": "in_progress",
            "report_artifact": "reviews/review.md",
        }])
        result = self.gate(idle_event("reviewer-1"))
        self.assertEqual(result.exit_code, 2)
        self.assertIn("has not delivered its report", result.stderr)

    def test_teammate_with_no_assignment_is_allowed(self):
        self.project.set_tasks([{"id": "t1", "owner": "someone-else", "status": "in_progress"}])
        self.assertEqual(self.gate(idle_event("free-agent")).exit_code, 0)

    def test_unnamed_teammate_is_allowed(self):
        self.assertEqual(self.gate({"hook_event_name": "TeammateIdle"}).exit_code, 0)

    def test_does_not_trap_teammate_whose_work_is_all_done(self):
        self.project.touch("src/done.py")
        self.project.set_tasks([
            {"id": "a", "owner": "builder", "status": "complete", "required_artifacts": ["src/done.py"]},
            {"id": "b", "owner": "builder", "status": "abandoned", "required_artifacts": ["src/gone.py"]},
        ])
        self.assertEqual(self.gate(idle_event("builder")).exit_code, 0)


# ---------------------------------------------------------------------------
# SubagentStop
# ---------------------------------------------------------------------------


def subagent_event(agent_type, stop_hook_active=False, **extra):
    event = {"hook_event_name": "SubagentStop", "agent_type": agent_type,
             "stop_hook_active": stop_hook_active, "last_assistant_message": "done"}
    event.update(extra)
    return event


class TestSubagentStop(GateTestCase):
    def test_protected_agent_missing_output_is_blocked(self):
        self.project.set_mode("implementation")
        self.project.set_tasks([{
            "id": "t1", "owner": "implementation-agent", "status": "in_progress",
            "required_artifacts": ["src/thing.py"],
        }])
        result = self.gate(subagent_event("implementation-agent"))
        self.assertEqual(result.decision, "block")
        self.assertIn("missing output", result.reason)
        self.assertIn("Analysis alone does not", result.reason)

    def test_protected_agent_without_passing_receipt_is_blocked(self):
        self.project.set_mode("implementation")
        self.project.touch("src/thing.py")
        self.project.set_tasks([{
            "id": "t1", "owner": "test-watchdog", "status": "in_progress",
            "required_artifacts": ["src/thing.py"], "required_validation_commands": ["pytest -q"],
        }])
        result = self.gate(subagent_event("test-watchdog"))
        self.assertEqual(result.decision, "block")
        self.assertIn("no passing receipt", result.reason)

    def test_completed_implementation_agent_is_allowed(self):
        self.project.set_mode("implementation")
        self.project.touch("src/thing.py")
        self.project.set_tasks([{
            "id": "t1", "owner": "implementation-agent", "status": "complete",
            "required_artifacts": ["src/thing.py"],
        }])
        result = self.gate(subagent_event("implementation-agent"))
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.decision)

    def test_protected_agent_with_no_contract_blocked_during_implementation(self):
        self.project.set_mode("implementation")
        result = self.gate(subagent_event("implementation-agent"))
        self.assertEqual(result.decision, "block")
        self.assertIn("no assigned contract", result.reason)

    def test_read_only_reviewers_may_return_findings(self):
        self.project.set_mode("implementation")
        self.project.set_tasks([{
            "id": "t1", "owner": "adversarial-reviewer", "status": "in_progress",
            "required_artifacts": ["never/written.md"],
        }])
        for agent in ("investigation-agent", "adversarial-reviewer", "final-adjudicator"):
            with self.subTest(agent=agent):
                result = self.gate(subagent_event(agent))
                self.assertEqual(result.exit_code, 0)
                self.assertIsNone(result.decision)

    def test_unrelated_agent_types_are_untouched(self):
        self.project.set_mode("implementation")
        for agent in ("general-purpose", "Explore", "Plan", "code-reviewer"):
            with self.subTest(agent=agent):
                self.assertIsNone(self.gate(subagent_event(agent)).decision)

    def test_stop_hook_active_prevents_recursive_blocking(self):
        self.project.set_mode("implementation")
        self.project.set_tasks([{
            "id": "t1", "owner": "implementation-agent", "status": "in_progress",
            "required_artifacts": ["src/thing.py"],
        }])
        result = self.gate(subagent_event("implementation-agent", stop_hook_active=True))
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.decision)

    def test_malformed_state_fails_closed_for_protected_agent(self):
        self.project.write_raw("RUN_STATE.json", "nope")
        result = self.gate(subagent_event("implementation-agent"))
        self.assertEqual(result.decision, "block")


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------


def stop_event(stop_hook_active=False):
    return {"hook_event_name": "Stop", "stop_hook_active": stop_hook_active,
            "last_assistant_message": "I am done."}


class TestStop(GateTestCase):
    def test_bootstrap_cannot_stop_before_static_pass(self):
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("STATIC_PASS_LIVE_PENDING", result.reason)
        self.assertIn("SAFE ALTERNATIVE:", result.reason)
        self.assertIn("complete static hook validation", result.reason)

    def test_bootstrap_can_stop_at_static_pass_live_pending(self):
        self.project.set_bootstrap(overall="STATIC_PASS_LIVE_PENDING", static_tests="PASS",
                                   settings_validation="PASS", monitored_runner_tests="PASS")
        result = self.gate(stop_event())
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.decision)

    def test_live_verification_cannot_stop_before_full_pass(self):
        self.project.set_mode("hook_live_verification")
        self.project.set_bootstrap(overall="STATIC_PASS_LIVE_PENDING")
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("not PASS", result.reason)

    def test_live_verification_can_stop_at_pass(self):
        self.project.set_mode("hook_live_verification")
        self.project.set_bootstrap(overall="PASS")
        self.assertIsNone(self.gate(stop_event()).decision)

    def test_ready_for_master_can_stop(self):
        self.project.set_mode("ready_for_master")
        self.assertIsNone(self.gate(stop_event()).decision)

    def test_implementation_cannot_stop_with_incomplete_acceptance(self):
        self.project.set_mode("implementation")
        self.project.set_acceptance(overall="IN_PROGRESS",
                                    open_critical_findings=["F-1 nondeterministic scheduler"],
                                    gates={"kernel": "PASS", "societal": "NOT_RUN"})
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("F-1 nondeterministic scheduler", result.reason)
        self.assertIn("societal", result.reason)

    def test_implementation_can_stop_at_final_pass(self):
        self.project.set_mode("implementation")
        self.project.set_acceptance(overall="PASS")
        self.assertIsNone(self.gate(stop_event()).decision)

    def test_frozen_acceptance_cannot_stop_before_pass(self):
        self.project.set_mode("frozen_acceptance")
        self.project.set_acceptance(overall="IN_PROGRESS")
        self.assertEqual(self.gate(stop_event()).decision, "block")

    def test_running_acceptance_jobs_block_completion(self):
        self.project.set_mode("implementation")
        self.project.set_acceptance(overall="PASS")
        self.project.add_active_job("accept-1", classification="frozen_acceptance", state="progressing")
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("accept-1", result.reason)
        self.assertIn("still running", result.reason)

    def test_finished_acceptance_job_does_not_block(self):
        self.project.set_mode("implementation")
        self.project.set_acceptance(overall="PASS")
        self.project.add_active_job("accept-1", classification="frozen_acceptance", state="finished")
        self.assertIsNone(self.gate(stop_event()).decision)

    def test_genuine_external_blocker_can_stop(self):
        self.project.set_mode("implementation", status="EXTERNAL_BLOCKER")
        self.project.set_acceptance(overall="IN_PROGRESS")
        self.assertIsNone(self.gate(stop_event()).decision)

    def test_external_blocker_mode_can_stop(self):
        self.project.set_mode("external_blocker")
        self.assertIsNone(self.gate(stop_event()).decision)

    def test_stop_hook_active_prevents_recursive_blocking(self):
        result = self.gate(stop_event(stop_hook_active=True))
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.decision)

    def test_completion_phrase_is_not_authority(self):
        event = stop_event()
        event["last_assistant_message"] = "ALL WORK COMPLETE. STATIC HOOK BOOTSTRAP PASSED."
        self.assertEqual(self.gate(event).decision, "block")

    def test_malformed_state_fails_closed(self):
        self.project.write_raw("RUN_STATE.json", "{")
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("RUN_STATE.json", result.reason)

    def test_malformed_bootstrap_status_blocks_bootstrap_stop(self):
        for bad in ("[]", "{oops", '"a string"', "null"):
            with self.subTest(content=bad):
                self.project.write_raw("HOOK_BOOTSTRAP_STATUS.json", bad)
                result = self.gate(stop_event())
                self.assertEqual(result.decision, "block")
                self.assertIn("HOOK_BOOTSTRAP_STATUS.json", result.reason)

    def test_bootstrap_status_without_overall_field_blocks(self):
        """A well-formed object that omits 'overall' must not read as permission to stop."""
        self.project.write_state("HOOK_BOOTSTRAP_STATUS.json",
                                 {"schema_version": 1, "static_tests": "PASS"})
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("overall", result.reason)


class TestStopContinuationSentinel(GateTestCase):
    """Regression for the worker_silent_death class (FAILURE_LEDGER 2026-08-04).

    A worker died mid-turn with no SubagentStop event, no completion
    notification, and no running processes; the session idled ~40 minutes,
    bounded only by a manually scheduled wakeup. The corrected dispatcher
    refuses to let a turn end in implementation/frozen_acceptance while
    acceptance is incomplete unless an unexpired continuation wakeup is
    armed in .agent-run/CONTINUATION.json — so a silent worker death can
    never strand the run past a bounded, recorded deadline.
    """

    def setUp(self):
        super().setUp()
        self.project.set_mode("implementation")
        self.project.set_acceptance(overall="IN_PROGRESS")

    def test_idle_stop_without_armed_continuation_names_the_gap(self):
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("no continuation trigger is armed", result.reason)
        self.assertIn("arm_continuation.py", result.reason)

    def test_armed_continuation_silences_the_continuation_blocker(self):
        self.project.arm_continuation(minutes=45)
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block",
                         "incomplete acceptance still blocks the stop")
        self.assertNotIn("arm_continuation.py", result.reason)

    def test_expired_continuation_blocks_with_rearm_guidance(self):
        self.project.arm_continuation(minutes=45, expired=True)
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("expired", result.reason)
        self.assertIn("arm_continuation.py", result.reason)

    def test_malformed_continuation_is_explicit(self):
        self.project.write_raw("CONTINUATION.json", "{ not json")
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("CONTINUATION.json", result.reason)

    def test_missing_armed_until_field_is_malformed_not_armed(self):
        self.project.write_state("CONTINUATION.json", {"schema_version": 1, "reason": "x"})
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("CONTINUATION.json", result.reason)

    def test_acceptance_pass_does_not_require_a_continuation(self):
        self.project.set_acceptance(overall="PASS")
        self.assertIsNone(self.gate(stop_event()).decision)

    def test_frozen_acceptance_requires_a_continuation_too(self):
        self.project.set_mode("frozen_acceptance")
        result = self.gate(stop_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("arm_continuation.py", result.reason)


class TestSessionStartContinuationLine(GateTestCase):
    EVENT = {"hook_event_name": "SessionStart", "source": "startup", "session_id": "s1"}

    def test_unarmed_continuation_is_surfaced_in_implementation(self):
        self.project.set_mode("implementation")
        context = self.gate(self.EVENT).additional_context
        self.assertIn("CONTINUATION: NOT ARMED", context)
        self.assertIn("arm_continuation.py", context)

    def test_armed_continuation_is_reported_with_deadline_and_reason(self):
        self.project.set_mode("implementation")
        self.project.arm_continuation(minutes=45, reason="watching spoof-fix worker")
        context = self.gate(self.EVENT).additional_context
        self.assertIn("CONTINUATION: armed until", context)
        self.assertIn("watching spoof-fix worker", context)

    def test_bootstrap_mode_context_omits_the_continuation_line(self):
        context = self.gate(self.EVENT).additional_context
        self.assertNotIn("CONTINUATION:", context)


# ---------------------------------------------------------------------------
# StopFailure
# ---------------------------------------------------------------------------


class TestStopFailure(GateTestCase):
    DOCUMENTED_ERROR_TYPES = (
        "rate_limit", "overloaded", "authentication_failed", "oauth_org_not_allowed",
        "billing_error", "invalid_request", "model_not_found", "server_error",
        "max_output_tokens", "unknown",
    )

    def ledger(self):
        text = (self.project.agent_run / "FAILURE_LEDGER.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def test_every_documented_failure_class_is_recorded(self):
        for error_type in self.DOCUMENTED_ERROR_TYPES:
            result = self.gate({
                "hook_event_name": "StopFailure", "error_type": error_type,
                "error_message": f"{error_type} happened", "session_id": "sess-1",
            })
            self.assertEqual(result.exit_code, 0)
        records = self.ledger()
        self.assertEqual(len(records), len(self.DOCUMENTED_ERROR_TYPES))
        self.assertEqual([r["error_type"] for r in records], list(self.DOCUMENTED_ERROR_TYPES))

    def test_recovery_request_records_required_context(self):
        self.project.set_mode("implementation", highest_leverage_blocker="scheduler drift",
                              next_action="fix the scheduler", phase="phase-3")
        self.gate({"hook_event_name": "StopFailure", "error_type": "rate_limit",
                   "error_message": "429", "session_id": "sess-9"})
        recovery = self.project.read_state("RECOVERY_REQUEST.json")
        self.assertEqual(recovery["failure_type"], "rate_limit")
        self.assertEqual(recovery["session_id"], "sess-9")
        self.assertEqual(recovery["phase"], "phase-3")
        self.assertEqual(recovery["highest_leverage_blocker"], "scheduler drift")
        self.assertEqual(recovery["next_action"], "fix the scheduler")
        self.assertTrue(recovery["branch"])
        self.assertTrue(recovery["git_sha"])
        self.assertTrue(recovery["timestamp"])

    def test_does_not_claim_it_can_restart_the_session(self):
        self.gate({"hook_event_name": "StopFailure", "error_type": "server_error"})
        recovery = self.project.read_state("RECOVERY_REQUEST.json")
        self.assertFalse(recovery["can_this_hook_restart_the_session"])
        self.assertIn("cannot continue, retry, or restart", recovery["explanation"])

    def test_malformed_optional_fields_do_not_crash(self):
        for event in (
            {"hook_event_name": "StopFailure"},
            {"hook_event_name": "StopFailure", "error_type": None, "error_message": None},
            {"hook_event_name": "StopFailure", "error_type": {"nested": "object"}},
            {"hook_event_name": "StopFailure", "error_message": "x" * 50000},
        ):
            with self.subTest(event=str(event)[:60]):
                self.assertEqual(self.gate(event).exit_code, 0)
        self.assertEqual(len(self.ledger()), 4)

    def test_logging_never_reports_the_simulation_as_failed_or_successful(self):
        self.gate({"hook_event_name": "StopFailure", "error_type": "overloaded",
                   "error_message": "529 overloaded"})
        record = self.ledger()[-1]
        self.assertEqual(record["simulation_result"], "not_applicable")
        self.assertEqual(record["kind"], "claude_code_api_turn_failure")
        self.assertIn("NOT a simulation or test result", record["note"])
        blob = json.dumps(record).lower()
        for forbidden in ("simulation_passed", "simulation_failed", "\"pass\"", "acceptance"):
            self.assertNotIn(forbidden, blob)

    def test_survives_unusable_run_state(self):
        self.project.write_raw("RUN_STATE.json", "{{{")
        self.assertEqual(self.gate({"hook_event_name": "StopFailure", "error_type": "unknown"}).exit_code, 0)
        self.assertIn("state_error", self.ledger()[-1])


# ---------------------------------------------------------------------------
# ConfigChange
# ---------------------------------------------------------------------------


def config_event(source="project_settings", changes=None):
    return {"hook_event_name": "ConfigChange", "config_source": source,
            "config_changes": changes if changes is not None else {"hooks": {}}}


def live_config_event(source="project_settings"):
    """The ConfigChange payload shape Claude Code actually sends.

    Captured from a real session during live hook verification. It names the
    source ``source`` -- not ``config_source`` -- and carries no
    ``config_changes`` at all. Reading only the synthetic spelling made every
    real change resolve to "unknown", which silently disabled this gate, so the
    whole matrix is re-run against this shape.
    """
    return {
        "session_id": "live-shape",
        "transcript_path": "/root/.claude/projects/x/live-shape.jsonl",
        "cwd": "/home/user/SWORLDMODEL-GROUND-UP",
        "prompt_id": "ff938abf-d752-48f5-8eef-ef0dd2a6a631",
        "hook_event_name": "ConfigChange",
        "source": source,
        "file_path": "/home/user/SWORLDMODEL-GROUND-UP/.claude/settings.json",
    }


class TestConfigChange(GateTestCase):
    def log(self):
        path = self.project.agent_run / "CONFIG_CHANGES.jsonl"
        if not path.exists():
            return []
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def test_allowed_during_bootstrap(self):
        result = self.gate(config_event())
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.decision)

    def test_blocked_during_implementation_without_maintenance_state(self):
        self.project.set_mode("implementation")
        result = self.gate(config_event())
        self.assertEqual(result.decision, "block")
        self.assertIn("hook_maintenance", result.reason)

    def test_blocked_during_frozen_acceptance(self):
        self.project.set_mode("frozen_acceptance")
        self.assertEqual(self.gate(config_event("local_settings")).decision, "block")

    def test_allowed_during_recorded_hook_maintenance(self):
        self.project.set_mode("hook_maintenance")
        self.assertIsNone(self.gate(config_event()).decision)

    def test_allowed_when_run_state_flags_maintenance_explicitly(self):
        self.project.set_mode("implementation", hook_maintenance=True)
        self.assertIsNone(self.gate(config_event()).decision)

    def test_user_settings_change_is_not_blocked(self):
        self.project.set_mode("implementation")
        self.assertIsNone(self.gate(config_event("user_settings")).decision)

    def test_policy_change_is_logged_but_never_blocked(self):
        self.project.set_mode("frozen_acceptance")
        result = self.gate(config_event("policy_settings"))
        self.assertIsNone(result.decision)
        self.assertIn("cannot block a managed policy change", result.json.get("systemMessage", ""))
        self.assertEqual(self.log()[-1]["config_source"], "policy_settings")

    def test_all_sources_are_logged(self):
        for source in ("user_settings", "project_settings", "local_settings", "policy_settings", "skills"):
            self.gate(config_event(source))
        self.assertEqual([r["config_source"] for r in self.log()],
                         ["user_settings", "project_settings", "local_settings", "policy_settings", "skills"])

    def test_malformed_state_fails_closed(self):
        self.project.write_raw("RUN_STATE.json", "!")
        result = self.gate(config_event())
        self.assertEqual(result.decision, "block")

    # -- the payload shape Claude Code actually sends -------------------

    def test_live_payload_shape_blocks_during_implementation(self):
        """The whole point: this is the shape that reaches the hook in practice."""
        self.project.set_mode("implementation")
        for source in ("project_settings", "local_settings"):
            with self.subTest(source=source):
                result = self.gate(live_config_event(source))
                self.assertEqual(result.decision, "block",
                                 "a real settings change during implementation must block")
                self.assertIn("hook_maintenance", result.reason)

    def test_live_payload_shape_records_the_real_source(self):
        result = self.gate(live_config_event("project_settings"))
        self.assertIsNone(result.decision)
        record = self.log()[-1]
        self.assertEqual(record["config_source"], "project_settings",
                         "the source must be read from the field the payload actually uses")
        self.assertEqual(record["changed_file"],
                         "/home/user/SWORLDMODEL-GROUND-UP/.claude/settings.json")

    def test_live_payload_shape_allows_during_hook_maintenance(self):
        for mode, extra in (("hook_maintenance", {}), ("implementation", {"hook_maintenance": True})):
            with self.subTest(mode=mode, extra=extra):
                self.project.set_mode(mode, **extra)
                self.assertIsNone(self.gate(live_config_event()).decision)

    def test_live_payload_shape_keeps_user_and_policy_behaviour(self):
        self.project.set_mode("implementation")
        self.assertIsNone(self.gate(live_config_event("user_settings")).decision)
        result = self.gate(live_config_event("policy_settings"))
        self.assertIsNone(result.decision)
        self.assertIn("cannot block a managed policy change", result.json.get("systemMessage", ""))

    def test_unidentifiable_source_fails_closed_in_protected_modes(self):
        """A renamed payload field must not silently disable the gate."""
        for mode in ("implementation", "frozen_acceptance"):
            with self.subTest(mode=mode):
                self.project.set_mode(mode)
                result = self.gate({"hook_event_name": "ConfigChange",
                                    "some_future_field": "project_settings"})
                self.assertEqual(result.decision, "block")
                self.assertIn("could not be identified", result.reason)
                self.assertIn("some_future_field", result.reason)

    def test_unidentifiable_source_is_not_blocked_outside_protected_modes(self):
        for mode in ("hook_bootstrap", "hook_live_verification", "hook_maintenance"):
            with self.subTest(mode=mode):
                self.project.set_mode(mode)
                self.assertIsNone(self.gate({"hook_event_name": "ConfigChange"}).decision)

    def test_unidentifiable_source_records_the_payload_fields(self):
        self.gate({"hook_event_name": "ConfigChange", "mystery": 1})
        record = self.log()[-1]
        self.assertEqual(record["config_source"], "unknown")
        self.assertIn("mystery", record["payload_fields"])


# ---------------------------------------------------------------------------
# Dispatcher robustness
# ---------------------------------------------------------------------------


class TestDispatcher(GateTestCase):
    def test_unknown_event_does_not_wedge_anything(self):
        result = self.gate({"hook_event_name": "PostToolUse", "tool_name": "Bash"})
        self.assertEqual(result.exit_code, 0)

    def test_missing_event_name_is_reported_not_crashed(self):
        result = self.gate({"session_id": "x"})
        self.assertEqual(result.exit_code, 0)
        self.assertIn("hook_event_name", result.stderr)

    def test_empty_stdin_is_handled(self):
        from harness import GATE, GIT_ENV  # noqa: PLC0415
        import os
        import subprocess

        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project.path)
        env.update(GIT_ENV)
        proc = subprocess.run([sys.executable, str(GATE)], input="", capture_output=True,
                              text=True, env=env, timeout=30, check=False)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("empty input", proc.stderr)

    def test_hooks_never_make_network_calls(self):
        source = (Path(__file__).resolve().parents[2] / ".claude/hooks/gate.py").read_text(encoding="utf-8")
        source += (Path(__file__).resolve().parents[2] / ".claude/hooks/hook_state.py").read_text(encoding="utf-8")
        for forbidden in ("urllib.request", "http.client", "requests", "socket.create_connection", "urlopen"):
            self.assertNotIn(forbidden, source)

    def test_gate_finishes_quickly(self):
        import time

        start = time.monotonic()
        self.gate({"hook_event_name": "SessionStart", "source": "startup"})
        self.assertLess(time.monotonic() - start, 10.0)


# ---------------------------------------------------------------------------
# Shell write-target parsing (the input PreToolUse classifies)
# ---------------------------------------------------------------------------


class TestShellWriteTargets(unittest.TestCase):
    """Unit-level lock on the parser behind the PreToolUse path rules.

    The end-to-end cases above prove the *gate* decides correctly; these pin the
    parse itself, so a regression names the wrong-parse cause directly instead of
    surfacing as a puzzling allow or deny.
    """

    @staticmethod
    def targets(command):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude" / "hooks"))
        import hook_state as hs

        return hs.shell_write_targets(command)

    def assert_targets(self, command, expected):
        self.assertEqual(sorted(self.targets(command)), sorted(expected), f"command: {command!r}")

    def test_plain_redirections(self):
        self.assert_targets("echo hi > out.txt", ["out.txt"])
        self.assert_targets("echo hi >out.txt", ["out.txt"])
        self.assert_targets("echo hi >> logs/out.txt", ["logs/out.txt"])
        self.assert_targets("cat x 2> err.log", ["err.log"])
        self.assert_targets("python3 x.py &> both.log", ["both.log"])
        self.assert_targets("echo hi >| forced.txt", ["forced.txt"])

    def test_quoted_and_spaced_targets_are_recovered(self):
        self.assert_targets('echo hi > "a b.txt"', ["a b.txt"])
        self.assert_targets("echo hi > 'quoted.txt'", ["quoted.txt"])

    def test_quoting_makes_an_operator_into_text(self):
        for command in ('echo "VAR=${FOO:-<unset>}"',
                        'python3 -c "print(1 if 2 > 1 else 0)"',
                        "python3 -c \"print(f'{a} -> {b}')\"",
                        "grep 'tee|sed -i' file.py"):
            with self.subTest(command=command):
                self.assert_targets(command, [])

    def test_heredoc_bodies_are_ignored(self):
        self.assert_targets(
            "git commit -F - <<'MSG'\nAdd a thing\n\nCo-Authored-By: A <a@b.invalid>\nMSG",
            [],
        )
        self.assert_targets("cat <<-EOF > real.txt\ntext > not_a_target\nEOF", ["real.txt"])

    def test_descriptor_duplication_is_not_a_file(self):
        self.assert_targets("pytest -q 2>&1", [])
        self.assert_targets("python3 x.py 2>&1 | head -5", [])

    def test_in_place_writers_yield_their_file_operands(self):
        self.assert_targets("sed -i 's/a/b/' prod.py", ["prod.py"])
        self.assert_targets("sed -i.bak -e s/a/b/ prod.py", ["prod.py"])
        self.assert_targets("sed -i -f script.sed a.py b.py", ["a.py", "b.py"])
        self.assert_targets("tee -a report.json", ["report.json"])
        self.assert_targets("truncate -s 0 keep.log", ["keep.log"])
        self.assert_targets("truncate --size=0 keep.log", ["keep.log"])

    def test_sed_without_in_place_writes_nothing(self):
        self.assert_targets("sed -n 1,5p prod.py", [])
        self.assert_targets("sed -e s/a/b/ prod.py", [])

    def test_each_pipeline_segment_is_parsed(self):
        self.assert_targets("python3 gen.py | tee a.txt > b.txt", ["a.txt", "b.txt"])
        self.assert_targets("echo a > x.txt && echo b > y.txt", ["x.txt", "y.txt"])

    def test_device_files_are_ignored(self):
        self.assert_targets("echo hi > /dev/null", [])

    def test_environment_assignments_do_not_hide_the_command(self):
        self.assert_targets("FOO=1 BAR=2 sed -i s/a/b/ prod.py", ["prod.py"])

    def test_unbalanced_quotes_still_yield_a_target(self):
        """The tokenizer falls back to a whitespace split; detection must survive."""
        self.assertIn("out.txt", self.targets("echo 'unbalanced > out.txt"))


if __name__ == "__main__":
    unittest.main()
