"""Test-owned helpers for the Phase 10 team-slice suite (engine env).

Import this module AFTER the per-module version/importorskip gates: it
imports ``baseline_helpers`` / ``cf_helpers`` / ``individual_helpers``
(earlier engine suites), which import the Concordia language-model
interface available only in the pinned engine environment
(Python >= 3.12).

Scenario vocabulary (actor names, turn texts, marker phrases, canaries)
lives HERE and in the frozen fixture -- never in ``sworldmodel/`` (the
hardcoding guard scans production on both interpreters).

The slice is fixture 2 (``team_commitment.yaml``): a five-person team
decision under a declared decision rule ("at least three explicit
commitments and no operations-lead veto"), driven end to end through the
real route -> counterfactual manager -> local Concordia backend (planner
+ builder + runner + hardened agency guard) -> cited outcome evaluation
-> both reporting artifacts, with STRICT scripted models only.

Structure of one branch (``TEAM_MAX_STEPS`` = 11 = two full five-actor
rotations plus the proposal owner's closing turn; fixed acting order in
world declaration order):

- ``announce_full_plan``      -- round 1 is the TEAM MEETING (every turn
  visible to all five), round 2 holds two PRIVATE POST-MEETING
  FOLLOW-UPS (Riley<->Sam, then Dana<->Sam) carrying per-conversation
  canary phrases, and step 11 records the declared failure outcome.
- ``private_ops_then_pilot``  -- round 1 opens with the PRIVATE
  Riley<->Sam workload conversation (the private-first candidate
  semantics), round 2 is the team meeting where the four explicit
  commitments land publicly, and step 11 records the declared success
  outcome.  Sam's round-2 meeting turn references the round-1 private
  cost-cap content (:data:`MEMORY_PHRASE`) -- the persistent-memory
  proof.
- ``immediate_binding_vote``  -- round 1 is the vote meeting where the
  authority holder exercises the declared veto; step 11 records the
  declared failure outcome.

Private versus shared interaction is expressed ENTIRELY through
existing configuration: the plan's ``notify_observers`` observer
question (the upstream event-resolution component asks the game-master
model "Which entities are aware of the event?" in a prompt containing
exactly the current event's text) is answered by the scripted GM model
from per-event visibility rules -- a needle unique to a private turn
maps to that conversation's participant names, and the generic
fallback rule broadcasts to the full roster.  No production change is
involved anywhere in this suite.

The metric predicates are ATTRIBUTION-ANCHORED (the recorded Phase 9
pattern, hardened by the phases 8-11 review finding F1): every metric
requires the upstream resolved-actor-turn wrapper
(``ACTOR_TURN_ANCHOR``) AND binds to the row's OWN leading ``Name:``
attribution (the ``{name}: {content}`` turn format the engine stamps
before commit), with the needles read from that actor's attributed
content -- never from substring co-occurrence anywhere in the row.  The
two authority-gated metrics (``veto_exercised``, ``pilot_accepted``)
additionally require the leading attribution to name the AUTHORITY
HOLDER and the content to OPEN with the utterance -- keyed to the
fixture's declared authority structure (the shared context and decision
rule name the operations lead's implementation veto).  Only events
emitted by the owning actor's own committed turn can satisfy a metric;
a Game-Master narration row textually claiming a tally, a coalition, or
the identical utterance spoken by a non-authority actor measures False
-- and so does a proxy ``Sam: <utterance>`` segment EMBEDDED in another
actor's turn (the row's leading attribution names the embedding actor).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from baseline_helpers import (StrictScriptedModel,  # noqa: F401
                              all_prompt_text, aware_rule)
from cf_helpers import (FIXTURE_DIR, SEED,  # noqa: F401
                        file_sha256, make_candidate, recorded_fixture_hash)
from individual_helpers import (ACTOR_TURN_ANCHOR,  # noqa: F401
                                actor_turn_matcher,
                                attributed_turn_matcher, route_action_map)
from sworldmodel.compilation.decision_route import prepare_decision_inputs
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            DecisionProblem,
                                            RecommendationResult,
                                            SCHEMA_VERSION)
from sworldmodel.decision.fixture_loader import load_fixture_file
from sworldmodel.decision.registry import ContractRegistry
from sworldmodel.outcomes import (count_metric, evaluate_branches,
                                  exists_metric)
from sworldmodel.outcomes.metrics import (WHOLE_TRACE_CITATION,
                                          matching_indices)
from sworldmodel.reporting import (build_recommendation_report,
                                   build_trace_report)

HERE = Path(__file__).resolve().parent
ARTIFACT_DIR = HERE / "artifacts"
RECOMMENDATION_ARTIFACT_PATH = (
    ARTIFACT_DIR / "team_commitment_recommendation_report.json")
TRACE_ARTIFACT_PATH = ARTIFACT_DIR / "team_commitment_trace_report.json"

FIXTURE_TWO_PATH = FIXTURE_DIR / "team_commitment.yaml"

#: two full five-actor rotations plus the proposal owner's closing turn
TEAM_MAX_STEPS = 11
#: one rotation of the five-actor fixed acting order
ROUND_LENGTH = 5
#: a timing inside the fixture-2 window for synthetic probe candidates
PROBE_TIMING = "2026-08-04T09:30:00Z"

#: the fixture's declared authority holder: the operations lead carries
#: the declared implementation veto (shared context + decision rule)
AUTHORITY_ACTOR_ID = "operations_lead"
AUTHORITY_NAME = "Sam"

# ---------------------------------------------------------------------------
# Metric marker phrases (scenario vocabulary; test-owned configuration)
# ---------------------------------------------------------------------------

#: an explicit support commitment, spoken in the committing actor's own
#: turn (any counting row must ALSO carry the actor-turn anchor)
COMMIT_MARKER = "an explicit commitment to"
#: explicit opposition, spoken in the opposing actor's own turn
OPPOSE_MARKER = "explicit opposition to"
#: the veto utterance; the metric binds it to the AUTHORITY HOLDER'S
#: own turn ("Sam: Exercise ..."), so the identical words spoken by any
#: other actor never measure as the veto
VETO_UTTERANCE = "Exercise the declared implementation veto"
#: the pilot acceptance utterance; likewise bound to the authority
#: holder's own turn (only the operations lead can accept the pilot)
PILOT_ACCEPT_UTTERANCE = "Accept the capped pilot"
#: the explicit outcome-recording phrase (the declared outcome must be
#: an actor-authored world event, never narration)
FINAL_MARKER = "the final decision of the team under the declared rule"

#: round-1 private content that Sam's round-2 meeting turn references
#: (the persistent-memory proof phrase)
MEMORY_PHRASE = "one-sprint cost cap"
#: private-conversation canaries -- each must reach exactly its
#: conversation's participants and nobody else
PRIVATE_OPS_CANARY = "the amber workload ledger figures"
FOLLOWUP_ONE_CANARY = "the crimson queue backlog"
FOLLOWUP_TWO_CANARY = "the violet reserve estimate"

RECORD_SUCCESS_TURN = (
    "Record the final decision of the team under the declared rule: the "
    "capped pilot proceeds this week.")
RECORD_FAILURE_TURN = (
    "Record the final decision of the team under the declared rule: the "
    "migration does not proceed this week.")

# ---------------------------------------------------------------------------
# Scripted turn tables (fixture candidate id -> actor id -> turns in
# acting order; ``None`` echoes the branch's inserted candidate action)
# ---------------------------------------------------------------------------

TEAM_TURNS = {
    "private_ops_then_pilot": {
        "proposal_owner": [
            None,
            "Present the limited, time-boxed pilot to the whole team, "
            "with the operations cost explicitly capped after the "
            "private workload conversation.",
            RECORD_SUCCESS_TURN,
        ],
        "operations_lead": [
            "Share the amber workload ledger figures with the proposal "
            "owner in the private conversation and ask for a one-sprint "
            "cost cap on the pilot's operations load.",
            "Accept the capped pilot under the privately requested "
            "one-sprint cost cap, and state an explicit commitment to "
            "the pilot; the declared implementation veto stays "
            "unexercised.",
        ],
        "budget_owner": [
            "Prepare the quarterly budget summary while the migration "
            "question is pending.",
            "State an explicit commitment to the capped pilot because "
            "its operations cost is bounded and stated.",
        ],
        "product_lead": [
            "Draft customer-pain notes for the upcoming migration "
            "discussion.",
            "State an explicit commitment to the pilot publicly, citing "
            "customer pain.",
        ],
        "neutral_member": [
            "Continue routine maintenance work and follow the team "
            "discussion when it opens.",
            "State an explicit commitment to the capped pilot after "
            "seeing the operations concern addressed.",
        ],
    },
    "announce_full_plan": {
        "proposal_owner": [
            None,
            "Follow up privately on the migration announcement and ask "
            "what operations load detail is driving the objection.",
            RECORD_FAILURE_TURN,
        ],
        "operations_lead": [
            "State explicit opposition to the migration plan, citing "
            "unaddressed operations load.",
            "Explain privately that the crimson queue backlog is the "
            "blocking operations load detail.",
        ],
        "budget_owner": [
            "Ask for bounded and stated costs before entering any "
            "commitment.",
            "Consult privately about operational feasibility and "
            "mention the violet reserve estimate.",
        ],
        "product_lead": [
            "State an explicit commitment to the migration plan "
            "publicly, citing customer pain.",
            "Summarize customer pain points in a note for the next "
            "product review.",
        ],
        "neutral_member": [
            "Abstain for now because the operations concerns remain "
            "unaddressed.",
            "File routine status updates unrelated to the migration.",
        ],
    },
    "immediate_binding_vote": {
        "proposal_owner": [
            None,
            "Compile the recorded responses without further requests.",
            RECORD_FAILURE_TURN,
        ],
        "operations_lead": [
            "Exercise the declared implementation veto against the "
            "unscoped migration request.",
            "Return to the operations queue triage.",
        ],
        "budget_owner": [
            "Decline to enter a commitment in the binding vote until "
            "costs are bounded.",
            "Review the quarterly budget ledger.",
        ],
        "product_lead": [
            "Vote in favor of the migration proposal and state an "
            "explicit commitment to it in the binding vote.",
            "Prepare the customer update note.",
        ],
        "neutral_member": [
            "Abstain from the immediate binding vote.",
            "Resume routine maintenance work.",
        ],
    },
}

#: per-branch private-visibility rules for the scripted GM model: a
#: needle unique to one committed event's text maps the observer answer
#: to that conversation's participant NAMES; every other event falls to
#: the generic full-roster rule.  (The upstream observer question's
#: prompt contains exactly the current event's text, so first-match
#: keying is sound; see the module docstring.)
TEAM_VISIBILITY = {
    "private_ops_then_pilot": [
        ("Privately address the operations lead's workload concern",
         ("Riley", "Sam")),
        (PRIVATE_OPS_CANARY, ("Riley", "Sam")),
    ],
    "announce_full_plan": [
        ("Follow up privately on the migration announcement",
         ("Riley", "Sam")),
        (FOLLOWUP_ONE_CANARY, ("Riley", "Sam")),
        (FOLLOWUP_TWO_CANARY, ("Dana", "Sam")),
    ],
    "immediate_binding_vote": [],
}

#: expected acting steps per actor under the fixed rotation (1-based)
EXPECTED_ATTEMPT_STEPS = {
    "proposal_owner": [1, 6, 11],
    "operations_lead": [2, 7],
    "budget_owner": [3, 8],
    "product_lead": [4, 9],
    "neutral_member": [5, 10],
}

PROBLEM_ID = "team_commitment_decision"
PROBLEM_DESIRED_OUTCOME = (
    "The team adopts the pipeline-migration proposal this week under "
    "the declared decision rule.")
PROBLEM_SUCCESS_CRITERIA = (
    "Measured by the declared evaluator only: decision_rule_satisfied "
    "first, then the declared secondary metrics, computed from the "
    "recorded event trace and terminal world state.")
PROBLEM_CONTEXT = (
    "Riley chooses how to seek adoption of the pipeline-migration "
    "proposal.")


def load_fixture_two():
    """Load the frozen team fixture through the strict loader (file
    untouched); returns a fresh LoadedFixture with its own registry."""
    return load_fixture_file(str(FIXTURE_TWO_PATH))


def actor_order(fx) -> list:
    return [actor.actor_id for actor in fx.world.actors]


def actor_names(fx) -> dict:
    return {actor.actor_id: actor.name for actor in fx.world.actors}


def actor_cta(name: str) -> str:
    """The plan's fixed per-actor call to action (the scripted actor
    models key their single rule on it)."""
    return f"What does {name} do next?"


def make_team_problem(fx, *, actions=None, permission=False,
                      problem_id=PROBLEM_ID) -> DecisionProblem:
    """The fixture-2 team decision as a ``DecisionProblem``: which of
    Riley's approaches most increases the chance the declared decision
    rule is satisfied this week.  ``actions`` defaults to the frozen
    fixture's three candidate actions, verbatim; the decision owner is
    named by the human-facing actor NAME and resolved by the route."""
    if actions is None:
        actions = [candidate.action for candidate in fx.candidates]
    return DecisionProblem.from_dict({
        "contract_type": DecisionProblem.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "problem_id": problem_id,
        "decision_owner": "Riley",
        "desired_outcome": PROBLEM_DESIRED_OUTCOME,
        "success_criteria": PROBLEM_SUCCESS_CRITERIA,
        "constraints": [],
        "time_horizon": {"start": "2026-08-04T09:00:00Z",
                         "cutoff": "2026-08-11T18:00:00Z"},
        "relevant_context": PROBLEM_CONTEXT,
        "candidate_interventions": list(actions),
        "candidate_generation_permission": permission,
    })


# ---------------------------------------------------------------------------
# Attribution-anchored metric predicates and the status rule
# ---------------------------------------------------------------------------

def anchored_matcher(*needles):
    """A matcher demanding a well-formed resolved actor turn (the anchor
    plus the row's own leading attribution) with every content needle in
    the attributed content -- narration rows (premise / pre-start
    records) never carry the anchor, so they can never satisfy it, and
    needles inside the framing or inside a proxy ``Name:`` segment of
    the row never count as another actor's content."""
    return actor_turn_matcher(*needles)


def commit_matcher():
    return anchored_matcher(COMMIT_MARKER)


def veto_matcher():
    """Authority-keyed: only the authority holder's OWN turn -- the
    row's leading attribution names Sam AND Sam's attributed content
    opens with the utterance -- counts as the veto."""
    return attributed_turn_matcher(AUTHORITY_NAME, VETO_UTTERANCE)


def team_predicates() -> dict:
    """Fixture-2 metric predicates (see the module docstring).

    ``decision_rule_satisfied`` implements the fixture's DECLARED rule
    from the measured trace: at least three explicit commitments and no
    authority-holder veto.  Its citations are the counted commitment
    rows, any veto row, and always the whole-trace scan bound (the rule
    reads the complete committed stream)."""
    commits = commit_matcher()
    vetoes = veto_matcher()

    def decision_rule(event_trace, result_dict):
        del result_dict  # the rule reads the committed trace alone
        commit_rows = matching_indices(event_trace, commits)
        veto_rows = matching_indices(event_trace, vetoes)
        value = len(commit_rows) >= 3 and not veto_rows
        citations = (list(commit_rows) + list(veto_rows)
                     + [WHOLE_TRACE_CITATION])
        return value, citations

    return {
        "decision_rule_satisfied": decision_rule,
        "explicit_support_commitments": count_metric(commits),
        "explicit_opposition": count_metric(anchored_matcher(OPPOSE_MARKER)),
        "veto_exercised": exists_metric(vetoes),
        "pilot_accepted": exists_metric(attributed_turn_matcher(
            AUTHORITY_NAME, PILOT_ACCEPT_UTTERANCE)),
        "final_decision_recorded": exists_metric(
            anchored_matcher(FINAL_MARKER)),
    }


def team_status_rule(metric_values, default_status):
    """Test-supplied terminal-status verdict, read from measured metrics
    only (R3: the verdict belongs to the external evaluator).  Maps the
    fixture's expectations: declared rule satisfied -> success; an
    exercised veto or explicit opposition -> failure; otherwise keep the
    runner's default (an unresolved meeting stays 'cutoff' -- never a
    fabricated outcome)."""
    del default_status
    if metric_values["decision_rule_satisfied"].value:
        return "success"
    if metric_values["veto_exercised"].value \
            or metric_values["explicit_opposition"].value > 0:
        return "failure"
    return None


# ---------------------------------------------------------------------------
# Scripted model factories
# ---------------------------------------------------------------------------

def _build_models(fx, table, visibility, candidate, capture, branch_seed):
    """Strict scripted models for one branch: one CTA-keyed rule per
    actor (``None`` first turn echoes the inserted candidate action) and
    the GM's visibility rules ahead of the full-roster fallback."""
    names = actor_names(fx)
    models = {}
    for actor_id in actor_order(fx):
        responses = list(table[actor_id])
        if responses and responses[0] is None:
            responses[0] = candidate.action
        models[actor_id] = StrictScriptedModel(
            [(actor_cta(names[actor_id]), responses)])
    gm_rules = [(needle, [", ".join(participants)])
                for needle, participants in visibility]
    gm_rules.append(aware_rule(list(names.values())))
    gm = StrictScriptedModel(gm_rules)
    if capture is not None:
        capture[candidate.candidate_id] = {
            "actors": models, "gm": gm, "seed": branch_seed}
    return models, gm


def team_fixture_factory(fx, capture=None):
    """Per-branch scripted models implementing the slice turn tables,
    keyed on WHICH fixture candidate action the branch carries (the
    route transports the fixture actions verbatim)."""
    by_action = {candidate.action: candidate.candidate_id
                 for candidate in fx.candidates}

    def factory(candidate, branch_seed):
        fixture_id = by_action[candidate.action]
        return _build_models(fx, TEAM_TURNS[fixture_id],
                             TEAM_VISIBILITY[fixture_id], candidate,
                             capture, branch_seed)

    return factory


def probe_factory(fx, tables, visibility=None, capture=None):
    """Scripted models for synthetic probe candidates, keyed by
    candidate id.  ``tables[candidate_id]`` maps actor id to turns
    (``None`` echoes the action); ``visibility[candidate_id]`` optional
    private-event rules, default full broadcast."""
    def factory(candidate, branch_seed):
        candidate_id = candidate.candidate_id
        rules = (visibility or {}).get(candidate_id, [])
        return _build_models(fx, tables[candidate_id], rules, candidate,
                             capture, branch_seed)

    return factory


# ---------------------------------------------------------------------------
# Slice and probe runners
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TeamSliceOutcome:
    """Everything one full team slice pass produced (route -> manager ->
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


def run_team_slice(*, seed=SEED, max_steps=TEAM_MAX_STEPS,
                   provenance_label="deterministic") -> TeamSliceOutcome:
    """One complete slice pass on a FRESH fixture load: frozen fixture 2
    -> DecisionProblem -> route (``prepare_decision_inputs``) ->
    ``run_candidates_detailed`` -> cited outcome evaluation -> the
    recommendation report and the causal trace report."""
    fx = load_fixture_two()
    problem = make_team_problem(fx)
    inputs = prepare_decision_inputs(
        problem, fx.world, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)
    capture: dict = {}
    run = run_candidates_detailed(
        inputs.world, inputs.candidates,
        model_factory=team_fixture_factory(fx, capture=capture),
        seed=seed, max_steps=max_steps,
        evaluator_spec=inputs.evaluator_spec, registry=inputs.registry,
        model_config={"kind": "phase10_team_slice"})
    evaluated = evaluate_branches(
        run.results, team_predicates(),
        evaluator_spec=inputs.evaluator_spec,
        status_rule=team_status_rule, registry=inputs.registry)
    report = build_recommendation_report(
        problem, inputs.candidates, run, evaluated,
        inputs.evaluator_spec, provenance_label=provenance_label,
        registry=inputs.registry)
    trace = build_trace_report(run, evaluated)
    recommendation = RecommendationResult.from_dict(
        report["recommendation"])
    return TeamSliceOutcome(fx=fx, problem=problem, inputs=inputs,
                            run=run, evaluated=tuple(evaluated),
                            recommendation=recommendation, report=report,
                            trace=trace, capture=capture)


def run_probe(fx, candidates, tables, *, visibility=None,
              max_steps=ROUND_LENGTH, world=None, registry=None,
              seed=SEED):
    """Run synthetic probe candidates on the fixture world (or a
    test-owned world variant) through the full manager + evaluation
    path; returns ``(run, evaluated, capture)``."""
    capture: dict = {}
    run = run_candidates_detailed(
        world if world is not None else fx.world,
        candidates,
        model_factory=probe_factory(fx, tables, visibility=visibility,
                                    capture=capture),
        seed=seed, max_steps=max_steps,
        evaluator_spec=fx.evaluator_spec,
        registry=registry if registry is not None else fx.registry)
    evaluated = evaluate_branches(
        run.results, team_predicates(),
        evaluator_spec=fx.evaluator_spec,
        status_rule=team_status_rule,
        registry=registry if registry is not None else fx.registry)
    return run, evaluated, capture


def world_variant(fx, world_id: str, starting_events):
    """A test-owned world built strictly through the frozen contract
    gate: the fixture world with a different id and the given pre-start
    events.  The frozen fixture file is untouched."""
    data = fx.world.to_dict()
    data["world_id"] = world_id
    data["starting_events"] = list(starting_events)
    world = CompiledDecisionWorld.from_dict(data)
    registry = ContractRegistry()
    registry.register_world(world)
    return world, registry


# ---------------------------------------------------------------------------
# Assertion-side conveniences
# ---------------------------------------------------------------------------

def branch_results_by_fixture_id(outcome: TeamSliceOutcome) -> dict:
    """Evaluated results keyed by FIXTURE candidate id (via the verbatim
    action-text bijection)."""
    mapping = route_action_map(outcome.fx, outcome.inputs)
    return {mapping[result.candidate_id]: result
            for result in outcome.evaluated}


def route_ids_by_fixture_id(outcome: TeamSliceOutcome) -> dict:
    mapping = route_action_map(outcome.fx, outcome.inputs)
    return {fixture_id: route_id
            for route_id, fixture_id in mapping.items()}


def private_context_by_actor(fx) -> dict:
    """Each actor's fixture private context (stripped, the planner's
    carriage form) -- the five distinct private-information canaries."""
    return {actor.actor_id: actor.private_context.strip()
            for actor in fx.world.actors}


def prompts_of(capture_entry: dict, actor_id: str) -> str:
    """Every prompt one branch's scripted actor model received, joined
    for containment assertions."""
    return all_prompt_text(capture_entry["actors"][actor_id])


def gm_prompts_of(capture_entry: dict) -> str:
    return all_prompt_text(capture_entry["gm"])


def turn_flags(fixture_id: str) -> dict:
    """Behavior flags realized by the scripted turn tables, per actor:
    ``commit`` (a turn carries the commitment marker) and ``veto`` (a
    turn carries the veto utterance).  A test cross-checks these against
    the frozen fixture's ``deterministic_script`` scaffolding flags."""
    flags = {}
    for actor_id, turns in TEAM_TURNS[fixture_id].items():
        joined = " ".join(turn for turn in turns if turn is not None)
        flags[actor_id] = {
            "commit": COMMIT_MARKER in joined,
            "veto": VETO_UTTERANCE in joined,
        }
    return flags
