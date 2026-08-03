"""Shared durable-state, git, receipt and classification logic for the control plane.

Every hook path in ``gate.py`` and every tool in ``.claude/tools`` imports from
here. Nothing in this module performs network access, and nothing in it blocks
for an unbounded time: git calls are subprocess calls with hard timeouts.

The module is deliberately dependency-free (Python 3 standard library only) so a
hook can never fail because a virtualenv was not active.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

SCHEMA_VERSION = 1

# --------------------------------------------------------------------------
# Run modes
# --------------------------------------------------------------------------

MODES = (
    "hook_bootstrap",
    "hook_live_verification",
    "ready_for_master",
    "implementation",
    "frozen_acceptance",
    "hook_maintenance",
    "external_blocker",
    "complete",
)

#: Modes in which the hook-control files themselves may be edited.
HOOK_EDIT_MODES = frozenset({"hook_bootstrap", "hook_live_verification", "hook_maintenance"})

#: Modes in which production implementation edits are forbidden.
PRODUCTION_FROZEN_MODES = frozenset(
    {"frozen_acceptance", "ready_for_master", "hook_bootstrap", "hook_live_verification"}
)

#: Modes in which a *freeze* over evaluator/fixture/prompt material applies.
ACCEPTANCE_FROZEN_MODES = frozenset({"frozen_acceptance"})

PLACEHOLDER_TOKEN = "MASTER_DIRECTIVE_PENDING"

MASTER_DIRECTIVE_PATH = "docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md"
MASTER_INIT_TASK_ID = "master-context-initialization"


# --------------------------------------------------------------------------
# Project resolution
# --------------------------------------------------------------------------


def project_dir() -> Path:
    """Resolve the project root.

    ``CLAUDE_PROJECT_DIR`` is set by Claude Code for every spawned hook process
    and is authoritative. Tests set it explicitly to point at synthetic project
    trees. The walk-up fallback keeps the tools usable from a plain shell.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".claude").is_dir() or (candidate / ".git").exists():
            return candidate
    return Path.cwd().resolve()


def agent_run_dir(root: Path | None = None) -> Path:
    return (root or project_dir()) / ".agent-run"


def receipts_dir(root: Path | None = None) -> Path:
    return agent_run_dir(root) / "receipts"


def jobs_dir(root: Path | None = None) -> Path:
    return agent_run_dir(root) / "jobs"


# --------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str):
    """Best-effort ISO-8601 parse. Returns ``None`` rather than raising."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return _dt.datetime.fromisoformat(text)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Atomic IO
# --------------------------------------------------------------------------


class StateError(Exception):
    """Raised when durable state is present but unusable.

    Malformed state is never silently swallowed: callers surface this to the
    model as an explicit failure with the offending path.
    """

    def __init__(self, path, detail: str):
        self.path = str(path)
        self.detail = detail
        super().__init__(f"{self.path}: {detail}")


def atomic_write_text(path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (same-filesystem temp + rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path, obj) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=False) + "\n")


def append_jsonl(path, obj) -> None:
    """Append one JSON record plus newline. Single ``write`` for atomicity."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, sort_keys=False) + "\n"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def read_json(path, *, required: bool = False, default=None):
    """Read JSON, raising :class:`StateError` on malformed content.

    A missing file returns ``default`` unless ``required`` is set.
    """
    path = Path(path)
    if not path.exists():
        if required:
            raise StateError(path, "required state file is missing")
        return default
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StateError(path, f"unreadable: {exc}") from exc
    if not raw.strip():
        raise StateError(path, "file is empty; expected a JSON object")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StateError(path, f"invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}") from exc


def read_text(path, *, default: str = "", limit: int | None = None) -> str:
    path = Path(path)
    if not path.exists():
        return default
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return default
    if limit is not None and len(text) > limit:
        return text[:limit] + "\n... [truncated]"
    return text


def sha256_file(path) -> str | None:
    path = Path(path)
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Git
# --------------------------------------------------------------------------


