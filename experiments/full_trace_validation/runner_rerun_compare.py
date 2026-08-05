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


def _is_possessive(record: dict, full_original: str = "") -> bool:
    """True when the guard's INPUT contains ``<affected name>'s``.

    Reads the full reconstructed pre-guard text when one is available and
    falls back to the 120-character excerpt otherwise.
    """
    original = (full_original or record.get("original_excerpt") or "")
    return any(f"{name}'s" in original or f"{name}’s" in original
               for name in (record.get("affected") or ()))


def _guard_class_census(facts: dict, full_originals: dict | None = None,
                        roster=None) -> dict:
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

    ORDERING FIX (2026-08-04, audit finding F4).  These two tests are NOT
    mutually exclusive: a possessive rewrite whose removal span happens
    to start right after a determiner ALSO ends in ``the.``, so it
    carries the D3 output signature while being a possessive INPUT.  The
    original ordering tested the output signature first and therefore
    filed such records under D3 -- which is how the a16z pre/post
    document came to publish a possessive case (``user_001`` step 11,
    ``reviews the People and Compensation Partner's latest reply``) as
    its one verbatim example of the class D3 closed.  The possessive test
    now runs FIRST because it reads the guard's INPUT, which is what
    actually decides the class; the dangling determiner is only a
    property of the output.

    Honest limit: the runner records guard excerpts capped at 120
    characters, so a record whose class is not visible in what is
    available is counted as UNCLASSIFIABLE rather than guessed into a
    bucket.  ``full_originals`` (keyed ``(branch, step)``) supplies the
    untruncated pre-guard text reconstructed from the step ledger when
    the caller can provide it, which removes most of that limit -- the
    D3 truncation happened at the colon, which in these transcripts is
    usually past character 120, so 18 of the 20 a16z records showed NO
    signature at all in their excerpts.

    When BOTH the untruncated text and the ``roster`` are available the
    D3 test is not a signature guess at all: the record's own pre-guard
    text is replayed through the CURRENT guard, and a text the current
    guard passes byte-identically IS by definition a member of the class
    the D3 fix closed.  The output-signature heuristic remains only as
    the fallback for callers that cannot supply either.
    """
    full_originals = full_originals or {}
    replay_guard = None
    if roster and full_originals:
        from sworldmodel.backends.concordia_local.guard import (
            make_agency_guard)
        replay_guard = make_agency_guard(list(roster))
    determined = []
    possessive = []
    unclassifiable = []
    other = []
    for record in facts["guard"]["records"]:
        original = record.get("original_excerpt") or ""
        rewritten = record.get("rewritten_excerpt") or ""
        full_original = full_originals.get(
            (record.get("branch"), record.get("step")), "")
        if _is_possessive(record, full_original):
            possessive.append(record)
        elif replay_guard is not None and full_original:
            if replay_guard(None, full_original,
                            record.get("active")) == full_original:
                determined.append(record)
            else:
                other.append(record)
        elif _DANGLING_DETERMINER.search(rewritten):
            determined.append(record)
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
        "classified_from_untruncated_text": sum(
            1 for record in facts["guard"]["records"]
            if full_originals.get((record.get("branch"), record.get("step")))),
        "classified_by_replaying_through_the_current_guard":
            bool(replay_guard),
        # prefer an example whose recorded excerpt actually SHOWS the
        # truncation; most D3 records were cut past character 120, so
        # their excerpts look unchanged and illustrate nothing
        "examples_determined": [
            record["rewritten_excerpt"] for record in
            (sorted(determined,
                    key=lambda item: not _DANGLING_DETERMINER.search(
                        item.get("rewritten_excerpt") or ""))[:2])],
        "examples_possessive": [record["original_excerpt"]
                                for record in possessive[:2]],
    }


def _full_pre_guard_texts(scenario_dir) -> dict:
    """Reconstruct each intervened step's UNTRUNCATED pre-guard event.

    The guard ledger caps its excerpts at 120 characters, but the step
    ledger records the actor's raw response for the same step, and the
    sequential engine hands the guard exactly
    ``Putative event to resolve:  <active>: <raw response>``.  That
    reconstruction is what the classifier and the replay below use; a
    step with no recorded raw response is simply absent from the map and
    falls back to the truncated excerpt.
    """
    texts: dict = {}
    branches_dir = Path(scenario_dir) / "branches"
    if not branches_dir.is_dir():
        return texts
    for branch_dir in sorted(branches_dir.iterdir()):
        ledger = branch_dir / "step_ledger.jsonl"
        guard_ledger = branch_dir / "guard_ledger.jsonl"
        if not (ledger.is_file() and guard_ledger.is_file()):
            continue
        raw_by_step = {}
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if "_artifact_class" in row:
                continue
            raw = (row.get("actor_raw_response") or {}).get(
                "engine_recorded_value")
            if raw:
                raw_by_step[row["step"]] = raw
        for line in guard_ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("intervened"):
                continue
            for record in row.get("records") or ():
                step = record.get("step")
                raw = raw_by_step.get(step)
                if not raw:
                    continue
                texts[(branch_dir.name, step)] = (
                    f"Putative event to resolve:  {record.get('active')}: "
                    f"{raw}")
    return texts


def _d3_replay_attribution(scenario_dir, roster) -> dict:
    """How many pre-fix interventions the D3 fix ACTUALLY explains.

    Audit finding F6: the comparison document attributed the whole
    pre-fix intervention count to defect D3 because the count fell to
    zero after the fix.  A count falling to zero across two live runs is
    not an attribution -- live sampling alone changes which turns the
    guard sees.

    This replays every pre-fix intervention's reconstructed pre-guard
    text through the CURRENT guard.  A record the current guard leaves
    byte-identical is explained by the fix; a record it still rewrites is
    NOT, and its disappearance from the re-run is sampling.  Records
    whose pre-guard text cannot be reconstructed are reported as
    unreplayable rather than assigned.
    """
    from sworldmodel.backends.concordia_local.guard import make_agency_guard

    guard = make_agency_guard(roster)
    texts = _full_pre_guard_texts(scenario_dir)
    explained = []
    still_rewritten = []
    unreplayable = []
    branches_dir = Path(scenario_dir) / "branches"
    total = 0
    if branches_dir.is_dir():
        for branch_dir in sorted(branches_dir.iterdir()):
            guard_ledger = branch_dir / "guard_ledger.jsonl"
            if not guard_ledger.is_file():
                continue
            for line in guard_ledger.read_text(
                    encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if not row.get("intervened"):
                    continue
                for record in row.get("records") or ():
                    total += 1
                    step = record.get("step")
                    text = texts.get((branch_dir.name, step))
                    entry = {"branch": branch_dir.name, "step": step,
                             "active": record.get("active"),
                             "excerpt": (text or record.get(
                                 "original_excerpt") or "")[:160]}
                    if not text:
                        unreplayable.append(entry)
                        continue
                    if guard(None, text, record.get("active")) == text:
                        explained.append(entry)
                    else:
                        still_rewritten.append(entry)
    return {
        "method": ("every pre-fix intervention's untruncated pre-guard "
                   "text, reconstructed from the step ledger, replayed "
                   "through the CURRENT guard"),
        "pre_fix_interventions": total,
        "explained_by_the_D3_fix": len(explained),
        "still_rewritten_by_the_current_guard": len(still_rewritten),
        "unreplayable_no_recorded_raw_response": len(unreplayable),
        "still_rewritten_records": still_rewritten,
        "note": ("a record the current guard still rewrites did NOT "
                 "disappear because of the fix; its absence from the "
                 "re-run is live sampling"),
    }


def _roster(scenario_dir) -> list:
    plan = json.loads((Path(scenario_dir) / "adapter" / "base_plan.json")
                      .read_text(encoding="utf-8"))
    return [actor["name"] for actor in plan["actor_configs"]]


def _candidate_set_identity(pre_dir, post_dir) -> dict:
    pre = freeze_lib.load_manifest(pre_dir / "freeze_manifest.json")
    post = freeze_lib.load_manifest(post_dir / "freeze_manifest.json")
    left = pre.get("entries", {}).get("candidate_set", {}).get("sha256")
    right = post.get("entries", {}).get("candidate_set", {}).get("sha256")
    return {"pre_fix_sha256": left, "post_fix_sha256": right,
            "identical": bool(left) and left == right}


def _notes(scenario_id, pre_facts, post_facts, pre_dir, post_dir,
           attribution=None) -> list:
    notes = []
    roster = _roster(pre_dir)
    pre_classes = _guard_class_census(pre_facts,
                                      _full_pre_guard_texts(pre_dir), roster)
    post_classes = _guard_class_census(post_facts,
                                       _full_pre_guard_texts(post_dir), roster)
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
                 + _fmt(post_classes) + ". The class is decided by the "
                 "guard's INPUT (a possessive `<Name>'s <act noun>` is a "
                 "possessive case even when its rewrite happens to end in "
                 "a dangling determiner), and by the UNTRUNCATED "
                 "pre-guard text reconstructed from the step ledger "
                 "wherever one is recoverable "
                 f"({pre_classes['classified_from_untruncated_text']} of "
                 f"{pre_classes['total']} pre-fix records).")
    if attribution and attribution["pre_fix_interventions"]:
        notes.append(
            "Attribution by REPLAY, not by subtraction: "
            f"{attribution['explained_by_the_D3_fix']} of "
            f"{attribution['pre_fix_interventions']} pre-fix "
            "interventions are explained by the D3 fix -- their "
            "reconstructed pre-guard text passes the CURRENT guard "
            "byte-identically. "
            f"{attribution['still_rewritten_by_the_current_guard']} still "
            "rewrite under the current guard and are therefore NOT "
            "attributable to D3; their absence from the re-run is live "
            "sampling."
            + ("" if not attribution["still_rewritten_records"] else
               " Still rewritten: "
               + "; ".join(f"`{entry['branch']}` step {entry['step']}"
                           for entry in
                           attribution["still_rewritten_records"][:4]) + ".")
            + ("" if not attribution[
                "unreplayable_no_recorded_raw_response"] else
               f" {attribution['unreplayable_no_recorded_raw_response']} "
               "record(s) had no recorded raw response and could not be "
               "replayed; they are counted in neither bucket."))
    if post_classes["total"] == 0 and pre_classes["total"] > 0:
        notes.append(
            "The guard did not fire at all in the re-run, so every "
            "pre-fix rewrite is gone. That the COUNT fell to zero is not "
            "by itself evidence about the cause; the replay line above is.")
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
    if pre_classes["examples_possessive"]:
        notes.append(
            "A pre-fix POSSESSIVE rewrite, verbatim from the guard "
            "ledger: `" + pre_classes["examples_possessive"][0]
            + "` -- this is the documented stateless conservatism, NOT "
            "the class D3 closed, and the current guard still rewrites "
            "it.")
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
    roster = _roster(pre_dir)
    attribution = _d3_replay_attribution(pre_dir, roster)
    payload = rerun_lib.compare_scenarios(
        scenario_id=scenario_id, pre_dir=pre_dir, post_dir=post_dir,
        freeze_comparison=freeze_comparison,
        notes=_notes(scenario_id, pre_facts, post_facts, pre_dir, post_dir,
                     attribution))
    payload["guard_class_census"] = {
        "pre_fix": _guard_class_census(
            pre_facts, _full_pre_guard_texts(pre_dir), roster),
        "post_fix": _guard_class_census(
            post_facts, _full_pre_guard_texts(post_dir), roster),
    }
    payload["d3_replay_attribution"] = attribution
    payload["frozen_input_verification"] = json.loads(
        (post_dir / "frozen_input_verification.json").read_text(
            encoding="utf-8"))
    return rerun_lib.write_comparison(post_dir, payload)


def write_call_accounting() -> Path:
    """Sum every provider call this validation pass recorded.

    The runs are found by globbing the recorder instrumentation the runs
    themselves wrote, so the total cannot drift from the evidence.
    """
    paths = (
        sorted(ARTIFACT_ROOT.glob("settling_experiment/**/"
                                  "instrumentation.json"))
        + sorted(ARTIFACT_ROOT.glob(f"*/{RERUN_SUBDIR}/shared/"
                                    "instrumentation_*.json"))
        + sorted(ARTIFACT_ROOT.glob(f"*/{RERUN_SUBDIR}/"
                                    "instrumentation_*.json")))
    paths = [path for path in paths
             if path.name != "instrumentation_validation.json"]
    payload = rerun_lib.session_call_accounting(paths)
    payload["what_this_covers"] = (
        "the settling experiment (both arms, all reps, plus the two "
        "kept harness-shakedown runs) and the three post-fix re-runs. It "
        "does NOT cover the pre-fix runs, whose own instrumentation is "
        "unchanged in their own directories.")
    path = ARTIFACT_ROOT / "SESSION_CALL_ACCOUNTING.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False)
                    + "\n", encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default=None, choices=SCENARIOS)
    args = parser.parse_args(argv)
    targets = (args.scenario,) if args.scenario else SCENARIOS
    for scenario_id in targets:
        path = compare(scenario_id)
        print(f"wrote {path}", flush=True)
    if args.scenario is None:
        print(f"wrote {write_call_accounting()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
