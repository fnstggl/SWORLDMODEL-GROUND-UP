"""Exact replay with zero provider calls.

The kernel ledger is the authority: replaying its records reconstructs the
world without any model being consulted.  This module rebuilds the world
from the recorded ledger and verifies that the reconstruction matches the
live run exactly -- event ids and ordering, every actor's local view,
every private memory, and the terminal lineage.
"""
from __future__ import annotations

from sworldmodel import World, canonical_json

from .journal import Journal, OP_TERMINAL
from .views import build_view


def replay_trajectory(records: list, *, live_world=None) -> dict:
    """Rebuild from the ledger alone; compare against the live world when
    one is supplied.  Performs no provider calls by construction: nothing
    in this path can reach a caller."""
    world = World.from_records([dict(r) for r in records], live=True)
    journal = Journal(world)
    events = journal.events()
    views = {aid: build_view(world, journal, aid) for aid in sorted(world.actors)}
    terminals = [r["data"] for r in world.records if r["op"] == OP_TERMINAL]
    result = {
        "llm_calls": 0,
        "records_replayed": len(world.records),
        "event_ids": [e["event_id"] for e in events],
        "event_order_hash": canonical_json([e["event_id"] for e in events]),
        "state_hash": world.state_hash(),
        "terminal_status": terminals[-1]["status"] if terminals else None,
        "terminal_support": terminals[-1]["supporting_event_ids"]
        if terminals else [],
    }
    if live_world is not None:
        live_journal = Journal(live_world)
        live_views = {aid: build_view(live_world, live_journal, aid)
                      for aid in sorted(live_world.actors)}
        live_terminals = [r["data"] for r in live_world.records
                          if r["op"] == OP_TERMINAL]
        result.update({
            "state_hash_matches":
                world.state_hash() == live_world.state_hash(),
            "event_ids_match":
                [e["event_id"] for e in events]
                == [e["event_id"] for e in live_journal.events()],
            "views_match": canonical_json(views) == canonical_json(live_views),
            "memories_match": canonical_json(
                {aid: [m.content for m in world.actors[aid].memories]
                 for aid in sorted(world.actors)}) == canonical_json(
                {aid: [m.content for m in live_world.actors[aid].memories]
                 for aid in sorted(live_world.actors)}),
            "terminal_matches":
                (terminals[-1] if terminals else None)
                == (live_terminals[-1] if live_terminals else None),
        })
        result["exact"] = all(result[k] for k in
                              ("state_hash_matches", "event_ids_match",
                               "views_match", "memories_match",
                               "terminal_matches"))
    return result
