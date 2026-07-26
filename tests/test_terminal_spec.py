"""The declarative terminal is a runtime capability in its own right.

Two things are proven here, independently of the compiler:
1. each observation kind reads the world mechanically and reports the ledger
   records that produced its reading;
2. declarative terminals reproduce the hand-authored Python terminals'
   answers exactly, on all three existing worlds.
"""
import pytest
from datetime import timedelta

from sworldmodel import Engine, at_local
from sworldmodel.terminal import (Observation, TerminalSpec, TerminalSpecError)
from worlds import committee_world, email_world, factory_world


# ---------------------------------------------------------------------------
# structural validation
# ---------------------------------------------------------------------------

def test_unknown_observation_kind_refused():
    with pytest.raises(TerminalSpecError, match="unknown observation kind"):
        Observation("vibes", {})


def test_missing_parameters_refused():
    with pytest.raises(TerminalSpecError, match="requires parameter"):
        Observation("fact_equals", {"key": "x"})
    with pytest.raises(TerminalSpecError, match="requires parameter"):
        Observation("resource_at_least", {"holder": "a", "name": "b"})


def test_tally_rule_validation():
    with pytest.raises(TerminalSpecError, match="tally rule"):
        Observation("tally_facts", {"key_prefix": "v:", "rule": "guess"})
    with pytest.raises(TerminalSpecError, match="count_value"):
        Observation("tally_facts", {"key_prefix": "v:", "rule": "count_value"})


def test_terminal_shape_validation():
    t = at_local(2026, 1, 1, tz="UTC")
    with pytest.raises(TerminalSpecError, match="question_type"):
        TerminalSpec("q", t, "vibes")
    with pytest.raises(TerminalSpecError, match="at least one condition"):
        TerminalSpec("q", t, "boolean")
    with pytest.raises(TerminalSpecError, match="needs a measure"):
        TerminalSpec("q", t, "quantity")


def test_round_trips_through_json():
    spec = TerminalSpec(
        "q", at_local(2026, 1, 1, tz="UTC"), "boolean",
        conditions=(Observation("fact_equals", {"key": "k", "value": 1}),))
    assert TerminalSpec.from_dict(spec.to_dict()).to_dict() == spec.to_dict()


# ---------------------------------------------------------------------------
# each observation reads real state and cites real producers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def committee_run():
    w, minds, t = committee_world.build()
    Engine(w, minds, t).run()
    return w


@pytest.fixture(scope="module")
def factory_run():
    w, minds, t = factory_world.build()
    Engine(w, minds, t).run()
    return w


def test_fact_observations(committee_run):
    w = committee_run
    r = Observation("fact_equals", {"key": "vote:eli", "value": "cut"}).read(w)
    assert r["satisfied"] and r["value"] == "cut" and r["producers"]
    r = Observation("fact_equals", {"key": "vote:eli", "value": "hold"}).read(w)
    assert not r["satisfied"]
    r = Observation("fact_exists", {"key": "motion"}).read(w)
    assert r["satisfied"]
    r = Observation("fact_exists", {"key": "nope"}).read(w)
    assert not r["satisfied"] and r["producers"] == []


def test_tally_observation(committee_run):
    w = committee_run
    r = Observation("tally_facts", {"key_prefix": "vote:", "rule": "majority",
                                    "expected_count": 3}).read(w)
    assert r["satisfied"] and r["value"] == "hold" and len(r["producers"]) == 3
    r = Observation("tally_facts", {"key_prefix": "vote:", "rule": "count_value",
                                    "value": "cut"}).read(w)
    assert r["value"] == 1
    r = Observation("tally_facts", {"key_prefix": "vote:", "rule": "count_all"}).read(w)
    assert r["value"] == 3
    # an incomplete tally is not satisfied
    r = Observation("tally_facts", {"key_prefix": "vote:", "rule": "majority",
                                    "expected_count": 5}).read(w)
    assert not r["satisfied"]


def test_tally_detects_a_tie():
    from sworldmodel import World, at_local as al
    w = World(al(2026, 1, 1, tz="UTC"))
    w.apply("fact.set", {"key": "v:a", "value": "yes"}, None)
    w.apply("fact.set", {"key": "v:b", "value": "no"}, None)
    r = Observation("tally_facts", {"key_prefix": "v:", "rule": "majority",
                                    "expected_count": 2}).read(w)
    assert r["value"] == "tie"


def test_resource_observations(factory_run):
    w = factory_run
    r = Observation("resource_measure", {"holder": "acme", "name": "widgets"}).read(w)
    assert r["value"] == 500.0 and r["producers"]
    r = Observation("resource_at_least", {"holder": "acme", "name": "widgets",
                                          "level": 400}).read(w)
    assert r["satisfied"]
    r = Observation("resource_at_least", {"holder": "acme", "name": "widgets",
                                          "level": 900}).read(w)
    assert not r["satisfied"]
    # production accruals are producers of the factory's own stock
    r = Observation("resource_measure", {"holder": "factory", "name": "widgets"}).read(w)
    assert len(r["producers"]) > 5


