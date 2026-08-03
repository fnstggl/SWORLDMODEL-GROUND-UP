# Compiler-to-Concordia Mapping

Field-by-field contract for the deterministic adapter that carries the
existing SWORLDMODEL scene compiler's output into the pinned Concordia
runtime. This document is normative for `sworldmodel/compilation/`; every
row is enforced by a named test in `tests/engine_compilation/`.

## 1. Scope and pinned inputs

| What | Where | Identity |
|---|---|---|
| Source contract | `compiler/scene_schema.py` (`SCENE_SCHEMA`, `validate_manifest_shape`) — the four-field scene manifest: `actors[{name, private_context}]`, `shared_context`, `starting_events[{time, description, visible_to}]`, `resolution` | SWORLDMODEL at implementation base `87f8c3d29cc7901d0d7d6ed835190cbde6fb3059` (branch `claude/concordia-agentsociety-best-action-engine`) |
| Compile metadata | `question`, `start`, `cutoff`, `context`, `evidence`, `compiler_version` (`input.json`); `evidence_mode`, metrics, legacy runtime `world_id` (`compiler_metrics.json`); review/normalization/validation reports | same |
| Destination contracts | `sworldmodel/decision/contracts.py` — `CompiledDecisionWorld`, `WorldActor`, `StartingEvent`, `InterventionInsertionPoint`, `CompilerProvenance`, `ConcordiaInitializationPlan`, `InterventionCandidate`, `EvaluatorSpec` (frozen, Phase 3) | same |
| Downstream chain | `sworldmodel/backends/concordia_local/planner.py` (world → plan) and `builder.py` (plan → live stock Concordia objects), both proven in Phases 4–8 | Concordia pinned at `7779a4c9f96bad10816d88c54e4cb17d53ac5222`; AgentSociety2 pinned at `6e9fc2e79f89f65a3e3d0d7899e380f7394099be` (third_party/UPSTREAM_LOCK.json) |
| Adapter | `sworldmodel/compilation/existing_compiler_adapter.py` (`existing_compiler_adapter_v1`) and `sworldmodel/compilation/decision_route.py` (`decision_route_v1`, `candidate_generator_v1`) | this document's subject |

The Concordia constructors, prefab parameters, initializer interfaces,
memory APIs, and engine startup path were inspected against the pinned
commit during the Phase 0 audit (`docs/engine_migration/audit_raw/CONCORDIA_AUDIT.md`);
the builder consumes exactly the audited public surfaces
(`EntityAgentWithLogging`, `ConcatActComponent`, `Constant`, `ListMemory`,
`ObservationToMemory`, `LastNObservations`, `SwitchAct`, `MakeObservation`,
`NextActingInFixedOrder`/`NextActing`, `FixedActionSpec`, `EventResolution`,
`Terminate`, `Sequential.run_loop`).

## 2. The adapter path (required intermediate object)

```
compiled scene (manifest + compile metadata, or persisted out_dir set)
  -> adapt_compiled_scene / adapt_compiled_artifacts        [this pass]
  -> validated CompiledDecisionWorld  (+ AdaptedScene sidecar)
  -> build_initialization_plan        [existing planner, unchanged]
  -> deterministic ConcordiaInitializationPlan
  -> build_branch / run_branch        [existing builder+runner, unchanged]
  -> validated Concordia objects
```

The adapter STOPS at `CompiledDecisionWorld`. Nothing is mapped through
scattered construction calls: the single code-owned
`ConcordiaInitializationPlan` (contracts.py ~1474) remains the only
bridge into Concordia construction, exactly as Phases 4–8 proved it.
The adapter is pure deterministic code — no LLM call, no paraphrase, no
summarization, no inferred fields, no guessed identities, no silent
defaults, no clock reads, no randomness. Malformed or incomplete input
raises `ContractValidationError` with every collected defect.

## 3. Mapping table

Legend — Kind: **D** direct (verbatim value), **T** transformed (fixed
code-owned rule, stated), **S** sidecar (retained outside the contract
world/plan). Owner: **L** LLM-authored content (via the compiler),
**U** user/caller, **C** code-owned. All contract objects serialize
losslessly (`to_dict`/`canonical_json`), so "persisted" means "rides the
world/plan contract JSON"; sidecar entries persist only if the caller
stores the `AdaptedScene.sidecar`/provenance record.

