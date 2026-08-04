# Engine Migration — Completion Report (Final Required Output)

**Verdict: PASS** — final adjudicator, 2026-08-04, at frozen SHA
`03886b7cbcb9c4854190bdd7d7fb1c5ca397b144`. This document is the
directive-mandated final output ("Final required output",
`MASTER_IMPLEMENTATION_DIRECTIVE.md`). Every claim below is backed by a
committed artifact, receipt, or job record named in place; the nine
gate-J documents carry the full detail and are cross-linked throughout.

## 1. Executive summary

The best-action engine was rebuilt on the two unmodified upstream
engines: Google DeepMind **Concordia** supplies actor/GM lifecycle,
memory, observation delivery, event resolution, and the sequential
engine loop; **AgentSociety 2** supplies workspace-bound stateless
agents, Ray-task distribution, and dispatcher plumbing. SWORLDMODEL owns
only the layer between: frozen decision contracts, a deterministic
compiler adapter, an initialization planner, a builder/runner pair over
stock Concordia, a minimum agency guard, a counterfactual branch
manager (serial and distributed), whole-branch checkpoint/restore,
metric extraction with resolving citations, and explicit-metric ranking
with a contract-enforced best-among-tested limitation. A best-action
request runs end to end deterministically on both routes (frozen
fixture and compiled artifact), locally and distributed
(byte-identical), at 100 and 1,000 agents (infrastructure only), with
operational robustness proven across the directive's fourteen
scenarios. Two CRITICAL attribution-spoofing vectors found by the
mandated adversarial reviews were closed with discriminating tests and
finder re-verification before the freeze. The frozen acceptance run
re-executed the entire mandatory suite from the beginning at one SHA
with zero code changes; the final adjudicator verified every gate on
artifacts and returned PASS.

## 2. Exact final architecture

`FINAL_ARCHITECTURE.md` (as-built; request flow, checkpoint path, model
seam, seeds). Plain-language ownership: `RESPONSIBILITY_OWNERSHIP.md`.

## 3. Exact commit SHAs

