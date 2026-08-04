"""Strict fixture-loader tests: the three FROZEN manual fixtures load and
validate byte-unchanged (hash manifest re-verified here), the population
fixture expands to exactly 100 unique member actors plus the singleton,
expected_deterministic blocks parse to the frozen values, and every
documented rejection path fires with explicit errors."""

import hashlib
import os
import sys

import pytest
import yaml

from sworldmodel.decision import (
    CompiledDecisionWorld, ContractValidationError, InterventionCandidate,
    LoadedFixture, load_fixture_dict, load_fixture_file)
from sworldmodel.decision.fixture_loader import extract_prose_blocks

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures", "best_action")
FIXTURE_NAMES = ("individual_reply", "team_commitment", "population_offer")
FROZEN_WINNERS = {
    "individual_reply": "concise_relevant",
    "team_commitment": "private_ops_then_pilot",
    "population_offer": "offer_premium",
}


def fixture_path(name):
    return os.path.join(FIXTURE_DIR, f"{name}.yaml")


def load(name) -> LoadedFixture:
    return load_fixture_file(fixture_path(name))


def err(fn, *args, **kwargs):
    with pytest.raises(ContractValidationError) as excinfo:
        fn(*args, **kwargs)
    return excinfo.value


# ---------------------------------------------------------------------------
# Frozen files: untouched, loadable, exact expected values
# ---------------------------------------------------------------------------

def test_frozen_fixture_hashes_match_the_manifest():
    """Equivalent to `sha256sum -c FIXTURES.sha256`: implementation work
    must never change the frozen fixtures."""
    manifest = {}
    with open(os.path.join(FIXTURE_DIR, "FIXTURES.sha256")) as handle:
        for line in handle:
            digest, filename = line.split()
            manifest[filename] = digest
    assert set(manifest) == {f"{name}.yaml" for name in FIXTURE_NAMES}
    for filename, expected in manifest.items():
        with open(os.path.join(FIXTURE_DIR, filename), "rb") as handle:
            actual = hashlib.sha256(handle.read()).hexdigest()
        assert actual == expected, f"{filename} was modified"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_frozen_fixture_loads_and_validates(name):
    fx = load(name)
    assert fx.fixture_id == name
    assert isinstance(fx.world, CompiledDecisionWorld)
    assert all(isinstance(c, InterventionCandidate) for c in fx.candidates)
    assert len(fx.candidates) == 3
    assert fx.expected_deterministic.ranking_first == FROZEN_WINNERS[name]
    # ranking_first is one of the declared candidates
    ids = [c.candidate_id for c in fx.candidates]
    assert fx.expected_deterministic.ranking_first in ids
    # expectations cover exactly the declared candidates
    assert set(fx.expected_deterministic.per_candidate) == set(ids)
    # registry is populated with the code-owned identifiers
    assert fx.registry.has_world(fx.world.world_id)
    assert all(fx.registry.has_candidate(i) for i in ids)
    # code-owned world identity mirrors the compiled scheme
    assert fx.world.world_id.startswith("w_")
    assert len(fx.world.world_id) == 14
    prov = fx.world.compiler_provenance
    assert prov.source == "manual_fixture"
    assert prov.artifact_hashes["fixture_canonical_sha256"] \
        == fx.fixture_content_hash


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_loading_is_deterministic(name):
    first, second = load(name), load(name)
    assert first.world.content_hash() == second.world.content_hash()
    assert first.fixture_content_hash == second.fixture_content_hash
    assert [c.content_hash() for c in first.candidates] \
        == [c.content_hash() for c in second.candidates]


def test_individual_fixture_exact_content():
    fx = load("individual_reply")
    assert fx.world.actor_ids() == ("sender", "recipient")
    assert fx.world.intervention_insertion_point.actor_id == "sender"
    assert fx.world.to_dict()["start_time"] == "2026-08-03T14:00:00Z"
    assert fx.world.to_dict()["cutoff"] == "2026-08-10T14:00:00Z"
    assert fx.world.starting_events == ()
    assert fx.evaluator_spec.primary_metric == "recipient_reply_sent"
    assert fx.evaluator_spec.secondary_metrics \
        == ("meeting_scheduled", "explicit_decline")
    per = fx.expected_deterministic.per_candidate
    assert per["concise_relevant"]["terminal_status"] == "success"
    assert per["long_generic"]["terminal_status"] == "cutoff"
    assert per["urgent_pressure"]["explicit_decline"] is True
    assert set(fx.deterministic_script) == {"recipient"}
    assert set(fx.deterministic_script["recipient"]) == {
        "long_generic", "concise_relevant", "urgent_pressure"}
    assert len(fx.live_model_assertions) == 6
    assert fx.candidate_parameter_blocks == {}
    assert fx.label is None and fx.decision_rule is None