| # | SWORLDMODEL source | Contract destination | Final Concordia destination (through planner → builder) | Kind | Visibility | Owner | Persisted |
|---|---|---|---|---|---|---|---|
| 1 | `manifest.actors[i].name` | `CompiledDecisionWorld.actors[i].name` → `plan.actor_configs[i].name` | `EntityAgentWithLogging(agent_name=name)`; `SwitchAct(entity_names)`; `NextActingInFixedOrder(sequence)`; `MakeObservation(player_names)` — the actor instance name | D | universal (names address entities) | L (value) / C (identity, see #2) | yes |
| 2 | *(derived)* stable actor ID | `WorldActor.actor_id`; keys of `plan.initial_observations`; `PlanActorConfig.actor_id` | none — Concordia addresses entities by name; the ID is the SWORLDMODEL-side stable handle (registry, branch results, memories) | T (`derive_actor_ids`: lowercase, non-alphanumeric runs → `_`, declaration-order `_2/_3` collision suffixes; underivable name = refusal) | universal | C | yes |
| 3 | `manifest.actors[i].private_context` | `CompiledDecisionWorld.actors[i].private_context` → `plan.actor_configs[i].private_init_data` (planner end-trim; interior bytes verbatim) | that actor's private `Constant` component (`pre_act_label="Private setup"`, key `private_setup`) — its private initializer context, nothing else | D | ONLY that actor's prompts/context; never other actors, never the GM | L | yes |
| 4 | `manifest.shared_context` | `CompiledDecisionWorld.shared_context` → `plan.shared_init_data` + first entry of EVERY actor's `plan.initial_observations[actor_id]` (planner v1 rule) | GM `Constant` (`"Shared setup"`, rostered only when non-blank) + one pre-queued `MakeObservation` observation per actor | D | every actor + GM | L | yes |
| 5 | `manifest.starting_events[i].description` | `StartingEvent.description` → framed `[<canonical time>] <description>` into `plan.gm_initial_events[i]` and into each visible actor's `initial_observations` | `game_master.observe("[event] " + framed)` (GM initial history) + `MakeObservation.add_to_queue` for exactly the visible actors (actor observations) | D (framing is #7's transform) | GM always; actors per `visible_to` | L | yes |
| 6 | `manifest.starting_events[i].visible_to` | resolved actor NAMES → code-owned IDs → `StartingEvent.visible_to` | controls exactly which actors' observation queues receive the event; nothing else | T (exact-name lookup against the declared cast; unknown name = refusal BEFORE simulation; empty list = documented refusal, §6.1) | governs #5 | L (names) / C (lookup) | yes |
| 7 | `manifest.starting_events[i].time` | `StartingEvent.time` (instant preserved; canonical UTC rendering) | the `[<canonical time>]` prefix riding with the event text in GM history and actor observations — explicit run-time metadata, never discarded | T (representation: any tz-aware ISO instant → UTC `Z` form; instant unchanged) | with #5 | L | yes |
| 8 | `manifest.resolution` | `CompiledDecisionWorld.success_criteria` | NONE. The planner deliberately drops it from the plan; it reaches only the external SWORLDMODEL outcome evaluator (`sworldmodel/outcomes` reading the recorded `BranchResult` trace/state) | D (verbatim at world level) | zero actor prompts, zero GM prompts — proven by canary | L | yes (world only) |
| 9 | compile input `question` | world identity (hashed into `world_id`) + `compiler_provenance.artifact_hashes["question_sha256"]` + sidecar `compile_inputs.question` (verbatim) | none — never enters any prompt or the plan body; its durable semantic home is the `DecisionProblem` the route pairs with the world | T + S | nobody in-simulation | U | provenance: yes; verbatim text: sidecar |
| 10 | compile input `start` | `CompiledDecisionWorld.start_time` → `plan.gm_config["start_time"]` + `plan.neutral_premise` (`"The simulation window opens at <start>."`) | `BuiltBranch.run_metadata["start_time"]`; the neutral premise is the engine `run_loop(premise=...)` opening observation (fixed text derived only from start; never mentions actors/contexts/criteria/candidates) | T (parse, canonical UTC) | premise: all actors; metadata: runner | U | yes |
| 11 | compile input `cutoff` | `CompiledDecisionWorld.cutoff` → `plan.gm_config["cutoff_time"]` | `BuiltBranch.run_metadata["cutoff_time"]` — an external run limit. `run_limits.max_steps` is a separate code-owned engine-step budget argument and is NEVER derived from the cutoff (planner rule, unchanged) | T (parse, canonical UTC) | metadata only | U | yes |
| 12 | compile input `context` | sidecar `artifact_files["input.json"].context` (out_dir mode, verbatim) | none | S | nobody | U | sidecar |
| 13 | compile input `evidence` | sidecar `artifact_files["input.json"].evidence` (out_dir mode, verbatim) | none | S | nobody | U | sidecar |
| 14 | `compiler_version` (input.json, cross-checked against metrics) | `CompilerProvenance.version` | none — provenance never enters actor reasoning (canary-proven) | D | nobody in-simulation | C (recorded by the compiler) | yes |
| 15 | `evidence_mode` (compiler_metrics.json) | `CompilerProvenance.evidence_mode` | none | D | nobody | C | yes |
| 16 | compiler metrics (`semantic_calls`, tokens, `wall_s`, `repaired_compile`, legacy `world_id`, …) | sidecar `artifact_files["compiler_metrics.json"]` verbatim + file hash in `artifact_hashes` | none | S | nobody | C | sidecar + hash |
| 17 | `scene_review.json`, `normalization_report.json`, `validation_report.json`, `scene_manifest.json`, `corrected_scene_manifest.json`, `genesis_resolution_check.json`, `runtime_bindings.json` (when present) | sidecar `artifact_files[<name>]` verbatim + file hash; `validation_report.errors != []` is a refusal gate (§6.5) | none | S | C | sidecar + hash |
| 18 | every other artifact file in the out_dir (prompts, raw responses, ledger, snapshots, …) | sha256 in `compiler_provenance.artifact_hashes[<filename>]` | none | S (by hash) | nobody | C | hash: yes |
| 19 | schema/manifest identity | `artifact_hashes["manifest_canonical_sha256"]` (canonical JSON of the mapped manifest) + `world_id` derivation | none | T | nobody | C | yes |
| 20 | insertion actor (CALLER-supplied; **not a manifest field**, §6.2) | `CompiledDecisionWorld.intervention_insertion_point.actor_id` → `plan.intervention_insertion` + `gm_config["intervention_boundary"]="first_turn_observation"` | the single code-owned boundary: `apply_intervention` appends candidate text ONLY to that actor's `initial_observations`, after the base plan/snapshot is frozen | T (name-or-derived-ID resolution; ambiguity/unknown = refusal) | boundary metadata | U (which actor) / C (mechanism) | yes |
| 21 | intervention candidate (route: `DecisionProblem.candidate_interventions[i]` or generator output) | `InterventionCandidate` (id `user_NNN`/`gen_NNN`; owner = insertion actor; timing = world start instant; action verbatim; summary = whitespace-collapsed head ≤120; provenance `user_supplied`/`generated`+config hash) | injected at #20's boundary only, per branch, after the base snapshot freeze; never in the base world | T (fixed rules) | insertion actor's branch only (cross-branch canary-proven) | U or generated-L / C (identity+rules) | yes |
| 22 | success criteria / evaluator (`DecisionProblem.success_criteria`; caller-declared `EvaluatorSpec`) | `EvaluatorSpec` → `plan.evaluator_spec` (passed through untouched) | none — external evaluator only; `sworldmodel/outcomes` measures from the recorded trace/terminal state | D | zero actor/GM prompts | U/C | yes |

