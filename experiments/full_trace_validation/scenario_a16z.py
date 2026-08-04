"""Frozen scenario data for the a16z historical hiring counterfactual.

Experiment-only.  The decision problem is the user's own file, copied
VERBATIM into ``data/a16z_problem.json`` and read from there -- there are
no placeholders to resolve: the window is fixed by the contract at
2025-07-01T16:00:00Z .. 2025-07-10T12:00:00Z.

Nothing in this module authors simulation content.  It declares:

- how the compiler question is derived from the user's own
  ``desired_outcome`` (a pure format, no new claims);
- the harness scope note handed to the compiler as context (classified
  ``TEST_ASSUMPTION``: it is a modelling decision, not a fact about
  anyone);
- the evidence items, each classified conservatively;
- the declared evaluator, the code-owned salary mapping, the simulation
  limits, the base seed, and the mechanical acceptance criteria a compile
  attempt must satisfy.

Why nothing here is ``PUBLICLY_VERIFIED``
-----------------------------------------
The evidence rules reserve ``PUBLICLY_VERIFIED`` for a claim a dated
public source published BEFORE the window opens.  This harness ran in
August 2026 and could not consult a source without risking the import of
post-cutoff material -- which is exactly what this scenario forbids.  So
no claim here is upgraded: every biography claim is carried at the
strictly weaker ``USER_SUPPLIED`` label, and the report says so.  That is
a limitation of the run, deliberately visible in the classification
counts rather than hidden behind a confident label.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .cutoff import CUTOFF_DATE, WINDOW_END
from .evidence import evidence_item

DATA_DIR = Path(__file__).resolve().parent / "data"
PROBLEM_PATH = DATA_DIR / "a16z_problem.json"

EXPERIMENT_ID = "a16z_richard_historical"
COMPILE_EXPERIMENT_ID = "a16z_compile"

#: the five declared actors, in the order the contract names them.  The
#: compiled cast must be exactly this SET; the compiled ORDER is whatever
#: the compiler produced and becomes the engine's fixed acting order.
DECISION_OWNER_NAME = "New Media Hiring Lead"
STRATEGY_PARTNER_NAME = "New Media Strategy Partner"
CREATIVE_LEAD_NAME = "Creative Production Lead"
COMP_PARTNER_NAME = "People and Compensation Partner"
SUBJECT_NAME = "Richard Zheng"

REQUIRED_CAST = (DECISION_OWNER_NAME, STRATEGY_PARTNER_NAME,
                 CREATIVE_LEAD_NAME, COMP_PARTNER_NAME, SUBJECT_NAME)

#: declared evaluator (from the user's harness notes)
PRIMARY_METRIC = "valid_offer_accepted"
SECONDARY_METRICS = ("salary_savings_vs_300k",)

#: engine step budget: three full rounds of the five-actor cast.  Under
#: the fixed acting order an authorized offer cannot precede the subject's
#: turn inside a single round, so one round could not express the declared
#: success path at all; three is the smallest budget that gives the
#: authority chain room without becoming open-ended.  Declared BEFORE the
#: run and frozen.
MAX_STEPS = 15
BASE_SEED = 20260804

#: how many byte-identical compile attempts are permitted before the run
#: is refused.  Resampling is disclosed, never repair: every attempt's
#: artifacts and every attempt's live calls are recorded and committed,
#: and the report publishes the cast of each attempt.
MAX_COMPILE_ATTEMPTS = 3

#: how the compiler question is derived: a pure format over the user's own
#: desired_outcome, adding no claim of its own
QUESTION_TEMPLATE = ("Will the following outcome occur before the cutoff? "
                     "{desired_outcome}")

#: modelling scope handed to the compiler.  A HARNESS DECISION, not a fact
#: about any person or firm; classified TEST_ASSUMPTION.
SCOPE_NOTE = (
    "Modelling scope for this simulation (a declared test setup, not a "
    "claim about the real world):\n"
    "1. This is a HISTORICAL COUNTERFACTUAL frozen on 2025-07-01. Your "
    "knowledge horizon is that instant: use only information that already "
    "existed as of 2025-07-01. Do not use, reference, or rely on anything "
    "published, announced, decided, or reported after 2025-07-01, "
    "including any later employment, later work, later campaign, or later "
    "announcement by any party. This is a knowledge horizon, NOT a "
    "deadline for the decision: the decision window is the simulation "
    "window given above.\n"
    "2. Model EXACTLY these five actors and no others, using exactly "
    "these names: New Media Hiring Lead; New Media Strategy Partner; "
    "Creative Production Lead; People and Compensation Partner; Richard "
    "Zheng. The first four are role-based stand-ins supplied by this "
    "test because the real committee is not public; they are given to "
    "you, not invented by you. Do not add, remove, rename, merge, or "
    "split actors. Do not add assistants, recruiters, lawyers, "
    "executives, board members, or intermediaries.\n"
    "3. Authority: the New Media Hiring Lead owns the hiring action; the "
    "People and Compensation Partner owns compensation approval; the New "
    "Media Strategy Partner and the Creative Production Lead advise and "
    "cannot issue an offer; Richard Zheng alone decides whether to "
    "accept, reject, counter, or delay.\n"
    "4. Do not invent a16z salary bands, internal budgets, compensation "
    "ceilings, private opinions, or hiring deliberations, and do not "
    "state any as fact. Nothing about anyone's private compensation, "
    "internal opinions, or exact internal authority is known.\n"
    "5. No starting event may state or imply that an offer has been "
    "prepared, authorized, issued, discussed with the candidate, "
    "accepted, rejected, or countered. The offer, if any, is what the "
    "simulation is for.\n"
    "6. Treat every claim in the evidence package at exactly the "
    "confidence its label gives it; do not elaborate an assumption into "
    "a fact.")

#: the code-owned salary mapping, lifted from the user's harness notes and
#: re-declared here so the metric can never come from model text
SALARY_MAPPING_KEYS = ("no_offer", "offer_100k", "offer_150k", "offer_200k",
                       "offer_250k", "offer_300k")

#: the salary figure each offer branch declares (used ONLY to prove the
#: branch inputs differ in nothing else; never parsed from model output)
DECLARED_SALARY_TOKEN = {
    "no_offer": None,
    "offer_100k": "$100,000",
    "offer_150k": "$150,000",
    "offer_200k": "$200,000",
    "offer_250k": "$250,000",
    "offer_300k": "$300,000",
}

_SALARY_TOKEN_RE = re.compile(r"\$\s?\d{1,3}(?:,\d{3})+")


def load_problem_data() -> dict:
    """The user's decision problem exactly as supplied."""
    return json.loads(PROBLEM_PATH.read_text(encoding="utf-8"))


