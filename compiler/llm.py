"""LLM transport for the compiler: strict JSON calls with schema repair.

Every call is temperature-0 JSON mode, validated immediately; validation
errors are echoed back for a bounded number of repair attempts, network
errors retry with exponential backoff, and every exchange (including failed
attempts) is recorded in the compile trace so compilation is inspectable and
auditable after the fact.  A failed call raises ``StageFailed`` -- callers
turn that into UNSUPPORTED items or a structured compile failure, never a
crash."""
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

#: Backstop against runaway compiles (a generous multiple of a normal run).
MAX_CALLS_PER_COMPILE = 250


class LLMUnavailable(RuntimeError):
    """The API could not be reached after bounded retries."""


class StageFailed(RuntimeError):
    """A compiler stage could not obtain a valid response."""


class Trace:
    """Append-only record of every LLM exchange in a compile run."""

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.calls = 0

    def log(self, **entry) -> None:
        self.entries.append(entry)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


class Caller:
    """One configured LLM endpoint.  ``transport`` is injectable so tests
    run scripted, fully deterministic compiles with zero network."""

    def __init__(self, model: str = DEFAULT_MODEL, transport=None,
                 max_repairs: int = 2, network_retries: int = 3) -> None:
        self.model = model
        self.transport = transport or self._call_api
        self.max_repairs = max_repairs
        self.network_retries = network_retries

    # -- network --------------------------------------------------------
    def _call_api(self, system: str, user: str) -> str:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise LLMUnavailable("DEEPSEEK_API_KEY is not set")
        payload = {"model": self.model, "temperature": 0.0, "max_tokens": 4000,
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
        delay = 2.0
        last = None
        for _ in range(self.network_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=180.0, context=ctx) as resp:
                    out = json.loads(resp.read().decode("utf-8"))
                return out["choices"][0]["message"]["content"]
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                last = e
                time.sleep(delay)
                delay *= 2
        raise LLMUnavailable(f"API unreachable after retries: {last}")

    # -- the one call shape every stage uses ----------------------------
    def ask_json(self, stage: str, system: str, user: str, trace: Trace,
                 validate=None):
        """Call, parse, validate; echo errors back for bounded repair
        attempts.  Returns the validated object or raises StageFailed."""
        if os.environ.get("WORLDC_VERBOSE"):
            print(f"  [compile] {stage} (call {trace.calls + 1})", flush=True)
        prompt = user
        last_errors: list = []
        for attempt in range(self.max_repairs + 1):
            if trace.calls >= MAX_CALLS_PER_COMPILE:
                raise StageFailed(
                    f"{stage}: compile exceeded {MAX_CALLS_PER_COMPILE} LLM calls")
            trace.calls += 1
            raw = self.transport(system, prompt)
            try:
                obj = json.loads(_strip_fences(raw))
                errors = list(validate(obj)) if validate else []
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                obj, errors = None, [f"response was not valid JSON: {e}"]
            trace.log(stage=stage, attempt=attempt, system=system, user=prompt,
                      response=raw, ok=not errors, errors=errors)
            if not errors:
                return obj
            last_errors = errors
            prompt = (user + "\n\nYour previous reply was rejected:\n- "
                      + "\n- ".join(str(e) for e in errors)
                      + "\nReply again with ONLY a corrected JSON object.")
        raise StageFailed(f"{stage}: no valid response after "
                          f"{self.max_repairs + 1} attempts: {last_errors}")
