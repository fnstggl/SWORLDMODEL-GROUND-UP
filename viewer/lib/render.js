/**
 * Rendering: view model in, HTML string out.
 *
 * The browser injects exactly these strings and the automated equivalence
 * test parses exactly these strings, so "what the test checked" and "what
 * is on screen" are the same bytes.
 *
 * Load-bearing conventions:
 *  - every committed event carries `data-committed-index`, `data-event-id`
 *    and `data-event-sha256`, and its text is inside a `<pre>` marked
 *    `data-event-text-for`;
 *  - every model call id appears as `data-call-id`;
 *  - every metric renders its citations in `data-citations`;
 *  - anything an actor never saw is wrapped in `.auditor-only`, which
 *    always paints its own banner.
 */

export function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Inverse of {@link esc}; the equivalence test uses the same mapping. */
export function unesc(value) {
  return String(value)
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&gt;/g, '>')
    .replace(/&lt;/g, '<')
    .replace(/&amp;/g, '&');
}

function fileHref(path) {
  return `../${path}`;
}

function sourceLink(path, label) {
  if (!path) return '<span class="src none">no source file</span>';
  return `<a class="src" href="${esc(fileHref(path))}" target="_blank" `
    + `rel="noopener">${esc(label || path)}</a>`;
}

function pre(text, extraAttrs = '') {
  // An empty box would read as a rendering fault. Say which kind of
  // nothing this is instead: absent from the record, or recorded empty.
  if (text === null || text === undefined) {
    return `<pre class="verbatim empty" ${extraAttrs}>(this field is not `
      + `present in the record)</pre>`;
  }
  if (text === '') {
    return `<pre class="verbatim empty" ${extraAttrs}>(recorded as an empty `
      + `string)</pre>`;
  }
  return `<pre class="verbatim" ${extraAttrs}>${esc(text)}</pre>`;
}

function json(value) {
  return pre(JSON.stringify(value, null, 2));
}

/**
 * Render a field that the artifacts explicitly mark unavailable.  The
 * reason is shown; it is never hidden and never replaced by a guess.
 */
function unavailableBlock(reason) {
  return `<div class="unavailable"><span class="tag">RECORDED AS `
    + `UNAVAILABLE</span><p>${esc(reason)}</p></div>`;
}

function unavailableReason(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)
      && typeof value.unavailable === 'string') return value.unavailable;
  return null;
}

function auditorOnly(title, bodyHtml, note) {
  return `<section class="auditor-only">
    <div class="auditor-band">AUDITOR-ONLY -- NO ACTOR EVER SAW THIS</div>
    <h4>${esc(title)}</h4>
    ${note ? `<p class="muted">${esc(note)}</p>` : ''}
    ${bodyHtml}
  </section>`;
}

/* ------------------------------------------------------------------ */
/* header                                                              */
/* ------------------------------------------------------------------ */

export function renderBanner(view) {
  const h = view.header;
  return `<div class="banner">
    <div class="banner-main">${esc(h.banner)}</div>
    <div class="banner-sub">This viewer is a PRESENTATION LAYER. The frozen
      artifacts under <code>${esc(view.run.dir)}</code> are the source of
      truth; nothing here is regenerated, summarised over, or recomputed
      into a new result.</div>
  </div>`;
}

function chip(label, value, source) {
  if (value === null || value === undefined || value === '') {
    return `<div class="chip missing"><span class="k">${esc(label)}</span>
      <span class="v">not recorded</span></div>`;
  }
  return `<div class="chip"><span class="k">${esc(label)}</span>
    <span class="v" title="${esc(value)}">${esc(value)}</span>
    ${source ? sourceLink(source, 'src') : ''}</div>`;
}

