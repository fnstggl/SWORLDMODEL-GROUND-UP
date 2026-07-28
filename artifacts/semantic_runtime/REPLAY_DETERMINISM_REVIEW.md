# Replay, Determinism and Persistence — Adversarial Review

**Scope:** `sworldmodel/semantic_runtime/{replay,journal,adapter,trace,trajectory}.py`,
`sworldmodel/world.py` (`World.from_records`, `World.apply`, the ledger and the
reducer table), and the single production call site `run_simulation.py:85`.

**Method:** probe scripts under
`/tmp/claude-0/-home-user-SWORLDMODEL-GROUND-UP/d6ed917c-38bc-56aa-a050-80f5be912f4e/scratchpad/audit_replay/`
driving the real runtime with the scripted `LifecycleModel` transport copied verbatim
from `tests/test_semantic_runtime.py`. **No live provider was contacted at any point.**
The reference run is the two-actor cold-message scene: 149 ledger records, 20 committed
events, 22 terminal checks, `traj.status == "cutoff"`.

**Reviewer note on tree state:** during the audit another agent changed
`sworldmodel/semantic_runtime/trace.py` and `trajectory.py` (plus
`tests/test_semantic_runtime.py`), landing as commits `81b8bd1` and `763147f`. The four
files that carry every finding below — `replay.py`, `journal.py`, `adapter.py`,
`world.py` — were **not** touched (`replay.py` md5 `932010585cfd…`, `world.py` md5
`5cb537438ff2…` throughout), and every headline probe was re-run against the post-commit
tree and reproduced identically. `tests/test_semantic_runtime.py` is green (29 passed) at
`763147f`. Line numbers for `trajectory.py` are as of that commit.

---

## Verdict

| Claim | Status |
|---|---|
| 1. Replaying a completed ledger reproduces the identical world with zero LLM calls | **FALSIFIED** — the reconstruction is not independent of the live world, and three of the five named dimensions (timestamps, event ordering across the whole ledger, terminal record) are not genuinely compared |
| 2. `exact` cannot be true unless all of that genuinely matches | **FALSIFIED** — `terminal_matches` is `x == x` on the same object; `exact` is trivially true on an empty ledger, on a never-run world, and on a *failed* run |
| 3. The adapter is deterministic | **HOLDS** — byte-identical across repeats and across `PYTHONHASHSEED` |
| 4. Nothing depends on wall clock / hash seed / iteration order / identity / filesystem | **MOSTLY HOLDS** — hash seed, iteration order and filesystem are clean; object identity and wall clock are violated (F1, F7, F8) |
| 5. `journal.observed` transitions survive replay and reproduce per-actor visibility | **HOLDS** |

**Headline result.** A forged 148-record ledger that shares only **68 of the real run's
149 records** — every world judgment fabricated, every actor decision and intention
fabricated, 21 world calls / 18 actor calls / 21 terminal checks / 21 scheduled events
deleted, every causal link forged (including `cause: null` after `genesis.sealed`) —
is certified `exact == True` by `replay_trajectory`.

---

## CRITICAL

### F1 — `replay_trajectory` compares the reconstruction against *itself*; `terminal_matches` is `x == x`

**Where:** `sworldmodel/semantic_runtime/replay.py:21`, `:25`, `:40-41`, `:54-56`;
call site `run_simulation.py:85`.

```python
# replay.py:21
world = World.from_records([dict(r) for r in records], live=True)
```

`dict(r)` is a **shallow** copy. It clones the outer `{seq,t,op,data,cause}` envelope
but the `"data"` value is the *same object* as the live world's. `World.from_records`
then appends those very dicts to `w.records` (`world.py:450`) without copying. Because
the only production call is

```python
# run_simulation.py:85
verification = replay_trajectory(world.records, live_world=world)
```

the "replayed" world and the live world share their entire record payload graph.

**Probe:** `p02_aliasing.py`
**Expected:** the reconstruction is an independent object graph rebuilt from serialized data.
**Observed:**
```
outer record dict is same object : False
inner  data  dict is same object : True
records whose data is ALIASED    : 149/149
replay terminals[-1] IS live terminals[-1] : True
  -> 'terminal_matches' evaluates  x == x  : True
```

