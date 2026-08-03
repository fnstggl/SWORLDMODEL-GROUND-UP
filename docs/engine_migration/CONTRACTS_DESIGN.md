# Fixed Contracts — Design Specification (Phase 3)

Directive-mandated minimality documentation: for every field — why it is
required, who creates it, who may modify it, where it is validated, whether
it is persisted, and whether it affects branch identity or reproducibility.
Implementation target: `sworldmodel/decision/contracts.py` (stdlib-only:
dataclasses + hand validators; canonical JSON via sorted keys; every contract
carries `schema_version` and rejects unknown fields — the product package
keeps `dependencies = []`).

Legend — Creator: C=code, L=LLM (bounded semantic field), U=user/fixture.
Mod: after creation, who may change it (— = immutable). Val: S=schema strict,
M=semantic validation. Persist: Y/N. Ident: affects branch identity /
reproducibility hash.

## Common envelope (all contracts)

| Field | Why | Creator | Mod | Val | Persist | Ident |
|---|---|---|---|---|---|---|
| `contract_type` | prevents one contract type being supplied where another is expected (directive-required rejection test) | C | — | S | Y | N |
| `schema_version` | versioning rules: never silently read as newer; incompatible → clear failure | C | — | S | Y | N |

## DecisionProblem

| Field | Why | Creator | Mod | Val | Persist | Ident |
|---|---|---|---|---|---|---|
| `problem_id` | stable reference for artifacts/reports | C | — | S | Y | N |
| `decision_owner` | the actor whose action is being chosen; semantic checks reference it | U/L | — | S+M (must resolve to a world actor after compilation) | Y | Y |
| `desired_outcome` | the product question; feeds success criteria | U/L | — | S | Y | Y |
| `success_criteria` | measurable YES/NO or metric spec for the evaluator | U/L | — | S+M (measurable from trace/state) | Y | Y |
| `constraints` | qualitative bounds candidates must respect | U/L | — | S+M (compat check per candidate) | Y | Y |
| `time_horizon` | start/cutoff pair for the simulation window | U | — | S (tz-aware ISO, cutoff>start) | Y | Y |
| `relevant_context` | evidence/context string handed to the compiler | U/L | — | S | Y | Y |
| `candidate_interventions` | user-supplied candidates, when given | U | — | S | Y | Y |
| `candidate_generation_permission` | explicit gate on LLM candidate generation | U | — | S (bool) | Y | N |

## CompiledDecisionWorld

Field paths mirror the proven compiler manifest (audit §(b)); the compiler
adapter maps `final_scene_manifest.json` + `input.json` into this contract
without paraphrase.

| Field | Why | Creator | Mod | Val | Persist | Ident |
|---|---|---|---|---|---|---|
| `world_id` | stable identity; joins artifacts across branches | C (hash of question|start|cutoff + manifest hash) | — | S | Y | Y |
| `actors[]` `{actor_id, name, private_context}` | the cast; `actor_id` is code-owned slug (LLM never invents IDs); private context feeds only that actor | name/context: L (via compiler); actor_id: C | — | S (non-empty; unique ids) + M (id collisions resolved deterministically) | Y | Y |
| `shared_context` | world-common starting knowledge → Concordia shared memory (directive mapping); canaries prove containment semantics | L | — | S | Y | Y |
| `starting_events[]` `{description, visible_to[], time}` | pre-t0 facts; visible_to resolves to actor_ids (unknown name = hard error, directive-required) | L (desc), C (id resolution, UTC canonicalization) | — | S+M | Y | Y |
| `cutoff` | external run limit; never equated to max_steps | U (via input) | — | S (tz-aware, >start) | Y | Y |
| `start_time` | simulation t0 | U | — | S | Y | Y |
| `success_criteria` | natural-language resolution → external evaluator ONLY (RESOLUTION_CANARY: appears in zero actor/GM prompts) | L | — | S+M (false-at-genesis checkable) | Y | Y |
| `intervention_insertion_point` | the single code-owned boundary where a candidate enters (actor_id + t0 semantics) | C | — | S+M (actor exists) | Y | Y |
| `compiler_provenance` | compiler version, evidence_mode, artifact hashes — sidecar, never actor-visible | C | — | S | Y | N (identity uses manifest hash already) |

## InterventionCandidate

