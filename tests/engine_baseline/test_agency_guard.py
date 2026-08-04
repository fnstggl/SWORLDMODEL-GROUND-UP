"""Phase 5: the minimum agency guard.

Directive rule under test ("Immediate minimum agency guard"): the Game
Master may describe mechanical or nonvoluntary consequences, but it may
not permanently commit a voluntary decision for a DIFFERENT actor
without giving that actor its own turn.

Proven here:

Unit (deterministic detector + rewriter, no engine, no model):
  1. a forced other-actor decision is rewritten: the decision assertion
     is gone, the active player's attempt survives verbatim, and the
     neutral availability clause is appended (marker containment per
     Phase 2 finding 4 -- never full-string equality against engine
     output; direct guard calls may assert exact strings because the
     guard's own contract IS byte-level);
  2. mechanical/nonvoluntary consequences pass through byte-identically;
  3. receipt/observation-only mentions pass through (receipt is not a
     voluntary act);
  4. the ACTIVE player's own decision passes through (actors own their
     own choices);
  5. unknown pseudo-actor names pass through (only the known roster is
     protected);
  6. multiple affected actors are all handled (chained clauses and
     compound subjects);
  7. empty/degenerate events pass through;
  8. prepositional objects, gerund participles, conditionals, and modal
     predictions are NOT treated as committed decisions (the
     over-blocking discriminators); reported speech IS detected on the
     deterministic path;
  9. the guard is idempotent and the escalation hook fires exactly once
     per rewrite with the documented arguments;
 10. the factory validates its roster and options.

Hardened classes (phases 3-7 adversarial review, findings 6 and 7 --
each class carries a caught case AND a nearby legitimate shape):
 13. pronoun and collective subjects are detected ("She agrees to the
     plan", "They commit to the deadline", "The team accepts the
     offer"): singular pronouns bind the nearest preceding roster name,
     plurals bind the distinct preceding names, and unresolvable
     subjects conservatively bind every non-active roster actor; the
     active player's own anaphora and non-act verbs pass through;
 14. perfect / progressive / modal-perfect auxiliary chains are
     detected ("has agreed", "is agreeing", "will have accepted");
     negations, passives ("has been chosen"), possession ("has a
     signed copy"), and bare modal predictions pass through;
 15. nominalizations are detected ("Bo's agreement to the terms",
     "the acceptance by Bo"); anticipation frames and requests about a
     future act ("waits for Bo's reply", "asks for Bo's agreement",
     "without Bo's signature") pass through;
 16. a comma-bounded parenthetical aside between subject and verb is
     detected ("Bo, after some thought, agrees") without blocking the
     active player's own aside shape;
 17. speaker-stance content is never removed (review over-block
     classes): belief-verb complements ("hopes Bo agrees", "believes
     Bo will reply") and performative content requests ("asks that Bo
     reply by Friday") survive byte-identically, while assertion verbs
     ("confirms", "announces that") remain caught.

Proxy attribution (phases 8-11 adversarial review, finding F1 --
upstream EventResolution's own ``:`` / ``--`` attribution separators):
 18. a NON-ACTIVE roster name immediately followed by ``:`` or by
     whitespace plus ``--`` claims the entire following content (to the
     line break) as that actor's own turn and is caught: the exact four
     reviewer probes, the dash variant, mid-text forms, a multi-sentence
     attributed segment, leading other-name attributions, marker chains
     ("Bo and Cam:"), and multiple markers in one event;
 19. the ACTIVE player's own attribution passes byte-identically --
     leading (the upstream turn format, alone or under the putative
     framing) and mid-text alike -- along with a colon after a
     non-roster word, recipient/epistolary colons after non-agent lead
     words ("sends a note to Bo: '...'"), performative-request colons
     after stance verbs ("asks Bo: '...'"), and the documented
     received-content residual ("reads the note from Bo: '...'");
     assertion-verb frames ("quotes Bo: 'I agree'") stay caught (the
     same line the reported-speech class draws);
 20. the new class is idempotent, escalates with the documented record
     shape, and scopes removal to the line break (content after a
     newline survives).

Integration (full stock-Concordia loop, scripted models per the Phase 4
pattern):
 11. an active actor's action text embedding the other actor's agreement
     is split: the committed ``[event]`` carries the attempt plus the
     availability form and never the forged agreement; the affected
     actor's own turn then actually occurs (their model prompt contains
     the availability observation) and THEIR scripted decision is what
     lands in the trace; ``guard_interventions`` records the rewrite
     with the right step/actors; three clean runs are byte-identical
     under the shared seeded harness;
 12. a clean control scenario shows ``guard_interventions == []`` and a
     trace byte-identical to the guard-disabled (Phase 4 identity-slot)
     configuration -- the Concordia loop still works, unchanged, when
     nothing violates.  (Scenarios one and two of this suite run the
     default-enabled guard end to end as well.)
"""

from __future__ import annotations

import json
import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "engine baseline requires Python >= 3.12 (Concordia floor); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from det import seeded_determinism  # tests/engine_contracts (via conftest)

