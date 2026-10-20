"""Whole-bundle selection preserves unselected manuscripts and review history."""
import json
from pathlib import Path

import pytest

from haean import exam_resume as legacy
from haean.full_exam import bundles
from haean.pipeline import feedback, run_pipeline, save
from haean.resume_selection import selected_slots
from test_composition_adapter import inputs, prepared, read
from test_composition_resume import HistoryProvider, hashes, history, install_runtime


def legacy_history(inputs, tmp_path, draft, modes=None):
    plan = read(inputs['plan'])
    previous = tmp_path / 'previous'
    previous.mkdir()
    (previous / 'plan.json').write_bytes(inputs['plan'].read_bytes())
    jobs = []
    for index, group in enumerate(bundles(plan)):
        run = prepared(previous / 'bundles' / str(index), group)
        try:
            run_pipeline(run, HistoryProvider(draft, (modes or {}).get(index, 'ready')), max_revisions=0)
        except RuntimeError:
            pass
        jobs.append({'bundle': index + 1, 'run': str(run), 'ids': [slot['id'] for slot in group],
                     'slots': [slot['number'] for slot in group], 'state': read(run / 'status.json')['state']})
    save(previous / 'production.json', {'exam': plan['exam'], 'subject': plan['subject'], 'total': 40,
         'jobs': jobs, 'complete': False, 'human_approved': False})
    return previous


def legacy_runtime(monkeypatch, draft, mode='ready'):
    providers = []
    def prepare(corpus, brief, root):
        index = len(list(root.glob('*'))) if root.exists() else 0
        group = [{'id': 'prepare-only', 'number': 1, 'topic': brief.topic, 'item_type': brief.item_type}]
        run = prepared(root / str(index), group)
        context = read(run / 'context.json')
        context.update(brief=brief.model_dump())
        context.pop('exam_assignment')
        save(run / 'context.json', context)
        save(run / 'brief.json', brief.model_dump())
        return run
    def provider(*args, **kwargs):
        value = HistoryProvider(draft, mode)
        providers.append(value)
        return value
    monkeypatch.setattr(legacy, 'prepare', prepare)
    monkeypatch.setattr(legacy, 'Corpus', lambda _: None)
    monkeypatch.setattr(legacy, 'CodexProvider', provider)
    monkeypatch.setattr('haean.full_exam.render_exam', lambda *args: None)
    return providers


@pytest.mark.parametrize('kind', ['legacy', 'composition'])
def test_selected_only_executes_one_bundle_preserving_incomplete_unselected(inputs, tmp_path, draft, monkeypatch, kind):
    modes = {1: 'seedless', 2: 'seeded', 3: 'reviewed'}
    previous = (legacy_history if kind == 'legacy' else history)(inputs, tmp_path, draft, modes=modes)
    original_jobs = read(previous / 'production.json')['jobs']
    providers = (legacy_runtime if kind == 'legacy' else install_runtime)(monkeypatch, draft)
    before = hashes(previous)
    out = tmp_path / 'selected'
    result = legacy.resume(previous, 'unused', out, workers=1, max_revisions=0, slots=original_jobs[3]['slots'])
    assert len(providers) == 1
    assert [call[0] for call in providers[0].calls] == ['revise', 'blind', 'editor']
    manifest = read(out / 'production.json')
    assert len(manifest['jobs']) == len(original_jobs) and manifest['total'] == 40
    assert not manifest['complete'] and not result['ready_for_human_review']
    assert any('미작성' in error for error in result['errors'])
    assert hashes(previous) == before
    assert (out / 'plan.json').read_bytes() == (previous / 'plan.json').read_bytes()
    for index, job in enumerate(manifest['jobs']):
        assert job['ids'] == original_jobs[index]['ids'] and job['slots'] == original_jobs[index]['slots']
        if index != 3:
            assert job['run'] == original_jobs[index]['run'] and job['reused'] and job['deferred']
            assert job['state'] == read(Path(job['run']) / 'status.json')['state']
            assert job['source_manifest_state'] == original_jobs[index]['state']
            assert job['source_run_state'] == job['state']
    # The next request can select a previously deferred, unreviewed draft.
    providers.clear()
    second = tmp_path / 'selected-again'
    legacy.resume(out, 'unused', second, workers=1, max_revisions=0, slots=original_jobs[2]['slots'])
    assert len(providers) == 1 and [call[0] for call in providers[0].calls] == ['blind', 'editor']
    assert read(second / 'production.json')['jobs'][3]['run'] == manifest['jobs'][3]['run']
    assert hashes(previous) == before


