/**
 * The catalog of runs this viewer can replay, and the artifact files each
 * one is made of.
 *
 * Every path is repository-relative, so the viewer reads exactly the
 * committed artifacts and nothing else.  The catalog is explicit rather
 * than discovered by directory listing for two reasons: a static file
 * server cannot be asked "what is in this directory?", and an explicit
 * list means a run that has LOST its files fails loudly instead of
 * silently disappearing from the menu.
 */

export const ARTIFACT_ROOT = 'artifacts/full_trace_validation_20260804';

/** Files that describe the session as a whole. */
export const SESSION_FILES = {
  readme: { path: `${ARTIFACT_ROOT}/README.md`, kind: 'text' },
  callAccounting: {
    path: `${ARTIFACT_ROOT}/SESSION_CALL_ACCOUNTING.json`,
    kind: 'json',
  },
};

/**
 * A branch (one candidate's counterfactual) is always these files.
 * `required: false` means the artifact genuinely does not exist for some
 * run kinds -- the viewer then says so, naming the run kind, instead of
 * inventing a value.
 */
export const BRANCH_FILES = [
  { key: 'stepLedger', name: 'step_ledger.jsonl', kind: 'jsonl',
    required: true, auditorOnly: true },
  { key: 'committedEvents', name: 'committed_events.jsonl', kind: 'jsonl',
    required: true },
  { key: 'llmCalls', name: 'llm_calls.jsonl', kind: 'jsonl', required: true },
  { key: 'observations', name: 'observations.jsonl', kind: 'jsonl',
    required: true },
  { key: 'guardLedger', name: 'guard_ledger.jsonl', kind: 'jsonl',
    required: true },
  { key: 'branchResult', name: 'branch_result.json', kind: 'json',
    required: true },
  { key: 'traceReport', name: 'trace_report.json', kind: 'json',
    required: false,
    absentReason: 'settling-arm runs write one trace report for the run, '
      + 'not one per branch' },
  { key: 'actorMemories', name: 'actor_memories.json', kind: 'json',
    required: false, absentReason: 'not written by this run kind' },
  { key: 'stepAttribution', name: 'step_attribution_check.json',
    kind: 'json', required: false,
    absentReason: 'the settling harness does not run the per-step '
      + 'attribution check' },
];

/** Branch files that are linked but never fetched (they are large). */
export const BRANCH_LINK_ONLY = ['raw_engine_log.json'];

const SCENARIO_FILES = [
  { key: 'freezeManifest', name: 'freeze_manifest.json', kind: 'json',
    required: true },
  { key: 'traceReport', name: 'trace_report.json', kind: 'json',
    required: true },
  { key: 'decisionProblem', name: 'decision_problem.json', kind: 'json',
    required: true },
  { key: 'evidenceManifest', name: 'evidence_manifest.json', kind: 'json',
    required: true },
  { key: 'candidates', name: 'candidates/candidates.json', kind: 'json',
    required: true },
  { key: 'evaluatorLedger', name: 'evaluator_ledger.json', kind: 'json',
    required: true },
  { key: 'recommendationResult', name: 'recommendation_result.json',
    kind: 'json', required: true },
  { key: 'basePlan', name: 'adapter/base_plan.json', kind: 'json',
    required: true },
  { key: 'adaptedWorld', name: 'adapter/adapted_world.json', kind: 'json',
    required: true },
  { key: 'allLlmCalls', name: 'all_llm_calls.jsonl', kind: 'jsonl',
    required: true },
  { key: 'rankingRefusal', name: 'ranking_refusal.json', kind: 'json',
    required: false,
    absentReason: 'this run produced a ranking, so no refusal was written' },
  { key: 'candidateBinding', name: 'candidates/candidate_binding.json',
    kind: 'json', required: false,
    absentReason: 'only the salary-mapped scenario binds candidates to '
      + 'code-owned keys' },
  { key: 'deliveryCheck', name: 'candidate_delivery_check.json',
    kind: 'json', required: false,
    alternatives: ['offer_delivery_check.json'],
    absentReason: 'no delivery check was written for this run' },
  { key: 'measurementAudit', name: 'measurement_audit.json', kind: 'json',
    required: false,
    absentReason: 'the post-hoc measurement audit was written for the '
      + 'message scenarios only' },
  { key: 'preVsPostFix', name: 'pre_vs_post_fix.json', kind: 'json',
    required: false,
    absentReason: 'only a post-fix re-run compares itself with a pre-fix '
      + 'run' },
  { key: 'frozenInputVerification', name: 'frozen_input_verification.json',
    kind: 'json', required: false,
    absentReason: 'only a post-fix re-run re-verifies the frozen inputs' },
  { key: 'cutoffValidation', name: 'historical_cutoff_validation.json',
    kind: 'json', required: false,
    absentReason: 'only the historical scenario enforces a knowledge '
      + 'cutoff' },
  { key: 'branchInputDiff', name: 'branch_input_diff.json', kind: 'json',
    required: false, absentReason: 'not written by this run' },
  { key: 'worldReuseProof', name: 'world_reuse_proof.json', kind: 'json',
    required: false,
    absentReason: 'only the generated-candidate scenario proves it reused '
      + 'the other scenario\'s compiled world' },
];

