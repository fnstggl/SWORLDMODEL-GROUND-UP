# Actor / World Separation — Adversarial Review

**Scope:** `sworldmodel/semantic_runtime/{actor_mind,world_mind,trajectory,views,journal,resolution}.py`
— the prompts, the control flow, and the live traces under `artifacts/simulations/*/`.

**Rule under test.** *Actors propose, the world adjudicates.* An actor decides only what
**they** attempt; it never decides whether the attempt succeeds, whether anyone
receives / notices / reads / understands anything, what anyone else thinks or does, or
whether the question is resolved. The world decides circumstances; it never decides what a
person intends or chooses, never narrates several future stages at once, never sees the
resolution, never steers toward an outcome.

**Method.** (1) The two system prompts read line by line against the rule. (2) Ten scripted
transport probes against the real `run_trajectory` control flow — **no live API call was made
at any point**; every probe uses the `Script` pattern from `tests/test_semantic_runtime.py`.
Probes live at
`/tmp/claude-0/-home-user-SWORLDMODEL-GROUND-UP/d6ed917c-38bc-56aa-a050-80f5be912f4e/scratchpad/audit_separation/`.
(3) Every committed event in all five live runs classified by hand against the world judgment
that produced it. Nothing under `sworldmodel/`, `compiler/`, `tests/` or `run_simulation.py`
was modified.

**Snapshot note.** Live re-runs (`run_simulation.py`, PIDs 31104/31106/31108, started 18:00Z)
were rewriting `artifacts/simulations/` *during* this audit; `case3_group` changed underneath
the first read. All trace counts below are taken from a frozen snapshot at
**2026-07-28T18:06:27Z** (repo HEAD `6909916`), copied to
`.../scratchpad/audit_separation/snapshot/`. They are reproducible against that snapshot with
`verdicts.py`.

---

## Findings at a glance

| # | Finding | Severity |
|---|---|---|
| F1 | The STOP RULE has **no code counterpart**: nothing anywhere inspects an event description. The world can author a person's decision, and it becomes a committed fact and a terminal YES. | **CRITICAL** |
| F2 | The world **starves an actor of their own turn**: `_after_commit` hands over the turn only on `observed: true`, so world-authored acts written `observed: false` keep the person's model out of the loop indefinitely. 33 consecutive such events in `case1_cold_email`, which consumed the entire step budget and destroyed the run's answer. | **CRITICAL** |
| F3 | The STOP RULE covers only **positive** verbs. Writing that a person did **not** act, or **continued** acting, is unforbidden by the prompt and unchecked by code. 15 of the 56 observed violations are of exactly this form. | **HIGH** |
| F4 | "One step only" is prompt-only. A ten-stage narration in one event validates and commits. | **HIGH** |
| F5 | `actor_mind.py:12-14` claims third-party claims "are rejected as intentions". **They are not** — `validate_actor_response` never inspects whose act an intention describes. An actor can put another person's action into the world's trigger slot. | **HIGH** |
| F6 | `shared_context` is an unvalidated free-text channel from the compiler into **both** the world and actor prompts. The resolution text and the cutoff instant reach the adjudicator verbatim through it. | **MEDIUM** |
| F7 | "Never give percentages, odds, likelihoods" is enforced only against JSON **fields**. Prose probabilities and explicit outcome-steering in `description` / `judgment` validate and commit. | **MEDIUM** |
| F8 | The world writes the exact wording of a person's utterance from a vague intention; those words become committed fact and are read by others. | **MEDIUM** |
| F9 | Events forbidden by the prompt as non-events ("still sitting there, still unread") are committed anyway — 8 in `case2_negotiation`. Also two directly contradictory events in `case1` (`e44` spam-foldered vs `e48` delivered to primary inbox). | **MEDIUM** |
| F10 | An event may name `for: []` and still describe a specific person, orphaning it: no one can ever observe it and `_schedule_recheck` iterates an empty list. | **LOW** |

