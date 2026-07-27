# Runtime world (reconstructed from the lowered state)

## Terminal
- question_type: quantity; cutoff: 2026-07-24T19:00:00+00:00
- observes: {"describe": "St. Vincent regional hospital holds a specific number of usable blood units at Friday noon, 24 July 2026.\nThe count of usable blood units in St. Vincent hospital's inventory at the cutoff time.", "kind": "resource_measure", "params": {"holder": "st_vincent_regional_hospital", "name": "blood_units"}}

## Actors
- Cascade regional blood centre (id cascade_regional_blood_centre, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "Measured average of 12 usable units per hour while drive is open", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [collection_week]: {"basis": "held at the start of the situation", "statement": "Week of Monday 20 July to Friday 24 July 2026", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "Drive open Monday to Friday 9 AM to 5 PM America/Los_Angeles", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [initial_stock]: {"basis": "held at the start of the situation", "statement": "40 usable units at 9 AM Monday 20 July\nHospital knows its own initial stock of 15 units", "updated_at": "2026-07-20T0
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "Each shipment moves 150 units", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipments arrive every Tuesday and Thursday at 7:00 PM (3 hours after 4:00 PM dispatch)\nShipments ever
- St. Vincent regional hospital (id st_vincent_regional_hospital, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "Measured average of 12 usable units per hour while drive is open", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [collection_week]: {"basis": "held at the start of the situation", "statement": "Week of Monday 20 July to Friday 24 July 2026", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "Drive open Monday to Friday 9 AM to 5 PM America/Los_Angeles", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [initial_stock]: {"basis": "held at the start of the situation", "statement": "40 usable units at 9 AM Monday 20 July\nHospital knows its own initial stock of 15 units", "updated_at": "2026-07-20T0
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "Each shipment moves 150 units", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipments arrive every Tuesday and Thursday at 7:00 PM (3 hours after 4:00 PM dispatch)\nShipments ever

## Channels

## Facts at genesis
- centre_initial_stock = "true"
- hospital_initial_stock = "true"
- initial_stock = "15"

## Quantities at genesis
- cascade_regional_blood_centre holds 40.0 of blood_units
- st_vincent_regional_hospital holds 15.0 of blood_units

## Scheduled queue at genesis
(feasibility of each scheduled transfer -- source stock sufficiency under the evidenced rates and timings -- was verified at compile time by the causal proofs and the approving reality review; the queue therefore carries the commitments unconditionally)
- 2026-07-20 16:00:00+00:00: world.ops ['process.active:monday_collection'] operating period begins
- 2026-07-21 00:00:00+00:00: world.ops ['process.active:monday_collection'] operating period ends
- 2026-07-21 16:00:00+00:00: world.ops ['process.active:tuesday_collection_before_4pm'] operating period begins
- 2026-07-21 23:00:00+00:00: world.ops ['process.active:tuesday_collection_before_4pm'] operating period ends
- 2026-07-21 23:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] tuesday_shipment -- Ship 150 units to St. Vincent regional hospital every Tuesday at 4:00 PM
The centre dispatches 150 units on Tuesday 21 J
- 2026-07-21 23:00:00+00:00: wake.actor [] scheduled_tuesday_shipment
- 2026-07-22 16:00:00+00:00: world.ops ['process.active:wednesday_collection'] operating period begins
- 2026-07-23 00:00:00+00:00: world.ops ['process.active:wednesday_collection'] operating period ends
- 2026-07-23 16:00:00+00:00: world.ops ['process.active:thursday_collection_before_4pm'] operating period begins
- 2026-07-23 23:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] thursday_shipment -- Ship 150 units to St. Vincent regional hospital every Thursday at 4:00 PM
The centre dispatches 150 units on Thursday 2
- 2026-07-23 23:00:00+00:00: wake.actor [] scheduled_thursday_shipment
- 2026-07-24 00:00:00+00:00: world.ops ['process.active:thursday_collection_before_4pm'] operating period ends

## Action definitions (what actors MAY do)

## Processes
('active' is only the state at genesis: a process with operating periods starts inactive and the scheduled 'operating period begins/ends' entries in the queue above switch it on and off; its work accrues while switched on)
- monday_collection: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "monday_collection", "last_applied": "2026-07-20T07:00:00+00:00", "note": "Centre's 2026 throughput report", "rate_per_hour": 12.0, "resource": "blood_units"}
- thursday_collection_before_4pm: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "thursday_collection_before_4pm", "last_applied": "2026-07-20T07:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "blood_units"}
- tuesday_collection_before_4pm: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "tuesday_collection_before_4pm", "last_applied": "2026-07-20T07:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "blood_units"}
- wednesday_collection: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "wednesday_collection", "last_applied": "2026-07-20T07:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "blood_units"}
