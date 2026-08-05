"""The guard behaviour this experiment ran into -- now FIXED upstream.

**History.**  This file first CHARACTERIZED a defect: the guard's
object-position exemption looked only at the word immediately before the
recipient name, so a determiner between the preposition and the name
defeated it.  A role-shaped cast takes determiners constantly, and the
live run hit the behaviour twenty times, deleting 4194 characters of
content the ACTIVE actor was itself sending.

**Now.**  The engine owner made the exemption determiner-transparent
(``sworldmodel/backends/concordia_local/guard.py``, ``_scan`` reads
through one ``_OBJECT_SLOT_DETERMINERS`` token).  The production-side
regression tests for the fix live with the guard's own unit suite,
``tests/engine_baseline/test_agency_guard.py`` (the
``determiner_transparency`` family).  What remains here is the
EXPERIMENT-side evidence: the exact recorded actor turn from the live
run, asserted against the corrected behaviour, so a future regression is
caught against real recorded text rather than a synthetic probe.

The a16z artifacts under ``artifacts/`` are the PRE-FIX record and stay
byte-identical; the experiment is re-run from its frozen input in a
separate pass.
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


def test_a_determiner_between_the_preposition_and_the_name_is_exempt_too():
    """The recorded live turn, asserted against the FIXED guard.

    Pre-fix this exact string came back as "... sends a concise message
    to the." plus an availability sentence, with the whole quoted message
    the ACTIVE actor was sending deleted from the committed world."""
    out = _guard(RECORDED_TURN)
    assert out == RECORDED_TURN
    # the message content survives in the committed event
    assert "only annual base salary is variable" in out
    assert "Confirmed" in out
    # and no availability sentence was appended: nobody's agency was
    # claimed, so there is nothing to offer back
    assert AVAILABILITY_MARKER not in out
    assert "sends a concise message to the." not in out


def test_the_same_sentence_without_the_colon_is_not_rewritten():
    """The trigger was the attribution marker, not the determiner alone;
    this shape passed before the fix and still passes."""
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


def test_a_genuine_agency_theft_with_a_determiner_is_still_caught():
    """The fix must not have bought the exemption with a hole: a real
    proxy attribution whose recipient carries an article is rewritten."""
    text = ("People and Compensation Partner sends the package to the "
            "New Media Hiring Lead. The New Media Hiring Lead agrees to "
            "the terms.")
    out = _guard(text)
    assert out.strip() != text.strip()
    assert "agrees to the terms" not in out
    assert f"New Media Hiring Lead {AVAILABILITY_MARKER}" in out
