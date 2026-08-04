"""The settling experiment: does a LIVE sender enact its candidate when
the send is not already pre-narrated?

Experiment-only.  Nothing here is imported by production code and nothing
here authors an actor turn: the ONE piece of text this module supplies is
the game master's observer-ROUTING answer, and it supplies it only to
remove a known confound (see :class:`ForcedRosterObserverGM`).

Why this experiment exists
--------------------------
The delivery root-cause investigation (``.agent-run/DECISIONS.md``,
"Delivery root cause 2026-08-04") established that the engine SUGGESTS an
intervention to the insertion actor rather than ENACTING it: the candidate
text is appended to that actor's initial observations and to nothing else,
so it propagates only if that actor's own model reproduces it.  The probe
that established this ran three world variants -- but all three used a
CONTENT-BLIND hash-derived sender, under which candidate text can never
propagate by construction.  They therefore could not test the one live
hypothesis that matters, and the investigation said so itself:

    R1-strong: the sender does not enact the candidate because the
    compiled world already NARRATES the send as having happened
    ("Beckett Zahedi sends the prepared message to Peter Thiel", a
    starting event), so the live sender, told the send is done, has
    nothing left to do and waits.

    R3: the sender does not enact the candidate because of the engine's
    intervention semantics -- a free-choice sender simply need not
    restate a message it was merely told about, pre-narration or not.

Those two make DIFFERENT predictions about the practical fix.  Under
R1-strong the remedy is compiler prompt hygiene (stop teaching the
pre-narrated sender-only send event); under R3 the remedy is an engine
semantic change (enact the intervention, at the cost of the insertion
actor's freedom to decline).  This module runs the two-arm live
experiment that separates them.

The design
----------
Two arms, identical in every respect except the starting event, both on
the FROZEN Peter world (the same compiler artifact directory scenario 1
used, re-adapted by deterministic code):

* **Arm A (pre-narrated)** -- the world exactly as compiled, whose single
  starting event is ``Beckett Zahedi sends the prepared message to Peter
  Thiel.`` with ``visible_to: [beckett_zahedi]``.
* **Arm B (not pre-narrated)** -- byte-identical world with
  ``starting_events: []`` (the shape the frozen manual fixtures use).

Same candidate, same seed, same model configuration, same step budget,
same live actor models, same recorder.  Live sampling varies, so each arm
runs three times and the result is reported as a rate over n=3, never as
a single sample.

The one forced answer, and why
------------------------------
The second recorded defect (D1, closed at ``c5a81214``) was that a game
master's free-text observer answer that does not match a roster name
routes the event nowhere.  If that fired inside this experiment it would
be indistinguishable from "the sender did not enact the candidate", so
the experiment would measure the wrong thing.  :class:`ForcedRosterObserverGM`
therefore answers the observer-routing question -- and ONLY that question
-- with the branch's full roster, so every committed event reaches every
actor and the routing gate cannot confound the measurement.  Every forced
answer is recorded verbatim in ``forced_observer_control.json``; every
other game-master call and every single actor turn goes to the live
provider through the ordinary recorder.
"""

from __future__ import annotations

import copy
import re

from . import recorder as recorder_lib

#: the upstream observer-routing question, verbatim from
#: ``concordia/components/game_master/event_resolution.py`` at the pinned
#: SHA.  The forced control fires on THIS question and nothing else.
OBSERVER_QUESTION = ("Which entities are aware of the event? Answer with "
                     "a comma-separated list of entity names.")

#: arm identifiers and what each one is
ARMS = {
    "a": ("pre_narrated",
          "the world exactly as the live compiler emitted it: one "
          "starting event narrating the send, visible to the sender only"),
    "b": ("not_pre_narrated",
          "the same world with starting_events removed, so nothing tells "
          "the sender the send already happened"),
}


class ForcedObserverControlError(RuntimeError):
    """The forced observer control could not be applied as declared."""


def arm_world(world, arm: str):
    """The :class:`CompiledDecisionWorld` for one arm.

    Arm ``a`` returns the frozen world unchanged.  Arm ``b`` returns the
    same world with ``starting_events`` emptied, rebuilt THROUGH the
    contract gate (``from_dict``) so the arm-B world is a fully validated
    contract instance and not a hand-patched object.  Every other field,
    including ``world_id`` and the compiler provenance, is byte-identical,
    which is what makes the two arms comparable.
    """
    from sworldmodel.decision.contracts import CompiledDecisionWorld

    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; expected one of "
                         f"{sorted(ARMS)}")
    if arm == "a":
        return world
    data = copy.deepcopy(world.to_dict())
    if not data["starting_events"]:
        raise ForcedObserverControlError(
            "arm B is defined as 'the same world with its starting event "
            "removed', but the frozen world has no starting event to "
            "remove: the two arms would be identical and the experiment "
            "would measure nothing")
    data["starting_events"] = []
    return CompiledDecisionWorld.from_dict(data)


