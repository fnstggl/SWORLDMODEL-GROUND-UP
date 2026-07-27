"""End-to-end pipeline runs with a scripted transport: zero network, fully
deterministic, meaningless labels throughout.  Proves the orchestration --
resolution -> discovery -> per-item translation -> assembly -> validation ->
round trip -> reviews -> bundle -> instantiate -> engine."""
import json

from sworldmodel import Engine, canonical_json

from compiler.legacy import compile_question, instantiate
from compiler.legacy.llm import Caller

from tests.test_compiler_core import neutral_items

ASOF = "2026-07-27"
QUESTION = "Will the typed record for subject_s exist before the deadline?"


class Script:
    """Order-based scripted transport (the pipeline's call order is part of
    its contract)."""

    def __init__(self, responses):
        self.responses = [r if isinstance(r, str) else json.dumps(r)
                          for r in responses]
        self.n = 0

    def __call__(self, system, user):
        if self.n >= len(self.responses):
            raise AssertionError(f"script exhausted after {self.n} calls; "
                                 f"unexpected extra call")
        r = self.responses[self.n]
        self.n += 1
        return r


RESOLUTION = {
    "modelable": True, "refusal_reason": "",
    "observable_outcome": "the typed record for subject_s exists before the "
                          "deadline",
    "reframed": False, "reframing_note": "",
    "answer_mode": "condition",
    "yes_means": "record produced in time",
    "no_means": "no record by the deadline",
    "start_local": "2026-07-27 08:00", "tz": "UTC",
    "cutoff_local": "2026-07-30 12:00", "cutoff_tz": "America/New_York",
    "horizon_provenance": "question_given",
    "horizon_note": "deadline stated by the question",
    "smallest_world": "person_a needs person_b, the only authorized "
                      "producer, to act",
}

SPINE = {"steps": [
    {"needed": "the typed record exists",
     "producible_by": "person_b's possible authorized act"},
    {"needed": "person_b learns it is wanted",
     "producible_by": "person_a's possible outreach on the channel"},
]}


def items(n):
    return {"items": [{"text": f"atomic claim {i}", "provenance": "inferred",
                       "evidence": []} for i in range(n)]}


def one_round(reality_review, meaning_review):
    """The full scripted response sequence for one compile attempt."""
    caps = neutral_items()
    by_cap = {}
    for inst in caps:
        by_cap.setdefault(inst["capability"], []).append(inst)
    buckets = {
        "participants": by_cap["add_participant"],
        "aggregates": by_cap["add_aggregate"],
        "communication": (by_cap["add_channel"] + by_cap["add_channel_access"]
                          + by_cap["add_attention"]),
        "starting_state": (by_cap["add_belief"] + by_cap["add_commitment"]
                           + by_cap["add_resource"]),
        "actions": by_cap["define_action"],
        "external": (by_cap["add_process"] + by_cap["add_operating_window"]
                     + by_cap["schedule_external_event"]),
        "uncertainty": by_cap["declare_uncertainty"],
        "exclusions": by_cap["declare_exclusion"],
    }
    seq = [RESOLUTION, SPINE]
    for cat in ("participants", "aggregates", "communication",
                "starting_state", "actions", "external", "uncertainty",
                "exclusions"):
        seq.append(items(len(buckets[cat])))
    for cat in ("participants", "aggregates", "communication",
                "starting_state", "actions", "external", "uncertainty",
                "exclusions"):
        seq.extend(buckets[cat])
    seq.append(by_cap["set_terminal"][0])
    seq.append(reality_review)
    seq.append(meaning_review)
    return seq


def repair_round(reality_review, meaning_review):
    """A repair round's scripted responses: anchored discovery re-emits the
    same item texts, so every non-terminal translation is REUSED (zero LLM
    calls) -- only resolution, spine, discovery, the terminal, and the
    reviews are consulted."""
    caps = neutral_items()
    by_cap = {}
    for inst in caps:
        by_cap.setdefault(inst["capability"], []).append(inst)
    counts = {"participants": 2, "aggregates": 1, "communication": 5,
              "starting_state": 3, "actions": 1, "external": 3,
              "uncertainty": 1, "exclusions": 1}
    seq = [RESOLUTION, SPINE]
    for cat in ("participants", "aggregates", "communication",
                "starting_state", "actions", "external", "uncertainty",
                "exclusions"):
        seq.append(items(counts[cat]))
    seq.append(by_cap["set_terminal"][0])
    seq.extend([reality_review, meaning_review])
    return seq


APPROVE = {"verdict": "approve", "objections": [], "dispositions": []}
REVISE = {"verdict": "revise",
          "objections": [{"severity": "blocking", "about": "attention",
                          "objection": "the checking cadence is unrealistic",
                          "fix_hint": "loosen it"}],
          "dispositions": []}