from baseline_helpers import (StrictScriptedModel, all_prompt_text,
                              aware_rule, run_signature)
from sworldmodel.backends.concordia_local import builder, planner, runner
from sworldmodel.backends.concordia_local.guard import (
    AVAILABILITY_MARKER, GUARD_SLOT_VALUE, make_agency_guard,
    voluntary_act_forms)
from sworldmodel.decision.contracts import (CompiledDecisionWorld,
                                            EvaluatorSpec, SCHEMA_VERSION)

SEED = 51015
ROSTER = ("Ada", "Bo", "Cam")


def _guard(recorder=None):
    return make_agency_guard(ROSTER, escalate=recorder)


# ---------------------------------------------------------------------------
# Unit: rewrite of forced other-actor decisions
# ---------------------------------------------------------------------------


def test_forced_decision_for_non_active_actor_is_rewritten():
    calls = []
    guard = _guard(lambda *args: calls.append(args))
    event = "Ada sends the outline to Bo, and Bo agrees to proceed."
    out = guard(None, event, "Ada")

    assert out != event
    # (b) the asserted other-actor decision is removed...
    assert "agrees to proceed" not in out
    # (a) ...the active player's attempt is preserved verbatim...
    assert "Ada sends the outline to Bo" in out
    # (c) ...and the neutral availability clause is appended.
    assert AVAILABILITY_MARKER in out
    assert "Bo is now able to observe" in out
    # The escalation hook fired exactly once, with the documented shape.
    assert calls == [(event, out, "Ada", ("Bo",))]


def test_whole_sentence_decision_is_removed_not_reworded():
    guard = _guard()
    out = guard(None, "Bo agrees to the plan.", "Ada")
    assert "agrees to the plan" not in out
    assert AVAILABILITY_MARKER in out
    # Nothing is invented in either direction: no acceptance, no refusal.
    assert "Bo is now able to observe this and to respond in their own " \
           "turn." == out


def test_past_tense_decision_is_detected():
    guard = _guard()
    out = guard(None, "Ada hands the ledger to Bo, and Bo signed it.", "Ada")
    assert "signed" not in out
    assert "Ada hands the ledger to Bo" in out
    assert AVAILABILITY_MARKER in out


def test_reported_speech_is_detected_on_the_deterministic_path():
    # An embedded decision assertion enters every observer's memory
    # verbatim once committed, so the deterministic default treats it as
    # the violation it is; only the OPTIONAL live-model confirmation may
    # relax this class, and no model is configured here.
    guard = _guard()
    out = guard(None, "Ada reports that Bo accepted the offer.", "Ada")
    assert "accepted the offer" not in out
    assert "Ada reports" in out
    assert AVAILABILITY_MARKER in out


# ---------------------------------------------------------------------------
# Unit: pass-through discriminators
# ---------------------------------------------------------------------------


def test_mechanical_consequences_pass_through_byte_identical():
    calls = []
    guard = _guard(lambda *args: calls.append(args))
    for event in (
            "The relay transmits the packet to Bo.",
            "A deadline lapses and the shared resource is consumed.",
            "The parcel addressed to Cam arrives at the depot.",
            "The lamp over Ada's bench flickers and goes dark.",
    ):
        assert guard(None, event, "Ada") == event
    assert calls == []


def test_receipt_only_mention_passes_through():
    guard = _guard()
    for event in (
            "Bo receives the file from Ada.",
            "Cam observes the announcement.",
            "The note reaches Bo unread.",
    ):
        assert guard(None, event, "Ada") == event


def test_active_players_own_decision_passes_through():
    guard = _guard()
    event = "Ada agrees to the revised terms."
    assert guard(None, event, "Ada") == event
    # Same text IS a violation when someone else is active.
    assert guard(None, event, "Bo") != event


def test_unknown_pseudo_actor_passes_through():
    guard = _guard()
    event = "Quorlan agrees to the plan."
    assert guard(None, event, "Ada") == event


def test_non_agent_grammar_is_not_over_blocked():
    guard = _guard()
    for event in (
            # prepositional object + gerund participle: the agreeing is
            # the SUBJECT's, not Bo's (the measured scenario-one shape)
            "Ada replies to Bo agreeing to a short conversation.",
            # conditional frame: a condition is not a commitment
            "If Bo agrees, the hold lapses.",
            "The offer stands until Bo accepts it.",
            # modal prediction: not a committed decision
            "Bo may agree later.",
            # coordinated verb of the ACTIVE subject after another name
            "Ada thanks Bo and confirms the agreed slot.",
    ):
        assert guard(None, event, "Ada") == event


def test_empty_and_degenerate_events_pass_through():
    guard = _guard()
    for event in ("", "   ", "\n", "Bo", "agrees"):
        assert guard(None, event, "Ada") == event
    assert guard(None, None, "Ada") is None


# ---------------------------------------------------------------------------
# Unit: multiple affected actors, idempotence, factory contracts
# ---------------------------------------------------------------------------


