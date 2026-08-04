"""Did this branch's intervention actually reach the world?

A counterfactual compares candidates.  That comparison only means
anything if the candidates DIFFERED in what the other actors saw.  The
engine's intervention boundary is deliberately narrow -- the candidate
text is appended to the INSERTION actor's initial observations and
nothing else (``counterfactuals.branch``) -- so whether it propagates
further depends on what that actor's own model chooses to do with it.
Under a scripted sender that echoes the candidate it always propagates;
under a free-choice sender it may not propagate at all, and two live runs
found exactly that: every branch's recipient ran on byte-identical
context, and the measured "differences" were sampling variation on one
prompt.

This module computes, per branch, from the branch's OWN recorded
artifacts, the fact those runs lacked:

    did any distinctive fragment of this branch's candidate text reach an
    actor OTHER than the insertion actor it was handed to?

Method (the cheap, production form of the experiment-side checks in
``experiments/full_trace_validation/delivery.py`` and
``offer_delivery.py``):

1. **Fragments.**  The candidate's action text (and each declared
   constraint) is split into sentence / line runs; runs of at least
   :data:`MIN_FRAGMENT_CHARS` characters are kept, longest first, capped
   at :data:`MAX_FRAGMENTS`.  A paraphrase therefore does not count --
   only real content arriving does.
2. **Distinctive-context refinement.**  A fragment already present in the
   branch's PRE-RUN context -- the shared setup, any actor's private
   setup, or any actor's non-intervention initial observations -- is
   discarded before testing.  Without this the check over-reports
   grossly: the a16z run's shared check reported 36 hits and 0 were real,
   because the compiler had given several actors byte-identical
   boilerplate, so every actor's own prompt tripped another actor's
   fragment.  Only fragments the intervention itself introduced are
   tested.
3. **Reach.**  A distinctive fragment found in a NON-insertion actor's
   own observation/memory stream means the intervention reached that
   actor.  Presence in the committed event stream alone is recorded
   separately (``reached_committed_world``): text can enter the world
   through the insertion actor's own turns and still never be delivered
   to anyone else, which is precisely the second live run's shape.

Honest third state.  When there is nothing to measure -- no distinctive
fragment survives step 2, or the branch produced no actor memories
(a failure result) -- the status is ``not_computed`` with the reason,
never ``not_delivered``.  ``sworldmodel.outcomes.ranking`` refuses to
rank on a measured "no"; it must not refuse on an absence of
measurement.

Pure stdlib; no engine import, no model, no randomness.
"""

from __future__ import annotations

import re

from sworldmodel.decision.contracts import (DELIVERY_DELIVERED,
                                            DELIVERY_NOT_COMPUTED,
                                            DELIVERY_NOT_DELIVERED,
                                            InterventionCandidate,
                                            default_intervention_delivery,
                                            delivery_status)

#: minimum length of a candidate substring counted as "distinctive"
MIN_FRAGMENT_CHARS = 24

#: how many fragments to test per candidate (longest first)
MAX_FRAGMENTS = 12

#: fixed description of the computation, recorded on every measured fact
METHOD = (
    "distinctive candidate fragments (>= 24 chars, sentence/line runs, "
    "longest 12) minus every fragment already present in the branch's "
    "pre-run context, searched in each non-insertion actor's own "
    "observation stream")

_WS = re.compile(r"\s+")
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def normalise(text) -> str:
    """Whitespace-normalised comparison form (interior bytes otherwise
    untouched; nothing is lowercased -- a case change is a content
    change for this purpose)."""
    if not isinstance(text, str):
        return ""
    return _WS.sub(" ", text).strip()


def candidate_fragments(text) -> list:
    """Distinctive fragments of one text: its longest sentence / line
    runs, whitespace-normalised, longest first then lexicographic (a
    fixed total order, so the record is byte-stable)."""
    fragments = []
    for piece in _SPLIT.split(text or ""):
        piece = normalise(piece)
        if len(piece) >= MIN_FRAGMENT_CHARS and piece not in fragments:
            fragments.append(piece)
    fragments.sort(key=lambda piece: (-len(piece), piece))
    return fragments[:MAX_FRAGMENTS]


