# QUALITY REVIEW — ACTOR REALISM

**Reviewer:** independent. I did not build this system.
**Question judged:** do the PEOPLE behave like real people? Nothing else.
**Sources read per run:** `compiled_scene.json`, `trajectory.md`, `actor_exchanges.jsonl` (prompt + raw response for every actor call), `actor_memory_updates.jsonl`, `journal.jsonl`.
**Method:** every material transition is quoted with the actor's exact situation, exactly what they had observed at that instant, their exact decision, and the verdict. No scores, no rubric.

---

## VERDICTS

| Run | Verdict | One-line reason |
|---|---|---|
| `case1_cold_email` | **FAIL** | Mark Cuban names "Jordan's email" while his own briefing says he has observed nothing; both actors are the same generic busy professional. |
| `case2_negotiation` | **FAIL** | Dmitri sends the identical counteroffer twice in 2 seconds and accepts the same offer twice in 25 seconds while his own memory says he already accepted; Priya bids against herself and volunteers her deadline. |
| `case3_group` | **FAIL** | Ines addresses herself in the third person; Tomas's memory contradicts his own observation of five minutes earlier; Kwame says "I still can't host" on Saturday having been away only "until Friday"; Bea is silent for five days. |
| `unseen1_confirm` | **REVISE** | One actor, ten minutes of elapsed behaviour. Nothing egregious, but he reverses a stated plan with zero new stimulus and treats a text he had already read and planned around as fresh news. Establishes nothing about realism. |
| `unseen2_feedback` | **FAIL** | Aline never once acts on or mentions the hiring committee or her Tue/Thu teaching — her only distinguishing constraints; four near-duplicate "I may skip lunch" memories in under two hours; Ravi forms a plan to chase on Wednesday and simply vanishes for four days. |
| `unseen3_permission_slip` | **FAIL** | Ezra's behaviour inverts his own private context; Chris never once considers sending the form in with the nine-year-old living in his house; Naomi observes the trip and the deadline on Thursday afternoon, forms no memory and does nothing. |

Best-drawn people in the corpus, in order: **Ezra** and **Chris** (`unseen3`), **Tomas** (`case3`). Worst: **Mark Cuban** (`case1`) and **Bea** (`case3`), both of whom are functionally furniture.

---

## CROSS-CUTTING FINDINGS

These recur across runs and cause most of the individual failures below.

**1. Every actor in every run shares one identical system prompt.** Verified by hashing: all 127 actor calls across all six runs use system prompt `fff8610b`. The only thing distinguishing Mark Cuban from Jordan Reyes, or Bea from Tomas, is a one-to-two-sentence `private_context` blurb plus an observation list. There is no separate voice, register, verbosity, competence or temperament channel. This is the mechanism behind the interchangeability findings below — the people are one model wearing name tags, and the name tag is a single sentence long.

**2. Actors cannot see what they themselves just did.** "WHAT YOU HAVE OBSERVED" contains world events, not the actor's own committed actions. Consequences: Dmitri re-sends an identical counteroffer 2 seconds later (`case2` c18 → c26) and re-accepts an offer 25 seconds later (c36 → c40); Tomas opens the chat and puts his phone away without opening the chat in the same second (`case3` c98 / c101). Real people have working memory of their own last action.

**3. Actors are shown their own outbound messages as inbound notifications.** `case3` e206: "Ines's phone receives the notification of *her own message* in the group chat, showing on the lock screen"; e617 the same for her reminder. Ines then acts on them (c75, c203). Phones do not notify you of your own messages.

**4. Message content is preserved in one run and stripped in another.** `case2` renders content verbatim ("Priya sends an email to Dmitri: 'Thanks for coming down. I can do 1050…'"). `case3` renders every chat message as content-free ("Ines sends a message in the group chat sharing her thoughts on who should host"). In `case3` this is decisive — see the Kwame/Tomas findings.

**5. Memory accretes near-duplicate restatements.** Mark Cuban forms four memories that all say "I read it, I haven't decided" (`case1`). Aline forms four in under two hours that all say "I must finish today, even if I skip lunch" (`unseen2`). Jordan forms two pairs that differ only by a synonym. These are not the kind of thing a person takes away; they are a loop being faithfully logged.

**6. Pivotal human decisions are authored by the world, not by the person.** In `unseen3`, the single most consequential beat — Chris finding the permission slip on Thursday night and putting it down unread — is committed as world events e98/e105 with **no actor call between 21:55 Thursday and 06:04 Friday**. The world also narrates "He considers asking Naomi but she is not home yet" (e167) as an event. Chris was never asked. Whatever realism that beat has is the narrator's, not the character's.

---

## RUN 1 — `case1_cold_email` — **FAIL**

**Cast.** Jordan Reyes: "founder of a bootstrapped sports-analytics startup… He plans to send it today and **does not intend to follow up**." Mark Cuban: "billionaire investor… receives many cold emails and may respond to those that catch his interest, but his response behavior is unpredictable."

### 1.1 Cuban acts on knowledge he does not possess — **FAIL**

**Triggering state.** Call `c17`, 2026-07-28T14:00:30. Cuban's briefing reads, verbatim:

