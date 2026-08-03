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
   max_steps} written by the executor at workspace creation (plus the
   optional Stage B keys ``checkpoint_after`` / ``halt_at_checkpoint``);
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

Whole-branch persistence and recovery (Stage B) extends the SAME step
contract with three explicit modes, selected at ``step()`` entry:

- RESUME: if ``state/branch_checkpoint.json`` exists, the branch resumes
  from it -- ``run_branch(..., resume_from=checkpoint)`` inside the same
  per-branch seeded scope (the runner restores the checkpoint's captured
  mid-run RNG state within that scope) -- and completes: the FULL result
  (restored history + continuation, absolute step accounting) is
  persisted as ``runner_record.json`` + ``branch_result.json`` exactly
  like an uninterrupted run.  The checkpoint file's presence, never a
  config change, is the mode switch: the write-once config stays intact.
- CHECKPOINT-AND-HALT (``checkpoint_after`` set with
  ``halt_at_checkpoint=true``): the branch runs to the end-of-step
  boundary, persists the checkpoint blob ATOMICALLY as
  ``state/branch_checkpoint.json``, writes NO result/record/error file,
  and returns ``branch_checkpointed:...`` -- the deliberately
  interrupted state a second ``step_agent_batch`` call resumes from.
- CHECKPOINT-AND-CONTINUE (``checkpoint_after`` set, halt false): one
  step call both persists the checkpoint blob and completes the branch
  (result files as usual; the blob is popped from the runner record --
  the dedicated file is its home -- while ``checkpoint_captured_at``
  stays in the record as evidence).

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
#: whole-branch checkpoint blob (Stage B); its presence switches step()
#: into resume mode
CHECKPOINT_FILE = "branch_checkpoint.json"


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
        checkpoint_path = state_dir / CHECKPOINT_FILE
        started = time.time()
        candidate_id = "unknown"
        branch_id = "unknown"
        try:
            spec = self._branch_spec()
            candidate_id = str(spec["candidate"].get("candidate_id",
                                                     candidate_id))
            branch_id = str(spec["branch_id"])
            if checkpoint_path.exists():
                mode = "resume"
            elif spec.get("checkpoint_after") is not None:
                mode = ("checkpoint_halt" if spec.get("halt_at_checkpoint")
                        else "checkpoint_continue")
            else:
                mode = "full"
            with self.trace_span(
                "branch.execute",
                attributes={
                    "branch.candidate_id": candidate_id,
                    "branch.id": branch_id,
                    "branch.seed": str(spec["branch_seed"]),
                    "branch.agent_id": self.id,
                    "branch.mode": mode,
                },
            ):
                raw, result = self._run_configured_branch(
                    spec, mode=mode, checkpoint_path=checkpoint_path)
                stopped = time.time()
                execution = self._execution_info(started, stopped, tick)
                captured = raw.pop("checkpoint", None)
                if captured is not None:
                    # The dedicated file is the blob's home; the record
                    # keeps checkpoint_captured_at as evidence.
                    _write_json_atomic(checkpoint_path, captured,
                                       coerce=False)
                if result is None:
                    # Deliberate interrupt: checkpoint persisted, no
                    # result yet -- a second step call resumes from it.
                    return (f"branch_checkpointed:{self.id}:"
                            f"{candidate_id}")
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
        checkpoint_after = spec.get("checkpoint_after")
        if checkpoint_after is not None and (
                type(checkpoint_after) is not int or checkpoint_after < 1):
            raise ValueError(
                "branch_execution.checkpoint_after must be an integer >= 1 "
                f"when present, got {checkpoint_after!r}")
        halt = spec.get("halt_at_checkpoint", False)
        if type(halt) is not bool:
            raise ValueError(
                "branch_execution.halt_at_checkpoint must be a boolean")
        if halt and checkpoint_after is None:
            raise ValueError(
                "branch_execution.halt_at_checkpoint requires "
                "checkpoint_after")
        return spec

    def _run_configured_branch(self, spec: dict, *, mode: str = "full",
                               checkpoint_path: Path | None = None):
        """Rebuild contracts and models, run the branch under the local
        manager's seeded scope, and return ``(raw_record, BranchResult)``
        shaped by the local manager's own result builder.

        ``mode`` selects the Stage B behavior (see the module docstring):
        ``resume`` loads the persisted checkpoint and continues it;
        ``checkpoint_halt`` / ``checkpoint_continue`` request a capture at
        ``spec['checkpoint_after']``.  A halt that actually captured a
        checkpoint returns ``(raw, None)`` -- the caller persists the blob
        and reports the interrupted state; a halt whose run legitimately
        ended BEFORE the boundary returns the normal completed pair.
        """
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

        run_kwargs = {}
        if mode == "resume":
            if checkpoint_path is None or not checkpoint_path.exists():
                raise ValueError(
                    "resume mode requires an existing checkpoint file")
            run_kwargs["resume_from"] = json.loads(
                checkpoint_path.read_text(encoding="utf-8"))
        elif mode in ("checkpoint_halt", "checkpoint_continue"):
            run_kwargs["checkpoint_after"] = spec["checkpoint_after"]
            run_kwargs["halt_at_checkpoint"] = mode == "checkpoint_halt"
            run_kwargs["checkpoint_identity"] = {
                "seed_material": branch_seed,
                "candidate_id": candidate.candidate_id,
                "branch_id": str(spec["branch_id"]),
                "model_config": {
                    "model_builder":
                        str(spec["model_spec"]["model_builder"])},
            }
        elif mode != "full":
            raise ValueError(f"unknown branch execution mode {mode!r}")

        with _seeded_branch_scope(branch_seed):
            raw = runner_module.run_branch(
                plan, actor_models=actor_models, gm_model=gm_model,
                **run_kwargs)
        if mode == "checkpoint_halt" and raw.get("halted_at_checkpoint") \
                and raw.get("checkpoint") is not None \
                and not raw.get("infrastructure_errors"):
            return raw, None
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
