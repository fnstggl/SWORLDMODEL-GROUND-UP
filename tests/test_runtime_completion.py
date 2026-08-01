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
    """The honest NO must keep working.

    A run whose queue carries it all the way to the deadline has lived the
    window; if the thing did not happen, NO is the answer. Only a run
    whose future ran out early is incomplete.
    """
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            # a real future stays on the queue all the way to the deadline
            return json.dumps({
                "judgment": "nothing else before then.",
                "event": None,
                "wakes": [{"actor": "ada_vance", "after": "2 days",
                           "reason": "she said she would look again"}]}), {}
        return json.dumps(NOTHING), {}

    _, _, traj = run(transport, steps=40)
    assert traj.status == "cutoff", traj.status
    assert (traj.answer or {}).get("status") == "NO_AT_CUTOFF"


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
                              "after": "1 minutes", "by": None, "lasts": "0 seconds"},
                    "wakes": []}), {}
            # the world tries to narrate transport, as it did throughout
            # the merged corpus
            return json.dumps({
                "judgment": "it lands.",
                "event": {"description": "The message arrives in Bo's "
                                         "inbox and a notification appears "
                                         "on his phone.",
                          "for": ["bo_ferrer"], "observed": False,
                          "after": "1 minutes", "by": None, "lasts": "0 seconds"},
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
                          "observed": True, "after": "2 minutes", "by": None, "lasts": "0 seconds"}, "wakes": []}), {}
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
                              "after": "20 minutes", "by": None, "lasts": "0 seconds"},
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
    answered YES three times and NO three times.

    With no semantic gate on the hot path this is structural: the same
    script produces the same journal, every time.
    """
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "actor_intention" in user:
                return json.dumps({
                    "judgment": "she does it.",
                    "event": {"description": "Aisha prints the lease "
                                             "document.",
                              "for": ["ada_vance"], "observed": True,
                              "after": "3 minutes",
                              "by": "ada_vance", "lasts": "0 seconds"},
                    "wakes": []}), {}
            return json.dumps({"judgment": "nothing.", "event": None,
                               "wakes": []}), {}
        if "ada_vance" in user:
            return json.dumps({"decision": "I print it.",
                               "intentions": ["Print the lease."],
                               "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    journals = []
    for _ in range(4):
        _, journal, _ = run(transport)
        journals.append([e["description"] for e in journal.events()])
    assert all(j == journals[0] for j in journals), \
        f"the same script produced different histories: {journals}"


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
                              "after": "1 minutes", "by": None, "lasts": "0 seconds"},
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
                              "after": "5 minutes",
                              "by": "bo_ferrer", "lasts": "0 seconds"},
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
                              "after": "1 minutes", "by": None, "lasts": "0 seconds"},
                    "wakes": []}), {}
            return json.dumps({"judgment": "nothing.", "event": None,
                               "wakes": []}), {}
        return json.dumps(NOTHING), {}

    world, journal, _ = run(transport)
    seen = render_view(build_view(world, journal, "bo_ferrer"))
    assert "will not go below" not in seen, \
        "a recipient was shown information he has not observed"


def test_the_sender_does_not_learn_the_recipients_attention():
    """The own-doing grant must not carry the far end of what was sent.

    This test used to branch on `event_consequence`, a trigger kind that no
    longer exists, so its only assertion sat inside an `if` that was never
    true and it passed unconditionally -- while a live run handed Dana, as
    authoritative observed fact, that her message had not been delivered
    because Marcus's phone was off.
    """
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "actor_intention" in user:
                # the world writes the sending AND the far end in one event
                return json.dumps({
                    "judgment": "she sends it.",
                    "event": {"description": "Dana sends the message. It "
                                             "enters the network but Marcus's "
                                             "phone is off, so it is not "
                                             "delivered.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "2 minutes",
                              "by": "ada_vance", "lasts": "0 seconds"}, "wakes": []}), {}
            return json.dumps({"judgment": "nothing.", "event": None,
                               "wakes": []}), {}
        if "ada_vance" in user:
            return json.dumps({"decision": "I message him.",
                               "intentions": ["Send Bo the message."],
                               "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    world, journal, _ = run(transport)
    sent = next((e for e in journal.events()
                 if "enters the network" in e["description"]), None)
    if sent is None:
        pytest.skip("the world did not produce the mixed event")
    from sworldmodel.semantic_runtime.views import build_view, render_view
    seen = render_view(build_view(world, journal, "ada_vance"))
    assert "phone is off" not in seen, (
        "the sender was told, as observed fact, why the far end did not "
        "receive it")

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
    # source only: tests script it, and reviewer reports quote it
    entry = [f for f in subprocess.run(
        ["git", "grep", "-l", "def run_trajectory", "--", "*.py"],
        capture_output=True, text=True, check=True).stdout.split()
        if not f.startswith("tests/")]
    assert entry == ["sworldmodel/semantic_runtime/trajectory.py"], entry


def test_whether_a_no_is_reachable_does_not_depend_on_arithmetic():
    """Two independent reviewers found that NO_AT_CUTOFF was reachable only
    when the last scheduled instant happened to divide the window exactly.

    A wake every two days over a fortnight answered NO; every three days
    answered incomplete_empty_queue, with identical world behaviour. The
    beyond-cutoff signal was being computed and thrown away, so the horizon
    was decided by divisibility rather than by what happened.
    """
    seen = {}
    for interval in ("1 days", "2 days", "3 days", "4 days", "5 days",
                     "36 hours", "7 days"):
        def transport(system, user, iv=interval):
            t = terminal_roles(user, system)
            if t:
                return t
            if "You are the world" in system:
                return json.dumps({
                    "judgment": "they each check again", "event": None,
                    "wakes": [{"actor": "ada_vance", "after": iv,
                               "reason": "she said she would"},
                              {"actor": "bo_ferrer", "after": iv,
                               "reason": "he said he would"}]}), {}
            return json.dumps(NOTHING), {}

        _, _, traj = run(transport, steps=40)
        seen[interval] = (traj.status, (traj.answer or {}).get("status"))
    assert len(set(seen.values())) == 1, (
        f"the answer depends on the wake interval rather than on the "
        f"world: {seen}")
    assert set(seen.values()) == {("cutoff", "NO_AT_CUTOFF")}, seen


def test_one_persons_monday_is_not_everybodys_horizon():
    """NO over a window is a claim that nothing happened to ANYONE in it.

    One actor saying "I'll look on Monday" is a fact about that actor. Read
    as a statement about the window it advanced the clock across an unlived
    fortnight on the strength of a single wake request -- exactly the thing
    the empty-queue rule exists to stop, arriving by another door.
    """
    def only_ada_is_finished(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            return json.dumps({
                "judgment": "she will look after the deadline.",
                "event": None,
                "wakes": [{"actor": "ada_vance", "after": "20 days",
                           "reason": "she said she would look then"}]}), {}
        return json.dumps(NOTHING), {}

    _, _, traj = run(only_ada_is_finished, steps=30)
    assert traj.status == "incomplete_empty_queue", traj.status
    assert (traj.answer or {}).get("status") != "NO_AT_CUTOFF"


def test_a_duration_is_not_a_statement_about_the_window():
    """A `lasts` running past the deadline made NO available in one step.

    Code -- not the world, not an actor -- computes the instant an action
    ends and schedules the free-wake there. When that landed past the
    cutoff it was read as somebody saying nothing more would happen. With
    everything else held fixed, a `lasts` of 7h58m answered incomplete and
    8h answered NO: the run that lived 99.8% of its window was refused a
    NO and the run that lived 0.2% gave one.
    """
    def one_long_act(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "attempts" in user:
                return json.dumps({
                    "judgment": "she settles in to it.",
                    "event": {"description": "Ada works on her own thing.",
                              "for": ["ada_vance"], "observed": True,
                              "after": "1 minutes", "by": "ada_vance",
                              "lasts": "20 days"},
                    "wakes": []}), {}
            return json.dumps({"judgment": "nothing follows.", "event": None,
                               "wakes": []}), {}
        if "ada_vance" in user:
            return json.dumps({"decision": "I get on with it.",
                               "intentions": ["work on my own thing"],
                               "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    _, _, traj = run(one_long_act, steps=30)
    assert traj.status.startswith("incomplete"), traj.status
    assert (traj.answer or {}).get("status") != "NO_AT_CUTOFF", \
        "a NO was read off one person's stated duration"


def test_a_turns_attempts_resolve_in_the_order_they_were_stated():
    """A person doing two things does the first one first.

    Live: a woman intended "check my bank account to confirm the transfer
    has arrived" and then "if confirmed, transfer 400 to Marian". The
    intentions were dispatched in order but their events fired from a
    time-ordered queue, so the shorter second one overtook the longer
    first: she sent 400 pounds thirty seconds BEFORE the check, and that
    check then said the money had not arrived. The condition was stripped
    because the world adjudicating the second attempt could not see the
    first -- it had not happened yet.
    """
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "attempts: Check" in user:
                # the prerequisite genuinely takes a while
                return json.dumps({
                    "judgment": "she looks it up.",
                    "event": {"description": "Ada checks the account and "
                                             "sees the transfer has arrived.",
                              "for": ["ada_vance"], "observed": True,
                              "after": "30 minutes",
                              "by": "ada_vance", "lasts": "0 seconds"}, "wakes": []}), {}
            if "attempts: If confirmed" in user:
                # ... and the dependent one is quick
                return json.dumps({
                    "judgment": "she sends it.",
                    "event": {"description": "Ada transfers the deposit on.",
                              "for": ["ada_vance"], "observed": True,
                              "after": "1 minutes",
                              "by": "ada_vance", "lasts": "0 seconds"}, "wakes": []}), {}
            return json.dumps({"judgment": "nothing.", "event": None,
                               "wakes": []}), {}
        if "ada_vance" in user:
            return json.dumps({
                "decision": "I check first, then send it on.",
                "intentions": ["Check the account for the transfer.",
                               "If confirmed, transfer the deposit on."],
                "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    _, journal, _ = run(transport)
    order = [e["description"] for e in journal.events()]
    check = next((i for i, d in enumerate(order) if "checks the account" in d),
                 None)
    send = next((i for i, d in enumerate(order) if "transfers the deposit" in d),
                None)
    assert check is not None and send is not None, order
    assert check < send, (
        f"the conditional attempt resolved before the check it depends on: "
        f"{order}")


def test_a_person_acting_survives_whatever_question_prompted_it():
    """Code must not delete a valid action either.

    The attention rule used to require that an answer to "what becomes of
    this for them?" be an attention event, and it deleted 58 world answers
    across eleven runs -- including "Marcus Bell replies to Dana Whitfield
    that the hall is confirmed", the decisive act of that scenario. That
    is the failure this whole branch exists to remove, with code in the
    reviewer's chair instead of a model.
    """
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "starting_event" in user:
                return json.dumps({
                    "judgment": "she asks him.",
                    "event": {"description": "Ada asks Bo to confirm the hall.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "1 minutes",
                              "by": "ada_vance", "lasts": "0 seconds"}, "wakes": []}), {}
            # the attention question, answered with a person acting
            return json.dumps({
                "judgment": "he answers her.",
                "event": {"description": "Bo replies that the hall is "
                                         "confirmed for the 14th.",
                          "for": ["ada_vance"], "observed": True,
                          "after": "20 minutes",
                          "by": "bo_ferrer", "lasts": "0 seconds"}, "wakes": []}), {}
        return json.dumps(NOTHING), {}

    _, journal, _ = run(transport)
    assert any("hall is confirmed" in e["description"]
               for e in journal.events()), \
        "a person's reply was deleted because the question was about attention"


def test_a_restatement_that_nothing_changed_is_still_refused():
    """The other side: nobody did it, and nobody's notice reached
    anything. That is the item's own state narrated again."""
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "starting_event" in user:
                return json.dumps({
                    "judgment": "she sends it.",
                    "event": {"description": "Ada sends Bo the proposal.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "1 minutes",
                              "by": "ada_vance", "lasts": "0 seconds"}, "wakes": []}), {}
            return json.dumps({
                "judgment": "it sits there.",
                "event": {"description": "The proposal remains unread in "
                                         "Bo's inbox.",
                          "for": ["bo_ferrer"], "observed": False,
                          "after": "2 hours",
                          "by": None, "lasts": "0 seconds"}, "wakes": []}), {}
        return json.dumps(NOTHING), {}

    _, journal, _ = run(transport)
    assert not any("remains unread" in e["description"]
                   for e in journal.events()), \
        "the absence of an event was committed as one"


