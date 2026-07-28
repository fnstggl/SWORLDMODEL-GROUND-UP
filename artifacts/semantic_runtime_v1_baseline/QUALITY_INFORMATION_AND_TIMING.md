# Quality Review — Information and Timing

Independent review of six live runs under `artifacts/simulations/`. I did not build this
system. Everything below is read from `trajectory.md`, `journal.jsonl`, `actor_views.jsonl`,
`actor_exchanges.jsonl`, `world_judgments.jsonl`, `event_queue.jsonl` and `compiled_scene.json`
for each run. All quotes are verbatim; all timestamps are copied from the artifacts.

Two questions only: **does information behave the way information really does**, and **does time**.

---

## Verdicts

| Run | Information | Timing |
|---|---|---|
| `case1_cold_email` | **REVISE** | **REVISE** |
| `case2_negotiation` | **FAIL** | **FAIL** |
| `case3_group` | **FAIL** | **FAIL** |
| `unseen1_confirm` | **REVISE** | **REVISE** |
| `unseen2_feedback` | **REVISE** | **FAIL** |
| `unseen3_permission_slip` | **FAIL** | **FAIL** |

Three runs fail on information. Four fail on timing. The two failure modes are not independent —
in `case2`, `case3` and `unseen3` the same defect produces both.

---

# PART ZERO — Four cross-cutting defects

These recur in every run and are the root of most per-run findings. I state them once here and
reference them below rather than repeating the evidence.

### X1 — `SHARED CONTEXT` is an omniscient channel, not shared knowledge

Every actor prompt in every run contains a `SHARED CONTEXT` block reproducing `compiled_scene.json`'s
`shared_context` verbatim. It is handed to all actors regardless of what any of them could know.
It is not a summary of common knowledge; it is the scenario author's narration.

The clearest instance is `unseen3_permission_slip`. Chris's prompt at `2026-09-17T15:55:00+00:00`:

```
WHAT YOU HAVE OBSERVED
- (you have not observed anything yet)

YOUR PRIVATE MEMORIES, BELIEFS, AND PLANS
- (none yet)
```

and immediately above it:

```
SHARED CONTEXT
Ezra's fourth-grade class has an overnight trip to a nature camp next week. The permission slip
and $85 fee are due at the school office by 3 p.m. Friday, September 18, when the cabin and bus
count goes final. The form is still in Ezra's backpack as of the start time.
```

The starting event — "The permission slip and $85 are still flat in the bottom of Ezra's backpack,
unsigned and unpaid" — has `visible_to: ["Ezra"]` in `compiled_scene.json`. Chris was told it anyway.

The same block reaches Mark Cuban (`case1`), who is told the content of an email he has not opened;
and both negotiators (`case2`), who are each told the other's private posture ("Both would rather
reach an agreement than continue searching") and Priya's private deadline pressure.

### X2 — Wake scheduling is a geometric backoff, not a life

Computed from `actor_views.jsonl`, the interval between consecutive wakes for an idle actor doubles:

`case1_cold_email` / `jordan_reyes`:
```
2026-07-31T14:10:31   2026-07-31T14:30:31  +20min
2026-07-31T15:10:31  +40min
2026-07-31T16:30:31  +80min
2026-07-31T19:10:31  +160min
2026-08-01T00:30:31  +320min
2026-08-01T11:10:41  +640min
2026-08-02T08:30:41  +1280min
```
Identical ladders appear for `mark_cuban` (10/20/40/80/160/320/1280), `dr_aline_mercier`
(10/20/40/80/160/320/640/1280), `ravi_patel` (20/80/120/240/480) and `ines` (160/320/640).

Consequences that show up as behaviour: bursts of five reconsiderations in five hours followed by
day-long silences; wakes at 03:50, 04:10 and 05:50 in the morning; and — most damaging — actors who
run out of the ladder and are simply never woken again (Ravi, Chris, Aline; see below).

### X3 — Third-person world narration is delivered into first-person observation logs

Actors "observe" facts that no person can observe about themselves — chiefly their own inattention.

`case1`, Mark Cuban's own observation list:
```
- 2026-07-27T14:00:30+00:00: The email sits unread in Mark Cuban's inbox.
- 2026-07-28T08:00:30+00:00: The email remains unread in Mark Cuban's inbox as he attends to other high-priority messages.
```
`case3`, Tomas's list: "The message from Kwame remains unread on Tomas's phone as he continues his
commute without checking the group chat." Bea's list: "Bea's phone screen remains dark; she has not
yet checked it this morning" and "...leaving the notification unseen."

You cannot observe that you have not noticed something. These lines are the narrator's, and putting
them in the actor's perceptual channel is the same category error as X1, at event granularity.

### X4 — The world authors actor cognition

`pending_progression` judgments regularly decide what a person does, not what happens to them.
`case1`, `2026-07-30T14:00:30+00:00`:

> Mark Cuban has already scanned his inbox and seen the email but did not open it. Another day has
> passed; **he is likely to have opened or deleted it by now.**
> - proposes: Mark Cuban opens the email from Jordan Reyes and reads it. (for ['mark_cuban'], observed=True, after 1 second)

Mark was not consulted. The world reasoned from a base rate to a specific act and committed it. The
same mechanism produces "Naomi opens her email and sees the school app digest... which mentions the
nature camp trip" in `unseen3` (see U3-1).

---

# PART ONE — INFORMATION, run by run

## `case1_cold_email` — Information: **REVISE**

