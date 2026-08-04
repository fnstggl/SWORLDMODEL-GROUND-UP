# Upstream Component Map — every upstream component used directly

> Gate J documentation set:
> [FINAL_ARCHITECTURE](FINAL_ARCHITECTURE.md) ·
> [RESPONSIBILITY_OWNERSHIP](RESPONSIBILITY_OWNERSHIP.md) ·
> [UPSTREAM_COMPONENT_MAP](UPSTREAM_COMPONENT_MAP.md) ·
> [IMPLEMENTATION_LOG](IMPLEMENTATION_LOG.md) ·
> [TEST_MATRIX](TEST_MATRIX.md) ·
> [SOCIETAL_SCALING_PATH](SOCIETAL_SCALING_PATH.md) ·
> [KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md) ·
> [NEXT_REALISM_PHASE](NEXT_REALISM_PHASE.md) ·
> [RUNBOOK](RUNBOOK.md)

Pins: Concordia `7779a4c9f96bad10816d88c54e4cb17d53ac5222`, AgentSociety 2
`6e9fc2e79f89f65a3e3d0d7899e380f7394099be`
(`third_party/UPSTREAM_LOCK.json`). Zero source patches
(`third_party/PATCHES.md`). Everything below is called from SWORLDMODEL
code **outside** the upstream packages; nothing upstream was copied,
subclassed-to-override-internals, or monkey-patched.

## 1. Concordia components (production entry point: `sworldmodel/backends/concordia_local/`)

All Concordia imports in production code live in exactly two modules —
`builder.py` (object construction) and `runner.py` (engine loop). The
constructors, parameters, and interfaces below were audited against the
pinned commit before use (`docs/engine_migration/audit_raw/CONCORDIA_AUDIT.md`).

| Upstream import path | Symbol(s) used | Where it enters our code | Role as built |
|---|---|---|---|
| `concordia.agents.entity_agent_with_logging` | `EntityAgentWithLogging` | `builder.py` | Every actor AND the game master are instances of this stock class |
| `concordia.components.agent` (as `agent_components`) | `concat_act_component.ConcatActComponent(randomize_choices=False)` | `builder.py` | Actor act component; deterministic choice order |
| 〃 | `constant.Constant` | `builder.py` | Actor private init data (`pre_act_label="Private setup"`); GM shared-setup constant |
| 〃 | `memory.ListMemory`, `memory.DEFAULT_MEMORY_COMPONENT_KEY` | `builder.py` (+ key reused by `checkpoint.py`) | Order-preserving per-actor and shared GM memory (embedder-free upstream backend; the builder refuses other memory backends) |
| 〃 | `observation.LastNObservations`, `observation.ObservationToMemory` | `builder.py` | Actor observation window + observation-to-memory recording |
| `concordia.components.game_master` (as `gm_components`) | `switch_act.SwitchAct` | `builder.py` | GM act component; every dispatch key supplied, so no model-improvising fallback exists |
| 〃 | `make_observation.MakeObservation(allow_llm_fallback=False)` + default key | `builder.py` | Observation delivery with the plan's initial observations pre-queued; LLM fallback disabled |
| 〃 | `next_acting.NextActingInFixedOrder`, `next_acting.NextActing` + default keys | `builder.py` | Acting order: deterministic fixed rotation, or model-chosen where the plan says so |
| 〃 | `next_acting.FixedActionSpec` | `builder.py` | The fixed free-form call to action per actor |
| 〃 | `event_resolution.EventResolution(event_resolution_steps=..., notify_observers=...)` + `EVENT_TAG`, `PUTATIVE_EVENT_TAG`, default key | `builder.py`, `runner.py` (tags for trace parsing) | Event resolution; **the final chain element is the SWORLDMODEL agency guard** (public constructor parameter — the guard seam). The upstream narrative-push step is refused by name |
| 〃 | `terminate.Terminate` + default key | `builder.py` | Explicit termination component |
| `concordia.typing.entity` (as `entity_lib`) | `free_action_spec` | `builder.py` | Action-spec construction for the fixed call to action |
| `concordia.environment.engines.sequential` | `Sequential` (`run_loop`) | `runner.py` | The unmodified upstream engine loop that runs every branch |
| Component-state API (methods on the objects above) | `entity.get_state()` / `entity.set_state()` | `checkpoint.py` (no direct `concordia` import — it operates on builder-produced objects) | Whole-branch checkpoint capture/restore through Concordia's own public per-entity state API |