def test_tampering_with_a_persisted_ledger_is_detectable_from_disk():
    """A reviewer copied a finished run, rewrote every event description
    and every terminal record, and the checker still reported exact=True.

    No semantic op has a kernel reducer, so the kernel state hash does not
    cover the journal at all, and the tool copied `exact` out of a file
    sitting in the same directory as the ledger it certified. Both were
    editable in one edit.
    """
    import json as _json
    import os
    import subprocess
    import sys
    import tempfile

    from sworldmodel.semantic_runtime.trace import write_artifacts

    world, journal, traj = run(silent_world)
    with tempfile.TemporaryDirectory() as d:
        write_artifacts(d, scene=SCENE, world=world, journal=journal,
                        bindings={"trajectory_id": "t1", "cutoff": CUTOFF,
                                  "starting_event_ids": [], "actor_ids": {}},
                        trajectory=traj,
                        caller=RuntimeCaller(transport=silent_world),
                        trace=Trace(), replay=None, question="q")
        assert os.path.exists(os.path.join(d, "ledger_digest.txt"))
        env = dict(os.environ, PYTHONPATH=os.getcwd())
        clean = subprocess.run(
            [sys.executable, "evaluation/reverify_replay.py", d],
            capture_output=True, text=True, env=env)
        assert clean.returncode == 0, clean.stdout + clean.stderr
        assert "digest=True" in clean.stdout, clean.stdout

        # now rewrite the record, exactly as the reviewer did
        path = os.path.join(d, "ledger.jsonl")
        rows = [_json.loads(l) for l in open(path) if l.strip()]
        for r in rows:
            if r["op"] == "journal.event":
                r["data"] = dict(r["data"],
                                 description="TAMPERED - she never did it")
        with open(path, "w") as f:
            for r in rows:
                f.write(_json.dumps(r, sort_keys=True) + "\n")
        dirty = subprocess.run(
            [sys.executable, "evaluation/reverify_replay.py", d],
            capture_output=True, text=True, env=env)
        assert dirty.returncode == 1, dirty.stdout
        assert "digest=False" in dirty.stdout, dirty.stdout


