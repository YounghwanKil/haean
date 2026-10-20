import hashlib
import json

import pytest

from haean.production_status import production_status


def test_progress_does_not_confuse_requested_review_with_completion(tmp_path):
    runs = [tmp_path / str(n) for n in range(3)]
    jobs = []
    for n, run in enumerate(runs):
        (run / 'codex-traces').mkdir(parents=True)
        (run / 'codex-traces' / '03-editor.input.json').write_text('{}')
        candidate = run / 'candidate.json'
        candidate.write_text('{}')
        state = {'state': 'prepared'} if n == 0 else {
            'state': 'awaiting_human_review',
            'candidate_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest()}
        (run / 'status.json').write_text(json.dumps(state))
        jobs.append({'bundle': n+1, 'slots': [n+1], 'run': str(run), 'state': 'prepared'})
    # A candidate changed after review cannot be counted as reviewed.
    (runs[2] / 'candidate.json').write_text('{"changed":true}')
    (runs[0] / 'review-r0.json').write_text(json.dumps({
        'revision': 0, 'errors': ['정의 조건 누락'],
        'editorial': {'issues': [{'severity': 'A', 'problem': '정의 조건 누락'}]}}))
    (runs[0] / 'codex-traces' / '04-revise.input.json').write_text('{}')
    (tmp_path / 'production.json').write_text(json.dumps({
        'exam': 'psat7', 'subject': '언어논리', 'total': 3, 'jobs': jobs}))
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    report = production_status(tmp_path)
    assert report['model_reviewed_items_with_matching_hash'] == 1
    assert report['process_liveness'] == 'not_checked'
    assert report['jobs'][0]['last_requested_stage'] == '04-revise'
    # A prepared manifest must not hide an error while its revision is running.
    assert report['jobs'][0]['last_saved_review']['errors'] == ['정의 조건 누락']
    assert report['jobs'][0]['reviewed_candidate_hash_matches'] is False
    assert '해시 불일치' in report['warnings'][0]
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


@pytest.mark.parametrize('severity,ready,effective', [('A', 0, 'needs_revision'),
    ('B', 0, 'needs_revision'), ('C', 1, 'awaiting_human_review')])
def test_pending_feedback_is_not_counted_as_ready(tmp_path, draft, brief, severity, ready, effective):
    from test_revision_feedback import original, add_feedback
    run = original(tmp_path, draft, brief)
    add_feedback(run, draft, severity)
    # Simulate a retained source status while a version-bound opinion was
    # appended later; status must inspect the opinion, not trust that flag.
    status_path = run / 'status.json'
    state = json.loads(status_path.read_text())
    state['state'] = 'awaiting_human_review'
    status_path.write_text(json.dumps(state))
    (tmp_path / 'production.json').write_text(json.dumps({'exam': brief.exam,
        'subject': brief.subject, 'total': 1, 'jobs': [{'bundle': 1, 'slots': [1],
        'run': str(run), 'state': 'awaiting_human_review', 'deferred': True}]}))
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = production_status(tmp_path)
    assert result['model_reviewed_items_with_matching_hash'] == 1
    assert result['ready_for_human_review_items'] == ready
    assert result['jobs'][0]['effective_state'] == effective
    assert result['jobs'][0]['pending_revision_feedback'] is (severity != 'C')
    assert result['jobs'][0]['deferred'] is True
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_unreadable_feedback_reports_unknown_instead_of_ready(tmp_path, draft, brief):
    from test_revision_feedback import original
    run = original(tmp_path, draft, brief)
    (tmp_path / 'feedback.jsonl').write_text('broken feedback')
    (tmp_path / 'production.json').write_text(json.dumps({'exam': brief.exam,
        'subject': brief.subject, 'total': 1, 'jobs': [{'bundle': 1, 'slots': [1],
        'run': str(run), 'state': 'awaiting_human_review'}]}))
    result = production_status(tmp_path)
    assert result['model_reviewed_items_with_matching_hash'] == 1
    assert result['ready_for_human_review_items'] == 0
    assert result['jobs'][0]['effective_state'] == 'review_unverified'
    assert result['jobs'][0]['pending_revision_feedback'] is None
    assert '후속 의견' in result['warnings'][0]


def test_stale_feedback_does_not_block_current_candidate(tmp_path, draft, brief):
    from test_revision_feedback import original, add_feedback
    run = original(tmp_path, draft, brief)
    add_feedback(run, draft)
    changed = draft.model_copy(deep=True)
    changed.items[0].explanation += ' 합성 수정본'
    candidate = run / 'candidate.json'
    candidate.write_text(changed.model_dump_json())
    (run / 'status.json').write_text(json.dumps({'state': 'awaiting_human_review',
        'candidate_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest()}))
    (tmp_path / 'production.json').write_text(json.dumps({'exam': brief.exam,
        'subject': brief.subject, 'total': 1, 'jobs': [{'bundle': 1, 'slots': [1],
        'run': str(run), 'state': 'awaiting_human_review'}]}))
    result = production_status(tmp_path)
    assert result['ready_for_human_review_items'] == 1
    assert result['jobs'][0]['pending_revision_feedback'] is False
