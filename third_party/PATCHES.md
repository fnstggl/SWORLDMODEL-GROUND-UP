# Upstream Patches

**No upstream modifications exist.**

Both pinned upstreams are used exactly as checked out at their pinned SHAs
(`UPSTREAM_LOCK.json`):

- Concordia `7779a4c9f96bad10816d88c54e4cb17d53ac5222` — unmodified.
- AgentSociety 2 `6e9fc2e79f89f65a3e3d0d7899e380f7394099be` — unmodified.

Environment-level compatibility measures (not source patches):

- `mcp>=1.13.1,<2` version pin in the engine environment (upstream's floating
  lower bound resolves to an incompatible major version).
- Dummy `AGENTSOCIETY_LLM_*` variables for offline import/testing.
- Test plugins (`pytest-xdist`, `pytest-timeout`, `pytest-asyncio`, `anyio`)
  required by the upstream suites' own configurations.

A future patch or fork is permitted only under the master directive's
conditions: the required behavior is impossible through available interfaces,
demonstrated by a failing contract test; the smallest possible patch is
isolated; upstream remains otherwise intact; the patch is documented here
line by line; and an adversarial reviewer agrees it is unavoidable.
