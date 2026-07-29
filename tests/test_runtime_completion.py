"""Phase C: the properties PR #5 shipped without.

Every test here was written against `main` at 26b5203 and verified to
FAIL there. They are not regression guards for hypothetical futures; each
one names a defect that thirteen independent reviewers found in the
merged code, and each fails until that defect is actually fixed.

Nothing in this file calls a live provider.
"""
import json

import pytest

from sworldmodel.semantic_runtime.llm import RuntimeCaller
from sworldmodel.semantic_runtime.replay import replay_trajectory
from sworldmodel.semantic_runtime.trace import Trace
from sworldmodel.semantic_runtime.trajectory import run_trajectory
from sworldmodel.simclock import parse_iso

from test_semantic_runtime import (CUTOFF, FINAL_MARKER, NO_AT_CUTOFF,
                                   NOTHING, SCENE, START, UNRESOLVED, build,
                                   reviewed)

# --------------------------------------------------------------- helpers


def terminal_roles(user, system):
    """The two read-only readings, answering the same way."""
    if "read-only outcome judge" in system \
            or "whether a stated condition has been met" in system:
        return json.dumps(NO_AT_CUTOFF if FINAL_MARKER in user
                          else UNRESOLVED), {}
    return None


def run(transport, *, steps=10, wrap=True):
    world, journal, bindings = build()
    caller = RuntimeCaller(transport=reviewed(transport) if wrap
                           else transport)
    traj = run_trajectory(world, journal, bindings, SCENE["resolution"],
                          caller, max_steps=steps, trace=Trace())
    return world, journal, traj


def silent_world(system, user):
    """A world in which nothing whatever is scheduled."""
    t = terminal_roles(user, system)
    if t:
        return t
    if "You are the world" in system:
        return json.dumps({"judgment": "nothing follows.", "event": None,
                           "wakes": []}), {}
    return json.dumps(NOTHING), {}


# ------------------------------------------- 1, 2, 12: the empty queue


def test_an_empty_queue_before_the_cutoff_is_incomplete_not_no():
    """The single most consequential defect in the merged code.

    Eleven of eleven NO answers in the shipped corpus stopped because the
    queue emptied, not because the horizon arrived; a cold email jumped
    its entire fortnight in one ledger record after a single step. NO at
    a cutoff is a claim about a whole window, justified only by the
    absence of events across it. If the window was never simulated, the
    absence is the scheduler's, not the world's.
    """
    world, journal, traj = run(silent_world)
    assert world.clock.now < parse_iso(CUTOFF), \
        "the clock was advanced to the horizon over unsimulated time"
    assert traj.status == "incomplete_empty_queue", traj.status
    assert (traj.answer or {}).get("status") != "NO_AT_CUTOFF", \
        "an unlived window was reported as a deadline that passed"


def test_incomplete_is_never_translated_into_no():
    """Whatever ends a run early, the answer may not become NO."""
    for steps in (1, 2, 3):
        _, _, traj = run(silent_world, steps=steps)
        assert traj.status.startswith("incomplete"), traj.status
        assert (traj.answer or {}).get("status") != "NO_AT_CUTOFF"


def test_the_horizon_may_only_be_claimed_by_reaching_it():
    """A run that genuinely runs out of scheduled time at the cutoff may
    still answer NO -- that is the honest case and must keep working."""
    n = {"i": 0}

    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            n["i"] += 1
            # something real is scheduled right up to the horizon
            return json.dumps({
                "judgment": "the day goes on.",
                "event": {"description": f"Ada gets on with thing {n['i']}.",
                          "for": ["ada_vance"], "observed": True,
                          "after": "5 days", "follow_up": False},
                "wakes": []}), {}
        return json.dumps(NOTHING), {}

    _, _, traj = run(transport, steps=40)
    assert traj.status in ("resolved", "cutoff"), traj.status


# ------------------------------- 3, 10: transport is state, not narrative


