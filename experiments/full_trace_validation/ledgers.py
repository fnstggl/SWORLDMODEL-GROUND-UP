"""Per-branch step ledgers reconstructed from what the engine really
exposed.

Experiment-only.  Nothing here is inferred: every field is either lifted
from a recorded live call, from the upstream engine's own per-step raw
log, from the frozen plan, or from the branch result.  A field the
current engine genuinely does not expose is written as
``{"unavailable": "<precise reason>"}`` -- never guessed, never dropped
silently.  Every such marker is collected by :func:`collect_unavailable`
and reported in the UNDER_THE_HOOD report's limitations section.

CONTAINMENT
-----------
``step_ledger.jsonl`` is an AUDITOR-ONLY artifact.  It deliberately holds
every actor's private context and every prompt side by side, which no
actor ever saw.  The report sections that represent an actor's prompt are
built from :func:`actor_prompt_record`, which returns ONLY that actor's
own prompt.  The two must never be mixed.

Sources, per step ``k`` (upstream ``sequential.Sequential.run_loop``
writes exactly one raw-log entry per completed step):

======================================  ====================================
step-ledger field                        source
======================================  ====================================
``active_actor``                         raw log ``Entity [<name>]`` key
``actor_private_context``                raw log ``private_setup.Value``
``shared_context``                       raw log ``shared_setup.Value``
``observations_delivered``               ``make_observation.<name>``
``memory_retrieved``                     ``recent_observations.Value``
``action_spec``                          ``next_action_spec.__act__.Value``
``actor_model_request``                  recorded call (this harness)
``actor_raw_response``                   recorded call + ``__act__.Value``
``attempted_action``                     ``resolve.__act__.Summary``
``game_master_input``                    ``resolve.__resolution__.Prompt``
``game_master_raw_response``             recorded call + ``resolve`` value
``candidate_event_before_guard``         guard record, else passthrough
``guard``                                runner ``guard_interventions``
``final_committed_event``                ``committed_events[k]``
``recipients``                           ``Details['Observers prompt']``
``termination_check``                    ``terminate.__act__.Value``
======================================  ====================================
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ENTITY_KEY_RE = re.compile(r"^Entity \[(?P<name>.+)\]$")

#: the upstream observers question, whose recorded answer names the
#: entities that received the resolved event
OBSERVERS_ANSWER_RE = re.compile(
    r"Which entities are aware of the event\?[^\n]*\nAnswer:\s*"
    r"(?P<answer>[^\n]*)")

AUDITOR_ONLY_BANNER = {
    "_artifact_class": "AUDITOR_ONLY",
    "_warning": ("this file deliberately contains every actor's private "
                 "context and every prompt side by side; no actor ever "
                 "saw this view. Never present it as an actor's prompt."),
}


def unavailable(reason: str) -> dict:
    return {"unavailable": reason}


def _sha(value) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _entity_key(entry: dict):
    for key in entry:
        match = ENTITY_KEY_RE.match(str(key))
        if match:
            return key, match.group("name")
    return None, None


def _gm_key(entry: dict):
    for key in entry:
        if key in ("Step", "Summary"):
            continue
        if ENTITY_KEY_RE.match(str(key)):
            continue
        return key
    return None


def _dig(mapping, *path, default=None):
    node = mapping
    for name in path:
        if not isinstance(node, dict) or name not in node:
            return default
        node = node[name]
    return node


def _observers_from_resolve(resolve: dict):
    prompt = _dig(resolve, "__resolution__", "Details", "Observers prompt",
                  default="")
    if not isinstance(prompt, str) or not prompt.strip():
        return unavailable(
            "the game master's resolution log recorded no observers "
            "prompt for this step")
    match = OBSERVERS_ANSWER_RE.search(prompt)
    if not match:
        return unavailable(
            "the observers prompt was recorded but carries no parsable "
            "'Answer:' line; raw prompt preserved in "
            "game_master_observers_prompt")
    answer = match.group("answer").strip()
    names = [part.strip() for part in answer.split(",") if part.strip()]
    return {"answer_text": answer, "names": names}


def _calls_for_step(calls, step):
    return [call for call in calls if call.get("step") == step]


def build_step_ledger(*, branch_id, candidate_id, plan, runner_record,
                      calls, committed_events, world_start, world_cutoff):
    """One list of step records for one branch (see module docstring)."""
    raw_log = list(runner_record.get("raw_log") or [])
    guard_records = list(runner_record.get("guard_interventions") or [])
    guard_by_step: dict = {}
    for record in guard_records:
        guard_by_step.setdefault(record["step"], []).append(record)

    plan_private = {config.actor_id: config.private_init_data
                    for config in plan.actor_configs}
    name_to_id = {config.name: config.actor_id
                  for config in plan.actor_configs}

    ledger: list = []
    committed_cursor = 0
    for index, entry in enumerate(raw_log):
        step = entry.get("Step", index + 1)
        entity_key, actor_name = _entity_key(entry)
        gm_key = _gm_key(entry)
        entity_log = entry.get(entity_key, {}) if entity_key else {}
        gm_log = entry.get(gm_key, {}) if gm_key else {}
        resolve = gm_log.get("resolve", {})

        step_calls = _calls_for_step(calls, step)
        actor_calls = [call for call in step_calls
                       if call["role"] == "actor"]
        gm_calls = [call for call in step_calls
                    if call["role"] == "game_master"]

        observations = {}
        for name, payload in (gm_log.get("make_observation") or {}).items():
            observations[name] = {
                "delivered_text": _dig(payload, "__make_observation__",
                                       "Value", default=""),
                "queue_for_active_entity": _dig(
                    payload, "__make_observation__",
                    "queue_active_entity", default=[]),
                "remaining_queue": _dig(payload, "__make_observation__",
                                        "queue", default={}),
            }

        guard_here = guard_by_step.get(step, [])
        if guard_here:
            before = {
                "excerpt": guard_here[0]["original_excerpt"],
                "truncated_to_chars": len(guard_here[0]["original_excerpt"]),
                "note": ("the runner records guard excerpts capped at 120 "
                         "characters; the untruncated pre-guard text is "
                         "not exposed by the current engine"),
            }
            guard_result = {
                "intervened": True,
                "records": guard_here,
                "explanation": (
                    "the minimum agency guard detected event text asserting "
                    "another actor's voluntary decision and rewrote it into "
                    "attempt-plus-availability form; affected actors: "
                    + ", ".join(sorted(
                        {name for record in guard_here
                         for name in record["affected"]}))),
            }
        else:
            before = {
                "equals_final_committed_event": True,
                "note": ("the guard did not fire on this step; the "
                         "minimum agency guard is a byte-identical "
                         "passthrough when it does not rewrite, so the "
                         "pre-guard candidate event IS the final "
                         "committed event recorded below"),
            }
            guard_result = {
                "intervened": False,
                "records": [],
                "explanation": ("no intervention: the guard passed the "
                                "candidate event through unchanged"),
            }

        final_event = None
        if committed_cursor < len(committed_events):
            resolved_value = _dig(resolve, "__resolution__", "Value",
                                  default="")
            for offset in range(committed_cursor, len(committed_events)):
                if not resolved_value or resolved_value.strip() and \
                        resolved_value.strip()[:60] in \
                        committed_events[offset]:
                    final_event = {"index": offset,
                                   "text": committed_events[offset]}
                    committed_cursor = offset + 1
                    break
            if final_event is None:
                final_event = {"index": committed_cursor,
                               "text": committed_events[committed_cursor]}
                committed_cursor += 1

        record = {
            "branch_id": branch_id,
            "candidate_id": candidate_id,
            "step": step,
            "simulation_time": unavailable(
                "the pinned upstream sequential engine has no simulation "
                "clock: steps are ordinal, not timed. The window "
                f"[{world_start}, {world_cutoff}] is carried in the plan "
                "and in event framing text only."),
            "active_actor": {
                "name": actor_name,
                "actor_id": name_to_id.get(actor_name),
            } if actor_name else unavailable(
                "this raw-log entry carries no entity key (the step took "
                "no actor turn)"),
            "actor_private_context": {
                "from_plan": plan_private.get(name_to_id.get(actor_name)),
                "as_rendered_in_prompt": _dig(entity_log, "private_setup",
                                              "Value"),
            },
            "shared_context": _dig(gm_log, "resolve", "shared_setup",
                                   "Value"),
            "observations_delivered": observations,
            "memory_retrieved": {
                "key": _dig(entity_log, "recent_observations", "Key"),
                "value": _dig(entity_log, "recent_observations", "Value"),
                "note": ("the pinned actor roster exposes its ordered "
                         "observation buffer; there is no separate "
                         "retrieval-scored memory component in this plan"),
            },
            "action_spec": {
                "requested_format": _dig(gm_log, "next_action_spec",
                                         "__act__", "Value"),
                "call_to_action": _dig(gm_log, "next_action_spec",
                                       "__act__", "Action Spec"),
                "next_acting_decision": _dig(gm_log, "next_acting",
                                             "__act__", "Value"),
            },
            "actor_model_request": (
                [{"call_id": call["call_id"], "messages":
                  call["request"]["messages"],
                  "params": call["params"], "retry": call["retry"],
                  "error": call["error"]}
                 for call in actor_calls]
                or unavailable(
                    "no actor model call was recorded at this step; the "
                    "actor's committed action came from the engine "
                    "without a provider request")),
            "actor_prompt_as_engine_assembled": _dig(
                entity_log, "__act__", "Prompt"),
            "actor_raw_response": {
                "recorded_calls": [
                    {"call_id": call["call_id"],
                     "response_raw": call["response_raw"],
                     "response_sha256": call["response_sha256"]}
                    for call in actor_calls],
                "engine_recorded_value": _dig(entity_log, "__act__",
                                              "Value"),
            },
            "attempted_action": _dig(resolve, "__act__", "Summary"),
            "game_master_input": {
                "resolution_prompt": _dig(resolve, "__resolution__",
                                          "Prompt"),
                "act_prompt": _dig(resolve, "__act__", "Prompt"),
                "observers_prompt": _dig(resolve, "__resolution__",
                                         "Details", "Observers prompt"),
            },
            "game_master_raw_response": {
                "recorded_calls": [
                    {"call_id": call["call_id"],
                     "request_messages": call["request"].get("messages"),
                     "response_raw": call["response_raw"],
                     "retry": call["retry"], "error": call["error"]}
                    for call in gm_calls],
                "engine_recorded_value": _dig(resolve, "__resolution__",
                                              "Value"),
            },
            "candidate_event_before_guard": before,
            "guard": guard_result,
            "final_committed_event": final_event or unavailable(
                "no committed event corresponds to this step (the step "
                "produced no engine-stamped [event] row)"),
            "recipients": _observers_from_resolve(resolve),
            "observations_created": {
                "note": ("the engine queues the resolved event for the "
                         "entities named in 'recipients'; the text each "
                         "one is handed appears in the NEXT step's "
                         "observations_delivered"),
                "queued_event_text": _dig(resolve, "__resolution__",
                                          "Value"),
            },
            "state_hash_after_step": {
                "committed_stream_prefix_sha256": _sha(
                    committed_events[:committed_cursor]),
                "committed_rows_so_far": committed_cursor,
                "full_engine_state_hash": unavailable(
                    "the engine exposes a whole-branch checkpoint only at "
                    "a requested end-of-step boundary "
                    "(runner.run_branch(checkpoint_after=k)); capturing "
                    "one every step would change what is being measured, "
                    "so this run records the committed-stream prefix hash "
                    "instead"),
            },
            "termination_check": {
                "question": _dig(gm_log, "terminate", "__act__",
                                 "Action Spec"),
                "answer": _dig(gm_log, "terminate", "__act__", "Value"),
            },
        }
        ledger.append(record)
    return ledger


def actor_prompt_record(step_record: dict, actor_name: str):
    """ONLY what the named actor's own prompt contained (containment
    discipline: never mix in another actor's context)."""
    active = step_record.get("active_actor")
    if not isinstance(active, dict) or active.get("name") != actor_name:
        return None
    messages = []
    request = step_record.get("actor_model_request")
    if isinstance(request, list):
        for call in request:
            messages.extend(call.get("messages") or [])
    return {
        "step": step_record["step"],
        "actor": actor_name,
        "prompt_messages_sent_to_the_model": messages,
        "engine_assembled_prompt": step_record.get(
            "actor_prompt_as_engine_assembled"),
        "response": step_record.get("actor_raw_response", {}).get(
            "engine_recorded_value"),
    }


