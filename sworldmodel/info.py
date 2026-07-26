"""Information: channels and attention.

Information has a timed lifecycle with distinct stages, each recorded:

    created -> sent -> delivered (available) -> noticed -> interpreted

Delivery latency comes from the channel (with provenance).  *Noticing* is
separate from delivery and never defaulted: it happens only through an
explicit, provenance-labeled AttentionRule for that actor+channel (alert-style
immediate attention, or a checking routine anchored to a calendar), or not at
all -- in which case the information remains delivered-but-unnoticed and the
kernel records that noticing was unsupported.  Unknown remains unknown; the
kernel never invents a delay to make a scenario proceed.

Interpretation (belief updates) belongs to the actor's mind, not the kernel.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from datetime import datetime as _datetime, date as _date

from .simclock import BusinessCalendar, CONCRETE_BASES, Duration, aware


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
        if self.basis not in CONCRETE_BASES:
            raise ValueError(
                f"AttentionRule.basis must be one of {sorted(CONCRETE_BASES)}; "
                f"if the noticing behavior is unknown, provide NO rule -- the "
                f"kernel then leaves information delivered-but-unnoticed")
        if not self.note:
            raise ValueError("AttentionRule requires a note explaining the assumed behavior")
        if self.check_every is not None and self.calendar is None:
            raise ValueError(
                "a checking cadence needs a calendar anchor (whose opening "
                "time phases the checks); calendar=None is only valid for "
                "continuous/alert-style attention")
        if self.check_every is not None and self.calendar is not None:
            window = (_datetime.combine(_date(2000, 1, 3), self.calendar.close_time)
                      - _datetime.combine(_date(2000, 1, 3), self.calendar.open_time))
            if self.check_every > window:
                raise ValueError(
                    f"check_every {self.check_every} exceeds the calendar's "
                    f"daily working window {window}: a multi-day cadence must "
                    f"be modeled explicitly (e.g. workdays/holidays), not "
                    f"silently rounded to daily checks")

    def notice_time(self, delivered: datetime) -> datetime:
        """Earliest instant >= delivery at which this rule notices."""
        delivered = aware(delivered)
        if self.calendar is not None:
            return self.calendar.next_attention(delivered, self.check_every)
        return delivered   # continuous alert-style attention

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
