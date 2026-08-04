# Pre-fix vs post-fix -- `a16z_richard_historical`

> **UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION.** Both runs below are uncalibrated one-shot simulations against a live model. Nothing here is a prediction about any real person.

The pre-fix run is preserved exactly as it was recorded; this re-run was written to `post_fix_rerun/` and nothing in the pre-fix directory was moved, deleted, or rewritten. Live model sampling is not reproducible at temperature 0, so the two runs are NOT expected to produce identical text -- what is compared is the ENGINE behaviour the four fixes were supposed to change.

## Frozen inputs

Every input entry below was hashed by the pre-fix run and re-hashed by this re-run:

| entry | pre-fix sha256 | post-fix sha256 | identical |
|---|---|---|---|
| decision_problem | `60fb4a87770875fb` | `60fb4a87770875fb` | yes |
| evidence_manifest | `08e85f0b1dee9ec3` | `08e85f0b1dee9ec3` | yes |
| compiler_command_and_config | `a053e0ecf1de74d3` | `a053e0ecf1de74d3` | yes |
| compiler_inputs | `2a17e9b7fff5849c` | `2a17e9b7fff5849c` | yes |
| compiler_artifact_dir_aggregate | `e550183449afce14` | `e550183449afce14` | yes |
| compiled_decision_world | `ddd2bf9d1a4725f0` | `ddd2bf9d1a4725f0` | yes |
| concordia_initialization_plan | `15e2834ce006b79b` | `15e2834ce006b79b` | yes |
| concordia_initialization_plan_content_hash | `39df9ca4c2490f77` | `39df9ca4c2490f77` | yes |
| evaluator_spec | `5fec7f8e04f36948` | `5fec7f8e04f36948` | yes |
| simulation_limits | `8dfb750444f51294` | `8dfb750444f51294` | yes |
| time_window | `d5fbdda25d096fb1` | `d5fbdda25d096fb1` | yes |
| branch_seeds | `eab7f7c6b7642a40` | `eab7f7c6b7642a40` | yes |

Every frozen input entry is byte-identical.

## Agency-guard interventions (defect D3)

The determiner false positive truncated a sentence at the determiner and deleted the ACTIVE actor's own quoted content whenever it addressed a determined recipient (`sends a message to THE <role name>: "..."`).

- pre-fix: **20** guard interventions
- post-fix: **0** guard interventions
- change: **-20**

The raw count is not by itself the D3 measurement: the guard has other, deliberate detection classes that the fix did not touch, and live sampling changes how often each one is triggered. The class split is in the notes at the end of this document.

| branch | pre-fix interventions | post-fix interventions |
|---|---|---|
| user_001 | 4 | 0 |
| user_002 | 0 | 0 |
| user_003 | 5 | 0 |
| user_004 | 2 | 0 |
| user_005 | 3 | 0 |
| user_006 | 6 | 0 |

## Per-branch contract facts

`intervention_delivered` and `unresolved_observers` are the two fields the fixes ADDED to `BranchResult`. The pre-fix run carries neither: that is reported as *not measured*, never as a value, because claiming a measurement the pre-fix run never made would be the same error the fixes exist to prevent.

| branch | terminal (pre) | terminal (post) | delivered (pre) | delivered (post) | unresolved observers (pre) | unresolved observers (post) |
|---|---|---|---|---|---|---|
| user_001 | cutoff | cutoff | not measured | `not_delivered` | not recorded | 7 |
| user_002 | cutoff | cutoff | not measured | `not_delivered` | not recorded | 6 |
| user_003 | cutoff | cutoff | not measured | `not_delivered` | not recorded | 6 |
| user_004 | cutoff | cutoff | not measured | `not_delivered` | not recorded | 7 |
| user_005 | cutoff | cutoff | not measured | `not_delivered` | not recorded | 7 |
| user_006 | cutoff | cutoff | not measured | `not_delivered` | not recorded | 6 |

## Unresolved observer names (defect D1)

Upstream `ObservationQueue.add` creates a queue key for whatever string the game master's free-text observer answer produced, so a name that matches no roster entity was dropped with no error and no record. The fix rosters a validated observer seam and records every non-resolving name verbatim. Nothing about routing changed -- only the silence.

- pre-fix: **not recorded at all** (the field did not exist; a dropped observer left no trace)
- post-fix: **39** non-resolving observer names recorded

| observer name the game master produced | occurrences |
|---|---|
| `Hiring Lead` | 24 |
| `hiring lead` | 15 |

