"""The code-owned canonical world graph.

This is the single representation between semantic discovery and
deterministic lowering. The model never sees or writes it: discovery calls
return small natural-language documents, the assembler turns them into
nodes and edges here, and everything downstream (review, proofs, lowering,
round-trip) reads this graph. Code owns every ID, every reference and every
lifecycle connection.

The vocabularies are closed and universal -- representation primitives, not
scenario engines. There is no committee node, no email node, no factory
node; there are participants, processes, information and the relationships
between them.

Two rules from the Phase 0 audit are made structural here rather than
textual:

* An actor decision is an ``action`` node reachable only through
  ``can_perform``. Nothing in this graph can schedule an action: what an
  actor WILL do is not representable, only what they CAN do.
* Meaning that used to live in prose next to contradicting structure
  (attention windows, transit delays, access denials) has explicit fields,
  so the reviewer, the proofs and the lowerer all read the same thing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .errors import InvalidReference, SemanticAmbiguity
from .symbols import SymbolTable, slug

# -- closed vocabularies ----------------------------------------------------

NODE_CATEGORIES = (
    "participant", "organization", "population", "process", "state",
    "information", "event", "action", "record", "resource", "terminal",
)

RELATIONSHIPS = (
    "knows", "has_state", "has_authority", "can_perform", "requires",
    "produces", "changes", "sends_to", "receives_from", "observes",
    "scheduled_at", "constrains", "measured_by_terminal",
)

#: The graph's epistemic bases. ``question_given`` is what the question
#: itself asserts; ``model_memory_unverified`` marks Mode B claims drafted
#: from model memory and must survive into every artifact untouched.
GRAPH_BASES = ("verified", "inferred", "question_given",
               "model_memory_unverified", "uncertain")

#: Bases that must cite evidence ids.
CITED_BASES = ("verified", "inferred")

#: Which (source category -> target category) pairs each relationship may
#: connect. This is the structural half of "code assembles": a vote, a
#: shipment and an email reply must all be expressible with exactly these.
ACTORS = ("participant", "organization", "population")
HAPPENINGS = ("action", "event", "process")
PRODUCIBLE = ("state", "record", "information", "resource", "event")

RELATION_DOMAINS = {
    "knows":                (ACTORS, ("information", "state")),
    "has_state":            (ACTORS + ("process", "resource"), ("state",)),
    "has_authority":        (ACTORS, ("action", "record", "process")),
    "can_perform":          (ACTORS, ("action",)),
    "requires":             (HAPPENINGS + ("state",),
                             ("state", "information", "record", "resource",
                              "event", "action", "process")),
    "produces":             (HAPPENINGS, PRODUCIBLE),
    "changes":              (HAPPENINGS, ("state", "resource")),
    "sends_to":             (ACTORS, ("process",)),
    "receives_from":        (ACTORS, ("process",)),
    "observes":             (ACTORS, ("state", "record", "process",
                                      "resource", "event")),
    "scheduled_at":         (("event",), ("event",)),
    "constrains":           (("state", "process", "organization"),
                             ("action", "process", "event")),
    "measured_by_terminal": (("state", "record", "resource"), ("terminal",)),
}

#: requires-edge necessity values. ``alternative`` edges belong to an
#: ``alt_group``; at least one member of each group must hold.
NECESSITY = ("necessary", "alternative", "optional")

#: For merging repeated mentions of one entity: existence is as well
#: evidenced as its best-supported mention.
BASIS_RANK = {"verified": 4, "inferred": 3, "question_given": 2,
              "model_memory_unverified": 1, "uncertain": 0}


class GraphSymbols(SymbolTable):
    """The same exact-match, refuse-ambiguity resolution the audit found
    worth preserving, over the graph's node categories."""
    KINDS = NODE_CATEGORIES


@dataclass
class Node:
    id: str
    category: str
    name: str
    meaning: str
    basis: str
    evidence_ids: tuple = ()
    attrs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "category": self.category, "name": self.name,
                "meaning": self.meaning,
                "provenance": {"basis": self.basis,
                               "evidence_ids": list(self.evidence_ids)},
                "attrs": self.attrs}


@dataclass
class Edge:
    src: str
    rel: str
    dst: str
    attrs: dict = field(default_factory=dict)

    def key(self) -> tuple:
        return (self.src, self.rel, self.dst,
                json.dumps(self.attrs, sort_keys=True))

    def to_dict(self) -> dict:
        return {"src": self.src, "rel": self.rel, "dst": self.dst,
                "attrs": self.attrs}


