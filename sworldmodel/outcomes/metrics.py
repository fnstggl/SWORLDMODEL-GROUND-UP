"""Generic trace-metric toolkit: matchers that produce CITED readings.

The outcome engine is fully generic -- this package never knows a metric
by name.  The caller supplies ``{metric_name: predicate}`` where a
predicate is::

    callable(event_trace, result_dict) -> (value, citations)

``value`` is a boolean or finite number (never a string) and
``citations`` is a NON-EMPTY sequence of trace event indices (integers)
and/or explicit ``'event:<event_id>'`` / ``'state:<key>'`` reference
strings.  The helpers here build such predicates from caller-supplied
text matchers, so every reading arrives already carrying the events it
was computed from -- the shape the Phase 3 metric-citation validation
requires.

Absence rule: a reading that matched NO event (a false existence claim,
a zero count) is still a claim about the trace -- it was computed by
scanning the COMPLETE recorded event stream.  Such readings cite the
scan bound instead: :data:`WHOLE_TRACE_CITATION`, the terminal-state key
the local runner records for exactly that stream.  The citation target
is a parameter so callers with differently shaped terminal state can
redirect it; it is never silently dropped, because a metric that cites
nothing is rejected downstream.

Pure stdlib; works on ``TraceEvent`` objects and on plain
``{'event_id', 'description'}`` mappings alike.
"""

from __future__ import annotations

from sworldmodel.decision.contracts import (ContractValidationError,
                                            ValidationIssue)

#: default citation for readings computed from the ABSENCE of matching
#: events: the runner's terminal-state key recording the size of the
#: committed event stream that was scanned
WHOLE_TRACE_CITATION = "state:committed_event_count"


def _fail(path: str, code: str, message: str) -> None:
    raise ContractValidationError([ValidationIssue(path, code, message)])


def event_description(entry) -> str:
    """The description text of one trace entry (contract object or plain
    mapping)."""
    if hasattr(entry, "description"):
        return entry.description
    if isinstance(entry, dict) and "description" in entry:
        return entry["description"]
    _fail("event_trace", "wrong_type",
          "trace entries must be TraceEvent objects or mappings with a "
          f"'description' key, got {type(entry).__name__}")


def substring_matcher(*needles, require_all: bool = True,
                      case_sensitive: bool = True):
    """A text matcher: does one event description contain the needles?

    ``require_all=True`` demands every needle; ``False`` accepts any one.
    The needle TEXT is caller data (scenario vocabulary belongs to
    callers and fixtures, never to this module).
    """
    if not needles:
        _fail("needles", "empty_collection",
              "at least one needle string is required")
    for index, needle in enumerate(needles):
        if not isinstance(needle, str) or not needle:
            _fail(f"needles[{index}]", "wrong_type",
                  "every needle must be a non-empty string, got "
                  f"{needle!r}")
    if not case_sensitive:
        needles = tuple(needle.lower() for needle in needles)

    def matcher(description: str) -> bool:
        haystack = description if case_sensitive else description.lower()
        found = (needle in haystack for needle in needles)
        return all(found) if require_all else any(found)

    matcher.needles = tuple(needles)
    return matcher


def matching_indices(event_trace, matcher) -> tuple:
    """Indices of every trace entry whose description satisfies the
    matcher, in trace order."""
    if not callable(matcher):
        _fail("matcher", "wrong_type", "matcher must be callable")
    return tuple(index for index, entry in enumerate(event_trace)
                 if matcher(event_description(entry)))


def exists_metric(matcher, *, absent_citation: str = WHOLE_TRACE_CITATION):
    """Predicate: True when at least one trace event satisfies the
    matcher, citing exactly the matching events; a False reading cites
    ``absent_citation`` (the recorded scan bound)."""
    _check_absent_citation(absent_citation)

    def predicate(event_trace, result_dict):
        del result_dict  # existence is read from the trace alone
        matched = matching_indices(event_trace, matcher)
        if matched:
            return True, matched
        return False, (absent_citation,)

    return predicate


def count_metric(matcher, *, absent_citation: str = WHOLE_TRACE_CITATION):
    """Predicate: how many trace events satisfy the matcher, citing the
    matching events; a zero count cites ``absent_citation``."""
    _check_absent_citation(absent_citation)

    def predicate(event_trace, result_dict):
        del result_dict  # the count is read from the trace alone
        matched = matching_indices(event_trace, matcher)
        if matched:
            return len(matched), matched
        return 0, (absent_citation,)

    return predicate


def _check_absent_citation(absent_citation) -> None:
    if not isinstance(absent_citation, str) \
            or not absent_citation.startswith(("event:", "state:")) \
            or absent_citation.partition(":")[2] == "":
        _fail("absent_citation", "invalid_value",
              "absent_citation must be an explicit 'event:<event_id>' or "
              f"'state:<key>' reference, got {absent_citation!r}")
