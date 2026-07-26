"""Checkpoint and resume.

Because every state change is a ledger record and pending events are ledger
records too, a checkpoint is simply the ledger up to a settled instant plus
the clock position.  Resuming replays the ledger (pure fold, zero actor/LLM
calls), rebuilds the pending-event queue from scheduled-but-unfired records,
re-wires the scenario's code adapters, and continues.  Nothing fires twice:
the processed-event set comes from the same ledger.
"""
from __future__ import annotations

import json

from .engine import Engine, Terminal
from .simclock import iso
from .world import World, canonical_json, sha256_of


def _queue_hash(world: World) -> str:
    return sha256_of([[e.seq, e.t.isoformat(), e.kind, e.depth]
                      for e in world.queue.pending()])


def save_checkpoint(world: World, path: str | None = None) -> dict:
    """Snapshot a paused (settled) world.  Contains everything needed to
    resume exactly: the immutable ledger and the clock position, plus
    verification hashes for both the state and the pending-event queue."""
    if world._pending_wakes:
        raise RuntimeError("checkpoint requires a settled world (no pending wakes)")
    cp = {
        "format": 1,
        "now": iso(world.clock.now),
        "ledger_position": world._seq,
        "state_hash": world.state_hash(),
        "queue_hash": _queue_hash(world),
        "records": list(world.records),
    }
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(canonical_json(cp))
    return cp


def load_checkpoint(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resume(checkpoint: dict, minds: dict, terminal: Terminal, wire=None) -> Engine:
    """Rebuild a live engine from a checkpoint.

    Scenario action definitions and scheduled events are ledger records, so
    they come back with the state; only minds (code) and the terminal are
    re-bound.  An optional ``wire(world)`` hook may perform extra read-only
    setup; it must not write records (detected and refused).
    """
    if checkpoint.get("format") != 1:
        raise RuntimeError(f"unsupported checkpoint format {checkpoint.get('format')!r}")
    records = checkpoint["records"]
    if records[-1]["seq"] != checkpoint["ledger_position"]:
        raise RuntimeError("checkpoint ledger position does not match its records")
    world = World.from_records(records, live=True)
    before = world._seq
    if wire is not None:
        wire(world)
        if world._seq != before:
            raise RuntimeError("wire() must not write records")
    if world.state_hash() != checkpoint["state_hash"]:
        raise RuntimeError("resumed state hash does not match checkpoint")
    if "queue_hash" in checkpoint and _queue_hash(world) != checkpoint["queue_hash"]:
        raise RuntimeError("resumed pending-event queue does not match checkpoint")
    return Engine(world, minds, terminal)
