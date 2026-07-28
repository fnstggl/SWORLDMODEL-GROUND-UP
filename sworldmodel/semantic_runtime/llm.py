"""Provider transport for the semantic runtime.

The compiler's caller is frozen with a hard three-call budget by design,
so the runtime carries its own caller with the same hardening: a whole-
request wall deadline, chunked reads under a total deadline, exactly ONE
technical retry per semantic call, and complete logging of every attempt
(prompt, raw body, tokens, duration, validation outcome).

A run-level call ceiling exists only as a runaway backstop.  It is sized
above the ordinary path (see ``trajectory.budget_for``) so that reaching
it means something is genuinely looping, and a small number of calls is
held in reserve so that a run which does spend its budget can still take
an honest final judgment on the trajectory it actually produced instead of
dying with nothing.  Exceeding the ceiling is never a silent truncation:
it is a recorded horizon, exactly like the step ceiling.
"""
from __future__ import annotations

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request

API_URL = "https://api.deepseek.com/chat/completions"
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"
DEFAULT_MODEL = "deepseek-chat"

SOCKET_TIMEOUT_S = 90.0
TOTAL_READ_DEADLINE_S = 240.0
TOTAL_REQUEST_DEADLINE_S = 270.0
MAX_RETRIES_PER_CALL = 1

#: Calls held out of the ordinary budget so the final judgment can always
#: be taken (one call plus its one retry).
RESERVED_FINAL_CALLS = 2


class RuntimeTechnicalFailure(RuntimeError):
    """A semantic call could not produce a usable response; nothing is
    committed."""


class CallBudgetExceeded(RuntimeError):
    """The run-level backstop tripped."""


class RuntimeCaller:
    """One configured endpoint with full per-call logging."""

    #: every provider attempt made by any caller in this process.  Replay
    #: reads it before and after reconstructing, so "zero provider calls"
    #: is a measurement rather than a claim.
    total_calls = 0

    def __init__(self, model: str = DEFAULT_MODEL, transport=None,
                 max_calls: int = 400,
                 reserved_calls: int = RESERVED_FINAL_CALLS) -> None:
        self.model = model
        self.transport = transport or self._call_api
        self.max_calls = max_calls
        self.reserved_calls = reserved_calls
        self.calls: list[dict] = []

    # -- budget --------------------------------------------------------
    def _ordinary_ceiling(self) -> int:
        return max(1, self.max_calls - self.reserved_calls)

    def budget_exhausted(self) -> bool:
        """True once only the reserved final-judgment calls remain."""
        return len(self.calls) >= self._ordinary_ceiling()

    # -- provider ------------------------------------------------------
    def _call_api(self, system: str, user: str):
        box: dict = {}

        def work():
            try:
                box["result"] = self._do_request(system, user)
            except BaseException as e:
                box["error"] = e

        th = threading.Thread(target=work, daemon=True)
        th.start()
        th.join(TOTAL_REQUEST_DEADLINE_S)
        if th.is_alive():
            raise TimeoutError(f"provider request exceeded "
                               f"{TOTAL_REQUEST_DEADLINE_S:.0f}s")
        if "error" in box:
            raise box["error"]
        return box["result"]

    def _do_request(self, system: str, user: str):
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeTechnicalFailure("DEEPSEEK_API_KEY is not set")
        payload = {"model": self.model, "temperature": 0.7,
                   "max_tokens": 1200,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        req = urllib.request.Request(
            API_URL, data=json.dumps(payload).encode("utf-8"),
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
                    raise TimeoutError("response exceeded the read deadline")
                chunk = resp.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        out = json.loads(b"".join(chunks).decode("utf-8"))
        return (out["choices"][0]["message"]["content"], out.get("usage", {}))

    # -- one semantic call ---------------------------------------------
    def ask(self, role: str, system: str, user: str, validate,
            *, sim_time: str = "", trigger: str = "",
            reserved: bool = False) -> dict:
        """Call, parse, validate; ONE retry of the same call on failure.
        Returns {"parsed", "raw", "call_id"}; raises
        RuntimeTechnicalFailure after the retry, having committed
        nothing.  ``reserved=True`` spends the held-back final-judgment
        allowance and is used only for the judgment that closes a run."""
        ceiling = self.max_calls if reserved else self._ordinary_ceiling()
        if len(self.calls) >= ceiling:
            raise CallBudgetExceeded(
                f"{role}: run exceeded {ceiling} provider calls")
        last_err = None
        for attempt in range(MAX_RETRIES_PER_CALL + 1):
            call_id = f"c{len(self.calls) + 1}"
            t0 = time.monotonic()
            # a retry that repeats the identical prompt gets the identical
            # mistake; the rejection reason is stated so the model can
            # correct exactly what was wrong.  This says nothing about the
            # situation -- only about the shape of the reply.
            attempt_user = user if not attempt else (
                f"{user}\n\nYOUR PREVIOUS REPLY WAS REJECTED\n"
                f"{last_err}\n"
                f"Reply again with ONLY a corrected JSON object that fixes "
                f"exactly that problem.  Change nothing else.")
            entry = {"call_id": call_id, "role": role, "model": self.model,
                     "attempt": attempt, "system": system,
                     "user": attempt_user,
                     "raw": None, "parsed": None, "validation": None,
                     "sim_time": sim_time, "trigger": trigger,
                     "wall_s": None, "input_tokens": 0, "output_tokens": 0}
            try:
                RuntimeCaller.total_calls += 1
                result = self.transport(system, attempt_user)
                raw, usage = result if isinstance(result, tuple) else (result, {})
                entry["raw"] = raw
                entry["wall_s"] = round(time.monotonic() - t0, 3)
                entry["input_tokens"] = (usage or {}).get("prompt_tokens", 0)
                entry["output_tokens"] = (usage or {}).get("completion_tokens", 0)
                obj = json.loads(_strip_fences(raw))
                parsed = validate(obj)
                entry["parsed"] = parsed if isinstance(parsed, dict) else obj
                entry["validation"] = "ok"
                self.calls.append(entry)
                return {"parsed": parsed, "raw": raw, "call_id": call_id}
            except Exception as e:
                entry["wall_s"] = entry["wall_s"] or round(
                    time.monotonic() - t0, 3)
                entry["validation"] = f"{type(e).__name__}: {e}"
                self.calls.append(entry)
                last_err = e
        raise RuntimeTechnicalFailure(
            f"{role}: no valid response after {MAX_RETRIES_PER_CALL + 1} "
            f"attempts: {last_err}")

    def metrics(self) -> dict:
        by_role: dict = {}
        for c in self.calls:
            r = by_role.setdefault(c["role"], {"calls": 0, "retries": 0,
                                               "wall_s": 0.0,
                                               "input_tokens": 0,
                                               "output_tokens": 0})
            r["calls"] += 1
            r["retries"] += 1 if c["attempt"] else 0
            r["wall_s"] = round(r["wall_s"] + (c["wall_s"] or 0), 2)
            r["input_tokens"] += c["input_tokens"]
            r["output_tokens"] += c["output_tokens"]
        return {"provider_calls": len(self.calls), "by_role": by_role,
                "total_input_tokens": sum(c["input_tokens"] for c in self.calls),
                "total_output_tokens": sum(c["output_tokens"] for c in self.calls),
                "total_wall_s": round(sum(c["wall_s"] or 0
                                          for c in self.calls), 2)}


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
    return t.strip()