const SETTLING_FILES = [
  { key: 'freezeManifest', name: 'freeze_manifest.json', kind: 'json',
    required: true },
  { key: 'traceReport', name: 'trace_report.json', kind: 'json',
    required: true },
  { key: 'armDesign', name: 'arm_design.json', kind: 'json', required: true },
  { key: 'settlingMeasurement', name: 'settling_measurement.json',
    kind: 'json', required: true },
  { key: 'rankingRefusal', name: 'ranking_refusal.json', kind: 'json',
    required: true },
  { key: 'recommendationResult', name: 'recommendation_report.json',
    kind: 'json', required: true },
  { key: 'forcedObserverControl', name: 'forced_observer_control.json',
    kind: 'json', required: true },
  { key: 'providerProbe', name: 'provider_probe.json', kind: 'json',
    required: true },
  { key: 'instrumentation', name: 'instrumentation.json', kind: 'json',
    required: true },
  { key: 'deliveryCheck', name: 'candidate_delivery_check.json',
    kind: 'json', required: true },
  { key: 'basePlan', name: 'adapter/base_plan.json', kind: 'json',
    required: true },
  { key: 'adaptedWorld', name: 'adapter/adapted_world.json', kind: 'json',
    required: true },
  { key: 'allLlmCalls', name: 'all_llm_calls.jsonl', kind: 'jsonl',
    required: true },
];

/**
 * Files whose location differs between run kinds.  The first path that
 * loads wins and the viewer shows WHICH one it used; if none load and the
 * entry is required, that is a loud error.
 */
function sharedLookups(dir, extra = []) {
  return [
    { key: 'modelConfiguration', kind: 'json', required: true,
      paths: [
        `${dir}/model_configuration.json`,
        `${dir}/shared/model_configuration.json`,
        ...extra.map((p) => `${p}/model_configuration.json`),
        `${ARTIFACT_ROOT}/shared/model_configuration.json`,
      ] },
    { key: 'environment', kind: 'json', required: true,
      paths: [
        `${dir}/environment.json`,
        `${dir}/shared/environment.json`,
        ...extra.map((p) => `${p}/environment.json`),
        `${ARTIFACT_ROOT}/shared/environment.json`,
      ] },
    { key: 'runIdentity', kind: 'json', required: false,
      absentReason: 'this run kind records its identity in arm_design.json '
        + 'and the freeze manifest instead',
      paths: [
        `${dir}/run_identity.json`,
        `${dir}/shared/run_identity.json`,
        `${ARTIFACT_ROOT}/shared/run_identity.json`,
      ] },
    { key: 'instrumentation', kind: 'json', required: false,
      absentReason: 'no per-run instrumentation summary was written here',
      paths: [
        `${dir}/instrumentation_validation.json`,
        `${dir}/shared/instrumentation_validation.json`,
        `${ARTIFACT_ROOT}/shared/instrumentation_validation.json`,
      ] },
  ];
}

