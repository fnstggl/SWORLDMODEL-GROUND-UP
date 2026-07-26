# Reality-fidelity review -- compiled world

**Question.** How many usable blood units will the regional hospital have received by Friday noon?
**Answer produced by the trajectory.** `315.0` (cutoff)
st_vincent_regional_hospital:usable_blood_units measured at 315

**How it was produced.** 3 ledger record(s)
were cited by the terminal, each an actual state transition in this run. The
reviewer's expected causal path was:
- Starting state: hospital has 15 units
- Tuesday 4pm: centre ships 150 units to hospital
- Tuesday ~7pm: hospital receives 150 units (3-hour transit)
- Thursday 4pm: centre ships 150 units to hospital
- Thursday ~7pm: hospital receives 150 units
- Friday noon: hospital holds 15 + 150 + 150 = 315 units

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
- Affordances declared: 0; ever completed: 0
- Never performed by anyone: none
- Participants who completed no action at all: ['cascade_regional_blood_centre', 'st_vincent_regional_hospital']
- Intentions the world rejected: 0
  - none
Every declared affordance was performed at least once, so the trajectory exercised the whole compiled world.

## Honest gaps recorded during compilation
- Information delivered but with no justified way to notice it: 0
  - none
- Attention patterns the scenario left uncertain, so no rule was created: 0
  - none
- Unresolved uncertainties carried by the scenario: 0
  - none
- Deliberately excluded from the world: 3
  - Elena Cruz's actions: She oversees receipts but does not affect collection or shipping schedule.
  - Any other hospitals or blood centres: Only Cascade centre and St. Vincent hospital are relevant.
  - Weekend operations: Drive is closed weekends; shipments only Tuesday/Thursday.