def test_team_fixture_exact_content():
    fx = load("team_commitment")
    assert fx.world.actor_ids() == (
        "proposal_owner", "operations_lead", "budget_owner", "product_lead",
        "neutral_member")
    assert fx.world.intervention_insertion_point.actor_id \
        == "proposal_owner"
    assert fx.decision_rule is not None and "veto" in fx.decision_rule
    assert fx.evaluator_spec.primary_metric == "decision_rule_satisfied"
    per = fx.expected_deterministic.per_candidate
    assert per["announce_full_plan"]["explicit_support_commitments"] == 1
    assert per["private_ops_then_pilot"]["explicit_support_commitments"] \
        == 4
    assert per["private_ops_then_pilot"]["decision_rule_satisfied"] is True
    assert per["immediate_binding_vote"]["veto_exercised"] is True
    assert set(fx.deterministic_script) == {
        "operations_lead", "budget_owner", "product_lead", "neutral_member"}
    assert len(fx.live_model_assertions) == 5


def test_population_fixture_expands_exactly_one_hundred_members():
    fx = load("population_offer")
    ids = fx.world.actor_ids()
    assert len(ids) == 101 and len(set(ids)) == 101
    assert ids[0] == "seller"
    members = ids[1:]
    assert list(members) == [f"customer_{i:03d}" for i in range(100)]
    # profile-by-count assignment, in declaration order
    by_profile = {"budget_conscious": 0, "premium_seeker": 0,
                  "feature_driven": 0}
    for actor in fx.world.actors[1:]:
        for profile in by_profile:
            if f"'{profile}'" in actor.private_context:
                by_profile[profile] += 1
    assert by_profile == {"budget_conscious": 40, "premium_seeker": 25,
                          "feature_driven": 35}
    # stated fields are carried verbatim into the member private context
    first = fx.world.actors[1]
    assert first.actor_id == "customer_000"
    assert "stated_budget_limit: 20" in first.private_context
    assert "discount_required" in first.private_context
    assert fx.world.intervention_insertion_point.actor_id == "seller"


def test_population_fixture_exact_expected_values():
    fx = load("population_offer")
    assert fx.label is not None and "SYNTHETIC" in fx.label
    assert fx.evaluator_spec.primary_metric == "total_revenue"
    expected = fx.expected_deterministic
    assert expected.metric_rankings["total_revenue"] == (
        "offer_premium", "offer_feature", "offer_budget")
    per = expected.per_candidate
    assert per["offer_budget"] == {
        "purchases": 40, "non_purchases": 60, "total_revenue": 720,
        "failures": 0, "completed_agent_runs": 100}
    assert per["offer_premium"]["total_revenue"] == 3750
    assert per["offer_feature"]["total_revenue"] == 2625
    # the mechanical parameter blocks ride along verbatim for the harness
    blocks = fx.candidate_parameter_blocks
    assert set(blocks) == {"offer_budget", "offer_premium", "offer_feature"}
    assert blocks["offer_budget"]["offer"]["price"] == 18
    assert blocks["offer_premium"]["offer"]["quality_tier"] == "premium"
    assert "collaboration" in blocks["offer_feature"]["offer"]["features"]
    assert fx.deterministic_script is None
    assert len(fx.infrastructure_assertions) == 5
    assert fx.live_model_assertions == ()


# ---------------------------------------------------------------------------
# The prose-block file layer (documented format decision)
# ---------------------------------------------------------------------------

def test_all_fixtures_are_plain_yaml_parseable():
    """History: the originally frozen population_offer ended a plain-scalar
    bullet with a line-final colon, which no conforming YAML parser accepts.
    Adjudicated as a syntax-only re-freeze (DECISIONS.md 2026-08-03,
    'Fixture 3 syntax re-freeze'): the colon became ', meaning' with zero
    semantic change, and every fixture must remain conforming YAML from now
    on. The loader's textual prose-block layer is retained as a
    belt-and-braces path and must agree with YAML's own parse."""
    for name in FIXTURE_NAMES:
        with open(fixture_path(name)) as handle:
            parsed = yaml.safe_load(handle.read())
        assert isinstance(parsed, dict) and parsed.get("fixture_id") == name


