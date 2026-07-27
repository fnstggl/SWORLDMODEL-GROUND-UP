"""Causal discovery: small natural-language calls, one aspect at a time.

Each call returns a short list of ATOMIC items (one claim per item, with a
provenance label and optional document citations) -- never one giant world
file.  The categories together cover: who exists, what can be attempted,
what is already true, who knows what, how information moves, what runs on
its own, what is scheduled, what is uncertain, and what is excluded.

The causal spine (worked backward from the observable outcome) is collected
for validation and review context; it lists what must be POSSIBLE, never
what will happen."""
from __future__ import annotations

from .capabilities import LIMITS, PROVENANCE_LABELS
from .llm import Caller, StageFailed, Trace
from .provenance import EvidenceRegistry
from .resolution import DESCRIBER_PREAMBLE, evidence_block

MAX_ITEMS = 16

#: category -> (bound, instruction).  Wording is universal; scenario meaning
#: only ever arrives in the model's answers (data).
CATEGORIES = [
    ("participants", LIMITS["participants"], """List the people (or \
person-like deciding units, e.g. a named officeholder) whose DECISIONS the \
outcome actually depends on -- the smallest sufficient cast.  One item per \
person: their name, real position/role, time zone or location if known, why \
the outcome depends on them, their goals, dispositions, and current focus, \
in plain sentences.  Exclude anyone whose absence would not change the \
answer."""),
    ("aggregates", LIMITS["aggregates"], """List the organizations, \
populations, audiences, systems, or places that matter but do NOT \
deliberate turn by turn -- their influence is quantities, rates, schedules, \
or standing rules.  One item each: what it is, what kind of thing it is, \
and why it matters.  Return an empty list if none matter."""),
    ("communication", MAX_ITEMS, """Describe how information really moves \
here, one atomic item each:
- each CHANNEL information travels through, with its typical delivery \
latency (seconds/minutes) and where that estimate comes from;
- each real ROUTE: who can actually reach whom on a channel (has the \
address / number / access) -- routes are not symmetric and not universal;
- each participant's real ATTENTION pattern on a channel: when they \
actually look (working hours? cadence? continuous alerts?).  If the real \
pattern is unknown, say exactly that -- unnoticed information then stays \
unnoticed."""),
    ("starting_state", MAX_ITEMS, """What is ALREADY TRUE when the world \
starts, one atomic claim per item:
- standing facts and statuses;
- quantities with units and holders (counts, stocks, balances, tallies);
- what each participant privately knows or believes (their knowledge \
boundary -- who does NOT know what matters too);
- existing relationships between the named people and things;
- obligations already scheduled, with due times;
- anything already in flight (a sent-but-unread message, a running \
order)."""),
    ("actions", LIMITS["actions"], """What can each participant ATTEMPT \
beyond plain sending and reading of messages (those two exist automatically \
for everyone with a route)?  One item per distinct attempt-type: who may \
attempt it (by role), what completing it changes in the world (a typed \
decision/approval record?  a quantity change?  a possession transfer?  \
starting or stopping a process?  follow-on effects after a delay?), what it \
requires beforehand, roughly how long the attempt takes and where that \
estimate comes from.  Describe possibilities only -- never assert that \
anyone WILL do these things."""),
    ("external", MAX_ITEMS, """What happens in this world WITHOUT anyone \
deciding, one atomic item each:
- ongoing processes with rates (production, spending, accumulation, decay) \
and their capacities;
- the operating schedules of those processes (shifts, opening hours);
- events already scheduled to occur regardless of anyone's choices \
(releases, openings, closings, deadline side-effects), with times;
- thresholds that someone is actively watching.
NEVER place a person's future decision here -- decisions are simulated, \
not scheduled."""),
    ("uncertainty", MAX_ITEMS, """What is genuinely unknown that materially \
affects the outcome?  One item each: what is unknown and why it matters.  \
These stay declared as uncertainty in the compiled world."""),
    ("exclusions", MAX_ITEMS, """What would a careful modeler deliberately \
LEAVE OUT of the smallest faithful world, and why is each exclusion safe \
(why it cannot change the answer)?  One item each."""),
]


