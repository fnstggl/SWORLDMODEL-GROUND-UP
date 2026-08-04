#!/usr/bin/env node
/**
 * Headless driver for the viewer.
 *
 * It runs the viewer's OWN assembly (`lib/assemble.js`) and its OWN
 * rendering (`lib/render.js`) against a repository checkout, then prints
 * the assembled view and the rendered HTML as JSON.  The automated
 * equivalence test uses this so it checks the real viewer logic instead of
 * a Python re-implementation of it.
 *
 * Usage:
 *   node viewer/node_driver.js --root <repo-root> --run <run-id>
 *                              [--branch <candidate-id>] [--no-verify]
 *                              [--list] [--html]
 */

import { runById, RUNS } from './lib/catalog.js';
import { assembleRun } from './lib/assemble.js';
import { renderBranchReplay } from './lib/render.js';
import { nodeIo } from './lib/io_node.js';
import { browserIo } from './lib/io_browser.js';

function parseArgs(argv) {
  const args = { root: process.cwd(), verify: true, html: false };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === '--root') { args.root = argv[++i]; }
    else if (token === '--run') { args.run = argv[++i]; }
    else if (token === '--branch') { args.branch = argv[++i]; }
    else if (token === '--no-verify') { args.verify = false; }
    else if (token === '--list') { args.list = true; }
    else if (token === '--html') { args.html = true; }
    else if (token === '--http') { args.http = argv[++i]; }
    else throw new Error(`unknown argument: ${token}`);
  }
  return args;
}

function summariseBranch(branch, view) {
  return {
    candidateId: branch.candidateId,
    branchId: branch.branchId,
    branchSeed: branch.branchSeed,
    terminalStatus: branch.terminalStatus,
    terminalStatusFromResult: branch.terminalStatusFromResult,
    stepsCompleted: branch.stepsCompleted,
    entryKinds: branch.timeline.entries.map((entry) => entry.kind),
    entryLabels: branch.timeline.entries.map((entry) => entry.label),
    committedEvents: branch.timeline.committedStream.map((row) => ({
      index: row.index,
      eventId: row.event_id,
      sha256: row.sha256,
      text: row.text,
    })),
    callIds: branch.timeline.callIds,
    ledgerCallOrder: branch.timeline.ledgerCallOrder,
    metrics: Object.fromEntries(Object.entries(branch.metrics)
      .map(([name, metric]) => [name, {
        value: metric.value,
        computedFrom: metric.computedFrom,
        citedEventIds: metric.citedEvents.map((c) => c.eventId),
      }])),
    candidateProvenance: branch.candidate && branch.candidate.provenance
      ? branch.candidate.provenance.source : null,
    infrastructureErrors: branch.infrastructureErrors,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.list) {
    process.stdout.write(JSON.stringify(RUNS.map((run) => ({
      id: run.id, kind: run.kind, phase: run.phase, dir: run.dir,
      label: `${run.groupLabel} -- ${run.label}`,
    })), null, 2));
    return;
  }
  const run = runById(args.run);
  if (!run) throw new Error(`no run with id ${args.run}`);
  // `--http` drives the BROWSER io adapter (fetch + WebCrypto) against a
  // running `viewer/serve.py`, so the path the browser takes is exercised
  // too, not only the filesystem path.
  const io = args.http
    ? browserIo({ base: args.http.endsWith('/') ? args.http : `${args.http}/` })
    : nodeIo(args.root);
  const view = await assembleRun(run, io, { verify: args.verify });

  const branchIndex = args.branch
    ? view.branches.findIndex((b) => b.candidateId === args.branch)
    : 0;
  if (args.branch && branchIndex === -1) {
    throw new Error(`no branch ${args.branch} in run ${args.run}`);
  }

  const payload = {
    runId: run.id,
    runDir: run.dir,
    label: `${run.groupLabel} -- ${run.label}`,
    banner: view.header.banner,
    header: {
      model: view.header.model,
      environment: view.header.environment,
      window: view.header.window,
      compiler: view.header.compiler,
      plan: view.header.plan,
      evidenceCounts: view.header.evidence ? view.header.evidence.counts : null,
      candidateSource: view.header.candidateSource,
      arm: view.header.arm,
      branchSeeds: view.header.branchSeeds,
    },
    limitations: view.limitations,
    documents: view.documents,
    outcome: {
      kind: view.outcome.kind,
      bestCandidateId: view.outcome.ranking
        ? view.outcome.ranking.best_candidate_id : null,
      refusalType: view.outcome.refusal
        ? view.outcome.refusal.error_type : null,
      source: view.outcome.kind === 'refusal'
        ? view.outcome.refusalSource : view.outcome.rankingSource,
    },
    branches: view.branches.map((branch) => summariseBranch(branch, view)),
    selectedBranchIndex: branchIndex,
    problems: view.problems,
    hashChecks: {
      total: view.hashReport.checks.length,
      matched: view.hashReport.checks.filter((c) => c.ok).length,
      mismatched: view.hashReport.checks.filter((c) => !c.ok)
        .map((c) => ({ kind: c.kind, path: c.path, label: c.label,
          expected: c.expected, actual: c.actual })),
      kinds: [...new Set(view.hashReport.checks.map((c) => c.kind))],
    },
    files: Object.fromEntries(Object.entries(view.files).map(([key, file]) => [
      key, { path: file.path, present: file.present, ok: file.ok,
        absentReason: file.absentReason || null },
    ])),
  };
  if (args.html) {
    payload.renderedHtml = renderBranchReplay(view, branchIndex);
  }
  process.stdout.write(JSON.stringify(payload));
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
});