def harness_notes() -> dict:
    return load_problem_data()["_harness_notes"]


def salary_savings_mapping() -> dict:
    """The code-owned ``{candidate_key: savings}`` mapping, read from the
    user's own harness notes (never re-typed here)."""
    mapping = dict(harness_notes()["code_owned_salary_mapping"])
    if tuple(mapping) != SALARY_MAPPING_KEYS:
        raise AssertionError(
            "the supplied salary mapping keys changed: expected "
            f"{list(SALARY_MAPPING_KEYS)}, found {list(mapping)}")
    return mapping


def build_problem_payload() -> dict:
    """The contract payload: the user's file with the harness notes block
    removed (it is not a contract field) and nothing else touched."""
    data = load_problem_data()
    data.pop("_harness_notes", None)
    horizon = data["time_horizon"]
    if horizon["start"] != "2025-07-01T16:00:00Z" \
            or horizon["cutoff"] != "2025-07-10T12:00:00Z":
        raise AssertionError(
            "the supplied problem's frozen window changed; refusing to "
            f"guess which window was meant: {horizon}")
    if len(data["candidate_interventions"]) != len(SALARY_MAPPING_KEYS):
        raise AssertionError(
            f"expected {len(SALARY_MAPPING_KEYS)} declared candidates, "
            f"found {len(data['candidate_interventions'])}")
    return data


