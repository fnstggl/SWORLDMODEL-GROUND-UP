# QUALITY GATE — FINAL REVIEW

Independent review of six live runs under `artifacts/simulations/`. I did not build this system.
Read per run: `compiled_scene.json`, `trajectory.md`, `journal.jsonl`, `actor_exchanges.jsonl`
(prompt + parsed response for every actor call), `world_judgments.jsonl`, `world_exchanges.jsonl`,
`terminal_checks.jsonl`, `terminal_result.json`, `ledger.jsonl`, `event_queue.jsonl`,
`runtime_metrics.json`, `compile/runtime_bindings.json`.

I first read `QUALITY_ACTOR_REALISM.md`, `QUALITY_CAUSAL_REALISM.md`,
`QUALITY_INFORMATION_AND_TIMING.md` and `QUALITY_TERMINAL_INDEPENDENCE.md`, which describe the
**previous, now-replaced** traces. Everything below judges the **current** traces on their own
terms; where I say "fixed" or "not fixed" I mean relative to those four reports.

No repository file was modified except this one.

---

## VERDICTS

| Run | Answer | Actor | Causal | Information | Timing | Terminal |
|---|---|---|---|---|---|---|
| `case1_cold_email` | YES (e107) | **FAIL** | **REVISE** | **REVISE** | **REVISE** | **PASS** |
| `case2_negotiation` | YES (e56,e65,e110) | **REVISE** | **REVISE** | **REVISE** | **FAIL** | **PASS** |
| `case3_group` | YES (6 events) | **FAIL** | **REVISE** | **REVISE** | **REVISE** | **PASS** |
| `unseen1_confirm` | YES (e18) | **REVISE** | **REVISE** | **FAIL** | **FAIL** | **PASS** |
| `unseen2_feedback` | NO_AT_CUTOFF | **REVISE** | **FAIL** | **REVISE** | **FAIL** | **REVISE** |
| `unseen4_holiday_deposit` | INCOMPLETE (step ceiling) | **REVISE** | **REVISE** | **PASS** | **FAIL** | **REVISE** |

Genuine, verified improvements over the previous round: actors now see their own prior actions
(`WHAT YOU HAVE ALREADY DECIDED AND TRIED`), which killed the duplicate-send defect; message
content is now carried inside event descriptions in every run; a bilateral resolution now requires
the counterparty to have observed the acceptance; no actor is silently dropped by the scheduler;
interior-state narration is down to 10/267 committed events (~4%); and `unseen4` contains the
corpus's first off-stage world (Dev's wife, the Leeds couple) and its first genuine adverse event.

---

## ANSWERS TO THE THREE SPECIFIC QUESTIONS

### 1. Is the new YES distribution earned, or has the lean merely inverted?

**Two of the four are earned, one is correct-by-luck, and one is not earned. And a new
one-directional mechanism has replaced the old one.**

Against what the scenarios support:

- **`case3_group` — earned, and the best run in the corpus.** Kwame is away; Bea checks her rota and
  finds she works Friday and Saturday nights; Tomas hates hosting and never volunteers; Ines raised
  it and wants it settled. By elimination Ines hosts. That is what actually happens, in that order,
  over 54 hours, with each person's attention arriving on their own schedule. The scenario supports
  YES and the trajectory reaches it the way it really goes.
- **`case2_negotiation` — outcome earned, route not.** Two motivated parties, a 500 gap, twelve
  days. YES is the likely answer. But it is reached in **97 minutes** with nobody asking a single
  question about a four-figure kiln.
- **`unseen1_confirm` — right answer, broken mechanism.** See §Information below: the world states
  in writing that Sam is *not* looking at his phone and the reply is committed in the same second.
- **`case1_cold_email` — not earned.** This is where the distribution has tipped. The question is
  whether a cold email to a public address from an unknown bootstrapped founder is *likely* to get a
  reply. The trace never represents the one thing that makes the answer no: volume. Across the whole
  run Mark Cuban opens **exactly one email**, and it is Jordan's. There is no assistant, no filter,
  no deletion, no competing message, no archive. He goes from *"I might reply if it seems promising,
  but I'm not sure yet"* (06:10) to sending a reply (08:10) **with no new input of any kind** — the
  stated trigger for the flip is `WHY YOU ARE CONSIDERING THINGS NOW — time has passed and you are
  looking at your situation again`. Then he waits on the founder's answer for five consecutive turns.

**The structural point.** Last round the lean lived in the scheduler and could only *suppress*
events. This round the lean lives in two new places, and both push toward YES:

**(a) A YES halts the run at the instant the judge flips; a NO must run to cutoff.** Verified in
`ledger.jsonl` for all three long YES runs — the last three records are always `world_call` /
`semantic.event` / `terminal_check: YES`. The consequence is that no YES is ever tested against what
comes next:

- `case1` last queued-but-never-committed event: *"The reply email from Mark Cuban is delivered to
  Jordan Reyes's inbox, marked as unread."*
