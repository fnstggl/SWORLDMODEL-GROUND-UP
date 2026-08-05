/**
 * The viewer's data-assembly transform: frozen artifact bytes in, one
 * ordered replay view model out.
 *
 * This module is PURE with respect to the environment: it never touches
 * the DOM, `fetch`, or the filesystem.  Everything it reads arrives
 * through the injected `io` object, so the browser and the automated
 * equivalence test drive the exact same ordering and selection logic.
 *
 * Two rules the code enforces rather than documents:
 *
 * 1. FAIL LOUD.  A missing, malformed, or hash-inconsistent artifact
 *    becomes a `problem` naming the file and the defect.  No placeholder
 *    event is ever invented and no broken record is dropped -- a record
 *    that will not parse is kept in position and marked malformed.
 * 2. AUDITOR-ONLY STAYS LABELLED.  `step_ledger.jsonl` deliberately holds
 *    every actor's private context side by side; no actor ever saw it.
 *    Anything derived from another actor's slice of a step is tagged
 *    `auditorOnly: true` and the actor-prompt view carries only the
 *    ACTIVE actor's own prompt.
 */

import {
  canonicalFromText,
  canonicalize,
  parseJsonPreservingNumbers,
  selectPath,
} from './canonical_json.js';
import { ARTIFACT_ROOT, BRANCH_FILES, BRANCH_LINK_ONLY, SESSION_FILES }
  from './catalog.js';

export const VIEWER_BANNER = 'UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION';

export const AUDITOR_ONLY_NOTE =
  'AUDITOR-ONLY -- assembled from step_ledger.jsonl, which deliberately '
  + 'places every actor\'s private context and every prompt side by side. '
  + 'No actor ever saw this view.';

/* ------------------------------------------------------------------ */
/* problems                                                            */
/* ------------------------------------------------------------------ */

function addProblem(problems, severity, file, what, detail = null) {
  problems.push({ severity, file, problem: what, detail });
  return problems[problems.length - 1];
}

/* ------------------------------------------------------------------ */
/* loading                                                             */
/* ------------------------------------------------------------------ */

/**
 * Read one artifact.  Returns a record that always states what happened;
 * callers decide whether an absence is an error or a documented absence.
 */
async function loadOne(io, path, kind, problems, { required, absentReason }) {
  const result = await io.readText(path);
  if (!result.ok) {
    const record = {
      path, kind, ok: false, present: false,
      error: result.error || 'could not be read',
      absentReason: absentReason || null,
    };
    if (required) {
      addProblem(problems, 'error', path,
        'required artifact could not be read', record.error);
    }
    return record;
  }
  const record = { path, kind, ok: true, present: true, text: result.text };
  if (kind === 'json') {
    try {
      record.json = JSON.parse(result.text);
      record.rawTree = parseJsonPreservingNumbers(result.text);
    } catch (error) {
      record.ok = false;
      record.error = `malformed JSON: ${error.message}`;
      addProblem(problems, 'error', path, 'malformed JSON', error.message);
    }
  } else if (kind === 'jsonl') {
    const parsed = parseJsonl(result.text, path, problems);
    record.rows = parsed.rows;
    record.malformedCount = parsed.malformedCount;
    if (parsed.malformedCount > 0) record.ok = false;
  }
  return record;
}

/**
 * Parse JSONL.  A line that will not parse is KEPT, in position, as a
 * `__malformed` row -- the viewer renders it as a loud red record rather
 * than quietly shortening the timeline.
 */
export function parseJsonl(text, path, problems = []) {
  const rows = [];
  let malformedCount = 0;
  const lines = text.split('\n');
  lines.forEach((line, offset) => {
    if (line.trim() === '') return;
    try {
      rows.push(JSON.parse(line));
    } catch (error) {
      malformedCount += 1;
      rows.push({
        __malformed: true,
        line: offset + 1,
        raw: line,
        error: error.message,
        path,
      });
      addProblem(problems, 'error', path,
        `malformed JSON on line ${offset + 1}`, error.message);
    }
  });
  return { rows, malformedCount };
}

