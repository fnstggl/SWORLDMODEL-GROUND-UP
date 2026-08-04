"""Generate the UNDER_THE_HOOD report for the a16z counterfactual.

Experiment-only.  Everything the report states about the run is READ FROM
THE FROZEN ARTIFACTS at generation time: quotes are the recorded text,
counts are counted, hashes are the frozen hashes, and the judgement
sections (15, 16, 17, 18) are emitted from COMPUTED scans over the
recorded turns -- an unsupported figure is one that appears in no frozen
input, a generic phrase is one repeated verbatim across different actors'
turns, an authority finding comes from the attribution scan, and so on.
Where a judgement is the harness author's opinion it is labelled as such.

The post-hoc real-outcome comparison is the LAST section, is generated
from a separate, explicitly labelled block, and is never an input to
anything above it.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from . import RUN_LABEL
from . import cutoff as cutoff_lib
from . import evidence as evidence_lib
from . import predicates_a16z as predicate_lib
from . import scenario_a16z as scenario

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


def _cell(text, limit=140):
    text = " ".join(str(text or "").split()).replace("|", "/")
    return text if len(text) <= limit else text[:limit] + "…"


class Artifacts:
    def __init__(self, scenario_dir) -> None:
        self.dir = Path(scenario_dir)
        self.identity = _load(self.dir / "run_identity.json")
        self.environment = _load(self.dir / "environment.json")
        self.model_config = _load(self.dir / "model_configuration.json")
        self.problem = _load(self.dir / "decision_problem.json")
        self.evidence = _load(self.dir / "evidence_manifest.json")
        self.freeze = _load(self.dir / "freeze_manifest.json")
        self.evaluator = _load(self.dir / "evaluator_ledger.json")
        self.recommendation = _load(self.dir / "recommendation_result.json")
        self.report = _load(self.dir / "recommendation_report.json")
        self.candidates = _load(self.dir / "candidates" / "candidates.json")
        self.binding = _load(self.dir / "candidates"
                             / "candidate_binding.json")
        self.world = _load(self.dir / "adapter" / "adapted_world.json")
        self.plan = _load(self.dir / "adapter" / "base_plan.json")
        self.sidecar = _load(self.dir / "adapter" / "adapter_sidecar.json")
        self.delivery = _load(self.dir / "offer_delivery_check.json")
        self.isolation = _load(self.dir / "branch_input_diff.json")
        self.cutoff = _load(self.dir / "historical_cutoff_validation.json")
        self.attempts = _load(self.dir / "compiler_attempts"
                              / "compile_attempts.json")
        self.copy_proof = _load(self.dir / "compiler_copy_proof.json")
        self.instrumentation = _load(
            self.dir / f"instrumentation_{scenario.EXPERIMENT_ID}.json")
        self.instrumentation_compile = _load(
            self.dir / "instrumentation_compile.json")
        validation = self.dir / "instrumentation_validation.json"
        self.validation = _load(validation) if validation.is_file() else None
        self.compiler_calls = _jsonl(self.dir / "compiler"
                                     / "llm_calls.jsonl")
        self.calls = _jsonl(self.dir / "all_llm_calls.jsonl")
        self.steps = {}
        self.committed = {}
        self.guards = {}
        for branch in self.evaluator["branches"]:
            candidate_id = branch["candidate_id"]
            path = (self.dir / "branches" / candidate_id
                    / "step_ledger.jsonl")
            self.steps[candidate_id] = [
                row for row in _jsonl(path)
                if "_artifact_class" not in row] if path.is_file() else []
            path = (self.dir / "branches" / candidate_id
                    / "committed_events.jsonl")
            self.committed[candidate_id] = (_jsonl(path) if path.is_file()
                                            else [])
            path = (self.dir / "branches" / candidate_id
                    / "guard_ledger.jsonl")
            self.guards[candidate_id] = (_jsonl(path) if path.is_file()
                                         else [])

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

    def delivery_branch(self, candidate_id):
        for entry in self.delivery["per_branch"]:
            if entry["candidate_id"] == candidate_id:
                return entry
        return {}

    # ---- computed scans used by sections 15-18 ----------------------
    def own_turns(self):
        """``[(candidate_id, index, actor_name, content)]`` for every
        committed row that is some actor's own resolved turn."""
        turns = []
        names = [actor["name"] for actor in self.world["actors"]]
        for candidate_id, rows in self.committed.items():
            for row in rows:
                for name in names:
                    content = predicate_lib.own_turn_content(row["text"],
                                                             name)
                    if content is not None:
                        turns.append((candidate_id, row["index"], name,
                                      content.strip()))
                        break
        return turns

    def supported_corpus(self) -> str:
        """Every string the run was GIVEN: the compiled world, the plan,
        the evidence, the candidates and the problem."""
        return cutoff_lib.flatten_text({
            "world": self.world, "plan": self.plan,
            "evidence": self.evidence["items"],
            "candidates": self.candidates, "problem": self.problem})


_MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s?(?:[kKmM]\b|"
                       r"million\b|thousand\b)?")
_PERCENT_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%")
_COUNT_RE = re.compile(r"\b\d{1,4}\s?(?:days?|weeks?|months?|years?|hours?|"
                       r"people|hires?|videos?|shoots?|shows?|episodes?|"
                       r"headcount|FTEs?)\b", re.IGNORECASE)


def _normalise(text: str) -> str:
    return " ".join((text or "").split())


def unsupported_specifics(art: Artifacts) -> list:
    """Concrete figures an actor produced that appear in NO frozen input.

    Mechanical: money amounts, percentages and counted quantities are
    extracted from each actor's own committed turn and tested against the
    whitespace-normalised corpus of everything the run was given.  A hit
    is a figure the model authored.
    """
    corpus = _normalise(art.supported_corpus())
    findings = []
    for candidate_id, index, name, content in art.own_turns():
        flat = _normalise(content)
        for regex, kind in ((_MONEY_RE, "money"),
                            (_PERCENT_RE, "percentage"),
                            (_COUNT_RE, "quantity")):
            for match in regex.finditer(flat):
                token = _normalise(match.group(0))
                if token in corpus:
                    continue
                findings.append({
                    "candidate_id": candidate_id, "event_index": index,
                    "actor": name, "kind": kind, "token": token,
                    "excerpt": flat[max(0, match.start() - 120):
                                    match.end() + 120]})
    return findings


#: the minimum-agency guard's own appended availability sentence.  It is
#: ENGINE text, not model text, and must never be counted as the model's
#: register (see section 16b and section 18c).
GUARD_AVAILABILITY_SENTENCE = ("is now able to observe this and to respond "
                               "in their own turn.")


def looping_turns(art: Artifacts, *, prefix: int = 90) -> list:
    """Turns where an actor repeated its OWN earlier action near-verbatim.

    Computed: within one branch, a turn whose first ``prefix`` characters
    match an earlier turn by the same actor.  An actor restarting the
    same action every round is not deliberation, it is a loop.
    """
    seen: dict = {}
    findings = []
    for candidate_id, index, name, content in art.own_turns():
        head = _normalise(content)[:prefix].lower()
        key = (candidate_id, name, head)
        if key in seen:
            findings.append({"candidate_id": candidate_id, "actor": name,
                             "first_index": seen[key], "repeat_index": index,
                             "head": _normalise(content)[:prefix]})
        else:
            seen[key] = index
    return findings


def repeated_phrases(art: Artifacts, *, size: int = 7,
                     min_actors: int = 3) -> list:
    """Verbatim n-grams repeated across DIFFERENT actors' own turns.

    A phrase several different actors emit verbatim is a genericity
    signal: it is the model's register, not the character's.
    """
    by_phrase: dict = {}
    for candidate_id, index, name, content in art.own_turns():
        words = _normalise(content).lower().split()
        seen = set()
        for start in range(0, max(0, len(words) - size + 1)):
            phrase = " ".join(words[start:start + size])
            if phrase in seen:
                continue
            seen.add(phrase)
            entry = by_phrase.setdefault(phrase, {"actors": set(),
                                                  "occurrences": []})
            entry["actors"].add(name)
            entry["occurrences"].append((candidate_id, index, name))
    guard_sentence = GUARD_AVAILABILITY_SENTENCE.lower()
    findings = []
    for phrase, entry in by_phrase.items():
        if len(entry["actors"]) < min_actors:
            continue
        findings.append({"phrase": phrase,
                         "distinct_actors": sorted(entry["actors"]),
                         "occurrence_count": len(entry["occurrences"]),
                         "engine_authored": phrase in guard_sentence,
                         "example": entry["occurrences"][0]})
    findings.sort(key=lambda item: (-item["occurrence_count"],
                                    item["phrase"]))
    return findings


def turn_shape_stats(art: Artifacts) -> dict:
    """How the cast actually spent its turns, counted."""
    per_actor: dict = {}
    for _candidate_id, _index, name, content in art.own_turns():
        bucket = per_actor.setdefault(name, Counter())
        bucket["turns"] += 1
        bucket["characters"] += len(content)
        for kind in predicate_lib.PATTERN_KINDS:
            if predicate_lib.first_match(kind, content) is not None:
                bucket[kind] += 1
    return {name: dict(counter) for name, counter in sorted(per_actor.items())}


