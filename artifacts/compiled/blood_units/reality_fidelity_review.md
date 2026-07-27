# Reality-fidelity review -- discovery-compiled world

**Question.** How many usable blood units will the regional hospital have received by Friday noon?
**Answer produced by the trajectory.** `15.0` (cutoff)
st_vincent_regional_hospital:blood_units measured at 15

## How this world was built
- Five small discovery calls described the possible world; code assembled
  the canonical graph (15 nodes, 18 edges),
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
- Participants who completed no action: ['courier_service', 'st_vincent_regional_hospital']


## Known mechanical limits stated plainly
- Scheduled transfers execute unconditionally; their feasibility (source
  stock sufficiency) was verified at compile time by the proofs and the
  reality review, and the kernel itself does not clamp an overdraw. A
  world whose schedule outruns its stocks must be caught at review, and
  this one was checked there.

## Unresolved uncertainty carried honestly
- Whether the mobile collection drive operates as scheduled on each day of the week, and whether the average rate of 12 units per hour holds exactly for each hour open. Also, whether any collected units are added to the centre's stock before shipments depart. (about: collection drive operation)
- How many usable units the centre has at the time of each shipment departure (Tuesday and Thursday 4 PM), given that the drive collects during the week and the centre may also have other inflows/outflows not mentioned. (about: centre stock after Monday 9 AM)
- Whether the Tuesday and Thursday shipments each contain exactly 150 units, as per the cooler capacity, and whether the centre has enough stock to fill them. Also, whether the shipment includes units collected that day. (about: shipment content)
- Whether the hospital uses any of its own stock between Monday 9 AM and Friday noon, and whether it receives any other shipments besides the Tuesday and Thursday ones. (about: hospital stock changes)
- Whether the 3-hour travel time is exact, and whether the Thursday shipment arrives before Friday noon (departure Thursday 4 PM, arrival ~7 PM Thursday, so yes, but need to confirm no delays). (about: timing precision)
