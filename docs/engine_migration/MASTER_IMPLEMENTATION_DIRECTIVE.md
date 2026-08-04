Act as the primary senior engineering orchestrator for a full implementation pass that replaces the unreliable SWORLDMODEL semantic runtime with a new engineering foundation built from the exact, already-working Concordia and AgentSociety 2 codebases.
Do not stop after producing an audit or plan. Audit first, then implement the architecture in controlled phases, test each phase, adversarially review it, fix every failure, and continue until every mandatory completion gate below passes on one frozen final commit.

### Implementation branch authority

Begin from the latest remote main after the verified control-plane PR has been merged.

Do not use codex/single-trajectory-runtime-final-completion as the implementation base.

Inspect that branch only for potentially reusable compiler, evidence, evaluator, fixture, or test work. Reuse an item only when it independently fits the new architecture and passes current tests.

Create one new implementation branch from updated main:

claude/concordia-agentsociety-best-action-engine

Open one draft PR from that branch into main.

Do not merge it during this run.

Do not stop to ask about ordinary engineering choices, debugging decisions, architecture details that can be resolved from the repositories, or which defect to fix next.

Ask me only when progress genuinely requires external information that is unavailable to you, such as:

- a missing API key or credential;
- access permission;
- a destructive or irreversible product decision not resolved by this directive;
- a required paid service that cannot be replaced locally.

When one gate requires external input, continue every independent task that can still proceed. Record the blocked gate and exact required input. Do not classify the entire run as EXTERNAL_BLOCKER while meaningful independent progress remains possible.

Repositories
Audit the complete current codebases, tests, examples, package manifests, dependencies, public interfaces, serialization behavior, and runtime paths of:
SWORLDMODEL-GROUND-UP
https://github\.com/fnstggl/SWORLDMODEL\-GROUND\-UP
Google DeepMind Concordia
https://github\.com/google\-deepmind/concordia
AgentSociety 2
https://github\.com/tsinghua\-fib\-lab/agentsociety

