# Ownership and Replacement Map

Directive-mandated classification of every existing simulation-related
SWORLDMODEL subsystem: **KEEP / ADAPT / REPLACE / ARCHIVE / DELETE**.
Derived from the verified audit (`audit_raw/SWORLDMODEL_AUDIT.md`, whose
retain/wrap/reuse-later/quarantine vocabulary maps as: retain unchanged→KEEP,
wrap→ADAPT, reuse later→ADAPT(deferred), quarantine as legacy→ARCHIVE,
delete only after proven unused→DELETE(gated)).

Status: INITIAL (post-audit, pre-implementation). The REACHABILITY PROOF
section is completed when the new production entry point exists; the final
map must show no REPLACE/ARCHIVE runtime subsystem reachable from it.

## Classification

| Subsystem | Class | Disposition |
|---|---|---|
| `compile_question.py` (CLI) | KEEP | Production compiler entry; later fronted by the DecisionProblem route (ADAPT at the routing layer only) |
| `compiler/scene_schema.py` | KEEP | Four-field manifest contract = seed of CompiledDecisionWorld |
| `compiler/scene_pipeline.py` | KEEP | Compile route unchanged; its kernel-instantiation tail remains a compile-time self-check (genesis-only, no loop) |
| `compiler/scene_llm.py`, `scene_prompts.py`, `scene_validate.py`, `scene_guards.py` | KEEP | Frozen compiler material; deterministic normalization reused upstream of the new adapter |
| `compiler/scene_adapter.py` | ADAPT | Kept as the compile-time reference semantics for privacy/visibility; superseded at runtime by CompiledDecisionWorld → ConcordiaInitializationPlan |
| `compiler/scene_resolution.py` (`NLResolution`, `build_nl_terminal`) | ADAPT | Spec source for the external outcome evaluator (false-at-genesis, cite-committed-events, no state mutation); kernel-coupled implementation stays with the kernel |
| `compiler/legacy/` (multi-stage compiler) | ARCHIVE | Already quarantined behind `--compiler legacy`; DELETE only after the evidence-package boundary is rebuilt and its 41 tests are re-scoped |
| Kernel: `sworldmodel/world.py`, `simclock.py`, `events.py`, `actors.py`, `info.py`, `actions.py` | KEEP (as compiler substrate) | Required by the compiler's determinism/genesis/replay self-checks (audit risk R1); long-term ARCHIVE candidate only if those self-checks are re-based |
| `sworldmodel/engine.py` (`Engine.run` = old resolver #1) | ARCHIVE | Not on the new path; reachable only from run_worlds/checkpoint/tests; `Terminal` dataclass must be re-homed or the import retained before any DELETE |
| `sworldmodel/terminals.py` | ADAPT(deferred) | Declarative metrics-from-state evaluator idea feeds the outcome evaluator; not on the new path initially |
| `sworldmodel/checkpoint.py`, `artifacts.py`, `llm_mind.py` | ARCHIVE | Kernel-demo era; DELETE(gated) after acceptance passes and tests are re-scoped |
| `sworldmodel/semantic_runtime/` (12 files) + `run_simulation.py` | REPLACE (functionally) / ARCHIVE (physically) | The unreliable runtime the directive replaces with Concordia; moved behind an explicit legacy flag only after the new engine passes every acceptance gate; not deleted this pass. Salvage list (prompt containment, replay verifier, invariant battery, incomplete-vs-NO) ported as tests/contract rules, not as code dependencies |
| `run_worlds.py`, `make_trace.py`, `worlds/` | ARCHIVE | Kernel-demo era; the only executable checkpoint/resume proof for the old kernel — retained read-only |
| `run_scene_acceptance.py`, `author_unseen.py`, `run_fidelity_review.py`, `make_acceptance_report.py` | KEEP | Compiler-side harnesses, runtime-agnostic; acceptance harness gains a plan-validity metric when the adapter exists (audit R9) |
| `acceptance/`, `evidence/`, `artifacts/`, reports (`SEMANTIC_RUNTIME_*.md`, `RUN_TRACE*.md`) | KEEP (read-only evidence) | Regression datasets, evidence packages, committed corpora, freeze manifests, defect record |
| `evaluation/` scripts | ADAPT(deferred) | Matched-pair question sets reused as-is; verifier checks ported to new artifact formats |
| Tests: `test_scene_compiler.py`, `test_hardcoding_guard.py`, kernel tests | KEEP | Compiler regression floor (gate B); hardcoding guard SCAN_ROOTS extended to the new engine package |
| Tests: freeze tests (`test_compiler_runtime_integration.py` freeze case, `test_semantic_runtime.py` freeze case) | ADAPT | Re-scoped explicitly and recorded (DECISIONS.md) at the phase that quarantines runtime files; never silently loosened |
| Tests: `test_semantic_runtime.py` battery, legacy-compiler tests, kernel-world tests | ARCHIVE with their subsystems | Invariant list ported to the new engine's checklist first |
| New: `sworldmodel/` best-action packages (decision/, compilation adapter, backends/, counterfactuals/, outcomes/, reporting/) | (new) | The replacement architecture; owned per `.agent-run/ARCHITECTURE.md` |

## Reachability proof (to be completed with the new entry point)

Requirement: from the new production entry point (DecisionProblem →
CompiledDecisionWorld → ConcordiaInitializationPlan → Concordia branch →
BranchResult → comparison → RecommendationResult), demonstrate by import graph
and by test that:

1. `semantic_runtime.trajectory.run_trajectory`, `world_step`, `actor_step`,
   and the semantic judge are not imported and not reachable;
2. `sworldmodel.engine.Engine.run` is not imported and not reachable;
3. the only kernel usage on the compile path is genesis-time instantiation
   inside `compile_scene`'s self-check (no event loop execution);
4. no Concordia action passes through either old resolver before becoming a
   committed `[event]`.

Verification method (when implemented): a dedicated test walks the import
graph of the new entry module and asserts the forbidden modules are absent,
plus a runtime canary asserting the old resolvers' entry functions were never
called during an end-to-end fixture run. Status: PENDING implementation.