def compile_scripted(script, **kw):
    caller = Caller(transport=script)
    return compile_question(QUESTION, asof=ASOF, caller=caller, **kw)


def test_full_compile_with_scripted_llm(tmp_path):
    script = Script(one_round(APPROVE, APPROVE))
    result = compile_scripted(script, out_dir=str(tmp_path / "out"))
    assert result.status == "compiled", result.report
    b = result.bundle
    assert script.n == len(script.responses)      # every call accounted for
    assert b["coverage"]["unsupported"] == []
    assert b["repair_rounds"] == []
    assert b["plan"]["terminal_spec"]["mode"] == "condition"
    assert (tmp_path / "out" / "bundle.json").exists()
    assert (tmp_path / "out" / "trace.jsonl").exists()
    assert (tmp_path / "out" / "genesis_ledger.jsonl").exists()

    # instantiate: zero LLM calls, byte-identical world, runnable engine
    world, minds, terminal = instantiate(b)
    assert world.state_hash() == b["state_hash"]
    assert canonical_json(world.records) == canonical_json(b["world_records"])
    assert set(minds) == {"person_a", "person_b"}
    out = Engine(world, {}, terminal).run(stop_after_events=6)
    assert out.metrics["events_processed"] > 0


def test_review_objection_triggers_one_repair_round():
    script = Script(one_round(REVISE, APPROVE) + repair_round(APPROVE, APPROVE))
    result = compile_scripted(script)
    assert result.status == "compiled"
    assert len(result.bundle["repair_rounds"]) == 1
    assert "unrealistic" in result.bundle["repair_rounds"][0][0]
    assert script.n == len(script.responses)
    reused = [t for t in result.bundle["translations"] if t.get("reused")]
    assert len(reused) >= 10          # the unchanged world came from cache


def test_second_rejection_fails_with_reasons():
    script = Script(one_round(REVISE, APPROVE) + repair_round(REVISE, APPROVE))
    result = compile_scripted(script, max_repair_rounds=1)
    assert result.status == "failed"
    assert any("unrealistic" in r for r in result.report["reasons"])


def test_unmodelable_question_is_refused_only_after_a_challenge():
    """A refusal must survive one challenge round: decision-dependent and
    'likely to' questions are modelable by doctrine, so only a repeated
    refusal is final."""
    refusal = {"modelable": False,
               "refusal_reason": "no observable resolution exists"}
    script = Script([refusal, refusal])
    result = compile_scripted(script)
    assert result.status == "refused"
    assert "no observable resolution" in result.report["reasons"][0]
    assert script.n == 2


def test_refusal_withdrawn_after_challenge_compiles():
    refusal = {"modelable": False,
               "refusal_reason": "depends on someone's future decision"}
    script = Script([refusal] + one_round(APPROVE, APPROVE))
    result = compile_scripted(script)
    assert result.status == "compiled", result.report
    assert len(result.bundle["repair_rounds"]) == 1


def test_unparseable_stage_fails_structurally_never_raises():
    script = Script(["this is not json"] * 3)     # repairs exhausted
    result = compile_scripted(script)
    assert result.status == "failed"
    assert any("resolution" in r for r in result.report["reasons"])


def test_translator_garbage_becomes_unsupported_not_crash():
    """A translator that answers nonsense for one item: the item must end
    as a recorded UNSUPPORTED (and here, dropping an attention item is
    survivable -- reviews still approve)."""
    seq = one_round(APPROVE, APPROVE)
    # the first attention item (communication[3]) is survivable: its actor
    # still has a commitment wake, so no new review finding appears.
    # order: resolution, spine, 8 discovery, then translations
    idx = 2 + 8 + 2 + 1 + 3       # participants(2)+aggregates(1)+comm[3]
    bad = {"capability": "add_attention",
           "fields": {"participant": "Person Nobody", "channel": "channel_c",
                      "mode": "periodic", "tz": "UTC", "open_time": "08:00",
                      "close_time": "18:00", "check_every_minutes": 60,
                      "provenance": "inferred", "note": "x"}}
    # both the first try and the corrective retry reference an unknown name;
    # the unknown-name failure earns one deferred retry after the sweep,
    # which here gives up explicitly
    give_up = {"capability": "UNSUPPORTED", "reason": "still cannot resolve"}
    seq = seq[:idx] + [bad, bad] + seq[idx + 1:]
    terminal_pos = len(seq) - 3         # ... terminal, reality, meaning
    seq = seq[:terminal_pos] + [give_up] + seq[terminal_pos:]
    script = Script(seq)
    result = compile_scripted(script)
    assert result.status == "compiled", result.report
    unsupported = result.bundle["coverage"]["unsupported"]
    assert unsupported == ["communication[3]"]
    trans = [t for t in result.bundle["translations"]
             if t["item_ref"] == "communication[3]"][0]
    assert "could not be resolved" in trans["result"]["reason"]


