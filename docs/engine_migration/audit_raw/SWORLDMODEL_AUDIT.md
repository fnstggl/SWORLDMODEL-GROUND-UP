# SWORLDMODEL-GROUND-UP — Engine-Migration Audit (read-only)

> Raw report of the read-only SWORLDMODEL auditor (investigation agent), 2026-08-03.
> Synthesized into `../SWORLD_CURRENT_STATE.md` and `../OWNERSHIP_AND_REPLACEMENT_MAP.md`; kept verbatim as audit evidence.

**Branch:** `claude/concordia-agentsociety-best-action-engine` @ `03ca54f` (VERIFIED via `git log`)
**Method:** every production file under `compiler/`, `sworldmodel/`, all 8 top-level entry scripts, all 4 report documents, all 16 test files, `pyproject.toml`, freeze manifests, and the migration directive were read; the test suite was executed offline. Nothing was written to the repository (pytest ran with `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`; `git status` shows only pre-existing `.agent-run` control-plane state from the parent run).
Claims are tagged **VERIFIED** (read the code / ran the command) or **INFERRED** (recommendation or judgment resting on verified facts).

---

## (a) Component inventory and classification

Classifications: **retain unchanged / wrap / reuse later / quarantine as legacy / replace / delete only after proven unused**. All "what it is" cells VERIFIED; classification cells INFERRED (recommendations) unless noted.

### Compiler (the asset to preserve)

| Component | What it is | Classification | Justification |
|---|---|---|---|
| `compile_question.py` | CLI for the production compiler `minimal_scene_v1`; `--compiler legacy` is an explicit diagnostic-only flag (lines 52–54, 62–71) | **retain unchanged**; later **wrap** with the DecisionProblem route | Directive says to add "a lightweight DecisionProblem route above the existing compiler" (`docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md:1229`) and "Do not redesign the existing world compiler … unless a failing mapping test proves" otherwise (line 1335) |
| `compiler/scene_schema.py` | The entire four-field manifest contract + review contract + strict shape validators (lines 19–55, 58–78, 91–148) | **retain unchanged** | This IS the `CompiledDecisionWorld` seed schema; field names match the directive's mapping table verbatim (directive lines 1258–1269) |
| `compiler/scene_pipeline.py` | Orchestration: Call 1 scene → Call 2 adversarial review → optional Call 3 correction → deterministic validation → instantiation, genesis-false check, replay check, full artifact set; never raises (lines 69–229); `instantiate_compiled()` zero-LLM rebuild (232–243) | **retain unchanged** (short term); the instantiation tail becomes **wrapped** | Statuses `compiled/corrected/abstained/failed` and artifact set are the compiler's proven contract. Its last stage instantiates into the *old kernel* `World` (lines 188–217) as a self-check — see risk R2 |
| `compiler/scene_llm.py` | `SceneCaller`: DeepSeek transport, hard `MAX_SEMANTIC_CALLS = 3` enforced *before* the call (lines 28, 126–131), 1 technical retry/slot, full request logging, deadlines (33–39) | **retain unchanged** | Independent of the runtime being replaced; injectable `transport` already supports offline tests (line 56) |
| `compiler/scene_prompts.py` | The three prompt frames; evidence-package block (lines 25–36); refusal doctrine (144–149) | **retain unchanged** | Frozen prompt material; on the universality-guard allowlist for its prohibition doctrine (`tests/test_hardcoding_guard.py:18–21`) |
| `compiler/scene_validate.py` | Deterministic normalization: NFKC/invisible-char/name normalization, alias merge, visible_to resolution, UTC canonicalization, duplicate collapse, resolution checks (lines 43–202) | **retain unchanged** | Pure stdlib, no kernel imports; exactly the deterministic layer the new adapter needs upstream of it |
| `compiler/scene_guards.py` | Shallow deterministic backup guards: prewritten-outcome overlap (92–120) and question-window narrower-than-cutoff (194–218) | **retain unchanged** | Pure functions, scenario-word free |
| `compiler/scene_adapter.py` | Direct instantiation of a validated scene into the *old kernel* `World`: IDs, private-context placement, ledgered starting events, visibility via `info.send_new`, personas (44–111) | **wrap** (keep as compile-time self-check), superseded at runtime by the new `CompiledDecisionWorld → ConcordiaInitializationPlan` adapter | It is the current reference semantics for visibility/privacy the new adapter must reproduce; but it binds the compiler to the old kernel (imports at lines 28–29) |
| `compiler/scene_resolution.py` | `NLResolution` + `build_nl_terminal`: NL resolution bound to the kernel `Terminal`; false-at-genesis; judge seam; citation verification (lines 28–70) | **reuse later** (the "external evaluator spec" seed); currently kernel-coupled (imports `sworldmodel.engine.Terminal`, line 24) | Directive maps `resolution` to "External SWORLDMODEL outcome evaluator only" (line 1270–1271); this wrapper's rules (false at genesis, cite ledger seqs, no state mutation) are the spec to port |
| `compiler/legacy/` (16 files, 4,634 lines) | Superseded ~200-call multi-stage compiler; reachable **only** via `--compiler legacy`; `import compiler` does not import it (VERIFIED by `compiler/__init__.py:10–12` and `artifacts/minimal_scene_compiler/PRODUCTION_ROUTE_AUDIT.md`) | **quarantine as legacy** (already is); **delete only after proven unused** | 41 offline tests exercise it (see §(d)); its `EvidenceRegistry`/`evidence_docs` mode (`compiler/legacy/pipeline.py:196–208`) is the only implemented structured-evidence consumer — keep until the evidence-package boundary is rebuilt |