def test_belief_and_action_observations(factory_run):
    w = factory_run
    r = Observation("belief_topic_exists", {"actor": "mo", "topic": "order:o1"}).read(w)
    assert r["satisfied"] and r["producers"]
    r = Observation("belief_topic_exists", {"actor": "mo", "topic": "nope"}).read(w)
    assert not r["satisfied"]
    r = Observation("action_completed", {"verb": "fulfill_order"}).read(w)
    assert r["satisfied"] and r["producers"]
    r = Observation("action_completed", {"verb": "fulfill_order",
                                         "actor": "nobody"}).read(w)
    assert not r["satisfied"]


def test_info_noticed_observation_uses_tags():
    # tagging is how a compiled world refers to information without inventing ids
    w, minds, t = factory_world.build()
    Engine(w, minds, t).run()
    r = Observation("info_noticed_by", {"actor": "mo", "tag": "nothing"}).read(w)
    assert not r["satisfied"]
    # the delivery confirmation carries type=delivery; retag one to prove the read
    info = next(i for i in w.infos.values() if i["data"].get("type") == "delivery")
    info["data"]["tag"] = "delivery_confirmation"
    r = Observation("info_noticed_by", {"actor": "mo",
                                        "tag": "delivery_confirmation"}).read(w)
    assert r["satisfied"] and r["producers"]
    # acme_contact never noticed it -- locality holds through the terminal too
    r = Observation("info_noticed_by", {"actor": "acme_contact",
                                        "tag": "delivery_confirmation"}).read(w)
    assert not r["satisfied"]


# ---------------------------------------------------------------------------
# equivalence with the hand-authored Python terminals
# ---------------------------------------------------------------------------

def test_boolean_spec_matches_handwritten_email_terminal():
    spec = TerminalSpec(
        question=email_world.QUESTION, cutoff=email_world.CUTOFF,
        question_type="boolean",
        conditions=(Observation("belief_topic_exists",
                                {"actor": "alice", "topic": "q2_confirmed"},
                                "Alice holds Bob's confirmation"),))
    w, minds, _ = email_world.build()
    out = Engine(w, minds, spec.to_terminal()).run()
    assert out.status == "resolved" and out.answer["answer"] == "yes"
    assert out.answer["computed_from"]

    # and the negative branch, mechanically
    w2, minds2, _ = email_world.build(reply=False)
    out2 = Engine(w2, minds2, spec.to_terminal()).run()
    assert out2.status == "cutoff" and out2.answer["answer"] == "no"


def test_choice_spec_matches_handwritten_committee_terminal():
    spec = TerminalSpec(
        question=committee_world.QUESTION, cutoff=committee_world.CUTOFF,
        question_type="choice",
        measure=Observation("tally_facts",
                            {"key_prefix": "vote:", "rule": "majority",
                             "expected_count": 3},
                            "majority of cast votes"))
    w, minds, _ = committee_world.build()
    out = Engine(w, minds, spec.to_terminal()).run()
    assert out.answer["answer"] == "hold"
    assert len(out.answer["computed_from"]) == 3

    # the informed counterfactual flips it, through the same spec
    w2, minds2, _ = committee_world.build(fran_traveling=False)
    out2 = Engine(w2, minds2, spec.to_terminal()).run()
    assert out2.answer["answer"] == "cut"


def test_quantity_spec_matches_handwritten_factory_terminal():
    spec = TerminalSpec(
        question=factory_world.QUESTION, cutoff=factory_world.CUTOFF,
        question_type="quantity",
        measure=Observation("resource_measure",
                            {"holder": "acme", "name": "widgets"},
                            "widgets received by Acme"))
    w, minds, _ = factory_world.build()
    out = Engine(w, minds, spec.to_terminal()).run()
    assert out.status == "cutoff" and out.answer["answer"] == 500.0
    assert out.answer["computed_from"]


def test_quantity_terminal_does_not_resolve_early():
    # "how many by X" is only answerable at X, never sooner
    spec = TerminalSpec("q", factory_world.CUTOFF, "quantity",
                        measure=Observation("resource_measure",
                                            {"holder": "acme", "name": "widgets"}))
    w, minds, _ = factory_world.build()
    out = Engine(w, minds, spec.to_terminal()).run()
    assert out.status == "cutoff"


def test_boolean_terminal_requires_all_conditions():
    spec = TerminalSpec(
        "q", email_world.CUTOFF, "boolean",
        conditions=(Observation("belief_topic_exists",
                                {"actor": "alice", "topic": "q2_confirmed"}),
                    Observation("fact_equals", {"key": "never", "value": 1})))
    w, minds, _ = email_world.build()
    out = Engine(w, minds, spec.to_terminal()).run()
    assert out.status == "cutoff" and out.answer["answer"] == "no"
