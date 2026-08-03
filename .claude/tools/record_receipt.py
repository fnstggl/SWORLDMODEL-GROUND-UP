#!/usr/bin/env python3
"""Write a task-completion evidence receipt atomically.

A receipt is the only accepted proof that a task's validation actually ran. The
``TaskCompleted`` gate checks that a receipt exists, that it passed, and that
its ``git_sha`` equals the SHA the task is being completed at -- a receipt
produced against a different SHA can never satisfy completion.

Two modes:

*Record an already-finished command*::

    python3 .claude/tools/record_receipt.py \
        --task-id my-task \
        --command 'python3 -m pytest tests/control_plane -q' \
        --exit-code 0 \
        --started-at 2026-01-01T00:00:00+00:00 \
        --finished-at 2026-01-01T00:01:00+00:00 \
        --artifact artifacts/report.json

*Run the command and record the result in one step* (recommended, because the
recorded exit code and timestamps are then observed rather than asserted)::

    python3 .claude/tools/record_receipt.py --task-id my-task --run -- \
        python3 -m pytest tests/control_plane -q

Receipts land in ``.agent-run/receipts/`` and are written via a temp file plus
``os.replace``, so a reader never observes a half-written receipt.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import hook_state as hs  # noqa: E402


def split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1 :]
    return argv, []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="record_receipt.py",
        description="Write an atomic, SHA-bound evidence receipt for a task.",
    )
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--command", default=None, help="exact command the receipt attests to")
    parser.add_argument("--exit-code", type=int, default=None)
    parser.add_argument("--started-at", default=None, help="ISO-8601; defaults to now")
    parser.add_argument("--finished-at", default=None, help="ISO-8601; defaults to now")
    parser.add_argument("--artifact", action="append", default=[], dest="artifacts",
                        help="repeatable; artifact produced by the run")
    parser.add_argument("--config-hash", action="append", default=[], dest="config_hashes",
                        help="repeatable NAME=PATH; records sha256 of PATH")
    parser.add_argument("--worktree", default=None, help="defaults to the git worktree root")
    parser.add_argument("--sha", default=None, help="override the recorded git SHA (rarely correct)")
    parser.add_argument("--invalid", action="store_true",
                        help="mark the receipt invalid (records a run that must not count)")
    parser.add_argument("--run", action="store_true",
                        help="run the command after '--' and record its observed result")
    parser.add_argument("--timeout", type=float, default=None,
                        help="with --run: seconds before the child is killed and the receipt fails")
    parser.add_argument("--out", default=None, help="explicit output path for the receipt")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    own_args, child_cmd = split_argv(argv)
    parser = build_parser()
    args = parser.parse_args(own_args)

    root = hs.project_dir()

    if args.run:
        if not child_cmd:
            parser.error("--run requires the command after '--'")
        command = " ".join(child_cmd)
        started = hs.utc_now_iso()
        try:
            proc = subprocess.run(
                child_cmd, cwd=str(root), capture_output=True, text=True,
                timeout=args.timeout, check=False,
            )
            exit_code = proc.returncode
            output_tail = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-2000:]
        except subprocess.TimeoutExpired:
            exit_code = 124
            output_tail = f"command exceeded --timeout {args.timeout}s and was killed"
        except OSError as exc:
            exit_code = 127
            output_tail = f"could not execute: {exc}"
        finished = hs.utc_now_iso()
    else:
        if args.command is None:
            parser.error("--command is required unless --run is used")
        if args.exit_code is None:
            parser.error("--exit-code is required unless --run is used")
        command = args.command
        exit_code = args.exit_code
        started = args.started_at or hs.utc_now_iso()
        finished = args.finished_at or hs.utc_now_iso()
        output_tail = None

    for label, value in (("--started-at", started), ("--finished-at", finished)):
        if hs.parse_iso(value) is None:
            parser.error(f"{label} is not a valid ISO-8601 timestamp: {value!r}")

    configuration_hashes: dict[str, str] = {}
    for entry in args.config_hashes:
        if "=" not in entry:
            parser.error(f"--config-hash expects NAME=PATH, got {entry!r}")
        name, _, path_text = entry.partition("=")
        path = Path(path_text)
        if not path.is_absolute():
            path = root / path_text
        digest = hs.sha256_file(path)
        if digest is None:
            parser.error(f"--config-hash path does not exist: {path_text}")
        configuration_hashes[name] = digest

    missing_artifacts = []
    for artifact in args.artifacts:
        path = Path(artifact)
        if not path.is_absolute():
            path = root / artifact
        if not path.exists():
            missing_artifacts.append(artifact)

    worktree = args.worktree or hs.git_worktree_root(root) or str(root)
    receipt = {
        "schema_version": hs.SCHEMA_VERSION,
        "task_id": args.task_id,
        "git_sha": args.sha or hs.git_sha(root) or "unknown",
        "worktree": worktree,
        "command": command,
        "exit_code": exit_code,
        "started_at": started,
        "finished_at": finished,
        "artifact_paths": list(args.artifacts),
        "configuration_hashes": configuration_hashes,
        "valid": not args.invalid and not missing_artifacts,
        "recorded_at": hs.utc_now_iso(),
        "git_branch": hs.git_branch(root),
        "worktree_clean": hs.git_is_clean(root),
    }
    if missing_artifacts:
        receipt["invalid_reason"] = "declared artifacts do not exist: " + ", ".join(missing_artifacts)
    if output_tail is not None:
        receipt["output_tail"] = output_tail

    try:
        if args.out:
            target = Path(args.out)
            if not target.is_absolute():
                target = root / args.out
            problems = hs.receipt_schema_problems(receipt)
            if problems:
                sys.stderr.write("refusing to write invalid receipt: " + "; ".join(problems) + "\n")
                return 2
            hs.atomic_write_json(target, receipt)
        else:
            target = hs.write_receipt(receipt, root)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"record_receipt: {exc}\n")
        return 2

    if not args.quiet:
        sys.stderr.write(
            "recorded receipt {} task={} sha={} exit={} valid={}\n".format(
                target, receipt["task_id"], receipt["git_sha"][:12], receipt["exit_code"], receipt["valid"]
            )
        )
    print(json.dumps({"receipt_path": str(target), "valid": receipt["valid"], "exit_code": exit_code}))

    # A receipt for a failed run is still written (the failure is the evidence),
    # but the tool exits nonzero so a caller cannot mistake it for success.
    return 0 if (exit_code == 0 and receipt["valid"]) else 1


if __name__ == "__main__":
    sys.exit(main())