def test_missing_channel_is_auto_patched_then_items_land():
    """When no channel was declared, every route/attention item strands on
    an unknown-name error; the sweep declares the channel via one targeted
    patch and the deferred pass then lands the stranded items."""
    caps = neutral_items()
    channel = [c for c in caps if c["capability"] == "add_channel"][0]
    by_cap = {}
    for inst in caps:
        by_cap.setdefault(inst["capability"], []).append(inst)
    comm = by_cap["add_channel_access"] + by_cap["add_attention"]  # no channel!
    buckets = {
        "participants": by_cap["add_participant"],
        "aggregates": by_cap["add_aggregate"],
        "communication": comm,
        "starting_state": (by_cap["add_belief"] + by_cap["add_commitment"]
                           + by_cap["add_resource"]),
        "actions": by_cap["define_action"],
        "external": (by_cap["add_process"] + by_cap["add_operating_window"]
                     + by_cap["schedule_external_event"]),
        "uncertainty": by_cap["declare_uncertainty"],
        "exclusions": by_cap["declare_exclusion"],
    }
    order = ("participants", "aggregates", "communication", "starting_state",
             "actions", "external", "uncertainty", "exclusions")

    def references_channel(inst):
        return "channel_c" in json.dumps(inst)

    seq = [RESOLUTION, SPINE]
    for cat in order:
        seq.append(items(len(buckets[cat])))
    stranded = []
    for cat in order:
        for inst in buckets[cat]:
            if references_channel(inst):
                seq.extend([inst, inst])   # fails + corrective retry fails
                stranded.append(inst)
            else:
                seq.append(inst)
    seq.append(channel)                    # the missing-channel patch call
    seq.extend(stranded)                   # deferred pass: all land now
    seq.append(by_cap["set_terminal"][0])
    seq.extend([APPROVE, APPROVE])
    script = Script(seq)
    result = compile_scripted(script)
    assert result.status == "compiled", result.report
    assert script.n == len(script.responses)
    refs = {t["item_ref"]: t["status"] for t in result.bundle["translations"]}
    assert refs["communication[200]"] == "lowered"       # the patched channel
    assert all(refs[f"communication[{i}]"] == "lowered" for i in range(4))
    assert refs["actions[0]"] == "lowered"


def test_validation_finding_gets_a_targeted_patch():
    """A missing answer-critical attention pattern is repaired by ONE
    surgical translation call, not a full re-description."""
    caps = neutral_items()
    # drop person_a's attention; point the terminal at their noticing
    caps = [c for c in caps
            if not (c["capability"] == "add_attention"
                    and c["fields"]["participant"] == "Person A")
            and c["capability"] != "set_terminal"]
    terminal = {"capability": "set_terminal", "fields": {
        "question_restated": "does person_a notice the outcome notice?",
        "mode": "condition", "cutoff_local": "2026-07-30 12:00",
        "tz": "America/New_York",
        "condition": {"check": "information_noticed",
                      "participant": "Person A",
                      "info_type": "outcome_notice"},
        "yes_means": "y", "no_means": "n"}}
    patch = {"capability": "add_attention", "fields": {
        "participant": "Person A", "channel": "channel_c",
        "mode": "periodic", "tz": "America/New_York",
        "open_time": "09:00", "close_time": "17:00",
        "check_every_minutes": 30, "provenance": "inferred",
        "note": "restored by patch"}}
    by_cap = {}
    for inst in caps:
        by_cap.setdefault(inst["capability"], []).append(inst)
    buckets = {
        "participants": by_cap["add_participant"],
        "aggregates": by_cap["add_aggregate"],
        "communication": (by_cap["add_channel"] + by_cap["add_channel_access"]
                          + by_cap["add_attention"]),
        "starting_state": (by_cap["add_belief"] + by_cap["add_commitment"]
                           + by_cap["add_resource"]),
        "actions": by_cap["define_action"],
        "external": (by_cap["add_process"] + by_cap["add_operating_window"]
                     + by_cap["schedule_external_event"]),
        "uncertainty": by_cap["declare_uncertainty"],
        "exclusions": by_cap["declare_exclusion"],
    }
    seq = [RESOLUTION, SPINE]
    order = ("participants", "aggregates", "communication", "starting_state",
             "actions", "external", "uncertainty", "exclusions")
    for cat in order:
        seq.append(items(len(buckets[cat])))
    for cat in order:
        seq.extend(buckets[cat])
    seq.extend([terminal, patch, APPROVE, APPROVE])
    script = Script(seq)
    result = compile_scripted(script)
    assert result.status == "compiled", result.report
    assert script.n == len(script.responses)
    patched = [t for t in result.bundle["translations"]
               if t["item_ref"] == "communication[100]"]
    assert patched and patched[0]["status"] == "lowered"
    assert result.bundle["validation"]["blocking"] == []
