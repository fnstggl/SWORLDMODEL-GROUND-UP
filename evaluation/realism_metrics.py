"""Whether a corpus looks like a world, measured rather than asserted.

Six properties, each one the counterpart of a defect that was found by
reading trajectories by hand:

**overlaps** -- one person doing two things at once.  Read off the record
now that events carry ``by`` and ``lasts``: for each actor, any pair whose
occupancies intersect.  This is exact, not a heuristic, and it is the
property the occupancy model exists to make impossible.

**zero_gaps** -- consecutive events separated by no simulated time at all.
A world in which nothing costs anything.

**window_lived** -- how much of the question's own window the trajectory
actually spent.  A NO over a window nobody lived is a fact about the
scheduler.

**exogenous** -- events nobody in the cast brought about.  A world where
this is zero is a world in which nothing can happen that the question did
not already contain.

**repeats** -- pairs the duplicate rule would now call one act.  Any left
in a finished corpus are ones it did not catch.

**quiet_turns** -- consultations that produced no intention.  Not a defect
in itself; people do nothing all the time.  A defect when it is most of
them.

Nothing here is read by the runtime.  It is evidence.
"""
from __future__ import annotations

import itertools
import json
import os

from sworldmodel.semantic_runtime.envelope import parse_duration
from sworldmodel.semantic_runtime.world_mind import says_the_same_thing
from sworldmodel.simclock import parse_iso


def _jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _span(e):
    t = parse_iso(e["t"])
    try:
        return t, t + parse_duration(e.get("lasts") or "0 seconds")
    except Exception:
        return t, t


def measure(run_dir: str) -> dict:
    events = _jsonl(os.path.join(run_dir, "journal.jsonl"))
    wakes = _jsonl(os.path.join(run_dir, "grounded_wakes.jsonl"))
    decisions = _jsonl(os.path.join(run_dir, "actor_views.jsonl"))
    exchanges = _jsonl(os.path.join(run_dir, "actor_exchanges.jsonl"))
    judgments = _jsonl(os.path.join(run_dir, "world_judgments.jsonl"))
    bind_p = os.path.join(run_dir, "compile_runtime_bindings.json")
    out = {"run": os.path.basename(run_dir.rstrip("/")),
           "events": len(events)}
    if not events:
        return out

    # Runs made before events carried who did them cannot be measured for
    # occupancy at all -- and must not be reported as if they could.  An
    # earlier version of this script read a missing `by` as "nobody did
    # it" and reported the old corpus as 93% exogenous, which is the
    # opposite of its actual defect.
    knows_by = all("by" in e for e in events)
    out["knows_by"] = knows_by

    # one person, two things at once -- exact, off `by` and `lasts`
    overlaps = []
    by_actor: dict = {}
    for e in events:
        if e.get("by"):
            by_actor.setdefault(e["by"], []).append(e)
    for actor, mine in by_actor.items():
        for a, b in itertools.combinations(mine, 2):
            (sa, ea), (sb, eb) = _span(a), _span(b)
            if sa < eb and sb < ea:            # genuinely intersecting
                overlaps.append({"actor": actor, "a": a["event_id"],
                                 "b": b["event_id"],
                                 "a_text": a["description"][:70],
                                 "b_text": b["description"][:70]})
    out["overlaps"] = len(overlaps) if knows_by else None
    out["overlap_examples"] = overlaps[:3]

    # time that costs nothing
    ts = [parse_iso(e["t"]) for e in events]
    gaps = [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    out["zero_gaps"] = sum(1 for g in gaps if g == 0)
    out["zero_gap_share"] = round(out["zero_gaps"] / len(gaps), 3) if gaps else 0

    # how much of the window was lived
    if os.path.exists(bind_p):
        with open(bind_p) as f:
            b = json.load(f)
        start, cut = parse_iso(b["start"]), parse_iso(b["cutoff"])
        window = (cut - start).total_seconds()
        lived = (max(ts) - start).total_seconds()
        out["window_lived"] = round(lived / window, 3) if window else None

    # anything that happened which nobody here chose
    out["exogenous"] = (
        sum(1 for e in events if not e.get("by")
            and str(e.get("source", "")).startswith("world_call"))
        if knows_by else None)
    out["world_own_turns"] = sum(1 for j in judgments
                                 if j.get("trigger") == "elapsed_world")

    # repeats the rule did not catch
    repeats = [{"a": a["event_id"], "b": b["event_id"],
                "text": a["description"][:70]}
               for a, b in itertools.combinations(events, 2)
               if a.get("by") == b.get("by")
               and tuple(a["for"]) == tuple(b["for"])
               and says_the_same_thing(a["description"], b["description"])]
    out["repeats_left"] = len(repeats)
    out["repeat_examples"] = repeats[:3]

    # consultations that produced nothing
    quiet = sum(1 for c in exchanges
                if not (c.get("parsed") or {}).get("intentions"))
    out["turns"] = len(exchanges)
    out["quiet_turns"] = quiet
    out["quiet_share"] = round(quiet / len(exchanges), 3) if exchanges else None
    out["wakes"] = len(wakes)
    out["views"] = len(decisions)
    return out


def _pct(x):
    return "-" if x is None else f"{x:.0%}"


if __name__ == "__main__":
    import sys
    dirs = [d for d in sorted(sys.argv[1:])
            if os.path.exists(os.path.join(d, "journal.jsonl"))]
    tot = {"events": 0, "overlaps": 0, "zero_gaps": 0, "exogenous": 0,
           "repeats_left": 0, "quiet_turns": 0, "turns": 0,
           "world_own_turns": 0}
    measurable = 0
    gapsum = 0
    print(f"{'run':<24}{'ev':>4}{'overlap':>9}{'0-gap':>8}{'window':>8}"
          f"{'exog':>6}{'rept':>6}{'quiet':>7}")
    for d in dirs:
        m = measure(d)
        for k in tot:
            tot[k] += m.get(k) or 0
        gapsum += max(m["events"] - 1, 0)
        measurable += m["events"] if m.get("knows_by") else 0
        print(f"{m['run']:<24}{m['events']:>4}"
              f"{'-' if m.get('overlaps') is None else m['overlaps']:>9}"
              f"{_pct(m.get('zero_gap_share')):>8}"
              f"{_pct(m.get('window_lived')):>8}"
              f"{'-' if m.get('exogenous') is None else m['exogenous']:>6}"
              f"{m.get('repeats_left', 0):>6}"
              f"{_pct(m.get('quiet_share')):>7}")
    if tot["events"]:
        able = measurable > 0
        print(f"{'TOTAL':<24}{tot['events']:>4}"
              f"{tot['overlaps'] if able else '-':>9}"
              f"{tot['zero_gaps'] / gapsum:>7.0%}"
              f"{'':>8}{tot['exogenous'] if able else '-':>6}"
              f"{tot['repeats_left']:>6}"
              f"{tot['quiet_turns'] / tot['turns'] if tot['turns'] else 0:>6.0%}")
        print(f"\nworld's own turns: {tot['world_own_turns']}   "
              f"events measurable for occupancy: {measurable}/{tot['events']}")
