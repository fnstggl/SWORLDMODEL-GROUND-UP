# SEMANTIC RUNTIME REPORT

One live, single-trajectory, LLM-native social simulation loop, built on the
frozen minimal world compiler and the existing persistent runtime.

The bet this phase tests: **flexible social meaning can stay natural
language, while a thin deterministic shell reliably preserves time,
information boundaries, identity, causality, memory, terminal lineage and
replay.**

The division of labour is absolute and is visible in every module:

> **LLMs write meaning. Code controls access, time, identity, persistence,
> causality and replay.**

---

## 1. Exact active production call graph

```
run_simulation.py
  |
  |-- compiler.compile_scene(question, start, cutoff)        [FROZEN, unchanged]
  |       -> SceneManifest {actors, shared_context, starting_events, resolution}
  |
  |-- semantic_runtime.adapter.instantiate_scene_manifest(scene, q, start, cutoff)
  |       -> (World, Journal, bindings)          # existing kernel, no new one
  |
  |-- semantic_runtime.trajectory.budget_for(max_steps, actors, starting_events)
  |       -> call ceiling derived from the scene's own shape
  |
  |-- semantic_runtime.trajectory.run_trajectory(world, journal, bindings,
  |                                              resolution, caller, ...)
  |       judge(final=False)                 # terminal must be false at init
  |       for each starting event:
  |           world_step(trigger_kind="starting_event")
  |           observed -> actor_step(...)
  |       while steps < max_steps and budget remains:
  |           ev = world.queue.pop()                     # kernel queue
  |           world.clock.advance_to(ev.t)               # kernel clock
  |           K_EVENT -> journal.commit(envelope)        # kernel ledger
  |                      journal.mark_observed(concerns) # if attention arrived
  |                      _after_commit:
  |                          observed -> actor_step  (the person's turn)
  |                          else     -> world_step  (the environment's turn)
  |           K_WAKE  -> pending items  -> world_step("pending_progression")
  |                      nothing pending -> actor_step (time has passed)
  |           judge(final=False)                        # YES ends the run
  |       finish(reason): clock -> cutoff, judge(final=True)   # YES or NO
  |
  |-- semantic_runtime.replay.replay_trajectory(world.records, live_world)
  |       -> World.from_records(...)          # zero provider calls
  |
  `-- semantic_runtime.trace.write_artifacts(out_dir, ...)
