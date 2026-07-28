"""Compile a question with the frozen minimal world compiler and run one
live semantic trajectory on the existing persistent runtime.

Usage:
  python3 run_simulation.py "your question" [--start ISO] [--cutoff ISO]
      [--context "..."] [--out artifacts/simulations/name] [--max-steps N]
      [--scene path/to/final_scene_manifest.json]

The compiler is frozen: this entry point calls the exact production route
(compiler.compile_scene) and consumes its exact four-field manifest.  With
--scene it replays a previously compiled manifest through the same runtime
(still the compiler's own artifact, never a hand-authored world).
"""
import argparse
import datetime as _dt
import json
import os
import re
import sys

from compiler import SceneCaller, compile_scene
from sworldmodel.semantic_runtime import instantiate_scene_manifest
from sworldmodel.semantic_runtime.llm import RuntimeCaller
from sworldmodel.semantic_runtime.replay import replay_trajectory
from sworldmodel.semantic_runtime.trace import (Trace, read_ledger,
                                                write_artifacts,
                                                write_replay_verification)
from sworldmodel.semantic_runtime.trajectory import budget_for, run_trajectory


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("question")
    ap.add_argument("--start", default=None)
    ap.add_argument("--cutoff", default=None)
    ap.add_argument("--context", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-steps", type=int, default=150)
    ap.add_argument("--scene", default=None,
                    help="reuse a compiled final_scene_manifest.json")
    ap.add_argument("--model", default="deepseek-chat")
    args = ap.parse_args()

    start = args.start or _dt.datetime.now(_dt.timezone.utc).replace(
        microsecond=0).isoformat()
    cutoff = args.cutoff or (
        _dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
        + _dt.timedelta(days=14)).isoformat()
    out = args.out or os.path.join(
        "artifacts", "simulations",
        re.sub(r"[^a-z0-9]+", "_", args.question.lower())[:40].strip("_"))
    os.makedirs(out, exist_ok=True)

    if args.scene:
        with open(args.scene) as f:
            scene = json.load(f)
        with open(os.path.join(os.path.dirname(args.scene), "input.json")) as f:
            inp = json.load(f)
        question, start, cutoff = inp["question"], inp["start"], inp["cutoff"]
        print(f"[compile] reusing frozen compiler artifact {args.scene}")
    else:
        question = args.question
        print("[compile] running the frozen minimal world compiler ...")
        result = compile_scene(question, start, cutoff, context=args.context,
                               caller=SceneCaller(args.model),
                               out_dir=os.path.join(out, "compile"))
        print(f"[compile] {result.status} "
              f"({result.metrics.get('semantic_calls')} semantic calls)")
        if result.status not in ("compiled", "corrected"):
            print(f"[compile] {result.reason}")
            return 1
        scene = result.manifest

    world, journal, bindings = instantiate_scene_manifest(
        scene, question, start, cutoff)
    # the backstop is derived from this scene's own shape, so it can only
    # fire on genuine runaway rather than truncating an ordinary run
    ceiling = budget_for(max_steps=args.max_steps, actors=len(world.actors),
                         starting_events=len(scene["starting_events"]))
    caller = RuntimeCaller(args.model, max_calls=ceiling)
    trace = Trace()
    print(f"[run] {len(world.actors)} actors, "
          f"{len(bindings['starting_event_ids'])} starting events, "
          f"cutoff {cutoff}, call ceiling {ceiling}")
    traj = run_trajectory(world, journal, bindings, scene["resolution"],
                          caller, max_steps=args.max_steps, trace=trace)
    # write the ledger first, then replay what was actually PERSISTED:
    # replaying the live world's own in-memory list would only prove the
    # process can talk to itself
    write_artifacts(out, scene=scene, world=world, journal=journal,
                    bindings=bindings, trajectory=traj, caller=caller,
                    trace=trace, replay=None, question=question)
    verification = replay_trajectory(read_ledger(out), live_world=world)
    write_replay_verification(out, verification)
    print(f"[run] {traj.status}: "
          f"{(traj.answer or {}).get('status')} — {traj.reason[:150]}")
    print(f"[run] {traj.steps} steps | {traj.world_calls} world calls | "
          f"{traj.actor_calls} actor calls | {traj.judge_calls} judge calls "
          f"| {len(journal.events())} committed events")
    print(f"[replay] exact={verification.get('exact')} "
          f"llm_calls={verification['llm_calls']} "
          f"integrity={'ok' if not verification['ledger_integrity'] else verification['ledger_integrity'][:2]} "
          f"checked={verification['checked']}")
    print(f"artifacts -> {out}")
    return 0 if traj.status in ("resolved", "cutoff") else 1


if __name__ == "__main__":
    sys.exit(main())
