"""AgentSociety distributed backend (Phase 7, Stage A: branch-level).

Module map (import the submodule you need explicitly):

- ``branch_executor``       -- ``run_candidates_distributed``: distribute
  complete, self-contained engine branches through AgentSociety's real
  worker/dispatcher interfaces (audit Option 2 primitives:
  ``init_dispatchers`` -> ``build_service_proxy`` ->
  ``create_agents_batch`` -> ``step_agent_batch`` with single-branch
  batches).  Pure stdlib plus ``sworldmodel`` at import time; the
  ``agentsociety2`` / ``ray`` imports happen lazily inside the run call,
  so importing the module works on interpreters where those optional
  packages are absent.
- ``branch_agent_template`` -- the custom ``AgentBase`` subclass SOURCE
  that the executor materializes into ``<workspace>/custom/agents/`` for
  AgentSociety's stock custom-module scanner.  Importing it directly
  requires the optional ``agentsociety2`` package and raises a clear
  ``ImportError`` without it; the executor only reads its source text and
  never imports it.

This package intentionally imports nothing here: ``import sworldmodel``
must keep working (Python >= 3.11) without ``agentsociety2``, ``ray``, or
``gdm-concordia`` installed.  Division of labour (directive, "Integration
principle"): SWORLDMODEL creates counterfactual branches, AgentSociety
schedules complete branches, the local engine backend runs each complete
simulation, AgentSociety collects the per-branch results, SWORLDMODEL
compares measured outcomes.
"""
