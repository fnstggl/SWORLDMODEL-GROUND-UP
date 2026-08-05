"""Shared setup for the full-trace-validation harness suite.

Importable under the system Python 3.11 product suite: every module in
this directory skips at collection time there, so this file only touches
``os.environ`` and ``sys.path`` at import.

Run with the pinned engine environment::

    /home/user/engine-env/bin/python -m pytest tests/experiment_harness -q
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

for _path in (str(REPO_ROOT),
              str(REPO_ROOT / "tests" / "engine_baseline"),
              str(REPO_ROOT / "tests" / "engine_counterfactuals"),
              str(REPO_ROOT / "tests" / "engine_individual"),
              str(REPO_ROOT / "tests" / "engine_compilation")):
    if _path not in sys.path:
        sys.path.insert(0, _path)