@pytest.mark.parametrize('kind', ['legacy', 'composition'])
@pytest.mark.parametrize('opinion', ['A', 'B', 'C', 'stale'])
def test_unselected_pending_feedback_cannot_make_assembly_ready(inputs, tmp_path, draft, monkeypatch, kind, opinion):
    previous = (legacy_history if kind == 'legacy' else history)(inputs, tmp_path, draft, modes={})
    jobs = read(previous / 'production.json')['jobs']
    parent = Path(jobs[0]['run'])
    item_id = read(parent / 'candidate.json')['items'][0]['id']
    feedback(parent, item_id, '보존할 후속 의견', '합성 검토자', 'B' if opinion == 'stale' else opinion)
    if opinion == 'stale':
        source = parent.parent / 'feedback.jsonl'
        value = read(source)
        value['candidate_sha256'] = '0' * 64
        source.write_text(json.dumps(value, ensure_ascii=False) + '\n')
    state = read(parent / 'status.json')
    state['state'] = 'awaiting_human_review'  # Old status must not override a valid current A/B.
    save(parent / 'status.json', state)
    selected_parent = Path(jobs[1]['run'])
    feedback(selected_parent, jobs[1]['ids'][0], '선택 묶음 수정', '합성 검토자', 'B')
    providers = (legacy_runtime if kind == 'legacy' else install_runtime)(monkeypatch, draft)
    before = hashes(previous)
    out = tmp_path / 'selected'
    result = legacy.resume(previous, 'unused', out, workers=1, max_revisions=0, slots=jobs[1]['slots'])
    assert len(providers) == 1 and hashes(previous) == before
    manifest = read(out / 'production.json')
    pending = opinion in {'A', 'B'}
    assert manifest['complete'] is not pending and result['ready_for_human_review'] is not pending
    deferred = manifest['jobs'][0]
    assert deferred['run'] == str(parent) and deferred['state'] == 'awaiting_human_review'
    assert bool(deferred.get('pending_revision_feedback')) is pending
    view = read(out / 'items' / '01' / 'status.json')
    assert view['state'] == ('needs_revision' if pending else 'awaiting_human_review')
    if pending:
        assert view['parent_state'] == 'awaiting_human_review'
        assert view['pending_revision_feedback']['records'][0]['entry']['text'] == '보존할 후속 의견'


@pytest.mark.parametrize('kind', ['legacy', 'composition'])
@pytest.mark.parametrize('slots', [[], [1, 1], [True], [1.0], ['1'], '1', [0], [41], [1]])
def test_invalid_selection_never_creates_output_or_provider(inputs, tmp_path, draft, monkeypatch, kind, slots):
    previous = (legacy_history if kind == 'legacy' else history)(inputs, tmp_path, draft, modes={})
    from haean import composition_resume
    for module in (legacy, composition_resume):
        monkeypatch.setattr(module, 'prepare', lambda *a, **k: pytest.fail('invalid selection prepared output'))
        monkeypatch.setattr(module, 'CodexProvider', lambda *a, **k: pytest.fail('invalid selection called model'))
    out = tmp_path / 'invalid'
    with pytest.raises(ValueError):
        legacy.resume(previous, 'unused', out, slots=slots)
    assert not out.exists()


@pytest.mark.parametrize('mutation', ['slots', 'ids', 'run', 'candidate', 'assignment'])
def test_unselected_legacy_inputs_are_checked_before_output(inputs, tmp_path, draft, monkeypatch, mutation):
    previous = legacy_history(inputs, tmp_path, draft)
    manifest = read(previous / 'production.json')
    source = manifest['jobs'][2]
    if mutation == 'slots':
        source['slots'].reverse()
    elif mutation == 'ids':
        source['ids'] = manifest['jobs'][1]['ids']
    elif mutation == 'run':
        source['run'] = manifest['jobs'][1]['run']
    elif mutation == 'candidate':
        path = Path(source['run']) / 'candidate.json'
        path.write_text(path.read_text() + '\n')
    else:
        path = Path(source['run']) / 'context.json'
        value = read(path)
        value['exam_assignment'][0]['number'] = 1
        save(path, value)
    save(previous / 'production.json', manifest)
    monkeypatch.setattr(legacy, 'prepare', lambda *a, **k: pytest.fail('invalid input prepared output'))
    out = tmp_path / 'invalid'
    with pytest.raises(ValueError):
        legacy.resume(previous, 'unused', out, slots=manifest['jobs'][0]['slots'])
    assert not out.exists()


@pytest.mark.parametrize('kind', ['legacy', 'composition'])
def test_selection_cannot_be_combined_with_replacements(inputs, tmp_path, draft, kind):
    previous = (legacy_history if kind == 'legacy' else history)(inputs, tmp_path, draft, modes={})
    out = tmp_path / 'invalid'
    with pytest.raises(ValueError, match='replacements'):
        legacy.resume(previous, 'unused', out, slots=[1, 2, 3, 4], replacements=[previous / 'production.json'])
    assert not out.exists()


