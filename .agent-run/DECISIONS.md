# Decisions
## Bootstrap decisions
- Use project-scoped Claude Code hooks.
- Use `/goal` as the primary lead-session continuation mechanism.
- Do not install Ralph for this workflow.
- Store changing execution state under `.agent-run/`.
- Require monitored execution for long-running jobs.
- Do not initialize detailed product architecture before the master directive is loaded.

## Hook maintenance 2026-08-03 -- shell write-target detection must be shell-aware

Entered `hook_maintenance` from `hook_live_verification` (previous mode kept in
`phase`) because live verification exposed a defect in `PreToolUse`.

**Defect.** `gate._shell_written_paths` decided which paths a `Bash` command
writes to by running regexes over the raw command text. Text matching cannot
tell a shell operator from the same characters appearing inside a quoted string
or a heredoc body, and it does not model each tool's argument grammar. Both
error directions were reproduced:

- *False positives* (observed live, twice, within minutes of starting live
  verification): `echo "VAR=${FOO:-<unset>}"` was denied as a write to `}`, and
  a `grep`/heredoc mentioning `sed -i s/a/b/` was denied as a write to `s/a/b`.
  Ordinary read-only commands were blocked.
- *False negatives* (reproduced against a synthetic project in
  `implementation` mode): `sed -i` captured the sed *script* instead of the
  file operand, so the capture fell through to the `production` category, which
  is allowed outside a freeze. `sed -i 's/deny/allow/' .claude/hooks/gate.py`,
  `sed -i 's/a/b/' .claude/settings.json` and an in-place edit of a pinned
  upstream path were all **allowed** -- defeating the hook-control and
  upstream-protection rules that `CLAUDE.md` rule 10 depends on.

**Smallest general cause.** Write-target detection was text matching rather than
shell-aware parsing. One cause, both symptoms.

**Fix.** `hook_state.shell_write_targets` now strips heredoc bodies (stdin data,
not shell syntax) and reuses the module's existing quoting-aware tokenizer, then
reads redirection operators as tokens and extracts real file operands for the
in-place writers (`tee`, `sed -i`, `truncate`), skipping options, option
arguments and the sed script. `gate._shell_written_paths` delegates to it. No
gate was weakened: the change removes false allows as well as false denials.

**Regression coverage.** `tests/control_plane/test_gate.py` gained direct
`shell_write_targets` unit tests plus end-to-end cases for the quoted-mention
false positives, the in-place-edit bypasses, quoted redirect targets, read-only
`sed`, and file-descriptor duplication.

### Outcome of the write-target fix

`tests/control_plane` went from 194 to 211 tests (112 to 141
subtests), all passing under `PYTHONHASHSEED` 0/1/7/42/12345/99991.
`validate_control_plane.py --run-tests` returns PASS. All three reproduction
probes are clean: 0 false positives, 0 missed detections, 0 bypasses. Mode
restored to `hook_live_verification`, and live verification was restarted from
the beginning against the post-fix commit -- no evidence from the pre-fix
configuration was counted.

## Hook maintenance 2026-08-03 -- ConfigChange read a payload field that does not exist

Entered `hook_maintenance` from `hook_live_verification` a second time.

**Defect.** `handle_config_change` resolved the changed-settings source with
`first_present(event, "config_source", "configSource")`. Live payloads captured
in this session name that field **`source`**, so every real change resolved to
`"unknown"`. An unknown source is never in `BLOCKING_CONFIG_SOURCES`, so the
handler fell through to `allow()`: **the ConfigChange gate could not block
anything in live operation.** Two real project-settings edits were logged with
`"config_source": "unknown"` and no `config_changes` key at all.

The static suite passed throughout because its `config_event()` helper built
the synthetic `config_source` spelling -- a shape live payloads never send.
This is exactly the class of defect fresh-session live verification exists to
catch, and it is invisible to static testing by construction.

**Observed live payload:** `session_id`, `transcript_path`, `cwd`, `prompt_id`,
`hook_event_name`, `source`, `file_path`.

**Smallest general cause.** A safety gate identified its subject from an assumed
payload field name and treated "field absent" as "nothing to block" -- failing
*open* on a gate the hooks README declares fail-closed.

**Fix.** Two parts, because the field name alone would leave the same trap set
for the next rename:
1. `handle_config_change` reads `source` first, keeping `config_source` /
   `configSource` as alternates, and now also logs the changed file path.
2. An *unidentifiable* source during `implementation` / `frozen_acceptance`
   (outside recorded hook maintenance) now **blocks**, naming the payload fields
   that were actually present, instead of silently allowing. Outside those
   protected modes it still allows, so nothing is trapped.

**Regression coverage.** `tests/control_plane/test_gate.py` gained a
`live_config_event()` helper built from the captured real payload, and the whole
block/allow matrix is re-run against that shape, plus fail-closed tests for an
unrecognised source and a test that the logged record names the payload fields
when the source cannot be identified.