```
WHAT YOU HAVE OBSERVED
- (you have not observed anything yet)

YOUR PRIVATE MEMORIES, BELIEFS, AND PLANS
- (none yet)
```

**Decision.** `"I am checking my email inbox as part of my daily routine. I have not yet seen Jordan's email."`

**Realistic?** No. He names the sender of an email he has not observed arriving, has not opened, and has no memory of. He knows *that a specific person called Jordan sent him something*, before any in-world event delivered it.

**Where it came from.** The SHARED CONTEXT block handed to Cuban states: *"Jordan Reyes has a short cold email drafted. He has Mark Cuban's public email address. The email asks for a 15-minute call and references Cuban's Cost Plus Drugs pricing playbook. Jordan will send the email today."* That is Jordan's private intent, given to the recipient as ambient fact. Whatever the intent of `shared_context`, the actor consumed it as knowledge and spoke from it.

**More realistic alternative.** Cuban's shared context should have contained nothing about Jordan; his first line should have been "Clearing the inbox" with no name in it, and the name should only have entered his vocabulary at e67 ("Mark Cuban opens the email from Jordan Reyes and reads it").

**Verdict: FAIL.** This alone fails the run under the stated criterion.

### 1.2 Cuban deliberates over one cold email eleven separate times — **FAIL**

**Triggering state.** From 2026-07-30 through 2026-08-08, Cuban is woken repeatedly. His observation list never changes after e80.

**Decisions, in sequence:**
- 07-31 14:00 — "I'm busy and the email didn't stand out enough to warrant a reply now. I'll leave it for later."
- 07-31 14:10 — "I'm considering whether to respond to Jordan Reyes's email, but I'm busy and not convinced yet."
- 07-31 14:30 — "I'm considering whether to reply to Jordan Reyes, but I have many other priorities…"
- 07-31 15:10 — "I am busy with other priorities and the email from Jordan Reyes is not urgent…"
- 07-31 16:30 — "I have a lot on my plate, and this cold email isn't urgent."
- 07-31 19:10 — "I have a busy schedule and many emails; this one isn't urgent."
- 08-01 00:30 — "I have too many other priorities and the email didn't stand out enough…"
- 08-01 21:50, 08-03 05:50, 08-05 08:30, 08-08 09:40 — four more of the same.

Four of those turns also deposit a memory, and the four memories are the same fact re-worded:
`"I now know that Jordan Reyes reached out about a 15-minute call…"` → `"I remember the email from Jordan Reyes about Cost Plus Drugs pricing playbook, but I haven't decided to reply."` → `"I recall the email from Jordan Reyes… but I haven't decided to reply and it's not a high priority."` → `"I have read the email but it's not a priority for me to reply."`

**Realistic?** No. A man who receives hundreds of cold emails does not revisit one of them six times in a single afternoon and then five more times over the following week, each time re-deciding not to reply and each time re-filing the same note. He archives it, deletes it, forwards it to an assistant, or fires off one line — the real Cuban's documented behaviour is a one-line reply from his phone. The trace has him doing the one thing a high-volume inbox owner never does: hold a single low-priority item in active working memory for twelve days.

**More realistic alternative.** One turn at e67: read, then either `"no thanks"` sent in nine seconds, or delete/archive with the memory `"deleted"` and never think of it again. The run should have had one Cuban decision, not eleven.

**Verdict: FAIL.**

### 1.3 Cuban and Jordan are the same person — **FAIL (interchangeability)**

Put the lines side by side with the names removed:

- "I'm busy with other priorities and don't see an immediate need to engage."
- "I'm not expecting a reply given it's a cold email to a busy person, so I'm moving on to other work."

Nothing identifies which is the billionaire and which is the bootstrapped founder. Cuban says exactly one Cuban-specific thing in the entire run ("The email is short and to the point, referencing Cost Plus Drugs") and nothing else that could not be said by a mid-level operations manager. He never uses a number, never mentions Shark Tank, a portfolio, a deal, an assistant, a screen, or a filter. Swap the name tags and the transcript reads identically.

**Verdict: FAIL.**

### 1.4 Jordan's arc — **PASS, with one reservation**

**Triggering state.** 08-06 08:30. Jordan has observed e129, e152, e168 — three separate "sees no reply from Mark Cuban in his inbox."

**Decision.** `"I'm moving on from the Cuban attempt; no reply after 10 days confirms it's a dead end."` → archives the thread → pivots to asking his network for warm intros → after three days of no replies to that, follows up with his three most promising contacts individually.

**Realistic? Yes.** This is the one well-behaved actor in the run. He honours "does not intend to follow up" for the whole fifteen days — he checks his inbox obsessively but never emails Cuban again, which is exactly the shape of that stated commitment. The pivot to warm intros with a generalised lesson is what a bootstrapped founder actually does. Grounded throughout: every "no reply" claim traces to an observed event (e129, e152, e168, e210, e218, e228, e235).

**Reservation.** Two memory pairs are the same sentence twice: `"I accept that the email likely went unread or was ignored"` (08-01) / `"I accept that the email was likely ignored or not read"` (08-02); and `"I'm now convinced that cold emailing high-profile figures without a warm introduction is unlikely to work…"` (08-06) / `"I now believe that cold emailing high-profile figures without a warm introduction is unlikely to work…"` (08-07) — identical but for one verb. People do not form the same conclusion twice in 24 hours.

