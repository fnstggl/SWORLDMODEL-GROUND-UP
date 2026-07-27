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
    cond = inst["fields"]["condition"]["all_of"][0]
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
