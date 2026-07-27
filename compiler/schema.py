"""The semantic contract: the only thing an LLM may produce.

Ten sections, natural-language meaning inside them, and three small fixed
vocabularies (change types, precondition types, observation types) that the
model *selects from* rather than invents.  There are no runtime identifiers,
field names, sequence numbers, payload shapes or code anywhere in here.

The contract document handed to the model is generated from this file, so
prompt and validator can never drift apart.
"""
from __future__ import annotations

from .errors import InsufficientEvidence, SemanticAmbiguity

SECTIONS = ("resolution", "scope", "participants", "starting_state",
            "communication_routes", "information", "scheduled_events",
            "processes", "action_affordances", "uncertainties",
            "terminal_producers")

#: How the world may change.  Each maps 1:1 onto a universal runtime
#: operation during lowering; none of them is scenario-specific.
CHANGE_TYPES = {
    "record_fact": "Set an objective, publicly checkable fact about the "
                   "world (a status, a flag, an outcome).",
    "create_record": "Create a formal typed record made BY someone ABOUT "
                     "something, carrying a value and the authority it was "
                     "made under -- a vote, a sign-off, an acceptance, a "
                     "filing, a confirmation. Use this whenever the answer "
                     "depends on counting or checking such records.",
    "set_quantity": "Set an objective quantity to a value.",
    "change_quantity": "Increase or decrease an objective quantity.",
    "transfer_resource": "Move an objective quantity from one holder to another.",
    "send_information": "Put information onto a communication route toward "
                        "recipients (delivery timing is the world's job).",
    "set_relationship": "Establish or remove a relationship between two parties.",
    "schedule_future_event": "Cause something to happen later, after a stated "
                             "delay with a stated basis.",
    "start_process": "Start a continuous process.",
    "stop_process": "Stop a continuous process.",
    "record_private_note": "Record something in the acting participant's own "
                           "private memory or belief (never another party's).",
}

#: What must be true for an action to be permitted.
PRECONDITION_TYPES = {
    "actor_has_role": "The acting participant holds one of the listed roles.",
    "world_fact_is": "A recorded fact currently has a given value.",
    "world_fact_absent": "A recorded fact does not exist yet.",
    "record_exists": "A typed record of some kind already exists.",
    "record_absent": "No such typed record exists yet (e.g. this party has "
                     "not already cast their vote / given their sign-off).",
    "within_time_window": "The current time is inside a stated window.",
    "action_already_completed": "An action with a given label has completed.",
    "has_noticed_information": "The acting participant has actually noticed "
                               "the information in question.",
    "has_quantity_at_least": "A holder has at least this much of a quantity.",
    "parameter_provided": "The action was given a non-empty value for this "
                          "parameter.",
    "parameter_one_of": "The parameter's value is one of the listed options.",
}

#: How the answer is observed from the finished world.
OBSERVATION_TYPES = {
    "participant_holds_belief": "A participant ended up holding a belief on a topic.",
    "participant_noticed_information": "A participant actually noticed "
                                       "information of a given tag.",
    "world_fact_is": "A recorded fact has a given value.",
    "world_fact_exists": "A recorded fact exists.",
    "quantity_reaches": "A quantity reached at least a level.",
    "quantity_measured": "Read a quantity's final value.",
    "action_was_completed": "An action with this label completed.",
    "record_was_made": "A typed record of some kind (optionally about a "
                       "particular subject, optionally by a particular party) "
                       "exists.",
    "tally_of_records": "Group typed records of one kind by their value and "
                        "apply a rule (majority, count of a value, total count).",
}

EPISTEMIC_STATUS = ("verified", "inferred", "scenario_given", "uncertain")

#: Sections whose every entry must carry a provenance block. Nothing factual
#: enters a compiled world without saying where it came from.
PROVENANCE_REQUIRED = ("participants", "starting_state", "information",
                       "communication_routes", "scheduled_events", "processes",
                       "action_affordances")
QUESTION_TYPES = ("boolean", "quantity", "choice")
TALLY_RULES = ("majority", "count_value", "count_all")


