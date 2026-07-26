"""Persistent actors and the strict boundary between mind and world.

An actor's persistent state is qualitative -- beliefs, goals, values,
emotions, relationships, commitments, memories, plan -- expressed as
statements with provenance and timestamps, never as invented psychological
numbers.  Memories are timestamped and append-only.

A Mind (scripted in Phase A, LLM-backed in Phase B) sees ONLY an ActorView:
a defensive copy of the actor's own state plus locally-known information and
the authoritative time context.  It returns a Decision: proposed intentions,
proposed private-state updates, and optional future-wake requests.  It has no
reference to the World, the clock, the queue, other actors, or the terminal;
everything it returns passes through kernel validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .actions import Intention
from .info import AttentionRule
from .simclock import fmt_local, fmt_span, iso, parse_iso


#: Private-state operations a mind may propose about ITSELF, and nothing else.
#: Violations are recorded in the ledger (mind.violation) and skipped --
#: containment is enforced, not assumed.
ACTOR_UPDATE_OPS = frozenset({
    "actor.belief", "actor.plan", "actor.emotion", "actor.physical",
    "actor.relationship", "actor.commit", "actor.commitment_resolved",
    "actor.memory", "actor.reconsider",
})


@dataclass(frozen=True)
class Belief:
    statement: str
    basis: str          # where the belief came from (free text provenance)
    updated_at: datetime


@dataclass(frozen=True)
class Memory:
    """Append-only, timestamped, qualitative.  No importance scores in the
    kernel: retrieval-ranking models belong above it."""
    t: datetime         # when the memory was created
    kind: str           # observation | note | interpretation | ...
    content: str        # qualitative content
    source: str         # what produced it (info id, action id, "decision", ...)


@dataclass
class Commitment:
    id: str
    what: str
    at: datetime | None   # None = not time-bound
    resolved: bool = False


@dataclass
class ActorState:
    """Everything the world durably remembers about an actor."""
    id: str
    name: str
    role: str
    tz: str
    attention: dict = field(default_factory=dict)        # channel -> AttentionRule
    goals: list = field(default_factory=list)            # [str]
    values: list = field(default_factory=list)           # [str]
    emotional_state: str = ""
    physical_state: str = ""
    beliefs: dict = field(default_factory=dict)          # topic -> Belief
    relationships: dict = field(default_factory=dict)    # other_id -> str
    commitments: dict = field(default_factory=dict)      # id -> Commitment
    memories: list = field(default_factory=list)         # [Memory], append-only
    plan: str = ""
    reconsider: list = field(default_factory=list)       # [{"on": kind|"any", "channel"?, "note"}]
    ongoing_action: str | None = None
    last_decision_at: datetime | None = None
    available_info: list = field(default_factory=list)   # delivered, not yet noticed
    noticed_info: list = field(default_factory=list)     # noticed (in arrival order)
    unprocessed_info: list = field(default_factory=list) # noticed since last decision
    deferred_wakes: list = field(default_factory=list)   # queued triggers while busy

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "role": self.role, "tz": self.tz,
            "attention": {ch: r.to_dict() for ch, r in sorted(self.attention.items())},
            "goals": list(self.goals), "values": list(self.values),
            "emotional_state": self.emotional_state, "physical_state": self.physical_state,
            "beliefs": {k: {"statement": b.statement, "basis": b.basis,
                            "updated_at": iso(b.updated_at)}
                        for k, b in sorted(self.beliefs.items())},
            "relationships": dict(sorted(self.relationships.items())),
            "commitments": {k: {"id": c.id, "what": c.what,
                                "at": iso(c.at) if c.at else None, "resolved": c.resolved}
                            for k, c in sorted(self.commitments.items())},
            "memories": [{"t": iso(m.t), "kind": m.kind, "content": m.content,
                          "source": m.source} for m in self.memories],
            "plan": self.plan,
            "reconsider": list(self.reconsider),
            "ongoing_action": self.ongoing_action,
            "last_decision_at": iso(self.last_decision_at) if self.last_decision_at else None,
            "available_info": list(self.available_info),
            "noticed_info": list(self.noticed_info),
            "unprocessed_info": list(self.unprocessed_info),
            "deferred_wakes": list(self.deferred_wakes),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ActorState":
        st = cls(id=d["id"], name=d["name"], role=d["role"], tz=d["tz"])
        st.attention = {ch: AttentionRule.from_dict(r)
                        for ch, r in d.get("attention", {}).items()}
        st.goals = list(d.get("goals", []))
        st.values = list(d.get("values", []))
        st.emotional_state = d.get("emotional_state", "")
        st.physical_state = d.get("physical_state", "")
        st.beliefs = {k: Belief(b["statement"], b["basis"], parse_iso(b["updated_at"]))
                      for k, b in d.get("beliefs", {}).items()}
        st.relationships = dict(d.get("relationships", {}))
        st.commitments = {k: Commitment(c["id"], c["what"],
                                        parse_iso(c["at"]) if c.get("at") else None,
                                        c.get("resolved", False))
                          for k, c in d.get("commitments", {}).items()}
        st.memories = [Memory(parse_iso(m["t"]), m["kind"], m["content"], m["source"])
                       for m in d.get("memories", [])]
        st.plan = d.get("plan", "")
        st.reconsider = list(d.get("reconsider", []))
        st.ongoing_action = d.get("ongoing_action")
        lda = d.get("last_decision_at")
        st.last_decision_at = parse_iso(lda) if lda else None
        st.available_info = list(d.get("available_info", []))
        st.noticed_info = list(d.get("noticed_info", []))
        st.unprocessed_info = list(d.get("unprocessed_info", []))
        st.deferred_wakes = list(d.get("deferred_wakes", []))
        return st


# ---------------------------------------------------------------------------
# What a mind is shown (defensive copies only) and what it may return.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InfoView:
    id: str
    author: str
    channel: str
    content: str
    data: dict
    noticed_at: datetime


@dataclass(frozen=True)
class ActionView:
    id: str
    verb: str
    params: dict
    started_at: datetime | None
    completes_at: datetime | None   # None when completion is condition-based


@dataclass(frozen=True)
class CommitmentView:
    id: str
    what: str
    at: datetime | None


@dataclass(frozen=True)
class VerbView:
    verb: str
    description: str


@dataclass(frozen=True)
class ActorView:
    """The complete and ONLY input to a mind."""
    actor_id: str
    name: str
    role: str
    tz: str
    now: datetime
    world_version: int                      # stamped so stale intentions can be detected
    reasons: tuple                          # tuple[dict]: why the actor is being consulted
    new_information: tuple                  # tuple[InfoView]: noticed since last decision
    goals: tuple
    values: tuple
    emotional_state: str
    physical_state: str
    beliefs: dict                           # topic -> Belief (frozen)
    relationships: dict                     # other id -> str
    memories: tuple                         # tuple[Memory] (frozen), append-only history
    plan: str
    reconsider: tuple                       # tuple[dict]
    commitments: tuple                      # tuple[CommitmentView], unresolved
    ongoing: ActionView | None
    completed: tuple                        # tuple[ActionView]: actions just finished
    time_since_last_decision: timedelta | None
    available_verbs: tuple                  # tuple[VerbView]

    def time_context(self) -> str:
        """The authoritative time block every actor call receives."""
        lines = [f"Current time:\n{fmt_local(self.now, self.tz)}"]
        if self.time_since_last_decision is not None:
            lines.append("\nTime since your previous relevant decision:\n"
                         + fmt_span(self.time_since_last_decision))
        pending = [c for c in self.commitments if c.at is not None and c.at >= self.now]
        if pending:
            lines.append("\nUpcoming commitments:")
            for c in pending:
                lines.append(f"- {c.what} in {fmt_span(c.at - self.now)}"
                             f" (at {fmt_local(c.at, self.tz)})")
        if self.ongoing is not None:
            when = (fmt_local(self.ongoing.completes_at, self.tz)
                    if self.ongoing.completes_at else "when its completion condition is met")
            lines.append(f"\nOngoing actions:\n- {self.ongoing.verb},"
                         f" expected completion at {when}")
        lines.append("\nWhy you are being consulted now:")
        for r in self.reasons:
            lines.append(f"- {r['kind']}: {r.get('detail', '')}")
        return "\n".join(lines)

    def render(self) -> str:
        """Full textual rendering (used as the LLM prompt body in Phase B and
        recorded in actor_views.jsonl for inspectability)."""
        parts = [self.time_context()]
        if self.new_information:
            parts.append("\nNew information you have just noticed:")
            for iv in self.new_information:
                parts.append(f"- [{iv.channel}] message {iv.id} from {iv.author}: "
                             f"{iv.content}")
        if self.completed:
            for av in self.completed:
                parts.append(f"\nYou just finished: {av.verb} {av.params}")
        parts.append(f"\nYour role: {self.role}")
        if self.goals:
            parts.append("Your goals:\n" + "\n".join(f"- {g}" for g in self.goals))
        if self.values:
            parts.append("Your dispositions:\n" + "\n".join(f"- {v}" for v in self.values))
        if self.beliefs:
            parts.append("Your current beliefs:")
            for topic, b in sorted(self.beliefs.items()):
                parts.append(f"- [{topic}] {b.statement} (basis: {b.basis})")
        if self.relationships:
            parts.append("Your relationships:")
            for other, rel in sorted(self.relationships.items()):
                parts.append(f"- {other}: {rel}")
        if self.emotional_state:
            parts.append(f"Your emotional state: {self.emotional_state}")
        if self.physical_state:
            parts.append(f"Your physical state: {self.physical_state}")
        if self.plan:
            parts.append(f"Your current plan: {self.plan}")
        if self.memories:
            parts.append("Your memories (oldest first):")
            for m in self.memories:
                parts.append(f"- [{fmt_local(m.t, self.tz)}] ({m.kind}) {m.content}")
        if self.available_verbs:
            parts.append("Actions available to you:")
            for v in self.available_verbs:
                parts.append(f"- {v.verb}: {v.description}")
        return "\n".join(parts)


@dataclass
class Decision:
    """Everything a mind may return.  All of it is validated by the kernel."""
    intentions: list = field(default_factory=list)       # [Intention]
    updates: list = field(default_factory=list)          # [(op, data)] -- own state only
    interrupt_ongoing: bool = False                      # request to break current action
    interrupt_reason: str = ""
    wake_me_at: datetime | None = None                   # plan-driven reconsideration
    wake_me_reason: str = ""
    note: str = ""                                       # the actor's own summary


class Mind:
    """Interface every actor implementation satisfies -- scripted rule
    policies in Phase A, an LLM-backed mind in Phase B."""

    def decide(self, view: ActorView) -> Decision:
        raise NotImplementedError
