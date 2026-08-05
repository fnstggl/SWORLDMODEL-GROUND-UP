"""Experiment-only code.

Nothing under ``experiments/`` is production.  The accepted engine lives
in ``sworldmodel/`` and ``compiler/``; this tree only OBSERVES it, freezes
its inputs, records every live model call, and writes audit artifacts.
No module here is imported by production code.
"""