(If It's easier to access, I attached forked versions of these repositories in this environment as well)

At the beginning of the run:
record the exact commit SHA of all three repositories;
create a new implementation branch;
record the Python and dependency requirements of each project;
run the existing test suites and runnable smoke examples before changing SWORLDMODEL;
save the baseline commands, results, failures, runtime, and environment details;
inspect the actual current APIs rather than relying on class names or assumptions in this prompt when the source code differs.
Core product vision
SWORLDMODEL is not primarily a generic forecasting system that answers arbitrary questions such as:
Will a bill pass?
Will Tesla exceed a delivery target?
Will an unrelated future event happen?
It is an intervention-centered best-action simulator.
The user supplies a situation, a desired result, constraints, and potentially some candidate actions. The system constructs the smallest relevant social world, runs matched simulations in which different actions are introduced, observes how the simulated people and world actually respond, measures the resulting outcome, and returns the strongest action among those tested.
The core product question is:
Given this situation and desired outcome, what action should the decision-maker take?
The central loop is:
Natural-language decision problem
        ↓
Compile the smallest relevant starting world
        ↓
Generate or receive candidate interventions
        ↓
Clone the same starting world for every candidate
        ↓
Apply one different intervention per branch
        ↓
Run the social simulation
        ↓
Measure the result from what actually happened
        ↓
Compare branches
        ↓
Return the best-performing tested action

The recommendation must come from the resulting simulated world state and event history. A final LLM must not simply read several narratives and invent which option “feels best.”
For this engineering pass, it is acceptable to report:
Best-performing action among the candidates tested in this engineering simulation.
Do not claim that the system has proven a global optimum or achieved calibrated real-world accuracy yet.
Scale target
Build one engineering architecture that can support:
Individual scale
two-person messaging;
persuasion;
negotiations;
fundraising calls;
follow-ups.
Small-team scale
approximately 5–20 people;
meetings;
private conversations;
authority;
coalitions;
commitments;
decisions.
Societal infrastructure
hundreds and eventually thousands of agents;
distributed execution;
persistent workspaces;
bounded LLM concurrency;
sparse activation;
checkpointing;
failure isolation;
aggregate outcome collection.
These are not the only situations each scenario should be able to support, this should ideally handle general / universal situations, these are examples not an extensive list
Individual and team simulations must become genuinely end-to-end functional during this pass.
Societal-scale infrastructure must be proven during this pass, but realistic population construction, category-specific behavior calibration, market realism, and policy realism are later work.
Do not claim that shallow or scripted scale tests prove realistic societal behavior.

Mandatory first actions, in exact order

1. Start from the latest remote main containing the merged verified control plane.
2. Confirm the working tree is clean.
3. Run the control-plane validator.
4. Create the new implementation branch from that exact main.
5. Save this complete master directive at docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md.
6. Record its SHA-256 hash.
7. Replace all MASTER_DIRECTIVE_PENDING placeholders with the complete architecture, task graph, critical path, protected paths, and acceptance gates derived from this directive.
8. Validate the initialized durable state.
9. Record a current-SHA initialization receipt.
10. Transition from ready_for_master to implementation.
11. Create the draft PR into main.
12. Begin the three-repository audit.
13. Only after the audit gates pass may production architecture implementation begin.

Do not change production implementation files before steps 1 through 10 pass.

Existing verified Claude Code control plane
This repository already contains a committed and tested Claude Code control plane.
Do not recreate, replace, broadly refactor, disable, or bypass:
.claude/settings.json
.claude/hooks/
.claude/tools/
.claude/agents/
.agent-run/
tests/control_plane/

Do not create a second hook system, watchdog, task ledger, acceptance ledger, or durable-state directory.
Treat the existing control-plane implementation and .claude/HOOKS_README.md as authoritative unless a demonstrated defect requires a controlled hook-maintenance phase.
Master-run preflight and initialization handshake
Before modifying any production implementation file:
Confirm the current branch begins from the latest merged control-plane commit.
Read completely:
CLAUDE.md;
.claude/HOOKS_README.md;
.agent-run/GOAL.md;
.agent-run/RUN_STATE.json;
.agent-run/ARCHITECTURE.md;
.agent-run/CRITICAL_PATH.md;
.agent-run/TASK_GRAPH.json;
.agent-run/ACCEPTANCE_STATUS.json;
.agent-run/HOOK_BOOTSTRAP_STATUS.json;
.agent-run/HANDOFF.md.
Confirm:
the control-plane validator passes;
no background jobs remain active;
the working tree is clean;
the run mode is ready_for_master;
hook bootstrap status permits the master run.
Save this complete master directive without summarizing or rewriting it at:
docs/engine_migration/MASTER_IMPLEMENTATION_DIRECTIVE.md

Compute and record its SHA-256 hash.
Populate the implementation-specific contents of:
ARCHITECTURE.md;
TASK_GRAPH.json;
CRITICAL_PATH.md;
DECISIONS.md;
UPSTREAM_PROTECTED_PATHS.json;
ACCEPTANCE_STATUS.json.
Represent every mandatory implementation phase and acceptance gate from this directive in the task graph and acceptance status.
Validate that no required implementation file remains marked MASTER_DIRECTIVE_PENDING.
Create a current-SHA receipt proving that master-context initialization passed.
Set the master-context fields in RUN_STATE.json to valid initialized values.
Transition the mode from ready_for_master to implementation.
Only after that successful transition may production implementation begin.
Do not fight or bypass PreToolUse when it blocks production edits before this handshake. Complete the required initialization instead.
If the control plane itself has a demonstrated defect:
record the defect;
enter the documented hook_maintenance mode;
fix the smallest general cause;
add a discriminating regression test;
rerun the complete control-plane validator;
exit hook maintenance;
restart the affected implementation or acceptance evidence from a valid state.
Do not modify control-plane files during ordinary implementation mode.
Use the existing hooks exactly as designed
SessionStart
The existing hook restores the durable run state after startup, resume, clearing, compaction, or fork.
At the beginning of every continued session, verify the injected summary against the actual files before acting.
PreToolUse
The existing hook protects:
frozen acceptance runs;
upstream source;
control-plane files;
destructive Git operations;
evidence artifacts;
unmonitored long-running jobs.
When blocked, follow the safe alternative returned by the hook. Do not weaken the rule merely to make a command run.
TaskCompleted
Every mandatory phase must exist in both:
Claude Code’s structured task system; and
.agent-run/TASK_GRAPH.json.
Use task creation and task updates so the hook actually receives completion events.
Before attempting completion, produce:
all required artifacts;
exact validation commands;
passing current-SHA receipts;
required reviewer reports;
evidence that blocking findings are resolved;
any required clean-worktree proof.
Do not repeatedly attempt completion without correcting the exact unmet requirement returned by the hook.
TeammateIdle
Where this event has been live-verified in the current environment, every teammate must be assigned:
a named task;
an explicit owner entry;
required artifacts;
required receipts;
a machine-checkable completion contract.
Where the event is documented as unavailable, do not claim it is protecting the run. Use the verified fallback controls:
structured task ownership;

#### TeammateIdle

Read the verified TeammateIdle status from the committed control-plane records.

When it is recorded as available, use it with explicit teammate ownership, required artifacts, receipts, and completion contracts.

When it is recorded as unavailable, do not claim it is enforcing teammate completion. Use:

- TaskCompleted;
- selective SubagentStop;
- explicit task ownership;
- unresolved-owner checks;
- lead review at every phase boundary.

No teammate-owned task may disappear merely because the teammate returned or became idle.


TaskCompleted;
selective SubagentStop;
lead-agent review;
unresolved-owner checks at every phase boundary.
An unavailable TeammateIdle event is a documented platform limitation, not permission to abandon teammate work.
SubagentStop
Use the protected implementation-agent and test-watchdog roles for work that must produce mandatory artifacts before returning.
Use read-only investigation and reviewer agents for findings that must be allowed to return immediately.
Do not broaden SubagentStop to trap every reviewer or research agent.
Stop
The existing Stop hook is a deterministic final guardrail.
It does not replace /goal, and it is not an unlimited standalone loop.
The lead may finish only when:
ACCEPTANCE_STATUS.json.overall == "PASS"

or a genuine:
RUN_STATE.json.status == "EXTERNAL_BLOCKER"

Do not alter acceptance files merely to release the hook.
Do not rely on a printed completion phrase.
StopFailure
The existing hook records provider and API failures and creates recovery evidence.
It does not restart or continue a terminated Claude Code session.
Never claim that StopFailure itself restored execution.
ConfigChange
Do not modify Claude Code project settings during implementation or frozen acceptance.
A genuinely required settings change must use the documented hook-maintenance transition, complete regression testing, and full control-plane revalidation.
Use the existing monitored runner
All long-running, detached, concurrent, corpus, scale, load, or acceptance commands must run through:
.claude/tools/run_monitored.py

Do not launch them directly with:
&
nohup
disown
detached shells
unregistered Claude background execution

Do not build another watchdog unless a failing test proves the existing runner cannot satisfy a required behavior.
Every monitored run must specify:
a unique job ID;
exploratory or frozen-acceptance classification;
no-progress timeout;
total timeout;
heartbeat interval;
artifact directory;
progress source where available;
exact child command.
The resulting job and receipt must correspond to the exact Git SHA being tested.
Continuation mechanism
Use the built-in /goal mechanism as the primary lead-session continuation system.
Do not install or depend on Ralph.

For every 100-job, 1,000-job, corpus, checkpoint, distributed, or final acceptance run, an explicit progress source is mandatory.

Before launching the run, ensure it reports:

- completed units;
- total units;
- current unit identifier;
- current phase;
- last successful unit;
- last-progress timestamp.

Log growth alone is not sufficient progress evidence for these runs.

If the existing command does not expose progress, add a thin test-runner adapter that reports progress without modifying the production behavior under test.

Do not launch a large run that the monitored runner cannot distinguish as progressing, stalled, CPU-spinning, network-waiting, failed, or dead.

The /goal condition must remain under its character limit and refer to the committed master directive and machine-generated acceptance status.
Use this continuation instruction:
Read the durable run state, identify the highest-leverage unmet mandatory gate, execute the next critical-path action, test it, record current-SHA evidence, update the durable state, and continue.
/loop may be used only as a secondary drift and background-job reassessment mechanism.
It must not be treated as a process watchdog because it cannot interrupt a busy or hung command.
Session and provider failure limitation
The verified control plane prevents ordinary voluntary early completion, unsafe edits, unsupported task completion, and unmonitored background hangs.
It cannot guarantee recovery after:
an API-level session failure;
provider outage;
cloud worker termination;
unrecoverable Claude Code process exit.
Unless a real external supervisor has separately been installed and verified, do not claim one exists.
Before any session ends without PASS:
update HANDOFF.md;
record the exact highest-leverage blocker;
record the exact next action;
preserve or commit valid work;
record active or interrupted jobs;
leave enough durable state for a fresh session to continue safely.
A fresh session must resume from the durable state rather than starting another broad audit.
Frozen acceptance activation
Before every frozen acceptance batch:
freeze and commit the exact tested SHA;
set RUN_STATE.json.mode to frozen_acceptance;
record frozen_sha;
confirm the tree is clean;
confirm no older process can write into the new artifact directory;
launch the batch through run_monitored.py.
For:
100-job tests;
1,000-job tests;
full-corpus runs;
checkpoint equivalence runs;
final acceptance;
no production, prompt, fixture, evaluator, or configuration changes are permitted while the batch runs.
When a relevant change becomes necessary:
abort the batch
mark its evidence invalid
fix the issue
create a new frozen SHA
restart the complete batch

Long-horizon autonomous execution and anti-stall protocol
This is a long-horizon implementation run. Do not use the ordinary pattern of implementing for several hours, listing remaining critical issues, stopping, and waiting for me to request another debugging pass.
The implementation is complete only when the mandatory acceptance gates pass. Open code defects, failing tests, critical reviewer findings, performance hangs, and integration failures are work to continue, not reasons to stop.
1. Terminal-state rule
There are only two permitted terminal states:
PASS
or:
EXTERNAL_BLOCKER
- exact blocking condition
- direct evidence
- all attempted approaches
- why additional code or reasoning cannot resolve it
- the exact human action required
The following are not valid terminal states:
incomplete with critical issues;
mostly complete;
implementation done but tests remain;
reviewers found defects;
corpus still running;
one final rerun needed;
follow-up prompt recommended;
remaining work listed for the user;
stopped because the task became complicated;
stopped because the current approach repeatedly failed.
A code defect, failing test, race condition, architectural conflict, unknown API, hang, malformed output, or difficult debugging problem is not an external blocker.
Continue until it is resolved or replaced by a better approach.
2. Durable run state
Do not rely on the current conversation as the source of truth.
Use and continuously maintain the existing committed durable-state files. Do not recreate or reset them:
.agent-run/
  GOAL.md
  ARCHITECTURE.md
  RUN_STATE.json
  TASK_GRAPH.json
  CRITICAL_PATH.md
  DECISIONS.md
  BLOCKERS.md
  FAILURE_LEDGER.jsonl
  BACKGROUND_JOBS.json
  ACCEPTANCE_STATUS.json
  HANDOFF.md
GOAL.md must contain the unchanged product objective:
Build the working Concordia plus AgentSociety engineering foundation for an intervention-centered best-action simulator across individual, team, and societal infrastructure scales.
RUN_STATE.json must always identify:
current phase;
current frozen SHA, if any;
current status;
highest-leverage blocker;
exact next action;
open critical and high findings;
running background jobs;
which acceptance gates pass;
which acceptance gates remain;
whether completion is legally permitted.
Update the state after every meaningful implementation, failure, test batch, architecture decision, reviewer report, and session restart.

The files currently marked MASTER_DIRECTIVE_PENDING are intentional placeholders. Replace their placeholder contents with the exact implementation architecture, phases, tasks, protected paths, critical path, and acceptance gates derived from this master directive before modifying any production code.
At the start of every main-agent turn, resumed session, compacted session, scheduled loop, or externally restarted run:
read GOAL.md;
read RUN_STATE.json;
read CRITICAL_PATH.md;
read unresolved entries in BLOCKERS.md;
inspect the current Git state;
continue the recorded highest-leverage next action.
Do not restart by broadly re-auditing the repository unless the durable state proves the prior audit is missing or stale.
3. Critical-path discipline
Maintain one explicit critical path from the present state to the next unmet mandatory acceptance gate.
At every decision point, ask:
What unresolved issue currently blocks the greatest number of downstream completion gates?
Work on that issue first.
Do not choose work merely because it is easy, local, or recently discovered.
Use this priority:
architecture or upstream-integration failures;
correctness failures that can produce false simulated outcomes;
state isolation, persistence, concurrency, and replay failures;
hangs and operational reliability failures;
acceptance-gate test coverage;
performance improvements required for scale;
documentation;
optional cleanup.
Maintain a work-in-progress limit:
one primary implementation task
plus
at most one independent background validation batch
Do not open many unrelated implementation fronts.
4. Agent-team structure
Do not construct a large fictional company hierarchy.
Use a small accountable team:
Lead orchestrator
Owns:
critical path;
task graph;
integration decisions;
phase transitions;
frozen-SHA discipline;
final completion authority.
The lead must continue implementing and coordinating. It must not become a passive summarizer of subagent output.
Implementation agent
Owns the single current implementation task.
Only one agent may be the primary writer for a tightly coupled subsystem at a time.
Investigation agent
Read-only by default.
Generates and tests competing explanations for a defect before the writer changes architecture.
Test and watchdog agent
Owns:
test commands;
background jobs;
heartbeats;
progress detection;
timeouts;
artifact integrity;
frozen-SHA verification.
It must not modify production code during a frozen evaluation.
Adversarial reviewer
Read-only and isolated.
Attempts to disprove that the current phase meets its gates.
Final adjudicator
Runs only after all other gates appear complete.
A verified critical finding blocks completion.
Use additional agents only when their work is genuinely independent and has a clear file or responsibility boundary.
Use isolated Git worktrees for parallel editing agents.
Agent-team members must not edit the same files concurrently.
5. Machine-enforced completion
Use the already-installed and verified Claude Code hooks. Do not recreate or reconfigure them during ordinary implementation.
TaskCompleted
Block a task from being marked complete unless:
its specified artifacts exist;
its tests pass;
its acceptance checks pass;
its branch or worktree is clean;
its implementation evidence is recorded.
TeammateIdle
Prevent a teammate from going idle when:
it still owns an in-progress task;
required outputs are missing;
tests have not been run;
it has returned only an analysis when implementation was assigned.
SubagentStop
Prevent a required subagent from stopping when its assigned completion contract is unmet.
Stop
Prevent the lead session from stopping unless:
ACCEPTANCE_STATUS.json.overall == "PASS"
or:
RUN_STATE.json.status == "EXTERNAL_BLOCKER"
The Stop hook must provide Claude with:
the highest-leverage unmet gate;
the current blocker;
the exact next action;
the instruction to continue.
Do not permit Claude to unlock the Stop hook merely by writing a completion phrase.
The completion condition must be read from machine-generated acceptance artifacts.
StopFailure
Record API errors, authentication failures, rate limits, and provider failures.
Write structured recovery evidence. StopFailure cannot block, continue, or restart the terminated session.
6. Strategy-escalation rule
Do not repeatedly make small variations of the same failed fix.
Record every significant failure in FAILURE_LEDGER.jsonl with:
failure class;
symptom;
root-cause hypothesis;
attempted correction;
evidence;
result;
affected gates.
Escalate as follows:
First failure of a class
Fix the direct demonstrated cause and add a discriminating regression test.
Second failure of the same class
Stop local patching.
Identify the shared structural cause and review the relevant architecture boundary.
Third failure of the same class
Generate at least three materially different approaches.
Assign independent agents to falsify each approach.
Do not choose the approach that merely requires the smallest diff. Choose the simplest approach that removes the failure class.
Fourth failure of the same class
Revert to the last proven checkpoint.
Replace or bypass the failing subsystem.
Do not continue accumulating patches around the same design.
A new fix must explain why it eliminates the failure class rather than only the current example.
7. /goal and scheduled reassessment
Use the built-in /goal continuation mechanism together with the existing verified Stop hook. Do not install, imitate, or depend on Ralph.
The repeated instruction must be:
Read the durable run state, identify the highest-leverage unmet completion gate, execute the next critical-path action, test it, update the durable state, and continue.
Do not merely repeat the entire original prompt without reading the current state.
Use a finite per-session iteration limit to prevent uncontrolled infinite token consumption.
Reaching the iteration limit is not completion. Before the session ends:
update HANDOFF.md;
record the next exact action;
commit or safely preserve all valid work;
cause the external supervisor to resume the same session or launch the next run.
Use /loop only as a secondary reassessment mechanism.
A scheduled loop may periodically ask:
Re-read the durable state. Verify that active work remains on the highest-leverage blocker. Inspect all background jobs for progress. Redirect the run if it has drifted.
Do not rely on /loop to detect a hung command.
8. External restart protocol
Run Claude Code under an external supervisor whenever possible.
The supervisor must:
capture the session ID or stable session name;
detect an unexpected session exit immediately;
inspect ACCEPTANCE_STATUS.json;
restart or resume when the status is not PASS;
feed the recovery prompt from HANDOFF.md;
preserve the same branch and worktree;
avoid starting duplicate lead sessions;
enforce a maximum restart rate;
log every restart.
Use an API-triggered routine, background-agent supervisor, CI workflow, or local process supervisor where available.
A periodic fallback restart may run hourly and must run no less frequently than every four hours, but event-driven restart is preferred.
Do not create two lead agents editing the same branch after a restart.
9. Background-job protocol
No background process may be launched without registration in:
.agent-run/BACKGROUND_JOBS.json
Every job record must include:
job ID;
PID;
process-group ID;
exact command;
working directory;
Git SHA;
configuration and prompt hashes;
start time;
hard deadline;
no-progress deadline;
expected units;
completed units;
heartbeat path;
progress path;
stdout and stderr paths;
artifact directory;
owning phase;
whether its result is acceptance evidence.
Every background process must:
emit a heartbeat at least every 30 seconds;
emit progress after every meaningful unit;
use per-operation timeouts;
use per-scene or per-branch timeouts;
have a total wall-clock timeout;
run in its own process group;
write partial progress atomically;
preserve diagnostic logs on failure.
The watchdog must poll every 30–60 seconds.
It must distinguish:
alive and progressing
alive but slow
CPU spinning
network request active
blocked with no activity
dead process
hard timeout
no-progress timeout
A process being alive is not evidence that it is healthy.
The watchdog must never merely wait for completion.
When a job stalls:
capture process state;
capture CPU usage;
capture recent logs;
capture stack traces where possible;
capture the last completed unit;
terminate the complete process group;
record a structured failure;
return control to the lead;
diagnose the root cause;
restart only after correction or a bounded transient retry.
Do not allow a job to remain on one scene, branch, or agent for hours without explicit progress.
10. Parallel work while tests run
Classify every test run before launching it.
Exploratory run
While an exploratory test runs, Claude may work on unrelated tasks only when:
the work occurs in a separate worktree;
it does not change the code under test;
it does not write into the run’s artifact directory;
the run is not later represented as final evidence for changed code.
Frozen acceptance run
During a frozen acceptance run:
do not modify production code;
do not modify prompts;
do not modify evaluation inputs;
do not modify evaluator logic;
do not merge changes into the tested branch;
do not allow old processes to write to the new artifact directory.
Claude may perform read-only analysis or documentation against the frozen SHA.
If any relevant code or prompt changes:
abort the complete batch
mark all batch artifacts invalid
create a new frozen SHA
restart the complete batch
For 100-agent, 1,000-agent, full-corpus, and final acceptance runs, this frozen rule is mandatory.
11. Test-harness validation
A passing test suite is not sufficient evidence when the test harness itself may be wrong.
For every load-bearing test or metric:
prove that it fails against the known-bad implementation;
prove that it passes after the fix;
test the evaluator independently;
test artifact tampering;
test missing files;
test stale SHAs;
test mixed-version artifacts;
test dead assertions and unreachable test branches.
Every production defect found by a corpus or live run must receive a discriminating regression test.
Do not claim that the test suite proves behavior it has never demonstrated it can detect.
12. Periodic architecture reset
After every:
three related failed fixes;
newly discovered critical defect;
major corpus invalidation;
repeated hang;
or phase lasting substantially longer than planned,
run a first-principles checkpoint:
restate the product invariant;
identify the authoritative owner of the failing responsibility;
ask whether two systems are competing for that responsibility;
identify whether the failure is caused by missing structure or excess structure;
consider deletion, replacement, or bypass before adding another patch;
ask at least one independent agent for a materially different approach;
update ARCHITECTURE.md and DECISIONS.md.
Do not preserve a failing architecture because substantial time has already been invested in it.
13. Highest-leverage reviewer
Keep one read-only reviewer responsible only for strategic drift.
At every phase boundary it must answer:
Is the current work on the critical path?
Does this change unblock a mandatory gate?
Is the team fixing a root cause or a symptom?
Is complexity increasing faster than demonstrated capability?
Is a simpler upstream component already available?
Is the run optimizing for impressive activity instead of completion?
Should any current work be stopped or reverted?
A finding that the run has drifted into low-leverage work must immediately return control to the lead for reprioritization.
14. Provider and transient failures
Provider errors must not invalidate correct code, but they must not be hidden.
For connection errors, rate limits, and transient provider failures:
use bounded exponential backoff;
cap the retry count;
preserve completed branch results;
do not treat a provider failure as a simulated outcome;
restart the failed unit only when branch independence permits it;
rerun the complete frozen batch when the acceptance protocol requires identical execution conditions.
If the provider remains unavailable, record EXTERNAL_BLOCKER only after direct health checks and bounded retries demonstrate that autonomous progress is impossible.
15. Context management
Do not allow the main context to become an unstructured record of every log line.
Persist detailed evidence to files.
Keep the main context focused on:
goal;
architecture;
current phase;
critical path;
latest evidence;
current blocker;
next decision.
Before compaction, write a complete handoff.
After compaction, verify the new context against the durable run state before taking action.
Resume existing specialist agents when continuing the same investigation rather than repeatedly starting new agents without their previous context.
16. Final completion enforcement
Before declaring completion:
freeze one final commit;
verify a clean tree;
verify upstream integrity;
run the complete acceptance suite from the beginning;
run all required adversarial reviewers;
resolve every verified critical finding;
regenerate machine-readable acceptance status;
have the final adjudicator read the actual artifacts;
require:
ACCEPTANCE_STATUS.json.overall == "PASS"
only then permit the Stop hook to release the session.
Do not finish with a list of remaining critical issues.
Do not ask me whether to fix the next issue.
Fix it, test it, update the run state, and continue.

Architectural replacement, not incremental runtime extension
This implementation is not an incremental addition to the existing SWORLDMODEL-GROUND-UP simulation runtime.
It is a replacement of the underlying execution architecture using the working upstream Concordia and AgentSociety 2 systems.
The intended production path is:
SWORLDMODEL decision and world inputs
        ↓
Concordia local simulation
        ↓
AgentSociety branch orchestration where distribution is required
        ↓
SWORLDMODEL outcome comparison and recommendation
Do not begin with the current SWORLDMODEL runtime and insert Concordia or AgentSociety components into it.
Do not preserve an existing SWORLDMODEL subsystem merely because it already exists.
Preserve or port a SWORLDMODEL component only when it owns product-specific functionality that Concordia and AgentSociety do not already provide.
Initial responsibility ownership
Use this division initially:
Responsibility
Initial owner
Local simulation runtime loop
Concordia engine
Actor observation lifecycle
Concordia
Actor action lifecycle
Concordia EntityAgent
Local action resolution
Concordia Game Master
Actor memory and components
Concordia
Local shared narrative state
Concordia Game Master memory
Outer distributed orchestration
AgentSociety 2
Initial whole-branch persistence and recovery 
AgentSociety workspaces storing complete Concordia checkpoints


LLM concurrency
AgentSociety dispatcher
Infrastructure tracing and failure isolation
AgentSociety 2
Starting-world compilation
Existing SWORLDMODEL compiler
Evidence input and grounding boundary
SWORLDMODEL
Counterfactual branching and comparison
New SWORLDMODEL layer
Behavioral calibration
Later pass

Architectural authority clarification
This ownership table defines the new production architecture, not merely a set of components to add to the existing SWORLDMODEL runtime.
Regardless of which Git branch is used for implementation, do not use the unfinished SWORLDMODEL semantic runtime as the execution foundation. It may be inspected for useful compiler, evidence, contract, evaluator, and test logic, but Concordia must replace its local runtime, actor lifecycle, memory, and world-resolution responsibilities.
There must be one authoritative implementation for each responsibility:
one local runtime: Concordia;
one live actor-memory system inside each branch: Concordia;
one local action resolver: the Concordia Game Master;
one distributed job and concurrency layer: AgentSociety 2;
one counterfactual comparison layer: SWORLDMODEL.
Do not leave the old SWORLDMODEL runtime running underneath, beside, or after Concordia. Do not pass Concordia actions back through the old world resolver before they become real.
Existing SWORLDMODEL commands may wrap the new architecture, but the production call path must be:
DecisionProblem
→ load or compile CompiledDecisionWorld
→ initialize Concordia
→ apply one InterventionCandidate
→ run the complete Concordia branch
→ produce BranchResult
→ optionally schedule complete branches through AgentSociety
→ compare BranchResults
→ produce RecommendationResult

Create:
docs/engine_migration/OWNERSHIP_AND_REPLACEMENT_MAP.md

Classify each existing simulation-related SWORLDMODEL subsystem as:
KEEP
ADAPT
REPLACE
ARCHIVE
DELETE

The map must show that no replaced SWORLDMODEL runtime subsystem remains reachable from the new production entry point.
Important scale clarification
For individual and team simulations, one stock or minimally wrapped Concordia engine owns the complete local trajectory.
For the first distributed architecture, AgentSociety schedules complete, independent Concordia branches:
Candidate A → complete Concordia simulation
Candidate B → complete Concordia simulation
Candidate C → complete Concordia simulation

Concordia owns everything inside each branch. AgentSociety owns scheduling, bounded concurrency, tracing, failure isolation, checkpoint storage, and result collection around those branches.
Initially persist and recover each complete Concordia simulation as one checkpointed unit. Do not distribute individual Concordia actor turns across AgentSociety workspaces during this pass.
For societal infrastructure, prove that stock AgentSociety can run:
many independent Concordia branches;
100 concurrent or batched jobs;
1,000 lightweight scripted or shallow jobs;
bounded concurrency;
persistence and resume;
failure isolation;
complete result collection.
These are infrastructure tests only. They do not prove realistic societal behavior.
Do not build during this pass:
causal partitions;
household or community partition systems;
cross-partition world synchronization;
distributed Game Masters;
individual Concordia actor reconstruction through AgentSociety;
one global Game Master containing every societal agent.
Actor-level distribution and societal partitioning are later gated architecture work. Implement them only after the individual and team best-action system works and measured evidence shows that complete-branch execution is insufficient.

Non-negotiable upstream-code preservation rule
The most important engineering requirement is to preserve Concordia and AgentSociety’s working code rather than loosely reimplementing their ideas.
Do not copy selected source files into rewritten SWORLDMODEL equivalents.
Preserve each upstream project as a complete, unchanged unit using the safest method supported by the actual repositories:
Prefer exact Git dependencies pinned to immutable commit SHAs when package structure supports this cleanly.
Use Git submodules or complete vendored snapshots when local source availability is necessary.
Preserve original package structure, imports, tests, examples, notices, and licenses.
Do not edit upstream source during the initial integration.
Do not monkey-patch upstream internals.
Do not recreate upstream classes from memory.
Do not silently copy an upstream class and modify it.
Do not depend on an unpinned branch or floating package version.
Create:
third_party/
  UPSTREAM_LOCK.json
  THIRD_PARTY_NOTICES.md
  INTEGRATION_METHOD.md
  PATCHES.md

UPSTREAM_LOCK.json must record:
repository;
exact commit SHA;
package version when applicable;
installation method;
checksum or integrity information;
license;
date imported.
PATCHES.md must initially state that no upstream modifications exist.
A fork or patch is permitted only when:
the required behavior is impossible through available interfaces;
the exact limitation is demonstrated with a failing contract test;
the smallest possible patch is isolated;
the upstream source remains otherwise intact;
the patch is documented line by line;
an adversarial reviewer agrees it is unavoidable.
First mandatory task: full three-repository audit
Before implementation, create:
docs/engine_migration/
  UPSTREAM_AUDIT.md
  SWORLD_CURRENT_STATE.md
  OWNERSHIP_MAP.md
  INTEGRATION_PLAN.md
  RISK_REGISTER.md
  ACCEPTANCE_GATES.md

Audit Concordia
Trace the real production path for:
engine startup;
sequential and simultaneous engines;
Game Master creation;
observation generation;
actor selection;
ActionSpec;
EntityAgent.observe;
EntityAgent.act;
component pre/post lifecycle;
Game Master event resolution;
memory updates;
scene transitions;
state serialization and restoration;
termination;
logging;
model calls;
concurrency assumptions.
Identify which exact public components can be used unchanged.
Identify every place where the default Game Master can:
invent facts;
decide another actor’s voluntary choice;
choose observers;
determine mechanical feasibility;
declare terminal results;
silently introduce causal events.
Do not remove those powers before first establishing the unmodified working baseline. Document them as later restrictions.
Audit AgentSociety 2
Trace the real production path for:
AgentBase;
agent creation;
workspace structure;
reconstruction from workspace;
state restoration;
agent step;
state persistence;
Ray workers;
batching;
asynchronous calls;
model dispatch;
global concurrency limiting;
ServiceProxy;
environment services;
EnvBase;
typed tools;
tracing;
replay;
checkpointing;
failure isolation;
token accounting;
shutdown and resume behavior.
Determine the safest way to use these exact components without replacing Concordia’s local actor and Game Master lifecycle.
Explicitly compare two integration levels:
Branch-level execution
AgentSociety distributes complete Concordia counterfactual simulations.
This should be implemented first because it preserves stock Concordia most directly.
Actor- or partition-level execution
AgentSociety reconstructs and executes Concordia-backed actors or local Concordia partitions.
This is needed for societal infrastructure but is more invasive.
Implement it only after branch-level integration is stable.
Audit SWORLDMODEL-GROUND-UP
Classify every existing component as:
retain unchanged;
wrap;
reuse later;
quarantine as legacy;
replace;
delete only after proven unused.
The existing world compiler is currently stronger than the runtime. Preserve its working production route and evidence boundary unless an integration test proves a change is required.
Do not assume the existing persistent runtime is reliable merely because it has extensive intended mechanics.
Audit:
the production compiler route;
current schema;
evidence-package boundary;
visibility handling;
private actor context;
terminal-resolution representation;
test fixtures;
current runtime;
ledger;
replay;
checkpointing;
artifacts;
known failure reports;
existing acceptance datasets.
Preserve existing compiler tests and artifacts as regression coverage.
Do not delete the old runtime during this pass. Move superseded production paths behind an explicit legacy flag only after the new engine passes every acceptance gate.
Architecture to implement
Create a new best-action execution path without initially destroying the existing route.
Recommended high-level package shape:
sworldmodel/
  decision/
    problem.py
    candidates.py
    success_criteria.py

  compilation/
    existing_compiler_adapter.py
    compiled_decision.py

  backends/
    concordia_local/
      builder.py
      actors.py
      game_master.py
      state.py
      runner.py

    agentsociety/
      branch_executor.py
      actor_workspace.py
      distributed_executor.py
      service_proxy.py
      partition_runner.py

  counterfactuals/
    snapshot.py
    branch.py
    manager.py
    comparison.py

  outcomes/
    metrics.py
    evaluator.py
    ranking.py

  reporting/
    recommendation.py
    trace_report.py

  legacy/
    existing_runtime/

Use the actual repository layout where a different structure is cleaner, but preserve the separation of responsibilities.
Fixed SWORLDMODEL-owned contracts
Do not make either upstream repository define the product’s external semantics.
Create small, stable, versioned contracts owned by SWORLDMODEL.
At minimum:
DecisionProblem
decision owner
desired outcome
success criteria
constraints
time horizon
relevant context
candidate interventions, when supplied
candidate-generation permission

CompiledDecisionWorld
actors
actor-private starting context
shared starting context
starting events
cutoff
success criteria
available intervention insertion point
compiler provenance

InterventionCandidate
candidate ID
natural-language summary
exact action or policy to introduce
decision owner
timing
constraints
provenance

SimulationSnapshot
starting world state
actor states
Game Master state
random seed state
model configuration
compiler artifact hash

BranchResult
candidate ID
terminal world state
event or narrative trace
explicit outcome metrics
success status
infrastructure errors
token and runtime statistics
artifact paths

RecommendationResult
best-performing tested candidate
ordered candidate results
metric differences
downside outcomes
run limitations
validation status

Code owns these schemas.
The LLM may generate semantic values inside them but must not generate a different schema for each scenario.

Contract-generation and validation rules
The fixed contracts must not depend on an LLM correctly writing arbitrary JSON, inventing identifiers, or remembering the schema.
Use this exact boundary:
Code creates the contract structure
        ↓
The LLM fills only explicitly allowed semantic fields
        ↓
Code performs strict schema validation
        ↓
Code performs separate real-world and scenario validation
        ↓
Only a fully valid object may enter the simulation

Code-owned fields
Code, not the LLM, must create and control:
contract type;
schema version;
candidate IDs;
actor IDs;
branch IDs;
world IDs;
timestamps;
artifact paths;
hashes;
model configuration;
random seeds;
provenance records;
success and error status;
token and runtime statistics;
references between stored objects.
The LLM must never guess an ID from a person’s name or create references to objects that have not been registered by code.
LLM-owned fields
The LLM may generate only bounded semantic content such as:
a natural-language action;
an action summary;
relevant context extracted from supplied material;
qualitative constraints;
proposed timing within allowed options;
candidate intervention content.
Use native structured output, tool calling, or function calling where supported. Do not ask the LLM to freely print a complete contract as unvalidated text.
Strict schema validation
Every contract must:
use strict types;
reject unknown fields;
reject missing required fields;
reject invalid enum values;
reject invalid references;
reject incorrect contract versions;
avoid silent type coercion;
have a canonical serialized form;
round-trip through serialize → deserialize without information loss.
Do not silently repair malformed LLM output.
When output is invalid:
record the original output and exact validation errors;
optionally allow one bounded, explicitly logged correction attempt using those errors;
reject the object or fail the branch if it remains invalid;
never continue with a partially valid or guessed object.
Separate syntax from meaning
Passing schema validation does not mean an action is valid in the simulated world.
After schema validation, perform semantic validation including:
the decision owner exists;
referenced actors exist;
the actor is allowed to attempt the action;
timing is inside the simulation horizon;
required targets and resources exist;
the intervention does not modify another branch;
the action does not directly declare another actor’s voluntary decision;
the action is compatible with declared constraints;
the success criterion is measurable from the resulting trace or world state.
An object with correct formatting but impossible or unauthorized meaning must be rejected explicitly.
Contract minimality
Keep contracts as small as possible.
For every field, document:
why it is required;
who creates it;
who may modify it;
where it is validated;
whether it is persisted;
whether it affects branch identity or reproducibility.
Do not add fields merely because they may be useful later. Add a field only when an existing implementation or acceptance test requires it.
Snapshot completeness
SimulationSnapshot must capture every piece of state capable of changing branch results, including:
Concordia actor component state;
actor memory;
Game Master memory and state;
current scene or phase;
pending events;
current simulation time;
model configuration;
random-number-generator state;
intervention insertion point;
compiler artifact hash;
relevant AgentSociety workspace state.
Create an explicit snapshot manifest listing every serialized component.
A snapshot is incomplete unless this test passes:
run to checkpoint
→ save snapshot
→ continue to result
→ restore snapshot separately
→ continue again
→ obtain the same deterministic result and trace

Adapter correctness
Every translation between SWORLDMODEL, Concordia, and AgentSociety must have round-trip and information-preservation tests.
Required checks:
SWOR object
→ Concordia or AgentSociety representation
→ SWOR object

The final SWOR object must preserve all meaningful information.
Adapters must not silently:
drop private context;
merge private and shared context;
rename actors using ambiguous display names;
remove provenance;
alter timing;
change success criteria;
substitute defaults for missing values;
convert one branch’s identifiers into another branch’s identifiers.
When an upstream representation cannot preserve a required field, retain it in an explicit SWORLDMODEL sidecar owned by the adapter rather than discarding it.
Contract versioning
Every persisted contract must contain an explicit schema_version.
Rules:
saved artifacts must never be silently interpreted as a newer schema;
incompatible versions must fail clearly;
migrations must be explicit, deterministic, and tested;
migrations must preserve the original artifact;
no migration may invent missing semantic information;
current code must document which versions it can read and write.
Required contract tests
Before contracts are used in a live simulation, test:
valid object acceptance;
missing field rejection;
unknown field rejection;
incorrect type rejection;
fabricated ID rejection;
cross-branch reference rejection;
unauthorized action rejection;
impossible timing rejection;
round-trip serialization;
adapter round-trip preservation;
snapshot restore equivalence;
schema-version mismatch;
malformed LLM output;
valid syntax with invalid meaning;
one contract type accidentally supplied where another is expected.
The fixed contracts are complete only when malformed or semantically invalid objects fail clearly before they can affect simulation state.

Minimal compiler connection
Do not redesign the world compiler during this pass.
Add a thin adapter that maps the existing compiled scene into the minimum Concordia initialization data:
actors;
private contexts;
shared context;
starting events;
cutoff;
natural-language success criteria.
Add a lightweight DecisionProblem route above the existing compiler.
For initial engineering tests, support:
manually supplied compiled fixtures;
user-supplied candidate actions;
a minimal LLM candidate generator using one fixed schema.
The full dynamic action-search algorithm is not part of this engineering pass.
Candidate generation quality is not a completion criterion yet.
The ability to run and compare candidates correctly is mandatory.

Exact compiler-to-Concordia mapping requirement
The compiler/runtime boundary is a critical integration risk. Do not implement it through informal prompt translation or an LLM-generated conversion.
Before writing the adapter:
Pin the exact Concordia and SWORLDMODEL commits.
Inspect the actual Concordia constructors, prefab parameters, initializer interfaces, memory APIs, scene APIs, and engine startup path.
Create:
docs/engine_migration/COMPILER_TO_CONCORDIA_MAPPING.md

For every source field, document:
exact SWORLDMODEL source path;
exact Concordia destination class and parameter;
whether the mapping is direct, transformed, or stored in a SWORLDMODEL sidecar;
visibility rules;
who owns the value;
whether it is persisted;
validation performed;
tests proving the mapping.
Use this initial mapping unless the pinned source code proves a different destination is required:
SWORLDMODEL source
Required destination
actors[i].name
Concordia actor instance name; stable actor ID remains code-owned
actors[i].private_context
Only that actor’s private initializer context or private initial memories
shared_context
Concordia shared initial memory; do not duplicate it into multiple destinations without justification
starting_events[i].description
Game Master initial history plus actor observations
starting_events[i].visible_to
Code-owned actor lookup controlling exactly which actors receive the observation
starting_events[i].time
Explicit run-time metadata or time component; never discard it silently
resolution
External SWORLDMODEL outcome evaluator only; never actor memory, shared memory, or Game Master premise
start time
SWORLDMODEL run metadata and any verified Concordia time component
cutoff
External run limit; do not treat max_steps as an exact time equivalent
intervention candidate
Injected at one explicit code-owned intervention boundary after the base snapshot is frozen
success criteria
External evaluator; not shown to actors or Game Master unless the scenario naturally makes the goal observable
compiler provenance
SWORLDMODEL sidecar metadata
schema and artifact hashes
SWORLDMODEL sidecar metadata

The adapter must be deterministic code. It must not call an LLM, paraphrase fields, summarize context, infer missing fields, guess actor identities, or silently insert defaults.
Required intermediate object
Create one code-owned ConcordiaInitializationPlan containing only the exact information needed to construct the pinned Concordia runtime:
actor instance configurations
actor-private initialization data
shared initialization data
Game Master configuration
neutral starting premise
initial observations by actor ID
Game Master initial events
run limits
intervention insertion specification
external evaluator specification
compiler provenance

The adapter path must be:
CompiledDecisionWorld
→ deterministic ConcordiaInitializationPlan
→ validated Concordia objects

Do not map compiler output directly through scattered construction calls across the codebase.
Information-leak tests
Use unique canary strings to prove:
PRIVATE_ALICE_CANARY appears only in Alice’s initial context and prompts;
PRIVATE_BOB_CANARY appears only in Bob’s initial context and prompts;
SHARED_CANARY is available to every intended actor;
an event visible only to Alice never appears in Bob’s context;
RESOLUTION_CANARY appears in zero actor prompts and zero Game Master prompts;
one branch’s intervention never appears in another branch;
compiler provenance never enters actor reasoning unless explicitly intended.
Mapping correctness tests
The adapter is incomplete until tests prove:
every compiler field is either mapped or explicitly retained in a sidecar;
no source field is silently discarded;
actor names resolve to stable code-owned IDs;
unknown visible_to names fail before simulation;
private and shared context remain separate;
starting-event order and timestamps are preserved;
the base world is identical before different interventions are inserted;
outcome criteria are evaluated only from the resulting trace or state;
manually written fixtures and compiler-produced fixtures initialize equivalent Concordia worlds;
the same compiled input produces the same initialization plan under deterministic settings.
Initial integration order
Implement in this order:
Manually written CompiledDecisionWorld fixture into Concordia.
Freeze the successful Concordia initialization and trajectory tests.
Implement the deterministic compiler adapter.
Run the same fixture through the SWORLDMODEL compiler output.
Compare both resulting ConcordiaInitializationPlan objects.
Only then enable natural-language compilation in the end-to-end route.
Do not redesign the existing world compiler during this integration pass unless a failing mapping test proves that its existing fields cannot express required initialization information.

Hard gate: prove Concordia independently before compiler integration
Before connecting any SWORLDMODEL compiler code, prove that the simulation engine works using a literal, manually written fixture committed to the test suite.
During this phase:
do not import or call the SWORLDMODEL compiler;
do not use evidence retrieval;
do not generate actors or world fields with an LLM;
do not use AgentSociety;
do not generate candidate interventions;
manually specify two actors, their private context, shared context, one starting event, a cutoff, and one external success criterion;
use Concordia’s real actor, memory, Game Master, and engine code;
prove observation → actor attempt → Game Master resolution → second actor response → persistent state → outcome trace works end to end.
Run it first with deterministic test models, then with several live-model smoke runs when credentials are available.
This phase passes only when:
the scenario completes reliably on three clean runs;
private information remains private;
actor memory persists across turns;
the Game Master produces a traceable resolved event;
the second actor receives an actual turn;
the outcome is read from the resulting trace;
no compiler package is imported anywhere in the execution path.
Freeze this working baseline before beginning compiler integration.
Afterward, run a second manually written scenario with different actors and a different type of social interaction to prove the integration is not hardcoded to the first example.
Only after both manual fixtures pass may the compiler-to-Concordia adapter be implemented.

Concordia local backend
First implement a working local backend using the stock Concordia runtime as directly as possible.
The path must be:
CompiledDecisionWorld
        ↓
Construct Concordia actors
        ↓
Initialize actor-private memory/components
        ↓
Construct Concordia Game Master
        ↓
Insert one intervention candidate
        ↓
Run stock or minimally wrapped Concordia engine
        ↓
Capture complete resulting state and trace

Initially preserve Concordia’s:
engine loop;
actor observation lifecycle;
actor action lifecycle;
component system;
memory system;
Game Master resolution;
local narrative state.
Do not prematurely rebuild the ideal authoritative resolver.
Immediate minimum agency guard
Once the unmodified baseline works, add one thin post-resolution or pre-commit guard without rewriting Concordia internals:
The Game Master may describe mechanical or nonvoluntary consequences, but it may not permanently commit a voluntary decision for a different actor without giving that actor its own turn.
Examples of voluntary decisions:
replying;
agreeing;
voting;
purchasing;
accepting;
rejecting;
signing;
supporting;
committing;
choosing what to say.
Bad:
Beckett sends the proposal, and Tim agrees to another meeting.

Required split:
Beckett sends the proposal.
Tim receives or becomes able to observe it.
Tim receives his own actor turn.
Tim decides whether and how to respond.

Implement this as an adapter, validator, event splitter, or agency-check component based on the actual Concordia interfaces.
Do not fork the entire Game Master.
AgentSociety integration sequence
The first integration must use AgentSociety in the narrowest way that preserves both upstream systems.
Do not begin by distributing individual Concordia actors or splitting one society across multiple Game Masters.
First use AgentSociety to run complete, self-contained Concordia simulations as independent jobs.
Stage A: branch-level distributed execution
Implement this first.
Each counterfactual candidate is one complete Concordia simulation:
Candidate A
→ complete Concordia simulation
→ BranchResult A

Candidate B
→ complete Concordia simulation
→ BranchResult B

Candidate C
→ complete Concordia simulation
→ BranchResult C

AgentSociety owns:
job scheduling;
worker execution;
bounded concurrency;
LLM dispatch and rate limiting;
tracing;
failure isolation;
token and runtime accounting;
result collection.
Concordia continues to own everything inside each branch:
actors;
actor memories;
observations;
actor turns;
Game Master;
event resolution;
local simulation loop;
local simulation state.
Use AgentSociety’s actual supported worker, dispatcher, tracing, and failure-handling interfaces.
Do not rewrite AgentSociety’s worker system.
Do not edit AgentSociety source unless a failing contract test proves its supported interfaces are insufficient.
Do not reconstruct individual Concordia actors through AgentSociety during this stage.
This stage passes only when:
one Concordia branch runs successfully through AgentSociety;
multiple branches run concurrently;
one failed branch does not stop the others;
local and distributed runs return equivalent structured results under deterministic test models;
concurrency limits are respected;
traces, token use, runtime, and errors are recorded;
Concordia’s internal runtime remains unchanged.
Stage B: whole-branch persistence and recovery
Persist the complete Concordia simulation branch as one checkpointed unit.
Do not initially persist and reconstruct every Concordia actor separately.
The lifecycle must be:
AgentSociety starts branch
        ↓
Construct complete Concordia simulation
        ↓
Run to checkpoint or completion
        ↓
Save the complete branch state
        ↓
Release the branch
        ↓
Restore the complete branch when required
        ↓
Continue the same Concordia simulation

The checkpoint must include every state item required by Concordia’s real checkpoint or serialization interfaces, including where supported:
all actor states;
all actor memories;
Game Master state and memory;
current simulation step;
scene state;
pending observations or events;
model configuration;
random state;
intervention identity;
compiler artifact identity.
Prefer Concordia’s existing complete simulation checkpointing and restoration path.
AgentSociety should store, locate, schedule, and restore that checkpoint without translating its internal contents unnecessarily.
Treat the Concordia checkpoint as an opaque versioned artifact wherever possible.
Do not create a second handwritten representation of Concordia memory or component state.
If Concordia cannot completely serialize a branch, document the exact missing state and add only the smallest required sidecar owned by SWORLDMODEL.
This stage passes only when:
run to checkpoint
→ save
→ continue to result A

restore the checkpoint separately
→ continue to result B

produces the same deterministic trace and result.
Stage C: infrastructure-only scale proof
For this implementation pass, prove AgentSociety scaling without yet inventing a full societal partition system.
Use one or both of these safe tests:
Run many independent Concordia simulations concurrently.
Run many simple AgentSociety scripted or shallow agents using AgentSociety’s existing environment and workspace patterns.
Demonstrate:
100 concurrent or batched jobs;
1,000 lightweight scripted or shallow jobs;
bounded concurrency;
workspace or checkpoint persistence;
failure isolation;
interruption and resume;
aggregate result collection;
no duplicated or lost jobs;
clean shutdown.
This proves infrastructure capacity only.
It does not prove realistic societal simulation.
Do not create during this stage:
household partitioning;
community partitioning;
cross-partition causal synchronization;
a global shared-world consistency system;
individual Concordia actor reconstruction through AgentSociety;
a distributed multi-Game-Master social world.
Later gated stage: actor-level and societal partition execution
Actor-level persistence and societal partitions are later architecture work.
Implement them only if measured evidence shows that complete-branch execution cannot support the required societal use cases.
Before beginning that work, create a separate design and acceptance review covering:
why whole-branch execution is insufficient;
how the population is divided;
which Game Master owns each event;
how events cross partitions;
how shared facts stay consistent;
how simultaneous changes are ordered;
how actors are activated;
how state conflicts are detected;
how the distributed result is validated.
No societal partition implementation may begin merely because it seems useful for future scale.
It must be justified by a concrete failed requirement that the simpler architecture cannot satisfy.
Integration principle
Use the simplest boundary possible:
SWORLDMODEL creates counterfactual branches
        ↓
AgentSociety schedules complete branches
        ↓
Concordia runs each complete local simulation
        ↓
AgentSociety collects BranchResults
        ↓
SWORLDMODEL compares measured outcomes

The first production architecture should distribute complete simulations, not individual actor turns.
Preserve the exact working Concordia and AgentSociety execution paths before attempting deeper integration.

Best-action counterfactual manager
Implement a new SWORLDMODEL counterfactual manager.
For every candidate:
Compile or load the starting world once.
Freeze the base snapshot.
Clone the same world, actors, Game Master state, model configuration, and seeds.
Apply exactly one candidate intervention.
Run the branch independently.
Store its trace and resulting state.
Evaluate explicit success criteria.
Compare branch outcomes.
Hard invariants:
no branch may modify another branch;
no branch may retrieve another branch’s memories;
identical candidates under deterministic test actors must produce identical results;
different candidates must differ initially only at the intervention boundary;
all branches must use the same base evidence and hidden-state assumptions;
branch failures must be reported rather than silently replaced.
Outcome evaluation
The final recommendation must be computed from what happened in the simulation.
Use explicit evaluators such as:
whether a reply was sent;
whether a meeting was scheduled;
whether a vote passed;
whether a commitment was made;
how many purchases occurred;
total cost;
total revenue;
number of affected people;
user-defined success criteria.
For this engineering pass, simple manually defined metrics are acceptable.
A final LLM may explain the results but may not override them.
Prohibited:
The final judge thinks Candidate B sounded most persuasive.

Required:
Candidate B produced the highest measured success under the declared criteria.

When multiple criteria conflict, return the measured tradeoff. Do not invent arbitrary weights unless the user explicitly supplied them.

Frozen manual best-action fixtures
Before connecting the natural-language world compiler or candidate generator, prove the complete best-action pipeline using manually written, version-controlled fixtures.
Claude must not invent the acceptance scenarios during implementation.
Store them under:
tests/fixtures/best_action/
  individual_reply.yaml
  team_commitment.yaml
  population_offer.yaml

Each fixture must directly provide:
fixture ID
manually written CompiledDecisionWorld
manually written InterventionCandidates
explicit code-owned outcome evaluator
deterministic test expectations
live-model realism assertions

The fixture-loading path must be:
Manual fixture
→ strict schema validation
→ CompiledDecisionWorld
→ frozen base snapshot
→ candidate branches
→ Concordia simulations
→ trace-based outcome evaluation
→ RecommendationResult

During these tests:
do not call the SWORLDMODEL compiler;
do not call evidence retrieval;
do not generate actors with an LLM;
do not generate candidate actions with an LLM;
do not let an LLM choose the winner;
do not change the fixtures after the final acceptance run begins.
Minimal fixture format
Use a small human-readable YAML or equivalent strictly validated format:
fixture_id: individual_reply

world:
  start_time: "2026-08-03T14:00:00Z"
  cutoff: "2026-08-10T14:00:00Z"

  actors:
    - id: sender
      name: Alex
      private_context: >
        Alex wants to arrange an introductory meeting with Morgan.

    - id: recipient
      name: Morgan
      private_context: >
        Morgan is busy, has no prior relationship with Alex, dislikes
        pressure and generic pitches, but responds to short messages
        containing clear relevance and a low-effort request.

  shared_context: >
    Alex has Morgan's email address. No message has been sent yet.

  starting_events: []

candidates:
  - id: long_generic
    actor_id: sender
    time: "2026-08-03T14:05:00Z"
    action: >
      Send a long general description of Alex's background and ask for
      a one-hour meeting.

  - id: concise_relevant
    actor_id: sender
    time: "2026-08-03T14:05:00Z"
    action: >
      Send a short message explaining one concrete reason the work is
      relevant to Morgan and ask for a fifteen-minute conversation.

  - id: urgent_pressure
    actor_id: sender
    time: "2026-08-03T14:05:00Z"
    action: >
      Send an urgent message implying that Morgan should respond today.

evaluator:
  primary_metric: recipient_reply_sent
  secondary_metrics:
    - meeting_scheduled
    - explicit_decline

Code must create all branch IDs, hashes, actor references, timestamps, statuses, and artifact paths.
The fixture contains semantic facts and candidate actions only.
Required fixture 1: individual reply
Use the exact basic structure above.
Purpose:
prove two-person simulation;
prove intervention isolation;
prove that the recipient receives their own turn;
prove that the Game Master cannot write the recipient's response;
prove that an actual reply event is required for success.
Candidates:
long, generic message with a large request;
concise, relevant message with a small request;
urgent, pressuring message.
Primary outcome:
Did the recipient actually send a reply?

Secondary outcomes:
Was a meeting scheduled?
Was there an explicit decline?
Was there no response by the cutoff?

Deterministic version
Use a scripted recipient only for the engineering test:
concise relevant message → positive reply;
long generic message → no reply;
urgent pressure message → explicit decline.
This scripted behavior is a test fixture only. It must never enter the production simulation logic.
The required result is:
concise_relevant ranks first

Live-model version
Run the same fixture using the normal Concordia actor.
Do not require the same candidate to win every stochastic run.
Require instead:
Morgan makes Morgan's own decision;
the decision refers to Morgan's stated incentives and constraints;
no branch receives information from another branch;
the resulting outcome is read from the trace;
no final judge overrides the measured outcome;
the trajectory contains no obviously impossible or contradictory behavior.
Required fixture 2: team commitment
Create one manually written five-person team:
proposal owner;
skeptical operations lead;
budget owner;
supportive product lead;
neutral team member.
The proposal requires an explicit declared decision rule:
The plan proceeds only if at least three members explicitly commit and
the operations lead does not exercise their declared implementation veto.

Test these candidates:
announce the full plan publicly and immediately request approval;
privately address the operations lead's workload concern, then present a limited pilot to the team;
request an immediate binding vote without addressing implementation concerns.
Measure only actual events:
explicit support commitments;
explicit opposition;
veto exercised;
pilot accepted;
final decision recorded.
The Game Master may not cast a vote, invent a commitment, or waive the veto for an actor.
The deterministic test version must define actor responses so Candidate 2 succeeds and the others do not.
The live-model version must test structural realism without requiring a fixed winner.
Required fixture 3: population infrastructure
Create a deliberately synthetic infrastructure test with 100 lightweight or scripted customer agents divided into three manually defined profiles.
Test three manually supplied offers.
Measure:
purchases;
non-purchases;
total revenue;
failures;
completed agent runs.
All customer rules must be explicit in the fixture and based only on stated budget limits and stated preferences.
This fixture proves:
aggregate branch comparison;
AgentSociety scheduling;
bounded concurrency;
result collection;
no duplicated agents;
no lost results.
It must be labeled:
SYNTHETIC INFRASTRUCTURE TEST — NOT A REALISTIC MARKET FORECAST

Do not use this result as evidence of societal realism.
Fixture immutability
Before implementation begins:
commit the three fixture files;
record their hashes;
record their expected deterministic results;
prevent implementation code from changing them silently.
During the frozen final evaluation:
fixture hashes must match;
expected outcomes must not be rewritten;
actor rules must not be weakened;
evaluator definitions must not be changed to match observed outputs.
Manual-fixture acceptance gates
The best-action counterfactual manager is not complete until:
all three fixtures load without importing the world compiler;
all candidates begin from the same base snapshot hash;
only the intervention differs between candidate branches;
deterministic runs produce the exact expected traces and rankings;
candidate order does not change results;
local and AgentSociety-distributed execution agree;
one failed branch does not affect other branches;
live-model traces preserve actor agency and information boundaries;
outcome evaluators read actual events or world state;
no LLM directly selects or overrides the winner;
every result clearly states whether it came from a deterministic test, live-model smoke test, or synthetic infrastructure test.
Later compiler gate
Only after the frozen manual fixtures pass may natural-language world compilation be enabled.
The compiler's first requirement is not to invent a new runtime format.
It must produce the same validated CompiledDecisionWorld structure already proven by the manual fixtures.
The compiler integration succeeds only when:
manually written fixture
and
compiler-produced equivalent fixture

create equivalent Concordia initialization plans and pass the same counterfactual tests.

No arbitrary quantitative social mechanics
Do not create invented mechanics such as:
persuasion += 0.4
trust -= 0.2
influence_weight = 0.75
likelihood_to_reply = 63

unless the number is:
explicitly supplied by the user;
grounded in data;
required for a mechanical test fixture;
or clearly labeled as a temporary synthetic infrastructure parameter that does not claim realism.
For social behavior during this pass:
actors should reason qualitatively from goals, beliefs, incentives, relationships, constraints, and observations;
voluntary decisions belong to actors;
mechanical quantities belong to code;
the Game Master resolves the local situation but must not act as a hidden scoring formula.
Numbers remain appropriate for:
time;
money;
quantities;
capacity;
counts;
explicit probabilities supplied by evidence;
concurrency;
resource limits;
deterministic test fixtures.
Required implementation phases
Phase 0: freeze and baseline
create migration branch;
record all SHAs;
run existing tests;
run available upstream smoke examples;
save baseline artifacts;
identify known current runtime failures;
do not change production routing yet.
Phase 1: dependency preservation and compatibility
pin complete upstream repositories;
establish one compatible environment;
preserve upstream source unchanged;
add license notices;
prove imports coexist;
prove minimal Concordia and AgentSociety examples run.
Phase 2: upstream contract tests
Create tests that independently prove:
Concordia:
actor observation works;
actor action works;
component lifecycle order is preserved;
Game Master resolution works;
memory persists;
state can be restored where supported.
AgentSociety:
workspace creation works;
reconstruction works;
execution works;
state persistence works;
concurrency limiting works;
one failed worker does not kill unrelated workers;
trace and token accounting work.
Do not add application logic until these pass.
Phase 3: decision and branch contracts
Implement the fixed SWORLDMODEL contracts and strict schema tests.
Phase 4: stock Concordia local baseline
Run one two-person compiled scenario end to end using Concordia.
Do not add AgentSociety yet.
Freeze this baseline.
Phase 5: minimum agency guard
Add the smallest possible protection against the Game Master committing another actor’s voluntary action.
Prove that the Concordia loop still works.
Phase 6: counterfactual branch manager
Run two manually supplied interventions from the same starting snapshot and compare explicit outcomes.
Phase 7: AgentSociety branch executor
Distribute complete Concordia branches through AgentSociety.
Prove local and distributed execution return equivalent structured results under deterministic test models.
Phase 8: Concordia actor workspace adapter
Persist and reconstruct Concordia actor state through AgentSociety workspaces.
Phase 9: individual vertical slice
Implement a complete message or persuasion decision:
Which of these messages most increases the chance of a second meeting?

The recipient must decide whether to reply.
The Game Master cannot pre-write the reply.
The outcome evaluator must read the actual resulting trace.
Phase 10: team vertical slice
Implement a 5–12 person decision involving:
private information;
authority;
a meeting;
private follow-up conversations;
commitments or votes;
a declared outcome.
The Game Master must not cast votes or make commitments on behalf of actors.
Phase 11: societal infrastructure proof
Prove:
100-agent run;
1,000-agent scripted or deliberately shallow run;
AgentSociety distributed execution;
bounded concurrency;
sparse activation;
persistent workspaces;
checkpoint/resume;
injected individual failures;
no duplicate or lost actions;
local partitions;
aggregate result collection.
This is an infrastructure test only.
Do not claim population realism.
Phase 12: frozen final acceptance run
Once code is ready:
Freeze the commit.
Run the entire mandatory test and evaluation suite without changing code.
If any test fails, end that evaluation batch.
Fix the code.
Freeze a new commit.
Restart the full evaluation suite from the beginning.
Do not make code changes midway through a batch and continue counting it as one successful run.
Mandatory acceptance gates
Claude may not call the implementation complete until every applicable gate passes.
A. Upstream integrity
Exact commit SHAs are recorded.
Upstream source is complete and unchanged.
No selected-file pseudo-fork exists.
PATCHES.md accurately lists every deviation.
Upstream smoke tests or runnable examples pass.
Integration code exists outside upstream packages.
Dependency installation is reproducible from a clean environment.
B. Baseline reliability
Existing compiler tests remain green.
Existing retained SWORLDMODEL tests remain green or failures are explicitly proven unrelated and replaced with equivalent coverage.
New tests pass on three consecutive clean runs.
No flaky test is ignored, retried until green, or marked expected failure without justification.
No silent exception swallowing exists in the core path.
Every branch failure produces a structured error artifact.
C. Individual simulation
The two-person scenario proves:
private context remains private;
shared context is shared;
observations reach only intended actors;
actor memory persists across multiple turns;
one actor cannot choose another actor’s voluntary response;
the Game Master cannot directly satisfy the success criterion by narration;
the trajectory reaches success, failure, cutoff, or explicit incomplete status;
artifacts contain the complete causal trace;
repeated executions do not fail mechanically.
Run at least:
deterministic scripted tests;
deterministic mock-model tests;
multiple live-model smoke runs when credentials are available.
D. Team simulation
The team scenario proves:
at least five actors;
private and shared interactions;
authority differences;
actor-owned votes or commitments;
persistent memory;
multiple rounds;
no omniscient actor context;
no Game Master-forced coalition;
explicit final outcome from actor/world events.
E. Counterfactual correctness
Every branch starts from the same frozen snapshot.
Only the intervention changes.
No state leaks between branches.
Identical interventions produce identical deterministic outcomes.
Candidate ordering does not change deterministic results.
Branches can run serially or in parallel.
The result ranking comes from explicit metrics.
A final LLM cannot override the ranking.
The system reports “best among tested candidates,” not an unsupported global optimum.
F. AgentSociety integration
AgentSociety’s real worker and dispatcher code is exercised.
Workspaces persist and reconstruct state.
Bounded concurrency is demonstrated.
Agent failures are isolated.
Token and runtime accounting are collected.
A distributed branch result matches a local result under deterministic models.
Shutdown and cleanup leave no corrupted state.
Checkpoint/resume works.
G. Societal infrastructure
A 100-agent shared or partitioned test succeeds.
A 1,000-agent scripted/shallow test succeeds.
Actors are not all activated every tick without cause.
Sparse activation can be inspected.
No action is dropped or duplicated.
Injected failures do not terminate unaffected partitions.
Aggregate outcomes equal the underlying recorded actions.
Cross-partition communication is explicit and traceable.
The system clearly labels this as infrastructure rather than calibrated societal simulation.
H. Simulation semantics
An adversarial reviewer must confirm:
actors reason from qualitative incentives, goals, beliefs, relationships, and constraints;
voluntary human decisions belong to the affected actor;
the Game Master is not an arbitrary final outcome decider;
no unexplained social weights were introduced;
no actor receives information it could not observe;
no outcome is counted unless it occurred in the trace or world state;
the system does not simulate irrelevant daily-life detail merely to appear realistic;
the simulation remains intervention-centered.
I. Operational robustness
Test:
clean installation;
cold startup;
repeated runs;
interruption;
resume;
one actor failure;
one branch failure;
malformed candidate;
malformed compiled input;
missing model credentials;
model timeout;
model malformed output;
Ray worker failure;
partial workspace corruption.
Failures must be explicit, bounded, and recoverable where possible.
J. Documentation
Produce:
docs/engine_migration/
  FINAL_ARCHITECTURE.md
  RESPONSIBILITY_OWNERSHIP.md
  UPSTREAM_COMPONENT_MAP.md
  IMPLEMENTATION_LOG.md
  TEST_MATRIX.md
  SOCIETAL_SCALING_PATH.md
  KNOWN_LIMITATIONS.md
  NEXT_REALISM_PHASE.md
  RUNBOOK.md

The final documentation must explain in plain language:
what Concordia owns;
what AgentSociety owns;
what SWORLDMODEL owns;
which code is exact upstream code;
which code is an adapter;
which code remains legacy;
how one best-action request flows through the system;
what has been proven;
what has not been proven;
what must happen during the later grounding and calibration phase.
Required subagents and adversarial review
Act as the primary senior developer and orchestration agent.
Use separate Opus-level subagents where available. Give each reviewer the complete relevant code and require written findings.
At minimum create these roles:
1. Upstream Preservation Auditor
Checks:
exact upstream usage;
no accidental rewrites;
no hidden source edits;
correct imports;
correct licenses;
correct pinned commits;
public-interface use;
unavoidable patch justification.
2. Integration Reliability Reviewer
Attacks:
state restoration;
race conditions;
workspace collisions;
branch leakage;
duplicated actions;
lost actions;
retries;
crashes;
cleanup;
checkpoint/resume;
dependency conflicts.
3. Concordia Semantics Reviewer
Checks:
actor lifecycle fidelity;
Game Master lifecycle fidelity;
memory persistence;
observation handling;
action handling;
preservation of Concordia’s actual working path.
4. AgentSociety Scale Reviewer
Checks:
real AgentSociety execution rather than a fake local substitute;
Ray use;
batching;
concurrency;
persistence;
worker isolation;
societal partition architecture.
5. Simulation Reality Reviewer
Rejects:
arbitrary social weights;
actors behaving from information they do not know;
Game Master-forced voluntary decisions;
final-result narration;
sophisticated-looking but causally empty role-play;
irrelevant full-life narration;
outcome metrics not tied to events.
This reviewer is not judging calibrated realism yet. It is judging whether the simulation at least operates like a real social world in structure.
6. Best-Action and Counterfactual Reviewer
Checks:
matched worlds;
intervention isolation;
explicit success criteria;
outcome extraction;
candidate comparison;
no final LLM override;
no unsupported global-optimum claim.
7. Final Adjudicator
Receives all implementation artifacts and reviewer reports.
It must return either:
PASS

or:
FAIL
- exact unmet gate
- evidence
- required correction

A majority vote is insufficient. Any verified critical failure blocks completion.
Implementation discipline
Make small, reviewable commits by phase.
Do not perform a giant rewrite.
Do not remove the legacy path before the replacement passes.
Do not combine unrelated architectural changes.
Do not add calibration during this pass.
Do not add elaborate population realism during this pass.
Do not add a giant action-search algorithm during this pass.
Do not hide failures with retries.
Do not loosen tests merely to make the new architecture pass.
Do not silently repair compiler output.
Do not invent a scenario-specific schema.
Do not use AgentSociety’s code-generation router for authoritative world mutations.
Do not claim “100% complete” merely because code compiles.
Define completion exclusively through the gates above.
Final required output
At completion, provide:
Executive summary.
Exact final architecture.
Exact commit SHAs for all three repositories.
Every file added or changed.
Every upstream component used directly.
Every adapter created.
Every upstream modification, ideally none.
Test results.
Individual simulation result.
Team simulation result.
100-agent infrastructure result.
1,000-agent infrastructure result.
Counterfactual comparison result.
Failure-injection results.
Reviewer reports.
Final adjudicator verdict.
Known limitations.
Exact next steps for:
evidence grounding;
observed/inferred/latent state separation;
representative population construction;
human-behavior calibration;
full action search;
confidence calibration.
Do not describe those later realism systems as completed unless they were separately implemented and validated.
Blocking behavior
Do not stop merely because the task is large.
Resolve implementation questions by auditing the actual code first.
Use the simplest architecture that preserves the working upstream paths and passes the gates.
Only ask me a question when:
the repository lacks required access;
a destructive product decision is unavoidable;
a licensing issue requires owner approval;
or two technically valid implementations would produce materially different product behavior and the source code cannot resolve the choice.
Otherwise proceed, document the assumption, implement it, and test it.
/loop until this entire implementation is 100% COMPLETE AND WORKING AS DESIRED.
Continue through this full cycle until every mandatory acceptance gate passes:
audit
→ plan
→ implement one phase
→ run tests
→ adversarial review
→ fix verified failures
→ rerun the complete phase
→ continue to the next phase
→ freeze final commit
→ run the full acceptance suite from the beginning
→ final adjudication

Do not exit the loop with a plan-only response.
Do not call the run complete while any critical reviewer finding, failing acceptance gate, flaky test, unexplained branch difference, state leak, actor-agency violation, or upstream-integrity violation remains.
