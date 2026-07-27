"""The default compilation pipeline.

    question (+ frozen evidence, or Mode B memory draft)
      -> five small discovery calls          (compiler/discovery.py)
      -> deterministic assembly              (compiler/assemble.py, code)
      -> backward causal proof               (compiler/proofs.py, code)
      -> forward executability proof         (compiler/proofs.py, code)
      -> item-at-a-time binding              (compiler/binding.py)
      -> deterministic emission              (compiler/emit.py, code)
      -> contract validation + lowering      (existing schema.py/lower.py)
      -> existing runtime, scripted minds
      -> terminal from the trajectory

The one-shot whole-scenario authoring path (compiler/pipeline.py) is no
longer the default; the eleven-section scenario still exists, but as a
code-generated artifact. The model discovers the causal world; code
assembles, connects and executes its representation.

Honesty rules carried from the audit:

* The output directory is cleared at the start of each run, so a case
  directory can never assert two contradictory outcomes at once.
* Model time is billed to the model, never to "lowering".
* An answer of "no" from a world whose affordances were never exercised
  is flagged in the fidelity review AND in the result record.
"""
from __future__ import annotations

import json
import os
import shutil
import time as wallclock

from sworldmodel import Engine, World
from sworldmodel.artifacts import write_artifacts

from . import schema
from .assemble import assemble
from .binding import bind_world
from .discovery import discover
from .emit import emit_scenario
from .errors import (COMPILED, CompilationStop, LoweringMismatch,
                     RealityReviewRejected)
from .llm import call_json
from .lower import lower
from .memory_evidence import draft_memory_evidence
from .minds import llm_minds
from .proofs import backward_causal_proof, forward_executability_proof


def _wj(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


def _wl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, default=str) + "\n")


