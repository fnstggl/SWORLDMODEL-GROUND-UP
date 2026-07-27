"""Declarative terminal specs: validation, mechanical evaluation, cited
producers, and the definition-level default completion condition."""
import pytest

from sworldmodel import (Decision, Engine, Intention, Mind, TerminalSpecError,
                         World, at_local, build_terminal, iso,
                         validate_terminal_spec)

START = at_local(2026, 5, 4, 8, 0, tz="UTC")
CUTOFF = at_local(2026, 5, 6, 12, 0, tz="UTC")


def base_spec(**over):
    spec = {"question": "does the marker fact appear before the cutoff?",
            "cutoff": iso(CUTOFF), "mode": "condition",
            "condition": {"check": "fact_exists", "key": "marker"},
            "yes_means": "the marker was recorded",
            "no_means": "no marker before the cutoff"}
    spec.update(over)
    return spec


def make_world():
    w = World(START)
    w.apply("channel.add", {"name": "wire",
                            "latency": {"seconds": 5, "basis": "verified",
                                        "note": "electronic push"}}, None)
    return w


# ---------------------------------------------------------------- validation
def test_spec_validation_rejects_bad_shapes():
    with pytest.raises(TerminalSpecError):
        validate_terminal_spec({"question": "q", "cutoff": iso(CUTOFF),
                                "mode": "condition"})          # no condition
    with pytest.raises(TerminalSpecError):
        validate_terminal_spec(base_spec(condition={"check": "nonsense"}))
    with pytest.raises(TerminalSpecError):
        validate_terminal_spec(base_spec(mode="value"))        # no value
    with pytest.raises(TerminalSpecError):
        validate_terminal_spec(base_spec(condition={"all_of": []}))
    validate_terminal_spec(base_spec())                        # good spec passes


# ------------------------------------------------------- condition terminals
def test_condition_yes_with_cited_producer():
    w = make_world()
    term = build_terminal(base_spec())
    seq = w.apply("fact.set", {"key": "marker", "value": True}, None)
    ans = term.evaluate(w, False)
    assert ans["answer"] == "yes"
    assert ans["computed_from"] == [f"record:{seq}"]


def test_condition_no_at_final_only():
    w = make_world()
    term = build_terminal(base_spec())
    assert term.evaluate(w, False) is None
    ans = term.evaluate(w, True)
    assert ans["answer"] == "no" and ans["computed_from"] == ["terminal.cutoff"]


def test_all_of_and_resource_check():
    w = make_world()
    w.apply("resource.set", {"holder": "site_a", "name": "units", "amount": 3}, None)
    spec = base_spec(condition={"all_of": [
        {"check": "fact_exists", "key": "marker"},
        {"check": "resource_at_least", "holder": "site_a", "name": "units",
         "amount": 5}]})
    term = build_terminal(spec)
    w.apply("fact.set", {"key": "marker", "value": 1}, None)
    assert term.evaluate(w, False) is None          # units still below 5
    w.apply("resource.adjust", {"holder": "site_a", "name": "units", "delta": 2}, None)
    ans = term.evaluate(w, False)
    assert ans["answer"] == "yes" and len(ans["computed_from"]) == 2


def test_information_noticed_check_matches_author_and_type():
    w = make_world()
    from sworldmodel import ActorState
    w.apply("actor.add", ActorState(id="p1", name="P One", role="observer",
                                    tz="UTC").to_dict(), None)
    iid = w.send_info("origin_x", ["p1"], "wire", "content body",
                      data={"type": "confirmation"}, cause=None)
    # delivered + noticed via ledger ops (mechanics tested elsewhere)
    w.clock.advance_to(w.clock.now.__class__.fromtimestamp(
        w.clock.now.timestamp() + 10, tz=w.clock.now.tzinfo))
    w.apply("info.deliver", {"id": iid, "to": "p1", "channel": "wire"}, None)
    spec = base_spec(condition={"check": "information_noticed", "actor": "p1",
                                "author": "origin_x",
                                "info_type": "confirmation"})
    term = build_terminal(spec)
    assert term.evaluate(w, False) is None          # delivered != noticed
    nseq = w.apply("info.notice", {"id": iid, "actor": "p1"}, None)
    ans = term.evaluate(w, False)
    assert ans["answer"] == "yes"
    assert ans["computed_from"] == [f"record:{nseq}"]
    # a different type never matches
    other = build_terminal(base_spec(condition={
        "check": "information_noticed", "actor": "p1", "info_type": "denial"}))
    assert other.evaluate(w, False) is None


