"""Timestamped events and the priority queue the engine drains.

Events are identified by the (unique, monotonic) sequence number of the
ledger record that scheduled them.  Ordering is total and deterministic:
(timestamp, same-instant causal depth, seq).  The queue refuses duplicate
seqs, supports cancellation, and never silently drops anything.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import datetime

#: Bound on causal chains within a single instant (backstop for true
#: zero-time loops; the engine additionally detects repeated identical
#: same-instant world states).
MAX_SAME_INSTANT_DEPTH = 60


class ZeroTimeLoopError(RuntimeError):
    """Same-instant causality exceeded its depth bound or revisited an
    identical world state: a true zero-time loop."""


class SchedulingInPastError(RuntimeError):
    """An event was scheduled before the current authoritative clock time."""


@dataclass(frozen=True)
class Event:
    seq: int              # identity: seq of the `event.scheduled` ledger record
    t: datetime           # UTC instant at which the event occurs
    kind: str
    data: dict
    cause: int | None     # ledger seq of what scheduled it
    depth: int            # same-instant causal depth (0 = fresh instant)

    def sort_key(self):
        return (self.t, self.depth, self.seq)


class EventQueue:
    """Deterministic priority queue of pending events."""

    def __init__(self) -> None:
        self._heap: list[tuple] = []
        self._seqs: set[int] = set()        # every seq ever pushed (uniqueness)
        self._cancelled: set[int] = set()

    def push(self, ev: Event) -> None:
        if ev.seq in self._seqs:
            raise ValueError(f"duplicate event seq {ev.seq}: event ids must be unique")
        self._seqs.add(ev.seq)
        heapq.heappush(self._heap, (ev.t, ev.depth, ev.seq, ev))

    def cancel(self, seq: int) -> None:
        self._cancelled.add(seq)

    def _prune(self) -> None:
        while self._heap and self._heap[0][2] in self._cancelled:
            heapq.heappop(self._heap)

    def peek(self) -> Event | None:
        self._prune()
        return self._heap[0][3] if self._heap else None

    def pop(self) -> Event | None:
        self._prune()
        return heapq.heappop(self._heap)[3] if self._heap else None

    def pending(self) -> list[Event]:
        """Live (uncancelled) events in firing order -- for inspection,
        checkpointing and tests."""
        return sorted((e for (_, _, s, e) in self._heap if s not in self._cancelled),
                      key=Event.sort_key)

    def __len__(self) -> int:
        return len(self.pending())
