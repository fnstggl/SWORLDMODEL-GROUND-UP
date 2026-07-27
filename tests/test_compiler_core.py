"""Deterministic compiler core: menu validation, reference building,
assembly, lowering, validation, and round trip -- on a world whose every
label is meaningless (person_a, channel_c, record_d...).  If the machinery
works here, it is operating on structure, not on scenario words."""
import pytest

from compiler import graph_builder
from compiler.assembly import assemble
from compiler.capabilities import render_menu, validate_capability, \
    CAPABILITIES, EFFECT_MACROS
from compiler.lowering import lower
from compiler.roundtrip import summarize
from compiler.validation import validate_world
from compiler.world_graph import WorldGraph

START = "2026-07-27T08:00:00+00:00"


def cap(_capability, **fields):
    return {"capability": _capability, "fields": fields}


def neutral_items():
    """A minimal but complete world out of meaningless labels."""
    return [
        cap("add_participant", name="Person A", aliases=["PA"],
            role="holder_of_role_x", tz="America/New_York",
            goals=["obtain the record"], traits=["thorough"],
            plan="waiting on the outcome", why_needed="their question"),
        cap("add_participant", name="Person B", role="holder_of_role_y",
            tz="Europe/Berlin", goals=["do their job"],
            why_needed="only authorized producer"),
        cap("add_aggregate", name="Org E", kind="organization",
            note="publishes signals on a schedule"),
        cap("add_channel", name="channel_c", latency_seconds=30,
            provenance="inferred", note="typical relay time"),
        cap("add_channel_access", sender="Person A", recipient="Person B",
            channel="channel_c", provenance="question_given",
            note="stated route"),
        cap("add_channel_access", sender="Person B", recipient="Person A",
            channel="channel_c", provenance="inferred",
            note="reply route exists"),
        cap("add_attention", participant="Person A", channel="channel_c",
            mode="periodic", tz="America/New_York", open_time="09:00",
            close_time="17:00", check_every_minutes=30,
            provenance="inferred", note="working-hours checker"),
        cap("add_attention", participant="Person B", channel="channel_c",
            mode="periodic", tz="Europe/Berlin", open_time="08:00",
            close_time="18:00", check_every_minutes=60,
            provenance="inferred", note="hourly checker"),
        cap("add_belief", participant="Person B", topic="the_value",
            statement="the value is 42, settled earlier",
            provenance="question_given"),
        cap("add_commitment", participant="Person A",
            what="reach out about the record", due_local="2026-07-27 10:00",
            tz="America/New_York", provenance="question_given"),
        cap("add_resource", holder="Org E", resource="stock_r", amount=10,
            unit_note="units", provenance="inferred"),
        cap("add_process", name="flow_f", owner="Org E", resource="stock_r",
            rate_per_hour=2.0, active_at_start=True, provenance="inferred",
            note="steady accumulation"),
        cap("add_operating_window", process="flow_f", tz="Europe/Berlin",
            workdays=[0, 1, 2, 3, 4], start_time="08:00", end_time="16:00",
            provenance="inferred", note="working hours only"),
        cap("define_action", verb="produce_record_d",
            description="create the typed record for subject_s. params: "
                        "choice.",
            allowed_roles=["holder_of_role_y"],
            params=[{"name": "choice", "note": "the recorded choice",
                     "required": True, "one_of": ["done", "declined"]}],
            effects=[{"do": "create_record", "record_type": "record_d",
                      "subject": "subject_s",
                      "choice_template": "{params.choice}"},
                     {"do": "send_information", "to": ["Person A"],
                      "channel": "channel_c",
                      "content_template": "the record is {params.choice}",
                      "info_type": "outcome_notice"}],
            duration_minutes=15, provenance="inferred",
            note="short authorized act"),
        cap("schedule_external_event", name="signal_event",
            at_local="2026-07-28 09:00", tz="Europe/Berlin",
            effects=[{"do": "send_information", "author": "Org E",
                      "to": ["Person B"], "channel": "channel_c",
                      "content_template": "the scheduled signal",
                      "info_type": "signal_t"}],
            provenance="question_given", note="already scheduled"),
        cap("declare_uncertainty", about="whether person_b acts at all",
            why_it_matters="the record only exists if they act"),
        cap("declare_exclusion", what="unrelated third parties",
            why_safe="they cannot produce or block the record"),
        cap("set_terminal",
            question_restated="does the typed record for subject_s exist "
                              "before the deadline?",
            mode="condition",
            cutoff_local="2026-07-30 12:00", tz="America/New_York",
            condition={"check": "record_exists", "record_type": "record_d",
                       "subject": "subject_s"},
            yes_means="the record was produced in time",
            no_means="no record before the deadline"),
    ]


def build_graph(items=None):
    g = WorldGraph()
    for i, inst in enumerate(items or neutral_items()):
        errs = validate_capability(inst)
        assert errs == [], f"item {i}: {errs}"
        errs = graph_builder.add_item(g, inst, f"t[{i}]")
        assert errs == [], f"item {i}: {errs}"
    return g


# ------------------------------------------------------------------ menu
def test_menu_single_source_of_truth():
    menu = render_menu()
    for cap_name, table in CAPABILITIES.items():
        assert cap_name in menu
        for field in table["fields"]:
            assert field in menu, f"{cap_name}.{field} missing from menu"
    for macro in EFFECT_MACROS:
        assert macro in menu


