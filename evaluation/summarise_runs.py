"""One table of what every finished run actually did.

Terminal, size, cost, how much of it was people rather than furniture,
and whether the mechanical checks hold.  Nothing here decides anything --
it is the number a claim gets checked against.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from interface_mechanics import is_mechanics  # noqa: E402
from verify_run import check  # noqa: E402


def summarise(run_dir: str) -> dict:
    m = json.load(open(os.path.join(run_dir, "runtime_metrics.json")))
    t = json.load(open(os.path.join(run_dir, "terminal_result.json")))
    events = [json.loads(l) for l in
              open(os.path.join(run_dir, "journal.jsonl"), encoding="utf-8")
              if l.strip()]
    wakes = [json.loads(l) for l in
             open(os.path.join(run_dir, "grounded_wakes.jsonl"),
                  encoding="utf-8") if l.strip()]
    replay = json.load(open(os.path.join(run_dir, "replay_verification.json")))
    mech = sum(1 for e in events if is_mechanics(e["description"]))
    span = ((events[-1]["t"][:16], events[0]["t"][:16]) if events
            else ("", ""))
    actors = json.load(open(os.path.join(run_dir, "initial_actor_states.json")))
    woke = {w.get("actor") for w in wakes}
    acted = {r["data"]["actor"] for r in
             (json.loads(l) for l in
              open(os.path.join(run_dir, "ledger.jsonl"), encoding="utf-8")
              if l.strip())
             if r.get("op") == "semantic.actor_call"}
    return {
        "run": os.path.basename(run_dir.rstrip("/")),
        "terminal": (t.get("answer") or {}).get("status"),
        "status": t["trajectory"]["status"],
        "events": len(events),
        "mechanics": mech,
        "steps": m.get("steps"), "calls": m.get("provider_calls"),
        "wall_s": round(m.get("total_wall_s") or 0),
        "actors": len(actors),
        "actors_who_acted": len(acted),
        "actors_ever_woken": len(woke),
        "wakes": len(wakes),
        "first": span[1], "last": span[0],
        "exact": replay.get("exact"),
        "llm_calls_on_replay": replay.get("llm_calls"),
        "failures": check(run_dir)["failures"],
    }


if __name__ == "__main__":
    rows = [summarise(d) for d in sorted(sys.argv[1:])
            if os.path.exists(os.path.join(d, "terminal_result.json"))]
    print(f"{'run':<28} {'terminal':<13} {'ev':>3} {'mech':>4} "
          f"{'act':>4} {'woke':>4} {'wakes':>5} {'calls':>6} {'exact':>6} chk")
    for r in rows:
        print(f"{r['run']:<28} {str(r['terminal']):<13} {r['events']:>3} "
              f"{r['mechanics']:>4} {r['actors_who_acted']}/{r['actors']:<2} "
              f"{r['actors_ever_woken']:>4} {r['wakes']:>5} "
              f"{str(r['calls']):>6} "
              f"{str(r['exact']):>6} "
              f"{'ok' if not r['failures'] else 'FAIL ' + r['failures'][0][:40]}")
    ev = sum(r["events"] for r in rows)
    mech = sum(r["mechanics"] for r in rows)
    yes = sum(1 for r in rows if r["terminal"] == "YES")
    no = sum(1 for r in rows if r["terminal"] == "NO_AT_CUTOFF")
    print(f"\n{len(rows)} runs | {ev} events | machinery {mech}/{ev} "
          f"({mech / ev:.0%})" if ev else "")
    print(f"terminals: {yes} YES, {no} NO_AT_CUTOFF, "
          f"{len(rows) - yes - no} other")
    print(f"replay exact: {sum(1 for r in rows if r['exact'])}/{len(rows)}; "
          f"model calls during replay: "
          f"{sum(r['llm_calls_on_replay'] or 0 for r in rows)}")