## 4. Validation and proving tests

| # (above) | Validation performed | Proving tests (tests/engine_compilation/) |
|---|---|---|
| 1, 2 | production shape gate (`validate_manifest_shape`, imported lazily — §7); duplicate-name refusal; slug derivability (`_SLUG_RE`) incl. suffixed ids; contract uniqueness re-check in `from_dict` | `test_mapping_correctness.py::test_adapter_output_is_a_validated_world_with_stable_code_owned_ids`, `::test_actor_name_id_rule_and_collision_suffixes_are_deterministic`, `::test_undecodable_actor_names_fail_loudly_with_all_defects` |
| 3, 4 | non-empty strings (shape gate + contract); separation asserted at world, plan, prompt, and memory level | `test_mapping_correctness.py::test_private_and_shared_context_stay_separate_in_world_and_plan`; `test_information_leaks.py::test_private_canaries_reach_only_their_own_actor`, `::test_shared_canary_reaches_every_intended_actor` |
| 5, 6, 7 | tz-aware ISO times (shape gate); exact-name resolution; empty/unknown/duplicate refusals; event times inside `[start, cutoff]` (contract semantics — the adapter never clamps); declared ORDER preserved | `test_mapping_correctness.py::test_starting_event_order_and_timestamps_are_preserved`, `::test_unknown_visible_to_names_fail_before_any_simulation`, `::test_empty_visible_to_is_refused_as_documented_contract_narrowing`, `::test_duplicate_visible_to_entries_are_rejected`, `::test_malformed_or_out_of_window_times_fail_loudly`; `test_information_leaks.py::test_single_visibility_event_never_reaches_the_other_actor` |
| 8 | non-empty; measurable-token contract semantics | `test_information_leaks.py::test_resolution_canary_reaches_no_actor_and_no_gm_prompt` (also asserts `RESOLUTION_CANARY not in plan.canonical_json()`) |
| 9 | non-empty question; hash recorded; verbatim sidecar | `test_information_leaks.py::test_compiler_provenance_never_enters_actor_reasoning` (QUESTION_CANARY block); `test_mapping_correctness.py::test_every_manifest_leaf_is_mapped_with_nothing_silently_discarded` |
| 10, 11 | strict tz-aware parse; `cutoff > start`; never clamped | `test_manual_vs_compiler_equivalence.py::test_plans_are_equal_modulo_the_documented_identity_fields` (gm_config equality), `test_mapping_correctness.py::test_malformed_or_out_of_window_times_fail_loudly` |
| 12–19 | required-file presence; JSON parse; completed-compile marker (metrics `world_id`); metrics-vs-input version consistency; validation-report gate; every file hashed | `test_artifact_set_loading.py` (all seven tests) |
| 20 | resolve-or-refuse incl. the name-vs-derived-id ambiguity case | `test_mapping_correctness.py::test_insertion_actor_resolves_by_name_or_derived_id_never_by_guess`; `test_decision_route.py::test_owner_must_resolve_to_the_worlds_insertion_actor` |
| 21 | strict candidate contract gate; single-boundary diff refusal (existing `apply_intervention`); one fixed generator schema, one model call, strict parse | `test_mapping_correctness.py::test_base_world_identical_before_different_interventions`; `test_information_leaks.py::test_one_branch_intervention_never_appears_in_another_branch`; `test_decision_route.py` (all eleven tests) |
| 22 | `EvaluatorSpec.parse`; planner passes through untouched | `test_manual_vs_compiler_equivalence.py::test_plans_are_equal_modulo_the_documented_identity_fields` |