```

Three semantic roles, and only three:

| role  | asks | may write | never sees |
|-------|------|-----------|------------|
| actor | "given only what you know, what do you attempt?" | `decision`, `intentions`, `private_updates` | the journal, other actors' minds, unobserved items, the resolution |
| world | "what concretely happens next, from this one trigger?" | `judgment`, one `event`, `wakes` | the resolution, the question, the cutoff |
| judge | "do the committed events satisfy the resolution?" | `status`, `supporting_event_ids`, `explanation` | prompts, intentions, memories, judgments — only committed events |

## 2. Exact compiler-to-runtime binding

`sworldmodel/semantic_runtime/adapter.py` consumes the compiler's four
fields mechanically. Nothing is re-prompted, re-schematised, enriched or
re-interpreted:

| manifest field | becomes |
|---|---|
| `actors[].name` | a kernel `ActorState` (`actor.add`), id derived deterministically from the name |
| `actors[].private_context` | a `semantic.actor_profile` ledger record, readable only through that actor's own view |
| `shared_context` | one immutable fact (`scene:shared_context`), given to every actor |
| `starting_events[]` | journal events committed at genesis (if at/before start) or scheduled on the kernel queue (if later) |
| `resolution` | **not passed to the adapter at all** — it reaches only the read-only judge |

`CONSUMED_FIELDS = ("actors", "shared_context", "starting_events")`. The
resolution's exclusion is enforced by a test that asserts the resolution
string appears in no ledger record and in no rendered actor view
(`tests/test_compiler_runtime_integration.py::test_adapter_never_consumes_or_exposes_the_resolution`).

## 3. Files added, reused, and modified

**Added** (1,755 lines, `sworldmodel/semantic_runtime/`):

| file | lines | responsibility |
|---|---|---|
| `envelope.py` | 180 | the four-field event envelope, duration grammar, containment of model-written text |
| `journal.py` | 143 | append-only committed history projected from the kernel ledger; observation transitions |
| `views.py` | 94 | code-only actor-local view construction and rendering |
| `actor_mind.py` | 100 | the one universal actor prompt + response validation and caps |
| `world_mind.py` | 199 | the one universal world prompt + response/envelope/wake validation |
| `resolution.py` | 133 | the read-only judge prompt + the terminal rules code enforces |
| `trajectory.py` | 396 | orchestration: turn handoff, scheduling, transactions, budget, horizon |
| `llm.py` | 199 | provider transport, deadlines, one corrective retry, full per-call logging |
| `replay.py` | 62 | zero-call replay verification |
| `trace.py` | 128 | the artifact set |
| `adapter.py` | 98 | manifest -> existing runtime |
| `__init__.py` | 23 | public surface |

Plus `run_simulation.py` (CLI), `tests/test_semantic_runtime.py`,
`tests/test_compiler_runtime_integration.py`.

**Reused, unmodified**: the entire existing kernel — `World.apply` (ledger,
immutability, sequence numbers, causality), `World.schedule` / `EventQueue`,
`Clock`, `ActorState`, the `actor.memory` reducer, `World.from_records`.
The runtime adds **no** reducer and **no** kernel change; its ops
(`journal.event`, `journal.observed`, `semantic.*`) are trace-only records
that the journal projects.

**Modified**: exactly one pre-existing file,
`tests/test_hardcoding_guard.py`, because an audit showed the guard listed
directories non-recursively and therefore scanned none of the new package.
No pre-existing *production* file is touched, which is checkable:
`git diff --name-status $(git merge-base origin/main HEAD) HEAD` shows
additions and that one test.

## 4. Proof the frozen compiler files are unchanged

`artifacts/semantic_runtime/COMPILER_FREEZE.txt` records the git blob hash
of every one of the 24 compiler production files, taken before any work in
this phase began.
`tests/test_compiler_runtime_integration.py::test_frozen_compiler_files_are_unchanged`
hashes the files **on disk** with `git hash-object` on every test run,
asserts the file set is identical, and asserts there are no untracked
files inside `compiler/`.

It reads the working tree deliberately. The first version of this test
read the git index, and an independent auditor defeated it twice: an
unstaged edit adding a live `_audit_backdoor()` to
`compiler/scene_pipeline.py` passed, and so did an entirely new untracked
`compiler/audit_second_stage.py`. Both are caught now; I reproduced both
attacks against the current test and both fail it.

The same auditor verified the record independently: the 24 hashes match
the index, the working tree, **and** the pre-phase merge-base tree, so the
freeze really is the state before this phase began, and
`git log origin/main..HEAD -- compiler/` is empty.

## 5. Proof no second runtime exists

- `instantiate_scene_manifest` returns the kernel's own `World`; a test
  asserts `isinstance(world, World)`, `isinstance(world.queue, EventQueue)`,
  `isinstance(world.clock, Clock)`.
- Every state change goes through `World.apply`; the journal is a
  *projection*, not storage. There is no second ledger, clock, queue, actor
  table, or memory store.
- `import sworldmodel.semantic_runtime` pulls in zero `compiler.*` modules
  (verified by the universality audit).
- No capability menu, action registry, effect language, handler table or
  scenario router exists anywhere in the runtime.

## 6. Actor response schema

```json
{"decision": "one or two sentences",
 "intentions": ["a concrete action attempted now"],
 "private_updates": ["a memory, belief, plan or commitment now held"]}
