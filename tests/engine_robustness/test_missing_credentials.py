"""Missing model credentials (OPERATIONAL_ROBUSTNESS_MATRIX row 10).

Every credential boundary in the credential map
(``third_party/INTEGRATION_METHOD.md``, risk R6) must refuse EXPLICITLY,
ACTIONABLY, and AT THE RIGHT BOUNDARY -- import/initialization for the
AgentSociety layer (never a mid-run crash), the transport call for the
compiler/semantic-runtime layer -- and the live-smoke suite must skip
exactly when its credential is absent (skip discipline, not silent
weakening).  All subprocess legs remove the variable from the CHILD
environment only.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "robustness suite requires Python >= 3.12 (engine env); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

import ast
import time

from robustness_helpers import (ENGINE_PYTHON, REPO_ROOT, child_env,
                                run_child)

LIVE_SMOKE = (REPO_ROOT / "tests" / "engine_individual"
              / "test_individual_slice_live_smoke.py")


def test_agentsociety_import_refuses_without_credentials(tmp_path):
    """Matrix row 10: with AGENTSOCIETY_LLM_API_KEY absent,
    ``import agentsociety2`` itself refuses -- the documented
    import-time boundary -- with an explicit, actionable error naming
    the exact variable.  Nothing runs first."""
    code, out, err = run_child(
        [ENGINE_PYTHON, "-c", "import agentsociety2"],
        log_dir=tmp_path,
        env=child_env(AGENTSOCIETY_LLM_API_KEY=None),
        timeout=60.0)
    assert code == 1, f"expected import refusal, got exit {code}: {err}"
    assert "ValueError" in err
    assert "AGENTSOCIETY_LLM_API_KEY is required" in err
    assert "set this environment variable" in err
    assert "Traceback" in err


def test_product_import_survives_and_engine_boundary_names_the_variable(
        tmp_path):
    """Matrix row 10: the stdlib-only product package imports WITHOUT
    credentials (offline analysis is never blocked), and a distributed
    run attempt fails at the ENGINE-IMPORT boundary -- before any
    workspace or branch exists -- with the variable named."""
    program = (
        "import sworldmodel\n"
        "from sworldmodel.backends.agentsociety import branch_executor\n"
        "print('PRODUCT_IMPORT_OK', flush=True)\n"
        "try:\n"
        "    branch_executor._import_engine()\n"
        "except Exception as exc:\n"
        "    print('BOUNDARY:' + type(exc).__name__, flush=True)\n"
        "    print('MESSAGE:' + str(exc)[:400], flush=True)\n"
        "else:\n"
        "    print('BOUNDARY:NONE', flush=True)\n"
    )
    code, out, err = run_child(
        [ENGINE_PYTHON, "-c", program],
        log_dir=tmp_path,
        env=child_env(AGENTSOCIETY_LLM_API_KEY=None),
        timeout=60.0)
    assert code == 0, f"child failed: {err[-800:]}"
    assert "PRODUCT_IMPORT_OK" in out
    assert "BOUNDARY:NONE" not in out
    assert "AGENTSOCIETY_LLM_API_KEY" in out, (
        "the engine boundary error must name the missing variable; "
        f"got: {out}")


def test_semantic_runtime_transport_names_missing_deepseek_key(monkeypatch):
    """Matrix row 10: the semantic-runtime transport refuses a call with
    DEEPSEEK_API_KEY unset as a typed ``RuntimeTechnicalFailure`` naming
    the variable, instantly (no network attempt), with both attempts
    recorded in the structured per-call log."""
    from sworldmodel.semantic_runtime import llm as llm_mod

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    caller = llm_mod.RuntimeCaller()
    started = time.monotonic()
    with pytest.raises(llm_mod.RuntimeTechnicalFailure) as excinfo:
        caller.ask("probe", "system", "user", lambda obj: obj)
    assert time.monotonic() - started < 5.0
    assert "DEEPSEEK_API_KEY is not set" in str(excinfo.value)
    assert len(caller.calls) == 2  # the one technical retry, then refusal
    for entry in caller.calls:
        assert "DEEPSEEK_API_KEY is not set" in entry["validation"]


def test_live_smoke_skips_exactly_when_deepseek_key_is_unset(tmp_path):
    """Matrix row 10 (skip discipline): the live-smoke module's OWN
    skipif condition is the env-var emptiness check (asserted on the
    source), and running the file without the key yields exactly two
    skips with the documented reason -- never a silent pass, never a
    network attempt."""
    tree = ast.parse(LIVE_SMOKE.read_text(encoding="utf-8"))
    source = LIVE_SMOKE.read_text(encoding="utf-8")
    marks = [node for node in tree.body
             if isinstance(node, ast.Assign)
             and any(getattr(target, "id", None) == "pytestmark"
                     for target in node.targets)]
    assert len(marks) == 1, "expected exactly one module-level pytestmark"
    segment = ast.get_source_segment(source, marks[0])
    assert "skipif" in segment
    assert 'not os.environ.get("DEEPSEEK_API_KEY")' in segment
    assert "DEEPSEEK_API_KEY is not set" in segment

    code, out, err = run_child(
        [ENGINE_PYTHON, "-m", "pytest", str(LIVE_SMOKE), "-q", "-rs"],
        log_dir=tmp_path,
        env=child_env(DEEPSEEK_API_KEY=None),
        cwd=REPO_ROOT,
        timeout=120.0)
    assert code == 0, f"pytest child failed: {out[-800:]}\n{err[-400:]}"
    assert "2 skipped" in out
    assert "DEEPSEEK_API_KEY is not set" in out
    assert "passed" not in out.replace("2 skipped", "")