No-silent-discard closure: the shape gate rejects any manifest field
outside the four (and any unknown actor/event sub-field), so an unmapped
field cannot exist; `test_every_manifest_leaf_is_mapped_with_nothing_silently_discarded`
walks every leaf of both a synthetic manifest and the committed REAL
compiled manifest and asserts its exact mapped destination, and
`test_unknown_manifest_fields_cannot_be_silently_dropped` proves the
rejection at all three levels. Determinism:
`test_same_input_twice_yields_byte_identical_world_and_plan` (and the
artifact-set variant) prove identical input → byte-identical world AND
plan canonical JSON.

## 5. Code-owned identity rules (fixed, versioned with the adapter)

- **Actor ID**: `derive_actor_ids` — lowercase; non-alphanumeric runs →
  `_`; strip boundary `_`; collisions get `_2`, `_3`, … in declaration
  order. A name yielding an empty, non-letter-leading, or over-long
  identifier is refused (`invalid_id`), never invented around. (The
  legacy runtime's `scene_adapter.slug` falls back to a fabricated
  `"actor"` id for undecodable names; the adapter deliberately refuses
  instead — recorded divergence.)
- **World ID**: `w_` + sha256(`existing_compiler_adapter_v1 | sha256(question) |
  canonical(start) | canonical(cutoff) | manifest_canonical_sha256`)[:12].
  Content-bound (two different manifests can never share a world id).
  The LEGACY runtime world id in `compiler_metrics.json` is preserved in
  the sidecar and never adopted (`test_legacy_runtime_world_id_is_preserved_in_sidecar_not_adopted`).
