"""Bind evaluation to the original request, independently of candidate metadata."""
from __future__ import annotations

from copy import deepcopy
import math

from .models import Brief, Draft


EVALUATION_INPUT_CONTRACT_VERSION = "per-item-requirements-v1"
REQUIREMENTS_POLICY = (
    "item_requirements는 원요청 기준이며 배정이 있으면 공통 brief의 유형·난도·소재보다 해당 ID 배정을 우선한다. "
    "draft의 메타데이터는 출제자의 주장으로 요청을 덮어쓰지 않는다. "
    "원목표 준수와 문면상 실질 난도 판단을 구별한다. answer_target은 요구/정답 근거가 아니다."
)
_REQUIRED = ("id", "item_type", "difficulty", "topic")
_TEXT = ("domain", "cognitive_task", "response_format", "calculation_load", "special_design")
_OPTIONAL = (*_TEXT, "shared_passage_id", "time", "expected_time_minutes",
             "table_design", "authoring_notes", "target_passage_characters", "graph_design",
             "composition_resolution")


def _text(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: 비어 있지 않은 문자열이 필요합니다")


def _json_value(value, path):
    """Accept structured design data without accepting arbitrary Python objects."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, list):
        for child in value:
            _json_value(child, path)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for child in value.values():
            _json_value(child, path)
        return
    raise ValueError(f"{path}: JSON 형식의 설계 데이터가 필요합니다")


def _optional_value(key, value, path):
    if key in _TEXT and not isinstance(value, str):
        raise ValueError(f"{path}: 문자열이 필요합니다")
    if key == "shared_passage_id" and value is not None:
        _text(value, path)
    if key in ("time", "expected_time_minutes"):
        if key == "time" and isinstance(value, str):
            _text(value, path)
        elif type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{path}: 양의 유한 시간이 필요합니다")
    if key == "target_passage_characters" and (type(value) is not int or value <= 0):
        raise ValueError(f"{path}: 양의 정수 글자 수가 필요합니다")
    if key == "authoring_notes" and not (isinstance(value, str) or (
            isinstance(value, list) and all(isinstance(note, str) for note in value))):
        raise ValueError(f"{path}: 문자열 또는 문자열 목록이 필요합니다")
    if key == "table_design" and not isinstance(value, (str, dict)):
        raise ValueError(f"{path}: 문자열 또는 설계 객체가 필요합니다")
    if key in ("graph_design", "composition_resolution") and not isinstance(value, dict):
        raise ValueError(f"{path}: 설계 객체가 필요합니다")
    _json_value(value, path)


def _route_matches(data, brief, path):
    for key in ("exam", "subject"):
        if key in data and data[key] != getattr(brief, key):
            raise ValueError(f"{path}.{key}: brief와 시험·과목이 다릅니다")


def build_evaluation_input(brief: Brief | dict, draft: Draft | dict,
                           review: dict | None = None, context: dict | None = None) -> dict:
    """Keep requests and candidates separate; fail closed on broken assignments.

    Only an absent ``exam_assignment`` permits common-Brief requirements. An
    explicitly empty or incomplete assignment must never borrow candidate fields.
    The output preserves candidate order even when the assignment order differs.
    """
    if not isinstance(brief, (Brief, dict)) or not isinstance(draft, (Draft, dict)):
        raise ValueError("brief와 draft는 해당 모델 또는 객체여야 합니다")
    brief_data = deepcopy(brief.model_dump() if isinstance(brief, Brief) else brief)
    draft_data = deepcopy(draft.model_dump() if isinstance(draft, Draft) else draft)
    request = Brief.model_validate(brief_data)
    candidate = Draft.model_validate(draft_data)
    if context is not None and not isinstance(context, dict):
        raise ValueError("context는 객체여야 합니다")
    context = {} if context is None else context
    if review is not None and not isinstance(review, dict):
        raise ValueError("review는 객체 또는 null이어야 합니다")
    if "brief" in context and Brief.model_validate(context["brief"]) != request:
        raise ValueError("context.brief: 입력 brief와 다릅니다")
    _route_matches(context, request, "context")
    ids = [item.id for item in candidate.items]
    for item_id in ids:
        _text(item_id, "draft.items.id")
    if len(set(ids)) != len(ids):
        raise ValueError("draft 문항 ID 중복")
    if len(ids) != request.count:
        raise ValueError("draft 문항 수가 brief.count와 다릅니다")

    source = "context.exam_assignment" if "exam_assignment" in context else "brief"
    assigned = {}
    if source == "context.exam_assignment":
        slots = context["exam_assignment"]
        if not isinstance(slots, list) or not slots:
            raise ValueError("context.exam_assignment: 비어 있지 않은 배정 목록이 필요합니다")
        for index, slot in enumerate(slots):
            path = f"context.exam_assignment[{index}]"
            if not isinstance(slot, dict):
                raise ValueError(f"{path}: 배정 객체가 필요합니다")
            for key in _REQUIRED:
                _text(slot.get(key), f"{path}.{key}")
            if slot["id"] in assigned:
                raise ValueError("exam_assignment 문항 ID 중복")
            _route_matches(slot, request, path)
            row = {key: deepcopy(slot[key]) for key in _REQUIRED}
            for key in _OPTIONAL:
                if key in slot:
                    _optional_value(key, slot[key], f"{path}.{key}")
                    row[key] = deepcopy(slot[key])
            assigned[slot["id"]] = row
        if set(assigned) != set(ids):
            raise ValueError("exam_assignment와 draft 문항 ID 누락·추가 또는 개수 불일치")

    requirements = []
    for item_id in ids:
        row = assigned[item_id] if assigned else {
            "id": item_id, "item_type": request.item_type,
            "difficulty": request.difficulty, "topic": request.topic}
        requirements.append({**row, "exam": request.exam, "subject": request.subject, "source": source})
    return {"brief": brief_data, "draft": draft_data, "review": deepcopy(review),
            "input_contract_version": EVALUATION_INPUT_CONTRACT_VERSION,
            "requirements_source": source, "requirements_policy": REQUIREMENTS_POLICY,
            "item_requirements": requirements}