- `case2` halts with Priya's own acceptance of **1200** (`e92`, `for=['dmitri_sokolov'] obs=False
  by=[]`) still undelivered, and her follow-up *"Great, 1150 works. Let's arrange pickup…"* proposed
  and never committed. A real transaction has to resolve that crossed pair; this one stops first.

**(b) The world model now almost never returns `null` when an actor has acted.** It converts
intentions into events, and pending items into attention, with very high frequency. In `unseen2` it
turns "reading a chapter" into 25 committed events; in `unseen4` it turns one unanswered phone call
into seven. A world biased toward *committing something* systematically favours whoever is acting,
which is the party a YES needs.

So: the distribution has moved for partly good reasons (case3 in particular is a real result), but
it has not stopped leaning — it now leans the other way, through a different mechanism.

### 2. Device mechanics — how much, and what does it displace?

Counted over all 267 committed events across the six runs.

| Run | Committed events | Turn on operating a device / screen / notification | Pure device state, no information at all |
|---|---|---|---|
| `case1_cold_email` | 11 | 5 (45%) | 0 |
| `case2_negotiation` | 14 | 5 (36%) | 2 (14%) |
| `case3_group` | 33 | 17 (52%) | 2 (6%) |
| `unseen1_confirm` | 2 | 1 (50%) | 0 |
| `unseen2_feedback` | 57 | 19 (33%) | 6 (11%) |
| `unseen4_holiday_deposit` | 150 | 87 (58%) | 31 (21%) |
| **TOTAL** | **267** | **134 (50%)** | **39 (15%)** |

"Roughly a third" understates it. On the loose definition it is **half**. The strict column (events
that convey nothing but a screen state) is the floor, and is itself conservative — it excludes, for
example, `unseen2` `e202` *"Dr Aline Mercier opens her calendar application on her laptop"* and
`case3` `e465` *"Ines opens a note-taking app on her phone and creates a new note titled 'Shopping
List'"*.

The world's own system prompt forbids this in the exact words of the counter-example it produces:

> Never narrate the MECHANICS of doing something. Opening an application, a window appearing,
> scrolling, clicking, typing a title, a file downloading, a screen displaying what someone just
> asked it to display: none of these are events. If a person does something, the event is that they
> did it — **"she puts it in her diary for Thursday", not the diary opening, the field being typed
> and the window closing.**

`unseen2` puts one entry in a diary in **eight committed events** at 08:00–08:10 on 2026‑07‑29:
`e272` *"opens her calendar application on her laptop"* → `e280` *"opens her calendar application and
views Wednesday and Thursday morning slots"* → `e285` *"calendar displays the current week"* → `e296`
*"calendar displays the current week, showing Wednesday and Thursday morning as available slots"* →
`e301` *"clicks on the Wednesday morning slot in her calendar to create a new event"* → `e305` *"sees
that Wednesday morning has no fixed commitments"* → `e310` *"starts typing a new calendar event"* →
`e328` *"creates a calendar event for Wednesday 9am‑12pm … and saves it."*

**Three concrete damages, in order of seriousness.**

1. **It consumes the budget that decides the answer.** `unseen4` hit `step ceiling 250 reached at
   2026-09-15T08:11:00+00:00, before the cutoff` — 40 hours short of the deadline — having spent 31
   committed events on pure phone state, including six separate commits of Ruth scrolling search
   results and five of *"The notification … remains on … lock screen, unread."* The last twelve
   events of the run are Ruth, Dev and Marian opening apps.
2. **It displaces the moves the question turns on.** In `unseen4` there are seven events for one
   unanswered phone call and **zero** for the two moves that decide the outcome: Ruth paying her own
   £200, and anyone asking Marian whether a part-deposit would hold the week (Nina proposes exactly
   this in `e520` and it is never pursued). In `case3` there are seventeen device events and **not
   one** in which two of four people who share a house are in the same room. In `unseen2` there are
   eight events for a calendar entry and **none** for the hiring committee that is her defining
   constraint — `c53` *"I will attend the hiring committee meeting this afternoon"* returns `null`
   and the committee is never simulated.
3. **It degrades the actors' only channel.** `views` shows an actor the `description` of events they
   observed. When half of those are screen states, the prompt an actor reasons from is a device log.
   `unseen4`'s Ruth is shown four separate records of herself reading one message from Nina at
   07:40 — two of which (`e1230`, `e1242`) are the same sentence verbatim.

### 3. `unseen4_holiday_deposit` — was it heading somewhere plausible?

**The destination yes; the route no.**

By Monday 14 Sept the run has already resolved substantively. `e571` (12:07) — Ruth to Marian:
*"Hi Marian, unfortunately we can't get the deposit together in time, so we'll have to pass on the
cottage for October half-term."* Marian reads it (`e955`, `e960`), writes in her paper diary *"Ruth
cancelled. Left voicemail for Leeds couple re availability"* (`e1052`), and starts chasing the Leeds
couple. Dev's £200 is submitted (`e310`) and its refund is being arranged. Run to Wednesday, the
answer is NO and it is defensible: only £200 of £600 ever moved.

But the route contains an error nobody in the cast catches, and it is the error the outcome rests
on. **Ruth never pays her own £200, never once mentions paying it, and describes her own third as
"fronting".** `e552`:

> *"Dev, thank you for paying your share. Nina, I hope your mum recovers well. Since neither of you
> can cover the remaining £400 and **I'm not in a position to front it**, I think we have to accept
> the cottage is off."*

£600 is £200 × 3. Dev has paid his. Of the remaining £400, **£200 is Ruth's own share** — nobody
else's money, and nothing she would be "fronting". Her private context is explicit that her
reluctance is about *covering other people*: *"she fronted £340 for a group meal last year and was
still chasing the last of it in the spring, so she is not keen on being the one who covers people
again."* She has been chasing this trip since March, has booked the week off and told her kids. She
would put her own £200 in within minutes. Instead she bins the trip on **Monday lunchtime, sixty
hours before Marian's deadline**, over a £400 gap of which half is hers, and neither of the other
two households — nor Marian, nor the world — ever says "Ruth, what about your £200?"

Nina's one constructive idea is also dropped: `e520` *"Is there any chance we could ask Marian if
she'd accept a smaller deposit, or maybe…"* — never pursued, never answered.

So the trajectory was heading to a plausible answer through an implausible group. **REVISE.**

---

## PER-RUN MATERIAL TRANSITIONS

Format: triggering state → decision/judgment (quoted) → realistic? → why → supporting context →
better alternative → verdict.

---

## `case1_cold_email` — YES on `e107`

### T1 — Cuban speaks about an email he has not observed (2026‑07‑27T14:10, `actor:mark_cuban`)

- **Triggering state.** His prompt, verbatim: `WHAT YOU HAVE OBSERVED` / `- (you have not observed
  anything yet)`; `YOUR PRIVATE MEMORIES…` / `- (none yet)`.
- **Decision.** *"I haven't seen any email from Jordan Reyes yet, so I'll continue with my usual
  routine."* Four hours later, `18:10`: attempts *"I open my email inbox and scan for any new
  messages, **including from Jordan Reyes**."*
- **Realistic? No.** He knows the name of a stranger who has emailed him, before any event delivered
  anything, and by 18:10 he is actively scanning *for that sender*. This is worse than the previous
  round's instance of the same defect, which was passive.
- **Supporting context.** The only source is the `SHARED CONTEXT` block in his own prompt: *"Jordan
  Reyes has a short cold email drafted… The email asks for a 15-minute call and references Cuban's
  Cost Plus Drugs pricing playbook."* The actor system prompt now warns *"The SHARED CONTEXT you are
  shown is the situation as an outsider would describe it. It is NOT a briefing you were given"* —
  the warning did not work.
- **Alternative.** Compile a per-actor common-ground block; Cuban's should be empty. His first line
  should be "clearing the inbox", and "Jordan Reyes" should first enter his vocabulary at `e84`.
- **FAIL.**

### T2 — The world contradicts the actor's committed choice in the same second (06:10:00)

- **Triggering state.** At 06:10:00 Cuban attempts *"Open the email from Jordan Reyes and read it."*
- **Committed, both at `2026-07-28T06:10:00`, both `observed=true` for him:**
  - `e76` — *"Mark Cuban opens his email client and sees the inbox. The email from Jordan Reyes is
    present among many unread messages, **but he does not open it at this time**."* (from `c25`,
    `pending_progression`)
  - `e84` — *"Mark Cuban opens the email from Jordan Reyes. The email content is displayed on his
    screen."* (from `c27`, `actor_intention`)
- **Realistic? No.** One man, one second, both opening and not opening. This is the `case3`/Tomas
  defect from the previous round, unchanged: two world calls adjudicate the same instant without
  either consulting what the other wrote.
- **Compounding.** His next prompt shows `e76` (the not-opening) and **not** `e84`; on that basis he
  says *"**I just read it**, so I'll decide if I want to reply."* He asserts having read something
  the only record in front of him says he did not open.
- **Alternative.** Arbitrate one resolution per actor per instant; a `pending_progression` must not
  commit an outcome the actor has already been asked about.
- **FAIL** (transition).

### T3 — The reply (2026‑07‑28T08:10, `actor:mark_cuban`)

- **Triggering state.** Observations unchanged since `e89` (06:10:30). Memories: *"I have read the
  email from Jordan Reyes and am considering it."* Trigger: `time has passed and you are looking at
  your situation again`.
- **Decision.** *"The email is short and references Cost Plus Drugs, which is relevant to my
  interests. I'll reply briefly to see if it's worth a call."*
- **Realistic? Marginally, in isolation; not as this run stages it.** The real Cuban does reply to
  some cold emails, so a reply is not impossible. But nothing changed between 06:10 and 08:10 — no
  new message, no reminder, no free moment described. The reversal is produced by a wake tick, which
  is the same criticism the previous round made of Sam Okonjo, now deciding a whole run.
- **Alternative.** Either he replies at 06:10 when he reads it (Cuban's documented behaviour is a
  one-line reply from his phone, immediately), or the world states what put it back in front of him.
- **REVISE.**

### T4 — Five identical idle turns (08:20 → 13:20)

*"I replied to Jordan's email asking for more details, so I'll wait to see if he responds…"* /
*"I've already replied asking for more details, so I'll wait for his response before taking further
action."* / *"I've already replied asking for details, so I'll wait for his response before doing
anything else."* / (identical again) / *"…so I'll continue to wait for his response before taking
further action."*

Jordan is the same instrument at the other end: `14:00:00` and `14:10:00` are the **same sentence
twice**, *"I just sent the email, so now I'll get back to my regular work and wait to see if I get a
reply."*

A billionaire investor does not check five times in five hours whether an unknown founder has
answered him. The wake ladder is still geometric and still visible: Cuban `10, 20, 40, 80, 160`;
Jordan `10, 20, 40, 80, 160, 320, 420, 640`. **FAIL** on actor realism, **REVISE** on timing.

### Terminal

`e107` — *"Mark Cuban opens a reply composition window and types a response saying he is open to a
short call and asks for more details on what Jordan wants to discuss, **then sends the reply**."* The
resolution asks only that *"Mark Cuban actually sent a response to Jordan Reyes's email before
2026-08-10T09:00:00-05:00."* The cited event contains exactly that act, and it came from the actor's
own intention, not from the world. Judge held UNRESOLVED ten times.

One blemish: the judge returned **UNRESOLVED on `e107` at 08:12** — *"the last event e107 shows it
was sent but not observed, so it is not yet committed as an observed event"* — then **YES on the same
`e107` at 18:10:02**, with no reason given for the change. (The first read was over-strict; sending
is the criterion. But the verdict flipped on unchanged evidence without saying so.) **PASS.**

---

## `case2_negotiation` — YES on `e56`, `e65`, `e110`

### T1 — Priya's opening move (09:00:00, `actor:priya_raghavan`)

- **Triggering state.** Her only observation is `e11`, the two initial positions. Dmitri has not
  moved. Twelve days to the deadline.
- **Decision.** *"I need to move towards a compromise. I'll propose meeting in the middle at 1150 to
  show flexibility and avoid losing the deal."* Sent as: *"How about we meet halfway at 1150? **I need
  the kiln before my lease renewal on the 20th**, and I'd like to wrap this up."*
- **Realistic? No — unchanged from the previous round.** She concedes 250 before the seller has
  moved, and volunteers the two facts that destroy her leverage, on turn one, instantly.
- **Alternative.** Hold at 900 and ask about condition, element age, kiln-sitter, firing hours,
  three-phase, collection. Twelve days is not urgency.
- **REVISE.**

### T2 — Judgment does not support the event it emits (10:00:00, `c15`)

- **Judgment, verbatim:** *"Priya has a message from Dmitri on her phone that she hasn't seen yet.
  She is waiting for a reply, but the reply is already there. **She will eventually check her
  phone.**"*
- **Committed:** `e52` *"Priya notices Dmitri's message on her phone: 'I can lower the price to
  1200.'"*, `observed=true`, `after: now`.
- **Realistic? No.** "Will eventually" is committed as "now". This is finding #2 of the previous
  causal review, unchanged.
- **REVISE.**

### T3 — Two committed non-events (10:30, 10:35)

- `e95` — *"The message remains on Priya's lock screen, unread, as she is not currently attending to
  her phone."*
- `e106` — *"Priya's phone screen shows the notification from Dmitri's '1150 works' message on the
  lock screen, but she does not pick up the phone right now."*
- The world's own rule: *"Never emit an event that merely restates that something is still sitting
  there, still unread, still waiting… that is not an event, it is the absence of one."* Two of
  fourteen committed events in this run are that exact category.
- **FAIL** (transition).

### T4 — The crossed offers (10:30 → 10:37) — the run's best beat

- `c29` (10:30): *"I proposed 1150 and Dmitri responded with 1200, so I need to decide whether to
  accept 1200 or walk away. **I'll accept 1200** because the deadline is tight and I need the kiln."*
  → `e92`, committed `for=['dmitri_sokolov'] obs=False by=[]`.
- `c40` (10:37), after reading `e65`: *"**Dmitri agreed to my 1150 offer before I sent my acceptance
  of 1200**, so I'll proceed with the 1150 deal."*
- **Realistic? Yes, and this is the best-observed human behaviour in the corpus** — a genuine
  crossed-message muddle, correctly identified and correctly resolved by the person who caused it.
- **But:** the run halts here. Her acceptance of 1200 is live, undelivered, and never adjudicated;
  her corrective message was proposed and never committed. In life Dmitri opens *"Okay, I can do
  1200. Let's finalize the deal"* and the two of them have to sort it out — possibly at 1200.
- **PASS** on the beat, **REVISE** on the truncation.

### T5 — Ninety-seven minutes

09:00 → 10:37, against a twelve-day window. Neither party asks one question about a four-figure kiln
— not condition, age, elements, controller, kiln-sitter, voltage, transport, or whether Priya can
lift it. Nobody views it. Nobody sleeps on it. Nothing fails, stalls or is misread: the adverse-event
scan over this run's journal returns **zero hits**. **FAIL** on timing.

### Terminal

> `YES ['e56','e65','e110']` — *"Dmitri observed Priya's offer of 1150 (e56) and agreed by sending
> '1150 works' (e65), which Priya observed (e110), forming an agreement on price 1150."*

Offer, acceptance, and communication of the acceptance back to the offeror — all three committed, all
three cited. This is a **direct and complete fix** of the previous round's worst finding (a YES
declared on an email the counterparty had never seen). **PASS.**

*Latent, unfixed:* `runtime_bindings.json` cutoff is `2026-09-20T18:00:00+01:00`, eighteen hours
**after** the resolution's own `2026-09-20T00:00:00+01:00`.

---

## `case3_group` — YES on `e159`, `e172`, `e294`, `e352`, `e514`, `e531`

### T1 — Universal instantaneous attention at t0 (08:00:00, `c2`)

- **Judgment:** *"The message has been sent to the group chat and is now available to all housemates.
  **They have just seen the notification on their phones**, but no one has responded yet."*
- **Committed:** `e15`, `observed: true, observed_by: ['ines','kwame','tomas','bea']`.
- **Realistic? No — unchanged.** Kwame's compiled context is *"away until Friday and **may not be
  reachable until then**"*; Bea's is *"works nights"*. Both are asserted to have seen an 8 a.m.
  message simultaneously. Kwame then replies at `08:00:00` (`e41`) and does not look at his phone
  again for **54 hours**. His stated unreachability never once bites; his phone-checking behaviour is
  instant, then absent.
- **Alternative.** Commit available-to-all, observed-by-none, and adjudicate each phone separately —
  which is exactly what this run does correctly for every subsequent message.
- **FAIL.**

### T2 — Ines replies to Ines (08:00:00, `c3`, the first actor call)

- **Prompt header:** `WHO YOU ARE — Ines (your identity in this situation: ines)`.
- **Decision:** *"I'm checking the group chat to see **Ines's** message and decide if I want to host
  or suggest something."* Intention: *"Open the group chat and read **Ines's** full message about the
  birthday dinner."*
- **Committed:** `e37` *"Ines opens the group chat and reads **her own message** about the birthday
  dinner."*
- **Realistic? No — unchanged from the previous round.** The actor does not know who it is, at turn
  one, and the world commits the confusion to the permanent record.
- **FAIL.**

### T3 — Bea waits four days for a housemate who does not exist

`c22` (08:05:30): *"I see that both Kwame and I can't host, so the remaining options are Ines or
**Finn**. I'll wait for them to respond."* She repeats it at `c33`, `c47`, `c58`, `c80`, `c84`,
`c102`, `c110` — **eight turns naming Finn**, the last at 23:45 on 10‑06.

There is no Finn. The cast is Ines, Kwame, Tomas, Bea. An actor hallucinated a fifth housemate,
formed a plan around him, and the plan survived across a whole simulated day without anything in the
system noticing. This is a new failure, not present in the previous review. **FAIL.**

### T4 — Bea's rota check (08:00:10, `e45`) — a real fix

*"Bea opens her work schedule app and sees that she is scheduled to work Friday night (Oct 9) and
Saturday night (Oct 10), both shifts ending at 7am the next morning."* She replies five minutes
later declining, with the reason. The previous round had her consulting an empty calendar three times
over two days and learning nothing. **PASS.**

### T5 — Duplication and a mental non-event

- Every group message is committed **twice** — `e82`/`e88` (Ines), `e256`/`e262` (Tomas),
  `e307`/`e313` (Bea), `e531`/`e537` (Kwame): "X sends…" then "X's message arrives in the group chat
  and becomes available to all members." In a group chat these are one instant; the world's own rule
  is *"Machinery that simply works is ONE step, not several."*
- `e365` (08:40:05) and `e369` (08:45:00) are the same reading committed twice, five minutes apart,
  from two different world calls.
- `e380` — *"Ines starts mentally planning a menu, considering pasta with a few options, **but does
  not write anything down or take any concrete action yet**."* The world committed an event whose own
  text says nothing concrete happened, describing what someone privately thinks. Both forbidden.
- **REVISE.**

### T6 — Four housemates, four days, no room

Across 33 committed events and 93 actor turns, **the world never once puts two of them in the same
room.** Ines plans a menu and writes a shopping list without speaking to anyone she lives with.
Unchanged from the previous round. **REVISE.**

### T7 — Timing

The question is settled at `09:40:03` — 100 minutes into a 4.5-day window. Everything after that is
dietary restrictions and a shopping list. Against it, the per-person attention modelling is good and
genuinely improved: Bea asleep post-shift 08:15→23:50, Kwame 54 hours, Tomas dipping in at 10:55,
19:15, 07:55, 14:00. **REVISE.**

### Terminal

> `YES` — *"Ines offered to host on Saturday evening (e159), and all housemates (Tomas, Bea, Kwame)
> saw and acknowledged this, with Bea and Kwame explicitly thanking Ines for hosting, indicating
> collective agreement on Ines as host before the deadline."*

32 UNRESOLVED checks, each naming precisely what was missing (*"Kwame has not observed Ines's offer
to host"*), then a single flip at the moment Kwame acknowledges. The chain is real and every link is
committed. One overstatement: **Tomas never acknowledged anything about hosting** — his only message
in the whole run is *"No restrictions here, I eat anything."* He observed (`e172`, `e352`) and did
not object. Reading that as agreement is defensible in a group chat; calling it "acknowledged" is
the judge describing something adjacent as established. **PASS**, with that noted.

*Unfixed:* runtime cutoff `2026-10-10T20:00:00+00:00` is 20 hours after the resolution's
`2026-10-10T00:00:00+00:00`.

---

## `unseen1_confirm` — YES on `e18`

### T1 — The world says he is not looking, and he replies in the same second

- **World judgment (`c2`), verbatim:** *"The message has just arrived on Sam's phone, but **he is not
  currently looking at his phone. It will sit unread until he picks it up.**"* → `event: null`, plus
  `wake sam_okonjo after 15 minutes: Sam might check his phone soon, but if not, the message remains
  unread.`
- **The ledger, same instant:** `e9`, `"observed": true, "observed_by": ["sam_okonjo"]`.
- **The actor, same instant (`c3`):** *"I need to reply to confirm the Thursday 8am slot as soon as
  possible to avoid losing it."* → `e18` at `08:00:00`.
- **Realistic? No.** Arrival, noticing, reading and replying all happen in **zero seconds**, and the
  world's own written judgment says the opposite is happening. This is the delivery→noticing→
  reading→acting collapse the whole design exists to prevent, stated and contradicted in one step.
  The 15-minute wake it scheduled was never needed because the actor had already been called.
- **Alternative.** Either the compiler should not mark the starting event observed, or the runtime
  should honour the world's `null` + wake before calling the actor. A man three weeks without hot
  water replying within sixty seconds of *picking up his phone* is right; replying before he picks it
  up is not.
- **Information: FAIL. Timing: FAIL.**

### T2 — Belief presupposing the outcome

Private update recorded at the instant of the *attempt*, before adjudication: *"I have confirmed the
appointment and will keep Thursday morning free."* Benign as a human belief; formally it asserts an
accomplished fact. Unchanged. **REVISE.**

### T3 — Scope and terminal

One actor, one step, zero elapsed minutes, two committed events. Nothing about interchangeability,
workload, competing incentives or delay is exercised. `e18` *is* the act the resolution names.
**Terminal PASS**; the run is thin evidence, not evidence of realism.

*Also unchanged:* `shared_context` says the text came *"at 9:00 this morning"*; the clock says
`08:00:00+00:00`. The timezone incoherence is still compiled in.

---

## `unseen2_feedback` — NO_AT_CUTOFF

The previous round failed this run because the scheduler stopped waking Aline mid-compose. **That is
fixed** — she is consulted 37 times, right up to `2026-07-31T16:00:00`, the cutoff instant. The run
now fails for the opposite reason.

### T1 — The reading loop (07‑27T20:10 → 07‑31T16:00) — the run's defining defect

Committed events, verbatim and repeatedly identical:

- *"Dr Aline Mercier reads the next portion of the results section of Ravi's thesis chapter, taking
  notes as she goes."* — committed **nine times** word-for-word (`e168`, `e181`, `e186`, `e376`,
  `e445`, `e458`, `e476`, `e487`, `e506`).
- *"Dr Aline Mercier continues reading the results section of Ravi's thesis chapter, taking notes as
  she goes."* — committed **four times** word-for-word.
- In total **15 of 57 committed events are verbatim duplicates of another committed event.**

She starts the results section at 21:30 Monday and is still in it at 16:00 Friday — **4½ days**, ~25
committed reading events, never reaching the discussion or conclusion, never writing a comment. A
supervisor reads a thesis chapter in an afternoon.

- **World judgment (`c183`), verbatim:** *"Aline continues reading the results section, but the
  chapter is long and she has only covered about half of the results. She is making progress but
  still has a substantial amount left, and the deadline is today."* The world has diagnosed the loop
  and then extended it.
- **Realistic? No.** And the NO turns on it: nothing ever interrupts her. No meeting, no student, no
  committee, no illness, no laptop. The adverse-event scan on this journal returns nothing. The
  answer is produced by a task that never terminates, not by a stated obstacle.
- **Alternative.** One event when she starts a session, one when she stops, `null` in between with
  wakes; and the world must not re-emit a description already in the record.
- **CAUSAL: FAIL.**

### T2 — She closes the document and prepares for bed, then reads for 25 more minutes

- `e126` (21:35) — *"Dr Aline Mercier saves the thesis chapter document, closes it, and prepares for
  bed."*
- `e129` (21:45) — *"Dr Aline Mercier reads the first few pages of the results section, taking notes,
  for about 15 minutes."*
- `e134` (22:00) — *"…She continues reading the next portion of the results section."*

Two independent chains (`c42` from her intention, `c43`/`c46` from an event consequence) adjudicated
the same evening without either reading the other. **FAIL.**

### T3 — Two clock errors, each stated inside a judgment

- `c132`, at `CURRENT TIME 2026-07-29T19:20:30`: *"**It is now 08:10:40 on Wednesday, July 29.**"* —
  eleven hours out. The actor's decision at that same instant reads *"It's now Wednesday morning, and
  I have blocked 9am-12pm today for reading Ravi's chapter. I will start that block now."* — at 19:20.
- `c188`, at `CURRENT TIME 2026-07-31T16:00:00` (the cutoff instant): *"**it is now 13:20 on the
  deadline day. She has several hours left.**"*
- **TIMING: FAIL.**

### T4 — Real fixes, worth recording

- `e150` — *"Dr Aline Mercier teaches her Tuesday class as scheduled."* Her stated teaching now
  happens. (Thursday's class still does not; the hiring committee never happens at all.)
- `c86` (Wed 02:30) — Ravi **chases**: *"It's early Wednesday morning now, so I'll send a polite
  follow-up email to Dr Mercier…"* → `e238`. Last round he stated a Wednesday follow-up twice and was
  never given a Wednesday.
- `e313` — Aline replies *"…she has started reading and will send comments by Friday"*; Ravi reads it
  (`e392`) and calibrates. The supervisory pair now actually communicate.
- `e215` — *"Dr Aline Mercier notices that the Tuesday 9-11am block she set aside for Ravi's chapter
  has already passed without her having completed the reading."* Last round she blew a self-commitment
  without noticing. **PASS** on all four.

### Terminal

> `NO_AT_CUTOFF` — *"No committed event shows that Dr Aline Mercier actually sent comments to Ravi
> Patel before the deadline; she only read parts of the chapter and replied promising to send
> comments."*

57 UNRESOLVED then one flip; the judge is accurate about the record and correctly refuses to count
the *promise* of comments as comments. No steering by any judgment. But the absence it certifies was
manufactured by a non-terminating reading loop rather than by anything about Aline's week.
**REVISE.**

---

## `unseen4_holiday_deposit` — INCOMPLETE (`step ceiling 250 reached at 2026-09-15T08:11:00+00:00, before the cutoff`)

### T1 — Nina breaks her defining constraint in her first second (19:40:00, `c8`)

- **Her compiled context:** *"Nina hasn't replied at all in the thread… because her mum came out of
  hospital after a fall three weeks ago and Nina genuinely doesn't know what October looks like yet.
  **Saying that out loud would make it a thing she has to deal with.**"*
- **Her observations:** one line, her own non-reply. No message from anyone.
- **Decision:** *"I need to reply to the group thread to let them know I'm unsure about October
  because of my mum's situation…"* → sends it in full.
- **Realistic? No.** The scenario is built on her *not* saying it. She says it unprompted, before
  Ruth's chase has even arrived, and then sends the same message again at 21:40, again at 09:40 the
  next morning (`e412`) and again at 09:50 (`e445`) — the same disclosure **four times**.
- **Alternative.** Silence, a thumbs-up, or "sorry, mad week — will come back to you". The point of
  her constraint is the friction of not saying it.
- **FAIL** (transition).

### T2 — Dev and his wife (06:30 → 08:25 Monday) — the best sequence in the corpus

`e187` *"Dev stands up from where he was sitting and goes to look for his wife in the house."* →
`e192` *"finds his wife in the kitchen and starts talking to her about the cottage deposit
situation."* → `e200` *"asks his wife if he can use the credit card for the £200 deposit, promising
to pay it off when he gets paid on the 28th."* → `e206` *"Dev's wife frowns and says, 'We agreed you
wouldn't use that card. But I know how much you want this trip. Let me think about it.'"* → (1h45m
later) `e249` *"'Fine, use the card for the deposit. But you pay it off the day you get paid, and
that's it – no more.'"*

An off-stage party, given a real position, taking real time, granting a conditional concession. This
is the first time in either review round that anyone outside the declared cast has acted. **PASS.**

### T3 — Ruth cancels sixty hours early, on an arithmetic error (12:07 Monday, `e571`)

Covered in full in §Question 3. `e552`: *"Since neither of you can cover the remaining £400 and I'm
not in a position to front it…"* — £200 of that £400 is her own share, which she never offers, never
mentions, and misdescribes as fronting. Nina's *"Is there any chance we could ask Marian if she'd
accept a smaller deposit"* (`e520`) is never pursued. **FAIL** as a transition; it is the transition
the run's direction rests on.

### T4 — One unanswered phone call, seven committed events, 5½ minutes of ringing

`e997` (21:50:00) dials → `e1005` (21:50:00) *"The call connects and rings on the Leeds couple's
phone"* → `e1010` (21:51:00) *"The phone rings at the Leeds couple's end"* → `e1020` (21:55:00) *"The
Leeds couple's phone rings. No one answers yet"* → `e1029` (21:55:30) *"…After several rings, the
call goes to voicemail"* → `e1038` voicemail left → `e1043` *"Marian ends the call after leaving the
voicemail and sets her phone down."*

The previous round flagged a 20-minute ring. It is now 5½ minutes. Phones divert in about thirty
seconds, and this is one automatic mechanism split into five steps. The **content** is right and
valuable — a competing buyer, chased, not reached — the granularity is not. **REVISE.**

### T5 — Duplication at scale

Ten distinct descriptions are committed twice, covering 20 of 150 events: Ruth's chase (`e358`/`e364`,
same second), her cancellation to Marian (`e571`/`e585`, ten minutes apart, two different wordings of
the same act), Nina's private apology (`e682`/`e698`), Ruth's reply to it (`e761`/`e775`), Ruth
reading Nina's message (`e1230`/`e1242`, verbatim, same second), Dev opening Ruth's messages
(`e1281`/`e1286`), Marian reading Ruth's message (`e1320`/`e1323`). Ruth reads Dev's two messages at
09:00, 09:02, 09:15 and 09:15 — four events for one reading. **REVISE.**

### T6 — Where the 250 steps went

36 hours of a 78-hour window consumed; 40 hours never simulated. Of 150 committed events, **87 turn
on operating a device and 31 convey nothing but device state** — including six commits of Ruth
scrolling staycation search results and five of *"The notification … remains on … lock screen,
unread."* The final twelve events of the run are three people opening apps. **TIMING: FAIL.**

### Information

The strongest dimension in the corpus. Nobody acts on what they lack. Private context stays private.
Attention is separated from delivery throughout and the reasons are specific and in-character
(*"he is still talking to his wife and does not pick up his phone"*, *"she is with her mother"*).
Dev's payment is correctly held as unconfirmed: `e842` *"Marian opens her banking app… sees no
deposit of £600 from anyone. She does not see any smaller payment either, or if Dev's £200 has
arrived, it is not the full deposit she is expecting"*, and the judge tracks it —
*"Dev's £200 transfer is submitted but not confirmed as received by Marian"*. **PASS.**

### Terminal

148 judge calls, all UNRESOLVED, all accurate; the judge never once counts Dev's £200 as the £600, and
correctly distinguishes submitted from received. No steering whatsoever. The terminal was never
reached. **REVISE** (incomplete, not defective).

---

## CROSS-CUTTING FINDINGS

**1. Two world calls still adjudicate the same instant without reading each other.** `case1`
`e76`/`e84` (opens / does not open, same second). `unseen2` `e126`/`e129` (closes the document and
prepares for bed / reads for 25 more minutes). `case3` `e365`/`e369`. `unseen4` `e1230`/`e1242`. The
previous round's Tomas defect has moved runs, not disappeared. 22 of `unseen4`'s 127 actor turns
occur at an instant that already had another turn for the same actor.

**2. The world still restates the record.** 35 of 267 committed events are verbatim duplicates of
another committed event (`unseen2` 15, `unseen4` 20), against the explicit rule *"Do not restate the
record… writing it again would make the same thing occur twice."*

**3. Only inattention still goes wrong, in five of six runs.** The adverse-event scan returns zero
hits for `case1`, `case2`, `case3` and `unseen1`, and nothing but a promise-to-send for `unseen2`.
`unseen4` alone has a competing buyer, an unanswered call and a spouse who says no. The world prompt
now explicitly asks for this (*"A situation in which the only thing that ever goes wrong is that
somebody did not get round to it is not a realistic situation"*); one run in six complies.

**4. `SHARED CONTEXT` is still an omniscient channel.** The actor prompt now warns against treating
it as a briefing, and the warning does not work: Mark Cuban scans his inbox *"including from Jordan
Reyes"* with `(you have not observed anything yet)`; Dmitri is told Priya's lease deadline at t=0.

**5. The geometric wake ladder is still there.** `10, 20, 40, 80, 160, 320, 640` appears in every
run. It now resets on events (the fix that stopped actors being dropped), but it still produces
bursts of five to eight identical no-op turns — Tomas's *"Ines is already hosting, so I don't need to
do anything"* roughly twenty times, Kwame's *"I'm still away and haven't seen any new messages"*
twelve times, Nina's *"the trip is off… I'll focus on my mum's recovery"* five times in three hours.

**6. Runtime cutoffs still overshoot the resolution deadline.** `case2` by 18 h, `case3` by 20 h.
Immaterial to these outcomes; still latent.

---

## THE THREE MOST SERIOUS REMAINING PROBLEMS

1. **`unseen4` — the answer turns on an arithmetic error nobody in the world catches.** `e552`:
   *"Since neither of you can cover the remaining £400 and I'm not in a position to front it, I think
   we have to accept the cottage is off."* Half that £400 is Ruth's own share of a trip she has
   chased since March, booked leave for and told her kids about. She cancels sixty hours early
   without ever offering it, and neither of the other two households, nor the cottage owner, nor the
   world model, ever asks her about it.

2. **`unseen2` — the NO is produced by a task that cannot finish.** *"Dr Aline Mercier reads the next
   portion of the results section of Ravi's thesis chapter, taking notes as she goes"* is committed
   **nine times verbatim**; she is inside the results section from Monday night to Friday afternoon.
   The world diagnoses it — *"the chapter is long and she has only covered about half of the results…
   and the deadline is today"* — and then extends it. Nothing ever interrupts her; the answer is a
   loop, not a week.

3. **Half of all committed events are somebody operating a device (134/267; 39 convey nothing else),
   and it costs the runs their budget and their substance.** `unseen2` spends eight committed events
   putting one entry in a calendar, against a system prompt whose own counter-example is *"she puts
   it in her diary for Thursday, not the diary opening, the field being typed and the window
   closing."* `unseen4` hits its step ceiling forty hours before the deadline with its last twelve
   events being three people opening apps. `case3` commits seventeen device events and not one in
   which two of four people who share a house are in the same room.

Runner-up, because it is new: **`case3`'s Bea spends eight consecutive turns across a full simulated
day waiting for a housemate who does not exist** — *"the remaining options are Ines or Finn"* — and
nothing in the system notices.
