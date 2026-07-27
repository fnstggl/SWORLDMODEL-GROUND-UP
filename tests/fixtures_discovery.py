"""Hand-authored discovery documents for the graph/assembly/proof tests.

The toy world is the directive's own example: Alice and Bob exist; Alice
can email Bob; Bob may notice or miss it; Bob may reply or not; Alice may
notice or miss the reply; YES means Alice reads Bob's confirmation before
the deadline. Nothing here predicts what either of them will do -- the
spine records what CAN happen and what each step needs.
"""
import copy

EVIDENCE_IDS = frozenset({"e1", "e2", "e3", "e4", "e5"})

RESOLUTION = {
    "terminal_meaning": "Whether Alice has read Bob's confirmation before "
                        "Friday 17:00 local time.",
    "answer_type": "boolean",
    "cutoff": {"when": "2026-03-06T17:00:00", "timezone": "America/New_York",
               "meaning": "end of business on Friday"},
    "positive_condition": "Alice has read Bob's confirmation before the "
                          "cutoff.",
    "negative_condition": "The cutoff passes without Alice having read it.",
    "proof": [
        {"kind": "state", "name": "alice has read bobs confirmation",
         "meaning": "Alice has actually read the reply, not merely "
                    "received it in an unread inbox."},
    ],
    "resolves_from_report": False,
    "measured_act": None,
    "ambiguities": [],
    "basis": "question_given", "evidence_ids": [],
}

SPINE = {"steps": [
    {"name": "alice sends the request",
     "kind": "actor_decision",
     "meaning": "Alice can email Bob asking for confirmation.",
     "prerequisites": [],
     "basis": "verified", "evidence_ids": ["e1"]},
    {"name": "bob has seen alices request",
     "kind": "condition",
     "meaning": "Bob has noticed the request in his inbox.",
     "prerequisites": [{"step": "alice sends the request"}],
     "basis": "inferred", "evidence_ids": ["e2"]},
    {"name": "bob sends a confirmation",
     "kind": "actor_decision",
     "meaning": "Bob can reply confirming; he may also not reply.",
     "prerequisites": [{"step": "bob has seen alices request"}],
     "uncertainty": "Bob may choose not to reply at all.",
     "basis": "uncertain", "evidence_ids": []},
    {"name": "bobs confirmation available to alice",
     "kind": "condition",
     "meaning": "The reply has been delivered where Alice can notice it.",
     "prerequisites": [{"step": "bob sends a confirmation"}],
     "basis": "inferred", "evidence_ids": ["e2"]},
    {"name": "alice reads the confirmation",
     "kind": "actor_decision",
     "meaning": "Alice can open and read the reply once it is there.",
     "prerequisites": [{"step": "bobs confirmation available to alice"}],
     "produces_proof": ["alice has read bobs confirmation"],
     "basis": "uncertain", "evidence_ids": []},
]}

PRODUCERS = {"assignments": [
    {"step": "alice sends the request",
     "producers": [{"name": "Alice Chen", "kind": "person",
                    "meaning": "Project coordinator; the asker.",
                    "basis": "verified", "evidence_ids": ["e1"]}]},
    {"step": "bob has seen alices request",
     "producers": [{"name": "work email", "kind": "communication_system",
                    "meaning": "The company email system both use.",
                    "basis": "verified", "evidence_ids": ["e2"]}]},
    {"step": "bob sends a confirmation",
     "producers": [{"name": "Bob Marsh", "kind": "person",
                    "meaning": "The counterpart whose confirmation is "
                               "needed.",
                    "basis": "verified", "evidence_ids": ["e1"]}]},
    {"step": "bobs confirmation available to alice",
     "producers": [{"name": "work email", "kind": "communication_system",
                    "meaning": "Same email system, return direction.",
                    "basis": "verified", "evidence_ids": ["e2"]}]},
    {"step": "alice reads the confirmation",
     "producers": [{"name": "Alice Chen", "kind": "person",
                    "meaning": "Only Alice can do her own reading.",
                    "basis": "verified", "evidence_ids": ["e1"]}]},
]}

STATE_INFO = {"entities": [
    {"name": "Alice Chen",
     "timezone": "America/New_York",
     "availability": {"workdays": [0, 1, 2, 3, 4],
                      "open": "09:00", "close": "17:00"},
     "initial_state": [
         {"name": "alice needs bobs confirmation",
          "meaning": "Alice's request is outstanding as the world opens.",
          "basis": "question_given"}],
     "commitments": [
         {"name": "alice workday starts",
          "meaning": "Alice is at her desk from Monday morning.",
          "when": "2026-03-02T09:00:00",
          "basis": "inferred", "evidence_ids": ["e3"]}],
     "channels": [
         {"name": "work email", "role": "both",
          "meaning": "Alice sends and receives on the company system.",
          "latency_meaning": "delivery within about a minute",
          "attention": {"cadence_minutes": 30,
                        "meaning": "checks about every half hour",
                        "calendar_meaning": "her business hours"},
          "basis": "verified", "evidence_ids": ["e2"]}]},
    {"name": "Bob Marsh",
     "timezone": "America/New_York",
     "availability": {"workdays": [0, 1, 2, 3, 4],
                      "open": "09:00", "close": "17:00"},
     "channels": [
         {"name": "work email", "role": "both",
          "meaning": "Bob reads and answers on the same system.",
          "latency_meaning": "delivery within about a minute",
          "attention": {"cadence_minutes": 60,
                        "meaning": "checks about hourly",
                        "calendar_meaning": "his business hours"},
          "basis": "verified", "evidence_ids": ["e4"]}],
     "not_available": [
         {"meaning": "Bob is at an offsite with no email on Wednesday.",
          "channel": "work email",
          "from": "2026-03-04T00:00:00", "to": "2026-03-04T23:59:59"}]},
]}

UNCERTAINTY = {
    "uncertainties": [
        {"about": "bob sends a confirmation",
         "meaning": "Bob may not reply before the cutoff, or at all."}],
    "exclusions": [
        {"name": "Bobs assistant",
         "why_safe": "No evidence anyone else reads or answers this inbox.",
         "basis": "inferred", "evidence_ids": ["e5"]}],
}


def docs():
    """Fresh deep copies, so tests can mutate freely."""
    return (copy.deepcopy(RESOLUTION), copy.deepcopy(SPINE),
            copy.deepcopy(PRODUCERS), copy.deepcopy(STATE_INFO),
            copy.deepcopy(UNCERTAINTY))
