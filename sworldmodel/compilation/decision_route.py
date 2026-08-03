"""Lightweight ``DecisionProblem`` route above the compiled world.

Directive ("Minimal compiler connection"): given a ``DecisionProblem`` and
a compiled world -- a manually supplied fixture world or the output of
:mod:`sworldmodel.compilation.existing_compiler_adapter` -- produce the
validated ``(CompiledDecisionWorld, candidates)`` pair the existing
counterfactual manager (``sworldmodel.counterfactuals.run_candidates``)
and branch executor consume.  Supported candidate sources:

- **user-supplied actions**: each ``problem.candidate_interventions``
  string becomes one ``InterventionCandidate`` under fixed code-owned
  rules (identifier ``user_NNN`` in declaration order; the world's single
  insertion actor as decision owner; timing = the world's start instant;
  action text verbatim; summary = whitespace-collapsed action head);
- **a minimal generated set**: ONE fixed prompt template and ONE fixed
  response schema (:data:`GENERATOR_PROMPT_TEMPLATE`,
  :data:`GENERATOR_RESPONSE_SCHEMA`) behind the existing model seam --
  any object exposing ``sample_text(prompt) -> str`` (every Concordia
  ``LanguageModel`` qualifies); exactly one call per generation; the
  response must be strict JSON matching the schema or the route fails
  loudly with every collected defect (no repair, no re-roll).  Generated
  candidates carry ``provenance.source = 'generated'`` and the
  configuration hash of the fixed template + schema + limit.

Candidate generation QUALITY is explicitly not a completion criterion of
this engineering pass; correct plumbing is.  The full dynamic
action-search algorithm is out of scope.

Refused loudly (never repaired): a problem whose decision owner does not
resolve to the world's single insertion actor; generation without the
problem's explicit permission; a request yielding zero candidates;
malformed generator output.  This module performs no LLM calls of its own
(the injected model object is called exactly once per generation) and is
pure stdlib -- it never imports Concordia, the compiler, or any engine
backend.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            ContractValidationError,
                                            DecisionProblem, EvaluatorSpec,
                                            InterventionCandidate,
                                            IssueCollector, SCHEMA_VERSION,
                                            ValidationIssue, _check_str,
                                            canonical_time)
from sworldmodel.decision.registry import ContractRegistry
from sworldmodel.decision.validation import validate_semantics

DECISION_ROUTE_VERSION = "decision_route_v1"
GENERATOR_VERSION = "candidate_generator_v1"

#: fixed default cap on generated candidates (part of the hashed config)
DEFAULT_MAX_GENERATED = 3

#: summary derivation cap (whitespace-collapsed action head), the same
#: fixed rule the strict fixture loader applies
_SUMMARY_LIMIT = 120

#: THE one fixed response schema for candidate generation (directive:
#: "a minimal LLM candidate generator using one fixed schema")
GENERATOR_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidates"],
    "properties": {
        "candidates": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["summary", "action"],
                "properties": {
                    "summary": {"type": "string", "minLength": 1},
                    "action": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

#: THE one fixed prompt template; every placeholder is a DecisionProblem
#: field or a fixed configuration value -- nothing world-private enters
GENERATOR_PROMPT_TEMPLATE = (
    "Propose candidate actions for the decision problem below.\n"
    "Respond with ONLY a JSON object matching this schema exactly -- no "
    "surrounding text, no extra fields:\n"
    "{schema}\n"
    "Propose between 1 and {max_candidates} candidates. Each candidate "
    "is one concrete action the decision owner could take inside the "
    "window. Do not repeat an already-supplied candidate.\n"
    "Decision owner: {decision_owner}\n"
    "Desired outcome: {desired_outcome}\n"
    "Success criteria: {success_criteria}\n"
    "Constraints: {constraints}\n"
    "Relevant context: {relevant_context}\n"
    "Window: {start} to {cutoff}\n"
    "Already-supplied candidates: {supplied}\n")


@dataclass(frozen=True)
class DecisionRunInputs:
    """The validated pair (plus bindings) ready for the existing
    counterfactual manager: ``run_candidates(inputs.world,
    inputs.candidates, evaluator_spec=inputs.evaluator_spec,
    registry=inputs.registry, ...)``."""

    problem: DecisionProblem
    world: CompiledDecisionWorld
    candidates: tuple
    evaluator_spec: EvaluatorSpec
    registry: ContractRegistry


def _fail(path: str, code: str, message: str) -> None:
    raise ContractValidationError([ValidationIssue(path, code, message)])


def _derive_summary(action: str) -> str:
    collapsed = " ".join(action.split())
    return collapsed[:_SUMMARY_LIMIT]


def _candidate_payload(candidate_id: str, summary: str, action: str,
                       owner: str, timing: str, provenance: dict) -> dict:
    return {
        "contract_type": InterventionCandidate.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "summary": summary,
        "action": action,
        "decision_owner": owner,
        "timing": timing,
        "constraints": [],
        "provenance": provenance,
    }


def build_user_candidates(problem: DecisionProblem,
                          world: CompiledDecisionWorld) -> tuple:
    """Map ``problem.candidate_interventions`` into validated
    ``InterventionCandidate`` objects under the fixed code-owned rules
    (see the module docstring).  Returns an empty tuple when the problem
    supplies none.
    """
    issues = IssueCollector()
    if not isinstance(problem, DecisionProblem):
        issues.add("problem", "wrong_type",
                   "expected a DecisionProblem instance, got "
                   f"{type(problem).__name__}")
    if not isinstance(world, CompiledDecisionWorld):
        issues.add("world", "wrong_type",
                   "expected a CompiledDecisionWorld instance, got "
                   f"{type(world).__name__}")
    issues.raise_if_any()

    owner = world.intervention_insertion_point.actor_id
    timing = canonical_time(world.start_time)
    return tuple(
        InterventionCandidate.from_dict(_candidate_payload(
            f"user_{index + 1:03d}", _derive_summary(action), action,
            owner, timing,
            {"source": "user_supplied", "generator_config_hash": ""}))
        for index, action in enumerate(problem.candidate_interventions))


def generator_config_hash(max_candidates: int = DEFAULT_MAX_GENERATED
                          ) -> str:
    """sha256 identity of the FIXED generator configuration (version +
    prompt template + response schema + candidate cap); recorded in every
    generated candidate's provenance."""
    payload = {
        "generator_version": GENERATOR_VERSION,
        "prompt_template": GENERATOR_PROMPT_TEMPLATE,
        "response_schema": GENERATOR_RESPONSE_SCHEMA,
        "max_candidates": max_candidates,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()


def build_generator_prompt(problem: DecisionProblem,
                           max_candidates: int = DEFAULT_MAX_GENERATED
                           ) -> str:
    """Deterministic prompt assembly from the fixed template and the
    problem's own fields; no other information enters."""
    if not isinstance(problem, DecisionProblem):
        _fail("problem", "wrong_type",
              "expected a DecisionProblem instance, got "
              f"{type(problem).__name__}")
    if type(max_candidates) is not int or max_candidates < 1:
        _fail("max_candidates", "invalid_value",
              "max_candidates must be an integer >= 1")
    return GENERATOR_PROMPT_TEMPLATE.format(
        schema=json.dumps(GENERATOR_RESPONSE_SCHEMA, sort_keys=True,
                          indent=1),
        max_candidates=max_candidates,
        decision_owner=problem.decision_owner,
        desired_outcome=problem.desired_outcome,
        success_criteria=problem.success_criteria,
        constraints="; ".join(problem.constraints) or "none declared",
        relevant_context=problem.relevant_context or "none supplied",
        start=canonical_time(problem.time_horizon.start),
        cutoff=canonical_time(problem.time_horizon.cutoff),
        supplied="; ".join(problem.candidate_interventions) or "none")


def _extract_json_text(raw, issues) -> str | None:
    """Mechanical extraction only: the raw text itself, or the body of
    exactly one complete code fence.  Anything else is a defect -- the
    route never repairs model output."""
    if not isinstance(raw, str) or not raw.strip():
        issues.add("generator_response", "wrong_type",
                   "the model returned no usable text")
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
        issues.add("generator_response", "invalid_value",
                   "unterminated or malformed code fence in the model "
                   "output")
        return None
    return text


def parse_generator_response(raw, max_candidates: int) -> list:
    """Strictly parse one model response against the fixed schema.

    Returns the list of ``{summary, action}`` entries; raises
    ``ContractValidationError`` with EVERY collected defect on any
    deviation (non-JSON text, wrong root shape, unknown fields, missing
    fields, blank strings, an empty list, or more than
    ``max_candidates`` entries).
    """
    issues = IssueCollector()
    text = _extract_json_text(raw, issues)
    issues.raise_if_any()
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ContractValidationError([ValidationIssue(
            "generator_response", "invalid_value",
            f"the model output is not valid JSON: {exc}")])
    if not isinstance(data, dict):
        _fail("generator_response", "wrong_type",
              f"expected a JSON object, got {type(data).__name__}")
    for key in sorted(set(data) - {"candidates"}):
        issues.add(f"generator_response.{key}", "unknown_field",
                   f"unknown field {key!r}: the fixed schema has exactly "
                   "one key, 'candidates'")
    if "candidates" not in data:
        issues.add("generator_response.candidates", "missing_field",
                   "required field 'candidates' is missing")
    issues.raise_if_any()

    items = data["candidates"]
    if not isinstance(items, list) or not items:
        _fail("generator_response.candidates", "empty_collection",
              "'candidates' must be a non-empty array")
    if len(items) > max_candidates:
        _fail("generator_response.candidates", "invalid_value",
              f"the model proposed {len(items)} candidates, above the "
              f"fixed limit of {max_candidates}")
    entries: list = []
    for index, item in enumerate(items):
        path = f"generator_response.candidates[{index}]"
        if not isinstance(item, dict):
            issues.add(path, "wrong_type",
                       f"expected an object, got {type(item).__name__}")
            continue
        for key in sorted(set(item) - {"summary", "action"}):
            issues.add(f"{path}.{key}", "unknown_field",
                       f"unknown field {key!r}: each candidate has "
                       "exactly 'summary' and 'action'")
        summary = action = None
        if "summary" not in item:
            issues.add(f"{path}.summary", "missing_field",
                       "required field 'summary' is missing")
        else:
            summary = _check_str(item["summary"], f"{path}.summary",
                                 issues)
        if "action" not in item:
            issues.add(f"{path}.action", "missing_field",
                       "required field 'action' is missing")
        else:
            action = _check_str(item["action"], f"{path}.action", issues)
        if summary is not None and action is not None:
            entries.append({"summary": summary, "action": action})
    issues.raise_if_any()
    return entries


def generate_candidates(problem: DecisionProblem,
                        world: CompiledDecisionWorld, *, model,
                        max_candidates: int = DEFAULT_MAX_GENERATED
                        ) -> tuple:
    """Generate candidates through the existing model seam: ONE
    ``model.sample_text`` call on the fixed prompt, strict parsing, and
    the fixed code-owned candidate rules (identifier ``gen_NNN``; the
    world's insertion actor; timing = the world's start instant;
    ``provenance.source = 'generated'`` with the configuration hash).

    Requires ``problem.candidate_generation_permission``; generation
    without permission is refused, never performed quietly.
    """
    issues = IssueCollector()
    if not isinstance(problem, DecisionProblem):
        issues.add("problem", "wrong_type",
                   "expected a DecisionProblem instance, got "
                   f"{type(problem).__name__}")
    if not isinstance(world, CompiledDecisionWorld):
        issues.add("world", "wrong_type",
                   "expected a CompiledDecisionWorld instance, got "
                   f"{type(world).__name__}")
    if type(max_candidates) is not int or max_candidates < 1:
        issues.add("max_candidates", "invalid_value",
                   "max_candidates must be an integer >= 1")
    sample = getattr(model, "sample_text", None)
    if not callable(sample):
        issues.add("model", "wrong_type",
                   "candidate generation needs a language-model object "
                   "exposing sample_text(prompt) -- the existing model "
                   f"seam; got {type(model).__name__}")
    issues.raise_if_any()
    if not problem.candidate_generation_permission:
        _fail("candidate_generation_permission", "invalid_value",
              "the decision problem does not permit candidate "
              "generation; supply candidate_interventions instead")

    prompt = build_generator_prompt(problem, max_candidates)
    raw = sample(prompt)
    entries = parse_generator_response(raw, max_candidates)
    config_hash = generator_config_hash(max_candidates)
    owner = world.intervention_insertion_point.actor_id
    timing = canonical_time(world.start_time)
    return tuple(
        InterventionCandidate.from_dict(_candidate_payload(
            f"gen_{index + 1:03d}", entry["summary"], entry["action"],
            owner, timing,
            {"source": "generated", "generator_config_hash": config_hash}))
        for index, entry in enumerate(entries))


def prepare_decision_inputs(
    problem: DecisionProblem,
    world: CompiledDecisionWorld,
    *,
    evaluator_spec: EvaluatorSpec,
    registry: ContractRegistry | None = None,
    generator_model=None,
    max_generated: int = DEFAULT_MAX_GENERATED,
) -> DecisionRunInputs:
    """Assemble and validate the complete run input set.

    Order of operations: type gates -> world registration -> problem
    semantics against the registry -> decision-owner-vs-insertion-actor
    equality -> user-supplied candidates -> optional generation (only
    when ``generator_model`` is supplied AND the problem permits it) ->
    per-candidate semantic validation and registration.  Raises
    ``ContractValidationError`` on any defect; never repairs, never
    narrows the request silently.
    """
    issues = IssueCollector()
    if not isinstance(problem, DecisionProblem):
        issues.add("problem", "wrong_type",
                   "expected a DecisionProblem instance, got "
                   f"{type(problem).__name__}")
    if not isinstance(world, CompiledDecisionWorld):
        issues.add("world", "wrong_type",
                   "expected a CompiledDecisionWorld instance, got "
                   f"{type(world).__name__}")
    if not isinstance(evaluator_spec, EvaluatorSpec):
        issues.add("evaluator_spec", "wrong_type",
                   "expected an EvaluatorSpec instance (the declared "
                   "code-owned outcome metrics), got "
                   f"{type(evaluator_spec).__name__}")
    if registry is not None and not isinstance(registry, ContractRegistry):
        issues.add("registry", "wrong_type",
                   "registry must be a ContractRegistry when supplied, "
                   f"got {type(registry).__name__}")
    issues.raise_if_any()

    registry = registry if registry is not None else ContractRegistry()
    if not registry.has_world(world.world_id):
        registry.register_world(world)
    validate_semantics(problem, registry, world_id=world.world_id)

    resolved_owner = registry.resolve_actor_reference(
        world.world_id, problem.decision_owner)
    insertion = world.intervention_insertion_point.actor_id
    if resolved_owner != insertion:
        _fail("decision_owner", "owner_mismatch",
              f"the problem's decision owner {problem.decision_owner!r} "
              f"resolves to {resolved_owner!r}, but the compiled world's "
              f"single insertion boundary belongs to {insertion!r}; the "
              "route never re-targets the boundary")

    candidates = list(build_user_candidates(problem, world))
    if generator_model is not None:
        candidates.extend(generate_candidates(
            problem, world, model=generator_model,
            max_candidates=max_generated))
    if not candidates:
        _fail("candidate_interventions", "empty_collection",
              "no candidates to run: the problem supplies none and no "
              "generator model was provided; at least one intervention "
              "candidate is required")

    for candidate in candidates:
        validate_semantics(candidate, registry, world_id=world.world_id)
        registry.register_candidate(candidate, world.world_id)

    return DecisionRunInputs(problem=problem, world=world,
                             candidates=tuple(candidates),
                             evaluator_spec=evaluator_spec,
                             registry=registry)
