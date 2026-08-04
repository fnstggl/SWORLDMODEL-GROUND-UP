"""Prove the salary branches differ in the salary and in NOTHING else.

Experiment-only.  The a16z contract requires that title, role scope,
reporting line, benefits, equity treatment, creative autonomy, resources
and start expectations stay constant across every salary branch, and that
ONLY annual base salary differs.  A promise is not proof, so this module
computes the proof from the actual frozen objects:

1. the candidate ACTION texts of the five offer branches, with every
   currency figure replaced by one placeholder, must be byte-identical;
2. the derived candidate SUMMARY texts, masked the same way, must be
   byte-identical;
3. every branch PLAN's canonical dict must differ from the base plan only
   under ``initial_observations.<insertion actor>`` (the engine's own
   isolation invariant, re-derived here independently);
4. the five offer branches' plans, masked the same way, must be
   byte-identical to each other -- so the only surviving difference in
   the whole simulation input is the salary figure.

The no-offer baseline is reported alongside but deliberately excluded
from (1), (2) and (4): it is a different action by construction, which is
what makes it the baseline.

Nothing is rewritten.  A difference outside the salary is reported with
its exact path and both values.
"""

from __future__ import annotations

import hashlib
import json
import re

#: currency figures in the forms the declared candidates use
SALARY_TOKEN_RE = re.compile(
    r"\$\s?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$\s?\d+(?:\.\d+)?\s?[kKmM]\b"
    r"|\$\s?\d+(?:\.\d+)?\b")

SALARY_PLACEHOLDER = "$<ANNUAL_BASE_SALARY>"


def mask_salaries(text: str) -> str:
    """Every currency figure replaced by one placeholder."""
    return SALARY_TOKEN_RE.sub(SALARY_PLACEHOLDER, text or "")


def mask_structure(value):
    """``mask_salaries`` applied to every string anywhere in a JSON tree."""
    if isinstance(value, str):
        return mask_salaries(value)
    if isinstance(value, dict):
        return {key: mask_structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_structure(item) for item in value]
    return value


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _sha(value) -> str:
    text = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _diff_paths(left, right, path="", changed=None):
    """Every leaf path where two JSON trees differ (type-strict)."""
    if changed is None:
        changed = []
    if type(left) is not type(right):
        changed.append(path)
        return changed
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            key_path = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                changed.append(key_path)
            else:
                _diff_paths(left[key], right[key], key_path, changed)
        return changed
    if isinstance(left, list):
        for index in range(max(len(left), len(right))):
            item_path = f"{path}[{index}]"
            if index >= len(left) or index >= len(right):
                changed.append(item_path)
            else:
                _diff_paths(left[index], right[index], item_path, changed)
        return changed
    if left != right:
        changed.append(path)
    return changed


def _at_path(tree, path):
    node = tree
    for token in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if token.startswith("["):
            index = int(token[1:-1])
            if not isinstance(node, list) or index >= len(node):
                return None
            node = node[index]
        else:
            if not isinstance(node, dict) or token not in node:
                return None
            node = node[token]
    return node


