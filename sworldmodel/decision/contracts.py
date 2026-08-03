"""Fixed, versioned, code-owned contracts for the best-action decision layer.

Seven frozen dataclasses (six external contracts plus the internal
initialization plan), each carrying a ``contract_type`` / ``schema_version``
envelope.  ``from_dict`` is the single strict gate: unknown fields, missing
required fields, wrong types, invalid enum values, naive or malformed
datetimes, and version mismatches are all rejected, and every error is
collected (never first-fail) into one ``ContractValidationError`` whose
issues carry (path, code, message).  Nothing is repaired silently.

``to_dict`` / ``from_dict`` round-trip loss-lessly; ``canonical_json`` (sorted
keys, compact separators) is the hashing base for ``content_hash`` (sha256).

Pure stdlib.  This module knows nothing about any concrete scenario: all
identifiers and messages use generic schema vocabulary only.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar, Mapping

SCHEMA_VERSION = 1

TERMINAL_STATUSES = ("success", "failure", "cutoff", "incomplete")
CANDIDATE_SOURCES = ("user_supplied", "generated")

#: fixed language required inside RecommendationResult.run_limitations
REQUIRED_LIMITATION_PHRASE = (
    "best-performing action among the candidates tested"
)
#: exactly one result-provenance label must appear as a whole token
RESULT_PROVENANCE_LABELS = (
    "deterministic", "live_model", "synthetic_infrastructure"
)

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_METRIC_REF_RE = re.compile(r"^(event|state):\S+$")
_PROVENANCE_LABEL_RE = re.compile(
    r"(?<![a-z0-9_])(" + "|".join(RESULT_PROVENANCE_LABELS) + r")(?![a-z0-9_])"
)
#: a "measurable shape" criterion must contain at least one identifier-like
#: token that downstream evaluators can bind to
_MEASURABLE_TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")

# sidecar component names every snapshot manifest must account for
SIDECAR_COMPONENTS = (
    "sidecar.rng",
    "sidecar.engine_cursor",
    "sidecar.model_config",
    "sidecar.compiler_artifact_hash",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationIssue:
    """One structural or semantic defect: where, what kind, and why."""

    path: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: [{self.code}] {self.message}"


class ContractValidationError(ValueError):
    """Raised with the COMPLETE list of collected issues -- never just the
    first one, and never after a silent repair."""

    def __init__(self, issues) -> None:
        self.issues = tuple(issues)
        detail = "; ".join(str(issue) for issue in self.issues)
        super().__init__(
            f"{len(self.issues)} contract validation issue(s): {detail}")

    def codes(self) -> tuple:
        return tuple(issue.code for issue in self.issues)

    def paths(self) -> tuple:
        return tuple(issue.path for issue in self.issues)


class IssueCollector:
    """Accumulates issues so callers can report everything at once."""

    def __init__(self) -> None:
        self._items: list = []

    def add(self, path: str, code: str, message: str) -> None:
        self._items.append(ValidationIssue(path, code, message))

    def extend(self, issues) -> None:
        self._items.extend(issues)

    @property
    def items(self) -> tuple:
        return tuple(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def raise_if_any(self) -> None:
        if self._items:
            raise ContractValidationError(self._items)


# ---------------------------------------------------------------------------
# Primitive field checks (collect-all style: return parsed value or None)
# ---------------------------------------------------------------------------

def _check_str(value, path, issues, *, allow_blank=False):
    if not isinstance(value, str):
        issues.add(path, "wrong_type",
                   f"expected string, got {type(value).__name__}")
        return None
    if not allow_blank and not value.strip():
        issues.add(path, "invalid_value", "string must not be empty or blank")
        return None
    return value


def _check_slug(value, path, issues):
    if not isinstance(value, str):
        issues.add(path, "wrong_type",
                   f"expected identifier string, got {type(value).__name__}")
        return None
    if not _SLUG_RE.match(value):
        issues.add(path, "invalid_id",
                   f"identifier {value!r} must match {_SLUG_RE.pattern}")
        return None
    return value


def _check_bool(value, path, issues):
    if type(value) is not bool:
        issues.add(path, "wrong_type",
                   f"expected boolean, got {type(value).__name__}")
        return None
    return value


def _check_status_value(value, path, issues):
    """validation_status values: boolean flags plus short string indicators
    (e.g. which metric decided a ranking — review finding D4). Widened from
    booleans-only; recorded in DECISIONS.md 2026-08-03 (#4 companion fixes)."""
    if type(value) is bool:
        return value
    if type(value) is str and 0 < len(value) <= 120:
        return value
    issues.add(path, "wrong_type",
               f"expected boolean or short string, got {type(value).__name__}")
    return None


def _check_int(value, path, issues, *, minimum=None):
    if type(value) is not int:  # bool is deliberately excluded
        issues.add(path, "wrong_type",
                   f"expected integer, got {type(value).__name__}")
        return None
    if minimum is not None and value < minimum:
        issues.add(path, "invalid_value", f"must be >= {minimum}")
        return None
    return value


def _check_number(value, path, issues, *, minimum=None):
    if type(value) not in (int, float):
        issues.add(path, "wrong_type",
                   f"expected number, got {type(value).__name__}")
        return None
    if isinstance(value, float) and not math.isfinite(value):
        issues.add(path, "invalid_value", "number must be finite")
        return None
    if minimum is not None and value < minimum:
        issues.add(path, "invalid_value", f"must be >= {minimum}")
        return None
    return value


def _check_metric_scalar(value, path, issues):
    """A measured value: bool or finite number (never a string)."""
    if type(value) is bool:
        return value
    if type(value) in (int, float):
        if isinstance(value, float) and not math.isfinite(value):
            issues.add(path, "invalid_value", "number must be finite")
            return None
        return value
    issues.add(path, "wrong_type",
               f"expected boolean or number, got {type(value).__name__}")
    return None


def _check_enum(value, path, issues, allowed, label):
    if not isinstance(value, str):
        issues.add(path, "wrong_type",
                   f"expected string {label}, got {type(value).__name__}")
        return None
    if value not in allowed:
        issues.add(path, "invalid_enum",
                   f"{value!r} is not a valid {label}; allowed: "
                   f"{', '.join(allowed)}")
        return None
    return value


def _check_datetime(value, path, issues):
    """Strict timezone-aware ISO-8601 parse; returns an aware datetime."""
    if not isinstance(value, str):
        issues.add(path, "wrong_type",
                   f"expected ISO-8601 string, got {type(value).__name__}")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        issues.add(path, "invalid_datetime",
                   f"{value!r} is not valid ISO-8601")
        return None
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        issues.add(path, "naive_datetime",
                   f"{value!r} must carry an explicit timezone offset")
        return None
    return parsed


def canonical_time(moment: datetime) -> str:
    """Canonical serialized form: UTC, ISO-8601, trailing 'Z'."""
    return moment.astimezone(timezone.utc).isoformat().replace(
        "+00:00", "Z")


def _check_str_tuple(value, path, issues, *, allow_empty=True, slug=False,
                     unique=False, allow_blank_items=False):
    if not isinstance(value, list):
        issues.add(path, "wrong_type",
                   f"expected list, got {type(value).__name__}")
        return None
    if not allow_empty and not value:
        issues.add(path, "empty_collection", "list must not be empty")
        return None
    out = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        parsed = (_check_slug(item, item_path, issues) if slug
                  else _check_str(item, item_path, issues,
                                  allow_blank=allow_blank_items))
        if parsed is not None:
            out.append(parsed)
    if unique and len(set(out)) != len(out):
        issues.add(path, "duplicate_id", "list items must be unique")
        return None
    if len(out) != len(value):
        return None
    return tuple(out)


def _check_json_tree(value, path, issues, *, depth=0):
    """Validate an opaque blob as a JSON-representable tree (str keys,
    finite numbers, no foreign objects).  Returns the value unchanged."""
    if depth > 32:
        issues.add(path, "invalid_value", "tree nesting exceeds depth 32")
        return None
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            issues.add(path, "invalid_value", "number must be finite")
            return None
        return value
    if isinstance(value, list):
        ok = True
        for index, item in enumerate(value):
            if _check_json_tree(item, f"{path}[{index}]", issues,
                                depth=depth + 1) is None and item is not None:
                ok = False
        return value if ok else None
    if isinstance(value, dict):
        ok = True
        for key, item in value.items():
            if not isinstance(key, str):
                issues.add(path, "wrong_type",
                           f"mapping key {key!r} must be a string")
                ok = False
                continue
            if _check_json_tree(item, f"{path}.{key}", issues,
                                depth=depth + 1) is None and item is not None:
                ok = False
        return value if ok else None
    issues.add(path, "wrong_type",
               f"value of type {type(value).__name__} is not "
               "JSON-representable")
    return None


def _check_scalar_map(value, path, issues, *, value_check, key_slug=False,
                      allow_empty=True):
    if not isinstance(value, dict):
        issues.add(path, "wrong_type",
                   f"expected mapping, got {type(value).__name__}")
        return None
    if not allow_empty and not value:
        issues.add(path, "empty_collection", "mapping must not be empty")
        return None
    out = {}
    ok = True
    for key, item in value.items():
        key_path = f"{path}.{key}"
        if key_slug:
            parsed_key = _check_slug(key, key_path, issues)
        else:
            parsed_key = _check_str(key, key_path, issues)
        if parsed_key is None:
            ok = False
            continue
        parsed_item = value_check(item, key_path, issues)
        if parsed_item is None and item is not None:
            ok = False
            continue
        out[parsed_key] = parsed_item
    return out if ok else None


def _require(data, key, path, issues):
    if key not in data:
        issues.add(f"{path}{key}", "missing_field",
                   f"required field {key!r} is missing")
        return False
    return True


def _reject_unknown(data, allowed, path, issues):
    for key in data:
        if key not in allowed:
            issues.add(f"{path}{key}", "unknown_field",
                       f"unknown field {key!r} is not part of this contract")


def _check_envelope(cls, data, issues):
    if _require(data, "contract_type", "", issues):
        raw = data["contract_type"]
        if not isinstance(raw, str):
            issues.add("contract_type", "wrong_type",
                       f"expected string, got {type(raw).__name__}")
        elif raw != cls.CONTRACT_TYPE:
            issues.add(
                "contract_type", "wrong_contract_type",
                f"expected contract_type {cls.CONTRACT_TYPE!r} but a "
                f"{raw!r} object was supplied")
    if _require(data, "schema_version", "", issues):
        raw = data["schema_version"]
        if type(raw) is not int:
            issues.add("schema_version", "wrong_type",
                       f"expected integer, got {type(raw).__name__}")
        elif raw < SCHEMA_VERSION:
            issues.add(
                "schema_version", "version_mismatch",
                f"schema_version {raw} is OLDER than the supported version "
                f"{SCHEMA_VERSION}; refusing to read without an explicit "
                "migration")
        elif raw > SCHEMA_VERSION:
            issues.add(
                "schema_version", "version_mismatch",
                f"schema_version {raw} is NEWER than the supported version "
                f"{SCHEMA_VERSION}; refusing to silently interpret it as "
                f"version {SCHEMA_VERSION}")


def _as_mapping(data):
    if not isinstance(data, Mapping):
        raise ContractValidationError([ValidationIssue(
            "", "wrong_type",
            f"expected a mapping, got {type(data).__name__}")])
    return dict(data)


# ---------------------------------------------------------------------------
# Canonical serialization mixin
# ---------------------------------------------------------------------------

class _Canonical:
    """Canonical JSON (sorted keys, compact separators) and sha256 identity."""

    def to_dict(self) -> dict:  # pragma: no cover - overridden everywhere
        raise NotImplementedError

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True,
                          separators=(",", ":"))

    def content_hash(self) -> str:
        return hashlib.sha256(
            self.canonical_json().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Support structures (embedded; no envelope of their own)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimeHorizon(_Canonical):
    """A [start, cutoff] window; cutoff must be strictly after start."""

    start: datetime
    cutoff: datetime

    def to_dict(self) -> dict:
        return {"start": canonical_time(self.start),
                "cutoff": canonical_time(self.cutoff)}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        _reject_unknown(value, ("start", "cutoff"), f"{path}.", issues)
        start = cutoff = None
        if _require(value, "start", f"{path}.", issues):
            start = _check_datetime(value["start"], f"{path}.start", issues)
        if _require(value, "cutoff", f"{path}.", issues):
            cutoff = _check_datetime(value["cutoff"], f"{path}.cutoff",
                                     issues)
        if start is not None and cutoff is not None and cutoff <= start:
            issues.add(f"{path}.cutoff", "invalid_value",
                       "cutoff must be strictly after start")
            return None
        if start is None or cutoff is None:
            return None
        return TimeHorizon(start=start, cutoff=cutoff)

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment <= self.cutoff


@dataclass(frozen=True)
class WorldActor(_Canonical):
    """One member of the cast; the identifier is code-owned."""

    actor_id: str
    name: str
    private_context: str

    def to_dict(self) -> dict:
        return {"actor_id": self.actor_id, "name": self.name,
                "private_context": self.private_context}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        _reject_unknown(value, ("actor_id", "name", "private_context"),
                        f"{path}.", issues)
        actor_id = name = context = None
        if _require(value, "actor_id", f"{path}.", issues):
            actor_id = _check_slug(value["actor_id"], f"{path}.actor_id",
                                   issues)
        if _require(value, "name", f"{path}.", issues):
            name = _check_str(value["name"], f"{path}.name", issues)
        if _require(value, "private_context", f"{path}.", issues):
            context = _check_str(value["private_context"],
                                 f"{path}.private_context", issues)
        if None in (actor_id, name, context):
            return None
        return WorldActor(actor_id=actor_id, name=name,
                          private_context=context)


@dataclass(frozen=True)
class StartingEvent(_Canonical):
    """A pre-start fact; visible_to holds code-resolved actor identifiers."""

    description: str
    visible_to: tuple
    time: datetime

    def to_dict(self) -> dict:
        return {"description": self.description,
                "visible_to": list(self.visible_to),
                "time": canonical_time(self.time)}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        _reject_unknown(value, ("description", "visible_to", "time"),
                        f"{path}.", issues)
        description = visible_to = time = None
        if _require(value, "description", f"{path}.", issues):
            description = _check_str(value["description"],
                                     f"{path}.description", issues)
        if _require(value, "visible_to", f"{path}.", issues):
            visible_to = _check_str_tuple(
                value["visible_to"], f"{path}.visible_to", issues,
                allow_empty=False, slug=True, unique=True)
        if _require(value, "time", f"{path}.", issues):
            time = _check_datetime(value["time"], f"{path}.time", issues)
        if None in (description, visible_to, time):
            return None
        return StartingEvent(description=description, visible_to=visible_to,
                             time=time)


@dataclass(frozen=True)
class InterventionInsertionPoint(_Canonical):
    """The single code-owned boundary where a candidate action enters."""

    actor_id: str

    def to_dict(self) -> dict:
        return {"actor_id": self.actor_id}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        _reject_unknown(value, ("actor_id",), f"{path}.", issues)
        actor_id = None
        if _require(value, "actor_id", f"{path}.", issues):
            actor_id = _check_slug(value["actor_id"], f"{path}.actor_id",
                                   issues)
        if actor_id is None:
            return None
        return InterventionInsertionPoint(actor_id=actor_id)


@dataclass(frozen=True)
class CompilerProvenance(_Canonical):
    """Sidecar record of what produced the compiled world; never
    actor-visible."""

    source: str
    version: str
    evidence_mode: str
    artifact_hashes: dict

    def to_dict(self) -> dict:
        return {"source": self.source, "version": self.version,
                "evidence_mode": self.evidence_mode,
                "artifact_hashes": dict(self.artifact_hashes)}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        allowed = ("source", "version", "evidence_mode", "artifact_hashes")
        _reject_unknown(value, allowed, f"{path}.", issues)
        source = version = mode = hashes = None
        if _require(value, "source", f"{path}.", issues):
            source = _check_str(value["source"], f"{path}.source", issues)
        if _require(value, "version", f"{path}.", issues):
            version = _check_str(value["version"], f"{path}.version", issues)
        if _require(value, "evidence_mode", f"{path}.", issues):
            mode = _check_str(value["evidence_mode"],
                              f"{path}.evidence_mode", issues,
                              allow_blank=True)
        if _require(value, "artifact_hashes", f"{path}.", issues):
            hashes = _check_scalar_map(
                value["artifact_hashes"], f"{path}.artifact_hashes", issues,
                value_check=_check_str)
        if None in (source, version, mode) or hashes is None:
            return None
        return CompilerProvenance(source=source, version=version,
                                  evidence_mode=mode,
                                  artifact_hashes=hashes)


@dataclass(frozen=True)
class CandidateProvenance(_Canonical):
    """Whether the candidate was supplied or generated, and by what."""

    source: str
    generator_config_hash: str

    def to_dict(self) -> dict:
        return {"source": self.source,
                "generator_config_hash": self.generator_config_hash}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        _reject_unknown(value, ("source", "generator_config_hash"),
                        f"{path}.", issues)
        source = config_hash = None
        if _require(value, "source", f"{path}.", issues):
            source = _check_enum(value["source"], f"{path}.source", issues,
                                 CANDIDATE_SOURCES, "candidate source")
        if _require(value, "generator_config_hash", f"{path}.", issues):
            config_hash = _check_str(
                value["generator_config_hash"],
                f"{path}.generator_config_hash", issues, allow_blank=True)
        if source == "generated" and config_hash is not None \
                and not config_hash:
            issues.add(f"{path}.generator_config_hash", "invalid_value",
                       "a generated candidate must carry its generator "
                       "configuration hash")
            return None
        if source is None or config_hash is None:
            return None
        return CandidateProvenance(source=source,
                                   generator_config_hash=config_hash)


@dataclass(frozen=True)
class EngineCursor(_Canonical):
    """Progress state a resumed run must restore exactly."""

    steps_completed: int
    remaining_budget: int
    premise_delivered: bool

    def to_dict(self) -> dict:
        return {"steps_completed": self.steps_completed,
                "remaining_budget": self.remaining_budget,
                "premise_delivered": self.premise_delivered}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        allowed = ("steps_completed", "remaining_budget",
                   "premise_delivered")
        _reject_unknown(value, allowed, f"{path}.", issues)
        steps = budget = premise = None
        if _require(value, "steps_completed", f"{path}.", issues):
            steps = _check_int(value["steps_completed"],
                               f"{path}.steps_completed", issues, minimum=0)
        if _require(value, "remaining_budget", f"{path}.", issues):
            budget = _check_int(value["remaining_budget"],
                                f"{path}.remaining_budget", issues,
                                minimum=0)
        if _require(value, "premise_delivered", f"{path}.", issues):
            premise = _check_bool(value["premise_delivered"],
                                  f"{path}.premise_delivered", issues)
        if steps is None or budget is None or premise is None:
            return None
        return EngineCursor(steps_completed=steps, remaining_budget=budget,
                            premise_delivered=premise)


def _check_rng_scalar(value, path, issues):
    if type(value) is int or isinstance(value, str):
        return value
    issues.add(path, "wrong_type",
               f"expected integer or string seed material, got "
               f"{type(value).__name__}")
    return None


@dataclass(frozen=True)
class SnapshotSidecar(_Canonical):
    """State the engine checkpoint does not capture but reproducibility
    requires."""

    rng: dict
    engine_cursor: EngineCursor
    model_config: dict
    compiler_artifact_hash: str

    def to_dict(self) -> dict:
        return {"rng": dict(self.rng),
                "engine_cursor": self.engine_cursor.to_dict(),
                "model_config": dict(self.model_config),
                "compiler_artifact_hash": self.compiler_artifact_hash}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        allowed = ("rng", "engine_cursor", "model_config",
                   "compiler_artifact_hash")
        _reject_unknown(value, allowed, f"{path}.", issues)
        rng = cursor = model = artifact = None
        if _require(value, "rng", f"{path}.", issues):
            rng = _check_scalar_map(value["rng"], f"{path}.rng", issues,
                                    value_check=_check_rng_scalar,
                                    allow_empty=False)
        if _require(value, "engine_cursor", f"{path}.", issues):
            cursor = EngineCursor.parse(value["engine_cursor"],
                                        f"{path}.engine_cursor", issues)
        if _require(value, "model_config", f"{path}.", issues):
            model = _check_scalar_map(value["model_config"],
                                      f"{path}.model_config", issues,
                                      value_check=_check_str)
        if _require(value, "compiler_artifact_hash", f"{path}.", issues):
            artifact = _check_str(value["compiler_artifact_hash"],
                                  f"{path}.compiler_artifact_hash", issues)
            if artifact is not None and not _HEX64_RE.match(artifact):
                issues.add(f"{path}.compiler_artifact_hash", "invalid_value",
                           "must be a 64-character lowercase hex sha256")
                artifact = None
        if rng is None or cursor is None or model is None or artifact is None:
            return None
        return SnapshotSidecar(rng=rng, engine_cursor=cursor,
                               model_config=model,
                               compiler_artifact_hash=artifact)


@dataclass(frozen=True)
class TraceEvent(_Canonical):
    """One committed event; the only licensed source of outcomes."""

    event_id: str
    description: str

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "description": self.description}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        _reject_unknown(value, ("event_id", "description"), f"{path}.",
                        issues)
        event_id = description = None
        if _require(value, "event_id", f"{path}.", issues):
            event_id = _check_str(value["event_id"], f"{path}.event_id",
                                  issues)
        if _require(value, "description", f"{path}.", issues):
            description = _check_str(value["description"],
                                     f"{path}.description", issues)
        if event_id is None or description is None:
            return None
        return TraceEvent(event_id=event_id, description=description)


