"""Frozen scenario data for the two Peter Thiel experiments.

Experiment-only.  The decision problem is the user's own file, copied
VERBATIM into ``data/peter_problem.json`` and read from there -- the two
``FREEZE_`` placeholders in ``time_horizon`` are the only substitution,
and they are replaced with the actual UTC run start and start + 7 days.

Nothing in this module authors simulation content.  It declares:

- how the compiler question is derived from the user's own
  ``desired_outcome`` (a pure format, no new claims);
- the harness scope note handed to the compiler as context (classified
  ``TEST_ASSUMPTION`` in the evidence manifest, because it is a modelling
  decision, not a fact about anyone);
- the evidence items, each classified conservatively;
- the declared evaluator, the simulation limits, and the base seed.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from .evidence import evidence_item

DATA_DIR = Path(__file__).resolve().parent / "data"
PROBLEM_PATH = DATA_DIR / "peter_problem.json"

SUPPLIED_EXPERIMENT_ID = "peter_supplied"
GENERATED_EXPERIMENT_ID = "peter_generated"
GENERATED_PROBLEM_ID = "peter_thiel_generated_email_test"

DECISION_OWNER_NAME = "Beckett Zahedi"
RECIPIENT_NAME = "Peter Thiel"

#: declared evaluator (from the user's harness notes)
PRIMARY_METRIC = "call_agreed"
SECONDARY_METRICS = ("positive_reply", "no_explicit_decline")

#: simulation limits.  Four engine steps give the two-actor cast two
#: turns each: the decision owner sends, the recipient answers, and both
#: have one further turn inside the window.
MAX_STEPS = 4
BASE_SEED = 20260804
MAX_GENERATED = 3

WINDOW_DAYS = 7

#: how the compiler question is derived: a pure format over the user's own
#: desired_outcome, adding no claim of its own
QUESTION_TEMPLATE = ("Will the following outcome occur before the cutoff? "
                     "{desired_outcome}")

#: modelling scope handed to the compiler.  This is a HARNESS DECISION,
#: not a fact about any person; it is classified TEST_ASSUMPTION.
SCOPE_NOTE = (
    "Modelling scope for this simulation: model exactly two actors, the "
    "sender and the recipient named in the context above. Do not add "
    "assistants, colleagues, partners, or intermediaries. Do not assign "
    "the recipient any private beliefs, inbox habits, calendar state, "
    "screening rules, or personal preferences: nothing of that kind is "
    "known, and inventing it would make the simulation a story rather "
    "than a test.")


def load_problem_data() -> dict:
    """The user's decision problem exactly as supplied (placeholders
    intact)."""
    return json.loads(PROBLEM_PATH.read_text(encoding="utf-8"))


def resolve_window(start: datetime.datetime) -> tuple:
    """``(start_iso, cutoff_iso)``: the actual UTC run start, and exactly
    seven days later."""
    if start.tzinfo is None:
        raise ValueError("the run start must be timezone-aware UTC")
    start = start.astimezone(datetime.timezone.utc).replace(microsecond=0)
    cutoff = start + datetime.timedelta(days=WINDOW_DAYS)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.strftime(fmt), cutoff.strftime(fmt)


def build_problem_payload(*, start_iso: str, cutoff_iso: str,
                          generated: bool) -> dict:
    """The contract payload for one scenario.

    Scenario 1 is the user's file with the window resolved.  Scenario 2
    is IDENTICAL except ``problem_id``, ``candidate_interventions=[]`` and
    ``candidate_generation_permission=True`` -- exactly the delta the user
    declared.  The harness notes block is dropped from the contract
    payload (it is not a contract field) and preserved separately.
    """
    data = load_problem_data()
    data.pop("_harness_notes", None)
    if data["time_horizon"]["start"] != "FREEZE_ACTUAL_RUN_START_UTC" \
            or data["time_horizon"]["cutoff"] != \
            "FREEZE_START_PLUS_SEVEN_DAYS_UTC":
        raise AssertionError(
            "the supplied problem no longer carries the two FREEZE_ "
            "placeholders; refusing to guess which fields to resolve")
    data["time_horizon"] = {"start": start_iso, "cutoff": cutoff_iso}
    if generated:
        data["problem_id"] = GENERATED_PROBLEM_ID
        data["candidate_interventions"] = []
        data["candidate_generation_permission"] = True
    return data


def harness_notes() -> dict:
    return load_problem_data()["_harness_notes"]


def compiler_question(problem_payload: dict) -> str:
    return QUESTION_TEMPLATE.format(
        desired_outcome=problem_payload["desired_outcome"])


def compiler_context(problem_payload: dict) -> str:
    """The user's own ``relevant_context`` plus the harness scope note."""
    return problem_payload["relevant_context"] + "\n\n" + SCOPE_NOTE


def render_evidence_package(manifest: dict) -> str:
    """The compiler-visible evidence, rendered as the compiler's evidence
    package: one line per item with its classification and source, so the
    compiler can never treat an assumption as a verified fact."""
    lines = []
    for index, item in enumerate(manifest["items"], start=1):
        if not item["used_by_compiler"]:
            continue
        lines.append(
            f"[{index}] ({item['classification']}) {item['claim']}\n"
            f"    source: {item['source']} | date: {item['date']} | "
            f"available before the window opens: "
            f"{item['available_before_cutoff']}")
    header = (
        "Every item below is labelled with how well it is established. "
        "USER_SUPPLIED items are asserted by the person running this "
        "simulation and are to be treated as true inside it. "
        "PUBLICLY_VERIFIED items are public record. TEST_ASSUMPTION items "
        "are modelling decisions with no source: do not elaborate them "
        "into facts. Nothing outside this package is established; do not "
        "invent private beliefs, inbox behaviour, calendar state, or "
        "personal preferences for any actor.")
    return header + "\n\n" + "\n".join(lines)


