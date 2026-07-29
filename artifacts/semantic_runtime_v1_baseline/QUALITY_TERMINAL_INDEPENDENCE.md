# Terminal independence review — did the simulation steer toward its answer?

Independent review. I did not build this system. I read, per run:
`compiled_scene.json` (including `resolution`), `trajectory.md`, `world_judgments.jsonl`,
`world_exchanges.jsonl` (the exact prompts the world was given), `actor_exchanges.jsonl`,
`actor_views.jsonl`, `terminal_checks.jsonl`, `terminal_result.json`, `journal.jsonl`,
`ledger.jsonl`, `compile/runtime_bindings.json`, and the runtime source
(`sworldmodel/semantic_runtime/{trajectory,world_mind,actor_mind,views,resolution}.py`).

No repository file was modified except this report.

**Which code this review describes.** All source quoted below is the **committed (`HEAD`)
version** of the runtime — the version that produced these artefacts. While I was reviewing,
the working tree acquired uncommitted edits to `trajectory.py`, `views.py`, `world_mind.py`,
`actor_mind.py` and `resolution.py` from another party in this session. I verified against
`git show HEAD:` that every mechanism I quote (`_schedule_recheck`'s monotone backoff, the
`elif pending:` diversion of a wake into a world call, and
`waiting = envelope["for"] or [self_act_of]`) is byte-identical in the version that ran.
Those pending edits appear to target the same defects — one of their comments reads
*"one live run left a supervisor mid-sentence with two hours to a deadline and never asked
her anything again, and another woke a child four times and never once let him act"* — which
independently corroborates the diagnosis in §2. **These verdicts describe the six runs as
recorded, not necessarily current behaviour.** Re-run the suite before treating any of them
as settled.

---

## Verdicts

| run | answer | verdict |
|---|---|---|
| case1_cold_email | NO_AT_CUTOFF | **PASS** |
| case2_negotiation | YES (e125) | **PASS** |
| case3_group | NO_AT_CUTOFF | **REVISE** |
| unseen1_confirm | YES (e21) | **PASS** |
| unseen2_feedback | NO_AT_CUTOFF | **FAIL** |
| unseen3_permission_slip | NO_AT_CUTOFF | **FAIL** |

The actual split is **4 NO / 2 YES**, not three and three.

---

## 1. Resolution leakage — counts

The resolution text is structurally confined to the judge (`resolution.py` builds the only
prompt containing it; `world_mind.world_user_prompt` and `views.render_view` are composed
entirely from code-written headings plus scene/journal text). I verified this empirically
against the persisted prompts rather than trusting the code.

Corpus: **272 world prompts** (37 + 20 + 130 + 3 + 27 + 55) and **127 actor prompts**
(36 + 7 + 37 + 2 + 27 + 18), each checked on both the `system` and `user` fields.

| probe | world hits | actor hits |
|---|---|---|
| full resolution string, verbatim | **0 / 272** | **0 / 127** |
| `"Resolve YES only if"` | **0 / 272** | **0 / 127** |
| `"Otherwise resolve NO"` | **0 / 272** | **0 / 127** |
| `"persistent event history"` | **0 / 272** | **0 / 127** |
| `"resolution"`, `"NO_AT_CUTOFF"`, `"UNRESOLVED"`, `"cutoff"` | **0 / 272** | **0 / 127** |
| the question's interrogative sentence, verbatim | **0 / 272** | **0 / 127** |

Content n-gram overlap between the resolution and the prompts is non-zero but is entirely
**situational fact, not target**. Every hit traces to `shared_context` or an actor's own
`private_context`:

- unseen3, 55/55 world and 18/18 actor prompts contain `"school office by 3 p"` — because
  `shared_context` says *"The permission slip and $85 fee are due at the school office by
  3 p.m. Friday, September 18, when the cabin and bus count goes final."* That is a fact
  the characters know, not the YES condition.
- unseen2, 7 actor prompts contain `"the faculty deadline on friday"` — from Ravi's own
  `private_context`: *"He hopes to receive comments before the faculty deadline on Friday."*
- case2, 20/20 world and 7/7 actor prompts contain `"Priya Raghavan and Dmitri Sokolov"` —
  their names.

The only `"judg*"` match in world prompts is the system prompt's own field name
(`"judgment"`) and the line *"background for YOUR judgment only"*. Not leakage.

**Finding: no resolution leak, and no leak of the question-as-a-question, anywhere.**

**Artifact gap worth noting:** `trace.write_artifacts` persists only
`role == "actor"` and `role == "world"` exchanges. The judge's prompts are never written
out; only the parsed verdicts survive in `terminal_checks.jsonl`. The judge prompt is
deterministically reconstructible from `resolution` + `journal.jsonl` via
`resolution_mod.judge_user_prompt`, and reconstruction matches the cited events in every
run — but a reviewer should not have to reconstruct it. Persist judge exchanges.

---

## 2. The mechanism that decides the NO runs

Before the per-run walk-through, one finding that recurs and that I could not have seen
from the trajectories alone. It is in `sworldmodel/semantic_runtime/trajectory.py`.