export function renderHeader(view) {
  const h = view.header;
  const m = h.model;
  const env = h.environment;
  const chips = [
    chip('run', h.runLabel, null),
    chip('phase', h.phase, null),
    chip('model', m.name, m.source),
    chip('provider', m.provider, m.source),
    chip('endpoint', m.baseUrl, m.source),
    chip('served model (probe)', m.servedModelReportedByProvider, m.probeSource),
    chip('repository SHA', env ? env.repositorySha : null,
      env ? env.source : null),
    chip('compiler', h.compiler.version
      ? `${h.compiler.version} (${h.compiler.status})` : null,
      h.compiler.source),
    chip('compiled world sha256', h.compiler.compiledWorldHash,
      h.compiler.source),
    chip('base plan', h.plan.basePlanId, h.plan.source),
    chip('base plan content hash', h.plan.basePlanContentHash, h.plan.source),
    chip('plan freeze sha256', h.plan.planFreezeHash, h.compiler.source),
    chip('world id', h.plan.worldId, h.plan.source),
    chip('base seed', h.plan.baseSeed, h.plan.source),
    chip('candidates', h.candidateSource.verified
      ? `${h.candidateSource.declared.toUpperCase()} (recorded: `
        + `${h.candidateSource.verified})`
      : h.candidateSource.declared.toUpperCase(),
      h.candidateSource.source),
    chip('window', h.window
      ? `${h.window.start} -> ${h.window.cutoff}` : null,
      h.window ? h.window.source : null),
  ];
  if (h.window && h.window.historicalCutoff) {
    chips.push(chip('historical knowledge cutoff', h.window.historicalCutoff,
      h.window.source));
  }
  if (h.arm) {
    chips.push(chip('arm', `${String(h.arm.arm).toUpperCase()} -- `
      + `${h.arm.armLabel}`, h.arm.source));
    chips.push(chip('counted in reported rates',
      h.arm.counted ? 'yes' : 'NO (harness shakedown)', h.arm.source));
  }

  const evidence = h.evidence;
  let evidenceHtml;
  if (evidence && evidence.counts) {
    const counts = Object.entries(evidence.counts)
      .map(([k, v]) => `<li><b>${esc(k)}</b>: ${esc(v)}<span class="muted"> --
        ${esc((evidence.rules && evidence.rules[k]) || '')}</span></li>`)
      .join('');
    evidenceHtml = `<ul class="evidence">${counts}</ul>
      <p class="muted">${esc(evidence.notes || '')}
      ${sourceLink(evidence.source, 'evidence_manifest.json')}</p>`;
  } else {
    evidenceHtml = unavailableBlock(evidence.absentReason
      || 'no evidence manifest was written for this run');
  }

  const seeds = h.branchSeeds.map((b) => `<tr>
      <td>${esc(b.candidateId)}</td><td class="mono">${esc(b.branchId)}</td>
      <td class="mono">${esc(b.branchSeed)}</td>
      <td class="mono">${esc(b.planId)}</td>
      <td class="mono small">${esc(b.planContentHash)}</td></tr>`).join('');

  return `<div class="header-grid">
    <div class="chips">${chips.join('')}</div>
    <details class="panel" open>
      <summary>Evidence classification</summary>${evidenceHtml}</details>
    <details class="panel">
      <summary>Branch seeds and plan hashes</summary>
      <table class="grid"><thead><tr><th>candidate</th><th>branch id</th>
        <th>branch seed</th><th>plan id</th><th>plan content hash</th></tr>
        </thead><tbody>${seeds}</tbody></table>
      <p class="muted">${sourceLink(h.plan.source, 'trace_report.json')}</p>
    </details>
    ${renderLimitations(view)}
    ${renderDocuments(view)}
    ${h.arm && h.arm.note ? `<div class="notice">${esc(h.arm.note)}</div>` : ''}
  </div>`;
}

/** Written reports that belong to this run, linked, never summarised. */
export function renderDocuments(view) {
  const documents = view.documents || [];
  if (!documents.length) return '';
  const items = documents.map((doc) => `<li>
    <a href="${esc(fileHref(doc.path))}" target="_blank"
      rel="noopener">${esc(doc.label)}</a>
    <code class="small muted">${esc(doc.path)}</code></li>`).join('');
  return `<details class="panel"><summary>Written reports for this run
    (opened as-is; this viewer does not summarise them)</summary>
    <ul>${items}</ul></details>`;
}

export function renderLimitations(view) {
  if (!view.limitations.length) return '';
  const items = view.limitations.map((item) => `<li>
    <b>${esc(item.label)}.</b> ${esc(item.text)}
    ${sourceLink(item.source, 'src')}</li>`).join('');
  return `<details class="panel limitations" open>
    <summary>Known limitations, as the artifacts state them</summary>
    <ul>${items}</ul></details>`;
}

export function renderProblems(view) {
  const errors = view.problems.filter((p) => p.severity === 'error');
  const warnings = view.problems.filter((p) => p.severity !== 'error');
  if (!errors.length && !warnings.length) {
    const checked = view.hashReport.skipped ? 0 : view.hashReport.checks.length;
    return `<div class="problems ok">No artifact problem found.
      ${checked} published hash${checked === 1 ? '' : 'es'} recomputed and
      matched.</div>`;
  }
  const row = (p) => `<li class="${esc(p.severity)}">
    <span class="sev">${esc(p.severity.toUpperCase())}</span>
    <code>${esc(p.file)}</code>: ${esc(p.problem)}
    ${p.detail ? `<div class="detail">${esc(p.detail)}</div>` : ''}</li>`;
  return `<div class="problems bad">
    <h3>${errors.length} error${errors.length === 1 ? '' : 's'},
      ${warnings.length} warning${warnings.length === 1 ? '' : 's'}
      in the artifacts</h3>
    <ul>${[...errors, ...warnings].map(row).join('')}</ul></div>`;
}

/* ------------------------------------------------------------------ */
/* timeline                                                            */
/* ------------------------------------------------------------------ */

