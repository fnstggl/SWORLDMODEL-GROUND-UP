"""Shape normalization: the exact synonymous JSON spellings live models
produce must validate identically to the canonical forms -- and genuinely
ambiguous input must still be rejected, never guessed."""
from compiler.capabilities import validate_capability


def test_nested_terminal_check_normalizes():
    inst = {"capability": "set_terminal", "fields": {
        "question_restated": "q", "mode": "condition",
        "cutoff_local": "2026-08-10T09:00", "tz": "America/Chicago",
        "condition": {"all_of": [
            {"information_noticed": {"participant": "P", "author": "Q",
                                     "info_type": "t"}}]},
        "yes_means": "y", "no_means": "n"}}
    assert validate_capability(inst) == []
    cond = inst["fields"]["condition"]        # one-clause all_of unwrapped
    assert cond["check"] == "information_noticed"
    assert inst["fields"]["cutoff_local"] == "2026-08-10 09:00"


def test_seconds_stripped_from_local_dt():
    inst = {"capability": "schedule_wake", "fields": {
        "participant": "P", "at_local": "2026-08-01 09:00:00", "tz": "UTC",
        "reason": "r", "provenance": "inferred"}}
    assert validate_capability(inst) == []
    assert inst["fields"]["at_local"] == "2026-08-01 09:00"


def test_nested_requires_and_effects_normalize():
    inst = {"capability": "define_action", "fields": {
        "verb": "act_x", "description": "d",
        "params": {"choice": {"note": "the pick", "required": True,
                              "one_of": ["a", "b"]}},
        "requires": [{"fact_equals": {"key": "k", "value": 1}}],
        "effects": [{"create_record": {"record_type": "r", "subject": "s",
                                       "choice_template": "{params.choice}"}}],
        "duration_minutes": 5, "provenance": "inferred", "note": "n"}}
    assert validate_capability(inst) == []
    f = inst["fields"]
    assert f["params"][0]["name"] == "choice"
    assert f["requires"][0]["kind"] == "fact_equals"
    assert f["effects"][0]["do"] == "create_record"


def test_single_effect_dict_normalizes_to_list():
    inst = {"capability": "schedule_external_event", "fields": {
        "name": "ev_x", "at_local": "2026-08-01 09:00", "tz": "UTC",
        "effects": {"create_record": {"record_type": "r", "subject": "s",
                                      "per_actor": False, "value": "v"}},
        "provenance": "inferred", "note": "n"}}
    assert validate_capability(inst) == []
    assert isinstance(inst["fields"]["effects"], list)
    assert inst["fields"]["effects"][0]["do"] == "create_record"


def test_none_known_attention_upgrades_but_real_rules_do_not():
    from compiler import graph_builder
    from compiler.world_graph import WorldGraph
    g = WorldGraph()
    for inst in [
        {"capability": "add_participant",
         "fields": {"name": "P", "role": "r", "why_needed": "w"}},
        {"capability": "add_channel",
         "fields": {"name": "chan_x", "latency_seconds": 5,
                    "provenance": "inferred", "note": "n"}},
        {"capability": "add_attention",
         "fields": {"participant": "P", "channel": "chan_x",
                    "mode": "none_known", "provenance": "uncertain",
                    "note": "unknown at first"}},
    ]:
        assert validate_capability(inst) == []
        assert graph_builder.add_item(g, inst, "x") == []
    upgrade = {"capability": "add_attention",
               "fields": {"participant": "P", "channel": "chan_x",
                          "mode": "periodic", "tz": "UTC",
                          "open_time": "09:00", "close_time": "17:00",
                          "check_every_minutes": 30,
                          "provenance": "inferred", "note": "patched"}}
    assert validate_capability(upgrade) == []
    assert graph_builder.add_item(g, upgrade, "y") == []
    assert len(g.attention) == 1 and g.attention[0]["mode"] == "periodic"
    dup = {"capability": "add_attention",
           "fields": {"participant": "P", "channel": "chan_x",
                      "mode": "continuous", "provenance": "inferred",
                      "note": "second real rule"}}
    assert validate_capability(dup) == []
    assert any("already declared" in e
               for e in graph_builder.add_item(g, dup, "z"))


def test_single_name_lists_and_one_clause_conjunctions_normalize():
    inst = {"capability": "set_terminal", "fields": {
        "question_restated": "q", "mode": "condition",
        "cutoff_local": "2026-08-10T23:59:00", "tz": "America/Chicago",
        "condition": {"all_of": [
            {"check": "information_sent", "sender": "P Q",
             "to": ["R S"], "info_type": "t"}]},
        "yes_means": "y", "no_means": "n"}}
    assert validate_capability(inst) == []
    cond = inst["fields"]["condition"]
    assert cond["check"] == "information_sent"     # all_of[1 clause] unwrapped
    assert cond["to"] == "R S"                     # single-name list -> name
    assert inst["fields"]["cutoff_local"] == "2026-08-10 23:59"


def test_set_terminal_outside_terminal_category_is_rejected():
    from compiler.translation import _validate_for
    inst = {"capability": "set_terminal", "fields": {
        "question_restated": "q", "mode": "condition",
        "cutoff_local": "2026-08-10 09:00", "tz": "UTC",
        "condition": {"check": "fact_exists", "key": "k"},
        "yes_means": "y", "no_means": "n"}}
    assert any("dedicated terminal item" in e
               for e in _validate_for("communication")(inst))
    assert _validate_for("terminal")(inst) == []


def test_ambiguous_shapes_still_rejected():
    # two keys: not the single-key nested form -- must NOT be guessed
    inst = {"capability": "set_terminal", "fields": {
        "question_restated": "q", "mode": "condition",
        "cutoff_local": "2026-08-10 09:00", "tz": "UTC",
        "condition": {"information_noticed": {"participant": "P"},
                      "extra": 1},
        "yes_means": "y", "no_means": "n"}}
    assert validate_capability(inst)
    # unknown kind stays rejected even in nested form
    inst2 = {"capability": "set_terminal", "fields": {
        "question_restated": "q", "mode": "condition",
        "cutoff_local": "2026-08-10 09:00", "tz": "UTC",
        "condition": {"made_up_check": {"participant": "P"}},
        "yes_means": "y", "no_means": "n"}}
    assert any("check must be one of" in e for e in validate_capability(inst2))