def collect_unavailable(ledger) -> list:
    """Every ``unavailable`` marker in a step ledger, with its path."""
    found: list = []

    def walk(node, path):
        if isinstance(node, dict):
            if set(node) == {"unavailable"}:
                found.append({"path": path, "reason": node["unavailable"]})
                return
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    for record in ledger:
        walk(record, f"step_{record.get('step')}")
    return found


def write_jsonl(rows, path, *, banner=None) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        if banner is not None:
            handle.write(json.dumps(banner, ensure_ascii=False) + "\n")
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return _sha(path.read_text(encoding="utf-8"))


def observation_rows(ledger) -> list:
    """Flat observation stream: who was handed what, at which step."""
    rows = []
    for record in ledger:
        delivered = record.get("observations_delivered") or {}
        for name, payload in sorted(delivered.items()):
            rows.append({
                "branch_id": record["branch_id"],
                "step": record["step"],
                "recipient": name,
                "delivered_text": payload.get("delivered_text"),
                "queue_for_active_entity": payload.get(
                    "queue_for_active_entity"),
            })
    return rows


def guard_rows(ledger) -> list:
    rows = []
    for record in ledger:
        guard = record.get("guard") or {}
        rows.append({
            "branch_id": record["branch_id"],
            "step": record["step"],
            "intervened": guard.get("intervened"),
            "explanation": guard.get("explanation"),
            "records": guard.get("records"),
            "candidate_event_before_guard": record.get(
                "candidate_event_before_guard"),
            "final_committed_event": record.get("final_committed_event"),
        })
    return rows


def committed_event_rows(branch_id, committed_events) -> list:
    return [{"branch_id": branch_id, "index": index,
             "event_id": f"ev_{index:04d}", "text": text,
             "sha256": _sha(text)}
            for index, text in enumerate(committed_events)]
