# Pre-fix vs post-fix -- `peter_supplied`

> **UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION.** Both runs below are uncalibrated one-shot simulations against a live model. Nothing here is a prediction about any real person.

The pre-fix run is preserved exactly as it was recorded; this re-run was written to `post_fix_rerun/` and nothing in the pre-fix directory was moved, deleted, or rewritten. Live model sampling is not reproducible at temperature 0, so the two runs are NOT expected to produce identical text -- what is compared is the ENGINE behaviour the four fixes were supposed to change.

## Frozen inputs

Every input entry below was hashed by the pre-fix run and re-hashed by this re-run:

| entry | pre-fix sha256 | post-fix sha256 | identical |
|---|---|---|---|
| decision_problem | `03dddf3582901a82` | `03dddf3582901a82` | yes |
| evidence_manifest | `ab5df254ce26701a` | `ab5df254ce26701a` | yes |
| compiler_command_and_config | `b83f2fd94abccbd2` | `b83f2fd94abccbd2` | yes |
| compiler_inputs | `fe5e722c097f568d` | `fe5e722c097f568d` | yes |
| compiler_artifact_dir_aggregate | `eb03fe7f4ef1b7a7` | `eb03fe7f4ef1b7a7` | yes |
| compiled_decision_world | `4d5a4845fcab5970` | `4d5a4845fcab5970` | yes |
| concordia_initialization_plan | `79779e0e2b2fd7f5` | `79779e0e2b2fd7f5` | yes |
| concordia_initialization_plan_content_hash | `c16eaa9eca3611a2` | `c16eaa9eca3611a2` | yes |
| evaluator_spec | `875d662a8c7945b2` | `875d662a8c7945b2` | yes |
| simulation_limits | `6fbe5dbfdcaef994` | `6fbe5dbfdcaef994` | yes |
| time_window | `2c3c732cb6accfd0` | `2c3c732cb6accfd0` | yes |
| branch_seeds | `4b02b115e541c63d` | `4b02b115e541c63d` | yes |

Every frozen input entry is byte-identical.

## Agency-guard interventions

Defect D3 was a determiner false positive: it truncated a sentence at the determiner and deleted the ACTIVE actor's own quoted content whenever it addressed a determined recipient (`sends a message to THE <role name>: "..."`).

- pre-fix: **1** guard interventions
- post-fix: **3** guard interventions
- change: **+2**

**That change is a count, not an attribution.** The guard has other, deliberate detection classes that the fix did not touch, and live sampling changes how often each one is triggered, so a count falling to zero does not by itself say D3 caused it. How many of the pre-fix interventions D3 actually explains is measured by REPLAY -- each pre-fix intervention's reconstructed pre-guard text is run through the current guard -- and is reported in the notes at the end of this document, together with the class split.

- explained by the D3 fix (replayed, byte-identical under the current guard): **0** of **1**
- still rewritten by the current guard (NOT attributable to D3): **1**
- not replayable (no recorded raw response): **0**

| branch | pre-fix interventions | post-fix interventions |
|---|---|---|
| user_001 | 1 | 1 |
| user_002 | 0 | 1 |
| user_003 | 0 | 1 |

## Per-branch contract facts

`intervention_delivered` and `unresolved_observers` are the two fields the fixes ADDED to `BranchResult`. The pre-fix run carries neither: that is reported as *not measured*, never as a value, because claiming a measurement the pre-fix run never made would be the same error the fixes exist to prevent.

| branch | terminal (pre) | terminal (post) | delivered (pre) | delivered (post) | unresolved observers (pre) | unresolved observers (post) |
|---|---|---|---|---|---|---|
| user_001 | cutoff | cutoff | not measured | `not_delivered` | not recorded | 0 |
| user_002 | success | cutoff | not measured | `not_delivered` | not recorded | 0 |
| user_003 | cutoff | cutoff | not measured | `not_delivered` | not recorded | 0 |

## Unresolved observer names (defect D1)

Upstream `ObservationQueue.add` creates a queue key for whatever string the game master's free-text observer answer produced, so a name that matches no roster entity was dropped with no error and no record. The fix rosters a validated observer seam and records every non-resolving name verbatim. Nothing about routing changed -- only the silence.

