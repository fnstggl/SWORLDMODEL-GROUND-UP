"""The replay viewer renders exactly what the frozen artifacts say.

What this proves
----------------
The viewer under ``viewer/`` is a presentation layer over
``artifacts/full_trace_validation_20260804``.  These tests drive the
viewer's OWN JavaScript -- ``viewer/lib/assemble.js`` (ordering and
selection) and ``viewer/lib/render.js`` (the HTML the browser injects) --
through ``viewer/node_driver.js`` under Node, and compare the result with
the raw artifact files read independently here in Python.

For at least one branch of every scenario (pre-fix and post-fix) plus a
settling arm, the tests assert that the ordered committed events, the
ordered model call ids, and the metric citations extracted FROM THE
RENDERED HTML are exactly the ones in ``committed_events.jsonl``,
``llm_calls.jsonl``, ``branch_result.json`` and ``evaluator_ledger.json``.

They also assert that the viewer fails loud: a missing file, a malformed
JSON document, a malformed JSONL line, and a hash mismatch each produce a
visible problem naming the file, and no placeholder event is invented in
their place.  Those cases run against COPIES in a temporary directory --
the real artifacts are never modified.

Honest limitations
------------------
* ``node`` is available in this environment (``/opt/node22/bin/node``,
  v22), so the tests exercise the viewer's real transform and its real
  rendering rather than a Python restatement of them.  If Node were
  missing these tests would skip rather than silently weaken.
* Most assertions read the HTML string that ``viewer/app.js`` assigns to
  ``innerHTML``, not a live DOM.  That string IS what the browser
  displays, but it is one step short of the rendered page, so
  ``test_viewer_renders_and_plays_in_a_real_browser`` closes the gap by
  driving a real headless Chromium (via the Playwright install at
  ``/opt/pw-browsers``) against a running ``viewer/serve.py`` and reading
  the ordered committed events back out of the live DOM.  That test skips
  if the browser is not installed; everything else still runs.
* Nothing here tests visual design: CSS is not asserted on.

Run with the pinned engine environment::

    /home/user/engine-env/bin/python -m pytest tests/test_replay_viewer.py -q
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VIEWER = REPO_ROOT / 'viewer'
DRIVER = VIEWER / 'node_driver.js'
ARTIFACTS = REPO_ROOT / 'artifacts' / 'full_trace_validation_20260804'

NODE = shutil.which('node') or shutil.which('nodejs') or '/opt/node22/bin/node'

pytestmark = pytest.mark.skipif(
    not Path(NODE).exists(),
    reason='node is required to drive the viewer\'s own JavaScript')


# --------------------------------------------------------------------- #
# driving the viewer                                                     #
# --------------------------------------------------------------------- #

def drive(run_id, *, branch=None, root=REPO_ROOT, html=False, http=None,
          verify=True):
    """Run the viewer's assembly + rendering and return its JSON payload."""
    command = [NODE, str(DRIVER), '--root', str(root), '--run', run_id]
    if branch:
        command += ['--branch', branch]
    if html:
        command.append('--html')
    if http:
        command += ['--http', http]
    if not verify:
        command.append('--no-verify')
    completed = subprocess.run(command, capture_output=True, text=True,
                               cwd=str(REPO_ROOT), timeout=300)
    assert completed.returncode == 0, (
        f'viewer driver failed for {run_id}:\n{completed.stderr}')
    return json.loads(completed.stdout)


@functools.lru_cache(maxsize=None)
def drive_cached(run_id, branch, html):
    return json.dumps(drive(run_id, branch=branch, html=html))


def cached(run_id, branch=None, html=False):
    return json.loads(drive_cached(run_id, branch, html))