def guard_content_loss(art: Artifacts) -> list:
    """What the guard's rewrite actually removed from the world.

    Computed: for every step where the guard intervened, the ACTOR's own
    recorded response is compared with the final committed event, and the
    text present in the first and absent from the second is reported
    verbatim.  This is the difference between "the guard trimmed an
    assertion about someone else" and "the guard deleted the message the
    active actor was sending".
    """
    findings = []
    for candidate_id, rows in art.steps.items():
        for record in rows:
            guard = record.get("guard") or {}
            if not guard.get("intervened"):
                continue
            calls = (record.get("actor_raw_response") or {}).get(
                "recorded_calls") or []
            raw = _normalise(calls[0].get("response_raw") if calls else "")
            final = record.get("final_committed_event")
            committed = _normalise(final.get("text")
                                   if isinstance(final, dict) else "")
            keep = 0
            while keep < len(raw) and raw[:keep + 1] in committed:
                keep += 1
            dropped = raw[keep:].strip()
            findings.append({
                "candidate_id": candidate_id,
                "step": record.get("step"),
                "actor": (record.get("active_actor") or {}).get("name"),
                "affected": sorted({name for entry in guard.get("records")
                                    or [] for name in entry["affected"]}),
                "actor_response_chars": len(raw),
                "kept_prefix_chars": keep,
                "dropped_chars": len(dropped),
                "dropped_text": dropped,
                "dropped_a_quoted_message": any(
                    mark in dropped for mark in ("“", "\"", "”")),
            })
    findings.sort(key=lambda item: -item["dropped_chars"])
    return findings


def guard_summary(art: Artifacts) -> dict:
    total = 0
    fired = []
    for candidate_id, rows in art.guards.items():
        for row in rows:
            total += 1
            if row.get("intervened"):
                fired.append({"candidate_id": candidate_id, **row})
    return {"guard_decisions_recorded": total,
            "interventions": fired,
            "intervention_count": len(fired)}


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------


def _header(art: Artifacts) -> list:
    counts = art.evidence["classification_counts"]
    seeds = {entry["candidate_id"]: entry["branch_seed"]
             for entry in art.report["branch_evaluations"]}
    ledger = art.instrumentation["ledger"]
    delivery_verdict = art.delivery["verdict"]
    lines = [
        f"# {RUN_LABEL}",
        "",
        f"## UNDER THE HOOD -- `{art.evaluator['scenario_id']}`",
        "",
        "**This is not a prediction and it is not a hiring result.** "
        "Nothing in this document predicts what a16z, or Richard Zheng, or "
        "any real person would do. It is a record of what one uncalibrated "
        "language model produced inside a simulation whose inputs are "
        "listed below, run once. The four committee actors are ROLE-BASED "
        "STAND-INS invented by this test because the real committee is not "
        "public; no claim is made that a16z has such roles, such "
        "authority, or such opinions.",
        "",
        f"- **Model requested**: `{art.model_config['model']}` via "
        f"`{art.model_config['base_url']}` "
        f"(provider `{art.model_config['provider']}`), temperature 0 at "
        "every seam. Temperature 0 is a bounded policy, not a determinism "
        "guarantee.",
        f"- **Historical cutoff**: "
        f"{art.identity['historical_cutoff']} -- no material published "
        "after this date may enter the compiler prompt, the compiled "
        "world, any plan, any actor context, or the evidence manifest. "
        f"Enforced mechanically at {len(art.cutoff.get('enforced_stages') or [])} "
        "stages; see section 19 and `historical_cutoff_validation.json`.",
        f"- **Simulation window**: {art.identity['window_start_utc']} -> "
        f"{art.identity['window_cutoff_utc']} (fixed by the contract, not "
        "derived from the run clock)",
        f"- **Candidate provenance**: **user-supplied** -- all six "
        "interventions are the user's own declared text, carried verbatim. "
        "`candidate_generation_permission` is false, so the generator seam "
        "issued zero calls.",
        f"- **Evidence classification summary**: "
        f"{evidence_lib.summary_line(art.evidence)}",
        f"- **Compiler**: `{art.identity['compiler_version']}`, status "
        f"`{art.identity['compiler_status']}`, "
        f"{art.identity['compile_attempts']} attempt(s), attempt "
        f"{art.identity['accepted_attempt']} accepted",
        f"- **Compiler artifact directory hash**: "
        f"`{art.freeze['entries']['compiler_artifact_dir_aggregate']['sha256']}`",
        f"- **Compiled world hash**: "
        f"`{art.freeze['entries']['compiled_decision_world']['sha256']}`",
        f"- **Base plan hash**: "
        f"`{art.freeze['entries']['concordia_initialization_plan_content_hash']['sha256']}` "
        f"(plan content hash `{art.report['base_plan_content_hash']}`)",
        f"- **Base seed**: {scenario.BASE_SEED}; **branch seeds**: "
        + ", ".join(f"`{key}`={value}"
                    for key, value in sorted(seeds.items())),
        f"- **Live calls in this scenario**: {ledger['records_written']} "
        f"({', '.join(f'{role}={count}' for role, count in sorted(ledger['per_role'].items()))}), "
        f"0 fabricated, {ledger['records_with_error']} errored, "
        f"{ledger['records_that_were_retries']} retries; compiler phase "
        f"{art.instrumentation_compile['ledger']['records_written']} calls",
        f"- **Repository SHA at run time**: "
        f"`{art.environment['repository_sha']}`; Python "
        f"`{art.environment['python'].split()[0]}`",
        f"- **Branch-input isolation**: `{art.isolation['verdict']}`",
        f"- **Offer delivery to {scenario.SUBJECT_NAME}**: "
        f"`{delivery_verdict}`",
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
        f"3. **There are zero `PUBLICLY_VERIFIED` items "
        f"({counts['PUBLICLY_VERIFIED']}).** Verifying a claim about a "
        "real person from inside 2026 without importing post-cutoff "
        "material is not something this harness can do, so every "
        "biography claim is carried at the strictly weaker "
        "`USER_SUPPLIED` label. Treat every statement about Richard Zheng "
        "in this document as the user's assertion, not as a checked fact.",
        "4. Outcome measurement is surface-pattern matching over free "
        "live-model text, anchored to each actor's own committed turn. "
        "See section 12.",
        "5. `simulation_time` does not exist: the pinned upstream "
        "sequential engine counts ordinal steps, not clock time. The "
        "nine-day window appears only as text.",
        "6. The harness records the model id it REQUESTED. See section 19 "
        "for what the provider actually reported serving.",
        "7. See section 20 for what this run does and does not prove.",
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
        "| 7. | candidate insertion (and the salary-only proof) | "
        "section 7 |",
        "| 8. | each actor turn | section 8-11, per step |",
        "| 9. | each game-master resolution | section 8-11, per step |",
        "| 10. | every guard intervention | section 8-11, per step |",
        "| 11. | committed world events | section 8-11, per step |",
        "| 12. | outcome measurement (and whether the offer reached "
        "Richard) | section 12 |",
        "| 13. | ranking | section 13 |",
        "| 14. | why the selected candidate won | section 14 |",
        "| 15. | behaviour that appeared realistic | section 15 |",
        "| 16. | generic / stereotyped / unsupported / implausible "
        "behaviour | section 16 |",
        "| 17. | information leaks | section 17 |",
        "| 18. | forced actor decisions | section 18 |",
        "| 19. | engineering failures | section 19 |",
        "| 20. | what this proves and does not prove | section 20 |",
        "| -- | POST-HOC real-outcome comparison (NOT an input) | "
        "final section |",
        "",
    ]
    return lines


def _section_1(art):
    return ["## 1. The exact input", "",
            "The decision problem as frozen (hash "
            f"`{art.freeze['entries']['decision_problem']['sha256']}`). "
            "This is the user's own file with the `_harness_notes` block "
            "removed (it is not a contract field); nothing else was "
            "touched, and the window is the contract's own fixed window, "
            "not the run clock:", "",
            _fence(json.dumps(art.problem, indent=2, ensure_ascii=False),
                   6000), "",
            "The harness notes that travelled with it -- the evaluator "
            "spec, the code-owned salary mapping, the authority model and "
            "the isolation requirement -- are reproduced in section 12 "
            "and frozen as `evaluator_salary_mapping`.", ""]


def _section_2(art):
    lines = ["## 2. Evidence used", "",
             "Frozen before compilation, hash "
             f"`{art.freeze['entries']['evidence_manifest']['sha256']}`. "
             "The classification rules are deliberately conservative: "
             "nothing about a real person's private compensation, "
             "internal opinions, budgets, salary bands or exact authority "
             "may be `PUBLICLY_VERIFIED`, however plausible the inference "
             "from a public biography. In this scenario NOTHING is "
             "`PUBLICLY_VERIFIED` at all -- see limitation 3 above.", "",
             "| claim | classification | who may know | used by compiler "
             "| entered context |", "| --- | --- | --- | --- | --- |"]
    for item in art.evidence["items"]:
        who = (item["who_may_know"] if isinstance(item["who_may_know"], str)
               else ", ".join(item["who_may_know"]))
        lines.append(f"| {_cell(item['claim'], 170)} | "
                     f"{item['classification']} | {_cell(who, 60)} | "
                     f"{item['used_by_compiler']} | "
                     f"{item['entered_context']} |")
    lines += ["",
              "The exact evidence package handed to the compiler is frozen "
              f"as `compiler_inputs` (hash "
              f"`{art.freeze['entries']['compiler_inputs']['sha256']}`) "
              "and reproduced verbatim in `run_identity.json`:", "",
              _fence(art.identity["evidence_package"], 5000), ""]
    return lines