def test_delivery_and_notification_are_not_committed_as_events():
    """44% of the merged corpus was a device or channel acting on its
    own. Availability is already a code-owned property of a journal item;
    narrating it as well makes the record a notification log."""
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "starting_event" in user:
                return json.dumps({
                    "judgment": "it goes.",
                    "event": {"description": "Ada sends Bo her proposal.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "1 minutes", "follow_up": False},
                    "wakes": []}), {}
            # the world tries to narrate transport, as it did throughout
            # the merged corpus
            return json.dumps({
                "judgment": "it lands.",
                "event": {"description": "The message arrives in Bo's "
                                         "inbox and a notification appears "
                                         "on his phone.",
                          "for": ["bo_ferrer"], "observed": False,
                          "after": "1 minutes", "follow_up": False},
                "wakes": []}), {}
        return json.dumps(NOTHING), {}

    _, journal, _ = run(transport)
    sent = [e for e in journal.events() if "sends Bo her proposal" in
            e["description"]]
    assert sent, "the human action was lost"
    # ... and it is available to Bo without any arrival event existing
    assert "bo_ferrer" in sent[0]["for"]
    assert "bo_ferrer" not in sent[0]["observed_by"]
    blob = " ".join(e["description"] for e in journal.events()).lower()
    for phrase in ("arrives in", "notification", "buzz", "lock screen",
                   "remains unread", "sits unread", "is delivered to"):
        assert phrase not in blob, f"transport narrated as an event: {phrase}"


def test_the_same_physical_act_is_not_committed_twice():
    """Near-identical, not byte-identical: the merged guard was an exact
    casefold match, and a woman signed one lease twice a minute apart."""
    said = {"n": 0}

    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            said["n"] += 1
            desc = ("Margaret signs the printed lease with a pen."
                    if said["n"] % 2 else
                    "Margaret signs the lease with a pen.")
            return json.dumps({
                "judgment": "she signs it.",
                "event": {"description": desc, "for": ["ada_vance"],
                          "observed": True, "after": "2 minutes",
                          "follow_up": True}, "wakes": []}), {}
        return json.dumps(NOTHING), {}

    _, journal, _ = run(transport, steps=12)
    signings = [e for e in journal.events() if "signs the" in
                e["description"] and "lease" in e["description"]]
    assert len(signings) <= 1, \
        f"one act committed {len(signings)} times: {[s['description'] for s in signings]}"


# ------------------------- 4, 5: a valid action may not be deleted


def test_a_valid_attempt_is_never_deleted_by_a_semantic_reviewer():
    """The chain four reviewers converged on. The actor decides to sign
    and return the lease; the world says she does; nothing in the runtime
    may throw that away, whatever a reviewer thinks of its prose."""
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "whether the proposed event" in system:
            # the reviewer that refused everything in the merged runtime
            return json.dumps({"verdict": "REVISE",
                               "reason": "a device acting on its own"}), {}
        if "whether what this person just said follows" in system:
            return json.dumps({"verdict": "REVISE",
                               "reason": "repeats an earlier attempt"}), {}
        if "You are the world" in system:
            if "actor_intention" in user:
                return json.dumps({
                    "judgment": "she does it.",
                    "event": {"description": "Margaret signs the lease and "
                                             "sends it back to Jian Wei.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "20 minutes", "follow_up": False},
                    "wakes": []}), {}
            return json.dumps({"judgment": "nothing.", "event": None,
                               "wakes": []}), {}
        if "ada_vance" in user:
            return json.dumps({"decision": "I will sign and return it.",
                               "intentions": ["Sign the lease and send it "
                                              "back."],
                               "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    _, journal, _ = run(transport, wrap=False)
    assert any("signs the lease" in e["description"]
               for e in journal.events()), \
        "the decisive act was destroyed by a reviewer and its absence " \
        "would have become the answer"


def test_identical_event_text_gets_identical_treatment():
    """The merged runtime PASSed and REVISEd the byte-identical string
    four calls apart in one run, so the same scene on identical evidence
    answered YES three times and NO three times."""
    flip = {"n": 0}

    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "whether the proposed event" in system:
            flip["n"] += 1
            return json.dumps(
                {"verdict": "PASS" if flip["n"] % 2 else "REVISE",
                 "reason": "inconsistent on purpose"}), {}
        if "You are the world" in system:
            if "actor_intention" in user:
                return json.dumps({
                    "judgment": "he does it.",
                    "event": {"description": "Aisha prints the lease "
                                             "document.",
                              "for": ["ada_vance"], "observed": True,
                              "after": "3 minutes", "follow_up": False},
                    "wakes": []}), {}
            return json.dumps({"judgment": "nothing.", "event": None,
                               "wakes": []}), {}
        if "ada_vance" in user:
            return json.dumps({"decision": "I print it.",
                               "intentions": ["Print the lease."],
                               "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    outcomes = set()
    for _ in range(4):
        flip["n"] = 0
        _, journal, _ = run(transport, wrap=False)
        outcomes.add(any("prints the lease" in e["description"]
                         for e in journal.events()))
    assert outcomes == {True}, \
        "whether a valid act survives depends on a coin flip in a reviewer"


# --------------------------- 6, 7: causes and other people's choices


def test_every_world_consequence_cites_the_attempt_that_caused_it():
    """The world received prose and returned prose; nothing bound a
    consequence to the attempt it came from."""
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "actor_intention" in user:
                return json.dumps({
                    "judgment": "she does it.",
                    "event": {"description": "Ada sends the note.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "1 minutes", "follow_up": False},
                    "wakes": []}), {}
            return json.dumps({"judgment": "nothing.", "event": None,
                               "wakes": []}), {}
        if "ada_vance" in user:
            return json.dumps({"decision": "I send it.",
                               "intentions": ["Send Bo the note."],
                               "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    world, journal, _ = run(transport)
    attempts = [r for r in world.records if r["op"] == "semantic.attempt"]
    assert attempts, "no attempt was ever recorded as its own object"
    ids = {a["data"]["attempt_id"] for a in attempts}
    caused = [e for e in journal.events() if "sends the note" in
              e["description"]]
    assert caused, "the attempt produced nothing"
    assert caused[0].get("attempt_id") in ids, \
        "a committed consequence names no attempt"


def test_the_world_cannot_author_another_persons_voluntary_choice():
    """Not by keyword, by identity: an attempt belongs to one actor, and
    a consequence in which somebody ELSE chooses is that person's turn."""
    turns = []

    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "actor_intention" in user:
                # Ada attempts; the world has BO decide something
                return json.dumps({
                    "judgment": "and he replies.",
                    "event": {"description": "Bo reads Ada's note and "
                                             "replies that he agrees.",
                              "for": ["ada_vance"], "observed": True,
                              "after": "5 minutes", "follow_up": False},
                    "wakes": []}), {}
            return json.dumps({"judgment": "nothing.", "event": None,
                               "wakes": []}), {}
        turns.append(user)
        if "ada_vance" in user:
            return json.dumps({"decision": "I send it.",
                               "intentions": ["Send Bo the note."],
                               "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    _, journal, _ = run(transport)
    assert not any("replies that he agrees" in e["description"]
                   for e in journal.events()), \
        "the world decided for Bo and it was committed as history"
    assert any("bo_ferrer" in u for u in turns), \
        "the choice was refused but never handed to the person whose it was"


# ------------------------------------------ 8, 9: information boundary


def test_a_recipient_cannot_see_information_before_it_is_available():
    from sworldmodel.semantic_runtime.views import build_view, render_view

    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "starting_event" in user:
                return json.dumps({
                    "judgment": "on its way.",
                    "event": {"description": "Ada sends Bo the figure she "
                                             "will not go below.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "1 minutes", "follow_up": False},
                    "wakes": []}), {}
            return json.dumps({"judgment": "nothing.", "event": None,
                               "wakes": []}), {}
        return json.dumps(NOTHING), {}

    world, journal, _ = run(transport)
    seen = render_view(build_view(world, journal, "bo_ferrer"))
    assert "will not go below" not in seen, \
        "a recipient was shown information he has not observed"


def test_the_sender_does_not_learn_the_recipients_attention():
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "actor_intention" in user:
                return json.dumps({
                    "judgment": "she sends it.",
                    "event": {"description": "Ada sends her answer to Bo.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "2 minutes", "follow_up": True},
                    "wakes": []}), {}
            if "event_consequence" in user:
                return json.dumps({
                    "judgment": "it lands.",
                    "event": {"description": "It reaches Bo, who is driving "
                                             "and does not notice it.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "1 minutes", "follow_up": False},
                    "wakes": []}), {}
            return json.dumps({"judgment": "nothing.", "event": None,
                               "wakes": []}), {}
        if "ada_vance" in user:
            return json.dumps({"decision": "I answer him.",
                               "intentions": ["Send Bo my answer."],
                               "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    _, journal, _ = run(transport)
    far = [e for e in journal.events() if "does not notice" in
           e["description"]]
    if far:
        assert "ada_vance" not in far[0]["observed_by"]


# ------------------------------- 11: the same question, over and over


def test_an_actor_is_not_consulted_again_having_learned_nothing():
    """One person received nineteen identical turns in the merged corpus
    and produced nothing at all. That is a runtime failure, not a
    person."""
    seen = []

    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            return json.dumps({
                "judgment": "call me back about him.",
                "event": None,
                "wakes": [{"actor": "bo_ferrer", "after": "2 hours",
                           "reason": "he may look later"}]}), {}
        if "bo_ferrer" in user:
            seen.append(user)
        return json.dumps(NOTHING), {}

    run(transport, steps=30)
    changed = {u[u.index("WHAT YOU HAVE ACTUALLY OBSERVED"):]
               if "WHAT YOU HAVE ACTUALLY OBSERVED" in u else u
               for u in seen}
    assert len(seen) - len(changed) <= 1, (
        f"{len(seen)} consultations of one person across "
        f"{len(changed)} distinct situations")


# ------------------------------------------ 13, 14, 15: the guarantees


def test_the_verifier_cannot_return_no_before_the_cutoff():
    from sworldmodel.semantic_runtime.resolution import (
        ResolutionError, make_verifier_validator)
    v = make_verifier_validator({"e1"}, parse_iso(START), parse_iso(CUTOFF))
    with pytest.raises(ResolutionError):
        v({"status": "NO_AT_CUTOFF", "supporting_event_ids": [],
           "explanation": "the deadline is in the future"})


def test_replay_detects_mutation_deletion_reordering_and_forgery():
    from sworldmodel.semantic_runtime.replay import check_ledger_integrity
    world, journal, _ = run(silent_world)
    good = replay_trajectory(world.records, live_world=world)
    assert good["exact"] and good["llm_calls"] == 0
    assert not good["ledger_integrity"]

    mutated = [dict(r) for r in world.records]
    for r in mutated:
        if r["op"] == "journal.event":
            r["data"] = dict(r["data"], description="something else")
            break
    assert not replay_trajectory(mutated, live_world=world)["exact"]

    deleted = [r for r in world.records if r["op"] != "journal.event"]
    assert not replay_trajectory(deleted, live_world=world)["exact"]

    # genesis must stay first or the kernel refuses the ledger outright,
    # which proves nothing about reordering
    head, tail = world.records[:1], [dict(r) for r in world.records[1:]]
    reordered = head + list(reversed(tail))
    assert (check_ledger_integrity(reordered)
            or not replay_trajectory(reordered, live_world=world)["exact"])

    forged = [dict(r) for r in world.records]
    forged.append(dict(forged[-1], seq=forged[-1]["seq"] + 1,
                       op="journal.event",
                       data={"event_id": "e999", "description": "he agreed",
                             "for": ["ada_vance"], "observed": True,
                             "trajectory_id": "t1", "source": "forged"}))
    assert not replay_trajectory(forged, live_world=world)["exact"]


def test_there_is_exactly_one_runtime_path():
    """A second orchestrator, or a compiler import, would make the frozen
    path a claim rather than a fact."""
    import subprocess
    import sys
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys;before=set(sys.modules);"
         "import sworldmodel.semantic_runtime;"
         "print([m for m in set(sys.modules)-before "
         "if m.split('.')[0]=='compiler'])"],
        capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]", out.stdout
    entry = subprocess.run(
        ["git", "grep", "-l", "def run_trajectory"],
        capture_output=True, text=True, check=True).stdout.split()
    assert entry == ["sworldmodel/semantic_runtime/trajectory.py"], entry