@pytest.mark.parametrize(
    "name", ["individual_reply", "team_commitment", "population_offer"])
def test_prose_extraction_matches_yaml_parse_where_yaml_works(name):
    with open(fixture_path(name)) as handle:
        text = handle.read()
    parsed = yaml.safe_load(text)  # all frozen fixtures are valid YAML now
    _rest, blocks = extract_prose_blocks(text)
    checked = 0
    for key in ("live_model_assertions", "infrastructure_assertions"):
        if key in parsed:
            assert blocks[key] == parsed[key], key
            checked += 1
    assert checked >= 1  # every fixture carries at least one assertion block


def test_prose_extraction_rejects_unrecognized_block_lines():
    text = ("fixture_id: sample\n"
            "live_model_assertions:\n"
            "  - A well-formed bullet line.\n"
            "  ~ not a bullet, not a continuation\n")
    exc = err(extract_prose_blocks, text)
    assert "invalid_value" in exc.codes()


# ---------------------------------------------------------------------------
# Synthetic fixtures: rejection paths (dict layer, pure stdlib)
# ---------------------------------------------------------------------------

START = "2026-08-03T14:00:00Z"
MID = "2026-08-03T15:00:00Z"
CUT = "2026-08-10T14:00:00Z"


def base_fixture():
    return {
        "fixture_id": "synthetic_case",
        "world": {
            "start_time": START,
            "cutoff": CUT,
            "actors": [
                {"id": "actor_a", "name": "Avery",
                 "private_context": "Wants a response."},
                {"id": "actor_b", "name": "Blake",
                 "private_context": "Responds to short clear requests."},
            ],
            "shared_context": "Two people share one task.",
            "starting_events": [],
        },
        "candidates": [
            {"id": "cand_one", "actor_id": "actor_a", "time": MID,
             "action": "Take the direct approach."},
            {"id": "cand_two", "actor_id": "actor_a", "time": MID,
             "action": "Take the indirect approach."},
        ],
        "evaluator": {"primary_metric": "outcome_reached",
                      "secondary_metrics": ["response_received"]},
        "expected_deterministic": {
            "ranking_first": "cand_one",
            "per_candidate": {
                "cand_one": {"outcome_reached": True,
                             "terminal_status": "success"},
                "cand_two": {"outcome_reached": False,
                             "terminal_status": "cutoff"},
            },
        },
    }


def test_synthetic_fixture_loads():
    fx = load_fixture_dict(base_fixture())
    assert fx.world.actor_ids() == ("actor_a", "actor_b")
    assert [c.candidate_id for c in fx.candidates] \
        == ["cand_one", "cand_two"]
    assert fx.candidates[0].summary == "Take the direct approach."
    assert fx.candidates[0].provenance.source == "user_supplied"


def test_fixture_root_must_be_a_mapping():
    exc = err(load_fixture_dict, ["not", "a", "mapping"])
    assert "wrong_type" in exc.codes()


def test_unknown_top_level_key_is_rejected():
    data = base_fixture()
    data["surprise_block"] = {"anything": 1}
    exc = err(load_fixture_dict, data)
    assert "unknown_field" in exc.codes()
    assert any("surprise_block" in path for path in exc.paths())


def test_missing_required_top_level_key_is_rejected():
    data = base_fixture()
    del data["evaluator"]
    exc = err(load_fixture_dict, data)
    assert "missing_field" in exc.codes()


def test_unknown_world_key_is_rejected():
    data = base_fixture()
    data["world"]["ambience"] = {"weather": "mild"}  # not actor-shaped
    exc = err(load_fixture_dict, data)
    assert "unknown_field" in exc.codes()
    assert any("world.ambience" in path for path in exc.paths())


def test_inline_singleton_actor_block_is_accepted():
    data = base_fixture()
    data["world"]["observer"] = {"id": "actor_c", "name": "Casey",
                                 "private_context": "Watches quietly."}
    fx = load_fixture_dict(data)
    assert "actor_c" in fx.world.actor_ids()


def test_population_block_is_expanded_generically():
    data = base_fixture()
    data["world"]["cohort_profiles"] = [
        {"profile_id": "steady", "count": 2, "stated_limit": 5,
         "stated_preferences": ["short_requests"]},
        {"profile_id": "eager", "count": 1, "stated_limit": 9},
    ]
    fx = load_fixture_dict(data)
    ids = fx.world.actor_ids()
    assert ("cohort_000", "cohort_001", "cohort_002") \
        == tuple(i for i in ids if i.startswith("cohort_"))
    member = next(a for a in fx.world.actors
                  if a.actor_id == "cohort_002")
    assert "'eager'" in member.private_context
    assert "stated_limit: 9" in member.private_context