- pre-fix: **not recorded at all** (the field did not exist; a dropped observer left no trace)
- post-fix: **0** non-resolving observer names recorded

No observer name failed to resolve in this re-run, so no event was dropped by this path.

## Ranking

- pre-fix: **PRODUCED** (winner `user_002`)
- post-fix: **REFUSED**

The refusal is the correct result, not a failure of the re-run. `sworldmodel.outcomes.ranking` refuses to name a winner when no measured branch delivered its intervention to any actor other than the insertion actor -- which is exactly what the pre-fix run did while publishing a winner anyway. The engine's verbatim reason:

```
refusing to rank: not one of the 3 measured branches delivered its intervention to any actor other than the insertion actor, so every branch ran the counterfactual's independent variable at the same (undelivered) value and the measured differences cannot have been caused by the candidates. A winner computed from these branches would be an artifact of model sampling on identical downstream context, not a comparison. Per-branch delivery: user_001: not_delivered (no_distinctive_fragment_reached_any_other_actor); user_002: not_delivered (no_distinctive_fragment_reached_any_other_actor); user_003: not_delivered (no_distinctive_fragment_reached_any_other_actor). Resolve the delivery failure (or run branches whose intervention reaches the world) and rank again; nothing is repaired or ranked silently here.
```

## Delivery check

| measure | pre-fix | post-fix |
|---|---|---|
| verdict | `candidates_never_reached_the_recipient` | `candidates_never_reached_the_recipient` |
| distinct recipient first-turn prompts | 1 | 1 |

## Instrumentation

| measure | pre-fix | post-fix |
|---|---|---|
| live calls | 24 | 24 |
| errors | 0 | 0 |
| retries | 0 | 0 |
| three counters agree | True | True |

## Notes

- Guard interventions split by class -- pre-fix: 0 determined-recipient (the class D3 closed), 1 possessive nominalization (a documented deliberate conservatism in the guard's own docstring, NOT a defect), 0 unclassifiable from the 120-character excerpt the runner records, 0 other, 1 total. Post-fix: 0 determined-recipient (the class D3 closed), 3 possessive nominalization (a documented deliberate conservatism in the guard's own docstring, NOT a defect), 0 unclassifiable from the 120-character excerpt the runner records, 0 other, 3 total. The class is decided by the guard's INPUT (a possessive `<Name>'s <act noun>` is a possessive case even when its rewrite happens to end in a dangling determiner), and by the UNTRUNCATED pre-guard text reconstructed from the step ledger wherever one is recoverable (1 of 1 pre-fix records).
- Attribution by REPLAY, not by subtraction: 0 of 1 pre-fix interventions are explained by the D3 fix -- their reconstructed pre-guard text passes the CURRENT guard byte-identically. 1 still rewrite under the current guard and are therefore NOT attributable to D3; their absence from the re-run is live sampling. Still rewritten: `user_001` step 3.
- A pre-fix POSSESSIVE rewrite, verbatim from the guard ledger: `Putative event to resolve:  Beckett Zahedi: Beckett Zahedi reads Peter Thiel's reply, then immediately compiles the repl` -- this is the documented stateless conservatism, NOT the class D3 closed, and the current guard still rewrites it.
- The possessive-nominalization count went UP. This is not a regression: it is the same documented behaviour firing more often because live sampling produced more turns of the form 'reads <Name>'s reply'. The guard docstring names this class explicitly as a stateless trade-off -- without history, a reference to a decision that really happened is indistinguishable from an invented one -- and the fix did not touch it.
- Live model sampling is not reproducible at temperature 0, so any change in terminal status or committed text between the two runs is sampling variation on identical inputs unless it is one of the engine behaviours listed above.
- The narrative UNDER_THE_HOOD_REPORT.md is not regenerated for a re-run: it renders the whole artifact root including the compile phase, which a re-run deliberately does not repeat. This document is the re-run's narrative; the pre-fix report is unchanged and still describes the pre-fix run.