```

Enforced in code by `actor_mind.validate_actor_response`: required
`decision` (non-empty string), both arrays optional and string-only, **no
additional properties**, `intentions` capped at `MAX_INTENTIONS_PER_TURN = 3`
and `private_updates` at 6 — because every intention costs a world
adjudication, so an uncapped list would let the model decide how much the
runtime spends.

An actor proposes and never adjudicates: success, delivery, another
person's observation, another person's belief and the terminal are all
world consequences.

## 7. World response schema

```json
{"judgment": "one or two sentences grounded in the current situation",
 "event": {"description": "...", "for": ["actor_id"],
           "observed": false, "after": "43 seconds"},
 "wakes": [{"actor": "actor_id", "after": "2 hours", "reason": "..."}]}
```

`event` may be `null`. At most **one** immediate event per judgment — the
world is asked for the next step, never a chain of future stages. `wakes`
is capped at `MAX_WAKES_PER_JUDGMENT = 4` for the same budget reason.
Enforced by `world_mind.make_world_validator`, which validates the
response, its envelope and its wakes **inside** the call, so an unusable
answer is retried once instead of ending the run.

## 8. Event envelope

Exactly four fields the model may write:

| field | meaning |
|---|---|
| `description` | what concretely happened, in plain language |
| `for` | which actors the event or its information becomes **available** to |
| `observed` | whether every actor in `for` has actually observed it |
| `after` | how much simulated time passes first |

Code owns everything else: `event_id`, the authoritative timestamp,
`source`, `cause`, `trajectory_id` and model-call provenance. Any attempt to
write one of those, or a `probability`/`weight`/`score`/`confidence` field,
is rejected before anything is committed.

`after` is universal time bookkeeping: `"now"`, or one or more
`<number> <unit>` parts (`"43 seconds"`, `"1 hour 30 minutes"`), bounded to
a 30-day single step. It is not a social-action vocabulary.

## 9. Local-view construction logic

No LLM builds or filters a view. `views.build_view` selects by exact
identity and stored visibility state:

```python
actor_id in event["for"]  AND  actor_id in event["observed_by"]
```

There is no semantic search, vector retrieval, salience weighting,
importance scoring or relevance ranking. Everything else in the view
(identity, that actor's own private context, the immutable shared context,
their own private memories, the current simulated time) is added *by
identity*.

Even the "why you are being consulted now" line is composed by code from
that actor's **own observed records**: callers pass event **ids**, never
prose, so nothing another role wrote can enter a view except through an
event code has already established the actor observed. When there is no
such event, the line is a fixed constant: *"time has passed and you are
looking at your situation again."*

Every model-written string placed in any prompt passes through
`envelope.contained` first, which flattens whitespace so the string
occupies exactly the one line code gave it and cannot forge a section
heading in a view, a world prompt or a judgment.

## 10. Memory-storage logic

An actor's `private_updates` are written through the **existing kernel
reducer** (`world.apply("actor.memory", ...)`) with `kind="private"` and
the originating call id as `source`. They are read back only via
`world.actors[actor_id].memories` for that same actor. The world model has
no parameter through which it could ever receive them.

## 11. Attention and observation lifecycle

The lifecycle is kept genuinely separate, and separation is mechanical, not
advisory:

```
exists -> sent -> arrives somewhere it could be seen -> reaches attention
       -> is read -> is understood
