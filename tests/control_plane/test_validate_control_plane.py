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

    def test_urls_inside_string_values_are_not_comments(self):
        """Regression: '//' inside a JSON string value is data, not a comment.

        Monitored-job records legitimately carry commands and URLs like
        'http://localhost:9'; the audit failed live on BACKGROUND_JOBS.json
        because the old raw-text scan could not tell values from syntax.
        """
        self.write_settings(self.good_settings())
        self.project.write_state("BACKGROUND_JOBS.json", {
            "schema_version": 1,
            "active_jobs": [],
            "completed_jobs": [{
                "job_id": "j1",
                "command": "env API_BASE=http://localhost:9 pytest /* glob */",
                "url": "https://example.com/path",
            }],
        })
        checks = self.run_check(vcp.check_json_parses)
        self.assertTrue(checks["json_files_parse"]["ok"], checks["json_files_parse"]["detail"])

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


class TestDocumentedLimitations(ValidatorCheckTestCase):
    """``PASS_WITH_DOCUMENTED_LIMITATION`` must cost more than a plain ``PASS``.

    A hook event can be implemented, registered, statically covered and still
    never emitted by the host. That has to be recordable without lying and
    without deadlocking the run -- but only against an explicit declaration, or
    the escape hatch just becomes a way to wave an unverified hook through.
    """

    LIMITATION = {
        "hook_event": "TeammateIdle",
        "status": "UNAVAILABLE_IN_CLAUDE_CODE_WEB",
        "reason": "the host never emits this event on this surface",
        "fallback_controls": ["TaskCompleted", "SubagentStop", "Stop", "explicit task ownership"],
    }

    def passing_checks(self, **overrides):
        checks = {event: "PASS" for event in vcp.REQUIRED_HOOK_EVENTS}
        checks.update(overrides)
        return checks

    def set_pass(self, **fields):
        base = dict(overall="PASS", static_tests="PASS", settings_validation="PASS",
                    monitored_runner_tests="PASS", fresh_session_hooks_loaded="PASS",
                    verified_commit="0" * 40)
        base.update(fields)
        self.project.set_bootstrap(**base)

    def check(self):
        return self.run_check(vcp.check_bootstrap_status_consistent)["bootstrap_status_consistent"]

    def test_declared_limitation_is_accepted(self):
        self.set_pass(
            live_event_tests="PASS_WITH_DOCUMENTED_LIMITATION",
            live_checks=self.passing_checks(TeammateIdle="UNAVAILABLE_IN_CLAUDE_CODE_WEB"),
            documented_limitations=[dict(self.LIMITATION)],
        )
        self.assertTrue(self.check()["ok"])

    def test_plain_pass_still_requires_every_live_check_to_pass(self):
        self.set_pass(
            live_event_tests="PASS",
            live_checks=self.passing_checks(TeammateIdle="UNAVAILABLE_IN_CLAUDE_CODE_WEB"),
        )
        check = self.check()
        self.assertFalse(check["ok"])
        self.assertIn("TeammateIdle", check["detail"])

    def test_limitation_status_without_a_declaration_is_rejected(self):
        self.set_pass(
            live_event_tests="PASS_WITH_DOCUMENTED_LIMITATION",
            live_checks=self.passing_checks(TeammateIdle="UNAVAILABLE_IN_CLAUDE_CODE_WEB"),
        )
        check = self.check()
        self.assertFalse(check["ok"])
        self.assertIn("documented_limitations", check["detail"])

    def test_a_limitation_cannot_excuse_an_event_it_does_not_name(self):
        self.set_pass(
            live_event_tests="PASS_WITH_DOCUMENTED_LIMITATION",
            live_checks=self.passing_checks(TeammateIdle="UNAVAILABLE_IN_CLAUDE_CODE_WEB",
                                            Stop="NOT_EMITTED"),
            documented_limitations=[dict(self.LIMITATION)],
        )
        check = self.check()
        self.assertFalse(check["ok"])
        self.assertIn("Stop", check["detail"])

    def test_declaration_must_match_the_live_check_it_excuses(self):
        self.set_pass(
            live_event_tests="PASS_WITH_DOCUMENTED_LIMITATION",
            live_checks=self.passing_checks(TeammateIdle="NOT_EMITTED"),
            documented_limitations=[dict(self.LIMITATION)],
        )
        check = self.check()
        self.assertFalse(check["ok"])
        self.assertIn("does not match", check["detail"])

    def test_each_declared_field_is_required(self):
        for field in vcp.DOCUMENTED_LIMITATION_FIELDS:
            with self.subTest(field=field):
                entry = dict(self.LIMITATION)
                del entry[field]
                self.set_pass(
                    live_event_tests="PASS_WITH_DOCUMENTED_LIMITATION",
                    live_checks=self.passing_checks(TeammateIdle="UNAVAILABLE_IN_CLAUDE_CODE_WEB"),
                    documented_limitations=[entry],
                )
                check = self.check()
                self.assertFalse(check["ok"])
                self.assertIn(field, check["detail"])

    def test_unknown_hook_event_cannot_be_excused(self):
        self.set_pass(
            live_event_tests="PASS_WITH_DOCUMENTED_LIMITATION",
            live_checks=self.passing_checks(),
            documented_limitations=[dict(self.LIMITATION, hook_event="NotAHook")],
        )
        check = self.check()
        self.assertFalse(check["ok"])
        self.assertIn("NotAHook", check["detail"])

    def test_invented_limitation_status_is_rejected(self):
        self.set_pass(
            live_event_tests="PASS_WITH_DOCUMENTED_LIMITATION",
            live_checks=self.passing_checks(TeammateIdle="WORKS_ON_MY_MACHINE"),
            documented_limitations=[dict(self.LIMITATION, status="WORKS_ON_MY_MACHINE")],
        )
        check = self.check()
        self.assertFalse(check["ok"])
        self.assertIn("recognised limitation status", check["detail"])

    def test_declaration_alongside_plain_pass_is_rejected(self):
        self.set_pass(
            live_event_tests="PASS",
            live_checks=self.passing_checks(),
            documented_limitations=[dict(self.LIMITATION)],
        )
        check = self.check()
        self.assertFalse(check["ok"])
        self.assertIn("documented_limitations", check["detail"])

    def test_empty_declaration_list_is_rejected(self):
        self.set_pass(
            live_event_tests="PASS_WITH_DOCUMENTED_LIMITATION",
            live_checks=self.passing_checks(TeammateIdle="UNAVAILABLE_IN_CLAUDE_CODE_WEB"),
            documented_limitations=[],
        )
        self.assertFalse(self.check()["ok"])

    def test_non_object_declaration_is_rejected(self):
        self.set_pass(
            live_event_tests="PASS_WITH_DOCUMENTED_LIMITATION",
            live_checks=self.passing_checks(TeammateIdle="UNAVAILABLE_IN_CLAUDE_CODE_WEB"),
            documented_limitations=["TeammateIdle is broken"],
        )
        self.assertFalse(self.check()["ok"])

    def test_the_real_repository_status_is_consistent(self):
        """The shipped HOOK_BOOTSTRAP_STATUS.json must satisfy the rule it relies on."""
        repo = Path(__file__).resolve().parents[2]
        status = json.loads((repo / ".agent-run" / "HOOK_BOOTSTRAP_STATUS.json").read_text("utf-8"))
        problems = vcp._documented_limitation_problems(status, status.get("live_event_tests"))
        self.assertEqual(problems, [])


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

    def test_docs_take_precedence_over_evaluator_fixture_prompt_heuristics(self):
        """A doc named after evaluators is prose, not an evaluator.

        Regression for the live failure where the directive-mandated
        docs/engine_migration/ACCEPTANCE_GATES.md classified as 'evaluator'
        and the change audit rejected it. Docs are editable even during a
        frozen acceptance batch (HOOKS_README §5).
        """
        for path in ("docs/engine_migration/ACCEPTANCE_GATES.md",
                     "docs/evaluation/notes.md",
                     "docs/prompts_overview.md",
                     "docs/fixtures_guide.md",
                     "ACCEPTANCE_NOTES.md"):
            with self.subTest(path=path):
                self.assertEqual(self.classify(path), "doc")


