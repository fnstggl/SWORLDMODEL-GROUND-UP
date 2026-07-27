"""The closed capability menu: the compiler-facing universal mechanics.

This module is the SINGLE SOURCE OF TRUTH for what a compiled world can be
made of.  The translator prompt is rendered from the same tables that
validate translator output, so the menu the LLM sees and the schema the code
enforces can never drift apart.

The menu sits at the lifecycle level -- perform an action, move information,
change a quantity, transfer possession, run a process, create a typed
record, change a relationship, schedule an event, restrict by authority.
It never contains scenario nouns or verbs; scenario meaning is carried in
the *data* the translator fills in (names, keys, record types, templates).
The hidden kernel operations underneath are not exposed here at all:
deterministic assembly expands these capabilities into kernel ops.

Everything here is structural validation (types, enums, required fields,
template hygiene).  Reference resolution (does this name exist?) belongs to
the graph builder; realism judgement belongs to the reviewers.
"""
from __future__ import annotations

import re

#: Claim labels for real-world assertions.  `uncertain` may never be used
#: where a concrete number is consumed -- uncertainty does not become fact.
PROVENANCE_LABELS = ("verified", "question_given", "inferred",
                     "model_memory_unverified", "uncertain")
CONCRETE_LABELS = ("verified", "question_given", "inferred",
                   "model_memory_unverified")

#: Hard bounds: the smallest faithful world, never a sprawling one.
LIMITS = {"participants": 8, "aggregates": 12, "channels": 8, "actions": 14,
          "horizon_days": 120, "genesis_events": 400}

_TEMPLATE_RE = re.compile(r"\{([a-zA-Z_.][a-zA-Z0-9_.]*)\}")
_HHMM_RE = re.compile(r"^\d{2}:\d{2}$")
_LOCAL_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

# ---------------------------------------------------------------------------
# effect macros: lifecycle compositions the translator may use in effects
# ---------------------------------------------------------------------------

EFFECT_MACROS = {
    "send_information": {
        "purpose": ("move information through a channel: created -> sent -> "
                    "delivered; the recipient may then notice and read it "
                    "(never guaranteed)"),
        "fields": {
            "to": {"type": "recipients", "required": True,
                   "note": "list of participant names, or {\"roles\": [...]}"},
            "channel": {"type": "name", "required": True},
            "content_template": {"type": "str", "required": True,
                                 "note": "the message text; inside an action "
                                         "it may use {params.x}"},
            "info_type": {"type": "str",
                          "note": "typed label for this information, e.g. a "
                                  "short slug; lets the terminal and other "
                                  "checks match it mechanically"},
            "author": {"type": "name",
                       "note": "ONLY inside scheduled external events: who "
                               "the information is from"},
        }},
    "create_record": {
        "purpose": ("create a typed record (a decision, approval, filing, "
                    "result).  Preserves who recorded it, what it concerned, "
                    "and the choice; authority comes from the action's "
                    "allowed_roles"),
        "fields": {
            "record_type": {"type": "slug", "required": True},
            "subject": {"type": "slug", "required": True},
            "choice_template": {"type": "str",
                                "note": "the recorded choice; may use "
                                        "{params.x} inside an action"},
            "value": {"type": "any", "note": "literal value if no template"},
            "per_actor": {"type": "bool",
                          "note": "true (default): one record per acting "
                                  "participant; false: a single shared record"},
            "once": {"type": "bool",
                     "note": "true (default): the same record may not be "
                             "created twice"},
        }},
    "adjust_quantity": {
        "purpose": "increase or decrease a quantity held somewhere",
        "fields": {
            "holder": {"type": "name", "required": True},
            "resource": {"type": "slug", "required": True},
            "delta_template": {"type": "num_or_template", "required": True},
        }},
    "transfer_possession": {
        "purpose": ("move a quantity from one holder to another; the source "
                    "loses exactly what the destination gains"),
        "fields": {
            "from_holder": {"type": "name", "required": True},
            "to_holder": {"type": "name", "required": True},
            "resource": {"type": "slug", "required": True},
            "amount_template": {"type": "num_or_template", "required": True},
        }},
    "set_process_active": {
        "purpose": "start or stop an ongoing process",
        "fields": {
            "process": {"type": "name", "required": True},
            "active": {"type": "bool", "required": True},
        }},
    "set_relationship": {
        "purpose": "establish, change, or describe a relationship",
        "fields": {
            "src": {"type": "name_or_actor", "required": True},
            "kind": {"type": "slug", "required": True},
            "dst": {"type": "name_or_actor", "required": True},
            "value": {"type": "str", "required": True},
        }},
    "schedule_followup": {
        "purpose": ("schedule further effects after a labeled real-world "
                    "delay (transit, processing, publication lag)"),
        "fields": {
            "delay_hours": {"type": "num", "required": True, "concrete": True},
            "provenance": {"type": "label", "required": True, "concrete": True},
            "note": {"type": "str", "required": True},
            "effects": {"type": "effects", "required": True,
                        "note": "nested effects (one level deep at most)"},
        }},
}