@dataclass(frozen=True)
class MetricValue(_Canonical):
    """A measured value plus the event/state references it was computed
    from; a metric that cites nothing is rejected."""

    value: object
    computed_from: tuple

    def to_dict(self) -> dict:
        return {"value": self.value,
                "computed_from": list(self.computed_from)}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        _reject_unknown(value, ("value", "computed_from"), f"{path}.",
                        issues)
        measured = refs = None
        if _require(value, "value", f"{path}.", issues):
            measured = _check_metric_scalar(value["value"], f"{path}.value",
                                            issues)
        if _require(value, "computed_from", f"{path}.", issues):
            refs = _check_str_tuple(value["computed_from"],
                                    f"{path}.computed_from", issues,
                                    allow_empty=False, unique=True)
            if refs is not None:
                for index, ref in enumerate(refs):
                    if not _METRIC_REF_RE.match(ref):
                        issues.add(
                            f"{path}.computed_from[{index}]",
                            "invalid_value",
                            f"reference {ref!r} must look like "
                            "'event:<event_id>' or 'state:<key>'")
                        refs = None
                        break
        if measured is None or refs is None:
            return None
        return MetricValue(value=measured, computed_from=refs)


@dataclass(frozen=True)
class RankingEntry(_Canonical):
    """One ranked candidate with the metric values it was ranked on."""

    candidate_id: str
    metric_values: dict

    def to_dict(self) -> dict:
        return {"candidate_id": self.candidate_id,
                "metric_values": dict(self.metric_values)}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        _reject_unknown(value, ("candidate_id", "metric_values"),
                        f"{path}.", issues)
        candidate_id = metrics = None
        if _require(value, "candidate_id", f"{path}.", issues):
            candidate_id = _check_slug(value["candidate_id"],
                                       f"{path}.candidate_id", issues)
        if _require(value, "metric_values", f"{path}.", issues):
            metrics = _check_scalar_map(
                value["metric_values"], f"{path}.metric_values", issues,
                value_check=_check_metric_scalar, key_slug=True,
                allow_empty=False)
        if candidate_id is None or metrics is None:
            return None
        return RankingEntry(candidate_id=candidate_id, metric_values=metrics)


