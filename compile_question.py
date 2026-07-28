"""Compile a natural-language social question into a runnable starting
scene (minimal_scene_v1 -- the production compiler).

Usage:
  python3 compile_question.py "your question" \
      [--start 2026-07-27T09:00:00-05:00] [--cutoff 2026-08-10T09:00:00-05:00] \
      [--context "extra user context"] [--evidence-file docs.txt] \
      [--out artifacts/scenes/name] [--model deepseek-chat]

Two semantic LLM calls normally (scene + independent adversarial review),
three maximum (one targeted correction) -- enforced in code.  The result is
a four-field scene manifest instantiated directly into the persistent
runtime; artifacts (exact prompts, raw responses, manifests, validation,
bindings, ledger, metrics) land under --out.

Without --evidence-file the compiler runs in model_memory_unverified mode:
it tests compiler robustness and semantic world shape, NOT current
real-world facts.

--compiler legacy runs the superseded ~200-call multi-stage compiler for
diagnostic comparison only; it is never selected automatically.
"""
import argparse
import datetime as _dt
import re
import sys


def _default_start() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(
        microsecond=0).isoformat()


def _default_cutoff(start: str) -> str:
    t = _dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
    return (t + _dt.timedelta(days=14)).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("question")
    ap.add_argument("--start", default=None,
                    help="tz-aware ISO start (default: now UTC)")
    ap.add_argument("--cutoff", default=None,
                    help="tz-aware ISO cutoff (default: start + 14 days)")
    ap.add_argument("--context", default=None,
                    help="optional user-provided context string")
    ap.add_argument("--evidence-file", default=None,
                    help="optional evidence package (text file)")
    ap.add_argument("--out", default=None, help="artifact directory")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--compiler", choices=["minimal", "legacy"],
                    default="minimal",
                    help="'legacy' is an explicit diagnostic flag only")
    args = ap.parse_args()

    out = args.out
    if out is None:
        slugq = re.sub(r"[^a-z0-9]+", "_", args.question.lower())[:40].strip("_")
        out = f"artifacts/scenes/{slugq}"

    if args.compiler == "legacy":
        print("[diagnostic] running the SUPERSEDED legacy multi-stage "
              "compiler (~200 LLM calls); minimal_scene_v1 is the "
              "production path", file=sys.stderr)
        from compiler.legacy import compile_question as legacy_compile
        from compiler.legacy.llm import Caller
        result = legacy_compile(args.question, caller=Caller(args.model),
                                out_dir=out)
        print(result.summary())
        return 0 if result.status == "compiled" else 1

    from compiler import SceneCaller, compile_scene
    start = args.start or _default_start()
    cutoff = args.cutoff or _default_cutoff(start)
    evidence = None
    if args.evidence_file:
        with open(args.evidence_file, "r", encoding="utf-8") as f:
            evidence = f.read()
    result = compile_scene(args.question, start, cutoff,
                           context=args.context, evidence=evidence,
                           caller=SceneCaller(args.model), out_dir=out)
    print(result.summary())
    return 0 if result.status in ("compiled", "corrected") else 1


if __name__ == "__main__":
    sys.exit(main())
