# Next Realism Phase — grounding and calibration work that has NOT been done

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

**Status of every item on this page: NOT IMPLEMENTED and NOT VALIDATED in
this pass.** This pass built and proved the engineering foundation — an
intervention-centered simulation engine with matched counterfactual
branches and measured outcomes. It did **not** make the simulations true.
The master directive names six later-phase work items
(`MASTER_IMPLEMENTATION_DIRECTIVE.md`, "Final required output" — "Exact
next steps for: …") and explicitly forbids describing them as completed
unless separately implemented and validated. They are expanded here into
concrete next steps anchored to the seams the as-built architecture
already exposes. Nothing below alters the foundational invariants
(upstream preservation, matched branches, measured-not-narrated outcomes,
no LLM override).

## 1. Evidence grounding

**Goal.** A compiled world's contents (actors, contexts, starting events)
are justified by real evidence, not by an LLM's plausible invention.

**As-built seams to build on.** `DecisionProblem.relevant_context` (the
evidence/context string, contract-carried); the compiler's `evidence`
input and `evidence_mode` metric — both currently ride the adapter
sidecar verbatim and reach no prompt
(`COMPILER_TO_CONCORDIA_MAPPING.md` rows 12–15);
`CompilerProvenance.artifact_hashes` (every compile artifact hashed).

**Concrete next steps.**
1. Define an evidence-package contract (source items, provenance,
   retrieval timestamps, per-claim citations) in the same
   strict-validation style as `sworldmodel/decision/contracts.py`.
2. Make the compiler consume it in a declared `evidence_mode`, emitting a
   claim-to-source map for every manifest field it grounds.
3. Add a grounding validator: every actor property and starting event
   either cites an evidence item or is explicitly labeled assumed —
   refusal, not repair, on unlabeled invention.
4. Acceptance: a fixture pair (grounded vs ungrounded compile of the same
   question) where the validator provably separates them; leak canaries
   proving evidence provenance never enters actor prompts (extending
   `tests/engine_compilation/test_information_leaks.py`).

## 2. Observed / inferred / latent state separation

**Goal.** The world state distinguishes what is known from observation,
what is inferred, and what is modeled-but-unobservable, so downstream
consumers can weight them differently.

**As-built seams.** `CompiledDecisionWorld` actor `private_context` /
`shared_context` / `starting_events[].visible_to` already carry a strict
VISIBILITY separation, canary-proven; the contracts' strict-schema
pattern is the template for adding epistemic labels.

**Concrete next steps.**
1. Extend the world contract (a new schema version — the versioning rules
   exist) with per-fact epistemic status
   (`observed | inferred | latent`) and source linkage into the §1
   evidence map.
2. Thread the labels through the planner without changing what actors
   SEE (epistemic metadata must never leak into prompts — canary tests in
   the §1 style).
3. Make the outcome evaluator record which epistemic classes each
   metric's cited events depended on.
4. Acceptance: contract round-trip + rejection battery for the new
   fields; a report that partitions a recommendation's evidence by
   epistemic class.

## 3. Representative population construction

**Goal.** Populations whose composition (demographics, preferences,
constraints) statistically reflects a declared target population, rather
than hand-written or LLM-invented casts.

**As-built seams.** The scale substrate (partitioned workspaces, sparse
activation, exact reconciliation — [SOCIETAL_SCALING_PATH.md](SOCIETAL_SCALING_PATH.md));
the fixture loader's strict validation pattern; population fixture 3
(`population_offer.yaml`) as the SYNTHETIC placeholder shape.

**Concrete next steps.**
1. Define a population-spec contract (marginals/joint distributions,
   sampling seed, provenance of the source statistics).
2. Implement a deterministic seeded sampler producing actor rosters with
   code-owned identities (never LLM-minted ids — the existing
   `derive_actor_ids` discipline).
3. Validate composition: sampled marginals within declared tolerance of
   the spec, tested; refusal on unsatisfiable specs.
4. Acceptance: representativeness tests against the declared source
   statistics — explicitly NOT a realism claim about individual behavior,
   which is §4's problem.

## 4. Human-behavior calibration

**Goal.** Evidence that simulated actors respond the way comparable real
people do, at least on measurable reference tasks.

**As-built seams.** The model seam (injected models / `model_builder`
specs — [FINAL_ARCHITECTURE.md](FINAL_ARCHITECTURE.md) §5) lets
calibration target the model layer without touching the engine; the
frozen-fixture + expected-block pattern
(`tests/fixtures/best_action/FIXTURES.md`) is the template for
calibration datasets; trace reports capture complete causal records to
score against.

**Concrete next steps.**
1. Assemble reference datasets of real human responses to situations the
   engine can express (frozen, hashed, directive-style — never authored
   by the implementing model).
2. Run matched simulations; score distributional agreement
   (response-type frequencies, not narrative style) with pre-registered
   metrics.
3. Iterate on actor configuration (persona content, memory policy, model
   choice) under a frozen evaluator — the "do not loosen tests to pass"
   rule applies verbatim.
4. Acceptance: pre-registered agreement thresholds met on held-out
   scenarios; every calibration claim carries its dataset hash and score
   artifact.

## 5. Full action search

**Goal.** Move beyond ranking a handful of supplied/generated candidates
to systematically exploring the action space.

**As-built seams.** The one-fixed-schema candidate generator
(`sworldmodel/compilation/decision_route.py`) with its explicit
permission gate and code-owned `gen_NNN` identities; branch-level
distribution that already parallelizes candidate evaluation; the
directive's standing prohibition on letting an LLM pick the winner.

**Concrete next steps.**
1. Define the search contract: proposal budget, dedup rule
   (candidate-text canonicalization), stopping criterion — all
   code-owned and recorded per run.
2. Implement iterative propose → simulate → measure → propose-again loops
   where ONLY measured outcomes (never model opinion) drive the next
   proposal round.
3. Keep every evaluated candidate in the report with its measured
   metrics; the recommendation stays "best among tested", now with an
   explicit search-coverage statement.
4. Acceptance: determinism of the search loop under scripted models;
   a proof that pruning decisions cite measured metrics only.

## 6. Confidence calibration

**Goal.** Recommendations carry honest uncertainty: how sensitive the
winner is to run-to-run variation and modeling assumptions.

**As-built seams.** Per-branch seeds are code-owned and derivable
(`derive_branch_seed`), so seed-ensemble runs are cheap to express;
`RecommendationResult.metric_differences` / `downside_outcomes` /
`validation_status.decided_by_metric` already expose margin structure;
`run_limitations` is the contract-enforced honesty channel.

**Concrete next steps.**
1. Seed-ensemble execution: N seeds per candidate under live/stochastic
   models; report per-candidate outcome distributions, not single runs.
2. Winner-stability statistics (how often the top candidate holds across
   the ensemble) and margin-vs-noise comparisons on the declared metrics.
3. Sensitivity probes over labeled assumptions (§2's epistemic classes):
   re-run with latent assumptions varied; report flips.
4. Acceptance: calibration-style scoring on scenarios with known
   deterministic ground truth (ensembles must converge to the proven
   deterministic winners as noise → 0); report language extended to
   state confidence honestly — never a probability invented by a model.

## 7. Ordering and ground rules

A workable order respecting the dependencies above: §1 → §2 (grounding
before epistemic labeling), then §4 (calibration needs grounded worlds),
§3 in parallel with §4 for population work, §5 and §6 last (search and
confidence consume everything else). Rules carried forward from the
directive for ALL of it: separate design + acceptance review per stage;
frozen evaluators and fixtures; adversarial review; no realism claims
without the validation artifacts; and none of it is permitted to weaken
the invariants this pass proved (upstream preservation, matched frozen
bases, single-intervention branches, measured outcomes, no LLM override).

**Restated once more: none of §§1–6 exists in the current system. Any
statement that SWORLDMODEL currently grounds evidence, separates
epistemic state, constructs representative populations, calibrates human
behavior, searches the action space, or quantifies confidence is false.**