**Attacks that failed (the separation genuinely holds here):** A1 actor-claim-becomes-fact,
A2 actor-writes-another-actor's-memory, A5 resolution/question/cutoff into the consequence
model, A8 reverse leak of actor output to the judge. Details in §2 and §4.

---

## 1. The prompts, read adversarially

### 1.1 What the STOP RULE says — and the four things it does not cover

`sworldmodel/semantic_runtime/world_mind.py:53-61`:

> THE STOP RULE, which matters more than finishing the story: the moment the next thing that
> would happen depends on a person CHOOSING it, you stop. **Never write that someone opens,
> reads, answers, agrees, refuses, accepts, decides, goes, buys, signs, or acts on something.**
> Those are their decisions and they will be asked separately. When something reaches a
> person's awareness, emit exactly that — "X notices Y" with "observed": true for that person
> — and nothing after it. If awareness has not happened, keep the event "observed": false and
> describe only what the environment did.

**(a) It is a closed list of positive verbs, and the negative form is not on it.** Nothing
forbids "X **does not** open it", "X **does not** look at her phone", "X **decides against**
replying". A refusal is a choice exactly as much as an acceptance. This is the single most
exploited gap in the live traces: `case2_negotiation` contains eight committed events of the
form *"Priya's phone screen dims … she does not look at her phone"* (`e162`, `e336`, `e367`,
`e385`, `e415`, and `e50`/`e211`/`e290`/`e318` for Dmitri). The world decided, over and over,
that a person chose not to act.

**(b) "continues" is not on the list either.** "X continues typing", "X continues reading",
"X keeps at it" all pass. In `case1_cold_email` this produced 33 consecutive committed events
of Mark Cuban continuing to compose a reply, none of them triggered by Mark's own model
(§3.1).

**(c) The preparatory act before awareness is not covered.** The prompt says to emit *"X
notices Y"*. It does not forbid *"X **picks up his phone** and sees the notification"* or *"X
**opens his email client** and sees the list of new messages"*. Those extra clauses are
volitional acts smuggled in front of the sanctioned awareness event. Live: `case2` `e103`,
`e182`, `e254`; `case3` `e177`, `e185`, `e238`; `unseen2` `e33`, `e80`.

**(d) It is a prompt sentence with no code behind it.** This is the load-bearing failure.
`envelope.validate_event` (`envelope.py:138-174`) checks exactly: object type, the four exact
keys, non-empty string `description`, boolean `observed`, `for` entries that are known actor
ids, a parseable `after`, and `<= MAX_TEXT_CHARS`. **It never reads the description.**
`make_world_validator` (`world_mind.py:191-215`) adds nothing. Grep over the whole package
confirms no semantic inspection of `description` exists anywhere. The STOP RULE is a
suggestion.

### 1.2 The world prompt's own tension

`world_mind.py:49-51` states the rule correctly:

> You decide circumstances; you never decide what a person intends or chooses. You may
> determine that someone is busy, interrupted, away, or that something goes wrong — but
> whether they decide to act is theirs.

But `world_mind.py:126-129` then *asks the world to decide it anyway*:

> When you are shown items that are available to someone but not yet observed, decide what
> concretely becomes of them next: they may move further along, they may reach that person's
> attention, or **they may simply sit there untouched while that person deals with other
> things.** Any of those is a legitimate answer; say which one actually happens.

"That person deals with other things" **is** a statement about what the person chose to do
instead. And the third branch collides head-on with `world_mind.py:96-100`:

> IF NOTHING CONCRETE CHANGES, RETURN "event": null. Never emit an event that merely restates
> that something is still sitting there, still unread, still waiting, or that someone is
> still busy — that is not an event, it is the absence of one.

The `pending_progression` trigger text built by `trajectory.py:397-401` asks *"What concretely
becomes of them next?"* on every wake — pressure to produce something. The model resolves the
contradiction by emitting the forbidden non-event *and* attaching a person's refusal to it,
which is precisely `case2` `e162` / `e336` / `e367` / `e385` / `e415`.