export function renderTimelineList(branch) {
  const items = branch.timeline.entries.map((entry, index) => {
    const event = entry.committedEvent;
    const guardFired = entry.kind === 'step' && entry.record.guard
      && entry.record.guard.intervened === true;
    const actor = entry.kind === 'step'
      ? (entry.record.active_actor && entry.record.active_actor.name) : '';
    const badges = [];
    if (entry.kind === 'genesis') badges.push('<span class="badge">start</span>');
    if (entry.kind === 'unattached') {
      badges.push('<span class="badge bad">unattached</span>');
    }
    if (entry.kind === 'malformed') {
      badges.push('<span class="badge bad">malformed</span>');
    }
    if (guardFired) badges.push('<span class="badge guard">guard</span>');
    return `<li class="tl-item" data-entry-index="${index}"
        data-entry-kind="${esc(entry.kind)}"
        ${entry.step !== undefined ? `data-step="${esc(entry.step)}"` : ''}>
      <button type="button" class="tl-btn" data-goto="${index}">
        <span class="tl-label">${esc(entry.label)}</span>
        <span class="tl-actor">${esc(actor)}</span>
        <span class="tl-event">${event ? esc(event.event_id) : '--'}</span>
        ${badges.join('')}
      </button></li>`;
  }).join('');
  return `<ol class="timeline">${items}</ol>`;
}

function renderObservationsForActor(entry, actorName) {
  const delivered = entry.record.observations_delivered;
  if (!delivered || typeof delivered !== 'object') {
    return unavailableBlock('this step record contains no observations_delivered '
      + 'section');
  }
  const own = delivered[actorName];
  if (!own) {
    return `<div class="unavailable"><span class="tag">NOT RECORDED</span>
      <p>the step record has no observation slice for the active actor
      ${esc(actorName)}</p></div>`;
  }
  const rows = (entry.observationRows || [])
    .filter((row) => row.recipient === actorName);
  const queue = Array.isArray(own.queue_for_active_entity)
    ? own.queue_for_active_entity : [];
  return `<p class="muted">Delivered to the ACTIVE actor
      (${esc(actorName)}) -- this is what that actor received this step.</p>
    ${pre(own.delivered_text || '')}
    <details><summary>${queue.length} queued observation
      ${queue.length === 1 ? 'item' : 'items'}</summary>
      ${queue.map((item) => pre(item)).join('')}</details>
    ${rows.length ? `<p class="muted">Also recorded independently in
      observations.jsonl (${rows.length} row${rows.length === 1 ? '' : 's'}
      for this actor and step).</p>` : ''}`;
}

function renderActorPrompt(entry) {
  const requests = entry.record.actor_model_request;
  if (!Array.isArray(requests) || !requests.length) {
    const reason = unavailableReason(requests);
    return reason ? unavailableBlock(reason)
      : unavailableBlock('no actor model request is recorded for this step');
  }
  return requests.map((call) => {
    const messages = Array.isArray(call.messages) ? call.messages : [];
    return `<div class="call" data-call-id="${esc(call.call_id)}">
      <div class="call-head">request <code class="call-id"
        data-call-id="${esc(call.call_id)}">${esc(call.call_id)}</code></div>
      ${messages.map((msg) => `<div class="msg">
        <div class="role">${esc(msg.role)}</div>${pre(msg.content)}</div>`)
        .join('')}
    </div>`;
  }).join('');
}

function renderActorResponse(entry) {
  const response = entry.record.actor_raw_response;
  const reason = unavailableReason(response);
  if (reason) return unavailableBlock(reason);
  if (!response) {
    return unavailableBlock('no actor response is recorded for this step');
  }
  const calls = Array.isArray(response.recorded_calls)
    ? response.recorded_calls : [];
  return `${calls.map((call) => `<div class="call">
      <div class="call-head">response to <code class="call-id"
        data-call-id="${esc(call.call_id)}">${esc(call.call_id)}</code>
        <span class="mono small">sha256 ${esc(call.response_sha256)}</span>
      </div>${pre(call.response_raw)}</div>`).join('')}
    <div class="sub"><h5>value the engine recorded</h5>
      ${pre(response.engine_recorded_value)}</div>`;
}

