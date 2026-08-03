"""Shared setup for the compiler-to-Concordia adapter suite.

This conftest must stay importable under the system Python 3.11 product
suite (every test module in this directory skips at collection time
there), so at module level it only touches ``os.environ`` and
``sys.path``.

- Dummy LLM credentials are installed via ``os.environ.setdefault``
  purely defensively (mirroring tests/engine_baseline/conftest.py): no
  module in this suite performs network I/O, but a transitive import
  must never explode on missing credentials.
- ``tests/engine_contracts`` and ``tests/engine_baseline`` are inserted
  into ``sys.path`` so this suite reuses the SAME ``det.py``
  seeded-determinism harness and the SAME ``baseline_helpers``
  scripted-model toolkit the earlier phases proved (single source of
  truth; no copies to drift).

Run with the pinned engine environment:

    /home/user/engine-env/bin/python -m pytest tests/engine_compilation -q
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
ENGINE_CONTRACTS_DIR = REPO_ROOT / "tests" / "engine_contracts"
ENGINE_BASELINE_DIR = REPO_ROOT / "tests" / "engine_baseline"

for _path in (str(ENGINE_CONTRACTS_DIR), str(ENGINE_BASELINE_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
