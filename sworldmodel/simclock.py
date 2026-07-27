"""Authoritative simulation time.

Continuous real-calendar time underneath, discrete events on top.

Every instant in the simulation is a timezone-aware ``datetime`` normalized
to UTC internally; naive datetimes are rejected everywhere.  Elapsed time is
therefore always real elapsed time -- daylight-saving transitions, weekends
and time zones fall out of the arithmetic instead of being approximated.

Two kinds of time arithmetic are deliberately separated:

* **elapsed durations** -- exact spans of physical time ("exactly 24 hours"),
  computed on UTC instants;
* **calendar movement** -- "next local day", "in two business days",
  "same date next month", computed on local wall clocks and therefore NOT
  always a fixed number of elapsed hours (a local day across a
  daylight-saving transition is 23 or 25 elapsed hours).

Ambiguous local times (fall-back) and nonexistent local times (spring-forward)
are never silently resolved: they raise unless the caller explicitly
disambiguates with ``fold``.

Durations carry *provenance*: no delay is ever silently invented.  Anything
that takes time must say whether the duration is verified, inferred,
actor-chosen, process-derived, genuinely immediate, or explicitly unknown.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc

#: Every duration/rate must state where it came from (spec: "never silently
#: assign 'one day' because the simulator needs a delay").
PROVENANCE_BASES = frozenset({
    "verified",         # documented schedule / measured / known fact
    "inferred",         # estimated from comparable real-world processes
    "actor_chosen",     # the actor decided to spend this long
    "process_derived",  # computed from rates and quantities in the world
    "scenario_given",   # stipulated by the question or scenario definition
    "immediate",        # genuinely instantaneous at this resolution
    "unknown",          # explicitly unknown -- flagged, never silent
})

#: Bases acceptable wherever a CONCRETE number (a duration, rate, latency,
#: cadence) is consumed.  "unknown" is deliberately excluded there: an
#: unknown duration must be modeled as a completion condition or an
#: explicitly labeled inference, never as a number wearing an "unknown" tag.
CONCRETE_BASES = frozenset(PROVENANCE_BASES - {"unknown"})


class NonexistentLocalTime(ValueError):
    """The local wall time does not exist (spring-forward gap)."""


class AmbiguousLocalTime(ValueError):
    """The local wall time occurs twice (fall-back overlap)."""


def aware(dt: datetime) -> datetime:
    """Normalize to UTC; reject naive datetimes outright."""
    if not isinstance(dt, datetime) or dt.tzinfo is None:
        raise ValueError(f"timezone-aware datetime required, got {dt!r}")
    return dt.astimezone(UTC)


def classify_local(naive: datetime, tz: str) -> str:
    """Classify a naive local wall time as 'unique', 'ambiguous' (fall-back)
    or 'nonexistent' (spring-forward)."""
    if naive.tzinfo is not None:
        raise ValueError("classify_local takes a naive local wall time")
    zone = ZoneInfo(tz)
    d0 = naive.replace(tzinfo=zone, fold=0)
    d1 = naive.replace(tzinfo=zone, fold=1)
    if d0.utcoffset() == d1.utcoffset():
        # single candidate offset -- but the wall time may still sit in a gap
        round_trip = d0.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        return "unique" if round_trip == naive else "nonexistent"
    # two candidate offsets: either both real (overlap) or a gap edge
    rt0 = d0.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    rt1 = d1.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    if rt0 == naive and rt1 == naive:
        return "ambiguous"
    return "nonexistent"


def local_instant(naive: datetime, tz: str, fold: int | None = None) -> datetime:
    """Convert a naive local wall time to a UTC instant, strictly.

    Nonexistent local times always raise.  Ambiguous local times raise unless
    the caller disambiguates with ``fold`` (0 = first occurrence, 1 = second).
    """
    kind = classify_local(naive, tz)
    if kind == "nonexistent":
        raise NonexistentLocalTime(
            f"{naive.isoformat()} does not exist in {tz} (spring-forward gap)")
    if kind == "ambiguous" and fold is None:
        raise AmbiguousLocalTime(
            f"{naive.isoformat()} occurs twice in {tz} (fall-back); pass fold=0 or fold=1")
    return naive.replace(tzinfo=ZoneInfo(tz), fold=fold or 0).astimezone(UTC)


def at_local(year: int, month: int, day: int, hour: int = 0, minute: int = 0,
             second: int = 0, tz: str = "UTC", fold: int | None = None) -> datetime:
    """Build a UTC instant from a local wall-clock time in a named zone.
    Strict: raises on nonexistent or (undisambiguated) ambiguous times."""
    return local_instant(datetime(year, month, day, hour, minute, second), tz, fold)


def elapsed(a: datetime, b: datetime) -> timedelta:
    """Exact physical time elapsed from a to b (UTC arithmetic)."""
    return aware(b) - aware(a)


def next_local_day(dt: datetime, tz: str, fold: int | None = None) -> datetime:
    """Calendar movement: the same wall-clock time on the next local calendar
    day.  Across DST transitions this is deliberately NOT 24 elapsed hours;
    raises if the resulting wall time is nonexistent/ambiguous (unless fold
    disambiguates)."""
    lt = aware(dt).astimezone(ZoneInfo(tz))
    naive = lt.replace(tzinfo=None) + timedelta(days=1)
    return local_instant(naive, tz, fold)


def add_business_days(dt: datetime, n: int, cal: "BusinessCalendar",
                      fold: int | None = None) -> datetime:
    """Calendar movement: same wall-clock time n business days later
    (per the calendar's workdays/holidays). n must be >= 1."""
    if n < 1:
        raise ValueError("n must be >= 1")
    lt = aware(dt).astimezone(ZoneInfo(cal.tz))
    d = lt.date()
    remaining = n
    for _ in range(4000):
        d = d + timedelta(days=1)
        if cal.is_workday(d):
            remaining -= 1
            if remaining == 0:
                return local_instant(datetime.combine(d, lt.time().replace(fold=0)),
                                     cal.tz, fold)
    raise ValueError("no business day found within 4000 days")


def add_calendar_months(dt: datetime, n: int, tz: str,
                        day_policy: str = "strict", fold: int | None = None) -> datetime:
    """Calendar movement: same local date/time n calendar months later.

    ``day_policy='strict'`` raises if the target month has no such day
    (e.g. Jan 31 + 1 month); ``day_policy='clamp'`` moves to the last day of
    the target month -- an explicit, labeled choice, never a silent default.
    """
    if day_policy not in ("strict", "clamp"):
        raise ValueError("day_policy must be 'strict' or 'clamp'")
    lt = aware(dt).astimezone(ZoneInfo(tz))
    month_index = lt.year * 12 + (lt.month - 1) + n
    year, month = divmod(month_index, 12)
    month += 1
    day = lt.day
    # days in target month
    first_next = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
    days_in_month = (first_next - date(year, month, 1)).days
    if day > days_in_month:
        if day_policy == "strict":
            raise ValueError(
                f"{year}-{month:02d} has no day {day}; pass day_policy='clamp' to use month end")
        day = days_in_month
    naive = datetime(year, month, day, lt.hour, lt.minute, lt.second, lt.microsecond)
    return local_instant(naive, tz, fold)


def iso(dt: datetime) -> str:
    return aware(dt).isoformat()


def parse_iso(s: str) -> datetime:
    return aware(datetime.fromisoformat(s))


def fmt_local(dt: datetime, tz: str) -> str:
    """Render an instant as local wall time, e.g. '2026-06-20 14:30:00 America/Mexico_City'."""
    return aware(dt).astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M:%S") + f" {tz}"


def fmt_span(delta: timedelta) -> str:
    """Human-readable elapsed time, e.g. '11 days, 4 hours'."""
    total = int(delta.total_seconds())
    sign = "-" if total < 0 else ""
    total = abs(total)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} day" + ("s" if days != 1 else ""))
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minutes:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
    if seconds and not days:
        parts.append(f"{seconds} second" + ("s" if seconds != 1 else ""))
    if not parts:
        parts = ["0 minutes"]
    return sign + ", ".join(parts)


