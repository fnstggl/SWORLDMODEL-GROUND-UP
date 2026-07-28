# Trajectory
**Question:** Will Dr Aline Mercier read Ravi Patel's thesis chapter and send comments before the faculty deadline on Friday? Ravi emailed the chapter to his supervisor on Monday morning. Aline is on the hiring committee this week, teaches Tuesday and Thursday, and has four other students waiting on feedback.
**Result:** failed — n/a

*terminal check at 2026-07-27T08:00:00+00:00: UNRESOLVED — The current time is before the deadline, and no events show Dr Aline Mercier reading the chapter or sending comments.*

**World judgment** (starting_event) at 2026-07-27T08:00:00+00:00

> trigger: Ravi Patel sends an email to Dr Aline Mercier with his thesis chapter attached.
>
> The email has been sent by Ravi's system and is now traveling through the university mail server. Aline is not currently checking email; she is likely preparing for her 9:00 lecture.
- proposes: The email arrives in Dr Aline Mercier's inbox on the university email server. (for ['dr_aline_mercier'], observed=False, after now)
- wake dr_aline_mercier after 1 hour: Aline may check her email after her lecture or during a break.

**ravi_patel decides** at 2026-07-27T08:00:00+00:00

> I've just sent my chapter to Aline, so I'll wait for her response before following up.

---

## 2026-07-27T08:00:00+00:00 — committed event `e18`

The email arrives in Dr Aline Mercier's inbox on the university email server.

- available to: dr_aline_mercier
- AVAILABLE but NOT observed
- source: world_call:c2

**World judgment** (event_consequence) at 2026-07-27T08:00:00+00:00

> trigger: The email arrives in Dr Aline Mercier's inbox on the university email server.
>
> It is 8 AM on Monday. Aline has not yet checked her email this morning; she may be preparing for the day or commuting. The email sits unread in her inbox.
- proposes: (no concrete event yet)
- wake dr_aline_mercier after 2 hours: She will likely check her email at the start of her workday around 10 AM.

*terminal check at 2026-07-27T08:00:00+00:00: UNRESOLVED — The deadline has not passed and no event shows Dr Aline Mercier reading the chapter or sending comments.*
