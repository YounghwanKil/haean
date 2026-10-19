import hashlib
import json
import pytest
from haean.final_review import human_checkpoint, prepare_final, final_review
from haean.models import EditorialReview
from haean.pipeline import feedback, save


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
    metadata = {'revision': 2, 'errors': [], 'parent_run': 'synthetic-parent',
                'evidence': {'blind': 'synthetic-blind-receipt', 'editorial': 'synthetic-editor-receipt'}}
    save(tmp_path/'status.json', {'state': 'awaiting_human_review', 'candidate_sha256': sha, **metadata})
    human_checkpoint(tmp_path,'tester',sha,'synthetic fixture')
    checkpoint_status = json.loads((tmp_path/'status.json').read_text())
    assert checkpoint_status['state'] == 'awaiting_final_formal_review'
    assert all(checkpoint_status[key] == value for key, value in metadata.items())
    before=(tmp_path/'candidate.json').read_bytes()
    class Provider:
        usage=[]
        def __init__(self):self.calls=[]
        def call(self,stage,*args):
            self.calls.append(stage);return EditorialReview(issues=[],summary='synthetic result')
    p=Provider();final_review(tmp_path,p)
    assert p.calls==['final-formal','final-quality']
    assert (tmp_path/'candidate.json').read_bytes()==before
    status = json.loads((tmp_path/'status.json').read_text())
    assert status['human_approved'] is False and status['human_reviewed'] is True
    assert status['state'] == 'awaiting_human_final_decision'
    assert all(status[key] == value for key, value in metadata.items())


@pytest.mark.parametrize('severity', ['A', 'B'])
def test_checkpoint_keeps_unresolved_feedback_blocking_final_prepare(tmp_path, draft, brief, severity):
    run = tmp_path/'run'; run.mkdir()
    sha = setup_run(run, draft, brief)
    metadata = {'revision': 2, 'parent_run': 'synthetic-parent',
                'evidence': {'blind': 'synthetic-receipt'}, 'errors': []}
    save(run/'status.json', {'state': 'awaiting_human_review', 'candidate_sha256': sha, **metadata})
    feedback(run, draft.items[0].id, '합성 미해결 의견', 'synthetic tester', severity)
    record = human_checkpoint(run, 'synthetic tester', sha, '합성 체크포인트 기록')

    status = json.loads((run/'status.json').read_text())
    assert status['state'] == 'needs_revision'
    assert all(status[key] == value for key, value in metadata.items())
    assert status['human_approved'] is False and status['human_reviewed'] is True
    assert record['decision'] == 'reviewed_not_delivery_approved'
    assert json.loads((run/'human-history/000.json').read_text()) == record
    with pytest.raises(ValueError, match='미해결'):
        prepare_final(run)
    assert not (run/'final-input.json').exists()


@pytest.mark.parametrize('state', ['prepared', 'awaiting_independent_review', 'failed', 'unknown'])
def test_checkpoint_does_not_complete_unfinished_review(tmp_path, draft, brief, state):
    sha = setup_run(tmp_path, draft, brief)
    save(tmp_path/'status.json', {'state': state, 'candidate_sha256': sha, 'pending_review': 'editor'})
    human_checkpoint(tmp_path, 'synthetic tester', sha, '합성 체크포인트 기록')
    status = json.loads((tmp_path/'status.json').read_text())
    assert status['state'] == state and status['pending_review'] == 'editor'
    with pytest.raises(ValueError, match='완료되지'):
        prepare_final(tmp_path)


def test_checkpoint_does_not_clear_remaining_errors(tmp_path, draft, brief):
    sha = setup_run(tmp_path, draft, brief)
    errors = ['합성 미해결 검토 오류']
    save(tmp_path/'status.json', {'state': 'awaiting_human_review', 'errors': errors})
    human_checkpoint(tmp_path, 'synthetic tester', sha, '합성 체크포인트 기록')
    assert json.loads((tmp_path/'status.json').read_text())['errors'] == errors
    with pytest.raises(ValueError, match='미해결'):
        prepare_final(tmp_path)


@pytest.mark.parametrize('status', [None, [], {}, {'state': ''}, {'state': None},
                                    {'state': 'awaiting_human_review', 'candidate_sha256': 'stale'}])
def test_checkpoint_rejects_incomplete_or_stale_status_without_writes(tmp_path, draft, brief, status):
    sha = setup_run(tmp_path, draft, brief)
    save(tmp_path/'status.json', status)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError, match='상태'):
        human_checkpoint(tmp_path, 'synthetic tester', sha, '합성 체크포인트 기록')
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_checkpoint_requires_existing_status(tmp_path, draft, brief):
    sha = setup_run(tmp_path, draft, brief)
    (tmp_path/'status.json').unlink()
    with pytest.raises(FileNotFoundError):
        human_checkpoint(tmp_path, 'synthetic tester', sha, '합성 체크포인트 기록')
    assert not (tmp_path/'human-checkpoint.json').exists()
    assert not (tmp_path/'human-history').exists()


def test_final_prepare_rejects_status_for_another_candidate(tmp_path, draft, brief):
    sha = setup_run(tmp_path, draft, brief)
    human_checkpoint(tmp_path, 'synthetic tester', sha, '합성 체크포인트 기록')
    status = json.loads((tmp_path/'status.json').read_text())
    save(tmp_path/'status.json', {**status, 'candidate_sha256': 'stale'})
    with pytest.raises(ValueError, match='상태의 문항 해시'):
        prepare_final(tmp_path)


def test_final_review_does_not_overwrite_new_revision_request(tmp_path, draft, brief):
    sha = setup_run(tmp_path, draft, brief)
    human_checkpoint(tmp_path, 'synthetic tester', sha, '합성 체크포인트 기록')

    class Provider:
        usage = []

        def call(self, stage, *args):
            status = json.loads((tmp_path/'status.json').read_text())
            save(tmp_path/'status.json', {**status, 'state': 'needs_revision'})
            return EditorialReview(issues=[], summary='synthetic result')

    with pytest.raises(ValueError, match='미해결'):
        final_review(tmp_path, Provider())
    assert json.loads((tmp_path/'status.json').read_text())['state'] == 'needs_revision'
    assert not (tmp_path/'final-review.json').exists()
