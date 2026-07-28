# Causal Realism Review — six simulation runs

Independent review. I did not build this system. I read, for each run:
`compiled_scene.json`, `trajectory.md`, `world_judgments.jsonl`,
`world_exchanges.jsonl`, `journal.jsonl`, `event_queue.jsonl`, plus
`terminal_checks.jsonl`, `runtime_metrics.json` and the actor exchanges where
they were needed to establish what the world was actually looking at.

One question only: **does what happens actually follow from what came before?**

No scores, no rubric, no weights.

---

## VERDICTS

| Run | Verdict |
|---|---|
| `case1_cold_email` | **REVISE** |
| `case2_negotiation` | **FAIL** |
| `case3_group` | **FAIL** |
| `unseen1_confirm` | **PASS** |
| `unseen2_feedback` | **FAIL** |
| `unseen3_permission_slip` | **FAIL** |

---

## What the design gets right, stated first so the failures are read fairly

The world's system prompt is the best part of this system and it is worth
quoting, because most of the failures below are the runtime violating its own
stated rules rather than the rules being wrong:

> Keep these genuinely distinct.  Information can exist, then be sent, then
> arrive somewhere a person could see it, then actually reach their attention,
> then actually be read, then be understood.  Arriving is NOT noticing.
> Noticing is NOT reading.  People miss things, postpone them, skim them,
> forget them, and never get to them at all.

> IF NOTHING CONCRETE CHANGES, RETURN "event": null.  Never emit an event that
> merely restates that something is still sitting there, still unread, still
> waiting, or that someone is still busy -- that is not an event, it is the
> absence of one.

> Be realistic rather than convenient. [...] nothing should happen merely
> because it would move the situation along.

Where the runs honour this, the causality is genuinely good. `case1`'s Cuban
side is the strongest thing in the corpus: the email arrives, sits, gets
scanned-but-not-opened, gets opened three days later, and gets closed without a
reply. `unseen3` models notifications-off, a 6 a.m. email digest, an unheard
voicemail and a night shift as real attentional obstacles. Delay and
inattention are represented well and frequently.

**What is never represented anywhere** is the second half of realism. A regex
scan of all six committed-event journals for `spam|bounce|undeliver|fail|error|
wrong number|wrong address|crash|battery|outage|sick|cancel|misread|
misunderstood|typo` returns **zero hits in all six runs**. Across 191 committed
events there is not one bounced message, one message read wrong, one dead
battery, one wrong number, one thing that broke. Every message that is sent
arrives; every message that is read is understood exactly as intended. The only
failure mode this world has is *nobody got round to it*. That is one failure
mode out of many, and four of the six runs lean their entire outcome on it.

Related and structural: the world prompt says `ACTOR IDS YOU MAY USE`, and
across all six runs the world emitted **zero events originating from anyone
outside the declared cast**. Bristol Plumbing never confirms. Jordan's entire
professional network never replies to anything over three days. There is no
off-stage world at all — which silently biases every question whose realistic
dynamics depend on a party the compiler did not name.

---

# `case1_cold_email` — REVISE

Answer: `NO_AT_CUTOFF`. 60 steps, 19 committed events.

### Transition 1 — send → arrival

- **Triggering state:** starting event, `e11`, "Jordan Reyes sends the cold email to Mark Cuban's public email address."
- **World judgment (`c2`):** "The email is sent from Jordan's outbox and is now in transit to Mark Cuban's email server. It has not yet arrived in his inbox."
- **Committed:** `e21` (+30s, `observed:false`, for `mark_cuban`) "The email arrives in Mark Cuban's public email inbox."
- **Realistic:** yes. Arrival separated from noticing, correctly unobserved.
- **PASS**

### Transition 2 — arrival → "the email sits unread"

- **Triggering state:** `e21` has just arrived; 2 p.m. Monday.
- **World judgment (`c5`):** "Mark Cuban is a busy person who receives many emails. The email has just arrived in his inbox, but he has not yet looked at it."
- **Committed:** `e29` (`after: now`) "**The email sits unread in Mark Cuban's inbox.**"
- **Realistic:** no — not because the *situation* is wrong (it is right) but because **this is not an event**. It is the world's own definition of a non-event, committed to the permanent record:

  > Never emit an event that merely restates that something is still sitting there, still unread, still waiting

  The same thing happens again at `c13`, committing `e45` "The email **remains unread** in Mark Cuban's inbox as he attends to other high-priority messages."
- **Why it matters:** these two pseudo-events then re-enter the world's own context window as "WHAT HAS CONCRETELY HAPPENED SO FAR" (verified in the `c22` prompt), where they pad the record with three near-identical restatements of one fact. This is manufacturing stages that are not events.
- **More realistic alternative:** `"event": null` with the judgment carrying the same content and a wake for the next morning — exactly what `c7`, `c11`, `c12`, `c16` and `c21` correctly did in this same run.
- **REVISE**

### Transition 3 — the day-3 opening