@dataclass(frozen=True)
class EvaluatorSpec(_Canonical):
    """Declared, code-owned outcome metrics: ranking follows these and
    nothing else."""

    primary_metric: str
    secondary_metrics: tuple

    def to_dict(self) -> dict:
        return {"primary_metric": self.primary_metric,
                "secondary_metrics": list(self.secondary_metrics)}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        _reject_unknown(value, ("primary_metric", "secondary_metrics"),
                        f"{path}.", issues)
        primary = secondary = None
        if _require(value, "primary_metric", f"{path}.", issues):
            primary = _check_slug(value["primary_metric"],
                                  f"{path}.primary_metric", issues)
        if _require(value, "secondary_metrics", f"{path}.", issues):
            secondary = _check_str_tuple(
                value["secondary_metrics"], f"{path}.secondary_metrics",
                issues, allow_empty=True, slug=True, unique=True)
        if primary is not None and secondary is not None \
                and primary in secondary:
            issues.add(f"{path}.secondary_metrics", "duplicate_id",
                       "secondary metrics must not repeat the primary "
                       "metric")
            return None
        if primary is None or secondary is None:
            return None
        return EvaluatorSpec(primary_metric=primary,
                             secondary_metrics=secondary)

    def all_metrics(self) -> tuple:
        return (self.primary_metric,) + tuple(self.secondary_metrics)