#: Precondition kinds for define_action.requires.
REQUIRE_KINDS = {
    "fact_equals": ("key", "value"),
    "fact_absent": ("key",),
    "noticed_information": ("param",),
    "resource_at_least": ("holder", "resource", "amount"),
}

#: Terminal condition checks (participant/holder/author are NAMES here; the
#: builder resolves them to internal ids).
TERMINAL_CHECKS = {
    "fact_equals": ("key", "value"),
    "fact_exists": ("key",),
    "resource_at_least": ("holder", "resource", "amount"),
    "information_noticed": ("participant",),
    "information_sent": ("sender",),
    "action_completed": ("verb",),
    "record_exists": ("record_type", "subject"),
    "count_records_at_least": ("record_type", "subject", "amount"),
}

# ---------------------------------------------------------------------------
# the capability table
# ---------------------------------------------------------------------------

CAPABILITIES = {
    "add_participant": {
        "purpose": ("a real person (or person-like deciding unit) who makes "
                    "decisions during the simulation"),
        "fields": {
            "name": {"type": "str", "required": True},
            "aliases": {"type": "str_list"},
            "role": {"type": "str", "required": True,
                     "note": "their real position; used for authority checks"},
            "tz": {"type": "tz", "note": "IANA zone, e.g. America/Chicago"},
            "goals": {"type": "str_list"},
            "traits": {"type": "str_list",
                       "note": "dispositions that shape decisions"},
            "plan": {"type": "str", "note": "what they are currently doing"},
            "why_needed": {"type": "str", "required": True},
        }},
    "add_aggregate": {
        "purpose": ("an organization, population, system, place, or object "
                    "that matters but does not deliberate turn by turn; its "
                    "behavior is carried by quantities, processes, and "
                    "scheduled events"),
        "fields": {
            "name": {"type": "str", "required": True},
            "aliases": {"type": "str_list"},
            "kind": {"type": "str", "required": True,
                     "note": "e.g. organization / population / system / place"},
            "note": {"type": "str", "required": True},
        }},
    "add_channel": {
        "purpose": "a transmission medium information can move through",
        "fields": {
            "name": {"type": "slug", "required": True},
            "latency_seconds": {"type": "num", "required": True,
                                "concrete": True},
            "provenance": {"type": "label", "required": True, "concrete": True},
            "note": {"type": "str", "required": True},
            "open_to_all": {"type": "bool",
                            "note": "true: every participant can reach every "
                                    "other on it; false (default): only "
                                    "declared add_channel_access routes exist"},
        }},
    "add_channel_access": {
        "purpose": ("a real route: the sender can actually reach the "
                    "recipient on this channel (has the address / number / "
                    "access)"),
        "fields": {
            "sender": {"type": "name", "required": True},
            "recipient": {"type": "name", "required": True},
            "channel": {"type": "name", "required": True},
            "provenance": {"type": "label", "required": True},
            "note": {"type": "str", "required": True},
        }},
    "add_attention": {
        "purpose": ("when a participant actually looks at a channel.  If "
                    "the real pattern is unknown, use mode none_known: "
                    "information will remain delivered-but-unnoticed rather "
                    "than the world inventing attention"),
        "fields": {
            "participant": {"type": "name", "required": True},
            "channel": {"type": "name", "required": True},
            "mode": {"type": "str", "required": True,
                     "one_of": ["continuous", "periodic", "none_known"]},
            "tz": {"type": "tz"},
            "workdays": {"type": "weekdays",
                         "note": "0=Mon .. 6=Sun; default Mon-Fri"},
            "open_time": {"type": "hhmm"},
            "close_time": {"type": "hhmm"},
            "check_every_minutes": {"type": "num", "concrete": True},
            "provenance": {"type": "label", "required": True},
            "note": {"type": "str", "required": True},
        }},
    "add_fact": {
        "purpose": "something already true in the world at the start",
        "fields": {
            "key": {"type": "slug", "required": True},
            "value": {"type": "any", "required": True},
            "provenance": {"type": "label", "required": True},
            "note": {"type": "str", "required": True},
        }},
    "add_resource": {
        "purpose": "a quantity held by a participant or aggregate at start",
        "fields": {
            "holder": {"type": "name", "required": True},
            "resource": {"type": "slug", "required": True},
            "amount": {"type": "num", "required": True},
            "unit_note": {"type": "str", "required": True},
            "provenance": {"type": "label", "required": True},
            "note": {"type": "str"},
        }},
    "add_process": {
        "purpose": ("an ongoing real-world process that changes a quantity "
                    "at a rate over elapsed time (production, spending, "
                    "accumulation, decay)"),
        "fields": {
            "name": {"type": "slug", "required": True},
            "owner": {"type": "name", "required": True},
            "resource": {"type": "slug", "required": True},
            "rate_per_hour": {"type": "num", "required": True,
                              "concrete": True},
            "capacity": {"type": "num"},
            "active_at_start": {"type": "bool", "required": True},
            "provenance": {"type": "label", "required": True, "concrete": True},
            "note": {"type": "str", "required": True},
        }},
    "add_operating_window": {
        "purpose": ("the schedule during which a process runs (shifts, "
                    "opening hours); outside the window it is inactive"),
        "fields": {
            "process": {"type": "name", "required": True},
            "tz": {"type": "tz", "required": True},
            "workdays": {"type": "weekdays", "required": True},
            "start_time": {"type": "hhmm", "required": True},
            "end_time": {"type": "hhmm", "required": True},
            "provenance": {"type": "label", "required": True, "concrete": True},
            "note": {"type": "str", "required": True},
        }},
    "add_threshold_watch": {
        "purpose": ("wake a participant when a quantity reaches a level "
                    "(they are watching it)"),
        "fields": {
            "holder": {"type": "name", "required": True},
            "resource": {"type": "slug", "required": True},
            "level": {"type": "num", "required": True},
            "wake_participant": {"type": "name", "required": True},
            "provenance": {"type": "label", "required": True},
            "note": {"type": "str", "required": True},
        }},
    "add_relationship": {
        "purpose": "an existing relationship between two named things",
        "fields": {
            "src": {"type": "name", "required": True},
            "kind": {"type": "slug", "required": True},
            "dst": {"type": "name", "required": True},
            "note": {"type": "str", "required": True},
        }},
    "add_belief": {
        "purpose": ("something one participant privately knows or believes "
                    "at the start (their knowledge boundary)"),
        "fields": {
            "participant": {"type": "name", "required": True},
            "topic": {"type": "slug", "required": True},
            "statement": {"type": "str", "required": True},
            "provenance": {"type": "label", "required": True},
            "note": {"type": "str"},
        }},
    "add_commitment": {
        "purpose": ("an obligation a participant already holds, with a due "
                    "time; they wake when it falls due"),
        "fields": {
            "participant": {"type": "name", "required": True},
            "what": {"type": "str", "required": True},
            "due_local": {"type": "local_dt", "required": True},
            "tz": {"type": "tz", "required": True},
            "wake": {"type": "bool", "note": "default true"},
            "provenance": {"type": "label", "required": True},
            "note": {"type": "str"},
        }},
    "define_action": {
        "purpose": ("something an actor can ATTEMPT (never a prediction "
                    "that they will).  Composed of universal effects; "
                    "authority via allowed_roles; takes real time"),
        "fields": {
            "verb": {"type": "slug", "required": True},
            "description": {"type": "str", "required": True,
                            "note": "shown to the actor; explain params"},
            "allowed_roles": {"type": "str_list",
                              "note": "roles that may attempt it; empty = "
                                      "any participant"},
            "params": {"type": "params",
                       "note": "small fields the actor fills when acting"},
            "requires": {"type": "requires",
                         "note": "preconditions beyond authority"},
            "effects": {"type": "effects", "required": True,
                        "note": "what happens when it COMPLETES"},
            "duration_minutes": {"type": "num", "concrete": True,
                                 "note": "typical time the attempt takes"},
            "completes_when": {"type": "completes_when",
                               "note": "alternative to duration: completes "
                                       "when a quantity reaches a level"},
            "interruptible": {"type": "bool"},
            "provenance": {"type": "label", "required": True, "concrete": True},
            "note": {"type": "str", "required": True},
        }},
    "schedule_external_event": {
        "purpose": ("something already scheduled to happen in the world "
                    "regardless of any actor's choice (a release, opening, "
                    "deadline side-effect).  NEVER an actor's future "
                    "decision -- those are simulated, not scheduled"),
        "fields": {
            "name": {"type": "slug", "required": True},
            "at_local": {"type": "local_dt", "required": True},
            "tz": {"type": "tz", "required": True},
            "effects": {"type": "effects", "required": True},
            "provenance": {"type": "label", "required": True, "concrete": True},
            "note": {"type": "str", "required": True},
        }},
    "schedule_wake": {
        "purpose": ("a participant will attend to the situation at a known "
                    "time (a planned check-in, an appointment they will "
                    "keep)"),
        "fields": {
            "participant": {"type": "name", "required": True},
            "at_local": {"type": "local_dt", "required": True},
            "tz": {"type": "tz", "required": True},
            "reason": {"type": "str", "required": True},
            "provenance": {"type": "label", "required": True},
        }},
    "declare_uncertainty": {
        "purpose": ("record something genuinely unknown that matters; it "
                    "stays visible instead of silently becoming a fact"),
        "fields": {
            "about": {"type": "str", "required": True},
            "why_it_matters": {"type": "str", "required": True},
        }},
    "declare_exclusion": {
        "purpose": "record something deliberately left out, and why safe",
        "fields": {
            "what": {"type": "str", "required": True},
            "why_safe": {"type": "str", "required": True},
        }},
    "set_terminal": {
        "purpose": ("the exact observable condition that answers the "
                    "question, plus the hard cutoff"),
        "fields": {
            "question_restated": {"type": "str", "required": True},
            "mode": {"type": "str", "required": True,
                     "one_of": ["condition", "value", "decision_count"]},
            "cutoff_local": {"type": "local_dt", "required": True},
            "tz": {"type": "tz", "required": True},
            "condition": {"type": "expr",
                          "note": "condition mode: resolves YES when true"},
            "value": {"type": "value_read",
                      "note": "value mode: quantity reported at the cutoff"},
            "decision": {"type": "decision",
                         "note": "decision_count mode: count typed records "
                                 "by option"},
            "resolve_when": {"type": "expr",
                             "note": "optional early resolution condition"},
            "yes_means": {"type": "str"},
            "no_means": {"type": "str"},
        }},
}

