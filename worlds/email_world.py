"""Hand-authored test world 1: a two-person message interaction.

Alice (New York) emails Bob (Los Angeles) late on Friday evening asking him
to confirm the final Q2 numbers.  Bob is off for the weekend; he notices the
email when he next attends his inbox -- Monday 09:00 Pacific, which crosses
the 2026-03-08 US spring-forward transition.  He reads it (that takes time),
interprets it into a belief, composes a reply (that takes time), and Alice
notices the reply on her own checking cadence.

    email arrives -> recipient notices it -> recipient interprets it
                  -> recipient chooses whether to reply

Everything here is scenario data and adapters; the runtime is the generic
kernel shared by all worlds.
"""
from __future__ import annotations

from datetime import timedelta

from sworldmodel import (ActorState, AttentionRule, BusinessCalendar, Decision,
                         Duration, Intention, Mind, Terminal, World, at_local, iso)
from .adapters import READ_MESSAGE, SEND_MESSAGE

TZ_NY = "America/New_York"
TZ_LA = "America/Los_Angeles"

START = at_local(2026, 3, 6, 8, 0, tz=TZ_NY)          # Friday morning
SEND_COMMIT_AT = at_local(2026, 3, 6, 21, 10, tz=TZ_NY)  # Friday 21:10 ET
CUTOFF = at_local(2026, 3, 10, 12, 0, tz=TZ_NY)       # Tuesday noon ET

QUESTION = ("Does Alice have Bob's confirmation of the final Q2 numbers "
            "before Tuesday 2026-03-10 12:00 America/New_York?")


def build(reply: bool = True):
    w = World(START)
    w.apply("channel.add",
            {"name": "email",
             "latency": {"seconds": 30, "basis": "verified",
                         "note": "typical SMTP relay delivery time"}}, None)
    # scenario actions are data in the ledger, not code
    w.apply("action.define", SEND_MESSAGE, None)
    w.apply("action.define", READ_MESSAGE, None)
    ny_cal = BusinessCalendar(tz=TZ_NY)
    la_cal = BusinessCalendar(tz=TZ_LA)
    email_checking = "checks email roughly every half hour during work hours"
    alice = ActorState(
        id="alice", name="Alice Ramos", role="program manager, East Coast office",
        tz=TZ_NY,
        attention={"email": AttentionRule(ny_cal, timedelta(minutes=30), "inferred",
                                          f"office worker; {email_checking}")},
        goals=["finalize the Monday Q2 summary with confirmed numbers"],
        values=["thorough", "dislikes sending unverified figures"],
        emotional_state="mildly pressed by the Monday deadline",
        physical_state="working a long Friday",
        relationships={"bob": "trusted colleague; owns the Q2 pipeline numbers"},
        plan="Finish the weekly review tonight, then get Bob's confirmation "
             "before the Monday summary.")
    w.apply("actor.add", alice.to_dict(), None)
    bob = ActorState(
        id="bob", name="Bob Okafor", role="finance lead, West Coast office",
        tz=TZ_LA,
        attention={"email": AttentionRule(la_cal, timedelta(minutes=30), "inferred",
                                          f"office worker; {email_checking}")},
        goals=["keep the quarter-close numbers accurate"],
        values=["precise", "answers colleagues promptly once he sees a request"],
        emotional_state="unwinding into the weekend",
        physical_state="rested",
        relationships={"alice": "trusted colleague preparing the Q2 summary"},
        plan="Off for the weekend; back Monday morning.")
    w.apply("actor.add", bob.to_dict(), None)
    w.apply("actor.belief",
            {"actor": "bob", "topic": "q2_numbers",
             "statement": "The final Q2 pipeline total is $4.2M, locked on March 3.",
             "basis": "verified: he closed the books himself on March 3"}, None)
    w.apply("actor.commit",
            {"actor": "alice", "id": "c1",
             "what": "email Bob about the Q2 numbers before the weekend",
             "at": iso(SEND_COMMIT_AT)}, None)
    w.schedule("wake.actor",
               {"actor": "alice", "reason": "scheduled_commitment",
                "detail": "c1: email Bob about the Q2 numbers before the weekend"},
               SEND_COMMIT_AT, None)
    minds = {"alice": AliceMind(), "bob": BobMind(reply=reply)}
    return w, minds, make_terminal()


def make_terminal() -> Terminal:
    def evaluate(world, final):
        alice = world.actors.get("alice")
        belief = alice.beliefs.get("q2_confirmed") if alice else None
        if belief is not None:
            producers = [f"record:{r['seq']}" for r in world.records
                         if r["op"] == "actor.belief"
                         and r["data"].get("topic") == "q2_confirmed"]
            return {"answer": "yes",
                    "detail": f"Alice held Bob's confirmation by "
                              f"{iso(belief.updated_at)}: {belief.statement}",
                    "computed_from": producers or ["actor:alice.beliefs.q2_confirmed"]}
        if final:
            return {"answer": "no",
                    "detail": "no confirmation reached Alice before the cutoff",
                    "computed_from": ["terminal.cutoff", "actor:alice.beliefs"]}
        return None
    return Terminal(QUESTION, CUTOFF, evaluate)


