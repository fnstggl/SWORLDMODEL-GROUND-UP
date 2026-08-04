# Concordia Engine Audit — google-deepmind/concordia fork @ `7779a4c9f96bad10816d88c54e4cb17d53ac5222`

> Raw report of the read-only Concordia auditor (investigation agent), 2026-08-03.
> Synthesized into `../UPSTREAM_AUDIT.md`; kept verbatim as audit evidence.

Repository: `/home/user/concordia` (remote: `fnstggl/concordia` fork — VERIFIED via `git remote -v`; HEAD SHA matches the requested commit — VERIFIED via `git rev-parse HEAD`). All paths below are absolute under `/home/user/concordia/`. Every claim is marked **VERIFIED** (I read the code at the cited lines) or **INFERRED** (deduced from verified facts).

---

## 1. Engine startup: end-to-end construction and run

**Canonical entry point** is the prefab-based `Simulation` class: `concordia/prefabs/simulation/generic.py:42-116` (VERIFIED). Constructor signature (lines 45-53): `Simulation(config, model, embedder, engine=sequential.Sequential(), override_agent_model=None, override_game_master_model=None)`.

Flow (all VERIFIED):
1. `prefab_lib.Config` (`concordia/typing/prefab.py:70-75`) holds `prefabs: Mapping[str, Prefab]`, `instances: Sequence[InstanceConfig]`, `default_premise`, `default_max_steps=100`. `InstanceConfig` (lines 63-67) = `{prefab: str, role: Role, params}`; `Role` is `ENTITY | GAME_MASTER | INITIALIZER` (lines 28-31).
2. `Simulation.__init__` creates **one shared GM memory bank** with `allow_duplicates=True` (`generic.py:90-96`) and a **fresh private memory bank per entity** (`generic.py:195-197`). Entities are built first, then initializers + game masters (`generic.py:112-116`), because GM prefabs receive `entities` references (`generic.py:167`) while entities never receive references to each other (design note, `generic.py:54-74` and `concordia/typing/simulation.py:41-49`).
3. Each prefab's `build(model, memory_bank)` returns an `EntityAgentWithLogging` (`concordia/typing/prefab.py:44-51`).
4. `Simulation.play(premise, max_steps, raw_log, get_state_callback, checkpoint_path, step_controller, step_callback)` (`generic.py:235-331`): sorts GMs initializers-first (lines 283-294), calls `self._engine.run_loop(game_masters=…, entities=…, premise=…, max_steps=…, verbose=True, log=raw_log, checkpoint_callback=…)` (lines 296-306), then builds a `structured_logging.SimulationLog` from the raw log and attaches all entity + GM memories (lines 308-331).

**Documented usage** matches: `CHEATSHEET.md` lines 24-107 ("Minimal Simulation Setup": build prefab dict via `helper_functions.get_package_classes`, build `Config`, `sim = simulation.Simulation(...); results = sim.play()`), and `examples/tutorial.ipynb` cells 3-14 (VERIFIED by extracting cells). Prefab discovery helper: `concordia/utils/helper_functions.py:176-190`.

**Minimal programmatic construction without prefabs is fully supported**: engines only require objects satisfying `entity_lib.Entity` (`concordia/environment/engine.py:33-87`). The library's own tests build `EntityAgentWithLogging` directly (act component + component dict) and call `engine.run_loop` with a hand-built GM — `concordia/prefabs/game_master/game_master_prefabs_test.py:163-199`, and even plain mock entities — `concordia/environment/engines/sequential_test.py:29-72` (VERIFIED).

---

## 2. Sequential and simultaneous engines

Base interface `Engine` (`concordia/environment/engine.py:30-87`, VERIFIED): abstract `make_observation`, `next_acting`, `resolve`, `terminate`, `next_game_master`, `run_loop(game_masters, entities, premise, max_steps, verbose, log, checkpoint_callback, step_controller, step_callback)`.

### Sequential (`concordia/environment/engines/sequential.py:67-412`, VERIFIED)

`run_loop` (lines 223-383) exact order per step:
1. Loop guard: `while not self.terminate(game_master, verbose) and steps < max_steps` (line 247). `terminate()` = GM `act()` with `OutputType.TERMINATE`, options `('Yes','No')` (lines 175-189). Premise, if any, is observed once by GM #0 as `[event] {premise}` before the loop (lines 243-246).
2. Optional `step_controller.wait_for_step_permission()` gate (lines 248-250; `concordia/environment/step_controller.py:38-146`).
3. `next_game_master()` — GM `act()` with `NEXT_GAME_MASTER` over GM-name options; skipped if only one GM (lines 191-221, 256).
4. **Observations for ALL entities in parallel**: `make_observation(gm, entity)` = GM `act()` with `MAKE_OBSERVATION` and call-to-action formatted with the entity name (lines 93-104); each non-empty result is delivered via `entity.observe(...)`; fan-out via `concurrency.run_tasks` (lines 262-283).
5. `next_acting()` — two GM `act()` calls: `NEXT_ACTING` (choice over entity names) then `NEXT_ACTION_SPEC` (free-form JSON string parsed by `engine_lib.action_spec_parser`) (lines 106-146). Invalid entity name raises `ValueError` (lines 140-144).
6. `SKIP_THIS_STEP` branch: skip act/resolve, still increments `steps`, fires callbacks (lines 288-311) — used by INITIALIZER game masters.
7. `raw_action = next_entity.act(entity_spec_to_use)`; the engine prefixes `"{entity.name}: "` if not already present (lines 317-321).
8. `resolve(gm, action)` (lines 148-173): `gm.observe(f'[putative_event] {action}')` → `result = gm.act(RESOLVE)` → **event commit**: `gm.observe(f'[event] {result}')` (line 170).
9. `steps += 1`; per-step structured log entry assembled from `get_last_log()` snapshots (lines 335-359); `checkpoint_callback(steps)` (lines 361-362); `step_callback(StepData…)` (lines 364-383).

