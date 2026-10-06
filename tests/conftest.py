import pytest
from haean.models import Draft, Brief


@pytest.fixture
def brief():
    return Brief(exam="leet", subject="추리논증", item_type="조건 추론", topic="예약 규칙")


@pytest.fixture
def draft():
    return Draft.model_validate({"design_summary": "테스트 전용 간단 조건 추론", "items": [{
        "id": "TEST-001", "subject": "추리논증", "item_type": "조건 추론", "domain": "규범",
        "topic": "예약 규칙", "difficulty": "하", "difficulty_basis": "테스트용 단일 조건",
        "stem": "반드시 참인 것은?", "passage": "예약이 승인되면 문자가 발송된다. 민수의 예약이 승인되었다.",
        "statements": [], "tables": [],
        "options": [{"number": n, "text": t} for n, t in enumerate([
            "민수에게 문자가 발송되었다.", "모든 예약이 승인되었다.", "문자가 발송되면 예약이 승인된다.",
            "다른 사람에게 문자가 발송되지 않았다.", "승인되지 않은 예약에는 문자가 발송되지 않는다."], 1)],
        "answer": 1, "judgments": [{"target": str(n), "verdict": "참" if n == 1 else "판단불가",
            "evidence": "승인되면 발송", "explanation": "전건 긍정" if n == 1 else "추가 조건이 없다.", "trap": "역 또는 범위 확대"} for n in range(1, 6)],
        "explanation": "예약 승인에서 문자 발송이 따른다.", "commentary": "조건문의 방향", "cognitive_task": "전건 긍정",
        "essential_conditions": ["승인 → 발송"], "originality": "시스템 테스트 전용. 납품 예제가 아님.",
        "source_ids": ["source-1"], "calculations": [], "shared_passage_id": None}]})
