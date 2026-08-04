# Harness shakedown runs (kept, not counted)

These are the FIRST two live runs of the settling harness, one per arm.
They are real, complete, recorded runs against the live provider; they are
kept here rather than deleted because deleting a run one has already seen
is exactly how a result gets quietly shaped.

They are **not** counted in `SETTLING_MEASUREMENTS.json` and not in the
n = 3 per-arm rates, for one reason: they ran before
`settling.enactment_check` gained its two content-blind overlap numbers
(`longest_shared_run_chars`, `candidate_token_overlap_ratio`). Those were
added because arm B's first sample showed that a bare "did the sender
reproduce the candidate verbatim?" yes/no reports a sender that WAITED and
a sender that SENT ITS OWN WORDS identically -- which would have hidden
the most informative thing in the experiment. Mixing two measurement
versions inside one reported rate would be worse than re-running, so the
three counted reps per arm were all run with the final instrument.

What these two runs found, for the record, is the same as what the counted
runs found:

| | shakedown arm A | shakedown arm B |
|---|---|---|
| sender enacted the candidate verbatim | no | no |
| candidate text in the recipient's prompts | no | no |
| `intervention_delivered` | `not_delivered` | `not_delivered` |
| ranking | REFUSED | REFUSED |
| unresolved observer names | 0 | 0 |
| forced observer interceptions | 4 | 4 |

Arm A's sender: *"Beckett Zahedi waits for a reply, checking his inbox
periodically but not sending any follow-up or additional messages, keeping
the ball in Peter Thiel's court as requested."*

Arm B's sender: *"Beckett Zahedi reviews the draft one more time, tightens
the subject line to \"Aurelius: 7.24× GPU goodput/$ (replay only, not
prod-validated)\" and the opening line to \"I'm not asking for money—I want
your criticism,\" then sends the email to Peter Thiel through the
established channel and sets a calendar reminder to follow up in five days
if no reply."*

That contrast -- arm B's sender performs the send but authors its own
message text -- is what prompted the two extra overlap numbers.