@dataclass(frozen=True)
class Duration:
    """A span of time plus the provenance of that estimate."""
    delta: timedelta
    basis: str
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.delta, timedelta):
            raise ValueError(f"Duration.delta must be a timedelta, got {self.delta!r}")
        if self.delta < timedelta(0):
            raise ValueError(f"Duration cannot be negative: {self.delta}")
        if self.basis not in CONCRETE_BASES:
            raise ValueError(
                f"Duration.basis must be one of {sorted(CONCRETE_BASES)}, got "
                f"{self.basis!r} (an unknown duration is a completion "
                f"condition, not a number labeled 'unknown')")

    def to_dict(self) -> dict:
        return {"seconds": self.delta.total_seconds(), "basis": self.basis, "note": self.note}

    @classmethod
    def from_dict(cls, d: dict) -> "Duration":
        return cls(timedelta(seconds=d["seconds"]), d["basis"], d.get("note", ""))


class Clock:
    """The single authority for the current simulation time.

    Only the engine advances it, and only forward.  Actors never invent the
    current time; every actor call receives the clock's value rendered in the
    actor's own time zone.
    """

    def __init__(self, start: datetime) -> None:
        self._now = aware(start)

    @property
    def now(self) -> datetime:
        return self._now

    def advance_to(self, t: datetime) -> None:
        t = aware(t)
        if t < self._now:
            raise ValueError(
                f"clock cannot move backwards: {self._now.isoformat()} -> {t.isoformat()}")
        self._now = t