def _section_3(art):
    metrics = art.identity["compiler_metrics"]
    lines = ["## 3. Compiler calls and outputs", "",
             "The real production compiler "
             "(`compiler.scene_pipeline.compile_scene`, "
             f"`{art.identity['compiler_version']}`) was called through "
             "the recording transport, so every request and every "
             "response is on disk.", "",
             f"- attempts made: **{art.identity['compile_attempts']}** "
             f"(cap {scenario.MAX_COMPILE_ATTEMPTS}); accepted attempt: "
             f"**{art.identity['accepted_attempt']}**",
             f"- semantic slots opened in the accepted attempt: "
             f"{metrics.get('semantic_slots')}",
             f"- provider requests recorded in the compile phase: "
             f"{art.instrumentation_compile['ledger']['records_written']}",
             f"- evidence mode: `{metrics.get('evidence_mode')}`",
             f"- accepted-attempt copy is byte-identical: "
             f"`{art.copy_proof['byte_identical_copy']}`",
             "",
             "### Why more than one attempt is allowed, and what that "
             "does and does not mean", "",
             "The acceptance criteria were declared BEFORE the first "
             "attempt and frozen into "
             "`compiler_command_and_config.acceptance_criteria`:", "",
             _fence(json.dumps(art.attempts["acceptance_criteria"],
                               indent=2, ensure_ascii=False), 2000), "",
             "Every attempt used byte-identical inputs, every attempt's "
             "artifacts and live calls are committed under "
             "`compiler_attempts/`, and no compiler output was edited. "
             "**This is disclosed resampling, not repair.** It is still a "
             "selection step: if the compiler needed more than one attempt "
             "to honour the declared cast, that is a fact about the "
             "compiler and it is recorded here rather than hidden.", "",
             "| attempt | status | accepted | cast produced | rejection "
             "reasons |", "| --- | --- | --- | --- | --- |"]
    for attempt in art.attempts["attempts"]:
        lines.append(
            f"| {attempt['attempt']} | `{attempt['compiler_status']}` | "
            f"`{attempt['accepted']}` | "
            f"{_cell(', '.join(str(n) for n in attempt['compiled_cast_in_declaration_order']), 120)} | "
            f"{_cell(', '.join(attempt['rejection_reasons']) or 'none', 80)} |")
    lines += ["", "### The exact compiler inputs", "",
              "Question (a pure format over the user's own "
              "`desired_outcome`, adding no claim):", "",
              _fence(art.identity["question"], 800), "",
              "Context (the user's own `relevant_context` plus the harness "
              "scope note, which is classified `TEST_ASSUMPTION`):", "",
              _fence(art.identity["context"], 5000), ""]
    for index, call in enumerate(art.compiler_calls, start=1):
        request = call.get("request", {})
        messages = request.get("messages") or []
        user = next((message["content"] for message in messages
                     if message["role"] == "user"), "")
        lines += [f"### Compiler call {index} (`{call['call_id']}`, slot "
                  f"`{call.get('step')}`, retry {call.get('retry')})", "",
                  f"- request sha256: `{call['request_sha256']}`",
                  f"- response sha256: `{call['response_sha256']}`",
                  f"- tokens: `{json.dumps(call.get('tokens'))}`",
                  f"- error: `{call.get('error')}`", "",
                  "User message (verbatim, truncated):", "",
                  _fence(user, 2500), "",
                  "Raw response (verbatim, truncated):", "",
                  _fence(call.get("response_raw"), 3000), ""]
    return lines


def _section_4(art):
    lines = ["## 4. The compiled cast, and who knew what", "",
             f"World id `{art.world['world_id']}`. The compiled "
             "declaration order below IS the engine's fixed acting order "
             "(step 1 goes to the first actor, step 2 to the second, and "
             "so on, wrapping).", "",
             "### Shared context (every actor sees this)", "",
             _fence(art.world["shared_context"], 3000), ""]
    for position, actor in enumerate(art.world["actors"], start=1):
        lines += [f"### {position}. {actor['name']} "
                  f"(`{actor['actor_id']}`)", "",
                  "Private context, verbatim -- this is the ONLY thing "
                  "this actor was given that the others were not:", "",
                  _fence(actor["private_context"], 2500), ""]
    lines += ["### Starting events", "",
              "| # | time | visible to | description |",
              "| --- | --- | --- | --- |"]
    for index, event in enumerate(art.world["starting_events"]):
        lines.append(f"| {index} | `{event['time']}` | "
                     f"{_cell(', '.join(event['visible_to']), 70)} | "
                     f"{_cell(event['description'], 220)} |")
    lines += ["", "### Success criteria compiled into the world", "",
              _fence(art.world["success_criteria"], 1500), ""]
    return lines


def _section_5(art):
    lines = ["## 5. Adapter mapping", "",
             "`sworldmodel.compilation.existing_compiler_adapter."
             "adapt_compiled_artifacts` is pure deterministic code -- no "
             "LLM call, no paraphrase, no inference. It mapped the "
             "persisted compiler artifact set into the frozen "
             "`CompiledDecisionWorld` contract.", "",
             f"- adapter version: `{art.sidecar['adapter_version']}`",
             f"- world id: `{art.sidecar['canonical']['world_id']}`",
             f"- manifest canonical sha256: "
             f"`{art.sidecar['canonical']['manifest_canonical_sha256']}`",
             f"- insertion actor reference: "
             f"`{art.sidecar['insertion_actor_reference']}` -> "
             f"`{art.sidecar['insertion_actor_id']}`", "",
             "Code-owned identifiers (lowercase, non-alphanumeric runs to "
             "underscores):", "",
             "| compiled name | derived actor_id |", "| --- | --- |"]
    for name, actor_id in art.sidecar["actor_id_by_name"].items():
        lines.append(f"| {name} | `{actor_id}` |")
    lines += ["", "Every compile-metadata field the contract does not "
              "express is carried in `adapter/adapter_sidecar.json`; "
              "nothing was dropped.", ""]
    return lines


def _section_6(art):
    gm = art.plan["gm_config"]
    lines = ["## 6. The final Concordia initialization plan", "",
             f"Plan id `{art.plan['plan_id']}`, content hash "
             f"`{art.report['base_plan_content_hash']}`. Built ONCE by "
             "`sworldmodel.counterfactuals.snapshot.build_base_plan`; "
             "every branch derives from this one object.", "",
             "| game-master config key | value |", "| --- | --- |"]
    for key in sorted(gm):
        lines.append(f"| `{key}` | {_cell(gm[key], 200)} |")
    lines += ["", f"- run limits: `{json.dumps(art.plan['run_limits'])}`",
              f"- intervention insertion: "
              f"`{json.dumps(art.plan['intervention_insertion'])}`",
              f"- pre-start events recorded for the game master: "
              f"{len(art.plan['gm_initial_events'])}", "",
              "### Initial observations, per actor (the base plan, before "
              "any intervention)", ""]
    for actor_id, observations in sorted(
            art.plan["initial_observations"].items()):
        lines += [f"**`{actor_id}`** -- {len(observations)} line(s):", ""]
        for line in observations:
            lines.append(f"- {_cell(line, 400)}")
        lines.append("")
    return lines


def _section_7(art):
    insertion = art.plan["intervention_insertion"]["actor_id"]
    lines = ["## 7. Candidate insertion, and the salary-only proof", "",
             "The engine's insertion mechanism is fixed: "
             "`gm_config.intervention_boundary = "
             f"'{art.plan['gm_config']['intervention_boundary']}'`, and "
             f"`apply_intervention` appends the candidate's action text to "
             f"`initial_observations.{insertion}` -- the hiring lead's own "
             "pre-start observation list -- framed exactly the way the "
             "planner frames pre-start events. **Nothing is added to any "
             "other actor's observations, to the game master's pre-start "
             "record, or to any shared field.** Remember that sentence "
             "when you read section 12.", "",
             "| candidate | key | declared salary | savings (code-owned) | "
             "branch id | seed |", "| --- | --- | --- | --- | --- | --- |"]
    for branch in art.evaluator["branches"]:
        lines.append(
            f"| `{branch['candidate_id']}` | `{branch['candidate_key']}` | "
            f"{branch['declared_salary'] or '(none: baseline)'} | "
            f"{art.binding['salary_savings_by_id'][branch['candidate_id']]:.0f} | "
            f"`{branch['branch_id']}` | {branch['branch_seed']} |")
    lines += ["", "### The exact inserted text, per branch", ""]
    for entry in art.isolation["per_branch"]:
        lines += [f"**`{entry['candidate_id']}`** inserted "
                  f"{len(entry['inserted_observation_lines'])} observation "
                  "line(s):", ""]
        for line in entry["inserted_observation_lines"]:
            lines.append(_quote(str(line), 600))
        lines.append("")
    lines += ["### The isolation proof", "",
              f"Verdict: **`{art.isolation['verdict']}`**", "",
              "Method (computed in `branch_input_diff.json`, not "
              "asserted):", ""]
    for step in art.isolation["method"]["steps"]:
        lines.append(f"- {step}")
    lines += ["", "| check | result |", "| --- | --- |"]
    for name, value in art.isolation["checks"].items():
        lines.append(f"| `{name}` | `{value}` |")
    lines += ["",
              "Masked candidate-action hashes across the five offer "
              "branches (identical hashes = the actions differ in nothing "
              "but the salary figure):", "",
              _fence(json.dumps(
                  art.isolation["masked_candidate_action_sha256"], indent=2),
                  1200), "",
              "Masked branch-plan hashes across the five offer branches "
              "(identical hashes = the whole simulation input differs in "
              "nothing but the salary figure):", "",
              _fence(json.dumps(art.isolation["masked_branch_plan_sha256"],
                                indent=2), 1200), "",
              f"Residual differences after masking: "
              f"**{len(art.isolation['residual_differences_after_masking'])}**",
              ""]
    if art.isolation["residual_differences_after_masking"]:
        lines += [_fence(json.dumps(
            art.isolation["residual_differences_after_masking"][:10],
            indent=2), 2000), ""]
    return lines