function scenarioRun({ id, group, groupLabel, label, dir, phase,
  candidateSource, docs }) {
  return {
    id,
    group,
    groupLabel,
    label,
    kind: 'scenario',
    phase,
    dir: `${ARTIFACT_ROOT}/${dir}`,
    candidateSource,
    files: SCENARIO_FILES,
    lookups: sharedLookups(`${ARTIFACT_ROOT}/${dir}`),
    docs: docs.map((d) => ({ ...d, path: `${ARTIFACT_ROOT}/${d.rel}` })),
  };
}

function settlingRun({ id, arm, armLabel, rep, dir, counted, note }) {
  return {
    id,
    group: `settling_arm_${arm}`,
    groupLabel: `Settling experiment -- arm ${arm.toUpperCase()} (${armLabel})`,
    label: `Arm ${arm.toUpperCase()} ${rep}${counted ? '' : ' [shakedown, not counted]'}`,
    kind: 'settling',
    phase: counted ? 'settling_counted' : 'settling_shakedown',
    dir: `${ARTIFACT_ROOT}/${dir}`,
    candidateSource: 'supplied',
    counted,
    note,
    files: SETTLING_FILES,
    lookups: [
      { key: 'modelConfiguration', kind: 'json', required: true,
        jsonPointer: ['model_configuration'],
        paths: [`${ARTIFACT_ROOT}/settling_experiment/SETTLING_MEASUREMENTS.json`] },
      { key: 'environment', kind: 'json', required: true,
        jsonPointer: ['environment'],
        paths: [`${ARTIFACT_ROOT}/settling_experiment/SETTLING_MEASUREMENTS.json`] },
    ],
    docs: [
      { rel: 'settling_experiment/README.md', label: 'Settling experiment README',
        path: `${ARTIFACT_ROOT}/settling_experiment/README.md` },
      { rel: 'settling_experiment/SETTLING_RESULT.md', label: 'Settling result',
        path: `${ARTIFACT_ROOT}/settling_experiment/SETTLING_RESULT.md` },
    ],
  };
}

