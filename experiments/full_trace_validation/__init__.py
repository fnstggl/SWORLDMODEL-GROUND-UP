"""Full-trace validation harness (experiment-only, not production).

A bounded transparency validation of the already-accepted engine: run the
REAL production path (``compiler.scene_pipeline.compile_scene`` ->
``sworldmodel.compilation.existing_compiler_adapter`` ->
``sworldmodel.compilation.decision_route`` ->
``sworldmodel.counterfactuals.manager`` -> ``sworldmodel.outcomes`` ->
``sworldmodel.reporting``) against a live model, and record every single
model call that the run makes.

The harness NEVER authors simulation content.  Actor turns, game-master
resolutions, compiler manifests, and generated candidates all come from
recorded live API calls; if a call fails, the failure is recorded and
reported, never replaced with harness text.

Modules
-------
``recorder``  the three recording seams (compiler transport, candidate
              generator, actor/GM models) plus the append-only call
              ledger and the network-boundary counter that proves no
              call bypassed recording.
``evidence``  the evidence manifest: per-item claim / source / date /
              cutoff availability / classification / who may know /
              whether the compiler used it / which context it entered.
``freeze``    sha256 freeze of every input before simulation.
``ledgers``   per-branch step ledgers reconstructed from the recorded
              calls, the engine raw log, the plan, and the branch result.
``predicates``experiment-owned, attribution-anchored outcome predicates.
``scenario_peter`` frozen scenario data (never in ``sworldmodel/``).
``runner_peter``   the scenario driver.
``report``    the UNDER_THE_HOOD report generator.

a16z historical counterfactual (scenario 3)
-------------------------------------------
``cutoff``    mechanical historical-cutoff enforcement (date arm + phrase
              arm) with a canary the validator must reject.
``scenario_a16z``   frozen scenario data: cast, scope note, evidence,
              code-owned salary mapping, compile acceptance criteria.
``predicates_a16z`` the declared metrics: an attribution-anchored
              authority chain, plus the CODE-OWNED salary metric.
``branch_diff``     proof that the salary branches differ in the salary
              and in nothing else.
``offer_delivery``  did the offer actually reach the subject's actor?
``runner_a16z``     the scenario driver.
``report_a16z``     the a16z UNDER_THE_HOOD report generator.
"""

RUN_LABEL = "UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION"
HARNESS_VERSION = "full_trace_validation_v1"