- **Triggering state:** `e56` already records "Mark Cuban scans his inbox, sees the email from Jordan Reyes among others, but does not open it." Two more days pass.
- **World judgment (`c22`, quoted verbatim from `world_exchanges.jsonl`):** "Mark Cuban has already scanned his inbox and seen the email but did not open it. Another day has passed; **he is likely to have opened or deleted it by now.**"
- **Committed:** `e67` "Mark Cuban opens the email from Jordan Reyes and reads it."
- **Realistic:** marginal. The stated reason is a coin-flip disjunction ("opened *or* deleted") resolved to one branch with no situated ground offered for that branch — and the world's own instruction is "Attention is a concrete situated event, never a chance". A cold email that a busy recipient has already consciously skipped once is, in practice, far more likely never to be opened.
- **In its favour, and this is important:** the leap runs *against* the eventual answer. It manufactured the one opportunity a YES needed, and the YES still did not happen — `e80` "Mark Cuban closes the email from Jordan Reyes and moves to the next unread message." A world that manufactures whatever the situation needs does not do that. This is the clearest evidence in the corpus that the world is not outcome-steering.
- **REVISE** (thin reasoning, right instinct)

### Transition 4 — the Jordan tail, 6–10 August

- **Triggering state:** `e196` (2026-08-07T08:42) "Jordan finishes composing the message and sends it to his network." Sim clock at the next check: 2026-08-08T09:40 — **25 hours later**.
- **World judgment (`c72`, verbatim):** "**Jordan has just sent the message to his network a moment ago; it is too early for any replies to have arrived.** His inbox will show no new messages from that send."
- **Committed:** `e210` "Jordan opens his email inbox and sees no new replies to his network message."
- **Realistic:** no. The justification is a false statement about the record the world was looking at. The prompt for `c72` lists `[2026-08-07T08:42:48] (e196)` and `CURRENT TIME 2026-08-08T09:40:48`. Twenty-five hours is not "a moment ago".
- **Compounding:** the same zero-reply result then repeats at `e218`, `e228`, `e235` — a founder emails his own network asking for warm intros and receives **nothing at all from anybody over three days**. That is not "delay", it is the absence of an off-stage world (see structural note above). The world never once emits an inbound event, because no network contact is a declared actor.
- **More realistic alternative:** at minimum one reply within a day ("no one comes to mind, sorry"), or an out-of-office; at minimum a judgment that says *why* silence is the outcome given a day has passed.
- **REVISE** — materially unsupported, but outside the resolution's causal spine (the question is about Cuban), so it does not overturn the answer.

### Verdict — `case1_cold_email`: REVISE

The decisive chain — send → arrive → sit → scan → open → close without replying
→ no reply — is well supported at every step and produces the right answer for
the right reasons. Against it: two committed non-events the world's own rules
forbid, one thinly-reasoned opening, and a five-day tail whose central claim
("no replies") rests on a false statement about elapsed time and on a world that
structurally cannot produce an inbound message.

---

# `case2_negotiation` — FAIL

Answer: `YES`. 20 steps, 18 committed events, **entire negotiation resolved in
65 minutes of simulated time** against a 12-day deadline.

### Transition 1 — both parties notice, simultaneously, at the wake

- **Triggering state:** two `pending_progression` wakes both due at 2026-09-08T10:00:00, one hour after each message arrived.
- **World judgment (`c13`):** "Priya is at her workshop, likely checking her phone periodically. It's been an hour since the message arrived; **she may soon glance at her inbox.**"
- **Committed:** `e47` "Priya notices Dmitri's message offering the kiln for 1100 in her inbox." (`observed: true`)
- **World judgment (`c14`):** "Dmitri is likely checking his phone periodically. It is now 10:00, an hour after the email arrived. He may have other commitments but **the email is unread.**"
- **Committed:** `e57` "Dmitri notices the email from Priya in his inbox." (`observed: true`)
- **Realistic:** no, on two counts. First, **the judgments do not support the events they emit** — "may soon glance" is not glancing, and "the email is unread" is the world stating the opposite of what it then commits. Second, both parties come to attention at the identical second, which is the second the scheduler happened to pick. Compare `case1`, where the same machinery correctly answered "no" four times in a row before anyone noticed anything.
- **Exact supporting context:** at `c10` the world had established a live obstacle — "Dmitri's phone is in his pocket, but he is currently in the middle of unloading a delivery truck and won't check it for a few minutes" — and then never referenced it again. The obstacle it invented was discarded the moment attention was convenient.
- **More realistic alternative:** `"event": null` for at least one of the two, with the delivery-truck obstacle honoured; stagger the two attentions by hours, not zero seconds.
- **FAIL**

### Transition 2 — the same offer sent twice

- `e71` (10:00:02) "Dmitri sends an email to Priya stating he can come down to 1100 but not to 1150."
- `e94` (10:00:02, two seconds later) "Dmitri sends an email to Priya: '**I can do 1100, that's my final offer.** Let me know soon given your deadline.'"
- **World judgment (`c28`):** "Dmitri has just seen the notification of a new email from Priya and is now composing a reply."
- **Realistic:** no. Two separate 1100 counter-offers to the same person in the same instant. The world's rule — "Do not restate the record either. If what you are about to write is already there in different words, that step has HAPPENED — writing it again would make the same thing occur twice" — was violated exactly as described.
- **FAIL**

