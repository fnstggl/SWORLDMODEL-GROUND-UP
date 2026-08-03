"""Cold-startup child (matrix row 2): first-run path in a fresh process.

Executed by ``test_cold_startup.py`` as a SUBPROCESS of the pinned
engine interpreter with an EMPTY run root:

  argv: <run_root> <marker>

Asserts, inside the fresh process, that the first-run path needs no
preexisting state of any kind -- no Ray runtime (``ray`` must never even
be imported by the local engine path), no workspaces, no caches -- then
runs ONE complete 1-candidate scripted branch through the public
counterfactual manager and writes a structured report into the run root.
Exit 0 on success; any defect exits nonzero with the error on stderr.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for path in (str(HERE), str(REPO_ROOT / "tests" / "engine_contracts"),
             str(REPO_ROOT / "tests" / "engine_baseline"),
             str(REPO_ROOT / "tests" / "engine_counterfactuals"),
             str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def main() -> int:
    run_root = Path(sys.argv[1]).resolve()
    marker = sys.argv[2]
    started = time.time()

    if not run_root.is_dir() or any(run_root.iterdir()):
        print(f"run root {run_root} is not an empty directory",
              file=sys.stderr)
        return 3

    from cf_helpers import (MAX_STEPS, SEED, branch_signature,
                            fixture_model_factory, fixture_predicates,
                            load_fixture_one)
    from sworldmodel.counterfactuals import run_candidates_detailed
    from sworldmodel.outcomes import evaluate_branches

    if "ray" in sys.modules:
        print("the local first-run path imported ray", file=sys.stderr)
        return 3

    fx = load_fixture_one()
    candidate = fx.candidates[1]
    assert candidate.candidate_id == "concise_relevant", (
        "fixture drifted: expected the middle candidate")

    run = run_candidates_detailed(
        fx.world, [candidate],
        model_factory=fixture_model_factory(fx),
        seed=SEED, max_steps=MAX_STEPS,
        evaluator_spec=fx.evaluator_spec, registry=fx.registry)
    result = run.results[0]
    evaluated = evaluate_branches([result], fixture_predicates())

    if "ray" in sys.modules:
        print("branch execution imported ray on the local path",
              file=sys.stderr)
        return 3

    report = {
        "schema_version": 1,
        "marker": marker,
        "pid": os.getpid(),
        "run_root_was_empty": True,
        "ray_imported": "ray" in sys.modules,
        "candidate_id": result.candidate_id,
        "terminal_status": result.terminal_status,
        "infrastructure_errors": list(result.infrastructure_errors),
        "event_count": len(result.event_trace),
        "branch_signature": branch_signature(result),
        "metric_values": {name: reading.value for name, reading
                          in evaluated[0].outcome_metrics.items()},
        "wall_seconds": round(time.time() - started, 3),
    }
    out_path = run_root / "cold_start_report.json"
    tmp = out_path.with_name(f".{out_path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(report, sort_keys=True, indent=2),
                   encoding="utf-8")
    os.replace(tmp, out_path)
    print("COLD_START_OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
