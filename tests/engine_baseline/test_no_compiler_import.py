"""Import-graph proof: the baseline execution path imports NO compiler
package and NO forbidden legacy-runtime module.

The check runs in a SUBPROCESS (same interpreter), because this test
session itself may legitimately import other packages for other tests --
only a fresh interpreter gives a truthful sys.modules claim.

Boundary fact (documented, verified below): ``sworldmodel/__init__.py``
(a Phase 3-era file outside Phase 4 ownership) eagerly imports the legacy
kernel modules -- including ``sworldmodel.engine`` -- for ANY
``import sworldmodel``, before this backend even exists on the import
path.  The truthful assertions are therefore:

  1. after importing the full baseline path (planner, builder, runner,
     and BOTH hard-gate scenario test modules), ``sys.modules`` contains
     no module named ``compiler`` or ``compiler.*`` -- at all;
  2. no ``sworldmodel.semantic_runtime`` module (including
     ``.trajectory``) was imported -- at all (the package __init__ does
     NOT pull these in, so absence is meaningful without a delta);
  3. delta discipline for the legacy kernel: the baseline path adds ZERO
     forbidden modules beyond what the bare ``import sworldmodel``
     package __init__ already brings in for every consumer;
  4. statically, none of the five baseline-path files contains an import
     statement referencing ``compiler``, ``sworldmodel.engine``, or
     ``sworldmodel.semantic_runtime`` (AST walk, not grep).
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine baseline requires Python >= 3.12 (Concordia floor); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASELINE_DIR = REPO_ROOT / "tests" / "engine_baseline"
CONTRACTS_DIR = REPO_ROOT / "tests" / "engine_contracts"

BASELINE_PATH_FILES = (
    REPO_ROOT / "sworldmodel" / "backends" / "concordia_local" / "planner.py",
    REPO_ROOT / "sworldmodel" / "backends" / "concordia_local" / "builder.py",
    REPO_ROOT / "sworldmodel" / "backends" / "concordia_local" / "runner.py",
    BASELINE_DIR / "test_hard_gate_scenario_one.py",
    BASELINE_DIR / "test_hard_gate_scenario_two.py",
)

_SUBPROCESS_SCRIPT = r"""
import json
import sys

import sworldmodel  # package __init__ (legacy kernel eager imports happen HERE)
after_package_init = set(sys.modules)

import sworldmodel.backends.concordia_local.planner
import sworldmodel.backends.concordia_local.builder
import sworldmodel.backends.concordia_local.runner
import test_hard_gate_scenario_one
import test_hard_gate_scenario_two
after_baseline_path = set(sys.modules)


def _forbidden(name):
    return (
        name == "compiler"
        or name.startswith("compiler.")
        or name == "sworldmodel.engine"
        or name == "sworldmodel.semantic_runtime"
        or name.startswith("sworldmodel.semantic_runtime.")
    )


print(json.dumps({
    "compiler_modules": sorted(
        m for m in after_baseline_path
        if m == "compiler" or m.startswith("compiler.")),
    "semantic_runtime_modules": sorted(
        m for m in after_baseline_path
        if m == "sworldmodel.semantic_runtime"
        or m.startswith("sworldmodel.semantic_runtime.")),
    "forbidden_added_by_baseline_path": sorted(
        m for m in (after_baseline_path - after_package_init)
        if _forbidden(m)),
    "package_init_alone_imports_engine": (
        "sworldmodel.engine" in after_package_init),
    "scenario_modules_loaded": (
        "test_hard_gate_scenario_one" in after_baseline_path
        and "test_hard_gate_scenario_two" in after_baseline_path),
}))
"""


def test_subprocess_import_graph_has_no_compiler_and_no_forbidden_modules():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        (str(REPO_ROOT), str(BASELINE_DIR), str(CONTRACTS_DIR)))
    completed = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SCRIPT],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=env,
        timeout=180, check=False)
    assert completed.returncode == 0, (
        f"subprocess failed\nstdout: {completed.stdout}\n"
        f"stderr: {completed.stderr}")
    report = json.loads(completed.stdout.strip().splitlines()[-1])

    # (1) No compiler package anywhere in the interpreter, full stop.
    assert report["compiler_modules"] == []
    # (2) No semantic-runtime module anywhere in the interpreter.
    assert report["semantic_runtime_modules"] == []
    # (3) The baseline path added zero forbidden modules beyond the bare
    # package __init__ (which demonstrably imports the legacy kernel for
    # every consumer -- that pre-existing fact is recorded, not hidden).
    assert report["forbidden_added_by_baseline_path"] == []
    assert report["package_init_alone_imports_engine"] is True
    # Sanity: the scenario modules really were imported in the subprocess.
    assert report["scenario_modules_loaded"] is True


def _imported_module_names(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module:
                # relative import inside the backend package
                names.append(f"<relative>.{node.module}")
            elif node.module:
                names.append(node.module)
    return names


def test_static_import_statements_reference_no_forbidden_module():
    forbidden_prefixes = ("compiler", "sworldmodel.engine",
                          "sworldmodel.semantic_runtime")
    offenders = []
    for path in BASELINE_PATH_FILES:
        for name in _imported_module_names(path):
            if any(name == prefix or name.startswith(prefix + ".")
                   for prefix in forbidden_prefixes):
                offenders.append(f"{path.name}: {name}")
    assert offenders == [], offenders