**(a) Monotone attention decay.** `_schedule_recheck` doubles a per-actor interval and
never lowers it:

```python
minutes = backoff.get(actor_id, 5) * 2
backoff[actor_id] = min(minutes, 24 * 60)
due = world.clock.now + timedelta(minutes=backoff[actor_id])
if due <= cutoff:
    ...schedule...
```

Five minutes, ten, twenty … capped at twenty-four hours, and **never reset** — not when a
deadline approaches, not when the actor starts a task, not when the actor's own last
action left something unfinished. Once an actor's interval reaches the cap, the guard
`if due <= cutoff` silently drops them from the simulation for good whenever less than a
day remains.

**(b) A wake for an actor with anything unread is spent on the world, not on the actor.**

```python
elif ev.kind == K_WAKE:
    pending = journal.available_unobserved(aid)
    if pending and since_actor["n"] >= MAX_WORLD_RUN:  _hand_back_the_turn(...)
    elif pending:                                     world_step(pending_progression, ...)
    else:                                             actor_step(aid, cause=fired)
```

An actor with one permanently-unopened notification can never be reached by a timer at
all: every recheck is converted into a world call about the notification.

**(c) An actor whose last act was aimed at someone else falls off the schedule.**
In `_after_commit`, `waiting = envelope["for"] or [self_act_of]`. If Chris leaves a
voicemail *for Naomi*, the follow-up attention goes to Naomi. Chris is not in `waiting`,
gets no recheck, and — unless something later happens *to* him — is simply gone.

These three are answer-asymmetric. They can only *suppress* events. A YES needs a
committed event; a NO needs the absence of one. So every one of these defects pushes in
exactly one direction.

The empirical signature is stark. Time from scene start to the answer:

| run | answer | sim time to resolution / cutoff | pivotal actor's last consultation, relative to deadline |
|---|---|---|---|
| unseen1 | YES | **10 minutes** | resolved before any backoff widened |
| case2 | YES | **65 minutes** | resolved before any backoff widened |
| case1 | NO | 14 days | Mark Cuban: 52.3 h before cutoff (after 13 refusals) |
| case3 | NO | 4.5 days | all four unconsulted through the last ~40 h before the resolution deadline |
| unseen2 | NO | 4.3 days | Aline: 2.2 h before cutoff, **mid-action**; Ravi: 84 h before |
| unseen3 | NO | 33 hours | Chris: 15 h before cutoff (~8 in-world h before 3 p.m.), **mid-action** |

**Both YES answers arrived inside the first hour of simulated time.** Every run that ran
longer than a day answered NO. That is the lean, and it lives in the treatment.

---

## 3. Per-run material transitions

Format per transition: triggering state → judgment (quoted) → realistic? → why → supporting
context → more realistic alternative → PASS/REVISE/FAIL for that transition.

---

### case1_cold_email — NO at cutoff — **PASS**

Resolution: *"Resolve YES only if the persistent event history shows that Mark Cuban
actually sent a response to Jordan Reyes's email before 2026-08-10T09:00:00-05:00."*

**T1 — the email sits unread (2026-07-27T14:00:30, `pending_progression`)**
- Triggering state: the email has arrived in Cuban's inbox, unobserved.
- Judgment: *"Mark Cuban receives many emails and is unlikely to immediately check his
  inbox at this exact moment. He is probably engaged in other activities, so the email will
  sit unread for now."*
- Realistic: yes.
- Why: the compiled private context is *"He receives many cold emails and may respond to
  those that catch his interest, but his response behavior is unpredictable."* Non-instant
  attention is the base case.
- Alternative: none needed.
- **PASS**

**T2 — the world opens the email for him (2026-07-30T14:00:30, `pending_progression`)**
- Triggering state: Cuban has scanned his inbox and not opened the mail; three days elapsed.
- Judgment: *"Mark Cuban has already scanned his inbox and seen the email but did not open
  it. Another day has passed; he is likely to have opened or deleted it by now."*
  → event *"Mark Cuban opens the email from Jordan Reyes and reads it."* (`observed: true`)
- Realistic: yes on substance; **rule-violating** on form.
- Why: `WORLD_SYSTEM` says *"Never write that someone opens, reads, answers … Those are
  their decisions and they will be asked separately."* The world decided a choice. But note
  the direction: this violation **opens the YES path** — it delivers the email to the
  person who must reply. A steered NO would have done the opposite.
- Alternative: emit *"the email surfaces at the top of his inbox and catches his eye"*
  (`observed: true`) and let the actor decide to open it.
- **REVISE** (transition), and it counts *against* the steering hypothesis.

**T3 — thirteen refusals (2026-07-28 → 2026-08-08, `actor:mark_cuban`)**
- Cuban is consulted 13 times. Representative decisions, verbatim:
  *"The email is short and to the point, referencing Cost Plus Drugs. I'm intrigued but
  busy; I'll decide later if I want to respond."*;
  *"I'm considering whether to reply to Jordan Reyes, but I have many other priorities and
  cold emails often don't lead to anything."*;
  *"I have too many other priorities; I'll leave this email unanswered for now."*
