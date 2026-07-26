"""Phase B: one live LLM-backed actor behind the same Mind interface.

The deterministic tests here drive DeepseekMind through an injected fake
transport to prove the containment contract without the network: the model
sees only the rendered ActorView, and everything it returns passes the same
kernel validation as scripted minds -- forbidden ops are recorded and
skipped, unknown verbs are rejected, and shared state stays untouched.

The live test (real Deepseek API) runs only when DEEPSEEK_API_KEY is set.
"""
import json
import os
import re

import pytest

from sworldmodel import Engine
from sworldmodel.llm_mind import DeepseekMind
from worlds import email_world


class FakeTransport:
    """Plays the role of the Deepseek API: understands only the rendered
    view text it is given (like the real model) and answers from a script."""

    def __init__(self, behavior="cooperative"):
        self.behavior = behavior
        self.calls = []

    def __call__(self, system, user):
        self.calls.append(user)
        if self.behavior == "garbage_then_valid":
            self.behavior = "cooperative"
            return "sorry, here is my answer in prose, not JSON"
        if self.behavior == "hostile":
            return json.dumps({
                "note": "trying to escape",
                "updates": [
                    {"op": "actor.belief",
                     "data": {"actor": "alice", "topic": "pwned",
                              "statement": "x", "basis": "x"}},
                    {"op": "fact.set", "data": {"key": "pwned", "value": True}},
                ],
                "intentions": [{"verb": "rewrite_history", "params": {},
                                "duration_minutes": 1,
                                "duration_basis": "actor_chosen"}],
                "wake_me_in_minutes": None})
        # cooperative: behave like a sensible Bob using only the view text
        m = re.search(r"message (i\d+) from alice[^:]*: (.*)", user)
        if m and "You just finished: read_message" not in user:
            info_id = m.group(1)
            return json.dumps({
                "note": "Alice needs the Q2 numbers; reading her email first.",
                "updates": [],
                "intentions": [{"verb": "read_message",
                                "params": {"info": info_id,
                                           "content": m.group(2)},
                                "duration_minutes": 6,
                                "duration_basis": "actor_chosen",
                                "duration_note": "reading carefully"}],
                "wake_me_in_minutes": None})
        if "You just finished: read_message" in user:
            belief = re.search(r"\[q2_numbers\] ([^\n]+) \(basis", user)
            figure = belief.group(1) if belief else "the final Q2 numbers"
            return json.dumps({
                "note": "Replying with the confirmed figure.",
                "updates": [{"op": "actor.belief",
                             "data": {"actor": "bob", "topic": "alice_request",
                                      "statement": "Alice needs the Q2 numbers "
                                                   "confirmed.",
                                      "basis": "her email, read in full"}}],
                "intentions": [{"verb": "send_message",
                                "params": {"to": "alice", "channel": "email",
                                           "content": f"Hi Alice -- confirmed: "
                                                      f"{figure}",
                                           "data": {"type": "reply",
                                                    "thread": "q2"}},
                                "duration_minutes": 12,
                                "duration_basis": "actor_chosen",
                                "duration_note": "double-checking while writing"}],
                "wake_me_in_minutes": None})
        return json.dumps({"note": "nothing to do", "updates": [],
                           "intentions": [], "wake_me_in_minutes": None})


def llm_bob(behavior="cooperative"):
    transport = FakeTransport(behavior)
    mind = DeepseekMind("bob", "Bob Okafor",
                        persona_brief="You are Bob Okafor, finance lead. You "
                                      "locked the Q2 numbers yourself.",
                        transport=transport)
    return mind, transport


def test_llm_actor_through_the_same_pipeline():
    w, minds, t = email_world.build()
    mind, transport = llm_bob()
    minds["bob"] = mind
    out = Engine(w, minds, t).run()
    assert out.status == "resolved" and out.answer["answer"] == "yes"
    # every model exchange is in the ledger; replay makes zero LLM calls
    exchanges = [r for r in w.records if r["op"] == "mind.exchange"]
    assert len(exchanges) == len(transport.calls) == out.metrics["llm_calls"]
    assert all(r["data"]["parsed"] for r in exchanges)
    # the model was shown ONLY its rendered local view
    for sent in transport.calls:
        assert "alice_request" not in sent or "YOUR CURRENT SITUATION" in sent
        assert "state_hash" not in sent and "world_version" not in sent


def test_hostile_llm_output_is_contained():
    w, minds, t = email_world.build()
    mind, transport = llm_bob("hostile")
    minds["bob"] = mind
    out = Engine(w, minds, t).run()
    violations = [r for r in w.records if r["op"] == "mind.violation"]
    rejections = [r for r in w.records if r["op"] == "intention.rejected"]
    assert any("alice" in v["data"]["reason"] for v in violations)
    assert any("fact.set" in v["data"]["reason"] for v in violations)
    assert any("rewrite_history" in r["data"]["verb"] for r in rejections)
    assert "pwned" not in w.facts
    assert "pwned" not in w.actors["alice"].beliefs
    # the run still terminates mechanically: Bob never replied
    assert out.answer["answer"] == "no"


def test_unparseable_output_retries_then_noops():
    w, minds, t = email_world.build()
    mind, transport = llm_bob("garbage_then_valid")
    minds["bob"] = mind
    out = Engine(w, minds, t).run()
    exchanges = [r for r in w.records if r["op"] == "mind.exchange"]
    assert exchanges[0]["data"]["attempt"] == 1        # first reply was garbage
    assert out.answer["answer"] == "yes"


@pytest.mark.skipif(not os.environ.get("DEEPSEEK_API_KEY"),
                    reason="DEEPSEEK_API_KEY not set")
def test_live_deepseek_actor():
    w, minds, t = email_world.build()
    minds["bob"] = DeepseekMind(
        "bob", "Bob Okafor",
        persona_brief="You are Bob Okafor, finance lead on the West Coast. "
                      "You personally locked the final Q2 pipeline total of "
                      "$4.2M on March 3. Alice is a trusted colleague; you "
                      "answer colleagues promptly once you see their request.")
    out = Engine(w, minds, t).run()
    # non-deterministic content, deterministic guarantees:
    assert out.status in ("resolved", "cutoff")
    assert out.metrics["llm_calls"] >= 1
    exchanges = [r for r in w.records if r["op"] == "mind.exchange"]
    assert exchanges, "live exchanges must be recorded for replay"
    # whatever the model did, it could not have touched shared state directly:
    # every post-genesis record has a cause chain rooted in kernel mechanics
    sealed = next(r["seq"] for r in w.records if r["op"] == "genesis.sealed")
    assert all(r["cause"] is not None for r in w.records if r["seq"] > sealed)
