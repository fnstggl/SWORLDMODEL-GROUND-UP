"""Test-owned helpers for the Phase 6 counterfactual suite (engine env).

Import this module AFTER the per-module version/importorskip gates: it
imports ``baseline_helpers`` (tests/engine_baseline), which imports the
Concordia language-model interface available only in the pinned engine
environment (Python >= 3.12).

Scenario vocabulary lives HERE and in the frozen fixtures, never in
``sworldmodel/``: the scripted responses, the metric needles, and the
status rule below are the fixture's deterministic engineering-test
scaffolding (directive: "Use a scripted recipient only for the
engineering test"), keyed on which candidate text the recipient observes.
"""

from __future__ import annotations

import hashlib
import json

from concordia.language_model import language_model

from baseline_helpers import (REPO_ROOT, StrictScriptedModel,  # noqa: F401
                              all_prompt_text, aware_rule)
from sworldmodel.decision.contracts import (InterventionCandidate,
                                            SCHEMA_VERSION)
from sworldmodel.decision.fixture_loader import load_fixture_file
from sworldmodel.outcomes import exists_metric

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "best_action"
FIXTURE_ONE_PATH = FIXTURE_DIR / "individual_reply.yaml"
FIXTURE_HASHES_PATH = FIXTURE_DIR / "FIXTURES.sha256"

SEED = 20260803
#: one full turn per actor under the fixed acting order (sender first)
MAX_STEPS = 2

SENDER_CTA = "What does Alex do next?"
RECIPIENT_CTA = "What does Morgan do next?"
SENDER_IDLE_TURN = "Alex continues quietly with unrelated preparation."
#: the scripted "no reply by cutoff" recipient turn (must trip none of the
#: metric needles below)
RECIPIENT_SILENT_TURN = ("Morgan files the message away and continues her "
                        "scheduled work without responding.")


def load_fixture_one():
    """Load the frozen fixture through the strict Phase 3 loader (file
    untouched); returns a fresh LoadedFixture with its own registry."""
    return load_fixture_file(str(FIXTURE_ONE_PATH))


def file_sha256(path) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def recorded_fixture_hash(file_name: str) -> str:
    """The frozen sha256 recorded for one fixture file in
    FIXTURES.sha256 (the freeze record committed with the fixtures)."""
    for line in FIXTURE_HASHES_PATH.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == file_name:
            return parts[0]
    raise AssertionError(f"{file_name} is not recorded in FIXTURES.sha256")


def make_candidate(candidate_id: str, action: str, *,
                   owner: str = "sender",
                   timing: str = "2026-08-03T14:05:00Z"):
    """A synthetic user-supplied candidate for isolation tests (built
    through the strict contract gate, like every candidate)."""
    return InterventionCandidate.from_dict({
        "contract_type": InterventionCandidate.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "summary": " ".join(action.split())[:120],
        "action": action,
        "decision_owner": owner,
        "timing": timing,
        "constraints": [],
        "provenance": {"source": "user_supplied",
                       "generator_config_hash": ""},
    })


def branch_signature(result) -> str:
    """Byte-comparable deterministic signature of one BranchResult:
    trace + metrics + status (+ identity and terminal state).  Wall-clock
    runtime stats and token stats are excluded from BYTE comparison for
    the same reason the baseline suite excludes the raw log."""
    data = result.to_dict()
    keys = ("branch_id", "candidate_id", "world_id", "terminal_status",
            "terminal_world_state", "event_trace", "outcome_metrics",
            "infrastructure_errors")
    return json.dumps({key: data[key] for key in keys}, sort_keys=True)