def arm_difference(world_a, world_b) -> dict:
    """The complete field-level difference between the two arm worlds --
    recorded so a reader can check the 'identical except the starting
    event' claim rather than take it on trust."""
    left = world_a.to_dict()
    right = world_b.to_dict()
    differing = sorted(key for key in set(left) | set(right)
                       if left.get(key) != right.get(key))
    return {
        "fields_that_differ": differing,
        "arm_a_starting_events": left.get("starting_events"),
        "arm_b_starting_events": right.get("starting_events"),
        "arm_a_content_hash": world_a.content_hash(),
        "arm_b_content_hash": world_b.content_hash(),
        "identical_except_starting_events": differing == ["starting_events"],
    }


def validate_roster(roster_names) -> tuple:
    """The roster the forced answer will name, or a loud refusal.

    A control that broadcasts to nobody would silently reproduce the very
    routing failure it exists to remove, so an empty roster is refused
    rather than defaulted.
    """
    names = tuple(roster_names or ())
    if not names:
        raise ForcedObserverControlError(
            "the forced observer control needs a non-empty roster: "
            "broadcasting to nobody would silently reproduce the "
            "observer-routing failure this control exists to remove")
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ForcedObserverControlError(
            f"every roster name must be a non-empty string; got {names!r}")
    return names


class ForcedRosterObserverGM(recorder_lib.RecordedDeepSeekChatModel):
    """The recorded game-master model with the observer-routing answer
    forced to the full roster.

    Rationale in the module docstring.  The interception is exact: the
    prompt must contain :data:`OBSERVER_QUESTION` verbatim.  Any other
    game-master call -- now or if upstream adds one -- falls through to
    the ordinary live, recorded path, so the control cannot silently grow
    beyond routing.

    The forced answer is the roster joined by ``", "``, which is what the
    upstream call site splits on, so it exercises the real routing code
    (``RosterValidatedMakeObservation.add_to_queue``) by the exact-match
    path rather than bypassing it.
    """

    def __init__(self, *args, roster_names, control_log: list, **kwargs):
        names = validate_roster(roster_names)
        super().__init__(*args, **kwargs)
        self.roster_names = names
        self.control_log = control_log

    @property
    def forced_answer(self) -> str:
        return ", ".join(self.roster_names)

    def sample_text(self, prompt: str, *, max_tokens=None, terminators=(),
                    **kwargs):
        if OBSERVER_QUESTION in (prompt or ""):
            answer = self.forced_answer
            self.control_log.append({
                "branch_id": self.branch_id,
                "step": self.cursor.on_gm_call(),
                "intercepted_question": OBSERVER_QUESTION,
                "forced_answer": answer,
                "prompt_tail": (prompt or "")[-400:],
                "provider_called": False,
            })
            return answer
        return super().sample_text(prompt, max_tokens=max_tokens,
                                   terminators=terminators, **kwargs)


def forced_observer_model_factory(context, *, api_key, world, branch_ids,
                                  capture: dict, cursors: dict,
                                  control_log: list,
                                  actor_max_tokens: int = 400,
                                  gm_max_tokens: int = 400):
    """``model_factory(candidate, branch_seed)`` with LIVE actors and a
    roster-broadcasting game master.

    Mirrors :func:`recorder.live_model_factory` exactly -- same recorded
    actor models, same per-branch :class:`recorder.StepCursor`, same
    system hints -- and substitutes :class:`ForcedRosterObserverGM` for
    the game master.  The actor seam is untouched: every actor turn in
    this experiment is a live provider completion.
    """
    names = {actor.actor_id: actor.name for actor in world.actors}
    roster = validate_roster(
        [name for _actor_id, name in sorted(names.items())])

    def factory(candidate, branch_seed):
        candidate_id = candidate.candidate_id
        branch_id = branch_ids[candidate_id]
        cursor = recorder_lib.StepCursor()
        cursors[candidate_id] = cursor
        actor_models = {
            actor_id: recorder_lib.RecordedDeepSeekChatModel(
                context, api_key=api_key,
                system_hint=recorder_lib.ACTOR_SYSTEM_HINT.format(name=name),
                role="actor", actor_id=actor_id, actor_name=name,
                branch_id=branch_id, cursor=cursor,
                seam_name=f"actor:{actor_id}",
                max_tokens=actor_max_tokens)
            for actor_id, name in sorted(names.items())}
        gm_model = ForcedRosterObserverGM(
            context, api_key=api_key,
            system_hint=recorder_lib.GM_SYSTEM_HINT, role="game_master",
            actor_id=None, actor_name=None, branch_id=branch_id,
            cursor=cursor, seam_name="game_master",
            max_tokens=gm_max_tokens, roster_names=roster,
            control_log=control_log)
        capture[candidate_id] = {
            "branch_id": branch_id, "branch_seed": branch_seed,
            "actors": actor_models, "gm": gm_model, "cursor": cursor,
            "forced_observer_answer": gm_model.forced_answer,
        }
        return actor_models, gm_model

    return factory


