"""LLM-facing discovery: five small calls, each answering one narrow
question with a small local result.

No call maintains global runtime references. No call is asked for runtime
operations, IDs, effect payloads, precondition enums or expression trees --
those belong to the assembler, the binding stage and the emitter. Every
call's prompt and raw response is logged verbatim.

Repair policy: at most ONE targeted repair per step. A repair receives the
step's own previous answer plus the exact defects and fixes only those --
it is a repair, not a reroll. A repaired step is not a first-pass success
and is counted separately.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .assemble import PRODUCER_KINDS, STEP_KINDS
from .errors import AmbiguousQuestion, SemanticAmbiguity
from .graph import ACTORS, CITED_BASES, GRAPH_BASES
from .llm import TruncatedResponse, call_json

ANSWER_TYPES = ("boolean", "quantity", "choice")
PROOF_KINDS = ("record", "state", "quantity")

_BASES_TEXT = (
    "Every object carries provenance: \"basis\" is one of "
    "\"verified\" (stated by the evidence; cite evidence_ids), "
    "\"inferred\" (a reasoned step from cited evidence; cite evidence_ids), "
    "\"question_given\" (fixed by the question itself), "
    "\"model_memory_unverified\" (from your own memory, unverified -- only "
    "when the instructions for this case allow it), or "
    "\"uncertain\" (genuinely unknown; never invent a value). "
    "\"evidence_ids\" is a list like [\"e1\"]. Never cite an id that is "
    "not in the evidence."
)

_COMMON_RULES = (
    "You are one narrow step of a world compiler. Answer ONLY this step's "
    "question, as a single JSON object exactly in the shape described. "
    "Natural-language meaning belongs in 'meaning' fields. Do NOT write "
    "identifiers, code, runtime operation names, JSON pointers, or "
    "template syntax like {braces}. Do NOT invent facts, participants, "
    "schedules, organizations or procedures that the evidence does not "
    "support. If something is unknown, say so with basis \"uncertain\" "
    "rather than choosing a convenient value.\n" + _BASES_TEXT
)


def render_question(question: dict) -> str:
    lines = ["QUESTION: " + str(question.get("question", "")).strip()]
    if question.get("deadline"):
        lines.append("DEADLINE / CUTOFF: " + str(question["deadline"]))
    if question.get("horizon"):
        lines.append("HORIZON: " + str(question["horizon"]))
    if question.get("resolution_note"):
        lines.append("RESOLUTION NOTE: " + str(question["resolution_note"]))
    return "\n".join(lines)


def render_evidence(evidence: dict) -> str:
    lines = ["EVIDENCE PACKAGE (the complete, frozen evidence; there is "
             "nothing else):"]
    for c in evidence.get("claims", ()):
        lines.append(
            f"  {c.get('id')} [{c.get('status', '?')}, "
            f"{c.get('visibility', '?')}, as of {c.get('as_of', '?')}] "
            f"{str(c.get('claim', '')).strip()} "
            f"(source: {c.get('source', 'unstated')})")
    return "\n".join(lines)


def evidence_ids(evidence: dict) -> frozenset:
    return frozenset(str(c.get("id")) for c in evidence.get("claims", ()))


# ---------------------------------------------------------------------------
# per-step validators: light shape checks so a defect is attributed to the
# right step immediately. Deep cross-references are the assembler's job.
# ---------------------------------------------------------------------------

def _prov_defects(item: dict, where: str, valid_ids: frozenset) -> list:
    out = []
    basis = item.get("basis")
    ids = item.get("evidence_ids") or []
    if basis not in GRAPH_BASES:
        out.append(f"{where}: basis must be one of {GRAPH_BASES}, "
                   f"got {basis!r}")
    elif basis in CITED_BASES and not ids:
        out.append(f"{where}: {basis!r} must cite evidence_ids")
    bad = [i for i in ids if str(i) not in valid_ids]
    if bad:
        out.append(f"{where}: cited evidence ids do not exist: {bad}")
    return out


def _need_str(item: dict, keys: tuple, where: str) -> list:
    return [f"{where}: missing {k!r}" for k in keys
            if not str(item.get(k) or "").strip()]


def v_resolution(doc: dict, valid_ids: frozenset) -> list:
    d = _need_str(doc, ("terminal_meaning", "positive_condition"),
                  "resolution")
    if doc.get("answer_type") not in ANSWER_TYPES:
        d.append(f"resolution: answer_type must be one of {ANSWER_TYPES}")
    cutoff = doc.get("cutoff") or {}
    d += _need_str(cutoff, ("when", "timezone"), "resolution.cutoff")
    proof = doc.get("proof") or []
    if not proof:
        d.append("resolution: 'proof' must list at least one observable "
                 "record, state or quantity")
    for i, p in enumerate(proof):
        w = f"resolution.proof[{i}]"
        d += _need_str(p, ("name", "meaning"), w)
        if p.get("kind") not in PROOF_KINDS:
            d.append(f"{w}: kind must be one of {PROOF_KINDS}")
        if p.get("kind") == "record" and not p.get("record_type"):
            d.append(f"{w}: a record proof needs record_type")
        if p.get("kind") == "quantity" and not p.get("holder"):
            d.append(f"{w}: a quantity proof needs holder")
    d += _prov_defects(doc, "resolution", valid_ids)
    if not isinstance(doc.get("ambiguities", []), list):
        d.append("resolution: ambiguities must be a list")
    return d


def v_spine(doc: dict, valid_ids: frozenset, proof_names: tuple) -> list:
    steps = doc.get("steps") or []
    if not steps:
        return ["spine: steps is empty"]
    d, seen = [], set()
    for s in steps:
        name = str(s.get("name") or "").strip()
        w = f"step {name or '?'!r}"
        d += _need_str(s, ("name", "meaning"), w)
        if name in seen:
            d.append(f"{w}: duplicate step name")
        seen.add(name)
        if s.get("kind") not in STEP_KINDS:
            d.append(f"{w}: kind must be one of {tuple(STEP_KINDS)}")
        if s.get("kind") == "scheduled_event" and not (
                s.get("when") or s.get("anchor")):
            d.append(f"{w}: a scheduled_event needs 'when' (calendar time "
                     f"with utc offset) or 'anchor'")
        when = str(s.get("when") or "")
        if "/" in when or ".." in when:
            d.append(f"{w}: an event happens at one instant, but 'when' "
                     f"is a range ({when!r}); a window of continuous work "
                     f"is a PROCESS (kind 'process', with its operating "
                     f"hours), not an event")
        if s.get("kind") == "uncertain_exogenous" \
                and s.get("basis") != "uncertain":
            d.append(f"{w}: an uncertain_exogenous step carries basis "
                     f"'uncertain'")
        d += _prov_defects(s, w, valid_ids)
        for p in s.get("prerequisites") or []:
            if not str(p.get("step") or "").strip():
                d.append(f"{w}: prerequisite missing 'step'")
        for pn in s.get("produces_proof") or []:
            if pn not in proof_names:
                d.append(f"{w}: produces_proof {pn!r} is not one of the "
                         f"resolution proof names {sorted(proof_names)}")
    for s in steps:
        for p in s.get("prerequisites") or []:
            ref = str(p.get("step") or "").strip()
            if ref and ref not in seen and ref not in proof_names:
                d.append(f"step {s.get('name')!r}: prerequisite {ref!r} "
                         f"names no step")
    return d


def v_producers(doc: dict, valid_ids: frozenset, step_names: tuple) -> list:
    d = []
    for a in doc.get("assignments") or []:
        step = str(a.get("step") or "").strip()
        w = f"assignment for {step or '?'!r}"
        if not step:
            d.append("assignment missing 'step'")
            continue
        if step not in step_names:
            d.append(f"{w}: names no causal step")
        if a.get("unsupported"):
            continue
        # an explicit empty producers list means 'nothing produces this'
        # (an initial fact, a self-standing schedule); the assembly
        # post-check enforces which steps genuinely need mechanisms
        for p in a.get("producers") or []:
            pw = f"{w} producer {p.get('name')!r}"
            d += _need_str(p, ("name",), pw)
            if p.get("kind") not in PRODUCER_KINDS:
                d.append(f"{pw}: kind must be one of "
                         f"{tuple(PRODUCER_KINDS)}")
            if p.get("kind") == "scheduled_event" and not (
                    p.get("when") or p.get("anchor")):
                d.append(f"{pw}: a scheduled_event producer needs 'when' "
                         f"or 'anchor'")
            d += _prov_defects(p, pw, valid_ids)
    return d


def v_entity(doc: dict, valid_ids: frozenset, name: str) -> list:
    d = []
    got = str(doc.get("name") or "").strip()
    if got != name:
        d.append(f"entity document must be about {name!r}, got {got!r}")
    avail = doc.get("availability")
    if avail:
        if not isinstance(avail.get("workdays"), list):
            d.append("availability.workdays must be a list of weekday "
                     "numbers, Monday=0")
        for k in ("open", "close"):
            if not str(avail.get(k) or "").strip():
                d.append(f"availability.{k} is missing (HH:MM)")
    needs_cal = any(
        isinstance((ch.get("attention") or {}).get("cadence_minutes"),
                   (int, float))
        for ch in doc.get("channels") or [])
    if needs_cal and not (avail and str(doc.get("timezone") or "").strip()):
        d.append("a checking cadence needs 'timezone' and 'availability' "
                 "(the real hours that anchor it)")
    for key in ("initial_state", "resources", "commitments", "authority",
                "knows", "channels", "sent_information"):
        for i, item in enumerate(doc.get(key) or []):
            w = f"{name!r}.{key}[{i}]"
            d += _prov_defects(item, w, valid_ids)
            if key == "channels":
                d += _need_str(item, ("name", "meaning"), w)
                if item.get("role") not in ("sender", "receiver", "both"):
                    d.append(f"{w}: role must be sender/receiver/both")
                att = item.get("attention")
                if att and att.get("cadence_minutes") is not None \
                        and not isinstance(att["cadence_minutes"],
                                           (int, float)):
                    d.append(f"{w}: attention.cadence_minutes must be a "
                             f"number or null")
            elif key == "commitments":
                d += _need_str(item, ("meaning",), w)
                if not (item.get("when") or item.get("anchor")):
                    d.append(f"{w}: a commitment needs 'when' or 'anchor'")
            elif key == "resources":
                d += _need_str(item, ("name", "meaning"), w)
                if not isinstance(item.get("amount"), (int, float)):
                    d.append(f"{w}: amount must be a number")
            elif key == "authority":
                d += _need_str(item, ("over", "meaning"), w)
            elif key == "sent_information":
                d += _need_str(item, ("name", "meaning", "channel"), w)
                if not isinstance(item.get("to"), list) or not item["to"]:
                    d.append(f"{w}: 'to' must be a non-empty list of "
                             f"recipient names")
                if not str(item.get("sent_time") or "").strip():
                    d.append(f"{w}: needs sent_time")
            else:
                d += _need_str(item, ("name", "meaning"), w)
    pb = doc.get("process_behavior")
    if pb:
        d += _prov_defects(pb, f"{name!r}.process_behavior", valid_ids)
    for i, item in enumerate(doc.get("not_available") or []):
        d += _need_str(item, ("meaning",), f"{name!r}.not_available[{i}]")
    return d


def v_uncertainty(doc: dict, valid_ids: frozenset) -> list:
    d = []
    for i, u in enumerate(doc.get("uncertainties") or []):
        d += _need_str(u, ("about", "meaning"), f"uncertainties[{i}]")
    for i, x in enumerate(doc.get("exclusions") or []):
        w = f"exclusions[{i}]"
        d += _need_str(x, ("name", "why_safe"), w)
        d += _prov_defects(x, w, valid_ids)
    return d


# ---------------------------------------------------------------------------
# the calls
# ---------------------------------------------------------------------------

@dataclass
class Discovery:
    resolution: dict = None
    spine: dict = None
    producers: dict = None
    state_info: dict = None
    uncertainty: dict = None
    calls: list = field(default_factory=list)     # verbatim prompt+response
    repairs: dict = field(default_factory=dict)   # step -> repair count
    validators: dict = field(default_factory=dict)  # step -> validator
    tokens: int = 0


def _ask(step: str, system: str, user: str, validator, disc: Discovery,
         call, model: str, allow_memory: bool) -> dict:
    """One discovery step: call, validate, at most one targeted repair."""
    if not allow_memory:
        system += ("\nBasis \"model_memory_unverified\" is NOT allowed for "
                   "this case: the evidence package is the whole world.")
    disc.validators[step] = validator
    doc, raw, defects = None, "", []
    for attempt in (0, 1):
        prompt_user = user if attempt == 0 else (
            user + "\n\nYOUR PREVIOUS ANSWER:\n" + raw
            + "\n\nEXACT DEFECTS -- fix ONLY these, change nothing else, "
              "and return the complete corrected JSON object:\n"
            + "\n".join(f"- {d}" for d in defects))
        try:
            doc, raw, usage = call(system, prompt_user, model=model)
            parse_error = None
        except TruncatedResponse as exc:
            doc, raw, usage = None, "", {}
            parse_error = str(exc)
        except ValueError as exc:
            doc, raw, usage = None, "", {}
            parse_error = f"the reply was not a valid JSON object: {exc}"
        disc.calls.append({"step": step, "attempt": attempt,
                           "prompt": {"system": system, "user": prompt_user},
                           "raw_response": raw, "usage": usage})
        disc.tokens += (usage or {}).get("total_tokens", 0)
        defects = [parse_error] if parse_error else validator(doc)
        if not defects:
            if attempt:
                disc.repairs[step] = disc.repairs.get(step, 0) + 1
            return doc
    raise SemanticAmbiguity(
        f"{step} discovery is still defective after one targeted repair",
        {"document": step, "defects": defects, "repairable": False})


def entity_list(resolution: dict, producers: dict) -> list:
    """The entities whose starting state must be discovered: every actor
    or non-channel process producer, plus every measured quantity's holder
    (who holds the opening stock even when producing nothing)."""
    entities, seen = [], set()
    for a in (producers or {}).get("assignments", ()):
        for p in a.get("producers") or []:
            key = (p.get("name"), PRODUCER_KINDS.get(p.get("kind")))
            if key in seen or key[1] is None:
                continue
            seen.add(key)
            if key[1] in ACTORS or (key[1] == "process"
                                    and p.get("kind")
                                    != "communication_system"):
                entities.append({"name": p["name"], "kind": p["kind"]})
    for p in (resolution or {}).get("proof", ()):
        if p.get("kind") == "quantity" and p.get("holder"):
            kind = {"person": "person"}.get(p.get("holder_kind"),
                                            "organization")
            key = (p["holder"], PRODUCER_KINDS.get(kind))
            if key not in seen:
                seen.add(key)
                entities.append({"name": p["holder"], "kind": kind})
    return entities


def _discover_new_entities(disc: Discovery, call, model) -> None:
    """Producers changed: the starting state must describe any producer it
    has never seen. Existing entity documents stay untouched."""
    fn = getattr(disc, "discover_entity", None)
    if fn is None or not disc.state_info:
        return
    have = {e.get("name") for e in disc.state_info.get("entities", [])}
    for ent in entity_list(disc.resolution, disc.producers):
        if ent["name"] not in have:
            disc.state_info["entities"].append(fn(ent, call, model))


def repair_document(disc: Discovery, doc_name: str, defects: list,
                    call=call_json, model: str = "deepseek-chat") -> bool:
    """One targeted repair of one discovery DOCUMENT, driven by defects
    found while assembling the canonical world -- exact cross-reference
    slips the per-step validation cannot see. The step's own recorded
    prompt is replayed with its previous answer and the defect list; a
    reroll never happens. Returns False when the document has no recorded
    step to repair."""
    if doc_name == "starting_state_and_information":
        steps = [s for s in disc.validators
                 if s.startswith("starting_state[")]
        # only the entities a defect actually names, when identifiable
        named = [s for s in steps
                 if any(s[len("starting_state["):-1] in d for d in defects)]
        steps = named or steps
    else:
        steps = [s for s in disc.validators if s == doc_name]
    if not steps:
        return False
    for step in steps:
        last = [c for c in disc.calls if c["step"] == step][-1]
        user = (last["prompt"]["user"]
                + "\n\nYOUR PREVIOUS ANSWER:\n" + last["raw_response"]
                + "\n\nEXACT DEFECTS found while assembling the world from "
                  "all the documents together. Fix ONLY the ones that "
                  "concern this document (references must name things that "
                  "exist; ignore defects about other entities), change "
                  "nothing else, and return the complete corrected JSON "
                  "object:\n" + "\n".join(f"- {d}" for d in defects))
        doc, raw, remaining = None, "", []
        for attempt in ("assembly_repair", "assembly_repair_shape_fix"):
            prompt_user = user if attempt == "assembly_repair" else (
                user + "\n\nYOUR CORRECTED ANSWER STILL HAS SHAPE "
                "DEFECTS -- fix ONLY these and return the complete "
                "object again:\n"
                + "\n".join(f"- {d}" for d in remaining)
                + "\n\nTHE ANSWER TO FIX:\n" + raw)
            try:
                doc, raw, usage = call(last["prompt"]["system"],
                                       prompt_user, model=model)
                err = None
            except (TruncatedResponse, ValueError) as exc:
                doc, raw, usage, err = None, "", {}, str(exc)
            disc.calls.append({"step": step, "attempt": attempt,
                               "prompt": {"system":
                                          last["prompt"]["system"],
                                          "user": prompt_user},
                               "raw_response": raw, "usage": usage})
            disc.tokens += (usage or {}).get("total_tokens", 0)
            remaining = [err] if err else disc.validators[step](doc)
            if not remaining:
                break
        if remaining:
            raise SemanticAmbiguity(
                f"{step} is still defective after its assembly repair",
                {"document": doc_name, "defects": remaining,
                 "repairable": False})
        disc.repairs[step] = disc.repairs.get(step, 0) + 1
        if step == "causal_spine":
            disc.spine = doc
            # a revised spine invalidates the producer projections (they
            # name the old steps): re-project them freshly against the new
            # spine, then discover any newly introduced producers
            fn = getattr(disc, "rediscover_producers", None)
            if fn is not None:
                fn(call, model)
                _discover_new_entities(disc, call, model)
        elif step == "producer_assignments":
            disc.producers = doc
            _discover_new_entities(disc, call, model)
        elif step == "uncertainty_and_exclusions":
            disc.uncertainty = doc
        elif step in ("resolution_contract",
                      "resolution_ambiguity_adjudication"):
            disc.resolution = doc
        elif step.startswith("starting_state["):
            name = step[len("starting_state["):-1]
            for i, ent in enumerate(disc.state_info["entities"]):
                if ent.get("name") == name:
                    disc.state_info["entities"][i] = doc
    return True


def discover(question: dict, evidence: dict, call=call_json,
             model: str = "deepseek-chat", allow_memory: bool = False,
             into: Discovery | None = None) -> Discovery:
    """Run the five discovery steps in order. Raises AmbiguousQuestion when
    the resolution step declares ambiguities instead of guessing. Pass
    ``into`` to keep the verbatim call log even when a step fails."""
    disc = into if into is not None else Discovery()
    q, ev = render_question(question), render_evidence(evidence)
    valid_ids = evidence_ids(evidence)
    ctx = q + "\n\n" + ev

    # STEP 1 -- resolution
    doc = _ask(
        "resolution_contract",
        _COMMON_RULES + "\n\nSTEP 1 -- RESOLUTION DISCOVERY.\n"
        "Answer only: what exact externally observable state, event, record "
        "or quantity resolves the question, and at what cutoff? The "
        "terminal must refer to the real-world outcome, not merely a "
        "report about it, unless the question explicitly resolves from "
        "that report.\n"
        "Return JSON with exactly these fields:\n"
        "  terminal_meaning: one sentence, what resolves the question\n"
        "  answer_type: \"boolean\" | \"quantity\" | \"choice\"\n"
        "  cutoff: {\"when\": \"YYYY-MM-DDTHH:MM:SS+HH:MM\", \"timezone\": "
        "IANA zone, \"meaning\": prose}\n"
        "  positive_condition: prose\n"
        "  negative_condition: prose or null\n"
        "  proof: list; each {\"kind\": \"record\"|\"state\"|\"quantity\", "
        "\"name\": short unique name, \"meaning\": prose, and for records "
        "\"record_type\": short noun (plus optional \"rule\": "
        "\"majority\"|\"count_all\"|\"count_value\", \"value\", "
        "\"expected_count\", \"subject\"), for quantities \"holder\": who "
        "holds it and \"unit\"} -- the observable things that would prove "
        "the outcome\n"
        "  resolves_from_report: true only if the question says the report "
        "settles it\n"
        "  measured_act: name of the act if the real-world act itself IS "
        "the measured outcome (a cast vote IS the vote record), else null\n"
        "  ambiguities: list of prose; ONLY materially different readings "
        "that the question, its RESOLUTION NOTE and the evidence together "
        "still leave open. The resolution note is authoritative: a "
        "reading it settles is settled and must NOT be declared. Never "
        "pick an open reading silently -- but never manufacture doubt "
        "about a settled one.\n"
        "  basis, evidence_ids: provenance of this terminal definition",
        ctx, lambda d: v_resolution(d, valid_ids), disc, call, model,
        allow_memory)
    if doc.get("ambiguities"):
        # A false refusal is the same disease as a false compile: before
        # stopping, one adjudication round must either quote the clause
        # that settles each reading, or confirm it is genuinely open.
        doc = _ask(
            "resolution_ambiguity_adjudication",
            _COMMON_RULES + "\n\nAMBIGUITY ADJUDICATION.\n"
            "A draft resolution declared the ambiguities listed below. For "
            "EACH one: if any clause of the question, its resolution note "
            "or the evidence settles it, it is settled -- drop it and "
            "resolve the terminal accordingly. The evidence package is "
            "COMPLETE: anything it does not mention (an extra source, a "
            "consumption process, another actor) does not exist in this "
            "world, so a reading that hinges on something unmentioned is "
            "settled by completeness and must be dropped. Keep an "
            "ambiguity only if the question and evidence as given still "
            "leave materially different answers possible. Return the "
            "complete corrected resolution object (same shape as before), "
            "with 'ambiguities' containing only the survivors.",
            ctx + "\n\nTHE DRAFT RESOLUTION:\n" + json.dumps(doc, indent=1)
            + "\n\nDECLARED AMBIGUITIES TO ADJUDICATE:\n"
            + "\n".join(f"- {a}" for a in doc["ambiguities"]),
            lambda d: v_resolution(d, valid_ids), disc, call, model,
            allow_memory)
        disc.repairs["resolution_ambiguity_adjudication"] = 1
        if doc.get("ambiguities"):
            raise AmbiguousQuestion(
                "the question admits materially different readings that "
                "survived adjudication",
                {"ambiguities": doc["ambiguities"]})
    disc.resolution = doc
    proof_names = tuple(p["name"] for p in doc["proof"])

    # STEP 2 -- backward causal spine
    disc.spine = _ask(
        "causal_spine",
        _COMMON_RULES + "\n\nSTEP 2 -- BACKWARD CAUSAL SPINE.\n"
        "CRITICAL: the causal spine describes possible and necessary "
        "causal dependencies. It is NOT a predicted trajectory. Do not "
        "convert actor choices into scheduled future events: represent "
        "them as available choices whose occurrence will be decided later "
        "by the actor during simulation. Do not decide which choices "
        "actors will make or which possible route will occur.\n"
        "Starting from the terminal, ask: what must causally happen "
        "immediately before this can become true? Repeat backward until "
        "every leaf is an initial fact, a scheduled external event, an "
        "actor decision, an organization action, a population response, "
        "an operating or physical process, or an explicitly uncertain "
        "exogenous event.\n"
        "Return JSON: {\"steps\": [...]}; each step exactly:\n"
        "  name: short unique label\n"
        "  meaning: prose, what this step is\n"
        "  kind: \"initial_fact\" | \"condition\" (an intermediate state "
        "that becomes true) | \"scheduled_event\" | \"actor_decision\" | "
        "\"organization_action\" | \"population_response\" | \"process\" | "
        "\"uncertain_exogenous\"\n"
        "  prerequisites: list of {\"step\": name of another step, "
        "\"necessity\": \"necessary\"|\"alternative\"|\"optional\", "
        "\"alt_group\": group label when alternative}\n"
        "  produces_proof: list of resolution proof names this step "
        "directly brings about (only for the step that does)\n"
        "  when: ONE calendar instant with utc offset -- ONLY for kind "
        "scheduled_event, and only when the evidence states the time. "
        "Something that runs over a window (a drive collecting 9-to-5, a "
        "line producing all shift) is a PROCESS, never an event\n"
        "  uncertainty: prose if this step's occurrence is genuinely "
        "open\n"
        "  basis, evidence_ids\n"
        "A step that directly produces a terminal proof QUANTITY must be "
        "a real mechanism that moves it -- a scheduled dispatch, a "
        "transfer, a process -- never the holder 'having' it. A "
        "fixed-size movement of stock between holders at a stated moment "
        "(a shipment of N units, a payment of N) is a scheduled_event "
        "whose occurrence transfers that amount; only sustained "
        "accumulation or consumption at a rate over a window is a "
        "process. Do not model one movement as both an event and a "
        "wrapper process around its arrival. Model each occurrence "
        "separately and completely: a Tuesday shipment and a Thursday "
        "shipment are two events, and when delivery takes time, each "
        "needs its own arrival step producing the receiving stock -- a "
        "dispatch without its arrival never delivers anything.\n"
        "The resolution proof names are: " + json.dumps(list(proof_names)),
        ctx + "\n\nTHE TERMINAL (from step 1):\n"
        + json.dumps(doc, indent=1),
        lambda d: v_spine(d, valid_ids, proof_names), disc, call, model,
        allow_memory)
    # STEP 3 -- producer assignment. The prompt is a closure over the
    # CURRENT spine, so a spine revision can re-project the assignments
    # against the new steps (a fresh discovery, not a repair).
    producers_system = (
        _COMMON_RULES + "\n\nSTEP 3 -- PRODUCER ASSIGNMENT.\n"
        "For every causal step, who or what can produce it? Use kinds: "
        "\"person\", \"organization\", \"population\", "
        "\"external_institution\", \"communication_system\", "
        "\"operating_process\", \"physical_process\", \"scheduled_event\", "
        "\"institutional_rule\". Do NOT invent a board, authority chain, "
        "process or organizational procedure because it seems plausible: "
        "if the evidence names nobody who can produce a step, mark it "
        "unsupported.\n"
        "Return JSON: {\"assignments\": [...]}; each exactly:\n"
        "  step: a causal step name\n"
        "  producers: list of {\"name\": who/what, \"kind\": one of the "
        "kinds, \"meaning\": prose role, \"basis\", \"evidence_ids\", and "
        "for scheduled_event producers \"when\"}\n"
        "  OR unsupported: prose reason nothing can produce it\n"
        "Initial facts and scheduled events need no producers. Actor "
        "decisions need the person/organization/population who could "
        "choose them. A condition with prerequisites and no mechanism of "
        "its own is a conjunction -- mark it unsupported with that "
        "reason. But the step the terminal measures needs the REAL "
        "mechanisms that change it -- the scheduled transfers, processes "
        "or actions already in the spine; never invent a wrapper process "
        "around whoever holds or reports it.")

    def rediscover_producers(rcall=None, rmodel=None):
        names = tuple(s["name"] for s in disc.spine["steps"]) + proof_names
        disc.producers = _ask(
            "producer_assignments", producers_system,
            ctx + "\n\nTHE CAUSAL STEPS (from step 2):\n"
            + json.dumps(disc.spine, indent=1),
            lambda d: v_producers(d, valid_ids, names),
            disc, rcall or call, rmodel or model, allow_memory)
        return disc.producers

    disc.rediscover_producers = rediscover_producers
    rediscover_producers()

    # STEP 4 -- starting state and information boundaries, per entity
    entities = entity_list(disc.resolution, disc.producers)

    def discover_entity(ent, ecall=None, emodel=None):
        is_process = PRODUCER_KINDS[ent["kind"]] == "process"
        shape = (
            "Return JSON exactly:\n"
            "  name: " + json.dumps(ent["name"]) + "\n"
            + ("  process_behavior: {\"meaning\": prose, \"rate_meaning\": "
               "the supported rate in prose with numbers, "
               "\"operating_meaning\": when it runs in prose, \"basis\", "
               "\"evidence_ids\"}\n"
               "  initial_state: list of {\"name\", \"meaning\", \"value\" "
               "optional, \"basis\", \"evidence_ids\"}\n"
               if is_process else
               "  timezone: IANA zone they live/work in\n"
               "  availability: {\"workdays\": [Monday=0..Sunday=6], "
               "\"open\": \"HH:MM\", \"close\": \"HH:MM\"} -- their real "
               "working/waking pattern\n"
               "  initial_state: list of {\"name\", \"meaning\", \"value\" "
               "optional, \"basis\", \"evidence_ids\"} -- what is true of "
               "them as the world opens, including commitments and "
               "stances. Never a counted stock: 'held N units' belongs "
               "under resources with amount N, or transfers and "
               "measurements cannot reach it\n"
               "  resources: list of {\"name\", \"meaning\", \"amount\" "
               "number, \"unit\", \"basis\", \"evidence_ids\"} -- STOCKS "
               "they hold that can be moved or consumed (units on hand, "
               "money, goods). Every 'holds/held N of X' in the evidence "
               "goes here. Never rates, speeds or capacities: a rate "
               "belongs to the process that runs at it, a capacity is a "
               "fact\n"
               "  commitments: list of {\"name\", \"meaning\", \"when\" "
               "calendar time with offset, \"basis\", \"evidence_ids\"} -- "
               "already-scheduled things involving them\n"
               "  authority: list of {\"over\": EXACTLY one causal step "
               "name from the context below, \"meaning\", \"basis\", "
               "\"evidence_ids\"} -- only authority the evidence "
               "supports; omit anything you cannot name exactly\n"
               "  knows: list of {\"name\", \"meaning\", \"visibility\": "
               "\"private\"|\"public\", \"basis\", \"evidence_ids\"} -- "
               "information they hold as the world opens\n"
               "  sent_information: list of {\"name\", \"meaning\", "
               "\"to\": [names], \"channel\": name, \"sent_time\": time "
               "with offset, \"basis\", \"evidence_ids\"} -- messages "
               "already in flight from them\n"
               "  channels: list of {\"name\": communication route, "
               "\"meaning\", \"role\": \"sender\"|\"receiver\"|\"both\", "
               "\"latency_meaning\": prose, \"attention\": "
               "{\"cadence_minutes\": number or null for continuous, "
               "\"meaning\": prose, \"calendar_meaning\": prose}, "
               "\"basis\", \"evidence_ids\"}\n"
               "  not_available: list of {\"meaning\", \"channel\" "
               "optional, \"from\", \"to\" times} -- access they do NOT "
               "have, including windows (travel, retreat, no account)\n")
            + "Include ONLY what the evidence and question support; empty "
              "lists are honest answers. Do not restate other entities.")
        return _ask(
            f"starting_state[{ent['name']}]",
            _COMMON_RULES + "\n\nSTEP 4 -- STARTING STATE AND INFORMATION "
            "BOUNDARY for ONE entity.\nDescribe only "
            + json.dumps(ent["name"]) + " (" + ent["kind"] + "): their "
            "relevant initial state, objective resources, existing "
            "commitments, authority and constraints, information "
            "initially available to them, information NOT available to "
            "them, and how they send/receive.\n" + shape,
            ctx + "\n\nCAUSAL STEPS AND PRODUCERS SO FAR:\n"
            + json.dumps(disc.producers, indent=1),
            lambda d, n=ent["name"]: v_entity(d, valid_ids, n),
            disc, ecall or call, emodel or model, allow_memory)

    disc.discover_entity = discover_entity
    disc.state_info = {"entities": [discover_entity(e) for e in entities]}

    # STEP 5 -- uncertainty and exclusions
    disc.uncertainty = _ask(
        "uncertainty_and_exclusions",
        _COMMON_RULES + "\n\nSTEP 5 -- UNCERTAINTY AND EXCLUSIONS.\n"
        "Which causal steps remain uncertain? Which producer states, "
        "timings, rates, attention behaviours or decisions remain "
        "unknown? Which plausible actors or processes are intentionally "
        "excluded, and why is each exclusion causally safe? Do not force "
        "uncertain steps to resolve: a world may legitimately reach its "
        "cutoff unresolved.\n"
        "Return JSON exactly:\n"
        "  uncertainties: list of {\"about\": a causal step, producer or "
        "entity name, \"meaning\": what is genuinely open}\n"
        "  exclusions: list of {\"name\": who/what is left out, "
        "\"why_safe\": why leaving it out cannot change the answer, "
        "\"basis\", \"evidence_ids\"}",
        ctx + "\n\nTHE WORLD SO FAR:\n"
        + json.dumps({"steps": [s["name"] for s in disc.spine["steps"]],
                      "entities": [e["name"] for e in entities]}, indent=1),
        lambda d: v_uncertainty(d, valid_ids), disc, call, model,
        allow_memory)
    return disc