export const RUNS = [
  scenarioRun({
    id: 'peter_supplied__pre_fix',
    group: 'peter_supplied',
    groupLabel: 'Scenario 1 -- message, user-supplied candidates',
    label: 'Pre-fix run',
    dir: 'peter_supplied',
    phase: 'pre_fix',
    candidateSource: 'supplied',
    docs: [
      { rel: 'peter_supplied/UNDER_THE_HOOD_REPORT.md',
        label: 'Under-the-hood report' },
    ],
  }),
  scenarioRun({
    id: 'peter_supplied__post_fix',
    group: 'peter_supplied',
    groupLabel: 'Scenario 1 -- message, user-supplied candidates',
    label: 'Post-fix re-run',
    dir: 'peter_supplied/post_fix_rerun',
    phase: 'post_fix',
    candidateSource: 'supplied',
    docs: [
      { rel: 'peter_supplied/post_fix_rerun/PRE_VS_POST_FIX.md',
        label: 'Pre-fix vs post-fix' },
      { rel: 'peter_supplied/UNDER_THE_HOOD_REPORT.md',
        label: 'Under-the-hood report (pre-fix run)' },
    ],
  }),
  scenarioRun({
    id: 'peter_generated__pre_fix',
    group: 'peter_generated',
    groupLabel: 'Scenario 2 -- message, model-generated candidates',
    label: 'Pre-fix run',
    dir: 'peter_generated',
    phase: 'pre_fix',
    candidateSource: 'generated',
    docs: [
      { rel: 'peter_generated/UNDER_THE_HOOD_REPORT.md',
        label: 'Under-the-hood report' },
      { rel: 'peter_generated/generator_prompt.txt',
        label: 'Candidate generator prompt' },
      { rel: 'peter_generated/generator_raw_response.txt',
        label: 'Candidate generator raw response' },
    ],
  }),
  scenarioRun({
    id: 'peter_generated__post_fix',
    group: 'peter_generated',
    groupLabel: 'Scenario 2 -- message, model-generated candidates',
    label: 'Post-fix re-run',
    dir: 'peter_generated/post_fix_rerun',
    phase: 'post_fix',
    candidateSource: 'generated',
    docs: [
      { rel: 'peter_generated/post_fix_rerun/PRE_VS_POST_FIX.md',
        label: 'Pre-fix vs post-fix' },
      { rel: 'peter_generated/post_fix_rerun/generator_prompt.txt',
        label: 'Candidate generator prompt' },
      { rel: 'peter_generated/post_fix_rerun/generator_raw_response.txt',
        label: 'Candidate generator raw response' },
    ],
  }),
  scenarioRun({
    id: 'a16z_richard_historical__pre_fix',
    group: 'a16z_richard_historical',
    groupLabel: 'Scenario 3 -- historical counterfactual, 6 salary branches',
    label: 'Pre-fix run',
    dir: 'a16z_richard_historical',
    phase: 'pre_fix',
    candidateSource: 'supplied',
    docs: [
      { rel: 'a16z_richard_historical/UNDER_THE_HOOD_REPORT.md',
        label: 'Under-the-hood report' },
    ],
  }),
  scenarioRun({
    id: 'a16z_richard_historical__post_fix',
    group: 'a16z_richard_historical',
    groupLabel: 'Scenario 3 -- historical counterfactual, 6 salary branches',
    label: 'Post-fix re-run',
    dir: 'a16z_richard_historical/post_fix_rerun',
    phase: 'post_fix',
    candidateSource: 'supplied',
    docs: [
      { rel: 'a16z_richard_historical/post_fix_rerun/PRE_VS_POST_FIX.md',
        label: 'Pre-fix vs post-fix' },
      { rel: 'a16z_richard_historical/UNDER_THE_HOOD_REPORT.md',
        label: 'Under-the-hood report (pre-fix run)' },
    ],
  }),
  settlingRun({ id: 'settling_arm_a__rep_1', arm: 'a',
    armLabel: 'pre-narrated send', rep: 'rep 1',
    dir: 'settling_experiment/arm_a/rep_1', counted: true }),
  settlingRun({ id: 'settling_arm_a__rep_2', arm: 'a',
    armLabel: 'pre-narrated send', rep: 'rep 2',
    dir: 'settling_experiment/arm_a/rep_2', counted: true }),
  settlingRun({ id: 'settling_arm_a__rep_3', arm: 'a',
    armLabel: 'pre-narrated send', rep: 'rep 3',
    dir: 'settling_experiment/arm_a/rep_3', counted: true }),
  settlingRun({ id: 'settling_arm_b__rep_1', arm: 'b',
    armLabel: 'no starting event', rep: 'rep 1',
    dir: 'settling_experiment/arm_b/rep_1', counted: true }),
  settlingRun({ id: 'settling_arm_b__rep_2', arm: 'b',
    armLabel: 'no starting event', rep: 'rep 2',
    dir: 'settling_experiment/arm_b/rep_2', counted: true }),
  settlingRun({ id: 'settling_arm_b__rep_3', arm: 'b',
    armLabel: 'no starting event', rep: 'rep 3',
    dir: 'settling_experiment/arm_b/rep_3', counted: true }),
  settlingRun({ id: 'settling_arm_a__shakedown', arm: 'a',
    armLabel: 'pre-narrated send', rep: 'shakedown run',
    dir: 'settling_experiment/harness_shakedown/arm_a_run', counted: false,
    note: 'First live run of the settling harness. Kept, complete and real, '
      + 'but NOT counted in the reported per-arm rates because it predates '
      + 'the final enactment instrument. See harness_shakedown/README.md.' }),
  settlingRun({ id: 'settling_arm_b__shakedown', arm: 'b',
    armLabel: 'no starting event', rep: 'shakedown run',
    dir: 'settling_experiment/harness_shakedown/arm_b_run', counted: false,
    note: 'First live run of the settling harness. Kept, complete and real, '
      + 'but NOT counted in the reported per-arm rates because it predates '
      + 'the final enactment instrument. See harness_shakedown/README.md.' }),
];

/** @returns {object|undefined} the catalog entry with this id */
export function runById(id) {
  return RUNS.find((run) => run.id === id);
}

/** Catalog entries grouped for a two-level run selector. */
export function runGroups() {
  const groups = [];
  for (const run of RUNS) {
    let group = groups.find((g) => g.id === run.group);
    if (!group) {
      group = { id: run.group, label: run.groupLabel, runs: [] };
      groups.push(group);
    }
    group.runs.push(run);
  }
  return groups;
}
