"""모든 트랙이 공유하는 문항 모델.

이 문항 모델은 기존 haean.models.Draft와 별도인 트랙 기반 스키마다.
현재 foundation은 조판기와 연결하지 않으며 기존 Figure의 argument/bar/line만 받는다.
신규본의 image/path 그림 파일은 지원하지 않는다. 기존 문항의 묵시 변환에도 쓰지 않는다.
- 지문 = 블록 목록(문단 안 줄바꿈 없음 — 줄은 조판기가 어절 단위로 정하고 넘치는 줄은 자간으로 눌러 넣어 한글이 같은 자리에서 접게 한다)
- 해설 = 조판기 '해설'(제재·난이도·논평·정오판단·선지판단)
설계·참고·계산 기록은 조판에 나가지 않는 제작 기록이다.
트랙별 제약(어휘·세트·계산 필수 등)은 각 트랙의 Track 클래스가 검사한다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ...models import Figure, StrictModel

BlockKind = Literal["문단", "소제목", "발언", "조건", "나열", "실험", "원리", "목록",
                    "조문", "항", "호", "의안", "표", "그림", "상자", "목", "주석"]
LABELLED = {"발언", "조건", "실험", "목록", "조문", "항", "호", "의안", "목"}
Mark = Literal["○", "×"]


class Cell(StrictModel):
    text: str
    colspan: int = Field(default=1, ge=1)
    rowspan: int = Field(default=1, ge=1)


class Block(StrictModel):
    """지문 블록 하나."""
    kind: BlockKind
    label: str = ""                 # 발언 '갑', 조건 '1', 조문 '제1조(목적)', 항 '②', 호 '1', 의안 '1', 목록 '1'
    text: str = ""                  # 표·그림이 아니면 필수. 줄바꿈 금지
    rows: list[list[Cell]] = Field(default_factory=list)   # 표: 합친 칸에 덮인 자리는 행에서 뺀다
    title: str = ""                 # 표 제목 '<표> …' · 그림 제목 '<그림> …' · 상자 제목 '상황'(PSAT)
    unit: str = ""                  # 표 단위 '(단위: …)'
    note: str = ""                  # 표 주석 '※ …'
    header_row: bool = False        # 표 첫 행 굵게
    col_widths: list[float] = Field(default_factory=list)   # 표 열 폭 비율(PSAT)
    align: list[Literal["L", "C", "R"]] = Field(default_factory=list)   # 표 열 정렬(PSAT)
    figure_id: str = ""             # 그림: Item.figures 의 id
    width_pt: float = 0             # 그림 폭(0이면 자동)
    children: list["Block"] = Field(default_factory=list)   # 상자 안 블록(PSAT <상  황> 등)

    @model_validator(mode="after")
    def shape(self):
        if self.kind == "상자":
            if not self.children:
                raise ValueError("상자 블록은 children이 필요합니다")
            if any(c.kind == "상자" for c in self.children):
                raise ValueError("상자 안에 상자를 넣지 않습니다")
        elif self.kind == "표":
            if not self.rows:
                raise ValueError("표 블록은 rows가 필요합니다")
        elif self.kind == "그림":
            if not self.figure_id:
                raise ValueError("그림 블록은 figure_id가 필요합니다")
        else:
            if not self.text.strip():
                raise ValueError(f"{self.kind} 블록 글이 비었습니다")
            if "\n" in self.text:
                raise ValueError("블록 안에서 줄을 바꾸지 않습니다. 블록을 나누세요")
        if self.kind in LABELLED and not self.label.strip():
            raise ValueError(f"{self.kind} 블록은 label이 필요합니다")
        return self


Block.model_rebuild()


class Statement(StrictModel):
    """<보기> 항목 하나. 'ㄱ.' 머리 없이."""
    text: str
    figure_id: str = ""


class Choice(StrictModel):
    """선지 하나. '①' 머리 없이. 그림 선지면 figure_id."""
    text: str = ""
    figure_id: str = ""
    width_pt: float = 0

    @model_validator(mode="after")
    def present(self):
        if not self.text.strip() and not self.figure_id:
            raise ValueError("선지는 글이나 그림이 필요합니다")
        return self


class Judge(StrictModel):
    """정오판단 하나. 〈보기〉 문항은 ㄱ·ㄴ·ㄷ 순, 선지는 ①~⑤ 순."""
    mark: Mark
    explanation: list[str] = Field(min_length=1)   # 문단 목록. 첫 문단에 조판기가 ↳ 를 붙인다
    trap: str = ""                                 # 제작 기록: 이 보기·선지가 노린 오개념(조판 안 함)


class Solution(StrictModel):
    topic: str = Field(min_length=1)               # 제재 / 주제
    level: int = Field(ge=1, le=5)                 # 난이도 ★ 수
    comment_title: str = ""                        # 출제자의 논평 제목(있으면 큰 표)
    comment: list[str] = Field(default_factory=list)
    statement_judgments: list[Judge] = Field(default_factory=list)
    option_judgments: list[Judge] = Field(default_factory=list)


class Design(StrictModel):
    """설계 기록(조판 안 함)."""
    core_judgment: str = Field(min_length=1)
    answer_condition: str = Field(min_length=1)
    distractor_paths: list[str] = Field(min_length=1)
    bypass_check: str = Field(min_length=1)
    reference_use: str


class Calculation(StrictModel):
    label: str
    expression: str                 # 숫자와 + - * / ( ) 만
    expected: str                   # 반올림 전 정확값(분수 가능)
    unit: str
    evidence: str                   # 표·그래프의 어느 값인지


class Item(StrictModel):
    id: str
    set_id: str = ""                # 공통지문 세트 묶음(트랙이 허용할 때만)
    area: str                       # 내용 영역
    area_detail: str = ""           # 내용 영역 세부(해설 표기 '대분류(세부)')
    item_type: str                  # 문항 유형
    item_format: str                # 응답 형식(합답형 등)
    discourse: str                  # 서술 형식(평서문·대화형 등)
    difficulty: Literal["하", "중", "상"]
    topic: str
    stem: str = Field(min_length=1)
    passage: list[Block] = Field(min_length=1)
    own_blocks: list[Block] = Field(default_factory=list)   # 세트 문항 고유 블록(<상황>·<보고서> 등). 공통 지문(passage) 뒤에 붙는다. 세트가 아니면 비운다
    statements: list[Statement] = Field(default_factory=list)
    options: list[Choice] = Field(min_length=5, max_length=5)
    option_layout: Literal["", "2열", "1열"] = ""
    flow: Literal["", "이어붙이기", "새단"] = ""     # PSAT 배치: 앞 단에 이어 놓기 / 늘 새 단
    answer: int = Field(ge=1, le=5)
    solution: Solution
    design: Design
    essential_conditions: list[str]
    reference_ids: list[str]
    calculations: list[Calculation] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self):
        texts = [c.text.strip() for c in self.options if not c.figure_id]
        if len(set(texts)) != len(texts):
            raise ValueError("선지 중복")
        if 0 < sum(bool(c.figure_id) for c in self.options) < 5:
            raise ValueError("그림 선지와 글 선지를 섞지 않습니다")
        known = {f.id for f in self.figures}
        used = [b.figure_id for b in self.passage + self.own_blocks if b.kind == "그림"]
        used += [c.figure_id for b in self.passage + self.own_blocks if b.kind == "상자" for c in b.children if c.kind == "그림"]
        used += [s.figure_id for s in self.statements if s.figure_id]
        used += [c.figure_id for c in self.options if c.figure_id]
        missing = sorted(set(used) - known)
        if missing:
            raise ValueError("figures에 없는 그림을 가리킵니다: " + ", ".join(missing))
        return self


class SetInfo(StrictModel):
    """공통지문 세트 머리. 지문은 세트 문항들의 passage(모두 같아야 함)를 쓴다."""
    set_id: str
    guide: str = ""                 # 안내('다음 글을 읽고 물음에 답하시오.' — 비우면 조판기 기본값)
    summary: list[str] = Field(default_factory=list)   # 언어이해 해설지 지문 총평


class Draft(StrictModel):
    design_summary: str
    items: list[Item] = Field(min_length=1, max_length=4)
    sets: list[SetInfo] = Field(default_factory=list)


# ── 표기 ─────────────────────────────────────────────────────────────

HEADS = "ㄱㄴㄷㄹㅁ"
CIRCLED = "①②③④⑤"


def block_line(b: Block) -> str:
    k, lab, t = b.kind, b.label.strip(), b.text.strip()
    return {"문단": t, "소제목": t, "발언": f"{lab} : {t}", "조건": f"◦ 조건 {lab} : {t}", "나열": f"◦ {t}",
            "실험": f"실험 {lab} : {t}", "원리": f"[원리] {t}", "목록": f"({lab}) {t}", "조문": f"{lab} {t}",
            "항": f"{lab} {t}", "호": f"{lab}. {t}", "의안": f"<의안 {lab}> {t}", "목": f"{lab}. {t}",
            "주석": f"※ {t}"}.get(k, "")


def passage_text(item: Item) -> str:
    """사람·모델이 읽는 지문(세트 문항은 공통 지문 + 고유 블록). 표는 ' | ' 행, 그림은 자리 표시, 상자는 제목 + 안쪽."""
    return blocks_text(item.passage + item.own_blocks)


def blocks_text(blocks) -> str:
    out = []
    for b in blocks:
        if b.kind == "상자":
            out.append(f"<{b.title}>" if b.title else "[상자]")
            out.append(blocks_text(b.children))
            continue
        if b.kind == "표":
            out += [x for x in (b.title, b.unit) if x]
            out += [" | ".join(c.text for c in r) for r in b.rows]
            out += [b.note] if b.note else []
        elif b.kind == "그림":
            out.append(f"[그림 {b.figure_id}]" + (f" {b.title}" if b.title else ""))
        else:
            out.append(block_line(b))
    return "\n".join(out)


def public_item(item: Item) -> dict:
    """블라인드 풀이용 공개 문항. 정답·해설·설계·참고·계산은 넣지 않는다."""
    figures = []
    for f in item.figures:
        data = f.model_dump()
        data["layout_note"] = ""
        if data["kind"] == "argument":
            data["note"] = ""
        figures.append(data)
    return {"id": item.id, "set_id": item.set_id, "stem": item.stem, "passage": passage_text(item),
            "statements": [f"{HEADS[k]}. {s.text}" + (f" [그림 {s.figure_id}]" if s.figure_id else "")
                           for k, s in enumerate(item.statements)],
            "options": [f"{CIRCLED[k]} " + (c.text or f"[그림 {c.figure_id}]") for k, c in enumerate(item.options)],
            "figures": figures}


def public_text(item: Item) -> str:
    p = public_item(item)
    return " ".join([p["stem"], p["passage"], *p["statements"], *p["options"]])