```

- An event with `observed: false` is **available**, not observed. It appears
  in no view. Code never converts availability into observation.
- Attention is a concrete situated event: the world is asked what in fact
  becomes of a pending item given the circumstances, and may legitimately
  answer that it simply sits there. It is never a probability.
- **Noticing settles the item it concerns.** When a step asks "what becomes
  of these pending items" and the answer is that attention reached them,
  code records an observation transition (`journal.observed`, append-only)
  on the original item at the instant it occurs. The original record is
  never rewritten. Without this an item stayed "available, not observed"
  forever and the runtime kept re-asking about something already dealt with.
- **Turn handoff is mechanical**: a committed event that is observed by
  someone hands the turn to *that person's* model; an unobserved one
  continues as the environment's turn, bounded to `MAX_ENV_CHAIN = 3`
  consecutive environmental steps before time is simply allowed to pass.
  This is what makes it impossible for the world to decide what a person
  does about something they have just noticed.
- A **wake carries timing only**. The world's stated reason is recorded in
  the ledger for tracing and is shown to no one — a person learns things
  only by observing events.

## 12. Terminal lineage rules

Enforced in `resolution.make_validator`, in code:

- YES must cite at least one committed event, and every cited id must exist.
- Only committed journal events are ever shown to the judge, so an
  intention, a private belief or a world judgment can never satisfy YES.
- `NO_AT_CUTOFF` is impossible before the cutoff instant.
- `UNRESOLVED` is impossible **at** the cutoff: the horizon is where a
  question stops being open, so the final judgment is YES or NO.
- The terminal is checked before anything runs, and a scene that already
  satisfies its own resolution at initialization is reported as such rather
  than being simulated.

The judge is read-only: it is handed plain copies and nothing from its
answer is committed except the check record itself. It is also told, for
each event, who it reached and who actually observed it — so a resolution
that requires a person to *know* something cannot be satisfied by an event
that merely arrived.

## 13. Retry and transaction behaviour

- **Everything is validated before anything is committed.** A world step
  validates the response, the envelope and the wakes, and only then writes
  the judgment record, schedules the event and schedules the wakes. A
  rejected response commits nothing — no partial state exists at any point.
- **Exactly one retry per semantic call**, and the retry is *corrective*:
  the rejection reason is handed back so the model can fix precisely that.
  (It describes the shape of the reply and says nothing about the
  situation.) A repeat failure is a structured `RuntimeTechnicalFailure`,
  never a silent truncation.
- **Deadlines**: a 90 s socket timeout, a 240 s total read deadline and a
  270 s whole-request wall deadline, so a stalled provider cannot hang a run.
- **Budget**: the call ceiling is derived from the scene's own shape
  (`budget_for`), so it sits provably above the ordinary path and can only
  fire on genuine runaway. Spending it is a **horizon, not a failure** —
  reserved calls guarantee an honest final judgment of the trajectory that
  actually occurred.

<!-- SECTIONS 14-21 ARE FILLED FROM THE FINAL RUNS AND AUDITS -->

## 14. Invariant-test results

`python3 -m pytest tests/ -q` → **223 passed**, of which 36 are specific to
this phase (33 in `tests/test_semantic_runtime.py`, 4 in
`tests/test_compiler_runtime_integration.py`, plus the universality-guard
coverage test). Every test in the suite is deterministic and calls no
provider.

The invariants each one holds down:

| invariant | test |
|---|---|
| the adapter consumes four fields and is deterministic | `test_adapter_consumes_the_four_fields_only_and_is_deterministic` |
| private context never crosses actors | `test_private_context_never_leaks_between_actors` |
| an unobserved event is in nobody's view | `test_unobserved_events_never_enter_a_view` |
| an observed event reaches only the actors named | `test_observed_event_reaches_only_actors_named_in_for` |
| durations parse, in one part or several; nothing else does | `test_duration_grammar_and_rejections`, `test_a_duration_may_be_written_in_several_parts` |
| code-owned fields and probability fields are refused | `test_event_envelope_rejects_unknown_actors_and_extra_fields`, `test_no_probability_or_weight_fields_are_accepted` |
| terminal rules are enforced in code | `test_terminal_rules_are_enforced_in_code`, `test_the_final_judgment_cannot_be_unresolved` |
| delivery ≠ noticing ≠ reading | `test_full_lifecycle_keeps_delivery_notice_and_read_distinct` |
| noticing settles the item, without rewriting it | `test_noticing_an_item_settles_that_item_without_rewriting_it` |
| observation hands the turn to the person, not the world | `test_observation_hands_the_turn_to_the_actor_not_the_world` |
| a person's own action gives them no fresh turn | `test_a_persons_own_action_does_not_hand_them_another_turn` |
| what a person does still travels afterwards | `test_what_a_person_does_still_travels_after_they_do_it` |
| the world cannot run long without asking anyone | `test_the_world_cannot_run_for_long_without_asking_anyone` |
| one instant cannot be subdivided forever | `test_one_instant_cannot_be_subdivided_forever` |
| silence does not end a situation before its horizon | `test_silence_does_not_end_a_situation_before_its_horizon` |
| intentions are not events | `test_intentions_are_not_committed_events` |
| a wake tells the woken person nothing | `test_a_wake_reason_never_reaches_the_person_it_wakes` |
| model text cannot forge a prompt section | `test_model_text_cannot_forge_a_section_of_a_view`, `..._of_the_world_prompt` |
| the model cannot set the runtime's budget | `test_the_model_cannot_set_the_runtime_budget` |
| the ceiling sits above the ordinary path | `test_the_call_ceiling_sits_above_the_ordinary_path` |
| a truncated run is incomplete and never answers NO | `test_a_truncated_run_is_incomplete_and_can_never_answer_no`, `test_spending_the_call_ceiling_is_a_horizon_not_a_failure` |
| a judgment cannot cite another trajectory | `test_a_judgment_cannot_cite_another_trajectory` |
| a scene with no window is refused | `test_a_scene_with_no_window_is_refused`, `test_a_starting_event_beyond_the_cutoff_is_never_scheduled` |
| unstorable text is repaired before commit | `test_unstorable_text_is_repaired_before_it_is_committed` |
| a verbose model cannot run up the bill | `test_a_merely_verbose_model_cannot_run_up_the_bill` |
| a rejected response commits nothing, once retried | `test_invalid_world_output_commits_nothing_after_one_retry`, `test_malformed_json_retries_once_then_fails_without_mutation` |
| the retry says what was wrong | `test_a_retry_is_told_exactly_what_was_wrong` |
| time never moves backwards; the cutoff holds | `test_time_never_moves_backward_and_cutoff_is_respected` |
| reaching the horizon is recorded | `test_reaching_the_horizon_is_recorded_so_the_run_stays_replayable` |
| replay is exact and calls no model | `test_replay_is_exact_and_calls_no_model`, `test_replay_measures_rather_than_asserts_zero_calls` |
| **and the replay check can fail** | `test_replay_detects_a_forged_terminal`, `test_replay_detects_deleted_and_rewritten_provenance`, `test_replay_detects_a_rewritten_event_that_no_hash_covers`, `test_replay_checks_the_ledger_on_its_own_terms`, `test_replay_reports_itself_vacuous_when_there_is_nothing_to_verify` |
| the compiler is frozen, on disk, including untracked files | `test_frozen_compiler_files_are_unchanged` |
| the universality guard covers every production file | `test_every_production_file_is_actually_scanned` |

## 16. Adversarial findings, and 17. what was done about each

Six independent auditors, none of which wrote the code. Full reports are in
`artifacts/semantic_runtime/`. Every CRITICAL and HIGH is listed here with
its resolution.

### Universality and bloat — 0 CRITICAL, 3 HIGH

| finding | resolution |
|---|---|
| the model controlled the runtime's call budget: 500 intentions in one turn consumed the entire budget and failed the run | intentions capped at 3, wakes at 4, both enforced by the validators |
| `max_steps=40` and `max_calls=400` were inconsistent — an ordinary 3-actor run died on the "runaway backstop", turning a legitimate cutoff into `failed` | the ceiling is derived from the scene's shape (`budget_for`) and spending it is a horizon, not a failure |
| four JSON-Schema constants advertised provider-native enforcement that never happened — no schema ever reached a provider | removed; the docstrings now say where enforcement actually lives, which is the tested validators |

Confirmed by the same audit: no scenario routing, no duplicate kernel, and
`import sworldmodel.semantic_runtime` pulls in **zero** `compiler.*` modules.

### Information boundaries — 0 CRITICAL, 4 HIGH

| finding | resolution |
|---|---|
| `wakes[].reason` was an unvalidated world→actor channel that bypassed the observation model — an actor was told the content of an event it had not observed, and another actor's private context | a wake now carries timing only; the reason is recorded and shown to no one. Views are built from event **ids** that code looks up in that actor's own observed records |
| the world could re-emit a person's private context, or raw intention text, as a committed public event | prompt rule: what you are shown about a person's circumstances is background for your judgment and never goes inside an event. **Accepted residual** — see §18 |
| the world could narrate an actor's decision as a committed event, producing a false YES with that actor's model never consulted | partially structural: the turn-handoff rule, and now the bound on how long the world may run without consulting anyone. **Accepted residual** — see §18 |
| no escaping or delimiting at any role boundary: model text forged section headings in views, world prompts and judgments | every model-written string is flattened before it enters any prompt, so it cannot begin a line it was not given |

Verified clean by the same audit: resolution containment (16/16 judge
prompts, 0 world, 0 actor, 0 ledger records), and an actor's success claim
cannot reach the judge because the judge's prompt is built only from
`journal.event` records.

### Time, causality and the terminal — 1 CRITICAL, 4 HIGH

| finding | resolution |
|---|---|
| **CRITICAL** a call-ceiling truncation was laundered into a definitive `NO_AT_CUTOFF` over time never simulated — the branch preventing it was unconditionally dead, and a passing test enshrined the bug | closing judgments are always paid for out of the reserve; the budget path is explicitly a truncation. The test now asserts the rule |
| `failed` claimed nothing partial was committed; the transaction boundary is the call, not the step | the status documents exactly what it guarantees: no response is ever partially committed, and records from calls that already completed remain, because those things happened |
| judge citations were not scoped to the trajectory | the journal is scoped by trajectory identity, and replay picks the scope up from the scene |
| `cause` is never validated at write time in the kernel | replay now checks it: every cause must exist and precede its record. **Write-time prevention remains open** — see §18 |
| `start > cutoff` was accepted, and events could commit beyond the cutoff | a scene with no window is refused; a starting event past the cutoff is never scheduled |

### Hostile model output and no-probabilities — 1 CRITICAL, 3 HIGH

Across 1,584 hostile trajectories and 114 malformed payloads, the
transactional core held: nothing escaped `run_trajectory`, no invalid
response was committed, no call committed twice, and **0 of 476** attempts
to write a code-owned field reached the ledger.

| finding | resolution |
|---|---|
| **CRITICAL** one lone UTF-16 surrogate passed every check, then killed the artifact write and `ledger.jsonl` with it | model text is repaired at the validation boundary; artifact writes survive bad content; the ledger is written first |
| a hostile final judgment left the run unreplayable, because the clock was advanced to the cutoff without a record | reaching the horizon is a ledger record |
| the ceiling counted calls, not bytes: a compliant but verbose model turned a 1.8M-character run into 44M at the same call count | every model-written string is capped, the rejection echoed on a retry is bounded, and the response body has a size limit |
| probabilities are rejected as fields but accepted without limit as text | **accepted residual** — see §18 |

### Replay and determinism — 3 CRITICAL, 4 HIGH

A forged ledger sharing only 68 of a real run's 149 records was certified
`exact`.

| finding | resolution |
|---|---|
| **CRITICAL** the reconstruction shared its record objects with what it was compared to, so `terminal_matches` was `x == x` | records are deep-copied; the two sides share no object |
| **CRITICAL** 40–55% of a ledger was deletable or fabricable undetected, because the state hash covers only reduced state and every record this runtime writes is trace-only | the whole ledger is compared record for record, and events, observations, memories, views and terminal lineage each field by field |
| **CRITICAL** `World.from_records` enforces no causality at all | replay checks the ledger on its own terms: contiguous sequence numbers, non-decreasing time, every cause existing and preceding its record, every observation naming an event that reached that actor, every YES citing events that exist |
| `exact=True` was vacuous on an empty or failed run | a verification with nothing to verify reports itself vacuous and is never `exact` |
| event timestamps, descriptions and audiences were never compared | all compared |
| memories compared only content | all fields compared |
| replay never read the persisted ledger, and `llm_calls: 0` was a literal | replay reads `ledger.jsonl` back from disk, and the call count is measured across the reconstruction |

Verified clean: byte-identical ledgers across five `PYTHONHASHSEED`
values, adapter determinism, and observation transitions surviving replay
exactly.

### Compiler freeze and integration — 0 CRITICAL, 3 HIGH

| finding | resolution |
|---|---|
| the freeze test read the git **index**, so an unstaged live backdoor in `compiler/scene_pipeline.py` passed, as did an untracked new module | it now hashes the files on disk and refuses untracked files. Verified by tampering both ways |
| the universality guard listed directories non-recursively, so `sworldmodel/semantic_runtime/` was scanned by **nothing**: an injected `is_email_scenario()` passed the guard and the entire suite | the guard walks every production file, and a second test asserts the coverage it claims. Verified by injection |
| the freeze covers `compiler/` but not the kernel modules the compiler imports | the branch modifies no pre-existing file except that one broken guard test — checkable with `git diff --name-status $(git merge-base origin/main HEAD) HEAD` |

Verified: 24 compiler files, hashes matching the index, the working tree
**and** the pre-phase merge-base tree; four state-changing kernel ops used,
all pre-existing; no reducer added; every domain-word hit in the runtime a
substring (`ada` in "adapter", `deal` in "dealing").

### Actor/world separation — 1 CRITICAL, 3 HIGH

This audit measured what the prompt-only STOP RULE was actually buying:
across five live runs, **56 of 163 committed events were person-choices the
world wrote** rather than that person's own model.

| finding | resolution |
|---|---|
| **CRITICAL** the STOP RULE has no code counterpart; a world response narrating "Bo reads, decides, agrees and replies" committed verbatim and produced a YES with Bo's model consulted zero times | it cannot be made one — see §18. What code now guarantees is the **rate**: the world may not run more than six steps in a row without a person being consulted |
| the world could starve an actor of their turn by writing their acts with `observed: false` | same bound; the turn comes back regardless of what the world writes |
| the STOP RULE lists only positive verbs — "does not open", "decides against" are unforbidden | same bound. **Accepted residual** |
| the actor docstring claimed third-party success claims "are rejected as intentions" — they are not | the docstring now says what is true: nothing an actor writes is committed as having happened, and the claim is handed to the world as an attempt |

Verified clean by the same audit: an actor's claim cannot become a fact
(`journal.commit` has two call sites, and the journal projects only
`journal.event` records); an actor cannot write another actor's memory; the
resolution, question and cutoff never reach the world or actors; and no
reverse leak from the judge into any prompt.

## 18. Unresolved limitations

Stated plainly, because each is a real boundary of what this phase
guarantees.

1. **A model can write a sentence that narrates someone's choice.** Code
   controls who is *consulted*, who *sees* what, when things happen and
   what is *committed* — but deciding whether a sentence narrates a choice
   requires reading it, which needs a model, not a validator. Mitigations
   are structural (the turn-handoff rule, the six-step bound on the world
   running alone, the STOP RULE in the prompt) and they reduce it; they do
   not eliminate it. A run's trace makes every instance visible and
   attributable.
2. **A hostile model can put a probability in a sentence.** Every
   probability, weight and score *field* is rejected, and no code anywhere
   reads such text as a number, so it cannot influence the runtime. A
   lexical filter would reject legitimate content — a quoted forecast, a
   price — so there is none.
3. **The world sees the shared context, which may mention a deadline.**
   That is realistic: people in a situation know its deadlines. The
   *resolution* never reaches it, which is the boundary that matters and is
   verified.
4. **`cause` is not validated at write time in the kernel.** Replay detects
   a dangling or forged cause; `World.apply` would still accept one. The
   kernel is outside this phase's scope, so the check lives in replay.
5. **A step is not a transaction; a call is.** A rejected response commits
   nothing, but if the second of an actor's three intentions fails
   technically, the first one's consequences remain committed — because
   they happened.
6. **No live retrieval.** Everything the world contains comes from the
   compiled scene. No claim is made about current real-world facts beyond
   what the compiler put there.
