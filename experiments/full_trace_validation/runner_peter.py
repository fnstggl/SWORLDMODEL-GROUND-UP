"""Driver for the two Peter Thiel transparency experiments.

Experiment-only.  Every phase runs the REAL production path against the
live model; the harness only records, freezes, and writes artifacts.

Phases (each is its own monitored job so a provider stall cannot take the
whole experiment down)::

    --phase compile     real compiler, live -> peter_supplied/compiler/
    --phase supplied    scenario 1: the user's three emails
    --phase generated   scenario 2: candidates generated live, SAME world
    --phase validate    instrumentation cross-check + README

Scenario 2 never recompiles.  It re-adapts the SAME frozen compiler
artifact directory (the adapter is pure deterministic code) and asserts
that the resulting world content hash and base plan content hash are
byte-identical to scenario 1's recorded hashes.  A mismatch fails the
phase loudly.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import (HARNESS_VERSION,  # noqa: E402
                                               RUN_LABEL)
from experiments.full_trace_validation import evidence as evidence_lib
from experiments.full_trace_validation import freeze as freeze_lib
from experiments.full_trace_validation import ledgers as ledger_lib
from experiments.full_trace_validation import predicates as predicate_lib
from experiments.full_trace_validation import recorder as recorder_lib
from experiments.full_trace_validation import scenario_peter as scenario

ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
SUPPLIED_DIR = ARTIFACT_ROOT / "peter_supplied"
GENERATED_DIR = ARTIFACT_ROOT / "peter_generated"
SHARED_DIR = ARTIFACT_ROOT / "shared"
COMPILER_DIR = SUPPLIED_DIR / "compiler"
RUN_IDENTITY_PATH = SHARED_DIR / "run_identity.json"

#: the freeze entries scenario 2 must reproduce byte-for-byte.  The
#: decision problem, the candidate set, the branch seeds and the
#: generation cap legitimately differ (that IS the scenario delta); the
#: evidence and the engine limits are compared by their content-only
#: entries, since the full manifest carries a per-scenario identifier.
REUSED_ENTRIES = ("compiler_artifact_dir_aggregate",
                  "compiled_decision_world",
                  "concordia_initialization_plan",
                  "concordia_initialization_plan_content_hash",
                  "evaluator_spec", "compiler_inputs", "time_window",
                  "evidence_items", "engine_simulation_limits")


def _now() -> str:
    return datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _progress(path, message: str) -> None:
    stamped = f"[{_now()}] {message}"
    print(stamped, flush=True)
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(stamped + "\n")


def _write_json(path, payload) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False)
                    + "\n", encoding="utf-8")


def _api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit(
            "DEEPSEEK_API_KEY is not set: this experiment only runs "
            "against the live provider and never fabricates output")
    return key


def _model_configuration() -> dict:
    return {
        "provider": recorder_lib.PROVIDER,
        "base_url": recorder_lib.DEEPSEEK_BASE_URL,
        "model": recorder_lib.DEEPSEEK_MODEL_ID,
        "roles": {
            "compiler": {
                "transport": "compiler.scene_llm.SceneCaller(transport=)",
                "temperature": 0.0, "max_tokens": 8000,
                "response_format": "json_object",
                "semantic_call_budget": 3},
            "candidate_generator": {
                "seam": "decision_route.prepare_decision_inputs("
                        "generator_model=)",
                "temperature": 0.0, "max_tokens": 2000,
                "response_format": "json_object",
                "calls_per_generation": 1},
            "actor": {
                "seam": "counterfactuals.manager.run_candidates_detailed("
                        "model_factory=)",
                "temperature": 0.0, "max_tokens": 400,
                "response_format": None},
            "game_master": {
                "seam": "counterfactuals.manager.run_candidates_detailed("
                        "model_factory=)",
                "temperature": 0.0, "max_tokens": 400,
                "response_format": None},
        },
        "retry_policy": {
            "max_attempts_per_call": recorder_lib.MAX_ATTEMPTS,
            "backoff_seconds": list(recorder_lib.BACKOFF_SECONDS),
            "every_attempt_recorded": True},
        "sampling_note": ("temperature 0 is a bounded policy, not a "
                          "determinism claim: the provider does not "
                          "guarantee reproducible completions"),
    }


def _environment() -> dict:
    import subprocess
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True,
                             check=False).stdout.strip()
    except Exception:  # noqa: BLE001
        sha = ""
    return {
        "label": RUN_LABEL,
        "harness_version": HARNESS_VERSION,
        "repository_sha": sha,
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "recorded_at": _now(),
    }


# ---------------------------------------------------------------------------
# phase: compile
# ---------------------------------------------------------------------------


def phase_compile(progress) -> int:
    from compiler.scene_llm import SceneCaller
    from compiler.scene_pipeline import COMPILER_VERSION, compile_scene

    api_key = _api_key()
    del api_key  # the compiler transport reads the key itself
    started = datetime.datetime.now(datetime.timezone.utc)
    start_iso, cutoff_iso = scenario.resolve_window(started)
    _progress(progress, f"compile: window {start_iso} -> {cutoff_iso}")

    problem_payload = scenario.build_problem_payload(
        start_iso=start_iso, cutoff_iso=cutoff_iso, generated=False)
    items = scenario.evidence_items(problem_payload)
    manifest = evidence_lib.build_manifest(
        experiment_id=scenario.SUPPLIED_EXPERIMENT_ID,
        window_start=start_iso, window_cutoff=cutoff_iso, items=items,
        actor_names=(),
        notes=("Written before compilation. The compiled cast is not yet "
               "known, so actor references are validated again after "
               "adaptation."))
    question = scenario.compiler_question(problem_payload)
    context = scenario.compiler_context(problem_payload)
    package = scenario.render_evidence_package(manifest)

    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    COMPILER_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(SHARED_DIR / "environment.json", _environment())
    _write_json(SHARED_DIR / "model_configuration.json",
                _model_configuration())

    ledger = recorder_lib.CallLedger(
        "peter_compile", COMPILER_DIR / "llm_calls.jsonl")
    context_obj = recorder_lib.RecorderContext(
        experiment_id="peter_compile", ledger=ledger,
        boundary=recorder_lib.NetworkBoundary())
    transport = recorder_lib.RecordingSceneTransport(context_obj)
    caller = SceneCaller(model=recorder_lib.DEEPSEEK_MODEL_ID,
                         transport=transport)

    _progress(progress, "compile: stage 1/1 calling the real compiler "
                        "(up to 3 semantic calls)")
    wall_started = time.perf_counter()
    result = compile_scene(question, start_iso, cutoff_iso,
                           context=context, evidence=package, caller=caller,
                           out_dir=str(COMPILER_DIR))
    wall = round(time.perf_counter() - wall_started, 2)
    _progress(progress, f"compile: status={result.status} wall={wall}s "
                        f"slots={caller.semantic_slots}")

    _write_json(SHARED_DIR / "instrumentation_compile.json",
                context_obj.instrumentation())
    identity = {
        "label": RUN_LABEL,
        "run_start_utc": start_iso,
        "cutoff_utc": cutoff_iso,
        "compiler_version": COMPILER_VERSION,
        "compiler_status": result.status,
        "compiler_reason": result.reason,
        "compiler_out_dir": str(COMPILER_DIR.relative_to(REPO_ROOT)),
        "question": question,
        "context": context,
        "evidence_package": package,
        "compiler_metrics": result.metrics,
        "wall_seconds": wall,
        "evidence_manifest": manifest,
        "decision_problem_payload_supplied": problem_payload,
    }
    _write_json(RUN_IDENTITY_PATH, identity)
    _progress(progress, f"compile: wrote {RUN_IDENTITY_PATH}")
    if result.status not in ("compiled", "corrected"):
        _progress(progress,
                  f"compile FAILED: {result.status}: {result.reason}")
        return 2
    _progress(progress, "compile: actors = "
              + ", ".join(actor["name"]
                          for actor in result.manifest["actors"]))
    return 0


# ---------------------------------------------------------------------------
# shared scenario machinery
# ---------------------------------------------------------------------------


def _cited_texts(event_trace, citations) -> list:
    """Resolve a metric's citations to the exact committed text.

    The contract normalises trace indices into ``event:<event_id>``
    references, so both forms must be resolved; a ``state:`` citation
    names terminal state, not an event, and resolves to nothing.
    """
    events = list(event_trace)
    by_id = {event.event_id: event.description for event in events}
    texts = []
    for citation in citations:
        if isinstance(citation, int):
            if 0 <= citation < len(events):
                texts.append(events[citation].description)
            continue
        if isinstance(citation, str) and citation.startswith("event:"):
            description = by_id.get(citation.split(":", 1)[1])
            if description is not None:
                texts.append(description)
    return texts


def _adapt_world():
    from sworldmodel.compilation.existing_compiler_adapter import (
        adapt_compiled_artifacts)

    return adapt_compiled_artifacts(
        str(COMPILER_DIR), insertion_actor=scenario.DECISION_OWNER_NAME)


def _load_identity() -> dict:
    return json.loads(RUN_IDENTITY_PATH.read_text(encoding="utf-8"))


def _evaluator_spec():
    from sworldmodel.decision.contracts import EvaluatorSpec

    return EvaluatorSpec(primary_metric=scenario.PRIMARY_METRIC,
                         secondary_metrics=tuple(scenario.SECONDARY_METRICS))


def _recipient_name(world) -> str:
    """The recipient actor NAME resolved from the compiled cast (never
    assumed): the single actor that is not the insertion actor."""
    insertion = world.intervention_insertion_point.actor_id
    others = [actor.name for actor in world.actors
              if actor.actor_id != insertion]
    if len(others) != 1:
        raise SystemExit(
            "this experiment measures a two-actor world; the compiled "
            f"cast has {len(world.actors)} actors "
            f"({[a.name for a in world.actors]}), so the recipient is "
            "ambiguous. Reported, not repaired.")
    return others[0]


def _run_scenario(*, scenario_id, out_dir, generated, progress):
    from sworldmodel.compilation.decision_route import (
        build_generator_prompt, generator_config_hash,
        prepare_decision_inputs)
    from sworldmodel.counterfactuals import run_candidates_detailed
    from sworldmodel.counterfactuals.branch import derive_branch_id
    from sworldmodel.counterfactuals.snapshot import (build_base_plan,
                                                      derive_branch_seed)
    from sworldmodel.decision.contracts import DecisionProblem
    from sworldmodel.outcomes import evaluate_branches
    from sworldmodel.reporting import (build_recommendation_report,
                                       build_trace_report)

    api_key = _api_key()
    identity = _load_identity()
    start_iso = identity["run_start_utc"]
    cutoff_iso = identity["cutoff_utc"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _progress(progress, f"{scenario_id}: adapting the frozen compiler "
                        "artifact set (deterministic, no LLM call)")
    adapted = _adapt_world()
    world = adapted.world
    recipient = _recipient_name(world)
    _progress(progress, f"{scenario_id}: cast = "
              + ", ".join(f"{a.name}({a.actor_id})" for a in world.actors)
              + f"; recipient = {recipient}")

    problem_payload = scenario.build_problem_payload(
        start_iso=start_iso, cutoff_iso=cutoff_iso, generated=generated)
    problem = DecisionProblem.from_dict(problem_payload)
    spec = _evaluator_spec()

    items = scenario.evidence_items(problem_payload)
    manifest = evidence_lib.build_manifest(
        experiment_id=scenario_id, window_start=start_iso,
        window_cutoff=cutoff_iso, items=items,
        actor_names=[actor.name for actor in world.actors],
        notes=("Frozen before simulation and hashed into "
               "freeze_manifest.json. Private-context assignments were "
               "requested of the compiler; where the compiler placed a "
               "claim is recorded in the compiled world, not here."))
    evidence_lib.write_manifest(manifest,
                                out_dir / "evidence_manifest.json")
    _write_json(out_dir / "decision_problem.json", problem_payload)

    base_plan = build_base_plan(world, spec, max_steps=scenario.MAX_STEPS)
    limits = {"max_steps": scenario.MAX_STEPS, "seed": scenario.BASE_SEED,
              "agency_guard_enabled": True,
              "acting_order": base_plan.gm_config.get("acting_order"),
              "max_generated": scenario.MAX_GENERATED if generated else 0}

    frozen = freeze_lib.FreezeManifest(
        scenario_id=scenario_id,
        note=("Frozen before any branch simulation. " + RUN_LABEL))
    frozen.add_json("decision_problem", problem_payload)
    frozen.add_json("evidence_manifest", manifest)
    frozen.add_json("evidence_items", manifest["items"])
    frozen.add_json("compiler_command_and_config", {
        "callable": "compiler.scene_pipeline.compile_scene",
        "compiler_version": identity["compiler_version"],
        "caller": "compiler.scene_llm.SceneCaller",
        "model": recorder_lib.DEEPSEEK_MODEL_ID,
        "transport": ("experiments.full_trace_validation.recorder."
                      "RecordingSceneTransport"),
        "out_dir": identity["compiler_out_dir"]})
    frozen.add_json("compiler_inputs", {
        "question": identity["question"], "start": start_iso,
        "cutoff": cutoff_iso, "context": identity["context"],
        "evidence": identity["evidence_package"]})
    frozen.add_directory("compiler_artifact_dir", COMPILER_DIR)
    frozen.add_text("compiled_decision_world", world.canonical_json())
    frozen.add_text("concordia_initialization_plan",
                    base_plan.canonical_json())
    frozen.add_json("concordia_initialization_plan_content_hash",
                    base_plan.content_hash())
    frozen.add_json("evaluator_spec", spec.to_dict())
    frozen.add_json("model_identities_and_params", _model_configuration())
    frozen.add_json("simulation_limits", limits)
    frozen.add_json("engine_simulation_limits",
                    {key: value for key, value in limits.items()
                     if key != "max_generated"})
    frozen.add_json("time_window", {"start": start_iso,
                                    "cutoff": cutoff_iso})

    ledger = recorder_lib.CallLedger(
        scenario_id, out_dir / "all_llm_calls.jsonl")
    context_obj = recorder_lib.RecorderContext(
        experiment_id=scenario_id, ledger=ledger,
        boundary=recorder_lib.NetworkBoundary())

    generator_model = None
    if generated:
        prompt = build_generator_prompt(problem, scenario.MAX_GENERATED)
        (out_dir / "generator_prompt.txt").write_text(prompt,
                                                      encoding="utf-8")
        frozen.add_text("candidate_generator_prompt", prompt)
        frozen.add_json("candidate_generator_config", {
            "generator_config_hash": generator_config_hash(
                scenario.MAX_GENERATED),
            "max_generated": scenario.MAX_GENERATED,
            "evidence_available_to_the_generator": (
                "the fixed template interpolates ONLY DecisionProblem "
                "fields: decision_owner, desired_outcome, "
                "success_criteria, constraints, relevant_context, window, "
                "already-supplied candidates. No world-private context, "
                "no compiled actor context, and no evidence item marked "
                "entered_context=private reaches it."),
            "one_shot": True})
        ledger.set_sink(out_dir / "generator_llm_calls.jsonl")
        generator_model = recorder_lib.RecordingGeneratorModel(
            context_obj, api_key=api_key)
        _progress(progress, f"{scenario_id}: candidate generation (one "
                            "live call, one-shot, no iterative search)")

    generation_error = None
    try:
        inputs = prepare_decision_inputs(
            problem, world, evaluator_spec=spec,
            generator_model=generator_model,
            max_generated=scenario.MAX_GENERATED)
    except Exception as exc:  # noqa: BLE001 - recorded, never repaired
        generation_error = f"{type(exc).__name__}: {exc}"
        if generator_model is not None:
            (out_dir / "generator_raw_response.txt").write_text(
                generator_model.last_response or "", encoding="utf-8")
            _write_json(out_dir / "generator_parsed.json", {
                "parsed": None, "rejected": True,
                "parse_or_validation_error": generation_error,
                "raw_response_preserved_in":
                    "generator_raw_response.txt"})
        _progress(progress,
                  f"{scenario_id}: candidate preparation FAILED: "
                  f"{generation_error}")
        _write_json(out_dir / "preparation_failure.json",
                    {"error": generation_error,
                     "instrumentation": context_obj.instrumentation()})
        return 3
    finally:
        ledger.set_sink(None)

    if generator_model is not None:
        (out_dir / "generator_raw_response.txt").write_text(
            generator_model.last_response or "", encoding="utf-8")
        try:
            parsed = json.loads(generator_model.last_response or "")
        except ValueError as exc:
            parsed = {"_unparsable": str(exc)}
        _write_json(out_dir / "generator_parsed.json", {
            "parsed_by_the_route": [candidate.to_dict()
                                    for candidate in inputs.candidates],
            "raw_json_as_returned": parsed,
            "rejected_fields_or_parse_errors": None,
            "generator_config_hash": generator_config_hash(
                scenario.MAX_GENERATED),
            "one_shot_generation": True,
            "note": ("the current implementation performs ONE-SHOT "
                     "generation, not iterative best-action search")})

    candidates = inputs.candidates
    candidate_payloads = [candidate.to_dict() for candidate in candidates]
    _write_json(out_dir / "candidates" / "candidates.json",
                candidate_payloads)
    frozen.add_json("candidate_set", candidate_payloads)

    branch_ids = {candidate.candidate_id:
                  derive_branch_id(world.world_id, candidate.candidate_id)
                  for candidate in candidates}
    branch_seeds = {candidate.candidate_id:
                    derive_branch_seed(scenario.BASE_SEED,
                                       candidate.candidate_id)
                    for candidate in candidates}
    frozen.add_json("branch_seeds", {"base_seed": scenario.BASE_SEED,
                                     "per_candidate": branch_seeds,
                                     "branch_ids": branch_ids})
    frozen.write(out_dir / "freeze_manifest.json")
    _progress(progress, f"{scenario_id}: freeze manifest written; "
              f"world={frozen.get('compiled_decision_world')[:16]} "
              f"plan={base_plan.content_hash()[:16]}")

    if generated:
        supplied_manifest = freeze_lib.load_manifest(
            SUPPLIED_DIR / "freeze_manifest.json")
        proof = freeze_lib.assert_entries_equal(
            supplied_manifest, freeze_lib.load_manifest(
                out_dir / "freeze_manifest.json"), REUSED_ENTRIES)
        _write_json(out_dir / "world_reuse_proof.json", {
            "claim": ("scenario 2 reused scenario 1's compiled world and "
                      "base plan byte-for-byte; no recompilation "
                      "occurred"),
            "entries": proof,
            "compiler_llm_calls_in_this_scenario": 0})
        _progress(progress, f"{scenario_id}: world/plan reuse proof OK")

    _write_json(out_dir / "adapter" / "adapted_world.json",
                json.loads(world.canonical_json()))
    _write_json(out_dir / "adapter" / "adapter_sidecar.json",
                adapted.sidecar)
    _write_json(out_dir / "adapter" / "actor_id_by_name.json",
                adapted.actor_id_by_name)
    _write_json(out_dir / "adapter" / "base_plan.json",
                json.loads(base_plan.canonical_json()))

    capture: dict = {}
    cursors: dict = {}
    factory = recorder_lib.live_model_factory(
        context_obj, api_key=api_key, world=world, branch_ids=branch_ids,
        capture=capture, cursors=cursors)

    def recording_factory(candidate, branch_seed):
        ledger.set_sink(out_dir / "branches" / candidate.candidate_id
                        / "llm_calls.jsonl")
        _progress(progress, f"{scenario_id}: branch "
                            f"{candidate.candidate_id} starting "
                            f"(seed {branch_seed})")
        return factory(candidate, branch_seed)

    wall_started = time.perf_counter()
    run = run_candidates_detailed(
        world, candidates, model_factory=recording_factory,
        seed=scenario.BASE_SEED, max_steps=scenario.MAX_STEPS,
        evaluator_spec=spec, registry=inputs.registry,
        model_config={"kind": HARNESS_VERSION,
                      "provider": recorder_lib.PROVIDER,
                      "model": recorder_lib.DEEPSEEK_MODEL_ID})
    wall = round(time.perf_counter() - wall_started, 2)
    ledger.set_sink(None)
    _progress(progress, f"{scenario_id}: all branches finished in {wall}s")

    declared = predicate_lib.declared_predicates(recipient)
    evaluated = evaluate_branches(
        run.results, declared, evaluator_spec=spec,
        status_rule=predicate_lib.status_rule, registry=inputs.registry)
    report = build_recommendation_report(
        problem, candidates, run, evaluated, spec,
        provenance_label="live_model", registry=inputs.registry)
    trace = build_trace_report(run, evaluated)

    all_calls = recorder_lib.read_ledger(out_dir / "all_llm_calls.jsonl")
    evaluator_ledger = {
        "label": RUN_LABEL,
        "scenario_id": scenario_id,
        "evaluator_spec": spec.to_dict(),
        "status_rule": ("call_agreed -> success; an explicit decline -> "
                        "failure; neither by the cutoff -> the runner's "
                        "default (cutoff when the step budget was "
                        "exhausted, incomplete for a technical stop)"),
        "attribution_anchor": predicate_lib.ACTOR_TURN_ANCHOR,
        "recipient_actor": recipient,
        "measurement_limitation": (
            "agreement is measured by explicit surface patterns over free "
            "live-model text; a recipient who agrees in wording no "
            "pattern covers is scored cutoff, not success"),
        "branches": [],
    }
    for result in evaluated:
        record = run.runner_records.get(result.candidate_id)
        explanation = predicate_lib.explain_metrics(
            [{"event_id": event.event_id,
              "description": event.description}
             for event in result.event_trace], recipient)
        evaluator_ledger["branches"].append({
            "candidate_id": result.candidate_id,
            "branch_id": result.branch_id,
            "committed_trace_ref":
                f"branches/{result.candidate_id}/committed_events.jsonl",
            "committed_event_count": len(result.event_trace),
            "terminal_status": result.terminal_status,
            "infrastructure_errors": list(result.infrastructure_errors),
            "metrics": {
                name: {"value": metric.value,
                       "computed_from": list(metric.computed_from),
                       "cited_event_texts": _cited_texts(
                           result.event_trace, metric.computed_from)}
                for name, metric in result.outcome_metrics.items()},
            "predicate_explanation": explanation,
            "steps_completed": (record or {}).get("steps_completed"),
        })
    recommendation = report["recommendation"]
    evaluator_ledger["ranking"] = {
        "declared_order": list(spec.all_metrics()),
        "ranking_key": ("primary metric first, then each secondary metric "
                        "in declared order; ties broken by the declared "
                        "candidate order"),
        "ranking": recommendation.get("ranking"),
        "best_candidate_id": recommendation.get("best_candidate_id"),
        "metric_differences": recommendation.get("metric_differences"),
        "downside_outcomes": recommendation.get("downside_outcomes"),
        "decided_by_metric": report.get("decided_by_metric"),
        "tie_break_used": bool(
            recommendation.get("validation_status", {}).get(
                "tie_break_candidate_id_lexicographic", False)),
        "validation_status": recommendation.get("validation_status"),
        "run_limitations": recommendation.get("run_limitations"),
        "final_recommendation_result": recommendation,
    }
    _write_json(out_dir / "evaluator_ledger.json", evaluator_ledger)
    _write_json(out_dir / "recommendation_result.json", recommendation)
    _write_json(out_dir / "recommendation_report.json", report)
    _write_json(out_dir / "trace_report.json", trace)

    unavailable_all: list = []
    for result in evaluated:
        candidate_id = result.candidate_id
        branch_dir = out_dir / "branches" / candidate_id
        branch_dir.mkdir(parents=True, exist_ok=True)
        record = run.runner_records.get(candidate_id)
        branch_calls = [call for call in all_calls
                        if call.get("branch_id") == branch_ids[candidate_id]]
        committed = list(record.get("committed_events") or []) if record \
            else []
        if record is None:
            _write_json(branch_dir / "branch_result.json", result.to_dict())
            _write_json(branch_dir / "runner_record_missing.json", {
                "reason": ("the branch failed before the runner returned; "
                           "no raw log exists"),
                "infrastructure_errors": list(result.infrastructure_errors)})
            continue
        step_ledger = ledger_lib.build_step_ledger(
            branch_id=branch_ids[candidate_id], candidate_id=candidate_id,
            plan=run.branch_plans[candidate_id], runner_record=record,
            calls=branch_calls, committed_events=committed,
            world_start=start_iso, world_cutoff=cutoff_iso)
        ledger_lib.write_jsonl(step_ledger,
                               branch_dir / "step_ledger.jsonl",
                               banner=ledger_lib.AUDITOR_ONLY_BANNER)
        ledger_lib.write_jsonl(ledger_lib.observation_rows(step_ledger),
                               branch_dir / "observations.jsonl")
        ledger_lib.write_jsonl(ledger_lib.guard_rows(step_ledger),
                               branch_dir / "guard_ledger.jsonl")
        ledger_lib.write_jsonl(
            ledger_lib.committed_event_rows(branch_ids[candidate_id],
                                            committed),
            branch_dir / "committed_events.jsonl")
        _write_json(branch_dir / "branch_result.json", result.to_dict())
        branch_trace = [entry for entry in trace["branches"]
                        if entry["candidate_id"] == candidate_id]
        _write_json(branch_dir / "trace_report.json",
                    branch_trace[0] if branch_trace else
                    {"unavailable": "no trace entry for this branch"})
        _write_json(branch_dir / "actor_memories.json",
                    record.get("actor_memories") or {})
        _write_json(branch_dir / "raw_engine_log.json",
                    record.get("raw_log") or [])
        cursor = cursors.get(candidate_id)
        _write_json(branch_dir / "step_attribution_check.json", {
            "method": ("one actor model call per engine step; a game "
                       "master call takes the current step number, and an "
                       "actor call that arrives when the current step "
                       "already has one advances the cursor"),
            "actor_calls_recorded": getattr(cursor, "actor_calls", None),
            "cursor_final_step": getattr(cursor, "step", None),
            "steps_completed_reported_by_runner":
                record.get("steps_completed"),
            "raw_log_entries": len(record.get("raw_log") or []),
            "consistent": (getattr(cursor, "actor_calls", None)
                           == record.get("steps_completed"))})
        unavailable_all.extend(
            {"candidate_id": candidate_id, **item}
            for item in ledger_lib.collect_unavailable(step_ledger))

    instrumentation = context_obj.instrumentation()
    instrumentation["wall_seconds"] = wall
    instrumentation["unavailable_fields"] = unavailable_all
    _write_json(SHARED_DIR / f"instrumentation_{scenario_id}.json",
                instrumentation)
    _progress(progress, f"{scenario_id}: instrumentation "
              f"{instrumentation['equality_proof']}")
    if not instrumentation["equality_proof"]["all_equal"]:
        _progress(progress, f"{scenario_id}: INSTRUMENTATION MISMATCH")
        return 4
    if generation_error:
        return 3
    return 0


# ---------------------------------------------------------------------------
# phase: validate
# ---------------------------------------------------------------------------


def phase_validate(progress) -> int:
    parts = {}
    for name in ("compile", scenario.SUPPLIED_EXPERIMENT_ID,
                 scenario.GENERATED_EXPERIMENT_ID):
        path = SHARED_DIR / f"instrumentation_{name}.json"
        if path.is_file():
            parts[name] = json.loads(path.read_text(encoding="utf-8"))
    ledger_files = sorted(ARTIFACT_ROOT.rglob("*llm_calls.jsonl"))
    master_files = [path for path in ledger_files
                    if path.name in ("all_llm_calls.jsonl",)
                    or path.parent.name == "compiler"]
    call_ids: list = []
    per_role: dict = {}
    for path in master_files:
        for record in recorder_lib.read_ledger(path):
            call_ids.append(record["call_id"])
            per_role[record["role"]] = per_role.get(record["role"], 0) + 1
    totals = {
        "ledger_records_written": sum(
            part["ledger"]["records_written"] for part in parts.values()),
        "network_boundary_requests": sum(
            part["network_boundary"]["request_count"]
            for part in parts.values()),
        "seam_attempt_total": sum(
            part["seam_attempt_total"] for part in parts.values()),
        "distinct_call_ids_on_disk": len(set(call_ids)),
        "records_on_disk": len(call_ids),
    }
    all_equal = len(set(totals.values())) == 1
    payload = {
        "label": recorder_lib.__doc__.splitlines()[0],
        "generated_at": _now(),
        "per_phase": parts,
        "master_ledger_files": [str(path.relative_to(REPO_ROOT))
                                for path in master_files],
        "totals": totals,
        "per_role_on_disk": dict(sorted(per_role.items())),
        "equality_proof": {
            "claim": ("every provider request issued at the network "
                      "boundary produced exactly one ledger record with a "
                      "distinct call_id; no live call bypassed the "
                      "recorder"),
            "all_equal": all_equal,
            "values": totals,
        },
    }
    _write_json(SHARED_DIR / "instrumentation_validation.json", payload)
    _progress(progress, f"validate: totals={totals} all_equal={all_equal}")
    if (SUPPLIED_DIR / "candidate_delivery_check.json").is_file():
        from experiments.full_trace_validation import report as report_lib

        _progress(progress,
                  f"validate: wrote {report_lib.write_readme(ARTIFACT_ROOT)}")
    return 0 if all_equal else 5


# ---------------------------------------------------------------------------
# phase: audit (no live calls; reads the frozen artifacts only)
# ---------------------------------------------------------------------------


def audit_scenario_dir(out_dir: Path) -> dict:
    """Candidate-delivery check + post-hoc measurement audit for one
    finished scenario.  Reads artifacts only; issues no provider call."""
    from experiments.full_trace_validation import (audit_predicates,
                                                   delivery)

    out_dir = Path(out_dir)
    evaluator = json.loads(
        (out_dir / "evaluator_ledger.json").read_text(encoding="utf-8"))
    candidates = {entry["candidate_id"]: entry for entry in json.loads(
        (out_dir / "candidates" / "candidates.json").read_text(
            encoding="utf-8"))}
    recipient = evaluator["recipient_actor"]

    branches = []
    branch_audits = {}
    for branch in evaluator["branches"]:
        candidate_id = branch["candidate_id"]
        ledger_path = (out_dir / "branches" / candidate_id
                       / "step_ledger.jsonl")
        rows = (delivery.load_step_ledger(ledger_path)
                if ledger_path.is_file() else [])
        branches.append((candidate_id,
                         candidates[candidate_id]["action"], rows))
        trace = [{"event_id": f"ev_{index:04d}",
                  "description": row["text"]}
                 for index, row in enumerate(_committed_rows(
                     out_dir / "branches" / candidate_id
                     / "committed_events.jsonl"))]
        branch_audits[candidate_id] = audit_predicates.audit_branch(
            trace, recipient,
            {name: value["value"]
             for name, value in branch["metrics"].items()})

    check = delivery.check_scenario(
        scenario_id=evaluator["scenario_id"], recipient_name=recipient,
        branches=branches)
    world = json.loads(
        (out_dir / "adapter" / "adapted_world.json").read_text(
            encoding="utf-8"))
    private_by_name = {actor["name"]: actor["private_context"]
                       for actor in world["actors"]}
    all_rows = [row for _cid, _action, rows in branches for row in rows]
    check["private_context_leak_check"] = \
        delivery.private_context_leak_check(
            step_ledger_rows=all_rows, private_by_name=private_by_name)

    # Resolve every metric citation to the exact committed text.  Pure
    # lookup from the committed stream: values and citations are never
    # touched, only rendered.
    changed = False
    for branch in evaluator["branches"]:
        rows = _committed_rows(out_dir / "branches"
                               / branch["candidate_id"]
                               / "committed_events.jsonl")
        by_id = {row["event_id"]: row["text"] for row in rows}
        for metric in branch["metrics"].values():
            texts = []
            for citation in metric["computed_from"]:
                if isinstance(citation, int) and 0 <= citation < len(rows):
                    texts.append(rows[citation]["text"])
                elif isinstance(citation, str) \
                        and citation.startswith("event:"):
                    text = by_id.get(citation.split(":", 1)[1])
                    if text is not None:
                        texts.append(text)
            if texts != metric.get("cited_event_texts"):
                metric["cited_event_texts"] = texts
                changed = True
    if changed:
        _write_json(out_dir / "evaluator_ledger.json", evaluator)
    _write_json(out_dir / "candidate_delivery_check.json", check)
    audit = audit_predicates.audit_scenario(branch_audits)
    _write_json(out_dir / "measurement_audit.json", audit)
    return {"delivery": check, "audit": audit}


def _committed_rows(path) -> list:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def phase_audit(progress) -> int:
    from experiments.full_trace_validation import report as report_lib

    for out_dir in (SUPPLIED_DIR, GENERATED_DIR):
        if not (out_dir / "evaluator_ledger.json").is_file():
            _progress(progress, f"audit: {out_dir.name} has no evaluator "
                                "ledger; skipping")
            continue
        result = audit_scenario_dir(out_dir)
        path = report_lib.write_report(ARTIFACT_ROOT, out_dir)
        _progress(progress, f"audit: wrote {path}")
        _progress(progress, f"audit: {out_dir.name} delivery verdict = "
                            f"{result['delivery']['verdict']}; distinct "
                            "recipient first-turn prompts = "
                            f"{result['delivery']['distinct_recipient_first_turn_prompts']}"
                            "; reading disagreements = "
                            f"{result['audit']['branches_where_the_two_readings_disagree']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True,
                        choices=("compile", "supplied", "generated",
                                 "audit", "validate"))
    parser.add_argument("--progress-file", default=None)
    args = parser.parse_args(argv)
    progress = args.progress_file
    if args.phase == "compile":
        return phase_compile(progress)
    if args.phase == "supplied":
        return _run_scenario(
            scenario_id=scenario.SUPPLIED_EXPERIMENT_ID,
            out_dir=SUPPLIED_DIR, generated=False, progress=progress)
    if args.phase == "generated":
        return _run_scenario(
            scenario_id=scenario.GENERATED_EXPERIMENT_ID,
            out_dir=GENERATED_DIR, generated=True, progress=progress)
    if args.phase == "audit":
        return phase_audit(progress)
    return phase_validate(progress)


if __name__ == "__main__":
    raise SystemExit(main())