def build_branch_input_diff(*, base_plan_dict, branch_plan_dicts,
                            candidates_by_id, offer_candidate_ids,
                            baseline_candidate_id,
                            insertion_actor_id,
                            declared_salary_by_candidate_id) -> dict:
    """The complete branch-input isolation proof (see module docstring).

    ``branch_plan_dicts`` maps candidate_id to that branch's plan as a
    plain dict; ``candidates_by_id`` maps candidate_id to the candidate
    contract dict.
    """
    prefix = f"initial_observations.{insertion_actor_id}"
    per_branch: list = []
    for candidate_id, plan in branch_plan_dicts.items():
        candidate = candidates_by_id[candidate_id]
        changed = _diff_paths(base_plan_dict, plan)
        stray = [path for path in changed
                 if path != prefix and not path.startswith(prefix + "[")]
        inserted = [_at_path(plan, path) for path in changed
                    if path.startswith(prefix + "[")]
        per_branch.append({
            "candidate_id": candidate_id,
            "declared_salary": declared_salary_by_candidate_id.get(
                candidate_id),
            "candidate_action": candidate["action"],
            "candidate_action_masked": mask_salaries(candidate["action"]),
            "candidate_summary": candidate["summary"],
            "candidate_summary_masked": mask_salaries(candidate["summary"]),
            "plan_paths_changed_vs_base": changed,
            "plan_paths_outside_the_insertion_boundary": stray,
            "inserted_observation_lines": inserted,
            "plan_sha256": _sha(plan),
            "plan_sha256_salary_masked": _sha(mask_structure(plan)),
        })

    offers = [entry for entry in per_branch
              if entry["candidate_id"] in set(offer_candidate_ids)]
    masked_action_hashes = {entry["candidate_id"]:
                            _sha(entry["candidate_action_masked"])
                            for entry in offers}
    masked_summary_hashes = {entry["candidate_id"]:
                             _sha(entry["candidate_summary_masked"])
                             for entry in offers}
    masked_plan_hashes = {entry["candidate_id"]:
                          entry["plan_sha256_salary_masked"]
                          for entry in offers}
    unmasked_plan_hashes = {entry["candidate_id"]: entry["plan_sha256"]
                            for entry in per_branch}

    residual_differences: list = []
    if offers:
        reference = offers[0]
        reference_masked_plan = mask_structure(
            branch_plan_dicts[reference["candidate_id"]])
        for entry in offers[1:]:
            other = mask_structure(branch_plan_dicts[entry["candidate_id"]])
            for path in _diff_paths(reference_masked_plan, other):
                residual_differences.append({
                    "left_candidate_id": reference["candidate_id"],
                    "right_candidate_id": entry["candidate_id"],
                    "path": path,
                    "left_value": _at_path(reference_masked_plan, path),
                    "right_value": _at_path(other, path)})

    all_actions_equal = len(set(masked_action_hashes.values())) <= 1
    all_summaries_equal = len(set(masked_summary_hashes.values())) <= 1
    all_plans_equal = len(set(masked_plan_hashes.values())) <= 1
    no_stray = all(not entry["plan_paths_outside_the_insertion_boundary"]
                   for entry in per_branch)
    all_plans_distinct_unmasked = (
        len(set(unmasked_plan_hashes.values())) == len(unmasked_plan_hashes))

    isolated = bool(all_actions_equal and all_summaries_equal
                    and all_plans_equal and no_stray
                    and not residual_differences)
    return {
        "claim": ("across the five offer branches the ONLY difference in "
                  "the simulation input is the annual base salary figure"),
        "method": {
            "salary_mask": SALARY_TOKEN_RE.pattern,
            "placeholder": SALARY_PLACEHOLDER,
            "steps": [
                "mask every currency figure in the candidate action and "
                "summary, then compare sha256",
                "diff every branch plan against the base plan and require "
                "every changed path to sit under "
                f"{prefix!r}",
                "mask every string in every branch plan, then compare the "
                "five offer branches' canonical plans byte for byte",
            ],
        },
        "insertion_boundary": prefix,
        "baseline_candidate_id": baseline_candidate_id,
        "offer_candidate_ids": list(offer_candidate_ids),
        "per_branch": per_branch,
        "masked_candidate_action_sha256": masked_action_hashes,
        "masked_candidate_summary_sha256": masked_summary_hashes,
        "masked_branch_plan_sha256": masked_plan_hashes,
        "unmasked_branch_plan_sha256": unmasked_plan_hashes,
        "residual_differences_after_masking": residual_differences,
        "checks": {
            "masked_candidate_actions_identical": all_actions_equal,
            "masked_candidate_summaries_identical": all_summaries_equal,
            "masked_branch_plans_identical": all_plans_equal,
            "no_plan_change_outside_the_insertion_boundary": no_stray,
            "every_branch_plan_distinct_before_masking":
                all_plans_distinct_unmasked,
        },
        "verdict": ("only_the_salary_differs" if isolated
                    else "OTHER_DIFFERENCES_FOUND"),
        "note": ("the no-offer baseline is excluded from the identity "
                 "checks by construction: it declares a different action, "
                 "which is what makes it the baseline. Its plan diff is "
                 "reported above alongside the offer branches."),
    }
