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
                              "after": "3 minutes", "follow_up": False,
                              "by": "ada_vance"},
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
                              "after": "5 minutes", "follow_up": False,
                              "by": "bo_ferrer"},
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
                              "after": "2 minutes", "follow_up": False,
                              "by": "ada_vance"}, "wakes": []}), {}
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
                    "judgment": "she checks again", "event": None,
                    "wakes": [{"actor": "ada_vance", "after": iv,
                               "reason": "she said she would"}]}), {}
            return json.dumps(NOTHING), {}

        _, _, traj = run(transport, steps=40)
        seen[interval] = (traj.status, (traj.answer or {}).get("status"))
    assert len(set(seen.values())) == 1, (
        f"the answer depends on the wake interval rather than on the "
        f"world: {seen}")
    assert set(seen.values()) == {("cutoff", "NO_AT_CUTOFF")}, seen


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
                              "after": "30 minutes", "follow_up": False,
                              "by": "ada_vance"}, "wakes": []}), {}
            if "attempts: If confirmed" in user:
                # ... and the dependent one is quick
                return json.dumps({
                    "judgment": "she sends it.",
                    "event": {"description": "Ada transfers the deposit on.",
                              "for": ["ada_vance"], "observed": True,
                              "after": "1 minutes", "follow_up": False,
                              "by": "ada_vance"}, "wakes": []}), {}
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
                              "after": "1 minutes", "follow_up": False,
                              "by": "ada_vance"}, "wakes": []}), {}
            # the attention question, answered with a person acting
            return json.dumps({
                "judgment": "he answers her.",
                "event": {"description": "Bo replies that the hall is "
                                         "confirmed for the 14th.",
                          "for": ["ada_vance"], "observed": True,
                          "after": "20 minutes", "follow_up": False,
                          "by": "bo_ferrer"}, "wakes": []}), {}
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
                              "after": "1 minutes", "follow_up": False,
                              "by": "ada_vance"}, "wakes": []}), {}
            return json.dumps({
                "judgment": "it sits there.",
                "event": {"description": "The proposal remains unread in "
                                         "Bo's inbox.",
                          "for": ["bo_ferrer"], "observed": False,
                          "after": "2 hours", "follow_up": False,
                          "by": None}, "wakes": []}), {}
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
