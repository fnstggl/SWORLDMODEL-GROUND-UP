# Evidence-retrieval port audit — SWORLDMODEL-CORE → SWORLDMODEL-GROUND-UP

**Status: audit only. No production code was written, modified, or ported. No branch was
created. No pull request was opened.** The single artifact of this work is this file.

| | |
|---|---|
| Donor (read-only) | `SWORLDMODEL-CORE` @ `52eb067`, branch `claude/evidence-retrieval-audit-s2gnrh`, working tree clean |
| Target (product) | `SWORLDMODEL-GROUND-UP` @ `226fe05` (= `main`, PR #4 merged), branch `claude/evidence-retrieval-audit-s2gnrh`, working tree clean |
| Target reference version | PR #5, head `f9bdbb0` (`claude/sworldmodel-runtime-completion`) |
| Live audit | 2026-07-29 · 5 runs · 1 453 s wall · 101 provider-model calls · 261 k tokens |
| Credentials present | `DEEPSEEK_API_KEY`, `JINA_API_KEY`, `SERPER_API_KEY` (no `SERPAPI_API_KEY`) |

**PR #5 does not touch the compiler.** `git diff main origin/claude/sworldmodel-runtime-completion`
changes 19 files, all under `sworldmodel/semantic_runtime/`, `evaluation/`, and `tests/`.
Every file under `compiler/` is byte-identical between the checked-out tree and PR #5, so
the input boundary this audit targets is the same in both.

---

## 1. The exact current CORE retrieval call graph

Traced from entry points, not from filenames or docs. Only **two** call sites in the
whole system reach the retrieval backend.

```
sworldmodel.cli:main
 └─ cli.cmd_forecast                                   cli.py:225
     └─ config.ForecastConfig.live(...)                config.py:69-116
     │    └─ DeepSeekGateway + UrllibTransport + LiveResearchBackend  (one shared transport)
     └─ api.run_forecast                               api.py:880
         ├─ config.research_backend.research(q, as_of, horizon)      api.py:892   ← ENTRY 1
         └─ api._repair → backend.augment_targeted(...)              api.py:285   ← ENTRY 2
                                                                     (coverage/repair only)
```

### `LiveResearchBackend.research()` — `live_research.py:331-348`

```
research(question, as_of, horizon)
 │
 ├─ retrieval_mode(as_of)                             live_research.py:319-330
 │    └─ RetrievalMode.decide(as_of, self._now)       source_fetch.py:186-192
 │         └─ requires_archived_copy(as_of, now)      source_fetch.py:150-163   [as_of < now]
 │
 ├─ research_planner.plan_research(gateway, …)        research_planner.py:98-151   ← LLM CALL 1
 │    12-field plan: process_summary, resolution_event, deadline, authoritative_sources,
 │    decision_makers, rules, prior_actions, scheduled_events, causal_drivers,
 │    required_facts, initial_queries, official_domains
 │
 ├─ _run_rounds(...)                                  live_research.py:449-521
 │   │
 │   ├─ _build_queues(plan, …)                        live_research.py:523-559
 │   │    targeted ⟵ caller · authoritative ⟵ site:<official domains> + authoritative_sources
 │   │    general  ⟵ initial_queries + decision_makers
 │   │
 │   └─ WHILE queues non-empty AND rounds < 3 AND not _time_up:
 │       ├─ _cumulative_room()                        live_research.py:304-315
 │       ├─ _collect_candidates(session, …)           live_research.py:692-736
 │       │   ├─ _next_queries(session)                live_research.py:561-608
 │       │   │     authoritative/general share the cap; reserve = (max_queries+1)//2
 │       │   ├─ _news_candidates(q, …)                live_research.py:738-786
 │       │   │   ├─ rss.google_news_rss_url           rss.py:118-121
 │       │   │   ├─ transport.get → rss.parse_rss     rss.py:133-163
 │       │   │   ├─ filter items: published is None OR published <= as_of
 │       │   │   ├─ take first budget.max_pages_per_query (=4) items
 │       │   │   └─ _resolve_item(item)               live_research.py:788-812
 │       │   │       ├─ rss.resolve_item_url          rss.py:171-186  [legacy; measured 0/100]
 │       │   │       ├─ gnews_decode.GoogleNewsDecoder.decode   gnews_decode.py:99-151
 │       │   │       │     signature GET → batchexecute POST → publisher URL
 │       │   │       │     typed failures: challenge|throttled|protocol_change|network
 │       │   │       └─ providers.jina_title_search("HEADLINE" "PUBLISHER")  providers.py:191-227
 │       │   ├─ search.duckduckgo_search              search.py:38-64   [optional extra]
 │       │   └─ providers.serper_search               providers.py:252-282
 │       │         ONLY when this round's free channels produced zero URLs
 │       │
 │       ├─ [round 1 only] _official_feed_candidates  live_research.py:625-690
 │       │   ├─ _feed_urls(domain)                    live_research.py:610-623
 │       │   │   ├─ rss.site_roots + transport.get + rss.discover_feed_links  rss.py:71-106
 │       │   │   └─ rss.feed_urls_for (15 conventional paths)  rss.py:46-63, 109-115
 │       │   └─ rank items by distinctive-term overlap with the question
 │       │
 │       ├─ _policy_filtered(urls)                    live_research.py:814-828
 │       │     http.check_url_shape                   http.py:159-233
 │       │
 │       ├─ _fetch_all(urls, …)                       live_research.py:830-906
 │       │   ├─ _normalized_dedup                     live_research.py:1386-1410
 │       │   ├─ runcache.SourceCache.load             runcache.py:111-142
 │       │   ├─ ThreadPoolExecutor(6) → source_fetch.fetch_source   source_fetch.py:234-320
 │       │   │     PASTCAST: source_fetch.archived_capture (Wayback CDX)  source_fetch.py:333-376
 │       │   │              → wayback_snapshot_url(…id_/…)             source_fetch.py:322-331
 │       │   │              → NO capture ≤ cutoff ⇒ _refused, never fetched live
 │       │   │     NOWCAST: direct GET
 │       │   │     pdf_text.looks_like_pdf / pdf_to_text / pdf_metadata_date
 │       │   │     source_fetch.extract_text / extract_title / extract_published
 │       │   └─ _reader_fallback                      live_research.py:908-930
 │       │         providers.jina_reader (r.jina.ai)  providers.py:152-188
 │       │         GUARD: `if not src.ok and not pastcast` — NOWCAST ONLY
 │       │
 │       ├─ _extract_all(question, as_of, sources, …) live_research.py:932-1034
 │       │   ├─ gate: s.evidence_time() > as_of  ⇒ reject
 │       │   ├─ gate: s.content_hash in seen_hashes ⇒ reject (duplicate document)
 │       │   ├─ ThreadPoolExecutor(4) → source_extract.extract_claims   source_extract.py:79-165
 │       │   │   ├─ runcache.ExtractionCache.load                       runcache.py:184-199
 │       │   │   ├─ _build_prompt (untrusted-document envelope)         source_extract.py:173-211
 │       │   │   ├─ gateway.generate(expected_keys=("claims",))         ← LLM CALL per source
 │       │   │   │     deepseek_gateway retry / jsonsalvage.salvage_json
 │       │   │   └─ verify_claim(...) per claim                         source_extract.py:232-321
 │       │   └─ _add_claim → evidence.EvidenceStore.add                 live_research.py:1036-1085
 │       │
 │       ├─ _detect_contradictions                    live_research.py:1087-1135
 │       │   └─ _is_decisive_conflict → LLM           live_research.py:1139-1217
 │       │       └─ _can_reconcile     → LLM          live_research.py:1219-1256
 │       ├─ _record_fact_retrieval                    live_research.py:1258-1285  (lexical only)
 │       └─ research_planner.followup_queries → LLM   research_planner.py:154-188
 │
 └─ _compile(...)                                     live_research.py:1289-1370
      └─ api.compile_for_mode(...)   ← CORE's WORLD COMPILER. NOT IN SCOPE FOR THE PORT.
```

**The retrieval layer ends at `_compile`.** Everything above it is the candidate for
porting; `_compile` is the boundary to CORE's forecasting stack and must not cross into
GROUND-UP.

**LLM calls per question:** 1 plan + 1 per source extracted + 1 per follow-up round +
(0–2 per contradiction candidate pair). Measured live: **16–30 calls per question.**

### Import closure — what porting would drag in

Built mechanically over CORE's `src/sworldmodel` (following deferred, in-function imports
too). The uncut closure of the retrieval modules is **49 modules, 24 of them forbidden**
for the target (`world_compiler`, `semantic_plan`, `semantic_lowering`, `semantic_compile`,
`engine`, `coverage`, `repair`, `grounding`, `reality`, `uncertainty`, `worldspec`,
`structures`, `outcomes`, `diagnosis`, `world_review`, `trajectory_audit`, `effects`,
`expressions`, `executor`, `actors`, `memory`, `novel`, `schedule`, `api`).

**Three import edges carry all of it:**

| Edge | Kind | What it reaches |
|---|---|---|
| `live_research.py:61` `from .research import ResearchBundle, assemble_bundle` | top-level | `world_compiler`, `worldspec`, `coverage`, `grounding`, `reality`, `uncertainty`, `expressions`, `actors`, `memory`, `schedule` |
| `live_research.py:1307` `from .api import compile_for_mode` | **deferred, inside `_compile`** — a naive import smoke-test will not surface it | `api`, `engine`, `repair`, `outcomes`, `structures`, `diagnosis`, `world_review`, `trajectory_audit`, `semantic_compile` → `semantic_plan`, `semantic_lowering`, `effects`, `executor`, `novel` |
| `models.py:23` `from .worldspec import TerminalExpression` | top-level | `worldspec` — and this is the *only* contamination reachable from `evidence`, `source_extract`, `models` |

After those three cuts the closure is **19 modules, 6 254 LOC, zero forbidden modules,
and zero third-party imports** (stdlib-only, compatible with GROUND-UP's
`dependencies = []` and `requires-python = ">=3.11"`).

Cutting edge 2 removes `research()`'s tail — `research()` *ends* with
`return self._compile(...)`. A port must call `_run_rounds` directly and build its own
package. That is a fork of the entry point, not a copy.

---

## 2. What currently works

Every row is either traced end-to-end in code or measured in §4.

