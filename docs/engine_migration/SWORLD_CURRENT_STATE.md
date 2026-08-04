# SWORLDMODEL Current State

Synthesis of the full read-only audit (2026-08-03) at branch
`claude/concordia-agentsociety-best-action-engine`. Full cited evidence:
`audit_raw/SWORLDMODEL_AUDIT.md`.

## The one-sentence state

The production world compiler (`minimal_scene_v1`) is strong, frozen, and
regression-covered; the semantic runtime it feeds is documented by its own
completion reports as FAILED (11 of 13 reviewers) and is the subsystem this
migration replaces with Concordia.

## What is strong (preserve)

- **Compiler production route**: `compile_question.py` → `compiler/scene_pipeline.py`
  (`compile_scene`): LLM Call 1 scene → Call 2 adversarial review → optional
  Call 3 correction → deterministic normalization/validation
  (`scene_validate.py`) → kernel instantiation self-check with genesis-false,
  determinism, and replay gates. Statuses `compiled|corrected|abstained|failed`,
  never a crash; hard 3-call budget enforced pre-call; full per-compile
  artifact set. Frozen-dataset acceptance: 120-case core — 96% first-pass
  compile on sufficient cases, 0 failed, honest abstention on insufficient
  (70%); unseen final 15/15 + 5/5.
- **The four-field manifest** (`compiler/scene_schema.py`) is the seed of
  `CompiledDecisionWorld`: `actors[].{name,private_context}`, `shared_context`,
  `starting_events[].{description,visible_to,time}`, `resolution` — with
  caller-owned `start`/`cutoff`/`question` in `input.json` and provenance in
  `compiler_metrics.json` / `world_id`. Real field paths for the future
  adapter are tabulated in the raw audit §(b).
- **Resolution containment**: the `resolution` field never enters actor or GM
  state (`CONSUMED_FIELDS` excludes it); it feeds only the external evaluator
  (judge + verifier). This is the containment precedent our Concordia path
  must reproduce (RESOLUTION_CANARY test).
- Offline test discipline: 252 product tests passing in 2.5 s with injected
  transports; the compiler's regression suite is `tests/test_scene_compiler.py`.
- Evidence assets: frozen acceptance datasets (120+20+20), matched-pair
  question sets, evidence packages, five generations of committed simulation
  corpora, byte-freeze manifests.

## What is broken (replace) — documented by its own reports

Verdicts: "eleven returned FAIL" (`SEMANTIC_RUNTIME_COMPLETION_REPORT.md`);
"the real-world quality gate fails" (`SEMANTIC_RUNTIME_REPORT.md`).

- C1 (CRITICAL): final NO licensed over time never simulated (empty queue ≠
  horizon reached; 11/11 NO runs stopped early; 14-day window jumped in one
  step).
- C2: three of five wake provenances wired to nothing — the direct cause of C1.
- C3: the world authors people's decisions (56/163 committed events in v1
  were person-choices written by the world mind; "Bo agrees" committed with
  Bo's model consulted zero times).
- Review deadlock ("one defect wearing three costumes"): event-quality rules
  unsatisfiable for device-mediated acts → decisive act deleted → queue empties
  → clock teleports → the absence is reported as the answer.
- Interface-machinery pollution (42% device events, 21% post-fix);
  run-to-run answer instability (NO,YES,NO,YES,YES on identical input);
  C4–C7 (early NO_AT_CUTOFF acceptance, wrong-instant caps, unfunded closing
  judgment, uncontrolled granularity).

**Paid-for lessons to carry into the Concordia path** (not relearn): prompt
containment (`envelope.contained`), zero-call replay verification, resolution
containment, shared-context omniscience leak (fixed by withholding shared
context from actor views), authorship-vs-delivery distinction,
incomplete-vs-NO distinction at cutoff (BranchResult must distinguish
`success/failure/cutoff/incomplete`), the invariant battery in
`SEMANTIC_RUNTIME_REPORT.md` §14 as the new engine's checklist.

## Structural constraints on the migration

1. **The compiler is not standalone** — it imports five kernel modules and
   `engine.Terminal`. The kernel files pinned in `KERNEL_FREEZE.txt` are
   retained while the compiler's self-checks depend on them.
2. **Byte-freeze tests** pin `compiler/` (24 files), 5 kernel files, and the
   12 semantic-runtime files + `run_simulation.py`. Any quarantine-by-move or
   compiler-adjacent addition breaks them; re-scoping those freeze tests is an
   explicit, recorded step of the phase that touches them (they encode the
   previous phase's discipline, not this one's).
3. **Old world resolvers**: #1 `sworldmodel/engine.py:Engine.run` (reachable
   only from `run_worlds.py`/`checkpoint.resume`/tests) and #2
   `semantic_runtime/trajectory.py:run_trajectory` (reachable from
   `run_simulation.py`). The replacement map must show neither is reachable
   from the new production entry point; compile-time instantiation in
   `scene_pipeline` is genesis-only (no loop runs) and stays as a self-check.
4. **LLM boundary**: four hand-rolled DeepSeek callers behind `DEEPSEEK_API_KEY`
   with injectable transports; the new engine brings Concordia
   `LanguageModel` + AgentSociety dispatcher — credential unification is a
   day-one integration task (risk register).
5. Zero-dependency stdlib product package (`requires-python >=3.11`,
   `dependencies=[]`), running in place via root `conftest.py`; the engine
   stack lives in a separate Python ≥3.12 environment (see PHASE0_BASELINE.md).

## Component classification

The full retain/wrap/reuse-later/quarantine/replace/delete inventory, with
justifications and citations, is in `audit_raw/SWORLDMODEL_AUDIT.md` §(a) and
is normatively restated in `OWNERSHIP_AND_REPLACEMENT_MAP.md` (KEEP/ADAPT/
REPLACE/ARCHIVE/DELETE vocabulary).
