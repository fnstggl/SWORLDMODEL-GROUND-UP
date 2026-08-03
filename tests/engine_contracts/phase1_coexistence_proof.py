"""Phase 1 proof: pinned upstreams coexist and minimally run in one process.

Run with the engine environment's Python (>=3.12):

    AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=http://localhost:9 \
        /home/user/engine-env/bin/python tests/engine_contracts/phase1_coexistence_proof.py

Deliberately NOT named test_*.py: the system-python (3.11) product suite must
not collect it (Concordia requires >=3.12). The engine-contract pytest suite
(Phase 2) lives beside it with its own import guards.

Exit code 0 == every proof passed. No network, no credentials, no Ray.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "dummy")
os.environ.setdefault("AGENTSOCIETY_LLM_API_BASE", "http://localhost:9")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

checks: list[str] = []


def ok(label: str) -> None:
    checks.append(label)
    print(f"  ok - {label}")


def main() -> int:
    # 1. Triple import coexistence in one interpreter.
    import concordia  # noqa: F401
    import agentsociety2  # noqa: F401
    import sworldmodel  # noqa: F401
    ok("imports coexist: concordia + agentsociety2 + sworldmodel")

    # 2. Minimal Concordia: real EntityAgent with real components acts offline.
    import numpy as np
    from concordia.agents import entity_agent_with_logging
    from concordia.associative_memory import basic_associative_memory
    from concordia.components import agent as agent_components
    from concordia.language_model import no_language_model
    from concordia.typing import entity as entity_lib

    model = no_language_model.NoLanguageModel()
    bank = basic_associative_memory.AssociativeMemoryBank(
        sentence_embedder=lambda _: np.ones(3)
    )
    agent = entity_agent_with_logging.EntityAgentWithLogging(
        agent_name="Alex",
        act_component=agent_components.concat_act_component.ConcatActComponent(
            model=model, randomize_choices=False
        ),
        context_components={
            "__memory__": agent_components.memory.AssociativeMemory(memory_bank=bank),
            "observation_to_memory": agent_components.observation.ObservationToMemory(),
            "recent": agent_components.observation.LastNObservations(history_length=10),
        },
    )
    agent.observe("Alex received a short email from Morgan.")
    action = agent.act(entity_lib.free_action_spec(call_to_action="What does {name} do?"))
    assert isinstance(action, str)
    state = agent.get_state()
    agent.set_state(state)
    memories = bank.get_all_memories_as_text()
    assert any("Morgan" in m for m in memories), memories
    ok("concordia EntityAgent observe/act/get_state/set_state with real memory bank")

    # 3. Minimal AgentSociety: workspace create + AGENT.json round-trip (no Ray).
    from agentsociety2.agent.base.agent import AgentBase

    with tempfile.TemporaryDirectory() as tmp:
        ws = os.path.join(tmp, "agent_0001")
        AgentBase.create(ws, profile={"name": "job-1"}, config={"max_react_turns": 1})
        assert os.path.isfile(os.path.join(ws, "AGENT.json"))
        assert os.path.isfile(os.path.join(ws, "config.json"))
        assert os.path.isdir(os.path.join(ws, "state"))
        import json

        meta = json.load(open(os.path.join(ws, "AGENT.json")))
        assert meta["schema_version"] == 1 and meta["step_count"] == 0
        blob_path = os.path.join(ws, "state", "opaque_blob.bin")
        with open(blob_path, "wb") as f:
            f.write(b"\x00\x01concordia-checkpoint-placeholder")
        assert os.path.getsize(blob_path) > 0
    ok("agentsociety2 workspace create + AGENT.json schema + opaque state/ blob")

    # 4. SWORLDMODEL compiler schema importable alongside both engines.
    from compiler import scene_schema  # noqa: F401

    assert hasattr(scene_schema, "SCENE_SCHEMA")
    ok("sworldmodel compiler schema importable in the engine environment")

    print(f"PHASE1 COEXISTENCE PROOF: {len(checks)}/4 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
