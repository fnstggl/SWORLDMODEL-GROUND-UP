# Runtime world (reconstructed from the lowered state)

## Terminal
- question_type: quantity; cutoff: 2026-07-24T19:00:00+00:00
- observes: {"describe": "The number of usable blood units in St. Vincent hospital's inventory at the deadline Friday noon July 24.\nThe number of usable blood units in St. Vincent hospital's inventory at the deadline.", "kind": "resource_measure", "params": {"holder": "st_vincent_regional_hospital", "name": "blood_units"}}

## Actors
- Cascade regional blood centre (id cascade_regional_blood_centre, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "The drive collects at a measured average of 12 usable units per hour while it is open.", "updated_at": "2026-07-20T07:
  believes [collection_week]: {"basis": "held at the start of the situation", "statement": "The collection week under consideration runs Monday 20 July to Friday 24 July 2026.", "updated_at": "2026-07-20T07:00:
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "The drive is open Monday to Friday from 9:00 AM to 5:00 PM America/Los_Angeles.", "updated_at": "2026-07-20T07:00:00+0
  believes [initial_stock_centre]: {"basis": "held at the start of the situation", "statement": "The centre held 40 usable units in stock at 9:00 AM on Monday 20 July 2026.", "updated_at": "2026-07-20T07:00:00+00:00
  believes [initial_stock_hospital]: {"basis": "held at the start of the situation", "statement": "Hospital knows its own initial stock of 15 units.\nSt. Vincent regional hospital held 15 usable units at the same mome
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "The Tuesday and Thursday shipments each move 150 units, the capacity of the centre's transport cooler.", "updated_at":
  believes [shipment_transit_time]: {"basis": "held at the start of the situation", "statement": "A shipment takes about 3 hours to reach the hospital and be received into its bank.", "updated_at": "2026-07-20T07:00:
  believes [shipping_schedule]: {"basis": "held at the start of the situation", "statement": "The centre ships its available stock to St. Vincent every Tuesday and Thursday at 4:00 PM America/Los_Angeles.", "upda
- St. Vincent regional hospital (id st_vincent_regional_hospital, role organization, tz America/Los_Angeles)
  believes [collection_rate]: {"basis": "held at the start of the situation", "statement": "The drive collects at a measured average of 12 usable units per hour while it is open.", "updated_at": "2026-07-20T07:
  believes [collection_week]: {"basis": "held at the start of the situation", "statement": "The collection week under consideration runs Monday 20 July to Friday 24 July 2026.", "updated_at": "2026-07-20T07:00:
  believes [drive_schedule]: {"basis": "held at the start of the situation", "statement": "The drive is open Monday to Friday from 9:00 AM to 5:00 PM America/Los_Angeles.", "updated_at": "2026-07-20T07:00:00+0
  believes [initial_stock_hospital]: {"basis": "held at the start of the situation", "statement": "Hospital knows its own initial stock of 15 units.\nSt. Vincent regional hospital held 15 usable units at the same mome
  believes [shipment_capacity]: {"basis": "held at the start of the situation", "statement": "The Tuesday and Thursday shipments each move 150 units, the capacity of the centre's transport cooler.", "updated_at":
  believes [shipment_schedule]: {"basis": "held at the start of the situation", "statement": "Hospital knows shipments arrive every Tuesday and Thursday at 7:00 PM.", "updated_at": "2026-07-20T07:00:00+00:00"}
  believes [shipment_transit_time]: {"basis": "held at the start of the situation", "statement": "A shipment takes about 3 hours to reach the hospital and be received into its bank.", "updated_at": "2026-07-20T07:00:
  believes [shipping_schedule]: {"basis": "held at the start of the situation", "statement": "The centre ships its available stock to St. Vincent every Tuesday and Thursday at 4:00 PM America/Los_Angeles.", "upda

## Channels

## Facts at genesis
- initial_stock_centre = "40 units"
- initial_stock_hospital = "true"

## Quantities at genesis
- cascade_regional_blood_centre holds 40.0 of blood_units
- st_vincent_regional_hospital holds 15.0 of blood_units

## Scheduled queue at genesis
(feasibility of each scheduled transfer -- source stock sufficiency under the evidenced rates and timings -- was verified at compile time by a deterministic stock walk: opening stock plus process accrual minus earlier outflows covers each commitment at its moment. The approving reality review saw the same numbers; the queue therefore carries the commitments unconditionally)
- 2026-07-20 16:00:00+00:00: world.ops ['process.active:collection_process_monday'] operating period begins
- 2026-07-21 00:00:00+00:00: world.ops ['process.active:collection_process_monday'] operating period ends
- 2026-07-21 16:00:00+00:00: world.ops ['process.active:collection_process_tuesday'] operating period begins
- 2026-07-21 23:00:00+00:00: world.ops ['fact.set'] tuesday_shipment_dispatch -- Centre dispatches 150 units to hospital at 4:00 PM Tuesday July 21.
Shipment of 150 units dispatched every Tues
- 2026-07-21 23:00:00+00:00: wake.actor [] scheduled_tuesday_shipment_dispatch
- 2026-07-22 00:00:00+00:00: world.ops ['process.active:collection_process_tuesday'] operating period ends
- 2026-07-22 02:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] tuesday_shipment_arrival -- Shipment of 150 units arrives from centre on Tuesday 21 July 2026 at 7:00 PM America/Los_Angeles.
Tuesday shipme
- 2026-07-22 02:00:00+00:00: wake.actor [] scheduled_tuesday_shipment_arrival
- 2026-07-22 16:00:00+00:00: world.ops ['process.active:collection_process_wednesday'] operating period begins
- 2026-07-23 00:00:00+00:00: world.ops ['process.active:collection_process_wednesday'] operating period ends
- 2026-07-23 16:00:00+00:00: world.ops ['process.active:collection_process_thursday'] operating period begins
- 2026-07-23 23:00:00+00:00: world.ops ['fact.set'] thursday_shipment_dispatch -- Centre dispatches 150 units to hospital at 4:00 PM Thursday July 23.
Shipment of 150 units dispatched every Th
- 2026-07-23 23:00:00+00:00: wake.actor [] scheduled_thursday_shipment_dispatch
- 2026-07-24 00:00:00+00:00: world.ops ['process.active:collection_process_thursday'] operating period ends
- 2026-07-24 02:00:00+00:00: world.ops ['fact.set', 'resource.transfer'] thursday_shipment_arrival -- Shipment of 150 units arrives from centre on Thursday 23 July 2026 at 7:00 PM America/Los_Angeles.
Thursday shi
- 2026-07-24 02:00:00+00:00: wake.actor [] scheduled_thursday_shipment_arrival
- 2026-07-24 16:00:00+00:00: world.ops ['process.active:collection_process_friday_morning'] operating period begins
- 2026-07-24 19:00:00+00:00: world.ops ['process.active:collection_process_friday_morning'] operating period ends

## Action definitions (what actors MAY do)

## Processes
('active' is only the state at genesis: a process with operating periods starts inactive and the scheduled 'operating period begins/ends' entries in the queue above switch it on and off; its work accrues while switched on)
- collection_process_friday_morning: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "collection_process_friday_morning", "last_applied": "2026-07-20T07:00:00+00:00", "note": "e2: measured average of 12 usable units per hour", "rate_per_hour": 12.0, "resource": "blood_units"}
- collection_process_monday: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "collection_process_monday", "last_applied": "2026-07-20T07:00:00+00:00", "note": "Centre's 2026 throughput report: average 12 usable units per hour.", "rate_per_hour": 12.0, "resource": "blood_units"}
- collection_process_thursday: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "collection_process_thursday", "last_applied": "2026-07-20T07:00:00+00:00", "note": "Centre's 2026 throughput report", "rate_per_hour": 12.0, "resource": "blood_units"}
- collection_process_tuesday: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "collection_process_tuesday", "last_applied": "2026-07-20T07:00:00+00:00", "note": "Centre's 2026 throughput report: average 12 usable units per hour", "rate_per_hour": 12.0, "resource": "blood_units"}
- collection_process_wednesday: {"active": false, "basis": "verified", "capacity": null, "holder": "cascade_regional_blood_centre", "id": "collection_process_wednesday", "last_applied": "2026-07-20T07:00:00+00:00", "note": "Centre's 2026 throughput report: average 12 usable units per hour.", "rate_per_hour": 12.0, "resource": "blood_units"}