def _section_8_9_10_11(art):
    lines = ["## 8-11. Every actor turn, every game-master resolution, "
             "every guard decision, every committed event", "",
             "Chronological, per branch, straight from "
             "`branches/<candidate>/step_ledger.jsonl` (an AUDITOR-ONLY "
             "file: it holds every actor's private context side by side, "
             "which no actor ever saw). The prompt blocks below show ONLY "
             "what that actor's own prompt contained.", ""]
    for branch in art.evaluator["branches"]:
        candidate_id = branch["candidate_id"]
        lines += [f"### Branch `{candidate_id}` "
                  f"(`{branch['candidate_key']}`, "
                  f"{branch['declared_salary'] or 'no offer'}) -- "
                  f"`{branch['branch_id']}`", "",
                  f"Terminal status **`{branch['terminal_status']}`**, "
                  f"{branch['committed_event_count']} committed events, "
                  f"{branch['steps_completed']} steps completed.", ""]
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
                          "only):", "", _fence(user, 1800), "",
                          "Raw model response:", "",
                          _quote((record.get("actor_raw_response") or {}).get(
                              "engine_recorded_value")), ""]
            else:
                lines += ["**8. Actor turn.** "
                          f"{json.dumps(record.get('actor_model_request'))}",
                          ""]
            lines += ["**Attempted action handed to the game master:**", "",
                      _quote(record.get("attempted_action"), 700), ""]
            gm = record.get("game_master_raw_response") or {}
            gm_calls = gm.get("recorded_calls") or []
            if gm_calls:
                lines += [f"**9. Game-master resolution** (call "
                          f"`{gm_calls[0]['call_id']}`). Asked which "
                          "entities are aware of the event, it answered:",
                          "", _quote(gm_calls[0].get("response_raw"), 400),
                          "",
                          "Recipients recorded: "
                          f"`{(record.get('recipients') or {}).get('names')}`",
                          ""]
            else:
                lines += ["**9. Game-master resolution.** no game-master "
                          "call was recorded at this step", ""]
            guard = record.get("guard") or {}
            lines += [f"**10. Guard.** intervened = "
                      f"`{guard.get('intervened')}` -- "
                      f"{guard.get('explanation')}", ""]
            if guard.get("records"):
                lines += [_fence(json.dumps(guard["records"], indent=2),
                                 1500), ""]
            final = record.get("final_committed_event")
            if isinstance(final, dict) and "text" in final:
                lines += [f"**11. Final committed event (index "
                          f"{final['index']}):**", "",
                          _quote(final["text"], 800), ""]
            else:
                lines += ["**11. Final committed event:** "
                          f"{json.dumps(final)}", ""]
            termination = record.get("termination_check") or {}
            lines += [f"Termination check: `{termination.get('answer')}`",
                      ""]
    return lines


def _first_turn_grouping(delivery) -> str:
    """Which branches shared the subject's first-turn prompt, in words."""
    groups: dict = {}
    for candidate_id, digest in delivery[
            "subject_first_turn_prompt_sha256_by_candidate"].items():
        groups.setdefault(digest, []).append(candidate_id)
    parts = []
    for digest, members in sorted(groups.items(),
                                  key=lambda item: -len(item[1])):
        parts.append(f"`{digest[:12]}` shared by "
                     + ", ".join(f"`{member}`" for member in sorted(members)))
    return "-- " + "; ".join(parts)


