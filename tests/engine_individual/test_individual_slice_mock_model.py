"""Phase 9 slice, deterministic MOCK-MODEL leg (non-scripted).

The same route -> manager -> outcomes -> reporting slice driven by
``HashDerivedModel``: a deterministic model whose every response is a
pure function of sha256(role seed + prompt) over fixed GENERIC templates
(see individual_helpers).  It carries no script keyed to the scenario,
no reply text, and no knowledge of the fixture's expected outcomes -- so
this leg proves the slice's MECHANICS (explicit terminal status,
complete causal trace, validating reports, stable hashes) do not depend
on scripts that know the answers.

Assertions here are mechanical + determinism only: with no scripted
reply, all declared metrics measure False with whole-trace citations and
the run ends at the step budget ('cutoff').  A generated-candidates
variant drives the route's one-fixed-schema generator through the same
hash-derived seam.

Ranking is REFUSED in this leg, and that is the correct result (updated
2026-08-04, defect D2).  The hash-derived sender is CONTENT-BLIND by
construction -- its every response is a function of sha256(seed+prompt)
over fixed generic templates -- so the candidate text handed to the
insertion actor can never propagate to the recipient.  Every branch
therefore runs the counterfactual's independent variable at the same
(undelivered) value, and ``outcomes.ranking`` refuses to name a winner
instead of ranking model-sampling noise.  Before the fix this leg
published a winner "decided by the candidate-id tie-break" and the
report/artifact assertions below covered exactly that.  The leg now
proves the mechanics AND the refusal; determinism is asserted over the
artifacts that still exist (the causal trace report, which does not go
through ranking) plus the evaluated branch contracts themselves.
"""

from __future__ import annotations

import json
import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine individual-slice suite requires Python >= 3.12 "
        "(Concordia floor); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from individual_helpers import (HashDerivedGeneratorModel,
                                HashDerivedModel, MOCK_TEMPLATES,
                                mock_factory_builder, run_slice)
from sworldmodel.compilation.decision_route import generator_config_hash
from sworldmodel.decision.contracts import (DELIVERY_NOT_DELIVERED,
                                            TERMINAL_STATUSES,
                                            delivery_status)
from sworldmodel.reporting import (trace_report_canonical_json,
                                   trace_report_content_hash,
                                   validate_trace_report)


def run_mock_slice(**kwargs):
    """The mock leg never delivers its intervention (content-blind
    sender), so ranking legitimately refuses -- see the module
    docstring."""
    kwargs.setdefault("allow_delivery_refusal", True)
    return run_slice(mock_factory_builder, **kwargs)


#: contract keys that are deterministic run to run (wall-clock runtime
#: stats are excluded for the same reason cf_helpers excludes them)
_SIGNATURE_KEYS = ("branch_id", "candidate_id", "world_id",
                   "terminal_status", "terminal_world_state",
                   "event_trace", "outcome_metrics",
                   "infrastructure_errors", "intervention_delivered",
                   "unresolved_observers")


def _branch_signature(outcome) -> str:
    """Byte-comparable signature of the evaluated branch contracts (the
    determinism target that survives a refused ranking)."""
    return json.dumps(
        [{key: result.to_dict()[key] for key in _SIGNATURE_KEYS}
         for result in outcome.evaluated], sort_keys=True)


def test_hash_derived_model_is_a_pure_function_of_the_prompt():
    """The mock's determinism basis, proven directly: same (seed,
    prompt) -> same response; different seed or prompt -> the response
    may differ; every non-roster response is a filled generic template."""
    model_a = HashDerivedModel("seed_one")
    model_b = HashDerivedModel("seed_one")
    prompt = "An arbitrary situation description with a question."
    other_prompt = "A different situation description entirely."
    first = model_a.sample_text(prompt)
    # Same seed + same prompt -> same response, across calls and
    # instances (no hidden call-counter state).
    assert first == model_a.sample_text(prompt) \
        == model_b.sample_text(prompt)
    # A different prompt changes the hash-derived tag (deterministic
    # fact for these fixed strings), so the response is prompt-driven.
    assert model_a.sample_text(other_prompt) != first
    assert any(first.startswith(template.split("{tag}")[0])
               for template in MOCK_TEMPLATES)


