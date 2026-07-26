"""End-to-end compilation, and the artifacts that show exactly how a
semantic world became a runtime world.

    question + frozen evidence
      -> semantic scenario      (model call 1)
      -> independent review     (model call 2, at most one targeted revision)
      -> deterministic lowering (zero model calls)
      -> existing runtime       (unchanged)
      -> terminal from the trajectory
"""
from __future__ import annotations

import json
import os
import time as wallclock

from sworldmodel import Engine, World
from sworldmodel.artifacts import write_artifacts

from .errors import (COMPILED, CompilationStop, InsufficientEvidence,
                     InvalidReference, NoCausalProducer, SemanticAmbiguity)
from .lower import lower
from .minds import llm_minds, mechanical_minds
from .review import blocking_defects, review
from .semantic import build_scenario


def _wj(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


def _wl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, default=str) + "\n")


def compile_case(question: dict, evidence: dict, outdir: str,
                 stage: str = "mechanical", model: str = "deepseek-chat",
                 run: bool = True) -> dict:
    """Compile one case and (optionally) run it. Returns a result record whose
    'stage' is either COMPILED or the exact failure stage."""
    os.makedirs(outdir, exist_ok=True)
    metrics = {"semantic_calls": 0, "reviewer_calls": 0, "revision_calls": 0,
               "prompt_tokens": 0, "completion_tokens": 0,
               "lowering_ms": 0.0, "runtime_ms": 0.0, "stage": None,
               "simulation_stage": stage}
    _wj(os.path.join(outdir, "question.json"), question)
    _wj(os.path.join(outdir, "evidence_package.json"), evidence)

    def count(usage):
        metrics["prompt_tokens"] += usage.get("prompt_tokens", 0)
        metrics["completion_tokens"] += usage.get("completion_tokens", 0)

    try:
        # ---- 1. semantic construction --------------------------------
        try:
            scenario, raw, prompt, usage = build_scenario(question, evidence,
                                                          model=model)
        except InsufficientEvidence as miss:
            # a missing citation is a contract slip, not a claim the evidence
            # cannot support; allow the one bounded repair, then insist
            if not miss.detail.get("repairable"):
                raise
            metrics["semantic_calls"] += 1
            count(getattr(build_scenario, "last_usage", {}) or {})
            scenario, raw, prompt, usage = build_scenario(
                question, evidence, previous=None, model=model,
                revision_defects=[{"kind": "uncited_assertion",
                                   "detail": REPAIR_INSTRUCTION.format(
                                       error=miss.reason),
                                   "severity": "critical"}])
            metrics["revision_calls"] += 1
        metrics["semantic_calls"] += 1
        count(usage)
        _wj(os.path.join(outdir, "semantic_scenario.json"), scenario)
        _wj(os.path.join(outdir, "semantic_call.json"),
            {"prompt": prompt, "raw_response": raw})

        # ---- 2. independent review -----------------------------------
        result, rraw, rprompt, rusage = review(question, evidence, scenario,
                                               model=model)
        metrics["reviewer_calls"] += 1
        count(rusage)
        _wj(os.path.join(outdir, "reality_review.json"),
            {**result, "raw_response": rraw})

        blocking = blocking_defects(result)
        if result["verdict"] == "REVISE" and blocking:
            scenario2, raw2, prompt2, usage2 = build_scenario(
                question, evidence, revision_defects=blocking,
                previous=scenario, model=model)
            metrics["revision_calls"] += 1
            count(usage2)
            result2, rraw2, _, rusage2 = review(question, evidence, scenario2,
                                                model=model)
            metrics["reviewer_calls"] += 1
            count(rusage2)
            _wj(os.path.join(outdir, "revision.json"),
                {"defects_addressed": blocking, "revised_scenario": scenario2,
                 "raw_response": raw2, "second_review": result2})
            scenario = scenario2
            _wj(os.path.join(outdir, "semantic_scenario.json"), scenario)
            still = blocking_defects(result2)
            if result2["verdict"] == "REVISE" and still:
                # one targeted revision only -- never reroll repeatedly
                raise CompilationStopWithStage(
                    "REALITY_REVIEW_REJECTED",
                    "defects remain after one targeted revision; the scenario "
                    "is not a truthful account and will not be run",
                    {"remaining_defects": still})

        # ---- 3. deterministic lowering (zero model calls) -------------
        # A structural defect (a name that resolves to nothing, a parameter an
        # action never declares) is a mechanical error, not a false claim about
        # the world, so exactly ONE repair round is allowed -- with the precise
        # compiler error handed back. Substantive stops (LOWERING_GAP,
        # NO_CAUSAL_PRODUCER, NOTHING_SCHEDULED) are never repaired: those mean
        # the world cannot answer its own question.
        t0 = wallclock.monotonic()
        try:
            compiled = lower(scenario, question.get("question", ""))
        except (InvalidReference, SemanticAmbiguity, NoCausalProducer) as first:
            defect = [{"kind": "structural_reference_error",
                       "detail": REPAIR_INSTRUCTION.format(error=first.reason),
                       "severity": "critical"}]
            scenario_r, raw_r, _, usage_r = build_scenario(
                question, evidence, revision_defects=defect, previous=scenario,
                model=model)
            metrics["revision_calls"] += 1
            count(usage_r)
            _wj(os.path.join(outdir, "structural_repair.json"),
                {"first_error": first.to_dict(), "repaired_scenario": scenario_r,
                 "raw_response": raw_r})
            scenario = scenario_r
            _wj(os.path.join(outdir, "semantic_scenario.json"), scenario)
            compiled = lower(scenario, question.get("question", ""))
        metrics["lowering_ms"] = round((wallclock.monotonic() - t0) * 1000, 1)

        _wj(os.path.join(outdir, "symbol_table.json"), compiled.symbols.to_dict())
        _wl(os.path.join(outdir, "lowering_trace.jsonl"), compiled.trace)
        _wj(os.path.join(outdir, "compilation_diagnostics.json"),
            {**compiled.diagnostics, "stage": COMPILED})
        _wj(os.path.join(outdir, "runtime_world_snapshot.json"),
            compiled.world.snapshot())
        _wj(os.path.join(outdir, "terminal_producer_report.json"),
            {"terminal": compiled.terminal_spec.to_dict(),
             "producer_index": compiled.producers if hasattr(compiled, "producers")
             else compiled.diagnostics.get("producer_index", {}),
             "terminal_producers_claimed": scenario.get("terminal_producers", []),
             "reviewer_causal_path": result.get("causal_path", [])})

        metrics["stage"] = COMPILED
        record = {"stage": COMPILED, "scenario": scenario, "review": result,
                  "compiled": compiled, "metrics": metrics}

        # ---- 4. execution through the unchanged runtime ---------------
        if run:
            minds = (mechanical_minds(compiled) if stage == "mechanical"
                     else llm_minds(compiled, scenario))
            t1 = wallclock.monotonic()
            outcome = Engine(compiled.world, minds,
                             compiled.terminal_spec.to_terminal()).run()
            metrics["runtime_ms"] = round((wallclock.monotonic() - t1) * 1000, 1)
            metrics["llm_calls_runtime"] = outcome.metrics.get("llm_calls", 0)
            record["outcome"] = outcome
            write_artifacts(outdir, compiled.world, outcome,
                            _fidelity_review(question, scenario, result,
                                             compiled, outcome, stage),
                            wall_ms=metrics["runtime_ms"])
            replayed = World.from_records(compiled.world.records)
            _wj(os.path.join(outdir, "terminal_producer_report.json"),
                {"terminal": compiled.terminal_spec.to_dict(),
                 "answer": outcome.answer,
                 "computed_from": (outcome.answer or {}).get("computed_from", []),
                 "observations": (outcome.answer or {}).get("observations", []),
                 "lineage": compiled.world.lineage(
                     next((r["seq"] for r in reversed(compiled.world.records)
                           if r["op"] == "terminal"), 0)),
                 "terminal_producers_claimed": scenario.get("terminal_producers", []),
                 "reviewer_causal_path": result.get("causal_path", []),
                 "replay_hash_match":
                     replayed.state_hash() == compiled.world.state_hash()})
        _wj(os.path.join(outdir, "metrics.json"), metrics)
        return record

    except CompilationStop as e:
        metrics["stage"] = e.stage
        raw = getattr(build_scenario, "last_raw", None)
        if raw is not None:
            _wj(os.path.join(outdir, "semantic_call.json"),
                {"prompt": getattr(build_scenario, "last_prompt", {}),
                 "raw_response": raw})
        _wj(os.path.join(outdir, "compilation_diagnostics.json"), e.to_dict())
        _wj(os.path.join(outdir, "metrics.json"), metrics)
        return {"stage": e.stage, "reason": e.reason, "detail": e.detail,
                "metrics": metrics}