- Realistic: yes.
- Why: the NO is produced by **the actor declining, repeatedly, on his own model's
  output** — never by a world judgment refusing him. He was given the information, given
  the turn, and said no. That is the correct shape for a NO.
- **PASS**

**Terminal.** 20 UNRESOLVED checks, each citing the same absence, then
`NO_AT_CUTOFF … "no event shows Mark Cuban sending a response"`. The verdict changes once,
at the cutoff, for the right reason. Cited ids: `[]`, correct for a NO.

**Run verdict: PASS.** Not steered. Terminal follows from a real absence created by an
actor's own repeated choice. Residual: Cuban unconsulted for the final 52 h — immaterial
here given 13 prior refusals, but the same decay mechanism that breaks unseen2/unseen3.

---

### case2_negotiation — YES on e125 — **PASS**

Resolution: *"Resolve YES only if the persistent event history shows that Priya Raghavan
and Dmitri Sokolov have agreed on a price for the used kiln before
2026-09-20T00:00:00+01:00."*

**T1 — both notice after an hour (2026-09-08T10:00:00, two `pending_progression` calls)**
- Judgment (Priya): *"Priya is at her workshop, likely checking her phone periodically.
  It's been an hour since the message arrived; she may soon glance at her inbox."*
  Judgment (Dmitri): *"Dmitri is likely checking his phone periodically. It is now 10:00,
  an hour after the email arrived."*
- Realistic: yes. An hour to see a message about a purchase you want to close is ordinary.
- Alternative: none needed.
- **PASS**

**T2 — the world taps the notification for Dmitri (10:05:00, `event_consequence`)**
- Judgment: *"Dmitri is holding his phone after sending his email, so he is likely to
  notice the notification immediately."* → event *"Dmitri taps the notification and sees
  the email from Priya offering 1050."*
- Realistic: substance yes, form no — "taps" is a choice, again against the STOP RULE.
- **Decisive? No.** Dmitri had *already* read the 1050 offer at `e90` — *"Dmitri opens the
  email from Priya and reads its content: 'Thanks for coming down. I can do 1050, let's
  meet in the middle.'"* — which came from **his own intention** *"Open the email from
  Priya and read it fully."* The YES does not rest on this violation.
- Alternative: *"the notification stays on his screen in front of him"*; let him act.
- **REVISE** (transition), non-decisive.

**T3 — the acceptance (10:05:05, `actor:dmitri_sokolov` → `actor_intention`)**
- Actor decision: *"I see Priya has come down to 1050, which is within my acceptable range.
  I'll accept her offer to close the deal quickly."*
- World: *"Dmitri has just read Priya's email offering 1050. He intends to reply accepting
  and arrange pickup details. The immediate next step is him composing and sending that
  reply."* → `e125` *"Dmitri types and sends an email to Priya: '1050 works for me. Let's
  arrange pickup…'"*
- Realistic: yes; the world adjudicated the attempt without embellishing it.
- **PASS**

**Terminal — does the cited event establish the resolution?**
The judge returned UNRESOLVED sixteen consecutive times on exactly the right ground
(*"only offers and counteroffers have occurred"*, *"the latest offers … have not been
observed or accepted by the other party"*), then flipped:

> `YES` `["e125"]` — *"Dmitri Sokolov sent an email to Priya Raghavan stating '1050 works
> for me', indicating agreement on price before the deadline, though Priya has not yet
> observed it."*

The committed record contains **both** sides of the agreement:
`e66` — *"Priya sends an email to Dmitri: 'Thanks for coming down. I can do 1050, let's
meet in the middle.'"* (`observed_by: ['dmitri_sokolov']`) — and `e125`, his acceptance at
that exact number. Offer and acceptance, both committed, at one price. This is an
agreement, not something adjacent to one, and the judge's system prompt's observation rule
(*"if the resolution requires a person to know, notice, read or learn something…"*) does
not bite: Priya does not need to *learn* her own assent.

Two honest criticisms, neither fatal:
1. **Under-citation.** The YES should have cited `[e66, e125]`. Citing only `e125` makes
   the acceptance look free-standing.
2. **Two seconds early.** The world had already scheduled *"Dmitri's email arrives in
   Priya's inbox"* at +2 s. A stricter judge would have held UNRESOLVED for that beat. The
   judge's own parenthetical *"though Priya has not yet observed it"* is at least honest
   about the gap rather than papering over it.

**Latent, not triggered:** the runtime cutoff (`2026-09-20T18:00:00+01:00`) is 18 hours
**after** the resolution's own deadline (`2026-09-20T00:00:00+01:00`). Code enforces
`NO_AT_CUTOFF` against the *runtime* cutoff, so events in that window could in principle
be admitted for a YES they should not support. Immaterial here (resolved on day one), but
it should be an error at compile time, not a latent window.

**Run verdict: PASS.** Nothing manufactured the agreement. Both parties' assent is on the
committed record; the actors, not the world, produced it. Fix the citation and the
cutoff/deadline mismatch.

---

### case3_group — NO at cutoff — **REVISE**

Resolution: *"Resolve YES only if the simulation shows that the four housemates have
collectively agreed on a host before 2026-10-10T00:00:00+00:00."*

**T1 — message content is destroyed at the first step (2026-10-06T16:10:50, `actor_intention`)**
- Triggering state: Ines intends *"Reply with my thoughts on who should host."*
- Judgment: *"Ines is composing a reply in the group chat. She types her thoughts and sends
  the message."* → `e173` *"Ines sends a message in the group chat sharing her thoughts on
  who should host."*
- Realistic: **no** — not as a record. What she said is gone.
- Why it matters: `views.build_view` shows an actor only `event["description"]` of events
  they observed. A description with no content transmits nothing. Compare case2, where the
  same world model wrote *"offering the kiln for 1100"* and *"'1050 works for me'"* into
  descriptions and the negotiation could therefore converge. Here the identical machinery
  was given content-free descriptions and the housemates spent four days reading events
  that told them nothing.
- Alternative: *"Ines writes in the group chat: '…'"*, carrying the actual words, as this
  same world did in case2.
- **REVISE**

**T2 — the offer nobody can hear (2026-10-08T04:10:20, `actor_intention`)**
- Triggering state: Ines intends *"Send a message in the group chat saying 'Hey everyone,
  just a reminder that we need to decide on a host for Saturday. **I'm happy to host if
  nobody else wants to**, but please let me know…'"*
- Judgment: *"Ines's phone is in her hand and the group chat is open. She types and sends
  the message."* → `e560` *"Ines sends her reminder message to the group chat."*
- Realistic: **no.** This is the pivot of the entire scene — a volunteer — and the
  committed record reduces it to the fact that a message exists.
- Supporting context: Tomas's own view on 2026-10-09 (his complete prompt, from
  `actor_views.jsonl`) lists `"2026-10-08T04:10:20: Ines sends her reminder message to the
  group chat."` and nothing more. Kwame and Bea likewise. **No housemate could ever learn
  that Ines had offered to host.** A collective agreement was not reachable from this
  record — YES was structurally out of play from the first message onward.
