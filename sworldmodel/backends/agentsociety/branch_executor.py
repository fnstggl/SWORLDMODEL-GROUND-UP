"""Distributed branch executor (Stage A): complete branches as worker jobs.

``run_candidates_distributed`` mirrors the local manager
(``sworldmodel.counterfactuals.manager.run_candidates_detailed``) exactly
up to the execution substrate: the SAME pre-flight validation, the SAME
single frozen base plan and genesis snapshot, the SAME per-candidate
branch plans (exactly one intervention each, proven by diff), the SAME
code-owned per-branch seed derivation -- then executes every branch as
one complete, self-contained job through AgentSociety's real public
worker/dispatcher interfaces instead of the local serial loop:

    init_dispatchers() -> build_service_proxy(env=None, trace=...)
    -> create_agents_batch.remote (one workspace per branch)
    -> step_agent_batch.remote([one_branch], ...)  x N, bounded in flight

(audit AGENTSOCIETY_AUDIT.md section A, Option 2 -- the primitives that
return the per-agent ok/error records and token deltas the stock society
driver discards).  Engine internals stay untouched: inside every worker
the branch runs through the unchanged ``concordia_local`` runner under
the local manager's own seeded-determinism scope, so local and
distributed runs are equivalent under deterministic models.

Custom-agent registration (Phase 2 finding #3): the branch-agent class
must be resolvable INSIDE each Ray worker, and driver-side registry
writes do not propagate.  The executor therefore materializes the
``branch_agent_template`` source text into
``<workspace>/custom/agents/`` and exports ``WORKSPACE_PATH`` (plus a
PYTHONPATH covering this repository) BEFORE ``init_dispatchers()``, so
the env snapshot Ray copies into workers lets every worker's registry
scanner find the class.  When Ray is already initialized by the caller
(for example a test session fixture), the executor materializes the
agent into the ALREADY-CAPTURED ``WORKSPACE_PATH`` instead -- the env
snapshot cannot be changed retroactively -- and a one-task worker probe
verifies, before any branch is submitted, that workers can import
``sworldmodel``, the engine runner, and the model-spec module, and can
resolve the agent class.

Model injection is a SERIALIZABLE SPEC, never a live object:
``model_spec = {"model_builder": "<package.module:attribute>",
"params": {...json...}}``.  Workers import the dotted reference and call
``builder(params)`` to obtain the local manager's model-provider
contract ``provider(candidate, branch_seed) -> (actor_models,
gm_model)``; the driver resolves and builds the same provider once,
purely to fail fast on a bad reference and to satisfy the shared
pre-flight (the driver never calls it).  Deterministic test models are
registered the same way (a test-owned module importable in workers);
production live-model specs use the same seam with a builder that
constructs API-backed model objects from the params -- builders must be
cheap and side-effect-free, deferring model construction to the provider
call inside the worker.

Result collection is FILE-AUTHORITATIVE with dual-channel agreement
(audit section 9: the stock driver silently drops step results; Option 2
returns them, and this executor keeps BOTH channels and refuses any
disagreement):

- driver ok=True requires ``state/branch_result.json`` (the strict
  ``BranchResult`` the worker wrote atomically) plus
  ``state/runner_record.json`` (raw runner record; guard interventions
  ride here per the recorded decision) and NO error file -- a missing or
  contradicting file raises ``CollectionIntegrityError`` naming the
  branch, never a silent partial success;
- driver ok=False requires ``state/branch_error.json``; a persisted
  partial result (mid-branch failure escalated by the agent) is loaded
  with its partial trace preserved, otherwise a failure ``BranchResult``
  is synthesized in the local manager's reported-never-hidden shape;
- ACCOUNTING is exactly-once (every candidate is submitted exactly once
  and harvested exactly once, enforced by the loud accounting
  equalities); EXECUTION is fail-loud-once: both submit sites pin
  ``.options(max_retries=0)``, so a worker crash (e.g. SIGKILL/OOM)
  surfaces exactly once as Ray's typed error in the harvest loop's
  ``task_error`` arm and is synthesized as a reported ``driver_only``
  failure ``BranchResult`` -- never silently re-executed by Ray's
  default task-retry policy (a silent re-run would double-spend live
  model calls and, for a workspace already carrying a checkpoint blob,
  invert the deliberate interrupt/resume protocol).  Recovery is an
  explicit re-run;
- the returned ``execution_report`` carries the full id accounting,
  per-branch worker pid / start / stop, the driver's submit-window
  ceiling, the measured worker-overlap ceiling, token totals, and the
  worker probe.

Concurrency is enforced IN CODE by a submit-window loop (at most
``parallelism`` single-branch tasks in flight, via ``ray.wait``) --
never by trusting the Ray CPU budget alone -- and observed concurrency
is measured from in-worker step timestamps.

Stage B (whole-branch persistence and recovery) extends this executor
without changing the Stage A path: ``run_candidates_distributed(...,
checkpoint_after=k)`` makes every branch persist its whole-branch
checkpoint blob (``state/branch_checkpoint.json``) at the end-of-step
boundary and continue, with the blob required at collection and
referenced from ``artifact_paths``; ``run_interrupted_then_resume``
drives the deliberately interrupted variant -- one batch round halts
every branch AT the checkpoint (no result yet; the driver explicitly
recognizes the interrupted workspace state), a SECOND batch round
resumes each branch from its own workspace to completion, and normal
collection then applies.  The checkpoint content itself is produced and
consumed entirely by ``sworldmodel.backends.concordia_local.checkpoint``
inside the workers; this executor stores, locates, schedules, and
restores it as an opaque versioned artifact.

Import-time dependencies: stdlib + ``sworldmodel`` only, so importing
this module works on Python 3.11 without ``agentsociety2``/``ray``/
``gdm-concordia``; the engine imports happen inside the run call and
degrade with a clear error.  The reuse of ``manager._preflight``,
``manager._result_from_runner`` (worker side), and
``manager._seeded_branch_scope`` (worker side) is deliberate: they are
the single source of truth for request validation, result shaping, and
per-branch seeding, and the completed ``counterfactuals`` package is not
modified by this phase.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sworldmodel.counterfactuals import manager as _local_manager
from sworldmodel.counterfactuals.branch import (apply_intervention,
                                                derive_branch_id)
from sworldmodel.counterfactuals.snapshot import (build_base_plan,
                                                  build_base_snapshot,
                                                  derive_branch_seed)
from sworldmodel.decision.contracts import (BranchResult,
                                            ContractValidationError,
                                            IssueCollector, SCHEMA_VERSION,
                                            ValidationIssue)
from sworldmodel.decision.registry import ContractRegistry
from sworldmodel.decision.validation import validate_semantics

_IMPORT_HELP = (
    "sworldmodel.backends.agentsociety.branch_executor requires the optional "
    "'agentsociety2' and 'ray' packages (engine environment, Python >= 3.12) "
    "with AGENTSOCIETY_LLM_API_KEY exported. 'import sworldmodel' and this "
    "module's import work without them; only run_candidates_distributed "
    "needs them."
)

#: the class name defined by branch_agent_template.py (asserted at
#: materialization time so the two files cannot drift silently)
AGENT_CLASS_NAME = "DistributedBranchAgent"
#: file name the template is materialized under inside custom/agents/
AGENT_MODULE_FILENAME = "distributed_branch_agent.py"
#: per-run directory (under run_dir) holding one workspace per branch
BRANCHES_DIRNAME = "branches"

_TEMPLATE_PATH = Path(__file__).with_name("branch_agent_template.py")

#: evidence file names the template writes (kept in sync by the
#: materialization-time source assertions below)
_RESULT_FILE = "branch_result.json"
_RECORD_FILE = "runner_record.json"
_ERROR_FILE = "branch_error.json"
#: whole-branch checkpoint blob (Stage B); its presence in a workspace
#: switches the agent's next step() into resume mode
_CHECKPOINT_FILE = "branch_checkpoint.json"

#: fixed simulation clock handed to step_agent_batch -- inert for branch
#: execution (the branch's own timeline lives in its plan), constant so
#: reruns are byte-stable
_DEFAULT_TASK_TIME = datetime(2000, 1, 1, 0, 0, 0)
_TASK_TICK = 1


class DistributedExecutionError(RuntimeError):
    """The distributed substrate is unusable or violated its protocol."""


class CollectionIntegrityError(DistributedExecutionError):
    """Result collection would lose or misattribute a branch; the run is
    refused loudly instead of returning a silent partial success."""


@dataclass(frozen=True)
class DistributedCounterfactualRun:
    """Everything one distributed counterfactual run produced.

    Field-compatible with the local ``CounterfactualRun`` (``results``
    holds one ``BranchResult`` per candidate in the CALLER'S order,
    failures reported in place; ``runner_records`` maps candidate_id to
    the raw runner record loaded from the branch workspace -- extended
    with a ``worker_execution`` block -- or ``None`` when the branch
    failed before the runner could return), plus ``execution_report``:
    the distributed accounting record described in the module docstring.
    """

    base_plan: object
    base_plan_content_hash: str
    base_snapshot: object
    branch_plans: dict          # candidate_id -> ConcordiaInitializationPlan
    branch_ids: dict            # candidate_id -> branch_id
    branch_seeds: dict          # candidate_id -> int
    results: tuple              # BranchResult, caller's candidate order
    runner_records: dict        # candidate_id -> raw runner dict | None
    registry: ContractRegistry
    execution_report: dict


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _write_json_atomic(path: Path, payload) -> None:
    """Atomic JSON write (tmp + os.replace; audit caveat U4)."""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _resolve_model_builder(reference: str):
    """Driver-side twin of the template's resolver (the template file is
    source-copied into workspaces, so it cannot share code by import):
    dotted ``package.module:attribute`` / ``package.module.attribute`` ->
    the builder callable.  Used only to FAIL FAST in the driver; workers
    resolve independently."""
    module_name, sep, attribute = str(reference).partition(":")
    if not sep:
        module_name, _, attribute = str(reference).rpartition(".")
    if not module_name or not attribute:
        raise ContractValidationError([ValidationIssue(
            "model_spec.model_builder", "invalid_value",
            f"{reference!r} must be a dotted reference of the form "
            "'package.module:attribute' or 'package.module.attribute'")])
    import importlib
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ContractValidationError([ValidationIssue(
            "model_spec.model_builder", "unknown_reference",
            f"module {module_name!r} is not importable in the driver: "
            f"{exc!r} (workers import the same reference; fix the module "
            "path or PYTHONPATH)")]) from exc
    builder = getattr(module, attribute, None)
    if builder is None:
        raise ContractValidationError([ValidationIssue(
            "model_spec.model_builder", "unknown_reference",
            f"module {module_name!r} has no attribute {attribute!r}")])
    if not callable(builder):
        raise ContractValidationError([ValidationIssue(
            "model_spec.model_builder", "wrong_type",
            f"{reference!r} resolved to a non-callable "
            f"{type(builder).__name__}")])
    return builder


def _builder_module_name(reference: str) -> str:
    module_name, sep, _ = str(reference).partition(":")
    if not sep:
        module_name, _, _ = str(reference).rpartition(".")
    return module_name


def _max_overlap(windows) -> int:
    """Maximum number of simultaneously open (start, stop) windows; ties
    are processed stop-before-start so back-to-back handoffs at the same
    timestamp do not count as overlap."""
    events = []
    for start, stop in windows:
        events.append((start, 1))
        events.append((stop, -1))
    events.sort(key=lambda event: (event[0], event[1]))
    current = peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def _flatten_token_stats(nested) -> dict:
    """AgentSociety per-task token deltas ``{model: {calls, input,
    output}}`` (shape pinned by the Phase 2 contracts) -> the flat
    non-negative-int map the ``BranchResult`` contract requires.  A shape
    violation is refused, never coerced silently."""
    flat: dict = {}
    if nested is None:
        return flat
    if not isinstance(nested, dict):
        raise CollectionIntegrityError(
            "token_stats returned by the worker task is not a mapping: "
            f"{type(nested).__name__}")
    for model_name, delta in nested.items():
        if not isinstance(model_name, str) or not isinstance(delta, dict):
            raise CollectionIntegrityError(
                f"token_stats entry {model_name!r} does not match the "
                "audited {model: {calls, input, output}} shape: "
                f"{delta!r}")
        for key, value in delta.items():
            if type(value) is not int or value < 0:
                raise CollectionIntegrityError(
                    f"token_stats[{model_name!r}][{key!r}] must be a "
                    f"non-negative integer, got {value!r}")
            flat[f"{model_name}.{key}"] = value
    return flat


def _merge_flat_token_stats(total: dict, flat: dict) -> None:
    for key, value in flat.items():
        total[key] = total.get(key, 0) + value


# ---------------------------------------------------------------------------
# Workspace materialization
# ---------------------------------------------------------------------------

def materialize_branch_agent(workspace_root) -> Path:
    """Copy the branch-agent template SOURCE into
    ``<workspace_root>/custom/agents/`` (plus the ``custom/envs/``
    directory the registry's workspace resolution also recognizes).
    Idempotent: an identical existing file is left untouched; a different
    one is atomically replaced.  Returns the materialized file path.
    """
    source = _TEMPLATE_PATH.read_text(encoding="utf-8")
    for needle in (f"class {AGENT_CLASS_NAME}(AgentBase)",
                   _RESULT_FILE, _RECORD_FILE, _ERROR_FILE,
                   _CHECKPOINT_FILE, "branch_execution"):
        if needle not in source:
            raise DistributedExecutionError(
                "branch_agent_template.py drifted from the executor's "
                f"expectations: {needle!r} not found in the template "
                "source")
    root = Path(workspace_root)
    agents_dir = root / "custom" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (root / "custom" / "envs").mkdir(parents=True, exist_ok=True)
    target = agents_dir / AGENT_MODULE_FILENAME
    if target.exists() and target.read_text(encoding="utf-8") == source:
        return target
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    tmp.write_text(source, encoding="utf-8")
    os.replace(tmp, target)
    return target


# ---------------------------------------------------------------------------
# Engine bring-up (lazy, guarded)
# ---------------------------------------------------------------------------

def _import_engine():
    try:
        import ray
        from agentsociety2.agent import runner as as2_runner
        from agentsociety2.agent.service_proxy import build_service_proxy
    except ImportError as exc:
        raise ImportError(f"{_IMPORT_HELP} (root cause: {exc!r})") from exc
    return ray, as2_runner, build_service_proxy


def _ensure_pythonpath_for_workers() -> None:
    """Workers only inherit the driver's PYTHONPATH env var (captured by
    init_dispatchers' job config); make sure this repository's root is on
    it so workers can import ``sworldmodel``."""
    import sworldmodel
    root = str(Path(sworldmodel.__file__).resolve().parents[1])
    parts = [part for part in
             os.environ.get("PYTHONPATH", "").split(os.pathsep) if part]
    if root not in parts:
        os.environ["PYTHONPATH"] = os.pathsep.join([root] + parts)


def _ensure_dispatchers(ray, run_dir: Path) -> Path:
    """Bring Ray up through the stock ``init_dispatchers`` path (or adopt
    an existing initialization) and return the EFFECTIVE workspace root
    workers use for custom-agent discovery."""
    from agentsociety2.config.llm_dispatcher import init_dispatchers

    if ray.is_initialized():
        current = os.environ.get("WORKSPACE_PATH", "").strip()
        if not current:
            raise DistributedExecutionError(
                "Ray is already initialized but WORKSPACE_PATH is unset; "
                "the env snapshot workers received cannot resolve any "
                "custom agent. Initialize Ray through this executor (with "
                "Ray down), or export WORKSPACE_PATH before the first "
                "init_dispatchers() call.")
        workspace = Path(os.path.realpath(os.path.expanduser(current)))
        if workspace != run_dir:
            # The env snapshot is frozen at first init: register the agent
            # in the workspace workers actually scan.
            materialize_branch_agent(workspace)
        return workspace

    workspace = Path(os.path.realpath(str(run_dir)))
    os.environ["WORKSPACE_PATH"] = str(workspace)
    _ensure_pythonpath_for_workers()
    asyncio.run(init_dispatchers())
    if not ray.is_initialized():  # pragma: no cover - defensive
        raise DistributedExecutionError(
            "init_dispatchers() returned but Ray reports not initialized")
    return workspace


def _assert_driver_registry_resolves(workspace: Path) -> None:
    """Fail fast in the driver if the stock scanner route cannot register
    the branch agent (workers resolve independently; the probe below
    verifies their side)."""
    from agentsociety2.registry import get_agent_module_class, get_registry

    get_registry().set_workspace(workspace)
    cls = get_agent_module_class(AGENT_CLASS_NAME)
    if cls is None or cls.__name__ != AGENT_CLASS_NAME:
        raise DistributedExecutionError(
            f"the custom-agent scanner did not register {AGENT_CLASS_NAME} "
            f"under WORKSPACE_PATH={workspace}; expected file: "
            f"{workspace / 'custom' / 'agents' / AGENT_MODULE_FILENAME}")


def _worker_environment_probe(agent_class_name: str, module_names) -> dict:
    """Executed INSIDE one Ray worker before any branch is submitted."""
    import importlib as _importlib
    import os as _os

    report = {
        "pid": _os.getpid(),
        "workspace_env": _os.environ.get("WORKSPACE_PATH"),
        "modules": {},
        "agent_class": None,
    }
    for name in module_names:
        try:
            _importlib.import_module(name)
            report["modules"][name] = "ok"
        except Exception as exc:  # noqa: BLE001 - reported to the driver
            report["modules"][name] = f"error: {exc!r}"
    try:
        from agentsociety2.registry import get_agent_module_class
        cls = get_agent_module_class(agent_class_name)
        if cls is not None and cls.__name__ == agent_class_name:
            report["agent_class"] = "ok"
        else:
            report["agent_class"] = "missing"
    except Exception as exc:  # noqa: BLE001 - reported to the driver
        report["agent_class"] = f"error: {exc!r}"
    return report


def _probe_worker_environment(ray, builder_reference: str) -> dict:
    """One-task probe: workers must be able to import ``sworldmodel``,
    the engine runner, the seeding scope, and the model-spec module, and
    must resolve the branch-agent class -- otherwise every branch would
    fail identically and diagnosis would be per-branch guesswork."""
    module_names = (
        "sworldmodel",
        "sworldmodel.counterfactuals.manager",
        "sworldmodel.backends.concordia_local.runner",
        _builder_module_name(builder_reference),
    )
    try:
        report = ray.get(
            ray.remote(_worker_environment_probe).remote(
                AGENT_CLASS_NAME, module_names))
    except Exception as exc:  # noqa: BLE001 - convert to guidance
        raise DistributedExecutionError(
            "the worker environment probe task failed outright; most "
            "likely the repository root was not on PYTHONPATH when "
            "init_dispatchers() first ran, so workers cannot import "
            f"sworldmodel (root cause: {exc!r})") from exc
    problems = [f"{name}: {status}"
                for name, status in report["modules"].items()
                if status != "ok"]
    if report["agent_class"] != "ok":
        problems.append(
            f"agent class {AGENT_CLASS_NAME}: {report['agent_class']}")
    if problems:
        raise DistributedExecutionError(
            "worker environment is not ready for branch execution: "
            + "; ".join(problems) + f" (full probe: {report})")
    return report


# ---------------------------------------------------------------------------
# Request validation (distributed-specific, ahead of the shared preflight)
# ---------------------------------------------------------------------------

def _validate_checkpoint_after(checkpoint_after, max_steps) -> None:
    """Driver-side preflight for the Stage B boundary: the runner inside
    every worker enforces the same rule, but a bad request must fail
    before any workspace is created."""
    if checkpoint_after is None:
        return
    if type(checkpoint_after) is not int \
            or not 1 <= checkpoint_after < max_steps:
        raise ContractValidationError([ValidationIssue(
            "checkpoint_after", "invalid_value",
            "checkpoint_after must be an integer end-of-step boundary in "
            f"[1, {max_steps}) (max_steps={max_steps}), got "
            f"{checkpoint_after!r}")])


def _branch_execution_config(*, branch_id: str, world_id: str, candidate,
                             plan, model_spec: dict, branch_seed: int,
                             max_steps: int, checkpoint_after=None,
                             halt_at_checkpoint: bool = False) -> dict:
    """The write-once ``branch_execution`` mapping one workspace carries
    (single source of truth for BOTH the normal and the interrupt/resume
    submission paths, so the spec shape cannot drift between them).  The
    Stage B keys are added only when a checkpoint was requested, keeping
    Stage A workspaces byte-stable."""
    config = {
        "schema_version": 1,
        "branch_id": branch_id,
        "world_id": world_id,
        "candidate": candidate.to_dict(),
        "plan": plan.to_dict(),
        "model_spec": {
            "model_builder": model_spec["model_builder"],
            "params": model_spec["params"],
        },
        "branch_seed": branch_seed,
        "max_steps": max_steps,
    }
    if checkpoint_after is not None:
        config["checkpoint_after"] = checkpoint_after
        config["halt_at_checkpoint"] = bool(halt_at_checkpoint)
    return config


def _validate_distributed_args(model_spec, parallelism,
                               pre_collect_hook) -> None:
    issues = IssueCollector()
    if not isinstance(model_spec, dict):
        issues.add("model_spec", "wrong_type",
                   "model_spec must be a mapping with 'model_builder' and "
                   f"'params', got {type(model_spec).__name__}")
    else:
        unknown = sorted(set(model_spec) - {"model_builder", "params"})
        for key in unknown:
            issues.add(f"model_spec.{key}", "unknown_field",
                       f"unknown field {key!r} is not part of the model "
                       "spec seam")
        reference = model_spec.get("model_builder")
        if not isinstance(reference, str) or not reference.strip():
            issues.add("model_spec.model_builder", "missing_field",
                       "a non-empty dotted reference string is required")
        params = model_spec.get("params")
        if not isinstance(params, dict):
            issues.add("model_spec.params", "wrong_type",
                       "params must be a mapping (JSON-serializable), got "
                       f"{type(params).__name__}")
        else:
            try:
                json.dumps(params)
            except (TypeError, ValueError) as exc:
                issues.add("model_spec.params", "invalid_value",
                           "params must be JSON-serializable -- workers "
                           f"rebuild models from this spec ({exc})")
    if type(parallelism) is not int or parallelism < 1:
        issues.add("parallelism", "invalid_value",
                   "parallelism must be an integer >= 1, got "
                   f"{parallelism!r}")
    if pre_collect_hook is not None and not callable(pre_collect_hook):
        issues.add("pre_collect_hook", "wrong_type",
                   "pre_collect_hook must be callable when supplied")
    issues.raise_if_any()


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def _load_json_evidence(path: Path, candidate_id: str):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CollectionIntegrityError(
            f"candidate {candidate_id!r}: evidence file {path} exists but "
            f"cannot be read as JSON: {exc!r}") from exc


def _shape_driver_payload(payload, agent_index: int,
                          candidate_id: str) -> dict:
    """Validate one step_agent_batch return value (the exact records the
    stock society driver discards) and normalize the harvest."""
    if not isinstance(payload, dict) \
            or set(payload) != {"results", "token_stats"}:
        raise CollectionIntegrityError(
            f"candidate {candidate_id!r}: step task returned an "
            f"unexpected payload shape: {type(payload).__name__} "
            f"{sorted(payload) if isinstance(payload, dict) else ''}")
    results = payload["results"]
    if not isinstance(results, list) or len(results) != 1:
        raise CollectionIntegrityError(
            f"candidate {candidate_id!r}: a single-branch batch must "
            f"return exactly one per-agent record, got {results!r}")
    record = results[0]
    if not isinstance(record, dict) or record.get("id") != agent_index:
        raise CollectionIntegrityError(
            f"candidate {candidate_id!r}: per-agent record is for id "
            f"{record.get('id') if isinstance(record, dict) else record!r}, "
            f"expected {agent_index} -- collection would misattribute a "
            "branch")
    ok = record.get("ok")
    if ok is True:
        return {"channel": "driver", "driver_ok": True,
                "driver_summary": record.get("summary"),
                "driver_error": None,
                "token_stats": payload["token_stats"]}
    if ok is False:
        return {"channel": "driver", "driver_ok": False,
                "driver_summary": None,
                "driver_error": str(record.get("error")),
                "token_stats": payload["token_stats"]}
    raise CollectionIntegrityError(
        f"candidate {candidate_id!r}: per-agent record carries no boolean "
        f"'ok' flag: {record!r}")


def _rebuild_result_from_file(file_result: dict, *, candidate_id: str,
                              branch_id: str, world_id: str,
                              flat_tokens: dict, extra_runtime: dict,
                              artifact_paths: list) -> BranchResult:
    """The authoritative rebuild: the worker-written contract dict, with
    the driver attaching collected artifact paths and folding in the
    task's token delta and wall-clock accounting."""
    identity = (file_result.get("candidate_id"),
                file_result.get("branch_id"),
                file_result.get("world_id"))
    if identity != (candidate_id, branch_id, world_id):
        raise CollectionIntegrityError(
            f"candidate {candidate_id!r}: the result file identifies "
            f"itself as (candidate={identity[0]!r}, branch={identity[1]!r}, "
            f"world={identity[2]!r}) but the run expected "
            f"(candidate={candidate_id!r}, branch={branch_id!r}, "
            f"world={world_id!r}) -- refusing a misattributed result")
    data = dict(file_result)
    data["token_stats"] = flat_tokens
    runtime = dict(data.get("runtime_stats") or {})
    runtime.update(extra_runtime)
    data["runtime_stats"] = runtime
    data["artifact_paths"] = list(artifact_paths)
    return BranchResult.from_dict(data)


def _synthesized_failure_result(*, branch_id: str, candidate_id: str,
                                world_id: str, error_texts: list,
                                flat_tokens: dict, extra_runtime: dict,
                                artifact_paths: list) -> BranchResult:
    """Mirror of the local manager's reported-never-hidden failure shape
    for a branch that produced no result file (contract rule R3: an
    engine stop without an evaluator verdict is never a failure verdict).
    """
    return BranchResult.from_dict({
        "contract_type": BranchResult.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "branch_id": branch_id,
        "candidate_id": candidate_id,
        "world_id": world_id,
        "terminal_status": _local_manager.STATUS_INCOMPLETE,
        "terminal_world_state": {},
        "event_trace": [],
        "outcome_metrics": {},
        "infrastructure_errors": list(error_texts),
        "token_stats": flat_tokens,
        "runtime_stats": dict(extra_runtime),
        "artifact_paths": list(artifact_paths),
    })


def _collect_branch(*, candidate_id: str, branch_id: str, world_id: str,
                    workspace: Path, harvest: dict,
                    expect_checkpoint: bool = False):
    """One branch: reconcile the driver channel with the workspace files
    (files authoritative) and return
    ``(BranchResult, raw_record_or_None, report_entry)``.

    ``expect_checkpoint=True`` (a run configured with ``checkpoint_after``)
    additionally requires the persisted ``branch_checkpoint.json`` blob
    and references it from the result's ``artifact_paths``; a configured
    checkpoint that never materialized is a loud integrity error, never a
    silent omission."""
    state_dir = workspace / "state"
    result_path = state_dir / _RESULT_FILE
    record_path = state_dir / _RECORD_FILE
    error_path = state_dir / _ERROR_FILE
    checkpoint_path = state_dir / _CHECKPOINT_FILE
    file_result = _load_json_evidence(result_path, candidate_id)
    file_record = _load_json_evidence(record_path, candidate_id)
    file_error = _load_json_evidence(error_path, candidate_id)
    checkpoint_artifacts: list = []
    if expect_checkpoint:
        if _load_json_evidence(checkpoint_path, candidate_id) is None:
            raise CollectionIntegrityError(
                f"candidate {candidate_id!r}: the run was configured with "
                f"checkpoint_after but no checkpoint blob exists at "
                f"{checkpoint_path} -- the persisted-state contract was "
                "not met (an early termination before the boundary must "
                "be diagnosed, not silently accepted)")
        checkpoint_artifacts.append(str(checkpoint_path))

    flat_tokens = _flatten_token_stats(harvest.get("token_stats"))
    task_seconds = max(
        0.0, harvest["harvested_unix"] - harvest["submitted_unix"])
    extra_runtime = {"task_wall_clock_seconds": task_seconds}
    worker_execution = {}
    for source in (file_record, file_error):
        if isinstance(source, dict) \
                and isinstance(source.get("worker_execution"), dict):
            worker_execution = source["worker_execution"]
            break
    started = worker_execution.get("started_unix")
    stopped = worker_execution.get("stopped_unix")
    if isinstance(started, (int, float)) and isinstance(stopped,
                                                        (int, float)):
        extra_runtime["worker_step_seconds"] = max(0.0, stopped - started)

    if harvest["driver_ok"]:
        if file_result is None:
            raise CollectionIntegrityError(
                f"candidate {candidate_id!r}: the driver reported ok=True "
                f"but the authoritative result file {result_path} is "
                "missing -- refusing to return a partial success (a lost "
                "branch is never silent)")
        if file_error is not None:
            raise CollectionIntegrityError(
                f"candidate {candidate_id!r}: the driver reported ok=True "
                f"but an error file exists at {error_path} -- the two "
                "failure-evidence channels disagree")
        if file_result.get("infrastructure_errors"):
            raise CollectionIntegrityError(
                f"candidate {candidate_id!r}: the driver reported ok=True "
                "but the result file records infrastructure errors -- the "
                "branch agent must escalate them; the channels disagree")
        if file_record is None:
            raise CollectionIntegrityError(
                f"candidate {candidate_id!r}: {result_path} exists but the "
                f"runner record {record_path} is missing -- guard-evidence "
                "collection would be silently incomplete")
        artifacts = [str(result_path), str(record_path)] \
            + checkpoint_artifacts
        result = _rebuild_result_from_file(
            file_result, candidate_id=candidate_id, branch_id=branch_id,
            world_id=world_id, flat_tokens=flat_tokens,
            extra_runtime=extra_runtime, artifact_paths=artifacts)
        failure_evidence = "none"
    else:
        driver_error = harvest.get("driver_error") or "unreported"
        if file_result is not None:
            # Mid-branch failure escalated by the agent: the partial
            # result (trace preserved) is authoritative; the error file is
            # required by the template's protocol.
            if file_error is None:
                raise CollectionIntegrityError(
                    f"candidate {candidate_id!r}: the driver reported "
                    "ok=False and a result file exists, but the protocol's "
                    f"error file {error_path} is missing -- inconsistent "
                    "failure evidence")
            if not file_result.get("infrastructure_errors"):
                raise CollectionIntegrityError(
                    f"candidate {candidate_id!r}: the driver reported "
                    "ok=False but the result file records no "
                    "infrastructure errors -- the channels disagree")
            artifacts = [str(result_path), str(record_path),
                         str(error_path)] + checkpoint_artifacts
            if file_record is None:
                artifacts.remove(str(record_path))
            result = _rebuild_result_from_file(
                file_result, candidate_id=candidate_id,
                branch_id=branch_id, world_id=world_id,
                flat_tokens=flat_tokens, extra_runtime=extra_runtime,
                artifact_paths=artifacts)
            failure_evidence = "dual_channel"
        else:
            error_texts = []
            artifacts = []
            if file_error is not None:
                error_texts.append(
                    f"worker ({file_error.get('phase', 'unknown')}): "
                    f"{file_error.get('error', 'unrecorded')}\n"
                    f"{file_error.get('traceback_tail', '')}")
                artifacts.append(str(error_path))
                failure_evidence = "dual_channel"
            else:
                failure_evidence = "driver_only"
            error_texts.append(f"driver: {driver_error}")
            result = _synthesized_failure_result(
                branch_id=branch_id, candidate_id=candidate_id,
                world_id=world_id, error_texts=error_texts,
                flat_tokens=flat_tokens, extra_runtime=extra_runtime,
                artifact_paths=artifacts)

    report_entry = {
        "driver_ok": harvest["driver_ok"],
        "driver_error": harvest.get("driver_error"),
        "channel": harvest["channel"],
        "submitted_unix": harvest["submitted_unix"],
        "harvested_unix": harvest["harvested_unix"],
        "task_wall_clock_seconds": task_seconds,
        "worker_pid": worker_execution.get("pid"),
        "worker_started_unix": started,
        "worker_stopped_unix": stopped,
        "result_file": file_result is not None,
        "record_file": file_record is not None,
        "error_file": file_error is not None,
        "checkpoint_file": checkpoint_path.exists(),
        "failure_evidence": failure_evidence,
    }
    return result, file_record, report_entry


def _claim_branches_root(branches_root: Path) -> None:
    """ATOMICALLY claim the run's branches root: ``mkdir`` with
    ``exist_ok=False`` is the one filesystem operation that both creates
    and asserts exclusivity in a single step, so two concurrent runs (or
    a sequential re-run) can never both pass an exists-check window and
    then silently overwrite each other's ``config.json`` workspaces
    through upstream ``create_agents_batch``.  Any existing directory --
    even an empty one left by an interrupted earlier claim -- is refused
    loudly: every distributed run owns a FRESH run_dir (write-once
    workspaces are part of the evidence contract), and reuse means
    evidence would be overwritten, never merged."""
    try:
        branches_root.mkdir()
    except FileExistsError:
        raise DistributedExecutionError(
            f"branches root {branches_root} already exists; every "
            "distributed run owns a fresh run_dir (write-once "
            "workspaces are part of the evidence contract). The claim "
            "is atomic: an earlier or concurrent run already owns this "
            "run_dir -- choose a fresh one; nothing was overwritten"
        ) from None


# ---------------------------------------------------------------------------
# The executor
# ---------------------------------------------------------------------------

def run_candidates_distributed(
    world,
    candidates,
    *,
    model_spec: dict,
    seed: int,
    max_steps: int,
    evaluator_spec,
    run_dir,
    parallelism: int,
    acting_order: str | None = None,
    agency_guard_enabled: bool = True,
    model_config: dict | None = None,
    registry: ContractRegistry | None = None,
    trace=True,
    task_time: datetime | None = None,
    pre_collect_hook=None,
    checkpoint_after: int | None = None,
) -> DistributedCounterfactualRun:
    """Run every candidate branch as one complete distributed job from
    ONE frozen base; return the full run record (see the module and
    :class:`DistributedCounterfactualRun` docstrings).

    Mirrors ``run_candidates_detailed``'s validation, base freeze, branch
    derivation, and result shapes exactly; adds ``model_spec`` (the
    serializable model seam), ``run_dir`` (workspaces, trace shards,
    ``execution_report.json``), ``parallelism`` (submit-window bound),
    ``trace`` (True / False / a prebuilt TraceProxy, passed to
    ``build_service_proxy``), ``task_time`` (fixed workspace clock), and
    ``pre_collect_hook`` (test/diagnostic seam: called with
    ``{candidate_id: workspace_path}`` after all tasks finish and before
    file collection).

    ``checkpoint_after`` (Stage B) makes every branch persist a
    whole-branch checkpoint blob at that end-of-step boundary and then
    CONTINUE to completion within its single step call; collection then
    requires the blob and references it from ``artifact_paths``.  For the
    deliberately interrupted variant (halt at the boundary, resume with a
    second batch call) use :func:`run_interrupted_then_resume`.
    """
    candidates = tuple(candidates)
    _validate_distributed_args(model_spec, parallelism, pre_collect_hook)
    _validate_checkpoint_after(checkpoint_after, max_steps)

    # Driver-side fail-fast on the spec reference; the built provider also
    # satisfies the shared preflight's model-provider callable contract
    # (the driver never calls it -- workers rebuild their own).
    builder = _resolve_model_builder(model_spec["model_builder"])
    driver_provider = builder(model_spec["params"])
    if not callable(driver_provider):
        raise ContractValidationError([ValidationIssue(
            "model_spec.model_builder", "wrong_type",
            "the builder must return a callable provider(candidate, "
            f"branch_seed); got {type(driver_provider).__name__}")])
    registry = _local_manager._preflight(
        world, candidates, driver_provider, seed, registry)

    base_plan = build_base_plan(
        world, evaluator_spec, max_steps=max_steps,
        acting_order=acting_order,
        agency_guard_enabled=agency_guard_enabled)
    base_hash = base_plan.content_hash()
    if model_config is None:
        model_config = {"model_builder": model_spec["model_builder"]}
    base_snapshot = build_base_snapshot(
        base_plan, seed=seed, model_config=model_config, registry=registry)

    branch_plans: dict = {}
    branch_ids: dict = {}
    branch_seeds: dict = {}
    for candidate in candidates:
        candidate_id = candidate.candidate_id
        branch_id = derive_branch_id(world.world_id, candidate_id)
        if registry.has_branch(branch_id):
            bound = registry.branch_binding(branch_id)
            if bound != (world.world_id, candidate_id):
                raise ContractValidationError([ValidationIssue(
                    "branch_id", "cross_branch_reference",
                    f"branch {branch_id!r} is already registered for "
                    f"world {bound[0]!r} / candidate {bound[1]!r}")])
        else:
            registry.register_branch(branch_id, world.world_id,
                                     candidate_id)
        branch_ids[candidate_id] = branch_id
        branch_plans[candidate_id] = apply_intervention(base_plan, candidate)
        branch_seeds[candidate_id] = derive_branch_seed(seed, candidate_id)

    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    branches_root = run_dir / BRANCHES_DIRNAME
    _claim_branches_root(branches_root)
    materialize_branch_agent(run_dir)

    ray, as2_runner, build_service_proxy = _import_engine()
    effective_workspace = _ensure_dispatchers(ray, run_dir)
    _assert_driver_registry_resolves(effective_workspace)
    probe = _probe_worker_environment(ray, model_spec["model_builder"])

    proxy = build_service_proxy(None, run_dir=run_dir, trace=trace,
                                replay=False)
    trace_dir = str(proxy.trace.trace_dir) if proxy.trace is not None \
        else None
    clock = task_time if task_time is not None else _DEFAULT_TASK_TIME

    items = []
    for index, candidate in enumerate(candidates, start=1):
        candidate_id = candidate.candidate_id
        items.append({
            "id": index,
            "profile": {"id": index, "name": f"branch_{candidate_id}"},
            "config": {
                "branch_execution": _branch_execution_config(
                    branch_id=branch_ids[candidate_id],
                    world_id=world.world_id,
                    candidate=candidate,
                    plan=branch_plans[candidate_id],
                    model_spec=model_spec,
                    branch_seed=branch_seeds[candidate_id],
                    max_steps=max_steps,
                    checkpoint_after=checkpoint_after,
                    halt_at_checkpoint=False),
            },
        })
    created = ray.get(as2_runner.create_agents_batch.remote(
        items, str(branches_root), AGENT_CLASS_NAME))
    if created != len(candidates):
        raise DistributedExecutionError(
            f"create_agents_batch created {created} workspaces for "
            f"{len(candidates)} branches")

    # Submit-window loop: at most ``parallelism`` single-branch tasks in
    # flight, enforced HERE (never by the Ray CPU budget alone).
    pending = deque(
        (index, candidate)
        for index, candidate in enumerate(candidates, start=1))
    in_flight: dict = {}          # ObjectRef -> (index, candidate_id, t)
    harvests: dict = {}           # candidate_id -> harvest record
    submission_order: list = []
    driver_max_in_flight = 0
    while pending or in_flight:
        while pending and len(in_flight) < parallelism:
            index, candidate = pending.popleft()
            # max_retries=0: a crashed worker surfaces exactly once as
            # the typed error in the harvest arm below -- never a silent
            # Ray re-execution (see the module docstring).
            ref = as2_runner.step_agent_batch.options(
                max_retries=0).remote(
                [index], str(branches_root), AGENT_CLASS_NAME,
                _TASK_TICK, clock, proxy)
            in_flight[ref] = (index, candidate.candidate_id, time.time())
            submission_order.append(candidate.candidate_id)
            driver_max_in_flight = max(driver_max_in_flight,
                                       len(in_flight))
        ready, _ = ray.wait(list(in_flight.keys()), num_returns=1)
        for ref in ready:
            index, candidate_id, submitted = in_flight.pop(ref)
            harvest = {"agent_index": index, "submitted_unix": submitted,
                       "harvested_unix": time.time()}
            try:
                payload = ray.get(ref)
            except Exception as exc:  # noqa: BLE001 - whole-task failure
                harvest.update({"channel": "task_error",
                                "driver_ok": False,
                                "driver_summary": None,
                                "driver_error": repr(exc),
                                "token_stats": {}})
            else:
                harvest.update(_shape_driver_payload(payload, index,
                                                     candidate_id))
            if candidate_id in harvests:
                raise CollectionIntegrityError(
                    f"candidate {candidate_id!r} harvested twice -- "
                    "exactly-once accounting violated")
            harvests[candidate_id] = harvest

    expected_ids = [candidate.candidate_id for candidate in candidates]
    if submission_order != expected_ids:
        raise CollectionIntegrityError(
            f"submission accounting mismatch: submitted "
            f"{submission_order}, expected {expected_ids}")
    if sorted(harvests) != sorted(expected_ids):
        missing = sorted(set(expected_ids) - set(harvests))
        extra = sorted(set(harvests) - set(expected_ids))
        raise CollectionIntegrityError(
            f"harvest accounting mismatch: missing {missing}, "
            f"unexpected {extra}")

    workspaces = {
        candidate.candidate_id: branches_root / f"agent_{index:04d}"
        for index, candidate in enumerate(candidates, start=1)}
    if pre_collect_hook is not None:
        pre_collect_hook(dict(workspaces))

    results: list = []
    runner_records: dict = {}
    per_branch: dict = {}
    token_totals: dict = {}
    for candidate in candidates:
        candidate_id = candidate.candidate_id
        result, record, report_entry = _collect_branch(
            candidate_id=candidate_id,
            branch_id=branch_ids[candidate_id],
            world_id=world.world_id,
            workspace=workspaces[candidate_id],
            harvest=harvests[candidate_id],
            expect_checkpoint=checkpoint_after is not None)
        validate_semantics(result, registry)
        results.append(result)
        runner_records[candidate_id] = record
        report_entry["agent_index"] = harvests[candidate_id]["agent_index"]
        report_entry["workspace"] = str(workspaces[candidate_id])
        per_branch[candidate_id] = report_entry
        _merge_flat_token_stats(token_totals, dict(result.token_stats))

    collected_ids = [result.candidate_id for result in results]
    if collected_ids != expected_ids:
        raise CollectionIntegrityError(
            f"collection accounting mismatch: collected {collected_ids}, "
            f"expected {expected_ids}")

    windows = [
        (entry["worker_started_unix"], entry["worker_stopped_unix"])
        for entry in per_branch.values()
        if isinstance(entry["worker_started_unix"], (int, float))
        and isinstance(entry["worker_stopped_unix"], (int, float))]
    execution_report = {
        "schema_version": 1,
        "agent_class": AGENT_CLASS_NAME,
        "workspace_root": str(effective_workspace),
        "branches_root": str(branches_root),
        "trace_dir": trace_dir,
        "checkpoint_after": checkpoint_after,
        "parallelism_limit": parallelism,
        "driver_max_in_flight": driver_max_in_flight,
        "worker_max_overlap": _max_overlap(windows) if windows else 0,
        "measured_windows": len(windows),
        "expected_candidate_ids": expected_ids,
        "submitted_candidate_ids": submission_order,
        "harvested_candidate_ids": sorted(harvests),
        "collected_candidate_ids": collected_ids,
        "exactly_once": True,   # every mismatch above raised instead
        "created_workspaces": created,
        "worker_probe": probe,
        "token_stats_total": token_totals,
        "per_branch": per_branch,
    }
    _write_json_atomic(run_dir / "execution_report.json", execution_report)

    return DistributedCounterfactualRun(
        base_plan=base_plan,
        base_plan_content_hash=base_hash,
        base_snapshot=base_snapshot,
        branch_plans=branch_plans,
        branch_ids=branch_ids,
        branch_seeds=branch_seeds,
        results=tuple(results),
        runner_records=runner_records,
        registry=registry,
        execution_report=execution_report)


# ---------------------------------------------------------------------------
# Stage B: deliberate interrupt at the checkpoint boundary + resume by a
# SECOND step_agent_batch call from the same workspace
# ---------------------------------------------------------------------------

def _submit_step_round(ray, as2_runner, proxy, clock, branches_root: Path,
                       indexed_candidates, parallelism: int):
    """One bounded submit-window round over ``[(agent_index,
    candidate_id), ...]``: at most ``parallelism`` single-branch tasks in
    flight (enforced here via ``ray.wait``, never by the Ray CPU budget
    alone).  Returns ``(harvests, submission_order, max_in_flight)`` with
    exactly-once harvesting enforced."""
    pending = deque(indexed_candidates)
    in_flight: dict = {}
    harvests: dict = {}
    submission_order: list = []
    max_in_flight = 0
    while pending or in_flight:
        while pending and len(in_flight) < parallelism:
            index, candidate_id = pending.popleft()
            # max_retries=0: fail-loud-once, same policy as the primary
            # submit site (see the module docstring).
            ref = as2_runner.step_agent_batch.options(
                max_retries=0).remote(
                [index], str(branches_root), AGENT_CLASS_NAME,
                _TASK_TICK, clock, proxy)
            in_flight[ref] = (index, candidate_id, time.time())
            submission_order.append(candidate_id)
            max_in_flight = max(max_in_flight, len(in_flight))
        ready, _ = ray.wait(list(in_flight.keys()), num_returns=1)
        for ref in ready:
            index, candidate_id, submitted = in_flight.pop(ref)
            harvest = {"agent_index": index, "submitted_unix": submitted,
                       "harvested_unix": time.time()}
            try:
                payload = ray.get(ref)
            except Exception as exc:  # noqa: BLE001 - whole-task failure
                harvest.update({"channel": "task_error",
                                "driver_ok": False,
                                "driver_summary": None,
                                "driver_error": repr(exc),
                                "token_stats": {}})
            else:
                harvest.update(_shape_driver_payload(payload, index,
                                                     candidate_id))
            if candidate_id in harvests:
                raise CollectionIntegrityError(
                    f"candidate {candidate_id!r} harvested twice -- "
                    "exactly-once accounting violated")
            harvests[candidate_id] = harvest
    return harvests, submission_order, max_in_flight


def _verify_interrupted_state(candidate_id: str, workspace: Path,
                              harvest: dict) -> dict:
    """Recognize one deliberately interrupted branch after the halt
    round, refusing every other file/driver combination loudly:
    driver ok=True with a ``branch_checkpointed`` summary, the checkpoint
    blob present and JSON-parseable, and NO result/record/error file (the
    branch has produced no result yet -- that is the point)."""
    state_dir = workspace / "state"
    checkpoint_path = state_dir / _CHECKPOINT_FILE
    if not harvest["driver_ok"]:
        raise DistributedExecutionError(
            f"candidate {candidate_id!r}: the checkpoint round failed in "
            f"the driver channel: {harvest.get('driver_error')!r}")
    summary = str(harvest.get("driver_summary") or "")
    if not summary.startswith("branch_checkpointed:") \
            or not summary.endswith(f":{candidate_id}"):
        raise CollectionIntegrityError(
            f"candidate {candidate_id!r}: the checkpoint round returned "
            f"summary {summary!r}, not the interrupted-state marker")
    blob = _load_json_evidence(checkpoint_path, candidate_id)
    if blob is None:
        raise CollectionIntegrityError(
            f"candidate {candidate_id!r}: interrupted state claimed but "
            f"no checkpoint blob exists at {checkpoint_path}")
    for name in (_RESULT_FILE, _RECORD_FILE, _ERROR_FILE):
        if (state_dir / name).exists():
            raise CollectionIntegrityError(
                f"candidate {candidate_id!r}: interrupted state must "
                f"carry ONLY the checkpoint blob, but {name} exists")
    cursor = ((blob.get("sidecar") or {}).get("engine_cursor") or {})
    return {
        "checkpoint_file": str(checkpoint_path),
        "steps_completed": cursor.get("steps_completed"),
        "remaining_steps": cursor.get("remaining_steps"),
    }


def run_interrupted_then_resume(
    world,
    candidates,
    *,
    model_spec: dict,
    seed: int,
    max_steps: int,
    evaluator_spec,
    run_dir,
    parallelism: int,
    checkpoint_after: int,
    acting_order: str | None = None,
    agency_guard_enabled: bool = True,
    model_config: dict | None = None,
    registry: ContractRegistry | None = None,
    trace=True,
    task_time: datetime | None = None,
    between_rounds_hook=None,
) -> DistributedCounterfactualRun:
    """The Stage B distributed gate flow, driven explicitly: every branch
    is INTERRUPTED at the checkpoint boundary and RESUMED by a second
    ``step_agent_batch`` call from its own workspace.

    Round 1 submits every branch with ``halt_at_checkpoint``: each worker
    runs to the end-of-step boundary ``checkpoint_after``, atomically
    persists ``state/branch_checkpoint.json``, and stops WITHOUT writing
    any result -- the driver then verifies the interrupted state
    per branch (checkpoint blob present, no result/record/error file)
    instead of running normal collection.  Round 2 submits the SAME agent
    indices again; each worker's ``step()`` finds the checkpoint blob and
    resumes from it inside the same per-branch seeded scope, completing
    the branch and writing the normal result files, which are collected
    with the standard file-authoritative rules plus the checkpoint blob
    referenced in ``artifact_paths``.

    Accounting: every candidate is submitted exactly once PER ROUND and
    collected exactly once overall; ``execution_report`` records both
    rounds, the per-branch interrupted state, and per-round token deltas
    (the collected ``BranchResult.token_stats`` carries the resume
    round's task delta -- the round split is preserved in the report).
    ``between_rounds_hook({candidate_id: workspace_path})``, when given,
    runs after the interrupt verification and before the resume round
    (test/diagnostic seam, e.g. asserting the interrupted filesystem
    state).

    Base freeze, branch derivation, and result shapes are identical to
    :func:`run_candidates_distributed`; the two entry points share the
    workspace spec builder and the collection path, so results from an
    interrupted-and-resumed run are directly comparable (signature keys)
    with an uninterrupted run of the same request.
    """
    candidates = tuple(candidates)
    _validate_distributed_args(model_spec, parallelism, between_rounds_hook)
    if checkpoint_after is None:
        raise ContractValidationError([ValidationIssue(
            "checkpoint_after", "missing_field",
            "run_interrupted_then_resume requires the explicit "
            "checkpoint boundary")])
    _validate_checkpoint_after(checkpoint_after, max_steps)

    builder = _resolve_model_builder(model_spec["model_builder"])
    driver_provider = builder(model_spec["params"])
    if not callable(driver_provider):
        raise ContractValidationError([ValidationIssue(
            "model_spec.model_builder", "wrong_type",
            "the builder must return a callable provider(candidate, "
            f"branch_seed); got {type(driver_provider).__name__}")])
    registry = _local_manager._preflight(
        world, candidates, driver_provider, seed, registry)

    base_plan = build_base_plan(
        world, evaluator_spec, max_steps=max_steps,
        acting_order=acting_order,
        agency_guard_enabled=agency_guard_enabled)
    base_hash = base_plan.content_hash()
    if model_config is None:
        model_config = {"model_builder": model_spec["model_builder"]}
    base_snapshot = build_base_snapshot(
        base_plan, seed=seed, model_config=model_config, registry=registry)

    branch_plans: dict = {}
    branch_ids: dict = {}
    branch_seeds: dict = {}
    for candidate in candidates:
        candidate_id = candidate.candidate_id
        branch_id = derive_branch_id(world.world_id, candidate_id)
        if registry.has_branch(branch_id):
            bound = registry.branch_binding(branch_id)
            if bound != (world.world_id, candidate_id):
                raise ContractValidationError([ValidationIssue(
                    "branch_id", "cross_branch_reference",
                    f"branch {branch_id!r} is already registered for "
                    f"world {bound[0]!r} / candidate {bound[1]!r}")])
        else:
            registry.register_branch(branch_id, world.world_id,
                                     candidate_id)
        branch_ids[candidate_id] = branch_id
        branch_plans[candidate_id] = apply_intervention(base_plan, candidate)
        branch_seeds[candidate_id] = derive_branch_seed(seed, candidate_id)

    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    branches_root = run_dir / BRANCHES_DIRNAME
    _claim_branches_root(branches_root)
    materialize_branch_agent(run_dir)

    ray, as2_runner, build_service_proxy = _import_engine()
    effective_workspace = _ensure_dispatchers(ray, run_dir)
    _assert_driver_registry_resolves(effective_workspace)
    probe = _probe_worker_environment(ray, model_spec["model_builder"])

    proxy = build_service_proxy(None, run_dir=run_dir, trace=trace,
                                replay=False)
    trace_dir = str(proxy.trace.trace_dir) if proxy.trace is not None \
        else None
    clock = task_time if task_time is not None else _DEFAULT_TASK_TIME

    items = []
    for index, candidate in enumerate(candidates, start=1):
        candidate_id = candidate.candidate_id
        items.append({
            "id": index,
            "profile": {"id": index, "name": f"branch_{candidate_id}"},
            "config": {
                "branch_execution": _branch_execution_config(
                    branch_id=branch_ids[candidate_id],
                    world_id=world.world_id,
                    candidate=candidate,
                    plan=branch_plans[candidate_id],
                    model_spec=model_spec,
                    branch_seed=branch_seeds[candidate_id],
                    max_steps=max_steps,
                    checkpoint_after=checkpoint_after,
                    halt_at_checkpoint=True),
            },
        })
    created = ray.get(as2_runner.create_agents_batch.remote(
        items, str(branches_root), AGENT_CLASS_NAME))
    if created != len(candidates):
        raise DistributedExecutionError(
            f"create_agents_batch created {created} workspaces for "
            f"{len(candidates)} branches")

    expected_ids = [candidate.candidate_id for candidate in candidates]
    workspaces = {
        candidate.candidate_id: branches_root / f"agent_{index:04d}"
        for index, candidate in enumerate(candidates, start=1)}
    indexed = [(index, candidate.candidate_id)
               for index, candidate in enumerate(candidates, start=1)]

    # ---- Round 1: run to the boundary, persist the blob, stop ----------
    halt_harvests, halt_order, halt_in_flight = _submit_step_round(
        ray, as2_runner, proxy, clock, branches_root, indexed, parallelism)
    if halt_order != expected_ids or sorted(halt_harvests) \
            != sorted(expected_ids):
        raise CollectionIntegrityError(
            f"checkpoint-round accounting mismatch: submitted "
            f"{halt_order}, harvested {sorted(halt_harvests)}, expected "
            f"{expected_ids}")
    interrupted: dict = {}
    for candidate_id in expected_ids:
        interrupted[candidate_id] = _verify_interrupted_state(
            candidate_id, workspaces[candidate_id],
            halt_harvests[candidate_id])

    if between_rounds_hook is not None:
        between_rounds_hook(dict(workspaces))

    # ---- Round 2: resume from the workspace, complete, collect ---------
    resume_harvests, resume_order, resume_in_flight = _submit_step_round(
        ray, as2_runner, proxy, clock, branches_root, indexed, parallelism)
    if resume_order != expected_ids or sorted(resume_harvests) \
            != sorted(expected_ids):
        raise CollectionIntegrityError(
            f"resume-round accounting mismatch: submitted {resume_order}, "
            f"harvested {sorted(resume_harvests)}, expected {expected_ids}")

    results: list = []
    runner_records: dict = {}
    per_branch: dict = {}
    token_totals: dict = {}
    for candidate in candidates:
        candidate_id = candidate.candidate_id
        result, record, report_entry = _collect_branch(
            candidate_id=candidate_id,
            branch_id=branch_ids[candidate_id],
            world_id=world.world_id,
            workspace=workspaces[candidate_id],
            harvest=resume_harvests[candidate_id],
            expect_checkpoint=True)
        validate_semantics(result, registry)
        results.append(result)
        runner_records[candidate_id] = record
        report_entry["agent_index"] = \
            resume_harvests[candidate_id]["agent_index"]
        report_entry["workspace"] = str(workspaces[candidate_id])
        report_entry["interrupted_state"] = interrupted[candidate_id]
        report_entry["checkpoint_round"] = {
            "submitted_unix": halt_harvests[candidate_id]["submitted_unix"],
            "harvested_unix": halt_harvests[candidate_id]["harvested_unix"],
            "token_stats": halt_harvests[candidate_id]["token_stats"],
        }
        per_branch[candidate_id] = report_entry
        _merge_flat_token_stats(token_totals, dict(result.token_stats))
        _merge_flat_token_stats(token_totals, _flatten_token_stats(
            halt_harvests[candidate_id]["token_stats"]))

    collected_ids = [result.candidate_id for result in results]
    if collected_ids != expected_ids:
        raise CollectionIntegrityError(
            f"collection accounting mismatch: collected {collected_ids}, "
            f"expected {expected_ids}")

    execution_report = {
        "schema_version": 1,
        "mode": "interrupt_resume",
        "agent_class": AGENT_CLASS_NAME,
        "workspace_root": str(effective_workspace),
        "branches_root": str(branches_root),
        "trace_dir": trace_dir,
        "checkpoint_after": checkpoint_after,
        "parallelism_limit": parallelism,
        "rounds": [
            {"round": 1, "purpose": "run_to_checkpoint_and_halt",
             "submitted_candidate_ids": halt_order,
             "driver_max_in_flight": halt_in_flight},
            {"round": 2, "purpose": "resume_from_workspace",
             "submitted_candidate_ids": resume_order,
             "driver_max_in_flight": resume_in_flight},
        ],
        "interrupted_candidate_ids": expected_ids,
        "expected_candidate_ids": expected_ids,
        "collected_candidate_ids": collected_ids,
        "exactly_once": True,   # every mismatch above raised instead
        "created_workspaces": created,
        "worker_probe": probe,
        "token_stats_total": token_totals,
        "per_branch": per_branch,
    }
    _write_json_atomic(run_dir / "execution_report.json", execution_report)

    return DistributedCounterfactualRun(
        base_plan=base_plan,
        base_plan_content_hash=base_hash,
        base_snapshot=base_snapshot,
        branch_plans=branch_plans,
        branch_ids=branch_ids,
        branch_seeds=branch_seeds,
        results=tuple(results),
        runner_records=runner_records,
        registry=registry,
        execution_report=execution_report)