# ---------------------------------------------------------------------------
# structural validation
# ---------------------------------------------------------------------------

def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_templates(text: str, allowed_params, context: str, errors, where):
    """Template hygiene: only {actor}/{action_id}/{now}/{params.x} inside an
    action, and no templates at all inside an external event."""
    for token in _TEMPLATE_RE.findall(str(text)):
        if context == "external":
            errors.append(f"{where}: templates like {{{token}}} are not "
                          f"allowed in scheduled external events")
        elif token in ("actor", "action_id", "now"):
            continue
        elif token.startswith("params."):
            if token[len("params."):] not in allowed_params:
                errors.append(f"{where}: template {{{token}}} references an "
                              f"undeclared param")
        else:
            errors.append(f"{where}: unknown template {{{token}}}")


def _validate_field(cap: str, fname: str, spec: dict, value, errors,
                    allowed_params=(), context: str = "action") -> None:
    t = spec["type"]
    where = f"{cap}.{fname}"
    if t == "str":
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{where}: non-empty string required")
    elif t == "slug":
        if not isinstance(value, str) or not re.match(r"^[a-z0-9][a-z0-9_.\-]*$", value):
            errors.append(f"{where}: lowercase slug required "
                          f"(letters/digits/underscore), got {value!r}")
    elif t == "num":
        if not _is_num(value):
            errors.append(f"{where}: number required, got {value!r}")
    elif t == "bool":
        if not isinstance(value, bool):
            errors.append(f"{where}: true/false required")
    elif t == "any":
        if not isinstance(value, (str, int, float, bool)):
            errors.append(f"{where}: scalar value required")
    elif t == "str_list":
        if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
            errors.append(f"{where}: list of strings required")
    elif t == "label":
        if value not in PROVENANCE_LABELS:
            errors.append(f"{where}: provenance must be one of "
                          f"{list(PROVENANCE_LABELS)}")
        elif spec.get("concrete") and value not in CONCRETE_LABELS:
            errors.append(f"{where}: a concrete number cannot be labeled "
                          f"'uncertain' -- either give a labeled estimate "
                          f"(inferred/model_memory_unverified) or model the "
                          f"unknown differently (declare_uncertainty, "
                          f"none_known attention, completes_when)")
    elif t == "tz":
        if not isinstance(value, str) or "/" not in value and value != "UTC":
            errors.append(f"{where}: IANA time zone required, got {value!r}")
    elif t == "hhmm":
        if not isinstance(value, str) or not _HHMM_RE.match(value):
            errors.append(f"{where}: 'HH:MM' required, got {value!r}")
    elif t == "local_dt":
        if not isinstance(value, str) or not _LOCAL_DT_RE.match(value):
            errors.append(f"{where}: 'YYYY-MM-DD HH:MM' required, got {value!r}")
    elif t == "weekdays":
        if not isinstance(value, list) or not value \
                or any(not isinstance(d, int) or d < 0 or d > 6 for d in value):
            errors.append(f"{where}: list of weekday numbers 0-6 required")
    elif t == "name":
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{where}: a declared name required")
    elif t == "name_or_actor":
        if not (isinstance(value, str) and (value.strip() or value == "{actor}")):
            errors.append(f"{where}: a declared name or {{actor}} required")
    elif t == "num_or_template":
        if not _is_num(value):
            if not isinstance(value, str) or not _TEMPLATE_RE.fullmatch(value):
                errors.append(f"{where}: number or single {{params.x}} "
                              f"template required")
            else:
                _check_templates(value, allowed_params, context, errors, where)
    elif t == "recipients":
        if isinstance(value, list):
            if not value or any(not isinstance(x, str) for x in value):
                errors.append(f"{where}: non-empty list of names required")
        elif isinstance(value, dict):
            if set(value) != {"roles"} or not isinstance(value["roles"], list) \
                    or not value["roles"]:
                errors.append(f"{where}: role selector must be "
                              f"{{\"roles\": [..]}}")
        else:
            errors.append(f"{where}: list of names or {{\"roles\": [..]}} required")
    elif t == "params":
        if not isinstance(value, list):
            errors.append(f"{where}: list required")
        else:
            for i, p in enumerate(value):
                if not isinstance(p, dict) or not isinstance(p.get("name"), str) \
                        or not re.match(r"^[a-z][a-z0-9_]*$", p.get("name", "")):
                    errors.append(f"{where}[{i}]: param needs a slug 'name'")
                    continue
                if not isinstance(p.get("note", ""), str):
                    errors.append(f"{where}[{i}]: note must be a string")
                if "one_of" in p and (not isinstance(p["one_of"], list)
                                      or not p["one_of"]):
                    errors.append(f"{where}[{i}]: one_of must be a non-empty list")
    elif t == "requires":
        if not isinstance(value, list):
            errors.append(f"{where}: list required")
        else:
            for i, r in enumerate(value):
                if not isinstance(r, dict) \
                        or r.get("kind") not in REQUIRE_KINDS:
                    errors.append(f"{where}[{i}]: kind must be one of "
                                  f"{sorted(REQUIRE_KINDS)}")
                    continue
                for f in REQUIRE_KINDS[r["kind"]]:
                    if f not in r:
                        errors.append(f"{where}[{i}]: {r['kind']} requires "
                                      f"field {f!r}")
                for k, v in r.items():
                    if isinstance(v, str):
                        _check_templates(v, allowed_params, context, errors,
                                         f"{where}[{i}]")
    elif t == "effects":
        validate_effects(value, errors, allowed_params, context, where, depth=0)
    elif t == "completes_when":
        if not isinstance(value, dict) \
                or not all(f in value for f in ("holder", "resource", "amount")):
            errors.append(f"{where}: needs holder, resource, amount")
        elif not _is_num(value["amount"]):
            if not (isinstance(value["amount"], str)
                    and _TEMPLATE_RE.fullmatch(value["amount"])):
                errors.append(f"{where}.amount: number or single template "
                              f"required")
            else:
                _check_templates(value["amount"], allowed_params, context,
                                 errors, where)
    elif t == "expr":
        validate_name_expr(value, errors, where)
    elif t == "value_read":
        if not isinstance(value, dict) \
                or value.get("read") not in ("resource", "count_records"):
            errors.append(f"{where}: read must be 'resource' or "
                          f"'count_records'")
        elif value["read"] == "resource":
            for f in ("holder", "resource"):
                if not value.get(f):
                    errors.append(f"{where}: resource read requires {f!r}")
        else:
            for f in ("record_type", "subject"):
                if not value.get(f):
                    errors.append(f"{where}: count_records requires {f!r}")
    elif t == "decision":
        if not isinstance(value, dict):
            errors.append(f"{where}: dict required")
        else:
            for f in ("record_type", "subject", "options"):
                if not value.get(f):
                    errors.append(f"{where}: decision requires {f!r}")
            if not isinstance(value.get("options"), list) \
                    or len(value.get("options") or []) < 2:
                errors.append(f"{where}: options must list >= 2 choices")
    else:  # pragma: no cover -- table error, not input error
        errors.append(f"{where}: unknown field type {t!r} in menu table")


