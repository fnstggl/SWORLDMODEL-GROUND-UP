"""Generate ACCEPTANCE_REPORT.md from stored acceptance artifacts.

Everything quoted is verbatim from the per-case artifact files (exact
inputs, exact prompts, exact raw responses, exact manifests, bindings,
genesis checks, metrics) -- selection and headings are the only authored
content.  Example picks: three clean first-pass, three corrected, two
honest abstentions, one historical-leakage challenge, one hostile/unseen.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "artifacts", "minimal_scene_compiler",
                   "ACCEPTANCE_REPORT.md")
F = "~~~~~~~~"


def read(case_dir, name, limit=None):
    p = os.path.join(case_dir, name)
    if not os.path.exists(p):
        return f"(artifact {name} absent)"
    with open(p, encoding="utf-8") as f:
        t = f.read()
    return t if limit is None or len(t) <= limit else \
        t[:limit] + f"\n... [{len(t) - limit} more chars in {name}]"


def example_block(w, row, title):
    d = row["out_dir"]
    w(f"\n\n## {title}: `{row['id']}` — status **{row['status']}**\n")
    w(f"\n### exact input\n{F}\n{read(d, 'input.json')}\n{F}\n")
    w(f"\n### exact Call 1 prompt\n{F}\n"
      f"{read(d, 'call_1_prompt.txt')}\n{F}\n")
    w(f"\n### exact Call 1 output\n{F}\n"
      f"{read(d, 'call_1_raw_response.txt')}\n{F}\n")
    w(f"\n### exact Call 2 prompt (frame + manifest under review)\n{F}\n"
      f"{read(d, 'call_2_prompt.txt')}\n{F}\n")
    w(f"\n### exact Call 2 output\n{F}\n"
      f"{read(d, 'call_2_raw_response.txt')}\n{F}\n")
    if os.path.exists(os.path.join(d, "call_3_raw_response.txt")):
        w(f"\n### exact Call 3 output (targeted correction)\n{F}\n"
          f"{read(d, 'call_3_raw_response.txt')}\n{F}\n")
    w(f"\n### final four-field manifest (normalized)\n{F}\n"
      f"{read(d, 'final_scene_manifest.json')}\n{F}\n")
    for name, label in (("runtime_bindings.json",
                         "normalized runtime IDs and bindings"),
                        ("actor_initial_views.json",
                         "initialized actor states"),
                        ("starting_event_ledger.jsonl",
                         "inserted starting events (genesis ledger)"),
                        ("genesis_resolution_check.json",
                         "genesis resolution result"),
                        ("compiler_metrics.json", "compiler metrics")):
        w(f"\n### {label}\n{F}\n{read(d, name, limit=6000)}\n{F}\n")


def pick(rows, status, n, pred=lambda r: True):
    out = [r for r in rows if r["status"] == status and pred(r)][:n]
    return out


def main(results_paths):
    all_rows, summaries = [], []
    for p in results_paths:
        payload = json.load(open(p))
        all_rows.extend(payload["rows"])
        summaries.append((payload["dataset"], payload["summary"]))
    lines = []
    w = lines.append
    w("# minimal_scene_v1 — acceptance report\n")
    w("\nMODEL-MEMORY MODE TESTS COMPILER ROBUSTNESS AND SEMANTIC WORLD "
      "SHAPE.\nIT DOES NOT VERIFY CURRENT REAL-WORLD FACTS.\n")
    for ds, s in summaries:
        w(f"\n## Summary — {ds}\n{F}\n{json.dumps(s, indent=1)}\n{F}\n")
    ex = []
    ex += [("clean first-pass", r) for r in pick(all_rows, "compiled", 3)]
    ex += [("corrected", r) for r in pick(all_rows, "corrected", 3)]
    ex += [("honest abstention", r) for r in pick(all_rows, "abstained", 2)]
    hist = pick(all_rows, "compiled", 1, lambda r: r.get("historical")) \
        or pick(all_rows, "corrected", 1, lambda r: r.get("historical")) \
        or pick(all_rows, "abstained", 1, lambda r: r.get("historical"))
    ex += [("historical leakage challenge", r) for r in hist]
    unseen = [r for r in all_rows if "unseen" in r.get("out_dir", "")]
    if unseen:
        ex += [("hostile unseen", unseen[0])]
    for title, row in ex:
        example_block(w, row, title)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("".join(l if l.endswith("\n") else l + "\n" for l in lines))
    print(f"report -> {OUT} ({len(ex)} examples, {len(all_rows)} cases)")


if __name__ == "__main__":
    main(sys.argv[1:] or
         [os.path.join(HERE, "artifacts", "scene_acceptance",
                       "dataset_core", "RESULTS.json")])