def read_jsonl(path):
    return [json.loads(line) for line in
            Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


# --------------------------------------------------------------------- #
# extracting what the viewer actually rendered                           #
# --------------------------------------------------------------------- #

def unescape(text):
    """Inverse of the escaper in ``viewer/lib/render.js``."""
    return (text.replace('&#39;', "'").replace('&quot;', '"')
            .replace('&gt;', '>').replace('&lt;', '<').replace('&amp;', '&'))


COMMITTED_RE = re.compile(
    r'<div class="committed" data-committed-index="(?P<index>[^"]*)"\s+'
    r'data-event-id="(?P<event_id>[^"]*)"\s+'
    r'data-event-sha256="(?P<sha256>[^"]*)">',
    re.S)

EVENT_TEXT_RE = re.compile(
    r'<pre class="verbatim" data-event-text-for="(?P<event_id>[^"]*)"\s*'
    r'>(?P<text>.*?)</pre>', re.S)

CALL_ID_RE = re.compile(r'data-call-id="([^"]*)"')

METRIC_RE = re.compile(
    r'<li class="metric" data-metric="(?P<name>[^"]*)"\s+'
    r'data-metric-value="(?P<value>[^"]*)"\s+'
    r'data-citations="(?P<citations>[^"]*)"', re.S)

AUDITOR_SECTION_RE = re.compile(
    r'<section class="auditor-only">.*?</section>', re.S)

ARTICLE_RE = re.compile(
    r'<article class="entry-detail" data-entry-index="(?P<index>\d+)"'
    r'.*?</article>', re.S)


def selected_branch(payload):
    """The branch the driver was pointed at (not simply the first one)."""
    return payload['branches'][payload['selectedBranchIndex']]


def rendered_committed_events(html):
    """Ordered committed events as the rendered timeline shows them."""
    heads = list(COMMITTED_RE.finditer(html))
    texts = {m.group('event_id'): unescape(m.group('text'))
             for m in EVENT_TEXT_RE.finditer(html)}
    out = []
    for match in heads:
        event_id = match.group('event_id')
        out.append({
            'index': int(match.group('index')),
            'event_id': event_id,
            'sha256': match.group('sha256'),
            'text': texts[event_id],
        })
    return out


def rendered_call_ids(html):
    """Ordered model call ids, first appearance wins (the chip and its
    container both carry the attribute)."""
    seen, out = set(), []
    for call_id in CALL_ID_RE.findall(html):
        if call_id not in seen:
            seen.add(call_id)
            out.append(call_id)
    return out


def rendered_metric_citations(html):
    return {m.group('name'): (m.group('citations').split('|')
                              if m.group('citations') else [])
            for m in METRIC_RE.finditer(html)}


def rendered_metric_values(html):
    return {m.group('name'): json.loads(unescape(m.group('value')))
            for m in METRIC_RE.finditer(html)}


# --------------------------------------------------------------------- #
# the equivalence assertion, used positively and as a mutation detector   #
# --------------------------------------------------------------------- #

def _branch_dir(source_root, run_dir, candidate_id):
    return Path(source_root) / run_dir / 'branches' / candidate_id


def assert_committed_events_match(payload, *, source_root, run_dir,
                                  candidate_id):
    branch_dir = _branch_dir(source_root, run_dir, candidate_id)
    expected = [
        {'index': row['index'], 'event_id': row['event_id'],
         'sha256': row['sha256'], 'text': row['text']}
        for row in read_jsonl(branch_dir / 'committed_events.jsonl')]
    assert rendered_committed_events(payload['renderedHtml']) == expected, (
        'the rendered committed-event stream differs from '
        f'{branch_dir / "committed_events.jsonl"}')


def assert_call_ids_match(payload, *, source_root, run_dir, candidate_id):
    branch_dir = _branch_dir(source_root, run_dir, candidate_id)
    expected = [row['call_id']
                for row in read_jsonl(branch_dir / 'llm_calls.jsonl')]
    assert rendered_call_ids(payload['renderedHtml']) == expected, (
        'the rendered model-call sequence differs from '
        f'{branch_dir / "llm_calls.jsonl"}')


def assert_metric_citations_match(payload, *, source_root, run_dir,
                                  candidate_id):
    branch_dir = _branch_dir(source_root, run_dir, candidate_id)
    result = read_json(branch_dir / 'branch_result.json')
    expected = {name: list(metric.get('computed_from', []))
                for name, metric in result['outcome_metrics'].items()}
    assert rendered_metric_citations(payload['renderedHtml']) == expected, (
        'the rendered metric citations differ from '
        f'{branch_dir / "branch_result.json"}')
    expected_values = {name: metric['value']
                       for name, metric in result['outcome_metrics'].items()}
    assert rendered_metric_values(payload['renderedHtml']) == expected_values


def assert_timeline_matches_source(payload, *, source_root, run_dir,
                                   candidate_id):
    """The rendered timeline == the frozen artifacts, exactly and in order.

    `source_root` is the tree the assertion compares AGAINST, which is what
    lets the mutation tests point the viewer at a corrupted copy while
    still comparing with the pristine artifacts.
    """
    where = dict(source_root=source_root, run_dir=run_dir,
                 candidate_id=candidate_id)
    assert_committed_events_match(payload, **where)
    assert_call_ids_match(payload, **where)
    assert_metric_citations_match(payload, **where)


# one branch per scenario, pre-fix and post-fix, plus one settling arm
EQUIVALENCE_CASES = [
    ('peter_supplied__pre_fix', 'peter_supplied', 'user_002'),
    ('peter_supplied__post_fix', 'peter_supplied/post_fix_rerun', 'user_001'),
    ('peter_generated__pre_fix', 'peter_generated', 'gen_001'),
    ('peter_generated__post_fix', 'peter_generated/post_fix_rerun', 'gen_002'),
    ('a16z_richard_historical__pre_fix', 'a16z_richard_historical', 'user_004'),
    ('a16z_richard_historical__post_fix',
     'a16z_richard_historical/post_fix_rerun', 'user_006'),
    ('settling_arm_a__rep_1', 'settling_experiment/arm_a/rep_1', 'user_001'),
    ('settling_arm_b__rep_2', 'settling_experiment/arm_b/rep_2', 'user_001'),
]

ARTIFACT_REL = 'artifacts/full_trace_validation_20260804'


@pytest.mark.parametrize('run_id,run_dir,candidate_id', EQUIVALENCE_CASES,
                         ids=[case[0] + '-' + case[2]
                              for case in EQUIVALENCE_CASES])
def test_rendered_timeline_equals_frozen_artifacts(run_id, run_dir,
                                                   candidate_id):
    payload = cached(run_id, candidate_id, True)
    assert_timeline_matches_source(
        payload, source_root=REPO_ROOT,
        run_dir=f'{ARTIFACT_REL}/{run_dir}', candidate_id=candidate_id)


# --------------------------------------------------------------------- #
# every run loads                                                        #
# --------------------------------------------------------------------- #

def all_run_ids():
    listing = subprocess.run([NODE, str(DRIVER), '--list'],
                             capture_output=True, text=True,
                             cwd=str(REPO_ROOT), timeout=120)
    assert listing.returncode == 0, listing.stderr
    return [entry['id'] for entry in json.loads(listing.stdout)]


def test_catalog_covers_every_run_directory():
    ids = all_run_ids()
    assert len(ids) == 14, ids
    for group in ('peter_supplied', 'peter_generated',
                  'a16z_richard_historical'):
        assert f'{group}__pre_fix' in ids
        assert f'{group}__post_fix' in ids
    for arm in ('a', 'b'):
        for rep in (1, 2, 3):
            assert f'settling_arm_{arm}__rep_{rep}' in ids
        assert f'settling_arm_{arm}__shakedown' in ids


@pytest.mark.parametrize('run_id', all_run_ids())
def test_every_run_loads_without_artifact_problems(run_id):
    payload = cached(run_id)
    errors = [p for p in payload['problems'] if p['severity'] == 'error']
    assert errors == [], errors
    assert payload['branches'], 'a run with no branch is not replayable'
    assert payload['hashChecks']['mismatched'] == []
    assert payload['hashChecks']['total'] > 0
    # every branch has an ordered timeline that covers its committed stream
    for branch in payload['branches']:
        assert branch['committedEvents'], branch['candidateId']
        assert branch['callIds'] == branch['ledgerCallOrder']


@pytest.mark.parametrize('run_id', all_run_ids())
def test_every_run_publishes_the_required_header_fields(run_id):
    payload = cached(run_id)
    header = payload['header']
    assert payload['banner'] == 'UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION'
    assert header['model']['name']
    assert header['model']['provider']
    assert header['environment']['repositorySha']
    assert header['plan']['basePlanContentHash']
    assert header['candidateSource']['declared'] in {'supplied', 'generated'}
    assert payload['limitations'], 'no known limitation was surfaced'
    for seed in header['branchSeeds']:
        assert seed['branchSeed'] is not None
        # exact, not rounded through a JavaScript double
        assert re.fullmatch(r'-?\d+', seed['branchSeed'])


@pytest.mark.parametrize('run_id', all_run_ids())
def test_every_linked_document_exists(run_id):
    """A dead link would be a quiet failure; the artifacts it points at
    must be there."""
    payload = cached(run_id)
    assert payload['documents']
    for document in payload['documents']:
        assert (REPO_ROOT / document['path']).is_file(), document


def test_branch_seeds_are_exact_not_rounded():
    payload = cached('peter_supplied__pre_fix')
    trace = read_json(ARTIFACTS / 'peter_supplied' / 'trace_report.json')
    expected = [str(b['branch_seed']) for b in trace['branches']]
    assert [s['branchSeed'] for s in payload['header']['branchSeeds']] == expected


def test_candidate_source_is_labelled_supplied_or_generated():
    supplied = cached('peter_supplied__pre_fix')
    generated = cached('peter_generated__pre_fix')
    assert supplied['header']['candidateSource']['verified'] == 'user_supplied'
    assert generated['header']['candidateSource']['verified'] == 'generated'
    for branch in supplied['branches']:
        assert branch['candidateProvenance'] == 'user_supplied'
    for branch in generated['branches']:
        assert branch['candidateProvenance'] == 'generated'


# --------------------------------------------------------------------- #
# refusals are first class; rankings carry their citations               #
# --------------------------------------------------------------------- #

@pytest.mark.parametrize('run_id,source', [
    ('peter_supplied__post_fix',
     'peter_supplied/post_fix_rerun/recommendation_result.json'),
    ('peter_generated__post_fix',
     'peter_generated/post_fix_rerun/recommendation_result.json'),
    ('a16z_richard_historical__post_fix',
     'a16z_richard_historical/post_fix_rerun/recommendation_result.json'),
    ('settling_arm_a__rep_1',
     'settling_experiment/arm_a/rep_1/recommendation_report.json'),
])
def test_refusal_is_rendered_as_a_first_class_result(run_id, source):
    payload = cached(run_id, None, True)
    assert payload['outcome']['kind'] == 'refusal'
    html = payload['renderedHtml']
    assert 'RANKING REFUSED -- this is a first-class' in html
    frozen = read_json(ARTIFACTS / source)
    assert frozen['refused'] is True
    assert payload['outcome']['refusalType'] == frozen['error_type']
    from html import escape as html_escape
    assert html_escape(frozen['what_this_means'], quote=True) in html \
        or frozen['what_this_means'] in unescape(html)
    assert 'No ranking and no refusal was' not in html


@pytest.mark.parametrize('run_id,source', [
    ('peter_supplied__pre_fix', 'peter_supplied/recommendation_result.json'),
    ('peter_generated__pre_fix', 'peter_generated/recommendation_result.json'),
    ('a16z_richard_historical__pre_fix',
     'a16z_richard_historical/recommendation_result.json'),
])
def test_ranking_reports_the_frozen_winner(run_id, source):
    payload = cached(run_id, None, True)
    assert payload['outcome']['kind'] == 'ranking'
    frozen = read_json(ARTIFACTS / source)
    assert payload['outcome']['bestCandidateId'] == frozen['best_candidate_id']
    html = payload['renderedHtml']
    assert f"<b>{frozen['best_candidate_id']}</b>" in html
    # the declared run limitation travels with the ranking
    assert frozen['run_limitations'][:60] in unescape(html)


def test_metric_citations_agree_with_the_evaluator_ledger():
    run_dir = ARTIFACTS / 'a16z_richard_historical'
    ledger = read_json(run_dir / 'evaluator_ledger.json')
    for entry in ledger['branches']:
        payload = cached('a16z_richard_historical__pre_fix',
                         entry['candidate_id'], True)
        rendered = rendered_metric_citations(payload['renderedHtml'])
        expected = {name: list(metric['computed_from'])
                    for name, metric in entry['metrics'].items()}
        assert rendered == expected, entry['candidate_id']


# --------------------------------------------------------------------- #
# auditor-only labelling                                                 #
# --------------------------------------------------------------------- #

def test_actor_prompt_pane_shows_only_that_actors_prompt():
    """The step ledger holds every actor's prompt; the prompt pane must not."""
    payload = cached('a16z_richard_historical__pre_fix', 'user_004', True)
    html = payload['renderedHtml']
    branch_dir = (ARTIFACTS / 'a16z_richard_historical' / 'branches'
                  / 'user_004')
    calls = {row['call_id']: row
             for row in read_jsonl(branch_dir / 'llm_calls.jsonl')}
    steps = [row for row in read_jsonl(branch_dir / 'step_ledger.jsonl')
             if '_artifact_class' not in row]

    # For each step, the call ids rendered in the "exact model request"
    # pane belong to the ACTIVE actor and to nobody else.
    pane_re = re.compile(
        r'<h4>5\. the exact model request for this actor</h4>(.*?)</section>',
        re.S)
    panes = pane_re.findall(html)
    assert len(panes) == len(steps)
    for step, pane in zip(sorted(steps, key=lambda r: r['step']), panes):
        active = step['active_actor']['name']
        for call_id in set(CALL_ID_RE.findall(pane)):
            call = calls[call_id]
            assert call['role'] == 'actor', call_id
            assert call['actor_name'] == active, (
                f'step {step["step"]} prompt pane shows a call belonging to '
                f'{call["actor_name"]}, not to the active actor {active}')


def test_other_actors_context_appears_only_inside_an_auditor_only_block():
    """Content that belongs to another actor at this step, and to nothing
    else in this step's record, must be rendered only inside an
    auditor-only band."""
    payload = cached('a16z_richard_historical__pre_fix', 'user_004', True)
    html = payload['renderedHtml']
    sections = AUDITOR_SECTION_RE.findall(html)
    assert sections, 'no auditor-only block was rendered'
    for section in sections:
        assert 'AUDITOR-ONLY -- NO ACTOR EVER SAW THIS' in section

    steps = {row['step']: row for row in read_jsonl(
        ARTIFACTS / 'a16z_richard_historical' / 'branches' / 'user_004'
        / 'step_ledger.jsonl') if '_artifact_class' not in row}
    articles = {int(m.group('index')): m.group(0)
                for m in ARTICLE_RE.finditer(html)}
    assert articles

    checked = 0
    for article in articles.values():
        match = re.search(r'<h3>Step (\d+)', article)
        if not match:
            continue
        step = steps[int(match.group(1))]
        active = step['active_actor']['name']
        # everything this step's record holds EXCEPT other actors' slices
        scrubbed = dict(step)
        scrubbed['observations_delivered'] = {
            active: step['observations_delivered'].get(active, {})}
        own_blob = json.dumps(scrubbed, ensure_ascii=False)
        outside = unescape(AUDITOR_SECTION_RE.sub('', article))
        for name, slice_ in step['observations_delivered'].items():
            if name == active:
                continue
            for line in (slice_.get('delivered_text') or '').split('\n'):
                line = line.strip()
                if len(line) < 40 or line in own_blob:
                    continue
                assert line not in outside, (
                    f'step {step["step"]}: content unique to {name} is '
                    'rendered outside an auditor-only block')
                checked += 1
    assert checked > 0, 'no cross-actor-only content was available to check'


def test_the_raw_step_ledger_record_is_labelled_auditor_only():
    payload = cached('peter_supplied__pre_fix', 'user_001', True)
    html = payload['renderedHtml']
    for section in AUDITOR_SECTION_RE.findall(html):
        if 'Complete step_ledger.jsonl record' in section:
            assert 'AUDITOR-ONLY' in section
            break
    else:
        pytest.fail('the raw step ledger record is not inside an '
                    'auditor-only block')


# --------------------------------------------------------------------- #
# fields the artifacts genuinely lack                                    #
# --------------------------------------------------------------------- #

def test_unavailable_fields_render_their_recorded_reason():
    payload = cached('peter_supplied__pre_fix', 'user_001', True)
    html = unescape(payload['renderedHtml'])
    step = [row for row in read_jsonl(
        ARTIFACTS / 'peter_supplied' / 'branches' / 'user_001'
        / 'step_ledger.jsonl') if '_artifact_class' not in row][0]
    sim_reason = step['simulation_time']['unavailable']
    state_reason = (step['state_hash_after_step']['full_engine_state_hash']
                    ['unavailable'])
    assert sim_reason in html, 'the simulation-time reason was hidden'
    assert state_reason in html, 'the engine-state-hash reason was hidden'
    assert 'RECORDED AS UNAVAILABLE' in payload['renderedHtml']


def test_documented_absences_name_the_reason_rather_than_failing():
    payload = cached('peter_supplied__pre_fix')
    absent = {key: value for key, value in payload['files'].items()
              if not value['present']}
    assert absent, 'expected some optional artifacts to be absent here'
    for key, value in absent.items():
        assert value['absentReason'], f'{key} is absent with no reason given'


# --------------------------------------------------------------------- #
# mutation tests: the equivalence assertion genuinely discriminates       #
# --------------------------------------------------------------------- #

def stage(tmp_path, *subdirs):
    """Copy artifact subtrees into a temporary root.  The real artifacts
    are read-only here and are never touched."""
    root = tmp_path / 'checkout'
    for sub in subdirs:
        source = ARTIFACTS / sub
        target = root / ARTIFACT_REL / sub
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
    for name in ('README.md', 'SESSION_CALL_ACCOUNTING.json'):
        if (ARTIFACTS / name).exists():
            shutil.copy2(ARTIFACTS / name, root / ARTIFACT_REL / name)
    return root


def test_mutation_reordering_two_events_fails_the_equivalence_check(tmp_path):
    """Swap which event happened at which position, keeping the file
    internally consistent, and the rendered timeline must diverge."""
    root = stage(tmp_path, 'peter_supplied', 'shared')
    events = (root / ARTIFACT_REL / 'peter_supplied' / 'branches' / 'user_002'
              / 'committed_events.jsonl')
    rows = [json.loads(line) for line in
            events.read_text(encoding='utf-8').splitlines() if line.strip()]
    rows[2], rows[3] = rows[3], rows[2]
    for position, row in enumerate(rows):        # keep index == position
        row['index'] = position
    events.write_text('\n'.join(json.dumps(row) for row in rows) + '\n',
                      encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', branch='user_002', root=root,
                    html=True)
    with pytest.raises(AssertionError, match='committed-event stream'):
        assert_timeline_matches_source(
            payload, source_root=REPO_ROOT,
            run_dir=f'{ARTIFACT_REL}/peter_supplied', candidate_id='user_002')
    # the viewer also notices on its own: the step ledger still remembers
    # which text it committed at that index
    assert any('text disagrees with' in p['problem']
               for p in payload['problems']), payload['problems']


def test_mutation_shuffling_rows_out_of_index_order_is_reported(tmp_path):
    """Rows moved without renumbering: the stream is index-anchored, so the
    timeline stays correct, but the viewer still says the file is wrong."""
    root = stage(tmp_path, 'peter_supplied', 'shared')
    events = (root / ARTIFACT_REL / 'peter_supplied' / 'branches' / 'user_002'
              / 'committed_events.jsonl')
    lines = events.read_text(encoding='utf-8').splitlines()
    lines[2], lines[3] = lines[3], lines[2]
    events.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', branch='user_002', root=root,
                    html=True)
    assert any('declares index' in p['problem'] and p['severity'] == 'error'
               for p in payload['problems']), payload['problems']