def test_multiple_affected_actors_are_all_handled():
    calls = []
    guard = _guard(lambda *args: calls.append(args))

    chained = "Ada circulates the draft, and Bo agrees and Cam signs it."
    out = guard(None, chained, "Ada")
    assert "Ada circulates the draft" in out
    assert "agrees" not in out and "signs" not in out
    assert "Bo is now able to observe" in out
    assert "Cam is now able to observe" in out
    assert calls[-1][3] == ("Bo", "Cam")

    compound = "Ada calls out, and Bo and Cam agree to proceed."
    out2 = guard(None, compound, "Ada")
    assert "agree to proceed" not in out2
    assert "Ada calls out" in out2
    assert "Bo is now able to observe" in out2
    assert "Cam is now able to observe" in out2
    assert calls[-1][3] == ("Bo", "Cam")


def test_guard_is_idempotent():
    guard = _guard()
    event = "Ada sends the outline to Bo, and Bo agrees to proceed."
    once = guard(None, event, "Ada")
    assert guard(None, once, "Ada") == once


def test_factory_validates_roster_and_options():
    with pytest.raises(ValueError, match="at least one"):
        make_agency_guard(())
    with pytest.raises(ValueError, match="non-blank"):
        make_agency_guard(("Ada", "  "))
    with pytest.raises(ValueError, match="unique"):
        make_agency_guard(("Ada", "Ada"))
    with pytest.raises(ValueError, match="callable"):
        make_agency_guard(("Ada",), escalate="not-a-callable")
    with pytest.raises(ValueError, match="requires a model"):
        make_agency_guard(("Ada",), use_llm_confirmation=True)
    guard = make_agency_guard(("Ada", "Bo"))
    assert guard.actor_names == ("Ada", "Bo")
    assert guard.guard_slot_value == GUARD_SLOT_VALUE


def test_voluntary_act_forms_cover_the_directive_lemmas():
    forms = voluntary_act_forms()
    # One finite form per directive act category (spot the full list).
    for form in ("replies", "agrees", "votes", "purchases", "accepts",
                 "rejects", "refuses", "declines", "signs", "supports",
                 "commits", "promises", "chooses", "says", "decides",
                 "agreed", "voted", "chose", "said", "decided"):
        assert form in forms, form
    # Gerunds are deliberately NOT triggers (participial false-positive
    # protection; see the guard module docstring).
    assert "agreeing" not in forms


# ---------------------------------------------------------------------------
# Unit: hardened detection classes (review findings 6 and 7)
# ---------------------------------------------------------------------------


def test_pronoun_subject_decisions_are_detected():
    calls = []
    guard = _guard(lambda *args: calls.append(args))

    # Unresolvable singular subject: every non-active actor is
    # conservatively bound and offered its own turn.
    out = guard(None, "She agrees to the plan.", "Ada")
    assert "agrees to the plan" not in out
    assert "Bo is now able to observe" in out
    assert "Cam is now able to observe" in out
    assert calls[-1][3] == ("Bo", "Cam")

    # Nearest-antecedent singular: binds exactly the nearest preceding
    # roster name, and the attempt prefix survives verbatim.
    out = guard(None, "Ada hands the ledger to Bo, and he signs it.", "Ada")
    assert "signs it" not in out
    assert "Ada hands the ledger to Bo" in out
    assert calls[-1][3] == ("Bo",)

    # Unresolvable bare plural (review's literal case).
    out = guard(None, "They commit to the deadline.", "Ada")
    assert "commit to the deadline" not in out
    assert calls[-1][3] == ("Bo", "Cam")

    # Plural resolved by the distinct preceding roster names.
    out = guard(None, "Ada and Bo confer in the hall. They agree.", "Cam")
    assert "They agree" not in out
    assert "Ada and Bo confer in the hall." in out
    assert calls[-1][3] == ("Ada", "Bo")

    # First-person plural binds beyond the speaker by construction.
    out = guard(None, "We agree to the terms.", "Ada")
    assert "agree to the terms" not in out
    assert calls[-1][3] == ("Bo", "Cam")


def test_pronoun_nearby_shapes_are_not_over_blocked():
    guard = _guard()
    for event in (
            # the active player's own anaphora is the active player's
            # own act (nearest antecedent == active)
            "Ada reviews the terms, and she signs them.",
            # non-act verb under a pronoun subject
            "She reviews the file.",
            # conditional frame over a pronoun subject
            "If they agree, the hold lapses.",
            # object-position pronouns are not subjects
            "Ada explains the plan to them in detail.",
    ):
        assert guard(None, event, "Ada") == event


def test_collective_subject_decisions_are_detected():
    calls = []
    guard = _guard(lambda *args: calls.append(args))

    out = guard(None, "The team accepts the offer.", "Ada")
    assert "accepts the offer" not in out
    assert "Bo is now able to observe" in out
    assert "Cam is now able to observe" in out
    assert calls[-1][3] == ("Bo", "Cam")

    # One modifier between determiner and group noun is covered.
    out = guard(None, "The legal team accepts the offer.", "Ada")
    assert "accepts the offer" not in out

    # Quantified plural group subject.
    out = guard(None, "All members agree to the deadline.", "Ada")
    assert "agree to the deadline" not in out


