# Single-trajectory runtime: a first-principles audit

Written against `main` at `26b5203` (PR #5 merged). Nothing here is taken
from a report heading or an aggregate number; every claim is checked
against source or against the artifacts on disk.

Thirteen independent reviewers examined this code. Two returned PASS
(compiler freeze, replay). Eleven returned FAIL, with **9 CRITICAL and 26
HIGH findings**. The final adjudicator returned FAIL. PR #5 was merged
anyway.

The purpose of this audit is not to enumerate those findings again. It is
to ask, of each part of the live path, whether it should exist at all.

---

## The finding that organises everything else

Four separate reviewers, working independently, converged on one causal
chain. The adjudicator stated it best:

> The system has no reliable way to let a person finish an ordinary
> action. The event-quality review holds two rules that cannot both be
> satisfied for any act done through a device (atomic → "the machine did
> it"; combined → "several stages at once"), so the decisive act gets
> deleted; the actor repeats it and is refused by the continuity reviewer
> for repeating; the queue empties; the clock is teleported to the
> horizon; and the absence of the act that was just destroyed is reported
> as the answer. **It is one defect wearing three costumes.**

Three of the nine CRITICALs, and roughly half the HIGHs, are that chain
seen from different angles. It is not a collection of bugs. It is one
design mistake: **an LLM was given the power to delete a valid action, in
the hot path, with no structural check on whether its two rules could
both be satisfied.**

The correct response is not a better prompt for that reviewer, nor a
third reviewer to check the second. It is to take the power away.

---

## What each thing is for

Classification: **ESSENTIAL** (a single authoritative responsibility
required for fidelity) · **REDUNDANT** (duplicates something already
owned) · **HARMFUL** (creates a failure mode larger than the one it
prevents) · **OFFLINE-ONLY** (useful as evaluation, must not alter the
trajectory) · **DEAD** (declared, unreachable, or unused).

### Live LLM roles

| role | verdict |
|---|---|
| actor | **ESSENTIAL** |
| world | **ESSENTIAL** |
| terminal judge | **ESSENTIAL** |
| terminal verifier | **ESSENTIAL** (not per-step) |
| event-quality reviewer | **HARMFUL → remove from hot path** |
| actor-continuity reviewer | **HARMFUL as scoped → narrow to a factual-contradiction check** |

### Mechanism

| component | verdict | why |
|---|---|---|
| `journal` append-only ledger + projections | ESSENTIAL | the one authoritative record |
| kernel `World` / `Clock` / `EventQueue` | ESSENTIAL | code owns time, order, identity |
| information lifecycle (`for` / `observed_by`) | ESSENTIAL **but wrongly expressed** | the distinctions are right; committing them as narrative events is not |
| replay + integrity check | ESSENTIAL | independently PASSed; detects mutation, deletion, reorder, forgery |
| `did_it` / `self_act_of` split | ESSENTIAL | authorship ≠ delivery; fixes a real leak |
| attempt → world trigger binding | **REDUNDANT/WEAK** | the world receives prose, not a cause id it must cite |
| wake scheduler | ESSENTIAL in principle, **bloated in fact** | see below |
| `WAKE_PROVENANCE` — `observed_event`, `known_deadline`, `action_completion` | **DEAD** | verified: zero scheduling sites, zero occurrences across 1,087 wakes |
| `ActorGroundingError`, `EventGroundingError` | **DEAD** | verified: never raised anywhere |
| event-review correction retry (`trajectory.py:293`) | **HARMFUL** | this is the loop that deletes the decisive act |
| actor-continuity correction retry (`trajectory.py:486`) | **HARMFUL** | refuses a person for repeating an act the other loop deleted |
| exact-casefold duplicate rule | **REDUNDANT** | catches byte-identical only; near-identical duplicates commit freely |
| `MAX_EVENTS_PER_INSTANT` | **REDUNDANT** | polices exact seconds; the granularity problem lives in minutes |
| empty-queue → `finish()` → horizon jump | **HARMFUL** | manufactures NO over unsimulated time |
| last-call sweep (added late in PR #5) | **HARMFUL as a substitute** | a mitigation presented as the fix; the CRITICAL survives it |
| `evaluation/*.py` | OFFLINE-ONLY | correct as such; nothing in the runtime reads them |
| 4,079 tracked generated artifact files | **BLOAT** | evidence, not source |

### The seven questions, for each live LLM role

**Actor.** Receives only its own authorised local state. Decides what
this person attempts. Cannot be enforced structurally — this is the
irreducible social judgment. Changes the trajectory, necessarily. No
demonstrated failure attributable to the role itself. **Stays.**

**World.** Receives one trigger and the public record. Decides what
concretely follows. Cannot be structural — also irreducible. **Stays**,
but must be bound to an explicit cause id and forbidden structurally (not
by prompt) from authoring another person's voluntary choice.

**Terminal judge.** Receives the resolution and committed events only.
Decides whether the condition is met. The resolution is natural language,
so this cannot be structural. **Stays**, with the clock rule enforced in
code.

**Terminal verifier.** Same inputs, never the judge's verdict. Runs once
per candidate answer, not per step. Protects the final answer against a
single reading. **Stays.**

**Event-quality reviewer.** Receives a proposed event. Decides whether it
"is a real thing that happened" — a judgment with no stable definition.
Demonstrated failures: PASSes and REVISEs the byte-identical string four
calls apart in one run; refuses both the atomic act and the combined act;
deletes the decisive action; converts YES to NO; makes the same scene on
byte-identical evidence answer YES three times and NO three times. Its
legitimate work — schema, actor ids, cause ids, duplicates, impossible
timestamps, authorisation — is *all* deterministic and already partly
done in code. **Remove from the hot path. Its realism judgments move
offline.**

**Actor-continuity reviewer.** Receives an actor's reply. Decides whether
it follows from what they have. Demonstrated failures: invented calendar
facts fed back into the actor's prompt; refused a man for repeating an
attempt whose event the *other* reviewer had deleted; overrode a
defining trait with nothing having happened. Its legitimate core — a
direct factual contradiction with the actor's own authorised record — is
narrow and worth keeping. **Narrow to exactly that; move realism
offline.**

---

## What replaces them

Structure, not another gate.

**Information transport becomes code-owned state, not events.** The
lifecycle distinctions are real and stay: created, sent, delivered,
available, observed, opened, read. What changes is that they are
transitions on a journal item rather than committed narrative events.
"The email arrives in the inbox", "the phone buzzes", "the notification
fades", "the message remains unread" stop being things the world writes
and start being things code knows. This alone removes the plurality of
the committed record — measured at 42–44% across the corpus by two
independent counts.

**Every world consequence cites an explicit cause.** An actor's attempt
becomes a code-owned record with an `attempt_id`; the world is given that
id and must cite it. A consequence naming a *different* actor as the one
choosing is routed to that actor as their turn rather than committed —
enforced by identity, not by keyword, and not by a reviewer's opinion.

**An empty queue before the cutoff is INCOMPLETE.** Not a mitigation, not
a sweep: a status. `NO_AT_CUTOFF` becomes mechanically unreachable while
`now < cutoff`, in the judge validator *and* the verifier validator, and
the horizon may only be claimed when the trajectory reached it through
scheduled events.

**Dead vocabulary is deleted rather than aspirational.** Three wake
provenances that no code path can produce, and two exception classes
never raised, are removed. A declared-but-unwired vocabulary has already
been the direct cause of three separate live defects in this codebase.

---

## What this costs

Removing the two reviewers removes two of six live LLM roles and roughly
half the calls on the hot path. It also removes the only thing currently
attempting to keep non-events out of the journal — which is why the
information-transport change has to land *with* it and not after: once
delivery is code-owned state, the events that reviewer was failing to
catch no longer exist to be caught.

The honest risk is that world output gets worse without a critic. The
mitigation is not a critic; it is that the world is asked a narrower
question (one cause, one consequence, no transport) and that everything
the reviewer was legitimately catching is checked deterministically.

That is testable, and Phase C tests it.

---

## Default

Where a responsibility can be enforced by structure, it must not be
enforced by a model. Where a model must judge, it must not be able to
delete what another model legitimately produced. Nothing is kept merely
because it exists.