def sender_first_turn(calls, sender_name: str) -> dict:
    """The sender's FIRST live turn in one branch, verbatim.

    ``calls`` is that branch's recorded call ledger.  This is the single
    observation the experiment turns on: what the live sender actually did
    on turn one, quoted rather than characterised.
    """
    for call in calls:
        if call.get("role") != "actor":
            continue
        if call.get("actor_name") != sender_name:
            continue
        if call.get("error"):
            continue
        return {
            "call_id": call.get("call_id"),
            "step": call.get("step"),
            "actor_name": call.get("actor_name"),
            "text": call.get("response_raw") or "",
        }
    return {"call_id": None, "step": None, "actor_name": sender_name,
            "text": None,
            "unavailable": "no successful sender actor call was recorded"}


_TOKEN = re.compile(r"[A-Za-z0-9]+")


def longest_common_substring_chars(left: str, right: str) -> int:
    """Length in characters of the longest run shared by two texts.

    Content-blind and symmetric: it says how much of the candidate the
    sender copied WITHOUT any judgement about what the copied part means.
    """
    left = left or ""
    right = right or ""
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    best = 0
    for i in range(1, len(left) + 1):
        current = [0] * (len(right) + 1)
        left_char = left[i - 1]
        for j in range(1, len(right) + 1):
            if left_char == right[j - 1]:
                current[j] = previous[j - 1] + 1
                if current[j] > best:
                    best = current[j]
        previous = current
    return best


def token_overlap_ratio(left: str, right: str) -> float:
    """Jaccard overlap of the two texts' case-folded alphanumeric token
    sets.  Content-blind; reported so a reader can see how much of the
    candidate's vocabulary survived into the sender's own wording."""
    left_tokens = {token.casefold() for token in _TOKEN.findall(left or "")}
    right_tokens = {token.casefold() for token in _TOKEN.findall(right or "")}
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    return round(len(left_tokens & right_tokens) / len(union), 4)


def enactment_check(*, first_turn_text, candidate_action) -> dict:
    """Did the sender's own first turn REPRODUCE distinctive candidate
    text?

    The PRIMARY reading, declared before the runs, is verbatim: a
    candidate fragment counts only if it appears in the sender's turn
    character-for-character, using the harness's existing fragment method
    (the same one the delivery checks use) so the number is comparable
    with them.  A paraphrase is NOT enactment for this purpose, and the
    unmatched-fragment example is recorded so a reader can see how close
    the turn came.

    Two CONTENT-BLIND overlap numbers are recorded next to it -- the
    longest shared character run and the token Jaccard.  They were added
    after the first live sample showed why a bare yes/no would mislead: a
    sender can perform the send and still author its own words, and the
    binary reading alone would report that identically to a sender that
    simply waited.  Neither number enters the verdict; both apply
    identically to both arms, and the sender's full turn is quoted in the
    result document so a reader can check every reading against the text.
    """
    from . import delivery as delivery_lib

    fragments = delivery_lib.candidate_fragments(candidate_action or "")
    text = delivery_lib.normalise(first_turn_text or "")
    action = delivery_lib.normalise(candidate_action or "")
    found = [fragment for fragment in fragments if fragment in text]
    return {
        "fragments_tested": len(fragments),
        "fragments_reproduced_in_sender_first_turn": len(found),
        "example_reproduced": found[0] if found else None,
        "example_not_reproduced": (
            None if not fragments or len(found) == len(fragments)
            else next(f for f in fragments if f not in text)),
        "sender_enacted_candidate_verbatim": bool(found),
        "longest_shared_run_chars": longest_common_substring_chars(action,
                                                                   text),
        "candidate_token_overlap_ratio": token_overlap_ratio(action, text),
        "method": ("candidate sentence/line runs of at least "
                   f"{delivery_lib.MIN_FRAGMENT_CHARS} characters, "
                   "whitespace-normalised, searched verbatim in the "
                   "sender's own first-turn completion; the two overlap "
                   "numbers are content-blind and do not enter the "
                   "verdict"),
    }


__all__ = ["OBSERVER_QUESTION", "ARMS", "ForcedObserverControlError",
           "validate_roster", "arm_world", "arm_difference",
           "ForcedRosterObserverGM", "forced_observer_model_factory",
           "sender_first_turn", "enactment_check",
           "longest_common_substring_chars", "token_overlap_ratio"]
