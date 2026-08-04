"""Phase 11 scale harness: partitions of scripted shallow agents driven
through AgentSociety's REAL worker/dispatcher primitives.

INFRASTRUCTURE TEST ONLY: everything in this module exercises execution
infrastructure with scripted, deliberately shallow agents --
infrastructure rather than calibrated societal simulation; no population
realism claim.  No LLM calls, no network I/O, anywhere.

Execution path (the audit Option 2 primitives, exactly the Phase 7
branch-executor route):

    init_dispatchers() -> build_service_proxy(env=None, trace=False)
    -> create_agents_batch.remote (one workspace per unit agent)
    -> step_agent_batch.remote([batch of ids], ...) bounded in flight

The custom ``ScaleUnitAgent`` class is materialized as SOURCE into
``<registry_root>/custom/agents/`` for AgentSociety's stock custom-module
scanner (driver-side registry writes do not cross the Ray boundary), and
``WORKSPACE_PATH`` is exported BEFORE the first ``init_dispatchers()``
because the Ray job env snapshot is frozen at first init.

Evidence model (dual channel, reconciled exactly):

- DRIVER LEDGER (``driver/driver_ledger.jsonl``): per-tick activation
  plans (the inspectable sparse-activation record), per-batch harvest
  results with in-flight counts, per-tick completions, sparse-probe
  results, injected-failure records.
- WORKSPACE FILES (``units/agent_<id>/state/``): per-agent append-only
  action log with a tamper-evident hash chain, atomic unit state, and
  structured error artifacts for injected failures.  The files are
  authoritative; :func:`reconcile_partition` refuses ANY disagreement
  (lost, duplicated, out-of-schedule, or out-of-order actions).

Checkpoint/resume: the driver checkpoint (``driver/driver_checkpoint
.json``) plus the persisted workspaces are the whole resumable state; a
fresh process (new Ray runtime) resumes the remaining ticks with
:func:`run_partition` ``resume=True`` and the per-agent hash chains prove
cross-process state continuity.

Partitions are ISOLATED BY DESIGN: disjoint agent-id ranges, disjoint
workspace trees, no cross-partition channel of any kind.  The aggregation
step (:func:`aggregate_partitions`) records that isolation explicitly and
proves the collected aggregate equals the union of per-partition recorded
actions byte-exactly, recomputing from the raw workspace records.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

#: the one statement every evidence artifact must carry (gate-G clause:
#: the system clearly labels this as infrastructure rather than
#: calibrated societal simulation)
INFRA_ONLY_STATEMENT = (
    "INFRASTRUCTURE TEST ONLY: scripted/shallow scale exercise of the "
    "AgentSociety execution substrate -- infrastructure rather than "
    "calibrated societal simulation; no population realism claim."
)

AGENT_CLASS_NAME = "ScaleUnitAgent"
AGENT_MODULE_FILENAME = "scale_unit_agent.py"
_TEMPLATE_PATH = HERE / "scale_agent_template.py"

UNITS_DIRNAME = "units"
DRIVER_DIRNAME = "driver"
STATE_FILE = "unit_state.json"
ACTIONS_FILE = "unit_actions.jsonl"
ERROR_FILE = "unit_error.json"
LEDGER_FILE = "driver_ledger.jsonl"
CHECKPOINT_FILE = "driver_checkpoint.json"
MANIFEST_FILE = "partition_manifest.json"
RECONCILIATION_FILE = "reconciliation.json"
SUMMARY_FILE = "partition_summary.json"
FAILURE_MARKER_PREFIX = "SCALE_INJECTED_UNIT_FAILURE_"

_TASK_TIME_BASE = datetime(2000, 1, 1, 0, 0, 0)


class ScaleHarnessError(RuntimeError):
    """Driver-side harness failure (setup, submission, accounting)."""


class ScaleReconciliationError(ScaleHarnessError):
    """Evidence reconciliation found lost/duplicated/out-of-schedule
    actions or any driver/workspace disagreement."""


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PartitionSpec:
    """Declared, deterministic partition run configuration.

    The activation schedule is fully declared: tick ``t`` activates agent
    ``a`` iff ``t`` is in ``full_ticks`` or ``(a + t) % stride == 0``.
    """

    partition_id: str
    first_agent_id: int
    agent_count: int
    ticks_from: int
    ticks_to: int
    stride: int
    batch_size: int
    window: int
    full_ticks: tuple = ()
    delay_ticks: dict = field(default_factory=dict)   # str(tick) -> seconds
    fail_at: dict = field(default_factory=dict)       # int agent -> int tick
    probe_tick: int | None = None
    overlap_assert_tick: int | None = None
    segments: dict = field(default_factory=dict)      # name -> [from, to]

    @property
    def agent_ids(self) -> tuple:
        return tuple(range(self.first_agent_id,
                           self.first_agent_id + self.agent_count))

    @property
    def ticks(self) -> tuple:
        return tuple(range(self.ticks_from, self.ticks_to + 1))

    def is_activated(self, tick: int, agent_id: int) -> bool:
        if tick in self.full_ticks:
            return True
        return (agent_id + tick) % self.stride == 0

    def activated_ids(self, tick: int) -> list:
        return [a for a in self.agent_ids if self.is_activated(tick, a)]

    def expected_ticks_for(self, agent_id: int) -> list:
        """Expected ACTION ticks: every activated tick, truncated
        strictly before the agent's injected-failure tick."""
        fail_tick = self.fail_at.get(agent_id)
        out = []
        for tick in self.ticks:
            if fail_tick is not None and tick >= fail_tick:
                break
            if self.is_activated(tick, agent_id):
                out.append(tick)
        return out

    def expected_total_actions(self) -> int:
        return sum(len(self.expected_ticks_for(a)) for a in self.agent_ids)

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "statement": INFRA_ONLY_STATEMENT,
            "partition_id": self.partition_id,
            "first_agent_id": self.first_agent_id,
            "agent_count": self.agent_count,
            "ticks_from": self.ticks_from,
            "ticks_to": self.ticks_to,
            "stride": self.stride,
            "batch_size": self.batch_size,
            "window": self.window,
            "full_ticks": list(self.full_ticks),
            "delay_ticks": dict(self.delay_ticks),
            "fail_at": {str(k): v for k, v in self.fail_at.items()},
            "probe_tick": self.probe_tick,
            "overlap_assert_tick": self.overlap_assert_tick,
            "segments": {k: list(v) for k, v in self.segments.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PartitionSpec":
        required = ("partition_id", "first_agent_id", "agent_count",
                    "ticks_from", "ticks_to", "stride", "batch_size",
                    "window")
        missing = [key for key in required if key not in data]
        if missing:
            raise ScaleHarnessError(
                f"partition spec missing keys: {sorted(missing)}")
        return cls(
            partition_id=str(data["partition_id"]),
            first_agent_id=int(data["first_agent_id"]),
            agent_count=int(data["agent_count"]),
            ticks_from=int(data["ticks_from"]),
            ticks_to=int(data["ticks_to"]),
            stride=int(data["stride"]),
            batch_size=int(data["batch_size"]),
            window=int(data["window"]),
            full_ticks=tuple(int(t) for t in data.get("full_ticks", [])),
            delay_ticks={str(k): float(v)
                         for k, v in (data.get("delay_ticks") or {}).items()},
            fail_at={int(k): int(v)
                     for k, v in (data.get("fail_at") or {}).items()},
            probe_tick=(None if data.get("probe_tick") is None
                        else int(data["probe_tick"])),
            overlap_assert_tick=(
                None if data.get("overlap_assert_tick") is None
                else int(data["overlap_assert_tick"])),
            segments={str(k): (int(v[0]), int(v[1]))
                      for k, v in (data.get("segments") or {}).items()},
        )

    @classmethod
    def load(cls, path) -> "PartitionSpec":
        return cls.from_dict(
            json.loads(Path(path).read_text(encoding="utf-8")))

    def validate(self) -> None:
        problems = []
        if self.agent_count < 1 or self.stride < 1 or self.window < 1 \
                or self.batch_size < 1:
            problems.append("agent_count/stride/window/batch_size must "
                            "all be >= 1")
        if self.ticks_from > self.ticks_to:
            problems.append("empty tick range")
        for tick in self.full_ticks:
            if not (self.ticks_from <= tick <= self.ticks_to):
                problems.append(f"full tick {tick} outside the range")
        for tick_str in self.delay_ticks:
            if not (self.ticks_from <= int(tick_str) <= self.ticks_to):
                problems.append(f"delay tick {tick_str} outside the range")
        for agent_id, fail_tick in self.fail_at.items():
            if agent_id not in self.agent_ids:
                problems.append(f"fail_at names foreign agent {agent_id}")
            elif not (self.ticks_from <= fail_tick <= self.ticks_to):
                problems.append(
                    f"fail_at tick {fail_tick} outside the range")
            elif not self.is_activated(fail_tick, agent_id):
                problems.append(
                    f"agent {agent_id} is not activated at its declared "
                    f"failure tick {fail_tick} -- the injection would "
                    "never fire there")
        if self.probe_tick is not None and not (
                self.ticks_from <= self.probe_tick <= self.ticks_to):
            problems.append("probe_tick outside the range")
        if self.overlap_assert_tick is not None \
                and str(self.overlap_assert_tick) not in self.delay_ticks:
            problems.append("overlap_assert_tick must be a delay tick "
                            "(windows are only measurable with a held "
                            "slot)")
        if problems:
            raise ScaleHarnessError(
                f"invalid partition spec {self.partition_id!r}: "
                + "; ".join(problems))

    def content_sha256(self) -> str:
        return sha256_text(json.dumps(self.to_dict(), sort_keys=True))


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json_atomic(path, payload) -> None:
    path = Path(path)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def append_jsonl(path, payload) -> None:
    data = (json.dumps(payload, ensure_ascii=False, sort_keys=True)
            + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def read_jsonl(path) -> list:
    records = []
    path = Path(path)
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def chunked(seq, size: int) -> list:
    seq = list(seq)
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def max_overlap(windows) -> int:
    """Maximum number of half-open ``[start, stop)`` intervals covering
    one instant (ties resolve stop-before-start: conservative)."""
    events = []
    for start, stop in windows:
        events.append((float(start), 1))
        events.append((float(stop), -1))
    events.sort(key=lambda item: (item[0], item[1]))
    current = peak = 0
    for _ts, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def genesis_chain(partition_id: str, agent_id: int) -> str:
    return sha256_text(f"unit-genesis|{partition_id}|{agent_id}")


def next_chain(chain: str, action_id: str, tick: int) -> str:
    return sha256_text(f"{chain}|{action_id}|{tick}")


def unit_dir(units_root, agent_id: int) -> Path:
    """Mirror of the runner's canonical per-agent workspace naming."""
    return Path(units_root) / f"agent_{int(agent_id):04d}"


def hash_unit_workspace(unit_path) -> str:
    """Deterministic content hash of one unit workspace (config,
    AGENT.json, every ``state/`` file) for the sparse no-change probe."""
    unit_path = Path(unit_path)
    parts = []
    candidates = [unit_path / "config.json", unit_path / "AGENT.json"]
    state_dir = unit_path / "state"
    if state_dir.exists():
        candidates.extend(sorted(state_dir.rglob("*")))
    for path in candidates:
        if path.is_file():
            rel = path.relative_to(unit_path).as_posix()
            parts.append(f"{rel}:{sha256_file(path)}")
    return sha256_text("\n".join(parts))


def parse_ok_summary(summary: str) -> dict:
    """Parse ``unit_ok|<id>|<tick>|<seq>|<action_id>|<start>|<stop>``."""
    parts = str(summary).split("|")
    if len(parts) != 7 or parts[0] != "unit_ok":
        raise ScaleHarnessError(
            f"malformed unit step summary: {summary!r}")
    return {
        "agent_id": int(parts[1]),
        "tick": int(parts[2]),
        "seq": int(parts[3]),
        "action_id": parts[4],
        "started_unix": float(parts[5]),
        "stopped_unix": float(parts[6]),
    }


# ---------------------------------------------------------------------------
# Engine bring-up (mirrors the proven branch-executor route)
# ---------------------------------------------------------------------------

def materialize_scale_agent(registry_root) -> Path:
    """Copy the scale-agent template SOURCE into
    ``<registry_root>/custom/agents/`` for the stock scanner.  Idempotent
    and atomic; drift-guarded like the branch executor's helper."""
    source = _TEMPLATE_PATH.read_text(encoding="utf-8")
    for needle in (f"class {AGENT_CLASS_NAME}(AgentBase)", STATE_FILE,
                   ACTIONS_FILE, ERROR_FILE, "scale_execution",
                   FAILURE_MARKER_PREFIX, "unit_ok|"):
        if needle not in source:
            raise ScaleHarnessError(
                "scale_agent_template.py drifted from the harness's "
                f"expectations: {needle!r} not found in the template")
    root = Path(registry_root)
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


def _import_engine():
    try:
        import ray
        from agentsociety2.agent import runner as as2_runner
        from agentsociety2.agent.service_proxy import build_service_proxy
    except ImportError as exc:
        raise ImportError(
            "the scale harness requires the engine environment "
            "(/home/user/engine-env, Python >= 3.12) with agentsociety2 "
            f"and ray installed (root cause: {exc!r})") from exc
    return ray, as2_runner, build_service_proxy


def _worker_probe(agent_class_name: str) -> dict:
    """Executed INSIDE one Ray worker before any batch is submitted."""
    import os as _os

    report = {"pid": _os.getpid(),
              "workspace_env": _os.environ.get("WORKSPACE_PATH"),
              "agent_class": None}
    try:
        from agentsociety2.registry import get_agent_module_class
        cls = get_agent_module_class(agent_class_name)
        report["agent_class"] = ("ok" if cls is not None
                                 and cls.__name__ == agent_class_name
                                 else "missing")
    except Exception as exc:  # noqa: BLE001 - reported to the driver
        report["agent_class"] = f"error: {exc!r}"
    return report


def ensure_engine(registry_root):
    """Bring the engine up (or adopt an existing initialization), with
    the agent registered for BOTH the driver and the workers.

    Returns ``(ray, as2_runner, build_service_proxy, effective_root,
    probe_report)``.
    """
    registry_root = Path(registry_root)
    registry_root.mkdir(parents=True, exist_ok=True)
    materialize_scale_agent(registry_root)

    ray, as2_runner, build_service_proxy = _import_engine()

    if ray.is_initialized():
        current = os.environ.get("WORKSPACE_PATH", "").strip()
        if not current:
            raise ScaleHarnessError(
                "Ray is already initialized but WORKSPACE_PATH is unset; "
                "the frozen env snapshot cannot resolve any custom agent. "
                "Initialize Ray through this harness (with Ray down) or "
                "export WORKSPACE_PATH before the first init_dispatchers().")
        effective = Path(os.path.realpath(os.path.expanduser(current)))
        if effective != registry_root:
            # Env snapshot frozen at first init: register the agent where
            # workers actually scan.
            materialize_scale_agent(effective)
    else:
        effective = Path(os.path.realpath(str(registry_root)))
        os.environ["WORKSPACE_PATH"] = str(effective)
        pythonpath = [part for part in
                      os.environ.get("PYTHONPATH", "").split(os.pathsep)
                      if part]
        for extra in (str(HERE), str(REPO_ROOT)):
            if extra not in pythonpath:
                pythonpath.insert(0, extra)
        os.environ["PYTHONPATH"] = os.pathsep.join(pythonpath)
        from agentsociety2.config.llm_dispatcher import init_dispatchers
        asyncio.run(init_dispatchers())
        if not ray.is_initialized():  # pragma: no cover - defensive
            raise ScaleHarnessError(
                "init_dispatchers() returned but Ray is not initialized")

    from agentsociety2.registry import get_agent_module_class, get_registry
    get_registry().set_workspace(effective)
    cls = get_agent_module_class(AGENT_CLASS_NAME)
    if cls is None or cls.__name__ != AGENT_CLASS_NAME:
        raise ScaleHarnessError(
            f"the custom-agent scanner did not register {AGENT_CLASS_NAME} "
            f"under {effective}")

    probe = ray.get(ray.remote(_worker_probe).remote(AGENT_CLASS_NAME))
    if probe.get("agent_class") != "ok":
        raise ScaleHarnessError(
            f"worker environment cannot resolve {AGENT_CLASS_NAME}: "
            f"{probe}")
    return ray, as2_runner, build_service_proxy, effective, probe


# ---------------------------------------------------------------------------
# Partition run (create / tick loop / checkpoint / resume)
# ---------------------------------------------------------------------------

def _progress(progress_path, payload) -> None:
    if progress_path is None:
        return
    payload = dict(payload)
    payload.setdefault("unix", time.time())
    append_jsonl(progress_path, payload)


def create_partition(spec: PartitionSpec, *, registry_root, partition_root,
                     progress_path=None, create_chunk: int = 50) -> dict:
    """Create every unit workspace of the partition through the REAL
    ``create_agents_batch`` Ray task (chunked for progress records)."""
    spec.validate()
    ray, as2_runner, _build_proxy, _eff, probe = ensure_engine(registry_root)
    partition_root = Path(partition_root)
    units_root = partition_root / UNITS_DIRNAME
    driver_dir = partition_root / DRIVER_DIRNAME
    if units_root.exists() and any(units_root.iterdir()):
        raise ScaleHarnessError(
            f"units root {units_root} already contains entries; every "
            "partition run owns a fresh root (write-once evidence)")
    units_root.mkdir(parents=True, exist_ok=True)
    driver_dir.mkdir(parents=True, exist_ok=True)

    items = []
    for agent_id in spec.agent_ids:
        items.append({
            "id": agent_id,
            "profile": {"id": agent_id, "name": f"unit_{agent_id}"},
            "config": {
                "scale_execution": {
                    "schema_version": 1,
                    "statement": INFRA_ONLY_STATEMENT,
                    "partition_id": spec.partition_id,
                    "delay_ticks": dict(spec.delay_ticks),
                    "fail_at_tick": spec.fail_at.get(agent_id),
                },
            },
        })
    created_total = 0
    for index, chunk in enumerate(chunked(items, create_chunk), start=1):
        created = ray.get(as2_runner.create_agents_batch.remote(
            chunk, str(units_root), AGENT_CLASS_NAME))
        if created != len(chunk):
            raise ScaleHarnessError(
                f"create_agents_batch created {created} workspaces for a "
                f"chunk of {len(chunk)}")
        created_total += created
        _progress(progress_path, {
            "event": "create_chunk_done", "partition": spec.partition_id,
            "chunk_index": index, "created_total": created_total,
            "target": spec.agent_count})
    if created_total != spec.agent_count:
        raise ScaleHarnessError(
            f"created {created_total} unit workspaces, expected "
            f"{spec.agent_count}")

    manifest = {
        "schema_version": 1,
        "statement": INFRA_ONLY_STATEMENT,
        "partition_id": spec.partition_id,
        "spec": spec.to_dict(),
        "spec_sha256": spec.content_sha256(),
        "agent_class": AGENT_CLASS_NAME,
        "units_root": str(units_root),
        "created_total": created_total,
        "worker_probe": probe,
        "created_unix": time.time(),
    }
    write_json_atomic(driver_dir / MANIFEST_FILE, manifest)
    append_jsonl(driver_dir / LEDGER_FILE, {
        "event": "partition_created", "partition": spec.partition_id,
        "created_total": created_total, "unix": time.time()})
    return manifest


def _load_checkpoint(driver_dir: Path) -> dict:
    path = driver_dir / CHECKPOINT_FILE
    if not path.exists():
        raise ScaleHarnessError(
            f"resume requested but no driver checkpoint at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_partition(spec: PartitionSpec, *, registry_root, partition_root,
                  tick_from: int | None = None, tick_to: int | None = None,
                  resume: bool = False, progress_path=None) -> dict:
    """Run the partition's tick range through REAL ``step_agent_batch``
    Ray tasks with a code-enforced submit window.

    ``resume=True`` continues from the persisted driver checkpoint and
    the persisted unit workspaces (a fresh process with a fresh Ray
    runtime resumes seamlessly -- that is the point).  When the range
    ends at the partition's final tick the full reconciliation runs and
    the partition summary is written.
    """
    spec.validate()
    tick_from = spec.ticks_from if tick_from is None else int(tick_from)
    tick_to = spec.ticks_to if tick_to is None else int(tick_to)
    if not (spec.ticks_from <= tick_from <= tick_to <= spec.ticks_to):
        raise ScaleHarnessError(
            f"tick range [{tick_from}, {tick_to}] is outside the spec "
            f"range [{spec.ticks_from}, {spec.ticks_to}]")

    partition_root = Path(partition_root)
    units_root = partition_root / UNITS_DIRNAME
    driver_dir = partition_root / DRIVER_DIRNAME
    ledger_path = driver_dir / LEDGER_FILE

    failed_agents: dict = {}
    if resume:
        checkpoint = _load_checkpoint(driver_dir)
        if checkpoint["spec_sha256"] != spec.content_sha256():
            raise ScaleHarnessError(
                "resume spec mismatch: the driver checkpoint was written "
                f"for spec {checkpoint['spec_sha256'][:12]}..., not "
                f"{spec.content_sha256()[:12]}...")
        if int(checkpoint["next_tick"]) != tick_from:
            raise ScaleHarnessError(
                f"resume expected to continue at tick "
                f"{checkpoint['next_tick']}, but tick_from={tick_from}")
        failed_agents = {int(k): dict(v) for k, v
                         in checkpoint.get("failed_agents", {}).items()}
        if not units_root.exists():
            raise ScaleHarnessError(
                f"resume requested but the persisted units root "
                f"{units_root} does not exist")
        existing = sorted(p.name for p in units_root.iterdir()
                          if p.is_dir())
        if len(existing) != spec.agent_count:
            raise ScaleHarnessError(
                f"resume found {len(existing)} unit workspaces, expected "
                f"{spec.agent_count}")
        ray, as2_runner, build_service_proxy, _eff, _probe = \
            ensure_engine(registry_root)
    else:
        if tick_from != spec.ticks_from:
            raise ScaleHarnessError(
                "a non-resume run must start at the spec's first tick")
        create_partition(spec, registry_root=registry_root,
                         partition_root=partition_root,
                         progress_path=progress_path)
        ray, as2_runner, build_service_proxy, _eff, _probe = \
            ensure_engine(registry_root)

    proxy = build_service_proxy(None, run_dir=driver_dir, trace=False,
                                replay=False)

    run_stats = {
        "partition_id": spec.partition_id,
        "tick_from": tick_from,
        "tick_to": tick_to,
        "resume": resume,
        "driver_max_in_flight": 0,
        "ticks_completed": [],
        "ok_actions": 0,
        "expected_failures": [],
        "started_unix": time.time(),
    }
    append_jsonl(ledger_path, {
        "event": "segment_start", "partition": spec.partition_id,
        "tick_from": tick_from, "tick_to": tick_to, "resume": resume,
        "window": spec.window, "batch_size": spec.batch_size,
        "unix": time.time()})

    for tick in range(tick_from, tick_to + 1):
        scheduled = spec.activated_ids(tick)
        excluded = [a for a in scheduled if a in failed_agents]
        activated = [a for a in scheduled if a not in failed_agents]
        append_jsonl(ledger_path, {
            "event": "tick_plan", "partition": spec.partition_id,
            "tick": tick, "activated": activated,
            "excluded_failed": excluded, "unix": time.time()})

        probe_hashes = None
        if spec.probe_tick == tick:
            inactive = [a for a in spec.agent_ids if a not in activated]
            probe_hashes = {a: hash_unit_workspace(unit_dir(units_root, a))
                            for a in inactive}

        clock = _TASK_TIME_BASE + timedelta(minutes=tick)
        pending = deque(enumerate(chunked(activated, spec.batch_size),
                                  start=1))
        in_flight: dict = {}
        harvested_ids: dict = {}
        tick_ok = 0
        tick_failures = []
        problems = []
        while pending or in_flight:
            while pending and len(in_flight) < spec.window:
                batch_index, ids = pending.popleft()
                ref = as2_runner.step_agent_batch.remote(
                    ids, str(units_root), AGENT_CLASS_NAME, tick, clock,
                    proxy)
                in_flight[ref] = (batch_index, ids, time.time())
                run_stats["driver_max_in_flight"] = max(
                    run_stats["driver_max_in_flight"], len(in_flight))
            if not in_flight:
                break
            ready, _ = ray.wait(list(in_flight.keys()), num_returns=1)
            for ref in ready:
                batch_index, ids, submitted = in_flight.pop(ref)
                try:
                    payload = ray.get(ref)
                except Exception as exc:  # noqa: BLE001 - whole-task failure
                    append_jsonl(ledger_path, {
                        "event": "batch_task_error", "partition":
                        spec.partition_id, "tick": tick,
                        "batch_index": batch_index, "agent_ids": ids,
                        "error": repr(exc), "unix": time.time()})
                    problems.append(
                        f"tick {tick} batch {batch_index}: whole-task "
                        f"failure {exc!r}")
                    continue
                results = payload["results"]
                token_stats = payload.get("token_stats")
                if token_stats != {}:
                    problems.append(
                        f"tick {tick} batch {batch_index}: non-empty "
                        f"token_stats {token_stats!r} from a scripted "
                        "run (no LLM calls happen here)")
                if sorted(r["id"] for r in results) != sorted(ids):
                    problems.append(
                        f"tick {tick} batch {batch_index}: result ids "
                        f"{sorted(r['id'] for r in results)} != submitted "
                        f"{sorted(ids)}")
                for record in results:
                    agent_id = int(record["id"])
                    if agent_id in harvested_ids:
                        problems.append(
                            f"tick {tick}: agent {agent_id} harvested "
                            "twice -- exactly-once accounting violated")
                        continue
                    harvested_ids[agent_id] = record
                    if record.get("ok"):
                        parsed = parse_ok_summary(record["summary"])
                        if parsed["agent_id"] != agent_id \
                                or parsed["tick"] != tick:
                            problems.append(
                                f"tick {tick}: summary identity mismatch "
                                f"{record['summary']!r}")
                        tick_ok += 1
                    else:
                        error_text = str(record.get("error", ""))
                        expected_tick = spec.fail_at.get(agent_id)
                        if expected_tick == tick \
                                and FAILURE_MARKER_PREFIX in error_text:
                            artifact = unit_dir(units_root, agent_id) \
                                / "state" / ERROR_FILE
                            if not artifact.exists():
                                problems.append(
                                    f"tick {tick}: failed agent "
                                    f"{agent_id} left no structured "
                                    f"error artifact at {artifact}")
                            failed_agents[agent_id] = {
                                "tick": tick, "error": error_text[:500]}
                            tick_failures.append(agent_id)
                        else:
                            problems.append(
                                f"tick {tick}: UNEXPECTED per-agent "
                                f"failure for agent {agent_id}: "
                                f"{error_text[:500]}")
                append_jsonl(ledger_path, {
                    "event": "batch_result", "partition": spec.partition_id,
                    "tick": tick, "batch_index": batch_index,
                    "agent_ids": ids, "submitted_unix": submitted,
                    "harvested_unix": time.time(),
                    "results": [
                        {"id": r["id"], "ok": bool(r.get("ok")),
                         **({"summary": r["summary"]} if r.get("ok")
                            else {"error": str(r.get("error"))[:500]})}
                        for r in results],
                    "token_stats": token_stats})
        if sorted(harvested_ids) != sorted(activated):
            problems.append(
                f"tick {tick}: harvested {sorted(harvested_ids)} != "
                f"activated {sorted(activated)}")

        if probe_hashes is not None:
            mismatched = []
            for agent_id, before in probe_hashes.items():
                after = hash_unit_workspace(unit_dir(units_root, agent_id))
                if after != before:
                    mismatched.append(agent_id)
            append_jsonl(ledger_path, {
                "event": "sparse_probe_result", "partition":
                spec.partition_id, "tick": tick,
                "inactive_count": len(probe_hashes),
                "unchanged": not mismatched,
                "mismatched_ids": mismatched, "unix": time.time()})
            if mismatched:
                problems.append(
                    f"tick {tick}: sparse probe found CHANGED workspaces "
                    f"for non-activated agents {mismatched}")

        append_jsonl(ledger_path, {
            "event": "tick_done", "partition": spec.partition_id,
            "tick": tick, "ok_count": tick_ok,
            "failed_now": tick_failures, "unix": time.time()})
        run_stats["ticks_completed"].append(tick)
        run_stats["ok_actions"] += tick_ok
        run_stats["expected_failures"].extend(tick_failures)
        write_json_atomic(driver_dir / CHECKPOINT_FILE, {
            "schema_version": 1,
            "statement": INFRA_ONLY_STATEMENT,
            "partition_id": spec.partition_id,
            "spec_sha256": spec.content_sha256(),
            "next_tick": tick + 1,
            "failed_agents": {str(k): v for k, v in failed_agents.items()},
            "last_completed_tick": tick,
            "unix": time.time(),
        })
        _progress(progress_path, {
            "event": "tick_done", "partition": spec.partition_id,
            "tick": tick, "activated": len(activated),
            "ok": tick_ok, "failed_now": len(tick_failures)})
        if problems:
            append_jsonl(ledger_path, {
                "event": "segment_abort", "partition": spec.partition_id,
                "tick": tick, "problems": problems, "unix": time.time()})
            raise ScaleHarnessError(
                f"partition {spec.partition_id} tick {tick} integrity "
                "problems:\n" + "\n".join(problems))

    run_stats["finished_unix"] = time.time()
    append_jsonl(ledger_path, {
        "event": "segment_done", "partition": spec.partition_id,
        "tick_from": tick_from, "tick_to": tick_to,
        "driver_max_in_flight": run_stats["driver_max_in_flight"],
        "unix": time.time()})
    _progress(progress_path, {
        "event": "segment_done", "partition": spec.partition_id,
        "tick_from": tick_from, "tick_to": tick_to})

    if tick_to == spec.ticks_to:
        reconciliation = reconcile_partition(spec, partition_root)
        _progress(progress_path, {
            "event": "reconcile_done", "partition": spec.partition_id,
            "ok": True, "actions_total":
                reconciliation["counts"]["actions_total"]})
        run_stats["reconciliation_ok"] = True
    return run_stats


# ---------------------------------------------------------------------------
# Reconciliation (files vs ledger vs declared schedule -- exact)
# ---------------------------------------------------------------------------

def reconcile_partition(spec: PartitionSpec, partition_root) -> dict:
    """Reconcile the partition's workspace files, driver ledger, and
    declared schedule EXACTLY; write ``reconciliation.json`` and
    ``partition_summary.json``; raise on any violation."""
    partition_root = Path(partition_root)
    units_root = partition_root / UNITS_DIRNAME
    driver_dir = partition_root / DRIVER_DIRNAME
    violations = []

    ledger = read_jsonl(driver_dir / LEDGER_FILE)
    manifest = json.loads(
        (driver_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    if manifest["spec_sha256"] != spec.content_sha256():
        violations.append("manifest spec hash does not match the spec "
                          "being reconciled")

    # -- ledger side -------------------------------------------------------
    ledger_actions: dict = {}      # (agent_id, tick) -> parsed summary
    ledger_failures: dict = {}     # agent_id -> {tick, error}
    tick_plans: dict = {}          # tick -> {"activated": [...], ...}
    driver_max_in_flight = 0
    token_stats_clean = True
    for record in ledger:
        event = record.get("event")
        if event == "tick_plan":
            tick_plans[int(record["tick"])] = record
        elif event == "segment_done":
            driver_max_in_flight = max(driver_max_in_flight,
                                       int(record["driver_max_in_flight"]))
        elif event == "batch_result":
            if record.get("token_stats") != {}:
                token_stats_clean = False
            for result in record["results"]:
                agent_id = int(result["id"])
                tick = int(record["tick"])
                if result["ok"]:
                    key = (agent_id, tick)
                    if key in ledger_actions:
                        violations.append(
                            f"ledger records agent {agent_id} tick {tick} "
                            "MORE than once (duplicate driver record)")
                    else:
                        ledger_actions[key] = \
                            parse_ok_summary(result["summary"])
                else:
                    if agent_id in ledger_failures:
                        violations.append(
                            f"ledger records more than one failure for "
                            f"agent {agent_id}")
                    ledger_failures[agent_id] = {
                        "tick": tick, "error": result.get("error", "")}
    if not token_stats_clean:
        violations.append("a batch returned non-empty token_stats in a "
                          "scripted run")

    # -- workspace-file side ----------------------------------------------
    per_agent = []
    file_actions: dict = {}        # (agent_id, tick) -> action record
    total_actions = 0
    for agent_id in spec.agent_ids:
        unit = unit_dir(units_root, agent_id)
        state_dir = unit / "state"
        actions = read_jsonl(state_dir / ACTIONS_FILE)
        expected_ticks = spec.expected_ticks_for(agent_id)
        chain = genesis_chain(spec.partition_id, agent_id)
        seen_ticks = []
        for index, action in enumerate(actions, start=1):
            if action.get("agent_id") != agent_id \
                    or action.get("partition_id") != spec.partition_id:
                violations.append(
                    f"agent {agent_id}: action {index} carries foreign "
                    f"identity {action.get('partition_id')}/"
                    f"{action.get('agent_id')}")
            if action.get("seq") != index:
                violations.append(
                    f"agent {agent_id}: seq not contiguous at position "
                    f"{index} (got {action.get('seq')})")
            expected_action_id = \
                f"{spec.partition_id}:{agent_id}:{action.get('seq')}"
            if action.get("action_id") != expected_action_id:
                violations.append(
                    f"agent {agent_id}: action_id "
                    f"{action.get('action_id')!r} != canonical "
                    f"{expected_action_id!r}")
            tick = int(action["tick"])
            if seen_ticks and tick <= seen_ticks[-1]:
                violations.append(
                    f"agent {agent_id}: ticks not strictly increasing at "
                    f"seq {index}")
            seen_ticks.append(tick)
            chain = next_chain(chain, action["action_id"], tick)
            if action.get("chain") != chain:
                violations.append(
                    f"agent {agent_id}: hash chain mismatch at seq "
                    f"{index} (tampered or out-of-order history)")
            key = (agent_id, tick)
            if key in file_actions:
                violations.append(
                    f"agent {agent_id}: DUPLICATE action for tick {tick}")
            file_actions[key] = action
        if seen_ticks != expected_ticks:
            violations.append(
                f"agent {agent_id}: action ticks {seen_ticks} != declared "
                f"schedule {expected_ticks} (lost or extra actions)")

        state_path = state_dir / STATE_FILE
        if actions:
            if not state_path.exists():
                violations.append(f"agent {agent_id}: missing unit state")
            else:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if state.get("seq") != len(actions) \
                        or state.get("chain") != chain \
                        or state.get("last_tick") != seen_ticks[-1]:
                    violations.append(
                        f"agent {agent_id}: unit state disagrees with the "
                        "action log")
        agent_meta = json.loads(
            (unit / "AGENT.json").read_text(encoding="utf-8"))
        if int(agent_meta.get("step_count", -1)) != len(actions):
            violations.append(
                f"agent {agent_id}: AGENT.json step_count "
                f"{agent_meta.get('step_count')} != recorded actions "
                f"{len(actions)} (workspace persistence broken)")

        error_path = state_dir / ERROR_FILE
        fail_tick = spec.fail_at.get(agent_id)
        fail_reached = fail_tick is not None and any(
            tick >= fail_tick for tick in spec.ticks
            if spec.is_activated(tick, agent_id))
        if fail_reached:
            if not error_path.exists():
                violations.append(
                    f"agent {agent_id}: injected failure left no "
                    "structured error artifact")
            else:
                error_payload = json.loads(
                    error_path.read_text(encoding="utf-8"))
                if error_payload.get("agent_id") != agent_id \
                        or FAILURE_MARKER_PREFIX not in str(
                            error_payload.get("error", "")):
                    violations.append(
                        f"agent {agent_id}: error artifact malformed")
            if agent_id not in ledger_failures:
                violations.append(
                    f"agent {agent_id}: injected failure missing from the "
                    "driver ledger (dual channel broken)")
        elif error_path.exists():
            violations.append(
                f"agent {agent_id}: unexpected error artifact present")

        total_actions += len(actions)
        per_agent.append({
            "agent_id": agent_id,
            "n_actions": len(actions),
            "seq_max": len(actions),
            "chain_final": chain if actions else None,
            "actions_file_sha256": (sha256_file(state_dir / ACTIONS_FILE)
                                    if actions else None),
            "failed_at_tick": fail_tick if fail_reached else None,
        })

    # -- cross-channel equality -------------------------------------------
    ledger_ids = sorted(v["action_id"] for v in ledger_actions.values())
    file_ids = sorted(v["action_id"] for v in file_actions.values())
    if ledger_ids != file_ids:
        lost = sorted(set(ledger_ids) - set(file_ids))
        extra = sorted(set(file_ids) - set(ledger_ids))
        violations.append(
            f"driver ledger vs workspace files disagree: in-ledger-only "
            f"{lost[:10]}, in-files-only {extra[:10]}")
    for key, parsed in ledger_actions.items():
        action = file_actions.get(key)
        if action is not None and (
                parsed["seq"] != action["seq"]
                or parsed["action_id"] != action["action_id"]):
            violations.append(
                f"agent {key[0]} tick {key[1]}: ledger/file record "
                "identity mismatch")

    # -- schedule vs ledger plans -----------------------------------------
    failed_since: dict = {a: ledger_failures[a]["tick"]
                          for a in ledger_failures}
    for tick in spec.ticks:
        plan = tick_plans.get(tick)
        if plan is None:
            violations.append(f"tick {tick}: no tick_plan in the ledger")
            continue
        scheduled = spec.activated_ids(tick)
        expect_excluded = sorted(
            a for a in scheduled
            if a in failed_since and failed_since[a] < tick)
        expect_activated = [a for a in scheduled
                            if a not in expect_excluded]
        if sorted(plan["activated"]) != sorted(expect_activated):
            violations.append(
                f"tick {tick}: ledger activation list != declared "
                "schedule")
        if sorted(plan["excluded_failed"]) != expect_excluded:
            violations.append(
                f"tick {tick}: ledger failed-exclusion list "
                f"{sorted(plan['excluded_failed'])} != expected "
                f"{expect_excluded}")
        acted = sorted(a for (a, t) in file_actions if t == tick)
        expect_acted = sorted(
            a for a in expect_activated if spec.fail_at.get(a) != tick)
        if acted != expect_acted:
            violations.append(
                f"tick {tick}: agents with recorded actions {acted} != "
                f"activated-minus-failing {expect_acted}")

    expected_failed = {
        a: t for a, t in spec.fail_at.items()
        if any(tick >= t for tick in spec.ticks
               if spec.is_activated(tick, a))}
    if {a: v["tick"] for a, v in ledger_failures.items()} != expected_failed:
        violations.append(
            f"driver failure records {ledger_failures} != declared "
            f"injections {expected_failed}")

    if total_actions != spec.expected_total_actions():
        violations.append(
            f"total recorded actions {total_actions} != schedule-derived "
            f"expectation {spec.expected_total_actions()}")
    if driver_max_in_flight > spec.window:
        violations.append(
            f"driver max in flight {driver_max_in_flight} exceeded the "
            f"configured window {spec.window}")

    # -- sparse probe ------------------------------------------------------
    probe_records = [r for r in ledger
                     if r.get("event") == "sparse_probe_result"]
    sparse_probe = probe_records[-1] if probe_records else None
    if spec.probe_tick is not None:
        if sparse_probe is None:
            violations.append("declared sparse probe tick produced no "
                              "probe record")
        elif not sparse_probe.get("unchanged"):
            violations.append(
                f"sparse probe found changed non-activated workspaces: "
                f"{sparse_probe.get('mismatched_ids')}")

    # -- concurrency evidence ---------------------------------------------
    overlap_by_tick = {}
    delay_tick_windows = {}
    for tick_str, delay in spec.delay_ticks.items():
        tick = int(tick_str)
        windows = [(a["started_unix"], a["stopped_unix"])
                   for (aid, t), a in file_actions.items() if t == tick]
        pids = {a["pid"] for (aid, t), a in file_actions.items()
                if t == tick}
        overlap_by_tick[tick] = {
            "delay_s": delay,
            "n_windows": len(windows),
            "max_overlap": max_overlap(windows),
            "distinct_pids": len(pids),
            "span_s": (max(w[1] for w in windows)
                       - min(w[0] for w in windows)) if windows else 0.0,
        }
        delay_tick_windows[tick] = sorted(windows)
    bound = spec.window * spec.batch_size
    if spec.overlap_assert_tick is not None:
        tick = spec.overlap_assert_tick
        stats = overlap_by_tick.get(tick)
        if stats is None:
            violations.append(
                f"overlap assert tick {tick} has no recorded windows")
        else:
            delay = stats["delay_s"]
            serial_floor = stats["n_windows"] * delay
            if stats["max_overlap"] > bound:
                violations.append(
                    f"tick {tick}: observed overlap "
                    f"{stats['max_overlap']} EXCEEDS the configured bound "
                    f"{bound} (window {spec.window} x batch "
                    f"{spec.batch_size})")
            if stats["max_overlap"] != bound:
                violations.append(
                    f"tick {tick}: steady-state overlap "
                    f"{stats['max_overlap']} != configured bound {bound} "
                    "(parallelism did not actually happen)")
            if stats["distinct_pids"] < 2:
                violations.append(
                    f"tick {tick}: all windows came from a single worker "
                    "pid -- no real worker parallelism")
            if stats["span_s"] >= serial_floor * 0.9:
                violations.append(
                    f"tick {tick}: wall span {stats['span_s']:.2f}s is "
                    f"not clearly below the serial floor "
                    f"{serial_floor:.2f}s -- execution serialized")
            short = [w for w in delay_tick_windows[tick]
                     if (w[1] - w[0]) < delay * 0.9]
            if short:
                violations.append(
                    f"tick {tick}: {len(short)} windows shorter than the "
                    "scripted delay -- slots were not actually held")

    counts = {
        "agents": spec.agent_count,
        "actions_total": total_actions,
        "expected_actions_total": spec.expected_total_actions(),
        "ledger_ok_records": len(ledger_actions),
        "failed_agents": sorted(ledger_failures),
        "per_tick_actions": {
            str(tick): sum(1 for (a, t) in file_actions if t == tick)
            for tick in spec.ticks},
    }
    identity_files = json.dumps(file_ids, sort_keys=True)
    identity_ledger = json.dumps(ledger_ids, sort_keys=True)
    reconciliation = {
        "schema_version": 1,
        "statement": INFRA_ONLY_STATEMENT,
        "partition_id": spec.partition_id,
        "ok": not violations,
        "violations": violations,
        "counts": counts,
        "driver_max_in_flight": driver_max_in_flight,
        "window": spec.window,
        "batch_size": spec.batch_size,
        "concurrency_bound": bound,
        "overlap_by_tick": {str(k): v for k, v in overlap_by_tick.items()},
        "sparse_probe": sparse_probe,
        "aggregate_sha256": {
            "action_ids_from_files": sha256_text(identity_files),
            "action_ids_from_ledger": sha256_text(identity_ledger),
            "equal": identity_files == identity_ledger,
        },
        "unix": time.time(),
    }
    write_json_atomic(driver_dir / RECONCILIATION_FILE, reconciliation)

    summary = {
        "schema_version": 1,
        "statement": INFRA_ONLY_STATEMENT,
        "partition_id": spec.partition_id,
        "spec": spec.to_dict(),
        "spec_sha256": spec.content_sha256(),
        "counts": counts,
        "driver_max_in_flight": driver_max_in_flight,
        "concurrency_bound": bound,
        "overlap_by_tick": {str(k): v for k, v in overlap_by_tick.items()},
        "overlap_assert_tick": spec.overlap_assert_tick,
        "overlap_windows_at_assert_tick": (
            delay_tick_windows.get(spec.overlap_assert_tick)
            if spec.overlap_assert_tick is not None else None),
        "sparse_probe": sparse_probe,
        "failed_agents": {str(a): ledger_failures[a]
                          for a in sorted(ledger_failures)},
        "per_agent": per_agent,
        "aggregate_sha256": reconciliation["aggregate_sha256"],
        "unix": time.time(),
    }
    write_json_atomic(driver_dir / SUMMARY_FILE, summary)

    if violations:
        raise ScaleReconciliationError(
            f"partition {spec.partition_id} reconciliation FAILED "
            f"({len(violations)} violations):\n" + "\n".join(violations))
    return reconciliation


# ---------------------------------------------------------------------------
# Aggregation across partitions
# ---------------------------------------------------------------------------

def aggregate_partitions(partitions, out_dir, *, progress_path=None) -> dict:
    """Aggregate the completed partitions and PROVE the aggregate equals
    the union of per-partition recorded actions, byte-exactly, by
    recomputing from the raw workspace records.

    ``partitions`` is ``[(PartitionSpec, partition_root), ...]``.  Writes
    ``aggregate_summary.json`` and ``aggregate_reconciliation.json`` into
    ``out_dir``; raises on any violation.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    violations = []
    per_partition = {}
    identity_files_all = []
    identity_ledger_all = []
    raw_records_all = []
    rollup_lines = {}

    seen_ids: dict = {}
    seen_roots: dict = {}
    for spec, root in partitions:
        root = Path(root).resolve()
        if root in seen_roots:
            violations.append(
                f"partitions {seen_roots[root]} and {spec.partition_id} "
                f"share the workspace root {root}")
        seen_roots[root] = spec.partition_id
        for agent_id in spec.agent_ids:
            if agent_id in seen_ids:
                violations.append(
                    f"agent id {agent_id} appears in partitions "
                    f"{seen_ids[agent_id]} and {spec.partition_id}")
            seen_ids[agent_id] = spec.partition_id

        driver_dir = root / DRIVER_DIRNAME
        reconciliation = json.loads(
            (driver_dir / RECONCILIATION_FILE).read_text(encoding="utf-8"))
        summary = json.loads(
            (driver_dir / SUMMARY_FILE).read_text(encoding="utf-8"))
        if not reconciliation.get("ok"):
            violations.append(
                f"partition {spec.partition_id} reconciliation is not ok")
        if summary.get("spec_sha256") != spec.content_sha256():
            violations.append(
                f"partition {spec.partition_id} summary spec hash "
                "mismatch")

        # Raw recomputation: read every unit's action log again.
        file_ids = []
        ledger_ids = []
        units_root = root / UNITS_DIRNAME
        for agent_id in spec.agent_ids:
            for action in read_jsonl(
                    unit_dir(units_root, agent_id) / "state" / ACTIONS_FILE):
                file_ids.append(action["action_id"])
                raw_records_all.append(action)
        for record in read_jsonl(driver_dir / LEDGER_FILE):
            if record.get("event") != "batch_result":
                continue
            for result in record["results"]:
                if result.get("ok"):
                    ledger_ids.append(
                        parse_ok_summary(result["summary"])["action_id"])
        file_ids.sort()
        ledger_ids.sort()
        if sha256_text(json.dumps(file_ids, sort_keys=True)) != \
                summary["aggregate_sha256"]["action_ids_from_files"]:
            violations.append(
                f"partition {spec.partition_id}: raw recomputation does "
                "not match the recorded per-partition aggregate hash")
        identity_files_all.extend(file_ids)
        identity_ledger_all.extend(ledger_ids)

        agent_hash_lines = sorted(
            f"{entry['agent_id']}:{entry['actions_file_sha256']}"
            for entry in summary["per_agent"]
            if entry["actions_file_sha256"] is not None)
        rollup_lines[spec.partition_id] = sha256_text(
            "\n".join(agent_hash_lines))
        per_partition[spec.partition_id] = {
            "partition_root": str(root),
            "agents": spec.agent_count,
            "first_agent_id": spec.first_agent_id,
            "actions_total": summary["counts"]["actions_total"],
            "expected_actions_total":
                summary["counts"]["expected_actions_total"],
            "failed_agents": summary["failed_agents"],
            "per_tick_actions": summary["counts"]["per_tick_actions"],
            "driver_max_in_flight": summary["driver_max_in_flight"],
            "window": spec.window,
            "action_ids_sha256":
                summary["aggregate_sha256"]["action_ids_from_files"],
            "per_agent_rollup_sha256": rollup_lines[spec.partition_id],
        }
        if progress_path is not None:
            append_jsonl(progress_path, {
                "event": "partition_aggregated",
                "partition": spec.partition_id,
                "actions": summary["counts"]["actions_total"],
                "unix": time.time()})

    identity_files_all.sort()
    identity_ledger_all.sort()
    collected = json.dumps(identity_ledger_all, sort_keys=True)
    recomputed = json.dumps(identity_files_all, sort_keys=True)
    if collected != recomputed:
        lost = sorted(set(identity_ledger_all) - set(identity_files_all))
        extra = sorted(set(identity_files_all) - set(identity_ledger_all))
        violations.append(
            "aggregate mismatch between the collected (driver ledger) "
            f"channel and the raw workspace records: collected-only "
            f"{lost[:10]}, files-only {extra[:10]}")
    if len(set(identity_files_all)) != len(identity_files_all):
        violations.append("duplicate action ids inside the aggregate")

    raw_records_all.sort(
        key=lambda a: (a["partition_id"], a["agent_id"], a["seq"]))
    full_records_sha = sha256_text(
        json.dumps(raw_records_all, sort_keys=True))
    total_actions = len(identity_files_all)
    expected_total = sum(
        spec.expected_total_actions() for spec, _root in partitions)
    if total_actions != expected_total:
        violations.append(
            f"aggregate total {total_actions} != schedule-derived "
            f"expectation {expected_total}")

    overall_rollup = sha256_text("\n".join(
        f"{pid}:{rollup_lines[pid]}" for pid in sorted(rollup_lines)))
    aggregate = {
        "schema_version": 1,
        "statement": INFRA_ONLY_STATEMENT,
        "partitions": per_partition,
        "totals": {
            "partitions": len(per_partition),
            "agents": sum(p["agents"] for p in per_partition.values()),
            "actions_total": total_actions,
            "expected_actions_total": expected_total,
            "failed_agents_total": sum(
                len(p["failed_agents"]) for p in per_partition.values()),
        },
        "aggregate_sha256": {
            "action_ids_collected_from_ledgers": sha256_text(collected),
            "action_ids_recomputed_from_workspaces":
                sha256_text(recomputed),
            "equal": collected == recomputed,
            "full_records_from_workspaces": full_records_sha,
            "per_agent_rollup_overall": overall_rollup,
        },
        "isolation": {
            "mode": "isolated_partitions_by_design",
            "cross_partition_channels": [],
            "note": ("partitions exchange NOTHING: disjoint agent-id "
                     "ranges, disjoint workspace trees, no shared mutable "
                     "state; this run records that isolation explicitly "
                     "as its cross-partition communication statement"),
            "workspace_roots": {pid: p["partition_root"]
                                for pid, p in per_partition.items()},
            "agent_ids_disjoint": True,
            "action_ids_unique": len(set(identity_files_all))
            == len(identity_files_all),
        },
        "unix": time.time(),
    }
    write_json_atomic(out_dir / "aggregate_summary.json", aggregate)
    write_json_atomic(out_dir / "aggregate_reconciliation.json", {
        "schema_version": 1,
        "statement": INFRA_ONLY_STATEMENT,
        "ok": not violations,
        "violations": violations,
        "totals": aggregate["totals"],
        "aggregate_sha256": aggregate["aggregate_sha256"],
        "unix": time.time(),
    })
    if progress_path is not None:
        append_jsonl(progress_path, {
            "event": "aggregate_done", "ok": not violations,
            "actions_total": total_actions, "unix": time.time()})
    if violations:
        raise ScaleReconciliationError(
            f"aggregation FAILED ({len(violations)} violations):\n"
            + "\n".join(violations))
    return aggregate
