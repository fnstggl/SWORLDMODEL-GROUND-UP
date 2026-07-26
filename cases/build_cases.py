"""Frozen, hand-prepared evidence packages for the acceptance cases.

There is NO live retrieval anywhere in this run. Each package is the
compiler's only factual basis, and each claim carries a source, an as-of
timestamp and an epistemic status so the compiler can tell verified fact from
reasonable inference. Cases are deliberately drawn from domains unlike the
three hand-authored runtime worlds.

    python3 cases/build_cases.py    ->  writes cases/<name>/{question,evidence_package}.json
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def claim(cid, text, source, as_of, status="verified", visibility="public"):
    return {"id": cid, "claim": text, "source": source, "as_of": as_of,
            "status": status, "visibility": visibility}


CASES = {}

# ---------------------------------------------------------------------------
# 1. DIRECT COMMUNICATION -- a document must reach a decision-maker in time
# ---------------------------------------------------------------------------
CASES["traffic_study"] = {
    "question": {
        "question": "Will Councilmember Reyes have read the finalized traffic "
                    "study before the council meeting begins?",
        "deadline": "2026-02-19T19:00:00-06:00",
        "resolution_note": "YES only if Reyes has actually noticed and read the "
                           "finalized study before the meeting starts. Receiving "
                           "it in an unread inbox does not count.",
    },
    "evidence": {
        "package_id": "ev_traffic_study_2026_02",
        "prepared_at": "2026-02-16T09:00:00-06:00",
        "note": "Hand-frozen package. No live retrieval.",
        "claims": [
            claim("e1", "Councilmember Alma Reyes sits on the Austin city "
                        "council transportation committee and will vote on the "
                        "Riverside corridor item at the 19 February meeting.",
                  "City of Austin council agenda, published 2026-02-12",
                  "2026-02-12T00:00:00-06:00"),
            claim("e2", "The council meeting begins Thursday 19 February 2026 at "
                        "7:00 PM America/Chicago.",
                  "City of Austin council agenda", "2026-02-12T00:00:00-06:00"),
            claim("e3", "Miguel Santos is the city transportation engineer "
                        "responsible for finalizing the Riverside corridor "
                        "traffic study.",
                  "City staff directory", "2026-01-30T00:00:00-06:00"),
            claim("e4", "Santos told the committee clerk on 16 February that the "
                        "study is complete except for a final peer-review "
                        "sign-off, which the external reviewer has committed to "
                        "deliver by 10:00 AM America/Chicago on 18 February.",
                  "Clerk's memo to committee members, 2026-02-16",
                  "2026-02-16T14:00:00-06:00"),
            claim("e4b", "Santos's documented practice is to email a finalized "
                         "study to council members within the hour after he "
                         "receives peer-review sign-off; the clerk confirms he "
                         "has done so for every corridor item this term.",
                   "Clerk's memo, 2026-02-16, and 2026 distribution log",
                   "2026-02-16T14:00:00-06:00"),
            claim("e5", "City staff distribute finalized studies to council "
                        "members as PDF attachments on the city email system.",
                  "Council operating procedure sec. 4.2",
                  "2025-06-01T00:00:00-05:00"),
            claim("e6", "Reyes works Monday to Friday from 8:30 AM to 6:00 PM "
                        "America/Chicago, and her chief of staff states she "
                        "reviews council email in a block at the start of each "
                        "working day and roughly every two hours thereafter.",
                  "Interview with Reyes's chief of staff, 2026-02-13",
                  "2026-02-13T00:00:00-06:00", status="verified"),
            claim("e7", "Reyes has stated publicly that she reads corridor "
                        "studies in full before voting on them, and that a study "
                        "arriving the day of a vote is 'not something I can "
                        "responsibly act on'.",
                  "Austin Monitor interview, 2025-11-04",
                  "2025-11-04T00:00:00-06:00"),
            claim("e8", "A finalized Riverside corridor study of this type runs "
                        "roughly 60 pages; comparable studies have taken Reyes's "
                        "office 60 to 90 minutes to read.",
                  "Chief of staff, describing prior corridor items",
                  "2026-02-13T00:00:00-06:00", status="inferred"),
            claim("e9", "City email delivers internally within about a minute.",
                  "City IT service description", "2025-09-01T00:00:00-05:00"),
            claim("e10", "Santos works Monday to Friday, 8:00 AM to 4:30 PM "
                         "America/Chicago, and checks email hourly during the "
                         "working day.",
                   "City staff schedule and clerk's description",
                   "2026-02-16T00:00:00-06:00", status="inferred"),
        ],
    },
}

# ---------------------------------------------------------------------------
# 2. INSTITUTIONAL DECISION -- an authorized body decides under a rule
# ---------------------------------------------------------------------------
CASES["ethics_committee"] = {
    "question": {
        "question": "Does the hospital ethics committee approve the "
                    "compassionate-use request at its 12 March meeting?",
        "deadline": "2026-03-12T16:00:00-04:00",
        "resolution_note": "The answer is whichever outcome the committee's "
                           "recorded votes produce under its own majority rule. "
                           "If the required votes are not cast before the "
                           "meeting ends, there is no decision.",
    },
    "evidence": {
        "package_id": "ev_ethics_committee_2026_03",
        "prepared_at": "2026-03-09T08:00:00-04:00",
        "note": "Hand-frozen package. No live retrieval.",
        "claims": [
            claim("e1", "St. Brendan's Hospital ethics committee has three "
                        "voting members: Dr. Helen Osei (chair), Dr. Raj Patel, "
                        "and Sister Margaret Doyle (lay member).",
                  "Hospital committee roster", "2026-01-15T00:00:00-05:00"),
            claim("e2", "The committee decides by simple majority of votes cast; "
                        "the chair puts a motion and members vote in the room.",
                  "Committee charter sec. 3", "2024-04-01T00:00:00-04:00"),
            claim("e3", "The committee meets 12 March 2026 at 2:00 PM "
                        "America/New_York to consider a compassionate-use "
                        "request for an unapproved oncology therapy.",
                  "Meeting notice", "2026-03-05T00:00:00-05:00"),
            claim("e4", "Hospital pharmacist Tomas Lindqvist was asked to prepare "
                        "a safety review of the therapy and circulate it to "
                        "members before the meeting.",
                  "Chair's request, minuted 2026-03-05",
                  "2026-03-05T00:00:00-05:00"),
            claim("e5", "The manufacturer released updated trial safety data on "
                        "10 March 2026 at 8:00 AM America/New_York showing a "
                        "lower rate of severe adverse events than previously "
                        "reported.",
                  "Manufacturer investor bulletin", "2026-03-10T08:00:00-04:00"),
            claim("e6", "Lindqvist monitors manufacturer bulletins as part of his "
                        "role and acts on them the same working day.",
                  "Pharmacy department procedure", "2025-08-01T00:00:00-04:00",
                  status="inferred"),
            claim("e7", "A safety review of this kind takes Lindqvist roughly "
                        "half a working day to prepare.",
                  "Comparable prior reviews", "2026-03-05T00:00:00-05:00",
                  status="inferred"),
            claim("e8", "Reviews are circulated to committee members by hospital "
                        "email, which delivers within about a minute.",
                  "Hospital IT", "2025-09-01T00:00:00-04:00"),
            claim("e9", "Dr. Osei has said she will not approve compassionate use "
                        "without current safety data, and considers the older "
                        "adverse-event rate disqualifying.",
                  "Minutes of 2026-02-12 meeting", "2026-02-12T00:00:00-05:00"),
            claim("e10", "Dr. Patel has consistently voted to approve "
                         "compassionate use where a safety review is available "
                         "and favourable.",
                   "Voting record 2024-2025", "2026-01-15T00:00:00-05:00"),
            claim("e11", "Sister Doyle votes with the documented safety "
                         "assessment when one has been provided to her.",
                   "Voting record 2024-2025", "2026-01-15T00:00:00-05:00"),
            claim("e12", "Osei and Patel work at the hospital and check email "
                         "several times during the working day; Doyle is "
                         "off-site on retreat from 10 to 12 March and the "
                         "hospital has no email contact with her during it, but "
                         "she attends the meeting in person.",
                   "Chair's assistant, 2026-03-09", "2026-03-09T00:00:00-05:00"),
            claim("e13", "Members are present in the meeting room and hear "
                         "motions put by the chair immediately.",
                   "Committee charter sec. 3", "2024-04-01T00:00:00-04:00"),
            claim("e14", "Stating a vote in the room takes a moment; the chair's "
                         "opening remarks and motion take about five minutes.",
                   "Prior meeting minutes", "2026-02-12T00:00:00-05:00",
                   status="inferred"),
        ],
    },
}

# ---------------------------------------------------------------------------
# 3. OPERATIONAL QUANTITY -- continuous processes against a deadline
# ---------------------------------------------------------------------------
CASES["blood_units"] = {
    "question": {
        "question": "How many usable blood units will the regional hospital "
                    "have received by Friday noon?",
        "deadline": "2026-07-24T12:00:00-07:00",
        "resolution_note": "The answer is the number of units the hospital "
                           "actually holds at the deadline.",
    },
    "evidence": {
        "package_id": "ev_blood_units_2026_07",
        "prepared_at": "2026-07-20T07:00:00-07:00",
        "note": "Hand-frozen package. No live retrieval.",
        "claims": [
            claim("e1", "The Cascade regional blood centre operates a mobile "
                        "collection drive at its Portland site.",
                  "Blood centre operations page", "2026-07-01T00:00:00-07:00"),
            claim("e2", "The drive collects at a measured average of 12 usable "
                        "units per hour while it is open.",
                  "Centre's 2026 throughput report",
                  "2026-07-01T00:00:00-07:00"),
            claim("e3", "The drive is open Monday to Friday from 9:00 AM to "
                        "5:00 PM America/Los_Angeles.",
                  "Published drive schedule", "2026-07-01T00:00:00-07:00"),
            claim("e4", "The collection week under consideration runs Monday "
                        "20 July to Friday 24 July 2026.",
                  "Drive schedule", "2026-07-01T00:00:00-07:00"),
            claim("e5", "The centre held 40 usable units in stock at 9:00 AM on "
                        "Monday 20 July 2026.",
                  "Centre inventory log", "2026-07-20T09:00:00-07:00"),
            claim("e6", "St. Vincent regional hospital held 15 usable units at "
                        "the same moment.",
                  "Hospital blood bank log", "2026-07-20T09:00:00-07:00"),
            claim("e7", "The centre ships its available stock to St. Vincent "
                        "every Tuesday and Thursday at 4:00 PM "
                        "America/Los_Angeles.",
                  "Standing distribution agreement",
                  "2026-01-01T00:00:00-08:00"),
            claim("e8", "A shipment takes about 3 hours to reach the hospital "
                        "and be received into its bank.",
                  "Courier service level and prior receipts",
                  "2026-07-01T00:00:00-07:00", status="inferred"),
            claim("e9", "The Tuesday and Thursday shipments each move 150 units, "
                        "the capacity of the centre's transport cooler.",
                  "Distribution agreement, cooler specification",
                  "2026-01-01T00:00:00-08:00"),
            claim("e10", "Bank supervisor Elena Cruz oversees receipts at the "
                         "hospital but does not control the collection rate or "
                         "the shipping schedule.",
                   "Hospital staff directory", "2026-06-01T00:00:00-07:00"),
        ],
    },
}

# ---------------------------------------------------------------------------
# 4. NEGOTIATION -- offers and acceptance under a hard deadline
# ---------------------------------------------------------------------------
CASES["wage_talks"] = {
    "question": {
        "question": "Will the union and the employer reach a signed wage "
                    "agreement before the strike deadline?",
        "deadline": "2026-10-31T23:59:00-05:00",
        "resolution_note": "YES only if an agreement has actually been recorded "
                           "as accepted by both sides before the deadline.",
    },
    "evidence": {
        "package_id": "ev_wage_talks_2026_10",
        "prepared_at": "2026-10-26T09:00:00-05:00",
        "note": "Hand-frozen package. No live retrieval.",
        "claims": [
            claim("e1", "Local 214 represents 1,200 warehouse workers at Kessler "
                        "Logistics; its lead negotiator is Yolanda Bright.",
                  "Union public filing", "2026-09-01T00:00:00-05:00"),
            claim("e2", "Kessler Logistics' lead negotiator is Dennis Wozniak, "
                        "VP of operations, who has authority to accept an "
                        "agreement up to a 4.5 percent wage increase without "
                        "board approval.",
                  "Company statement to the mediator",
                  "2026-10-20T00:00:00-05:00"),
            claim("e3", "Bright has authority from a ratification vote to accept "
                        "any offer at or above a 4 percent wage increase.",
                  "Union ratification vote result, 2026-10-18",
                  "2026-10-18T00:00:00-05:00"),
            claim("e4", "The union set a strike deadline of 11:59 PM "
                        "America/Chicago on 31 October 2026.",
                  "Union strike notice", "2026-10-19T00:00:00-05:00"),
            claim("e5", "As of 26 October the employer's standing offer is a 3.5 "
                        "percent wage increase and the union's standing demand "
                        "is 5 percent.",
                  "Mediator's status memo", "2026-10-26T09:00:00-05:00"),
            claim("e6", "A mediated bargaining session is scheduled for 29 "
                        "October 2026 at 10:00 AM America/Chicago.",
                  "Mediator's scheduling notice", "2026-10-22T00:00:00-05:00"),
            claim("e7", "Both negotiators attend mediated sessions in person and "
                        "hear offers made at the table immediately.",
                  "Mediation protocol", "2026-10-22T00:00:00-05:00"),
            claim("e8", "Formulating and tabling a revised offer takes a "
                        "negotiator roughly 45 minutes of caucus time in "
                        "comparable sessions.",
                  "Mediator's description of prior rounds",
                  "2026-10-22T00:00:00-05:00", status="inferred"),
            claim("e9", "Wozniak has told the mediator he will move to 4.5 "
                        "percent, his full authority, only if the union first "
                        "comes down from 5 percent.",
                  "Mediator's status memo", "2026-10-26T09:00:00-05:00"),
            claim("e10", "Bright has told her executive board she is prepared to "
                         "come down to 4.5 percent at the mediated session to "
                         "avoid a strike.",
                   "Union executive board minutes, 2026-10-25",
                   "2026-10-25T00:00:00-05:00"),
            claim("e11", "An agreement is recorded as accepted when a negotiator "
                         "accepts the other side's tabled offer at the table.",
                   "Mediation protocol", "2026-10-22T00:00:00-05:00"),
        ],
    },
}

# ---------------------------------------------------------------------------
# 6. DELIBERATELY INSUFFICIENT -- must refuse, not improvise
# ---------------------------------------------------------------------------
CASES["insufficient_merger"] = {
    "question": {
        "question": "Will Halvorsen Group's board approve the Meridian "
                    "acquisition before the end of the quarter?",
        "deadline": "2026-12-31T17:00:00-05:00",
        "resolution_note": "YES only if the board records an approval before the "
                           "deadline.",
    },
    "evidence": {
        "package_id": "ev_insufficient_merger_2026_q4",
        "prepared_at": "2026-11-02T09:00:00-05:00",
        "note": "Hand-frozen package, deliberately insufficient: it contains no "
                "information about the board, its members, its schedule, its "
                "decision rule, or the state of the transaction. A compiler that "
                "produces a confident world from this is inventing it.",
        "claims": [
            claim("e1", "Halvorsen Group is a privately held logistics company "
                        "headquartered in Oslo.",
                  "Company website", "2026-10-01T00:00:00+02:00"),
            claim("e2", "Meridian Freight is a privately held company operating "
                        "in the same sector.",
                  "Company website", "2026-10-01T00:00:00+02:00"),
            claim("e3", "A trade publication reported in October 2026 that the "
                        "two companies 'are understood to have held talks', "
                        "without naming sources or describing any process.",
                  "Nordic Logistics Weekly, 2026-10-14",
                  "2026-10-14T00:00:00+02:00", status="inferred"),
            claim("e4", "Neither company has made any public statement about a "
                        "transaction.",
                  "Search of both companies' press pages",
                  "2026-11-02T00:00:00+01:00"),
        ],
    },
}


def main():
    for name, case in CASES.items():
        d = os.path.join(HERE, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "question.json"), "w", encoding="utf-8") as f:
            json.dump(case["question"], f, indent=2, sort_keys=True)
            f.write("\n")
        with open(os.path.join(d, "evidence_package.json"), "w",
                  encoding="utf-8") as f:
            json.dump(case["evidence"], f, indent=2, sort_keys=True)
            f.write("\n")
        print(f"wrote cases/{name}/ "
              f"({len(case['evidence']['claims'])} claims)")


if __name__ == "__main__":
    main()
