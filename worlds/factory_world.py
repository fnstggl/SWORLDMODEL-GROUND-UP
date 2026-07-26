"""Hand-authored test world 3: an operational process with quantities.

    orders arrive -> production occurs -> inventory changes
    -> deliveries complete -> total accumulates

A factory line produces 40 widgets/hour while the shift runs (08:00-16:00
Chicago, a scheduled operating calendar expressed as world.ops events).  A
purchase order for 500 units arrives Monday morning; the ops manager notices
it on his order-desk attention pattern and commits to ship when stock covers
the order -- an action whose completion is a *condition* (inventory >= 500),
so the kernel projects the threshold crossing from current rates, retargets
it when the shift ends overnight, and fires it Tuesday 12:30.  Shipping hands
the stock to the carrier; delivery completes 18 labeled hours later; the
terminal answer is the customer's received quantity, mechanically read from
resource state with its full producer lineage.

The delivery confirmation is also copied to a contact at the customer who has
no attention rule: it stays delivered-but-unnoticed (unknown remains
unknown), demonstrating that the kernel never invents noticing behavior.
"""
from __future__ import annotations

from datetime import date, time as dtime, timedelta

from sworldmodel import (ActorState, AttentionRule, BusinessCalendar, Decision,
                         Intention, Mind, Terminal, World, at_local, iso, recurring)

TZ_CH = "America/Chicago"

START = at_local(2026, 4, 6, 6, 0, tz=TZ_CH)            # Monday 06:00
ORDER_AT = at_local(2026, 4, 6, 9, 30, tz=TZ_CH)        # Monday 09:30
CUTOFF = at_local(2026, 4, 9, 12, 0, tz=TZ_CH)          # Thursday noon

QUESTION = ("How many widgets has Acme received by Thursday 2026-04-09 "
            "12:00 America/Chicago?")

FULFILL_ORDER = {
    "verb": "fulfill_order",
    "description": ("Commit to fulfill an open order: stage stock and ship as "
                    "soon as inventory covers it. params: order_id, qty. "
                    "Completes when factory inventory reaches qty."),
    "conditions": [
        {"require": "role_in", "roles": ["ops manager"]},
        {"require": "fact_equals", "key": "order:{params.order_id}:status",
         "value": "received"},
    ],
    # completion effects: ship (transfer to carrier) and schedule the
    # delivery -- all universal ops, with a provenance-labeled transit delay
    "effects": [
        ["fact.set", {"key": "order:{params.order_id}:status", "value": "shipped"}],
        ["resource.transfer", {"from_holder": "factory", "to_holder": "carrier",
                               "name": "widgets", "amount": "{params.qty}"}],
        ["event.schedule_in", {
            "kind": "world.ops", "delay_hours": 18, "basis": "inferred",
            "note": "regional freight transit time, comparable lanes",
            "data": {"ops": [
                ["resource.transfer", {"from_holder": "carrier",
                                       "to_holder": "acme", "name": "widgets",
                                       "amount": "{params.qty}"}],
                ["fact.set", {"key": "order:{params.order_id}:status",
                              "value": "delivered"}],
                ["info.send_new", {"author": "carrier",
                                   "to": ["mo", "acme_contact"],
                                   "channel": "order_system",
                                   "content": "Delivery confirmation: PO "
                                              "{params.order_id} "
                                              "({params.qty} widgets) delivered.",
                                   "data": {"type": "delivery",
                                            "id": "{params.order_id}"}}]],
                "note": "carrier delivers PO {params.order_id}"}}],
        ["actor.memory", {"actor": "{actor}", "kind": "note",
                          "content": "Shipped PO {params.order_id}: {params.qty} "
                                     "widgets handed to the carrier.",
                          "source": "{action_id}"}],
    ],
}


def build():
    w = World(START)
    w.apply("channel.add",
            {"name": "order_system",
             "latency": {"seconds": 60, "basis": "verified",
                         "note": "order portal / EDI processing time"}}, None)
    w.apply("action.define", FULFILL_ORDER, None)
    w.apply("entity.add", {"id": "factory", "kind": "plant",
                           "properties": {"line": "widget line 1"}}, None)
    w.apply("entity.add", {"id": "acme", "kind": "customer",
                           "properties": {"name": "Acme Corp"}}, None)
    w.apply("resource.set", {"holder": "factory", "name": "widgets", "amount": 0}, None)
    w.apply("resource.set", {"holder": "acme", "name": "widgets", "amount": 0}, None)
    w.apply("process.add",
            {"id": "p_line1", "holder": "factory", "resource": "widgets",
             "rate_per_hour": 40.0, "active": False,
             "basis": "verified",
             "note": "rated line speed from the plant spec (scenario-given)"},
            None)

    desk_cal = BusinessCalendar(tz=TZ_CH, open_time=dtime(8, 0),
                                close_time=dtime(17, 0))
    mo = ActorState(
        id="mo", name="Mo Jackson", role="ops manager", tz=TZ_CH,
        attention={"order_system": AttentionRule(
            desk_cal, timedelta(minutes=15), "inferred",
            "order desk checks the order system frequently during shift")},
        goals=["ship every order as soon as stock allows"],
        values=["reliable", "hates late shipments"],
        plan="Run the week's production; fulfill orders as they arrive.")
    w.apply("actor.add", mo.to_dict(), None)
    # a contact at the customer with NO attention rule and no mind: the
    # kernel must leave their copy delivered-but-unnoticed
    w.apply("actor.add", ActorState(
        id="acme_contact", name="Acme receiving desk", role="customer contact",
        tz=TZ_CH).to_dict(), None)

    # operating calendar as scheduled world data: shift on/off Mon-Fri
    for day_start in recurring(TZ_CH, dtime(8, 0), date(2026, 4, 6), date(2026, 4, 10)):
        w.schedule("world.ops",
                   {"ops": [["process.active", {"id": "p_line1", "active": True}]],
                    "note": "shift start (verified: plant operating calendar)"},
                   day_start, None)
    for day_end in recurring(TZ_CH, dtime(16, 0), date(2026, 4, 6), date(2026, 4, 10)):
        w.schedule("world.ops",
                   {"ops": [["process.active", {"id": "p_line1", "active": False}]],
                    "note": "shift end (verified: plant operating calendar)"},
                   day_end, None)

    # the order arrives: scheduled external reality, pure data
    w.schedule("world.ops",
               {"ops": [
                   ["fact.set", {"key": "order:o1:status", "value": "received"}],
                   ["fact.set", {"key": "order:o1:qty", "value": 500}],
                   ["info.send_new", {"author": "acme", "to": ["mo"],
                                      "channel": "order_system",
                                      "content": "PO o1: 500 widgets, ship as "
                                                 "soon as available.",
                                      "data": {"type": "order", "id": "o1",
                                               "qty": 500}}]],
                "note": "customer purchase order arrives"},
               ORDER_AT, None)
    minds = {"mo": MoMind()}
    return w, minds, make_terminal()