def _need(obj, key, where, kind=None):
    if key not in obj:
        raise SemanticAmbiguity(f"{where}: missing required field {key!r}",
                                {"object": obj})
    if kind is not None and not isinstance(obj[key], kind):
        raise SemanticAmbiguity(
            f"{where}: field {key!r} must be {kind.__name__}, got "
            f"{type(obj[key]).__name__}", {"object": obj})
    return obj[key]


def validate(doc: dict) -> None:
    """Structural validation of a semantic scenario.  Raises
    SemanticAmbiguity with the exact defect; never repairs anything."""
    if not isinstance(doc, dict):
        raise SemanticAmbiguity("semantic scenario must be a JSON object")
    for s in SECTIONS:
        if s not in doc:
            raise SemanticAmbiguity(f"missing required section {s!r}",
                                    {"present": sorted(doc)})

    res = doc["resolution"]
    qt = _need(res, "question_type", "resolution")
    if qt not in QUESTION_TYPES:
        raise SemanticAmbiguity(
            f"resolution.question_type must be one of {list(QUESTION_TYPES)}, "
            f"got {qt!r}")
    _need(res, "deadline", "resolution", str)
    obs = _need(res, "observations", "resolution", list)
    if not obs:
        raise SemanticAmbiguity(
            "resolution.observations is empty: nothing would be measured")
    for o in obs:
        ot = _need(o, "observation_type", "resolution.observations")
        if ot not in OBSERVATION_TYPES:
            raise SemanticAmbiguity(
                f"unknown observation_type {ot!r} "
                f"(known: {sorted(OBSERVATION_TYPES)})")
        if ot in ("tally_of_records", "record_was_made"):
            if not o.get("record_type"):
                raise SemanticAmbiguity(
                    f"{ot!r} needs a 'record_type' naming the kind of record "
                    f"being read, and it must be the SAME string used by the "
                    f"create_record change that makes them")
        if ot == "tally_of_records":
            rule = _need(o, "rule", "tally_of_records")
            if rule not in TALLY_RULES:
                raise SemanticAmbiguity(
                    f"tally rule must be one of {list(TALLY_RULES)}, got {rule!r}")

    parts = doc["participants"]
    if not isinstance(parts, list) or not parts:
        raise SemanticAmbiguity("participants must be a non-empty list")
    names = []
    for p in parts:
        n = _need(p, "name", "participants", str)
        _need(p, "kind", "participants", str)
        _need(p, "role", "participants", str)
        names.append(n.strip().lower())
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise SemanticAmbiguity(
            f"participant names are not unique: {sorted(dupes)}; every "
            f"reference would be ambiguous")

    for i, a in enumerate(doc["action_affordances"]):
        where = f"action_affordances[{i}]"
        _need(a, "label", where, str)
        _need(a, "available_to", where, dict)
        has_duration = isinstance(a.get("duration"), dict)
        has_completion = isinstance(a.get("completion_condition"), dict)
        if not has_duration and not has_completion:
            raise SemanticAmbiguity(
                f"{where} ({a.get('label')!r}): needs either a duration or a "
                f"completion_condition -- an action cannot take no time")
        if has_duration and has_completion:
            raise SemanticAmbiguity(
                f"{where} ({a.get('label')!r}): has both a duration and a "
                f"completion_condition; exactly one decides when it finishes")
        for c in a.get("preconditions", []) or []:
            ct = _need(c, "condition_type", f"{where}.preconditions")
            if ct not in PRECONDITION_TYPES:
                raise SemanticAmbiguity(
                    f"{where}: unknown condition_type {ct!r} "
                    f"(known: {sorted(PRECONDITION_TYPES)})")
        for e in a.get("consequences_on_completion", []) or []:
            _check_change(e, where)

    for i, ev in enumerate(doc["scheduled_events"]):
        where = f"scheduled_events[{i}]"
        _need(ev, "description", where, str)
        _need(ev, "time", where, str)
        _need(ev, "basis", where, str)
        for e in ev.get("effects", []) or []:
            _check_change(e, where)

    for i, pr in enumerate(doc["processes"]):
        where = f"processes[{i}]"
        _need(pr, "name", where, str)
        _need(pr, "owner", where, str)
        _need(pr, "output_quantity", where, str)
        rate = _need(pr, "rate", where, dict)
        _need(rate, "amount_per_hour", f"{where}.rate")
        st = _need(rate, "status", f"{where}.rate")
        if st not in EPISTEMIC_STATUS:
            raise SemanticAmbiguity(
                f"{where}.rate.status must be one of {list(EPISTEMIC_STATUS)}")

    if not isinstance(doc["terminal_producers"], list) or not doc["terminal_producers"]:
        raise SemanticAmbiguity(
            "terminal_producers is empty: nothing claims to produce the answer")


