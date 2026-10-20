"""External revision intent is bound to a reviewed version, never its status."""
from pathlib import Path
import json

import pytest

from haean import exam_resume, composition_resume
from haean.pipeline import feedback, save
from haean.revision_request import create_request, load_request
from haean.revision_feedback import load_revision_feedback, requires_revision, validate_revision_feedback
from test_composition_adapter import inputs, read
from test_composition_resume import history, install_runtime, hashes
from test_resume_selection import legacy_history, legacy_runtime


@pytest.fixture(params=['legacy', 'composition'])
def scenario(request, inputs, tmp_path, draft):
    previous = (legacy_history if request.param == 'legacy' else history)(inputs, tmp_path, draft, modes={})
    return previous, legacy_runtime if request.param == 'legacy' else install_runtime


def request_file(previous, tmp_path, *, index=0, name='request.json', **kwargs):
    job = read(previous / 'production.json')['jobs'][index]
    out = tmp_path / name
    packet = create_request(previous, out, slots=job['slots'],
        text='합성 수정 요청 원문\n정답은 유지하고 오답의 추론 경로를 검토하세요.',
        reviewer='합성 총괄', origin='model', **kwargs)
    return out, packet, job


def test_explicit_c_revises_once_without_source_mutation(scenario, tmp_path, draft, monkeypatch):
    previous, setup = scenario
    before = hashes(previous)
    request, packet, job = request_file(previous, tmp_path)
    assert hashes(previous) == before
    assert packet['severity'] == 'C' and packet['expert_verified'] is False
    assert load_request(request)['packet'] == packet
    providers = setup(monkeypatch, draft)
    out = tmp_path / 'next'
    result = exam_resume.resume(previous, 'unused', out, slots=job['slots'], revision_requests=[request], workers=1, max_revisions=0)
    assert result['ready_for_human_review'], result['errors']
    assert hashes(previous) == before and len(providers) == 1
    assert [call[0] for call in providers[0].calls] == ['revise', 'blind', 'editor']
    calls = providers[0].calls
    combined = calls[0][2]['revision_feedback']
    assert combined['schema_version'] == 2 and requires_revision(combined)
    assert combined['records'][-1]['entry']['text'] == packet['text']
    assert calls[0][2]['review'] == read(Path(job['run']) / 'review-r0.json')
    assert set(calls[1][2]) == {'items'}
    assert 'revision_feedback' not in json.dumps(calls[1][2])
    run = Path(read(out / 'production.json')['jobs'][0]['run'])
    assert load_revision_feedback(run, read(run / 'candidate.json')) is None
    # The inherited request is consumed by the fresh review, without caller deletion.
    providers.clear()
    repeated = tmp_path / 'repeated'
    exam_resume.resume(out, 'unused', repeated, slots=job['slots'], workers=1, max_revisions=0)
    assert not providers and hashes(previous) == before
    assert read(repeated / 'production.json')['jobs'][0]['run'] == str(run)


def test_local_c_stays_nonforcing_and_is_delivered_with_explicit_request(scenario, tmp_path, draft, monkeypatch):
    previous, setup = scenario
    job = read(previous / 'production.json')['jobs'][0]
    parent = Path(job['run'])
    opinion = feedback(parent, job['ids'][0], '합성 기존 C 의견', '검토자', 'C', origin='model')
    assert not requires_revision(load_revision_feedback(parent, read(parent / 'candidate.json')))
    providers = setup(monkeypatch, draft)
    exam_resume.resume(previous, 'unused', tmp_path / 'unforced', slots=job['slots'], workers=1, max_revisions=0)
    assert not providers
    request, packet, job = request_file(previous, tmp_path)
    before = hashes(previous)
    result = exam_resume.resume(previous, 'unused', tmp_path / 'forced', slots=job['slots'], revision_requests=[request], workers=1, max_revisions=0)
    assert result['ready_for_human_review'], result['errors']
    combined = providers[0].calls[0][2]['revision_feedback']
    assert combined['local_feedback']['records'][0]['entry'] == opinion
    assert combined['records'][0]['entry'] == opinion
    assert combined['records'][1]['entry']['text'] == packet['text']
    assert hashes(previous) == before
    validate_revision_feedback(combined, read(parent / 'candidate.json'))
    forged = json.loads(json.dumps(combined))
    forged['records'][0]['entry']['text'] = '변조'
    with pytest.raises(ValueError):
        validate_revision_feedback(forged, read(parent / 'candidate.json'))


