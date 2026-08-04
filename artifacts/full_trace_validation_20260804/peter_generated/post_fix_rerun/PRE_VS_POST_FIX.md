# Pre-fix vs post-fix -- `peter_generated`

> **UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION.** Both runs below are uncalibrated one-shot simulations against a live model. Nothing here is a prediction about any real person.

The pre-fix run is preserved exactly as it was recorded; this re-run was written to `post_fix_rerun/` and nothing in the pre-fix directory was moved, deleted, or rewritten. Live model sampling is not reproducible at temperature 0, so the two runs are NOT expected to produce identical text -- what is compared is the ENGINE behaviour the four fixes were supposed to change.

## Frozen inputs

Every input entry below was hashed by the pre-fix run and re-hashed by this re-run:

| entry | pre-fix sha256 | post-fix sha256 | identical |
|---|---|---|---|
| decision_problem | `0f953e857c0c78d8` | `0f953e857c0c78d8` | yes |
| evidence_manifest | `eb943353e4883115` | `eb943353e4883115` | yes |
| compiler_command_and_config | `b83f2fd94abccbd2` | `b83f2fd94abccbd2` | yes |
| compiler_inputs | `fe5e722c097f568d` | `fe5e722c097f568d` | yes |
| compiler_artifact_dir_aggregate | `eb03fe7f4ef1b7a7` | `eb03fe7f4ef1b7a7` | yes |
| compiled_decision_world | `4d5a4845fcab5970` | `4d5a4845fcab5970` | yes |
| concordia_initialization_plan | `79779e0e2b2fd7f5` | `79779e0e2b2fd7f5` | yes |
| concordia_initialization_plan_content_hash | `c16eaa9eca3611a2` | `c16eaa9eca3611a2` | yes |
| evaluator_spec | `875d662a8c7945b2` | `875d662a8c7945b2` | yes |
| simulation_limits | `b481366c3e487def` | `b481366c3e487def` | yes |
| time_window | `2c3c732cb6accfd0` | `2c3c732cb6accfd0` | yes |
| branch_seeds | `a4ecf66a01f97060` | `a4ecf66a01f97060` | yes |

Every frozen input entry is byte-identical.

## Agency-guard interventions (defect D3)

The determiner false positive truncated a sentence at the determiner and deleted the ACTIVE actor's own quoted content whenever it addressed a determined recipient (`sends a message to THE <role name>: "..."`).

- pre-fix: **2** guard interventions
- post-fix: **1** guard interventions
- change: **-1**

The raw count is not by itself the D3 measurement: the guard has other, deliberate detection classes that the fix did not touch, and live sampling changes how often each one is triggered. The class split is in the notes at the end of this document.

| branch | pre-fix interventions | post-fix interventions |
|---|---|---|
| gen_001 | 1 | 0 |
| gen_002 | 1 | 0 |
| gen_003 | 0 | 1 |

## Per-branch contract facts

`intervention_delivered` and `unresolved_observers` are the two fields the fixes ADDED to `BranchResult`. The pre-fix run carries neither: that is reported as *not measured*, never as a value, because claiming a measurement the pre-fix run never made would be the same error the fixes exist to prevent.

| branch | terminal (pre) | terminal (post) | delivered (pre) | delivered (post) | unresolved observers (pre) | unresolved observers (post) |
|---|---|---|---|---|---|---|
| gen_001 | success | cutoff | not measured | `not_delivered` | not recorded | 0 |
| gen_002 | cutoff | success | not measured | `not_delivered` | not recorded | 0 |
| gen_003 | cutoff | success | not measured | `not_delivered` | not recorded | 0 |

## Unresolved observer names (defect D1)

Upstream `ObservationQueue.add` creates a queue key for whatever string the game master's free-text observer answer produced, so a name that matches no roster entity was dropped with no error and no record. The fix rosters a validated observer seam and records every non-resolving name verbatim. Nothing about routing changed -- only the silence.

- pre-fix: **not recorded at all** (the field did not exist; a dropped observer left no trace)
- post-fix: **0** non-resolving observer names recorded

No observer name failed to resolve in this re-run, so no event was dropped by this path.

## Ranking

- pre-fix: **PRODUCED** (winner `gen_001`)
- post-fix: **REFUSED**

The refusal is the correct result, not a failure of the re-run. `sworldmodel.outcomes.ranking` refuses to name a winner when no measured branch delivered its intervention to any actor other than the insertion actor -- which is exactly what the pre-fix run did while publishing a winner anyway. The engine's verbatim reason:

```
refusing to rank: not one of the 3 measured branches delivered its intervention to any actor other than the insertion actor, so every branch ran the counterfactual's independent variable at the same (undelivered) value and the measured differences cannot have been caused by the candidates. A winner computed from these branches would be an artifact of model sampling on identical downstream context, not a comparison. Per-branch delivery: gen_001: not_delivered (no_distinctive_fragment_reached_any_other_actor); gen_002: not_delivered (no_distinctive_fragment_reached_any_other_actor); gen_003: not_delivered (no_distinctive_fragment_reached_any_other_actor). Resolve the delivery failure (or run branches whose intervention reaches the world) and rank again; nothing is repaired or ranked silently here.
```

## Delivery check

| measure | pre-fix | post-fix |
|---|---|---|
| verdict | `candidates_never_reached_the_recipient` | `no_candidate_text_reached_the_recipient` |
| distinct recipient first-turn prompts | 1 | 2 |

## Instrumentation

| measure | pre-fix | post-fix |
|---|---|---|
| live calls | 25 | 25 |
| errors | 0 | 0 |
| retries | 0 | 0 |
| three counters agree | True | True |

## Notes

- Guard interventions split by class -- pre-fix: 0 determined-recipient (the class D3 closed), 2 possessive nominalization (a documented deliberate conservatism in the guard's own docstring, NOT a defect), 0 unclassifiable from the 120-character excerpt the runner records, 0 other, 2 total. Post-fix: 0 determined-recipient (the class D3 closed), 1 possessive nominalization (a documented deliberate conservatism in the guard's own docstring, NOT a defect), 0 unclassifiable from the 120-character excerpt the runner records, 0 other, 1 total.
- Live model sampling is not reproducible at temperature 0, so any change in terminal status or committed text between the two runs is sampling variation on identical inputs unless it is one of the engine behaviours listed above.
- The candidate set is a live OUTPUT of this scenario, not a frozen input. The generator INPUTS were compared and are identical (`candidate_generator_prompt`, `candidate_generator_config`). The re-run regenerated candidates live and the resulting set is NOT byte-identical to the pre-fix set (pre `72b1abfa26779a4d`, post `dc6060d25a12856a`), which is expected from a live one-shot generation and is why the candidate set is excluded from the frozen-input table above.
- The narrative UNDER_THE_HOOD_REPORT.md is not regenerated for a re-run: it renders the whole artifact root including the compile phase, which a re-run deliberately does not repeat. This document is the re-run's narrative; the pre-fix report is unchanged and still describes the pre-fix run.

