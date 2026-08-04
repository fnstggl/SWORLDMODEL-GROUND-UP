# Implementation Log — phase by phase, from the durable evidence

> Gate J documentation set:
> [FINAL_ARCHITECTURE](FINAL_ARCHITECTURE.md) ·
> [RESPONSIBILITY_OWNERSHIP](RESPONSIBILITY_OWNERSHIP.md) ·
> [UPSTREAM_COMPONENT_MAP](UPSTREAM_COMPONENT_MAP.md) ·
> [IMPLEMENTATION_LOG](IMPLEMENTATION_LOG.md) ·
> [TEST_MATRIX](TEST_MATRIX.md) ·
> [SOCIETAL_SCALING_PATH](SOCIETAL_SCALING_PATH.md) ·
> [KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md) ·
> [NEXT_REALISM_PHASE](NEXT_REALISM_PHASE.md) ·
> [RUNBOOK](RUNBOOK.md)

Sources of record: `.agent-run/TASK_GRAPH.json` (per-task
`completion_evidence`), `.agent-run/DECISIONS.md` (every adjudication),
`.agent-run/FAILURE_LEDGER.jsonl` (every incident), `.agent-run/receipts/`
(current-SHA evidence receipts), and the branch history of
`claude/concordia-agentsociety-best-action-engine`. All work occurred
2026-08-03. Receipt discipline: a receipt is valid at the exact SHA it
records; committed receipts are therefore re-recorded at each fold-in HEAD
(DECISIONS, "Receipt re-record protocol"), and the validator enforces
completion-grade receipts (clean worktree OR content-hash continuity) for
every completed phase task (`phase_receipt_discipline`).

## 0. Initialization and branch authority

- Master directive saved verbatim at
  `docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md`, sha256
  `ac863c8355fab544fc79c8a440ed643b8b0879147209134868985dec67a0cdbb`;
  control plane initialized from it (`ddb14b5`); implementation branch
  created from main `87f8c3d` (the merged verified control plane); draft
  PR #9 opened and kept unmerged (task
  `implementation-branch-and-draft-pr`, verified via the GitHub API at
  `1a6b991`).

## 1. Three-repository audit (gates it fed: A)

- Commit `c1618ff`; receipt
  `three-repository-audit__03ca54fa1c12__20260803T0528500000.json`.
- Landed: `UPSTREAM_AUDIT.md`, `SWORLD_CURRENT_STATE.md`,
  `OWNERSHIP_MAP.md`, `INTEGRATION_PLAN.md`, `RISK_REGISTER.md`,
  `ACCEPTANCE_GATES.md`, `OWNERSHIP_AND_REPLACEMENT_MAP.md`, plus the raw
  reports `audit_raw/{CONCORDIA,AGENTSOCIETY,SWORLDMODEL}_AUDIT.md`
  (verified APIs, real production paths, retain/wrap/quarantine
  classification).

## 2. Phase 0 — freeze and baseline (gate B)

- Commit `c1618ff`; receipt `phase-0-freeze-and-baseline__03ca54fa1c12__...json`;
  monitored jobs `.agent-run/jobs/phase0-*`.
- Results: SWORLDMODEL 483/0; Concordia core 560/0 (20 failures
  examples-only, present at the pinned upstream HEAD); AgentSociety2
  387/0; one Python 3.12.3 engine env with triple import coexistence
  (`PHASE0_BASELINE.md`).