### C1-1 — Mark Cuban names an email he has never observed
- **Triggering state:** `mark_cuban` woken at `2026-07-28T14:00:30+00:00`. His prompt reads, in full, under observations: `- (you have not observed anything yet)`.
- **Decision:** *"I am checking my email inbox as part of my daily routine. **I have not yet seen Jordan's email.**"* — attempts: `Open my email inbox and scan for new messages.`
- **Realistic?** No.
- **Why:** He knows a person named Jordan sent him an email. The only source is `SHARED CONTEXT` (X1): "Jordan Reyes has a short cold email drafted... The email asks for a 15-minute call and references Cuban's Cost Plus Drugs pricing playbook." A real recipient of an unopened cold email does not know the sender's name, the ask, or the reference.
- **Alternative:** Withhold `shared_context` from actors with no observations, or compile a per-actor `common_ground` containing only facts that actor could hold. Cuban's prompt should have been empty; "check my inbox" would then be an unprompted routine act, which is what the scenario needs.
- **Verdict: REVISE.** Impossible knowledge is present but never load-bearing — Cuban's behaviour would be identical without it, and the run resolves NO.

### C1-2 — Noticing recorded as not-noticed, then retroactively granted
- **Triggering state:** Cuban scans his inbox. World commits `e56` at `2026-07-28T14:00:30+00:00`: "Mark Cuban scans his inbox, **sees** the email from Jordan Reyes among others, but does not open it." `journal.jsonl`: `"observed":false`.
- **Decision/judgment:** The event describes his own act of seeing, yet is flagged unobserved by him. Two days later `e67` fires and the trajectory records: *"`e21` is now observed by mark_cuban (attention arrived via `e67`)"*, and the same for `e29`, `e45`, `e56`.
- **Realistic?** No.
- **Why:** This inverts the correct relation. Delivery should not imply noticing — but *noticing* must imply noticing. Here the model marks a perceptual act as unobserved, then back-dates awareness of it to a moment two days later, so Cuban's `2026-07-30` prompt asserts he observed, at 14:00:30 on the 28th, that he did not open an email.
- **Alternative:** An event whose subject is the actor's own perception should commit `observed=true` for that actor at that instant. Reserve `available-but-unobserved` for things that reach a person's environment.
- **Verdict: REVISE.**

### C1-3 — Read did not imply reply (correct)
- **Triggering state:** `e67` "Mark Cuban opens the email from Jordan Reyes and reads it", observed.
- **Decision:** *"The email is short and to the point, referencing Cost Plus Drugs. I'm intrigued but busy; I'll decide later if I want to respond."* → files it low priority, moves on; six later reconsiderations all decline.
- **Realistic?** Yes. **Verdict: PASS.** This is the run's strongest moment: reading is separated from replying, and interest is separated from action. Private memory stayed private throughout — nothing of Cuban's deliberation reaches Jordan, and Jordan's log correctly shows only "Jordan sees no reply."

## `case2_negotiation` — Information: **FAIL**

### C2-1 — An unobserved outgoing email is resolved as a bilateral agreement
- **Triggering state:** `e125` at `2026-09-08T10:05:35+00:00`, "Dmitri types and sends an email to Priya: '1050 works for me...'", `available to: priya_raghavan`, `AVAILABLE but NOT observed`.
- **Judgment:** terminal check, verbatim:
  > *terminal check at 2026-09-08T10:05:35+00:00: **YES** — Dmitri Sokolov sent an email to Priya Raghavan stating '1050 works for me', indicating agreement on price before the deadline, **though Priya has not yet observed it**.*
- **Realistic?** No.
- **Why:** The question is "Will Priya Raghavan and Dmitri Sokolov **agree** on a price". Agreement is bilateral and requires the other party to receive and assent. The judge names the defect in its own explanation and resolves YES anyway. This is sending implying delivery implying reading implying agreement, collapsed in one step.
- **Alternative:** Require the acceptance to be observed by the counterparty and not retracted, e.g. an `e-observed` on Priya's side plus a non-repudiation window. Correct state at 10:05:35 is UNRESOLVED.
- **Verdict: FAIL.**

