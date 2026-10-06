"""Role-separated, reproducible retrieval with whole-item few-shot examples."""
import json
import re
from collections import Counter


def fields(row):
    return json.loads(row['meta']).get('fields', {})


def source_item_id(row):
    f = fields(row)
    year = re.search(r'20\d{2}', str(f.get('학년도', f.get('연도', ''))))
    number = f.get('문항 번호')
    if not year or not isinstance(number, (int, float)): return None
    if row['exam'] == 'leet': return f'{year.group()}_{int(number):02d}'
    return f"{row['exam']}:{f.get('회차', year.group())}:{f.get('과목')}:{int(number):02d}"


def retrieve(corpus, brief):
    query = f'{brief.subject} {brief.item_type} {brief.topic}'
    candidates = corpus.search(query, brief.exam, 10000, {'example', 'metadata'})
    candidates = [r for r in candidates if fields(r).get('과목') == brief.subject]
    def rank(row):
        f = fields(row)
        exact = brief.item_type in [f.get(k) for k in ('문항유형', '세부 유형 ID', '세부 유형명', '세부유형')]
        year = re.search(r'20\d{2}', str(f.get('학년도', f.get('연도', ''))))
        recent = int(year.group()) if year else 0
        return (row['role'] != 'example', not exact, -int(recent >= 2024), -row['score'], -recent, row['locator'])
    candidates.sort(key=rank)
    selected, years, seen = [], Counter(), set()
    # Prefer up to two references from each year, then fill any remaining slots.
    for diversify in (True, False):
        for row in candidates:
            if row['id'] in seen: continue
            f = fields(row)
            year = str(f.get('학년도', f.get('연도', 'unknown')))
            if diversify and years[year] >= 2: continue
            selected.append(row); seen.add(row['id']); years[year] += 1
            if len(selected) == 6: break
        if len(selected) == 6: break
    if not selected:
        selected = corpus.search(query, brief.exam, 4, {'wiki', 'reference'})
    principle_ids = {r['source_id'] for sheet in ('문항 제작 원칙', '자료 기준')
                     for r in corpus.rows(brief.exam, sheet) if r['row'] > 1}
    principles = [dict(r) for r in corpus.db.execute('SELECT * FROM records WHERE exam=?', (brief.exam,)) if r['id'] in principle_ids]
    feedback = corpus.search(query + ' 오류 수정', brief.exam, 30, {'feedback'})
    feedback = [r for r in feedback if fields(r).get('과목') in (None, brief.subject)][:3]
    refs = list({r['id']: r for r in [*selected, *principles, *feedback]}.values())
    references = []
    for row in refs:
        f = fields(row)
        meta = json.loads(row['meta'])
        record = {k: row[k] for k in ('id', 'locator', 'exam', 'role')}
        # Excel cell coordinates remain in the corpus; avoid sending duplicate cell/field text.
        record.update(text=json.dumps(f, ensure_ascii=False, default=str) if f else row['text'],
                      source_sha256=row['sha'], source_item_id=source_item_id(row),
                      use='few_shot' if row['role'] == 'example' else 'design_metadata' if row['role'] == 'metadata' else 'reference',
                      label_status='source_unverified',
                      full_question=bool((f.get('지문') or f.get('표')) and f.get('선지')),
                      answer_verified=meta.get('answer_verified', False),
                      transcription_verified=meta.get('transcription_verified', False))
        if meta.get('source'): record['source'] = meta['source']
        references.append(record)
    examples = [r['id'] for r in references if r['use'] == 'few_shot' and r['full_question']]
    return references, {'method': 'keyword retrieval + exact source labels + recent-year priority + year diversity',
                        'embedding_model': None, 'full_few_shot_ids': examples,
                        'unverified_answer_reference_ids': [r['id'] for r in references if r['full_question'] and not r['answer_verified']],
                        'design_metadata_ids': [r['id'] for r in references if r['use'] == 'design_metadata'],
                        'missing': [] if examples else ['해당 시험의 지문·선지 전문 few-shot 없음. 통계·분류 행을 전문 예시로 취급하지 말 것.'],
                        'selected': [{'id': r['id'], 'source_item_id': r['source_item_id'], 'use': r['use']} for r in references]}
