"""Re-run the acceptance corpus through the current runtime.

The scenes come from the frozen compiler's own artifacts, so the compiler
is not re-run and every difference between two corpora is the runtime's.
Each run is independent: one failing does not stop the rest.

Usage:
  python3 evaluation/run_corpus.py OUT_DIR [--from artifacts/final_v6]
                                   [--only name,name] [--max-steps N]
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


def cases(src: str) -> list:
    out = []
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        scene_p = os.path.join(d, "compiled_scene.json")
        bind_p = os.path.join(d, "compile_runtime_bindings.json")
        if not (os.path.exists(scene_p) and os.path.exists(bind_p)):
            continue
        with open(scene_p) as f:
            scene = json.load(f)
        with open(bind_p) as f:
            b = json.load(f)
        out.append((name, scene, b["question"], b["start"], b["cutoff"]))
    return out


def run_one(name, scene, question, start, cutoff, out_dir, max_steps):
    world, journal, bindings = instantiate_scene_manifest(
        scene, question, start, cutoff)
    caller = RuntimeCaller(
        max_calls=budget_for(max_steps=max_steps, actors=len(world.actors),
                             starting_events=len(scene["starting_events"])))
    trace = Trace()
    traj = run_trajectory(world, journal, bindings, scene["resolution"],
                          caller, max_steps=max_steps, trace=trace)
    os.makedirs(out_dir, exist_ok=True)
    write_artifacts(out_dir, scene=scene, world=world, journal=journal,
                    bindings=bindings, trajectory=traj, caller=caller,
                    trace=trace, replay=None, question=question)
    ver = replay_trajectory(read_ledger(out_dir))
    write_replay_verification(out_dir, ver)
    return traj, journal, ver


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out")
    ap.add_argument("--from", dest="src", default="artifacts/final_v6")
    ap.add_argument("--only", default="")
    ap.add_argument("--max-steps", type=int, default=250)
    args = ap.parse_args()

    only = {s for s in args.only.split(",") if s}
    os.makedirs(args.out, exist_ok=True)
    rows = []
    for name, scene, question, start, cutoff in cases(args.src):
        if only and name not in only:
            continue
        print(f"[run] {name}", flush=True)
        try:
            traj, journal, ver = run_one(
                name, scene, question, start, cutoff,
                os.path.join(args.out, name), args.max_steps)
            rows.append({"run": name, "status": traj.status,
                         "terminal": (traj.answer or {}).get("status"),
                         "events": len(journal.events()),
                         "steps": traj.steps,
                         "calls": (traj.world_calls + traj.actor_calls
                                   + traj.judge_calls + traj.review_calls),
                         "replay_records": ver["records_replayed"],
                         "ledger_problems": ver["ledger_integrity"],
                         "reason": traj.reason})
            print(f"  -> {traj.status} / {(traj.answer or {}).get('status')} "
                  f"({len(journal.events())} events)", flush=True)
        except Exception as e:                       # one run, not the set
            rows.append({"run": name, "status": "CRASHED", "error": repr(e),
                         "traceback": traceback.format_exc()})
            print(f"  -> CRASHED {e!r}", flush=True)
        with open(os.path.join(args.out, "corpus.json"), "w") as f:
            json.dump(rows, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