def test_collective_nearby_shapes_are_not_over_blocked():
    guard = _guard()
    for event in (
            # non-act verb under a group subject
            "The team studies the offer.",
            # conditional frame over a group subject
            "If the team accepts, the hold lapses.",
            # mechanical relay: subject noun is not a decision-making
            # group, so "says" stays mechanical
            "The relay says the code twice.",
            # group noun in object position
            "Ada forwards the draft to the team.",
    ):
        assert guard(None, event, "Ada") == event


def test_auxiliary_chain_decisions_are_detected():
    guard = _guard()
    for event, gone in (
            ("Bo has agreed to the terms.", "agreed to the terms"),
            ("Bo is agreeing to the plan.", "agreeing to the plan"),
            ("Bo will have accepted by then.", "accepted"),
            ("Bo has been agreeing all week.", "agreeing"),
    ):
        out = guard(None, event, "Ada")
        assert gone not in out, event
        assert AVAILABILITY_MARKER in out, event
        assert "Bo is now able to observe" in out, event


def test_auxiliary_nearby_shapes_are_not_over_blocked():
    guard = _guard()
    for event in (
            # negated chains are denials, not commitments
            "Bo has not agreed.",
            # BE/HAVE + been + participle keeps the name in patient
            # position (passive) -- not Bo's act
            "Bo has been chosen to lead.",
            # possession, not an auxiliary chain
            "Bo has a signed copy.",
            # bare modal prediction (pinned v1 semantics, kept)
            "Bo may agree later.",
    ):
        assert guard(None, event, "Ada") == event


def test_nominalization_decisions_are_detected():
    calls = []
    guard = _guard(lambda *args: calls.append(args))

    out = guard(None, "Bo's agreement to the terms closes the matter.",
                "Ada")
    assert "agreement to the terms" not in out
    assert "Bo is now able to observe" in out
    assert calls[-1][3] == ("Bo",)

    out = guard(None, "The acceptance by Bo settles it.", "Ada")
    assert "acceptance by Bo" not in out
    assert "Bo is now able to observe" in out
    assert calls[-1][3] == ("Bo",)

    out = guard(None, "Bo's commitment to attend is noted.", "Ada")
    assert "commitment to attend" not in out
    assert calls[-1][3] == ("Bo",)

    # A presupposing reference asserts the same accomplished decision
    # (stateless conservatism, documented in the guard module).
    out = guard(None, "Cam files Bo's refusal.", "Cam")
    assert "refusal" not in out
    assert calls[-1][3] == ("Bo",)


def test_nominalization_nearby_shapes_are_not_over_blocked():
    guard = _guard()
    for event in (
            # anticipation frames: the act has NOT happened yet
            "Ada waits for Bo's reply.",
            "Ada asks for Bo's agreement.",
            "Without Bo's signature, the file stays open.",
            # request verb directly before the possessive
            "Ada requests Bo's decision by noon.",
            # possessive of a non-act noun
            "Ada returns Bo's ledger to the shelf.",
            # the active player's own nominal
            "Ada's decision stands.",
    ):
        assert guard(None, event, "Ada") == event


def test_parenthetical_comma_decisions_are_detected():
    calls = []
    guard = _guard(lambda *args: calls.append(args))

    out = guard(None, "Bo, after some thought, agrees.", "Ada")
    assert "agrees" not in out
    assert "Bo is now able to observe" in out
    assert calls[-1][3] == ("Bo",)

    # A roster name inside the aside is NOT part of the subject chain.
    out = guard(None, "Bo, prompted by Ada, signs the form.", "Ada")
    assert "signs the form" not in out
    assert calls[-1][3] == ("Bo",)


def test_parenthetical_nearby_shapes_are_not_over_blocked():
    guard = _guard()
    for event in (
            # the active player's own decision with an aside
            "Ada, after some thought, agrees to proceed.",
            # aside followed by a non-act verb
            "Bo, according to the log, arrives at noon.",
    ):
        assert guard(None, event, "Ada") == event


def test_belief_verb_complements_are_not_blocked():
    calls = []
    guard = _guard(lambda *args: calls.append(args))
    for event in (
            # the review's over-block classes: the SPEAKER'S mental
            # state about another actor is the speaker's own content
            "Ada hopes Bo agrees.",
            "Ada believes Bo will reply.",
            "Ada doubts Bo signed.",
            "Ada expects that Bo agrees.",
    ):
        assert guard(None, event, "Ada") == event
    assert calls == []


def test_performative_content_requests_are_not_blocked():
    calls = []
    guard = _guard(lambda *args: calls.append(args))
    for event in (
            # a request ABOUT another actor's future act is the
            # requester's own act; the content must remain
            "Ada asks that Bo reply by Friday.",
            "Ada proposes that Bo sign first.",
            "Ada urges Bo to accept.",
    ):
        assert guard(None, event, "Ada") == event
    assert calls == []


