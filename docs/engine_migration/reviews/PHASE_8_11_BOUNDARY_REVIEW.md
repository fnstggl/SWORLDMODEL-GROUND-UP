# Adversarial review — Phases 8–11 boundary at c80787e

> Findings report of the read-only adversarial reviewer, 2026-08-03, with
> per-finding dispositions applied by the lead in the same session. The
> reviewer's full text is preserved in the session transcript; this document
> records every finding, the gate-H clause table, and each resolution
> (gate H trail, third boundary review after 0–2 and 3–7).

## Verdicts

D1 checkpoint: holds-with-findings · D2 guard hardening:
holds-with-findings · D3 adapter mapping: **holds** (no silent-discard
input could be crafted) · D4 slice evidence: holds-with-findings · D5
scale evidence: **holds** (52/52 hashes reverified; negative proofs
live) · D6 suite hygiene: holds-with-findings. The reviewer
independently reproduced the nine-suite battery at 235 passed, verified
frozen fixtures against FIXTURES.sha256, and verified both upstream
checkouts clean at their pins.

## Gate H clause table (as reviewed → after dispositions)

| Clause | Review verdict | After disposition |
|---|---|---|
| qualitative incentives, no numeric social weights | confirmed | confirmed |
| voluntary decisions belong to the affected actor | **refuted (F1)** | restored by the F1 fix; re-confirmation scheduled with the frozen-SHA review |
| GM not an arbitrary final outcome decider | confirmed | confirmed |
| no unexplained social weights | confirmed | confirmed |
| no actor receives unobservable information | confirmed | confirmed |
| no outcome counted unless in trace/world state | **refuted (F1)** | restored by the F1 fix; re-confirmation scheduled with the frozen-SHA review |
| no irrelevant daily-life detail | confirmed | confirmed |
| intervention-centered | confirmed | confirmed |

## Findings and dispositions

1. **F1 — HIGH — colon/dash proxy attribution.** `Name:` / `Name --`
   (upstream EventResolution's own attribution separators) evaded the
   guard's whitespace-adjacent subject detector, and the slice
   evaluators' "attribution anchors" accepted substring co-occurrence
   anywhere in a row — one actor could cast another's reply/vote/veto
   and have it counted (reviewer reproduced end-to-end on both slices:
   fabricated recipient reply → terminal success citing the sender's own
   row; non-authority proxy veto → terminal flip). **FIXED (1f8404b)**:
   guard detection class 6 treats colon/dash as subject-attribution
   boundaries for non-active roster names (content-blind, existing
   suppression semantics; active player's own attribution passes
   anywhere); evaluator anchors bind to the row's OWN leading
   attribution == the predicate-named actor with the opening-adjacency
   requirement; all four reviewer probes reproduced BEFORE (pass-through
   / miscount) and AFTER (rewritten + escalation records; metrics False;
   no terminal flip); 19 discriminating tests added; committed example
   artifacts byte-identical; battery 235 → 254; PYTHONHASHSEED 0/5/13
   green; guard-hashing receipts (agency-guard-hardening, phase-5)
   re-recorded at the fix commit. New honestly-documented residuals in
   the guard docstring: single em/en-dash separators, line-split names,
   marker-after-aside, received-content colon frames after non-agent
   lead words, and same-line over-removal (recoverable direction —
   removal + availability, never invented agency). **Lead follow-up in
   the same session**: the counterfactual suite's fixture predicates
   (tests/engine_counterfactuals/cf_helpers.py) still used the bare
   substring shape outside the fix agent's ownership — rewired onto the
   same leading-attribution anchor with a three-test discriminating
   module (test_predicate_attribution.py); consumer suites
   (counterfactuals 23, distributed 7, checkpoint 16) unchanged-green.
2. **F3 — MEDIUM — validator FAIL at HEAD** (`initialization_level`):
   the documented one-commit master-receipt re-record lag, plus the same
   single failure in the control-plane suite's end-to-end test.
   **DISPOSITIONED (mechanical)**: the Phase 12 freeze sequence ends
   with the master-context receipt re-recorded at the frozen SHA so the
   validator PASSES at the SHA being adjudicated. Not a defect; the lag
   self-heals at every fold-in and the frozen run pins it permanently.
3. **F2 — LOW — checkpoint stored_hashes canonicalization untested.**
   The defensive sort branch was inert against current objects (builder
   refuses non-ListMemory backends) and had zero live coverage; the code
   and DECISIONS disclosed this honestly. **FIXED (1f8404b)**: dedicated
   unit module (test_state_canonicalization.py, 4 tests): permutation
   identity at tree and canonical-bytes level, nested-in-list depth,
   passthrough without the key, non-string entries verbatim. No
   production change.
4. **F4 — LOW — scale reconciliation trust boundary.** The big-run
   file-vs-ledger equality is asserted from committed self-attested
   reconciliation fields (raw unit ledgers live outside the repo);
   mitigations already in place: the reconciliation code path has live
   small-N negative controls (drop/duplicate a real action line →
   refusal naming the agent) and the rollup hash chain is recomputed
   from committed summaries. **ACCEPTED** as a disclosed two-tier
   design; recorded here and in PHASE11_SCALE_EVIDENCE.md.

## Attacks that failed (reviewer-verified strengths)

Checkpoint A=A'=B is genuinely discriminating (naive-reseed control
diverges; distributed fresh-process resume byte-equal; tampered-
checkpoint refusals comprehensive). Adapter: dup-visible_to,
name-collision, case-collision, unicode-lossy manifests all refused
loudly or mapped losslessly; output byte-identical across 5 runs. Scale
evidence: 52/52 hashes recompute; per-tick actions sum exactly; hash
chains equal in both directions. Hygiene: per-suite counts reconcile
with every receipt claim; no flakes under the reviewer's runs.

## Freeze decision trail

Reviewer: F1 blocks robustness/freeze until dispositioned; F3 must be
cleared mechanically at the freeze. Lead: F1 fixed same-session (not
accepted-as-residual), F2 fixed, F3 scheduled into the freeze sequence,
F4 accepted. The two F1-refuted gate-H clauses are restored by
construction and will be re-confirmed by the reviewer role at the frozen
SHA before adjudication. Nothing now blocks the operational-robustness
and documentation phases.
