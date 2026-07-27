# Runtime world (reconstructed from the lowered state)

## Terminal
- question_type: quantity; cutoff: 2026-07-24T19:00:00+00:00
- observes: {"describe": "St. Vincent regional hospital holds a certain number of usable blood units at Friday noon, July 24, 2026.\nThe number of usable blood units in St. Vincent hospital's inventory at the deadline.", "kind": "resource_measure", "params": {"holder": "st_vincent_regional_hospital", "name": "usable_blood_units"}}

## Actors
- Cascade regional blood centre (id cascade_regional_blood_centre, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "The centre knows the average collection rate of 12 units per hour.", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "The centre knows the drive is open Mon-Fri 9-5.", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [own_stock]: {"basis": "held at the start of the situation", "statement": "The centre knows its own stock levels.", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "The centre knows each shipment moves 150 units.", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipments arrive every Tuesday and Thursday at about 7 PM (4 PM + 3 hours)", "updated_at": "2026-07-20T
  believes [shipment_size]: {"basis": "held at the start of the situation", "statement": "Hospital knows each shipment is 150 units", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [shipping_schedule]: {"basis": "held at the start of the situation", "statement": "The centre knows shipments depart every Tuesday and Thursday at 4 PM.", "updated_at": "2026-07-20T07:00:00+00:00"}
- St. Vincent regional hospital (id st_vincent_regional_hospital, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "The centre knows the average collection rate of 12 units per hour.", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "The centre knows the drive is open Mon-Fri 9-5.", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [initial_hospital_stock]: {"basis": "held at the start of the situation", "statement": "Hospital knows its own stock of 15 units at 9 AM Monday", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "The centre knows each shipment moves 150 units.", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipments arrive every Tuesday and Thursday at about 7 PM (4 PM + 3 hours)", "updated_at": "2026-07-20T
  believes [shipment_size]: {"basis": "held at the start of the situation", "statement": "Hospital knows each shipment is 150 units", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [shipping_schedule]: {"basis": "held at the start of the situation", "statement": "The centre knows shipments depart every Tuesday and Thursday at 4 PM.", "updated_at": "2026-07-20T07:00:00+00:00"}

## Channels

## Facts at genesis
- holds_stock = "true"
- initial_centre_stock = "true"
- initial_hospital_stock = "15 units"

## Quantities at genesis
- cascade_regional_blood_centre holds 40.0 of usable_blood_units
- st_vincent_regional_hospital holds 15.0 of blood_units

## Scheduled queue at genesis
(feasibility of each scheduled transfer -- source stock sufficiency under the evidenced rates and timings -- was verified at compile time by a deterministic stock walk: opening stock plus process accrual minus earlier outflows covers each commitment at its moment. The approving reality review saw the same numbers; the queue therefore carries the commitments unconditionally)
- 2026-07-20 16:00:00+00:00: world.ops ['process.active:monday_collection'] operating period begins
- 2026-07-21 00:00:00+00:00: world.ops ['process.active:monday_collection'] operating period ends
- 2026-07-21 16:00:00+00:00: world.ops ['process.active:tuesday_collection_before_4pm'] operating period begins
- 2026-07-21 23:00:00+00:00: world.ops ['process.active:tuesday_collection_before_4pm'] operating period ends
- 2026-07-21 23:00:00+00:00: world.ops ['fact.set'] tuesday_shipment -- Shipment of 150 units to St. Vincent regional hospital every Tuesday at 4:00 PM.
The centre dispatches 150 units to St. 
- 2026-07-21 23:00:00+00:00: wake.actor [] scheduled_tuesday_shipment
- 2026-07-22 02:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] tuesday_shipment_arrives -- The Tuesday shipment of 150 units arrives at St. Vincent hospital and is received into its bank. (basis: inferre
- 2026-07-22 16:00:00+00:00: world.ops ['process.active:wednesday_collection'] operating period begins
- 2026-07-23 00:00:00+00:00: world.ops ['process.active:wednesday_collection'] operating period ends
- 2026-07-23 16:00:00+00:00: world.ops ['process.active:thursday_collection_before_4pm'] operating period begins
- 2026-07-23 23:00:00+00:00: world.ops ['fact.set'] thursday_shipment -- Shipment of 150 units to St. Vincent regional hospital every Thursday at 4:00 PM.
The centre dispatches 150 units to St
- 2026-07-23 23:00:00+00:00: wake.actor [] scheduled_thursday_shipment
- 2026-07-24 00:00:00+00:00: world.ops ['process.active:thursday_collection_before_4pm'] operating period ends
- 2026-07-24 02:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] thursday_shipment_arrives -- The Thursday shipment of 150 units arrives at St. Vincent hospital and is received into its bank. (basis: infer

## Action definitions (what actors MAY do)

## Processes
('active' is only the state at genesis: a process with operating periods starts inactive and the scheduled 'operating period begins/ends' entries in the queue above switch it on and off; its work accrues while switched on)
- monday_collection: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "monday_collection", "last_applied": "2026-07-20T07:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "usable_blood_units"}
- thursday_collection_before_4pm: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "thursday_collection_before_4pm", "last_applied": "2026-07-20T07:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "usable_blood_units"}
- tuesday_collection_before_4pm: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "tuesday_collection_before_4pm", "last_applied": "2026-07-20T07:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "usable_blood_units"}
- wednesday_collection: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "wednesday_collection", "last_applied": "2026-07-20T07:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "usable_blood_units"}
