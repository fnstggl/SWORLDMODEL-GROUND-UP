"""CHARACTERIZATION of a guard behaviour this experiment ran into.

**These tests record what the accepted engine DOES today, not what it
should do.**  They exist because the a16z run hit the behaviour twenty
times and the UNDER_THE_HOOD report quotes them as evidence; if the
behaviour is deliberately changed, this file must change with it and the
a16z experiment must be re-run from its frozen input.  Nothing here
modifies production code.

The observation
---------------
``sworldmodel.backends.concordia_local.guard`` documents an
object-position exemption so the epistolary form stays usable: "sends a
note to Morgan: 'call me'" is the speaker's OWN message TO the name and
must pass through unchanged.  The exemption looks at the word
IMMEDIATELY before the name, so a determiner between the preposition and
the name defeats it:

- ``sends a message to New Media Hiring Lead: "..."``      -> exempt
- ``sends a note to Morgan: "call me"``                     -> exempt
- ``sends a message to THE New Media Hiring Lead: "..."``   -> REWRITTEN

In the rewritten case the whole quoted message is removed from the
committed world event, leaving a dangling "to the." and an availability
sentence.  In this run that destroyed the content of twenty committed
events -- including compensation approvals and internal notes -- because
role-based actor names are natural determiner-taking noun phrases
("the People and Compensation Partner").  A cast of personal names would
not have hit it.

This is reported to the engine owner, not repaired here: the guard is a
safety-relevant agency protection shared with the already-committed
Peter scenarios, and this experiment is not its owner.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if sys.version_info < (3, 12):
    pytest.skip("harness suite runs in the pinned engine environment "
                "(Python >= 3.12)", allow_module_level=True)

from sworldmodel.backends.concordia_local.guard import (  # noqa: E402
    AVAILABILITY_MARKER, make_agency_guard)

ROSTER = ("People and Compensation Partner", "New Media Hiring Lead",
          "New Media Strategy Partner", "Creative Production Lead",
          "Richard Zheng")

ACTIVE = "People and Compensation Partner"

#: the exact recorded actor turn from branch user_001, step 4 of the live
#: run (artifacts/.../a16z_richard_historical/branches/user_001/
#: step_ledger.jsonl), trimmed to the sentence that triggered the rewrite
RECORDED_TURN = (
    "People and Compensation Partner: People and Compensation Partner "
    "reviews the fixed package parameters for the New Media role and "
    "sends a concise message to the New Media Hiring Lead: “Confirmed"
    "—the role’s title, scope, reporting line, benefits, and "
    "equity are fixed as previously documented; only annual base salary "
    "is variable.”")


def _guard(text: str) -> str:
    return make_agency_guard(list(ROSTER))(None, text, ACTIVE)


def test_the_object_position_exemption_holds_without_a_determiner():
    text = ("People and Compensation Partner: sends a concise message to "
            "New Media Hiring Lead: “the package is fixed.”")
    assert _guard(text).strip() == text.strip()


def test_the_documented_epistolary_example_is_exempt():
    text = "Alex: Alex sends a note to Morgan: “call me”"
    assert _guard(list((text,))[0]).strip() == text.strip()


def test_a_determiner_between_the_preposition_and_the_name_defeats_it():
    """DEFECT CHARACTERIZATION -- fix this and the assertion flips.

    The guard rewrites a message the ACTIVE actor sent, and the quoted
    content is deleted from the committed world.
    """
    out = _guard(RECORDED_TURN)
    assert out.strip() != RECORDED_TURN.strip()
    assert "sends a concise message to the." in out
    assert AVAILABILITY_MARKER in out
    # the message content is gone from the committed event
    assert "only annual base salary is variable" not in out
    assert "Confirmed" not in out


def test_the_same_sentence_without_the_colon_is_not_rewritten():
    """The trigger is the attribution marker, not the determiner alone."""
    text = ("People and Compensation Partner: People and Compensation "
            "Partner sends a concise message to the New Media Hiring Lead "
            "saying the package is fixed.")
    assert _guard(text).strip() == text.strip()


def test_a_genuine_agency_theft_is_still_caught():
    """The protection itself must not be confused with the defect."""
    text = ("People and Compensation Partner: New Media Hiring Lead "
            "agrees to the terms and signs the offer.")
    out = _guard(text)
    assert out.strip() != text.strip()
    assert AVAILABILITY_MARKER in out
    assert "signs the offer" not in out
