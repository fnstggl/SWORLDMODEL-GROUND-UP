# Agent A — code correctness review (status and findings)

**Process disclosure:** the independent Claude reviewer agent was
terminated mid-review by the account's monthly Claude spend limit.  Before
termination it authored three executable probes (parsing/logging, budget
enforcement, timeout enforcement).  The lead agent ran and re-ran those
probes, fixed what they exposed, and verified the fixes against the same
probes — so the *findings* below are independently authored and
mechanically verified, while the *narrative completion* of the review is
by the lead agent (not independent self-certification of untested claims:
every claim here is a probe result).

## Findings (both fixed and re-verified)

### A-1 (HIGH, fixed): unexpected transport exception consumed a semantic
slot with zero logged requests
`SceneCaller.semantic_call` logged attempts only for the anticipated
exception tuple; an unexpected exception class from the transport escaped
the logging path — a semantic slot was counted with `provider requests
logged: 0`, hiding the attempt.  Fix: every attempt is logged whatever the
failure class (`except Exception` with the entry appended before
re-raise/continue).  Probe now shows `provider requests logged: 2` for the
same scenario, and the JSONDecodeError control still retries and logs
(`attempts logged: 2` → structured `TechnicalFailure`).

### A-2 (HIGH, fixed): header-level stalls evaded the total deadline
The 300 s total deadline covered only the body-read loop; `urlopen()`
itself (connect + headers) was bounded only by the 90 s *per-operation*
socket timeout, so a header-dripping server could stretch a request far
past any wall (probe: 1 s deadline, request completed at 3.2 s,
"NOT ENFORCED").  Fix: the entire provider request now runs in a worker
thread joined against `TOTAL_REQUEST_DEADLINE_S = 330 s`; on expiry the
thread is abandoned and `TimeoutError` flows into the logged
retry → `TechnicalFailure` path.  Direct verification: a 5 s header-level
stall under a patched 1 s wall produced a structured `TechnicalFailure`
at 2.0 s (two attempts, both logged).

### Probe 2 — budget enforcement: PASSED as designed
`compiled | slots: 2 | provider requests: 3 | attempt numbers: [0, 1, 0]`
(a technical retry inside slot 1 is logged and does not open a new slot);
the fourth-slot attempt fails with `COMPILER_CALL_BUDGET_EXCEEDED`
*before* any request; `per_slot` attempt accounting reconciles with the
raw request log.  "ALL BUDGET CHECKS PASSED."

## Remaining review coverage
Actor-name normalization, duplicate handling, visibility filtering, scene
serialization, instantiation determinism, replay, and mutable aliasing
are covered by Agent D's hostile probes (see HOSTILE_OUTPUT_REVIEW.md)
and the 160-test suite (`tests/test_scene_compiler.py` asserts private
context stays in the owning actor, undeclared actors receive nothing,
instantiate-twice hash equality, and replay equality).  Failure isolation
in the threaded harness is per-case (`compile_scene` never raises;
each case has its own `SceneCaller`).  No CRITICAL findings are open.
