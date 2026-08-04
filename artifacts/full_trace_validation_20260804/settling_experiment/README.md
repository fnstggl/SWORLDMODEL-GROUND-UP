# Settling experiment -- does a live sender enact its candidate?

> **UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION**
>
> This is a transparency experiment on a simulation engine. It is not a prediction about any real person, it is not calibrated against any real-world outcome, and n = 3 live samples per arm is far too small to estimate a rate precisely. Read every number below as a description of what this engine did on these runs.


## What this directory is

A two-arm live experiment on the FROZEN Peter world. It exists because the delivery root-cause investigation could not decide between two explanations of why candidate text never reached the recipient: its probe arms all used a content-blind hash-derived sender, under which candidate text cannot propagate by construction. This experiment uses a LIVE sender.

## The two hypotheses

- **R1-strong.** World construction. The live sender does not enact its candidate BECAUSE the compiled world already narrates the send as having happened. Remove the pre-narration and a live sender will enact the candidate. Practical fix: compiler prompt hygiene -- stop teaching the pre-narrated, sender-only send event.
- **R3.** Engine intervention semantics. The live sender does not enact its candidate because the engine SUGGESTS the intervention to the insertion actor rather than ENACTING it, and a free-choice actor need not restate a message it was merely told about -- pre-narrated or not. Practical fix: an engine semantic change (enact the intervention as a pre-start event authored by the insertion actor), which costs that actor the freedom to decline.

## Design

| | Arm A | Arm B |
|---|---|---|
| starting event | `Beckett Zahedi sends the prepared message to Peter Thiel.` (`visible_to: [sender]`) | none (`starting_events: []`) |
| everything else | the frozen compiled world | byte-identical |

- candidate: `user_001` (one of the user's three supplied emails), frozen in `runner_settling.SETTLING_CANDIDATE_ID` so both arms and every rep provably use the same intervention text
- seed, step budget, evaluator, model configuration: identical across arms and reps
- reps per arm: **3** (live sampling varies at temperature 0, so a single sample could not distinguish 'never' from 'not this time')
- sender: LIVE. Every actor turn in this experiment is a live provider completion recorded through the ordinary recorder.
- one forced control: the game master's observer-ROUTING answer is forced to the full roster, so the observer-routing defect closed at `c5a81214` cannot confound the measurement. That is the ONLY harness-supplied text; every interception is recorded verbatim in each rep's `forced_observer_control.json`.

## Result

**R3 survived.** the live sender did not enact its candidate in ANY arm-B rep (0/3), i.e. removing the pre-narration did not make the sender restate the message. R1-strong predicted the opposite and is refuted in its strong form; the engine's suggest-not-enact intervention semantics (R3) is what remains standing.

See `SETTLING_RESULT.md` for the full reading and `SETTLING_MEASUREMENTS.json` for the machine-readable numbers.

## Layout

```
settling_experiment/
  README.md                    this file
  SETTLING_RESULT.md           the verdict and what it means
  SETTLING_MEASUREMENTS.json   every number, machine-readable
  arm_a/rep_{1,2,3}/           arm A, one live branch per rep
  arm_b/rep_{1,2,3}/           arm B, one live branch per rep
  harness_shakedown/           the first two live runs, KEPT and not counted; see its own README for why
```

Each rep directory carries the standard ledgers: `freeze_manifest.json`, `arm_design.json`, `adapter/`, `all_llm_calls.jsonl`, `branches/<candidate>/{step_ledger,observations,guard_ledger,committed_events}.jsonl`, `branches/<candidate>/{branch_result,actor_memories,raw_engine_log}.json`, `trace_report.json`, `recommendation_report.json` (or `ranking_refusal.json`), `candidate_delivery_check.json`, `forced_observer_control.json`, `settling_measurement.json`, `instrumentation.json`, `provider_probe.json`.

