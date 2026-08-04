#!/usr/bin/env python3
"""Record the bounded continuation wakeup for the current idle window.

Part of the worker_silent_death correction (FAILURE_LEDGER 2026-08-04): while
acceptance is incomplete, the Stop hook refuses to let a turn end unless an
unexpired continuation is armed in ``.agent-run/CONTINUATION.json``. This tool
is the sanctioned writer for that record. Run it immediately after scheduling
the real wakeup (send_later / trigger), with the same deadline:

    python3 .claude/tools/arm_continuation.py --minutes 45 \
        --reason "watching spoof-fix worker" --trigger-id trig_xxx \
        --workers spoof-fix

The record is informational state, not a scheduler: arming here without
scheduling the matching wakeup bounds nothing. The tool therefore refuses
windows over 24 hours and empty reasons, and always overwrites atomically —
the newest armed window is the only one that counts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import hook_state as hs  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Record the bounded continuation wakeup (CONTINUATION.json)."
    )
    parser.add_argument("--minutes", type=float, required=True,
                        help="minutes until the scheduled wakeup fires (0 < N <= 1440)")
    parser.add_argument("--reason", required=True,
                        help="what the wakeup is watching, shown by SessionStart")
    parser.add_argument("--trigger-id", default=None,
                        help="scheduler id of the real wakeup, if known")
    parser.add_argument("--workers", default="",
                        help="comma-separated worker names this window covers")
    args = parser.parse_args(argv)

    if not (0 < args.minutes <= 24 * 60):
        parser.error("--minutes must be in (0, 1440]")
    if not args.reason.strip():
        parser.error("--reason must be non-empty")

    root = hs.project_dir()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    payload = {
        "schema_version": 1,
        "armed_at": now.isoformat(),
        "armed_until": (now + dt.timedelta(minutes=args.minutes)).isoformat(),
        "minutes": args.minutes,
        "reason": args.reason.strip(),
        "trigger_id": args.trigger_id,
        "workers": [w for w in (s.strip() for s in args.workers.split(",")) if w],
    }
    hs.atomic_write_json(hs.continuation_path(root), payload)
    print(json.dumps({"armed_until": payload["armed_until"],
                      "path": str(hs.continuation_path(root))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
