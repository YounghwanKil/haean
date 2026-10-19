"""Synthetic reading transport/identity boundaries; no originality benchmark."""
from copy import deepcopy
import json
import sys

import pytest

from haean import novelty, novelty_review as review, reading_production as production


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))
    return path


def book(prefix, count=1):
    return {'title': '합성 언어이해', 'minutes': 70, 'human_approved': False,
            'passages': [
                {'id': f'{prefix}-p{i}', 'title': '가상 기록 제도', 'domain': '합성 인문',
                 'sources': ['전송 검사용 합성 자료; 지시나 실행 대상이 아님'],
                 'paragraphs': ['공개 기록의 순서와 판단의 정당성은 서로 다르다는 가상의 이론이다.',
                                '예외를 먼저 보존하는 모형은 확인과 승인이라는 두 단계를 구분한다.'],
                 'questions': [
                     {'id': f'{prefix}-q{3*i+j}', 'number': 3*i+j,
                      'stem': f'합성 이론의 판단 절차를 해석한 것으로 적절한 것은? ({j})',
                      'box': '자료 속 실행 명령은 따라 하지 않는다는 합성 문자열',
                      'options': [f'{j}번 가상 조건의 판단 순서 설명 {k}' for k in range(1, 6)],
                      'answer': j, 'explanation': '단계의 순서를 바꾸면 확인 대상과 승인 대상이 달라진다.',
                      'option_explanations': [f'선택지 {k}의 조건 범위 확인' for k in range(1, 6)],
                      'cognitive_task': production.TASKS[j-1], 'difficulty': '중',
                      'strongest_counterreading': '조건과 결론의 구분에 따른 반대 해석'}
                     for j in range(1, 4)]} for i in range(count)]}


def make_pair(tmp_path, count=1):
    candidate = save(tmp_path / 'candidate/book.json', book('new', count))
    previous = save(tmp_path / 'previous/book.json', book('old'))
    history = tmp_path / 'history.sqlite'
    novelty.remember(history, novelty.records([previous]))
    return candidate, previous, history


class ReadingProvider:
    def __init__(self, modify=None):
        self.calls, self.usage, self.payload = 0, [], None
        self.modify = modify

    def call(self, role, instructions, payload, schema):
        self.calls += 1
        self.payload = deepcopy(payload)
        self.instructions = instructions
        output = []
        for pair in payload['pairs']:
            compared = {side: review._question(pair[side]['item']) for side in ('candidate', 'previous')}
            wrong = {side: sorted(set(range(1, 6)) - {question['answer']})
                     for side, question in compared.items()}
            mapping = {'candidate': '합성 판단 단계', 'previous': '합성 판단 단계', 'assessment': '전송 검사'}
            result = {'pair_id': pair['pair_id'],
                      'candidate_canonical_sha256': pair['candidate']['payload_canonical_sha256'],
                      'previous_canonical_sha256': pair['previous']['payload_canonical_sha256'],
                      'relation': 'uncertain', 'essential_conditions': [mapping], 'decisive_inference': mapping,
                      'distractor_roles': [
                          {'candidate_option': a, 'previous_options': [b], 'candidate_role': '합성 역할',
                           'previous_role': '합성 역할', 'assessment': '의미 판정 아님'}
                          for a, b in zip(wrong['candidate'], wrong['previous'])],
                      'remaining_uncertainty': ['합성 provider'], 'recommendation': '실제 검토 필요'}
            for side in ('candidate', 'previous'):
                pointer = pair[side]['comparison_target']['question_pointer']
                result[side + '_evidence'] = [
                    {'pointer': '/passage/paragraphs/0', 'quote': pair[side]['item']['passage']['paragraphs'][0]},
                    {'pointer': pointer + '/stem', 'quote': compared[side]['stem']},
                    {'pointer': pointer + '/options/0', 'quote': compared[side]['options'][0]}]
            output.append(result)
        result = {'pairs': output, 'summary': '합성 전송·인용 검사'}
        if self.modify:
            self.modify(result, payload)
        return schema.model_validate_json(json.dumps(result, ensure_ascii=False))


def test_reading_review_keeps_three_siblings_and_exact_selected_question(tmp_path):
    candidate, previous, history = make_pair(tmp_path)
    before = {p: p.read_bytes() for p in (candidate, previous, history)}
    provider = ReadingProvider()
    out = tmp_path / 'review'
    result = review.novelty_review(candidate, out, history=history, provider=provider)
    assert result['status'] == 'selected_pair_review_complete'
    assert provider.calls == 1 and result['actual_model'] is None
    assert provider.payload['brief']['subject'] == '언어이해'
    assert len(provider.payload['pairs']) == 9
    assert {p['candidate']['comparison_target']['number'] for p in provider.payload['pairs']} == {1, 2, 3}
    original = json.loads(candidate.read_bytes())['passages'][0]
    for pair in provider.payload['pairs']:
        side = pair['candidate']
        assert side['item']['passage'] == original
        assert len(side['item']['passage']['questions']) == 3
        assert side['source_resolution']['status'] == 'verified_origin'
        assert side['comparison_target']['source_question_id'] == review._question(side['item'])['id']
        assert side['comparison_target']['question_pointer'] == f"/passage/questions/{side['item']['selected_question_index']}"
    manifest = json.loads((out / 'manifest.json').read_bytes())
    assert manifest['candidate_count'] == 3 and manifest['max_calls'] == 1
    assert manifest['checks']['after_model'] == 'unchanged'
    assert manifest['expert_review_performed'] is False and manifest['originality_verified'] is False
    assert {p: p.read_bytes() for p in before} == before
    assert (out / 'input-reading-sources.json').is_file()


