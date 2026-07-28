"""The binding between the frozen minimal world compiler and the semantic
runtime.

These tests exercise the real production route -- ``compiler.compile_scene``
-- and feed its exact four-field output into the runtime.  Both providers
are scripted, so the test is deterministic and calls nothing live, but the
CODE PATH is the production one: no hand-authored world, no alternate
compiler, no reshaped manifest.  If the runtime ever consumed a fixture
instead of the compiler's own output, the manifest-identity assertions
below would fail.
"""
import json
import subprocess
import sys

import pytest

from compiler import SceneCaller, compile_scene
from sworldmodel.semantic_runtime import instantiate_scene_manifest
from sworldmodel.semantic_runtime.adapter import CONSUMED_FIELDS
from sworldmodel.semantic_runtime.llm import RuntimeCaller
from sworldmodel.semantic_runtime.replay import replay_trajectory
from sworldmodel.semantic_runtime.trace import Trace
from sworldmodel.semantic_runtime.trajectory import run_trajectory
from sworldmodel.semantic_runtime.views import build_view, render_view

QUESTION = "Will Bo respond to Ada's message before the cutoff?"
START = "2026-07-27T09:00:00-05:00"
CUTOFF = "2026-08-10T09:00:00-05:00"

COMPILER_MANIFEST = {
    "actors": [
        {"name": "Ada Vance",
         "private_context": "Ada wants a response about her proposal."},
        {"name": "Bo Ferrer",
         "private_context": "Bo receives many approaches and rarely replies."},
    ],
    "shared_context": "Ada has prepared a short message and can send it.",
    "starting_events": [
        {"time": START, "description": "Ada sends her prepared message to Bo.",
         "visible_to": ["Ada Vance"]},
    ],
    "resolution": "Resolve YES only if the committed history shows Bo sent "
                  "Ada a response before the cutoff. Otherwise NO.",
}
APPROVE = {"verdict": "APPROVE", "defects": []}


def compiler_transport(responses):
    it = iter([json.dumps(r) for r in responses])

    def transport(system, user):
        return next(it)
    return transport


def compile_via_production_route():
    """The exact production entry point, with a scripted provider."""
    caller = SceneCaller(transport=compiler_transport([COMPILER_MANIFEST,
                                                       APPROVE]))
    return compile_scene(QUESTION, START, CUTOFF, caller=caller)


def runtime_model(system, user):
    if "read-only outcome judge" in system:
        # UNRESOLVED is not available at the cutoff, and code enforces it
        status = ("NO_AT_CUTOFF" if "THIS IS THE FINAL JUDGMENT" in user
                  else "UNRESOLVED")
        return json.dumps({"status": status, "supporting_event_ids": [],
                           "explanation": "nothing yet"}), {}
    if "You are the world" in system:
        if "starting_event" in user:
            return json.dumps({
                "judgment": "It lands where Bo could see it.",
                "event": {"description": "Ada's message arrives for Bo.",
                          "for": ["bo_ferrer"], "observed": False,
                          "after": "1 minutes"}, "wakes": []}), {}
        return json.dumps({"judgment": "Nothing concrete follows.",
                           "event": None, "wakes": []}), {}
    return json.dumps({"decision": "Nothing to do.", "intentions": [],
                       "private_updates": []}), {}


def test_end_to_end_question_to_trajectory_through_production_compiler():
    result = compile_via_production_route()
    assert result.status in ("compiled", "corrected"), result.reason
    scene = result.manifest
    # the runtime consumes the compiler's EXACT four fields
    assert set(scene) == {"actors", "shared_context", "starting_events",
                          "resolution"}

    world, journal, bindings = instantiate_scene_manifest(
        scene, QUESTION, START, CUTOFF)
    # every actor and starting event came from the compiler's own output
    assert [world.actors[a].name for a in sorted(world.actors)] == \
        sorted(a["name"] for a in scene["actors"])
    assert journal.shared_context() == scene["shared_context"]
    assert journal.events()[0]["description"] == \
        scene["starting_events"][0]["description"]

    caller = RuntimeCaller(transport=runtime_model)
    traj = run_trajectory(world, journal, bindings, scene["resolution"],
                          caller, max_steps=6, trace=Trace())
    assert traj.status in ("resolved", "cutoff", "incomplete"), traj.reason
    assert len(journal.events()) >= 2          # a real trajectory ran
    verification = replay_trajectory(world.records, live_world=world)
    assert verification["exact"] and verification["llm_calls"] == 0


def test_adapter_never_consumes_or_exposes_the_resolution():
    result = compile_via_production_route()
    scene = result.manifest
    world, journal, bindings = instantiate_scene_manifest(
        scene, QUESTION, START, CUTOFF)
    assert "resolution" not in CONSUMED_FIELDS
    blob = json.dumps(world.records)
    assert scene["resolution"] not in blob     # never enters world state
    for aid in world.actors:
        rendered = render_view(build_view(world, journal, aid))
        assert scene["resolution"] not in rendered
        assert "Resolve YES" not in rendered


def test_runtime_uses_the_existing_kernel_not_a_second_one():
    from sworldmodel import World
    from sworldmodel.events import EventQueue
    from sworldmodel.simclock import Clock
    scene = compile_via_production_route().manifest
    world, _, _ = instantiate_scene_manifest(scene, QUESTION, START, CUTOFF)
    assert isinstance(world, World)
    assert isinstance(world.queue, EventQueue)
    assert isinstance(world.clock, Clock)


def test_frozen_compiler_files_are_unchanged():
    """The compiler is frozen for this phase: every production blob hash
    must match the freeze record taken before any work began."""
    frozen = {}
    with open("artifacts/semantic_runtime/COMPILER_FREEZE.txt") as f:
        for line in f:
            if line.strip():
                blob, path = line.split()
                frozen[path] = blob
    out = subprocess.run(["git", "ls-files", "-s", "compiler/"],
                         capture_output=True, text=True, check=True)
    current = {}
    for line in out.stdout.splitlines():
        parts = line.split()
        current[parts[3]] = parts[1]
    changed = [p for p, h in frozen.items()
               if current.get(p) != h]
    assert changed == [], f"frozen compiler files changed: {changed}"
    assert set(current) == set(frozen), "compiler files were added or removed"
