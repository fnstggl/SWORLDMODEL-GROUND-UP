"""Transport robustness: a connection that drops before any reply
arrives is retried (the question was never answered), while a reply that
DID arrive is never resampled -- that distinction is the whole point."""
import http.client
import json

import pytest

from compiler import llm
from compiler.llm import ModelUnavailable


def _fake_response(payload):
    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")
    return R()


OK = {"choices": [{"message": {"content": '{"ok": true}'},
                   "finish_reason": "stop"}],
      "usage": {"total_tokens": 7}}


def test_incomplete_read_is_retried_not_crashed(monkeypatch):
    """The failure that killed a live run: IncompleteRead subclasses
    HTTPException, not OSError, so it escaped the transport guard."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def flaky(req, timeout=None, context=None):
        calls.append(1)
        if len(calls) == 1:
            raise http.client.IncompleteRead(b"")
        return _fake_response(OK)

    monkeypatch.setattr(llm.urllib.request, "urlopen", flaky)
    doc, raw, usage = llm.call_json("sys", "user")
    assert doc == {"ok": True}
    assert len(calls) == 2


def test_transport_failure_gives_up_honestly(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def dead(req, timeout=None, context=None):
        calls.append(1)
        raise http.client.IncompleteRead(b"")

    monkeypatch.setattr(llm.urllib.request, "urlopen", dead)
    with pytest.raises(ModelUnavailable, match="after 3 attempts"):
        llm.call_json("sys", "user")
    assert len(calls) == llm.TRANSPORT_ATTEMPTS


def test_a_reply_that_arrives_is_never_resampled(monkeypatch):
    """Unparseable content is a defect the caller repairs once with the
    exact complaint -- the transport must not quietly ask again."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def garbage(req, timeout=None, context=None):
        calls.append(1)
        return _fake_response(
            {"choices": [{"message": {"content": "not json at all"},
                          "finish_reason": "stop"}], "usage": {}})

    monkeypatch.setattr(llm.urllib.request, "urlopen", garbage)
    with pytest.raises(ValueError):
        llm.call_json("sys", "user")
    assert len(calls) == 1