def intervention_texts(candidate: InterventionCandidate) -> tuple:
    """The raw texts one candidate contributes at the insertion boundary
    (the action, then each declared constraint, in declared order)."""
    return (candidate.action,) + tuple(candidate.constraints)


def _baseline_text(plan, inserted_lines) -> str:
    """The branch's PRE-RUN context, minus the intervention itself.

    Everything an actor already had before the first turn: the shared
    setup, every actor's private setup, and every initial observation
    that is NOT one of the intervention's own inserted lines.
    """
    parts = [plan.shared_init_data]
    parts.extend(config.private_init_data for config in plan.actor_configs)
    inserted = set(inserted_lines)
    for observations in plan.initial_observations.values():
        parts.extend(line for line in observations if line not in inserted)
    return normalise(" ".join(parts))


def compute_intervention_delivery(*, candidate, plan, actor_memories,
                                  committed_events) -> dict:
    """The per-branch ``intervention_delivered`` fact (see the module
    docstring and ``contracts.INTERVENTION_DELIVERY_STATUSES``).

    ``actor_memories`` maps actor_id to that actor's own recorded
    observation/memory rows; ``committed_events`` is the branch's
    committed event stream.  Never raises on missing evidence: an
    unmeasurable branch reports ``not_computed`` with the reason.
    """
    fact = default_intervention_delivery()
    if not isinstance(candidate, InterventionCandidate):
        fact["reason"] = "no_candidate"
        return fact
    insertion_actor = plan.intervention_insertion.actor_id
    fact["insertion_actor"] = insertion_actor
    fact["method"] = METHOD

    # Lazy import: same package, but keep the import graph explicit.
    from .branch import insertion_observation_texts

    fragments: list = []
    for text in intervention_texts(candidate):
        for fragment in candidate_fragments(text):
            if fragment not in fragments:
                fragments.append(fragment)
    baseline = _baseline_text(plan, insertion_observation_texts(candidate))
    distinctive = [fragment for fragment in fragments
                   if fragment not in baseline]
    fact["fragments_tested"] = len(distinctive)

    memories = actor_memories if isinstance(actor_memories, dict) else {}
    others = [actor_id for actor_id in sorted(memories)
              if actor_id != insertion_actor]
    if not distinctive:
        fact["reason"] = ("no_distinctive_candidate_fragments"
                          if fragments
                          else "candidate_text_too_short_to_fingerprint")
        return fact
    if not others:
        fact["reason"] = "no_other_actor_memory_recorded"
        return fact

    reached: list = []
    found = 0
    for actor_id in others:
        joined = normalise(" ".join(str(row) for row in memories[actor_id]))
        hits = [fragment for fragment in distinctive if fragment in joined]
        if hits:
            reached.append(actor_id)
            found = max(found, len(hits))
    committed = normalise(" ".join(str(row) for row in
                                   (committed_events or ())))
    fact["reached_actors"] = reached
    fact["fragments_found"] = found
    fact["reached_committed_world"] = any(fragment in committed
                                          for fragment in distinctive)
    fact["status"] = DELIVERY_DELIVERED if reached else DELIVERY_NOT_DELIVERED
    fact["reason"] = ("reached_non_insertion_actor" if reached else
                      "no_distinctive_fragment_reached_any_other_actor")
    return fact


#: re-exported from the contract layer so callers of this module do not
#: need two imports to read what it computed
delivery_status = delivery_status


__all__ = ["MIN_FRAGMENT_CHARS", "MAX_FRAGMENTS", "METHOD", "normalise",
           "candidate_fragments", "intervention_texts",
           "compute_intervention_delivery", "delivery_status",
           "DELIVERY_DELIVERED", "DELIVERY_NOT_DELIVERED",
           "DELIVERY_NOT_COMPUTED"]
