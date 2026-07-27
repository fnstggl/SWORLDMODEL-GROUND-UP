"""Compile a natural-language question into a runnable world.

Usage:
  python3 compile_question.py "your question" [--asof YYYY-MM-DD]
      [--docs evidence.json] [--out artifacts/compiled/name]
      [--model deepseek-chat]

evidence.json is a list of {"id", "title", "date", "content"} documents;
providing it switches the compiler into evidence_docs mode (claims labeled
'verified' must cite these documents).  Without it, the compiler runs in
model_memory mode.

Compilation needs DEEPSEEK_API_KEY.  The result is a WorldBundle under
--out; instantiate it later with compiler.instantiate(bundle) and run
Engine(world, minds, terminal).run() -- zero further LLM calls to rebuild
the world.
"""
import argparse
import json
import os
import re
import sys

from compiler import compile_question
from compiler.llm import Caller


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("question")
    ap.add_argument("--asof", default=None, help="compile-day (YYYY-MM-DD)")
    ap.add_argument("--docs", default=None, help="evidence documents JSON")
    ap.add_argument("--out", default=None, help="artifact directory")
    ap.add_argument("--model", default="deepseek-chat")
    args = ap.parse_args()

    docs = None
    if args.docs:
        with open(args.docs, "r", encoding="utf-8") as f:
            docs = json.load(f)
    out = args.out
    if out is None:
        slug = re.sub(r"[^a-z0-9]+", "_", args.question.lower())[:40].strip("_")
        out = os.path.join("artifacts", "compiled", slug)

    result = compile_question(args.question, asof=args.asof,
                              evidence_docs=docs, caller=Caller(args.model),
                              out_dir=out)
    print(result.summary())
    return 0 if result.status == "compiled" else 1


if __name__ == "__main__":
    sys.exit(main())