@pytest.mark.parametrize('slots', [None, [], [1], [1, 1], [True], [41]])
def test_invalid_request_selection_creates_nothing(scenario, tmp_path, slots):
    previous, _ = scenario
    out = tmp_path / 'invalid' / 'request.json'
    with pytest.raises(ValueError):
        create_request(previous, out, slots=slots, text='합성 의견', reviewer='검토자', origin='model')
    assert not out.parent.exists()


@pytest.mark.parametrize('values', [{'reviewer': ''}, {'text': ' '}, {'origin': 'expert'}, {'severity': 'D'}])
def test_unnamed_or_invalid_request_creates_nothing(scenario, tmp_path, values):
    previous, _ = scenario
    options = dict(text='합성 의견', reviewer='검토자', origin='model', severity='C')
    options.update(values)
    out = tmp_path / 'invalid.json'
    with pytest.raises(ValueError):
        create_request(previous, out, slots=read(previous / 'production.json')['jobs'][0]['slots'], **options)
    assert not out.exists()


@pytest.mark.parametrize('mutation', ['candidate', 'context', 'brief', 'review', 'status', 'plan', 'manifest', 'feedback', 'latest_draft', 'request'])
def test_stale_inputs_rejected_before_output_and_provider(scenario, tmp_path, draft, monkeypatch, mutation):
    previous, setup = scenario
    request, packet, job = request_file(previous, tmp_path)
    parent = Path(job['run'])
    if mutation in {'candidate', 'context', 'brief', 'status'}:
        path = parent / (mutation + '.json')
    elif mutation == 'review':
        path = parent / 'review-r0.json'
    elif mutation == 'plan':
        path = previous / 'plan.json'
    elif mutation == 'manifest':
        path = previous / 'production.json'
    elif mutation == 'latest_draft':
        path = parent / 'draft-r1.json'
        save(path, read(parent / 'candidate.json'))
    elif mutation == 'feedback':
        feedback(parent, job['ids'][0], '새 후속 의견', '검토자', 'C')
        path = parent.parent / 'feedback.jsonl'
    else:
        value = read(request)
        value['bundles'][0]['candidate']['sha256'] = '0' * 64
        save(request, value)
        path = request
    path.write_text(path.read_text() + '\n')
    providers = setup(monkeypatch, draft)
    out = tmp_path / 'invalid'
    with pytest.raises(ValueError):
        exam_resume.resume(previous, 'unused', out, slots=job['slots'], revision_requests=[request], workers=1)
    assert not out.exists() and not providers


@pytest.mark.parametrize('kind', ['selection_required', 'outside', 'duplicate', 'other_exam', 'replacement'])
def test_request_scope_rejected_before_output(scenario, tmp_path, draft, monkeypatch, kind):
    previous, setup = scenario
    request, packet, job = request_file(previous, tmp_path)
    options = dict(slots=job['slots'], revision_requests=[request])
    target = previous
    if kind == 'selection_required':
        options.pop('slots')
    elif kind == 'outside':
        options['slots'] = read(previous / 'production.json')['jobs'][1]['slots']
    elif kind == 'duplicate':
        options['revision_requests'].append(request)
    elif kind == 'replacement':
        options['replacements'] = [previous / 'production.json']
    else:
        target = tmp_path / 'another-exam'
        target.mkdir()
        for name in ['plan.json', 'production.json']:
            (target / name).write_bytes((previous / name).read_bytes())
    providers = setup(monkeypatch, draft)
    out = tmp_path / 'invalid'
    with pytest.raises(ValueError):
        exam_resume.resume(target, 'unused', out, workers=1, **options)
    assert not out.exists() and not providers


@pytest.mark.parametrize('failure', ['revision_failure', 'seeded', 'constructor'])
def test_interrupted_request_lifecycle(scenario, tmp_path, draft, monkeypatch, failure):
    previous, setup = scenario
    request, packet, job = request_file(previous, tmp_path)
    setup(monkeypatch, draft, mode=failure)
    if failure == 'constructor':
        def fail(*args, **kwargs):
            raise RuntimeError('synthetic constructor failure')
        monkeypatch.setattr(exam_resume, 'CodexProvider', fail)
        monkeypatch.setattr(composition_resume, 'CodexProvider', fail)
    before = hashes(previous)
    first = tmp_path / 'first'
    exam_resume.resume(previous, 'unused', first, slots=job['slots'], revision_requests=[request], workers=1, max_revisions=0)
    assert read(first / 'production.json')['jobs'][0]['state'] == 'failed'
    first_before = hashes(first)
    providers = setup(monkeypatch, draft)
    result = exam_resume.resume(first, 'unused', tmp_path / 'second', slots=job['slots'], workers=1, max_revisions=0)
    assert result['ready_for_human_review'], result['errors']
    stages = [call[0] for call in providers[0].calls]
    assert stages == (['blind', 'editor'] if failure == 'seeded' else ['revise', 'blind', 'editor'])
    packet = providers[0].calls[-1][2]['revision_feedback']
    assert packet['application'] == ('historical_review' if failure == 'seeded' else 'pending_revision')
    assert packet['schema_version'] == 2
    assert hashes(previous) == before and hashes(first) == first_before