@dataclass(frozen=True)
class PlanActorConfig(_Canonical):
    """Instance configuration for one actor in an initialization plan."""

    actor_id: str
    name: str
    private_init_data: str

    def to_dict(self) -> dict:
        return {"actor_id": self.actor_id, "name": self.name,
                "private_init_data": self.private_init_data}

    @staticmethod
    def parse(value, path, issues):
        if not isinstance(value, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(value).__name__}")
            return None
        _reject_unknown(value, ("actor_id", "name", "private_init_data"),
                        f"{path}.", issues)
        actor_id = name = data = None
        if _require(value, "actor_id", f"{path}.", issues):
            actor_id = _check_slug(value["actor_id"], f"{path}.actor_id",
                                   issues)
        if _require(value, "name", f"{path}.", issues):
            name = _check_str(value["name"], f"{path}.name", issues)
        if _require(value, "private_init_data", f"{path}.", issues):
            data = _check_str(value["private_init_data"],
                              f"{path}.private_init_data", issues,
                              allow_blank=True)
        if actor_id is None or name is None or data is None:
            return None
        return PlanActorConfig(actor_id=actor_id, name=name,
                               private_init_data=data)


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionProblem(_Canonical):
    """The product question: whose action is being chosen, toward what
    outcome, under which constraints and window."""

    CONTRACT_TYPE: ClassVar[str] = "decision_problem"
    _FIELDS: ClassVar[tuple] = (
        "contract_type", "schema_version", "problem_id", "decision_owner",
        "desired_outcome", "success_criteria", "constraints", "time_horizon",
        "relevant_context", "candidate_interventions",
        "candidate_generation_permission")

    problem_id: str
    decision_owner: str
    desired_outcome: str
    success_criteria: str
    constraints: tuple
    time_horizon: TimeHorizon
    relevant_context: str
    candidate_interventions: tuple
    candidate_generation_permission: bool

    def to_dict(self) -> dict:
        return {
            "contract_type": self.CONTRACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "problem_id": self.problem_id,
            "decision_owner": self.decision_owner,
            "desired_outcome": self.desired_outcome,
            "success_criteria": self.success_criteria,
            "constraints": list(self.constraints),
            "time_horizon": self.time_horizon.to_dict(),
            "relevant_context": self.relevant_context,
            "candidate_interventions": list(self.candidate_interventions),
            "candidate_generation_permission":
                self.candidate_generation_permission,
        }

    @classmethod
    def from_dict(cls, data) -> "DecisionProblem":
        data = _as_mapping(data)
        issues = IssueCollector()
        _check_envelope(cls, data, issues)
        _reject_unknown(data, cls._FIELDS, "", issues)
        problem_id = owner = outcome = criteria = None
        constraints = horizon = context = supplied = permission = None
        if _require(data, "problem_id", "", issues):
            problem_id = _check_slug(data["problem_id"], "problem_id",
                                     issues)
        if _require(data, "decision_owner", "", issues):
            owner = _check_str(data["decision_owner"], "decision_owner",
                               issues)
        if _require(data, "desired_outcome", "", issues):
            outcome = _check_str(data["desired_outcome"], "desired_outcome",
                                 issues)
        if _require(data, "success_criteria", "", issues):
            criteria = _check_str(data["success_criteria"],
                                  "success_criteria", issues)
        if _require(data, "constraints", "", issues):
            constraints = _check_str_tuple(data["constraints"],
                                           "constraints", issues)
        if _require(data, "time_horizon", "", issues):
            horizon = TimeHorizon.parse(data["time_horizon"], "time_horizon",
                                        issues)
        if _require(data, "relevant_context", "", issues):
            context = _check_str(data["relevant_context"],
                                 "relevant_context", issues,
                                 allow_blank=True)
        if _require(data, "candidate_interventions", "", issues):
            supplied = _check_str_tuple(data["candidate_interventions"],
                                        "candidate_interventions", issues)
        if _require(data, "candidate_generation_permission", "", issues):
            permission = _check_bool(
                data["candidate_generation_permission"],
                "candidate_generation_permission", issues)
        issues.raise_if_any()
        return cls(problem_id=problem_id, decision_owner=owner,
                   desired_outcome=outcome, success_criteria=criteria,
                   constraints=constraints, time_horizon=horizon,
                   relevant_context=context,
                   candidate_interventions=supplied,
                   candidate_generation_permission=permission)