@dataclass(frozen=True)
class BusinessCalendar:
    """Working hours in a named time zone, with weekends and holidays.

    All queries take and return UTC instants; wall-clock reasoning happens in
    the calendar's zone, so daylight-saving transitions are handled by
    ``zoneinfo`` rather than by us.
    """
    tz: str
    workdays: frozenset = frozenset({0, 1, 2, 3, 4})  # Mon..Fri
    open_time: time = time(9, 0)
    close_time: time = time(17, 0)
    holidays: frozenset = frozenset()  # of datetime.date

    def _zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    def is_workday(self, d: date) -> bool:
        return d.weekday() in self.workdays and d not in self.holidays

    def is_open(self, at: datetime) -> bool:
        lt = aware(at).astimezone(self._zone())
        return self.is_workday(lt.date()) and self.open_time <= lt.time() < self.close_time

    def open_of(self, d: date) -> datetime:
        """The instant this calendar opens on day ``d``.

        Explicit, deterministic DST policy (recorded here, not silent): if
        the opening wall time falls in a spring-forward gap, the day opens at
        the first existing wall time after the gap; if it falls in a
        fall-back overlap, the FIRST occurrence opens the day (fold=0)."""
        naive = datetime.combine(d, self.open_time)
        kind = classify_local(naive, self.tz)
        if kind == "unique":
            return local_instant(naive, self.tz)
        if kind == "ambiguous":
            return local_instant(naive, self.tz, fold=0)
        for minutes in range(1, 181):
            cand = naive + timedelta(minutes=minutes)
            if classify_local(cand, self.tz) == "unique":
                return local_instant(cand, self.tz)
        raise ValueError(f"cannot resolve opening time on {d} in {self.tz}")

    def next_open(self, at: datetime) -> datetime:
        """Earliest instant >= ``at`` that falls inside working hours."""
        at = aware(at)
        if self.is_open(at):
            return at
        lt = at.astimezone(self._zone())
        d = lt.date()
        if self.is_workday(d) and lt.time() < self.open_time:
            return self.open_of(d)
        for i in range(1, 400):
            nd = d + timedelta(days=i)
            if self.is_workday(nd):
                return self.open_of(nd)
        raise ValueError(f"no working day within 400 days of {at.isoformat()}")

    def next_attention(self, at: datetime, check_every: timedelta | None) -> datetime:
        """Earliest instant >= ``at`` when someone on this calendar looks at a
        channel they check every ``check_every`` (checks aligned to opening
        time each working day).  ``None`` means continuously attentive while
        open.  Check times follow the local wall clock, which is what real
        routines do across DST transitions."""
        t = self.next_open(at)
        if not check_every:
            return t
        zone = self._zone()
        lt = t.astimezone(zone)
        day_open = datetime.combine(lt.date(), self.open_time)
        naive = lt.replace(tzinfo=None)
        q, r = divmod(naive - day_open, check_every)
        k = q + (1 if r else 0)
        candidate = day_open + k * check_every
        for _ in range(1000):
            if candidate.time() >= self.close_time or candidate.date() != day_open.date():
                # past closing: the next check happens at the next working
                # day's opening -- CALENDAR-day movement, never +24 elapsed h
                d = day_open.date()
                for i in range(1, 400):
                    nd = d + timedelta(days=i)
                    if self.is_workday(nd):
                        return self.open_of(nd)
                raise ValueError("no working day within 400 days")
            if classify_local(candidate, self.tz) == "unique":
                cand_utc = local_instant(candidate, self.tz)
                if cand_utc >= t:
                    return cand_utc
            # wall time in a DST gap or already passed: move to the next check
            candidate += check_every
        raise ValueError("could not compute next attention time")

    def to_dict(self) -> dict:
        return {
            "tz": self.tz,
            "workdays": sorted(self.workdays),
            # keep sub-minute precision: an end-of-day boundary of
            # 23:59:59.999999 must not round down to 23:59:00 and leave a
            # dead minute in a round-the-clock calendar
            "open": self.open_time.isoformat(),
            "close": self.close_time.isoformat(),
            "holidays": sorted(d.isoformat() for d in self.holidays),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BusinessCalendar":
        return cls(
            tz=d["tz"],
            workdays=frozenset(d.get("workdays", [0, 1, 2, 3, 4])),
            open_time=time.fromisoformat(d.get("open", "09:00")),
            close_time=time.fromisoformat(d.get("close", "17:00")),
            holidays=frozenset(date.fromisoformat(x) for x in d.get("holidays", [])),
        )


def recurring(tz: str, at_time: time, from_date: date, until_date: date,
              workdays: frozenset = frozenset({0, 1, 2, 3, 4}),
              holidays: frozenset = frozenset()):
    """Yield UTC instants for a recurring local-time schedule (e.g. shift
    starts on workdays).  Calendar-correct: one day is one calendar day."""
    d = from_date
    while d <= until_date:
        if d.weekday() in workdays and d not in holidays:
            yield local_instant(datetime.combine(d, at_time), tz)
        d += timedelta(days=1)
