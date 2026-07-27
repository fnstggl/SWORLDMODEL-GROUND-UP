"""The binding validators refuse malformed small fields with teaching
defects, so the one targeted repair can fix them."""
from compiler.binding import _v_process, _v_substance


def _base():
    return {"amount_per_hour": 12, "rate_status": "verified",
            "rate_note": "measured", "output_resource": None}


def test_dated_operating_window_is_accepted():
    doc = _base()
    doc["operating"] = {"timezone": "America/Los_Angeles",
                        "workdays": [0], "start": "09:00", "end": "17:00",
                        "from_date": "2026-07-20",
                        "until_date": "2026-07-20"}
    assert _v_process(doc) == []


def test_operating_dates_must_parse():
    doc = _base()
    doc["operating"] = {"timezone": "UTC", "workdays": [0],
                        "start": "09:00", "end": "17:00",
                        "from_date": "July 20", "until_date": "2026-07-20"}
    assert any("from_date" in x for x in _v_process(doc))


def test_operating_window_must_not_be_reversed():
    doc = _base()
    doc["operating"] = {"timezone": "UTC", "workdays": [0, 1],
                        "start": "09:00", "end": "17:00",
                        "from_date": "2026-07-21",
                        "until_date": "2026-07-20"}
    assert any("before" in x for x in _v_process(doc))


def test_single_date_must_list_its_own_weekday():
    doc = _base()
    # 2026-07-20 is a Monday (weekday 0); workdays says Tuesday only
    doc["operating"] = {"timezone": "UTC", "workdays": [1],
                        "start": "09:00", "end": "17:00",
                        "from_date": "2026-07-20",
                        "until_date": "2026-07-20"}
    assert any("weekday" in x for x in _v_process(doc))


def test_substance_verdict_must_be_boolean_and_grounded():
    assert _v_substance({"same_substance": True, "why": "same goods"}) == []
    assert any("true or false" in x for x in
               _v_substance({"same_substance": "yes", "why": "x"}))
    assert any("why" in x for x in
               _v_substance({"same_substance": False, "why": ""}))


def test_missing_rate_teaches_the_decorative_escape():
    doc = {"amount_per_hour": None, "rate_status": None,
           "rate_note": "not applicable; fixed-size shipments",
           "output_resource": None}
    defects = _v_process(doc)
    (d,) = defects
    assert "decorative" in d
    # and a well-formed decorative reply is accepted outright
    assert _v_process({"decorative": True, "why": "transfers carry it"}) \
        == []


def test_stale_bindings_are_pruned_after_a_graph_rebuild():
    from compiler.binding import Bindings, prune_dead_bindings
    from compiler.graph import WorldGraph

    g = WorldGraph()
    keep = g.add_node("process", "line assembly", "kept", "question_given")
    b = Bindings()
    b.processes[keep] = {"amount_per_hour": 5, "rate_status": "verified"}
    b.processes["process:renamed_away"] = {"decorative": True, "why": "x"}
    b.events["event:gone"] = {"amounts": {}}
    b.slots["process:old"] = ("processes", "process:renamed_away")
    b.slots["process:kept"] = ("processes", keep)
    b.substance_identities = [
        {"holder": "organization:x", "a": "resource:dead",
         "b": "resource:dead2", "same": True}]
    dropped = prune_dead_bindings(g, b)
    assert set(dropped) == {"event:gone", "process:renamed_away"}
    assert list(b.processes) == [keep]
    assert list(b.slots) == ["process:kept"]
    assert b.substance_identities == []


def test_missing_duration_teaches_the_near_instant_rule():
    from compiler.binding import _v_action
    doc = {"duration_minutes": None,
           "duration_status": "model_memory_unverified",
           "duration_note": "presence is a state", "parameters": []}
    defects = _v_action(doc, [], [], [])
    assert any("near-instant" in x for x in defects)
    ok = {"duration_minutes": 1,
          "duration_status": "model_memory_unverified",
          "duration_note": "walking into the chamber", "parameters": []}
    assert _v_action(ok, [], [], []) == []
