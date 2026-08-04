"""Shared setup for the Phase 10 team-vertical-slice suite.

This conftest must stay importable under the system Python 3.11 product
suite (every test module in this directory skips at collection time
there), so at module level it only touches ``os.environ`` and
``sys.path``.

- Dummy LLM credentials are installed via ``os.environ.setdefault``
  purely defensively (mirroring tests/engine_baseline/conftest.py): the
  scripted slice performs no network I/O, and a transitive import must
  never explode on missing credentials.
- ``tests/engine_baseline``, ``tests/engine_counterfactuals``, and
  ``tests/engine_individual`` are inserted into ``sys.path`` so this
  suite reuses the SAME ``baseline_helpers`` scripted-model toolkit, the
  SAME ``cf_helpers`` freeze-record/candidate scaffolding, and the SAME
  ``individual_helpers`` attribution-anchor constant and route-mapping
  helper the earlier phases proved (single source of truth; no copies
  to drift).
- The two session-scoped slice fixtures below run the full scripted
  fixture-2 slice exactly twice for the whole suite; both passes are
  deterministic (proven by the byte-identity tests that consume them),
  so every module reads the same shared outcome objects instead of
  re-running the slowest scenario per module.  The imports inside the
  fixture bodies are deliberately lazy: the fixtures only ever run in
  the pinned engine environment.

Run with the pinned engine environment:

    /home/user/engine-env/bin/python -m pytest tests/engine_team -q
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "dummy")
os.environ.setdefault("AGENTSOCIETY_LLM_API_BASE", "http://localhost:9")
os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
for _path in (
    str(REPO_ROOT / "tests" / "engine_baseline"),
    str(REPO_ROOT / "tests" / "engine_counterfactuals"),
    str(REPO_ROOT / "tests" / "engine_individual"),
):
    if _path not in sys.path:
        sys.path.insert(0, _path)


@pytest.fixture(scope="session")
def team_slice():
    """One shared scripted fixture-2 slice pass; tests treat it as
    read-only."""
    from team_helpers import run_team_slice

    return run_team_slice()


@pytest.fixture(scope="session")
def team_slice_second():
    """A second, independent full pass of the same slice (the
    determinism / repeated-execution counterpart)."""
    from team_helpers import run_team_slice

    return run_team_slice()
