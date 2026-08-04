"""The recorder must capture EVERY live call -- including every retry --
and must never write a credential.

These are harness tests, not engine tests: they exercise
``experiments/full_trace_validation/recorder.py`` against a stubbed
provider so the guarantees can be checked without spending live calls.
"""

from __future__ import annotations

import json
import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip("harness suite runs in the pinned engine environment "
                "(Python >= 3.12); run with /home/user/engine-env/bin/"
                "python", allow_module_level=True)

pytest.importorskip("concordia.language_model.language_model",
                    exc_type=ImportError)

from experiments.full_trace_validation import recorder as rec  # noqa: E402


def _context(tmp_path, experiment_id="unit"):
    ledger = rec.CallLedger(experiment_id, tmp_path / "all_calls.jsonl")
    return rec.RecorderContext(experiment_id=experiment_id, ledger=ledger,
                               boundary=rec.NetworkBoundary())


def _model(context, **kwargs):
    defaults = dict(api_key="sk-unit-test-key-abcdefghijklmnop",
                    system_hint="hint", role="actor", actor_id="a1",
                    actor_name="A", branch_id="br_unit",
                    cursor=rec.StepCursor(), seam_name="actor:a1")
    defaults.update(kwargs)
    return rec.RecordedDeepSeekChatModel(context, **defaults)


# ---------------------------------------------------------------------------
# every call is recorded
# ---------------------------------------------------------------------------


def test_every_successful_call_becomes_exactly_one_record(tmp_path,
                                                          monkeypatch):
    context = _context(tmp_path)
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        return "the response", {"prompt_tokens": 5, "completion_tokens": 3}

    monkeypatch.setattr(rec, "_chat_completion", fake)
    model = _model(context)
    assert model.sample_text("prompt one") == "the response"
    assert model.sample_text("prompt two") == "the response"

    records = rec.read_ledger(tmp_path / "all_calls.jsonl")
    assert len(records) == 2 == len(calls)
    assert [r["call_id"] for r in records] == ["unit-000001", "unit-000002"]
    assert all(set(r) == set(rec.RECORD_FIELDS) for r in records)
    assert records[0]["request"]["messages"][1]["content"] == "prompt one"
    assert records[0]["response_raw"] == "the response"
    assert records[0]["tokens"] == {"prompt_tokens": 5,
                                    "completion_tokens": 3}
    assert records[0]["retry"] == 0 and records[0]["error"] is None
    proof = context.instrumentation()["equality_proof"]
    assert proof["all_equal"] is True
    assert proof["ledger_records_written"] == 2
    assert proof["network_boundary_requests"] == 2
    assert proof["seam_attempt_total"] == 2


