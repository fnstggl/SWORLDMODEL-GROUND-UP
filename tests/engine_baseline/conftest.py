"""Shared setup for the Phase 4 stock-Concordia baseline suite.

This conftest must stay importable under the system Python 3.11 product
suite (every test module in this directory skips at collection time
there), so at module level it only touches ``os.environ`` and ``sys.path``.

- Dummy LLM credentials are installed via ``os.environ.setdefault`` purely
  defensively (mirroring tests/engine_contracts/conftest.py): no module in
  this suite imports agentsociety2 or performs network I/O, but a
  transitive import must never explode on missing credentials.
- ``tests/engine_contracts`` is inserted into ``sys.path`` so this suite
  reuses the SAME ``det.py`` seeded-determinism harness the Phase 2
  contracts proved (single source of truth; no copy to drift).

Run with the pinned engine environment:

    /home/user/engine-env/bin/python -m pytest tests/engine_baseline -q
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

for _path in (str(ENGINE_CONTRACTS_DIR),):
    if _path not in sys.path:
        sys.path.insert(0, _path)
