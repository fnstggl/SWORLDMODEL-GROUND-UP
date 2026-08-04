"""The observer seam: a name the game master invents is never DROPPED.

Defect closed here (2026-08-04 under-the-hood validation, defect D1).
Upstream ``EventResolution`` asks the game-master model, in free text,
"Which entities are aware of the event?" and hands each comma-separated
fragment to ``ObservationQueue.add``.  ``ObservationQueue.add`` creates a
queue key for whatever string it is handed, so a name that does not match
a roster entity lands in a queue nobody ever reads: the event is dropped
with no error, no log line, and no record anywhere.  In the live runs
this killed the ONE branch whose sender actually enacted its candidate --
the game master answered with a mention-sigil form of the recipient's
name and the enacted event went nowhere.

The upstream behaviour itself is reproduced here as a pinned fact (no
patch to ``/home/user/concordia``); the fix lives at OUR seam, the
builder's ``RosterValidatedMakeObservation``, and is proven in three
layers: the resolver unit, the enqueue behaviour, and one full branch run
whose game master names an unresolvable observer.
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

from concordia.components.game_master import make_observation as upstream_obs

from baseline_helpers import StrictScriptedModel
from cf_helpers import (MAX_STEPS, RECIPIENT_CTA, RECIPIENT_SILENT_TURN,
                        SEED, SENDER_CTA, fixture_status_rule,
                        load_fixture_one, make_candidate)
from individual_helpers import anchored_predicates
from sworldmodel.backends.concordia_local.builder import (
    OBSERVER_BROADCAST_KEYWORD, RosterValidatedMakeObservation,
    normalize_observer_name)
from sworldmodel.counterfactuals import run_candidates_detailed
from sworldmodel.outcomes import evaluate_branches

ROSTER = ("Alex", "Morgan")

#: the GM answer shape the live run actually produced: one resolvable
#: name and one mention-sigil form that resolves to nobody
AWARE_QUESTION_NEEDLE = "Which entities are aware"


class _NullModel:
    """A model object the seam never calls (the queue path is pure code);
    present because upstream's constructor requires one."""

    def sample_text(self, prompt, **kwargs):  # pragma: no cover - unused
        raise AssertionError("the observer seam must not call the model")

    def sample_choice(self, prompt, responses, **kwargs):  # pragma: no cover
        raise AssertionError("the observer seam must not call the model")


def _seam(roster=ROSTER):
    return RosterValidatedMakeObservation(
        model=_NullModel(), player_names=list(roster),
        allow_llm_fallback=False, roster_names=tuple(roster))


# ---------------------------------------------------------------------------
# The upstream behaviour this seam exists to close (pinned fact, no patch)
# ---------------------------------------------------------------------------


def test_upstream_queue_silently_drops_a_nonmatching_name():
    """The pinned upstream fact, reproduced directly: adding an event
    under a name that is not a roster entity succeeds, returns nothing,
    and the event is unreachable from the real entity's queue."""
    queue = upstream_obs.ObservationQueue()
    queue.add("@Morgan", "the offer was sent", list(ROSTER))
    # No error was raised, and Morgan's own queue is empty.
    assert queue.get_and_clear("Morgan") == []
    # The event is sitting under a phantom key nobody reads.
    assert queue.get_all()["@Morgan"] == ["the offer was sent"]


# ---------------------------------------------------------------------------
# Unit: resolution
# ---------------------------------------------------------------------------


def test_normalization_is_conservative():
    assert normalize_observer_name("  @Morgan.  ") == "Morgan"
    assert normalize_observer_name("'Morgan'") == "Morgan"
    assert normalize_observer_name("**Morgan**") == "Morgan"
    # Interior bytes are never touched: nothing is abbreviated or joined.
    assert normalize_observer_name("Morgan  Ada") == "Morgan  Ada"
    assert normalize_observer_name(None) == ""


def test_resolver_resolves_only_what_it_can_justify():
    seam = _seam()
    assert seam.resolve_observer_name("Morgan") == ("Morgan", "exact")
    assert seam.resolve_observer_name(" @Morgan, ") \
        == ("Morgan", "exact_after_normalization")
    assert seam.resolve_observer_name("morgan") == ("Morgan", "case_folded")
    assert seam.resolve_observer_name("all") \
        == (OBSERVER_BROADCAST_KEYWORD, "broadcast_keyword")
    # NOT resolved: no prefix, nickname, or edit-distance guessing.
    for unknown in ("Morg", "Morgan Reyes", "the recipient", "Quorlan", ""):
        resolved, reason = seam.resolve_observer_name(unknown)
        assert resolved is None, unknown
        assert reason in ("no_roster_match", "blank_after_normalization")


def test_ambiguous_folded_match_resolves_to_nobody():
    """Two roster names that differ only by case fold to one key; the
    seam refuses rather than pick one."""
    seam = _seam(("Morgan", "MORGAN "))
    assert seam.resolve_observer_name("morgan") \
        == (None, "ambiguous_roster_match")


