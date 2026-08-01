"""Take the replay proof again, from the ledger that was persisted.

Replaying what was written to disk is the proof; replaying the live
world's own in-memory list would only show that the process can talk to
itself.  So this can be re-run at any time, by anyone, against a finished
run -- and it is the same code path the run itself used at the end.

The one thing it cannot re-derive is EXACTNESS against the live world,
which existed only while the process was running.  What it does check is
that the persisted ledger replays with no model calls at all, that its
internal references hold, and that it verifies a non-empty run rather
than reporting success over nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sworldmodel import canonical_json  # noqa: E402
from sworldmodel.semantic_runtime.replay import replay_trajectory  # noqa: E402
from sworldmodel.semantic_runtime.trace import read_ledger  # noqa: E402


def reverify(run_dir: str, *, write: bool = False) -> dict:
    records = read_ledger(run_dir)
    fresh = replay_trajectory(records)
    # THE DIGEST, RE-DERIVED.  This is the part that makes tampering
    # detectable from disk: rewrite a description or a terminal record and
    # the hash of the persisted ledger stops matching the one taken when it
    # was written.  Without it a reviewer rewrote every event in a run and
    # this tool still said exact=True.
    stamp = os.path.join(run_dir, "ledger_digest.txt")
    fresh["digest_matches"] = None
    if os.path.exists(stamp):
        want = open(stamp).read().strip()
        got = hashlib.sha256(canonical_json(records).encode()).hexdigest()
        fresh["digest_matches"] = (want == got)
        fresh["ledger_digest"] = got
    path = os.path.join(run_dir, "replay_verification.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            original = json.load(f)
        # the live-world comparison is only possible while that world
        # exists, so it is carried over and LABELLED rather than re-derived
        fresh["exact_during_run"] = original.get("exact")
        fresh["exact"] = None
    if write:
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(fresh, indent=1, default=str))
    return fresh


if __name__ == "__main__":
    write = "--write" in sys.argv
    bad = 0
    for d in sorted(a for a in sys.argv[1:] if not a.startswith("--")):
        if not os.path.exists(os.path.join(d, "ledger.jsonl")):
            continue
        v = reverify(d, write=write)
        ok = (not v["ledger_integrity"] and v["llm_calls"] == 0
              and v["checked"].get("events")
              and v.get("digest_matches") is not False)
        bad += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'} {os.path.basename(d.rstrip('/')):<28} "
              f"digest={v.get('digest_matches')} "
              f"exact_during_run={v.get('exact_during_run')} "
              f"calls={v['llm_calls']} "
              f"events={v['checked'].get('events')} "
              f"integrity={v['ledger_integrity'] or 'ok'}")
    sys.exit(1 if bad else 0)
