"""Validate an execution selection without shrinking an exam's manifest."""
from pathlib import Path


def selected_slots(plan, jobs, slots):
    if slots is None:
        return None
    if (not isinstance(slots, (list, tuple)) or not slots
            or any(type(number) is not int or number < 1 for number in slots)):
        raise ValueError('slots는 비어 있지 않은 양의 정수 번호 목록이어야 합니다')
    if len(slots) != len(set(slots)):
        raise ValueError('slots 문항 번호 중복')
    rows = plan['slots']
    numbers = [row['number'] for row in rows]
    ids = [row['id'] for row in rows]
    if (any(type(number) is not int or number < 1 for number in numbers)
            or any(not isinstance(item_id, str) or not item_id for item_id in ids)
            or len(set(numbers)) != len(numbers) or len(set(ids)) != len(ids)):
        raise ValueError('재개 plan 문항 ID·번호 중복·형식 오류')
    missing = set(slots) - set(numbers)
    if missing:
        raise ValueError('원 회차에 없는 문항 번호: ' + ', '.join(map(str, sorted(missing))))
    slot_map = dict(zip(ids, rows))
    seen, runs, shared = set(), set(), {}
    for index, job in enumerate(jobs):
        item_ids, job_slots = job.get('ids'), job.get('slots')
        if (not isinstance(item_ids, list) or not item_ids
                or any(not isinstance(item_id, str) or item_id not in slot_map
                       or item_id in seen for item_id in item_ids)
                or len(set(item_ids)) != len(item_ids)):
            raise ValueError('재개 배정 ID 중복·누락')
        if (not isinstance(job_slots, list) or any(type(number) is not int for number in job_slots)
                or job_slots != [slot_map[item_id]['number'] for item_id in item_ids]):
            raise ValueError('재개 배정 ID·번호·순서 불일치')
        seen.update(item_ids)
        if not isinstance(job.get('run'), str) or not job['run']:
            raise ValueError('재개 run 경로 누락')
        run = Path(job['run']).resolve()
        if run in runs:
            raise ValueError('재개 run 중복')
        runs.add(run)
        for item_id in item_ids:
            key = slot_map[item_id].get('shared_passage_id')
            if key:
                if key in shared and shared[key] != index:
                    raise ValueError('공통지문 묶음 분리')
                shared[key] = index
    if seen != set(ids):
        raise ValueError('재개 배정 ID 누락')
    requested = set(slots)
    for job in jobs:
        overlap = requested.intersection(job['slots'])
        if overlap and overlap != set(job['slots']):
            raise ValueError('기존 묶음 전체를 선택해야 합니다. 함께 필요한 번호: '
                             + ', '.join(map(str, sorted(set(job['slots']) - requested))))
    return requested


def deferred_job(source, state, revision_feedback, bundle):
    """Keep the original run and its errors; never rewrite its review status."""
    from .revision_feedback import requires_revision
    job = {**source, 'bundle': bundle, 'state': state['state'], 'reused': True, 'deferred': True,
           'source_manifest_state': source.get('state'), 'source_run_state': state['state']}
    for key in ('errors', 'error'):
        if key in state:
            if key in source and source[key] != state[key]:
                job['source_manifest_' + key] = source[key]
            job[key] = state[key]
    # A prior selection's copied packet is not authoritative; re-read the run.
    job.pop('pending_revision_feedback', None)
    if requires_revision(revision_feedback):
        job['pending_revision_feedback'] = revision_feedback
    return job


def manifest_complete(jobs):
    return all(job['state'] == 'awaiting_human_review' and not job.get('pending_revision_feedback')
               for job in jobs)
