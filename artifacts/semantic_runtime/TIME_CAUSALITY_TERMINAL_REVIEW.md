# Time, Causality and the Terminal — Adversarial Review

**Scope:** `sworldmodel/semantic_runtime/{trajectory,journal,envelope,resolution,replay}.py`
and the kernel it sits on (`sworldmodel/{world,simclock,events}.py`).

**Code under test:** commit `763147f` (findings first measured at `c7da707`; the tree
moved twice mid-audit — `81b8bd1`, `763147f` — and **every finding below was re-measured
and reproduces on `763147f`**). `pytest tests/test_semantic_runtime.py tests/test_time.py
tests/test_kernel_invariants.py` → 72 passed. The findings are not artifacts of a broken tree.

**Method:** standalone probes under
`/tmp/claude-0/-home-user-SWORLDMODEL-GROUND-UP/d6ed917c-38bc-56aa-a050-80f5be912f4e/scratchpad/audit_time/`
(`harness.py`, `p1_time_cutoff.py`, `p2_causality.py`, `p3_terminal.py`, `p4_failure.py`,
`p5_incomplete.py`, `p6_final.py`) driving the **real** runtime with scripted transports.
No live API was called anywhere. No file under `sworldmodel/`, `compiler/`, `tests/` or
`run_simulation.py` was modified.

---

## Verdict at a glance

| # | Claim | Verdict |
|---|-------|---------|
| 1 | Time never moves backwards; timestamps code-owned; no LLM writes a timestamp | **HOLDS** for the three runtime roles. Broken at the edges by C-1/H-4 and the compiled manifest (M-3) |
| 2 | Every committed event has an explicit cause; the chain is unbroken to genesis | **HOLDS in practice, UNENFORCED** — H-3 |
| 3 | Nothing is committed beyond the cutoff | **HOLDS in-run; FALSIFIED at setup** — H-4 |
| 4 | The terminal is false at initialization | **HOLDS** — survived every attack |
| 5 | YES requires a real committed event; intentions/memories/judgments cannot satisfy it | **HOLDS within a trajectory; FALSIFIED across trajectories** — H-2 |
| 6 | NO_AT_CUTOFF impossible before the cutoff; UNRESOLVED impossible at it | First half **HOLDS**. Second half is `final`-scoped, not time-scoped — M-1, L-1 |
| 7 | Exactly one of resolved/cutoff/failed; `failed` = nothing partial committed | **FALSIFIED on both halves** — C-1, H-1, M-2, M-8 |
| 8 | Queue pops in time order; ties deterministic; clock only advances | **HOLDS** — survived every attack |

---

# CRITICAL

## C-1 — A run truncated by the call ceiling is laundered into a definitive `NO_AT_CUTOFF` over time it never simulated

**Files:** `sworldmodel/semantic_runtime/trajectory.py:407-410`, `:412-421`, `:276-297`;
`sworldmodel/semantic_runtime/llm.py:128-131`

**Probe:** `p5_incomplete.py` P5.1/P5.3, `p6_final.py` P6.4, plus a parameterised sweep.

**Expected.** `trajectory.py:281-286` states the invariant in its own words:

> "A run that stopped early because it ran out of steps or calls is a different thing
> entirely: the trajectory never reached the horizon … Such a run is reported as
> incomplete and may still return YES on what it did commit — **but it may never return
> NO, because that would turn a budget artifact into an answer.**"

`trajectory.py:407-410` implements exactly that for the call ceiling:

```python
if caller.budget_exhausted():
    return finish(f"call ceiling {caller.max_calls} reached at "
                  f"{_iso_now(world)}, before the cutoff", truncated=True)
```

**Observed.** That branch is **unconditionally dead**. `finish(truncated=True)` calls
`judge(final=False)` (`trajectory.py:290`), which passes `reserved=final` → `reserved=False`
(`trajectory.py:263`), which makes `RuntimeCaller.ask` use the *ordinary* ceiling
(`llm.py:128`) and immediately raise:

```python
ceiling = self.max_calls if reserved else self._ordinary_ceiling()
if len(self.calls) >= ceiling:
    raise CallBudgetExceeded(...)
```

But `budget_exhausted()` is *defined* as `len(self.calls) >= self._ordinary_ceiling()`
(`llm.py:66-68`) — the exact condition that got us here. So the raise is guaranteed.
`CallBudgetExceeded` is then caught at `trajectory.py:412` and `finish()` is re-entered
**with `truncated` defaulting to `False`** (`:417`), which advances the clock to the
cutoff (`:288-289`) and takes a `final=True` judgment that re-permits `NO_AT_CUTOFF`.