| Field | Why | Creator | Mod | Val | Persist | Ident |
|---|---|---|---|---|---|---|
| `candidate_id` | code-owned; ranking/report key; LLM never guesses it | C | — | S | Y | Y |
| `summary` | human-readable label for reports | L/U | — | S | Y | N |
| `action` | the exact action/policy introduced in the branch | L/U | — | S+M (actor allowed; no other actor's voluntary decision embedded; constraint-compatible; timing inside horizon) | Y | Y |
| `decision_owner` | must equal the world's insertion-point actor | C (copied) | — | S+M | Y | Y |
| `timing` | when the intervention lands (within allowed options) | L/U | — | S+M | Y | Y |
| `constraints` | candidate-specific bounds | L/U | — | S | Y | Y |
| `provenance` | user-supplied vs generated (+generator config hash) | C | — | S | Y | N |

## SimulationSnapshot

Whole-branch unit: Concordia checkpoint blob + SWORLDMODEL sidecar (audit §F
gaps). Snapshot manifest lists every serialized component (directive).

| Field | Why | Creator | Mod | Val | Persist | Ident |
|---|---|---|---|---|---|---|
| `snapshot_id` / `world_id` | identity + join keys | C | — | S | Y | Y |
| `concordia_checkpoint` | complete `make_checkpoint_data()` output (opaque, versioned) | C (Concordia) | — | S (shape: entities/game_masters keys present) | Y | Y |
| `sidecar.rng` | seed material Concordia does not capture (global random state seed, numpy seed policy) — gate-E reproducibility | C | — | S | Y | Y |
| `sidecar.engine_cursor` | steps completed, remaining budget, premise-delivered flag (resume restarts engines at 0) | C | — | S | Y | Y |
| `sidecar.model_config` | model identity/params per role (restore must reconstruct identically) | C | — | S | Y | Y |
| `sidecar.compiler_artifact_hash` | binds branch to the exact compiled world | C | — | S | Y | Y |
| `snapshot_manifest[]` | names every serialized component (completeness audit) | C | — | S+M (manifest matches checkpoint keys) | Y | N |

## BranchResult

| Field | Why | Creator | Mod | Val | Persist | Ident |
|---|---|---|---|---|---|---|
| `candidate_id`, `branch_id`, `world_id` | joins result → candidate → world; code-owned | C | — | S+M (registered ids only; cross-branch references rejected) | Y | — |
| `terminal_status` | `success|failure|cutoff|incomplete` — R3: early termination is NEVER converted to a NO/failure by default | C (evaluator) | — | S (enum) | Y | — |
| `terminal_world_state` | final state basis for metrics | C | — | S | Y | — |
| `event_trace[]` | committed `[event]` stream + per-step log refs; the ONLY licensed source of outcomes | C (Concordia raw_log/GM memory) | — | S | Y | — |
| `outcome_metrics{}` | explicit metric values read from trace/state | C (evaluator) | — | S+M (each metric cites the events/state it was computed from) | Y | — |
| `infrastructure_errors[]` | provider failures/timeouts recorded, never a simulated outcome (directive §14) | C | — | S | Y | — |
| `token_stats` / `runtime_stats` | accounting (gate F) | C | — | S | Y | — |
| `artifact_paths[]` | where the full trace/checkpoint live | C | — | S (existing at write) | Y | — |

## RecommendationResult

| Field | Why | Creator | Mod | Val | Persist | Ident |
|---|---|---|---|---|---|---|
| `best_candidate_id` | computed argmax under declared criteria — code only, no LLM override | C | — | S+M (must equal ranking[0]) | Y | — |
| `ranking[]` | ordered candidate results with metric values | C | — | S+M (consistent with BranchResults) | Y | — |
| `metric_differences` | measured deltas between candidates | C | — | S | Y | — |
| `downside_outcomes` | worst observed outcomes per candidate | C | — | S | Y | — |
| `run_limitations` | fixed language: "best-performing action among the candidates tested in this engineering simulation"; deterministic vs live-model vs synthetic labeling | C | — | S (required phrases present) | Y | — |
| `validation_status` | which gates/checks the run satisfied | C | — | S | Y | — |

## ConcordiaInitializationPlan (internal, code-owned)

Deterministic product of the adapter; no LLM involvement; fields mirror the
directive's required list (actor instance configs, private init data, shared
init data, GM config, neutral premise, initial observations by actor_id, GM
initial events, run limits, intervention insertion spec, evaluator spec,
compiler provenance). Identity: sha256 of canonical JSON — the equality
target for the manual-vs-compiler-produced fixture test.

## Validation architecture

1. `validate_schema(obj)` — strict types, unknown-field rejection, enum
   checks, version gate. Pure; no I/O.
2. `validate_semantics(obj, registry)` — reference resolution against the
   code-owned registry (actors, candidates, branches), authority checks
   (actor may attempt action; no embedded voluntary decision for another
   actor — reuses the agency-guard detector), timing-in-horizon,
   measurability of criteria.
3. Rejection behavior: original output + exact errors recorded; at most one
   explicitly logged bounded correction attempt for LLM-produced semantic
   fields; then hard failure of the object/branch. No silent repair, ever.
4. Round-trip: `to_json`/`from_json` loss-less; canonical serialization is
   the hashing base for identity fields.

## Test battery (directive-required, Phase 3 exit)

valid acceptance; missing/unknown field; wrong types; fabricated ID;
cross-branch reference; unauthorized action; impossible timing; round-trip;
adapter round-trip preservation; snapshot restore equivalence (deferred to
Phase 8 for the full blob; manifest checks in Phase 3); schema-version
mismatch; malformed LLM output; valid-syntax-invalid-meaning; wrong contract
type supplied.