### Transition 3 — noticing something already read

- `e106` (10:05:05) "Dmitri **taps the notification and sees** the email from Priya offering 1050."
- `e117` (10:05:30) "Dmitri **notices the notification** of a new email from Priya (the 1050 offer) on his phone screen."
- **World judgment (`c39`):** "Dmitri has just finished reading Priya's 1050 offer and is likely to respond, but he may first check the new email notification that appeared on his phone screen."
- **Realistic:** no. He notices the arrival of a message he read 25 seconds earlier, and the world's own judgment says in the same breath that he has already finished reading it. Attention runs backwards.
- **FAIL**

### Transition 4 — the resolution itself

- **Triggering state:** `e125` (10:05:35) "Dmitri types and sends an email to Priya: '1050 works for me. Let's arrange pickup...'" — committed `observed: false`, for `priya_raghavan`.
- **Terminal judgment (`c44`), verbatim:** "Dmitri Sokolov sent an email to Priya Raghavan stating '1050 works for me', indicating agreement on price before the deadline, **though Priya has not yet observed it.**"
- **Resolution criterion, verbatim:** "Resolve YES only if the persistent event history shows that Priya Raghavan **and** Dmitri Sokolov **have agreed** on a price."
- **Realistic:** no. An agreement between two people is not constituted by one of them sending an unread email. The judge names the defect and resolves YES anyway. Everything this system does correctly elsewhere — arriving is not noticing, noticing is not reading — is discarded at the one moment it decides the answer. The run then stops immediately, at the exact instant that produces YES, before Priya can fail to see it, before the kiln is viewed, before pickup or payment can fall through.
- **More realistic alternative:** hold `UNRESOLVED` until Priya observes the acceptance; and continue the run — the deadline was 12 days out and a used-kiln sale involves at minimum a viewing and a handover.
- **FAIL**

### What did not happen, and should have

A 500-unit gap closed from first contact to acceptance in 65 minutes with no
viewing of the kiln, no question about condition or transport or payment, no
"let me think about it overnight", no one going quiet, no third party, no
counter-bidder. Dmitri's opening move (`c6`, 09:00:00) conceded 300 unprompted,
before he had even seen Priya's 1150. Nothing at any point delays, stalls or
fails. For a negotiation with twelve days of runway, the things that did not
happen are far less plausible than the things that did.

### Verdict — `case2_negotiation`: FAIL

Materially unsupported consequences (judgments that state the opposite of the
event they emit), duplicated stages, attention running backwards, and a YES
declared on a message the counterparty never received — announced, in the
judge's own words, as such.

---

# `case3_group` — FAIL

Answer: `NO_AT_CUTOFF`. 165 steps, 130 world calls, 71 committed events.

### Transition 1 — the opening claim

- **Triggering state:** starting event at 08:00 Tuesday, Ines posts to the group chat. Scene states Kwame "is away until Friday and may not be reachable until then"; Tomas is subsequently established as commuting.
- **World judgment (`c2`), verbatim:** "Ines has just sent the message; it is now in the group chat. **All housemates have seen it because they are all actively checking their phones at this moment.**"
- **Realistic:** no. The world asserts simultaneous universal attention — including from the housemate the scene declares unreachable — with no ground whatsoever, and this is the assertion that lets the whole situation start instantly. Two calls later (`c6`) Kwame, the away housemate, sends a reply within the same second, justified by "Kwame has mobile reception and is typing a reply in the group chat."
- **More realistic alternative:** the message posts; each housemate's attention is adjudicated separately, as the world's own arriving/noticing rule requires and as this same run does correctly for Tomas and Bea later.
- **FAIL**

### Transition 2 — direct contradiction of the record, five seconds apart

- **Triggering state:** 2026-10-06T20:55:50. Tomas's turn produced two mutually exclusive intentions, and the world honoured **both**.
- **World judgment (`c99`):** "Tomas has already seen and read Kwame's reply... He is about to open the chat." → `e313` (20:55:55) "Tomas **unlocks his phone and opens the group chat app**, which displays the conversation..."
- **World judgment (`c102`):** "Tomas has just seen the notification but chooses not to act on it, so he puts his phone away without opening the chat." → `e309` (20:55:50) "Tomas **puts his phone back in his pocket without opening the group chat**."
- **Realistic:** no. Committed in that order, Tomas puts the phone away without opening the chat and then, five seconds later, opens the chat. The world's instruction — "Do not contradict what is already in the record" — was violated by the world adjudicating one turn twice without consulting what it had just written.
- **FAIL**

### Transition 3 — the manufactured-non-event mass

This is the run's defining problem. A representative sample from `journal.jsonl`,
all permanently committed:

