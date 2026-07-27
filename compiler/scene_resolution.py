"""The generic natural-language resolution wrapper.

There are no fixed terminal families.  A compiled scene carries ONE
open-ended natural-language resolution; this wrapper binds it to the
runtime's terminal interface with these guarantees, proven by tests:

- it is false at genesis (it never resolves before any event has fired);
- it can inspect the persistent event history (read-only copies);
- a judgment must cite the exact ledger record seqs supporting it, and the
  citations are verified against the history;
- it cannot create events or modify world state (it only ever sees deep
  copies of the records);
- it cannot predict a result before it occurs (with no judge attached, the
  run ends "unresolved_pending_judgment" at the cutoff).

Classifying the actual event history against the resolution text is a
LATER runtime-judge concern, outside world compilation and outside the
semantic-call budget; ``judge`` is the seam where it will plug in."""
from __future__ import annotations

import copy
from dataclasses import dataclass

from sworldmodel.engine import Terminal
from sworldmodel.simclock import parse_iso


@dataclass(frozen=True)
class NLResolution:
    question: str
    resolution: str
    cutoff: str          # tz-aware ISO instant
    world_id: str

    def to_dict(self) -> dict:
        return {"question": self.question, "resolution": self.resolution,
                "cutoff": self.cutoff, "world_id": self.world_id}


def build_nl_terminal(res: NLResolution, judge=None) -> Terminal:
    """-> engine Terminal.  ``judge`` (optional, for tests and the later
    judgment phase) is a pure function judge(records, resolution, question)
    -> None | {"answer": str, "detail": str, "event_seqs": [int, ...]}.
    It receives a DEEP COPY of the ledger records -- structurally unable to
    create events or modify world state."""

    def evaluate(world, final: bool):
        if not world.history:
            return None                    # false at genesis, always
        if judge is not None:
            verdict = judge(copy.deepcopy(world.records), res.resolution,
                            res.question)
            if verdict is not None:
                seqs = verdict.get("event_seqs") or []
                known = {r["seq"] for r in world.records}
                if not seqs or any(s not in known for s in seqs):
                    raise ValueError(
                        "a resolution judgment must cite existing ledger "
                        "record seqs")
                return {"answer": verdict["answer"],
                        "detail": verdict.get("detail", res.resolution),
                        "computed_from": [f"record:{s}" for s in seqs]}
        if final:
            return {"answer": "unresolved_pending_judgment",
                    "detail": f"cutoff reached; the trajectory awaits "
                              f"judgment against: {res.resolution}",
                    "computed_from": ["terminal.cutoff"]}
        return None

    return Terminal(res.question, parse_iso(res.cutoff), evaluate)
