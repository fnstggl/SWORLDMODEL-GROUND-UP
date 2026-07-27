# Runtime world (reconstructed from the lowered state)

## Terminal
- question_type: quantity; cutoff: 2026-07-24T19:00:00+00:00
- observes: {"describe": "St. Vincent regional hospital holds N usable blood units at Friday noon, July 24, 2026.\nThe number of usable blood units in St. Vincent's inventory at Friday noon.", "kind": "resource_measure", "params": {"holder": "st_vincent_regional_hospital", "name": "hospital_units_at_deadline"}}

## Actors
- Cascade regional blood centre (id cascade_regional_blood_centre, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "Average 12 usable units per hour while drive is open", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "Drive open Mon-Fri 9 AM to 5 PM America/Los_Angeles", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [initial_stock]: {"basis": "held at the start of the situation", "statement": "40 usable units at 9 AM Monday 20 July 2026", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "150 units per shipment", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "Shipments every Tuesday and Thursday at 4 PM", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipment_size]: {"basis": "held at the start of the situation", "statement": "Hospital knows each shipment is 150 units.", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipment_transit_time]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipment takes about 3 hours.", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipping_schedule]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipments arrive every Tuesday and Thursday.", "updated_at": "2026-07-21T23:00:00+00:00"}
- St. Vincent regional hospital (id st_vincent_regional_hospital, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "Average 12 usable units per hour while drive is open", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "Drive open Mon-Fri 9 AM to 5 PM America/Los_Angeles", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [initial_hospital_stock]: {"basis": "held at the start of the situation", "statement": "Hospital knows its own stock at start.", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "150 units per shipment", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "Shipments every Tuesday and Thursday at 4 PM", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipment_size]: {"basis": "held at the start of the situation", "statement": "Hospital knows each shipment is 150 units.", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipment_transit_time]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipment takes about 3 hours.", "updated_at": "2026-07-21T23:00:00+00:00"}
  believes [shipping_schedule]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipments arrive every Tuesday and Thursday.", "updated_at": "2026-07-21T23:00:00+00:00"}

## Channels

## Facts at genesis
- collection_rate = "12"
- initial_centre_stock = "true"
- initial_hospital_stock = "15"
- initial_stock = "40"
- shipment_capacity = "150"
- shipment_schedule = "true"
- shipment_transit_time = "3"

## Quantities at genesis
- cascade_regional_blood_centre holds 40.0 of hospital_units_at_deadline
- st_vincent_regional_hospital holds 15.0 of usable_blood_units

## Scheduled queue at genesis
- 2026-07-21 23:00:00+00:00: world.ops ['fact.set'] tuesday_shipment -- Dispatch 150 units to St. Vincent hospital
The centre dispatches 150 units on Tuesday July 21, 2026 at 4:00 PM. (basis: 
- 2026-07-21 23:00:00+00:00: wake.actor [] scheduled_tuesday_shipment
- 2026-07-22 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-22 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-22 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-22 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-22 02:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] tuesday_shipment_received -- Shipment dispatched Tuesday 4:00 PM arrives about 3 hours later, so by 7:00 PM Tuesday.
The Tuesday shipment of
- 2026-07-22 02:00:00+00:00: wake.actor [] scheduled_tuesday_shipment_received
- 2026-07-22 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-22 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-22 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-22 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-23 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-23 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-23 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-23 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-23 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-23 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-23 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-23 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-23 23:00:00+00:00: world.ops ['fact.set'] thursday_shipment -- Dispatch 150 units to St. Vincent hospital
The centre dispatches 150 units on Thursday July 23, 2026 at 4:00 PM. (basis
- 2026-07-23 23:00:00+00:00: wake.actor [] scheduled_thursday_shipment
- 2026-07-24 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-24 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-24 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-24 00:00:00+00:00: world.ops ['process.active'] operating period ends
- 2026-07-24 02:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] thursday_shipment_received -- Shipment dispatched Thursday 4:00 PM arrives about 3 hours later, so by 7:00 PM Thursday.
The Thursday shipmen
- 2026-07-24 02:00:00+00:00: wake.actor [] scheduled_thursday_shipment_received
- 2026-07-24 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-24 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-24 16:00:00+00:00: world.ops ['process.active'] operating period begins
- 2026-07-24 16:00:00+00:00: world.ops ['process.active'] operating period begins

## Action definitions (what actors MAY do)

## Processes
- monday_collection: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "monday_collection", "last_applied": "2026-07-21T23:00:00+00:00", "note": "Centre's 2026 throughput report", "rate_per_hour": 12.0, "resource": "hospital_units_at_deadline"}
- thursday_collection_before_4pm: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "thursday_collection_before_4pm", "last_applied": "2026-07-21T23:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "hospital_units_at_deadline"}
- tuesday_collection_before_4pm: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "tuesday_collection_before_4pm", "last_applied": "2026-07-21T23:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "hospital_units_at_deadline"}
- wednesday_collection: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "wednesday_collection", "last_applied": "2026-07-21T23:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "hospital_units_at_deadline"}
