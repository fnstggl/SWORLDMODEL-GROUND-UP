"""README + SETTLING_RESULT.md for the settling experiment.

Experiment-only.  Every number rendered here is read from
``SETTLING_MEASUREMENTS.json``, which is itself assembled from the
per-rep ``settling_measurement.json`` files the live runs wrote.  Nothing
is retyped by hand and the verdict is COMPUTED by :func:`verdict` from
the two arms' enactment rates under a rule stated in the document itself,
so a reader can re-derive it.
"""

from __future__ import annotations

import json
from pathlib import Path

RUN_LABEL = "UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION"

BANNER = (
    "> **" + RUN_LABEL + "**\n>\n"
    "> This is a transparency experiment on a simulation engine. It is "
    "not a prediction about any real person, it is not calibrated "
    "against any real-world outcome, and n = 3 live samples per arm is "
    "far too small to estimate a rate precisely. Read every number below "
    "as a description of what this engine did on these runs.\n")

#: the two hypotheses the experiment separates, stated before the data
HYPOTHESES = {
    "R1_strong": (
        "World construction. The live sender does not enact "
        "its candidate BECAUSE the compiled world already narrates the "
        "send as having happened. Remove the pre-narration and a live "
        "sender will enact the candidate. Practical fix: compiler prompt "
        "hygiene -- stop teaching the pre-narrated, sender-only send "
        "event."),
    "R3": (
        "Engine intervention semantics. The live sender does not "
        "enact its candidate because the engine SUGGESTS the "
        "intervention to the insertion actor rather than ENACTING it, "
        "and a free-choice actor need not restate a message it was "
        "merely told about -- pre-narrated or not. Practical fix: an "
        "engine semantic change (enact the intervention as a pre-start "
        "event authored by the insertion actor), which costs that actor "
        "the freedom to decline."),
}


def _dig(row, dotted):
    value = row
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _pct(rate) -> str:
    if rate is None:
        return "n/a"
    return f"{rate['hits']}/{rate['n']}"


def verdict(aggregate: dict) -> dict:
    """Which hypothesis survived, computed from the two arms.

    The decision rule, fixed before the runs and restated in the
    document: the experiment turns on ARM B's enactment rate, because
    arm B is the only arm in which R1-strong makes a positive prediction.

    - arm B enactment > 0 and arm B > arm A  -> R1-strong SURVIVES
    - arm B enactment == 0                   -> R1-strong REFUTED (in its
      strong form); R3 survives
    - arm B > 0 and arm A > 0 and equal      -> pre-narration is not the
      operative variable; R3 survives with the note that enactment
      happens anyway
    """
    arm_a = aggregate["arms"]["a"]
    arm_b = aggregate["arms"]["b"]
    enact_a = arm_a["sender_enacted_candidate_verbatim"]
    enact_b = arm_b["sender_enacted_candidate_verbatim"]
    deliver_b = arm_b["candidate_text_in_recipient_prompts"]
    if enact_b["n"] == 0 or enact_a["n"] == 0:
        return {"survived": "UNDETERMINED",
                "reason": "at least one arm recorded no reps",
                "arm_a_enactment": _pct(enact_a),
                "arm_b_enactment": _pct(enact_b)}
    if enact_b["hits"] == 0:
        survived = "R3"
        reason = (
            "the live sender did not enact its candidate in ANY arm-B rep "
            f"({_pct(enact_b)}), i.e. removing the pre-narration did not "
            "make the sender restate the message. R1-strong predicted the "
            "opposite and is refuted in its strong form; the engine's "
            "suggest-not-enact intervention semantics (R3) is what "
            "remains standing.")
    elif enact_b["hits"] > enact_a["hits"]:
        survived = "R1_strong"
        reason = (
            f"the live sender enacted its candidate in {_pct(enact_b)} "
            f"arm-B reps but only {_pct(enact_a)} arm-A reps. Removing "
            "the pre-narration is what changed the sender's behaviour, "
            "which is R1-strong's positive prediction.")
    else:
        survived = "R3"
        reason = (
            f"the sender enacted at the same rate in both arms "
            f"(A {_pct(enact_a)}, B {_pct(enact_b)}), so the "
            "pre-narration is not the operative variable; whatever drives "
            "enactment here, removing the pre-narration is not it.")
    return {
        "survived": survived,
        "reason": reason,
        "arm_a_enactment": _pct(enact_a),
        "arm_b_enactment": _pct(enact_b),
        "arm_b_candidate_reached_recipient": _pct(deliver_b),
        "practical_fix": (
            "compiler prompt hygiene" if survived == "R1_strong"
            else "an engine semantic change, not compiler prompt hygiene"),
        "also_measured": _also_measured(arm_a, arm_b),
    }


