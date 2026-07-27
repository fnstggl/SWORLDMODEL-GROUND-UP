# Universality & bloat review — minimal_scene_v1 production path

Agent B audit (read-only; no repo code modified). Audited at commit
`1f307cc` ("Insufficiency beats plausibility: refusal doctrine +
empty-cast abstention"), which landed mid-audit; every finding below was
re-verified against the post-commit state. All 158 tests pass
(`python3 -m pytest tests/ -q` → `158 passed in 5.48s`).

Scope: scenario keyword routing, case-name/acceptance constants,
scenario-family compilers and fixed terminal families, capability-menu
reachability, hidden per-object model calls, legacy-compiler fallback,
unnecessary abstractions, dead code / unused imports / deletable files.

Verdict summary: **no CRITICAL findings, no HIGH findings.** The
production scene path (compiler/scene_*.py, 1,148 lines including
`__init__.py`) is universal and lean. The delete list below is
housekeeping (unused imports) plus one policy-decision bulk deletion
(the legacy package and its coupled kernel/test surface).

---

## 1. Scenario keyword routing in executable logic — NONE

Grep of `email|committee|vote|election|negotiat|factory|market`
(case-insensitive) over `compiler/` (excluding `legacy/`) and
`sworldmodel/`:

- `compiler/scene_pipeline.py:47` — `field(default_factory=dict)`
  (Python dataclass idiom, not the word "factory").
- `compiler/scene_prompts.py:4` (docstring) and `:74` (Rule 10) — the
  universal prohibition doctrine ("NEVER schedule a reply, a vote, an
  agreement, an approval, ... unless the question explicitly states it
  has already occurred"). This names acts to forbid *for every scenario
  equally*; it is prompt text, contains no conditional, and is the
  explicit exemption. **Verified: `scene_prompts.py` contains zero
  executable routing** — it is string constants plus four pure
  formatting functions (`_frame`, `call1_user`, `call2_user`,
  `call3_user`) that never branch on question content.
- `sworldmodel/` hits are all `default_factory`, docstrings/comments
  (`terminals.py:10`, `actions.py:14`, `actions.py:45`), and one false
  positive ("s**election**" in `world.py:256`).

The repo's own guard, `tests/test_hardcoding_guard.py`, AST-scans
`compiler/`, `compiler/legacy/`, and `sworldmodel/` for 29 scenario
words in identifiers and non-docstring string literals, with only
`compiler/scene_prompts.py` allowlisted (delegated to this audit). It
passes.

Guard-scope note (LOW): the guard does not scan `worlds/` (correct —
those ARE scenario data) nor the root harness scripts. Manually
verified: `compile_question.py` and `run_scene_acceptance.py` pass the
question/case fields through untouched with no content dispatch.
`run_worlds.py` and `make_trace.py` do contain literal demo-world names
("email", "committee", "factory", "phase_b_email_llm") in executable
constants — but as the *purpose* of those demo harnesses (run/render the
three hand-authored kernel-validation worlds), not as routing of any
user question, and neither is importable from the compile path (proof in
§6).

The mid-audit commit's new empty-cast branch
(`scene_pipeline.py:111-118`) triggers on `manifest.get("actors") == []`
— a structural signal, not a keyword; the added refusal doctrine in
Call 1/Call 2 prompts names universal categories (no decision-maker,
past counterfactual, contradictory premise, internal state without
user-provided proxy, pure lookup/physics), not scenarios.

## 2. Case-name checks / acceptance-case constants in production — NONE

The frozen dataset (`acceptance/dataset_core.json`, 120 cases) has ids
like `dm_landlord_heater_reply`, `dm_kennedy_khrushchev_letters`. Grep
of representative ids over all `*.py`: zero hits. `run_scene_acceptance.py`
is fully data-driven — `case["id"]` is used only for output paths and
report rows; `kind`/`category` come from the data and are never matched
against constants in compile logic.

LOW: `make_acceptance_report.py:86` checks `"unseen" in r["out_dir"]` —
a dataset-*name* convention inside the report generator (selects which
examples to quote). Not in the compile path, affects no compile result.

## 3. Scenario-family compilers / fixed terminal families — NONE in production

- The production resolution is ONE open-ended natural-language string
  bound by the generic wrapper `compiler/scene_resolution.py`
  (`NLResolution` + `build_nl_terminal`): false at genesis, judge-seam
  for the later runtime judgment phase, citation-verified against the
  ledger. No `email_reply`, `committee_vote`, or any enumerated family
  exists anywhere in `compiler/scene_*.py`.
- `sworldmodel/terminals.py` is a typed terminal-spec system, but its
  check kinds are universal primitives (`fact_equals`, `fact_exists`,
  `resource_at_least`, `information_noticed`, `information_sent`,
  `action_completed`, `count_facts_at_least`) — not scenario families —
  and it is NOT imported by the scene path at all. Its only non-test
  consumer is `compiler/legacy/lowering.py` (see delete list).
- Legacy's `TERMINAL_CHECKS` / typed `terminal_spec` live only in
  `compiler/legacy/` (capabilities.py, lowering.py, validation.py,
  roundtrip.py) and legacy-only tests.

## 4. Capability-menu translation — NOT reachable from production

`CAPABILITIES` / `render_menu` / `validate_capability` /
`normalize_capability` exist only in `compiler/legacy/capabilities.py`
(44 KB), referenced by legacy modules and legacy-only tests. Module-load
proof in §6 shows a full production compile never loads any of it.

## 5. Hidden per-object model calls — NONE; max 6 provider requests

By code reading of the current `compile_scene`:

- Exactly three `semantic_call` sites exist in the entire production
  path (`scene_pipeline.py:107, 135, 157`): Call 1 (scene), Call 2
  (review), Call 3 (correction, only on verdict REVISE).
- `scene_llm.SceneCaller.semantic_call` raises
  `CompilerCallBudgetExceeded` **before** opening a fourth slot
  (`MAX_SEMANTIC_CALLS = 3`, checked pre-append, pre-request).
- Each slot permits `MAX_TECHNICAL_RETRIES_PER_SLOT = 1` retry for
  transport/JSON failures → at most 2 HTTP requests per slot.
- **Maximum possible provider requests per `compile_scene` invocation:
  3 × 2 = 6.** Normal clean path: 2 semantic calls / 2 requests
  (verified live with a scripted transport: `status: compiled,
  semantic_calls: 2, provider_requests: 2`).
- Everything after Call 2/3 is pure code: `validate_scene` (regex/
  unicode/datetime only), `instantiate_scene` (loops over actors/events
  emitting kernel ops — zero calls per object), the double
  instantiation determinism hash check, `build_nl_terminal` genesis
  evaluation (judge is None during compile), and replay-from-records.
- The only two network call sites in the non-legacy codebase are
  `compiler/scene_llm.py` (the budgeted compile transport) and
  `sworldmodel/llm_mind.py` (runtime actor minds — never imported
  during compile; proven in §6). The only environment variable the
  production path reads is `DEEPSEEK_API_KEY`.

## 6. Legacy fallback — NONE; mechanical verification

Commands executed in this audit:

1. `python3 -c "import compiler, sys; print('compiler.legacy' in
   sys.modules)"` → **False**. ✅
2. Full scripted end-to-end `compile_scene` (Call 1 → review →
   validation → instantiation → genesis check → replay) → status
   `compiled`, then: `compiler.legacy` in `sys.modules` → **False**;
   `sworldmodel.llm_mind` → **False**; any `worlds*` module → **False**. ✅
3. Grep `compiler.legacy` outside `compiler/legacy/` and
   `compile_question.py` — remaining occurrences are all non-executable
   or tests (acceptable per mandate):
   - `compiler/__init__.py:10` — docstring sentence only; the package
     imports only `scene_llm` and `scene_pipeline`.
   - Tests (allowed; the complete list):
     `tests/test_compiler_core.py` (imports 7 legacy modules),
     `tests/test_pipeline_fake_llm.py`,
     `tests/test_compiler_failures.py`,
     `tests/test_normalization.py`,
     `tests/test_hardcoding_guard.py` (path string in `SCAN_DIRS` only —
     it *scans* legacy for scenario vocabulary; no import).
   - Docs: `README.md`, `artifacts/minimal_scene_compiler/
     OLD_VS_NEW_COMPILER.md`, `PRODUCTION_ROUTE_AUDIT.md`.
4. `compile_question.py`: `--compiler` is an argparse choice
   `["minimal", "legacy"]`, default `"minimal"`; the single
   `if args.compiler == "legacy"` branch is the only legacy import in
   executable code, prints a superseded-path stderr warning, and
   returns. A failed minimal compile returns exit code 1 — there is no
   retry, no reroute, no env-var switch, no import of legacy on any
   failure path. `run_scene_acceptance.py` imports only
   `compiler.compile_scene`/`SceneCaller` and cannot reach legacy at
   all.

## 7. Abstraction review of the scene path — lean; nothing to remove

Seven modules, 1,148 lines total, each with a distinct non-overlapping
job: prompts (strings), llm (transport+budget), schema (shape), validate
(deterministic normalization), adapter (instantiation), resolution (NL
terminal wrapper), pipeline (orchestration). There is no translation
layer, no second semantic representation, no per-scenario anything.

Reviewed and deliberately KEPT (not bloat):
- `build_nl_terminal(judge=...)` — unused by the compile path but is the
  documented, tested seam for the later runtime-judgment phase
  (citation verification lives there).
- `instantiate_compiled` — the zero-LLM rebuild API from stored
  artifacts; tested (`test_scripted_first_pass_compile`).
- The double `instantiate_scene` + hash comparison — determinism
  validation, one extra pure instantiation, no calls.
- `_strip_fences` — 7-line robustness for injected transports.

The single production-path deletion is the unused import in item D1
below.

---

## 8. DELETE LIST

### A. Delete now — zero risk, no behavior change (unused imports)

Production scene path:
1. `compiler/scene_pipeline.py:29` — `world_id_for` is imported from
   `.scene_adapter` and never used in the module (it is used inside
   `scene_adapter.py` itself). Keep `instantiate_scene`.

Kernel (`sworldmodel/`):
2. `sworldmodel/engine.py:29` — `import math` (never referenced).
3. `sworldmodel/actions.py:24` — `from datetime import datetime`.
4. `sworldmodel/actors.py:20` — `from .actions import Intention` (the
   only other mention is a comment on line 269).
5. `sworldmodel/events.py:11` — `field` in
   `from dataclasses import dataclass, field`.
6. `sworldmodel/llm_mind.py:26` — `parse_iso` in
   `from .simclock import Duration, parse_iso`.

Demo/harness:
7. `worlds/factory_world.py:25-26` — `iso` in the sworldmodel import.
8. `run_worlds.py:13` — `World` in the sworldmodel import.

Tests:
9. `tests/test_committee_world.py:4` — `timedelta`.
10. `tests/test_time.py:4` — `time` (the `datetime.time` class; `date`,
    `datetime`, `timedelta` are used).
11. `tests/test_kernel_invariants.py:3` — `import json`.
12. `tests/test_compiler_core.py:5` — `import pytest` (no
    `pytest.<anything>` in the file).

Legacy (only if legacy is kept at all):
13. `compiler/legacy/roundtrip.py:10` — `parse_iso`.
14. `compiler/legacy/assembly.py:19` — `date` (only `.date()` method
    calls appear later, never the class); `:21` — `at_local` (only the
    string key `"at_local"` appears); `:27` —
    `from .graph_builder import BUILTIN_VERBS` (never referenced).

(All verified by AST scan + per-name grep; `from __future__ import
annotations` and package `__init__` re-exports were excluded as
intentional.)

### B. Deletable as a policy decision (recommended once diagnostic
### comparison value expires)

15. **`compiler/legacy/` — the whole package** (15 files, 4,318 lines,
    ~163 KB, including the 44 KB capability menu) **plus** the
    `--compiler legacy` branch of `compile_question.py` (the argparse
    choice and lines 62-71) **plus the four legacy-only test files**
    (`tests/test_compiler_core.py` 330, `tests/test_compiler_failures.py`
    189, `tests/test_pipeline_fake_llm.py` 341,
    `tests/test_normalization.py` 133 lines) and the
    `"compiler/legacy"` entry in `test_hardcoding_guard.SCAN_DIRS`.
    Why deletable: mechanically proven unreachable from every production
    route (§6); superseded by minimal_scene_v1 on every axis per
    OLD_VS_NEW_COMPILER.md; its continued presence is ~5.3k lines of
    maintenance and audit surface whose only function is historical
    comparison. The mandate currently keeps it behind the explicit flag,
    so this is a decision for the owner, not a defect.
16. **`sworldmodel/terminals.py` (315 lines) + `tests/test_terminals.py`
    (211 lines) + the `terminals` re-exports in
    `sworldmodel/__init__.py` (line 20-21)** — goes with item 15. The
    only non-test consumer is `compiler/legacy/lowering.py`; the
    production path resolves through `compiler/scene_resolution.py`
    instead, and the hand-authored demo worlds construct
    `engine.Terminal` directly. If legacy is kept, an alternative
    cleanup is moving `terminals.py` into `compiler/legacy/` so the
    kernel stops exporting a spec system the production compiler never
    uses.
17. **`evidence/*.json`** (3 files, 16 KB) — referenced by zero Python
    code; mentioned only in `COMPILER_DESIGN.md` narrative. They were
    inputs to the legacy-era compiles in `artifacts/compiled/`.
18. **`artifacts/compiled/`** (30 MB) — legacy multi-stage compile
    outputs (`*__evidence_docs` / `*__model_memory` pairs); historical
    evidence for the superseded path. Archive or delete with item 15.

### C. Explicitly NOT recommended for deletion

- `worlds/` + `run_worlds.py` + `make_trace.py` + their tests — the
  hand-authored kernel-validation worlds and their artifact/trace
  tooling; scenario content lives there *as data*, which is the
  architecture working as intended.
- `sworldmodel/llm_mind.py` — runtime actor minds (Phase B); not loaded
  during compile.
- `worlds/__init__.py` (empty) — package marker.
- `__pycache__/` directories — untracked by git (verified); no cleanup
  needed in the repo.

---

## Findings by severity

- **CRITICAL: none.**
- **HIGH: none.**
- MEDIUM: (16) `sworldmodel/terminals.py` is kernel-exported but
  legacy-only — relocate or delete with legacy.
- LOW: (D1) unused `world_id_for` import in the production pipeline;
  (A2-A14) unused imports listed above; hardcoding-guard scan scope
  excludes root harness scripts (manually verified clean);
  `make_acceptance_report.py` selects examples by the `"unseen"`
  dataset-name substring (report tooling only).