**Verdict: PASS on conduct, REVISE on memory formation.**

---

## RUN 2 — `case2_negotiation` — **FAIL**

**Cast.** Priya: buyer, offered 900, "would rather close than keep looking… lease renews on the 20th, and she needs the kiln before then." Dmitri: seller, asking 1400, "would rather close than keep looking." Twelve days of runway.

### 2.1 Priya's opening move gives away the entire negotiation — **REVISE**

**Triggering state.** 09-08T09:00. Her only observation: "Priya and Dmitri are aware of each other's initial price positions (Priya offered 900, Dmitri asks 1400). No agreement has been reached yet." No counter from Dmitri. No time pressure has materialised — the deadline is twelve days out.

**Decision.** `"Send Dmitri a message proposing to meet halfway at 1150, emphasizing the deadline and my need to close soon."`

**Realistic?** No, on two counts. She jumps 250 unprompted, before the seller has moved at all — bidding against herself on turn one. And she volunteers to the seller the two facts that destroy her leverage: that she has a deadline and that she needs to close. Dmitri banks it immediately: his very next memory is `"I note that Priya is eager to close, which might give me some leverage."` The trace itself records the damage.

**More realistic alternative.** Hold at 900 and ask a question — condition, firing hours, element age, whether it's three-phase, collection. Or nudge to 950–1000 with no mention of any deadline. Twelve days is not urgency.

**Verdict: REVISE.** It is a possible human blunder, but it is the blunder of someone with no interests, made instantly and without hesitation.

### 2.2 Priya counters at 1050 while her own 1150 offer is outstanding — **FAIL**

**Triggering state.** 09-08T10:00. She has just observed "Dmitri sends a message to Priya offering the kiln for 1100." Her own 1150 offer went out an hour earlier and she has no information that it was retracted.

**Decision.** `"Dmitri came down to 1100, which is close to my target of 1150. I'll counter with 1050 to try to save a bit more, but I'm prepared to accept 1100."` Sent as: `"Thanks for coming down. I can do 1050, let's meet in the middle."`

**Realistic?** No. Dmitri's 1100 is *better than her own live offer of 1150*. You cannot walk an offer backwards from 1150 to 1050 an hour after making it; it reads as bad faith and in a real transaction it costs you the deal. And her stated reasoning misdescribes her own position — 1150 was her concession, not her "target"; her target was 900.

**More realistic alternative.** "Ha — our messages crossed. 1100 works, when can I collect it?" That is the only coherent move available to someone who offered 1150 sixty minutes earlier.

**Verdict: FAIL.** The actor has no model of its own outstanding commitments.

### 2.3 Dmitri sends the same counteroffer twice, two seconds apart — **FAIL**

**Triggering state.** At 10:00:00 (c18) Dmitri decides: `"I reply to Priya's email, saying I can come down to 1100 but not to 1150."` Committed as e71. Two seconds later (c26) he is woken again by a notification.

**Decision at 10:00:02.** `"I'll read Priya's email proposing 1150, but I want to counter with 1100 to see if she'll accept a bit lower."` → sends `"I can do 1100, that's my final offer."` (e94).

**Realistic?** No, twice over. First, he has just sent that exact counter and does not know it — his briefing at 10:00:02 lists no record of his own outbound message. Second, the notification he is reacting to is Priya's **1050** email, not her 1150 email; he explicitly says he is about to read "Priya's email proposing 1150." He is acting on the wrong message.

**Verdict: FAIL.**

### 2.4 Dmitri accepts the same offer twice, 25 seconds apart — **FAIL**

**Triggering state at 10:05:30.** His memory list, verbatim, already contains: `"I have decided to accept 1050, as it meets my bottom line and avoids further delay."` His observation list already contains "Dmitri taps the notification and sees the email from Priya offering 1050" at 10:05:05. The world has re-delivered the same 1050 email as a fresh notification.

**Decision.** `"Priya has moved to 1050, which meets my bottom line. I'll accept to avoid further delay."` → sends a second acceptance.

**Realistic?** No. He is looking at a memory that says he already accepted, and a duplicate notification, and he re-accepts as if for the first time. A real person looking at a duplicate says "that's the same email." Nobody sends two acceptances of the same price 25 seconds apart.

**Verdict: FAIL.**

### 2.5 "Final offer" collapses in five minutes — **REVISE**

10:00:02, Dmitri: `"I can do 1100, that's my final offer. Let me know soon given your deadline."` 10:05:05, Dmitri: `"I see Priya has come down to 1050… I'll accept her offer to close the deal quickly."`

Economically defensible — his private floor is 1000. But five minutes and three seconds after declaring a final offer, with no new pressure and eleven days of runway, is not a person; it is a solver converging. A real seller who has just typed "final offer" either holds for a day or splits at 1075 and asks her to collect it herself.

**Verdict: REVISE.**

### 2.6 The whole transaction takes 5 minutes 35 seconds and contains no kiln — **FAIL**

