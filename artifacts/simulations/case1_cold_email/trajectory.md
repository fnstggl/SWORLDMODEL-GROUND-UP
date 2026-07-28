# Trajectory
**Question:** Is this cold email likely to get a response from Mark Cuban within two weeks? Jordan Reyes, founder of a bootstrapped sports-analytics startup, has drafted a short cold email to Mark Cuban's public address asking for a 15-minute call and referencing Cuban's Cost Plus Drugs pricing playbook. Jordan will send it today and does not plan to follow up.
**Result:** cutoff — UNRESOLVED

*terminal check at 2026-07-27T14:00:00+00:00: UNRESOLVED — No event shows Mark Cuban sending a response to Jordan Reyes's email, and the deadline has not passed.*

**World judgment** (starting_event) at 2026-07-27T14:00:00+00:00

> trigger: Jordan Reyes sends the cold email to Mark Cuban's public email address.
>
> The email is sent from Jordan's email client to Mark Cuban's public email address. It enters the email delivery system, but it has not yet arrived in Mark Cuban's inbox.
- proposes: The email leaves Jordan's outbox and is transmitted over the internet towards Mark Cuban's email server. (for ['jordan_reyes'], observed=False, after now)

---

## 2026-07-27T14:00:00+00:00 — committed event `e16`

The email leaves Jordan's outbox and is transmitted over the internet towards Mark Cuban's email server.

- available to: jordan_reyes
- AVAILABLE but NOT observed
- source: world_call:c2

*terminal check at 2026-07-27T14:00:00+00:00: UNRESOLVED — The current time is before the cutoff (2026-08-10T09:00:00-05:00) and no response from Mark Cuban has been committed yet.*

**World judgment** (attention_check) at 2026-07-27T15:00:00+00:00

> trigger: Does anything available to jordan_reyes reach their attention now?  Reason for looking: something is available to them that they have not observed
>
> Jordan is not currently looking at his outbox or email status; he sent the email and moved on. The transmission event is not something he monitors in real time.
- proposes: (no concrete event yet)

*terminal check at 2026-07-27T15:00:00+00:00: UNRESOLVED — The current time is before the deadline of 2026-08-10T09:00:00-05:00, and no committed event shows Mark Cuban sending a response.*

*terminal check at 2026-08-10T14:00:00+00:00: UNRESOLVED — No event shows Mark Cuban sending a response, and the cutoff time has not yet passed.*