def test_mutation_dropping_a_step_record_fails_the_equivalence_check(tmp_path):
    """Losing one step must lose its committed event and its model calls
    from the rendered timeline -- loudly, not silently."""
    root = stage(tmp_path, 'peter_supplied', 'shared')
    ledger = (root / ARTIFACT_REL / 'peter_supplied' / 'branches' / 'user_002'
              / 'step_ledger.jsonl')
    lines = ledger.read_text(encoding='utf-8').splitlines()
    del lines[2]                                  # drop step 2's record
    ledger.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', branch='user_002', root=root,
                    html=True)
    where = dict(source_root=REPO_ROOT,
                 run_dir=f'{ARTIFACT_REL}/peter_supplied',
                 candidate_id='user_002')
    with pytest.raises(AssertionError, match='committed-event stream'):
        assert_committed_events_match(payload, **where)
    with pytest.raises(AssertionError, match='model-call sequence'):
        assert_call_ids_match(payload, **where)
    assert any('claimed by no step record' in p['problem']
               for p in payload['problems']), payload['problems']
    assert any('no step record surfaces it' in p['problem']
               for p in payload['problems']), payload['problems']


def test_mutation_dropping_one_event_fails_the_equivalence_check(tmp_path):
    root = stage(tmp_path, 'peter_supplied', 'shared')
    events = (root / ARTIFACT_REL / 'peter_supplied' / 'branches' / 'user_002'
              / 'committed_events.jsonl')
    lines = events.read_text(encoding='utf-8').splitlines()
    del lines[4]
    events.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', branch='user_002', root=root,
                    html=True)
    with pytest.raises(AssertionError, match='committed-event stream'):
        assert_timeline_matches_source(
            payload, source_root=REPO_ROOT,
            run_dir=f'{ARTIFACT_REL}/peter_supplied', candidate_id='user_002')
    assert any('is not present in the committed stream' in p['problem']
               for p in payload['problems']), payload['problems']
    # nothing was invented to fill the gap
    rendered = rendered_committed_events(payload['renderedHtml'])
    assert len(rendered) == 5