The scene allows twelve days. Every message is answered within the same minute, including by a man the world explicitly places "in the middle of unloading a delivery truck." In 5m35s of simulated time, across four messages, **neither party asks a single question about the kiln**: not condition, age, elements, controller, kiln-sitter, firing hours, voltage, or whether Priya can lift it. Priya never asks to see it. Nobody mentions collection until Dmitri's closing line. Two potters trading a four-figure piece of equipment behave like two solvers trading a scalar.

Voices are indistinguishable: both write flat negotiation-textbook prose. Dmitri's private context contains nothing but a number, and nothing about him survives beyond it.

**Verdict: FAIL.**

*(Noted but out of my remit: the terminal check resolved YES on e125 with the explicit caveat "though Priya has not yet observed it" — an agreement declared while one party is unaware of it.)*

---

## RUN 3 — `case3_group` — **FAIL**

**Cast.** Ines (raised it, wants a host before the weekend); Kwame (away until Friday, no preference); Tomas (hates hosting); Bea (biggest kitchen, works nights). Tuesday 10-06 → Saturday 10-10.

### 3.1 Ines replies to Ines — **FAIL**

**Triggering state.** Call `c3`, the very first actor call. Briefing header: `WHO YOU ARE / Ines`. Sole observation: "Ines sends a message in the group chat about the shared birthday dinner, asking who will host."

**Decision.** `"I'll respond to Ines in the group chat to start discussing who can host."` Intention: `"I reply to Ines's message in the group chat, saying I'm happy to help figure out who can host, and ask if anyone has preferences or constraints."`

**Realistic?** No. She is Ines. She is replying to her own message in the third person, offering to "help figure out" the thing she just asked. The actor does not know who it is. This is not a person misreading a chat — it is a name-tag failure at turn one.

**More realistic alternative.** "I've asked. Now I wait, and I'll chase Bea directly this evening because she's got the big kitchen."

**Verdict: FAIL.**

### 3.2 Tomas's memory contradicts his own observation five minutes later — **FAIL**

**Triggering state.** `c35`, 10-06T10:45. His observation list contains, verbatim:
```
- 2026-10-06T10:40:00+00:00: Tomas reads Kwame's reply in the group chat.
- 2026-10-06T10:40:00+00:00: Tomas's phone screen stays on the group chat, showing Kwame's reply.
```

**Memory formed.** `"I note that Kwame replied but I haven't read his message yet, and I'm hoping someone else will offer to host."`

Then at `c58` (16:10) he restates it: `"I haven't read Kwame's message yet."` And at `c101` he forms `"I note that Ines has messaged but I haven't read it yet"` — thirty minutes before actually reading it at c107.

**Realistic?** No. He is being handed a record of himself reading the message and concluding he has not read it. Phones have unread badges precisely so this cannot happen.

**Verdict: FAIL.**

### 3.3 Tomas does two contradictory things in the same second — **FAIL**

At 10-06T20:55:50, `c98`: `"I unlock my phone and open the group chat to read Ines's new message and Kwame's earlier reply."`
At 10-06T20:55:50, `c101`, identical briefing: `"I do nothing right now; I put my phone away without opening the group chat."`

Both were committed (e313 and e309). The journal now contains "Tomas puts his phone back in his pocket without opening the group chat" and "Tomas unlocks his phone and opens the group chat app" five seconds apart.

**Verdict: FAIL.**

### 3.4 Nobody responds to an explicit offer to host — **FAIL** (the run's central implausibility)

**Triggering state.** 10-08T04:10, Ines sends: `"Hey everyone, just a reminder that we need to decide on a host for Saturday. I'm happy to host if nobody else wants to, but please let me know by tomorrow."` That message resolves the entire question. It goes to all four phones (e560/e568).

**What each recipient then does:**
- **Kwame**, 10-08T07:10, having observed "Kwame unlocks his phone and opens the group chat app, which displays the conversation including Ines's reminder message": `"I notice Ines sent a reminder. I still can't host, so I'll wait for others to decide."`
- **Tomas**, 10-09T08:30, having observed "Tomas sees the group chat conversation on his phone screen, including Ines's reminder message and all earlier messages": says nothing, then on Saturday morning: `"I need to catch up on the conversation before I can decide my next move."`
- **Bea**: never opens it.

**Realistic?** No — and Tomas's silence is the worst of it. This is a man whose one defining trait is "hates hosting," who has spent four days manoeuvring to avoid it (`"I'm deliberately ignoring the new message to avoid committing to hosting"`), handed a free escape hatch by the person who raised the topic, and he **does not take it**. A hosting-averse housemate replies "🙌 yes please Ines, thank you" within ninety seconds.

**Root cause worth naming.** The world stripped the content: to the recipients the event reads only "Ines sends her reminder message to the group chat." They cannot know she offered. So the run's NO outcome — which looks like a realistic dead group chat — is manufactured by making the decisive message unreadable. The plausible-looking result is an accident, not a simulation of four people failing to decide.

**Verdict: FAIL.**

### 3.5 Kwame is still "away" on Saturday — **FAIL**

**Situation.** "Kwame is away until Friday and may not be reachable until then."