async function loadRunFiles(run, io, problems) {
  const files = {};
  for (const spec of run.files) {
    const candidates = [spec.name, ...(spec.alternatives || [])];
    let record = null;
    for (const name of candidates) {
      const attempt = await loadOne(io, `${run.dir}/${name}`, spec.kind,
        [], { required: false, absentReason: spec.absentReason });
      if (attempt.present) {
        record = attempt;
        // Re-run the parse diagnostics against the real problem list so a
        // malformed-but-present file is reported.
        if (spec.kind === 'json' && !attempt.ok) {
          addProblem(problems, 'error', attempt.path, 'malformed JSON',
            attempt.error);
        } else if (spec.kind === 'jsonl' && attempt.malformedCount > 0) {
          addProblem(problems, 'error', attempt.path,
            `${attempt.malformedCount} malformed JSONL line(s)`, null);
        }
        break;
      }
    }
    if (!record) {
      record = {
        path: `${run.dir}/${spec.name}`, kind: spec.kind, ok: false,
        present: false, absentReason: spec.absentReason || null,
        error: 'not found',
      };
      if (spec.required) {
        addProblem(problems, 'error', record.path,
          'required artifact is missing', null);
      }
    }
    record.auditorOnly = Boolean(spec.auditorOnly);
    files[spec.key] = record;
  }
  for (const lookup of run.lookups || []) {
    let record = null;
    for (const path of lookup.paths) {
      const attempt = await loadOne(io, path, lookup.kind, [],
        { required: false });
      if (attempt.present) { record = attempt; break; }
    }
    if (!record) {
      record = {
        path: lookup.paths[0], kind: lookup.kind, ok: false, present: false,
        absentReason: lookup.absentReason || null,
        error: `not found at any of: ${lookup.paths.join(', ')}`,
      };
      if (lookup.required) {
        addProblem(problems, 'error', record.path,
          'required artifact is missing', record.error);
      }
    } else if (lookup.jsonPointer && record.json) {
      record.json = selectPlain(record.json, lookup.jsonPointer);
      record.pointer = lookup.jsonPointer.join('.');
      if (record.json === undefined) {
        addProblem(problems, 'error', record.path,
          `expected key "${lookup.jsonPointer.join('.')}" is absent`, null);
      }
    }
    files[lookup.key] = record;
  }
  return files;
}

function selectPlain(value, path) {
  let node = value;
  for (const key of path) {
    if (node === null || node === undefined) return undefined;
    node = node[key];
  }
  return node;
}

/**
 * Read a number EXACTLY as the artifact wrote it, as a string.
 *
 * `JSON.parse` silently rounds integers above 2^53, and the branch seeds in
 * these artifacts are 63-bit.  Showing `3730100026622196000` where the file
 * says `3730100026622196392` would be a fabricated value, so every seed the
 * viewer displays comes through here, from the preserved literal.
 */
export function exactNumber(fileRecord, path) {
  if (!fileRecord || !fileRecord.rawTree) return null;
  const node = selectPath(fileRecord.rawTree, path);
  if (node === undefined || node === null) return null;
  if (typeof node === 'object' && typeof node.literal === 'string') {
    return node.literal;
  }
  return String(node);
}

/* ------------------------------------------------------------------ */
/* branch discovery                                                    */
/* ------------------------------------------------------------------ */

/**
 * Which branches does this run have?  Taken from the run's own trace
 * report, then CROSS-CHECKED against the candidate set and the evaluator
 * ledger.  A disagreement is a loud problem, never a silent union.
 */
export function discoverBranches(run, files, problems) {
  const trace = files.traceReport && files.traceReport.json;
  const listed = [];
  if (trace && Array.isArray(trace.branches)) {
    trace.branches.forEach((entry, position) => {
      listed.push({
        candidateId: entry.candidate_id,
        branchId: entry.branch_id,
        // exact literal: branch seeds exceed JavaScript's safe integer range
        branchSeed: exactNumber(files.traceReport,
          ['branches', position, 'branch_seed']),
        planId: entry.branch_plan_id,
        planContentHash: entry.branch_plan_content_hash,
        terminalStatus: entry.terminal_status,
        stepsCompleted: entry.steps_completed,
      });
    });
  } else if (files.traceReport && files.traceReport.present) {
    addProblem(problems, 'error', files.traceReport.path,
      'trace report has no "branches" array; the branch list cannot be '
      + 'established from the artifacts', null);
  }

  const candidates = files.candidates && files.candidates.json;
  if (Array.isArray(candidates)) {
    const fromCandidates = candidates.map((c) => c.candidate_id);
    const fromTrace = listed.map((b) => b.candidateId);
    if (canonicalize([...fromCandidates].sort())
        !== canonicalize([...fromTrace].sort())) {
      addProblem(problems, 'error', files.candidates.path,
        'candidate set and trace report disagree about which branches ran',
        `candidates=${JSON.stringify(fromCandidates)} `
        + `trace_report=${JSON.stringify(fromTrace)}`);
    }
  }
  const ledger = files.evaluatorLedger && files.evaluatorLedger.json;
  if (ledger && Array.isArray(ledger.branches)) {
    const fromLedger = ledger.branches.map((b) => b.candidate_id);
    const fromTrace = listed.map((b) => b.candidateId);
    if (canonicalize([...fromLedger].sort())
        !== canonicalize([...fromTrace].sort())) {
      addProblem(problems, 'error', files.evaluatorLedger.path,
        'evaluator ledger and trace report disagree about which branches ran',
        `evaluator=${JSON.stringify(fromLedger)} `
        + `trace_report=${JSON.stringify(fromTrace)}`);
    }
  }
  return listed;
}

async function loadBranchFiles(run, candidateId, io, problems) {
  const dir = `${run.dir}/branches/${candidateId}`;
  const files = {};
  for (const spec of BRANCH_FILES) {
    const record = await loadOne(io, `${dir}/${spec.name}`, spec.kind,
      problems, { required: spec.required, absentReason: spec.absentReason });
    record.auditorOnly = Boolean(spec.auditorOnly);
    files[spec.key] = record;
  }
  files.__linkOnly = BRANCH_LINK_ONLY.map((name) => ({
    path: `${dir}/${name}`,
    note: 'linked, not loaded (large raw engine log)',
  }));
  files.__dir = dir;
  return files;
}

