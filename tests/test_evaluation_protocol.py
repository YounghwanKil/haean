"""Protocol wiring at suite, frozen-comparison, and CLI boundaries."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from haean import evaluation
from haean.evaluation_input import EVALUATION_INPUT_CONTRACT_VERSION
from haean.pipeline import save


def read(path):
    return json.loads(path.read_text())


def evaluation_result(draft):
    return evaluation.Evaluation.model_validate({
        'items': [{'item_id': item.id,
                   'dimensions': [{'name': dimension, 'score': 3, 'evidence': '합성 문항 위치 근거'}
                                  for dimension in sorted(evaluation.DIMENSIONS)],
                   'fatal_errors': [], 'missing_evidence': ['실제 전문가 검토 없음'],
                   'expert_verified': False} for item in draft.items],
        'summary': '합성 평가 응답',
    })


def test_evaluate_suite_uses_and_saves_per_item_contract(tmp_path, draft, brief, monkeypatch):
    common = brief.model_copy(update={'count': 2, 'shared_passage': True, 'difficulty': '중'})
    first = draft.items[0].model_copy(deep=True)
    first.difficulty = '상'
    first.shared_passage_id = 'SYNTHETIC-PAIR'
    second = first.model_copy(deep=True)
    second.id = 'TEST-002'
    second.item_type, second.difficulty = '논증 평가', '하'
    candidate = draft.model_copy(update={'items': [first, second]}, deep=True)
    assignment = [{'id': item.id, 'item_type': item.item_type, 'difficulty': item.difficulty,
                   'topic': item.topic, 'shared_passage_id': item.shared_passage_id}
                  for item in candidate.items]
    suite = tmp_path / 'suite.json'
    save(suite, {'version': 'synthetic-suite', 'split': 'pilot', 'cases': [
        {'id': 'mixed-pair', 'group': 'synthetic-group', 'brief': common.model_dump()}]})
    corpus = object()
    calls, providers = [], []

    def prepare(received_corpus, request, root):
        assert received_corpus is corpus and request == common
        run = root / 'synthetic-run'
        run.mkdir(parents=True)
        save(run / 'brief.json', common.model_dump())
        save(run / 'context.json', {'brief': common.model_dump(), 'exam_assignment': assignment})
        calls.append('prepare')
        return run

    class Provider:
        def __init__(self, model, *, max_calls, trace_dir):
            assert model == 'synthetic-evaluator' and max_calls == 14
            self.trace_dir, self.usage, self.payload = trace_dir, [], None
            providers.append(self)

        def call(self, stage, instructions, payload, schema):
            assert stage == 'evaluate' and schema is evaluation.Evaluation
            calls.append(stage)
            self.payload = copy.deepcopy(payload)
            return evaluation_result(candidate)

    review = {'revision': 1, 'errors': [], 'blind': {'solutions': [
        {'item_id': item.id, 'answer': item.answer, 'uniquely_answerable': True,
         'option_reasons': ['합성 선지 근거'] * 5, 'missing_conditions': []} for item in candidate.items],
        'issues': []}, 'editorial': {'issues': [], 'summary': '현 버전에 대한 합성 검토'}}

    def pipeline(run, provider, max_revisions):
        assert max_revisions == 2 and provider is providers[0]
        calls.append('pipeline')
        save(run / 'candidate.json', candidate.model_dump())
        save(run / 'status.json', {'revision': 1, 'state': 'awaiting_human_review', 'errors': []})
        save(run / 'review-r1.json', review)
        return candidate

    monkeypatch.setattr(evaluation, 'prepare', prepare)
    monkeypatch.setattr(evaluation, 'run_pipeline', pipeline)
    monkeypatch.setattr(evaluation, 'CodexProvider', Provider)
    monkeypatch.setattr(evaluation.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout='synthetic-codex\n'))
    result = evaluation.evaluate_suite(corpus, suite, tmp_path / 'output', max_revisions=2,
                                       model='synthetic-evaluator')
    assert calls == ['prepare', 'pipeline', 'evaluate']
    assert result['evaluation_protocol'] == 'haean-evaluation-v3'
    assert result['complete'] and result['results'][0]['quality'] == 3
    run = Path(result['results'][0]['run'])
    payload = providers[0].payload
    assert payload['input_contract_version'] == EVALUATION_INPUT_CONTRACT_VERSION
    assert payload['requirements_source'] == 'context.exam_assignment'
    requirements = {row['id']: row for row in payload['item_requirements']}
    assert (requirements['TEST-001']['item_type'], requirements['TEST-001']['difficulty']) == ('조건 추론', '상')
    assert (requirements['TEST-002']['item_type'], requirements['TEST-002']['difficulty']) == ('논증 평가', '하')
    assert payload['brief']['difficulty'] == '중' and payload['brief']['item_type'] == '조건 추론'
    assert payload['draft'] == candidate.model_dump() and payload['review'] == review
    assert read(run / 'evaluation-input.json') == payload
    assert read(run / 'evaluation.json') == evaluation_result(candidate).model_dump()
    assert read(run / 'context.json')['exam_assignment'] == assignment
    assert read(run / 'candidate.json') == candidate.model_dump()
    assert read(tmp_path / 'output/results.json') == result


def legacy_result():
    return {'suite': 'synthetic-suite', 'split': 'pilot', 'model': 'synthetic-model', 'repeats': 1,
            'max_revisions': 1, 'mode': 'codex-prompt-pipeline', 'humanizer': 'not_applied',
            'frozen': {'rubric': 'same'}, 'complete': True,
            'results': [{'case_id': 'shared-case', 'repeat': 0, 'exam': 'psat7', 'subject': '언어논리',
                         'quality': 3, 'eligible': True, 'fatal_count': 0}]}


@pytest.mark.parametrize('old_protocol', [None, 'haean-evaluation-v2'])
def test_compare_refuses_legacy_or_v2_against_v3_even_with_same_scores_and_hashes(old_protocol):
    baseline = legacy_result()
    if old_protocol is not None:
        baseline['evaluation_protocol'] = old_protocol
    candidate = copy.deepcopy(baseline)
    candidate['evaluation_protocol'] = 'haean-evaluation-v3'
    before = copy.deepcopy((baseline, candidate))
    with pytest.raises(ValueError, match='evaluation_protocol'):
        evaluation.compare(baseline, candidate)
    assert (baseline, candidate) == before


def test_compare_keeps_legacy_to_legacy_without_silently_upgrading_metadata():
    baseline = legacy_result()
    candidate = copy.deepcopy(baseline)
    candidate['results'][0]['quality'] = 3.5
    before = copy.deepcopy((baseline, candidate))
    result = evaluation.compare(baseline, candidate)
    assert result['decision'] == 'candidate_signal'
    assert result['auto_promoted'] is False and result['expert_verified'] is False
    assert (baseline, candidate) == before
    assert 'evaluation_protocol' not in baseline and 'evaluation_protocol' not in candidate


def test_frozen_fingerprint_covers_input_helper_and_saved_run_evaluator(tmp_path, monkeypatch):
    # Use real fingerprinting over a tiny synthetic repository, without editing production code.
    root = tmp_path / 'frozen-root'
    dependencies = ('src/haean/evaluation_input.py', 'src/haean/evaluation_run.py',
                    'src/haean/execution_provenance.py', 'src/haean/composition_adapter.py',
                    'src/haean/composition/service.py')
    paths = ('evals/protocol.md', 'evals/rubric.md', *dependencies)
    for relative in paths:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic frozen contract: ' + relative)
    suite = root / 'suite.json'
    save(suite, {'version': 'synthetic'})
    monkeypatch.setattr(evaluation, 'ROOT', root)
    initial = evaluation.frozen_fingerprint(suite)
    for relative in paths:
        path = root / relative
        assert initial[str(path.resolve())] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert str(Path(evaluation.__file__).resolve()) in initial
    assert str(suite.resolve()) in initial
    for relative in dependencies:
        path = root / relative
        original = path.read_bytes()
        path.write_bytes(original + b'\nchanged')
        changed = evaluation.frozen_fingerprint(suite)
        assert {key for key in initial if initial[key] != changed[key]} == {str(path.resolve())}
        path.write_bytes(original)


@pytest.mark.parametrize('revision,model', [(None, None), (0, 'synthetic-evaluation-model')])
def test_evaluate_run_cli_dispatches_current_or_archived_revision(tmp_path, monkeypatch, capsys, revision, model):
    from haean.cli import main
    run, out = tmp_path / 'saved run', tmp_path / 'new results'
    received = []

    def evaluate_run(run_arg, out_arg, *, revision, model):
        received.append((run_arg, out_arg, revision, model))
        return {'synthetic': True, 'selected_revision': revision, 'requested_model': model}

    monkeypatch.setattr('haean.evaluation_run.evaluate_run', evaluate_run)
    monkeypatch.setattr('haean.cli.Corpus', lambda *a, **kw: pytest.fail('saved evaluation must not initialize a corpus'))
    argv = ['haean-tool', 'evaluate-run', str(run), '--out', str(out)]
    if revision is not None:
        argv += ['--revision', str(revision)]
    if model is not None:
        argv += ['--model', model]
    monkeypatch.setattr('sys.argv', argv)
    main()
    expected_model = model or 'gpt-6-astra'
    assert received == [(run, out, revision, expected_model)]
    assert json.loads(capsys.readouterr().out) == {
        'synthetic': True, 'selected_revision': revision, 'requested_model': expected_model}
    assert not run.exists() and not out.exists()