def test_stance_boundary_still_catches_assertions():
    # Nearby caught shapes proving the stance suppression is narrow:
    # verbs that ASSERT the act (rather than hope for or request it)
    # remain violations.
    guard = _guard()
    out = guard(None, "Ada confirms Bo agrees.", "Ada")
    assert "agrees" not in out
    assert "Bo is now able to observe" in out

    out = guard(None, "Ada announces that Bo agreed to the terms.", "Ada")
    assert "agreed to the terms" not in out
    assert "Bo is now able to observe" in out


def test_hardened_classes_are_idempotent():
    guard = _guard()
    for event, active in (
            ("She agrees to the plan.", "Ada"),
            ("They commit to the deadline.", "Ada"),
            ("The team accepts the offer.", "Ada"),
            ("Bo has agreed to the terms.", "Ada"),
            ("Bo's agreement to the terms closes the matter.", "Ada"),
            ("The acceptance by Bo settles it.", "Ada"),
            ("Bo, after some thought, agrees.", "Ada"),
    ):
        once = guard(None, event, active)
        assert once != event
        assert guard(None, once, active) == once, event


# ---------------------------------------------------------------------------
# Unit: proxy attribution -- ":" / "--" subject boundaries (phases 8-11
# adversarial review, finding F1)
# ---------------------------------------------------------------------------


def test_reviewer_probe_colon_dash_attributions_are_caught():
    """The exact four phases-8-11 reviewer probes, verbatim: upstream's
    own attribution separators must not smuggle another actor's reply,
    agreement, or vote past the guard."""
    guard = make_agency_guard(("Alex", "Morgan", "Sam"))
    for event, affected in (
            ("Send the note asking for a call. Morgan: agrees to the "
             "plan.", "Morgan"),
            ("Send the note asking for a call. Morgan -- agrees to the "
             "plan.", "Morgan"),
            ("Send the note asking for a call. Morgan: Reply agreeing "
             "to a fifteen-minute conversation next week.", "Morgan"),
            ("Present the revised plan. Sam: Vote yes.", "Sam"),
    ):
        out = guard(None, event, "Alex")
        assert out != event, event
        # The attributed segment is gone, the attempt prefix survives,
        # and the availability sentence names the affected actor.
        assert f"{affected}:" not in out, event
        assert f"{affected} --" not in out, event
        assert out.startswith(("Send the note asking for a call.",
                               "Present the revised plan.")), event
        assert f"{affected} {AVAILABILITY_MARKER}" in out, event


def test_proxy_attribution_forms_are_caught():
    calls = []
    guard = _guard(lambda *args: calls.append(args))

    # Leading other-name attribution: the event claims to BE the other
    # actor's turn outright.
    out = guard(None, "Bo: Vote yes.", "Ada")
    assert out == ("Bo is now able to observe this and to respond in "
                   "their own turn.")
    assert calls[-1][3] == ("Bo",)

    # Attributed speech: no act verb required -- choosing what to say
    # is itself a voluntary decision.
    out = guard(None, "Ada posts the sheet. Bo: 'Count me in for "
                      "Tuesday.'", "Ada")
    assert "Count me in" not in out
    assert "Ada posts the sheet." in out
    assert "Bo is now able to observe" in out

    # A multi-sentence attributed segment is removed WHOLE: upstream
    # defines no closing delimiter, so everything to the line break is
    # the claimed content -- no trailing sentence may survive as
    # anyone else's text.
    out = guard(None, "Ada opens the review. Bo: I accept the terms. "
                      "I will sign tomorrow.", "Ada")
    assert out == ("Ada opens the review. Bo is now able to observe "
                   "this and to respond in their own turn.")

    # The dash form of the same segment.
    out = guard(None, "Ada opens the review. Bo -- I accept the terms.",
                "Ada")
    assert "accept the terms" not in out
    assert "Bo is now able to observe" in out

    # A name chain before the marker binds every non-active member.
    out = guard(None, "Bo and Cam: We accept the offer.", "Ada")
    assert "accept the offer" not in out
    assert "Bo is now able to observe" in out
    assert "Cam is now able to observe" in out
    assert calls[-1][3] == ("Bo", "Cam")

    # Multiple markers in one event: every proxied actor is offered its
    # own turn.
    out = guard(None, "Bo: I vote yes. Cam: I vote yes.", "Ada")
    assert "vote yes" not in out
    assert "Bo is now able to observe" in out
    assert "Cam is now able to observe" in out


def test_active_players_own_attribution_passes():
    calls = []
    guard = _guard(lambda *args: calls.append(args))
    for event in (
            # the whole text as one leading attribution to the active
            # player -- the upstream turn format -- changes not at all
            "Ada: agrees to the revised terms.",
            "Ada: Reply agreeing to the plan and file the note.",
            # the same under the upstream putative framing the guard
            # sees as a resolution step
            "Putative event to resolve:  Ada: sends the outline to Bo.",
            # mid-text self-attribution claims nobody else's agency
            "The clock strikes nine. Ada: begins the review.",
            # the dash form of the active player's own attribution
            "Ada -- opens the ledger and reads.",
    ):
        assert guard(None, event, "Ada") == event
    assert calls == []