def test_mutation_dropping_a_call_from_the_ledger_is_reported(tmp_path):
    """A step that references a call the ledger no longer holds is a loud
    error: the timeline must never show a call with no recorded evidence."""
    root = stage(tmp_path, 'peter_supplied', 'shared')
    calls = (root / ARTIFACT_REL / 'peter_supplied' / 'branches' / 'user_002'
             / 'llm_calls.jsonl')
    lines = calls.read_text(encoding='utf-8').splitlines()
    dropped = json.loads(lines[3])['call_id']
    del lines[3]
    calls.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', branch='user_002', root=root,
                    html=True)
    named = [p for p in payload['problems']
             if 'is not in the branch call ledger' in p['problem']]
    assert named, payload['problems']
    assert dropped in named[0]['problem']


def test_mutation_renaming_a_call_id_fails_the_equivalence_check(tmp_path):
    root = stage(tmp_path, 'peter_supplied', 'shared')
    ledger = (root / ARTIFACT_REL / 'peter_supplied' / 'branches' / 'user_002'
              / 'step_ledger.jsonl')
    text = ledger.read_text(encoding='utf-8')
    ledger.write_text(text.replace('peter_supplied-000011',
                                   'peter_supplied-999999'), encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', branch='user_002', root=root,
                    html=True)
    with pytest.raises(AssertionError, match='model-call sequence'):
        assert_call_ids_match(
            payload, source_root=REPO_ROOT,
            run_dir=f'{ARTIFACT_REL}/peter_supplied', candidate_id='user_002')


