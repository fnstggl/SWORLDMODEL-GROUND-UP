"""Did the OFFER actually reach Richard Zheng's actor?

Experiment-only.  The Peter runs' headline finding was that the candidate
text never reached the recipient actor: the recipient's first-turn prompt
was byte-identical across every branch, so the branch comparison was
measuring live-model sampling variation on one identical prompt rather
than a difference between candidates.  This scenario asks the SAME
question of the salary offers, and answers it mechanically from the
recorded artifacts before any ranking is allowed to mean anything.

Three checks per branch, on top of the generic ones in :mod:`delivery`:

``salary token``
    Does this branch's own declared salary figure appear in a prompt
    actually sent to the subject's model?  Both the comma form
    (``$150,000``) and the plain digit form (``150000``, ``150k``) are
    tested, because a live model may restate a figure either way.
``contamination baseline``
    Does the same figure ALSO appear in the no-offer baseline branch's
    subject prompts, or in the compiled world's static context?  If it
    does, a hit is not evidence of delivery -- it was already there.  The
    ``$100,000 per video shoot`` evidence item makes this a real risk for
    the ``$100,000`` branch, so the check is computed, not assumed.
``world reach``
    Does the figure appear anywhere in the branch's committed event
    stream, or in the observations the engine delivered to the subject?
    A figure that reached the world but not the subject's prompt is a
    different failure from one that never existed at all.

Nothing here changes a metric.  It decides what a metric is allowed to
mean.
"""

from __future__ import annotations

import hashlib
import re

from .delivery import (candidate_fragments, check_branch,  # noqa: F401
                       normalise, private_context_leak_check,
                       recipient_prompts)