def compile_question(question: dict, evidence: dict | None, outdir: str,
                     stage: str = "scripted", model: str = "deepseek-chat",
                     run: bool = True, scripts: dict | None = None,
                     call=call_json, reuse: bool = False,
                     review_model: str = "deepseek-reasoner") -> dict:
    """Compile one question end to end. ``evidence=None`` selects Mode B
    (question-only: a model-memory draft, every claim marked
    model_memory_unverified). ``reuse=True`` re-lowers the frozen
    approved_scenario.json with zero model calls, so scripted-mind and
    live-mind runs compare the identical world. Returns a record whose
    'stage' is COMPILED or the exact failure stage; never raises a
    CompilationStop."""
    if reuse:
        return _reuse_frozen(question, outdir, stage, run, scripts)
    if os.path.isdir(outdir):
        shutil.rmtree(outdir)
    os.makedirs(outdir)
    t_wall = wallclock.monotonic()
    calls: list = []                 # non-discovery, non-binding logs
    from .discovery import Discovery
    from .binding import Bindings
    disc = Discovery()
    bindings = Bindings()

    def all_calls():
        return calls + disc.calls + bindings.calls
    metrics = {
        "mode": "question_only" if evidence is None else "frozen_evidence",
        "discovery_calls": 0, "binding_calls": 0, "model_tokens": 0,
        "repairs_by_step": {}, "first_pass_by_step": {},
        "assembly_ms": 0.0, "proofs_ms": 0.0, "emit_ms": 0.0,
        "lowering_ms": 0.0, "runtime_ms": 0.0, "model_ms": 0.0,
        "stage": None, "simulation_stage": stage,
    }
    _wj(os.path.join(outdir, "question.json"), question)
    _wj(os.path.join(outdir, "run_manifest.json"),
        {"pipeline": "worldcompiler", "model": model,
         "mode": metrics["mode"]})

    def finish_failure(exc: CompilationStop) -> dict:
        metrics["stage"] = exc.stage
        _wj(os.path.join(outdir, "compilation_diagnostics.json"),
            exc.to_dict())
        metrics["discovery_calls"] = len(disc.calls)
        metrics["binding_calls"] = len(bindings.calls)
        metrics["repairs_by_step"].update(disc.repairs)
        metrics["repairs_by_step"].update(bindings.repairs)
        metrics["model_tokens"] = disc.tokens + bindings.tokens
        _wl(os.path.join(outdir, "model_calls.jsonl"), all_calls())
        _wj(os.path.join(outdir, "metrics.json"), metrics)
        return {"stage": exc.stage, "reason": exc.reason,
                "detail": exc.detail, "metrics": metrics}

    # ---- Mode B: draft evidence from model memory --------------------
    try:
        if evidence is None:
            t0 = wallclock.monotonic()
            evidence, log = draft_memory_evidence(question, call, model)
            metrics["model_ms"] += (wallclock.monotonic() - t0) * 1000
            calls.extend(log)
    except CompilationStop as exc:
        _wj(os.path.join(outdir, "evidence_package.json"),
            {"claims": [], "mode": "question_only"})
        return finish_failure(exc)
    _wj(os.path.join(outdir, "evidence_package.json"), evidence)

    # ---- discovery ---------------------------------------------------
    t0 = wallclock.monotonic()
    try:
        discover(question, evidence, call=call, model=model,
                 allow_memory=(metrics["mode"] == "question_only"),
                 into=disc)
        stop = None
    except CompilationStop as exc:
        stop = exc
    metrics["model_ms"] += (wallclock.monotonic() - t0) * 1000
    metrics["discovery_calls"] = len(disc.calls)
    metrics["repairs_by_step"].update(disc.repairs)
    for name, doc in (("resolution_contract", disc.resolution),
                      ("causal_spine", disc.spine),
                      ("producer_assignments", disc.producers),
                      ("starting_state_and_information", disc.state_info),
                      ("uncertainty_and_exclusions", disc.uncertainty)):
        if doc is not None:
            _wj(os.path.join(outdir, f"{name}.json"), doc)
    state_repaired = any(k.startswith("starting_state[")
                         for k in disc.repairs)
    for name in ("resolution_contract", "causal_spine",
                 "producer_assignments", "starting_state_and_information",
                 "uncertainty_and_exclusions"):
        repaired = name in disc.repairs or (
            name == "starting_state_and_information" and state_repaired)
        metrics["first_pass_by_step"][name] = not repaired
    if stop is not None:
        return finish_failure(stop)

    # ---- deterministic assembly + proofs -----------------------------
    # An assembly defect names the discovery document that owns it; that
    # document gets at most ONE targeted repair before the case stops.
    from .discovery import evidence_ids, repair_document
    repaired_docs: set = set()
    metrics["assembly_repairs"] = []
    while True:
        try:
            t0 = wallclock.monotonic()
            graph, trace = assemble(
                disc.resolution, disc.spine, disc.producers,
                disc.state_info, disc.uncertainty,
                valid_evidence_ids=evidence_ids(evidence))
            metrics["assembly_ms"] = round(
                (wallclock.monotonic() - t0) * 1000, 1)
            _wj(os.path.join(outdir, "canonical_world_graph.json"),
                graph.to_dict())
            _wl(os.path.join(outdir, "assembly_trace.jsonl"), trace)

            t0 = wallclock.monotonic()
            backward = backward_causal_proof(graph)
            _wj(os.path.join(outdir, "backward_causal_proof.json"),
                backward)
            forward = forward_executability_proof(graph)
            _wj(os.path.join(outdir, "forward_executability_proof.json"),
                forward)
            metrics["proofs_ms"] = round(
                (wallclock.monotonic() - t0) * 1000, 1)

            # ---- binding BEFORE the review: the reviewer must see the
            # fully wired world (rates, amounts, stock connections), not
            # a pre-binding skeleton it would misjudge as decorative ----
            from .binding import connect_process_outputs
            t0 = wallclock.monotonic()
            bind_world(graph, evidence, call=call, model=model,
                       into=bindings)
            connect_process_outputs(graph, bindings)
            metrics["model_ms"] += (wallclock.monotonic() - t0) * 1000
            _wj(os.path.join(outdir, "canonical_world_graph.json"),
                graph.to_dict())

            # ---- independent causal-reality review -------------------
            from .reality import raise_for, review_reality
            t0 = wallclock.monotonic()
            review, rlog = review_reality(question, evidence, graph,
                                          backward, forward, call=call,
                                          model=review_model,
                                          bindings=bindings)
            metrics["model_ms"] += (wallclock.monotonic() - t0) * 1000
            calls.extend(rlog)
            metrics["reviewer_calls"] = \
                metrics.get("reviewer_calls", 0) + 1
            _wj(os.path.join(outdir, "reality_review.json"), review)
            raise_for(review)
            break
        except CompilationStop as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            if not detail.get("repairable"):
                return finish_failure(exc)
            review = detail.get("review")
            if review:
                # ONE targeted revision round total: every tagged document
                # is revised at once, and the SECOND review's verdict is
                # final. Per-round fresh reviews inventing new objections
                # is exactly the oscillation the audit condemned.
                if metrics.get("review_revision_round"):
                    return finish_failure(RealityReviewRejected(
                        "defects remain after one targeted revision; the "
                        "world is not a truthful account and will not be "
                        "run", {"review": review}))
                metrics["review_revision_round"] = 1
                docs = sorted({d["document"] for d in review["defects"]})
                t0 = wallclock.monotonic()
                try:
                    for doc_name in docs:
                        repair_document(
                            disc, doc_name,
                            [f"{d['what']} -- {d['why_material']}"
                             for d in review["defects"]
                             if d["document"] == doc_name],
                            call=call, model=model)
                except CompilationStop as exc2:
                    metrics["model_ms"] += \
                        (wallclock.monotonic() - t0) * 1000
                    return finish_failure(exc2)
                metrics["model_ms"] += (wallclock.monotonic() - t0) * 1000
                metrics["assembly_repairs"].extend(
                    f"review:{d}" for d in docs)
                continue
            doc_name = detail.get("document")
            if doc_name is None and exc.stage in (
                    "NO_CAUSAL_PRODUCER", "INVALID_REFERENCE"):
                # a proof failure is usually a missing or wrong producer:
                # route its one repair to the producer assignments
                doc_name = "producer_assignments"
            if not doc_name or doc_name in repaired_docs:
                return finish_failure(exc)
            repaired_docs.add(doc_name)
            t0 = wallclock.monotonic()
            try:
                if not repair_document(disc, doc_name,
                                       exc.detail.get("defects", []),
                                       call=call, model=model):
                    return finish_failure(exc)
            except CompilationStop as exc2:
                metrics["model_ms"] += (wallclock.monotonic() - t0) * 1000
                return finish_failure(exc2)
            metrics["model_ms"] += (wallclock.monotonic() - t0) * 1000
            metrics["assembly_repairs"].append(doc_name)
            for name, doc in (
                    ("resolution_contract", disc.resolution),
                    ("causal_spine", disc.spine),
                    ("producer_assignments", disc.producers),
                    ("starting_state_and_information", disc.state_info),
                    ("uncertainty_and_exclusions", disc.uncertainty)):
                _wj(os.path.join(outdir, f"{name}.json"), doc)

    metrics["binding_calls"] = len(bindings.calls)
    metrics["repairs_by_step"].update(bindings.repairs)

    # ---- deterministic emission + existing validation + lowering -----
    try:
        t0 = wallclock.monotonic()
        scenario = emit_scenario(graph, bindings, question)
        metrics["emit_ms"] = round((wallclock.monotonic() - t0) * 1000, 1)
        _wj(os.path.join(outdir, "generated_semantic_scenario.json"),
            scenario)
        try:
            schema.validate(scenario)
            schema.check_provenance(scenario, evidence)
        except CompilationStop as exc:
            raise LoweringMismatch(
                "the code-generated scenario failed its own contract; this "
                "is a compiler defect, not a model error: " + exc.reason,
                {"inner": exc.to_dict()})
        t0 = wallclock.monotonic()
        compiled = lower(scenario, question.get("question", ""))
        metrics["lowering_ms"] = round(
            (wallclock.monotonic() - t0) * 1000, 1)

        # ---- semantic round-trip: the lowered world must mean what the
        # approved world means, or it does not run ----------------------
        from .roundtrip import (describe_graph, describe_runtime,
                                review_equivalence)
        graph_md = describe_graph(graph, question, bindings)
        runtime_md = describe_runtime(compiled)
        with open(os.path.join(outdir, "runtime_round_trip.md"), "w",
                  encoding="utf-8") as f:
            f.write(runtime_md)
        t0 = wallclock.monotonic()
        equivalence, elog = review_equivalence(graph_md, runtime_md,
                                               call=call,
                                               model=review_model)
        metrics["model_ms"] += (wallclock.monotonic() - t0) * 1000
        calls.extend(elog)
        _wj(os.path.join(outdir, "semantic_equivalence_review.json"),
            equivalence)

        # ---- automatic causal red team ---------------------------------
        from .challenge import challenge_world
        challenges = challenge_world(graph)
        _wj(os.path.join(outdir, "causal_challenge_report.json"),
            challenges)
        if challenges["failed"]:
            raise LoweringMismatch(
                "causal challenge tests failed; the compiled world must "
                "not run", {"failed": challenges["failed"]})
    except CompilationStop as exc:
        return finish_failure(exc)

    _wj(os.path.join(outdir, "approved_scenario.json"), scenario)
    _wj(os.path.join(outdir, "symbol_table.json"),
        compiled.symbols.to_dict())
    _wl(os.path.join(outdir, "lowering_trace.jsonl"), compiled.trace)
    _wj(os.path.join(outdir, "runtime_world_snapshot.json"),
        compiled.world.snapshot())

    metrics["stage"] = COMPILED
    record = {"stage": COMPILED, "scenario": scenario, "graph": graph,
              "compiled": compiled, "metrics": metrics,
              "backward_proof": backward, "forward_proof": forward}

    # ---- execution through the unchanged runtime ---------------------
    if run:
        if stage == "llm":
            minds = llm_minds(compiled, scenario)
        else:
            from tests.scripted_minds import scripted_minds
            try:
                minds = scripted_minds(compiled, scripts or {})
            except ValueError as exc:
                # a drifted script is a harness misconfiguration; run with
                # nobody acting and say so everywhere, never silently no-op
                record_mismatch = str(exc)
                metrics["script_mismatch"] = record_mismatch
                minds = scripted_minds(compiled, {})
        t0 = wallclock.monotonic()
        outcome = Engine(compiled.world, minds,
                         compiled.terminal_spec.to_terminal()).run()
        metrics["runtime_ms"] = round(
            (wallclock.monotonic() - t0) * 1000, 1)
        record["outcome"] = outcome
        never_used = sorted(
            set(compiled.world.action_defs)
            - {a["verb"] for a in compiled.world.actions.values()
               if a["state"] == "completed"})
        ans = outcome.answer or {}
        record["artifact_risk"] = bool(
            ans.get("answer") in ("no", 0, 0.0) and never_used)
        if metrics.get("script_mismatch"):
            record["script_mismatch"] = metrics["script_mismatch"]
            record["artifact_risk"] = True
        write_artifacts(outdir, compiled.world, outcome,
                        _fidelity(question, graph, compiled, outcome,
                                  stage, never_used, metrics),
                        wall_ms=metrics["runtime_ms"])
        replayed = World.from_records(compiled.world.records)
        replay_ok = replayed.state_hash() == compiled.world.state_hash()
        _wj(os.path.join(outdir, "terminal_producer_report.json"), {
            "terminal": compiled.terminal_spec.to_dict(),
            "answer": ans,
            "computed_from": ans.get("computed_from", []),
            "graph_producer_lineage": {
                c["component"]: c["producers"]
                for c in backward["components"]},
            "replay_hash_match": replay_ok})
        challenges["exact_replay"] = bool(replay_ok)
        _wj(os.path.join(outdir, "causal_challenge_report.json"),
            challenges)
        if not replay_ok:
            record["replay_mismatch"] = True
            record["artifact_risk"] = True

    metrics["wall_ms"] = round((wallclock.monotonic() - t_wall) * 1000, 1)
    metrics["model_tokens"] = disc.tokens + bindings.tokens
    _wl(os.path.join(outdir, "model_calls.jsonl"), all_calls())
    _wj(os.path.join(outdir, "metrics.json"), metrics)
    return record


