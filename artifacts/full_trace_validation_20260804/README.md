# UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION

## Full-trace validation of the accepted engine -- two live runs

**Not a prediction of anyone's behaviour.** These are uncalibrated, one-shot simulations run against a live language model for the purpose of seeing exactly what the engine does. Nothing here is evidence about Peter Thiel, or about any real person.

- **Model**: `deepseek-chat` via `https://api.deepseek.com` (`deepseek`), temperature 0 at every seam
- **Window**: 2026-08-04T18:10:38Z -> 2026-08-11T18:10:38Z (actual UTC run start + 7 days)
- **Repository SHA at run time**: `7e30a8ea8ef3e8e171ed15c35f964284b9872e6e`
- **Compiler**: `minimal_scene_v1`, status `compiled`, run ONCE for scenario 1 and reused byte-for-byte by scenario 2

## Instrumentation: no call bypassed the recorder

```json
{
  "claim": "every provider request issued at the network boundary produced exactly one ledger record with a distinct call_id; no live call bypassed the recorder",
  "all_equal": true,
  "values": {
    "ledger_records_written": 51,
    "network_boundary_requests": 51,
    "seam_attempt_total": 51,
    "distinct_call_ids_on_disk": 51,
    "records_on_disk": 51
  }
}
```

Three counters incremented at three different places -- the network boundary (immediately before the HTTP request), each wrapper's own attempt counter, and the ledger writer -- all agree. Every attempt, including any retry or failure, is one JSONL record with its own `call_id`.

## Scenarios

| scenario | candidate source | branches | winner | terminal statuses | live calls |
| --- | --- | --- | --- | --- | --- |
| `peter_supplied` | user-supplied, verbatim | 3 | `user_002` | user_001=cutoff, user_002=success, user_003=cutoff | 24 |
| `peter_generated` | generated (one-shot, live) | 3 | `gen_001` | gen_001=success, gen_002=cutoff, gen_003=cutoff | 25 |

## The headline finding

- `peter_supplied`: candidate-delivery verdict **`candidates_never_reached_the_recipient`** -- 1 distinct recipient first-turn prompt(s) across 3 branches; `user_001` 0/6 candidate fragments delivered, `user_002` 0/5 candidate fragments delivered, `user_003` 0/6 candidate fragments delivered.
- `peter_generated`: candidate-delivery verdict **`candidates_never_reached_the_recipient`** -- 1 distinct recipient first-turn prompt(s) across 3 branches; `gen_001` 0/1 candidate fragments delivered, `gen_002` 0/1 candidate fragments delivered, `gen_003` 0/1 candidate fragments delivered.

In both scenarios the candidate text never reached the recipient actor, so **the rankings are not evidence that one candidate is better than another**. See section 17 of each report for the exact mechanism, recorded step by step.

## Evidence classification

- `peter_supplied`: USER_SUPPLIED=6, PUBLICLY_VERIFIED=1, TEST_ASSUMPTION=3, UNKNOWN=3
- `peter_generated`: USER_SUPPLIED=6, PUBLICLY_VERIFIED=1, TEST_ASSUMPTION=3, UNKNOWN=3

Conservative by rule: nothing about a real person's private personality, compensation, inbox behaviour, calendar availability, internal opinions or exact authority may be classified `PUBLICLY_VERIFIED`. The engine's contracts have no first-class observed / inferred / latent fields, so those classifications live ONLY in `evidence_manifest.json` and the engine never reads them.

## Layout

```
README.md
shared/{environment,model_configuration,instrumentation_validation,run_identity}.json
peter_supplied/
  decision_problem.json  evidence_manifest.json  freeze_manifest.json
  compiler/              (the real compiler's own artifacts + its call ledger)
  adapter/               (adapted world, base plan, id map, sidecar)
  candidates/            (the three candidates as contracts)
  branches/<candidate_id>/
     llm_calls.jsonl        every live call in that branch
     step_ledger.jsonl      AUDITOR-ONLY per-step record
     observations.jsonl     what each actor was handed
     guard_ledger.jsonl     pre-guard / post-guard per step
     committed_events.jsonl the committed world events
     branch_result.json     the contract result
     trace_report.json      the engine's own trace entry
  evaluator_ledger.json  recommendation_result.json
  candidate_delivery_check.json  measurement_audit.json
  UNDER_THE_HOOD_REPORT.md
peter_generated/         (same, plus generator_prompt.txt, generator_raw_response.txt,
                          generator_parsed.json, world_reuse_proof.json)
```

`branches/*/step_ledger.jsonl` is **auditor-only**: it deliberately places every actor's private context and every prompt in one file. No actor ever saw that view. The report sections that represent an actor's prompt show only that actor's own prompt.

## Reproducing

```bash
PYTHONPATH=. /home/user/engine-env/bin/python \
  -m experiments.full_trace_validation.runner_peter --phase compile
# then --phase supplied, --phase generated, --phase audit, --phase validate
```

Live calls are required; the harness never fabricates model output. A phase that cannot reach the provider fails loudly with every recorded attempt left in the ledger.

