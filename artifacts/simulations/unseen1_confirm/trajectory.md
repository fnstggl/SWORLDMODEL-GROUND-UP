# Trajectory
**Question:** Will Sam Okonjo confirm the plumber's appointment before 6pm today? Bristol Plumbing texted Sam at 9:00 this morning asking him to confirm a Thursday 8am slot by 6pm or lose it. Sam has been waiting three weeks for this appointment because his boiler is out, he is at his desk all day with his phone next to him, and confirming takes one text message.
**Result:** resolved — YES

*terminal check at 2026-07-28T08:00:00+00:00: UNRESOLVED — No event shows Sam Okonjo sending a text message confirming the appointment; only a received message is recorded.*

**World judgment** (starting_event) at 2026-07-28T08:00:00+00:00

> trigger: Bristol Plumbing's text message arrives on Sam Okonjo's phone.
>
> The message has already arrived and been observed by Sam. No new concrete event occurs.
- proposes: (no concrete event yet)

**sam_okonjo decides** at 2026-07-28T08:00:00+00:00

> I need to reply to confirm the appointment immediately so I don't lose the slot.
- attempts: I pick up my phone and reply 'Yes' to confirm the Thursday 8am slot.
- privately: I have replied to Bristol Plumbing to secure the appointment.

**World judgment** (actor_intention) at 2026-07-28T08:00:00+00:00

> trigger: sam_okonjo attempts: I pick up my phone and reply 'Yes' to confirm the Thursday 8am slot.
>
> Sam picks up his phone, unlocks it, and opens the messaging app. He sees the Bristol Plumbing text and begins typing a reply.
- proposes: Sam types 'Yes' and presses send. The message is sent from his phone to Bristol Plumbing's number. (for ['sam_okonjo'], observed=True, after 10 seconds)

---

## 2026-07-28T08:00:10+00:00 — committed event `e17`

Sam types 'Yes' and presses send. The message is sent from his phone to Bristol Plumbing's number.

- available to: sam_okonjo
- OBSERVED by them
- source: world_call:c4

**sam_okonjo decides** at 2026-07-28T08:00:10+00:00

> I have already sent the confirmation, so I will continue with my day and wait for any further communication.
- attempts: I will put my phone down and resume my work.
- privately: I believe the appointment is confirmed now that I have sent the reply.

**World judgment** (actor_intention) at 2026-07-28T08:00:10+00:00

> trigger: sam_okonjo attempts: I will put my phone down and resume my work.
>
> Sam has just sent the message and is now putting his phone down to resume work. Nothing else happens immediately.
- proposes: (no concrete event yet)

*terminal check at 2026-07-28T08:00:10+00:00: YES — Event e17 shows Sam Okonjo sent a text message confirming the appointment before the deadline.*
