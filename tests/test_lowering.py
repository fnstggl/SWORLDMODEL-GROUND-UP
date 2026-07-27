"""The deterministic lowering layer, tested without any model call.

These prove the compiler->runtime boundary: hand-written semantic scenarios
become executable worlds, and malformed or dishonest ones are refused at the
correct stage rather than approximated.
"""
import copy

import pytest

from sworldmodel import Engine, World, elapsed, parse_iso
from compiler import lower
from tests.scripted_minds import scripted_minds
from compiler.errors import (InvalidReference, LoweringGap, NoCausalProducer,
                             NothingScheduled, SemanticAmbiguity)
from compiler.schema import validate
from tests.fixtures_semantic import (MESSAGE_CASE, MESSAGE_CASE_SCRIPT,
                                     QUANTITY_CASE, QUANTITY_CASE_SCRIPT)


def compiled(case):
    return lower(copy.deepcopy(case))


# ---------------------------------------------------------------------------
# a message world compiles and executes
# ---------------------------------------------------------------------------

def test_message_case_compiles_into_the_runtime():
    c = compiled(MESSAGE_CASE)
    w = c.world
    assert set(w.actors) == {"dana_whitfield", "priya_raman"}
    assert set(w.channels) == {"work_email"}
    assert set(w.action_defs) == {"send_an_on_record_comment"}
    # the world starts when the earliest real thing happens, not "now"
    assert w.start == parse_iso("2026-05-08T18:40:00-04:00")
    # authority is identity-based and came from available_to
    defn = w.action_defs["send_an_on_record_comment"]
    assert {"require": "actor_in", "actors": ["priya_raman"]} in defn["conditions"]
    # the effect is a universal op, not a scenario verb
    assert defn["effects"][0][0] == "info.send_new"


def test_message_case_runs_to_a_trajectory_derived_answer():
    c = compiled(MESSAGE_CASE)
    out = Engine(c.world, scripted_minds(c, MESSAGE_CASE_SCRIPT), c.terminal_spec.to_terminal()).run()
    assert out.status in ("resolved", "cutoff")
    assert out.answer["computed_from"]
    # the request was sent Friday evening; the press officer is in London and
    # only sees it on the next working day -- real calendar time, not a step
    notice = next(r for r in c.world.records
                  if r["op"] == "info.notice" and r["data"]["actor"] == "priya_raman")
    sent = parse_iso("2026-05-08T18:40:00-04:00")
    assert parse_iso(notice["t"]) > sent
    assert elapsed(sent, parse_iso(notice["t"])).total_seconds() > 3600 * 24


def test_compiled_world_replays_exactly():
    c = compiled(MESSAGE_CASE)
    Engine(c.world, scripted_minds(c, MESSAGE_CASE_SCRIPT), c.terminal_spec.to_terminal()).run()
    replayed = World.from_records(c.world.records)
    assert replayed.state_hash() == c.world.state_hash()
    assert replayed.terminal_result == c.world.terminal_result


def test_lowering_is_deterministic():
    a, b = compiled(MESSAGE_CASE), compiled(MESSAGE_CASE)
    assert a.world.state_hash() == b.world.state_hash()
    assert a.symbols.to_dict() == b.symbols.to_dict()


# ---------------------------------------------------------------------------
# an operational world compiles and integrates continuous time
# ---------------------------------------------------------------------------

def test_quantity_case_compiles_and_accrues_real_production():
    # the quantity world has no affordances; its own (empty) script is the
    # honest pairing -- the message script here used to no-op silently
    c = compiled(QUANTITY_CASE)
    out = Engine(c.world, scripted_minds(c, QUANTITY_CASE_SCRIPT),
                 c.terminal_spec.to_terminal()).run()
    assert out.status == "cutoff"
    # opening stock 120 + a 200-unit transfer that the line could actually cover
    assert out.answer["answer"] == 320.0
    assert out.answer["computed_from"]
    accruals = [r for r in c.world.records if r["op"] == "process.accrue"]
    assert accruals, "the continuous process never ran"
    # production only accrued inside the declared day shift
    for r in accruals:
        span = (parse_iso(r["data"]["to"]) - parse_iso(r["data"]["from"]))
        assert span.total_seconds() <= 8 * 3600 + 1


def test_operating_periods_become_real_shift_events():
    c = compiled(QUANTITY_CASE)
    starts = [e for e in c.world.queue.pending()
              if e.kind == "world.ops"
              and any(op[0] == "process.active" and op[1]["active"]
                      for op in e.data.get("ops", []))]
    assert len(starts) >= 2          # one per workday in the window


# ---------------------------------------------------------------------------
# refusals: each failure surfaces at its own stage
# ---------------------------------------------------------------------------

def test_unknown_participant_reference_refused():
    case = copy.deepcopy(MESSAGE_CASE)
    case["action_affordances"][0]["consequences_on_completion"][0]["to"] = {
        "participants": ["Somebody Else"]}
    with pytest.raises(InvalidReference, match="Somebody Else"):
        lower(case)


