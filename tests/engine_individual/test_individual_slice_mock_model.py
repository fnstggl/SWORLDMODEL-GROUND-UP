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
reply, all declared metrics measure False with whole-trace citations,
the ranking falls to the DISCLOSED candidate-id tie-break, and the run
ends at the step budget ('cutoff').  A generated-candidates variant
drives the route's one-fixed-schema generator through the same
hash-derived seam.
"""

from __future__ import annotations

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
from sworldmodel.decision.contracts import TERMINAL_STATUSES
from sworldmodel.reporting import (report_canonical_json,
                                   report_content_hash,
                                   trace_report_canonical_json,
                                   trace_report_content_hash,
                                   validate_recommendation_report,
                                   validate_trace_report)


def run_mock_slice(**kwargs):
    return run_slice(mock_factory_builder, **kwargs)


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

    # Reports assemble and validate; the ranking is decided by the
    # DISCLOSED tie-break (nothing invented a difference).
    validate_recommendation_report(outcome.report)
    validate_trace_report(outcome.trace)
    assert outcome.report["decided_by_metric"] == "candidate_id_tie_break"
    assert outcome.recommendation.validation_status[
        "tie_break_candidate_id_lexicographic"] is True
    assert "applied in this ranking" \
        in outcome.recommendation.run_limitations

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
    assert report_content_hash(first.report) \
        == report_content_hash(second.report)
    assert report_canonical_json(first.report) \
        == report_canonical_json(second.report)
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
    # it, so commit content is the model's own hash-derived turn); the
    # slice completed with a validating artifact pair and an explicit
    # terminal status.
    result = outcome.evaluated[0]
    assert result.infrastructure_errors == ()
    assert result.terminal_status in TERMINAL_STATUSES
    sender_rows = outcome.trace["branches"][0]["actor_records"][
        "sender"]["observations"]
    assert any(candidate.action in row for row in sender_rows)
    sender_model = outcome.capture["gen_001"]["actors"]["sender"]
    assert any(candidate.action in prompt
               for prompt in sender_model.prompts)
    validate_recommendation_report(outcome.report)
    validate_trace_report(outcome.trace)
    assert outcome.report["winner"] == "gen_001"
    assert outcome.report["decided_by_metric"] == "single_candidate"

    # Deterministic like everything else in this leg.
    second = run_mock_slice(actions=(), permission=True,
                            generator_model=HashDerivedGeneratorModel())
    assert report_content_hash(second.report) \
        == report_content_hash(outcome.report)
    assert trace_report_content_hash(second.trace) \
        == trace_report_content_hash(outcome.trace)
