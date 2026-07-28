# Production route audit — minimal_scene_v1

The canonical production path for a normal question:

```
compile_question.py "<question>" [--start ..] [--cutoff ..] [--context ..]
  -> compiler.compile_scene            (compiler/scene_pipeline.py)
     -> SceneCaller.semantic_call x2   (Call 1 scene, Call 2 review)
        [x3 max: Call 3 targeted correction, only on REVISE]
     -> scene_schema.validate_manifest_shape / validate_review_shape
     -> scene_validate.validate_scene  (deterministic, zero LLM)
     -> scene_adapter.instantiate_scene -> existing sworldmodel.World
     -> scene_resolution.build_nl_terminal -> existing sworldmodel Terminal
```

## Mechanical proof the legacy (~200-call) compiler is not reachable by default

Executed audit (see git history for the exact commands):

1. `import compiler` → `'compiler.legacy' in sys.modules` = **False**.
2. A full scripted `compile_scene(...)` end to end (Call 1 → review →
   validation → instantiation) → status `compiled`, and
   `'compiler.legacy' in sys.modules` = **False**.
3. `grep legacy` across every minimal-path module
   (`scene_schema.py`, `scene_llm.py`, `scene_prompts.py`,
   `scene_validate.py`, `scene_adapter.py`, `scene_resolution.py`,
   `scene_pipeline.py`, `compiler/__init__.py`) → **only docstring
   mentions in `__init__.py`; zero imports**.
4. The ONLY code path importing `compiler.legacy` anywhere outside
   `compiler/legacy/` itself is the explicit diagnostic branch in
   `compile_question.py` guarded by `--compiler legacy`, which also prints
   a superseded-path warning to stderr.  `--compiler` defaults to
   `minimal`; nothing selects `legacy` automatically, and there is no
   fallback from a failed minimal compile to the legacy compiler.

## Semantic-call budget

`compiler/scene_llm.py` enforces `MAX_SEMANTIC_CALLS = 3` **before** a
slot opens: the fourth `semantic_call()` raises
`CompilerCallBudgetExceeded`, which `compile_scene` converts to the
structured failure `COMPILER_CALL_BUDGET_EXCEEDED`.  Transport/JSON
failures allow exactly one logged technical retry per slot
(`MAX_TECHNICAL_RETRIES_PER_SLOT = 1`) and then fail structurally
(`TECHNICAL_FAILURE`); nothing loops.  Every provider request is logged
with prompts, raw response, token usage, duration, and attempt number
(`SceneCaller.requests`), and every request runs under a 90 s socket
timeout plus a 300 s total read deadline.

## Version stamping

Every compile artifact records `compiler_version = "minimal_scene_v1"`
(`input.json` and `compiler_metrics.json`).