# ------------------------------------------------------------ value terminal
def test_value_resource_reported_at_final():
    w = make_world()
    w.apply("resource.set", {"holder": "site_b", "name": "units", "amount": 0}, None)
    w.apply("resource.adjust", {"holder": "site_b", "name": "units", "delta": 7}, None)
    spec = base_spec(mode="value",
                     value={"read": "resource", "holder": "site_b",
                            "name": "units"})
    spec.pop("condition")
    term = build_terminal(spec)
    assert term.evaluate(w, False) is None
    ans = term.evaluate(w, True)
    assert ans["answer"] == 7.0 and ans["computed_from"]


# --------------------------------------------------- decision-count terminal
def test_decision_count_majority_and_tie():
    w = make_world()
    spec = base_spec(mode="decision_count",
                     decision={"prefix": "choice:", "options": ["alpha", "beta"],
                               "tie": "tie"})
    spec.pop("condition")
    term = build_terminal(spec)
    w.apply("fact.set", {"key": "choice:p1", "value": "alpha"}, None)
    w.apply("fact.set", {"key": "choice:p2", "value": "beta"}, None)
    ans = term.evaluate(w, True)
    assert ans["answer"] == "tie"
    w.apply("fact.set", {"key": "choice:p3", "value": "alpha"}, None)
    ans = term.evaluate(w, True)
    assert ans["answer"] == "alpha" and len(ans["computed_from"]) == 3


def test_decision_count_resolves_early_via_resolve_when():
    w = make_world()
    spec = base_spec(mode="decision_count",
                     decision={"prefix": "choice:", "options": ["alpha", "beta"],
                               "tie": "tie"},
                     resolve_when={"check": "fact_equals", "key": "closed",
                                   "value": True})
    spec.pop("condition")
    term = build_terminal(spec)
    w.apply("fact.set", {"key": "choice:p1", "value": "beta"}, None)
    assert term.evaluate(w, False) is None
    w.apply("fact.set", {"key": "closed", "value": True}, None)
    assert term.evaluate(w, False)["answer"] == "beta"


# ------------------------------- default completion condition on definitions
class OneShotMind(Mind):
    """Proposes a single condition-completed intention with no duration and
    no explicit completes_when: the definition's default must apply."""
    def __init__(self):
        self.done = False

    def decide(self, view):
        if self.done:
            return Decision(note="nothing further")
        self.done = True
        return Decision(intentions=[Intention("await_level", {"qty": 10})],
                        note="waiting for the level")


def test_default_completes_when_from_definition():
    w = World(START)
    w.apply("action.define",
            {"verb": "await_level",
             "description": "complete when the holder's level reaches qty",
             "conditions": [],
             "default_completes_when": {
                 "resource_at_least": ["site_c", "units", "{params.qty}"]},
             "effects": [["fact.set", {"key": "level_reached", "value": True}]]},
            None)
    w.apply("resource.set", {"holder": "site_c", "name": "units", "amount": 0}, None)
    w.apply("process.add", {"id": "flow1", "holder": "site_c", "resource": "units",
                            "rate_per_hour": 5.0, "active": True,
                            "basis": "verified", "note": "given flow"}, None)
    from sworldmodel import ActorState
    w.apply("actor.add", ActorState(id="p1", name="P One", role="operator",
                                    tz="UTC").to_dict(), None)
    w.schedule("wake.actor", {"actor": "p1", "reason": "scheduled_start",
                              "detail": "begin"}, START, None)
    term = build_terminal(base_spec(condition={"check": "fact_equals",
                                               "key": "level_reached",
                                               "value": True}))
    out = Engine(w, {"p1": OneShotMind()}, term).run()
    assert out.status == "resolved" and out.answer["answer"] == "yes"
    # the watch created from the substituted default fired at 10 units / 5 per hour
    assert w.resource("site_c", "units") >= 10.0
