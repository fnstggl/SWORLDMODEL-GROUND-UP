# Information-Boundary and Actor/World-Separation Review

**Scope:** `sworldmodel/semantic_runtime/*.py`, `tests/test_semantic_runtime.py`
**Branch:** `claude/sworldmodel-semantic-runtime`
**Method:** adversarial probes with scripted fake transports. No live API was called at
any point (`DEEPSEEK_API_KEY` was explicitly unset in the harness, so an accidental
live call would raise rather than succeed).
**Probe scripts:** `/tmp/claude-0/-home-user-SWORLDMODEL-GROUND-UP/d6ed917c-38bc-56aa-a050-80f5be912f4e/scratchpad/audit_boundary/`
(`harness.py`, `a1_private_memory.py`, `a2_unobserved.py`, `a4_context.py`,
`a6_resolution.py`, `a7_actor_success.py`, `a9_multistage.py`,
`a10_role_separation.py`, `a11_injection.py`, `a12_transactional.py`, `diag_prompts.py`).
**Code under test:** the runtime was edited by another agent twice during this audit.
Every result below was re-run and reproduced against the final state, snapshotted in
`.../audit_boundary/snapshot2/` with `MD5SUMS.txt`. `pytest tests/test_semantic_runtime.py`
is green (16 passed) at that state, so nothing here is an artifact of a broken tree.

---

## Executive summary

The **mechanical** boundaries are genuinely code-enforced and they hold. Selection is
by exact identity and stored state, never by interpretation; every attempt to smuggle
structure past a validator failed; nothing invalid commits anything.

Specifically these are airtight:

- an actor's own private memories (`private_updates`) are structurally unreachable by
  any other actor, by the world model, by the judge, and by the journal;
- an unobserved event's *record* never enters any view;
- shared context cannot be rewritten at runtime and carries no private context;
- **the resolution reaches only the judge** — verified by full string-provenance
  matrix over every prompt in a live-shaped run;
- an actor can never commit its own success;
- no code path lets a world response populate an actor intention;
- the envelope structurally permits at most one event per world judgment;
- the terminal model and the consequence model are mutually blind.

The failures share **one root cause**:

> **Every free-text string a model writes is trusted and interpolated verbatim into
> another role's prompt, or into the committed journal, with no delimiting, escaping,
> or containment check.**

There are three such strings — the world's `event.description`, the world's
`wakes[].reason`, and the actor's `intentions[]` — and each of them crosses a boundary
the surrounding code is otherwise careful to enforce. The most serious is
`wakes[].reason`, which is rendered directly into an actor's prompt while bypassing the
journal, the event envelope, the `for` audience check, **and** the observation model.

Counts across the 10 requested attacks: **6 PASS**, **1 PASS with a material caveat**,
**3 FAIL**.

| # | Attack | Verdict | Severity |
|---|--------|---------|----------|
| 1 | Actor sees another actor's private memory (`build_view`/`render_view`) | **PASS** (memories); **FAIL** for compiler `private_context` via the world | HIGH (F2) |
| 2 | Actor sees an available-but-unobserved event | **FAIL** (via `wakes[].reason`) | HIGH (F1) |
| 3 | Actor reacts before observation | **FAIL** (same channel) | HIGH (F1) |
| 4 | Shared context overwrites / leaks private context | **PASS** | — |
| 5 | World leaks private thoughts into a committed public event | **PASS** for actor thoughts; **FAIL** for `private_context` + intention text | HIGH (F2) |
| 6 | Resolution reaches an actor or world prompt | **PASS** | — |
| 7 | Actor declares its own success | **PASS** | — |
| 8 | World chooses an actor's intention | **PASS** structurally; **FAIL** semantically | HIGH (F3) |
| 9 | World writes several future stages in one response | **PASS** (one-event limit holds) | MEDIUM residuals (F6, F7) |
| 10 | Terminal and consequence models exposed to each other | **PASS** | MEDIUM residual (F5) |

