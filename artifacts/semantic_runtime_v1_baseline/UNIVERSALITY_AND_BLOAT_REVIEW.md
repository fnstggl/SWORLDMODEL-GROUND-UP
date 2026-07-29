# Universality and Bloat Review — `sworldmodel/semantic_runtime`

**Scope reviewed:** `sworldmodel/semantic_runtime/*.py` (12 modules, 1,486 lines),
`run_simulation.py` (97 lines), `tests/test_semantic_runtime.py`,
`tests/test_compiler_runtime_integration.py`.
**Branch:** `claude/sworldmodel-semantic-runtime` @ `ed97646`
**Mode:** read-only. No implementation file was modified.

---

## Verdict

**The runtime does NOT move the old compiler's complexity into the runtime.**

Searched for, and did **not** find, any of:

| Rejected pattern | Result |
|---|---|
| Scenario keyword routing in executable code | **none** |
| Branching on question wording / actor names / medium / industry / institution / category | **none** |
| Email-, negotiation-, committee-, meeting-specific logic | **none** |
| Capability menu / action registry / verb ontology | **none** |
| Effect language / handler registry / dispatch table | **none** |
| Second intermediate representation | **none** |
| Second `World`, `Clock`, `EventQueue`, compiler, or replay engine | **none** |
| Duplicate world-state system | **none** (the `Journal` is a pure projection) |

The defects below are **budget/bound and dead-code defects**, not architectural
regression. Three are HIGH; none are CRITICAL.

---

## Verification (real commands, real output)

### V1 — `import sworldmodel.semantic_runtime` does not import `compiler.legacy`

```
$ python3 -c "import sys, sworldmodel.semantic_runtime as sr; \
  print([m for m in sys.modules if m=='compiler' or m.startswith('compiler.')])"
compiler modules pulled in: NONE
PASS
```

Zero `compiler.*` modules enter `sys.modules`. The only static import of
`compiler` in scope is `run_simulation.py:21`
(`from compiler import SceneCaller, compile_scene`) — the CLI entry point
invoking the frozen compiler, not the runtime library. No runtime module
imports `compiler` at all (`sworldmodel/semantic_runtime/*.py` import only
`sworldmodel`, `sworldmodel.simclock`, siblings, and stdlib).

### V2 — no scenario families in executable lines

Method: `tokenize` each module and split tokens into two populations —
`NAME`/`NUMBER` (executable) versus `STRING`/`COMMENT` — then scan each
population separately against ~70 scenario-family terms with word boundaries.

**Executable-token hits: 3, all false positives.**

```
sworldmodel/semantic_runtime/adapter.py:35   'lower'    -> name.lower()          (str method)
sworldmodel/semantic_runtime/envelope.py:45  'compile'  -> re.compile(...)       (regex)
sworldmodel/semantic_runtime/envelope.py:60  'lower'    -> text.strip().lower()  (str method)
run_simulation.py:49                         'lower'    -> args.question.lower() (filename slug)
run_simulation.py:21                         'compiler' -> frozen compiler entry point
```

**String/prompt hits: 3, all doctrine or transport.**

```
actor_mind.py:1   "one universal prompt for every scenario"   (doctrine)
world_mind.py:1   "one universal prompt for every scenario"   (doctrine)
llm.py:22,24      "api.deepseek.com/chat/completions", "deepseek-chat"  (endpoint)
```