REPAIR_INSTRUCTION = """The world builder refused to build your scenario with this
exact error:

    {error}

Fix ONLY this defect and return the complete corrected scenario.
- If it says no participant of some name exists: ADD that party to
  "participants" (with kind, role, causal_relevance and evidence_ids). Every
  party you name anywhere -- as an information holder, a sender, a quantity
  holder, a transfer recipient -- must be declared there.
- If it says an action references a parameter it never declares: ADD that
  parameter to that action's "parameters", with "fill_from":
  "noticed_information" and the tag of the message it responds to.
- If it says a route does not exist: ADD it to "communication_routes"
  (in-person speech is a route with "seconds": 0).
- If it says a quantity was never introduced: ADD a "starting_state" entry of
  kind "quantity" for it, or a process that outputs it.
- If it says assertions cite no evidence: add "evidence_ids": ["e1", ...] to
  every participant and every starting_state entry, naming the claim ids that
  support it, or set "status": "inferred" where it is your own reasoning.
- If it says the terminal is ALREADY SATISFIED by the starting state: change
  "resolution.observations" so it observes what actually HAPPENS -- the action
  that produces the outcome ("action_was_completed") or the message actually
  received ("participant_noticed_information") -- and delete any
  "starting_state" belief written on that same topic."""


class CompilationStopWithStage(CompilationStop):
    def __init__(self, stage, reason, detail=None):
        super().__init__(reason, detail)
        self.stage = stage