class TestChangeAuditModeAwareness(ValidatorCheckTestCase):
    """The change audit's forbidden set follows the run mode.

    Bootstrap keeps the original strictness; implementation forbids only
    pinned upstream paths (adding engine code is the point of the run);
    frozen acceptance is measured against RUN_STATE.frozen_sha rather than
    the branch base. Regression for the live defect where the validator
    could never PASS on an implementation commit that added production or
    evaluator-named files.
    """

    def audit(self, base=None):
        return self.run_check(vcp.check_no_production_changes, base)["no_production_files_changed"]

    def test_bootstrap_mode_still_rejects_production_changes(self):
        (self.project.path / "engine_core.py").write_text("x = 1\n", encoding="utf-8")
        check = self.audit()
        self.assertFalse(check["ok"])
        self.assertIn("engine_core.py", check["detail"])

    def test_implementation_mode_accepts_production_and_evaluator_changes(self):
        self.project.set_mode("implementation")
        (self.project.path / "engine_core.py").write_text("x = 1\n", encoding="utf-8")
        evaluator_dir = self.project.path / "acceptance"
        evaluator_dir.mkdir()
        (evaluator_dir / "gate.py").write_text("y = 2\n", encoding="utf-8")
        check = self.audit()
        self.assertTrue(check["ok"], check["detail"])
        self.assertEqual(check["forbidden_categories"], ["upstream_protected"])

    def test_implementation_mode_still_rejects_pinned_upstream_changes(self):
        self.project.set_mode("implementation")
        self.project.write_state("UPSTREAM_PROTECTED_PATHS.json", {
            "schema_version": 1, "status": "INITIALIZED",
            "repositories": [], "protected_paths": [{"path": "third_party/concordia/"}],
        })
        target = self.project.path / "third_party" / "concordia" / "core.py"
        target.parent.mkdir(parents=True)
        target.write_text("hacked = True\n", encoding="utf-8")
        check = self.audit()
        self.assertFalse(check["ok"])
        self.assertIn("third_party/concordia/core.py", check["detail"])

    def test_frozen_acceptance_measures_against_frozen_sha(self):
        self.project._git("checkout", "-q", "-b", "impl")
        (self.project.path / "engine_core.py").write_text("x = 1\n", encoding="utf-8")
        self.project._git("add", "-A")
        self.project._git("commit", "-q", "-m", "engine code")
        frozen = self.project.head_sha()
        self.project.set_mode("frozen_acceptance", frozen_sha=frozen)
        check = self.audit()
        # The production diff versus main predates the freeze; nothing changed
        # since frozen_sha, so the frozen scope is intact.
        self.assertTrue(check["ok"], check["detail"])
        (self.project.path / "engine_core.py").write_text("x = 2\n", encoding="utf-8")
        check = self.audit()
        self.assertFalse(check["ok"])
        self.assertIn("engine_core.py", check["detail"])

    def test_frozen_acceptance_without_frozen_sha_fails(self):
        self.project.set_mode("frozen_acceptance", frozen_sha=None)
        check = self.audit()
        self.assertFalse(check["ok"])
        self.assertIn("frozen_sha", check["detail"])


