# Trajectory
**Question:** Will Sam Okonjo confirm the plumber's appointment before 6pm today? Bristol Plumbing texted Sam at 9:00 this morning asking him to confirm a Thursday 8am slot by 6pm or lose it. Sam has been waiting three weeks for this appointment because his boiler is out, he is at his desk all day with his phone next to him, and confirming takes one text message.
**Result:** resolved — YES

*terminal check at 2026-07-28T08:00:00+00:00: UNRESOLVED — The committed event shows a message arriving, but not Sam Okonjo sending a confirmation text; no such event has occurred yet and the deadline has not passed.*

**World judgment** (starting_event) at 2026-07-28T08:00:00+00:00

> trigger: Bristol Plumbing's text message arrives on Sam Okonjo's phone.
>
> The message is on Sam's phone, but it is 8 AM and he may be asleep or not checking his phone yet.
- proposes: (no concrete event yet)
- wake sam_okonjo after 2 hours: Check if Sam has noticed the message by 10 AM, a more typical time for checking messages.

**sam_okonjo decides** at 2026-07-28T08:00:00+00:00

> I just saw the message arrive, but it's only 8am and they texted at 9am? That's odd. I'll read it properly now and reply to confirm.
- attempts: Read the text message from Bristol Plumbing and reply 'yes' to confirm the Thursday 8am slot.
- privately: I have received a confirmation request from Bristol Plumbing and need to reply by 6pm.

**World judgment** (actor_intention) at 2026-07-28T08:00:00+00:00

> trigger: sam_okonjo attempts: Read the text message from Bristol Plumbing and reply 'yes' to confirm the Thursday 8am slot.
>
> Sam has the phone in hand, the message is visible on screen. He reads it and taps 'Reply'. The reply message is composed and sent.
- proposes: Sam Okonjo reads the text message from Bristol Plumbing and sends a reply with 'yes' to confirm the Thursday 8am slot. (for ['sam_okonjo'], observed=True, after now)

---

## 2026-07-28T08:00:00+00:00 — committed event `e18`

Sam Okonjo reads the text message from Bristol Plumbing and sends a reply with 'yes' to confirm the Thursday 8am slot.

- available to: sam_okonjo
- OBSERVED by them
- source: world_call:c4

**sam_okonjo decides** at 2026-07-28T08:00:00+00:00

> I have already replied to the text, so I will now set a reminder for the appointment and continue with my work.
- attempts: Set a calendar reminder for Thursday 8am for the boiler repair
- attempts: Return to my desk work
- privately: I have confirmed the appointment, so I expect the repair to happen on Thursday

**World judgment** (actor_intention) at 2026-07-28T08:00:00+00:00

> trigger: sam_okonjo attempts: Set a calendar reminder for Thursday 8am for the boiler repair
>
> Sam picks up his phone and opens the calendar app, but he is momentarily distracted by a notification from his work email. He sets the phone down without completing the reminder.
- proposes: Sam opens his calendar app but is interrupted by a work email notification and puts the phone down before setting the reminder. (for ['sam_okonjo'], observed=True, after 30 seconds)
- wake sam_okonjo after 10 minutes: He may return to setting the reminder after dealing with the email.

**World judgment** (actor_intention) at 2026-07-28T08:00:00+00:00

> trigger: sam_okonjo attempts: Return to my desk work
>
> Sam has already sent the confirmation reply, so nothing further happens regarding the text. He returns to his desk work.
- proposes: (no concrete event yet)

*terminal check at 2026-07-28T08:00:00+00:00: YES — Sam Okonjo sent a reply confirming the appointment via text message before the deadline.*
