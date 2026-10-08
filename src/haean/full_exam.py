"""Produce a planned full exam with bounded parallel, separately reviewed bundles."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
from pathlib import Path

from .corpus import Corpus
from .models import Brief, Draft, Item
from .pipeline import prepare, run_pipeline, save
from .codex_runtime import CodexProvider


def load_plan(path):
    plan = json.loads(Path(path).read_text())
    expected = 25 if plan['exam'] == 'psat7' else 40
    slots = plan['slots']
    if len(slots) != expected or sorted(s['number'] for s in slots) != list(range(1, expected+1)):
        raise ValueError('회차 문항 수·번호 누락 또는 중복')
    if len({s['id'] for s in slots}) != expected: raise ValueError('회차 문항 ID 중복')
    for s in slots:
        Brief(exam=plan['exam'], subject=plan['subject'], item_type=s['item_type'], topic=s['topic'])
    return plan


def bundles(plan):
    """Group like types; keep each shared passage pair in its own writer call."""
    singles, shared = defaultdict(list), defaultdict(list)
    for slot in plan['slots']:
        if slot.get('shared_passage_id'): shared[slot['shared_passage_id']].append(slot)
        else: singles[(slot['domain'], slot['item_type'])].append(slot)
    result = []
    for group in shared.values():
        if len(group) != 2:
            raise ValueError('공통지문은 2문항으로 배정하세요')
        result.append(group)
    for group in singles.values():
        result.extend(group[i:i+4] for i in range(0, len(group), 4))
    return sorted(result, key=lambda g: min(s['number'] for s in g))


def brief_difficulty(group):
    """Coarse schema level only; retain finer slot labels in exam_assignment."""
    levels = {s['difficulty'] for s in group}
    return next(iter(levels)) if len(levels) == 1 and levels <= {'하', '중', '상'} else '중'


def build(plan_path, db, out, workers=3, max_revisions=2, model='gpt-6-astra'):
    if not 1 <= workers <= 3: raise ValueError('동시 출제 묶음은 1–3개')
    plan_path, out = Path(plan_path), Path(out)
    plan = load_plan(plan_path)
    if out.exists(): raise ValueError('새 회차 실행 경로를 사용하세요. 기존 실행 기록은 보존합니다')
    out.mkdir(parents=True)
    save(out/'plan.json', plan)
    from .evaluation import harness_fingerprint
    save(out/'provenance.json', {'model': model, 'mode': 'codex-prompt-pipeline',
        'humanizer': 'not_applied', 'expert_verified': False, 'harness': harness_fingerprint(),
        'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(), 'max_revisions': max_revisions})
    jobs = []
    corpus = Corpus(db)
    for index, group in enumerate(bundles(plan), 1):
        brief = Brief(exam=plan['exam'], subject=plan['subject'], item_type=group[0]['item_type'],
            topic=' / '.join(s['topic'] for s in group), count=len(group),
            difficulty=brief_difficulty(group),
            shared_passage=bool(group[0].get('shared_passage_id')))
        run = prepare(corpus, brief, out/'bundles')
        context = json.loads((run/'context.json').read_text())
        context['exam_assignment'] = group
        from .leet_editorial import exam_editorial_context
        editorial_context = exam_editorial_context(plan, group)
        if editorial_context is not None:
            context['exam_editorial_context'] = editorial_context
        if any(s.get('special_design') == 'argument_structure' for s in group):
            from .pipeline import prompt
            context['argument_structure_instructions'] = prompt('argument_structure')
        context['exam_contract'] = ('회차 배정표의 각 id, 소재, 영역, 추론 과제, 개별 난도를 지켜 한 문항씩 작성하라. '
            '여러 문항의 개별 난도가 다른 묶음에서는 공통 brief.difficulty보다 exam_assignment의 개별 난도를 우선한다. '
            '각 item_type은 해당 슬롯의 item_type과 일치해야 한다. answer_target은 권장 분포이고 논리를 바꿔 강요하지 말라. '
            '배정된 순서대로 출력하고 회차의 다른 문항이 정답 단서가 되지 않게 하라. '
            '작성 문항 외의 슬롯을 임의로 추가하지 말라. 해설과 1–5 선지별 판단을 빠짐없이 작성하라. '
            '그림이 필요하면 figures를 반드시 채워라. 논증구조는 option_1부터 option_5까지 argument 도식 5개, '
            '표→그래프는 bar 또는 line의 범주·계열·축 단위와 선택지별 실제 수치를 넣는다. '
            '텍스트 설명만으로 그림 유형을 대체하거나 렌더가 끝났다고 쓰지 말라. '
            '사용하지 않는 그림 필드는 빈 배열/빈 문자열로 채운다. 그림이 필요 없는 문항의 figures는 빈 배열이다.')
        save(run/'context.json', context)
        with (run/'request.md').open('a') as f:
            f.write('\n\n회차 배정:\n'+json.dumps(group, ensure_ascii=False, indent=2))
            if editorial_context is not None:
                f.write('\n\n회차 소재·구조 대조:\n'+json.dumps(editorial_context, ensure_ascii=False, indent=2))
        jobs.append({'bundle': index, 'run': str(run.resolve()), 'slots': [s['number'] for s in group],
                     'ids': [s['id'] for s in group], 'state': 'prepared'})
    manifest = {'exam': plan['exam'], 'subject': plan['subject'], 'total': len(plan['slots']), 'jobs': jobs,
                'complete': False, 'human_approved': False}
    save(out/'production.json', manifest)
    def work(job):
        run = Path(job['run'])
        provider = CodexProvider(model, max_calls=3+3*max_revisions, timeout=1200, trace_dir=run/'codex-traces')
        try:
            draft = run_pipeline(run, provider, max_revisions)
            state = json.loads((run/'status.json').read_text())
            if [i.id for i in draft.items] != job['ids']:
                state.update(state='needs_revision', errors=[*state.get('errors', []), '회차 배정 문항 ID·순서 불일치'])
                save(run/'status.json', state)
            return {**job, 'state': state['state'], 'errors': state.get('errors', [])}
        except Exception as exc:
            return {**job, 'state': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(work, job): i for i, job in enumerate(jobs)}
        for future in as_completed(pending):
            manifest['jobs'][pending[future]] = future.result()
            save(out/'production.json', manifest)
    manifest['complete'] = all(j['state'] == 'awaiting_human_review' for j in manifest['jobs'])
    save(out/'production.json', manifest)
    return assemble(out)


def assemble(out):
    out = Path(out).resolve()
    plan, production = json.loads((out/'plan.json').read_text()), json.loads((out/'production.json').read_text())
    lookup, errors = {}, []
    for job in production['jobs']:
        run = Path(job['run'])
        if not (run/'candidate.json').exists(): errors.append(f"미작성 묶음 {job['bundle']}"); continue
        candidate = run/'candidate.json'
        draft = Draft.model_validate_json(candidate.read_text())
        source_state = json.loads((run/'status.json').read_text())
        if source_state.get('candidate_sha256') != hashlib.sha256(candidate.read_bytes()).hexdigest():
            errors.append(f"검토 버전 해시 불일치 묶음 {job['bundle']}")
        if [item.id for item in draft.items] != job['ids']:
            errors.append(f"배정 ID·순서 불일치 묶음 {job['bundle']}")
        for item in draft.items:
            if item.id in lookup: errors.append('문항 ID 중복: '+item.id)
            lookup[item.id] = (item, run)
    items, item_runs, status = [], [], []
    for slot in plan['slots']:
        if slot['id'] not in lookup: errors.append(f"미작성 {slot['number']}번"); continue
        item, parent = lookup[slot['id']]
        source_state = json.loads((parent/'status.json').read_text())
        if source_state['state'] != 'awaiting_human_review': errors.append(f"재검토 필요 {slot['number']}번")
        errors.extend(check_slot(slot, item, plan['subject']))
        items.append({'number': slot['number'], **item.model_dump()})
        view = out/'items'/f"{slot['number']:02d}"; view.mkdir(parents=True, exist_ok=True)
        save(view/'candidate.json', {'design_summary': '회차 검토 묶음에서 분리한 편집 뷰', 'items': [item.model_dump()]})
        brief = json.loads((parent/'brief.json').read_text()); brief.update(count=1, shared_passage=False)
        # A mixed bundle's common brief must not replace this slot's assignment.
        for field in ('difficulty', 'item_type', 'topic'):
            if field in slot:
                brief[field] = slot[field]
        save(view/'brief.json', brief)
        state = {**source_state, 'parent_review_run': str(parent), 'human_approved': False,
                 'candidate_sha256': hashlib.sha256((view/'candidate.json').read_bytes()).hexdigest(),
                 'note': '독립 검토는 parent_review_run에서 묶음으로 실행했다. 분리 후 새 검토를 한 것이 아니다.'}
        save(view/'status.json', state)
        item_runs.append(str(view.resolve()))
        status.append({'number': slot['number'], 'id': item.id, 'run': str(view.resolve()),
                       'parent_run': str(parent), 'state': source_state['state']})
    answers = [i['answer'] for i in items]
    repeated = [items[i]['number'] for i in range(2, len(answers)) if answers[i] == answers[i-1] == answers[i-2]]
    passages = Counter(i['passage'] for i in items if not i['shared_passage_id'])
    if any(n > 1 for n in passages.values()): errors.append('독립 문항 지문 중복')
    shared = defaultdict(list)
    for item in items:
        if item['shared_passage_id']: shared[item['shared_passage_id']].append(item)
    for shared_id, group in shared.items():
        if len(group) != 2 or any((i['passage'], i['tables']) != (group[0]['passage'], group[0]['tables']) for i in group):
            errors.append('공통지문·표 불일치: '+shared_id)
    result = {'exam': plan['exam'], 'subject': plan['subject'], 'requested': len(plan['slots']),
        'written': len(items), 'items': status, 'errors': errors, 'answer_distribution': dict(Counter(answers)),
        'three_answer_streak_endings': repeated, 'item_runs': item_runs,
        'composition_observations': composition_observations(plan, items),
        'ready_for_human_review': len(items) == len(plan['slots']) and not errors,
        'human_approved': False, 'layout_verified': False, 'delivery_ready': False}
    save(out/'assembled.json', result)
    save(out/'exam-items.json', {'items': items})
    render_exam(out, items, result)
    return result


def composition_observations(plan, items):
    """Describe whole-exam patterns without treating counts as quality scores."""
    by_number = {i['number']: i for i in items}
    blocks = []
    for start in range(1, len(plan['slots']) + 1, 5):
        numbers = list(range(start, start + 5))
        if not all(n in by_number for n in numbers): continue
        answers = [by_number[n]['answer'] for n in numbers]
        blocks.append({'numbers': numbers, 'answers': answers,
                       'all_five_answers_once': sorted(answers) == [1, 2, 3, 4, 5]})
    mismatches = []
    for slot in plan['slots']:
        actual = by_number.get(slot['number'], {}).get('difficulty')
        expected = slot.get('difficulty')
        if actual and expected and actual != expected:
            mismatches.append({'number': slot['number'], 'planned': expected, 'actual': actual})
    return {'five_item_blocks': blocks,
            'all_five_answers_once_blocks': sum(b['all_five_answers_once'] for b in blocks),
            'planned_difficulty': dict(Counter(s['difficulty'] for s in plan['slots'] if s.get('difficulty'))),
            'actual_difficulty': dict(Counter(i['difficulty'] for i in items if i.get('difficulty'))),
            'difficulty_mismatches': mismatches,
            'note': '회차 편집 검토용 관찰값. 균등 분포나 패턴 개수로 합격을 판정하지 않는다. 난도는 실측값이 아니다.'}


def check_slot(slot, item, subject):
    """Mechanical completeness only; this does not establish logical correctness."""
    errors, prefix = [], f"{slot['number']}번: "
    if item.subject != subject or item.item_type != slot['item_type']:
        errors.append(prefix+'과목·유형 배정 불일치')
    if item.shared_passage_id != slot.get('shared_passage_id'):
        errors.append(prefix+'공통지문 ID 불일치')
    if slot.get('special_design') == 'argument_structure':
        places = [f.placement for f in item.figures if f.kind == 'argument']
        if sorted(places) != [f'option_{i}' for i in range(1,6)]:
            errors.append(prefix+'논증구조 선택지 그림 5개 누락·중복')
    if slot.get('graph_design'):
        chart_figures = [f for f in item.figures if f.kind in {'bar', 'line'}]
        requirements = slot['graph_design'].get('figure_requirements', {})
        if requirements:
            if len(chart_figures) != requirements['count'] or any(f.placement != requirements['placement'] for f in chart_figures):
                errors.append(prefix+'배정 그래프 개수·위치 불일치')
        elif sorted(f.placement for f in chart_figures) != [f'option_{i}' for i in range(1,6)]:
            errors.append(prefix+'그래프 선택지 5개 누락·중복')
    if '합답' in slot.get('response_format', '') and not item.statements and not item.figures:
        errors.append(prefix+'합답형 보기 누락')
    return errors


def render_exam(out, items, result):
    from .export import export_review
    problems, solutions = [], []
    for row in result['items']:
        run = Path(row['run']); export_review(run)
        for name, blocks in [('questions', problems), ('solutions', solutions)]:
            text = (run/f'{name}.html').read_text()
            article = text[text.index('<article>'):text.rindex('</article>')+len('</article>')]
            article = article.replace('src="figures/', 'src="'+str(run.relative_to(out))+'/figures/')
            blocks.append(article.replace('<h2>1.', f"<h2>{row['number']}.", 1))
    for name, blocks in [('questions', problems), ('solutions', solutions)]:
        title = html.escape(f"해안 {result['exam']} {result['subject']} 모의고사 검토용")
        content = f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{title}</title>'
        content += '<style>body{max-width:900px;margin:40px auto;font-family:serif;line-height:1.8}article{break-before:page;padding:20px 0}table{border-collapse:collapse;width:100%}td,th{border:1px solid;padding:5px}aside{border:1px solid;padding:12px}h2{font-size:18px}</style>'
        content += f'<h1>{title}</h1><p>{result["written"]}/{result["requested"]}문항 · 사람 검토 전 · HWP 인쇄 양식과 별도</p>'
        (out/f'{name}.html').write_text(content+''.join(blocks)+'</html>')