| Event | Description |
|---|---|
| `e206` | "**Ines's phone receives the notification of her own message** in the group chat, showing on the lock screen." |
| `e224` | "Ines notices the notification on her lock screen." |
| `e233` | "Ines opens the group chat app on her phone, which displays the conversation including her own latest message." |
| `e241` | "Ines sees the group chat conversation on her phone screen, with her own latest message displayed and no new messages from others." |
| `e185` | "Bea opens the calendar app on her phone to view her work schedule." |
| `e190` | "Bea's calendar app opens and displays her work schedule for the upcoming week." |
| `e238` | "Bea's phone screen dims and then turns off after a few seconds of inactivity, leaving the notification unseen." |
| `e446` | "Bea's phone screen remains dark; she has not yet checked it this morning." |
| `e575` | "The notification of Ines's reminder message appears on Bea's phone lock screen, but the phone remains untouched." |
| `e580` | "The notification of Ines's reminder message **stays on Bea's phone lock screen, unseen**." (same second as `e575`) |
| `e346`/`e351`/`e354` | Kwame unlocks and opens the group chat — **committed three times at 22:35:55**. |

- **World judgment for `e206` (`c66`):** "Ines's own message appears in the group chat on her device, but she is not currently looking at her phone; it sits as a notification on her lock screen."
- **Realistic:** no. Four of these — `e206`, `e224`, `e233`, `e241` — form a complete causal chain in which Ines is notified of her own message, notices it, opens the app, and sees her own message. Nothing happened. `e238`, `e446`, `e575`, `e580` are the world's own forbidden category verbatim ("still sitting there, still unread"). `e185`/`e190` and the Kwame triple are the world's other forbidden category verbatim ("Opening an application, a window appearing... a screen displaying what someone just asked it to display: none of these are events").
- **Effect on causality:** of 71 committed events, the large majority are phone mechanics. The chronology reads as a log of screen states, not a record of what happened between four people.
- **FAIL**

### Transition 4 — what never happened at all

Four housemates share one house at 14 Ferndale Road. Over four simulated days
and 130 world calls, **the world never once emits an event in which two of them
are in the same room.** Nobody passes anybody in the hall, nobody is in the
kitchen at the same time, nobody says a word out loud. Every interaction in the
entire run is mediated by a group chat, and the whole outcome is decided by
notifications going unseen.

The skipped stage is decisive: on 2026-10-08 Ines posts "I'm happy to host if
nobody else wants to, but please let me know". Kwame reads it (`e610`), Tomas
reads it (`e706`), and nobody ever answers a housemate who has volunteered.
Meanwhile the four of them are living in the same building.

- **More realistic alternative:** at least one co-presence event over four days — the world is explicitly authorised to decide circumstances, and "Tomas comes down and Ines is at the kitchen table" is exactly the kind of ordinary circumstance it is meant to supply. A group-chat thread dying is plausible; a shared house in which nobody meets for four days is not.
- **FAIL**

### Verdict — `case3_group`: FAIL

A direct contradiction of the record, a groundless universal-attention claim at
t0, dozens of committed non-events including a complete chain about a woman
being notified of her own message, one action committed three times in the same
second — and an entire co-habiting stage of the situation skipped, which is the
stage the answer turns on.

---

# `unseen1_confirm` — PASS

Answer: `YES`. 2 steps, 2 committed events, 3 world calls.

### Transition 1 — the message is already here

- **Triggering state:** starting event `e9`, "Bristol Plumbing's text message arrives on Sam Okonjo's phone", already `observed: true` per the scene.
- **World judgment (`c2`):** "The message has already arrived and been observed by Sam. No new event occurs."
- **Committed:** nothing (`"event": null`).
- **Realistic:** yes, and correctly restrained — the world declined to invent a stage where none existed.
- **PASS**

### Transition 2 — deferral, then action

- **Triggering state:** at 08:00 Sam decides "I need to reply to confirm the Thursday 8am slot, but it's only 8am now and the text says I have until 6pm. **I'll reply later when I have a moment**" — and produces no attempt. A code-scheduled recheck fires ten minutes later.
- **Actor at 08:10:** "I just saw the text arrived 10 minutes ago, so I'll reply now to avoid forgetting later."
- **World judgment (`c5`):** "Sam has his phone next to him and intends to reply. The reply is sent immediately."
- **Committed:** `e21` "Sam Okonjo sends the reply 'Yes, confirm Thursday 8am'."
- **Realistic:** yes. The one realistic risk in this situation — deferral — was generated, and then resolved by the person deciding to act, not by the world deciding for him. The world's contribution ("phone next to him, sent immediately") is exactly what the scene states. Given a highly motivated actor, a phone at hand, a one-text task and a ten-hour window, frictionlessness *is* the realistic base rate here. This is the correct place for nothing to go wrong.
- **PASS**

### Two notes that do not change the verdict

