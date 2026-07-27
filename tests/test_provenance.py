"""Epistemic provenance: nothing factual enters a compiled world unlabelled.

Inheritance exists so the model does not have to restate the same citation on
every nested rate and duration -- which in practice never converged. What is
enforced is unchanged and tested here: a basis is always resolved, anything
claimed verified or inferred cites real evidence, and an uncertain quantity
never becomes a concrete number.
"""
import copy

import pytest

from compiler.errors import InsufficientEvidence, LoweringGap
from compiler.lower import lower
from compiler.schema import EPISTEMIC_STATUS, check_provenance, provenance_of
from tests.fixtures_semantic import MESSAGE_CASE, QUANTITY_CASE

EV = {"claims": [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}, {"id": "e4"},
                 {"id": "e5"}, {"id": "e7"}]}


def doc():
    return {
        "resolution": {"provenance": {"basis": "scenario_given"}},
        "participants": [
            {"name": "A",
             "provenance": {"basis": "verified", "evidence_ids": ["e1"]},
             "attention": [{"route": "r", "status": "inferred",
                            "check_interval_minutes": 30}]}],
        "starting_state": [], "information": [],
        "communication_routes": [
            {"name": "r",
             "provenance": {"basis": "verified", "evidence_ids": ["e2"]},
             "delivery_delay": {"status": "verified", "seconds": 30}}],
        "scheduled_events": [], "processes": [], "action_affordances": [],
    }


def test_scenario_given_and_uncertain_need_no_citation():
    for basis in ("uncertain", "scenario_given"):
        d = doc()
        d["participants"][0]["provenance"] = {"basis": basis}
        # the nested entry must follow suit: there is no evidence to inherit
        d["participants"][0]["attention"][0]["status"] = basis
        check_provenance(d, EV)


def test_inferred_nested_object_cannot_lean_on_an_uncertain_parent():
    """Inheritance passes evidence down; it never manufactures it. A nested
    claim of 'inferred' under a parent that cites nothing must cite its own
    evidence or admit it is uncertain too."""
    d = doc()
    d["participants"][0]["provenance"] = {"basis": "uncertain"}
    d["participants"][0]["attention"][0]["status"] = "inferred"
    with pytest.raises(InsufficientEvidence, match="cites no evidence_ids"):
        check_provenance(d, EV)


def test_nested_object_inherits_the_parents_evidence():
    """A rate or delivery delay states its own status but may rely on the
    evidence cited by the process or route it belongs to."""
    check_provenance(doc(), EV)


def test_nested_object_may_override_with_its_own_basis():
    d = doc()
    d["participants"][0]["attention"][0]["provenance"] = {
        "basis": "inferred", "evidence_ids": ["e3"]}
    check_provenance(d, EV)


def test_unlabelled_top_level_object_is_refused():
    d = doc()
    d["participants"][0].pop("provenance")
    with pytest.raises(InsufficientEvidence, match="no provenance"):
        check_provenance(d, EV)


def test_verified_without_citation_is_refused():
    d = doc()
    d["participants"][0]["provenance"] = {"basis": "verified"}
    with pytest.raises(InsufficientEvidence, match="cites no evidence_ids"):
        check_provenance(d, EV)


def test_inferred_without_citation_is_refused():
    d = doc()
    d["participants"][0]["provenance"] = {"basis": "inferred"}
    with pytest.raises(InsufficientEvidence, match="cites no evidence_ids"):
        check_provenance(d, EV)


def test_citing_evidence_that_does_not_exist_is_refused():
    d = doc()
    d["participants"][0]["provenance"]["evidence_ids"] = ["e404"]
    with pytest.raises(InsufficientEvidence, match="do not exist"):
        check_provenance(d, EV)


def test_unknown_basis_is_refused():
    d = doc()
    d["participants"][0]["provenance"] = {"basis": "probably", "evidence_ids": ["e1"]}
    with pytest.raises(InsufficientEvidence, match="must be one of"):
        check_provenance(d, EV)


def test_all_violations_are_reported_together():
    d = doc()
    d["participants"][0]["provenance"] = {"basis": "verified"}
    d["communication_routes"][0]["provenance"] = {"basis": "inferred"}
    with pytest.raises(InsufficientEvidence) as ei:
        check_provenance(d, EV)
    defects = ei.value.detail["defects"]
    assert len(defects) >= 2
    joined = " ".join(defects)
    assert "participants['A']" in joined and "communication_routes['r']" in joined
    assert ei.value.detail["repairable"] is True


def test_the_four_bases_are_exactly_as_specified():
    assert EPISTEMIC_STATUS == ("verified", "inferred", "scenario_given",
                                "uncertain")


def test_status_field_counts_as_a_stated_basis():
    assert provenance_of({"status": "inferred", "evidence_ids": ["e1"]}) \
        == ("inferred", ["e1"])
    assert provenance_of({}) == (None, [])


# ---------------------------------------------------------------------------
# provenance survives into the runtime, and uncertainty never becomes a number
# ---------------------------------------------------------------------------

def test_real_fixtures_satisfy_provenance():
    check_provenance(copy.deepcopy(MESSAGE_CASE), {"claims": [
        {"id": i} for i in ("e1", "e2", "e3", "e4", "e5")]})


def test_labels_reach_the_runtime():
    c = lower(copy.deepcopy(MESSAGE_CASE))
    ch = c.world.channels["work_email"]
    assert ch.latency.basis in ("verified", "inferred", "scenario_given")
    defn = c.world.action_defs["send_an_on_record_comment"]
    assert defn["duration"]["basis"] in ("verified", "inferred", "scenario_given")
    for rule in c.world.actors["priya_raman"].attention.values():
        assert rule.basis in ("verified", "inferred", "scenario_given")


def test_uncertain_never_becomes_a_concrete_number():
    for field, case, msg in (
            ("duration", MESSAGE_CASE, "completion_condition"),
            ("rate", QUANTITY_CASE, "uncertain rate")):
        d = copy.deepcopy(case)
        if field == "duration":
            d["action_affordances"][0]["duration"]["status"] = "uncertain"
        else:
            d["processes"][0]["rate"]["status"] = "uncertain"
        with pytest.raises(LoweringGap, match=msg):
            lower(d)