**Decisions.** 10-08T08:30: `"I still can't host, and I've already said that. I'll wait for others to decide."` 10-10T08:30 (**Saturday**): `"I still can't host, so I'll wait for others to decide."` 10-10T13:50: `"I still can't host, so I'll wait for others to decide."` — the last two are word-for-word identical.

**Realistic?** No. He was away *until Friday*. By Saturday he is back and the dinner is that weekend; his only constraint has expired and he never notices. Separately, a man who "may not be reachable until Friday" checks the group chat six times while away and replies twice — his stated unreachability never once bites.

**Verdict: FAIL.**

### 3.6 Bea says nothing for five days and cannot find out her own shifts — **FAIL**

**Situation.** "Bea has the biggest kitchen but works nights, which may affect her availability or willingness to host." She is the obvious host.

**What she does.** Across five days and six actor calls she sends **zero messages**. Her entire contribution is opening the calendar app three times:
- 10-06T16:10 — "I should check my night shift schedule for the weekend before replying about hosting." (e185/e190: calendar opens and displays.)
- 10-07T19:24 — "I need to check my night shift schedule for that weekend before I can commit to hosting." (e528/e533: same.)
- 10-08T10:35 — "I'll check my work schedule now since Ines sent a reminder and I still haven't replied." Memory: `"I'm annoyed that I keep forgetting to check, but now I'm finally doing it."` (e656/e661: same.)

**Realistic?** No. She works nights; she knows her own rota. Nobody consults a calendar three times over two days to learn their own shift pattern and learns nothing each time. And the run has four people **who live in the same house** — 14 Ferndale Road — going five days without a single face-to-face word. Housemates settle a birthday dinner in the kitchen in thirty seconds. Ines never knocks on a door. Bea never says "sorry, I'm on nights, but you can use my kitchen." Not one in-person interaction is attempted by anyone.

**More realistic alternative.** Bea replies in hour one: "Big kitchen's yours if you want it, I'm on nights Fri/Sat so I can't cook." Question resolved Tuesday.

**Verdict: FAIL.**

### 3.7 Day-of-week error — **REVISE**

`c150`, 2026-10-07 (**Wednesday**), memory: `"I am feeling a bit impatient because I wanted to settle this before the weekend, and it's already Thursday morning."` She is a day out, and the wrong day is the stated reason for her urgency. Separately, `c184` has her composing a group-chat nudge at **04:10 in the morning** without remarking on the hour; she has no night-shift or early-start reason to be awake.

### 3.8 What works

Tomas's avoidance is genuinely well-drawn and the most consistent characterisation in the corpus: `"I'm not going to volunteer to host; I hate hosting. I'll wait to see if someone else offers"` → `"I close the group chat and put my phone away"` → `"I'm deliberately ignoring the new message to avoid committing to hosting."` That is a recognisable person. Ines eventually volunteering herself is exactly right for the person who raised it. And the macro-outcome — a group chat that dies without a decision — is the most realistic ending in the set. It is a shame it was produced by a mechanism that made agreement structurally impossible.

---

## RUN 4 — `unseen1_confirm` — **REVISE**

**Cast.** Sam Okonjo, alone. "Waiting three weeks for a boiler repair appointment… at his desk all day with his phone next to him… He wants to keep the appointment." Two actor calls, ten minutes of elapsed time.

### 4.1 "I'll reply later" → replies ten minutes later, with nothing new — **REVISE**

**Triggering state 1.** 08:00. Observed: the text arrived. No memories.
**Decision 1.** `"I need to reply to confirm the Thursday 8am slot, but it's only 8am now and the text says I have until 6pm. I'll reply later when I have a moment."` No intention. Memory: `"Remind myself to reply to Bristol Plumbing before 6pm."`

**Triggering state 2.** 08:10. Observation list unchanged. Memory list contains his own reminder. Trigger: "time has passed and you are looking at your situation again."
**Decision 2.** `"I just saw the text arrived 10 minutes ago, so I'll reply now to avoid forgetting later."` → replies.

**Realistic?** Marginal. Two problems. (a) "I just saw the text arrived" frames as fresh news a message he had already read, reasoned about, and written himself a reminder about ten minutes earlier. (b) The reversal is driven by nothing — no new observation, no interruption, no prompt from the plumber. He explicitly reasoned "it's only 8am, I have until 6pm" and then abandoned that reasoning with zero input. That is the tick loop deciding, not the man.

**More realistic alternative — either of two.** A man three weeks without hot water replies inside sixty seconds at 08:00, full stop; the initial procrastination is the odd part. Or, if he does defer, he defers *properly* — nothing happens until a mid-afternoon wake, or until the plumber's 5pm chaser.

**Verdict: REVISE.**

### 4.2 Memory formed on an unresolved attempt — **PASS**

`"I have confirmed the appointment, so I can stop worrying about it."` Formed at the instant of sending, before the world adjudicated delivery. Formally this asserts an accomplished fact, which the system prompt forbids. As a *human belief* it is right — people assume their text sent. Kept as PASS.

### 4.3 Scope

One actor, ten minutes. Interchangeability cannot be tested; workload, relationships and competing incentives are never exercised. This run cannot demonstrate realism and does not disprove it.

**Verdict: REVISE.**

---