def test_attribution_nearby_shapes_are_not_over_blocked():
    calls = []
    guard = _guard(lambda *args: calls.append(args))
    for event in (
            # a colon after a non-roster word is not an attribution
            "Agenda: review the plan.",
            "Ada notes one thing: the schedule holds.",
            # recipient/epistolary colon after a non-agent lead word:
            # the quoted content is the SPEAKER'S message TO the name
            "Ada sends a note to Bo: 'please review the draft.'",
            "Ada leaves a message for Bo: 'call when free.'",
            # performative-request colon after a stance verb (review
            # finding 6 class): the question is the speaker's own
            "Ada asks Bo: 'will you sign?'",
            # received-content frame: DOCUMENTED residual of the
            # object-position exemption (see the guard docstring)
            "Ada reads the note from Bo: 'I agree.'",
            # digits around a colon are nobody's attribution
            "The review runs from 9:15 to 10:00.",
    ):
        assert guard(None, event, "Ada") == event
    assert calls == []


def test_quoted_attribution_assertion_stays_caught():
    # Consistency with the reported-speech line: an assertion-shaped
    # report is caught ("confirms Bo agrees"), so a quoted-stance colon
    # form lands on the caught side of that same line.
    guard = _guard()
    out = guard(None, 'Ada quotes Bo: "I agree to the terms."', "Ada")
    assert "I agree to the terms" not in out
    assert "Ada quotes" in out
    assert "Bo is now able to observe" in out


def test_proxy_attribution_scopes_to_the_line_break():
    guard = _guard()
    out = guard(None, "Bo: I refuse the offer.\nAda continues the "
                      "briefing.", "Ada")
    # The attributed segment dies at the newline; the next line's
    # narration survives, and the availability sentence is appended.
    assert "refuse the offer" not in out
    assert "Ada continues the briefing." in out
    assert "Bo is now able to observe" in out


def test_proxy_attribution_escalation_record_shape():
    calls = []
    guard = _guard(lambda *args: calls.append(args))
    event = "Present the revised plan. Bo: Vote yes."
    out = guard(None, event, "Ada")
    assert calls == [(event, out, "Ada", ("Bo",))]


def test_proxy_attribution_is_idempotent():
    guard = _guard()
    for event, active in (
            ("Send the note. Bo: agrees to the plan.", "Ada"),
            ("Send the note. Bo -- agrees to the plan.", "Ada"),
            ("Bo: Vote yes.", "Ada"),
            ("Bo: I vote yes. Cam: I vote yes.", "Ada"),
            ("Bo: I refuse.\nAda continues the briefing.", "Ada"),
            ("Bo and Cam: We accept the offer.", "Ada"),
    ):
        once = guard(None, event, active)
        assert once != event
        assert guard(None, once, active) == once, event


# ---------------------------------------------------------------------------
# Unit: the object-position exemption is DETERMINER-TRANSPARENT
# (the a16z live-run defect: a role-shaped roster name takes an article,
# which defeated the lead-word test, so the guard truncated the sentence
# at the determiner and deleted the ACTIVE actor's own quoted message)
# ---------------------------------------------------------------------------

#: role-shaped roster: names that are natural determiner-taking noun
#: phrases, which is what the defect needed and a personal-name cast
#: never produces
ROLE_ROSTER = ("Duty Officer", "Records Keeper", "Ada")


def _role_guard(recorder=None):
    return make_agency_guard(ROLE_ROSTER, escalate=recorder)


def test_determined_recipient_keeps_the_object_position_exemption():
    """The three-probe triple: bare name, the docstring's own example,
    and the determined form must all pass through BYTE-IDENTICALLY.

    Pre-fix the third probe was rewritten to "... sends a message to
    the." plus an availability sentence, destroying the active actor's
    own quoted content."""
    calls = []
    guard = _role_guard(lambda *args: calls.append(args))
    bare = ('Duty Officer sends a message to Records Keeper: '
            '"the schedule holds."')
    documented = "Ada sends a note to Bo: 'call me'"
    determined = ('Duty Officer sends a message to the Records Keeper: '
                  '"the schedule holds."')
    assert guard(None, bare, "Duty Officer") == bare
    assert _guard()(None, documented, "Ada") == documented
    assert guard(None, determined, "Duty Officer") == determined
    # the quoted content the ACTIVE actor authored survives verbatim
    assert '"the schedule holds."' in guard(None, determined, "Duty Officer")
    assert calls == []


