"""Human checkpoint and read-only post-human review. Never rewrite a candidate."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .models import Draft, EditorialReview
from .pipeline import save
from .evaluation_input import build_evaluation_input


def candidate_sha(run):
    return hashlib.sha256((run / 'candidate.json').read_bytes()).hexdigest()


def _requirements_sources(run):
    return {name: hashlib.sha256((run / name).read_bytes()).hexdigest()
            if (run / name).is_file() else None for name in ('brief.json', 'context.json')}


def _load_status(run, sha):
    status = json.loads((run / 'status.json').read_text())
    if not isinstance(status, dict) or not isinstance(status.get('state'), str) or not status['state']:
        raise ValueError('문항 검토 상태가 불완전합니다. 현행 문항의 검토 상태를 확인하세요')
    if 'candidate_sha256' in status and status['candidate_sha256'] != sha:
        raise ValueError('검토 상태의 문항 해시가 현재 문항과 다릅니다. 현행 문항을 다시 검토하세요')
    return status


def _final_status(run, sha):
    status = _load_status(run, sha)
    if status['state'] == 'needs_revision' or status.get('errors'):
        raise ValueError('미해결 수정 의견을 먼저 처리하세요')
    if status['state'] not in {'awaiting_final_formal_review', 'awaiting_human_final_decision'}:
        raise ValueError('사전 검토가 완료되지 않았습니다. 독립 검토와 사람 검토 상태를 확인하세요')
    return status


def human_checkpoint(run: Path, reviewer: str, expected_sha: str, note: str):
    if not reviewer.strip() or not note.strip(): raise ValueError('실제 검토자와 검토 기록이 필요합니다')
    if expected_sha != candidate_sha(run): raise ValueError('사람이 검토한 문항 해시가 현재 문항과 다릅니다')
    status = _load_status(run, expected_sha)
    record = {'reviewer': reviewer, 'note': note, 'candidate_sha256': expected_sha,
              'recorded_at': datetime.now(timezone.utc).isoformat(), 'decision': 'reviewed_not_delivery_approved'}
    history = run / 'human-history'; history.mkdir(exist_ok=True)
    save(history / f'{len(list(history.glob("*.json"))):03}.json', record)
    save(run / 'human-checkpoint.json', record)
    # A human review record does not resolve outstanding review work or errors.
    if status['state'] in {'awaiting_human_review', 'awaiting_final_formal_review', 'awaiting_human_final_decision'} and not status.get('errors'):
        status['state'] = 'awaiting_final_formal_review'
    status.update(human_approved=False, human_reviewed=True, candidate_sha256=expected_sha)
    save(run / 'status.json', status)
    return record


def prepare_final(run: Path):
    checkpoint = json.loads((run / 'human-checkpoint.json').read_text())
    sha = candidate_sha(run)
    if checkpoint['candidate_sha256'] != sha:
        raise ValueError('사람 검토 이후 문항이 바뀌었습니다. 현행 문항의 사람 검토가 필요합니다')
    _final_status(run, sha)
    source_hashes = _requirements_sources(run)
    draft = Draft.model_validate_json((run / 'candidate.json').read_text())
    brief = json.loads((run / 'brief.json').read_text())
    context = json.loads((run / 'context.json').read_text()) if source_hashes['context.json'] else None
    evaluation_input = build_evaluation_input(brief, draft, context=context)
    packet = {'candidate_sha256': sha, 'draft': draft.model_dump(), 'human_checkpoint': checkpoint,
              **{key: value for key, value in evaluation_input.items() if key not in {'draft', 'review'}},
              'requirements_source_sha256': source_hashes,
              'instructions': '사람 검토 후 최종 형식 점검이다. 오탈자·번호·기호·해설 형식·삭제한 문장 참조·정답표 동기화만 보고한다. 지문·조건·수치·선지·정답을 변경하지 않는다. 내용 오류가 보이면 사람에게 반환할 이슈로 기록한다.'}
    if source_hashes != _requirements_sources(run) or sha != candidate_sha(run):
        raise ValueError('최종 검토 준비 중 문항·요청 명세가 바뀌었습니다')
    save(run / 'final-input.json', packet)
    save(run / 'final.schema.json', EditorialReview.model_json_schema())
    return packet


def final_review(run: Path, provider):
    packet = prepare_final(run)
    formal = provider.call('final-formal', packet['instructions'], packet, EditorialReview)
    if _requirements_sources(run) != packet['requirements_source_sha256']:
        raise ValueError('최종 검토 중 요청 명세가 바뀌었습니다. 새 입력으로 다시 검토하세요')
    quality = provider.call('final-quality', '문항 품질에 관한 별도 자문이다. 추론의 필요성, 오답 기능, 과도한 독해 부담, 유형 적합성을 근거와 함께 평가한다. 문항을 고치거나 형식 검토의 통과 여부를 대체하지 않는다. 실측 난도나 전문가 승인이라고 주장하지 않는다.', packet, EditorialReview)
    if candidate_sha(run) != packet['candidate_sha256']:
        raise ValueError('검토 중 문항 변경 감지. 결과를 현행 문항의 검토로 적용하지 않았습니다')
    if _requirements_sources(run) != packet['requirements_source_sha256']:
        raise ValueError('최종 검토 중 요청 명세가 바뀌었습니다. 결과를 현행 문항에 적용하지 않았습니다')
    ids = {i['id'] for i in packet['draft']['items']}
    if any(i.item_id not in ids for r in (formal, quality) for i in r.issues):
        raise ValueError('검토 결과에 알 수 없는 문항 ID가 있습니다')
    status = _final_status(run, packet['candidate_sha256'])
    result = {'candidate_sha256': packet['candidate_sha256'], 'formal': formal.model_dump(),
              'input_contract_version': packet['input_contract_version'],
              'requirements_source_sha256': packet['requirements_source_sha256'],
              'quality_advice': quality.model_dump(), 'human_approved': False}
    save(run / 'final-review.json', result)
    save(run / 'final-usage.json', getattr(provider, 'usage', []))
    status.update(state='awaiting_human_final_decision', human_approved=False,
                  candidate_sha256=packet['candidate_sha256'], formal_issue_count=len(formal.issues))
    save(run / 'status.json', status)
    return result