def _git(root: Path, *args: str, timeout: float = 5.0, strip: bool = True):
    """Run git and return stdout, or ``None`` on any failure.

    ``strip=False`` matters for ``status --porcelain``: its ``XY `` prefix is
    fixed-width and the first column is a space for unstaged changes, so
    stripping would shift the first line and swallow a leading '.' from a path
    such as ``.agent-run/RUN_STATE.json``.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() if strip else proc.stdout.rstrip("\n")


def git_sha(root: Path | None = None) -> str | None:
    return _git(root or project_dir(), "rev-parse", "HEAD")


def git_branch(root: Path | None = None) -> str | None:
    return _git(root or project_dir(), "rev-parse", "--abbrev-ref", "HEAD")


def git_worktree_root(root: Path | None = None) -> str | None:
    return _git(root or project_dir(), "rev-parse", "--show-toplevel")


def git_status_porcelain(root: Path | None = None, *, expand_untracked: bool = True) -> str | None:
    """Porcelain status.

    ``--untracked-files=all`` by default: without it git collapses an untracked
    tree into a single ``dir/`` entry, which a path classifier cannot judge.
    """
    args = ["status", "--porcelain"]
    if expand_untracked:
        args.append("--untracked-files=all")
    return _git(root or project_dir(), *args, strip=False)


def git_is_clean(root: Path | None = None) -> bool | None:
    status = git_status_porcelain(root)
    if status is None:
        return None
    return status == ""


def parse_porcelain_paths(status: str | None) -> list[str]:
    """Extract repository-relative paths from ``git status --porcelain`` output.

    The single porcelain parser for the whole control plane. Each line is
    ``XY <path>``; a rename is ``XY <old> -> <new>`` and only the new path is
    reported.
    """
    if not status:
        return []
    paths: list[str] = []
    for line in status.splitlines():
        if len(line) <= 3:
            continue
        entry = line[3:]
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        entry = entry.strip().strip('"')
        if entry:
            paths.append(entry)
    return paths


def git_dirty_paths(root: Path | None = None) -> list[str]:
    return parse_porcelain_paths(git_status_porcelain(root))


# --------------------------------------------------------------------------
# Durable state accessors
# --------------------------------------------------------------------------

_RUN_STATE_REQUIRED = (
    "schema_version",
    "mode",
    "status",
    "phase",
    "next_action",
    "completion_allowed",
)

_MASTER_CONTEXT_FIELDS = (
    "master_context_loaded",
    "master_directive_path",
    "master_directive_sha256",
    "architecture_initialized",
    "task_graph_initialized",
    "acceptance_gates_initialized",
)


def read_run_state(root: Path | None = None) -> dict:
    """Load and structurally validate ``RUN_STATE.json``.

    Raises :class:`StateError` when the file is missing, malformed, missing a
    required field, or records an unsupported mode. Callers on safety-critical
    paths convert this into a block, never into a silent allow.
    """
    root = root or project_dir()
    path = agent_run_dir(root) / "RUN_STATE.json"
    state = read_json(path, required=True)
    if not isinstance(state, dict):
        raise StateError(path, "expected a JSON object at the top level")
    missing = [field for field in _RUN_STATE_REQUIRED if field not in state]
    if missing:
        raise StateError(path, "missing required field(s): " + ", ".join(missing))
    if state.get("mode") not in MODES:
        raise StateError(
            path,
            "unsupported mode {!r}; supported modes are: {}".format(state.get("mode"), ", ".join(MODES)),
        )
    return state


def read_bootstrap_status(root: Path | None = None) -> dict:
    root = root or project_dir()
    path = agent_run_dir(root) / "HOOK_BOOTSTRAP_STATUS.json"
    status = read_json(path, required=True)
    if not isinstance(status, dict):
        raise StateError(path, "expected a JSON object at the top level")
    if "overall" not in status:
        raise StateError(path, "missing required field: overall")
    return status


def read_acceptance_status(root: Path | None = None) -> dict:
    root = root or project_dir()
    path = agent_run_dir(root) / "ACCEPTANCE_STATUS.json"
    status = read_json(path, required=True)
    if not isinstance(status, dict):
        raise StateError(path, "expected a JSON object at the top level")
    if "overall" not in status:
        raise StateError(path, "missing required field: overall")
    return status


def read_task_graph(root: Path | None = None) -> dict:
    root = root or project_dir()
    path = agent_run_dir(root) / "TASK_GRAPH.json"
    graph = read_json(path, required=True)
    if not isinstance(graph, dict):
        raise StateError(path, "expected a JSON object at the top level")
    tasks = graph.get("tasks")
    if not isinstance(tasks, list):
        raise StateError(path, "field 'tasks' must be a list")
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise StateError(path, f"tasks[{index}] must be an object")
        if not task.get("id"):
            raise StateError(path, f"tasks[{index}] is missing an 'id'")
    return graph


def read_background_jobs(root: Path | None = None) -> dict:
    root = root or project_dir()
    path = agent_run_dir(root) / "BACKGROUND_JOBS.json"
    jobs = read_json(path, required=False, default={"schema_version": SCHEMA_VERSION, "active_jobs": [], "completed_jobs": []})
    if not isinstance(jobs, dict):
        raise StateError(path, "expected a JSON object at the top level")
    jobs.setdefault("active_jobs", [])
    jobs.setdefault("completed_jobs", [])
    if not isinstance(jobs["active_jobs"], list) or not isinstance(jobs["completed_jobs"], list):
        raise StateError(path, "'active_jobs' and 'completed_jobs' must be lists")
    return jobs


def find_task(graph: dict, task_id: str):
    for task in graph.get("tasks", []):
        if task.get("id") == task_id:
            return task
    return None


def find_task_by_subject(graph: dict, subject: str):
    if not subject:
        return None
    lowered = subject.strip().lower()
    for task in graph.get("tasks", []):
        if str(task.get("subject", "")).strip().lower() == lowered:
            return task
    return None


def tasks_owned_by(graph: dict, owner: str) -> list:
    if not owner:
        return []
    lowered = owner.strip().lower()
    return [t for t in graph.get("tasks", []) if str(t.get("owner", "")).strip().lower() == lowered]


# --------------------------------------------------------------------------
# Master-context handshake
# --------------------------------------------------------------------------


def master_context_pending(state: dict) -> bool:
    """True while the master implementation directive has not been loaded."""
    return not bool(state.get("master_context_loaded"))


def master_context_problems(root: Path | None = None, state: dict | None = None) -> list[str]:
    """Return the reasons the ``ready_for_master`` -> ``implementation`` transition is invalid.

    An empty list means every master-context precondition holds. This is the
    single authority used by both the validator and the hooks so the two can
    never disagree.
    """
    root = root or project_dir()
    problems: list[str] = []
    try:
        state = state if state is not None else read_run_state(root)
    except StateError as exc:
        return [f"RUN_STATE.json unusable: {exc.detail}"]

    for field in _MASTER_CONTEXT_FIELDS:
        if field not in state:
            problems.append(f"RUN_STATE.json is missing master-context field '{field}'")

    for flag in ("master_context_loaded", "architecture_initialized", "task_graph_initialized", "acceptance_gates_initialized"):
        if not state.get(flag):
            problems.append(f"RUN_STATE.json.{flag} is not true")

    declared_path = state.get("master_directive_path")
    if not declared_path:
        problems.append("RUN_STATE.json.master_directive_path is not set")
    else:
        directive = root / declared_path
        if not directive.is_file():
            problems.append(f"master directive file is missing: {declared_path}")
        else:
            actual = sha256_file(directive)
            declared_hash = state.get("master_directive_sha256")
            if not declared_hash:
                problems.append("RUN_STATE.json.master_directive_sha256 is not set")
            elif actual != declared_hash:
                problems.append(
                    "master directive hash mismatch: RUN_STATE records {} but {} hashes to {}".format(
                        declared_hash, declared_path, actual
                    )
                )

    for name in ("ARCHITECTURE.md", "CRITICAL_PATH.md"):
        path = agent_run_dir(root) / name
        if not path.is_file():
            # A missing file must never be mistaken for an initialized one.
            problems.append(f"{name} is missing")
            continue
        content = read_text(path)
        if PLACEHOLDER_TOKEN in content:
            problems.append(f"{name} still contains the {PLACEHOLDER_TOKEN} placeholder")
        elif not content.strip():
            problems.append(f"{name} is empty")

    try:
        graph = read_task_graph(root)
    except StateError as exc:
        problems.append(f"TASK_GRAPH.json unusable: {exc.detail}")
    else:
        if graph.get("status") == PLACEHOLDER_TOKEN:
            problems.append(f"TASK_GRAPH.json status is still {PLACEHOLDER_TOKEN}")
        real_tasks = [t for t in graph.get("tasks", []) if not t.get("bootstrap_only")]
        if not real_tasks:
            problems.append("TASK_GRAPH.json contains no implementation tasks")

    try:
        acceptance = read_acceptance_status(root)
    except StateError as exc:
        problems.append(f"ACCEPTANCE_STATUS.json unusable: {exc.detail}")
    else:
        if not isinstance(acceptance.get("gates"), dict) or not acceptance.get("gates"):
            problems.append("ACCEPTANCE_STATUS.json defines no mandatory acceptance gates")

    upstream = read_json(agent_run_dir(root) / "UPSTREAM_PROTECTED_PATHS.json", default=None)
    if not isinstance(upstream, dict):
        problems.append("UPSTREAM_PROTECTED_PATHS.json is missing or malformed")
    elif upstream.get("status") == PLACEHOLDER_TOKEN:
        problems.append(f"UPSTREAM_PROTECTED_PATHS.json status is still {PLACEHOLDER_TOKEN}")

    if not master_init_receipt(root):
        problems.append(
            f"no valid passing receipt exists for task '{MASTER_INIT_TASK_ID}' at the current SHA"
        )
    return problems


def master_init_receipt(root: Path | None = None):
    root = root or project_dir()
    head = git_sha(root)
    for receipt in load_receipts(MASTER_INIT_TASK_ID, root):
        if not receipt_is_passing(receipt):
            continue
        if head is None or receipt.get("git_sha") == head:
            return receipt
    return None


# --------------------------------------------------------------------------
# Receipts
# --------------------------------------------------------------------------

RECEIPT_REQUIRED_FIELDS = (
    "schema_version",
    "task_id",
    "git_sha",
    "worktree",
    "command",
    "exit_code",
    "started_at",
    "finished_at",
    "artifact_paths",
    "configuration_hashes",
    "valid",
)


def receipt_schema_problems(receipt) -> list[str]:
    if not isinstance(receipt, dict):
        return ["receipt is not a JSON object"]
    problems = [f"missing field '{f}'" for f in RECEIPT_REQUIRED_FIELDS if f not in receipt]
    if "exit_code" in receipt and not isinstance(receipt["exit_code"], int):
        problems.append("'exit_code' must be an integer")
    if "valid" in receipt and not isinstance(receipt["valid"], bool):
        problems.append("'valid' must be a boolean")
    if "artifact_paths" in receipt and not isinstance(receipt["artifact_paths"], list):
        problems.append("'artifact_paths' must be a list")
    if "configuration_hashes" in receipt and not isinstance(receipt["configuration_hashes"], dict):
        problems.append("'configuration_hashes' must be an object")
    if "git_sha" in receipt and not isinstance(receipt.get("git_sha"), str):
        problems.append("'git_sha' must be a string")
    return problems


def receipt_is_passing(receipt) -> bool:
    if receipt_schema_problems(receipt):
        return False
    return receipt.get("exit_code") == 0 and receipt.get("valid") is True


def load_receipts(task_id: str | None = None, root: Path | None = None) -> list[dict]:
    """Load every receipt, optionally filtered by task id.

    Malformed receipt files are returned with an ``_error`` marker rather than
    dropped, so a corrupt receipt can never quietly become "no receipt".
    """
    root = root or project_dir()
    directory = receipts_dir(root)
    if not directory.is_dir():
        return []
    out: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = read_json(path, required=True)
        except StateError as exc:
            out.append({"_error": exc.detail, "_path": str(path), "task_id": None})
            continue
        if not isinstance(data, dict):
            out.append({"_error": "not a JSON object", "_path": str(path), "task_id": None})
            continue
        data["_path"] = str(path)
        if task_id is None or data.get("task_id") == task_id:
            out.append(data)
    return out


def receipt_filename(task_id: str, sha: str | None, finished_at: str) -> str:
    safe_task = re.sub(r"[^A-Za-z0-9_.-]+", "-", task_id or "unknown")
    safe_sha = (sha or "nosha")[:12]
    safe_time = re.sub(r"[^0-9A-Za-z]+", "", finished_at or utc_now_iso())
    return f"{safe_task}__{safe_sha}__{safe_time}.json"


def write_receipt(receipt: dict, root: Path | None = None) -> Path:
    root = root or project_dir()
    problems = receipt_schema_problems(receipt)
    if problems:
        raise ValueError("refusing to write invalid receipt: " + "; ".join(problems))
    target = receipts_dir(root) / receipt_filename(
        receipt.get("task_id", "unknown"), receipt.get("git_sha"), receipt.get("finished_at", "")
    )
    atomic_write_json(target, receipt)
    return target


# --------------------------------------------------------------------------
# Path classification
# --------------------------------------------------------------------------

#: Structural classification rules. These encode only *settled* facts about the
#: control plane's own layout plus generic, non-repository-specific heuristics.
#: The detailed production/upstream map is supplied later by the master
#: directive through UPSTREAM_PROTECTED_PATHS.json; until then anything
#: unrecognised falls through to ``production``, which is the conservative
#: answer during any freeze.
CONTROL_PLANE_PREFIXES = (".claude/",)
CONTROL_PLANE_FILES = ("CLAUDE.md",)
AGENT_RUN_PREFIXES = (".agent-run/",)
TEST_PREFIXES = ("tests/",)
TEST_FILES = ("conftest.py",)
DOC_PREFIXES = ("docs/",)

_EVALUATOR_RE = re.compile(r"(^|/)(eval|evals|evaluation|evaluator|acceptance|scoring|judge|adjudicat)", re.I)
_FIXTURE_RE = re.compile(r"(^|/)(fixtures?|golden|snapshots?|testdata|corpus|worlds|evidence)(/|$)", re.I)
_PROMPT_RE = re.compile(r"(^|/|_|-)prompts?(/|_|-|\.|$)", re.I)


def _under_any(rel: str, prefixes) -> bool:
    """True when ``rel`` is one of the prefix directories itself, or inside one.

    Git reports an untracked tree as ``dir/``, so the directory itself must
    classify the same way as the files beneath it.
    """
    for prefix in prefixes:
        bare = prefix.rstrip("/")
        if rel == bare or rel.startswith(bare + "/"):
            return True
    return False


def normalize_repo_path(path_like, root: Path | None = None) -> str:
    """Return a repository-relative POSIX path for ``path_like``.

    Absolute paths outside the project are returned unchanged so the caller can
    recognise them as external.
    """
    root = (root or project_dir()).resolve()
    if not path_like:
        return ""
    raw = Path(str(path_like))
    try:
        resolved = raw if raw.is_absolute() else (root / raw)
        rel = os.path.relpath(str(resolved.resolve(strict=False)), str(root))
    except (OSError, ValueError):
        return str(path_like).replace("\\", "/")
    rel = rel.replace("\\", "/")
    return rel


def classify_path(path_like, root: Path | None = None) -> str:
    """Classify a path into one control-plane category.

    Returns one of: ``control_plane``, ``agent_run``, ``upstream_protected``,
    ``evaluator``, ``fixture``, ``prompt``, ``test``, ``doc``, ``external``,
    ``production``.
    """
    root = root or project_dir()
    rel = normalize_repo_path(path_like, root)
    if not rel:
        return "production"
    if rel.startswith("../") or Path(rel).is_absolute():
        return "external"

    if rel in CONTROL_PLANE_FILES or _under_any(rel, CONTROL_PLANE_PREFIXES):
        return "control_plane"
    if _under_any(rel, AGENT_RUN_PREFIXES):
        return "agent_run"
    if is_upstream_protected(rel, root):
        return "upstream_protected"
    if rel in TEST_FILES or _under_any(rel, TEST_PREFIXES):
        return "test"
    if _EVALUATOR_RE.search(rel):
        return "evaluator"
    if _FIXTURE_RE.search(rel):
        return "fixture"
    if _PROMPT_RE.search(rel):
        return "prompt"
    if _under_any(rel, DOC_PREFIXES) or (rel.endswith(".md") and "/" not in rel):
        return "doc"
    return "production"


def upstream_protected_paths(root: Path | None = None) -> list[str]:
    root = root or project_dir()
    data = read_json(agent_run_dir(root) / "UPSTREAM_PROTECTED_PATHS.json", default=None)
    if not isinstance(data, dict):
        return []
    paths = data.get("protected_paths")
    if not isinstance(paths, list):
        return []
    out: list[str] = []
    for entry in paths:
        if isinstance(entry, str):
            out.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("path"), str):
            out.append(entry["path"])
    return out


def _strip_leading_dot_slash(path: str) -> str:
    """Remove a leading ``./`` only.

    ``str.lstrip("./")`` takes a *character set* and would turn
    ``.agent-run/x`` into ``agent-run/x``.
    """
    text = path.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def is_upstream_protected(rel_path: str, root: Path | None = None) -> bool:
    rel = _strip_leading_dot_slash(rel_path)
    for protected in upstream_protected_paths(root):
        pat = _strip_leading_dot_slash(protected).rstrip("/")
        if not pat:
            continue
        if rel == pat or rel.startswith(pat + "/"):
            return True
        if any(ch in pat for ch in "*?[") and _glob_match(rel, pat):
            return True
    return False


def _glob_match(path: str, pattern: str) -> bool:
    import fnmatch

    if fnmatch.fnmatch(path, pattern):
        return True
    # Treat a directory-style glob as covering everything beneath it.
    return fnmatch.fnmatch(path, pattern.rstrip("/") + "/*")


# --------------------------------------------------------------------------
# Command classification
# --------------------------------------------------------------------------

MONITORED_RUNNER = "run_monitored.py"

#: Shell constructs that detach work from the foreground of this tool call.
_BACKGROUND_PATTERNS = (
    (re.compile(r"(?<![&|>])&\s*(?:$|[;\n])"), "trailing '&' backgrounding"),
    (re.compile(r"\bnohup\b"), "nohup"),
    (re.compile(r"\bdisown\b"), "disown"),
    (re.compile(r"\bsetsid\b"), "setsid"),
    (re.compile(r"\bscreen\s+-\w*d"), "detached screen session"),
    (re.compile(r"\btmux\s+new(-session)?\b[^|;]*\s-\w*d"), "detached tmux session"),
    (re.compile(r"\bat\s+(now|\+)"), "at(1) scheduling"),
    (re.compile(r"\bbatch\b\s*$"), "batch(1) scheduling"),
)

#: Workload shapes that must run under the monitored runner regardless of how
#: they are launched. Kept semantic (what the job *is*) rather than a list of
#: specific commands.
_LONG_RUNNING_PATTERNS = (
    (re.compile(r"\bcorpus\b", re.I), "corpus run"),
    (re.compile(r"\b(scale|scaling)[-_ ]?(test|run|sweep)\b", re.I), "scale run"),
    (re.compile(r"\bload[-_ ]?test", re.I), "load test"),
    (re.compile(r"\bstress[-_ ]?test", re.I), "stress test"),
    (re.compile(r"\bsoak\b", re.I), "soak run"),
    # '_' is a word character, so \b would miss 'bench_runtime.py'. Match on a
    # non-letter boundary instead, which still rejects 'benched'/'benchmarking'.
    (re.compile(r"(?<![A-Za-z])bench(?:mark)?(?![A-Za-z])", re.I), "benchmark"),
    (re.compile(r"\bsweep\b", re.I), "parameter sweep"),
    (re.compile(r"--?n[-_]?agents[= ]\s*\d{2,}", re.I), "many-agent run"),
    (re.compile(r"\b\d{2,}[-_ ]?agents?\b", re.I), "many-agent run"),
    (re.compile(r"--?(episodes|iterations|trials|steps)[= ]\s*\d{3,}", re.I), "high-iteration run"),
    (re.compile(r"\bfrozen[-_ ]?acceptance\b", re.I), "frozen acceptance run"),
)

#: Commands that are demonstrably short and harmless even when backgrounded.
_SHORT_SAFE_HEADS = frozenset(
    {
        "echo", "true", "false", "pwd", "ls", "cat", "head", "tail", "wc", "stat",
        "grep", "rg", "find", "which", "basename", "dirname", "date", "printf",
        "sleep", "touch", "mkdir", "cp", "mv", "realpath", "env", "sort", "uniq",
        "diff", "cmp", "sed", "awk", "jq", "tee", "chmod", "test",
    }
)

_READ_ONLY_GIT = frozenset(
    {
        "status", "log", "diff", "show", "rev-parse", "branch", "remote", "config",
        "describe", "blame", "shortlog", "ls-files", "ls-tree", "cat-file", "for-each-ref",
        "merge-base", "name-rev", "reflog", "count-objects", "check-ignore", "whatchanged",
        "grep", "verify-commit", "rev-list", "symbolic-ref", "var", "help", "version",
    }
)


def _split_command(command: str) -> list[list[str]]:
    """Split a shell command into best-effort argv segments per sub-command."""
    segments: list[list[str]] = []
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    current: list[str] = []
    for token in tokens:
        if token in {";", "&&", "||", "|", "&", "\n"} or set(token) <= {"&", "|", ";"} and token:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def _strip_env_assignments(argv: list[str]) -> list[str]:
    index = 0
    while index < len(argv) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[index]):
        index += 1
    return argv[index:]


def is_monitored_command(command: str) -> bool:
    return MONITORED_RUNNER in (command or "")


def background_reason(command: str, tool_input: dict | None = None) -> str | None:
    """Return why a command is detached from the foreground, or ``None``."""
    if tool_input and tool_input.get("run_in_background") is True:
        return "Claude Code background execution (run_in_background=true)"
    for pattern, label in _BACKGROUND_PATTERNS:
        if pattern.search(command or ""):
            return label
    return None


def long_running_reason(command: str) -> str | None:
    for pattern, label in _LONG_RUNNING_PATTERNS:
        if pattern.search(command or ""):
            return label
    return None


def is_short_and_harmless(command: str) -> bool:
    """True when every sub-command is a known-cheap, non-workload command."""
    segments = _split_command(command or "")
    if not segments:
        return False
    for argv in segments:
        argv = _strip_env_assignments(argv)
        if not argv:
            continue
        head = Path(argv[0]).name
        if head == "git":
            sub = next((a for a in argv[1:] if not a.startswith("-")), None)
            if sub in _READ_ONLY_GIT:
                continue
            return False
        if head in _SHORT_SAFE_HEADS:
            if head == "sleep":
                try:
                    if float(argv[1]) > 60:
                        return False
                except (IndexError, ValueError):
                    return False
            continue
        if head in {"python", "python3"} and any(a in {"-V", "--version"} for a in argv[1:]):
            continue
        return False
    return True


def requires_monitored_runner(command: str, tool_input: dict | None = None) -> str | None:
    """Return the reason a command must go through ``run_monitored.py``.

    ``None`` means the command may run directly.
    """
    if not command:
        return None
    if is_monitored_command(command):
        return None
    long_reason = long_running_reason(command)
    if long_reason:
        return f"it is a {long_reason}"
    bg_reason = background_reason(command, tool_input)
    if bg_reason and not is_short_and_harmless(command):
        return f"it uses {bg_reason}"
    return None


# --------------------------------------------------------------------------
# Destructive git detection
# --------------------------------------------------------------------------

_DESTRUCTIVE_GIT = (
    (re.compile(r"^reset$"), re.compile(r"--hard|--merge|--keep"), "git reset that discards working-tree state"),
    (re.compile(r"^clean$"), re.compile(r"-[a-zA-Z]*[fdxX]"), "git clean that deletes untracked files"),
    (re.compile(r"^checkout$"), re.compile(r"(^|\s)(--|-f|--force|--ours|--theirs)(\s|$)"), "git checkout that discards local modifications"),
    (re.compile(r"^restore$"), re.compile(r".*"), "git restore that discards local modifications"),
    (re.compile(r"^stash$"), re.compile(r"\b(drop|clear|pop)\b"), "git stash operation that can destroy stashed work"),
    (re.compile(r"^branch$"), re.compile(r"(^|\s)-[a-zA-Z]*D(\s|$)"), "forced branch deletion"),
    (re.compile(r"^update-ref$"), re.compile(r"(^|\s)-d(\s|$)"), "direct ref deletion"),
    (re.compile(r"^rm$"), re.compile(r"-[a-zA-Z]*[rf]"), "forced/recursive git rm"),
)


def destructive_git_reason(command: str) -> str | None:
    """Detect history- or work-destroying git invocations."""
    for argv in _split_command(command or ""):
        argv = _strip_env_assignments(argv)
        if not argv or Path(argv[0]).name != "git":
            continue
        rest = argv[1:]
        # Skip global options such as -C <dir> so the subcommand is found.
        index = 0
        while index < len(rest):
            token = rest[index]
            if token in {"-C", "--git-dir", "--work-tree", "-c"}:
                index += 2
                continue
            if token.startswith("-"):
                index += 1
                continue
            break
        if index >= len(rest):
            continue
        sub = rest[index]
        tail = " ".join(rest[index + 1:])
        if sub == "push":
            if re.search(r"(^|\s)(-f|--force)(\s|$)", tail) or "--force-with-lease" in tail or re.search(r"(^|\s)\+\S+:", tail):
                return "a force push"
            continue
        for sub_re, arg_re, label in _DESTRUCTIVE_GIT:
            if sub_re.match(sub) and arg_re.search(tail):
                return label
    return None


# --------------------------------------------------------------------------
# Shell write targets
# --------------------------------------------------------------------------

#: A redirection operator, as produced by :func:`_split_command`. Leading file
#: descriptors are separate tokens (``2> f`` -> ``2``, ``>``, ``f``), so only the
#: punctuation run needs matching here. ``<`` is deliberately absent: reading a
#: file is not writing to it.
_REDIRECT_OP_RE = re.compile(r"^&?>{1,2}[|&]?$")

#: The same operator with its target glued on (``>out.txt``). ``_split_command``
#: separates these, so this only matters on its whitespace-split fallback path
#: for a command with unbalanced quotes.
_REDIRECT_ATTACHED_RE = re.compile(r"^&?>{1,2}\|?(?!\s)(.+)$")

#: ``<<MARKER`` / ``<<-'MARKER'`` -- but not the ``<<<`` here-string.
_HEREDOC_RE = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(command: str) -> str:
    """Remove heredoc bodies, keeping the command lines around them.

    A heredoc body is stdin *data* for the command -- often another language
    entirely -- so shell syntax inside it is text, not shell. Scanning it for
    redirections produces pure noise: a wrapped e-mail address or a quoted
    ``sed -i`` in a commit message is not a write.
    """
    lines = (command or "").split("\n")
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        index += 1
        for match in _HEREDOC_RE.finditer(line):
            marker = match.group(2)
            while index < len(lines) and lines[index].strip() != marker:
                index += 1
            index += 1  # drop the terminator line as well
    return "\n".join(kept)


def _split_redirections(argv: list[str]) -> tuple[list[str], list[str]]:
    """Separate ``argv`` into plain words and the files it redirects onto."""
    words: list[str] = []
    targets: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if _REDIRECT_OP_RE.match(token):
            target = argv[index + 1] if index + 1 < len(argv) else None
            index += 2
            # '>&1' / '2>&1' duplicate a file descriptor; nothing is written.
            if target is not None and not (token.endswith("&") and target.isdigit()):
                targets.append(target)
            continue
        attached = _REDIRECT_ATTACHED_RE.match(token)
        if attached:
            targets.append(attached.group(1))
            index += 1
            continue
        words.append(token)
        index += 1
    return words, targets


def _sed_is_in_place(words: list[str]) -> bool:
    """True for ``sed -i`` / ``-i.bak`` / ``-ni`` / ``--in-place``."""
    for token in words[1:]:
        if token == "--":
            break
        if token.startswith("--in-place"):
            return True
        if token.startswith("-") and not token.startswith("--") and len(token) > 1:
            if "i" in token[1:].split(".", 1)[0]:
                return True
    return False


#: Commands that write to their file operands. ``arg_options`` are the options
#: that consume a following word; ``script_first`` marks a grammar whose first
#: operand is a program rather than a file (``sed 's/a/b/' file``); ``gate``
#: decides whether this invocation writes at all.
_WRITING_COMMANDS = {
    "tee": {"arg_options": frozenset(), "script_first": False, "gate": None},
    "truncate": {
        "arg_options": frozenset({"-s", "--size", "-r", "--reference"}),
        "script_first": False,
        "gate": None,
    },
    "sed": {
        "arg_options": frozenset({"-e", "-f", "--expression", "--file"}),
        "script_first": True,
        "gate": _sed_is_in_place,
    },
}


def _file_operands(words: list[str], arg_options, script_first: bool) -> list[str]:
    """Return a command's file operands, skipping options and their arguments."""
    operands: list[str] = []
    script_pending = script_first
    index = 1
    while index < len(words):
        token = words[index]
        index += 1
        if token == "--":
            operands.extend(words[index:])
            break
        if token.startswith("-") and token != "-":
            name = token.split("=", 1)[0]
            if name in arg_options:
                # The script came from -e/-f, so no operand is the script.
                script_pending = False
                if token == name:  # value is the next word, not glued on
                    index += 1
            continue
        if script_pending:
            script_pending = False  # this operand is the script, not a file
            continue
        operands.append(token)
    return operands


