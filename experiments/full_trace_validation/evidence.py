"""Evidence manifest: what the run was allowed to know, and how sure we are.

Experiment-only.  One entry per factual claim that reaches the compiler,
the actors, or the evaluator.  The manifest is written BEFORE simulation
and hashed into the freeze manifest, so a later artifact can never be
justified by evidence that was added afterwards.

Classification rules (deliberately conservative)
------------------------------------------------
``USER_SUPPLIED``
    The user of this experiment asserted it.  It is treated as true
    INSIDE the simulation and is not independently verified here.
``PUBLICLY_VERIFIED``
    A public, first-party-preferred, dated source states it and it was
    published before the window opens.  Only stable public-record facts
    qualify.
``TEST_ASSUMPTION``
    The harness or the compiler needs it for the scene to exist, but no
    source establishes it.  Anything about a real person's private
    personality, private compensation, inbox behaviour, calendar
    availability, internal opinions, or exact decision authority is a
    TEST_ASSUMPTION or UNKNOWN -- NEVER ``PUBLICLY_VERIFIED``, however
    plausible the inference from a public biography.
``UNKNOWN``
    Nobody involved knows it; recorded so its absence is visible.

``entered_context`` records where the claim actually went: ``shared``
(the compiled world's shared context), ``private:<actor>`` (that actor's
private context only), or ``none`` (recorded but never injected).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

CLASSIFICATIONS = ("USER_SUPPLIED", "PUBLICLY_VERIFIED", "TEST_ASSUMPTION",
                   "UNKNOWN")

ITEM_FIELDS = ("claim", "source", "date", "available_before_cutoff",
               "classification", "who_may_know", "used_by_compiler",
               "entered_context")

MANIFEST_VERSION = "evidence_manifest_v1"

#: subjects that may never be classified PUBLICLY_VERIFIED (see docstring)
UNVERIFIABLE_SUBJECTS = (
    "private personality", "private compensation", "inbox behaviour",
    "inbox behavior", "calendar availability", "internal opinion",
    "exact authority", "scheduling preference",
)


class EvidenceError(ValueError):
    """A manifest that does not satisfy the schema or the classification
    rules.  Carries every collected defect."""

    def __init__(self, defects) -> None:
        self.defects = list(defects)
        super().__init__("; ".join(self.defects))


def evidence_item(*, claim, source, date, available_before_cutoff,
                  classification, who_may_know, used_by_compiler,
                  entered_context) -> dict:
    """One manifest entry, in the fixed field order."""
    return {
        "claim": claim,
        "source": source,
        "date": date,
        "available_before_cutoff": available_before_cutoff,
        "classification": classification,
        "who_may_know": who_may_know,
        "used_by_compiler": used_by_compiler,
        "entered_context": entered_context,
    }


def _check_item(index, item, actor_names, defects) -> None:
    path = f"items[{index}]"
    if not isinstance(item, dict):
        defects.append(f"{path}: expected an object")
        return
    missing = [name for name in ITEM_FIELDS if name not in item]
    if missing:
        defects.append(f"{path}: missing fields {missing}")
    extra = sorted(set(item) - set(ITEM_FIELDS))
    if extra:
        defects.append(f"{path}: unknown fields {extra}")
    if missing or extra:
        return
    for name in ("claim", "source", "date", "entered_context"):
        if not isinstance(item[name], str) or not item[name].strip():
            defects.append(f"{path}.{name}: must be a non-empty string")
    for name in ("available_before_cutoff", "used_by_compiler"):
        if not isinstance(item[name], bool):
            defects.append(f"{path}.{name}: must be a boolean")
    if item["classification"] not in CLASSIFICATIONS:
        defects.append(
            f"{path}.classification: {item['classification']!r} is not "
            f"one of {list(CLASSIFICATIONS)}")
    who = item["who_may_know"]
    if who == "all":
        pass
    elif isinstance(who, list) and who:
        for name in who:
            if not isinstance(name, str) or not name.strip():
                defects.append(
                    f"{path}.who_may_know: entries must be non-empty "
                    "actor names or identifiers")
            elif actor_names and name not in actor_names:
                defects.append(
                    f"{path}.who_may_know: {name!r} is not a declared "
                    f"actor ({sorted(actor_names)})")
    else:
        defects.append(
            f"{path}.who_may_know: must be 'all' or a non-empty list of "
            "actor names/identifiers")
    entered = item.get("entered_context")
    if isinstance(entered, str):
        if entered not in ("shared", "none"):
            if not entered.startswith("private:"):
                defects.append(
                    f"{path}.entered_context: must be 'shared', 'none', "
                    f"or 'private:<actor>', got {entered!r}")
            else:
                actor = entered.split(":", 1)[1]
                if actor_names and actor not in actor_names:
                    defects.append(
                        f"{path}.entered_context: private context names "
                        f"unknown actor {actor!r}")
    if item.get("classification") == "PUBLICLY_VERIFIED":
        low = f"{item.get('claim', '')} {item.get('source', '')}".lower()
        for subject in UNVERIFIABLE_SUBJECTS:
            if subject in low:
                defects.append(
                    f"{path}.classification: a claim about "
                    f"{subject!r} may never be PUBLICLY_VERIFIED")
        if item.get("source", "").strip().lower() in (
                "inference", "assumption", "none", "n/a"):
            defects.append(
                f"{path}.source: PUBLICLY_VERIFIED requires a real "
                "source, not an inference")


def build_manifest(*, experiment_id, window_start, window_cutoff, items,
                   actor_names=(), notes="") -> dict:
    """Validate and assemble the evidence manifest.

    ``actor_names`` (when supplied) is the compiled cast; ``who_may_know``
    and ``private:<actor>`` references are checked against it so an
    evidence entry can never name an actor that does not exist.
    """
    defects: list = []
    actor_names = set(actor_names or ())
    if not isinstance(items, (list, tuple)) or not items:
        defects.append("items: at least one evidence item is required")
    else:
        for index, item in enumerate(items):
            _check_item(index, item, actor_names, defects)
        claims = [item.get("claim") for item in items
                  if isinstance(item, dict)]
        seen = set()
        for claim in claims:
            if claim in seen:
                defects.append(f"items: duplicate claim {claim!r}")
            seen.add(claim)
    if defects:
        raise EvidenceError(defects)

    counts: dict = {name: 0 for name in CLASSIFICATIONS}
    for item in items:
        counts[item["classification"]] += 1
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "experiment_id": experiment_id,
        "window": {"start": window_start, "cutoff": window_cutoff},
        "actor_names": sorted(actor_names),
        "classification_counts": counts,
        "classification_rules": {
            "USER_SUPPLIED": "asserted by the user of this experiment; "
                             "treated as true inside the simulation, not "
                             "independently verified here",
            "PUBLICLY_VERIFIED": "stated by a dated public source "
                                 "published before the window opens",
            "TEST_ASSUMPTION": "needed for the scene to exist; no source "
                               "establishes it",
            "UNKNOWN": "not known to anyone in this experiment; recorded "
                       "so the gap is visible",
        },
        "notes": notes,
        "items": [dict(item) for item in items],
    }
    return manifest


def manifest_sha256(manifest: dict) -> str:
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")).hexdigest()


def write_manifest(manifest: dict, path) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False)
                    + "\n", encoding="utf-8")
    return manifest_sha256(manifest)


def compiler_visible_items(manifest: dict) -> list:
    return [item for item in manifest["items"] if item["used_by_compiler"]]


def summary_line(manifest: dict) -> str:
    counts = manifest["classification_counts"]
    return ", ".join(f"{name}={counts[name]}" for name in CLASSIFICATIONS)