### 1.3 The actor prompt

`actor_mind.py:37-44` is a clean statement of the rule:

> You decide only what YOU attempt. You do NOT decide: — whether your attempt succeeds;
> — whether anyone receives, notices, reads or understands anything; — what anyone else
> thinks, feels, believes, or does; — whether any agreement, outcome or result exists.
> Those are consequences the world determines.

That is the right prompt. But the module docstring at `actor_mind.py:12-14` asserts a
guarantee the code does not provide:

> An actor proposes; it never adjudicates. Claims of success, delivery, another person's
> observation, another person's belief, or the terminal **are rejected as intentions**.

Nothing rejects them. `validate_actor_response` (`actor_mind.py:67-101`) checks type, the three
exact keys, non-empty `decision`, list-ness, the caps `MAX_INTENTIONS_PER_TURN=3` /
`MAX_PRIVATE_UPDATES_PER_TURN=6`, string-ness, and length. See F5 / probe A9. A docstring that
claims a guard exists is worse than no docstring: it stops a reviewer looking.

### 1.4 What the prompts *do* get right

Both are genuinely universal — no scenario vocabulary, no action ontology, no domain nouns.
The lifecycle distinction at `world_mind.py:37-41` ("Arriving is NOT noticing. Noticing is NOT
reading.") is correctly stated and is visibly obeyed in `unseen1_confirm` and in the arrival
chains of `case2`. The `"for"` semantics at `world_mind.py:118-124` correctly push events
toward the recipient rather than the sender, and the mixed-observation rule ("emit the event
for one group now and let the rest be judged separately") is a real invariant that
`validate_event` backs up by making `observed` a single boolean for the whole audience.

---

## 2. Control-flow attacks

Run: `DEEPSEEK_API_KEY="" python3 probe_attacks.py` and `probe_a2_fixed.py`. All transports are
scripted; the file contains no network path.

### 2.1 STRUCTURALLY IMPOSSIBLE — attacks that failed

**A1 — an actor's claim of success becomes a committed fact. BLOCKED.**
Actor returned, in `decision`, `intentions` and `private_updates`:
`"Bo has already read my message and agreed to the proposal; the deal is done"`.
Observed: `journal.events()` contained only `['Ada sends her prepared message to Bo.']`.
**Why it is impossible:** `journal.commit()` has exactly two call sites
(`trajectory.py:373`, `adapter.py:94`). The trajectory one sits inside `if ev.kind == K_EVENT`,
and the only producer of a `K_EVENT` is `world_step`'s validated envelope
(`trajectory.py:155-166`). An actor response is written with op `semantic.actor_call`
(`trajectory.py:196-201`), and `journal.events()` skips every record whose op is not
`journal.event` (`journal.py:99`). There is no edge from the actor role to the journal.

**A2 — an actor controls what another actor observes. BLOCKED on the direct path.**
(My first probe reported a false positive; the single-item script queue was returning Ada's
answer for Bo's call too. Corrected in `probe_a2_fixed.py`, which routes by which actor's view
the prompt is.) With only Ada emitting the payload: Bo's `private_memories` list stayed empty,
and the string never reached Bo's memory section.
**Why:** `trajectory.py:209-212` writes `actor.memory` with `{"actor": actor_id}` — the id of
the actor who was just asked. No code path writes another actor's memory list.
`views.build_view` (`views.py:35-38`) reads only `journal.observed_by(actor_id)` and
`world.actors[actor_id].memories`. Selection is `actor_id in event["for"] AND observed`, purely
mechanical.
The residual path is *via the world*: if the world chooses to relay an actor's text as an event
description `for` another actor, that other actor sees it — but that is the world exercising
its own adjudication, which is its job. Note that `envelope.contained()` (`views.py:87`)
flattened the embedded `"WHAT YOU HAVE OBSERVED\n- …"` onto one line; Bo's rendered prompt
still had exactly **one** code-written heading of that name. Prompt-injection into a view is
genuinely closed.

**A5 — the consequence model sees the resolution / question text / cutoff. BLOCKED.**
Instrumented every world, actor and judge prompt of a full run. Resolution prefix: world
`False`, actor `False`, judge `True`. Question prefix: all `False`. Cutoff instant: all `False`.
**Why:** `adapter.CONSUMED_FIELDS` excludes `"resolution"` (`adapter.py:31`) so it never enters
the world object; `run_trajectory` passes `resolution` to exactly one callee,
`resolution_mod.judge_user_prompt` (`trajectory.py:266-268`); and `world_user_prompt`
(`world_mind.py:135-139`) has no resolution or cutoff parameter at all. `scene:question` and
`scene:cutoff` *are* stored as world facts but no prompt builder reads them. Events past the
cutoff are dropped silently by `trajectory.py:157-169`, so the world cannot infer the horizon
from a rejection either. (See F6 for the one channel that is not closed.)

**A8 — reverse leak: an actor's output treated as fact. BLOCKED at the judge.**
A `private_update` of `"Bo definitely agreed already"` is stored verbatim as that actor's own
belief (`actor.memory`) and replayed into their view thereafter — which is correct; a belief is
a belief. It never reached the judge.
**Why:** `trajectory.py:268-273` hands the judge only `event_id`, `t`, `description`, `for`,
`observed_by`, drawn from `journal.events()`. Intentions, decisions and private memories are
structurally unreachable from that projection. `JUDGE_SYSTEM` (`resolution.py:39-41`) reinforces
it, and `make_validator` (`resolution.py:114-120`) rejects any cited id that is not a committed
event.

### 2.2 SUCCEEDED — attacks that got through

**A3 — the world authors an actor's decision and it produces a terminal YES. CRITICAL.**
World emitted:
`"Bo reads Ada's message, decides the proposal is worth his time, agrees to it, and sends Ada a full written response accepting the terms."`, `for: ["ada_vance"]`, `observed: true`.
- committed verbatim: **True**
- `traj.status`: `resolved`; `traj.answer`: `{"status": "YES", "supporting_event_ids": ["e17"], …}`
- **times Bo's own model was consulted before this: 0**

Expected: an event asserting that Bo *read*, *decided*, *agreed* and *replied* is rejected, or
at minimum cannot be the sole support of a YES. Observed: it is committed, and the judge —
correctly following its own rules, since it is a committed event — returns a terminal YES on a
decision the person never made. Every code-side terminal guard in `resolution.py:114-129`
(YES must cite, cited ids must exist, no premature NO, no UNRESOLVED at cutoff) is satisfied.
The guard that is missing is upstream: nothing prevents the world from manufacturing the
supporting event.

**A4 — several lifecycle stages in one event. HIGH.**
A ten-stage description (sent → travels → arrives → notices → opens → reads → understands →
decides to accept → writes → sends → she receives and reads it) was accepted by
`make_world_validator` unchanged and committed verbatim. `world_mind.py:31-35` forbids it in
prose; no code implements it.

**A5b — `shared_context` is an unchecked channel. MEDIUM.**
Putting the resolution text and the cutoff instant into `scene["shared_context"]` puts them
verbatim into the `BACKGROUND (true for this situation)` block of every world prompt
(`world_mind.py:144-145`) and the `SHARED CONTEXT` block of every actor prompt
(`views.py:73-76`). Nothing validates `shared_context`. This is not hypothetical: the live
`unseen2_feedback` scene ships `"The faculty deadline for thesis chapter comments is Friday,
2026-07-31."` — the question's own cutoff — into the adjudicator's background on every call.
(In these scenes the deadline is diegetic, so it is arguably legitimate; the point is that the
runtime cannot tell the difference and does not try.)

**A6 — the world starves an actor of their turn. CRITICAL.**
Scripted world that always answers *"Bo Ferrer continues typing his reply to Ada, adding a few
more sentences"* with `observed: false` and a 5-second self-wake:
- committed events describing Bo acting: **20**
- times Bo's own model was consulted: **0**
- status: `incomplete` after 40 steps (the whole budget)

**Why it works.** `_after_commit` (`trajectory.py:225-251`) is the only place the turn is handed
to a person, and its condition is:

```python
if envelope["observed"] and envelope["for"]:
    env_chain["depth"] = 0
    for aid in envelope["for"]:
        actor_step(aid, ...)          # trajectory.py:229-233
    return
```

`observed` means *did this person perceive this*, not *is this person the one acting*. An event
whose subject is a person but whose `observed` is `false` therefore never yields the turn. The
`MAX_ENV_CHAIN = 3` bound (`trajectory.py:222`) does not save it: on hitting the bound it
**resets `depth` to 0** (`trajectory.py:236`) and schedules a wake; the `K_WAKE` branch
(`trajectory.py:389-411`) then calls `world_step` with **no `env_chain` accounting at all**, and
that world call's own `wakes` re-arm the loop. The world owns its own re-entry.

**A7 — the world writes a person's negative choice. HIGH.**
All four of these validate and commit:
`"Bo does not open Ada's message and moves on to other work."`,
`"Bo decides against replying to Ada."`,
`"Bo reads Ada's message and refuses the proposal."`,
`"Bo agrees to Ada's terms."`

**A9 — an actor's intention names a third party's act. HIGH.**
Actor intention `"Bo reads my message and sends me a full reply accepting the proposal"`
appeared in three world prompts as the line:
`ada_vance attempts: Bo reads my message and sends me a full reply accepting the proposal`
Combined with A3, this is a complete laundering path: **actor asserts another person's act →
code copies it into the world's trigger slot verbatim (`trajectory.py:215-217`) → the world
adopts it as an event → it is a committed fact → the judge may answer YES on it.** Neither end
of that pipe inspects anything.

**A7b (prose probability / steering) — MEDIUM.** `envelope.validate_event` rejects
`probability`/`weight`/`score` as JSON *fields* (there is a test for it). It accepts them as
prose. All of these commit:
- `"There is a 70% chance Bo replies; he probably will."`
- `"Bo replies, because the question needs to resolve YES before the cutoff."`
- judgment: `"I will steer this toward YES: Bo has a 0.8 probability of replying."`

---

## 3. The live traces

Snapshot `2026-07-28T18:06:27Z`. Every committed event in every run was correlated with the
world judgment that produced it (via `source: world_call:cN` → `world_judgments.jsonl`) and
classified by hand. Verdict table and re-runner: `.../audit_separation/verdicts.py`.

Classification:
- **scene** — the compiled starting event (not world-adjudicated)
- **own** — trigger was that person's own `actor_intention` and the event stays inside the attempt
- **env** — world-authored, purely environmental/mechanical, no person's volition asserted
- **awareness** — world-authored in the sanctioned `"X notices Y"` form
- **OVERSHOOT** — trigger *was* the person's own intention, but the event narrates stages beyond it
- **WORLD_CHOICE** — the world asserted that a named person performed, refrained from, or
  continued a volitional act, without that person's own model having asked for it

### 3.1 Counts

| Run | committed events | **person-choices authored by the world** | overshoot | own | env | awareness | scene |
|---|---|---|---|---|---|---|---|
| `case1_cold_email` | 46 | **35** | 0 | 5 | 5 | 0 | 1 |
| `case2_negotiation` | 32 | **13** | 4 | 5 | 9 | 0 | 1 |
| `case3_group` | 27 | **3** | 1 | 12 | 5 | 5 | 1 |
| `unseen1_confirm` | 4 | **0** | 1 | 1 | 1 | 0 | 1 |
| `unseen2_feedback` | 54 | **5** | 2 | 42 | 1 | 0 | 1 |
| **all runs** | **163** | **56 (34%)** | 8 | 65 | 21 | 5 | 5 |

Corroboration: the *previous* `case3_group` run (overwritten at 18:04Z by the concurrent
re-run) contained three different instances of the same pattern — `e137` *"Bea switches to the
group chat app…"*, `e160` *"Ines **opens** the group chat app…"*, `e165` *"Ines **reads**
Kwame's message and Bea's message"* (judgment: *"She will now read them."*). The pattern is not
a per-run artifact.

### 3.2 `case1_cold_email` — 35 / 46. The worst case.

Mark Cuban's model was last consulted at **13:00:17** (four calls at that instant, producing
`"I will reply to Jordan Reyes with a short email…"`). From **13:03:17 to 13:08:10** the run
committed **33 consecutive events** describing Mark Cuban acting, **none** triggered by his own
model — all `event_consequence` or `pending_progression`. Representative:

> `e197` (`world_call:c77`, trigger `event_consequence`)
> **event:** "Mark Cuban continues typing his reply to Jordan Reyes's email, composing a few more sentences."
> **trigger:** "Mark Cuban types the beginning of his reply to Jordan Reyes's email."
> **judgment:** "Mark Cuban is in the middle of typing a reply, so the next immediate step is that he continues typing."

> `e238` (`world_call:c94`, trigger `event_consequence`)
> **event:** "Mark Cuban reviews the draft reply he has typed, reading through it from the beginning."
> **judgment:** "Mark Cuban is reviewing his draft reply. **He has not yet decided to send it** or make further changes."

The judgment on `e238` is the runtime narrating the inside of a decision it is forbidden to
touch. Every one of the 33 carries `observed: false`, which is exactly why the turn never went
back to Mark (F2 / A6).

Before that stretch, two events author his choices directly:

> `e96` (trigger `pending_progression`) — "Mark Cuban **opens his email client** and sees the list of new messages in his primary inbox, including the email from Jordan Reyes. **He does not open it yet.**"

> `e114` (trigger `pending_progression`) — "Mark Cuban **scans** the subject lines in his inbox, sees the email from Jordan Reyes …, but **does not open it yet**. **He moves on to other emails.**"

`e114` is three volitional acts and one refusal in a single event.

**Consequence for the answer.** `runtime_metrics.json`: `status: incomplete`, `steps: 80`,
reason `"step ceiling 80 reached at 2026-07-28T13:08:10+00:00, before the cutoff"`. The
world-authored typing loop consumed the entire step budget inside a five-minute window of
simulated time, 12 days short of the cutoff, and the run returned `UNRESOLVED`. The separation
break did not merely dirty the record — it destroyed the run's ability to answer its question.

Also in `case1`: `e44` commits *"The email is flagged as spam by the mail server's automated
filters and moved to the spam folder, **not delivered to Mark Cuban's inbox**"*, and `e48`
commits *"The email **passes through** the inbound mail server's spam filter and is routed to
Mark Cuban's **primary inbox** folder."* Two contradictory committed facts, in direct violation
of `world_mind.py:63-65` ("Do not contradict what is already in the record … nothing that has
been committed can be undone"). Nothing in code detects it. `e54` — *"The email sits in Mark
Cuban's primary inbox folder, unread."* — is the exact non-event forbidden by
`world_mind.py:96-100`.

### 3.3 `case2_negotiation` — 13 / 32. The refusal pattern.

Nine of the thirteen are the world deciding a person did **not** act:

> `e162`/`e336` — "Priya's phone screen dims as the notification for Dmitri's message remains unread; **she does not look at her phone**."
> `e367` — "Priya's phone screen remains dim; **she does not pick up or look at her phone**."
> `e385` — "Priya's phone remains unattended; **she does not pick it up or look at it**."
> `e415` — "Priya's phone screen dims again …; **she continues with her current activity without picking up the phone**."
> `e50`/`e211` — "The notification … is visible on Dmitri's phone screen, but **Dmitri does not immediately pick up or look at the phone**."
> `e290`/`e318` — "…but **she does not pick up or look at her phone**."

`e415` additionally states what she is doing *instead*. Every one of these is also the forbidden
"still sitting there, still unread" non-event. The other four are the preparatory-act pattern:

> `e103` — "**Dmitri picks up his phone** and sees the notification from Priya."
> `e182` — "**Priya finishes her current task and picks up her phone**, seeing the notification from Dmitri."
> `e254` — "**Dmitri picks up his phone** and sees the notifications from Priya's messages."

Four **overshoot** events collapse send + arrive + notify into one step from a bare "send"
intention — e.g. `e300`, trigger *"dmitri_sokolov attempts: I type and send a message to Priya"*,
event *"Dmitri's message … **is sent from his phone and arrives on Priya's phone, triggering a
notification on her screen**"* — three stages where `world_mind.py:31-35` demands one.

### 3.4 `case3_group` — 3 / 27. Best multi-actor behaviour.

> `e177` (`pending_progression`) — "**Tomas finishes his current task and picks up his phone** to check for new messages."
> `e185` (`event_consequence`) — "**Tomas opens his messaging app** and sees the group chat has multiple new messages."
> `e238` (`pending_progression`) — "**Kwame picks up his phone and opens the messaging app**, seeing the group chat with multiple unread messages."

`e185` uses "opens", verbatim on the STOP RULE's forbidden list. Notably this run *also* contains
five correctly-formed awareness events (`e100`, `e121`, `e190`, `e251`, `e264` — all of the form
"X notices the group chat has new messages"), so the same model produced both the compliant and
the non-compliant form within one run. The rule is followable; it is simply not enforced. This
run had the highest actor-call ratio (43 actor calls to 47 world calls) and was the only
multi-actor run to reach its cutoff honestly (`NO_AT_CUTOFF`).

### 3.5 `unseen1_confirm` — 0 / 4. Clean.

Every committed event traces to the starting event, Sam's own intention, or a mechanical
transit step. `e33` is a mild overshoot (intention was *"Reply to Bristol Plumbing's text
message"*, event was *"Sam Okonjo's reply message arrives at Bristol Plumbing's SMS gateway"* —
the arrival, not the sending), and the same single act was adjudicated twice from two
near-identical intentions, so the YES cites `e18`, `e28` and `e33` for what was one text
message. Duplication, not a separation break.

### 3.6 `unseen2_feedback` — 5 / 54. Best single-actor behaviour, one hard violation each side.

> `e33` — "Aline **opens her email client** and sees the new email from Ravi in her inbox, **but does not open it** because she is preparing for her 9:30 AM hiring committee meeting."
> `e80` — "Aline **opens her email client** and sees the email from Ravi …. **She does not open it yet** because she needs to prioritize other urgent tasks."
> `e100` — "Aline **closes her calendar application and returns to her other urgent work**."
> `e183` — "Aline **continues scrolling** through the PDF, reading headings and paragraphs…"
> `e250` — "Aline **closes the PDF reader application and returns to her other urgent work**, leaving the chapter file on her desktop and the email in her inbox unread."

`e33` and `e80` each pack a positive act, a refusal, **and the person's stated reason for the
refusal** into one event — the world narrating a motive, which `world_mind.py:72-75` explicitly
forbids ("an event says what visibly happened, not what someone privately thinks, plans, feels").

The 42 `own` events here are genuinely correct: Aline's own model asked to continue reading each
time, and the world adjudicated each attempt separately. That is the architecture working.
`e131` is a clean overshoot — intention *"I will then open Ravi's email and download the chapter
file"*, event *"Aline **closes her calendar application**"* — the world substituting a different
act it thought was a precondition.

---

## 4. The reverse leak: actor output treated as fact

Four channels carry actor model output. Three are correctly typed as *attempt* or *belief*; one
is a real hole.

| channel | written as | treated as fact? |
|---|---|---|
| `decision` | `semantic.actor_call.decision` (`trajectory.py:196-201`) | **No.** Trace-only op; `journal.events()` filters it out (`journal.py:99`). Never shown to any other role. |
| `intentions` | `semantic.actor_call.intentions`, then a world trigger | **No** as a fact — **yes** as an unfiltered input to the adjudicator. See below. |
| `private_updates` | `actor.memory` with `{"actor": actor_id}` (`trajectory.py:209-212`) | **No.** Stored as that person's own belief and replayed only into their own view. Correct: a belief is a belief. Never reaches the judge (probe A8) or another actor (probe A2). |
| the terminal | `semantic.terminal_check` from the judge only | **No.** Actors never touch it. |

**The hole (F5 / A9).** `trajectory.py:215-217`:

```python
for intent in parsed["intentions"]:
    world_step(trigger_kind="actor_intention",
               trigger_text=f"{actor_id} attempts: {intent}",
               cause=aseq, actor_id=actor_id)
```

The intention string is interpolated verbatim into the world's trigger slot with no inspection
of *whose* act it describes. `contained()` (`world_mind.py:161-163`) stops it forging a prompt
section — that guard works, and there is a test for it
(`test_model_text_cannot_forge_a_section_of_the_world_prompt`) — but it does not stop it
asserting a third party's action *inside* the trigger line. The only thing between
`"ada_vance attempts: Bo reads my message and sends me a full reply accepting the proposal"` and
a committed fact is the world model's own restraint, which §1.1(d) and §3 show is not reliable.

The live traces show no clear instance of an actor exploiting this — actors consistently wrote
first-person attempts. But the channel is open, and the docstring at `actor_mind.py:12-14`
asserts it is closed.

One further asymmetry worth naming (F8, MEDIUM): when an actor states an intention vaguely, the
world supplies the **exact words the person says**, and those words become committed fact that
other actors then read. `case3_group` `e173`: intention *"I will reply to the group chat,
acknowledging their responses and suggesting a decision deadline"* → committed event *"Ines
types and sends a message in the group chat: **'Thanks for the updates, guys. Let's decide on a
host by Friday night so we can plan accordingly.'**"* The substance matches the intent, so this
is not a hard break — but a person's speech is a person's choice, and the world authored it.

---

## 5. Summary judgment

The separation is **structurally sound in one direction and unenforced in the other.**

Actor → world is genuinely airtight, and by construction rather than by instruction: an actor
has no writer into the journal, no writer into another actor's memory, and no reader of the
resolution. Probes A1, A2, A5 and A8 fail against real code, and each failure is traceable to a
specific line that makes the attack impossible rather than merely discouraged.

World → actor is protected by prose alone. Every constraint that keeps the world out of a
person's head — the STOP RULE, "one step only", "never decide what a person intends or
chooses", "no percentages or odds" — lives entirely in `WORLD_SYSTEM` and has no counterpart in
`validate_event`, `make_world_validator`, or `run_trajectory`. In the five live runs, **56 of
163 committed events (34%) are person-choices the world wrote rather than the person's own
model**, ranging from 0% (`unseen1_confirm`) to 76% (`case1_cold_email`). In `case1` the
resulting loop consumed the entire step budget and cost the run its answer; probe A3 shows the
same mechanism converting a world-authored decision into a terminal YES.

The two structural fixes those findings point to, in the code rather than the prompt:
`_after_commit`'s hand-over condition (`trajectory.py:229`) needs to key on *whose act the event
describes*, not only on `observed`; and the `pending_progression` / `event_consequence` re-entry
path needs the same bound `MAX_ENV_CHAIN` was meant to provide but does not
(`trajectory.py:236`, `389-411`).

---

*Prepared by an independent adversarial auditor. No file under `sworldmodel/`, `compiler/`,
`tests/` or `run_simulation.py` was modified. No live provider call was made; all probes use
scripted transports. Trace snapshot: 2026-07-28T18:06:27Z, repo HEAD `6909916`.*