def test_determiner_transparency_covers_the_documented_frame_families():
    calls = []
    guard = _role_guard(lambda *args: calls.append(args))
    for event in (
            # every non-agent lead-word family, with an article
            'Duty Officer leaves a message for the Records Keeper: '
            '"call when free."',
            "Duty Officer reads the note from the Records Keeper: "
            "'I agree.'",
            # conditional frame (a condition is not a commitment)
            "If the Records Keeper agrees, the hold lapses.",
            "The offer stands until the Records Keeper accepts it.",
            # speaker-stance frame about another actor's future act
            "Duty Officer hopes the Records Keeper agrees to the plan.",
            "Duty Officer asks that the Records Keeper reply by Friday.",
            # possessive determiner in the same slot
            "Duty Officer forwards the file to their Records Keeper: "
            "'for the record.'",
    ):
        assert guard(None, event, "Duty Officer") == event, event
    assert calls == []


def test_determiner_transparency_does_not_weaken_genuine_protection():
    """The protection itself is unchanged: a real proxy attribution and a
    real committed decision for another actor are still rewritten, with
    or without a determiner."""
    guard = _role_guard()
    for event, affected, stolen in (
            # sentence-initial determined subject: the lookback hits
            # punctuation, so the determiner exempts nothing
            ("Duty Officer sends a message to the Records Keeper. The "
             "Records Keeper agrees to the offer.",
             "Records Keeper", "agrees to the offer"),
            # the lead's second probe shape, through a complementizer
            ("Duty Officer tells the Records Keeper that the Records "
             "Keeper accepts.",
             "Records Keeper", "accepts"),
            # a determined name after a clause link is still an agent
            ("Duty Officer hands over the ledger, and the Records Keeper "
             "signed it.",
             "Records Keeper", "signed"),
            # bare proxy attribution, determined or not
            ("Duty Officer opens the review. The Records Keeper: I accept "
             "the terms.",
             "Records Keeper", "I accept the terms"),
            # an adjective between determiner and name is a documented
            # residual and stays on the CAUGHT side
            ("Duty Officer sends a message to the acting Records Keeper: "
             "'noted.'",
             "Records Keeper", "noted"),
    ):
        out = guard(None, event, "Duty Officer")
        assert out != event, event
        assert stolen not in out, event
        assert f"{affected} {AVAILABILITY_MARKER}" in out, event


def test_determiner_transparency_is_idempotent_and_escalates_once():
    calls = []
    guard = _role_guard(lambda *args: calls.append(args))
    exempt = ('Duty Officer sends a message to the Records Keeper: '
              '"the schedule holds."')
    assert guard(None, guard(None, exempt, "Duty Officer"),
                 "Duty Officer") == exempt
    assert calls == []
    caught = ("Duty Officer files the report. The Records Keeper agrees "
              "to the terms.")
    once = guard(None, caught, "Duty Officer")
    assert once != caught
    assert guard(None, once, "Duty Officer") == once
    assert len(calls) == 1
    assert calls[0][2] == "Duty Officer"
    assert calls[0][3] == ("Records Keeper",)


# ---------------------------------------------------------------------------
# Integration: full stock-Concordia loop (Phase 4 pattern)
# ---------------------------------------------------------------------------

MAX_STEPS = 2  # one turn per actor under the fixed order

PROBE_WORLD = {
    "contract_type": "compiled_decision_world",
    "schema_version": SCHEMA_VERSION,
    "world_id": "w_agency_guard_probe",
    "actors": [
        {"actor_id": "first_party", "name": "Ada",
         "private_context": "Ada opens the exchange."},
        {"actor_id": "second_party", "name": "Bo",
         "private_context": "Bo answers in his own words."},
    ],
    "shared_context": "Ada and Bo share one open request.",
    "starting_events": [],
    "start_time": "2026-09-02T08:00:00Z",
    "cutoff": "2026-09-04T18:00:00Z",
    "success_criteria": "The second party's own decision appears in the "
                        "trace.",
    "intervention_insertion_point": {"actor_id": "first_party"},
    "compiler_provenance": {
        "source": "manual_inline_test",
        "version": "inline_v1",
        "evidence_mode": "manual",
        "artifact_hashes": {},
    },
}
SPEC = EvaluatorSpec(primary_metric="second_party_decision",
                     secondary_metrics=())

#: the active actor's attempt embeds the OTHER actor's agreement
VIOLATING_TURN = ("sends the outline PROP_77 to Bo, and Bo agrees to "
                  "attend GHOST_ACCEPT_9")
#: the affected actor's OWN scripted decision, made in his own turn
OWN_DECISION_TURN = "agrees to attend and asks one question OWN_DECISION_5"

CONTROL_TURNS = {
    "first_party": "opens with request REQ_1",
    "second_party": "answers request REQ_1 with OK_1",
}


def _world(world_id):
    data = dict(PROBE_WORLD)
    data["world_id"] = world_id
    return CompiledDecisionWorld.from_dict(data)


def _models(first_turn, second_turn):
    return {
        "first_party": StrictScriptedModel(
            [("What does Ada do next?", [first_turn])]),
        "second_party": StrictScriptedModel(
            [("What does Bo do next?", [second_turn])]),
        "gm": StrictScriptedModel([aware_rule(["Ada", "Bo"])]),
    }