class RaisingModel(language_model.LanguageModel):
    """A model that fails mid-branch: every call raises.  Used to prove
    branch-failure isolation (the error must surface in that branch's
    BranchResult and nowhere else)."""

    def __init__(self, marker: str):
        self.marker = marker
        self.prompts: list = []

    def sample_text(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        raise RuntimeError(self.marker)

    def sample_choice(self, prompt: str, responses, **kwargs):
        raise RuntimeError(self.marker)


def fixture_model_factory(fx, capture=None):
    """Per-branch scripted models implementing the frozen fixture's
    ``deterministic_script`` mapping.

    - The sender's scripted turn ECHOES the branch's candidate action
      (delivered to the sender as its t0 insertion observation), so the
      committed event carries the exact candidate text.
    - The recipient's rules are keyed on WHICH CANDIDATE TEXT the
      recipient observes: one rule per fixture candidate, needle = that
      candidate's verbatim action text, response = the fixture script's
      response for that candidate ('none' -> a silent non-reply turn).
      Only the branch's own candidate text ever appears in the branch,
      so exactly one rule can match; an unmatched prompt fails loudly
      (StrictScriptedModel).
    """
    script = fx.deterministic_script["recipient"]
    actions = {candidate.candidate_id: candidate.action
               for candidate in fx.candidates}

    def factory(candidate, branch_seed):
        recipient_rules = []
        for candidate_id, action in actions.items():
            response = script[candidate_id]["response"].strip()
            text = RECIPIENT_SILENT_TURN if response == "none" else response
            recipient_rules.append((action, [text]))
        sender = StrictScriptedModel(
            [(SENDER_CTA, [candidate.action, SENDER_IDLE_TURN])])
        recipient = StrictScriptedModel(recipient_rules)
        gm = StrictScriptedModel([aware_rule(["Alex", "Morgan"])])
        if capture is not None:
            capture[candidate.candidate_id] = {
                "sender": sender, "recipient": recipient, "gm": gm,
                "seed": branch_seed}
        return {"sender": sender, "recipient": recipient}, gm

    return factory


def simple_model_factory(response_map, capture=None, raising=None):
    """Scripted models for synthetic candidates.

    ``response_map`` maps candidate_id -> (needle, recipient_response);
    the recipient rule keys on the needle (a distinctive substring of
    that candidate's action text).  ``raising`` names candidate_ids whose
    RECIPIENT model raises mid-branch (failure-isolation tests).
    """
    raising = frozenset(raising or ())

    def factory(candidate, branch_seed):
        candidate_id = candidate.candidate_id
        sender = StrictScriptedModel(
            [(SENDER_CTA, [candidate.action, SENDER_IDLE_TURN])])
        if candidate_id in raising:
            recipient = RaisingModel(
                f"INJECTED_BRANCH_FAILURE_{candidate_id}")
        else:
            rules = [(needle, [response])
                     for needle, response in response_map.values()]
            recipient = StrictScriptedModel(rules)
        gm = StrictScriptedModel([aware_rule(["Alex", "Morgan"])])
        if capture is not None:
            capture[candidate_id] = {
                "sender": sender, "recipient": recipient, "gm": gm,
                "seed": branch_seed}
        return {"sender": sender, "recipient": recipient}, gm

    return factory


#: the upstream sequential engine wraps every RESOLVED ACTOR TURN in this
#: framing before commit; premise/pre-start rows never carry it (same
#: anchor as tests/engine_individual/individual_helpers.py -- replicated
#: because the engine suites are deliberately self-contained)
_ACTOR_TURN_ANCHOR = "Putative event to resolve:"

#: sentence punctuation/quotes never appear inside a real attribution
#: name; finding one means the head is not a well-formed turn stamp
#: (fail closed: such a row matches no metric)
_NAME_BREAK_CHARS = ".!?\"\n"


def _leading_attribution(description):
    """``(name, content)`` from the row's OWN leading attribution, else
    ``None``.  Mirrors individual_helpers.leading_attribution: the text
    between the anchor and the FIRST ``:`` or `` --`` separator is the
    active player's name; a malformed head refuses rather than guesses."""
    index = description.find(_ACTOR_TURN_ANCHOR)
    if index < 0:
        return None
    tail = description[index + len(_ACTOR_TURN_ANCHOR):].lstrip(" \t")
    cuts = [cut for cut in (tail.find(":"), tail.find(" --")) if cut >= 0]
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


def _attributed(actor, opening, *needles):
    """Matcher counting ONLY ``actor``'s own resolved turn: the row's
    leading attribution must name the actor and the attributed content
    must START with ``opening`` (review F1: substring co-occurrence
    anywhere in a row -- e.g. a proxy ``Name: ...`` segment embedded in
    ANOTHER actor's turn -- must never match)."""

    def matcher(description: str) -> bool:
        parsed = _leading_attribution(description)
        if parsed is None:
            return False
        name, content = parsed
        if name != actor or not content.startswith(opening):
            return False
        return all(needle in content for needle in needles)

    return matcher


def fixture_predicates():
    """Test-supplied metric predicates reading ONLY the event trace.

    Each metric binds to the RECIPIENT'S OWN committed turn via the
    row's leading attribution (review F1 closed the co-occurrence gap:
    a reply written by anyone else no longer satisfies the metric)."""
    return {
        "recipient_reply_sent": exists_metric(
            _attributed("Morgan", "Reply")),
        "meeting_scheduled": exists_metric(
            _attributed("Morgan", "Reply",
                        "agreeing to a fifteen-minute conversation")),
        "explicit_decline": exists_metric(
            _attributed("Morgan", "Reply declining")),
    }


def fixture_status_rule(metric_values, default_status):
    """Test-supplied terminal-status verdict, read from measured metrics
    only (R3: the verdict belongs to the external evaluator).  Maps the
    fixture's expectations: explicit decline -> failure; reply plus
    scheduled follow-up -> success; otherwise keep the runner's default
    (no reply by cutoff -> 'cutoff')."""
    del default_status
    if metric_values["explicit_decline"].value:
        return "failure"
    if metric_values["recipient_reply_sent"].value \
            and metric_values["meeting_scheduled"].value:
        return "success"
    return None
