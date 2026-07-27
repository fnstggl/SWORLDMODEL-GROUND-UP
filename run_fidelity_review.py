"""Agent C -- world-fidelity review of every ACCEPTED scene, post hoc.

An independent reviewer model (fresh context per scene, a different rubric
from the compile-time reviewer) audits each accepted manifest.  These
calls are an audit AFTER compilation; they are not part of any compile's
semantic-call budget.

Verdict per scene: OK | DEFECT with severity CRITICAL / MAJOR / MINOR.
A CRITICAL defect disqualifies the scene from counting as semantically
successful in the acceptance report."""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from compiler.scene_llm import SceneCaller

HERE = os.path.dirname(os.path.abspath(__file__))

RUBRIC = """You are an independent world-fidelity auditor for a social \
simulator.  You are given a QUESTION (with start/cutoff and optional \
context) and the ACCEPTED four-field starting scene compiled from it \
(actors with private context, shared context, starting events, and a \
natural-language resolution).  The simulation runs AFTER this scene: \
actor models make every decision; the scene must only set the stage.

Audit adversarially and answer each:
1. smallest_world: is this the smallest causally sufficient social world?
2. missing: is any materially relevant actor missing?
3. decorative: is any included actor unable to affect the answer?
4. invented_precision: does the scene state precise schedules, habits, \
numbers, or facts that neither the question, the context, nor common \
knowledge supports?
5. info_boundaries: is each actor's private context only theirs?  Does \
shared context leak private information?
6. prewritten: does any starting event or context sentence pre-decide a \
future actor choice, or make the YES condition already true?
7. observable_resolution: is the resolution an externally observable \
event/record in the persistent history, matching the user's question?
8. leakage: for real historical settings -- does any post-start outcome \
knowledge appear in the scene?
9. genuinely_open: could the simulation genuinely produce either YES or \
NO from this scene?

Severity: CRITICAL = the scene would make the simulation answer the wrong \
question or pre-decide the result; MAJOR = material realism distortion; \
MINOR = cosmetic.  Preserved uncertainty is CORRECT, never a defect.  \
Role-identified actors and collectives-as-single-actors are CORRECT.

Reply with ONLY JSON:
{"verdict": "OK" | "DEFECT",
 "worst_severity": "NONE" | "MINOR" | "MAJOR" | "CRITICAL",
 "defects": [{"aspect": "<one of the 9 keys>", "severity": "...",
              "detail": "..."}]}"""


def review_case(row):
    d = row["out_dir"]
    inp = json.load(open(os.path.join(d, "input.json")))
    scene = json.load(open(os.path.join(d, "final_scene_manifest.json")))
    user = (f"QUESTION: {inp['question']}\nstart: {inp['start']}\n"
            f"cutoff: {inp['cutoff']}\ncontext: {inp.get('context')}\n\n"
            f"ACCEPTED SCENE:\n{json.dumps(scene, indent=1)}\n\n"
            f"Audit now.  Reply with ONLY the JSON verdict.")
    caller = SceneCaller()
    try:
        r = caller.semantic_call("fidelity", RUBRIC, user)
        v = r["parsed"]
        if v.get("verdict") not in ("OK", "DEFECT"):
            raise ValueError(f"bad verdict shape: {v}")
    except Exception as e:
        v = {"verdict": "REVIEW_ERROR", "worst_severity": "NONE",
             "defects": [], "error": str(e)[:200]}
    v["id"] = row["id"]
    with open(os.path.join(d, "fidelity_review.json"), "w") as f:
        json.dump(v, f, indent=1)
    return v


def main():
    results_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        HERE, "artifacts", "scene_acceptance", "dataset_core", "RESULTS.json")
    payload = json.load(open(results_path))
    accepted = [r for r in payload["rows"]
                if r["status"] in ("compiled", "corrected")]
    verdicts = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(review_case, r) for r in accepted]
        for fut in as_completed(futs):
            v = fut.result()
            verdicts.append(v)
            print(f"  [{len(verdicts):>3}/{len(accepted)}] "
                  f"{v['verdict']:<12} {v.get('worst_severity', ''):<8} "
                  f"{v['id']}", flush=True)
    counts = {"OK": 0, "MINOR": 0, "MAJOR": 0, "CRITICAL": 0,
              "REVIEW_ERROR": 0}
    for v in verdicts:
        if v["verdict"] == "OK":
            counts["OK"] += 1
        elif v["verdict"] == "REVIEW_ERROR":
            counts["REVIEW_ERROR"] += 1
        else:
            counts[v.get("worst_severity", "MINOR")] += 1
    out = {"reviewed": len(verdicts), "counts": counts,
           "critical": [v for v in verdicts
                        if v.get("worst_severity") == "CRITICAL"],
           "major": [v for v in verdicts
                     if v.get("worst_severity") == "MAJOR"]}
    outp = results_path.replace("RESULTS.json", "FIDELITY.json")
    with open(outp, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(counts, indent=1))
    print(f"-> {outp}")


if __name__ == "__main__":
    main()
