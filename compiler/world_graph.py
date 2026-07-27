"""The canonical intermediate representation of a compiled world.

A WorldGraph holds every accepted capability instance under canonical
internal ids, plus the name registry that maps every declared name and alias
to its id.  It is pure data between translation and assembly: no LLM ever
touches it, and nothing here knows what any particular world is about.
"""
from __future__ import annotations

import re


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "x"


class NameRegistry:
    """Canonical names, aliases, and collision-free ids.  Reference
    resolution is exact (casefolded) against declared names/aliases;
    ambiguity is an error, never a guess."""

    def __init__(self) -> None:
        self.ids: dict[str, dict] = {}       # id -> {name, kind}
        self._by_name: dict[str, set] = {}   # casefolded name/alias -> {ids}

    def add(self, name: str, aliases: list, kind: str) -> str:
        existing = self.resolve(name)
        if existing is not None:
            return existing                   # merged by the builder
        base = slugify(name)
        nid, n = base, 2
        while nid in self.ids:
            nid, n = f"{base}_{n}", n + 1
        self.ids[nid] = {"name": name, "kind": kind}
        for label in {name, *aliases, nid}:
            self._by_name.setdefault(label.strip().casefold(), set()).add(nid)
        return nid

    def resolve(self, name) -> str | None:
        if not isinstance(name, str):
            return None
        hits = self._by_name.get(name.strip().casefold(), set())
        return next(iter(hits)) if len(hits) == 1 else None

    def resolve_or_error(self, name, expect_kinds, errors, where) -> str | None:
        hits = self._by_name.get(str(name).strip().casefold(), set()) \
            if isinstance(name, str) else set()
        if len(hits) > 1:
            errors.append(f"{where}: name {name!r} is ambiguous between "
                          f"{sorted(hits)}")
            return None
        if not hits:
            errors.append(f"{where}: unknown name {name!r} -- every reference "
                          f"must be a declared name (declared: "
                          f"{sorted(i for i in self.ids)})")
            return None
        nid = next(iter(hits))
        kind = self.ids[nid]["kind"]
        if expect_kinds and kind not in expect_kinds:
            errors.append(f"{where}: {name!r} is a {kind}, expected one of "
                          f"{sorted(expect_kinds)}")
            return None
        return nid

    def kind_of(self, nid: str) -> str:
        return self.ids[nid]["kind"]


class WorldGraph:
    """Everything the compiled world is made of, keyed by internal ids."""

    def __init__(self) -> None:
        self.registry = NameRegistry()
        self.participants: dict[str, dict] = {}
        self.aggregates: dict[str, dict] = {}
        self.channels: dict[str, dict] = {}
        self.routes: list[dict] = []          # {sender, recipient, channel, ...}
        self.attention: list[dict] = []
        self.facts: list[dict] = []
        self.resources: list[dict] = []
        self.processes: dict[str, dict] = {}
        self.windows: list[dict] = []
        self.watches: list[dict] = []
        self.relationships: list[dict] = []
        self.beliefs: list[dict] = []
        self.commitments: list[dict] = []
        self.actions: dict[str, dict] = {}    # verb -> lowered-ready fields
        self.external_events: list[dict] = []
        self.wakes: list[dict] = []
        self.uncertainties: list[dict] = []
        self.exclusions: list[dict] = []
        self.terminal: dict | None = None
        self.notes: list[str] = []            # builder decisions worth surfacing

    # -- queries used by validation/round-trip ---------------------------
    def roles(self) -> dict:
        return {pid: p["role"] for pid, p in self.participants.items()}

    def holders(self) -> set:
        return set(self.participants) | set(self.aggregates)

    def describe_registry(self) -> str:
        """Compact context block for translation calls: what already exists
        and may be referenced by name."""
        lines = []
        if self.participants:
            lines.append("Participants (name -- role -- tz):")
            for pid, p in self.participants.items():
                lines.append(f"  {p['name']} -- {p['role']} -- {p.get('tz', 'UTC')}")
        if self.aggregates:
            lines.append("Aggregates (name -- kind):")
            for aid, a in self.aggregates.items():
                lines.append(f"  {a['name']} -- {a['kind']}")
        if self.channels:
            lines.append("Channels: " + ", ".join(
                c["name"] for c in self.channels.values()))
        if self.processes:
            lines.append("Processes: " + ", ".join(
                f"{p['name']} ({self.ids_name(p['owner'])}:{p['resource']})"
                for p in self.processes.values()))
        held = sorted({f"{self.ids_name(r['holder'])}:{r['resource']}"
                       for r in self.resources})
        if held:
            lines.append("Quantities: " + ", ".join(held))
        if self.facts:
            lines.append("Facts: " + ", ".join(f["key"] for f in self.facts))
        if self.actions:
            lines.append("Defined actions: " + ", ".join(sorted(self.actions)))
        rts = sorted({f"{e['record_type']}:{e['subject']}"
                      for a in self.actions.values()
                      for e in a["fields"].get("effects", [])
                      if e.get("do") == "create_record"})
        if rts:
            lines.append("Record types in use (record_type:subject): "
                         + ", ".join(rts))
        return "\n".join(lines) or "(nothing declared yet)"

    def ids_name(self, nid: str) -> str:
        info = self.registry.ids.get(nid)
        return info["name"] if info else nid
