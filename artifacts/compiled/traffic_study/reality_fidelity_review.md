# Reality-fidelity review -- compiled world

**Question.** Will Councilmember Reyes have read the finalized traffic study before the council meeting begins?
**Answer produced by the trajectory.** `no` (cutoff)
Councilmember Reyes has not noticed and read the finalized traffic study before the council meeting begins.

**How it was produced.** 1 ledger record(s)
were cited by the terminal, each an actual state transition in this run. The
reviewer's expected causal path was:
- 2026-02-18T10:00:00-06:00: external reviewer sends peer-review sign-off to Santos via city email
- 2026-02-18T10:01:00-06:00: Santos receives sign-off (email delivery ~1 min)
- 2026-02-18T10:01:00-06:00 to 10:20:00-06:00: Santos sends finalized study to Reyes (20 min action)
- 2026-02-18T10:21:00-06:00: Reyes receives study email
- 2026-02-18T10:30:00-06:00 or 12:30:00-06:00: Reyes notices study at next email check (every 2 hours, first check after 8:30 AM is ~10:30 AM)
- 2026-02-18T10:30:00-06:00 to 11:45:00-06:00 (or later): Reyes reads study (75 min)
- 2026-02-19T19:00:00-06:00: Meeting starts; Reyes has read the study

## What this run does establish
- The world was built from the frozen evidence package alone, through one
  fixed semantic contract, and lowered by code that makes no model calls.
- Every duration, rate, latency and attention pattern carries a provenance
  label; the lowering layer refuses to invent any of them.
- Information was delivered on real routes with real latency, and noticed
  only where a justified attention rule existed.
- The terminal reads world state and cites the records that produced it.

## What this run does NOT establish
- **Behavioural realism.** Actors here are the deterministic MechanicalMind: on each wake they take the first affordance whose parameters they can fill. That proves the compiled world is executable and that the causal path reaches the terminal. It says nothing about what real people would choose.
- **Forecast accuracy.** No backtest, no calibration, no comparison to a real
  outcome has been performed.
- **Evidence quality.** The evidence package was hand-frozen; live retrieval
  is deliberately not part of this run.

## Did the actors actually exercise this world?
- Affordances declared: 2; ever completed: 0
- Never performed by anyone: ['read_the_finalized_study', 'send_the_finalized_study']
- Participants who completed no action at all: ['alma_reyes', 'external_reviewer', 'miguel_santos']
- Intentions the world rejected: 0
  - none
**READ THIS ANSWER WITH CARE.** The result is negative AND part of the world was never exercised, so it reflects the limits of the authored script rather than the situation itself.

## Honest gaps recorded during compilation
- Information delivered but with no justified way to notice it: 0
  - none
- Attention patterns the scenario left uncertain, so no rule was created: 0
  - none
- Unresolved uncertainties carried by the scenario: 0
  - none
- Deliberately excluded from the world: 3
  - Other council members: Only Reyes's reading matters for the answer.
  - Committee clerk: Only mentioned as source of information; does not affect the outcome.
  - Other corridor items: Only the Riverside corridor study is relevant.
