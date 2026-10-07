import json
import pytest
from haean.exam_resume import select_jobs, seed_from
from haean.pipeline import run_pipeline, save
from test_core import reviews


def test_replacements_cannot_silently_drop_half_a_bundle(tmp_path):
    save(tmp_path/'production.json', {'jobs':[{'ids':['a','b'],'slots':[1,2]}, {'ids':['c'],'slots':[3]}]})
    replacement = tmp_path/'recovery.json'
    save(replacement, {'jobs':[{'ids':['a'],'slots':[1]}]})
    with pytest.raises(ValueError, match='전체'):
        select_jobs(tmp_path, [replacement])
    save(replacement, {'jobs':[{'ids':['a'],'slots':[1]}, {'ids':['b'],'slots':[2]}]})
    assert [j['ids'] for j in select_jobs(tmp_path,[replacement])] == [['a'],['b'],['c']]
    save(replacement, {'jobs':[{'ids':['a','a'],'slots':[1,1]}]})
    with pytest.raises(ValueError, match='중복'):
        select_jobs(tmp_path, [replacement])


def test_seed_selects_latest_saved_draft_not_stale_review(tmp_path):
    save(tmp_path/'draft-r0.json', {'old':True})
    save(tmp_path/'review-r0.json', {'errors':['old error']})
    save(tmp_path/'draft-r1.json', {'new':True})
    seed, review, path = seed_from(tmp_path)
    assert seed == {'new':True} and review is None
    assert path.name == 'draft-r1.json'


def test_interrupted_first_revision_keeps_inherited_feedback(tmp_path):
    save(tmp_path/'inherited-draft.json', {'saved':True})
    save(tmp_path/'inherited-review.json', {'errors':['fix']})
    seed, review, path = seed_from(tmp_path)
    assert seed['saved'] and review['errors'] == ['fix']


def test_seed_is_revised_then_blind_reviewed_without_generation(tmp_path, draft, brief):
    save(tmp_path/'brief.json', brief.model_dump())
    save(tmp_path/'context.json', {'references':[{'id':'source-1','text':'다른 예시'}]})
    class Provider:
        usage=[]
        def __init__(self): self.calls=[]
        def call(self, stage, instructions, payload, schema):
            self.calls.append(stage)
            if stage == 'revise':
                assert payload['review']['errors'] == ['기존 지적']
                return draft
            if stage == 'blind':
                assert 'answer' not in payload['items'][0]
                assert 'review' not in payload and 'context' not in payload
                return reviews(draft)[0]
            if stage == 'editor': return reviews(draft)[1]
            raise AssertionError('완성 초안을 신규 생성하면 안 됨')
    provider = Provider()
    run_pipeline(tmp_path, provider, initial_draft=draft.model_dump(), initial_review={'errors':['기존 지적']})
    assert provider.calls == ['revise','blind','editor']
    state=json.loads((tmp_path/'status.json').read_text())
    assert state['state']=='awaiting_human_review' and not state['human_approved']
    assert (tmp_path/'inherited-review.json').exists()


def test_fine_difficulty_does_not_break_resume_schema():
    from haean.full_exam import brief_difficulty
    assert brief_difficulty([{'difficulty':'중하'}]) == '중'
    assert brief_difficulty([{'difficulty':'상'}, {'difficulty':'상'}]) == '상'
    assert brief_difficulty([{'difficulty':'하'}, {'difficulty':'상'}]) == '중'