def shell_write_targets(command: str) -> list[str]:
    """Return the paths a shell command writes to.

    Covers redirection targets and the in-place writers (``tee``, ``sed -i``,
    ``truncate``). Detection is shell-aware rather than text-matching: a ``>``
    or a ``sed -i`` that merely appears inside a quoted string or a heredoc body
    is data and is ignored, while a genuine target is still recovered when it is
    quoted or preceded by option arguments.

    Best effort by design. It is one classification input among several, never
    the only thing between a tool call and a protected file.
    """
    found: list[str] = []
    for raw_argv in _split_command(strip_heredocs(command or "")):
        words, targets = _split_redirections(_strip_env_assignments(raw_argv))
        found.extend(targets)
        if not words:
            continue
        spec = _WRITING_COMMANDS.get(Path(words[0]).name)
        if spec is None:
            continue
        if spec["gate"] is not None and not spec["gate"](words):
            continue
        found.extend(_file_operands(words, spec["arg_options"], spec["script_first"]))
    return [p for p in found if p and not p.startswith("/dev/")]


#: Ephemeral runner scratch: logs and diagnostics the monitored runner recreates
#: on every job. The durable record of a job also lives in the protected
#: BACKGROUND_JOBS.json registry, so removing this scratch loses no evidence --
#: except during a freeze, when the logs *are* the acceptance artifacts.
EPHEMERAL_AGENT_RUN_DIR = ".agent-run/jobs"