def _sweep_templates(value, allowed_params, context, errors, where) -> None:
    """Template hygiene over every string in an effect, wherever it sits."""
    if isinstance(value, str):
        _check_templates(value, allowed_params, context, errors, where)
    elif isinstance(value, list):
        for v in value:
            _sweep_templates(v, allowed_params, context, errors, where)
    elif isinstance(value, dict):
        for v in value.values():
            _sweep_templates(v, allowed_params, context, errors, where)


def validate_effects(effects, errors, allowed_params, context, where,
                     depth: int) -> None:
    if not isinstance(effects, list) or not effects:
        errors.append(f"{where}: non-empty list of effects required")
        return
    if depth > 1:
        errors.append(f"{where}: effects may nest at most one "
                      f"schedule_followup level")
        return
    for i, eff in enumerate(effects):
        w = f"{where}[{i}]"
        if not isinstance(eff, dict) or eff.get("do") not in EFFECT_MACROS:
            errors.append(f"{w}: 'do' must be one of {sorted(EFFECT_MACROS)}")
            continue
        macro = EFFECT_MACROS[eff["do"]]
        for f in eff:
            if f != "do" and f not in macro["fields"]:
                errors.append(f"{w}: unknown field {f!r} for {eff['do']}")
        for fname, spec in macro["fields"].items():
            if spec.get("required") and fname not in eff:
                errors.append(f"{w}: {eff['do']} requires field {fname!r}")
        for fname, spec in macro["fields"].items():
            if fname not in eff:
                continue
            if fname == "effects":
                validate_effects(eff[fname], errors, allowed_params, context,
                                 f"{w}.effects", depth + 1)
            else:
                _validate_field(eff["do"], fname, spec, eff[fname], errors,
                                allowed_params, context)
        _sweep_templates({k: v for k, v in eff.items()
                          if k not in ("do", "effects")},
                         allowed_params, context, errors, w)
        if eff.get("do") == "send_information":
            if context == "external" and not eff.get("author"):
                errors.append(f"{w}: send_information in an external event "
                              f"requires an author")
            if context != "external" and eff.get("author"):
                errors.append(f"{w}: author is only valid in external "
                              f"events (inside an action the actor is the "
                              f"author)")
        if eff.get("do") == "create_record":
            if context == "external" and eff.get("per_actor", True):
                errors.append(f"{w}: create_record in an external event "
                              f"must set per_actor false")
            if "choice_template" not in eff and "value" not in eff:
                errors.append(f"{w}: create_record needs choice_template "
                              f"or value")


