# SETTLING RESULT

> **UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION**
>
> This is a transparency experiment on a simulation engine. It is not a prediction about any real person, it is not calibrated against any real-world outcome, and n = 3 live samples per arm is far too small to estimate a rate precisely. Read every number below as a description of what this engine did on these runs.


## The question

Does a LIVE sender enact its candidate when the send is not already pre-narrated?

Two prior live scenarios found that candidate text never reached the recipient actor. The root-cause investigation named two surviving explanations and could not separate them, because every probe arm it ran used a content-blind hash-derived sender under which candidate text cannot propagate by construction. This experiment separates them with a live sender.

- **R1-strong.** World construction. The live sender does not enact its candidate BECAUSE the compiled world already narrates the send as having happened. Remove the pre-narration and a live sender will enact the candidate. Practical fix: compiler prompt hygiene -- stop teaching the pre-narrated, sender-only send event.
- **R3.** Engine intervention semantics. The live sender does not enact its candidate because the engine SUGGESTS the intervention to the insertion actor rather than ENACTING it, and a free-choice actor need not restate a message it was merely told about -- pre-narrated or not. Practical fix: an engine semantic change (enact the intervention as a pre-start event authored by the insertion actor), which costs that actor the freedom to decline.

## Design (two arms, identical except the starting event)

