"""Information: channels and attention.

Information has a timed lifecycle with distinct stages, each recorded:

    created -> sent -> delivered (available) -> noticed -> interpreted

Delivery latency comes from the channel (with provenance).  *Noticing* is
separate from delivery and never defaulted: it happens only through

* an explicit, provenance-labeled AttentionRule for that actor+channel, or
* a scheduled check (a wake event carrying ``notice_channels``, e.g. an
  inbox-check commitment), or
* not at all -- in which case the information remains delivered-but-unnoticed
  and the kernel records that noticing was unsupported.  Unknown remains
  unknown; the kernel never invents a delay to make a scenario proceed.

Interpretation (belief updates) belongs to the actor's mind, not the kernel.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .simclock import BusinessCalendar, Duration, PROVENANCE_BASES, aware


@dataclass(frozen=True)
class Channel:
    """A transmission medium with a delivery latency and its provenance."""
    name: str
    latency: Duration

    def to_dict(self) -> dict:
        return {"name": self.name, "latency": self.latency.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> "Channel":
        return cls(d["name"], Duration.from_dict(d["latency"]))


@dataclass(frozen=True)
class AttentionRule:
    """When an actor actually looks at a channel.

    ``calendar`` bounds attention to working/waking hours (None = any hour);
    ``check_every`` is the actor's checking cadence within those hours
    (None = continuously attentive while the calendar is open).
    ``basis`` + ``note`` are required provenance: an attention pattern is a
    real-world claim and must say where it came from.
    """
    calendar: BusinessCalendar | None
    check_every: timedelta | None
    basis: str
    note: str

    def __post_init__(self) -> None:
        if self.basis not in PROVENANCE_BASES:
            raise ValueError(f"AttentionRule.basis must be one of {sorted(PROVENANCE_BASES)}")
        if not self.note:
            raise ValueError("AttentionRule requires a note explaining the assumed behavior")

    def notice_time(self, delivered: datetime) -> datetime:
        """Earliest instant >= delivery at which this rule notices."""
        delivered = aware(delivered)
        if self.calendar is not None:
            return self.calendar.next_attention(delivered, self.check_every)
        if not self.check_every:
            return delivered
        # no calendar: cadence anchored at the top of the UTC day
        anchor = delivered.replace(hour=0, minute=0, second=0, microsecond=0)
        q, r = divmod(delivered - anchor, self.check_every)
        k = q + (1 if r else 0)
        return anchor + k * self.check_every

    def to_dict(self) -> dict:
        return {
            "calendar": self.calendar.to_dict() if self.calendar else None,
            "check_every_seconds": self.check_every.total_seconds() if self.check_every else None,
            "basis": self.basis,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AttentionRule":
        return cls(
            calendar=BusinessCalendar.from_dict(d["calendar"]) if d.get("calendar") else None,
            check_every=(timedelta(seconds=d["check_every_seconds"])
                         if d.get("check_every_seconds") else None),
            basis=d["basis"],
            note=d.get("note", ""),
        )
