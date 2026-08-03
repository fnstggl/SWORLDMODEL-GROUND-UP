"""Interruption child (matrix rows 4-5): checkpoint, announce, then stall.

Executed by ``test_interruption_resume.py`` as a SUBPROCESS of the
pinned engine interpreter:

  argv: <out_dir> <marker>

Runs fixture-1's ``concise_relevant`` branch to the Stage B end-of-step
boundary (``checkpoint_after=2`` of 4, ``halt_at_checkpoint=True``)
inside the per-branch seeded scope, persists the captured whole-branch
checkpoint ATOMICALLY to ``<out_dir>/checkpoint.json``, appends the
``CHECKPOINT_PERSISTED`` line to ``<out_dir>/progress``, and then blocks
forever -- a mid-run branch process for the parent to SIGTERM/SIGKILL.
The parent then proves the persisted state survived the kill by resuming
it to completion and comparing against an uninterrupted reference.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for path in (str(HERE), str(REPO_ROOT / "tests" / "engine_contracts"),
             str(REPO_ROOT / "tests" / "engine_baseline"),
             str(REPO_ROOT / "tests" / "engine_counterfactuals"),
             str(REPO_ROOT / "tests" / "engine_checkpoint"),
             str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

CANDIDATE_ID = "concise_relevant"


def main() -> int:
    out_dir = Path(sys.argv[1]).resolve()
    marker = sys.argv[2]
    del marker  # identification token for /proc scans; carried in argv

    from checkpoint_helpers import (CHECKPOINT_AFTER, SEED, branch_setup,
                                    checkpoint_identity, load_fixture_one,
                                    make_models, prompt_pure_params)
    from sworldmodel.backends.concordia_local import runner as runner_module
    from sworldmodel.counterfactuals.manager import _seeded_branch_scope

    fx = load_fixture_one()
    candidate, plan, branch_id, branch_seed = branch_setup(fx, CANDIDATE_ID)
    params = prompt_pure_params(fx)
    actor_models, gm_model = make_models(params, candidate, branch_seed)

    with _seeded_branch_scope(branch_seed):
        raw = runner_module.run_branch(
            plan, actor_models=actor_models, gm_model=gm_model,
            checkpoint_after=CHECKPOINT_AFTER, halt_at_checkpoint=True,
            checkpoint_identity=checkpoint_identity(candidate, branch_id,
                                                    branch_seed))
    if raw.get("checkpoint") is None or not raw.get("halted_at_checkpoint"):
        print("no checkpoint was captured at the boundary", file=sys.stderr)
        return 3

    blob_path = out_dir / "checkpoint.json"
    tmp = blob_path.with_name(f".{blob_path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(raw["checkpoint"], sort_keys=True),
                   encoding="utf-8")
    os.replace(tmp, blob_path)

    with open(out_dir / "progress", "a", encoding="utf-8") as handle:
        handle.write("CHECKPOINT_PERSISTED\n")
        handle.flush()
        os.fsync(handle.fileno())

    # Mid-run stall: the branch process is now hanging with its
    # checkpoint safely on disk; the parent kills this process.
    threading.Event().wait()
    return 0  # pragma: no cover - unreachable


if __name__ == "__main__":
    sys.exit(main())