@dataclass(frozen=True)
class CompiledDecisionWorld(_Canonical):
    """The validated starting world: cast, contexts, pre-start facts,
    window, criteria, the single insertion boundary, and provenance."""

    CONTRACT_TYPE: ClassVar[str] = "compiled_decision_world"
    _FIELDS: ClassVar[tuple] = (
        "contract_type", "schema_version", "world_id", "actors",
        "shared_context", "starting_events", "start_time", "cutoff",
        "success_criteria", "intervention_insertion_point",
        "compiler_provenance")

    world_id: str
    actors: tuple
    shared_context: str
    starting_events: tuple
    start_time: datetime
    cutoff: datetime
    success_criteria: str
    intervention_insertion_point: InterventionInsertionPoint
    compiler_provenance: CompilerProvenance

    def to_dict(self) -> dict:
        return {
            "contract_type": self.CONTRACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "world_id": self.world_id,
            "actors": [actor.to_dict() for actor in self.actors],
            "shared_context": self.shared_context,
            "starting_events": [event.to_dict()
                                for event in self.starting_events],
            "start_time": canonical_time(self.start_time),
            "cutoff": canonical_time(self.cutoff),
            "success_criteria": self.success_criteria,
            "intervention_insertion_point":
                self.intervention_insertion_point.to_dict(),
            "compiler_provenance": self.compiler_provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, data) -> "CompiledDecisionWorld":
        data = _as_mapping(data)
        issues = IssueCollector()
        _check_envelope(cls, data, issues)
        _reject_unknown(data, cls._FIELDS, "", issues)
        world_id = shared = criteria = None
        start = cutoff = insertion = provenance = None
        actors: list = []
        events: list = []
        if _require(data, "world_id", "", issues):
            world_id = _check_slug(data["world_id"], "world_id", issues)
        if _require(data, "actors", "", issues):
            raw_actors = data["actors"]
            if not isinstance(raw_actors, list):
                issues.add("actors", "wrong_type",
                           f"expected list, got {type(raw_actors).__name__}")
            elif not raw_actors:
                issues.add("actors", "empty_collection",
                           "a world must declare at least one actor")
            else:
                for index, raw in enumerate(raw_actors):
                    actor = WorldActor.parse(raw, f"actors[{index}]", issues)
                    if actor is not None:
                        actors.append(actor)
                ids = [actor.actor_id for actor in actors]
                if len(set(ids)) != len(ids):
                    issues.add("actors", "duplicate_id",
                               "actor identifiers must be unique")
                names = [actor.name for actor in actors]
                if len(set(names)) != len(names):
                    issues.add(
                        "actors", "duplicate_id",
                        "actor names must be unique so name references "
                        "resolve without ambiguity")
        if _require(data, "shared_context", "", issues):
            shared = _check_str(data["shared_context"], "shared_context",
                                issues, allow_blank=True)
        if _require(data, "starting_events", "", issues):
            raw_events = data["starting_events"]
            if not isinstance(raw_events, list):
                issues.add("starting_events", "wrong_type",
                           f"expected list, got {type(raw_events).__name__}")
            else:
                for index, raw in enumerate(raw_events):
                    event = StartingEvent.parse(
                        raw, f"starting_events[{index}]", issues)
                    if event is not None:
                        events.append(event)
        if _require(data, "start_time", "", issues):
            start = _check_datetime(data["start_time"], "start_time", issues)
        if _require(data, "cutoff", "", issues):
            cutoff = _check_datetime(data["cutoff"], "cutoff", issues)
        if start is not None and cutoff is not None and cutoff <= start:
            issues.add("cutoff", "invalid_value",
                       "cutoff must be strictly after start_time")
        if _require(data, "success_criteria", "", issues):
            criteria = _check_str(data["success_criteria"],
                                  "success_criteria", issues)
        if _require(data, "intervention_insertion_point", "", issues):
            insertion = InterventionInsertionPoint.parse(
                data["intervention_insertion_point"],
                "intervention_insertion_point", issues)
        if _require(data, "compiler_provenance", "", issues):
            provenance = CompilerProvenance.parse(
                data["compiler_provenance"], "compiler_provenance", issues)
        issues.raise_if_any()
        return cls(world_id=world_id, actors=tuple(actors),
                   shared_context=shared, starting_events=tuple(events),
                   start_time=start, cutoff=cutoff,
                   success_criteria=criteria,
                   intervention_insertion_point=insertion,
                   compiler_provenance=provenance)

    def actor_ids(self) -> tuple:
        return tuple(actor.actor_id for actor in self.actors)

    def horizon(self) -> TimeHorizon:
        return TimeHorizon(start=self.start_time, cutoff=self.cutoff)