### Simultaneous (`concordia/environment/engines/simultaneous.py:69-459`, VERIFIED)

Differences: `next_acting` returns a *list* — GM answers `NEXT_ACTING` with a comma-separated name list, then one `NEXT_ACTION_SPEC` call per named entity (lines 104-159). Per-entity closure `_entity_act` does make_observation (GM call under `self._gm_log_lock`, lines 305-317), `entity.observe`, `entity.act`; all run concurrently and fault-tolerantly via `concurrency.run_tasks_in_background` (lines 358-376). All actions are newline-joined and resolved in **one** `resolve()` call (lines 393-394). Step/termination structure otherwise identical (lines 242-429).

### Asynchronous (`concordia/environment/engines/asynchronous.py`, VERIFIED header 15-21, 67-81)

Each entity runs its own observe-act thread; GM components must be thread-safe; requires `ReactiveMeasurements` on every entity (lines 67-81). Exists but is not the default; not audited in depth here.

---

## 3. Game Master creation

A GM **is** an `EntityAgentWithLogging` whose acting component is `SwitchAct` (`concordia/prefabs/game_master/generic.py:261-272`, VERIFIED). `SwitchAct.get_action_attempt` dispatches on `action_spec.output_type` (`concordia/components/game_master/switch_act.py:274-338`, VERIFIED). For each GM-specific output type it checks for a reserved component key in the contexts and, if the key is **absent, falls back to a raw LLM "YOLO" chain** (its own comments call it that):

| Function | Reserved key | Component (default impl) | YOLO fallback |
|---|---|---|---|
| terminate | `__terminate__` (`switch_act.py:35-37`) | `Terminate`/`NeverTerminate`/`SceneBasedTerminator` (`components/game_master/terminate.py:25-151`) | `yes_no_question` (`switch_act.py:132-141`) |
| next GM | `__next_game_master__` | `NextGameMaster` (`next_game_master.py:34-132`), `SceneTracker` (same key, `scene_tracker.py:40-41`) | multiple choice (`switch_act.py:262-270`) |
| make observation | `__make_observation__` | `MakeObservation` (`make_observation.py:85-266`) | open question, 1000 tokens (`switch_act.py:154-161`) |
| next acting | `__next_acting__` | `NextActing` LLM-choice (`next_acting.py:47-136`), `NextActingInFixedOrder` (257-336), `NextActingInRandomOrder` (339-409), `NextActingFromSceneSpec` (412-490) | multiple choice (`switch_act.py:174-182`) |
| next action spec | `__next_action_spec__` | `NextActionSpec` (`next_acting.py:493-613`), `NextActionSpecFromSceneSpec` (616-709), `FixedActionSpec` (712-758) | open question + JSON reformat (`switch_act.py:202-230`) |
| resolve | `__resolution__` | `EventResolution` (`event_resolution.py:40-278`) | open question (`switch_act.py:243-249`) |

(All VERIFIED.)

**Actor selection**: the generic prefab picks `NextActing` (LLM choice), fixed-order, or random per `acting_order` param (`prefabs/game_master/generic.py:161-188`). `NextActing.pre_act` asks "Whose turn is next?" as a multiple-choice over player names and records `_currently_active_player` (`next_acting.py:106-126`).

**Observation generation**: `MakeObservation.pre_act` (on `MAKE_OBSERVATION`) parses the active entity name out of the call-to-action string (`make_observation.py:165-201`), drains that entity's `ObservationQueue` (lines 205-209), and if the queue is empty and `allow_llm_fallback=True` (default) asks the model "What does X observe now? … Keep the story moving forward." (lines 210-220), optionally reformatting to a style (lines 224-245). `ObservationQueue` is thread-safe, supports the special target `'all'`, and can be shared across GMs via `external_queue` (lines 41-82, 97-141); only the `*_and_dramaturgic` prefabs expose `external_queue` as a param (e.g. `prefabs/game_master/dialogic_and_dramaturgic.py:118,200` — VERIFIED via grep).

**Event resolution**: `EventResolution.pre_act` (on `RESOLVE`) gets the active player from the NextActing component (`event_resolution.py:147-154`), scans GM memory for `[putative_event]` entries and picks the most recent one from the active player (lines 155-193), strips the name prefix (lines 197-207), then runs the configured `event_resolution_steps` thought chain via `run_chain_of_thought` (lines 211-216; chain runner at 1282-1308: each step is `f(document, premise, active_player_name) -> str`, output feeds the next). If `notify_observers=True` it then asks "Which entities are aware of the event?" and queues the event statement for each named entity via `MakeObservation.add_to_queue` (lines 219-236). The generic prefab's default chain is `[maybe_inject_narrative_push, AccountForAgencyOfOthers, result_to_who_what_where]` (`prefabs/game_master/generic.py:202-210`) with `notify_observers=True` (line 230).

**Terminal states**: declared either (a) by the LLM every step via the YOLO terminate path — note the **generic GM prefab registers NO terminate component** (component dict at `prefabs/game_master/generic.py:233-246` has no `__terminate__` key — VERIFIED), (b) by `Terminate.terminate()` being called programmatically (`terminate.py:55-56`), (c) by `SceneBasedTerminator`/`SceneTracker` when all scene rounds are consumed (`terminate.py:109-151`, `scene_tracker.py:229-238`), or (d) by the engine's `max_steps`/`step_controller` (§9).

---

## 4. ActionSpec