- Incident (ledger #1–2): the first receipt run exposed that the
  validator's change audit was bootstrap-only and misclassified docs as
  evaluators — fixed in a recorded hook-maintenance window (mode-aware
  forbidden sets; docs-precedence classification; regression tests); a
  stray upstream-suite `argv.json` in the repo root led to the
  cd-into-upstream-checkout rule. The failing exit-1 receipt is kept
  deliberately as evidence.

## 3. Phase 1 — dependency preservation (gate A)

- Commit `c1618ff`; receipt `phase-1-dependency-preservation__03ca54fa1c12__...json`.
- Method: exact Git dependencies pinned to immutable SHAs, editable
  installs from clean checkouts, no vendored trees;
  `third_party/{UPSTREAM_LOCK.json,INTEGRATION_METHOD.md,PATCHES.md,THIRD_PARTY_NOTICES.md}`;
  PATCHES.md records zero upstream modifications. Coexistence proof:
  `tests/engine_contracts/phase1_coexistence_proof.py` exit 0.

## 4. Phase 2 — upstream contract tests (gates A, F)

- Commit `751284b`; receipt `phase-2-upstream-contract-tests__5059a468e48a__...json`
  (Ray-suite receipt honestly re-recorded clean later at `8fc2bd3`/`a64dc28`).
- Landed: `tests/engine_contracts/` (39 tests): Concordia
  observe/act/lifecycle order, GM SwitchAct dispatch, the
  `event_resolution_steps` guard seam proven writable/veto-capable before
  observer queueing, checkpoint key set pinned
  `{entities, game_masters, raw_log, checkpoint_counter}`, byte-identical
  deterministic harness (`det.py`); AgentSociety workspace round-trip,
  failure isolation, trace spans, token deltas, bounded concurrency ≤ 2.
- Binding findings recorded as the Phase 2 addendum in
  `INTEGRATION_PLAN.md` (Ray works locally; `env=None` valid; custom-agent
  registration via `WORKSPACE_PATH` before first init; guard-commit
  wrapping shape; AGENT.json schema drift; upstream checkpoint payload has
  no engine cursor and no RNG — the Stage B sidecar list).

## 5. Frozen manual fixtures (gate E)

- Commit `5059a46`; receipt `frozen-manual-fixtures__5059a468e48a__...json`;
  hashes in `tests/fixtures/best_action/FIXTURES.{md,sha256}`.
- One adjudicated change ever: fixture 3 was unparseable by conforming
  YAML parsers (line-final colon in a plain scalar); syntax-only re-freeze
  with zero semantic change, new hash recorded, loader hardened to assert
  conforming YAML for ALL fixtures (DECISIONS, "Fixture 3 syntax
  re-freeze"). Expected winners unchanged: `concise_relevant` /
  `private_ops_then_pilot` / `offer_premium`.

## 6. Phase 3 — decision and branch contracts (gates B, E)

- Commit `2b75c45`; receipts re-recorded clean at `254bbb8`/`4adbd87`.
- Landed: `sworldmodel/decision/` (contracts, registry, validation,
  fixture_loader); `tests/test_decision_contracts.py` (116 at landing; 70
  strict-parse core) + `tests/test_fixture_loader.py` (48). All
  deviations from `CONTRACTS_DESIGN.md` were narrowings, recorded in the
  phase report.

## 7. Phase 4 — stock Concordia local baseline (hard gate; gate C)

- Commit `e6b7b6a`; receipts at `14134b4` (with config hashes).
- Two literal manual scenarios end-to-end on the stock Sequential engine,
  strict scripted models (`sample_choice` never fires — no GM
  improvisation path), three byte-identical clean runs each, canary
  containment incl. RESOLUTION, guard seam wired (identity default at
  this phase), subprocess import proof of zero compiler/semantic_runtime
  modules, R3 terminal statuses. `tests/engine_baseline/` born (25 tests
  then; 64 at HEAD after guard phases).

## 8. Phase 5 — minimum agency guard (gates C, H)

- Commit `84c2c7c`; receipt at `ab9eeef` (re-recorded at `fcf4442` and
  `1f8404b` as guard.py legitimately changed under later sanctioned
  tasks — the content-continuity check caught each change, correctly).
- Landed: `guard.py` (deterministic detector v1), planner/builder/runner
  wiring, `PLANNER_VERSION` v1→v2 (default-enabled guard changes emitted
  plans), enabled-vs-disabled control-trace equivalence,
  `guard_interventions` recording. Recorded deviation: the guard block in
  `gm_config` is scalar (`agency_guard_enabled` + `guard_slot`) because
  the frozen Phase 3 contract validates `gm_config` as a scalar map.

## 9. Phase 6 — counterfactual branch manager (gate E)

- Commit `fac9fc2`; receipts at `99657b4`.
- Landed: `sworldmodel/counterfactuals/`, `sworldmodel/outcomes/`,
  `tests/engine_counterfactuals/`. Gate-E invariants proven locally;
  FIXTURE-1 deterministic acceptance: per-candidate metrics equal the
  frozen expected block; winner `concise_relevant` MEASURED (first
  declared secondary, `meeting_scheduled`), not tie-broken; three
  byte-identical pipeline runs. Ranking semantics adjudicated: declared
  metric order, descending, polarity never inferred; lexicographic
  candidate_id only as a FLAGGED final tie-break.

## 10. Phase 7 — AgentSociety branch executor, Stage A (gate F)

- Commit `25db15c`; receipt at `a44bf16` (Ray-suite receipt re-recorded
  clean at the Phase 8 fold-in per the review).
- Landed: `sworldmodel/backends/agentsociety/`,
  `tests/engine_distributed/`. Local==distributed per-candidate signature
  equality on fixture 1; driver window == worker overlap == 2 with
  exactly-once accounting; dual-channel failure evidence; model seam is
  `model_builder` dotted-name + JSON params. Documented divergence:
  worker-captured mid-branch errors are escalated to step failures AFTER
  persisting the partial result (dual channel), where the local manager
  returns such branches without raising.

## 11. Boundary review #1 (phases 0–2, at `db8175e`) — all six claims HOLD

`reviews/PHASE_0_2_BOUNDARY_REVIEW.md`. HIGH finding (pre-existing,
exposed): the pinned upstream checkouts sat OUTSIDE the write-block
perimeter — an editable-install source edit would have silently changed
the engine under contract. Fixed in hook maintenance #3 (checkouts
classified `upstream_protected` in every mode + continuous integrity
check + lock-file protection). Also: three weak contract tests
strengthened, provenance corrected (the pinned "forks" are pure upstream
mirrors), baseline dirty-worktree disclosure added, receipt policy
hardened. No Phase 4 blocker.

## 12. Boundary review #2 (phases 3–7, at `db41689`) — two HIGHs, both fixed

`reviews/PHASE_3_7_BOUNDARY_REVIEW.md`; fixes at `254bbb8`, `eaa4ed8`.

- HIGH: ~1/8 flaky upstream state round-trip test (set-ordered
  `stored_hashes` under PYTHONHASHSEED) — canonicalized; Phase 8 writer
  bound to canonicalize checkpoint serialization (ledger
  `hash-order-sensitive-state-comparison`).
- HIGH: phase receipts were not completion-grade (dirty-worktree at
  parent SHAs; validator never checked them; rule 7 decorative) — hook
  maintenance #4 added `phase_receipt_discipline`; receipts re-recorded
  clean with path-labeled config hashes.
- **Incident: receipt file-order defect (#4a).** The new check picked the
  "newest" receipt as `passing[-1]` — FILE order; receipt names embed the
  SHA prefix, so a lexicographically-late OLD receipt shadowed genuinely
  newer clean ones (false red), and the mirror case could mask a
  proof-less receipt (false green — the dangerous direction). Fixed in
  the same window: newest = `max()` by recorded timestamp; two
  stash-verified discriminating tests.
- Mediums fixed: contract aliasing (defensive deep copies),
  ranking-polarity opacity (`decided_by_metric` + full declared-order
  re-validation). Medium queued and later closed: worker-side seeded
  scope unproven → `test_worker_rng_equivalence.py` at `8fc2bd3`. Guard
  findings 6+7 queued → §14.

## 13. Phase 8 — whole-branch persistence, Stage B (gate F)

- Commits `9bdd557`/`61705f2`; receipt
  `phase-8-concordia-actor-workspace-adapter__61705f214dc8__...json`
  (119 tests, clean worktree).
- A=A'=B full-signature equality under two seeds; RNG-divergence
  discriminator (naive re-seed visibly diverges); distributed
  interrupted-resume byte-equal with `resumed_from_checkpoint=true`.
  Upstream surprises repaired entirely through public API
  ([UPSTREAM_COMPONENT_MAP.md](UPSTREAM_COMPONENT_MAP.md) §4.2).
  Known pre-existing environment issue recorded: `engine_contracts` +
  `engine_distributed` in ONE pytest session can collide via the frozen
  Ray env snapshot (run suites separately; see
  [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §7.4).

## 14. Agency-guard hardening (gate H)

- Commit `a4112f6`; receipt at `a4112f6...` re-recorded per protocol;
  lead verification at `7e6294e`.
- Closed review findings 6+7: pronoun/collective subjects with
  deterministic roster-name resolution, perfect/progressive auxiliary
  chains, roster-anchored nominalizations, parenthetical asides — each
  with caught + nearby-shape discriminating tests; belief-verb
  complements and performative requests no longer over-blocked
  (byte-identical survival proven); the lemma stem+suffix table replaced
  with plain literals plus a narrowed per-file hardcoding-guard word
  allowance (`{vote, voting}` for guard.py) with an exactness test.

## 15. Incident: silent agent pause + unmonitored long suite (hook maintenance #5)

Ledger `silent-agent-pause-plus-unmonitored-long-suite`; fix at
`7e88b71`/`9218c1d`. The compiler-adapter subagent's bare five-suite
engine pytest baseline was rejected by the permission layer before any
process spawned; the subagent paused awaiting direction for 4h20m,
externally indistinguishable from a hung run — no PID, no registry entry,
no heartbeat existed to prove the negative. General cause: multi-suite
engine batteries matched no long-running pattern, so they ran as bare
unbounded foreground Bash. Fix: pytest naming ≥ 2 `tests/engine_*`
directories now REQUIRES the monitored runner (bounded
`record_receipt --run --timeout` exempt per segment); regression tests;
lead protocol arms a liveness check when launching writer agents. This is
why every DoD battery from the adapter task onward has a monitored job
record ([TEST_MATRIX.md](TEST_MATRIX.md) §3).

## 16. Compiler-to-Concordia adapter (gates C, H)

- Commit `1ae1196`; monitored battery `adapter-final-dod` at `a03ee51`
  (180 tests); receipt at `cb995b3`; lead-verified independently.
- Landed: `sworldmodel/compilation/`, `COMPILER_TO_CONCORDIA_MAPPING.md`
  (every source field mapped or sidecar-retained, each row test-named),
  `tests/engine_compilation/` (46): leak canaries end-to-end,
  manual-vs-compiler plan equivalence on fixture 1 (differences exactly
  `{plan_id, world_id, compiler_provenance}` through the name-keyed ID
  bijection), route tests incl. the one-fixed-schema generator. Zero
  `compiler/` modifications; lazy shape-gate import with import-isolation
  proofs. Lead dispositions recorded: observer-less starting events stay
  refused (contract narrowing); the compile question's home is
  `DecisionProblem` (hash+sidecar treatment permanent); undecodable actor
  names refused, never fabricated.

## 17. Phase 9 — individual vertical slice (gates C, E)

- Commit `cc4ba2e`; monitored `phase9-final-dod` at `460d502` (200
  tests); receipt commit `9ba9b3a`.
- Landed: `sworldmodel/reporting/` + `tests/engine_individual/`:
  per-clause gate-C battery (guard-enforced no-choosing-another's-
  response; attribution-anchored evaluator defeating GM narration; all
  four terminal statuses; 3× byte-identical repeats), deterministic
  hash-derived mock-model leg (no scenario knowledge), live DeepSeek
  smoke leg (2 tests, 5 passing executions each, zero transport
  retries), committed hash-asserted example report/trace artifacts.
  The attribution-anchored predicate pattern was recorded as the Phase 10
  template.

## 18. Phase 10 — team vertical slice (gate D)

- Commit `6c3bd85`; monitored `phase10-final-dod` at `6d946e8` (219);
  receipt commit `fcf4442`.
- Fixture 2, 5 actors, 11 engine steps, every gate-D clause its own test:
  pairwise private isolation across all 20 ordered pairs × 3 branches;
  meeting fan-out; participant-only follow-ups; the authority flip probe
  (identical veto sentence from authority vs non-authority flips
  failure↔success); actor-owned votes with a guard-blocked proxy vote; GM
  narration uncitable for tallies; round-N references round-1 private
  content; explicit outcomes incl. a cutoff variant; byte-identical
  repeats under PYTHONHASHSEED 0/5/13. **Zero production changes** — all
  expressed through existing plan configuration. Mechanical note
  recorded: a branch's final-step event is queued but never delivered
  (run ends before the next fan-out) — see
  [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §7.1.

## 19. Phase 11 — societal infrastructure proof, Stage C (gate G)

- Commits `9c0b75b` (suite + evidence + doc), `cf091a6` (receipt); ten
  monitored jobs at evidence SHA `05938a3`, all exit 0; battery
  `phase11-final-dod` at 235.
- 100-agent run 394/394 reconciled; 1,000-agent run as 4 isolated
  250-agent partitions × 2 segments with fresh-process fresh-Ray
  checkpoint/resume at tick 6 (2,395/2,395; aggregate ids byte-equal to
  raw-workspace recomputation); sparse activation inspectable; injected
  failures isolated dual-channel; refuse-lost/duplicated negative proofs;
  infrastructure-only labeling test-enforced everywhere. 52 committed
  evidence files with a sha256 manifest (`PHASE11_SCALE_EVIDENCE.md`).

## 20. Boundary review #3 (phases 8–11, at `c80787e`) — the F1 story

`reviews/PHASE_8_11_BOUNDARY_REVIEW.md`; fix commit `1f8404b`; trail
closure `eda9868`/`ba934d0`. Verdicts: checkpoint/guard/slice/hygiene
hold-with-findings; adapter and scale evidence HOLD outright; battery
independently reproduced at 235.

- **F1 (HIGH — two gate-H clauses REFUTED as reviewed).** `Name:` /
  `Name --` — upstream EventResolution's own attribution separators —
  evaded the guard's whitespace-adjacent subject detector, and the slice
  evaluators' attribution anchors accepted substring co-occurrence
  anywhere in a row. The reviewer reproduced end-to-end proxy casts of
  another actor's reply and veto, counted as outcomes. **Fixed the same
  session, not accepted as residual** (`1f8404b`): guard detection class
  6 (colon/dash subject-attribution boundaries for non-active roster
  names; the active player's own attribution passes byte-identically);
  evaluator anchors bind to the row's OWN leading attribution == the
  predicate-named actor; all four reviewer probes reproduced BEFORE
  (pass-through/miscount) and AFTER (rewritten + escalation records, no
  terminal flip); 19 discriminating tests; battery 235 → 254; committed
  example artifacts stayed byte-identical; guard-hashing receipts
  re-recorded. Lead follow-up: the counterfactual suite's own helper
  predicates still used the bare substring shape — rewired onto the same
  anchor with a three-test discriminating module
  (`tests/engine_counterfactuals/test_predicate_attribution.py`). New
  guard residuals documented honestly
  ([KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §2). The two refuted
  clauses are restored by construction; re-confirmation by the reviewer
  role at the frozen SHA is scheduled before adjudication.
- **F2 (LOW)**: inert stored_hashes canonicalization untested → dedicated
  4-test unit module (`test_state_canonicalization.py`), no production
  change.
- **F3 (MEDIUM)**: validator FAIL at HEAD is the documented one-commit
  master-receipt staleness → mechanical; the Phase 12 freeze sequence
  ends with the master receipt re-recorded at the frozen SHA.
- **F4 (LOW)**: big-run scale reconciliation trusts committed
  self-attested equality fields → ACCEPTED as a disclosed two-tier design
  ([KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §5).

## 21. Gate I — operational robustness matrix

- Commits `2404226` (suite + matrix), `2935ce7` (receipt); battery
  `robustness-final-dod` at 284; fold-in `095b56e`.
- `tests/engine_robustness/` (27 tests) + `OPERATIONAL_ROBUSTNESS_MATRIX.md`
  covering all fourteen gate-I scenarios with per-row
  explicit/bounded/recoverable verdicts; monitored clean-install probe
  (23.3 s, 151 packages, versions matching the phase-0 freeze — doubling
  as gate-A reproducibility evidence); three honest findings recorded
  (G1, F-R1, L1 — [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) §3).

## 22. Where this log ends

At `5667596` (gate-I fold-in + master receipt re-record), the remaining
mandatory work is: this gate-J documentation set, the six named reviewer
roles against the near-freeze SHA (including re-confirmation of the two
F1-refuted gate-H clauses), the Phase 12 frozen acceptance run (full
suite from the beginning at one frozen SHA, master receipt re-recorded at
that SHA per F3), ACCEPTANCE_STATUS gates to PASS with evidence, and the
final adjudicator (`.agent-run/RUN_STATE.json.next_action`;
`.agent-run/TASK_GRAPH.json`).
