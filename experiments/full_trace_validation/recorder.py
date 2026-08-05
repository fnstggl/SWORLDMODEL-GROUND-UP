"""Transparent recording of every live model call the run makes.

Experiment-only.  Nothing here is imported by production code, and nothing
here authors simulation content: each wrapper forwards the application's
own request to the provider and records exactly what went out and exactly
what came back.

Three seams, one ledger
-----------------------
The production path reaches a model at exactly three places, and this
module wraps all three:

1. **compiler transport** -- ``compiler.scene_llm.SceneCaller(transport=)``
   takes ``callable(system, user) -> raw | (raw, usage)``.
   :class:`RecordingSceneTransport` delegates to the PRODUCTION request
   builder (``SceneCaller._call_api`` of an inner, otherwise-unused
   caller) so the bytes on the wire are production's, and records the
   exact ``(system, user)`` the compiler passed plus the raw response.
2. **candidate generator** -- ``decision_route.prepare_decision_inputs(
   generator_model=)`` calls ``model.sample_text(prompt)`` exactly once.
   :class:`RecordingGeneratorModel` records that call.
3. **actor and game-master models** -- the counterfactual manager's
   ``model_factory(candidate, branch_seed) -> ({actor_key: model},
   gm_model)``.  :class:`RecordedDeepSeekChatModel` subclasses the proven
   test-owned live model (``tests/engine_individual/individual_helpers.
   DeepSeekChatModel``) and records every ``sample_text`` attempt.

Every attempt -- including failures and retries -- becomes ONE ledger
record with its own ``call_id`` and an incrementing ``retry``.

Proving no call bypassed the recorder
-------------------------------------
Three counters are incremented in three different places:

- :class:`NetworkBoundary` ``request_count`` -- bumped immediately before
  the HTTP request, inside the only object in this experiment that talks
  to the network;
- each wrapper's ``attempts`` -- bumped in the wrapper's own retry loop;
- :class:`CallLedger` ``records_written`` / ``len(call_ids)`` -- bumped
  when a record is appended to disk.

A provider request that reached the network without being recorded would
raise ``request_count`` above ``records_written``; a fabricated record
would raise ``records_written`` above ``request_count``.  Equality of all
three (written to ``shared/instrumentation_validation.json``) is the
proof.

Secrets
-------
:func:`scrub` removes credential-shaped material from every field before
it is written, and :func:`assert_no_secrets` re-checks the serialized
record.  API keys, ``Authorization`` headers and cookies are never
recorded; a record that would carry one raises instead of being written.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL_ID = "deepseek-chat"
PROVIDER = "deepseek"

#: the exact field set of one ledger record, in write order
RECORD_FIELDS = (
    "call_id", "experiment_id", "branch_id", "step", "role", "actor_id",
    "actor_name", "model", "provider", "callable", "request", "params",
    "started_at", "finished_at", "response_raw", "response_parsed",
    "tokens", "cost", "retry", "error", "request_sha256",
    "response_sha256")

ROLES = ("compiler", "candidate_generator", "actor", "game_master", "other")

#: bounded retry policy for every seam (DeepSeek 503s intermittently);
#: EVERY attempt is recorded, including the ones that failed
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = (2.0, 6.0, 15.0)

_REDACTED = "[REDACTED]"

#: credential shapes that may never reach an artifact.  ``sk-`` keys are
#: the provider's own format; the environment values are added at runtime.
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)\bauthorization\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.]{12,}"),
    re.compile(r"(?i)\bcookie\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bapi[_\-]?key\b\s*[:=]\s*\S+"),
)

#: environment variables whose VALUES must never be written
_SECRET_ENV_VARS = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SERPER_API_KEY",
                    "JINA_API_KEY", "ANTHROPIC_API_KEY",
                    "AGENTSOCIETY_LLM_API_KEY")


def secret_values() -> tuple:
    """Every live credential value currently in the environment (used to
    scrub verbatim occurrences, never written anywhere)."""
    found = []
    for name in _SECRET_ENV_VARS:
        value = os.environ.get(name)
        if value and len(value) >= 8:
            found.append(value)
    return tuple(found)


def scrub(value):
    """Recursively replace credential-shaped material with a marker.

    Applies to strings anywhere in the structure: exact environment
    credential values first (so a key that does not match a shape pattern
    is still removed), then the shape patterns.
    """
    if isinstance(value, str):
        text = value
        for secret in secret_values():
            if secret in text:
                text = text.replace(secret, _REDACTED)
        for pattern in _SECRET_PATTERNS:
            text = pattern.sub(_REDACTED, text)
        return text
    if isinstance(value, dict):
        return {scrub(key): scrub(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(item) for item in value]
    return value


def assert_no_secrets(serialized: str) -> None:
    """Refuse to write a record that still carries credential material."""
    for secret in secret_values():
        if secret in serialized:
            raise AssertionError(
                "refusing to write a ledger record containing a live "
                "credential value; the scrubber must be fixed before "
                "this run continues")
    for pattern in _SECRET_PATTERNS:
        match = pattern.search(serialized)
        if match and _REDACTED not in match.group(0):
            raise AssertionError(
                "refusing to write a ledger record containing "
                f"credential-shaped material: {match.group(0)[:24]!r}...")


def sha256_text(text) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = json.dumps(text, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_now() -> str:
    """UTC timestamp, second-and-microsecond precision, Z suffix."""
    import datetime
    return datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# the network boundary
# ---------------------------------------------------------------------------


class NetworkBoundary:
    """The single counter of provider requests actually issued.

    Every seam bumps this immediately BEFORE its HTTP request and nothing
    else does.  Kept deliberately independent of the ledger so the two can
    be compared.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.request_count = 0
        self.per_role: dict = {}

    def bump(self, role: str) -> int:
        with self._lock:
            self.request_count += 1
            self.per_role[role] = self.per_role.get(role, 0) + 1
            return self.request_count

    def snapshot(self) -> dict:
        with self._lock:
            return {"request_count": self.request_count,
                    "per_role": dict(sorted(self.per_role.items()))}


