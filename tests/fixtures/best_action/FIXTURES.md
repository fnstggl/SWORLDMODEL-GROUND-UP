# Frozen Manual Best-Action Fixtures

Directive-mandated acceptance scenarios, manually written and version-
controlled BEFORE the best-action pipeline is implemented. The pipeline is
built to pass these; they are never adjusted to match observed outputs.

## Immutability

Frozen at commit with the SHA-256 hashes below. Any change requires an
explicit `.agent-run/DECISIONS.md` entry with justification and re-freeze;
during the frozen final evaluation (Phase 12) changes are prohibited
outright, hashes must match, expected outcomes must not be rewritten, actor
rules must not be weakened, and evaluator definitions must not be changed to
match observed outputs.

| Fixture | File | SHA-256 |
|---|---|---|
| individual_reply | `individual_reply.yaml` | `03bf7be7dbbbbe3f9e6768d60cccb6301c459d59b62204e0a9de1e84b6dcd201` |
| team_commitment | `team_commitment.yaml` | `2e15efa7cf59c2250213516557b22bd7c65cae934b66856876f54eeb84e4afb6` |
| population_offer | `population_offer.yaml` | `93537342df26761bc67cb6cbb6aedc89531a9ab8719040be283047928b418985` |

Verification: `cd tests/fixtures/best_action && sha256sum -c FIXTURES.sha256`
(the sidecar checksum file is frozen alongside the fixtures).

## Contract

Each fixture directly provides: fixture ID; a manually written
CompiledDecisionWorld (`world:` block); manually written
InterventionCandidates (`candidates:`); the explicit code-owned outcome
evaluator (`evaluator:` — declared primary/secondary metrics);
deterministic test expectations (`deterministic_script` +
`expected_deterministic`); and live-model realism assertions
(`live_model_assertions` / `infrastructure_assertions`).

Loading path (Phase 3+): manual fixture → strict schema validation →
CompiledDecisionWorld → frozen base snapshot → candidate branches →
Concordia simulations → trace-based outcome evaluation →
RecommendationResult. During fixture tests: no SWORLDMODEL compiler import,
no evidence retrieval, no LLM-generated actors or candidates, no LLM winner
selection.

`deterministic_script` blocks are engineering-test scaffolding consumed ONLY
by the scripted/mock model layer of the test harness; they must never enter
production simulation logic.

Expected deterministic winners: `concise_relevant` (fixture 1),
`private_ops_then_pilot` (fixture 2), `offer_premium` on the declared
primary metric total_revenue (fixture 3 — deliberately different from the
purchase-count winner, proving ranking follows declared metrics).

`population_offer` is labeled SYNTHETIC INFRASTRUCTURE TEST — NOT A
REALISTIC MARKET FORECAST, and must never be cited as societal realism
evidence.