class AliceMind(Mind):
    def decide(self, view):
        kinds = {r["kind"] for r in view.reasons}
        if "scheduled_commitment" in kinds:
            content = ("Hi Bob -- could you confirm the final Q2 pipeline "
                       "numbers when you get a chance? I need them for "
                       "Monday's summary.")
            return Decision(
                intentions=[Intention(
                    "send_message",
                    {"to": "bob", "channel": "email", "content": content,
                     "data": {"type": "question", "thread": "q2"}},
                    duration=Duration(timedelta(minutes=8), "actor_chosen",
                                      "time she takes to compose a short email"),
                    note="fulfilling her Friday commitment")],
                updates=[("actor.commitment_resolved", {"actor": "alice", "id": "c1"}),
                         ("actor.memory", {"actor": "alice", "kind": "note",
                                           "content": "Decided to email Bob about "
                                                      "the Q2 numbers tonight.",
                                           "source": "decision"})],
                note="Friday evening: sending Bob the Q2 question before logging off")
        if "info_noticed" in kinds and view.new_information:
            iv = view.new_information[0]
            return Decision(
                intentions=[Intention(
                    "read_message", {"info": iv.id, "content": iv.content},
                    duration=Duration(timedelta(minutes=4), "inferred",
                                      "short reply, quick read"),
                    note="Bob replied; reading it")],
                note="Bob's reply arrived; reading it now")
        for av in view.completed:
            content = av.params.get("content", "")
            if av.verb == "read_message" and any(
                    k in content.lower() for k in ("confirm", "4.2", "q2")):
                return Decision(
                    updates=[("actor.belief",
                              {"actor": "alice", "topic": "q2_confirmed",
                               "statement": f"Bob confirmed the Q2 numbers: {content}",
                               "basis": f"his email ({av.params.get('info')}), "
                                        f"read in full"}),
                             ("actor.plan", {"actor": "alice",
                                             "plan": "Fold the confirmed numbers "
                                                     "into the Monday summary."})],
                    note="Interpreting Bob's reply: the numbers are confirmed")
            if av.verb == "send_message":
                return Decision(
                    updates=[("actor.plan", {"actor": "alice",
                                             "plan": "Wait for Bob's reply before "
                                                     "finalizing the summary."})],
                    note="Email sent; waiting on Bob")
        return Decision(note="nothing further to do right now")


class BobMind(Mind):
    def __init__(self, reply: bool = True) -> None:
        self.reply = reply

    def decide(self, view):
        kinds = {r["kind"] for r in view.reasons}
        if "info_noticed" in kinds and view.new_information:
            iv = view.new_information[0]
            return Decision(
                intentions=[Intention(
                    "read_message", {"info": iv.id, "content": iv.content},
                    duration=Duration(timedelta(minutes=6), "inferred",
                                      "reading and re-checking the request"),
                    note="new email from Alice; reading it")],
                updates=[("actor.emotion", {"actor": "bob",
                                            "statement": "Monday-morning inbox "
                                                         "triage; slightly rushed"})],
                note="Back at his desk Monday; Alice's email is at the top")
        for av in view.completed:
            if av.verb == "read_message":
                req_id = av.params.get("info")
                updates = [("actor.belief",
                            {"actor": "bob", "topic": "alice_request",
                             "statement": "Alice needs the final Q2 numbers "
                                          "confirmed for her Monday summary.",
                             "basis": f"her email ({req_id}), read in full"})]
                if not self.reply:
                    updates.append(("actor.plan",
                                    {"actor": "bob",
                                     "plan": "Deep in quarter-close reviews; will "
                                             "answer Alice later in the week."}))
                    return Decision(updates=updates,
                                    note="Read Alice's email but deferring the reply")
                q2 = view.beliefs["q2_numbers"].statement
                content = f"Hi Alice -- confirmed: {q2}"
                return Decision(
                    updates=updates,
                    intentions=[Intention(
                        "send_message",
                        {"to": "alice", "channel": "email", "content": content,
                         "data": {"type": "reply", "thread": "q2",
                                  "in_reply_to": req_id}},
                        duration=Duration(timedelta(minutes=12), "actor_chosen",
                                          "double-checks the ledger figure while "
                                          "composing"),
                        note="answering Alice's confirmation request")],
                    note="Replying with the confirmed Q2 total")
            if av.verb == "send_message":
                return Decision(
                    updates=[("actor.plan", {"actor": "bob",
                                             "plan": "Back to quarter-close work."})],
                    note="Reply sent")
        return Decision(note="nothing further to do right now")


REVIEW = """# Reality-fidelity review -- email world

## What is real-world faithful here
- **Time is real.** Alice's email leaves at 21:18:30 ET Friday (composing took
  8 minutes after her 21:10 decision, delivery 30s). Bob does not see it for
  the whole weekend; his notice fires Monday 09:00 Pacific. The elapsed gap is
  61h41m30s, not 62h41m30s, because 2026-03-08 (spring forward) removed an
  hour -- the kernel derived that from the tz database, not from a modeler.
- **Information is local.** Bob's reply exists only because a noticed,
  delivered message carried Alice's question; his answer quotes his own prior
  belief (the $4.2M figure he locked on March 3), not world state he cannot
  see.
- **Nothing is instant.** notice -> read (6 min) -> interpret -> compose
  (12 min) -> deliver (30s) -> Alice notices on her half-hour cadence.

## Honest limitations (labeled, not hidden)
- The 30-minute inbox cadence is an *inferred* attention model ("office
  worker") and is marked as such in the rule's provenance. Real noticing is
  burstier: phones buzz, people peek at 22:00. A phone-notification channel
  with its own rule would be the faithful extension.
- Bob starts reading the instant he notices. Realistically there is a
  seconds-to-minutes gap (finishing coffee, other emails first). The kernel
  supports it (the mind could schedule the read later); the scripted mind
  keeps it simple.
- Weekend attention is modeled as *zero*, which overstates disconnection --
  many people glance at email on Saturday. The correction would again be an
  explicit, provenance-labeled weekend rule, not a kernel change.
"""
