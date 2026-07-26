"""Render every run artifact into ONE canonical, time-ordered Markdown trace.

The ledger is the single source of truth and is already in causal/time order
(seq is monotonic, timestamps non-decreasing).  Every other .jsonl artifact is
a projection of it, so the merged stream below annotates each record with the
artifact streams it belongs to -- nothing is invented, nothing is reordered.

Usage:
  python3 make_trace.py            -> writes RUN_TRACE.md (full, verbatim JSON)
  python3 make_trace.py --compact  -> prints the compact stream to stdout
"""
import json
import os
import sys

from sworldmodel import fmt_local, parse_iso

INLINE_BODIES = True

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "artifacts")

# run order, and the local time zone each world is narrated in
WORLDS = [
    ("email", "America/New_York",
     "Two-person message interaction (NY <-> LA, weekend + DST gap)"),
    ("committee", "America/Mexico_City",
     "Small group decision (data release -> briefing -> motion -> votes)"),
    ("factory", "America/Chicago",
     "Operational process with quantities (shifts, threshold, transit)"),
    ("phase_b_email_llm", "America/New_York",
     "Phase B: same world, Bob played by a live Deepseek-backed mind"),
]

# which projection artifact each op appears in (mirrors sworldmodel/artifacts.py)
STREAMS = {
    "actor.decision": "wakes", "actor.wake_deferred": "wakes", "actor.wake": "wakes",
    "actor.view": "views", "mind.exchange": "views",
    "action.propose": "intentions+actions",
    "intention.rejected": "rejections", "mind.violation": "rejections",
    "action.define": "actions", "action.state": "actions",
    "action.start_refused": "actions", "action.complete_refused": "actions",
    "info.create": "info", "info.send": "info", "info.deliver": "info",
    "info.notice": "info", "info.noticing_unsupported": "info",
    "info.notice_skipped": "info",
    "fact.set": "state", "entity.add": "state", "entity.set": "state",
    "resource.set": "state", "resource.adjust": "state",
    "resource.transfer": "state", "relationship.set": "state",
    "actor.add": "state", "actor.belief": "state", "actor.plan": "state",
    "actor.emotion": "state", "actor.physical": "state",
    "actor.relationship": "state", "actor.commit": "state",
    "actor.commitment_resolved": "state", "actor.memory": "state",
    "actor.reconsider": "state", "actor.ongoing": "state",
    "process.add": "process", "process.active": "process",
    "process.rate": "process", "process.accrue": "process",
    "watch.add": "process", "watch.fired": "process", "watch.premature": "process",
}

