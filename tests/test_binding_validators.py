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


def test_binding_prompts_carry_the_declared_uncertainties():
    """A binder told 'never resolve declared uncertainty' but shown none
    fills the gap the world just admitted to. generator_fuel: discovery
    declared the fuel burn rate unknown, and the binding then invented
    78 L/h from textbook generator efficiency and labelled it
    'inferred'."""
    from compiler.binding import Bindings, bind_world
    from compiler.graph import WorldGraph

    g = WorldGraph()
    g.add_node("terminal", "terminal", "how much fuel is left",
               "question_given", attrs={"answer_type": "quantity",
                                        "cutoff": {"when": "x"}})
    org = g.add_node("organization", "Plant", "the plant",
                     "question_given")
    rs = g.add_node("resource", "diesel", "fuel in the day tank",
                    "question_given", attrs={"holder": org, "amount": 620})
    g.add_edge(rs, "measured_by_terminal", "terminal:terminal")
    pr = g.add_node("process", "generator burns fuel", "it consumes fuel",
                    "question_given")
    g.add_edge(pr, "changes", rs)
    g.add_world_uncertainty(
        "fuel burn rate",
        "The generator's fuel consumption rate is unknown; the evidence "
        "states no litres-per-hour figure.")

    seen = []

    def call(system, user, model="stub", **kw):
        seen.append(user)
        doc = {"unsupported": "no consumption rate is stated anywhere"}
        return doc, json_dumps(doc), {"total_tokens": 0}

    import json as _json
    json_dumps = _json.dumps
    b = Bindings()
    try:
        bind_world(g, None, call=call, model="stub", into=b)
    except Exception:
        pass                      # the unsupported item refuses; fine
    assert seen, "no binding prompt was issued"
    joined = "\n".join(seen)
    assert "ALREADY DECLARED THESE THINGS UNKNOWN" in joined
    assert "consumption rate is unknown" in joined


def test_inferred_may_not_mean_general_world_knowledge():
    """The catalog must not license 'inferred' for textbook constants --
    that wording is what let a fabricated burn rate through."""
    from compiler.binding import _CATALOG

    assert "ARITHMETIC FROM NUMBERS THE EVIDENCE ITSELF STATES" in _CATALOG
    assert "NEVER means derived from general world knowledge" in \
        _CATALOG.replace("\n", " ").replace("  ", " ")
    assert "model_memory_unverified" in _CATALOG
