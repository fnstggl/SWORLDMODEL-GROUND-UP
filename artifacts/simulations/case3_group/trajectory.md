# Trajectory
**Question:** Will the four housemates at 14 Ferndale Road settle on who hosts the shared birthday dinner before the weekend? Ines raised it in the group chat this morning; Kwame is away until Friday, Tomas hates hosting, and Bea has the biggest kitchen but works nights.
**Result:** cutoff — NO_AT_CUTOFF

*terminal check at 2026-10-06T08:00:00+00:00: UNRESOLVED — No event shows the four housemates collectively agreeing on a host; the only event is a question, not an agreement.*

**World judgment** (starting_event) at 2026-10-06T08:00:00+00:00

> trigger: Ines sends a message in the group chat about the shared birthday dinner, asking who will host.
>
> The message has already been sent and observed by all housemates. No immediate concrete change occurs as a result of the same trigger.
- proposes: (no concrete event yet)

**ines decides** at 2026-10-06T08:00:00+00:00

> I need to read Ines's message properly before responding. I'll check the group chat.
- attempts: I open the group chat and read Ines's message about the shared birthday dinner.
- privately: I now know Ines is asking who will host the shared birthday dinner. I wonder if I could host, but I need to check my availability.

**World judgment** (actor_intention) at 2026-10-06T08:00:00+00:00

> trigger: ines attempts: I open the group chat and read Ines's message about the shared birthday dinner.
>
> Ines's message is already observed by all, so there is nothing new to read. The group chat is already up to date.
- proposes: (no concrete event yet)

**kwame decides** at 2026-10-06T08:00:00+00:00

> I'm away until Friday and can't host, so I'll reply to Ines's message to clarify my situation and step back.
- attempts: I send a message in the group chat: 'Hey everyone, I'm away until Friday and won't be able to host. Happy for someone else to take it on. Let me know if you need anything from me.'
- privately: I've clarified that I'm unavailable to host, so the decision is up to the others.

**World judgment** (actor_intention) at 2026-10-06T08:00:00+00:00

> trigger: kwame attempts: I send a message in the group chat: 'Hey everyone, I'm away until Friday and won't be able to host. Happy for someone else to take it on. Let me know if you need anything from me.'
>
> Kwame's message is composed and sent. The group chat receives the message, making it available to all members.
- proposes: Kwame sends a message in the group chat: 'Hey everyone, I'm away until Friday and won't be able to host. Happy for someone else to take it on. Let me know if you need anything from me.' (for ['bea', 'ines', 'kwame', 'tomas'], observed=False, after now)

**tomas decides** at 2026-10-06T08:00:00+00:00

> I'm not going to volunteer to host because I hate hosting. I'll wait to see if someone else offers.
- privately: Ines asked about hosting for the birthday dinner; I hope someone else volunteers so I don't have to.

**bea decides** at 2026-10-06T08:00:00+00:00

> I'll wait and see what others say before offering my kitchen, since I work nights and need to check my schedule.
- privately: I remember Ines asked about hosting; I'll check my work schedule for the weekend before committing to anything.

---

## 2026-10-06T08:00:00+00:00 — committed event `e30`

Kwame sends a message in the group chat: 'Hey everyone, I'm away until Friday and won't be able to host. Happy for someone else to take it on. Let me know if you need anything from me.'

- available to: bea, ines, kwame, tomas
- AVAILABLE but NOT observed
- source: world_call:c6

**World judgment** (event_consequence) at 2026-10-06T08:00:00+00:00

> trigger: Kwame sends a message in the group chat: 'Hey everyone, I'm away until Friday and won't be able to host. Happy for someone else to take it on. Let me know if you need anything from me.'
>
> The message is in the group chat, visible to all. Bea is at home and her phone is nearby, so she will check the chat soon.
- proposes: Bea notices the new message from Kwame in the group chat. (for ['bea'], observed=True, after 2 minutes)

*terminal check at 2026-10-06T08:00:00+00:00: UNRESOLVED — No committed event shows the four housemates collectively agreeing on a host, and the deadline has not passed.*

---

## 2026-10-06T08:02:00+00:00 — committed event `e35`

Bea notices the new message from Kwame in the group chat.

- available to: bea
- OBSERVED by them
- source: world_call:c9

**bea decides** at 2026-10-06T08:02:00+00:00

