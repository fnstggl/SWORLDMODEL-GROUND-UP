"""The LLM-native social simulation loop.

LLMs write meaning.  Code controls access, time, identity, persistence,
causality, and replay.

The frozen four-field scene manifest produced by the minimal world
compiler is consumed directly (``adapter``), instantiated into the
existing persistent runtime, and then driven one concrete causal step at a
time: the world model adjudicates what immediately happens, actor models
decide only what they attempt, and deterministic code commits every event
with its exact time, cause, visibility, and observation state.

Nothing here duplicates a kernel primitive: authoritative time, event
ordering, the immutable ledger, actor identity, actor memories, scheduling
and replay all come from ``sworldmodel``.
"""
from .adapter import instantiate_scene_manifest
from .journal import Journal
from .trajectory import SemanticTrajectory, run_trajectory
from .replay import replay_trajectory

__all__ = ["Journal", "SemanticTrajectory", "instantiate_scene_manifest",
           "replay_trajectory", "run_trajectory"]