@dataclass(frozen=True)
class InterventionCandidate(_Canonical):
    """One candidate action introduced at the world's insertion boundary."""

    CONTRACT_TYPE: ClassVar[str] = "intervention_candidate"
    _FIELDS: ClassVar[tuple] = (
        "contract_type", "schema_version", "candidate_id", "summary",
        "action", "decision_owner", "timing", "constraints", "provenance")

    candidate_id: str
    summary: str
    action: str
    decision_owner: str
    timing: datetime
    constraints: tuple
    provenance: CandidateProvenance

    def to_dict(self) -> dict:
        return {
            "contract_type": self.CONTRACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "summary": self.summary,
            "action": self.action,
            "decision_owner": self.decision_owner,
            "timing": canonical_time(self.timing),
            "constraints": list(self.constraints),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, data) -> "InterventionCandidate":
        data = _as_mapping(data)
        issues = IssueCollector()
        _check_envelope(cls, data, issues)
        _reject_unknown(data, cls._FIELDS, "", issues)
        candidate_id = summary = action = owner = None
        timing = constraints = provenance = None
        if _require(data, "candidate_id", "", issues):
            candidate_id = _check_slug(data["candidate_id"], "candidate_id",
                                       issues)
        if _require(data, "summary", "", issues):
            summary = _check_str(data["summary"], "summary", issues)
        if _require(data, "action", "", issues):
            action = _check_str(data["action"], "action", issues)
        if _require(data, "decision_owner", "", issues):
            owner = _check_slug(data["decision_owner"], "decision_owner",
                                issues)
        if _require(data, "timing", "", issues):
            timing = _check_datetime(data["timing"], "timing", issues)
        if _require(data, "constraints", "", issues):
            constraints = _check_str_tuple(data["constraints"],
                                           "constraints", issues)
        if _require(data, "provenance", "", issues):
            provenance = CandidateProvenance.parse(data["provenance"],
                                                   "provenance", issues)
        issues.raise_if_any()
        return cls(candidate_id=candidate_id, summary=summary, action=action,
                   decision_owner=owner, timing=timing,
                   constraints=constraints, provenance=provenance)


@dataclass(frozen=True)
class SimulationSnapshot(_Canonical):
    """A whole-branch persisted unit: the engine checkpoint blob plus the
    sidecar, with a manifest naming every serialized component."""

    CONTRACT_TYPE: ClassVar[str] = "simulation_snapshot"
    _FIELDS: ClassVar[tuple] = (
        "contract_type", "schema_version", "snapshot_id", "world_id",
        "concordia_checkpoint", "sidecar", "snapshot_manifest")
    REQUIRED_CHECKPOINT_KEYS: ClassVar[tuple] = ("entities", "game_masters")

    snapshot_id: str
    world_id: str
    concordia_checkpoint: dict
    sidecar: SnapshotSidecar
    snapshot_manifest: tuple

    def to_dict(self) -> dict:
        return {
            "contract_type": self.CONTRACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": self.snapshot_id,
            "world_id": self.world_id,
            "concordia_checkpoint": copy.deepcopy(self.concordia_checkpoint),
            "sidecar": self.sidecar.to_dict(),
            "snapshot_manifest": list(self.snapshot_manifest),
        }

    @classmethod
    def from_dict(cls, data) -> "SimulationSnapshot":
        data = _as_mapping(data)
        issues = IssueCollector()
        _check_envelope(cls, data, issues)
        _reject_unknown(data, cls._FIELDS, "", issues)
        snapshot_id = world_id = checkpoint = sidecar = manifest = None
        if _require(data, "snapshot_id", "", issues):
            snapshot_id = _check_slug(data["snapshot_id"], "snapshot_id",
                                      issues)
        if _require(data, "world_id", "", issues):
            world_id = _check_slug(data["world_id"], "world_id", issues)
        if _require(data, "concordia_checkpoint", "", issues):
            raw = data["concordia_checkpoint"]
            if not isinstance(raw, dict):
                issues.add("concordia_checkpoint", "wrong_type",
                           f"expected mapping, got {type(raw).__name__}")
            else:
                checkpoint = copy.deepcopy(
                    _check_json_tree(raw, "concordia_checkpoint", issues))
                for key in cls.REQUIRED_CHECKPOINT_KEYS:
                    if key not in raw:
                        issues.add(f"concordia_checkpoint.{key}",
                                   "missing_field",
                                   f"checkpoint blob must contain {key!r}")
                        checkpoint = None
        if _require(data, "sidecar", "", issues):
            sidecar = SnapshotSidecar.parse(data["sidecar"], "sidecar",
                                            issues)
        if _require(data, "snapshot_manifest", "", issues):
            manifest = _check_str_tuple(data["snapshot_manifest"],
                                        "snapshot_manifest", issues,
                                        allow_empty=False, unique=True)
        issues.raise_if_any()
        return cls(snapshot_id=snapshot_id, world_id=world_id,
                   concordia_checkpoint=checkpoint, sidecar=sidecar,
                   snapshot_manifest=manifest)