`terminals` (`replay.py:25`) and `live_terminals` (`replay.py:40-41`) both project
`r["data"]` out of aliased records, so `replay.py:54-56` compares an object to itself.
It cannot return `False`. Demonstrated end to end in `p06_vacuity.py` section E:

```
after forging the live world's FINAL terminal record in place:
   exact = True  terminal_status = FORGED  support = ['e999999']
-> replay certifies a terminal citing an event that does not exist
```

The runtime's own test (`tests/test_semantic_runtime.py:353`) asserts
`verification["exact"] is True` through exactly this aliased path, so the test cannot
fail on the terminal dimension either.

**Severity: CRITICAL.** Claim 2 explicitly says the flag is "not comparing an object to
itself". It is, for the terminal dimension, on every production run.

**Fix:** `World.from_records(json.loads(canonical_json(records)), ...)`, or at minimum
`copy.deepcopy`. Better: replay the *persisted* `ledger.jsonl` (see F7).

---

### F2 — 40–55 % of a ledger can be deleted, and all of its provenance fabricated, with `exact == True`

**Where:** `sworldmodel/world.py:754-796` (the reducer table) + `replay.py:58-61`.

`journal.event`, `journal.observed`, `semantic.actor_profile`, `semantic.actor_call`,
`semantic.world_call`, `semantic.terminal_check` and `event.scheduled` have **no
reducer** — they are trace-only in the kernel (comment at `world.py:792-795`).
`World.state_hash()` (`world.py:391-404`) therefore cannot see them at all. The only
other checks are `event_ids_match` (ids only), `views_match`, `memories_match` and the
dead `terminal_matches`. Anything that is (a) not reduced into state, (b) not a
`journal.event` id, (c) not visible in a per-actor view, and (d) not the *last*
terminal record is compared on **no dimension whatsoever**.

`state_hash` does incidentally catch a changed record *count* — but only because
`w._seq = records[-1]["seq"]` (`world.py:451`) feeds `snapshot()["version"]`. Preserve
the last record's `seq` and `t` and even that check goes away.

**Probe:** `p03_tamper.py` and the final forgery probe. Ledger round-tripped through
`canonical_json` first, so no aliasing helps the tamperer.

| Tamper (149-record ledger) | `exact` |
|---|---|
| DELETE every `semantic.world_call` (21) | **True** |
| DELETE every `semantic.actor_call` (18) | **True** |
| DELETE every `event.scheduled` (21) | **True** |
| DELETE every `semantic.terminal_check` except the last (21) | **True** |
| DELETE all three provenance families (60 records → 89 left) | **True** |
| REWRITE every world judgment text (21) | **True** |
| REWRITE every actor decision + intentions (18) | **True** |
| SWAP first and last `semantic.world_call` | **True** |
| INSERT 5 forged world judgments (duplicate `seq`, before last) | **True** |
| INSERT a forged `YES` terminal_check citing `e999` (not last) | **True** |
| STRIP to state ops + profiles + final terminal (149 → 68) | **True** |
| …then substitute 80 wholly fabricated provenance records (148 total) | **True** |

Final line of the forgery probe:

```
original ledger records: 149  forged ledger records: 148
records they have in common (op,seq,data): 68
```

**Severity: CRITICAL.** "Replaying a completed run's ledger reproduces the identical
world" is false: replay verifies the reduced kernel state and the *journal event id
list*, and is blind to the entire semantic provenance layer that this runtime exists to
produce — which world judgment caused which event, which actor decided what, which
intentions were adjudicated, and every terminal check but the last.

**Fix:** compare the ledgers themselves —
`canonical_json(world.records) == canonical_json(live_world.records)` — and report
`len(records)` against `len(live_world.records)`. That single line subsumes most of
this section.

---

### F3 — `World.from_records` enforces **no** causality at all; `genesis.sealed` can be stripped and causeless records appended

**Where:** `sworldmodel/world.py:446-450` versus `world.py:105-121`.

`World.apply` refuses a causeless record after genesis:

