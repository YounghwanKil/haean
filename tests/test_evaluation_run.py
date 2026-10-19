"""Saved-revision evaluation must preserve the actual request and source run."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from haean.evaluation import DIMENSIONS, Evaluation
from haean.evaluation_run import evaluate_run
from haean.pipeline import save


def read(path):
    return json.loads(path.read_text())


def tree_bytes(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob('*') if p.is_file()}


def review_for(draft, revision):
    return {
        'revision': revision,
        'blind': {'solutions': [
            {'item_id': item.id, 'answer': item.answer, 'uniquely_answerable': True,
             'option_reasons': ['합성 선지 근거'] * 5, 'missing_conditions': []}
            for item in draft.items], 'issues': []},
        'editorial': {'issues': [], 'summary': '합성 검토, 실제 전문가 판단 아님'},
        'errors': [], 'similarity_hits': [],
    }


class EvaluationProvider:
    def __init__(self, mutation=None, result_ids=None):
        self.calls = 0
        self.usage = []
        self.payloads = []
        self.mutation = mutation
        self.result_ids = result_ids

    def call(self, stage, instructions, payload, schema):
        assert stage == 'evaluate'
        assert schema is Evaluation
        self.calls += 1
        self.payloads.append(copy.deepcopy(payload))
        if self.mutation:
            self.mutation()
        ids = self.result_ids if self.result_ids is not None else [i['id'] for i in payload['draft']['items']]
        return Evaluation.model_validate({
            'items': [{'item_id': item_id,
                       'dimensions': [{'name': name, 'score': 3, 'evidence': '합성 점수 근거'}
                                      for name in sorted(DIMENSIONS)],
                       'fatal_errors': [], 'missing_evidence': ['합성 테스트, 전문가 검토 없음'],
                       'expert_verified': False} for item_id in ids],
            'summary': '합성 평가 응답',
        })


@pytest.fixture
def revision_run(tmp_path, draft, brief, monkeypatch):
    # The only process queried by this API is Codex's version, never a model.
    monkeypatch.setattr('haean.evaluation_run.subprocess.run',
                        lambda *a, **kw: SimpleNamespace(stdout='synthetic-codex-version\n'))
    run = tmp_path / 'source-run'
    run.mkdir()
    shared_brief = brief.model_copy(update={'count': 2, 'shared_passage': True, 'difficulty': '중'})
    first = draft.items[0].model_copy(deep=True)
    first.difficulty = '상'
    first.shared_passage_id = 'SYNTHETIC-SHARED'
    second = first.model_copy(deep=True)
    second.id = 'TEST-002'
    second.item_type = '논증 평가'
    second.difficulty = '하'
    initial = draft.model_copy(update={'items': [first, second]}, deep=True)
    final = initial.model_copy(deep=True)
    final.items[1].explanation += ' 최종 버전에서 표현을 구체화했다.'
    assignment = [{'id': i.id, 'number': n, 'item_type': i.item_type,
                   'difficulty': i.difficulty, 'topic': i.topic,
                   'shared_passage_id': i.shared_passage_id}
                  for n, i in enumerate(initial.items, 1)]
    save(run / 'brief.json', shared_brief.model_dump())
    save(run / 'context.json', {'brief': shared_brief.model_dump(), 'exam_assignment': assignment,
                               'references': [{'id': 'source-1', 'text': '합성 출처'}]})
    for revision, candidate in enumerate((initial, final)):
        save(run / f'draft-r{revision}.json', candidate.model_dump())
        save(run / f'review-r{revision}.json', review_for(candidate, revision))
    save(run / 'candidate.json', final.model_dump())
    save(run / 'status.json', {'state': 'needs_revision', 'revision': 1,
        'human_approved': False, 'errors': ['후속 구조 반복 의견은 저장 revision 평가와 별개'],
        'candidate_sha256': hashlib.sha256((run / 'candidate.json').read_bytes()).hexdigest()})
    save(run / 'human-checkpoint.json', {'note': '합성 기존 기록, 자동 승인하지 않음'})
    save(run / 'evaluation.json', {'protocol': 'legacy-v2', 'summary': '과거 점수를 덮어쓰지 않음'})
    return run


def test_saved_initial_and_current_get_per_id_targets_and_preserve_originals(tmp_path, revision_run):
    before = tree_bytes(revision_run)
    initial_provider, final_provider = EvaluationProvider(), EvaluationProvider()
    initial_out, final_out = tmp_path / 'initial-eval', tmp_path / 'final-eval'
    initial = evaluate_run(revision_run, initial_out, revision=0, provider=initial_provider)
    current = evaluate_run(revision_run, final_out, provider=final_provider)

    assert initial['complete'] and current['complete']
    for result in (initial, current):
        assert result['quality'] == 3 and result['model_eligible'] is True
        assert result['eligible'] is False
        assert result['saved_provenance']['requirements'] == 'unverified'
        assert result['saved_provenance']['review'] == 'unverified'
    assert initial['selected_revision'] == 0 and initial['selected_current'] is False
    assert current['selected_revision'] == 1 and current['selected_current'] is True
    assert initial_provider.calls == final_provider.calls == 1
    for provider, out in ((initial_provider, initial_out), (final_provider, final_out)):
        payload = provider.payloads[0]
        assert payload['requirements_source'] == 'context.exam_assignment'
        requirements = {r['id']: r for r in payload['item_requirements']}
        assert (requirements['TEST-001']['item_type'], requirements['TEST-001']['difficulty']) == ('조건 추론', '상')
        assert (requirements['TEST-002']['item_type'], requirements['TEST-002']['difficulty']) == ('논증 평가', '하')
        assert payload['brief']['item_type'] == '조건 추론' and payload['brief']['difficulty'] == '중'
        assert read(out / 'evaluation-input.json') == payload
        assert read(out / 'evaluation.json')['items'][1]['item_id'] == 'TEST-002'
    assert initial_provider.payloads[0]['draft'] == read(revision_run / 'draft-r0.json')
    assert final_provider.payloads[0]['draft'] == read(revision_run / 'candidate.json')
    assert initial_provider.payloads[0]['draft'] != final_provider.payloads[0]['draft']
    assert tree_bytes(revision_run) == before
    assert current['source_state_at_start'] == 'needs_revision'
    assert current['human_approved'] is False and current['release_approved'] is False
    assert current['generation_calls'] == 0 and current['actual_model'] is None


@pytest.mark.parametrize('existing_approval', [False, True])
def test_evaluation_never_changes_source_state_or_existing_human_approval(tmp_path, revision_run, existing_approval):
    status = read(revision_run / 'status.json')
    status['human_approved'] = existing_approval
    save(revision_run / 'status.json', status)
    before = tree_bytes(revision_run)
    result = evaluate_run(revision_run, tmp_path / 'evaluation', provider=EvaluationProvider())
    assert result['complete'] and result['human_approved'] is False
    assert tree_bytes(revision_run) == before
    assert read(revision_run / 'status.json')['human_approved'] is existing_approval


@pytest.mark.parametrize('mutation', ['missing_solution', 'duplicate_solution', 'wrong_solution', 'blind_issue', 'editor_issue'])
def test_saved_review_cannot_refer_to_other_or_missing_items(tmp_path, revision_run, mutation):
    path = revision_run / 'review-r1.json'
    review = read(path)
    if mutation == 'missing_solution':
        review['blind']['solutions'].pop()
    elif mutation == 'duplicate_solution':
        review['blind']['solutions'][1] = copy.deepcopy(review['blind']['solutions'][0])
    elif mutation == 'wrong_solution':
        review['blind']['solutions'][1]['item_id'] = 'OTHER-ITEM'
    else:
        role = 'blind' if mutation == 'blind_issue' else 'editorial'
        review[role]['issues'].append({'severity': 'C', 'category': '합성', 'item_id': 'OTHER-ITEM',
                                     'location': '문장', 'problem': '다른 문항 의견', 'fix': '원 검토를 확인'})
    save(path, review)
    provider = EvaluationProvider()
    out = tmp_path / 'should-not-exist'
    with pytest.raises(ValueError, match='ID|문항'):
        evaluate_run(revision_run, out, provider=provider)
    assert provider.calls == 0 and not out.exists()


@pytest.mark.parametrize('role', ['blind', 'editorial'])
def test_saved_shared_issue_with_known_ids_is_forwarded_verbatim(tmp_path, revision_run, role):
    path = revision_run / 'review-r1.json'
    review = read(path)
    issue = {'severity': 'C', 'category': '공통지문', 'item_id': 'TEST-001, TEST-002',
             'location': '공유 본문', 'problem': '두 문항에 적용되는 합성 문체 의견', 'fix': '함께 검토'}
    review[role]['issues'].append(issue)
    save(path, review)
    original = tree_bytes(revision_run)
    provider = EvaluationProvider()
    out = tmp_path / 'shared-issue-evaluation'
    result = evaluate_run(revision_run, out, provider=provider)
    assert result['complete'] is True and provider.calls == 1
    assert provider.payloads[0]['review'][role]['issues'] == [issue]
    assert read(out / 'evaluation-input.json')['review'][role]['issues'] == [issue]
    assert tree_bytes(revision_run) == original


@pytest.mark.parametrize('role', ['blind', 'editorial'])
@pytest.mark.parametrize('item_ids', ['TEST-001, OTHER-ITEM', 'TEST-001, TEST-001',
                                      'TEST-001, , TEST-002', 'TEST-001,', ',TEST-002'])
def test_saved_shared_issue_rejects_unknown_repeated_or_empty_members(tmp_path, revision_run, role, item_ids):
    path = revision_run / 'review-r1.json'
    review = read(path)
    review[role]['issues'].append({'severity': 'C', 'category': '공통지문', 'item_id': item_ids,
                                  'location': '공유 본문', 'problem': '잘못된 문항 연결', 'fix': '원문 확인'})
    save(path, review)
    original = tree_bytes(revision_run)
    provider = EvaluationProvider()
    out = tmp_path / 'invalid-shared-issue'
    with pytest.raises(ValueError, match='ID|문항'):
        evaluate_run(revision_run, out, provider=provider)
    assert provider.calls == 0 and not out.exists()
    assert tree_bytes(revision_run) == original


@pytest.mark.parametrize('destination', ['existing', 'inside_source'])
def test_existing_or_source_nested_output_is_refused_without_model(tmp_path, revision_run, destination):
    out = tmp_path / 'existing' if destination == 'existing' else revision_run / 'new-eval'
    if destination == 'existing':
        out.mkdir()
        (out / 'keep.txt').write_text('기존 결과')
    before = tree_bytes(tmp_path)
    provider = EvaluationProvider()
    with pytest.raises(ValueError, match='새 경로'):
        evaluate_run(revision_run, out, provider=provider)
    assert provider.calls == 0 and tree_bytes(tmp_path) == before


@pytest.mark.parametrize('source', ['brief.json', 'context.json', 'status.json', 'candidate.json', 'review-r1.json', 'draft-r1.json'])
def test_source_changed_during_provider_call_invalidates_result_and_preserves_response(tmp_path, revision_run, source):
    path = revision_run / source
    original = path.read_bytes()
    provider = EvaluationProvider(mutation=lambda: path.write_bytes(original + b'\n'))
    out = tmp_path / 'mutation-eval'
    result = evaluate_run(revision_run, out, provider=provider)
    assert provider.calls == 1
    assert result['state'] == 'failed' and result['complete'] is False
    assert result['eligible'] is False and result['quality'] is None
    assert '바뀌' in result['error']
    assert (out / 'evaluation.json').exists()  # Raw scoring response is evidence, not a usable success.
    assert path.read_bytes() == original + b'\n'  # The evaluator does not silently repair concurrent changes.
    assert read(revision_run / 'status.json')['state'] == 'needs_revision'


@pytest.mark.parametrize('ids', [['TEST-001'], ['TEST-001', 'TEST-001'], ['TEST-001', 'OTHER-ITEM']])
def test_evaluator_missing_duplicate_or_unknown_ids_do_not_create_success(tmp_path, revision_run, ids):
    before = tree_bytes(revision_run)
    out = tmp_path / 'invalid-evaluation'
    result = evaluate_run(revision_run, out, provider=EvaluationProvider(result_ids=ids))
    assert result['state'] == 'failed' and result['eligible'] is False
    assert result['quality'] is None and result['complete'] is False
    assert read(out / 'evaluation.json')['items'][0]['item_id'] == ids[0]
    assert tree_bytes(revision_run) == before
