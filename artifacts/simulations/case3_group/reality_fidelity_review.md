# Reality fidelity review — `case3_group`

Judged by independent reviewers who did not build this system, against the trajectory in this directory.  The full reasoning, with quotations, is in `artifacts/semantic_runtime/QUALITY_GATE_FINAL.md`; the earlier round that these traces replaced is in `QUALITY_ACTOR_REALISM.md`, `QUALITY_CAUSAL_REALISM.md`, `QUALITY_INFORMATION_AND_TIMING.md` and `QUALITY_TERMINAL_INDEPENDENCE.md`.

The trajectory these verdicts were given on answered **YES**.

| dimension | verdict |
|---|---|
| actor realism | **FAIL** |
| causal realism | **REVISE** |
| information realism | **REVISE** |
| timing realism | **REVISE** |
| terminal independence | **PASS** |

No numeric score is given, deliberately: the reviewers were asked to say plainly what is realistic and what is not.

A trajectory fails the gate if any reviewer finds impossible knowledge, implausible actor behaviour, terminal steering, skipped essential causality, unrealistic timing, the world choosing an actor's decision, or materially unsupported consequences.

**This trajectory does not pass.**

The runs in this directory were re-run after the gate reported, with one fix applied (an event whose description already exists word for word is dropped rather than committed again).  The verdicts above are from the traces that preceded that fix and have not been re-judged; the numbers in `SEMANTIC_RUNTIME_REPORT.md` §15 are from the current ones.
