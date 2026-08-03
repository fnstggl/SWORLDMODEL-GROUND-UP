"""Set-derived state canonicalization actually canonicalizes (phases
8-11 review finding F2).

``_canonicalize_state_tree`` exists to make ``stored_hashes`` -- the one
known upstream state key serialized as ``list(<set>)``, whose order is
salted per process by PYTHONHASHSEED -- byte-canonical across processes.
The builder's own rosters never carry an associative bank, so the branch
is purely defensive; this unit proves the defense WORKS against the
shape it guards (permutation identity) and touches nothing else
(passthrough).
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 12):
    pytest.skip(
        "checkpoint suite requires Python >= 3.12 (engine env); "
        "run with /home/user/engine-env/bin/python",
        allow_module_level=True,
    )

pytest.importorskip("concordia.environment.engines.sequential",
                    exc_type=ImportError)

from sworldmodel.backends.concordia_local.checkpoint import (
    _canonicalize_state_tree, checkpoint_canonical_json)


def test_stored_hashes_permutations_canonicalize_identically():
    """Two permutations of the same set-derived list -- exactly what two
    PYTHONHASHSEED processes would serialize -- canonicalize to
    identical trees and identical canonical bytes."""
    base = {
        "__memory_bank__": {
            "stored_hashes": ["h_bravo", "h_alpha", "h_charlie"],
            "memory_bank": ["row one", "row two"],
        },
        "act_component": {"state": "idle"},
    }
    permuted = {
        "__memory_bank__": {
            "stored_hashes": ["h_charlie", "h_bravo", "h_alpha"],
            "memory_bank": ["row one", "row two"],
        },
        "act_component": {"state": "idle"},
    }
    canon_a = _canonicalize_state_tree(base)
    canon_b = _canonicalize_state_tree(permuted)
    assert canon_a == canon_b
    # The list really was SORTED, not merely compared loosely...
    assert canon_a["__memory_bank__"]["stored_hashes"] \
        == ["h_alpha", "h_bravo", "h_charlie"]
    # ...and the canonical byte form (what the checkpoint records and
    # hashes) is identical too.
    assert checkpoint_canonical_json(canon_a) \
        == checkpoint_canonical_json(canon_b)
    # Sibling order-bearing lists are untouched.
    assert canon_a["__memory_bank__"]["memory_bank"] \
        == ["row one", "row two"]


def test_stored_hashes_are_canonicalized_at_any_depth():
    """The key is recognized recursively -- including for dicts nested
    inside lists, where the parent key does not propagate."""
    tree_a = {"entities": [{"stored_hashes": ["b", "a"]},
                           {"stored_hashes": ["z", "y"]}]}
    tree_b = {"entities": [{"stored_hashes": ["a", "b"]},
                           {"stored_hashes": ["y", "z"]}]}
    assert _canonicalize_state_tree(tree_a) \
        == _canonicalize_state_tree(tree_b) \
        == {"entities": [{"stored_hashes": ["a", "b"]},
                         {"stored_hashes": ["y", "z"]}]}


def test_trees_without_the_key_pass_through_unchanged():
    """A tree carrying NO set-derived key is returned structurally
    unchanged: every other list keeps its order (order there is
    meaningful state) and scalars are untouched."""
    tree = {
        "memory_bank": ["second-would-sort-first", "alpha row"],
        "steps": [3, 1, 2],
        "nested": {"names": ["Zoe", "Abe"], "count": 2},
        "flag": True,
    }
    assert _canonicalize_state_tree(tree) == tree


def test_non_string_items_under_the_key_are_left_verbatim():
    """The sort applies only to all-string lists (the upstream
    ``list(<set of str hashes>)`` shape); anything else is preserved
    verbatim rather than reordered on a guess."""
    tree = {"stored_hashes": ["b", 2, "a"]}
    assert _canonicalize_state_tree(tree) == {"stored_hashes":
                                              ["b", 2, "a"]}