class TestPhaseReceiptDiscipline(ValidatorCheckTestCase):
    """Completed tasks need completion-grade receipts (review finding H2)."""

    def complete_task(self, task_id="phase-x"):
        self.project.set_tasks([{
            "id": task_id, "subject": "s", "description": "d",
            "owner": "implementation-agent", "owner_type": "subagent",
            "status": "complete",
            "required_receipts": [{"task_id": task_id, "must_pass": True}],
        }], status="INITIALIZED")
        return task_id

    def check(self):
        return self.run_check(vcp.check_phase_receipt_discipline)["phase_receipt_discipline"]

    def test_clean_worktree_receipt_passes(self):
        task = self.complete_task()
        self.project.add_receipt(task, worktree_clean=True)
        result = self.check()
        self.assertTrue(result["ok"], result["detail"])
        self.assertEqual(result["checked"], 1)

    def test_dirty_receipt_without_content_proof_fails(self):
        task = self.complete_task()
        self.project.add_receipt(task, worktree_clean=False)
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertIn("no configuration_hashes to prove content continuity", result["detail"])

    def test_dirty_receipt_with_matching_config_hashes_passes(self):
        task = self.complete_task()
        artifact = self.project.path / "module.py"
        artifact.write_text("x = 1\n", encoding="utf-8")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.project.add_receipt(task, worktree_clean=False,
                                 configuration_hashes={"module.py": digest})
        result = self.check()
        self.assertTrue(result["ok"], result["detail"])

    def test_content_drift_after_receipt_fails(self):
        task = self.complete_task()
        artifact = self.project.path / "module.py"
        artifact.write_text("x = 1\n", encoding="utf-8")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.project.add_receipt(task, worktree_clean=False,
                                 configuration_hashes={"module.py": digest})
        artifact.write_text("x = 2\n", encoding="utf-8")
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertIn("no longer matches", result["detail"])

    def test_label_only_hashes_are_not_continuity_proof(self):
        task = self.complete_task()
        self.project.add_receipt(task, worktree_clean=False,
                                 configuration_hashes={"a_label": "0" * 64})
        result = self.check()
        self.assertFalse(result["ok"])

    def test_missing_passing_receipt_fails_and_incomplete_tasks_are_ignored(self):
        task = self.complete_task()
        self.project.add_receipt(task, exit_code=1)
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertIn("no passing receipt", result["detail"])
        self.project.set_tasks([{
            "id": "wip", "subject": "s", "description": "d",
            "owner": "implementation-agent", "owner_type": "subagent",
            "status": "in_progress",
            "required_receipts": [{"task_id": "wip", "must_pass": True}],
        }], status="INITIALIZED")
        result = self.check()
        self.assertTrue(result["ok"], result["detail"])
        self.assertEqual(result["checked"], 0)

    def test_newest_is_chronological_not_file_order(self):
        """Regression: receipt file names embed the SHA prefix, so file order
        is lexicographic-by-SHA. An OLD dirty receipt whose SHA sorts late
        must not shadow a genuinely newer clean receipt."""
        task = self.complete_task()
        # Old dirty receipt; sha "fff..." sorts lexicographically LAST.
        self.project.add_receipt(task, sha="f" * 40, worktree_clean=False,
                                 finished_at="2026-01-01T00:00:10+00:00")
        # Newer clean receipt; sha "222..." sorts lexicographically FIRST.
        self.project.add_receipt(task, sha="2" * 40, worktree_clean=True,
                                 finished_at="2026-01-02T00:00:10+00:00")
        result = self.check()
        self.assertTrue(result["ok"], result["detail"])

    def test_chronologically_newest_dirty_receipt_is_not_masked_by_old_clean_one(self):
        """The inverse direction: a stale clean receipt sorting late by file
        name must not hide that the actual newest receipt lacks proof."""
        task = self.complete_task()
        # Old clean receipt; sha "fff..." sorts lexicographically LAST.
        self.project.add_receipt(task, sha="f" * 40, worktree_clean=True,
                                 finished_at="2026-01-01T00:00:10+00:00")
        # Newer dirty no-proof receipt; sha "222..." sorts FIRST by file name.
        self.project.add_receipt(task, sha="2" * 40, worktree_clean=False,
                                 finished_at="2026-01-02T00:00:10+00:00")
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertIn("no configuration_hashes", result["detail"])


