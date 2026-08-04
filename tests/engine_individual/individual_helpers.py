"""Test-owned helpers for the Phase 9 individual-slice suite (engine env).

Import this module AFTER the per-module version/importorskip gates: it
imports ``cf_helpers`` (tests/engine_counterfactuals), which imports the
Concordia language-model interface available only in the pinned engine
environment (Python >= 3.12).

Scenario vocabulary (actor names, message texts, reply words, metric
needles) lives HERE, in ``cf_helpers``, and in the frozen fixture --
never in ``sworldmodel/`` (the hardcoding guard scans production on both
interpreters).

Three model legs drive the same slice:

- **scripted**  -- the proven ``cf_helpers.fixture_model_factory``
  implementing the frozen fixture's ``deterministic_script``;
- **mock**      -- :class:`HashDerivedModel`: a deterministic
  NON-scripted model whose response is a pure function of
  sha256(role seed + prompt) over fixed GENERIC templates.  It knows no
  scenario script and no expected answers, so this leg proves the slice
  does not depend on scripts knowing the outcome;
- **live**      -- :class:`DeepSeekChatModel`: a minimal test-owned
  Concordia ``LanguageModel`` over the DeepSeek OpenAI-compatible API
  (mechanical assertions only; never semantic determinism).

The suite's metric predicates are ATTRIBUTION-ANCHORED, and the anchor
binds to the resolved turn's ACTIVE PLAYER (phases 8-11 review finding
F1 closed the earlier substring co-occurrence form): a row counts only
when it carries the upstream resolved-actor-turn wrapper
(:data:`ACTOR_TURN_ANCHOR`) AND the row's OWN leading ``Name:``
attribution -- the ``{name}: {content}`` turn format the upstream
sequential engine stamps before commit -- names the predicate's actor,
AND the needles occur in that actor's OWN attributed content.  A
Game-Master narration row (premise or pre-start record) textually
claiming the outcome never counts (no anchor), and neither does another
actor's turn EMBEDDING a ``Morgan: Reply ...`` proxy segment (the row's
leading attribution names the embedding actor, not Morgan).  The gate-C
narration test and the proxy-attribution suite prove both distinctions.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from concordia.language_model import language_model

from baseline_helpers import (AWARE_QUESTION_NEEDLE,  # noqa: F401
                              StrictScriptedModel, all_prompt_text,
                              aware_rule)
from cf_helpers import (FIXTURE_ONE_PATH, MAX_STEPS, SEED,  # noqa: F401
                        RECIPIENT_CTA, SENDER_CTA, RaisingModel,
                        branch_signature, file_sha256,
                        fixture_model_factory, fixture_status_rule,
                        load_fixture_one, make_candidate,
                        recorded_fixture_hash)
from sworldmodel.compilation.decision_route import prepare_decision_inputs
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.decision.contracts import (DecisionProblem,
                                            RecommendationResult,
                                            SCHEMA_VERSION)
from sworldmodel.outcomes import evaluate_branches, exists_metric
from sworldmodel.reporting import (build_recommendation_report,
                                   build_trace_report)

HERE = Path(__file__).resolve().parent
ARTIFACT_DIR = HERE / "artifacts"
RECOMMENDATION_ARTIFACT_PATH = (
    ARTIFACT_DIR / "individual_reply_recommendation_report.json")
TRACE_ARTIFACT_PATH = ARTIFACT_DIR / "individual_reply_trace_report.json"

#: the upstream sequential engine wraps every RESOLVED ACTOR TURN in this
#: putative-event framing before commit; premise and pre-start narration
#: rows never carry it, so it anchors metrics to actor-attributed rows
ACTOR_TURN_ANCHOR = "Putative event to resolve:"

#: characters that may never appear inside a leading attribution NAME:
#: their presence means the first separator found belongs to later
#: content, i.e. the row head is not a well-formed ``{name}: {content}``
#: turn stamp (fail closed: such a row matches no metric)
_NAME_BREAK_CHARS = ".!?\"\n"


def leading_attribution(description: str):
    """``(name, content)`` parsed from the row's OWN leading attribution,
    or ``None`` when the row is not a well-formed resolved actor turn.

    The upstream sequential engine commits every resolved turn as
    ``{anchor} {name}: {content}`` (engines/sequential.py formats the
    action as ``f'{name}: {raw_action}'``; EventResolution recognizes
    ``:`` and `` --`` as the attribution separators).  The name is the
    text between the anchor and the FIRST separator; a "name" carrying
    sentence punctuation or a quote means the head is unattributed and
    the parse refuses (returns ``None``) rather than guessing.
    """
    index = description.find(ACTOR_TURN_ANCHOR)
    if index < 0:
        return None
    tail = description[index + len(ACTOR_TURN_ANCHOR):].lstrip(" \t")
    colon = tail.find(":")
    dash = tail.find(" --")
    cuts = [cut for cut in (colon, dash) if cut >= 0]
    if not cuts:
        return None
    cut = min(cuts)
    if tail[cut] == ":":
        name, content = tail[:cut], tail[cut + 1:]
    else:
        name, content = tail[:cut], tail[cut + 3:]
    name = name.strip()
    if not name or any(char in name for char in _NAME_BREAK_CHARS):
        return None
    return name, content.strip()


def attributed_turn_matcher(actor: str, opening: str, *needles):
    """A matcher counting ONLY the named actor's own resolved turn: the
    row's leading attribution must name ``actor``, the actor's attributed
    content must START with ``opening`` (the old ``"{actor}: {opening}"``
    adjacency, now bound to the row's real active player), and every
    additional needle must occur in that content.  Substring
    co-occurrence elsewhere in the row -- e.g. a proxy ``Name: ...``
    segment embedded in ANOTHER actor's turn -- never matches."""
    assert actor and opening

    def matcher(description: str) -> bool:
        parsed = leading_attribution(description)
        if parsed is None:
            return False
        name, content = parsed
        if name != actor or not content.startswith(opening):
            return False
        return all(needle in content for needle in needles)

    matcher.actor = actor
    matcher.needles = (opening,) + tuple(needles)
    return matcher


def actor_turn_matcher(*needles):
    """A matcher for metrics owned by WHICHEVER actor's turn carries the
    needles: the row must be a well-formed resolved actor turn (anchor +
    leading attribution) and every needle must occur in the attributed
    content -- never in the framing, and never in a row that carries no
    attribution."""
    assert needles

    def matcher(description: str) -> bool:
        parsed = leading_attribution(description)
        if parsed is None:
            return False
        _name, content = parsed
        return all(needle in content for needle in needles)

    matcher.needles = tuple(needles)
    return matcher

#: the phrase the fixture's expected winner scripts into the reply, used
#: by the multi-turn memory test
REPLY_AGREE_PHRASE = "agreeing to a fifteen-minute conversation"

PROBLEM_ID = "individual_message_decision"
PROBLEM_DESIRED_OUTCOME = (
    "Morgan replies to the introductory message and a second "
    "conversation is scheduled before the window closes.")
PROBLEM_SUCCESS_CRITERIA = (
    "Measured by the declared evaluator only: recipient_reply_sent "
    "first, then meeting_scheduled and explicit_decline, computed from "
    "the recorded event trace and terminal world state.")
PROBLEM_CONTEXT = (
    "Alex may send Morgan one introductory message to open the window.")


def make_slice_problem(fx, *, actions=None, permission=False,
                       problem_id=PROBLEM_ID) -> DecisionProblem:
    """The fixture-1 message decision as a ``DecisionProblem``: 'which of
    these messages most increases the chance of a reply and a second
    conversation'.  ``actions`` defaults to the frozen fixture's three
    candidate actions, verbatim; the decision owner is named by the
    human-facing actor NAME and resolved by the route."""
    if actions is None:
        actions = [candidate.action for candidate in fx.candidates]
    return DecisionProblem.from_dict({
        "contract_type": DecisionProblem.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "problem_id": problem_id,
        "decision_owner": "Alex",
        "desired_outcome": PROBLEM_DESIRED_OUTCOME,
        "success_criteria": PROBLEM_SUCCESS_CRITERIA,
        "constraints": [],
        "time_horizon": {"start": "2026-08-03T14:00:00Z",
                         "cutoff": "2026-08-10T14:00:00Z"},
        "relevant_context": PROBLEM_CONTEXT,
        "candidate_interventions": list(actions),
        "candidate_generation_permission": permission,
    })


def anchored_predicates() -> dict:
    """Fixture-1 metric predicates, attribution-anchored (see module
    docstring): every metric requires the resolved-actor-turn wrapper
    AND binds to the row's OWN leading attribution -- only the
    recipient's own committed turn, opening with its reply text, can
    satisfy a reply metric."""
    return {
        "recipient_reply_sent": exists_metric(
            attributed_turn_matcher("Morgan", "Reply")),
        "meeting_scheduled": exists_metric(
            attributed_turn_matcher("Morgan", "Reply",
                                    REPLY_AGREE_PHRASE)),
        "explicit_decline": exists_metric(
            attributed_turn_matcher("Morgan", "Reply declining")),
    }


@dataclass(frozen=True)
class SliceOutcome:
    """Everything one full slice pass produced (route -> manager ->
    outcomes -> both reports)."""

    fx: object
    problem: DecisionProblem
    inputs: object
    run: object
    evaluated: tuple
    recommendation: RecommendationResult
    report: dict
    trace: dict
    capture: dict


def run_slice(model_factory_builder, *, actions=None, seed=SEED,
              max_steps=MAX_STEPS, provenance_label="deterministic",
              permission=False, generator_model=None) -> SliceOutcome:
    """One complete slice pass on a FRESH fixture load: frozen fixture ->
    DecisionProblem -> route (``prepare_decision_inputs``) ->
    ``run_candidates_detailed`` -> cited outcome evaluation -> the
    recommendation report and the causal trace report.

    ``model_factory_builder(fx, capture)`` returns the manager's
    ``model_factory(candidate, branch_seed)``.
    """
    fx = load_fixture_one()
    problem = make_slice_problem(fx, actions=actions,
                                 permission=permission)
    inputs = prepare_decision_inputs(
        problem, fx.world, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry, generator_model=generator_model)
    capture: dict = {}
    run = run_candidates_detailed(
        inputs.world, inputs.candidates,
        model_factory=model_factory_builder(fx, capture),
        seed=seed, max_steps=max_steps,
        evaluator_spec=inputs.evaluator_spec, registry=inputs.registry,
        model_config={"kind": "phase9_individual_slice"})
    evaluated = evaluate_branches(
        run.results, anchored_predicates(),
        evaluator_spec=inputs.evaluator_spec,
        status_rule=fixture_status_rule, registry=inputs.registry)
    report = build_recommendation_report(
        problem, inputs.candidates, run, evaluated,
        inputs.evaluator_spec, provenance_label=provenance_label,
        registry=inputs.registry)
    trace = build_trace_report(run, evaluated)
    recommendation = RecommendationResult.from_dict(
        report["recommendation"])
    return SliceOutcome(fx=fx, problem=problem, inputs=inputs, run=run,
                        evaluated=tuple(evaluated),
                        recommendation=recommendation, report=report,
                        trace=trace, capture=capture)


def scripted_factory_builder(fx, capture):
    """The proven fixture scripted models (cf_helpers), keyed on which
    candidate TEXT the recipient observes -- unchanged for route-built
    candidates because the route carries the fixture actions verbatim."""
    return fixture_model_factory(fx, capture=capture)


def run_scripted_slice(**kwargs) -> SliceOutcome:
    return run_slice(scripted_factory_builder, **kwargs)


def route_action_map(fx, inputs) -> dict:
    """Bijection route candidate_id -> fixture candidate_id, keyed on the
    verbatim action text the route carried through."""
    by_action = {candidate.action: candidate.candidate_id
                 for candidate in fx.candidates}
    mapping = {}
    for candidate in inputs.candidates:
        fixture_id = by_action.get(candidate.action)
        assert fixture_id is not None, (
            f"route candidate {candidate.candidate_id} action does not "
            "match any fixture candidate")
        mapping[candidate.candidate_id] = fixture_id
    assert sorted(mapping.values()) == sorted(by_action.values())
    return mapping


# ---------------------------------------------------------------------------
# Deterministic mock-model leg (non-scripted)
# ---------------------------------------------------------------------------

#: fixed GENERIC action templates; the {tag} token is hash-derived.  No
#: scenario vocabulary, no reply words, no answers.
MOCK_TEMPLATES = (
    "Take stock of the situation and record note {tag}.",
    "Compose a short considered message labeled {tag} and set it aside.",
    "Review the latest information and file summary {tag}.",
    "Ask one clarifying question tagged {tag} at the next opportunity.",
)


class HashDerivedModel(language_model.LanguageModel):
    """Deterministic NON-scripted model: the response is a pure function
    of sha256(role_seed + prompt) over :data:`MOCK_TEMPLATES`.

    The one policy exception is the game master's observer question
    (:data:`AWARE_QUESTION_NEEDLE`), answered with the full cast roster
    -- a broadcast-awareness GM policy supplied as CONFIGURATION (the
    harness knows the cast), not as a script that knows outcomes.
    ``sample_choice`` raises: no multiple-choice model path may execute
    anywhere in this slice.
    """

    def __init__(self, role_seed: str, roster_names=()):
        self._role_seed = str(role_seed)
        self._roster = tuple(roster_names)
        self.prompts: list = []

    def sample_text(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        if self._roster and AWARE_QUESTION_NEEDLE in prompt:
            return ", ".join(self._roster)
        digest = hashlib.sha256(
            (self._role_seed + "\x1f" + prompt).encode("utf-8")).hexdigest()
        template = MOCK_TEMPLATES[int(digest[:8], 16) % len(MOCK_TEMPLATES)]
        return template.format(tag=digest[:10])

    def sample_choice(self, prompt: str, responses, **kwargs):
        raise AssertionError(
            "sample_choice was called: the deterministic mock leg must "
            "never take a multiple-choice model path; prompt head: "
            f"{prompt[:200]!r}")


def mock_factory_builder(fx, capture):
    """Per-branch fresh hash-derived models: role seeds bind the branch
    seed and the role, so branches stay distinct AND reproducible."""
    names = [actor.name for actor in fx.world.actors]
    actor_ids = [actor.actor_id for actor in fx.world.actors]

    def factory(candidate, branch_seed):
        actor_models = {
            actor_id: HashDerivedModel(f"{branch_seed}|actor|{actor_id}")
            for actor_id in actor_ids}
        gm_model = HashDerivedModel(f"{branch_seed}|gm", roster_names=names)
        capture[candidate.candidate_id] = {
            "actors": actor_models, "gm": gm_model, "seed": branch_seed}
        return actor_models, gm_model

    return factory


class HashDerivedGeneratorModel:
    """Duck-typed ``sample_text`` seam for the route's candidate
    generator: emits strict fixed-schema JSON with ONE hash-derived
    generic action (no scenario vocabulary, no known answers)."""

    def __init__(self, role_seed: str = "generator"):
        self._role_seed = role_seed
        self.prompts: list = []

    def sample_text(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        digest = hashlib.sha256(
            (self._role_seed + "\x1f" + prompt).encode("utf-8")).hexdigest()
        tag = digest[:10]
        return (
            '{"candidates": [{"summary": "Documented option ' + tag
            + '", "action": "Carry out documented option ' + tag
            + ' within the declared window."}]}')


# ---------------------------------------------------------------------------
# Live-model leg (DeepSeek OpenAI-compatible API; mechanical only)
# ---------------------------------------------------------------------------

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL_ID = "deepseek-chat"
#: marker distinguishing transport failure from assertion failure
LIVE_UNREACHABLE_MARKER = "LIVE_ENDPOINT_UNREACHABLE"


class LiveEndpointError(RuntimeError):
    """The live endpoint could not be used (transport/auth/timeout).
    Carries the exact underlying evidence; the marker string lets tests
    distinguish this from any assertion failure."""


class DeepSeekChatModel(language_model.LanguageModel):
    """Minimal test-owned Concordia ``LanguageModel`` over the DeepSeek
    OpenAI-compatible chat API.

    Bounded and evidence-recording: temperature 0, a hard per-response
    token cap, generous per-call timeout, and every call's served model
    id + elapsed seconds appended to the shared ``evidence`` list.  Any
    transport-level failure raises :class:`LiveEndpointError` with the
    exact underlying exception -- inside a branch the runner records it
    verbatim in ``infrastructure_errors``, where the smoke test finds
    the marker and reports (never hides) it.
    """

    def __init__(self, *, api_key: str, system_hint: str,
                 evidence: list, timeout_s: float = 90.0,
                 max_tokens: int = 200):
        import openai  # engine-env test dependency (already pinned)

        self._client = openai.OpenAI(
            api_key=api_key, base_url=DEEPSEEK_BASE_URL,
            timeout=timeout_s, max_retries=2)
        self._system_hint = system_hint
        self._max_tokens = int(max_tokens)
        self._evidence = evidence

    def sample_text(self, prompt: str, *, max_tokens: int | None = None,
                    terminators=(), temperature: float | None = None,
                    timeout: float | None = None, seed: int | None = None,
                    **kwargs) -> str:
        del temperature, timeout, seed, kwargs  # bounded fixed policy
        cap = self._max_tokens
        if type(max_tokens) is int and 0 < max_tokens < cap:
            cap = max_tokens
        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=DEEPSEEK_MODEL_ID,
                messages=[
                    {"role": "system", "content": self._system_hint},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=cap,
                temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001 - wrapped with evidence
            raise LiveEndpointError(
                f"{LIVE_UNREACHABLE_MARKER}: base_url="
                f"{DEEPSEEK_BASE_URL} model={DEEPSEEK_MODEL_ID} "
                f"cause={type(exc).__name__}: {exc!r}") from exc
        elapsed = time.perf_counter() - started
        text = response.choices[0].message.content or ""
        self._evidence.append({
            "served_model": response.model,
            "elapsed_s": round(elapsed, 3),
            "prompt_chars": len(prompt),
            "response_chars": len(text),
        })
        for terminator in terminators or ():
            text = text.split(terminator)[0]
        return text.strip()

    def sample_choice(self, prompt: str, responses, **kwargs):
        raise AssertionError(
            "sample_choice was called: no multiple-choice model path may "
            "execute in this slice; prompt head: " f"{prompt[:200]!r}")


ACTOR_SYSTEM_HINT = (
    "You are {name}, a person in a turn-based simulation. Private "
    "context and observations appear in the user message. Answer with "
    "exactly one short sentence in third person describing the single "
    "concrete action {name} takes next. No commentary, no options.")
GM_SYSTEM_HINT = (
    "You are the rules engine of a turn-based simulation. Answer the "
    "question in the user message directly and concisely. When asked "
    "which entities are aware of an event, answer with a comma-"
    "separated list of entity names only.")


def live_factory_builder(fx, capture, *, api_key: str, evidence: list):
    """Per-branch fresh live models with generic role hints; every call
    appends evidence to the shared list."""
    names = {actor.actor_id: actor.name for actor in fx.world.actors}

    def factory(candidate, branch_seed):
        del branch_seed  # live leg asserts mechanics, not determinism
        actor_models = {
            actor_id: DeepSeekChatModel(
                api_key=api_key,
                system_hint=ACTOR_SYSTEM_HINT.format(name=name),
                evidence=evidence)
            for actor_id, name in names.items()}
        gm_model = DeepSeekChatModel(
            api_key=api_key, system_hint=GM_SYSTEM_HINT,
            evidence=evidence)
        capture[candidate.candidate_id] = {
            "actors": actor_models, "gm": gm_model}
        return actor_models, gm_model

    return factory


def transport_failures(evaluated) -> list:
    """Every recorded infrastructure error that is live-transport
    evidence (the marker), across all branches."""
    found = []
    for result in evaluated:
        for error in result.infrastructure_errors:
            if LIVE_UNREACHABLE_MARKER in error:
                found.append(error)
    return found
