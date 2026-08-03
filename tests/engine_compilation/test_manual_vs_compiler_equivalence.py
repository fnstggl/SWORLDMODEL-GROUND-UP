"""Manual-vs-compiler-produced initialization equivalence (fixture 1).

Directive ("Initial integration order" / "Mapping correctness tests"):
manually written fixtures and compiler-produced fixtures must initialize
EQUIVALENT Concordia worlds.  The pair here:

- MANUAL side: the frozen fixture ``individual_reply.yaml`` through the
  strict Phase 3 loader (file untouched; byte-identity re-proven against
  the freeze record in-test);
- COMPILER-SHAPED side: the committed hand-written vector
  ``vectors/individual_reply_scene.json`` -- the SAME scene expressed in
  the compiler's four-field manifest format -- through the deterministic
  adapter.

Both worlds run through the REAL planner into their
``ConcordiaInitializationPlan`` objects, which are compared field by
field, and then through the real builder + runner under identical
scripted models, where the recorded traces must be byte-identical.

Documented principled representation differences (asserted EXACTLY, not
papered over; recorded in COMPILER_TO_CONCORDIA_MAPPING.md):

1. **Actor identifiers.**  The fixture format declares ids
   (``sender``/``recipient``); the compiler manifest has no id field, so
   the adapter derives ids from names (``alex``/``morgan``).  The two id
   sets are compared through the name-keyed bijection -- names are the
   shared identity anchor and Concordia addresses entities by name.
2. **Identity fields.**  ``world_id``/``plan_id`` are code-owned
   derivations over different input identities, and
   ``compiler_provenance`` records the two different construction routes
   (``manual_fixture`` vs ``scene_compiler``).  Everything else in the
   plan must be byte-equal after the id bijection.
3. **World-level only:** ``success_criteria`` texts differ (the loader
   synthesizes an evaluator sentence; the adapter carries the manifest's
   resolution verbatim) and the fixture's YAML folded scalar leaves a
   trailing newline on ``shared_context``.  Both differences are
   invisible at plan level by design: evaluator-only prose never enters
   the plan, and the planner end-trims boundary whitespace.
"""

from __future__ import annotations

import hashlib
import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine compilation suite requires Python >= 3.12 (Concordia "
        "floor); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from compilation_helpers import (DOCUMENTED_PLAN_IDENTITY_FIELDS,
                                 FIXTURE_HASHES_PATH, FIXTURE_ONE_PATH,
                                 adapt_equivalence_vector, build_plan,
                                 map_plan_actor_ids, map_world_actor_ids,
                                 name_keyed_id_bijection, run_plan)
from sworldmodel.compilation import COMPILED_SCENE_SOURCE
from sworldmodel.decision.fixture_loader import (FIXTURE_SOURCE,
                                                 load_fixture_file)

MAX_STEPS = 2


def _fixture():
    return load_fixture_file(str(FIXTURE_ONE_PATH))


def _pair():
    """(fixture, adapted scene, id bijection adapter-side -> fixture-side)."""
    fx = _fixture()
    adapted = adapt_equivalence_vector()
    id_map = name_keyed_id_bijection(adapted.world, fx.world)
    return fx, adapted, id_map