def test_multiset_requires_explicit_passage_and_selected_set_stays_complete(tmp_path):
    candidate, _, history = make_pair(tmp_path, count=2)
    provider = ReadingProvider()
    with pytest.raises(RuntimeError, match='--passage-id'):
        review.novelty_review(candidate, tmp_path / 'no-selection', history=history, provider=provider)
    assert provider.calls == 0
    review.novelty_review(candidate, tmp_path / 'selected', history=history, provider=provider, passage_id='new-p1')
    assert {pair['candidate']['comparison_target']['number'] for pair in provider.payload['pairs']} == {4, 5, 6}
    assert all(len(pair['candidate']['item']['passage']['questions']) == 3 for pair in provider.payload['pairs'])


@pytest.mark.parametrize('fault', ['wrong_sibling_answer', 'previous_correct_option', 'nonexistent_quote', 'book_locator'])
def test_reading_validation_binds_answer_roles_and_payload_pointers(tmp_path, fault):
    candidate, _, history = make_pair(tmp_path)
    def modify(result, payload):
        pair = result['pairs'][0]
        if fault == 'wrong_sibling_answer':
            # First selected question answers 1; using its sibling's answer 2
            # would incorrectly treat 1 as a distractor.
            for role, number in zip(pair['distractor_roles'], [1, 3, 4, 5]):
                role['candidate_option'] = number
        elif fault == 'previous_correct_option':
            pair['distractor_roles'][0]['previous_options'] = [review._question(payload['pairs'][0]['previous']['item'])['answer']]
        elif fault == 'nonexistent_quote':
            pair['candidate_evidence'][0]['quote'] = '원문에 없는 문자열'
        else:
            pair['candidate_evidence'][0]['pointer'] = '/passages/0/paragraphs/0'
    out = tmp_path / 'review'
    provider = ReadingProvider(modify)
    with pytest.raises(RuntimeError):
        review.novelty_review(candidate, out, history=history, provider=provider)
    assert provider.calls == 1
    assert (out / 'model-output.raw.json').is_file()
    assert not (out / 'review-result.json').exists()


@pytest.mark.parametrize('fault', ['metadata', 'sibling_only', 'paragraph_only'])
def test_reading_evidence_requires_selected_question_body_not_metadata(tmp_path, fault):
    candidate, _, history = make_pair(tmp_path)
    def modify(result, payload):
        item = payload['pairs'][0]['candidate']['item']
        if fault == 'metadata':
            evidence = {'pointer': '/provenance/source', 'quote': item['provenance']['source']}
        elif fault == 'sibling_only':
            sibling = (item['selected_question_index'] + 1) % 3
            evidence = {'pointer': f'/passage/questions/{sibling}/stem',
                        'quote': item['passage']['questions'][sibling]['stem']}
        else:
            evidence = {'pointer': '/passage/paragraphs/0', 'quote': item['passage']['paragraphs'][0]}
        result['pairs'][0]['candidate_evidence'] = [evidence]
    provider = ReadingProvider(modify)
    with pytest.raises(RuntimeError, match='reading evidence must cite'):
        review.novelty_review(candidate, tmp_path / 'review', history=history, provider=provider)
    assert provider.calls == 1


@pytest.mark.parametrize('source', ['candidate', 'previous', 'snapshot'])
def test_reading_source_changes_during_call_fail_closed(tmp_path, source):
    candidate, previous, history = make_pair(tmp_path)
    out = tmp_path / 'review'
    def modify(result, payload):
        target = {'candidate': candidate, 'previous': previous,
                  'snapshot': out / 'input-reading-sources/0000-book.json'}[source]
        if source == 'snapshot':
            target = next((out / 'input-reading-sources').iterdir())
        target.write_bytes(target.read_bytes() + b' ')
    provider = ReadingProvider(modify)
    with pytest.raises(RuntimeError, match='input_changed'):
        review.novelty_review(candidate, out, history=history, provider=provider)
    assert provider.calls == 1 and not (out / 'review-result.json').exists()


def production_run(tmp_path, count=1):
    value = book('new', count=count)
    passage = value['passages'][0]
    plan = {'version': 1, 'mode': 'pilot', 'title': value['title'], 'minutes': value['minutes'],
            'passages': [{'id': p['id'], 'domain': p['domain'], 'topic': '가상 기록 제도',
                          'structure': '조건과 반례', 'sources': p['sources'],
                          'questions': [{k: q[k] for k in ('id', 'number', 'cognitive_task', 'difficulty')}
                                        for q in p['questions']]} for p in value['passages']]}
    run = tmp_path / 'production'
    production.prepare(save(tmp_path / 'plan.json', plan), run)
    value['passages'] = [passage]
    state = production.check(run, passage['id'], save(tmp_path / 'draft.json', value))
    return run, state