/* ------------------------------------------------------------------ */
/* timeline                                                            */
/* ------------------------------------------------------------------ */

function unavailableReason(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)
      && typeof value.unavailable === 'string') {
    return value.unavailable;
  }
  return null;
}

/** Every call id a step record surfaces, actor calls first, then GM calls. */
export function callIdsForStep(step) {
  const ids = [];
  const requests = step.actor_model_request;
  if (Array.isArray(requests)) {
    for (const call of requests) {
      if (call && typeof call === 'object' && call.call_id) ids.push(call.call_id);
    }
  }
  const gm = step.game_master_raw_response;
  if (gm && typeof gm === 'object' && Array.isArray(gm.recorded_calls)) {
    for (const call of gm.recorded_calls) {
      if (call && typeof call === 'object' && call.call_id) ids.push(call.call_id);
    }
  }
  return ids;
}

/**
 * Build one branch's ordered replay timeline.
 *
 * The committed-event stream is emitted in the order the TIMELINE plays
 * it, not by re-reading the file in order -- so if step selection or
 * ordering were wrong, the stream would diverge from
 * `committed_events.jsonl` and the equivalence test would catch it.
 *
 * @returns {{entries: object[], committedStream: object[], callIds: string[],
 *            problems: object[], auditorBanner: object|null}}
 */
export function assembleBranchTimeline({
  candidateId, branchId, files,
}) {
  const problems = [];
  const stepFile = files.stepLedger;
  const committedFile = files.committedEvents;
  const callsFile = files.llmCalls;
  const observationFile = files.observations;
  const guardFile = files.guardLedger;

  const rawSteps = (stepFile && stepFile.rows) || [];
  let auditorBanner = null;
  const stepRows = [];
  const malformedRows = [];
  for (const row of rawSteps) {
    if (row && row.__malformed) { malformedRows.push(row); continue; }
    if (row && row._artifact_class === 'AUDITOR_ONLY') {
      auditorBanner = row;
      continue;
    }
    stepRows.push(row);
  }
  if (!auditorBanner && stepFile && stepFile.present) {
    addProblem(problems, 'warning', stepFile.path,
      'the AUDITOR_ONLY banner record is missing from this ledger', null);
  }

  const committedRows = ((committedFile && committedFile.rows) || [])
    .filter((row) => !row.__malformed);
  const committedMalformed = ((committedFile && committedFile.rows) || [])
    .filter((row) => row.__malformed);
  committedRows.forEach((row, position) => {
    if (typeof row.index === 'number' && row.index !== position) {
      addProblem(problems, 'error', committedFile.path,
        `committed event row ${position} declares index ${row.index}`,
        'the committed stream is not in index order');
    }
  });
  const committedByIndex = new Map();
  for (const row of committedRows) committedByIndex.set(row.index, row);

  const orderedSteps = [...stepRows].sort((a, b) => a.step - b.step);
  const fileOrder = stepRows.map((s) => s.step);
  const sortedOrder = orderedSteps.map((s) => s.step);
  if (canonicalize(fileOrder) !== canonicalize(sortedOrder)) {
    addProblem(problems, 'warning', stepFile.path,
      'step records are not in ascending step order in the file',
      `file order=${JSON.stringify(fileOrder)}`);
  }
  const seenSteps = new Set();
  for (const step of orderedSteps) {
    if (seenSteps.has(step.step)) {
      addProblem(problems, 'error', stepFile.path,
        `step ${step.step} appears more than once`, null);
    }
    seenSteps.add(step.step);
  }

  const observationsByStep = new Map();
  for (const row of (observationFile && observationFile.rows) || []) {
    if (row.__malformed) continue;
    if (!observationsByStep.has(row.step)) observationsByStep.set(row.step, []);
    observationsByStep.get(row.step).push(row);
  }
  const guardByStep = new Map();
  for (const row of (guardFile && guardFile.rows) || []) {
    if (row.__malformed) continue;
    guardByStep.set(row.step, row);
  }
  const callsById = new Map();
  const ledgerCallOrder = [];
  for (const row of (callsFile && callsFile.rows) || []) {
    if (row.__malformed) continue;
    callsById.set(row.call_id, row);
    ledgerCallOrder.push(row.call_id);
  }

  // Which committed rows does a step claim?
  const claimedIndices = new Set();
  for (const step of orderedSteps) {
    const final = step.final_committed_event;
    if (final && typeof final.index === 'number') claimedIndices.add(final.index);
  }
  const firstClaimed = claimedIndices.size
    ? Math.min(...claimedIndices) : committedRows.length;

  const entries = [];

  // Starting events: committed before the first step claimed anything.
  for (const row of committedRows) {
    if (claimedIndices.has(row.index)) continue;
    if (row.index >= firstClaimed) continue;
    entries.push({
      kind: 'genesis',
      key: `genesis-${row.index}`,
      label: 'starting event (committed before step 1)',
      note: 'read from committed_events.jsonl; no step record authored it, '
        + 'because it was placed by the compiled world, not by an actor turn',
      committedEvent: row,
      callIds: [],
    });
  }

  for (const step of orderedSteps) {
    const final = step.final_committed_event;
    const finalUnavailable = unavailableReason(final);
    let committedEvent = null;
    if (final && typeof final.index === 'number') {
      committedEvent = committedByIndex.get(final.index) || null;
      if (!committedEvent) {
        addProblem(problems, 'error', committedFile.path,
          `step ${step.step} names committed event index ${final.index}, `
          + 'which is not present in the committed stream', null);
      } else if (typeof final.text === 'string'
          && final.text !== committedEvent.text) {
        addProblem(problems, 'error', committedFile.path,
          `step ${step.step} committed-event text disagrees with `
          + `committed_events.jsonl row ${final.index}`, null);
      }
    } else if (!finalUnavailable) {
      addProblem(problems, 'error', stepFile.path,
        `step ${step.step} has no usable final_committed_event`, null);
    }

    const stepCallIds = callIdsForStep(step);
    for (const id of stepCallIds) {
      if (!callsById.has(id)) {
        addProblem(problems, 'error', callsFile.path,
          `step ${step.step} references call_id ${id}, which is not in the `
          + 'branch call ledger', null);
      }
    }

    entries.push({
      kind: 'step',
      key: `step-${step.step}`,
      step: step.step,
      label: `step ${step.step}`,
      record: step,
      committedEvent,
      committedEventUnavailable: finalUnavailable,
      guard: guardByStep.get(step.step) || null,
      observationRows: observationsByStep.get(step.step) || [],
      callIds: stepCallIds,
      calls: stepCallIds.map((id) => callsById.get(id) || { call_id: id,
        __missing: true }),
    });
  }

  // Committed rows no step claimed and that are not starting events.
  for (const row of committedRows) {
    if (claimedIndices.has(row.index)) continue;
    if (row.index < firstClaimed) continue;
    addProblem(problems, 'error', committedFile.path,
      `committed event index ${row.index} is claimed by no step record`,
      'it is shown at the end of the timeline rather than hidden');
    entries.push({
      kind: 'unattached',
      key: `unattached-${row.index}`,
      label: 'committed event claimed by NO step record',
      committedEvent: row,
      callIds: [],
    });
  }

  for (const row of malformedRows) {
    entries.push({
      kind: 'malformed',
      key: `malformed-${row.line}`,
      label: `unparseable step_ledger.jsonl line ${row.line}`,
      record: row,
      committedEvent: null,
      callIds: [],
    });
  }
  for (const row of committedMalformed) {
    entries.push({
      kind: 'malformed',
      key: `malformed-committed-${row.line}`,
      label: `unparseable committed_events.jsonl line ${row.line}`,
      record: row,
      committedEvent: null,
      callIds: [],
    });
  }

  const committedStream = entries
    .filter((entry) => entry.committedEvent)
    .map((entry) => entry.committedEvent);
  const callIds = entries.flatMap((entry) => entry.callIds);

  const surfaced = new Set(callIds);
  for (const id of ledgerCallOrder) {
    if (!surfaced.has(id)) {
      addProblem(problems, 'error', callsFile.path,
        `call ${id} is recorded in this branch's ledger but no step record `
        + 'surfaces it', 'the timeline would otherwise hide a live call');
    }
  }

  return { entries, committedStream, callIds, problems, auditorBanner,
    ledgerCallOrder };
}