| # | Component | Evidence it works |
|---|---|---|
| W1 | **Google News batchexecute decoder** (`gnews_decode.py`) | **146/146 resolutions succeeded across five live runs; zero failures of any kind** (135/135 in the four primary runs). The single most reliable component measured. It replaces `rss.resolve_item_url`, which the repo itself records as recovering 0 of 100 items (`rss.py:44`, `docs/KNOWN_LIMITATIONS.md`). |
| W2 | **Google News RSS as a query surface** | 47 feeds fetched, 1 685 items returned, all parsed, never blocked, sub-second. |
| W3 | **Direct publisher fetch + `extract_text`** | **89/89 accepted sources came through the direct path.** Chrome-stripping with the `_MIN_KEPT_SHARE` fallback (`source_fetch.py:412-450`) produced usable text from `.gov` HTML, SEC EDGAR, PDFs, and modern JS-heavy news sites. |
| W4 | **PDF text extraction** (`pdf_text.py`, 135 lines, stdlib-only) | `CRPT-119srpt127.pdf`, `IN12704.1.pdf`, `BILLS-119s4784rs.pdf` all yielded extractable text and dated correctly. |
| W5 | **The untrusted-document envelope** (`source_extract.py:173-224`) | Per-call marker derived from `question ⊕ url ⊕ content_hash`; fence/quote runs collapsed; the envelope word itself defanged. A page author cannot predict the closing token. Sound by construction. |
| W6 | **Verbatim-excerpt anchoring** (`source_extract.py:265-266`) | Works exactly as designed — no stored claim in any run lacked a real sentence in the fetched bytes. It is also the largest single source of *accidental* loss (§5). |
| W7 | **Provider circuit breaker** (`providers.ProviderHealth`) | DuckDuckGo tripped correctly after 3 consecutive blocks in 3 of 5 runs, and each run continued on the remaining channels. |
| W8 | **Fetch policy / SSRF guard** (`http.py:159-233`) | Scheme allowlist, per-hop re-validation after redirect, size cap enforced *during* read and decompression, content-type allowlist. Research URLs come off third-party HTML; this is not optional. |
| W9 | **`IncompleteRead` / protocol-error containment** (`http.py:355-368`) | A truncated chunked body becomes a document-level `HttpError`. The code records that before this, one `IncompleteRead` destroyed a twenty-minute run. |
| W10 | **Per-source failure isolation in extraction** (`live_research.py:993-1008`) | A `GatewayError` on one document is recorded as "extraction failed" for that source and the run continues. The docstring's distinction — "we could not read a source" vs "we do not know what someone decided" — is exactly right. |
| W11 | **Mechanical cutoff view** (`evidence.py:103-104, 186-217`) | The cutoff is an `EvidenceView` bound to `as_of`, not prompt wording. `get()` on a post-cutoff claim raises. |
| W12 | **Cutoff correctness in both directions** | No over-admission could be constructed. `RetrievalMode` is decided once against a pinned `_now`; `archived_capture` rejects `stamp > as_of`; `evidence_time()` is clamped at `observed_at`; the `SourceCache` regime key separates `live` from `archive:<as_of>`, so a cache hit cannot serve post-cutoff bytes to a pastcast. |
| W13 | **Deterministic, content-addressed IDs** (`ids.py`, 58 lines) | No randomness, no wall clock. |
| W14 | **JSON truncation salvage** (`jsonsalvage.py`, 97 lines) | Closes open brackets/strings, trims the trailing partial member, invents nothing, and only runs after the retry budget is spent. |
| W15 | **Missing publisher never kills a source** | `_publisher()` derives from the hostname (`source_fetch.py:543-548`). Measured: **0 sources with a missing publisher out of 89.** |
| W16 | **Missing publication date never kills a source** | `evidence_time()` falls back to `observed_at`. Measured: **22 of 89 accepted sources had `published_at = None` and were used normally**, in both modes. The requirement "missing metadata becomes UNKNOWN, not a crash" is **already satisfied at the source level.** |
| W17 | **The target's information boundary already holds** | At PR #5, `sworldmodel/semantic_runtime/adapter.py:65-66` writes `shared_context` as a **world fact only**; `views.py:15-28` deliberately excludes it from actor views, with a docstring recording six live runs where it leaked. `tests/test_semantic_runtime.py:1932-1947` enforces it. |

---

## 3. What currently fails

Ordered by blast radius. Every finding is reproduced, not inferred.

### F1 — CRITICAL: `as_of = now` silently becomes a **pastcast**, and archive-only retrieval then destroys most candidates

`requires_archived_copy` is `as_of < now` with **no tolerance window**
(`source_fetch.py:163`), and `self._now` is set on the first `retrieval_mode()` call
(`live_research.py:326-328`) — always *after* the caller computed `as_of`.

```
PASTCAST   lag=+0.140000s   as_of == datetime.now() computed 0.14 s earlier
NOWCAST    lag=+0.000000s   as_of == exactly the run-start instant
NOWCAST    lag=-0.000001s   as_of == run start + 1 microsecond
```

**All four primary audit runs flipped to pastcast on a lag of 0.036 s – 0.639 s.**
Measured cost: **65 of 121 rejections (54%) were "no archived capture at or before the
cutoff"** — the single largest loss category in the audit.

The A/B control settles it. The identical question, re-run with the cutoff 10 minutes
ahead of the run start (the *only* change):

| | pastcast (`as_of = now`) | nowcast control |
|---|---|---|
| archive rejections | **18** | **0** |
| official-feed items found | 0 | **30** |
| Jina Reader recoveries attempted | 0 | **3** |
| primary sources reached | CRS reports, GovTrack, one Senate vote page | `armed-services.senate.gov/…/passage_fy…`, `congress.gov/119/bills/s4784/BILLS-119s4784rs.pdf`, `whitehouse.gov/…/SAP-HR88…` |

The `RetrievalMode` docstring (`source_fetch.py:166-180`) says pinning the instant fixes
the drift problem. It fixes *mid-run* drift. It does not fix a caller passing "now",
which is what "forecast from today" means.

### F2 — CRITICAL: the claim verifier destroys most of what the extractor found, and preferentially destroys the most decision-relevant claims

Across the four primary runs the model offered **98 claims**; the verifier refused **52
(53%)**. Re-running `verify_claim` offline against the cached documents and the cached raw
model output shows the refusals are overwhelmingly formatting artifacts (§5).

Three instances, each the highest-value claim available for its question:

```
REFUSED: the supporting span does not contain the date(s) the claim asserts: 2026-07-23
  document : web.archive.org/…/dailypress.senate.gov/thursday-july-23-2026/
  claim    : Majority Leader Thune withdrew the motion to proceed to S. 4784, the
             FY2027 NDAA, on July 23, 2026
  excerpt  : "2:50 p.m. Majority Leader Thune withdrew his motion to proceed to
              S. 4784, the FY2027 NDAA."

REFUSED: the supporting span does not contain the value(s) the claim asserts: 2026
  document : cnbc.com/2026/07/23/interest-rate-hike-iran-european-central-bank.html
  claim    : Traders anticipate a rate hike at the ECB's September meeting  (2026)
  excerpt  : "But traders are already anticipating a rate hike in September, as ECB
              president Christine Lagarde warned renewed Middle East hostilities…"

REFUSED: the supporting span does not contain the date(s) the claim asserts: 2026-03-18
  document : nbcnews.com/business/media/disney-names-parks-chief-josh-damaro-ceo-…
  claim    : Disney named Josh D'Amaro as successor to Bob Iger, effective March 18, 2026
  excerpt  : "The Walt Disney Co. announced Tuesday that theme parks chief Josh D'Amaro
              will succeed Bob Iger… on March 18."
```

In every case the excerpt is verbatim and exact, and the year or date the claim supplies
is one the code **already holds** in `source.published_at`. `verify_claim` never consults
it. The claim is punished for being *more precise than the sentence it quotes*.

### F3 — HIGH: the official institutional feed channel produced nothing for 3 of 4 questions

`_official_feed_candidates` is described as the primary rung (`live_research.py:632-640`;
`docs/RETRIEVAL_ARCHITECTURE.md` §1). Measured:

| question | official domains planned | feed items found |
|---|---|---|
| legislative (pastcast) | `senate.gov`, `congress.gov`, `armed-services.senate.gov` | **0** |
| policy | `nyc.gov`, `nypd.gov`, `nycouncil.nyc`, `dot.nyc.gov` | **0** |
| official (ECB) | `ecb.europa.eu` | **0** |
| person | Disney corporate/investor domains | 100 |
| legislative (nowcast control) | + `whitehouse.gov` | 30 |

Where it did fire on the person run, ranking by question-term overlap put three
irrelevant press releases first — "Marvel Studios Comic-Con", "D23 sweepstakes",
"Disney Worldbuilders teaser" — spending three fetch-and-extract slots (three LLM calls)
before reaching anything about the question.

The ECB run is the sharpest case: the question was chosen *because* official evidence is
essential, `ecb.europa.eu` was correctly planned, the feed channel returned nothing —
and 11 of 17 accepted sources were nonetheless `ecb.europa.eu` pages, reached by ordinary
Google News and DuckDuckGo discovery plus direct fetch. **The generic channel found the
official source that the dedicated official channel missed.**

### F4 — HIGH: the two-LLM-call contradiction subsystem is nearly inert on real data

