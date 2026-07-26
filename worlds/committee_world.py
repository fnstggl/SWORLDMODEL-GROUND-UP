"""Hand-authored test world 2: a small group decision.

    new data arrives -> committee members receive it -> members discuss
    -> proposal appears -> members vote -> votes are counted

A scheduled inflation release (Wed 08:00 Mexico City) is noticed by the
staff analyst, who spends four labeled hours preparing a briefing and emails
it to the three committee members.  Two of them read it before Thursday's
10:00 meeting; Fran is traveling and does not check email until Friday, so
she votes on her stale belief.  The meeting is a scheduled commitment; the
chair puts a motion on the floor (spoken, zero-latency channel, immediate
attention because everyone is in the room); a vote is an *authorized
decision record* -- `fact.set vote:<member>` guarded by declarative
authority/precondition data.  "Vote" is scenario meaning, not an engine
capability.  The tally is computed mechanically from those records.
"""
from __future__ import annotations

from datetime import date, time as dtime, timedelta

from sworldmodel import (ActorState, AttentionRule, BusinessCalendar, Decision,
                         Duration, Intention, Mind, Terminal, World, at_local, iso)
from .adapters import READ_MESSAGE, SEND_MESSAGE

TZ_MX = "America/Mexico_City"

START = at_local(2026, 6, 23, 8, 0, tz=TZ_MX)          # Tuesday
RELEASE_AT = at_local(2026, 6, 24, 8, 0, tz=TZ_MX)     # Wednesday 08:00
MEETING_AT = at_local(2026, 6, 25, 10, 0, tz=TZ_MX)    # Thursday 10:00
CUTOFF = at_local(2026, 6, 25, 12, 0, tz=TZ_MX)        # Thursday noon

MEMBERS = ("dana", "eli", "fran")
QUESTION = ("What does the committee decide on the policy rate at the "
            "2026-06-25 meeting (hold or cut), counted from cast votes?")

PROPOSE_MOTION = {
    "verb": "propose_motion",
    "description": ("Put a motion on the floor (chair only, meeting in "
                    "session). params: motion."),
    "conditions": [
        {"require": "fact_equals", "key": "meeting_open", "value": True},
        {"require": "role_in", "roles": ["chair"]},
        {"require": "fact_absent", "key": "motion"},
        {"require": "param_nonempty", "param": "motion"},
    ],
    "effects": [
        ["fact.set", {"key": "motion", "value": "{params.motion}"}],
        ["info.send_new", {"author": "{actor}",
                           "to": {"role_in": ["chair", "member"],
                                  "exclude": ["{actor}"]},
                           "channel": "meeting_floor",
                           "content": "Motion on the floor: {params.motion}. "
                                      "Please vote.",
                           "data": {"type": "motion", "motion": "{params.motion}"}}],
        ["actor.memory", {"actor": "{actor}", "kind": "note",
                          "content": "Put the motion on the floor: {params.motion}",
                          "source": "{action_id}"}],
    ],
}

CAST_VOTE = {
    "verb": "cast_vote",
    "description": ("Cast your vote on the motion on the floor (members only, "
                    "meeting in session, one vote each). params: motion, choice "
                    "(hold|cut)."),
    "conditions": [
        {"require": "fact_equals", "key": "meeting_open", "value": True},
        {"require": "role_in", "roles": ["chair", "member"]},
        {"require": "fact_equals", "key": "motion", "value": "{params.motion}"},
        {"require": "fact_absent", "key": "vote:{actor}"},
        {"require": "param_in", "param": "choice", "values": ["hold", "cut"]},
    ],
    "effects": [
        ["fact.set", {"key": "vote:{actor}", "value": "{params.choice}"}],
        ["actor.memory", {"actor": "{actor}", "kind": "note",
                          "content": "Voted {params.choice} on: {params.motion}",
                          "source": "{action_id}"}],
    ],
}

