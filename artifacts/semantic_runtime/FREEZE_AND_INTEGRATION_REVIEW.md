# Freeze and Integration Review

Independent adversarial audit of four claims about the semantic-runtime phase.
The auditor did not write this code and worked from git and the source files,
not from the project's own documentation.

- Repo: `/home/user/SWORLDMODEL-GROUND-UP`
- Branch: `claude/sworldmodel-semantic-runtime` @ `6909916`
- Base: `origin/main` @ `d9985bb`; merge-base `f2c77a8`
- Date of audit: 2026-07-28
- Scratch scripts: `/tmp/claude-0/-home-user-SWORLDMODEL-GROUND-UP/d6ed917c-38bc-56aa-a050-80f5be912f4e/scratchpad/audit_freeze/`
- No repository file was modified. All destructive experiments ran in a
  throwaway clone (`scratchpad/audit_freeze/clone`).
- Concurrency note: another agent committed `6909916` and made an uncommitted
  edit to `sworldmodel/semantic_runtime/trajectory.py` (the `self_act_of`
  post-commit rule) while this audit was running. Claims 1-3 were verified
  against committed `6909916`; the Claim 4 scans were re-run against the live
  worktree afterwards — the new code adds one branch,
  `trigger_kind == "actor_intention"`, which is structural, and the scan totals
  are unchanged.

## Verdicts

| # | Claim | Verdict |
|---|-------|---------|
| 1 | The compiler is frozen and unchanged | **VERIFIED as fact** — but the *test that enforces it* is defeatable (HIGH) |
| 2 | Runtime consumes the compiler's exact four fields, no second lowering; `resolution` never reaches world or actors | **VERIFIED** (code + empirical trajectory probe) |
| 3 | No second compiler/runtime/clock/queue/world-state/memory/registry | **VERIFIED for kernel primitives; QUALIFIED for "runtime"** (MEDIUM) |
| 4 | No scenario-specific logic anywhere in the runtime | **VERIFIED as fact — zero scenario branches found; but wholly unenforced** (HIGH) |

## Findings