function renderGameMaster(entry) {
  const input = entry.record.game_master_input;
  const response = entry.record.game_master_raw_response;
  const inputReason = unavailableReason(input);
  const inputHtml = inputReason ? unavailableBlock(inputReason)
    : (input ? Object.entries(input).map(([key, value]) => `<div class="sub">
        <h5>${esc(key)}</h5>${pre(value)}</div>`).join('')
      : unavailableBlock('no game master input is recorded for this step'));
  const responseReason = unavailableReason(response);
  let responseHtml;
  if (responseReason) responseHtml = unavailableBlock(responseReason);
  else if (!response) {
    responseHtml = unavailableBlock('no game master response is recorded');
  } else {
    const calls = Array.isArray(response.recorded_calls)
      ? response.recorded_calls : [];
    responseHtml = `${calls.map((call) => `<div class="call">
        <div class="call-head">game master call <code class="call-id"
          data-call-id="${esc(call.call_id)}">${esc(call.call_id)}</code>
          ${call.error ? `<span class="badge bad">error</span>` : ''}
          ${call.retry ? `<span class="badge">retry ${esc(call.retry)}</span>`
            : ''}</div>
        ${(call.request_messages || []).map((msg) => `<div class="msg">
          <div class="role">${esc(msg.role)}</div>${pre(msg.content)}</div>`)
          .join('')}
        <div class="sub"><h5>raw response</h5>${pre(call.response_raw)}</div>
      </div>`).join('')}
      <div class="sub"><h5>value the engine recorded</h5>
        ${pre(response.engine_recorded_value)}</div>`;
  }
  return `<div class="two-col"><div><h5>game master input</h5>${inputHtml}</div>
    <div><h5>game master response</h5>${responseHtml}</div></div>`;
}

function renderGuard(entry) {
  const before = entry.record.candidate_event_before_guard;
  const guard = entry.record.guard;
  const beforeReason = unavailableReason(before);
  let beforeHtml;
  if (beforeReason) beforeHtml = unavailableBlock(beforeReason);
  else if (!before) {
    beforeHtml = unavailableBlock('no pre-guard candidate event is recorded');
  } else if (before.equals_final_committed_event) {
    beforeHtml = `<p class="ok-note">Identical to the final committed event.
      ${esc(before.note || '')}</p>`;
  } else {
    beforeHtml = `${pre(before.excerpt)}
      ${before.note ? `<p class="muted">${esc(before.note)}</p>` : ''}
      ${typeof before.truncated_to_chars === 'number'
        ? `<p class="muted">Recorded excerpt is capped at
          ${esc(before.truncated_to_chars)} characters.</p>` : ''}`;
  }
  let guardHtml;
  if (!guard) guardHtml = unavailableBlock('no guard record for this step');
  else if (guard.intervened !== true) {
    guardHtml = `<p class="ok-note">No intervention.
      ${esc(guard.explanation || '')}</p>`;
  } else {
    guardHtml = `<div class="guard-fired">
      <div class="badge guard">GUARD INTERVENED</div>
      <p>${esc(guard.explanation || '')}</p>
      ${(guard.records || []).map((rec) => `<div class="sub">
        <div><b>active</b>: ${esc(rec.active)} &middot;
          <b>affected</b>: ${esc((rec.affected || []).join(', '))}</div>
        <h5>original excerpt</h5>${pre(rec.original_excerpt)}
        <h5>rewritten excerpt</h5>${pre(rec.rewritten_excerpt)}</div>`)
        .join('')}</div>`;
  }
  const ledger = entry.guard;
  return `<div class="two-col">
    <div><h5>proposed event BEFORE the guard</h5>${beforeHtml}</div>
    <div><h5>guard intervention</h5>${guardHtml}
      ${ledger ? `<details><summary>guard_ledger.jsonl record for this
        step</summary>${json(ledger)}</details>` : ''}</div></div>`;
}

function renderCommitted(entry, branch, view) {
  const event = entry.committedEvent;
  if (!event) {
    if (entry.committedEventUnavailable) {
      return unavailableBlock(entry.committedEventUnavailable);
    }
    return `<div class="unavailable"><span class="tag">NO COMMITTED EVENT</span>
      <p>this step record names no committed event and gives no reason</p></div>`;
  }
  const check = view.hashReport.checks.find((c) => c.kind === 'committed_event'
    && c.label === `${branch.candidateId} event ${event.event_id}`);
  const hashHtml = check
    ? `<span class="hash ${check.ok ? 'ok' : 'bad'}">sha256
        ${esc(event.sha256)} -- ${check.ok ? 'recomputed and matched'
        : 'RECOMPUTED VALUE DIFFERS'}</span>`
    : `<span class="hash">sha256 ${esc(event.sha256)}</span>`;
  return `<div class="committed" data-committed-index="${esc(event.index)}"
      data-event-id="${esc(event.event_id)}"
      data-event-sha256="${esc(event.sha256)}">
    <div class="committed-head"><b>${esc(event.event_id)}</b>
      <span class="muted">index ${esc(event.index)}</span> ${hashHtml}</div>
    <pre class="verbatim" data-event-text-for="${esc(event.event_id)}"
      >${esc(event.text)}</pre></div>`;
}

