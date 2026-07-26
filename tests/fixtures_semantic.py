"""Hand-written semantic scenarios used to test the deterministic lowering
layer without spending model calls.

These are written the way the contract asks a model to write: names, natural
language and the fixed vocabularies -- no identifiers, no payloads, no code.
"""

# A two-party message exchange with a real weekend gap, expressed purely
# semantically.
MESSAGE_CASE = {
    "resolution": {
        "question": "Does the reporter get an on-record comment before the deadline?",
        "question_type": "boolean",
        "deadline": "2026-05-11T17:00:00-04:00",
        "yes_condition": "The reporter has noticed an on-record comment",
        "no_condition": "The deadline passes with no comment noticed",
        "observed_from": "what the reporter actually received and noticed",
        "observations": [
            {"observation_type": "participant_noticed_information",
             "participant": "Dana Whitfield", "tag": "on record comment",
             "description": "the reporter noticed the press officer's comment"}
        ],
    },
    "scope": {
        "included": ["the reporter", "the press officer", "work email",
                     "their working hours"],
        "excluded": [{"thing": "the newsroom's editors",
                      "reason": "they do not control whether a comment arrives"}],
    },
    "participants": [
        {"name": "Dana Whitfield", "kind": "person", "role": "reporter",
         "timezone": "America/New_York",
         "causal_relevance": "asks for the comment and must receive it",
         "evidence_ids": ["e1"],
         "availability": {"timezone": "America/New_York", "workdays": [0, 1, 2, 3, 4],
                          "open": "09:00", "close": "18:00"},
         "attention": [{"route": "work email", "status": "inferred",
                        "description": "checks email every 20 minutes while working",
                        "check_interval_minutes": 20}]},
        {"name": "Priya Raman", "kind": "person", "role": "press officer",
         "timezone": "Europe/London",
         "causal_relevance": "holds the authority to give an on-record comment",
         "evidence_ids": ["e2"],
         "availability": {"timezone": "Europe/London", "workdays": [0, 1, 2, 3, 4],
                          "open": "09:00", "close": "17:30"},
         "attention": [{"route": "work email", "status": "inferred",
                        "description": "reviews the press inbox hourly on workdays",
                        "check_interval_minutes": 60}]},
    ],
    "starting_state": [
        {"subject": "Priya Raman", "kind": "belief",
         "topic": "approved statement",
         "description": "The approved line is that the trial met its primary endpoint.",
         "visibility": "private", "status": "verified", "evidence_ids": ["e3"]},
    ],
    "communication_routes": [
        {"name": "work email",
         "description": "ordinary corporate email",
         "delivery_delay": {"description": "normal electronic delivery",
                            "status": "verified", "seconds": 45}},
    ],
    "information": [
        {"holder": "Dana Whitfield", "topic": "comment request",
         "content": "Can you give me an on-record comment on the trial result?",
         "route": "work email", "already_sent_to": ["Priya Raman"],
         "sent_time": "2026-05-08T18:40:00-04:00",
         "tag": "comment request",
         "basis": "the reporter's sent-mail record (e4)"},
    ],
    "scheduled_events": [
        {"description": "publication deadline passes",
         "time": "2026-05-11T17:00:00-04:00",
         "basis": "the newsroom's stated deadline (e5)",
         "effects": [{"change_type": "record_fact", "about": "publication deadline",
                      "value": "passed"}]},
    ],
    "processes": [],
    "action_affordances": [
        {"label": "send an on-record comment",
         "description": "reply to the reporter with the approved line",
         "available_to": {"participants": ["Priya Raman"]},
         "parameters": [
             {"name": "request", "description": "the request being answered",
              "fill_from": "noticed_information", "tag": "comment_request"}],
         "preconditions": [
             {"condition_type": "has_noticed_information", "from_parameter": "request"}],
         "duration": {"description": "time to clear and compose the line",
                      "status": "inferred", "typical_minutes": 25},
         "consequences_on_completion": [
             {"change_type": "send_information", "route": "work email",
              "tag": "on record comment",
              "description": "the on-record comment reaches the reporter",
              "content": "On the record: the trial met its primary endpoint.",
              "to": {"participants": ["Dana Whitfield"]}}]},
    ],
    "uncertainties": [
        {"description": "Whether the press officer needs legal sign-off first",
         "type": "procedural",
         "supported_possibilities": ["replies from the approved line directly",
                                     "waits for counsel and misses the deadline"],
         "evidence_ids": []},
    ],
    "terminal_producers": [
        {"terminal_component": "the reporter has an on-record comment",
         "can_be_produced_by": [
             "the press officer completes 'send an on-record comment'",
             "the comment is delivered on work email",
             "the reporter notices it during working hours"]},
    ],
}


