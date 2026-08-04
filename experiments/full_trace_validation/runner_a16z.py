"""Driver for the a16z historical hiring counterfactual.

Experiment-only.  Every phase runs the REAL production path against the
live model; the harness only records, freezes, validates, and writes
artifacts.  It never authors an actor turn, a game-master resolution, or
a compiler manifest.

Phases (each is its own monitored job so a provider stall cannot take the
whole experiment down)::

    --phase compile     real compiler, live -> a16z_richard_historical/
    --phase branches    the six salary branches, live
    --phase audit       delivery + isolation + cutoff audit + report
    --phase validate    instrumentation cross-check

The historical boundary is enforced MECHANICALLY, not promised: every
compiler input, every compiled surface, every plan, every candidate,
every evidence item and every actor prompt is scanned by
:mod:`cutoff`, and a violation refuses the run.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import (HARNESS_VERSION,  # noqa: E402
                                               RUN_LABEL)
from experiments.full_trace_validation import branch_diff as diff_lib
from experiments.full_trace_validation import cutoff as cutoff_lib
from experiments.full_trace_validation import evidence as evidence_lib
from experiments.full_trace_validation import freeze as freeze_lib
from experiments.full_trace_validation import ledgers as ledger_lib
from experiments.full_trace_validation import offer_delivery as delivery_lib
from experiments.full_trace_validation import predicates_a16z as predicate_lib
from experiments.full_trace_validation import recorder as recorder_lib
from experiments.full_trace_validation import scenario_a16z as scenario

ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
SCENARIO_DIR = ARTIFACT_ROOT / scenario.EXPERIMENT_ID
COMPILER_DIR = SCENARIO_DIR / "compiler"
ATTEMPTS_DIR = SCENARIO_DIR / "compiler_attempts"
RUN_IDENTITY_PATH = SCENARIO_DIR / "run_identity.json"


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


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _refusal_record(exc, evaluated) -> dict:
    """The recorded shape of a REFUSED ranking.

    ``sworldmodel.outcomes.ranking`` refuses to name a winner when no
    branch delivered its intervention to any actor but the insertion
    actor -- the exact failure this scenario's own live run produced and
    published a winner for anyway.  The refusal is now the result: it is
    written where the recommendation would have been, with the engine's
    verbatim reason and the per-branch delivery facts the engine computed
    from each branch's own artifacts.
    """
    return {
        "refused": True,
        "error_type": type(exc).__name__,
        "reason": str(exc),
        "what_this_means": (
            "the counterfactual's independent variable never varied "
            "downstream: no branch's candidate text reached any actor "
            "other than the insertion actor, so the branches cannot be "
            "compared and no winner is reported"),
        "per_branch_delivery": {
            result.candidate_id: dict(result.intervention_delivered)
            for result in evaluated},
    }


def _jsonl(path) -> list:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


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
        "model_identity_caveat": (
            "the harness records the model id it REQUESTED. The provider "
            "may serve a different build under that id; the pre-run and "
            "post-run probes in provider_probe.json record what the "
            "provider itself reported."),
        "roles": {
            "compiler": {
                "transport": "compiler.scene_llm.SceneCaller(transport=)",
                "temperature": 0.0, "max_tokens": 8000,
                "response_format": "json_object",
                "semantic_call_budget": 3},
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
        "candidate_generator_not_used": (
            "candidate_generation_permission is false in this contract: "
            "all six candidates are the user's own declared interventions, "
            "so the generator seam issues zero calls"),
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
        "scenario_id": scenario.EXPERIMENT_ID,
        "repository_sha": sha,
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "recorded_at": _now(),
    }


# ---------------------------------------------------------------------------
# compile-attempt acceptance (declared BEFORE the first attempt)
# ---------------------------------------------------------------------------


def evaluate_compile_attempt(status, reason, manifest) -> dict:
    """Apply the frozen mechanical acceptance criteria to one attempt."""
    import re

    checks: dict = {}
    checks["compiler_status_ok"] = status in ("compiled", "corrected")
    cast: list = []
    prewritten: list = []
    cutoff_report = None
    if isinstance(manifest, dict) and isinstance(manifest.get("actors"),
                                                 list):
        cast = [actor.get("name") for actor in manifest["actors"]]
        negation = re.compile(scenario.NEGATION_BEFORE_RE, re.IGNORECASE)
        for pattern in scenario.PREWRITTEN_OUTCOME_PATTERNS:
            compiled = re.compile(pattern, re.IGNORECASE)
            for index, event in enumerate(manifest.get("starting_events")
                                          or []):
                description = str(event.get("description", ""))
                for found in compiled.finditer(description):
                    if negation.search(description[:found.start()]):
                        # "no offer has been made" is the OPPOSITE of a
                        # prewritten outcome; recorded, never counted
                        continue
                    prewritten.append({
                        "starting_event_index": index,
                        "pattern": pattern,
                        "matched_text": found.group(0),
                        "description": description})
        cutoff_report = cutoff_lib.scan_surfaces(
            {"final_scene_manifest": manifest})
    checks["cast_is_exactly_the_declared_five"] = (
        sorted(name for name in cast if name)
        == sorted(scenario.REQUIRED_CAST))
    checks["no_prewritten_outcome_in_starting_events"] = not prewritten
    checks["historical_cutoff_clean"] = bool(
        cutoff_report and cutoff_report["clean"])
    accepted = all(checks.values())
    return {
        "accepted": accepted,
        "compiler_status": status,
        "compiler_reason": reason,
        "compiled_cast_in_declaration_order": cast,
        "checks": checks,
        "prewritten_outcome_findings": prewritten,
        "cutoff_scan": cutoff_report,
        "rejection_reasons": [name for name, value in checks.items()
                              if not value],
    }


# ---------------------------------------------------------------------------
# phase: compile
# ---------------------------------------------------------------------------


def phase_compile(progress) -> int:
    from compiler.scene_llm import SceneCaller
    from compiler.scene_pipeline import COMPILER_VERSION, compile_scene

    _api_key()
    problem_payload = scenario.build_problem_payload()
    start_iso = problem_payload["time_horizon"]["start"]
    cutoff_iso = problem_payload["time_horizon"]["cutoff"]
    items = scenario.evidence_items()
    manifest = evidence_lib.build_manifest(
        experiment_id=scenario.COMPILE_EXPERIMENT_ID,
        window_start=start_iso, window_cutoff=cutoff_iso, items=items,
        actor_names=(),
        notes=("Written before compilation. The compiled cast is not yet "
               "known, so actor references are validated again after "
               "adaptation."))
    question = scenario.compiler_question(problem_payload)
    context = scenario.compiler_context(problem_payload)
    package = scenario.render_evidence_package(manifest)

    # ---- the historical boundary, BEFORE any live call ------------------
    pre_compile_surfaces = {
        "decision_problem": problem_payload,
        "evidence_manifest": manifest,
        "compiler_question": question,
        "compiler_context": context,
        "compiler_evidence_package": package,
        "harness_scope_note": scenario.SCOPE_NOTE,
    }
    try:
        pre_report = cutoff_lib.assert_clean(pre_compile_surfaces)
    except cutoff_lib.HistoricalCutoffViolation as exc:
        SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
        _write_json(SCENARIO_DIR / "historical_cutoff_validation.json",
                    {"stage": "pre_compile", "clean": False,
                     "violations": exc.findings})
        _progress(progress, f"compile REFUSED: {exc}")
        return 6
    _progress(progress,
              "compile: pre-compile cutoff gate clean over "
              f"{pre_report['surface_count']} surfaces "
              f"({len(pre_report['window_references'])} window references)")

    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(SCENARIO_DIR / "environment.json", _environment())
    _write_json(SCENARIO_DIR / "model_configuration.json",
                _model_configuration())

    ledger = recorder_lib.CallLedger(
        scenario.COMPILE_EXPERIMENT_ID, ATTEMPTS_DIR / "all_llm_calls.jsonl")
    context_obj = recorder_lib.RecorderContext(
        experiment_id=scenario.COMPILE_EXPERIMENT_ID, ledger=ledger,
        boundary=recorder_lib.NetworkBoundary())

    attempts: list = []
    accepted_attempt = None
    for attempt in range(1, scenario.MAX_COMPILE_ATTEMPTS + 1):
        attempt_dir = ATTEMPTS_DIR / f"attempt_{attempt}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        ledger.set_sink(attempt_dir / "llm_calls.jsonl")
        transport = recorder_lib.RecordingSceneTransport(context_obj)
        caller = SceneCaller(model=recorder_lib.DEEPSEEK_MODEL_ID,
                             transport=transport)
        _progress(progress, f"compile: attempt {attempt}/"
                            f"{scenario.MAX_COMPILE_ATTEMPTS} calling the "
                            "real compiler (up to 3 semantic calls)")
        started = time.perf_counter()
        result = compile_scene(question, start_iso, cutoff_iso,
                               context=context, evidence=package,
                               caller=caller, out_dir=str(attempt_dir))
        wall = round(time.perf_counter() - started, 2)
        ledger.set_sink(None)
        verdict = evaluate_compile_attempt(result.status, result.reason,
                                           result.manifest)
        verdict.update({"attempt": attempt, "wall_seconds": wall,
                        "compiler_metrics": result.metrics,
                        "artifact_dir": str(
                            attempt_dir.relative_to(REPO_ROOT))})
        _write_json(attempt_dir / "attempt_verdict.json", verdict)
        attempts.append(verdict)
        _progress(progress,
                  f"compile: attempt {attempt} status={result.status} "
                  f"accepted={verdict['accepted']} wall={wall}s cast="
                  + ", ".join(str(name) for name
                              in verdict["compiled_cast_in_declaration_order"]))
        if verdict["accepted"]:
            accepted_attempt = attempt
            break
        _progress(progress, "compile: attempt rejected because "
                  + ", ".join(verdict["rejection_reasons"]))

    _write_json(ATTEMPTS_DIR / "compile_attempts.json", {
        "acceptance_criteria": scenario.compile_acceptance_criteria(),
        "attempts": attempts,
        "accepted_attempt": accepted_attempt,
        "note": ("attempts used BYTE-IDENTICAL inputs; every attempt's "
                 "artifacts and live calls are committed above. Resampling "
                 "is disclosed, never repair: no compiler output was "
                 "edited by the harness."),
    })
    _write_json(SCENARIO_DIR / "instrumentation_compile.json",
                context_obj.instrumentation())

    if accepted_attempt is None:
        _progress(progress, "compile FAILED: no attempt met the declared "
                            "acceptance criteria; reported, not repaired")
        return 2

    source = ATTEMPTS_DIR / f"attempt_{accepted_attempt}"
    if COMPILER_DIR.exists():
        shutil.rmtree(COMPILER_DIR)
    shutil.copytree(source, COMPILER_DIR)
    copy_proof = {
        "accepted_attempt": accepted_attempt,
        "source": str(source.relative_to(REPO_ROOT)),
        "target": str(COMPILER_DIR.relative_to(REPO_ROOT)),
        "per_file_sha256_source": freeze_lib.hash_directory(source),
        "per_file_sha256_target": freeze_lib.hash_directory(COMPILER_DIR),
    }
    copy_proof["byte_identical_copy"] = (
        copy_proof["per_file_sha256_source"]["aggregate"]
        == copy_proof["per_file_sha256_target"]["aggregate"])
    _write_json(SCENARIO_DIR / "compiler_copy_proof.json", copy_proof)
    if not copy_proof["byte_identical_copy"]:
        _progress(progress, "compile FAILED: the accepted attempt was not "
                            "copied byte-identically")
        return 2

    accepted = attempts[accepted_attempt - 1]
    identity = {
        "label": RUN_LABEL,
        "scenario_id": scenario.EXPERIMENT_ID,
        "window_start_utc": start_iso,
        "window_cutoff_utc": cutoff_iso,
        "historical_cutoff": cutoff_lib.CUTOFF_DATE.isoformat(),
        "compiler_version": COMPILER_VERSION,
        "compiler_status": accepted["compiler_status"],
        "compiler_reason": accepted["compiler_reason"],
        "compiler_out_dir": str(COMPILER_DIR.relative_to(REPO_ROOT)),
        "compile_attempts": len(attempts),
        "accepted_attempt": accepted_attempt,
        "compiled_cast_in_declaration_order":
            accepted["compiled_cast_in_declaration_order"],
        "question": question,
        "context": context,
        "evidence_package": package,
        "compiler_metrics": accepted["compiler_metrics"],
        "evidence_manifest_pre_compile": manifest,
        "decision_problem_payload": problem_payload,
        "pre_compile_cutoff_report": pre_report,
    }
    _write_json(RUN_IDENTITY_PATH, identity)
    _progress(progress, f"compile: wrote {RUN_IDENTITY_PATH}")
    _progress(progress, "compile: accepted cast = "
              + ", ".join(accepted["compiled_cast_in_declaration_order"]))
    return 0


# ---------------------------------------------------------------------------
# phase: branches
# ---------------------------------------------------------------------------


def _adapt_world():
    from sworldmodel.compilation.existing_compiler_adapter import (
        adapt_compiled_artifacts)

    return adapt_compiled_artifacts(
        str(COMPILER_DIR), insertion_actor=scenario.DECISION_OWNER_NAME)


def _cited_texts(event_trace, citations) -> list:
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


def _resolve_cast(world) -> dict:
    """Bind the declared roles to the compiled cast by EXACT name."""
    names = [actor.name for actor in world.actors]
    if sorted(names) != sorted(scenario.REQUIRED_CAST):
        raise SystemExit(
            "the compiled cast is not the declared five actors: "
            f"{names}. Reported, not repaired.")
    insertion = world.intervention_insertion_point.actor_id
    by_name = {actor.name: actor.actor_id for actor in world.actors}
    if by_name[scenario.DECISION_OWNER_NAME] != insertion:
        raise SystemExit(
            "the compiled world's insertion boundary is "
            f"{insertion!r}, not the declared decision owner "
            f"{scenario.DECISION_OWNER_NAME!r}. Reported, not repaired.")
    return {"actor_id_by_name": by_name,
            "declaration_order": names,
            "insertion_actor_id": insertion}


def phase_branches(progress) -> int:
    from sworldmodel.compilation.decision_route import prepare_decision_inputs
    from sworldmodel.counterfactuals import run_candidates_detailed
    from sworldmodel.counterfactuals.branch import derive_branch_id
    from sworldmodel.counterfactuals.snapshot import (build_base_plan,
                                                      derive_branch_seed)
    from sworldmodel.decision.contracts import (DecisionProblem,
                                                EvaluatorSpec)
    from sworldmodel.outcomes import (InterventionNotDeliveredError,
                                      evaluate_branch)
    from sworldmodel.reporting import (build_recommendation_report,
                                       build_trace_report)

    api_key = _api_key()
    identity = _load_json(RUN_IDENTITY_PATH)
    start_iso = identity["window_start_utc"]
    cutoff_iso = identity["window_cutoff_utc"]
    out_dir = SCENARIO_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    _progress(progress, "branches: adapting the frozen compiler artifact "
                        "set (deterministic, no LLM call)")
    adapted = _adapt_world()
    world = adapted.world
    cast = _resolve_cast(world)
    _progress(progress, "branches: cast = "
              + ", ".join(f"{a.name}({a.actor_id})" for a in world.actors))

    problem_payload = scenario.build_problem_payload()
    problem = DecisionProblem.from_dict(problem_payload)
    spec = EvaluatorSpec(primary_metric=scenario.PRIMARY_METRIC,
                         secondary_metrics=tuple(scenario.SECONDARY_METRICS))

    items = scenario.evidence_items()
    manifest = evidence_lib.build_manifest(
        experiment_id=scenario.EXPERIMENT_ID, window_start=start_iso,
        window_cutoff=cutoff_iso, items=items,
        actor_names=[actor.name for actor in world.actors],
        notes=("Frozen before simulation and hashed into "
               "freeze_manifest.json. There are no PUBLICLY_VERIFIED items: "
               "this run did not consult a dated public source, because "
               "doing so from outside the counterfactual would risk "
               "importing material published after the 2025-07-01 cutoff. "
               "Private-context assignments were REQUESTED of the "
               "compiler; where the compiler actually placed a claim is "
               "recorded in the compiled world, not here."))
    evidence_lib.write_manifest(manifest, out_dir / "evidence_manifest.json")
    _write_json(out_dir / "decision_problem.json", problem_payload)

    base_plan = build_base_plan(world, spec, max_steps=scenario.MAX_STEPS)
    limits = {"max_steps": scenario.MAX_STEPS, "seed": scenario.BASE_SEED,
              "agency_guard_enabled": True,
              "acting_order": base_plan.gm_config.get("acting_order"),
              "acting_sequence": cast["declaration_order"],
              "max_generated": 0}

    frozen = freeze_lib.FreezeManifest(
        scenario_id=scenario.EXPERIMENT_ID,
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
        "out_dir": identity["compiler_out_dir"],
        "compile_attempts": identity["compile_attempts"],
        "accepted_attempt": identity["accepted_attempt"],
        "acceptance_criteria": scenario.compile_acceptance_criteria()})
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
    frozen.add_json("evaluator_salary_mapping",
                    scenario.salary_savings_mapping())
    frozen.add_json("model_identities_and_params", _model_configuration())
    frozen.add_json("simulation_limits", limits)
    frozen.add_json("time_window", {"start": start_iso,
                                    "cutoff": cutoff_iso,
                                    "historical_cutoff":
                                        cutoff_lib.CUTOFF_DATE.isoformat()})

    ledger = recorder_lib.CallLedger(
        scenario.EXPERIMENT_ID, out_dir / "all_llm_calls.jsonl")
    context_obj = recorder_lib.RecorderContext(
        experiment_id=scenario.EXPERIMENT_ID, ledger=ledger,
        boundary=recorder_lib.NetworkBoundary())

    inputs = prepare_decision_inputs(problem, world, evaluator_spec=spec,
                                     generator_model=None)
    candidates = inputs.candidates
    candidate_payloads = [candidate.to_dict() for candidate in candidates]
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    _write_json(out_dir / "candidates" / "candidates.json",
                candidate_payloads)
    frozen.add_json("candidate_set", candidate_payloads)

    savings = scenario.savings_by_candidate_id(candidate_ids)
    keys_by_id = scenario.candidate_key_by_id(candidate_ids)
    salary_by_id = {candidate_id: scenario.DECLARED_SALARY_TOKEN[key]
                    for candidate_id, key in keys_by_id.items()}
    baseline_id = next(candidate_id for candidate_id, key
                       in keys_by_id.items() if key == "no_offer")
    offer_ids = [candidate_id for candidate_id in candidate_ids
                 if candidate_id != baseline_id]
    _write_json(out_dir / "candidates" / "candidate_binding.json", {
        "claim": ("the code-owned binding from declared candidate position "
                  "to salary mapping key and savings value; verified "
                  "against the frozen candidate text, never against model "
                  "output"),
        "candidate_key_by_id": keys_by_id,
        "declared_salary_by_id": salary_by_id,
        "salary_savings_by_id": savings,
        "baseline_candidate_id": baseline_id,
        "offer_candidate_ids": offer_ids})
    frozen.add_json("candidate_binding", {"keys": keys_by_id,
                                          "savings": savings})

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
    _progress(progress, "branches: freeze manifest written; "
              f"world={frozen.get('compiled_decision_world')[:16]} "
              f"plan={base_plan.content_hash()[:16]}")

    _write_json(out_dir / "adapter" / "adapted_world.json",
                json.loads(world.canonical_json()))
    _write_json(out_dir / "adapter" / "adapter_sidecar.json",
                adapted.sidecar)
    _write_json(out_dir / "adapter" / "actor_id_by_name.json",
                adapted.actor_id_by_name)
    _write_json(out_dir / "adapter" / "base_plan.json",
                json.loads(base_plan.canonical_json()))

    # ---- the historical boundary over every pre-simulation surface -----
    from sworldmodel.counterfactuals.branch import apply_intervention

    branch_plans_preview = {
        candidate.candidate_id: apply_intervention(base_plan, candidate)
        for candidate in candidates}
    surfaces = {
        "decision_problem": problem_payload,
        "evidence_manifest": manifest,
        "compiler_inputs": {"question": identity["question"],
                            "context": identity["context"],
                            "evidence": identity["evidence_package"]},
        "compiled_decision_world": json.loads(world.canonical_json()),
        "concordia_initialization_plan": json.loads(
            base_plan.canonical_json()),
        "candidate_set": candidate_payloads,
    }
    for candidate_id, plan in branch_plans_preview.items():
        surfaces[f"branch_plan:{candidate_id}"] = json.loads(
            plan.canonical_json())
    try:
        pre_sim_report = cutoff_lib.assert_clean(surfaces)
    except cutoff_lib.HistoricalCutoffViolation as exc:
        _write_json(out_dir / "historical_cutoff_validation.json",
                    {"stage": "pre_simulation", "clean": False,
                     "violations": exc.findings})
        _progress(progress, f"branches REFUSED: {exc}")
        return 6
    _write_json(out_dir / "historical_cutoff_validation.json", {
        "stage": "pre_simulation",
        "note": ("the post-run stage (every recorded actor prompt and "
                 "every model response) is appended by --phase audit"),
        "pre_simulation": pre_sim_report})
    _progress(progress, "branches: pre-simulation cutoff gate clean over "
                        f"{pre_sim_report['surface_count']} surfaces")

    # ---- branch-input isolation proof, BEFORE the simulation ------------
    isolation = diff_lib.build_branch_input_diff(
        base_plan_dict=json.loads(base_plan.canonical_json()),
        branch_plan_dicts={cid: json.loads(plan.canonical_json())
                           for cid, plan in branch_plans_preview.items()},
        candidates_by_id={payload["candidate_id"]: payload
                          for payload in candidate_payloads},
        offer_candidate_ids=offer_ids,
        baseline_candidate_id=baseline_id,
        insertion_actor_id=cast["insertion_actor_id"],
        declared_salary_by_candidate_id=salary_by_id)
    _write_json(out_dir / "branch_input_diff.json", isolation)
    _progress(progress,
              f"branches: branch-input isolation = {isolation['verdict']}")
    if isolation["verdict"] != "only_the_salary_differs":
        _progress(progress, "branches REFUSED: the offer branches differ in "
                            "more than the salary; reported, not repaired")
        return 7

    capture: dict = {}
    cursors: dict = {}
    factory = recorder_lib.live_model_factory(
        context_obj, api_key=api_key, world=world, branch_ids=branch_ids,
        capture=capture, cursors=cursors)

    def recording_factory(candidate, branch_seed):
        ledger.set_sink(out_dir / "branches" / candidate.candidate_id
                        / "llm_calls.jsonl")
        _progress(progress, f"branches: branch {candidate.candidate_id} "
                            f"({keys_by_id[candidate.candidate_id]}) "
                            f"starting (seed {branch_seed})")
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
    _progress(progress, f"branches: all branches finished in {wall}s")

    predicates = predicate_lib.declared_predicates(
        approver_name=scenario.COMP_PARTNER_NAME,
        hiring_lead_name=scenario.DECISION_OWNER_NAME,
        subject_name=scenario.SUBJECT_NAME,
        savings_by_candidate_id=savings)
    evaluated = []
    rejection_by_id = {}
    for result in run.results:
        hits = predicate_lib.subject_rejection_hits(result.event_trace,
                                                    scenario.SUBJECT_NAME)
        rejection_by_id[result.candidate_id] = hits
        evaluated.append(evaluate_branch(
            result, predicates, evaluator_spec=spec,
            status_rule=predicate_lib.make_status_rule(
                subject_rejected=bool(hits)),
            registry=inputs.registry))
    evaluated = tuple(evaluated)

    trace = build_trace_report(run, evaluated)
    # A ranking is REFUSED when no branch delivered its intervention (the
    # exact shape this scenario's own run found).  Every other artifact is
    # still written and the refusal is recorded verbatim where the
    # recommendation would have been.
    report = None
    ranking_refusal = None
    try:
        report = build_recommendation_report(
            problem, candidates, run, evaluated, spec,
            provenance_label="live_model", registry=inputs.registry)
    except InterventionNotDeliveredError as exc:
        ranking_refusal = _refusal_record(exc, evaluated)
        _progress(progress,
                  "branches: ranking REFUSED -- no branch delivered its "
                  "intervention to any actor but the insertion actor")

    all_calls = recorder_lib.read_ledger(out_dir / "all_llm_calls.jsonl")
    evaluator_ledger = {
        "label": RUN_LABEL,
        "scenario_id": scenario.EXPERIMENT_ID,
        "evaluator_spec": spec.to_dict(),
        "status_rule": predicate_lib.STATUS_RULE_TEXT,
        "attribution_anchor": predicate_lib.ACTOR_TURN_ANCHOR,
        "subject_actor": scenario.SUBJECT_NAME,
        "compensation_approver": scenario.COMP_PARTNER_NAME,
        "hiring_lead": scenario.DECISION_OWNER_NAME,
        "primary_metric_rule": (
            "valid_offer_accepted is true only when the compensation "
            "approver's OWN committed turn authorizes, the hiring lead's "
            "OWN committed turn issues the offer, and the subject's OWN "
            "committed turn accepts at a strictly later trace position. "
            "Game-master narration and any other actor's paraphrase fail "
            "the attribution anchor and can never satisfy it."),
        "secondary_metric_rule": (
            "salary_savings_vs_300k is CODE-OWNED: the user's declared "
            "mapping applied to the branch's declared candidate. It is "
            "never parsed from model text and is never read from the "
            "trace; its citation is the scan bound only because the "
            "contract requires every metric to cite something."),
        "code_owned_salary_mapping": scenario.salary_savings_mapping(),
        "candidate_key_by_id": keys_by_id,
        "measurement_limitation": (
            "approval, offer issuance, acceptance and refusal are read by "
            "explicit surface patterns over free live-model text; an actor "
            "who accepts in wording no pattern covers is scored as not "
            "accepting"),
        "branches": [],
    }
    for result in evaluated:
        record = run.runner_records.get(result.candidate_id)
        explanation = predicate_lib.explain_metrics(
            [{"event_id": event.event_id,
              "description": event.description}
             for event in result.event_trace],
            approver_name=scenario.COMP_PARTNER_NAME,
            hiring_lead_name=scenario.DECISION_OWNER_NAME,
            subject_name=scenario.SUBJECT_NAME,
            savings_value=savings[result.candidate_id])
        authority = predicate_lib.authority_violation_scan(
            [{"event_id": event.event_id,
              "description": event.description}
             for event in result.event_trace],
            subject_name=scenario.SUBJECT_NAME)
        evaluator_ledger["branches"].append({
            "candidate_id": result.candidate_id,
            "candidate_key": keys_by_id[result.candidate_id],
            "declared_salary": salary_by_id[result.candidate_id],
            "branch_id": result.branch_id,
            "branch_seed": branch_seeds[result.candidate_id],
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
            "subject_explicit_refusals":
                rejection_by_id[result.candidate_id],
            "authority_violation_scan": authority,
            "steps_completed": (record or {}).get("steps_completed"),
        })
    recommendation = report["recommendation"] if report is not None else None
    if recommendation is not None:
        evaluator_ledger["ranking"] = {
            "declared_order": list(spec.all_metrics()),
            "ranking_key": ("primary metric first, then each secondary "
                            "metric in declared order, each compared "
                            "descending; ties broken by candidate_id in "
                            "ascending lexicographic order"),
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
    else:
        evaluator_ledger["ranking"] = {
            "declared_order": list(spec.all_metrics()),
            **ranking_refusal,
        }
    _write_json(out_dir / "evaluator_ledger.json", evaluator_ledger)
    _write_json(out_dir / "recommendation_result.json",
                recommendation if recommendation is not None
                else ranking_refusal)
    _write_json(out_dir / "recommendation_report.json",
                report if report is not None else ranking_refusal)
    if ranking_refusal is not None:
        _write_json(out_dir / "ranking_refusal.json", ranking_refusal)
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
    _write_json(SCENARIO_DIR / f"instrumentation_{scenario.EXPERIMENT_ID}"
                               ".json", instrumentation)
    _progress(progress, "branches: instrumentation "
              f"{instrumentation['equality_proof']}")
    if not instrumentation["equality_proof"]["all_equal"]:
        _progress(progress, "branches: INSTRUMENTATION MISMATCH")
        return 4
    return 0


# ---------------------------------------------------------------------------
# phase: audit (no live calls; reads the frozen artifacts only)
# ---------------------------------------------------------------------------


def phase_audit(progress) -> int:
    from experiments.full_trace_validation import delivery
    from experiments.full_trace_validation import report_a16z

    out_dir = SCENARIO_DIR
    evaluator = _load_json(out_dir / "evaluator_ledger.json")
    binding = _load_json(out_dir / "candidates" / "candidate_binding.json")
    candidates = {entry["candidate_id"]: entry for entry in
                  _load_json(out_dir / "candidates" / "candidates.json")}
    world = _load_json(out_dir / "adapter" / "adapted_world.json")
    subject = evaluator["subject_actor"]

    static_world_text = cutoff_lib.flatten_text({
        "shared_context": world["shared_context"],
        "actors": [{"name": actor["name"],
                    "private_context": actor["private_context"]}
                   for actor in world["actors"]],
        "starting_events": world["starting_events"]})

    branches = []
    rows_by_id = {}
    for branch in evaluator["branches"]:
        candidate_id = branch["candidate_id"]
        ledger_path = (out_dir / "branches" / candidate_id
                       / "step_ledger.jsonl")
        rows = (delivery.load_step_ledger(ledger_path)
                if ledger_path.is_file() else [])
        rows_by_id[candidate_id] = rows
        committed_path = (out_dir / "branches" / candidate_id
                          / "committed_events.jsonl")
        committed = ([row["text"] for row in _jsonl(committed_path)]
                     if committed_path.is_file() else [])
        branches.append((candidate_id, candidates[candidate_id]["action"],
                         rows, committed,
                         binding["declared_salary_by_id"][candidate_id]))

    check = delivery_lib.check_offer_delivery(
        scenario_id=evaluator["scenario_id"], subject_name=subject,
        branches=branches,
        baseline_candidate_id=binding["baseline_candidate_id"],
        static_world_text=static_world_text)
    private_by_name = {actor["name"]: actor["private_context"]
                       for actor in world["actors"]}
    all_rows = [row for rows in rows_by_id.values() for row in rows]
    check["private_context_leak_check"] = delivery.private_context_leak_check(
        step_ledger_rows=all_rows, private_by_name=private_by_name)
    check["distinctive_private_context_leak_check"] = (
        delivery_lib.distinctive_private_context_leak_check(
            step_ledger_rows=all_rows, private_by_name=private_by_name))
    _write_json(out_dir / "offer_delivery_check.json", check)
    _progress(progress, f"audit: offer delivery verdict = {check['verdict']}"
                        "; distinct subject first-turn prompts = "
                        f"{check['distinct_subject_first_turn_prompts']}")

    # ---- post-run cutoff audit over prompts AND responses --------------
    prompt_surfaces = {}
    response_surfaces = {}
    for candidate_id, rows in rows_by_id.items():
        prompts = []
        responses = []
        for row in rows:
            request = row.get("actor_model_request")
            if isinstance(request, list):
                for call in request:
                    for message in call.get("messages") or []:
                        prompts.append(message.get("content") or "")
            raw = row.get("actor_raw_response") or {}
            for call in raw.get("recorded_calls") or []:
                responses.append(call.get("response_raw") or "")
            gm = row.get("game_master_raw_response") or {}
            for call in gm.get("recorded_calls") or []:
                for message in call.get("request_messages") or []:
                    prompts.append(message.get("content") or "")
                responses.append(call.get("response_raw") or "")
        prompt_surfaces[f"actor_and_gm_prompts:{candidate_id}"] = prompts
        response_surfaces[f"model_responses:{candidate_id}"] = responses

    prompt_report = cutoff_lib.scan_surfaces(prompt_surfaces)
    response_report = cutoff_lib.scan_surfaces(response_surfaces)
    existing = _load_json(out_dir / "historical_cutoff_validation.json")
    existing["post_run_prompts"] = prompt_report
    existing["post_run_model_responses"] = {
        "status": ("ADVISORY: the harness cannot prevent a live model from "
                   "emitting post-cutoff material in its own output; a "
                   "finding here is reported, not suppressed"),
        **response_report}
    existing["enforced_stages"] = ["pre_compile", "pre_simulation",
                                   "post_run_prompts"]
    existing["overall_clean"] = bool(
        existing["pre_simulation"]["clean"] and prompt_report["clean"])
    existing["canary"] = {
        "canary_string": cutoff_lib.POST_CUTOFF_CANARY,
        "rejected_by_the_validator": not cutoff_lib.scan_text(
            "canary", cutoff_lib.POST_CUTOFF_CANARY)["clean"],
        "proof_test": ("tests/experiment_harness/test_a16z_cutoff.py::"
                       "test_the_canary_is_rejected_by_both_arms")}
    _write_json(out_dir / "historical_cutoff_validation.json", existing)
    _progress(progress, "audit: post-run prompt cutoff scan clean="
                        f"{prompt_report['clean']} "
                        f"({prompt_report['violation_count']} violations); "
                        "response scan clean="
                        f"{response_report['clean']} "
                        f"({response_report['violation_count']} findings)")

    path = report_a16z.write_report(SCENARIO_DIR)
    _progress(progress, f"audit: wrote {path}")
    return 0


# ---------------------------------------------------------------------------
# phase: validate
# ---------------------------------------------------------------------------


def phase_validate(progress) -> int:
    parts = {}
    for name in ("compile", scenario.EXPERIMENT_ID):
        path = SCENARIO_DIR / f"instrumentation_{name}.json"
        if path.is_file():
            parts[name] = _load_json(path)
    master_files = [ATTEMPTS_DIR / "all_llm_calls.jsonl",
                    SCENARIO_DIR / "all_llm_calls.jsonl"]
    master_files = [path for path in master_files if path.is_file()]
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
        "label": RUN_LABEL,
        "scenario_id": scenario.EXPERIMENT_ID,
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
    _write_json(SCENARIO_DIR / "instrumentation_validation.json", payload)
    _progress(progress, f"validate: totals={totals} all_equal={all_equal}")
    return 0 if all_equal else 5


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True,
                        choices=("compile", "branches", "audit", "validate"))
    parser.add_argument("--progress-file", default=None)
    args = parser.parse_args(argv)
    progress = args.progress_file
    if args.phase == "compile":
        return phase_compile(progress)
    if args.phase == "branches":
        return phase_branches(progress)
    if args.phase == "audit":
        return phase_audit(progress)
    return phase_validate(progress)


if __name__ == "__main__":
    raise SystemExit(main())
