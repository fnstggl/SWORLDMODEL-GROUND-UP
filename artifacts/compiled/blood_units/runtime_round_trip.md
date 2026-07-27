# Runtime world (reconstructed from the lowered state)

## Terminal
- question_type: quantity; cutoff: 2026-07-24T19:00:00+00:00
- observes: {"describe": "St. Vincent regional hospital holds a certain number of usable blood units at Friday noon, July 24, 2026.\nThe number of usable blood units in St. Vincent regional hospital's blood bank at the deadline.", "kind": "resource_measure", "params": {"holder": "st_vincent_regional_hospital", "name": "usable_blood_units"}}

## Actors
- Cascade regional blood centre (id cascade_regional_blood_centre, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "The drive collects at a measured average of 12 usable units per hour while it is open.", "updated_at": "2026-07-21T23:
  believes [collection_week]: {"basis": "held at the start of the situation", "statement": "The collection week under consideration runs Monday 20 July to Friday 24 July 2026.", "updated_at": "2026-07-21T23:00:
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "The drive is open Monday to Friday from 9:00 AM to 5:00 PM America/Los_Angeles.", "updated_at": "2026-07-21T23:00:00+0
  believes [hospital_initial_stock]: {"basis": "held at the start of the situation", "statement": "St. Vincent regional hospital held 15 usable units at the same moment.", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [initial_stock]: {"basis": "held at the start of the situation", "statement": "The centre held 40 usable units in stock at 9:00 AM on Monday 20 July 2026.\nThe hospital knows its own initial stock 
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "The Tuesday and Thursday shipments each move 150 units, the capacity of the centre's transport cooler.", "updated_at":
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "The centre ships its available stock to St. Vincent every Tuesday and Thursday at 4:00 PM America/Los_Angeles.\nThe ho
  believes [transit_time]: {"basis": "held at the start of the situation", "statement": "A shipment takes about 3 hours to reach the hospital and be received into its bank.", "updated_at": "2026-07-21T23:00:
- St. Vincent regional hospital (id st_vincent_regional_hospital, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "The drive collects at a measured average of 12 usable units per hour while it is open.", "updated_at": "2026-07-21T23:
  believes [collection_week]: {"basis": "held at the start of the situation", "statement": "The collection week under consideration runs Monday 20 July to Friday 24 July 2026.", "updated_at": "2026-07-21T23:00:
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "The drive is open Monday to Friday from 9:00 AM to 5:00 PM America/Los_Angeles.", "updated_at": "2026-07-21T23:00:00+0
  believes [hospital_initial_stock]: {"basis": "held at the start of the situation", "statement": "St. Vincent regional hospital held 15 usable units at the same moment.", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [initial_stock]: {"basis": "held at the start of the situation", "statement": "The centre held 40 usable units in stock at 9:00 AM on Monday 20 July 2026.\nThe hospital knows its own initial stock 
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "The Tuesday and Thursday shipments each move 150 units, the capacity of the centre's transport cooler.", "updated_at":
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "The centre ships its available stock to St. Vincent every Tuesday and Thursday at 4:00 PM America/Los_Angeles.\nThe ho
  believes [transit_time]: {"basis": "held at the start of the situation", "statement": "A shipment takes about 3 hours to reach the hospital and be received into its bank.", "updated_at": "2026-07-21T23:00:

## Channels

## Facts at genesis
- centre_initial_stock = "true"
- hospital_initial_stock = "true"
- initial_stock = "15"

## Quantities at genesis
- cascade_regional_blood_centre holds 40.0 of usable_blood_units
- st_vincent_regional_hospital holds 15.0 of blood_units

## Scheduled queue at genesis
(feasibility of each scheduled transfer -- source stock sufficiency under the evidenced rates and timings -- was verified at compile time by the causal proofs and the approving reality review; the queue therefore carries the commitments unconditionally)
- 2026-07-21 23:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-21 23:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] tuesday_shipment -- Shipment of 150 units dispatched every Tuesday at 4:00 PM.
The centre dispatches 150 units to St. Vincent on Tuesday, Ju
- 2026-07-21 23:00:00+00:00: wake.actor [] scheduled_tuesday_shipment
- 2026-07-22 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-22 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-22 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-22 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-22 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-22 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-22 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-22 23:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-23 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-23 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-23 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-23 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-23 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-23 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-23 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-23 23:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-23 23:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] thursday_shipment -- Shipment of 150 units dispatched every Thursday at 4:00 PM.
The centre dispatches 150 units to St. Vincent on Thursday,
- 2026-07-23 23:00:00+00:00: wake.actor [] scheduled_thursday_shipment
- 2026-07-24 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-24 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-24 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-24 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-24 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-24 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-24 16:00:00+00:00: world.ops ['process.active'] operating period begins

## Action definitions (what actors MAY do)

## Processes
- monday_collection: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "monday_collection", "last_applied": "2026-07-21T23:00:00+00:00", "note": "Centre's 2026 throughput report", "rate_per_hour": 12.0, "resource": "usable_blood_units"}
- thursday_collection_before_dispatch: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "thursday_collection_before_dispatch", "last_applied": "2026-07-21T23:00:00+00:00", "note": "Centre's 2026 throughput report", "rate_per_hour": 12.0, "resource": "usable_blood_units"}
- tuesday_collection_before_dispatch: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "tuesday_collection_before_dispatch", "last_applied": "2026-07-21T23:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "usable_blood_units"}
- wednesday_collection: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "wednesday_collection", "last_applied": "2026-07-21T23:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "usable_blood_units"}
