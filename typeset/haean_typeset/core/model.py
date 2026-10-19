# -*- coding: utf-8 -*-
"""조판 계획의 데이터 꼴. 값(문단 모양 번호·폭)은 프로필이 채운다."""
from dataclasses import dataclass, field


@dataclass
class Para:
    ps: int                     # 문단 모양 ID
    st: int                     # 스타일 ID
    runs: list                  # [(글자 모양 ID, [조각...])]
    kind: str = ""
    indent_pt: float = 0.0      # 둘째 줄부터 더 들어가는 폭(내어쓰기)
    first_pt: float = 0.0       # 첫 줄만 더 들어가는 폭(들여쓰기)
    left_pt: float = 0.0
    gap_after: float = 0.0
    gap_before: float = 0.0
    text: str = ""              # 머리 + 원고 글 (줄 나눔·점검 기준)
    column_break: bool = False
    right_pt: float = 0.0
    container: float = 0.0      # 문단이 놓이는 폭
    src: tuple = ()             # 원고 자리 ("지문", k) ("보기", k) ("선지", k) ("발문",)
    head: str = ""              # 조판기가 붙인 머리. text = head + 원고 글
    line_pt: float = 0.0        # 줄 간격(pt)

    def widths(self):
        """(첫 줄 폭, 둘째 줄부터 폭)"""
        base = self.container - self.left_pt - self.right_pt
        return base - self.first_pt, base - self.indent_pt

    def n_lines(self):
        return self.text.count("\n") + 1


@dataclass
class Cell:
    text: str
    col: int
    row: int
    colspan: int = 1
    rowspan: int = 1


@dataclass
class Table:
    rows: list                  # 원고 행(문자열 또는 {"글","가로","세로"})
    kind: str = "표"
    title: str = ""
    unit: str = ""
    note: str = ""
    header: bool = True
    src: tuple = ()
    height: float = 0.0         # 프로필이 계산해 채운다(제목·단위·주석 포함)
    cells: list = field(default_factory=list)
    col_widths: list = field(default_factory=list)
    row_heights: list = field(default_factory=list)
    ncols: int = 0


@dataclass
class Figure:
    path: str                   # 원고에 적힌 경로
    abspath: str = ""
    width_pt: float = 0.0       # 놓을 크기
    height_pt: float = 0.0
    px: tuple = (0, 0)
    natural_pt: tuple = (0.0, 0.0)
    src: tuple = ()
    kind: str = "그림"
    bin_id: str = ""            # 조립 때 정해진다(imageN)
