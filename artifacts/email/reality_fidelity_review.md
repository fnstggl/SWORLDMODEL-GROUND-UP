# Reality-fidelity review -- email world

## What is real-world faithful here
- **Time is real.** Alice's email leaves at 21:18:30 ET Friday (composing took
  8 minutes after her 21:10 decision, delivery 30s). Bob does not see it for
  the whole weekend; his notice fires Monday 09:00 Pacific. The elapsed gap is
  61h41m30s, not 62h41m30s, because 2026-03-08 (spring forward) removed an
  hour -- the kernel derived that from the tz database, not from a modeler.
- **Information is local.** Bob's reply exists only because a noticed,
  delivered message carried Alice's question; his answer quotes his own prior
  belief (the $4.2M figure he locked on March 3), not world state he cannot
  see.
- **Nothing is instant.** notice -> read (6 min) -> interpret -> compose
  (12 min) -> deliver (30s) -> Alice notices on her half-hour cadence.

## Honest limitations (labeled, not hidden)
- The 30-minute inbox cadence is an *inferred* attention model ("office
  worker") and is marked as such in the rule's provenance. Real noticing is
  burstier: phones buzz, people peek at 22:00. A phone-notification channel
  with its own rule would be the faithful extension.
- Bob starts reading the instant he notices. Realistically there is a
  seconds-to-minutes gap (finishing coffee, other emails first). The kernel
  supports it (the mind could schedule the read later); the scripted mind
  keeps it simple.
- Weekend attention is modeled as *zero*, which overstates disconnection --
  many people glance at email on Saturday. The correction would again be an
  explicit, provenance-labeled weekend rule, not a kernel change.