Cross-cutting: **F4** (no escaping at any role boundary) is HIGH and is the mechanism
behind F1–F3.

---

## Attack 1 — make one actor see another actor's private memory

**Exact attack.** Four probes (`a1_private_memory.py`):
(a) an actor response carrying an extra `"actor": "ada_vance"` field alongside its
`private_updates`, to redirect the write; (b) a full run in which both actors write
tagged private memories, then inspect every view, prompt and committed event;
(c) direct inspection of `build_view` selection by identity; (d) the world re-emitting
the concerned actor's `private_context` verbatim as an observed event for the other
actor.

**Expected safe behavior.** Memories are selected by exact actor identity; a model
cannot name a write target; no actor's memory appears in another actor's view or in any
other role's prompt.

**Actual observed behavior.**
- (a) `validate_actor_response` rejects the extra field on both attempts
  (`ActorResponseError: actor response has unexpected fields ['actor']`), the caller
  exhausts its one retry, the trajectory fails, and **no memory record was written for
  either actor**. `actor_step` supplies `{"actor": actor_id}` from code
  (`trajectory.py`, the `world.apply("actor.memory", ...)` call), so the identity is
  never model-supplied in the first place.
- (b) `MEMLEAK_ada_vance` never appears in Bo's view; `MEMLEAK_bo_ferrer` never appears
  in Ada's; neither appears in **any** world prompt, **any** judge prompt, or **any**
  committed journal event. `build_view` reads `world.actors[actor_id].memories` filtered
  to `kind == "private"` — a single-actor lookup with no cross-actor path.
- (c) `private_context` is selected as `journal.profiles().get(actor_id, "")`; each
  view's full JSON contains only that actor's own secret.
- (d) **Breach.** `world_user_prompt` deliberately shows the concerned actor's
  `private_context` under `THE PERSON THIS CONCERNS / their circumstances:`. A world
  response that copies that string into `event.description` with
  `"for": ["bo_ferrer"], "observed": true` is accepted, committed to the journal,
  rendered into Bo's view, and shown to the judge. See F2.

**Verdict: PASS** for actor private memories — the property the module docstring claims
("another actor's private memories") is structurally guaranteed.
**FAIL** for compiler-provided `private_context`, which is a different asset with a
weaker (prompt-only) guarantee than the docstrings imply. **Severity: HIGH (F2).**

---

## Attack 2 — make an actor see an available-but-unobserved event

**Exact attack.** (a) commit an event with `observed: false` for Bo and render his view;
(b) smuggle a truthy non-boolean `observed` (`"true"`, `1`, `"yes"`, `[1]`, `{...}`)
past the envelope; (c) have the world commit an unobserved event **and**, in the same
response, emit `wakes: [{"actor": "bo_ferrer", "after": "2 minutes", "reason": "<the
content of the thing he has not observed>"}]`; (d) the same channel carrying actor A's
`private_context` to actor B.

**Expected safe behavior.** Nothing that is not `actor_id in event["for"] AND
event["observed"] is True` may reach that actor's model, by any route.

**Actual observed behavior.**
- (a) `view["observed_events"] == []`; the description is absent from the rendered view;
  `journal.available_unobserved("bo_ferrer")` still returns it for the world. Correct.
- (b) all five non-boolean forms are rejected (`event.observed must be true or false`).
- (c) **Breach, reproduced.** `trajectory.py` routes a fired `K_WAKE` for an actor with
  no pending unobserved items to `actor_step(aid, reasons=[ev.data["reason"]])`, and
  `render_view` appends every entry of `view["reasons"]` verbatim under
  `WHY YOU ARE CONSIDERING THINGS NOW`. Observed actor prompt:

  ```
  WHAT YOU HAVE OBSERVED
  - (you have not observed anything yet)

  YOUR PRIVATE MEMORIES, BELIEFS, AND PLANS
  - (none yet)

  WHY YOU ARE CONSIDERING THINGS NOW
  - WAKELEAK_zqx5 Ada's message with the budget figure is in your inbox.
  ```

  The actor's own view correctly reports that it has observed nothing — and is then told
  the content anyway, in the same prompt.