FILES = ["initial_world.json", "event_ledger.jsonl", "actor_wakes.jsonl",
         "actor_views.jsonl", "intentions.jsonl", "intention_rejections.jsonl",
         "action_lifecycle.jsonl", "information_lifecycle.jsonl",
         "state_transitions.jsonl", "continuous_process_transitions.jsonl",
         "checkpoints.jsonl", "terminal_result.json",
         "replay_verification.json", "runtime_metrics.json"]


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def summarize(rec, compact):
    """One-line human summary of a record's payload."""
    op, d = rec["op"], rec["data"]
    if op == "world.genesis":
        return f"start={d['start']} schema={d['schema']}"
    if op == "genesis.sealed":
        return "world construction complete; every later record needs a cause"
    if op == "event.scheduled":
        return f"[{d['kind']}] at {d['t']} depth={d['depth']}"
    if op == "event.fired":
        return f"[{d['kind']}]"
    if op == "event.cancelled":
        return f"event {d['event']}: {d['reason']}"
    if op == "channel.add":
        lat = d["latency"]
        return (f"{d['name']}: latency {lat['seconds']}s "
                f"({lat['basis']}: {lat['note']})")
    if op == "action.define":
        return f"{d['verb']} -- {len(d.get('conditions', []))} conditions, " \
               f"{len(d.get('effects', []))} effects"
    if op == "actor.add":
        return f"{d['id']} ({d['name']}, {d['role']}, {d['tz']})"
    if op == "actor.belief":
        return f"{d['actor']}[{d['topic']}] = {d['statement']!r} (basis: {d['basis']})"
    if op == "actor.plan":
        return f"{d['actor']}: {d['plan']!r}"
    if op == "actor.emotion":
        return f"{d['actor']}: {d['statement']!r}"
    if op == "actor.memory":
        return f"{d['actor']} <- ({d['kind']}) {d['content']!r}"
    if op == "actor.commit":
        return f"{d['actor']} commits {d['id']}: {d['what']!r} at={d.get('at')}"
    if op == "actor.commitment_resolved":
        return f"{d['actor']} resolved {d['id']}"
    if op == "actor.ongoing":
        return f"{d['actor']} ongoing -> {d['action']}"
    if op == "actor.view":
        head = (f"{d['actor']} shown world v{d['world_version']}, reasons="
                f"{[r['kind'] for r in d['reasons']]}")
        if compact and INLINE_BODIES:
            # the rendered view IS the actor's entire epistemic position --
            # show it indented, since information locality lives or dies here
            body = d["rendered"].replace("\n", "\n      ")
            return head + "\n\n      ```\n      " + body + "\n      ```"
        return head
    if op == "actor.decision":
        return (f"{d['actor']} because {[r['kind'] for r in d['reasons']]} -> "
                f"intentions={d['intentions']} | {d['note']!r}")
    if op == "actor.wake_deferred":
        return (f"{d['actor']} wake QUEUED ({d['kind']}): {d['denial_reason']}; "
                f"reconsider at {d['reconsider_at']}")
    if op == "mind.exchange":
        head = (f"{d['actor']} LLM exchange parsed={d['parsed']} "
                f"attempt={d.get('attempt')}")
        if compact and INLINE_BODIES:
            resp = d.get("response", "")
            return (head + "\n\n      **raw model response:**\n      ```json\n      "
                    + resp.replace("\n", "\n      ") + "\n      ```")
        return head
    if op == "mind.violation":
        return f"{d['actor']} REFUSED: {d['reason']}"
    if op == "intention.rejected":
        return f"{d['actor']}:{d['verb']} REJECTED -- {d['reason']}"
    if op == "action.propose":
        dur = d.get("duration")
        dtxt = (f"{dur['seconds']}s ({dur['basis']})" if dur
                else f"completes_when {d.get('completes_when')}")
        return f"{d['id']} {d['actor']}:{d['verb']} {d.get('params')} dur={dtxt} " \
               f"based_on_v{d['based_on_version']}"
    if op == "action.state":
        extra = ""
        for k in ("reason", "completes_at", "watch", "observed_version"):
            if k in d:
                extra += f" {k}={d[k]}"
        return f"{d['id']} -> {d['state']}{extra}"
    if op == "info.create":
        return f"{d['id']} by {d['author']}: {d['content']!r} data={d.get('data')}"
    if op == "info.send":
        return f"{d['id']} -> {d['to']} via {d['channel']}"
    if op == "info.deliver":
        return f"{d['id']} DELIVERED to {d['to']} via {d['channel']}"
    if op == "info.notice":
        return f"{d['id']} NOTICED by {d['actor']}"
    if op == "info.noticing_unsupported":
        return f"{d['id']} for {d['actor']}: {d['note']}"
    if op == "fact.set":
        return f"{d['key']} = {d['value']!r}"
    if op == "entity.add":
        return f"{d['id']} ({d.get('kind')}) {d.get('properties')}"
    if op == "resource.set":
        return f"{d['holder']}:{d['name']} = {d['amount']}"
    if op == "resource.adjust":
        return f"{d['holder']}:{d['name']} {d['delta']:+g}"
    if op == "resource.transfer":
        return f"{d['amount']:g} {d['name']}: {d['from_holder']} -> {d['to_holder']}"
    if op == "process.add":
        return (f"{d['id']}: {d['holder']}:{d['resource']} @ {d['rate_per_hour']}/h "
                f"active={d.get('active')} ({d['basis']}: {d['note']})")
    if op == "process.active":
        return f"{d['id']} active={d['active']}"
    if op == "process.accrue":
        return (f"{d['id']} +{d['amount']:g} over {d['from']} -> {d['to']}"
                + (" [clamped]" if d.get("clamped") else ""))
    if op == "watch.add":
        return (f"{d['id']}: {d['holder']}:{d['resource']} >= {d['level']} "
                f"-> {d.get('on_reach')} ({d['basis']})")
    if op == "watch.fired":
        return f"{d['id']} threshold reached"
    if op == "watch.premature":
        return f"{d['id']} fired early (have {d['amount']:g}, need {d['level']})"
    if op == "terminal":
        a = d["answer"]
        return f"[{d['status']}] {a.get('answer')!r} -- {a.get('detail','')}"
    return json.dumps(d, sort_keys=True)[:200]


