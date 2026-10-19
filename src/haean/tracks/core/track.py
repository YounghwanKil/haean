"""트랙(과목별 생성 에이전트) 기반 클래스와 출제 명세.

트랙 하나 = 과목 하나: 어휘(facet), 세트 정책, 문항 수, 조판 프로필, 단계별 지침(rules/), 추가 검사.
엔진(pipeline·check·references)은 트랙 객체를 통해서만 과목 규칙을 쓴다. 엔진에는 과목 이름이 없다.
"""
from __future__ import annotations

from importlib.resources import files
from typing import Literal

from pydantic import Field

from ...models import StrictModel

STAGE_RULES = ("material", "design", "writer", "editor")
FOUNDATION_VERSION = "haean-track-foundation-v1"


class Brief(StrictModel):
    track: str
    grade: Literal[5, 7] | None = None      # PSAT 급수
    area: str                                # 내용 영역(대분류 — 트랙 어휘)
    area_detail: str = ""                    # 내용 영역 세부(해설 표기 '인문(철학)'의 괄호 안). 트랙이 목록을 두면 출제 단계에서 정한다
    item_type: str                           # 문항 유형
    item_format: str                         # 응답 형식
    discourse: str                           # 서술 형식
    topic: str = ""                          # 비우면 소재 탐색 단계가 정한다
    difficulty: Literal["하", "중", "상"] = "중"
    count: int = Field(default=1, ge=1, le=4)
    set: bool = False                        # 공통지문 세트로 쓸지
    ids: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)   # 회차의 다른 문항 소재·판단 구조 요약


MIXABLE = ("item_type", "item_format")   # 세트 명세에서 '혼합'을 받을 수 있는 facet


