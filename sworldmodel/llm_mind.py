"""Phase B: a live LLM-backed actor behind the exact same Mind interface.

The LLM receives ONLY the rendered ActorView (its own local state, noticed
information, and the authoritative time context) and returns ONLY a JSON
decision: intentions, private-state updates about itself, and an optional
future-wake request.  It has no handle on the World, Clock, queue, terminal
or other actors -- structurally it cannot mutate shared state, and everything
it returns passes through the same kernel validation as scripted minds
(forbidden ops are recorded as mind.violation, unknown verbs are rejected,
durations require provenance).

Model responses and raw exchanges are recorded in the ledger
(``mind.exchange``) so runs remain inspectable; replay never calls the LLM.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import timedelta

from .actions import Intention
from .actors import Decision, Mind
from .simclock import Duration, parse_iso

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"

SYSTEM_PROMPT = """You are {name}, a real person, living through the situation described.
You are not an assistant and you are not narrating a story: you are this person,
making your own decisions inside your own day. You only know what appears in the
briefing below. You cannot see other people's thoughts, you cannot control
outcomes, and your actions take real time. You propose what you do next; the
world decides what actually happens.

Respond with ONLY a JSON object, no markdown fences, with this shape:
{{
  "note": "one sentence: what you are thinking/deciding and why",
  "updates": [
    {{"op": "actor.belief", "data": {{"actor": "{actor_id}", "topic": "...",
       "statement": "...", "basis": "where this belief comes from"}}}},
    {{"op": "actor.memory", "data": {{"actor": "{actor_id}", "kind": "note",
       "content": "...", "source": "decision"}}}}
  ],
  "intentions": [
    {{"verb": "<one of the available actions>", "params": {{...}},
       "duration_minutes": <realistic number>,
       "duration_basis": "actor_chosen",
       "duration_note": "why this long",
       "note": "why you are doing this"}}
  ],
  "wake_me_in_minutes": null
}}

Rules:
- updates may only use ops actor.belief / actor.memory / actor.plan /
  actor.emotion (data.actor must be "{actor_id}").
- intentions[].verb must be one of the actions listed as available to you.
- durations must be realistic for a human doing that task.
- if nothing needs doing right now, return empty lists.
- "wake_me_in_minutes": set a number only if you genuinely want to revisit
  the situation later without any new trigger."""


class LLMUnavailable(RuntimeError):
    pass


def _http_json(url: str, payload: dict, api_key: str, timeout: float = 120.0) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    ctx = ssl.create_default_context(
        cafile=CA_BUNDLE if os.path.exists(CA_BUNDLE) else None)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


class DeepseekMind(Mind):
    """One live actor.  persona_brief is the identity/context injection the
    world compiler would normally produce."""

    def __init__(self, actor_id: str, name: str, persona_brief: str,
                 model: str = "deepseek-chat", temperature: float = 0.0,
                 max_retries: int = 2, transport=None) -> None:
        self.actor_id = actor_id
        self.name = name
        self.persona_brief = persona_brief
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.transport = transport or self._call_api   # injectable for tests
        self.last_exchange = None

    # -- transport ------------------------------------------------------
    def _call_api(self, system: str, user: str) -> str:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise LLMUnavailable("DEEPSEEK_API_KEY is not set")
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }
        try:
            out = _http_json(DEEPSEEK_URL, payload, api_key)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise LLMUnavailable(f"Deepseek API unreachable: {e}") from e
        return out["choices"][0]["message"]["content"]

    # -- Mind interface -------------------------------------------------
    def decide(self, view) -> Decision:
        system = SYSTEM_PROMPT.format(name=self.name, actor_id=self.actor_id)
        user = self.persona_brief + "\n\n=== YOUR CURRENT SITUATION ===\n" + view.render()
        raw, err = None, None
        for attempt in range(self.max_retries + 1):
            raw = self.transport(system, user)
            try:
                decision = self._parse(raw, view)
                self.last_exchange = {"request": user, "system": system,
                                      "response": raw, "attempt": attempt,
                                      "parsed": True}
                return decision
            except (ValueError, KeyError, TypeError) as e:
                err = str(e)
                user = (user + f"\n\nYour previous reply could not be parsed "
                               f"({err}). Reply again with ONLY the JSON object.")
        self.last_exchange = {"request": user, "system": system, "response": raw,
                              "parsed": False, "error": err}
        return Decision(note=f"mind output unparseable after retries: {err}")

    def _parse(self, raw: str, view) -> Decision:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        obj = json.loads(text)
        updates = []
        for u in obj.get("updates", []) or []:
            updates.append((u["op"], u["data"]))
        intentions = []
        for it in obj.get("intentions", []) or []:
            dur = None
            if it.get("duration_minutes") is not None:
                # the actor stated this number, so "actor_chosen" is factual;
                # an absent justification is RECORDED as absent, never invented
                dur = Duration(timedelta(minutes=float(it["duration_minutes"])),
                               it.get("duration_basis") or "actor_chosen",
                               it.get("duration_note")
                               or "stated by the actor; no justification given")
            intentions.append(Intention(verb=it["verb"],
                                        params=it.get("params", {}) or {},
                                        duration=dur, note=it.get("note", "")))
        wake_at = None
        if obj.get("wake_me_in_minutes"):
            wake_at = view.now + timedelta(minutes=float(obj["wake_me_in_minutes"]))
        return Decision(intentions=intentions, updates=updates,
                        wake_me_at=wake_at, wake_me_reason="LLM-chosen revisit",
                        note=str(obj.get("note", "")))
