"""Shared model transport for the compiler's two calls.

Deliberately tiny: one JSON-mode request, recorded verbatim so every
compilation is inspectable and re-checkable without re-running the model.
"""
from __future__ import annotations

import http.client
import json
import os
import ssl
import time
import urllib.error
import urllib.request

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"

#: Transport-only retries (a connection that dropped before any reply
#: arrived). Never a retry of a reply that arrived and was rejected.
TRANSPORT_ATTEMPTS = 3


class ModelUnavailable(RuntimeError):
    pass


class TruncatedResponse(ValueError):
    """The model hit its output limit mid-document. Never salvage a partial
    world -- a truncated scenario is not a smaller scenario, it is a broken
    one."""


def call_json(system: str, user: str, model: str = "deepseek-chat",
              temperature: float = 0.0, max_tokens: int = 16000,
              timeout: float = 600.0) -> tuple:
    """Return (parsed_object, raw_text, usage). Raises ModelUnavailable on
    transport failure and ValueError if the reply is not JSON."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ModelUnavailable("DEEPSEEK_API_KEY is not set")
    payload = {
        "model": model, "temperature": temperature, "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        DEEPSEEK_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    ctx = ssl.create_default_context(
        cafile=CA_BUNDLE if os.path.exists(CA_BUNDLE) else None)
    # A dropped connection means NO answer arrived -- retrying asks the
    # same question again. That is categorically different from re-rolling
    # a reply that did arrive and failed validation, which this compiler
    # never does: a received answer is repaired once, never resampled.
    body, last = None, None
    for attempt in range(TRANSPORT_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=timeout,
                                        context=ctx) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            break
        except (urllib.error.URLError, OSError, TimeoutError,
                http.client.HTTPException) as e:
            last = e
            if attempt + 1 < TRANSPORT_ATTEMPTS:
                time.sleep(2 ** attempt)
    if body is None:
        raise ModelUnavailable(
            f"Deepseek API unreachable after {TRANSPORT_ATTEMPTS} attempts: "
            f"{last}") from last
    usage = body.get("usage") or {}
    choice = body["choices"][0]
    raw = choice["message"]["content"]
    if choice.get("finish_reason") == "length":
        raise TruncatedResponse(
            f"the reply hit the {max_tokens}-token output limit and stopped "
            f"mid-document ({len(raw)} chars). Return a SMALLER world: include "
            f"only what can change the answer.")
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text), raw, usage
