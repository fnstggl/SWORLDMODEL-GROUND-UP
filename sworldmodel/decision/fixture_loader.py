"""Strict loader for the frozen manual fixtures.

``load_fixture_dict`` (pure stdlib) maps one already-parsed fixture mapping
into validated contracts: a ``CompiledDecisionWorld``, the
``InterventionCandidate`` list, the declared ``EvaluatorSpec``, the
deterministic expectations, and the engineering-test scaffolding blocks.
``load_fixture_file`` adds the file/YAML step and imports the YAML parser
lazily so the product package itself stays stdlib-only.

Accepted shape (everything else is rejected, never repaired):

- top level: ``fixture_id``, ``world``, ``candidates``, ``evaluator``,
  ``expected_deterministic`` (required); ``label``, ``decision_rule``,
  ``deterministic_script``, ``live_model_assertions``,
  ``infrastructure_assertions`` (optional).
- ``world``: ``start_time``, ``cutoff``, ``shared_context``,
  ``starting_events`` (required); ``actors`` (optional) plus two generic
  structural forms: any ``<prefix>_profiles`` key holding population
  profile blocks (expanded by code into ``<prefix>_NNN`` member actors with
  private context built verbatim from the stated fields), and any key whose
  value is a single inline actor mapping (exactly ``id``/``name``/
  ``private_context``).
- ``candidates[*]``: ``id``, ``actor_id``, ``time``, ``action``; any extra
  key whose value is a mapping is kept as an opaque per-candidate parameter
  block for the scripted test harness (never production logic); any other
  extra key is rejected.

All identifiers are code-validated; ``visible_to`` entries may be actor
identifiers or unique actor names and are resolved to identifiers (unknown
or ambiguous references are hard errors).  Every check collects into one
``ContractValidationError`` listing all defects.

File-format note: the two assertion blocks are free prose bullet lists for
humans and later live-run checks, and one frozen file's prose contains a
line-final colon that no conforming YAML parser accepts as a plain scalar.
The frozen files are immutable, so the accepted FILE format is defined to
match them: ``load_fixture_file`` extracts the assertion blocks textually
(column-0 ``<key>:`` line, ``  - `` bullets, 4-space continuations folded
with single spaces -- exactly YAML's plain-scalar folding) and parses the
remainder as strict YAML.  The extraction is deterministic and strict;
tests prove it byte-equivalent to YAML's own parse on files YAML can read.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping

from .contracts import (CompiledDecisionWorld, ContractValidationError,
                        EvaluatorSpec, InterventionCandidate, IssueCollector,
                        SCHEMA_VERSION, TERMINAL_STATUSES, ValidationIssue,
                        canonical_time, _check_datetime, _check_enum,
                        _check_int, _check_json_tree, _check_metric_scalar,
                        _check_slug, _check_str, _check_str_tuple)
from .registry import ContractRegistry
from .validation import validate_semantics

FIXTURE_LOADER_VERSION = "fixture_loader_v1"
FIXTURE_SOURCE = "manual_fixture"

_REQUIRED_TOP_KEYS = ("fixture_id", "world", "candidates", "evaluator",
                      "expected_deterministic")
_OPTIONAL_TOP_KEYS = ("label", "decision_rule", "deterministic_script",
                      "live_model_assertions", "infrastructure_assertions")
_WORLD_BASE_KEYS = ("start_time", "cutoff", "shared_context",
                    "starting_events", "actors")
_ACTOR_ENTRY_KEYS = ("id", "name", "private_context")
_EVENT_ENTRY_KEYS = ("description", "visible_to", "time")
_CANDIDATE_BASE_KEYS = ("id", "actor_id", "time", "action")
_EXPECTED_BASE_KEYS = ("ranking_first", "per_candidate")

_GROUP_KEY_RE = re.compile(r"^([a-z][a-z0-9_]*)_profiles$")
_METRIC_RANKING_KEY_RE = re.compile(r"^ranking_by_([a-z][a-z0-9_]*)$")
_SUMMARY_LIMIT = 120


@dataclass(frozen=True)
class ExpectedDeterministic:
    """The frozen deterministic expectations: required winner, exact
    per-candidate values, and any declared per-metric orderings."""

    ranking_first: str
    per_candidate: dict
    metric_rankings: dict


@dataclass(frozen=True)
class LoadedFixture:
    """Everything one frozen fixture provides, fully validated."""

    fixture_id: str
    label: object
    world: CompiledDecisionWorld
    candidates: tuple
    evaluator_spec: EvaluatorSpec
    decision_rule: object
    deterministic_script: object
    expected_deterministic: ExpectedDeterministic
    live_model_assertions: tuple
    infrastructure_assertions: tuple
    candidate_parameter_blocks: dict
    registry: ContractRegistry
    fixture_content_hash: str


#: assertion blocks are extracted textually before the YAML parse (see the
#: file-format note in the module docstring)
PROSE_BLOCK_KEYS = ("live_model_assertions", "infrastructure_assertions")


def extract_prose_blocks(text: str):
    """Split fixture text into (yaml_text, {key: [bullet, ...]}).

    A prose block starts at a column-0 line ``<key>:`` for a key in
    ``PROSE_BLOCK_KEYS`` and consumes ``  - `` bullets, 4-space
    continuation lines (folded with single spaces), blank lines, and
    indented comment lines, ending at the first line whose first character
    is not whitespace.  Any other line shape inside a block is a hard
    error -- never a guess.
    """
    kept: list = []
    blocks: dict = {}
    issues = IssueCollector()
    current = None  # (key, [[fragment, ...], ...])
    for number, line in enumerate(text.split("\n"), start=1):
        if current is not None:
            key, items = current
            stripped = line.strip()
            if line.startswith("  - "):
                items.append([line[4:].strip()])
                continue
            if line[:1].isspace() or not line:
                if not stripped or stripped.startswith("#"):
                    continue
                if line.startswith("    ") and items:
                    items[-1].append(stripped)
                    continue
                issues.add(f"{key} (line {number})", "invalid_value",
                           f"unrecognized line inside prose block: "
                           f"{line!r}")
                continue
            blocks[key] = [" ".join(fragments) for fragments in items]
            current = None
        head, _, tail = line.partition(":")
        if not line[:1].isspace() and _ == ":" and not tail.strip() \
                and head in PROSE_BLOCK_KEYS:
            if head in blocks:
                issues.add(head, "duplicate_id",
                           f"prose block {head!r} appears more than once")
            current = (head, [])
            continue
        kept.append(line)
    if current is not None:
        key, items = current
        blocks[key] = [" ".join(fragments) for fragments in items]
    issues.raise_if_any()
    return "\n".join(kept), blocks


def load_fixture_file(path) -> LoadedFixture:
    """Read and parse a fixture file, then defer to ``load_fixture_dict``.

    The YAML parser is imported lazily: it is a TEST-TIME dependency only
    (install the PyYAML package); the product package keeps zero runtime
    dependencies.
    """
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "load_fixture_file requires the PyYAML package to parse "
            "fixture files; it is a test-time dependency only (install "
            "with: pip install pyyaml). The product package itself stays "
            "stdlib-only; already-parsed mappings can be loaded with "
            "load_fixture_dict instead.") from exc
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    yaml_text, prose_blocks = extract_prose_blocks(text)
    data = yaml.safe_load(yaml_text)
    if not isinstance(data, Mapping):
        raise ContractValidationError([ValidationIssue(
            str(path), "wrong_type",
            f"fixture root must be a mapping, got {type(data).__name__}")])
    data = dict(data)
    for key, bullets in prose_blocks.items():
        if key in data:
            raise ContractValidationError([ValidationIssue(
                key, "duplicate_id",
                f"{key!r} appears both as a prose block and as a parsed "
                "document key")])
        data[key] = bullets
    return load_fixture_dict(data, source=str(path))


def load_fixture_dict(data, *, source: str = "<fixture>") -> LoadedFixture:
    """Strictly map one parsed fixture mapping into validated contracts."""
    if not isinstance(data, Mapping):
        raise ContractValidationError([ValidationIssue(
            source, "wrong_type",
            f"fixture root must be a mapping, got {type(data).__name__}")])
    data = dict(data)
    issues = IssueCollector()
    _check_json_tree(data, source, issues)
    issues.raise_if_any()

    for key in data:
        if key not in _REQUIRED_TOP_KEYS and key not in _OPTIONAL_TOP_KEYS:
            issues.add(key, "unknown_field",
                       f"unknown top-level fixture key {key!r}")
    for key in _REQUIRED_TOP_KEYS:
        if key not in data:
            issues.add(key, "missing_field",
                       f"required fixture key {key!r} is missing")
    issues.raise_if_any()

    fixture_id = _check_slug(data["fixture_id"], "fixture_id", issues)
    evaluator = EvaluatorSpec.parse(data["evaluator"], "evaluator", issues)

    world_parts = _parse_world_block(data["world"], issues)
    candidate_parts = _parse_candidates_block(data["candidates"], issues)

    label = None
    if "label" in data:
        label = _check_str(data["label"], "label", issues)
    decision_rule = None
    if "decision_rule" in data:
        decision_rule = _check_str(data["decision_rule"], "decision_rule",
                                   issues)
    live_assertions = ()
    if "live_model_assertions" in data:
        live_assertions = _check_str_tuple(
            data["live_model_assertions"], "live_model_assertions", issues,
            allow_empty=False) or ()
    infra_assertions = ()
    if "infrastructure_assertions" in data:
        infra_assertions = _check_str_tuple(
            data["infrastructure_assertions"], "infrastructure_assertions",
            issues, allow_empty=False) or ()

    issues.raise_if_any()

    candidate_ids = tuple(entry["id"] for entry in candidate_parts.entries)
    actor_ids = {actor["actor_id"] for actor in world_parts.actors}

    if len(set(candidate_ids)) != len(candidate_ids):
        issues.add("candidates", "duplicate_id",
                   "candidate identifiers must be unique")
    insertion_actor = None
    owners = {entry["actor_id"] for entry in candidate_parts.entries}
    if len(owners) > 1:
        issues.add("candidates", "owner_mismatch",
                   "all candidates must act through the world's single "
                   f"insertion actor, but several were named: "
                   f"{', '.join(sorted(owners))}")
    elif owners:
        insertion_actor = next(iter(owners))
        if insertion_actor not in actor_ids:
            issues.add("candidates", "unknown_reference",
                       f"insertion actor {insertion_actor!r} is not a "
                       "declared or expanded world actor")

    expected = _parse_expected_block(
        data["expected_deterministic"], candidate_ids, evaluator, issues)
    script = None
    if "deterministic_script" in data:
        script = _parse_script_block(data["deterministic_script"],
                                     actor_ids, candidate_ids, issues)
    issues.raise_if_any()

    content_hash = hashlib.sha256(
        json.dumps(data, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()
    world_id = "w_" + hashlib.sha256("|".join(
        (fixture_id, world_parts.start_iso,
         world_parts.cutoff_iso)).encode("utf-8")).hexdigest()[:12]
    secondary = ", ".join(evaluator.secondary_metrics) or "none"
    success_criteria = (
        "Outcome is measured by the declared code-owned evaluator, "
        "computed only from the recorded event trace and terminal world "
        f"state; primary metric: {evaluator.primary_metric}; secondary "
        f"metrics: {secondary}.")

    world = CompiledDecisionWorld.from_dict({
        "contract_type": CompiledDecisionWorld.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "world_id": world_id,
        "actors": world_parts.actors,
        "shared_context": world_parts.shared_context,
        "starting_events": world_parts.events,
        "start_time": world_parts.start_iso,
        "cutoff": world_parts.cutoff_iso,
        "success_criteria": success_criteria,
        "intervention_insertion_point": {"actor_id": insertion_actor},
        "compiler_provenance": {
            "source": FIXTURE_SOURCE,
            "version": FIXTURE_LOADER_VERSION,
            "evidence_mode": FIXTURE_SOURCE,
            "artifact_hashes": {"fixture_canonical_sha256": content_hash},
        },
    })
    candidates = tuple(
        InterventionCandidate.from_dict({
            "contract_type": InterventionCandidate.CONTRACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "candidate_id": entry["id"],
            "summary": _derive_summary(entry["action"]),
            "action": entry["action"],
            "decision_owner": entry["actor_id"],
            "timing": entry["time"],
            "constraints": [],
            "provenance": {"source": "user_supplied",
                           "generator_config_hash": ""},
        }) for entry in candidate_parts.entries)

    registry = ContractRegistry()
    registry.register_world(world)
    for candidate in candidates:
        registry.register_candidate(candidate, world.world_id)

    semantic_issues = IssueCollector()
    for target, kwargs in [(world, {})] + [
            (candidate, {"world_id": world.world_id})
            for candidate in candidates]:
        try:
            validate_semantics(target, registry, **kwargs)
        except ContractValidationError as exc:
            semantic_issues.extend(exc.issues)
    semantic_issues.raise_if_any()

    return LoadedFixture(
        fixture_id=fixture_id, label=label, world=world,
        candidates=candidates, evaluator_spec=evaluator,
        decision_rule=decision_rule, deterministic_script=script,
        expected_deterministic=expected,
        live_model_assertions=live_assertions,
        infrastructure_assertions=infra_assertions,
        candidate_parameter_blocks=candidate_parts.parameter_blocks,
        registry=registry, fixture_content_hash=content_hash)


# ---------------------------------------------------------------------------
# World block
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _WorldParts:
    actors: list
    shared_context: str
    events: list
    start_iso: str
    cutoff_iso: str


def _parse_world_block(block, issues) -> "_WorldParts":
    if not isinstance(block, dict):
        issues.add("world", "wrong_type",
                   f"expected mapping, got {type(block).__name__}")
        return _WorldParts([], "", [], "", "")
    start = cutoff = None
    if "start_time" not in block:
        issues.add("world.start_time", "missing_field",
                   "required field 'start_time' is missing")
    else:
        start = _check_datetime(block["start_time"], "world.start_time",
                                issues)
    if "cutoff" not in block:
        issues.add("world.cutoff", "missing_field",
                   "required field 'cutoff' is missing")
    else:
        cutoff = _check_datetime(block["cutoff"], "world.cutoff", issues)
    if start is not None and cutoff is not None and cutoff <= start:
        issues.add("world.cutoff", "invalid_value",
                   "cutoff must be strictly after start_time")
    shared = ""
    if "shared_context" not in block:
        issues.add("world.shared_context", "missing_field",
                   "required field 'shared_context' is missing")
    else:
        shared = _check_str(block["shared_context"], "world.shared_context",
                            issues) or ""

    actors: list = []
    for key, value in block.items():
        if key in _WORLD_BASE_KEYS and key != "actors":
            continue
        path = f"world.{key}"
        if key == "actors":
            actors.extend(_parse_actor_list(value, path, issues))
            continue
        group = _GROUP_KEY_RE.match(key)
        if group is not None:
            actors.extend(_expand_population(value, group.group(1), path,
                                             issues))
            continue
        if isinstance(value, dict) \
                and set(value.keys()) == set(_ACTOR_ENTRY_KEYS):
            parsed = _parse_actor_entry(value, path, issues)
            if parsed is not None:
                actors.append(parsed)
            continue
        issues.add(path, "unknown_field",
                   f"unknown world key {key!r}: not a base field, not a "
                   "'<prefix>_profiles' population block, and not an inline "
                   "actor mapping")

    events: list = []
    if "starting_events" not in block:
        issues.add("world.starting_events", "missing_field",
                   "required field 'starting_events' is missing")
    else:
        events = _parse_events(block["starting_events"], actors, start,
                               cutoff, issues)
    return _WorldParts(
        actors=actors, shared_context=shared, events=events,
        start_iso=canonical_time(start) if start is not None else "",
        cutoff_iso=canonical_time(cutoff) if cutoff is not None else "")


def _parse_actor_list(value, path, issues) -> list:
    if not isinstance(value, list) or not value:
        issues.add(path, "wrong_type",
                   "expected a non-empty list of actor entries")
        return []
    out = []
    for index, entry in enumerate(value):
        parsed = _parse_actor_entry(entry, f"{path}[{index}]", issues)
        if parsed is not None:
            out.append(parsed)
    return out


def _parse_actor_entry(entry, path, issues):
    if not isinstance(entry, dict):
        issues.add(path, "wrong_type",
                   f"expected mapping, got {type(entry).__name__}")
        return None
    for key in entry:
        if key not in _ACTOR_ENTRY_KEYS:
            issues.add(f"{path}.{key}", "unknown_field",
                       f"unknown actor field {key!r}")
    actor_id = name = context = None
    if "id" not in entry:
        issues.add(f"{path}.id", "missing_field", "actor 'id' is missing")
    else:
        actor_id = _check_slug(entry["id"], f"{path}.id", issues)
    if "name" not in entry:
        issues.add(f"{path}.name", "missing_field",
                   "actor 'name' is missing")
    else:
        name = _check_str(entry["name"], f"{path}.name", issues)
    if "private_context" not in entry:
        issues.add(f"{path}.private_context", "missing_field",
                   "actor 'private_context' is missing")
    else:
        context = _check_str(entry["private_context"],
                             f"{path}.private_context", issues)
    if None in (actor_id, name, context):
        return None
    return {"actor_id": actor_id, "name": name,
            "private_context": context.strip()}


def _render_stated_value(value) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(_render_stated_value(item) for item in value)
    return str(value)


def _expand_population(value, prefix, path, issues) -> list:
    """Expand explicit profile blocks into code-generated member actors:
    identifiers ``<prefix>_NNN`` assigned in declaration order, profile by
    count, with private context built verbatim from the stated fields."""
    if not isinstance(value, list) or not value:
        issues.add(path, "wrong_type",
                   "expected a non-empty list of profile blocks")
        return []
    members = []
    seen_profiles = set()
    member_index = 0
    for block_index, block in enumerate(value):
        block_path = f"{path}[{block_index}]"
        if not isinstance(block, dict):
            issues.add(block_path, "wrong_type",
                       f"expected mapping, got {type(block).__name__}")
            continue
        if "profile_id" not in block or "count" not in block:
            issues.add(block_path, "missing_field",
                       "profile blocks require 'profile_id' and 'count'")
            continue
        profile_id = _check_slug(block["profile_id"],
                                 f"{block_path}.profile_id", issues)
        count = _check_int(block["count"], f"{block_path}.count", issues,
                           minimum=1)
        if profile_id is None or count is None:
            continue
        if profile_id in seen_profiles:
            issues.add(f"{block_path}.profile_id", "duplicate_id",
                       f"profile {profile_id!r} appears more than once")
            continue
        seen_profiles.add(profile_id)
        stated = []
        bad = False
        for key, item in block.items():
            if key in ("profile_id", "count"):
                continue
            key_path = f"{block_path}.{key}"
            if _check_slug(key, key_path, issues) is None:
                bad = True
                continue
            if not _valid_stated_value(item):
                issues.add(key_path, "wrong_type",
                           "stated fields must be scalars or lists of "
                           "scalars")
                bad = True
                continue
            stated.append((key, item))
        if bad:
            continue
        for _ in range(count):
            member_id = f"{prefix}_{member_index:03d}"
            detail = "; ".join(f"{key}: {_render_stated_value(item)}"
                               for key, item in stated)
            context = (f"Member {member_index:03d} of population profile "
                       f"'{profile_id}' in group '{prefix}'.")
            if detail:
                context = f"{context} {detail}."
            members.append({"actor_id": member_id, "name": member_id,
                            "private_context": context})
            member_index += 1
    return members


def _valid_stated_value(value) -> bool:
    if type(value) is bool or type(value) in (int, float):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(
            not isinstance(item, (list, dict))
            and _valid_stated_value(item) for item in value)
    return False


def _parse_events(value, actors, start, cutoff, issues) -> list:
    if not isinstance(value, list):
        issues.add("world.starting_events", "wrong_type",
                   f"expected list, got {type(value).__name__}")
        return []
    by_id = {actor["actor_id"] for actor in actors}
    by_name: dict = {}
    for actor in actors:
        by_name.setdefault(actor["name"], []).append(actor["actor_id"])
    events = []
    for index, entry in enumerate(value):
        path = f"world.starting_events[{index}]"
        if not isinstance(entry, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(entry).__name__}")
            continue
        for key in entry:
            if key not in _EVENT_ENTRY_KEYS:
                issues.add(f"{path}.{key}", "unknown_field",
                           f"unknown event field {key!r}")
        missing = [key for key in _EVENT_ENTRY_KEYS if key not in entry]
        if missing:
            issues.add(path, "missing_field",
                       f"event fields missing: {', '.join(missing)}")
            continue
        description = _check_str(entry["description"],
                                 f"{path}.description", issues)
        moment = _check_datetime(entry["time"], f"{path}.time", issues)
        raw_refs = entry["visible_to"]
        resolved = []
        if not isinstance(raw_refs, list) or not raw_refs:
            issues.add(f"{path}.visible_to", "wrong_type",
                       "expected a non-empty list of actor references")
            continue
        ok = True
        for ref_index, ref in enumerate(raw_refs):
            ref_path = f"{path}.visible_to[{ref_index}]"
            if not isinstance(ref, str) or not ref.strip():
                issues.add(ref_path, "wrong_type",
                           "actor reference must be a non-empty string")
                ok = False
                continue
            if ref in by_id:
                resolved.append(ref)
                continue
            matches = by_name.get(ref, [])
            if len(matches) == 1:
                resolved.append(matches[0])
            elif len(matches) > 1:
                issues.add(ref_path, "unknown_reference",
                           f"actor name {ref!r} is ambiguous")
                ok = False
            else:
                issues.add(ref_path, "unknown_reference",
                           f"{ref!r} does not resolve to a declared actor "
                           "identifier or unique actor name")
                ok = False
        if description is None or moment is None or not ok:
            continue
        if start is not None and cutoff is not None \
                and not (start <= moment <= cutoff):
            issues.add(f"{path}.time", "timing_out_of_range",
                       "event time must fall inside [start_time, cutoff]")
            continue
        events.append({"description": description, "visible_to": resolved,
                       "time": canonical_time(moment)})
    return events


# ---------------------------------------------------------------------------
# Candidates block
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _CandidateParts:
    entries: list
    parameter_blocks: dict


def _parse_candidates_block(value, issues) -> "_CandidateParts":
    if not isinstance(value, list) or not value:
        issues.add("candidates", "wrong_type",
                   "expected a non-empty list of candidate entries")
        return _CandidateParts([], {})
    entries = []
    blocks: dict = {}
    for index, entry in enumerate(value):
        path = f"candidates[{index}]"
        if not isinstance(entry, dict):
            issues.add(path, "wrong_type",
                       f"expected mapping, got {type(entry).__name__}")
            continue
        missing = [key for key in _CANDIDATE_BASE_KEYS if key not in entry]
        if missing:
            issues.add(path, "missing_field",
                       f"candidate fields missing: {', '.join(missing)}")
            continue
        candidate_id = _check_slug(entry["id"], f"{path}.id", issues)
        actor_id = _check_slug(entry["actor_id"], f"{path}.actor_id",
                               issues)
        moment = _check_datetime(entry["time"], f"{path}.time", issues)
        action = _check_str(entry["action"], f"{path}.action", issues)
        extras: dict = {}
        ok = True
        for key, item in entry.items():
            if key in _CANDIDATE_BASE_KEYS:
                continue
            key_path = f"{path}.{key}"
            if isinstance(item, dict):
                if _check_slug(key, key_path, issues) is None:
                    ok = False
                    continue
                extras[key] = item
            else:
                issues.add(
                    key_path, "unknown_field",
                    f"unknown candidate key {key!r}; only mapping-valued "
                    "parameter blocks for the scripted test harness are "
                    "accepted beyond the base fields")
                ok = False
        if None in (candidate_id, actor_id, moment, action) or not ok:
            continue
        entries.append({"id": candidate_id, "actor_id": actor_id,
                        "time": canonical_time(moment),
                        "action": action.strip()})
        if extras:
            blocks[candidate_id] = extras
    return _CandidateParts(entries=entries, parameter_blocks=blocks)


def _derive_summary(action: str) -> str:
    collapsed = " ".join(action.split())
    return collapsed[:_SUMMARY_LIMIT]


# ---------------------------------------------------------------------------
# Expectation and script blocks (engineering-test scaffolding only)
# ---------------------------------------------------------------------------

def _parse_expected_block(value, candidate_ids, evaluator, issues):
    if not isinstance(value, dict):
        issues.add("expected_deterministic", "wrong_type",
                   f"expected mapping, got {type(value).__name__}")
        return None
    known_metrics = set(evaluator.all_metrics()) if evaluator else set()
    metric_rankings: dict = {}
    for key in value:
        if key in _EXPECTED_BASE_KEYS:
            continue
        match = _METRIC_RANKING_KEY_RE.match(key)
        if match is None:
            issues.add(f"expected_deterministic.{key}", "unknown_field",
                       f"unknown expectation key {key!r}")
            continue
        metric = match.group(1)
        if metric not in known_metrics:
            issues.add(f"expected_deterministic.{key}", "unknown_reference",
                       f"{metric!r} is not a declared evaluator metric")
            continue
        ordering = _check_str_tuple(value[key],
                                    f"expected_deterministic.{key}", issues,
                                    allow_empty=False, slug=True,
                                    unique=True)
        if ordering is not None:
            if set(ordering) != set(candidate_ids):
                issues.add(f"expected_deterministic.{key}",
                           "unknown_reference",
                           "ordering must cover exactly the declared "
                           "candidates")
            else:
                metric_rankings[metric] = ordering
    ranking_first = None
    if "ranking_first" not in value:
        issues.add("expected_deterministic.ranking_first", "missing_field",
                   "required field 'ranking_first' is missing")
    else:
        ranking_first = _check_slug(value["ranking_first"],
                                    "expected_deterministic.ranking_first",
                                    issues)
        if ranking_first is not None and candidate_ids \
                and ranking_first not in candidate_ids:
            issues.add("expected_deterministic.ranking_first",
                       "unknown_reference",
                       f"{ranking_first!r} is not a declared candidate")
    per_candidate: dict = {}
    if "per_candidate" not in value:
        issues.add("expected_deterministic.per_candidate", "missing_field",
                   "required field 'per_candidate' is missing")
    else:
        raw = value["per_candidate"]
        if not isinstance(raw, dict):
            issues.add("expected_deterministic.per_candidate", "wrong_type",
                       f"expected mapping, got {type(raw).__name__}")
        else:
            if candidate_ids and set(raw.keys()) != set(candidate_ids):
                issues.add(
                    "expected_deterministic.per_candidate",
                    "unknown_reference",
                    "expectations must cover exactly the declared "
                    f"candidates; got {sorted(raw.keys())}, declared "
                    f"{sorted(candidate_ids)}")
            for candidate_id, block in raw.items():
                block_path = ("expected_deterministic.per_candidate."
                              f"{candidate_id}")
                if not isinstance(block, dict) or not block:
                    issues.add(block_path, "wrong_type",
                               "expected a non-empty mapping of metric "
                               "expectations")
                    continue
                parsed_block: dict = {}
                for metric, expected_value in block.items():
                    metric_path = f"{block_path}.{metric}"
                    if metric == "terminal_status":
                        status = _check_enum(expected_value, metric_path,
                                             issues, TERMINAL_STATUSES,
                                             "terminal status")
                        if status is not None:
                            parsed_block[metric] = status
                        continue
                    if metric not in known_metrics:
                        issues.add(metric_path, "unknown_reference",
                                   f"{metric!r} is not a declared "
                                   "evaluator metric")
                        continue
                    scalar = _check_metric_scalar(expected_value,
                                                  metric_path, issues)
                    if scalar is not None:
                        parsed_block[metric] = scalar
                per_candidate[candidate_id] = parsed_block
    if issues:
        return None
    return ExpectedDeterministic(ranking_first=ranking_first,
                                 per_candidate=per_candidate,
                                 metric_rankings=metric_rankings)


def _parse_script_block(value, actor_ids, candidate_ids, issues):
    """Scripted responses are test scaffolding consumed only by the mock
    layer of the harness; here they are shape-checked (known actors, known
    candidates, mapping leaves) and passed through verbatim."""
    if not isinstance(value, dict) or not value:
        issues.add("deterministic_script", "wrong_type",
                   "expected a non-empty mapping keyed by actor identifier")
        return None
    for actor_id, per_candidate in value.items():
        actor_path = f"deterministic_script.{actor_id}"
        if actor_id not in actor_ids:
            issues.add(actor_path, "unknown_reference",
                       f"{actor_id!r} is not a declared world actor")
            continue
        if not isinstance(per_candidate, dict) or not per_candidate:
            issues.add(actor_path, "wrong_type",
                       "expected a non-empty mapping keyed by candidate "
                       "identifier")
            continue
        for candidate_id, leaf in per_candidate.items():
            leaf_path = f"{actor_path}.{candidate_id}"
            if candidate_id not in candidate_ids:
                issues.add(leaf_path, "unknown_reference",
                           f"{candidate_id!r} is not a declared candidate")
                continue
            if not isinstance(leaf, dict):
                issues.add(leaf_path, "wrong_type",
                           "expected a mapping of scripted response fields")
    if issues:
        return None
    return value
