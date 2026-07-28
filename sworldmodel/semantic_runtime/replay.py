"""Exact replay with zero provider calls, verified rather than asserted.

The kernel ledger is the authority: replaying its records reconstructs the
world without any model being consulted.  Verifying that is only
meaningful if the check can actually FAIL, so three things matter here.

**The reconstruction must be independent of what it is compared to.**
``World.from_records`` stores the record objects it is handed, so passing
the live world's own records would make both sides read the very same
dicts and every comparison would be ``x == x``.  The records are deep-
copied first; the two sides then share no object at all.

**The ledger's own integrity is checked, not assumed.**  ``from_records``
replays reducers directly and enforces no causality, so this module checks
it: contiguous sequence numbers, non-decreasing timestamps, every cause
existing and preceding its record, every observation transition naming an
event that reached that actor, and every terminal YES citing events that
exist.

**Nothing is compared by summary alone.**  The kernel's state hash covers
only reduced state, and the semantic runtime's records are trace-only, so
a hash match says nothing about them.  Every committed event is compared
field by field, every observation transition, every memory with all of its
fields, every actor's whole view, and the entire terminal lineage.

A verification over an empty or incomplete ledger reports itself as
vacuous instead of claiming exactness it did not establish.
"""
from __future__ import annotations

import copy

from sworldmodel import World, canonical_json
from sworldmodel.simclock import parse_iso

from .journal import Journal, OP_EVENT, OP_OBSERVED, OP_TERMINAL
from .llm import RuntimeCaller
from .views import build_view


def check_ledger_integrity(records: list) -> list:
    """Everything the ledger must satisfy on its own terms.  Returns the
    list of problems; empty means it is internally consistent."""
    problems = []
    seqs = set()
    last_seq = None
    last_t = None
    sealed = False
    for r in records:
        seq = r.get("seq")
        if not isinstance(seq, int):
            problems.append(f"record {r.get('op')!r} has a non-integer seq")
            continue
        if last_seq is not None and seq != last_seq + 1:
            problems.append(f"seq {seq} does not follow {last_seq}")
        last_seq = seq
        seqs.add(seq)
        try:
            t = parse_iso(r["t"])
        except Exception:
            problems.append(f"seq {seq} has an unreadable timestamp "
                            f"{r.get('t')!r}")
        else:
            if last_t is not None and t < last_t:
                problems.append(f"seq {seq} moves time backwards")
            last_t = t
        cause = r.get("cause")
        if sealed:
            if cause is None:
                problems.append(f"seq {seq} ({r['op']}) has no cause after "
                                f"genesis was sealed")
            elif cause not in seqs:
                problems.append(f"seq {seq} names a cause {cause} that does "
                                f"not exist before it")
        if r.get("op") == "genesis.sealed":
            sealed = True

    by_event = {r["data"]["event_id"]: r["data"]
                for r in records if r.get("op") == OP_EVENT}
    for r in records:
        if r.get("op") == OP_OBSERVED:
            d = r["data"]
            ev = by_event.get(d.get("event_id"))
            if ev is None:
                problems.append(f"seq {r['seq']} records an observation of "
                                f"{d.get('event_id')!r}, which does not exist")
            elif d.get("actor") not in ev.get("for", []):
                problems.append(
                    f"seq {r['seq']} records {d.get('actor')!r} observing "
                    f"{d.get('event_id')}, which never reached them")
        elif r.get("op") == OP_TERMINAL:
            d = r["data"]
            for eid in d.get("supporting_event_ids") or []:
                if eid not in by_event:
                    problems.append(
                        f"seq {r['seq']} cites {eid!r}, which is not a "
                        f"committed event")
            if d.get("status") == "YES" and not d.get("supporting_event_ids"):
                problems.append(f"seq {r['seq']} is a YES citing nothing")
    return problems


def _projection(world) -> dict:
    """Everything a replay must reproduce, in comparable form."""
    journal = Journal(world)
    return {
        "events": journal.events(),
        "observations": [r["data"] for r in world.records
                         if r["op"] == OP_OBSERVED],
        "terminals": [r["data"] for r in world.records
                      if r["op"] == OP_TERMINAL],
        "views": {aid: build_view(world, journal, aid)
                  for aid in sorted(world.actors)},
        "memories": {aid: [{"t": m.t.isoformat(), "kind": m.kind,
                            "content": m.content,
                            "source": getattr(m, "source", None)}
                           for m in world.actors[aid].memories]
                     for aid in sorted(world.actors)},
        "state_hash": world.state_hash(),
        "now": world.clock.now.isoformat(),
    }


def replay_trajectory(records: list, *, live_world=None) -> dict:
    """Rebuild from the ledger alone and verify the reconstruction.

    ``records`` may come straight from a live world or be read back from
    ``ledger.jsonl``; reading it back from disk is the stronger proof and
    is what the CLI does.
    """
    calls_before = RuntimeCaller.total_calls
    # deep copy: the reconstruction must share no object with its subject,
    # or every comparison below would be an identity check
    own = copy.deepcopy(list(records))
    problems = check_ledger_integrity(own)
    world = World.from_records(own, live=True)
    mine = _projection(world)
    result = {
        "llm_calls": RuntimeCaller.total_calls - calls_before,
        "records_replayed": len(world.records),
        "event_ids": [e["event_id"] for e in mine["events"]],
        "event_order_hash": canonical_json(
            [e["event_id"] for e in mine["events"]]),
        "state_hash": mine["state_hash"],
        "terminal_status": (mine["terminals"][-1]["status"]
                            if mine["terminals"] else None),
        "terminal_support": (mine["terminals"][-1]["supporting_event_ids"]
                             if mine["terminals"] else []),
        "ledger_integrity": problems,
        "checked": {"records": len(world.records),
                    "events": len(mine["events"]),
                    "observations": len(mine["observations"]),
                    "terminal_checks": len(mine["terminals"]),
                    "actors": len(mine["views"]),
                    "memories": sum(len(v) for v in mine["memories"].values())},
    }
    # a verification that had nothing to verify says so
    vacuous = not (mine["events"] and mine["terminals"] and mine["views"])
    result["vacuous"] = vacuous
    if live_world is None:
        result["exact"] = None
        return result

    theirs = _projection(live_world)
    same = {name: canonical_json(mine[name]) == canonical_json(theirs[name])
            for name in ("events", "observations", "terminals", "views",
                         "memories")}
    result.update({
        # the whole ledger, record for record.  The kernel's state hash
        # covers reduced state only, and every record this runtime writes
        # is trace-only, so without this a judgment, a decision or a
        # scheduled event could be rewritten or dropped unnoticed.
        "records_match": (canonical_json(world.records)
                          == canonical_json(live_world.records)),
        "state_hash_matches": mine["state_hash"] == theirs["state_hash"],
        "event_ids_match": ([e["event_id"] for e in mine["events"]]
                            == [e["event_id"] for e in theirs["events"]]),
        "events_match": same["events"],
        "observations_match": same["observations"],
        "views_match": same["views"],
        "memories_match": same["memories"],
        "terminal_matches": same["terminals"],
        "clock_matches": mine["now"] == theirs["now"],
    })
    result["exact"] = bool(
        not vacuous and not problems and result["llm_calls"] == 0
        and all(result[k] for k in
                ("records_match", "state_hash_matches", "event_ids_match",
                 "events_match", "observations_match", "views_match",
                 "memories_match", "terminal_matches", "clock_matches")))
    return result
