"""Shared setup for the Phase 11 scale suite (fast tier + verification).

INFRASTRUCTURE TEST ONLY: this suite exercises execution infrastructure
with scripted, deliberately shallow agents -- infrastructure rather than
calibrated societal simulation; no population realism claim.

This conftest must stay importable under the system Python 3.11 product
suite (the fast tier skips at collection time there; the verification
tier is pure stdlib and runs anywhere), so at module level it only
touches ``os.environ`` and ``sys.path``.

Offline contract: dummy LLM credentials are installed via
``os.environ.setdefault`` BEFORE any ``agentsociety2`` import can happen
(``import agentsociety2`` raises at module load when
AGENTSOCIETY_LLM_API_KEY is unset).  No test in this directory performs
network I/O or LLM calls: the only agent class is the scripted
``ScaleUnitAgent`` materialized from ``scale_agent_template.py``.

Worker-side imports: Ray workers only see the PYTHONPATH env var captured
into the job config at the FIRST ``init_dispatchers()`` call, so this
module puts the repository root and THIS directory (``scale_harness``,
whose module-level worker probe function must be importable in workers)
on PYTHONPATH now, before any fixture can initialize Ray.

Ray ownership across suites mirrors the proven
``tests/engine_distributed`` pattern: a session-scoped fixture owns (or
adopts) the runtime, and the directory-scoped ``pytest_runtest_teardown``
hook releases a suite-owned runtime as soon as the run leaves this
directory, so a later Ray suite (``tests/engine_distributed`` in the
nine-suite battery) gets a fresh env snapshot.  The env values match the
sibling Ray suites so all conftests agree on
``Config.LLM_RAY_MAX_WORKERS`` regardless of import order.

Run with the pinned engine environment:

    /home/user/engine-env/bin/python -m pytest tests/engine_scale -q
"""

from __future__ import annotations

import asyncio
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

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Worker-side PYTHONPATH (see module docstring).
_pythonpath = [part for part in
               os.environ.get("PYTHONPATH", "").split(os.pathsep) if part]
for _path in (str(HERE), str(REPO_ROOT)):
    if _path not in _pythonpath:
        _pythonpath.insert(0, _path)
os.environ["PYTHONPATH"] = os.pathsep.join(_pythonpath)


# ---------------------------------------------------------------------------
# Suite-owned Ray lifecycle
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
def scale_engine(tmp_path_factory, request):
    """One local Ray runtime + one scanner workspace for this suite.

    Materializes the scale-unit agent via the harness's own helper (the
    same code path the monitored jobs use), sets WORKSPACE_PATH, points
    the DRIVER registry at it, and runs ``init_dispatchers()`` exactly
    once.  If Ray is already initialized by a foreign suite, adopts its
    captured WORKSPACE_PATH and only materializes the agent there.

    Skips (with the captured error) if Ray cannot start in this sandbox.
    """
    if sys.version_info < (3, 12):  # pragma: no cover - engine env is 3.12
        pytest.skip("scale fast tier requires Python >= 3.12 (engine env)")
    pytest.importorskip("agentsociety2", exc_type=ImportError)
    ray = pytest.importorskip("ray", exc_type=ImportError)

    from scale_harness import materialize_scale_agent

    if ray.is_initialized():
        adopted = os.environ.get("WORKSPACE_PATH", "").strip()
        if not adopted:
            pytest.skip("Ray was initialized externally without "
                        "WORKSPACE_PATH; workers cannot resolve the "
                        "scale agent")
        root = Path(adopted)
        materialize_scale_agent(root)
        yield {"registry_root": root, "num_cpus": None, "owned": False}
        return

    root = tmp_path_factory.mktemp("scale_workspace")
    materialize_scale_agent(root)
    _RAY_STATE["prior_workspace"] = os.environ.get("WORKSPACE_PATH")
    os.environ["WORKSPACE_PATH"] = str(root)

    from agentsociety2.registry import get_registry

    get_registry().set_workspace(root)

    from agentsociety2.config.llm_dispatcher import init_dispatchers

    try:
        asyncio.run(init_dispatchers())
    except Exception as exc:  # noqa: BLE001 - sandbox capability probe
        pytest.skip(f"Ray could not start in this sandbox: {exc!r}")
    if not ray.is_initialized():  # pragma: no cover - defensive
        pytest.skip("Ray reported not initialized after init_dispatchers()")
    _RAY_STATE["owned"] = True
    request.addfinalizer(_shutdown_owned_ray)

    yield {"registry_root": root, "num_cpus": 2, "owned": True}