def candidate_key_by_index() -> dict:
    """``{declaration index: mapping key}``, cross-checked against the
    frozen candidate text.

    The route names candidates ``user_NNN`` in declaration order, so the
    binding is positional; this function REFUSES a binding whose declared
    salary token does not appear in that position's candidate text, which
    is what keeps the metric code-owned rather than text-derived.
    """
    payload = build_problem_payload()
    actions = payload["candidate_interventions"]
    binding: dict = {}
    for index, key in enumerate(SALARY_MAPPING_KEYS):
        action = actions[index]
        token = DECLARED_SALARY_TOKEN[key]
        found = _SALARY_TOKEN_RE.findall(action)
        if token is None:
            if found:
                raise AssertionError(
                    f"candidate {index} ({key}) is the no-offer baseline "
                    f"but carries salary token(s) {found}")
        else:
            if [item.replace(" ", "") for item in found] != [token]:
                raise AssertionError(
                    f"candidate {index} ({key}) must declare exactly "
                    f"{token!r}; its text carries {found}")
        binding[index] = key
    return binding


def savings_by_candidate_id(candidate_ids) -> dict:
    """``{candidate_id: savings}`` for the run's candidates, in the order
    the route produced them.  Code-owned end to end: the value comes from
    the user's mapping via the declaration index, never from model text.
    """
    ids = list(candidate_ids)
    keys = candidate_key_by_index()
    if len(ids) != len(keys):
        raise AssertionError(
            f"expected {len(keys)} candidates, the run produced {len(ids)}: "
            f"{ids}")
    mapping = salary_savings_mapping()
    return {candidate_id: float(mapping[keys[index]])
            for index, candidate_id in enumerate(ids)}


def candidate_key_by_id(candidate_ids) -> dict:
    ids = list(candidate_ids)
    keys = candidate_key_by_index()
    return {candidate_id: keys[index]
            for index, candidate_id in enumerate(ids)}


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
            f"available on or before the "
            f"{CUTOFF_DATE.isoformat()} cutoff: "
            f"{item['available_before_cutoff']}")
    header = (
        "HISTORICAL EVIDENCE PACKAGE, frozen at "
        f"{CUTOFF_DATE.isoformat()}. Every item below is labelled with "
        "how well it is established. USER_SUPPLIED items are asserted by "
        "the person running this simulation and are to be treated as true "
        "inside it; they are NOT independently verified. TEST_ASSUMPTION "
        "items are modelling decisions with no source: do not elaborate "
        "them into facts. UNKNOWN items are recorded so their absence is "
        "visible; do not fill them in. There are no PUBLICLY_VERIFIED "
        "items in this package, because this run did not consult a dated "
        "public source. Nothing outside this package is established: do "
        "not invent salary bands, budgets, compensation ceilings, private "
        "opinions, internal deliberations, or decision authority, and do "
        "not use anything published after "
        f"{CUTOFF_DATE.isoformat()}.")
    return header + "\n\n" + "\n".join(lines)