class Track:
    name = ""
    label = ""
    # 조판 프로필: 급수별(급수 없는 과목은 None 키). 프로필이 아직 없으면 조판 검사를 건너뛴다
    typeset_profiles: dict = {}
    # facet 어휘. None이면 자유 입력(정제 데이터에서 어휘가 정해지면 목록으로 고정)
    vocab: dict[str, list[str] | None] = {"area": None, "item_type": None, "item_format": None, "discourse": None}
    set_size = 0                 # 0: 세트 없음, n: n문항 세트
    set_required = False
    set_mixed_types = False      # True면 세트 명세의 item_type·item_format='혼합', 문항마다 어휘 안에서 고른다
    grades: tuple = ()           # PSAT: (5, 7)
    middot = "·"                 # 가운뎃점 글리프. LEET는 · (U+00B7), PSAT은 ㆍ (U+318D, 기출·인사처 표기)
    year_label = "학년도"         # 참고 기출 표기의 연도 단위 — '2027학년도 9번'(LEET) · '2026년 14번'(PSAT 공식 표기 '2026년도 5급 공채')
    style_note = ""              # 윤문 기준선에 붙일 과목 표기 메모(발언 라벨·블록 관행) — haean tools style
    polish_note = ""             # 윤문 기준서 끝에 붙일 과목 메모(기준서 위치·조문형·인물 표기 등) — haean tools style 가 docs/<트랙>/윤문기준서.md 에 쓴다
    diagram_options = False      # True면 원고 `설계.도식선지`(5개 구조)를 그림 선지의 argument 그림으로 되읽는다(추리논증 논증 구조 도식)
    area_details: dict | None = None   # 내용 영역 세부 목록 {대분류: [세부…]} — 있으면 세부 필수([]면 붙이지 않음)
    comment_required = True      # 해설 논평(제목 + 출처 문장)을 문항마다 요구(언어이해는 세트 해설이라 끈다)

    def profile(self, grade=None):
        return self.typeset_profiles.get(grade)

    def status(self) -> dict:
        """노출된 기반 기능과 아직 연결하지 않은 검토·생성 기능을 구분한다."""
        return {
            "version": FOUNDATION_VERSION,
            "scope": "foundation",
            "track": self.name,
            "label": self.label,
            "grades": list(self.grades),
            "generation_connected": False,
            "independent_review_connected": False,
            "typeset_connected": False,
            "composition_available": False,
            "supported_figure_kinds": ["argument", "bar", "line"],
            "image_file_supported": False,
            "review_lexicon": "not_imported_not_applied" if self.name == "leet_reasoning" else "not_applicable",
            "designless_manuscript_type_mapping": "unavailable_without_composition_rules" if self.grades else "not_exposed",
            "quality_improvement_verified": False,
            "notes": ["문항 스키마는 기존 Draft와 다릅니다. 기존 run의 후보를 자동 변환하지 않습니다.",
                      "과목 규칙은 후속 출제·검토 연결의 참고 지침이며 현재 명령은 모델을 호출하지 않습니다.",
                      "기존 위키·누적 생성물 구조 검토·동결 평가 경로를 유지합니다."],
        }

    # ── 명세
    def max_items(self, grade=None) -> int:
        return 40

    def check_brief(self, b: Brief) -> list[str]:
        errors = []
        if b.track != self.name:
            errors.append(f"트랙 {b.track} ≠ {self.name}")
        for facet in ("area", "item_type", "item_format", "discourse"):
            if not getattr(b, facet).strip():
                errors.append(f"{facet}는 비울 수 없습니다")
        for facet, allowed in self.vocab.items():
            if facet in MIXABLE and self.set_mixed_types and b.set and getattr(b, facet) == "혼합":
                continue
            if allowed is not None and getattr(b, facet) not in allowed:
                errors.append(f"{facet} '{getattr(b, facet)}'는 이 트랙 어휘({' / '.join(allowed)})에 없습니다")
        from .areas import detail_issues
        errors += detail_issues(self, b.area, b.area_detail)
        if self.grades and b.grade not in self.grades:
            errors.append(f"급수(grade)는 {self.grades} 중 하나")
        if not self.grades and b.grade is not None:
            errors.append("이 트랙은 급수를 쓰지 않습니다")
        if b.set and not self.set_size:
            errors.append(f"{self.label}은 공통지문 세트를 출제하지 않습니다")
        if b.set and b.count != self.set_size:
            errors.append(f"세트는 {self.set_size}문항 단위입니다")
        if self.set_required and not b.set:
            errors.append(f"{self.label}은 {self.set_size}문항 지문 세트로만 출제합니다")
        if b.ids and len(b.ids) != b.count:
            errors.append("ids 수가 count와 다릅니다")
        if any(not value.strip() or value != value.strip() for value in b.ids):
            errors.append("문항 ID는 공백만이거나 앞뒤 공백을 포함할 수 없습니다")
        if len({value.strip() for value in b.ids}) != len(b.ids):
            errors.append("문항 ID 중복")
        return errors

    # ── 지침
    def rule(self, stage: str) -> str:
        if stage not in (*STAGE_RULES, "blind"):
            raise ValueError("지원하지 않는 규칙 단계: " + stage)
        core = files("haean.tracks.core").joinpath("rules")
        own = files(f"haean.tracks.{self.name}").joinpath("rules")
        text = core.joinpath("common.md").read_text(encoding="utf-8")
        if stage == "blind":
            return core.joinpath("blind.md").read_text(encoding="utf-8")
        return text + "\n" + own.joinpath(stage + ".md").read_text(encoding="utf-8")

    def rule_files(self):
        out = {}
        for pkg in ("haean.tracks.core", f"haean.tracks.{self.name}"):
            for p in files(pkg).joinpath("rules").iterdir():
                if p.name.endswith(".md"):
                    out[f"{pkg}/{p.name}"] = p.read_bytes()
        return out

    # ── 참고 사례: 단계별로 무엇을 찾나 (지정한 facet은 완화하지 않는다)
    def stage_queries(self, b: Brief, stage: str) -> dict:
        from .references import RefQuery
        g = {"grade": b.grade} if self.grades else {}
        if stage == "design":
            item_type = None if b.item_type == "혼합" else b.item_type
            return {"design_refs": RefQuery(track=self.name, role="item", area=b.area, item_type=item_type,
                                            item_format=None if b.item_format == "혼합" else b.item_format, text=b.topic, k=4, **g)}
        if stage == "write":
            return {"style_refs": RefQuery(track=self.name, role="item", discourse=b.discourse, area=b.area, k=3, **g)}
        if stage == "edit":
            return {"review_cases": RefQuery(track=self.name, role="case", area=b.area, k=4, **g)}
        return {}

    # ── 트랙 추가 검사: (errors, warnings)
    def check_item(self, item, brief: Brief) -> tuple[list[str], list[str]]:
        return [], []

    # ── 조판 원고 되읽기(manuscript_import): 원고 한 문항 → (내용 영역, 문항 유형, 응답 형식). 트랙마다 원고의 어느 키가 기준인지 다르다
    def import_facets(self, q: dict) -> tuple[str, str, str]:
        d, hs = q.get("설계") or {}, q.get("해설") or {}
        return (d.get("내용영역") or hs.get("내용영역") or "", d.get("유형") or hs.get("문항유형") or "",
                "합답형" if q.get("보기") else "일반")