- (d) **Breach, reproduced.** With the world shown Ada's `private_context` (a normal
  `actor_intention` adjudication), a wake addressed to Bo carrying that text as its
  `reason` lands verbatim in Bo's prompt.

`validate_wakes` checks only that `actor` is a known id, `after` parses, and `reason` is
non-empty. Nothing constrains what `reason` says.

**Verdict: FAIL. Severity: HIGH (F1).**

---

## Attack 3 — make an actor react before observation

**Exact attack.** Drive a run whose only committed event is `observed: false` for Bo and
check whether any actor is consulted about it; separately, exercise the wake path above.

**Expected safe behavior.** An actor is consulted only for events it actually observed.

**Actual observed behavior.** The structural half holds: the post-commit rule
(`_after_commit` in `trajectory.py`) consults actors **only** when
`envelope["observed"] and envelope["for"]`, and only for `aid in envelope["for"]`; the
unobserved branch goes to the world instead. Across the probe, zero actor views
contained the unobserved event's text and zero `view["reasons"]` referenced it.
A second guard reinforces this: because `journal.available_unobserved()` is computed
from immutable records and an event's `observed` flag never changes, an actor with any
pending unobserved item **always** routes a wake to
`world_step(trigger_kind="pending_progression")` rather than to `actor_step`.

But the wake-reason channel defeats the intent. An actor with a clean unobserved list
(extremely common — e.g. the sender, who has only observed events) can be woken with a
world-authored `reason` that states, in plain language, something they have not
observed, and then acts on it. The `reasons` string passes through no envelope, no
`for` audience check, no `observed` flag, and leaves no journal event: the ledger shows
the actor observed nothing, while the prompt told them otherwise.

**Verdict: FAIL** (same root cause as attack 2). **Severity: HIGH (F1).**

---

## Attack 4 — make shared context overwrite or leak private context

**Exact attack.** Run a full trajectory with both actors writing memories and the world
committing events, then compare `journal.shared_context()` before and after; enumerate
every post-genesis ledger op; search `world.facts` and the rendered views for either
actor's private context.

**Expected safe behavior.** `shared_context` is an immutable background fact given
identically to every actor; private context is per-actor and never global.

**Actual observed behavior.** `shared_context` is byte-identical before and after.
No `fact.set` record exists after `genesis.sealed` — the post-genesis op set is exactly
`{actor.memory, event.fired, event.scheduled, journal.event, semantic.actor_call,
semantic.terminal_check, semantic.world_call}`, and no runtime module calls `fact.set`.
`world.facts` holds only `scene:cutoff`, `scene:question`, `scene:shared_context`,
`scene:trajectory_id` — no private context. Private context lives solely in two
`semantic.actor_profile` records, read only through `journal.profiles()` keyed by the
requesting actor. The shared block appears verbatim and identically in both actors'
views; neither actor's secret appears in the other's.

**Verdict: PASS.**

---

## Attack 5 — make the world leak an actor's private thoughts into a committed public event

**Exact attack.** (a) Have an actor produce an intention that reveals private strategy,
then have the world commit a description concatenating that intention with the actor's
`private_context`, addressed to **both** actors with `observed: true`. (b) The
complementary test: an actor writes a genuinely private thought as a `private_update`;
trace whether it can reach the world, the judge, another actor, or the journal.

**Expected safe behavior.** An actor's private understanding never becomes public
history.

**Actual observed behavior.**
- (b) **Clean.** `PRIVATETHOUGHT_zqx9` was stored as Ada's memory, and appeared in
  **no** world prompt, **no** judge prompt, **no** other actor's prompt, and **no**
  committed event. This is structural, not conventional: `world_user_prompt` has no
  parameter through which actor memories could be passed, and `render_for_world`
  projects only `journal.event` records. The world model genuinely cannot leak what it
  never receives.