def _check_change(e: dict, where: str) -> None:
    ct = _need(e, "change_type", f"{where}.consequences")
    if ct == "create_record" and not e.get("record_type"):
        raise SemanticAmbiguity(
            f"{where}: create_record needs a 'record_type', and it must match "
            f"the record_type your resolution observations read")
    if ct not in CHANGE_TYPES:
        raise SemanticAmbiguity(
            f"{where}: unknown change_type {ct!r} (known: {sorted(CHANGE_TYPES)})",
            {"change": e})
    for sub in e.get("effects", []) or []:      # schedule_future_event nesting
        _check_change(sub, where)


def provenance_of(obj: dict):
    """Extract (basis, evidence_ids) from an object.

    Either encoding is accepted: an explicit ``provenance`` block, or the
    object's own ``status``/``basis`` field alongside ``evidence_ids``. A
    nested rate or duration already states its epistemic status, so demanding
    a second, redundant structure on top of it would police form rather than
    honesty. What is enforced either way is the substance: a basis is stated,
    and anything claimed verified or inferred cites the evidence for it.
    """
    p = obj.get("provenance")
    if isinstance(p, dict):
        return p.get("basis"), list(p.get("evidence_ids") or [])
    basis = obj.get("status")
    if basis is None and isinstance(obj.get("basis"), str) \
            and obj["basis"] in EPISTEMIC_STATUS:
        basis = obj["basis"]
    return basis, list(obj.get("evidence_ids") or [])