function renderRecipients(entry) {
  const recipients = entry.record.recipients;
  const created = entry.record.observations_created;
  const reason = unavailableReason(recipients);
  const recipientHtml = reason ? unavailableBlock(reason)
    : (recipients ? `<p>The game master named these entities as aware of the
        event: <b>${esc((recipients.names || []).join(', ') || 'none')}</b></p>
      ${pre(recipients.answer_text)}`
      : unavailableBlock('no recipient record for this step'));
  const createdReason = unavailableReason(created);
  const createdHtml = createdReason ? unavailableBlock(createdReason)
    : (created ? `<p class="muted">${esc(created.note || '')}</p>
        ${pre(created.queued_event_text)}`
      : unavailableBlock('no observation-creation record for this step'));
  return `<div class="two-col"><div><h5>who received the observation</h5>
    ${recipientHtml}</div><div><h5>observation queued</h5>${createdHtml}</div>
    </div>`;
}

function renderStateHash(entry, branch, view) {
  const state = entry.record.state_hash_after_step;
  if (!state) return unavailableBlock('no state hash record for this step');
  const reason = unavailableReason(state);
  if (reason) return unavailableBlock(reason);
  const check = view.hashReport.checks.find((c) => c.kind === 'state_prefix'
    && c.label === `${branch.candidateId} step ${entry.step} `
      + 'committed-stream prefix');
  const fullReason = unavailableReason(state.full_engine_state_hash);
  return `<div class="state">
    <div><b>committed-stream prefix sha256</b>
      <span class="mono">${esc(state.committed_stream_prefix_sha256)}</span>
      ${check ? `<span class="hash ${check.ok ? 'ok' : 'bad'}">${check.ok
        ? 'recomputed and matched' : 'RECOMPUTED VALUE DIFFERS'}</span>` : ''}
    </div>
    <div><b>committed rows so far</b>
      <span class="mono">${esc(state.committed_rows_so_far)}</span></div>
    <div><b>full engine state hash</b>
      ${fullReason ? unavailableBlock(fullReason)
        : `<span class="mono">${esc(state.full_engine_state_hash)}</span>`}
    </div></div>`;
}

function renderAuditorSlice(entry, activeActorName) {
  const delivered = entry.record.observations_delivered;
  if (!delivered || typeof delivered !== 'object') return '';
  const others = Object.entries(delivered)
    .filter(([name]) => name !== activeActorName);
  if (!others.length) return '';
  const body = others.map(([name, slice]) => `<div class="sub">
    <h5>${esc(name)}</h5>${pre(slice.delivered_text || '')}</div>`).join('');
  return auditorOnly(
    `Other actors' observation slices this step (${others.length})`, body,
    'These belong to other actors. The active actor\'s prompt above does not '
    + 'contain them.');
}

export function renderEntryDetail(entry, branch, view, index) {
  const attrs = `class="entry-detail" data-entry-index="${index}" `
    + `data-entry-kind="${esc(entry.kind)}"`;
  if (entry.kind === 'genesis' || entry.kind === 'unattached') {
    return `<article ${attrs}>
      <h3>${esc(entry.label)}</h3>
      ${entry.note ? `<p class="muted">${esc(entry.note)}</p>` : ''}
      ${entry.kind === 'unattached' ? `<div class="problems bad">
        <h3>This committed event is claimed by no step record.</h3>
        <p>It is shown here rather than dropped. Treat the timeline as
        incomplete until the artifacts explain it.</p></div>` : ''}
      <section class="pane"><h4>committed event</h4>
        ${renderCommitted(entry, branch, view)}</section>
    </article>`;
  }
  if (entry.kind === 'malformed') {
    return `<article ${attrs}>
      <h3>${esc(entry.label)}</h3>
      <div class="problems bad"><h3>This record could not be parsed.</h3>
        <p>It is kept in position so the timeline is not silently
        shortened.</p>
        <p><code>${esc(entry.record.error)}</code></p></div>
      ${pre(entry.record.raw)}</article>`;
  }

  const record = entry.record;
  const actor = record.active_actor || {};
  const actorName = actor.name || '';
  const simTime = record.simulation_time;
  const simReason = unavailableReason(simTime);
  const privateContext = record.actor_private_context || {};
  const privateReason = unavailableReason(privateContext);
  const termination = record.termination_check;

  return `<article ${attrs}>
    <h3>Step ${esc(record.step)} &middot; ${esc(actorName)}</h3>

    <section class="pane"><h4>1. simulation time</h4>
      ${simReason ? unavailableBlock(simReason)
        : `<p class="mono">${esc(simTime)}</p>`}</section>

    <section class="pane"><h4>2. active actor</h4>
      <p><b>${esc(actorName)}</b>
        <span class="mono muted">${esc(actor.actor_id || '')}</span></p>
      ${record.action_spec ? `<details><summary>action spec the engine
        requested</summary>${json(record.action_spec)}</details>` : ''}</section>

    <section class="pane"><h4>3. what this actor could see</h4>
      <div class="two-col">
        <div class="private-box">
          <div class="box-band">PRIVATE -- ${esc(actorName)} ONLY</div>
          ${privateReason ? unavailableBlock(privateReason) : `
            <h5>from the plan</h5>${pre(privateContext.from_plan)}
            <h5>as rendered into this actor's prompt</h5>
            ${pre(privateContext.as_rendered_in_prompt)}`}
        </div>
        <div class="shared-box">
          <div class="box-band">SHARED -- every actor in this world</div>
          ${pre(record.shared_context)}
        </div>
      </div></section>

    <section class="pane"><h4>4. observations this actor received</h4>
      ${renderObservationsForActor(entry, actorName)}
      ${record.memory_retrieved ? `<details><summary>memory the engine
        retrieved for this actor</summary>${json(record.memory_retrieved)}
        </details>` : ''}</section>

    <section class="pane"><h4>5. the exact model request for this actor</h4>
      <p class="muted">Verbatim, as sent. This pane contains only
        ${esc(actorName)}'s own prompt.</p>
      ${renderActorPrompt(entry)}
      ${Array.isArray(record.actor_prompt_as_engine_assembled)
        ? `<details><summary>prompt as the engine assembled it
          (line by line)</summary>${pre(record
            .actor_prompt_as_engine_assembled.join('\n'))}</details>` : ''}
    </section>

    <section class="pane"><h4>6. the raw model response</h4>
      ${renderActorResponse(entry)}</section>

    <section class="pane"><h4>7. the action this actor attempted</h4>
      ${unavailableReason(record.attempted_action)
        ? unavailableBlock(unavailableReason(record.attempted_action))
        : pre(record.attempted_action)}</section>

    <section class="pane"><h4>8. game master</h4>
      ${renderGameMaster(entry)}</section>

    <section class="pane"><h4>9-10. proposed event and the agency guard</h4>
      ${renderGuard(entry)}</section>

    <section class="pane"><h4>11. the final committed event</h4>
      ${renderCommitted(entry, branch, view)}</section>

    <section class="pane"><h4>12. who received the resulting observation</h4>
      ${renderRecipients(entry)}</section>

    <section class="pane"><h4>13. state after this step</h4>
      ${renderStateHash(entry, branch, view)}</section>

    <section class="pane"><h4>14. termination check</h4>
      ${termination ? `<p><b>${esc(termination.question)}</b>
        &rarr; <b>${esc(termination.answer)}</b></p>`
        : unavailableBlock('no termination check recorded for this step')}
    </section>

    ${renderAuditorSlice(entry, actorName)}

    ${auditorOnly('Complete step_ledger.jsonl record for this step',
      `<details><summary>show the raw auditor record</summary>
        ${json(record)}</details>`,
      'Every actor\'s private context and every prompt, side by side.')}
  </article>`;
}