Measured sweep (`world` proposes a 5-minute step; `max_steps=500`):

```
max_calls | status | answer       | steps simulated
   3      | cutoff | NO_AT_CUTOFF |  0
   4      | cutoff | NO_AT_CUTOFF |  0
   5      | cutoff | NO_AT_CUTOFF |  0
   8      | cutoff | NO_AT_CUTOFF |  2
  12      | cutoff | NO_AT_CUTOFF |  4
  20      | cutoff | NO_AT_CUTOFF |  8
  40      | cutoff | NO_AT_CUTOFF | 20
  80      | cutoff | NO_AT_CUTOFF | 42
```

Never `incomplete`; always `NO_AT_CUTOFF`. P6.4 shows the exact call tape:

```
c1 judge  sim_time=2026-07-27T14:00  ok      <- initial terminal check
c2 world  sim_time=2026-07-27T14:00  ok
c3 actor  sim_time=2026-07-27T14:00  ok      <- ordinary ceiling (3) now spent
c4 judge  sim_time=2026-08-10T14:00  ok      <- clock teleported to the cutoff
terminal records: [(final=False,'UNRESOLVED'), (final=True,'NO_AT_CUTOFF')]
status=cutoff  answer=NO_AT_CUTOFF  steps=0
```

P5.3 quantifies the damage: the last committed event sits at `2026-07-27T14:05`, the
judgment is taken at `2026-08-10T14:00` — **13 days 23:55:00 of simulated time was never
simulated at all**, and a definitive negative answer is asserted over it.

**Why CRITICAL rather than HIGH.** Every other finding corrupts internal state or a
guarantee; this one manufactures a *wrong published answer*. The system's entire output is
YES/NO on a forecasting question, and this path converts "we ran out of budget" into "the
deadline arrived and it did not happen," with `final=True` stamped on the ledger record.
It is also **enshrined in a passing test** — `tests/test_semantic_runtime.py:543-555`
(`test_spending_the_call_ceiling_is_a_horizon_not_a_failure`) asserts
`traj.status == "cutoff"` and `traj.answer["status"] == "NO_AT_CUTOFF"`, in direct
contradiction with its sibling `test_a_truncated_run_is_incomplete_and_can_never_answer_no`
(`:659-681`). The two tests encode opposite invariants and both pass.

**Aggravating:** commit `81b8bd1` ("Silence is not the end of a situation",
`trajectory.py:327-335`) now reschedules rechecks whenever the queue empties before the
cutoff. That makes runs consume strictly more budget, so the call ceiling — and therefore
this path — fires *more* often, not less.

**Minimum fix:** `finish(truncated=True)` must not need a provider call it cannot make.
Either pass `reserved=True` for the truncated judgment as well (and account for it in
`RESERVED_FINAL_CALLS`), or make the `except CallBudgetExceeded` handler at `:412`
re-finish with `truncated=True`. Then reconcile the two contradictory tests.

---

# HIGH

## H-1 — `failed` does not mean the failing step committed nothing

**Files:** `trajectory.py:337-364` (the step body), `:175-212` (`actor_step`),
`:118-172` (`world_step`)

**Probe:** `p4_failure.py` P4.1/P4.2, `p6_final.py` P6.5.

**Expected.** Claim 7 and the module docstring (`trajectory.py:17-19`): "this module …
enforces the transactional rule that a failed or invalid response commits nothing."

**Observed.** The transaction boundary is the **call**, not the **step**. `caller.ask`
is indeed atomic — an invalid response is retried once and then raises, having written
nothing. But a single queue step performs *many* calls, each committing as it returns.

P6.5 — the world commits an observed event, the actor call then fails on both attempts:

```
status=failed
after the last event.fired the step wrote: Counter({'journal.event': 1})
durable journal events committed inside the failing step: ['e17']
```

`e17` is a permanent entry in the authoritative history of a run reported as `failed`.

P4.1 — actor returns three intentions; the third world adjudication is unusable:

```
status=failed
the failing step had already written 1 semantic.actor_call, 3 actor.memory,
2 semantic.world_call and 2 event.scheduled records
2 events remain queued at the moment of failure
```

So a `failed` run leaves behind committed journal events, actor memories, world-judgment
records, and a *live queue of scheduled future events*. Downstream consumers that treat
`failed` as "discard, nothing happened" are wrong; the ledger is a partially-executed
trajectory.

