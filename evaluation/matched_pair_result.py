"""What the matched pairs actually showed, counted over replicates.

A single run per arm cannot tell a real difference from an ordinary one.
The first pass had one YES and one NO across pair B and it looked like the
names had done it; four runs of each arm showed the two arms answering at
exactly the same rate, and the split was the variance the question has on
its own.
"""
from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from interface_mechanics import is_mechanics  # noqa: E402

ARMS = {
    "A same names, RESPONSIVE evidence": "a1_responsive",
    "A same names, AVOIDING evidence": "a2_unresponsive",
    "B Okafor / Herrera": "b1_okafor_herrera",
    "B Thornbury / Lim": "b2_thornbury_lim",
    "C evidence against the stereotype": "c1_against_stereotype",
}


def runs_for(stem: str) -> list:
    base = "artifacts/matched_pairs"
    return sorted(d for d in
                  [os.path.join(base, stem)] + glob.glob(
                      os.path.join(base, stem + "__r*"))
                  if os.path.exists(os.path.join(d, "terminal_result.json")))


def arm(stem: str) -> dict:
    out = []
    for d in runs_for(stem):
        t = json.load(open(os.path.join(d, "terminal_result.json")))
        events = [json.loads(l) for l in
                  open(os.path.join(d, "journal.jsonl"), encoding="utf-8")
                  if l.strip()]
        out.append({"terminal": (t.get("answer") or {}).get("status"),
                    "events": len(events),
                    "mechanics": sum(1 for e in events
                                     if is_mechanics(e["description"]))})
    yes = sum(1 for r in out if r["terminal"] == "YES")
    return {"runs": len(out), "yes": yes,
            "events": [r["events"] for r in out],
            "terminals": [r["terminal"] for r in out]}


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    res = {}
    for label, stem in ARMS.items():
        a = arm(stem)
        res[stem] = a
        print(f"{label:<38} {a['yes']}/{a['runs']} YES   events "
              f"{a['events']}")
    print()
    a1, a2 = res["a1_responsive"], res["a2_unresponsive"]
    b1, b2 = res["b1_okafor_herrera"], res["b2_thornbury_lim"]
    print("PAIR A -- same two names, opposite evidence.  Behaviour must "
          "follow the evidence:")
    print(f"  responsive {a1['yes']}/{a1['runs']} YES vs avoiding "
          f"{a2['yes']}/{a2['runs']} YES  -> "
          f"{'SEPARATES' if a1['yes'] > a2['yes'] else 'DOES NOT SEPARATE'}")
    print("PAIR B -- different names, same evidence.  Behaviour must NOT "
          "follow the names:")
    print(f"  {b1['yes']}/{b1['runs']} YES vs {b2['yes']}/{b2['runs']} YES  -> "
          f"{'SAME RATE' if b1['yes'] == b2['yes'] else 'DIFFERENT RATE'}")
