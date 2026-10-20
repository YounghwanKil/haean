"""Transport and evidence boundaries; not tests of expert judgment."""
import json
from copy import deepcopy

import pytest

from haean.shortcut_review import shortcut_review


def setup_run(tmp_path, draft, brief):
    run = tmp_path / 'source'
    run.mkdir()
    (run / 'candidate.json').write_text(draft.model_dump_json())
    (run / 'brief.json').write_text(brief.model_dump_json())
    (run / 'status.json').write_text('{"state":"needs_revision"}')
    return run


class Provider:
    calls = 0
    usage = []

    def __init__(self, mutate=None):
        self.inputs = []
        self.mutate = mutate

    def call(self, stage, instructions, payload, schema):
        self.calls += 1
        self.inputs.append(deepcopy(payload))
        item = (payload['items'] if stage == 'shortcut-solve' else payload['draft']['items'])[0]
        common = {'item_id': item['id'], 'evidence': [{'pointer': '/passage', 'quote': item['passage']}], 'uncertainty': []}
        if stage == 'shortcut-solve':
            result = {'routes': [{**common, 'answer': 1, 'steps': [{'reasoning': 'synthetic', 'remaining_options': [1]}], 'skipped_reasoning': []}]}
        else:
            result = {'findings': [{**common, 'route_valid': 'yes', 'classification': 'legitimate_efficiency',
                'decisive_check': 'synthetic only', 'condition_contribution': 'synthetic only', 'recommendation': 'human review'}]}
        if self.mutate:
            self.mutate(stage, result)
        return schema.model_validate(result)


def test_two_sessions_no_answer_leak_and_source_unchanged(tmp_path, draft, brief):
    run = setup_run(tmp_path, draft, brief)
    before = {p: p.read_bytes() for p in run.iterdir()}
    fake = Provider()
    result = shortcut_review(run, tmp_path / 'output', provider=fake)
    public = fake.inputs[0]['items'][0]
    for key in ('answer', 'explanation', 'cognitive_task', 'essential_conditions', 'judgments', 'difficulty_basis'):
        assert key not in public
    assert 'brief' not in fake.inputs[0]
    assert fake.inputs[1]['draft']['items'][0]['answer'] == draft.items[0].answer
    assert fake.calls == 2 and result['complete']
    assert not result['approval'] and not result['expert_verified']
    assert result['actual_model'] is None
    assert before == {p: p.read_bytes() for p in run.iterdir()}
    assert json.loads((tmp_path / 'output/routes.json').read_text()) == fake.inputs[1]['supplied_routes']


@pytest.mark.parametrize('fault', ['wrong_id', 'duplicate_id', 'fake_quote', 'answer_leak_pointer', 'negative_pointer', 'bad_options', 'return_eliminated', 'wrong_final'])
def test_solver_bad_evidence_stops_before_audit(tmp_path, draft, brief, fault):
    run = setup_run(tmp_path, draft, brief)
    def mutate(stage, result):
        row = result['routes'][0]
        if fault == 'wrong_id': row['item_id'] = 'missing'
        if fault == 'duplicate_id': result['routes'].append(deepcopy(row))
        if fault == 'fake_quote': row['evidence'][0]['quote'] = 'NOT IN SOURCE'
        if fault == 'answer_leak_pointer': row['evidence'][0] = {'pointer': '/explanation', 'quote': 'not public'}
        if fault == 'negative_pointer': row['evidence'][0] = {'pointer': '/options/-1/text', 'quote': 'x'}
        if fault == 'bad_options': row['steps'][0]['remaining_options'] = [1, 6]
        if fault == 'return_eliminated': row['steps'].append({'reasoning': 'x', 'remaining_options': [1, 2]})
        if fault == 'wrong_final': row['answer'] = 2
    fake = Provider(mutate)
    with pytest.raises(ValueError): shortcut_review(run, tmp_path / 'output', provider=fake)
    assert fake.calls == 1
    result = json.loads((tmp_path / 'output/result.json').read_text())
    assert not result['complete'] and 'error' in result
    assert (tmp_path / 'output/routes.json').is_file()


def test_input_change_during_call_preserves_failure(tmp_path, draft, brief):
    run = setup_run(tmp_path, draft, brief)
    def mutate(stage, result):
        (run / 'candidate.json').write_text('{}')
    fake = Provider(mutate)
    with pytest.raises(ValueError, match='input_changed'):
        shortcut_review(run, tmp_path / 'output', provider=fake)
    assert fake.calls == 1
    assert not json.loads((tmp_path / 'output/result.json').read_text())['complete']


def test_auditor_cannot_certify_invalid_route(tmp_path, draft, brief):
    run = setup_run(tmp_path, draft, brief)
    def mutate(stage, result):
        if stage == 'shortcut-audit': result['findings'][0]['route_valid'] = 'no'
    with pytest.raises(ValueError, match='미확인'):
        shortcut_review(run, tmp_path / 'output', provider=Provider(mutate))


def test_assignment_mismatch_and_output_overlap_preflight(tmp_path, draft, brief):
    run = setup_run(tmp_path, draft, brief)
    fake = Provider()
    with pytest.raises(ValueError): shortcut_review(run, run/'output', provider=fake)
    (run / 'context.json').write_text('{"exam_assignment":[]}')
    with pytest.raises(ValueError, match='배정'):
        shortcut_review(run, tmp_path/'output', provider=fake)
    assert fake.calls == 0 and not (tmp_path/'output').exists()
