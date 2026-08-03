"""Clean installation (OPERATIONAL_ROBUSTNESS_MATRIX row 1; gate A
"reproducible from a clean environment").

Committed-evidence tier (the Phase 11 scale-suite design): the heavy leg
-- rebuilding the whole engine environment from an empty venv per
``third_party/INTEGRATION_METHOD.md`` and running the coexistence check
plus one fast engine smoke suite inside it -- runs as a MONITORED JOB
executing ``clean_install_probe.py``; this module validates the
committed structured evidence strictly against the lock and the
documented procedure.  Pure stdlib, runs under both interpreters.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
EVIDENCE = HERE / "evidence" / "clean_install.json"
LOCK = REPO_ROOT / "third_party" / "UPSTREAM_LOCK.json"

#: the documented install sequence, in order (drift here means the probe
#: and INTEGRATION_METHOD.md no longer agree)
EXPECTED_PHASES = (
    "verify_pinned_checkouts",
    "create_venv",
    "install_concordia_editable",
    "install_agentsociety2_editable",
    "install_mcp_environment_pin",
    "install_test_plugins",
    "coexistence_check",
    "package_inventory",
    "engine_smoke_suite",
)


def _evidence() -> dict:
    assert EVIDENCE.exists(), (
        f"clean-install evidence missing at {EVIDENCE}; run "
        "clean_install_probe.py through the monitored runner "
        "(see the probe's module docstring)")
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_clean_install_evidence_is_green_bounded_and_complete():
    """Row 1: the recorded rebuild succeeded end to end -- every
    documented phase ok, total wall time within the recorded budget,
    run under a named monitored job."""
    evidence = _evidence()
    assert evidence["schema_version"] == 1
    assert evidence["ok"] is True
    assert evidence["failures"] == []
    assert evidence["within_budget"] is True
    assert 0 < evidence["total_seconds"] <= evidence["budget_total_s"]
    assert evidence["monitored_job_id"].startswith(
        "robustness-clean-install")
    assert evidence["integration_method_doc"] \
        == "third_party/INTEGRATION_METHOD.md"
    assert (REPO_ROOT / evidence["integration_method_doc"]).exists()

    names = [phase["name"] for phase in evidence["phases"]]
    assert names == list(EXPECTED_PHASES)
    for phase in evidence["phases"]:
        assert phase["ok"] is True, f"phase {phase['name']} not ok"
        assert phase["seconds"] >= 0


def test_clean_install_used_the_locked_upstreams():
    """Row 1: the environment was built from checkouts sitting EXACTLY
    at the pinned SHAs of third_party/UPSTREAM_LOCK.json, clean."""
    evidence = _evidence()
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    locked = {upstream["name"]: upstream["pinned_commit_sha"]
              for upstream in lock["upstreams"]}
    assert set(evidence["pins"]) == set(locked)
    for name, pin in evidence["pins"].items():
        assert pin["ok"] is True
        assert pin["clean"] is True
        assert pin["head"] == locked[name] == pin["pinned_commit_sha"]


def test_clean_install_proved_the_environment_works():
    """Row 1: the fresh environment passed the coexistence check and the
    named engine smoke suite (2 tests), with a real dependency set."""
    evidence = _evidence()
    inventory = evidence["package_inventory"]
    assert inventory["count"] >= 50
    key = inventory["key_versions"]
    for package in ("gdm-concordia", "agentsociety2", "ray", "litellm",
                    "mcp", "pytest"):
        assert key.get(package), f"{package} missing from the fresh env"
    assert key["mcp"].split(".")[0] == "1"  # the documented <2 pin held

    smoke = evidence["smoke"]
    assert smoke["test_path"] \
        == "tests/engine_counterfactuals/test_failure_isolation.py"
    assert (REPO_ROOT / smoke["test_path"]).exists()
    assert smoke["returncode"] == 0
    assert smoke["passed_2"] is True
    assert evidence["venv_removed_after_run"] is True