**Method note.** The payload was captured by temporarily registering a
throwaway diagnostic hook that recorded the raw event JSON, then removing it.
The validator's `settings_hook_shape` check correctly failed while that
temporary hook was registered, because its command used an absolute path rather
than `${CLAUDE_PROJECT_DIR}`. `.claude/settings.json` was restored byte for
byte afterwards (sha256
`ad585f6ae64c10d131664d5818611ed10b6aed0bcbe7df723acf0992ba620582`).

### Outcome of the ConfigChange fix

Static suite green; the deterministic gate matrix runs the whole ConfigChange
block/allow table against BOTH payload shapes. Mode restored to
`hook_live_verification` and live verification restarted from the beginning
against the post-fix commit.

## Finding 2026-08-03 -- TeammateIdle is never emitted in this environment

Not a defect in the hook, and not fixed by changing code: recorded because it
materially limits what the control plane actually guarantees here.

The same diagnostic technique was pointed at `TeammateIdle`. Across three
genuine idles by a named teammate that owned an in-progress task with a missing
required artifact, **zero `TeammateIdle` invocations were observed**. Two
independent detectors agree: the throwaway dumper captured nothing (while
provably writing, verified by a self-test), and the real gate -- registered on
the same event -- never blocked the teammate.

The registration is correct, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set and
reaches the process environment, and the running Claude Code is 2.1.220, exactly
the version `.claude/HOOKS_README.md` claims the contract was verified against.
The README's assertion that `TeammateIdle` is live in this configuration is
therefore **unverified in this remote, non-interactive environment**.

Consequence: the "no silent abandonment" guarantee is not in force for
Agent-tool subagents here. `TeammateIdle`'s handler logic is fully covered by
the harness and by the static suite, but nothing was observed to invoke it.
Clearing this needs an interactive agent-teams session; see
`.agent-run/RUN_STATE.json` `external_blocker`.

## Resolution 2026-08-03 -- TeammateIdle is UNAVAILABLE_IN_CLAUDE_CODE_WEB, and is not a master-run blocker