def test_validator_rejects_invention():
    bad = cap("add_participant", name="X", role="r", why_needed="w",
              invented_field="nope")
    assert any("invented" in e or "unknown field" in e
               for e in validate_capability(bad))
    assert validate_capability({"capability": "made_up_capability",
                                "fields": {}})
    assert validate_capability({"capability": "UNSUPPORTED"})  # needs reason
    assert not validate_capability({"capability": "UNSUPPORTED",
                                    "reason": "cannot express"})


def test_uncertain_never_backs_concrete_numbers():
    bad = cap("add_channel", name="channel_z", latency_seconds=10,
              provenance="uncertain", note="?")
    assert any("uncertain" in e for e in validate_capability(bad))


def test_template_hygiene():
    bad = cap("define_action", verb="v_x", description="d",
              effects=[{"do": "create_record", "record_type": "r",
                        "subject": "s",
                        "choice_template": "{params.undeclared}"}],
            duration_minutes=5, provenance="inferred", note="n")
    assert any("undeclared" in e for e in validate_capability(bad))
    bad_ext = cap("schedule_external_event", name="e", at_local="2026-07-28 09:00",
                  tz="UTC", effects=[{"do": "create_record",
                                      "record_type": "r", "subject": "s",
                                      "per_actor": False,
                                      "value": "{params.x}"}],
                  provenance="inferred", note="n")
    assert any("not allowed in scheduled external events" in e
               for e in validate_capability(bad_ext))


# ---------------------------------------------------------- builder rules
def test_builder_rejects_unknown_and_ambiguous_names():
    g = build_graph()
    errs = graph_builder.add_item(
        g, cap("add_belief", participant="Person Zz", topic="t",
               statement="s", provenance="inferred"), "x")
    assert any("unknown name" in e for e in errs)
    # ambiguity: an alias colliding with another participant's name
    inst = cap("add_participant", name="Person C", aliases=["Person A"],
               role="holder_of_role_z", why_needed="test")
    graph_builder.add_item(g, inst, "y")
    errs = graph_builder.add_item(
        g, cap("add_belief", participant="Person A", topic="t",
               statement="s", provenance="inferred"), "z")
    assert any("ambiguous" in e for e in errs)


def test_builder_merges_duplicate_participants():
    g = build_graph()
    before = len(g.participants)
    errs = graph_builder.add_item(
        g, cap("add_participant", name="person a", role="holder_of_role_x",
               goals=["a second goal"], why_needed="dup"), "dup")
    assert errs == []
    assert len(g.participants) == before
    pa = g.participants[g.registry.resolve("Person A")]
    assert "a second goal" in pa["goals"]


# ------------------------------------------------- assembly + lowering
def test_assemble_lower_validate_roundtrip():
    g = build_graph()
    plan, errors = assemble(g, START)
    assert errors == []
    world, terminal, minds = lower(plan)
    # routes exist both ways; attention rules landed; process windowed off
    assert world.facts.get("route:channel_c:person_a:person_b") is True
    assert world.facts.get("route:channel_c:person_b:person_a") is True
    assert "channel_c" in world.actors["person_a"].attention
    # 08:00 UTC start = 10:00 Berlin on a Monday -> window open
    assert world.processes["flow_f"]["active"] is True
    assert set(minds) == {"person_a", "person_b"}
    assert "Person A" in minds["person_a"]["persona_brief"]
    report = validate_world(g, plan)
    assert report.ok(), report.blocking
    assert report.dry_run["events_fired"] > 0
    text = summarize(world, plan["terminal_spec"], plan)
    for needle in ("Person A", "Person B", "channel_c", "produce_record_d",
                   "flow_f", "record_d:subject_s", "FINISH LINE"):
        assert needle in text, f"{needle} missing from round trip"


def test_lowering_is_deterministic():
    g = build_graph()
    plan, _ = assemble(g, START)
    w1, _, _ = lower(plan)
    w2, _, _ = lower(plan)
    assert w1.state_hash() == w2.state_hash()


def test_authorized_verbs_only_offered_to_authorized_roles():
    g = build_graph()
    plan, _ = assemble(g, START)
    world, _, _ = lower(plan)
    defn = world.action_defs["produce_record_d"]
    roles = [c["roles"] for c in defn["conditions"]
             if c.get("require") == "role_in"][0]
    assert roles == ["holder_of_role_y"]
    # the built-in universal actions exist in every compiled world
    assert "transmit_information" in world.action_defs
    assert "review_information" in world.action_defs


# ------------------------------------------------------------ renaming test
def test_universality_under_renaming():
    """Rename every label; the machinery must behave identically."""
    def rename(obj):
        if isinstance(obj, dict):
            return {k: rename(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [rename(v) for v in obj]
        if isinstance(obj, str):
            return (obj.replace("Person A", "Blorp Q")
                       .replace("person_a", "blorp_q")
                       .replace("Person B", "Zande W")
                       .replace("Org E", "Klorg V")
                       .replace("channel_c", "conduit_k")
                       .replace("record_d", "mark_m")
                       .replace("stock_r", "heap_h")
                       .replace("flow_f", "drift_g"))
        return obj

    items = [rename(i) for i in neutral_items()]
    g = build_graph(items)
    plan, errors = assemble(g, START)
    assert errors == []
    report = validate_world(g, plan)
    assert report.ok(), report.blocking
    world, _, _ = lower(plan)
    assert "blorp_q" in world.actors and "zande_w" in world.actors