def validate_name_expr(expr, errors, where) -> None:
    if not isinstance(expr, dict):
        errors.append(f"{where}: expression must be a dict")
        return
    if "all_of" in expr or "any_of" in expr:
        key = "all_of" if "all_of" in expr else "any_of"
        if not isinstance(expr[key], list) or not expr[key]:
            errors.append(f"{where}.{key}: non-empty list required")
            return
        for i, kid in enumerate(expr[key]):
            validate_name_expr(kid, errors, f"{where}.{key}[{i}]")
        return
    kind = expr.get("check")
    if kind not in TERMINAL_CHECKS:
        errors.append(f"{where}: check must be one of {sorted(TERMINAL_CHECKS)}"
                      f" -- write checks FLAT, e.g. {{\"check\": "
                      f"\"fact_equals\", \"key\": \"...\", \"value\": ...}}")
        return
    for f in TERMINAL_CHECKS[kind]:
        if f not in expr:
            errors.append(f"{where}: {kind} requires field {f!r}")


# ---------------------------------------------------------------------------
# normalization: unambiguous synonymous shapes are rewritten, never guessed
# ---------------------------------------------------------------------------

_DT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::\d{2})?$")


def _norm_dt(v):
    m = _DT_RE.match(v) if isinstance(v, str) else None
    return f"{m.group(1)} {m.group(2)}" if m else v