class WorldGraph:
    """Canonical nodes + edges with closed vocabularies and code-owned IDs.

    Every mutation validates: unknown categories, unknown relationships,
    domain violations, duplicate names, dangling references and unlabelled
    or miscited provenance are refused at the point of entry, naming the
    defect. Nothing is repaired and nothing is guessed.
    """

    def __init__(self, valid_evidence_ids=None) -> None:
        self.symbols = GraphSymbols()
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._edge_keys: set = set()
        self.uncertainties: list[dict] = []
        self.exclusions: list[dict] = []
        self.valid_evidence_ids = (None if valid_evidence_ids is None
                                   else set(valid_evidence_ids))

    # -- nodes ----------------------------------------------------------
    def add_node(self, category: str, name: str, meaning: str,
                 basis: str, evidence_ids=(), attrs: dict | None = None,
                 where: str = "graph") -> str:
        if category not in NODE_CATEGORIES:
            raise ValueError(f"{where}: unknown node category {category!r}")
        self._check_provenance(basis, evidence_ids, f"{where}: {name!r}")
        if category in ACTORS:
            for other in ACTORS:
                if other != category and self.maybe(other, name):
                    raise SemanticAmbiguity(
                        f"{where}: {name!r} already exists as a "
                        f"{other}; one entity cannot be both a {other} "
                        f"and a {category}")
        ident = self.symbols.register(category, name)
        node_id = f"{category}:{ident}"
        self.nodes[node_id] = Node(node_id, category, str(name),
                                   str(meaning or ""), basis,
                                   tuple(evidence_ids), dict(attrs or {}))
        return node_id

    def absorb(self, node_id: str, meaning: str, basis: str,
               evidence_ids=(), where: str = "graph") -> str:
        """A later discovery mentions an existing node: merge, order-free.
        Meanings accumulate (sorted, deduplicated); evidence is unioned;
        the basis becomes the strongest any mention earned. Nothing is
        overwritten and nothing depends on which mention came first."""
        n = self.node(node_id)
        self._check_provenance(basis, evidence_ids, f"{where}: {n.name!r}")
        parts = {p for p in n.meaning.split("\n") if p}
        if meaning:
            parts.add(str(meaning))
        n.meaning = "\n".join(sorted(parts))
        n.evidence_ids = tuple(sorted(set(n.evidence_ids)
                                      | set(evidence_ids)))
        if BASIS_RANK[basis] > BASIS_RANK[n.basis]:
            n.basis = basis
        return node_id

    def resolve(self, category: str, name: str, where: str) -> str:
        """Name -> node id, refusing near-misses with a did-you-mean."""
        return f"{category}:{self.symbols.resolve(category, name, where)}"

    def maybe(self, category: str, name: str) -> str | None:
        ident = self.symbols.maybe(category, name)
        return f"{category}:{ident}" if ident else None

    def resolve_any(self, categories, name: str, where: str) -> str:
        """Resolve a name across several categories; exactly one must match."""
        hits = [nid for c in categories if (nid := self.maybe(c, name))]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise SemanticAmbiguity(
                f"{where}: {name!r} matches more than one thing "
                f"({', '.join(sorted(hits))}); references must be unique",
                {"name": name, "matches": sorted(hits)})
        known = sorted(n for c in categories for n in self.symbols.names(c))
        raise InvalidReference(
            f"{where}: nothing named {name!r} exists "
            f"in {'/'.join(categories)}",
            {"name": name, "known": known})

    def node(self, node_id: str) -> Node:
        if node_id not in self.nodes:
            raise InvalidReference(f"no node {node_id!r} in the graph")
        return self.nodes[node_id]

    def by_category(self, category: str) -> list:
        return sorted((n for n in self.nodes.values()
                       if n.category == category), key=lambda n: n.id)

    # -- edges ----------------------------------------------------------
    def add_edge(self, src: str, rel: str, dst: str,
                 attrs: dict | None = None, where: str = "graph") -> Edge:
        if rel not in RELATIONSHIPS:
            raise ValueError(f"{where}: unknown relationship {rel!r}")
        s, d = self.node(src), self.node(dst)
        src_ok, dst_ok = RELATION_DOMAINS[rel]
        if s.category not in src_ok or d.category not in dst_ok:
            raise SemanticAmbiguity(
                f"{where}: {rel} cannot connect {s.category} -> {d.category} "
                f"(allowed: {'/'.join(src_ok)} -> {'/'.join(dst_ok)})",
                {"src": src, "rel": rel, "dst": dst})
        attrs = dict(attrs or {})
        if rel == "requires":
            nec = attrs.setdefault("necessity", "necessary")
            if nec not in NECESSITY:
                raise ValueError(f"{where}: necessity must be one of "
                                 f"{NECESSITY}, got {nec!r}")
            if nec == "alternative" and not attrs.get("alt_group"):
                raise ValueError(f"{where}: an alternative prerequisite "
                                 f"needs an alt_group")
        edge = Edge(src, rel, dst, attrs)
        if edge.key() in self._edge_keys:
            return edge                        # idempotent: stated twice is once
        self._edge_keys.add(edge.key())
        self.edges.append(edge)
        return edge

    def edges_from(self, src: str, rel: str | None = None) -> list:
        return sorted((e for e in self.edges if e.src == src
                       and (rel is None or e.rel == rel)),
                      key=lambda e: e.key())

    def edges_to(self, dst: str, rel: str | None = None) -> list:
        return sorted((e for e in self.edges if e.dst == dst
                       and (rel is None or e.rel == rel)),
                      key=lambda e: e.key())

    # -- derived views used by proofs and review ------------------------
    def producers_of(self, node_id: str) -> list:
        """Happenings with a produces/changes edge into this node."""
        return sorted({e.src for e in self.edges
                       if e.dst == node_id and e.rel in ("produces", "changes")})

    def prerequisites_of(self, node_id: str) -> list:
        return self.edges_from(node_id, "requires")

    def performers_of(self, action_id: str) -> list:
        return sorted({e.src for e in self.edges_to(action_id, "can_perform")})

    def terminal(self) -> Node:
        terms = self.by_category("terminal")
        if len(terms) != 1:
            raise SemanticAmbiguity(
                f"the graph must contain exactly one terminal, found "
                f"{len(terms)}")
        return terms[0]

    def measured_components(self) -> list:
        return sorted({e.src for e in self.edges
                       if e.rel == "measured_by_terminal"})

    # -- uncertainty and exclusions -------------------------------------
    def add_uncertainty(self, about_id: str, meaning: str,
                        where: str = "uncertainty") -> None:
        self.node(about_id)                     # must exist
        self.uncertainties.append({"about": about_id, "meaning": str(meaning)})

    def add_exclusion(self, name: str, why_safe: str, basis: str,
                      evidence_ids=(), where: str = "exclusion") -> None:
        self._check_provenance(basis, evidence_ids, f"{where}: {name!r}")
        hits = [nid for c in NODE_CATEGORIES if (nid := self.maybe(c, name))]
        if hits:
            raise SemanticAmbiguity(
                f"{where}: {name!r} is both in the world ({hits[0]}) and "
                f"excluded from it; it must be one or the other")
        self.exclusions.append({"name": str(name), "why_safe": str(why_safe),
                                "basis": basis,
                                "evidence_ids": list(evidence_ids)})

    # -- provenance ------------------------------------------------------
    def _check_provenance(self, basis: str, evidence_ids, where: str) -> None:
        if basis not in GRAPH_BASES:
            raise SemanticAmbiguity(
                f"{where}: basis must be one of {GRAPH_BASES}, got {basis!r}")
        if basis in CITED_BASES and not evidence_ids:
            raise SemanticAmbiguity(
                f"{where}: a claim marked {basis!r} cites no evidence_ids")
        if self.valid_evidence_ids is not None:
            missing = [i for i in evidence_ids
                       if i not in self.valid_evidence_ids]
            if missing:
                raise SemanticAmbiguity(
                    f"{where}: cited evidence ids do not exist: {missing}")

    # -- serialization ---------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in
                      sorted(self.nodes.values(), key=lambda n: n.id)],
            "edges": [e.to_dict() for e in
                      sorted(self.edges, key=lambda e: e.key())],
            "uncertainties": sorted(self.uncertainties,
                                    key=lambda u: (u["about"], u["meaning"])),
            "exclusions": sorted(self.exclusions, key=lambda x: x["name"]),
            "symbol_table": self.symbols.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict,
                  valid_evidence_ids=None) -> "WorldGraph":
        """Rebuild through the same validating funnel, so a hand-edited
        artifact cannot smuggle in structure the graph would refuse."""
        g = cls(valid_evidence_ids)
        for n in data.get("nodes", ()):
            prov = n.get("provenance") or {}
            g.add_node(n["category"], n["name"], n.get("meaning", ""),
                       prov.get("basis"), prov.get("evidence_ids", ()),
                       n.get("attrs"), where="from_dict")
        ids = {n["id"] for n in data.get("nodes", ())}
        rebuilt = set(g.nodes)
        if ids != rebuilt:
            raise SemanticAmbiguity(
                f"from_dict: node ids changed on rebuild "
                f"(missing={sorted(ids - rebuilt)}, "
                f"extra={sorted(rebuilt - ids)}); ids are code-owned and "
                f"must be reproducible")
        for e in data.get("edges", ()):
            g.add_edge(e["src"], e["rel"], e["dst"], e.get("attrs"),
                       where="from_dict")
        for u in data.get("uncertainties", ()):
            g.add_uncertainty(u["about"], u["meaning"])
        for x in data.get("exclusions", ()):
            g.add_exclusion(x["name"], x["why_safe"], x["basis"],
                            x.get("evidence_ids", ()))
        return g
