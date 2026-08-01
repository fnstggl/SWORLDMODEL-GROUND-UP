"""Complete under-the-hood artifacts for a live run.

Every prompt, raw response, parsed response, validation result, retry,
simulated time, wall time, token count, causal trigger and committed
record is written out.  Only the model's required structured answer and
its brief decision/judgment summary are recorded -- no hidden reasoning is
requested or stored.
"""
from __future__ import annotations

import hashlib
import json
import os

from sworldmodel import canonical_json

from .adapter import CONSUMED_FIELDS


class Trace:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def record(self, kind: str, **data) -> None:
        self.entries.append(dict(data, kind=kind))

    def of(self, kind: str) -> list:
        return [e for e in self.entries if e["kind"] == kind]


def _write_jsonl(path, rows):
    # errors="replace": an artifact write happens after a whole paid-for
    # run, and must never be the thing that loses it
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        for r in rows:
            f.write(canonical_json(r) + "\n")


def write_artifacts(out_dir: str, *, scene: dict, world, journal, bindings,
                    trajectory, caller, trace: Trace, replay: dict,
                    question: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    j = lambda name, obj: open(os.path.join(out_dir, name), "w",
                               encoding="utf-8", errors="replace").write(
                                   json.dumps(obj, indent=1, default=str))

    # the ledger is the authoritative artifact, so it is written FIRST:
    # nothing later may be able to lose it
    _write_jsonl(os.path.join(out_dir, "ledger.jsonl"), world.records)
    # ... and a digest OF it, so that "this run replayed exactly" is a
    # property anyone can re-derive from disk rather than a boolean sitting
    # in a file beside the ledger.  A reviewer rewrote every event
    # description and every terminal record in a run and the checker still
    # reported exact=True, because no semantic op has a kernel reducer and
    # the state hash therefore does not cover the journal at all.
    with open(os.path.join(out_dir, "ledger_digest.txt"), "w") as f:
        f.write(hashlib.sha256(
            canonical_json(world.records).encode()).hexdigest() + "\n")
    j("compiled_scene.json", scene)
    j("initial_actor_states.json",
      {aid: {"name": st.name,
             "private_context": journal.profiles().get(aid, "")}
       for aid, st in sorted(world.actors.items())})
    _write_jsonl(os.path.join(out_dir, "journal.jsonl"), journal.events())
    _write_jsonl(os.path.join(out_dir, "event_queue.jsonl"),
                 [{"seq": r["seq"], "t": r["data"]["t"],
                   "kind": r["data"]["kind"], "data": r["data"]["data"],
                   "cause": r["cause"]}
                  for r in world.records if r["op"] == "event.scheduled"])
    _write_jsonl(os.path.join(out_dir, "actor_views.jsonl"),
                 trace.of("actor_view"))
    _write_jsonl(os.path.join(out_dir, "actor_exchanges.jsonl"),
                 [c for c in caller.calls if c["role"] == "actor"])
    _write_jsonl(os.path.join(out_dir, "actor_memory_updates.jsonl"),
                 [{"actor": r["data"]["actor"], "t": r["t"],
                   "content": r["data"]["content"],
                   "source": r["data"].get("source", "")}
                  for r in world.records
                  if r["op"] == "actor.memory"
                  and r["data"].get("kind") == "private"])
    _write_jsonl(os.path.join(out_dir, "world_exchanges.jsonl"),
                 [c for c in caller.calls if c["role"] == "world"])
    _write_jsonl(os.path.join(out_dir, "world_judgments.jsonl"),
                 trace.of("world_judgment"))
    _write_jsonl(os.path.join(out_dir, "terminal_checks.jsonl"),
                 trace.of("terminal_check"))
    _write_jsonl(os.path.join(out_dir, "terminal_verifications.jsonl"),
                 trace.of("terminal_verification"))
    _write_jsonl(os.path.join(out_dir, "actor_continuity_reviews.jsonl"),
                 trace.of("continuity_review") + trace.of(
                     "actor_response_rejected"))
    # what code refused, and why -- there is no semantic gate left to log
    _write_jsonl(os.path.join(out_dir, "structural_refusals.jsonl"),
                 trace.of("restatement_refused")
                 + trace.of("choice_returned_to_its_owner"))
    # Every place code overruled the model.  These were emitted into the
    # trace and persisted nowhere, which is precisely backwards: they are
    # the moments a reader most needs, because they are where the record
    # stopped being the model's judgment.  A run whose decisive act was
    # proposed and refused twice looked, in the artifacts, exactly like a
    # run in which the world judged that nothing happened.
    _write_jsonl(os.path.join(out_dir, "code_overrides.jsonl"),
                 [dict(e, override=e["kind"]) for k in
                  ("event_abandoned", "duplicate_event_dropped",
                   "duration_floored", "actor_turn_abandoned",
                   "group_observation_split", "progression_skipped",
                   "restatement_refused", "ordered_after_earlier_attempt",
                   "choice_returned_to_its_owner", "wake_beyond_cutoff")
                  for e in trace.of(k)])
    _write_jsonl(os.path.join(out_dir, "grounded_wakes.jsonl"),
                 trace.of("wake_scheduled"))
    _write_jsonl(os.path.join(out_dir, "review_exchanges.jsonl"),
                 [c for c in caller.calls
                  if c["role"] in ("continuity", "verifier")])
    j("compile_runtime_bindings.json",
      {k: v for k, v in bindings.items() if k != "actor_ids"} |
      {"actor_ids": bindings.get("actor_ids", {}),
       "consumed_fields": list(CONSUMED_FIELDS),
       "resolution_reaches": "the read-only judge and verifier only"})
    j("terminal_result.json",
      {"question": question, "trajectory": trajectory.to_dict(),
       "answer": trajectory.answer, "reason": trajectory.reason})
    j("runtime_metrics.json",
      dict(caller.metrics(), **trajectory.to_dict(),
           committed_events=len(journal.events()),
           ledger_records=len(world.records)))
    if replay is not None:
        j("replay_verification.json", replay)
    with open(os.path.join(out_dir, "trajectory.md"), "w",
              encoding="utf-8", errors="replace") as f:
        f.write(render_trajectory(question, journal, trace, trajectory))


def read_ledger(out_dir: str) -> list:
    """The persisted ledger, read back from disk.

    Replaying what was actually written is the real proof; replaying the
    live world's own in-memory list only proves the process can talk to
    itself.
    """
    path = os.path.join(out_dir, "ledger.jsonl")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_replay_verification(out_dir: str, verification: dict) -> None:
    with open(os.path.join(out_dir, "replay_verification.json"), "w",
              encoding="utf-8", errors="replace") as f:
        f.write(json.dumps(verification, indent=1, default=str))


def render_trajectory(question, journal, trace: Trace, trajectory) -> str:
    """Chronological, readable: trigger, availability, observation, actor
    view, decision, intention, world judgment, committed event, private
    updates, wakes, terminal status."""
    out = [f"# Trajectory\n", f"**Question:** {question}\n",
           f"**Result:** {trajectory.status} — "
           f"{(trajectory.answer or {}).get('status', 'n/a')}\n"]
    for e in trace.entries:
        k = e["kind"]
        if k == "committed_event":
            who = ", ".join(e["for"]) or "no one"
            seen = "OBSERVED by them" if e["observed"] \
                else "AVAILABLE but NOT observed"
            out.append(f"\n---\n\n## {e['t']} — committed event "
                       f"`{e['event_id']}`\n\n{e['description']}\n\n"
                       f"- available to: {who}\n- {seen}\n"
                       f"- source: {e['source']}\n")
        elif k == "world_judgment":
            ev = e.get("event")
            out.append(f"\n**World judgment** ({e['trigger']}) at {e['t']}\n\n"
                       f"> trigger: {e['trigger_text']}\n>\n"
                       f"> {e['judgment']}\n")
            if ev:
                out.append(f"- proposes: {ev['description']} "
                           f"(for {ev.get('for')}, observed="
                           f"{ev.get('observed')}, after {ev.get('after')})\n")
            else:
                out.append("- proposes: (no concrete event yet)\n")
        elif k == "event_abandoned":
            # NOT the same as "nothing happened": the world said something
            # did, twice, and was overruled.  Rendering the two alike is
            # how a NO produced by a refusal reads as a NO produced by a
            # quiet afternoon.
            out.append(f"\n**Proposed and refused twice** at {e['t']} — "
                       f"nothing was committed\n\n"
                       f"> would have been: {e['rejected']}\n>\n"
                       f"> refused because: {e['reason']}\n")
            for w in e.get("wakes") or []:
                out.append(f"- wake {w['actor']} after {w['after']}: "
                           f"{w['reason']}\n")
        elif k == "item_observed":
            out.append(f"\n*`{e['event_id']}` is now observed by "
                       f"{e['actor']} (attention arrived via "
                       f"`{e['via']}`)*\n")
        elif k == "actor_view":
            out.append(f"\n<details><summary>what {e['actor']} could see at "
                       f"{e['t']} (their entire prompt)</summary>\n\n"
                       f"```\n{e['rendered']}\n```\n\n</details>\n")
        elif k == "actor_decision":
            out.append(f"\n**{e['actor']} decides** at {e['t']}\n\n"
                       f"> {e['decision']}\n")
            for i in e["intentions"]:
                out.append(f"- attempts: {i}\n")
            for u in e["private_updates"]:
                out.append(f"- privately: {u}\n")
        elif k == "terminal_check":
            out.append(f"\n*terminal check at {e['t']}: {e['status']} — "
                       f"{e['explanation']}*\n")
        elif k == "event_beyond_cutoff":
            out.append(f"\n*(a proposed event at {e['due']} falls beyond the "
                       f"cutoff and was not scheduled)*\n")
    return "".join(out)
