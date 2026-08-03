"""Compiled ``out_dir`` artifact-set loading: complete capture, loud
refusal of incomplete or failed sets, and dict-vs-file-mode agreement.

The committed vector ``vectors/compiled_scene_artifact/`` is a verbatim
copy of a real production compile (metadata subset); a guard test proves
the copy still matches the live committed artifact set when present.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys

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
                                 LIVE_ARTIFACT_DIR)
from sworldmodel.compilation import (adapt_compiled_artifacts,
                                     adapt_compiled_scene)
from sworldmodel.decision.contracts import ContractValidationError

INSERTION = "Jordan Reyes"


def _load(name: str):
    with open(COMPILED_ARTIFACT_VECTOR_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _copy_vector(tmp_path, exclude=(), mutate=None):
    """A scratch copy of the committed vector for destructive cases."""
    target = tmp_path / "artifact_set"
    target.mkdir(parents=True)
    for path in sorted(COMPILED_ARTIFACT_VECTOR_DIR.iterdir()):
        if path.is_file() and path.name not in exclude:
            shutil.copy(path, target / path.name)
    if mutate:
        mutate(target)
    return target


def test_committed_vector_matches_live_artifacts_when_present():
    if not LIVE_ARTIFACT_DIR.is_dir():
        pytest.skip("live compiled artifact directory not present")
    for path in sorted(COMPILED_ARTIFACT_VECTOR_DIR.iterdir()):
        if not path.is_file():
            continue
        live = LIVE_ARTIFACT_DIR / path.name
        assert live.is_file(), f"{path.name} missing from live artifacts"
        assert path.read_bytes() == live.read_bytes(), (
            f"{path.name}: committed vector diverged from the live "
            "compiled artifact it was copied from")


def test_out_dir_mode_maps_the_final_manifest_and_hashes_every_file():
    scene = adapt_compiled_artifacts(COMPILED_ARTIFACT_VECTOR_DIR,
                                     insertion_actor=INSERTION)
    manifest = _load("final_scene_manifest.json")
    world = scene.world
    assert [actor.name for actor in world.actors] \
        == [actor["name"] for actor in manifest["actors"]]
    assert [actor.private_context for actor in world.actors] \
        == [actor["private_context"] for actor in manifest["actors"]]
    assert world.shared_context == manifest["shared_context"]
    assert world.success_criteria == manifest["resolution"]
    assert len(world.starting_events) \
        == len(manifest["starting_events"])
    assert world.intervention_insertion_point.actor_id == "jordan_reyes"
    # Every regular file in the set is hashed into the provenance
    # sidecar, byte-exactly.
    hashes = world.compiler_provenance.artifact_hashes
    for path in sorted(COMPILED_ARTIFACT_VECTOR_DIR.iterdir()):
        if not path.is_file():
            continue
        assert hashes[path.name] \
            == hashlib.sha256(path.read_bytes()).hexdigest(), path.name
    assert "manifest_canonical_sha256" in hashes
    assert "question_sha256" in hashes


def test_out_dir_metadata_lands_in_the_sidecar_verbatim():
    scene = adapt_compiled_artifacts(COMPILED_ARTIFACT_VECTOR_DIR,
                                     insertion_actor=INSERTION)
    files = scene.sidecar["artifact_files"]
    # Every parsed metadata file rides the sidecar verbatim -- including
    # compile inputs the contract has no slot for (question, context,
    # evidence) and the recorded metrics/review/reports.
    for name in ("input.json", "final_scene_manifest.json",
                 "compiler_metrics.json", "scene_manifest.json",
                 "scene_review.json", "normalization_report.json",
                 "validation_report.json"):
        assert files[name] == _load(name), name
    compile_input = files["input.json"]
    assert "question" in compile_input
    assert "context" in compile_input   # optional compile input, kept
    assert "evidence" in compile_input  # optional compile input, kept
    inputs = scene.sidecar["compile_inputs"]
    assert inputs["question"] == compile_input["question"]
    assert inputs["evidence_mode"] \
        == files["compiler_metrics.json"]["evidence_mode"]


def test_legacy_runtime_world_id_is_preserved_in_sidecar_not_adopted():
    scene = adapt_compiled_artifacts(COMPILED_ARTIFACT_VECTOR_DIR,
                                     insertion_actor=INSERTION)
    legacy = scene.sidecar["artifact_files"]["compiler_metrics.json"][
        "world_id"]
    assert legacy  # the completed-compile marker
    # The adapter's world identity is its own code-owned derivation,
    # bound to the manifest content -- never the legacy runtime's id.
    assert scene.world.world_id != legacy
    assert scene.world.world_id \
        == scene.sidecar["canonical"]["world_id"]


def test_out_dir_and_dict_modes_agree_on_world_content():
    from_files = adapt_compiled_artifacts(COMPILED_ARTIFACT_VECTOR_DIR,
                                          insertion_actor=INSERTION)
    manifest = _load("final_scene_manifest.json")
    compile_input = _load("input.json")
    metrics = _load("compiler_metrics.json")
    from_dict = adapt_compiled_scene(
        manifest,
        question=compile_input["question"],
        start=compile_input["start"],
        cutoff=compile_input["cutoff"],
        insertion_actor=INSERTION,
        compiler_version=compile_input["compiler_version"],
        evidence_mode=metrics["evidence_mode"],
    )
    left = from_files.world.to_dict()
    right = from_dict.world.to_dict()
    # File hashes exist only where files exist; everything else is
    # byte-identical, including the code-owned world identity.
    left["compiler_provenance"]["artifact_hashes"] = None
    right["compiler_provenance"]["artifact_hashes"] = None
    assert left == right
    assert from_files.world.world_id == from_dict.world.world_id
    assert from_files.actor_id_by_name == from_dict.actor_id_by_name


def test_missing_required_files_are_refused(tmp_path):
    for missing in ("final_scene_manifest.json", "input.json",
                    "compiler_metrics.json"):
        target = _copy_vector(tmp_path / missing.replace(".", "_"),
                              exclude=(missing,))
        with pytest.raises(ContractValidationError) as excinfo:
            adapt_compiled_artifacts(target, insertion_actor=INSERTION)
        assert missing in str(excinfo.value)
    with pytest.raises(ContractValidationError) as excinfo:
        adapt_compiled_artifacts(tmp_path / "no_such_dir",
                                 insertion_actor=INSERTION)
    assert "not a directory" in str(excinfo.value)


def test_incomplete_or_failed_compiles_are_refused(tmp_path):
    # (a) metrics without the completed-compile world_id marker.
    def drop_world_id(target):
        metrics = json.loads(
            (target / "compiler_metrics.json").read_text())
        del metrics["world_id"]
        (target / "compiler_metrics.json").write_text(
            json.dumps(metrics))
    target = _copy_vector(tmp_path / "no_marker", mutate=drop_world_id)
    with pytest.raises(ContractValidationError) as excinfo:
        adapt_compiled_artifacts(target, insertion_actor=INSERTION)
    assert "COMPLETED compile" in str(excinfo.value)

    # (b) a recorded validation failure.
    def add_validation_errors(target):
        (target / "validation_report.json").write_text(json.dumps(
            {"errors": ["synthetic recorded defect"], "warnings": []}))
    target = _copy_vector(tmp_path / "failed_validation",
                          mutate=add_validation_errors)
    with pytest.raises(ContractValidationError) as excinfo:
        adapt_compiled_artifacts(target, insertion_actor=INSERTION)
    assert "synthetic recorded defect" in str(excinfo.value)

    # (c) internal inconsistency between metrics and compile input.
    def skew_version(target):
        metrics = json.loads(
            (target / "compiler_metrics.json").read_text())
        metrics["compiler_version"] = "other_version"
        (target / "compiler_metrics.json").write_text(
            json.dumps(metrics))
    target = _copy_vector(tmp_path / "skewed", mutate=skew_version)
    with pytest.raises(ContractValidationError) as excinfo:
        adapt_compiled_artifacts(target, insertion_actor=INSERTION)
    assert "internally inconsistent" in str(excinfo.value)

    # (d) unreadable JSON in a required file.
    def truncate_manifest(target):
        (target / "final_scene_manifest.json").write_text("{not json")
    target = _copy_vector(tmp_path / "truncated",
                          mutate=truncate_manifest)
    with pytest.raises(ContractValidationError) as excinfo:
        adapt_compiled_artifacts(target, insertion_actor=INSERTION)
    assert "not valid JSON" in str(excinfo.value)