def _reuse_frozen(question, outdir, stage, run, scripts) -> dict:
    """Re-lower and re-run the frozen approved scenario. Zero model calls;
    nothing is wiped; the graph and discovery artifacts stay as compiled."""
    path = os.path.join(outdir, "approved_scenario.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path}: no frozen world to reuse; compile the case first")
    with open(path, encoding="utf-8") as f:
        scenario = json.load(f)
    metrics = {"mode": "reuse_frozen", "stage": None,
               "simulation_stage": stage, "lowering_ms": 0.0,
               "runtime_ms": 0.0}
    t0 = wallclock.monotonic()
    compiled = lower(scenario, question.get("question", ""))
    metrics["lowering_ms"] = round((wallclock.monotonic() - t0) * 1000, 1)
    metrics["stage"] = COMPILED
    record = {"stage": COMPILED, "scenario": scenario, "compiled": compiled,
              "metrics": metrics}
    if run:
        minds = (llm_minds(compiled, scenario) if stage == "llm"
                 else __import__("tests.scripted_minds",
                                 fromlist=["scripted_minds"])
                 .scripted_minds(compiled, scripts or {}))
        t0 = wallclock.monotonic()
        outcome = Engine(compiled.world, minds,
                         compiled.terminal_spec.to_terminal()).run()
        metrics["runtime_ms"] = round(
            (wallclock.monotonic() - t0) * 1000, 1)
        record["outcome"] = outcome
        never_used = sorted(
            set(compiled.world.action_defs)
            - {a["verb"] for a in compiled.world.actions.values()
               if a["state"] == "completed"})
        ans = outcome.answer or {}
        record["artifact_risk"] = bool(
            ans.get("answer") in ("no", 0, 0.0) and never_used)
        rundir = os.path.join(outdir, f"reuse_{stage}")
        os.makedirs(rundir, exist_ok=True)
        write_artifacts(rundir, compiled.world, outcome,
                        f"# Reuse run ({stage} minds) of the frozen world\n"
                        f"\nSame approved scenario, re-lowered with zero "
                        f"model calls.\n", wall_ms=metrics["runtime_ms"])
        replayed = World.from_records(compiled.world.records)
        _wj(os.path.join(rundir, "terminal_producer_report.json"), {
            "terminal": compiled.terminal_spec.to_dict(),
            "answer": ans, "computed_from": ans.get("computed_from", []),
            "replay_hash_match":
                replayed.state_hash() == compiled.world.state_hash()})
        _wj(os.path.join(rundir, "metrics.json"), metrics)
    return record


