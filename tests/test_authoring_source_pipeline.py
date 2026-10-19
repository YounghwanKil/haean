import hashlib
import json

import pytest

from haean.pipeline import run_pipeline, save
from test_core import reviews


def attached_context(tmp_path, brief):
    snapshot = tmp_path / 'fact.json'
    save(snapshot, {'facts': '합성 테스트의 자료 설명'})
    fact = {'id': 'attached-fact', 'facts': '합성 테스트의 자료 설명',
            'url': 'https://example.org/test-only', 'snapshot_path': str(snapshot),
            'snapshot_sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest()}
    packet = tmp_path / 'packet.json'
    save(packet, {'sources': [fact]})
    return {'brief': brief.model_dump(), 'references': [{'id': 'source-1', 'text': '별도 예시'}],
            'exam_assignment': [{'id': 'TEST-001', 'item_type': brief.item_type,
                'composition_resolution': {'topic_fact_input': {
                    'packet_path': str(packet),
                    'packet_sha256': hashlib.sha256(packet.read_bytes()).hexdigest(),
                    'sources': [fact]}}}]}, snapshot


def test_attached_fact_is_accepted_without_exposing_it_to_blind(tmp_path, draft, brief):
    context, _ = attached_context(tmp_path, brief)
    draft.items[0].source_ids = ['attached-fact']
    save(tmp_path / 'brief.json', brief.model_dump())
    save(tmp_path / 'context.json', context)

    class Provider:
        usage = []
        def call(self, stage, instructions, payload, schema):
            if stage == 'generate':
                assert payload['exam_assignment'] == context['exam_assignment']
                return draft
            if stage == 'blind':
                assert set(payload) == {'items'}
                assert 'source_ids' not in payload['items'][0]
                assert 'attached-fact' not in json.dumps(payload)
                return reviews(draft)[0]
            assert stage == 'editor'
            assert payload['exam_assignment'] == context['exam_assignment']
            assert payload['mechanical_errors'] == []
            return reviews(draft)[1]

    run_pipeline(tmp_path, Provider(), max_revisions=0)
    assert json.loads((tmp_path / 'status.json').read_text())['state'] == 'awaiting_human_review'


def test_source_changed_during_generation_stops_before_review(tmp_path, draft, brief):
    context, snapshot = attached_context(tmp_path, brief)
    save(tmp_path / 'brief.json', brief.model_dump())
    save(tmp_path / 'context.json', context)

    class Provider:
        usage = []
        calls = []
        def call(self, stage, *args):
            self.calls.append(stage)
            snapshot.write_text('changed')
            return draft

    provider = Provider()
    with pytest.raises(ValueError):
        run_pipeline(tmp_path, provider, max_revisions=0)
    assert provider.calls == ['generate']
    assert json.loads((tmp_path / 'status.json').read_text())['state'] == 'failed'
    assert not (tmp_path / 'candidate.json').exists()


def test_manual_check_uses_same_attachment_contract(tmp_path, draft, brief, monkeypatch):
    from haean.cli import main
    context, _ = attached_context(tmp_path, brief)
    draft.items[0].source_ids = ['attached-fact']
    save(tmp_path / 'context.json', context)
    source = tmp_path / 'draft-input.json'
    source.write_text(draft.model_dump_json())
    monkeypatch.setattr('sys.argv', ['haean-tool', 'check', str(tmp_path), str(source)])
    main()
    status = json.loads((tmp_path / 'status.json').read_text())
    assert status['errors'] == []
    assert status['state'] == 'awaiting_independent_review'


def test_invalid_attachment_in_later_bundle_blocks_build_before_output(tmp_path, monkeypatch):
    from haean.full_exam import build
    slots = [{'id': f'item-{n}', 'number': n, 'domain': str(n), 'difficulty': '중',
              'item_type': '조건 추론', 'topic': '합성 테스트'} for n in range(1, 41)]
    slots[-1]['composition_resolution'] = {'topic_fact_input': {
        'packet_path': str(tmp_path / 'missing.json'), 'packet_sha256': '0' * 64,
        'sources': [{'id': 'missing-fact', 'facts': '내용'}]}}
    plan = tmp_path / 'plan.json'
    save(plan, {'exam': 'leet', 'subject': '추리논증', 'slots': slots})
    out = tmp_path / 'production'
    def unexpected(*args, **kwargs):
        pytest.fail('유효하지 않은 자료로 모델을 시작하면 안 됨')
    monkeypatch.setattr('haean.full_exam.CodexProvider', unexpected)
    with pytest.raises(ValueError):
        build(plan, tmp_path / 'unused.sqlite', out)
    assert not out.exists()


def test_late_retrieval_collision_blocks_all_model_calls(tmp_path, brief, monkeypatch):
    from haean.full_exam import build
    context, _ = attached_context(tmp_path, brief)
    slots = [{'id': f'item-{n}', 'number': n, 'domain': str(n), 'difficulty': '중',
              'item_type': brief.item_type, 'topic': '합성 테스트'} for n in range(1, 41)]
    slots[-1]['composition_resolution'] = context['exam_assignment'][0]['composition_resolution']
    plan = tmp_path / 'plan.json'
    save(plan, {'exam': 'leet', 'subject': brief.subject, 'slots': slots})
    prepared = []
    def prepare(_corpus, _brief, directory):
        run = directory / str(len(prepared))
        run.mkdir(parents=True)
        save(run / 'context.json', {'references': [{'id': 'attached-fact', 'text': '다른 내용'}]})
        (run / 'request.md').write_text('합성 입력')
        prepared.append(run)
        return run
    def unexpected(*args, **kwargs):
        pytest.fail('후반 자료 충돌을 검증하기 전에 모델을 호출하면 안 됨')
    monkeypatch.setattr('haean.full_exam.Corpus', lambda *_: object())
    monkeypatch.setattr('haean.full_exam.prepare', prepare)
    monkeypatch.setattr('haean.full_exam.CodexProvider', unexpected)
    with pytest.raises(ValueError, match='conflicting'):
        build(plan, tmp_path / 'unused.sqlite', tmp_path / 'production', workers=1)
    assert len(prepared) == 40