class TestAuditExemptProtectedMetadata(ValidatorCheckTestCase):
    """audit_exempt entries skip the branch-diff audit but stay write-protected."""

    def audit(self, base=None):
        return self.run_check(vcp.check_no_production_changes, base)["no_production_files_changed"]

    def test_exempt_metadata_not_flagged_but_source_trees_still_are(self):
        self.project.set_mode("implementation")
        self.project.write_state("UPSTREAM_PROTECTED_PATHS.json", {
            "schema_version": 1, "status": "INITIALIZED", "repositories": [],
            "protected_paths": [
                {"path": "third_party/LOCK.json", "audit_exempt": True},
                {"path": "third_party/vendor/"},
            ],
        })
        lock = self.project.path / "third_party" / "LOCK.json"
        lock.parent.mkdir(parents=True)
        lock.write_text("{}\n", encoding="utf-8")
        check = self.audit()
        self.assertTrue(check["ok"], check["detail"])
        # The gate category is unchanged: writes are still blocked by PreToolUse.
        self.assertEqual(hs.classify_path("third_party/LOCK.json", self.project.path),
                         "upstream_protected")
        vendor = self.project.path / "third_party" / "vendor" / "x.py"
        vendor.parent.mkdir(parents=True)
        vendor.write_text("x = 1\n", encoding="utf-8")
        check = self.audit()
        self.assertFalse(check["ok"])
        self.assertIn("third_party/vendor/x.py", check["detail"])