def _fidelity(question, graph, compiled, outcome, stage, never_used,
              metrics) -> str:
    ans = outcome.answer or {}
    idle = sorted(aid for aid in compiled.world.actors
                  if not any(a["actor"] == aid and a["state"] == "completed"
                             for a in compiled.world.actions.values()))
    risk = ans.get("answer") in ("no", 0, 0.0) and bool(never_used)
    minds_note = (
        "Actors are live model-backed minds; their choices are plausible "
        "but unvalidated." if stage == "llm" else
        "Actors follow fixture-authored scripts (or none). A run driven "
        "by scripts proves the compiled world executes; it is NEVER a "
        "forecast of behaviour.")
    return f"""# Reality-fidelity review -- discovery-compiled world

**Question.** {question.get('question', '')}
**Answer produced by the trajectory.** `{ans.get('answer')}` ({outcome.status})
{ans.get('detail', '')}

## How this world was built
- Five small discovery calls described the possible world; code assembled
  the canonical graph ({len(graph.nodes)} nodes, {len(graph.edges)} edges),
  proved backward producer chains and forward executability, bound each
  semantic item to a universal capability, and emitted the runtime world
  deterministically. Repairs used: {metrics['repairs_by_step'] or 'none'}.
- No step wrote the future: scheduled events carry evidenced times only,
  and every actor decision is an affordance the actor may or may not take.

## What this run does NOT establish
- {minds_note}
- No backtest, calibration or comparison with a real outcome exists here.

## Did the trajectory exercise the world?
- Affordances never performed: {never_used or 'none'}
- Participants who completed no action: {idle or 'none'}
{"**READ THIS ANSWER WITH CARE.** The result is negative AND part of the world was never exercised: it reflects the limits of the driving minds, not the situation." if risk else ""}

## Known mechanical limits stated plainly
- Scheduled transfers execute unconditionally; their feasibility (source
  stock sufficiency) was verified at compile time by the proofs and the
  reality review, and the kernel itself does not clamp an overdraw. A
  world whose schedule outruns its stocks must be caught at review, and
  this one was checked there.

## Unresolved uncertainty carried honestly
{chr(10).join('- ' + u['meaning'] + ' (about: ' + (u.get('about') or u.get('topic') or 'the world') + ')' for u in graph.uncertainties) or '- none declared'}
"""