| ID | Severity | Finding |
|----|----------|---------|
| F1 | HIGH | `test_frozen_compiler_files_are_unchanged` reads `git ls-files -s` (the **index**). An unstaged worktree edit to a frozen compiler file passes the test while the edit is live at import time. Demonstrated. |
| F2 | HIGH | The same test cannot see a **new untracked `.py` inside `compiler/`**. A whole second lowering stage could be added there and the freeze test still passes. Demonstrated. |
| F3 | HIGH | The pre-existing universality guard `tests/test_hardcoding_guard.py` scans `("compiler", "compiler/legacy", "sworldmodel")` with a **non-recursive `os.listdir`**. `sworldmodel/semantic_runtime/` is not scanned by it or by anything else. An injected `is_email_scenario()` keyword router in `trajectory.py` passes all 218 tests. Demonstrated. |
| F4 | MEDIUM | The freeze covers only `compiler/`. The production compiler imports `sworldmodel` (`canonical_json`, `World`, `ActorState`, `AttentionRule`, `simclock`, `engine.Terminal`). Editing those would change compiler behaviour with every freeze hash still matching. Not exercised on this branch (zero pre-existing files were modified), but the mechanism does not cover it. |
| F5 | MEDIUM | `trajectory.run_trajectory` is a **second orchestration loop** beside the pre-existing `sworldmodel/engine.py:Engine.run`. Both drain `world.queue`, advance the kernel clock, apply `event.fired`, consult actors and evaluate a terminal. No kernel primitive is duplicated, but the phase did not reuse `Engine`. |
| F6 | MEDIUM | The runtime implements availability/observation itself (`journal.event` + `journal.observed` trace records, projected in `journal.py`) instead of the kernel's existing information lifecycle (`info.create/send/deliver/notice` + `Channel`/`AttentionRule`, which have real reducers and state). Two visibility models now coexist — the frozen `compiler/scene_adapter.py` uses the kernel one, the runtime uses the new one. |
| F7 | LOW | Two independent manifest→World adapters now exist: frozen `compiler/scene_adapter.py:instantiate_scene` (compiler self-check only) and new `sworldmodel/semantic_runtime/adapter.py:instantiate_scene_manifest` (what actually runs). They differ (e.g. private context: kernel `actor.memory` kind `context` vs. trace-only `semantic.actor_profile`). Drift risk; not a lowering stage, since the compiler's world is discarded. |
| F8 | LOW | `sworldmodel/semantic_runtime/llm.py` is the **fourth** DeepSeek HTTP transport in the repo (`sworldmodel/llm_mind.py`, `compiler/scene_llm.py`, `compiler/legacy/llm.py` pre-exist). Justified in its docstring (the compiler's caller is frozen with a hard 3-call budget), but it is duplication. |
| F9 | INFO | `adapter.CONSUMED_FIELDS` is declarative only — nothing in the adapter reads it; it is asserted by a test. The actual exclusion of `resolution` is by construction (the adapter never indexes that key). |

---

## CLAIM 1 — The compiler is frozen and unchanged

**Verdict: VERIFIED as a statement of fact. The enforcement test is weak (F1, F2, F4).**

### The freeze record is complete and correct

`artifacts/semantic_runtime/COMPILER_FREEZE.txt` lists **24** blob hashes. Every
tracked file under `compiler/` is exactly those 24 — nothing is omitted:

```
$ git ls-files -s compiler/ | wc -l      →  24
in freeze not in tree: []      in tree not in freeze: []      hash mismatches: []
```

The freeze covers all 8 production `scene_*.py` modules, `compiler/__init__.py`,
and all 15 `compiler/legacy/*` modules — i.e. a superset of the production path.

Three independent hash comparisons, all clean:

| Compared against | Result |
|---|---|
| git index (`git ls-files -s compiler/`) | 24/24 match |
| **working tree** (`git hash-object` on each file) | 24/24 match — no unstaged edit |
| **merge-base tree** `f2c77a8` (the state before the phase) | 24/24 match, same file set |

The third is the important one: it confirms the freeze hashes really are the
pre-phase state, rather than a snapshot taken after edits. `COMPILER_FREEZE.txt`
itself has exactly one commit in its history (`b84362d`, the first commit of the
phase) and is unmodified in the worktree.

No `.gitattributes` and no submodules exist, so no smudge/clean filter can make
blob hashes lie. All 24 entries are mode `100644` — no symlink can point a
"frozen" path at different content.

### Git history shows no change to `compiler/` on this branch

```
$ git log --stat origin/main..HEAD -- compiler/     → (empty)
$ git diff --stat origin/main HEAD -- compiler/     → (empty)
$ git diff --stat f2c77a8 HEAD -- compiler/         → (empty)
```

Stronger: the entire branch is **additive**. 13 commits, 180 files, 24 705
insertions, **zero deletions and zero modifications of any pre-existing file**:

```
$ git diff --name-status f2c77a8 HEAD | grep -cv '^A'   → 0
```

Nothing under `sworldmodel/` (world.py, simclock.py, events.py, engine.py,
info.py, terminals.py, actors.py) was touched either. This independently closes
F4 for this branch even though the freeze mechanism does not cover it.

The only files with only-`__pycache__` presence under `compiler/` are gitignored
`.pyc` artifacts. Some are stale (e.g. `compiler/__pycache__/lowering.pyc`, whose
source moved to `legacy/`); CPython will not import a `__pycache__` `.pyc` with no
adjacent source, so they are inert.

### The enforcement test *can* pass while a compiler file is modified — demonstrated

`tests/test_compiler_runtime_integration.py:135-153` compares the freeze record
against `git ls-files -s compiler/`. `git ls-files` reports the **index**, not the
worktree, and reports only **tracked** files. In a clone, with the test file
untouched:

| Experiment | Freeze test result |
|---|---|
| clean tree | PASS (correct) |
| **unstaged edit** to `compiler/scene_pipeline.py` injecting a live `_audit_backdoor()` that rewrites the resolution | **PASS — escape confirmed (F1)** |
| **new untracked** `compiler/audit_second_stage.py` | **PASS — escape confirmed (F2)** |
| **staged** edit to `compiler/scene_guards.py` | FAIL (correctly caught) |
| test run from a different cwd | FAIL with `FileNotFoundError` (fail-closed, acceptable) |

Evidence for F1: after the edit, `git ls-files -s compiler/scene_pipeline.py`
still reported the frozen blob `149e8112…` while `git hash-object` on the file
reported `bbb4c24d…`, and `import compiler.scene_pipeline` exposed the injected
symbol. The test passed anyway.

**Recommended fix (one line each):** compare `git hash-object` / `git diff --quiet
--exit-code -- compiler/` in addition to the index, and assert that
`git ls-files --others --exclude-standard compiler/` (filtered to `*.py`) is
empty. Optionally extend the freeze record to the `sworldmodel/` modules the
compiler imports (F4).

So: the claim is true today and verifiable by three independent routes, but a
future change could break it without the test noticing.

---

## CLAIM 2 — Exact four-field consumption, no second lowering, resolution never reaches world or actors

**Verdict: VERIFIED.**

### The path from compiler to runtime has nothing in it

`run_simulation.py:64-75` (production entry point):

1. `compile_scene(question, start, cutoff, context=…, caller=SceneCaller(model), out_dir=…)`
2. `scene = result.manifest`
3. `instantiate_scene_manifest(scene, question, start, cutoff)`

Between (1) and (3): no LLM call, no schema rewrite, no enrichment, no
normalisation, no lookup table. `result.manifest` is the compiler's own
post-validation manifest — `compiler/scene_pipeline.py:218` returns
`manifest=scene`, where `scene` is `validate_scene(...)[0]`, which returns exactly
`{"actors", "shared_context", "starting_events", "resolution"}`
(`compiler/scene_validate.py:199`). All normalisation happens *inside* the frozen
compiler. The `--scene` replay path just `json.load`s the compiler's own
`final_scene_manifest.json`.

`adapter.py` (109 lines) is a mechanical field map:

| manifest field | destination | anything interpretive? |
|---|---|---|
| `shared_context` | `fact.set scene:shared_context` | verbatim string |
| `actors[].name` | `actor.add` + slug→id (`re.sub("[^a-z0-9]+","_")`) | mechanical id assignment, not name matching |
| `actors[].private_context` | `semantic.actor_profile` record, readable only through that actor's own view | verbatim string |
| `starting_events[]` | `journal.commit` if `time <= start`, `world.schedule` if `<= cutoff`, recorded-and-skipped if beyond | time comparison only |
| `resolution` | **never referenced in adapter.py** | — |

`grep resolution sworldmodel/semantic_runtime/adapter.py` → only the docstring and
the `CONSUMED_FIELDS` comment. No `scene["resolution"]` read exists.

### Where the resolution actually goes

`run_simulation.py:85` passes it to `run_trajectory(...)`, which passes it to
exactly one place: `resolution_mod.judge_user_prompt(resolution, …)`
(`trajectory.py:268`). It is never passed to `world_mind.world_user_prompt` or
`actor_mind.actor_user_prompt`, whose signatures do not accept it.

### Empirical proof over a full trajectory

The existing test only checks this at instantiation time. I ran a complete
scripted trajectory (33 steps, 66 provider calls) with a unique marker embedded in
the resolution string
(`scratchpad/audit_freeze/probe_resolution_leak.py`):

```
calls by role:                        {'judge': 14, 'world': 35, 'actor': 17}
prompts containing the resolution:    14 — all role='judge'
non-judge prompts containing it:      []
ledger records containing it:         []
```

Zero of the 35 world prompts and zero of the 17 actor prompts contained it, and
it never entered `world.records`.

**Back-flow also checked** (the judge's own `explanation` could re-import
resolution wording into later prompts). With a marker planted in every judge
explanation (`probe_judge_backflow.py`): it appeared in **0 prompts of any role**
and only in the `semantic.terminal_check` ledger records, which is the intended
audit trail. The reason is structural: `Journal.events()`, `render_for_world()`
and `build_view()` project only `journal.event` / `journal.observed` /
`semantic.actor_profile` records — terminal records are unreachable from every
prompt-building path.

The only "second instantiation" in the repo is the frozen compiler's own
`compiler/scene_adapter.py:instantiate_scene`, used *inside* `compile_scene` for
determinism/genesis/replay self-checks. Its `World` and `bindings` are discarded;
the runtime re-instantiates from the manifest. That is duplication (F7), not a
lowering stage between the compiler and the runtime.

---

## CLAIM 3 — No second compiler / runtime / clock / queue / world-state / memory / registry

**Verdict: VERIFIED for every kernel primitive. QUALIFIED on the word "runtime".**

### Measured: zero compiler modules imported

`scratchpad/audit_freeze/probe_imports.py`, subprocess, `sys.modules` before/after
`import sworldmodel.semantic_runtime`:

```
new modules: 112
modules matching  compiler | compiler.* :  []          ← zero
sworldmodel.*: world, simclock, events, actors, actions, info, engine,
               terminals, checkpoint  +  the 11 semantic_runtime modules
```

(The stdlib `email` package appears in the 112 — it is pulled in by
`http.client`/`ssl` via `urllib`, not by anything scenario-related.)

### It uses the pre-existing kernel and adds no reducer

Every state-changing call the runtime makes, exhaustively:

| Call site | Kernel op | Reducer status |
|---|---|---|
| `adapter.py:64,65,67,68` | `fact.set` | pre-existing kernel reducer |
| `adapter.py:75` | `actor.add` | pre-existing kernel reducer |
| `trajectory.py:209` | `actor.memory` | pre-existing kernel reducer |
| `trajectory.py:366` | `event.fired` | pre-existing kernel reducer |
| `adapter.py:80`, `journal.py:51,83`, `trajectory.py:147,197,278,306` | `semantic.*`, `journal.*` | **not in `_REDUCERS`** → trace-only, exactly as `world.py:792-795` documents for `event.scheduled`, `actor.view`, etc. |

`sworldmodel/world.py` is byte-identical to `origin/main` (the branch modifies no
pre-existing file), so `_REDUCERS` (`world.py:754`) is unchanged. There is no
`setattr`, no `globals()` mutation, no reducer registration, no monkeypatching
anywhere in `sworldmodel/semantic_runtime/` or `run_simulation.py` (grepped).

Clock and queue: the runtime never constructs one. It calls `world.clock.now`,
`world.clock.advance_to`, `world.schedule(...)`, `world.queue.peek/pop` — the
kernel's `Clock` and `EventQueue`. The class inventory of the whole package is:

```
Journal (projection wrapper: holds only `world` + `trajectory_id`)
RuntimeCaller (HTTP transport + call log)
Trace (in-memory list, artifact rendering only)
SemanticTrajectory (result dataclass)
+ 4 exception types
```

No `Clock`, no `Queue`, no `World`, no `Store`, no `Registry`, no `Compiler`.

Memory: actor private updates go through the kernel's `actor.memory` reducer and
are read back from `world.actors[aid].memories` (`views.py:37`). No parallel store.

Capability/action registry: the runtime never emits `action.define`,
`action.propose`, `action.state`, `channel.add` or any `info.*` op; it does not
import `sworldmodel.actions`, `sworldmodel.info`, `AttentionRule`, `Channel`,
`Mind`, `Engine`, `terminals.build_terminal` or `eval_expr`. There is no
capability graph, verb table or action ontology.

### The qualifications (F5, F6, F8)

Refuting harder: the phase *did* add parallel implementations of things the repo
already had, all built on the same kernel:

- **F5 — a second driver loop.** `sworldmodel/engine.py:Engine.run` already
  drains the queue, advances the clock, delivers information, wakes actors,
  validates intentions and evaluates a terminal. `trajectory.run_trajectory` does
  structurally the same job (458 lines) and does not use `Engine`. Defensible —
  the semantics are LLM-written rather than typed-action — but "no second runtime"
  is only true if "runtime" means "kernel primitives", not "orchestration loop".
- **F6 — a second visibility model.** The kernel has an information lifecycle
  with real state (`infos`) and reducers (`info.create/send/deliver/notice`) plus
  `AttentionRule.notice_time`; the frozen `compiler/scene_adapter.py` uses it. The
  runtime instead encodes availability/observation as `journal.event.for` /
  `.observed` plus `journal.observed` transitions, projected in `journal.py`. No
  new storage system (it is all ledger records), but it is a second model of the
  same concept.
- **F8 — a fourth HTTP transport.**

None of these is a second *kernel*. Reported so the claim is not read more
broadly than the evidence supports.

---

## CLAIM 4 — No scenario-specific logic anywhere in the runtime

**Verdict: VERIFIED as a statement of fact — I found zero scenario logic. But
nothing enforces it (F3).**

### Exhaustive scan for domain vocabulary

`scratchpad/audit_freeze/scan_scenario.py` scans all 12 files of
`sworldmodel/semantic_runtime/` plus `run_simulation.py` for ~90 domain terms
(email/inbox/mail/sms/slack, negotiation/offer/price/bid/deal/contract/invoice/
salary, committee/vote/ballot/quorum/election/poll, meeting/dinner/lunch/
restaurant/interview, recruiter/manager/investor/doctor/lawyer/court/teacher,
scenario/domain/vertical, and stock person names), classifying each hit by AST
position (docstring / comment / string / code).

**25 hits, all false positives.** Every one is a substring of an ordinary word or
a role name:

| Hit | Actual text | Verdict |
|---|---|---|
| `ada` ×5 | `**ada**pter`, `re**ada**ble`, `**ada**pter.py` | substring |
| `election` | `s**election** is mechanical` (views.py:6) | substring |
| `deal` ×4 | `dealt with`, `dealing with`, `deals with other things` | substring |
| `buy` | `"…decides, goes, buys, signs, or acts on…"` (world_mind.py:56) | universal list of *choice verbs* the world may never narrate — the opposite of a commerce branch |
| `email` ×1 | journal.py:72 docstring: *"an email that has been seen is still that email"* | illustrative prose in a docstring; no code path |
| `judge ` ×8 | the read-only judge role | universal role name |
| `scenario` ×2 | *"one universal prompt for every scenario"* | doctrine statement |

### Exhaustive scan for content-dependent branching

`scan_branches.py` (AST) lists **every** `Compare`, membership test, regex,
`.lower()`, `.startswith()`, `.split()` and every module-level constant in the
package. Full results reviewed by hand. The complete set of things the runtime
branches on:

- **ledger op names** — `OP_EVENT`, `OP_OBSERVED`, `OP_TERMINAL`, `OP_PROFILE`,
  `"genesis.sealed"`, `"event.fired"`, `"actor.memory"`
- **actor ids and structural fields** — `actor_id in e["for"]`,
  `actor_id in e["observed_by"]`, `d["trajectory_id"] != self.trajectory_id`
- **its own fixed status vocabulary** — `"YES"`, `"UNRESOLVED"`, `"NO_AT_CUTOFF"`
- **its own trace kinds and call roles** — `k == "actor_view"`, `c["role"] == "world"`
- **time units** — `_UNITS` (second/minute/hour/day/week), `"now"/"immediately"/"0"/"none"`, `_SEPARATORS = ("and","&","+")`
- **JSON fences** — `t.startswith("```")`

There is **no** comparison against event text, actor names, the question, the
shared context, or any domain word. The only text transforms are: slugify a name
into an id (`adapter.actor_id_for`), parse a duration, `clean_text` (length +
encoding hygiene), `contained` (whitespace flattening for prompt containment),
`_strip_fences`.

Module-level constants are all universal bounds: `MAX_INTENTIONS_PER_TURN=3`,
`MAX_PRIVATE_UPDATES_PER_TURN=6`, `MAX_WAKES_PER_JUDGMENT=4`, `MAX_ENV_CHAIN=3`,
`MAX_STEP_DAYS=30`, `MAX_TEXT_CHARS=2000`, backoff `1h → ×2 → cap 24h`, plus HTTP
timeouts. None is tuned to a domain.

### Prompts name no domain

`WORLD_SYSTEM` (world_mind.py:27-132), `ACTOR_SYSTEM` (actor_mind.py:27-60) and
`JUDGE_SYSTEM` (resolution.py:33-58) were read in full. They speak only of
*something*, *someone*, *an item*, *information*, *a person's attention*. The
message-lifecycle language ("Information can exist, then be sent, then arrive
somewhere a person could see it, then actually reach their attention, then
actually be read") is a **universal mechanic** — it is stated in terms of
information, never of a channel type, and no code branches on it. Section
headings are code-owned and generic (`CURRENT TIME`, `BACKGROUND`,
`WHAT HAS CONCRETELY HAPPENED SO FAR`, `THE TRIGGER YOU MUST JUDGE`).

### But nothing would stop it (F3)

`tests/test_hardcoding_guard.py` — the repo's universality guard — iterates
`SCAN_DIRS = ("compiler", "compiler/legacy", "sworldmodel")` with
`os.listdir(...)`, which is **not recursive**. `sworldmodel/semantic_runtime/` is
therefore never scanned, and the guard was not extended this phase.

Demonstrated in the clone: injecting into `trajectory.py`

```python
EMAIL_INBOX_ROUTE = "email"
def is_email_scenario(text):
    return "email" in text.lower() or "committee vote" in text.lower()
```

→ `tests/test_hardcoding_guard.py` **passes**, and the full suite **218 passed**.

**Recommended fix:** add `"sworldmodel/semantic_runtime"` to `SCAN_DIRS` (or make
the walk recursive) and add `run_simulation.py`. With the code as it stands today
that change passes immediately — I verified the directory is clean against a
superset of the guard's own word list.

---

## Reproduction

```bash
cd /home/user/SWORLDMODEL-GROUND-UP
SP=/tmp/claude-0/-home-user-SWORLDMODEL-GROUND-UP/d6ed917c-38bc-56aa-a050-80f5be912f4e/scratchpad/audit_freeze

# Claim 1
git ls-files -s compiler/ | wc -l                      # 24, matches the freeze
git diff --stat origin/main HEAD -- compiler/          # empty
git diff --name-status $(git merge-base origin/main HEAD) HEAD | grep -v '^A'   # empty
git ls-tree -r $(git merge-base origin/main HEAD) compiler/                     # same 24 blobs

# Claim 1 escapes (run in a clone, never in the repo)
git clone --no-hardlinks . $SP/clone
#   unstaged edit to compiler/*.py   → freeze test PASSES
#   new untracked compiler/*.py      → freeze test PASSES
#   staged edit                      → freeze test FAILS (correct)

# Claim 2
PYTHONPATH=$SP/clone python3 $SP/probe_resolution_leak.py   # resolution only in judge prompts
PYTHONPATH=$SP/clone python3 $SP/probe_judge_backflow.py    # judge text never re-enters a prompt

# Claim 3
PYTHONPATH=. python3 $SP/probe_imports.py                   # compiler_modules: []

# Claim 4
python3 $SP/scan_scenario.py                                # 25 hits, all substrings
python3 $SP/scan_branches.py                                # every branch is structural
```

## Summary

All four claims hold as descriptions of the code as it stands at `6909916`. Three
of the four are enforced weakly or not at all: the freeze test sees only the git
index and only tracked files (F1, F2), the freeze does not cover the
`sworldmodel/` modules the compiler imports (F4), and the universality guard does
not scan the new runtime directory at all (F3). The substantive qualifications to
the "nothing new was introduced" story are F5 (a second orchestration loop beside
`Engine`) and F6 (a second availability/observation model beside the kernel's
information lifecycle) — both built entirely on the existing kernel ledger, clock
and queue, and neither adding a reducer.
