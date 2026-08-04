"""Shared reporting primitives: canonical serialization and run access.

Both report builders in this package serialize plain JSON trees.  The
canonical form is the same one the frozen contracts use for hashing --
sorted keys, compact separators, ASCII-safe -- so a report's content hash
is a pure function of its content: mapping insertion order, set iteration
order, and per-process hash salts can never leak into the bytes
(FAILURE_LEDGER ``hash-order-sensitive-state-comparison``).  Non-finite
numbers are refused, never encoded.

``require_run_attributes`` is the strict duck-typed gate over the
counterfactual run record (``CounterfactualRun`` or any equivalent): the
builders name exactly the attributes they read and refuse loudly when one
is missing, instead of importing and pinning a concrete class.

Pure stdlib; scenario-agnostic by construction (no scenario vocabulary
may ever appear in this package -- the hardcoding guard scans it on both
interpreters).
"""

from __future__ import annotations

import hashlib
import json

from sworldmodel.decision.contracts import (ContractValidationError,
                                            IssueCollector, ValidationIssue)


def canonical_json(tree) -> str:
    """Canonical JSON text of a plain tree: sorted keys, compact
    separators, ASCII-safe, non-finite numbers refused.

    Raises ``ContractValidationError`` when the tree is not
    JSON-serializable -- a report that cannot serialize deterministically
    is refused, never repaired.
    """
    try:
        return json.dumps(tree, sort_keys=True, separators=(",", ":"),
                          allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError([ValidationIssue(
            "", "invalid_value",
            "report content is not canonically JSON-serializable: "
            f"{type(exc).__name__}: {exc}")]) from exc


def canonical_content_hash(tree) -> str:
    """sha256 hex digest of the canonical JSON text."""
    return hashlib.sha256(canonical_json(tree).encode("utf-8")).hexdigest()


def require_run_attributes(run, attributes, issues: IssueCollector) -> bool:
    """Collect an issue for every named attribute the run record lacks;
    returns True when all are present."""
    ok = True
    for name in attributes:
        if not hasattr(run, name):
            issues.add(f"run.{name}", "missing_field",
                       "the counterfactual run record must expose "
                       f"{name!r} (see CounterfactualRun)")
            ok = False
    return ok
