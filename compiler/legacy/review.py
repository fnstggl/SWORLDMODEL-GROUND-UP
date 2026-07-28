"""Adversarial review: two independent verdicts, never one vague blessing.

Reality review: does the compiled world match the real situation as of the
day, given the evidence?  It attacks invented facts, wrong casts, fantasy
timings and attention patterns, missing forces, and pre-written outcomes --
and must explicitly disposition every finding validation flagged.

Meaning review: does the runtime reconstruction still say what the approved
description said?  Drift between them means the world must not run.

Blocking objections trigger one bounded repair round in the pipeline; a
second rejection fails the compile with the objections in the report."""
from __future__ import annotations

from .llm import Caller, Trace
from .resolution import evidence_block
from .provenance import EvidenceRegistry

_RUNTIME_BRIEF = """How the runtime works (judge against THIS, not against \
an imagined simulator):
- It is deterministic mechanics plus actor models: each participant's \
decisions are made by their own model AT SIMULATION TIME.  A person can \
reply/act if they exist, have the ability and route, and can notice the \
relevant information -- no scripted "decision rule" should exist, and its \
absence is correct, not a gap.
- Every participant automatically has two universal actions: transmitting \
information to anyone they have a route to, and reading information they \
have noticed.
- Information moves mechanically: created -> sent -> delivered (channel \
latency) -> noticed ONLY through the recipient's declared, provenance-\
labeled attention pattern (their real checking habits).  Without a \
declared pattern, delivered information stays unnoticed FOREVER; checking \
frequency cannot "emerge from the actor model", so demanding a pattern's \
removal produces an impossible world.  A labeled estimate (reported \
habits, or inference from comparable people) is the correct realism; \
attack its VALUE only if evidence contradicts it.
- Noticing automatically wakes the recipient's actor model to decide what \
to do next (including replying via the universal transmit action).  No \
extra "decide" action, scheduled wake, or watch is needed beyond \
attention plus routes.
- Chance is NOT a runtime primitive.  A numeric "probability" fact is a \
DEFECT (it pre-writes the outcome): demand declared uncertainty instead, \
never a probabilistic mechanism.  Whether things happen emerges from the \
run; likelihoods emerge later across many runs.
- An honestly-labeled attention estimate (inferred from comparable \
habits, or clearly-marked memory) may be attacked ONLY by naming contrary \
evidence or a specific more-faithful alternative.  "The real habit is \
unknown" is NOT an objection -- the label already records that epistemic \
status.  And NEVER demand none_known (no pattern) for someone the answer \
requires to notice something: no pattern means they never notice, which \
pre-writes NO -- that demand is itself the distortion.
Approve when the world is as faithful as the available evidence permits, \
with honest labels on the rest -- demand fixes only for material \
distortions you can name.  Perfection beyond the evidence is not the bar."""

_REALITY_PREAMBLE = """You are an adversarial reality reviewer for a \
simulation compiler.  A described world will be simulated to answer a real \
question; your job is to attack its ACCURACY against the real situation as \
of the given day, using only the evidence provided and clearly-labeled \
memory.  Hunt for:
- invented or wrong facts, participants, authority, or relationships;
- a wrong or missing decisive force (a person, process, or rule reality \
has but the world lacks);
- unrealistic timings, latencies, rates, or attention patterns;
- uncertainty silently converted into convenient fact (including numeric \
"probability" facts -- always a defect);
- anything that pre-writes the outcome instead of letting it emerge;
- a terminal that answers a different question than the one asked.

%s

Approve ONLY what the evidence supports.  Be specific; vague unease is not \
an objection.  Reply with ONLY a JSON object.""" % _RUNTIME_BRIEF

_MEANING_PREAMBLE = """You are a meaning-preservation reviewer for a \
simulation compiler.  Compare the APPROVED DESCRIPTION of a world with the \
RUNTIME RECONSTRUCTION read back from the built world.  Flag material \
drift:
- things described but absent from the runtime;
- things in the runtime that were never described;
- changed constraints, authority, routes, attention, timing, or terminal \
meaning.
Cosmetic wording differences are not drift.

%s

A described "decision" or "possible reply" is PRESERVED when the person \
exists with the route, ability, and attention to do it -- the deciding \
itself happens at simulation time and needs no mechanism in the world.  \
Reply with ONLY a JSON object.""" % _RUNTIME_BRIEF


