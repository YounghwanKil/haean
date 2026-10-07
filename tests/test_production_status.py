import hashlib
import json

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
    (tmp_path / 'production.json').write_text(json.dumps({
        'exam': 'psat7', 'subject': '언어논리', 'total': 3, 'jobs': jobs}))
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    report = production_status(tmp_path)
    assert report['model_reviewed_items_with_matching_hash'] == 1
    assert report['process_liveness'] == 'not_checked'
    assert report['jobs'][0]['last_requested_stage'] == '03-editor'
    assert report['jobs'][0]['reviewed_candidate_hash_matches'] is False
    assert '해시 불일치' in report['warnings'][0]
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