def is_ephemeral_job_scratch(rel: str) -> bool:
    """True for the jobs directory itself or anything beneath it."""
    return rel == EPHEMERAL_AGENT_RUN_DIR or rel.startswith(EPHEMERAL_AGENT_RUN_DIR + "/")


def destructive_filesystem_reason(command: str, root: Path | None = None,
                                  state: dict | None = None) -> str | None:
    """Detect deletion/overwrite of control-plane or frozen acceptance artifacts."""
    root = root or project_dir()
    frozen = bool(state) and state.get("mode") == "frozen_acceptance"
    for argv in _split_command(command or ""):
        argv = _strip_env_assignments(argv)
        if not argv:
            continue
        head = Path(argv[0]).name
        if head not in {"rm", "shred", "truncate"}:
            continue
        for token in argv[1:]:
            if token.startswith("-"):
                continue
            rel = normalize_repo_path(token, root)
            category = classify_path(token, root)
            if category == "agent_run" and is_ephemeral_job_scratch(rel) and not frozen:
                continue
            if category in {"control_plane", "agent_run"}:
                if frozen and is_ephemeral_job_scratch(rel):
                    return f"deletion of frozen acceptance job artifacts ({token})"
                return f"deletion of {category.replace('_', ' ')} state ({token})"
    return None


# --------------------------------------------------------------------------
# Hook IO helpers
# --------------------------------------------------------------------------


def read_event(stream=None) -> dict:
    """Read and parse the hook event JSON from stdin."""
    stream = stream if stream is not None else sys.stdin
    raw = stream.read()
    if not raw or not raw.strip():
        raise StateError("<stdin>", "hook received empty input; expected a JSON event object")
    try:
        event = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StateError("<stdin>", f"hook input is not valid JSON: {exc.msg}") from exc
    if not isinstance(event, dict):
        raise StateError("<stdin>", "hook input must be a JSON object")
    return event


def first_present(event: dict, *names, default=None):
    """Return the first present, non-empty field among ``names``.

    Hook payload field names are read defensively: a renamed or nested field
    must degrade into an explicit "unknown" rather than a crash.
    """
    for name in names:
        if "." in name:
            cursor = event
            for part in name.split("."):
                if isinstance(cursor, dict) and part in cursor:
                    cursor = cursor[part]
                else:
                    cursor = None
                    break
            if cursor not in (None, ""):
                return cursor
            continue
        value = event.get(name)
        if value not in (None, ""):
            return value
    return default