def evidence_items(problem_payload: dict) -> list:
    """The evidence manifest entries for both Peter scenarios.

    Conservative by construction: everything about the sender and the
    project is USER_SUPPLIED (asserted by the user, not verified here);
    only stable public-record facts about the recipient are
    PUBLICLY_VERIFIED; every modelling decision is TEST_ASSUMPTION; and
    everything the simulation would need but nobody knows is UNKNOWN.
    """
    user = "user-supplied decision problem (data/peter_problem.json)"
    supplied_date = "2026-08-04 (supplied to this experiment)"
    public = "public professional record (widely published biography)"
    harness = "harness modelling decision (experiments/full_trace_validation)"
    both = [DECISION_OWNER_NAME, RECIPIENT_NAME]
    return [
        evidence_item(
            claim="Beckett Zahedi is 17 and is starting Princeton in fall "
                  "2026.",
            source=user, date=supplied_date,
            available_before_cutoff=True, classification="USER_SUPPLIED",
            who_may_know=[DECISION_OWNER_NAME], used_by_compiler=True,
            entered_context=f"private:{DECISION_OWNER_NAME}"),
        evidence_item(
            claim="Beckett Zahedi is building Aurelius, a supervisory "
                  "optimization system for GPU fleets.",
            source=user, date=supplied_date,
            available_before_cutoff=True, classification="USER_SUPPLIED",
            who_may_know=[DECISION_OWNER_NAME], used_by_compiler=True,
            entered_context=f"private:{DECISION_OWNER_NAME}"),
        evidence_item(
            claim="In replay tests over approximately 1.5 million public "
                  "production requests, Aurelius produced approximately "
                  "724% more SLA-safe goodput per dollar.",
            source=user, date=supplied_date,
            available_before_cutoff=True, classification="USER_SUPPLIED",
            who_may_know=[DECISION_OWNER_NAME], used_by_compiler=True,
            entered_context=f"private:{DECISION_OWNER_NAME}"),
        evidence_item(
            claim="The 724% result has NOT been validated in a live "
                  "production deployment and may not be represented as "
                  "production-proven.",
            source=user, date=supplied_date,
            available_before_cutoff=True, classification="USER_SUPPLIED",
            who_may_know=[DECISION_OWNER_NAME], used_by_compiler=True,
            entered_context=f"private:{DECISION_OWNER_NAME}"),
        evidence_item(
            claim="Beckett Zahedi has never contacted Peter Thiel and has "
                  "no known mutual introduction.",
            source=user, date=supplied_date,
            available_before_cutoff=True, classification="USER_SUPPLIED",
            who_may_know=both, used_by_compiler=True,
            entered_context="shared"),
        evidence_item(
            claim="Beckett Zahedi wants criticism and a short technical "
                  "conversation, not an immediate investment.",
            source=user, date=supplied_date,
            available_before_cutoff=True, classification="USER_SUPPLIED",
            who_may_know=[DECISION_OWNER_NAME], used_by_compiler=True,
            entered_context=f"private:{DECISION_OWNER_NAME}"),
        evidence_item(
            claim="Peter Thiel is a partner at Founders Fund, a cofounder "
                  "of PayPal and of Palantir, and the founder of the "
                  "Thiel Fellowship.",
            source=public, date="public record predating 2026-08-04",
            available_before_cutoff=True,
            classification="PUBLICLY_VERIFIED", who_may_know="all",
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="This simulation models exactly two actors: the sender "
                  "and the recipient. No assistant, colleague, or "
                  "intermediary exists in the modelled world.",
            source=harness, date=supplied_date,
            available_before_cutoff=True,
            classification="TEST_ASSUMPTION", who_may_know="all",
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="The recipient reads and can answer a message inside "
                  "the seven-day window (the simulation gives him turns).",
            source=harness, date=supplied_date,
            available_before_cutoff=True,
            classification="TEST_ASSUMPTION", who_may_know="all",
            used_by_compiler=False, entered_context="none"),
        evidence_item(
            claim="Peter Thiel's actual inbox behaviour, screening rules, "
                  "assistant arrangements, and calendar availability in "
                  "this window.",
            source="no source; not knowable from public biography",
            date="n/a", available_before_cutoff=False,
            classification="UNKNOWN", who_may_know=[RECIPIENT_NAME],
            used_by_compiler=False, entered_context="none"),
        evidence_item(
            claim="Peter Thiel's private opinions about GPU-fleet "
                  "scheduling, about this specific claim, and about "
                  "unsolicited cold email from teenagers.",
            source="no source; not knowable from public biography",
            date="n/a", available_before_cutoff=False,
            classification="UNKNOWN", who_may_know=[RECIPIENT_NAME],
            used_by_compiler=False, entered_context="none"),
        evidence_item(
            claim="Whether the 724% replay result would survive "
                  "independent technical scrutiny.",
            source="not established by this experiment", date="n/a",
            available_before_cutoff=False, classification="UNKNOWN",
            who_may_know="all", used_by_compiler=False,
            entered_context="none"),
        evidence_item(
            claim=("The decision window runs from "
                   f"{problem_payload['time_horizon']['start']} to "
                   f"{problem_payload['time_horizon']['cutoff']} "
                   "(the actual UTC run start plus seven days)."),
            source=harness, date=supplied_date,
            available_before_cutoff=True,
            classification="TEST_ASSUMPTION", who_may_know="all",
            used_by_compiler=True, entered_context="shared"),
    ]
