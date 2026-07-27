"""Provider transport and the hard semantic-call budget.

Two semantic LLM calls normally (scene construction + independent review),
three maximum (one targeted correction).  The budget is enforced BEFORE a
call is made: an attempt to open a fourth semantic slot raises
CompilerCallBudgetExceeded and the compile fails with
COMPILER_CALL_BUDGET_EXCEEDED -- the count is never merely reported after
the fact.

Nothing is hidden in a client library: every provider request (including
the single permitted technical retry per slot for transport/JSON failures)
is logged with prompts, raw response, tokens, duration, and attempt number.
Every request carries a hard total deadline; a timeout is a structured
technical failure, never an unbounded reroll."""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request

API_URL = "https://api.deepseek.com/chat/completions"
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"
DEFAULT_MODEL = "deepseek-chat"

MAX_SEMANTIC_CALLS = 3
#: transport/parse failures allow ONE logged retry per semantic slot; a
#: second failure is a structured technical failure of the compile
MAX_TECHNICAL_RETRIES_PER_SLOT = 1

SOCKET_TIMEOUT_S = 90.0
TOTAL_READ_DEADLINE_S = 300.0


class CompilerCallBudgetExceeded(RuntimeError):
    code = "COMPILER_CALL_BUDGET_EXCEEDED"


class TechnicalFailure(RuntimeError):
    """Transport or parse failure after the permitted retry."""


class SceneCaller:
    """One configured provider endpoint with full request logging.

    ``transport`` is injectable for tests: callable(system, user) -> either
    a raw string or (raw string, usage dict)."""

    def __init__(self, model: str = DEFAULT_MODEL, transport=None) -> None:
        self.model = model
        self.transport = transport or self._call_api
        self.requests: list[dict] = []      # every provider request, logged
        self.semantic_slots: list[str] = []

    # -- provider ------------------------------------------------------
    def _call_api(self, system: str, user: str):
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise TechnicalFailure("DEEPSEEK_API_KEY is not set")
        payload = {"model": self.model, "temperature": 0.0,
                   "max_tokens": 8000,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            API_URL, data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_key}"})
        ctx = ssl.create_default_context(
            cafile=CA_BUNDLE if os.path.exists(CA_BUNDLE) else None)
        with urllib.request.urlopen(req, timeout=SOCKET_TIMEOUT_S,
                                    context=ctx) as resp:
            deadline = time.monotonic() + TOTAL_READ_DEADLINE_S
            chunks = []
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"response exceeded the {TOTAL_READ_DEADLINE_S:.0f}s "
                        f"total deadline")
                chunk = resp.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        out = json.loads(b"".join(chunks).decode("utf-8"))
        usage = out.get("usage", {})
        return out["choices"][0]["message"]["content"], usage

    # -- the semantic budget -------------------------------------------
    def semantic_call(self, slot: str, system: str, user: str) -> dict:
        """Open a semantic slot (Call 1, 2, or 3), send the request, parse
        JSON.  Raises CompilerCallBudgetExceeded BEFORE exceeding the
        budget; TechnicalFailure after the permitted technical retry.
        Returns {"parsed": obj, "raw": str, "slot": slot}."""
        if len(self.semantic_slots) >= MAX_SEMANTIC_CALLS:
            raise CompilerCallBudgetExceeded(
                f"semantic call {slot!r} would be call "
                f"#{len(self.semantic_slots) + 1}; the budget is "
                f"{MAX_SEMANTIC_CALLS}")
        self.semantic_slots.append(slot)
        last_err = None
        for attempt in range(MAX_TECHNICAL_RETRIES_PER_SLOT + 1):
            t0 = time.monotonic()
            entry = {"slot": slot, "attempt": attempt, "system": system,
                     "user": user, "response": None, "usage": {},
                     "duration_s": None, "error": None}
            try:
                result = self.transport(system, user)
                raw, usage = result if isinstance(result, tuple) else (result, {})
                entry["response"] = raw
                entry["usage"] = usage
                entry["duration_s"] = round(time.monotonic() - t0, 3)
                parsed = json.loads(_strip_fences(raw))
                self.requests.append(entry)
                return {"parsed": parsed, "raw": raw, "slot": slot}
            except (urllib.error.URLError, OSError, TimeoutError,
                    json.JSONDecodeError, KeyError) as e:
                entry["duration_s"] = round(time.monotonic() - t0, 3)
                entry["error"] = f"{type(e).__name__}: {e}"
                self.requests.append(entry)
                last_err = e
        raise TechnicalFailure(
            f"{slot}: provider request failed after "
            f"{MAX_TECHNICAL_RETRIES_PER_SLOT + 1} attempts: {last_err}")

    def metrics(self) -> dict:
        per_slot = {}
        for r in self.requests:
            s = per_slot.setdefault(r["slot"], {"attempts": 0, "duration_s": 0.0,
                                                "prompt_tokens": 0,
                                                "completion_tokens": 0})
            s["attempts"] += 1
            s["duration_s"] = round(s["duration_s"] + (r["duration_s"] or 0), 3)
            s["prompt_tokens"] += (r["usage"] or {}).get("prompt_tokens", 0)
            s["completion_tokens"] += (r["usage"] or {}).get(
                "completion_tokens", 0)
        return {"semantic_calls": len(self.semantic_slots),
                "semantic_slots": list(self.semantic_slots),
                "provider_requests": len(self.requests),
                "total_prompt_tokens": sum(
                    (r["usage"] or {}).get("prompt_tokens", 0)
                    for r in self.requests),
                "total_completion_tokens": sum(
                    (r["usage"] or {}).get("completion_tokens", 0)
                    for r in self.requests),
                "per_slot": per_slot}


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return text.strip()