def _sha(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def salary_variants(token) -> tuple:
    """Every surface form of one declared salary figure.

    ``$150,000`` -> ``$150,000``, ``150,000``, ``150000``, ``150k``,
    ``$150k``, ``150 thousand``.
    """
    if not token:
        return ()
    digits = re.sub(r"[^\d]", "", token)
    if not digits:
        return ()
    amount = int(digits)
    forms = {token, token.replace("$", ""), digits}
    if amount % 1000 == 0:
        thousands = amount // 1000
        forms.update({f"{thousands}k", f"{thousands}K", f"${thousands}k",
                      f"${thousands}K", f"{thousands} thousand"})
    return tuple(sorted(forms, key=len, reverse=True))


def _hits(variants, haystack) -> list:
    return [variant for variant in variants if variant in haystack]


def observations_delivered_to(step_ledger_rows, subject_name) -> list:
    """Every observation text the engine handed the subject, per step."""
    delivered = []
    for record in step_ledger_rows:
        payload = (record.get("observations_delivered") or {}).get(
            subject_name)
        if not isinstance(payload, dict):
            continue
        text = payload.get("delivered_text") or ""
        if text:
            delivered.append({"step": record.get("step"), "text": text})
    return delivered


def check_offer_branch(*, candidate_id, candidate_action, subject_name,
                       step_ledger_rows, committed_texts, declared_salary,
                       baseline_prompt_text, static_world_text) -> dict:
    """One branch's offer-delivery record."""
    generic = check_branch(candidate_id=candidate_id,
                           candidate_action=candidate_action,
                           recipient_name=subject_name,
                           step_ledger_rows=step_ledger_rows)
    prompts = recipient_prompts(step_ledger_rows, subject_name)
    joined_prompts = " ".join(normalise(entry["prompt"])
                              for entry in prompts)
    observations = observations_delivered_to(step_ledger_rows, subject_name)
    joined_observations = " ".join(normalise(entry["text"])
                                   for entry in observations)
    joined_committed = " ".join(normalise(text) for text in committed_texts)

    variants = salary_variants(declared_salary)
    in_prompts = _hits(variants, joined_prompts)
    in_observations = _hits(variants, joined_observations)
    in_committed = _hits(variants, joined_committed)
    in_baseline = _hits(variants, normalise(baseline_prompt_text))
    in_static_world = _hits(variants, normalise(static_world_text))
    contaminated = bool(in_baseline or in_static_world)

    return {
        **generic,
        "declared_salary": declared_salary,
        "salary_surface_forms_tested": list(variants),
        "salary_found_in_subject_prompts": in_prompts,
        "salary_found_in_subject_observations": in_observations,
        "salary_found_in_committed_events": in_committed,
        "salary_also_present_in_no_offer_baseline_prompts": in_baseline,
        "salary_also_present_in_static_world_context": in_static_world,
        "contaminated_token": contaminated,
        "offer_reached_the_subject": bool(in_prompts) and not contaminated,
        "offer_reached_the_world": bool(in_committed) and not contaminated,
        "subject_prompt_count": len(prompts),
        "subject_observation_count": len(observations),
    }


def check_offer_delivery(*, scenario_id, subject_name, branches,
                         baseline_candidate_id, static_world_text) -> dict:
    """``branches``: iterable of
    ``(candidate_id, action, rows, committed_texts, declared_salary)``.
    """
    branches = list(branches)
    baseline_rows = next(
        (rows for candidate_id, _a, rows, _c, _s in branches
         if candidate_id == baseline_candidate_id), [])
    baseline_prompt_text = " ".join(
        entry["prompt"] for entry in recipient_prompts(baseline_rows,
                                                       subject_name))

    per_branch = [
        check_offer_branch(
            candidate_id=candidate_id, candidate_action=action,
            subject_name=subject_name, step_ledger_rows=rows,
            committed_texts=committed, declared_salary=salary,
            baseline_prompt_text=baseline_prompt_text,
            static_world_text=static_world_text)
        for candidate_id, action, rows, committed, salary in branches]

    first_hashes = {entry["candidate_id"]:
                    entry["recipient_first_turn_prompt_sha256"]
                    for entry in per_branch}
    all_prompt_hashes = {
        entry["candidate_id"]: [item["sha256"]
                                for item in entry["per_prompt_sha256"]]
        for entry in per_branch}
    distinct_first = len(set(first_hashes.values()))
    distinct_all = len({tuple(value)
                        for value in all_prompt_hashes.values()})

    offer_entries = [entry for entry in per_branch
                     if entry["candidate_id"] != baseline_candidate_id]
    reached = [entry["candidate_id"] for entry in offer_entries
               if entry["offer_reached_the_subject"]]
    reached_world = [entry["candidate_id"] for entry in offer_entries
                     if entry["offer_reached_the_world"]]

    if not reached and distinct_first <= 1:
        verdict = "offers_never_reached_the_subject"
    elif not reached:
        verdict = "no_salary_figure_reached_the_subject"
    elif len(reached) < len(offer_entries):
        verdict = "some_offers_reached_the_subject"
    elif distinct_first <= 1:
        verdict = "subject_saw_identical_first_turn_context"
    else:
        verdict = "offers_reached_the_subject"

    return {
        "scenario_id": scenario_id,
        "subject_actor": subject_name,
        "baseline_candidate_id": baseline_candidate_id,
        "per_branch": per_branch,
        "subject_first_turn_prompt_sha256_by_candidate": first_hashes,
        "subject_all_prompt_sha256_by_candidate": all_prompt_hashes,
        "distinct_subject_first_turn_prompts": distinct_first,
        "distinct_subject_full_prompt_sequences": distinct_all,
        "branch_count": len(per_branch),
        "offer_branches_whose_salary_reached_the_subject": reached,
        "offer_branches_whose_salary_reached_the_world": reached_world,
        "verdict": verdict,
        "interpretation": INTERPRETATION[verdict],
    }


def distinctive_private_context_leak_check(*, step_ledger_rows,
                                           private_by_name) -> dict:
    """Leak check over fragments DISTINCTIVE to one actor.

    The generic check in :mod:`delivery` compares every actor's prompt
    against every other actor's private-context fragments.  When the
    compiler gives two actors byte-identical boilerplate -- and it did
    here: both advisory actors carry the sentence "Aware of Richard
    Zheng's background as described in the evidence package." -- each
    actor's OWN prompt trips the other actor's fragment, and the generic
    check reports a leak that is not one.

    This refinement keeps only fragments owned by exactly ONE actor, so a
    finding means actor A's prompt carried content that could only have
    come from actor B.  Both results are reported: the raw count, the
    shared-boilerplate fragments that explain the difference, and the
    distinctive count.
    """
    fragments_by_owner = {name: candidate_fragments(text)
                          for name, text in private_by_name.items()}
    owners_by_fragment: dict = {}
    for name, fragments in fragments_by_owner.items():
        for fragment in fragments:
            owners_by_fragment.setdefault(fragment, set()).add(name)
    shared = sorted(fragment for fragment, owners
                    in owners_by_fragment.items() if len(owners) > 1)
    distinctive = {
        name: [fragment for fragment in fragments
               if len(owners_by_fragment[fragment]) == 1]
        for name, fragments in fragments_by_owner.items()}

    findings = []
    checked = 0
    for record in step_ledger_rows:
        active = record.get("active_actor")
        if not isinstance(active, dict):
            continue
        owner = active.get("name")
        request = record.get("actor_model_request")
        if not isinstance(request, list):
            continue
        for call in request:
            for message in call.get("messages") or []:
                if message.get("role") != "user":
                    continue
                prompt = normalise(message.get("content") or "")
                checked += 1
                for other, fragments in distinctive.items():
                    if other == owner:
                        continue
                    hits = [fragment for fragment in fragments
                            if fragment in prompt]
                    if hits:
                        findings.append({
                            "step": record.get("step"),
                            "prompt_owner": owner, "leaked_from": other,
                            "fragment": hits[0][:200]})
    return {
        "method": ("only private-context fragments owned by exactly one "
                   "actor are tested, so byte-identical boilerplate the "
                   "compiler gave two actors cannot register as a leak"),
        "prompts_checked": checked,
        "leaks_found": len(findings),
        "findings": findings,
        "shared_boilerplate_fragments": shared,
        "shared_boilerplate_fragment_count": len(shared),
        "distinctive_fragment_counts": {name: len(fragments)
                                        for name, fragments
                                        in sorted(distinctive.items())},
    }


INTERPRETATION = {
    "offers_reached_the_subject": (
        "every offer branch's own salary figure appeared in a prompt "
        "actually sent to the subject's model, and the subject's "
        "first-turn context differed by branch, so a measured difference "
        "between branches can be attributed to the offers."),
    "offers_never_reached_the_subject": (
        "NO offer branch's salary figure ever appeared in a prompt sent to "
        "the subject's model, AND the subject's first-turn prompt was "
        "byte-identical in every branch. Any difference the metrics report "
        "therefore cannot have been caused by the offers: the run measures "
        "live-model sampling variation on one identical prompt. THIS IS "
        "NOT A HIRING RESULT and the ranking is not evidence that one "
        "salary is better than another."),
    "no_salary_figure_reached_the_subject": (
        "no offer branch's salary figure reached the subject's own "
        "prompts, although the subject's first-turn prompts did differ; "
        "any measured difference must be traced to that other difference, "
        "not to the offer amount. THIS IS NOT A HIRING RESULT."),
    "some_offers_reached_the_subject": (
        "some offer branches' salary figures reached the subject and "
        "others did not; a comparison across the full branch set is not "
        "like-for-like, and only the branches listed in "
        "'offer_branches_whose_salary_reached_the_subject' were actually "
        "tested against the subject."),
    "subject_saw_identical_first_turn_context": (
        "salary figures reached the subject later in the branch, but the "
        "subject's FIRST turn ran on identical context in every branch; "
        "differences arising at that first turn are sampling variation, "
        "not offer effects."),
}