# ---------------------------------------------------------------------------
# Unit: enqueue behaviour
# ---------------------------------------------------------------------------


def test_resolved_names_route_exactly_as_upstream_routes_them():
    """Every resolvable spelling lands in the REAL entity's queue, in
    order -- read through the same component-state API the engine reads."""
    seam = _seam()
    seam.add_to_queue("Morgan", "one")
    seam.add_to_queue(" @Morgan. ", "two")
    seam.add_to_queue("morgan", "three")
    queue = seam.get_state()["queue"]
    assert queue == {"Morgan": ["one", "two", "three"]}
    assert seam.unresolved_observers == []


def test_broadcast_keyword_keeps_its_upstream_meaning():
    seam = _seam()
    seam.add_to_queue("all", "everyone hears this")
    state = seam.get_state()["queue"]
    assert state["Alex"] == ["everyone hears this"]
    assert state["Morgan"] == ["everyone hears this"]
    assert seam.unresolved_observers == []


def test_unresolvable_name_is_recorded_and_not_queued():
    """The exact live-run shape: the GM names one real observer and one
    mention-sigil string that resolves to nobody."""
    seam = _seam()
    seam.add_to_queue("Morgan", "the offer was sent")
    seam.add_to_queue("@PeterThiel", "the offer was sent")
    seam.add_to_queue("the whole room", "the offer was sent")

    queue = seam.get_state()["queue"]
    assert queue["Morgan"] == ["the offer was sent"]
    # No phantom keys were created for the unresolvable names.
    assert set(queue) == {"Morgan"}

    records = seam.unresolved_observers
    assert [entry["observer_name"] for entry in records] \
        == ["@PeterThiel", "the whole room"]
    assert [entry["normalized"] for entry in records] \
        == ["PeterThiel", "the whole room"]
    assert all(entry["reason"] == "no_roster_match" for entry in records)
    assert all(entry["event_excerpt"] == "the offer was sent"
               for entry in records)


def test_records_survive_the_component_state_round_trip():
    """Checkpoint/resume carries the evidence: a restored branch does not
    forget the observers its pre-checkpoint half failed to resolve."""
    seam = _seam()
    seam.add_to_queue("@PeterThiel", "the offer was sent")
    state = seam.get_state()
    restored = _seam()
    restored.set_state(state)
    assert restored.unresolved_observers == seam.unresolved_observers
    assert restored.get_state() == state


# ---------------------------------------------------------------------------
# End to end: one branch whose game master names an unresolvable observer
# ---------------------------------------------------------------------------


def _run_branch_with_gm_answer(answer: str):
    fx = load_fixture_one()
    candidate = make_candidate("user_001",
                               "Send the note asking for a call.")

    def factory(candidate_in, branch_seed):
        del branch_seed
        sender = StrictScriptedModel(
            [(SENDER_CTA, [candidate_in.action, "Alex waits."])])
        recipient = StrictScriptedModel(
            [(RECIPIENT_CTA, [RECIPIENT_SILENT_TURN])])
        gm = StrictScriptedModel([(AWARE_QUESTION_NEEDLE, [answer])])
        return {"sender": sender, "recipient": recipient}, gm

    run = run_candidates_detailed(
        fx.world, [candidate], model_factory=factory, seed=SEED,
        max_steps=MAX_STEPS, evaluator_spec=fx.evaluator_spec,
        registry=fx.registry)
    evaluated = evaluate_branches(
        run.results, anchored_predicates(),
        evaluator_spec=fx.evaluator_spec,
        status_rule=fixture_status_rule, registry=fx.registry)
    return run, evaluated[0]


def test_a_resolvable_gm_answer_records_nothing():
    run, result = _run_branch_with_gm_answer("Alex, Morgan")
    assert list(result.infrastructure_errors) == []
    assert run.runner_records["user_001"]["unresolved_observers"] == []
    assert result.unresolved_observers == ()


def test_an_unresolvable_gm_answer_reaches_the_branch_result():
    """Upstream would have dropped '@Morgan' with no trace at all; the
    record must be reachable from the runner record AND the contract."""
    run, result = _run_branch_with_gm_answer("Alex, @PeterThiel")
    assert list(result.infrastructure_errors) == []

    runner_records = run.runner_records["user_001"]["unresolved_observers"]
    assert runner_records, "the runner record must carry the evidence"
    assert {entry["observer_name"] for entry in runner_records} \
        == {"@PeterThiel"}
    assert all(entry["reason"] == "no_roster_match"
               for entry in runner_records)

    # ... and it survives the contract gate on the BranchResult.
    assert result.unresolved_observers
    assert {entry["observer_name"]
            for entry in result.unresolved_observers} == {"@PeterThiel"}
    assert result.to_dict()["unresolved_observers"] \
        == [dict(entry) for entry in result.unresolved_observers]
