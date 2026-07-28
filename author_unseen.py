"""Agent E -- author 20 unseen acceptance questions, implementation-blind.

The authoring model receives ONLY the case-format contract and diversity
instructions -- nothing about the compiler, its prompts, or the frozen
dataset -- and runs after the implementation freeze.  Output:
acceptance/dataset_unseen.json."""
import json
import os

from compiler.scene_llm import SceneCaller

HERE = os.path.dirname(os.path.abspath(__file__))

SPEC = """You are authoring 20 UNSEEN test questions for a social-scene \
compiler you know nothing about.  Each case is exactly:
{"id": snake_case_slug, "kind": "sufficient" | "insufficient",
 "category": short_slug, "historical": false,
 "question": "1-3 sentence natural-language question",
 "start": tz-aware ISO 8601, "cutoff": tz-aware ISO 8601 after start,
 "context": string or null,
 "why": "one sentence on why it is sufficient/insufficient"}

Author 15 SUFFICIENT cases: concrete social questions (who notices, \
decides, communicates, responds) with identifiable parties (named people, \
role-identified parties, organizations, defined groups), realistic \
horizons (hours to weeks), fictional/synthetic names and organizations, \
across at least 10 distinct social domains including at least one \
historical-style case with "historical": true set in a real pre-2020 \
institutional setting whose start/cutoff precede the outcome and whose \
text never states the outcome.  Give ~5 of them a short context \
paragraph.  Make several deliberately tricky: unusual phrasing, nested \
clauses, multiple parties, a deadline inside the question.

Author 5 INSUFFICIENT cases: questions that should be refused -- e.g. no \
identifiable party anywhere, pure fact lookup, pure physics, past \
counterfactual, unobservable feeling with no proxy.

Vary time zones and offsets.  Use dates in August-October 2026 except the \
historical case.  Reply with ONLY a JSON array of the 20 case objects."""


def main():
    caller = SceneCaller()
    r = caller.semantic_call("author_unseen", SPEC,
                             "Author the 20 cases now. Reply with ONLY the "
                             "JSON array (or an object with key 'cases').")
    cases = r["parsed"]
    if isinstance(cases, dict):
        cases = cases.get("cases") or next(iter(cases.values()))
    assert isinstance(cases, list) and len(cases) == 20, len(cases)
    ids = [c["id"] for c in cases]
    assert len(set(ids)) == 20
    for c in cases:
        assert c["kind"] in ("sufficient", "insufficient")
        c.setdefault("context", None)
        c.setdefault("historical", False)
    path = os.path.join(HERE, "acceptance", "dataset_unseen_final.json")
    with open(path, "w") as f:
        json.dump(cases, f, indent=1)
    kinds = [c["kind"] for c in cases]
    print(f"wrote {path}: {kinds.count('sufficient')} sufficient, "
          f"{kinds.count('insufficient')} insufficient")


if __name__ == "__main__":
    main()