**Prompts verified free of scenario families.** `WORLD_SYSTEM`
(world_mind.py:43-103), `ACTOR_SYSTEM` (actor_mind.py:31-64) and
`JUDGE_SYSTEM` (resolution.py:36-56) name no medium, institution, industry,
role or scenario category. Their only concrete verbs — "send", "arrive",
"notice", "read" — appear as doctrine about *step granularity*
(world_mind.py:48-51: "the immediate consequence is the sending, not the
receiving, the noticing, the reading") and about universal human behaviour
(actor_mind.py:51: "slow to reply"), never as routing conditions. No prompt
enumerates action types.

### V3 — every branch is on machinery, never on content

Every string comparison in the runtime, via AST walk:

```
llm.py:67          "error" in box
resolution.py:102  status == "YES"
resolution.py:105  status == "NO_AT_CUTOFF"
trajectory.py:209  r["op"] == "genesis.sealed"
trajectory.py:212  first["status"] == "YES"
trajectory.py:296  checked["status"] == "YES"
trajectory.py:307  final["status"] == "YES"
trajectory.py:237  ev.kind == K_EVENT       # 2 queue kinds, inline if/elif
trajectory.py:267  ev.kind == K_WAKE
views.py:26        m.kind == "private"
journal.py:60      r["op"] != OP_EVENT
trace.py:52,56,62,63,65,93,101,115,122,125   ledger op names / trace kinds / caller roles
```

All are internal machinery constants: kernel ledger op names, the three judge
statuses, two queue kinds, three caller roles, trace record kinds. **No branch
reads the question, an actor name, a medium, an industry, an institution or a
category.** No `match` statements. No dispatch dict keyed on content.

### V4 — the kernel is the only source of time, queue, state and replay

```
$ grep -n "^class " sworldmodel/semantic_runtime/*.py
```
yields only `Journal`, `RuntimeCaller`, `Trace`, `SemanticTrajectory`, and four
exception classes. **No `World`, no `Clock`, no `EventQueue`.**

No `heapq`, `deque`, `PriorityQueue`, `datetime.now`, `self.now`, `self.clock`,
`self.queue`, `self.state` anywhere in the runtime. Confirmed usage:

- time — `world.clock.now`, `world.clock.advance_to` (trajectory.py:59, 84, 116, 129, 141, 230-231, 305-306; views.py:30)
- queue — `world.queue.peek/pop`, `world.schedule` (trajectory.py:86, 131, 143, 226, 229, 265, 289; adapter.py:94)
- state — `world.apply` exclusively (adapter.py:59-77, journal.py:40, trajectory.py:120, 159, 171, 196, 232)
- replay — `World.from_records` (replay.py:21)

`Journal` holds only `self.world` (journal.py:30-31); every method is a
projection over `world.records`. There is no shadow state to drift.
`tests/test_compiler_runtime_integration.py:122-130` asserts
`isinstance(world, World)`, `isinstance(world.queue, EventQueue)`,
`isinstance(world.clock, Clock)`.

### V5 — maximum LLM calls per step and per run

Read from `trajectory.py` and confirmed by execution against an adversarial
scripted transport.

**Per step** (K_EVENT branch, `observed=True`):

```
  1  world call   trigger_kind="event_consequence"        trajectory.py:256-260
+ Σ over each observing actor a:
     1  actor call                                        trajectory.py:153-156
   + I_a world calls (one per intention)                  trajectory.py:176-179
+ 1  judge call                                           trajectory.py:295
= A·(1 + I) + 2 semantic calls
```

Measured, 5 actors × 12 intentions, `max_steps=1`:
**71 provider requests** (63 world, 5 actor, 3 judge). Formula: 5·13 + 2 = 67,
plus 3 starting-event world calls and 1 initialization judge call = 71. Exact.

**Per run:**

```
pre-loop   : 1 judge (trajectory.py:211) + S world calls (S = |starting_events|, trajectory.py:220-223)
loop       : max_steps × [A·(1 + I) + 2]
post-loop  : 1 judge (trajectory.py:305)
retries    : × 2 provider HTTP requests per semantic call (MAX_RETRIES_PER_CALL = 1, llm.py:29)
HARD CAP   : 400 provider HTTP requests (RuntimeCaller.max_calls default, llm.py:45)
```

Measured ceiling with a self-sustaining chain and `max_steps=10**6`:

```
status=failed  steps=80  calls=400  reason='CallBudgetExceeded: world: run exceeded 400 provider calls'
```

`A` (actors), `I` (intentions per actor) and `S` (starting events) are **all
unbounded from the runtime's side**. The only real bound on a run is the
400-call backstop, and exceeding it fails the run (trajectory.py:312-315 →
`run_simulation.py:93` exit 1). See HIGH-1 and HIGH-2.

---

## Findings

### CRITICAL

**None.**

---

### HIGH-1 — `intentions` is unbounded and each intention costs its own world LLM call; the model controls the runtime's call budget

- `sworldmodel/semantic_runtime/actor_mind.py:24-25` — `ACTOR_SCHEMA["intentions"]` is an unbounded array (no `maxItems`).
- `sworldmodel/semantic_runtime/actor_mind.py:82-92` — `validate_actor_response` validates element types but imposes **no length cap**.
- `sworldmodel/semantic_runtime/trajectory.py:176-179` — `for intent in parsed["intentions"]: world_step(...)`, one world LLM call per intention.

A single actor response therefore multiplies directly into provider calls with
no code-side ceiling. Measured: **1 actor, 1 step, one response containing 500
intentions consumed the entire 400-call budget and failed the run**:

```
[E] actors=1 intentions=500 max_steps=40 max_calls=400
    -> status=failed steps=1 calls=400
       reason='CallBudgetExceeded: world: run exceeded 400 provider calls'
```

This is a genuine control-inversion: the doctrine is "code controls access,
time, identity, persistence, causality and replay" (`__init__.py:3-4`), but
here the model controls how much work the runtime does. **Fix:** cap the
intention list in `validate_actor_response` (a small universal bound, e.g. 8,
is scenario-neutral — it is a resource bound, not a capability menu), and add
`"maxItems"` to the schema if the schema is kept at all (see HIGH-3).

### HIGH-2 — the default `max_steps` and the default call budget are mutually inconsistent; an ordinary run fails on the runaway backstop

- `run_simulation.py:36` — `--max-steps` default **40**.
- `run_simulation.py:74` — `RuntimeCaller(args.model)`; the budget is **not** passed.
- `sworldmodel/semantic_runtime/llm.py:45` — `max_calls: int = 400`.
- `sworldmodel/semantic_runtime/trajectory.py:63` — `run_trajectory` default is `max_steps=60`, a **third, different** value for the same knob.

40 steps × [A·(1+I) + 2] exceeds 400 for any scene with roughly ≥ 3 actors and
≥ 2 intentions each. Measured on the exact default CLI configuration:

```
[B] actors=3 intentions=2 max_steps=40 max_calls=400
    -> status=failed steps=40 calls=400
       reason='CallBudgetExceeded: world: run exceeded 400 provider calls'
[C] actors=2 intentions=1 max_steps=40 max_calls=400
    -> status=cutoff  steps=40 calls=203        (survives)
```

`llm.py:9-10` documents the ceiling as existing "only as a runaway backstop",
but on defaults it fires for a three-person scene doing nothing unusual. A
budget backstop that trips on the normal path is a step ceiling in disguise,
and it converts a legitimate `cutoff` result into `failed`. **Fix:** derive the
call budget from `max_steps` and the actor count, or raise `max_calls` and pass
it explicitly from `run_simulation.py`; and collapse the two `max_steps`
defaults (40 vs 60) into one.

### HIGH-3 — four dead JSON-Schema constants that advertise a provider-side guarantee that does not exist

| Constant | Location | Repo-wide references |
|---|---|---|
| `EVENT_SCHEMA` | `envelope.py:28-39` | 1 — only from the dead `WORLD_SCHEMA` |
| `WORLD_SCHEMA` | `world_mind.py:20-41` (+ import `world_mind.py:18`) | 1 (its own definition) |
| `ACTOR_SCHEMA` | `actor_mind.py:18-29` | 1 (its own definition) |
| `RESOLUTION_SCHEMA` | `resolution.py:24-34` | 1 (its own definition) |

`sworldmodel/semantic_runtime/llm.py:75-79` builds the only provider payload
in the runtime:

```python
payload = {"model": self.model, "temperature": 0.7, "max_tokens": 1200,
           "response_format": {"type": "json_object"},   # <- not json_schema
           "messages": [...]}
```

**No schema ever reaches a provider.** `envelope.py:28` nevertheless comments
`#: Provider-native strict schema for a proposed event.`, and each constant
carries `"additionalProperties": False` — which reads as a guarantee that
extra fields are rejected upstream. They are not; the guarantee is real but
lives entirely in the hand-written validators (`validate_event`,
`validate_actor_response`, `validate_world_response`, `make_validator`), which
do enforce it correctly and are tested (`test_semantic_runtime.py:137-153`,
`384-391`).

~57 lines of dead code asserting a safety property that is enforced somewhere
else. In a codebase whose thesis is that code owns the boundary, a false claim
about *where* the boundary is enforced is worth more than its line count.
**Fix:** delete all four, or actually send them (`response_format:
{"type": "json_schema", ...}`) and keep the validators as defence in depth.

---

### MEDIUM

**M1 — the world adjudicator's history is silently truncated to 60 events; the judge's is not.**
`journal.py:96` — `def render_for_world(self, limit: int = 60)`, called at
`trajectory.py:100` with no argument. Events beyond the last 60 vanish from the
world prompt with no marker and no ledger record that truncation occurred.
`resolution.py:63-75` (`judge_user_prompt`) passes **all** events. On any run
long enough to matter, the world adjudicates against a different history than
the judge scores. Either paginate/summarize explicitly and record it, or make
the two symmetric.

**M2 — the world's "person this concerns" is chosen by arbitrary array order.**
`trajectory.py:260` — `actor_id=envelope["for"][0] if envelope["for"] else None`.
That actor's private context is then injected into the world prompt
(`world_mind.py:115-118`, "THE PERSON THIS CONCERNS ... their circumstances").
`for` order comes from the model's own array (`envelope.py:106-114` dedupes
but preserves order), so which actor's private circumstances the world sees is
decided by list position. Not scenario routing, but an unjustified code-side
privilege that should be principled or removed.

