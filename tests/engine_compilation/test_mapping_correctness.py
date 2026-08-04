"""Mapping-correctness proofs for the compiler-to-Concordia adapter.

Directive ("Mapping correctness tests"): every compiler field mapped or
explicitly retained in a sidecar; no silent discard; stable code-owned
actor identifiers; unknown ``visible_to`` names fail before simulation;
private and shared context stay separate; starting-event order and
timestamps preserved; the base world is identical before different
interventions; identical input produces a byte-identical initialization
plan.  Each test names the mapping-table row it proves
(docs/engine_migration/COMPILER_TO_CONCORDIA_MAPPING.md).
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from datetime import datetime

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine compilation suite requires Python >= 3.12 (Concordia "
        "floor); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from compilation_helpers import (COMPILED_ARTIFACT_VECTOR_DIR,
                                 EVENT_ALICE_ONLY_CANARY,
                                 PRIVATE_ALICE_CANARY, PRIVATE_BOB_CANARY,
                                 REPO_ROOT, SEED, SHARED_CANARY,
                                 adapt_canary_scene, build_plan,
                                 canary_manifest, make_evaluator_spec,
                                 manifest_leaves, scripted_models_for_plan)
from sworldmodel.compilation import (adapt_compiled_scene, derive_actor_ids)
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.counterfactuals.branch import (diff_plans,
                                                insertion_path_prefix)
from sworldmodel.decision.contracts import (ContractValidationError,
                                            InterventionCandidate,
                                            SCHEMA_VERSION, canonical_time)

CANARY_START = "2026-08-03T09:00:00Z"
CANARY_CUTOFF = "2026-08-04T09:00:00Z"


def _adapt(manifest, **overrides):
    arguments = {
        "question": "Which candidate action works best for the opener?",
        "start": CANARY_START,
        "cutoff": CANARY_CUTOFF,
        "insertion_actor": "Alice",
        "compiler_version": "vtest_mapping",
        "evidence_mode": "scripted_test_vector",
    }
    arguments.update(overrides)
    return adapt_compiled_scene(manifest, **arguments)


def _codes(excinfo):
    return set(excinfo.value.codes())


def _paths(excinfo):
    return set(excinfo.value.paths())


# ---------------------------------------------------------------------------
# Stable code-owned identifiers
# ---------------------------------------------------------------------------

def test_adapter_output_is_a_validated_world_with_stable_code_owned_ids():
    scene = adapt_canary_scene()
    assert scene.actor_id_by_name == {"Alice": "alice", "Bob": "bob"}
    world = scene.world
    assert [actor.actor_id for actor in world.actors] == ["alice", "bob"]
    assert [actor.name for actor in world.actors] == ["Alice", "Bob"]
    assert world.intervention_insertion_point.actor_id == "alice"
    assert world.starting_events[0].visible_to == ("alice",)
    # The identifier binding is stable across independent adaptations.
    again = adapt_canary_scene()
    assert again.actor_id_by_name == scene.actor_id_by_name
    assert again.world.world_id == world.world_id


def test_actor_name_id_rule_and_collision_suffixes_are_deterministic():
    names = ["Anne Marie", "Anne-Marie", "ANNE  marie"]
    first = derive_actor_ids(names)
    assert first == {"Anne Marie": "anne_marie",
                     "Anne-Marie": "anne_marie_2",
                     "ANNE  marie": "anne_marie_3"}
    assert derive_actor_ids(names) == first  # stable, order-derived


def test_undecodable_actor_names_fail_loudly_with_all_defects():
    with pytest.raises(ContractValidationError) as excinfo:
        derive_actor_ids(["!!!", "9Lives", "Valid Name"])
    assert _codes(excinfo) == {"invalid_id"}
    assert _paths(excinfo) == {"actors[0].name", "actors[1].name"}
    with pytest.raises(ContractValidationError) as excinfo:
        derive_actor_ids(["Twin", "Twin"])
    assert "duplicate_id" in _codes(excinfo)


def test_insertion_actor_resolves_by_name_or_derived_id_never_by_guess():
    manifest = canary_manifest()
    by_name = _adapt(manifest, insertion_actor="Bob")
    assert by_name.world.intervention_insertion_point.actor_id == "bob"
    by_id = _adapt(manifest, insertion_actor="bob")
    assert by_id.world.intervention_insertion_point.actor_id == "bob"
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(manifest, insertion_actor="Stranger")
    assert _codes(excinfo) == {"unknown_reference"}
    assert _paths(excinfo) == {"insertion_actor"}
    # A reference that is one actor's name AND a different actor's
    # derived identifier is ambiguous and refused, never guessed.
    tricky = canary_manifest()
    tricky["actors"] = [
        {"name": "Team Lead", "private_context": "Holds the first brief."},
        {"name": "team_lead", "private_context": "Holds the second brief."},
    ]
    tricky["starting_events"] = []
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(tricky, insertion_actor="team_lead")
    assert "ambiguous" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Loud failure on malformed or unresolvable input
# ---------------------------------------------------------------------------

def test_unknown_visible_to_names_fail_before_any_simulation():
    manifest = canary_manifest()
    manifest["starting_events"][0]["visible_to"] = ["Stranger"]
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(manifest)
    assert _codes(excinfo) == {"unknown_reference"}
    assert _paths(excinfo) == {"starting_events[0].visible_to[0]"}
    assert "never fuzzy-matches" in str(excinfo.value)


def test_empty_visible_to_is_refused_as_documented_contract_narrowing():
    manifest = canary_manifest()
    manifest["starting_events"][0]["visible_to"] = []
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(manifest)
    assert _codes(excinfo) == {"empty_collection"}
    assert "COMPILER_TO_CONCORDIA_MAPPING.md" in str(excinfo.value)


def test_duplicate_visible_to_entries_are_rejected():
    manifest = canary_manifest()
    manifest["starting_events"][0]["visible_to"] = ["Alice", "Alice"]
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(manifest)
    assert "duplicate_id" in _codes(excinfo)


def test_manifest_shape_gate_rejects_unknown_missing_and_wrong_types():
    manifest = canary_manifest()
    manifest["extra_field"] = "surplus"
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(manifest)
    assert "unknown top-level fields" in str(excinfo.value)

    manifest = canary_manifest()
    del manifest["resolution"]
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(manifest)
    assert "missing required field 'resolution'" in str(excinfo.value)

    manifest = canary_manifest()
    manifest["actors"] = []
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(manifest)
    assert "actors must be a non-empty array" in str(excinfo.value)

    with pytest.raises(ContractValidationError):
        _adapt(["not", "a", "mapping"])


def test_malformed_or_out_of_window_times_fail_loudly():
    # Naive event time: caught by the production shape gate.
    manifest = canary_manifest()
    manifest["starting_events"][0]["time"] = "2026-08-03T09:00:00"
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(manifest)
    assert "timezone-aware" in str(excinfo.value)

    # Event after the cutoff: caught by contract semantic validation,
    # never clamped or dropped.
    manifest = canary_manifest()
    manifest["starting_events"][0]["time"] = "2026-09-01T09:00:00Z"
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(manifest)
    assert "timing_out_of_range" in _codes(excinfo)

    # Naive start argument; inverted window.
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(canary_manifest(), start="2026-08-03T09:00:00")
    assert "naive_datetime" in _codes(excinfo)
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(canary_manifest(), cutoff="2026-08-01T09:00:00Z")
    assert "cutoff must be strictly after start" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Every field mapped or in the sidecar; nothing silently discarded
# ---------------------------------------------------------------------------

def _assert_full_leaf_coverage(manifest, scene):
    world = scene.world
    world_events = list(world.starting_events)
    for path, kind, value in manifest_leaves(manifest):
        if kind == "name":
            assert any(actor.name == value for actor in world.actors), path
        elif kind == "private_context":
            assert any(actor.private_context == value
                       for actor in world.actors), path
        elif kind == "shared_context":
            assert world.shared_context == value, path
        elif kind == "event_time":
            index = int(path.split("[")[1].split("]")[0])
            supplied = datetime.fromisoformat(value.replace("Z", "+00:00"))
            assert world_events[index].time == supplied, path
        elif kind == "event_description":
            index = int(path.split("[")[1].split("]")[0])
            assert world_events[index].description == value, path
        elif kind == "visible_to":
            index = int(path.split("[")[1].split("]")[0])
            mapped = scene.actor_id_by_name[value]
            assert mapped in world_events[index].visible_to, path
        elif kind == "resolution":
            assert world.success_criteria == value, path
        else:  # pragma: no cover - the walker names every kind
            raise AssertionError(f"unclassified leaf {path}")


def test_every_manifest_leaf_is_mapped_with_nothing_silently_discarded():
    # (a) the synthetic canary manifest;
    manifest = canary_manifest()
    _assert_full_leaf_coverage(manifest, _adapt(manifest))
    # (b) the committed REAL compiled manifest (production vocabulary
    # lives in the committed vector, never in production code).
    with open(COMPILED_ARTIFACT_VECTOR_DIR / "final_scene_manifest.json",
              encoding="utf-8") as handle:
        compiled = json.load(handle)
    with open(COMPILED_ARTIFACT_VECTOR_DIR / "input.json",
              encoding="utf-8") as handle:
        compile_input = json.load(handle)
    scene = adapt_compiled_scene(
        compiled,
        question=compile_input["question"],
        start=compile_input["start"],
        cutoff=compile_input["cutoff"],
        insertion_actor=compiled["actors"][0]["name"],
        compiler_version=compile_input["compiler_version"],
        evidence_mode="model_memory_unverified",
    )
    _assert_full_leaf_coverage(compiled, scene)
    # Surrounding compile metadata: mapped or in the sidecar, verbatim.
    inputs = scene.sidecar["compile_inputs"]
    assert inputs["question"] == compile_input["question"]
    assert inputs["start"] == compile_input["start"]
    assert inputs["cutoff"] == compile_input["cutoff"]
    assert inputs["compiler_version"] == compile_input["compiler_version"]
    hashes = scene.world.compiler_provenance.artifact_hashes
    assert set(hashes) >= {"manifest_canonical_sha256", "question_sha256"}
    assert scene.world.compiler_provenance.version \
        == compile_input["compiler_version"]


def test_unknown_manifest_fields_cannot_be_silently_dropped():
    # By construction nothing unknown can pass: the production shape gate
    # rejects any field outside the four -- proven at actor and event
    # level too.
    manifest = canary_manifest()
    manifest["actors"][0]["role"] = "surplus"
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(manifest)
    assert "unknown fields" in str(excinfo.value)
    manifest = canary_manifest()
    manifest["starting_events"][0]["channel"] = "surplus"
    with pytest.raises(ContractValidationError) as excinfo:
        _adapt(manifest)
    assert "unknown fields" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Separation, ordering, base-world identity, determinism
# ---------------------------------------------------------------------------

def test_private_and_shared_context_stay_separate_in_world_and_plan():
    scene = adapt_canary_scene()
    plan = build_plan(scene.world)
    configs = {config.actor_id: config for config in plan.actor_configs}
    assert PRIVATE_ALICE_CANARY in configs["alice"].private_init_data
    assert PRIVATE_BOB_CANARY in configs["bob"].private_init_data
    assert PRIVATE_ALICE_CANARY not in configs["bob"].private_init_data
    assert PRIVATE_BOB_CANARY not in configs["alice"].private_init_data
    assert PRIVATE_ALICE_CANARY not in plan.shared_init_data
    assert PRIVATE_BOB_CANARY not in plan.shared_init_data
    for actor_id, observations in plan.initial_observations.items():
        joined = "\n".join(observations)
        assert PRIVATE_ALICE_CANARY not in joined, actor_id
        assert PRIVATE_BOB_CANARY not in joined, actor_id
        assert SHARED_CANARY in joined, actor_id
    assert SHARED_CANARY in plan.shared_init_data
    gm_events = "\n".join(plan.gm_initial_events)
    assert PRIVATE_ALICE_CANARY not in gm_events
    assert PRIVATE_BOB_CANARY not in gm_events


def test_starting_event_order_and_timestamps_are_preserved():
    manifest = canary_manifest()
    # Declared deliberately OUT of chronological order, mixed offsets.
    manifest["starting_events"] = [
        {"time": "2026-08-03T15:00:00Z",
         "description": "Third-hour signal reaches both desks.",
         "visible_to": ["Alice", "Bob"]},
        {"time": "2026-08-03T11:00:00+02:00",
         "description": "Early-morning signal reaches one desk.",
         "visible_to": ["Bob"]},
        {"time": "2026-08-03T12:00:00Z",
         "description": "Midday signal reaches one desk.",
         "visible_to": ["Alice"]},
    ]
    scene = _adapt(manifest, cutoff="2026-08-04T09:00:00Z")
    events = list(scene.world.starting_events)
    assert [event.description for event in events] == [
        "Third-hour signal reaches both desks.",
        "Early-morning signal reaches one desk.",
        "Midday signal reaches one desk.",
    ]
    # Instants preserved exactly; +02:00 input is the same instant as
    # its canonical UTC rendering.
    assert canonical_time(events[0].time) == "2026-08-03T15:00:00Z"
    assert canonical_time(events[1].time) == "2026-08-03T09:00:00Z"
    assert canonical_time(events[2].time) == "2026-08-03T12:00:00Z"
    plan = build_plan(scene.world)
    assert list(plan.gm_initial_events) == [
        "[2026-08-03T15:00:00Z] Third-hour signal reaches both desks.",
        "[2026-08-03T09:00:00Z] Early-morning signal reaches one desk.",
        "[2026-08-03T12:00:00Z] Midday signal reaches one desk.",
    ]
    # Per-actor observations keep the declared order of visible events.
    alice_observations = plan.initial_observations["alice"]
    assert alice_observations[1].startswith("[2026-08-03T15:00:00Z]")
    assert alice_observations[2].startswith("[2026-08-03T12:00:00Z]")


def test_same_input_twice_yields_byte_identical_world_and_plan():
    first = adapt_canary_scene()
    second = adapt_canary_scene()
    assert first.world.canonical_json() == second.world.canonical_json()
    assert first.sidecar == second.sidecar
    plan_one = build_plan(first.world)
    plan_two = build_plan(second.world)
    assert plan_one.canonical_json() == plan_two.canonical_json()
    assert plan_one.plan_id == plan_two.plan_id


def _candidate(candidate_id: str, action: str) -> InterventionCandidate:
    return InterventionCandidate.from_dict({
        "contract_type": InterventionCandidate.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "summary": " ".join(action.split())[:120],
        "action": action,
        "decision_owner": "alice",
        "timing": CANARY_START,
        "constraints": [],
        "provenance": {"source": "user_supplied",
                       "generator_config_hash": ""},
    })


def test_base_world_identical_before_different_interventions():
    scene = adapt_canary_scene()
    spec = make_evaluator_spec()
    candidates = (_candidate("path_one", "Open with the first approach."),
                  _candidate("path_two", "Open with the second approach."))

    def factory(candidate, branch_seed):
        plan = build_plan(scene.world, evaluator_spec=spec)
        turn_texts = {"alice": candidate.action}
        return scripted_models_for_plan(plan, turn_texts)

    run = run_candidates_detailed(
        scene.world, candidates, model_factory=factory, seed=SEED,
        max_steps=2, evaluator_spec=spec,
        model_config={"kind": "scripted_test_models"})
    # The frozen base is byte-identical to an independently built plan.
    reference = build_plan(scene.world, evaluator_spec=spec)
    assert run.base_plan_content_hash == reference.content_hash()
    # Every branch differs from the base ONLY at the single insertion
    # boundary of the insertion actor.
    prefix = insertion_path_prefix(run.base_plan)
    assert prefix == "initial_observations.alice"
    for candidate in candidates:
        changed = diff_plans(run.base_plan,
                             run.branch_plans[candidate.candidate_id])
        assert changed, candidate.candidate_id
        for path in changed:
            assert path == prefix or path.startswith(prefix + "["), path
    for result in run.results:
        assert result.infrastructure_errors == ()


# ---------------------------------------------------------------------------
# Import isolation: the adapter package never imports the compiler at
# import time, and its only compiler reference is the lazy shape gate.
# ---------------------------------------------------------------------------

_IMPORT_PROBE = r"""
import json
import sys

