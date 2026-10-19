# -*- coding: utf-8 -*-
"""PSAT 조판 계획 꼴."""
from dataclasses import dataclass, field

from ...core.linebreak import wrap


@dataclass
class TP:
    """글 문단 하나(발문·선지·상자 안 문단 …)."""
    kind: str
    ps: int
    st: int
    cs: int
    hcs: int
    head: str            # 머리 글(라벨 + 고정폭 빈칸) — 줄 폭 계산에 들어감
    raw_head: str        # 탭 등 XML 머리(줄 폭 계산 밖: 첫 줄 시작이 이미 탭 자리)
    body: str            # 원고 글(표기 포함)
    first_w: float
    rest_w: float
    pitch: float
    gap: float = 0.0     # 문단 위+아래 여백
    shrink: float = 0.0
    src: tuple = ()
    prefix: str = ""     # 원고 문자열에서 body 앞(되쓰기용)
    wrap_lines: bool = True
    lines: int = 1

    @property
    def text(self):
        return self.head + self.body

    def measure(self, wm, auto_break=True):
        """줄 수를 정한다. 원고에 줄이 정해져 있으면 그대로, 아니면 어절 단위로 나눈 줄 수."""
        if "\n" in self.body or not self.wrap_lines:
            self.lines = self.body.count("\n") + 1
        else:
            self.lines = len(wrap(self.text, self.first_w, self.rest_w, wm.with_shrink(self.shrink)))
        return self.lines

    def broken(self, wm):
        """줄을 나눈 body(첫 줄에 머리 포함 폭으로 나눔)."""
        if "\n" in self.body or not self.wrap_lines:
            return self.body
        lines = wrap(self.text, self.first_w, self.rest_w, wm.with_shrink(self.shrink))
        return "\n".join(lines)[len(self.head):]

    @property
    def height(self):
        return self.lines * self.pitch + self.gap


@dataclass
class Box:
    """상자: title 이 비면 제목 없는 상자, 있으면 <title> 제목 상자."""
    title: str
    content: list                # TP / DataTable / Fig
    src: tuple = ()
    inner_w: float = 0.0
    height: float = 0.0          # 개체 높이(바깥 여백 제외)


@dataclass
class DataTable:
    rows: list
    title: str = ""
    unit: str = ""
    note: list = field(default_factory=list)      # 주석 문단 글
    header_rows: int = 1
    col_widths: list = field(default_factory=list)
    align: list = field(default_factory=list)     # 열별 "C"/"R"/"L"
    src: tuple = ()
    cells: list = field(default_factory=list)     # (row, col, colspan, rowspan, text)
    ncols: int = 0
    nrows: int = 0
    row_heights: list = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0          # 표 개체 높이
    title_tp: object = None
    unit_tp: object = None
    note_tps: list = field(default_factory=list)


@dataclass
class Fig:
    path: str
    abspath: str = ""
    width_pt: float = 0.0
    height_pt: float = 0.0
    px: tuple = (0, 0)
    src: tuple = ()
    title_tp: object = None
    bin_id: str = ""
    kind: str = "그림"
