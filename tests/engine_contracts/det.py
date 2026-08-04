"""Determinism harness for Concordia runs — reused by later phases (gate E).

Why this exists (audit CONCORDIA_AUDIT.md §13, verified against source):

- Every ``InteractiveDocument`` creates an UNSEEDED ``np.random.default_rng()``
  unless one is injected (concordia/document/interactive_document.py:63-67),
  and ``multiple_choice_question(randomize_choices=True)`` permutes option
  order with that rng (interactive_document.py:303-336). Components construct
  documents without an rng, so option shuffling is nondeterministic even with
  a deterministic model.
- Several GM components additionally use the global ``random`` module
  (event_resolution.py:881, 1188; next_acting.py:385).
- Therefore bit-exact deterministic runs are NOT reachable through public
  configuration alone; the harness must (a) seed/patch
  ``numpy.random.default_rng`` and global ``random`` at run boundaries, and
  (b) callers should set ``randomize_choices=False`` on act components where
  that switch is exposed (ConcatActComponent; the SwitchAct GM paths have no
  such switch).

The patch below swaps the ``default_rng`` attribute on OUR process's already
imported ``numpy.random`` module object for the duration of the context and
restores it afterwards. It does not edit any upstream source file.

Every no-arg ``default_rng()`` call returns a FRESH generator seeded with the
same fixed seed. That makes each InteractiveDocument's draw stream identical
regardless of the (thread-pool) order in which documents are created, which is
exactly what run-level byte-identity needs. Calls that pass an explicit seed
are delegated to the original factory unchanged.
"""

from __future__ import annotations

import contextlib
import random
from collections.abc import Iterator

import numpy as np


def ones_embedder(text: str) -> np.ndarray:
    """Deterministic trivial sentence embedder for offline memory banks."""
    del text
    return np.ones(3)


@contextlib.contextmanager
def seeded_determinism(seed: int = 20260803) -> Iterator[None]:
    """Context manager: make Concordia's RNG entry points deterministic.

    Within the context:
      - ``numpy.random.default_rng()`` (no explicit seed) returns a fresh
        generator seeded with ``seed`` on every call;
      - the global ``random`` module is seeded with ``seed``;
      - the legacy ``numpy.random`` global state is seeded with
        ``seed % 2**32``.

    All three are restored on exit (monkeypatching our process only — no
    upstream source is modified).
    """
    original_default_rng = np.random.default_rng
    python_random_state = random.getstate()
    numpy_legacy_state = np.random.get_state()

    def _seeded_default_rng(seed_arg=None, *args, **kwargs):
        if seed_arg is None and not args and not kwargs:
            return original_default_rng(seed)
        return original_default_rng(seed_arg, *args, **kwargs)

    np.random.default_rng = _seeded_default_rng
    random.seed(seed)
    np.random.seed(seed % (2**32))
    try:
        yield
    finally:
        np.random.default_rng = original_default_rng
        random.setstate(python_random_state)
        np.random.set_state(numpy_legacy_state)