def test_shared_passage_cannot_be_selected_through_split_manifest():
    plan = {'slots': [{'id': 'a', 'number': 1, 'shared_passage_id': 'pair'},
                      {'id': 'b', 'number': 2, 'shared_passage_id': 'pair'}]}
    jobs = [{'ids': ['a'], 'slots': [1], 'run': '/synthetic/a'},
            {'ids': ['b'], 'slots': [2], 'run': '/synthetic/b'}]
    with pytest.raises(ValueError, match='공통지문'):
        selected_slots(plan, jobs, [1, 2])


@pytest.mark.parametrize('kind', ['legacy', 'composition'])
def test_selected_failed_revision_replays_exact_seed_and_feedback(inputs, tmp_path, draft, monkeypatch, kind):
    previous = (legacy_history if kind == 'legacy' else history)(inputs, tmp_path, draft, modes={})
    jobs = read(previous / 'production.json')['jobs']
    parent = Path(jobs[1]['run'])
    feedback(parent, jobs[1]['ids'][0], '선택한 원본의 수정 의견', '합성 검토자', 'B')
    setup = legacy_runtime if kind == 'legacy' else install_runtime
    setup(monkeypatch, draft, mode='revision_failure')
    first = tmp_path / 'first'
    legacy.resume(previous, 'unused', first, workers=1, max_revisions=0, slots=jobs[1]['slots'])
    inherited = Path(read(first / 'production.json')['jobs'][1]['run'])
    assert read(inherited / 'inherited-draft.json') == read(parent / 'candidate.json')
    before = hashes(previous), hashes(first)
    providers = setup(monkeypatch, draft)
    second = tmp_path / 'second'
    result = legacy.resume(first, 'unused', second, workers=1, max_revisions=0, slots=jobs[1]['slots'])
    assert result['ready_for_human_review'], result['errors']
    assert len(providers) == 1 and [call[0] for call in providers[0].calls] == ['revise', 'blind', 'editor']
    assert providers[0].calls[0][2]['revision_feedback']['run'] == str(parent)
    assert (hashes(previous), hashes(first)) == before


@pytest.mark.parametrize('kind', ['legacy', 'composition'])
def test_copied_deferral_flags_do_not_override_current_ready_sources(inputs, tmp_path, draft, monkeypatch, kind):
    previous = (legacy_history if kind == 'legacy' else history)(inputs, tmp_path, draft, modes={})
    manifest = read(previous / 'production.json')
    for index in (0, 1):
        manifest['jobs'][index].update(deferred=True, pending_revision_feedback={'copied_old_marker': True})
    save(previous / 'production.json', manifest)
    providers = (legacy_runtime if kind == 'legacy' else install_runtime)(monkeypatch, draft)
    before = hashes(previous)
    out = tmp_path / 'selected'
    result = legacy.resume(previous, 'unused', out, workers=1, max_revisions=0, slots=manifest['jobs'][0]['slots'])
    actual = read(out / 'production.json')
    assert result['ready_for_human_review'] and actual['complete'] and not providers
    assert 'deferred' not in actual['jobs'][0] and 'pending_revision_feedback' not in actual['jobs'][0]
    assert actual['jobs'][1]['deferred'] and 'pending_revision_feedback' not in actual['jobs'][1]
    assert hashes(previous) == before


def test_legacy_selective_preparation_cannot_change_a_preserved_source(inputs, tmp_path, draft, monkeypatch):
    previous = legacy_history(inputs, tmp_path, draft, modes={1: 'reviewed'})
    jobs = read(previous / 'production.json')['jobs']
    providers = legacy_runtime(monkeypatch, draft)
    prepare = legacy.prepare
    def changing_prepare(*args, **kwargs):
        run = prepare(*args, **kwargs)
        path = Path(jobs[0]['run']) / 'context.json'
        path.write_text(path.read_text() + '\n')
        return run
    monkeypatch.setattr(legacy, 'prepare', changing_prepare)
    out = tmp_path / 'selected'
    result = legacy.resume(previous, 'unused', out, workers=1, max_revisions=0, slots=jobs[1]['slots'])
    actual = read(out / 'production.json')
    assert not providers and not result['ready_for_human_review'] and not actual['complete']
    assert actual['jobs'][1]['state'] == 'failed'
    assert '원본 입력·검토 변경' in actual['jobs'][1]['error']


def test_unselected_composition_review_receipt_is_still_verified(inputs, tmp_path, draft, monkeypatch):
    previous = history(inputs, tmp_path, draft, modes={1: 'reviewed'})
    jobs = read(previous / 'production.json')['jobs']
    path = Path(jobs[1]['run']) / 'review-r0.json'
    path.write_text(path.read_text() + '\n')
    providers = install_runtime(monkeypatch, draft)
    out = tmp_path / 'invalid'
    with pytest.raises(ValueError, match='해시'):
        legacy.resume(previous, 'unused', out, slots=jobs[0]['slots'])
    assert not out.exists() and not providers
