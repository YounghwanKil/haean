from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Brief(StrictModel):
    exam: Literal["leet", "psat5", "psat7"]
    subject: Literal["추리논증", "언어논리", "자료해석", "상황판단"]
    item_type: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    difficulty: Literal["하", "중", "상"] = "중"
    count: int = Field(default=1, ge=1, le=4)
    shared_passage: bool = False

    @model_validator(mode="after")
    def route(self):
        if (self.exam == "leet") != (self.subject == "추리논증"):
            raise ValueError("LEET는 추리논증, PSAT는 언어논리·자료해석·상황판단을 선택하세요.")
        if self.shared_passage and self.count != 2:
            raise ValueError("공통 지문 세트는 2문항 단위입니다.")
        return self


class Option(StrictModel):
    number: int = Field(ge=1, le=5)
    text: str = Field(min_length=1)


class Judgment(StrictModel):
    target: str
    verdict: Literal["참", "거짓", "판단불가"]
    evidence: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    trap: str


class Calculation(StrictModel):
    label: str
    expression: str
    expected: str
    unit: str
    evidence: str


class Table(StrictModel):
    title: str
    unit: str
    columns: list[str]
    rows: list[list[str]]
    note: str


class FigureNode(StrictModel):
    id: str
    label: str


class FigureEdge(StrictModel):
    sources: list[str] = Field(min_length=1)
    target: str
    relation: Literal['support', 'attack']


class FigureSeries(StrictModel):
    name: str
    values: list[float]


class Figure(StrictModel):
    id: str
    placement: Literal['passage', 'option_1', 'option_2', 'option_3', 'option_4', 'option_5']
    kind: Literal['argument', 'bar', 'line']
    title: str
    x_label: str
    y_label: str
    categories: list[str]
    series: list[FigureSeries]
    nodes: list[FigureNode]
    edges: list[FigureEdge]
    note: str

    @model_validator(mode='after')
    def structure(self):
        if self.kind == 'argument':
            ids = {n.id for n in self.nodes}
            if not ids or len(ids) != len(self.nodes): raise ValueError('도식 노드 ID 누락·중복')
            if any(e.target not in ids or not set(e.sources) <= ids or e.target in e.sources for e in self.edges):
                raise ValueError('도식 연결의 노드 참조 오류')
        elif not self.categories or not self.series or any(len(s.values) != len(self.categories) for s in self.series):
            raise ValueError('그래프 범주와 계열 길이 불일치')
        return self


class Item(StrictModel):
    id: str
    subject: str
    item_type: str
    domain: str
    topic: str
    difficulty: Literal["하", "중", "상"]
    difficulty_basis: str
    stem: str = Field(min_length=1)
    passage: str = Field(min_length=1)
    statements: list[str]
    tables: list[Table]
    options: list[Option] = Field(min_length=5, max_length=5)
    answer: int = Field(ge=1, le=5)
    judgments: list[Judgment] = Field(min_length=5)
    explanation: str = Field(min_length=1)
    commentary: str
    cognitive_task: str
    essential_conditions: list[str]
    originality: str
    source_ids: list[str]
    calculations: list[Calculation]
    shared_passage_id: str | None
    figures: list[Figure] = Field(default_factory=list)

    @model_validator(mode="after")
    def options_unique(self):
        if [o.number for o in self.options] != [1, 2, 3, 4, 5]:
            raise ValueError("Options must be ordered 1–5")
        if len({o.text.strip() for o in self.options}) != 5:
            raise ValueError("Duplicate options")
        for table in self.tables:
            if not table.columns or any(len(row) != len(table.columns) for row in table.rows):
                raise ValueError("Table rows must match columns")
        return self


class Draft(StrictModel):
    design_summary: str
    items: list[Item] = Field(min_length=1, max_length=4)


class Issue(StrictModel):
    severity: Literal["A", "B", "C"]
    category: str
    item_id: str
    location: str
    problem: str
    fix: str


class Solution(StrictModel):
    item_id: str
    answer: int | None = Field(ge=1, le=5)
    uniquely_answerable: bool
    option_reasons: list[str] = Field(min_length=5, max_length=5)
    missing_conditions: list[str]


class BlindReview(StrictModel):
    solutions: list[Solution]
    issues: list[Issue]


class EditorialReview(StrictModel):
    issues: list[Issue]
    summary: str
