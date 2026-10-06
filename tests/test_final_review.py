import hashlib
import json
import pytest
from haean.final_review import human_checkpoint, prepare_final, final_review
from haean.models import EditorialReview
from haean.pipeline import save


def setup_run(path, draft, brief):
    save(path/'candidate.json',draft.model_dump());save(path/'brief.json',brief.model_dump())
    save(path/'status.json',{'state':'awaiting_human_review','human_approved':False})
    return hashlib.sha256((path/'candidate.json').read_bytes()).hexdigest()


def test_no_final_review_without_actual_checkpoint(tmp_path,draft,brief):
    sha=setup_run(tmp_path,draft,brief)
    with pytest.raises(FileNotFoundError):prepare_final(tmp_path)
    with pytest.raises(ValueError):human_checkpoint(tmp_path,'tester','old','synthetic fixture')
    human_checkpoint(tmp_path,'tester',sha,'synthetic fixture, no actual expert approval')
    packet=prepare_final(tmp_path)
    assert packet['candidate_sha256']==sha
    draft.items[0].answer=2;save(tmp_path/'candidate.json',draft.model_dump())
    with pytest.raises(ValueError,match='바뀌'):prepare_final(tmp_path)


def test_post_human_review_never_rewrites_or_approves(tmp_path,draft,brief):
    sha=setup_run(tmp_path,draft,brief)
    human_checkpoint(tmp_path,'tester',sha,'synthetic fixture')
    before=(tmp_path/'candidate.json').read_bytes()
    class Provider:
        usage=[]
        def __init__(self):self.calls=[]
        def call(self,stage,*args):
            self.calls.append(stage);return EditorialReview(issues=[],summary='synthetic result')
    p=Provider();final_review(tmp_path,p)
    assert p.calls==['final-formal','final-quality']
    assert (tmp_path/'candidate.json').read_bytes()==before
    assert json.loads((tmp_path/'status.json').read_text())['human_approved'] is False