/* ------------------------------------------------------------------ */
/* metrics, outcome, comparison                                        */
/* ------------------------------------------------------------------ */

export function renderMetrics(branch, view) {
  const entries = Object.values(branch.metrics);
  if (!entries.length) {
    return `<div class="unavailable"><span class="tag">NO METRICS</span>
      <p>this branch result records no outcome metrics</p></div>`;
  }
  const items = entries.map((metric) => {
    const citations = metric.computedFrom.join('|');
    const events = metric.citedEvents.map((cite) => (cite.missing
      ? `<li class="bad">cites ${esc(cite.eventId)}, which is NOT a committed
          event of this branch</li>`
      : `<li><button type="button" class="cite"
          data-goto-event="${esc(cite.eventId)}">${esc(cite.eventId)}</button>
          <pre class="verbatim small">${esc(cite.text)}</pre></li>`)).join('');
    const state = metric.stateCitations.map((c) => `<li class="mono">${esc(c)}
      <span class="muted"> -- computed from branch state, not from a single
      event</span></li>`).join('');
    return `<li class="metric" data-metric="${esc(metric.name)}"
        data-metric-value="${esc(JSON.stringify(metric.value))}"
        data-citations="${esc(citations)}">
      <div class="metric-head"><b>${esc(metric.name)}</b> =
        <span class="mono">${esc(JSON.stringify(metric.value))}</span></div>
      <ul class="cites">${events}${state}</ul>
      <div class="muted">${sourceLink(metric.source, 'branch_result.json')}
        ${metric.ledgerSource
          ? sourceLink(metric.ledgerSource, 'evaluator_ledger.json') : ''}</div>
    </li>`;
  }).join('');
  return `<ul class="metrics">${items}</ul>`;
}