@dataclass(frozen=True)
class BranchResult(_Canonical):
    """The measured outcome of one branch; metrics cite the events/state
    they were computed from."""

    CONTRACT_TYPE: ClassVar[str] = "branch_result"
    _FIELDS: ClassVar[tuple] = (
        "contract_type", "schema_version", "branch_id", "candidate_id",
        "world_id", "terminal_status", "terminal_world_state", "event_trace",
        "outcome_metrics", "infrastructure_errors", "token_stats",
        "runtime_stats", "artifact_paths")

    branch_id: str
    candidate_id: str
    world_id: str
    terminal_status: str
    terminal_world_state: dict
    event_trace: tuple
    outcome_metrics: dict
    infrastructure_errors: tuple
    token_stats: dict
    runtime_stats: dict
    artifact_paths: tuple

    def to_dict(self) -> dict:
        return {
            "contract_type": self.CONTRACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "branch_id": self.branch_id,
            "candidate_id": self.candidate_id,
            "world_id": self.world_id,
            "terminal_status": self.terminal_status,
            "terminal_world_state": copy.deepcopy(self.terminal_world_state),
            "event_trace": [event.to_dict() for event in self.event_trace],
            "outcome_metrics": {name: metric.to_dict()
                                for name, metric in
                                self.outcome_metrics.items()},
            "infrastructure_errors": list(self.infrastructure_errors),
            "token_stats": dict(self.token_stats),
            "runtime_stats": dict(self.runtime_stats),
            "artifact_paths": list(self.artifact_paths),
        }

    @classmethod
    def from_dict(cls, data) -> "BranchResult":
        data = _as_mapping(data)
        issues = IssueCollector()
        _check_envelope(cls, data, issues)
        _reject_unknown(data, cls._FIELDS, "", issues)
        branch_id = candidate_id = world_id = status = None
        state = metrics = tokens = runtime = None
        errors = paths = None
        trace: list = []
        if _require(data, "branch_id", "", issues):
            branch_id = _check_slug(data["branch_id"], "branch_id", issues)
        if _require(data, "candidate_id", "", issues):
            candidate_id = _check_slug(data["candidate_id"], "candidate_id",
                                       issues)
        if _require(data, "world_id", "", issues):
            world_id = _check_slug(data["world_id"], "world_id", issues)
        if _require(data, "terminal_status", "", issues):
            status = _check_enum(data["terminal_status"], "terminal_status",
                                 issues, TERMINAL_STATUSES,
                                 "terminal status")
        if _require(data, "terminal_world_state", "", issues):
            raw = data["terminal_world_state"]
            if not isinstance(raw, dict):
                issues.add("terminal_world_state", "wrong_type",
                           f"expected mapping, got {type(raw).__name__}")
            else:
                state = copy.deepcopy(
                    _check_json_tree(raw, "terminal_world_state", issues))
        if _require(data, "event_trace", "", issues):
            raw = data["event_trace"]
            if not isinstance(raw, list):
                issues.add("event_trace", "wrong_type",
                           f"expected list, got {type(raw).__name__}")
            else:
                for index, item in enumerate(raw):
                    event = TraceEvent.parse(item, f"event_trace[{index}]",
                                             issues)
                    if event is not None:
                        trace.append(event)
                ids = [event.event_id for event in trace]
                if len(set(ids)) != len(ids):
                    issues.add("event_trace", "duplicate_id",
                               "event identifiers must be unique")
        if _require(data, "outcome_metrics", "", issues):
            metrics = _check_scalar_map(
                data["outcome_metrics"], "outcome_metrics", issues,
                value_check=MetricValue.parse, key_slug=True)
        if _require(data, "infrastructure_errors", "", issues):
            errors = _check_str_tuple(data["infrastructure_errors"],
                                      "infrastructure_errors", issues)
        if _require(data, "token_stats", "", issues):
            tokens = _check_scalar_map(
                data["token_stats"], "token_stats", issues,
                value_check=lambda v, p, i: _check_int(v, p, i, minimum=0))
        if _require(data, "runtime_stats", "", issues):
            runtime = _check_scalar_map(
                data["runtime_stats"], "runtime_stats", issues,
                value_check=lambda v, p, i: _check_number(v, p, i,
                                                          minimum=0))
        if _require(data, "artifact_paths", "", issues):
            paths = _check_str_tuple(data["artifact_paths"],
                                     "artifact_paths", issues, unique=True)
        issues.raise_if_any()
        return cls(branch_id=branch_id, candidate_id=candidate_id,
                   world_id=world_id, terminal_status=status,
                   terminal_world_state=state, event_trace=tuple(trace),
                   outcome_metrics=metrics,
                   infrastructure_errors=errors, token_stats=tokens,
                   runtime_stats=runtime, artifact_paths=paths)


@dataclass(frozen=True)
class RecommendationResult(_Canonical):
    """The computed comparison: argmax under the declared criteria only,
    with mandatory fixed limitation language and provenance labeling."""

    CONTRACT_TYPE: ClassVar[str] = "recommendation_result"
    _FIELDS: ClassVar[tuple] = (
        "contract_type", "schema_version", "best_candidate_id", "ranking",
        "metric_differences", "downside_outcomes", "run_limitations",
        "validation_status")

    best_candidate_id: str
    ranking: tuple
    metric_differences: dict
    downside_outcomes: dict
    run_limitations: str
    validation_status: dict

    def to_dict(self) -> dict:
        return {
            "contract_type": self.CONTRACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "best_candidate_id": self.best_candidate_id,
            "ranking": [entry.to_dict() for entry in self.ranking],
            "metric_differences": {key: dict(value) for key, value in
                                   self.metric_differences.items()},
            "downside_outcomes": dict(self.downside_outcomes),
            "run_limitations": self.run_limitations,
            "validation_status": dict(self.validation_status),
        }

    @classmethod
    def from_dict(cls, data) -> "RecommendationResult":
        data = _as_mapping(data)
        issues = IssueCollector()
        _check_envelope(cls, data, issues)
        _reject_unknown(data, cls._FIELDS, "", issues)
        best = limitations = None
        differences = downsides = status_map = None
        ranking: list = []
        if _require(data, "best_candidate_id", "", issues):
            best = _check_slug(data["best_candidate_id"],
                               "best_candidate_id", issues)
        if _require(data, "ranking", "", issues):
            raw = data["ranking"]
            if not isinstance(raw, list):
                issues.add("ranking", "wrong_type",
                           f"expected list, got {type(raw).__name__}")
            elif not raw:
                issues.add("ranking", "empty_collection",
                           "ranking must contain at least one entry")
            else:
                for index, item in enumerate(raw):
                    entry = RankingEntry.parse(item, f"ranking[{index}]",
                                               issues)
                    if entry is not None:
                        ranking.append(entry)
                ids = [entry.candidate_id for entry in ranking]
                if len(set(ids)) != len(ids):
                    issues.add("ranking", "duplicate_id",
                               "ranked candidate identifiers must be unique")
        if _require(data, "metric_differences", "", issues):
            differences = _check_scalar_map(
                data["metric_differences"], "metric_differences", issues,
                value_check=lambda v, p, i: _check_scalar_map(
                    v, p, i,
                    value_check=lambda vv, pp, ii: _check_number(vv, pp, ii),
                    key_slug=True))
        if _require(data, "downside_outcomes", "", issues):
            downsides = _check_scalar_map(
                data["downside_outcomes"], "downside_outcomes", issues,
                value_check=_check_str, key_slug=True)
        if _require(data, "run_limitations", "", issues):
            limitations = _check_str(data["run_limitations"],
                                     "run_limitations", issues)
            if limitations is not None:
                if REQUIRED_LIMITATION_PHRASE not in limitations:
                    issues.add(
                        "run_limitations", "missing_phrase",
                        "run_limitations must contain the fixed phrase "
                        f"{REQUIRED_LIMITATION_PHRASE!r}")
                    limitations = None
                elif not _PROVENANCE_LABEL_RE.search(limitations):
                    issues.add(
                        "run_limitations", "missing_phrase",
                        "run_limitations must carry a result-provenance "
                        "label: one of "
                        f"{', '.join(RESULT_PROVENANCE_LABELS)}")
                    limitations = None
        if _require(data, "validation_status", "", issues):
            status_map = _check_scalar_map(
                data["validation_status"], "validation_status", issues,
                value_check=_check_status_value)
        issues.raise_if_any()
        return cls(best_candidate_id=best, ranking=tuple(ranking),
                   metric_differences=differences,
                   downside_outcomes=downsides,
                   run_limitations=limitations,
                   validation_status=status_map)


