# AgentSociety 2 Distributed-Layer Audit (engine-migration load-bearing)

> Raw report of the read-only AgentSociety 2 auditor (investigation agent), 2026-08-03.
> Synthesized into `../UPSTREAM_AUDIT.md`; kept verbatim as audit evidence.

**Repo state**: `/home/user/agentsociety2` is checked out exactly at `6e9fc2e` ("Add citation files for AgentSociety"), the stated fork base — `git log` HEAD = `6e9fc2e79f89f65a3e3d0d7899e380f7394099be`, remote `fnstggl/agentsociety2`. No local commits on top. VERIFIED.

**Path legend** (used below for brevity; all paths are absolute under this prefix):
`AS2` = `/home/user/agentsociety2/packages/agentsociety2/agentsociety2`
`PKG` = `/home/user/agentsociety2/packages/agentsociety2`

**Headline discrepancies vs. repo docs** (matters because CLAUDE.md was part of the briefing):
- There is **no TraceActor and no replay Ray actor** in the current code. Trace and replay are distributed, lock-free, per-process append sinks (`AS2/trace/sharded_writer.py:46-47`, `AS2/storage/replay_proxy.py:1-13`). `PKG/docs/architecture.rst:171` ("TraceActor is a resident Ray actor") is stale. VERIFIED.
- `Config.TRACE_WRITER_ASYNC` (`AS2/config/config.py:241-248`) is defined but never consumed by the trace writer (only set in `PKG/tests/conftest.py:15`); the sink is unbuffered `os.write` so there is nothing async to configure (`AS2/trace/sharded_writer.py:147-149`). VERIFIED (grep over the package found no other reader).
- Nothing writes `.runtime/logs/*`. `.runtime` exists only as an ignored directory name in `WorkspaceFS` (`AS2/agent/base/workspace_fs.py:16,104`); `AS2/agent/README.md:31-32` describes `.runtime/events.jsonl`, which no code writes. VERIFIED.
- `PKG/examples/advanced/01_custom_agent.py` is stale relative to the current API: it calls `super().__init__(id=..., profile=...)` (line 45) and `AgentSociety(agents=[...])` (lines 311, 333), but `AgentBase.__init__` is arg-less (`AS2/agent/base/agent.py:145-151`) and `AgentSociety` takes `agent_specs` (`AS2/society/society.py:130-143`). Do not copy that example. VERIFIED.
- Version skew: `PKG/pyproject.toml:7` says `2.8.4`; `AS2/__init__.py:48` says `__version__ = "2.8.3"`. VERIFIED.

---

## 1. AgentBase: construction and workspace

All VERIFIED unless noted.

**Construction model** (`AS2/agent/base/agent.py:9-19`): `__init__` is arg-less and only sets empty slots (:145-208). The real API:

- `create(workspace_path, profile, config)` — classmethod, **synchronous**, writes the initial workspace and returns nothing (:233-283). Writes:
  - `config.json` — static config, "write-once, never rewritten" (:250-253)
  - `AGENT.json` — initial metadata: `schema_version=1, agent_class, agent_id, name, profile, step_count=0, current_time, tick, visible_skills, activated_skills, disabled_skills, default_activated_skills, initialized_at` (:256-283)
  - empty dirs `state/` and `memory/` (`STANDARD_WORKSPACE_DIRS`, :62, :248-249)
- `from_workspace(workspace_path, service_proxy)` — async classmethod: `agent = cls(); await agent.restore(...)` (:285-303).
- `restore(workspace_path, service_proxy)` — the real init (:305-416): reads `config.json` + `AGENT.json`; sets `_id/_profile/_name/_config`; `_bind_services(proxy)` (:344, defined :214-227 — binds env router, default LLM client, model name); `_setup_skill_runtime` (:345); `_bind_workspace` (:346, defined :618-647 — builds `WorkspaceFS` + per-agent `JsonlTraceWriter` backed by a process-local `ShardedAppendSink` from `proxy.trace`, :649-664); restores visible/activated skills, `step_count`, `current_time`, `initialized_at` (:356-384); re-scans skill sources into the process-global registry (:394-416).
- `to_workspace(workspace_path)` — abstract (:423-426). `PersonAgent.to_workspace` writes only `AGENT.json` via `persist_agent_json` (`AS2/agent/person.py:180-197`); `config.json` is never rewritten. `AGENT.json` content built by `build_agent_json` (`AS2/agent/base/agent.py:774-812`), enriched by PersonAgent with skills + memory pointers (`AS2/agent/person.py:201-221`).

**What persists / how reconstruction works**: durable per-agent state is exactly the workspace files — `AGENT.json` (counters, time, profile, skill sets), `config.json` (static), `MEMORY.md`, `memory/episodes.jsonl`, `memory/state.json` (`AS2/agent/memory.py:18-21`), `state/todos.json` + `state/todos_archive.jsonl` (`AS2/agent/base/todo.py:21,314`). Reconstruction = `from_workspace` re-reading those files each time; agents are stateless records between calls ("workspace-bound stateless records", `AS2/agent/runner.py:5-11`).

**Caveat**: `persist_agent_json` uses `WorkspaceFS.write_text` which is a plain `Path.write_text` — **not atomic** (`AS2/agent/base/agent.py:829-834`; `AS2/agent/base/workspace_fs.py:134-152`). Contrast: society checkpoints use `atomic_write_text` (tmp + `os.replace`, `AS2/storage/workspace_state.py:19-33`). A crash mid-write can corrupt one agent's `AGENT.json` (see E).

**Workspace naming**: `<workspace_root>/agent_<id:04d>`, where `workspace_root = run_dir/agents` (`AS2/agent/runner.py:97-103`; `AS2/society/society.py:174-179,314-316`).

## 2. Agent step execution as Ray tasks

All VERIFIED. File: `AS2/agent/runner.py`.

