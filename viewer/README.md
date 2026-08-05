# Frozen replay viewer

A read-only, self-contained static viewer over the frozen artifacts of the
under-the-hood validation in
`artifacts/full_trace_validation_20260804/`.

> **This is a presentation layer. The artifacts are the source of truth.**
> The viewer reads the committed artifact files directly and never
> regenerates, rewrites, summarises over, caches into, or becomes the
> source of truth for any simulation data. Nothing under `artifacts/` is
> written, moved, or modified by anything in this directory. If the viewer
> and an artifact disagree, the artifact is right and the viewer has a bug.

## One command

```bash
python3 viewer/serve.py
```

It serves the repository read-only on `http://127.0.0.1:8765` and opens
`http://127.0.0.1:8765/viewer/index.html`. Stop it with Ctrl-C.
`--port N` picks a different port, `--no-open` skips launching a browser.

A local HTTP origin is required, not a convenience: browsers refuse
cross-origin `file://` fetches of the artifact JSON, and `crypto.subtle`
-- which the viewer uses to recompute the published hashes -- exists only
in a secure context, which `http://localhost` is and `file://` is not. If
you open `index.html` off the disk anyway, the page says so in a red band
rather than silently showing an empty or unverified replay.

Any other static server rooted at the repository works too
(`python3 -m http.server`, for instance); `serve.py` simply adds
read-only enforcement, the right content types for `.jsonl`, and threading
so a browser's keep-alive connections cannot stall the page.

## What it shows

**Run selection.** All fourteen recorded runs: each of the three
scenarios (`peter_supplied`, `peter_generated`, `a16z_richard_historical`)
in both its pre-fix and its `post_fix_rerun/` form, plus the six counted
settling-experiment reps (arm A and arm B, three each) and the two kept
harness-shakedown runs, which are labelled as not counted in the reported
rates.

**Branch selection.** Every candidate branch of the selected run, with its
terminal status and committed-event count.

**Chronological playback** with play / pause / previous / next, a scrub
bar, a speed control, arrow-key and space-bar shortcuts, and a shareable
deep link (`#run=...&branch=...&entry=...`).

**Per step**, in the order the engine produced it:

1. simulation time,
2. the active actor,
3. what that actor could see -- **private context and shared context in
   separately banded boxes**,
4. the observations that actor received this step,
5. the exact model request, verbatim, for that actor only,
6. the raw model response,
7. the action the actor attempted,
8. the game master's input prompts and its raw response,
9. the proposed event before the guard,
10. any agency-guard intervention, with the original and rewritten text,
11. the final committed event, with its `sha256` recomputed and checked,
12. who received the resulting observation, and what was queued,
13. the state hash after the step, recomputed and checked,
14. the termination check.

**Then**, for the whole run: outcome metrics with their exact event
citations (click a citation to jump to that committed event), the final
ranking **or the refusal**, a side-by-side comparison of the candidate
branches, a published-hash verification summary, and a table of every raw
artifact file with a direct link to it.

