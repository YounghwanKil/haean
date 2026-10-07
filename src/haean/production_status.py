"""Read saved production progress without starting or resuming model calls."""
from collections import Counter
import hashlib
import json
from pathlib import Path


def production_status(folder):
    folder = Path(folder).resolve()
    try:
        manifest = json.loads((folder / 'production.json').read_text())
    except json.JSONDecodeError as exc:
        raise ValueError('production.json 저장 중이거나 손상되었습니다. 잠시 후 다시 조회하세요.') from exc
    jobs, warnings = [], []
    reviewed = 0
    for job in manifest['jobs']:
        run = Path(job['run'])
        traces = sorted((run / 'codex-traces').glob('[0-9][0-9]-*.input.json'))
        state = {}
        try:
            state = json.loads((run / 'status.json').read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            warnings.append(f"묶음 {job['bundle']}: 상태 파일 없음 또는 저장 중")
        candidate = run / 'candidate.json'
        bound = (candidate.exists() and state.get('candidate_sha256') ==
                 hashlib.sha256(candidate.read_bytes()).hexdigest())
        passed = state.get('state') == 'awaiting_human_review' and bound
        if passed:
            reviewed += len(job['slots'])
        if state.get('state') == 'awaiting_human_review' and not bound:
            warnings.append(f"묶음 {job['bundle']}: 검토 버전 해시 불일치")
        jobs.append({'bundle': job['bundle'], 'slots': job['slots'],
                     'manifest_state': job['state'], 'run_state': state.get('state'),
                     'last_requested_stage': traces[-1].name.removesuffix('.input.json') if traces else None,
                     'reviewed_candidate_hash_matches': bool(passed),
                     'errors': job.get('errors', []), 'error': job.get('error')})
    return {'folder': str(folder), 'exam': manifest['exam'], 'subject': manifest['subject'],
            'total_items': manifest['total'], 'total_bundles': len(jobs),
            'manifest_states': dict(Counter(j['manifest_state'] for j in jobs)),
            'model_reviewed_items_with_matching_hash': reviewed,
            'process_liveness': 'not_checked', 'warnings': warnings, 'jobs': jobs,
            'note': '저장된 기록 조회입니다. 마지막 요청은 완료 증거가 아니며 프로세스 생존·사람 승인·인쇄 검증을 판정하지 않습니다.'}