def test_population_block_with_invalid_count_is_rejected():
    for bad in (0, True, "many"):
        data = base_fixture()
        data["world"]["cohort_profiles"] = [
            {"profile_id": "steady", "count": bad}]
        exc = err(load_fixture_dict, data)
        assert {"invalid_value", "wrong_type"} & set(exc.codes()), bad


def test_population_block_duplicate_profile_is_rejected():
    data = base_fixture()
    data["world"]["cohort_profiles"] = [
        {"profile_id": "steady", "count": 1},
        {"profile_id": "steady", "count": 1}]
    exc = err(load_fixture_dict, data)
    assert "duplicate_id" in exc.codes()


def test_candidate_extra_scalar_key_is_rejected():
    data = base_fixture()
    data["candidates"][0]["priority"] = 5
    exc = err(load_fixture_dict, data)
    assert "unknown_field" in exc.codes()


def test_candidate_mapping_extra_key_is_kept_as_parameter_block():
    data = base_fixture()
    data["candidates"][0]["knobs"] = {"level": 3}
    fx = load_fixture_dict(data)
    assert fx.candidate_parameter_blocks == {"cand_one":
                                             {"knobs": {"level": 3}}}


def test_duplicate_candidate_ids_are_rejected():
    data = base_fixture()
    data["candidates"][1]["id"] = "cand_one"
    exc = err(load_fixture_dict, data)
    assert "duplicate_id" in exc.codes()


def test_candidates_with_differing_actors_are_rejected():
    data = base_fixture()
    data["candidates"][1]["actor_id"] = "actor_b"
    exc = err(load_fixture_dict, data)
    assert "owner_mismatch" in exc.codes()


def test_candidate_actor_must_exist_in_world():
    data = base_fixture()
    for candidate in data["candidates"]:
        candidate["actor_id"] = "actor_ghost"
    exc = err(load_fixture_dict, data)
    assert "unknown_reference" in exc.codes()


def test_candidate_timing_outside_window_is_rejected():
    data = base_fixture()
    data["candidates"][0]["time"] = "2026-09-01T00:00:00Z"
    exc = err(load_fixture_dict, data)
    assert "timing_out_of_range" in exc.codes()


def test_cutoff_not_after_start_is_rejected():
    data = base_fixture()
    data["world"]["cutoff"] = START
    exc = err(load_fixture_dict, data)
    assert "invalid_value" in exc.codes()


def test_naive_fixture_time_is_rejected():
    data = base_fixture()
    data["world"]["start_time"] = "2026-08-03T14:00:00"
    exc = err(load_fixture_dict, data)
    assert "naive_datetime" in exc.codes()


def test_visible_to_accepts_ids_and_unique_names():
    data = base_fixture()
    data["world"]["starting_events"] = [
        {"description": "A prior exchange occurred.",
         "visible_to": ["actor_a", "Blake"], "time": MID}]
    fx = load_fixture_dict(data)
    assert fx.world.starting_events[0].visible_to == ("actor_a", "actor_b")


def test_unknown_visible_to_name_is_a_hard_error():
    data = base_fixture()
    data["world"]["starting_events"] = [
        {"description": "A prior exchange occurred.",
         "visible_to": ["Nobody"], "time": MID}]
    exc = err(load_fixture_dict, data)
    assert "unknown_reference" in exc.codes()


def test_ambiguous_visible_to_name_is_rejected():
    data = base_fixture()
    data["world"]["actors"].append(
        {"id": "actor_c", "name": "Blake",
         "private_context": "A second person with the same name."})
    data["world"]["starting_events"] = [
        {"description": "A prior exchange occurred.",
         "visible_to": ["Blake"], "time": MID}]
    exc = err(load_fixture_dict, data)
    codes = set(exc.codes())
    assert {"unknown_reference", "duplicate_id"} & codes


def test_event_time_outside_window_is_rejected():
    data = base_fixture()
    data["world"]["starting_events"] = [
        {"description": "A prior exchange occurred.",
         "visible_to": ["actor_a"], "time": "2026-09-01T00:00:00Z"}]
    exc = err(load_fixture_dict, data)
    assert "timing_out_of_range" in exc.codes()


def test_expected_winner_must_be_a_declared_candidate():
    data = base_fixture()
    data["expected_deterministic"]["ranking_first"] = "cand_ghost"
    exc = err(load_fixture_dict, data)
    assert "unknown_reference" in exc.codes()


