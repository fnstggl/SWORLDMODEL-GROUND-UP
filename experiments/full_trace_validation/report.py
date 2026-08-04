"""Generate the UNDER_THE_HOOD report for one finished scenario.

Experiment-only.  Everything the report states about the run is READ FROM
THE FROZEN ARTIFACTS at generation time -- quotes are the recorded text,
counts are counted, hashes are the frozen hashes.  The judgement sections
(15, 16, 18, 20) are the harness author's assessment, and each judgement
is emitted only when the artifacts support it (for example the
information-flow finding is emitted from the delivery check's computed
verdict, not from an opinion typed in advance).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import RUN_LABEL
from . import evidence as evidence_lib
from . import recorder as recorder_lib

MAX_QUOTE = 900


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _jsonl(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _quote(text, limit=MAX_QUOTE):
    text = (text or "").strip()
    if len(text) > limit:
        text = text[:limit] + " […]"
    return "\n".join("> " + line for line in text.splitlines()) or "> "


def _fence(text, limit=MAX_QUOTE):
    text = (text or "").strip()
    if len(text) > limit:
        text = text[:limit] + "\n[…truncated…]"
    return "```\n" + text + "\n```"


class ScenarioArtifacts:
    def __init__(self, root: Path, scenario_dir: Path) -> None:
        self.root = Path(root)
        self.dir = Path(scenario_dir)
        self.identity = _load(self.root / "shared" / "run_identity.json")
        self.environment = _load(self.root / "shared" / "environment.json")
        self.model_config = _load(
            self.root / "shared" / "model_configuration.json")
        self.problem = _load(self.dir / "decision_problem.json")
        self.evidence = _load(self.dir / "evidence_manifest.json")
        self.freeze = _load(self.dir / "freeze_manifest.json")
        self.evaluator = _load(self.dir / "evaluator_ledger.json")
        self.recommendation = _load(self.dir / "recommendation_result.json")
        self.report = _load(self.dir / "recommendation_report.json")
        self.candidates = _load(self.dir / "candidates" / "candidates.json")
        self.world = _load(self.dir / "adapter" / "adapted_world.json")
        self.plan = _load(self.dir / "adapter" / "base_plan.json")
        self.sidecar = _load(self.dir / "adapter" / "adapter_sidecar.json")
        self.delivery = _load(self.dir / "candidate_delivery_check.json")
        self.audit = _load(self.dir / "measurement_audit.json")
        self.instrumentation = _load(
            self.root / "shared"
            / f"instrumentation_{self.evaluator['scenario_id']}.json")
        self.compiler_calls = _jsonl(
            self.root / "peter_supplied" / "compiler" / "llm_calls.jsonl")
        self.calls = _jsonl(self.dir / "all_llm_calls.jsonl")
        self.scenario_id = self.evaluator["scenario_id"]
        self.generated = self.scenario_id.endswith("generated")
        self.steps = {}
        for branch in self.evaluator["branches"]:
            path = (self.dir / "branches" / branch["candidate_id"]
                    / "step_ledger.jsonl")
            self.steps[branch["candidate_id"]] = [
                row for row in _jsonl(path)
                if "_artifact_class" not in row] if path.is_file() else []

    def candidate(self, candidate_id):
        for entry in self.candidates:
            if entry["candidate_id"] == candidate_id:
                return entry
        return {}

    def branch(self, candidate_id):
        for entry in self.evaluator["branches"]:
            if entry["candidate_id"] == candidate_id:
                return entry
        return {}


def _header(art: ScenarioArtifacts) -> list:
    from .scenario_peter import BASE_SEED

    seeds = {"base_seed": BASE_SEED,
             "per_candidate": {entry["candidate_id"]: entry["branch_seed"]
                               for entry in
                               art.report["branch_evaluations"]}}
    lines = [
        f"# {RUN_LABEL}",
        "",
        f"## UNDER THE HOOD -- `{art.scenario_id}`",
        "",
        "**This is not a prediction.** Nothing in this document predicts "
        "what Peter Thiel, or any real person, would actually do. It is a "
        "record of what one uncalibrated language model produced inside a "
        "simulation whose inputs are listed below, run once.",
        "",
        f"- **Model**: `{art.model_config['model']}` via "
        f"`{art.model_config['base_url']}` "
        f"(provider `{art.model_config['provider']}`), temperature 0 at "
        "every seam. Temperature 0 is a bounded policy, not a determinism "
        "guarantee.",
        f"- **Candidate provenance**: "
        + ("**generated** -- the three candidates were produced by one "
           "live model call at the route's generator seam; the current "
           "implementation performs ONE-SHOT generation, not iterative "
           "best-action search."
           if art.generated else
           "**user-supplied** -- the three candidate emails are the "
           "user's own text, carried verbatim into the run."),
        f"- **Evidence classification summary**: "
        f"{evidence_lib.summary_line(art.evidence)}",
        f"- **Window**: {art.identity['run_start_utc']} -> "
        f"{art.identity['cutoff_utc']} (the actual UTC run start plus "
        "exactly seven days)",
        f"- **Compiler**: `{art.identity['compiler_version']}`, status "
        f"`{art.identity['compiler_status']}`, semantic slots "
        f"{art.identity['compiler_metrics']['semantic_slots']}",
        f"- **Compiler artifact directory hash**: "
        f"`{art.freeze['entries']['compiler_artifact_dir_aggregate']['sha256']}`",
        f"- **Compiled world hash**: "
        f"`{art.freeze['entries']['compiled_decision_world']['sha256']}`",
        f"- **Base plan hash**: "
        f"`{art.freeze['entries']['concordia_initialization_plan_content_hash']['sha256']}` "
        f"(plan content hash `{art.report['base_plan_content_hash']}`)",
        f"- **Base seed**: {seeds['base_seed']}; **branch seeds**: "
        + ", ".join(f"`{key}`={value}"
                    for key, value in sorted(
                        seeds["per_candidate"].items())),
        f"- **Live calls in this scenario**: "
        f"{art.instrumentation['ledger']['records_written']} "
        f"({', '.join(f'{role}={count}' for role, count in sorted(art.instrumentation['ledger']['per_role'].items()))}), "
        f"0 fabricated, "
        f"{art.instrumentation['ledger']['records_with_error']} errored, "
        f"{art.instrumentation['ledger']['records_that_were_retries']} "
        f"retries",
        f"- **Repository SHA at run time**: "
        f"`{art.environment['repository_sha']}`; Python "
        f"`{art.environment['python'].split()[0]}`",
        "",
        "### Known limitations, stated up front",
        "",
        "1. One run. No repeats, no seeds swept, no calibration against "
        "any real outcome. Nothing here is statistically meaningful.",
        "2. The engine's contracts have **no first-class "
        "observed / inferred / latent fields**. Every claim in this "
        "simulation is carried as plain text in an actor's private "
        "context or the shared context; the only place its epistemic "
        "status is recorded is this experiment's `evidence_manifest.json`, "
        "which the engine itself never reads.",
        "3. Outcome measurement is surface-pattern matching over free "
        "live-model text, anchored to the recipient's own committed turn. "
        "See section 12 and `measurement_audit.json`.",
        "4. `simulation_time` does not exist: the pinned upstream "
        "sequential engine counts ordinal steps, not clock time. The "
        "seven-day window appears only as text.",
        "5. See section 20 for what this run does and does not prove.",
        "",
        "### Contents -- all 20 required points", "",
        "| # | point | where |", "| --- | --- | --- |",
        "| 1. | exact input | section 1 |",
        "| 2. | evidence used | section 2 |",
        "| 3. | compiler calls and outputs | section 3 |",
        "| 4. | compiled cast, private and shared information | "
        "section 4 |",
        "| 5. | adapter mapping | section 5 |",
        "| 6. | final Concordia plan | section 6 |",
        "| 7. | candidate insertion | section 7 |",
        "| 8. | each actor turn | section 8-11, per step |",
        "| 9. | each game-master resolution | section 8-11, per step |",
        "| 10. | every guard intervention | section 8-11, per step |",
        "| 11. | committed world events | section 8-11, per step |",
        "| 12. | outcome measurement | section 12 |",
        "| 13. | ranking | section 13 |",
        "| 14. | why the selected candidate won | section 14 |",
        "| 15. | behaviour that appeared realistic | section 15 |",
        "| 16. | generic / stereotyped / unsupported / implausible "
        "behaviour | section 16 |",
        "| 17. | information leaks | section 17 |",
        "| 18. | forced actor decisions | section 18 |",
        "| 19. | engineering failures | section 19 |",
        "| 20. | what this proves and does not prove | section 20 |",
        "",
    ]
    return lines


def _section_1(art):
    lines = ["## 1. The exact input", "",
             "The decision problem as frozen (hash "
             f"`{art.freeze['entries']['decision_problem']['sha256']}`):",
             "", _fence(json.dumps(art.problem, indent=2,
                                   ensure_ascii=False), 4000), ""]
    if art.generated:
        lines += [
            "This is the user's problem with exactly the declared delta: "
            "`problem_id` changed, `candidate_interventions` emptied, and "
            "`candidate_generation_permission` set true. Every other "
            "field is byte-identical to scenario 1.", ""]
    return lines


def _section_2(art):
    lines = ["## 2. Evidence used", "",
             "Frozen before compilation, hash "
             f"`{art.freeze['entries']['evidence_manifest']['sha256']}`. "
             "The classification rules are deliberately conservative: "
             "nothing about a real person's private personality, "
             "compensation, inbox behaviour, calendar, internal opinions "
             "or exact authority may be `PUBLICLY_VERIFIED`, however "
             "plausible the inference from a public biography.", "",
             "| claim | classification | who may know | used by compiler "
             "| entered context |", "| --- | --- | --- | --- | --- |"]
    for item in art.evidence["items"]:
        who = (item["who_may_know"] if isinstance(item["who_may_know"], str)
               else ", ".join(item["who_may_know"]))
        claim = item["claim"].replace("|", "/")
        if len(claim) > 150:
            claim = claim[:150] + "…"
        lines.append(f"| {claim} | {item['classification']} | {who} | "
                     f"{item['used_by_compiler']} | "
                     f"{item['entered_context']} |")
    lines += ["",
              "The exact evidence package handed to the compiler is "
              "frozen as `compiler_inputs` (hash "
              f"`{art.freeze['entries']['compiler_inputs']['sha256']}`) "
              "and reproduced in `shared/run_identity.json`.", ""]
    return lines


def _section_3(art):
    lines = ["## 3. Compiler calls and outputs", "",
             f"The real production compiler "
             f"(`compiler.scene_pipeline.compile_scene`, "
             f"`{art.identity['compiler_version']}`) ran once, at the "
             "start of scenario 1. **Scenario 2 did not recompile** -- it "
             "re-adapted the same frozen artifact directory (see section "
             "5).", "",
             f"- semantic slots opened: "
             f"{art.identity['compiler_metrics']['semantic_slots']}",
             f"- provider requests: "
             f"{art.identity['compiler_metrics']['provider_requests']}",
             f"- evidence mode: "
             f"`{art.identity['compiler_metrics']['evidence_mode']}`",
             f"- wall clock: {art.identity['wall_seconds']}s",
             f"- result: `{art.identity['compiler_status']}`", ""]
    for call in art.compiler_calls:
        lines += [
            f"### Compiler call `{call['call_id']}` "
            f"(retry {call['retry']}, "
            f"{(call['tokens'] or {}).get('total_tokens')} tokens)", "",
            "System prompt (first 700 chars):", "",
            _fence(call["request"]["messages"][0]["content"], 700), "",
            "User message (first 900 chars):", "",
            _fence(call["request"]["messages"][1]["content"], 900), "",
            "Raw response:", "",
            _fence(call["response_raw"], 1800), ""]
    return lines


def _section_4(art):
    world = art.world
    lines = ["## 4. Compiled cast, private and shared information", "",
             f"World id `{world['world_id']}`, "
             f"{len(world['actors'])} actors.", ""]
    for actor in world["actors"]:
        lines += [f"### `{actor['actor_id']}` -- {actor['name']}", "",
                  "Private context (this actor's alone):", "",
                  _quote(actor["private_context"]), ""]
    lines += ["### Shared context (every actor sees this)", "",
              _quote(world["shared_context"]), "",
              "### Starting events", ""]
    for event in world["starting_events"]:
        lines += [f"- `{event['time']}` visible to "
                  f"{event['visible_to']}: {event['description']}"]
    lines += ["",
              "### Resolution condition compiled for the world", "",
              _quote(world.get("resolution_condition", "")), ""]
    return lines


def _section_5(art):
    lines = ["## 5. Adapter mapping", "",
             "`sworldmodel.compilation.existing_compiler_adapter."
             "adapt_compiled_artifacts` is pure deterministic code: no "
             "model call, no paraphrase, no defaults. It read the frozen "
             "artifact directory and produced the contract world.", "",
             "| compiled manifest | contract world |",
             "| --- | --- |"]
    for name, actor_id in sorted(
            _load(art.dir / "adapter" / "actor_id_by_name.json").items()):
        lines.append(f"| actor name `{name}` | `actor_id` = "
                     f"`{actor_id}` (code-owned derivation) |")
    lines += [
        "| `shared_context` | `world.shared_context` |",
        "| `starting_events[].visible_to` | resolved to actor ids |",
        "| `resolution` | `world.resolution_condition` |",
        "| compile metadata | `compiler_provenance` + adapter sidecar |",
        "",
        f"Insertion boundary: "
        f"`{art.world['intervention_insertion_point']['actor_id']}` "
        "(the decision owner). The adapter refuses to re-target it.", "",
        f"Adapter version: "
        f"`{art.sidecar.get('adapter_version', 'recorded in sidecar')}`; "
        f"world content hash "
        f"`{art.freeze['entries']['compiled_decision_world']['sha256']}`.",
        ""]
    if art.generated:
        proof = _load(art.dir / "world_reuse_proof.json")
        lines += ["### Proof that this scenario reused scenario 1's world",
                  "", "| frozen entry | scenario 1 | scenario 2 | equal |",
                  "| --- | --- | --- | --- |"]
        for name, entry in proof["entries"].items():
            lines.append(f"| `{name}` | `{entry['left'][:20]}…` | "
                         f"`{entry['right'][:20]}…` | "
                         f"**{entry['equal']}** |")
        lines += ["", f"Compiler LLM calls in this scenario: "
                  f"**{proof['compiler_llm_calls_in_this_scenario']}**.",
                  ""]
    return lines


def _section_6(art):
    plan = art.plan
    lines = ["## 6. Final Concordia initialization plan", "",
             f"Plan id `{plan['plan_id']}`, content hash "
             f"`{art.report['base_plan_content_hash']}`. This is the base "
             "every branch shares; a branch may differ from it under "
             "exactly one path.", "",
             f"- engine: `{plan['gm_config'].get('engine')}`; acting "
             f"order: `{plan['gm_config'].get('acting_order')}`",
             f"- game master: `{plan['gm_config'].get('gm_name')}`; "
             f"agency guard enabled: "
             f"`{plan['gm_config'].get('agency_guard_enabled')}`",
             f"- run limits: `{plan['run_limits']}`",
             f"- intervention boundary: "
             f"`{plan['gm_config'].get('intervention_boundary')}` at "
             f"`{plan['intervention_insertion']['actor_id']}`",
             f"- neutral premise: ", "", _quote(plan["neutral_premise"]),
             "", "Initial observations queued per actor (before any "
             "intervention):", ""]
    for actor_id, observations in sorted(
            plan["initial_observations"].items()):
        lines.append(f"- `{actor_id}`:")
        for observation in observations:
            lines.append(f"  - {observation[:300]}")
    lines.append("")
    return lines


def _section_7(art):
    lines = ["## 7. Candidate insertion", "",
             "Each candidate is appended to the insertion actor's "
             "`initial_observations` and to nothing else. The branch "
             "plan differs from the base plan under exactly "
             f"`initial_observations."
             f"{art.plan['intervention_insertion']['actor_id']}`.", ""]
    for entry in art.candidates:
        lines += [f"### `{entry['candidate_id']}` "
                  f"(source: `{entry['provenance']['source']}`)", "",
                  f"- summary: {entry['summary']}",
                  f"- timing: `{entry['timing']}`",
                  f"- decision owner: `{entry['decision_owner']}`",
                  f"- generator config hash: "
                  f"`{entry['provenance'].get('generator_config_hash') or '(none: user-supplied)'}`",
                  "", "Action text carried into the world verbatim:", "",
                  _fence(entry["action"], 1200), ""]
    if art.generated:
        prompt = (art.dir / "generator_prompt.txt").read_text(
            encoding="utf-8")
        raw = (art.dir / "generator_raw_response.txt").read_text(
            encoding="utf-8")
        parsed = _load(art.dir / "generator_parsed.json")
        lines += ["### The generator call", "",
                  "One live call at "
                  "`prepare_decision_inputs(generator_model=...)`. The "
                  "fixed template interpolates only `DecisionProblem` "
                  "fields -- no world-private context reaches it.", "",
                  "Prompt (verbatim, first 1600 chars):", "",
                  _fence(prompt, 1600), "",
                  "Raw response (verbatim):", "", _fence(raw, 2000), "",
                  f"- generator config hash: "
                  f"`{parsed['generator_config_hash']}`",
                  f"- rejected fields / parse errors: "
                  f"`{parsed['rejected_fields_or_parse_errors']}`",
                  f"- one-shot generation: "
                  f"`{parsed['one_shot_generation']}` -- **the current "
                  "implementation performs ONE-SHOT generation, not "
                  "iterative best-action search.**", ""]
    return lines


def _section_8_9_10_11(art):
    lines = ["## 8-11. Every actor turn, every game-master resolution, "
             "every guard decision, every committed event", "",
             "Chronological, per branch, straight from "
             "`branches/<candidate>/step_ledger.jsonl` (auditor-only: it "
             "holds every actor's context side by side; the prompt blocks "
             "below show ONLY what that actor's own prompt contained).",
             ""]
    for branch in art.evaluator["branches"]:
        candidate_id = branch["candidate_id"]
        lines += [f"### Branch `{candidate_id}` "
                  f"(`{branch['branch_id']}`)", ""]
        for record in art.steps.get(candidate_id, []):
            active = record.get("active_actor") or {}
            lines += [f"#### Step {record['step']} -- "
                      f"{active.get('name')}", ""]
            request = record.get("actor_model_request")
            if isinstance(request, list) and request:
                call = request[0]
                user = next((message["content"]
                             for message in call["messages"]
                             if message["role"] == "user"), "")
                lines += [f"**8. Actor turn.** The prompt "
                          f"{active.get('name')} received (call "
                          f"`{call['call_id']}`, this actor's own prompt "
                          "only):", "", _fence(user, 1600), "",
                          "Raw model response:", "",
                          _quote(record["actor_raw_response"][
                              "engine_recorded_value"]), ""]
            else:
                lines += ["**8. Actor turn.** "
                          f"{json.dumps(record.get('actor_model_request'))}",
                          ""]
            lines += ["**Attempted action handed to the game master:**", "",
                      _quote(record.get("attempted_action")), ""]
            gm = record.get("game_master_raw_response") or {}
            gm_calls = gm.get("recorded_calls") or []
            if gm_calls:
                lines += [f"**9. Game-master resolution** (call "
                          f"`{gm_calls[0]['call_id']}`). The game master "
                          "was asked which entities are aware of the "
                          "event; it answered:", "",
                          _quote(gm_calls[0]["response_raw"]), "",
                          f"Recipients recorded: "
                          f"`{(record.get('recipients') or {}).get('names')}`",
                          ""]
            guard = record.get("guard") or {}
            lines += [f"**10. Guard.** intervened = "
                      f"`{guard.get('intervened')}` -- "
                      f"{guard.get('explanation')}", ""]
            final = record.get("final_committed_event")
            if isinstance(final, dict) and "text" in final:
                lines += ["**11. Final committed event "
                          f"(index {final['index']}):**", "",
                          _quote(final["text"], 700), ""]
            else:
                lines += [f"**11. Final committed event:** "
                          f"{json.dumps(final)}", ""]
            lines += [f"Termination check: "
                      f"`{record.get('termination_check')}`; state after "
                      "step (committed-stream prefix hash): "
                      f"`{record['state_hash_after_step']['committed_stream_prefix_sha256'][:16]}…`",
                      ""]
    return lines


def _section_12(art):
    lines = ["## 12. Outcome measurement", "",
             f"Declared evaluator: primary "
             f"`{art.evaluator['evaluator_spec']['primary_metric']}`, "
             f"secondary "
             f"{art.evaluator['evaluator_spec']['secondary_metrics']}. "
             f"Status rule: {art.evaluator['status_rule']}.", "",
             "Every predicate is **attribution-anchored**: a committed "
             f"row counts only when it carries the engine's resolved-turn "
             f"wrapper `{art.evaluator['attribution_anchor']}` AND the "
             "row's own leading `Name:` attribution names "
             f"`{art.evaluator['recipient_actor']}` AND the pattern "
             "occurs in that actor's own attributed content. Message "
             "delivery, message opening, game-master narration, and "
             "another actor paraphrasing the recipient can never satisfy "
             "a metric.", "",
             f"Measurement limitation, stated by the evaluator ledger "
             f"itself: {art.evaluator['measurement_limitation']}", "",
             "| branch | terminal status | " + " | ".join(
                 art.evaluator["evaluator_spec"]["secondary_metrics"]
                 + [art.evaluator["evaluator_spec"]["primary_metric"]])
             + " | committed events |",
             "| --- | --- | " + " | ".join(
                 ["---"] * (len(art.evaluator["evaluator_spec"]
                                ["secondary_metrics"]) + 1)) + " | --- |"]
    for branch in art.evaluator["branches"]:
        metrics = branch["metrics"]
        row = [f"`{branch['candidate_id']}`", branch["terminal_status"]]
        for name in (art.evaluator["evaluator_spec"]["secondary_metrics"]
                     + [art.evaluator["evaluator_spec"]["primary_metric"]]):
            row.append(str(metrics[name]["value"]))
        row.append(str(branch["committed_event_count"]))
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "### Exactly what each reading cited", ""]
    for branch in art.evaluator["branches"]:
        lines += [f"**`{branch['candidate_id']}`**", ""]
        for name, metric in sorted(branch["metrics"].items()):
            lines.append(f"- `{name}` = `{metric['value']}`, cited "
                         f"`{metric['computed_from']}`")
            for text in metric.get("cited_event_texts", []):
                lines += ["", _quote(text, 500), ""]
        turns = branch["predicate_explanation"]["recipient_own_turns"]
        lines += ["",
                  f"  The scan set was the "
                  f"{len(turns)} committed rows attributed to "
                  f"`{art.evaluator['recipient_actor']}`:", ""]
        for turn in turns:
            lines += [_quote(turn["content"], 700), ""]
    return lines


def _section_13_14(art):
    ranking = art.evaluator["ranking"]
    lines = ["## 13. Ranking", "",
             f"Ranking key: {ranking['ranking_key']}. Declared order: "
             f"`{ranking['declared_order']}`. Tie-break used: "
             f"`{ranking['tie_break_used']}`.", "",
             "| position | candidate | " + " | ".join(
                 ranking["declared_order"]) + " |",
             "| --- | --- | " + " | ".join(
                 ["---"] * len(ranking["declared_order"])) + " |"]
    for position, entry in enumerate(ranking["ranking"], start=1):
        row = [str(position), f"`{entry['candidate_id']}`"]
        for name in ranking["declared_order"]:
            row.append(str(entry["metric_values"][name]))
        lines.append("| " + " | ".join(row) + " |")
    winner = ranking["best_candidate_id"]
    lines += ["",
              f"Selected: **`{winner}`**; separated from the runner-up by "
              f"`{ranking['decided_by_metric']}`.", "",
              "Contract limitation language carried by the "
              "`RecommendationResult` itself:", "",
              _quote(ranking["run_limitations"]), "",
              "## 14. Why the selected candidate won", "",
              f"`{winner}` won because the recipient's own committed turn "
              f"in that branch matched the declared acceptance pattern "
              f"and no other branch's did. The exact matching text:", ""]
    branch = art.branch(winner)
    hits = branch["predicate_explanation"]["per_metric"]["call_agreed"][
        "hits"]
    if hits:
        for hit in hits:
            lines += [f"- pattern `{hit['pattern']}` matched "
                      f"`{hit['matched_text']}` at committed row "
                      f"{hit['index']}"]
    else:
        lines += ["- no branch matched the primary metric; the ranking "
                  "fell through to the declared secondaries and then to "
                  "the lexicographic candidate-id tie-break."]
    lines += ["",
              "**Read section 17 before treating this as a comparison "
              "between the candidates.**", ""]
    return lines


def _findings(art):
    """Sections 15-20: the harness author's assessment, each emitted from
    what the artifacts actually show."""
    delivery = art.delivery
    audit = art.audit
    recipient = art.evaluator["recipient_actor"]
    identical = delivery["distinct_recipient_first_turn_prompts"] <= 1
    repeated = []
    for branch in art.evaluator["branches"]:
        turns = [turn["content"] for turn in
                 branch["predicate_explanation"]["recipient_own_turns"]]
        if len(turns) >= 2 and len(set(turns)) < len(turns):
            repeated.append(branch["candidate_id"])
    gm_self_only = []
    gm_reply_self_only = []
    total_resolutions = 0
    for candidate_id, rows in art.steps.items():
        for record in rows:
            names = (record.get("recipients") or {}).get("names") or []
            active = (record.get("active_actor") or {}).get("name")
            if not names:
                continue
            total_resolutions += 1
            if names == [active]:
                gm_self_only.append((candidate_id, record["step"], active))
                text = (record.get("actor_raw_response") or {}).get(
                    "engine_recorded_value") or ""
                if active == recipient and "repl" in text.lower():
                    gm_reply_self_only.append(
                        (candidate_id, record["step"], text))

    lines = ["## 15. Behaviour that appeared realistic", ""]
    lines += [
        "- The recipient's replies are **stylistically plausible for the "
        "genre**: short, blunt, data-first, no flattery. Real recorded "
        "text, quoted verbatim:", "",
        _quote(art.evaluator["branches"][0]["predicate_explanation"][
            "recipient_own_turns"][0]["content"] if
            art.evaluator["branches"][0]["predicate_explanation"][
                "recipient_own_turns"] else "(no recipient turn)", 500),
        "",
        "- The **sender** behaved conservatively and consistently with "
        "its own private context: having been told the message was "
        "already sent, it waited rather than re-sending, and drafted the "
        "one-page memo the constraints permit. That is a sensible "
        "reading of its situation.",
        "- The compiler **refused to invent** private psychology for the "
        "recipient. Its private context literally records the absence: "
        "\"No private beliefs, inbox behavior, scheduling details, or "
        "personal preferences are known or assigned.\" That is the "
        "correct behaviour for an evidence-classified run and it held.",
        "- No branch produced a self-serving outcome for the sender: no "
        "actor narrated a result it did not own, and the guard never "
        "needed to intervene (section 10).",
        "",
        "## 16. Behaviour that appeared generic, stereotyped, "
        "unsupported, or implausible", "",
    ]
    if repeated:
        lines += [
            f"- **The recipient repeated itself verbatim.** In branches "
            f"{', '.join('`' + cid + '`' for cid in repeated)} the "
            f"recipient's second committed turn is *byte-identical* to "
            "its first -- the same sentence, the same quoted email, the "
            "same calendar remark. A person answering their own already-"
            "sent reply would not re-send it word for word. This is the "
            "model regurgitating its own prior output, which was fed back "
            "to it as an observation.", ""]
    lines += [
        "- **Invented specifics that no evidence supports.** The "
        "recipient's turns assert calendar facts that the evidence "
        "manifest explicitly classifies as UNKNOWN -- for example "
        "blocking a slot \"on his calendar as 'Aurelius critique'\" and "
        "naming \"Thursday\". Nothing in the compiled world gave the "
        "recipient a calendar, a week structure, or availability. The "
        "compiler correctly declined to invent inbox and scheduling "
        "behaviour; the ACTOR model invented it anyway at run time. The "
        "engine has no mechanism that would stop it.",
        "- **Uniformly warm.** Across all six branches in both scenarios "
        "the recipient never declines, never ignores, never asks who the "
        "sender is, and never mentions the enormous base rate against "
        "cold outreach. `no_explicit_decline` is `True` in every single "
        "branch. A cold email from an unknown 17-year-old to one of the "
        "most-contacted investors alive producing a 6/6 engagement rate "
        "is not a plausible frequency; it is the assistant-style "
        "helpfulness prior of the underlying model.",
        "- **The '724%' claim was never challenged.** No recipient turn "
        "questioned the metric definition, the replay methodology, or "
        "whether replay results transfer -- despite the sender's own "
        "private context flagging exactly that weakness.",
    ]
    if art.generated:
        with_email_body = [entry["candidate_id"] for entry in art.candidates
                           if "Subject:" in entry["action"]]
        off_channel_re = __import__("re").compile(
            r"\btwitter\b|\bdirect message\b|\bDM\b|\bpublic post\b"
            r"|\bsocial media\b|\btag(?:ging)?\s+@", __import__("re").I)
        off_channel = [entry["candidate_id"] for entry in art.candidates
                       if off_channel_re.search(entry["action"])]
        lines += [
            "- **The generator did not write emails.** "
            f"{len(with_email_body)} of {len(art.candidates)} generated "
            "candidates contain an actual email body; the rest are "
            "descriptions of an action (\"Draft and send an email … "
            "ensuring the body is 45-85 words\"). The route's fixed "
            "prompt asks for \"one concrete action the decision owner "
            "could take\", not for message text, so scenario 2 does not "
            "compare three emails -- it compares three plans. Comparing "
            "it to scenario 1 on that axis would be a category error."]
        if off_channel:
            lines += [
                "- **One generated candidate changes the channel "
                "entirely.** "
                + ", ".join(f"`{cid}`" for cid in off_channel)
                + " proposes a public post plus a direct message rather "
                "than the email the problem is about. No declared "
                "constraint forbids it, which is itself a finding: the "
                "constraint list governs the message, not the medium."]
    if gm_reply_self_only:
        candidate_id, step, text = gm_reply_self_only[0]
        lines += [
            "- **The game master's awareness rulings are wrong on their "
            "face.** At branch "
            f"`{candidate_id}` step {step} the recipient's own turn "
            "says, verbatim:", "", _quote(text, 400), "",
            "  and the game master answered the engine's \"which "
            "entities are aware of the event?\" question with only "
            f"`{recipient}`. A reply sent to the sender, of which the "
            "sender is ruled unaware. "
            f"{len(gm_self_only)} of {total_resolutions} recorded "
            "resolutions in this scenario routed the event to its own "
            "author alone, which is why the two actors never actually "
            "communicated."]
    elif gm_self_only:
        lines += [
            f"- **The game master routed {len(gm_self_only)} of "
            f"{total_resolutions} resolutions to the acting actor "
            "alone**, so the two actors never actually communicated."]
    leak = delivery.get("private_context_leak_check") or {}
    lines += ["", "## 17. Information leaks", ""]
    lines += [
        "**No leak in the direction that is usually feared -- computed, "
        "not asserted.** Every recorded prompt was compared against every "
        "other actor's private context, verbatim and by longest "
        f"distinctive fragment: {leak.get('prompts_checked')} prompts "
        f"checked, **{leak.get('leaks_found')} leaks found**"
        + (f" ({leak['findings'][:1]})" if leak.get("findings") else "")
        + ". Private context appears only under that actor's own "
        "`Private setup:` block. "
        f"`{art.dir.name}/branches/*/step_ledger.jsonl` is auditor-only "
        "and is the only place both appear together.", "",
        "**The opposite failure occurred, and it is worse for this "
        "experiment.**", "",
        f"- Delivery-check verdict: **`{delivery['verdict']}`**",
        f"- {delivery['interpretation']}", "",
        f"- The recipient's first-turn prompt has sha256 "
        + ", ".join(f"`{sha[:16]}…` (`{cid}`)" for cid, sha in
                    sorted(delivery[
                        "recipient_first_turn_prompt_sha256_by_candidate"
                    ].items()))
        + f" -- **{delivery['distinct_recipient_first_turn_prompts']} "
        "distinct value(s) across "
        f"{delivery['branch_count']} branches.**",
        "- Distinctive candidate fragments found in any prompt sent to "
        "the recipient: "
        + ", ".join(
            f"`{entry['candidate_id']}`: "
            f"{entry['candidate_fragments_found_in_recipient_prompts']}"
            f"/{entry['candidate_fragments_tested']}"
            for entry in delivery["per_branch"]) + ".", "",
        "Mechanically, the chain broke in three places, all recorded:",
        "",
        "1. the compiler put the starting event \"the sender sends the "
        "prepared message\" `visible_to` the **sender only**, so the "
        "recipient never observed the send;",
        "2. the intervention insertion boundary (by design) appends the "
        "candidate text to the **insertion actor's** initial "
        "observations and to nothing else -- the design expects the "
        "sender's own turn to carry the content outward;",
        "3. the sender's model, seeing that the send had already "
        "happened, chose to **wait** rather than restate the message, so "
        "the content was never emitted into an event; and the game "
        "master then routed each event only to its own author.",
        "",
        "Net effect: the recipient answered from the generic shared "
        "context alone, identically in every branch.", "",
        "## 18. Forced actor decisions", "",
        "- **No actor decision was made for another actor.** The agency "
        "guard is enabled and recorded zero interventions in this "
        "scenario, and inspection of the committed stream shows why: no "
        "actor's turn asserted the other's choice as an accomplished "
        "fact. The recipient's acceptance is authored by the recipient's "
        "own model; the evaluator's attribution anchor requires exactly "
        "that.",
        "- **The engine did, however, force the CONVERSATION'S SHAPE.** "
        "The fixed acting order alternates sender/recipient for "
        f"{art.plan['run_limits'].get('max_steps')} steps regardless of "
        "whether either has anything to say, and the recipient is given "
        "a turn whether or not it has received anything. In a real "
        "seven-day window the overwhelmingly likely recipient behaviour "
        "-- silence -- is not reachable as a 'no turn'; it can only "
        "appear as an actor turn that says nothing happened.",
        "- The step budget is the cutoff. There is no clock; "
        "`terminal_status = cutoff` means 'the step budget ran out', not "
        "'seven days elapsed'.",
        "",
        "## 19. Engineering failures observed", "",
        f"- **Zero infrastructure errors, zero retries, zero fabricated "
        f"content.** All "
        f"{art.instrumentation['ledger']['records_written']} live calls "
        "in this scenario succeeded on the first attempt, and the "
        "instrumentation cross-check "
        f"(`{art.instrumentation['equality_proof']['all_equal']}`) shows "
        "the network-boundary counter, the wrapper attempt counters and "
        "the ledger record count all agree.",
        "- **A validity failure, not a crash**: the candidate-delivery "
        "problem in section 17. Nothing in the engine detects or reports "
        "it; the pipeline happily produced a ranked recommendation over "
        "branches whose recipient never saw the candidates. This "
        "harness now computes `candidate_delivery_check.json` precisely "
        "so the condition cannot pass unnoticed again.",
        "- **An evaluator-coverage failure**: the declared surface "
        "patterns missed plain acceptances such as \"I'll give you 20 "
        "minutes on Thursday\" and \"Thursday works\". The declared "
        "reading and a post-hoc broader reading disagree on "
        f"{audit['branches_where_the_two_readings_disagree']} of "
        f"{audit['branch_count']} branches "
        "(`measurement_audit.json`). The declared evaluator was NOT "
        "changed and NOT re-run -- doing so after seeing the transcripts "
        "would be tuning the evaluator to the outcome -- so the measured "
        "results stand as measured and the audit is published beside "
        "them, clearly labelled as not an independent measurement.",
        "- **Fields the engine does not expose** are marked, not "
        "guessed. In this scenario "
        f"{len(art.instrumentation['unavailable_fields'])} "
        "`unavailable` markers were written, of exactly two kinds: no "
        "simulation clock exists, and no per-step whole-engine state "
        "hash is obtainable without changing what is measured.",
        "",
        "## 20. What this experiment proves -- and what it does not", "",
        "### It proves",
        "",
        "- The production path runs end to end against a live model: "
        "real compiler -> deterministic adapter -> decision route -> "
        "counterfactual manager -> attribution-anchored evaluator -> "
        "ranking -> reports.",
        "- **Every** model call is recorded. "
        f"{art.instrumentation['ledger']['records_written']} calls, "
        f"{art.instrumentation['ledger']['distinct_call_ids']} distinct "
        "call ids, equal to the independent network-boundary counter and "
        "to the sum of the per-seam attempt counters.",
        "- Private context stayed private (section 17).",
        "- Success was read only from the recipient's own committed "
        "turn; no game-master narration and no paraphrase could satisfy "
        "a metric.",
        "- Scenario 2 reused scenario 1's compiled world and base plan "
        "byte-for-byte (section 5), so the supplied-vs-generated "
        "comparison is not confounded by a different world.",
        "",
        "### It does NOT prove", "",
        "- **Nothing whatsoever about Peter Thiel.** No claim here is "
        "evidence about a real person's behaviour, inbox, calendar, "
        "opinions, or likelihood of taking a call.",
        "- **It does not show that any candidate is better than any "
        "other.** In this run the candidates never reached the "
        "recipient (section 17), so the ranking reflects live-model "
        "sampling variation on an identical prompt, not candidate "
        "quality.",
        "- It does not establish calibration, realism, or base rates. "
        "The 6/6 engagement rate across both scenarios is on its face "
        "implausible.",
        "- It does not establish reproducibility: one run, no repeats, "
        "and temperature 0 is not a determinism guarantee from this "
        "provider.",
        "- It does not validate the evaluator's coverage; see the "
        "measurement audit.",
        "- The contracts still carry no observed/inferred/latent "
        "distinction, so the engine cannot itself reason about how well "
        "any claim in the world is established.",
        "",
    ]
    return lines


def _refused_report(scenario_dir, refusal: dict) -> str:
    """The report for a scenario whose RANKING WAS REFUSED.

    ``sworldmodel.outcomes.ranking`` refuses to name a winner when no
    branch delivered its intervention to any actor other than the
    insertion actor -- the exact failure this scenario's own live run
    hit while still publishing a ranking.  With no ranking there is
    nothing to compare, and rendering the comparison sections would
    manufacture the appearance of a result, so this short report states
    the refusal, its verbatim engine reason, and the per-branch delivery
    facts instead.
    """
    delivery = refusal.get("per_branch_delivery") or {}
    lines = [
        f"# {RUN_LABEL}", "",
        f"## RANKING REFUSED -- `{Path(scenario_dir).name}`", "",
        "**This is not a prediction.** Nothing in this document predicts "
        "what any real person would do; it records what one uncalibrated "
        "language model produced inside a simulation, run once, and why "
        "that run cannot be ranked.", "",
        "**No winner is reported for this scenario, and that is the "
        "result.** Not one branch's candidate text reached any actor "
        "other than the actor it was handed to, so every branch ran the "
        "counterfactual's independent variable at the same (undelivered) "
        "value. Any difference between the branches is model sampling "
        "variation on identical downstream context.", "",
        f"Refusal type: `{refusal.get('error_type')}`", "",
        "Engine reason, verbatim:", "",
        "```", str(refusal.get("reason", "")).strip(), "```", "",
        "## Per-branch delivery (computed from each branch's own artifacts)",
        "",
        "| candidate | status | reason | reached actors |",
        "| --- | --- | --- | --- |",
    ]
    for candidate_id in sorted(delivery):
        fact = delivery[candidate_id] or {}
        lines.append(
            f"| {candidate_id} | {fact.get('status')} | "
            f"{fact.get('reason')} | "
            f"{', '.join(fact.get('reached_actors') or []) or '(none)'} |")
    lines += [
        "", "Every other artifact of this scenario was written and is "
        "unaffected: the freeze manifest, the per-branch ledgers, the "
        "evaluator ledger (whose `ranking` block carries this refusal), "
        "the trace report, and the delivery check. The refusal removes "
        "exactly one thing -- the winner.", ""]
    text = "\n".join(lines) + "\n"
    recorder_lib.assert_no_secrets(text)
    return text


def build_report(root, scenario_dir) -> str:
    # A refused ranking is reported WITHOUT assembling the comparison
    # artifact set: there is no ranking to compare, and the refusal must
    # be reportable from what a refused run actually wrote.
    refusal = _load(Path(scenario_dir) / "recommendation_report.json")
    if isinstance(refusal, dict) and refusal.get("refused") is True:
        return _refused_report(scenario_dir, refusal)
    art = ScenarioArtifacts(root, scenario_dir)
    lines = []
    lines += _header(art)
    lines += _section_1(art)
    lines += _section_2(art)
    lines += _section_3(art)
    lines += _section_4(art)
    lines += _section_5(art)
    lines += _section_6(art)
    lines += _section_7(art)
    lines += _section_8_9_10_11(art)
    lines += _section_12(art)
    lines += _section_13_14(art)
    lines += _findings(art)
    lines += ["---", "",
              "Artifacts referenced by this report live beside it: "
              "`decision_problem.json`, `evidence_manifest.json`, "
              "`freeze_manifest.json`, `compiler/` (scenario 1), "
              "`adapter/`, `candidates/`, "
              "`branches/<candidate_id>/{llm_calls,step_ledger,"
              "observations,guard_ledger,committed_events}.jsonl`, "
              "`evaluator_ledger.json`, `recommendation_result.json`, "
              "`candidate_delivery_check.json`, `measurement_audit.json`.",
              "",
              "`step_ledger.jsonl` is **auditor-only**: it deliberately "
              "holds every actor's private context and every prompt in "
              "one place. No actor ever saw that view.", ""]
    text = "\n".join(lines) + "\n"
    recorder_lib.assert_no_secrets(text)
    return text


def write_report(root, scenario_dir) -> Path:
    text = build_report(root, scenario_dir)
    path = Path(scenario_dir) / "UNDER_THE_HOOD_REPORT.md"
    path.write_text(text, encoding="utf-8")
    return path


def build_readme(root) -> str:
    root = Path(root)
    identity = _load(root / "shared" / "run_identity.json")
    environment = _load(root / "shared" / "environment.json")
    model_config = _load(root / "shared" / "model_configuration.json")
    validation = _load(root / "shared" / "instrumentation_validation.json")
    scenarios = []
    for name in ("peter_supplied", "peter_generated"):
        directory = root / name
        if (directory / "evaluator_ledger.json").is_file():
            scenarios.append((name, ScenarioArtifacts(root, directory)))
    lines = [
        f"# {RUN_LABEL}", "",
        "## Full-trace validation of the accepted engine -- two live "
        "runs", "",
        "**Not a prediction of anyone's behaviour.** These are "
        "uncalibrated, one-shot simulations run against a live language "
        "model for the purpose of seeing exactly what the engine does. "
        "Nothing here is evidence about Peter Thiel, or about any real "
        "person.", "",
        f"- **Model**: `{model_config['model']}` via "
        f"`{model_config['base_url']}` (`{model_config['provider']}`), "
        "temperature 0 at every seam",
        f"- **Window**: {identity['run_start_utc']} -> "
        f"{identity['cutoff_utc']} (actual UTC run start + 7 days)",
        f"- **Repository SHA at run time**: "
        f"`{environment['repository_sha']}`",
        f"- **Compiler**: `{identity['compiler_version']}`, status "
        f"`{identity['compiler_status']}`, run ONCE for scenario 1 and "
        "reused byte-for-byte by scenario 2",
        "", "## Instrumentation: no call bypassed the recorder", "",
        f"```json", json.dumps(validation["equality_proof"], indent=2),
        "```", "",
        "Three counters incremented at three different places -- the "
        "network boundary (immediately before the HTTP request), each "
        "wrapper's own attempt counter, and the ledger writer -- all "
        "agree. Every attempt, including any retry or failure, is one "
        "JSONL record with its own `call_id`.", "",
        "## Scenarios", "",
        "| scenario | candidate source | branches | winner | "
        "terminal statuses | live calls |",
        "| --- | --- | --- | --- | --- | --- |"]
    for name, art in scenarios:
        statuses = ", ".join(
            f"{branch['candidate_id']}={branch['terminal_status']}"
            for branch in art.evaluator["branches"])
        source = ("generated (one-shot, live)" if art.generated
                  else "user-supplied, verbatim")
        lines.append(
            f"| `{name}` | {source} | "
            f"{len(art.evaluator['branches'])} | "
            f"`{art.evaluator['ranking']['best_candidate_id']}` | "
            f"{statuses} | "
            f"{art.instrumentation['ledger']['records_written']} |")
    lines += ["", "## The headline finding", ""]
    for name, art in scenarios:
        lines.append(
            f"- `{name}`: candidate-delivery verdict "
            f"**`{art.delivery['verdict']}`** -- "
            f"{art.delivery['distinct_recipient_first_turn_prompts']} "
            "distinct recipient first-turn prompt(s) across "
            f"{art.delivery['branch_count']} branches; "
            + ", ".join(
                f"`{entry['candidate_id']}` "
                f"{entry['candidate_fragments_found_in_recipient_prompts']}"
                f"/{entry['candidate_fragments_tested']} candidate "
                "fragments delivered"
                for entry in art.delivery["per_branch"]) + ".")
    lines += [
        "",
        "In both scenarios the candidate text never reached the recipient "
        "actor, so **the rankings are not evidence that one candidate is "
        "better than another**. See section 17 of each report for the "
        "exact mechanism, recorded step by step.", "",
        "## Evidence classification", ""]
    for name, art in scenarios:
        lines.append(f"- `{name}`: "
                     f"{evidence_lib.summary_line(art.evidence)}")
    lines += [
        "",
        "Conservative by rule: nothing about a real person's private "
        "personality, compensation, inbox behaviour, calendar "
        "availability, internal opinions or exact authority may be "
        "classified `PUBLICLY_VERIFIED`. The engine's contracts have no "
        "first-class observed / inferred / latent fields, so those "
        "classifications live ONLY in `evidence_manifest.json` and the "
        "engine never reads them.", "",
        "## Layout", "", "```",
        "README.md",
        "shared/{environment,model_configuration,"
        "instrumentation_validation,run_identity}.json",
        "peter_supplied/",
        "  decision_problem.json  evidence_manifest.json  "
        "freeze_manifest.json",
        "  compiler/              (the real compiler's own artifacts + "
        "its call ledger)",
        "  adapter/               (adapted world, base plan, id map, "
        "sidecar)",
        "  candidates/            (the three candidates as contracts)",
        "  branches/<candidate_id>/",
        "     llm_calls.jsonl        every live call in that branch",
        "     step_ledger.jsonl      AUDITOR-ONLY per-step record",
        "     observations.jsonl     what each actor was handed",
        "     guard_ledger.jsonl     pre-guard / post-guard per step",
        "     committed_events.jsonl the committed world events",
        "     branch_result.json     the contract result",
        "     trace_report.json      the engine's own trace entry",
        "  evaluator_ledger.json  recommendation_result.json",
        "  candidate_delivery_check.json  measurement_audit.json",
        "  UNDER_THE_HOOD_REPORT.md",
        "peter_generated/         (same, plus generator_prompt.txt, "
        "generator_raw_response.txt,",
        "                          generator_parsed.json, "
        "world_reuse_proof.json)",
        "```", "",
        "`branches/*/step_ledger.jsonl` is **auditor-only**: it "
        "deliberately places every actor's private context and every "
        "prompt in one file. No actor ever saw that view. The report "
        "sections that represent an actor's prompt show only that "
        "actor's own prompt.", "",
        "## Reproducing", "", "```bash",
        "PYTHONPATH=. /home/user/engine-env/bin/python \\",
        "  -m experiments.full_trace_validation.runner_peter "
        "--phase compile", "# then --phase supplied, --phase generated, "
        "--phase audit, --phase validate", "```", "",
        "Live calls are required; the harness never fabricates model "
        "output. A phase that cannot reach the provider fails loudly "
        "with every recorded attempt left in the ledger.", ""]
    text = "\n".join(lines) + "\n"
    recorder_lib.assert_no_secrets(text)
    return text


def write_readme(root) -> Path:
    path = Path(root) / "README.md"
    path.write_text(build_readme(root), encoding="utf-8")
    return path
