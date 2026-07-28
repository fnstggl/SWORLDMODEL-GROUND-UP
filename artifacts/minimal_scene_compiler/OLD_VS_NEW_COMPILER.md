# Old vs new compiler

| | legacy multi-stage | minimal_scene_v1 |
|---|---|---|
| semantic LLM calls per compile | ~130–250 (resolution, 9 discovery aspects, per-item translation with retries, patches, 2 reviews, ×3 anchored repair rounds) | 2 normal, 3 max (hard-enforced before the call) |
| semantic representations | 3 (NL description items → capability instances → genesis op plan) | 1 (the four-field manifest, stored as-is) |
| translation layer | closed 19-capability menu, per-item calls, reference registry, deferred passes, surgical patches | none |
| repair machinery | anchored full re-description rounds, reuse cache, corrections diet, patchable findings | one targeted correction call, only on reviewer REVISE |
| observed live behavior | 1 full success in ~20 attempts across 4 batches; per-run nondeterminism; failure tail still surfacing new causes per batch; minutes per compile; one provider stall hung a run for hours | first live compile: 2 calls, 5.3 s, first-pass APPROVE; structured outcome guaranteed by construction |
| what the LLM authors | world objects, action definitions, effect templates, terminal ASTs, provenance labels per item | who exists (with private context), shared context, initial events, one NL resolution |
| what code authors | IDs, lowering, validation, runtime ops | IDs, normalization, validation, direct instantiation, cutoff, ledger |
| where futures live | validated as *possible* actions/producers at compile time | entirely in the simulation; compile time contains no futures at all |
| failure modes eliminated by construction | — | missing/inconsistent references (no references to translate), duplicated per-item events (event dedup + no per-item generation), invented times/organizations (reviewer + no capability slots demanding them), prewritten terminals (genesis-false check + no terminal AST), malformed parameters (no parameters), lowering mismatches (no lowering), reviewer instability loops (single review, one correction), long compile times, unbounded rerolls |
| status | demoted to `compiler/legacy/`, reachable only via explicit `--compiler legacy` diagnostic flag; never auto-selected | production default |

The legacy path remains in-tree solely for diagnostic comparison and its
regression tests still run (against `compiler.legacy.*` imports); the
production route audit proves normal compilation cannot reach it.