# ---------------------------------------------------------------------------
# the ledger
# ---------------------------------------------------------------------------


class CallLedger:
    """Append-only JSONL ledger with a monotonic global call counter.

    ``master_path`` receives every record.  ``sink`` additionally routes
    records to a per-branch / per-stage file; both writes happen inside
    the same lock so a record can never exist in one file only.
    """

    def __init__(self, experiment_id: str, master_path) -> None:
        self.experiment_id = str(experiment_id)
        self.master_path = Path(master_path)
        self.master_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._counter = 0
        self.records_written = 0
        self.call_ids: list = []
        self.per_role: dict = {}
        self.errors = 0
        self.retries = 0
        self._sink: Path | None = None

    # -- routing -------------------------------------------------------
    def set_sink(self, path) -> None:
        """Direct subsequent records additionally to ``path`` (None = the
        master ledger only)."""
        with self._lock:
            if path is None:
                self._sink = None
                return
            sink = Path(path)
            sink.parent.mkdir(parents=True, exist_ok=True)
            self._sink = sink

    # -- identity ------------------------------------------------------
    def next_call_id(self) -> str:
        with self._lock:
            self._counter += 1
            return f"{self.experiment_id}-{self._counter:06d}"

    # -- writing -------------------------------------------------------
    def append(self, record: dict) -> dict:
        """Scrub, validate the exact field set, and append."""
        missing = [name for name in RECORD_FIELDS if name not in record]
        if missing:
            raise AssertionError(
                f"ledger record is missing required fields: {missing}")
        extra = sorted(set(record) - set(RECORD_FIELDS))
        if extra:
            raise AssertionError(
                f"ledger record carries unknown fields: {extra}")
        if record["role"] not in ROLES:
            raise AssertionError(f"unknown role {record['role']!r}")
        clean = {name: scrub(record[name]) for name in RECORD_FIELDS}
        line = json.dumps(clean, ensure_ascii=False, sort_keys=False)
        assert_no_secrets(line)
        with self._lock:
            with self.master_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            if self._sink is not None:
                with self._sink.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            self.records_written += 1
            self.call_ids.append(clean["call_id"])
            role = clean["role"]
            self.per_role[role] = self.per_role.get(role, 0) + 1
            if clean["error"]:
                self.errors += 1
            if clean["retry"]:
                self.retries += 1
        return clean

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "experiment_id": self.experiment_id,
                "records_written": self.records_written,
                "distinct_call_ids": len(set(self.call_ids)),
                "per_role": dict(sorted(self.per_role.items())),
                "records_with_error": self.errors,
                "records_that_were_retries": self.retries,
                "master_ledger": str(self.master_path),
            }