| Repository | Role | SHA |
|---|---|---|
| SWORLDMODEL-GROUND-UP | frozen acceptance SHA | `03886b7cbcb9c4854190bdd7d7fb1c5ca397b144` |
| SWORLDMODEL-GROUND-UP | freeze evidence HEAD | `e19b73a3a766e737c19f83f975ffc8a40fe4c285` |
| SWORLDMODEL-GROUND-UP | completion (this report's parent) | `c1838a3` + this commit |
| google-deepmind/concordia (pinned checkout) | upstream engine, unmodified | `7779a4c9f96bad10816d88c54e4cb17d53ac5222` |
| tsinghua-fib-lab/agentsociety (pinned checkout) | upstream engine, unmodified | `6e9fc2e79f89f65a3e3d0d7899e380f7394099be` |

Pins recorded in `third_party/UPSTREAM_LOCK.json`; both checkouts
verified byte-clean at adjudication.

## 4. Files added or changed

244 commits on `claude/concordia-agentsociety-best-action-engine`.
Against the run's baseline: 271 files, +65,827/−152 lines, of which
`sworldmodel/` 54 files (+15,853/−143), `tests/` 184 files (+42,333/−9),
the rest `docs/engine_migration/` and `third_party/`. Legacy runtime and
compiler production route preserved untouched. Phase-by-phase log with
commits and receipts: `IMPLEMENTATION_LOG.md`.

## 5. Upstream components used directly / 6. Adapters / 7. Upstream modifications

Every upstream symbol, by import path and entry point:
`UPSTREAM_COMPONENT_MAP.md` (four honest notes included). Adapters:
`sworldmodel/compilation/existing_compiler_adapter.py` (compiler → 
CompiledDecisionWorld), `sworldmodel/backends/concordia_local/`
(planner/builder/runner/guard/checkpoint), 
`sworldmodel/backends/agentsociety/` (branch agent template + 
distributed executor). **Upstream modifications: none** —
`third_party/PATCHES.md` records zero patches; environment-level pins
only (`INTEGRATION_METHOD.md`).

## 8. Test results (frozen SHA, monitored records in `.agent-run/BACKGROUND_JOBS.json`)

- Ten-suite engine battery (`phase12-frozen-battery-retry`): **315
  passed, exit 0** — baseline 64, contracts 39, compilation 50,
  individual 34 (incl. 10 live executions), team 25, counterfactuals 30,
  distributed 10, checkpoint 16, scale 20, robustness 27.
- System suite (`phase12-frozen-system`): **714 passed** + the legacy
  live leg adjudicated external-transient (DeepSeek 503 flap) with a
  green stable-window re-leg (`phase12-legacy-live-releg`, exit 0).
- Control plane: 274 tests + 156 subtests; validator all-green at the
  evidence HEAD. Hardcoding guard: both interpreters. Seed sweep
  PYTHONHASHSEED 0/5/13: 30/30/30 (re-executed by the adjudicator).
- Full suite→proof→gate mapping: `TEST_MATRIX.md`.

## 9. Simulation results

- **Individual** (gate C): fixture-1 frozen ranking reproduced —
  `concise_relevant` wins, `decided_by=meeting_scheduled`; RUNBOOK
  worked example executes it verbatim.
- **Team** (gate D): 5-actor slice with pairwise-private isolation,
  meeting fan-out, authority flip probe, actor-owned votes,
  guard-blocked proxy vote.
- **100-agent / 1,000-agent infrastructure** (gate G): exact
  reconciliation (394 and 2,395 actions), sparse activation,
  injected-failure isolation, fresh-process checkpoint/resume —
  **infrastructure only, no population realism**
  (`PHASE11_SCALE_EVIDENCE.md`, provenance caveat included;
  `SOCIETAL_SCALING_PATH.md`).
- **Counterfactual comparison** (gate E): matched worlds, intervention
  isolation, order invariance, identical-candidate byte identity,
  explicit-metric ranking, no LLM override, best-among-tested only.
- **Failure injection** (gates F/I): worker SIGKILL → typed
  fail-loud-once with synthesized failure result; SIGTERM/SIGKILL
  interruption → byte-identical resume; workspace corruption → explicit
  refusal + restore-last-good; 14-row matrix in
  `OPERATIONAL_ROBUSTNESS_MATRIX.md`.

## 10. Reviewer reports and adjudication

Six mandated roles ran with written findings (summarized with
dispositions in `.agent-run/DECISIONS.md`; boundary reviews in
`docs/engine_migration/reviews/`). Two CRITICALs (anchor-spoofing
narration; putative-row leak incl. the split-mint sibling vector) were
closed at `c34ade6` and `e575b85` with 26 discriminating tests and
re-verified by their finders (0/7 evasions, 0/3 false positives). One
HIGH and five MEDIUMs closed; all LOWs dispositioned. **Final
adjudicator: PASS** — all ten gates verified on artifacts, all seven
directive completion categories clear, honesty bar uncontradicted.

## 11. Known limitations

`KNOWN_LIMITATIONS.md` — including: guard detector residuals
(documented, tested); no in-branch model-call timeout seam (bounded at
the mandatory monitored-runner layer); single-host Ray;
scripted-model determinism scope with live-model structure-only smoke;
the F4 scale-evidence trust boundary; the `evaluate_branches`
failed-branch API contract; reserved-marker refusal and
committed-stream count invariant as standing design constraints.

## 12. Exact next steps (later realism phase — none implemented, none validated)

`NEXT_REALISM_PHASE.md`: evidence grounding; observed/inferred/latent
state separation; representative population construction;
human-behavior calibration; full action search; confidence calibration.
Per the directive these are explicitly **not** part of this pass and no
claim to the contrary appears anywhere in the acceptance record.
