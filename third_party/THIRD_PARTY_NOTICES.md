# Third-Party Notices

This project integrates the following third-party software as pinned,
unmodified Git dependencies (see `UPSTREAM_LOCK.json` for exact commits and
`INTEGRATION_METHOD.md` for how they are installed). No third-party source is
vendored into this repository.

## Concordia (gdm-concordia)

- Copyright 2023 DeepMind Technologies Limited
- Source: https://github.com/google-deepmind/concordia
  (integrated via the fork https://github.com/fnstggl/concordia at the pinned
  commit `7779a4c9f96bad10816d88c54e4cb17d53ac5222`)
- License: Apache License, Version 2.0
  (full text: `LICENSE` at the repository root of the pinned checkout;
  https://www.apache.org/licenses/LICENSE-2.0)
- Used as: the local social-simulation engine (entities, game masters,
  engines, memory, checkpointing), unmodified.

## AgentSociety 2 (agentsociety2)

- Copyright the AgentSociety authors (Tsinghua FIB Lab)
- Source: https://github.com/tsinghua-fib-lab/agentsociety
  (integrated via the fork https://github.com/fnstggl/agentsociety2 at the
  pinned commit `6e9fc2e79f89f65a3e3d0d7899e380f7394099be`, package
  `packages/agentsociety2`)
- License: Apache License, Version 2.0
  (full text: `LICENSE` at the repository root and in
  `packages/agentsociety2/LICENSE` of the pinned checkout;
  https://www.apache.org/licenses/LICENSE-2.0)
- Used as: the distributed orchestration layer (agent workspaces, Ray-based
  batch runner, LLM dispatcher, tracing, replay), unmodified.

Both licenses are permissive Apache-2.0; attribution and license reproduction
obligations are met by this notice, the pinned checkouts' LICENSE files, and
`UPSTREAM_LOCK.json` provenance records. NOTICE-file obligations: neither
pinned checkout ships a NOTICE file at its root as of the pinned commits.

Transitive Python dependencies (ray, litellm, numpy, pandas, mcp, etc.) are
installed from PyPI under their own licenses; the exact resolved set is
frozen in `docs/engine_migration/phase0_engine_env_freeze.txt`.
