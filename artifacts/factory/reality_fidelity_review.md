# Reality-fidelity review -- factory world

## What is real-world faithful here
- **Continuous change is exact, not stepped.** Inventory is integrated from
  the labeled 40/hour rate over precisely the elapsed intervals the shift
  calendar allows: 70 units by Mo's 09:45 wake (1.75h x 40); 320 by Monday
  close; 500 exactly at Tuesday 12:30.
  The threshold event was first projected for Monday 20:30, then *cancelled*
  when the shift ended (rate fell to zero) and re-projected from Tuesday's
  restart -- the schedule follows the physics, not the other way round.
- **Nothing teleports.** Stock moves factory -> carrier -> customer; the
  18-hour transit is a labeled inference; the confirmation is a message on a
  channel with latency, noticed on the manager's desk pattern the next
  morning (delivered 06:31, noticed 08:00).
- **The answer is a measurement.** "How many widgets has Acme received" is
  read from `acme:widgets` with the full producer lineage: transfer <-
  delivery event <- shipping action <- threshold <- recorded accruals.

## Honest limitations (labeled, not hidden)
- Production has no scrap rate, no changeover downtime, no variance; the
  rated speed is taken at face value (and labeled as scenario-given).
- Shipping ignores loading time and carrier pickup windows; the 18h transit
  is a point estimate where reality is a distribution.
- The customer is passive: no chasing emails, no partial-delivery
  negotiation. Their receiving desk deliberately has no attention model, so
  its copy of the confirmation stays unnoticed rather than being invented.
