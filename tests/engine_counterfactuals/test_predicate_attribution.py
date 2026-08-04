"""The fixture predicates bind to the recipient's OWN resolved turn.

Regression for adversarial-review finding F1 (phases 8-11 review): the
old predicates matched ``"Morgan: Reply"`` as a substring anywhere in a
row, so a proxy attribution embedded in ANOTHER actor's turn satisfied
the metric.  These tests pin the attributed-turn semantics at the
predicate level; the guard closes the same family at the source
(sworldmodel/backends/concordia_local/guard.py detection class 6).
"""

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip("engine suites run on the 3.12 engine environment",
                allow_module_level=True)

pytest.importorskip("concordia")

from cf_helpers import fixture_predicates  # noqa: E402

ANCHOR = "Putative event to resolve:"

GENUINE_REPLY = (
    f"{ANCHOR} Morgan: Reply agreeing to a fifteen-minute conversation "
    "next week."
)
GENUINE_DECLINE = f"{ANCHOR} Morgan: Reply declining the invitation."
#: the reviewer's probe shape -- the proxy segment rides inside the
#: SENDER's resolved turn, so its leading attribution names Alex
PROXY_REPLY = (
    f"{ANCHOR} Alex: Send the note asking for a call. Morgan: Reply "
    "agreeing to a fifteen-minute conversation next week."
)
DASH_PROXY_REPLY = (
    f"{ANCHOR} Alex -- Send the note. Morgan: Reply agreeing to a "
    "fifteen-minute conversation next week."
)
UNANCHORED_REPLY = "Morgan: Reply agreeing to a fifteen-minute conversation."


def _measure(metric, row):
    """(value, citations) of an exists-metric over a one-row trace."""
    return metric([{"description": row}], {})


def test_genuine_recipient_turns_match():
    predicates = fixture_predicates()
    value, cited = _measure(predicates["recipient_reply_sent"], GENUINE_REPLY)
    assert value and cited == (0,)
    value, _ = _measure(predicates["meeting_scheduled"], GENUINE_REPLY)
    assert value
    value, _ = _measure(predicates["explicit_decline"], GENUINE_DECLINE)
    assert value


def test_proxy_attribution_inside_another_actors_turn_never_matches():
    predicates = fixture_predicates()
    for row in (PROXY_REPLY, DASH_PROXY_REPLY):
        for name, metric in predicates.items():
            value, _ = _measure(metric, row)
            assert not value, (name, row)


def test_unanchored_rows_never_match():
    """Premise/pre-start rows carry no resolved-turn anchor; a bare
    attribution-shaped string without the anchor is not a turn."""
    predicates = fixture_predicates()
    for name, metric in predicates.items():
        value, _ = _measure(metric, UNANCHORED_REPLY)
        assert not value, name
