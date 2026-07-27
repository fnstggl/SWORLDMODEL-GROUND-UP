"""Compile and run every acceptance case through the DISCOVERY pipeline.

    python3 compile_cases.py                 # all cases, scripted minds
    python3 compile_cases.py traffic_study   # one case
    python3 compile_cases.py --stage llm     # same frozen worlds, live minds
    python3 compile_cases.py --reuse         # replay frozen approved worlds
    python3 compile_cases.py --legacy        # the retired one-shot pipeline

The default is compiler/worldcompiler.py: five small discovery calls,
code-owned assembly, causal proofs, item-at-a-time binding, deterministic
emission, and the unchanged lowering + runtime. The one-shot
whole-scenario pipeline remains importable behind --legacy for comparison
only; it is no longer the default.

A case may carry cases/<name>/expectation.json:
    {"expected_answer": ..., "why": "hand-derivation from the evidence"}
A compiled case that contradicts its hand-derived answer is a FAILURE even
though it compiled -- and a negative answer produced by a world whose
affordances were never exercised is flagged, never blessed.

expected_answer of null or "REFUSAL" means the case MUST refuse: the
'why' is then the hand-argument for why no honest answer exists. The
expectation file is the single source of truth for that -- a separately
maintained list of refusal cases silently rots the moment a case is
added, scoring correct refusals as failures.

Artifacts land in artifacts/compiled/<case>/.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASES_DIR = os.path.join(HERE, "cases")
OUT_ROOT = os.path.join(HERE, "artifacts", "compiled")

#: Cases with no expectation.json at all that must still refuse.
EXPECTED_REFUSAL = {"insufficient_merger"}


def expects_refusal(name: str, expectation: dict) -> bool:
    """A case must refuse when its expectation says so -- expected_answer
    null or "REFUSAL" -- or, lacking an expectation file, when it is named
    in EXPECTED_REFUSAL."""
    if expectation:
        answer = expectation.get("expected_answer")
        return answer is None or str(answer).upper() == "REFUSAL"
    return name in EXPECTED_REFUSAL

#: A case that must refuse has to refuse because the EVIDENCE cannot support
#: a world -- not because the model tripped over a contract, and not because
#: of a formatting-convention gap (the audit's D16: LOWERING_GAP is a
#: capability statement, not an evidence judgement).
SUBSTANTIVE_REFUSALS = {"REALITY_REVIEW_REJECTED", "NO_CAUSAL_PRODUCER",
                        "NOTHING_SCHEDULED", "AMBIGUOUS_QUESTION",
                        "UNSUPPORTED_CAPABILITY", "INSUFFICIENT_EVIDENCE"}


def load(name):
    d = os.path.join(CASES_DIR, name)
    with open(os.path.join(d, "question.json"), encoding="utf-8") as f:
        q = json.load(f)
    with open(os.path.join(d, "evidence_package.json"), encoding="utf-8") as f:
        e = json.load(f)
    return q, e


def load_optional(name, filename):
    path = os.path.join(CASES_DIR, name, filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
    reuse = "--reuse" in sys.argv
    legacy = "--legacy" in sys.argv
    names = args or sorted(
        d for d in os.listdir(CASES_DIR)
        if os.path.isdir(os.path.join(CASES_DIR, d)))

    if legacy:
        from compiler.pipeline import compile_case as run_one

        def compile_one(q, e, outdir, scripts):
            return run_one(q, e, outdir, stage=stage, scripts=scripts,
                           reuse_scenario=reuse)
    else:
        from compiler.worldcompiler import compile_question

        def compile_one(q, e, outdir, scripts):
            return compile_question(q, e, outdir, stage=stage,
                                    scripts=scripts, reuse=reuse)

    summary = []
    for name in names:
        q, e = load(name)
        expectation = load_optional(name, "expectation.json") or {}
        outdir = os.path.join(OUT_ROOT, name)
        print(f"\n=== {name} ===\n  {q['question']}")
        try:
            result = compile_one(q, e, outdir, load_script(name))
        except Exception:                       # an uncaught crash is its own
            import traceback                    # failure class, never silent
            traceback.print_exc()
            summary.append({"case": name, "stage": "CRASH",
                            "expected_refusal": expects_refusal(name, expectation),
                            "reason": traceback.format_exc().strip()
                            .splitlines()[-1]})
            continue
        m = result["metrics"]
        row = {"case": name, "stage": result["stage"],
               "expected_refusal": expects_refusal(name, expectation),
               "pipeline": "legacy" if legacy else "discovery",
               "discovery_calls": m.get("discovery_calls",
                                        m.get("semantic_calls", 0)),
               "binding_calls": m.get("binding_calls", 0),
               "repairs": m.get("repairs_by_step",
                                m.get("revision_calls", 0)),
               "tokens": m.get("model_tokens",
                               m.get("prompt_tokens", 0)
                               + m.get("completion_tokens", 0)),
               "lowering_ms": m.get("lowering_ms", 0.0),
               "runtime_ms": m.get("runtime_ms", 0.0)}
        if result["stage"] == "COMPILED":
            out = result.get("outcome")
            c = result["compiled"]
            row["answer"] = (out.answer or {}).get("answer") if out else None
            row["run_status"] = out.status if out else None
            row["actors"] = len(c.world.actors)
            row["affordances"] = len(c.world.action_defs)
            row["artifact_risk"] = bool(result.get("artifact_risk"))
            print(f"  COMPILED: {row['actors']} participants, "
                  f"{row['affordances']} affordances, "
                  f"{len(c.world.processes)} processes")
            print(f"  ANSWER: {row['answer']!r} ({row['run_status']})")
            if result.get("script_mismatch"):
                row["script_mismatch"] = True
                print(f"  SCRIPT MISMATCH: {result['script_mismatch'][:150]}")
        else:
            row["reason"] = result["reason"]
            row["model_declared_insufficient"] = (
                result.get("detail", {}).get("declared_by")
                == "semantic compiler"
                or result.get("detail", {}).get("mode") == "question_only")
            print(f"  {result['stage']}: {result['reason'][:160]}")
        if expectation:
            row["expected_answer"] = expectation.get("expected_answer")
        summary.append(row)

    os.makedirs(OUT_ROOT, exist_ok=True)
    with open(os.path.join(OUT_ROOT, "summary.json"), "w",
              encoding="utf-8") as f:
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
        if correct and not refused:
            if "expected_answer" in r \
                    and r.get("answer") != r["expected_answer"]:
                correct = False
                note = (f"  <- answer {r.get('answer')!r} contradicts the "
                        f"hand-derived {r['expected_answer']!r}")
            elif r.get("artifact_risk"):
                correct = False
                note = ("  <- negative answer from a world that was never "
                        "exercised; a statement about the minds, not the "
                        "situation")
        ok &= correct
        mark = "OK " if correct else "BAD"
        print(f"  [{mark}] {r['case']:<22} {r['stage']:<26} "
              f"answer={r.get('answer')!r}{note}")
    print(f"\n{'all cases behaved as required' if ok else 'SOME CASES MISBEHAVED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