Deliberately **not** used, with reasons recorded:

- `concordia.prefabs.simulation.generic.Simulation` /
  `make_checkpoint_data` / `load_from_checkpoint` — prefab-wrapper-only
  helpers; this backend builds entities directly from a validated plan, so
  the component-state API those helpers wrap is used instead
  (`checkpoint.py` module docstring; [FINAL_ARCHITECTURE.md](FINAL_ARCHITECTURE.md) §4).
- `event_resolution.maybe_inject_narrative_push` — refused by name in the
  planner/builder chain (narrative pushes would let the GM steer outcomes).
- Package-wide prefab enumeration (`get_package_classes()`) — never called;
  the upstream examples-only breakage at the pinned SHA
  (`UPSTREAM_LOCK.json.known_issues`) is therefore off our path.
- `AccountForAgencyOfOthers` — the upstream in-repo precedent for the guard
  seam is LLM-driven and unseeded-shuffle nondeterministic; our guard is
  deterministic code in the same public slot (`guard.py` docstring).

## 2. AgentSociety 2 components (production entry point: `sworldmodel/backends/agentsociety/`)

All `agentsociety2`/`ray` imports are lazy (inside the run call) so
`import sworldmodel` works without them. Interfaces audited in
`docs/engine_migration/audit_raw/AGENTSOCIETY_AUDIT.md` ("Option 2"
primitives — the public Ray-task layer that returns the per-agent
ok/error records and token deltas the stock society driver discards).