def test_the_same_act_reworded_is_one_act_but_different_numbers_are_not():
    """The exact-string guard caught 11 word-for-word repeats in one
    corpus and missed ~46 rewordings -- a woman signed one lease twice a
    minute apart, and a decisive act was committed twice.

    The other direction matters more: over-merging deletes valid acts,
    which is the failure this whole branch exists to remove. So a numeric
    difference disqualifies a match outright, and borderline pairs are
    left alone.
    """
    from sworldmodel.semantic_runtime.world_mind import says_the_same_thing

    assert says_the_same_thing(
        "Margaret signs the printed lease with a pen.",
        "Margaret signs the lease with a pen.")
    # different numbers are different things, however alike they read
    assert not says_the_same_thing("Ruth transfers 400 to Marian.",
                                   "Ruth transfers 200 to Marian.")
    assert not says_the_same_thing("Ada reads the 1st page.",
                                   "Ada reads the 2nd page.")
    # and genuinely different acts are never merged
    assert not says_the_same_thing("Bo replies that the hall is confirmed.",
                                   "Ada asks Bo to confirm the hall.")


# ------------------------------------------------------ time is occupied
#
# One missing concept behind most of two rounds of reviewer findings: an
# action had a start and no duration, so nobody was ever busy.  65% of a
# 202-event corpus happened at the same instant as its cause, a woman
# signed a lease two minutes into a thirty-minute call, and a support call
# was narrated as thirty-three events inside three minutes.