def _run_once(plan, first_turn, second_turn):
    models = _models(first_turn, second_turn)
    with seeded_determinism(SEED):
        result = runner.run_branch(
            plan,
            actor_models={"first_party": models["first_party"],
                          "second_party": models["second_party"]},
            gm_model=models["gm"])
    return models, result


def test_forced_agreement_is_split_and_actor_decides_in_own_turn():
    plan = planner.build_initialization_plan(
        _world("w_agency_guard_probe"), SPEC, max_steps=MAX_STEPS)
    assert plan.gm_config["guard_slot"] == GUARD_SLOT_VALUE

    runs = [_run_once(plan, VIOLATING_TURN, OWN_DECISION_TURN)
            for _attempt in range(3)]

    for _models_used, result in runs:
        assert result["infrastructure_errors"] == []
        assert result["steps_completed"] == MAX_STEPS

    # Three clean runs, byte-identical trace AND identical interventions.
    assert len({run_signature(result) for _m, result in runs}) == 1
    assert len({json.dumps(result["guard_interventions"], sort_keys=True)
                for _m, result in runs}) == 1

    models, result = runs[0]
    committed = result["committed_events"]
    assert len(committed) == 3  # premise + two resolved turns

    # The forged agreement NEVER commits, anywhere in the event stream.
    for row in committed:
        assert "GHOST_ACCEPT_9" not in row
    # ...and never reaches any actor's memory or the affected actor's
    # model prompts (the GM's own [putative_event] bookkeeping row is the
    # only place the raw attempt remains, as an attempt).
    assert "GHOST_ACCEPT_9" not in json.dumps(result["actor_memories"])
    assert "GHOST_ACCEPT_9" not in all_prompt_text(models["second_party"])
    assert any(builder.PUTATIVE_EVENT_TAG in row and "GHOST_ACCEPT_9" in row
               for row in result["gm_memory"])

    # The committed first-turn event carries the attempt VERBATIM plus
    # the availability form (marker containment, never full equality).
    ada_row = next(row for row in committed if "PROP_77" in row)
    assert "Ada: sends the outline PROP_77 to Bo" in ada_row
    assert AVAILABILITY_MARKER in ada_row
    assert "Bo is now able to observe" in ada_row

    # The affected actor's own turn actually happened: his prompt
    # contained the availability observation (not the forged decision),
    # and HIS scripted decision is what landed in the trace.
    bo_prompts = models["second_party"].prompts
    assert len(bo_prompts) == 1
    assert AVAILABILITY_MARKER in bo_prompts[0]
    assert "PROP_77" in bo_prompts[0]
    bo_putative = [i for i, row in enumerate(result["gm_memory"])
                   if builder.PUTATIVE_EVENT_TAG in row and "Bo:" in row
                   and "OWN_DECISION_5" in row]
    assert bo_putative, "the affected actor never took his own turn"
    bo_row = next(row for row in committed if "OWN_DECISION_5" in row)
    assert "Bo: agrees to attend" in bo_row
    assert committed.index(ada_row) < committed.index(bo_row)

    # The runner recorded the intervention with the right step/actors.
    interventions = result["guard_interventions"]
    assert len(interventions) == 1
    record = interventions[0]
    assert record["step"] == 1
    assert record["active"] == "Ada"
    assert record["affected"] == ["Bo"]
    assert len(record["original_excerpt"]) <= 120
    assert len(record["rewritten_excerpt"]) <= 120
    assert "and Bo agrees" in record["original_excerpt"]
    assert "Bo is now able" in record["rewritten_excerpt"]


def test_clean_control_run_matches_guard_disabled_baseline():
    """Prove the Concordia loop still works: with no violation, the
    default-enabled guard produces a trace byte-identical to the
    guard-disabled (Phase 4 identity-slot) configuration and records
    zero interventions."""
    world = _world("w_agency_guard_control")
    enabled_plan = planner.build_initialization_plan(
        world, SPEC, max_steps=MAX_STEPS)
    disabled_plan = planner.build_initialization_plan(
        world, SPEC, max_steps=MAX_STEPS, agency_guard_enabled=False)
    assert enabled_plan.gm_config["guard_slot"] == GUARD_SLOT_VALUE
    assert disabled_plan.gm_config["guard_slot"] == "identity"

    _enabled_models, enabled_result = _run_once(
        enabled_plan, CONTROL_TURNS["first_party"],
        CONTROL_TURNS["second_party"])
    _disabled_models, disabled_result = _run_once(
        disabled_plan, CONTROL_TURNS["first_party"],
        CONTROL_TURNS["second_party"])

    for result in (enabled_result, disabled_result):
        assert result["infrastructure_errors"] == []
        assert result["steps_completed"] == MAX_STEPS
        assert result["guard_interventions"] == []

    # Identical committed events, actor memories, event trace, step
    # count, and terminal status -- the guard is a pure pass-through on
    # clean traffic.
    assert run_signature(enabled_result) == run_signature(disabled_result)

    committed = enabled_result["committed_events"]
    assert any("REQ_1" in row for row in committed)
    assert any("OK_1" in row for row in committed)
    assert AVAILABILITY_MARKER not in json.dumps(committed)