def evidence_items() -> list:
    """The evidence manifest entries for the a16z counterfactual.

    Conservative by construction: every claim about a real person or firm
    is USER_SUPPLIED (asserted by the user of this experiment, verified by
    nobody here); every modelling decision is TEST_ASSUMPTION; and
    everything the simulation would need but nobody knows -- private
    compensation, internal budgets, salary bands, internal opinions, the
    real committee, the real authority chain -- is UNKNOWN.
    """
    user = "user-supplied decision problem (data/a16z_problem.json)"
    supplied = ("asserted by the user of this experiment as known at the "
                "2025-07-01 boundary; not independently verified here")
    harness = ("harness modelling decision "
               "(experiments/full_trace_validation/scenario_a16z.py)")
    none_known = "no source; not knowable from public biography"
    everyone = "all"
    return [
        evidence_item(
            claim="Richard Zheng is a recent high-school graduate.",
            source=user, date=supplied, available_before_cutoff=True,
            classification="USER_SUPPLIED", who_may_know=everyone,
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="Richard Zheng has been Head of Marketing at Aviato.",
            source=user, date=supplied, available_before_cutoff=True,
            classification="USER_SUPPLIED", who_may_know=everyone,
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="Richard Zheng is the founder of UNHRD.",
            source=user, date=supplied, available_before_cutoff=True,
            classification="USER_SUPPLIED", who_may_know=everyone,
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="Richard Zheng is an independent creative and media "
                  "operator.",
            source=user, date=supplied, available_before_cutoff=True,
            classification="USER_SUPPLIED", who_may_know=everyone,
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="Richard Zheng has worked on projects involving TIME, "
                  "the United Nations, Forbes, Fidelity, Cluely, "
                  "Browserbase, Z Fellows, Axiom Space, and SpaceX.",
            source=user, date=supplied, available_before_cutoff=True,
            classification="USER_SUPPLIED", who_may_know=everyone,
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="UNVERIFIED USER CLAIM, label preserved: Richard Zheng "
                  "previously earned approximately $100,000 per video "
                  "shoot and managed eight shoots simultaneously. This is "
                  "reported project revenue and must NOT be treated as "
                  "equivalent to an annual salary or to personal income.",
            source=user + " (explicitly flagged unverified by the user)",
            date=supplied, available_before_cutoff=True,
            classification="USER_SUPPLIED", who_may_know=[SUBJECT_NAME],
            used_by_compiler=True,
            entered_context=f"private:{SUBJECT_NAME}"),
        evidence_item(
            claim="a16z New Media is intended to provide in-house "
                  "creative production, owned-channel distribution, "
                  "launch strategy, and media support for portfolio "
                  "companies.",
            source=user + "; the user attributes this to public evidence, "
                          "which this harness did not independently check",
            date=supplied, available_before_cutoff=True,
            classification="USER_SUPPLIED", who_may_know=everyone,
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="This simulation models exactly five actors: New Media "
                  "Hiring Lead; New Media Strategy Partner; Creative "
                  "Production Lead; People and Compensation Partner; "
                  "Richard Zheng. The first four are ROLE-BASED "
                  "STAND-INS supplied by this test because the real "
                  "hiring committee is not public. They are not real "
                  "people and no claim is made that a16z has such roles.",
            source=harness, date="declared before the run",
            available_before_cutoff=True,
            classification="TEST_ASSUMPTION", who_may_know=everyone,
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="Declared authority model: the New Media Hiring Lead "
                  "owns the hiring action; the People and Compensation "
                  "Partner owns compensation approval; the strategy and "
                  "creative actors advise only; Richard Zheng alone "
                  "decides whether to accept, reject, counter, or delay. "
                  "This is a test setup, not a description of a16z.",
            source=harness, date="declared before the run",
            available_before_cutoff=True,
            classification="TEST_ASSUMPTION", who_may_know=everyone,
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="The role package -- title, role scope, reporting line, "
                  "benefits, equity treatment, creative autonomy, "
                  "resources and start expectations -- is held FIXED and "
                  "unspecified across every branch; only annual base "
                  "salary varies.",
            source=harness, date="declared before the run",
            available_before_cutoff=True,
            classification="TEST_ASSUMPTION", who_may_know=everyone,
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="The decision window runs from 2025-07-01T16:00:00Z to "
                  "2025-07-10T12:00:00Z, and every actor is available to "
                  "act inside it (the simulation gives each one turns).",
            source=harness, date="declared before the run",
            available_before_cutoff=True,
            classification="TEST_ASSUMPTION", who_may_know=everyone,
            used_by_compiler=True, entered_context="shared"),
        evidence_item(
            claim="Any internal compensation ceiling, budget limit, or "
                  "salary band that appears anywhere in this run is a "
                  "TEST ASSUMPTION authored inside the simulation, never "
                  "a historical fact about a16z.",
            source=harness, date="declared before the run",
            available_before_cutoff=True,
            classification="TEST_ASSUMPTION", who_may_know=everyone,
            used_by_compiler=False, entered_context="none"),
        evidence_item(
            claim="The real a16z New Media hiring committee, its "
                  "membership, its internal authority chain, and its "
                  "decision process.",
            source=none_known, date="n/a", available_before_cutoff=False,
            classification="UNKNOWN", who_may_know=everyone,
            used_by_compiler=False, entered_context="none"),
        evidence_item(
            claim="a16z's actual salary bands, compensation budget, and "
                  "any internal compensation ceiling for this role.",
            source=none_known, date="n/a", available_before_cutoff=False,
            classification="UNKNOWN", who_may_know=everyone,
            used_by_compiler=False, entered_context="none"),
        evidence_item(
            claim="Richard Zheng's actual compensation expectations, "
                  "reservation price, competing options, financial "
                  "position, and private preferences in this window.",
            source=none_known, date="n/a", available_before_cutoff=False,
            classification="UNKNOWN", who_may_know=[SUBJECT_NAME],
            used_by_compiler=False, entered_context="none"),
        evidence_item(
            claim="The private opinions of any real person at a16z about "
                  "Richard Zheng, and any real internal deliberation "
                  "about hiring him.",
            source=none_known, date="n/a", available_before_cutoff=False,
            classification="UNKNOWN", who_may_know=everyone,
            used_by_compiler=False, entered_context="none"),
        evidence_item(
            claim="Whether any employment offer was in fact made to "
                  "Richard Zheng on or before 2025-07-01, and on what "
                  "terms.",
            source=none_known, date="n/a", available_before_cutoff=False,
            classification="UNKNOWN", who_may_know=everyone,
            used_by_compiler=False, entered_context="none"),
    ]