def test_request_saved_outside_source_and_exclusive(scenario, tmp_path):
    previous, _ = scenario
    job = read(previous / 'production.json')['jobs'][0]
    before = hashes(previous)
    unselected = read(previous / 'production.json')['jobs'][1]
    for out in (previous / 'request.json', Path(job['run']) / 'request.json', Path(unselected['run']) / 'request.json'):
        with pytest.raises(ValueError, match='밖에'):
            create_request(previous, out, slots=job['slots'], text='요청', reviewer='검토자', origin='human')
    request, _, _ = request_file(previous, tmp_path)
    content = request.read_bytes()
    with pytest.raises(ValueError, match='새 수정 요청'):
        create_request(previous, request, slots=job['slots'], text='다른 요청', reviewer='검토자', origin='human')
    assert request.read_bytes() == content and hashes(previous) == before


def test_request_changed_during_preparation_stops_before_provider(scenario, tmp_path, draft, monkeypatch):
    previous, setup = scenario
    request, _, job = request_file(previous, tmp_path)
    providers = setup(monkeypatch, draft)
    module = exam_resume if setup == legacy_runtime else composition_resume
    original_prepare = module.prepare
    def changing_prepare(*args, **kwargs):
        run = original_prepare(*args, **kwargs)
        request.write_text(request.read_text() + '\n')
        return run
    monkeypatch.setattr(module, 'prepare', changing_prepare)
    out = tmp_path / 'changed'
    result = exam_resume.resume(previous, 'unused', out, slots=job['slots'], revision_requests=[request], workers=1, max_revisions=0)
    assert not providers and not result['ready_for_human_review']
    assert read(out / 'production.json')['jobs'][0]['state'] == 'failed'


def test_disjoint_requests_keep_each_original_text(scenario, tmp_path, draft, monkeypatch):
    previous, setup = scenario
    first, _, first_job = request_file(previous, tmp_path, index=0, name='first.json')
    second_job = read(previous / 'production.json')['jobs'][1]
    second = tmp_path / 'second.json'
    create_request(previous, second, slots=second_job['slots'], text='두 번째 묶음 전용 수정 원문',
        reviewer='다른 합성 총괄', origin='human', severity='B')
    providers = setup(monkeypatch, draft)
    before = hashes(previous)
    out = tmp_path / 'next'
    result = exam_resume.resume(previous, 'unused', out, slots=first_job['slots'] + second_job['slots'],
        revision_requests=[first, second], workers=1, max_revisions=0)
    assert result['ready_for_human_review'] and len(providers) == 2
    texts = [provider.calls[0][2]['revision_feedback']['records'][-1]['entry']['text'] for provider in providers]
    assert texts == [read(first)['text'], read(second)['text']]
    assert hashes(previous) == before


def test_reviewed_candidate_must_be_latest_draft_before_request(scenario, tmp_path):
    previous, _ = scenario
    job = read(previous / 'production.json')['jobs'][0]
    parent = Path(job['run'])
    changed = read(parent / 'candidate.json')
    changed['items'][0]['explanation'] += ' 최신 미검토 초안'
    save(parent / 'draft-r1.json', changed)
    with pytest.raises(ValueError):
        create_request(previous, tmp_path / 'request.json', slots=job['slots'],
            text='오래된 candidate에 수정 요청', reviewer='합성 총괄', origin='model')
    assert not (tmp_path / 'request.json').exists()


def test_external_source_feedback_ledger_cannot_be_request_destination(scenario, tmp_path):
    original, _ = scenario
    # Real production manifests may reference runs outside the exam directory.
    previous = tmp_path / 'external-run-exam'
    previous.mkdir()
    for name in ('production.json', 'plan.json'):
        (previous / name).write_bytes((original / name).read_bytes())
    jobs = read(previous / 'production.json')['jobs']
    ledger = Path(jobs[0]['run']).parent / 'feedback.jsonl'
    assert not ledger.exists()
    before = hashes(original), hashes(previous)
    with pytest.raises(ValueError, match='feedback.jsonl'):
        create_request(previous, ledger, slots=jobs[0]['slots'], text='합성 수정 요청',
            reviewer='합성 총괄', origin='model')
    assert not ledger.exists()
    assert (hashes(original), hashes(previous)) == before