~190 lines and up to 2 LLM calls per candidate pair, with a run-ending consequence
(`live_research.py:1210-1211`: *"A decisive verdict blocks the whole run and cannot be
cleared by recompilation"*).

**Measured: 2 contradiction checks across five runs, 1 LLM call, 0 contradictions
recorded.** Pairing requires two claims with an identical `_topic(proposition)` prefix
**and** an identical sorted entity tuple **and** different `normalized_value` strings —
three LLM-authored strings agreeing exactly. The person run contains a genuine tension
(`Disney expects to announce its next CEO in early 2026` alongside `Josh D'Amaro named
CEO effective March 18, 2026`) that was never examined.

The subsystem carries the *risk* of an unrecoverable false block without delivering the
benefit.

### F5 — HIGH: three single points of failure still destroy a whole run and lose every artifact

All three reproduced:

**(a) A timezone-naive `--as-of` crashes on the first RSS response.** `cli.py:227` does
`datetime.fromisoformat(args.as_of)` with no normalization; `live_research.py:760`
compares that against `RssItem.published`, which `rss.py:150` produces via
`parsedate_to_datetime` — aware for every Google News item.

```
item.published: 2026-07-20 10:00:00+00:00 | naive as_of: 2026-07-01 00:00:00
TypeError: can't compare offset-naive and offset-aware datetimes
```

`_news_candidates` catches only `HttpError`. The `TypeError` escapes to `api.py:917`,
`partial_live_trace` is never set (it is assigned only inside `_compile`), and the run is
filed as `ForecastRefused(stage="research")` with **no trace and no evidence store**.
Every test constant and every documented example carries an offset, so the path is
untested.

**(b) One malformed `Content-Type` charset destroys the run and is misfiled as a
*simulation* failure.** `http.py:405-412` does `raw.decode(charset, errors="replace")`;
`errors="replace"` guards bad bytes, not a bad codec name.

```
'text/html; charset=none'               -> LookupError: unknown encoding: none
'text/html; charset=utf-8charset=utf-8' -> LookupError: unknown encoding: utf-8charset=utf-8
http.UrllibTransport._request handlers:
  except UrlRejected
  except (urllib.error.URLError, TimeoutError, OSError)
  except (http.client.HTTPException, zlib.error)
```

`LookupError` is none of them. It surfaces from `pool.map` in `_fetch_all`, is not caught
by `run_forecast` (which lists `TypeError, ValueError, KeyError`), and reaches
`cli.py:311` as `failure_stage="simulation"`, exit 4, no research artifacts. This is the
exact shape of the bug already fixed one line away for `IncompleteRead`.

**(c) `followup_queries` is the one unguarded gateway call inside the research loop.**
`live_research.py:509-517`. Extraction is wrapped per source; `_is_decisive_conflict` and
`_can_reconcile` both catch `GatewayError`. This one does not. A transient DeepSeek
failure after round 1 discards every claim and source gathered so far. It also fires on
the final round, where its output can never be used.

### F6 — HIGH: Wayback is an unmonitored, un-retried, un-scored single point of failure, and its outages are written into the record as facts about the world

`archived_capture` (`source_fetch.py:333-375`) returns `None` identically for: no capture
exists; `HttpError`; non-200; `JSONDecodeError`; short payload. `fetch_source:255-260`
then emits one message for all five — *"no archived capture at or before the cutoff"*.
There is no `trace.bump("wayback")`, no `ProviderHealth` entry, and no retry, while
`_fetch_all` drives the CDX endpoint from 6 concurrent threads. A direct probe from this
container timed out on `web.archive.org/cdx` at 20 s.

The consequence is that CORE's own headline pastcast evidence — *"40 candidate URLs, none
with an archived capture at or before the cutoff"* (`api.py:360-364`) — **cannot currently
be distinguished from a rate limit.**

### F7 — MEDIUM: two silent-loss paths where usable sources vanish with no trace entry

* **Fetch-cap tail** (`live_research.py:840-845`): candidates beyond `max_fetches` are
  sliced off. They are not added to `seen_urls`, not appended to `trace.rejected`, and not
  carried to the next round. In round 1 the official-feed channel is *prepended* and can
  supply up to 24 URLs on its own — more than `max_fetches = 20` — so an entire round's
  news yield can be discarded. DuckDuckGo results are never recorded at all
  (`live_research.py:709` writes only `{query, channel}`), so those vanish without trace.
* **Extract-budget tail** (`live_research.py:967-976`): `chosen = fresh[:budget_left]`;
  the remainder gets no `trace.rejected` entry, but its URLs are already in
  `session.seen_urls`, so no later round or repair pass re-fetches them. An auditor sees
  *N* sources fetched, *M < N* extraction calls, and no explanation.

Both are the odd ones out in a subsystem that is otherwise scrupulous about recording
every refusal.

### F8 — MEDIUM: `_epi` fails toward the *strongest* class; `_can_reconcile` fails toward *blocking*

* `source_extract.py:531-533`: any value outside `{observation, inference, hypothesis}`
  becomes `"observation"`. Five lines below, `_auth` correctly clamps an unparseable
  authority hint to the **lowest** level, with a docstring explaining why. The two
  defaults point in opposite directions in the same file, and `observation` is the class
  that admits a claim to contradiction adjudication.
* `live_research.py:1254`: `return resp.data.get("reconcilable") is True`. A model
  replying `"reconcilable": "true"` (string) yields `False`, so `_is_decisive_conflict`
  returns `not False = True` and the run-ending contradiction is recorded. The paired
  check one line up (`decisive is not True`) fails *open*.

### F9 — MEDIUM: `_strs` turns a wrong-typed plan field into silent total research failure

`deepseek_gateway._schema_ok` is presence-only (`:408-409`: `all(k in data for k in
expected_keys)`). If the model returns `"initial_queries": "senate NDAA status"` — a bare
string, key present — the gateway accepts, `_strs` (`research_planner.py:191-194`) returns
`()`, `_build_queues` yields three empty deques, the `while` at `live_research.py:468`
never executes, and `research()` returns zero claims **with no error anywhere.**

### F10 — MEDIUM: three of six discovery/recovery rungs were exercised zero times

* `_reader_fallback` is guarded by `if not src.ok and not pastcast`
  (`live_research.py:872-876`). Since F1 makes nearly every run a pastcast, Jina Reader
  fired **0 times in the four primary runs** despite 20+ direct-fetch failures — and
  **3 times** the moment the nowcast control removed the mode flip.
* `serper_search` fires only when a round's free channels produced **zero** URLs
  (`live_research.py:726`), and that gate is per *round*, not per query — one DuckDuckGo
  hit on one general query suppresses the paid fallback for four authoritative queries in
  the same round that returned nothing. **0 Serper calls in 5 runs.**
* `jina_title_search` fires only when the decoder fails. The decoder never failed.
  **0 Jina Search calls in 5 runs.**

They are not proven. They are untested in this environment.

### F11 — MEDIUM: rejected claims are recorded without their excerpt, so they cannot be diagnosed

`live_research.py:1024-1032` records `{url, reason, proposition}` — not the
`supporting_excerpt`, which is the thing that failed. Diagnosing F2 required
reconstructing raw model output from `runcache.ExtractionCache` and re-running
`verify_claim` offline. In a production run without that cache the evidence is gone.

### F12 — MEDIUM: `max_pages_per_query = 4` discards ~92% of RSS items before any relevance filter

`_news_candidates` slices `within[:4]` (`live_research.py:759`) **by feed order**.
Measured: **1 685 RSS items retrieved across five runs, 146 URLs resolved.** Which four
survive is Google's ordering, not the question's. Meanwhile
`trace.rss_requests` reports `within_cutoff` (often 50–100) beside
`resolved_to_publisher` (4), so the trace reads as a 90-item resolution failure when only
4 were attempted.

### F13 — Documentation overstates the code

* `docs/RETRIEVAL_ARCHITECTURE.md`: *"`providers.ProviderHealth` scores every provider
  call."* It does not. Google News RSS (`live_research.py:750-756`) and Wayback
  (`source_fetch.py:333-375`) are never scored and never checked for usability — two of
  the six rungs, including the one listed first for pastcasts, sit outside the breaker.
* Same doc: *"rest a provider for the rest of the run"* is accurate on mechanism, silent
  on the two consequences that matter — **empties count toward the trip**
  (`providers.py:82-90`), and there is **no recovery path at all**.
* Same doc, §1 ordering: official feeds are prepended to the *fetch* queue, but
  `_collect_candidates` — including the paid Serper fallback — has already run to
  completion first.
* `docs/EVIDENCE_AND_CUTOFF.md` §Contradictions describes *"explicit corpus-declared pairs
  plus exact `claim_key` matches… fuzzy topic/prefix heuristics are avoided"*. The live
  path groups by `_topic(proposition)|entities` — a topic-prefix heuristic — and
  adjudicates with two LLM calls. There is no `claim_key` and no corpus in the live path.
* `docs/KNOWN_LIMITATIONS.md` cites `rss_requests.unresolvable_redirects`; that key does
  not exist anywhere in `src/`.
* `docs/FAILURE_STAGE_CLASSIFICATION.md`: *"SIGKILL mid-run loses nothing (research
  checkpoint verified)"*. SIGKILL cannot be trapped; `cli.py:57-62` handles `SIGTERM` and
  `SIGINT` only, and `_checkpoint_research` runs *after* `research()` returns
  (`api.py:924`), so a stop during research loses the entire store and trace.
* `live_research.py:479` comment *"Once, at the start"*: `rounds` is a local counter reset
  at `:467`, so every `augment_targeted` pass re-runs the full official-feed probe — up to
  13 times per question under `_REPAIR_CEILING = 12`.

### F14 — On the target side: the evidence path has never once been executed

* **0 of 183** recorded `evidence_mode` values in GROUND-UP's artifacts (across 173
  `compiler_metrics.json` files) say `"evidence_package"`. 182 say
  `model_memory_unverified`; one legacy artifact says `evidence_docs`.
* `run_simulation.py:64` calls `compile_scene(question, start, cutoff, context=…)` —
  **no `evidence=`**, and there is no `--evidence` flag. `run_scene_acceptance.py` is the
  same. `compile_question.py:80-82` is the only caller that passes evidence, and it stops
  at the compiler and never reaches the runtime.
* There is **no test anywhere** exercising `evidence_mode == "evidence_package"`.

The seam this port targets is a stub.

---

## 4. Measured results from the live audit questions

Method: the exact production functions `research_planner.plan_research` and
`LiveResearchBackend._run_rounds`, stopped at the evidence package. `_compile` was never
called — no world was compiled and nothing was forecast. **No production code was
modified.** The harness lives outside both repositories. Default `ResearchBudget`, cold
caches, nowcast intent (`as_of = now`, `horizon = now + 120 d`).

### Per-question

| | 1. legislative | 2. policy | 3. named person | 4. official | control: 1 as true nowcast |
|---|---|---|---|---|---|
| question | Senate passes FY2027 NDAA before end of 2026? | Which policy most reduces NYC package theft? | Disney names Iger's successor before end of 2026? | ECB cuts deposit rate at next meeting? | same as 1, cutoff +10 min |
| **retrieval mode** | pastcast (lag +0.14 s) | pastcast (+0.04 s) | pastcast (+0.64 s) | pastcast (+0.39 s) | **nowcast (−599 s)** |
| wall time | 307 s | 268 s | 287 s | 270 s | 319 s |
| rounds / stop reason | 2 / budget | 3 / query budget | 2 / extract budget | 2 / budget | 1 / budget |
| LLM calls (plan/extract/other) | 16 (1/14/1) | 18 (1/15/2) | 30 (1/28/1) | 20 (1/17/2) | 17 (1/15/1) |
| tokens | 46 276 | 47 767 | 80 591 | 48 390 | 37 810 |
| **generated queries** | 10 (6 auth, 4 gen) | 12 (6 auth, 6 gen) | 10 | 10 | 5 |
| **Google News items found** | 161 | 363 | 456 | 595 | 110 |
| **publisher URLs resolved** | 24 | 33 | 38 | 40 | 11 |
| — via decoder / via Jina title search | **24 / 0** | **33 / 0** | **38 / 0** | **40 / 0** | **11 / 0** |
| official-feed items | 0 | 0 | 100 | 0 | 30 |
| DuckDuckGo calls / failures / tripped | 8 / 4 / **yes** | 3 / 3 / **yes** | 5 / 3 / **yes** | 10 / 1 / no | 5 / 3 / no |
| **Serper calls** | 0 | 0 | 0 | 0 | 0 |
| **Jina Reader calls** | 0 | 0 | 0 | 0 | **3** |
| **Jina Search calls** | 0 | 0 | 0 | 0 | 0 |
| URLs attempted (after dedup) | 33 | 33 | 37 | 40 | 20 |
| **direct fetch: ok / failed** | 14 / 19 | 15 / 18 | 28 / 9 | 17 / 23 | 15 / 5 |
| duplicate URLs/docs removed | 0 recorded | 0 recorded | 0 recorded | 0 recorded | 0 recorded |
| sources missing publisher | **0** | **0** | **0** | **0** | **0** |
| sources missing pub date | 5 | 3 | 7 | 3 | 4 |
| extraction calls | 14 | 15 | 28 | 17 | 15 |
| **claims offered by model** | 16 | 25 | 40 | 17 | 10 |
| **claims stored** | **5** | **14** | **19** | **8** | **2** |
| **claims refused** | **11 (69%)** | **11 (44%)** | **21 (52%)** | **9 (53%)** | **8 (80%)** |
| contradiction checks / recorded | 0 / 0 | 0 / 0 | 0 / 0 | 2 / 0 | 0 / 0 |

### Rejections by exact reason (four primary runs, 121 total)

| reason | count | share |
|---|---|---|
| `no archived capture at or before the cutoff` | **65** | 54% |
| `claim not verified: supporting excerpt does not appear verbatim` | 18 | 15% |
| `claim not verified: the supporting span does not contain the value(s)` | 15 | 12% |
| `claim not verified: the supporting span does not contain the date(s)` | 13 | 11% |
| `claim not verified: document never mentions: <word>` | 4 | 3% |
| `unreachable/empty` | 4 | 3% |
| `claim not verified: the supporting span does not mention the claim's subject` | 2 | 2% |

