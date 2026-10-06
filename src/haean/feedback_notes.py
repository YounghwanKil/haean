"""Text feedback inbox for the native Haean improvement skill, never executable rules."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

SUBJECTS = {
    'leet': {'추리논증'},
    'psat5': {'언어논리', '자료해석', '상황판단'},
    'psat7': {'언어논리', '자료해석', '상황판단'},
    'team': set(),
}


def add_note(folder: Path, text: str, exam: str, subject: str | None, reviewer: str, origin='human'):
    if exam not in SUBJECTS or (subject and subject not in SUBJECTS[exam]):
        raise ValueError('피드백의 시험·과목 범위를 확인하세요')
    if not text.strip() or not reviewer.strip():
        raise ValueError('검토자와 피드백을 입력하세요')
    if origin not in {'human', 'model'}:
        raise ValueError('origin은 human 또는 model')
    identity = {'exam': exam, 'subject': subject, 'reviewer': reviewer.strip(), 'origin': origin, 'text': text}
    digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{digest[:24]}.json'
    note = {**identity, 'id': digest[:24], 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'untriaged',
            'kind': 'submitted_text_feedback', 'expert_verified': False}
    try:
        with path.open('x', encoding='utf-8') as handle:
            json.dump(note, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        duplicate = False
    except FileExistsError:
        note = json.loads(path.read_text(encoding='utf-8'))
        duplicate = True
    return {'note': note, 'path': str(path), 'duplicate': duplicate,
            'next': '$haean-evolve가 원문·문항 근거를 확인하고 평가 가능한 변경 후보로 연결합니다. 지침에 자동 삽입하지 않습니다.'}


def list_notes(folder: Path, exam=None, subject=None, limit=12):
    if exam and exam not in SUBJECTS:
        raise ValueError('알 수 없는 시험')
    if subject and exam and subject not in SUBJECTS[exam]:
        raise ValueError('피드백의 시험·과목 범위를 확인하세요')
    if not 1 <= limit <= 100:
        raise ValueError('limit는 1–100')
    notes = [json.loads(p.read_text(encoding='utf-8')) for p in folder.glob('*.json')]
    notes = [n for n in notes if (not exam or n['exam'] in {exam, 'team'}) and
             (not subject or n['subject'] in {None, subject})]
    return sorted(notes, key=lambda n: (n['created_at'], n['id']), reverse=True)[:limit]