def render_world(name, tz, blurb, compact):
    d = os.path.join(ART, name)
    ledger = load_jsonl(os.path.join(d, "event_ledger.jsonl"))
    terminal = load_json(os.path.join(d, "terminal_result.json"))
    verify = load_json(os.path.join(d, "replay_verification.json"))
    metrics = load_json(os.path.join(d, "runtime_metrics.json"))
    checkpoints = load_jsonl(os.path.join(d, "checkpoints.jsonl"))
    initial = load_json(os.path.join(d, "initial_world.json"))

    out = []
    w = out.append
    w(f"\n\n# WORLD: {name}\n")
    w(f"*{blurb}*\n")
    w(f"**Question:** {terminal['question']}\n")
    w(f"**Answer:** `{json.dumps(terminal['answer'].get('answer'))}` "
      f"({terminal['status']}) — {terminal['answer'].get('detail','')}\n")
    w(f"**Verification:** replay final hash `{verify['replayed_final_hash'][:16]}…` "
      f"== original `{verify['original_final_hash'][:16]}…` → "
      f"**{verify['final_hash_match']}**; terminal match "
      f"**{verify['terminal_match']}**; deterministic repeat run: "
      f"**{verify['deterministic_repeat_run']}**\n")
    w(f"**Metrics:** {json.dumps(metrics, sort_keys=True)}\n")

    # ---- initial world -------------------------------------------------
    w(f"\n## {name} — initial_world.json (state at genesis seal)\n")
    if compact:
        w("```json")
        w(json.dumps({k: initial[k] for k in
                      ("start", "now", "version", "channels", "resources",
                       "facts", "entities") if k in initial},
                     indent=2, sort_keys=True))
        w("```")
        w(f"\n*Actors at genesis:* "
          + ", ".join(f"`{a}`" for a in sorted(initial.get("actors", {}))))
        w(f"\n*Pre-scheduled events:* "
          + str(len(initial.get("scheduled_events", []))) + " on the calendar\n")
        for ev in initial.get("scheduled_events", []):
            w(f"- seq {ev['seq']}: **{ev['kind']}** at {ev['t']} "
              f"({fmt_local(parse_iso(ev['t']), tz)})")
    else:
        w("```json")
        w(json.dumps(initial, indent=2, sort_keys=True))
        w("```")

    # ---- the canonical merged stream ------------------------------------
    w(f"\n## {name} — canonical time-ordered stream ({len(ledger)} records)\n")
    w("Every ledger record in causal order. `seq` = ledger position and event "
      "id; `cause` = the record that produced it; `streams` = which artifact "
      "projections contain it.\n")
    last_t = None
    for rec in ledger:
        t = rec["t"]
        if t != last_t:
            w(f"\n### ⏱ {fmt_local(parse_iso(t), tz)}  ·  `{t}`\n")
            last_t = t
        stream = STREAMS.get(rec["op"], "ledger-only")
        cause = rec["cause"] if rec["cause"] is not None else "—"
        w(f"- **`{rec['seq']:>3}`** `{rec['op']}` ← cause `{cause}` "
          f"· _{stream}_  \n  {summarize(rec, compact)}")
        if not compact:
            w(f"\n  ```json\n  " +
              json.dumps(rec, indent=2, sort_keys=True).replace("\n", "\n  ")
              + "\n  ```")

    # ---- checkpoints -----------------------------------------------------
    w(f"\n## {name} — checkpoints.jsonl ({len(checkpoints)} checkpoints)\n")
    if checkpoints:
        for cp in checkpoints:
            w(f"- ledger seq `{cp['at_ledger_seq']}` at `{cp['now']}` — "
              f"state hash `{cp['state_hash'][:16]}…`")
        w("\nEach checkpoint was resumed into a fresh engine with fresh minds; "
          "the resulting ledger was byte-identical to the uninterrupted run.")
    else:
        w("*(no checkpoints: the live-LLM run is not replayed through "
          "checkpoint/resume, since a re-run may legitimately differ)*")

    # ---- terminal, verification, metrics ---------------------------------
    w(f"\n## {name} — terminal_result.json (with full producer lineage)\n")
    if compact:
        # the lineage entries are verbatim copies of records already shown in
        # the stream above -- render them as the causal chain of seq numbers
        lean = {k: v for k, v in terminal.items() if k != "producer_lineage"}
        w("```json")
        w(json.dumps(lean, indent=2, sort_keys=True))
        w("```")
        chain = terminal.get("producer_lineage", [])
        w(f"\n**Producer lineage** ({len(chain)} records, newest first) — the "
          f"causal chain from the terminal back to genesis:\n")
        w("  " + "\n  ← ".join(
            f"`{e['seq']}` {e['op']}" if "seq" in e else "…truncated…"
            for e in chain))
    else:
        w("```json")
        w(json.dumps(terminal, indent=2, sort_keys=True))
        w("```")
    w(f"\n## {name} — replay_verification.json\n")
    w("```json")
    w(json.dumps(verify, indent=2, sort_keys=True))
    w("```")
    w(f"\n## {name} — runtime_metrics.json\n")
    w("```json")
    w(json.dumps(metrics, indent=2, sort_keys=True))
    w("```")

    # ---- projections verbatim (full mode only) ---------------------------
    if not compact:
        for fn in ("actor_wakes.jsonl", "actor_views.jsonl", "intentions.jsonl",
                   "intention_rejections.jsonl", "action_lifecycle.jsonl",
                   "information_lifecycle.jsonl", "state_transitions.jsonl",
                   "continuous_process_transitions.jsonl"):
            rows = load_jsonl(os.path.join(d, fn))
            w(f"\n## {name} — {fn} ({len(rows)} records, verbatim)\n")
            if not rows:
                w("*(empty — nothing of this kind occurred in this run)*")
                continue
            w("```json")
            for r in rows:
                w(json.dumps(r, sort_keys=True))
            w("```")

    # ---- fidelity review --------------------------------------------------
    rev = os.path.join(d, "reality_fidelity_review.md")
    if os.path.exists(rev):
        w(f"\n## {name} — reality_fidelity_review.md\n")
        with open(rev, encoding="utf-8") as f:
            w(f.read())
    return "\n".join(out)