def check_provenance(doc: dict, evidence: dict) -> None:
    """Every semantic object states its epistemic basis, and anything claimed
    as verified or inferred cites the evidence that supports it.

    All violations are collected into one message so a single bounded repair
    round can fix them together."""
    known = {c["id"] for c in evidence.get("claims", [])}
    errs, cited = [], set()

    def check(obj, where, extra_nested=(), inherited=None):
        """Validate one object's epistemic basis.

        A nested object (a process's rate, an affordance's duration, a route's
        delivery_delay, a participant's attention entry) INHERITS its parent's
        provenance unless it states its own. Inheritance is explicit
        resolution, not silence: the object still has a stated basis and cited
        evidence, and the resolved value is what the lowerer records. Making
        the model restate the same citation on every nested object polices
        form rather than honesty, and in practice it simply never converges.
        """
        basis, ids = provenance_of(obj)
        if inherited is not None:
            pbasis, pids = inherited
            if basis is None:
                basis = pbasis          # no basis of its own: take the parent's
            if not ids:
                ids = pids              # own basis, parent's supporting evidence
        if basis is None:
            errs.append(f"{where}: no provenance. Add "
                        f'"provenance": {{"basis": "verified"|"inferred"|'
                        f'"scenario_given"|"uncertain", "evidence_ids": [...]}}')
        elif basis not in EPISTEMIC_STATUS:
            errs.append(f"{where}: provenance.basis is {basis!r}, must be one "
                        f"of {list(EPISTEMIC_STATUS)}")
        elif basis in ("verified", "inferred") and not ids:
            errs.append(f"{where}: basis {basis!r} cites no evidence_ids. "
                        f"Cite the claims that support it, or use "
                        f'"scenario_given" / "uncertain" if nothing does.')
        cited.update(ids)
        resolved = (basis, ids)
        for key in extra_nested:
            nested = obj.get(key)
            if isinstance(nested, dict):
                check(nested, f"{where}.{key}", inherited=resolved)
            elif isinstance(nested, list):
                for j, item in enumerate(nested):
                    if isinstance(item, dict):
                        check(item, f"{where}.{key}[{j}]", inherited=resolved)

    for i, p in enumerate(doc.get("participants") or []):
        check(p, f"participants[{p.get('name', i)!r}]", ("attention",))
    for i, s_ in enumerate(doc.get("starting_state") or []):
        check(s_, f"starting_state[{i}]")
    for i, inf in enumerate(doc.get("information") or []):
        check(inf, f"information[{i}]")
    for i, r in enumerate(doc.get("communication_routes") or []):
        check(r, f"communication_routes[{r.get('name', i)!r}]", ("delivery_delay",))
    for i, ev in enumerate(doc.get("scheduled_events") or []):
        check(ev, f"scheduled_events[{i}] ({str(ev.get('description'))[:40]!r})")
    for i, pr in enumerate(doc.get("processes") or []):
        check(pr, f"processes[{pr.get('name', i)!r}]", ("rate",))
    for i, a in enumerate(doc.get("action_affordances") or []):
        check(a, f"action_affordances[{a.get('label', i)!r}]", ("duration",))
    # the resolution rule is the compiler's reading of the question, so it is
    # scenario_given unless it claims otherwise
    res = doc.get("resolution", {})
    if provenance_of(res)[0] is None:
        res = {**res, "provenance": {"basis": "scenario_given"}}
    check(res, "resolution")

    unknown = sorted(cited - known)
    if unknown:
        errs.append(f"cites evidence ids that do not exist in the package: "
                    f"{unknown}")
    if errs:
        raise InsufficientEvidence(
            f"{len(errs)} object(s) lack honest provenance -- the compiler may "
            f"not introduce an unlabelled factual assumption:\n  - "
            + "\n  - ".join(errs),
            {"defects": errs, "repairable": True,
             "available_evidence_ids": sorted(known)})


def check_evidence_sufficiency(doc: dict, evidence: dict) -> None:
    """Every factual claim must trace to the frozen evidence package."""
    known = {c["id"] for c in evidence.get("claims", [])}
    cited, uncited = set(), []
    for p in doc["participants"]:
        ids = p.get("evidence_ids") or []
        cited.update(ids)
        if not ids:
            uncited.append(f"participants[{p['name']!r}]")
    for i, s in enumerate(doc["starting_state"]):
        ids = s.get("evidence_ids") or []
        cited.update(ids)
        if not ids and s.get("status") != "inferred":
            label = (s.get("description") or s.get("about")
                     or s.get("topic") or s.get("subject") or "?")
            uncited.append(
                f"starting_state[{i}] (kind={s.get('kind', 'fact')!r}, "
                f"subject={s.get('subject')!r}): {str(label)[:70]!r}")
    unknown = sorted(cited - known)
    if unknown:
        # citing evidence that does not exist is a claim about the world that
        # the package cannot back -- not a formatting slip
        raise InsufficientEvidence(
            f"scenario cites evidence ids that are not in the package: {unknown}",
            {"unknown_ids": unknown, "available": sorted(known)})
    if uncited:
        # every assertion must be traceable; a missing citation is mechanically
        # fixable, so it is marked repairable rather than ending the run
        raise InsufficientEvidence(
            "these assertions cite no evidence at all. Add \"evidence_ids\" "
            "listing the claim ids that support each one, or mark it "
            "\"status\": \"inferred\" if it is your own reasoning: "
            + "; ".join(uncited[:8]),
            {"uncited": uncited, "repairable": True,
             "available_evidence_ids": sorted(known)})


