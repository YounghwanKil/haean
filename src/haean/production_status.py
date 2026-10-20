"""Read saved production progress without starting or resuming model calls."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from .revision_feedback import load_revision_feedback, requires_revision


def production_status(folder):
    folder = Path(folder).resolve()
    try:
        manifest = json.loads((folder / 'production.json').read_text())
    except json.JSONDecodeError as exc:
        raise ValueError('production.json 저장 중이거나 손상되었습니다. 잠시 후 다시 조회하세요.') from exc
    jobs, warnings = [], []
    reviewed, ready = 0, 0
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
        effective_state = state.get('state')
        pending_feedback, feedback_error = None, None
        if passed:
            try:
                pending_feedback = requires_revision(load_revision_feedback(
                    run, json.loads(candidate.read_text())))
                if pending_feedback:
                    effective_state = 'needs_revision'
                    warnings.append(f"묶음 {job['bundle']}: 현 후보에 미적용 A/B 후속 의견")
                else:
                    ready += len(job['slots'])
            except (OSError, ValueError, TypeError, KeyError) as exc:
                pending_feedback, effective_state = None, 'review_unverified'
                feedback_error = f'{type(exc).__name__}: {exc}'
                warnings.append(f"묶음 {job['bundle']}: 후속 의견 확인 실패: {feedback_error}")
        elif effective_state == 'awaiting_human_review':
            effective_state = 'review_unverified'
        reviews = sorted(run.glob('review-r*.json'),
                         key=lambda p: int(p.stem.removeprefix('review-r'))
                         if p.stem.removeprefix('review-r').isdigit() else -1)
        last_review = None
        if reviews:
            try:
                review = json.loads(reviews[-1].read_text())
                last_review = {'revision': review.get('revision'),
                               'errors': review.get('errors', []),
                               'issues': review.get('blind', {}).get('issues', []) +
                                         review.get('editorial', {}).get('issues', [])}
            except json.JSONDecodeError:
                warnings.append(f"묶음 {job['bundle']}: 최근 검토 파일 저장 중 또는 손상")
        jobs.append({'bundle': job['bundle'], 'slots': job['slots'],
                     'manifest_state': job['state'], 'run_state': state.get('state'),
                     'effective_state': effective_state,
                     'deferred': bool(job.get('deferred', False)),
                     'pending_revision_feedback': pending_feedback, 'feedback_error': feedback_error,
                     'last_requested_stage': traces[-1].name.removesuffix('.input.json') if traces else None,
                     'reviewed_candidate_hash_matches': bool(passed),
                     'last_saved_review': last_review,
                     'errors': job.get('errors', []), 'error': job.get('error')})
    return {'folder': str(folder), 'exam': manifest['exam'], 'subject': manifest['subject'],
            'total_items': manifest['total'], 'total_bundles': len(jobs),
            'manifest_states': dict(Counter(j['manifest_state'] for j in jobs)),
            'model_reviewed_items_with_matching_hash': reviewed,
            'ready_for_human_review_items': ready,
            'effective_states': dict(Counter(j['effective_state'] for j in jobs)),
            'process_liveness': 'not_checked', 'warnings': warnings, 'jobs': jobs,
            'note': '저장 검토·해시 일치 수와 미적용 A/B 의견을 제외한 사람 검토 대기 수를 구분합니다. 마지막 요청은 완료 증거가 아니며 프로세스 생존·사람 승인·인쇄 검증을 판정하지 않습니다.'}