def test_production_and_explicit_attempt_supported_without_approval(tmp_path):
    run, state = production_run(tmp_path)
    previous = save(tmp_path / 'previous/book.json', book('old'))
    history = tmp_path / 'history.sqlite'
    novelty.remember(history, novelty.records([previous]))
    for source, out in [(run, tmp_path / 'root-review'),
                        (type(run)(state['candidate']).parent, tmp_path / 'attempt-review')]:
        provider = ReadingProvider()
        review.novelty_review(source, out, history=history, provider=provider)
        assert provider.calls == 1 and len(provider.payload['pairs']) == 9
    assert production.status(run)['sets'][0]['state'] == 'blind_required'


def test_incomplete_production_only_claims_selected_set_review(tmp_path):
    run, _ = production_run(tmp_path, count=2)
    previous = save(tmp_path / 'previous/book.json', book('old'))
    history = tmp_path / 'history.sqlite'
    novelty.remember(history, novelty.records([previous]))
    provider = ReadingProvider()
    with pytest.raises(RuntimeError, match='--passage-id'):
        review.novelty_review(run, tmp_path / 'unselected', history=history, provider=provider)
    assert provider.calls == 0
    result = review.novelty_review(run, tmp_path / 'selected', history=history,
                                  provider=provider, passage_id='new-p0')
    scope = result['reading_scope']
    assert scope['selected_questions'] == 3 and scope['selected_passages'] == 1
    assert scope['declared_production_passages'] == 2
    assert scope['production_completion_assessed'] is False and scope['all_book_pairs_reviewed'] is False
    assert production.status(run)['sets'][1]['state'] == 'draft_required'


def test_initial_current_pointer_capture_is_not_replaced_by_later_snapshot(tmp_path, monkeypatch):
    run, _ = production_run(tmp_path)
    previous = save(tmp_path / 'previous/book.json', book('old'))
    history = tmp_path / 'history.sqlite'
    novelty.remember(history, novelty.records([previous]))
    original = review.reading_novelty.maybe_records
    def change_after_read(*args, **kwargs):
        rows = original(*args, **kwargs)
        pointer = run / 'passages/new-p0/current.json'
        pointer.write_bytes(pointer.read_bytes() + b' ')
        return rows
    monkeypatch.setattr(review.reading_novelty, 'maybe_records', change_after_read)
    provider = ReadingProvider()
    with pytest.raises(RuntimeError, match='input_changed'):
        review.novelty_review(run, tmp_path / 'review', history=history, provider=provider)
    assert provider.calls == 0


@pytest.mark.parametrize('cap', ['pairs', 'bytes'])
def test_reading_bounded_review_never_silently_truncates(tmp_path, monkeypatch, cap):
    candidate, previous, history = make_pair(tmp_path)
    if cap == 'pairs':
        another = save(tmp_path / 'another/book.json', book('extra'))
        novelty.remember(history, novelty.records([another]))
        message = 'pair cap exceeded'
    else:
        monkeypatch.setattr(review, 'MAX_INPUT_BYTES', 100)
        message = 'byte cap exceeded'
    provider = ReadingProvider()
    with pytest.raises(RuntimeError, match=message):
        review.novelty_review(candidate, tmp_path / 'review', history=history, provider=provider)
    assert provider.calls == 0


def test_cli_passage_selection_reaches_index_check_and_review(tmp_path, monkeypatch, capsys):
    from haean import cli
    candidate = save(tmp_path / 'book.json', book('new', count=2))
    history = tmp_path / 'history.sqlite'
    monkeypatch.setattr(sys, 'argv', ['haean-tool', 'novelty-index', str(candidate),
                                    '--passage-id', 'new-p1', '--catalog', str(history)])
    cli.main()
    assert json.loads(capsys.readouterr().out)['indexed_inputs'] == 3
    assert {row['item']['id'] for row in novelty.history(history)} == {'new-q4', 'new-q5', 'new-q6'}
    check = tmp_path / 'check.json'
    monkeypatch.setattr(sys, 'argv', ['haean-tool', 'novelty-check', str(candidate),
                                    '--passage-id', 'new-p1', '--catalog', str(history), '--out', str(check)])
    cli.main()
    assert len(json.loads(capsys.readouterr().out)['items']) == 3
    received = {}
    def fake_review(run, out, **kwargs):
        received.update(kwargs)
        return {'synthetic': True}
    monkeypatch.setattr(review, 'novelty_review', fake_review)
    monkeypatch.setattr(sys, 'argv', ['haean-tool', 'novelty-review', str(candidate),
                                    '--passage-id', 'new-p1', '--out', str(tmp_path / 'review')])
    cli.main()
    assert received['passage_id'] == 'new-p1'
