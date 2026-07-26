"""Compile and run every acceptance case.

    python3 compile_cases.py                 # all cases, mechanical minds
    python3 compile_cases.py traffic_study   # one case
    python3 compile_cases.py --stage llm     # Stage 2: same worlds, live minds
    python3 compile_cases.py --reuse         # replay frozen approved worlds

Artifacts land in artifacts/compiled/<case>/.
"""
import json
import os
import sys

from compiler.pipeline import compile_case

HERE = os.path.dirname(os.path.abspath(__file__))
CASES_DIR = os.path.join(HERE, "cases")
OUT_ROOT = os.path.join(HERE, "artifacts", "compiled")

EXPECTED_REFUSAL = {"insufficient_merger"}

#: A case that must refuse has to refuse because the EVIDENCE cannot support a
#: world -- not because the model tripped over the contract. Stopping at a
#: formatting slip would be a false positive dressed as a success.
SUBSTANTIVE_REFUSALS = {"REALITY_REVIEW_REJECTED", "NO_CAUSAL_PRODUCER",
                        "NOTHING_SCHEDULED", "LOWERING_GAP"}


def load(name):
    d = os.path.join(CASES_DIR, name)
    with open(os.path.join(d, "question.json"), encoding="utf-8") as f:
        q = json.load(f)
    with open(os.path.join(d, "evidence_package.json"), encoding="utf-8") as f:
        e = json.load(f)
    return q, e


def load_script(name):
    """A fixture may supply its own scripted minds (test harness only)."""
    path = os.path.join(CASES_DIR, name, "scripted_minds.py")
    if not os.path.exists(path):
        return {}
    ns = {}
    with open(path, encoding="utf-8") as f:
        exec(compile(f.read(), path, "exec"), ns)
    return ns.get("SCRIPT", {})


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    stage = "llm" if "--stage" in sys.argv and "llm" in sys.argv else "scripted"
    reuse = "--reuse" in sys.argv     # replay the frozen approved world
    names = args or sorted(
        d for d in os.listdir(CASES_DIR)
        if os.path.isdir(os.path.join(CASES_DIR, d)))

    summary = []
    for name in names:
        q, e = load(name)
        outdir = os.path.join(OUT_ROOT, name)
        print(f"\n=== {name} ===\n  {q['question']}")
    result = compile_case(q, e, outdir, stage=stage,
                              scripts=load_script(name), reuse_scenario=reuse)
        m = result["metrics"]
        row = {"case": name, "stage": result["stage"],
               "expected_refusal": name in EXPECTED_REFUSAL,
               "semantic_calls": m["semantic_calls"],
               "reviewer_calls": m["reviewer_calls"],
               "revision_calls": m["revision_calls"],
               "tokens": m["prompt_tokens"] + m["completion_tokens"],
               "lowering_ms": m["lowering_ms"], "runtime_ms": m["runtime_ms"]}
        if result["stage"] == "COMPILED":
            out = result.get("outcome")
            c = result["compiled"]
            row["answer"] = (out.answer or {}).get("answer") if out else None
            row["run_status"] = out.status if out else None
            row["actors"] = len(c.world.actors)
            row["affordances"] = len(c.world.action_defs)
            row["events"] = out.metrics["events_processed"] if out else 0
            print(f"  COMPILED: {row['actors']} participants, "
                  f"{row['affordances']} affordances, "
                  f"{len(c.world.processes)} processes")
            print(f"  ANSWER: {row['answer']!r} ({row['run_status']}) "
                  f"from {len((out.answer or {}).get('computed_from', []))} "
                  f"producing records")
        else:
            row["reason"] = result["reason"]
            row["model_declared_insufficient"] = (
                result.get("detail", {}).get("declared_by") == "semantic compiler")
            print(f"  {result['stage']}: {result['reason'][:160]}")
        summary.append(row)

    os.makedirs(OUT_ROOT, exist_ok=True)
    with open(os.path.join(OUT_ROOT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
        f.write("\n")

    print("\n=== summary ===")
    ok = True
    for r in summary:
        refused = r["stage"] != "COMPILED"
        correct = refused == r["expected_refusal"]
        note = ""
        if correct and r["expected_refusal"]:
            substantive = (r["stage"] in SUBSTANTIVE_REFUSALS
                           or r.get("model_declared_insufficient"))
            if not substantive:
                correct = False
                note = ("  <- refused on a contract slip, NOT because the "
                        "evidence is insufficient")
        ok &= correct
        mark = "OK " if correct else "BAD"
        print(f"  [{mark}] {r['case']:<22} {r['stage']:<26} "
              f"answer={r.get('answer')!r}{note}")
    print(f"\n{'all cases behaved as required' if ok else 'SOME CASES MISBEHAVED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