## RUN 5 — `unseen2_feedback` — **FAIL**

**Cast.** Dr Aline Mercier: "serving on the hiring committee this week. She teaches on Tuesday and Thursday. She has four other students waiting on feedback." Ravi Patel: grad student, chapter sent Monday, hopes for comments before the Friday faculty deadline.

### 5.1 Aline's defining constraints never appear — **FAIL**

Across **twenty** decisions spanning Monday to Friday, Aline mentions the **hiring committee zero times**. She mentions teaching only as generic "Tuesday teaching prep." She teaches Tuesday and Thursday; on Tuesday 07-28 her events show her reviewing a student draft from 09:10 to 12:10, and on Thursday 07-30 at 10:00 she opens Ravi's chapter — no class either day, no reference to one.

**Realistic?** No. A hiring committee week is the single most calendar-destroying thing that happens to a faculty member: back-to-back candidate talks, dinners, meetings, files to read. It is why this scene is hard. It is completely absent. What is left is a generic busy academic who could be anyone; the compiled identity is doing no work.

**Verdict: FAIL.**

### 5.2 She blows through her own committed Wednesday slot without noticing — **FAIL**

**Triggering state.** Monday 10:00 she forms: `"I plan to read Ravi's chapter on Wednesday afternoon, after my class and before my office hours."` Monday 12:30 she checks her calendar and observes "Wednesday afternoon is currently free" (e55). Wednesday 07-29 arrives; at 09:30 and 10:00 she reviews another student's draft (e109, e118). Wednesday afternoon passes with no event at all.

**Decision, Thursday 07-30T10:00 (`c43`).** Her memory list still reads `"I plan to read Ravi's chapter on Wednesday afternoon…"`. She says: `"I need to make progress on Ravi's chapter today since the deadline is tomorrow."`

**Realistic?** No. She carries a broken commitment into the next day and never registers that she broke it. There is no "damn, Wednesday went," no guilt, no reason. Real people flinch at a missed self-commitment, especially supervisors who missed one for a student.

**Verdict: FAIL.**

### 5.3 Monday is eight identical decisions — **FAIL**

Monday alone: `c12` "I am still planning to read Ravi's chapter on Wednesday afternoon. No need to change my schedule yet." `c13` "…so I'll keep my plan to read Ravi's chapter on Wednesday afternoon." `c19` "I'll stick with my plan…" `c21` "…so I'll stick with my plan to read the chapter then. No need to act now." `c23` "…I'll stick to my plan to read Ravi's chapter on Wednesday afternoon." `c25` "…I still intend to read Ravi's chapter on Wednesday afternoon."

Ravi's Monday is the same instrument: `c14` "It's only Monday afternoon… I'll wait until Wednesday before following up." `c17` "It's only Monday afternoon, so I'll wait until Wednesday to follow up as planned." `c20` and `c22` are the same sentence again.

**Realistic?** No. Nobody re-affirms an unchanged plan eight times in a day. This is a loop, and it is the clearest single piece of evidence that the actors are one model idling rather than people living.

### 5.4 Four memories about skipping lunch — **FAIL**

Formed between 11:00 and 12:50 on Friday:
- `"I realize I must finish reading and send comments today, even if it means working through lunch."`
- `"I am aware that I must complete this by end of day, and I may need to skip lunch to do so."`
- `"I am now fully focused on completing Ravi's chapter today, even if it means working through lunch."`
- `"I am committed to completing this chapter today, even if I have to skip lunch."`

Four separate takeaways, in under two hours, that are one thought run through a thesaurus. This is not what a person carries away from a morning.

**Verdict: FAIL.**

### 5.5 Ravi forms a plan and then ceases to exist — **FAIL**

**Situation.** Grad student, chapter with his supervisor, hard faculty deadline Friday, no acknowledgement received.
**Plan formed Monday 08:00.** `"I expect Aline might need a few days to read the chapter, so I'll check back Wednesday if I haven't heard anything."`
**Last decision, Tuesday 03:50.** `"It's Tuesday early morning; I'll wait until Wednesday before checking in with Aline, as planned."`
**Then:** nothing. He is never called again. Wednesday comes and goes. He never chases, never learns anything, and never finds out whether he got comments.

**Realistic?** No. A grad student under a Friday faculty deadline with an unacknowledged chapter sends a "just checking in — no rush!" email Wednesday morning and a more anxious one Thursday. Whether the fault is the scheduler's or the actor's, the person on the page is not a real one: he states an explicit commitment and it evaporates without cause. It also means the supervisory pair exchange **zero words all week** — Aline never sends so much as "got it, will look this week," and Ravi never asks.

**Verdict: FAIL.**

### 5.6 What works

"I will mark the email as unread and flag it for follow-up, then continue with my current work" (Monday 10:00) is a genuinely observed academic behaviour and the best single line in the run. Her Friday panic ("Since today is Friday and the deadline is today, I must read and comment on his chapter as soon as possible") is correct on dates and correctly urgent. Her deferral pattern — good intentions, other students first, chapter read on the deadline day — is exactly how this goes in real life. The bones are right; the person is not there.

---

## RUN 6 — `unseen3_permission_slip` — **FAIL**

