# Acceptance dataset specification (frozen before case-specific debugging)

Produce `acceptance/dataset_core.json`: a JSON array of test cases for a
social-scene compiler. Each case has ONLY these fields:

```json
{
  "id": "short_slug",
  "kind": "sufficient" | "insufficient",
  "category": "<one of the categories below>",
  "historical": false,
  "question": "the natural-language question",
  "start": "2026-07-27T09:00:00-05:00",
  "cutoff": "2026-08-10T09:00:00-05:00",
  "context": "optional user-provided context string, or null",
  "why": "one sentence: why this case is sufficient/insufficient"
}
```

Rules:
- 100 cases with kind "sufficient": simple, well-specified SOCIAL questions a
  simulator could answer by watching who notices, communicates, decides.
- 20 cases with kind "insufficient": deliberately ambiguous, underspecified,
  pure factual-lookup, purely physical/operational with no social decision,
  or unresolvable — the compiler should honestly abstain on these.
- NO hand-authored actor lists, NO prebuilt worlds, NO scene descriptions —
  only question, start, cutoff, optional context.
- Timestamps must be timezone-aware ISO 8601, start strictly before cutoff,
  horizons from hours to a few months.
- Mostly SYNTHETIC/FICTIONAL people, companies, and institutions (invented
  names) so memorized outcomes cannot dominate. Names must be plausible and
  varied (cultures, genders, org types).
- Exactly 8-10 of the 100 sufficient cases use FAMOUS HISTORICAL actors or
  institutions with `"historical": true`, a start/cutoff BEFORE the known
  outcome, and the outcome NOT stated anywhere in the case. These test
  outcome-leakage, not forecasting.
- The 100 sufficient cases must cover ALL of these categories (roughly
  evenly; use the exact category strings):
  direct_message_response, cold_outreach, scheduling, hiring_response,
  interpersonal_negotiation, organizational_approval,
  committee_participation, legislative_institutional, customer_response,
  founder_executive_decision, public_communication, small_group_coordination,
  representative_population, deadline_bounded_action, mixed_social_scheduled.
- The 20 insufficient cases must include: missing decision-maker, missing
  observable outcome, pure fact lookup ("what is the capital of..."),
  pure physics ("will this beam hold..."), past counterfactual, pure
  matter of taste, question about the asker's own unstated feelings,
  vague "will things improve" with no observable, contradiction in premise,
  and empty/near-empty questions.
- `context` should be non-null in roughly a third of sufficient cases (a
  short paragraph of user-supplied situation detail); null elsewhere.
- ids unique, lowercase snake_case.

Output ONLY the JSON file at acceptance/dataset_core.json (valid JSON, no
comments), plus a one-paragraph coverage summary at acceptance/DATASET_NOTES.md
(counts per category/kind/historical).