export function renderOutcome(view) {
  const outcome = view.outcome;
  if (outcome.kind === 'refusal') {
    const refusal = outcome.refusal || {};
    const perBranch = refusal.per_branch_delivery || {};
    const rows = Object.entries(perBranch).map(([id, info]) => `<tr>
      <td>${esc(id)}</td><td>${esc(info.status)}</td>
      <td>${esc(info.reason)}</td>
      <td>${esc(info.insertion_actor)}</td>
      <td>${esc((info.reached_actors || []).join(', ') || 'none')}</td>
      <td>${esc(info.fragments_found)}/${esc(info.fragments_tested)}</td>
      </tr>`).join('');
    return `<section class="refusal">
      <div class="refusal-band">RANKING REFUSED -- this is a first-class result, not an error</div>
      <p class="lead">${esc(refusal.what_this_means || '')}</p>
      <h4>${esc(refusal.error_type || 'refusal')}</h4>
      ${pre(refusal.reason)}
      ${rows ? `<table class="grid"><thead><tr><th>candidate</th>
        <th>delivery</th><th>reason</th><th>insertion actor</th>
        <th>reached</th><th>fragments</th></tr></thead>
        <tbody>${rows}</tbody></table>` : ''}
      <p class="muted">${sourceLink(outcome.refusalSource)}</p>
    </section>`;
  }
  const ranking = outcome.ranking;
  if (!ranking) {
    return `<div class="problems bad"><h3>No ranking and no refusal was
      found.</h3><p>The run should have produced one or the other.</p></div>`;
  }
  const rows = (ranking.ranking || []).map((row, position) => `<tr
      ${row.candidate_id === ranking.best_candidate_id
        ? 'class="winner"' : ''}>
    <td>${position + 1}</td><td>${esc(row.candidate_id)}</td>
    <td>${esc(JSON.stringify(row.metric_values))}</td></tr>`).join('');
  const validation = ranking.validation_status || {};
  return `<section class="ranking">
    <h4>Best candidate: <b>${esc(ranking.best_candidate_id)}</b>
      ${validation.decided_by_metric
        ? `<span class="muted">decided by
          ${esc(validation.decided_by_metric)}</span>` : ''}</h4>
    <table class="grid"><thead><tr><th>#</th><th>candidate</th>
      <th>metric values</th></tr></thead><tbody>${rows}</tbody></table>
    ${ranking.downside_outcomes ? `<details><summary>downside outcomes</summary>
      ${json(ranking.downside_outcomes)}</details>` : ''}
    ${ranking.metric_differences ? `<details><summary>metric differences
      </summary>${json(ranking.metric_differences)}</details>` : ''}
    <details open><summary>validation status</summary>${json(validation)}
      </details>
    <p class="limit">${esc(ranking.run_limitations || '')}</p>
    <p class="muted">${sourceLink(outcome.rankingSource)}</p>
  </section>`;
}

export function renderComparison(view) {
  const metricNames = [];
  for (const branch of view.branches) {
    for (const name of Object.keys(branch.metrics)) {
      if (!metricNames.includes(name)) metricNames.push(name);
    }
  }
  const head = `<tr><th>field</th>${view.branches
    .map((b) => `<th>${esc(b.candidateId)}</th>`).join('')}</tr>`;
  const row = (label, fn) => `<tr><th>${esc(label)}</th>${view.branches
    .map((b) => `<td>${fn(b)}</td>`).join('')}</tr>`;
  const metricRows = metricNames.map((name) => `<tr>
    <th>metric: ${esc(name)}</th>${view.branches.map((b) => {
      const metric = b.metrics[name];
      if (!metric) return '<td class="muted">not measured</td>';
      return `<td data-compare-metric="${esc(name)}"
        data-candidate="${esc(b.candidateId)}">
        <span class="mono">${esc(JSON.stringify(metric.value))}</span>
        <div class="small muted">${esc(metric.computedFrom.join(', '))}</div>
      </td>`;
    }).join('')}</tr>`).join('');
  return `<table class="grid compare"><thead>${head}</thead><tbody>
    ${row('branch id', (b) => `<span class="mono small">${esc(b.branchId)}</span>`)}
    ${row('branch seed', (b) => `<span class="mono small">${esc(b.branchSeed)}</span>`)}
    ${row('terminal status', (b) => esc(b.terminalStatus))}
    ${row('steps completed', (b) => esc(b.stepsCompleted))}
    ${row('committed events', (b) => esc(b.timeline.committedStream.length))}
    ${row('model calls', (b) => esc(b.timeline.callIds.length))}
    ${row('guard interventions', (b) => esc(b.timeline.entries
      .filter((e) => e.kind === 'step' && e.record.guard
        && e.record.guard.intervened === true).length))}
    ${row('infrastructure errors', (b) => (b.infrastructureErrors.length
      ? `<span class="bad">${esc(b.infrastructureErrors.length)}</span>`
      : '0'))}
    ${row('candidate source', (b) => esc(b.candidate && b.candidate.provenance
      ? b.candidate.provenance.source : 'not recorded'))}
    ${metricRows}
  </tbody></table>`;
}