```python
# world.py:108-111
if self.genesis_sealed and cause is None:
    raise WorldIntegrityError(
        f"record {op!r} has no cause; after genesis every state "
        f"transition must name what produced it")
```

`from_records` bypasses `apply` entirely — it calls `w._reduce(rec)` directly
(`world.py:447`) — so that guard, the `copy.deepcopy` at `world.py:115`, and the
per-record clock discipline are all skipped on the replay path.

**Probe:** `p04_integrity.py`
**Expected:** a ledger whose causal chain is broken is rejected.
**Observed:**
```
every cause stripped to null (post-genesis records too)   ACCEPTED  seq=149
every cause points FORWARD in time (cause > seq)          ACCEPTED  seq=149
every cause points at a nonexistent seq 999999            ACCEPTED  seq=149
timestamps shuffled out of monotonic order                ACCEPTED  seq=149
genesis.sealed record deleted                             ACCEPTED  seq=149
      genesis_sealed flag on the replayed world: False
      >>> a causeless record was accepted into the replayed world
```

`replay_trajectory` does not check `cause` either — `p03_tamper.py` rewrote all 139
causal links to point at `seq 1` and `exact` stayed `True`.

The `genesis.sealed` case is a complete escape hatch: strip the seal → `from_records`
→ the reconstructed world has `genesis_sealed == False` → arbitrary causeless records
can be appended → `replay_trajectory(rw.records, live_world=rw)` returns
`exact == True` (probe section "can a replayed world be appended to and re-verified?").

Two integrity checks *do* survive, both by accident rather than design:
- duplicated `seq` is caught by `EventQueue.push` — but **only** when at least two
  `event.scheduled` records survive. `p09_refine.py` section (e): delete every
  `event.scheduled` (itself undetected, F2) and set every `seq` to 7 → **ACCEPTED**,
  `version == 7`.
- a final `t` before `start` is caught by `clock.advance_to` at `world.py:452` — but
  only for the *last* record; interior timestamps are never validated because
  `from_records` never advances the clock per record.

**Severity: CRITICAL.** The module docstrings claim the ledger "inherits immutability,
monotonic sequence numbers, authoritative timestamps, explicit causality (`cause`)…
for free" (`journal.py:4-8`) and that "the ledger IS the world's history"
(`world.py:9-12`). On the replay path none of that is enforced.

**Fix:** validate in `from_records` — `seq` strictly increasing from 1, `t`
non-decreasing, `cause` either `None` (only before `genesis.sealed`) or a `seq` strictly
less than the record's own, exactly one `world.genesis` at index 0, at most one
`genesis.sealed`.

---

## HIGH

### F4 — `exact` is trivially true on empty, never-run and **failed** runs

**Where:** `replay.py:58-61`.

`exact = all(...)` over five booleans, each of which degenerates to a comparison of two
empty or `None` values when the run produced nothing.

**Probe:** `p06_vacuity.py`

| Input | `exact` | Compared |
|---|---|---|
| A bare `World(start)` — 1 record, genesis only | **True** | 0 events, 0 views, 0 memories, terminal `None == None` |
| A scene with zero actors and zero starting events | **True** | 0 views, 0 memories |
| An instantiated scene that never ran a trajectory | **True** | terminal `None` |
| A run whose judge returned unparseable JSON → `traj.status == "failed"` | **True** | terminal `None` |

The failed-run case is the damaging one. `run_simulation.py` writes
`replay_verification.json` unconditionally (`trace.py:77`) and prints
`[replay] exact=True`, and nothing in the replay result records that the trajectory
failed, that no terminal was ever reached, or that `records_replayed` is a fraction of a
normal run. A reader of `replay_verification.json` alone cannot tell a clean 149-record
resolved run from a 12-record crash.

**Severity: HIGH.** Directly falsifies claim 2's "not vacuous".

**Fix:** make `exact` require non-vacuity — a terminal record must exist, at least one
event must have been committed — or emit `"exact": null` with a `"reason"` when there is
nothing to verify, and carry `trajectory.status` into the replay artifact.

---