class TestUpstreamCheckoutIntegrity(ValidatorCheckTestCase):
    """The pinned checkouts are continuously verified, not point-in-time.

    Regression for the adversarial-review finding that nothing enforced the
    external checkouts staying at their recorded SHAs.
    """

    def make_checkout(self):
        checkout = Project.create()
        self.addCleanup(checkout.destroy)
        return checkout

    def register(self, checkout, pinned=None, path=None):
        self.project.write_state("UPSTREAM_PROTECTED_PATHS.json", {
            "schema_version": 1, "status": "INITIALIZED",
            "repositories": [{
                "name": "fake-upstream",
                "local_checkout": path if path is not None else str(checkout.path),
                "baseline_sha_at_initialization":
                    pinned if pinned is not None else checkout.head_sha(),
            }],
            "protected_paths": [],
        })

    def check(self):
        return self.run_check(vcp.check_upstream_checkout_integrity)[
            "upstream_checkouts_integrity"]

    def test_clean_checkout_at_pinned_sha_passes(self):
        checkout = self.make_checkout()
        self.register(checkout)
        result = self.check()
        self.assertTrue(result["ok"], result["detail"])
        self.assertEqual(result["checked"], 1)

    def test_local_modification_is_detected(self):
        checkout = self.make_checkout()
        self.register(checkout)
        (checkout.path / "hacked.py").write_text("x = 1\n", encoding="utf-8")
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertIn("local modifications", result["detail"])

    def test_sha_drift_is_detected(self):
        checkout = self.make_checkout()
        self.register(checkout, pinned="0" * 40)
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertIn("does not match", result["detail"])

    def test_absent_checkout_is_noted_not_failed(self):
        checkout = self.make_checkout()
        self.register(checkout, path=str(checkout.path / "does-not-exist"))
        result = self.check()
        self.assertTrue(result["ok"], result["detail"])
        self.assertIn("absent", result["detail"])
        self.assertEqual(result["checked"], 0)

    def test_absolute_checkout_paths_classify_as_upstream_protected(self):
        checkout = self.make_checkout()
        self.register(checkout)
        inside = str(checkout.path / "engine" / "core.py")
        self.assertEqual(hs.classify_path(inside, self.project.path), "upstream_protected")
        self.assertEqual(hs.classify_path("/somewhere/else/file.py", self.project.path),
                         "external")


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
        # The check skips when there is no comparable base ref -- a fresh clone
        # of a single branch has nothing to diff against. A skip reports no
        # changed_paths at all, which is not the same as reporting an empty
        # list, so read it defensively rather than assuming the key is present.
        if "changed_paths" not in check:
            self.assertIn("skipped", check["detail"])
            self.skipTest(f"no comparable base ref: {check['detail']}")
        # The forbidden set is mode-dependent (bootstrap discipline vs
        # implementation vs frozen acceptance); the check reports the set it
        # enforced, and that report is the single source of truth here.
        forbidden = set(check.get("forbidden_categories") or [])
        self.assertTrue(forbidden, "the check must report its forbidden categories")
        self.assertIn("upstream_protected", forbidden,
                      "pinned upstream source must be inviolable in every mode")
        for path in check["changed_paths"]:
            with self.subTest(path=path):
                category = hs.classify_path(path, REPO_ROOT)
                if category == "upstream_protected" and hs.is_upstream_audit_exempt(path, REPO_ROOT):
                    continue  # write-protected metadata born on this branch
                self.assertNotIn(category, forbidden,
                                 f"{path} is in a category forbidden for this mode")


if __name__ == "__main__":
    unittest.main()