1. `c6` splits the send into "Sam sends the reply" and "The reply is transmitted from Sam Okonjo's phone to Bristol Plumbing's messaging system" — the world's own "machinery that simply works is ONE step, not several" applied to a text message. It was never committed (the run ended first), so it caused no harm.
2. `e21` is committed with `for: []` — available to no one. Bristol Plumbing is not a declared actor, so the confirmation goes nowhere and nothing on the other end ever acknowledges it. The resolution only requires that Sam *sent*, so this does not affect the answer — but it is the same structural blindness to off-stage parties seen in `case1`, and a run where the question had been "does the plumber turn up" would have had nowhere to go.

### Verdict — `unseen1_confirm`: PASS

Short, but every transition follows from what came before, the one plausible
obstacle was represented and then legitimately overcome by the actor, and the
world did not invent anything. The run is thin evidence, not bad evidence.

---

# `unseen2_feedback` — FAIL

Answer: `NO_AT_CUTOFF`. 48 steps, 23 committed events.

### Transition 1 — the week of legitimate delay

Monday: `e26` Aline notices Ravi's email; `e35` "Aline marks the email from Ravi
as unread and flags it for follow-up"; `c10` "Aline has flagged the email but is
now at her desk dealing with other urgent matters from the hiring committee."
Tuesday–Wednesday she works other students' drafts. Thursday she opens Ravi's
PDF. This is well modelled procrastination against real commitments, and it is
the best-supported stretch of the run. **PASS.**

### Transition 2 — reading, committed nine times

- **Triggering state:** Friday, deadline day, Aline reading the chapter.
- **Committed, verbatim, in order:** `e142` "begins reading"; `e147` "continues reading the first few pages"; `e155` "continues reading and annotating... making notes in the margins"; `e161` "continues... moving through several more pages"; `e169` "continues... progressing through the middle sections"; `e175` (**same second as `e169`**) "continues... working through the middle sections"; `e184` "continues... working through the remaining sections"; `e195` "**finishes** reading and annotating the **last section**"; `e198` "**continues** reading and annotating... progressing through the **remaining sections**"; `e203` "**finishes** reading the last page and closes the PDF".
- **World judgment for `e198` (`c68`):** "Aline is in the middle of reading Ravi's chapter, and the deadline is today. She will continue reading and annotating without interruption for the next hour or so."
- **Realistic:** no. She finishes the last section at 12:50, then at 12:55 continues through the remaining sections, then finishes again at 12:56. `e169` and `e175` are the same event at the same instant. This is one continuous activity sliced into nine near-identical committed records, two of them contradictory — again the world's own prohibition on restating the record, ignored nine times in a row.
- **More realistic alternative:** one event when she starts, one when she stops, `"event": null` in between with wakes. Also worth noting: "reading" is a person's choice, and the STOP RULE says the world should not be narrating it at all.
- **FAIL**

### Transition 3 — the decisive one: the run stops mid-sentence and answers NO

- **Triggering state:** 2026-07-31T13:50:08. She has just closed the PDF. Deadline is 17:00 +01:00 = **16:00 in sim time — two hours and ten minutes away.** Her committed private beliefs at this moment, from her own prompt: *"I realize I must finish reading and send comments today, even if it means working through lunch"*, *"I am committed to completing this chapter today, even if I have to skip lunch."* Her attempt: "I open my email and draft a reply to Ravi with my comments."
- **World judgment (`c74`):** "Aline has just finished reading the chapter and closed the PDF. She now opens her email to compose a reply with her comments." → `e211`, `"wakes": []`.
- **World judgment (`c75`), the last call of the run:** "Aline has just started composing a reply to Ravi. **She has finished reading his chapter and is now ready to write her comments.**" → `e216` "Aline is composing a reply email to Ravi Patel, **with the cursor blinking in the body of the email**", `"wakes": []`.
- **Committed:** `e216`. Then nothing. The queue was empty; Aline's code-side fallback recheck had widened to its 24-hour ceiling (visible in `event_queue.jsonl`: her fallback wakes go 12:10 → 12:30 → 13:10 → 14:30 → 17:10 → 22:30 → next-day, reaching daily by 07-31T10:00). The next recheck would have been 2026-08-01T13:50, past the cutoff, so none was scheduled, the loop broke, the clock advanced from 13:50 to 16:00 unsimulated, and the judge returned:

  > "Aline read Ravi's thesis chapter but never sent comments to Ravi; **the last event shows her composing a reply, but no event shows the email was sent**, and the deadline has passed."

