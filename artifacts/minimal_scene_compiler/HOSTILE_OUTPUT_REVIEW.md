# Agent D — hostile output and schema review (status and findings)

**Process disclosure:** the independent Claude tester agent was terminated
mid-run by the account's monthly Claude spend limit, after completing 93
recorded probes against the schema and validator layers
(probe1: 52 schema attacks, probe2: 41 validator attacks) and before its
adapter probe (whose file contains a literal null byte from its own
payloads and cannot be executed).  The lead agent re-ran both surviving
probe suites, fixed every flagged defect, re-verified against the same
probes, and completed the adapter attacks with an equivalent fresh probe.

## Findings from the independent probes (all fixed and re-verified)

- **V30–V32 (MEDIUM→fixed):** `validate_scene` raised
  (`TypeError`/`ValueError`) on malformed or naive caller start/cutoff
  strings instead of returning errors.  Now returns
  `invalid start/cutoff: ...` validation errors.  (Through the public
  `compile_scene` these were already caught as `INTERNAL_ERROR` — never an
  uncaught crash — but the validator is a public deterministic layer and
  now degrades properly.)
- **V14 / V36 (HIGH→fixed):** actor names and resolutions consisting only
  of zero-width characters (U+200B etc., Unicode category Cf) passed the
  non-empty checks — an invisible actor and an invisible resolution.
  Invisibles are now stripped during normalization; empty-after-cleanup
  names, resolutions, shared context, and event descriptions are
  validation errors, and invisible infixes no longer make identical names
  distinct.
- **V22 (MEDIUM→fixed):** the same instant written in different UTC
  offsets (`09:00-05:00` vs `14:00Z`) did not collapse as an exact
  duplicate event.  Event identity now uses the UTC-normalized instant,
  and stored event times are UTC-normalized.
- **V34 (LOW→fixed):** event descriptions were whitespace-normalized but
  the resolution was not, so the resolution-as-occurred-event check missed
  doubled-space variants.  The resolution is now normalized identically
  before comparison.
- **V40b (accepted precondition):** `validate_scene({})` raises KeyError —
  documented: the pipeline shape-gates manifests before validation.

Post-fix probe re-runs: probe1/probe2 show no remaining unexpected
behaviors (3 non-OK entries are documented preconditions of the class
V40b).

## Adapter attacks (fresh probe, lead-run, all PASS)

- template metacharacters in event descriptions
  (`{actor} {0} %s {{x}} $(cmd) `` `t` `` `{params.z}`) flow through the
  information lifecycle **literally** — no substitution, no crash;
- names that slugify identically (`A-B` vs `A B`) instantiate as TWO
  actors with suffixed IDs — never silently merged;
- scale: 500 actors × 200 events × 1 MB shared context validates and
  instantiates in bounded time (< 30 s) without error;
- a `visible_to` entry repeated 50× collapses to a single delivery.

Regressions for every fixed finding are in
`tests/test_scene_compiler.py::test_hostile_invisibles_offsets_and_bad_frames`
(suite: 160 passing).  No CRITICAL findings are open.