Resolution reasons: `no_roster_match=39`.

Every one of these events was DROPPED -- before and after the fix. The fix does not deliver them (delivering an event to a guessed actor is a worse failure than not delivering it); it makes the loss visible instead of silent.

## Ranking

- pre-fix: **PRODUCED** (winner `user_001`)
- post-fix: **REFUSED**

The refusal is the correct result, not a failure of the re-run. `sworldmodel.outcomes.ranking` refuses to name a winner when no measured branch delivered its intervention to any actor other than the insertion actor -- which is exactly what the pre-fix run did while publishing a winner anyway. The engine's verbatim reason:

```
refusing to rank: not one of the 6 measured branches delivered its intervention to any actor other than the insertion actor, so every branch ran the counterfactual's independent variable at the same (undelivered) value and the measured differences cannot have been caused by the candidates. A winner computed from these branches would be an artifact of model sampling on identical downstream context, not a comparison. Per-branch delivery: user_001: not_delivered (no_distinctive_fragment_reached_any_other_actor); user_002: not_delivered (no_distinctive_fragment_reached_any_other_actor); user_003: not_delivered (no_distinctive_fragment_reached_any_other_actor); user_004: not_delivered (no_distinctive_fragment_reached_any_other_actor); user_005: not_delivered (no_distinctive_fragment_reached_any_other_actor); user_006: not_delivered (no_distinctive_fragment_reached_any_other_actor). Resolve the delivery failure (or run branches whose intervention reaches the world) and rank again; nothing is repaired or ranked silently here.
```

## Delivery check

| measure | pre-fix | post-fix |
|---|---|---|
| verdict | `no_salary_figure_reached_the_subject` | `offers_never_reached_the_subject` |
| distinct recipient first-turn prompts | 2 | 1 |

## Historical cutoff re-verification

The counterfactual is set before 2025-07-01, so the boundary is enforced mechanically at three stages plus a canary the validator must reject.

| stage | pre-fix | post-fix |
|---|---|---|
| enforced stages | `['pre_compile', 'pre_simulation', 'post_run_prompts']` | `['pre_compile', 'pre_simulation', 'post_run_prompts']` |
| pre-simulation scan clean | True | True |
| pre-simulation surfaces scanned | 12 | 12 |
| post-run prompt violations | 0 | 0 |
| post-run model-response findings (advisory) | 0 | 0 |
| canary rejected by the validator | True | True |
| overall clean | True | True |

The pre-compile stage is not repeated: this re-run reuses the original compile phase's frozen compiler artifact directory byte-for-byte (see `frozen_input_verification.json`), and that phase's scan is recorded at `artifacts/full_trace_validation_20260804/a16z_richard_historical/historical_cutoff_validation.json`.

## Branch-input isolation

- pre-fix verdict: `only_the_salary_differs`
- post-fix verdict: `only_the_salary_differs`

## Instrumentation

| measure | pre-fix | post-fix |
|---|---|---|
| live calls | 180 | 180 |
| errors | 0 | 0 |
| retries | 0 | 0 |
| three counters agree | True | True |

## Notes

- Guard interventions split by class -- pre-fix: 2 determined-recipient (the class D3 closed), 0 possessive nominalization (a documented deliberate conservatism in the guard's own docstring, NOT a defect), 18 unclassifiable from the 120-character excerpt the runner records, 0 other, 20 total. Post-fix: 0 determined-recipient (the class D3 closed), 0 possessive nominalization (a documented deliberate conservatism in the guard's own docstring, NOT a defect), 0 unclassifiable from the 120-character excerpt the runner records, 0 other, 0 total.
- The guard did not fire at all in the re-run, so every pre-fix rewrite is gone -- including every one that could not be classified from its truncated excerpt.
- A pre-fix determined-recipient rewrite, verbatim from the guard ledger: `Putative event to resolve:  New Media Hiring Lead: New Media Hiring Lead reviews the. People and Compensation Partner is` -- the sentence was cut at the determiner and the active actor's own content after it was deleted.
- Live model sampling is not reproducible at temperature 0, so any change in terminal status or committed text between the two runs is sampling variation on identical inputs unless it is one of the engine behaviours listed above.
- The narrative UNDER_THE_HOOD_REPORT.md is not regenerated for a re-run: it renders the whole artifact root including the compile phase, which a re-run deliberately does not repeat. This document is the re-run's narrative; the pre-fix report is unchanged and still describes the pre-fix run.

