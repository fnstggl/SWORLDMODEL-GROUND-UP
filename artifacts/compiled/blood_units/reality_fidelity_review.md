# Reality-fidelity review -- discovery-compiled world

**Question.** How many usable blood units will the regional hospital have received by Friday noon?
**Answer produced by the trajectory.** `315.0` (cutoff)
st_vincent_regional_hospital:blood_units measured at 315

## How this world was built
- Five small discovery calls described the possible world; code assembled
  the canonical graph (26 nodes, 44 edges),
  proved backward producer chains and forward executability, bound each
  semantic item to a universal capability, and emitted the runtime world
  deterministically. Repairs used: {'resolution_ambiguity_adjudication': 1, 'process:collection_process_monday': 2}.
- No step wrote the future: scheduled events carry evidenced times only,
  and every actor decision is an affordance the actor may or may not take.

## What this run does NOT establish
- Actors follow fixture-authored scripts (or none). A run driven by scripts proves the compiled world executes; it is NEVER a forecast of behaviour.
- No backtest, calibration or comparison with a real outcome exists here.

## Did the trajectory exercise the world?
- Affordances never performed: none
- Participants who completed no action: ['cascade_regional_blood_centre', 'st_vincent_regional_hospital']


## Known mechanical limits stated plainly
- Scheduled transfers execute unconditionally; their feasibility (source
  stock sufficiency) was verified at compile time by the proofs and the
  reality review, and the kernel itself does not clamp an overdraw. A
  world whose schedule outruns its stocks must be caught at review, and
  this one was checked there.

## Unresolved uncertainty carried honestly
- none declared
