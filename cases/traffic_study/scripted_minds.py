"""TEST-ONLY scripted minds for the traffic_study fixture.

Written by hand against this fixture's own affordance labels and message
tags. Nothing here is derived from compiler output, and nothing here models
what these people would actually decide -- it encodes only the plainest
reading of the evidence, so the compiled runtime objects get exercised:

    e4b  Santos emails the finalized study within the hour of sign-off
    e7   Reyes reads corridor studies in full before voting on them

The point is to prove the compiled world RUNS -- that authority, the noticed
information precondition, the composing and reading durations, the email
route and the terminal all wire together. A run driven by this script is not
a forecast and must never be reported as one.
"""

SCRIPT = {
    "Miguel Santos": [
        {"trigger": "notices",
         "tag": "peer review signoff",
         "action": "send the finalized study",
         "bind_from_notice": {"signoff": "id"},
         "why": "e4b: his documented practice is to distribute within the "
                "hour of receiving sign-off"},
    ],
    "Alma Reyes": [
        {"trigger": "notices",
         "tag": "finalized study",
         "action": "read the finalized study",
         "bind_from_notice": {"study": "id"},
         "why": "e7: she reads corridor studies in full before voting"},
    ],
}
