# Adversarial review — Phases 3–7 boundary at db41689

> Findings report of the read-only adversarial reviewer, 2026-08-03, with
> per-finding dispositions applied by the lead in the same session. The
> reviewer's full text is preserved in the session transcript; this document
> records every finding and its resolution (gate H trail).

## Verdicts

D1 contracts: holds-with-findings · D2 agency guard: holds-with-findings ·
D3 counterfactuals: holds · D4 ranking: holds-with-findings · D5
distributed: holds-with-findings · D6 suite hygiene: **broken** (two HIGH).
Nothing blocked Phase 8 from starting.

## Findings and dispositions

1. **HIGH — flaky test (~1/8 process launches)**: upstream
   `AssociativeMemoryBank.get_state` serializes a SET of salted hashes;
   PYTHONHASHSEED 5/13 reproduce ordering flips failing
   `test_get_state_set_state_round_trips_memory_to_fresh_agent`; undocumented,
   and a Phase 12 frozen-batch coin-flip. **FIXED**: comparison canonicalized
   (stored_hashes sorted; semantics unchanged — set_state rebuilds a set);
   verified under seeds 5/13/0/7; FAILURE_LEDGER entry
   `hash-order-sensitive-state-comparison`; the Phase 8 writer was warned the
   same mechanism affects cross-process checkpoint serialization and must
   canonicalize checkpoint state (acknowledged in its brief).
2. **HIGH — phase receipts not completion-grade**: every phase 3–7 receipt was
   a dirty-worktree run at the completion commit's parent SHA; the validator
   never checked phase tasks; rule 7 decorative. **FIXED** (hook maintenance
   #4): new validator check `phase_receipt_discipline` — a completed task's
   newest passing receipt must be clean-worktree OR carry configuration_hashes
   that all match the current files (content continuity; label-only hashes
   rejected); six discriminating tests; receipts re-recorded at clean HEAD
   with path-labeled hashes (Ray-suite receipts p2/p7 re-recorded at the
   Phase 8 fold-in to avoid contending with the active writer's Ray tests —
   until then the check names exactly those two, honestly).
3. **Medium — contracts alias caller-owned mutable state**
   (terminal_world_state, concordia_checkpoint aliased by reference; mutation
   after the gate changed content_hash). **FIXED**: defensive deep copies at
   ingest and egress; contract tests green.
4. **Medium — ranking polarity opacity**: a "bad" declared secondary can crown
   the measurably worse candidate with an all-green status. **FIXED**:
   `validation_status.decided_by_metric` names what separated the top two
   (metric name / candidate_id_tie_break / single_candidate); module docstring
   states the descending imposition honestly; `_recommendation_semantics` now
   re-validates the FULL declared-order key (a primary-honoring,
   secondary-inverting ordering fails); contract widened to allow short string
   status values (recorded in DECISIONS).
5. **Medium — worker-side seeded scope unproven** (scripted models consume no
   RNG; deleting the template's `_seeded_branch_scope` would pass all tests).
   **QUEUED (accepted for Stage A, required before Phase 12)**: add a
   distributed equivalence candidate whose model consumes per-document RNG —
   scheduled with the Phase 8 fold-in alongside the p7 receipt re-record.
6. **Medium — guard evasions beyond documented gaps** (parenthetical commas,
   nominalizations, pronoun/collective subjects) + over-block of belief-verb
   complements ("hopes Morgan agrees") and performative content ("asks that
   Morgan reply by Friday" → content removed). Reviewer judged the DEFAULT
   constrained path safe today (GM authors no event text; only actor-authored
   shapes can occur) but a live directive hole at Phases 9–10. **QUEUED
   (blocking Phase 9 start)**: guard hardening task — pronouns/perfects/
   nominalizations/belief-verb complements — plus the honesty item below.
7. **Medium (process) — hardcoding-guard mechanism circumvention**: the lemma
   stem+suffix table exists to evade the scanner's word list; substantively
   generic (the directive's own act categories) but the sanctioned remedy is a
   documented ALLOWLIST entry. **QUEUED with guard hardening**: add guard.py
   to the hardcoding-guard allowlist with justification and simplify the
   table to plain literals.
8. **Low** items — equality/hash looseness (`1` vs `1.0` etc.), NFC/NFD,
   `apply_intervention` malformed-window silent skip, ok=False partial-result
   runner-record tolerance asymmetry, runner-record text not signature-compared
   cross-leg: **ACCEPTED** with notes; revisit only if they bite (ledgered
   rationale: byte-level identity is the defined bar; registry validation
   remains the gate for the skipped window check).
9. **D6 verification results** (reviewer's own runs at db41689): engine suite
   run1 1F/106P (the flake), run2 107P; system suite 672P/21S with only the
   documented receipt item; fixtures hash-verified; upstream checkouts clean
   at pins. Consistent with the run's claims apart from the two HIGHs above.

## Reviewer's three hardening actions → status

1. Kill the flake → DONE (+ Phase 8 checkpoint canonicalization directive).
2. Completion-grade receipts + validator enforcement → DONE (p2/p7 re-record
   at Phase 8 fold-in).
3. Worker-RNG equivalence candidate → QUEUED at Phase 8 fold-in (pre-freeze
   requirement).