/* ------------------------------------------------------------------ */
/* metrics and citations                                               */
/* ------------------------------------------------------------------ */

/**
 * Outcome metrics with the exact events they were computed from.
 * `branch_result.json` and `evaluator_ledger.json` must agree; if they do
 * not, that is reported rather than resolved by preference.
 */
export function assembleMetrics({ candidateId, branchFiles, evaluatorLedger,
  evaluatorPath, committedRows }) {
  const problems = [];
  const result = branchFiles.branchResult && branchFiles.branchResult.json;
  const metrics = {};
  const byId = new Map(committedRows.map((row) => [row.event_id, row]));

  const fromResult = (result && result.outcome_metrics) || {};
  let ledgerEntry = null;
  if (evaluatorLedger && Array.isArray(evaluatorLedger.branches)) {
    ledgerEntry = evaluatorLedger.branches
      .find((b) => b.candidate_id === candidateId) || null;
    if (!ledgerEntry) {
      addProblem(problems, 'error', evaluatorPath,
        `no evaluator ledger entry for candidate ${candidateId}`, null);
    }
  }

  for (const [name, value] of Object.entries(fromResult)) {
    const citations = Array.isArray(value.computed_from)
      ? value.computed_from : [];
    const entry = {
      name,
      value: value.value,
      computedFrom: citations,
      source: branchFiles.branchResult.path,
      citedEvents: [],
      citedEventTexts: [],
      stateCitations: [],
    };
    for (const citation of citations) {
      if (typeof citation !== 'string') continue;
      if (citation.startsWith('event:')) {
        const eventId = citation.slice('event:'.length);
        const row = byId.get(eventId);
        if (!row) {
          addProblem(problems, 'error', branchFiles.branchResult.path,
            `metric ${name} cites ${citation}, which is not a committed `
            + 'event of this branch', null);
          entry.citedEvents.push({ eventId, missing: true });
        } else {
          entry.citedEvents.push({ eventId, index: row.index, text: row.text,
            sha256: row.sha256 });
        }
      } else {
        entry.stateCitations.push(citation);
      }
    }
    if (ledgerEntry && ledgerEntry.metrics && ledgerEntry.metrics[name]) {
      const ledgerMetric = ledgerEntry.metrics[name];
      entry.ledgerSource = evaluatorPath;
      entry.citedEventTexts = ledgerMetric.cited_event_texts || [];
      if (canonicalize(ledgerMetric.computed_from || [])
          !== canonicalize(citations)) {
        addProblem(problems, 'error', evaluatorPath,
          `metric ${name} citations disagree between branch_result.json and `
          + 'evaluator_ledger.json',
          `branch_result=${JSON.stringify(citations)} `
          + `evaluator=${JSON.stringify(ledgerMetric.computed_from)}`);
      }
      if (canonicalize(ledgerMetric.value) !== canonicalize(entry.value)) {
        addProblem(problems, 'error', evaluatorPath,
          `metric ${name} value disagrees between branch_result.json and `
          + 'evaluator_ledger.json',
          `branch_result=${JSON.stringify(entry.value)} `
          + `evaluator=${JSON.stringify(ledgerMetric.value)}`);
      }
    }
    metrics[name] = entry;
  }
  return { metrics, problems, ledgerEntry };
}

