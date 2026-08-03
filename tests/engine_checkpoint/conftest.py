"""Shared setup for the Phase 8 whole-branch checkpoint/resume suite.

This conftest must stay importable under the system Python 3.11 product
suite (every test module in this directory skips at collection time
there), so at module level it only touches ``os.environ`` and
``sys.path``.

Offline contract: dummy LLM credentials are installed via
``os.environ.setdefault`` BEFORE any ``agentsociety2`` import can happen.
No test in this directory performs network I/O or real LLM calls: every
model is a deterministic scripted model, and the distributed leg rebuilds
its models inside Ray workers from a serializable spec
(``checkpoint_model_specs``).

Worker-side imports: Ray workers only see the PYTHONPATH env var captured
into the job config at the FIRST ``init_dispatchers()`` call, so this
module puts the repository root (``sworldmodel``) and THIS directory (the
dotted-name model-spec module ``checkpoint_model_specs``) on PYTHONPATH
now, before any fixture can initialize Ray.  Because pytest imports every
conftest during collection, the sibling Ray suites' directories are on
PYTHONPATH as well before the first init, whichever suite initializes
first.

Ray ownership across suites mirrors the proven
``tests/engine_distributed`` pattern: a session-scoped fixture owns (or
adopts) the runtime, and the directory-scoped ``pytest_runtest_teardown``
hook releases a suite-owned runtime as soon as the run leaves this
directory, so a later Ray suite gets a fresh env snapshot.

Run with the pinned engine environment:

    /home/user/engine-env/bin/python -m pytest tests/engine_checkpoint -q
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Environment: MUST run before any agentsociety2 import anywhere in the
# session.  setdefault only; values match the sibling Ray suites so the
# suites agree on Config.LLM_RAY_MAX_WORKERS regardless of import order.
# ---------------------------------------------------------------------------
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "dummy")
os.environ.setdefault("AGENTSOCIETY_LLM_API_BASE", "http://localhost:9")
os.environ.setdefault("AGENTSOCIETY_LLM_RAY_MAX_WORKERS", "2")
os.environ.setdefault("AGENTSOCIETY_TRACE_WRITER_ASYNC", "0")
os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

# Driver-side sys.path: this directory plus the proven helper toolkits
# reused as single sources of truth (det harness, baseline scripted-model
# toolkit, fixture-1 vocabulary, distributed signature keys).
for _path in (str(HERE),
              str(REPO_ROOT / "tests" / "engine_contracts"),
              str(REPO_ROOT / "tests" / "engine_baseline"),
              str(REPO_ROOT / "tests" / "engine_counterfactuals"),
              str(REPO_ROOT / "tests" / "engine_distributed")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Worker-side PYTHONPATH (see module docstring).
_pythonpath = [part for part in
               os.environ.get("PYTHONPATH", "").split(os.pathsep) if part]
for _path in (str(HERE), str(REPO_ROOT)):
    if _path not in _pythonpath:
        _pythonpath.insert(0, _path)
os.environ["PYTHONPATH"] = os.pathsep.join(_pythonpath)


# ---------------------------------------------------------------------------
# Suite-owned Ray lifecycle (mirrors tests/engine_distributed/conftest.py)
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
def checkpoint_engine(tmp_path_factory, request):
    """One local Ray runtime + one custom-agent workspace for this suite.

    Materializes the branch-agent template via the executor's own public
    helper, sets WORKSPACE_PATH, points the DRIVER registry at it, and
    runs ``init_dispatchers()`` exactly once; adopts a foreign runtime's
    captured WORKSPACE_PATH instead when Ray is already initialized.
    Skips (with the captured error) if Ray cannot start in this sandbox.
    """
    if sys.version_info < (3, 12):  # pragma: no cover - engine env is 3.12
        pytest.skip("checkpoint suite requires Python >= 3.12 (engine env)")
    pytest.importorskip("agentsociety2", exc_type=ImportError)
    ray = pytest.importorskip("ray", exc_type=ImportError)
    pytest.importorskip("concordia.environment.engines.sequential",
                        exc_type=ImportError)

    from sworldmodel.backends.agentsociety import branch_executor

    if ray.is_initialized():
        adopted = os.environ.get("WORKSPACE_PATH", "").strip()
        if not adopted:
            pytest.skip("Ray was initialized externally without "
                        "WORKSPACE_PATH; workers cannot resolve the "
                        "branch agent")
        root = Path(adopted)
        branch_executor.materialize_branch_agent(root)
        yield {"workspace_root": root, "num_cpus": None, "owned": False}
        return

    root = tmp_path_factory.mktemp("checkpoint_workspace")
    branch_executor.materialize_branch_agent(root)
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

    yield {"workspace_root": root, "num_cpus": 2, "owned": True}
