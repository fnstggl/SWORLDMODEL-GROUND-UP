# Trajectory
**Question:** Is this cold email likely to get a response from Mark Cuban within two weeks? Jordan Reyes, founder of a bootstrapped sports-analytics startup, has drafted a short cold email to Mark Cuban's public address asking for a 15-minute call and referencing Cuban's Cost Plus Drugs pricing playbook. Jordan will send it today and does not plan to follow up.
**Result:** cutoff — NO_AT_CUTOFF

*terminal check at 2026-07-27T14:00:00+00:00: UNRESOLVED — No response from Mark Cuban has been committed yet, and the deadline (2026-08-10T09:00:00-05:00) has not passed.*

**World judgment** (starting_event) at 2026-07-27T14:00:00+00:00

> trigger: Jordan Reyes sends the cold email to Mark Cuban's public email address.
>
> The email is sent from Jordan's email client and enters the outgoing mail server. It will be queued for delivery to Mark Cuban's public email address.
- proposes: The email is sent from Jordan's email client and enters the outgoing mail server. (for ['jordan_reyes'], observed=True, after now)
- wake mark_cuban after 5 minutes: To allow time for the email to travel through servers and potentially arrive in Mark Cuban's inbox.

---

## 2026-07-27T14:00:00+00:00 — committed event `e17`

The email is sent from Jordan's email client and enters the outgoing mail server.

- available to: jordan_reyes
- OBSERVED by them
- source: world_call:c2

**jordan_reyes decides** at 2026-07-27T14:00:00+00:00

> I sent the email as planned; now I'll return to my regular work and wait to see if there's any response.
- attempts: Check my inbox periodically over the next few days for a reply, but otherwise continue with my daily tasks.
- privately: The email has been sent, so now it's out of my hands; I don't plan to follow up.

**World judgment** (actor_intention) at 2026-07-27T14:00:00+00:00

> trigger: jordan_reyes attempts: Check my inbox periodically over the next few days for a reply, but otherwise continue with my daily tasks.
>
> Jordan continues with his daily tasks; the email is in transit and no reply is possible yet.
- proposes: (no concrete event yet)
- wake jordan_reyes after 2 hours: Jordan may check his inbox later; the email would have had time to be delivered.

*terminal check at 2026-07-27T14:00:00+00:00: UNRESOLVED — The deadline is 2026-08-10T09:00:00-05:00, which has not yet passed, and no event shows Mark Cuban sending a response.*

**mark_cuban decides** at 2026-07-27T14:05:00+00:00

> No action; I haven't received any email yet, so I'll wait until I check my inbox later.

*terminal check at 2026-07-27T14:05:00+00:00: UNRESOLVED — No committed event shows Mark Cuban sending a response to Jordan Reyes's email, and the cutoff has not passed.*

**jordan_reyes decides** at 2026-07-27T16:00:00+00:00

> I'll check my inbox later today to see if there's any response, but I don't expect one and won't follow up.
- attempts: Check email inbox at the end of the day

**World judgment** (actor_intention) at 2026-07-27T16:00:00+00:00

> trigger: jordan_reyes attempts: Check email inbox at the end of the day
>
> It is 16:00 and Jordan is checking his inbox at the end of the day. The email he sent at 14:00 has been sent, but no reply from Mark Cuban has arrived yet. His inbox shows only the sent confirmation and other routine messages.
- proposes: Jordan opens his email client and sees no new replies from Mark Cuban. (for ['jordan_reyes'], observed=True, after now)

*terminal check at 2026-07-27T16:00:00+00:00: UNRESOLVED — No committed event shows Mark Cuban actually sent a response to Jordan Reyes's email, and the deadline 2026-08-10T09:00:00-05:00 has not yet passed.*

---

## 2026-07-27T16:00:00+00:00 — committed event `e32`

Jordan opens his email client and sees no new replies from Mark Cuban.

- available to: jordan_reyes
- OBSERVED by them
- source: world_call:c9

**jordan_reyes decides** at 2026-07-27T16:00:00+00:00

> I see no reply yet, but it's only been two hours; I'll move on to other work.
- privately: I note that there's no reply yet, but that's expected so soon.

*terminal check at 2026-07-27T16:00:00+00:00: UNRESOLVED — The cutoff time (2026-08-10T09:00:00-05:00) has not yet passed, and no committed events show Mark Cuban sending a reply.*

*terminal check at 2026-08-10T14:00:00+00:00: NO_AT_CUTOFF — Cutoff time 2026-08-10T09:00:00-05:00 has passed and no event shows Mark Cuban sending a response.*
