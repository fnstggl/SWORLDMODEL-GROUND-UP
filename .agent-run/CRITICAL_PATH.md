# Critical Path

Status: INITIALIZED_FROM_MASTER_DIRECTIVE
Derived from `docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md`
(sha256 `ac863c8355fab544fc79c8a440ed643b8b0879147209134868985dec67a0cdbb`).

One explicit path from the present state to the final adjudication. Work the
first unmet step; do not open unrelated fronts. WIP limit: one primary
implementation task plus at most one independent background validation batch.

0.  DONE  Hook bootstrap + live verification + merged control plane (main
          `87f8c3d29cc7901d0d7d6ed835190cbde6fb3059`).
1.  DONE  Master-context initialization handshake: directive saved verbatim,
          sha256 recorded, `.agent-run` populated, validator PASS,
          current-SHA `master-context-initialization` receipt recorded,
          mode `ready_for_master` → `implementation`.
2.  NEXT  Re-verify state at session start (validator; if the master-init
          receipt is stale because HEAD moved, re-record it at the current
          SHA), then create the implementation branch
          `claude/concordia-agentsociety-best-action-engine` from updated
          main containing this initialization, and open the draft PR into
          main (directive mandatory first actions, steps 11–12).
3.  Three-repository audit (Concordia, AgentSociety 2, SWORLDMODEL) →
    `docs/engine_migration/{UPSTREAM_AUDIT,SWORLD_CURRENT_STATE,
    OWNERSHIP_MAP,INTEGRATION_PLAN,RISK_REGISTER,ACCEPTANCE_GATES,
    OWNERSHIP_AND_REPLACEMENT_MAP}.md. Production implementation is gated on
    the audit gates passing (directive step 13).
4.  Phase 0 — freeze and baseline: record all three repo SHAs, Python/dep
    requirements, run existing suites and upstream smoke examples, save
    baseline artifacts. No production routing changes.
5.  Phase 1 — dependency preservation and compatibility: pin complete
    upstream repos; `third_party/` lock, notices, integration method,
    PATCHES.md (initially: no patches); prove imports coexist and minimal
    upstream examples run. Feeds gate A.
6.  Phase 2 — upstream contract tests (Concordia lifecycle/memory/GM;
    AgentSociety workspaces/concurrency/failure isolation/accounting).
    No application logic before these pass.
7.  Phase 3 — decision and branch contracts (fixed SWORLDMODEL schemas +
    strict schema/semantic validation tests), and commit the three frozen
    manual best-action fixtures with recorded hashes and expected
    deterministic results.
8.  Phase 4 — stock Concordia local baseline: hard gate — two manually
    written scenarios end-to-end, no compiler import anywhere in the
    execution path; freeze the baseline. Feeds gate C.
9.  Phase 5 — minimum agency guard (thin; no Game Master fork); Concordia
    loop still works.
10. Phase 6 — counterfactual branch manager: two manual interventions from
    one frozen snapshot, explicit outcome comparison. Feeds gate E.
11. Compiler-to-Concordia adapter (only after the frozen manual fixtures
    pass): COMPILER_TO_CONCORDIA_MAPPING.md, deterministic
    ConcordiaInitializationPlan, canary information-leak tests, manual vs
    compiler-produced equivalence.
12. Phase 7 — AgentSociety branch executor (Stage A): distributed complete
    branches; local ≡ distributed under deterministic models. Feeds gate F.
13. Phase 8 — Concordia actor workspace adapter (Stage B): whole-branch
    checkpoint persistence and deterministic restore equivalence.
14. Phase 9 — individual vertical slice (recipient owns the reply; evaluator
    reads the trace). Feeds gate C.
15. Phase 10 — team vertical slice (5–12 people, private info, authority,
    votes/commitments owned by actors). Feeds gate D.
16. Phase 11 — societal infrastructure proof (Stage C): 100-job and
    1,000-job monitored runs with explicit progress sources, failure
    injection, resume, aggregate collection. Feeds gate G. Infrastructure
    only — no realism claim.
17. Ongoing at every phase boundary: adversarial review; fix verified
    findings; failure ledger + strategy escalation on repeats. Feeds gate H.
18. Operational robustness matrix (interrupt/resume, malformed inputs,
    missing credentials, Ray worker failure, workspace corruption). Feeds
    gate I.
19. Final documentation set under `docs/engine_migration/`. Feeds gate J.
20. Phase 12 — frozen final acceptance: freeze one commit, clean tree, run
    the complete suite from the beginning through the monitored runner; any
    failure ⇒ fix, new frozen SHA, restart the whole batch.
21. Final adjudicator reads actual artifacts → `ACCEPTANCE_STATUS.json`
    overall PASS. Only then may the run terminate (or a genuine
    EXTERNAL_BLOCKER at any earlier point).
