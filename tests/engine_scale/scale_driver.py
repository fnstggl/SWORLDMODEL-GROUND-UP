"""CLI driver for the Phase 11 monitored scale jobs.

INFRASTRUCTURE TEST ONLY: scripted/shallow scale exercise of the
AgentSociety execution substrate -- infrastructure rather than calibrated
societal simulation; no population realism claim.

Every monitored job invokes this script FOREGROUND through
``.claude/tools/run_monitored.py`` with a ``--progress-file`` this driver
appends per-chunk / per-tick records to (strong progress).  Modes:

- ``run``: one partition segment (create + ticks, or ``--resume`` the
  persisted workspaces from the driver checkpoint).  When the segment
  ends at the spec's final tick, the exact reconciliation runs and the
  partition summary is written.
- ``aggregate``: read N completed partitions, recompute the aggregate
  from the raw workspace records, and prove it equals the collected
  (driver-ledger) union byte-exactly.

Run with the pinned engine environment, e.g.::

    /home/user/engine-env/bin/python tests/engine_scale/scale_driver.py \
        run --spec tests/engine_scale/specs/scale1000_p1.json \
        --segment A --registry-root /home/user/scale_runs/x/p1 \
        --partition-root /home/user/scale_runs/x/p1 \
        --progress-file /home/user/scale_runs/x/p1/driver/progress.jsonl

The dummy-LLM environment is installed with ``setdefault`` BEFORE any
``agentsociety2`` import (its config module refuses to load without an
API key) and never overrides a caller-provided configuration.  No LLM
call is ever made: the only agent class is the scripted
``ScaleUnitAgent``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Environment BEFORE any agentsociety2 import (dummy credentials; scale
# jobs default to 4 Ray CPUs on this 4-core host -- their own processes,
# so the 2-worker agreement of the shared pytest suites does not apply).
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "dummy")
os.environ.setdefault("AGENTSOCIETY_LLM_API_BASE", "http://localhost:9")
os.environ.setdefault("AGENTSOCIETY_LLM_RAY_MAX_WORKERS", "4")
os.environ.setdefault("AGENTSOCIETY_TRACE_WRITER_ASYNC", "0")
os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from scale_harness import (INFRA_ONLY_STATEMENT, PartitionSpec,  # noqa: E402
                           aggregate_partitions, append_jsonl,
                           run_partition)


def _segment_range(spec: PartitionSpec, segment: str | None):
    if segment is None or segment == "full":
        return spec.ticks_from, spec.ticks_to
    if segment not in spec.segments:
        raise SystemExit(
            f"spec {spec.partition_id} declares no segment {segment!r} "
            f"(has {sorted(spec.segments)})")
    return spec.segments[segment]


def _cmd_run(args) -> int:
    spec = PartitionSpec.load(args.spec)
    tick_from, tick_to = _segment_range(spec, args.segment)
    progress = Path(args.progress_file)
    progress.parent.mkdir(parents=True, exist_ok=True)
    append_jsonl(progress, {
        "event": "job_start", "mode": "run", "statement":
        INFRA_ONLY_STATEMENT, "partition": spec.partition_id,
        "segment": args.segment, "tick_from": tick_from,
        "tick_to": tick_to, "resume": bool(args.resume),
        "agents": spec.agent_count, "unix": time.time()})
    stats = run_partition(
        spec,
        registry_root=args.registry_root,
        partition_root=args.partition_root,
        tick_from=tick_from,
        tick_to=tick_to,
        resume=bool(args.resume),
        progress_path=progress)
    append_jsonl(progress, {
        "event": "job_done", "mode": "run",
        "partition": spec.partition_id, "segment": args.segment,
        "ok_actions": stats["ok_actions"],
        "driver_max_in_flight": stats["driver_max_in_flight"],
        "reconciled": bool(stats.get("reconciliation_ok")),
        "unix": time.time()})
    print(json.dumps({"job": "run", "partition": spec.partition_id,
                      "segment": args.segment, "stats": stats},
                     sort_keys=True, default=str))
    return 0


def _cmd_aggregate(args) -> int:
    progress = Path(args.progress_file)
    progress.parent.mkdir(parents=True, exist_ok=True)
    pairs = []
    for item in args.partitions:
        spec_path, _, root = item.partition("=")
        if not root:
            raise SystemExit(
                f"--partition must be SPEC_JSON=PARTITION_ROOT, got "
                f"{item!r}")
        pairs.append((PartitionSpec.load(spec_path), Path(root)))
    append_jsonl(progress, {
        "event": "job_start", "mode": "aggregate",
        "statement": INFRA_ONLY_STATEMENT,
        "partitions": [spec.partition_id for spec, _ in pairs],
        "unix": time.time()})
    aggregate = aggregate_partitions(pairs, args.out,
                                     progress_path=progress)
    append_jsonl(progress, {
        "event": "job_done", "mode": "aggregate",
        "actions_total": aggregate["totals"]["actions_total"],
        "equal": aggregate["aggregate_sha256"]["equal"],
        "unix": time.time()})
    print(json.dumps({"job": "aggregate", "totals": aggregate["totals"],
                      "aggregate_sha256": aggregate["aggregate_sha256"]},
                     sort_keys=True))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=("Phase 11 scale driver -- " + INFRA_ONLY_STATEMENT))
    sub = parser.add_subparsers(dest="mode", required=True)

    run_p = sub.add_parser("run", help="run one partition segment")
    run_p.add_argument("--spec", required=True)
    run_p.add_argument("--segment", default="full",
                       help="segment name from the spec, or 'full'")
    run_p.add_argument("--registry-root", required=True)
    run_p.add_argument("--partition-root", required=True)
    run_p.add_argument("--progress-file", required=True)
    run_p.add_argument("--resume", action="store_true")
    run_p.set_defaults(func=_cmd_run)

    agg_p = sub.add_parser("aggregate",
                           help="aggregate completed partitions")
    agg_p.add_argument("--partition", dest="partitions", action="append",
                       required=True, metavar="SPEC_JSON=PARTITION_ROOT")
    agg_p.add_argument("--out", required=True)
    agg_p.add_argument("--progress-file", required=True)
    agg_p.set_defaults(func=_cmd_aggregate)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    finally:
        try:
            import ray
            if ray.is_initialized():
                ray.shutdown()
        except Exception:  # noqa: BLE001 - shutdown is best effort
            pass


if __name__ == "__main__":
    raise SystemExit(main())
