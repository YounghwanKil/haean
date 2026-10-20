"""Read saved production progress without starting or resuming model calls."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from .production_review_provenance import review_provenance


def production_status(folder):
    folder = Path(folder).resolve()
    try:
        manifest = json.loads((folder / 'production.json').read_text())
    except json.JSONDecodeError as exc:
        raise ValueError('production.json 저장 중이거나 손상되었습니다. 잠시 후 다시 조회하세요.') from exc
    jobs, warnings = [], []
    reviewed, ready, claimed, records_found = 0, 0, 0, 0
    for job in manifest['jobs']:
        run = Path(job['run'])
        traces = sorted((run / 'codex-traces').glob('[0-9][0-9]-*.input.json'))
        state = {}
        try:
            state = json.loads((run / 'status.json').read_text())
            if not isinstance(state, dict):
                raise ValueError('status 객체 필요')
        except (OSError, ValueError):
            state = {}
            warnings.append(f"묶음 {job['bundle']}: 상태 파일 없음 또는 저장 중")
        candidate = run / 'candidate.json'
        try:
            bound = state.get('candidate_sha256') == hashlib.sha256(candidate.read_bytes()).hexdigest()
        except OSError:
            bound = False
        status_claim = state.get('state') == 'awaiting_human_review' and bound
        if status_claim:
            claimed += len(job['slots'])
        if state.get('state') == 'awaiting_human_review' and not bound:
            warnings.append(f"묶음 {job['bundle']}: 검토 버전 해시 불일치")
        provenance = review_provenance(run)
        evidence = provenance['items']
        # A broken manifest must not turn one checked item into several slots.
        mapped = len(evidence) == len(job['slots'])
        if not mapped:
            provenance['error'] = provenance['error'] or 'manifest_item_count_mismatch'
        if 'ids' in job and job['ids'] != [item['item_id'] for item in evidence]:
            mapped = False
            provenance['error'] = 'manifest_item_ids_mismatch'
        provenance['manifest_mapping'] = ('ids_and_count' if 'ids' in job else 'count_only; manifest has no item IDs')
        verified = [item for item in evidence if item['verified']] if mapped else []
        reviewed += len(verified)
        records_found += sum(bool(item['records_found']) for item in evidence) if mapped else 0
        ready_items = [item for item in verified if status_claim and item['review_passed']
                       and item['pending_revision_feedback'] is False and item['feedback_error'] is None]
        ready += len(ready_items)
        feedback_errors = [item['feedback_error'] for item in evidence if item['feedback_error']]
        feedback_error = '; '.join(dict.fromkeys(feedback_errors)) or None
        pending_feedback = (None if feedback_error else
                            any(item['pending_revision_feedback'] for item in evidence))
        effective_state = state.get('state')
        if status_claim:
            if len(verified) != len(job['slots']) or feedback_error:
                effective_state = 'review_unverified'
            elif pending_feedback or any(not item['review_passed'] for item in verified):
                effective_state = 'needs_revision'
            else:
                effective_state = 'awaiting_human_review'
        elif effective_state == 'awaiting_human_review':
            effective_state = 'review_unverified'
        if pending_feedback:
            warnings.append(f"묶음 {job['bundle']}: 현 후보에 미적용 A/B 후속 의견")
        if feedback_error:
            warnings.append(f"묶음 {job['bundle']}: 후속 의견 확인 실패: {feedback_error}")
        if effective_state == 'review_unverified' and not feedback_error:
            reasons = sorted({item['reason'] for item in evidence if item['reason']})
            warnings.append(f"묶음 {job['bundle']}: 현재 문항 검토 근거 미확인: "
                            + ', '.join(reasons or [provenance['error'] or 'review_not_found']))
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
            except (OSError, ValueError, AttributeError, TypeError):
                warnings.append(f"묶음 {job['bundle']}: 최근 검토 파일 저장 중 또는 손상")
        jobs.append({'bundle': job['bundle'], 'slots': job['slots'],
                     'manifest_state': job['state'], 'run_state': state.get('state'),
                     'effective_state': effective_state,
                     'deferred': bool(job.get('deferred', False)),
                     'pending_revision_feedback': pending_feedback, 'feedback_error': feedback_error,
                     'last_requested_stage': traces[-1].name.removesuffix('.input.json') if traces else None,
                     'candidate_hash_matches_status': bool(bound),
                     'status_claims_reviewed_with_matching_hash': bool(status_claim),
                     'reviewed_candidate_hash_matches': bool(mapped and evidence and len(verified) == len(evidence)),
                     'verified_review_items': len(verified), 'ready_for_human_review_items': len(ready_items),
                     'review_provenance': provenance,
                     'review_records_found_items': sum(bool(item['records_found']) for item in evidence) if mapped else 0,
                     'last_saved_review': last_review,
                     'errors': job.get('errors', []), 'error': job.get('error')})
    # Duplicate rows must not inflate a production's reviewed/ready totals.
    # Reject every affected mapping, rather than silently blessing the first.
    id_counts = Counter(item['item_id'] for job in jobs for item in job['review_provenance']['items'])
    slot_counts = Counter(slot for job in jobs for slot in job['slots'])
    run_counts = Counter(str(Path(job['run']).resolve()) for job in manifest['jobs'])
    for job, source in zip(jobs, manifest['jobs']):
        duplicate_ids = sorted({item['item_id'] for item in job['review_provenance']['items']
                                if id_counts[item['item_id']] > 1})
        duplicate_slots = [slot for slot in job['slots'] if slot_counts[slot] > 1]
        duplicate_run = run_counts[str(Path(source['run']).resolve())] > 1
        if duplicate_ids or duplicate_slots or duplicate_run:
            job['review_provenance']['error'] = 'manifest_duplicate_item_mapping'
            job['review_provenance']['duplicate_mapping'] = {
                'item_ids': duplicate_ids, 'slots': duplicate_slots, 'run': duplicate_run}
            job['verified_review_items'] = job['ready_for_human_review_items'] = 0
            job['review_records_found_items'] = 0
            job['reviewed_candidate_hash_matches'] = False
            job['effective_state'] = 'review_unverified'
            warnings.append(f"묶음 {job['bundle']}: production 문항 ID·슬롯·run 중복 연결")
    reviewed = sum(job['verified_review_items'] for job in jobs)
    ready = sum(job['ready_for_human_review_items'] for job in jobs)
    records_found = sum(job['review_records_found_items'] for job in jobs)
    return {'folder': str(folder), 'exam': manifest['exam'], 'subject': manifest['subject'],
            'total_items': manifest['total'], 'total_bundles': len(jobs),
            'manifest_states': dict(Counter(j['manifest_state'] for j in jobs)),
            'status_claimed_reviewed_items_with_matching_hash': claimed,
            'review_records_found_items': records_found,
            'model_reviewed_items_with_matching_hash': reviewed,
            'ready_for_human_review_items': ready,
            'effective_states': dict(Counter(j['effective_state'] for j in jobs)),
            'process_liveness': 'not_checked', 'warnings': warnings, 'jobs': jobs,
            'note': '상태의 검토 완료 주장·기록 발견·현재 문항에 연결된 검토를 구분합니다. '
                    'model_reviewed_items_with_matching_hash는 호환 필드명이며 실행 모델을 인증하지 않습니다. '
                    'ready는 검토 근거·정답·오류와 현 버전 및 상속 경로의 해당 문항 후속 의견을 확인한 수입니다. '
                    'legacy 기록 발견만으로 ready를 인정하지 않습니다. 마지막 요청·사람 승인·인쇄 검증·프로세스 생존은 판정하지 않습니다.'}