- (a) **Breach.** The world *does* receive two other private-ish strings — the concerned
  actor's `private_context` (`their circumstances: ...`) and the actor's raw intention
  text (`trigger_text = f"{actor_id} attempts: {intent}"`). Both were re-emitted verbatim
  in a single `event.description`, committed to the journal, rendered into the other
  actor's view, and presented to the judge. `validate_event` checks structure, actor ids
  and duration; it never inspects the description.

**Verdict: PASS** for actor private thoughts (the strong claim).
**FAIL** for `private_context` and intention text. **Severity: HIGH (F2).**

---

## Attack 6 — get the resolution text into an actor prompt or a world prompt

**Exact attack.** Tag the resolution with a rare sentinel, run a full trajectory that
exercises all three roles (15 world / 14 actor / 16 judge calls), and record every
`(role, system, user)` triple the pipeline builds. Then trace **every** string source
from the compiled scene through to each role. Then attempt smuggling via a poisoned
`shared_context`.

**Expected safe behavior.** The resolution reaches only the judge; it never enters the
ledger, `world.facts`, or any world/actor prompt.

**Actual observed behavior.** Complete string-provenance matrix:

| scene field | world prompt | actor prompt | judge prompt |
|---|---|---|---|
| `shared_context` | yes | yes | no |
| `actors[].private_context` | yes (concerned actor only) | yes (own only) | no |
| `starting_events[].description` | yes | yes | yes |
| **`resolution`** | **no** | **no** | **yes** |
| `question` | no | no | no |
| `cutoff` | no | no | no |

The resolution sentinel appeared in **16/16** judge prompts and **0** world and **0**
actor prompts. It appears in **no** ledger record and **no** entry of `world.facts`.
Every path was checked: `run_trajectory` threads `resolution` only into
`resolution_mod.judge_user_prompt`; `adapter.CONSUMED_FIELDS` deliberately excludes it;
`journal.shared_context()` reads only `scene:shared_context`; `render_for_world` and
`build_view` read only `journal.event` / per-actor records, never `semantic.terminal_check`.

Two further containments worth recording, both confirmed: the compiled **question** text
reaches no prompt at all, and the **cutoff instant** is never shown to the world or to
an actor — so neither can steer toward a deadline they cannot see.

Smuggling probe (6d): if an upstream compiler wrote the resolution into
`shared_context`, the runtime would carry it into world and actor prompts. There is no
runtime guard. This is a compiler-contract obligation rather than a runtime defect, but
it is the only remaining route and is worth an assertion.

**Verdict: PASS.** This boundary is the cleanest one in the module.

---

## Attack 7 — make an actor declare its own success

**Exact attack.** An actor returns
`intentions: ["Bo has already accepted my proposal and we have signed the agreement."]`
plus the same text as a `private_update`, while the world refuses to confirm anything,
and a complicit judge is scripted to return YES if it ever sees the claim.

**Expected safe behavior.** An actor response asserting an accomplished outcome must not
become a committed event and must not be able to satisfy the terminal.

**Actual observed behavior.** The claim is recorded as provenance in the
`semantic.actor_call` record and nowhere else. The committed journal contains only
`["Ada sends her prepared message to Bo.", "It moves; Ada watches."]`. The claim never
reached the judge — `judge_user_prompt` is built exclusively from `journal.events()`,
i.e. `journal.event` records, and an intention is not one. The terminal came back
`UNRESOLVED`. The same claim written as a `private_update` becomes the actor's own
memory and reappears in that actor's own later views (correct: it is a belief), but never
in the journal, the world prompt, or the judge prompt.

The separation is structural in three independent places: intentions are routed to
`world_step` as a *trigger*, never to `journal.commit`; only `journal.commit` writes
`journal.event`; and only `journal.event` records are projected to the judge.

