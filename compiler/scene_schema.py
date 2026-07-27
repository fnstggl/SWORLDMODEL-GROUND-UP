"""The four-field SceneManifest contract and the review contract.

This is the ENTIRE semantic surface of world compilation: who exists at the
start (with their private context), what context is shared, what initial
events actually occur, and what observed event history counts as YES or NO.
The manifest is a small storage envelope for meaning -- code owns every ID,
timestamp format, runtime operation, and implementation detail.

Strict by construction: exactly these fields, no unknown fields, no
additions unless a concrete failure proves the information cannot come from
the question, code-owned metadata, the evidence package, the runtime, or a
later actor decision."""
from __future__ import annotations

from datetime import datetime

#: The strict JSON schema for LLM Call 1 (embedded in the prompt verbatim
#: and enforced by validate_manifest_shape below).
SCENE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["actors", "shared_context", "starting_events", "resolution"],
    "properties": {
        "actors": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "private_context"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "private_context": {"type": "string", "minLength": 1},
                },
            },
        },
        "shared_context": {"type": "string", "minLength": 1},
        "starting_events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["time", "description", "visible_to"],
                "properties": {
                    "time": {"type": "string", "format": "date-time"},
                    "description": {"type": "string", "minLength": 1},
                    "visible_to": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
        "resolution": {"type": "string", "minLength": 1},
    },
}

#: The strict schema for LLM Call 2 (the independent adversarial review).
REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "defects"],
    "properties": {
        "verdict": {"enum": ["APPROVE", "REVISE", "ABSTAIN"]},
        "defects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "problem", "correction"],
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "problem": {"type": "string", "minLength": 1},
                    "correction": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}


def _iso_tz_aware(s) -> bool:
    if not isinstance(s, str):
        return False
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt.tzinfo is not None


def validate_manifest_shape(obj) -> list:
    """Strict shape validation of a Call-1/Call-3 manifest -> error list."""
    errors = []
    if not isinstance(obj, dict):
        return ["manifest must be a JSON object"]
    unknown = set(obj) - {"actors", "shared_context", "starting_events",
                          "resolution"}
    if unknown:
        errors.append(f"unknown top-level fields {sorted(unknown)}: the "
                      f"manifest has exactly four fields")
    for f in ("actors", "shared_context", "starting_events", "resolution"):
        if f not in obj:
            errors.append(f"missing required field {f!r}")
    if errors:
        return errors
    if not isinstance(obj["actors"], list) or not obj["actors"]:
        errors.append("actors must be a non-empty array")
    else:
        for i, a in enumerate(obj["actors"]):
            if not isinstance(a, dict):
                errors.append(f"actors[{i}] must be an object")
                continue
            unknown = set(a) - {"name", "private_context"}
            if unknown:
                errors.append(f"actors[{i}]: unknown fields {sorted(unknown)}")
            for f in ("name", "private_context"):
                if not isinstance(a.get(f), str) or not a.get(f, "").strip():
                    errors.append(f"actors[{i}].{f} must be a non-empty string")
    if not isinstance(obj["shared_context"], str) \
            or not obj["shared_context"].strip():
        errors.append("shared_context must be a non-empty string")
    if not isinstance(obj["starting_events"], list):
        errors.append("starting_events must be an array (possibly empty)")
    else:
        for i, e in enumerate(obj["starting_events"]):
            if not isinstance(e, dict):
                errors.append(f"starting_events[{i}] must be an object")
                continue
            unknown = set(e) - {"time", "description", "visible_to"}
            if unknown:
                errors.append(f"starting_events[{i}]: unknown fields "
                              f"{sorted(unknown)}")
            if not _iso_tz_aware(e.get("time")):
                errors.append(f"starting_events[{i}].time must be a "
                              f"timezone-aware ISO 8601 timestamp")
            if not isinstance(e.get("description"), str) \
                    or not e.get("description", "").strip():
                errors.append(f"starting_events[{i}].description must be a "
                              f"non-empty string")
            vt = e.get("visible_to")
            if not isinstance(vt, list) \
                    or any(not isinstance(v, str) or not v.strip()
                           for v in vt):
                errors.append(f"starting_events[{i}].visible_to must be an "
                              f"array of non-empty actor names")
    if not isinstance(obj["resolution"], str) or not obj["resolution"].strip():
        errors.append("resolution must be a non-empty string")
    return errors


def validate_review_shape(obj) -> list:
    errors = []
    if not isinstance(obj, dict):
        return ["review must be a JSON object"]
    unknown = set(obj) - {"verdict", "defects"}
    if unknown:
        errors.append(f"unknown fields {sorted(unknown)}: the review has "
                      f"exactly verdict and defects")
    if obj.get("verdict") not in ("APPROVE", "REVISE", "ABSTAIN"):
        errors.append("verdict must be APPROVE, REVISE, or ABSTAIN")
    if not isinstance(obj.get("defects"), list):
        errors.append("defects must be an array (empty for APPROVE)")
    else:
        for i, d in enumerate(obj["defects"]):
            if not isinstance(d, dict):
                errors.append(f"defects[{i}] must be an object")
                continue
            unknown = set(d) - {"path", "problem", "correction"}
            if unknown:
                errors.append(f"defects[{i}]: unknown fields {sorted(unknown)}")
            for f in ("path", "problem", "correction"):
                if not isinstance(d.get(f), str) or not d.get(f, "").strip():
                    errors.append(f"defects[{i}].{f} must be a non-empty "
                                  f"string")
    if obj.get("verdict") == "REVISE" and not obj.get("defects"):
        errors.append("REVISE requires at least one defect")
    return errors