**Fix direction:** either mark the step boundary in the ledger so a partial step is
identifiable and skippable on replay, or checkpoint the ledger length at the top of the
step and refuse to report `failed` without stating what survived.

---

## H-2 — The judge's admissible-citation set is not scoped to the trajectory

**Files:** `journal.py:81-102` (`events()`), `trajectory.py:250-252` (`judge`),
`journal.py:37-50` (`commit` writes `trajectory_id` and nothing ever reads it)

**Probe:** `p3_terminal.py` P3.3.

**Expected.** Claim 5. Every committed event carries a `trajectory_id`
(`journal.py:49`) — the field exists precisely so events belong to a trajectory.

**Observed.** `trajectory_id` is **write-only**. `grep -rn trajectory_id` over the whole
repo shows it written at `trajectory.py:145,196,271,351`, `adapter.py:91`,
`journal.py:49` — and read by nothing. `Journal.events()` returns every `journal.event`
record in the world regardless of trajectory, and `judge()` builds
`known_event_ids = {e["event_id"] for e in events}` from it.

Two trajectories on one world, trajectory 2 committing **zero** events of its own:

```
traj1=traj_6c2ac9dc4a94  traj2=traj_9d3a8ba7b8ba
traj2 own committed events: []
traj2 status=resolved
traj2 answer={'status':'YES','supporting_event_ids':['e17'],
              'explanation':'an event from the other trajectory shows it'}
e17 belongs to traj1
```

A trajectory that committed nothing resolved **YES** by citing a foreign trajectory's
event, and the validator accepted it. The same hole means any journal event committed into
the world *before* `run_trajectory` is called is also admissible (which is exactly what
`tests/test_semantic_runtime.py:112-114` does in setup).

**Reachability today:** latent. The only production call site (`run_simulation.py:83`)
builds a fresh world per trajectory, so this cannot currently fire. It is reported HIGH
because (a) `run_trajectory` is exported public API (`semantic_runtime/__init__.py:22`),
(b) the codebase already carries the field whose entire purpose is preventing this, and
(c) any future resume/replay/multi-trajectory path silently inherits it.