`concordia/typing/entity.py` (VERIFIED):
- `OutputType` enum (lines 25-41): player types `FREE, CHOICE, FLOAT`; GM types `MAKE_OBSERVATION, NEXT_ACTING, NEXT_ACTION_SPEC, RESOLVE, TERMINATE, NEXT_GAME_MASTER, SKIP_THIS_STEP`; groupings at lines 43-68.
- `ActionSpec` frozen dataclass (lines 73-135): `call_to_action: str`, `output_type`, `options` (required non-empty and duplicate-free for CHOICE types, forbidden otherwise — `__post_init__` lines 90-98), `tag`. `validate(action)` (lines 100-120) checks CHOICE membership / FLOAT parseability. `to_dict`/`action_spec_from_dict` (lines 122-152) give JSON round-trip.
- Helpers `free_action_spec`/`float_action_spec`/`choice_action_spec`/`skip_this_step_action_spec` (lines 155-174); `DEFAULT_CALL_TO_ACTION` (177-182), `DEFAULT_ACTION_SPEC` (184-187), `DEFAULT_CALL_TO_SPEECH`/`DEFAULT_SPEECH_ACTION_SPEC` (190-201).

**Call-to-action strings**: The GM emits the next actor's ActionSpec **as a JSON string**; `engine.action_spec_parser` parses JSON with a legacy `"prompt: …;;type: …"` fallback (`environment/engine.py:90-175`). `{name}` is substituted engine-side when formatting GM calls (`engines/sequential.py:99-100,129-130`) and entity-side by the act component: `ConcatActComponent` uses `.replace('{name}', entity.name)` (`components/agent/concat_act_component.py:106-108`); `SwitchAct` uses `.format(name=…)` (`switch_act.py:284-286`). The `{timedelta}` placeholder mentioned in the docstring (`typing/entity.py:79`) has no substitution code in current act components (grep found no other occurrence) — vestigial (INFERRED from that search).

---

## 5. EntityAgent lifecycles

`concordia/agents/entity_agent.py` (VERIFIED):
- `EntityAgent(agent_name, act_component, context_components)`; components are bound via `set_entity` (lines 44-75). Phase machine enforced: `READY → PRE_ACT → POST_ACT → UPDATE → READY` and `READY → PRE_OBSERVE → POST_OBSERVE → UPDATE → READY` (`typing/entity_component.py:39-87`).
- `act(action_spec)` (lines 154-188), under `_control_lock`: (1) phase `PRE_ACT`, **parallel** `pre_act(action_spec)` on all context components → `ComponentContextMapping` (name → string); (2) `act_component.get_action_attempt(contexts, action_spec)`; (3) phase `POST_ACT`, parallel `post_act(action_attempt)` — **return values discarded** (line 174); (4) phase `UPDATE`, parallel `update()`; (5) `READY`, return action string.
- `observe(observation)` (lines 190-216): parallel `pre_observe(observation)` → parallel `post_observe()` → parallel `update()`.
- Parallel dispatch `_parallel_call_` (lines 110-152) dedups component instances registered under multiple names and runs them in a thread pool (`concurrency.run_tasks`). **Component execution order within a phase is therefore unordered/concurrent; ordering only affects prompt concatenation** in the act component (`concat_act_component.py:84-94`; `switch_act.py:108-119`).
- Context building: components that expose cached cross-readable state derive from `ActionSpecIgnored` (`components/agent/action_spec_ignored.py:25-103`) — value computed once per phase, readable by other components only during `PRE_ACT`/`POST_ACT` (lines 49-72), invalidated in `update()` (lines 85-87).
- `get_state`/`set_state` aggregate the act component and all context components (lines 218-255).
- `EntityAgentWithLogging` adds a `Measurements` registry, wires each `ComponentWithLogging` to a channel named after its component key, plus `__act__` (`agents/entity_agent_with_logging.py:27-112`), and implements `get_last_log()` (lines 108-112) which the engines snapshot after each GM call.

The standard actor prefab `basic.Entity` (`prefabs/entity/basic.py:32-202`) assembles: `Instructions` (constant role-play instructions, `components/agent/instructions.py:22-43`), optional `Goal` constant, three `QuestionOfRecentMemories` chains (situation/self/person-by-situation, `components/agent/question_of_recent_memories.py:28-120`), `LastNObservations`, `ObservationToMemory`, `AssociativeMemory`, with `ConcatActComponent` (all VERIFIED). A `minimal.Entity` variant with only instructions/observations/memory exists (`prefabs/entity/minimal.py:31-152`).

---

## 6. Memory

- **Bank**: `AssociativeMemoryBank` (`concordia/associative_memory/basic_associative_memory.py:30-259`, VERIFIED). Pandas DataFrame `['text','embedding']`; `add()` strips newlines, hash-dedups unless `allow_duplicates` (lines 87-114), batches into `_pending_memories`; `retrieve_associative(query,k)` = cosine top-k via embedder (133-198); `retrieve_recent(k)` (218-237); `scan(selector_fn)` insertion-ordered (200-216); `get_all_memories_as_text()` (249-255); `get_state`/`set_state` = stored hashes + DataFrame JSON (56-73, embeddings included). Memories are never deleted (docstring lines 239-247).
- **Component**: `components/agent/memory.py` — abstract `Memory` (30-110) and `AssociativeMemory` (113-235): `add()` buffers during act/observe and commits during the `UPDATE` phase (`update()` lines 216-222); reads forbidden during `UPDATE` (`_check_phase` 40-44). Default key `'__memory__'` (line 27). `ListMemory` (238-341) is the embedder-free alternative.
- **Write paths**: agent/GM observations reach memory via `ObservationToMemory.pre_observe`, which prefixes `[observation]` (`components/agent/observation.py:30-59`). GM event memory arises because the engines call `gm.observe('[putative_event] …')`/`gm.observe('[event] …')` (§2), so GM memory rows look like `[observation] [event] …`; `DisplayEvents` scans for `[event]` (`event_resolution.py:281-345`) and `EventResolution` scans for `[putative_event]` (line 158).
- **Retrieval into prompts**: `LastNObservations` (recency, `observation.py:76-153`), `AllSimilarMemories` (LLM-summarized query → associative retrieve, `components/agent/all_similar_memories.py:30-120`), `QuestionOfRecentMemories` (recency + LLM question).
- **Formative memories**: `FormativeMemoriesInitializer` GM component (`components/game_master/formative_memories_initializer.py:32-330`): on its first `NEXT_GAME_MASTER` call it writes shared memories to GM memory, generates per-player backstory episodes with a two-stage LLM chain (lines 218-321), queues everything to players via `MakeObservation.add_to_queue`, then returns its own GM name once and afterwards the `next_game_master_name` (lines 168-216). Packaged as an INITIALIZER-role prefab with `NeverTerminate` + `FixedActionSpec(skip_this_step)` (`prefabs/game_master/formative_memories_initializer.py:90-131`), which triggers the engine's SKIP branch.