export function renderRawLinks(view, branch) {
  const runRows = Object.entries(view.files).map(([key, file]) => {
    if (!file || !file.path) return '';
    const status = file.present
      ? (file.ok ? 'loaded' : 'PRESENT BUT UNPARSEABLE')
      : `absent -- ${file.absentReason || file.error || 'not found'}`;
    return `<tr><td>${esc(key)}</td>
      <td>${file.present ? `<a href="${esc(fileHref(file.path))}"
        target="_blank" rel="noopener">${esc(file.path)}</a>`
        : `<code>${esc(file.path)}</code>`}</td>
      <td class="${file.present && file.ok ? '' : 'bad'}">${esc(status)}
        ${file.auditorOnly ? '<span class="badge audit">auditor-only</span>'
          : ''}</td></tr>`;
  }).join('');
  const branchRows = branch ? Object.entries(branch.files)
    .filter(([key]) => !key.startsWith('__'))
    .map(([key, file]) => `<tr><td>${esc(key)}</td>
      <td>${file.present ? `<a href="${esc(fileHref(file.path))}"
        target="_blank" rel="noopener">${esc(file.path)}</a>`
        : `<code>${esc(file.path)}</code>`}</td>
      <td class="${file.present && file.ok ? '' : 'bad'}">${file.present
        ? (file.ok ? 'loaded' : 'PRESENT BUT UNPARSEABLE')
        : `absent -- ${esc(file.absentReason || file.error || 'not found')}`}
        ${file.auditorOnly ? '<span class="badge audit">auditor-only</span>'
          : ''}</td></tr>`).join('')
    + (branch.files.__linkOnly || []).map((link) => `<tr><td>rawEngineLog</td>
      <td><a href="${esc(fileHref(link.path))}" target="_blank"
        rel="noopener">${esc(link.path)}</a></td>
      <td>${esc(link.note)}</td></tr>`).join('')
    : '';
  return `<table class="grid"><thead><tr><th>artifact</th><th>file</th>
    <th>status</th></tr></thead><tbody>${runRows}${branchRows}</tbody></table>`;
}

export function renderHashReport(view) {
  if (view.hashReport.skipped) {
    return '<p class="muted">hash verification was not run</p>';
  }
  const byKind = new Map();
  for (const check of view.hashReport.checks) {
    if (!byKind.has(check.kind)) byKind.set(check.kind, { ok: 0, bad: [] });
    const bucket = byKind.get(check.kind);
    if (check.ok) bucket.ok += 1; else bucket.bad.push(check);
  }
  const rows = [...byKind.entries()].map(([kind, bucket]) => `<tr>
    <td>${esc(kind)}</td><td>${esc(bucket.ok)}</td>
    <td class="${bucket.bad.length ? 'bad' : ''}">${esc(bucket.bad.length)}</td>
    <td>${bucket.bad.map((c) => `<div class="bad">${esc(c.label)}:
      published ${esc(c.expected)}, recomputed ${esc(c.actual)}</div>`)
      .join('')}</td></tr>`).join('');
  return `<table class="grid"><thead><tr><th>hash family</th><th>matched</th>
    <th>mismatched</th><th>detail</th></tr></thead><tbody>${rows}</tbody>
    </table>`;
}

/* ------------------------------------------------------------------ */
/* the whole branch replay                                             */
/* ------------------------------------------------------------------ */

/**
 * Render one branch's complete replay: the header, the ordered timeline,
 * every step detail, the metrics with their citations, the ranking or the
 * refusal, the side-by-side comparison and the raw artifact links.
 *
 * The browser injects this string; the equivalence test parses it.
 */
export function renderBranchReplay(view, branchIndex) {
  const branch = view.branches[branchIndex];
  if (!branch) {
    return `<div class="problems bad"><h3>No branch ${esc(branchIndex)} in
      this run.</h3></div>`;
  }
  const details = branch.timeline.entries
    .map((entry, index) => renderEntryDetail(entry, branch, view, index))
    .join('');
  return `<div class="replay" data-run-id="${esc(view.run.id)}"
      data-candidate-id="${esc(branch.candidateId)}"
      data-branch-id="${esc(branch.branchId)}"
      data-branch-seed="${esc(branch.branchSeed)}"
      data-entry-count="${esc(branch.timeline.entries.length)}">
    ${renderBanner(view)}
    ${renderProblems(view)}
    ${renderHeader(view)}
    <div class="replay-body">
      <div class="replay-timeline">
        <h3>Timeline (${esc(branch.timeline.entries.length)} entries)</h3>
        ${renderTimelineList(branch)}
      </div>
      <div class="replay-detail">${details}</div>
    </div>
    <details class="panel" open><summary>Outcome metrics and their exact
      event citations -- ${esc(branch.candidateId)}</summary>
      ${renderMetrics(branch, view)}</details>
    <details class="panel" open><summary>Final ranking or refusal</summary>
      ${renderOutcome(view)}</details>
    <details class="panel"><summary>Side-by-side candidate comparison</summary>
      ${renderComparison(view)}</details>
    <details class="panel"><summary>Published-hash verification</summary>
      ${renderHashReport(view)}</details>
    <details class="panel"><summary>Raw artifact records</summary>
      ${renderRawLinks(view, branch)}</details>
  </div>`;
}