### Kernel (`sworldmodel/`, excluding `semantic_runtime/`)

| Component | What it is | Classification | Justification |
|---|---|---|---|
| `world.py` | Single mutation funnel `World.apply` → append-only ledger `{seq,t,op,data,cause}` + pure reducers; `schedule/cancel/send_info/run_ops/accrue_to`; `from_records` pure replay; state hash (lines 105–121, 133–152, 419–464) | **retain unchanged** while the compiler depends on it; long-term **quarantine as legacy** substrate | `compiler.scene_adapter` and `scene_pipeline`'s determinism/replay self-checks require it; also pinned by `KERNEL_FREEZE.txt` |
| `simclock.py`, `events.py`, `actors.py`, `info.py`, `actions.py` | tz-aware clock/DST, deterministic queue `(t, depth, seq)`, private `ActorState`, channels/attention, declarative `ActionDef` | **retain unchanged** (compiler + tests depend); long-term **quarantine** | Same dependency chain; `scene_adapter.py:28–29` imports `ActorState`, `AttentionRule`, `iso`, `parse_iso` |
| `engine.py` | The Phase-A/B mechanical event loop `Engine.run` (old world resolver #1) + the `Terminal` dataclass (lines 55–62, 87–232) | **quarantine as legacy**; **replace** for simulation duties; **delete only after proven unused** (Terminal must be re-homed first) | Reachable in production only from `run_worlds.py` and `checkpoint.resume`; but `compiler/scene_resolution.py:24` imports `Terminal` from it, so it cannot be dropped naively |
| `terminals.py` | Declarative terminal-spec evaluator (data → mechanical evaluation, cited producers) | **reuse later** or quarantine | Production scene path uses `NLResolution` instead; used by legacy lowering and 10 tests; its "explicit metrics from state" idea matches the directive's outcome evaluator |
| `checkpoint.py` | Ledger-position checkpoint + byte-identical resume (lines 1–25) | **quarantine as legacy** | Only `run_worlds.py` and tests use it; the concept (snapshot = ledger position + hash) maps onto `SimulationSnapshot` (directive lines 1043–1049) |
| `artifacts.py` | Kernel-run artifact projections (for `run_worlds.py`) | **quarantine as legacy** | Kernel-demo era only |
| `llm_mind.py` | `DeepseekMind` — Phase B live actor behind the `Mind` interface (lines 83–167) | **quarantine as legacy**; **delete only after proven unused** | Only `run_worlds.py:138–147` uses it; superseded twice over (semantic runtime, then Concordia actors) |

### Semantic runtime (the replacement target)

| Component | What it is | Classification | Justification |
|---|---|---|---|
| `sworldmodel/semantic_runtime/` (12 files, ~3,000 lines) | The LLM-native single-trajectory loop: `adapter.py` (manifest→World+Journal), `trajectory.py` (orchestration, 1,069 lines), `journal.py` (ledger projection), `views.py` (code-only local views), `actor_mind.py`/`world_mind.py`/`resolution.py` (the 6 semantic roles), `llm.py` (RuntimeCaller), `replay.py` (zero-call replay verification), `trace.py` (21-artifact writer), `envelope.py` (4-field event envelope) | **replace** (whole subsystem); physically **quarantine as legacy** (directive's `legacy/existing_runtime/`, line 1006–1007); **delete only after proven unused** | Both completion reports return FAIL against it (see §(c)). Salvage: `envelope.contained/clean_text` prompt-containment (envelope.py:53–81), `replay.check_ledger_integrity` (replay.py:41–105), the artifact-set convention (trace.py:38–118), the weekday-rendering lesson (views.py:82–104), `journal` availability-vs-observation semantics — these encode paid-for failure knowledge the Concordia path must not relearn |
| `run_simulation.py` | Production entry: frozen compile → `instantiate_scene_manifest` → `run_trajectory` → write artifacts → replay from disk (lines 21–105) | **replace** (its successor is the new pipeline CLI); quarantine alongside the runtime | It is the top of the path being replaced; pinned by `RUNTIME_FREEZE.txt` |

### Entry points, fixtures, assets

| Component | What it is | Classification | Justification |
|---|---|---|---|
| `run_scene_acceptance.py` | Compiler acceptance harness over frozen datasets; per-case artifacts + aggregate metrics (lines 28–95) | **retain unchanged** | The compiler's regression harness; independent of the runtime (compile→instantiate→genesis/replay checks only, no simulation) |
| `author_unseen.py` | Implementation-blind unseen-case author (1 LLM call) | **retain unchanged** | Runtime-agnostic evaluation tooling |
| `run_fidelity_review.py` | Post-hoc LLM world-fidelity audit of accepted scenes (9-point rubric, lines 22–56) | **retain unchanged** | Audits compiler output only |
| `make_acceptance_report.py` | Renders ACCEPTANCE_REPORT.md verbatim from artifacts | **retain unchanged** | Compiler-side reporting |
| `run_worlds.py` | Runs the 3 hand-authored kernel worlds + Phase B; determinism/resume/replay assertions (lines 50–91) | **quarantine as legacy** | Kernel-demo era; still the only executable proof of checkpoint/resume |
| `make_trace.py` | Renders kernel-world artifacts into RUN_TRACE.md; `WORLDS` hardcodes email/committee/factory/phase_b (lines 24–33) | **quarantine as legacy** | Only understands kernel-era artifact layout |
| `worlds/` (email/committee/factory + adapters) | Hand-authored kernel fixtures, scripted minds, data-only action defs | **quarantine as legacy** | Consumed by kernel tests and `run_worlds.py` only |
| `acceptance/` (3 datasets + spec + notes) | 120-case frozen core dataset, 2×20 unseen datasets, authoring spec | **retain unchanged** | Regression-worthy; frozen by design (`DATASET_SPEC.md` header: "frozen before case-specific debugging") |
| `evaluation/` (6 scripts) | Mechanical re-checkable run verifiers (`verify_run.py`, `reverify_replay.py`, `summarise_runs.py`), machinery measure (`interface_mechanics.py`), matched-pair questions/results (`matched_pairs.py`, `matched_pair_result.py`) | **reuse later** | `matched_pairs.py` question sets are runtime-agnostic evaluation inputs; the verifiers' checks (resolution containment, no unobserved leakage, time monotone, wake provenance, exact replay) are the acceptance ideas to port; the file-format bindings are semantic-runtime-specific |
| `evidence/` (3 JSON doc packages) | Structured `{id,title,date,content}` doc lists (VERIFIED by parsing `cold_email.json`) | **retain unchanged** | Format feeds the legacy `evidence_docs` mode; also the natural fixture set for the future evidence-package boundary |
| `artifacts/` (17 subtrees) | Committed run evidence: compiler acceptance runs + reports, 6 audit reviews, 5 generations of simulation corpora (`simulations` … `simulations_v5`), matched pairs, freeze manifests | **retain unchanged** (read-only evidence) | Baseline the directive requires for comparison; freeze manifests (`COMPILER_FREEZE.txt` 24 files, `KERNEL_FREEZE.txt` 5 files, `RUNTIME_FREEZE.txt` 13 files — VERIFIED) are load-bearing for current tests |
| Reports: `SEMANTIC_RUNTIME_REPORT.md`, `SEMANTIC_RUNTIME_COMPLETION_REPORT.md`, `SEMANTIC_RUNTIME_COMPLETION_PLAN.md`, `RUN_TRACE.md` (561 KB), `RUN_TRACE_COMPACT.md` (141 KB) | Phase reports and kernel-era merged traces | **retain unchanged** (evidence); RUN_TRACE files are kernel-era only | The defect record justifying the migration lives here |
| `README.md`, `COMPILER_DESIGN.md` | README documents minimal_scene_v1 as production; **`COMPILER_DESIGN.md` documents the LEGACY multi-stage pipeline** (RESOLUTION→…→REVIEW→WorldBundle, lines 44–92) — VERIFIED | retain; flag `COMPILER_DESIGN.md` as describing the superseded compiler | A mapping doc citing COMPILER_DESIGN.md for "the compiler" would describe the wrong compiler |
| `docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md` (2,188 lines) | The migration directive incl. `CompiledDecisionWorld` and `ConcordiaInitializationPlan` contracts | **retain unchanged** | Control-plane input |
| `tests/` (16 files) | See §(d) | split per §(d) | — |

---

## (b) Compiler schema summary — real field paths

### Inputs (VERIFIED)
- CLI: `question` (positional), `--start` (tz-aware ISO, default now UTC), `--cutoff` (default start+14d), `--context` (string), `--evidence-file` (raw text file), `--out`, `--model` (`compile_question.py:41–55`).
- Programmatic: `compile_scene(question, start, cutoff, context=None, evidence=None, caller, out_dir)` (`compiler/scene_pipeline.py:69–72`).
- **Evidence-package boundary:** the evidence string is injected verbatim as an `EVIDENCE PACKAGE:` block into all three prompts (`compiler/scene_prompts.py:32–33`); absent evidence switches the frame to a model-memory note and stamps `metrics.evidence_mode = "model_memory_unverified"` vs `"evidence_package"` (`scene_pipeline.py:83–85`). The README states this boundary exists "so live retrieval can attach later without changing the four-field contract" (`README.md:55–57`). The *structured* doc format (`[{id,title,date,content}]`, `evidence/*.json`) is consumed only by the legacy compiler's `evidence_docs` mode (`compiler/legacy/pipeline.py:196–208`). VERIFIED.

### The compiled scene — exact field paths the adapter will consume (all VERIFIED)

Schema constant: `SCENE_SCHEMA`, `compiler/scene_schema.py:19–55`. Canonical persisted form: `final_scene_manifest.json` (normalized; written at `scene_pipeline.py:175`), alongside raw `scene_manifest.json` and `input.json`.

| Future `CompiledDecisionWorld` need | Actual current path | Produced/normalized at |
|---|---|---|
| `actors[].name` | `manifest["actors"][i]["name"]` (non-empty string) | LLM Call 1; normalized (NFKC, whitespace, alias-merge) at `scene_validate.py:69–96`; ID assignment `slug(name)` + collision suffix at `scene_adapter.py:34–37, 67–73` (runtime variant: `semantic_runtime/adapter.py:34–39`) |
| `actors[].private_context` | `manifest["actors"][i]["private_context"]` (non-empty string) | Call 1; stored **only** in the owning actor: `actor.memory` record with `source="scene_manifest:private_context"` (`scene_adapter.py:81–83`) or `semantic.actor_profile` record (`semantic_runtime/adapter.py:80–82`); persona brief `"You are {name}.\n{private_context}"` at `scene_adapter.py:106–110` |
| `shared_context` | `manifest["shared_context"]` (single string) | Call 1; stored as fact `scene:shared_context` (`scene_adapter.py:58–59`; `semantic_runtime/adapter.py:65–66`). **Caution:** the semantic runtime deliberately removed it from actor views after leaks in all six v1 runs (`views.py:14–23`); the older scene_adapter still copies it into every actor's memory (`scene_adapter.py:84–86`) — two divergent precedents |
| `starting_events[].description` | `manifest["starting_events"][i]["description"]` | Call 1; whitespace/invisible normalization `scene_validate.py:111–115` |
| `starting_events[].visible_to` | `manifest["starting_events"][i]["visible_to"]` — array of **actor names** (must resolve to declared actors; unambiguous short forms resolved, ambiguity is an error) | `scene_validate.py:117–146`; mapped to code-owned IDs at `scene_adapter.py:91` / `semantic_runtime/adapter.py:88`; unresolvable name → validation error (`scene_validate.py:139–141`), exactly the "unknown visible_to names fail before simulation" test the directive requires (line 1320) |
| `starting_events[].time` | `manifest["starting_events"][i]["time"]` — tz-aware ISO 8601, canonicalized to UTC (`scene_validate.py:156`); pre-start times clamped to start as "already-occurred state" (`scene_validate.py:150–155`); post-cutoff → error (compile-side) or sidecar list `starting_events_beyond_cutoff` (runtime adapter, `adapter.py:104–108`) |
| `resolution` (success criterion) | `manifest["resolution"]` — one natural-language YES/NO condition over observed event history | Call 1; wrapped by `NLResolution{question, resolution, cutoff, world_id}` (`scene_resolution.py:28–37`), persisted in `runtime_bindings.json` under key `resolution` (`scene_pipeline.py:209–210`); **never** enters the adapter or actor state (`semantic_runtime/adapter.py:31` — `CONSUMED_FIELDS = ("actors","shared_context","starting_events")`) |
| start time | `input.json["start"]` (`scene_pipeline.py:98–101`) — caller-owned, not in the manifest |
| cutoff | `input.json["cutoff"]`; also fact `scene:cutoff` in the runtime adapter (`adapter.py:68`) |
| question | `input.json["question"]`; fact `scene:question` |
| provenance/hashes | `world_id = "w_" + sha256(question\|start\|cutoff)[:12]` (`scene_adapter.py:39–41`); trajectory analog `traj_…` (`semantic_runtime/adapter.py:42–44`); `compiler_metrics.json` carries `compiler_version="minimal_scene_v1"`, `evidence_mode`, `semantic_calls`, `per_slot` tokens/durations, `repaired_compile` (`scene_pipeline.py:80–86, 218–221`); determinism proven by double-instantiation hash equality (`scene_pipeline.py:188–192`) and serialize→`from_records`→hash replay check (203–208); phase freeze recorded as git blob hashes in `artifacts/semantic_runtime/{COMPILER,KERNEL,RUNTIME}_FREEZE.txt` |

### Terminal-resolution representation at runtime (VERIFIED)
`build_nl_terminal` (`compiler/scene_resolution.py:40–70`): false while `world.history` is empty; optional pure `judge(records_deepcopy, resolution, question)` must cite existing ledger seqs or `ValueError`; with no judge, cutoff yields `"unresolved_pending_judgment"`. In the semantic runtime the resolution instead reaches exactly two read-only roles — judge and verifier (`semantic_runtime/resolution.py:1–24`; statuses `YES / UNRESOLVED / NO_AT_CUTOFF`, line 31) — with code-enforced rules: YES must cite committed event ids; NO_AT_CUTOFF impossible before cutoff; UNRESOLVED impossible at cutoff.

### Compile outcome statuses (VERIFIED)
`compiled | corrected | abstained | failed(reason)` — never a crash (`scene_pipeline.py:39–47, 222–229`); abstention paths: empty cast (111–118), `UNRESOLVABLE…` resolution (124–128), reviewer ABSTAIN (145–150), "unresolvable" validation errors (180–182). Failure codes: `SCHEMA_INVALID`, `REVIEW_SCHEMA_INVALID`, `CORRECTION_SCHEMA_INVALID`, `VALIDATION_FAILED`, `INSTANTIATION_NOT_DETERMINISTIC`, `TERMINAL_TRUE_AT_GENESIS`, `REPLAY_MISMATCH`, `COMPILER_CALL_BUDGET_EXCEEDED`, `TECHNICAL_FAILURE`, `INTERNAL_ERROR`.

### Per-compile artifact directory (VERIFIED, `scene_pipeline.py:98–221`)
`input.json`, `call_{1,2,3}_prompt.txt`, `call_{1,2,3}_raw_response.txt`, `scene_manifest.json`, `scene_review.json`, `corrected_scene_manifest.json`, `final_scene_manifest.json`, `normalization_report.json`, `validation_report.json`, `genesis_resolution_check.json`, `runtime_bindings.json`, `initialized_world_snapshot.json`, `starting_event_ledger.jsonl`, `actor_initial_views.json`, `compiler_metrics.json`, `internal_error.txt` (on crash).

---

## (c) Documented defects (runtime) and documented strengths (compiler)

### Compiler strengths — why it "independently owns product value" (all VERIFIED from cited sources)

1. Frozen dataset acceptance, `artifacts/scene_acceptance/dataset_core/RESULTS.json`: 120 cases — sufficient: 96% compiled first-pass, 3% corrected, 100% schema success, 99% instantiated, 0 failed; insufficient: 70% honest abstention; median 2 semantic calls, max 3, 0 over budget; median wall 5.0 s, p95 6.4 s.
2. Unseen final dataset: 15/15 sufficient compiled first-pass, 5/5 insufficient abstained, 0 failures (`artifacts/scene_acceptance/dataset_unseen_final/RESULTS.json`).
3. Byte-frozen and independently re-verified across three phases: 24 compiler files hash-checked on disk each test run, untracked/staged files refused (`tests/test_compiler_runtime_integration.py:149–191`; `SEMANTIC_RUNTIME_COMPLETION_REPORT.md` §4).
4. Deterministic instantiation and replay proven per compile (`scene_pipeline.py:188–208`); budget enforced pre-call (`scene_llm.py:126–131`).
5. Both completion reports treat the compiler as the fixed point: "The compiler is frozen: this entry point calls the exact production route" (`run_simulation.py:8–10`); "compiler.compile_scene (FROZEN, unchanged)" (`SEMANTIC_RUNTIME_REPORT.md:23`).

### Documented runtime defects — the case for replacement (each with source; all VERIFIED as *documented claims*)

**Verdict lines:** "Status: INCOMPLETE. All thirteen reviewers have now run; eleven returned FAIL and the final quality gate is one of them" (`SEMANTIC_RUNTIME_COMPLETION_REPORT.md:3–5`); "the real-world quality gate fails" (`SEMANTIC_RUNTIME_REPORT.md:642–648`); "One FAIL means the semantic runtime is not complete. There are four." (`COMPLETION_REPORT:581–583`).

Critical/high, still open at freeze:

1. **C1 (CRITICAL): a final NO is licensed over time never simulated.** 11 of 11 NO runs stopped on an empty queue, not at the horizon; `case1_cold_email` jumped its entire 14-day window after a single step (`COMPLETION_REPORT:323–337`). Mitigated by a last-call sweep, "still not fixed" (`COMPLETION_REPORT:379–391`; sweep code `trajectory.py:871–905`).
2. **C2 (HIGH): three of five wake provenances wired to nothing**; no `known_deadline` wake exists, "the direct cause of C1" (`COMPLETION_REPORT:339–345`; vocabulary at `trajectory.py:154–159`).
3. **C3 (HIGH): the world still authors people's decisions.** 56/163 committed events in v1 were person-choices the world wrote; a narrated "Bo reads, decides, agrees and replies" committed verbatim and produced YES with Bo's model consulted zero times (`SEMANTIC_RUNTIME_REPORT.md:459–470`; `COMPLETION_REPORT:347–354`). Structural rate-bound only (`MAX_WORLD_RUN = 6`, `trajectory.py:595`).
4. **The review deadlock — "one defect wearing three costumes"** (final gate): the event-quality review's two rules cannot both be satisfied for any act done through a device, so the decisive act is deleted, the actor is refused for repeating it, the queue empties, the clock teleports to the horizon, and the absence of the destroyed act is reported as the answer; the reviewer REVISEd "Aisha prints the lease document." then PASSed the byte-identical string four calls later; same lease scene: YES in 3 runs, NO in 3 (`COMPLETION_REPORT:487–520`).
5. **Interface-machinery pollution:** corrected measure 42% (147/353) of committed events are devices acting, 21% post-fix (`COMPLETION_REPORT:186–199`); earlier self-reported figure was wrong by ~5× (ibid.).
6. **Run-to-run answer instability:** `case1_cold_email` answered NO, YES, NO, YES, YES across five runs; a judge that flips on identical input at initialization (`SEMANTIC_RUNTIME_REPORT.md:533–554`).
7. **C4–C7 (HIGH/MEDIUM):** verifier accepted NO_AT_CUTOFF four days early destroying a correct YES (C4, since repaired per §19); `MAX_EVENTS_PER_INSTANT` measures the wrong instant (C5); reserved final calls can't fund the closing judgment (C6); uncontrolled granularity — 15 events in one minute, "signs with a pen" twice (C7) (`COMPLETION_REPORT:356–377`).
8. **Accepted residuals** (`SEMANTIC_RUNTIME_REPORT.md` §18): narrated choices can't be code-detected; probabilities in prose; kernel doesn't validate `cause` at write time; a step is not a transaction (a call is); no live retrieval.
9. **Timing realism failed in 4 of 6 quality-gate runs**; believability failed or partial in 5 of 6 (`SEMANTIC_RUNTIME_REPORT.md:565–584`).
10. Historical defect classes fixed only by accretion — geometric polling (3:50 a.m. reconsiderations), inert non-speakers (Kwame: consulted 19×, 37 wakes, zero events), authorship-vs-delivery false NO, shared-context omniscience in all six v1 runs (`COMPLETION_REPORT` §10; `COMPLETION_PLAN` defect map items 1–20; `views.py:14–23`).

**What was independently verified as sound** (worth preserving as bar-setting): compiler freeze, exact zero-call replay from the persisted ledger (23/23 then 9/9 runs), resolution containment (reaches only judge+verifier), no demographic caricature, evidence-sensitivity separation 4/4 vs 0/4 in matched pair A (`COMPLETION_REPORT` §§9, 12, 13, 20).

---

## (d) Test and asset inventory — offline runnability

**VERIFIED by execution:** `python3 -m pytest tests/ -q` (control_plane excluded) → **252 passed, 1 skipped in 2.51 s** on Python 3.11.15 with `DEEPSEEK_API_KEY` empty. The only skip is the live Phase-B test (`tests/test_llm_phase_b.py:137–138`, `skipif not DEEPSEEK_API_KEY`). Every other test injects a scripted `transport` — no network anywhere (VERIFIED by grep and by the run).

| Test file | Tests | Covers | LLM/network | Keep? (INFERRED) |
|---|---|---|---|---|
| `tests/test_time.py` | 13 | kernel simclock (DST, business days, provenance) | none | keep while kernel retained |
| `tests/test_kernel_invariants.py` | 30 | kernel World/Engine invariants | none | keep while kernel retained |
| `tests/test_terminals.py` | 10 | declarative terminal specs | none | keep / reuse later |
| `tests/test_checkpoint_resume.py` | 6 | checkpoint/resume ≡ uninterrupted, all 3 worlds | none | quarantine with kernel |
| `tests/test_email_world.py` / `test_committee_world.py` / `test_factory_world.py` | 9/8/9 | hand-authored kernel worlds | none | quarantine with worlds/ |
| `tests/test_llm_phase_b.py` | 4 (1 live) | DeepseekMind parse/validation via FakeTransport; 1 live smoke | 3 offline, 1 skipif live | quarantine with llm_mind |
| `tests/test_compiler_core.py` | 13 | **legacy** compiler assembly/lowering/roundtrip | none | quarantine with legacy |
| `tests/test_compiler_failures.py` | 11 | **legacy** compiler wrong-world rejections | none | quarantine with legacy |
| `tests/test_normalization.py` | 8 | **legacy** capability JSON normalization | none | quarantine with legacy |
| `tests/test_pipeline_fake_llm.py` | 9 | **legacy** end-to-end pipeline, scripted transport (docstring lines 1–4) | none | quarantine with legacy |
| `tests/test_scene_compiler.py` | 32 | **production compiler**: schema strictness, budget, normalization, adapter privacy/visibility, NL resolution wrapper, scripted end-to-end | none | **retain — the compiler's regression suite** |
| `tests/test_compiler_runtime_integration.py` | 5 | production compile → semantic runtime binding; resolution never consumed/exposed; **compiler+kernel freeze-on-disk test** (lines 149–214) | none | retain the manifest-identity/privacy tests; re-scope the freeze test (risk R4) |
| `tests/test_semantic_runtime.py` | 74 | the full semantic-runtime invariant battery incl. replay-can-fail tests; **runtime freeze test** (lines 1673–1679) | none | quarantine with the runtime; port the *invariant list* (§14 of `SEMANTIC_RUNTIME_REPORT.md`) as the new engine's checklist |
| `tests/test_hardcoding_guard.py` | 2 | recursive scenario-vocabulary guard over `compiler/` + `sworldmodel/` (SCAN_ROOTS line 15) | none | retain; extend SCAN_ROOTS to the new engine package |
| Total | 253 | — | 1 live-optional | — |

**Assets:** acceptance datasets (120 + 20 + 20 cases, composition VERIFIED by parsing); matched-pair question sets (`evaluation/matched_pairs.py`); evidence packages (3); committed artifact corpora across 5 simulation generations + audits. Regression-worthy to preserve verbatim: `acceptance/*.json`, `artifacts/scene_acceptance/*/RESULTS.json`, `artifacts/semantic_runtime/*_FREEZE.txt`, matched-pair definitions.

---

## (e) Dependencies, installability, LLM boundary, mutation map, risks

### Dependencies (item 6)
- `pyproject.toml` (9 lines, VERIFIED): name `sworldmodel`, version 0.1.0, `requires-python >= 3.11`, **`dependencies = []`**, no extras, **no entry points/scripts**, no build-system table; only `[tool.pytest.ini_options] testpaths=["tests"]`.
- The repo runs **in place**: root `conftest.py:1–4` inserts the repo root on `sys.path`; `compiler`, `worlds`, `evaluation` are top-level packages *not* declared in the project metadata. `pip install .` would rely on setuptools auto-discovery over a flat multi-package layout and is not the supported path — INFERRED (not executed); in-place pytest is VERIFIED working offline in 2.5 s.
- Runtime is stdlib-only (urllib/ssl/json/datetime/zoneinfo) — VERIFIED by imports across all production files.

### LLM boundary (item 7) — all VERIFIED
One provider, one env var, four independent hand-rolled callers, no SDK:

| Caller | File | Endpoint | Env | Params |
|---|---|---|---|---|
| `SceneCaller` (production compiler) | `compiler/scene_llm.py:24, 88–95` | `https://api.deepseek.com/chat/completions` | `DEEPSEEK_API_KEY` | temp 0.0, max_tokens 8000, JSON mode, budget 3, deadlines 90/300/330 s |
| `RuntimeCaller` (semantic runtime) | `sworldmodel/semantic_runtime/llm.py:27, 104–111` | same | same | temp 0.7, max_tokens 1200, JSON mode, run ceiling `budget_for`, 2 reserved final calls |
| `DeepseekMind` (Phase B) | `sworldmodel/llm_mind.py:28, 101–111` | same | same | temp 0.0, max_tokens 900 |
| legacy `Caller` | `compiler/legacy/llm.py:19, 71–74` | same | same | temp 0.0, max_tokens 4000 |

All four hardcode CA bundle path `/root/.ccr/ca-bundle.crt` when present (`scene_llm.py:25,102`; `llm.py:28,117`; `llm_mind.py:29,78`). Transports are constructor-injectable everywhere, which is what keeps the entire suite offline.

### Everything reachable from production entry points that mutates world state (item 9) — the "old world resolver" map (VERIFIED)

Single mutation funnel: `World.apply` (`sworldmodel/world.py:105–121`); everything below funnels through it.

| Path | Mutators reached | Note for the replacement map |
|---|---|---|
| `compile_question.py` / `run_scene_acceptance.py` → `compile_scene` | `scene_adapter.instantiate_scene`: `fact.set`, `channel.add`, `actor.add`, `actor.memory`, `schedule("world.ops")` (`scene_adapter.py:57–105`) — **genesis-time only; no loop runs**; terminal genesis check is read-only (`scene_resolution.py:47–50`) | Compile-time self-check; if kept, must be shown to never execute scheduled events (it doesn't — no `Engine`/`run_trajectory` call in `scene_pipeline.py`) |
| `run_simulation.py` → `instantiate_scene_manifest` → `run_trajectory` | Adapter: `fact.set`×4, `actor.add`, `semantic.actor_profile`, `seal_genesis`, `journal.commit`, `schedule("semantic.event")` (`adapter.py:64–108`). Loop (**old resolver #2**): `queue.pop`+`clock.advance_to`+`apply("event.fired")` (`trajectory.py:906–911`), `journal.commit`/`mark_observed` (930–965), `apply` of `semantic.world_call/actor_call/continuity/event_review/terminal_check/verification/horizon/turn_abandoned`, `actor.memory`, `schedule(K_EVENT/K_WAKE)`, `cancel_event` (220–222), final `clock.advance_to(cutoff)`+`OP_HORIZON` (818–825) | The subsystem being replaced; prove `run_trajectory`, `world_step`, `actor_step`, `judge` unreachable from the new path |
| `run_worlds.py` → `Engine(w, minds, term).run()` | **Old resolver #1** — the full mechanical loop: `event.fired`, `accrue_to`, `run_ops` (world.ops), `info.deliver/notice/notice_skipped/noticing_unsupported`, action lifecycle (`action.propose/state/start_refused/complete_refused`), `watch.add/fired/premature` + retarget cancels, `actor.wake/wake_deferred/view/decision`, `mind.exchange/violation`, `terminal` (`engine.py:96–571`, grep-verified list) | Reachable today only from `run_worlds.py`, `checkpoint.resume` (`checkpoint.py`), and tests. **Not** used by the semantic runtime (it drives `world.queue` directly). Quarantining `run_worlds.py`+`worlds/`+`checkpoint`+`llm_mind` severs every production route into `Engine.run`; the residual import is `Terminal` only (`scene_resolution.py:24`) |
| `author_unseen.py`, `run_fidelity_review.py`, `make_trace.py`, `make_acceptance_report.py` | No `World` construction; file writes + (for the first two) LLM calls | Not world-state mutators |

### Migration risks (e)

- **R1 — The compiler is not standalone.** `compiler/` imports the kernel (`scene_adapter.py:28–29`; `scene_resolution.py:24–25`; `scene_pipeline.py:26`). "Preserve the compiler, replace the runtime" therefore requires retaining (or shimming) `world.py`, `actors.py`, `info.py`, `simclock.py`, `events.py`, `actions.py`, and `engine.Terminal` — exactly the five files pinned in `KERNEL_FREEZE.txt` plus their imports. Deleting the kernel wholesale breaks the compiler's own determinism/genesis/replay gates (`scene_pipeline.py:187–208`). VERIFIED dependency; INFERRED consequence.
- **R2 — Two divergent visibility/`shared_context` precedents.** `scene_adapter` copies `shared_context` into every actor's memory (`scene_adapter.py:84–86`); the semantic runtime withholds it from actors after documented leaks in 6/6 v1 runs (`views.py:14–23`; `COMPLETION_PLAN` defect 13). The Concordia mapping (directive line 1262–1263: shared initial memory) must consciously pick a side and carry the canary tests (directive lines 1306–1314), or it re-imports the omniscience leak. VERIFIED facts; INFERRED risk.
- **R3 — NO-side epistemics is the deepest documented failure (C1) and is engine-independent.** An empty Concordia queue before the cutoff is the same trap: absence of simulated time is not evidence of absence. The directive's "cutoff = external run limit; do not treat max_steps as an exact time equivalent" (lines 1274–1275) addresses it only partially; the incomplete-vs-NO distinction (`trajectory.py:805–839`, `finish(truncated=…)`) should be ported as a contract rule on `BranchResult`. VERIFIED defect; INFERRED carry-over.
- **R4 — Phase-freeze tests will fight the migration.** `test_frozen_compiler_files_are_unchanged` fails on *any* added/removed/edited file under `compiler/` and on the 5 pinned kernel files (`tests/test_compiler_runtime_integration.py:149–214`); `test_the_runtime_is_frozen_for_the_unseen_case` pins `run_simulation.py` + all 12 semantic-runtime files (`tests/test_semantic_runtime.py:1673–1679`, `RUNTIME_FREEZE.txt`). Quarantine-by-moving files breaks both. These freezes encode the *previous* phase's discipline and need an explicit, recorded re-scope in the new phase (they are ordinary tests, not `.claude/` control plane — but under CLAUDE.md rule 6 they are immutable during any `frozen_acceptance` window). VERIFIED mechanics; INFERRED process risk.
- **R5 — Insufficient-case leakage is a real compiler gap, not just a runtime one.** dataset_core insufficient honest-handling is only 70% (6/20 compiled anyway) (`RESULTS.json`, VERIFIED). The DecisionProblem route above the compiler should not assume abstention is airtight.
- **R6 — Single-provider coupling.** Endpoint + `DEEPSEEK_API_KEY` + CA-bundle path are hardcoded in four places (§LLM boundary). The Concordia/AgentSociety stack brings its own model layers (AgentSociety expects `AGENTSOCIETY_LLM_API_KEY`/`AGENTSOCIETY_LLM_API_BASE`); unifying credentials is a day-one integration task. VERIFIED coupling; INFERRED task.
- **R7 — Nondeterminism sources to not inherit.** Runtime temp 0.7 (`semantic_runtime/llm.py:107`) with no seed anywhere; the documented answer flip-flopping (§(c) items 4, 6) is partly this. The directive's `SimulationSnapshot.random seed state` (line 1047) has no current counterpart. VERIFIED absence.
- **R8 — Documentation trap.** `COMPILER_DESIGN.md` describes the superseded legacy pipeline, not `minimal_scene_v1`; a mapping doc citing it would map the wrong schema (WorldBundle, capability menu) — the real production contract is `compiler/scene_schema.py` + `README.md:12–66`. VERIFIED.
- **R9 — Acceptance harness semantics shift.** `run_scene_acceptance.py`'s "instantiated" metric currently means "instantiated into the old kernel". After migration it should additionally (or instead) mean "produces a valid `ConcordiaInitializationPlan`", or the compiler's headline metric silently measures a quarantined path. INFERRED.
- **R10 — Salvage discipline.** The semantic runtime embeds ~30 paid-for failure lessons as code comments and invariant tests (duplicate-commit-before-landing, authorship-vs-delivery, group-observation splitting, weekday rendering, prompt containment, replay-that-can-fail). Deleting rather than quarantining loses the only executable record of them; the invariant table in `SEMANTIC_RUNTIME_REPORT.md` §14 (lines 326–370) is the ready-made checklist to port to the Concordia gate. INFERRED recommendation on VERIFIED material.

---

### Confidence and the next observation
High confidence on the inventory, schema paths, defect list, and test/asset facts (directly read/executed). Medium confidence on two classification calls: (1) how much of the kernel must survive long-term (depends on whether the migration keeps the compiler's kernel-backed self-checks or replaces them with plan-level checks), and (2) legacy-compiler deletion timing. The single observation that would raise confidence most: pin the Concordia commit and inspect its actual initializer/memory/GM constructor signatures — that determines whether the four-field manifest maps directly (as the directive's table at lines 1255–1283 assumes) or needs the `starting_events[].time` sidecar treatment, which is the one field with no obvious stock-Concordia destination. [Addressed: see `CONCORDIA_AUDIT.md` — the constructor/initializer surface is now documented; `starting_events[].time` has no stock destination and goes to the SWORLDMODEL sidecar + observation text, per `../COMPILER_TO_CONCORDIA_MAPPING.md` when written.]
