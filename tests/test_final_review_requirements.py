"""Post-human checks retain per-item requirements and reject stale requests."""
import copy
import hashlib
import json

import pytest

from haean.final_review import final_review, human_checkpoint, prepare_final
from haean.models import EditorialReview
from haean.pipeline import save


def read(path):
    return json.loads(path.read_text())


@pytest.fixture
def mixed_final_run(tmp_path, draft, brief):
    run = tmp_path / 'final-run'
    run.mkdir()
    first = draft.items[0].model_copy(deep=True)
    first.difficulty = '상'
    first.shared_passage_id = 'SYNTHETIC-SHARED'
    second = first.model_copy(deep=True)
    second.id = 'TEST-002'
    second.item_type = '논증 평가'
    second.difficulty = '하'
    draft = draft.model_copy(update={'items': [first, second]}, deep=True)
    brief = brief.model_copy(update={'count': 2, 'shared_passage': True, 'difficulty': '중'})
    assignment = [{'id': item.id, 'item_type': item.item_type, 'difficulty': item.difficulty,
                   'topic': item.topic, 'shared_passage_id': item.shared_passage_id} for item in draft.items]
    save(run / 'candidate.json', draft.model_dump())
    save(run / 'brief.json', brief.model_dump())
    save(run / 'context.json', {'brief': brief.model_dump(), 'exam_assignment': assignment})
    sha = hashlib.sha256((run / 'candidate.json').read_bytes()).hexdigest()
    save(run / 'status.json', {'state': 'awaiting_human_review', 'human_approved': False,
                              'candidate_sha256': sha, 'errors': [], 'revision': 1})
    human_checkpoint(run, 'synthetic reviewer', sha, '합성 fixture. 실제 전문가 확인을 뜻하지 않음')
    return run


class FinalProvider:
    usage = []

    def __init__(self, mutation=None):
        self.calls = []
        self.mutation = mutation

    def call(self, stage, instructions, payload, schema):
        assert schema is EditorialReview
        self.calls.append((stage, copy.deepcopy(payload)))
        if self.mutation:
            self.mutation(stage)
        return EditorialReview(issues=[], summary='합성 검토')


def test_final_both_stages_receive_original_mixed_targets_without_rewriting(mixed_final_run):
    before = (mixed_final_run / 'candidate.json').read_bytes()
    checkpoint = (mixed_final_run / 'human-checkpoint.json').read_bytes()
    provider = FinalProvider()
    result = final_review(mixed_final_run, provider)
    assert [stage for stage, _ in provider.calls] == ['final-formal', 'final-quality']
    formal, quality = [payload for _, payload in provider.calls]
    assert formal == quality
    requirements = {row['id']: row for row in formal['item_requirements']}
    assert (requirements['TEST-001']['item_type'], requirements['TEST-001']['difficulty']) == ('조건 추론', '상')
    assert (requirements['TEST-002']['item_type'], requirements['TEST-002']['difficulty']) == ('논증 평가', '하')
    assert formal['brief']['difficulty'] == '중'
    assert formal['requirements_source'] == 'context.exam_assignment'
    assert formal['requirements_source_sha256']['context.json'] == hashlib.sha256((mixed_final_run / 'context.json').read_bytes()).hexdigest()
    assert (mixed_final_run / 'candidate.json').read_bytes() == before
    assert (mixed_final_run / 'human-checkpoint.json').read_bytes() == checkpoint
    assert result['human_approved'] is False
    status = read(mixed_final_run / 'status.json')
    assert status['state'] == 'awaiting_human_final_decision' and status['human_approved'] is False


@pytest.mark.parametrize('source', ['brief.json', 'context.json'])
@pytest.mark.parametrize('stage', ['final-formal', 'final-quality'])
def test_requirement_mutation_between_or_during_stages_cannot_be_applied(mixed_final_run, source, stage):
    path = mixed_final_run / source
    original = path.read_bytes()
    status_before = (mixed_final_run / 'status.json').read_bytes()
    candidate_before = (mixed_final_run / 'candidate.json').read_bytes()

    def mutate(current_stage):
        if current_stage == stage:
            path.write_bytes(original + b'\n')

    provider = FinalProvider(mutate)
    with pytest.raises(ValueError, match='명세가 바뀌'):
        final_review(mixed_final_run, provider)
    expected = ['final-formal'] if stage == 'final-formal' else ['final-formal', 'final-quality']
    assert [name for name, _ in provider.calls] == expected
    assert not (mixed_final_run / 'final-review.json').exists()
    assert (mixed_final_run / 'status.json').read_bytes() == status_before
    assert (mixed_final_run / 'candidate.json').read_bytes() == candidate_before
    assert path.read_bytes() == original + b'\n'


def test_final_prepare_rejects_divergent_brief_and_context_without_model(mixed_final_run):
    brief = read(mixed_final_run / 'brief.json')
    brief['topic'] = '다른 요청으로 바뀜'
    save(mixed_final_run / 'brief.json', brief)
    provider = FinalProvider()
    with pytest.raises(ValueError, match='context.brief'):
        final_review(mixed_final_run, provider)
    assert provider.calls == []
    assert not (mixed_final_run / 'final-input.json').exists()
    assert not (mixed_final_run / 'final-review.json').exists()


def test_final_prepare_refuses_explicit_empty_assignment_instead_of_common_brief(mixed_final_run):
    context = read(mixed_final_run / 'context.json')
    context['exam_assignment'] = []
    save(mixed_final_run / 'context.json', context)
    with pytest.raises(ValueError, match='배정'):
        prepare_final(mixed_final_run)
    assert not (mixed_final_run / 'final-input.json').exists()