def _norm_keyed(d, known, field):
    """{"<kind>": {..fields..}} -> {"<field>": "<kind>", ..fields..} when the
    single key is a known kind -- the exact nested spelling models produce."""
    if isinstance(d, dict) and field not in d and len(d) == 1:
        (k, v), = d.items()
        if k in known and isinstance(v, dict):
            return {field: k, **v}
    return d


def normalize_expr(expr):
    if not isinstance(expr, dict):
        return expr
    if "all_of" in expr or "any_of" in expr:
        key = "all_of" if "all_of" in expr else "any_of"
        if isinstance(expr[key], list):
            return {key: [normalize_expr(k) for k in expr[key]]}
        return expr
    return _norm_keyed(expr, TERMINAL_CHECKS, "check")


def normalize_effects(effects):
    if isinstance(effects, dict):
        effects = [effects]          # a single macro not wrapped in a list
    if not isinstance(effects, list):
        return effects
    out = []
    for eff in effects:
        eff = _norm_keyed(eff, EFFECT_MACROS, "do")
        if isinstance(eff, dict) and isinstance(eff.get("effects"), list):
            eff = dict(eff, effects=normalize_effects(eff["effects"]))
        out.append(eff)
    return out


_HHMM_LOOSE = re.compile(r"^(\d{1,2}):?(\d{2})(?::\d{2})?$")


