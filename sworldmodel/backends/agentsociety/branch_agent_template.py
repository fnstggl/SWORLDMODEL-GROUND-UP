"""Distributed branch agent SOURCE (materialized, never imported, by the
executor).

One agent workspace == one counterfactual branch.  ``branch_executor``
copies this file's exact source text into
``<workspace>/custom/agents/distributed_branch_agent.py`` so
AgentSociety's stock custom-module scanner registers the class inside
every Ray worker process (scanner route proven by the Phase 2 contract
suite; driver-side registry writes do not cross the Ray boundary).  The
class therefore satisfies the scanner's acceptance rules: defined in the
file, a direct ``AgentBase`` subclass, no-arg constructible, overrides
``to_workspace`` / ``ask`` / ``step``, non-empty docstring description.

``step`` contract (the whole branch, in-process, exactly once):

1. read the write-once ``config.json`` -> ``branch_execution`` mapping
   {branch_id, world_id, candidate, plan, model_spec, branch_seed,
   max_steps} written by the executor at workspace creation;
2. rebuild the plan and candidate strictly through the Phase 3 contract
   gates; rebuild the model objects from the serializable model spec
   (``model_spec['model_builder']`` is a dotted reference resolving to a
   callable that, given ``model_spec['params']``, returns the local
   manager's model-provider contract ``provider(candidate, branch_seed)
   -> (actor_models, gm_model)``);
3. run the complete branch through the UNCHANGED local engine backend
   (``sworldmodel.backends.concordia_local.runner.run_branch``) inside
   the SAME per-branch seeded determinism scope the local manager uses
   (``sworldmodel.counterfactuals.manager._seeded_branch_scope`` --
   imported, never duplicated).  Safe here because Ray runs one task per
   worker process at a time, so exactly one branch touches this process's
   global RNG state -- the distributed analogue of the local manager's
   "serial on purpose" rule;
4. persist evidence ATOMICALLY (tmp + ``os.replace``; audit caveat U4:
   upstream agent persistence is not atomic, so every file this agent
   owns is):
   - ``state/runner_record.json``  -- the full raw runner record (guard
     interventions ride here per the recorded decision) plus a
     ``worker_execution`` block {pid, started/stopped unix, tick};
   - ``state/branch_result.json``  -- the strict ``BranchResult`` dict
     shaped by the SAME code path as the local manager
     (``_result_from_runner``), with empty ``artifact_paths`` (the
     driver attaches collected paths);
   - ``state/branch_error.json``   -- on ANY failure: exception repr,
     traceback tail, phase, then the exception is RE-RAISED so the
     driver's Option 2 per-agent record also reports ok=False
     (dual-channel failure evidence).  A runner-captured mid-branch
     infrastructure error is escalated the same way AFTER the partial
     result files are written, so the partial trace is never lost.

Importing this module requires the optional ``agentsociety2`` package
(engine environment); without it the import fails with a clear
``ImportError`` while ``import sworldmodel`` stays green -- the executor
reads this file's text and never imports it.
"""

from __future__ import annotations

import importlib
import json
import os
import time
import traceback
from pathlib import Path

_IMPORT_HELP = (
    "sworldmodel.backends.agentsociety.branch_agent_template requires the "
    "optional 'agentsociety2' package (engine environment, Python >= 3.12) "
    "with AGENTSOCIETY_LLM_API_KEY exported. The branch executor only reads "
    "this file's source text; import it directly only where the scanner "
    "would (inside an AgentSociety workspace)."
)

try:
    from agentsociety2.agent.base.agent import AgentBase
except ImportError as exc:  # degrade loudly, never partially
    raise ImportError(f"{_IMPORT_HELP} (root cause: {exc!r})") from exc

#: config.json keys the executor writes and this agent requires
_REQUIRED_SPEC_KEYS = ("schema_version", "branch_id", "world_id",
                       "candidate", "plan", "model_spec", "branch_seed",
                       "max_steps")