PREPARE_BRIEFING = {
    "verb": "prepare_briefing",
    "description": ("Prepare a staff briefing from a noticed release and "
                    "email it to the committee. params: based_on_info, content."),
    "conditions": [
        {"require": "role_in", "roles": ["staff analyst"]},
        {"require": "noticed_info", "info": "{params.based_on_info}"},
        {"require": "param_nonempty", "param": "content"},
    ],
    "effects": [
        ["info.send_new", {"author": "{actor}",
                           "to": {"role_in": ["chair", "member"]},
                           "channel": "email",
                           "content": "{params.content}",
                           "data": {"type": "briefing",
                                    "based_on": "{params.based_on_info}"}}],
        ["actor.memory", {"actor": "{actor}", "kind": "note",
                          "content": "Sent the inflation briefing to the committee.",
                          "source": "{action_id}"}],
    ],
}


def build(fran_traveling: bool = True):
    w = World(START)
    for name, latency, basis, note in (
            ("data_wire", 5, "verified", "electronic wire push at release time"),
            ("email", 30, "verified", "typical email delivery time"),
            ("meeting_floor", 0, "verified", "spoken aloud in the meeting room")):
        w.apply("channel.add", {"name": name,
                                "latency": {"seconds": latency, "basis": basis,
                                            "note": note}}, None)
    for defn in (SEND_MESSAGE, READ_MESSAGE, PROPOSE_MOTION, CAST_VOTE,
                 PREPARE_BRIEFING):
        w.apply("action.define", defn, None)

    mx_cal = BusinessCalendar(tz=TZ_MX, open_time=dtime(9, 0), close_time=dtime(18, 0))
    staff_cal = BusinessCalendar(tz=TZ_MX, open_time=dtime(8, 0), close_time=dtime(18, 0))
    in_room = AttentionRule(None, None, "verified",
                            "present in the meeting room; speech is heard at once")
    stale_belief = ("Inflation has been running near 4 percent, above target.",
                    "May CPI report")

    gus = ActorState(
        id="gus", name="Gustavo Pena", role="staff analyst", tz=TZ_MX,
        attention={"data_wire": AttentionRule(staff_cal, None, "verified",
                                              "watching the release calendar is his "
                                              "job; the release time is scheduled")},
        goals=["brief the committee accurately and fast on new data"],
        values=["rigorous", "neutral"],
        plan="Watch Wednesday's inflation release and brief the committee.")
    w.apply("actor.add", gus.to_dict(), None)

    def member(mid, name, role, values, email_rule):
        st = ActorState(
            id=mid, name=name, role=role, tz=TZ_MX,
            attention={"email": email_rule, "meeting_floor": in_room},
            goals=["decide the policy rate responsibly"],
            values=values,
            relationships={m: "committee colleague" for m in MEMBERS if m != mid},
            plan="Review incoming analysis before Thursday's meeting.")
        w.apply("actor.add", st.to_dict(), None)
        w.apply("actor.belief", {"actor": mid, "topic": "inflation",
                                 "statement": stale_belief[0],
                                 "basis": stale_belief[1]}, None)
        w.apply("actor.commit", {"actor": mid, "id": "m1",
                                 "what": "attend the policy meeting",
                                 "at": iso(MEETING_AT)}, None)

    member("dana", "Dana Ortiz", "chair",
           ["institutionally cautious; discounts single data points"],
           AttentionRule(mx_cal, timedelta(minutes=60), "inferred",
                         "senior official; assistant batches email roughly hourly"))
    member("eli", "Elias Roth", "member",
           ["data-driven; responds to new evidence"],
           AttentionRule(mx_cal, timedelta(minutes=30), "inferred",
                         "checks email frequently between engagements"))
    fran_rule = (AttentionRule(
                     BusinessCalendar(tz=TZ_MX, open_time=dtime(9, 0),
                                      close_time=dtime(18, 0),
                                      holidays=frozenset({date(2026, 6, 24),
                                                          date(2026, 6, 25)})),
                     timedelta(minutes=30), "verified",
                     "travel schedule: offline Wednesday-Thursday, resumes Friday")
                 if fran_traveling else
                 AttentionRule(mx_cal, timedelta(minutes=30), "inferred",
                               "checks email frequently between engagements"))
    member("fran", "Francisca Duarte", "member",
           ["data-driven; responds to new evidence"], fran_rule)

    # scheduled reality (data, not code): the release and the meeting
    w.schedule("world.ops",
               {"ops": [
                   ["fact.set", {"key": "inflation_release",
                                 "value": "3.1% y/y (below expectations)"}],
                   ["info.send_new", {"author": "statistics_wire", "to": ["gus"],
                                      "channel": "data_wire",
                                      "content": "June inflation printed 3.1% y/y, "
                                                 "below the 3.6% consensus and "
                                                 "moving toward target.",
                                      "data": {"type": "data_release",
                                               "series": "inflation"}}]],
                "note": "scheduled statistical release (verified: official "
                        "calendar)"},
               RELEASE_AT, None)
    w.schedule("world.ops",
               {"ops": [["fact.set", {"key": "meeting_open", "value": True}]],
                "note": "the policy meeting is called to order (verified: "
                        "official meeting calendar)"},
               MEETING_AT, None)
    for mid in MEMBERS:
        w.schedule("wake.actor",
                   {"actor": mid, "reason": "scheduled_commitment",
                    "detail": "m1: the policy meeting begins"}, MEETING_AT, None)
    minds = {"gus": GusMind(),
             "dana": MemberMind("dana"), "eli": MemberMind("eli"),
             "fran": MemberMind("fran")}
    return w, minds, make_terminal()