def contract_document() -> str:
    """The contract handed to the model, generated from this module."""
    def block(title, mapping):
        lines = [f"{title}:"]
        for k, v in sorted(mapping.items()):
            lines.append(f'  - "{k}": {v}')
        return "\n".join(lines)

    return f"""You describe WHAT IS TRUE AND WHAT CAN HAPPEN. You never write software.

Return ONE JSON object with exactly these top-level sections:
{", ".join(SECTIONS)}

Write natural language INSIDE the sections. Refer to participants, routes,
quantities and processes BY THE EXACT NAMES you gave them. Normal code will
create every identifier.

You MUST NOT produce: internal ids, field names, event ids, sequence numbers,
queue priorities, causal depth, world versions, runtime operation names, raw
effect payloads, expression trees, database references, replay records, or
code of any kind. If you find yourself writing something that looks like a
program, stop -- describe the meaning instead.

{block("CHANGE TYPES (the only ways the world may change)", CHANGE_TYPES)}

{block("PRECONDITION TYPES (the only ways to gate an action)", PRECONDITION_TYPES)}

{block("OBSERVATION TYPES (the only ways to read the answer)", OBSERVATION_TYPES)}

=== EXACT SHAPE OF EACH SECTION ===

"resolution": {{
  "provenance": {{"basis": "scenario_given", "evidence_ids": []}},
  "question_type": "boolean" | "quantity" | "choice",   // REQUIRED
  "deadline": "2026-02-19T19:00:00-06:00",              // REQUIRED, ISO + offset
  "yes_condition": "...", "no_condition": "...",        // boolean questions
  "measure_description": "...",                          // quantity questions
  "observed_from": "how the answer is read off the finished world",
  "observations": [ ... ]                                // REQUIRED, see below
}}
For "boolean", list every observation that must ALL hold for YES.
For "quantity" or "choice", give EXACTLY ONE observation.

Observation shapes (pick the observation_type, then give its fields):
  {{"observation_type": "participant_holds_belief", "participant": "<name>",
    "topic": "<short topic phrase>", "description": "..."}}
    // WARNING: this is satisfied by ANY belief on that topic, INCLUDING one the
    // participant already holds at the start. If your question is whether
    // something HAPPENS, do not use this. Use "action_was_completed" for the
    // action that produces the knowledge, or
    // "participant_noticed_information" for the message that carries it.
    // The terminal must NEVER be true before the world runs.
  {{"observation_type": "participant_noticed_information", "participant": "<name>",
    "tag": "<the same tag string you used on the send_information change>"}}
  {{"observation_type": "world_fact_is", "about": "<what the fact is about>",
    "value": <value>}}
  {{"observation_type": "world_fact_exists", "about": "<what the fact is about>"}}
  {{"observation_type": "quantity_reaches", "holder": "<participant name>",
    "quantity": "<quantity name>", "amount": <number>}}
  {{"observation_type": "quantity_measured", "holder": "<participant name>",
    "quantity": "<quantity name>"}}
  {{"observation_type": "action_was_completed", "action_label": "<affordance label>",
    "participant": "<optional name>"}}
  {{"observation_type": "record_was_made", "record_type": "<same string as the
    create_record that makes them>", "subject": "<optional>",
    "made_by": "<optional participant name>"}}
  {{"observation_type": "tally_of_records",
    "record_type": "<THE SAME STRING as the create_record change that makes
    these records -- e.g. 'vote', 'sign-off', 'acceptance'>",
    "subject": "<optional: only count records about this>",
    "rule": "majority" | "count_value" | "count_all",
    "expected_count": <how many records must exist before the tally is final>,
    "value": <required only for count_value>}}

"scope": {{"included": ["..."], "excluded": [{{"thing": "...", "reason": "..."}}]}}

"participants": [{{
  "name": "<unique display name>", "kind": "person"|"organization"|"operating system"|"population",
  "role": "<short role label; actions may be granted by role>",
  "timezone": "America/Chicago",
  "causal_relevance": "why this one can change the answer",
  "evidence_ids": ["e1"],                      // REQUIRED
  "identity_brief": "who they are, in their own terms",
  "goals": ["..."], "values": ["..."],
  "initial_emotional_state": "...", "initial_physical_state": "...",
  "initial_plan": "...",
  "relationships": [{{"to": "<other participant name>", "description": "..."}}],
  "availability": {{"timezone": "America/Chicago", "workdays": [0,1,2,3,4],
                    "open": "09:00", "close": "17:00", "holidays": ["2026-02-16"]}},
  "attention": [{{"route": "<communication route name>",
                  "status": "verified"|"inferred"|"uncertain",
                  "description": "how and when they actually look at this route",
                  "check_interval_minutes": 30,        // omit if continuously attentive
                  "bounded_by_availability": true}}]
}}]
EVERY party that acts in this world must appear in "participants" -- anyone
who SENDS INFORMATION, HOLDS A QUANTITY, RECEIVES A TRANSFER or TAKES AN
ACTION. That includes external parties who appear only once: a wire service, an
external reviewer, a courier, a manufacturer, a depot. If you name it anywhere
else in the scenario, declare it here first, with its causal_relevance and
evidence_ids. Weekday numbers are 0=Monday .. 6=Sunday.

"starting_state": [{{
  "subject": "<participant name>",
  "kind": "fact" | "quantity" | "belief" | "relationship",
  "description": "...", "status": "verified"|"inferred", "evidence_ids": ["e3"],
  // kind=quantity:
  "quantity": {{"name": "<quantity name>", "holder": "<participant name>", "amount": 0}},
  // kind=belief:
  "topic": "<short topic phrase>",
  // kind=fact:
  "about": "<what the fact is about>", "value": <value>,
  // kind=relationship:
  "other": "<participant name>", "relationship_kind": "..."
}}]

"communication_routes": [{{
  "name": "<route name>", "description": "...",
  "delivery_delay": {{"description": "...", "status": "verified"|"inferred",
                      "seconds": 60}}
}}]
EVERY route you name anywhere -- in "attention", in "information", in any
send_information change -- must be declared here first. That includes speech:
if people are in the same room, declare a route (for example "spoken in the
meeting room") with "seconds": 0, and give each person present an "attention"
entry on it with status "verified" and no check_interval_minutes, meaning they
hear it at once.

"information": [{{
  "holder": "<participant name>",           // who has it at the start
  "topic": "<short topic phrase>", "content": "the actual content",
  "basis": "how we know they have it",
  // ONLY if it was ALREADY SENT before/at the start of the window:
  "already_sent_to": ["<participant name>"], "route": "<route name>",
  "sent_time": "2026-02-16T18:40:00-06:00", "tag": "<tag string>"
}}]

"scheduled_events": [{{
  "description": "...", "time": "2026-02-18T08:00:00-06:00",
  "basis": "which evidence establishes this time", "evidence_ids": ["e5"],
  "effects": [ <change objects> ],
  "wakes": [{{"participant": "<name>", "reason": "why they are brought in now"}}]
}}]

"processes": [{{
  "name": "<process name>", "owner": "<participant name>",
  "output_quantity": "<quantity name>", "description": "...",
  "rate": {{"amount_per_hour": 25, "status": "verified"|"inferred", "note": "..."}},
  "capacity": null,
  "initially_active": false,
  "operating_periods": {{"description": "day shift", "timezone": "Europe/Berlin",
                         "workdays": [0,1,2,3,4], "start": "06:00", "end": "14:00"}}
}}]

"action_affordances": [{{
  "label": "<short unique action name, e.g. 'send the finalized study'>",
  "description": "...",
  "available_to": {{"participants": ["<name>"]}}  OR  {{"roles": ["<role>"]}},
  "parameters": [{{"name": "choice", "description": "...",
                   "allowed_values": ["approve", "reject"],   // OR
                   "fill_from": "noticed_information",        // the message being acted on
                   "tag": "<tag of the information this action responds to>"}}],
  "preconditions": [ <precondition objects> ],
  "duration": {{"description": "...", "status": "verified"|"inferred",
                "typical_minutes": 25}},
  // OR, when the action finishes on a condition rather than a clock:
  "completion_condition": {{"quantity": "<name>", "holder": "<name>", "amount": 500}},
  "consequences_on_completion": [ <change objects> ]
}}]

AN ACTION THAT RESPONDS TO A MESSAGE -- copy this pattern exactly. The
parameter, the precondition and the tag must all line up, or the action can
never be performed and compilation will be refused:
  {{"label": "send the finalized study",
    "available_to": {{"participants": ["Miguel Santos"]}},
    "parameters": [{{"name": "signoff", "description": "the sign-off he received",
                     "fill_from": "noticed_information",
                     "tag": "peer review signoff"}}],
    "preconditions": [{{"condition_type": "has_noticed_information",
                        "from_parameter": "signoff"}}],
    "duration": {{"description": "time to attach and send",
                  "status": "inferred", "typical_minutes": 20}},
    "consequences_on_completion": [
      {{"change_type": "send_information", "route": "city email",
        "tag": "finalized study", "content": "...",
        "to": {{"participants": ["Alma Reyes"]}}}}]}}
Note "tag": "peer review signoff" on the parameter is the SAME tag string used
by whatever sends that message. Every parameter you mention in a precondition
or in an effect MUST appear in "parameters".

Precondition objects:
  {{"condition_type": "actor_has_role", "roles": ["chair"]}}
  {{"condition_type": "world_fact_is", "about": "...", "value": <v>}}
  {{"condition_type": "world_fact_absent", "about": "..."}}
  {{"condition_type": "record_exists", "record_type": "vote",
    "subject": "<optional>", "made_by": "<optional participant name>"}}
  {{"condition_type": "record_absent", "record_type": "vote",
    "made_by_acting_participant": true}}     // "has not already voted"
  {{"condition_type": "within_time_window", "after": "<ISO>", "before": "<ISO>"}}
  {{"condition_type": "action_already_completed", "action_label": "<label>",
    "participant": "<optional name>"}}
  {{"condition_type": "has_noticed_information", "from_parameter": "<parameter name>"}}
  {{"condition_type": "has_quantity_at_least", "holder": "...", "quantity": "...",
    "amount": 100}}
  {{"condition_type": "parameter_provided", "parameter": "..."}}
  {{"condition_type": "parameter_one_of", "parameter": "...", "values": ["a","b"]}}

Change objects (used in "effects" and "consequences_on_completion"):
  {{"change_type": "record_fact", "about": "...", "value": <v>,
    "value_from_parameter": "choice"}}       // instead of a fixed value
  {{"change_type": "create_record",
    "record_type": "vote",                   // the kind of record; the SAME
                                             // string your tally_of_records or
                                             // record_was_made observation reads
    "subject": "<what it is about>",         // or "subject_from_parameter"
    "value": "hold",                         // or "value_from_parameter": "choice"
    "authority": "<under what authority it was made>",
    "made_by": "<participant name>"}}        // ONLY in scheduled_events; inside
                                             // an action the acting party is
                                             // the maker automatically
  {{"change_type": "set_quantity" | "change_quantity", "quantity": "...",
    "holder": "...", "amount": <n> | "delta": <n>}}
  {{"change_type": "transfer_resource", "quantity": "...", "from": "...",
    "to": "...", "amount": <n>}}
  {{"change_type": "send_information", "route": "...", "tag": "<tag string>",
    "content": "...", "description": "...",
    "to": {{"participants": ["..."]}} | {{"roles": ["..."],
            "exclude_acting_participant": true}} | {{"from_parameter": "..."}},
    "from": "<name>"}}                       // "from" only in scheduled_events
  {{"change_type": "set_relationship", "from": "...", "to": "...",
    "relationship_kind": "...", "description": "..."}}
  {{"change_type": "schedule_future_event", "description": "...",
    "delay": {{"hours": 3, "status": "inferred", "description": "why this long"}},
    "effects": [ <change objects> ]}}
  {{"change_type": "start_process" | "stop_process", "process": "<process name>"}}
  {{"change_type": "record_private_note", "topic": "<topic>", "content": "...",
    "basis": "...", "participant": "<name>"}}   // "participant" only in scheduled_events

=== HONESTY RULES: PROVENANCE ON EVERY OBJECT ===
EVERY participant, starting_state entry, information entry, communication
route, scheduled event, process and action affordance MUST carry:

  "provenance": {{"basis": "verified" | "inferred" | "scenario_given" | "uncertain",
                 "evidence_ids": ["e3", "e7"],
                 "note": "which claim supports this, or why you inferred it"}}

  - "verified"       the evidence package states it. MUST cite evidence_ids.
  - "inferred"       your reasoning from the evidence. MUST cite the claims
                     you reasoned FROM, and say so in the note.
  - "scenario_given" stipulated by the question itself (the deadline, what
                     counts as the answer). No evidence_ids needed.
  - "uncertain"      genuinely unknown. No evidence_ids needed.

Nested objects that carry a number of their own -- a route's delivery_delay, a
process's rate, an affordance's duration, a participant's attention entry --
INHERIT their parent's provenance automatically. You only need to give one its
own "provenance" block (or its own "status" + "evidence_ids") when its basis
genuinely DIFFERS from its parent's -- for example a participant whose role is
verified but whose email-checking habit is only inferred. Otherwise say
nothing and the parent's basis applies.

You may not introduce an unlabelled factual assumption anywhere. NEVER invent
a convenient number and label it verified. If noticing behaviour is uncertain,
say "uncertain": the message will then be delivered and remain unnoticed, and
the answer may honestly come back "unresolved" -- which is a correct result,
not a failure.

=== IT MUST ACTUALLY BE ABLE TO HAPPEN ===
Trace your own answer before you finish:
- Something must be scheduled at or before the deadline, or nothing happens.
- The terminal must be FALSE at the start and become true only through the
  trajectory. If your observations are already satisfied by "starting_state",
  the simulation decides nothing and the world will be refused.
- Every observation in "resolution" must be produced by some effect, process,
  starting quantity or affordance you actually declared.
- If the answer depends on someone NOTICING something, that person needs an
  attention rule on the route it arrives by.
- If an action is meant to respond to a message, give it a parameter with
  "fill_from": "noticed_information" and the tag of that message, and a
  "has_noticed_information" precondition.
- "terminal_producers" must name the real chain that produces each part of
  the answer.

Include ONLY what can materially change the answer. Everything you leave out
should appear in scope.excluded with the reason it cannot matter.

COUNTING THINGS -- copy this pattern. The record_type strings MUST match:
  affordance "cast a vote" -> consequences_on_completion:
     [{{"change_type": "create_record", "record_type": "vote",
        "subject_from_parameter": "motion", "value_from_parameter": "choice",
        "authority": "voting member under the charter"}}]
  its preconditions:
     [{{"condition_type": "record_absent", "record_type": "vote",
        "made_by_acting_participant": true}}]
  resolution.observations:
     [{{"observation_type": "tally_of_records", "record_type": "vote",
        "rule": "majority", "expected_count": 3}}]

=== CHECK BEFORE YOU RETURN ===
1. All eleven sections present? (empty lists are fine where nothing applies,
   but resolution.observations and terminal_producers must NOT be empty)
2. resolution.question_type set, deadline an ISO time with an offset?
3. Every party you named anywhere declared in participants?
4. Every route you named declared in communication_routes?
5. Every quantity you named introduced by a starting_state entry or a process?
6. Every parameter used in a precondition or effect declared in that action's
   "parameters"?
6b. Does every create_record have a "record_type", and does every
   tally_of_records / record_was_made read that SAME record_type string?
7. A "provenance" block on every participant, starting_state entry,
   information entry, route, scheduled event, process and affordance -- and on
   every nested rate, duration, delivery_delay and attention entry?
8. Is the terminal FALSE at the start, and produced only by the trajectory?
9. Something scheduled at or before the deadline?
10. One complete JSON object, nothing else, not truncated?
"""
