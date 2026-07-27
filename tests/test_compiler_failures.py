"""Wrong worlds must stop: pre-resolved terminals, pre-written outcomes,
missing producers, dead worlds, unnoticeable answers, dead authority."""
from compiler import graph_builder
from compiler.assembly import assemble
from compiler.capabilities import validate_capability
from compiler.validation import validate_world
from compiler.world_graph import WorldGraph

from tests.test_compiler_core import cap, neutral_items, START


def graph_from(items):
    g = WorldGraph()
    for i, inst in enumerate(items):
        assert validate_capability(inst) == [], inst
        errs = graph_builder.add_item(g, inst, f"t[{i}]")
        assert errs == [], errs
    return g


def replace_terminal(items, terminal):
    return [i for i in items if i["capability"] != "set_terminal"] + [terminal]


def validate(items):
    g = graph_from(items)
    plan, errors = assemble(g, START)
    if errors:
        return None, errors
    return validate_world(g, plan), []


def test_terminal_true_at_genesis_is_blocking():
    items = neutral_items()
    items.insert(0, cap("add_fact", key="marker_done", value=True,
                        provenance="question_given", note="already true"))
    items = replace_terminal(items, cap(
        "set_terminal", question_restated="is the marker set?",
        mode="condition", cutoff_local="2026-07-30 12:00",
        tz="America/New_York",
        condition={"check": "fact_equals", "key": "marker_done",
                   "value": True},
        yes_means="y", no_means="n"))
    report, errors = validate(items)
    assert errors == []
    assert any("already true at genesis" in b for b in report.blocking)


def test_scheduled_event_writing_terminal_fact_is_blocking():
    items = neutral_items()
    items = replace_terminal(items, cap(
        "set_terminal", question_restated="does the outcome fact appear?",
        mode="condition", cutoff_local="2026-07-30 12:00",
        tz="America/New_York",
        condition={"check": "fact_equals", "key": "outcome_fact",
                   "value": "yes"},
        yes_means="y", no_means="n"))
    items.append(cap(
        "schedule_external_event", name="prewritten",
        at_local="2026-07-29 09:00", tz="UTC",
        effects=[{"do": "create_record", "record_type": "outcome",
                  "subject": "fact", "per_actor": False, "value": "yes"}],
        provenance="inferred", note="illegitimate scripted answer"))
    # the record key is 'outcome:fact' -- point the terminal at it exactly
    items = replace_terminal(items, cap(
        "set_terminal", question_restated="does the outcome fact appear?",
        mode="condition", cutoff_local="2026-07-30 12:00",
        tz="America/New_York",
        condition={"check": "fact_exists", "key": "outcome:fact"},
        yes_means="y", no_means="n"))
    report, errors = validate(items)
    assert errors == []
    assert any("pre-written" in b for b in report.blocking)


def test_missing_producer_is_blocking():
    items = neutral_items()
    items = replace_terminal(items, cap(
        "set_terminal", question_restated="does an unproducible fact appear?",
        mode="condition", cutoff_local="2026-07-30 12:00",
        tz="America/New_York",
        condition={"check": "fact_exists", "key": "nothing_makes_this"},
        yes_means="y", no_means="n"))
    report, errors = validate(items)
    assert errors == []
    assert any("nothing in the world can produce" in b
               for b in report.blocking)


def test_dead_world_is_blocking():
    items = [i for i in neutral_items()
             if i["capability"] not in ("schedule_external_event",
                                        "add_commitment",
                                        "add_operating_window")]
    report, errors = validate(items)
    assert errors == []
    assert any("dead world" in b for b in report.blocking)


def test_unnoticeable_answer_information_is_blocking():
    items = [i for i in neutral_items()
             if not (i["capability"] == "add_attention"
                     and i["fields"]["participant"] == "Person A")]
    items = replace_terminal(items, cap(
        "set_terminal",
        question_restated="does person_a notice the outcome notice?",
        mode="condition", cutoff_local="2026-07-30 12:00",
        tz="America/New_York",
        condition={"check": "information_noticed", "participant": "Person A",
                   "info_type": "outcome_notice"},
        yes_means="y", no_means="n"))
    report, errors = validate(items)
    assert errors == []
    assert any("attends no channel" in b for b in report.blocking)


def test_unauthorized_terminal_action_is_blocking():
    items = neutral_items()
    items = replace_terminal(items, cap(
        "set_terminal", question_restated="does person_a produce the record?",
        mode="condition", cutoff_local="2026-07-30 12:00",
        tz="America/New_York",
        condition={"check": "action_completed", "verb": "produce_record_d",
                   "participant": "Person A"},
        yes_means="y", no_means="n"))
    report, errors = validate(items)
    assert errors == []
    assert any("not authorized" in b for b in report.blocking)


def test_no_terminal_is_a_hard_assembly_error():
    items = [i for i in neutral_items() if i["capability"] != "set_terminal"]
    g = graph_from(items)
    plan, errors = assemble(g, START)
    assert plan is None
    assert any("finish line" in e for e in errors)


def test_commitment_before_start_is_an_assembly_error():
    items = neutral_items()
    items.append(cap("add_commitment", participant="Person B",
                     what="already overdue thing", due_local="2026-07-20 10:00",
                     tz="UTC", provenance="inferred"))
    g = graph_from(items)
    plan, errors = assemble(g, START)
    assert plan is None
    assert any("before the" in e and "start" in e for e in errors)


def test_chance_encoded_as_fact_is_blocking():
    items = neutral_items()
    items.insert(0, cap("add_fact", key="reply_probability", value=0.15,
                        provenance="inferred", note="invented chance"))
    report, errors = validate(items)
    assert errors == []
    assert any("pre-write the outcome" in b for b in report.blocking)


def test_past_external_event_folds_into_starting_state():
    items = neutral_items()
    items.append(cap(
        "schedule_external_event", name="already_happened",
        at_local="2026-07-20 09:00", tz="UTC",
        effects=[{"do": "create_record", "record_type": "prior_mark",
                  "subject": "subject_p", "per_actor": False,
                  "value": "done"}],
        provenance="question_given", note="occurred before the start"))
    from tests.test_compiler_failures import graph_from
    g = graph_from(items)
    from compiler.assembly import assemble
    from compiler.lowering import lower
    plan, errors = assemble(g, START)
    assert errors == []
    assert any("folded into the starting state" in n for n in plan["notes"])
    world, _, _ = lower(plan)
    assert world.facts.get("prior_mark:subject_p") == "done"
    assert not any(s for s in plan["schedules"]
                   if "already_happened" in str(s))


def test_needs_review_findings_are_surfaced_not_silenced():
    # a participant nobody can wake -> needs_review, not silent acceptance
    items = neutral_items()
    items.insert(2, cap("add_participant", name="Person Idle",
                        role="holder_of_role_w", why_needed="edge case"))
    report, errors = validate(items)
    assert errors == []
    assert report.ok()
    assert any("person_idle" in f for f in report.needs_review)