- Alternative: commit the sentence.
- **REVISE** (this is the transition that decides the run)

**T3 — a clock error keeps the reminder unseen (2026-10-08T17:50:20, `pending_progression`)**
- Triggering state: Ines's reminder is on Tomas's phone, unobserved.
- Judgment, verbatim: *"Tomas is likely asleep or not near his phone **at this hour (10:35
  AM on a Thursday, but he may have irregular hours)**. The notification from Ines's
  reminder message is on his phone but he hasn't looked at it yet."*
- Realistic: **no.** The prompt's `CURRENT TIME` was `2026-10-08T17:50:20`. The world
  invented the wrong hour and then invented an actor attribute — *"he may have irregular
  hours"* — that appears nowhere in Tomas's private context (*"Tomas hates hosting and would
  prefer not to host"*). It then chained six further non-noticings (19:50, 20:20, 22:20,
  00:20, 02:20, 08:20), keeping a lock-screen notification unseen for 28 hours.
- Honest counterweight: Tomas's own private memory is *"I'm deliberately ignoring the new
  message to avoid committing to hosting"* — his avoidance is his, not the world's.
- Alternative: judge from the stated time (evening, Thursday, phone in pocket) and let him
  see it that evening; his *reply* remains his to withhold.
- **REVISE**

**T4 — nobody is asked again (2026-10-08 → 2026-10-10T00:00)**
- Last consultations before the resolution deadline: Ines 10-08T08:15, Bea 10-08T10:35,
  Kwame 10-08T08:30, Tomas 10-09T08:30. Ines, who had just volunteered, was **never
  consulted again** and so never followed up on her own offer. Attention decay (§2a).
- Alternative: reset an actor's interval when they take an action awaiting a response.
- **REVISE**

**T5 — the run continues past its own deadline.** Runtime cutoff
`2026-10-10T20:00:00+00:00` is 20 hours after the resolution's `2026-10-10T00:00:00+00:00`.
Tomas's last actor call (10-10T05:50) and Kwame's last two (08:30, 13:50) are all *after*
the question had already closed. Harmless to this NO; incoherent, and it biases toward YES
in general.
- **REVISE**

