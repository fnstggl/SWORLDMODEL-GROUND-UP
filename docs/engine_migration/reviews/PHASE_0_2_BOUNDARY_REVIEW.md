# Adversarial review — Phases 0–2 boundary at db8175e

> Raw report of the read-only adversarial reviewer, 2026-08-03. Verbatim
> evidence for the review trail (gate H). Disposition of every finding:
> `.agent-run/DECISIONS.md` "Phase 0–2 boundary review outcome". Summary:
> all six claims HOLD (three with findings); **no Phase 4 blocker**; the
> HIGH external-checkout gap, the lock-file protection gap, the three weak
> tests, the provenance errors, and the disclosure gaps were all fixed in
> the same session (hook maintenance #3 + follow-up edits), each with
> discriminating regression tests where applicable.

Scope note: HEAD moved during review from db8175e to 9e7609d; the only delta is one FAILURE_LEDGER.jsonl line (recording the reviewer's own stream stall). All findings hold at db8175e. In-progress Phase-3 files were excluded throughout.

## C1 — Upstream integrity: HOLDS (2 LOW accuracy findings)

Evidence:
- `/home/user/concordia` → HEAD = 7779a4c9f96bad10816d88c54e4cb17d53ac5222; `/home/user/agentsociety2` → 6e9fc2e79f89f65a3e3d0d7899e380f7394099be. Both `git status --porcelain` empty, `git diff HEAD` empty.
- Stronger than claimed: `git ls-remote` shows 7779a4c IS upstream google-deepmind/concordia HEAD/main; same for tsinghua-fib-lab/agentsociety and 6e9fc2e. The "forks" are pure mirrors.
- Pseudo-fork search: no upstream license headers outside third_party docs; no upstream class redefinitions anywhere in the repo; only tests import concordia. Editable installs resolve to the pinned checkouts.

Findings:
- LOW — UPSTREAM_LOCK.json and PHASE0_BASELINE.md F3 mis-attributed ScriptedByEntityModel as fork-added; it is Google-authored upstream commit 1372a37 and the pinned SHA equals upstream main. [FIXED: provenance corrected in both files.]
- LOW — the lock's integrity guarantee was point-in-time only. [FIXED: continuous `upstream_checkouts_integrity` validator check.]

## C2 — Baseline honesty: HOLDS (provenance-hygiene findings)

All three headline rows match their job records exactly (483/0 at exit 0; 18 FAILED lines all under examples/ with 560 passed; 387/0 at exit 0). Superseded attempts disclosed accurately.

Findings:
- MEDIUM — baseline jobs ran with `worktree_clean_at_start: false`, undisclosed. [FIXED: disclosure added to PHASE0_BASELINE.md §3.]
- LOW — the 252-passed cross-check row lacked a job record, cited the wrong source doc, and printed a command that couldn't exclude control_plane. [FIXED: row corrected.]
- LOW — audit receipt (253 passed, live smoke ran) vs auditor's offline run (252+1 skip) were blended. [FIXED: both runs now distinguished in the row.]

## C3 — Phase 2 suite substance: HOLDS (3 weak tests named)

Reviewer re-ran the suite independently: 39 passed. Core claims genuinely established against real upstream objects (phase-order recorder in a real EntityAgent; bank probe for commit timing; guard-seam assertions on the GM's real memory bank and the real MakeObservation queue, cross-checked against upstream `sequential.py::resolve()`; exact checkpoint key set; two full byte-compared deterministic runs; on-disk worker evidence for batch isolation).

The 3 weakest tests:
1. Concurrency test proved only the upper bound — a fully serialized dispatcher would pass; `len(pids) >= 1` was vacuous. [FIXED: warm-up round added (cold-start serialization was real, measured 6s gap), then strict `overlap == 2` + anti-serialization wall-span bound.]
2. `np.random.default_rng is np.random.default_rng` tautology — a leaked monkeypatch would go undetected. [FIXED: captures the original factory, asserts replaced inside the context and restored after.]
3. token_stats asserted only `isinstance(dict)`. [FIXED: exact `== {}` for the no-LLM run + audited shape contract for any entries.]

Minor (accepted, LOW): veto-before-observer-queueing untested with notify_observers=True (same upstream code path as the tested rewrite); checkpoint restore equality covers memory text + raw_log + names only. Noted for Phase 8's deeper equivalence gate.

## C4 — Fixture freeze: HOLDS (no findings)

Hashes verified; population_offer arithmetic fully consistent (40+25+35=100; 720/3750/2625; revenue winner ≠ purchase-count winner as designed); team_commitment scripted counts satisfy/violate the declared rule exactly as claimed (1/4/1 commits; veto only in candidate 3; proposer's own support not counted — discriminating); individual_reply byte-identical to the directive's verbatim fixture lines.

## C5 — Control-plane maintenance: HOLDS-WITH-FINDINGS

Verified: upstream_protected in every mode's forbidden set and blocked unconditionally by the gate; frozen mode measures against frozen_sha and includes tests; real JSON comments still rejected via strict parse; the new regression tests are discriminating; classify_path ordering safe for in-repo paths (upstream/test checked before doc).

Findings:
- HIGH (pre-existing, exposed) — the actual pinned upstream checkouts classified `external`, which no mode blocks: a `sed -i` in /home/user/concordia would silently change the engine under contract with no repo diff. [FIXED: `classify_path` now returns upstream_protected for paths inside recorded `local_checkout` trees (every mode blocks them); continuous integrity check added; regression tests in both gate and validator suites.]
- MEDIUM — UPSTREAM_LOCK.json classified freely-editable production. [FIXED: protected via `protected_paths` with `audit_exempt` (write-blocked in every mode; branch-diff audit skips its legitimate creation); discriminating tests both ways.]
- MEDIUM — ACCEPTANCE_GATES.md reclassified doc → editable during freeze, unpinned. [ACCEPTED with mitigation: Phase 12 freeze protocol records sha256 of gate-definition docs in the freeze record; the hash-pinned directive remains authoritative. Recorded in the Phase 12 task contract.]
- LOW — no frozen-mode test-path gate coverage. [FIXED: `test_frozen_acceptance_blocks_test_edits` incl. a fixtures path.]
- LOW — "docs explicitly editable during freeze" overstated HOOKS_README §5 (implied by omission). [ACCEPTED: wording note; behavior unchanged and now test-pinned.]

## C6 — Receipts: HOLDS-WITH-FINDINGS

Current phase receipts verified genuine (commands match claims; reviewer reproduced 39/39 and the fixture hashes independently).

Findings:
- LOW-MEDIUM — "every receipt is exit_code 0" was false as stated: the superseded first phase-0 receipt records exit 1 (the very run that exposed the validator defects). Mechanically inert (receipt_is_passing requires exit 0; a later passing receipt exists at the same SHA) and disclosed in the task graph. [ACCEPTED as historical evidence; kept deliberately.]
- MEDIUM-HIGH (systemic) — receipts recorded on dirty worktrees whose base SHAs lack the tested artifacts; `configuration_hashes` empty for phase-2; task-graph completion SHAs not audit-exact. [PARTIALLY FIXED + POLICY: task-graph `completed_at_sha` backfilled to the artifact-bearing commits; henceforth phase receipts carry `--config-hash` for key artifacts and are re-recorded at the artifact-bearing commit when feasible; the residual property that a receipt can never live inside the commit it attests to is inherent and documented (DECISIONS "Receipt re-record protocol").]

## Highest-leverage weakness (reviewer's words)

"The evidence chain's SHA discipline is nominal, not real, and the engine itself sits outside the enforcement perimeter. … The single most exploitable point: an agent can silently edit /home/user/concordia or /home/user/agentsociety2 (editable installs, no hook fires, no repo diff appears), invalidating every 'pinned upstream' contract until the next manual gate-A check."

[DISPOSITION: the named exploit is closed (hook blocks the checkouts in every mode + continuous integrity check); the receipt-discipline hardening is applied as above.]

## Phase 4 blocker?

**No.** All pins genuine; baselines match records; the contract suite is substantive on exactly the seams Phase 4 needs; fixtures verified. Findings were hardening work, all dispositioned above.
