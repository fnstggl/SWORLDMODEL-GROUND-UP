"""Mechanical checks anybody can re-run over a finished run's artifacts.

Nothing here is a judgment about whether a trajectory is believable --
that is what people are for.  These are the claims that can be settled by
looking: that the resolution never reached anyone who was not allowed to
see it, that nobody saw an item they had not observed, that time never
went backwards, that every committed event has a cause, that no committed
event is a word-for-word repeat of another, that every wake carries a
real provenance, and that replay reproduced the run exactly with no model
calls at all.
"""
from __future__ import annotations

import json
import os
import sys

#: The five kinds of reason a wake is allowed to exist for.  A wake with
#: anything else -- or with nothing -- is a poll wearing a costume.
WAKE_PROVENANCE = {"actor_plan", "observed_event", "world_process",
                   "known_deadline", "action_completion"}


def _jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check(run_dir: str) -> dict:
    fails: list[str] = []
    scene = _json(os.path.join(run_dir, "compiled_scene.json"))
    events = _jsonl(os.path.join(run_dir, "journal.jsonl"))
    ledger = _jsonl(os.path.join(run_dir, "ledger.jsonl"))
    views = _jsonl(os.path.join(run_dir, "actor_views.jsonl"))
    wakes = _jsonl(os.path.join(run_dir, "grounded_wakes.jsonl"))
    replay = _json(os.path.join(run_dir, "replay_verification.json"))

    # ---- the resolution reaches the judge and the verifier, nobody else
    resolution = scene["resolution"]
    stem = resolution.strip()[:60]
    for name in ("actor_views.jsonl", "actor_exchanges.jsonl",
                 "world_exchanges.jsonl", "ledger.jsonl"):
        path = os.path.join(run_dir, name)
        if os.path.exists(path):
            blob = open(path, encoding="utf-8").read()
            if stem and stem in blob:
                fails.append(f"the resolution appears in {name}")

    # ---- shared_context is the world's, not the actors'
    shared = (scene.get("shared_context") or "").strip()
    if len(shared) > 40:
        probe = shared[:40]
        for v in views:
            if probe in v.get("rendered", ""):
                fails.append("shared_context appears in an actor's prompt")
                break

    # ---- nobody sees an item they have not observed
    for v in views:
        who = v["actor"]
        for item in v["view"].get("observed_events", []):
            rec = next((e for e in events
                        if e["description"] == item["description"]), None)
            if rec and who not in (rec.get("observed_by") or []):
                fails.append(f"{who} was shown {rec['event_id']} unobserved")

    # ---- time never goes backwards, and every event has a cause
    times = [e["t"] for e in events]
    if times != sorted(times):
        fails.append("time moved backwards in the journal")
    if any(e.get("cause") is None for e in events):
        fails.append("a committed event has no cause")

    # ---- the same thing does not happen twice, word for word
    seen: dict[str, str] = {}
    for e in events:
        key = e["description"].strip().casefold()
        if key in seen:
            fails.append(f"{e['event_id']} repeats {seen[key]} word for word")
        seen[key] = e["event_id"]

    # ---- every wake exists for one of the five reasons
    for w in wakes:
        if w.get("provenance") not in WAKE_PROVENANCE:
            fails.append(f"a wake has provenance {w.get('provenance')!r}")
        if not (w.get("reason") or "").strip():
            fails.append("a wake exists with no reason")

    # ---- replay reproduced it exactly, having asked nothing
    if not replay.get("exact"):
        fails.append("replay was not exact")
    if replay.get("llm_calls"):
        fails.append(f"replay made {replay['llm_calls']} model calls")
    if replay.get("ledger_integrity"):
        fails.append(f"ledger integrity: {replay['ledger_integrity'][:2]}")
    if not replay.get("checked", {}).get("events"):
        fails.append("replay verified no events at all (vacuous)")

    return {"run": os.path.basename(run_dir.rstrip("/")),
            "events": len(events), "ledger_records": len(ledger),
            "wakes": len(wakes), "failures": fails}


if __name__ == "__main__":
    bad = 0
    for d in sorted(sys.argv[1:]):
        if not os.path.exists(os.path.join(d, "replay_verification.json")):
            continue
        r = check(d)
        bad += len(r["failures"])
        mark = "ok " if not r["failures"] else "FAIL"
        print(f"{mark} {r['run']:<28} {r['events']:>3} events "
              f"{r['ledger_records']:>4} records {r['wakes']:>3} wakes")
        for f in r["failures"]:
            print(f"       - {f}")
    print(f"\n{'all checks passed' if not bad else str(bad) + ' failures'}")
    sys.exit(1 if bad else 0)
