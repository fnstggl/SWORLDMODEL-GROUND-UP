# Before-state baseline (start of the completion pass)

recorded: 2026-07-28T17:42:10-04:00
base commit (origin/main): 226fe05c971b90053e889721785f4dcd250b6843
branch: claude/sworldmodel-runtime-completion
predecessor PR: #4 https://github.com/fnstggl/SWORLDMODEL-GROUND-UP/pull/4 (MERGED)

## test count
230 passed in 7.79s

## compiler production file hashes (must never change)
420fea310883622ccc61434271680cb14244c982 compiler/__init__.py
4bbeb854058fbb8d0c3974cf6b9fb82ecdfc6d4d compiler/legacy/__init__.py
1f9467ed5e69f106ff89779947c57d6b23e0368e compiler/legacy/assembly.py
da8b549dcfdf70221e251e979f504598246d3ec9 compiler/legacy/capabilities.py
d1f7a7565c940c8a0c9c82d3db4125324d4b6071 compiler/legacy/causal_discovery.py
5c71ffccfa514d2e27f83a856460637b3d37af2c compiler/legacy/graph_builder.py
b79b26d15af42ad8e10c24cedc57c1aef2de3b8c compiler/legacy/llm.py
cc3436b0457d3cc2d30cfd04d5773b20e932aa72 compiler/legacy/lowering.py
493f173f4601ff9bf90fc7f4aff8d3bc20fc6322 compiler/legacy/pipeline.py
e30a0d11467e5dad24cac32bfe00e5996d4a4c29 compiler/legacy/provenance.py
5025da3ceb92d70bb17b100e401728995b0ebad4 compiler/legacy/resolution.py
ccf758acd1d840562668b1696efb2f8a85755be8 compiler/legacy/review.py
6eccc3af319c6e70d40f67923f355363807a2556 compiler/legacy/roundtrip.py
601e017f96dea46b0a5b9672d495273fd415a96f compiler/legacy/translation.py
c4ec2d1c7a899fef298e23d8811fa690ec9a25e3 compiler/legacy/validation.py
e5cf83819ef84105a662746fe0947c1fb7bc2625 compiler/legacy/world_graph.py
15e5243d7532fa7962254f3055a15b9b34a9e951 compiler/scene_adapter.py
3533cbd4cf07e6c104356b1d16963bf5f05a1ddb compiler/scene_guards.py
e8d8e32725615f30fc835ced281fba087792656c compiler/scene_llm.py
149e81126541505b27f50d9887279302ac4b035c compiler/scene_pipeline.py
8e7343bc6222932c7733d6d35f0493fa4cbdaf4d compiler/scene_prompts.py
f6fda7b875de127bc48c5836ad5eea285f234976 compiler/scene_resolution.py
99ee81f06ba9404b017bda4bb0a2d1745f9e45cb compiler/scene_schema.py
f93414c4e7b80a725eae13ea6506b18b3a6017ac compiler/scene_validate.py

## semantic runtime file hashes at baseline
330d812fb130f458d2d77927468b1ab9f6c6b674 run_simulation.py
af0267daed8780f4f2fa56e8bcd3e2b73f4e20e4 sworldmodel/semantic_runtime/__init__.py
80e6b9d8652e8d58fcd89364428f0c8a1e65b256 sworldmodel/semantic_runtime/actor_mind.py
180a249dc6f97e0356f3661e8418c7af3609b142 sworldmodel/semantic_runtime/adapter.py
edfbdbc26830b86a1f59fcbab87f673ae727f212 sworldmodel/semantic_runtime/envelope.py
53625431614e7273a8c2d50dc3d5fab92b19b19f sworldmodel/semantic_runtime/journal.py
c85b9080c0dccc756a4f3dad511bd156b06e2adb sworldmodel/semantic_runtime/llm.py
bf4988230f2423298601594f502cf7076b69f198 sworldmodel/semantic_runtime/replay.py
89ee46b0cdda110dcd068643f4664b8234315303 sworldmodel/semantic_runtime/resolution.py
5ebc270ca80235ec47e7c121af608fa8a34ab328 sworldmodel/semantic_runtime/trace.py
bd9e4f0aeca07029fd9d8adb36042d554f0f6868 sworldmodel/semantic_runtime/trajectory.py
a19fda36a9b779dc03f6cbfee8aff15e21cd55e9 sworldmodel/semantic_runtime/views.py
2eacd61a428eedd75827689be993fc620dda577c sworldmodel/semantic_runtime/world_mind.py

## preserved baseline artifacts
artifacts/semantic_runtime_v1_baseline/simulations/  (7 runs)
  - case1_cold_email
  - case2_negotiation
  - case3_group
  - unseen1_confirm
  - unseen2_feedback
  - unseen3_permission_slip
  - unseen4_holiday_deposit

## previous adversarial and quality reports (preserved)
  - ACTOR_WORLD_SEPARATION_REVIEW.md
  - BEFORE_STATE.md
  - FREEZE_AND_INTEGRATION_REVIEW.md
  - HOSTILE_OUTPUT_REVIEW.md
  - INFORMATION_BOUNDARY_REVIEW.md
  - QUALITY_ACTOR_REALISM.md
  - QUALITY_CAUSAL_REALISM.md
  - QUALITY_GATE_FINAL.md
  - QUALITY_INFORMATION_AND_TIMING.md
  - QUALITY_TERMINAL_INDEPENDENCE.md
  - REPLAY_DETERMINISM_REVIEW.md
  - TIME_CAUSALITY_TERMINAL_REVIEW.md
  - UNIVERSALITY_AND_BLOAT_REVIEW.md
