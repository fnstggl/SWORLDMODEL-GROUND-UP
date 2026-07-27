# Reality-fidelity review -- compiled world

**Question.** Does the hospital ethics committee approve the compassionate-use request at its 12 March meeting?
**Answer produced by the trajectory.** `no` (cutoff)
The committee does not approve the compassionate-use request.

**How it was produced.** 1 ledger record(s)
were cited by the terminal, each an actual state transition in this run. The
reviewer's expected causal path was:
- 2026-03-10 08:00: Manufacturer bulletin published with updated safety data.
- Lindqvist notices bulletin (monitors same day).
- Lindqvist prepares safety review (half-day, completes by ~12:00 on March 10).
- Lindqvist sends review via email to Osei, Patel, Doyle.
- Osei and Patel receive email within minutes (check email).
- Doyle does not receive email (on retreat, no email access).
- 2026-03-12 14:00: Meeting starts.
- Osei puts motion to approve (5 minutes).
- Osei votes approve (has current safety data, favorable).
- Patel votes approve (review favorable).
- Doyle does not vote (no safety assessment provided to her).
- Tally: 2 approve, 0 reject. Majority approves.
- Resolution: committee approves compassionate-use request.

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
- Affordances declared: 3; ever completed: 0
- Never performed by anyone: ['prepare_and_send_safety_review', 'put_motion_to_approve', 'vote']
- Participants who completed no action at all: ['dr_helen_osei', 'dr_raj_patel', 'manufacturer', 'sister_margaret_doyle', 'tomas_lindqvist']
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
- Deliberately excluded from the world: 2
  - Any other hospital business: Not relevant to the question.
  - Details of the therapy or patient: Not needed to determine approval outcome.
