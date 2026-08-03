"""Hung-branch child (matrix row 11): a model call that never returns.

Executed by ``test_model_timeout.py`` UNDER THE MONITORED RUNNER:

  argv: <marker>

Runs fixture-1's ``concise_relevant`` branch through the public
counterfactual manager with a recipient model that announces its first
call and then blocks forever -- the exact shape of a live model call
that never times out.  The engine backend has NO in-branch model-call
timeout seam (recorded in the matrix), so this process, left alone,
would hang indefinitely; the monitored runner's no-progress kill is the
outer bound the parent test asserts.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for path in (str(HERE), str(REPO_ROOT / "tests" / "engine_contracts"),
             str(REPO_ROOT / "tests" / "engine_baseline"),
             str(REPO_ROOT / "tests" / "engine_counterfactuals"),
             str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

CANDIDATE_ID = "concise_relevant"


def main() -> int:
    marker = sys.argv[1]
    del marker  # identification token for /proc scans; carried in argv

    from baseline_helpers import StrictScriptedModel, aware_rule
    from cf_helpers import (MAX_STEPS, SEED, SENDER_CTA, SENDER_IDLE_TURN,
                            load_fixture_one)
    from robustness_model_specs import HangingModel
    from sworldmodel.counterfactuals import run_candidates_detailed

    fx = load_fixture_one()
    candidate = fx.candidates[1]
    assert candidate.candidate_id == CANDIDATE_ID

    def factory(cand, branch_seed):
        del branch_seed
        sender = StrictScriptedModel(
            [(SENDER_CTA, [cand.action, SENDER_IDLE_TURN])])
        recipient = HangingModel("BRANCH_MODEL_CALL_HANGING")
        gm = StrictScriptedModel([aware_rule(["Alex", "Morgan"])])
        return {"sender": sender, "recipient": recipient}, gm

    print("BRANCH_STARTING", flush=True)
    run_candidates_detailed(
        fx.world, [candidate], model_factory=factory, seed=SEED,
        max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)
    print("UNREACHABLE_COMPLETION", flush=True)  # pragma: no cover
    return 0  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
