# Reality-fidelity review -- discovery-compiled world

**Question.** How many usable blood units will the regional hospital have received by Friday noon?
**Answer produced by the trajectory.** `300.0` (cutoff)
st_vincent_regional_hospital:usable_blood_units measured at 300

## How this world was built
- Five small discovery calls described the possible world; code assembled
  the canonical graph (28 nodes, 51 edges),
  proved backward producer chains and forward executability, bound each
  semantic item to a universal capability, and emitted the runtime world
  deterministically. Repairs used: {'resolution_ambiguity_adjudication': 1}.
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
- Whether the centre's stock at 4 PM Tuesday (after Monday and Tuesday collections) is at least 150 units to ship. The centre starts with 40 units, collects 12 units/hour for 8 hours Monday (96 units) and 7 hours Tuesday before 4 PM (84 units), total 220 units, which is enough. However, any unstated usage or wastage could reduce stock; the evidence does not mention any other demand or losses. (about: state:centre_has_enough_stock_tuesday)
- Whether the centre's stock at 4 PM Thursday (after Wednesday and Thursday collections, minus Tuesday shipment) is at least 150 units. After Tuesday shipment of 150, remaining stock is 70 units (220-150). Wednesday collection: 12 units/hour for 8 hours = 96 units, total 166. Thursday collection before 4 PM: 7 hours = 84 units, total 250. Enough. Again, unstated usage or losses could change this. (about: state:centre_has_enough_stock_thursday)
- Whether the Tuesday shipment actually arrives and is received by the hospital before Friday noon. The shipment departs at 4 PM Tuesday, takes 3 hours, arrives at 7 PM Tuesday. That is well before Friday noon, so it should be received. But any delay or rejection could affect it. (about: event:tuesday_shipment_arrives)
- Whether the Thursday shipment arrives and is received by Friday noon. Departs 4 PM Thursday, arrives 7 PM Thursday, well before deadline. Same caveats. (about: event:thursday_shipment_arrives)
- The hospital starts with 15 units at 9 AM Monday. No evidence of any usage or additional deliveries besides the two shipments. So it remains 15 until shipments arrive. (about: state:initial_hospital_stock)
- The centre collects 12 units/hour for 8 hours on Monday (9 AM to 5 PM). That is 96 units. This is based on average rate; actual could vary but evidence states measured average. (about: process:monday_collection)
- On Tuesday, collection runs 9 AM to 4 PM (7 hours) before the 4 PM shipment departure. That yields 84 units. Same average rate assumption. (about: process:tuesday_collection_before_4pm)
- Wednesday collection: 9 AM to 5 PM, 8 hours, 96 units. (about: process:wednesday_collection)
- Thursday collection: 9 AM to 4 PM, 7 hours, 84 units. (about: process:thursday_collection_before_4pm)