def _check_gm_scalar(value, path, issues):
    if type(value) in (str, bool, int):
        return value
    if type(value) is float:
        return _check_number(value, path, issues)
    issues.add(path, "wrong_type",
               f"expected scalar, got {type(value).__name__}")
    return None


@dataclass(frozen=True)
class ConcordiaInitializationPlan(_Canonical):
    """Internal, fully code-owned deterministic product of the adapter; its
    content hash is the equality target for manual-vs-compiled parity."""

    CONTRACT_TYPE: ClassVar[str] = "concordia_initialization_plan"
    _FIELDS: ClassVar[tuple] = (
        "contract_type", "schema_version", "plan_id", "world_id",
        "actor_configs", "shared_init_data", "gm_config", "neutral_premise",
        "initial_observations", "gm_initial_events", "run_limits",
        "intervention_insertion", "evaluator_spec", "compiler_provenance")

    plan_id: str
    world_id: str
    actor_configs: tuple
    shared_init_data: str
    gm_config: dict
    neutral_premise: str
    initial_observations: dict
    gm_initial_events: tuple
    run_limits: dict
    intervention_insertion: InterventionInsertionPoint
    evaluator_spec: EvaluatorSpec
    compiler_provenance: CompilerProvenance

    def to_dict(self) -> dict:
        return {
            "contract_type": self.CONTRACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "world_id": self.world_id,
            "actor_configs": [config.to_dict()
                              for config in self.actor_configs],
            "shared_init_data": self.shared_init_data,
            "gm_config": dict(self.gm_config),
            "neutral_premise": self.neutral_premise,
            "initial_observations": {key: list(value) for key, value in
                                     self.initial_observations.items()},
            "gm_initial_events": list(self.gm_initial_events),
            "run_limits": dict(self.run_limits),
            "intervention_insertion":
                self.intervention_insertion.to_dict(),
            "evaluator_spec": self.evaluator_spec.to_dict(),
            "compiler_provenance": self.compiler_provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, data) -> "ConcordiaInitializationPlan":
        data = _as_mapping(data)
        issues = IssueCollector()
        _check_envelope(cls, data, issues)
        _reject_unknown(data, cls._FIELDS, "", issues)
        plan_id = world_id = shared = premise = None
        gm_config = observations = limits = None
        insertion = evaluator = provenance = None
        gm_events = None
        configs: list = []
        if _require(data, "plan_id", "", issues):
            plan_id = _check_slug(data["plan_id"], "plan_id", issues)
        if _require(data, "world_id", "", issues):
            world_id = _check_slug(data["world_id"], "world_id", issues)
        if _require(data, "actor_configs", "", issues):
            raw = data["actor_configs"]
            if not isinstance(raw, list):
                issues.add("actor_configs", "wrong_type",
                           f"expected list, got {type(raw).__name__}")
            elif not raw:
                issues.add("actor_configs", "empty_collection",
                           "a plan must configure at least one actor")
            else:
                for index, item in enumerate(raw):
                    config = PlanActorConfig.parse(
                        item, f"actor_configs[{index}]", issues)
                    if config is not None:
                        configs.append(config)
                ids = [config.actor_id for config in configs]
                if len(set(ids)) != len(ids):
                    issues.add("actor_configs", "duplicate_id",
                               "actor identifiers must be unique")
        if _require(data, "shared_init_data", "", issues):
            shared = _check_str(data["shared_init_data"],
                                "shared_init_data", issues,
                                allow_blank=True)
        if _require(data, "gm_config", "", issues):
            gm_config = _check_scalar_map(data["gm_config"], "gm_config",
                                          issues,
                                          value_check=_check_gm_scalar)
        if _require(data, "neutral_premise", "", issues):
            premise = _check_str(data["neutral_premise"], "neutral_premise",
                                 issues)
        if _require(data, "initial_observations", "", issues):
            observations = _check_scalar_map(
                data["initial_observations"], "initial_observations",
                issues,
                value_check=lambda v, p, i: _check_str_tuple(v, p, i),
                key_slug=True)
        if _require(data, "gm_initial_events", "", issues):
            gm_events = _check_str_tuple(data["gm_initial_events"],
                                         "gm_initial_events", issues)
        if _require(data, "run_limits", "", issues):
            limits = _check_scalar_map(
                data["run_limits"], "run_limits", issues,
                value_check=lambda v, p, i: _check_int(v, p, i, minimum=0),
                key_slug=True, allow_empty=False)
        if _require(data, "intervention_insertion", "", issues):
            insertion = InterventionInsertionPoint.parse(
                data["intervention_insertion"], "intervention_insertion",
                issues)
        if _require(data, "evaluator_spec", "", issues):
            evaluator = EvaluatorSpec.parse(data["evaluator_spec"],
                                            "evaluator_spec", issues)
        if _require(data, "compiler_provenance", "", issues):
            provenance = CompilerProvenance.parse(
                data["compiler_provenance"], "compiler_provenance", issues)
        issues.raise_if_any()
        return cls(plan_id=plan_id, world_id=world_id,
                   actor_configs=tuple(configs), shared_init_data=shared,
                   gm_config=gm_config, neutral_premise=premise,
                   initial_observations=observations,
                   gm_initial_events=gm_events, run_limits=limits,
                   intervention_insertion=insertion,
                   evaluator_spec=evaluator,
                   compiler_provenance=provenance)


#: contract_type string -> class, for dispatching parsers
CONTRACT_CLASSES = {
    cls.CONTRACT_TYPE: cls for cls in (
        DecisionProblem, CompiledDecisionWorld, InterventionCandidate,
        SimulationSnapshot, BranchResult, RecommendationResult,
        ConcordiaInitializationPlan)
}
