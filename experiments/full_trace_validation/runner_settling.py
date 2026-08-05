"""Driver for the settling experiment (see ``settling.py`` for the design).

Experiment-only.  Every actor turn is a live provider completion recorded
through the ordinary recorder; the only harness-supplied text in the whole
run is the game master's observer-ROUTING answer, and that is recorded
verbatim in ``forced_observer_control.json`` for every branch.

Phases (each rep is its own monitored job so a provider stall cannot take
the experiment down)::

    --phase rep --arm a --rep 1     one live branch, arm A
    --phase rep --arm b --rep 1     one live branch, arm B
    --phase summarize               per-arm rates + SETTLING_RESULT.md

Nothing under ``artifacts/full_trace_validation_20260804`` other than the
``settling_experiment/`` subtree is written by this module.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import (HARNESS_VERSION,  # noqa: E402
                                               RUN_LABEL)
from experiments.full_trace_validation import delivery as delivery_lib
from experiments.full_trace_validation import freeze as freeze_lib
from experiments.full_trace_validation import ledgers as ledger_lib
from experiments.full_trace_validation import predicates as predicate_lib
from experiments.full_trace_validation import recorder as recorder_lib
from experiments.full_trace_validation import scenario_peter as scenario
from experiments.full_trace_validation import settling as settling_lib

ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
SUPPLIED_DIR = ARTIFACT_ROOT / "peter_supplied"
COMPILER_DIR = SUPPLIED_DIR / "compiler"
SETTLING_DIR = ARTIFACT_ROOT / "settling_experiment"
RUN_IDENTITY_PATH = ARTIFACT_ROOT / "shared" / "run_identity.json"

#: the ONE candidate this experiment uses, frozen here so both arms and
#: every rep provably use the same intervention text.  It is the first of
#: the three emails the user supplied, taken verbatim from the frozen
#: candidate set that scenario 1 ran.
SETTLING_CANDIDATE_ID = "user_001"

#: reps per arm.  Temperature 0 is a bounded policy, not a determinism
#: guarantee, so a single sample per arm could not distinguish "the
#: sender never enacts" from "this sample did not".
REPS_PER_ARM = 3


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


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit(
            "DEEPSEEK_API_KEY is not set: this experiment only runs "
            "against the live provider and never fabricates output")
    return key


def provider_probe(api_key: str) -> dict:
    """A one-token health probe issued OUTSIDE the simulation.

    It is not simulation content and is not in the call ledger; it is
    here because the ledger records the model id the harness REQUESTED
    and the provider may serve a different build under that id.
    """
    body = json.dumps({"model": recorder_lib.DEEPSEEK_MODEL_ID,
                       "messages": [{"role": "user", "content": "hi"}],
                       "max_tokens": 1}).encode("utf-8")
    request = urllib.request.Request(
        recorder_lib.DEEPSEEK_BASE_URL + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        "requested_model": recorder_lib.DEEPSEEK_MODEL_ID,
        "served_model_reported_by_provider": payload.get("model"),
        "response_id": payload.get("id"),
        "system_fingerprint": payload.get("system_fingerprint"),
        "usage": payload.get("usage"),
        "probed_at": _now(),
    }


def _environment() -> dict:
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


def _model_configuration() -> dict:
    """The model configuration for this experiment.

    Identical to the Peter scenarios' actor / game-master configuration
    (``runner_peter._model_configuration``) minus the compiler and
    generator roles, which this experiment does not exercise: it reuses
    the frozen compiler artifacts and one frozen supplied candidate.
    """
    return {
        "provider": recorder_lib.PROVIDER,
        "base_url": recorder_lib.DEEPSEEK_BASE_URL,
        "model": recorder_lib.DEEPSEEK_MODEL_ID,
        "roles": {
            "actor": {
                "seam": "counterfactuals.manager.run_candidates_detailed("
                        "model_factory=)",
                "temperature": 0.0, "max_tokens": 400,
                "response_format": None,
                "live": True},
            "game_master": {
                "seam": "counterfactuals.manager.run_candidates_detailed("
                        "model_factory=)",
                "temperature": 0.0, "max_tokens": 400,
                "response_format": None,
                "live": ("yes for every call EXCEPT the observer-routing "
                         "question, which is forced to the full roster as "
                         "the experiment's declared control"),
                "forced_control": settling_lib.OBSERVER_QUESTION},
        },
        "retry_policy": {
            "max_attempts_per_call": recorder_lib.MAX_ATTEMPTS,
            "backoff_seconds": list(recorder_lib.BACKOFF_SECONDS),
            "every_attempt_recorded": True},
        "sampling_note": ("temperature 0 is a bounded policy, not a "
                          "determinism claim: the provider does not "
                          "guarantee reproducible completions"),
    }


def _adapt_world():
    from sworldmodel.compilation.existing_compiler_adapter import (
        adapt_compiled_artifacts)

    return adapt_compiled_artifacts(
        str(COMPILER_DIR), insertion_actor=scenario.DECISION_OWNER_NAME)


def _recipient_name(world) -> str:
    insertion = world.intervention_insertion_point.actor_id
    others = [actor.name for actor in world.actors
              if actor.actor_id != insertion]
    if len(others) != 1:
        raise SystemExit(
            "this experiment measures a two-actor world; the compiled "
            f"cast has {len(world.actors)} actors, so the recipient is "
            "ambiguous. Reported, not repaired.")
    return others[0]


def _sender_name(world) -> str:
    insertion = world.intervention_insertion_point.actor_id
    for actor in world.actors:
        if actor.actor_id == insertion:
            return actor.name
    raise SystemExit("the world's insertion actor is not in its own cast")


def _committed_rows(path) -> list:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _refusal_record(exc, evaluated) -> dict:
    return {
        "refused": True,
        "error_type": type(exc).__name__,
        "reason": str(exc),
        "what_this_means": (
            "no branch's candidate text reached any actor other than the "
            "insertion actor, so the engine refuses to name a winner"),
        "per_branch_delivery": {
            result.candidate_id: dict(result.intervention_delivered)
            for result in evaluated},
    }


# ---------------------------------------------------------------------------
# phase: rep
# ---------------------------------------------------------------------------


def phase_rep(*, arm: str, rep: int, progress) -> int:
    from sworldmodel.compilation.decision_route import prepare_decision_inputs
    from sworldmodel.counterfactuals import run_candidates_detailed
    from sworldmodel.counterfactuals.branch import derive_branch_id
    from sworldmodel.counterfactuals.snapshot import (build_base_plan,
                                                      derive_branch_seed)
    from sworldmodel.decision.contracts import (DecisionProblem, EvaluatorSpec)
    from sworldmodel.outcomes import (InterventionNotDeliveredError,
                                      evaluate_branches)
    from sworldmodel.reporting import (build_recommendation_report,
                                       build_trace_report)

    api_key = _api_key()
    arm_label, arm_note = settling_lib.ARMS[arm]
    run_id = f"settling_arm_{arm}_rep_{rep}"
    out_dir = SETTLING_DIR / f"arm_{arm}" / f"rep_{rep}"
    out_dir.mkdir(parents=True, exist_ok=True)

    identity = _read_json(RUN_IDENTITY_PATH)
    start_iso = identity["run_start_utc"]
    cutoff_iso = identity["cutoff_utc"]

    _progress(progress, f"{run_id}: probing the provider before the run")
    probe_pre = provider_probe(api_key)
    _progress(progress, f"{run_id}: provider serves "
                        f"{probe_pre['served_model_reported_by_provider']!r} "
                        f"for {probe_pre['requested_model']!r}")

    _progress(progress, f"{run_id}: adapting the frozen compiler artifact "
                        "set (deterministic, no LLM call)")
    adapted = _adapt_world()
    base_world = adapted.world
    world = settling_lib.arm_world(base_world, arm)
    sender = _sender_name(world)
    recipient = _recipient_name(world)
    difference = settling_lib.arm_difference(
        base_world, settling_lib.arm_world(base_world, "b"))
    _progress(progress, f"{run_id}: arm={arm} ({arm_label}); sender={sender}; "
                        f"recipient={recipient}; starting_events="
                        f"{len(world.starting_events)}")

    problem_payload = scenario.build_problem_payload(
        start_iso=start_iso, cutoff_iso=cutoff_iso, generated=False)
    problem = DecisionProblem.from_dict(problem_payload)
    spec = EvaluatorSpec(primary_metric=scenario.PRIMARY_METRIC,
                         secondary_metrics=tuple(scenario.SECONDARY_METRICS))

    inputs = prepare_decision_inputs(problem, world, evaluator_spec=spec,
                                     generator_model=None,
                                     max_generated=scenario.MAX_GENERATED)
    chosen = [candidate for candidate in inputs.candidates
              if candidate.candidate_id == SETTLING_CANDIDATE_ID]
    if len(chosen) != 1:
        raise SystemExit(
            f"the frozen settling candidate {SETTLING_CANDIDATE_ID!r} is "
            "not in the problem's candidate set "
            f"({[c.candidate_id for c in inputs.candidates]}); refusing to "
            "substitute another one")
    candidates = tuple(chosen)
    candidate = candidates[0]

    base_plan = build_base_plan(world, spec, max_steps=scenario.MAX_STEPS)
    branch_ids = {candidate.candidate_id:
                  derive_branch_id(world.world_id, candidate.candidate_id)}
    branch_seeds = {candidate.candidate_id:
                    derive_branch_seed(scenario.BASE_SEED,
                                       candidate.candidate_id)}

    frozen = freeze_lib.FreezeManifest(
        scenario_id=run_id,
        note=("Frozen before the branch ran. Settling experiment arm "
              f"{arm} ({arm_label}), rep {rep}. " + RUN_LABEL))
    frozen.add_json("decision_problem", problem_payload)
    frozen.add_json("evidence_manifest", identity["evidence_manifest"])
    frozen.add_json("compiler_command_and_config", {
        "callable": "compiler.scene_pipeline.compile_scene",
        "compiler_version": identity["compiler_version"],
        "caller": "compiler.scene_llm.SceneCaller",
        "model": recorder_lib.DEEPSEEK_MODEL_ID,
        "transport": ("experiments.full_trace_validation.recorder."
                      "RecordingSceneTransport"),
        "out_dir": identity["compiler_out_dir"],
        "note": ("this experiment did NOT recompile: it re-adapts the "
                 "compiler artifact directory scenario 1 froze, by "
                 "deterministic code, and issues zero compiler calls")})
    frozen.add_json("compiler_inputs", {
        "question": identity["question"], "start": start_iso,
        "cutoff": cutoff_iso, "context": identity["context"],
        "evidence": identity["evidence_package"]})
    frozen.add_directory("compiler_artifact_dir", COMPILER_DIR)
    frozen.add_text("compiled_decision_world_as_compiled",
                    base_world.canonical_json())
    # the world this arm actually ran on: arm A's is byte-identical to the
    # compiled world, arm B's differs in starting_events and nothing else
    frozen.add_text("compiled_decision_world", world.canonical_json())
    frozen.add_json("arm_difference", difference)
    frozen.add_text("concordia_initialization_plan",
                    base_plan.canonical_json())
    frozen.add_json("concordia_initialization_plan_content_hash",
                    base_plan.content_hash())
    frozen.add_json("evaluator_spec", spec.to_dict())
    frozen.add_json("candidate_set",
                    [candidate.to_dict() for candidate in candidates])
    frozen.add_json("model_identities_and_params", _model_configuration())
    frozen.add_json("simulation_limits",
                    {"max_steps": scenario.MAX_STEPS,
                     "seed": scenario.BASE_SEED,
                     "agency_guard_enabled": True,
                     "acting_order": base_plan.gm_config.get("acting_order")})
    frozen.add_json("branch_seeds", {"base_seed": scenario.BASE_SEED,
                                     "per_candidate": branch_seeds,
                                     "branch_ids": branch_ids})
    frozen.add_json("time_window", {"start": start_iso, "cutoff": cutoff_iso})
    frozen.add_json("forced_observer_control",
                    {"question": settling_lib.OBSERVER_QUESTION,
                     "forced_answer_is": "the branch's full actor roster"})
    frozen.write(out_dir / "freeze_manifest.json")

    _write_json(out_dir / "arm_design.json", {
        "run_id": run_id, "arm": arm, "arm_label": arm_label,
        "arm_note": arm_note, "rep": rep,
        "candidate_id": candidate.candidate_id,
        "candidate_action": candidate.action,
        "sender": sender, "recipient": recipient,
        "seed": scenario.BASE_SEED, "max_steps": scenario.MAX_STEPS,
        "branch_id": branch_ids[candidate.candidate_id],
        "branch_seed": branch_seeds[candidate.candidate_id],
        "arm_difference": difference,
        "plan_content_hash": base_plan.content_hash(),
        "world_content_hash": world.content_hash(),
    })
    _write_json(out_dir / "adapter" / "adapted_world.json",
                json.loads(world.canonical_json()))
    _write_json(out_dir / "adapter" / "adapter_sidecar.json",
                adapted.sidecar)
    _write_json(out_dir / "adapter" / "base_plan.json",
                json.loads(base_plan.canonical_json()))

    ledger = recorder_lib.CallLedger(run_id, out_dir / "all_llm_calls.jsonl")
    context_obj = recorder_lib.RecorderContext(
        experiment_id=run_id, ledger=ledger,
        boundary=recorder_lib.NetworkBoundary())

    capture: dict = {}
    cursors: dict = {}
    control_log: list = []
    factory = settling_lib.forced_observer_model_factory(
        context_obj, api_key=api_key, world=world, branch_ids=branch_ids,
        capture=capture, cursors=cursors, control_log=control_log)

    def recording_factory(candidate_obj, branch_seed):
        ledger.set_sink(out_dir / "branches" / candidate_obj.candidate_id
                        / "llm_calls.jsonl")
        _progress(progress, f"{run_id}: branch {candidate_obj.candidate_id} "
                            f"starting (seed {branch_seed})")
        return factory(candidate_obj, branch_seed)

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
    _progress(progress, f"{run_id}: branch finished in {wall}s")

    declared = predicate_lib.declared_predicates(recipient)
    evaluated = evaluate_branches(
        run.results, declared, evaluator_spec=spec,
        status_rule=predicate_lib.status_rule, registry=inputs.registry)
    trace = build_trace_report(run, evaluated)
    report = None
    refusal = None
    try:
        report = build_recommendation_report(
            problem, candidates, run, evaluated, spec,
            provenance_label="live_model", registry=inputs.registry)
    except InterventionNotDeliveredError as exc:
        refusal = _refusal_record(exc, evaluated)
        _progress(progress, f"{run_id}: ranking REFUSED")

    _write_json(out_dir / "trace_report.json", trace)
    _write_json(out_dir / "recommendation_report.json",
                report if report is not None else refusal)
    if refusal is not None:
        _write_json(out_dir / "ranking_refusal.json", refusal)

    all_calls = recorder_lib.read_ledger(out_dir / "all_llm_calls.jsonl")
    result = evaluated[0]
    record = run.runner_records.get(result.candidate_id)
    branch_dir = out_dir / "branches" / result.candidate_id
    branch_dir.mkdir(parents=True, exist_ok=True)
    branch_calls = [call for call in all_calls
                    if call.get("branch_id")
                    == branch_ids[result.candidate_id]]
    committed = list(record.get("committed_events") or []) if record else []
    step_ledger: list = []
    if record is not None:
        step_ledger = ledger_lib.build_step_ledger(
            branch_id=branch_ids[result.candidate_id],
            candidate_id=result.candidate_id,
            plan=run.branch_plans[result.candidate_id], runner_record=record,
            calls=branch_calls, committed_events=committed,
            world_start=start_iso, world_cutoff=cutoff_iso)
        ledger_lib.write_jsonl(step_ledger, branch_dir / "step_ledger.jsonl",
                               banner=ledger_lib.AUDITOR_ONLY_BANNER)
        ledger_lib.write_jsonl(ledger_lib.observation_rows(step_ledger),
                               branch_dir / "observations.jsonl")
        ledger_lib.write_jsonl(ledger_lib.guard_rows(step_ledger),
                               branch_dir / "guard_ledger.jsonl")
        ledger_lib.write_jsonl(
            ledger_lib.committed_event_rows(
                branch_ids[result.candidate_id], committed),
            branch_dir / "committed_events.jsonl")
        _write_json(branch_dir / "actor_memories.json",
                    record.get("actor_memories") or {})
        _write_json(branch_dir / "raw_engine_log.json",
                    record.get("raw_log") or [])
    else:
        _write_json(branch_dir / "runner_record_missing.json", {
            "reason": ("the branch failed before the runner returned; no "
                       "raw log exists"),
            "infrastructure_errors": list(result.infrastructure_errors)})
    _write_json(branch_dir / "branch_result.json", result.to_dict())

    _write_json(out_dir / "forced_observer_control.json", {
        "what_this_is": (
            "the ONE piece of text this experiment supplies. The game "
            "master's observer-ROUTING answer is forced to the full "
            "roster so the known observer-routing defect (D1, closed at "
            "c5a81214) cannot confound the measurement. Every actor turn "
            "is a live provider completion; no other game-master call was "
            "intercepted."),
        "intercepted_question": settling_lib.OBSERVER_QUESTION,
        "roster_broadcast": list(
            capture[result.candidate_id]["forced_observer_answer"].split(
                ", ")),
        "interceptions": control_log,
        "interception_count": len(control_log),
        "control_actually_fired": bool(control_log),
    })

    delivery_check = delivery_lib.check_branch(
        candidate_id=result.candidate_id, candidate_action=candidate.action,
        recipient_name=recipient, step_ledger_rows=step_ledger)
    first_turn = settling_lib.sender_first_turn(branch_calls, sender)
    enactment = settling_lib.enactment_check(
        first_turn_text=first_turn.get("text"),
        candidate_action=candidate.action)
    instrumentation = context_obj.instrumentation()
    instrumentation["wall_seconds"] = wall
    _write_json(out_dir / "instrumentation.json", instrumentation)
    probe_post = provider_probe(api_key)
    _write_json(out_dir / "provider_probe.json",
                {"pre_run": probe_pre, "post_run": probe_post})

    measurement = {
        "run_id": run_id, "arm": arm, "arm_label": arm_label, "rep": rep,
        "candidate_id": result.candidate_id,
        "branch_id": result.branch_id,
        "sender": sender, "recipient": recipient,
        "starting_event_count": len(world.starting_events),
        "sender_first_turn": first_turn,
        "sender_enactment": enactment,
        "candidate_text_in_recipient_prompts": {
            "recipient_prompt_count":
                delivery_check["recipient_prompt_count"],
            "fragments_tested":
                delivery_check["candidate_fragments_tested"],
            "fragments_found":
                delivery_check["candidate_fragments_found_in_recipient_prompts"],
            "content_delivered_to_recipient":
                delivery_check["content_delivered_to_recipient"],
            "recipient_first_turn_prompt_sha256":
                delivery_check["recipient_first_turn_prompt_sha256"],
            "example_fragment_found":
                delivery_check["example_fragment_found"],
        },
        "intervention_delivered": dict(result.intervention_delivered),
        "unresolved_observers": [dict(entry)
                                 for entry in result.unresolved_observers],
        "unresolved_observer_count": len(result.unresolved_observers),
        "forced_observer_interceptions": len(control_log),
        "terminal_status": result.terminal_status,
        "outcome_metrics": {name: metric.value for name, metric
                            in result.outcome_metrics.items()},
        "ranking": ("REFUSED" if refusal is not None else "PRODUCED"),
        "ranking_reason": (refusal["reason"] if refusal is not None
                           else "the engine produced a ranking"),
        "guard_interventions": sum(
            1 for row in ledger_lib.guard_rows(step_ledger)
            if row.get("intervened")),
        "committed_event_count": len(result.event_trace),
        "steps_completed": (record or {}).get("steps_completed"),
        "infrastructure_errors": list(result.infrastructure_errors),
        "live_calls": instrumentation["ledger"]["records_written"],
        "live_call_errors":
            instrumentation["ledger"]["records_with_error"],
        "live_call_retries":
            instrumentation["ledger"]["records_that_were_retries"],
        "provider_served":
            probe_pre["served_model_reported_by_provider"],
        "wall_seconds": wall,
    }
    _write_json(out_dir / "settling_measurement.json", measurement)
    _write_json(out_dir / "candidate_delivery_check.json", delivery_check)
    _progress(progress, f"{run_id}: enacted="
                        f"{enactment['sender_enacted_candidate_verbatim']} "
                        f"delivered_to_recipient="
                        f"{delivery_check['content_delivered_to_recipient']} "
                        f"intervention_delivered="
                        f"{result.intervention_delivered.get('status')} "
                        f"ranking={measurement['ranking']}")
    if not instrumentation["equality_proof"]["all_equal"]:
        _progress(progress, f"{run_id}: INSTRUMENTATION MISMATCH")
        return 4
    if not control_log:
        _progress(progress, f"{run_id}: FORCED CONTROL NEVER FIRED")
        return 6
    return 0


# ---------------------------------------------------------------------------
# phase: summarize
# ---------------------------------------------------------------------------


def _arm_rows(arm: str) -> list:
    rows = []
    for rep in range(1, REPS_PER_ARM + 1):
        path = SETTLING_DIR / f"arm_{arm}" / f"rep_{rep}" \
            / "settling_measurement.json"
        if path.is_file():
            rows.append(_read_json(path))
    return rows


def _rate(rows, key) -> dict:
    hits = [row for row in rows if bool(_dig(row, key))]
    return {"n": len(rows), "hits": len(hits),
            "rate": (round(len(hits) / len(rows), 4) if rows else None)}


def _dig(row, dotted):
    value = row
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def arm_summary(arm: str) -> dict:
    rows = _arm_rows(arm)
    arm_label, arm_note = settling_lib.ARMS[arm]
    return {
        "arm": arm, "arm_label": arm_label, "arm_note": arm_note,
        "reps_recorded": len(rows),
        "sender_enacted_candidate_verbatim": _rate(
            rows, "sender_enactment.sender_enacted_candidate_verbatim"),
        "candidate_text_in_recipient_prompts": _rate(
            rows,
            "candidate_text_in_recipient_prompts."
            "content_delivered_to_recipient"),
        "intervention_delivered_status": [
            _dig(row, "intervention_delivered.status") for row in rows],
        "ranking": [row.get("ranking") for row in rows],
        "terminal_status": [row.get("terminal_status") for row in rows],
        "unresolved_observer_count": [row.get("unresolved_observer_count")
                                      for row in rows],
        "guard_interventions": [row.get("guard_interventions")
                                for row in rows],
        "forced_observer_interceptions": [
            row.get("forced_observer_interceptions") for row in rows],
        "provider_served": sorted({row.get("provider_served")
                                   for row in rows
                                   if row.get("provider_served")}),
        "live_calls": sum(row.get("live_calls") or 0 for row in rows),
        "live_call_errors": sum(row.get("live_call_errors") or 0
                                for row in rows),
        "live_call_retries": sum(row.get("live_call_retries") or 0
                                 for row in rows),
        "longest_shared_run_chars": [
            _dig(row, "sender_enactment.longest_shared_run_chars")
            for row in rows],
        "candidate_token_overlap_ratio": [
            _dig(row, "sender_enactment.candidate_token_overlap_ratio")
            for row in rows],
        "sender_first_turns": [
            {"rep": row.get("rep"),
             "text": _dig(row, "sender_first_turn.text")} for row in rows],
        "recipient_first_turn_prompt_sha256": [
            _dig(row, "candidate_text_in_recipient_prompts."
                      "recipient_first_turn_prompt_sha256")
            for row in rows],
    }


def phase_summarize(progress) -> int:
    from experiments.full_trace_validation import report_settling

    summaries = {arm: arm_summary(arm) for arm in ("a", "b")}
    aggregate = {
        "label": RUN_LABEL,
        "generated_at": _now(),
        "environment": _environment(),
        "model_configuration": _model_configuration(),
        "candidate_id": SETTLING_CANDIDATE_ID,
        "reps_per_arm_declared": REPS_PER_ARM,
        "arms": summaries,
        "totals": {
            "live_calls": sum(summary["live_calls"]
                              for summary in summaries.values()),
            "live_call_errors": sum(summary["live_call_errors"]
                                    for summary in summaries.values()),
            "live_call_retries": sum(summary["live_call_retries"]
                                     for summary in summaries.values()),
        },
    }
    _write_json(SETTLING_DIR / "SETTLING_MEASUREMENTS.json", aggregate)
    readme = report_settling.write_readme(SETTLING_DIR, aggregate)
    result = report_settling.write_result(SETTLING_DIR, aggregate)
    _progress(progress, f"summarize: wrote {readme} and {result}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True,
                        choices=("rep", "summarize"))
    parser.add_argument("--arm", default=None, choices=("a", "b"))
    parser.add_argument("--rep", type=int, default=None)
    parser.add_argument("--progress-file", default=None)
    args = parser.parse_args(argv)
    if args.phase == "summarize":
        return phase_summarize(args.progress_file)
    if args.arm is None or args.rep is None:
        parser.error("--phase rep requires --arm and --rep")
    return phase_rep(arm=args.arm, rep=args.rep,
                     progress=args.progress_file)


if __name__ == "__main__":
    raise SystemExit(main())
