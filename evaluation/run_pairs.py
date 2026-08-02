"""Matched-pair evidence sensitivity, over replicates, on the current runtime.

The question this answers is not "does a scene work" but "does the answer
follow the evidence".  It is the only measurement that distinguishes a
forecaster from a machine that says YES whenever it manages to simulate
something: 16 of 22 acceptance runs answered YES and exactly one answered
NO, which is a distribution a coin could produce and a useful system could
not.

Three comparisons, each varying one thing:

  A  same people, opposite evidence   -- the answer must follow the evidence
  B  same evidence, different names   -- the answer must NOT follow the names
  C  evidence against the stereotype  -- the answer must follow the evidence

The scenes come from the frozen compiler's own artifacts, so the compiler
is not re-run: every difference between arms is the runtime's, and every
difference between replicates of ONE arm is the variance the question has
on its own.  A single run per arm cannot tell those apart, which is why
this takes replicates and reports rates.

Usage:
  python3 evaluation/run_pairs.py OUT_DIR [--replicates 5] [--max-steps 250]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

from sworldmodel.semantic_runtime import instantiate_scene_manifest
from sworldmodel.semantic_runtime.llm import RuntimeCaller
from sworldmodel.semantic_runtime.replay import replay_trajectory
from sworldmodel.semantic_runtime.trace import (Trace, read_ledger,
                                                write_artifacts,
                                                write_replay_verification)
from sworldmodel.semantic_runtime.trajectory import budget_for, run_trajectory

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matched_pairs import PAIRS  # noqa: E402

SRC = "artifacts/matched_pairs"


def compiled(stem: str):
    """The frozen compiler's own artifact for this arm, if it has one."""
    for d in (os.path.join(SRC, stem),
              os.path.join(SRC, stem + "__r2")):
        p = os.path.join(d, "compiled_scene.json")
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    return None


def one(stem: str, scene, out_dir: str, max_steps: int) -> dict:
    spec = PAIRS[stem]
    world, journal, bindings = instantiate_scene_manifest(
        scene, spec["question"], spec["start"], spec["cutoff"])
    caller = RuntimeCaller(
        max_calls=budget_for(max_steps=max_steps, actors=len(world.actors),
                             starting_events=len(scene["starting_events"])))
    trace = Trace()
    traj = run_trajectory(world, journal, bindings, scene["resolution"],
                          caller, max_steps=max_steps, trace=trace)
    os.makedirs(out_dir, exist_ok=True)
    write_artifacts(out_dir, scene=scene, world=world, journal=journal,
                    bindings=bindings, trajectory=traj, caller=caller,
                    trace=trace, replay=None, question=spec["question"])
    write_replay_verification(out_dir, replay_trajectory(read_ledger(out_dir)))
    return {"arm": stem, "status": traj.status,
            "terminal": (traj.answer or {}).get("status"),
            "events": len(journal.events()), "steps": traj.steps}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out")
    ap.add_argument("--replicates", type=int, default=5)
    ap.add_argument("--max-steps", type=int, default=250)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rows = []
    for stem in PAIRS:
        scene = compiled(stem)
        if scene is None:
            print(f"[skip] {stem}: no frozen compiler artifact", flush=True)
            continue
        for i in range(1, args.replicates + 1):
            print(f"[run] {stem} r{i}", flush=True)
            try:
                rows.append(one(stem, scene,
                                os.path.join(args.out, f"{stem}__r{i}"),
                                args.max_steps))
            except Exception as e:                   # one replicate, not all
                rows.append({"arm": stem, "status": "CRASHED",
                             "error": repr(e),
                             "traceback": traceback.format_exc()})
            print(f"  -> {rows[-1].get('status')} / "
                  f"{rows[-1].get('terminal')}", flush=True)
            with open(os.path.join(args.out, "pairs.json"), "w") as f:
                json.dump(rows, f, indent=1)
    # ... and, once every arm has all its replicates, a copy where the
    # report cites it from.  A run directory is regenerable evidence and is
    # not tracked; a half-finished set of replicates is worse than no
    # measurement, because a rate over three of five runs reads like a rate.
    if len(rows) == len(PAIRS) * args.replicates:
        keep = os.path.join("artifacts", "semantic_runtime", "mvp",
                            "pairs_summary.json")
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        with open(keep, "w") as f:
            json.dump({"frozen_runtime": open(
                "artifacts/semantic_runtime/RUNTIME_FREEZE.txt").read().split(),
                "replicates": args.replicates, "runs": rows}, f, indent=1)
        print(f"[summary] {keep}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
