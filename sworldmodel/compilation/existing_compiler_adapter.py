"""Deterministic adapter: existing compiled scene -> ``CompiledDecisionWorld``.

The production compiler (``compiler.scene_pipeline``, minimal_scene_v1)
emits a four-field scene manifest -- actors (name + private_context),
shared_context, starting_events (time + description + visible_to), and
resolution -- plus compile metadata (question, start, cutoff, compiler
version, evidence mode) and, when an ``out_dir`` was given, a persisted
artifact set.  This module maps that output into the frozen Phase 3
``CompiledDecisionWorld`` contract, the entry point of the proven
downstream chain (planner -> ``ConcordiaInitializationPlan`` -> builder ->
validated Concordia objects).  The adapter STOPS at the contract; it never
builds engine objects itself.

Guarantees (directive, "Exact compiler-to-Concordia mapping requirement"):

- **Pure deterministic code.**  No LLM call, no paraphrase, no summary, no
  inference of missing fields, no guessed identities, no silent defaults,
  no clock reads, no randomness.  Identical input -> byte-identical
  ``world.canonical_json()``.
- **Loud, complete failure.**  Malformed or incomplete input raises
  ``ContractValidationError`` carrying EVERY collected defect with a
  precise path; nothing is repaired or dropped silently.
- **No silent field discard.**  Every manifest field maps into the
  contract; every piece of surrounding compile metadata either maps, is
  hashed into ``compiler_provenance.artifact_hashes``, or is carried
  verbatim in the returned :class:`AdaptedScene` sidecar.  The complete
  field-by-field record is docs/engine_migration/COMPILER_TO_CONCORDIA_MAPPING.md.
- **Code-owned identities.**  Actor identifiers are derived from actor
  names by the fixed rule in :func:`derive_actor_ids` (lowercase,
  non-alphanumerics to underscores, declaration-order ``_2``/``_3``
  suffixes on collision).  A name the rule cannot express is refused --
  never replaced with an invented identity.
- **References resolve or fail before simulation.**  ``visible_to``
  entries must EXACTLY match a declared actor name (validated manifests
  already carry canonical names; the adapter never fuzzy-matches), and
  the caller-supplied insertion actor must resolve unambiguously to a
  cast member.
- **Documented contract narrowing.**  The manifest permits an event
  visible to no actor; the frozen contract requires at least one
  observer per starting event.  Such input is refused with an error
  naming this narrowing -- never mapped lossily.
- **Recorded, non-blocking hygiene.**  A starting event whose
  DESCRIPTION names a declared actor its ``visible_to`` leaves out is
  recorded as a labeled warning (:func:`visibility_incoherence_warnings`,
  :data:`VISIBILITY_WARNING_LABEL`) on ``AdaptedScene.warnings`` and in
  the sidecar -- never refused.  The shape is legitimate in worlds that
  deliberately narrate a one-sided act, and it is also the exact shape
  of the delivery defect the 2026-08-04 under-the-hood validation found,
  so it is surfaced rather than either ignored or rejected.

Input surfaces:

- :func:`adapt_compiled_scene`     -- manifest mapping + compile metadata.
- :func:`adapt_compiled_artifacts` -- a compiled ``out_dir`` artifact set
  (``final_scene_manifest.json`` + ``input.json`` +
  ``compiler_metrics.json``, exactly what the production pipeline
  persists and ``instantiate_compiled`` reads).

The manifest shape gate is the PRODUCTION one: ``validate_manifest_shape``
from ``compiler.scene_schema``, imported lazily inside the call so that
importing this package never imports the compiler package.  The compiler
package ``__init__`` transitively imports its LLM transport module; that
import is side-effect-free (module-level constants and definitions only --
no network, no file writes, no environment mutation), this module never
references any callable from it, and the isolation is proven by
tests/engine_compilation (import-graph and static-import tests).  Nothing
under ``compiler/`` is modified or re-implemented here.

Pure stdlib.  Importable everywhere ``sworldmodel`` is importable.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            ContractValidationError,
                                            IssueCollector, SCHEMA_VERSION,
                                            ValidationIssue, _SLUG_RE,
                                            _check_datetime,
                                            _check_json_tree, _check_str,
                                            canonical_time)
from sworldmodel.decision.validation import validate_semantics

ADAPTER_VERSION = "existing_compiler_adapter_v1"

#: ``compiler_provenance.source`` label for worlds mapped by this adapter
COMPILED_SCENE_SOURCE = "scene_compiler"

#: reserved ``artifact_hashes`` keys the adapter always writes itself
_RESERVED_HASH_KEYS = ("manifest_canonical_sha256", "question_sha256")

#: artifact files a complete compiled ``out_dir`` must contain
REQUIRED_ARTIFACT_FILES = ("input.json", "final_scene_manifest.json",
                           "compiler_metrics.json")
#: additional artifact files parsed into the sidecar when present
OPTIONAL_JSON_ARTIFACT_FILES = ("scene_manifest.json",
                                "corrected_scene_manifest.json",
                                "scene_review.json",
                                "normalization_report.json",
                                "validation_report.json",
                                "genesis_resolution_check.json",
                                "runtime_bindings.json")

_ID_CLEAN_RE = re.compile(r"[^a-z0-9]+")

#: label every visibility-incoherence finding carries.  HEURISTIC by
#: construction (see :func:`visibility_incoherence_warnings`) and recorded
#: as a warning, never a refusal.
VISIBILITY_WARNING_LABEL = "heuristic_visibility_incoherence"


@dataclass(frozen=True)
class AdaptedScene:
    """One adapter result: the validated contract world, the code-owned
    name-to-identifier binding, the sidecar of every piece of compile
    metadata the contract does not express (adapter-owned provenance; the
    caller persists it alongside the world if durability is wanted), and
    the recorded non-blocking warnings (also carried in the sidecar)."""

    world: CompiledDecisionWorld
    actor_id_by_name: dict
    sidecar: dict
    warnings: tuple = ()


def _names_an_actor(description: str, name: str) -> bool:
    """Whole-token occurrence of ``name`` inside ``description``.

    Deliberately narrow: the EXACT declared name only, bounded by
    non-alphanumeric characters on both sides (so "Ada" does not match
    inside "Adalyn" and "Duty Officer" does not match "Deputy Duty
    Officers"), case-sensitive because both strings come from the same
    manifest.  No first-name, nickname, initial, or fuzzy matching --
    an over-eager rule would flood every world with warnings and train
    readers to ignore them.
    """
    if not name:
        return False
    start = 0
    while True:
        index = description.find(name, start)
        if index == -1:
            return False
        before = description[index - 1] if index > 0 else " "
        after_index = index + len(name)
        after = (description[after_index]
                 if after_index < len(description) else " ")
        if not before.isalnum() and not after.isalnum():
            return True
        start = index + 1


def visibility_incoherence_warnings(events, actor_names,
                                    actor_id_by_name=None) -> tuple:
    """Starting events whose DESCRIPTION names an actor their
    ``visible_to`` leaves out.

    Why this is worth recording (2026-08-04 under-the-hood validation).
    A compiled cold-outreach world routinely ships a send event described
    as "A sends the prepared message to B" with ``visible_to: [A]`` --
    the production compiler's own prompt exemplar teaches that shape --
    so B is narrated as a participant in an event B never observes.  The
    event is then delivered to A only, A's model is told the send already
    happened, and the content can reach B only if A's own model chooses
    to restate it.  Nothing in the chain (scene validation, this adapter,
    the planner) noticed the mismatch.

    Why a WARNING and not a refusal.  The shape is legitimate in worlds
    where the description deliberately narrates a one-sided act (a
    private note ABOUT someone, an unsent draft, an observation of a
    third party).  Refusing would reject those worlds outright.  The
    finding is recorded, labeled :data:`VISIBILITY_WARNING_LABEL`, and
    left for the reader.

    ``events`` are the mapped starting-event payloads (description +
    resolved ``visible_to`` ids), ``actor_names`` maps actor_id -> name.
    Returns a deterministic tuple ordered by (event index, actor id).
    """
    del actor_id_by_name  # accepted for call-site symmetry; unused
    findings: list = []
    for index, event in enumerate(events):
        visible = set(event["visible_to"])
        description = event["description"]
        for actor_id in sorted(actor_names):
            if actor_id in visible:
                continue
            name = actor_names[actor_id]
            if not _names_an_actor(description, name):
                continue
            findings.append({
                "label": VISIBILITY_WARNING_LABEL,
                "event_index": index,
                "actor_id": actor_id,
                "actor_name": name,
                "visible_to": list(event["visible_to"]),
                "detail": (
                    f"starting event {index} names {name!r} in its "
                    "description but its visible_to does not include "
                    f"{actor_id!r}, so that actor is narrated as part of "
                    "an event it never observes. Heuristic and "
                    "non-blocking: a deliberately one-sided narration is "
                    "legitimate, but a send/receive event that should "
                    "have reached the named actor is a delivery defect "
                    "this warning is the only trace of."),
            })
    return tuple(findings)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def derive_actor_ids(names) -> dict:
    """Actor name -> stable code-owned identifier, declaration order.

    Fixed rule: lowercase the name, replace every non-alphanumeric run
    with one underscore, strip boundary underscores; on collision with an
    earlier actor's identifier append ``_2``, ``_3``, ... in declaration
    order.  A name the rule cannot express as a contract-valid identifier
    (empty after cleaning, leading non-letter, or over-long) is REFUSED
    with a precise error -- the adapter never invents an identity.
    Duplicate names are refused here so every name maps to exactly one
    identifier (the contract independently requires unique names).
    """
    issues = IssueCollector()
    taken: set = set()
    out: dict = {}
    for index, name in enumerate(names):
        path = f"actors[{index}].name"
        if not isinstance(name, str) or not name.strip():
            issues.add(path, "invalid_value",
                       "actor name must be a non-empty string")
            continue
        if name in out:
            issues.add(path, "duplicate_id",
                       f"actor name {name!r} is declared more than once; "
                       "names must be unique so references resolve without "
                       "ambiguity")
            continue
        base = _ID_CLEAN_RE.sub("_", name.lower()).strip("_")
        if not base or not _SLUG_RE.match(base):
            issues.add(path, "invalid_id",
                       f"cannot derive a contract-valid identifier from "
                       f"actor name {name!r}: the code-owned rule "
                       f"(lowercase; non-alphanumeric runs to underscores) "
                       f"yields {base!r}, which does not match "
                       f"{_SLUG_RE.pattern}; the adapter refuses to invent "
                       "an identity")
            continue
        actor_id = base
        suffix = 2
        while actor_id in taken:
            actor_id = f"{base}_{suffix}"
            suffix += 1
        if not _SLUG_RE.match(actor_id):
            issues.add(path, "invalid_id",
                       f"collision suffixing produced {actor_id!r}, which "
                       f"does not match {_SLUG_RE.pattern}")
            continue
        taken.add(actor_id)
        out[name] = actor_id
    issues.raise_if_any()
    return out


def _manifest_shape_errors(manifest) -> list:
    """The PRODUCTION manifest shape gate, imported lazily (see the
    module docstring for the import-isolation contract)."""
    try:
        from compiler.scene_schema import validate_manifest_shape
    except ImportError as exc:  # pragma: no cover - environment defect
        raise ContractValidationError([ValidationIssue(
            "manifest", "invalid_value",
            "the production manifest shape gate (compiler.scene_schema."
            f"validate_manifest_shape) is not importable: {exc!r}; the "
            "adapter refuses to substitute a weaker gate of its own")]
        ) from exc
    return validate_manifest_shape(manifest)


def adapt_compiled_scene(
    manifest,
    *,
    question: str,
    start: str,
    cutoff: str,
    insertion_actor: str,
    compiler_version: str,
    evidence_mode: str,
    extra_artifact_hashes: Mapping | None = None,
    extra_sidecar: Mapping | None = None,
) -> AdaptedScene:
    """Map one validated compiled scene into a ``CompiledDecisionWorld``.

    ``manifest`` is the four-field scene mapping exactly as the production
    compiler validated it (``final_scene_manifest.json`` semantics).
    ``question``/``start``/``cutoff`` are the compile inputs (``start``
    and ``cutoff`` timezone-aware ISO-8601 instants).  ``insertion_actor``
    names the single code-owned intervention boundary -- decision-layer
    metadata the manifest deliberately does not carry -- and must resolve
    unambiguously to a declared actor (exact name, or the derived
    identifier).  ``compiler_version`` and ``evidence_mode`` are recorded
    compile metadata (never defaulted here).  ``extra_artifact_hashes``
    merges caller-supplied artifact identity strings into the provenance
    sidecar; ``extra_sidecar`` merges additional metadata into the
    returned sidecar.  Raises ``ContractValidationError`` with every
    collected defect; never repairs.
    """
    issues = IssueCollector()
    question_checked = _check_str(question, "question", issues)
    start_dt = _check_datetime(start, "start", issues)
    cutoff_dt = _check_datetime(cutoff, "cutoff", issues)
    insertion_ref = _check_str(insertion_actor, "insertion_actor", issues)
    version = _check_str(compiler_version, "compiler_version", issues)
    mode = _check_str(evidence_mode, "evidence_mode", issues,
                      allow_blank=True)
    if start_dt is not None and cutoff_dt is not None \
            and cutoff_dt <= start_dt:
        issues.add("cutoff", "invalid_value",
                   "cutoff must be strictly after start")
    if extra_artifact_hashes is not None \
            and not isinstance(extra_artifact_hashes, Mapping):
        issues.add("extra_artifact_hashes", "wrong_type",
                   "expected a mapping of artifact identity strings, got "
                   f"{type(extra_artifact_hashes).__name__}")
    if extra_sidecar is not None and not isinstance(extra_sidecar, Mapping):
        issues.add("extra_sidecar", "wrong_type",
                   "expected a mapping, got "
                   f"{type(extra_sidecar).__name__}")
    issues.raise_if_any()

    # ---- manifest: production shape gate, then JSON-tree strictness ----
    shape_errors = _manifest_shape_errors(manifest)
    if shape_errors:
        raise ContractValidationError([
            ValidationIssue("manifest", "invalid_value", error)
            for error in shape_errors])
    _check_json_tree(manifest, "manifest", issues)
    issues.raise_if_any()

    # ---- code-owned identities --------------------------------------
    actor_id_by_name = derive_actor_ids(
        [actor["name"] for actor in manifest["actors"]])

    # ---- starting events: resolve references, preserve order ---------
    events_payload: list = []
    for index, event in enumerate(manifest["starting_events"]):
        path = f"starting_events[{index}]"
        references = event["visible_to"]
        if not references:
            issues.add(
                f"{path}.visible_to", "empty_collection",
                "this compiled scene declares an event visible to no "
                "actor, but the frozen decision contract requires every "
                "starting event to name at least one observing actor "
                "(StartingEvent.visible_to must be non-empty); the "
                "adapter refuses rather than dropping the event or "
                "inventing an observer -- recorded as a contract "
                "narrowing in docs/engine_migration/"
                "COMPILER_TO_CONCORDIA_MAPPING.md")
            continue
        resolved: list = []
        ok = True
        for ref_index, reference in enumerate(references):
            if reference in actor_id_by_name:
                resolved.append(actor_id_by_name[reference])
            else:
                ok = False
                issues.add(
                    f"{path}.visible_to[{ref_index}]", "unknown_reference",
                    f"{reference!r} does not exactly match any declared "
                    "actor name; the adapter maps validated scenes and "
                    "never fuzzy-matches or guesses actor identities")
        if ok:
            events_payload.append({"description": event["description"],
                                   "visible_to": resolved,
                                   "time": event["time"]})
    issues.raise_if_any()

    # ---- insertion boundary: caller-owned, must resolve --------------
    id_to_name = {actor_id: name
                  for name, actor_id in actor_id_by_name.items()}
    name_hit = actor_id_by_name.get(insertion_ref)
    id_hit = insertion_ref if insertion_ref in id_to_name else None
    insertion_id = None
    if name_hit is not None and id_hit is not None and name_hit != id_hit:
        issues.add("insertion_actor", "unknown_reference",
                   f"{insertion_ref!r} is ambiguous: it is the name of "
                   f"actor {name_hit!r} and the derived identifier of "
                   f"actor {id_to_name[id_hit]!r}; refusing to guess")
    elif name_hit is not None:
        insertion_id = name_hit
    elif id_hit is not None:
        insertion_id = id_hit
    else:
        issues.add("insertion_actor", "unknown_reference",
                   f"{insertion_ref!r} does not resolve to a declared "
                   "actor name or derived identifier; the insertion "
                   "boundary must belong to a member of the cast")
    issues.raise_if_any()

    # ---- identity and provenance -------------------------------------
    manifest_hash = _sha256_text(_canonical(manifest))
    question_hash = _sha256_text(question_checked)
    start_iso = canonical_time(start_dt)
    cutoff_iso = canonical_time(cutoff_dt)
    world_id = "w_" + _sha256_text("|".join((
        ADAPTER_VERSION, question_hash, start_iso, cutoff_iso,
        manifest_hash)))[:12]

    artifact_hashes = {"manifest_canonical_sha256": manifest_hash,
                       "question_sha256": question_hash}
    for key, value in dict(extra_artifact_hashes or {}).items():
        key_path = f"extra_artifact_hashes.{key}"
        if not isinstance(key, str) or not key.strip():
            issues.add(key_path, "invalid_value",
                       "artifact hash keys must be non-empty strings")
            continue
        if key in _RESERVED_HASH_KEYS:
            issues.add(key_path, "duplicate_id",
                       f"{key!r} is a reserved adapter-owned hash key")
            continue
        if not isinstance(value, str) or not value.strip():
            issues.add(key_path, "invalid_value",
                       "artifact hash values must be non-empty strings")
            continue
        artifact_hashes[key] = value
    issues.raise_if_any()

    # ---- the contract gate -------------------------------------------
    world = CompiledDecisionWorld.from_dict({
        "contract_type": CompiledDecisionWorld.CONTRACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "world_id": world_id,
        "actors": [{"actor_id": actor_id_by_name[actor["name"]],
                    "name": actor["name"],
                    "private_context": actor["private_context"]}
                   for actor in manifest["actors"]],
        "shared_context": manifest["shared_context"],
        "starting_events": events_payload,
        "start_time": start,
        "cutoff": cutoff,
        "success_criteria": manifest["resolution"],
        "intervention_insertion_point": {"actor_id": insertion_id},
        "compiler_provenance": {
            "source": COMPILED_SCENE_SOURCE,
            "version": version,
            "evidence_mode": mode,
            "artifact_hashes": artifact_hashes,
        },
    })
    validate_semantics(world)

    # ---- sidecar: everything the contract does not express -----------
    # Non-blocking hygiene (R2): record, never refuse.  Computed after
    # the contract gate so it reads the RESOLVED identifiers.
    warnings = visibility_incoherence_warnings(
        events_payload,
        {actor_id_by_name[actor["name"]]: actor["name"]
         for actor in manifest["actors"]})

    sidecar = {
        "adapter_version": ADAPTER_VERSION,
        "warnings": [dict(entry) for entry in warnings],
        "warning_counts": {VISIBILITY_WARNING_LABEL: len(warnings)},
        "compile_inputs": {
            "question": question_checked,
            "start": start,
            "cutoff": cutoff,
            "compiler_version": version,
            "evidence_mode": mode,
        },
        "canonical": {
            "world_id": world_id,
            "start_time": start_iso,
            "cutoff": cutoff_iso,
            "manifest_canonical_sha256": manifest_hash,
            "question_sha256": question_hash,
        },
        "actor_id_by_name": dict(actor_id_by_name),
        "insertion_actor_reference": insertion_ref,
        "insertion_actor_id": insertion_id,
    }
    for key, value in dict(extra_sidecar or {}).items():
        key_path = f"extra_sidecar.{key}"
        if not isinstance(key, str) or not key.strip():
            issues.add(key_path, "invalid_value",
                       "sidecar keys must be non-empty strings")
            continue
        if key in sidecar:
            issues.add(key_path, "duplicate_id",
                       f"{key!r} collides with an adapter-owned sidecar "
                       "key")
            continue
        if _check_json_tree(value, key_path, issues) is None \
                and value is not None:
            continue
        sidecar[key] = value
    issues.raise_if_any()

    return AdaptedScene(world=world,
                        actor_id_by_name=dict(actor_id_by_name),
                        sidecar=sidecar,
                        warnings=warnings)


def adapt_compiled_artifacts(out_dir, *, insertion_actor: str,
                             extra_sidecar: Mapping | None = None
                             ) -> AdaptedScene:
    """Map one persisted compiled artifact set into a
    ``CompiledDecisionWorld``.

    Reads exactly what the production pipeline persists: the validated
    ``final_scene_manifest.json`` (the manifest production instantiates
    from), the compile inputs from ``input.json``, and the recorded
    ``compiler_metrics.json``.  Every regular file in the directory is
    sha256-hashed into ``compiler_provenance.artifact_hashes`` (keyed by
    file name), and every known metadata file is carried verbatim in the
    sidecar under ``artifact_files`` -- nothing is silently dropped.

    Refused loudly (never repaired): a missing or unreadable required
    file; an artifact set whose metrics record no ``world_id`` (the
    marker the pipeline writes only for a completed compile); an
    internally inconsistent set (metrics vs input compiler version); a
    set whose ``validation_report.json`` records errors.
    """
    issues = IssueCollector()
    base = Path(out_dir)
    if not base.is_dir():
        raise ContractValidationError([ValidationIssue(
            "out_dir", "invalid_value",
            f"{str(out_dir)!r} is not a directory of compiled artifacts")])

    for file_name in REQUIRED_ARTIFACT_FILES:
        if not (base / file_name).is_file():
            issues.add(file_name, "missing_field",
                       f"a complete compiled artifact set requires "
                       f"{file_name!r}; an incomplete or failed compile "
                       "is not adaptable")
    issues.raise_if_any()

    parsed: dict = {}
    for file_name in REQUIRED_ARTIFACT_FILES + OPTIONAL_JSON_ARTIFACT_FILES:
        path = base / file_name
        if not path.is_file():
            continue
        try:
            parsed[file_name] = json.loads(
                path.read_text(encoding="utf-8"))
        except ValueError as exc:
            issues.add(file_name, "invalid_value",
                       f"not valid JSON: {exc}")
    issues.raise_if_any()

    input_data = parsed["input.json"]
    metrics = parsed["compiler_metrics.json"]
    for file_name, value in (("input.json", input_data),
                             ("compiler_metrics.json", metrics)):
        if not isinstance(value, Mapping):
            issues.add(file_name, "wrong_type",
                       f"expected a JSON object, got "
                       f"{type(value).__name__}")
    issues.raise_if_any()

    for key in ("question", "start", "cutoff", "compiler_version"):
        if key not in input_data:
            issues.add("input.json", "missing_field",
                       f"required compile-input key {key!r} is missing")
    if "world_id" not in metrics:
        issues.add("compiler_metrics.json", "invalid_value",
                   "the metrics record carries no 'world_id', the marker "
                   "the production pipeline writes only for a COMPLETED "
                   "compile; refusing to adapt an incomplete, abstained, "
                   "or failed artifact set")
    if "evidence_mode" not in metrics:
        issues.add("compiler_metrics.json", "missing_field",
                   "the metrics record carries no 'evidence_mode'")
    issues.raise_if_any()

    if metrics.get("compiler_version") != input_data["compiler_version"]:
        issues.add("compiler_metrics.json", "invalid_value",
                   "artifact set is internally inconsistent: metrics "
                   f"record compiler version "
                   f"{metrics.get('compiler_version')!r} but the compile "
                   f"input recorded {input_data['compiler_version']!r}")
    validation_report = parsed.get("validation_report.json")
    if isinstance(validation_report, Mapping) \
            and validation_report.get("errors"):
        issues.add("validation_report.json", "invalid_value",
                   "the artifact set records deterministic validation "
                   "errors; a scene that failed validation is not "
                   "adaptable: "
                   + "; ".join(str(error) for error in
                               validation_report["errors"][:4]))
    issues.raise_if_any()

    file_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(base.iterdir()) if path.is_file()}

    sidecar_extras = {"artifact_files": parsed}
    for key, value in dict(extra_sidecar or {}).items():
        if key in sidecar_extras:
            issues.add(f"extra_sidecar.{key}", "duplicate_id",
                       f"{key!r} collides with the artifact-set sidecar "
                       "key")
            continue
        sidecar_extras[key] = value
    issues.raise_if_any()

    return adapt_compiled_scene(
        parsed["final_scene_manifest.json"],
        question=input_data["question"],
        start=input_data["start"],
        cutoff=input_data["cutoff"],
        insertion_actor=insertion_actor,
        compiler_version=input_data["compiler_version"],
        evidence_mode=metrics["evidence_mode"],
        extra_artifact_hashes=file_hashes,
        extra_sidecar=sidecar_extras,
    )
