"""Checkpoint/resume must be exactly equivalent to uninterrupted execution:
same ledger, same hashes, same terminal, same wakes/deliveries/completions --
nothing duplicated, nothing lost."""
import json

import pytest

from sworldmodel import Engine, Terminal, World, parse_iso, resume, save_checkpoint
from worlds import committee_world, email_world, factory_world

BUILDERS = {
    "email": email_world.build,
    "committee": committee_world.build,
    "factory": factory_world.build,
}


def run_uninterrupted(build):
    w, minds, t = build()
    out = Engine(w, minds, t).run()
    return w, out


def run_with_interruptions(build, every):
    w, minds, t = build()
    eng = Engine(w, minds, t)
    out = eng.run(stop_after_events=every)
    hops = 0
    while out.status == "paused":
        cp = save_checkpoint(eng.world)
        # a fresh engine, fresh minds: nothing survives except the checkpoint
        _, minds, t = build()
        eng = resume(cp, minds, t)
        out = eng.run(stop_after_events=every)
        hops += 1
        assert hops < 200
    return eng.world, out, hops


@pytest.mark.parametrize("name", list(BUILDERS))
@pytest.mark.parametrize("every", [1, 3, 7])
def test_resume_is_exactly_equivalent(name, every):
    build = BUILDERS[name]
    w_u, out_u = run_uninterrupted(build)
    w_r, out_r, hops = run_with_interruptions(build, every)
    assert hops >= 1
    assert json.dumps(w_r.records) == json.dumps(w_u.records)   # same ledger
    assert w_r.state_hash() == w_u.state_hash()                 # same state
    assert out_r.answer == out_u.answer                         # same terminal
    # same wakes, deliveries, completions -- none duplicated
    for op in ("actor.decision", "info.deliver", "info.notice", "event.fired"):
        assert len([r for r in w_r.records if r["op"] == op]) \
            == len([r for r in w_u.records if r["op"] == op])
    fired = [r["data"]["event"] for r in w_r.records if r["op"] == "event.fired"]
    assert len(fired) == len(set(fired))                        # each event once


@pytest.mark.parametrize("name", list(BUILDERS))
def test_replay_is_pure_reconstruction(name):
    w, out = run_uninterrupted(BUILDERS[name])
    replayed = World.from_records(w.records)   # zero mind/LLM calls by design
    assert replayed.state_hash() == w.state_hash()
    assert replayed.terminal_result == w.terminal_result
    # and replay itself is deterministic across repeated runs
    replayed2 = World.from_records(w.records)
    assert replayed2.state_hash() == replayed.state_hash()


def test_checkpoint_requires_settled_world_and_matching_hash():
    w, minds, t = factory_world.build()
    eng = Engine(w, minds, t)
    out = eng.run(stop_after_events=4)
    assert out.status == "paused"
    cp = save_checkpoint(eng.world)
    assert cp["state_hash"] == eng.world.state_hash()
    tampered = dict(cp, state_hash="0" * 64)
    _, minds2, t2 = factory_world.build()
    with pytest.raises(RuntimeError, match="hash"):
        resume(tampered, minds2, t2)


def test_checkpoint_detects_queue_divergence():
    w, minds, t = factory_world.build()
    eng = Engine(w, minds, t)
    eng.run(stop_after_events=4)
    cp = save_checkpoint(eng.world)
    # drop one pending scheduled-event record: state hashing cannot see it
    # (event.scheduled is a trace op), but the queue verification must
    recs = list(cp["records"])
    fired = {r["data"].get("event") for r in recs if r["op"] == "event.fired"}
    idx = next(i for i in range(len(recs) - 1)
               if recs[i]["op"] == "event.scheduled" and recs[i]["seq"] not in fired)
    del recs[idx]
    tampered = dict(cp, records=recs)
    _, m2, t2 = factory_world.build()
    with pytest.raises(RuntimeError, match="queue"):
        resume(tampered, m2, t2)


def test_resume_with_already_elapsed_cutoff_terminates_cleanly():
    # a resumed segment that processes zero events must still write a valid,
    # caused terminal record
    w, minds, t = email_world.build()
    eng = Engine(w, minds, t)
    out = eng.run(stop_after_events=2)
    assert out.status == "paused"
    cp = save_checkpoint(eng.world)
    _, m2, _ = email_world.build()
    early = Terminal(t.question, parse_iso(cp["now"]), t.evaluate)
    eng2 = resume(cp, m2, early)
    out2 = eng2.run()
    assert out2.status == "cutoff" and out2.answer["answer"] == "no"
    term = next(r for r in eng2.world.records if r["op"] == "terminal")
    assert term["cause"] is not None


def test_wire_hook_may_not_write_records():
    w, minds, t = email_world.build()
    eng = Engine(w, minds, t)
    out = eng.run(stop_after_events=2)
    cp = save_checkpoint(eng.world)
    _, minds2, t2 = email_world.build()

    def bad_wire(world):
        world.apply("fact.set", {"key": "sneaky", "value": 1}, cause=1)

    with pytest.raises(RuntimeError, match="must not write"):
        resume(cp, minds2, t2, wire=bad_wire)