/* ------------------------------------------------------------------ */
/* hash verification                                                   */
/* ------------------------------------------------------------------ */

/**
 * Recompute every hash the artifacts publish and compare.
 *
 * Four independent families are checked:
 *   - each committed event row's own `sha256` over its text,
 *   - each step's `committed_stream_prefix_sha256` over the committed
 *     texts so far (the per-step state hash),
 *   - each recorded call's `request_sha256` / `response_sha256`,
 *   - the freeze manifest's entries against the files on disk.
 */
export async function verifyHashes({ run, files, branches, io }) {
  const checks = [];
  const problems = [];

  async function check(kind, path, label, expected, actual) {
    const ok = expected === actual;
    checks.push({ kind, path, label, expected, actual, ok });
    if (!ok) {
      addProblem(problems, 'error', path, `hash mismatch (${label})`,
        `manifest/record says ${expected}, recomputed ${actual}`);
    }
    return ok;
  }

  for (const branch of branches) {
    const bf = branch.files;
    const rows = ((bf.committedEvents && bf.committedEvents.rows) || [])
      .filter((row) => !row.__malformed);
    for (const row of rows) {
      if (typeof row.sha256 !== 'string' || typeof row.text !== 'string') continue;
      await check('committed_event', bf.committedEvents.path,
        `${branch.candidateId} event ${row.event_id}`,
        row.sha256, await io.sha256(row.text));
    }
    const texts = [];
    const prefixHashes = new Map();
    for (const row of rows) texts.push(row.text);
    for (const entry of branch.timeline.entries) {
      if (entry.kind !== 'step') continue;
      const state = entry.record.state_hash_after_step;
      if (!state || typeof state.committed_stream_prefix_sha256 !== 'string') {
        continue;
      }
      const count = state.committed_rows_so_far;
      if (typeof count !== 'number') continue;
      const recomputed = await io.sha256(canonicalize(texts.slice(0, count)));
      prefixHashes.set(entry.step, recomputed);
      await check('state_prefix', bf.stepLedger.path,
        `${branch.candidateId} step ${entry.step} committed-stream prefix`,
        state.committed_stream_prefix_sha256, recomputed);
    }
    const callRows = ((bf.llmCalls && bf.llmCalls.rows) || [])
      .filter((row) => !row.__malformed);
    const rawLines = bf.llmCalls && bf.llmCalls.text
      ? bf.llmCalls.text.split('\n').filter((line) => line.trim() !== '') : [];
    for (let k = 0; k < callRows.length; k += 1) {
      const row = callRows[k];
      if (typeof row.request_sha256 === 'string' && rawLines[k]) {
        let requestCanonical = null;
        try {
          const tree = parseJsonPreservingNumbers(rawLines[k]);
          requestCanonical = canonicalize(selectPath(tree, ['request']));
        } catch (error) {
          addProblem(problems, 'error', bf.llmCalls.path,
            `call ${row.call_id}: request could not be re-serialised`,
            error.message);
        }
        if (requestCanonical !== null) {
          await check('call_request', bf.llmCalls.path,
            `${branch.candidateId} call ${row.call_id} request`,
            row.request_sha256, await io.sha256(requestCanonical));
        }
      }
      if (typeof row.response_sha256 === 'string'
          && typeof row.response_raw === 'string'
          && row.response_sha256 !== '') {
        await check('call_response', bf.llmCalls.path,
          `${branch.candidateId} call ${row.call_id} response`,
          row.response_sha256, await io.sha256(row.response_raw));
      }
    }
  }

  // Freeze-manifest entries whose subject is a file the viewer already has.
  const manifest = files.freezeManifest && files.freezeManifest.json;
  if (manifest && manifest.entries) {
    const bindings = [
      { entry: 'decision_problem', file: files.decisionProblem },
      { entry: 'evidence_manifest', file: files.evidenceManifest },
      { entry: 'evidence_items', file: files.evidenceManifest,
        pointer: ['items'] },
      { entry: 'candidate_set', file: files.candidates },
      { entry: 'model_identities_and_params', file: files.modelConfiguration },
      { entry: 'candidate_binding', file: files.candidateBinding,
        transform: 'candidate_binding' },
    ];
    for (const binding of bindings) {
      const entry = manifest.entries[binding.entry];
      const file = binding.file;
      if (!entry || !file || !file.present || !file.text) continue;
      if (binding.transform) continue; // subject is not the file verbatim
      let canonical;
      try {
        if (binding.pointer) {
          const tree = parseJsonPreservingNumbers(file.text);
          const node = selectPath(tree, binding.pointer);
          if (node === undefined) continue;
          canonical = canonicalize(node);
        } else if (file.pointer) {
          // the file holds the subject under a pointer (settling arms)
          continue;
        } else {
          canonical = canonicalFromText(file.text);
        }
      } catch (error) {
        addProblem(problems, 'error', file.path,
          `could not re-serialise for freeze entry "${binding.entry}"`,
          error.message);
        continue;
      }
      await check('freeze_entry', file.path,
        `freeze entry "${binding.entry}"`, entry.sha256,
        await io.sha256(canonical));
    }
    // The compiler artifact directory publishes a per-file hash table.
    const perFile = manifest.entries.compiler_artifact_dir_per_file;
    if (perFile && perFile.detail && typeof perFile.detail === 'object') {
      const compilerDir = compilerDirFor(run, manifest);
      const table = {};
      for (const [name, expected] of Object.entries(perFile.detail)) {
        const read = await io.readText(`${compilerDir}/${name}`);
        if (!read.ok) {
          addProblem(problems, 'error', `${compilerDir}/${name}`,
            'file named by the freeze manifest could not be read',
            read.error || 'not found');
          continue;
        }
        const actual = await io.sha256(read.text);
        table[name] = actual;
        await check('compiler_file', `${compilerDir}/${name}`,
          `compiler artifact ${name}`, expected, actual);
      }
      const aggregate = manifest.entries.compiler_artifact_dir_aggregate;
      if (aggregate && Object.keys(table).length
          === Object.keys(perFile.detail).length) {
        await check('compiler_aggregate', compilerDir,
          'compiler artifact directory aggregate', aggregate.sha256,
          await io.sha256(canonicalize(table)));
      }
    }
  }

  return { checks, problems };
}

