"""Identifiers and reference resolution.

The model writes names ("Bob", "company email", "widget production"). This
module turns them into stable internal identifiers and resolves every
reference, refusing ambiguity instead of guessing. It makes no model calls
and invents no meaning.
"""
from __future__ import annotations

import re
import unicodedata

from .errors import InvalidReference, SemanticAmbiguity


def slug(text: str, fallback: str = "x") -> str:
    """Deterministic identifier from free text."""
    if text is None:
        return fallback
    s = unicodedata.normalize("NFKD", str(text))
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    s = re.sub(r"_+", "_", s)
    return s[:60] or fallback


class SymbolTable:
    """Name -> id, one namespace per kind, with ambiguity detection."""

    KINDS = ("participant", "route", "quantity", "process", "affordance",
             "fact", "tag")

    def __init__(self) -> None:
        self._by_kind: dict = {k: {} for k in self.KINDS}   # lookup key -> id
        self._display: dict = {}                            # id -> original name
        self._used_ids: dict = {k: set() for k in self.KINDS}

    # -- registration ---------------------------------------------------
    def register(self, kind: str, name: str, prefix: str = "") -> str:
        if kind not in self.KINDS:
            raise ValueError(f"unknown symbol kind {kind!r}")
        key = self._key(name)
        if not key:
            raise SemanticAmbiguity(f"{kind} has an empty name")
        if key in self._by_kind[kind]:
            raise SemanticAmbiguity(
                f"two {kind}s share the name {name!r}; every reference to it "
                f"would be ambiguous")
        base = (prefix + slug(name)) or kind
        ident = base
        n = 2
        while ident in self._used_ids[kind]:
            ident = f"{base}_{n}"
            n += 1
        self._used_ids[kind].add(ident)
        self._by_kind[kind][key] = ident
        self._display[f"{kind}:{ident}"] = str(name)
        return ident

    # -- resolution -----------------------------------------------------
    def resolve(self, kind: str, name: str, where: str) -> str:
        key = self._key(name)
        table = self._by_kind[kind]
        if key in table:
            return table[key]
        # a near-miss is still a refusal, but say what was meant
        candidates = [self._display[f"{kind}:{v}"] for k, v in table.items()
                      if key and (key in k or k in key)]
        if len(candidates) == 1:
            raise InvalidReference(
                f"{where}: no {kind} named {name!r}; did you mean "
                f"{candidates[0]!r}? References must match exactly.",
                {"kind": kind, "name": name, "known": self.names(kind)})
        raise InvalidReference(
            f"{where}: no {kind} named {name!r}",
            {"kind": kind, "name": name, "known": self.names(kind)})

    def maybe(self, kind: str, name: str) -> str | None:
        return self._by_kind[kind].get(self._key(name))

    def has(self, kind: str, name: str) -> bool:
        return self._key(name) in self._by_kind[kind]

    def names(self, kind: str) -> list:
        return sorted(self._display[f"{kind}:{v}"]
                      for v in self._by_kind[kind].values())

    def ids(self, kind: str) -> list:
        return sorted(self._by_kind[kind].values())

    def display(self, kind: str, ident: str) -> str:
        return self._display.get(f"{kind}:{ident}", ident)

    @staticmethod
    def _key(name: str) -> str:
        return slug(name)

    def to_dict(self) -> dict:
        return {
            "namespaces": {
                kind: {self._display[f"{kind}:{ident}"]: ident
                       for ident in sorted(table.values())}
                for kind, table in self._by_kind.items() if table
            }
        }


def fact_key(table: SymbolTable, about: str, scope: str = "global",
             actor_template: str = "{actor}") -> str:
    """Fact keys are derived from what the fact is ABOUT, so an effect that
    writes one and a terminal that reads one agree without either naming an
    identifier."""
    base = slug(about, "fact")
    if scope == "per_actor":
        return f"{base}:{actor_template}"
    return base


def fact_prefix(about: str) -> str:
    return slug(about, "fact") + ":"