def test_every_retry_attempt_is_recorded_with_its_own_call_id(tmp_path,
                                                              monkeypatch):
    context = _context(tmp_path)
    attempts = {"n": 0}

    def flaky(**kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("HTTP Error 503: Service Unavailable")
        return "eventually fine", {}

    monkeypatch.setattr(rec, "_chat_completion", flaky)
    monkeypatch.setattr(rec.time, "sleep", lambda seconds: None)
    model = _model(context)
    assert model.sample_text("p") == "eventually fine"

    records = rec.read_ledger(tmp_path / "all_calls.jsonl")
    assert [r["retry"] for r in records] == [0, 1, 2]
    assert len({r["call_id"] for r in records}) == 3
    assert "503" in records[0]["error"] and "503" in records[1]["error"]
    assert records[2]["error"] is None
    assert context.instrumentation()["equality_proof"]["all_equal"] is True
    assert context.ledger.snapshot()["records_with_error"] == 2


def test_persistent_failure_raises_loudly_with_the_ledger_intact(
        tmp_path, monkeypatch):
    context = _context(tmp_path)

    def always_503(**kwargs):
        raise RuntimeError("HTTP Error 503: Service Unavailable")

    monkeypatch.setattr(rec, "_chat_completion", always_503)
    monkeypatch.setattr(rec.time, "sleep", lambda seconds: None)
    model = _model(context)
    with pytest.raises(rec.LiveCallFailed) as excinfo:
        model.sample_text("p")
    assert "503" in str(excinfo.value)
    records = rec.read_ledger(tmp_path / "all_calls.jsonl")
    assert len(records) == rec.MAX_ATTEMPTS
    assert [r["retry"] for r in records] == list(range(rec.MAX_ATTEMPTS))
    assert all(r["error"] for r in records)
    assert all(r["response_raw"] is None for r in records)
    # a run that dies on persistent 503 leaves the proof intact
    assert context.instrumentation()["equality_proof"]["all_equal"] is True


def test_a_bypassed_provider_request_desynchronizes_the_counters(tmp_path):
    """The proof has teeth: bumping the network boundary without writing a
    record (what a bypassing call path would do) breaks equality."""
    context = _context(tmp_path)
    context.boundary.bump("actor")
    assert context.instrumentation()["equality_proof"]["all_equal"] is False


def test_per_branch_sink_and_master_ledger_stay_in_step(tmp_path,
                                                        monkeypatch):
    context = _context(tmp_path)
    monkeypatch.setattr(rec, "_chat_completion",
                        lambda **kwargs: ("ok", {}))
    context.ledger.set_sink(tmp_path / "branches" / "c1" / "llm_calls.jsonl")
    _model(context).sample_text("one")
    context.ledger.set_sink(tmp_path / "branches" / "c2" / "llm_calls.jsonl")
    _model(context).sample_text("two")
    context.ledger.set_sink(None)

    master = rec.read_ledger(tmp_path / "all_calls.jsonl")
    first = rec.read_ledger(tmp_path / "branches" / "c1" / "llm_calls.jsonl")
    second = rec.read_ledger(tmp_path / "branches" / "c2" / "llm_calls.jsonl")
    assert len(master) == 2 and len(first) == 1 and len(second) == 1
    assert first[0] == master[0] and second[0] == master[1]


def test_step_cursor_attributes_calls_to_engine_steps():
    cursor = rec.StepCursor()
    assert cursor.on_gm_call() == 1        # pre-turn game-master work
    assert cursor.on_actor_call() == 1     # the step's single actor turn
    assert cursor.on_gm_call() == 1        # resolution of that turn
    assert cursor.on_actor_call() == 2     # the next step's actor turn
    assert cursor.on_gm_call() == 2
    assert cursor.actor_calls == 2


def test_sample_choice_is_recorded_before_it_is_refused(tmp_path):
    context = _context(tmp_path)
    model = _model(context, role="game_master", actor_id=None,
                   actor_name=None, seam_name="game_master")
    with pytest.raises(AssertionError):
        model.sample_choice("pick", ["a", "b"])
    records = rec.read_ledger(tmp_path / "all_calls.jsonl")
    assert len(records) == 1
    assert "sample_choice refused" in records[0]["error"]


# ---------------------------------------------------------------------------
# secrets
# ---------------------------------------------------------------------------


def test_scrub_removes_the_live_credential_value(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-live-DO-NOT-LEAK-123456")
    text = "Authorization: Bearer sk-live-DO-NOT-LEAK-123456"
    cleaned = rec.scrub(text)
    assert "sk-live-DO-NOT-LEAK-123456" not in cleaned
    assert rec._REDACTED in cleaned


def test_scrub_walks_nested_structures(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-nested-secret-value-999")
    payload = {"a": ["x", {"b": "key=sk-nested-secret-value-999"}]}
    cleaned = rec.scrub(payload)
    assert "sk-nested-secret-value-999" not in json.dumps(cleaned)


def test_a_record_carrying_a_credential_is_refused(tmp_path, monkeypatch):
    """Belt and braces: if the scrubber were bypassed, the writer refuses."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-refuse-me-abcdefghijkl")
    ledger = rec.CallLedger("unit", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(rec, "scrub", lambda value: value)
    record = {name: None for name in rec.RECORD_FIELDS}
    record.update({"call_id": "x", "experiment_id": "unit", "role": "other",
                   "retry": 0,
                   "request": {"messages": [
                       {"role": "user",
                        "content": "sk-refuse-me-abcdefghijkl"}]}})
    with pytest.raises(AssertionError, match="live credential"):
        ledger.append(record)
    assert not (tmp_path / "ledger.jsonl").exists() or \
        (tmp_path / "ledger.jsonl").read_text(encoding="utf-8") == ""


def test_authorization_headers_never_reach_a_record(tmp_path, monkeypatch):
    context = _context(tmp_path)
    monkeypatch.setattr(rec, "_chat_completion",
                        lambda **kwargs: (
                            "Authorization: Bearer sk-echoed-key-abcdefgh",
                            {}))
    _model(context).sample_text("echo the header back")
    text = (tmp_path / "all_calls.jsonl").read_text(encoding="utf-8")
    assert "sk-echoed-key-abcdefgh" not in text
    assert rec._REDACTED in text


def test_the_record_field_set_is_exact(tmp_path):
    ledger = rec.CallLedger("unit", tmp_path / "ledger.jsonl")
    record = {name: None for name in rec.RECORD_FIELDS}
    record.update({"call_id": "x", "role": "other", "retry": 0})
    ledger.append(record)
    with pytest.raises(AssertionError, match="unknown fields"):
        ledger.append(dict(record, extra_field=1))
    incomplete = dict(record)
    incomplete.pop("tokens")
    with pytest.raises(AssertionError, match="missing required fields"):
        ledger.append(incomplete)