def busy_world(first_lasts="30 minutes", second_after="2 minutes"):
    """Ada states two things.  The first takes real time; the world says
    the second follows almost immediately."""
    state = {"n": 0}

    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "attempts" not in user:
                return json.dumps({"judgment": "the scene begins.",
                                   "event": None, "wakes": []}), {}
            state["n"] += 1
            n = state["n"]
            if n == 1:
                return json.dumps({
                    "judgment": "she gets him on the phone.",
                    "event": {"description": "Ada talks to Bo on the phone.",
                              "for": ["bo_ferrer"], "observed": True,
                              "after": "0 seconds", "by": "ada_vance",
                              "lasts": first_lasts},
                    "wakes": []}), {}
            if n == 2:
                return json.dumps({
                    "judgment": "she also gets the papers away.",
                    "event": {"description": "Ada posts the signed papers.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": second_after, "by": "ada_vance",
                              "lasts": "0 seconds"},
                    "wakes": []}), {}
            return json.dumps({"judgment": "nothing further.",
                               "event": None, "wakes": []}), {}
        if "ada_vance" in user and state["n"] == 0:
            return json.dumps({
                "decision": "I will call him and send the papers.",
                "intentions": ["call Bo", "post the signed papers"],
                "private_updates": []}), {}
        return json.dumps(NOTHING), {}
    return transport


def test_a_second_act_cannot_begin_inside_the_first():
    """A person doing a thirty-minute thing is not also doing something
    else two minutes in.  This is the whole of the occupancy model, and
    nothing but code can enforce it: the world proposes each event without
    knowing what else that person has going on."""
    _, journal, _ = run(busy_world(), steps=20)
    by_desc = {e["description"]: parse_iso(e["t"]) for e in journal.events()}
    call = by_desc["Ada talks to Bo on the phone."]
    post = by_desc["Ada posts the signed papers."]
    assert (post - call).total_seconds() >= 30 * 60, \
        f"the second act began {(post - call)} into a thirty-minute call"


def test_an_actor_is_told_what_they_are_in_the_middle_of():
    """The runtime knew somebody was occupied and the person did not, so
    they answered as though their afternoon were empty."""
    from sworldmodel.semantic_runtime.views import build_view, render_view
    world, journal, _ = run(busy_world(), steps=20)
    view = build_view(world, journal, "ada_vance",
                      busy_until=parse_iso(CUTOFF))
    assert view["busy_until"]
    assert "in the middle of" in render_view(view).lower()
    # ... and a person who is free is told nothing at all about it
    free = build_view(world, journal, "ada_vance")
    assert free["busy_until"] is None
    assert "in the middle of" not in render_view(free).lower()


def test_finishing_something_brings_the_person_back():
    """The occupancy model must not be able to strand anybody.  If it can
    only ever stop a person acting, it produces exactly the abandoned-
    mid-sentence shape the corpus is full of: somebody goes quiet in the
    middle of a task and is never asked anything again."""
    trace = Trace()
    world, journal, bindings = build()
    caller = RuntimeCaller(transport=reviewed(busy_world()))
    run_trajectory(world, journal, bindings, SCENE["resolution"], caller,
                   max_steps=20, trace=trace)
    finishes = [w for w in trace.of("wake_scheduled")
                if w["provenance"] == "own_act_finished"]
    assert finishes, "nothing was scheduled for when the call ends"
    assert finishes[0]["actor"] == "ada_vance"


def test_somebody_mid_task_is_not_consulted_about_the_next_thing():
    """Asking a person what they want to do twenty seconds into a
    thirty-minute call is how one actor collected 55 consecutive turns
    and 185 model calls to commit two events."""
    trace = Trace()
    world, journal, bindings = build()
    caller = RuntimeCaller(transport=reviewed(busy_world()))
    run_trajectory(world, journal, bindings, SCENE["resolution"], caller,
                   max_steps=20, trace=trace)
    held = trace.of("still_mid_task")
    assert held, "a person on a thirty-minute call was asked what to do next"
    assert held[0]["actor"] == "ada_vance"


def test_an_instantaneous_act_occupies_nobody():
    """The rule is duration, not a ban on doing two things.  An act the
    world says takes no time leaves the person free at once, so nothing
    here slows down a world that really is quick."""
    _, journal, _ = run(busy_world(first_lasts="0 seconds"), steps=20)
    by_desc = {e["description"]: parse_iso(e["t"]) for e in journal.events()}
    gap = (by_desc["Ada posts the signed papers."]
           - by_desc["Ada talks to Bo on the phone."]).total_seconds()
    assert gap <= 2 * 60, f"a nil-duration act still blocked for {gap}s"


