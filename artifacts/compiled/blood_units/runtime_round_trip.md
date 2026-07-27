# Runtime world (reconstructed from the lowered state)

## Terminal
- question_type: quantity; cutoff: 2026-07-24T19:00:00+00:00
- observes: {"describe": "The number of usable blood units in St. Vincent's blood bank at the deadline.\nTotal usable units in hospital bank at Friday noon = initial 15 + Tuesday 150 + Thursday 150 = 315.", "kind": "resource_measure", "params": {"holder": "st_vincent_regional_hospital", "name": "blood_units"}}

## Actors
- Courier service (id courier_service, role operating_process, tz UTC)
  believes [shipment_quantity]: {"basis": "held at the start of the situation", "statement": "Hospital knows each shipment contains 150 units", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipments arrive every Tuesday and Thursday at 7 PM", "updated_at": "2026-07-21T23:00:00+00:00"}
- St. Vincent regional hospital (id st_vincent_regional_hospital, role organization, tz America/Los_Angeles)
  believes [own_initial_stock]: {"basis": "held at the start of the situation", "statement": "Hospital knows its own initial stock of 15 units", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipment_quantity]: {"basis": "held at the start of the situation", "statement": "Hospital knows each shipment contains 150 units", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipments arrive every Tuesday and Thursday at 7 PM", "updated_at": "2026-07-21T23:00:00+00:00"}

## Channels

## Facts at genesis
- initial_stock = "15"

## Quantities at genesis
- st_vincent_regional_hospital holds 15.0 of blood_units

## Scheduled queue at genesis
(feasibility of each scheduled transfer -- source stock sufficiency under the evidenced rates and timings -- was verified at compile time by a deterministic stock walk: opening stock plus process accrual minus earlier outflows covers each commitment at its moment. The approving reality review saw the same numbers; the queue therefore carries the commitments unconditionally)
- 2026-07-21 23:00:00+00:00: world.ops ['fact.set'] tuesday_shipment_departure -- Centre dispatches 150 units to hospital at 4:00 PM Tuesday July 21. (basis: verified: e7, e9)
- 2026-07-22 02:00:00+00:00: world.ops ['fact.set'] tuesday_shipment_arrival -- Tuesday shipment arrives at hospital (basis: inferred: e7, e8)
- 2026-07-22 02:00:00+00:00: wake.actor [] scheduled_tuesday_shipment_arrival
- 2026-07-23 23:00:00+00:00: world.ops ['fact.set'] thursday_shipment_departure -- Centre dispatches 150 units to hospital at 4:00 PM Thursday July 23. (basis: verified: e7, e9)
- 2026-07-24 02:00:00+00:00: world.ops ['fact.set'] thursday_shipment_arrival -- Thursday shipment arrives at hospital (basis: inferred: e7, e8)
- 2026-07-24 02:00:00+00:00: wake.actor [] scheduled_thursday_shipment_arrival

## Action definitions (what actors MAY do)

## Processes
('active' is only the state at genesis: a process with operating periods starts inactive and the scheduled 'operating period begins/ends' entries in the queue above switch it on and off; its work accrues while switched on)
