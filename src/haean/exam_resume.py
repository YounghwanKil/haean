"""Continue an interrupted exam in a new lineage without overwriting prior runs."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path

from .codex_runtime import CodexProvider
from .corpus import Corpus
from .full_exam import assemble, load_plan, brief_difficulty
from .models import Brief, Draft
from .pipeline import prepare, run_pipeline, save


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_jobs(previous, replacements=()):
    """Explicit replacements must replace whole source bundles, without overlap."""
    jobs = read(Path(previous) / 'production.json')['jobs']
    replacements = [job for path in replacements for job in read(path)['jobs']]
    replaced_ids = [item for job in replacements for item in job['ids']]
    if len(replaced_ids) != len(set(replaced_ids)):
        raise ValueError('대체 묶음 ID 중복')
    remaining = set(replaced_ids)
    selected = []
    for job in jobs:
        overlap = set(job['ids']) & remaining
        if overlap and overlap != set(job['ids']):
            raise ValueError('원 묶음 전체를 대체해야 합니다')
        if overlap:
            remaining -= overlap
        else:
            selected.append(job)
    if remaining:
        raise ValueError('원 회차에 없는 대체 ID')
    return sorted(selected + replacements, key=lambda j: min(j['slots']))


def seed_from(run):
    drafts = sorted(run.glob('draft-r*.json'), key=lambda p: int(p.stem.split('-r')[1]))
    if not drafts:
        inherited = run / 'inherited-draft.json'
        if inherited.exists():
            review = run / 'inherited-review.json'
            return read(inherited), read(review) if review.exists() else None, inherited
        if (run / 'candidate.json').exists():
            raise ValueError('후보만 있고 초안 이력이 없는 run은 자동 재개할 수 없습니다')
        return None, None, None
    path = drafts[-1]
    review = run / path.name.replace('draft-', 'review-')
    return read(path), read(review) if review.exists() else None, path


def resume(previous, db, out, workers=3, max_revisions=2, model='gpt-6-astra', replacements=()):
    if not 1 <= workers <= 3 or not 0 <= max_revisions <= 3:
        raise ValueError('workers 1–3, max_revisions 0–3 범위를 사용하세요')
    previous, out = Path(previous).resolve(), Path(out).resolve()
    plan = load_plan(previous / 'plan.json')
    selected = select_jobs(previous, replacements)
    slot_map = {s['id']: s for s in plan['slots']}
    ids = [i for job in selected for i in job['ids']]
    if len(ids) != len(set(ids)) or set(ids) != set(slot_map):
        raise ValueError('재개 배정의 ID 중복·누락')
    if out.exists():
        raise ValueError('새 재개 출력 경로가 필요합니다. 기존 기록을 보존합니다')
    out.mkdir(parents=True)
    save(out / 'plan.json', plan)
    from .evaluation import harness_fingerprint
    save(out / 'provenance.json', {'mode': 'resumed-production', 'model': model,
        'parent': str(previous), 'parent_manifest_sha256': sha(previous / 'production.json'),
        'replacement_manifests': [{'path': str(Path(p).resolve()), 'sha256': sha(p)} for p in replacements],
        'harness': harness_fingerprint(), 'max_revisions': max_revisions,
        'humanizer': 'not_applied', 'expert_verified': False})
    jobs, seeds = [], {}
    corpus = Corpus(db)
    for source in selected:
        parent = Path(source['run']).resolve()
        state = read(parent / 'status.json')
        candidate = parent / 'candidate.json'
        if state['state'] == 'awaiting_human_review':
            if not candidate.exists() or state.get('candidate_sha256') != sha(candidate):
                raise ValueError('기존 검토 해시 불일치: ' + str(parent))
            if [i.id for i in Draft.model_validate_json(candidate.read_text()).items] != source['ids']:
                raise ValueError('기존 후보의 ID·순서 불일치')
            jobs.append({**source, 'bundle': len(jobs)+1, 'state': state['state'], 'reused': True})
            continue
        seed, review, seed_path = seed_from(parent)
        original_group = [slot_map[i] for i in source['ids']]
        # Never split an existing draft or a shared passage pair.
        groups = [original_group] if seed or any(s.get('shared_passage_id') for s in original_group) else [original_group[i:i+2] for i in range(0, len(original_group), 2)]
        for group in groups:
            brief = Brief(exam=plan['exam'], subject=plan['subject'], item_type=group[0]['item_type'],
                topic=' / '.join(s['topic'] for s in group), count=len(group),
                difficulty=brief_difficulty(group),
                shared_passage=bool(group[0].get('shared_passage_id')))
            run = prepare(corpus, brief, out / 'bundles')
            context = read(run / 'context.json')
            old_context = read(parent / 'context.json')
            if seed:
                # Preserve references used by the inherited draft; no retrospective RAG replacement.
                for key in ('references', 'retrieval', 'feedback'):
                    context[key] = old_context.get(key, [] if key != 'retrieval' else {})
                save(run / 'retrieval.json', context['retrieval'])
            for key in ('exam_contract', 'argument_structure_instructions'):
                if key in old_context:
                    context[key] = old_context[key]
            context['exam_contract'] = context.get('exam_contract', '') + '\n개별 난도는 exam_assignment를 우선한다. 그림 검토 미완료를 실제 확인 없이 해결되었다고 쓰지 말라.'
            context['exam_assignment'] = group
            context['resume_lineage'] = {'parent': str(parent), 'parent_state': state['state'],
                'seed_sha256': sha(seed_path) if seed_path else None,
                'seed_path': str(seed_path) if seed_path else None}
            save(run / 'context.json', context)
            save(run / 'lineage.json', context['resume_lineage'])
            provenance = read(run / 'provenance.json')
            provenance['source_ids'] = [r['id'] for r in context['references']]
            save(run / 'provenance.json', provenance)
            from .pipeline import writer_prompt
            (run / 'request.md').write_text(writer_prompt(brief) + '\n\n입력 자료(JSON):\n' + json.dumps(context, ensure_ascii=False, indent=2))
            job = {'bundle': len(jobs)+1, 'run': str(run), 'ids': [s['id'] for s in group],
                'slots': [s['number'] for s in group], 'state': 'prepared', 'parent_run': str(parent), 'reused': False}
            jobs.append(job)
            seeds[str(run)] = (seed, review)
    manifest = {'exam': plan['exam'], 'subject': plan['subject'], 'total': len(plan['slots']),
        'jobs': jobs, 'complete': False, 'human_approved': False, 'parent': str(previous)}
    save(out / 'production.json', manifest)

    def work(job):
        run = Path(job['run'])
        try:
            seed, review = seeds[str(run)]
            provider = CodexProvider(model, max_calls=4+3*max_revisions, timeout=1200, trace_dir=run/'codex-traces')
            draft = run_pipeline(run, provider, max_revisions, initial_draft=seed, initial_review=review)
            state = read(run / 'status.json')
            if [i.id for i in draft.items] != job['ids']:
                state.update(state='needs_revision', errors=[*state.get('errors', []), '회차 ID·순서 불일치'])
                save(run / 'status.json', state)
            return {**job, 'state': state['state'], 'errors': state.get('errors', [])}
        except Exception as exc:
            return {**job, 'state': 'failed', 'error': f'{type(exc).__name__}: {exc}'}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(work, job): i for i, job in enumerate(jobs) if not job['reused']}
        for future in as_completed(pending):
            index = pending[future]
            manifest['jobs'][index] = future.result()
            save(out / 'production.json', manifest)
    manifest['complete'] = all(j['state'] == 'awaiting_human_review' for j in manifest['jobs'])
    save(out / 'production.json', manifest)
    return assemble(out)
