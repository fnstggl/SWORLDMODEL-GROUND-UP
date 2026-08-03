"""Tests for .claude/tools/validate_control_plane.py and the master-context handshake.

Two layers:

* unit tests that drive individual checks against synthetic project trees,
  including deliberately known-bad fixtures (malformed status, disabled hooks,
  missing events, stale receipts, surviving placeholders);
* one end-to-end run of the validator against this repository, asserting the
  output contract and the structural checks that are not circular.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".claude" / "tools"))
sys.path.insert(0, str(REPO_ROOT / ".claude" / "hooks"))

import hook_state as hs  # noqa: E402
import validate_control_plane as vcp  # noqa: E402

from harness import Project, VALIDATOR, run_tool  # noqa: E402


def checks_by_name(result) -> dict:
    return {c["check"]: c for c in result.checks}


class TestFrontmatterParser(unittest.TestCase):
    def test_valid_frontmatter_parses(self):
        data, error = vcp.parse_frontmatter(
            "---\nname: my-agent\ndescription: Does a thing\ntools: Read, Grep\n---\n\nBody text.\n"
        )
        self.assertIsNone(error)
        self.assertEqual(data["name"], "my-agent")
        self.assertEqual(data["description"], "Does a thing")

    def test_missing_opening_fence_is_an_error(self):
        _, error = vcp.parse_frontmatter("name: my-agent\n")
        self.assertIn("'---' frontmatter fence", error)

    def test_unclosed_fence_is_an_error(self):
        _, error = vcp.parse_frontmatter("---\nname: x\ndescription: y\n")
        self.assertIn("never closed", error)

    def test_empty_body_is_an_error(self):
        _, error = vcp.parse_frontmatter("---\nname: x\ndescription: y\n---\n\n   \n")
        self.assertIn("empty body", error)

    def test_real_agent_definitions_all_parse(self):
        for rel in vcp.AGENT_FILES:
            with self.subTest(agent=rel):
                data, error = vcp.parse_frontmatter((REPO_ROOT / rel).read_text(encoding="utf-8"))
                self.assertIsNone(error, f"{rel}: {error}")
                self.assertEqual(data["name"], Path(rel).stem)
                self.assertTrue(data["description"])


class ValidatorCheckTestCase(unittest.TestCase):
    def setUp(self):
        self.project = Project.create()
        self.addCleanup(self.project.destroy)

    def write_settings(self, settings):
        path = self.project.path / ".claude" / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    def good_settings(self):
        (self.project.path / ".claude" / "hooks" / "gate.py").write_text("# stub\n", encoding="utf-8")
        return {
            "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
            "hooks": {
                event: [{"hooks": [{"type": "command",
                                    "command": "python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/gate.py"}]}]
                for event in vcp.REQUIRED_HOOK_EVENTS
            },
        }

    def run_check(self, func, *args):
        result = vcp.Result()
        func(self.project.path, result, *args)
        return checks_by_name(result)


class TestSettingsChecks(ValidatorCheckTestCase):
    def test_complete_settings_pass(self):
        self.write_settings(self.good_settings())
        checks = self.run_check(vcp.check_settings)
        self.assertTrue(checks["settings_has_required_events"]["ok"])
        self.assertTrue(checks["settings_hook_shape"]["ok"])
        self.assertTrue(checks["settings_script_paths_exist"]["ok"])
        self.assertTrue(checks["agent_teams_enabled"]["ok"])

    def test_missing_hook_event_is_detected(self):
        settings = self.good_settings()
        del settings["hooks"]["Stop"]
        self.write_settings(settings)
        checks = self.run_check(vcp.check_settings)
        self.assertFalse(checks["settings_has_required_events"]["ok"])
        self.assertIn("Stop", checks["settings_has_required_events"]["detail"])

    def test_disabled_hooks_is_a_failure(self):
        settings = self.good_settings()
        settings["disableAllHooks"] = True
        self.write_settings(settings)
        checks = self.run_check(vcp.check_settings)
        self.assertFalse(checks["hooks_not_disabled"]["ok"])

    def test_missing_script_path_is_detected(self):
        settings = self.good_settings()
        settings["hooks"]["Stop"] = [{"hooks": [{
            "type": "command", "command": "python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/ghost.py"}]}]
        self.write_settings(settings)
        checks = self.run_check(vcp.check_settings)
        self.assertFalse(checks["settings_script_paths_exist"]["ok"])
        self.assertIn("ghost.py", checks["settings_script_paths_exist"]["detail"])

    def test_command_without_project_dir_placeholder_is_detected(self):
        settings = self.good_settings()
        settings["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": "python3 .claude/hooks/gate.py"}]}]
        self.write_settings(settings)
        checks = self.run_check(vcp.check_settings)
        self.assertFalse(checks["settings_hook_shape"]["ok"])
        self.assertIn("CLAUDE_PROJECT_DIR", checks["settings_hook_shape"]["detail"])

    def test_agent_teams_flag_missing_is_a_warning_not_an_error(self):
        settings = self.good_settings()
        settings["env"] = {}
        self.write_settings(settings)
        checks = self.run_check(vcp.check_settings)
        self.assertFalse(checks["agent_teams_enabled"]["ok"])
        self.assertEqual(checks["agent_teams_enabled"]["severity"], "warning")


class TestJsonChecks(ValidatorCheckTestCase):
    def test_json_with_comments_is_rejected(self):
        self.project.write_raw("RUN_STATE.json", '{\n  // a comment\n  "mode": "hook_bootstrap"\n}\n')
        checks = self.run_check(vcp.check_json_parses)
        self.assertFalse(checks["json_files_parse"]["ok"])

    def test_trailing_comma_is_rejected(self):
        self.project.write_raw("TASK_GRAPH.json", '{"schema_version": 1, "tasks": [],}')
        checks = self.run_check(vcp.check_json_parses)
        self.assertFalse(checks["json_files_parse"]["ok"])

    def test_invalid_jsonl_ledger_is_detected(self):
        (self.project.agent_run / "FAILURE_LEDGER.jsonl").write_text(
            '{"ok": 1}\nnot json\n', encoding="utf-8")
        checks = self.run_check(vcp.check_json_parses)
        self.assertFalse(checks["failure_ledger_is_valid_jsonl"]["ok"])

    def test_empty_ledger_is_valid(self):
        checks = self.run_check(vcp.check_json_parses)
        self.assertTrue(checks["failure_ledger_is_valid_jsonl"]["ok"])


class TestBootstrapStatusConsistency(ValidatorCheckTestCase):
    def test_in_progress_is_consistent(self):
        self.assertTrue(self.run_check(vcp.check_bootstrap_status_consistent)["bootstrap_status_consistent"]["ok"])

    def test_static_pass_requires_all_static_gates_to_pass(self):
        self.project.set_bootstrap(overall="STATIC_PASS_LIVE_PENDING", static_tests="PASS",
                                   settings_validation="NOT_RUN", monitored_runner_tests="PASS")
        check = self.run_check(vcp.check_bootstrap_status_consistent)["bootstrap_status_consistent"]
        self.assertFalse(check["ok"])
        self.assertIn("settings_validation", check["detail"])

    def test_static_pass_requires_live_verification_to_remain_pending(self):
        self.project.set_bootstrap(overall="STATIC_PASS_LIVE_PENDING", static_tests="PASS",
                                   settings_validation="PASS", monitored_runner_tests="PASS",
                                   live_event_tests="PASS")
        check = self.run_check(vcp.check_bootstrap_status_consistent)["bootstrap_status_consistent"]
        self.assertFalse(check["ok"])
        self.assertIn("live_event_tests", check["detail"])

    def test_full_pass_requires_a_verified_commit(self):
        self.project.set_bootstrap(overall="PASS", static_tests="PASS", settings_validation="PASS",
                                   monitored_runner_tests="PASS", fresh_session_hooks_loaded="PASS",
                                   live_event_tests="PASS", verified_commit=None)
        check = self.run_check(vcp.check_bootstrap_status_consistent)["bootstrap_status_consistent"]
        self.assertFalse(check["ok"])
        self.assertIn("verified_commit", check["detail"])

    def test_malformed_status_is_reported(self):
        self.project.write_raw("HOOK_BOOTSTRAP_STATUS.json", "{oops")
        check = self.run_check(vcp.check_bootstrap_status_consistent)["bootstrap_status_consistent"]
        self.assertFalse(check["ok"])
        self.assertIn("HOOK_BOOTSTRAP_STATUS.json", check["detail"])

    def test_unrecognised_overall_value_is_reported(self):
        self.project.set_bootstrap(overall="TOTALLY_FINE_TRUST_ME")
        check = self.run_check(vcp.check_bootstrap_status_consistent)["bootstrap_status_consistent"]
        self.assertFalse(check["ok"])


class TestInitializationLevels(ValidatorCheckTestCase):
    """The same placeholder is valid at one level and a failure at another."""

    def fully_initialize(self):
        """Bring the synthetic project to a genuinely valid 'implementation' level."""
        directive = self.project.path / "docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md"
        directive.parent.mkdir(parents=True, exist_ok=True)
        directive.write_text("# Master directive\n\nDo the thing.\n", encoding="utf-8")
        digest = hashlib.sha256(directive.read_bytes()).hexdigest()

        self.project.write_text("ARCHITECTURE.md", "# Architecture\n\nConcrete architecture here.\n")
        self.project.write_text("CRITICAL_PATH.md", "# Critical Path\n\n1. Real step.\n")
        self.project.set_tasks([{"id": "impl-1", "owner": "implementation-agent", "status": "pending"}],
                               status="INITIALIZED")
        self.project.set_acceptance(gates={"kernel": "NOT_RUN"})
        self.project.write_state("UPSTREAM_PROTECTED_PATHS.json", {
            "schema_version": 1, "status": "INITIALIZED",
            "repositories": [{"name": "concordia"}], "protected_paths": ["vendor/concordia"]})
        self.project.add_receipt(hs.MASTER_INIT_TASK_ID, command="validate_control_plane.py")
        self.project.set_mode("implementation", master_context_loaded=True,
                              master_directive_path="docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md",
                              master_directive_sha256=digest, architecture_initialized=True,
                              task_graph_initialized=True, acceptance_gates_initialized=True)
        return digest

    # -- level 1: hook_bootstrap ---------------------------------------

    def test_bootstrap_level_accepts_placeholders(self):
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertTrue(check["ok"])
        self.assertEqual(check["level"], "hook_bootstrap")

    def test_bootstrap_level_rejects_premature_master_context_fields(self):
        self.project.set_mode("hook_bootstrap", master_context_loaded=True)
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertFalse(check["ok"])
        self.assertIn("must all remain false/null", check["detail"])

    def test_bootstrap_level_rejects_speculative_implementation_tasks(self):
        self.project.set_tasks([{"id": "concordia-integration", "owner": "x", "status": "pending"}])
        check = self.run_check(vcp.check_initialization_level)["no_speculative_tasks"]
        self.assertFalse(check["ok"])
        self.assertIn("concordia-integration", check["detail"])

    def test_bootstrap_only_tasks_are_permitted(self):
        self.project.set_tasks([{"id": "hook-verify", "owner": "x", "status": "pending",
                                 "bootstrap_only": True}])
        self.assertTrue(self.run_check(vcp.check_initialization_level)["no_speculative_tasks"]["ok"])

    # -- level 2: ready_for_master -------------------------------------

    def test_ready_for_master_still_accepts_placeholders(self):
        self.project.set_mode("ready_for_master")
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertTrue(check["ok"])
        self.assertEqual(check["level"], "ready_for_master")
        self.assertTrue(check["outstanding_master_context"],
                        "the outstanding preconditions must still be reported")

    # -- level 3: implementation ---------------------------------------

    def test_implementation_level_rejects_surviving_placeholders(self):
        self.project.set_mode("implementation")
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertFalse(check["ok"], "a bootstrap placeholder must fail once mode is implementation")
        detail = check["detail"]
        self.assertIn("MASTER_DIRECTIVE_PENDING", detail)

    def test_fully_initialized_implementation_passes(self):
        self.fully_initialize()
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertTrue(check["ok"], check["detail"])

    def test_each_placeholder_file_is_individually_load_bearing(self):
        """Reverting any single file to its bootstrap placeholder must fail on its own."""
        for name, placeholder in (
            ("ARCHITECTURE.md", "# Architecture State\nStatus: MASTER_DIRECTIVE_PENDING\n"),
            ("CRITICAL_PATH.md", "# Critical Path\nStatus: MASTER_DIRECTIVE_PENDING\n"),
        ):
            with self.subTest(file=name):
                self.fully_initialize()
                self.assertTrue(self.run_check(vcp.check_initialization_level)["initialization_level"]["ok"])
                self.project.write_text(name, placeholder)
                check = self.run_check(vcp.check_initialization_level)["initialization_level"]
                self.assertFalse(check["ok"])
                self.assertIn(name, check["detail"])

    def test_missing_placeholder_file_is_not_mistaken_for_initialized(self):
        for name in ("ARCHITECTURE.md", "CRITICAL_PATH.md"):
            with self.subTest(file=name):
                self.fully_initialize()
                (self.project.agent_run / name).unlink()
                check = self.run_check(vcp.check_initialization_level)["initialization_level"]
                self.assertFalse(check["ok"])
                self.assertIn(f"{name} is missing", check["detail"])

    def test_implementation_rejects_hash_mismatch(self):
        self.fully_initialize()
        directive = self.project.path / "docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md"
        directive.write_text("# Master directive\n\nSomething else entirely.\n", encoding="utf-8")
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertFalse(check["ok"])
        self.assertIn("hash mismatch", check["detail"])

    def test_implementation_rejects_missing_directive(self):
        self.fully_initialize()
        (self.project.path / "docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md").unlink()
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertFalse(check["ok"])
        self.assertIn("missing", check["detail"])

    def test_implementation_rejects_empty_task_graph(self):
        self.fully_initialize()
        self.project.set_tasks([], status="INITIALIZED")
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertFalse(check["ok"])
        self.assertIn("no implementation tasks", check["detail"])

    def test_implementation_rejects_missing_acceptance_gates(self):
        self.fully_initialize()
        self.project.set_acceptance(gates={})
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertFalse(check["ok"])
        self.assertIn("no mandatory acceptance gates", check["detail"])

    def test_implementation_rejects_uninitialized_upstream_protection(self):
        self.fully_initialize()
        self.project.write_state("UPSTREAM_PROTECTED_PATHS.json", {
            "schema_version": 1, "status": "MASTER_DIRECTIVE_PENDING",
            "repositories": [], "protected_paths": []})
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertFalse(check["ok"])
        self.assertIn("UPSTREAM_PROTECTED_PATHS.json", check["detail"])

    def test_implementation_rejects_missing_initialization_receipt(self):
        self.fully_initialize()
        for receipt in (self.project.agent_run / "receipts").glob("*.json"):
            receipt.unlink()
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertFalse(check["ok"])
        self.assertIn(hs.MASTER_INIT_TASK_ID, check["detail"])

    def test_implementation_rejects_stale_initialization_receipt(self):
        self.fully_initialize()
        for receipt in (self.project.agent_run / "receipts").glob("*.json"):
            receipt.unlink()
        self.project.add_receipt(hs.MASTER_INIT_TASK_ID, sha="0" * 40)
        check = self.run_check(vcp.check_initialization_level)["initialization_level"]
        self.assertFalse(check["ok"], "a receipt from another SHA must not satisfy the handshake")

    def test_implementation_rejects_failed_initialization_receipt(self):
        self.fully_initialize()
        for receipt in (self.project.agent_run / "receipts").glob("*.json"):
            receipt.unlink()
        self.project.add_receipt(hs.MASTER_INIT_TASK_ID, exit_code=1)
        self.assertFalse(self.run_check(vcp.check_initialization_level)["initialization_level"]["ok"])


class TestPathClassification(unittest.TestCase):
    """Git reports untracked trees as 'dir/'; a bare directory must classify like its contents."""

    def classify(self, path):
        return hs.classify_path(path, REPO_ROOT)

    def test_directory_forms_classify_like_their_contents(self):
        for path, expected in ((".claude", "control_plane"), (".claude/", "control_plane"),
                               (".agent-run", "agent_run"), (".agent-run/", "agent_run"),
                               ("tests", "test"), ("tests/", "test"),
                               ("docs", "doc"), ("docs/", "doc")):
            with self.subTest(path=path):
                self.assertEqual(self.classify(path), expected)

    def test_control_plane_files_are_recognised(self):
        for path in ("CLAUDE.md", ".claude/settings.json", ".claude/hooks/gate.py",
                     ".claude/agents/implementation-agent.md"):
            with self.subTest(path=path):
                self.assertEqual(self.classify(path), "control_plane")

    def test_unknown_paths_fall_through_to_production(self):
        """The conservative default: anything unrecognised is treated as production."""
        for path in ("sworldmodel/kernel.py", "compiler/scene.py", "run_worlds.py",
                     "some/brand/new/module.py"):
            with self.subTest(path=path):
                self.assertEqual(self.classify(path), "production")

    def test_generic_evaluator_fixture_and_prompt_heuristics(self):
        self.assertEqual(self.classify("evaluation/score.py"), "evaluator")
        self.assertEqual(self.classify("acceptance/gate.py"), "evaluator")
        self.assertEqual(self.classify("worlds/committee.json"), "fixture")
        self.assertEqual(self.classify("pkg/prompts/system.txt"), "prompt")


class TestPorcelainParsing(unittest.TestCase):
    """`git status --porcelain` uses a fixed-width 'XY ' prefix; dotfiles are the trap."""

    def test_unstaged_change_to_a_dotfile_keeps_its_leading_dot(self):
        self.assertEqual(
            hs.parse_porcelain_paths(" M .agent-run/RUN_STATE.json"),
            [".agent-run/RUN_STATE.json"],
        )

    def test_all_status_codes_parse(self):
        status = (
            " M .agent-run/RUN_STATE.json\n"
            "M  .claude/settings.json\n"
            "MM .claude/hooks/gate.py\n"
            "?? .agent-run/new.json\n"
            "A  tests/control_plane/test_gate.py\n"
            "R  old/name.py -> new/name.py\n"
            "D  removed.py"
        )
        self.assertEqual(hs.parse_porcelain_paths(status), [
            ".agent-run/RUN_STATE.json", ".claude/settings.json", ".claude/hooks/gate.py",
            ".agent-run/new.json", "tests/control_plane/test_gate.py", "new/name.py", "removed.py",
        ])

    def test_empty_and_none_are_handled(self):
        self.assertEqual(hs.parse_porcelain_paths(""), [])
        self.assertEqual(hs.parse_porcelain_paths(None), [])

    def test_live_dirty_dotfile_is_classified_as_agent_run(self):
        """End-to-end: a real modified tracked dotfile must not read as production."""
        project = Project.create()
        self.addCleanup(project.destroy)
        project.write_text("BLOCKERS.md", "# Blockers\n\nmodified\n")
        project._git("add", "-A")
        project._git("commit", "-q", "-m", "add state")
        project.write_text("BLOCKERS.md", "# Blockers\n\nmodified again\n")

        dirty = hs.git_dirty_paths(project.path)
        self.assertIn(".agent-run/BLOCKERS.md", dirty)
        for path in dirty:
            with self.subTest(path=path):
                self.assertNotEqual(hs.classify_path(path, project.path), "production")

    def test_leading_dot_slash_is_stripped_without_eating_the_dot(self):
        self.assertEqual(hs._strip_leading_dot_slash("./vendor/x"), "vendor/x")
        self.assertEqual(hs._strip_leading_dot_slash(".agent-run/x"), ".agent-run/x")
        self.assertEqual(hs._strip_leading_dot_slash("././a"), "a")


class TestReceiptSchema(unittest.TestCase):
    def valid_receipt(self):
        return {
            "schema_version": 1, "task_id": "t", "git_sha": "abc", "worktree": "/tmp/x",
            "command": "pytest", "exit_code": 0, "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:01+00:00", "artifact_paths": [],
            "configuration_hashes": {}, "valid": True,
        }

    def test_valid_receipt_passes(self):
        self.assertEqual(hs.receipt_schema_problems(self.valid_receipt()), [])
        self.assertTrue(hs.receipt_is_passing(self.valid_receipt()))

    def test_every_required_field_is_enforced(self):
        for field in hs.RECEIPT_REQUIRED_FIELDS:
            with self.subTest(field=field):
                receipt = self.valid_receipt()
                del receipt[field]
                self.assertIn(f"missing field '{field}'", hs.receipt_schema_problems(receipt))
                self.assertFalse(hs.receipt_is_passing(receipt))

    def test_nonzero_exit_code_is_not_passing(self):
        receipt = self.valid_receipt()
        receipt["exit_code"] = 1
        self.assertFalse(hs.receipt_is_passing(receipt))

    def test_invalid_flag_is_not_passing(self):
        receipt = self.valid_receipt()
        receipt["valid"] = False
        self.assertFalse(hs.receipt_is_passing(receipt))

    def test_wrong_types_are_rejected(self):
        receipt = self.valid_receipt()
        receipt["exit_code"] = "0"
        self.assertIn("'exit_code' must be an integer", hs.receipt_schema_problems(receipt))


class TestRecordReceiptTool(unittest.TestCase):
    def setUp(self):
        self.project = Project.create()
        self.addCleanup(self.project.destroy)

    def test_run_mode_records_observed_result(self):
        from harness import RECORD_RECEIPT

        proc = run_tool(self.project, RECORD_RECEIPT,
                        ["--task-id", "t1", "--run", "--", sys.executable, "-c", "print('ok')"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        receipts = list((self.project.agent_run / "receipts").glob("*.json"))
        self.assertEqual(len(receipts), 1)
        receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(receipt["task_id"], "t1")
        self.assertEqual(receipt["exit_code"], 0)
        self.assertTrue(receipt["valid"])
        self.assertEqual(receipt["git_sha"], self.project.head_sha())
        self.assertEqual(hs.receipt_schema_problems(receipt), [])

    def test_failing_command_records_a_failing_receipt_and_exits_nonzero(self):
        from harness import RECORD_RECEIPT

        proc = run_tool(self.project, RECORD_RECEIPT,
                        ["--task-id", "t2", "--run", "--", sys.executable, "-c", "import sys; sys.exit(3)"])
        self.assertEqual(proc.returncode, 1)
        receipt = json.loads(next((self.project.agent_run / "receipts").glob("*.json")).read_text())
        self.assertEqual(receipt["exit_code"], 3)

    def test_declared_but_missing_artifact_makes_the_receipt_invalid(self):
        from harness import RECORD_RECEIPT

        proc = run_tool(self.project, RECORD_RECEIPT,
                        ["--task-id", "t3", "--command", "x", "--exit-code", "0",
                         "--artifact", "does/not/exist.json"])
        self.assertEqual(proc.returncode, 1)
        receipt = json.loads(next((self.project.agent_run / "receipts").glob("*.json")).read_text())
        self.assertFalse(receipt["valid"])
        self.assertIn("do not exist", receipt["invalid_reason"])

    def test_bad_timestamp_is_rejected(self):
        from harness import RECORD_RECEIPT

        proc = run_tool(self.project, RECORD_RECEIPT,
                        ["--task-id", "t4", "--command", "x", "--exit-code", "0",
                         "--started-at", "yesterday"])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("ISO-8601", proc.stderr)


class TestValidatorEndToEnd(unittest.TestCase):
    """Run the real validator against this repository and check its contract."""

    @classmethod
    def setUpClass(cls):
        proc = subprocess.run([sys.executable, str(VALIDATOR)], cwd=str(REPO_ROOT),
                              capture_output=True, text=True, timeout=300, check=False)
        cls.proc = proc
        cls.payload = json.loads(proc.stdout)

    def test_machine_readable_result_on_stdout(self):
        self.assertEqual(self.payload["tool"], "validate_control_plane")
        self.assertIn(self.payload["overall"], {"PASS", "FAIL"})
        self.assertIsInstance(self.payload["checks"], list)
        self.assertTrue(self.payload["generated_at"])

    def test_human_readable_result_on_stderr(self):
        self.assertIn("control plane:", self.proc.stderr)
        self.assertLess(len(self.proc.stderr.splitlines()), 60, "human summary must stay concise")

    def test_exit_code_matches_overall(self):
        self.assertEqual(self.proc.returncode, 0 if self.payload["overall"] == "PASS" else 1)

    def test_all_expected_checks_are_reported(self):
        names = {c["check"] for c in self.payload["checks"]}
        for expected in ("required_files_exist", "json_files_parse", "settings_has_required_events",
                         "settings_script_paths_exist", "python_sources_compile",
                         "agent_definitions_parse", "hook_tests_passed",
                         "monitored_runner_tests_passed", "no_production_files_changed",
                         "claude_md_preserved", "git_context_recorded",
                         "bootstrap_status_consistent", "initialization_level",
                         "run_state_valid"):
            self.assertIn(expected, names)

    def test_structural_checks_pass_for_this_repository(self):
        checks = {c["check"]: c for c in self.payload["checks"]}
        for name in ("required_files_exist", "json_files_parse", "settings_has_required_events",
                     "settings_hook_shape", "settings_script_paths_exist", "python_sources_compile",
                     "agent_definitions_parse", "no_production_files_changed", "claude_md_preserved",
                     "run_state_valid", "bootstrap_status_consistent", "initialization_level"):
            with self.subTest(check=name):
                self.assertTrue(checks[name]["ok"], f"{name}: {checks[name]['detail']}")

    def test_no_production_implementation_files_changed(self):
        check = next(c for c in self.payload["checks"] if c["check"] == "no_production_files_changed")
        self.assertTrue(check["ok"], check["detail"])
        for path in check["changed_paths"]:
            with self.subTest(path=path):
                self.assertIn(hs.classify_path(path, REPO_ROOT),
                              {"control_plane", "agent_run", "test", "doc"},
                              f"{path} is not a control-plane path")


if __name__ == "__main__":
    unittest.main()