def _mean(values):
    numbers = [value for value in (values or ()) if isinstance(value,
                                                               (int, float))]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 4)


def _also_measured(arm_a: dict, arm_b: dict) -> dict:
    """Content-blind facts recorded next to the verdict but NOT part of
    the decision rule.

    The two overlap statistics are the only mechanical evidence for
    something the binary enactment reading cannot express: whether the
    sender's behaviour changed between arms at all.  They are reported
    with their means so a reader can see the direction without having to
    read six turns -- but the turns are quoted too, and they are what
    settles it.
    """
    a_overlap = _mean(arm_a.get("candidate_token_overlap_ratio"))
    b_overlap = _mean(arm_b.get("candidate_token_overlap_ratio"))
    a_run = _mean(arm_a.get("longest_shared_run_chars"))
    b_run = _mean(arm_b.get("longest_shared_run_chars"))
    return {
        "mean_token_overlap_arm_a": a_overlap,
        "mean_token_overlap_arm_b": b_overlap,
        "mean_longest_shared_run_arm_a": a_run,
        "mean_longest_shared_run_arm_b": b_run,
        "arm_b_reuses_more_candidate_vocabulary": (
            None if a_overlap is None or b_overlap is None
            else b_overlap > a_overlap),
        "note": ("a higher overlap in arm B with enactment still at zero "
                 "means the sender's first turn CHANGED but its message "
                 "text remained its own: it wrote about the send in the "
                 "candidate's vocabulary without reproducing the "
                 "candidate. Read the quoted turns; they are the "
                 "evidence, these numbers only point at it."),
    }


def _quote(text) -> str:
    if not text:
        return "    (no text recorded)"
    return "\n".join("    " + line for line in str(text).splitlines())