def test_all_reference_defects_are_reported_together():
    """A scenario with several missing declarations must report them all in
    one go, so a single bounded repair round can fix them."""
    case = copy.deepcopy(MESSAGE_CASE)
    case["action_affordances"][0]["consequences_on_completion"][0]["to"] = {
        "participants": ["Ghost One"]}
    case["information"][0]["holder"] = "Ghost Two"
    case["participants"][0]["attention"][0]["route"] = "carrier pigeon"
    with pytest.raises(InvalidReference) as ei:
        lower(case)
    assert len(ei.value.detail["defects"]) == 3
    joined = ei.value.reason
    assert "Ghost One" in joined and "Ghost Two" in joined and "carrier pigeon" in joined


def test_duplicate_participant_names_are_ambiguous():
    case = copy.deepcopy(MESSAGE_CASE)
    case["participants"].append(dict(case["participants"][0]))
    with pytest.raises(SemanticAmbiguity, match="not unique"):
        validate(case)


def test_uncertain_duration_cannot_become_a_number():
    case = copy.deepcopy(MESSAGE_CASE)
    case["action_affordances"][0]["duration"]["status"] = "uncertain"
    with pytest.raises(LoweringGap, match="completion_condition"):
        lower(case)


def test_missing_duration_is_never_invented():
    case = copy.deepcopy(MESSAGE_CASE)
    del case["action_affordances"][0]["duration"]["typical_minutes"]
    with pytest.raises(LoweringGap, match="will not invent"):
        lower(case)


def test_uncertain_rate_cannot_become_a_process():
    case = copy.deepcopy(QUANTITY_CASE)
    case["processes"][0]["rate"]["status"] = "uncertain"
    with pytest.raises(LoweringGap, match="uncertain rate"):
        lower(case)


def test_uncertain_delivery_delay_refused():
    case = copy.deepcopy(MESSAGE_CASE)
    case["communication_routes"][0]["delivery_delay"]["status"] = "uncertain"
    with pytest.raises(LoweringGap, match="uncertain delivery delay"):
        lower(case)


def test_terminal_with_no_producer_is_refused():
    case = copy.deepcopy(MESSAGE_CASE)
    # nothing in this world ever produces that tag
    case["resolution"]["observations"][0]["tag"] = "a signed affidavit"
    with pytest.raises(NoCausalProducer, match="nothing in this world can"):
        lower(case)


def test_unsupported_noticing_yields_unresolved_not_no():
    """A message really is sent and delivered, so the causal pathway exists --
    only the NOTICING is unsupported by evidence. That is unresolved
    uncertainty, not an impossible world, and the honest answer at the cutoff
    is 'unresolved' rather than 'no'."""
    case = copy.deepcopy(MESSAGE_CASE)
    case["participants"][0]["attention"] = []     # reporter attends nothing
    c = lower(case)                                # compiles: pathway is real
    assert c.terminal_spec.uncertain_paths, "the uncertain step was not recorded"
    out = Engine(c.world, scripted_minds(c, MESSAGE_CASE_SCRIPT), c.terminal_spec.to_terminal()).run()
    assert out.answer["answer"] == "unresolved"
    assert out.answer["unresolved_because"]
    # and the world is honest about why: delivered, never noticed
    assert any(t["step"] == "noticing_uncertain" for t in c.trace)


def test_genuinely_impossible_terminal_is_still_refused():
    """Unresolved uncertainty is distinct from no producer at all."""
    case = copy.deepcopy(MESSAGE_CASE)
    case["resolution"]["observations"][0]["tag"] = "a signed affidavit"
    with pytest.raises(NoCausalProducer):
        lower(case)


def test_world_with_nothing_scheduled_is_refused():
    case = copy.deepcopy(MESSAGE_CASE)
    case["scheduled_events"] = []
    case["information"] = []
    with pytest.raises(NothingScheduled):
        lower(case)


def test_unknown_quantity_reference_refused():
    case = copy.deepcopy(QUANTITY_CASE)
    case["scheduled_events"][1]["effects"][0]["quantity"] = "gold bars"
    with pytest.raises(InvalidReference, match="no quantity named 'gold bars'"):
        lower(case)


def test_role_that_no_participant_holds_is_refused():
    case = copy.deepcopy(MESSAGE_CASE)
    case["action_affordances"][0]["available_to"] = {"roles": ["chief counsel"]}
    with pytest.raises(InvalidReference, match="chief counsel"):
        lower(case)


def test_record_made_by_a_world_event_must_name_its_maker():
    case = copy.deepcopy(MESSAGE_CASE)
    case["scheduled_events"][0]["effects"] = [
        {"change_type": "create_record", "record_type": "sign-off",
         "value": "granted"}]
    with pytest.raises(LoweringGap, match="must name who"):
        lower(case)


def test_naive_timestamp_refused():
    case = copy.deepcopy(MESSAGE_CASE)
    case["scheduled_events"][0]["time"] = "2026-05-11 17:00:00"
    with pytest.raises(SemanticAmbiguity, match="time zone"):
        lower(case)


# ---------------------------------------------------------------------------
# the lowering layer must never call a model
# ---------------------------------------------------------------------------

def test_lowering_makes_no_model_calls(monkeypatch):
    import compiler.llm as llm

    def explode(*a, **kw):
        raise AssertionError("the lowering layer called a model")

    monkeypatch.setattr(llm, "call_json", explode)
    c = compiled(MESSAGE_CASE)
    Engine(c.world, scripted_minds(c, MESSAGE_CASE_SCRIPT), c.terminal_spec.to_terminal()).run()