import sworldmodel.compilation
after_package_import = sorted(
    name for name in sys.modules
    if name == "compiler" or name.startswith("compiler."))

from sworldmodel.compilation import adapt_compiled_scene
try:
    adapt_compiled_scene(
        {"actors": [{"name": "Probe One", "private_context": "holds a"}],
         "shared_context": "shared line",
         "starting_events": [],
         "resolution": "resolved from history"},
        question="which action works",
        start="2026-08-03T09:00:00Z",
        cutoff="2026-08-04T09:00:00Z",
        insertion_actor="Probe One",
        compiler_version="vprobe",
        evidence_mode="probe")
    adapted = True
except Exception:
    adapted = False
after_call = sorted(
    name for name in sys.modules
    if name == "compiler" or name.startswith("compiler."))
print(json.dumps({"after_package_import": after_package_import,
                  "after_call": after_call, "adapted": adapted}))
"""


def test_importing_the_compilation_package_pulls_no_compiler_module():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    completed = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=env,
        timeout=180, check=False)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    # Import time: ZERO compiler modules.
    assert report["after_package_import"] == []
    # Call time: the lazy production shape gate pulls the compiler
    # package (whose __init__ transitively loads its sibling modules,
    # documented side-effect-free); the adapter still works offline
    # with no credentials.
    assert report["adapted"] is True
    assert "compiler.scene_schema" in report["after_call"]


def test_static_imports_reference_only_the_declared_compiler_gate():
    package_dir = REPO_ROOT / "sworldmodel" / "compilation"
    compiler_imports = []
    module_level_compiler_imports = []
    for path in sorted(package_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name == "compiler" or name.startswith("compiler."):
                    compiler_imports.append((path.name, name))
        for node in tree.body:  # module level only
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name == "compiler" or name.startswith("compiler."):
                    module_level_compiler_imports.append((path.name, name))
    # No module-level compiler import anywhere in the package.
    assert module_level_compiler_imports == []
    # The ONLY compiler reference in the whole package is the lazy
    # production shape gate.
    assert compiler_imports == [
        ("existing_compiler_adapter.py", "compiler.scene_schema")]