| Upstream import path | Symbol(s) used | Where it enters our code | Role as built |
|---|---|---|---|
| `agentsociety2.config.llm_dispatcher` | `init_dispatchers` | `branch_executor.py` | Ray runtime + per-process dispatcher bring-up (the one Ray owner per process segment) |
| `agentsociety2.agent.service_proxy` | `build_service_proxy(env=None, trace=...)` | `branch_executor.py` | Service injection for workers; `env=None` is a valid, audited configuration (Phase 2 finding #2 — branch agents never call `ask_env`) |
| `agentsociety2.agent.runner` | `create_agents_batch.remote`, `step_agent_batch.remote` | `branch_executor.py` | Workspace creation and branch execution as AgentSociety's own Ray tasks (single-branch batches) |
| `agentsociety2.registry` | `get_registry`, `get_agent_module_class` | `branch_executor.py` | Stock custom-module scanner resolution of the branch-agent class (driver-side check; workers resolve through the same stock scanner via `WORKSPACE_PATH`) |
| `agentsociety2.agent.base.agent` | `AgentBase` | `branch_agent_template.py` | The branch agent is a stock `AgentBase` subclass using the supported custom-agent contract (`create`/`from_workspace`/`step`/`to_workspace`); the executor materializes its SOURCE into `<workspace>/custom/agents/` and never imports it on the driver |
| Workspace layout (behavioral contract) | `config.json`, `AGENT.json`, `state/*` | `branch_agent_template.py`, `branch_executor.py`, `tests/engine_scale/` | Branch inputs/outputs and checkpoints persist as plain files in the stock per-agent workspace |
| `ray` | `ray.get`, `ray.wait`, `ray.is_initialized` | `branch_executor.py` | Submission window (bounded in-flight), harvest, adoption of an existing Ray runtime |

The scale harness (`tests/engine_scale/`, test-owned) drives the same
public path at 100–1,000 agents: `init_dispatchers` →
`build_service_proxy` → `create_agents_batch` → `step_agent_batch`, with
its own scripted `ScaleUnitAgent` materialized through the same stock
custom-agent scanner (`PHASE11_SCALE_EVIDENCE.md`, "What ran").

## 3. Test-side upstream usage

The engine test suites import additional upstream surfaces to PROVE
contracts, never to run production logic: `concordia.language_model`
(scripted/mock model base class), `concordia.document`,
`concordia.associative_memory`, `concordia.prefabs.*` (Phase 2 upstream
contract probes), and the upstream engines/components already listed
(`tests/engine_contracts/`, `tests/engine_baseline/baseline_helpers.py`).
Upstream's own suites were run unmodified in the engine environment as the
gate-A baseline (Concordia core 560 passed; AgentSociety2 387 passed —
`docs/engine_migration/PHASE0_BASELINE.md` §3).

## 4. Public-interface discipline

**No upstream private API is imported anywhere in production code.** Every
upstream reference above is a documented public class, function, default
key constant, or constructor parameter, inspected against the pinned
commit during the audit. Four related notes, recorded honestly:

1. **The one private-name reuse is SWORLDMODEL-internal, not upstream.**
   `backends/agentsociety/branch_executor.py` imports
   `manager._preflight`, `manager._result_from_runner`, and
   `manager._seeded_branch_scope` from `sworldmodel/counterfactuals/manager.py`
   — our own package. Recorded in DECISIONS (Phase 7 notes) as the
   deliberate reuse-over-duplication tradeoff: they are the single source
   of truth for request validation, result shaping, and per-branch
   seeding, and the completed `counterfactuals` package was not modified
   by later phases. The recorded trigger for promoting them to public
   names was "if churn appears"; no churn appeared through Phases 8–11,
   so the names stand.
2. **Upstream behavioral quirks are documented, not patched.** Where
   upstream public behavior required care, the accommodation lives on our
   side with the upstream file/line cited in our docstrings:
   `ListMemory.set_state` re-points its bank (we refill the original
   handle); `EntityAgent.set_state` swallows component exceptions (we
   enforce post-restore `get_state()` byte-equality);
   `Sequential.run_loop` re-observes the premise on resume (we pass
   `premise=''` + remaining budget); `stored_hashes` serializes a set
   (we canonicalize). All in `checkpoint.py`/`runner.py` docstrings and
   DECISIONS (Phase 8 notes).
3. **Upstream reporting seams are accepted as-is.** The corrupted-
   workspace driver-channel error names the agent, not the file (pinned
   `agentsociety2` behavior; finding F-R1,
   `OPERATIONAL_ROBUSTNESS_MATRIX.md`); recorded, not patched.
4. **The branch-agent template touches inherited `_`-prefixed AgentBase
   members.** `backends/agentsociety/branch_agent_template.py` reads and
   writes `_workspace_root`, `_bind_workspace`, `_current_time`,
   `_step_count`, and `_config` — underscore-named attributes/methods it
   INHERITS from upstream's `AgentBase`. Mitigation, verified against the
   pinned checkout: upstream's own subclass `PersonAgent`
   (`agentsociety2/agent/person.py`) uses the identical idiom
   line-for-line (e.g. `if self._workspace_root is None:
   self._bind_workspace(workspace_path)`, `self._step_count += 1`,
   `self._current_time = t`, reading `self._config` in its config
   helper); upstream's base-class comment explicitly anticipates
   subclass use ("Generic counters / state — set by restore / subclass
   restore", `agent/base/agent.py`); and no public accessors for these
   members exist upstream, so the underscore idiom IS the supported
   subclassing surface. Disclosed here rather than hidden behind a
   wrapper that would only rename the same access.

Continuous enforcement: the pinned checkouts are write-blocked in every
mode and integrity-checked on every validator run
(`third_party/UPSTREAM_LOCK.json.integrity_enforcement`;
`reviews/PHASE_0_2_BOUNDARY_REVIEW.md` C5 closed the original perimeter
gap). The Upstream Preservation reviewer verified: no upstream license
headers outside `third_party` docs, no upstream class redefinitions
anywhere in the repo, editable installs resolving to the pinned checkouts
(C1).