def make_terminal() -> Terminal:
    def evaluate(world, final):
        votes = {m: world.facts.get(f"vote:{m}") for m in MEMBERS}
        cast = {m: v for m, v in votes.items() if v is not None}
        producers = [f"record:{r['seq']}" for r in world.records
                     if r["op"] == "fact.set"
                     and r["data"]["key"].startswith("vote:")]
        if len(cast) == len(MEMBERS):
            hold = sum(1 for v in cast.values() if v == "hold")
            cut = len(cast) - hold
            winner = "hold" if hold > cut else "cut" if cut > hold else "tie"
            return {"answer": winner,
                    "detail": f"votes: {cast} -> {winner} {max(hold, cut)}-"
                              f"{min(hold, cut)}",
                    "computed_from": producers}
        if final:
            return {"answer": "no decision",
                    "detail": f"only {len(cast)} of {len(MEMBERS)} votes were "
                              f"cast before the cutoff: {cast}",
                    "computed_from": producers or ["terminal.cutoff"]}
        return None
    return Terminal(QUESTION, CUTOFF, evaluate)


class GusMind(Mind):
    def decide(self, view):
        for iv in view.new_information:
            if iv.data.get("type") == "data_release":
                content = (f"Staff briefing on the June release: {iv.content} "
                           f"Staff assessment: inflation is below expectations "
                           f"and approaching target.")
                return Decision(
                    updates=[("actor.belief",
                              {"actor": "gus", "topic": "inflation",
                               "statement": "June inflation was 3.1% y/y, below "
                                            "expectations.",
                               "basis": f"wire release {iv.id}"})],
                    intentions=[Intention(
                        "prepare_briefing",
                        {"based_on_info": iv.id, "content": content},
                        duration=Duration(timedelta(hours=4), "inferred",
                                          "comparable staff analyses take about "
                                          "half a working day"),
                        note="turn the release into a committee briefing")],
                    note="Release is out; preparing the briefing")
        for av in view.completed:
            if av.verb == "prepare_briefing":
                return Decision(note="Briefing out to the committee")
        return Decision(note="nothing to do")