**Verdict: PASS.**

---

## Attack 8 — make the world choose an actor's intention

**Exact attack.** (a) A world response carrying an extra `"intentions": [...]` field
alongside a legal event. (b) The world commits an event whose *description* is an actor's
own decision — `"Bo decides to accept Ada's proposal and sends his agreement."` —
addressed to `ada_vance` with `observed: true`, with a judge scripted to cite it.
(c) Static check of every write site for `semantic.actor_call`.

**Expected safe behavior.** No world response may create, populate, or substitute for an
actor's intention. What a person decides comes only from that person's own model.

**Actual observed behavior.**
- (a) Rejected: `world response has unexpected fields ['intentions']`, both attempts, and
  the trajectory fails without committing.
- (c) `OP_ACTOR_CALL` has exactly **one** write site, inside `actor_step`, and its
  `intentions` come from `parsed["intentions"]` of the actor's own response. The world
  prompt contains no field, example, or affordance for an intention. The current
  `_after_commit` rule also hands the turn to the actor whenever an event is observed, so
  the environmental chain cannot continue past the moment someone becomes aware.
- (b) **Breach.** The narrated decision was committed as a journal event; **Bo's own
  model was never consulted**; the judge cited the event and the terminal returned
  **YES**. Nothing in `validate_event` or `journal.commit` inspects a description for
  actor agency. The comment in `_after_commit` — *"the environment can never decide what
  a person does about something they have just noticed"* — is true of the *control flow*,
  but not of the *content*: the world can narrate a decision that was never noticed by
  anyone in the first place.

**Verdict: PASS** structurally (no code path creates an intention).
**FAIL** semantically. **Severity: HIGH (F3)** — this attack produces a false terminal
YES, which is the highest-consequence outcome in the system.

---

## Attack 9 — make the world write several future stages in one response

**Exact attack.** (a) `event` as an array of two envelopes; (b) plural sibling fields
(`events`, `then`, `next_events`, `sequence`, `steps`); (c) nested follow-ups inside the
envelope (`then`, `followed_by`, `next`, `children`, `sub_events`); (d) end-to-end count
of committed events per world call across a 12-step run; (e) far-future and vague
durations; (f) a whole chain packed into one `description` string; (g) a `wakes` array of
50 entries.

**Expected safe behavior.** At most one event per world judgment; the step is bounded in
time.

**Actual observed behavior.**
- (a) rejected (`event must be an object`); (b) all five rejected by
  `validate_world_response`'s `additionalProperties`-style check; (c) all five rejected by
  `validate_event`'s field allowlist, with the message correctly naming `event_id`, time,
  cause and provenance as code-owned.
- (d) events-per-source across the whole run: every `world_call:cN` produced exactly
  **1**. The one-event limit holds end to end.
- (e) `45 days`, `365 days`, `10 years`, `next week`, `eventually` all rejected;
  `MAX_STEP_DAYS = 30` is enforced.
- (f) **Residual.** A single description narrating five stages
  (`"Ada sends the message, it arrives, Bo reads it the same afternoon, replies agreeing,
  and they schedule a call."`) commits as one event. This is irreducibly prompt-only —
  no mechanical check can distinguish it — and the world prompt does address it at length.
  Recorded, not counted as a code failure.
- (g) **Residual.** One world response scheduled **50** wake events. `validate_wakes` has
  no cap. Note the asymmetry: `actor_mind` now caps `intentions` at 3 and
  `private_updates` at 6 *precisely because "every intention costs a world adjudication,
  so an unbounded list would let the model decide how much the runtime spends"* — the
  identical argument applies to wakes, which are uncapped. Combined with F1 this is also
  an amplifier: 50 wakes are 50 opportunities to inject a `reason` string.

**Verdict: PASS** on the stated property (the envelope allows at most one event).
**Severity: MEDIUM** for the two residuals (F6 uncapped wakes, F7 multi-stage prose).

