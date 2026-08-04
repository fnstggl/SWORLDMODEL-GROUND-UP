"""Code-owned identifier registry.

Every world, actor, candidate, and branch identifier is registered by code
at creation time.  Semantic validation resolves references ONLY against this
registry, so a fabricated identifier (one no code path ever created) or a
cross-branch reference (a branch cited with a world/candidate pairing other
than the one it was registered with) is rejected instead of being trusted.

Registration itself is strict: duplicates and references to unregistered
objects raise ``ContractValidationError`` immediately.  Pure stdlib, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import (CompiledDecisionWorld, ContractValidationError,
                        InterventionCandidate, TimeHorizon, ValidationIssue,
                        _SLUG_RE)


def _fail(path: str, code: str, message: str) -> None:
    raise ContractValidationError([ValidationIssue(path, code, message)])


@dataclass(frozen=True)
class _WorldRecord:
    actor_ids: frozenset
    actor_names: dict
    insertion_actor_id: str
    horizon: TimeHorizon


class ContractRegistry:
    """Registry of code-created identifiers and their bindings."""

    def __init__(self) -> None:
        self._worlds: dict = {}
        self._candidates: dict = {}   # candidate_id -> world_id
        self._branches: dict = {}     # branch_id -> (world_id, candidate_id)

    # -- registration ------------------------------------------------------

    def register_world(self, world: CompiledDecisionWorld) -> None:
        if not isinstance(world, CompiledDecisionWorld):
            _fail("world", "wrong_type",
                  f"expected CompiledDecisionWorld, got "
                  f"{type(world).__name__}")
        if world.world_id in self._worlds:
            _fail("world_id", "duplicate_id",
                  f"world {world.world_id!r} is already registered")
        names: dict = {}
        for actor in world.actors:
            names.setdefault(actor.name, []).append(actor.actor_id)
        self._worlds[world.world_id] = _WorldRecord(
            actor_ids=frozenset(world.actor_ids()),
            actor_names=names,
            insertion_actor_id=world.intervention_insertion_point.actor_id,
            horizon=world.horizon())

    def register_candidate(self, candidate: InterventionCandidate,
                           world_id: str) -> None:
        if not isinstance(candidate, InterventionCandidate):
            _fail("candidate", "wrong_type",
                  f"expected InterventionCandidate, got "
                  f"{type(candidate).__name__}")
        if world_id not in self._worlds:
            _fail("world_id", "unregistered_id",
                  f"world {world_id!r} is not registered")
        if candidate.candidate_id in self._candidates:
            _fail("candidate_id", "duplicate_id",
                  f"candidate {candidate.candidate_id!r} is already "
                  "registered")
        self._candidates[candidate.candidate_id] = world_id

    def register_branch(self, branch_id: str, world_id: str,
                        candidate_id: str) -> None:
        if not isinstance(branch_id, str) or not _SLUG_RE.match(branch_id):
            _fail("branch_id", "invalid_id",
                  f"branch identifier {branch_id!r} must match "
                  f"{_SLUG_RE.pattern}")
        if branch_id in self._branches:
            _fail("branch_id", "duplicate_id",
                  f"branch {branch_id!r} is already registered")
        if world_id not in self._worlds:
            _fail("world_id", "unregistered_id",
                  f"world {world_id!r} is not registered")
        if candidate_id not in self._candidates:
            _fail("candidate_id", "unregistered_id",
                  f"candidate {candidate_id!r} is not registered")
        bound_world = self._candidates[candidate_id]
        if bound_world != world_id:
            _fail("candidate_id", "cross_branch_reference",
                  f"candidate {candidate_id!r} belongs to world "
                  f"{bound_world!r}, not {world_id!r}; a branch may not "
                  "join identifiers across worlds")
        self._branches[branch_id] = (world_id, candidate_id)

    # -- queries -----------------------------------------------------------

    def has_world(self, world_id: str) -> bool:
        return world_id in self._worlds

    def has_candidate(self, candidate_id: str) -> bool:
        return candidate_id in self._candidates

    def has_branch(self, branch_id: str) -> bool:
        return branch_id in self._branches

    def has_actor(self, world_id: str, actor_id: str) -> bool:
        record = self._worlds.get(world_id)
        return record is not None and actor_id in record.actor_ids

    def world_actor_ids(self, world_id: str) -> frozenset:
        return self._require_world(world_id).actor_ids

    def world_insertion_actor(self, world_id: str) -> str:
        return self._require_world(world_id).insertion_actor_id

    def world_horizon(self, world_id: str) -> TimeHorizon:
        return self._require_world(world_id).horizon

    def resolve_actor_reference(self, world_id: str, reference: str):
        """Resolve an actor identifier OR unique actor name to the
        identifier; returns None when unknown or ambiguous."""
        record = self._require_world(world_id)
        if reference in record.actor_ids:
            return reference
        matches = record.actor_names.get(reference, [])
        if len(matches) == 1:
            return matches[0]
        return None

    def candidate_world(self, candidate_id: str) -> str:
        if candidate_id not in self._candidates:
            _fail("candidate_id", "unregistered_id",
                  f"candidate {candidate_id!r} is not registered")
        return self._candidates[candidate_id]

    def branch_binding(self, branch_id: str) -> tuple:
        if branch_id not in self._branches:
            _fail("branch_id", "unregistered_id",
                  f"branch {branch_id!r} is not registered")
        return self._branches[branch_id]

    def _require_world(self, world_id: str) -> _WorldRecord:
        if world_id not in self._worlds:
            _fail("world_id", "unregistered_id",
                  f"world {world_id!r} is not registered")
        return self._worlds[world_id]
