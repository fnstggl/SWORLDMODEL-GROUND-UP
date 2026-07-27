"""Provenance: every meaningful claim says where it came from.

Compiler labels: verified | question_given | inferred |
model_memory_unverified | uncertain.  These map onto the kernel's duration/
rate bases without losing the original label (it is preserved in the note),
and `uncertain` is refused wherever a concrete number is consumed --
uncertainty never silently becomes fact.

In evidence-docs mode, `verified` additionally requires at least one valid
document citation on the item; without docs, `verified` is only acceptable
for claims stated by the question itself.
"""
from __future__ import annotations

#: compiler label -> kernel provenance basis (simclock.CONCRETE_BASES)
_KERNEL_BASIS = {
    "verified": "verified",
    "question_given": "verified",       # stated by the question: given, exact
    "inferred": "inferred",
    "model_memory_unverified": "inferred",
}


def kernel_basis(label: str) -> str:
    if label not in _KERNEL_BASIS:
        raise ValueError(f"label {label!r} cannot back a concrete value")
    return _KERNEL_BASIS[label]


def kernel_basis_any(label: str) -> str:
    """Like kernel_basis, but permits 'uncertain' where the kernel accepts
    an explicit 'unknown' (never where a concrete number is consumed)."""
    return "unknown" if label == "uncertain" else kernel_basis(label)


def prov_note(label: str, note: str, evidence: list | None = None) -> str:
    """The kernel-facing note: original label + explanation + citations."""
    cites = f" [docs: {', '.join(evidence)}]" if evidence else ""
    return f"[{label}] {note}{cites}"


class EvidenceRegistry:
    """The documents a compile run is allowed to treat as verification."""

    def __init__(self, docs: list | None, mode: str) -> None:
        if mode not in ("model_memory", "evidence_docs"):
            raise ValueError(f"unknown evidence mode {mode!r}")
        self.mode = mode
        self.docs = {d["id"]: d for d in (docs or [])}
        if mode == "evidence_docs" and not self.docs:
            raise ValueError("evidence_docs mode requires at least one document")

    def check_claim(self, label: str, evidence: list | None, where: str) -> list:
        """Deterministic enforcement -> list of error strings."""
        errors = []
        for ref in evidence or []:
            if ref not in self.docs:
                errors.append(f"{where}: cites unknown document {ref!r}")
        if label == "verified" and self.mode == "evidence_docs" \
                and not (evidence or []):
            errors.append(f"{where}: 'verified' requires a document citation "
                          f"in evidence_docs mode (use inferred/"
                          f"model_memory_unverified otherwise)")
        if label == "verified" and self.mode == "model_memory":
            errors.append(f"{where}: 'verified' is not available in "
                          f"model_memory mode -- label the claim "
                          f"model_memory_unverified, inferred, or "
                          f"question_given")
        return errors

    def render(self) -> str:
        """The documents block shown to description-stage calls."""
        if not self.docs:
            return ""
        parts = ["EVIDENCE DOCUMENTS (the only permissible basis for "
                 "'verified' claims):"]
        for d in self.docs.values():
            parts.append(f"--- doc {d['id']} | {d.get('title', '')} | "
                         f"{d.get('date', '')} ---")
            parts.append(str(d.get("content", "")).strip())
        return "\n".join(parts)