def _fidelity_review(question, scenario, review_result, compiled, outcome,
                     stage) -> str:
    """An honest account of what this compiled run does and does not show."""
    ans = outcome.answer or {}
    def _text(x, *keys):
        """Sections may arrive as objects or as bare strings; render either."""
        if isinstance(x, dict):
            for k in keys:
                if x.get(k):
                    return str(x[k])
            return json.dumps(x, sort_keys=True)[:200]
        return str(x)

    excl = scenario.get("scope", {}).get("excluded", []) or []
    uncertainties = scenario.get("uncertainties", []) or []
    unnoticed = [t for t in compiled.trace
                 if t["step"] == "info_deliverable_but_unnoticed"]
    omitted = [t for t in compiled.trace if t["step"] == "attention_omitted"]

    # How much of the compiled world did the actors actually exercise? A
    # negative answer produced by a world where nobody managed to act is a
    # statement about the minds, not about the situation -- say so plainly.
    w = compiled.world
    declared = set(w.action_defs)
    completed = {a["verb"] for a in w.actions.values() if a["state"] == "completed"}
    rejected = [r["data"] for r in w.records if r["op"] == "intention.rejected"]
    never_used = sorted(declared - completed)
    idle = sorted(aid for aid in w.actors
                  if not any(a["actor"] == aid and a["state"] == "completed"
                             for a in w.actions.values()))
    artifact_risk = (ans.get("answer") in ("no", "no decision", 0, 0.0)
                     and bool(never_used))
    return f"""# Reality-fidelity review -- compiled world

**Question.** {question['question']}
**Answer produced by the trajectory.** `{ans.get('answer')}` ({outcome.status})
{ans.get('detail','')}

**How it was produced.** {len(ans.get('computed_from', []))} ledger record(s)
were cited by the terminal, each an actual state transition in this run. The
reviewer's expected causal path was:
{chr(10).join('- ' + s for s in review_result.get('causal_path', [])) or '- (none recorded)'}

## What this run does establish
- The world was built from the frozen evidence package alone, through one
  fixed semantic contract, and lowered by code that makes no model calls.
- Every duration, rate, latency and attention pattern carries a provenance
  label; the lowering layer refuses to invent any of them.
- Information was delivered on real routes with real latency, and noticed
  only where a justified attention rule existed.
- The terminal reads world state and cites the records that produced it.

## What this run does NOT establish
- **Behavioural realism.** {"Actors here are the deterministic MechanicalMind: on each wake they take the first affordance whose parameters they can fill. That proves the compiled world is executable and that the causal path reaches the terminal. It says nothing about what real people would choose." if stage == "mechanical" else "Actors are live model-backed minds; their choices are plausible but unvalidated. Nothing here calibrates them against real outcomes."}
- **Forecast accuracy.** No backtest, no calibration, no comparison to a real
  outcome has been performed.
- **Evidence quality.** The evidence package was hand-frozen; live retrieval
  is deliberately not part of this run.

## Did the actors actually exercise this world?
- Affordances declared: {len(declared)}; ever completed: {len(completed)}
- Never performed by anyone: {never_used or "none"}
- Participants who completed no action at all: {idle or "none"}
- Intentions the world rejected: {len(rejected)}
{chr(10).join("  - " + r.get("actor", "?") + ":" + r.get("verb", "?") + " -- " + str(r.get("reason", ""))[:110] for r in rejected[:8]) or "  - none"}
{"**READ THIS ANSWER WITH CARE.** The result is negative AND part of the world was never exercised, so it may reflect the limits of the mechanical policy rather than the situation itself. Re-run this compiled world at Stage 2 (live minds) before drawing any conclusion from it." if artifact_risk else "Every declared affordance was performed at least once, so the answer reflects the world rather than an actor that simply never acted."}

## Honest gaps recorded during compilation
- Information delivered but with no justified way to notice it: {len(unnoticed)}
{chr(10).join(f"  - {t['actor']} on route {t['route']} (tag {t['tag']})" for t in unnoticed) or "  - none"}
- Attention patterns the scenario left uncertain, so no rule was created: {len(omitted)}
{chr(10).join(f"  - {t['participant']} on {t['route']}: {t['reason']}" for t in omitted) or "  - none"}
- Unresolved uncertainties carried by the scenario: {len(uncertainties)}
{chr(10).join("  - " + _text(u, "description", "uncertainty") for u in uncertainties) or "  - none"}
- Deliberately excluded from the world: {len(excl)}
{chr(10).join("  - " + _text(e, "thing", "excluded") + ": " + _text(e, "reason") for e in excl) or "  - none"}
"""
