"""The global natural-language world journal.

The journal is the append-only authoritative history of what actually
occurred.  It is not a new storage system: every entry is a record in the
existing kernel ledger (``World.apply``), so it inherits immutability,
monotonic sequence numbers, authoritative timestamps, explicit causality
(``cause``), and replay for free.  This module is the projection and the
commit interface over that ledger.

Only something the world adjudicator confirms as having concretely
occurred may enter the journal.  An intention is not a committed event; an
unexecuted plan is not a committed event; a model prediction is not a
committed event.
"""
from __future__ import annotations

#: ledger op names owned by the semantic runtime (all trace-only in the
#: kernel: they are inspectable history, and the projections below are the
#: only readers, so no kernel reducer is added or modified)
OP_EVENT = "journal.event"
OP_PROFILE = "semantic.actor_profile"
OP_ACTOR_CALL = "semantic.actor_call"
OP_WORLD_CALL = "semantic.world_call"
OP_TERMINAL = "semantic.terminal_check"


class Journal:
    """Append-only committed history, projected from the kernel ledger."""

    def __init__(self, world) -> None:
        self.world = world

    # -- commit -------------------------------------------------------
    def commit(self, envelope: dict, *, cause: int, source: str,
               trajectory_id: str) -> dict:
        """Commit one concrete event.  ``cause`` is the ledger seq of the
        record that produced it -- every committed event has a causal
        trigger, enforced by the kernel itself after genesis."""
        eid = f"e{self.world.version + 1}"
        seq = self.world.apply(OP_EVENT, {
            "event_id": eid,
            "description": envelope["description"],
            "for": list(envelope["for"]),
            "observed": bool(envelope["observed"]),
            "source": source,
            "trajectory_id": trajectory_id,
        }, cause)
        return {"event_id": eid, "seq": seq,
                "t": self.world.records[-1]["t"],
                "description": envelope["description"],
                "for": list(envelope["for"]),
                "observed": bool(envelope["observed"]),
                "source": source}

    # -- projections ---------------------------------------------------
    def events(self) -> list:
        """Every committed event, in commit order."""
        out = []
        for r in self.world.records:
            if r["op"] != OP_EVENT:
                continue
            d = r["data"]
            out.append({"event_id": d["event_id"], "seq": r["seq"], "t": r["t"],
                        "description": d["description"], "for": list(d["for"]),
                        "observed": bool(d["observed"]),
                        "source": d.get("source", ""), "cause": r["cause"]})
        return out

    def by_id(self, event_id: str):
        for e in self.events():
            if e["event_id"] == event_id:
                return e
        return None

    def observed_by(self, actor_id: str) -> list:
        """Exactly what this actor has actually observed -- the only events
        code will ever place in that actor's view."""
        return [e for e in self.events()
                if actor_id in e["for"] and e["observed"]]

    def available_unobserved(self, actor_id: str) -> list:
        """Available to the actor but NOT observed: the world may reason
        about these when adjudicating attention; the actor never sees
        them."""
        return [e for e in self.events()
                if actor_id in e["for"] and not e["observed"]]

    def profiles(self) -> dict:
        """actor_id -> compiler-provided private context."""
        return {r["data"]["actor"]: r["data"]["private_context"]
                for r in self.world.records if r["op"] == OP_PROFILE}

    def shared_context(self) -> str:
        return self.world.facts.get("scene:shared_context", "")

    def render_for_world(self, limit: int = 60) -> str:
        """The committed history as the world adjudicator sees it."""
        lines = []
        for e in self.events()[-limit:]:
            who = ", ".join(e["for"]) or "no one"
            seen = "observed" if e["observed"] else "available, NOT observed"
            lines.append(f"- [{e['t']}] ({e['event_id']}) {e['description']} "
                         f"| available to: {who} | {seen}")
        return "\n".join(lines) or "(nothing has happened yet)"
