"""Driver-side helpers for the Phase 7 distributed suite.

Import this module AFTER the per-module version/importorskip gates: it
imports ``cf_helpers`` (tests/engine_counterfactuals) and
``baseline_helpers`` (tests/engine_baseline), which import the Concordia
language-model interface available only in the pinned engine environment
(Python >= 3.12).  Those toolkits stay the single source of truth for the
fixture-1 scripted vocabulary, metric predicates, and status rule; this
module only adapts them into the serializable params consumed by
``distributed_model_specs.build_scripted_models`` on BOTH execution legs.
"""

from __future__ import annotations

import json
from pathlib import Path

from baseline_helpers import AWARE_QUESTION_NEEDLE
from cf_helpers import (MAX_STEPS, RECIPIENT_SILENT_TURN,  # noqa: F401
                        SEED, SENDER_CTA, SENDER_IDLE_TURN,
                        fixture_predicates, fixture_status_rule,
                        load_fixture_one, make_candidate)
from distributed_model_specs import CANDIDATE_ACTION_TOKEN

#: the dotted reference every distributed run in this suite ships
MODEL_BUILDER_REF = "distributed_model_specs:build_scripted_models"

#: BranchResult fields covered by the equivalence signature.  DELIBERATELY
#: EXCLUDED: ``token_stats`` and ``runtime_stats`` (substrate-specific
#: wall-clock / task accounting that legitimately differs between the
#: serial local loop and Ray workers) and ``artifact_paths`` (the
#: distributed run attaches collected workspace file paths; the local run
#: has none).  Same key set as cf_helpers.branch_signature.
SIGNATURE_KEYS = ("branch_id", "candidate_id", "world_id",
                  "terminal_status", "terminal_world_state", "event_trace",
                  "outcome_metrics", "infrastructure_errors")


def result_signature(result) -> str:
    """Byte-comparable deterministic signature of one BranchResult (see
    ``SIGNATURE_KEYS`` for the documented inclusion/exclusion rule)."""
    data = result.to_dict()
    return json.dumps({key: data[key] for key in SIGNATURE_KEYS},
                      sort_keys=True)


def observer_names(world) -> list:
    """Every declared actor's display name, in declared order (the GM's
    scripted observer answer)."""
    return [actor.name for actor in world.actors]


def scripted_params(fx, candidates=None, *, failing_ids=(),
                    marker_prefix="INJECTED_DISTRIBUTED_FAILURE_",
                    delay_s=0.0, recipient_response=None) -> dict:
    """Serializable params implementing the frozen fixture's
    ``deterministic_script`` (or a constant recipient response for
    synthetic candidates) for ``build_scripted_models``.

    - The sender's scripted turn echoes the branch's candidate action via
      the substitution token, so the committed event carries the exact
      candidate text (mirrors cf_helpers.fixture_model_factory).
    - The recipient's rules key on WHICH candidate text the recipient
      observes: one rule per candidate, needle = that candidate's verbatim
      action text.  Only the branch's own candidate text ever appears in
      a branch, so exactly one rule can match.
    """
    candidates = tuple(candidates if candidates is not None
                       else fx.candidates)
    recipient_rules = []
    for candidate in candidates:
        if recipient_response is not None:
            text = recipient_response
        else:
            response = fx.deterministic_script["recipient"][
                candidate.candidate_id]["response"].strip()
            text = RECIPIENT_SILENT_TURN if response == "none" else response
        recipient_rules.append([candidate.action, [text]])
    params = {
        "actor_rules": {
            "sender": [[SENDER_CTA,
                        [CANDIDATE_ACTION_TOKEN, SENDER_IDLE_TURN]]],
            "recipient": recipient_rules,
        },
        "gm_rules": [[AWARE_QUESTION_NEEDLE,
                      [", ".join(observer_names(fx.world))]]],
    }
    if failing_ids:
        params["failing"] = {
            "actor": "recipient",
            "candidate_ids": list(failing_ids),
            "marker_prefix": marker_prefix,
        }
    if delay_s:
        params["delay_s"] = delay_s
    return params


def model_spec(params) -> dict:
    return {"model_builder": MODEL_BUILDER_REF, "params": params}


def read_trace_records(trace_dir) -> list:
    records = []
    for shard in sorted(Path(trace_dir).glob("trace_*.jsonl")):
        for line in shard.read_text(encoding="utf-8").splitlines():
            records.append(json.loads(line))
    return records