# An operational quantity world: continuous production against a deadline.
QUANTITY_CASE = {
    "resolution": {
        "question": "How many finished units has the depot received by the cutoff?",
        "question_type": "quantity",
        "deadline": "2026-09-18T12:00:00+02:00",
        "measure_description": "units held by the depot",
        "observed_from": "the depot's received quantity",
        "observations": [
            {"observation_type": "quantity_measured", "holder": "Central Depot",
             "quantity": "finished units",
             "description": "units the depot actually holds"}],
    },
    "scope": {"included": ["the assembly line", "the depot"],
              "excluded": [{"thing": "retail demand",
                            "reason": "the question is about depot receipts only"}]},
    "participants": [
        {"name": "Assembly Line 3", "kind": "operating system",
         "role": "production line", "timezone": "Europe/Berlin",
         "causal_relevance": "produces the units", "evidence_ids": ["e1"]},
        {"name": "Central Depot", "kind": "organization", "role": "depot",
         "timezone": "Europe/Berlin",
         "causal_relevance": "receives and holds finished units",
         "evidence_ids": ["e2"]},
    ],
    "starting_state": [
        {"subject": "Assembly Line 3", "kind": "quantity",
         "quantity": {"name": "finished units", "holder": "Assembly Line 3",
                      "amount": 0},
         "status": "verified", "evidence_ids": ["e3"],
         "description": "the line starts the window with nothing staged"},
        {"subject": "Central Depot", "kind": "quantity",
         "quantity": {"name": "finished units", "holder": "Central Depot",
                      "amount": 120},
         "status": "verified", "evidence_ids": ["e4"],
         "description": "opening depot stock"},
    ],
    "communication_routes": [],
    "information": [],
    "scheduled_events": [
        {"description": "the shift week begins",
         "time": "2026-09-16T06:00:00+02:00",
         "basis": "plant shift calendar (e5)",
         "effects": [{"change_type": "record_fact", "about": "shift week",
                      "value": "running"}]},
        {"description": "a staged transfer moves stock to the depot",
         "time": "2026-09-17T18:00:00+02:00",
         "basis": "standing daily transfer at 18:00 (e6)",
         "effects": [{"change_type": "transfer_resource",
                      "quantity": "finished units",
                      "from": "Assembly Line 3", "to": "Central Depot",
                      "amount": 200}]},
    ],
    "processes": [
        {"name": "unit assembly", "owner": "Assembly Line 3",
         "output_quantity": "finished units",
         "description": "the line running at its rated speed",
         "rate": {"amount_per_hour": 25, "status": "verified",
                  "note": "rated line speed from the plant specification (e7)"},
         "operating_periods": {"description": "day shift", "timezone": "Europe/Berlin",
                               "workdays": [0, 1, 2, 3, 4],
                               "start": "06:00", "end": "14:00"}},
    ],
    "action_affordances": [],
    "uncertainties": [],
    "terminal_producers": [
        {"terminal_component": "units held by the depot",
         "can_be_produced_by": ["the standing transfer from the line",
                                "opening depot stock"]},
    ],
}