def test_mutation_changing_a_metric_citation_is_detected(tmp_path):
    root = stage(tmp_path, 'peter_supplied', 'shared')
    result = (root / ARTIFACT_REL / 'peter_supplied' / 'branches' / 'user_002'
              / 'branch_result.json')
    payload_json = json.loads(result.read_text(encoding='utf-8'))
    payload_json['outcome_metrics']['call_agreed']['computed_from'] = \
        ['event:ev_0001']
    result.write_text(json.dumps(payload_json, indent=2), encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', branch='user_002', root=root,
                    html=True)
    with pytest.raises(AssertionError, match='metric citations'):
        assert_timeline_matches_source(
            payload, source_root=REPO_ROOT,
            run_dir=f'{ARTIFACT_REL}/peter_supplied', candidate_id='user_002')
    assert any('citations disagree' in p['problem']
               for p in payload['problems']), payload['problems']


# --------------------------------------------------------------------- #
# fail-loud paths                                                        #
# --------------------------------------------------------------------- #

def test_missing_artifact_is_reported_by_name(tmp_path):
    root = stage(tmp_path, 'peter_supplied', 'shared')
    victim = (root / ARTIFACT_REL / 'peter_supplied' / 'branches' / 'user_001'
              / 'committed_events.jsonl')
    victim.unlink()

    payload = drive('peter_supplied__pre_fix', branch='user_001', root=root,
                    html=True)
    named = [p for p in payload['problems']
             if p['file'].endswith('user_001/committed_events.jsonl')
             and p['severity'] == 'error']
    assert named, payload['problems']
    assert 'could not be read' in named[0]['problem']
    # no placeholder events were invented in its place
    assert rendered_committed_events(payload['renderedHtml']) == []
    assert selected_branch(payload)['committedEvents'] == []