- Public tasks are **sync wrappers** over async cores, because Ray 2.x forbids `@ray.remote` on `async def` regular tasks (:31-36, :264-267). Each wrapper runs `asyncio.run(<async core>)` (:304-311).
- `step_agent_batch(agent_ids, workspace_root, agent_class_name, tick, t, service_proxy)` (:267-311): per agent — `from_workspace → step(tick,t) → to_workspace → close`, all inside a per-agent `try/except` returning `{"id", "ok": True, "summary"}` or `{"id", "ok": False, "error": repr(e)}` (:119-131). All agents in a batch run **concurrently via `asyncio.gather`** (:133-140). Return value is `{"results": [...], "token_stats": service_proxy.take_token_stats()}` (:304-311).
- `create_agents_batch(items, ...)` writes initial workspaces via `cls.create` without instantiating agents in the driver (:143-152, :314-336). Note the async core creates agents **sequentially** in a loop.
- `questionnaire_agent_batch` mirrors step batching for surveys (:155-215, :380-429); `query_agent_task` is a single-agent ask/intervene/dump op, "not on the hot path" (:218-261, :339-377).
- Agent class is resolved **inside the task** via the module registry, with fallback to `getattr(agentsociety2.agent, name)` (:67-94).
- The decorator degrades gracefully: if `import ray` fails, `_ray_remote` returns the plain function (:52-57) — but callers use `.remote(...)`, so Ray-less operation still breaks (see E).
- Driver side (`AS2/society/society.py:581-635`): each tick chunks `agent_ids` into `batch_size` chunks, submits one `step_agent_batch.remote` per chunk (:602-614), `await`s all refs (`await ref`, :648-651), folds token deltas (:618-628).

**Failure-isolation gap (critical for the branch-executor use case)**: in `AgentSociety.step`, the per-agent `results` returned by the batch are **discarded** — only `token_stats` is consumed (`AS2/society/society.py:621-628`). A failed agent step is not logged by the driver and not persisted (on exception, `to_workspace` is skipped — `AS2/agent/runner.py:122-131`). The only durable record of the failure is the error-status trace span emitted when `agent.step`'s `trace_span` context exits with an exception (`AS2/trace/sharded_writer.py:269-276`; `AS2/agent/person.py:398-406`). The questionnaire path, by contrast, aggregates and logs failures (`AS2/society/society.py:780-807`). VERIFIED.

## 3. ServiceProxy

All VERIFIED. File: `AS2/agent/service_proxy.py`.

- `ServiceProxy` is a dataclass of **serializable handles only**: `env` (in-process `RouterBase` or `EnvRouterProxy`), `llm: LLMClients {coder, default, embedding|None}`, `trace: TraceProxy|None`, `replay: ReplayProxy|None`, `run_dir` (:101-120). Protocols `EnvLike/LLMClientLike/TraceLike/ReplayLike` define the contract (:26-81).
- `take_token_stats()` drains all three LLM clients' deltas and merges them (:122-135) — this is how Ray tasks carry token usage back.
- Factory `build_service_proxy(env, *, run_dir, trace, trace_dir, replay, replay_db_path, replay_sample_rate)` (:171-279): builds one `LLMClient` per configured role (:230-236; embedding only if configured, :143-150); trace wiring accepts a pre-built `TraceProxy`, `True` (build one at `run_dir/trace`), or `False` (:241-252); replay wiring likewise with `ReplayProxy` at `run_dir/replay` (:257-271).
- Construction/passing in production: the CLI builds one `TraceProxy` + one `ReplayProxy`, hands them to **both** the env-router actor and `build_service_proxy` so agents and env share dirs (`AS2/society/cli.py:505-540`); the proxy is passed into every Ray task by `AgentSociety` (`AS2/society/society.py:596-614`).
- If you do **not** inject a proxy, `AgentSociety._resolve_service_proxy` builds one with **`trace=False`** (`AS2/society/society.py:341-355`) — tracing requires injecting your own proxy.

## 4. LLM dispatch

All VERIFIED. File: `AS2/config/llm_dispatcher.py` (plus `AS2/config/config.py`).

