"""Local Concordia backend: stock upstream runtime, driven by contracts.

Module map (import the submodule you need explicitly):

- ``planner``  -- pure stdlib.  Deterministic
  ``CompiledDecisionWorld`` -> ``ConcordiaInitializationPlan`` mapping.
  Importable everywhere ``sworldmodel`` is importable.
- ``builder``  -- plan -> live Concordia objects through the audited public
  APIs only (no upstream forks).  Requires the optional ``gdm-concordia``
  package (Python >= 3.12); importing it without that package raises a
  clear ``ImportError`` while the rest of ``sworldmodel`` stays usable.
- ``runner``   -- drives one branch through Concordia's stock sequential
  engine and captures the committed event stream, per-actor memories, the
  raw log, and step/wall-clock stats.  Same optional dependency as
  ``builder``.

This package intentionally does not import its submodules here: the
planner must remain importable when Concordia is absent, and the
engine-dependent modules must fail loudly only when actually requested.
"""
