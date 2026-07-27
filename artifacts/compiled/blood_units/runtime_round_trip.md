# Runtime world (reconstructed from the lowered state)

## Terminal
- question_type: quantity; cutoff: 2026-07-24T19:00:00+00:00
- observes: {"describe": "St. Vincent regional hospital holds a specific number of usable blood units at Friday noon, July 24, 2026.\nThe count of usable blood units in St. Vincent hospital's inventory at the deadline.", "kind": "resource_measure", "params": {"holder": "st_vincent_regional_hospital", "name": "blood_units"}}

## Actors
- Cascade regional blood centre (id cascade_regional_blood_centre, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "Average collection rate of 12 units per hour while drive is open", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "Drive open Monday to Friday 9:00 AM to 5:00 PM", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [initial_stock]: {"basis": "held at the start of the situation", "statement": "Hospital knows its own initial stock of 15 units\nOwn stock of 40 units at Monday 9:00 AM", "updated_at": "2026-07-20T
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "Each shipment moves 150 units", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipments arrive every Tuesday and Thursday around 7 PM (3 hours after 4 PM dispatch)\nShipments every 
  believes [transit_time]: {"basis": "held at the start of the situation", "statement": "Shipment takes about 3 hours to reach hospital", "updated_at": "2026-07-20T07:00:00+00:00"}
- St. Vincent regional hospital (id st_vincent_regional_hospital, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "Average collection rate of 12 units per hour while drive is open", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "Drive open Monday to Friday 9:00 AM to 5:00 PM", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [initial_stock]: {"basis": "held at the start of the situation", "statement": "Hospital knows its own initial stock of 15 units\nOwn stock of 40 units at Monday 9:00 AM", "updated_at": "2026-07-20T
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "Each shipment moves 150 units", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipments arrive every Tuesday and Thursday around 7 PM (3 hours after 4 PM dispatch)\nShipments every 
  believes [transit_time]: {"basis": "held at the start of the situation", "statement": "Shipment takes about 3 hours to reach hospital", "updated_at": "2026-07-20T07:00:00+00:00"}

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
- 2026-07-20 16:00:00+00:00: world.ops ['process.active:collection_monday'] operating period begins
- 2026-07-21 00:00:00+00:00: world.ops ['process.active:collection_monday'] operating period ends
- 2026-07-21 16:00:00+00:00: world.ops ['process.active:collection_tuesday'] operating period begins
- 2026-07-21 23:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] shipment_dispatched_tuesday -- Ship 150 units to St. Vincent regional hospital every Tuesday at 4:00 PM
The centre dispatches a shipment of 
- 2026-07-21 23:00:00+00:00: wake.actor [] scheduled_shipment_dispatched_tuesday
- 2026-07-22 00:00:00+00:00: world.ops ['process.active:collection_tuesday'] operating period ends
- 2026-07-22 16:00:00+00:00: world.ops ['process.active:collection_wednesday'] operating period begins
- 2026-07-23 00:00:00+00:00: world.ops ['process.active:collection_wednesday'] operating period ends
- 2026-07-23 16:00:00+00:00: world.ops ['process.active:collection_thursday'] operating period begins
- 2026-07-23 23:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] shipment_dispatched_thursday -- Ship 150 units to St. Vincent regional hospital every Thursday at 4:00 PM
The centre dispatches a shipment o
- 2026-07-23 23:00:00+00:00: wake.actor [] scheduled_shipment_dispatched_thursday
- 2026-07-24 00:00:00+00:00: world.ops ['process.active:collection_thursday'] operating period ends

## Action definitions (what actors MAY do)

## Processes
('active' is only the state at genesis: a process with operating periods starts inactive and the scheduled 'operating period begins/ends' entries in the queue above switch it on and off; its work accrues while switched on)
- collection_monday: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "collection_monday", "last_applied": "2026-07-20T07:00:00+00:00", "note": "Centre's 2026 throughput report", "rate_per_hour": 12.0, "resource": "blood_units"}
- collection_thursday: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "collection_thursday", "last_applied": "2026-07-20T07:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "blood_units"}
- collection_tuesday: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "collection_tuesday", "last_applied": "2026-07-20T07:00:00+00:00", "note": "Centre's 2026 throughput report", "rate_per_hour": 12.0, "resource": "blood_units"}
- collection_wednesday: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "collection_wednesday", "last_applied": "2026-07-20T07:00:00+00:00", "note": "Centre's 2026 throughput report states 12 usable units per hour.", "rate_per_hour": 12.0, "resource": "blood_units"}