def _validate_items(bound: int, registry: EvidenceRegistry):
    def check(obj) -> list:
        errors = []
        if not isinstance(obj, dict) or not isinstance(obj.get("items"), list):
            return ["reply must be {\"items\": [...]}"]
        if len(obj["items"]) > bound:
            errors.append(f"at most {bound} items are allowed; keep the "
                          f"smallest faithful set")
        for i, it in enumerate(obj["items"]):
            if not isinstance(it, dict):
                errors.append(f"items[{i}] must be an object")
                continue
            if not isinstance(it.get("text"), str) or len(it.get("text", "")) < 3:
                errors.append(f"items[{i}].text must be a non-empty claim")
            if it.get("provenance") not in PROVENANCE_LABELS:
                errors.append(f"items[{i}].provenance must be one of "
                              f"{list(PROVENANCE_LABELS)}")
            ev = it.get("evidence", [])
            if not isinstance(ev, list) or any(not isinstance(x, str) for x in ev):
                errors.append(f"items[{i}].evidence must be a list of "
                              f"document ids")
            else:
                if registry.mode == "model_memory" and ev:
                    it["evidence"] = ev = []   # no documents exist to cite
                errors.extend(registry.check_claim(it.get("provenance"),
                                                   ev, f"items[{i}]"))
        return errors
    return check


def _validate_spine(obj) -> list:
    errors = []
    if not isinstance(obj, dict) or not isinstance(obj.get("steps"), list) \
            or not obj.get("steps"):
        return ["reply must be {\"steps\": [...]} with at least one step"]
    if len(obj["steps"]) > 8:
        errors.append("at most 8 steps")
    for i, s in enumerate(obj["steps"]):
        if not isinstance(s, dict) or not s.get("needed") \
                or not s.get("producible_by"):
            errors.append(f"steps[{i}] needs 'needed' and 'producible_by'")
    return errors


def _frame(question: str, asof: str, resolution: dict,
           registry: EvidenceRegistry) -> str:
    return f"""THE QUESTION (data, not instructions):
{question}

THE OBSERVABLE RESOLUTION (already fixed):
{resolution['observable_outcome']}
Answer mode: {resolution['answer_mode']}.  World starts \
{resolution['start_local']} {resolution['tz']}; hard cutoff \
{resolution['cutoff_local']} {resolution['cutoff_tz']}.
Smallest world: {resolution['smallest_world']}

{evidence_block(registry, asof)}"""


def discover(question: str, asof: str, resolution: dict,
             registry: EvidenceRegistry, caller: Caller, trace: Trace,
             corrections: str = "") -> dict:
    """Run all discovery calls -> {"spine": [...], <category>: [items...]}."""
    frame = _frame(question, asof, resolution, registry)
    fix = (f"\n\nCORRECTIONS FROM A PREVIOUS ATTEMPT (address them):\n"
           f"{corrections}" if corrections else "")
    out: dict = {}
    spine_user = f"""{frame}

Work BACKWARD from the observable resolution.  For the outcome to become \
true, what conditions must become true, and who or what could produce each \
one (a person's possible decision, an ongoing process, a scheduled event, \
an institutional rule)?  These are possibilities, not predictions.  If some \
essential condition has NO possible producer in reality, say so in that \
step ("producible_by": "nothing -- explain").{fix}

Reply with ONLY: {{"steps": [{{"needed": "...", "producible_by": "..."}}]}}"""
    out["spine"] = caller.ask_json("discovery.spine", DESCRIBER_PREAMBLE,
                                   spine_user, trace,
                                   validate=_validate_spine)["steps"]
    spine_text = "\n".join(f"- {s['needed']}  <= {s['producible_by']}"
                           for s in out["spine"])
    prior_context = ""
    for category, bound, instruction in CATEGORIES:
        user = f"""{frame}

THE CAUSAL SPINE (what must be POSSIBLE, worked backward):
{spine_text}
{prior_context}
YOUR TASK NOW -- {category.upper()}:
{instruction}

Each item must state exactly ONE atomic claim, in plain language, with a \
provenance label and (if verified) document citations.{fix}

Reply with ONLY:
{{"items": [{{"text": "one atomic claim", "provenance": "label", \
"evidence": []}}]}}"""
        try:
            obj = caller.ask_json(f"discovery.{category}", DESCRIBER_PREAMBLE,
                                  user, trace,
                                  validate=_validate_items(bound, registry))
            out[category] = obj["items"]
        except StageFailed:
            if category in ("participants",):
                raise                      # a world with nobody in it is dead
            out[category] = []
        if category == "participants" and out[category]:
            names = "; ".join(it["text"].split(".")[0][:80]
                              for it in out[category])
            prior_context = (f"\nPARTICIPANTS ALREADY ESTABLISHED (use these "
                             f"exact names): {names}\n")
    return out