**Always in the header**: the `UNCALIBRATED LIVE-MODEL EXPLORATORY
SIMULATION` banner, the model and provider and endpoint, the repository
SHA the run was recorded at, the compiler version and status, the compiled
world hash, the base plan id and content hash, the per-branch seed (read
as an exact literal, because these seeds exceed JavaScript's safe integer
range), the evidence classification counts with their rules, whether the
candidates were **supplied or generated** (declared by the catalog and
verified against each candidate's recorded provenance), and every known
limitation the artifacts state, each with the file that states it.

A refusal to rank is rendered as a **first-class result** -- its own
banner, its reason, and the per-branch delivery table -- never as an
error.

## Auditor-only labelling

`branches/*/step_ledger.jsonl` deliberately places every actor's private
context and every prompt side by side. **No actor ever saw that view.**

The convention in this viewer:

* anything derived from another actor's slice of a step, and the raw step
  ledger record itself, is wrapped in a red **`AUDITOR-ONLY -- NO ACTOR
  EVER SAW THIS`** band;
* the actor-prompt pane (item 5 above) contains only the **active** actor's
  own request, verbatim, and nothing else -- this is enforced by a test
  that checks every rendered call id in that pane belongs to the active
  actor;
* an actor's own private context is banded `PRIVATE -- <name> ONLY` and
  the world's shared context is banded `SHARED -- every actor in this
  world`, so the two can never be read as one block.

## Fail-loud behaviour

The viewer never invents a placeholder event and never silently omits a
broken record.

* **Missing file.** A required artifact that cannot be read is a visible
  error naming the path. An artifact that a given run kind genuinely does
  not produce is listed as an absence *with the reason*, not as a failure.
* **Malformed JSON.** A document that will not parse is an error naming the
  file and the parser message. A JSONL line that will not parse is kept in
  position as a red `malformed` timeline entry with its line number and the
  raw text, so the timeline is never quietly shortened.
* **Hash inconsistency.** Every published hash is recomputed in the
  browser and compared: each committed event's `sha256`, each step's
  `committed_stream_prefix_sha256`, each recorded call's
  `request_sha256` / `response_sha256`, the freeze manifest's entries for
  the decision problem, evidence manifest, evidence items, candidate set
  and model configuration, and every file in the compiler artifact
  directory plus its aggregate. A mismatch is reported with both values
  and the file. (Hashes are recomputed with a canonical JSON serialiser
  that reproduces Python's float formatting; `JSON.stringify` would write
  `0` where the harness hashed `0.0` and would accuse an intact artifact.)
* **Internal disagreement.** A step that names a committed event index the
  stream does not contain, a committed row no step claims, a call the step
  ledger references but the branch ledger does not hold, a call in the
  ledger no step surfaces, a metric whose citations differ between
  `branch_result.json` and `evaluator_ledger.json`, a candidate set that
  disagrees with the trace report, or candidate provenance that
  contradicts the run's declared candidate source -- each is a named,
  visible error.
* **Recorded absences.** Several fields legitimately carry
  `{"unavailable": "<reason>"}` -- notably `simulation_time` (the pinned
  sequential engine has no clock; steps are ordinal) and
  `full_engine_state_hash` (a whole-branch checkpoint is only taken at a
  requested boundary, so the run records the committed-stream prefix hash
  instead). The viewer prints the recorded reason in an amber
  `RECORDED AS UNAVAILABLE` block. It does not hide them and does not
  substitute a value.

Fetching an optional artifact that a run does not have produces a `404` in
the browser's network log. That is the probe working; each one appears in
the raw-artifact table as a documented absence.

## Layout

```
viewer/
  serve.py             read-only local server (GET/HEAD only)
  index.html           the page shell
  style.css
  app.js               run/branch selection, playback, deep links
  node_driver.js       headless driver -- runs the same assembly and the
                       same rendering under node, for the tests
  lib/
    catalog.js         which runs exist and which files each is made of
    assemble.js        the pure transform: artifacts -> ordered view model
    render.js          view model -> the HTML the browser injects
    canonical_json.js  Python-compatible canonical JSON for hashing
    io_browser.js      fetch + WebCrypto
    io_node.js         filesystem + node:crypto
```

## Tests

```bash
/home/user/engine-env/bin/python -m pytest tests/test_replay_viewer.py -q
```

`tests/test_replay_viewer.py` drives this viewer's own JavaScript through
`node_driver.js` and asserts that the ordered committed events, the
ordered model call ids and the metric citations **extracted from the
rendered HTML** are exactly those in the frozen files, for one branch of
every scenario in both phases plus a settling arm. It also drives a real
headless Chromium against `serve.py` and reads the committed-event order
back out of the live DOM. The fail-loud paths are tested against copies in
a temporary directory; the real artifacts are never touched.
