# Upstream Integration Method

Per the master directive's non-negotiable upstream-code preservation rule, the
chosen method is the directive's preferred one: **exact Git dependencies
pinned to immutable commit SHAs**, installed unmodified. No upstream source is
copied into this repository; no selected-file pseudo-fork exists; no upstream
file is edited, monkey-patched, or recreated from memory. `PATCHES.md` records
zero deviations.

## Pinned upstreams

Authoritative pins: `third_party/UPSTREAM_LOCK.json`.

| Upstream | Pinned SHA | Install |
|---|---|---|
| Concordia (gdm-concordia 2.4.0, Apache-2.0) | `7779a4c9f96bad10816d88c54e4cb17d53ac5222` | editable from the pinned checkout; or `pip install git+https://github.com/fnstggl/concordia@7779a4c9f96bad10816d88c54e4cb17d53ac5222` |
| AgentSociety 2 (agentsociety2 2.8.4, Apache-2.0) | `6e9fc2e79f89f65a3e3d0d7899e380f7394099be` | editable from `packages/agentsociety2` in the pinned checkout; or `pip install 'git+https://github.com/fnstggl/agentsociety2@6e9fc2e79f89f65a3e3d0d7899e380f7394099be#subdirectory=packages/agentsociety2'` |

## One compatible environment (recreate commands)

Python floors: Concordia ≥3.12; agentsociety2 ≥3.11,<3.14; sworldmodel ≥3.11.
The unified engine environment therefore uses Python 3.12.

```bash
# 1. Environment (uv; /usr/bin/python3.12 available on this image)
uv venv /home/user/engine-env --python /usr/bin/python3.12

# 2. Pinned upstreams (local checkouts at the pinned SHAs are the primary
#    source in this workspace; the git+https forms above are the network
#    equivalent for a fresh machine)
uv pip install -p /home/user/engine-env/bin/python -e /home/user/concordia
uv pip install -p /home/user/engine-env/bin/python -e /home/user/agentsociety2/packages/agentsociety2

# 3. Environment pin required for upstream compatibility (source unchanged):
#    upstream declares mcp[cli]>=1.13.1; mcp 2.x removed mcp.server.fastmcp.
uv pip install -p /home/user/engine-env/bin/python "mcp[cli]>=1.13.1,<2"

# 4. Test-only plugins (upstream suite configs require them)
uv pip install -p /home/user/engine-env/bin/python pytest pytest-xdist pytest-timeout pytest-asyncio anyio

# 5. Verify triple coexistence (dummy creds satisfy agentsociety2's
#    import-time requirement; no network needed)
AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=http://localhost:9 \
  /home/user/engine-env/bin/python -c "import concordia, agentsociety2; import sys; sys.path.insert(0, '/home/user/SWORLDMODEL-GROUND-UP'); import sworldmodel; print('coexistence OK')"
```

Frozen package list of the working environment:
`docs/engine_migration/phase0_engine_env_freeze.txt` (ray 2.56.1,
litellm 1.95.0, mcp 1.29.0, numpy 2.5.1, pandas 3.0.5, …).

The SWORLDMODEL product package itself is stdlib-only (`dependencies = []`)
and additionally runs on the system Python 3.11 alongside the control plane.

## Credential map (risk R6)

| Layer | Variable(s) | Notes |
|---|---|---|
| SWORLDMODEL compiler (DeepSeek) | `DEEPSEEK_API_KEY` | injectable transport; offline tests never need it |
| AgentSociety dispatcher | `AGENTSOCIETY_LLM_API_KEY`, `AGENTSOCIETY_LLM_API_BASE`, `AGENTSOCIETY_LLM_MODEL` | required at import (dummy OK offline) |
| Concordia | model object injected by our code | deterministic/test models offline; live models wrapped per language_model providers |

## Upstream suite verification in this environment

- Concordia: `engine-env pytest /home/user/concordia -q --timeout=120` →
  560 passed core, failures confined to `examples/` (fork-introduced; see
  UPSTREAM_LOCK known_issues). Run with cwd inside the upstream checkout.
- AgentSociety2: `env AGENTSOCIETY_LLM_API_KEY=dummy … engine-env pytest
  /home/user/agentsociety2/packages/agentsociety2/tests -q` → 387 passed.
  Run with cwd inside the upstream checkout (their tests write scratch to cwd).

Job records: `.agent-run/jobs/phase0-*`. Baseline detail:
`docs/engine_migration/PHASE0_BASELINE.md`.

## Protected paths

`third_party/concordia/` and `third_party/agentsociety/` remain **reserved
and protected** (`.agent-run/UPSTREAM_PROTECTED_PATHS.json`) even though the
chosen method keeps no vendored trees: the protection prevents accidental
creation of divergent local copies. If a future phase must vendor (e.g., for
an air-gapped environment), follow the sanctioned import procedure recorded
in `UPSTREAM_PROTECTED_PATHS.json.import_procedure`.