#: a negation immediately governing a matched act phrase.  "no offer has
#: been made" is the OPPOSITE of a prewritten outcome, and an acceptance
#: gate that rejected it would be rejecting exactly the scene the run
#: needs.  Applied to the text preceding a match.
NEGATION_BEFORE_RE = r"\b(?:no|not|never|nor|without|neither)\s+" \
                     r"(?:\w+[\s,]+){0,3}$"

#: patterns whose presence in a compiled STARTING EVENT means the compiler
#: prewrote part of the outcome (offer prepared / issued / accepted).
#: Applied mechanically to the compile acceptance check, with the negation
#: guard above.
PREWRITTEN_OUTCOME_PATTERNS = (
    r"\boffer\s+(?:has\s+been|was|is)\s+(?:made|issued|extended|sent|"
    r"prepared|approved|authoriz\w+|accepted|declined|rejected)",
    r"\b(?:has|have|had)\s+(?:already\s+)?(?:made|issued|extended|sent)\b"
    r"[^.!?]{0,40}\boffer\b",
    r"\b(?:accepts?|accepted|rejects?|rejected|declines?|declined|"
    r"counters?|countered)\b[^.!?]{0,40}\b(?:the\s+)?offer\b",
    r"\boffer\s+letter\s+(?:has\s+been|was|is)\s+(?:sent|signed|issued)",
    r"\bcompensation\s+(?:has\s+been|was)\s+approved\b",
    r"\bsalary\s+of\s+\$",
)


def compile_acceptance_criteria() -> dict:
    """The mechanical criteria one compile attempt must satisfy, declared
    BEFORE the first attempt and frozen into the manifest."""
    return {
        "required_cast_exact_set": list(REQUIRED_CAST),
        "cast_order": ("not constrained; whatever the compiler declares "
                       "becomes the engine's fixed acting order and is "
                       "published"),
        "no_prewritten_outcome_in_starting_events": list(
            PREWRITTEN_OUTCOME_PATTERNS),
        "negation_guard": NEGATION_BEFORE_RE,
        "historical_cutoff_clean": {
            "cutoff": CUTOFF_DATE.isoformat(),
            "window_end": WINDOW_END.isoformat()},
        "max_attempts": MAX_COMPILE_ATTEMPTS,
        "resampling_policy": (
            "attempts use BYTE-IDENTICAL inputs; every attempt's compiler "
            "artifacts and every attempt's live calls are recorded and "
            "committed; the first attempt meeting all criteria is used "
            "and the cast of every attempt is published. Resampling is "
            "disclosed, never repair: no compiler output is edited."),
    }