def _validate_review(n_findings: int):
    def check(obj) -> list:
        errors = []
        if not isinstance(obj, dict):
            return ["a JSON object is required"]
        if obj.get("verdict") not in ("approve", "revise"):
            errors.append("verdict must be 'approve' or 'revise'")
        objections = obj.get("objections")
        if not isinstance(objections, list):
            errors.append("objections must be a list (possibly empty)")
        else:
            for i, o in enumerate(objections):
                if not isinstance(o, dict) \
                        or o.get("severity") not in ("blocking", "minor") \
                        or not o.get("objection"):
                    errors.append(f"objections[{i}] needs severity "
                                  f"blocking|minor and an objection")
            if obj.get("verdict") == "revise" \
                    and not any(o.get("severity") == "blocking"
                                for o in objections if isinstance(o, dict)):
                errors.append("verdict 'revise' requires at least one "
                              "blocking objection")
        if n_findings:
            disp = obj.get("dispositions")
            if not isinstance(disp, list) or len(disp) != n_findings:
                errors.append(f"dispositions must address all {n_findings} "
                              f"flagged findings, in order")
            else:
                for i, d in enumerate(disp):
                    if not isinstance(d, dict) \
                            or d.get("disposition") not in ("accept",
                                                            "must_fix") \
                            or not d.get("why"):
                        errors.append(f"dispositions[{i}] needs disposition "
                                      f"accept|must_fix and why")
        return errors
    return check


def review_reality(question: str, asof: str, registry: EvidenceRegistry,
                   summary: str, description_text: str, findings: list,
                   unsupported: list, uncertainties: list, exclusions: list,
                   caller: Caller, trace: Trace) -> dict:
    findings_text = "\n".join(f"{i + 1}. {f}"
                              for i, f in enumerate(findings)) or "(none)"
    unsupported_text = "\n".join(f"- {u}" for u in unsupported) or "(none)"
    unc = "\n".join(f"- {u.get('about')}: {u.get('why_it_matters')}"
                    for u in uncertainties) or "(none)"
    exc = "\n".join(f"- {e.get('what')}: {e.get('why_safe')}"
                    for e in exclusions) or "(none)"
    user = f"""THE QUESTION: {question}
Facts as of: {asof}

{evidence_block(registry, asof)}

THE COMPILED WORLD (as the runtime will actually simulate it):
{summary}

DECLARED UNCERTAINTIES (kept as uncertainty, not fact):
{unc}

DECLARED EXCLUSIONS (left out on purpose):
{exc}

ITEMS THE TRANSLATOR COULD NOT EXPRESS (dropped from the world):
{unsupported_text}

FINDINGS FLAGGED BY MECHANICAL VALIDATION (disposition each one, in order):
{findings_text}

Judge: does this world match the real situation as of {asof} closely enough \
that simulating it would answer the question honestly?  Attack what is \
wrong or missing.  For each flagged finding decide: "accept" (the modeling \
choice reflects reality) or "must_fix" (it distorts reality), with why.

Reply with ONLY:
{{"verdict": "approve" | "revise",
  "objections": [{{"severity": "blocking" | "minor", "about": "...",
                   "objection": "...", "fix_hint": "..."}}],
  "dispositions": [{{"finding": 1, "disposition": "accept" | "must_fix",
                     "why": "..."}}]}}"""
    return caller.ask_json("review.reality", _REALITY_PREAMBLE, user, trace,
                           validate=_validate_review(len(findings)))


def review_meaning(description_text: str, summary: str, caller: Caller,
                   trace: Trace) -> dict:
    user = f"""THE APPROVED DESCRIPTION (what the describer intended):
{description_text}

THE RUNTIME RECONSTRUCTION (read back from the built world):
{summary}

Did the build preserve the meaning?  Flag material drift only.

Reply with ONLY:
{{"verdict": "approve" | "revise",
  "objections": [{{"severity": "blocking" | "minor", "about": "...",
                   "objection": "...", "fix_hint": "..."}}]}}"""
    return caller.ask_json("review.meaning", _MEANING_PREAMBLE, user, trace,
                           validate=_validate_review(0))


def render_description(resolution: dict, description: dict) -> str:
    """The approved description as one text block (for review + bundle)."""
    lines = [f"Observable resolution: {resolution['observable_outcome']}",
             f"Answer mode: {resolution['answer_mode']}; YES: "
             f"{resolution['yes_means']}; NO: {resolution['no_means']}",
             f"Start {resolution['start_local']} {resolution['tz']}; cutoff "
             f"{resolution['cutoff_local']} {resolution['cutoff_tz']} "
             f"({resolution['horizon_note']})"]
    if resolution.get("reframed"):
        lines.append(f"Reframed from the original question: "
                     f"{resolution['reframing_note']}")
    lines.append("")
    lines.append("Causal spine (what must be possible, backward):")
    for s in description.get("spine", []):
        lines.append(f"- {s['needed']}  <= {s['producible_by']}")
    for category in ("participants", "aggregates", "communication",
                     "starting_state", "actions", "external", "uncertainty",
                     "exclusions"):
        items = description.get(category, [])
        if not items:
            continue
        lines.append("")
        lines.append(f"{category}:")
        for it in items:
            ev = f" [docs: {', '.join(it['evidence'])}]" \
                if it.get("evidence") else ""
            lines.append(f"- ({it['provenance']}{ev}) {it['text']}")
    return "\n".join(lines)
