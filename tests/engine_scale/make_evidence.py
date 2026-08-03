"""Copy a completed monitored scale job's durable proof into the
committed evidence tree, and build the evidence hashes manifest.

INFRASTRUCTURE TEST ONLY: scripted/shallow scale exercise of the
AgentSociety execution substrate -- infrastructure rather than calibrated
societal simulation; no population realism claim.

``.agent-run/jobs/`` is gitignored (ephemeral runner scratch), so the
durable per-job proof is copied here and committed:

    python3 tests/engine_scale/make_evidence.py snapshot \
        --job-id phase11-scale1000-p1-segB \
        --copy /path/to/reconciliation.json=reconciliation.json ...

    python3 tests/engine_scale/make_evidence.py manifest

Copies are verbatim; the manifest records the sha256 of every committed
evidence file so the verification tier (and the completion receipt) can
prove content continuity byte-exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
EVIDENCE = HERE / "evidence"
JOBS_DIR = REPO_ROOT / ".agent-run" / "jobs"

STATEMENT = (
    "INFRASTRUCTURE TEST ONLY: scripted/shallow scale exercise of the "
    "AgentSociety execution substrate -- infrastructure rather than "
    "calibrated societal simulation; no population realism claim.")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_snapshot(args) -> int:
    job_dir = EVIDENCE / args.job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    record_path = JOBS_DIR / args.job_id / "job.json"
    if not record_path.exists():
        raise SystemExit(f"no final job record at {record_path}")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("state") != "finished" or record.get("exit_code") != 0:
        raise SystemExit(
            f"refusing to snapshot a non-passing job: state="
            f"{record.get('state')} exit={record.get('exit_code')}")
    shutil.copy2(record_path, job_dir / "job.json")
    copied = ["job.json"]
    for item in args.copies or []:
        src, _, dst = item.partition("=")
        source = Path(src)
        if not source.exists():
            raise SystemExit(f"copy source missing: {source}")
        target = job_dir / (dst or source.name)
        shutil.copy2(source, target)
        copied.append(target.name)
    print(json.dumps({"job_id": args.job_id, "copied": sorted(copied)}))
    return 0


def cmd_manifest(args) -> int:
    del args
    files = {}
    for path in sorted(EVIDENCE.rglob("*")):
        if path.is_file() and path.name != "hashes_manifest.json":
            files[str(path.relative_to(EVIDENCE))] = _sha256(path)
    manifest = {
        "schema_version": 1,
        "statement": STATEMENT,
        "generated_unix": time.time(),
        "file_count": len(files),
        "files": files,
    }
    out = EVIDENCE / "hashes_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                              sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(out), "file_count": len(files)}))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=STATEMENT)
    sub = parser.add_subparsers(dest="mode", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--job-id", required=True)
    snap.add_argument("--copy", dest="copies", action="append",
                      metavar="SRC=DSTNAME")
    snap.set_defaults(func=cmd_snapshot)
    man = sub.add_parser("manifest")
    man.set_defaults(func=cmd_manifest)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