def test_expected_block_must_cover_exactly_the_candidates():
    data = base_fixture()
    del data["expected_deterministic"]["per_candidate"]["cand_two"]
    exc = err(load_fixture_dict, data)
    assert "unknown_reference" in exc.codes()


def test_expected_metric_must_be_declared():
    data = base_fixture()
    data["expected_deterministic"]["per_candidate"]["cand_one"][
        "invented_metric"] = 1
    exc = err(load_fixture_dict, data)
    assert "unknown_reference" in exc.codes()


def test_expected_terminal_status_enum_is_enforced():
    data = base_fixture()
    data["expected_deterministic"]["per_candidate"]["cand_one"][
        "terminal_status"] = "victorious"
    exc = err(load_fixture_dict, data)
    assert "invalid_enum" in exc.codes()


def test_expected_unknown_key_is_rejected():
    data = base_fixture()
    data["expected_deterministic"]["narrative"] = "it goes well"
    exc = err(load_fixture_dict, data)
    assert "unknown_field" in exc.codes()


def test_metric_ranking_key_must_name_declared_metric_and_cover_all():
    data = base_fixture()
    data["expected_deterministic"]["ranking_by_invented"] = [
        "cand_one", "cand_two"]
    exc = err(load_fixture_dict, data)
    assert "unknown_reference" in exc.codes()
    data = base_fixture()
    data["expected_deterministic"]["ranking_by_outcome_reached"] = [
        "cand_one"]
    exc = err(load_fixture_dict, data)
    assert "unknown_reference" in exc.codes()
    data = base_fixture()
    data["expected_deterministic"]["ranking_by_outcome_reached"] = [
        "cand_one", "cand_two"]
    fx = load_fixture_dict(data)
    assert fx.expected_deterministic.metric_rankings["outcome_reached"] \
        == ("cand_one", "cand_two")


def test_script_keys_must_resolve_to_actors_and_candidates():
    data = base_fixture()
    data["deterministic_script"] = {
        "actor_ghost": {"cand_one": {"response": "none"}}}
    exc = err(load_fixture_dict, data)
    assert "unknown_reference" in exc.codes()
    data = base_fixture()
    data["deterministic_script"] = {
        "actor_b": {"cand_ghost": {"response": "none"}}}
    exc = err(load_fixture_dict, data)
    assert "unknown_reference" in exc.codes()
    data = base_fixture()
    data["deterministic_script"] = {
        "actor_b": {"cand_one": {"response": "agree"},
                    "cand_two": {"response": "decline"}}}
    fx = load_fixture_dict(data)
    assert fx.deterministic_script["actor_b"]["cand_two"] \
        == {"response": "decline"}


def test_non_json_content_is_rejected():
    data = base_fixture()
    data["world"]["start_time"] = object()
    exc = err(load_fixture_dict, data)
    assert "wrong_type" in exc.codes()


def test_all_loader_errors_are_collected_together():
    data = base_fixture()
    data["surprise_block"] = 1                       # unknown top key
    del data["evaluator"]                            # missing top key
    exc = err(load_fixture_dict, data)
    assert len(exc.issues) >= 2


def test_load_fixture_file_names_pyyaml_when_missing(monkeypatch,
                                                     tmp_path):
    monkeypatch.setitem(sys.modules, "yaml", None)
    with pytest.raises(ImportError) as excinfo:
        load_fixture_file(fixture_path("individual_reply"))
    assert "PyYAML" in str(excinfo.value)
    assert "load_fixture_dict" in str(excinfo.value)


def test_load_fixture_file_round_trip_on_written_synthetic(tmp_path):
    path = tmp_path / "synthetic_case.yaml"
    path.write_text(yaml.safe_dump(base_fixture()), encoding="utf-8")
    fx = load_fixture_file(str(path))
    assert fx.fixture_id == "synthetic_case"
    assert fx.world.content_hash() \
        == load_fixture_dict(base_fixture()).world.content_hash()


def test_loaded_worlds_pass_wider_contract_round_trip():
    for name in FIXTURE_NAMES:
        fx = load(name)
        rebuilt = CompiledDecisionWorld.from_dict(fx.world.to_dict())
        assert rebuilt == fx.world
        assert rebuilt.content_hash() == fx.world.content_hash()
        for candidate in fx.candidates:
            again = InterventionCandidate.from_dict(candidate.to_dict())
            assert again == candidate
