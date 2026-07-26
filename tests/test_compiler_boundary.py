"""The compiler boundary, tested without model calls.

Two things must hold no matter what a model returns:
1. anything that looks like runtime internals is refused, not lowered;
2. a structurally dead or pre-answered world can never reach the runtime.
"""
import copy

import pytest

from compiler.errors import (InvalidReference, NoCausalProducer, SemanticAmbiguity)
from compiler.lower import lower
from compiler.schema import (CHANGE_TYPES, OBSERVATION_TYPES, PRECONDITION_TYPES,
                             contract_document, validate)
from compiler.semantic import _reject_runtime_syntax
from compiler.symbols import SymbolTable, slug
from sworldmodel.actions import KNOWN_CONDITIONS
from sworldmodel.terminal import OBSERVATION_KINDS
from sworldmodel.world import ALLOWED_EFFECT_OPS
from tests.fixtures_semantic import MESSAGE_CASE, QUANTITY_CASE


# ---------------------------------------------------------------------------
# the model may not emit runtime internals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    {"participants": [{"name": "A", "seq": 12}]},
    {"resolution": {"world_version": 4}},
    {"scheduled_events": [{"ops": [["fact.set", {}]]}]},
    {"action_affordances": [{"effects": [{"op": "resource.adjust"}]}]},
])
def test_runtime_internal_fields_refused(bad):
    with pytest.raises(SemanticAmbiguity, match="runtime-internal field"):
        _reject_runtime_syntax(bad)


@pytest.mark.parametrize("text", [
    "call world.apply to set the fact",
    "emit info.send_new to the recipient",
    "def compute_total(world):",
    "schedule a world.ops event",
])
def test_runtime_syntax_in_prose_refused(text):
    with pytest.raises(SemanticAmbiguity, match="runtime syntax"):
        _reject_runtime_syntax({"participants": [{"causal_relevance": text}]})


def test_ordinary_prose_is_not_refused():
    _reject_runtime_syntax(copy.deepcopy(MESSAGE_CASE))
    _reject_runtime_syntax(copy.deepcopy(QUANTITY_CASE))


# ---------------------------------------------------------------------------
# the semantic vocabularies stay small and bind onto universal runtime ops
# ---------------------------------------------------------------------------

def test_semantic_vocabularies_are_small_and_fixed():
    assert len(CHANGE_TYPES) == 11
    assert len(PRECONDITION_TYPES) == 11
    assert len(OBSERVATION_TYPES) == 9


def test_every_observation_type_has_a_runtime_reading():
    lowered = {
        "participant_holds_belief": "belief_topic_exists",
        "participant_noticed_information": "info_noticed_by",
        "world_fact_is": "fact_equals", "world_fact_exists": "fact_exists",
        "quantity_reaches": "resource_at_least",
        "quantity_measured": "resource_measure",
        "action_was_completed": "action_completed",
        "record_was_made": "record_exists",
        "tally_of_records": "tally_records",
    }
    assert set(lowered) == set(OBSERVATION_TYPES)
    assert set(lowered.values()) <= OBSERVATION_KINDS


def test_no_scenario_verb_reaches_the_runtime_vocabulary():
    """The runtime's operation and condition sets must stay domain-free.

    Matched on whole tokens: 'relationship.set' is a universal mechanic even
    though it contains the letters of 'ship'."""
    domain_words = {"vote", "reply", "email", "ship", "shipment", "produce",
                    "production", "approve", "approval", "negotiate", "treaty",
                    "meeting", "manufacture", "deliver", "delivery", "order"}
    for name in list(ALLOWED_EFFECT_OPS) + list(KNOWN_CONDITIONS):
        tokens = set(name.lower().replace(".", "_").split("_"))
        assert not (tokens & domain_words), f"{name} carries scenario meaning"


def test_contract_document_is_generated_from_the_vocabularies():
    doc = contract_document()
    for name in list(CHANGE_TYPES) + list(PRECONDITION_TYPES) + list(OBSERVATION_TYPES):
        assert name in doc, f"{name} missing from the contract handed to the model"


# ---------------------------------------------------------------------------
# structural integrity of compiled worlds
# ---------------------------------------------------------------------------

def test_action_referencing_an_undeclared_parameter_is_refused():
    """A dead action -- one whose precondition names a parameter it never
    declares -- can never fire, so it must not compile."""
    case = copy.deepcopy(MESSAGE_CASE)
    case["action_affordances"][0]["parameters"] = []
    with pytest.raises(InvalidReference, match="never declares"):
        lower(case)


def test_effect_referencing_an_undeclared_parameter_is_refused():
    case = copy.deepcopy(MESSAGE_CASE)
    case["action_affordances"][0]["consequences_on_completion"][0][
        "content_from_parameter"] = "nonexistent"
    with pytest.raises(InvalidReference, match="never declares"):
        lower(case)


def test_terminal_already_true_at_the_start_is_refused():
    """The trajectory must produce the answer -- never initialization."""
    case = copy.deepcopy(MESSAGE_CASE)
    case["resolution"]["observations"] = [
        {"observation_type": "participant_holds_belief",
         "participant": "Priya Raman", "topic": "approved statement"}]
    with pytest.raises(NoCausalProducer, match="already satisfied by the starting state"):
        lower(case)


def test_action_needs_exactly_one_completion_rule():
    case = copy.deepcopy(MESSAGE_CASE)
    del case["action_affordances"][0]["duration"]
    with pytest.raises(SemanticAmbiguity, match="cannot take no time"):
        validate(case)
    case["action_affordances"][0]["duration"] = {"status": "inferred",
                                                 "typical_minutes": 5}
    case["action_affordances"][0]["completion_condition"] = {"quantity": "x"}
    with pytest.raises(SemanticAmbiguity, match="exactly one"):
        validate(case)


# ---------------------------------------------------------------------------
# identifiers are generated by code, deterministically, and never by the model
# ---------------------------------------------------------------------------

def test_slugs_are_stable_and_collision_safe():
    assert slug("Alma Reyes") == "alma_reyes"
    assert slug("  Élan Vital!! ") == "elan_vital"
    t = SymbolTable()
    assert t.register("participant", "Acme Corp") == "acme_corp"
    with pytest.raises(SemanticAmbiguity, match="share the name"):
        t.register("participant", "acme corp")


def test_reference_resolution_reports_near_misses():
    t = SymbolTable()
    t.register("participant", "Miguel Santos")
    with pytest.raises(InvalidReference, match="did you mean"):
        t.resolve("participant", "Santos", "somewhere")


def test_same_scenario_always_yields_the_same_identifiers():
    a, b = lower(copy.deepcopy(MESSAGE_CASE)), lower(copy.deepcopy(MESSAGE_CASE))
    assert a.symbols.to_dict() == b.symbols.to_dict()
    assert sorted(a.world.action_defs) == sorted(b.world.action_defs)


def test_fact_keys_agree_between_writer_and_reader():
    """A record written by an effect and read by the terminal must land on the
    same key without either side naming an identifier."""
    from compiler.symbols import fact_key
    t = SymbolTable()
    assert fact_key(t, "the motion on the floor") == "the_motion_on_the_floor"
    assert fact_key(t, "the motion on the floor", "per_actor") \
        == "the_motion_on_the_floor:{actor}"
