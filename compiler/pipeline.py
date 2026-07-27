"""The compile pipeline: question -> validated, reviewed, runnable world.

    question + asof + evidence
      -> resolution (exact observable answer, or structured refusal)
      -> causal discovery (small natural-language items)
      -> translation (one item at a time onto the closed menu)
      -> deterministic assembly into a genesis plan
      -> mechanical validation (backward / forward / integrity / dry run)
      -> round-trip English read back from the lowered world
      -> adversarial reality + meaning reviews
      -> WorldBundle (world records, terminal spec, minds, full trace)

One bounded repair round: blocking validation findings and review
objections are fed back into a full re-description; a second failure
produces a structured failure report.  compile_question never raises -- the
outcome is always a CompileResult that says exactly what happened.

instantiate(bundle) rebuilds (World, minds, Terminal) with ZERO LLM calls,
ready for Engine(world, minds, terminal).run().
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import traceback
from dataclasses import dataclass, field

from sworldmodel import canonical_json, iso

from . import assembly, causal_discovery, resolution, review, roundtrip, \
    translation, validation
from .llm import Caller, StageFailed, Trace
from .lowering import lower
from .provenance import EvidenceRegistry
from .world_graph import WorldGraph

BUNDLE_VERSION = 1


@dataclass
class CompileResult:
    status: str                 # compiled | refused | failed
    question: str
    bundle: dict | None = None
    report: dict = field(default_factory=dict)
    out_dir: str | None = None

    def summary(self) -> str:
        lines = [f"[{self.status}] {self.question}"]
        if self.status == "compiled":
            b = self.bundle
            lines.append(f"  terminal: {b['plan']['terminal_spec']['question']}")
            lines.append(f"  mode {b['plan']['terminal_spec']['mode']}; "
                         f"cutoff {b['plan']['cutoff']}")
            lines.append(f"  {len(b['minds'])} actors, "
                         f"{len(b['plan']['ops'])} genesis ops, "
                         f"{len(b['plan']['schedules'])} scheduled events, "
                         f"{b['llm_calls']} LLM calls, "
                         f"{len(b['repair_rounds'])} repair rounds")
            cov = b["coverage"]
            lines.append(f"  coverage: {cov['lowered']} lowered, "
                         f"{len(cov['unsupported'])} unsupported")
        else:
            for r in self.report.get("reasons", [])[:12]:
                lines.append(f"  - {r}")
        if self.out_dir:
            lines.append(f"  artifacts -> {self.out_dir}")
        return "\n".join(lines)


#: categories whose unexpressed items get surfaced in repair corrections --
#: a lost participant, route, action, or terminal breaks worlds; a dropped
#: duplicate or stray claim is normal coverage hygiene and stays out of the
#: repair diet.
_LOAD_BEARING = ("participants", "communication", "actions", "terminal")


def _load_bearing_drops(translations: list, cap: int = 6) -> list:
    out = []
    for t in translations:
        if t["status"] != "unsupported" or t["category"] not in _LOAD_BEARING:
            continue
        out.append(f"item {t['item_ref']} ({t['text'][:80]!r}) was not "
                   f"expressed: {t['result'].get('reason', '')[:160]}")
    return out[:cap]


# ---------------------------------------------------------------------------
# one full attempt (description -> reviews); repairs re-run it with
# corrections appended to every stage prompt
# ---------------------------------------------------------------------------

def _attempt(question: str, asof: str, registry: EvidenceRegistry,
             caller: Caller, trace: Trace, corrections: str,
             previous: dict | None = None) -> dict:
    previous = previous or {}
    res = resolution.resolve(question, asof, registry, caller, trace,
                             corrections, previous.get("resolution"))
    if res.get("modelable") is False:
        return {"outcome": "refused", "resolution": res,
                "reasons": [res.get("refusal_reason", "not modelable")]}
    notes: list = []
    start = assembly.to_instant(res["start_local"], res["tz"], notes,
                                "world start")
    description = causal_discovery.discover(question, asof, res, registry,
                                            caller, trace, corrections,
                                            previous.get("description"))
    graph = WorldGraph()
    translations = translation.translate_all(question, res, description,
                                             graph, caller, trace,
                                             corrections)
    evidence_map = {t["item_ref"]: t.get("evidence") or None
                    for t in translations}
    plan, errors = assembly.assemble(graph, iso(start),
                                     evidence_of=evidence_map.get)
    dropped = _load_bearing_drops(translations)
    if errors:
        # the unexpressed load-bearing items are usually WHY assembly
        # failed: put their reasons in front of the repair round, not just
        # the symptom -- but keep the diet strict, or corrections drown the
        # instructions they ride on
        return {"outcome": "repair", "resolution": res,
                "description": description, "translations": translations,
                "reasons": [f"assembly: {e}" for e in errors] + dropped}
    report = validation.validate_world(graph, plan)
    if report.patchable:
        # surgical repair first: one targeted translation per finding beats
        # re-rolling the whole world description.  This runs for blocking
        # findings AND for review-magnet findings (a participant who could
        # never act), so reviewers see the patched world.
        patch_records = translation.translate_patches(
            question, res, graph, report.patchable[:4], caller, trace,
            corrections)
        translations.extend(patch_records)
        if any(r["status"] == "lowered" for r in patch_records):
            plan2, errors2 = assembly.assemble(graph, iso(start),
                                               evidence_of=evidence_map.get)
            if not errors2:
                report2 = validation.validate_world(graph, plan2)
                better = (len(report2.blocking), len(report2.needs_review)) \
                    <= (len(report.blocking), len(report.needs_review))
                if better:
                    plan, report = plan2, report2
    if not report.ok():
        dropped = _load_bearing_drops(translations)
        return {"outcome": "repair", "resolution": res,
                "description": description, "translations": translations,
                "plan": plan, "validation": report.to_dict(),
                "reasons": [f"validation: {b}"
                            for b in report.blocking] + dropped}
    world, terminal, minds = lower(plan)
    world2, _, _ = lower(plan)
    if world.state_hash() != world2.state_hash():   # pragma: no cover
        return {"outcome": "repair", "resolution": res,
                "description": description, "translations": translations,
                "plan": plan,
                "reasons": ["lowering is not deterministic (internal error)"]}
    summary = roundtrip.summarize(world, plan["terminal_spec"], plan)
    description_text = review.render_description(res, description)
    unsupported = [f"{t['item_ref']}: {t['text']}  "
                   f"(reason: {t['result'].get('reason', '')})"
                   for t in translations if t["status"] == "unsupported"]
    reality = review.review_reality(
        question, asof, registry, summary, description_text,
        report.needs_review, unsupported,
        graph.uncertainties, graph.exclusions, caller, trace)
    meaning = review.review_meaning(description_text, summary, caller, trace)
    reasons = []
    for name, rev in (("reality", reality), ("meaning", meaning)):
        for o in rev.get("objections", []):
            if o.get("severity") == "blocking":
                reasons.append(f"{name} review: {o.get('about', '')}: "
                               f"{o['objection']} "
                               f"(fix: {o.get('fix_hint', '')})")
    for d in reality.get("dispositions", []):
        if d.get("disposition") == "must_fix":
            idx = d.get("finding")
            finding = report.needs_review[idx - 1] \
                if isinstance(idx, int) and 1 <= idx <= len(report.needs_review) \
                else str(idx)
            reasons.append(f"reality review requires a fix: {finding} -- "
                           f"{d['why']}")
    out = {"outcome": "repair" if reasons else "ok",
           "resolution": res, "description": description,
           "description_text": description_text,
           "translations": translations, "graph": graph, "plan": plan,
           "validation": report.to_dict(), "summary": summary,
           "reviews": {"reality": reality, "meaning": meaning},
           "world": world, "minds": minds, "notes": notes,
           "reasons": reasons}
    return out


def compile_question(question: str, asof: str | None = None,
                     evidence_docs: list | None = None,
                     caller: Caller | None = None,
                     out_dir: str | None = None,
                     max_repair_rounds: int = 2) -> CompileResult:
    """The public entry point.  Never raises: every outcome -- compiled,
    refused, or failed -- is a structured CompileResult with artifacts."""
    asof = asof or _dt.date.today().isoformat()
    caller = caller or Caller()
    trace = Trace()
    mode = "evidence_docs" if evidence_docs else "model_memory"
    repair_rounds: list = []
    try:
        registry = EvidenceRegistry(evidence_docs, mode)
        corrections = ""
        attempt = None
        previous = None
        challenged = False
        for round_no in range(max_repair_rounds + 1):
            attempt = _attempt(question, asof, registry, caller, trace,
                               corrections, previous)
            if attempt["outcome"] != "refused":
                previous = {"resolution": attempt.get("resolution"),
                            "description": attempt.get("description")}
            if attempt["outcome"] == "ok":
                break
            if attempt["outcome"] == "refused":
                # a refusal must survive exactly one challenge:
                # decision-dependent, "likely to", and normative questions
                # are modelable by doctrine, and a repeated refusal is final
                if challenged or round_no >= max_repair_rounds:
                    break
                challenged = True
                repair_rounds.append(attempt["reasons"])
                corrections = (
                    "You refused this question as unmodelable, saying:\n"
                    f"- {attempt['reasons'][0]}\n"
                    "Re-examine that refusal. Outcomes that depend on "
                    "people's future decisions ARE modelable (the "
                    "simulation's actor models decide; you only build the "
                    "stage and the observable finish line). 'Likely to' "
                    "questions reframe to the concrete observable event by "
                    "a deadline. Refuse again ONLY if truly nothing "
                    "observable could resolve the question even in "
                    "principle.")
                continue
            repair_rounds.append(attempt["reasons"])
            corrections = "\n".join(f"- {r}" for r in attempt["reasons"])
            corrections += (
                "\nThese corrections ADD requirements.  Everything that was "
                "already correct in the previous attempt (the cast, the "
                "channels, the routes, the schedule, the terminal) must be "
                "produced again in full -- do not shrink the world.")
        result = _finalize(question, asof, mode, evidence_docs, attempt,
                           repair_rounds, trace, out_dir)
    except StageFailed as e:
        result = CompileResult("failed", question,
                               report={"reasons": [str(e)],
                                       "repair_rounds": repair_rounds})
    except Exception as e:   # the compiler itself must never crash a caller
        result = CompileResult(
            "failed", question,
            report={"reasons": [f"internal error: {type(e).__name__}: {e}"],
                    "traceback": traceback.format_exc(),
                    "repair_rounds": repair_rounds})
    if out_dir:
        _write_artifacts(out_dir, result, trace)
        result.out_dir = out_dir
    return result


def _finalize(question, asof, mode, evidence_docs, attempt, repair_rounds,
              trace, out_dir) -> CompileResult:
    if attempt["outcome"] == "refused":
        return CompileResult("refused", question,
                             report={"reasons": attempt["reasons"],
                                     "resolution": attempt["resolution"]})
    if attempt["outcome"] == "repair":
        return CompileResult(
            "failed", question,
            report={"reasons": attempt["reasons"],
                    "repair_rounds": repair_rounds,
                    "validation": attempt.get("validation"),
                    "reviews": attempt.get("reviews")})
    graph: WorldGraph = attempt["graph"]
    translations = attempt["translations"]
    world = attempt["world"]
    bundle = {
        "bundle_version": BUNDLE_VERSION,
        "question": question, "asof": asof,
        "evidence_mode": mode, "evidence_docs": evidence_docs or [],
        "resolution": attempt["resolution"],
        "description": attempt["description"],
        "description_text": attempt["description_text"],
        "translations": [{k: v for k, v in t.items()} for t in translations],
        "coverage": {
            "lowered": sum(1 for t in translations
                           if t["status"] == "lowered"),
            "unsupported": [t["item_ref"] for t in translations
                            if t["status"] == "unsupported"]},
        "plan": attempt["plan"],
        "world_records": world.records,
        "state_hash": world.state_hash(),
        "minds": attempt["minds"],
        "validation": attempt["validation"],
        "roundtrip_summary": attempt["summary"],
        "reviews": attempt["reviews"],
        "uncertainties": graph.uncertainties,
        "exclusions": graph.exclusions,
        "notes": attempt["plan"]["notes"] + attempt["notes"],
        "repair_rounds": repair_rounds,
        "llm_calls": trace.calls,
        "status": "compiled",
    }
    return CompileResult("compiled", question, bundle=bundle)


def instantiate(bundle: dict):
    """Bundle -> (World, minds, Terminal), zero LLM calls.  The returned
    triple plugs straight into Engine(world, minds, terminal).run()."""
    from sworldmodel.llm_mind import DeepseekMind
    world, terminal, _ = lower(bundle["plan"])
    minds = {aid: DeepseekMind(aid, info["name"], info["persona_brief"])
             for aid, info in bundle["minds"].items()}
    return world, minds, terminal


# ---------------------------------------------------------------------------
# artifacts
# ---------------------------------------------------------------------------

def _write_artifacts(out_dir: str, result: CompileResult, trace: Trace) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "trace.jsonl"), "w", encoding="utf-8") as f:
        for e in trace.entries:
            f.write(canonical_json(e) + "\n")
    if result.status == "compiled":
        b = result.bundle
        with open(os.path.join(out_dir, "bundle.json"), "w",
                  encoding="utf-8") as f:
            f.write(json.dumps(b, indent=1, sort_keys=True))
        with open(os.path.join(out_dir, "roundtrip.md"), "w",
                  encoding="utf-8") as f:
            f.write(f"# Runtime reconstruction\n\n```\n"
                    f"{b['roundtrip_summary']}\n```\n")
        with open(os.path.join(out_dir, "description.md"), "w",
                  encoding="utf-8") as f:
            f.write(f"# Approved world description\n\n```\n"
                    f"{b['description_text']}\n```\n")
        with open(os.path.join(out_dir, "genesis_ledger.jsonl"), "w",
                  encoding="utf-8") as f:
            for rec in b["world_records"]:
                f.write(canonical_json(rec) + "\n")
    with open(os.path.join(out_dir, "report.json"), "w",
              encoding="utf-8") as f:
        payload = {"status": result.status, "question": result.question,
                   "report": result.report}
        if result.status == "compiled":
            payload["report"] = {
                "validation": result.bundle["validation"],
                "reviews": result.bundle["reviews"],
                "coverage": result.bundle["coverage"],
                "repair_rounds": result.bundle["repair_rounds"],
                "llm_calls": result.bundle["llm_calls"]}
        f.write(json.dumps(payload, indent=1, sort_keys=True, default=str))
