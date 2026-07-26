"""Under-the-hood artifacts: every run is fully inspectable.

Everything here is a projection of the single append-only ledger -- there is
no second source of truth.  For each world we emit the initial snapshot, the
full ledger, per-concern views (wakes, actor views, intentions, rejections,
action/information/process lifecycles, state transitions), checkpoints,
terminal result with producer lineage, replay verification hashes, runtime
metrics and the hand-written reality-fidelity review.
"""
from __future__ import annotations

import json
import os

from .world import World, canonical_json

WAKE_OPS = {"actor.decision", "actor.wake_deferred", "actor.wake"}
REJECT_OPS = {"intention.rejected", "mind.violation"}
ACTION_OPS = {"action.define", "action.propose", "action.state",
              "action.start_refused", "action.complete_refused"}
INFO_OPS = {"info.create", "info.send", "info.deliver", "info.notice",
            "info.noticing_unsupported"}
STATE_OPS = {"fact.set", "entity.add", "entity.set", "resource.set",
             "resource.adjust", "resource.transfer", "relationship.set",
             "actor.add", "actor.belief", "actor.plan", "actor.emotion",
             "actor.physical", "actor.relationship", "actor.commit",
             "actor.commitment_resolved", "actor.memory", "actor.reconsider",
             "actor.ongoing"}
PROCESS_OPS = {"process.add", "process.active", "process.rate",
               "process.accrue", "watch.add", "watch.fired", "watch.premature"}


def _write_jsonl(path: str, rows: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(canonical_json(row) + "\n")


def _write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


def write_artifacts(outdir: str, world: World, outcome, review_md: str,
                    checkpoints: list | None = None, wall_ms: float = 0.0,
                    deterministic_repeat: bool | None = None) -> dict:
    os.makedirs(outdir, exist_ok=True)
    recs = world.records

    sealed_idx = next(i for i, r in enumerate(recs) if r["op"] == "genesis.sealed")
    initial = World.from_records(recs[:sealed_idx + 1])
    _write_json(os.path.join(outdir, "initial_world.json"), initial.snapshot())

    _write_jsonl(os.path.join(outdir, "event_ledger.jsonl"), recs)
    _write_jsonl(os.path.join(outdir, "actor_wakes.jsonl"),
                 [r for r in recs if r["op"] in WAKE_OPS])
    _write_jsonl(os.path.join(outdir, "actor_views.jsonl"),
                 [r for r in recs if r["op"] in ("actor.view", "mind.exchange")])
    _write_jsonl(os.path.join(outdir, "intentions.jsonl"),
                 [r for r in recs if r["op"] == "action.propose"])
    _write_jsonl(os.path.join(outdir, "intention_rejections.jsonl"),
                 [r for r in recs if r["op"] in REJECT_OPS])
    _write_jsonl(os.path.join(outdir, "action_lifecycle.jsonl"),
                 [r for r in recs if r["op"] in ACTION_OPS])
    _write_jsonl(os.path.join(outdir, "information_lifecycle.jsonl"),
                 [r for r in recs if r["op"] in INFO_OPS])
    _write_jsonl(os.path.join(outdir, "state_transitions.jsonl"),
                 [r for r in recs if r["op"] in STATE_OPS])
    _write_jsonl(os.path.join(outdir, "continuous_process_transitions.jsonl"),
                 [r for r in recs if r["op"] in PROCESS_OPS])
    _write_jsonl(os.path.join(outdir, "checkpoints.jsonl"), checkpoints or [])

    terminal_rec = next((r for r in recs if r["op"] == "terminal"), None)
    _write_json(os.path.join(outdir, "terminal_result.json"), {
        "question": world.terminal_result["question"] if world.terminal_result else None,
        "status": world.terminal_result["status"] if world.terminal_result else None,
        "answer": world.terminal_result["answer"] if world.terminal_result else None,
        "at": world.terminal_result["at"] if world.terminal_result else None,
        "producer_lineage": (world.lineage(terminal_rec["seq"])
                             if terminal_rec else []),
    })

    replayed = World.from_records(recs)   # zero actor/LLM calls
    verification = {
        "initial_state_hash": initial.state_hash(),
        "original_final_hash": world.state_hash(),
        "replayed_final_hash": replayed.state_hash(),
        "final_hash_match": replayed.state_hash() == world.state_hash(),
        "terminal_match": replayed.terminal_result == world.terminal_result,
        "deterministic_repeat_run": deterministic_repeat,
        "ledger_records": len(recs),
    }
    _write_json(os.path.join(outdir, "replay_verification.json"), verification)

    _write_json(os.path.join(outdir, "runtime_metrics.json"), {
        **outcome.metrics, "ledger_records": len(recs),
        "wall_ms": round(wall_ms, 1),
        "pending_events_at_end": len(world.queue),
    })

    with open(os.path.join(outdir, "reality_fidelity_review.md"), "w",
              encoding="utf-8") as f:
        f.write(review_md)
    return verification