The check above was re-run once, cleanly and bounded, from a **Claude Code on
the web** session (`CLAUDE_CODE_ENTRYPOINT=remote`, `CLAUDE_CODE_REMOTE=true`,
Claude Code 2.1.220, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`), with the hook
configuration byte-identical to the verified commit
`190b04e5b2f8652bd1d7a88f847c101f3161243a`. It did not fire. This entry records
the decision to stop treating that as a blocker.

**Why the result is trustworthy this time.** The previous attempt inferred
non-emission from a throwaway diagnostic hook. This one used the host's own
debug log, `/tmp/claude-code.log` (`CLAUDE_CODE_DEBUG=true`), which is written by
the Claude Code process itself and names every hook it invokes. That detector
was validated *inside the same measurement window* by a positive control: the
teammate was told to attempt a `Write` to `.claude/hooks/__idleprobe__.txt`, and
the host log recorded the resulting denial as
`Hook PreToolUse:Write (PreToolUse) success: {... "permissionDecision": "deny" ...}`.
So the log demonstrably captures hook invocations that occur in a teammate's
execution context.

**The measurement.** Log bytes 90452 to 105260, 121 lines, covering the
teammate's whole life. Zero occurrences of `Teammate` or `TeammateIdle`. The
window's hook invocations reconcile exactly: six `Bash` dispatches produced six
allow lines, one `Write` produced the one named denial, and `Agent` is not in the
`PreToolUse` matcher. **No unexplained hook invocation exists**, so the event did
not fire silently either.

**Not a missing feature -- a missing emission path.** The 2.1.220 binary
contains the literal string `TeammateIdle` 21 times. The event exists in this
build; this execution surface never reaches the code that emits it for
Agent-tool teammates.

**What that costs.** The teammate owned `tmp-teammate-idle-name`, status
`in_progress`, with a `required_artifacts` entry that did not exist. It finished
and went idle with the work unfinished and nothing stopped it. That is the
concrete demonstration that "no silent abandonment" is not enforced by a hook
here. The gate remains registered and its handler is fully covered by the static
suite, so it will take effect unchanged on any surface that does emit the event.

**Decision.** `TeammateIdle` is recorded as `UNAVAILABLE_IN_CLAUDE_CODE_WEB` and
treated as **optional**, not as a gate the master run must clear. Silent
abandonment is instead covered by four controls that *are* live-verified at
`190b04e`:

1. `TaskCompleted` -- blocks marking a task complete without its declared
   artifacts and a passing current-SHA receipt. This is the control that matters
   most, because abandonment that tries to look like completion is stopped here.
2. `SubagentStop` -- blocks `implementation-agent` and `test-watchdog` from
   stopping on an incomplete contract, which covers the protected writer roles
   that do the production work.
3. `Stop` -- blocks the lead from ending the run while gates are unmet, so an
   abandoned task cannot leave the run silently.
4. Explicit task ownership in `TASK_GRAPH.json` plus lead-agent review of every
   teammate return. Ownership is declared before the work starts, so an
   unfinished task is visible in durable state regardless of whether any hook
   fired.

The residual gap is narrow and stated plainly: an *unprotected* teammate type
that abandons work **without** claiming completion is caught by the lead's review
and by `TASK_GRAPH.json`, not by a hook. `.claude/HOOKS_README.md` is corrected
to say so rather than to promise enforcement it does not deliver here.

**Control-plane change made under this entry.** Entered `hook_maintenance` to
correct `.claude/HOOKS_README.md` sections 1 and 2, and to fix a validator rule
that made `overall: PASS` unreachable for any documented environment limitation:
`check_bootstrap_status_consistent` required `live_event_tests == "PASS"`
verbatim, so an honest result could never be recorded as PASS. It now also
accepts `PASS_WITH_DOCUMENTED_LIMITATION`, and only when the limitation is
explicitly declared -- naming a registered hook event, carrying a reason, and
leaving every other live check at `PASS`. The rule was loosened in exactly one
place and made stricter about evidence in three.

## Master-context initialization 2026-08-03

- **The master implementation directive is loaded and authoritative.** Saved
  verbatim (no summarizing, no rewriting) at
  `docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md`, sha256
  `ac863c8355fab544fc79c8a440ed643b8b0879147209134868985dec67a0cdbb`, recorded
  in `RUN_STATE.json.master_directive_sha256`. Where any `.agent-run` summary
  and the directive disagree, the directive wins.
- **Branch authority.** This initialization was performed, per the operator's
  explicit branch designation for this session, on
  `claude/engine-migration-setup-j5d0ti` (created from main
  `87f8c3d29cc7901d0d7d6ed835190cbde6fb3059`, the latest main containing the
  merged verified control plane). The directive's implementation branch
  `claude/concordia-agentsociety-best-action-engine` is to be created from
  updated main once this initialization lands there (directive: "Begin from
  the latest remote main after the verified control-plane PR has been merged"
  + mandatory first action 4); the draft PR into main is opened from that
  implementation branch and not merged during the run. If the master run
  starts before this setup branch is merged, it continues from this
  initialized branch state rather than re-deriving it.
- **Upstream baselines recorded at initialization.** Local fork checkouts:
  concordia `7779a4c9f96bad10816d88c54e4cb17d53ac5222`
  (fnstggl/concordia, upstream google-deepmind/concordia); agentsociety2
  `6e9fc2e79f89f65a3e3d0d7899e380f7394099be` (fnstggl/agentsociety2, upstream
  tsinghua-fib-lab/agentsociety). These are baselines for the audit; Phase 1
  pins the immutable integration SHAs in `third_party/UPSTREAM_LOCK.json`,
  which then becomes the pin of record.
- **Protected upstream paths registered ahead of import.**
  `third_party/concordia/` and `third_party/agentsociety/` are protected now,
  before they exist, so no divergent local copy can appear by accident. The
  sanctioned Phase 1 import window procedure is documented in
  `UPSTREAM_PROTECTED_PATHS.json.import_procedure`.
- **Receipt re-record protocol.** A `master-context-initialization` receipt is
  valid only at the exact SHA it records; committing the receipt necessarily
  moves HEAD past it (`.claude/HOOKS_README.md` §4: re-record after committing
  or rebasing). Every fresh session in `implementation` mode therefore starts
  by running the validator and, if the only failure is a stale
  `master-context-initialization` receipt, re-records it at the current SHA
  via `python3 .claude/tools/record_receipt.py --task-id
  master-context-initialization --run -- python3 -m pytest
  tests/control_plane -q` (when pytest is absent, the equivalent fallback the
  validator itself uses: `... --run -- python3
  tests/control_plane/test_gate.py`) followed by a validator re-run, and
  optionally a second receipt recording the validator PASS itself. This is
  re-verification at the new SHA, not new authority. Applied at
  initialization: transition receipt at 87f8c3d29cc79, re-recorded suite +
  validator-PASS receipts at the initialization commit that followed it.
- **TeammateIdle remains UNAVAILABLE_IN_CLAUDE_CODE_WEB** (inherited from
  bootstrap, unchanged): rely on TaskCompleted, selective SubagentStop,
  explicit task ownership in TASK_GRAPH.json, and lead review at phase
  boundaries, exactly as the directive's fallback list requires.
- **Phase 0 baseline artifact path fixed as**
  `docs/engine_migration/PHASE0_BASELINE.md` so the phase's completion
  contract is machine-checkable from the task graph.

## Hook maintenance 2026-08-03 -- change audit was bootstrap-only; docs misclassified as evaluators

Entered `hook_maintenance` from `implementation` (previous mode kept in
`phase`) because the Phase 0 receipt run demonstrated two validator defects.

**Defect 1 (blocking by design, wrongly).** `validate_control_plane.py::
check_no_production_changes` unconditionally forbade `production`,
`evaluator`, `fixture`, and `prompt` categories in the branch diff versus
main. That rule encodes the *hook-bootstrap* discipline ("the control plane
may add its own files and its own tests, and nothing else"). Once the
master-context handshake has passed and the mode is `implementation`,
changing production/evaluator/fixture/prompt code is the entire point of the
run -- with the check as it stood, the validator could never PASS on any
commit that adds engine code, making every downstream current-SHA receipt
unattainable. Demonstrated live: the full suite failed on
`docs/engine_migration/ACCEPTANCE_GATES.md (evaluator)` -- a documentation
file whose creation is directive-mandated.

**Defect 2.** `hook_state.classify_path` ran the evaluator/fixture/prompt
filename heuristics *before* the `docs/` prefix rule, so any documentation
path containing words like "acceptance" or "evaluation" classified as
`evaluator` material. Documentation is explicitly editable even during a
frozen acceptance batch (HOOKS_README §5), so this order is wrong in general.

**Smallest general causes and fixes.**
1. `classify_path` now classifies `docs/` (and root-level `*.md`) as `doc`
   before applying the evaluator/fixture/prompt heuristics. Non-doc paths
   (`evaluation/score.py`, `acceptance/gate.py`, `worlds/*.json`,
   `*/prompts/*`) classify exactly as before.
2. `check_no_production_changes` is now mode-aware, with the forbidden set
   reported in its payload (`forbidden_categories`): bootstrap modes keep the
   original strict set; `implementation` (and hook_maintenance / complete /
   external_blocker) forbid only `upstream_protected`; `frozen_acceptance`
   forbids production/evaluator/fixture/prompt/test changes measured against
   `RUN_STATE.frozen_sha` (and fails outright if frozen_sha is unset). Pinned
   upstream source stays inviolable in every mode.

**Regression coverage added.** `tests/control_plane/
test_validate_control_plane.py`: docs-over-heuristics classification tests;
a git-backed mode-awareness suite proving (a) implementation mode accepts a
production diff, (b) implementation mode still rejects a pinned-upstream
diff, (c) bootstrap mode still rejects a production diff, (d) frozen
acceptance passes when nothing changed since frozen_sha and fails on a
production change after it, and (e) frozen acceptance without frozen_sha
fails. The end-to-end repository test now derives the allowed categories from
the check's own reported `forbidden_categories` instead of hardcoding the
bootstrap set.

Also cleaned: a stray `argv.json` written into the repo root by the
AgentSociety baseline suite (their tests write it to the invoking cwd);
future upstream-suite runs cd into the upstream checkout first. Recorded in
FAILURE_LEDGER.jsonl.

**Outcome.** A third defect of the same naive-text-scan class surfaced during
revalidation and was fixed in the same window: `check_json_parses` flagged any
`//` or `/*` in the raw file as "comment syntax", which false-positived on
URLs inside legitimate JSON string values (live case: monitored-job commands
in `BACKGROUND_JOBS.json` carrying `http://localhost:9`). Since the strict
`json.loads` parse already rejects every real comment form, the raw-text scan
was removed and a regression test added (`test_urls_inside_string_values_are_
not_comments`); `UPSTREAM_PROTECTED_PATHS.json` URLs were restored to full
`https://` form. Revalidation: validator suite 81 tests OK, gate suite OK,
`validate_control_plane.py --run-tests` PASS (hook suite 131 passed + 93
subtests; runner suite 25 passed). Mode restored to `implementation`.


## Hook maintenance 2026-08-03 (#3) -- external checkouts entered the enforcement perimeter

Trigger: Phases 0-2 adversarial review (verbatim report + per-finding
disposition: docs/engine_migration/reviews/PHASE_0_2_BOUNDARY_REVIEW.md).
Its HIGH finding demonstrated live that the pinned upstream checkouts
classified `external`, which no mode blocks -- an editable-install source
edit would silently change the engine under contract.

Changes (all with discriminating regression tests, suites green,
`validate_control_plane.py --run-tests` PASS):
1. `classify_path` returns `upstream_protected` for any path inside a
   recorded `repositories[].local_checkout` tree -- blocked in EVERY mode.
2. New validator check `upstream_checkouts_integrity`: every recorded
   checkout that exists must sit at its recorded SHA with zero local
   modifications, on every validator run (absent checkouts are noted, not
   failed).
3. `third_party/UPSTREAM_LOCK.json` is now write-protected via
   `protected_paths` with the new explicit `audit_exempt` flag: PreToolUse
   blocks edits in every mode, while the branch-diff audit skips its
   legitimate creation on this branch. Pin changes require the documented
   exception procedure.
4. Frozen-mode gate coverage for `tests/**` paths added (reviewer LOW).

## Phase 0-2 boundary review outcome 2026-08-03

All six reviewed claims HOLD; no Phase 4 blocker. Non-maintenance fixes
applied in the same session: three weak engine-contract tests strengthened
(steady-state overlap == 2 after a warm-up round -- cold-start serialization
was real and is now measured around; rng-restoration tautology replaced with
a real restore assertion; token_stats exact-empty + shape contract);
provenance corrected (ScriptedByEntityModel is upstream commit 1372a37; the
pinned fork SHAs equal upstream main -- pure mirrors); baseline
dirty-worktree disclosure added; receipt-discipline policy hardened
(completed_at_sha backfilled to artifact-bearing commits; phase receipts
carry --config-hash going forward). ACCEPTED items: ACCEPTANCE_GATES.md
stays a doc, mitigated by hashing gate-definition docs into the Phase 12
freeze record; the historical exit-1 phase-0 receipt is kept deliberately as
evidence of the defect it exposed.

## Fixture 3 syntax re-freeze 2026-08-03

Phase 3 found `population_offer.yaml` unparseable by conforming YAML
parsers: a plain-scalar bullet ended with a line-final colon (illegal
multi-line mapping key). Adjudication: syntax-only re-freeze -- the colon
became ", meaning" with zero semantic change (rules, counts, expectations
byte-identical otherwise); new sha256
93537342df26761bc67cb6cbb6aedc89531a9ab8719040be283047928b418985 recorded in
FIXTURES.md + FIXTURES.sha256; the loader test now asserts ALL fixtures are
conforming YAML and that the textual prose-block layer agrees with YAML's
own parse. Rationale: the wart would compound forever; the immutability rule
targets semantic gaming, not syntax validity; final acceptance has not
begun. The frozen-manual-fixtures receipt is re-recorded against the new
hashes.


## Phase 5 notes 2026-08-03

- Guard plan-shape deviation (forced by the frozen Phase 3 contract):
  `gm_config` is validated as a scalar map, so the agency-guard block is the
  scalar `agency_guard_enabled: bool` + `guard_slot` string rather than a
  nested object. Accepted; revisit only if gm_config ever needs structured
  values for other reasons.
- `PLANNER_VERSION` bumped v1 -> v2 (default-enabled guard changes the
  emitted mapping; same-input plan identities must not collide across
  versions).
- Detector v1 documented under-detections (modals/perfects/negations/
  passives) are conservative-by-design for a "minimum" guard; the optional
  single yes/no live-model confirmation may relax the reported-speech
  borderline class later. Gate H's semantics reviewer weighs these.


## Phase 6 notes 2026-08-03

- Ranking semantics (lead adjudication of the agent's deviation): rank key is
  the user-DECLARED metric sequence -- primary, then secondaries in declared
  order, all descending, polarity never inferred; candidate_id lexicographic
  is only the final code-owned tie-break and is FLAGGED in validation_status
  when it actually decided an ordering. Fixture-1's winner is measured
  (meeting_scheduled True vs False), not tie-broken -- proven by the flag's
  asserted absence.
- Terminal-status mapping: the runner reports only cutoff/incomplete (R3);
  success/failure verdicts come from the evaluator layer via a caller
  status_rule over measured metrics, refused on infrastructure-errored
  branches.
- guard_interventions have no BranchResult field (frozen contract): they ride
  the runner diagnostics record; Phase 7's distributed executor persists that
  record as an artifact file referenced from BranchResult.artifact_paths.


## Phase 7 notes 2026-08-03

- Stage A gate PASSED with byte-identical local/distributed branch
  signatures (sha256 per candidate) and the measured fixture winner
  reproduced over the distributed leg; file-authoritative collection with
  CollectionIntegrityError on any driver/file disagreement.
- Model seam key is `model_builder` (dotted-name + JSON params) -- the
  hardcoding guard forbids the bare word the brief suggested; same seam for
  future live models.
- Distributed escalation semantics: runner-captured mid-branch errors are
  escalated to step failures AFTER persisting the partial result, so
  branch_error.json and the driver record agree (dual channel); the local
  manager returns such branches without raising. Documented divergence.
- Upstream discoveries recorded in test docstrings: a warm-up round must
  HOLD worker slots with the same blocking delay as the timed round (a
  zero-cost warm-up is absorbed by one worker); the Ray job env snapshot is
  frozen at first init_dispatchers -- later WORKSPACE_PATH/PYTHONPATH
  exports never reach workers, so one Ray owner per process segment and the
  executor adopts an existing init's workspace rather than repointing it.
- Private imports from counterfactuals.manager (_preflight,
  _seeded_branch_scope, _result_from_runner) are the accepted
  reuse-over-duplication tradeoff; promote to public names during the
  documentation phase if churn appears.


## Hook maintenance 2026-08-03 (#4) -- completion receipts become completion-grade

Trigger: Phases 3-7 adversarial review finding H2 -- every phase receipt was
a dirty-worktree run at the completion commit's parent SHA, and the
validator never checked phase-task receipts, making CLAUDE.md rule 7
("a receipt against another SHA cannot satisfy completion") decorative.

Fix (smallest general): new validator check `phase_receipt_discipline` --
for every TASK_GRAPH task with status=complete and required_receipts, the
newest passing receipt must satisfy clean-worktree OR content continuity:
every file named in the receipt's configuration_hashes must currently hash
to the recorded value (a receipt then certifies exact bytes regardless of
the inherent one-commit SHA staleness of committed receipts). A receipt
with neither property, a failed/missing receipt, or a hash mismatch fails
the check. Master-context task excluded (its own stricter SHA-exact check
stands). Phases 3-7 receipts re-recorded at the clean post-fix HEAD with
config hashes over each phase's key artifacts.

Companion non-maintenance fixes from the same review: the ~1/8 flaky
upstream state round-trip test made hash-order-insensitive (stored_hashes
is set-derived; PYTHONHASHSEED 5/13 reproduced; ledgered); contract
JSON-tree fields (terminal_world_state, concordia_checkpoint) defensively
deep-copied at ingest and egress so content_hash cannot be mutated from
outside; ranking validation_status gains decided_by_metric and the module
docstring states the descending-order imposition honestly; recommendation
re-validation now checks the full declared-order key, not primary-only
monotonicity.

**Outcome (#4).** Control-plane suites green (93 validator tests incl. 6 new; gate suite OK); validator run below records the two honestly-deferred Ray-suite receipts (p2/p7) as the only red until the Phase 8 fold-in. Companion fixes verified: flake killed under reproducing seeds; contracts deep-copy; decided_by_metric + full declared-order re-validation (validation_status widened to short strings). Reviews: docs/engine_migration/reviews/PHASE_3_7_BOUNDARY_REVIEW.md. Mode restored to implementation.

**Amendment (#4a), same day — "newest" made chronological.** After the
clean-HEAD re-record, the validator STILL flagged phases 3/5/6/fixtures:
`phase_receipt_discipline` picked "newest" as `passing[-1]`, which is file
order, and receipt file names embed the git SHA prefix — so a
lexicographically-late OLD SHA (9e7609d... > 254bbb8...) shadowed the
genuinely newer clean receipts. Fixed inside the same maintenance window:
newest passing receipt is now `max()` by `recorded_at`/`finished_at`. Two
discriminating tests added (both stash-verified to fail on the old code):
an old dirty receipt sorting late must not create a false red over a newer
clean receipt, and an old clean receipt sorting late must not mask a newer
proof-less receipt (false green — the dangerous direction). Suites green:
validator 95, gate 134, monitored-runner 25. Validator now names exactly
the two deferred Ray-suite receipts (p2/p7). Mode restored to
implementation.


## Phase 8 notes 2026-08-03 (fold-in)

- Stage B gate PASSED: whole-branch checkpoint/restore with three-way
  full-signature equality (A=A'=B, two seeds), RNG stream continuity
  proven by a divergence discriminator (naive re-seed control visibly
  diverges; proper restore matches byte-for-byte), and distributed
  interrupted-resume byte-equal to the uninterrupted run with live RNG
  draws crossing the worker boundary through the blob.
- Upstream repairs entirely through public API: ListMemory.set_state
  re-points its bank at the argument list (refill the original handle and
  hand it back); EntityAgent.set_state swallows component exceptions, so
  restore_branch enforces post-restore get_state() byte-equality
  (canonicalized stored_hashes) as the only trusted success signal.
- Restore requires behaviorally prompt-pure models (model internals are
  never serialized) -- documented in checkpoint.py, enforced structurally
  in the checkpoint suite's model spec.
- Fold-in items closed: p2/p7 Ray-suite receipts re-recorded clean
  (p7 with path-labeled config hashes after the batch-ordering effect --
  a receipt recorded mid-batch sees earlier receipts as untracked and
  loses worktree_clean; commit between records or carry hashes); the
  worker-RNG distributed equivalence proof (finding D5) landed as
  test_worker_rng_equivalence.py with non-vacuity assertions.
- Known pre-existing issue (reported by the phase-8 writer, reproduced at
  db41689 pre-phase): engine-env `pytest tests/engine_contracts
  tests/engine_distributed` in ONE session fails via frozen Ray env
  snapshot + worker registry cache when the distributed suite adopts the
  contracts suite's workspace; DoD-ordered command avoids it. Candidate
  for the operational-robustness matrix, not a product defect.

## Guard hardening notes 2026-08-03 (findings 6+7 closed)

- Unresolved-subject policy: pronoun/collective subjects that cannot be
  resolved to a roster name conservatively bind every non-active roster
  actor (each receives an availability sentence) -- errs toward agency
  preservation; verbose on large rosters by design.
- Reference resolution is deterministic and gender-blind: singular
  pronouns bind the nearest preceding roster name; bare "they" binds the
  distinct preceding roster names with an all-non-active fallback.
- Documented residuals (guard docstring): second-person/"it" subjects,
  do-support emphatics, bare-modal futures, pronoun-possessive
  nominalizations, collective possessives, multi-comma asides; asyndetic
  serial-verb tails over-rewrite in the recoverable direction. Stateless
  nominal trade-off: references to genuinely past acts are
  indistinguishable from invented ones without history and are
  conservatively rewritten.
- Hardcoding-guard allowlist mechanism upgraded during the sanctioned
  remedy: whole-file skips replaced by per-file word allowances (files
  stay scanned for every other word), with an exactness test rejecting
  broad/stale/empty entries. guard.py's allowance is exactly
  {vote, voting}; "committee" was deliberately left off the guard's
  group-noun list to keep it that narrow.

## Hook maintenance 2026-08-03 (#5) -- engine DoD battery becomes monitored

Trigger: the "engine DoD baseline before changes" incident. The
compiler-adapter subagent's baseline command (bare foreground 5-suite
engine pytest, `... -q 2>&1 | tail -5`) was REJECTED by the permission
layer at 12:25:40Z before any process spawned; the subagent paused
awaiting direction and sat idle 4h20m. Externally this read as a job
running four hours without progress; in fact there was never a PID, no
BACKGROUND_JOBS entry, no heartbeat, no log -- and therefore also nothing
that could prove the negative. Ledgered as
`silent-agent-pause-plus-unmonitored-long-suite`.

General cause: `_LONG_RUNNING_PATTERNS` classifies long jobs by semantic
class (corpus/scale/load/bench/many-agent/frozen-acceptance); a
multi-suite engine pytest battery matched none of them, so
`requires_monitored_runner()` let it run as bare unbounded foreground
Bash with no observability. Rule 5's "long test" intent did not cover the
run the phases actually use as their DoD.

Fix (smallest general): `long_running_reason` now classifies a pytest
invocation naming two or more distinct `tests/engine_*` directories as a
"multi-suite engine test battery" (monitored runner required). Bounded
evidence runs stay legal: `record_receipt.py --run` with an explicit
`--timeout` is exempt per shell segment (the tool kills its child at the
timeout; its default is None, so the flag is mandatory for the
exemption). Single-suite pytest and file-level iteration stay direct.
Four regression tests added (battery denied incl. the exact incident
shape and env-prefixed form; single-suite allowed; monitored/bounded
receipt forms allowed; per-segment smuggling and timeout-less receipt
runs denied). Suites: gate 138, validator 95, monitored-runner 25 -- all
green. Mode restored to implementation.

Operational protocol change (non-hook): when the lead launches a writer
subagent it arms a `send_later` liveness check-in (~45 min) and verifies
the agent's transcript is advancing when it fires, because a
permission-paused subagent emits no completion signal. Recorded in
HANDOFF.md.

## Compiler-adapter notes 2026-08-03 (task complete; lead dispositions)

- Contract-expressiveness finding: the compiler schema permits a starting
  event with EMPTY visible_to (observer-less ledger fact); frozen
  StartingEvent requires >=1 observer. Disposition: the adapter's loud
  refusal STANDS. No frozen fixture or acceptance scenario needs
  observer-less pre-start facts; if one ever does, that is a
  contract-version change decided then, not a silent widening now.
- The compile question has no CompiledDecisionWorld slot. Disposition:
  identity-hash + provenance + sidecar treatment ACCEPTED as the
  permanent Stage-A/B answer; DecisionProblem is the question's semantic
  home. Canary-proven never to reach prompts. Revisit only if a future
  contract version is opened for other reasons.
- Undecodable actor names (empty slug / non-letter-leading) are refused,
  not fabricated -- deliberate divergence from legacy scene_adapter.slug
  under the no-invented-identities rule. ACCEPTED.
- Route surface (prepare_decision_inputs / build_user_candidates /
  generate_candidates + one-fixed-schema generator, duck-typed
  sample_text seam, exactly one call per generation) is the Phase 9
  entry seam.

## Phase 9 notes 2026-08-03 (individual vertical slice complete)

- reporting/common.py is a third module beyond the directive's two named
  files (shared canonical serialization) -- sanctioned by the directive's
  "cleaner structure" clause; responsibilities stay separated.
- The frozen contract embedded by the report document is
  RecommendationResult (computed only via outcomes.rank_branches); the
  report round-trips every embedded contract through strict from_dict/
  content_hash. Design note, not a gap: full BranchResult dicts are NOT
  embedded because content_hash covers wall-clock runtime_stats; the
  report embeds the deterministic evaluation core and documents the
  exclusion. BranchResult remains the contract of record.
- Evaluator predicates for the slice are attribution-anchored (require
  the resolved-actor-turn wrapper), which is what defeats GM-narration
  satisfaction of success criteria; recorded as the pattern for Phase 10
  team predicates.
- Live smoke: requested deepseek-chat; endpoint serves deepseek-v4-flash.
  Retry-once policy with LIVE_ENDPOINT_UNREACHABLE infrastructure-error
  distinction. openai 2.52.0 was already in the engine env.
- Monitored DoD job ran pre-commit (exploratory, dirty tree); the
  SHA-exact clean-tree proof is the receipt battery at the completion
  commit. This ordering (monitored battery -> commit -> bounded receipt
  battery at clean HEAD) is the accepted per-phase pattern.

## Phase 10 notes 2026-08-03 (team vertical slice complete)

- Every gate-D clause was expressible through EXISTING configuration:
  meeting = plan defaults (fixed acting order, notify_observers) with the
  scripted GM answering the observer question with the full roster;
  private follow-ups = GM observer-subset answers keyed to turn-unique
  needles (sound because the aware-question prompt carries only the
  current event text in this build); authority = attribution-anchored
  evaluator predicates keyed to the fixture's authority holder (the
  Phase 9 pattern), proven by an identical-utterance flip probe. No
  surgical concordia_local addition was needed.
- Mechanical note for future team scenarios (and reviewers): a branch's
  FINAL-step event is queued to observers but never delivered (the run
  ends before the next fan-out) -- last-step turns exist in the world
  record but reach no actor memory. Team assertions must be designed
  around delivered steps.
- Phase-5 receipt re-recorded at the current HEAD: the content-continuity
  check correctly flagged that guard.py changed after phase-5's receipt
  -- the change is the SANCTIONED guard hardening (a4112f6, its own
  completed task). New receipt hashes the hardened guard.py + its test
  file; the guard+builder suites pass with the hardened content.

## Phase 11 notes 2026-08-03 (societal infrastructure proof complete)

- The 600s Bash ceiling made partition-chunked monitored jobs the design:
  4x250 agents x 2 segments with a declared tick-6 checkpoint boundary,
  segment B resuming in a fresh process + fresh Ray runtime from
  persisted workspaces + a spec-hash-bound driver checkpoint. The
  chunking IS the partitions/checkpoint-resume/aggregation demonstration,
  not a workaround.
- run_monitored semantics observation (documented, no hook change
  needed): progress_source records the most recent signal per poll, so a
  trailing stdout write can leave it at log_movement even when
  completed_units advanced; durable strong-progress evidence is the
  completed_units field, which the verification tier asserts.
- Raw run roots retained outside the repo at /home/user/scale_runs/
  phase11/ for post-hoc inspection; durable evidence committed under
  tests/engine_scale/evidence/ (52 files, sha256 manifest).
- No substrate defects at scale: per-agent failure isolation held at
  250-agent partitions; 4-digit agent ids safe.

## Phases 8-11 adversarial review 2026-08-03 -- verdicts and dispositions

Reviewer verdicts: D1 checkpoint holds-with-findings; D2 guard
holds-with-findings; D3 adapter HOLDS (no silent-discard input could be
crafted); D4 slice evidence holds-with-findings; D5 scale evidence HOLDS
(52/52 hashes reverified); D6 hygiene holds-with-findings. Nine-suite
battery independently reproduced at 235. Gate H: 6 clauses confirmed, 2
refuted by F1.

- F1 (HIGH, blocks freeze): `Name:` / `Name --` attribution -- upstream
  EventResolution's own separators -- evades the guard's
  whitespace-adjacent subject detector, and the slice evaluators'
  "attribution anchors" accept substring co-occurrence anywhere in a row.
  One actor can cast another's reply/vote/veto and have it counted.
  DISPOSITION: FIX (in flight): guard treats colon/dash as
  subject-attribution boundaries for non-active roster names (active
  player's own leading attribution passes); evaluator anchors bind to the
  row's OWN leading attribution == the predicate-named actor;
  discriminating tests reproduce all reviewer probes both directions;
  guard-hashing receipts re-recorded. Committed example artifacts must
  stay byte-identical (scripted runs contain no proxy forms).
- F2 (LOW): checkpoint stored_hashes canonicalization inert against
  current objects and untested. DISPOSITION: unit test added with the F1
  fix (permutation-identity + passthrough); the defensive branch stays.
- F3 (MEDIUM): validator FAIL at HEAD is the documented one-commit
  master-receipt staleness. DISPOSITION: mechanical; the Phase 12 freeze
  sequence ends with the master receipt re-recorded at the frozen SHA so
  the validator PASSES at the SHA being adjudicated.
- F4 (LOW): big-run scale reconciliation trusts committed self-attested
  equality fields (raw unit ledgers live outside the repo); the
  reconciliation CODE path has live small-N negative controls and the
  rollup chain is recomputed from committed summaries. DISPOSITION:
  accepted two-tier design, disclosed here and in the evidence doc.
