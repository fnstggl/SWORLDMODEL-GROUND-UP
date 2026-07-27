"""Deterministic transfer feasibility. Zero model calls.

The runtime schedules committed transfers unconditionally: the kernel
does not clamp an overdraw and nothing may quietly convert a shortfall
into a smaller shipment. So the world's own numbers must cover its
commitments BEFORE any reviewer sees it: for every scheduled transfer,
the source's computable balance at that moment -- opening stock, plus
what its bound processes accrue by then, plus earlier arrivals, minus
earlier outflows -- must cover the amount. A shortfall is a document
defect with the usual one targeted repair: the spine omits a producing
mechanism, the opening stock is understated, or the commitment is
genuinely conditional -- and a genuinely conditional commitment cannot
be scheduled as certain, so if the repair confirms the shortfall the
compilation refuses honestly.

Anything the walk cannot place or price (an event without a concrete
instant, a process without a computable window) suppresses the verdict
for every stock it touches instead of guessing: refusal to compute is
never an accusation.
"""
from __future__ import annotations

from datetime import datetime, time as clock_time
from zoneinfo import ZoneInfo

from sworldmodel.simclock import recurring

from .emit import substance_classes
from .errors import SemanticAmbiguity
from .graph import ACTORS, WorldGraph


def _actor_id(graph: WorldGraph, name):
    if not name:
        return None
    for c in ACTORS:
        nid = graph.maybe(c, name)
        if nid:
            return nid
    return None


def _parse_when(value):
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo is not None else None


def _clock(value):
    try:
        h, m = str(value).split(":", 1)
        return clock_time(int(h), int(m))
    except (TypeError, ValueError):
        return None


def _accrued(op: dict, rate: float, start: datetime, until: datetime):
    """Units a process contributes between start and until, or None when
    its window cannot be computed. No operating dict = runs continuously."""
    if until <= start:
        return 0.0
    if not op:
        return rate * (until - start).total_seconds() / 3600.0
    tz = op.get("timezone")
    begin, end = _clock(op.get("start")), _clock(op.get("end"))
    if not tz or begin is None or end is None or end <= begin:
        return None
    try:
        zone = ZoneInfo(tz)
        d0 = start.astimezone(zone).date()
        d1 = until.astimezone(zone).date()
        for key in ("from_date", "until_date"):
            if op.get(key):
                bound = datetime.fromisoformat(f"{op[key]}T00:00:00").date()
                if key == "from_date" and bound > d0:
                    d0 = bound
                if key == "until_date" and bound < d1:
                    d1 = bound
        workdays = frozenset(op.get("workdays") or (0, 1, 2, 3, 4, 5, 6))
        total = 0.0
        # recurring yields UTC instants; pair each day's begin with its
        # end exactly the way the lowering schedules them
        begins = recurring(tz, begin, d0, d1, workdays, frozenset())
        ends = recurring(tz, end, d0, d1, workdays, frozenset())
        for t0, t1 in zip(begins, ends):
            lo, hi = max(t0, start), min(t1, until)
            if hi > lo:
                total += (hi - lo).total_seconds() / 3600.0
        return rate * total
    except Exception:
        return None


