"""Temporal edge cases: elapsed vs calendar arithmetic, DST, month ends,
business days, attention scheduling, duration provenance."""
import pytest
from datetime import date, datetime, time, timedelta

from sworldmodel import (AmbiguousLocalTime, BusinessCalendar, Clock, Duration,
                        NonexistentLocalTime, add_business_days,
                        add_calendar_months, at_local, classify_local, elapsed,
                        fmt_span, next_local_day)

NY = "America/New_York"


def test_elapsed_24_hours_is_exact():
    a = at_local(2026, 5, 4, 9, 0, tz=NY)
    b = a + timedelta(hours=24)
    assert elapsed(a, b) == timedelta(hours=24)


def test_next_local_day_across_spring_forward_is_23_elapsed_hours():
    # Sat 2026-03-07 09:00 ET -> Sun 2026-03-08 09:00 ET crosses the gap
    a = at_local(2026, 3, 7, 9, 0, tz=NY)
    b = next_local_day(a, NY)
    assert b.astimezone().tzinfo is not None
    assert elapsed(a, b) == timedelta(hours=23)          # calendar day != 24h
    assert (a + timedelta(hours=24)) != b                 # they genuinely differ


def test_next_local_day_across_fall_back_is_25_elapsed_hours():
    a = at_local(2026, 10, 31, 9, 0, tz=NY)
    b = next_local_day(a, NY)
    assert elapsed(a, b) == timedelta(hours=25)


def test_nonexistent_local_time_raises():
    assert classify_local(datetime(2026, 3, 8, 2, 30), NY) == "nonexistent"
    with pytest.raises(NonexistentLocalTime):
        at_local(2026, 3, 8, 2, 30, tz=NY)


def test_ambiguous_local_time_requires_fold():
    assert classify_local(datetime(2026, 11, 1, 1, 30), NY) == "ambiguous"
    with pytest.raises(AmbiguousLocalTime):
        at_local(2026, 11, 1, 1, 30, tz=NY)
    first = at_local(2026, 11, 1, 1, 30, tz=NY, fold=0)
    second = at_local(2026, 11, 1, 1, 30, tz=NY, fold=1)
    assert elapsed(first, second) == timedelta(hours=1)


def test_month_end_movement_is_explicit():
    jan31 = at_local(2026, 1, 31, 10, 0, tz=NY)
    with pytest.raises(ValueError):
        add_calendar_months(jan31, 1, NY)                 # strict: no Feb 31
    clamped = add_calendar_months(jan31, 1, NY, day_policy="clamp")
    assert clamped == at_local(2026, 2, 28, 10, 0, tz=NY)
    mar15 = at_local(2026, 3, 15, 10, 0, tz=NY)
    assert add_calendar_months(mar15, 3, NY) == at_local(2026, 6, 15, 10, 0, tz=NY)


def test_business_day_movement_skips_weekends_and_holidays():
    cal = BusinessCalendar(tz=NY, holidays=frozenset({date(2026, 5, 25)}))  # Memorial Day
    fri = at_local(2026, 5, 22, 11, 0, tz=NY)
    assert add_business_days(fri, 1, cal) == at_local(2026, 5, 26, 11, 0, tz=NY)
    assert add_business_days(fri, 2, cal) == at_local(2026, 5, 27, 11, 0, tz=NY)


def test_calendar_open_close_and_next_open():
    cal = BusinessCalendar(tz=NY)
    assert cal.is_open(at_local(2026, 3, 6, 16, 59, tz=NY))
    assert not cal.is_open(at_local(2026, 3, 6, 17, 0, tz=NY))
    # Friday evening -> Monday 09:00, across the DST gap
    nxt = cal.next_open(at_local(2026, 3, 6, 18, 0, tz=NY))
    assert nxt == at_local(2026, 3, 9, 9, 0, tz=NY)
    assert elapsed(at_local(2026, 3, 6, 18, 0, tz=NY), nxt) == timedelta(hours=62)


def test_next_attention_grid_and_after_hours():
    cal = BusinessCalendar(tz=NY)
    # delivered 09:07, checked every 30 min from opening -> 09:30
    got = cal.next_attention(at_local(2026, 3, 4, 9, 7, tz=NY), timedelta(minutes=30))
    assert got == at_local(2026, 3, 4, 9, 30, tz=NY)
    # delivered after close -> first check at next opening
    got = cal.next_attention(at_local(2026, 3, 4, 18, 30, tz=NY), timedelta(minutes=30))
    assert got == at_local(2026, 3, 5, 9, 0, tz=NY)
    # continuous attention while open
    got = cal.next_attention(at_local(2026, 3, 4, 9, 7, tz=NY), None)
    assert got == at_local(2026, 3, 4, 9, 7, tz=NY)


def test_clock_is_monotonic_and_tz_aware():
    c = Clock(at_local(2026, 1, 1, tz=NY))
    with pytest.raises(ValueError):
        c.advance_to(at_local(2025, 12, 31, tz=NY))
    with pytest.raises(ValueError):
        Clock(datetime(2026, 1, 1))                       # naive rejected


def test_duration_provenance_is_mandatory():
    with pytest.raises(ValueError):
        Duration(timedelta(hours=1), "because")
    with pytest.raises(ValueError):
        Duration(timedelta(hours=-1), "verified")
    # a concrete number can never be labeled "unknown" -- an unknown duration
    # is a completion condition or a labeled inference, not a decorated guess
    with pytest.raises(ValueError):
        Duration(timedelta(hours=1), "unknown", "explicitly unknown")


def test_attention_rules_are_strict():
    from sworldmodel import AttentionRule
    cal = BusinessCalendar(tz=NY)
    with pytest.raises(ValueError):     # cadence needs a calendar anchor
        AttentionRule(None, timedelta(minutes=30), "inferred", "x")
    with pytest.raises(ValueError):     # multi-day cadence must be modeled, not rounded
        AttentionRule(cal, timedelta(days=2), "inferred", "x")
    with pytest.raises(ValueError):     # concrete behavior can't be "unknown"
        AttentionRule(cal, timedelta(minutes=30), "unknown", "x")
    with pytest.raises(ValueError):     # provenance note is mandatory
        AttentionRule(cal, timedelta(minutes=30), "inferred", "")


def test_fmt_span():
    assert fmt_span(timedelta(days=11, hours=4)) == "11 days, 4 hours"
    assert fmt_span(timedelta(minutes=0)) == "0 minutes"