### F5 — event **timestamps** are never a compared dimension, and unobserved events are compared on nothing

**Where:** `replay.py:29`, `:46-47` compare `[e["event_id"] …]` only. `Journal.events()`
(`journal.py:98-101`) carries `t`, `description`, `for`, `observed`, `source` — none of
which reach the comparison except through `build_view` (`views.py:52-54`), which only
sees events the actor **actually observed**.

**Probe:** `p09_refine.py` section (a'), on an interior `journal.event` with `for: []`,
`observed: false`:

| Tamper | `exact` |
|---|---|
| its timestamp moved five years (2026 → 2031) | **True** |
| its description completely rewritten | **True** |
| its audience changed to both actors | **True** |
| its `observed` flag flipped to true | **True** |
| its `source` and `trajectory_id` replaced | **True** |

(The audience and `observed` cases each pass individually because the other field
neutralizes them; `p10_debug_views.py` confirms the *combined* change is caught by
`views_match`. `p08_gaps.py` shows the timestamp change is caught only when the tampered
record happens to be the ledger's **last**, via `clock.advance_to` at `world.py:452`.)

Interior timestamps of *observed* events are caught, but only incidentally: `build_view`
happens to include `"t"` in `observed_events`.

**Severity: HIGH.** Claim 1 says "same timestamps". Replay never compares them.

**Fix:** compare `canonical_json(events)` rather than `[e["event_id"] for e in events]`
at `replay.py:46-47` — that covers ids, order, timestamps, descriptions, audiences,
observation state and source in one line.

---

### F6 — `memories_match` compares only memory **content**

**Where:** `replay.py:49-53`.

```python
"memories_match": canonical_json(
    {aid: [m.content for m in world.actors[aid].memories] ...
```

`Memory` is `(t, kind, content, source)` (`actors.py:42-50`). Timestamp, kind and source
are dropped. Rewriting the `source` of all 17 private memories leaves `memories_match ==
True`; it is caught only by `state_hash_matches`, because `ActorState.to_dict`
(`actors.py:98-99`) happens to serialize them.

**Probe:** final tamper matrix.

| Tamper (17 `actor.memory` records) | flags that fired |
|---|---|
| CONTENT rewritten | state_hash, views, memories |
| KIND → `note` | state_hash, views |
| SOURCE rewritten | **state_hash only** |
| ACTOR reassigned | state_hash, views, memories |

**Severity: HIGH.** Claim 1 says "same actor memories". The named check verifies a
strict subset; the dimension is only saved by a different check that happens to overlap.
Any future memory field not in `ActorState.to_dict` would be verified by nothing.

**Fix:** `[m.__dict__ for m in ...]` or `[(iso(m.t), m.kind, m.content, m.source) …]`.

---

### F7 — replay never reads the persisted ledger, and `llm_calls: 0` is a literal

**Where:** `run_simulation.py:85`, `trace.py:77` and `trace.py:81`, `replay.py:27`.

Ordering in `run_simulation.py`: the trajectory runs → `replay_trajectory` is handed the
**in-memory** `world.records` → `write_artifacts` writes
`replay_verification.json` (`trace.py:77`) → *then* writes `ledger.jsonl`
(`trace.py:81`). The certificate is produced before the artifact it appears to certify
exists, and is never compared against it. Nothing in the pipeline ever calls
`World.load_ledger`.

**Probe:** `p08_gaps.py` section (d) — the persisted file *does* currently round-trip and
replay clean, but that is a property of the data, not a property anything verifies:

```
replay_verification.json says exact = True
in-memory ledger == persisted ledger: True
replaying the PERSISTED file instead: exact = True
(this check is never performed by run_simulation.py)
```

Separately, `replay.py:27` reports `"llm_calls": 0` as a **literal constant**. Nothing
counts, meters or asserts provider calls. The property is true by construction (no
`RuntimeCaller` is reachable from `replay.py`), but the field is an assertion, not a
measurement — and the docstring's "Performs no provider calls by construction"
(`replay.py:19-20`) is the only thing standing behind it. The test at
`tests/test_semantic_runtime.py:354-355` does check `len(caller.calls)` independently,
which is the honest check; the artifact does not.

**Severity: HIGH.** The whole point of "the ledger is the authority" is that the
*persisted* ledger can rebuild the world. That is asserted, never exercised.

**Fix:** in `run_simulation.py`, write `ledger.jsonl` first, then
`replay_trajectory(World.load_ledger(path), live_world=world)`.

---

## MEDIUM

### F8 — wall-clock time leaks into three artifacts

**Where:** `llm.py:145` (`entry["wall_s"] = round(time.monotonic() - t0, 3)`),
`llm.py:164-180` (`metrics()`), consumed at `trace.py:55-56`, `:64-65`, `:74-76`.

**Probe:** `p09_refine.py` section (c') — two runs of the *identical* scripted scene,
differing only in transport latency (1 ms vs 9 ms):

```
artifacts that differ between two identical scripted runs:
  ['actor_exchanges.jsonl', 'runtime_metrics.json', 'world_exchanges.jsonl']
ledger.jsonl among them: False
journal.jsonl among them: False
total_wall_s: 0.02 vs 0.17
```

The ledger, journal, views, memory updates, event queue, terminal result, trajectory.md
and replay verification are all byte-stable. Only the three call-log artifacts carry
wall time. This does not touch the replay guarantee but does mean
`artifacts/simulations/*/` is not byte-reproducible, which is how the current
`git status` shows those directories perpetually dirty.

**Fix:** move `wall_s` / `total_wall_s` into a separate `timings.json` excluded from
reproducibility comparison, or round to a coarse bucket.

### F9 — `run_simulation.py` defaults the simulation start to the wall clock

**Where:** `run_simulation.py:42-46`.

```python
start = args.start or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
```

`start` feeds `trajectory_id_for(question, start, cutoff)` (`adapter.py:42-44`) and every
timestamp in the world. Two invocations of the same command one second apart produce
different trajectory ids and completely different ledgers. `--start` fixes it, but the
default path is not reproducible. Note the adapter itself is clean — the dependency is
in the entry point.

**Severity: MEDIUM** — relevant to claim 4 as shipped, trivially avoidable.

---

## LOW

- **`event_order_hash` is not a hash.** `replay.py:30` is
  `canonical_json([e["event_id"] for e in events])` — the raw list, verbatim, written
  into `replay_verification.json`. Misleading name; grows unbounded with the run.
- **Observation `source` is uncompared.** `p05_observed.py`: rewriting the `source` of
  every `journal.observed` record leaves `exact == True`. Provenance-only, harmless in
  isolation, but part of the F2 pattern.
- **`replay_trajectory` propagates `WorldIntegrityError` uncaught.** A ledger not
  beginning with `world.genesis` (`world.py:427-428`) raises out of `run_simulation.py:85`,
  losing an otherwise complete run before any artifact is written.
- **`trace.write_artifacts` leaks file handles.** The `j = lambda …: open(...).write(...)`
  at `trace.py:38-40` relies on CPython refcounting to close. No absolute paths, no
  wall-clock timestamps and no unordered iteration were found in the artifact writers
  themselves — `_write_jsonl` uses `canonical_json` (sorted keys) and every dict
  comprehension iterates `world.records` or a `sorted(...)` view.

---

## Attacks that FAILED to break it

These were tried in earnest and the runtime held.

1. **`PYTHONHASHSEED`.** `p01_repeat_and_hashseed.py` run under
   `PYTHONHASHSEED ∈ {0, 1, 12345, 987654321, random}` in separate subprocesses. Ledger
   SHA-256 `8b71570a3d9d…`, world `state_hash` `5f528d0e91ee…`, adapter `state_hash`
   `b546d2af01db…` and `trajectory_id traj_871d615a927d` were **identical in all five**.
   Every set in the hot path is used for membership only; every dict is iterated in
   insertion order or through `sorted()`; `journal.events()` (`journal.py:94-97`)
   derives `observed_by` by filtering the ordered `audience` list against a set rather
   than iterating the set.
2. **Repeat determinism.** The same scripted scene run twice in one process produced
   byte-identical ledgers and identical `SemanticTrajectory` dicts. Claim 3 holds:
   `instantiate_scene_manifest` is byte-deterministic, `trajectory_id_for`
   (`adapter.py:42-44`) is a plain SHA-256 of `question|start|cutoff`, and
   `actor_id_for` (`adapter.py:34-39`) is order-stable over the manifest's actor list.
3. **Claim 5 — observation transitions.** `p05_observed.py`. `journal.observed` survives
   replay exactly: `bo_ferrer`'s 18 observed event ids and `ada_vance`'s 1 are identical
   between the live and replayed journals. Deleting the observation → detected
   (`views_match`). Reassigning it to the other actor → detected (`views_match`).
   **Forging an observation for an actor not listed in the event's `for`** is rejected by
   the projection itself — `journal.py:94-97` intersects with `audience`, so the forged
   actor never appears in `observed_by` and never enters a view. The write-time guard at
   `journal.py:71-74` and the read-time projection agree.
4. **Replay does not mutate the live world.** `p07_mutation_and_artifacts.py`:
   `state_hash`, full canonical ledger bytes, record count (149 → 149) and clock all
   unchanged across `replay_trajectory`. No reducer writes into the record `data` it is
   handed; the ones that would (`_red_action_propose`, `_red_watch_add`,
   `_red_actor_reconsider`, `world.py:718/583/639`) `deepcopy` first. One aliasing
   *hazard* exists — `from_records(live=True)` pushes queue `Event`s whose `data` **is**
   the live record's payload dict (`world.py:461-463`; 1 of 1 pending entries in the
   reference run) — but nothing on the current code path writes through it.
5. **Truncation.** Truncating the ledger to 99 %, 90 %, 50 % and 25 % was detected every
   time. Truncating only the trailing non-reducing records was detected. Truncation is
   the one corruption class replay handles well, because it moves the last record's `seq`
   and `t`, which `state_hash` and the clock both see.
6. **Reordering committed events.** Swapping the first two `journal.event` records is
   detected by `event_ids_match`. Reversing the whole ledger is rejected outright by the
   reducers (`unknown actor 'bo_ferrer'`).
7. **Appending forged state.** Appending a forged private memory, a rewritten
   `scene:question`, or any record with a fresh `seq` is detected — the first two by
   `state_hash_matches` and `views_match`, the last only because `snapshot()["version"]`
   moves. (Reusing the previous `seq` defeats this — see F2.)
8. **Private context leakage into views.** Stripping `semantic.actor_profile` records is
   detected by `views_match`, because `build_view` (`views.py:50`) reads
   `journal.profiles()`. Compiler-provided private context *is* covered.
9. **Filesystem / locale dependence.** No absolute paths, `os.getcwd()`, `os.listdir`,
   `time.time()`, `random`, or `id()`-derived values were found in `replay.py`,
   `journal.py`, `adapter.py`, `views.py`, or the reducer table. `write_artifacts` takes
   `out_dir` as a parameter and never records it.

---

## Recommended fixes, in priority order

1. `replay.py:21` — deep-copy or JSON round-trip the records before reconstruction. Kills
   F1 outright.
2. `replay.py` — add `"ledgers_match": canonical_json(world.records) == canonical_json(live_world.records)`
   and `"record_count_matches"` to the `exact` conjunction. Kills F2 and most of F5.
3. `world.py:446-450` — validate `seq` monotonicity, `t` monotonicity, and `cause`
   (`None` only before `genesis.sealed`, otherwise a strictly smaller existing `seq`)
   inside `from_records`. Kills F3.
4. `replay.py:46-47` / `:49-53` — compare `canonical_json(events)` and full `Memory`
   tuples rather than id lists and content lists. Kills F5 and F6.
5. `replay.py:58-61` — refuse to report `exact` when there is nothing to verify; carry
   `trajectory.status` into the artifact. Kills F4.
6. `run_simulation.py:85` — write `ledger.jsonl` first and replay it from disk. Kills F7.

Fixes 1–4 are roughly ten lines and would have caused every one of the twelve
undetected tampers in F2 to fail.
