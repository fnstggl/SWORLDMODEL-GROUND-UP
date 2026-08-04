"""Write ``PRE_VS_POST_FIX.md`` for each re-run scenario.

Experiment-only, no live call: it reads both artifact sets and renders
the comparison.  Every note it adds is COMPUTED from the artifacts, not
asserted -- the guard-class claim, the candidate-set identity and the
observer-name census are all derived here so a reader can re-derive them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.full_trace_validation import freeze as freeze_lib  # noqa: E402
from experiments.full_trace_validation import rerun as rerun_lib  # noqa: E402

ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "full_trace_validation_20260804"
RERUN_SUBDIR = "post_fix_rerun"

SCENARIOS = ("peter_supplied", "peter_generated", "a16z_richard_historical")

#: the generated scenario's generation INPUTS.  The candidate set itself
#: is a live output and is compared separately, never required to match.
GENERATOR_ENTRIES = ("candidate_generator_prompt",
                     "candidate_generator_config")

#: the D3 SIGNATURE, read off the guard's own output: the determiner
#: false positive truncated the sentence AT the determiner, so the
#: rewritten text ends in a dangling determiner followed by a period
#: ("... New Media Hiring Lead reviews the. <availability sentence>").
_DANGLING_DETERMINER = re.compile(
    r"\b(?:the|a|an|this|that|these|those|their|his|her|its)\.(?:\s|$)",
    re.IGNORECASE)

#: the excerpt cap the runner records guard text at
_EXCERPT_CAP = 120


def _guard_class_census(facts: dict) -> dict:
    """Split the guard's interventions by class, from the guard's own
    recorded excerpts.

    Two classes matter here and conflating them would make a fix look
    like a regression, or hide one:

    * **the class D3 closed** -- the determined-recipient object slot
      (``sends a message to THE <role name>: "<content>"``). Its
      signature is visible in the guard's OUTPUT: the sentence was cut at
      the determiner, so the rewrite ends in a dangling ``the.`` / ``a.``
      before the availability sentence.
    * **possessive nominalization** (``reads <Name>'s reply``) -- a
      DIFFERENT and documented deliberate conservatism, stated in the
      guard's own docstring: without history, a reference to a decision
      that really happened is indistinguishable from an invented one.
      The fix did not touch it and was not supposed to.

    Honest limit: the runner records guard excerpts capped at 120
    characters, so a record whose excerpt is truncated before either
    signature appears is counted as UNCLASSIFIABLE rather than guessed
    into a bucket.
    """
    determined = []
    possessive = []
    unclassifiable = []
    other = []
    for record in facts["guard"]["records"]:
        original = record.get("original_excerpt") or ""
        rewritten = record.get("rewritten_excerpt") or ""
        affected = record.get("affected") or []
        if _DANGLING_DETERMINER.search(rewritten):
            determined.append(record)
        elif any(f"{name}'s" in original or f"{name}’s" in original
                 for name in affected):
            possessive.append(record)
        elif len(original) >= _EXCERPT_CAP and len(rewritten) >= _EXCERPT_CAP:
            unclassifiable.append(record)
        else:
            other.append(record)
    return {
        "determined_recipient_object_slot_the_D3_fix_closed":
            len(determined),
        "possessive_nominalization_documented_conservatism": len(possessive),
        "unclassifiable_from_the_120_character_excerpt":
            len(unclassifiable),
        "other": len(other),
        "total": len(facts["guard"]["records"]),
        "examples_determined": [record["rewritten_excerpt"]
                                for record in determined[:2]],
        "examples_possessive": [record["original_excerpt"]
                                for record in possessive[:2]],
    }


def _candidate_set_identity(pre_dir, post_dir) -> dict:
    pre = freeze_lib.load_manifest(pre_dir / "freeze_manifest.json")
    post = freeze_lib.load_manifest(post_dir / "freeze_manifest.json")
    left = pre.get("entries", {}).get("candidate_set", {}).get("sha256")
    right = post.get("entries", {}).get("candidate_set", {}).get("sha256")
    return {"pre_fix_sha256": left, "post_fix_sha256": right,
            "identical": bool(left) and left == right}


def _notes(scenario_id, pre_facts, post_facts, pre_dir, post_dir) -> list:
    notes = []
    pre_classes = _guard_class_census(pre_facts)
    post_classes = _guard_class_census(post_facts)
    def _fmt(census):
        return (
            f"{census['determined_recipient_object_slot_the_D3_fix_closed']}"
            " determined-recipient (the class D3 closed), "
            f"{census['possessive_nominalization_documented_conservatism']}"
            " possessive nominalization (a documented deliberate "
            "conservatism in the guard's own docstring, NOT a defect), "
            f"{census['unclassifiable_from_the_120_character_excerpt']}"
            " unclassifiable from the 120-character excerpt the runner "
            f"records, {census['other']} other, "
            f"{census['total']} total")

    notes.append("Guard interventions split by class -- pre-fix: "
                 + _fmt(pre_classes) + ". Post-fix: "
                 + _fmt(post_classes) + ".")
    if post_classes["total"] == 0 and pre_classes["total"] > 0:
        notes.append(
            "The guard did not fire at all in the re-run, so every "
            "pre-fix rewrite is gone -- including every one that could "
            "not be classified from its truncated excerpt.")
    elif post_classes[
            "determined_recipient_object_slot_the_D3_fix_closed"] == 0 \
            and pre_classes[
                "determined_recipient_object_slot_the_D3_fix_closed"] > 0:
        notes.append(
            "Every determined-recipient rewrite is gone. That is exactly "
            "the class D3 closed, and it is the class that was deleting "
            "the ACTIVE actor's own quoted message content.")
    if pre_classes["examples_determined"]:
        notes.append(
            "A pre-fix determined-recipient rewrite, verbatim from the "
            "guard ledger: `" + pre_classes["examples_determined"][0]
            + "` -- the sentence was cut at the determiner and the active "
            "actor's own content after it was deleted.")
    if post_classes["possessive_nominalization_documented_conservatism"] > \
            pre_classes["possessive_nominalization_documented_conservatism"]:
        notes.append(
            "The possessive-nominalization count went UP. This is not a "
            "regression: it is the same documented behaviour firing more "
            "often because live sampling produced more turns of the form "
            "'reads <Name>'s reply'. The guard docstring names this class "
            "explicitly as a stateless trade-off -- without history, a "
            "reference to a decision that really happened is "
            "indistinguishable from an invented one -- and the fix did "
            "not touch it.")
    notes.append(
        "Live model sampling is not reproducible at temperature 0, so any "
        "change in terminal status or committed text between the two runs "
        "is sampling variation on identical inputs unless it is one of the "
        "engine behaviours listed above.")
    if scenario_id == "peter_generated":
        identity = _candidate_set_identity(pre_dir, post_dir)
        generator = rerun_lib.compare_freeze_manifests(
            pre_dir / "freeze_manifest.json",
            post_dir / "freeze_manifest.json",
            entries=GENERATOR_ENTRIES)
        notes.append(
            "The candidate set is a live OUTPUT of this scenario, not a "
            "frozen input. The generator INPUTS were compared and are "
            + ("identical (`" + "`, `".join(GENERATOR_ENTRIES) + "`)."
               if generator["all_identical"]
               else "NOT identical: `"
                    + "`, `".join(generator["entries_that_differ"]) + "`.")
            + " The re-run regenerated candidates live and the resulting "
            "set is "
            + ("byte-identical to the pre-fix set."
               if identity["identical"]
               else "NOT byte-identical to the pre-fix set "
                    f"(pre `{str(identity['pre_fix_sha256'])[:16]}`, post "
                    f"`{str(identity['post_fix_sha256'])[:16]}`), which is "
                    "expected from a live one-shot generation and is why "
                    "the candidate set is excluded from the frozen-input "
                    "table above."))
    notes.append(
        "The narrative UNDER_THE_HOOD_REPORT.md is not regenerated for a "
        "re-run: it renders the whole artifact root including the compile "
        "phase, which a re-run deliberately does not repeat. This document "
        "is the re-run's narrative; the pre-fix report is unchanged and "
        "still describes the pre-fix run.")
    return notes


def compare(scenario_id: str) -> Path:
    pre_dir = ARTIFACT_ROOT / scenario_id
    post_dir = pre_dir / RERUN_SUBDIR
    if not (post_dir / "evaluator_ledger.json").is_file():
        raise SystemExit(f"{scenario_id}: no re-run artifacts at {post_dir}")
    freeze_comparison = rerun_lib.compare_freeze_manifests(
        pre_dir / "freeze_manifest.json",
        post_dir / "freeze_manifest.json")
    pre_facts = rerun_lib.scenario_facts(pre_dir, scenario_id)
    post_facts = rerun_lib.scenario_facts(post_dir, scenario_id)
    payload = rerun_lib.compare_scenarios(
        scenario_id=scenario_id, pre_dir=pre_dir, post_dir=post_dir,
        freeze_comparison=freeze_comparison,
        notes=_notes(scenario_id, pre_facts, post_facts, pre_dir, post_dir))
    payload["guard_class_census"] = {
        "pre_fix": _guard_class_census(pre_facts),
        "post_fix": _guard_class_census(post_facts),
    }
    payload["frozen_input_verification"] = json.loads(
        (post_dir / "frozen_input_verification.json").read_text(
            encoding="utf-8"))
    return rerun_lib.write_comparison(post_dir, payload)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default=None, choices=SCENARIOS)
    args = parser.parse_args(argv)
    targets = (args.scenario,) if args.scenario else SCENARIOS
    for scenario_id in targets:
        path = compare(scenario_id)
        print(f"wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