Both arms run on the same frozen compiled Peter world (re-adapted from scenario 1's frozen compiler artifact directory by deterministic code -- zero compiler calls), the same single candidate `user_001`, the same seed, the same step budget, the same evaluator and the same model configuration.

- **Arm A (pre-narrated).** The world exactly as compiled: one starting event, `Beckett Zahedi sends the prepared message to Peter Thiel.`, `visible_to: [beckett_zahedi]`.
- **Arm B (not pre-narrated).** The same world with `starting_events: []` -- the shape the frozen manual fixtures use. Rebuilt through the contract gate, and the recorded field-level diff shows `starting_events` is the only field that differs.

The game master's observer-ROUTING answer is forced to the full roster in BOTH arms, so the observer-routing defect closed at `c5a81214` cannot confound the measurement. That control is the only harness-supplied text in the experiment; every actor turn is live.

n = 3 reps in arm A and 3 in arm B.

## What was measured

| measure | Arm A (pre-narrated) | Arm B (not pre-narrated) |
|---|---|---|
| sender enacted the candidate verbatim on its first turn | **0/3** | **0/3** |
| distinctive candidate text in the recipient's own prompts | **0/3** | **0/3** |
| production `intervention_delivered.status` | `['not_delivered', 'not_delivered', 'not_delivered']` | `['not_delivered', 'not_delivered', 'not_delivered']` |
| ranking produced or REFUSED | `['REFUSED', 'REFUSED', 'REFUSED']` | `['REFUSED', 'REFUSED', 'REFUSED']` |
| terminal status | `['success', 'success', 'cutoff']` | `['cutoff', 'cutoff', 'cutoff']` |
| unresolved observer names (D1 fix) | `[0, 0, 0]` | `[0, 0, 0]` |
| agency-guard interventions | `[1, 1, 0]` | `[0, 0, 0]` |
| longest shared character run, candidate vs sender first turn | `[8, 8, 7]` | `[25, 10, 16]` |
| candidate/first-turn token overlap (Jaccard) | `[0.0843, 0.0843, 0.0864]` | `[0.1818, 0.1753, 0.1031]` |

Rates are `hits/n`. The `intervention_delivered` column is the value of the production field added by the D2 fix, computed by `sworldmodel.counterfactuals.delivery` from each branch's own artifacts -- not by this harness.

### Arm A -- pre_narrated

the world exactly as the live compiler emitted it: one starting event narrating the send, visible to the sender only

- reps recorded: **3**
- sender enacted the candidate verbatim on its first turn: **0/3**
- distinctive candidate text appeared in the recipient's own prompts: **0/3**
- production `intervention_delivered.status` per rep: `['not_delivered', 'not_delivered', 'not_delivered']`
- ranking per rep: `['REFUSED', 'REFUSED', 'REFUSED']`
- terminal status per rep: `['success', 'success', 'cutoff']`
- unresolved observer names recorded per rep (D1 fix): `[0, 0, 0]`
- forced observer-routing interceptions per rep: `[4, 4, 4]`
- agency-guard interventions per rep: `[1, 1, 0]`
- longest shared character run between the candidate and the sender's first turn: `[8, 8, 7]` (content-blind, does not enter the verdict)
- candidate/first-turn token overlap (Jaccard): `[0.0843, 0.0843, 0.0864]`
- distinct recipient first-turn prompt hashes: **2** across 3 reps
- live calls: 12 (errors 0, retries 0)

The sender's actual first turn, verbatim, per rep:

rep 1:

```
Beckett Zahedi waits for a reply, checking his inbox periodically but not sending any follow-up or additional messages, keeping the ball in Peter Thiel's court as requested.
```

rep 2:

```
Beckett Zahedi waits for a reply, checking his inbox periodically but not sending any follow-up or additional messages, keeping the ball in Peter Thiel's court as requested.
```

rep 3:

```
Beckett Zahedi waits for a reply, checking his inbox periodically but not sending any follow-up or additional messages, keeping the ball in Peter Thiel's court.
```


### Arm B -- not_pre_narrated

the same world with starting_events removed, so nothing tells the sender the send already happened

- reps recorded: **3**
- sender enacted the candidate verbatim on its first turn: **0/3**
- distinctive candidate text appeared in the recipient's own prompts: **0/3**
- production `intervention_delivered.status` per rep: `['not_delivered', 'not_delivered', 'not_delivered']`
- ranking per rep: `['REFUSED', 'REFUSED', 'REFUSED']`
- terminal status per rep: `['cutoff', 'cutoff', 'cutoff']`
- unresolved observer names recorded per rep (D1 fix): `[0, 0, 0]`
- forced observer-routing interceptions per rep: `[4, 4, 4]`
- agency-guard interventions per rep: `[0, 0, 0]`
- longest shared character run between the candidate and the sender's first turn: `[25, 10, 16]` (content-blind, does not enter the verdict)
- candidate/first-turn token overlap (Jaccard): `[0.1818, 0.1753, 0.1031]`
- distinct recipient first-turn prompt hashes: **3** across 3 reps
- live calls: 12 (errors 0, retries 0)

The sender's actual first turn, verbatim, per rep:

rep 1:

```
Beckett Zahedi reviews the draft one final time, confirms the subject line and body are accurate and that the "not production-validated" caveat is prominent, then clicks send to Peter Thiel through the established email channel, and immediately begins drafting the one-page technical memo to have it ready if Peter responds.
```

rep 2:

```
Beckett Zahedi reviews the draft one more time, tightens the subject line to "Aurelius: 7.24× GPU goodput/$ (replay only, not prod-validated)" and the opening line to "I'm not asking for money—I want your criticism," then sends the email to Peter Thiel's known contact address and sets a calendar reminder to follow up in five days if no reply.
```

rep 3:

```
Beckett Zahedi reviews the drafted email one final time, confirms the subject line and the explicit caveat that the results are replay-only and not production-proven, then sends it to Peter Thiel through the established channel, noting in his own calendar to follow up if no reply arrives by August 10.
```


## Verdict

**R3 survived.**

the live sender did not enact its candidate in ANY arm-B rep (0/3), i.e. removing the pre-narration did not make the sender restate the message. R1-strong predicted the opposite and is refuted in its strong form; the engine's suggest-not-enact intervention semantics (R3) is what remains standing.

Decision rule, fixed before the runs: the experiment turns on arm B's enactment rate, because arm B is the only arm in which R1-strong makes a positive prediction. Arm B enactment above zero and above arm A's would have supported R1-strong; arm B enactment at zero refutes it in its strong form.

### What else the arms differed in (recorded, not part of the rule)

Removing the pre-narration did NOT leave the sender unchanged. Read the quoted turns above: in arm A the sender WAITS in every rep; in arm B it performs the send in every rep. It just writes its OWN message rather than the candidate's. The content-blind overlap numbers point at the same thing without judging it:

| | Arm A | Arm B |
|---|---|---|
| mean candidate/first-turn token overlap | `0.085` | `0.1534` |
| mean longest shared character run | `7.6667` | `17.0` |

a higher overlap in arm B with enactment still at zero means the sender's first turn CHANGED but its message text remained its own: it wrote about the send in the candidate's vocabulary without reproducing the candidate. Read the quoted turns; they are the evidence, these numbers only point at it.

So the pre-narrated sender-only send event IS a real world-construction defect -- it suppresses the sender's own send action -- and it is still not the reason the candidate fails to reach the recipient. Both statements are supported here; neither one substitutes for the other.

## What this means for the practical fix

**an engine semantic change, not compiler prompt hygiene.**

Compiler prompt hygiene is still worth doing on its own merits -- `compiler/scene_prompts.py` ships the literal exemplar that teaches the sender-only pre-narrated send event, and the R2 visibility-incoherence warning now records when a starting event names an actor outside its `visible_to`. But this experiment shows that hygiene alone would NOT have made the candidate reach the recipient: with the pre-narration removed entirely, the live sender still did not restate the candidate. It sent an email it wrote itself.

The remaining lever is the one the lead deliberately did not pull in this pass: enact the intervention as a pre-start event authored by the insertion actor (R3 + R4a). That is a SEMANTIC change to the accepted counterfactual -- the insertion actor loses the freedom to decline the candidate -- and it is a decision to be taken explicitly, not smuggled in as a bug fix. What already landed (D2) is the honest interim: the engine now measures whether the intervention reached anyone and REFUSES to rank when it did not, so an invalid comparison surfaces as a refusal instead of a published winner.

## The follow-up experiment this result cancels

A follow-up was planned and is deliberately NOT run: a variant of the supplied scenario with all three candidates on an arm-B world, to see whether the full path can produce a genuine candidate comparison when the world is compiled coherently.

It is cancelled by this result. Its premise was that a live sender enacts its candidate once the pre-narration is gone. Arm B measured that premise directly and it did not hold: 0/3 reps reproduced any distinctive candidate text, and 0/3 got any of it into the recipient's prompts. Running three candidates instead of one on the same world would produce three more undelivered branches and one more refusal -- more live calls for a result already measured. Running it anyway and reporting the refusal as if it were new information would be padding, not evidence.

## Limitations, stated plainly

- **n = 3 per arm is small.** Three live samples cannot estimate a rate precisely, and they cannot rule out a low-probability behaviour: a 0/3 result is consistent with any true rate below roughly 0.6 at 95% confidence. What 0/3 does establish is that the behaviour is not the common case, which is what the two hypotheses actually disagree about.
- **One candidate, one world, one model.** The measurement is of candidate `user_001` on the Peter world against deepseek `deepseek-chat` (the provider actually served `deepseek-v4-flash`). Another candidate, cast, or model could behave differently.
- **Enactment is measured verbatim.** A fragment counts only if it appears in the sender's own turn character-for-character. A sender that faithfully paraphrased its candidate would be scored as not enacting. The sender's full first turn is quoted above so a reader can check that reading against the text.
- **The observer broadcast is a forced control, not the production default.** In production the game master answers that question freely. Forcing it removes a known confound; it also means these runs are more favourable to delivery than production would be, so a non-delivery here is the stronger result.
- **This says nothing about Peter Thiel.** It is a measurement of an engine's intervention semantics that happens to use a compiled world with those names in it.

## Provenance

- live calls: **24** (errors 0, retries 0)
- provider actually served: `deepseek-v4-flash` for requested `deepseek-chat`
- repository SHA: `f90f28fdb17c512d3f1035ac9eef7b9fd47f2b54`
- generated at: 2026-08-04T21:23:44Z