---

## 7. Scenes

- Specs: `SceneTypeSpec` (name, `game_master_name`, `default_premise` per participant, `action_spec` override, `possible_participants`) and `SceneSpec` (scene_type, participants, `num_rounds`, `start_time`, premise) — `concordia/typing/scene.py:25-79` (VERIFIED).
- `SceneTracker` (`components/game_master/scene_tracker.py:46-274`, VERIFIED) is registered under the **`__next_game_master__` key** (lines 40-41), so scene transitions ride the engine's `next_game_master` call: it returns the scene's GM name (or a default) on `NEXT_GAME_MASTER` (lines 240-244). Round progress is tracked by writing `[scene counter](n)` markers into GM memory on each `RESOLVE` (lines 246-264); premises are queued to participants exactly once per scene via a `[scene premise queued]` marker (lines 162-209); termination when all rounds consumed (lines 123-127, 229-238). Its own `get_state` is empty — state is derived from GM memory (lines 268-274).
- Participant/action-spec selection per scene: `NextActingFromSceneSpec` (round-robin over scene participants, `next_acting.py:452-475`) and `NextActionSpecFromSceneSpec` (serializes the scene's ActionSpec, possibly per-participant mapping, `next_acting.py:678-691`).
- Prefabs wiring scenes: `dialogic_and_dramaturgic.py`, `game_theoretic_and_dramaturgic.py`, `psychology_experiment.py`, etc. (file list VERIFIED; internals spot-checked).

---

## 8. State serialization / restoration

**Interfaces** (VERIFIED):
- Every component must implement `get_state()/set_state()` returning JSON-able `ComponentState`; contract: state excludes constructor args, and `set_state` assumes an identically-constructed instance (`typing/entity_component.py:118-162`). `get_dynamic_state()` marks runtime-editable keys (lines 164-181).
- `EntityAgent.get_state/set_state` = `{act_component, context_components:{name: state}}` (`agents/entity_agent.py:218-255`); GMs are the same class. `EntityWithComponents` declares both abstract (`typing/entity_component.py:219-227`).
- Memory bank state includes full text + embeddings (`basic_associative_memory.py:56-73`); the agent memory component also saves its uncommitted `buffer` (`components/agent/memory.py:134-144`). `MakeObservation` saves the pending observation queue (`make_observation.py:260-266`); `EventResolution` saves `_active_entity_name`/`_putative_action` (`event_resolution.py:257-267`); `NextActing*` save the active player/sequence (`next_acting.py:128-136, 323-336, 399-409`).

**Simulation-level checkpoint path** (VERIFIED): `generic.Simulation.make_checkpoint_data()` (`prefabs/simulation/generic.py:333-380`) → `{entities:{name:{prefab_type, entity_params, components, component_info}}, game_masters:{…, role}, raw_log, checkpoint_counter}`; `save_checkpoint(step, checkpoint_path)` writes `step_{n}_checkpoint.json` after every engine step via the `checkpoint_callback` (lines 279-281, 518-537; engine calls at `sequential.py:361-362`); `load_from_checkpoint(dict)` re-instantiates or updates entities/GMs through the prefab registry and `set_state` (lines 539-644). Round-trip is tested offline with `NoLanguageModel` in `concordia/prefabs/simulation/checkpoint_test.py:84-131`.

**What is NOT covered** (each item VERIFIED at cited lines; the aggregation is INFERRED):
- **RNG state**: every `InteractiveDocument` creates an unseeded `np.random.default_rng()` (`document/interactive_document.py:63-67`); global `random` module state used by GM components (§13). Neither is captured.
- **Engine position**: `run_loop` local `steps` counter, the currently-selected game master, and mid-step position are not serialized; `play()` after restore restarts the loop at `game_masters[0]` with `steps=0` and **re-observes the premise** (`sequential.py:242-246`; `generic.py:267-306`). Only component flags (e.g. `FormativeMemoriesInitializer._initialized`, `formative_memories_initializer.py:323-330`) prevent re-initialization.
- **Non-JSON values are silently dropped** by `_make_json_serializable` (`generic.py:382-404`); measurements objects are explicitly expected to disappear from params (`checkpoint_test.py:133-150`).
- **Measurement/log channels** (`Measurements._channels`) are not part of any state; `raw_log` is saved but per-channel histories are not.
- `Phase`, `_capture_key_by_thread`, thread pools, `StepController` state, the model/embedder identities, and the `Config`/`scenes` objects themselves (restore requires reconstructing the same `Simulation` with the same config so `config.prefabs` lookups succeed — `generic.py:591-595`).

---

## 9. Termination

A run ends when (VERIFIED):
1. GM answers `Yes` to the TERMINATE query at the top of each loop iteration (`sequential.py:247`, `simultaneous.py:266`) — via `Terminate`/`SceneBasedTerminator` component state or the LLM YOLO fallback (§3);
2. `steps >= max_steps` (default 100 from `Config.default_max_steps`, `typing/prefab.py:75`);
3. `step_controller.wait_for_step_permission()` returns False after `stop()` (`sequential.py:248-250`; `step_controller.py:108-145`).
There is no timeout/exception-based termination in the engines; entity failures in the simultaneous engine are logged and skipped (`simultaneous.py:372-376`), while in the sequential engine exceptions propagate out of `run_loop` (INFERRED: no try/except around `next_entity.act` at `sequential.py:317`).

---

## 10. Logging / tracing

- **Raw log**: engines append one dict per step containing filtered `get_last_log()` snapshots for every engine phase (`terminate/next_game_master/make_observation/next_acting/next_action_spec/resolve`) plus the acting entity's log (`sequential.py:55-64, 241-359, 385-412`; `simultaneous.py:431-459`) (VERIFIED).
- **Component channels**: `ComponentWithLogging.set_logging_channel` (`typing/entity_component.py:184-193`) wired to `Measurements` channels per component key (`entity_agent_with_logging.py:61-80`); `Measurements` is a threadsafe dict of channel lists (`utils/measurements.py:22-111`). Async variant `ReactiveMeasurements` in `utils/async_measurements.py` (exists; spot-checked via checkpoint_test usage).
- **Structured log**: `SimulationLog` with content-deduplicating `ContentStore`, entity/step/component indexes, `to_json/from_json`, `to_html` (renders via `structured_logging_html.render_dynamic_html`), `attach_memories`, and an `AIAgentLogInterface` query API (`utils/structured_logging.py:200-630, 633+`) (VERIFIED).
- **CLI**: console script `concordia-log` (`setup.py:80-84`) → `command_line_interface/concordia_log.py` (argparse tool over `SimulationLog.from_json`, lines 32-63, 369-457). A static `log_viewer.html` and `simulation_server.py`/`visual_interface.py` exist in `utils/` (file list VERIFIED).
- Model-call profiling: `language_model/profiled_language_model.py` (exists, not audited in depth); `DEFAULT_STATS_CHANNEL = 'language_model_stats'` (`language_model.py:29`).

---

## 11. Model calls

- **Interface**: `LanguageModel.sample_text(prompt, max_tokens=5000, terminators, temperature=1.0, top_p, top_k, timeout=60, seed=None)` and `sample_choice(prompt, responses, seed=None) -> (idx, response, info)` (`concordia/language_model/language_model.py:37-104`, VERIFIED).
- **Where calls happen**: exclusively inside components/act-components through `InteractiveDocument.open_question / multiple_choice_question / yes_no_question` (`document/interactive_document.py:142-349`); the engines themselves never call the model — they only call `entity.act/observe` (VERIFIED across §2 files). Note `open_question` does **not** forward any `seed` (lines 182-189).
- **Wrappers (opt-in, not applied automatically)**: `RetryLanguageModel` (tenacity exponential backoff + jitter, `retry_wrapper.py:24-127`), `CallLimitLanguageModel` (`call_limit_wrapper.py:24+`), `profiled_language_model.py`. `generic.Simulation` stores the passed model unwrapped (`generic.py:75-80`) (VERIFIED; "not applied automatically" INFERRED from the absence of wrapping there and in prefabs).
- **Deterministic/offline models**: `NoLanguageModel` (empty text, always choice 0 — `no_language_model.py:25-58`), `RandomChoiceLanguageModel` / `BiasedMedianChoiceLanguageModel` (seedable per-call, lines 61-118), `testing/mock_model.MockModel` (fixed string, choice 0 — `mock_model.py:22-69`). Provider registry + `language_model_setup(..., disable_language_model=True) → NoLanguageModel` in `contrib/language_models/__init__.py:60-83` (VERIFIED).

---

## 12. Concurrency assumptions

- **Threads only; no asyncio anywhere in the core** (VERIFIED: `utils/concurrency.py` is `concurrent.futures.ThreadPoolExecutor`-based, lines 28-220; no `async def` in core modules encountered).
- Concurrency sites: component fan-out inside every `act()/observe()` (`entity_agent.py:110-152`); all-entity observation fan-out in Sequential (`sequential.py:279-283`); per-entity act fan-out in Simultaneous (`simultaneous.py:358-376`, GM calls serialized only for make_observation via `_gm_log_lock`, line 311); fully threaded per-entity loops in Asynchronous (GM must be thread-safe, `asynchronous.py:15-21`).
- Safety mechanisms: `EntityAgent._control_lock` serializes act/observe per entity (`entity_agent.py:64,158,192`); phase lock (line 65); memory-bank lock (`basic_associative_memory.py:48`); `ObservationQueue` lock (`make_observation.py:48-50`); measurements lock (`measurements.py:28`).
- **One Sequential/Simultaneous simulation is driven single-threaded from the caller's thread** (fan-out is scoped and joined each step) — VERIFIED from `run_loop` structure. **Multiple simulations in one process**: each `Simulation` owns its entities/banks/logs; the only shared mutable global state found is the process-wide `random` module state (§13) and Python-global logging — so concurrent simulations are functionally safe but not reproducible (INFERRED from the grep in §13 plus absence of module-level mutable singletons in the files read).

---

## 13. RNG / determinism

Randomness entry points (all VERIFIED):
1. `InteractiveDocument` creates an **unseeded** `np.random.default_rng()` unless one is injected (`document/interactive_document.py:50-67`); `multiple_choice_question(randomize_choices=True)` permutes option order every call (lines 303-336). Components construct documents without an rng (e.g. `switch_act.py:280`, `next_acting.py:112`), so **option shuffling is nondeterministic even with a deterministic model**.
2. Global `random` module: `AccountForAgencyOfOthers` shuffles actor lists (`event_resolution.py:881`); `maybe_inject_narrative_push` picks a random complication (`event_resolution.py:1188`); `NextActingInRandomOrder` (`next_acting.py:385`); `ExamplesSynchronous` samples example names, injectable `rnd` (`instructions.py:131-135`); contrib components (`marketplace.py:500`, `day_in_the_life_initializer.py:481`).
3. `open_question_diversified` picks among candidate answers via the document rng (`interactive_document.py:293`).
4. `ConcatActComponent(randomize_choices=True)` default for actors (`concat_act_component.py:44,122-127`); exposed as prefab param `'randomize_choices'` (`prefabs/entity/basic.py:44,76`). **SwitchAct's GM paths have no such switch** — its `multiple_choice_question` calls use the randomizing default (`switch_act.py:176-182, 264-270`).

Consequence (INFERRED from the above): with `NoLanguageModel`/`MockModel` (`sample_choice` returns index 0 of the *shuffled* letters), multiple-choice outcomes are uniformly random. Bit-exact deterministic runs are **not achievable through public configuration alone**; they additionally require seeding/patching `np.random.default_rng` and the global `random` module, and setting `randomize_choices=False` where exposed. The `seed` parameter on `LanguageModel` is unused by `InteractiveDocument` callers (`interactive_document.py:182-189`).

---

## A. Public components usable unchanged for a two-actor social simulation

All VERIFIED as existing public API; the composition claim is INFERRED from §§1-7:

- **Actors**: `prefabs.entity.basic.Entity` or `prefabs.entity.minimal.Entity` (+ `EntityAgentWithLogging` directly). Private per-actor state is structural: each entity gets its own `AssociativeMemoryBank` (`generic.py:195-197`) and entities never see each other's objects (`generic.py:54-74`).
- **Private context**: `Constant` goal component (`components/agent/constant.py:23-66`, param `'goal'`); `FormativeMemoriesInitializer` `player_specific_memories` / `player_specific_context` (`components/game_master/formative_memories_initializer.py:44-47`); or `memory_state` param preload (`generic.py:206-222`).
- **Shared context**: `shared_memories` (same initializer, lines 43, 179-192) — goes to GM memory and every player's queue; or GM `Instructions`-style `Constant` components; or the `premise` argument to `play()` (delivered to the GM only, `sequential.py:243-246`).
- **Initial observations**: `MakeObservation.add_to_queue` / `ObservationQueue` (`make_observation.py:41-82,256-258`); scene premises (`scene_tracker.py:162-209`); INITIALIZER role + engine SKIP step (`sequential.py:288-311`).
- **Cutoff**: `Config.default_max_steps` / `play(max_steps=…)`; `Terminate` component or `SceneBasedTerminator` for exact scene-count cutoffs (`terminate.py:25-151` + `scene_tracker.py`).
- **Full event trace**: `raw_log` (per-step dict incl. every GM phase prompt/output) + `SimulationLog.to_json/to_html` (`generic.py:308-331`, `structured_logging.py`); GM event stream = `game_master_memory_bank.get_all_memories_as_text()` filtered on `[event]` / `DisplayEvents` (`event_resolution.py:281-345`); per-entity memories via `__memory__.get_all_memories_as_text()` (`generic.py:311-324`).
- **GM**: `prefabs.game_master.dialogic.GameMaster` for pure conversation (fixed speech ActionSpec, near-pass-through resolution `RemoveSpecificText`, `notify_observers=False` + `SendEventToRelevantPlayers` — `dialogic.py:172-240`) or `generic.GameMaster` for narrative simulation.

## B. Every place the DEFAULT Game Master can exercise unrestricted authority

Baseline: generic GM prefab (`prefabs/game_master/generic.py`) + `SwitchAct` + Sequential engine. All citations VERIFIED.

1. **Invent facts**
   - `MakeObservation` LLM fallback when the queue is empty: "What does X observe now? … Keep the story moving forward." (`components/game_master/make_observation.py:210-220`; enabled by default `allow_llm_fallback=True`, line 98).
   - GM instructions authorize invention: "You are the game master so you may control any non-player character. You will track the state of the world…", "Try to ensure the story always moves forward" (`components/game_master/instructions.py:82-101`); the make-observation few-shot example is a fully invented scene (lines 36-48).
   - SwitchAct YOLO fallbacks answer any GM query from raw context with no component constraint (`switch_act.py:132-141, 154-161, 204-230, 243-249`).
   - Thought-chain step `result_to_effect_caused_by_active_player`: "…it is critical always to take a stance on what is happening and **invent when necessary**" (`event_resolution.py:776-791`; available via `extra_event_resolution_steps`).
   - `WorldState.post_act` free-form invents/updates state variables after each resolution (`components/game_master/world_state.py:99-138`).
2. **Decide another actor's voluntary choice**
   - The RESOLVE chain rewrites the event freely (`result_to_who_what_where`, `event_resolution.py:732-758`); the only guard, `AccountForAgencyOfOthers` (lines 833-945), is itself LLM-driven: it detects "voluntary acts of inactive players" by yes/no question (lines 864-867) and, when it *does* consult the affected player (via `player.act` with a Yes/No spec, lines 891-900), a "Yes" lets the GM commit that player's action.
   - `Conversation` resolution step makes players speak (calls `player.act` for listed participants but **invents lines for any non-player name the LLM lists**, lines 989-1002) and force-feeds the merged conversation to participants via `observe` (lines 1020-1023).
   - `maybe_inject_narrative_push` explicitly licenses NPC volition: "Non-player characters … can always be used to push the narrative forward" (lines 1176-1179).
3. **Choose observers**
   - `EventResolution` with `notify_observers=True` (generic prefab line 230): open question "Which entities are aware of the event?" decides who observes (`event_resolution.py:226-234`).
   - `SendEventToRelevantPlayers.post_act`: per-player yes/no "Is X aware of the latest event above?" (`event_resolution.py:469-494`).
   - Engine-level: any entity whose `make_observation` returns non-empty gets it (`sequential.py:262-277`) — and the LLM fallback means the GM effectively decides observation content per entity every step.
4. **Determine mechanical feasibility**
   - No structured feasibility system exists in the default chain; success/failure is whatever the RESOLVE prompt produces. Dedicated but *optional* steps: `determine_success_and_why` ("Does the attempted action succeed? …", `event_resolution.py:588-626`), `attempt_to_result` (663-686), `get_action_category_and_player_capability` (1053-1141). None are in the generic default chain (`generic.py:206-210`).
5. **Declare terminal results**
   - The generic GM prefab includes **no `__terminate__` component** (component dict `generic.py:233-246`), so every step's termination check runs the SwitchAct YOLO path: a bare `yes_no_question('Is the game/simulation finished?')` (`switch_act.py:132-141`, `sequential.py:42`). The LLM can end the run at any step.
6. **Silently introduce causal events**
   - `maybe_inject_narrative_push`: if the LLM judges the story "repetitive", it invents five complications, `random.choice`s one, and merges it into the player's event (`event_resolution.py:1144-1201`) — this is the **first** step of the generic default chain (`generic.py:206-210`), so it runs on every resolution.
   - `maybe_cut_to_next_scene` appends `[CUT TO NEXT SCENE]` time-skips (1204-1279; optional).
   - The MakeObservation fallback (item 1) also introduces events players "observe" that were never resolved as events.

## C. Package / dependency requirements

All VERIFIED:
- **Packaging**: `setup.py` (`setup.py:34-146`) — name `gdm-concordia`, version 2.4.0, `python_requires='>=3.12'` (line 68), classifiers 3.12/3.13/3.14 (lines 61-63), `.python-version` = `3.12`. `pyproject.toml` has only `[build-system] setuptools>=42` + tool configs (no `[project]` table) — so `pip install .` / `pip install -e /home/user/concordia` builds through setup.py; PyPI name `gdm-concordia` (README install section).
- **Core deps** (`setup.py:69-79`): `absl-py, ipython, matplotlib, numpy>=1.26, pandas, python-dateutil, reactivex, tenacity, termcolor`. Extras per provider: `openai, google (google-genai, google-cloud-aiplatform), huggingface (torch/transformers/accelerate), mistralai, ollama, together, groq, vllm, langchain, amazon (boto3), mcp`, and `dev` (lines 85-145). `requirements.txt` is a 6325-line pip-compile lockfile with hashes for `examples/requirements.in + setup.py` (examples add `sentence-transformers`, etc.).
- **License**: Apache-2.0, `LICENSE` at repo root (header verified) + `license='Apache 2.0'`, `license_files=['LICENSE']` (`setup.py:37-38`).
- **Console script**: `concordia-log` (`setup.py:80-84`).
- **The audit machine could not run it as-is**: system Python is 3.11.15 (< 3.12); `import concordia` succeeds only because the top-level `__init__.py` is empty; `import concordia.environment.engine` fails without `absl` (VERIFIED by running exactly those commands; nothing was installed by the auditor). [Superseded operationally: the run's engine env is Python 3.12.3 with the package installed — see PHASE0_BASELINE.md.]

## D. Tests/examples runnable WITHOUT network/LLM credentials

The entire core test suite is offline-safe by design: unit tests use `no_language_model.NoLanguageModel` and trivial embedders (`np.random.rand(3)` or `np.ones(3)`) — VERIFIED for `prefabs/entity/prefabs_test.py:65`, `prefabs/game_master/game_master_prefabs_test.py:151`, `components/agent/agent_components_test.py`, `components/game_master/gm_components_test.py`, `prefabs/simulation/checkpoint_test.py:100`, engine tests with pure-mock entities (`environment/engines/sequential_test.py:29-72`), and example tests (`examples/games/haggling/haggling_test.py:39` etc.). Pytest config: `[tool.pytest.ini_options]` requires `pytest-xdist`, `addopts="-n auto"`, `testpaths=["concordia","examples"]` (`pyproject.toml:31-34`).

Exact commands (environment with Python ≥3.12 and `pip install -e '.[dev]'`):
```
cd /home/user/concordia
python -m pytest concordia/environment -n auto                      # engine tests (mock entities, no LLM)
python -m pytest concordia/prefabs -n auto                          # prefab + checkpoint round-trip (NoLanguageModel)
python -m pytest concordia/components -n auto                       # agent/GM component tests (NoLanguageModel)
python -m pytest concordia/document concordia/utils -n auto
python -m pytest examples -n auto                                   # example scaffolding tests (NoLanguageModel)
```
Notebooks (`examples/tutorial.ipynb` etc.) need an API key unless `DISABLE_LANGUAGE_MODEL=True`, which swaps in `NoLanguageModel` and a constant embedder (tutorial cells 4-6; `contrib/language_models/__init__.py:82-83`) — VERIFIED.

## E. Narrowest seam for a SWORLDMODEL "minimum agency guard" (between GM resolution and event commit)

Three supported attachment points, ordered by narrowness (mechanics VERIFIED; recommendation INFERRED):

1. **Final `event_resolution_steps` entry (recommended — component-native, complete gate).** `EventResolution.__init__` accepts an arbitrary sequence of callables `(InteractiveDocument, event_str, active_player_name) -> str` (`components/game_master/event_resolution.py:46-56, 93`), executed by `run_chain_of_thought` (lines 1282-1308) where each step's output becomes the next step's input and the last output **is** the event statement. A guard appended last sees the fully-resolved candidate event **before** (a) observer notification (`notify_observers` block runs after the chain, lines 219-236), (b) SwitchAct returning it to the engine, and (c) the engine's `[event]` commit. It can rewrite, veto, or split the event (returning a reformulated multi-clause statement). `AccountForAgencyOfOthers` (lines 833-945) is the in-repo precedent for exactly this kind of validator, including calling `player.act()` for consent. Caveat: the generic prefab's `extra_event_resolution_steps` param only resolves *names of functions defined in* `event_resolution.py` via `getattr` (`prefabs/game_master/generic.py:211-214`), so a custom callable requires assembling `EventResolution` yourself (or a thin custom prefab) — but **no GM fork**: it is a public constructor parameter.
2. **Engine wrapper around `resolve()` (narrowest single choke point).** The literal commit is one line: `game_master.observe(f'{EVENT_TAG} {result}')` (`engines/sequential.py:170`; `simultaneous.py:185`). A subclass of `Sequential` overriding `resolve()` can intercept `putative_event` before `observe('[putative_event]…')` and `result` between `act(RESOLVE)` and the `[event]` observe, and can emit multiple `[event]` observations (event splitting). The engine is injectable into `Simulation` (`generic.py:50-52, 82`). Limitation: by this point observer queues may already be populated (EventResolution's `notify_observers` ran inside `gm.act`), so pair it with `notify_observers=False` + `SendEventToRelevantPlayers` (post_act, also inside act) or option 1.
3. **GM context component `post_act` hook (side-effect only).** Components receive the resolved event via `post_act(action_attempt)` when the last spec was RESOLVE — the pattern used by `SendEventToRelevantPlayers` (`event_resolution.py:444-504`) and `WorldState` (`world_state.py:99-138`). Suitable for auditing/vetoing observation delivery, **not** for changing the committed event: `EntityAgent.act` discards `post_act` return values (`agents/entity_agent.py:174`).

## F. Best-supported complete-simulation checkpoint/restore path, and the SWORLDMODEL sidecar gap

**Best-supported path** (VERIFIED, §8): `generic.Simulation` with `play(checkpoint_path=…)` → per-step `step_{n}_checkpoint.json` via `save_checkpoint` (`generic.py:518-537`, called from the engine after every step, `sequential.py:361-362`), or programmatic `make_checkpoint_data()` / `get_state_callback` (`generic.py:277-281, 333-380`); restore via a **freshly constructed `Simulation` with the same `Config`** + `load_from_checkpoint(dict)` (`generic.py:539-644`), then `play()` again. Round-trip covered by `prefabs/simulation/checkpoint_test.py:84-131`. Captured: every component's `get_state` (including full memory banks with embeddings, observation queues, buffered memories, scene counters via GM memory, next-acting cursors, prefab type + JSON-able params, role), `raw_log`, `checkpoint_counter`.

**What a SWORLDMODEL sidecar must still capture** (each gap VERIFIED at cited lines in §8/§13; list assembly INFERRED):
1. **RNG**: per-document `np.random.default_rng()` (unseedable from outside, `interactive_document.py:67`) and global `random` state — required for replayable branches; practically means patching/seeding both at branch boundaries.
2. **Engine cursor**: step count, active GM, and premise-already-delivered flag; on resume `run_loop` restarts at `game_masters[0]`, `steps=0`, and re-observes the premise (`sequential.py:242-247`; `generic.py:267-306`). Sidecar should record remaining-step budget and pass `premise=''` on resume.
3. **Config identity**: the `Config`/prefab objects, `scenes` lists, model name/params, embedder identity (embeddings are stored, but *new* memories need the same embedder to be comparable), and any non-JSON params silently dropped by `_make_json_serializable` (`generic.py:382-404`).
4. **Telemetry**: `Measurements` channel histories and `SimulationLog` content store (only `raw_log` is checkpointed; measurements objects are dropped — `checkpoint_test.py:133-150`).
5. **In-flight step artifacts** if branching mid-step (putative event delivered but not resolved; observer queues filled but not drained) — partially covered by `EventResolution`/`MakeObservation` state but only coherent at step boundaries; the safe branch point is the engine's `checkpoint_callback`, which fires only at end-of-step (`sequential.py:361-362`).
6. **`StepController` state** and any wrapper-model counters (`CallLimitLanguageModel._calls`, `call_limit_wrapper.py:44-45`).

---

### Cross-cutting findings most load-bearing for the migration

1. **The event pipeline has exactly one commit primitive** — `gm.observe('[event] …')` issued by the engine (`sequential.py:170`) — and one fully-supported pre-commit hook chain (`event_resolution_steps`). The guard design in (E) does not require forking any class.
2. **The default GM is maximally permissive**: no terminate component (LLM decides ending), LLM-invented observations on empty queue, LLM-chosen observers, and a random-narrative-injection step in the default resolution chain (§B). Restriction = swap/parameterize components, not patch code.
3. **Determinism is not reachable via configuration alone** even with `NoLanguageModel`, because of unseeded per-document numpy RNG and global `random` (§13).
4. **Checkpointing is step-granular and component-complete but not process-complete** (§F): engine cursor, RNG, and telemetry are the sidecar's responsibility.
5. The audit environment (Python 3.11, no deps) could not execute the package; all runtime claims above rest on code reading plus the two import probes documented in §C/D. [The run's engine env at Python 3.12.3 subsequently executed the full suite: 560 core tests passed — see PHASE0_BASELINE.md.]