class MemberMind(Mind):
    def __init__(self, member_id: str) -> None:
        self.member_id = member_id

    def _choice(self, view) -> str:
        data_driven = any("responds to new evidence" in v for v in view.values)
        belief = view.beliefs.get("inflation")
        sees_soft_print = bool(belief) and "below expectations" in belief.statement
        return "cut" if (data_driven and sees_soft_print) else "hold"

    def decide(self, view):
        me = self.member_id
        for iv in view.new_information:
            if iv.data.get("type") == "briefing":
                return Decision(
                    intentions=[Intention(
                        "read_message", {"info": iv.id, "content": iv.content},
                        duration=Duration(timedelta(minutes=20), "inferred",
                                          "a data briefing takes a focused read"),
                        note="reading the staff briefing")],
                    note="Staff briefing arrived; reading it")
            if iv.data.get("type") == "motion":
                return Decision(
                    intentions=[Intention(
                        "cast_vote",
                        {"motion": iv.data["motion"], "choice": self._choice(view)},
                        duration=Duration(timedelta(minutes=2), "actor_chosen",
                                          "stating a vote in the room"),
                        note="voting on the motion")],
                    note=f"Voting {self._choice(view)} based on current beliefs")
        for av in view.completed:
            if av.verb == "read_message" and "below" in av.params.get("content", ""):
                return Decision(
                    updates=[("actor.belief",
                              {"actor": me, "topic": "inflation",
                               "statement": "Staff analysis: inflation printed "
                                            "below expectations and is approaching "
                                            "target.",
                               "basis": f"staff briefing {av.params.get('info')}, "
                                        f"read in full"})],
                    note="Updating on the staff briefing")
            if av.verb == "propose_motion":
                return Decision(
                    intentions=[Intention(
                        "cast_vote",
                        {"motion": av.params["motion"], "choice": self._choice(view)},
                        duration=Duration(timedelta(minutes=2), "actor_chosen",
                                          "stating a vote in the room"),
                        note="chair votes after opening the motion")],
                    note="Motion is on the floor; casting the chair's vote")
        kinds = {r["kind"] for r in view.reasons}
        if "scheduled_commitment" in kinds:
            if view.role == "chair":
                return Decision(
                    intentions=[Intention(
                        "propose_motion", {"motion": "hold the policy rate"},
                        duration=Duration(timedelta(minutes=5), "actor_chosen",
                                          "opening remarks and stating the motion"),
                        note="chairing: putting the motion to a vote")],
                    updates=[("actor.emotion", {"actor": me,
                                                "statement": "focused; running the "
                                                             "meeting"})],
                    note="Meeting open; putting the hold motion on the floor")
            return Decision(
                updates=[("actor.emotion", {"actor": me,
                                            "statement": "attentive; in the meeting"})],
                note="In the meeting; waiting for the chair")
        return Decision(note="nothing to do")


REVIEW = """# Reality-fidelity review -- committee world

## What is real-world faithful here
- **Scheduled reality drives the timeline.** The release (Wed 08:00) and the
  meeting (Thu 10:00) are calendar facts, not simulation rounds. Nobody is
  polled between them.
- **Analysis takes time.** The staff briefing consumes four labeled hours; it
  reaches members just after noon, and each notices it on their own attention
  pattern (hourly batching for the chair, half-hourly for Eli, not at all for
  traveling Fran). Information locality does real work: Fran votes hold on a
  stale belief because she genuinely never saw the briefing.
- **Authority is enforced by the world.** Only the chair can put a motion on
  the floor; double votes are rejected; the tally is computed only from cast
  vote records -- there is no path from anyone's belief straight to the
  outcome.

## Honest limitations (labeled, not hidden)
- **No real discussion.** A real meeting has argument, persuasion and
  amendment; here the chair states one motion and members vote their current
  beliefs. The kernel supports message exchange on the floor channel; richer
  deliberation needs richer minds (Phase B direction), not new engine parts.
- **Attention cadences are inferred** ("assistant batches email hourly") and
  labeled as such; real senior officials' attention is far less regular.
- **Beliefs move in one step.** Members flip from "near 4%" to "below
  expectations" after one briefing; real belief revision is noisier and
  socially mediated.
- Dana's caution is a disposition sentence driving a scripted rule --
  transparent but shallow; an LLM mind would trade transparency for richness.
"""