**Fix:** one line — filter `events()` (or the judge's set) by `trajectory_id`.

---

## H-3 — `cause` is never validated: a broken causal chain is accepted, invisible, and replayable

**Files:** `world.py:105-121` (`apply`), `world.py:336-351` (`lineage`),
`semantic_runtime/replay.py:17-62`

**Probe:** `p2_causality.py` P2.2/P2.3/P2.4.

**Expected.** Claim 2 — "the causal chain is unbroken back to genesis."

**Observed.** `World.apply` checks only that `cause is not None` after genesis
(`world.py:108-112`). It never checks that the value names an existing record, that it
precedes the effect, or that it is even an integer. All five forged causes were accepted:

```
nonexistent seq 99999        ACCEPTED   chain broken
negative seq -1              ACCEPTED   chain broken
forward reference (own seq+) ACCEPTED   chain broken  <- effect precedes its cause
string cause "not-a-seq"     ACCEPTED   chain broken
float cause 3.5              ACCEPTED   chain broken
```

The break is then **silent** in every direction:

* `lineage()` walks `by_seq.get(cur["cause"])` (`world.py:350`). A dangling cause yields
  `None`, which terminates the walk identically to reaching the origin. Measured: the
  lineage of a record with `cause=3.5` prints `[(16, 'journal.event')]` — one hop, no
  marker. `lineage()` explicitly flags *truncation* (`world.py:344-346`) but not a
  dangling link.
* `World.from_records` replays the ledger with no causality check at all; at commit
  `763147f` `replay.py` reported `exact` reconstruction of the corrupt ledger
  (`state_hash=a744aa48…`).

> **Concurrent work — partially closed.** An uncommitted rewrite of `replay.py` in the
> working tree (another agent, in flight at the time of writing) adds a `ledger_integrity`
> check. Re-running the same probe against it gives
> `ledger_integrity: ['seq 12 names a cause 99999 that does not exist before it']` and
> `exact=False`. That closes the **detection** half (M-9). The **prevention** half stands
> unchanged: `World.apply` still accepts `cause=99999` at write time, and `lineage()` is
> still silent about the break. A corrupt chain is now caught only at replay, after it is
> already durable in the ledger.

**What holds.** The runtime's *own* paths never produce a bad cause. P2.1 walked all 33
committed events of a full run to genesis with zero breaks, and P2.6 confirmed every
journal event names an `event.fired` or `genesis.sealed` record. So claim 2 is true of the
current code — it is a **convention, not an invariant**, with no detector anywhere.

**Fix:** in `World.apply`, require `isinstance(cause, int) and 0 < cause <= self._seq`;
in `lineage()`, emit `{"dangling": True, "cause": …}` instead of stopping silently.

---

## H-4 — An inverted horizon (`start > cutoff`) is accepted and commits events beyond the cutoff

**Files:** `trajectory.py:93` (`cutoff = parse_iso(bindings["cutoff"])` — no ordering
check), `adapter.py:82-97` (no bounds check on `starting_events[].time`)

**Probe:** `p1_time_cutoff.py` P1.6/P1.7, `p6_final.py` P6.3.

**Expected.** Claim 3 — "nothing is ever committed beyond the cutoff instant."

**Observed.** With `start = 2026-09-01` and `cutoff = 2026-08-10`, the run is accepted and:

```
status=cutoff  clock=2026-09-01T14:00:00+00:00  cutoff=2026-08-10T09:00:00-05:00
committed events beyond the cutoff: ['2026-09-01T14:00:00+00:00']
answer=NO_AT_CUTOFF
```

A committed journal event sits **22 days past the cutoff**. `finish()` then declines to
advance the clock (`:288`, `now < cutoff` is false) and the judge — seeing `now > cutoff` —
is permitted `NO_AT_CUTOFF` and takes it. Separately (P1.6), `adapter.py:94-97` will
happily schedule a starting event at `2027-01-01`, four and a half months past the cutoff.

**Reachability.** `compiler/scene_validate.py:63` rejects `cutoff <= start` and `:148`
rejects starting events after the cutoff — but **that validation is not in the layer under
audit and is bypassed on two live paths**: `run_simulation.py:52-57` (`--scene`) loads a
stored manifest and calls `instantiate_scene_manifest` directly with no validation, and
`--start/--cutoff` are accepted from the CLI with no ordering check
(`run_simulation.py:42-46`). The runtime has no horizon guard of its own.

**In-run containment holds.** Every *in-run* cutoff path was attacked and survived:
30-day step floods (P1.2), events due exactly at the cutoff (P1.4, 2 committed *at*, 0
beyond), events one second past it, a 32-event run with zero `event.scheduled` and zero
`event.fired` records past the cutoff (P1.5). The failure is entirely at setup.

**Fix:** `run_trajectory` should reject `cutoff <= start`; `instantiate_scene_manifest`
should reject or drop starting events outside `[start, cutoff]`.

---

# MEDIUM

**M-1 — `incomplete` can still carry a `NO_AT_CUTOFF` answer.**
`trajectory.py:290` passes `final=not truncated` to `judge`, but `make_validator`
(`resolution.py:121`) gates `NO_AT_CUTOFF` purely on `now < cutoff`; `truncated` never
reaches it. Probe P5.2: a run whose single step lands exactly on the cutoff and then trips
the step ceiling produces `status='incomplete'` with `answer='NO_AT_CUTOFF'` — the exact
pairing `finish()`'s docstring forbids. Pass `truncated` into the validator.

**M-2 — Seven inputs escape `run_trajectory` as uncaught exceptions.**
Setup (`trajectory.py:91-95`) sits *outside* the `try` at `:300`, and the handler tuple at
`:423` covers only `EnvelopeError | RuntimeTechnicalFailure | ValueError`. Probe P6.6:

```
malformed cutoff string             ValueError (raised before the try)
naive (tz-less) cutoff              ValueError (raised before the try)
missing 'cutoff' key                KeyError
missing 'trajectory_id' key         KeyError
starting_event_ids naming e999      TypeError: 'NoneType' object is not subscriptable
transport raises BaseException      KeyboardInterrupt (llm.py:164 catches Exception only)
clock near datetime.max + 30 days   OverflowError
```

Also `p2_causality.py` P2.5: a world with no `genesis.sealed` record makes
`next(...)` at `trajectory.py:301` raise bare `StopIteration`, uncaught.

**M-3 — The compiled manifest, not code, sets absolute simulated instants.**
Claim 1 says "no LLM ever writes a timestamp." That is airtight for the three *runtime*
roles: P6.1 showed all 13 time/provenance field names (`t`, `time`, `at`, `timestamp`,
`occurred_at`, `when`, `event_id`, `seq`, `cause`, `caused_by`, `trajectory_id`, `source`,
`observed_by`) rejected by `validate_event`, and 4 by the judge validator; P6.2 confirmed
across 65 committed events that every `t` equals the ledger clock and no time-bearing key
appears in any payload. But `starting_events[].time` in the manifest *is* compiler-LLM
output, and `adapter.py:82,94` adopts it verbatim as a scheduled instant that the clock
then advances to (P6.3). The claim should be scoped: "no runtime role writes a timestamp."

**M-4 — Huge durations escape as `OverflowError`, not `EnvelopeError`.**
`envelope.py:101` builds `timedelta(seconds=seconds)` *before* the `MAX_STEP_DAYS` check at
`:102`. `"99999999999999999999 days"` raises `OverflowError: Python int too large to
convert to C int`. It is contained (caught by `llm.py:164`, retried, then
`RuntimeTechnicalFailure` → `status=failed`), but the corrective-retry text added in
`llm.py:140-144` feeds the model a C-level message it cannot act on. Bound the numeric
value before constructing the `timedelta`. The rest of the new multi-part grammar survived
20 hostile strings cleanly (P6.7): `-5 minutes`, `5 minutes ago`, `in 5 minutes`,
`about 2 hours`, `1.5.5 days`, `3 weeks 10 days`, `30 days 1 seconds` all correctly
rejected; nothing over 30 days accepted.

**M-5 — The judge is not told about partial non-observation.**
`resolution.py:82-83` renders `observed_by` as `"observed by X"` and drops the remainder.
For an event `for: [ada, bo]` with only `ada` having observed it, the judge sees
`| observed by ada_vance` with no mention that `bo_ferrer` has not
(P3.8). `journal.render_for_world` (`journal.py:135-139`) *does* append
`"; not yet observed by …"` for the world. Since the judge's core rule is "only an event
they actually observed can satisfy it," this asymmetry can produce a wrong YES.

**M-6 — An unusable final judgment discards the whole trajectory.**
P5.4: a judge that hallucinates a citation at the true horizon fails validation twice →
`RuntimeTechnicalFailure` → `status=failed, answer=None`. A fully simulated 14-day
trajectory with a valid committed history is thrown away because the last call was
malformed. A fallback (e.g. re-ask with the admissible id set stated) would preserve it.

**M-7 — Status-vocabulary drift.**
The dataclass now documents five values (`trajectory.py:61-67`) and three were produced in
one probe run (`cutoff`, `incomplete`, `failed`). `run_simulation.py:97` still returns
`0 if traj.status in ("resolved","cutoff") else 1`, so a legitimate `incomplete` run exits
non-zero and reads as a process failure to any caller/CI.

**M-8 — The kernel's zero-time-loop guard is inert in this runtime.**
`world.schedule` only computes a nonzero same-instant `depth` when `self._ctx_time is not
None` (`world.py:140-147`), and `_ctx_time` is set only by `engine.py`, which the semantic
runtime does not use. Every `event.scheduled` record in every probe carried `depth=0`, so
`MAX_SAME_INSTANT_DEPTH = 60` and `ZeroTimeLoopError` are unreachable here. P4.6 — a world
returning `after:"now"` with observed events and 3 intentions per turn — produced
**401 committed events at a single instant** with the clock never moving, bounded only by
`max_steps`. Time did not run backwards and nothing passed the cutoff, so claims 1/3/8 are
not violated; but the kernel's stated protection is not in force.

**M-9 — Replay does not verify causality — *being fixed in the working tree*.**
Consequence of H-3, listed separately because `replay.py` is in scope. At commit
`763147f`, `replay_trajectory` reported `exact` reconstruction of a ledger containing five
dangling causes; it checked state, event ids, views, memories and the terminal — never the
cause graph. An **uncommitted** rewrite of `replay.py` present in the working tree adds a
`ledger_integrity` field that catches exactly this (verified: see the note under H-3).
Treat M-9 as closed once that lands; H-3's write-time prevention gap is separate and open.

---

# LOW

**L-1 — `UNRESOLVED` is forbidden by `final`, not by the clock.**
`resolution.py:125` reads `if final and status == "UNRESOLVED"`. The per-step check at
`trajectory.py:397` uses `final=False`, so a judgment taken at a step landing exactly on
the cutoff instant may legally return `UNRESOLVED` (P3.4). Harmless in practice — the run
still takes a `final=True` judgment afterwards — but the guard is one word away from
matching its own docstring (`resolution.py:15-16`, "UNRESOLVED cannot be returned AT the
cutoff").

**L-2 — Duplicate citations accepted.** `{"supporting_event_ids": ["e1","e1","e1"]}`
validates and is stored verbatim (`resolution.py:130`). Cosmetic.

**L-3 — The corrective retry echoes the exact cutoff instant to the judge.**
`resolution.py:122-124` embeds `now.isoformat() < cutoff.isoformat()` in the rejection
message, which `llm.py:140-144` now feeds back into the retry prompt. Minor, and the judge
already sees the current time.

---

# Claims that survived attack

These are stated explicitly, with the probes that **failed** to break them.

**Claim 4 — the terminal is false at initialization. HOLDS.**
P3.5: the very first provider call is a judge call, before any world or actor call
(`world_calls=0, actor_calls=0`); a scene whose starting event already satisfies the
resolution returns `resolved` with reason *"the compiled scene already satisfies its own
resolution at initialization"*. P3.6: with all starting events scheduled in the future,
`known_event_ids` is empty at init, so every citation is rejected and a greedy YES cannot
be forged — the run fails rather than resolving.

**Claim 5, within a trajectory — HOLDS.**
Attacked three ways and rejected every time. P3.1: a judge citing a **real, existing
`semantic.actor_call` id** (`c5`) — the id exists in the ledger, but the namespaces are
disjoint (`c*` for calls, `e*` for journal events, `journal.py:42`) and membership is
checked at `resolution.py:113-117`. P3.2: same for a `semantic.world_call` id (`c2`).
P3.4 unit sweep: YES with no citation, YES citing `e99`, YES citing `c1`, YES citing
`["e1","e99"]` (one good one bad), lowercase `"yes"`, and an extra `confidence` field —
all rejected. Private memories and intentions are never placed in the judge prompt at all
(`trajectory.py:255-261` passes only journal events).

**Claim 6, first half — HOLDS.** `NO_AT_CUTOFF` before the cutoff is rejected
(`resolution.py:121`, P3.4).

**Claim 8 — HOLDS.** P4.7: three identical scripted runs produced byte-identical
`state_hash` and identical event order across 47 events. Ordering is
`(t, depth, seq)` with `seq` unique (`events.py:38,50-54`), so ties are impossible.
P1.5: 32 scheduled events, none beyond the cutoff, none fired out of order. The clock is
advanced only forward, only to popped event times (`trajectory.py:340-341`), and
`Clock.advance_to` raises on any backwards move (`simclock.py:248-253`).

**Claim 1, timestamps — HOLDS.** P6.1/P6.2 above (see M-3 for the manifest caveat).
P1.2: a 30-day-step flood left timestamps monotone with none beyond the cutoff.
P1.3: a `"0 seconds"` flood over 87 steps advanced the clock normally via the backoff
rechecks and never moved it backwards.

**Claim 3, in-run — HOLDS.** P1.2, P1.4, P1.5 (see H-4 for the setup-side failure).

**Termination under hostile worlds — HOLDS.** P4.4: a world returning `event=null`
forever terminates cleanly at the cutoff with an honest `NO_AT_CUTOFF`. P4.5: a wake storm
(4 wakes per judgment, the `MAX_WAKES_PER_JUDGMENT` maximum) left the queue at 0 pending
and terminated in 36 steps. P5.5: a deep environmental chain with an empty audience
terminated at the cutoff. The `MAX_WAKES_PER_JUDGMENT=4` and
`MAX_INTENTIONS_PER_TURN=3` caps mean the model cannot set the runtime's own budget.

---

# Recommended order of work

1. **C-1** — fix the dead `truncated=True` branch and reconcile the two contradictory
   tests. This is the only finding that publishes a wrong answer.
2. **H-4** — add a horizon guard in `run_trajectory` / `instantiate_scene_manifest`;
   it is two comparisons and closes a claim-3 falsification on a live code path.
3. **H-2** — scope `journal.events()` (or the judge's id set) by `trajectory_id`. One line.
4. **H-1** — decide whether the transaction unit is the call or the step, and make the
   `failed` contract say which.
5. **H-3 / M-9** — validate `cause` in `World.apply`; mark dangling links in `lineage()`;
   add a cause-graph check to `replay_trajectory`.
6. M-1, M-2, M-5, M-7 are each small and independently shippable.
