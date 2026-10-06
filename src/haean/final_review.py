"""Human checkpoint and read-only post-human review. Never rewrite a candidate."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .models import Draft, EditorialReview
from .pipeline import save


def candidate_sha(run):
    return hashlib.sha256((run / 'candidate.json').read_bytes()).hexdigest()


def human_checkpoint(run: Path, reviewer: str, expected_sha: str, note: str):
    if not reviewer.strip() or not note.strip(): raise ValueError('실제 검토자와 검토 기록이 필요합니다')
    if expected_sha != candidate_sha(run): raise ValueError('사람이 검토한 문항 해시가 현재 문항과 다릅니다')
    record = {'reviewer': reviewer, 'note': note, 'candidate_sha256': expected_sha,
              'recorded_at': datetime.now(timezone.utc).isoformat(), 'decision': 'reviewed_not_delivery_approved'}
    history = run / 'human-history'; history.mkdir(exist_ok=True)
    save(history / f'{len(list(history.glob("*.json"))):03}.json', record)
    save(run / 'human-checkpoint.json', record)
    save(run / 'status.json', {'state': 'awaiting_final_formal_review', 'human_approved': False,
                               'human_reviewed': True, 'candidate_sha256': expected_sha})
    return record


def prepare_final(run: Path):
    checkpoint = json.loads((run / 'human-checkpoint.json').read_text())
    sha = candidate_sha(run)
    if checkpoint['candidate_sha256'] != sha:
        raise ValueError('사람 검토 이후 문항이 바뀌었습니다. 현행 문항의 사람 검토가 필요합니다')
    status = json.loads((run / 'status.json').read_text())
    if status.get('state') == 'needs_revision': raise ValueError('미해결 수정 의견을 먼저 처리하세요')
    draft = Draft.model_validate_json((run / 'candidate.json').read_text())
    packet = {'candidate_sha256': sha, 'draft': draft.model_dump(), 'human_checkpoint': checkpoint,
              'brief': json.loads((run / 'brief.json').read_text()),
              'instructions': '사람 검토 후 최종 형식 점검이다. 오탈자·번호·기호·해설 형식·삭제한 문장 참조·정답표 동기화만 보고한다. 지문·조건·수치·선지·정답을 변경하지 않는다. 내용 오류가 보이면 사람에게 반환할 이슈로 기록한다.'}
    save(run / 'final-input.json', packet)
    save(run / 'final.schema.json', EditorialReview.model_json_schema())
    return packet


def final_review(run: Path, provider):
    packet = prepare_final(run)
    formal = provider.call('final-formal', packet['instructions'], packet, EditorialReview)
    quality = provider.call('final-quality', '문항 품질에 관한 별도 자문이다. 추론의 필요성, 오답 기능, 과도한 독해 부담, 유형 적합성을 근거와 함께 평가한다. 문항을 고치거나 형식 검토의 통과 여부를 대체하지 않는다. 실측 난도나 전문가 승인이라고 주장하지 않는다.', packet, EditorialReview)
    if candidate_sha(run) != packet['candidate_sha256']:
        raise ValueError('검토 중 문항 변경 감지. 결과를 현행 문항의 검토로 적용하지 않았습니다')
    ids = {i['id'] for i in packet['draft']['items']}
    if any(i.item_id not in ids for r in (formal, quality) for i in r.issues):
        raise ValueError('검토 결과에 알 수 없는 문항 ID가 있습니다')
    result = {'candidate_sha256': packet['candidate_sha256'], 'formal': formal.model_dump(),
              'quality_advice': quality.model_dump(), 'human_approved': False}
    save(run / 'final-review.json', result)
    save(run / 'final-usage.json', getattr(provider, 'usage', []))
    save(run / 'status.json', {'state': 'awaiting_human_final_decision', 'human_approved': False,
                               'candidate_sha256': packet['candidate_sha256'],
                               'formal_issue_count': len(formal.issues)})
    return result