> I'm checking my work schedule for the weekend before responding, since I work nights.
- attempts: Open my phone calendar to check my work schedule for Friday night through Sunday morning.
- privately: I need to confirm my availability before offering to host.

**World judgment** (actor_intention) at 2026-10-06T08:02:00+00:00

> trigger: bea attempts: Open my phone calendar to check my work schedule for Friday night through Sunday morning.
>
> Bea has just noticed Kwame's message; she now acts on her intention to check her calendar. She pulls out her phone and opens the calendar app.
- proposes: Bea opens her phone calendar to view her work schedule. (for ['bea'], observed=True, after now)

*terminal check at 2026-10-06T08:02:00+00:00: UNRESOLVED — No committed event shows that the four housemates have collectively agreed on a host; only messages have been sent but no agreement reached.*

---

## 2026-10-06T08:02:00+00:00 — committed event `e43`

Bea opens her phone calendar to view her work schedule.

- available to: bea
- OBSERVED by them
- source: world_call:c12

**bea decides** at 2026-10-06T08:02:00+00:00

> Checking my work schedule to see if I'm free to host the dinner on Saturday.
- attempts: I look at my calendar for Saturday 2026-10-10 and Sunday 2026-10-11 to see if I have any shifts or commitments.
- privately: I am considering hosting if I'm free, but I need to confirm my schedule first.

**World judgment** (actor_intention) at 2026-10-06T08:02:00+00:00

> trigger: bea attempts: I look at my calendar for Saturday 2026-10-10 and Sunday 2026-10-11 to see if I have any shifts or commitments.
>
> Bea is already looking at her calendar on her phone, so she can immediately see her schedule for the requested days.
- proposes: Bea sees her calendar for Saturday 2026-10-10 and Sunday 2026-10-11 on her phone. (for ['bea'], observed=True, after now)

*terminal check at 2026-10-06T08:02:00+00:00: UNRESOLVED — No event shows that the four housemates have collectively agreed on a host; only initial messages and Bea's actions have occurred.*

---

## 2026-10-06T08:02:00+00:00 — committed event `e50`

Bea sees her calendar for Saturday 2026-10-10 and Sunday 2026-10-11 on her phone.

- available to: bea
- OBSERVED by them
- source: world_call:c15

**bea decides** at 2026-10-06T08:02:00+00:00

> I'm checking my calendar to see if I'm free to host the birthday dinner this weekend.
- attempts: I look at my calendar for Saturday 2026-10-10 and Sunday 2026-10-11 to see my work schedule.

**World judgment** (actor_intention) at 2026-10-06T08:02:00+00:00

> trigger: bea attempts: I look at my calendar for Saturday 2026-10-10 and Sunday 2026-10-11 to see my work schedule.
>
> Bea is already looking at her calendar on her phone, so the next concrete step is that she sees the entries for those days.
- proposes: Bea sees her calendar for Saturday 2026-10-10 and Sunday 2026-10-11 on her phone. (for ['bea'], observed=True, after now)

*terminal check at 2026-10-06T08:02:00+00:00: UNRESOLVED — No event shows that all four housemates have collectively agreed on a host; only Kwame declined and Bea checked her schedule.*

---

## 2026-10-06T08:02:00+00:00 — committed event `e56`

Bea sees her calendar for Saturday 2026-10-10 and Sunday 2026-10-11 on her phone.

- available to: bea
- OBSERVED by them
- source: world_call:c18

**bea decides** at 2026-10-06T08:02:00+00:00

> I'm checking my calendar to see if I'm free on the weekend to potentially host.
- attempts: I look at my calendar for Saturday 10th and Sunday 11th October to check my work shifts.
- privately: I now know my work schedule for that weekend.

**World judgment** (actor_intention) at 2026-10-06T08:02:00+00:00

> trigger: bea attempts: I look at my calendar for Saturday 10th and Sunday 11th October to check my work shifts.
>
> Bea has already seen her calendar for those dates in the previous event; nothing new happens.
- proposes: (no concrete event yet)

*terminal check at 2026-10-06T08:02:00+00:00: UNRESOLVED — No committed event shows that all four housemates have collectively agreed on a host; only inquiries and personal observations have occurred, and the deadline has not passed.*

*terminal check at 2026-10-10T20:00:00+00:00: NO_AT_CUTOFF — The deadline 2026-10-10T00:00:00+00:00 has passed and no committed event shows that the four housemates collectively agreed on a host.*