/**
 * Where the compiler artifacts named by the freeze manifest live.  The
 * manifest records an absolute path from the recording machine; the viewer
 * maps it back to this checkout by keeping only the part from the artifact
 * root onwards.  If that cannot be done the caller gets a loud read error
 * naming the file, not a silent skip.
 */
function compilerDirFor(run, manifest) {
  const aggregate = manifest.entries.compiler_artifact_dir_aggregate;
  const recorded = aggregate && aggregate.detail && aggregate.detail.path;
  if (typeof recorded === 'string') {
    const marker = `${ARTIFACT_ROOT}/`;
    const at = recorded.indexOf(marker);
    if (at !== -1) return recorded.slice(at);
  }
  return `${run.dir}/compiler`;
}

/* ------------------------------------------------------------------ */
/* header                                                              */
/* ------------------------------------------------------------------ */

function firstString(...values) {
  for (const value of values) {
    if (typeof value === 'string' && value !== '') return value;
  }
  return null;
}

function assembleHeader(run, files, branches, problems) {
  const model = files.modelConfiguration && files.modelConfiguration.json;
  const env = files.environment && files.environment.json;
  const identity = files.runIdentity && files.runIdentity.json;
  const evidence = files.evidenceManifest && files.evidenceManifest.json;
  const trace = files.traceReport && files.traceReport.json;
  const manifest = files.freezeManifest && files.freezeManifest.json;
  const probe = files.providerProbe && files.providerProbe.json;
  const arm = files.armDesign && files.armDesign.json;

  const header = {
    banner: VIEWER_BANNER,
    bannerSources: [files.environment, files.runIdentity]
      .filter((f) => f && f.json && f.json.label === VIEWER_BANNER)
      .map((f) => f.path),
    runLabel: `${run.groupLabel} -- ${run.label}`,
    phase: run.phase,
    model: {
      provider: model ? model.provider : null,
      name: model ? model.model : null,
      baseUrl: model ? model.base_url : null,
      roles: model ? model.roles : null,
      retryPolicy: model ? model.retry_policy : null,
      samplingNote: model ? model.sampling_note : null,
      source: files.modelConfiguration ? files.modelConfiguration.path : null,
      servedModelReportedByProvider: probe && probe.pre_run
        ? probe.pre_run.served_model_reported_by_provider : null,
      probeSource: probe ? files.providerProbe.path : null,
    },
    environment: env ? {
      repositorySha: env.repository_sha,
      python: env.python,
      platform: env.platform,
      recordedAt: env.recorded_at,
      harnessVersion: env.harness_version,
      source: files.environment.path,
    } : null,
    window: identity ? {
      start: firstString(identity.run_start_utc, identity.window_start_utc),
      cutoff: firstString(identity.cutoff_utc, identity.window_cutoff_utc),
      historicalCutoff: identity.historical_cutoff || null,
      source: files.runIdentity.path,
    } : null,
    question: identity ? identity.question : null,
    compiler: {
      version: identity ? identity.compiler_version : null,
      status: identity ? identity.compiler_status : null,
      reason: identity ? identity.compiler_reason : null,
      compiledWorldHash: manifest && manifest.entries
        && manifest.entries.compiled_decision_world
        ? manifest.entries.compiled_decision_world.sha256 : null,
      compilerDirAggregate: manifest && manifest.entries
        && manifest.entries.compiler_artifact_dir_aggregate
        ? manifest.entries.compiler_artifact_dir_aggregate.sha256 : null,
      source: files.freezeManifest ? files.freezeManifest.path : null,
    },
    plan: {
      worldId: trace ? trace.world_id : null,
      basePlanId: trace ? trace.base_plan_id : null,
      basePlanContentHash: trace ? trace.base_plan_content_hash : null,
      baseSnapshotId: trace ? trace.base_snapshot_id : null,
      baseSeed: trace ? trace.base_seed : null,
      planFreezeHash: manifest && manifest.entries
        && manifest.entries.concordia_initialization_plan
        ? manifest.entries.concordia_initialization_plan.sha256 : null,
      source: files.traceReport ? files.traceReport.path : null,
    },
    evidence: evidence ? {
      counts: evidence.classification_counts,
      rules: evidence.classification_rules,
      notes: evidence.notes,
      actorNames: evidence.actor_names,
      source: files.evidenceManifest.path,
    } : {
      counts: null,
      absentReason: 'settling-arm runs reuse the frozen scenario world and '
        + 'do not re-publish an evidence manifest of their own',
      source: null,
    },
    candidateSource: {
      declared: run.candidateSource,
      verified: null,
      source: files.candidates ? files.candidates.path : null,
    },
    arm: arm ? {
      arm: arm.arm,
      armLabel: arm.arm_label,
      armNote: arm.arm_note,
      rep: arm.rep,
      seed: exactNumber(files.armDesign, ['seed']),
      branchSeed: exactNumber(files.armDesign, ['branch_seed']),
      maxSteps: arm.max_steps,
      difference: arm.arm_difference,
      counted: run.counted,
      note: run.note || null,
      source: files.armDesign.path,
    } : null,
    branchSeeds: branches.map((b) => ({
      candidateId: b.candidateId,
      branchId: b.branchId,
      branchSeed: b.branchSeed,
      planId: b.planId,
      planContentHash: b.planContentHash,
    })),
  };

  const candidates = files.candidates && files.candidates.json;
  if (Array.isArray(candidates)) {
    const sources = [...new Set(candidates
      .map((c) => (c.provenance ? c.provenance.source : null)))];
    header.candidateSource.verified = sources.join(', ');
    header.candidateSource.perCandidate = candidates.map((c) => ({
      candidateId: c.candidate_id,
      source: c.provenance ? c.provenance.source : null,
      generatorConfigHash: c.provenance ? c.provenance.generator_config_hash : null,
    }));
    const declaredMatches = sources.every((s) => (
      (run.candidateSource === 'supplied' && s === 'user_supplied')
      || (run.candidateSource === 'generated' && s === 'generated')));
    if (!declaredMatches) {
      addProblem(problems, 'error', files.candidates.path,
        'candidate provenance does not match the run\'s declared candidate '
        + 'source', `declared=${run.candidateSource} recorded=${sources.join(', ')}`);
    }
  } else if (files.armDesign && files.armDesign.json) {
    header.candidateSource.verified = 'user_supplied (frozen settling '
      + 'candidate, recorded in arm_design.json)';
    header.candidateSource.source = files.armDesign.path;
  }
  return header;
}

