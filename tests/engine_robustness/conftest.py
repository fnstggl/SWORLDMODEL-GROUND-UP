"""Shared setup for the gate-I operational-robustness suite.

Matrix: every test module in this directory cites its row(s) of
``docs/engine_migration/OPERATIONAL_ROBUSTNESS_MATRIX.md`` in its module
docstring; the matrix maps all fourteen directive scenarios to evidence.

This conftest must stay importable under the system Python 3.11 product
suite (every engine-gated test module in this directory skips at
collection time there), so at module level it only touches
``os.environ`` and ``sys.path``.

Offline contract: dummy LLM credentials are installed via
``os.environ.setdefault`` BEFORE any ``agentsociety2`` import can happen
(``import agentsociety2`` raises at module load when
AGENTSOCIETY_LLM_API_KEY is unset).  No test in this directory performs
network I/O or real LLM calls; the missing-credentials tests probe the
documented refusals in SUBPROCESSES with the variables explicitly
removed from the child environment, never from this process.

Path reuse (single sources of truth, the proven cross-suite pattern):
``baseline_helpers`` / ``cf_helpers`` / ``checkpoint_helpers`` /
``checkpoint_model_specs`` / ``scale_harness`` are imported from their
owning suites; nothing is copied.  Worker-side PYTHONPATH additionally
carries the repository root and ``tests/engine_scale`` (Ray pickles the
harness's module-level worker-probe function by reference, so workers
must be able to import ``scale_harness``) plus this directory, captured
into the Ray job config at the FIRST ``init_dispatchers()`` call.

Ray ownership across suites mirrors the proven
``tests/engine_distributed`` / ``tests/engine_scale`` pattern: the
session-scoped ``robustness_engine`` fixture owns (or adopts) the
runtime, and the directory-scoped ``pytest_runtest_teardown`` hook
releases a suite-owned runtime as soon as the run leaves this directory,
so a later Ray suite gets a fresh env snapshot.  Env values match the
sibling Ray suites so all conftests agree on
``Config.LLM_RAY_MAX_WORKERS`` regardless of import order.

Run with the pinned engine environment:

    /home/user/engine-env/bin/python -m pytest tests/engine_robustness -q
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Environment: MUST run before any agentsociety2 import anywhere in the
# session.  setdefault only; values match the sibling Ray suites.
# ---------------------------------------------------------------------------
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "dummy")
os.environ.setdefault("AGENTSOCIETY_LLM_API_BASE", "http://localhost:9")
os.environ.setdefault("AGENTSOCIETY_LLM_RAY_MAX_WORKERS", "2")
os.environ.setdefault("AGENTSOCIETY_TRACE_WRITER_ASYNC", "0")
os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

# Driver-side sys.path: this directory plus the owning suites of the
# reused toolkits (contracts det harness, baseline scripted models,
# fixture-1 counterfactual vocabulary, checkpoint helpers + model specs,
# scale harness).
for _path in (str(HERE),
              str(REPO_ROOT / "tests" / "engine_contracts"),
              str(REPO_ROOT / "tests" / "engine_baseline"),
              str(REPO_ROOT / "tests" / "engine_counterfactuals"),
              str(REPO_ROOT / "tests" / "engine_checkpoint"),
              str(REPO_ROOT / "tests" / "engine_scale")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Worker-side PYTHONPATH (frozen into the Ray job config at first init).
_pythonpath = [part for part in
               os.environ.get("PYTHONPATH", "").split(os.pathsep) if part]
for _path in (str(HERE), str(REPO_ROOT / "tests" / "engine_scale"),
              str(REPO_ROOT)):
    if _path not in _pythonpath:
        _pythonpath.insert(0, _path)
os.environ["PYTHONPATH"] = os.pathsep.join(_pythonpath)


# ---------------------------------------------------------------------------
# Suite-owned Ray lifecycle (same shape as tests/engine_distributed)
# ---------------------------------------------------------------------------

_RAY_STATE = {"owned": False, "released": False, "prior_workspace": None}


def _shutdown_owned_ray() -> None:
    """Release the suite-owned Ray runtime exactly once and restore the
    prior WORKSPACE_PATH.  No-op when Ray belongs to another suite."""
    if not _RAY_STATE["owned"] or _RAY_STATE["released"]:
        return
    _RAY_STATE["released"] = True
    try:
        import ray

        ray.shutdown()
    finally:
        prior = _RAY_STATE["prior_workspace"]
        if prior is None:
            os.environ.pop("WORKSPACE_PATH", None)
        else:
            os.environ["WORKSPACE_PATH"] = prior


def pytest_runtest_teardown(item, nextitem):
    """Directory-scoped hook: when the NEXT item lives outside this
    directory -- or there is none -- release the suite-owned Ray runtime
    so a later Ray suite gets a fresh env snapshot."""
    del item
    if nextitem is not None:
        next_path = str(getattr(nextitem, "path", None) or nextitem.fspath)
        if next_path.startswith(str(HERE) + os.sep):
            return
    _shutdown_owned_ray()


@pytest.fixture(scope="session")
def robustness_engine(tmp_path_factory, request):
    """One local Ray runtime + one registry workspace for this suite's
    worker-failure tests, brought up through the scale harness's own
    ``ensure_engine`` (the same code path the Phase 11 monitored jobs
    used).  Adopts a foreign runtime when one is already initialized.

    Skips (with the captured error) if Ray cannot start in this sandbox.
    """
    if sys.version_info < (3, 12):  # pragma: no cover - engine env is 3.12
        pytest.skip("robustness Ray tests require Python >= 3.12 "
                    "(engine env)")
    pytest.importorskip("agentsociety2", exc_type=ImportError)
    ray = pytest.importorskip("ray", exc_type=ImportError)
    pytest.importorskip("concordia.environment.engines.sequential",
                        exc_type=ImportError)

    import scale_harness

    owned = not ray.is_initialized()
    if owned:
        _RAY_STATE["prior_workspace"] = os.environ.get("WORKSPACE_PATH")
        root = tmp_path_factory.mktemp("robustness_registry")
    else:
        adopted = os.environ.get("WORKSPACE_PATH", "").strip()
        if not adopted:
            pytest.skip("Ray was initialized externally without "
                        "WORKSPACE_PATH; workers cannot resolve the "
                        "scale agent")
        root = Path(adopted)

    try:
        engine = scale_harness.ensure_engine(root)
    except Exception as exc:  # noqa: BLE001 - sandbox capability probe
        pytest.skip(f"Ray could not start in this sandbox: {exc!r}")
    ray_mod, as2_runner, build_service_proxy, effective, probe = engine
    if owned:
        _RAY_STATE["owned"] = True
        request.addfinalizer(_shutdown_owned_ray)

    yield {
        "ray": ray_mod,
        "as2_runner": as2_runner,
        "build_service_proxy": build_service_proxy,
        "registry_root": effective,
        "worker_probe": probe,
        "owned": owned,
    }
