"""Visibility incoherence is RECORDED, never refused (R2 hygiene).

The 2026-08-04 under-the-hood validation traced part of the delivery
failure to a compiled world shape nothing in the chain flagged: a
starting event described as "A sends the prepared message to B" carrying
``visible_to: [A]``.  B is narrated as a participant in an event B never
observes; the send is delivered to A only; A's model is told the send
already happened, so the content reaches B only if A's own model chooses
to restate it.  The production compiler's own prompt exemplar teaches
that exact shape, so it is systematic across cold-outreach worlds, and
scene validation, this adapter, and the planner all passed it silently.

The remedy is a labeled WARNING, not a refusal: a deliberately one-sided
narration (a private note ABOUT someone, an unsent draft, an observation
of a third party) is a legitimate world and must not be rejected.  These
tests hold the line in both directions -- the incoherent shape is
recorded with enough detail to act on, and the adapter still returns a
usable world.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine compilation suite requires Python >= 3.12 "
        "(Concordia floor); run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

from compilation_helpers import (CANARY_CUTOFF, CANARY_START,
                                 adapt_canary_scene, canary_manifest)
from sworldmodel.compilation import (VISIBILITY_WARNING_LABEL,
                                     adapt_compiled_scene,
                                     visibility_incoherence_warnings)


def _adapt(manifest, insertion_actor="Alice"):
    return adapt_compiled_scene(
        manifest, question="Which candidate action works best?",
        start=CANARY_START, cutoff=CANARY_CUTOFF,
        insertion_actor=insertion_actor,
        compiler_version="vtest_visibility",
        evidence_mode="scripted_test_vector")


def _one_sided_send_manifest():
    """The exact defect shape the compiler's own exemplar teaches."""
    manifest = canary_manifest()
    manifest["starting_events"] = [{
        "time": CANARY_START,
        "description": "Alice sends the prepared message to Bob.",
        "visible_to": ["Alice"],
    }]
    return manifest


# ---------------------------------------------------------------------------
# The finding
# ---------------------------------------------------------------------------


def test_the_one_sided_send_shape_is_recorded():
    adapted = _adapt(_one_sided_send_manifest())

    assert len(adapted.warnings) == 1
    warning = adapted.warnings[0]
    assert warning["label"] == VISIBILITY_WARNING_LABEL
    assert warning["event_index"] == 0
    assert warning["actor_id"] == "bob"
    assert warning["actor_name"] == "Bob"
    assert warning["visible_to"] == ["alice"]
    assert "does not include 'bob'" in warning["detail"]

    # The same record rides the persisted sidecar, clearly labeled and
    # counted, so a caller that only keeps artifacts still sees it.
    assert adapted.sidecar["warnings"] == [dict(warning)]
    assert adapted.sidecar["warning_counts"] == {
        VISIBILITY_WARNING_LABEL: 1}


def test_a_warning_never_refuses_the_world():
    """Recorded, not rejected: the adapted world is fully usable and the
    event's declared visibility is carried through UNCHANGED (the
    adapter never repairs what it warns about)."""
    adapted = _adapt(_one_sided_send_manifest())
    assert adapted.warnings
    event = adapted.world.starting_events[0]
    assert event.visible_to == ("alice",)
    assert event.description == "Alice sends the prepared message to Bob."
    assert adapted.world.world_id.startswith("w_")


def test_a_coherent_world_records_nothing():
    manifest = _one_sided_send_manifest()
    manifest["starting_events"][0]["visible_to"] = ["Alice", "Bob"]
    adapted = _adapt(manifest)
    assert adapted.warnings == ()
    assert adapted.sidecar["warnings"] == []
    assert adapted.sidecar["warning_counts"] == {
        VISIBILITY_WARNING_LABEL: 0}


def test_the_canary_scene_is_clean():
    """The suite's own baseline scene names no actor outside its
    visibility, so the check does not fire on ordinary worlds."""
    adapted = adapt_canary_scene()
    assert adapted.warnings == ()


# ---------------------------------------------------------------------------
# Conservatism: the matcher must not flood the reader
# ---------------------------------------------------------------------------


def test_matching_is_whole_token_and_exact_only():
    """No substring, prefix, or fuzzy matching: an over-eager rule would
    warn on every world and train readers to ignore the warning."""
    events = [{"description": "Alicia and Bobbin review the ledger.",
               "visible_to": ["alice"]},
              {"description": "The note reaches Bob, unread.",
               "visible_to": ["alice"]},
              {"description": "Nobody is named here at all.",
               "visible_to": ["alice"]}]
    findings = visibility_incoherence_warnings(
        events, {"alice": "Alice", "bob": "Bob"})
    # Only the middle event names a real, non-visible actor.
    assert [entry["event_index"] for entry in findings] == [1]
    assert findings[0]["actor_id"] == "bob"


def test_findings_are_deterministically_ordered():
    events = [{"description": "Bob and Alice are both named here.",
               "visible_to": []}]
    first = visibility_incoherence_warnings(
        events, {"bob": "Bob", "alice": "Alice"})
    second = visibility_incoherence_warnings(
        events, {"alice": "Alice", "bob": "Bob"})
    assert first == second
    assert [entry["actor_id"] for entry in first] == ["alice", "bob"]