def make_terminal() -> Terminal:
    def evaluate(world, final):
        if not final:
            return None  # a "how many by <deadline>" question resolves at the deadline
        total = world.resource("acme", "widgets")
        producers = []
        for r in world.records:
            if r["op"] == "resource.transfer" and r["data"].get("to_holder") == "acme":
                producers.append(f"record:{r['seq']}")
                # full lineage: transfer <- delivery event <- shipping action
                # <- threshold <- accruals; recorded for the artifact
        lineage = (world.lineage(int(producers[-1].split(":")[1]))
                   if producers else [])
        return {"answer": total,
                "detail": f"Acme's received widgets at the cutoff: {total:g}",
                "computed_from": producers or ["resource:acme:widgets"],
                "lineage": [{"seq": e["seq"], "op": e["op"]} for e in lineage]}
    return Terminal(QUESTION, CUTOFF, evaluate)


class MoMind(Mind):
    def decide(self, view):
        for iv in view.new_information:
            if iv.data.get("type") == "order":
                oid, qty = iv.data["id"], iv.data["qty"]
                return Decision(
                    updates=[("actor.commit",
                              {"actor": "mo", "id": f"c_{oid}",
                               "what": f"fulfill PO {oid} ({qty} widgets)",
                               "at": None}),
                             ("actor.memory",
                              {"actor": "mo", "kind": "note",
                               "content": f"New order {oid} for {qty} widgets; "
                                          f"will ship as soon as stock covers it.",
                               "source": iv.id})],
                    intentions=[Intention(
                        "fulfill_order", {"order_id": oid, "qty": qty},
                        completes_when={"resource_at_least":
                                        ["factory", "widgets", qty]},
                        note="stage and ship when inventory reaches the order "
                             "quantity")],
                    note=f"Order {oid} in; committing to fulfill it")
            if iv.data.get("type") == "delivery":
                oid = iv.data["id"]
                return Decision(
                    updates=[("actor.commitment_resolved",
                              {"actor": "mo", "id": f"c_{oid}"}),
                             ("actor.belief",
                              {"actor": "mo", "topic": f"order:{oid}",
                               "statement": f"PO {oid} was delivered to the "
                                            f"customer.",
                               "basis": f"carrier confirmation ({iv.id})"})],
                    note=f"Delivery of {oid} confirmed; closing it out")
        for av in view.completed:
            if av.verb == "fulfill_order":
                return Decision(
                    updates=[("actor.plan",
                              {"actor": "mo",
                               "plan": "Order shipped; watch for the delivery "
                                       "confirmation."})],
                    note="Shipment handed to the carrier")
        return Decision(note="nothing to do")


REVIEW = """# Reality-fidelity review -- factory world

## What is real-world faithful here
- **Continuous change is exact, not stepped.** Inventory is integrated from
  the labeled 40/hour rate over precisely the elapsed intervals the shift
  calendar allows: 70 units by Mo's 09:45 wake (1.75h x 40); 320 by Monday
  close; 500 exactly at Tuesday 12:30.
  The threshold event was first projected for Monday 20:30, then *cancelled*
  when the shift ended (rate fell to zero) and re-projected from Tuesday's
  restart -- the schedule follows the physics, not the other way round.
- **Nothing teleports.** Stock moves factory -> carrier -> customer; the
  18-hour transit is a labeled inference; the confirmation is a message on a
  channel with latency, noticed on the manager's desk pattern the next
  morning (delivered 06:31, noticed 08:00).
- **The answer is a measurement.** "How many widgets has Acme received" is
  read from `acme:widgets` with the full producer lineage: transfer <-
  delivery event <- shipping action <- threshold <- recorded accruals.

## Honest limitations (labeled, not hidden)
- Production has no scrap rate, no changeover downtime, no variance; the
  rated speed is taken at face value (and labeled as scenario-given).
- Shipping ignores loading time and carrier pickup windows; the 18h transit
  is a point estimate where reality is a distribution.
- The customer is passive: no chasing emails, no partial-delivery
  negotiation. Their receiving desk deliberately has no attention model, so
  its copy of the confirmation stays unnoticed rather than being invented.
"""
