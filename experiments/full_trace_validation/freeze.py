"""Freeze and hash every input before simulation.

Experiment-only.  A :class:`FreezeManifest` accumulates named sha256
entries, each stamped with the UTC instant it was frozen, and is written
to ``freeze_manifest.json`` before any branch runs.  Anything not present
in the manifest was not an input; anything present cannot be quietly
changed afterwards, because the same hashes are recomputed by the harness
tests and by the audit.

The required entry set per scenario is :data:`REQUIRED_ENTRIES`:

- the ``DecisionProblem`` (contract canonical JSON),
- the evidence manifest,
- the compiler command and configuration,
- the compiler inputs (question / start / cutoff / context / evidence),
- the compiler artifact directory (per file AND an aggregate),
- the ``CompiledDecisionWorld``,
- the ``ConcordiaInitializationPlan`` (the base plan all branches share),
- the evaluator specification,
- the candidate set,
- the model identities and generation parameters,
- the simulation limits, the window, and the per-branch seeds.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FREEZE_VERSION = "freeze_manifest_v1"

REQUIRED_ENTRIES = (
    "decision_problem",
    "evidence_manifest",
    "compiler_command_and_config",
    "compiler_inputs",
    "compiler_artifact_dir_aggregate",
    "compiled_decision_world",
    "concordia_initialization_plan",
    "evaluator_spec",
    "candidate_set",
    "model_identities_and_params",
    "simulation_limits",
    "time_window",
    "branch_seeds",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical(value) -> str:
    """Canonical JSON for hashing: sorted keys, no incidental spacing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def sha256_json(value) -> str:
    return sha256_text(canonical(value))


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def hash_directory(path) -> dict:
    """Per-file sha256 plus one aggregate over the sorted (name, hash)
    pairs -- so a renamed, added, or removed file changes the aggregate.
    """
    base = Path(path)
    per_file = {}
    for item in sorted(base.rglob("*")):
        if item.is_file():
            per_file[str(item.relative_to(base))] = sha256_file(item)
    aggregate = sha256_json(per_file)
    return {"per_file": per_file, "aggregate": aggregate,
            "file_count": len(per_file)}


class FreezeManifest:
    """Accumulate named freeze entries, then write them once."""

    def __init__(self, *, scenario_id: str, note: str = "") -> None:
        self.scenario_id = scenario_id
        self.note = note
        self.entries: dict = {}
        self.order: list = []

    def _stamp(self) -> str:
        import datetime
        return datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def add(self, name: str, *, sha256: str, kind: str, detail=None) -> str:
        if name in self.entries:
            raise AssertionError(
                f"freeze entry {name!r} is already frozen; a second value "
                "would silently replace the first")
        self.entries[name] = {"sha256": sha256, "kind": kind,
                              "frozen_at": self._stamp(),
                              "detail": detail}
        self.order.append(name)
        return sha256

    def add_json(self, name: str, value, *, kind: str = "json",
                 detail=None) -> str:
        return self.add(name, sha256=sha256_json(value), kind=kind,
                        detail=detail)

    def add_text(self, name: str, text: str, *, kind: str = "text",
                 detail=None) -> str:
        return self.add(name, sha256=sha256_text(text), kind=kind,
                        detail=detail)

    def add_directory(self, name: str, path) -> dict:
        record = hash_directory(path)
        self.add(f"{name}_aggregate", sha256=record["aggregate"],
                 kind="directory_aggregate",
                 detail={"path": str(path),
                         "file_count": record["file_count"]})
        self.add(f"{name}_per_file",
                 sha256=sha256_json(record["per_file"]),
                 kind="directory_per_file",
                 detail=record["per_file"])
        return record

    def get(self, name: str) -> str:
        return self.entries[name]["sha256"]

    def missing_required(self) -> list:
        return [name for name in REQUIRED_ENTRIES
                if name not in self.entries]

    def to_dict(self) -> dict:
        return {
            "freeze_version": FREEZE_VERSION,
            "scenario_id": self.scenario_id,
            "note": self.note,
            "required_entries": list(REQUIRED_ENTRIES),
            "missing_required_entries": self.missing_required(),
            "entry_order": list(self.order),
            "entries": {name: dict(self.entries[name])
                        for name in self.order},
        }

    def write(self, path, *, require_complete: bool = True) -> dict:
        missing = self.missing_required()
        if require_complete and missing:
            raise AssertionError(
                "refusing to write an incomplete freeze manifest; missing "
                f"required entries: {missing}")
        payload = self.to_dict()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False)
                          + "\n", encoding="utf-8")
        return payload


def load_manifest(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def entry_sha(manifest: dict, name: str) -> str:
    return manifest["entries"][name]["sha256"]


def assert_entries_equal(left: dict, right: dict, names) -> dict:
    """Prove two freeze manifests agree on the named entries.

    Used to show scenario 2 reused scenario 1's compiled world and base
    plan byte-for-byte instead of recompiling.
    """
    proof = {}
    mismatched = []
    for name in names:
        left_sha = entry_sha(left, name)
        right_sha = entry_sha(right, name)
        proof[name] = {"left": left_sha, "right": right_sha,
                       "equal": left_sha == right_sha}
        if left_sha != right_sha:
            mismatched.append(name)
    if mismatched:
        raise AssertionError(
            "freeze manifests disagree on entries that must be identical: "
            f"{mismatched}; the second scenario did not reuse the first "
            "scenario's frozen inputs")
    return proof