def main():
    global INLINE_BODIES
    if "--chat" in sys.argv:
        INLINE_BODIES = False       # stream only; view/LLM bodies live in files
    compact = "--compact" in sys.argv or "--chat" in sys.argv
    parts = [
        "# SWORLDMODEL — complete run trace\n",
        "All artifacts from every run, merged into one canonical, "
        "time-ordered document.\n",
        "The **event ledger is the single source of truth**: `{seq, t, op, "
        "data, cause}`. Every other artifact (wakes, views, intentions, "
        "action/information/state/process lifecycles) is a *projection* of "
        "that ledger, so the merged stream below tags each record with the "
        "streams it belongs to rather than repeating it. Replaying the ledger "
        "with zero actor/LLM calls reproduces the final state hash and "
        "terminal result exactly.\n",
        "Runs, in execution order:\n",
    ]
    for n, tz, blurb in WORLDS:
        parts.append(f"- **{n}** — {blurb} (times shown in {tz})")
    for n, tz, blurb in WORLDS:
        parts.append(render_world(n, tz, blurb, compact))
    doc = "\n".join(parts)
    if compact:
        sys.stdout.write(doc)
    else:
        with open(os.path.join(HERE, "RUN_TRACE.md"), "w", encoding="utf-8") as f:
            f.write(doc)
        print(f"wrote RUN_TRACE.md ({len(doc):,} chars)")


if __name__ == "__main__":
    main()