#: result/evidence file names under the workspace ``state/`` directory
RESULT_FILE = "branch_result.json"
RECORD_FILE = "runner_record.json"
ERROR_FILE = "branch_error.json"


def _write_json_atomic(path: Path, payload, *, coerce: bool) -> None:
    """Atomic JSON write: serialize fully, write a same-directory temp
    file, then ``os.replace`` (audit caveat U4).  ``coerce=False`` demands
    strictly JSON-representable payloads (contract files); ``coerce=True``
    stringifies foreign objects (diagnostic files only)."""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2,
                      default=str if coerce else None)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _resolve_model_builder(reference: str):
    """Resolve the serializable model-spec dotted reference
    (``package.module:attribute`` or ``package.module.attribute``) to the
    builder callable inside THIS worker process."""
    module_name, sep, attribute = str(reference).partition(":")
    if not sep:
        module_name, _, attribute = str(reference).rpartition(".")
    if not module_name or not attribute:
        raise ValueError(
            f"model_spec.model_builder {reference!r} must be a dotted "
            "reference of the form 'package.module:attribute' or "
            "'package.module.attribute'")
    module = importlib.import_module(module_name)
    builder = getattr(module, attribute, None)
    if builder is None:
        raise ValueError(
            f"model_spec.model_builder {reference!r}: module "
            f"{module_name!r} has no attribute {attribute!r}")
    if not callable(builder):
        raise ValueError(
            f"model_spec.model_builder {reference!r} resolved to a "
            f"non-callable {type(builder).__name__}")
    return builder


