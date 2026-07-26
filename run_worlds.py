"""Run the three hand-authored worlds (and, if DEEPSEEK_API_KEY is set, the
Phase B world with one live LLM actor), verify determinism / replay /
checkpoint-resume, and emit the complete under-the-hood artifacts to
artifacts/<world>/.

Usage:  python3 run_worlds.py [--skip-llm]
"""
import json
import os
import sys
import time as wallclock

from sworldmodel import Engine, World, fmt_local, parse_iso, resume, save_checkpoint
from sworldmodel.artifacts import write_artifacts
from worlds import committee_world, email_world, factory_world

HERE = os.path.dirname(os.path.abspath(__file__))


def narrative(world, tz):
    """Print the causal timeline in local wall time."""
    interesting = {"event.fired", "actor.decision", "action.state",
                   "info.notice", "intention.rejected", "actor.wake_deferred",
                   "terminal"}
    for r in world.records:
        if r["op"] not in interesting:
            continue
        t = fmt_local(parse_iso(r["t"]), tz)
        d = r["data"]
        if r["op"] == "event.fired" and d["kind"] not in ("wake.actor",):
            print(f"  {t}  EVENT {d['kind']}  {json.dumps(d.get('data', {}))[:90]}")
        elif r["op"] == "actor.decision":
            why = ",".join(x["kind"] for x in d["reasons"])
            print(f"  {t}  {d['actor'].upper()} decides ({why}): {d['note'][:80]}"
                  f"  -> {d['intentions'] or 'no action'}")
        elif r["op"] == "action.state" and d["state"] in ("started", "completed",
                                                          "failed", "interrupted"):
            extra = d.get("reason", "")
            print(f"  {t}  action {d['id']} {d['state']} {extra[:60]}")
        elif r["op"] == "info.notice":
            print(f"  {t}  {d['actor']} notices {d['id']}")
        elif r["op"] == "actor.wake_deferred":
            print(f"  {t}  wake for {d['actor']} DEFERRED: {d['denial_reason']}")
        elif r["op"] == "intention.rejected":
            print(f"  {t}  REJECTED {d['actor']}:{d['verb']} -- {d['reason'][:70]}")
        elif r["op"] == "terminal":
            print(f"  {t}  TERMINAL [{d['status']}]: {json.dumps(d['answer'])[:120]}")


def run_world(name, build, tz, review, minds_override=None, check_resume=True):
    print(f"\n=== {name} ===")
    t0 = wallclock.monotonic()
    w, minds, term = build()
    if minds_override:
        minds.update(minds_override())
    out = Engine(w, minds, term).run()
    wall_ms = (wallclock.monotonic() - t0) * 1000
    narrative(w, tz)

    deterministic = None
    checkpoints = []
    if minds_override is None:   # scripted worlds: prove determinism + resume
        w2, minds2, term2 = build()
        Engine(w2, minds2, term2).run()
        deterministic = json.dumps(w.records) == json.dumps(w2.records)

        w3, minds3, term3 = build()
        eng = Engine(w3, minds3, term3)
        o3 = eng.run(stop_after_events=10)
        while o3.status == "paused":
            cp = save_checkpoint(eng.world)
            checkpoints.append({"at_ledger_seq": cp["ledger_position"],
                                "now": cp["now"], "state_hash": cp["state_hash"]})
            _, mindsN, termN = build()
            eng = resume(cp, mindsN, termN)
            o3 = eng.run(stop_after_events=10)
        resume_ok = (json.dumps(eng.world.records) == json.dumps(w.records)
                     and eng.world.state_hash() == w.state_hash())
        print(f"  [verify] deterministic={deterministic} "
              f"resume_equivalent={resume_ok} ({len(checkpoints)} checkpoints)")
        assert deterministic and resume_ok

    outdir = os.path.join(HERE, "artifacts", name)
    verification = write_artifacts(outdir, w, out, review,
                                   checkpoints=checkpoints, wall_ms=wall_ms,
                                   deterministic_repeat=deterministic)
    print(f"  [verify] replay hash match={verification['final_hash_match']} "
          f"terminal match={verification['terminal_match']}")
    assert verification["final_hash_match"] and verification["terminal_match"]
    print(f"  artifacts -> artifacts/{name}/")
    return out


PHASE_B_REVIEW = """# Reality-fidelity review -- Phase B (one live LLM actor)

Bob is played by deepseek-chat through the exact Mind interface the scripted
actors use.  The model receives only Bob's rendered local view (his identity,
beliefs, memories, noticed messages and the authoritative time context) and
returns JSON: intentions, private-state updates about himself, optional
future wake.  Structurally it holds no reference to the world, clock, queue,
terminal or other actors; everything it returns passes kernel validation
(hostile-output tests prove forbidden updates are recorded as violations and
skipped, unknown verbs are rejected, shared state stays untouched).

Observed live behavior: Bob noticed Alice's email Monday 09:00 Pacific (the
kernel decided when he could notice it -- the model was never asked to invent
time), decided to reply, composed for a self-chosen realistic duration, and
his reply's content came from HIS OWN belief (the $4.2M he locked in March),
not from any world fact he couldn't see.  Alice -- still scripted -- noticed
the reply on her half-hour cadence and interpreted it into her belief; the
terminal resolved mechanically from that belief record.

Honest limitations:
- One live actor only (by design of this step); live-vs-live dynamics are
  untested here.
- The model is prompted for temperature-0 JSON; richer free-form deliberation
  (drafting, hesitating, multitasking) is not yet elicited.
- Replay never calls the model (exchanges are in the ledger), but a live
  RE-RUN is not bit-deterministic: the API may answer differently. Replay
  determinism and run determinism are different guarantees; only the first
  is claimed for Phase B.
"""


def main():
    skip_llm = "--skip-llm" in sys.argv
    run_world("email", email_world.build, "America/New_York",
              email_world.REVIEW)
    run_world("committee", committee_world.build, "America/Mexico_City",
              committee_world.REVIEW)
    run_world("factory", factory_world.build, "America/Chicago",
              factory_world.REVIEW)

    if skip_llm or not os.environ.get("DEEPSEEK_API_KEY"):
        print("\n[phase B] skipped (no DEEPSEEK_API_KEY or --skip-llm)")
        return

    from sworldmodel.llm_mind import DeepseekMind

    def llm_minds():
        return {"bob": DeepseekMind(
            "bob", "Bob Okafor",
            persona_brief="You are Bob Okafor, finance lead on the West "
                          "Coast. You personally locked the final Q2 "
                          "pipeline total of $4.2M on March 3. Alice is a "
                          "trusted colleague; you answer colleagues promptly "
                          "once you see their request.")}

    run_world("phase_b_email_llm", email_world.build, "America/New_York",
              PHASE_B_REVIEW, minds_override=llm_minds)


if __name__ == "__main__":
    main()