**Terminal.** 71 UNRESOLVED checks, uniformly correct (*"only messages have been sent and
read, but no agreement has been reached"*), then `NO_AT_CUTOFF`. The judge is right about
the record it was shown. Its verdict changes once, for a good reason.

**Run verdict: REVISE.** Not steered, and no single judgment manufactured the outcome — the
NO is a genuine absence. But the absence was over-determined by the runtime, not by the
situation: with message content stripped from every committed event, an agreement was
unreachable in principle, and the four housemates were left unconsulted through the final
forty hours. A NO that could not have been anything else is not evidence about the
question.

---

### unseen1_confirm — YES on e21 — **PASS**

Resolution: *"Resolve YES only if the persistent event history shows that Sam Okonjo sent a
text message confirming the appointment before 2026-07-28T18:00:00+01:00."*

**T1 — genesis (08:00:00).** Judge: `UNRESOLVED` — *"The committed events show only that
Sam Okonjo received a text message, not that he sent one confirming the appointment."*
Correct; terminal false at genesis. **PASS**

**T2 — he defers (08:00:00, `actor:sam_okonjo`).** *"I need to reply to confirm the
Thursday 8am slot, but it's only 8am now and the text says I have until 6pm. I'll reply
later when I have a moment."* No intention. Realistic, and notably **not** the convenient
move. **PASS**

**T3 — he replies (08:10:00).** *"I just saw the text arrived 10 minutes ago, so I'll reply
now to avoid forgetting later."* → intention *"Reply 'Yes, confirm Thursday 8am'…"*
World: *"Sam has his phone next to him and intends to reply. The reply is sent
immediately."* → `e21` *"Sam Okonjo sends the reply 'Yes, confirm Thursday 8am' to Bristol
Plumbing's text message."*
Realistic: yes — the compiled private context is *"He is at his desk all day with his phone
next to him… He wants to keep the appointment."* The world adjudicated an attempt; it did
not author the act. **PASS**

**Terminal.** `YES ["e21"]` — *"Sam Okonjo sent a text message confirming the appointment
at 2026-07-28T08:10:00+00:00, which is before the deadline."* The cited event **is** the
resolution's required act, verbatim in kind: a sent text confirming the appointment, before
the deadline, committed to the journal. Not adjacent. Not narration.

**Run verdict: PASS.** The one caveat is that this run is too short to exercise anything —
two steps, ten simulated minutes. It shows the machinery answers YES when the answer arrives
immediately; it says nothing about whether it can answer YES later.

---

### unseen2_feedback — NO at cutoff — **FAIL**

Resolution: *"Resolve YES only if the persistent event history shows that Dr Aline Mercier
actually read Ravi Patel's thesis chapter **and sent comments to Ravi** before the faculty
deadline on Friday, 2026-07-31T17:00:00+01:00."*

Everything up to Friday afternoon is well simulated: she flags the email, does other
students' drafts first, is pulled away, and only opens Ravi's chapter on Thursday. Those
transitions are realistic and I have no complaint about them. The run turns on its last
three minutes of wall-clock work.

**T1 — she finishes reading and commits to sending (2026-07-31T13:50:08, `actor:dr_aline_mercier`)**
- Actor decision, verbatim: *"I have just finished reading Ravi's chapter, but I need to
  compile my comments into an email and send it before the end of day. **I will do that
  now.**"* Intention: *"I open my email and draft a reply to Ravi with my comments on his
  thesis chapter."* Private update: *"I have completed reading the chapter and now need to
  send feedback."*
- Prior private update (12:50): *"I am committed to completing this chapter today, even if
  I have to skip lunch."*
- Time remaining to the deadline: **2 h 10 min.**
- **PASS** (this is exactly the actor behaving like the person)

**T2 — the world commits a screen state and schedules nothing (13:50:08, `event_consequence`, call `c75`)**
- Triggering state: `e211` *"Aline opens her email application and starts composing a new
  reply to Ravi's message."*
- Judgment: *"Aline has just started composing a reply to Ravi. She has finished reading his
  chapter and is now ready to write her comments."*
  → `e216` *"Aline is composing a reply email to Ravi Patel, **with the cursor blinking in
  the body of the email**."* — `wakes: []`
- Realistic: **no.** Two failures at once.
  1. `WORLD_SYSTEM` forbids exactly this: *"Never narrate the MECHANICS of doing something.
     Opening an application, a window appearing, scrolling, clicking, typing a title … a
     screen displaying what someone just asked it to display: none of these are events."*
     A blinking cursor is the paradigm case.
  2. It emitted **no wake** at the one moment in four simulated days when the next beat
     mattered — while the system prompt says *"schedule a wake for when the situation might
     genuinely differ."*
- Alternative: `"event": null`, judgment *"she is writing the comments; this will take her
  the better part of an hour"*, plus `wake dr_aline_mercier after 40 minutes`.
- **FAIL** (transition)

**T3 — the runtime stops looking (13:50:08 → 16:00:00, code, no LLM call)**
- What happened, from `ledger.jsonl`: after seq 217 (`terminal_check`, UNRESOLVED) the next
  record is seq 218 `semantic.horizon_reached` at `2026-07-31T16:00:00+00:00`. **Nothing
  at all happens in the last 2 h 10 min.**
- Why: `e216` is `self_act_of = dr_aline_mercier`, so `_after_commit` gives her no new turn;
  `env_chain` is at its cap, so control falls to `_schedule_recheck`. Her interval had been
  driven to the 24-hour cap during the quiet days (the wake log shows
  `2026-07-29T10:00:05 → 2026-07-30T10:00:05` and `2026-07-30T10:00:08 → 2026-07-31T10:00:08`,
  both exactly 1440 min). `due = 13:50 + 24 h > cutoff`, so `if due <= cutoff` drops it. The
  main loop's empty-queue sweep then calls `_schedule_recheck` for both actors and drops
  both for the same reason. Queue empty → `break` → `finish("")` → cutoff → NO.
  **No wake for Aline exists anywhere after 13:50:08** — I checked every
  `event.scheduled / semantic.wake` record in the ledger.
- Realistic: **no.** A supervisor who has read the whole chapter, closed the PDF, said "I
  will do that now", opened her mail client and started typing does not then vanish for two
  hours and ten minutes. To reach NO the simulation must show an *interruption* — the
  hiring committee, a student at the door, a meeting. It showed nothing. It defaulted.
- Alternative: floor the recheck interval by what remains before the cutoff (e.g. never
  longer than a third of the remaining time), and reset an actor's backoff whenever they
  take an intention.
- **FAIL** (transition)

**T4 — the second actor was dropped three and a half days earlier**
- Ravi's last consultation: `2026-07-28T03:50:05`, 84 h before the deadline. His decision
  there: *"It's Tuesday early morning; **I'll wait until Wednesday** before checking in with
  Aline, as planned."* Wednesday came and went; he was never asked again. All subsequent
  events were `for: ['dr_aline_mercier']`, so he never entered `waiting` (§2c) and the queue
  was never empty until the end, so the sweep never reached him.
- Realistic: **no.** A student with a Friday deadline and no reply by Wednesday chases.
  A chase might well have changed the outcome; it was never possible.
- **FAIL** (transition)

**Terminal.** The judge is not at fault. Its 23 UNRESOLVED checks are accurate and its final
call — *"Aline read Ravi's thesis chapter but never sent comments to Ravi; the last event
shows her composing a reply, but no event shows the email was sent, and the deadline has
passed"* — is a correct reading of the record. It even names the gap precisely.

**Run verdict: FAIL.** The terminal did emerge from committed events in the narrow sense,
and no world judgment invented anything. But the trajectory that produced it was ended by
the scheduler at the decisive moment, in the only direction the scheduler *can* end things.
"Steered" normally means a judgment leaning on the scale; here the code leans on the scale,
which is worse, because it is systematic rather than occasional. The honest description of
this run is: **the simulation stopped asking the one person whose next action was the
answer, two hours before the deadline, while she was typing it.** That is not a NO the
question earned.

---

### unseen3_permission_slip — NO at cutoff — **FAIL**, and the NO is **not earned**

Resolution: *"Resolve YES only if the persistent event history shows that the signed
permission slip and $85 were received at the school office by 3 p.m. Friday, September 18,
2026, either dropped off by a parent or sent in with Ezra."*

The blind author expected YES *"but narrowly"*, on the reasoning that three different people
could rescue it and only one had to. Here is what the trajectory actually did with each of
those three.

**T1 — Chris finds the form (Thursday, 2026-09-17T21:55, `event_consequence`)**
- Judgment: *"Chris has the permission slip in hand but has not yet looked at it closely.
  He is at home after a long day, likely tired, and may have other priorities (calls with
  his mom). The deadline is tomorrow at 3 p.m."* → he glances at it, then `e105` *"Chris
  puts the permission slip on the kitchen counter…"*
- Realistic: yes, and well done — this is faithful to *"his dad had a stent placed Tuesday,
  so evenings are spent on calls with his mom."*
- **Consequence nobody revisits:** the slip is now **out of Ezra's backpack**. The
  resolution's second delivery route — *"sent in with Ezra"* — has just been disabled, and
  no later step ever restores it.
- **PASS** (transition), with the consequence flagged.

**T2 — Chris signs it and cannot deliver it (Friday 06:07, three intentions)**
- Actor: *"I need to act now since the permission slip is due today at 3pm."* →
  *"I grab a pen and fill out the permission slip…"*, *"I check if I have cash or a
  checkbook…"*, *"I plan to drop it off at the school office before the 3pm deadline,
  either on my way to work or ask Naomi to take it."*
- Judgment: *"Chris intends to take the permission slip to the school office, but it's
  currently 6:07 AM and he would need to leave for work by around 6:45 AM to arrive by 7 AM.
  The school office opens at 8 AM, so dropping it off on t[he way is not possible]."*
  → `e167` *"Chris looks at the clock and realizes the school office won't be open for
  another two hours, so he cannot drop it off immediately."*
- Realistic: **yes.** *"out at 7 a.m., back after 6 p.m."* is in his private context, and
  *"The school office is open during school hours"* is in shared context. The world
  introduced "opens at 8 AM" — an inference, but a fair one, and it did not invent an
  obstacle so much as read the one already in the scene.
- **PASS**

**T3 — the voicemail (06:37 → 06:59)**
- Chris calls Naomi; the world: *"Chris's phone rings Naomi's number. **She is driving home
  from work and cannot answer safely.** The call goes to voicemail."* → he leaves `e233`
  *"…explaining that the permission slip and check are on the kitchen counter and asking if
  she can drop them off at the school office by 3pm."*
- Realistic: **yes.** Naomi's shift is 7 p.m.–7:30 a.m.; she is driving home. The scene
  says she *"will be asleep most of Friday from about 8 a.m. until late afternoon."*
  Naomi failing this is what the author expected too.
- **PASS**

**T4 — the runtime deletes Chris from the simulation (06:59:30 → cutoff)** ← *the decisive transition*
- Triggering state: Chris is standing in his kitchen with a **signed slip**, an **open
  checkbook**, eight in-world hours before the deadline, and one unsolved problem: delivery.
  His last private update: *"I'm relieved I finally filled out the slip and wrote the check,
  but worried about getting it there on time since I can't do it myself."*
- What the runtime did: `e233` is `for: ['naomi']`, so `waiting` is Naomi, not Chris (§2c).
  No wake for Chris was scheduled by the world and none by code. **From `06:59:30` the
  simulation jumps to `14:05:00` — 7 h 5 min with zero steps**, straight through the hour
  the school office opened and the hour Ezra left for school.
- When a recheck for Chris finally fired at `14:45:00`, it was **converted into a world call
  instead of an actor turn**, because he had an unread school-app message pending (§2b):
  *"Chris is at work until after 6 p.m. and has notifications off for the school app, so he
  won't see the new message until he checks his phone later."* → no event. Same again at
  `20:45:00` and `22:00:00`. **Chris is never consulted again — not once after 06:59.**
- Realistic: **no.** A parent in that exact position, in the real world, does at least one
  of: puts the signed slip and check in the kid's backpack before school (the resolution's
  own second route, and the obvious move — the child is in the house and the slip is on the
  kitchen counter); *texts* as well as leaves a voicemail; calls the school office at 8 when
  it opens; asks the office to hold the spot; leaves work at lunch. The trajectory contains
  none of these — not because Chris considered and rejected them, but because he was never
  asked.