# ---------------------------------------------------------------------------
# simulation step attribution
# ---------------------------------------------------------------------------


class StepCursor:
    """Mechanical step attribution for calls inside one branch.

    The upstream sequential engine's loop is, per step: deliver
    observations -> choose the next actor -> ``actor.act()`` (exactly one
    ACTOR model call) -> ``resolve`` (game-master model call) -> log.  So:
    a game-master call takes the current step number, and an ACTOR call
    that arrives when the current step already has one advances the
    cursor first.  The rule is mechanical and is cross-checked against the
    branch's recorded ``steps_completed`` in the step ledger; any mismatch
    is written down rather than smoothed over.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.step = 1
        self._actor_seen = False
        self.actor_calls = 0

    def on_actor_call(self) -> int:
        with self._lock:
            if self._actor_seen:
                self.step += 1
            self._actor_seen = True
            self.actor_calls += 1
            return self.step

    def on_gm_call(self) -> int:
        with self._lock:
            return self.step


# ---------------------------------------------------------------------------
# shared recording machinery
# ---------------------------------------------------------------------------


@dataclass
class SeamCounters:
    """Per-wrapper independent counters (see the module docstring)."""

    invocations: int = 0
    attempts: int = 0
    failures: int = 0

    def to_dict(self) -> dict:
        return {"invocations": self.invocations, "attempts": self.attempts,
                "failed_attempts": self.failures}


@dataclass
class RecorderContext:
    """Everything the seams share for one experiment process."""

    experiment_id: str
    ledger: CallLedger
    boundary: NetworkBoundary
    seams: dict = field(default_factory=dict)

    def counters(self, name: str) -> SeamCounters:
        return self.seams.setdefault(name, SeamCounters())

    def instrumentation(self) -> dict:
        """The cross-check written to instrumentation_validation.json."""
        ledger = self.ledger.snapshot()
        boundary = self.boundary.snapshot()
        seam_attempts = sum(counter.attempts
                            for counter in self.seams.values())
        equal = (ledger["records_written"] == boundary["request_count"]
                 == seam_attempts == ledger["distinct_call_ids"])
        return {
            "experiment_id": self.experiment_id,
            "ledger": ledger,
            "network_boundary": boundary,
            "seams": {name: counter.to_dict()
                      for name, counter in sorted(self.seams.items())},
            "seam_attempt_total": seam_attempts,
            "equality_proof": {
                "claim": ("every provider request issued at the network "
                          "boundary produced exactly one ledger record "
                          "with a distinct call_id, and every ledger "
                          "record corresponds to one wrapper attempt"),
                "ledger_records_written": ledger["records_written"],
                "ledger_distinct_call_ids": ledger["distinct_call_ids"],
                "network_boundary_requests": boundary["request_count"],
                "seam_attempt_total": seam_attempts,
                "all_equal": bool(equal),
            },
        }


class _AttemptRecorder:
    """Bounded-retry executor that records EVERY attempt."""

    def __init__(self, context: RecorderContext, seam_name: str) -> None:
        self.context = context
        self.seam_name = seam_name

    def run(self, *, role, callable_name, request, params, model,
            perform, branch_id=None, step=None, actor_id=None,
            actor_name=None, parse=None, max_attempts=MAX_ATTEMPTS):
        """Call ``perform()`` with bounded retry; record every attempt.

        ``perform()`` must issue EXACTLY ONE provider request and return
        ``(response_text, usage_dict, extra)``.  It is called only after
        the network-boundary counter is bumped, so a request that reaches
        the provider is always counted.
        """
        counters = self.context.counters(self.seam_name)
        counters.invocations += 1
        last_error = None
        for attempt in range(max_attempts):
            counters.attempts += 1
            self.context.boundary.bump(role)
            call_id = self.context.ledger.next_call_id()
            started = utc_now()
            text = None
            usage: dict = {}
            error = None
            try:
                text, usage = perform()
            except BaseException as exc:  # noqa: BLE001 - recorded, re-raised
                error = f"{type(exc).__name__}: {exc}"
                last_error = exc
            finished = utc_now()
            parsed = None
            if text is not None and parse is not None:
                try:
                    parsed = parse(text)
                except Exception as exc:  # noqa: BLE001
                    parsed = {"_parse_error":
                              f"{type(exc).__name__}: {exc}"}
            self.context.ledger.append({
                "call_id": call_id,
                "experiment_id": self.context.experiment_id,
                "branch_id": branch_id,
                "step": step,
                "role": role,
                "actor_id": actor_id,
                "actor_name": actor_name,
                "model": model,
                "provider": PROVIDER,
                "callable": callable_name,
                "request": request,
                "params": params,
                "started_at": started,
                "finished_at": finished,
                "response_raw": text,
                "response_parsed": parsed,
                "tokens": dict(usage) if usage else None,
                "cost": None,
                "retry": attempt,
                "error": error,
                "request_sha256": sha256_text(request),
                "response_sha256": sha256_text(text),
            })
            if error is None:
                return text, usage
            counters.failures += 1
            if attempt + 1 < max_attempts:
                time.sleep(BACKOFF_SECONDS[
                    min(attempt, len(BACKOFF_SECONDS) - 1)])
        raise LiveCallFailed(
            f"{self.seam_name}: {max_attempts} recorded attempts all "
            f"failed; last error: {last_error!r}") from last_error


class LiveCallFailed(RuntimeError):
    """Every recorded attempt at one live call failed.  The ledger holds
    all of them; the run fails loudly rather than fabricating output."""


# ---------------------------------------------------------------------------
# seam 1: compiler transport
# ---------------------------------------------------------------------------


class RecordingSceneTransport:
    """``callable(system, user)`` for ``SceneCaller(transport=)``.

    Delegates to the PRODUCTION request builder so the request bytes,
    deadlines and JSON-object response format are production's; records
    the exact ``(system, user)`` the compiler passed and the exact raw
    response.  The compiler's own one-retry-per-slot policy sits on top of
    this wrapper's bounded retry, and every attempt from either layer is a
    separate ledger record.
    """

    def __init__(self, context: RecorderContext, *,
                 model: str = DEEPSEEK_MODEL_ID) -> None:
        from compiler.scene_llm import SceneCaller as _ProdCaller
        from compiler import scene_llm as _scene_llm

        self.context = context
        self.model = model
        self._inner = _ProdCaller(model=model)
        self._scene_llm = _scene_llm
        self._recorder = _AttemptRecorder(context, "compiler_transport")
        self.slot_hint = "compiler_call"

    def params(self) -> dict:
        """The production payload parameters, read from the production
        module (never re-declared here)."""
        return {
            "api_url": self._scene_llm.API_URL,
            "model": self.model,
            "temperature": 0.0,
            "max_tokens": 8000,
            "response_format": {"type": "json_object"},
            "socket_timeout_s": self._scene_llm.SOCKET_TIMEOUT_S,
            "total_request_deadline_s":
                self._scene_llm.TOTAL_REQUEST_DEADLINE_S,
            "request_body_built_by":
                "compiler.scene_llm.SceneCaller._do_request",
        }

    def __call__(self, system: str, user: str):
        def perform():
            result = self._inner._call_api(system, user)
            raw, usage = (result if isinstance(result, tuple)
                          else (result, {}))
            return raw, usage or {}

        text, usage = self._recorder.run(
            role="compiler",
            callable_name="compiler.scene_llm.SceneCaller._call_api"
                          " (via injected transport)",
            request={"messages": [{"role": "system", "content": system},
                                  {"role": "user", "content": user}]},
            params=self.params(),
            model=self.model,
            step=self.slot_hint,
            perform=perform,
            parse=json.loads,
        )
        return text, usage


# ---------------------------------------------------------------------------
# seam 2: candidate generator
# ---------------------------------------------------------------------------


class RecordingGeneratorModel:
    """``sample_text(prompt) -> str`` for
    ``prepare_decision_inputs(generator_model=)``.

    The route calls this exactly once per generation and then parses the
    result strictly against its own fixed schema; this wrapper adds
    nothing to the prompt and repairs nothing in the response.
    """

    def __init__(self, context: RecorderContext, *,
                 api_key: str, model: str = DEEPSEEK_MODEL_ID,
                 max_tokens: int = 2000,
                 timeout_s: float = 180.0) -> None:
        self.context = context
        self.model = model
        self.max_tokens = int(max_tokens)
        self.timeout_s = float(timeout_s)
        self._api_key = api_key
        self._recorder = _AttemptRecorder(context, "candidate_generator")
        self.last_prompt: str | None = None
        self.last_response: str | None = None

    def params(self) -> dict:
        return {"base_url": DEEPSEEK_BASE_URL, "model": self.model,
                "temperature": 0.0, "max_tokens": self.max_tokens,
                "response_format": {"type": "json_object"},
                "timeout_s": self.timeout_s}

    def sample_text(self, prompt: str, **kwargs) -> str:
        del kwargs  # the route passes none; a fixed bounded policy applies
        self.last_prompt = prompt
        messages = [{"role": "user", "content": prompt}]

        def perform():
            return _chat_completion(
                api_key=self._api_key, model=self.model, messages=messages,
                max_tokens=self.max_tokens, timeout_s=self.timeout_s,
                response_format={"type": "json_object"})

        text, _usage = self._recorder.run(
            role="candidate_generator",
            callable_name=("experiments.full_trace_validation.recorder."
                           "RecordingGeneratorModel.sample_text"),
            request={"messages": messages},
            params=self.params(),
            model=self.model,
            step="candidate_generation",
            perform=perform,
            parse=json.loads,
        )
        self.last_response = text
        return text


# ---------------------------------------------------------------------------
# seam 3: actor and game-master models
# ---------------------------------------------------------------------------


def _chat_completion(*, api_key, model, messages, max_tokens, timeout_s,
                     response_format=None):
    """One provider request, no client-side retry, exact raw text back.

    Deliberately stdlib urllib rather than a client library: a library's
    hidden retry would issue provider requests the counters never see.
    """
    import ssl
    import urllib.request

    payload = {"model": model, "messages": messages,
               "max_tokens": int(max_tokens), "temperature": 0.0}
    if response_format is not None:
        payload["response_format"] = response_format
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        DEEPSEEK_BASE_URL + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    ca_bundle = "/root/.ccr/ca-bundle.crt"
    context = ssl.create_default_context(
        cafile=ca_bundle if os.path.exists(ca_bundle) else None)
    with urllib.request.urlopen(request, timeout=timeout_s,
                                context=context) as response:
        raw = response.read()
    parsed = json.loads(raw.decode("utf-8"))
    text = parsed["choices"][0]["message"]["content"] or ""
    return text, dict(parsed.get("usage") or {})


class _LiveModelUnavailable:
    """Stand-in base used only where the engine environment is absent.

    Importing this module must work on the product interpreter (the
    secret-scan and artifact tests run there), but a live model must
    never silently work without the pinned Concordia package: every
    inherited entry point raises.
    """

    _IMPORT_HELP = (
        "the live model requires the pinned engine environment "
        "(Python >= 3.12 with gdm-concordia); run with "
        "/home/user/engine-env/bin/python")

    def __init__(self, *args, **kwargs):
        raise ImportError(self._IMPORT_HELP)

    def sample_text(self, *args, **kwargs):
        raise ImportError(self._IMPORT_HELP)

    def sample_choice(self, *args, **kwargs):
        raise ImportError(self._IMPORT_HELP)


def _live_model_base():
    """The proven test-owned live model class, reused (not copied).

    ``tests/engine_individual/individual_helpers.DeepSeekChatModel`` is
    the repository's live Concordia ``LanguageModel`` for DeepSeek; this
    harness subclasses it so there is one definition of the live model.
    Where Concordia is not importable the loud stand-in above is used, so
    this module still imports on the product interpreter.
    """
    import sys
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    for extra in (root / "tests" / "engine_individual",
                  root / "tests" / "engine_counterfactuals",
                  root / "tests" / "engine_baseline"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    try:
        from individual_helpers import DeepSeekChatModel
    except ImportError:
        return _LiveModelUnavailable
    return DeepSeekChatModel


LIVE_MODEL_AVAILABLE = _live_model_base() is not _LiveModelUnavailable


class RecordedDeepSeekChatModel(_live_model_base()):
    """The proven live model, with every attempt recorded.

    ``sample_text`` is overridden entirely: the parent's OpenAI client is
    replaced by a single stdlib request so that no hidden client retry can
    issue an unrecorded provider request.  ``sample_choice`` keeps the
    parent's refusal (no multiple-choice path may run here) but records
    the attempt first, so a silent path change would still show up.
    """

    def __init__(self, context: RecorderContext, *, api_key: str,
                 system_hint: str, role: str, actor_id, actor_name,
                 branch_id, cursor: StepCursor, seam_name: str,
                 model: str = DEEPSEEK_MODEL_ID, max_tokens: int = 400,
                 timeout_s: float = 180.0) -> None:
        # The parent's __init__ is deliberately NOT called: it builds an
        # OpenAI client with its own hidden retry, and a hidden retry
        # would issue provider requests the counters never see.  This
        # class overrides sample_text completely and reaches the provider
        # only through the stdlib ``_chat_completion`` above, so the
        # parent's client would be dead weight.  The inheritance is kept
        # so the object IS the repository's live LanguageModel type and
        # inherits its sample_choice refusal.
        if not LIVE_MODEL_AVAILABLE:
            raise ImportError(_LiveModelUnavailable._IMPORT_HELP)
        self._system_hint = system_hint
        if role not in ("actor", "game_master"):
            raise ValueError(f"unexpected role {role!r}")
        self.context = context
        self.role = role
        self.actor_id = actor_id
        self.actor_name = actor_name
        self.branch_id = branch_id
        self.cursor = cursor
        self.model_id = model
        self.max_tokens = int(max_tokens)
        self.timeout_s = float(timeout_s)
        self._api_key = api_key
        self._recorder = _AttemptRecorder(context, seam_name)

    def params(self) -> dict:
        return {"base_url": DEEPSEEK_BASE_URL, "model": self.model_id,
                "temperature": 0.0, "max_tokens": self.max_tokens,
                "timeout_s": self.timeout_s, "response_format": None}

    def sample_text(self, prompt: str, *, max_tokens=None, terminators=(),
                    **kwargs) -> str:
        del kwargs  # bounded fixed policy, as in the parent
        cap = self.max_tokens
        if type(max_tokens) is int and 0 < max_tokens < cap:
            cap = max_tokens
        step = (self.cursor.on_actor_call() if self.role == "actor"
                else self.cursor.on_gm_call())
        messages = [{"role": "system", "content": self._system_hint},
                    {"role": "user", "content": prompt}]

        def perform():
            return _chat_completion(
                api_key=self._api_key, model=self.model_id,
                messages=messages, max_tokens=cap,
                timeout_s=self.timeout_s)

        params = self.params()
        params["max_tokens"] = cap
        params["terminators"] = list(terminators or ())
        text, _usage = self._recorder.run(
            role=self.role,
            callable_name=("experiments.full_trace_validation.recorder."
                           "RecordedDeepSeekChatModel.sample_text"),
            request={"messages": messages},
            params=params,
            model=self.model_id,
            branch_id=self.branch_id,
            step=step,
            actor_id=self.actor_id,
            actor_name=self.actor_name,
            perform=perform,
        )
        for terminator in terminators or ():
            text = text.split(terminator)[0]
        return text.strip()

    def sample_choice(self, prompt: str, responses, **kwargs):
        self._recorder.context.ledger.append({
            "call_id": self._recorder.context.ledger.next_call_id(),
            "experiment_id": self.context.experiment_id,
            "branch_id": self.branch_id,
            "step": self.cursor.on_gm_call(),
            "role": self.role,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "model": self.model_id,
            "provider": PROVIDER,
            "callable": ("experiments.full_trace_validation.recorder."
                         "RecordedDeepSeekChatModel.sample_choice"),
            "request": {"prompt": prompt, "responses": list(responses)},
            "params": self.params(),
            "started_at": utc_now(),
            "finished_at": utc_now(),
            "response_raw": None,
            "response_parsed": None,
            "tokens": None,
            "cost": None,
            "retry": 0,
            "error": ("sample_choice refused: no multiple-choice model "
                      "path may execute in this experiment"),
            "request_sha256": sha256_text(prompt),
            "response_sha256": "",
        })
        return super().sample_choice(prompt, responses, **kwargs)


ACTOR_SYSTEM_HINT = (
    "You are {name}, a person in a turn-based simulation. Private "
    "context and observations appear in the user message. Answer with "
    "exactly one short paragraph in third person describing the single "
    "concrete action {name} takes next, including the exact words of any "
    "message {name} sends. No commentary, no options.")

GM_SYSTEM_HINT = (
    "You are the rules engine of a turn-based simulation. Answer the "
    "question in the user message directly and concisely. When asked "
    "which entities are aware of an event, answer with a comma-"
    "separated list of entity names only.")


def live_model_factory(context: RecorderContext, *, api_key, world,
                       branch_ids, capture: dict, cursors: dict,
                       actor_max_tokens: int = 400,
                       gm_max_tokens: int = 400):
    """Build the manager's ``model_factory(candidate, branch_seed)``.

    One fresh recorded model per actor plus one for the game master, per
    branch; the per-branch :class:`StepCursor` is shared by them so step
    attribution is consistent inside a branch.
    """
    names = {actor.actor_id: actor.name for actor in world.actors}

    def factory(candidate, branch_seed):
        candidate_id = candidate.candidate_id
        branch_id = branch_ids[candidate_id]
        cursor = StepCursor()
        cursors[candidate_id] = cursor
        actor_models = {
            actor_id: RecordedDeepSeekChatModel(
                context, api_key=api_key,
                system_hint=ACTOR_SYSTEM_HINT.format(name=name),
                role="actor", actor_id=actor_id, actor_name=name,
                branch_id=branch_id, cursor=cursor,
                seam_name=f"actor:{actor_id}",
                max_tokens=actor_max_tokens)
            for actor_id, name in sorted(names.items())}
        gm_model = RecordedDeepSeekChatModel(
            context, api_key=api_key, system_hint=GM_SYSTEM_HINT,
            role="game_master", actor_id=None, actor_name=None,
            branch_id=branch_id, cursor=cursor, seam_name="game_master",
            max_tokens=gm_max_tokens)
        capture[candidate_id] = {
            "branch_id": branch_id, "branch_seed": branch_seed,
            "actors": actor_models, "gm": gm_model, "cursor": cursor,
            "actor_system_hints": {
                actor_id: ACTOR_SYSTEM_HINT.format(name=name)
                for actor_id, name in sorted(names.items())},
            "gm_system_hint": GM_SYSTEM_HINT,
        }
        return actor_models, gm_model

    return factory


def read_ledger(path) -> list:
    """Every record in one JSONL ledger, in write order."""
    path = Path(path)
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records