**M3 — `Trace` is a second, parallel, non-authoritative history duplicating the ledger.**
`trace.py:17-25` plus the `note()` closure at `trajectory.py:72-74` and eleven
call sites. Nearly everything it stores already exists in authoritative form:

| Trace kind | Already in |
|---|---|
| `committed_event` | `journal.events()` / `OP_EVENT` |
| `terminal_check` | `OP_TERMINAL` |
| `actor_decision` | `OP_ACTOR_CALL` + `actor.memory` records |
| `world_judgment` | `OP_WORLD_CALL` + `event.scheduled` + `caller.calls[].user` |
| `actor_view` | `caller.calls[role=="actor"].user` |

`trace.py:53-56` writes `actor_views.jsonl` and `actor_exchanges.jsonl`, which
both persist the same prompt text. This is presentation-layer duplication, not
a duplicate world-state system — `Trace` has no reducers, is never read back
into state, and `replay.py` ignores it entirely — so it is not a kernel
violation. But it is duplicated bookkeeping threaded through the core loop.

**M4 — a world-proposed event dropped for falling past the cutoff is recorded only in the trace, never in the ledger.**
`trajectory.py:137-139` — `note("event_beyond_cutoff", ...)` with no
corresponding `world.apply`. This is the one thing `Trace` holds that the
ledger does not, which is precisely backwards: replay from `world.records`
alone (`replay.py:21`) cannot know the world proposed anything there. Either
apply a ledger record or make the loss explicit.