class DistributedBranchAgent(AgentBase):
    """Distributed branch agent: runs one complete simulation branch per
    step and persists its result files atomically."""

    async def to_workspace(self, workspace_path):
        workspace_path = Path(workspace_path)
        if self._workspace_root is None:
            self._bind_workspace(workspace_path)
        self.persist_agent_json(tick=None, t=self._current_time)

    async def ask(self, message, readonly=True, *, t=None):
        return f"branch_agent:{self.id}:{message}"

    # ------------------------------------------------------------------
    # step: the whole branch
    # ------------------------------------------------------------------

    async def step(self, tick, t):
        self._step_count += 1
        self._current_time = t
        state_dir = self.workspace_root_path() / "state"
        started = time.time()
        candidate_id = "unknown"
        branch_id = "unknown"
        try:
            spec = self._branch_spec()
            candidate_id = str(spec["candidate"].get("candidate_id",
                                                     candidate_id))
            branch_id = str(spec["branch_id"])
            with self.trace_span(
                "branch.execute",
                attributes={
                    "branch.candidate_id": candidate_id,
                    "branch.id": branch_id,
                    "branch.seed": str(spec["branch_seed"]),
                    "branch.agent_id": self.id,
                },
            ):
                raw, result = self._run_configured_branch(spec)
                stopped = time.time()
                execution = self._execution_info(started, stopped, tick)
                record_payload = dict(raw)
                record_payload["worker_execution"] = execution
                _write_json_atomic(state_dir / RECORD_FILE, record_payload,
                                   coerce=True)
                _write_json_atomic(state_dir / RESULT_FILE, result.to_dict(),
                                   coerce=False)
                if result.infrastructure_errors:
                    # Escalate runner-captured errors AFTER persisting the
                    # partial result, so the driver's Option 2 record also
                    # reports ok=False (dual-channel failure evidence)
                    # while the partial trace survives on disk.
                    first_line = str(result.infrastructure_errors[0]) \
                        .splitlines()[0][:300]
                    escalation = RuntimeError(
                        "branch reported infrastructure errors; first: "
                        f"{first_line}")
                    self._write_error_file(
                        state_dir, escalation, phase="captured_by_runner",
                        details=list(result.infrastructure_errors),
                        started=started, tick=tick,
                        candidate_id=candidate_id, branch_id=branch_id)
                    raise escalation
        except BaseException as exc:
            if not (state_dir / ERROR_FILE).exists():
                self._write_error_file(
                    state_dir, exc, phase="setup_or_run", details=[],
                    started=started, tick=tick,
                    candidate_id=candidate_id, branch_id=branch_id)
            raise
        return f"branch_ok:{self.id}:{candidate_id}"

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _branch_spec(self) -> dict:
        spec = (self._config or {}).get("branch_execution")
        if not isinstance(spec, dict):
            raise ValueError(
                "workspace config.json carries no 'branch_execution' "
                "mapping; this workspace was not created by the branch "
                "executor")
        missing = [key for key in _REQUIRED_SPEC_KEYS if key not in spec]
        if missing:
            raise ValueError(
                "branch_execution config is missing required keys: "
                f"{sorted(missing)}")
        model_spec = spec["model_spec"]
        if not isinstance(model_spec, dict) \
                or "model_builder" not in model_spec \
                or "params" not in model_spec:
            raise ValueError(
                "branch_execution.model_spec must be a mapping with "
                "'model_builder' (dotted reference) and 'params'")
        return spec

    def _run_configured_branch(self, spec: dict):
        """Rebuild contracts and models, run the branch under the local
        manager's seeded scope, and return ``(raw_record, BranchResult)``
        shaped by the local manager's own result builder."""
        from sworldmodel.backends.concordia_local import runner \
            as runner_module
        from sworldmodel.counterfactuals.manager import (
            _result_from_runner, _seeded_branch_scope)
        from sworldmodel.decision.contracts import (
            ConcordiaInitializationPlan, InterventionCandidate)

        plan = ConcordiaInitializationPlan.from_dict(spec["plan"])
        candidate = InterventionCandidate.from_dict(spec["candidate"])
        branch_seed = spec["branch_seed"]
        if type(branch_seed) is not int:
            raise ValueError(
                "branch_execution.branch_seed must be an integer, got "
                f"{type(branch_seed).__name__}")
        declared_max = spec["max_steps"]
        if plan.run_limits.get("max_steps") != declared_max:
            raise ValueError(
                f"branch_execution.max_steps ({declared_max!r}) does not "
                "match the plan's run limit "
                f"({plan.run_limits.get('max_steps')!r}); refusing a "
                "drifted configuration")

        builder = _resolve_model_builder(spec["model_spec"]["model_builder"])
        provider = builder(spec["model_spec"]["params"])
        if not callable(provider):
            raise ValueError(
                "the model builder must return a callable "
                "provider(candidate, branch_seed), got "
                f"{type(provider).__name__}")
        provided = provider(candidate, branch_seed)
        try:
            actor_models, gm_model = provided
        except (TypeError, ValueError):
            raise ValueError(
                "the model provider must return the pair (actor_models, "
                f"gm_model), got {type(provided).__name__}") from None

        with _seeded_branch_scope(branch_seed):
            raw = runner_module.run_branch(
                plan, actor_models=actor_models, gm_model=gm_model)
        result = _result_from_runner(raw, spec["branch_id"],
                                     candidate.candidate_id,
                                     spec["world_id"])
        return raw, result

    def _execution_info(self, started: float, stopped: float,
                        tick) -> dict:
        return {
            "pid": os.getpid(),
            "agent_id": self.id,
            "tick": tick,
            "started_unix": started,
            "stopped_unix": stopped,
            "step_count": self._step_count,
        }

    def _write_error_file(self, state_dir: Path, exc: BaseException, *,
                          phase: str, details: list, started: float,
                          tick, candidate_id: str, branch_id: str) -> None:
        """Best-effort atomic error evidence; never masks the original
        exception (the re-raise carries it to the driver regardless)."""
        try:
            payload = {
                "schema_version": 1,
                "candidate_id": candidate_id,
                "branch_id": branch_id,
                "phase": phase,
                "error": repr(exc),
                "error_type": type(exc).__name__,
                "traceback_tail": traceback.format_exc()[-4000:],
                "details": list(details),
                "worker_execution": self._execution_info(
                    started, time.time(), tick),
            }
            _write_json_atomic(state_dir / ERROR_FILE, payload, coerce=True)
        except Exception:  # noqa: BLE001 - evidence write must not mask exc
            pass
