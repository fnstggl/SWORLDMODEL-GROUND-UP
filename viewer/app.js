/**
 * The browser shell: run/branch selection, playback, deep links.
 *
 * All data assembly lives in `lib/assemble.js` and all HTML in
 * `lib/render.js`, so the automated equivalence test can drive exactly the
 * same code through `node_driver.js`.  This file only wires events.
 */

import { RUNS, runById, runGroups } from './lib/catalog.js';
import { assembleRun } from './lib/assemble.js';
import { renderBranchReplay } from './lib/render.js';
import { browserIo, hashingAvailable } from './lib/io_browser.js';

const app = document.getElementById('app');
const runSelect = document.getElementById('run-select');
const branchSelect = document.getElementById('branch-select');
const scrub = document.getElementById('scrub');
const position = document.getElementById('position');
const speedSelect = document.getElementById('speed');

const io = browserIo({ base: '../' });
const cache = new Map();

const state = {
  runId: RUNS[0].id,
  branchIndex: 0,
  entryIndex: 0,
  entryCount: 0,
  playing: false,
  timer: null,
  view: null,
};

function readHash() {
  const raw = window.location.hash.replace(/^#/, '');
  const params = new URLSearchParams(raw);
  const runId = params.get('run');
  if (runId && runById(runId)) state.runId = runId;
  const branch = params.get('branch');
  if (branch !== null) state.pendingBranchId = branch;
  const entry = params.get('entry');
  if (entry !== null) state.pendingEntry = Number(entry);
}

function writeHash() {
  const branch = state.view && state.view.branches[state.branchIndex];
  const params = new URLSearchParams();
  params.set('run', state.runId);
  if (branch) params.set('branch', branch.candidateId);
  params.set('entry', String(state.entryIndex));
  const next = `#${params.toString()}`;
  if (window.location.hash !== next) {
    window.history.replaceState(null, '', next);
  }
}

function buildRunSelect() {
  runSelect.innerHTML = '';
  for (const group of runGroups()) {
    const optgroup = document.createElement('optgroup');
    optgroup.label = group.label;
    for (const run of group.runs) {
      const option = document.createElement('option');
      option.value = run.id;
      option.textContent = run.label;
      optgroup.appendChild(option);
    }
    runSelect.appendChild(optgroup);
  }
  runSelect.value = state.runId;
}

function buildBranchSelect(view) {
  branchSelect.innerHTML = '';
  view.branches.forEach((branch, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    const events = branch.timeline.committedStream.length;
    option.textContent = `${branch.candidateId} -- ${branch.terminalStatus}`
      + ` (${events} committed events)`;
    branchSelect.appendChild(option);
  });
  branchSelect.value = String(state.branchIndex);
}

function fatal(message, detail) {
  app.innerHTML = `<div class="problems bad"><h3>${message}</h3>
    <pre class="verbatim">${detail || ''}</pre></div>`;
}

async function loadRun(runId) {
  const run = runById(runId);
  if (!run) { fatal(`No run with id ${runId}.`); return null; }
  if (cache.has(runId)) return cache.get(runId);
  app.innerHTML = `<p class="loading">Loading
    <code>${run.dir}</code> ...</p>`;
  const view = await assembleRun(run, io, { verify: hashingAvailable() });
  cache.set(runId, view);
  return view;
}

function activate(index) {
  const details = app.querySelectorAll('.entry-detail');
  const items = app.querySelectorAll('.tl-item');
  if (!details.length) return;
  const clamped = Math.max(0, Math.min(index, details.length - 1));
  state.entryIndex = clamped;
  details.forEach((node, i) => node.classList.toggle('active', i === clamped));
  items.forEach((node, i) => node.classList.toggle('current', i === clamped));
  scrub.value = String(clamped);
  position.textContent = `${clamped + 1} / ${details.length}`;
  const current = items[clamped];
  if (current && current.scrollIntoView) {
    current.scrollIntoView({ block: 'nearest' });
  }
  const detail = details[clamped];
  if (detail) detail.scrollTop = 0;
  writeHash();
}

function stop() {
  state.playing = false;
  if (state.timer) { window.clearInterval(state.timer); state.timer = null; }
  document.getElementById('btn-play').innerHTML = '&#9654;';
}

function play() {
  if (state.playing) { stop(); return; }
  state.playing = true;
  document.getElementById('btn-play').innerHTML = '&#10074;&#10074;';
  const interval = Number(speedSelect.value);
  state.timer = window.setInterval(() => {
    if (state.entryIndex >= state.entryCount - 1) { stop(); return; }
    activate(state.entryIndex + 1);
  }, interval);
}

function wireReplay() {
  app.querySelectorAll('[data-goto]').forEach((button) => {
    button.addEventListener('click', () => {
      stop();
      activate(Number(button.dataset.goto));
    });
  });
  app.querySelectorAll('[data-goto-event]').forEach((button) => {
    button.addEventListener('click', () => {
      const eventId = button.dataset.gotoEvent;
      const target = [...app.querySelectorAll('.entry-detail')]
        .findIndex((node) => node.querySelector(
          `[data-event-id="${CSS.escape(eventId)}"]`));
      if (target >= 0) {
        stop();
        activate(target);
        app.querySelector('.replay-body').scrollIntoView({ block: 'start' });
      }
    });
  });
}

async function renderCurrent() {
  const view = await loadRun(state.runId);
  if (!view) return;
  state.view = view;
  if (state.pendingBranchId) {
    const found = view.branches
      .findIndex((b) => b.candidateId === state.pendingBranchId);
    state.branchIndex = found >= 0 ? found : 0;
    state.pendingBranchId = null;
  }
  if (state.branchIndex >= view.branches.length) state.branchIndex = 0;
  buildBranchSelect(view);
  app.innerHTML = renderBranchReplay(view, state.branchIndex);
  const branch = view.branches[state.branchIndex];
  state.entryCount = branch ? branch.timeline.entries.length : 0;
  scrub.max = String(Math.max(0, state.entryCount - 1));
  wireReplay();
  let start = 0;
  if (state.pendingEntry !== undefined && state.pendingEntry !== null) {
    start = state.pendingEntry;
    state.pendingEntry = null;
  }
  activate(start);
}

runSelect.addEventListener('change', async () => {
  stop();
  state.runId = runSelect.value;
  state.branchIndex = 0;
  await renderCurrent();
});

branchSelect.addEventListener('change', async () => {
  stop();
  state.branchIndex = Number(branchSelect.value);
  await renderCurrent();
});

document.getElementById('btn-prev').addEventListener('click', () => {
  stop(); activate(state.entryIndex - 1);
});
document.getElementById('btn-next').addEventListener('click', () => {
  stop(); activate(state.entryIndex + 1);
});
document.getElementById('btn-first').addEventListener('click', () => {
  stop(); activate(0);
});
document.getElementById('btn-last').addEventListener('click', () => {
  stop(); activate(state.entryCount - 1);
});
document.getElementById('btn-play').addEventListener('click', play);
scrub.addEventListener('input', () => { stop(); activate(Number(scrub.value)); });
speedSelect.addEventListener('change', () => { if (state.playing) { stop(); play(); } });

window.addEventListener('keydown', (event) => {
  if (event.target instanceof HTMLSelectElement
      || event.target instanceof HTMLInputElement) return;
  if (event.key === 'ArrowLeft') { stop(); activate(state.entryIndex - 1); }
  else if (event.key === 'ArrowRight') { stop(); activate(state.entryIndex + 1); }
  else if (event.key === ' ') { event.preventDefault(); play(); }
});

async function boot() {
  if (!hashingAvailable()) {
    document.getElementById('insecure-warning').hidden = false;
  }
  readHash();
  buildRunSelect();
  runSelect.value = state.runId;
  try {
    await renderCurrent();
  } catch (error) {
    fatal('The viewer could not assemble this run.',
      `${error.stack || error.message}`);
  }
}

boot();
