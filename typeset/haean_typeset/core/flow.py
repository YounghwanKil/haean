# -*- coding: utf-8 -*-
"""단 흐름 배치 시뮬레이션(과목 무관).

문서를 '덩이(Unit)' 차례로 단에 쌓는다. 덩이는 문항 하나, 또는 공통지문 세트의 머리·지문.
덩이마다 정책이 있다:
  "column" — 늘 새 단에서 시작(단 맨 위가 아니면 단 나누기)
  "fit"    — 지금 단에 다 들어가면 이어서, 아니면 새 단
  "flow"   — 그냥 이어서(넘치면 한글이 다음 단으로 흘림)
덩이는 블록(Block) 목록이다. 블록은 문단 XML 하나와 높이(pt)를 가진다. 글 문단은 줄 단위로 단 경계에서
나뉠 수 있고(split), 개체(상자·표·그림)를 담은 문단은 통째로 다음 단으로 넘어간다.

단 맨 위에서 시작하는 덩이와 이어지는 덩이 앞에 다른 머리 블록(빈 줄)을 둘 수 있다(lead_top / lead_between).
결과로 각 덩이의 시작·끝 단, 단 나누기를 넣을 블록, 넘침을 돌려준다. 단 나누기는 블록 XML 의 첫 문단
columnBreak="0" 을 "1" 로 바꿔 넣는다(쪽 나누기는 쓰지 않는다: 2단에서 왼쪽 단 끝의 단 나누기 = 다음 쪽).
"""
from dataclasses import dataclass, field

EPS = 0.5


@dataclass
class Block:
    xml: str
    height: float
    kind: str = ""
    src: tuple = ()
    lines: int = 0
    line_pt: float = 0.0
    split: bool = False
    column_break: bool = False

    def render(self):
        if not self.column_break:
            return self.xml
        return self.xml.replace('columnBreak="0"', 'columnBreak="1"', 1)


@dataclass
class Unit:
    key: object
    blocks: list
    policy: str = "column"
    lead_top: object = None        # Block 또는 None
    lead_between: object = None
    label: str = ""
    item_numbers: tuple = ()
    info: dict = field(default_factory=dict)

    def height(self, lead=None):
        return sum(b.height for b in self.blocks) + (lead.height if lead else 0.0)


def place(units, capacity):
    """capacity(col) → 그 단 높이(pt). → (단 수, [덩이별 배치 dict])
    배치 dict: key, start_col, end_col, top(시작 단에서 쓴 높이), height, over(한 단보다 큰 개체), split(여러 단에 걸침)."""
    col, used, out = 0, 0.0, []
    for u in units:
        fits_here = used + u.height(u.lead_between) <= capacity(col) + EPS
        new = used > EPS and (u.policy == "column" or (u.policy == "fit" and not fits_here))
        if new:
            col, used = col + 1, 0.0
        lead = u.lead_top if used <= EPS else u.lead_between
        blocks = ([lead] if lead is not None else []) + list(u.blocks)
        u.info["blocks"] = blocks
        if new:
            blocks[0].column_break = True
        start, top, over = col, used, False
        for b in blocks:
            room = capacity(col) - used
            if b.height <= room + EPS:
                used += b.height
                continue
            if b.split and b.line_pt > 0 and b.lines > 1:
                fit = max(0, int((room + EPS) // b.line_pt))
                rest = b.lines - fit
                extra = b.height - b.lines * b.line_pt         # 문단 위아래 여백
                while rest > 0:
                    col += 1
                    n = min(rest, max(1, int((capacity(col) + EPS) // b.line_pt)))
                    used = n * b.line_pt
                    rest -= n
                used += max(0.0, extra)
                continue
            if used > EPS:
                col += 1
            used = b.height
            if b.height > capacity(col) + EPS:
                over = True
        out.append({"key": u.key, "label": u.label, "items": list(u.item_numbers), "start_col": start,
                    "end_col": col, "top": round(top, 1), "height": round(sum(b.height for b in blocks), 1),
                    "over": over, "split": col > start})
    return col + 1, out


def render(units):
    return "".join(b.render() for u in units for b in u.info.get("blocks", u.blocks))