/** Every limitation the artifacts state, with the file that states it. */
function assembleLimitations(files) {
  const out = [];
  const push = (file, text, label) => {
    if (file && file.present && typeof text === 'string' && text !== '') {
      out.push({ label, text, source: file.path });
    }
  };
  const model = files.modelConfiguration && files.modelConfiguration.json;
  push(files.modelConfiguration, model && model.sampling_note,
    'Sampling');
  const evaluator = files.evaluatorLedger && files.evaluatorLedger.json;
  push(files.evaluatorLedger, evaluator && evaluator.measurement_limitation,
    'Measurement');
  push(files.evaluatorLedger, evaluator && evaluator.status_rule,
    'Terminal-status rule');
  const recommendation = files.recommendationResult
    && files.recommendationResult.json;
  push(files.recommendationResult, recommendation && recommendation.run_limitations,
    'Result provenance');
  const audit = files.measurementAudit && files.measurementAudit.json;
  if (audit && files.measurementAudit.present) {
    push(files.measurementAudit,
      `${audit.status || ''} -- ${audit.purpose || ''}`.trim(),
      'Post-hoc measurement audit');
  }
  const delivery = files.deliveryCheck && files.deliveryCheck.json;
  if (delivery && files.deliveryCheck.present) {
    const verdict = firstString(delivery.verdict,
      delivery.content_delivered_to_recipient === false
        ? 'candidate content did not reach the recipient' : null);
    push(files.deliveryCheck, verdict, 'Candidate delivery');
  }
  const measurement = files.settlingMeasurement && files.settlingMeasurement.json;
  if (measurement && measurement.sender_enactment) {
    push(files.settlingMeasurement, measurement.sender_enactment.method,
      'Enactment measurement method');
  }
  return out;
}