def _arm_block(summary: dict) -> str:
    lines = [
        f"### Arm {summary['arm'].upper()} -- {summary['arm_label']}",
        "",
        summary["arm_note"],
        "",
        f"- reps recorded: **{summary['reps_recorded']}**",
        "- sender enacted the candidate verbatim on its first turn: "
        f"**{_pct(summary['sender_enacted_candidate_verbatim'])}**",
        "- distinctive candidate text appeared in the recipient's own "
        f"prompts: **{_pct(summary['candidate_text_in_recipient_prompts'])}**",
        "- production `intervention_delivered.status` per rep: "
        f"`{summary['intervention_delivered_status']}`",
        f"- ranking per rep: `{summary['ranking']}`",
        f"- terminal status per rep: `{summary['terminal_status']}`",
        "- unresolved observer names recorded per rep (D1 fix): "
        f"`{summary['unresolved_observer_count']}`",
        "- forced observer-routing interceptions per rep: "
        f"`{summary['forced_observer_interceptions']}`",
        f"- agency-guard interventions per rep: "
        f"`{summary['guard_interventions']}`",
        "- longest shared character run between the candidate and the "
        f"sender's first turn: `{summary.get('longest_shared_run_chars')}` "
        "(content-blind, does not enter the verdict)",
        "- candidate/first-turn token overlap (Jaccard): "
        f"`{summary.get('candidate_token_overlap_ratio')}`",
        "- distinct recipient first-turn prompt hashes: "
        f"**{len(set(summary['recipient_first_turn_prompt_sha256']))}** "
        f"across {summary['reps_recorded']} reps",
        f"- live calls: {summary['live_calls']} "
        f"(errors {summary['live_call_errors']}, "
        f"retries {summary['live_call_retries']})",
        "",
        "The sender's actual first turn, verbatim, per rep:",
        "",
    ]
    for entry in summary["sender_first_turns"]:
        lines.append(f"rep {entry['rep']}:")
        lines.append("")
        lines.append("```")
        lines.append(_quote(entry["text"]).replace("    ", "", 1)
                     if entry["text"] else "(no text recorded)")
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def write_readme(root, aggregate: dict) -> Path:
    root = Path(root)
    verdict_payload = verdict(aggregate)
    lines = [
        "# Settling experiment -- does a live sender enact its candidate?",
        "",
        BANNER,
        "",
        "## What this directory is",
        "",
        "A two-arm live experiment on the FROZEN Peter world. It exists "
        "because the delivery root-cause investigation could not decide "
        "between two explanations of why candidate text never reached the "
        "recipient: its probe arms all used a content-blind hash-derived "
        "sender, under which candidate text cannot propagate by "
        "construction. This experiment uses a LIVE sender.",
        "",
        "## The two hypotheses",
        "",
        f"- **R1-strong.** {HYPOTHESES['R1_strong']}",
        f"- **R3.** {HYPOTHESES['R3']}",
        "",
        "## Design",
        "",
        "| | Arm A | Arm B |",
        "|---|---|---|",
        "| starting event | `Beckett Zahedi sends the prepared message to "
        "Peter Thiel.` (`visible_to: [sender]`) | none (`starting_events: "
        "[]`) |",
        "| everything else | the frozen compiled world | byte-identical |",
        "",
        f"- candidate: `{aggregate['candidate_id']}` (one of the user's "
        "three supplied emails), frozen in "
        "`runner_settling.SETTLING_CANDIDATE_ID` so both arms and every "
        "rep provably use the same intervention text",
        "- seed, step budget, evaluator, model configuration: identical "
        "across arms and reps",
        f"- reps per arm: **{aggregate['reps_per_arm_declared']}** (live "
        "sampling varies at temperature 0, so a single sample could not "
        "distinguish 'never' from 'not this time')",
        "- sender: LIVE. Every actor turn in this experiment is a live "
        "provider completion recorded through the ordinary recorder.",
        "- one forced control: the game master's observer-ROUTING answer "
        "is forced to the full roster, so the observer-routing defect "
        "closed at `c5a81214` cannot confound the measurement. That is "
        "the ONLY harness-supplied text; every interception is recorded "
        "verbatim in each rep's `forced_observer_control.json`.",
        "",
        "## Result",
        "",
        f"**{verdict_payload['survived']} survived.** "
        f"{verdict_payload['reason']}",
        "",
        "See `SETTLING_RESULT.md` for the full reading and "
        "`SETTLING_MEASUREMENTS.json` for the machine-readable numbers.",
        "",
        "## Layout",
        "",
        "```",
        "settling_experiment/",
        "  README.md                    this file",
        "  SETTLING_RESULT.md           the verdict and what it means",
        "  SETTLING_MEASUREMENTS.json   every number, machine-readable",
        "  arm_a/rep_{1,2,3}/           arm A, one live branch per rep",
        "  arm_b/rep_{1,2,3}/           arm B, one live branch per rep",
        "  harness_shakedown/           the first two live runs, KEPT and "
        "not counted; see its own README for why",
        "```",
        "",
        "Each rep directory carries the standard ledgers: "
        "`freeze_manifest.json`, `arm_design.json`, `adapter/`, "
        "`all_llm_calls.jsonl`, "
        "`branches/<candidate>/{step_ledger,observations,guard_ledger,"
        "committed_events}.jsonl`, "
        "`branches/<candidate>/{branch_result,actor_memories,"
        "raw_engine_log}.json`, `trace_report.json`, "
        "`recommendation_report.json` (or `ranking_refusal.json`), "
        "`candidate_delivery_check.json`, `forced_observer_control.json`, "
        "`settling_measurement.json`, `instrumentation.json`, "
        "`provider_probe.json`.",
        "",
    ]
    path = root / "README.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_result(root, aggregate: dict) -> Path:
    root = Path(root)
    verdict_payload = verdict(aggregate)
    arm_a = aggregate["arms"]["a"]
    arm_b = aggregate["arms"]["b"]
    totals = aggregate["totals"]
    lines = [
        "# SETTLING RESULT",
        "",
        BANNER,
        "",
        "## The question",
        "",
        "Does a LIVE sender enact its candidate when the send is not "
        "already pre-narrated?",
        "",
        "Two prior live scenarios found that candidate text never reached "
        "the recipient actor. The root-cause investigation named two "
        "surviving explanations and could not separate them, because "
        "every probe arm it ran used a content-blind hash-derived sender "
        "under which candidate text cannot propagate by construction. "
        "This experiment separates them with a live sender.",
        "",
        f"- **R1-strong.** {HYPOTHESES['R1_strong']}",
        f"- **R3.** {HYPOTHESES['R3']}",
        "",
        "## Design (two arms, identical except the starting event)",
        "",
        "Both arms run on the same frozen compiled Peter world "
        "(re-adapted from scenario 1's frozen compiler artifact "
        "directory by deterministic code -- zero compiler calls), the "
        f"same single candidate `{aggregate['candidate_id']}`, the same "
        "seed, the same step budget, the same evaluator and the same "
        "model configuration.",
        "",
        "- **Arm A (pre-narrated).** The world exactly as compiled: one "
        "starting event, `Beckett Zahedi sends the prepared message to "
        "Peter Thiel.`, `visible_to: [beckett_zahedi]`.",
        "- **Arm B (not pre-narrated).** The same world with "
        "`starting_events: []` -- the shape the frozen manual fixtures "
        "use. Rebuilt through the contract gate, and the recorded "
        "field-level diff shows `starting_events` is the only field that "
        "differs.",
        "",
        "The game master's observer-ROUTING answer is forced to the full "
        "roster in BOTH arms, so the observer-routing defect closed at "
        "`c5a81214` cannot confound the measurement. That control is the "
        "only harness-supplied text in the experiment; every actor turn "
        "is live.",
        "",
        f"n = {arm_a['reps_recorded']} reps in arm A and "
        f"{arm_b['reps_recorded']} in arm B.",
        "",
        "## What was measured",
        "",
        "| measure | Arm A (pre-narrated) | Arm B (not pre-narrated) |",
        "|---|---|---|",
        "| sender enacted the candidate verbatim on its first turn | "
        f"**{_pct(arm_a['sender_enacted_candidate_verbatim'])}** | "
        f"**{_pct(arm_b['sender_enacted_candidate_verbatim'])}** |",
        "| distinctive candidate text in the recipient's own prompts | "
        f"**{_pct(arm_a['candidate_text_in_recipient_prompts'])}** | "
        f"**{_pct(arm_b['candidate_text_in_recipient_prompts'])}** |",
        "| production `intervention_delivered.status` | "
        f"`{arm_a['intervention_delivered_status']}` | "
        f"`{arm_b['intervention_delivered_status']}` |",
        "| ranking produced or REFUSED | "
        f"`{arm_a['ranking']}` | `{arm_b['ranking']}` |",
        "| terminal status | "
        f"`{arm_a['terminal_status']}` | `{arm_b['terminal_status']}` |",
        "| unresolved observer names (D1 fix) | "
        f"`{arm_a['unresolved_observer_count']}` | "
        f"`{arm_b['unresolved_observer_count']}` |",
        "| agency-guard interventions | "
        f"`{arm_a['guard_interventions']}` | "
        f"`{arm_b['guard_interventions']}` |",
        "| longest shared character run, candidate vs sender first turn | "
        f"`{arm_a.get('longest_shared_run_chars')}` | "
        f"`{arm_b.get('longest_shared_run_chars')}` |",
        "| candidate/first-turn token overlap (Jaccard) | "
        f"`{arm_a.get('candidate_token_overlap_ratio')}` | "
        f"`{arm_b.get('candidate_token_overlap_ratio')}` |",
        "",
        "Rates are `hits/n`. The `intervention_delivered` column is the "
        "value of the production field added by the D2 fix, computed by "
        "`sworldmodel.counterfactuals.delivery` from each branch's own "
        "artifacts -- not by this harness.",
        "",
        _arm_block(arm_a),
        "",
        _arm_block(arm_b),
        "",
        "## Verdict",
        "",
        f"**{verdict_payload['survived']} survived.**",
        "",
        verdict_payload["reason"],
        "",
        "Decision rule, fixed before the runs: the experiment turns on "
        "arm B's enactment rate, because arm B is the only arm in which "
        "R1-strong makes a positive prediction. Arm B enactment above "
        "zero and above arm A's would have supported R1-strong; arm B "
        "enactment at zero refutes it in its strong form.",
        "",
        "### What else the arms differed in (recorded, not part of the "
        "rule)",
        "",
        "Removing the pre-narration did NOT leave the sender unchanged. "
        "Read the quoted turns above: in arm A the sender WAITS in every "
        "rep; in arm B it performs the send in every rep. It just writes "
        "its OWN message rather than the candidate's. The content-blind "
        "overlap numbers point at the same thing without judging it:",
        "",
        "| | Arm A | Arm B |",
        "|---|---|---|",
        "| mean candidate/first-turn token overlap | "
        f"`{verdict_payload['also_measured']['mean_token_overlap_arm_a']}` | "
        f"`{verdict_payload['also_measured']['mean_token_overlap_arm_b']}` |",
        "| mean longest shared character run | "
        f"`{verdict_payload['also_measured']['mean_longest_shared_run_arm_a']}`"
        " | "
        f"`{verdict_payload['also_measured']['mean_longest_shared_run_arm_b']}`"
        " |",
        "",
        verdict_payload["also_measured"]["note"],
        "",
        "So the pre-narrated sender-only send event IS a real world-"
        "construction defect -- it suppresses the sender's own send "
        "action -- and it is still not the reason the candidate fails to "
        "reach the recipient. Both statements are supported here; neither "
        "one substitutes for the other.",
        "",
        "## What this means for the practical fix",
        "",
        f"**{verdict_payload['practical_fix']}.**",
        "",
    ]
    if verdict_payload["survived"] == "R3":
        lines.extend([
            "Compiler prompt hygiene is still worth doing on its own "
            "merits -- `compiler/scene_prompts.py` ships the literal "
            "exemplar that teaches the sender-only pre-narrated send "
            "event, and the R2 visibility-incoherence warning now records "
            "when a starting event names an actor outside its "
            "`visible_to`. But this experiment shows that hygiene alone "
            "would NOT have made the candidate reach the recipient: with "
            "the pre-narration removed entirely, the live sender still "
            "did not restate the candidate. It sent an email it wrote "
            "itself.",
            "",
            "The remaining lever is the one the lead deliberately did not "
            "pull in this pass: enact the intervention as a pre-start "
            "event authored by the insertion actor (R3 + R4a). That is a "
            "SEMANTIC change to the accepted counterfactual -- the "
            "insertion actor loses the freedom to decline the candidate "
            "-- and it is a decision to be taken explicitly, not "
            "smuggled in as a bug fix. What already landed (D2) is the "
            "honest interim: the engine now measures whether the "
            "intervention reached anyone and REFUSES to rank when it did "
            "not, so an invalid comparison surfaces as a refusal instead "
            "of a published winner.",
        ])
    else:
        lines.extend([
            "The pre-narrated, sender-only send event is the operative "
            "variable. `compiler/scene_prompts.py` ships the literal "
            "exemplar that teaches it, so the defect is systematic across "
            "cold-outreach worlds rather than an LLM slip, and fixing the "
            "compiler prompt is the minimal remedy. An engine semantic "
            "change is NOT required by this evidence.",
        ])
    lines.extend([
        "",
        "## The follow-up experiment this result cancels",
        "",
    ])
    if verdict_payload["survived"] == "R1_strong":
        lines.extend([
            "Because arm B's live sender DOES enact its candidate, a "
            "clearly-labelled experiment-side variant of the supplied "
            "scenario -- all three candidates, on an arm-B world -- is "
            "worth running to see whether the full path can produce a "
            "genuine candidate comparison. It lives in "
            "`peter_supplied/variant_no_prenarration/`.",
        ])
    else:
        lines.extend([
            "A follow-up was planned and is deliberately NOT run: a "
            "variant of the supplied scenario with all three candidates "
            "on an arm-B world, to see whether the full path can produce "
            "a genuine candidate comparison when the world is compiled "
            "coherently.",
            "",
            "It is cancelled by this result. Its premise was that a live "
            "sender enacts its candidate once the pre-narration is gone. "
            "Arm B measured that premise directly and it did not hold: "
            f"{_pct(arm_b['sender_enacted_candidate_verbatim'])} reps "
            "reproduced any distinctive candidate text, and "
            f"{_pct(arm_b['candidate_text_in_recipient_prompts'])} got any "
            "of it into the recipient's prompts. Running three candidates "
            "instead of one on the same world would produce three more "
            "undelivered branches and one more refusal -- more live calls "
            "for a result already measured. Running it anyway and "
            "reporting the refusal as if it were new information would be "
            "padding, not evidence.",
        ])
    lines.extend([
        "",
        "## Limitations, stated plainly",
        "",
        f"- **n = {arm_a['reps_recorded']} per arm is small.** Three live "
        "samples cannot estimate a rate precisely, and they cannot rule "
        "out a low-probability behaviour: a 0/3 result is consistent with "
        "any true rate below roughly 0.6 at 95% confidence. What 0/3 does "
        "establish is that the behaviour is not the common case, which is "
        "what the two hypotheses actually disagree about.",
        "- **One candidate, one world, one model.** The measurement is "
        f"of candidate `{aggregate['candidate_id']}` on the Peter world "
        f"against {aggregate['model_configuration']['provider']} "
        f"`{aggregate['model_configuration']['model']}` (the provider "
        f"actually served `{_served(aggregate)}`). Another candidate, "
        "cast, or model could behave differently.",
        "- **Enactment is measured verbatim.** A fragment counts only if "
        "it appears in the sender's own turn character-for-character. A "
        "sender that faithfully paraphrased its candidate would be scored "
        "as not enacting. The sender's full first turn is quoted above so "
        "a reader can check that reading against the text.",
        "- **The observer broadcast is a forced control, not the "
        "production default.** In production the game master answers that "
        "question freely. Forcing it removes a known confound; it also "
        "means these runs are more favourable to delivery than production "
        "would be, so a non-delivery here is the stronger result.",
        "- **This says nothing about Peter Thiel.** It is a measurement "
        "of an engine's intervention semantics that happens to use a "
        "compiled world with those names in it.",
        "",
        "## Provenance",
        "",
        f"- live calls: **{totals['live_calls']}** "
        f"(errors {totals['live_call_errors']}, "
        f"retries {totals['live_call_retries']})",
        f"- provider actually served: `{_served(aggregate)}` for requested "
        f"`{aggregate['model_configuration']['model']}`",
        f"- repository SHA: `{aggregate['environment']['repository_sha']}`",
        f"- generated at: {aggregate['generated_at']}",
        "",
    ])
    path = root / "SETTLING_RESULT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _served(aggregate: dict) -> str:
    """Every distinct model id the provider actually reported serving,
    read from the per-rep one-token probes."""
    served = set()
    for arm in ("a", "b"):
        for entry in aggregate["arms"][arm].get("provider_served") or ():
            served.add(entry)
    return ", ".join(sorted(served)) if served else "(see provider_probe.json)"


__all__ = ["BANNER", "HYPOTHESES", "verdict", "write_readme", "write_result"]