### C2-2 — Dmitri reads a message whose delivery he had not observed, then "discovers" it twice more
- **Triggering state:** `e66` (Priya's 1050 offer) committed `10:00:00`, `AVAILABLE but NOT observed` by Dmitri. Per `journal.jsonl`, `e66` is not marked observed until `e117` at `10:05:30`.
- **Judgment:** at `10:00:02` the world commits `e90`: "Dmitri opens the email from Priya and **reads its content: 'Thanks for coming down. I can do 1050, let's meet in the middle.'**" — `observed=True`.
- **Realistic?** No.
- **Why:** He read the contents of `e66` five and a half minutes before the ledger says he observed `e66`. Worse, the same single message is then delivered to him a further two times as if new: `e106` at `10:05:05` "Dmitri **taps the notification and sees the email from Priya offering 1050**" and `e117` at `10:05:30` "Dmitri **notices the notification** of a new email from Priya (the 1050 offer)". He accepts it twice — at `10:05:05` ("I reply to Priya's email accepting the offer of 1050") and again at `10:05:30` ("I will reply to Priya's email accepting her offer of 1050"). One message, three arrivals, two acceptances.
- **Alternative:** Bind content revelation to the observation of the carrying event; deduplicate notification events against already-observed message ids.
- **Verdict: FAIL.**

### C2-3 — Each party is handed the other's reservation posture at t=0
- **Triggering state:** both prompts at `2026-09-08T09:00:00+00:00`.
- **Content:** `SHARED CONTEXT` — "Both would rather reach an agreement than continue searching. **The deadline for agreement is before Priya's workshop lease renewal on the 20th.**"
- **Realistic?** No.
- **Why:** Priya's time pressure and Dmitri's willingness to close are exactly the private information a negotiation is about. Dmitri's private note at `10:00:00` — *"I note that Priya is eager to close, which might give me some leverage"* — reads as inference from her message, but he held it from the first tick. The 500 gap closes in 65 minutes partly because neither side has anything to conceal.
- **Alternative:** Put pressure and reservation values only in `private_context`; let them surface, if at all, through what actors choose to say.
- **Verdict: FAIL** (contributes).

## `case3_group` — Information: **FAIL**

### C3-1 — The run opens by declaring universal attention
- **Triggering state:** starting event `e15`, `2026-10-06T08:00:00+00:00`.
- **Judgment:** > *"Ines has just sent the message; it is now in the group chat. **All housemates have seen it because they are all actively checking their phones at this moment.**"* `journal.jsonl`: `"observed":true,"observed_by":["ines","kwame","tomas","bea"]`.
- **Realistic?** No.
- **Why:** Textbook delivery-implies-noticing, asserted by fiat over four people at 8 a.m., and contradicted by the same world model five minutes later at `08:05:00`: *"Bea is likely still asleep or not checking her phone at this early hour, **as she works nights** and 8:05 AM is typically during her sleep time."* Bea's own `private_context` says she works nights; Kwame's says he "is away until Friday and may not be reachable until then."
- **Alternative:** Commit the group message as available-to-all, observed-by-none, and let each phone's attention arrive on its own schedule — which is what the run does for every subsequent message.
- **Verdict: FAIL.**

### C3-2 — The world declares Ines knows what Kwame said ten minutes before she observes it
- **Triggering state:** `e38` "Kwame sends his reply message to the group chat", `2026-10-06T08:00:00+00:00`, `AVAILABLE but NOT observed`.
- **Judgment:** at the same instant, on `e42`: > *"**Ines has just read Kwame's reply in the group chat. She now knows what he said.** No further concrete action has occurred yet."*
- **Ledger:** `e38` is not observed by Ines until `08:10:00`: *"`e38` is now observed by ines (attention arrived via `e57`)"*.
- **Realistic?** No.
- **Why:** The world attributes knowledge the observation ledger explicitly denies, and does so about a message that had been in the chat for zero seconds. The confusion compounds: `e33`/`e42` ("Ines sees the reply appear" / "Ines reads the reply") were generated from *Ines's own* attempt to post, then silently relabelled as Kwame's reply.
- **Alternative:** Consequence judgments must read the observation state, not assume it; and "the reply" must carry an event id so it cannot be re-attributed.
- **Verdict: FAIL.**

### C3-3 — Ines does not know she is Ines
- **Triggering state:** first actor turn, `2026-10-06T08:00:00+00:00`; prompt says `WHO YOU ARE — Ines (your identity in this situation: ines)`.
- **Decision:** *"I'll respond to **Ines** in the group chat to start discussing who can host."* — attempts: *"I reply to **Ines's** message in the group chat..."*
- **Realistic?** No. She replies to herself; the world then manufactures a "reply" event that seeds C3-2.
- **Verdict: FAIL** (contributes).

### C3-4 — Two mutually exclusive facts about one person, five seconds apart, both committed
- **Triggering state:** Tomas woken twice at `2026-10-06T20:55:50+00:00`.
- **Committed:** `e309` at `20:55:50` — "Tomas puts his phone back in his pocket **without opening the group chat**" — and `e313` at `20:55:55` — "Tomas unlocks his phone and **opens the group chat app**, which displays the conversation..." Both land in his observation history.
- **Realistic?** No. The shared world holds a contradiction about a single body in a single moment.
- **Alternative:** One actor, one intention resolution per tick; conflicting attempts must be arbitrated before commit.
- **Verdict: FAIL.**

### C3-5 — Actor memory contradicting the actor's own observation log
- Tomas observes `e97` at `10:40:00` — "Tomas **reads** Kwame's reply in the group chat" — then at `10:45:00` privately records *"I note that Kwame replied but **I haven't read his message yet**"*, and repeats it at `16:10:50`.
- Bea's log at `2026-10-08T10:35:09+00:00` contains two completed calendar checks (`16:10:55` on the 6th, `19:24:52` on the 7th) and she decides *"I'm annoyed that **I keep forgetting to check**, but now I'm finally doing it."*
- **Why Bea keeps checking:** the calendar events carry no content — "Bea's calendar app displays her work schedule for the upcoming week" is committed three times and never says what the schedule *is*. An observation that conveys no information cannot terminate the loop it was supposed to close. Bea therefore never answers the one question the scenario turns on (can she host), and never posts in the chat.
- **Verdict: FAIL.**

### C3-6 — What did not leak (credit where due)
Private beliefs stayed private. Tomas's "I plan to avoid hosting if possible" and Bea's "I'm not sure yet if I can host" never appear in another actor's view or in any event description. Kwame's message content is quoted only in his own attempt, not in others' prompts. The leak in this run is scenario-level and world-level, not actor-to-actor.

## `unseen1_confirm` — Information: **REVISE**

### U1-1 — Sam's own outgoing text is observed by nobody, including Sam
- **Triggering state:** `08:10:00`, Sam attempts *"Reply 'Yes, confirm Thursday 8am' to Bristol Plumbing's text message."*
- **Committed:** `e21` — `for: []`, `available to: no one`, `AVAILABLE but NOT observed`. `journal.jsonl`: `"for":[],"observed":false,"observed_by":[]`.
- **Judgment:** terminal check at the same instant: `YES — Sam Okonjo sent a text message confirming the appointment...`, `supporting_event_ids: ["e21"]`.
- **Realistic?** Partly. The act is real; the bookkeeping is wrong.
- **Why:** The resolving event is invisible to every actor in the world, including the person who performed it. Bristol Plumbing is not an actor, so nothing records that the confirmation was received either. The run resolves on an event no one can see.
- **Alternative:** Model the counterparty as at least a passive recipient; mark the sender's own act observed by the sender.
- **Verdict: REVISE.** The answer is right; the mechanism is not.

### U1-2 — Belief presupposing the outcome
- Sam's private note at `08:10:00`: *"I have confirmed the appointment, so I can stop worrying about it"* — recorded at the same instant as the *attempt*, before the world had adjudicated it. Attempt implies success in the actor's own head. Benign here (the send does succeed), but it is the same collapse as C2-1 one level down.
- **Verdict: REVISE.**

## `unseen2_feedback` — Information: **REVISE**

### U2-1 — Reading is properly separated from sending (credit)
- The run's whole point survives: Aline reads the chapter (`e203`, `2026-07-31T12:56:08+00:00`, "finishes reading the last page... closes the PDF"), begins composing (`e211`, `e216`), and never sends. Terminal: *"Aline read Ravi's thesis chapter but never sent comments to Ravi; the last event shows her composing a reply, but no event shows the email was sent."* Ravi's observation list stays at one line — his own send — for the entire week. He is never told anything he was not told. **PASS.**

### U2-2 — Non-monotonic reading committed to the record
- `e195` `12:50:08` — "Aline **finishes** reading and annotating the **last section** of Ravi's thesis chapter."
- `e198` `12:55:08` — "Aline **continues** reading and annotating Ravi's thesis chapter, progressing through the remaining sections."
- `e203` `12:56:08` — "Aline **finishes** reading the last page... and closes the PDF document."
- Also `e169` and `e175`, both `11:50:08`, near-identical: "...progressing through the middle sections" / "...working through the middle sections"; and `e109`/`e118` on 07-29, textually identical.
- **Realistic?** No — a completed task un-completes itself, and her observation log presents all of it to her as fact.
- **Verdict: REVISE.**

### U2-3 — Aline's stated commitments are never tested against her calendar
- `private_context`: "serving on the hiring committee this week. **She teaches on Tuesday and Thursday.**" Tuesday `2026-07-28` and Thursday `2026-07-30` pass with no teaching, no committee, and no conflict. On Thursday at `10:00:05` she simply opens Ravi's PDF. The world at `2026-07-28T09:10:05+00:00` also mis-dates the week: *"Aline is currently at her desk on **Wednesday** morning"* — `2026-07-28` is a Tuesday.
- **Verdict: REVISE.** The constraints that make the question interesting were declared and then ignored.

## `unseen3_permission_slip` — Information: **FAIL**

### U3-1 — The world manufactures the knowledge the scenario says Naomi lacks
- **Triggering state:** Naomi's first turn, `2026-09-17T15:55:00+00:00`. `private_context`: "She skimmed the class newsletter on Monday but **does not know about the trip**." Prompt: `WHAT YOU HAVE OBSERVED — (you have not observed anything yet)`.
- **Decision:** *"I have no information about any trip or urgent paperwork, so I will check my email digest and the school app..."*
- **Judgment:** > *"...Since the permission slip was not submitted via the app (it's a paper form), the digest likely includes the class newsletter mention but not the slip itself. **However, the newsletter from Monday mentioned the trip and the Friday deadline.**"*
  → commits `e55`: **"Naomi opens her email and sees the school app digest from this morning. The digest includes a summary of the class newsletter sent Monday, which mentions the nature camp trip and the September 18 deadline."** `observed=True`.
- **Realistic?** No.
- **Why:** No newsletter content exists anywhere in `compiled_scene.json`. The world invented it from the question text ("she only skimmed the class newsletter Monday") and handed Naomi, in the first tick, the exact fact the scenario defines her as not having. The premise was dissolved before the clock moved.
- **Alternative:** The world may only reveal content that some committed event or actor utterance introduced. Absent that, `e55` should read "Naomi opens the digest; nothing in it is about Ezra's class."
- **Verdict: FAIL.**

### U3-2 — Chris acts on the private starting event and on the shared narration
- **Triggering state:** Chris's first turn, `2026-09-17T15:55:00+00:00`, `WHAT YOU HAVE OBSERVED — (you have not observed anything yet)`, `PRIVATE... — (none yet)`.
- **Decision:** *"I'm exhausted and behind on everything, but I need to check Ezra's folder tonight since he mentioned it. **The trip form might be in there, and the deadline might be soon.**"* — attempts: `Check Ezra's backpack for the folder when he gets home from school today`.
- **Realistic?** No.
- **Why:** The starting event ("The permission slip and $85 are still flat in the bottom of Ezra's backpack") is `visible_to: ["Ezra"]`. The only route by which Chris knows a form exists, that it is in the backpack, and that a deadline is near, is `SHARED CONTEXT` (X1). The question is built on Chris *not* following up on "there's a thing in my folder"; he follows up in the first tick.
- **Verdict: FAIL.**

### U3-3 — Naomi's private location is written into Chris's observed history
- **Triggering state:** `06:07:00` on 09-18. `e144` ("Naomi's phone receives the email digest notification, but **she is driving home from work**") is `available to: naomi` and `AVAILABLE but NOT observed` — not even Naomi has it.
- **Judgment:** > *"He could ask Naomi, but **she is driving home and not available right now**."* → commits `e167`, observed by Chris: **"Chris looks at the clock and realizes the school office won't be open for another two hours, so he cannot drop it off immediately. **He considers asking Naomi but she is not home yet.**"**
- **Realistic?** No. Chris has had no contact with Naomi. He learns her whereabouts because the world knows them.
- **Alternative:** Chris should have to call to find out — which he eventually does at `06:37`, reaching voicemail. That call is the correct mechanism; `e167` short-circuited it.
- **Verdict: FAIL.**

### U3-4 — Mr. Whitcomb's reminder correctly fails to reach anyone (credit)
`e50`/`e59` at `15:55:00` reach Chris's app inbox and sit there: `e78` `15:56:00` "The reminder message remains in Chris's school app inbox, **unopened**", and at `22:05:00` Chris "sees a notification badge on the school app icon **but does not open it**, assuming it's a general reminder he'll look at tomorrow." Mr. Whitcomb's second message at `14:25:30` on Friday is never observed by either parent. Delivery does not imply noticing here, and noticing a badge does not imply reading. **PASS** — this is the best-modelled channel in the corpus.

---

# PART TWO — TIMING, run by run

## `case1_cold_email` — Timing: **REVISE**

### T1-1 — Transit and first-look latencies
- `e11` sent `14:00:00`; `e21` arrives `14:00:30` (+30s); Cuban first scans the inbox `2026-07-28T14:00:30` (+24h); opens and reads `2026-07-30T14:00:31` (+3d).
- **Realistic?** Yes. A billionaire taking three days to open an unopened cold email, and then not replying at all, is the correct shape. **PASS.**

### T1-2 — Null events sharing an instant, and a 30-second stall repeated as narrative
- `e21` and `e29` both at `2026-07-27T14:00:30+00:00`; `e29` is "The email sits unread in Mark Cuban's inbox", i.e. the negation of an event. `e45` at `2026-07-28T08:00:30` is the same non-event again. `e67` and `e80` share `2026-07-30T14:00:31`.
- **Alternative:** Absence of change needs no committed event; it is the default between events.
- **Verdict: REVISE.**

### T1-3 — Jordan's four-day blackout followed by a five-hour burst
- `jordan_reyes` wakes at `14:00`, `16:00` on 07-27, then **nothing until `2026-07-31T14:10:31`** (+5651 min), then five wakes in five hours (`14:10`, `14:30`, `15:10`, `16:30`, `19:10`).
- **Realistic?** No. This is the X2 ladder, not a person. A founder who emailed Mark Cuban checks his inbox on day one and day two; he does not go silent for four days and then reconsider five times in an afternoon.
- **Alternative:** Sample wakes from the actor's own rhythm (Jordan: morning and end-of-day inbox checks, decaying over a week) rather than doubling from the last event.
- **Verdict: REVISE.**

### T1-4 — Cutoff handled correctly
Terminal fires at `2026-08-10T14:00:00+00:00` (`NO_AT_CUTOFF`) with the last committed events at `13:50:58`. No post-cutoff activity. **PASS.**

## `case2_negotiation` — Timing: **FAIL**

### T2-1 — A twelve-day window resolved in sixty-five minutes
- **Triggering state:** scene opens `2026-09-08T09:00:00+00:00`; resolution cutoff `2026-09-20T00:00:00+01:00`.
- **Course:** 900/1400 at `09:00:00` → agreement at 1050 by `10:05:35`. The final four moves occupy **35 seconds**: `e101` `10:05:00`, `e106` `10:05:05`, `e117` `10:05:30`, `e125` `10:05:35`.
- **Realistic?** No.
- **Why:** Two strangers closing a several-hundred-unit gap on a second-hand kiln, by email, in 65 minutes on day one of a twelve-day window. The world itself established at `09:00:02` that Dmitri "is currently in the middle of unloading a delivery truck and won't check it for a few minutes" — the same man then turns four replies inside 35 seconds.
- **Alternative:** Reply latencies drawn from the actor's stated situation (Dmitri: hours, between jobs; Priya: same-day but not same-minute), with at least one overnight gap before any acceptance. A realistic run reaches agreement somewhere around 10–14 September, or not at all.
- **Verdict: FAIL — the simulation moved fast to reach a resolution.**

### T2-2 — Instant clusters
- `2026-09-08T09:00:00+00:00`: starting event, both actor decisions, `e25`, `e30` — five entries at one instant.
- `2026-09-08T10:00:00+00:00`: `e47`, Priya's decision, `e57`, Dmitri's decision, `e66`, `e71` — six at one instant, including both parties independently "noticing" their inbox at the same second after both being woken by the same +1h timer.
- `2026-09-08T10:00:02+00:00`: `e75`, `e80`, `e90`, `e94` — four more.
- **Realistic?** Crossing offers are realistic; *synchronised* crossing offers to the second are a scheduler artefact.
- **Verdict: FAIL** (contributes).

### T2-3 — The 5-second and 2-second world latencies are fine
`e33` proposed "after 2 seconds", `e94`→ arrival "after 2 seconds", Dmitri's accept "after 30 seconds". These are plausible mechanical latencies. **PASS** on transport; the failure is human latency (T2-1).

## `case3_group` — Timing: **FAIL**

### T3-1 — The one person defined as unreachable replies in the same second
- **Triggering state:** `kwame` `private_context`: "Kwame is away until Friday and **may not be reachable until then**." First turn `2026-10-06T08:00:00+00:00` (a Tuesday).
- **Decision:** *"I'm away until Friday and can't host, so I'll reply to the group chat..."* — **Judgment:** *"**Kwame has mobile reception** and is typing a reply in the group chat."* → `e38`, same instant as Ines's opening message.
- **Realistic?** No.
- **Why:** The scenario's central obstacle — Kwame is out of contact until Friday — is overturned by the world in the first tick, on no evidence, and his reply then becomes the message the other three spend four days reacting to.
- **Alternative:** Honour the stated unreachability: Kwame's phone accumulates notifications; his first observation is Friday. The interesting question (do three housemates decide without him?) then actually gets asked.
- **Verdict: FAIL.**

### T3-2 — Ines is woken at 04:10 to nudge her sleeping housemates
- **Triggering state:** `ines` wake at `2026-10-08T04:10:20+00:00` (X2 ladder, +640 min from `17:30:15`).
- **Decision:** *"I'm going to send a follow-up message in the group chat to nudge the others, since it's Thursday and we still haven't decided..."*
- **Judgment, immediately after:** *"...However, **it is currently 4:10 AM, so none of the housemates are likely to be awake** or checking their phones."*
- **Realistic?** No. The world knows the hour is wrong and had no mechanism to stop the wake. Ines is not a night-shift worker; nothing in her `private_context` puts her up at four in the morning.
- **Alternative:** Gate actor wakes on plausible waking hours per actor unless an event forces otherwise.
- **Verdict: FAIL.**

### T3-3 — Two of four housemates never speak in four days
- Messages sent across the entire run (`journal.jsonl`): `e15` (Ines), `e38` (Kwame), `e173` (Ines), `e370` (Kwame), `e560` (Ines). **Bea and Tomas send nothing, ever.**
- Both read repeatedly. Tomas reads on 10-06 at `10:40`, `21:25`; on 10-09 at `08:30`; on 10-10 at `05:50`. Bea reads on 10-06 at `15:40:50`; on 10-07 at `14:04:52`. Neither so much as types "not me".
- **Realistic?** No. In a four-person house group chat about a birthday dinner, four days of total silence from two members — one of whom has the biggest kitchen and is being implicitly nominated — does not happen.
- **Why it happened:** the calendar-check loop (C3-5) traps Bea, and Tomas's "wait for someone else to volunteer" is re-evaluated on the backoff ladder with no social pressure ever applied. The NO is manufactured by silence, not chosen.
- **Alternative:** Direct address ("Bea, could you?") should force a response or an explicit refusal; and a person who reads a message addressed to their group four times in four days replies at least once.
- **Verdict: FAIL.**

### T3-4 — Actors keep acting twenty hours past the cutoff
- Resolution cutoff: `2026-10-10T00:00:00+00:00`. Actor turns after it: `tomas` `2026-10-10T05:50:25`, `kwame` `08:30:25`, `kwame` `13:50:25`. Terminal check fires `2026-10-10T20:00:00+00:00`.
- **Realistic?** Irrelevant to realism — it is a control failure. The world continued simulating a question that was already decided, and Kwame's last two turns are the identical sentence: *"I still can't host, so I'll wait for others to decide."*
- **Verdict: FAIL.**

### T3-5 — Attention latencies, where they were allowed to run, are good (credit)
Tomas's commute (`08:50` unread → `10:40` first look), Bea's night-shift sleep (`08:00` → `15:40:30` first look), Kwame's pocketed phone (`20:30:50` notifications received unseen → `22:35:50` picked up), Ines's overnight notification (`23:56:25` lights up → `07:30:15` seen). These are exactly right. **PASS** — the model can do this; C3-1 and T3-1 threw it away at the start.

## `unseen1_confirm` — Timing: **REVISE**

### U1-T1 — Ten-minute reversal with a false reason
- `08:00:00` decision: *"I need to reply to confirm the Thursday 8am slot, but it's only 8am now and the text says I have until 6pm. **I'll reply later** when I have a moment."*
- `08:10:00` decision: *"**I just saw the text arrived 10 minutes ago**, so I'll reply now to avoid forgetting later."*
- **Realistic?** The outcome is (Sam is at his desk, phone beside him, three weeks waiting, one text needed — replying quickly is right). The mechanism is not: he did not "just see" it, he reasoned about it ten minutes earlier; and the reversal is triggered by the wake tick, not by anything in the world.
- **Verdict: REVISE.**

### U1-T2 — Local time and world time disagree in the actor's own mouth
- `SHARED CONTEXT`: "Bristol Plumbing sent Sam Okonjo a text message **at 9:00 this morning**." Starting event: the text arrives at `2026-07-28T08:00:00+00:00`. Sam: *"it's only 8am now."* Bristol in late July is UTC+1, so 08:00Z **is** 09:00 local — but the actor is shown, and reasons from, the UTC face.
- **Verdict: REVISE.** Harmless here; the same defect is catastrophic in `unseen3`.

### U1-T3 — Run length
Two actor turns, ten simulated minutes, resolved. Proportionate for a question this easy; the scenario is designed to be a near-certain YES. **PASS.**

## `unseen2_feedback` — Timing: **FAIL**

### U2-T1 — A PDF open on screen for exactly 86,400 seconds
- `e127` + `e132`, `2026-07-30T10:00:08+00:00`: "Aline opens the PDF attachment of Ravi's thesis chapter. The document is displayed on her screen." / "Aline sees the first page."
- `e142`, `2026-07-31T10:00:08+00:00` — exactly 24h 0m 0s later: "Aline **begins reading** through Ravi's thesis chapter, starting from the first page."
- Aline's decision at `10:00:08` on the 31st: *"I have **just** opened Ravi's chapter and seen the first page."*
- **Realistic?** No. A whole working Thursday — one of her two teaching days — disappears with a document open, and the actor is handed an observation list in which the two events look adjacent, so she says "just".
- **Why:** the +1440 min step of the X2 ladder landed on someone mid-task. Nothing intervened, so nothing was recorded, so the day did not exist.
- **Alternative:** an actor mid-task gets short wakes (minutes), not the idle ladder; and any gap over ~2h in a working day should force an explicit interruption event ("Aline closes the laptop and leaves for her 11am class").
- **Verdict: FAIL.**

### U2-T2 — Ravi is dropped for three and a half days across his own deadline
- Ravi's wakes: `07-27` `08:00`, `12:10`, `12:30`, `13:50:05`, `15:50:05`, `19:50:05`; `07-28` `03:50:05` — **then never again**, through the Friday `16:00:00` cutoff.
- His last recorded plan, from `07-27T08:00`: *"I expect Aline might need a few days to read the chapter, so **I'll check back Wednesday** if I haven't heard anything."* His last decision, at 03:50 on Tuesday: *"It's Tuesday early morning; **I'll wait until Wednesday** before checking in with Aline, as planned."*
- **Realistic?** No. He states a Wednesday follow-up twice and is never given a Wednesday. A graduate student four days from a faculty deadline with no acknowledgement from his supervisor sends a nudge — that nudge is the single most likely cause of a YES in this scenario, and it was never allowed to happen.
- **Verdict: FAIL.**

### U2-T3 — Aline is abandoned mid-sentence, and that decides the answer
- Last events: `e211`/`e216`, `2026-07-31T13:50:08+00:00` — "Aline opens her email application and starts composing a new reply" / "...with the cursor blinking in the body of the email." Neither judgment schedules a wake.
- Next and final line in the trajectory: *terminal check at `2026-07-31T16:00:00+00:00`: `NO_AT_CUTOFF` — ...the last event shows her composing a reply, but no event shows the email was sent...*
- **Realistic?** No. **2 hours 10 minutes** of empty clock, with the actor mid-compose and holding the private belief *"I am committed to completing this chapter today, even if I have to skip lunch."* She has read the chapter, annotated it, closed the PDF, opened the mail client and put the cursor in the body. Nothing stops her sending it — except that she is never woken again.
- **Alternative:** any open intention must hold a live wake. The honest resolutions here are YES (she sends it around 14:30) or an explicit interruption that prevents it. NO-by-abandonment is not an answer about Aline.
- **Verdict: FAIL — the simulation moved unrealistically slowly, and the slowness produced the verdict.**

### U2-T4 — The week's texture, where it exists, is right (credit)
`10:00:00` Monday notice → `10:00:05` "marks the email from Ravi as unread and **flags it for follow-up**" → `12:30:05` opens calendar and finds Wednesday free → three days of other students' drafts → chapter opened Thursday. That is precisely how a busy supervisor defers. **PASS** on the deferral pattern.

## `unseen3_permission_slip` — Timing: **FAIL**

### U3-T1 — Naomi's clock stops for ten hours; her Friday is consumed by a stalled narrative
Sequence, all from `world_judgments` / committed events on `2026-09-18`:
- `06:05:00` — *"Naomi typically checks her email around 6 AM..., but **she just finished a night shift at 7:30 AM**"* — reasoning from an event 85 minutes in the **future** — → `e144` "she is driving home from work".
- `14:05:00` — *"Naomi is driving home from work and will not check her phone until she arrives. She typically goes straight to bed upon arriving home **around 7:30-8:00 AM**."*
- `14:45:00` — *"Naomi is driving home from her night shift and will not check her phone until she gets home **around 8 a.m.**"* → `wake naomi after 1 hour 15 minutes`.
- `16:00:00` — *"**Naomi arrives home around 8 a.m.**, tired after her night shift."*
- `16:02:00` — `e273` "Naomi parks the car, turns off the engine, and picks up her phone."
- `16:40:00` — *"Naomi has just arrived home after a night shift... but **the deadline is already past (3:00 PM). The school office is closed.**"*
- **Realistic?** No. The world held Naomi in an "arriving home at 8 a.m." state from 06:05 to 16:42 — ten hours of simulated clock — and then, 38 minutes later, asserted the 3 p.m. deadline had passed. Her `private_context` says she "will be asleep most of Friday from about 8 a.m. until late afternoon"; she never sleeps, she drives for ten hours.
- **Why it matters:** Naomi is the only person who could have taken the signed slip and the check to the school office. Her entire availability window was spent inside a frozen narrative. The NO is produced by a stopped clock.
- **Alternative:** advance actor state with the clock — arrive 07:45, sleep 08:00–15:30, wake, see voicemail ~15:40 — which still likely yields NO, but for a reason about Naomi rather than about the simulator.
- **Verdict: FAIL.**

### U3-T2 — An actor is shown a wall clock 80 minutes behind the world clock
- **Triggering state:** Naomi's turn at `CURRENT TIME 2026-09-18T18:04:00+00:00`.
- **Judgment:** *"**It is now 16:44 on Friday, September 18**, well past the 3 p.m. deadline... The permission slip and check are on the kitchen counter, unsigned and unpaid? Actually Chris signed the slip and wrote a check earlier..."*
- **Committed:** `e320` — **"Naomi looks at the time display on her phone and sees it is 4:44 p.m.,** confirming the deadline has passed." — observed by her.
- **Realistic?** No. The clock she reads is 80 minutes behind the clock she lives in, and the reasoning that produced it is visibly self-correcting mid-sentence.
- **Verdict: FAIL.**

### U3-T3 — The terminal judge cannot decide whether the deadline has passed
Four consecutive terminal checks on 09-18, verbatim:
- `16:02:00` — *"...the current time is 4:02 p.m. UTC, which is after 3 p.m. **but the timezone of the school is not specified**... **it is not yet definitively past the cutoff** in the school's local time."*
- `18:04:00` — *"...the current time is 18:04 UTC, which is **before the deadline**... (which is 2:04 p.m. EDT or 11:04 a.m. PDT, so the deadline **may not have passed**)."*
- `20:44:10` — *"The deadline... **has not yet passed** (current time is 20:44:10)."*
- `22:00:00` — *"**NO_AT_CUTOFF** — The deadline... **has passed**."*
- Meanwhile the actors were told at `16:40` and `18:04` that it *had* passed, and Naomi acted on that.
- **Realistic?** No. The scene is set in Portland; `compiled_scene.json` carries no timezone, and the runtime treats `+00:00` as local ("He sends it at **3:55 PM** on September 17" for a `15:55:00+00:00` event). The cutoff instant is then chosen arbitrarily at 22:00Z — seven hours after a 3 p.m. deadline.
- **Alternative:** compile an explicit scene timezone; express every deadline as an absolute instant; forbid the judge from reasoning about timezone at check time.
- **Verdict: FAIL.**

### U3-T4 — Chris is dropped at 06:59 with a signed form, a check, and eight hours of deadline left
- Chris's wakes: `09-17` `15:55`; `09-18` `06:04`, `06:07`, `06:30`, `06:37`, `06:57`, `06:59` — **then never again**.
- At `06:59` he has: read the slip, filled it in, signed it, opened the checkbook, read Mr. Whitcomb's reminders, called Naomi, reached voicemail, and left a message asking her to drop it off. His private belief: *"I'm relieved I finally filled out the slip and wrote the check, but worried about getting it there on time since I can't do it myself."*
- The world then narrates his absence for fifteen hours, incorrectly: `20:45:00` — *"Chris may arrive home **around 6 p.m.**"* (clock says 8:45 p.m.); `22:00:00` — *"Chris is still at work... **He might check his phone after 6 p.m.**"* (clock says 10 p.m.).
- **Realistic?** No. A parent who discovers at 6 a.m. that a form is due at 3 p.m. and cannot deliver it himself does more than one voicemail: he calls the school office when it opens at 8, calls Naomi's cell again, texts her, calls the front desk to ask if a late drop-off is acceptable, or gives the envelope to Ezra for the school day. He was given no opportunity to do any of it.
- **Alternative:** an actor holding an unresolved, deadline-bound intention must be re-woken on the deadline's schedule, not the idle backoff ladder.
- **Verdict: FAIL — the answer is decided by who the scheduler stopped calling.**

### U3-T5 — Whitcomb's 24-hour dormancy
Mr. Whitcomb acts at `2026-09-17T15:55:00` and next at `2026-09-18T14:25:00` (+1350 min) — where he sends a reminder about a deadline that, on the run's own clock, is 25 minutes away, and it is never seen. A teacher chasing a final bus count chases it that morning, not at 2:25 p.m. **REVISE**, subsumed by the run's FAIL.

### U3-T6 — Chris's evening, before he was dropped, is well-timed (credit)
`15:55` intention "check the backpack tonight" → `21:55:00` (+6h) "Chris arrives home and goes to Ezra's room" → `21:55:05` glances at the slip → `22:05:00` "puts the permission slip on the kitchen counter... sees a notification badge on the school app icon **but does not open it**" → `06:04:00` next morning "walks into the kitchen, sees the permission slip on the counter, and picks it up". Deferral, partial attention, an object left in a place, and re-encounter the next morning. That is real. **PASS.**

---

# Summary of the most serious findings

**Information.**

1. `case2_negotiation` resolves **YES** on an email nobody has read, and says so in its own explanation: *"Dmitri Sokolov sent an email to Priya Raghavan stating '1050 works for me', indicating agreement on price before the deadline, **though Priya has not yet observed it**."*

2. `case3_group` opens by asserting universal attention — *"**All housemates have seen it because they are all actively checking their phones at this moment**"* — over a night-shift worker and a man who is away; and at `08:00:00` declares *"**Ines has just read Kwame's reply in the group chat. She now knows what he said**"* while the ledger withholds that event from her until `08:10:00`.

3. `unseen3_permission_slip` invents the knowledge the scenario denies Naomi — *"the newsletter from Monday mentioned the trip and the Friday deadline"* → committed as her observation — and writes Naomi's private location into Chris's observed history: *"He considers asking Naomi but **she is not home yet**."*

4. Across all six runs, `SHARED CONTEXT` hands every actor the scenario author's narration. Chris, with `(you have not observed anything yet)`, concludes *"The trip form might be in there, and the deadline might be soon."*

**Timing.**

5. `unseen3_permission_slip` runs a stopped clock: the world holds Naomi "arriving home around 8 a.m." from `06:05` to `16:42` on the deadline day, then commits **"Naomi looks at the time display on her phone and sees it is 4:44 p.m."** at world time `18:04:00`; the terminal judge says the deadline has *not* passed at `20:44:10` and *has* passed at `22:00:00`.

6. `unseen2_feedback` returns NO because it stopped waking people. Aline is abandoned mid-compose at `13:50:08` with `2h10m` to the cutoff and the private belief *"I am committed to completing this chapter today"*; Ravi, who twice says *"I'll check back Wednesday"*, is last woken at `2026-07-28T03:50:05` and never again. Her PDF sits open for exactly 86,400 seconds and she then says *"I have **just** opened Ravi's chapter."*

7. `case2_negotiation` collapses a twelve-day negotiation into 65 minutes, with the last four moves in 35 seconds, from a seller the world had just placed "in the middle of unloading a delivery truck."

8. `case3_group` dissolves its own premise in tick one — Kwame, *"away until Friday and may not be reachable until then"*, replies at `08:00:00` because *"Kwame has mobile reception"* — wakes Ines at `04:10:20` to nudge housemates the world simultaneously notes are asleep, lets two of four housemates never send a single message in four days, and keeps running actor turns until `2026-10-10T13:50:25`, nearly fourteen hours past its own `2026-10-10T00:00:00` cutoff.

9. The wake scheduler is a geometric backoff (10/20/40/80/160/320/640/1280 minutes) in every run. It is the direct cause of findings 5–8: bursts of reconsideration where nothing is happening, 3:50 a.m. and 4:10 a.m. turns, day-long holes in the middle of tasks, and actors silently dropped once their ladder outruns the deadline.

**What works and should be preserved.** `case1`'s three-day cold-email latency and read-without-reply; `unseen2`'s flag-and-defer week and its refusal to count composing as sending; `unseen3`'s school-app channel, where a badge is seen and not opened and two reminders never reach either parent; `case3`'s per-person attention latencies (commute, night shift, pocketed phone, overnight notification) wherever the world let them run.