- **Realistic:** **no, and this is the most serious finding in the corpus.** The answer to the question is produced by a backoff timer, not by anything in the situation. Nothing interrupted her. No meeting, no student at the door, no hiring committee, no laptop dying, no decision to sleep on it — the world was never asked, because it had twice returned no wake and the machinery had run out of reasons to look at her again. A person who has just spent three hours reading a chapter, has resolved four times to send comments that day, and has two hours left, does not simply cease to exist. The world's own final judgment says she "is now ready to write her comments."
- **The skipped stage is the one the question is about.** Writing and sending an email you have already resolved to send is the mundane, necessary, entirely ordinary stage between "composing" and "sent", and it was not adjudicated at all — it was timed out.
- **Compounding:** `e216` itself is pure forbidden mechanics ("the cursor blinking in the body of the email") and it consumed the run's last world call. And the design's own honesty rule was inverted here: the code comment at `trajectory.py` notes a truncated run "may not answer NO over time it never simulated" — this run was classed `cutoff` rather than truncated, and so answered NO over 130 minutes it never simulated.
- **More realistic alternative:** either the world emits a wake ("check whether she finishes the email before her 3 p.m. commitment"), or the world states a concrete interruption and commits it. Either produces a defensible answer. What is not defensible is silence.
- **FAIL**

### Transition 4 — the student who never chases

Ravi is woken seven times, takes no action every time, and is **never consulted
again after 2026-07-28T03:50** — Tuesday morning. From Tuesday to Friday, a
graduate student with a hard Friday deadline and no feedback never sends a
single "just checking in", and nothing in the world ever prompts him to. The
world emits no Ravi-side event after the opening send. A supervision
relationship where the student is silent for four days across a deadline is not
the plausible default; it is the convenient one, since any nudge from Ravi would
have re-entered Aline's attention.

- **REVISE** in isolation; part of the FAIL pattern in context.

### Verdict — `unseen2_feedback`: FAIL

The outcome is an artifact of the scheduler. Essential causality — finishing and
sending an email the actor had resolved to send, with two hours in hand — was
skipped rather than adjudicated, and the final committed event is a blinking
cursor.

---

# `unseen3_permission_slip` — FAIL

Answer: `NO_AT_CUTOFF`. 72 steps, 42 committed events. This is the most
ambitious run and has the best friction modelling in the corpus. It also has the
clearest instance of the world producing exactly what the outcome needed.

### Transition 1 — the reminders that legitimately miss

`e50`/`e72` Whitcomb's app messages land; `c14` "Chris has notifications off for
the school app, so he won't see the reminder until he opens the app"; `e78` they
sit unopened; `e116`/`e121` the 6 a.m. digest reaches Naomi's inbox while
`c36` correctly reasons "Naomi is asleep after her night shift". This is the
scene's stated attentional geometry honoured precisely. **PASS.**

### Transition 2 — Chris in two places at once

- **Triggering state:** Friday 06:07, Chris in the kitchen with the slip, issuing three intentions in one turn.
- **Committed sequence:** `e162` (06:07:00) "Chris picks up a pen from the counter and **starts filling out** the permission slip"; `e170` (06:07:10) "Chris **sets the permission slip down on the counter and walks to the drawer** where he keeps his wallet and checkbook"; `e175` (06:07:10) "Chris sees the checkbook and wallet in the drawer"; `e178` (06:07:30) "Chris **finishes writing Ezra's name and signing his own signature on the permission slip**"; `e183` (06:07:30) "Chris pulls out the checkbook and opens it to write a check."
- **World judgment for `e178` (`c52`):** "Chris is in the kitchen, filling out the permission slip. He has just started writing, so the slip is not yet completely filled out or signed."
- **Realistic:** no. He signs the slip at the counter at the same second he is at the drawer pulling out the checkbook, having already put the slip down and walked away twenty seconds earlier. The world adjudicated the three intentions independently and never reconciled them against each other.
- **REVISE** on its own; it becomes material in Transition 5.

### Transition 3 — the world enumerates the options and omits the one that matters

- **Triggering state:** Chris has the slip, has read the 3 p.m. deadline, and attempts: "I plan to drop it off at the school office before the 3pm deadline, either on my way to work or ask Naomi to take it."
- **World judgment (`c51`), verbatim:** "Chris intends to take the permission slip to the school office, but it's currently 6:07 AM and he would need to leave for work by around 6:45 AM to arrive by 7 AM. The school office opens at 8 AM, so dropping it off on the way to work is not possible. He could ask Naomi, but she is driving home and not available right now."
- **Committed:** `e167` "Chris looks at the clock and **realizes** the school office won't be open for another two hours, so he cannot drop it off immediately. He **considers** asking Naomi but she is not home yet."
- **Realistic:** no, on two counts.
  1. The event narrates Chris's interior — "realizes", "considers" — which the world is explicitly forbidden from doing ("an event says what visibly happened, not what someone privately thinks, plans, feels"; "Never write that someone... decides").
  2. More seriously, it enumerates the delivery routes as exactly two and silently drops the third. The resolution criterion names both: *"either dropped off by a parent **or sent in with Ezra**."* Chris is standing in the kitchen at 6:07 a.m. with a signed permission slip, and his nine-year-old son — who attends that school, who is going there in under two hours, and whose backpack the slip came out of the previous night — is asleep down the hall. Putting the form in the kid's backpack is *the* ordinary thing a parent does, and it is the single most likely path to YES. It is never surfaced, never attempted, never refused. The world closed the option by not listing it.