---

### LOW

**L1 — unreachable defensive code (verified by execution).**
- `trajectory.py:115-117` — `due = world.clock.now + envelope["delta"]; if due < world.clock.now: raise EnvelopeError("proposed event moves time backwards")`. `parse_duration` (`envelope.py:56-80`) can never return a negative `timedelta`: `_DURATION_RE` (`envelope.py:45`) requires `\d+`, so a leading `-` fails to parse. Confirmed: `"-5 minutes"`, `"- 5 minutes"`, `"-0.5 hours"` all raise `EnvelopeError` at parse time.
- `envelope.py:78-79` — `if delta < timedelta(0): raise` — unreachable for the same reason.
- `trajectory.py:115` and `trajectory.py:129` compute the identical `due` twice.

**L2 — dead dataclass field.** `trajectory.py:48` — `records: dict = field(default_factory=dict)` on `SemanticTrajectory`. Never assigned, never read, absent from `to_dict()` (`trajectory.py:50-55`), absent from every artifact.

**L3 — unused imports.**
- `adapter.py:22` — `from datetime import datetime`
- `adapter.py:25` — `iso` (only `parse_iso` is used)
- `trajectory.py:24` — `datetime` (only `timedelta` is used)
- `llm.py:19` — `import urllib.error` (only `urllib.request` is used)

