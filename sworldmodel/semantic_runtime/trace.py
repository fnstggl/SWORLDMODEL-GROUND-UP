"""Complete under-the-hood artifacts for a live run.

Every prompt, raw response, parsed response, validation result, retry,
simulated time, wall time, token count, causal trigger and committed
record is written out.  Only the model's required structured answer and
its brief decision/judgment summary are recorded -- no hidden reasoning is
requested or stored.
"""
from __future__ import annotations

import json
import os

from sworldmodel import canonical_json


class Trace:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def record(self, kind: str, **data) -> None:
        self.entries.append(dict(data, kind=kind))

    def of(self, kind: str) -> list:
        return [e for e in self.entries if e["kind"] == kind]


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(canonical_json(r) + "\n")


def write_artifacts(out_dir: str, *, scene: dict, world, journal, bindings,
                    trajectory, caller, trace: Trace, replay: dict,
                    question: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    j = lambda name, obj: open(os.path.join(out_dir, name), "w",
                               encoding="utf-8").write(
                                   json.dumps(obj, indent=1, default=str))

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
    j("terminal_result.json",
      {"question": question, "trajectory": trajectory.to_dict(),
       "answer": trajectory.answer, "reason": trajectory.reason})
    j("runtime_metrics.json",
      dict(caller.metrics(), **trajectory.to_dict(),
           committed_events=len(journal.events()),
           ledger_records=len(world.records)))
    j("replay_verification.json", replay)
    with open(os.path.join(out_dir, "trajectory.md"), "w",
              encoding="utf-8") as f:
        f.write(render_trajectory(question, journal, trace, trajectory))
    _write_jsonl(os.path.join(out_dir, "ledger.jsonl"), world.records)


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