### Aggregate

```
4 questions · 1 133 s wall · 84 LLM calls · 223 k tokens · 42 logical queries
1 575 RSS items → 135 publisher URLs (135 decoded, 0 via title search)
143 URLs attempted → 74 documents read → 98 claims offered → 46 stored (53% refused)
provider requests: google_news_rss 42 · google_news_decoder 135 · duckduckgo 26
                   jina_reader 0 · jina_search 0 · serper 0
```

### Is the final evidence actually relevant and sufficient?

Not merely "did the code complete" — it completed on all five runs.

| question | verdict | reasoning |
|---|---|---|
| **1. legislative** | **INSUFFICIENT** | 5 claims. Two are near-contentless (`value='None'`), one is a hypothesis. The three facts that actually answer it — cloture on the motion to proceed **rejected 50–46 on 14 July**, the motion **withdrawn 23 July**, the bill **reported by committee 15 June** — were all extracted by the model and all **refused by the verifier**. The stored evidence does not tell you where the bill stands. |
| **2. policy** | **PARTIALLY SUFFICIENT** | 14 claims. Genuinely useful: the LockerNYC pilot expansion, the Manhattan Institute finding that increased enforcement did *not* reduce shoplifting, package-theft rate differentials. Contaminated: five claims from `market.us` (a vendor market-research page) and one fetch of `britannica.com/procon/milk-debate`. **No New York City government source at all** — all four official domains returned nothing. |
| **3. named person** | **SUFFICIENT** | 19 claims, all on-topic, from `thewaltdisneycompany.com`, `sec.gov`, `d23.com`, `abcnews.com`, WSJ, CNBC, LA Times. The question is decisively answered (D'Amaro named 3 Feb 2026, effective 18 Mar 2026). The strongest result in the audit — and still 21 of 40 claims were refused. |
| **4. official** | **SUFFICIENT-AS-FRAMING, INSUFFICIENT-AS-ANSWER** | 8 claims, 5 from `ecb.europa.eu` itself: rates **raised** 25 bp on 11 June 2026, data-dependent meeting-by-meeting approach, no pre-commitment, inflation back to 2% in H2 2027, upside risks. But every market-expectation claim about the *next* meeting — *"traders are already anticipating a rate hike in September"*, *"traders expect a 0.25% hike in September"* — was refused because the year `2026` does not appear near the quote. The ECB's 23 July 2026 press release was fetched and yielded no stored claim. |
| **control** | **INSUFFICIENT, but for a different reason** | The nowcast reached far better sources (the SASC passage document, the engrossed bill PDF, the White House Statement of Administration Policy) and lost **zero** candidates to the archive. Then the verifier refused **8 of 10** claims, leaving 2. |

**The two defects are independent and multiplicative.** F1 decides *which documents you
get to read*; F2 decides *how much of what you read survives*. Fixing only one leaves the
other in full force — which the control run demonstrates directly: better sources, worse
yield.

### Did missing metadata cause unnecessary evidence loss?

**At the source level, no.** 0 of 89 accepted sources were lost to a missing publisher;
22 had no publication date and were used normally in both modes. CORE already degrades
source metadata to UNKNOWN correctly.

**At the claim level, yes, severely — but the mechanism is the opposite of the expected
one.** Claims are not lost because metadata is *missing*; they are lost because the model
**supplied** metadata (a resolved date, a year, a normalized value) that the document
expresses relatively or in words. Of the 28 date/value refusals, every one examined was a
claim correctly resolving "today", "on March 18", "at the end of this year", "its July
meeting" against `source.published_at` — a field the code holds and the verifier does not
read.

---

## 5. Every unnecessary formatting requirement found

Each row is classified **PROTECTION** (it stops invented evidence) or **ACCIDENT** (it
stops correctly-grounded evidence for a syntax reason), on the basis of what it actually
rejected in the live runs.

| # | Requirement | Where | Observed effect | Verdict |
|---|---|---|---|---|
| A1 | **Excerpt must appear verbatim after `_norm`** — which unifies quotes, dashes and whitespace runs but **does not** normalize punctuation-adjacent spacing | `source_extract.py:265-266`, `_norm` `:415-425` | 18 refusals. PDF text extraction inserts spaces: document `s. 4784 , 6/15/2026` vs excerpt `S. 4784, 6/15/2026`; `s.rept. 119 - 127` vs `S.Rept. 119-127`; `( du and wang, 2022 )` vs `(Du and Wang, 2022)`. One refusal matched **350 of 386 characters (91%)** contiguously. | **Rule = PROTECTION. Normalization = ACCIDENT.** Keep the rule; make `_norm` collapse spaces around punctuation. |
| A2 | **No ellipsis / span-join handling** | same | The model writes `"Amazon told me it does not have a policy… Jim Mayer, director of UPS media relations…"` joining two real sentences. 76% contiguous match, refused. | **ACCIDENT.** Split on `…`/`...` and require each fragment to appear. |
| A3 | **A table quoted in reading order must be contiguous in the source** | same | The **senate.gov roll-call vote page** — the most authoritative possible source for "will the Senate pass X". The model quoted `Vote Result: Cloture on the Motion to Proceed Rejected / YEAs 50 / NAYs 46 / Vote Date: July 14, 2026`. Every token is in the document; the HTML interleaves `Measure Number` and `Measure Title` between them. 51% contiguous. Refused. | **ACCIDENT** in effect. Structured pages are exactly where primary records live. |
| A4 | **Every date the claim asserts must appear within 320 chars of the quote** | `source_extract.py:281-291`, `_DATE_WINDOW_CHARS = 320` | 13 refusals. Every one examined was a *correct* resolution of a relative form the document used: "today" (page published that day), "on March 18" (year from the article), "at the end of this year", "as of July 22, 2026" (the page's own date). `source.published_at` holds the answer and is never consulted. | **ACCIDENT.** The verbatim-excerpt check already anchors the sentence. Delete; carry the source's publication date beside the claim instead. |
| A5 | **Every number the claim asserts must appear within ~150 chars of the quote** | `:299-306`, `_value_region` `:359-401` | 15 refusals. Overwhelmingly a **bare year**: `_numbers("…FY2027 would authorize $1.14 trillion")` yields `{1.14, 2027}`, and `_date_component_numbers` exempts only digits inside a *recognized full-date pattern*, so "FY2027", "its July 2025 meeting", "in September 2026" are unprotected. Also `6.5` vs "six-and-a-half", `3` vs "only three", `40%… in 2025` vs a document that writes "compared to 2024". | **ACCIDENT.** A claim is punished for being more precise than its quote. |
| A6 | **Every capitalized word in the proposition must appear in the document** | `_proper_nouns` `:513-521` | 4 refusals, all spurious. `"Using secure parcel lockers…"` → required noun **`using`**; `"context: Police enforcement (prosecution)…"` → **`police`** (the `context:` prefix is stripped, promoting `Police` to first word) against a document that writes "Prosecutors"; `USPS` against a document writing "U.S. Postal Service". | **Rule = PROTECTION (S8). Implementation = ACCIDENT.** Drop the statement's first token; accept acronym↔expansion. |
| A7 | **Topic-namespace prefix (`roster:`, `vote:`, `rule:`, `date:`, `context:`)** | prompt `:205`; consumed by `_topic` `:1421` and `_proper_nouns` `:516` | Undocumented as a contract but load-bearing twice: `_topic` returns `"fact"` for any unprefixed claim, collapsing every such claim into one subject bucket; and `_proper_nouns` strips only `^[a-z_]+:` — a model writing `Roster:` keeps `Roster` as a required proper noun. It is also a scenario taxonomy the target forbids, and it **trips GROUND-UP's own hardcoding guard** (`'vote' in source_extract.py:179`). | **ACCIDENT.** Delete the prefix and `_topic`. |
| A8 | **`normalized_value` — no vocabulary, no schema, no examples — used as an identity key in three places** | prompt `:207`; `content_id` `:1045`, lineage `:1050`, contradiction grouping `:1117` | `"8.5%"`, `"8.50 percent"`, `"8.5 pct"` are three distinct values ⇒ spurious contradiction candidates ⇒ up to 2 LLM calls ⇒ possible run-ending false block. It also supplies numbers to the A5 check: the *value string alone* killed claims whose proposition and excerpt matched perfectly. | **ACCIDENT.** Delete the field entirely. |
| A9 | **`epistemic_type` must be one of three exact strings** | `_epi` `:531-533` | Anything else silently becomes `observation` — the strongest class, and the one that admits a claim to contradiction adjudication. | **ACCIDENT, and pointed the wrong way** (F8). Delete the field; if kept, fail to `inference`. |
| A10 | **`authority_hint` must be an integer 1–4** | `_auth` `:536-547` | Clamps to LOWEST on failure — the right direction. But the *values* are unreliable: the ECB's own press release was rated `1` (LOW) while `cnbc.com` was rated `3`. The hint then becomes `authority_level`, `source_type` **and** `confidence = hint/4` — three stored fields carrying one unreliable integer. | **Fail direction = PROTECTION. The field itself = ACCIDENT.** Code knows the host; derive authority from a domain match against the plan's official domains instead. |
| A11 | **`expected_keys` is presence-only** | `deepseek_gateway.py:408-409` | No type check anywhere. `_strs` then silently yields `()` for a wrong-typed field — F9, total silent research failure. | **ACCIDENT.** Coerce a bare string to a one-element list; validate shape, not just presence. |
| A12 | **Date recognition covers three English formats only** | `:455-457` | ISO, `D Month YYYY`, `Month D, YYYY`. `17/01/2026`, `17.01.2026`, non-English month names all fail. It fails *closed*, so it is safe — but lossy for the institutional and EU sources the system targets. | **ACCIDENT** (moot once A4 is deleted). |
| A13 | **Number canonicalization assumes Anglo separators** | `:499-510` | `re.sub(r",(?=\d{3}\b)", "", raw).replace(",", ".")` — German/French `1.200` (thousands) parses as `1.2`. | **ACCIDENT** (moot once A5 is deleted). |
| A14 | **`_can_reconcile` requires a JSON boolean `true`** | `live_research.py:1254` | `"true"` as a string ⇒ the run-ending contradiction is recorded. The paired check one line up fails open. | **ACCIDENT**, asymmetric in the damaging direction. |
| A15 | **`ResearchPlan` demands 12 fields; 5 have no consumer at all** | `research_planner.py:23-35, 101-127` | `rules`, `prior_actions`, `scheduled_events`, `causal_drivers`, `process_summary` are parsed by `_strs`, serialized by `to_dict`, and re-parsed by `from_dict` — a closed loop. `deadline` is requested as ISO and only string-interpolated. | **ACCIDENT.** Five more fields the model can get wrong, for nothing. |
| A16 | **`EvidenceClaim.published_at` is a non-optional `datetime`** | `evidence.py:53` | Never bites in CORE because `evidence_time()` always supplies one — but it means the schema cannot represent "publication date UNKNOWN". A port that keeps this shape re-introduces the failure the target explicitly wants to avoid. | **ACCIDENT.** Make it `datetime | None`. |

**Net:** of 52 claim-level refusals in the four primary runs, **at least 46 are
accidental syntax brittleness** and at most a handful are genuine anti-hallucination
catches. The two checks that carry essentially all the real protection — verbatim excerpt
containment and proper-noun containment — account for the *rule*; almost every measured
loss comes from the *auxiliary* date, value, subject and normalized-value checks layered
on top of them.

---

## 6. Every essential factual-safety protection that must remain

**None of these may be dropped to simplify the port.**

| # | Protection | Where | Why it is load-bearing |
|---|---|---|---|
| S1 | **Every claim carries a verbatim excerpt that exists in the fetched bytes** | `source_extract.py:265-266` | The one check that makes the model unable to assert a sentence the page does not contain. Keep the rule; relax only the normalization (§5 A1–A3). |
| S2 | **The fetched document is data, never instructions** | `source_extract.py:173-224` | Per-call unpredictable marker from `question ⊕ url ⊕ content_hash`; fences and quote runs collapsed; the envelope word defanged; explicit operator framing. Research reads attacker-controlled pages. Port verbatim. |
| S3 | **A provider that names a URL never supplies evidence** | `live_research.py:692-736` + `_fetch_all` | Search results, RSS items and decoder output are candidate URLs only. Everything is fetched and read before any claim exists. Never let a snippet become a claim. |
| S4 | **The URL is fetched under a hostile-input policy** | `http.py:159-233, 419-451` | Scheme allowlist, per-hop revalidation after redirect, private/loopback refusal, size cap enforced during read *and* decompression, content-type allowlist. |
| S5 | **The cutoff is a mechanical view, not prompt wording** | `evidence.py:103-104, 186-217` | Downstream code can only receive claims through a view bound to `as_of`. A "cutoff status" *field* the LLM is asked to respect is not a substitute. |
| S6 | **A source is dated by when its content was demonstrably observed, never by what it says about itself** | `source_fetch.py:125-146` | `evidence_time()` = declared date only when ≤ `observed_at`, else `observed_at`. A page edited after the cutoff cannot serve post-cutoff text under a pre-cutoff timestamp. |
| S7 | **A future-dated page is refused** | `source_fetch.py:288-297` | A document claiming to be newer than the moment it was observed cannot be dated. |
| S8 | **A claim may not name a person, body or place the document never mentions** | `source_extract.py:316-320` | The rule is right; its `_proper_nouns` implementation is not (§5 A6). Keep the rule, fix the extraction. |
| S9 | **An unparseable authority signal clamps to the weakest reading** | `source_extract.py:536-547` | Correct fail direction — and the model that `_epi` must be changed to match (F8). |
| S10 | **One unreadable source costs that source, not the run** | `live_research.py:993-1008` | "We could not read a page" ≠ "we do not know what someone decided". Must survive the port — and must be extended to the calls that currently lack it (F5c). |
| S11 | **Content-addressed IDs and hashes; no randomness, no wall clock** | `ids.py` | Replayability. Every ID in the ported contract must be minted this way. |
| S12 | **Truncation salvage is the last resort, after the retry budget** | `deepseek_gateway.py:256-300` + `jsonsalvage.py` | A recovered prefix satisfies a schema check as well as a complete answer does; using it early silently simulates a truncated world. |
| S13 | **A duplicate document is rejected by content hash, not by URL** | `live_research.py:958-963` | Two URLs serving the same bytes are one source. |
| S14 | **Missing publisher and missing publication date degrade to derived/UNKNOWN, never to a crash or a rejection** | `source_fetch.py:543-548`, `:135-146` | Already correct; measured 0 publisher losses and 22 undated sources used normally. Preserve exactly. |
| S15 | **The prompt-visible render carries each claim's attested names** | `world_compiler.py:1955-1975` | The docstring records a live run where dropping entity names made a reviewer call correctly-cited names "unsupported inventions". |
| S16 | **Every refusal is recorded with its reason** | `live_research.py:825, 899-905, 952-964, 1006-1009, 1024-1030` | The habit is right; the port must close the two holes (F7) and record the excerpt on claim refusals (F11). |

### The battle-earned register

Protections whose docstrings name the live failure that bought them — port these with
their comments intact, because the comment is the test rationale:

| Protection | Quote (abridged) | Where |
|---|---|---|
| `HTTPException`/`zlib.error` containment | *"a live EU-Mercosur run died twenty minutes in when one page's chunked response ended 15 bytes short"* | `http.py:355-361` |
| The batchexecute decoder existing at all | *"Measured on this machine, 0 of 100 items from a live feed were resolvable"* | `rss.py:43-45` |
| Whole-question budget ceilings | *"one live OPEC+ run was killed from outside at forty minutes with 26 logical queries issued"* | `live_research.py:102-106` |
| The authoritative/general **share** (both directions) | *"Authoritative queries were once enqueued last and never ran; then the fix gave them unconditional priority, and a live run spent all twenty queries on official domains"* | `live_research.py:121-126`, `:584-589` |
| `RetrievalMode` pinned at process start | *"a cutoff a few hours in the past silently turned an intended nowcast into archive-only retrieval"* | `source_fetch.py:169-175` |
| `_CHROME` excluding `form`/`header` | *"an ASP.NET WebForms page puts the entire `<body>` inside one `<form>`… Stripping it extracted those pages to the empty string"* | `source_fetch.py:42-51` |
| Main-region hoisting + the 0.35 fallback | *"every single page from the Bank of England's site… yielded zero claims"* | `source_fetch.py:415-421, 447-449` |
| The circuit breaker | *"a live pass spent its whole discovery budget re-asking a blocked engine and compiled an empty world from the silence"* | `providers.py:21-24` |
| `_value_region` narrowed from a char window | *"a 320-character reach accepted a number 300 characters past the quote"* | `source_extract.py:334-339` |
| Date comparison by date, not by token | *"the phantom '1' from the month can never appear in prose that writes 'January'"* | `source_extract.py:281-287` |
| Checkpointing research the moment it exists | *"A live EU-Mercosur run spent twenty minutes gathering evidence and then died in a truncated HTTP read, leaving an empty trace directory"* | `api.py:791-797` |
| Truncation → more room before salvage | *"that still beats discarding everything, which is how a provider limit came to be reported as 'no actors were compiled'"* | `deepseek_gateway.py:259-268` |

By contrast, these carry **no** observed-failure provenance and should be treated as free
parameters, not as earned constants: `_TRIP_AFTER = 3` and the never-reset policy,
`max_contradiction_checks = 8`, `low_info_rounds_to_stop = 2`, `max_pages_per_query = 4`,
`_MIN_KEPT_SHARE = 0.35`, the decoder's `interval_seconds = 0.2`, and the runcache TTLs.

---

## 7. The simplest reliable target architecture

```
question, start, cutoff
   │
   ├─ 1. PLAN                (1 LLM call)
   │     → search queries, official domains, authoritative sources
   │       3 fields, all optional, all lists-of-strings; a bare string coerces to [string]
   │
   ├─ 2. DISCOVER            (0 LLM calls)
   │     official feeds (autodiscovery + conventional paths, min relevance score)
   │     Google News RSS  →  batchexecute decoder   (rank items, then slice)
   │     Serper                                     ← when the round is THIN, not only empty
   │     [DuckDuckGo: not ported]
   │
   ├─ 3. FETCH               (0 LLM calls)
   │     policy check → direct GET → Jina Reader on failure (BOTH modes)
   │     PDF → pdf_text ; HTML → extract_text
   │     dedup: one normalized-URL set, then content hash
   │     NOWCAST BY DEFAULT. Archive mode only on an explicit caller flag.
   │
   ├─ 4. READ                (1 LLM call per source, isolated, wrapped)
   │     untrusted-document envelope
   │     → natural-language statement + verbatim excerpt + entities (optional)
   │       + one bucket label from a fixed universal vocabulary
   │
   ├─ 5. VERIFY              (0 LLM calls)
   │     excerpt appears in the fetched text under punctuation-tolerant normalization
   │     proper nouns in the statement appear in the document (first token exempt)
   │     NO date check · NO value check · NO subject check · NO normalized_value
   │     a failure is a recorded LIMITATION, and only excerpt-absence deletes a claim
   │
   └─ 6. PACKAGE + RENDER    (0 LLM calls)
         cutoff filtering applied mechanically BEFORE rendering
         → one budgeted string for the compiler + a provenance sidecar on disk
```

**Six stages, one LLM call per source plus one plan call.** No repair rounds, no coverage
gate, no contradiction adjudication, no world compilation, no probabilities, no weights,
no scenario routing, no per-institution logic.

Rules the port must follow:

1. **Code owns every ID, timestamp, hash, URL normalization and date parse.** The model
   writes prose, a quote, and one bucket label.
2. **Every metadata field is optional and degrades to `UNKNOWN`.** A missing publisher,
   date, entity list or bucket never rejects a source or a claim.
3. **Verification failures are structured, non-fatal, and always carry the excerpt.**
4. **Every stage fails independently.** No single provider and no single document can end
   a run. Every model call inside the loop is wrapped, including the plan and the
   follow-up call.
5. **Nothing in retrieval knows what kind of question it is.** No institution names, no
   seeded domain lists, no scenario words — and this is enforced (§11).

---

## 8. The minimal evidence-package contract

```python
# (code) = generated by code. Everything else is optional and may be UNKNOWN.

@dataclass(frozen=True)
class Source:
    source_id: str                  # (code) content_id("s", canonical_url, content_sha256)
    url: str                        # (code) canonical; tracking params stripped
    text: str                       # extracted document text  [SIDECAR ONLY — never rendered]
    content_sha256: str             # (code)
    fetched_at: datetime            # (code)
    retrieval_route: str            # (code) "direct" | "reader" | "archive" | "feed" | "cache"
    cutoff_status: str              # (code) "before_cutoff" | "after_cutoff" | "undated"
    title: str = ""                 # UNKNOWN ⇒ ""
    publisher: str = ""             # UNKNOWN ⇒ "" (host is a fine default)
    published_at: datetime | None = None    # UNKNOWN ⇒ None. NEVER a rejection reason.

@dataclass(frozen=True)
class Claim:
    claim_id: str                   # (code) content_id("c", source_id, statement)
    source_id: str                  # (code)
    statement: str                  # natural language, one sentence, NO namespace prefix
    excerpt: str                    # verbatim from Source.text
    bucket: str                     # one of a fixed universal set (below); UNKNOWN ⇒ "world"
    entities: tuple[str, ...] = ()  # optional; empty is fine
    limitations: tuple[str, ...] = ()   # structured, non-fatal:
                                        #   "source_undated"
                                        #   "excerpt_normalized_match"
                                        #   "conflicts_with:<claim_id>"

@dataclass(frozen=True)
class EvidencePackage:
    question: str
    retrieved_at: datetime          # (code)
    cutoff: datetime | None         # (code, from the caller)
    world: tuple[Claim, ...]                 # public facts about the situation
    actors: dict[str, tuple[Claim, ...]]     # keyed by the name as it appears in sources
    schedules: tuple[Claim, ...]             # dated events and deadlines
    relationships: tuple[Claim, ...]         # who is connected to whom, and how
    constraints: tuple[Claim, ...]           # institutional / procedural / physical limits
    contradictions: tuple[tuple[str, str], ...]   # claim_id pairs — LABELLED, not adjudicated
    unresolved: tuple[str, ...]              # what retrieval looked for and did not find
    sources: tuple[Source, ...]              # full provenance
```

**Deliberately absent:** probability, weight, confidence, score, authority level,
epistemic enum, source-type enum, lineage id, `normalized_value`, `valid_from`,
`valid_until`, scenario category, and any instruction to the compiler.

`bucket` is **one label per claim from a fixed universal vocabulary**
(`world | actor | schedule | relationship | constraint`), assigned in the same extraction
call that writes the claim. It is not scenario routing: the vocabulary is identical for
every question and no code branches on question type. A missing or unrecognised label
degrades to `world`.

### Rendering to the compiler

The compiler's `evidence` parameter is `str | None`, so the package reaches it as text.
The renderer must:

* emit a **public block** (`world`, `schedules`, `constraints`, `contradictions`) and one
  **per-actor block** each, clearly labelled as belonging to that person alone;
* carry each claim's `[claim_id]`, publisher, and date — or the literal `date: UNKNOWN`;
* wrap the whole thing in an **untrusted-data envelope** with a marker derived from the
  question, exactly as `source_extract._build_prompt` does — the compiler's `_frame`
  labels the *question* as "data to model, not instructions" and does **not** do the same
  for evidence;
* state the routing rule explicitly (public → `shared_context`, per-actor →
  `private_context`);
* **never render `Source.text`** — the excerpt is sufficient. 20 sources × 9 000 chars is
  ~45 000 tokens and will not fit;
* enforce a **hard character budget with a recorded truncation flag**.

**On the budget.** The compiler is not the binding constraint. `shared_context` is re-sent
on **every** world adjudication (`sworldmodel/semantic_runtime/trajectory.py:246`), and
PR #5's own artifacts show 3–58 world calls per run against a real `shared_context` of
**141–325 characters**. A 4 000-token shared context on a 58-call run adds ~232 000 input
tokens — more than doubling a measured `total_in` of 411 227. CORE's own compact render
(`render_evidence`, limit 160 claims) measures ~3 000–5 000 tokens.

**Recommended: ≤ 25 000 characters rendered total (~6 000 tokens), and a much tighter
implicit ceiling on whatever reaches `shared_context`.**

---

## 9. How the package feeds the existing four-field compiler

The compiler contract is unchanged. `compile_scene(question, start, cutoff, context=None,
evidence=None, …)` (`compiler/scene_pipeline.py:70-72`) already accepts an evidence
string, and `compiler/scene_prompts.py:32-33` already interpolates it as
`EVIDENCE PACKAGE:\n{evidence}`. **The port adds a producer for that string.**

| Compiler field | Fed by | Rule |
|---|---|---|
| `actors[].name` | `actors`, `relationships` | Only parties the question or the evidence *refers to*. Retrieval never adds an actor the compiler would have to invent; `CALL1_SYSTEM`'s STEP ZERO identifiability check (`scene_prompts.py:133-142`) still governs. |
| `actors[].private_context` | that actor's claims **only** | The private channel: `semantic_runtime/adapter.py:80-82` records it as an actor profile and `views.py:70` shows it only to that actor. |
| `shared_context` | `world` + `constraints`, **selectively and briefly** | It is re-sent on every world call. Keep it to a short frame; leave the rest of the public record as background the compiler *used*. |
| `starting_events[]` | `schedules` + dated `world` claims | Only events that have already happened at `start`; `visible_to` is the compiler's decision. Retrieval supplies dated facts and never schedules the future. |
| `resolution` | the question + `schedules` | Retrieval supplies the real deadline where one exists, so the resolution window is the question's own rather than the cutoff's. |

### Public evidence must not become universal actor knowledge — **achievable, and already implemented**

The requirement is met by the PR #5 runtime, and this needs stating precisely because the
repository contains **two adapters with opposite behaviour**:

* **`sworldmodel/semantic_runtime/adapter.py:65-66` — the production runtime path**
  (used by `run_simulation.py:74`). `shared_context` becomes a **world fact only**:
  `world.apply("fact.set", {"key": "scene:shared_context", …})`. Its sole consumer is
  `world_mind.py:181-183`. `views.py:15-28` deliberately excludes it from actor views,
  with a docstring recording six live runs where it leaked, and
  `tests/test_semantic_runtime.py:1932-1947` enforces the exclusion.
  *(The docstring at `adapter.py:9` still says "given to every actor" — stale since PR #5.)*
* **`compiler/scene_adapter.py:84-86` — the compiler's internal determinism check**
  (used only inside `compile_scene` at `scene_pipeline.py:188-189` and by
  `tests/test_scene_compiler.py:348`). This one *does* copy `shared_context` into every
  actor's memory. That world is discarded — but the compiler still writes
  `actor_initial_views.json` from it, so with retrieval switched on, that **artifact**
  would show public evidence rendered as per-actor memory even though the runtime never
  does so.

So the routing rule is available and mechanically enforced where it matters:
**public → `shared_context` (world background only); per-actor → `private_context`;
anything an actor must *learn* during the run → a `starting_event` with a narrow
`visible_to`.**

**The inverse risk is real and unguarded.** `actor_mind.py:41-47` tells each actor that
what appears under `AUTHORITATIVE ACTOR EVIDENCE` is *"true and takes precedence… even
where a general impression of someone in your position would suggest otherwise"*, and
`private_context` is a flat string with **no slot for a source, a date, or an uncertainty
marker**. A retrieved third-party claim about a real person therefore becomes
unquestionable truth inside that person's model. The port needs an explicit policy for
what may be placed there.

---

## 10. Exact CORE files and functions: port / simplify / rewrite / fallback / reject

### PORT DIRECTLY (≈ 1 100 lines)

| Unit | Lines | Note |
|---|---|---|
| `ids.py` — `canonical_json`, `sha256_hex`, `content_id`, `prompt_hash` | 58 | The whole ID discipline (S11). |
| `http.py` — `FetchPolicy`, `check_url_shape`, `UrllibTransport` | 485 | Non-negotiable (S4, W9). **Add `LookupError`/`UnicodeError` to `_request` with a UTF-8 fallback** (F5b). |
| `pdf_text.py` | 135 | Primary records are PDFs. Stdlib-only. |
| `jsonsalvage.py` | 97 | Truncation recovery (S12). |
| `gnews_decode.py` | 209 | 135/135 measured. Typed failures, id cache, pacing. |
| `source_extract._build_prompt` + `_neutralize` | ~50 | The untrusted-document envelope (S2). Reuse it for the *package render* too. |
| `source_fetch.extract_text`, `_to_text`, `_main_region`, `extract_title`, `extract_published`, `_parse_dt`, `_header_date`, `_aware`, `_looks_textual`, `_publisher`, `_unescape` | ~140 | Every constant annotated with the page it was earned on. |

### PORT WITH SIMPLIFICATION

| Unit | Change |
|---|---|
| `source_extract.verify_claim` | Keep S1 + S8. **Delete** the date check, the value check, the subject check and `normalized_value`. Strengthen `_norm` for punctuation-adjacent spacing and ellipsis joins. Return a **limitation**, and delete a claim only on excerpt-absence. |
| `source_extract._norm`, `_proper_nouns` | Keep both, fixed as above. `_numbers`, `_dates`, `_date_component_numbers`, `_value_region`, `_supporting_region`, `_value_terms` become unnecessary. |
| `live_research._news_candidates` + `_resolve_item` | Keep. **Rank items by question-term overlap before slicing**, and raise `max_pages_per_query` (F12). Drop the `rss.resolve_item_url` first attempt. |
| `live_research._official_feed_candidates` | Keep the mechanism; require a minimum overlap score before spending a fetch slot (F3). Guard it with a time/fetch budget and run it genuinely once (F13). |
| `live_research._fetch_all`, `_normalized_dedup`, `_policy_filtered` | Keep. Collapse three URL-dedup layers into one session `seen` set. **Record the sliced tail in the trace** (F7). |
| `live_research._extract_all` | Keep the cutoff gate, content-hash gate, bounded pool and per-source isolation. **Record the sliced tail** (F7). Drop `ExtractionResult` (5 of its 6 fields are trace-only). |
| `providers.ProviderHealth` | Keep the breaker; collapse 8 counters to `consecutive_failures` + `tripped`; **do not count `note_empty` toward the trip**; add a half-open retry. |
| `providers.jina_reader`, `jina_title_search`, `serper_search`, `_score_response` | Keep. **Change both trigger conditions**: Reader must fire in *both* modes (F10); Serper must fire when a round is *thin*, per query, not only when the whole round is empty. |
| `rss.*` | Keep `site_roots`, `discover_feed_links`, `feed_urls_for`, `google_news_rss_url`, `parse_rss`, `is_google_redirect`, `RssItem`. Delete `resolve_item_url`, `_url_parameter`, `_decode_article_id`, `_publisher_link_in` (37 lines, measured 0/100). **Replace `from email.utils import parsedate_to_datetime`** — the stdlib module name itself trips the target's guard (§11). |
| `research_planner.plan_research` | Keep. Cut the plan from 12 fields to **3** (`initial_queries`, `official_domains`, `authoritative_sources`). `resolution_event`, `decision_makers`, `causal_drivers`, `rules`, `prior_actions`, `scheduled_events` are compiler instructions the target forbids and would moot STEP ZERO; `process_summary` and `deadline` have no consumer. **Coerce a bare string to a one-element list** (F9). **Wrap the call** (F5c). |
| `runcache.ExtractionCache` | Keep — it replays through the same verification. `SourceCache` optional. |
| `source_fetch.fetch_source`, `RetrievalMode`, `requires_archived_copy`, `archived_capture` | Keep, but **default to nowcast**: archive mode must be an explicit caller flag, never inferred from clock drift (F1). Put Wayback behind `ProviderHealth` with a distinct "index unavailable" rejection reason (F6). |

### REWRITE MINIMALLY

| Unit | Replaces | Why |
|---|---|---|
| `Source` / `Claim` / `EvidencePackage` (§8) | `evidence.EvidenceClaim` (23 fields), `EvidenceStore`, `EvidenceView`, `research.ResearchBundle` | 9 of `EvidenceClaim`'s 23 fields have **no consumer other than serialization** (`valid_from`, `valid_until`, `source_title`, `confidence`, `retrieved_at`, `retrieved_url`, `archived_at`, `content_sha256`, `extraction_prompt_sha256`); 2 more (`source_type`, `confidence`) are pure derivations of `authority_level`. Keep `EvidenceView`'s **unreachability property** (S5) and supply a replacement ordering, since `relevant()` sorted by `authority_level`. |
| `render_package()` | `world_compiler.render_evidence` (`:1955-1975`) | Port the shape — id, statement, publisher, date, names (S15) — grouped into §8 buckets, with `UNKNOWN` instead of a forced date, an untrusted-data envelope, and a hard budget. |
| The round loop | `_run_rounds` (73) + `_build_queues` (37) + `_next_queries` (48) + `_QueryQueues` (11) + `authoritative_query_reserve` (17) | The *behaviour* — alternate two channels; when one empties the other takes the rest — is earned by two documented starvation incidents and must be kept. It is ~15 lines, not 186. |
| A non-slot LLM path in the target's own caller | `gateway.py` (239) + `deepseek_gateway.py` (409) | GROUND-UP already has two hardened callers (`compiler/scene_llm.py`, `semantic_runtime/llm.py`). Extraction is one call per source and would trip `MAX_SEMANTIC_CALLS = 3`, so it needs a path that does not consume a semantic slot — plus `salvage_json` and a corrective retry. ~60 lines replaces 648. |
| `as_of` normalization at the CLI | — | Normalize to UTC and reject/repair a naive value before it can reach the loop (F5a). |

### KEEP ONLY AS FALLBACK

| Unit | Condition |
|---|---|
| `providers.serper_search` | Paid. Fires when free discovery is thin. Must never be required for a run to succeed. |
| `providers.jina_reader` | Only after a direct fetch fails — in **both** modes. |
| `providers.jina_title_search` | Only when the decoder fails on a known headline + publisher. |
| `source_fetch.archived_capture` + the Wayback path | Only for an explicit past-cutoff request. Never the default (F1, F6). |
| `jsonsalvage.salvage_json` | Only after the retry budget is spent (S12). |

### NOT PORTED

| Unit | Lines | Reason |
|---|---|---|
| `_detect_contradictions`, `_is_decisive_conflict`, `_can_reconcile`, `_is_observation`, `_subject_key`, `max_contradiction_checks` | ~190 | 2 checks fired in 5 runs, 0 contradictions found (F4); 2 LLM calls per pair; a false positive is unrecoverable (F8). **Replace with labelling** — surface disagreeing claims as `contradictions` pairs and let the compiler's own adversarial Call 2 judge. |
| `_record_fact_retrieval` + `fact_retrieval` trace | ~40 | Its own docstring says it never reports coverage and never stops research. |
| `augment_for_coverage`, `augment_targeted`, `_followup_budget`, `_missing_query`, `ResearchTrace.resume`, the `compiler_mode` mismatch guard | ~124 | Repair rounds. The target allows exactly one correction call. |
| `_compile`, `_ModeDispatchConfig`, the `partial_live_trace` rider | ~89 | The boundary to CORE's world compiler — import edge 2. |
| `total_*` budget tier + `_cumulative_room` | ~25 | Exists because repair could re-spend the opening budget. No repair ⇒ one budget. |
| `search.py` (DuckDuckGo) | 68 | `providers.py:16` records it as the direct cause of an empty-evidence pass; measured, it tripped in 3 of 5 runs and contributed no unique accepted source. Keep the 2-line `site_query` helper. |
| `evidence.check_lineage_independence`, `lineage_groups`, `independent_event_ids`, `lineage_event_id`, `render`, `render_view`, `relevant`, `by_entity`, `observations`, `tokens` | ~130 | **Zero production callers** (verified by grep; `check_lineage_independence` and `render_view` appear only in `tests/unit/test_evidence.py`). Lineage is keyed on three LLM strings and does not do what its docstring claims. |
| `epistemics.py` | 218 | A **second** epistemic vocabulary (`EpistemicClass` verified/inferred/hypothetical vs `EpistemicType` observation/inference/hypothesis). Imported by exactly one module — `grounding.py` — which is not ported. |
| `models.py` (keep nothing) | 430 | `WeightProvenance`, `ForecastStatus`, `IntegrityVerdict` are forecasting. `SourceType` declares 7 values of which the live path can emit 4. `AuthorityLevel` + `SourceType` + `confidence` are three stored fields carrying one unreliable integer. **Also cut `models.py:23` and the `terminal: TerminalExpression` field at `:145`** — import edge 3. |
| `research.py` `ResearchBundle` | 109 | Import edge 1. Replaced by `EvidencePackage`. |
| `coverage.py` (1 338), `repair.py` (706), `grounding.py` (751), `reality.py` (455), `uncertainty.py` (197), `schedule.py` (218), `world_compiler.py`, `semantic_plan.py`, `semantic_lowering.py`, `semantic_compile.py`, `engine.py`, `api.py`, `worldspec.py`, `structures.py`, `diagnosis.py`, `world_review.py`, `trajectory_audit.py`, `effects.py`, `expressions.py`, `executor.py`, `actors.py`, `novel.py`, `memory.py`, `outcomes.py`, `tracing.py` | ~3 900 + | Forecasting, branching, weighting, world compilation, simulation. Reachable **only** through the three import edges above. |

---

## 11. The exact GROUND-UP integration point

**One function, one parameter, no signature change.**

```python
# compiler/scene_pipeline.py:69-72   (UNCHANGED)
def compile_scene(question: str, start: str, cutoff: str,
                  context: str | None = None, evidence: str | None = None,
                  caller: SceneCaller | None = None,
                  out_dir: str | None = None) -> SceneCompileResult:
```

```python
# compiler/scene_prompts.py:25-36    (UNCHANGED)
if evidence:
    parts.append(f"\nEVIDENCE PACKAGE:\n{evidence}")
else:
    parts.append(f"\n{_MODEL_MEMORY_NOTE}")
```

The port adds a package and one flag:

```
sworldmodel/research/            ← NEW. Under `sworldmodel/`, so the guard already scans it.
    plan.py    discover.py   fetch.py    read.py
    verify.py  package.py    render.py
    http.py    pdf_text.py   ids.py      salvage.py

compile_question.py   --retrieve      run live retrieval; pass the render as `evidence`
run_simulation.py     --evidence / --retrieve   (currently missing entirely — F14)
```

`compile_question.py:76-79` reads `--evidence-file` into a string; `--retrieve` produces
the same string from `research.render_package(...)`. Everything after that line is
untouched.

### Five target-side constraints the port must satisfy

**(1) The compiler is frozen by hash.**
`tests/test_compiler_runtime_integration.py:149-216` asserts that the **set** of `.py`
files under `compiler/` equals `artifacts/semantic_runtime/COMPILER_FREEZE.txt`, that
every file's `git hash-object` matches, that `git ls-files --others compiler/` is empty,
and that `git diff --cached -- compiler/` is empty; `KERNEL_FREEZE.txt` similarly pins
`sworldmodel/{engine,events,simclock,terminals,world}.py`. **A new file inside `compiler/`
fails. An edit to `compiler/scene_prompts.py` fails.** Retrieval must live outside
`compiler/`, and any prompt change requires formally re-cutting the freeze.

**(2) Call 2 is not licensed to accept evidence-grounded actors.** Verified textually:

| prompt | line | wording |
|---|---|---|
| `CALL1_SYSTEM` | `scene_prompts.py:145` | *"identifiable from the question, the user context, **or supplied evidence**"* |
| `CALL2_SYSTEM` | `:206` | *"approve it only when the original question or supplied **context** states…"* |
| `CALL2_SYSTEM` | `:215` | *"Compare the original **question**, the start time, the compile cutoff…"* |
| `CALL2_SYSTEM` | `:252` | *"ABSTAIN … actors invented for parties **the question and context** NEVER REFER TO"* |
| `CALL2_SYSTEM` | `:273` | *"referents … that resolve to nothing **in the question or context**"* |

A reviewer following the letter must ABSTAIN on any actor identified only from retrieval —
which is the entire point of retrieval. **This is the single most important blocker on the
target side, and fixing it means editing the frozen `scene_prompts.py`.**

**(3) Supplying evidence deletes the model-memory doctrine.** `_frame` makes
`_MODEL_MEMORY_NOTE` and `evidence` mutually exclusive (`scene_prompts.py:32-35`), and
that note is the only place Call 1 is told *"do not present anything as verified, do not
fabricate citations"* and *"you must not import the known historical OUTCOME into the
starting scene."* Turning retrieval on removes the outcome-leakage prohibition with
nothing to replace it. An evidence-mode note must be added — again inside the frozen file.

**(4) The deterministic guards cannot see evidence, and routing around them is a trap.**
`scene_pipeline.py:173-174` passes only `question` and `context` to `validate_scene`, so
`scene_guards.window_findings` cannot see a deadline stated only in evidence. **Do not
work around this by passing the package as `context=`**: `scene_guards.py:177` scans
`f"{question}\n{context or ''}"` and its `_BEFORE_RE` will latch onto the first
`before|by <date>` in any unrelated source and raise a spurious `VALIDATION_FAILED`.
Evidence must go through `evidence=`.

**(5) The hardcoding guard scans `compiler/` and `sworldmodel/` recursively.** Running
GROUND-UP's own `scan_file` over CORE's 15 retrieval modules gives exactly **3
violations**:

```
rss.py:28            'email' in 'email.utils'
source_fetch.py:27   'email' in 'email.utils'
source_extract.py:179 'vote' in '…"proposition": "<short factual statement, prefixed with
                      a topic namespace like 'roster:' or 'vote:' …'
```

Both are fixable and both should be fixed anyway: the topic-namespace prefix is §5 A7,
and the `email.utils` import needs indirecting or replacing. **Everything else is clean** —
`rss.FEED_PATHS` is 15 generic paths, `site_roots` takes any host, and every domain comes
from the runtime plan. Do not introduce a curated domain list during the port. If the
package is placed at a new top-level root instead of under `sworldmodel/`, it is scanned by
nothing and `SCAN_ROOTS` must be extended.

---

## 12. Recommended implementation order

Each step is independently testable. **Do not start step *n+1* before step *n* passes.**

| # | Step | Done when |
|---|---|---|
| 0 | **Decide the freeze question.** Get an explicit decision on re-cutting `COMPILER_FREEZE.txt` to allow the two `scene_prompts.py` edits (§11.2, §11.3). | The decision is recorded. **If it is "no", stop — see §13.** |
| 1 | **Transport and IDs.** `sworldmodel/research/{http,ids,pdf_text,salvage}.py` ported verbatim + the `LookupError` fix. | Fetch-policy tests pass (scheme, redirect revalidation, size cap during decompression, content type, bad charset); hardcoding guard passes. |
| 2 | **Fetch + text extraction, nowcast only.** | Given URLs, produces `Source` records with publisher/title/date degrading to UNKNOWN and never raising. Naive `as_of` is normalized at the boundary. |
| 3 | **Discovery.** Official feeds → Google News RSS → decoder → Serper. | Given queries, produces candidate URLs; **each provider can be disabled individually and the run still completes**; the sliced tails appear in the trace. |
| 4 | **Read + verify.** Envelope prompt, natural-language claims, excerpt anchoring, proper-noun containment, structured limitations. | The **52 refusals this audit measured** are replayed offline against the cached documents: **≥ 45 survive**, and every survivor still has a real excerpt in the bytes. |
| 5 | **Plan**, 3 fields, string-coercing, wrapped. | A plan response with a bare string for `initial_queries` still yields queries (F9 regression). A `GatewayError` mid-loop does not discard gathered evidence (F5c). |
| 6 | **Package + render.** | ≤ 25 000 chars with a truncation flag; every claim carries `[claim_id]`, publisher, date-or-UNKNOWN; actor blocks separated from the public block; untrusted-data envelope present; provenance sidecar written. |
| 7 | **Prompt changes + freeze re-cut.** Extend `CALL2_SYSTEM` to admit supplied evidence; add an evidence-mode doctrine note carrying the outcome-leakage prohibition. | `COMPILER_FREEZE.txt` re-cut and the change justified in writing; all existing compiler tests pass. |
| 8 | **Wire it up.** `--retrieve` in `compile_question.py`; `--evidence`/`--retrieve` in `run_simulation.py` and `run_scene_acceptance.py`. | The **first ever** end-to-end run with `evidence_mode == "evidence_package"`, plus a leak test asserting no rendered source text reaches any actor view. |
| 9 | **Optional: past-cutoff mode** behind an explicit flag, with Wayback under `ProviderHealth`. | A past cutoff refuses undated sources with a structured limitation and never engages from clock drift. |

---

## 13. Risks and tests required before the port ships

### Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Relaxing the verifier admits invented evidence.** The date and value checks do catch *some* fabrication. | Keep S1 and S8. Replay all 98 recorded claims through the new verifier and hand-check every claim that newly survives. Any claim whose excerpt is not in the bytes is a regression, full stop. |
| R2 | **`shared_context` bloat multiplies across world calls** (3–58 per run, measured). | Hard budget on the render; a much tighter implicit ceiling on `shared_context`; a size regression test. |
| R3 | **Retrieved third-party claims about real people become unquestionable truth** inside `private_context` (`actor_mind.py:41-47`), which has no uncertainty slot. | An explicit policy for what may enter `private_context`; prefer routing contested claims to the public block. |
| R4 | **Retrieval starts steering the answer.** A package that pre-writes the outcome makes the simulation decorative. | No probabilities/weights/scores by construction (§8); no `resolution_event` or `decision_makers` from the planner; a guard test asserting those field names never appear. |
| R5 | **Prompt injection via evidence.** The compiler's `_frame` labels the *question* as data and does not do the same for evidence. | Port CORE's marker envelope into the renderer (S2). |
| R6 | **Provider-shape drift** (Google batchexecute, Jina, Serper). | Typed failures already; add contract tests with recorded fixtures and a live smoke test that may be skipped but never fails the suite. |
| R7 | **Wayback single point of failure** (F6) if the archive path ships. | Step 9 last, behind a flag, under `ProviderHealth`, with "index unavailable" distinguished from "no capture". |
| R8 | **Scenario logic creeps into retrieval.** | Package under `sworldmodel/research/` so the existing guard scans it; every domain from the runtime plan. |
| R9 | **Cost and latency.** One LLM call per source; measured **270–320 s and 38–81 k tokens per question**. | Cap sources per run; keep `ExtractionCache`; make the budget an explicit caller parameter; report retrieval calls **separately from `semantic_calls`** so `README.md:52`'s "two semantic calls" stays true. |
| R10 | **The freeze.** Steps 7 and 8 change hashed files and add a code path that has never run. | Re-cut deliberately, with the justification recorded; do not let the port land as a silent freeze break. |

### Tests required

**Grounding (must not regress)**

1. A claim whose excerpt is not in the fetched bytes is refused. *(S1)*
2. A claim naming a person the document never mentions is refused. *(S8)*
3. A document containing `<<<END_UNTRUSTED_SOURCE_DOCUMENT …>>>` plus its own instructions does not change the extraction output. *(S2)*
4. A snippet from a search provider never becomes a claim without a fetch. *(S3)*
5. `http` refuses `file:`, a redirect to `127.0.0.1`, an over-size body and a disallowed content type — the last three *after* the first hop. *(S4)*
6. A page declaring a date after the moment it was observed is refused. *(S7)*
7. A post-cutoff claim is unreachable through the package, mechanically. *(S5)*

**Non-fatality (the point of the port)**

8. A source with no publisher is used, with `publisher = ""`.
9. A source with no publication date is used in nowcast, with `published_at = None` and `cutoff_status = "undated"`.
10. A source with no publication date under an explicit past cutoff produces a **structured limitation**, not an exception and not a run failure.
11. An extraction call that fails costs that source only.
12. A plan call, a follow-up call, and an extraction call each failing in turn leaves the gathered evidence intact. *(F5c)*
13. Every provider disabled in turn (feeds, RSS, decoder, Reader, Search, Serper) still yields a package or an honest empty package with `unresolved` populated.
14. A naive `--as-of` is normalized, not crashed on. *(F5a)*
15. A response with `Content-Type: text/html; charset=none` rejects that page and not the run. *(F5b)*
16. A plan response with a bare string where a list is expected still produces queries. *(F9)*
17. `as_of` equal to the run start selects **nowcast**, not pastcast. *(F1)*

**Brittleness regressions (each derived from a real refusal in §4)**

18. Excerpt `S. 4784, 6/15/2026` verifies against document text `s. 4784 , 6/15/2026`. *(A1)*
19. Excerpt `(Du and Wang, 2022)` verifies against `( du and wang, 2022 )`. *(A1)*
20. An excerpt joining two real sentences with `…` verifies. *(A2)*
21. A claim asserting "March 18, 2026" whose excerpt says "on March 18" verifies, with the source's `published_at` recorded beside it. *(A4)*
22. A claim about "the ECB's September 2026 meeting" whose excerpt says "in September" verifies. *(A5)*
23. A statement beginning "Using…" or "Police…" is not required to contain that word in the document. *(A6)*

**Contract**

24. The rendered package contains no field named `probability`, `weight`, `score`, `confidence`, `prior`, or `authority`.
25. `compile_scene`'s signature and `_frame`'s structure are unchanged; all existing compiler tests pass.
26. Rendered package size stays under the cap for a 28-source run, and truncation is flagged.
27. `tests/test_hardcoding_guard.py` scans `sworldmodel/research/` and passes.
28. `import sworldmodel.research` pulls in **zero** `compiler.*` modules.
29. `COMPILER_FREEZE.txt` matches the tree after the deliberate re-cut.

**Determinism**

30. Two runs over the same recorded documents produce identical `source_id`s, `claim_id`s and content hashes.
31. A cached extraction replays through the *same* verifier as a live call.

---

## 14. Verdict

# GO — with a hard precondition and a fixed scope

**Port it. Do not port it as-is, and do not port most of it.**

The retrieval layer contains roughly **1 800 lines that genuinely produce grounded
evidence** — the fetch policy, the text extractor, the PDF reader, the batchexecute
decoder, the untrusted-document envelope, the excerpt anchoring, the archive-dating rule,
and the official-feed discovery mechanism. Those are worth having and would take a long
time to rediscover; nearly every constant in them is annotated with the live failure that
set it. **That part is a genuine asset and this audit recommends taking it.**

The other ~4 400 lines in the retrieval closure are forecasting machinery the target
rejects, trace fields with no reader, a second implementation of a problem already solved
elsewhere in the same file, or — in the case of the contradiction subsystem — a run-ending
risk that fired twice in five runs and found nothing.

**Three findings decide the shape of the port, and all three are measured, not argued:**

1. **`as_of = now` silently becomes archive-only retrieval.** 0.036 s of clock drift did
   it in four of four runs, and it cost 54% of all rejected candidates. The A/B control is
   unambiguous: same question, cutoff pushed 10 minutes out, **zero** archive rejections,
   official feeds live, Jina Reader engaged, and the run reached the engrossed bill PDF and
   the Statement of Administration Policy instead of GovTrack.

2. **The claim verifier destroys most of what the extractor finds, and preferentially
   destroys the best claims.** 52 of 98 refused. The Senate's own record of the motion being
   withdrawn, the roll-call result of the cloture vote, the market expectation for the next
   ECB meeting, the date Disney's new CEO takes office — every one extracted correctly with
   a verbatim quote, every one thrown away by a date-proximity or bare-year rule that the
   code could have satisfied from `source.published_at`, a field it already holds. At most
   a handful of the 52 were real hallucination catches.

3. **The target's evidence path has never been executed.** 0 of 183 compiles ran with an
   evidence package, `run_simulation.py` has no `--evidence` flag, and no test covers the
   mode. This is a greenfield seam, not a supported one.

**The hard precondition is on the target side, not the donor's.** `CALL2_SYSTEM` — the
compiler's independent reviewer — is textually instructed to abstain on actors that are
not identifiable *"from the question or context"*. `CALL1_SYSTEM` says *"question, the
user context, or supplied evidence"*. Call 2 was never updated. Retrieval exists precisely
to name parties the question does not name, so as it stands the reviewer would abstain on
the port's primary use case. Fixing it means editing `compiler/scene_prompts.py`, which
`test_frozen_compiler_files_are_unchanged` pins by hash — so **the compiler freeze must be
formally re-cut, deliberately, with the change recorded.**

**If that decision is refused and the compiler stays frozen, this verdict becomes DO NOT
PORT** — attaching a live retrieval layer to a reviewer instructed to reject everything it
produces would be strictly worse than the current honest `model_memory_unverified` mode.

Given the re-cut, the sequencing is not negotiable either. **Fix the cutoff default and
the verifier before wiring anything to the compiler.** They are independent and
multiplicative: the control run proves that fixing discovery alone gets you better sources
and a *worse* yield (80% refused). A port that carries either defect forward will look
like it works — every run completed, every request returned 200 — while delivering an
evidence package that omits the facts the question turns on.

**Scope: take ~1 800 lines. Reject ~4 400. Cut three import edges. Re-cut the freeze.
Fix the mode default and the verifier first. Then wire it up.**

---

## Appendix A — audit method and limits

* The live runs used the exact production functions `research_planner.plan_research` and
  `LiveResearchBackend._run_rounds`. `_compile` was never called; no world was compiled and
  nothing was forecast.
* No file in `SWORLDMODEL-CORE` was modified. No production file in
  `SWORLDMODEL-GROUND-UP` was modified. The harness and all analysis scripts live outside
  both repositories.
* Refusal diagnosis was done by replaying `runcache.ExtractionCache` raw model output and
  `runcache.SourceCache` documents through `verify_claim` offline — no re-querying, no
  re-fetching, and no modification of the production check.
* **Four questions plus one control is a small sample.** It is enough to establish that a
  failure mode exists and to size it on these questions; it is not enough to estimate a
  population rate. The nowcast control differs from its pastcast twin in the mode *and* in
  the plan the model happened to generate, so it is a clean A/B only on the mode-gated
  behaviours (archive rejections, Reader engagement, feed availability), not on claim yield.
* **One environment.** `web.archive.org/cdx` timed out on a direct probe here; DuckDuckGo
  answered some requests and blocked others; `reuters.com` returned 401. Provider
  availability elsewhere will differ.
* Three rungs of the discovery chain (Jina Reader in pastcast, Jina Search, Serper) were
  exercised **zero** times in the primary runs, so this audit says nothing about whether
  they work — only that the conditions gating them almost never occur.
* Three independent read-only reviewers ran against the same code (retrieval reliability,
  simplification, ground-up port). Their findings are folded into §3, §5, §9, §10 and §11.
  **Every reviewer claim reproduced here was independently re-verified against the source
  before inclusion** — including the naive-`as_of` `TypeError`, the `charset` `LookupError`,
  the `_schema_ok` presence-only check, the zero-production-caller status of
  `check_lineage_independence` and `render_view`, the `epistemics.py` import fan-in, the
  compiler freeze test, the Call-1/Call-2 licensing asymmetry, the three hardcoding-guard
  violations, and the two adapters' opposite `shared_context` behaviour. One reviewer claim
  was **corrected**: `shared_context` does *not* reach every actor in the production
  runtime — that behaviour belongs to `compiler/scene_adapter.py`, which `compile_scene`
  uses only for its internal determinism check.