**L4 — `CONSUMED_FIELDS` is a test-only tautology.** `adapter.py:31` defines it; no production code reads it. Its sole consumer, `test_compiler_runtime_integration.py:113`, asserts `"resolution" not in CONSUMED_FIELDS` — an assertion about a literal tuple, which cannot fail unless someone edits the tuple. The real invariant is genuinely tested by lines 114-119 (`scene["resolution"] not in json.dumps(world.records)` and not in any rendered view). The constant documents intent but proves nothing.

**L5 — `run_simulation.py --scene` silently discards the positional question and mislabels the output directory.** `run_simulation.py:47-49` derives `out` from `args.question`; `run_simulation.py:57` then overwrites `question`, `start` and `cutoff` from `input.json`. Artifacts land in a directory named after the ignored argument. Either make `question` optional when `--scene` is given, or compute `out` after the override.

**L6 — the bare event-loop skeleton is re-implemented rather than reused.** `trajectory.py:226-234` (`peek` → `pop` → `advance_to` → `apply("event.fired")`) mirrors `sworldmodel/engine.py:111-139`. This is the **correct** call and should not be "fixed": `Engine.run()` is welded to the old `ActionView`/`VerbView`/`Intention`/action-template ontology (`engine.py:211-236, 284-345, 595-658`) — exactly the capability menu the semantic runtime exists to eliminate. Reusing it would reimport the rejected design. Recorded so the duplication is a stated decision rather than an accident. **This is not a second replay engine**: replay is `World.from_records` only (`replay.py:21`).

**L7 — test coverage is single-family.** Both `tests/test_semantic_runtime.py:31-48` and `tests/test_compiler_runtime_integration.py:31-45` use the same Ada→Bo message/inbox scene, and `LifecycleModel` routes its scripted answers on wording (`test_semantic_runtime.py:230` `if "Open" in user or "read" in user.lower()`, `:237` `if "repl" in user.lower()`). That routing is in a **test fixture**, not the runtime, so it is not a universality violation — but the universality claimed by the module docstrings ("one universal prompt for every scenario") is never exercised against a second, structurally different scene (no shared physical location, no artifact exchange, no group deliberation). A second fixture scene with a different social shape would turn the claim into a tested property.

---

## Out of scope (recorded, not on the delete list)

`sworldmodel/engine.py` (734 L), `actions.py` (182 L), `actors.py` (283 L),
`llm_mind.py` (167 L), `terminals.py` (315 L), `info.py` (102 L) and
`compiler/legacy/` (13 modules) carry the old capability/action/verb ontology.
The semantic runtime touches none of them. They are **not** proposed for
deletion here: this review is scoped to the runtime, and `run_worlds.py`,
`worlds/*.py`, `compiler/scene_resolution.py` and eight test modules still
depend on them. Retiring them is a separate decision.

---

## Delete list

Concrete, ordered, with the reason each is safe.

### Tier 1 — dead code, zero behavioural change (~66 lines)