def _norm_hhmm(v):
    m = _HHMM_LOOSE.match(v) if isinstance(v, str) else None
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else v


def normalize_capability(instance) -> None:
    """In-place shape normalization applied before validation.  Only exact,
    unambiguous synonymous shapes are rewritten (nested single-key kinds,
    'T' datetime separators, '0900'-style times, dict-shaped param maps,
    JSON nulls meaning absent); nothing is invented."""
    if not isinstance(instance, dict):
        return
    table = CAPABILITIES.get(instance.get("capability"))
    fields = instance.get("fields")
    if table is None or not isinstance(fields, dict):
        return
    for fname in [k for k, v in fields.items() if v is None]:
        del fields[fname]                      # null means absent
    for fname, spec in table["fields"].items():
        if fname not in fields:
            continue
        v, t = fields[fname], spec["type"]
        if t == "local_dt":
            fields[fname] = _norm_dt(v)
        elif t == "hhmm":
            fields[fname] = _norm_hhmm(v)
        elif t == "expr":
            fields[fname] = normalize_expr(v)
        elif t == "effects":
            fields[fname] = normalize_effects(v)
        elif t == "requires" and isinstance(v, list):
            fields[fname] = [_norm_keyed(r, REQUIRE_KINDS, "kind") for r in v]
        elif t == "params" and isinstance(v, dict):
            fields[fname] = [
                dict({"name": k}, **pv) if isinstance(pv, dict)
                else {"name": k, "note": str(pv)}
                for k, pv in v.items()]


def validate_capability(instance: dict) -> list:
    """Validate one translated item -> list of error strings (empty = ok).
    Unambiguous synonymous shapes are normalized in place first."""
    errors: list = []
    if not isinstance(instance, dict):
        return ["capability instance must be a JSON object"]
    normalize_capability(instance)
    cap = instance.get("capability")
    if cap == "UNSUPPORTED":
        if not isinstance(instance.get("reason"), str) or not instance["reason"]:
            errors.append("UNSUPPORTED requires a reason")
        return errors
    if cap not in CAPABILITIES:
        return [f"unknown capability {cap!r} (or UNSUPPORTED); allowed: "
                f"{sorted(CAPABILITIES)}"]
    table = CAPABILITIES[cap]
    fields = instance.get("fields")
    if not isinstance(fields, dict):
        return [f"{cap}: 'fields' object required"]
    for f in fields:
        if f not in table["fields"]:
            errors.append(f"{cap}: unknown field {f!r} -- fields may not be "
                          f"invented")
    for fname, spec in table["fields"].items():
        if spec.get("required") and fname not in fields:
            errors.append(f"{cap}: missing required field {fname!r}")
    context = "external" if cap == "schedule_external_event" else "action"
    declared_params = tuple(
        p.get("name") for p in fields.get("params", [])
        if isinstance(p, dict)) if cap == "define_action" else ()
    for fname, spec in table["fields"].items():
        if fname in fields:
            _validate_field(cap, fname, spec, fields[fname], errors,
                            declared_params, context)
    # cross-field rules
    if cap == "define_action" and not errors:
        if "duration_minutes" not in fields and "completes_when" not in fields:
            errors.append("define_action: needs duration_minutes or "
                          "completes_when")
        for r in fields.get("requires", []):
            if r.get("kind") == "noticed_information" \
                    and r.get("param") not in declared_params:
                errors.append(f"define_action: noticed_information references "
                              f"undeclared param {r.get('param')!r}")
    if cap == "add_attention" and not errors:
        if fields["mode"] != "none_known" \
                and fields.get("provenance") == "uncertain":
            errors.append(
                "add_attention: an actual attention pattern cannot be "
                "labeled 'uncertain' -- label the estimate (inferred / "
                "model_memory_unverified) or use mode none_known")
        if fields["mode"] == "periodic":
            for f in ("tz", "open_time", "close_time", "check_every_minutes"):
                if f not in fields:
                    errors.append(
                        f"add_attention: periodic mode requires {f!r} -- if "
                        f"the exact cadence is unknown, either give a "
                        f"labeled estimate (inferred from comparable "
                        f"habits) or use mode 'continuous' with the same "
                        f"open/close window")
    if cap == "set_terminal" and not errors:
        mode = fields["mode"]
        need = {"condition": "condition", "value": "value",
                "decision_count": "decision"}[mode]
        if need not in fields:
            errors.append(f"set_terminal: mode {mode!r} requires field "
                          f"{need!r}")
    return errors


