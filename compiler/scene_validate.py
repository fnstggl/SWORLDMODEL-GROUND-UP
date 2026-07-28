"""Deterministic scene validation and normalization.

Shallow, guaranteed checks only.  Code may normalize capitalization,
whitespace, punctuation, safe Unicode variation, unambiguous aliases, and
exact duplicate events -- and must never invent an actor, a process, a
channel, a future action, an event time, a habit, an authority, a
relationship, a consequence, or a resolution condition."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from .scene_guards import prewritten_outcome_findings, window_findings


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _strip_invisibles(s: str) -> str:
    """Remove zero-width/format characters (Unicode category Cf): a name or
    resolution made only of invisibles must count as empty, and invisible
    infixes must not make identical names distinct."""
    return "".join(ch for ch in s if unicodedata.category(ch) != "Cf")


def norm_name(name: str) -> str:
    """Normalization key for actor-name comparison: NFKC, invisibles
    stripped, collapsed whitespace, casefold, stripped surrounding
    punctuation."""
    s = _strip_invisibles(unicodedata.normalize("NFKC", name))
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip(".,;:!?'\"()[]{}")
    return s.casefold()


def display_name(name: str) -> str:
    s = _strip_invisibles(unicodedata.normalize("NFKC", name))
    return re.sub(r"\s+", " ", s).strip()


def validate_scene(manifest: dict, start_iso: str, cutoff_iso: str,
                   question: str | None = None, context: str | None = None):
    """-> (normalized_manifest, normalization_report, validation_errors,
    validation_warnings).  On errors the manifest must not instantiate.

    When the question is supplied, two shallow backup guards also run (see
    scene_guards): near-identical prewritten outcomes, and a question
    window narrower than the compile cutoff.  The independent reviewer
    remains the primary detector for both."""
    errors: list = []
    warnings: list = []
    notes: list = []
    try:
        start = parse_ts(start_iso)
        cutoff = parse_ts(cutoff_iso)
        if start.tzinfo is None or cutoff.tzinfo is None:
            raise ValueError("start/cutoff must be timezone-aware")
    except (ValueError, TypeError) as e:
        # caller-owned inputs are still validated, never raised through
        return None, {"notes": []}, [f"invalid start/cutoff: {e}"], []
    if cutoff <= start:
        errors.append(f"cutoff {cutoff_iso} is not after start {start_iso}")

    # ---- actors: normalize, dedupe, alias handling --------------------
    actors: list = []
    by_key: dict = {}
    for i, a in enumerate(manifest["actors"]):
        name = display_name(a["name"])
        key = norm_name(a["name"])
        if not key:
            errors.append(f"actors[{i}].name normalizes to empty")
            continue
        if key in by_key:
            # unambiguous alias of an existing actor: merge contexts, note it
            existing = by_key[key]
            if a["private_context"].strip() \
                    and a["private_context"].strip() \
                    not in existing["private_context"]:
                existing["private_context"] += "\n" + a["private_context"].strip()
            notes.append(f"actors[{i}] {a['name']!r} merged into "
                         f"{existing['name']!r} (same normalized name)")
            continue
        node = {"name": name, "private_context": a["private_context"].strip()}
        by_key[key] = node
        actors.append(node)
    keys = list(by_key)
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1:]:
            if k1 != k2 and (k1 in k2 or k2 in k1):
                warnings.append(
                    f"actor names {by_key[k1]['name']!r} and "
                    f"{by_key[k2]['name']!r} contain one another: possible "
                    f"aliases kept as DISTINCT actors (never merged on a "
                    f"guess)")

    # ---- starting events ---------------------------------------------
    events: list = []
    seen_exact: set = set()
    for i, e in enumerate(manifest["starting_events"]):
        try:
            t = parse_ts(e["time"])
        except ValueError:
            errors.append(f"starting_events[{i}].time is not a valid "
                          f"timestamp")
            continue
        if t.tzinfo is None:
            errors.append(f"starting_events[{i}].time is not timezone-aware")
            continue
        desc = re.sub(r"\s+", " ",
                      _strip_invisibles(e["description"])).strip()
        if not desc:
            errors.append(f"starting_events[{i}].description is empty after "
                          f"normalization")
            continue
        vis = []
        for v in e["visible_to"]:
            k = norm_name(v)
            if k not in by_key:
                errors.append(f"starting_events[{i}].visible_to: {v!r} does "
                              f"not resolve to a declared actor")
            elif by_key[k]["name"] in vis:
                notes.append(f"starting_events[{i}]: duplicate visible_to "
                             f"entry {v!r} collapsed")
            else:
                vis.append(by_key[k]["name"])
        if t > cutoff:
            errors.append(f"starting_events[{i}] at {e['time']} is after "
                          f"the cutoff")
            continue
        if t < start:
            notes.append(f"starting_events[{i}] at {e['time']} precedes the "
                         f"start; it is applied at the start instant as "
                         f"already-occurred state")
            t = start
        t = t.astimezone(timezone.utc)      # one instant, one identity
        exact = (t.isoformat(), desc.casefold(), tuple(sorted(vis)))
        if exact in seen_exact:
            notes.append(f"starting_events[{i}] is an exact duplicate; "
                         f"collapsed")
            continue
        for prev in events:
            if prev["description"].casefold() == desc.casefold():
                warnings.append(
                    f"starting_events[{i}] repeats the description of an "
                    f"earlier event at a different time/visibility: "
                    f"probable duplicate (kept; review)")
        seen_exact.add(exact)
        events.append({"time": t.isoformat(), "description": desc,
                       "visible_to": vis})

    # ---- resolution ---------------------------------------------------
    resolution = re.sub(r"\s+", " ",
                        _strip_invisibles(manifest["resolution"])).strip()
    if not resolution:
        errors.append("resolution is empty after normalization")
    if resolution.upper().startswith("UNRESOLVABLE"):
        errors.append(f"scene declared unresolvable by the compiler: "
                      f"{resolution}")
    for i, e in enumerate(events):
        if e["description"].casefold() == resolution.casefold():
            errors.append(
                f"the resolution literally appears as starting_events[{i}]: "
                f"the terminal must not already be an occurred event")
    shared = re.sub(r"\s+", " ",
                    _strip_invisibles(manifest["shared_context"])).strip()
    if not shared:
        errors.append("shared_context is empty after normalization")

    # ---- shallow backup guards (Call 2 is the primary detector) -------
    if question is not None and resolution:
        g_err, g_warn = prewritten_outcome_findings(events, resolution)
        errors.extend(g_err)
        warnings.extend(g_warn)
        errors.extend(window_findings(question, context, resolution,
                                      start, cutoff))

    normalized = {"actors": actors, "shared_context": shared,
                  "starting_events": events, "resolution": resolution}
    report = {"notes": notes, "merged_or_collapsed": len(notes),
              "actor_count": len(actors), "event_count": len(events)}
    return normalized, report, errors, warnings