def test_duration_is_carried_on_the_event_and_survives_replay():
    """`lasts` is load-bearing, so it is part of the committed record and
    a replay that dropped it would not be exact."""
    world, journal, _ = run(busy_world(), steps=20)
    call = next(e for e in journal.events()
                if e["description"] == "Ada talks to Bo on the phone.")
    assert call["lasts"] == "30 minutes"
    assert replay_trajectory(world.records, live_world=world)["exact"]


# ------------------------------------------- the world is a place, not a
# reaction function
#
# The adjudicator had exactly three occasions, all reactive: a starting
# event, somebody's attempt, something already in somebody's inbox. So
# nothing could ever happen that a person in the cast had not chosen.
# Across 209 committed events in the shipped corpus there were zero events
# from outside it -- no office shut, no deadline bit on its own, nobody
# chased what they were owed -- and the one thing that ever went wrong was
# that somebody had not got round to it, which the world prompt itself
# calls unrealistic.


def quiet_but_moving_world(exogenous_by=None):
    """Nobody in the cast does anything; the world is asked what happened
    in the time they spend not doing it."""
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if "Nobody here does anything between now and" in user:
                return json.dumps({
                    "judgment": "the office closes for the weekend.",
                    "event": {"description": "The letting office closes "
                                             "until Monday.",
                              "for": ["ada_vance"], "observed": False,
                              "after": "10 minutes", "by": exogenous_by,
                              "lasts": "0 seconds"},
                    "wakes": []}), {}
            return json.dumps({
                "judgment": "nothing follows from that.", "event": None,
                "wakes": [{"actor": "ada_vance", "after": "2 days",
                           "reason": "she said she would look again"}]}), {}
        return json.dumps(NOTHING), {}
    return transport


def test_something_can_happen_that_nobody_in_the_scene_chose():
    """Without the world's own turn, a fortnight of simulated time
    contains only what the cast did to each other."""
    _, journal, _ = run(quiet_but_moving_world(), steps=30)
    descs = [e["description"] for e in journal.events()]
    assert any("letting office closes" in d for d in descs), descs
    exogenous = [e for e in journal.events() if e["by"] is None
                 and e["source"].startswith("world_call")]
    assert exogenous, "every committed event was somebody in the cast acting"


def test_the_worlds_own_turn_may_not_write_a_persons_choice():
    """'Meanwhile, what happened?' is the widest invitation in the runtime
    to record somebody's decision as weather. There is no adjudicating
    actor on that turn by construction, which is exactly when the identity
    guard matters most: nobody here did it is what the turn MEANS."""
    trace = Trace()
    world, journal, bindings = build()
    caller = RuntimeCaller(
        transport=reviewed(quiet_but_moving_world(exogenous_by="bo_ferrer")))
    run_trajectory(world, journal, bindings, SCENE["resolution"], caller,
                   max_steps=30, trace=trace)
    handed = trace.of("choice_returned_to_its_owner")
    assert handed, "the world wrote Bo's choice on its own turn and it stood"
    assert handed[0]["actor"] == "bo_ferrer"
    assert not any("letting office closes" in e["description"]
                   for e in journal.events())


def test_the_world_is_asked_about_unlived_time_only_once_per_instant():
    """Code owns only the threshold -- that the question is owed at all.
    Asking repeatedly at one instant is the same question again, and each
    one costs a call."""
    trace = Trace()
    world, journal, bindings = build()
    caller = RuntimeCaller(transport=reviewed(quiet_but_moving_world()))
    run_trajectory(world, journal, bindings, SCENE["resolution"], caller,
                   max_steps=30, trace=trace)
    asked = [j for j in trace.of("world_judgment")
             if j["trigger"] == "elapsed_world"]
    assert asked
    assert len(asked) == len({j["t"] for j in asked}), \
        [j["t"] for j in asked]


def test_a_short_hop_is_not_a_stretch_of_unlived_time():
    """The question is about time a situation could move in. Asking it of
    the next ninety seconds is not a question, it is a tax."""
    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            return json.dumps({
                "judgment": "nothing follows.", "event": None,
                "wakes": [{"actor": "ada_vance", "after": "2 minutes",
                           "reason": "she said she would check back"}]}), {}
        return json.dumps(NOTHING), {}

    trace = Trace()
    world, journal, bindings = build()
    run_trajectory(world, journal, bindings, SCENE["resolution"],
                   RuntimeCaller(transport=reviewed(transport)),
                   max_steps=12, trace=trace)
    assert not [j for j in trace.of("world_judgment")
                if j["trigger"] == "elapsed_world"]


def test_a_person_with_nothing_new_is_told_exactly_that():
    """A view can never say 'nothing changed', so 208 of 240 no-op
    consultations opened by announcing a change that had not happened."""
    from sworldmodel.semantic_runtime.views import build_view, render_view
    world, journal, _ = run(silent_world)
    rendered = render_view(build_view(world, journal, "bo_ferrer"))
    assert "nothing new has reached you" in rendered \
        or "for the first time" in rendered
    assert "has changed" not in rendered.lower()


