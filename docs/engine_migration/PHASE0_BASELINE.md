# Phase 0 — Freeze and Baseline

Recorded: 2026-08-03. Branch: `claude/concordia-agentsociety-best-action-engine`.
Baseline measurements executed at repo SHA `03ca54fa1c12...` (see receipts and
`.agent-run/jobs/*/job.json` for exact per-run SHAs). No production routing was
changed before or during these measurements.

## 1. Exact repository SHAs (frozen baseline)

| Repository | Role | SHA | Source |
|---|---|---|---|
| SWORLDMODEL-GROUND-UP | product | `87f8c3d29cc7901d0d7d6ed835190cbde6fb3059` (implementation base main) → branch work at `03ca54f...` | local checkout `/home/user/SWORLDMODEL-GROUND-UP` |
| concordia (fork of google-deepmind/concordia) | local simulation engine | `7779a4c9f96bad10816d88c54e4cb17d53ac5222` | local checkout `/home/user/concordia`, branch `claude/engine-migration-setup-j5d0ti` |
| agentsociety (fork of tsinghua-fib-lab/agentsociety, v2 package) | distributed orchestration | `6e9fc2e79f89f65a3e3d0d7899e380f7394099be` | local checkout `/home/user/agentsociety2`, branch `claude/engine-migration-setup-j5d0ti` |

Note: the concordia fork HEAD adds "three new social media simulation
scenarios" on top of upstream; see §4 finding F3 for a fork-introduced
examples-path defect this causes. Phase 1 pin selection must weigh fork HEAD
vs the last clean upstream commit.

## 2. Python and dependency requirements

| Project | requires-python | Declared deps | Notes |
|---|---|---|---|
| sworldmodel | `>=3.11` | `[]` (stdlib only) | no build-system table, no entry points; runs in place via root `conftest.py` sys.path insertion |
| gdm-concordia | `>=3.12` | see `phase0_engine_env_freeze.txt` | **hard 3.12 floor** — system default 3.11.15 cannot run it |
| agentsociety2 | `>=3.11,<3.14` | incl. `mcp[cli]>=1.13.1`, ray, litellm | floating `mcp` lower bound resolves to mcp 2.0.0 which **breaks imports** (`mcp.server.fastmcp` removed) — environment must pin `mcp>=1.13.1,<2` |

**One compatible environment** (proves Phase 1 feasibility): `/home/user/engine-env`,
Python **3.12.3** (`uv venv --python /usr/bin/python3.12`), containing
`gdm-concordia` (editable from the pinned checkout), `agentsociety2` (editable
from `packages/agentsociety2`), `mcp 1.29.0` (pinned `<2`), and `sworldmodel`
importable via `PYTHONPATH`. Triple import coexistence VERIFIED:
`import concordia`, `import agentsociety2`, `import sworldmodel` all succeed in
one process. Full frozen package list: `docs/engine_migration/phase0_engine_env_freeze.txt`
(151 packages; key pins: ray 2.56.1, litellm 1.95.0, numpy 2.5.1, pandas 3.0.5).