| # | Delete | Lines | Why safe |
|---|---|---|---|
| 1 | `sworldmodel/semantic_runtime/envelope.py:28-39` — `EVENT_SCHEMA` | 12 | Only referenced by `WORLD_SCHEMA`, itself deleted in #2. Never sent to a provider. |
| 2 | `sworldmodel/semantic_runtime/world_mind.py:20-41` — `WORLD_SCHEMA`, and line 18 `from .envelope import EVENT_SCHEMA` | 23 | Zero references repo-wide. Enforcement is `validate_world_response` (line 136). |
| 3 | `sworldmodel/semantic_runtime/actor_mind.py:18-29` — `ACTOR_SCHEMA` | 12 | Zero references repo-wide. Enforcement is `validate_actor_response` (line 71). |
| 4 | `sworldmodel/semantic_runtime/resolution.py:24-34` — `RESOLUTION_SCHEMA` | 11 | Zero references repo-wide. Enforcement is `make_validator` (line 78). |
| 5 | `sworldmodel/semantic_runtime/trajectory.py:48` — `records: dict = field(default_factory=dict)` | 1 | Never assigned or read; absent from `to_dict()`. |
| 6 | `sworldmodel/semantic_runtime/trajectory.py:115-117` — the `due < world.clock.now` guard | 3 | Unreachable: `parse_duration` cannot yield a negative delta (verified). Line 129 recomputes `due` anyway. |
| 7 | `sworldmodel/semantic_runtime/envelope.py:78-79` — `if delta < timedelta(0)` | 2 | Unreachable for the same reason. |
| 8 | `sworldmodel/semantic_runtime/adapter.py:22` — `from datetime import datetime` | 1 | Unused. |
| 9 | `sworldmodel/semantic_runtime/adapter.py:25` — the `iso` name in the import | 0 | Unused; keep `parse_iso`. |
| 10 | `sworldmodel/semantic_runtime/trajectory.py:24` — the `datetime` name in the import | 0 | Unused; keep `timedelta`. |
| 11 | `sworldmodel/semantic_runtime/llm.py:19` — `import urllib.error` | 1 | Unused. |

After Tier 1, `dataclass`/`field` remain needed by `SemanticTrajectory`, and
`from dataclasses import dataclass, field` (trajectory.py:23) can drop `field`.

### Tier 2 — remove after replacing the assertion (~2 lines)

| # | Delete | Precondition |
|---|---|---|
| 12 | `sworldmodel/semantic_runtime/adapter.py:29-31` — `CONSUMED_FIELDS` and its comment | Drop `tests/test_compiler_runtime_integration.py:20` (the import) and `:113` (the tautological assert). The real invariant stays covered by lines 114-119. |

### Tier 3 — collapse duplicated bookkeeping (~40 lines, needs a design call)

| # | Delete / change | Note |
|---|---|---|
| 13 | `trace.py` `committed_event` and `terminal_check` handling, and the matching `note()` calls at `trajectory.py:242` and `trajectory.py:202-203` | Both are fully reconstructible from `journal.events()` and the `OP_TERMINAL` records; `render_trajectory` can read the ledger directly. |
| 14 | `trace.py:53-54` — `actor_views.jsonl` | Byte-for-byte the same prompt text already in `actor_exchanges.jsonl` (`caller.calls[role=="actor"].user`). |
| 15 | `trajectory.py:138-139` — `note("event_beyond_cutoff", ...)` | Do **not** simply delete: replace with a `world.apply` ledger record so the dropped proposal survives replay (M4). Deleting it without that loses the information entirely. |

### Not to delete

- `trajectory.py:81-90` and `:263-266`, `:285-288` — the widening revisit backoff. It is universal time bookkeeping (double, cap at 24 h), contains no scenario logic, and prevents pending situations from being silently abandoned. Keep.
- `trajectory.py:226-234` — the pop/advance/fire loop. Duplicates `engine.py:111-139` in shape only; reusing `Engine.run()` would reimport the rejected action ontology (L6). Keep, and state the decision in the module docstring.
- Every validator (`validate_event`, `validate_wakes`, `validate_actor_response`, `validate_world_response`, `make_validator`). These carry the entire code-side boundary once the dead schemas in Tier 1 are gone.

### Fixes that are additions, not deletions

- HIGH-1: cap `intentions` length in `validate_actor_response` (`actor_mind.py:82-92`).
- HIGH-2: pass an explicit, derived `max_calls` from `run_simulation.py:74`, and unify the `max_steps` defaults at `run_simulation.py:36` and `trajectory.py:63`.
- M1: make `render_for_world`'s truncation explicit and symmetric with the judge's view.
- M2: justify or remove the `envelope["for"][0]` privilege at `trajectory.py:260`.

---

## Test status

```
$ python3 -m pytest tests/test_semantic_runtime.py tests/test_compiler_runtime_integration.py -q
19 passed in 0.14s
```

No test asserts anything the delete list would break.
