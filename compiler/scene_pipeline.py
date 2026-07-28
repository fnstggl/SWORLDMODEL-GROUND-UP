"""minimal_scene_v1 -- the canonical production compile path.

question + start + cutoff + optional context/evidence
  -> LLM CALL 1: minimal four-field scene manifest
  -> LLM CALL 2: independent adversarial scene review
  -> optional LLM CALL 3: one targeted correction (recorded as repaired)
  -> deterministic validation and ID assignment
  -> direct runtime instantiation (existing persistent runtime)

Two semantic calls normally, three maximum (enforced in code before the
call is made), zero translation calls, zero per-object calls, zero repair
loops.  Every outcome is structured: compiled | corrected | abstained |
failed(reason) -- never a crash, never a silent false default.

MODEL-MEMORY MODE (the default, no evidence package) TESTS COMPILER
ROBUSTNESS AND SEMANTIC WORLD SHAPE.  IT DOES NOT VERIFY CURRENT
REAL-WORLD FACTS: nothing it produces is labeled verified and no factual-
accuracy claim may be made from it."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from sworldmodel import canonical_json

from . import scene_prompts
from .scene_adapter import instantiate_scene
from .scene_llm import (CompilerCallBudgetExceeded, SceneCaller,
                        TechnicalFailure)
from .scene_resolution import NLResolution, build_nl_terminal
from .scene_schema import validate_manifest_shape, validate_review_shape
from .scene_validate import validate_scene

COMPILER_VERSION = "minimal_scene_v1"


@dataclass
class SceneCompileResult:
    status: str          # compiled | corrected | abstained | failed
    question: str
    reason: str = ""
    manifest: dict | None = None
    review: dict | None = None
    bindings: dict | None = None
    metrics: dict = field(default_factory=dict)
    out_dir: str | None = None

    def summary(self) -> str:
        m = self.metrics
        lines = [f"[{self.status}] {self.question}"]
        if self.reason:
            lines.append(f"  reason: {self.reason[:300]}")
        if self.manifest:
            lines.append(f"  actors: "
                         f"{[a['name'] for a in self.manifest['actors']]}")
            lines.append(f"  events: {len(self.manifest['starting_events'])}"
                         f" | resolution: {self.manifest['resolution'][:110]}")
        lines.append(f"  semantic calls: {m.get('semantic_calls')} | "
                     f"provider requests: {m.get('provider_requests')} | "
                     f"wall: {m.get('wall_s')}s | "
                     f"compiler: {COMPILER_VERSION}")
        if self.out_dir:
            lines.append(f"  artifacts -> {self.out_dir}")
        return "\n".join(lines)


def compile_scene(question: str, start: str, cutoff: str,
                  context: str | None = None, evidence: str | None = None,
                  caller: SceneCaller | None = None,
                  out_dir: str | None = None) -> SceneCompileResult:
    """The public entry point.  Never raises."""
    caller = caller or SceneCaller()
    t0 = time.monotonic()
    art: dict = {}                       # filename -> content to persist

    def finish(status, reason="", manifest=None, review=None, bindings=None,
               extra_metrics=None):
        metrics = dict(caller.metrics())
        metrics["wall_s"] = round(time.monotonic() - t0, 2)
        metrics["compiler_version"] = COMPILER_VERSION
        metrics["evidence_mode"] = ("evidence_package" if evidence
                                    else "model_memory_unverified")
        metrics.update(extra_metrics or {})
        art["compiler_metrics.json"] = json.dumps(metrics, indent=1)
        result = SceneCompileResult(status, question, reason, manifest,
                                    review, bindings, metrics)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            for fname, content in art.items():
                with open(os.path.join(out_dir, fname), "w",
                          encoding="utf-8") as f:
                    f.write(content)
            result.out_dir = out_dir
        return result

    art["input.json"] = json.dumps(
        {"question": question, "start": start, "cutoff": cutoff,
         "context": context, "evidence": evidence,
         "compiler_version": COMPILER_VERSION}, indent=1)
    try:
        # ---- CALL 1: scene construction -------------------------------
        u1 = scene_prompts.call1_user(question, start, cutoff, context,
                                      evidence)
        art["call_1_prompt.txt"] = scene_prompts.CALL1_SYSTEM + "\n\n" + u1
        r1 = caller.semantic_call("call_1_scene", scene_prompts.CALL1_SYSTEM,
                                  u1)
        art["call_1_raw_response.txt"] = r1["raw"]
        manifest = r1["parsed"]
        if isinstance(manifest, dict) and manifest.get("actors") == []:
            # an empty cast is an honest refusal to invent a scene, however
            # the model labeled it -- a structured abstention, not a schema
            # failure and never a false default
            return finish("abstained",
                          "compiler produced an empty cast: not simulatable "
                          "as a social scene ("
                          + str(manifest.get("resolution", ""))[:300] + ")")
        shape_errors = validate_manifest_shape(manifest)
        if shape_errors:
            return finish("failed", "SCHEMA_INVALID: " + "; ".join(
                shape_errors[:6]))
        art["scene_manifest.json"] = json.dumps(manifest, indent=1)
        if str(manifest.get("resolution", "")).strip().upper() \
                .startswith("UNRESOLVABLE"):
            return finish("abstained",
                          f"compiler: {manifest['resolution'][:400]}",
                          manifest=manifest)

        # ---- CALL 2: independent adversarial review -------------------
        mj = json.dumps(manifest, indent=1)
        u2 = scene_prompts.call2_user(question, start, cutoff, context,
                                      evidence, mj)
        art["call_2_prompt.txt"] = scene_prompts.CALL2_SYSTEM + "\n\n" + u2
        r2 = caller.semantic_call("call_2_review", scene_prompts.CALL2_SYSTEM,
                                  u2)
        art["call_2_raw_response.txt"] = r2["raw"]
        review = r2["parsed"]
        rev_errors = validate_review_shape(review)
        if rev_errors:
            return finish("failed", "REVIEW_SCHEMA_INVALID: " + "; ".join(
                rev_errors[:6]), manifest=manifest)
        art["scene_review.json"] = json.dumps(review, indent=1)
        repaired = False
        if review["verdict"] == "ABSTAIN":
            reason = "; ".join(f"{d['path']}: {d['problem']}"
                               for d in review["defects"][:4]) \
                or "reviewer abstained"
            return finish("abstained", reason, manifest=manifest,
                          review=review)
        if review["verdict"] == "REVISE":
            # ---- CALL 3: one targeted correction ----------------------
            dj = json.dumps(review["defects"], indent=1)
            u3 = scene_prompts.call3_user(question, start, cutoff, context,
                                          evidence, mj, dj)
            art["call_3_prompt.txt"] = scene_prompts.CALL3_SYSTEM + "\n\n" + u3
            r3 = caller.semantic_call("call_3_correction",
                                      scene_prompts.CALL3_SYSTEM, u3)
            art["call_3_raw_response.txt"] = r3["raw"]
            corrected = r3["parsed"]
            shape_errors = validate_manifest_shape(corrected)
            if shape_errors:
                return finish("failed", "CORRECTION_SCHEMA_INVALID: "
                              + "; ".join(shape_errors[:6]),
                              manifest=manifest, review=review)
            manifest = corrected
            repaired = True
            art["corrected_scene_manifest.json"] = json.dumps(manifest,
                                                              indent=1)
            # deterministic validation follows; the reviewer is NOT recalled

        # ---- deterministic validation + normalization -----------------
        scene, norm_report, errors, warnings = validate_scene(manifest,
                                                              start, cutoff)
        art["final_scene_manifest.json"] = json.dumps(scene, indent=1)
        art["normalization_report.json"] = json.dumps(norm_report, indent=1)
        art["validation_report.json"] = json.dumps(
            {"errors": errors, "warnings": warnings}, indent=1)
        if errors:
            if any("unresolvable" in e for e in errors):
                return finish("abstained", "; ".join(errors[:4]),
                              manifest=manifest, review=review)
            return finish("failed", "VALIDATION_FAILED: "
                          + "; ".join(errors[:6]), manifest=manifest,
                          review=review)

        # ---- direct runtime instantiation -----------------------------
        world, bindings = instantiate_scene(scene, question, start, cutoff)
        world2, _ = instantiate_scene(scene, question, start, cutoff)
        if world.state_hash() != world2.state_hash():
            return finish("failed", "INSTANTIATION_NOT_DETERMINISTIC",
                          manifest=manifest, review=review)
        res = NLResolution(question, scene["resolution"], cutoff,
                           bindings["world_id"])
        terminal = build_nl_terminal(res)
        genesis = terminal.evaluate(world, False)
        art["genesis_resolution_check.json"] = json.dumps(
            {"resolution": res.to_dict(), "value_at_genesis": genesis,
             "false_at_genesis": genesis is None}, indent=1)
        if genesis is not None:
            return finish("failed", "TERMINAL_TRUE_AT_GENESIS",
                          manifest=manifest, review=review)
        # serialization / reload / replay of the initialized state
        replayed = world.__class__.from_records(
            json.loads(canonical_json(world.records)))
        if replayed.state_hash() != world.state_hash():
            return finish("failed", "REPLAY_MISMATCH", manifest=manifest,
                          review=review)
        art["runtime_bindings.json"] = json.dumps(
            dict(bindings, resolution=res.to_dict()), indent=1)
        art["initialized_world_snapshot.json"] = json.dumps(world.snapshot(),
                                                            indent=1)
        art["starting_event_ledger.jsonl"] = "\n".join(
            canonical_json(r) for r in world.records)
        art["actor_initial_views.json"] = json.dumps(
            {aid: st.to_dict() for aid, st in sorted(world.actors.items())},
            indent=1)
        return finish("corrected" if repaired else "compiled",
                      manifest=scene, review=review, bindings=bindings,
                      extra_metrics={"repaired_compile": repaired,
                                     "world_id": bindings["world_id"]})
    except CompilerCallBudgetExceeded as e:
        return finish("failed", f"COMPILER_CALL_BUDGET_EXCEEDED: {e}")
    except TechnicalFailure as e:
        return finish("failed", f"TECHNICAL_FAILURE: {e}")
    except Exception as e:                # the compiler must never crash
        import traceback
        art["internal_error.txt"] = traceback.format_exc()
        return finish("failed", f"INTERNAL_ERROR: {type(e).__name__}: {e}")


def instantiate_compiled(out_dir: str):
    """Rebuild (World, Terminal, bindings) from a compiled case's stored
    artifacts, with zero LLM calls."""
    with open(os.path.join(out_dir, "final_scene_manifest.json")) as f:
        scene = json.load(f)
    with open(os.path.join(out_dir, "input.json")) as f:
        inp = json.load(f)
    world, bindings = instantiate_scene(scene, inp["question"], inp["start"],
                                        inp["cutoff"])
    res = NLResolution(inp["question"], scene["resolution"], inp["cutoff"],
                       bindings["world_id"])
    return world, build_nl_terminal(res), bindings