def test_mock_model_slice_is_mechanically_complete():
    outcome = run_mock_slice()

    # Every branch ran to an EXPLICIT terminal status with a complete
    # trace and zero infrastructure errors.
    assert len(outcome.evaluated) == 3
    for result in outcome.evaluated:
        assert result.infrastructure_errors == ()
        assert result.terminal_status in TERMINAL_STATUSES
        assert result.terminal_status == "cutoff"  # budget exhausted
        assert len(result.event_trace) == 3  # premise + both turns
        # Metrics measured (False) WITH citations: the absence readings
        # cite the recorded whole-trace scan bound.
        for name in ("recipient_reply_sent", "meeting_scheduled",
                     "explicit_decline"):
            metric = result.outcome_metrics[name]
            assert metric.value is False
            assert metric.computed_from \
                == ("state:committed_event_count",)

    # Every branch MEASURED its intervention as undelivered: the
    # content-blind sender cannot propagate the candidate, so no
    # non-insertion actor ever saw it.
    for result in outcome.evaluated:
        assert delivery_status(result) == DELIVERY_NOT_DELIVERED
        fact = result.intervention_delivered
        assert fact["reached_actors"] == []
        assert fact["insertion_actor"] == "sender"
        assert fact["fragments_tested"] >= 1

    # So the ranking is REFUSED rather than published: a counterfactual
    # whose independent variable never varied downstream has nothing to
    # compare.  The trace artifact still assembles and validates.
    assert outcome.report is None and outcome.recommendation is None
    assert outcome.delivery_refusal
    assert "refusing to rank" in outcome.delivery_refusal
    for candidate_id in ("user_001", "user_002", "user_003"):
        assert candidate_id in outcome.delivery_refusal
    validate_trace_report(outcome.trace)

    # The causal trace is complete: attempts recorded for both actors
    # per branch, and every attempt is a hash-derived template fill.
    for branch in outcome.trace["branches"]:
        assert branch["runner_record_available"] is True
        assert branch["steps_completed"] == 2
        records = branch["actor_records"]
        assert sorted(records) == ["recipient", "sender"]
        for record in records.values():
            assert len(record["attempts"]) == 1
            attempt = record["attempts"][0]["attempt"]
            assert any(
                attempt.startswith(template.split("{tag}")[0])
                for template in MOCK_TEMPLATES), attempt
        assert branch["unattributed_attempts"] == []


def test_mock_model_slice_deterministic_across_two_runs():
    first = run_mock_slice()
    second = run_mock_slice()
    # The recommendation report does not exist in this leg (ranking is
    # refused); everything that does exist is byte-identical, including
    # the refusal message and the per-branch delivery facts.
    assert first.delivery_refusal == second.delivery_refusal
    assert _branch_signature(first) == _branch_signature(second)
    assert trace_report_content_hash(first.trace) \
        == trace_report_content_hash(second.trace)
    assert trace_report_canonical_json(first.trace) \
        == trace_report_canonical_json(second.trace)


def test_mock_model_generated_candidate_leg():
    """The route's one-fixed-schema candidate generator, driven through
    the same duck-typed ``sample_text`` seam by a hash-derived mock:
    exactly one generation call, a strict-JSON candidate, and the full
    slice completes mechanically on the generated action."""
    generator = HashDerivedGeneratorModel()
    outcome = run_mock_slice(actions=(), permission=True,
                             generator_model=generator)

    # Exactly one model call produced exactly one generated candidate
    # carrying the fixed generator configuration hash.
    assert len(generator.prompts) == 1
    assert len(outcome.inputs.candidates) == 1
    candidate = outcome.inputs.candidates[0]
    assert candidate.candidate_id == "gen_001"
    assert candidate.provenance.source == "generated"
    assert candidate.provenance.generator_config_hash \
        == generator_config_hash()
    assert candidate.action.startswith("Carry out documented option ")

    # The generated action was inserted at the boundary and DELIVERED to
    # the acting entity: it appears in the insertion actor's recorded
    # observations and acting prompt (a non-scripted model does not echo
    # it, so commit content is the model's own hash-derived turn).
    result = outcome.evaluated[0]
    assert result.infrastructure_errors == ()
    assert result.terminal_status in TERMINAL_STATUSES
    sender_rows = outcome.trace["branches"][0]["actor_records"][
        "sender"]["observations"]
    assert any(candidate.action in row for row in sender_rows)
    sender_model = outcome.capture["gen_001"]["actors"]["sender"]
    assert any(candidate.action in prompt
               for prompt in sender_model.prompts)
    validate_trace_report(outcome.trace)

    # ... and it went NO FURTHER.  This assertion is the one this test
    # was a single actor short of before defect D2 was closed: delivery
    # to the insertion actor was proven, delivery to anybody else was
    # never checked, and a winner was published regardless.  With the
    # measurement in place the single-candidate ranking is refused.
    assert delivery_status(result) == DELIVERY_NOT_DELIVERED
    assert result.intervention_delivered["reached_actors"] == []
    assert outcome.report is None and outcome.recommendation is None
    assert "gen_001" in outcome.delivery_refusal
    assert "1 measured branches" in outcome.delivery_refusal

    # Deterministic like everything else in this leg.
    second = run_mock_slice(actions=(), permission=True,
                            generator_model=HashDerivedGeneratorModel())
    assert second.delivery_refusal == outcome.delivery_refusal
    assert _branch_signature(second) == _branch_signature(outcome)
    assert trace_report_content_hash(second.trace) \
        == trace_report_content_hash(outcome.trace)