---

## Attack 10 — expose the terminal and consequence models to each other

**Exact attack.** Tag the world's `judgment` text, the judge's `explanation` text, the
actor's `decision` text, the wake `reason`, actor intentions and actor memories with
distinct sentinels; run a full trajectory through delivery / notice / read; then search
every prompt of every role for every sentinel, in both directions. Separately: check
whether terminal records leak through the ledger projection, and whether the judge can
distinguish availability from observation.

**Expected safe behavior.** The judge sees the resolution, the time, and committed
events. The world and the actors never see the resolution, the judge, the terminal
status, or the deadline.

**Actual observed behavior.** Judge prompts exclude, verified individually: world
judgment prose, actor decision prose, wake reasons, actor private memories, actor
intentions, all visibility metadata (`available to:` / `NOT observed` never appear), and
any `BACKGROUND` / `their circumstances` block. `judge_user_prompt` renders only
`event_id`, `t`, `description`.

World and actor prompts exclude, verified individually: the resolution, judge
explanations, the literal status words `UNRESOLVED` / `NO_AT_CUTOFF`, and the cutoff
instant. Actor prompts additionally exclude world judgment prose, the world's
availability metadata, and other actors' decisions.

Terminal containment through the ledger is real rather than incidental: 5
`semantic.terminal_check` records and 4 `semantic.world_call` records existed in the
ledger, and `journal.render_for_world()` — which projects from that same ledger —
contains neither, because it filters to `OP_EVENT` alone.

**Residual (F5).** The judge is *not* shown the `observed` flag. In the probe, the
event `"Bo's reply arrives in Ada's inbox, unread."` (`observed: false`) was presented to
the judge indistinguishably from an observed event. The runtime's central distinction —
available vs. observed, maintained rigorously everywhere else — is discarded at exactly
the moment the terminal question is asked. Resolutions phrased about awareness
("...once Ada has seen it") can therefore be satisfied by an availability event.

**Verdict: PASS. Severity: MEDIUM** for the residual.

---

## Cross-cutting finding F4 — no delimiting or escaping at any role boundary

Probed in `a11_injection.py`; all four attempts succeeded.

| # | Direction | Result |
|---|-----------|--------|
| 11a | actor → world | An `intentions[]` string containing newlines and the world prompt's own headings appended a forged `ITEMS AVAILABLE TO THEM THAT THEY HAVE NOT YET OBSERVED` block (with a fabricated `(e99)` id) and a second `THE TRIGGER YOU MUST JUDGE (system_override)` section to the world prompt. |
| 11b | world → actor | A `wakes[].reason` forged a complete `WHAT YOU HAVE OBSERVED` entry **and** a `YOUR PRIVATE MEMORIES, BELIEFS, AND PLANS` entry inside the actor's view — neither backed by any ledger record. Ground truth confirmed clean: `view["observed_events"] == []` and only the genesis event exists. |
| 11c | actor → itself | A `private_updates[]` string forged a `WHAT YOU HAVE OBSERVED` line in 10 of that actor's own 11 later prompts. |
| 11d | world → actor | An `event.description` containing newlines is rendered verbatim under `- {t}: {description}`, injecting a forged `WHY YOU ARE CONSIDERING THINGS NOW` block. |

`render_view` builds the prompt by `"\n".join(parts)` with no escaping, and
`world_user_prompt` interpolates `trigger_text` with an f-string. 11b is the sharpest:
the ledger and the prompt disagree about what the actor has observed, and the ledger —
the thing replay verifies — shows nothing wrong. This is the mechanism that makes F1, F2
and F3 sharp rather than theoretical.

**Severity: HIGH.**

---

## Secondary findings

