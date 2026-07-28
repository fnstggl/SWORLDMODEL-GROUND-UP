"""Acceptance harness for minimal_scene_v1.

For every dataset case: compile -> review -> optional correction ->
deterministic validation -> runtime instantiation -> genesis terminal
check -> serialization/replay check.  No full forecast simulations.

Stores the complete per-case artifact set under
artifacts/scene_acceptance/<dataset>/<id>/ and aggregate metrics + a
summary report.  Never crashes on a case: every outcome is structured.

Usage: python3 run_scene_acceptance.py [dataset.json ...] [--workers 4]
       (default dataset: acceptance/dataset_core.json)
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from compiler import SceneCaller, compile_scene

HERE = os.path.dirname(os.path.abspath(__file__))


def run_case(case: dict, base: str) -> dict:
    out = os.path.join(base, case["id"])
    caller = SceneCaller()
    result = compile_scene(case["question"], case["start"], case["cutoff"],
                           context=case.get("context"), caller=caller,
                           out_dir=out)
    return {"id": case["id"], "kind": case["kind"],
            "category": case.get("category"),
            "historical": bool(case.get("historical")),
            "status": result.status, "reason": result.reason[:300],
            "semantic_calls": result.metrics.get("semantic_calls"),
            "provider_requests": result.metrics.get("provider_requests"),
            "wall_s": result.metrics.get("wall_s"),
            "actors": [a["name"] for a in (result.manifest or {}).get(
                "actors", [])],
            "out_dir": out}


def pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def summarize(rows: list) -> dict:
    suff = [r for r in rows if r["kind"] == "sufficient"]
    insuff = [r for r in rows if r["kind"] == "insufficient"]
    ok = [r for r in suff if r["status"] in ("compiled", "corrected")]
    walls = sorted(r["wall_s"] for r in rows if r["wall_s"] is not None)
    p95 = walls[int(0.95 * (len(walls) - 1))] if walls else None
    calls = sorted(r["semantic_calls"] for r in rows
                   if r["semantic_calls"] is not None)
    return {
        "total": len(rows),
        "sufficient": {
            "n": len(suff),
            "compiled_first_pass": pct(
                sum(1 for r in suff if r["status"] == "compiled"), len(suff)),
            "corrected": pct(
                sum(1 for r in suff if r["status"] == "corrected"), len(suff)),
            "schema_success": pct(
                sum(1 for r in suff
                    if "SCHEMA_INVALID" not in r["reason"]
                    and "TECHNICAL_FAILURE" not in r["reason"]), len(suff)),
            "instantiated": pct(len(ok), len(suff)),
            "abstained": sum(1 for r in suff if r["status"] == "abstained"),
            "failed": sum(1 for r in suff if r["status"] == "failed"),
        },
        "insufficient": {
            "n": len(insuff),
            "honest_abstention_or_structured": pct(
                sum(1 for r in insuff
                    if r["status"] in ("abstained", "failed")), len(insuff)),
            "abstained": sum(1 for r in insuff
                             if r["status"] == "abstained"),
            "compiled_anyway": sum(1 for r in insuff
                                   if r["status"] in ("compiled",
                                                      "corrected")),
        },
        "semantic_calls": {
            "median": statistics.median(calls) if calls else None,
            "max": max(calls) if calls else None,
            "over_budget": sum(1 for c in calls if c > 3),
        },
        "wall_s": {"median": statistics.median(walls) if walls else None,
                   "p95": p95},
        "failures": [{"id": r["id"], "status": r["status"],
                      "reason": r["reason"][:160]}
                     for r in rows if r["status"] == "failed"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("datasets", nargs="*",
                    default=["acceptance/dataset_core.json"])
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    all_rows = []
    for ds_path in args.datasets or ["acceptance/dataset_core.json"]:
        with open(ds_path) as f:
            cases = json.load(f)
        name = os.path.splitext(os.path.basename(ds_path))[0]
        base = os.path.join(HERE, "artifacts", "scene_acceptance", name)
        rows = []
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(run_case, c, base): c["id"] for c in cases}
            for fut in as_completed(futs):
                row = fut.result()
                rows.append(row)
                print(f"  [{len(rows):>3}/{len(cases)}] {row['status']:<10} "
                      f"{row['id']} ({row['semantic_calls']} calls, "
                      f"{row['wall_s']}s)", flush=True)
        rows.sort(key=lambda r: r["id"])
        summary = summarize(rows)
        payload = {"dataset": ds_path, "rows": rows, "summary": summary}
        out_json = os.path.join(base, "RESULTS.json")
        os.makedirs(base, exist_ok=True)
        with open(out_json, "w") as f:
            json.dump(payload, f, indent=1)
        print(f"\n=== {name} ===")
        print(json.dumps(summary, indent=1))
        print(f"results -> {out_json}")
        all_rows.extend(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
