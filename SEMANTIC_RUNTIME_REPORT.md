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

**Modified**: nothing outside the new files. The diff against `main`
touches no pre-existing production file.

## 4. Proof the frozen compiler files are unchanged

`artifacts/semantic_runtime/COMPILER_FREEZE.txt` records the git blob hash
of every one of the 24 compiler production files, taken before any work in
this phase began. `tests/test_compiler_runtime_integration.py::test_frozen_compiler_files_are_unchanged`
re-reads `git ls-files -s compiler/` on every test run and asserts both that
every recorded blob matches and that the file set is identical (nothing
added or removed).

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
