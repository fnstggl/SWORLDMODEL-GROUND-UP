"""Freeze-hash stability and evidence-manifest schema.

Pure-stdlib harness modules: these run on either interpreter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import (evidence as ev,  # noqa: E402
                                               freeze as fz)
from experiments.full_trace_validation import (  # noqa: E402
    scenario_peter as scenario)

WINDOW = ("2026-08-04T12:00:00Z", "2026-08-11T12:00:00Z")


def _items():
    payload = scenario.build_problem_payload(
        start_iso=WINDOW[0], cutoff_iso=WINDOW[1], generated=False)
    return scenario.evidence_items(payload)


# ---------------------------------------------------------------------------
# freeze
# ---------------------------------------------------------------------------


def test_hashes_are_stable_across_key_order_and_repetition():
    left = fz.sha256_json({"b": 2, "a": [1, {"z": 0, "y": 1}]})
    right = fz.sha256_json({"a": [1, {"y": 1, "z": 0}], "b": 2})
    assert left == right == fz.sha256_json({"b": 2,
                                            "a": [1, {"z": 0, "y": 1}]})
    assert len(left) == 64
    # canonicalisation is pinned: a silent change to separators, sorting,
    # or encoding would move this value
    assert fz.sha256_json({"a": 1}) == fz.sha256_text('{"a":1}')
    # list ORDER is content, not incidental
    assert fz.sha256_json([1, 2]) != fz.sha256_json([2, 1])


def test_directory_hash_notices_added_renamed_and_edited_files(tmp_path):
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    (tmp_path / "b.txt").write_text("two", encoding="utf-8")
    first = fz.hash_directory(tmp_path)
    assert first["file_count"] == 2
    assert fz.hash_directory(tmp_path)["aggregate"] == first["aggregate"]

    (tmp_path / "b.txt").write_text("two!", encoding="utf-8")
    edited = fz.hash_directory(tmp_path)["aggregate"]
    assert edited != first["aggregate"]

    (tmp_path / "b.txt").rename(tmp_path / "c.txt")
    renamed = fz.hash_directory(tmp_path)["aggregate"]
    assert renamed != edited

    (tmp_path / "d.txt").write_text("three", encoding="utf-8")
    assert fz.hash_directory(tmp_path)["aggregate"] != renamed


def test_a_frozen_entry_can_never_be_overwritten():
    manifest = fz.FreezeManifest(scenario_id="unit")
    manifest.add_json("decision_problem", {"a": 1})
    with pytest.raises(AssertionError, match="already frozen"):
        manifest.add_json("decision_problem", {"a": 2})


def test_an_incomplete_freeze_manifest_is_refused(tmp_path):
    manifest = fz.FreezeManifest(scenario_id="unit")
    manifest.add_json("decision_problem", {"a": 1})
    assert set(manifest.missing_required()) == set(
        fz.REQUIRED_ENTRIES) - {"decision_problem"}
    with pytest.raises(AssertionError, match="incomplete freeze manifest"):
        manifest.write(tmp_path / "freeze_manifest.json")


def test_written_manifest_round_trips(tmp_path):
    manifest = fz.FreezeManifest(scenario_id="unit", note="n")
    for name in fz.REQUIRED_ENTRIES:
        manifest.add_json(name, {"name": name})
    written = manifest.write(tmp_path / "freeze_manifest.json")
    reloaded = fz.load_manifest(tmp_path / "freeze_manifest.json")
    assert reloaded == written
    assert reloaded["missing_required_entries"] == []
    for name in fz.REQUIRED_ENTRIES:
        assert fz.entry_sha(reloaded, name) == fz.sha256_json(
            {"name": name})


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------


def test_the_scenario_manifest_validates_and_classifies_conservatively():
    manifest = ev.build_manifest(
        experiment_id="unit", window_start=WINDOW[0],
        window_cutoff=WINDOW[1], items=_items(),
        actor_names=(scenario.DECISION_OWNER_NAME,
                     scenario.RECIPIENT_NAME))
    counts = manifest["classification_counts"]
    assert set(counts) == set(ev.CLASSIFICATIONS)
    assert counts["UNKNOWN"] >= 1, "an honest manifest records its gaps"
    for item in manifest["items"]:
        assert set(item) == set(ev.ITEM_FIELDS)
    verified = [item for item in manifest["items"]
                if item["classification"] == "PUBLICLY_VERIFIED"]
    for item in verified:
        low = item["claim"].lower()
        assert "inbox" not in low and "calendar" not in low
        assert "prefer" not in low and "opinion" not in low


def test_private_inference_may_never_be_publicly_verified():
    bad = [ev.evidence_item(
        claim="His inbox behaviour means he answers short messages.",
        source="inference from public biography", date="2026-01-01",
        available_before_cutoff=True,
        classification="PUBLICLY_VERIFIED", who_may_know="all",
        used_by_compiler=True, entered_context="shared")]
    with pytest.raises(ev.EvidenceError) as excinfo:
        ev.build_manifest(experiment_id="unit", window_start=WINDOW[0],
                          window_cutoff=WINDOW[1], items=bad)
    assert any("may never be PUBLICLY_VERIFIED" in defect
               for defect in excinfo.value.defects)


def test_unknown_actor_references_are_refused():
    items = [ev.evidence_item(
        claim="c", source="s", date="d", available_before_cutoff=True,
        classification="TEST_ASSUMPTION", who_may_know=["Nobody At All"],
        used_by_compiler=False, entered_context="private:Nobody At All")]
    with pytest.raises(ev.EvidenceError) as excinfo:
        ev.build_manifest(experiment_id="unit", window_start=WINDOW[0],
                          window_cutoff=WINDOW[1], items=items,
                          actor_names=("Someone Else",))
    joined = " ".join(excinfo.value.defects)
    assert "is not a declared actor" in joined
    assert "unknown actor" in joined


def test_bad_shapes_collect_every_defect():
    items = [{"claim": "c"}]
    with pytest.raises(ev.EvidenceError) as excinfo:
        ev.build_manifest(experiment_id="unit", window_start=WINDOW[0],
                          window_cutoff=WINDOW[1], items=items)
    assert "missing fields" in excinfo.value.defects[0]

    items = [ev.evidence_item(
        claim="c", source="s", date="d", available_before_cutoff="yes",
        classification="MADE_UP", who_may_know=[], used_by_compiler=1,
        entered_context="somewhere")]
    with pytest.raises(ev.EvidenceError) as excinfo:
        ev.build_manifest(experiment_id="unit", window_start=WINDOW[0],
                          window_cutoff=WINDOW[1], items=items)
    joined = " ".join(excinfo.value.defects)
    for fragment in ("available_before_cutoff", "classification",
                     "who_may_know", "used_by_compiler",
                     "entered_context"):
        assert fragment in joined


def test_the_rendered_evidence_package_carries_classifications():
    manifest = ev.build_manifest(
        experiment_id="unit", window_start=WINDOW[0],
        window_cutoff=WINDOW[1], items=_items(),
        actor_names=(scenario.DECISION_OWNER_NAME,
                     scenario.RECIPIENT_NAME))
    package = scenario.render_evidence_package(manifest)
    assert "USER_SUPPLIED" in package
    assert "TEST_ASSUMPTION" in package
    for item in manifest["items"]:
        assert (item["claim"] in package) is bool(item["used_by_compiler"])


def test_the_supplied_problem_is_used_verbatim():
    raw = json.loads(scenario.PROBLEM_PATH.read_text(encoding="utf-8"))
    payload = scenario.build_problem_payload(
        start_iso=WINDOW[0], cutoff_iso=WINDOW[1], generated=False)
    assert payload["problem_id"] == raw["problem_id"]
    assert payload["decision_owner"] == raw["decision_owner"]
    assert payload["desired_outcome"] == raw["desired_outcome"]
    assert payload["success_criteria"] == raw["success_criteria"]
    assert payload["constraints"] == raw["constraints"]
    assert payload["relevant_context"] == raw["relevant_context"]
    assert payload["candidate_interventions"] == \
        raw["candidate_interventions"]
    assert len(payload["candidate_interventions"]) == 3
    assert payload["time_horizon"] == {"start": WINDOW[0],
                                       "cutoff": WINDOW[1]}
    assert "_harness_notes" not in payload


def test_the_generated_delta_is_exactly_the_declared_one():
    supplied = scenario.build_problem_payload(
        start_iso=WINDOW[0], cutoff_iso=WINDOW[1], generated=False)
    generated = scenario.build_problem_payload(
        start_iso=WINDOW[0], cutoff_iso=WINDOW[1], generated=True)
    differing = {key for key in supplied
                 if supplied[key] != generated.get(key)}
    assert differing == {"problem_id", "candidate_interventions",
                         "candidate_generation_permission"}
    assert generated["candidate_interventions"] == []
    assert generated["candidate_generation_permission"] is True
    assert generated["problem_id"] == scenario.GENERATED_PROBLEM_ID


def test_the_window_is_exactly_seven_days():
    import datetime
    start = datetime.datetime(2026, 8, 4, 18, 30, 12, 987654,
                              tzinfo=datetime.timezone.utc)
    start_iso, cutoff_iso = scenario.resolve_window(start)
    assert start_iso == "2026-08-04T18:30:12Z"
    assert cutoff_iso == "2026-08-11T18:30:12Z"
    parse = datetime.datetime.fromisoformat
    assert parse(cutoff_iso.replace("Z", "+00:00")) - parse(
        start_iso.replace("Z", "+00:00")) == datetime.timedelta(days=7)