- **More realistic alternative:** the world states the circumstances (office opens at 8, he leaves at 6:45, Ezra leaves for school at ~7:30) and **stops**, per the STOP RULE, leaving the choice to Chris.
- **FAIL**

### Transition 4 — Ezra does not exist

- **Triggering state:** Ezra is a declared actor with a full private context (he wants to go, Dev told him the cabins have spiders, the slip is in his backpack).
- **What happened:** Ezra is woken four times — 09-17 13:45, 15:45, 15:55, and 09-18 14:25 — and takes **no action every time**. He observes exactly one event in the entire run, the starting event. The world emits **zero** events for Ezra after `e15`. He is never depicted waking up, leaving for school, arriving at school, or coming home. Friday, the deadline day, passes with no child in it.
- **Realistic:** no. Between `e238` (06:59:30, Chris's voicemail) and `e255` (14:25, Whitcomb) **7.5 hours of the deadline day contain no events at all** — the entire school day, the school run, Chris's departure for work, and the 3 p.m. deadline itself. The bus and cabin count going final at 3 p.m., Whitcomb noticing Ezra's form never arrived, the office closing — none of it occurs.
- **This is skipped essential causality.** The question is whether a form gets from a kitchen counter to a school office. The simulation never once puts the form near the child who travels between those two places daily.
- **FAIL**

### Transition 5 — the ten-hour drive, and the deletion of the one path to YES

- **Triggering state:** Naomi's scene context: night shifts Thursday–Saturday, 7 p.m. to 7:30 a.m.; "she will be asleep most of Friday from about 8 a.m. until late afternoon."
- **World judgment (`c43`), at sim time 06:05 Friday:** "Naomi typically checks her email around 6 AM when the digest arrives, but **she just finished a night shift at 7:30 AM** and is likely heading home to sleep." → `e144` "Naomi's phone receives the email digest notification, but **she is driving home from work** and does not look at her phone."
- **World judgment (`c92`), at sim time 16:00:** "**Naomi arrives home around 8 a.m.**, tired after her night shift. She will likely check her phone briefly before going to sleep, but may not have the energy to read through all messages." → `e273` (16:02) "**Naomi parks the car, turns off the engine, and picks up her phone.** She sees the email digest notification and the voicemail notification, but does not open either yet."
- **Realistic:** no, and this is the run's decisive corruption.
  - At 06:05 she is put in the car although her shift runs to 07:30 — the world states a future time ("just finished... at 7:30 AM") as though it were past.
  - She then remains in that car until 16:02. **A ten-hour commute.**
  - The world's own judgment for the parking event says she arrives home *around 8 a.m.* and *will likely check her phone briefly before going to sleep*. The event it emits places that arrival at **4 p.m.**
  - **The gap is exactly what the NO required.** Had the world committed what its own judgment says — home at 8 a.m., glances at the phone before bed — she would have heard Chris's voicemail with **seven hours** to spare, a car, and a school office open until 3. That is the one live path to YES in the entire run, and it was removed by an event that contradicts the reasoning printed directly above it.
  - The stage that was skipped is entirely mundane: arriving home, going to bed, waking in the late afternoon. Instead the world merged "arrives home" and "wakes up" into one parking event eight hours out of place.
- **More realistic alternative:** commit the arrival at ~08:00 with the phone glance the judgment describes, then let Naomi decide. A tired night-shift nurse plausibly does not act on it — but that has to be *her* failure, adjudicated, not a ten-hour drive.
- **FAIL**

### Transition 6 — a check that was never written, and a clock that is wrong

- `e183` (06:07:30) is the last event mentioning the payment: "Chris **pulls out the checkbook and opens it to write a check for $85.**" **No event ever records a check being written.**
- Yet `e233` (06:59:30) commits Chris's voicemail saying "the permission slip **and check** are on the kitchen counter";
- and the run's final answer states: "the committed events show that the permission slip was signed **and a check written** but never delivered to the school office."
- `c109`'s judgment leaks the model's own uncertainty straight into the record: "The permission slip and check are on the kitchen counter, unsigned and unpaid? **Actually** Chris signed the slip and wrote a check earlier, so those are ready but not delivered."
- And the event that judgment produced, `e320`, commits: "Naomi looks at the time display on her phone and sees it is **4:44 p.m.**" — at sim time **18:04:00**, i.e. 6:04 p.m. The committed clock reading is 80 minutes stale (it is the time of `e303`, two events earlier). A clock is the one object in a simulation that cannot be wrong.
- Separately, the terminal check at `c122` (sim time 20:44) states: "The deadline of 3 p.m. Friday, September 18, 2026 **has not yet passed** (current time is 20:44:10)".
- **Realistic:** no. A physical artifact central to the resolution exists only inside the narration of other events and in the final answer, never as a committed fact; and the run's own time bookkeeping contradicts itself three separate ways.
- **FAIL**

### Transition 7 — a phone that rings for twenty minutes

- `e210` (06:37:00) "Chris's phone dials Naomi's number and begins to ring."
- `e220` (06:57:30) "**The call rings several times then goes to voicemail.** Chris hears the voicemail greeting."
- `e225` (06:57:30) "The voicemail greeting plays, then the beep sounds, indicating Chris can leave a message."
- **World judgment (`c73`):** "Chris's phone rings Naomi's number. She is driving home from work and cannot answer safely. The call goes to voicemail."
- **Realistic:** no. Twenty minutes and thirty seconds of ringing before voicemail; phones divert in about thirty seconds. The reason is right, the duration is impossible, and `e220`/`e225` split one automatic mechanism into two committed steps.
- **REVISE**

### Verdict — `unseen3_permission_slip`: FAIL

The best friction modelling in the corpus, undone by: a whole actor and a whole
school day skipped on the deadline day; the world enumerating the delivery
routes and omitting the one the resolution names; and a pivotal event that
contradicts its own stated judgment by eight hours in exactly the direction the
NO required.

---

## Cross-cutting findings

**1. The world violates its own best rules, and nothing checks it.** Every
failure above is already prohibited in the system prompt: don't restate the
record, don't contradict the record, don't narrate mechanics, don't narrate
decisions, return `null` when nothing changes. Nothing in the runtime compares a
proposed event against what is already committed, so `case2` sends the same
offer twice, `case3` commits one action three times in one second, `unseen2`
finishes reading twice, and `unseen3` has Chris signing at the counter while
standing at the drawer.

**2. Judgments routinely fail to support the events they license.** `case2`
`c14` — "the email is unread" → *commits noticing*. `case2` `c13` — "she may soon
glance" → *commits glancing*. `unseen3` `c92` — "arrives home around 8 a.m." →
*commits parking at 4 p.m.* `case1` `c72` — "just sent... a moment ago" *when the
record in front of it says 25 hours*. The judgment field looks like reasoning but
is not load-bearing on the event.

**3. Only inattention can go wrong.** Zero adverse events across all six
journals: no bounce, no spam folder, no misread message, no wrong number, no
dead battery, no illness, no cancellation. Four of six runs hang their entire
answer on somebody not getting round to something. A world with exactly one
failure mode is not a realistic world, it is a single mechanism.

**4. Nothing exists outside the declared cast.** The world may only name the
actor ids it is given, and in practice it never emits an event caused by anyone
else. Bristol Plumbing never confirms; Jordan's whole network is silent for
three days; there are no colleagues, no neighbours, no school office. Any
question whose realistic dynamics run through an unmodelled third party gets
silence by construction, and silence is read as evidence.

**5. Scheduler artifacts reach the answer.** `unseen2` returns NO because a
per-actor backoff hit 24 hours while a woman was mid-email with two hours to
spare. `case2` returns YES because the run stopped at the instant an acceptance
was sent and before it was received. In both cases the machinery, not the
situation, decided.

**6. Where the design works, it works well, and it is not outcome-steering.**
`case1`'s `c22` manufactured the opening a YES needed and the YES still did not
happen. `unseen1` let its actor defer and then act on his own. `unseen3` modelled
notifications-off, a digest, and an unheard voicemail with real care. The failures
above are execution failures against a good design, not evidence that the world
is writing toward a predetermined answer — except in `unseen3` Transition 5,
which is the one place I could not explain the divergence any other way.

---

## Summary of the most serious findings

1. **`unseen2_feedback`** — the answer is a timer artifact. Last committed event:
   *"Aline is composing a reply email to Ravi Patel, with the cursor blinking in
   the body of the email."* World's own final judgment: *"She has finished
   reading his chapter and is now ready to write her comments."* Both final world
   calls returned `"wakes": []`; the clock jumped 130 unsimulated minutes to the
   cutoff and answered *"no event shows the email was sent."*

2. **`unseen3_permission_slip`** — the pivot contradicts its own reasoning by
   eight hours, in the direction the outcome needed. Judgment: *"Naomi arrives
   home around 8 a.m. ... She will likely check her phone briefly before going to
   sleep."* Event committed at 16:02: *"Naomi parks the car, turns off the
   engine, and picks up her phone."*

3. **`unseen3_permission_slip`** — the child is never in the simulation. Ezra is
   woken four times, acts zero times, and receives zero events after the opening.
   The world's `e167` lists the delivery options as *"he cannot drop it off
   immediately. He considers asking Naomi"* — omitting the route the resolution
   names, *"or sent in with Ezra"*.

4. **`case2_negotiation`** — YES declared on an unreceived message, by a judge
   that says so: *"indicating agreement on price before the deadline, though
   Priya has not yet observed it."*

5. **`case3_group`** — the record contradicted five seconds apart: `e309`
   *"Tomas puts his phone back in his pocket without opening the group chat"*
   followed by `e313` *"Tomas unlocks his phone and opens the group chat app"*;
   and four housemates who share a house never meet in person across four days
   and 130 world calls.

6. **`case1_cold_email`** — *"Jordan has just sent the message to his network a
   moment ago; it is too early for any replies to have arrived"*, written 25
   hours after the send, in front of a record that shows the send timestamp.