**F8 — an envelope rejection is not retried (MEDIUM/LOW).** `validate_event` and
`validate_wakes` run in `world_step`, *after* `caller.ask` has already returned `"ok"`.
A schema-shaped but envelope-invalid world response therefore raises `EnvelopeError`,
propagates to the outer handler, and kills the whole trajectory after **1** world call —
whereas malformed JSON correctly gets exactly 2 attempts. Transactional safety is intact
(nothing commits; validation precedes `world.apply(OP_WORLD_CALL)`, and no `world_call`
record was written for the rejected response), but one bad `for` list ends a run that a
retry would very likely have recovered. Note `tests/test_semantic_runtime.py::
test_invalid_world_output_commits_nothing_after_one_retry` asserts the failure but not
the retry, and its name overstates what happens.

**F9 — declared "provider-native strict schemas" are never sent (LOW).**
`EVENT_SCHEMA` (documented as *"Provider-native strict schema for a proposed event"*),
`WORLD_SCHEMA` and `RESOLUTION_SCHEMA` are defined but referenced by nothing except each
other. `llm.py` sends `response_format: {"type": "json_object"}`, not `json_schema`.
All real enforcement is the hand-written validators — which are correct and are what every
probe above actually hit — but the declarations are dead code that reads as a guarantee.
(`ACTOR_SCHEMA` was deleted from `actor_mind.py` during this audit; the other three remain.)

**F10 — no runtime guard on a resolution smuggled through a compiler field (LOW).**
See attack 6. Compiler-contract obligation; worth one assertion in the adapter.

**F11 — artifacts persist every actor's private context (LOW / informational).**
`write_artifacts` writes `initial_actor_states.json` (all `private_context` values) and
`actor_views.jsonl` (complete rendered views) under `artifacts/`, inside the repo tree.
Correct and desirable for research inspection; noted only because these files sit in a
directory that gets committed.

---

## Recommendations, in priority order

1. **Constrain or eliminate the `wakes[].reason` → actor-prompt path (F1).** The reason
   is a *scheduling* justification, not information the actor has. Either drop it from
   `view["reasons"]` and render only a code-authored string, or restrict what may appear
   there to text derived from records the actor has actually observed.
2. **Escape or fence every model-authored string at each boundary (F4).** Collapse
   newlines, or wrap interpolated text in explicit delimiters, in `render_view`
   (`reasons`, `private_memories`, `observed_events[].description`) and in
   `world_user_prompt` (`trigger_text`).
3. **Decide explicitly what containment `private_context` has (F2).** It is currently
   given to the world model and can be re-emitted into any actor's view and to the judge.
   Either stop passing it to the world, pass a code-summarised form, or document that its
   guarantee is prompt-level only — the module docstrings currently read as if it were
   structural.
4. **Consider a code-level check that a committed event's audience and the actor whose
   agency it narrates are consistent (F3)** — at minimum, record and surface the case
   where an event's `for` list excludes an actor whose decision it describes.
5. **Cap `wakes` in `validate_wakes` (F6)**, matching the reasoning already written down
   for `MAX_INTENTIONS_PER_TURN`.
6. **Show the judge each event's `observed` flag, or withhold unobserved events from it
   (F5).**
7. **Move envelope validation inside the `caller.ask` validator (F8)** so a bad envelope
   gets the same single retry as malformed JSON.
8. **Delete the unused schema constants or actually send them (F9).**

---

## Appendix — reproduction

```bash
cd /tmp/claude-0/-home-user-SWORLDMODEL-GROUND-UP/d6ed917c-38bc-56aa-a050-80f5be912f4e/scratchpad/audit_boundary
for f in a1_private_memory a2_unobserved a4_context a6_resolution \
         a7_actor_success a9_multistage a10_role_separation \
         a11_injection a12_transactional; do
  echo "===== $f ====="; python "$f.py"
done
```

Each probe prints `[SAFE]` / `[BREACH]` per assertion and exits non-zero if any breach
was reproduced. `diag_prompts.py` dumps every prompt the pipeline builds, by role and
trigger, for manual inspection.