# ---------------------------------------------------------------------------
# menu rendering: the exact text the translator sees, from the same tables
# ---------------------------------------------------------------------------

def _render_fields(fields: dict, indent: str = "    ") -> list:
    out = []
    for fname, spec in fields.items():
        req = "REQUIRED" if spec.get("required") else "optional"
        note = f" -- {spec['note']}" if spec.get("note") else ""
        one_of = f" one of {spec['one_of']}" if spec.get("one_of") else ""
        out.append(f"{indent}{fname} ({spec['type']}, {req}){one_of}{note}")
    return out


def render_menu() -> str:
    lines = [
        "CAPABILITY MENU (closed: select exactly one per item, fill its "
        "fields, or return UNSUPPORTED)",
        "",
        "Provenance labels for every real-world claim: "
        + ", ".join(PROVENANCE_LABELS) + ".",
        "'uncertain' is never allowed on a concrete number.",
        "",
        "Two universal actions exist in EVERY world automatically -- do not "
        "define them yourself:",
        "  transmit_information: any participant composes and sends "
        "information to a participant they have a route to (params: to, "
        "channel, content).",
        "  review_information: any participant reads information they have "
        "noticed (params: info, content).",
        "Define an action ONLY when it does something more than sending or "
        "reading (creates a typed record, moves quantities, starts or stops "
        "a process, schedules follow-on effects).",
        "",
    ]
    for cap in CAPABILITIES:
        lines.append(f"{cap}: {CAPABILITIES[cap]['purpose']}")
        lines.extend(_render_fields(CAPABILITIES[cap]["fields"]))
        lines.append("")
    lines.append("EFFECT MACROS (the only building blocks of 'effects'):")
    lines.append("")
    for m in EFFECT_MACROS:
        lines.append(f"{m}: {EFFECT_MACROS[m]['purpose']}")
        lines.extend(_render_fields(EFFECT_MACROS[m]["fields"]))
        lines.append("")
    lines.append("Preconditions ('requires' entries): "
                 + "; ".join(f"{k} needs {list(v)}"
                             for k, v in REQUIRE_KINDS.items()))
    lines.append("")
    lines.append("Terminal checks: "
                 + "; ".join(f"{k} needs {list(v)}"
                             for k, v in TERMINAL_CHECKS.items())
                 + ".  Write each check FLAT: {\"check\": \"<kind>\", "
                 + "<fields>...}."
                 + "  Combine with {\"all_of\": [..]} / {\"any_of\": [..]}."
                 + "  information_noticed also accepts author and info_type;"
                 + " information_sent ('sender has sent information',"
                 + " whether or not it was seen yet) also accepts to and"
                 + " info_type -- the universal transmit action produces it,"
                 + " so no scenario verb is needed for plain"
                 + " sending/replying;"
                 + " record_exists also accepts by (participant) and choice.")
    lines.append("")
    lines.append("Templates: inside define_action effects/requires you may "
                 "use {actor} (the acting participant) and {params.x} for "
                 "declared params.  Scheduled external events may not use "
                 "templates.")
    return "\n".join(lines)
