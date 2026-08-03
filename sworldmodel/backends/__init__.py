"""Execution backends for the decision layer.

Each backend subpackage turns validated decision contracts
(``sworldmodel.decision``) into runs on a concrete engine.  The top-level
package deliberately imports nothing: a backend with optional third-party
dependencies (for example ``concordia_local``) must be imported explicitly,
so ``import sworldmodel`` keeps working on interpreters where those optional
engine packages are absent.
"""
