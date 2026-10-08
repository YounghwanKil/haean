"""Advisory production context, never an evaluator or an automatic rewrite."""
from __future__ import annotations


def editorial_plan(brief):
    if brief.exam != 'leet' or brief.subject != '추리논증':
        return None
    return {
        'scope': 'leet/추리논증',
        'mode': 'advisory',
        'instruction_profile': 'leet_editorial',
        'order': ['소재·판단 구조 대조', '핵심 추론·오답 기능', '발문·표지 호응',
                  '조건 보존·용어 일관성', '윤문 후 전 선지·해설 재검증', '실제 양식 확인'],
        'record_in': {'writer': 'design_summary', 'editor': 'issues와 summary'},
        'decisions': ['참고 자료의 논점과 새 판단 구조의 차이', '발문 선택과 보기 판단 방식의 근거',
                      '삭제·유지·선지 이관한 조건과 이관 위치', '대안 선택 및 연동 수정의 범위'],
        'automatic_rewrite': False,
        'score_effect': None,
    }


def exam_editorial_context(plan, group):
    """Expose other bundles' design briefs without author answers or raw sources.

    A slot overview is evidence for planning, not proof of semantic duplication.
    Preserve the frozen assignments; report conflicts for the assembler instead.
    """
    if plan['exam'] != 'leet' or plan['subject'] != '추리논증':
        return None
    keys = ('id', 'number', 'domain', 'topic', 'item_type', 'cognitive_task',
            'special_design', 'shared_passage_id')
    return {
        'mode': 'advisory',
        'assigned_ids': [s['id'] for s in group],
        'slot_overview': [{k: s[k] for k in keys if k in s} for s in plan['slots']],
        'comparison': '소재와 조건 관계·판단 구조를 함께 비교한다.',
        'assignment_policy': '배정은 유지하고 충돌 문항 ID와 재구성안을 design_summary에 기록한다.',
        'first_slot_preference': ('1번은 규범 견해·주장 중심을 우선 검토한다. 배정과 충돌하면 알리고 '
                                  '임의로 바꾸지 않는다. 분량은 실제 양식에서 확인한다.'),
        'coverage': '배정표 대조이며 완성 문항 간 중복 검토를 대신하지 않는다.',
    }