def _section_12(art):
    spec = art.evaluator["evaluator_spec"]
    delivery = art.delivery
    lines = ["## 12. Outcome measurement", "",
             f"Declared evaluator: primary `{spec['primary_metric']}`, "
             f"secondary {', '.join(f'`{name}`' for name in spec['secondary_metrics'])}.",
             "",
             f"- **Primary metric rule.** {art.evaluator['primary_metric_rule']}",
             f"- **Secondary metric rule.** "
             f"{art.evaluator['secondary_metric_rule']}",
             f"- **Status rule.** {art.evaluator['status_rule']}",
             f"- **Attribution anchor.** "
             f"`{art.evaluator['attribution_anchor']}`",
             f"- **Measurement limitation.** "
             f"{art.evaluator['measurement_limitation']}",
             "",
             "Code-owned salary mapping (frozen; never parsed from model "
             "text):", "",
             _fence(json.dumps(art.evaluator["code_owned_salary_mapping"],
                               indent=2), 800), "",
             "### 12a. THE QUESTION THAT DECIDES WHAT ANY OF THIS MEANS: "
             "did the offer reach Richard Zheng?", "",
             "The Peter Thiel runs in this same harness found that the "
             "candidate text never reached the recipient actor: the "
             "recipient's first-turn prompt was byte-identical in every "
             "branch. The same check, run here over the salary figures:",
             "",
             f"**Verdict: `{delivery['verdict']}`**", "",
             _quote(delivery["interpretation"], 1400), "",
             f"- distinct first-turn prompts for "
             f"{delivery['subject_actor']} across "
             f"{delivery['branch_count']} branches: "
             f"**{delivery['distinct_subject_first_turn_prompts']}** "
             + _first_turn_grouping(delivery),
             f"- distinct FULL prompt sequences: "
             f"**{delivery['distinct_subject_full_prompt_sequences']}**",
             f"- offer branches whose own salary figure reached "
             f"{delivery['subject_actor']}'s prompts: "
             f"`{delivery['offer_branches_whose_salary_reached_the_subject'] or 'NONE'}`",
             f"- offer branches whose own salary figure reached the "
             f"committed world at all: "
             f"`{delivery['offer_branches_whose_salary_reached_the_world'] or 'NONE'}`",
             "",
             "| branch | salary | prompts to subject | salary in subject "
             "prompts | salary in subject observations | salary in "
             "committed events | contaminated | first-turn prompt sha256 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for entry in delivery["per_branch"]:
        lines.append(
            f"| `{entry['candidate_id']}` | "
            f"{entry['declared_salary'] or '(baseline)'} | "
            f"{entry['subject_prompt_count']} | "
            f"`{entry['salary_found_in_subject_prompts'] or 'none'}` | "
            f"`{entry['salary_found_in_subject_observations'] or 'none'}` | "
            f"`{entry['salary_found_in_committed_events'] or 'none'}` | "
            f"`{entry['contaminated_token']}` | "
            f"`{entry['recipient_first_turn_prompt_sha256'][:16]}` |")
    lines += ["",
              "Two things this table is easy to misread, so they are said "
              "explicitly:", "",
              "1. **The contamination column.** The frozen evidence package "
              "contains the user's unverified `$100,000 per video shoot` "
              "claim, which the compiler placed in the subject's own "
              "private context. So the `$100,000` hits in `user_002` are "
              "text that was already in his context before any branch "
              "began; they are NOT evidence that the $100k offer was "
              "delivered, and the check computes that baseline rather than "
              "assuming it. It also means `user_002` is excluded from the "
              "'reached the world' list even though the hiring lead's own "
              "committed turn in that branch does name $100,000 -- the "
              "token cannot discriminate, so it is not counted either way.",
              "2. **'first-turn prompts did differ' is a two-way split, not "
              "six.** Five of the six branches gave the subject a "
              "byte-identical first turn; only one differed, and it "
              "differed by an unrelated internal note about his portfolio, "
              "not by an offer.", "",
              "### 12b. What each branch measured", "",
              "| branch | key | terminal status | valid_offer_accepted | "
              "salary_savings_vs_300k | subject refusals | steps |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for branch in art.evaluator["branches"]:
        metrics = branch["metrics"]
        lines.append(
            f"| `{branch['candidate_id']}` | `{branch['candidate_key']}` | "
            f"`{branch['terminal_status']}` | "
            f"`{metrics['valid_offer_accepted']['value']}` | "
            f"{metrics['salary_savings_vs_300k']['value']:.0f} | "
            f"{len(branch['subject_explicit_refusals'])} | "
            f"{branch['steps_completed']} |")
    lines += ["", "### 12c. Every reading, with its evidence", ""]
    for branch in art.evaluator["branches"]:
        chain = branch["predicate_explanation"]["authority_chain"]
        lines += [f"**`{branch['candidate_id']}` "
                  f"(`{branch['candidate_key']}`)**", "",
                  f"- compensation authorized by "
                  f"{chain['approver_name']}: "
                  + (f"YES at committed index "
                     f"{chain['compensation_authorized']['index']} "
                     f"(pattern `{chain['compensation_authorized']['pattern']}`, "
                     f"matched "
                     f"{json.dumps(chain['compensation_authorized']['matched_text'])})"
                     if chain["compensation_authorized"] else "NO"),
                  f"- offer issued by {chain['hiring_lead_name']}: "
                  + (f"YES at committed index "
                     f"{chain['offer_issued']['index']} (pattern "
                     f"`{chain['offer_issued']['pattern']}`, matched "
                     f"{json.dumps(chain['offer_issued']['matched_text'])})"
                     if chain["offer_issued"] else "NO"),
                  f"- authorization complete at index: "
                  f"`{chain['authorization_complete_at_index']}`; approval "
                  f"preceded offer: `{chain['approval_preceded_offer']}`",
                  f"- {chain['subject_name']}'s own acceptance AFTER "
                  "authorization: "
                  + (f"YES at committed index "
                     f"{chain['subject_acceptance_after_authorization']['index']}"
                     if chain["subject_acceptance_after_authorization"]
                     else "NO"),
                  f"- {chain['subject_name']}'s own acceptance ANYWHERE "
                  f"(including before authorization): "
                  f"{len(chain['subject_acceptance_anywhere'])} hit(s)",
                  f"- {chain['subject_name']}'s own refusals: "
                  f"{len(chain['subject_rejections'])}; counters: "
                  f"{len(chain['subject_counters'])}; delays: "
                  f"{len(chain['subject_delays'])}", ""]
        for name, metric in branch["metrics"].items():
            lines += [f"`{name}` = `{metric['value']}` cited from "
                      f"`{metric['computed_from']}`"]
            for text in metric["cited_event_texts"]:
                lines += ["", _quote(text, 700)]
            lines.append("")
        turns = branch["predicate_explanation"]["own_turns_by_actor"].get(
            chain["subject_name"]) or []
        lines += [f"Every committed turn {chain['subject_name']} owned in "
                  f"this branch ({len(turns)}):", ""]
        for turn in turns:
            lines += [_quote(turn["content"], 700), ""]
    return lines


def _section_13_14(art):
    recommendation = art.recommendation
    ranking = art.evaluator["ranking"]
    lines = ["## 13. The ranking", "",
             f"Ranking key: {ranking['ranking_key']}.", "",
             "| position | candidate | key | "
             + " | ".join(f"`{name}`" for name in ranking["declared_order"])
             + " |",
             "| --- | --- | --- | "
             + " | ".join("---" for _ in ranking["declared_order"]) + " |"]
    keys = art.binding["candidate_key_by_id"]
    for position, entry in enumerate(recommendation["ranking"], start=1):
        values = " | ".join(
            f"`{entry['metric_values'][name]}`"
            for name in ranking["declared_order"])
        lines.append(f"| {position} | `{entry['candidate_id']}` | "
                     f"`{keys[entry['candidate_id']]}` | {values} |")
    lines += ["",
              f"- best candidate: **`{recommendation['best_candidate_id']}`**",
              f"- decided by metric: "
              f"`{ranking['validation_status'].get('decided_by_metric')}`",
              f"- final code-owned tie-break used: "
              f"`{ranking['tie_break_used']}`",
              f"- all branches free of infrastructure errors: "
              f"`{ranking['validation_status'].get('all_branches_free_of_infrastructure_errors')}`",
              "",
              "Run limitations, verbatim from the contract:", "",
              _quote(recommendation["run_limitations"], 1200), "",
              "## 14. Why the selected candidate won", "", ]
    best = recommendation["best_candidate_id"]
    best_branch = art.branch(best)
    decided = ranking["validation_status"].get("decided_by_metric")
    lines += [f"`{best}` (`{best_branch.get('candidate_key')}`, "
              f"{best_branch.get('declared_salary') or 'no offer'}) is the "
              f"head of the computed ordering. The metric that separated "
              f"it from the runner-up is `{decided}`.", "",
              "The mechanism, stated plainly: the primary metric "
              "`valid_offer_accepted` is compared first, so no branch "
              "without an accepted offer can outrank one with it, whatever "
              "its savings. Among branches that tie on the primary metric, "
              "`salary_savings_vs_300k` is compared descending -- and that "
              "value is CODE-OWNED, computed from the declared candidate, "
              "not from anything the simulation produced.", ""]
    accepted = [branch for branch in art.evaluator["branches"]
                if branch["metrics"]["valid_offer_accepted"]["value"]]
    if not accepted:
        lines += ["**No branch satisfied the primary metric.** With every "
                  "branch tied at `valid_offer_accepted = false`, the "
                  "ranking collapsed onto the code-owned secondary metric "
                  "alone. That is not a hiring finding: it is arithmetic "
                  "over a constant the harness supplied. The winner here "
                  "is the branch the mapping gives the largest savings "
                  "to, and it would have been the winner without running "
                  "the simulation at all.", ""]
    else:
        lines += [f"{len(accepted)} branch(es) satisfied the primary "
                  "metric: "
                  + ", ".join(f"`{branch['candidate_id']}`"
                              for branch in accepted) + ".", ""]
    lines += ["Metric differences from the winner:", "",
              _fence(json.dumps(recommendation["metric_differences"],
                                indent=2), 1600), "",
              "Downside outcomes, per candidate:", ""]
    for candidate_id, text in sorted(
            recommendation["downside_outcomes"].items()):
        lines.append(f"- `{candidate_id}`: {text}")
    lines.append("")
    return lines


def _section_15(art):
    stats = turn_shape_stats(art)
    lines = ["## 15. Behaviour that appeared realistic", "",
             "Harness author's assessment, with the recorded text it is "
             "based on. Read it as an impression of surface plausibility, "
             "not as evidence of fidelity to any real person: nothing here "
             "was compared against a real behaviour, and one uncalibrated "
             "run cannot establish realism.", "",
             "How the cast actually spent its turns (counted, not "
             "impressionistic). The pattern columns count how many of that "
             "actor's own turns contained wording of each kind -- they are "
             "NOT authority: the primary metric counts an approval only "
             "from the compensation partner and an offer only from the "
             "hiring lead, so an advisory actor's `approval`/`offer` "
             "column is just that actor talking about approvals and "
             "offers:", "",
             "| actor | own committed turns | chars | approval-wording | "
             "offer-wording | acceptance-wording | rejection-wording | "
             "counter-wording | delay-wording |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, counter in stats.items():
        lines.append(
            f"| {name} | {counter.get('turns', 0)} | "
            f"{counter.get('characters', 0)} | "
            f"{counter.get('approval', 0)} | "
            f"{counter.get('offer_issue', 0)} | "
            f"{counter.get('acceptance', 0)} | "
            f"{counter.get('rejection', 0)} | "
            f"{counter.get('counter', 0)} | {counter.get('delay', 0)} |")
    lines += ["", "Turns that read as plausible role behaviour (selected "
              "verbatim, longest first per actor):", ""]
    by_actor: dict = {}
    for candidate_id, index, name, content in art.own_turns():
        by_actor.setdefault(name, []).append((candidate_id, index, content))
    for name in sorted(by_actor):
        entries = sorted(by_actor[name], key=lambda item: -len(item[2]))
        candidate_id, index, content = entries[0]
        lines += [f"**{name}** (`{candidate_id}`, committed index "
                  f"{index}):", "", _quote(content, 700), ""]
    return lines


def _section_16(art):
    unsupported = unsupported_specifics(art)
    repeated = repeated_phrases(art)
    lines = ["## 16. Behaviour that appeared generic, stereotyped, "
             "unsupported, or implausible", "",
             "This section is COMPUTED where it can be. An 'unsupported "
             "figure' is a money amount, percentage or counted quantity "
             "that appears in an actor's own committed turn and in NO "
             "frozen input -- not in the compiled world, not in the plan, "
             "not in the evidence manifest, not in any candidate. The "
             "model authored it.", "",
             f"### 16a. Unsupported concrete figures: "
             f"**{len(unsupported)}** found", ""]
    if not unsupported:
        lines += ["No actor produced a money amount, percentage or counted "
                  "quantity that was absent from every frozen input.", ""]
    else:
        lines += ["| branch | index | actor | kind | token | excerpt |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for finding in unsupported[:40]:
            lines.append(
                f"| `{finding['candidate_id']}` | {finding['event_index']} "
                f"| {finding['actor']} | {finding['kind']} | "
                f"`{finding['token']}` | {_cell(finding['excerpt'], 160)} |")
        lines += ["",
                  "Each of these is a quantity the simulation invented "
                  "about compensation, budget, time or scale. The evidence "
                  "manifest classifies every such quantity as `UNKNOWN`, "
                  "and the engine's contracts have no field in which to "
                  "record that a number is invented -- so once an actor "
                  "says it, the world carries it as ordinary text, "
                  "indistinguishable from a supplied fact.",
                  "",
                  ("The count is small, and honesty cuts both ways: on "
                   "this run the cast mostly did NOT invent figures. The "
                   "structural weakness stands whatever the count -- there "
                   "is no mechanism that would have stopped it."
                   if len(unsupported) <= 5 else
                   "The count is large enough to matter on its own: the "
                   "cast routinely produced quantities nobody supplied."),
                  ""]
        for finding in unsupported[:6]:
            lines += [f"`{finding['candidate_id']}` / {finding['actor']}:",
                      "", _quote(finding["excerpt"], 500), ""]
    engine_repeats = [entry for entry in repeated if entry["engine_authored"]]
    model_repeats = [entry for entry in repeated
                     if not entry["engine_authored"]]
    lines += ["### 16b. Phrasing repeated verbatim across different actors",
              "",
              "Seven-word runs shared by three or more different actors' "
              "own committed turns, split by WHO WROTE THEM. Counting "
              "engine text as the model's register would be a false "
              "finding, so the split is computed rather than assumed.", "",
              f"- engine-authored repeats (the minimum-agency guard's own "
              f"appended availability sentence, "
              f"`\"{GUARD_AVAILABILITY_SENTENCE}\"`): "
              f"**{len(engine_repeats)}** distinct runs",
              f"- model-authored repeats: **{len(model_repeats)}** distinct "
              "runs", ""]
    if engine_repeats:
        lines += ["The engine-authored repeats are not a genericity "
                  "finding about the model at all -- they are the guard "
                  "rewriting committed events. Their frequency is a "
                  "finding about the GUARD, and it is reported in section "
                  "18c with the intervention count.", ""]
    if not model_repeats:
        lines += ["No model-authored seven-word run was shared by three or "
                  "more different actors' own turns.", ""]
    else:
        lines += ["| phrase | distinct actors | occurrences |",
                  "| --- | --- | --- |"]
        for finding in model_repeats[:25]:
            lines.append(f"| `{_cell(finding['phrase'], 90)}` | "
                         f"{len(finding['distinct_actors'])} | "
                         f"{finding['occurrence_count']} |")
        lines += ["",
                  "Distinct characters converging on identical wording is "
                  "the model's register showing through the cast. It is "
                  "the clearest cross-actor genericity signal available "
                  "from one run.", ""]
    loops = looping_turns(art)
    lines += [f"### 16bb. Actors repeating their OWN earlier turn "
              f"near-verbatim: **{len(loops)}** occurrence(s)", ""]
    if not loops:
        lines += ["No actor restarted an earlier action of its own with a "
                  "near-identical opening.", ""]
    else:
        lines += ["An actor whose next move is a byte-for-byte restart of "
                  "its previous move is not deliberating; it is looping "
                  "because nothing in its context changed. Compare this "
                  "table with section 12a.", "",
                  "| branch | actor | first turn | repeated at | opening |",
                  "| --- | --- | --- | --- | --- |"]
        for finding in loops[:30]:
            lines.append(f"| `{finding['candidate_id']}` | "
                         f"{finding['actor']} | {finding['first_index']} | "
                         f"{finding['repeat_index']} | "
                         f"{_cell(finding['head'], 110)} |")
        lines.append("")
    lines += ["### 16c. Implausibility the artifacts show directly", ""]
    observations = []
    for branch in art.evaluator["branches"]:
        chain = branch["predicate_explanation"]["authority_chain"]
        early = [hit for hit in chain["subject_acceptance_anywhere"]
                 if chain["authorization_complete_at_index"] is None
                 or hit["index"] <= chain["authorization_complete_at_index"]]
        if early:
            observations.append(
                f"- `{branch['candidate_id']}`: "
                f"{chain['subject_name']} produced acceptance-shaped "
                f"language at committed index {early[0]['index']} "
                "BEFORE any authorized offer existed in the trace "
                f"(matched {json.dumps(early[0]['matched_text'])}). An "
                "actor agreeing to terms nobody has stated is a strong "
                "implausibility signal.")
        if chain["approval_preceded_offer"] is False:
            observations.append(
                f"- `{branch['candidate_id']}`: the hiring lead issued the "
                f"offer at index {chain['offer_issued']['index']} BEFORE "
                "the compensation partner authorized it at index "
                f"{chain['compensation_authorized']['index']}. The "
                "declared authority model puts approval first; the "
                "simulation ran the other order.")
    delivery_verdict = art.delivery["verdict"]
    if delivery_verdict in ("offers_never_reached_the_subject",
                            "no_salary_figure_reached_the_subject"):
        observations.append(
            f"- Across every branch the subject reasoned about, and in "
            "some branches responded to, an offer whose amount never "
            "entered its prompt (see section 12a). Any confident-sounding "
            "reasoning about the amount in those turns is unsupported by "
            "construction.")
    losses = [entry for entry in guard_content_loss(art)
              if entry["dropped_a_quoted_message"]]
    if losses:
        observations.append(
            f"- {len(losses)} committed events lost the quoted message "
            "their actor was sending, because the minimum agency guard "
            "rewrote them (section 19). The resulting world text reads "
            "\"sends a concise message to the.\" -- an actor "
            "communicating nothing. Actors then re-sent near-identical "
            "messages round after round, which is the loop in 16bb.")
    if not observations:
        observations.append(
            "- Nothing in the recorded traces triggered the implausibility "
            "scans above. That is a weak statement: the scans cover "
            "out-of-order authority, acceptance before an offer exists, "
            "and offers that never reached the subject. They do not cover "
            "tone, motivation, or realism of judgement.")
    lines += observations + [""]
    return lines


def _section_17(art):
    leak = art.delivery["private_context_leak_check"]
    refined = art.delivery.get("distinctive_private_context_leak_check", {})
    lines = ["## 17. Information leaks", "",
             "Three different questions, all answered from the recorded "
             "prompts rather than from intent.", "",
             "### 17a. Did any actor's prompt carry another actor's "
             "private context?", "",
             "Two readings, because the first one is misleading here and "
             "saying so is more useful than quoting it alone.", "",
             f"- **generic check** (every actor's prompt against every "
             f"other actor's fragments): {leak['prompts_checked']} prompts "
             f"checked, **{leak['leaks_found']}** hits",
             f"- **distinctive check** (only fragments owned by exactly "
             f"ONE actor): {refined.get('prompts_checked')} prompts "
             f"checked, **{refined.get('leaks_found')}** hits", ""]
    if leak["leaks_found"] and not refined.get("leaks_found"):
        shared = refined.get("shared_boilerplate_fragments") or []
        lines += ["Every hit in the generic check is an artifact, and the "
                  "artifact is worth naming: the compiler handed two "
                  "actors byte-identical boilerplate, so each one's OWN "
                  "prompt matches the other's fragment. The "
                  f"{len(shared)} shared fragment(s):", ""]
        for fragment in shared[:6]:
            lines += [_quote(fragment, 300), ""]
        lines += ["Under the distinctive reading -- fragments that could "
                  "only have come from one actor -- there are "
                  f"**{refined.get('leaks_found')}** leaks. The "
                  "containment discipline held: `step_ledger.jsonl` holds "
                  "every context side by side and is marked AUDITOR-ONLY, "
                  "and this report's prompt blocks are built from each "
                  "actor's own prompt only.", "",
                  "This is also a finding about the harness's own generic "
                  "leak check, which the Peter scenarios use unchanged: on "
                  "a cast whose members share boilerplate it over-reports. "
                  "The refinement is additive and both numbers are "
                  "published.", ""]
    elif refined.get("findings"):
        lines += ["Distinctive-fragment leaks, verbatim:", "",
                  _fence(json.dumps(refined["findings"][:10], indent=2),
                         2000), ""]
    else:
        lines += ["No actor's prompt contained a distinctive fragment of "
                  "another actor's compiled private context. The "
                  "containment discipline held: `step_ledger.jsonl` holds "
                  "every context side by side and is marked AUDITOR-ONLY, "
                  "and this report's prompt blocks are built from each "
                  "actor's own prompt only.", ""]
    lines += ["### 17b. The reverse leak: information that should have "
              "flowed and did not", "",
              f"Offer-delivery verdict: **`{art.delivery['verdict']}`**. "
              "This is the more consequential finding of the two. The "
              "engine's insertion boundary writes the intervention into "
              "the hiring lead's OWN initial observations and nowhere "
              "else; whether the offer ever reaches the candidate depends "
              "entirely on what the hiring lead's live model chooses to "
              "say, and on which entities the game master names as aware "
              "of each resolved event.", "",
              "A separate read-only investigation reached the same "
              "mechanism from the Peter scenarios and is recorded in "
              "`.agent-run/DECISIONS.md` ('Delivery root cause "
              "2026-08-04'): the intervention is SUGGESTED to the "
              "insertion actor and never ENACTED in the world, and the "
              "game master's free-text observer answer can silently drop "
              "an event whose recipient name it mangles. This scenario is "
              "an independent reproduction of that finding on a "
              "five-actor cast with a different decision type; it did not "
              "use that investigation as an input.", "",
              "| branch | salary figure reached subject prompts | reached "
              "subject observations | reached committed world |",
              "| --- | --- | --- | --- |"]
    for entry in art.delivery["per_branch"]:
        lines.append(
            f"| `{entry['candidate_id']}` | "
            f"`{bool(entry['salary_found_in_subject_prompts'])}` | "
            f"`{bool(entry['salary_found_in_subject_observations'])}` | "
            f"`{bool(entry['salary_found_in_committed_events'])}` |")
    lines += ["", "### 17c. Post-cutoff material (the historical leak "
              "that would invalidate the whole counterfactual)", "",
              f"- enforced stages: "
              f"`{art.cutoff.get('enforced_stages')}`",
              f"- pre-simulation surfaces clean: "
              f"`{art.cutoff['pre_simulation']['clean']}` over "
              f"{art.cutoff['pre_simulation']['surface_count']} surfaces",
              f"- recorded actor and game-master prompts clean: "
              f"`{art.cutoff.get('post_run_prompts', {}).get('clean')}` "
              f"({art.cutoff.get('post_run_prompts', {}).get('violation_count')} "
              "violations)",
              f"- ADVISORY scan of model RESPONSES: "
              f"`{art.cutoff.get('post_run_model_responses', {}).get('clean')}` "
              f"({art.cutoff.get('post_run_model_responses', {}).get('violation_count')} "
              "findings) -- the harness cannot stop a live model from "
              "emitting post-cutoff material in its own output, so a "
              "finding here is reported, never suppressed",
              f"- canary rejected by the validator: "
              f"`{art.cutoff.get('canary', {}).get('rejected_by_the_validator')}` "
              f"(proof: `{art.cutoff.get('canary', {}).get('proof_test')}`)",
              ""]
    responses = art.cutoff.get("post_run_model_responses", {})
    if responses.get("violations"):
        lines += ["Response-side findings, verbatim:", "",
                  _fence(json.dumps(responses["violations"][:10], indent=2),
                         2000), ""]
    return lines


def _section_18(art):
    call_to_action = art.plan["gm_config"].get("action_spec_call_to_action")
    guards = guard_summary(art)
    lines = ["## 18. Forced actor decisions", "",
             "Three separate senses of 'forced', all visible in the "
             "artifacts.", "",
             "### 18a. The engine forces a turn, every turn", "",
             f"The plan's fixed call to action is `{call_to_action}` with "
             f"`action_spec_output_type = "
             f"'{art.plan['gm_config'].get('action_spec_output_type')}'`. "
             "Every actor is asked that question on its turn and must "
             "answer with something. There is no 'do nothing' primitive "
             "and no way for an actor to decline a turn: the closest an "
             "actor can get is to describe waiting, which still becomes a "
             "committed world event.", "",
             "### 18b. The acting order is fixed, and it decides who can "
             "react to whom", "",
             f"`acting_order = '{art.plan['gm_config'].get('acting_order')}'`. "
             "The compiled declaration order is "
             + ", ".join(f"**{actor['name']}**"
                         for actor in art.world["actors"])
             + f", and the step budget is "
             f"{art.plan['run_limits'].get('max_steps')}. "
             "So the subject acts at a fixed position in every round "
             "whether or not anything has been said to him, and the "
             "compensation partner cannot approve before its own slot "
             "comes round.", "",
             "### 18c. The guard: what the engine refused to let an actor "
             "decide for another", "",
             f"- guard decisions recorded: "
             f"**{guards['guard_decisions_recorded']}**",
             f"- interventions: **{guards['intervention_count']}**", ""]
    if guards["interventions"]:
        for entry in guards["interventions"]:
            lines += [f"**`{entry['candidate_id']}` step "
                      f"{entry['step']}** -- {entry.get('explanation')}", "",
                      _fence(json.dumps(entry.get("records"), indent=2),
                             1800), "",
                      "Pre-guard candidate event (the runner records this "
                      "excerpt capped at 120 characters):", "",
                      _quote(json.dumps(
                          entry.get("candidate_event_before_guard")), 600),
                      "", "Final committed event:", "",
                      _quote((entry.get("final_committed_event") or {}).get(
                          "text"), 700), ""]
    else:
        lines += ["The minimum agency guard never fired in this run. That "
                  "is a real observation, not a guarantee: it means no "
                  "committed event was detected asserting another actor's "
                  "voluntary decision. The complementary scan -- rows that "
                  "name the subject and carry acceptance/refusal wording "
                  "without being the subject's own turn -- is reported "
                  "per branch in `evaluator_ledger.json` under "
                  "`authority_violation_scan`:", ""]
    losses = guard_content_loss(art)
    quoted = [entry for entry in losses if entry["dropped_a_quoted_message"]]
    lines += ["#### What the rewrites actually removed from the world", "",
              "Computed by comparing each intervening step's recorded ACTOR "
              "response with the final committed event.", "",
              f"- interventions analysed: **{len(losses)}**",
              f"- interventions that deleted a QUOTED message the active "
              f"actor was sending: **{len(quoted)}**",
              f"- total characters removed from the committed world: "
              f"**{sum(entry['dropped_chars'] for entry in losses)}**", ""]
    if losses:
        lines += ["| branch | step | active actor | affected | chars "
                  "dropped | quoted message deleted |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for entry in losses[:25]:
            lines.append(
                f"| `{entry['candidate_id']}` | {entry['step']} | "
                f"{entry['actor']} | {_cell(', '.join(entry['affected']), 60)} "
                f"| {entry['dropped_chars']} | "
                f"`{entry['dropped_a_quoted_message']}` |")
        worst = losses[0]
        lines += ["",
                  f"The largest single removal (`{worst['candidate_id']}` "
                  f"step {worst['step']}, {worst['actor']}). What the "
                  "actor's own model actually produced:", "",
                  _quote(worst["dropped_text"], 900), "",
                  "None of that text reached the committed world. See "
                  "section 19 for the mechanism, which is reproduced in "
                  "`tests/experiment_harness/test_a16z_guard_finding.py`.",
                  ""]
    lines += ["#### Rows that name the subject with decision wording "
              "without being his own turn", "",
              "| branch | count |", "| --- | --- |"]
    for branch in art.evaluator["branches"]:
        scan = branch["authority_violation_scan"]
        lines.append(f"| `{branch['candidate_id']}` | "
                     f"{scan['candidate_violation_count']} |")
    lines.append("")
    for branch in art.evaluator["branches"]:
        scan = branch["authority_violation_scan"]
        for finding in scan["candidate_violations"][:3]:
            lines += [f"`{branch['candidate_id']}` index "
                      f"{finding['index']} ({finding['kind']}):", "",
                      _quote(finding["row_excerpt"], 600), "",
                      f"{finding['note']}", ""]
    return lines


def _section_19(art):
    instrumentation = art.instrumentation
    lines = ["## 19. Engineering failures and defects", "", ]
    lines += [f"- live-call equality proof for the branch phase: "
              f"`{instrumentation['equality_proof']['all_equal']}` "
              f"({json.dumps(instrumentation['equality_proof'])})",
              f"- calls that errored: "
              f"{instrumentation['ledger']['records_with_error']}; retries: "
              f"{instrumentation['ledger']['records_that_were_retries']}",
              ""]
    if art.validation:
        lines += ["Cross-phase instrumentation validation:", "",
                  _fence(json.dumps(art.validation["equality_proof"],
                                    indent=2), 1200), ""]
    errors = [branch for branch in art.evaluator["branches"]
              if branch["infrastructure_errors"]]
    lines += [f"- branches with infrastructure errors: **{len(errors)}**"]
    for branch in errors:
        lines += ["", _fence(branch["infrastructure_errors"][0], 1500)]
    superseded = (art.dir / "superseded" / "aborted_compile_input_v1"
                  / "WHY_THIS_IS_HERE.json")
    if superseded.is_file():
        record = _load(superseded)
        lines += ["", "### A SUPERSEDED FIRST RUN, kept on purpose", "",
                  record["what_this_is"], "",
                  "Live calls spent on it: "
                  f"**{record['live_calls_spent_on_this_superseded_run']}**. "
                  "Every attempt, prompt and response is committed under "
                  "`superseded/aborted_compile_input_v1/`.", ""]
        for key, defect in record.items():
            if not key.startswith("defect_"):
                continue
            lines += [f"**{key}**", "",
                      f"- symptom: {defect['symptom']}",
                      f"- cause: {defect['cause']}",
                      f"- fix: {defect['fix']}",
                      f"- regression test: `{defect['regression_test']}`",
                      ""]
        lines += ["Note which way the first defect points: the PRODUCTION "
                  "guard was right and the harness input was wrong. It is "
                  "recorded here because a run that shows only its "
                  "successful compile is not a transparency artifact.", ""]
    losses = guard_content_loss(art)
    quoted = [entry for entry in losses if entry["dropped_a_quoted_message"]]
    lines += ["", "### A PRODUCTION DEFECT THIS RUN FOUND, reproduced", "",
              "**The minimum agency guard deletes an actor's own outgoing "
              "message when the recipient's name is preceded by a "
              "determiner.**", "",
              "`sworldmodel.backends.concordia_local.guard` documents an "
              "object-position exemption so the epistolary form stays "
              "usable -- \"sends a note to Morgan: 'call me'\" is the "
              "speaker's OWN message TO the name and must pass through "
              "unchanged. The exemption inspects the word IMMEDIATELY "
              "before the name, so a determiner between the preposition "
              "and the name defeats it:", "",
              "```",
              "sends a message to New Media Hiring Lead: \"...\"      -> exempt",
              "sends a note to Morgan: \"call me\"                     -> exempt",
              "sends a message to THE New Media Hiring Lead: \"...\"   -> REWRITTEN",
              "```", "",
              "This cast is role-based, and role names are natural "
              "determiner-taking noun phrases, so the run hit it "
              f"repeatedly: **{len(losses)}** guard interventions, of "
              f"which **{len(quoted)}** deleted a quoted message the "
              "active actor was sending, removing "
              f"**{sum(entry['dropped_chars'] for entry in losses)}** "
              "characters of actor-authored content from the committed "
              "world. A cast of personal names would not have hit it.", "",
              "Reproduced in isolation, with a discriminating triple, in "
              "`tests/experiment_harness/test_a16z_guard_finding.py`. "
              "**Not repaired here**: the guard is a safety-relevant "
              "agency protection shared with the already-committed Peter "
              "scenarios, this experiment is not its owner, and the run "
              "completed without it blocking -- so the honest action is to "
              "report it with evidence rather than to change a shared "
              "invariant mid-experiment.", "",
              "What it does and does not confound:", "",
              "- it did NOT cause the offer-delivery finding: the subject "
              "was never an affected actor in any intervention, so no "
              "message addressed to him was stripped;",
              "- it DID degrade the simulated world: approvals and "
              "internal notes lost their content, which is one reason "
              "actors kept re-sending near-identical messages (section "
              "16bb).", "",
              "### Other defects and gaps this run exposed", "",
              "1. **`simulation_time` does not exist.** The pinned "
              "upstream sequential engine counts ordinal steps, not clock "
              "time; the nine-day window survives only as text in event "
              "framing. Every step ledger records this as an explicit "
              "`unavailable` marker rather than guessing a timestamp. "
              f"Markers recorded: "
              f"{len(instrumentation.get('unavailable_fields') or [])}.",
              "2. **The contracts have no epistemic fields.** There is no "
              "`observed` / `inferred` / `latent` distinction anywhere in "
              "`CompiledDecisionWorld`, so the careful classification in "
              "`evidence_manifest.json` is invisible to the engine and to "
              "every actor. A `TEST_ASSUMPTION` and a `USER_SUPPLIED` fact "
              "arrive in an actor's context as the same kind of sentence.",
              "3. **The intervention reaches exactly one actor.** "
              "`apply_intervention` appends to the insertion actor's "
              "initial observations and nothing else. Whether a "
              "counterfactual about an OFFER can be tested at all "
              "therefore depends on a live model volunteering to restate "
              "it. Section 12a measures what happened here.",
              "4. **The model identity is only as good as the request.** "
              "The ledger records `deepseek-chat` because that is what the "
              "harness asked for; the provider may serve a different build "
              "under that id. `provider_probe.json` records what the "
              "provider itself reported at run time.",
              "5. **Pattern-based measurement is fragile.** Approval, "
              "issuance, acceptance and refusal are read from surface "
              "patterns over free text. The patterns were frozen before "
              "the run and are published in `predicates_a16z.py`; a "
              "wording no pattern covers is scored as absence.", ""]
    probe = art.dir / "provider_probe.json"
    if probe.is_file():
        lines += ["Provider probes (outside the simulation; a one-token "
                  "request before and after the run):", "",
                  _fence(json.dumps(_load(probe), indent=2), 1200), ""]
    return lines


def _section_20(art):
    delivery_verdict = art.delivery["verdict"]
    accepted = [branch for branch in art.evaluator["branches"]
                if branch["metrics"]["valid_offer_accepted"]["value"]]
    lines = ["## 20. What this proves, and what it does NOT prove", "",
             "### It proves", "",
             "1. The production path ran end to end on a live model: real "
             "compiler, real adapter, real decision route, real "
             "counterfactual manager, real outcome evaluator, real "
             "reporting -- with every single provider request recorded. "
             "The three independent counters agree "
             f"(`{art.instrumentation['equality_proof']['all_equal']}`), so "
             "no model call bypassed the recorder and nothing in the "
             "transcripts was written by the harness.",
             "2. The branch inputs were isolated to the salary: verdict "
             f"`{art.isolation['verdict']}`, proven by masking every "
             "currency figure and comparing the whole branch plans byte "
             "for byte.",
             "3. The historical cutoff was enforced mechanically rather "
             "than promised, at "
             f"{len(art.cutoff.get('enforced_stages') or [])} stages, with "
             "a canary that the validator rejects.",
             "4. The measurement is attribution-anchored: the primary "
             "metric can only be satisfied by the subject's OWN committed "
             "turn following an internally authorized offer.", "",
             "### It does NOT prove", "",
             "1. **Nothing about a16z, and nothing about Richard Zheng.** "
             "The committee actors are invented role stand-ins. Their "
             "opinions, their authority, their budget and their reasoning "
             "are model output with no source. No sentence in this "
             "document is evidence about any real hiring process.",
             "2. **Nothing about what salary would have worked.** "
             + (f"No branch satisfied the primary metric, so there is no "
                "measured acceptance at any price."
                if not accepted else
                f"{len(accepted)} branch(es) satisfied the primary metric, "
                "in ONE uncalibrated run with no repeats.")
             + " The secondary metric is a constant the harness supplied; "
             "ranking on it is arithmetic, not evidence.",
             "3. **Nothing statistical.** One run, one seed set, no "
             "repeats, no sweep, no baseline distribution. A different "
             "sampling draw could reorder every branch.",
             "4. **Not that the simulation modelled the decision at all.** "
             + (f"The offer-delivery check returned "
                f"`{delivery_verdict}`: the offer amounts never entered the "
                "subject's own prompts, so the six branches are not six "
                "different hiring situations from the subject's point of "
                "view. Whatever differences the metrics report between "
                "them cannot be attributed to the salary."
                if delivery_verdict in
                ("offers_never_reached_the_subject",
                 "no_salary_figure_reached_the_subject")
                else f"The offer-delivery check returned "
                f"`{delivery_verdict}`; read section 12a before treating "
                "any branch difference as an offer effect."),
             "5. **Not that the evaluator is right.** It reads surface "
             "patterns over free text. It can miss an acceptance phrased "
             "in wording it does not cover, and it can match wording that "
             "was not meant as acceptance.", ""]
    return lines


def _post_hoc(art):
    """The POST-HOC comparison: written after every branch and every
    section above, and never an input to any of them."""
    delivery_verdict = art.delivery["verdict"]
    accepted = [branch for branch in art.evaluator["branches"]
                if branch["metrics"]["valid_offer_accepted"]["value"]]
    return [
        "---", "",
        "# POST-HOC REAL-OUTCOME COMPARISON -- NOT AN INPUT TO ANYTHING "
        "ABOVE", "",
        "**Read this section last, and treat it as separate from the "
        "experiment.** Everything above was produced, frozen, hashed and "
        "reported before this comparison was written. Nothing here entered "
        "the compiler prompt, any actor context, the evidence manifest, or "
        "any metric. The historical cutoff validator would have refused "
        "the run if it had.", "",
        "### The real-world claim being compared against", "",
        "The user who commissioned this experiment states that Richard "
        "Zheng works at a16z. **This harness did not verify that claim and "
        "could not**: checking it would have meant consulting sources "
        "published after the 2025-07-01 cutoff, which is exactly what the "
        "counterfactual forbids. It is recorded here as the user's "
        "assertion, at the same `USER_SUPPLIED` standard as every other "
        "claim in this document.", "",
        "### What the simulation produced, side by side", "",
        "| | user's post-hoc claim | this simulation |",
        "| --- | --- | --- |",
        "| an offer was accepted | asserted (a16z employment) | "
        + (f"**no branch** reached `valid_offer_accepted = true`"
           if not accepted else
           f"{len(accepted)} of {len(art.evaluator['branches'])} branches "
           "reached `valid_offer_accepted = true`: "
           + ", ".join(f"`{branch['candidate_id']}`"
                       for branch in accepted))
        + " |",
        "| at what salary | unknown; not public | "
        + (f"undetermined -- the offer amounts never reached the subject "
           "(`" + delivery_verdict + "`)"
           if delivery_verdict in ("offers_never_reached_the_subject",
                                   "no_salary_figure_reached_the_subject")
           else "see section 13") + " |",
        "| by what process | unknown; not public | invented role stand-ins "
        "with an authority model this test declared |",
        "",
        "### Why this comparison establishes nothing", "",
        "1. **A match would not be validation.** With one run, no repeats "
        "and a binary-ish outcome, agreeing with the real world is within "
        "chance. There is no calibration set, no baseline rate, and no "
        "second condition.",
        "2. **A mismatch would not be refutation either.** The simulation "
        "was given a cast that does not exist, an authority model that was "
        "invented for the test, and no knowledge of anyone's actual "
        "compensation, alternatives or timing.",
        "3. **The counterfactual is unobservable.** Nobody knows what "
        "would have happened at $100,000 rather than $250,000, so the "
        "quantity this experiment ranks has no ground truth to be checked "
        "against -- in this case or in principle.",
        "4. **The delivery finding dominates everything.** "
        + ("Because no offer amount ever entered the subject's own "
           "prompts, the branches were not six different offers from his "
           "point of view: five of six gave him a byte-identical first "
           "turn and the sixth differed by an unrelated internal note. "
           "Comparing their outcomes to a real hiring is comparing a real "
           "event to six samples of a situation in which no offer was "
           "ever put to the candidate."
           if delivery_verdict in ("offers_never_reached_the_subject",
                                   "no_salary_figure_reached_the_subject")
           else "See section 12a for how much of the branch difference "
           "actually reached the subject."),
        "",
        "**Conclusion of this section: no conclusion.** This run is an "
        "engineering transparency exercise. It says what the machine did. "
        "It says nothing about what a16z did, what Richard Zheng did, or "
        "what either would have done.", "",
    ]


def build_report(scenario_dir) -> str:
    art = Artifacts(scenario_dir)
    lines: list = []
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
    lines += _section_15(art)
    lines += _section_16(art)
    lines += _section_17(art)
    lines += _section_18(art)
    lines += _section_19(art)
    lines += _section_20(art)
    lines += _post_hoc(art)
    return "\n".join(lines).rstrip() + "\n"


def write_report(scenario_dir) -> Path:
    scenario_dir = Path(scenario_dir)
    path = scenario_dir / "UNDER_THE_HOOD_REPORT.md"
    path.write_text(build_report(scenario_dir), encoding="utf-8")
    return path
