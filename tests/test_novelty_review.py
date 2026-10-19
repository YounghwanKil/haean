"""Synthetic input/transport checks, not an expert originality benchmark."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from haean import novelty
from haean import novelty_review as module


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_run(root, draft, brief, name='candidate', identity='NEW', context=None):
    run = root / name
    run.mkdir()
    data = deepcopy(draft.model_dump())
    data['items'][0]['id'] = identity
    save(run / 'candidate.json', data)
    save(run / 'brief.json', brief.model_dump())
    save(run / 'status.json', {'state': 'needs_human_review', 'revision': 0})
    if context is not None:
        save(run / 'context.json', context)
    return run


def setup_pair(tmp_path, draft, brief, *, context=None, dissimilar=False):
    run = make_run(tmp_path, draft, brief, context=context)
    old_run = make_run(tmp_path, draft, brief, name='previous', identity='OLD')
    if dissimilar:
        value = json.loads((old_run / 'candidate.json').read_text())
        item = value['items'][0]
        item.update(passage='구조가 다른 합성 문항', cognitive_task='다른 과제',
                    essential_conditions=['다른 조건'], explanation='별개 해설')
        item['options'] = [{'number': number, 'text': f'새 선지 {number}'} for number in range(1, 6)]
        save(old_run / 'candidate.json', value)
    history = tmp_path / 'history.sqlite'
    novelty.remember(history, novelty.records([old_run]))
    return run, old_run, history


def valid_result(payload):
    mapping = {'candidate': '합성 조건', 'previous': '합성 조건', 'assessment': '비교 대상'}
    pairs = []
    for pair in payload['pairs']:
        previous_wrong = sorted(set(range(1, 6)) - {pair['previous']['item']['answer']})
        candidate_wrong = sorted(set(range(1, 6)) - {pair['candidate']['item']['answer']})
        pairs.append({
            'pair_id': pair['pair_id'],
            'candidate_canonical_sha256': pair['candidate']['payload_canonical_sha256'],
            'previous_canonical_sha256': pair['previous']['payload_canonical_sha256'],
            'relation': 'uncertain', 'essential_conditions': [mapping], 'decisive_inference': mapping,
            'distractor_roles': [{'candidate_option': current, 'previous_options': [old],
                                  'candidate_role': '합성 오답', 'previous_role': '합성 오답',
                                  'assessment': '테스트 전용'} for current, old in zip(candidate_wrong, previous_wrong)],
            'candidate_evidence': [{'pointer': '/passage', 'quote': pair['candidate']['item']['passage']}],
            'previous_evidence': [{'pointer': '/passage', 'quote': pair['previous']['item']['passage']}],
            'remaining_uncertainty': ['fake provider; no semantic judgment'], 'recommendation': '실제 검토 필요'})
    return {'pairs': pairs, 'summary': '합성 전송 검사'}


class FakeProvider:
    def __init__(self, modify=None):
        self.calls = 0
        self.usage = []
        self.modify = modify
        self.payload = None

    def call(self, stage, instructions, payload, schema):
        self.calls += 1
        self.payload = deepcopy(payload)
        self.stage = stage
        self.instructions = instructions
        self.usage.append({'stage': stage, 'usage': {'input_tokens': 10, 'output_tokens': 10}})
        result = valid_result(payload)
        if self.modify:
            self.modify(result, payload)
        return schema.model_validate_json(json.dumps(result, ensure_ascii=False))


def test_flag_zero_top_neighbor_reaches_actual_call_and_does_not_write_sources(tmp_path, draft, brief):
    context = {'exam_assignment': [{'id': 'NEW', 'item_type': brief.item_type,
                                   'authoring_notes': '문항 명세', 'composition_resolution': 'PRIVATE_VERDICT'}],
               'feedback': 'PRIVATE_VERDICT', 'targeted_repair': 'PRIVATE_VERDICT',
               'resume_lineage': {'revision_feedback': 'PRIVATE_VERDICT'}}
    run, old, history = setup_pair(tmp_path, draft, brief, context=context, dissimilar=True)
    before = {path: sha(path) for folder in (run, old) for path in folder.iterdir()}
    before[history] = sha(history)
    out = tmp_path / 'review'
    provider = FakeProvider()
    result = module.novelty_review(run, out, history=history, provider=provider)
    assert provider.calls == 1 and provider.stage == 'editor'
    pair = provider.payload['pairs'][0]
    assert pair['previous']['item']['id'] == 'OLD'
    assert pair['retrieval']['review_candidate'] is False
    assert pair['selection_reasons'] == ['lexical_top_neighbor']
    assert pair['previous']['source_resolution']['status'] == 'verified_origin'
    assert 'PRIVATE_VERDICT' not in json.dumps(provider.payload)
    assert provider.payload['task_spec']['exam_assignment'][0]['authoring_notes'] == '문항 명세'
    assert (out / 'input-context.json').read_bytes() == (run / 'context.json').read_bytes()
    assert {path: sha(path) for path in before} == before
    manifest = json.loads((out / 'manifest.json').read_text())
    assert manifest['checks']['after_model'] == 'unchanged'
    assert manifest['before_hashes'][str(history)]['raw_sha256'] == before[history]
    assert manifest['input_bytes'] > 0 and manifest['input_tokens'] is None
    assert manifest['actual_model'] is None and not manifest['expert_review_performed']
    assert result['status'] == 'selected_pair_review_complete' and not result['approval_created']
    assert (out / 'model-output.raw.json').exists()


def test_based_on_all_versions_precede_search_and_do_not_choose_current(tmp_path, draft, brief):
    context = {'exam_assignment': [{'id': 'NEW', 'based_on_item_id': 'OLD'}]}
    run, old, history = setup_pair(tmp_path, draft, brief, context=context)
    first = novelty.records([old])[0]
    second = deepcopy(first)
    second['item']['passage'] += ' 다른 수정판이다.'
    second['sha256'] = novelty.digest(second['item'])
    novelty.remember(history, [second])
    novelty.remember(history, [first])  # current intentionally points to older version.
    provider = FakeProvider()
    module.novelty_review(run, tmp_path / 'review', history=history, provider=provider)
    pairs = provider.payload['pairs']
    assert len(pairs) == 2
    assert {pair['previous']['sha256'] for pair in pairs} == {first['sha256'], second['sha256']}
    assert all('based_on_all_stored_versions' in pair['selection_reasons'] for pair in pairs)
    assert all(pair['based_on_version_status']['stored_version_count'] == 2 for pair in pairs)
    assert all(not pair['based_on_version_status']['generation_time_version_bound'] for pair in pairs)
    assert {pair['previous']['source_resolution']['status'] for pair in pairs} == {'verified_origin', 'unresolved'}
    assert len({pair['pair_id'] for pair in pairs}) == 2


def test_based_on_missing_fails_without_model_and_preserves_manifest(tmp_path, draft, brief):
    context = {'exam_assignment': [{'id': 'NEW', 'based_on_item_id': 'MISSING'}]}
    run, old, history = setup_pair(tmp_path, draft, brief, context=context)
    provider = FakeProvider()
    out = tmp_path / 'review'
    with pytest.raises(RuntimeError, match='based_on item missing'):
        module.novelty_review(run, out, history=history, provider=provider)
    assert provider.calls == 0
    assert json.loads((out / 'manifest.json').read_text())['status'] == 'failed'


def test_same_id_versions_excluded_and_cross_subject_excluded(tmp_path, draft, brief):
    run, old, history = setup_pair(tmp_path, draft, brief)
    same = novelty.records([run])[0]
    other = deepcopy(novelty.records([old])[0])
    other['exam'], other['subject'] = 'psat7', '상황판단'
    other['item']['id'], other['item']['subject'] = 'OTHER', '상황판단'
    other['sha256'] = novelty.digest(other['item'])
    novelty.remember(history, [same, other])
    provider = FakeProvider()
    out = tmp_path / 'review'
    module.novelty_review(run, out, history=history, provider=provider)
    assert [pair['previous']['item']['id'] for pair in provider.payload['pairs']] == ['OLD']
    coverage = json.loads((out / 'selection-coverage.json').read_text())[0]
    assert coverage['same_id_revision_versions_excluded'] == 1
    assert coverage['other_subject_versions_excluded'] == 1


def test_mandatory_flags_above_pair_cap_fail_instead_of_truncating(tmp_path, draft, brief):
    run, old, history = setup_pair(tmp_path, draft, brief)
    rows = []
    for number in range(module.MAX_PAIRS):
        row = deepcopy(novelty.records([old])[0])
        row['item']['id'] = f'FLAG-{number}'
        row['sha256'] = novelty.digest(row['item'])
        rows.append(row)
    novelty.remember(history, rows)
    provider = FakeProvider()
    out = tmp_path / 'review'
    with pytest.raises(RuntimeError, match='pair cap exceeded'):
        module.novelty_review(run, out, history=history, provider=provider)
    assert provider.calls == 0
    manifest = json.loads((out / 'manifest.json').read_text())
    assert len(manifest['selection']) == module.MAX_PAIRS + 1


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'extra', 'hash', 'quote', 'pointer', 'roles'])
def test_result_binding_rejects_pair_hash_and_quote_faults(tmp_path, draft, brief, fault):
    run, old, history = setup_pair(tmp_path, draft, brief)
    def modify(result, payload):
        pair = result['pairs'][0]
        if fault == 'missing':
            result['pairs'] = []
        elif fault == 'duplicate':
            result['pairs'].append(deepcopy(pair))
        elif fault == 'extra':
            extra = deepcopy(pair)
            extra['pair_id'] = 'unrequested-pair'
            result['pairs'].append(extra)
        elif fault == 'hash':
            pair['previous_canonical_sha256'] = '0' * 64
        elif fault == 'quote':
            pair['candidate_evidence'][0]['quote'] = '원문에 없는 인용'
        elif fault == 'pointer':
            pair['previous_evidence'][0]['pointer'] = '/does-not-exist'
        else:
            pair['distractor_roles'][0]['candidate_option'] = 1
    provider = FakeProvider(modify)
    out = tmp_path / 'review'
    with pytest.raises(RuntimeError):
        module.novelty_review(run, out, history=history, provider=provider)
    assert provider.calls == 1
    assert (out / 'model-output.raw.json').exists()
    assert not (out / 'review-result.json').exists()
    assert json.loads((out / 'manifest.json').read_text())['status'] == 'failed'


@pytest.mark.parametrize('target', ['candidate', 'database', 'saved_input'])
def test_changes_during_model_are_rejected(tmp_path, draft, brief, target):
    run, old, history = setup_pair(tmp_path, draft, brief)
    out = tmp_path / 'review'
    def modify(result, payload):
        path = {'candidate': run / 'candidate.json', 'database': history,
                'saved_input': out / 'review-input.json'}[target]
        path.write_bytes(path.read_bytes() + b' ')
    provider = FakeProvider(modify)
    with pytest.raises(RuntimeError, match='input_changed'):
        module.novelty_review(run, out, history=history, provider=provider)
    assert json.loads((out / 'manifest.json').read_text())['status'] == 'failed'
    assert not (out / 'review-result.json').exists()


def test_catalog_payload_hash_corruption_fails_before_model(tmp_path, draft, brief):
    run, old, history = setup_pair(tmp_path, draft, brief)
    with sqlite3.connect(history) as db:
        db.execute("UPDATE versions SET sha='incorrect'")
    before = sha(history)
    provider = FakeProvider()
    with pytest.raises(RuntimeError, match='catalog payload hash mismatch'):
        module.novelty_review(run, tmp_path / 'review', history=history, provider=provider)
    assert provider.calls == 0 and sha(history) == before


def test_image_aliases_join_pair_side_and_version_without_changing_original_id(tmp_path, draft, brief, monkeypatch):
    from haean import figures, visual_review
    context = {'exam_assignment': [{'id': 'NEW', 'based_on_item_id': 'OLD'}]}
    figure = {'id': 'FIG', 'placement': 'passage', 'kind': 'argument', 'title': '',
              'x_label': '', 'y_label': '', 'categories': [], 'series': [],
              'nodes': [{'id': 'a', 'label': '가'}, {'id': 'b', 'label': '나'}],
              'edges': [{'sources': ['a'], 'target': 'b', 'relation': 'support'}], 'note': ''}
    data = draft.model_dump()
    data['items'][0]['figures'] = [figure]
    draft = module.Draft.model_validate(data)
    run, old, history = setup_pair(tmp_path, draft, brief, context=context)
    second = deepcopy(novelty.records([old])[0])
    second['item']['passage'] += ' 수정판'
    second['sha256'] = novelty.digest(second['item'])
    novelty.remember(history, [second])
    def render(item, directory):
        directory.mkdir(parents=True)
        path = directory / 'synthetic.png'
        path.write_bytes(b'synthetic renderer output, not a verified image')
        return {'FIG': path}
    monkeypatch.setattr(figures, 'render_item', render)
    provider = FakeProvider()
    module.novelty_review(run, tmp_path / 'review', history=history, provider=provider)
    payload = provider.payload
    paths, images = visual_review.review_images('editor', payload, tmp_path / 'renders')
    mapping = {entry['rendering_id']: entry for entry in payload['rendering_map']}
    assert len(paths) == 4 and len(mapping) == 4
    assert {image['item_id'] for image in images} == set(mapping)
    assert len({entry['payload_canonical_sha256'] for entry in mapping.values() if entry['side'] == 'previous'}) == 2
    assert {pair['previous']['item']['id'] for pair in payload['pairs']} == {'OLD'}
    assert all(set(item) == {'id', 'figures'} for item in payload['draft']['items'])


def test_model_failure_preserves_evidence_and_no_retry(tmp_path, draft, brief):
    run, old, history = setup_pair(tmp_path, draft, brief)
    def fail(result, payload):
        raise RuntimeError('synthetic CLI failure')
    provider = FakeProvider(fail)
    out = tmp_path / 'review'
    with pytest.raises(RuntimeError, match='synthetic CLI failure'):
        module.novelty_review(run, out, history=history, provider=provider)
    assert provider.calls == 1
    manifest = json.loads((out / 'manifest.json').read_text())
    assert manifest['status'] == 'failed' and manifest['completed_at']
    assert (out / 'usage.json').exists() and (out / 'pairs.json').exists()


def test_existing_output_and_source_child_rejected_before_any_reads(tmp_path, draft, brief):
    out = tmp_path / 'exists'
    out.mkdir()
    save(out / 'keep.json', {'original': True})
    with pytest.raises(ValueError, match='new path'):
        module.novelty_review(tmp_path / 'absent', out, history=tmp_path / 'missing')
    assert json.loads((out / 'keep.json').read_text()) == {'original': True}
    run = make_run(tmp_path, draft, brief)
    with pytest.raises(ValueError, match='outside'):
        module.novelty_review(run, run / 'review', history=tmp_path / 'missing')
    assert not (run / 'review').exists()


def test_real_provider_configuration_is_one_astra_call(tmp_path, draft, brief, monkeypatch):
    run, old, history = setup_pair(tmp_path, draft, brief)
    captured = {}
    provider = FakeProvider()
    def construct(model, **kwargs):
        captured.update(model=model, **kwargs)
        return provider
    monkeypatch.setattr(module, 'CodexProvider', construct)
    out = tmp_path / 'review'
    module.novelty_review(run, out, history=history)
    assert captured == {'model': 'gpt-6-astra', 'max_calls': 1, 'trace_dir': out / 'codex-traces'}
    assert provider.calls == 1


def test_context_brief_mismatch_rejected(tmp_path, draft, brief):
    context = {'brief': {**brief.model_dump(), 'topic': '다른 명세'}}
    run, old, history = setup_pair(tmp_path, draft, brief, context=context)
    provider = FakeProvider()
    with pytest.raises(RuntimeError, match='context.brief differs'):
        module.novelty_review(run, tmp_path / 'review', history=history, provider=provider)
    assert provider.calls == 0
