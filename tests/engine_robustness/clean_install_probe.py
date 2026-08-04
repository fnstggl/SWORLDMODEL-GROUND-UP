"""Clean-installation probe (OPERATIONAL_ROBUSTNESS_MATRIX row 1; also
gate A "reproducible from a clean environment" evidence).

Standalone, stdlib-only script (system Python or engine Python) executed
under the MONITORED RUNNER.  It reproduces the engine environment FROM
NOTHING following ``third_party/INTEGRATION_METHOD.md`` step for step --
a brand-new venv, editable installs of the two pinned upstream checkouts
(verified to sit at their locked SHAs, clean), the documented ``mcp``
environment pin, the documented test plugins -- then proves the result
works: the coexistence check and ONE fast engine smoke suite
(``tests/engine_counterfactuals/test_failure_isolation.py``, 2 tests)
run green inside the fresh environment.

Every phase is timed and bounded; the structured evidence JSON is
written atomically to ``--evidence-out`` (committed under
``tests/engine_robustness/evidence/`` and validated by
``test_clean_install_evidence.py`` -- the same committed-evidence tier
design the Phase 11 scale suite uses).  The venv is deleted afterwards
unless ``--keep-venv``.

Usage (through the monitored runner)::

    python3 .claude/tools/run_monitored.py \
        --job-id robustness-clean-install --classification exploratory \
        --no-progress-timeout 300 --total-timeout 900 \
        -- python3 tests/engine_robustness/clean_install_probe.py \
           --venv-dir <scratch>/clean-install-venv \
           --evidence-out tests/engine_robustness/evidence/clean_install.json \
           --job-id robustness-clean-install
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
LOCK_PATH = REPO_ROOT / "third_party" / "UPSTREAM_LOCK.json"
PROTECTED_PATH = REPO_ROOT / ".agent-run" / "UPSTREAM_PROTECTED_PATHS.json"
INTEGRATION_DOC = REPO_ROOT / "third_party" / "INTEGRATION_METHOD.md"
SMOKE_TEST = "tests/engine_counterfactuals/test_failure_isolation.py"

#: documented interpreter floor for the unified engine environment
VENV_PYTHON_BASE = "/usr/bin/python3.12"

#: overall wall budget (seconds); the monitored runner enforces its own
#: outer bound on top
DEFAULT_TOTAL_BUDGET_S = 780.0

STATEMENT = (
    "Clean-installation evidence: the engine environment rebuilt from an "
    "empty venv per third_party/INTEGRATION_METHOD.md, with the "
    "coexistence check and one fast engine smoke suite green inside it."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_logged(argv, *, env=None, cwd=None, timeout=600.0):
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [str(part) for part in argv], capture_output=True, text=True,
            env=env, cwd=str(cwd) if cwd else None, timeout=timeout,
            check=False)
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        code = -1
        out = (exc.stdout or b"").decode("utf-8", "replace") \
            if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = f"TIMEOUT after {timeout}s"
    return {
        "argv": [str(part) for part in argv],
        "returncode": code,
        "seconds": round(time.monotonic() - started, 3),
        "stdout_tail": out[-1200:],
        "stderr_tail": err[-1200:],
    }


def git_head(path: Path) -> str:
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=False)
    return result.stdout.strip()


def git_dirty(path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        capture_output=True, text=True, check=False)
    return bool(result.stdout.strip())


def atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--venv-dir", required=True)
    parser.add_argument("--evidence-out", required=True)
    parser.add_argument("--job-id", default="")
    parser.add_argument("--keep-venv", action="store_true")
    parser.add_argument("--budget-total", type=float,
                        default=DEFAULT_TOTAL_BUDGET_S)
    args = parser.parse_args()

    venv_dir = Path(args.venv_dir).resolve()
    evidence_out = Path(args.evidence_out)
    if not evidence_out.is_absolute():
        evidence_out = REPO_ROOT / evidence_out
    started_monotonic = time.monotonic()

    evidence = {
        "schema_version": 1,
        "statement": STATEMENT,
        "integration_method_doc": "third_party/INTEGRATION_METHOD.md",
        "monitored_job_id": args.job_id,
        "generated_at": utc_now(),
        "repo_sha": git_head(REPO_ROOT),
        "repo_worktree_dirty": git_dirty(REPO_ROOT),
        "venv_python_base": VENV_PYTHON_BASE,
        "budget_total_s": args.budget_total,
        "phases": [],
        "pins": {},
        "package_inventory": {},
        "smoke": {},
        "ok": False,
    }
    failures = []

    def phase(name: str, record: dict, *, ok=None) -> bool:
        entry = {"name": name, **record}
        entry["ok"] = (record.get("returncode") == 0) if ok is None \
            else bool(ok)
        evidence["phases"].append(entry)
        if not entry["ok"]:
            failures.append(name)
        print(f"[clean-install] {name}: "
              f"{'ok' if entry['ok'] else 'FAILED'} "
              f"({entry.get('seconds', '?')}s)", flush=True)
        return entry["ok"]

    def finish(exit_code: int) -> int:
        evidence["total_seconds"] = round(
            time.monotonic() - started_monotonic, 3)
        evidence["within_budget"] = \
            evidence["total_seconds"] <= args.budget_total
        evidence["failures"] = failures
        evidence["ok"] = not failures and evidence["within_budget"]
        evidence["finished_at"] = utc_now()
        if not args.keep_venv and venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)
            evidence["venv_removed_after_run"] = True
        else:
            evidence["venv_removed_after_run"] = False
        atomic_write_json(evidence_out, evidence)
        print(f"[clean-install] evidence -> {evidence_out} "
              f"(ok={evidence['ok']}, total {evidence['total_seconds']}s)",
              flush=True)
        return 0 if evidence["ok"] else max(exit_code, 3)

    # ---- phase: verify the pinned checkouts ---------------------------
    started = time.monotonic()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    protected = json.loads(PROTECTED_PATH.read_text(encoding="utf-8"))
    recorded = {entry["name"]: entry["local_checkout"]
                for entry in protected.get("repositories", [])
                if entry.get("local_checkout")}

    def checkout_for(lock_name: str):
        """Match the lock's upstream name to the protected-paths record
        (the records use the upstream project name, e.g. 'agentsociety'
        for the lock's 'agentsociety2'): exact name first, then the
        unique prefix relation."""
        if lock_name in recorded:
            return recorded[lock_name]
        prefixed = [path for name, path in recorded.items()
                    if lock_name.startswith(name)
                    or name.startswith(lock_name)]
        return prefixed[0] if len(prefixed) == 1 else None

    checkouts = {}
    pins_ok = True
    for upstream in lock["upstreams"]:
        name = upstream["name"]
        pinned = upstream["pinned_commit_sha"]
        checkout = checkout_for(name)
        checkouts[name] = checkout
        head = git_head(Path(checkout)) if checkout else ""
        dirty = git_dirty(Path(checkout)) if checkout else True
        entry_ok = bool(checkout) and head == pinned and not dirty
        pins_ok = pins_ok and entry_ok
        evidence["pins"][name] = {
            "local_checkout": checkout,
            "pinned_commit_sha": pinned,
            "head": head,
            "clean": not dirty,
            "ok": entry_ok,
        }
    if not phase("verify_pinned_checkouts",
                 {"seconds": round(time.monotonic() - started, 3)},
                 ok=pins_ok):
        return finish(3)
    concordia_checkout = Path(checkouts["concordia"])
    as2_checkout = Path(checkouts["agentsociety2"]) / "packages" \
        / "agentsociety2"

    # ---- phase: brand-new venv ----------------------------------------
    if venv_dir.exists():
        print(f"refusing to reuse existing venv dir {venv_dir}",
              file=sys.stderr)
        phase("create_venv", {"seconds": 0.0}, ok=False)
        return finish(3)
    uv = shutil.which("uv")
    if not uv:
        phase("create_venv",
              {"seconds": 0.0, "stderr_tail": "uv not on PATH"}, ok=False)
        return finish(3)
    evidence["uv_version"] = run_logged([uv, "--version"])["stdout_tail"] \
        .strip()
    if not phase("create_venv", run_logged(
            [uv, "venv", venv_dir, "--python", VENV_PYTHON_BASE],
            timeout=120.0)):
        return finish(3)
    venv_python = venv_dir / "bin" / "python"

    # ---- phases: the documented installs, in the documented order -----
    install_steps = (
        ("install_concordia_editable",
         [uv, "pip", "install", "-p", venv_python, "-e",
          concordia_checkout]),
        ("install_agentsociety2_editable",
         [uv, "pip", "install", "-p", venv_python, "-e", as2_checkout]),
        ("install_mcp_environment_pin",
         [uv, "pip", "install", "-p", venv_python, "mcp[cli]>=1.13.1,<2"]),
        ("install_test_plugins",
         [uv, "pip", "install", "-p", venv_python, "pytest",
          "pytest-xdist", "pytest-timeout", "pytest-asyncio", "anyio"]),
    )
    for name, argv in install_steps:
        if not phase(name, run_logged(argv, timeout=480.0)):
            return finish(3)

    # ---- phase: coexistence check (doc step 5, dummy creds) -----------
    offline_env = dict(os.environ)
    offline_env.update({
        "AGENTSOCIETY_LLM_API_KEY": "dummy",
        "AGENTSOCIETY_LLM_API_BASE": "http://localhost:9",
        "AGENTSOCIETY_TRACE_WRITER_ASYNC": "0",
        "MEM0_TELEMETRY": "False",
        "ANONYMIZED_TELEMETRY": "False",
    })
    offline_env.pop("PYTHONPATH", None)  # the fresh env stands alone
    coexistence = run_logged(
        [venv_python, "-c",
         "import concordia, agentsociety2, sys; "
         f"sys.path.insert(0, {str(REPO_ROOT)!r}); "
         "import sworldmodel; print('coexistence OK')"],
        env=offline_env, timeout=120.0)
    if not phase("coexistence_check", coexistence,
                 ok=coexistence["returncode"] == 0
                 and "coexistence OK" in coexistence["stdout_tail"]):
        return finish(3)

    # ---- phase: package inventory (full capture: the JSON is large) ---
    started = time.monotonic()
    full = subprocess.run(
        [str(uv), "pip", "list", "-p", str(venv_python), "--format",
         "json"], capture_output=True, text=True, check=False)
    inventory = {"seconds": round(time.monotonic() - started, 3)}
    try:
        packages = json.loads(full.stdout)
    except ValueError:
        packages = []
    by_name = {pkg["name"].lower(): pkg["version"] for pkg in packages}
    evidence["package_inventory"] = {
        "count": len(packages),
        "key_versions": {name: by_name.get(name)
                         for name in ("gdm-concordia", "agentsociety2",
                                      "ray", "litellm", "mcp", "numpy",
                                      "pytest")},
    }
    phase("package_inventory",
          {"seconds": inventory["seconds"]},
          ok=len(packages) >= 50 and by_name.get("mcp", "9").split(".")[0]
          == "1")

    # ---- phase: one fast engine smoke suite ---------------------------
    smoke = run_logged(
        [venv_python, "-m", "pytest", SMOKE_TEST, "-q", "-p",
         "no:cacheprovider"],
        env=offline_env, cwd=REPO_ROOT, timeout=300.0)
    evidence["smoke"] = {
        "test_path": SMOKE_TEST,
        "returncode": smoke["returncode"],
        "seconds": smoke["seconds"],
        "output_tail": smoke["stdout_tail"][-400:],
        "passed_2": "2 passed" in smoke["stdout_tail"],
    }
    phase("engine_smoke_suite", smoke,
          ok=smoke["returncode"] == 0
          and "2 passed" in smoke["stdout_tail"])

    return finish(0)


if __name__ == "__main__":
    sys.exit(main())