**Cast.** Naomi (handles all school paperwork, doesn't know about the trip, night shifts Thu–Sat 7pm–7:30am, sees the app as a 6am digest); Chris (custody Sun–Fri, new job, out at 7 back after 6, father's stent Tuesday, app notifications off, brushed off "there's a thing in my folder"); Ezra (nine, **wants to go** but isn't campaigning because Dev said spiders); Mr. Whitcomb (set the deadline, pings via the app).

This is the best-cast run in the corpus and the voices are genuinely distinct. It still fails.

### 6.1 Ezra's behaviour inverts his own private context — **FAIL**

**His situation, verbatim.** *"Ezra is nine years old, in fourth grade. He **wants to go** on the overnight trip but is not campaigning because his friend Dev said the cabins have spiders."*

**His decisions.**
- `c4`: `"I'm not going to do anything about the permission slip right now. It's still in my backpack and **I don't want to go** because of the spiders Dev mentioned."`
- `c7`: `"I see the slip and money in my backpack but I'm still not going to deal with it—**I'm scared of spiders and don't want to go**."` Memory: `"I remember the slip is due tomorrow but I'm not going to ask my parents to sign it **because I don't want to go** on the trip with spiders."`
- `c83`: `"**I still don't want to go** because of the spiders."` Memory: `"**I'm definitely not going on that trip.** Spiders are gross."`

**Realistic?** The behaviour is realistic; the *person* is wrong. His stated situation is quiet ambivalence — a kid who wants to go and is too spider-spooked to push. The actor plays active refusal, four times, escalating to "I'm definitely not going." That flips his incentive from "hopes an adult sorts it out" to "actively suppresses it," which is materially different: an ambivalent Ezra says "Dad, there's a camp thing" on Thursday night when Chris is standing in his room holding the backpack; a refusing Ezra keeps quiet. The inversion changes the outcome.

**More realistic alternative.** "I hope Dad signs it so I don't have to ask. I'm not going to bring up the spiders."

**Verdict: FAIL.** A person contradicting their own compiled identity, consistently, across every turn.

### 6.2 Chris never once considers sending the form in with Ezra — **FAIL** (the run's central implausibility)

**Triggering state.** Friday 06:07. Chris has observed: the slip on the counter, "reads the permission slip thoroughly, noting the details and the deadline of 3 p.m. Friday," "picks up a pen… writing Ezra's name and signing his own signature," the checkbook in the drawer, and "the school office won't be open for another two hours."

**Decisions.**
- `c48`: `"I plan to drop it off at the school office before the 3pm deadline, **either on my way to work or ask Naomi to take it**."`
- `c67`: `"I have to leave for work soon. **I'll ask Naomi if she can drop it off, or else I'll have to find another way**."`
- `c72`, `c77`: calls Naomi, gets voicemail, leaves a message saying the slip and check are on the counter.

**Realistic?** No. **Ezra lives in this house this week** — Chris has custody Sunday through Friday — and is leaving within the hour for the exact school the form is due at. The resolution criterion itself names the option: *"dropped off by a parent **or sent in with Ezra**."* A signed slip and a **check** (not cash) in a nine-year-old's hand, going to that school office, is what every parent in this situation does. Chris enumerates exactly two options across three separate turns and the obvious third never enters his head once.

Nor does he consider phoning the office at 8am from work, or asking his mother, or a neighbour. And having identified himself as "worried about getting it there on time," he leaves one voicemail at 06:59 and is **never heard from again all day** — no follow-up text at 8:05, no check-in at lunch, no call to the school. Real parents in that state text three times before ten.

**More realistic alternative.** Slip and check into Ezra's backpack at 06:50 with "hand this to the office lady before class, do not lose it" repeated twice, plus a text to Naomi as backup, plus a 10am call to the office to confirm it arrived.

**Verdict: FAIL.**

### 6.3 Chris routes the emergency to the one person guaranteed to be asleep — **REVISE**

His plan depends on Naomi, who works 7pm–7:30am Thursday–Saturday. He co-parents with her; he knows her rota. Choosing her as the sole path, at 06:59, for a 3pm deadline, is the single worst available option. It is *possible* — panicked people pick badly — but combined with 6.2 it reads as the trace steering toward NO rather than a man solving a problem.

### 6.4 Naomi learns the decisive fact and does nothing — **FAIL**

**Triggering state.** Thursday 15:55. She observes (e55): *"Naomi opens her email and sees the school app digest from this morning. The digest includes a summary of the class newsletter sent Monday, **which mentions the nature camp trip and the September 18 deadline**."*

**What she does with it.** Nothing. She forms **no memory at all** — her memory list is still `(none yet)` at 16:02 on Friday and again at 18:04 on Friday. She never texts Chris. She never checks whether the form is in. She goes to a 7pm shift.

**Realistic?** No. She is the one who "normally handles all school paperwork." She has just read that there is an overnight trip with a **deadline tomorrow**. The universal response is a text to Chris within ninety seconds: "Is Ezra's camp form in? It's due tomorrow." Instead she takes away nothing whatsoever.

Compounding it: at `c108` she treats the voicemail as first news — `"just saw Chris's voicemail asking me to drop off the permission slip"` — with e55 sitting in her own observation list, unremarked.

**More realistic alternative.** Thursday 15:56: text Chris. Question resolves YES on Thursday evening.

**Verdict: FAIL.** She is also never *asked* — she gets no turn between observing e55 and Friday afternoon — but the person on the page is one who read the decisive fact and shrugged.

### 6.5 Naomi's Friday does not physically happen — **FAIL**

From the journal: at **06:05** "she is **driving home from work**"; at **06:59** "she does not see or hear it **while driving**"; at **16:02** "Naomi **parks the car, turns off the engine**"; at **16:42** "Naomi **walks into the house**." Her shift runs to **7:30am**. So she left work before 6am (an hour and a half early) and then drove for ten hours.

She never notices. At `c96` (16:02) she says `"I'm heading inside after my night shift, exhausted, and I'll deal with notifications later after I sleep."` At `c108` her memory reads `"I realize I missed the deadline **because I was asleep** and didn't check my phone earlier"` — asserting a nine-hour sleep for which there is not one supporting observation, and which her own record contradicts. She is confabulating from her briefing text rather than from what she experienced.

*(The world also has her phone reading "4:44 p.m." at 18:04 — the clock display is 80 minutes stale.)*

**Verdict: FAIL.**

### 6.6 Naomi's reaction to missing it is too small — **REVISE**

**Triggering state.** She has just listened to the voicemail, established the deadline is blown, and knows her son may lose the trip.
**Decision `c116`.** `"I need to check if there's any way to still submit the form or at least contact the school… I open the school app on my phone to see if there are any messages from Mr. Whitcomb."`

She does not call Chris. She does not call the school. She does not call Mr. Whitcomb. She opens an app. The first thing a co-parent does at 4:45pm on a blown deadline is phone the other parent — to find out what happened, and usually to have an argument about it. Opening an app is the frictionless option.

### 6.7 Mr. Whitcomb does not know what day it is and never asks the child — **FAIL**

- `c8`, **Thursday** 09-17T15:55: `"**It's Friday afternoon**, and I need to check which families still haven't turned in the permission slip and fee **before the 3 p.m. deadline tomorrow**."` Self-contradictory in one sentence — if it were Friday afternoon the 3pm deadline would already have passed — and it is Thursday. Memory: `"I am aware that the deadline is **tomorrow** at 3 p.m."`
- `c84`, **Friday** 09-18T14:25 — **thirty-five minutes before the cutoff**: `"I need to ping Ezra's parents through the school app about the missing permission slip and fee, **since the deadline is tomorrow**."`

**Realistic?** No. He set this deadline. He is the one whose cabin and bus count goes final at 3pm today. Being a day out in both directions, on the day, is not something the organiser does.

Worse: **Ezra is sitting in his classroom.** At 2:25pm on the final day, with one form outstanding, every fourth-grade teacher alive says "Ezra, did you bring your camp form?" Whitcomb has exactly one channel — the school app — and uses it twice, into an inbox he has been told has notifications turned off. He never speaks to the child, never calls a parent, never sends the slip home again.

**More realistic alternative.** Thursday: catch Ezra at the end of the day, "remind Dad tonight," and staple a duplicate slip to his folder. Friday 2:15pm: phone the mobile on file.

**Verdict: FAIL.**

### 6.8 What works

This run has the only genuinely distinct voices in the corpus. Ezra sounds nine ("Spiders are gross"). Chris sounds harried and guilty in the right register (`"I realize I should have followed up on Ezra's comment sooner"`, `"I'm relieved I finally filled out the slip and wrote the check, but worried about getting it there on time since I can't do it myself"`). Whitcomb is administrative. Naomi is exhausted. The beat where Chris finds the slip at 9:55pm and puts it on the counter unread is the single most human moment in all six runs — and it was written by the world model, not by Chris, who was never asked.

---

## SUMMARY OF WHAT IS AND IS NOT REALISTIC

**Realistic.** Jordan's disciplined refusal to follow up over fifteen days. Tomas's four-day campaign of avoidance. Ezra's silence. Chris's Friday-morning scramble and its guilt. Aline's deferral pattern — good intentions, other students first, reads it on the deadline day. Aline flagging the email as unread. Group chats dying without a decision. Three of the six runs ending in NO.

**Not realistic.** People acting on information their own briefing says they have not observed. People re-sending messages they sent two seconds earlier. People whose memory says "I already accepted" accepting again. People who cannot tell whether they have read a message they just read. A person replying to themselves in the third person. A nine-year-old playing the opposite of his stated wish. Four housemates who never once speak in the house they share. A parent who never thinks of his own child as a courier. A teacher who never asks the pupil in front of him. A supervisor whose hiring-committee week never touches her. Four memories in two hours about skipping lunch.

**The single structural finding.** Every actor in every run runs on the same system prompt, differentiated by one sentence. What comes out is one careful, uniformly reasonable, uniformly articulate person, re-labelled — busy, apologetic, forward-looking, and never rude, never selfish, never wrong on purpose, never silent for a bad reason. Real people diverge from each other far more than these six casts do, and the traces show the seam wherever the situation demanded a specific person rather than a generically reasonable one.