def test_a_known_future_past_the_deadline_is_the_horizon_however_it_is_said():
    """"She will get to it on Monday" and "come back to me on Monday" are
    the same evidence about a Friday deadline: the world has said what
    happens next and none of it lands inside the window. One of them could
    answer NO and the other could not, purely because the beyond-cutoff
    signal was recorded for wakes and thrown away for events."""
    def as_events(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if " attempts:" not in user:
                return json.dumps({"judgment": "nothing yet.", "event": None,
                                   "wakes": []}), {}
            who = ("bo_ferrer" if "bo_ferrer attempts:" in user
                   else "ada_vance")
            return json.dumps({
                "judgment": "they get to it after the deadline.",
                "event": {"description": f"{who} turns to it.",
                          "for": [who], "observed": False,
                          "after": "20 days", "by": who,
                          "lasts": "10 minutes"},
                "wakes": []}), {}
        return json.dumps({"decision": "I will get to it.",
                           "intentions": ["turn to it"],
                           "private_updates": []}), {}

    def as_wakes(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            return json.dumps({
                "judgment": "they each get to it after the deadline.",
                "event": None,
                "wakes": [{"actor": a, "after": "20 days",
                           "reason": "they said they would look then"}
                          for a in ("ada_vance", "bo_ferrer")]}), {}
        return json.dumps(NOTHING), {}

    outcomes = set()
    for transport in (as_events, as_wakes):
        _, _, traj = run(transport, steps=30)
        outcomes.add((traj.status, (traj.answer or {}).get("status")))
    assert outcomes == {("cutoff", "NO_AT_CUTOFF")}, outcomes


def test_chasing_is_not_something_a_reviewer_may_refuse():
    """The actor prompt tells people that they wait, chase and ask again;
    the continuity reviewer refused a reply that "does again something
    they have already done" or "goes over an unchanged question again
    merely because time has passed". Chasing is both of those.

    That is why, in the shipped corpus, a woman owed 600 pounds never
    contacts the person who owes her, and a student waiting on feedback
    never follows up once in thirty-one events. The two prompts have to
    agree, and the one that gets to say what a person may choose is the
    person's own.
    """
    from sworldmodel.semantic_runtime.actor_mind import (ACTOR_SYSTEM,
                                                         CONTINUITY_SYSTEM)
    assert "chase" in ACTOR_SYSTEM
    assert "CHASING IS NOT A DEFECT" in CONTINUITY_SYSTEM
    # the two rules that made following up refusable, in the exact words
    # they were written in
    assert "unchanged question again merely because time has passed" \
        not in CONTINUITY_SYSTEM
    assert "- does again something they have already done" \
        not in CONTINUITY_SYSTEM
    # ... and what they were protecting is still protected
    assert "already succeeded" in CONTINUITY_SYSTEM


# ------------------------------------------------- what two adversarial
# reviewers broke, and what stops it now


def test_waiting_for_an_act_is_not_doing_it():
    """Occupancy ran from now to start+duration, so a woman who would post
    a letter on Wednesday was busy from Monday. Every act in between was
    pushed to Wednesday, and any that then fell past the cutoff was
    destroyed -- including, in the reviewer's demonstration, the reply that
    would have answered the question.

    `after` is a wait and `lasts` is the work. The occupancy is
    [start, start+lasts), and the only question is whether a new act would
    BEGIN inside it.
    """
    state = {"n": 0}

    def transport(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if " attempts:" not in user:
                return json.dumps({"judgment": "the scene begins.",
                                   "event": None, "wakes": []}), {}
            state["n"] += 1
            if state["n"] == 1:
                return json.dumps({
                    "judgment": "she will post it on Wednesday.",
                    "event": {"description": "Ada posts the papers.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "2 days", "by": "ada_vance",
                              "lasts": "2 minutes"}, "wakes": []}), {}
            if state["n"] == 2:
                return json.dumps({
                    "judgment": "and she rings him now.",
                    "event": {"description": "Ada rings Bo about it.",
                              "for": ["bo_ferrer"], "observed": True,
                              "after": "0 seconds", "by": "ada_vance",
                              "lasts": "2 minutes"}, "wakes": []}), {}
            return json.dumps({"judgment": "nothing further.",
                               "event": None, "wakes": []}), {}
        if "ada_vance" in user and state["n"] == 0:
            return json.dumps({
                "decision": "Both.", "intentions": ["post the papers",
                                                    "ring Bo about it"],
                "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    _, journal, _ = run(transport, steps=25)
    by_desc = {e["description"]: parse_iso(e["t"]) for e in journal.events()}
    assert "Ada rings Bo about it." in by_desc, \
        "the immediate act was pushed out behind a two-day wait and deleted"
    assert (by_desc["Ada rings Bo about it."]
            - parse_iso(START)).total_seconds() < 3600


def test_a_repeat_days_later_is_chasing_not_a_duplicate():
    """The duplicate rule had no time bound, so doing the same thing again
    four days later was dropped end to end -- which cancels out the change
    that just stopped a reviewer refusing exactly that."""
    from sworldmodel.semantic_runtime.world_mind import make_world_validator
    said = ("ada_vance", ("bo_ferrer",), "Ada messages Bo asking about it.")
    body = {"judgment": "again", "event": {
        "description": "Ada messages Bo asking about it.",
        "for": ["bo_ferrer"], "observed": False, "after": "0 seconds",
        "by": "ada_vance", "lasts": "1 minutes"}, "wakes": []}
    # within the hour it is the same act said twice ...
    near = make_world_validator({"ada_vance", "bo_ferrer"},
                                already_committed=frozenset({said}))
    assert near(json.loads(json.dumps(body)))["event_checked"] is None
    # ... and the runtime only ever offers it what is recent
    far = make_world_validator({"ada_vance", "bo_ferrer"},
                               already_committed=frozenset())
    assert far(json.loads(json.dumps(body)))["event_checked"]


def test_saying_a_thing_did_not_happen_is_not_saying_it_did():
    """A sorted bag of tokens cannot see a negation: "he can host" against
    "he cannot host" scores 0.96. In every such pair the act that would be
    deleted is the decisive one."""
    from sworldmodel.semantic_runtime.world_mind import says_the_same_thing
    for yes, no in [
            ("Tomas says he can host the dinner.",
             "Tomas says he cannot host the dinner."),
            ("The booking is going ahead.",
             "The booking is not going ahead."),
            ("Bo accepts the offer.", "Bo does not accept the offer."),
            ("Ada reaches him on the line.",
             "Ada fails to reach him on the line.")]:
        assert not says_the_same_thing(yes, no), (yes, no)
    # ... and a genuine reword is still one act
    assert says_the_same_thing("Ada rings Bo about the papers.",
                               "Ada rings Bo about the papers again.")


def test_an_act_with_no_stated_doer_still_occupies_the_person_who_did_it():
    """Leaving `by` null switched occupancy off entirely, while code went
    on stamping the same event as that person's own doing. The second act
    began two minutes into a thirty-minute call and the ledger could not be
    audited for it."""
    state = {"n": 0}

    def no_doer(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if " attempts:" not in user:
                return json.dumps({"judgment": "the scene begins.",
                                   "event": None, "wakes": []}), {}
            state["n"] += 1
            if state["n"] == 1:
                return json.dumps({
                    "judgment": "she gets him on the line.",
                    "event": {"description": "Ada talks to Bo on the line.",
                              "for": ["bo_ferrer"], "observed": True,
                              "after": "0 seconds", "by": None,
                              "lasts": "30 minutes"}, "wakes": []}), {}
            if state["n"] == 2:
                return json.dumps({
                    "judgment": "and the papers go out.",
                    "event": {"description": "Ada posts the papers.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "2 minutes", "by": None,
                              "lasts": "0 seconds"}, "wakes": []}), {}
            return json.dumps({"judgment": "nothing further.",
                               "event": None, "wakes": []}), {}
        if "ada_vance" in user and state["n"] == 0:
            return json.dumps({
                "decision": "Both.",
                "intentions": ["talk to Bo on the line", "post the papers"],
                "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    _, journal, _ = run(no_doer, steps=25)
    by_desc = {e["description"]: e for e in journal.events()}
    talk = by_desc["Ada talks to Bo on the line."]
    assert talk["by"] == "ada_vance", "the ledger cannot say who did it"
    post = by_desc.get("Ada posts the papers.")
    assert post is not None
    assert (parse_iso(post["t"]) - parse_iso(talk["t"])).total_seconds() \
        >= 30 * 60


def test_the_world_may_not_run_on_forever_by_teaching_nobody_anything():
    """The bound on how long the world may go without consulting anybody
    cleared itself on the way in, whether or not it consulted anyone -- and
    the only people it ever consulted were ones who had never been asked at
    all. Measured on the shipped code: 54 consecutive world adjudications
    against a limit of 6."""
    from sworldmodel.semantic_runtime.trajectory import MAX_WORLD_RUN
    n = {"i": 0}

    def busy_world_that_teaches_nobody(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            n["i"] += 1
            return json.dumps({
                "judgment": "the situation moves on its own.",
                "event": {"description": f"Something shifts, step {n['i']}.",
                          "for": ["ada_vance"], "observed": False,
                          "after": "3 minutes", "by": None,
                          "lasts": "0 seconds"}, "wakes": []}), {}
        return json.dumps(NOTHING), {}

    trace = Trace()
    world, journal, bindings = build()
    run_trajectory(world, journal, bindings, SCENE["resolution"],
                   RuntimeCaller(transport=reviewed(
                       busy_world_that_teaches_nobody)),
                   max_steps=40, trace=trace)
    # longest stretch of world judgments with no actor turn between them
    order = [e["kind"] for e in trace.entries
             if e["kind"] in ("world_judgment", "actor_decision")]
    longest = run_len = 0
    for k in order:
        run_len = run_len + 1 if k == "world_judgment" else 0
        longest = max(longest, run_len)
    assert longest <= MAX_WORLD_RUN + 2, longest


def test_a_contested_answer_cannot_be_proposed_again_unchanged():
    """Disagreement left no trace: the judge was re-asked on the next step
    that committed ANY event, and the identical claim could be put again
    until the second reading happened to agree. A byte-identical YES was
    accepted on its third outing over a record whose only additions were
    irrelevant to it."""
    import re as _re
    state = {"n": 0}

    def judge_insists_verifier_refuses(system, user):
        if "read-only outcome judge" in system:
            # the SAME claim every time: the first committed event
            first = _re.findall(r"- (e\d+) \[", user)[:1]
            return json.dumps({"status": "YES" if first else "UNRESOLVED",
                               "supporting_event_ids": first,
                               "explanation": "it is done"}), {}
        if "whether a stated condition has been met" in system:
            return json.dumps({"status": "UNRESOLVED",
                               "supporting_event_ids": [],
                               "explanation": "I see nothing of the sort"}), {}
        if "whether what this person just said follows" in system:
            return json.dumps({"verdict": "PASS", "reason": "fine"}), {}
        if "You are the world" in system:
            state["n"] += 1
            return json.dumps({
                "judgment": "something small happens.",
                "event": {"description": f"A small thing, {state['n']}.",
                          "for": ["ada_vance"], "observed": False,
                          "after": "5 minutes", "by": None,
                          "lasts": "0 seconds"}, "wakes": []}), {}
        return json.dumps(NOTHING), {}

    trace = Trace()
    world, journal, bindings = build()
    traj = run_trajectory(world, journal, bindings, SCENE["resolution"],
                          RuntimeCaller(
                              transport=judge_insists_verifier_refuses),
                          max_steps=25, trace=trace)
    assert traj.status != "resolved", "a refused YES was accepted on a retry"
    # the identical claim is refused without spending a second reading
    assert trace.of("claim_already_refuted"), \
        "the same claim on the same evidence was put to the verifier again"


def test_an_act_the_world_proposed_and_code_destroyed_is_in_the_ledger():
    """Three of the four ways an adjudicated act is destroyed wrote only to
    the trace. The ledger is the authoritative artifact and the digest is
    taken over it, so an auditor could not discover that an act had been
    proposed and destroyed -- which is what has to be visible when a NO is
    claimed over its absence."""
    def repeats_itself(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            return json.dumps({
                "judgment": "the same thing again.",
                "event": {"description": "Ada messages Bo about the hall.",
                          "for": ["bo_ferrer"], "observed": False,
                          "after": "1 minutes", "by": "ada_vance",
                          "lasts": "1 minutes"}, "wakes": []}), {}
        return json.dumps(NOTHING), {}

    world, _, _ = run(repeats_itself, steps=20)
    refusals = [r["data"] for r in world.records
                if r["op"] == "semantic.world_call"
                and r["data"].get("refused_event")]
    assert refusals, "an act was proposed and destroyed with no ledger record"
    assert refusals[0]["refused_because"]
    assert refusals[0]["refused_event"]["description"]


def test_an_act_placed_before_a_queued_one_still_cannot_overlap_it():
    """Acts are not scheduled in the order they happen: an adjudication
    late in one chain can place an event EARLIER than one already queued.

    Occupancy that keeps only the person's latest interval blocks acts
    that arrive in time order and nothing else, so this case walked
    straight through it -- 510 overlapping pairs across 360 events in a
    live corpus, including a woman on a phone call and describing a fault
    to that same call one second in.
    """
    state = {"n": 0}

    def out_of_order(system, user):
        t = terminal_roles(user, system)
        if t:
            return t
        if "You are the world" in system:
            if " attempts:" not in user:
                return json.dumps({"judgment": "the scene begins.",
                                   "event": None, "wakes": []}), {}
            state["n"] += 1
            if state["n"] == 1:
                # the LATER-starting act is adjudicated first
                return json.dumps({
                    "judgment": "she gets to the second thing at half past.",
                    "event": {"description": "Ada writes up the notes.",
                              "for": ["bo_ferrer"], "observed": False,
                              "after": "30 minutes", "by": "ada_vance",
                              "lasts": "5 minutes"}, "wakes": []}), {}
            if state["n"] == 2:
                # ... and this one starts BEFORE it and runs right through
                return json.dumps({
                    "judgment": "and the call starts now and runs an hour.",
                    "event": {"description": "Ada is on a long call.",
                              "for": ["bo_ferrer"], "observed": True,
                              "after": "0 seconds", "by": "ada_vance",
                              "lasts": "60 minutes"}, "wakes": []}), {}
            return json.dumps({"judgment": "nothing further.",
                               "event": None, "wakes": []}), {}
        if "ada_vance" in user and state["n"] == 0:
            return json.dumps({
                "decision": "Both.",
                "intentions": ["write up the notes", "take the long call"],
                "private_updates": []}), {}
        return json.dumps(NOTHING), {}

    _, journal, _ = run(out_of_order, steps=25)
    from evaluation.realism_metrics import measure
    spans = []
    for e in journal.events():
        if e["by"] != "ada_vance":
            continue
        begins = parse_iso(e["t"])
        spans.append((begins, begins + _dur(e["lasts"]), e["description"]))
    for i, a in enumerate(spans):
        for b in spans[i + 1:]:
            assert not (a[0] < b[1] and b[0] < a[1]), \
                f"one person doing two things at once: {a[2]} || {b[2]}"
    assert len(spans) == 2, [s[2] for s in spans]


def _dur(text):
    from sworldmodel.semantic_runtime.envelope import parse_duration
    return parse_duration(text)