def test_missing_required_run_level_artifact_is_reported(tmp_path):
    root = stage(tmp_path, 'peter_supplied', 'shared')
    (root / ARTIFACT_REL / 'peter_supplied' / 'evaluator_ledger.json').unlink()
    payload = drive('peter_supplied__pre_fix', root=root)
    named = [p for p in payload['problems']
             if p['file'].endswith('evaluator_ledger.json')]
    assert named, payload['problems']
    assert named[0]['severity'] == 'error'


def test_malformed_json_document_is_reported_by_name(tmp_path):
    root = stage(tmp_path, 'peter_supplied', 'shared')
    victim = root / ARTIFACT_REL / 'peter_supplied' / 'decision_problem.json'
    victim.write_text('{"contract_type": "decision_problem", ', encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', root=root)
    named = [p for p in payload['problems']
             if p['file'].endswith('decision_problem.json')]
    assert named, payload['problems']
    assert named[0]['severity'] == 'error'
    assert 'malformed JSON' in named[0]['problem']


def test_malformed_jsonl_line_is_kept_in_place_and_reported(tmp_path):
    root = stage(tmp_path, 'peter_supplied', 'shared')
    victim = (root / ARTIFACT_REL / 'peter_supplied' / 'branches' / 'user_003'
              / 'step_ledger.jsonl')
    lines = victim.read_text(encoding='utf-8').splitlines()
    lines[2] = lines[2][:len(lines[2]) // 2]      # truncate one record
    victim.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', branch='user_003', root=root,
                    html=True)
    named = [p for p in payload['problems']
             if p['file'].endswith('user_003/step_ledger.jsonl')
             and 'malformed JSON on line 3' in p['problem']]
    assert named, payload['problems']
    # the broken record is shown, not dropped
    branch = selected_branch(payload)
    assert 'malformed' in branch['entryKinds']
    assert 'unparseable step_ledger.jsonl line 3' in ' '.join(
        branch['entryLabels'])
    assert 'This record could not be parsed.' in payload['renderedHtml']


def test_hash_mismatch_in_a_committed_event_is_reported(tmp_path):
    root = stage(tmp_path, 'peter_supplied', 'shared')
    victim = (root / ARTIFACT_REL / 'peter_supplied' / 'branches' / 'user_001'
              / 'committed_events.jsonl')
    rows = [json.loads(line) for line in
            victim.read_text(encoding='utf-8').splitlines() if line.strip()]
    rows[1]['text'] = rows[1]['text'] + ' (tampered)'   # sha256 left alone
    victim.write_text('\n'.join(json.dumps(row) for row in rows) + '\n',
                      encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', branch='user_001', root=root,
                    html=True)
    mismatched = payload['hashChecks']['mismatched']
    assert mismatched, 'a tampered event text did not trip the hash check'
    assert any(m['kind'] == 'committed_event' for m in mismatched)
    assert any('hash mismatch' in p['problem']
               and p['file'].endswith('user_001/committed_events.jsonl')
               for p in payload['problems'])
    assert 'RECOMPUTED VALUE DIFFERS' in payload['renderedHtml']


def test_hash_mismatch_in_a_frozen_input_is_reported(tmp_path):
    root = stage(tmp_path, 'peter_supplied', 'shared')
    victim = root / ARTIFACT_REL / 'peter_supplied' / 'evidence_manifest.json'
    manifest = json.loads(victim.read_text(encoding='utf-8'))
    manifest['notes'] = 'quietly edited after the freeze'
    victim.write_text(json.dumps(manifest, indent=1), encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', root=root)
    mismatched = payload['hashChecks']['mismatched']
    assert any(m['kind'] == 'freeze_entry' for m in mismatched), mismatched
    assert any(p['file'].endswith('evidence_manifest.json')
               and 'hash mismatch' in p['problem']
               for p in payload['problems'])


def test_hash_mismatch_in_a_compiler_artifact_is_reported(tmp_path):
    root = stage(tmp_path, 'peter_supplied', 'shared')
    victim = (root / ARTIFACT_REL / 'peter_supplied' / 'compiler'
              / 'call_1_prompt.txt')
    victim.write_text(victim.read_text(encoding='utf-8') + '\n',
                      encoding='utf-8')

    payload = drive('peter_supplied__pre_fix', root=root)
    mismatched = payload['hashChecks']['mismatched']
    assert any(m['kind'] == 'compiler_file' for m in mismatched), mismatched
    assert any(m['kind'] == 'compiler_aggregate' for m in mismatched)


def test_hash_verification_uses_python_compatible_canonical_json():
    """Floats are the trap: Python writes ``0.0`` where JSON.stringify
    writes ``0``.  If the viewer used JSON.stringify it would report a
    mismatch on an intact artifact -- a false accusation."""
    payload = cached('a16z_richard_historical__pre_fix')
    kinds = set(payload['hashChecks']['kinds'])
    assert {'freeze_entry', 'state_prefix', 'call_request',
            'compiler_file'} <= kinds
    assert payload['hashChecks']['mismatched'] == []
    # the frozen model configuration really does contain floats
    config = read_json(ARTIFACTS / 'a16z_richard_historical'
                       / 'model_configuration.json')
    assert '0.0' in json.dumps(config['roles'])


def test_recomputed_hashes_agree_with_python():
    """The viewer's hash of a committed event equals Python's."""
    payload = cached('peter_supplied__pre_fix', 'user_001', True)
    rendered = rendered_committed_events(payload['renderedHtml'])
    for event in rendered:
        assert hashlib.sha256(
            event['text'].encode('utf-8')).hexdigest() == event['sha256']


# --------------------------------------------------------------------- #
# the browser IO path                                                    #
# --------------------------------------------------------------------- #

class _QuietHandlerFactory:
    """Serve the repository with the viewer's own read-only handler."""

    def __enter__(self):
        sys.path.insert(0, str(VIEWER))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'viewer_serve', VIEWER / 'serve.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        os.environ['VIEWER_SERVE_QUIET'] = '1'
        handler = functools.partial(module.ReadOnlyHandler,
                                    directory=str(REPO_ROOT))
        # the viewer's OWN server class: a browser keeps connections open,
        # so a single-threaded server would deadlock the page load
        self.httpd = module.ViewerServer(('127.0.0.1', 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        return False


def test_browser_io_path_matches_filesystem_path():
    """`fetch` + `crypto.subtle` against `viewer/serve.py` assembles the
    same view as the filesystem reader."""
    with _QuietHandlerFactory() as server:
        over_http = drive('settling_arm_b__rep_1',
                          http=f'http://127.0.0.1:{server.port}/')
    from_disk = cached('settling_arm_b__rep_1')
    for key in ('branches', 'outcome', 'problems', 'limitations', 'banner'):
        assert over_http[key] == from_disk[key], key
    assert over_http['hashChecks'] == from_disk['hashChecks']


def test_serve_py_is_read_only():
    with _QuietHandlerFactory() as server:
        base = f'http://127.0.0.1:{server.port}'
        with urllib.request.urlopen(f'{base}/viewer/index.html') as response:
            assert response.status == 200
        request = urllib.request.Request(f'{base}/viewer/index.html',
                                         data=b'x', method='POST')
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        assert caught.value.code == 405


# --------------------------------------------------------------------- #
# a real browser                                                          #
# --------------------------------------------------------------------- #

PLAYWRIGHT_MODULES = '/opt/node22/lib/node_modules'
CHROMIUM_ROOT = Path('/opt/pw-browsers')

BROWSER_PROBE = r'''
import { createRequire } from 'node:module';
const require = createRequire(process.argv[3] + '/');
const { chromium } = require('playwright');
const browser = await chromium.launch({
  args: ['--no-sandbox', '--no-proxy-server', '--disable-dev-shm-usage'],
});
const page = await browser.newPage();
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(String(error)));
await page.goto(process.argv[2], { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.replay', { timeout: 60000 });
const out = await page.evaluate(() => ({
  banner: document.querySelector('.banner-main').textContent.trim(),
  insecureWarningHidden: document.getElementById('insecure-warning').hidden,
  problems: document.querySelector('.replay .problems').textContent
    .replace(/\s+/g, ' ').trim(),
  runOptionCount: document.querySelectorAll('#run-select option').length,
  branchOptions: [...document.querySelectorAll('#branch-select option')]
    .map((option) => option.value),
  eventOrder: [...document.querySelectorAll('.committed')]
    .map((node) => node.dataset.eventId),
  eventHashes: [...document.querySelectorAll('.committed')]
    .map((node) => node.dataset.eventSha256),
  auditorBands: document.querySelectorAll('.auditor-band').length,
  timelineEntries: document.querySelectorAll('.tl-item').length,
  activeEntry: document.querySelector('.entry-detail.active')
    .dataset.entryIndex,
  position: document.getElementById('position').textContent.trim(),
}));
await page.click('#btn-next');
out.activeAfterNext = await page.locator('.entry-detail.active')
  .getAttribute('data-entry-index');
const cite = page.locator('button.cite').first();
out.citeEventId = await cite.getAttribute('data-goto-event');
await cite.scrollIntoViewIfNeeded();
await cite.click();
out.eventAfterCiteJump = await page
  .locator('.entry-detail.active .committed').getAttribute('data-event-id');
await page.click('#btn-play');
await page.waitForTimeout(2600);
await page.click('#btn-play');
out.positionAfterPlay = (await page.textContent('#position')).trim();
await page.selectOption('#run-select', 'settling_arm_b__rep_2');
await page.waitForSelector('.refusal-band', { timeout: 60000 });
out.refusalBand = (await page.textContent('.refusal-band')).trim();
out.refusalProblems = (await page.textContent('.replay .problems'))
  .replace(/\s+/g, ' ').trim();
out.pageErrors = pageErrors;
await browser.close();
process.stdout.write(JSON.stringify(out));
'''


@pytest.mark.skipif(not CHROMIUM_ROOT.exists(),
                    reason='no headless browser is installed here')
def test_viewer_renders_and_plays_in_a_real_browser(tmp_path):
    """Drive the actual page: fetch, WebCrypto hashing, playback, and the
    committed-event order read back out of the live DOM."""
    probe = tmp_path / 'browser_probe.mjs'
    probe.write_text(BROWSER_PROBE, encoding='utf-8')
    env = {key: value for key, value in os.environ.items()
           if 'proxy' not in key.lower()}

    with _QuietHandlerFactory() as server:
        url = (f'http://127.0.0.1:{server.port}/viewer/index.html'
               '#run=peter_supplied__pre_fix&branch=user_002&entry=0')
        completed = subprocess.run(
            [NODE, str(probe), url, PLAYWRIGHT_MODULES],
            capture_output=True, text=True, timeout=600, env=env,
            cwd=str(REPO_ROOT))
    assert completed.returncode == 0, completed.stderr[-3000:]
    result = json.loads(completed.stdout)

    assert result['pageErrors'] == []
    assert result['banner'] == 'UNCALIBRATED LIVE-MODEL EXPLORATORY SIMULATION'
    assert result['insecureWarningHidden'] is True
    assert result['runOptionCount'] == 14
    assert result['branchOptions'] == ['0', '1', '2']

    # the live DOM's committed-event order is the frozen file's order
    rows = read_jsonl(ARTIFACTS / 'peter_supplied' / 'branches' / 'user_002'
                      / 'committed_events.jsonl')
    assert result['eventOrder'] == [row['event_id'] for row in rows]
    assert result['eventHashes'] == [row['sha256'] for row in rows]
    assert result['timelineEntries'] == len(rows)

    # hashes were recomputed in the browser with WebCrypto, and matched
    assert 'No artifact problem found' in result['problems']
    assert '101 published hashes recomputed and matched' in result['problems']

    # playback and navigation
    assert result['activeEntry'] == '0'
    assert result['activeAfterNext'] == '1'
    assert result['eventAfterCiteJump'] == result['citeEventId']
    assert result['positionAfterPlay'].startswith('6 /')
    assert result['auditorBands'] >= 4

    # switching to a settling arm renders the refusal as a first-class result
    assert result['refusalBand'] == (
        'RANKING REFUSED -- this is a first-class result, not an error')
    assert 'No artifact problem found' in result['refusalProblems']


def test_viewer_never_writes_to_the_artifact_tree():
    """A presentation layer must not be able to change what it presents."""
    sources = [path for path in VIEWER.rglob('*')
               if path.suffix in {'.js', '.py', '.html', '.css'}]
    assert sources
    forbidden = ('writeFile', 'appendFile', 'unlink', 'rmdir', 'mkdir',
                 'open(', 'shutil.copy', 'os.remove')
    for path in sources:
        if path.name == 'serve.py':
            continue          # audited separately; it only reads and serves
        text = path.read_text(encoding='utf-8')
        for token in forbidden:
            assert token not in text, f'{path} contains {token!r}'
    serve_text = (VIEWER / 'serve.py').read_text(encoding='utf-8')
    for token in ('writeFile', 'shutil.copy', 'os.remove', 'os.unlink'):
        assert token not in serve_text
