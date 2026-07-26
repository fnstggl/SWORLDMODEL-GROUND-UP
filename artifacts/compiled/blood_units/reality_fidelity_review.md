# Reality-fidelity review -- compiled world

**Question.** How many usable blood units will the regional hospital have received by Friday noon?
**Answer produced by the trajectory.** `315.0` (cutoff)
st_vincent_regional_hospital:usable_blood_units measured at 315

**How it was produced.** 3 ledger record(s)
were cited by the terminal, each an actual state transition in this run. The
reviewer's expected causal path was:
- Monday 09:00: Centre has 40 units, hospital has 15 units.
- Monday 09:00-17:00: Collection drive produces 12*8=96 units (total centre: 136).
- Tuesday 09:00-16:00: Collection produces 12*7=84 units (total centre: 220).
- Tuesday 16:00: Shipment of 150 units leaves centre (centre: 70).
- Tuesday 19:00: Shipment arrives at hospital (hospital: 165).
- Wednesday 09:00-17:00: Collection produces 96 units (centre: 166).
- Thursday 09:00-16:00: Collection produces 84 units (centre: 250).
- Thursday 16:00: Shipment of 150 units leaves centre (centre: 100).
- Thursday 19:00: Shipment arrives at hospital (hospital: 315).
- Friday 12:00: Hospital holds 315 units.

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
- Deliberately excluded from the world: 2
  - Elena Cruz: She oversees receipts but does not affect the collection rate or shipping schedule; her actions are not needed to determine the final quantity.
  - Any other hospitals or blood centres: Only St. Vincent receives shipments from Cascade; no other parties are involved.
