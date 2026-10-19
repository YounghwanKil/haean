"""내용영역 표기 — '대분류(세부)'.

해설지의 내용영역 칸은 대분류만이 아니라 세부 분야까지 찍는다(추리논증 해설 양식 메모:
규범(법) / 인문(법,철학,논리,역사) / 사회(경제,경영) / 논리학·수학 / 과학기술(물리/화학/생명/지구) → '인문(철학)', '과학기술(생명)' …).
트랙 어휘(검색·분배·표절 셀)는 대분류(`area`)로, 세부는 `area_detail`로 따로 들고, 원고·해설지에는 둘을 합친 표기를 쓴다.
세부는 출제(설계) 단계에서 정한다 — 생성틀은 내용 설계가, 자유 형식은 명세(Brief.area_detail)가.
"""
from __future__ import annotations

import re

LABEL = re.compile(r"^\s*([^()（）]+?)\s*[(（]\s*([^()（）]+?)\s*[)）]\s*$")


def split(label) -> tuple[str, str]:
    """'인문(철학)' → ('인문', '철학'), '논리학·수학' → ('논리학·수학', '')."""
    s = str(label or "").strip()
    m = LABEL.match(s)
    return (m.group(1), m.group(2)) if m else (s, "")


def base(label) -> str:
    return split(label)[0]


def label(area: str, detail: str = "") -> str:
    area, detail = str(area or "").strip(), str(detail or "").strip()
    return f"{area}({detail})" if area and detail else area


def detail_issues(track, area: str, detail: str) -> list[str]:
    """트랙의 세부 옵션(Track.area_details — 양식 메모 그대로)과 대조. 세부 없음(대분류만)은 늘 허용. 목록이 없는 트랙은 보지 않는다."""
    table = getattr(track, "area_details", None)
    if not table or area not in table:
        return []
    allowed = table[area]
    if not allowed:
        return [f"내용영역 '{area}'은 세부 분야를 붙이지 않습니다('{label(area, detail)}')"] if detail else []
    if detail and detail not in allowed:
        return [f"내용영역 '{label(area, detail)}'은 양식 옵션({' / '.join(label(area, d) for d in allowed)} / {area})에 없습니다 — 괄호로 포섭되지 않으면 '{area}'만 쓴다"]
    return []


def facet(track_name: str, value) -> str:
    """원고 해설의 내용영역 표기 → 트랙 어휘(대분류). 세부 목록이 없는 트랙(상황판단 '법·제도(실제)' 등)은 그대로."""
    from .. import get
    try:
        has_details = bool(get(track_name).area_details)
    except Exception:
        has_details = False
    return base(value) if has_details and value else (value or "")