- **Candidate IDs**: `user_NNN` / `gen_NNN` in declaration/response
  order; timing = world start instant; decision owner = the insertion
  actor; summary = whitespace-collapsed action head (≤120 chars, the
  fixture loader's exact rule); constraints empty; provenance
  `user_supplied` (empty config hash) or `generated` (sha256 of the
  fixed generator version + prompt template + response schema + cap).
- **Text carriage**: the adapter carries every text field byte-verbatim
  into the world contract. Boundary whitespace trimming happens ONLY in
  the planner (its documented uniform end-trim rule, required by the
  upstream observation delimiter); the adapter itself never rewrites
  text.

## 6. Divergences, narrowings, and non-manifest inputs (explicit)

1. **Empty `visible_to` is refused (contract narrowing).** The compiler
   schema permits an event visible to no actor (a world fact no one
   directly observes; the legacy runtime ledgers it without an
   `info.send`). The frozen `StartingEvent` contract requires ≥1
   observer. The adapter fails loudly with an error naming this
   narrowing rather than dropping the event or inventing an observer.
   **Finding for the lead**: if observer-less pre-start facts must be
   expressible, `StartingEvent.visible_to` needs a contract-version
   change; no lossy workaround is implemented.
2. **The insertion point is not a manifest field.** The manifest has no
   intervention concept; whose action is being chosen is decision-layer
   metadata. The adapter therefore REQUIRES `insertion_actor` from the
   caller (the route supplies `DecisionProblem.decision_owner`), and
   refuses unknown or ambiguous references. This matches the directive
   table's "code-owned intervention boundary" destination.
3. **The question has no contract slot.** `CompiledDecisionWorld` (and
   the plan) carry no free-text compile question; the question's
   semantic home is the `DecisionProblem`. The adapter binds it into
   the world identity (hash), records `question_sha256` in provenance,
   and carries the verbatim text in the sidecar. It never reaches any
   prompt (canary-proven).
4. **`visible_to` resolution is exact-match only.** Alias/short-form
   resolution ("Jordan" for "Jordan Reyes") is the compiler validator's
   job (`scene_validate.py`), which already ran before
   `final_scene_manifest.json` was written. Feeding the adapter a raw
   pre-validation manifest with alias forms fails loudly instead of
   being fuzzy-matched.
5. **Failed/incomplete artifact sets are refused.** The production
   pipeline persists artifacts even for failed compiles;
   `adapt_compiled_artifacts` requires the completed-compile marker
   (metrics `world_id`), consistency between recorded versions, and an
   error-free `validation_report.json`.
6. **`shared_context` reaches two destinations** (GM constant + every
   actor's first observation). This is the Phase 4 planner's documented
   v1 rule, kept unchanged: actors must actually OBSERVE the shared
   ground truth (queue), while the GM needs it as standing context for
   resolution. The directive's "do not duplicate without justification"
   is satisfied by this recorded justification and by the Phase 4–6
   proofs that both destinations are live.
7. **Directive initial-table conformance**: every destination in the
   directive's table (lines "actors[i].name" … "schema and artifact
   hashes") is implemented as specified; no pinned-source conflict
   forced a different destination. The only refinements are the three
   explicit items above (1–3), each a narrowing or an explicit caller
   input, never a silent re-route.

## 7. Import and purity constraints

`sworldmodel/compilation` imports NO compiler module at import time; the
single compiler reference in the package is the lazy, call-time import
of `compiler.scene_schema.validate_manifest_shape` (the production shape
gate — zero drift with what the compiler itself accepts). Importing the
`compiler` package executes its `__init__`, which transitively loads its
sibling modules including the LLM transport; that import is
side-effect-free (constants and definitions only — no network, no file
writes, no environment mutation), and the adapter never references any
callable from it. Proven by
`test_mapping_correctness.py::test_importing_the_compilation_package_pulls_no_compiler_module`
(fresh-interpreter probe: zero `compiler.*` modules after package import;
adapter call succeeds offline with no credentials) and
`::test_static_imports_reference_only_the_declared_compiler_gate` (AST
walk: the only `compiler.*` import statement in the package, at any
nesting level, is the declared gate). Nothing under `compiler/` was
modified; the Phase 4 baseline import-graph proof
(`tests/engine_baseline/test_no_compiler_import.py`) is unaffected
because `concordia_local` never imports this package.

The package is scanned by the hardcoding guard
(`tests/test_hardcoding_guard.py`) on both interpreters; all scene
vocabulary (including canary strings) lives in tests and committed
vectors only.

## 8. Manual-vs-compiler equivalence record (fixture 1)

Pair construction (`test_manual_vs_compiler_equivalence.py`):

- **Manual side**: frozen `tests/fixtures/best_action/individual_reply.yaml`
  through the strict Phase 3 loader (byte-identity against
  `FIXTURES.sha256` re-proven in-test).
- **Compiler-shaped side**: the committed hand-written vector
  `tests/engine_compilation/vectors/individual_reply_scene.json` — the
  SAME scene in the four-field manifest format — through the adapter.
  (A verbatim copy of a REAL production compile is additionally
  committed at `tests/engine_compilation/vectors/compiled_scene_artifact/`
  and exercised by the artifact-set suite; a guard test keeps it
  byte-identical to the live `artifacts/simulations/case1_cold_email/compile/`
  set it was copied from.)

Both worlds pass through the REAL planner; the resulting
`ConcordiaInitializationPlan` objects are equal on **every** field
except exactly `{plan_id, world_id, compiler_provenance}` after the
name-keyed actor-ID bijection `{alex→sender, morgan→recipient}` —
asserted as an exact set, not a subset. Principled differences,
documented rather than papered over:

- **Actor identifiers** differ by construction: the fixture format
  declares ids; the manifest has none, so the adapter derives them from
  names. Names are the shared identity anchor (and the identity
  Concordia actually addresses); the bijection is name-keyed and total.
- **`plan_id` / `world_id` / `compiler_provenance`** differ because the
  two routes have different code-owned identities and provenance
  (`manual_fixture`/`fixture_loader_v1` vs `scene_compiler`/vector
  version) — the sidecar identity of what produced each world.
- **World level only**: `success_criteria` texts differ (loader
  synthesizes an evaluator sentence; the adapter carries the manifest
  resolution verbatim) and the fixture's YAML folded scalar leaves a
  trailing newline on `shared_context`. Both are invisible at plan
  level by design (evaluator-only prose never enters the plan; the
  planner end-trims boundary whitespace) — asserted exactly in
  `test_world_level_differences_are_exactly_the_documented_ones`.

Beyond plan comparison, both plans are BUILT and RUN through the real
builder + runner under identical scripted models:
`test_both_routes_run_byte_identical_traces_under_identical_models`
proves byte-identical committed events, event traces, GM memory,
terminal status, and (through the bijection) per-actor memory rows —
the two routes initialize equivalent Concordia worlds in behavior, not
just on paper.

## 9. Information-leak canaries (adapter-derived worlds, end to end)

All run through the real planner + builder + runner with strict scripted
models (`tests/engine_compilation/test_information_leaks.py`); every
canary is asserted PRESENT at its intended destination before any
absence is asserted:

| Canary | Proves |
|---|---|
| `PRIVATE_ALICE_CANARY` / `PRIVATE_BOB_CANARY` | private context reaches only its own actor's prompts; never the other actor, the GM, the other actor's memory, or a committed event |
| `SHARED_CANARY` | shared context reaches every intended actor's prompts and memory |
| `EVENT_ALICE_ONLY_CANARY` | a single-visibility event never appears in the non-observer's prompts or memory (GM keeps the full pre-start record by design) |
| `RESOLUTION_CANARY` | zero actor prompts, zero GM prompts, zero memory rows, zero bytes of the plan |
| `PROVENANCE_CANARY` (+ `QUESTION_CANARY`) | compiler provenance (and the compile question) never enters actor reasoning while remaining fully recorded in the world/plan sidecar fields |
| `BRANCH_ONE_ACTION_CANARY` / `BRANCH_TWO_ACTION_CANARY` | one branch's intervention never appears in another branch's prompts or recorded trace |