- **No module-global router/pool.** `LLMClient` is a serializable dataclass of `(model_name, base_url, api_key, model_type)`; on first `call()` per event loop it builds its own litellm `Router` + `AdaptiveSemaphore`, rebuilt if the loop changes; `__getstate__` strips runtime so every deserialized copy rebuilds fresh (:363-435). Router: single `openai/<model>` deployment, `cache_responses=True`, `num_retries=0` (litellm retries disabled; dispatcher's retry loop is authoritative) (:296-318).
- **Roles**: `default` / `coder` / `embedding`, connection params from `get_llm_connection(role)` with coder/embedding falling back to default key/base (`AS2/config/config.py:538-559`; fallbacks :138-208). `build_client_for_role(role)` (:339-355).
- **Concurrency control**: `AdaptiveSemaphore` — TCP-style AIMD per process, initial = `Config.LLM_RAY_CONCURRENCY` (env `AGENTSOCIETY_LLM_RAY_CONCURRENCY`, default 16; `AS2/config/config.py:317-328`), `min=1`, **no max cap** (:419-431); decrease ×0.7 on >10% rate-limit/slow round, cooldown 3 rounds, additive/doubling increase capped at step 16 (:134-288); latency-slow detection via rolling P25 baseline × `LLM_LATENCY_DEGRADE_FACTOR` (default 4.0) and optional absolute `LLM_SLOW_LATENCY_MS` (`AS2/config/config.py:257-300`).
- **Retry/timeout**: per-request timeout `AGENTSOCIETY_LLM_REQUEST_TIMEOUT` default 60 s (:50-56); `call()` default `max_retries=3` (4 attempts), exponential backoff (1s→60s cap) only for rate-limit-like errors, immediate retry otherwise; exhaustion raises `LLMDispatchError(rate_limit_like=...)` (:459-543). Rate-limit detection includes litellm `RateLimitError`, `RouterRateLimitError`, and string heuristics (:75-88). Streaming is explicitly unsupported (:470-473).
- **Env vars at import**: importing `agentsociety2.config.config` **raises `ValueError` at module import if `AGENTSOCIETY_LLM_API_KEY` is unset** (`AS2/config/config.py:490-500`). `AGENTSOCIETY_LLM_API_BASE` defaults to `https://api.openai.com/v1` (:109-111) so its check only fires if explicitly set empty. This propagates to bare `import agentsociety2`: `agentsociety2/__init__.py` → `.agent` → `agent/base/agent.py:44` → `env/router_base.py:62` → `agentsociety2.config`. VERIFIED chain. Default model `gpt-5.5` (:123).
- **Token accounting**: per-`LLMClient` dict `{model: {calls, input, output}}` from `usage.prompt_tokens/completion_tokens` (:437-447); drained by `take_token_stats` (:449-453); merged per batch into `AgentSociety._token_stats` (`AS2/society/society.py:619-628`). Two gaps: (a) `_token_stats` is a private field — never logged, never written to `pid.json`, no public accessor (grep over package; only writers found); (b) the **env actor's** LLM usage is not included — it lives in the actor's own clients, readable via `RouterBase.get_token_usages` (`AS2/env/router_base.py:780-802`) but `EnvRouterProxy` does not forward that method (`AS2/env/env_router_proxy.py:46-97`). VERIFIED.
- **Ray init lives here**: `init_dispatchers()` calls `ray.init(ignore_reinit_error=True, include_dashboard=False, num_cpus=Config.LLM_RAY_MAX_WORKERS, object_store_memory=1_000_000_000, job_config=..., runtime_env=None)` (:570-603); job config copies all non-`UV*` driver env vars plus a PYTHONPATH containing the package install root into workers (:551-567); uv runtime-env packaging disabled (:58-59, :584-602). `shutdown_dispatchers()` is a no-op (:606-609).

## 5. Environment layer

All VERIFIED.

- **`EnvBase`** (`AS2/env/base.py:364-573`): metaclass `EnvMeta` collects `@tool`-decorated methods into `_registered_tools/_readonly_tools/_tool_kinds` (:339-361); instance builds an MCP `ToolManager` and OpenAI function schemas, with readonly subset (:427-453). `is_concurrency_safe()` classmethod defaults `False` (:385-399). Lifecycle: `init/step/close` (:555-573; `step` raises `NotImplementedError` in the base). Workspace persistence hooks: `_bind_workspace`, `to_workspace` (default no-op), `restore` (default returns False), `from_workspace` classmethod (:581-619). Declarative replay: `_agent_state_columns` / `_env_state_columns` auto-register `{prefix}_agent_state` / `{prefix}_env_state` tables + datasets (:635-786) with write helpers (:788-836).
- **`@tool(readonly, name, description, kind)`** (`AS2/env/base.py:103-316`): validates observe (≤1 param besides self) / statistics (0 params) / readonly constraints (:124-162); wraps sync and async functions to append call records (`function_name, kwargs, return_value, exception_occurred, exception_info, timestamp`, plus trace ids) to `self._tool_call_history` (:211-308).
- **`RouterBase`** (`AS2/env/router_base.py:166-453`): holds env modules, coder + default `LLMClient`s (injected via `llm_clients_spec` or built from config, :195-211), abstract `ask()` (:340-360), `init` (module init then `from_workspaces` restore, :362-374), `step` (gathers module steps, :376-383), `bind_env_workspaces(root, module_types)` → `<root>/<module_type>` per module (:392-402), `to_workspaces`/`from_workspaces` with per-module failure isolation and loud partial-resume errors (:404-453). Env-side LLM spans (`llm.completion`) emitted through an injected sink and ContextVar-carried per-ask trace context (:238-315).
- **Routers**: `CodeGenRouter` (default in production), `ReActRouter`, `PlanExecuteRouter`, `TwoTierReActRouter`, `TwoTierPlanExecuteRouter`, `SearchToolRouter` (`AS2/env/__init__.py:43-67`). `CodeGenRouter.ask` runs a pipeline `InitStage → CodeStage → SummaryStage → ObserveFinalStage` (`AS2/env/router_codegen.py:1642-1687`); code providers chain Predefined → Cache (FAISS/embedding) → LLM (:1579-1584); generated code passes an AST safety validator (forbidden nodes, dangerous builtins/imports, `while True` without break; :1010-1091) and executes with restricted builtins/whitelisted modules (:1093-1139); exec is serialized behind `_execute_lock` unless **all** modules declare `is_concurrency_safe()` (:1563-1598).
- **Ray actor**: `get_env_router_actor_class(max_concurrency)` builds and caches a `ray.remote(max_concurrency=...)` actor class owning a `CodeGenRouter` (`AS2/env/env_router_actor.py:27-180`). The actor instantiates env modules from the registry inside its own process (:78-92), binds env workspaces to `<run_dir>/env/<module_type>` (:93-100), takes injected `LLMClient`s, `ReplayProxy`, `TraceProxy` (:53-113), and exposes `init/to_workspaces/from_workspaces/set_current_time/set_replay_writer/ask/get_world_description/step/close` (:115-174). `max_concurrency = Config.ENV_ACTOR_MAX_CONCURRENCY` (default 8) only when every module is concurrency-safe, else 1 (`AS2/society/cli.py:492-499`; `AS2/config/config.py:249-255`).
- **`EnvRouterProxy`** (`AS2/env/env_router_proxy.py:17-97`): same method surface as an in-process router; forwards to the actor; `set_current_time`/`set_replay_writer` are fire-and-forget `.remote` calls (:46-63); carries `env_skill_dirs` resolved from the registry so env-provided agent skills stay discoverable across the Ray boundary (:22-31, :100-144).
- **How agents call ask**: `AgentBase.ask_env(ctx, message, readonly, template_mode, trace_id, parent_span_id)` merges an identity overlay `{id, agent_id, person_id}` and awaits `self._env.ask(...)` (`AS2/agent/base/agent.py:463-506`); PersonAgent's step issues an initial `<observe>` ask (`AS2/agent/person.py:425-458`), and the ReAct tool loop can issue further `ask_env` calls.

## 6. Tracing

All VERIFIED. Files: `AS2/trace/sharded_writer.py`, `AS2/trace/span.py`.

- **No central actor and no background thread.** `TraceProxy` is just `{trace_dir}` (:78-89). Every writer process builds its own `ShardedAppendSink` (`build_local_sink`, :163-171): 256 shard files `trace_<xx>.jsonl` keyed by `trace_id[:2]`, appended via `os.open(O_APPEND)+os.write`; records are value-capped under PIPE_BUF so single writes are kernel-atomic; no locks (:49-160).
- **Span API**: `JsonlTraceWriter` per agent (created in `_bind_workspace`, `AS2/agent/base/agent.py:635-639`) emits OTel-shaped JSONL: `resource{service.name, agent.id}, scope, trace_id, span_id, parent_span_id, name, kind, start/end_time_unix_nano, status{code,message}, attributes (+event.sequence), events` (:299-341). Context-manager `trace_span` records `status=error` + message on exception (:248-280). When no sink is bound, span API works but records are dropped (:179-198).
- **What gets recorded**: agent side — `agent.init`, `agent.step`, `agent.ask`, `react.loop`, `react.turn`, `react.tool` spans with attributes like step count, hook counts, memory episode counts, output summaries (`AS2/agent/person.py:365-521`; `AS2/agent/base/agent.py:1604-1742`). Env side — `llm.completion` spans for codegen/summary calls, parented into the asking agent's trace (`AS2/env/router_base.py:263-315`). Attribute string values are truncated (~PIPE_BUF/2) — full payloads are expected in replay, not trace (:49-75).
- **Where**: `run_dir/trace/trace_<xx>.jsonl` (CLI wiring `AS2/society/cli.py:505-510`; default `run_dir/"trace"` in `build_service_proxy`, `AS2/agent/service_proxy.py:245-250`).

## 7. Replay / storage

All VERIFIED.

- **Writer**: `ReplayProxy` = `{replay_dir, enabled}` dataclass; lazily builds a process-local `ReplaySink`; pickling drops the sink (`AS2/storage/replay_proxy.py:23-97`). `ReplaySink` appends JSONL rows to `{table}.{shard:02x}.jsonl` (shard = `crc32(line) % 256`), each shard write guarded by `fcntl.flock` because rows can exceed PIPE_BUF (`AS2/storage/replay_sink.py:1-193`); rows normalized (datetime→ISO, dict/list→JSON string) (:65-76).
- **Catalog**: `register_table(TableSchema)` / `register_dataset(ReplayDatasetSpec, columns)` merge idempotently into `_schema.json` under flock (:199-244). `ColumnDef`/`TableSchema` in `AS2/storage/table_schema.py`; dataset specs in `AS2/storage/replay_metadata.py`.
- **`ReplayWriter`** is now only a back-compat alias over `ReplaySink` that strips a trailing `.db` — SQLite is gone (`AS2/storage/replay_sink.py:265-280`).
- **Reader**: `ReplayReader` builds DuckDB views over the JSONL shards from `_schema.json` (`AS2/storage/replay_reader.py:1-120`), with legacy dict shapes for the backend.
- **Framework tables still written**: only `agent_profile` — registered and written once at society init (`AS2/society/society.py:241-309`, names from `AS2/storage/replay_metadata.py`). Legacy SQLModel classes (`AgentProfile`, `AgentStatus`, `AgentDialog`) remain in `AS2/storage/models.py` for reading old DBs; new runs don't write `agent_status`/`agent_dialog` (no writer call sites; the CLAUDE.md statement matches code here). Env modules add their own `{prefix}_agent_state` / `{prefix}_env_state` tables (`AS2/env/base.py:671-786`).

## 8. Society orchestration and CLI

All VERIFIED.

- **`AgentSociety`** (`AS2/society/society.py:99-213`): record-based; holds `agent_specs` (`{"id","profile","config"}`), `agent_ids`, env router handle, `service_proxy`, `batch_size` (default `Config.BATCH_SIZE` = env `AGENTSOCIETY_BATCH_SIZE`, default 256; `AS2/config/config.py:330-343`), `run_dir`. `init()` = `init_dispatchers` (Ray) → resolve proxy → replay profile persistence → batch-create workspaces → `env_router.init(t)` → write `SOCIETY.json` once (:360-390). `step(tick)` = push clock → fan out batches → env.step → advance clock → `to_workspace` checkpoint (:581-635). `run(num_steps, tick)` loops with a `_should_terminate` check (:637-646). `ask`/`intervene` go through `AgentSocietyHelper` which reconstructs target agents locally in the driver (:656-713; helper at `AS2/society/helper.py`). `run_questionnaire` fans out `questionnaire_agent_batch` (:715-818).
- **Checkpointing**: `SOCIETY.json` — immutable full snapshot (schema_version, agent_class_name, agent_specs, env_module_types, env_kwargs, batch_size, steps_hash), written once, atomic (:436-455). `SOCIETY_STEP.json` — per-step scalars (current_time, step_count, completed_step_count, terminated), atomic (:457-469). `AgentSociety.from_workspace(run_dir, env_router=..., service_proxy=...)` validates schema and rebuilds, skipping re-creation (:482-569).
- **InitConfig/StepsConfig** (`AS2/society/models.py`): `InitConfig{env_modules[], agents[], codegen_router}` (:52-60); steps = `run|ask|intervene|questionnaire` discriminated union with pydantic validation (:63-141); `start_t` ISO required (:127-141).
- **CLI** (`AS2/society/cli.py`): entry `python -m agentsociety2.society.cli` / console script `agentsociety` (`PKG/pyproject.toml:85-87`). Args: `--config` (required), `--steps` (required), `--run-dir` (default "."), `--experiment-id`, `--log-level`, `--log-file` (optional flag; "required" for background runs is a convention documented in help text and CLAUDE.md, not enforced — :815-819), `--replay-disable`, `--batch-size`, `--resume` (:782-846). Early env validation exits 1 if `AGENTSOCIETY_LLM_API_KEY` missing (:59-81). `pid.json` in run_dir tracks `pid, status(running/completed/failed), start_time/end_time, experiment_id, simulation_time, step_count`, updated every second during RunSteps (:283-319, :636-657). Artifacts: `run_dir/artifacts/ask_step_<i>_<simtime>.md`, `intervene_step_...md` (YAML front matter + markdown), `questionnaire_step_...json` (:659-739). Agent `kwargs` are split into config keys (`AGENT_CONFIG_KEYS`: max_react_turns, enable_memory, enable_todo_list, disabled_skill_ids, default_activated_skill_ids, extra_skill_paths) vs profile (:42-56, :250-272). Single agent class per society enforced (:274-281). Custom module scan walks up from run_dir to the nearest ancestor containing `custom/` (:441-453). Per-top-level-step exceptions are caught, logged, and **the run continues to the next step** (:751-758).

## 9. Failure isolation

- Per-agent step failure: caught in the task, batch survives, error dict returned (`AS2/agent/runner.py:130-131`) — but the driver **discards step results** (`AS2/society/society.py:621-628`), so failures are silent except for error-status trace spans. Failed agent's `to_workspace` is skipped, so its workspace stays at the previous step's state. VERIFIED (details in section 2).
- Whole-task failure (worker crash, serialization error): the exception propagates through `asyncio.gather` in `society.step` → aborts that tick → the CLI catches it at the top-level-step boundary, logs, updates pid.json, and proceeds to the next step (`AS2/society/cli.py:751-758`). No batch-level retry in repo code; runner tasks are declared with bare `ray.remote(fn)` and no options (`AS2/agent/runner.py:52-57`; grep confirmed no `max_retries`). INFERRED (Ray defaults, not repo code): Ray retries tasks up to 3 times only on worker-process death, not on Python exceptions (`retry_exceptions=False` default).
- Env module failures: single-module restore/persist failures are isolated and logged loudly, other modules continue (`AS2/env/router_base.py:404-453`). Env actor death is not handled specially — subsequent `ask` calls would raise `RayActorError` into agent steps (INFERRED from absence of any handling; no reconnect/restart logic found).
- Questionnaire failures: isolated per agent, aggregated, logged with counts (`AS2/society/society.py:780-807`). VERIFIED.
- LLM failure: `LLMDispatchError` after retries propagates into `agent.step` → per-agent error dict. A distinction the code makes: `rate_limit_like` flag on the error (`AS2/config/llm_dispatcher.py:67-73`). Note for accounting: an `LLMDispatchError` is a provider failure, not a property of the simulated agent — the step-results discard means the framework will not say which it was unless you read trace shards or capture results yourself.

## 10. Checkpointing / resume / shutdown

All VERIFIED.

- Three independent layers, all file-based: (1) agent workspaces (every step via `to_workspace` in the task, `AS2/agent/runner.py:124`); (2) env module workspaces `run_dir/env/<module_type>` (every society step via `env_router.to_workspaces()`, `AS2/society/society.py:418-434`; restore inside actor `init`, `AS2/env/env_router_actor.py:115-119`, `AS2/env/router_base.py:362-374`); (3) society scalars `SOCIETY.json` + `SOCIETY_STEP.json` (atomic; section 8).
- CLI `--resume` (`AS2/society/cli.py:379-432,542-553`): re-reads checkpoint, restores clock/step cursors, skips completed top-level steps and completed ticks inside a partially-done RunStep; env types/kwargs come from the checkpoint (not the config file) to avoid drift; `steps.yaml` drift detected via sha256 with a warning (:376-377, :404-413). Ask/Intervene/Questionnaire steps recorded via `mark_step_completed` (`AS2/society/society.py:471-480`; called `AS2/society/cli.py:749`).
- Shutdown: `society.close()` closes the env router (actor → modules), closes the replay sink if it owns the proxy, `shutdown_dispatchers()` is a no-op (`AS2/society/society.py:392-413`). **`ray.shutdown()` is never called anywhere** (grep verified) — the local Ray cluster dies with the driver process. Trace sinks need no close (fds reclaimed at process exit, :399-401).

## 11. Concurrency limiting

All VERIFIED (mechanisms), with one INFERRED Ray detail.

Layers, outermost first:
1. **Ray CPU budget**: `ray.init(num_cpus=Config.LLM_RAY_MAX_WORKERS)` (default = logical CPU count; env `AGENTSOCIETY_LLM_RAY_MAX_WORKERS`) caps concurrent `step_agent_batch` tasks per tick (`AS2/config/llm_dispatcher.py:589-596`; `AS2/config/config.py:304-315`). INFERRED: each task consumes 1 CPU by Ray default (no `num_cpus` override on the tasks).
2. **Batching**: tasks per tick = `ceil(N / batch_size)`; `batch_size` default 256 (`AS2/society/society.py:602-614`; `AS2/config/config.py:330-343`, with guidance in the docstring and CLI help `AS2/society/cli.py:825-835`).
3. **In-task fan-out**: all agents in a batch run concurrently under `asyncio.gather` — unbounded within the batch (`AS2/agent/runner.py:133-140`).
4. **Per-process LLM AIMD semaphore**: the real global brake — every process (each Ray worker, the env actor, the driver) starts at `LLM_RAY_CONCURRENCY` (16) in-flight LLM calls and adapts, uncapped upward, min 1 (`AS2/config/llm_dispatcher.py:411-435`). Note this is per-process, so aggregate initial concurrency ≈ 16 × (#active worker processes + actor + driver).
5. **Env actor concurrency**: `max_concurrency=1` unless all modules concurrency-safe, then `ENV_ACTOR_MAX_CONCURRENCY` (8) (`AS2/society/cli.py:492-499`); plus in-router `_execute_lock` for codegen exec (`AS2/env/router_codegen.py:1563-1598`).

## 12. Ray usage summary

- **Init**: local, in-process `ray.init` with no address — starts a single-node cluster (`AS2/config/llm_dispatcher.py:579-603`); dashboard off; 1 GB object store; env-var passthrough job config. Nothing in the repo configures multi-node; `RAY_ADDRESS`-style cluster attach would be Ray-default behavior (INFERRED).
- **Long-lived actor**: only `EnvRouterActor` (`AS2/society/cli.py:512-523`). Everything else is stateless tasks: `step_agent_batch`, `create_agents_batch`, `questionnaire_agent_batch`, `query_agent_task` (`AS2/agent/runner.py:59-64`).
- **No Ray for trace/replay/LLM** — per-process sinks and clients (sections 3, 6, 7). The "trace writer and replay writer run as long-lived shared Ray actors" line in `/home/user/agentsociety2/CLAUDE.md` is stale relative to this code. VERIFIED.
- **Resource assumptions**: shared filesystem between driver and workers (workspaces/trace/replay are plain paths — true for single-node; the code resolves run_dir to absolute precisely because worker cwd differs, `AS2/society/society.py:169-179`). Multi-node would break workspace reads unless the run_dir is on shared storage (INFERRED from the design; no NFS/S3 handling exists).

---

# A. Narrowest supported way to run N independent opaque Python jobs

Requirements recap: one complete external simulation per job (~minutes), bounded concurrency, tracing, failure isolation, token/runtime accounting, result collection, **no source modifications**.

**Ranked options** (1 = recommended):

**Option 1 — custom `AgentBase` subclass whose `step()` runs the job, driven by `AgentSociety`.** Most stock code exercised; small custom surface (one class + one trivial env module).
- Job = agent: `create()` writes the job spec into the workspace; `step(tick, t)` runs the opaque job and writes results/artifacts into the workspace; `to_workspace()` persists metadata. Contract: `AS2/agent/base/agent.py:233-303,423-442`. You may inherit the concrete base `create/from_workspace/restore` and override only `to_workspace/ask/step` (PersonAgent does exactly this — `AS2/agent/person.py:50-54,120-134`).
- Stock machinery for free: workspace creation via `create_agents_batch`, per-tick fan-out via `step_agent_batch`, per-agent failure isolation, `asyncio.gather` in-batch concurrency, per-task token deltas (`AS2/agent/runner.py:109-140,304-311`), AIMD LLM gating if the job calls LLMs through `self.acompletion` (`AS2/agent/base/agent.py:512-539`), per-agent trace writer bound automatically in `restore→_bind_workspace` (`AS2/agent/base/agent.py:618-647`), society checkpoint/resume.
- Wiring without touching source: (i) put the class file under `<workspace_root>/custom/agents/yourjob.py` (scanner requires an `AgentBase` subclass defined in the file — `AS2/backend/services/custom/scanner.py:52-117`); (ii) ensure Ray workers can resolve it: workers re-run registry lazy-load, which finds `custom/` via the `WORKSPACE_PATH` env var or a cwd-ancestor scan (`AS2/registry/base.py:65-96,170-196`); driver env vars (including `WORKSPACE_PATH`) propagate to workers via the job config (`AS2/config/llm_dispatcher.py:551-567`). Set `WORKSPACE_PATH` explicitly — the cwd walk is unreliable because worker cwd differs (`AS2/society/society.py:169-173`).
- Env router: `AgentSociety` requires one (`AS2/society/society.py:130-149`); production-shaped choice is the env actor + `EnvRouterProxy` over a trivial concurrency-safe `EnvBase` module (registered the same `custom/envs/` way), giving `max_concurrency` up to 8 (`AS2/society/cli.py:492-523`). An in-process `RouterBase` inside the `ServiceProxy` must cross the Ray pickle boundary and carries `asyncio.Lock`/ContextVar state (`AS2/env/router_base.py:232-241`) — treat that as unsupported for the Ray path (INFERRED: serialization risk; tests only use in-process routers without Ray, `PKG/tests/framework/test_society_resume.py:1-5`).
- Concurrency bound: `batch_size` + `AGENTSOCIETY_LLM_RAY_MAX_WORKERS` (jobs in flight ≤ min(ceil(N/batch_size), num_cpus) × batch_size; within a batch all run concurrently, so for ~minutes-long CPU-bound jobs set `batch_size=1` and `num_cpus` = desired parallelism — the in-batch gather is unbounded, `AS2/agent/runner.py:133-140`).
- **Caveats** (both verified above): `society.step()` discards per-agent ok/error/summary (`AS2/society/society.py:621-628`) — collect results from each job's workspace files instead (that is the supported result channel; see B); tracing requires injecting `build_service_proxy(..., trace=True/TraceProxy)` because the society's self-built proxy sets `trace=False` (`AS2/society/society.py:347-352`); token totals end up in the private `society._token_stats`.

**Option 2 — direct use of the runner + service-proxy primitives (no `AgentSociety`).** Narrowest surface for *result collection*; slightly more orchestration owned by the caller, but every call is a public API:
`await init_dispatchers()` (`AS2/config/llm_dispatcher.py:570-603`) → `build_service_proxy(env, run_dir=..., trace=..., replay=...)` (`AS2/agent/service_proxy.py:171-279`) → `create_agents_batch.remote(...)` → `step_agent_batch.remote(ids, workspace_root, "YourAgent", tick, t, proxy)` → each return gives `{"results": [{"id","ok","summary"|"error"}], "token_stats": {...}}` directly (`AS2/agent/runner.py:267-311`). You get exactly the failure-isolation and token-accounting records the society throws away, and you choose the batch/parallelism policy. You lose: SOCIETY.json checkpoint/resume, questionnaire/ask plumbing, pid.json/artifacts. Same custom-agent registration requirement as Option 1.

**Option 3 — society with a custom env module running the jobs inside `@tool` methods.** Not recommended: all tool execution funnels through the single `EnvRouterActor` process, serialized by `_execute_lock` unless all modules are concurrency-safe, and even then capped at `max_concurrency` ≤ `ENV_ACTOR_MAX_CONCURRENCY` (8) in **one** process (`AS2/env/env_router_actor.py:27-44`; `AS2/env/router_codegen.py:1563-1598`; `AS2/society/cli.py:492-499`). Minutes-long jobs would monopolize the actor and stall every agent's `ask_env`. It also routes job invocation through LLM codegen with an AST sandbox that forbids `open`/imports (`AS2/env/router_codegen.py:1010-1139`) — actively hostile to opaque jobs.

**Verdict**: Option 1 for checkpoint/resume and the most stock path; Option 2 if per-job ok/error/token results in the driver matter more than resume. Both viable without source changes; Option 3 is not fit for purpose.

# B. Arbitrary opaque per-job artifacts in workspaces

**Yes.** VERIFIED:
- Each agent owns `<run_dir>/agents/agent_<id:04d>/` with framework-reserved files limited to `config.json`, `AGENT.json`, `state/`, `memory/` (`AS2/agent/base/agent.py:61-62,246-283`); `restore` reads only `config.json` + `AGENT.json` (:323-329), so extra files are inert to the framework.
- Supported write paths: (a) the sandboxed `WorkspaceFS` (`write_text/append_text`, UTF-8 text only, path-escape guarded — `AS2/agent/base/workspace_fs.py:106-173`); (b) plain `pathlib` I/O against `self.workspace_root_path()` in agent code (`AS2/agent/base/agent.py:683-691`) — the workspace dir is wholly agent-owned, and nothing scans or validates its contents.
- For a **binary blob** (e.g., a Concordia checkpoint): `WorkspaceFS` has no binary API, so write it directly, e.g. `(self.workspace_root_path() / "state" / "concordia_checkpoint.pkl").write_bytes(...)`. `state/` is created by `create()` and is the intended dynamic-state home (:248-249). Files under `.runtime/` are additionally hidden from workspace listing/grep tools (`AS2/agent/base/workspace_fs.py:104,268-284`).
- On disk: `<run_dir>/agents/agent_0001/state/<blob>`; survives resume because agent workspaces are never rewritten wholesale (only `AGENT.json` is), and `create_agents_batch` is skipped on resume (`AS2/society/society.py:565-568`).
- For *indexed* artifacts, register a replay dataset and write rows via `proxy.replay.register_table/register_dataset/write_batch` (`AS2/storage/replay_proxy.py:61-91`) — but for large binary blobs the workspace file is the right place (replay rows are JSONL).

# C. Packaging / dependencies

All VERIFIED from files:
- **Python**: `requires-python = ">=3.11,<3.14"` (`PKG/pyproject.toml:10`); mypy pinned to 3.11 semantics (:197-198).
- **License**: Apache-2.0, both repo root and package (`LICENSE`, `PKG/LICENSE`; `PKG/pyproject.toml:11`).
- **uv workspace**: root `pyproject.toml` declares `members = ["packages/agentsociety2"]` only — v1 `packages/agentsociety`, community, and benchmark are **not** workspace members in this fork; `agentsociety2 = { workspace = true }`; default index is the Tsinghua PyPI mirror (root pyproject lines 1-15). `uv.lock` present at root.
- **Key deps** (`PKG/pyproject.toml:49-83`): `ray>=2.0.0; sys_platform != 'win32'` (no Ray on Windows — the Ray-based society path cannot work there), `litellm>=1.83.7`, `duckdb>=1.4.0`, `sqlmodel>=0.0.16`, `sqlalchemy[asyncio]`, `pydantic>=2.10.4`, `mcp[cli]>=1.13.1` (EnvBase imports it at module load, `AS2/env/base.py:56-58` — **note: resolves to incompatible mcp 2.x unless the environment pins `<2`**), `fastapi`/`uvicorn` (backend), `faiss-cpu` (codegen cache), `numpy`, `pandas`, `mem0ai`, `tiktoken`, `black` (runtime dep — codegen formatting, `AS2/env/router_base.py:67`), `json-repair`, `pycityproto`, `plotly`. Extras: `analysis`, `dev` (pytest, pytest-asyncio, ruff, mypy), `docs`, `eda`, `ml` (:96-138).
- **Standalone install**: build backend hatchling (:1-3); all dependencies are plain PyPI names; no path/workspace dependency inside `PKG/pyproject.toml` (no dependency on `agentsociety` v1). So `pip install /home/user/agentsociety2/packages/agentsociety2` (or `uv pip install`) from the local checkout works without the rest of the monorepo. [Confirmed operationally by the run: editable install into the Python 3.12.3 engine env succeeded; see PHASE0_BASELINE.md.] Console scripts installed: `agentsociety` (CLI) and `agentsociety-workspace` (:85-87).

# D. Tests: what exists, what runs offline, exact commands

- **Layout** (`PKG/tests/`): top level — react/tool/schema tests (`test_agent_react_tools.py`, `test_agent_react_validation.py`, `test_agent_skill_catalog.py`, `test_person_tools.py`, `test_function_parser.py`, `test_daily_guidance_cli.py`, `test_workspace_cli.py`, `test_backend_path_security.py`, paper/analysis/research regressions); `tests/framework/` — 20 files, 129 test functions covering config, workspace contract, society resume, replay sink/writer, trace, skill registry, todo, runtime, contrib envs; `tests/skills/` — literature/analysis/experiment/hypothesis. VERIFIED listing.
- **Network/LLM requirements**: the suite is designed hermetic. `PKG/tests/conftest.py:4-18` injects dummy `AGENTSOCIETY_LLM_API_KEY=test-key`, `AGENTSOCIETY_LLM_API_BASE=https://api.openai.com/v1`, `AGENTSOCIETY_TRACE_WRITER_ASYNC=0`, and telemetry off — exactly the env-var set needed for imports to succeed (the hard import-time requirement is only `AGENTSOCIETY_LLM_API_KEY`, section 4). `tests/framework/test_workspace_contract.py:3` states "CI is intentionally hermetic: tests here must not call real LLM providers" and builds stub ServiceProxies (:25-38); `test_society_resume.py:1` is explicitly "no Ray / no LLM" with a stub router; the one aiohttp test fully mocks `ClientSession` (`PKG/tests/test_workspace_cli.py:9-66`); literature MCP tests are pure URL-string functions (`PKG/tests/skills/test_literature_mcp_client.py:1-50`). VERIFIED for the files read; remaining files INFERRED hermetic by the same pattern (stubs/mocks, no live-endpoint markers found by grep).
- **Exact commands** (require deps installed):
  ```bash
  cd /home/user/agentsociety2 && uv sync                       # workspace install
  cd /home/user/agentsociety2/packages/agentsociety2 && uv sync --extra dev
  cd /home/user/agentsociety2/packages/agentsociety2 && uv run pytest tests/framework -q   # fastest hermetic core
  cd /home/user/agentsociety2/packages/agentsociety2 && uv run pytest -q                   # full suite
  ```
  No extra env vars needed beyond what `tests/conftest.py` sets itself; for any non-pytest import, export dummy `AGENTSOCIETY_LLM_API_KEY=test-key` first. Pytest config: `testpaths=["tests"]`, `asyncio_mode="auto"` (`PKG/pyproject.toml:186-195`) — `pytest-asyncio` (dev extra) is required. [The run executed the suite in the engine env: 387 passed, 0 failed — see PHASE0_BASELINE.md.]

# E. Failure modes to plan for

1. **Ray unavailable / not installed**: `init_dispatchers` does a hard `import ray` → `ImportError` at `society.init()` (`AS2/config/llm_dispatcher.py:579`). Even though `_ray_remote` degrades to the plain function when ray is missing (`AS2/agent/runner.py:52-57`), the society calls `.remote(...)` on it (`AS2/society/society.py:331,606`) → `AttributeError`. There is **no supported Ray-less society path**; tests avoid it by never calling `init`/`step` with real batches. On Windows, ray isn't even a dependency (`PKG/pyproject.toml:81`). VERIFIED. If the Ray *cluster* dies mid-run: in-flight `await ref` raises, the tick aborts, the CLI logs and proceeds to the next top-level step (which will also fail) until the run ends `failed`/`completed` — plan an external supervisor.
2. **LLM API unreachable**: each call gets 60 s timeout + 4 attempts (immediate retries for non-429, capped exponential backoff for 429-like) then `LLMDispatchError` (`AS2/config/llm_dispatcher.py:459-543`). In step mode this becomes a silent per-agent failure (results discarded, section 9) — the run keeps ticking and terminates "completed" with empty work; only trace spans (status=error) and worker logs show it. AIMD sheds to min 1 concurrency under sustained failure but never halts. Import-time: unset key aborts before anything runs (`AS2/config/config.py:490-495`); CLI double-checks and exits 1 (`AS2/society/cli.py:59-81`). Distinguish these in accounting: `LLMDispatchError.rate_limit_like` marks provider throttling, and none of these are properties of the job under test.
3. **Workspace corrupted mid-run**:
   - Agent `AGENT.json`/`config.json` corrupt → `json.loads` raises inside `from_workspace` → per-agent error every subsequent tick, permanently, silently (driver ignores step results); no self-heal. Root-cause risk is real because `persist_agent_json` is a **non-atomic** write (`AS2/agent/base/agent.py:829-834` via `workspace_fs.py:144-147`) and `to_workspace` runs on every step for every agent. Mitigation for opaque jobs: keep artifacts write-atomic (tmp+rename) and treat `AGENT.json` as best-effort.
   - Society checkpoints are atomic (`AS2/storage/workspace_state.py:19-33`); corrupt/truncated `SOCIETY.json`/`SOCIETY_STEP.json` fails resume loudly with explicit errors (`AS2/society/society.py:482-520`; CLI `SystemExit`, `AS2/society/cli.py:388-397`).
   - Env module snapshots: per-module restore failure → that module starts fresh, others resume; loud ERROR about inconsistent env state, run continues (`AS2/env/router_base.py:404-436`).
   - Replay/trace shards are append-only; a torn replay row is possible only if a process dies inside an flock'd write (bounded by design, `AS2/storage/replay_sink.py:16-21`); DuckDB reader would surface parse errors at read time, not during the run (INFERRED).

---

**Confidence**: High on all VERIFIED items (read directly, current checkout = upstream fork base). Medium on the three INFERRED Ray-behavior points (task retry defaults, actor CPU accounting, RAY_ADDRESS attach) and on the pickle-failure claim for in-process routers inside a `ServiceProxy`.

**Single next observation that would raise confidence most**: in an installed environment, run a 2-agent, `batch_size=1` society with a stub custom agent whose `step()` raises for agent 2, and confirm (a) the run completes with no driver-side record of the failure other than trace shards, and (b) `cloudpickle.dumps(ServiceProxy(env=<in-process CodeGenRouter>, ...))` fails — that would convert the two most load-bearing INFERRED claims (silent step-failure drop is already code-verified; the pickle limit is not) into measured facts.