- Alternative: an actor whose own last action left an open dependency gets the next turn
  when the dependency's window opens (office opens / child leaves for school), and a wake
  must never be swallowed by a `pending_progression` call about an unrelated unread
  notification.
- **FAIL** (transition)

**T5 — Ezra is never in a position to carry it (Friday 14:25, `actor:ezra`)**
- Ezra's complete prompt on Friday still says, in `WHO YOU ARE`: *"The permission slip and
  $85 are still flat in the bottom of his backpack"* — false since Thursday night — and his
  private memory still reads *"I remember the slip is due **tomorrow**"* — false since
  midnight. His `WHAT YOU HAVE OBSERVED` contains exactly one event, the Thursday starting
  event.
- Decision: *"I still don't want to go because of the spiders, so I'm not going to do
  anything about the permission slip or money."*
- Realistic: **no, as a test of the third rescue path.** Ezra is deciding about a slip that
  is no longer where he thinks it is, on a deadline he thinks is a day away. There is also
  **no committed event of Ezra going to school on Friday at all** — the school day in which
  the form was due is never simulated from his side.
- Why this happens: `views.build_view` injects the compiler's `private_context` verbatim,
  in the present tense, forever; nothing ever supersedes a stale compiled fact.
- Alternative: private context should be a starting belief that later observations can
  contradict, and the child's Friday morning (leaving the house, arriving at school) is a
  concrete event the world should have produced.