Test-only additions required by upstream suite configs (not production deps):
`pytest 9.1.1`, `pytest-xdist` (required by Concordia's pytest config),
`pytest-timeout`, `pytest-asyncio` + `anyio` (required by AgentSociety async
tests). The SWORLDMODEL control plane and product suite also run on system
Python 3.11.15.

Platform: Linux 6.18.5 x86_64.

## 3. Baseline test-suite results (all via `.claude/tools/run_monitored.py`, exploratory classification)

| Suite | Command (child) | Result | Runtime | Job record |
|---|---|---|---|---|
| SWORLDMODEL full (product + control plane) | `python3 -m pytest tests -q` (Python 3.11.15) | **483 passed, 162 subtests, 0 failed** | 66 s | `.agent-run/jobs/phase0-sworldmodel-baseline-suite-2/job.json` |
| SWORLDMODEL product-only (audit cross-check, control_plane excluded) | `python3 -m pytest tests/ -q` | **252 passed, 1 skipped** (only skip = live-LLM smoke, `DEEPSEEK_API_KEY` unset) | 2.5 s | run by read-only auditor; see SWORLD_CURRENT_STATE.md §(d) |
| Concordia full repo | `engine-env pytest /home/user/concordia -q --timeout=120` | **560 passed, 38 subtests; 18 failed + 2 errors — ALL under `examples/`; core library 0 failures** | 14 s | `.agent-run/jobs/phase0-concordia-baseline-suite-3/job.json` |
| AgentSociety2 tests | `engine-env pytest packages/agentsociety2/tests -q` with dummy `AGENTSOCIETY_LLM_*` | **387 passed, 0 failed** (offline) | 28 s | `.agent-run/jobs/phase0-agentsociety-baseline-suite-2/job.json` |

Superseded attempts kept for the record (environment discovery, not code
failures): `phase0-sworldmodel-baseline-suite` (1 failure = the documented
SHA-exact master-receipt staleness; cleared by re-recording the receipt at the
measured SHA), `phase0-concordia-baseline-suite` (exit 4: missing
pytest-timeout), `phase0-concordia-baseline-suite-2` (exit 4: Concordia's
pytest config requires pytest-xdist), `phase0-agentsociety-baseline-suite`
(66 failures, all "async def functions are not natively supported" — missing
pytest-asyncio/anyio, cleared by installing the plugins).

## 4. Known failures identified at baseline

- **F1 (pre-existing, documented): the SWORLDMODEL semantic runtime fails its
  own completion gates.** Eleven of thirteen reviewers returned FAIL
  (C1 time-jump NO, C2 dead wake provenances, C3 world authoring people's
  decisions, review deadlock, machinery pollution, run-to-run answer
  instability, C4–C7). Sources: `SEMANTIC_RUNTIME_COMPLETION_REPORT.md`,
  `SEMANTIC_RUNTIME_REPORT.md`. This is the documented motivation for the
  engine replacement; details in SWORLD_CURRENT_STATE.md §(c).
- **F2 (environment): upstream dependency incompatibilities** — Concordia
  needs Python ≥3.12; agentsociety2's floating `mcp>=1.13.1` resolves to the
  incompatible mcp 2.x (fix: environment pin `<2`, no source change).
- **F3 (fork-introduced, examples-only): all 18 failures + 2 collection errors
  in the Concordia suite are under `examples/`** and share one root cause: the
  fork's added `ScriptedByEntityModel` (language-model class requiring
  constructor args) breaks `concordia/utils/helper_functions.py:189`
  `get_package_classes()`, which instantiates discovered classes with no
  arguments. Core `concordia/` packages: zero failures. Not on our execution
  path; recorded for Phase 1 pin selection and gate A honesty.
- **F4 (network-dependent test):** `agentsociety2` test
  `test_download_map_file_uses_working_official_url` requires outbound network
  (passed once plugins installed in this proxied environment; flagged as
  potentially flaky offline).

## 5. Baseline artifacts

- Monitored job records + logs: `.agent-run/jobs/phase0-*/`
- Environment freeze: `docs/engine_migration/phase0_engine_env_freeze.txt`
- Committed evidence corpora predating this run (read-only): `artifacts/`
  (compiler acceptance results, semantic-runtime corpora v1–v5, freeze
  manifests `COMPILER_FREEZE.txt` / `KERNEL_FREEZE.txt` / `RUNTIME_FREEZE.txt`)

## 6. Phase 0 conclusions

1. The engine we are adopting is healthy in our environment: Concordia core
   suite 100% green offline; AgentSociety2 suite 100% green offline with
   dummy credentials.
2. The product suite is 100% green at baseline; existing compiler tests are
   the regression floor for gate B.
3. One Python 3.12 environment can host all three codebases simultaneously
   (Phase 1 precondition proven).
4. No production routing was changed. Upstream sources remain byte-identical
   to their recorded SHAs (editable installs reference the unmodified
   checkouts).
