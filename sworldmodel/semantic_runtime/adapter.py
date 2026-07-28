"""Mechanical adapter: frozen four-field scene manifest -> existing runtime.

The compiler's exact output is consumed directly.  Nothing is re-prompted,
re-schematised, re-interpreted, or enriched: the four fields map onto
runtime primitives that already exist, and nothing else is added.

    actors           -> persistent runtime actor identities + private
                        context records (private context is never global)
    shared_context   -> immutable background fact, given to every actor
    starting_events  -> initial journal events / scheduled queue entries
    resolution       -> NOT passed here at all; it reaches only the
                        read-only terminal judge

There is no capability graph, action ontology, causal program, second
WorldSpec, handler registry or effect language between the manifest and
the runtime.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime

from sworldmodel import ActorState, World
from sworldmodel.simclock import iso, parse_iso

from .journal import Journal, OP_PROFILE

#: fields the adapter is allowed to see; the resolution is deliberately
#: excluded so it cannot leak into world or actor prompts by accident
CONSUMED_FIELDS = ("actors", "shared_context", "starting_events")


def actor_id_for(name: str, taken: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "actor"
    aid, n = base, 2
    while aid in taken:
        aid, n = f"{base}_{n}", n + 1
    return aid


def trajectory_id_for(question: str, start: str, cutoff: str) -> str:
    h = hashlib.sha256(f"{question}|{start}|{cutoff}".encode()).hexdigest()
    return f"traj_{h[:12]}"


def instantiate_scene_manifest(scene: dict, question: str, start_iso: str,
                               cutoff_iso: str):
    """-> (world, journal, bindings).  Deterministic: identical inputs
    produce a byte-identical world (hash-checked in tests)."""
    start = parse_iso(start_iso)
    world = World(start)
    journal = Journal(world)
    tid = trajectory_id_for(question, start_iso, cutoff_iso)
    bindings = {"trajectory_id": tid, "actor_ids": {}, "question": question,
                "start": start_iso, "cutoff": cutoff_iso,
                "starting_event_ids": []}

    world.apply("fact.set", {"key": "scene:question", "value": question}, None)
    world.apply("fact.set", {"key": "scene:shared_context",
                             "value": scene["shared_context"]}, None)
    world.apply("fact.set", {"key": "scene:trajectory_id", "value": tid}, None)
    world.apply("fact.set", {"key": "scene:cutoff", "value": cutoff_iso}, None)

    taken: set = set()
    for a in scene["actors"]:
        aid = actor_id_for(a["name"], taken)
        taken.add(aid)
        bindings["actor_ids"][a["name"]] = aid
        world.apply("actor.add",
                    ActorState(id=aid, name=a["name"], role="actor",
                               tz="UTC").to_dict(), None)
        # private context is stored as its own record, readable ONLY through
        # that actor's own view (never a global fact, never another actor's)
        world.apply(OP_PROFILE, {"actor": aid, "name": a["name"],
                                 "private_context": a["private_context"]},
                    None)

    world.seal_genesis()
    genesis_seq = world.version
    for i, e in enumerate(scene["starting_events"]):
        when = parse_iso(e["time"])
        audience = [bindings["actor_ids"][n] for n in e["visible_to"]]
        payload = {"description": e["description"], "for": audience,
                   # a starting event is given by the question: the actors it
                   # is visible to have it as their own situation
                   "observed": True, "after": "now"}
        if when <= start:
            rec = journal.commit(payload, cause=genesis_seq,
                                 source=f"starting_event[{i}]",
                                 trajectory_id=tid)
            bindings["starting_event_ids"].append(rec["event_id"])
        else:
            world.schedule("semantic.event",
                           {"envelope": payload,
                            "source": f"starting_event[{i}]"},
                           when, genesis_seq)
    return world, journal, bindings
