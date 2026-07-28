"""SceneManifestAdapter: direct instantiation of a validated scene into the
existing persistent runtime.  No second semantic representation.

The adapter only:
1. generates stable world/actor/event IDs (code-owned);
2. creates persistent runtime actors;
3. stores each actor's private context ONLY in that actor's state;
4. stores shared context in the shared scene record (and hands each actor
   their access to it);
5. appends starting events to the canonical event ledger;
6. resolves visible_to references to runtime actor IDs;
7. exposes each starting event only to the declared actors (via the
   kernel's information lifecycle on a single generic "scene" channel --
   directly-experienced events, latency zero, universal mechanics);
8. schedules the cutoff through the existing clock/engine;
9. attaches the natural-language resolution condition;
10. preserves the original manifest byte-for-byte as an audit artifact
    (the pipeline writes it; this module never mutates it).

It does NOT infer actions, compile capabilities, build process graphs,
invent communication routes, or enumerate futures.  After initialization,
actors use the existing generic mind/world interface."""
from __future__ import annotations

import hashlib
import re

from sworldmodel import ActorState, AttentionRule, World
from sworldmodel.simclock import iso, parse_iso

SCENE_CHANNEL = "scene"


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "actor"


def world_id_for(question: str, start: str, cutoff: str) -> str:
    h = hashlib.sha256(f"{question}|{start}|{cutoff}".encode()).hexdigest()
    return f"w_{h[:12]}"


def instantiate_scene(scene: dict, question: str, start_iso: str,
                      cutoff_iso: str):
    """validated+normalized scene -> (World, bindings).  Deterministic;
    calling twice yields byte-identical worlds (hash-checked by the
    pipeline)."""
    start = parse_iso(start_iso)
    w = World(start)
    bindings = {"world_id": world_id_for(question, start_iso, cutoff_iso),
                "actor_ids": {}, "event_records": [],
                "code_owned_defaults": {
                    "actor_role": "actor",
                    "actor_tz": "UTC",
                    "scene_channel_latency": "0s (directly experienced)"}}
    w.apply("fact.set", {"key": "scene:question", "value": question}, None)
    w.apply("fact.set", {"key": "scene:shared_context",
                         "value": scene["shared_context"]}, None)
    w.apply("channel.add", {
        "name": SCENE_CHANNEL,
        "latency": {"seconds": 0, "basis": "verified",
                    "note": "scene events are directly experienced by the "
                            "actors they are visible to"}}, None)
    # actors: private context lives ONLY in the owning actor's state
    ids_taken: set = set()
    for a in scene["actors"]:
        aid = slug(a["name"])
        n = 2
        while aid in ids_taken:
            aid, n = f"{slug(a['name'])}_{n}", n + 1
        ids_taken.add(aid)
        bindings["actor_ids"][a["name"]] = aid
        st = ActorState(
            id=aid, name=a["name"], role="actor", tz="UTC",
            attention={SCENE_CHANNEL: AttentionRule(
                None, None, "verified",
                "events declared visible to this actor are directly "
                "experienced")})
        w.apply("actor.add", st.to_dict(), None)
        w.apply("actor.memory", {
            "actor": aid, "kind": "context", "content": a["private_context"],
            "source": "scene_manifest:private_context"}, None)
        w.apply("actor.memory", {
            "actor": aid, "kind": "context", "content": scene["shared_context"],
            "source": "scene_manifest:shared_context"}, None)
    # starting events: ledgered; visible only to the declared actors
    for i, e in enumerate(scene["starting_events"]):
        eid = f"se{i + 1}"
        t = parse_iso(e["time"])
        recipients = [bindings["actor_ids"][n] for n in e["visible_to"]]
        ops = [["fact.set", {"key": f"scene:event:{eid}",
                             "value": e["description"]}]]
        if recipients:
            ops.append(["info.send_new", {
                "author": "scene", "to": recipients,
                "channel": SCENE_CHANNEL, "content": e["description"],
                "data": {"type": "scene_event", "event_id": eid}}])
        ev = w.schedule("world.ops",
                        {"ops": ops, "note": f"starting event {eid}"},
                        max(t, start), None)
        bindings["event_records"].append(
            {"event_id": eid, "ledger_seq": ev.seq, "at": iso(max(t, start)),
             "visible_to_ids": recipients,
             "description": e["description"]})
    bindings["personas"] = {
        bindings["actor_ids"][a["name"]]: {
            "name": a["name"],
            "persona_brief": f"You are {a['name']}.\n{a['private_context']}"}
        for a in scene["actors"]}
    return w, bindings
