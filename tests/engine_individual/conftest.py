"""Shared setup for the Phase 9 individual-vertical-slice suite.

This conftest must stay importable under the system Python 3.11 product
suite (every test module in this directory skips at collection time
there), so at module level it only touches ``os.environ`` and
``sys.path``.

- Dummy LLM credentials are installed via ``os.environ.setdefault``
  purely defensively (mirroring tests/engine_baseline/conftest.py): the
  scripted and mock legs perform no network I/O, and a transitive import
  must never explode on missing credentials.  The LIVE smoke leg uses
  ``DEEPSEEK_API_KEY`` (a separate variable) and is skipped when it is
  absent.
- ``tests/engine_baseline`` and ``tests/engine_counterfactuals`` are
  inserted into ``sys.path`` so this suite reuses the SAME
  ``baseline_helpers`` scripted-model toolkit and the SAME ``cf_helpers``
  fixture-1 scaffolding (model factory, status rule, freeze-record
  checks) the earlier phases proved (single source of truth; no copies
  to drift).

Run with the pinned engine environment:

    /home/user/engine-env/bin/python -m pytest tests/engine_individual -q
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "dummy")
os.environ.setdefault("AGENTSOCIETY_LLM_API_BASE", "http://localhost:9")
os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
ENGINE_BASELINE_DIR = REPO_ROOT / "tests" / "engine_baseline"
ENGINE_COUNTERFACTUALS_DIR = REPO_ROOT / "tests" / "engine_counterfactuals"

for _path in (str(ENGINE_BASELINE_DIR), str(ENGINE_COUNTERFACTUALS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