def check_transfer_feasibility(graph: WorldGraph, bindings) -> None:
    """Raises SemanticAmbiguity (document: causal_spine) when a scheduled
    transfer overdraws its source under the world's own bound numbers."""
    classes = substance_classes(graph, bindings)

    def class_of(rid):
        return classes.get(rid, graph.node(rid).name)

    # scheduled movements: (when, event, resource class, spec)
    moves, unverifiable = [], set()
    for eid in sorted(bindings.events):
        try:
            node = graph.node(eid)
        except Exception:
            continue
        bound = bindings.events[eid] or {}
        for rname, spec in sorted((bound.get("amounts") or {}).items()):
            rid = graph.maybe("resource", rname)
            if rid is None or not isinstance(spec, dict):
                continue
            amount = spec.get("amount")
            if not isinstance(amount, (int, float)):
                continue
            when = _parse_when(node.attrs.get("when"))
            if when is None:
                unverifiable.add(class_of(rid))
                continue
            moves.append((when, node, rid, spec))
    if not moves:
        return

    start = min(w for w, *_ in moves)
    # information already in flight can start the world earlier, giving
    # processes more accrual time than the movements alone suggest
    for inf in graph.by_category("information"):
        sent = _parse_when((inf.attrs.get("sent") or {}).get("sent_time"))
        if sent is not None and sent < start:
            start = sent

    # continuous inflows: (holder id, class, rate, operating)
    accruals = []
    for pid in sorted(bindings.processes):
        bound = bindings.processes[pid] or {}
        if bound.get("decorative"):
            continue
        rate = bound.get("amount_per_hour")
        if not isinstance(rate, (int, float)) or rate <= 0:
            continue
        try:
            edges = (graph.edges_from(pid, "changes")
                     + graph.edges_from(pid, "produces"))
        except Exception:
            continue
        for e in edges:
            target = graph.node(e.dst)
            if target.category != "resource":
                continue
            holder = target.attrs.get("holder")
            if not holder:
                continue
            op = bound.get("operating")
            if op is not None and not isinstance(op, dict):
                unverifiable.add(class_of(target.id))
                continue
            accruals.append((holder, class_of(target.id), float(rate), op))
            # a dated process may begin before every scheduled movement
            if op and op.get("from_date"):
                try:
                    zone = ZoneInfo(op.get("timezone") or "UTC")
                    day0 = datetime.fromisoformat(
                        f"{op['from_date']}T00:00:00").replace(tzinfo=zone)
                    if day0 < start:
                        start = day0
                except Exception:
                    unverifiable.add(class_of(target.id))

    def inflow(holder, cname, until):
        total = 0.0
        for h, c, rate, op in accruals:
            if h != holder or c != cname:
                continue
            got = _accrued(op, rate, start, until)
            if got is None:
                unverifiable.add(cname)
                return None
            total += got
        return total

    # opening stocks per (holder, class)
    opening: dict = {}
    for rs in graph.by_category("resource"):
        amt = rs.attrs.get("amount")
        holder = rs.attrs.get("holder")
        if holder and isinstance(amt, (int, float)):
            key = (holder, class_of(rs.id))
            opening[key] = opening.get(key, 0.0) + float(amt)

    # every movement leg, chronological; at one instant credits land
    # before debits (a kernel transfer is atomic on both sides)
    legs = []
    for when, node, rid, spec in moves:
        cname = class_of(rid)
        kind = spec.get("kind")
        if kind == "transfer":
            legs.append((when, node, cname, spec.get("from"),
                         -float(spec["amount"])))
            legs.append((when, node, cname, spec.get("to"),
                         +float(spec["amount"])))
        elif kind == "adjust":
            holder_attr = graph.node(rid).attrs.get("holder")
            holder_name = (graph.node(holder_attr).name if holder_attr
                           else spec.get("to") or spec.get("from"))
            legs.append((when, node, cname, holder_name,
                         float(spec["amount"])))

    flows: dict = {}
    shortfalls = []
    for when, node, cname, holder_name, delta in sorted(
            legs, key=lambda l: (l[0], l[4] < 0, l[1].id, l[2])):
        hid = _actor_id(graph, holder_name)
        if hid is None:
            if holder_name:
                unverifiable.add(cname)
            continue
        key = (hid, cname)
        produced = inflow(hid, cname, when)
        if produced is None:
            continue
        balance = opening.get(key, 0.0) + produced + flows.get(key, 0.0)
        if delta < 0 and balance + delta < -1e-9:
            shortfalls.append((cname, (
                f"scheduled event {node.name!r} moves {-delta:g} "
                f"{cname} out of {graph.node(hid).name!r} at "
                f"{when.isoformat()}, but their computable stock then "
                f"is only {balance:g} (opening "
                f"{opening.get(key, 0.0):g} + produced {produced:g} + "
                f"net earlier movements {flows.get(key, 0.0):g}). "
                f"Either the causal spine omits a mechanism that "
                f"produces {cname} for them before that moment, the "
                f"starting stock is understated, or the commitment is "
                f"genuinely conditional -- and a conditional commitment "
                f"cannot be scheduled as certain. If the world truly "
                f"cannot cover it, say so plainly.")))
        flows[key] = flows.get(key, 0.0) + delta

    defects = [text for cname, text in shortfalls
               if cname not in unverifiable]
    if defects:
        raise SemanticAmbiguity(
            "the world's own numbers cannot cover its scheduled "
            "commitments", {"defects": defects, "repairable": True,
                            "document": "causal_spine"})