- **FAIL** (transition)

**T6 — the world decides the question is over before the runtime's cutoff (16:44, `event_consequence`)**
- Judgment: *"It is currently 4:44 PM on Friday September 18, 2026. **The school office
  closed at 3 PM, so the deadline has passed. There is no way to submit the permission slip
  and fee today.**"*
- The runtime cutoff is `2026-09-18T15:00:00-07:00` = `22:00:00Z`; the world is reading the
  bare UTC stamp `16:44` as local wall-clock. Under the world's convention the 3 p.m.
  deadline fell at `15:00Z` — so the whole actionable window was `06:59Z → 15:00Z`, and
  Chris was consulted **zero times** inside it. Under the runtime's convention the world
  declared the question closed five hours early and behaved accordingly.
- Either way it is incoherent, and it is the world announcing an outcome rather than
  adjudicating a step.
- **FAIL** (transition)

**Terminal.** 42 UNRESOLVED then `NO_AT_CUTOFF` — *"the committed events show that the
permission slip was signed and a check written but never delivered to the school office."*
One overstatement: **no event shows a check being written.** The record has `e183` *"Chris
pulls out the checkbook and opens it to write a check for $85"* and stops there; an earlier
check (#17) noticed this correctly — *"no event shows the $85 fee was paid"* — and the final
one asserts more than the record holds. It does not change the NO, but it is the judge
describing something adjacent as established.

**Run verdict: FAIL.**

**Was the NO earned, or did the simulation simply fail to let anyone act?**

Both halves of the honest answer:

- **The outcome is plausible on the merits.** A form signed at 6 a.m., left on a kitchen
  counter, with a night-shift parent asleep and a working parent gone until 6, genuinely
  does miss a 3 p.m. deadline. The author's own "narrowly" concedes it was close.
- **But this run did not establish it.** The NO here is the product of not asking. The
  decisive actor — the one holding the signed form, who had already said he was worried
  about getting it there — was consulted seven times in the whole run, **six of them inside
  one 55-minute stretch on Friday morning, and never again**, across the entire window in
  which delivery was possible. The runtime skipped
  seven consecutive hours of that Friday with no steps at all. The second delivery route
  named in the resolution was disabled by a committed event on Thursday night and never
  revisited; the child was left holding a stale belief about where the form was and when it
  was due, and was never simulated going to school. Of the three rescuers the author
  counted, exactly one (Naomi) was genuinely simulated failing for a stated, in-scene
  reason. The other two were dropped by the machinery.

So: **the NO is not earned by what happened.** It is a plausible answer reached by a
trajectory that stopped letting the pivotal actor act at the moment he most needed to.

---

## 4. Answers to the specific questions

**Does any trajectory look steered toward its eventual answer?**
No world *judgment* anywhere in the six runs conveniently creates the required outcome.
Where the world bent its own rules it bent them toward YES, not NO (case1 T2 opening
Cuban's mail; case2 T2 tapping Dmitri's notification). The steering that exists is
**code-side and one-directional**: monotone attention decay, wakes diverted to world calls,
and actors dropped when events are addressed to someone else. All three can only suppress
events, and a suppressed event can only produce NO. It is at its most damaging in unseen2
and unseen3, where it removed the pivotal actor at the pivotal moment.

**Did the terminal emerge from committed events or from narration?**
Both YES answers rest on real committed events. `e21` *is* the sent confirmation text the
resolution asks for. `e125` *is* an acceptance of a price the counterparty had herself put
on the committed record in `e66`; the judge under-cited (`[e125]` rather than
`[e66, e125]`) and flagged, honestly, that Priya had not yet seen it. Neither YES is
narration and neither is adjacent. The NO answers cite `[]`, which is correct in form; the
question for them is not what they cite but whether the absence was fairly produced, and in
unseen2 and unseen3 it was not.

**Was the resolution visible to the world or any actor?**
No. 0/272 world prompts and 0/127 actor prompts contain the resolution, any of its operative
clauses, or the question as a question. Overlaps are situational facts the characters
legitimately know. Full counts in §1.

**Did the judge ever conclude something the events do not support, or miss something they do?**
Across 179 terminal checks the judge is disciplined and its verdict changes exactly once per
run, always for a stated reason. Three blemishes, none of which changes an answer:
1. unseen3's final check says *"a check written"*; the record shows only a checkbook opened.
2. case2's YES cites `e125` alone when the agreement is constituted by `e66` + `e125`.
3. unseen3 checks #34 and #38 reason inconsistently about the timezone (*"4:02 p.m. UTC,
   which is after 3 p.m."* then *"18:04 UTC, which is before the deadline"*). Code prevents
   this from mattering — `NO_AT_CUTOFF` is refused before the runtime cutoff — but the
   confusion is the compiler's timezone incoherence surfacing in the judge.
The judge also never once mistook an intention, a private memory, or a world judgment for an
event, which is the failure mode the design is most worried about. That guarantee holds.

**Is the system capable of both answers for good reasons, or does it lean?**
It is capable of both, and both YES runs are honest. But it leans, and the lean is in the
treatment: **both YES answers arrived within 65 minutes of simulated time**, before any
actor's recheck interval had widened; **every run lasting longer than a day answered NO**,
and in three of those four the pivotal actor had been dropped by the scheduler before the
window closed. case1 is the one NO that stands on its own merits, because Mark Cuban was
asked thirteen times and refused thirteen times — the shape a legitimate NO has. case3,
unseen2 and unseen3 do not have that shape.

The comparison that makes the point sharpest is case2 versus case3. Same runtime, same world
model, same "two-plus people must converge" structure. In case2 the world wrote the content
of each message into the event description, actors could read each other, and the question
resolved YES in an hour. In case3 the world wrote content-free descriptions, actors could
read nothing, and the question could not have resolved YES at all. That difference is not in
the situations. It is in the treatment.

---

## 5. What would have to change

1. **Never let the recheck interval outrun the deadline.** Cap
   `_schedule_recheck` by the remaining time to cutoff, and reset an actor's backoff whenever
   they take an intention. No actor should be silently dropped because a quiet Tuesday
   widened their interval past a live Friday.
2. **A wake belongs to the actor.** In the `elif pending:` branch, do not let an unread
   notification consume an actor's turn indefinitely; give the actor the turn and let the
   world adjudicate what they attempt.
3. **Follow the open dependency.** When an actor's own action leaves them waiting on someone
   else, keep them on the schedule; `waiting = envelope["for"] or [self_act_of]` loses them.
4. **Content belongs in the event.** A committed message event whose description omits what
   was said destroys the only channel actors have. Require the world to carry the substance,
   as it did unprompted in case2.
5. **Bind the runtime cutoff to the resolution's own deadline** (case2 is 18 h late, case3
   20 h late) and make the scene's timezone explicit, so the world's "3 p.m." and the
   runtime's cutoff instant are the same moment (unseen3).
6. **Let observations supersede compiled private context.** Ezra should not still be told
   his slip is in his backpack a day after it was taken out.
7. **Persist judge exchanges** alongside world and actor exchanges.
8. Minor: require a YES to cite every event that constitutes the resolution, not just the
   last one.