/* ------------------------------------------------------------------ */
/* the whole run                                                       */
/* ------------------------------------------------------------------ */

/**
 * Assemble one complete run view model.
 *
 * @param {object} run   a catalog entry
 * @param {{readText: function, sha256: function}} io
 * @param {{verify?: boolean}} [options]
 */
export async function assembleRun(run, io, options = {}) {
  const verify = options.verify !== false;
  const problems = [];
  const files = await loadRunFiles(run, io, problems);
  const listed = discoverBranches(run, files, problems);

  const branches = [];
  for (const entry of listed) {
    const branchFiles = await loadBranchFiles(run, entry.candidateId, io,
      problems);
    const timeline = assembleBranchTimeline({
      candidateId: entry.candidateId,
      branchId: entry.branchId,
      files: branchFiles,
    });
    problems.push(...timeline.problems);
    const committedRows = ((branchFiles.committedEvents
      && branchFiles.committedEvents.rows) || [])
      .filter((row) => !row.__malformed);
    const evaluatorLedger = files.evaluatorLedger && files.evaluatorLedger.json;
    const metrics = assembleMetrics({
      candidateId: entry.candidateId,
      branchFiles,
      evaluatorLedger,
      evaluatorPath: files.evaluatorLedger ? files.evaluatorLedger.path : null,
      committedRows,
    });
    problems.push(...metrics.problems);

    const result = branchFiles.branchResult && branchFiles.branchResult.json;
    if (result && result.branch_id && entry.branchId
        && result.branch_id !== entry.branchId) {
      addProblem(problems, 'error', branchFiles.branchResult.path,
        'branch_id disagrees with the trace report',
        `branch_result=${result.branch_id} trace_report=${entry.branchId}`);
    }
    const candidate = Array.isArray(files.candidates && files.candidates.json)
      ? files.candidates.json.find((c) => c.candidate_id === entry.candidateId)
      : null;

    branches.push({
      ...entry,
      files: branchFiles,
      timeline,
      metrics: metrics.metrics,
      evaluatorEntry: metrics.ledgerEntry,
      branchResult: result || null,
      candidate,
      infrastructureErrors: (result && result.infrastructure_errors) || [],
      terminalStatusFromResult: result ? result.terminal_status : null,
      runtimeStats: result ? result.runtime_stats : null,
      interventionDelivered: result ? result.intervention_delivered : null,
    });
  }

  const header = assembleHeader(run, files, branches, problems);
  const limitations = assembleLimitations(files);

  const recommendation = files.recommendationResult
    && files.recommendationResult.json;
  const refusalFile = files.rankingRefusal && files.rankingRefusal.present
    ? files.rankingRefusal : null;
  const refusalJson = refusalFile ? refusalFile.json : null;
  const recommendationIsRefusal = Boolean(recommendation
    && recommendation.refused === true);
  const outcome = {
    kind: recommendationIsRefusal || refusalJson ? 'refusal' : 'ranking',
    refusal: recommendationIsRefusal ? recommendation : refusalJson,
    refusalSource: recommendationIsRefusal
      ? files.recommendationResult.path
      : (refusalFile ? refusalFile.path : null),
    ranking: recommendationIsRefusal ? null : recommendation,
    rankingSource: recommendationIsRefusal
      ? null
      : (files.recommendationResult ? files.recommendationResult.path : null),
  };
  if (outcome.kind === 'refusal' && recommendationIsRefusal && refusalJson
      && canonicalize(refusalJson) !== canonicalize(recommendation)) {
    addProblem(problems, 'warning', files.rankingRefusal.path,
      'ranking_refusal.json and recommendation_result.json are both present '
      + 'and differ', 'both are shown');
  }
  if (outcome.kind === 'ranking' && recommendation
      && !Array.isArray(recommendation.ranking)) {
    addProblem(problems, 'error', files.recommendationResult.path,
      'recommendation result is neither a refusal nor a ranking', null);
  }

  let hashReport = { checks: [], problems: [], skipped: true };
  if (verify) {
    hashReport = await verifyHashes({ run, files, branches, io });
    hashReport.skipped = false;
    problems.push(...hashReport.problems);
  }

  return {
    run,
    header,
    files,
    branches,
    outcome,
    limitations,
    hashReport,
    problems,
    auditorOnlyNote: AUDITOR_ONLY_NOTE,
    documents: [
      { label: 'Session README (all runs)', path: SESSION_FILES.readme.path },
      { label: 'Session call accounting',
        path: SESSION_FILES.callAccounting.path },
      ...(run.docs || []).map((doc) => ({ label: doc.label, path: doc.path })),
    ],
  };
}