def test_fixture_file_still_matches_freeze_record():
    with open(FIXTURE_ONE_PATH, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    recorded = None
    for line in FIXTURE_HASHES_PATH.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "individual_reply.yaml":
            recorded = parts[0]
    assert digest == recorded, (
        "frozen fixture individual_reply.yaml no longer matches its "
        "committed freeze record")


def test_id_bijection_is_name_keyed_and_total():
    fx, adapted, id_map = _pair()
    assert id_map == {"alex": "sender", "morgan": "recipient"}
    assert adapted.actor_id_by_name == {"Alex": "alex", "Morgan": "morgan"}


def test_plans_are_equal_modulo_the_documented_identity_fields():
    fx, adapted, id_map = _pair()
    plan_fixture = build_plan(fx.world, max_steps=MAX_STEPS,
                              evaluator_spec=fx.evaluator_spec)
    plan_adapted = build_plan(adapted.world, max_steps=MAX_STEPS,
                              evaluator_spec=fx.evaluator_spec)
    mapped = map_plan_actor_ids(plan_adapted.to_dict(), id_map)
    reference = plan_fixture.to_dict()

    differing = sorted(key for key in reference
                       if mapped[key] != reference[key])
    assert differing == sorted(DOCUMENTED_PLAN_IDENTITY_FIELDS), (
        "the two construction routes may differ ONLY in the documented "
        f"identity fields; got {differing}")

    # The load-bearing equalities, stated explicitly as well.
    assert mapped["actor_configs"] == reference["actor_configs"]
    assert mapped["initial_observations"] \
        == reference["initial_observations"]
    assert mapped["shared_init_data"] == reference["shared_init_data"]
    assert mapped["gm_config"] == reference["gm_config"]
    assert mapped["neutral_premise"] == reference["neutral_premise"]
    assert mapped["gm_initial_events"] == reference["gm_initial_events"]
    assert mapped["run_limits"] == reference["run_limits"]
    assert mapped["evaluator_spec"] == reference["evaluator_spec"]
    assert mapped["intervention_insertion"] \
        == reference["intervention_insertion"]

    # The identity differences are exactly the two construction routes.
    assert reference["compiler_provenance"]["source"] == FIXTURE_SOURCE
    assert mapped["compiler_provenance"]["source"] \
        == COMPILED_SCENE_SOURCE
    assert plan_fixture.plan_id != plan_adapted.plan_id
    assert plan_fixture.world_id != plan_adapted.world_id


def test_world_level_differences_are_exactly_the_documented_ones():
    fx, adapted, id_map = _pair()
    mapped = map_world_actor_ids(adapted.world.to_dict(), id_map)
    reference = fx.world.to_dict()
    differing = sorted(key for key in reference
                       if mapped[key] != reference[key])
    assert differing == ["compiler_provenance", "shared_context",
                         "success_criteria", "world_id"]
    # shared_context differs ONLY by the fixture file's trailing
    # newline (YAML folded scalar); interior bytes identical.
    assert mapped["shared_context"] \
        == reference["shared_context"].rstrip("\n")
    assert reference["shared_context"].endswith("\n")
    # Cast, contexts, events, and window are identical.
    assert mapped["actors"] == reference["actors"]
    assert mapped["starting_events"] == reference["starting_events"]
    assert mapped["start_time"] == reference["start_time"]
    assert mapped["cutoff"] == reference["cutoff"]
    assert mapped["intervention_insertion_point"] \
        == reference["intervention_insertion_point"]


def test_both_routes_run_byte_identical_traces_under_identical_models():
    fx, adapted, id_map = _pair()
    plan_fixture = build_plan(fx.world, max_steps=MAX_STEPS,
                              evaluator_spec=fx.evaluator_spec)
    plan_adapted = build_plan(adapted.world, max_steps=MAX_STEPS,
                              evaluator_spec=fx.evaluator_spec)

    # Identical scripted turns on both sides, keyed by ACTOR NAME (the
    # entity identity Concordia actually addresses).
    turns_by_name = {
        "Alex": "Alex drafts the opening note and sets it aside.",
        "Morgan": "Morgan continues the scheduled work for now.",
    }

    def turn_texts_for(plan):
        return {config.actor_id: turns_by_name[config.name]
                for config in plan.actor_configs}

    result_fixture, _actors_f, _gm_f = run_plan(
        plan_fixture, turn_texts_for(plan_fixture))
    result_adapted, _actors_a, _gm_a = run_plan(
        plan_adapted, turn_texts_for(plan_adapted))
    for result in (result_fixture, result_adapted):
        assert result["infrastructure_errors"] == []
        assert result["steps_completed"] == MAX_STEPS

    # Name-addressed engine artifacts must be byte-identical.
    assert result_fixture["committed_events"] \
        == result_adapted["committed_events"]
    assert result_fixture["event_trace"] == result_adapted["event_trace"]
    assert result_fixture["gm_memory"] == result_adapted["gm_memory"]
    assert result_fixture["terminal_status"] \
        == result_adapted["terminal_status"]
    assert result_fixture["run_metadata"] == result_adapted["run_metadata"]

    # Per-actor memories are keyed by the route's own actor ids; through
    # the bijection they are byte-identical rows.
    for adapter_id, fixture_id in id_map.items():
        assert result_adapted["actor_memories"][adapter_id] \
            == result_fixture["actor_memories"][fixture_id], adapter_id
