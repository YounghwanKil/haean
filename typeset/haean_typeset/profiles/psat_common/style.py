# -*- coding: utf-8 -*-
"""PSAT 문제지 양식 설정(양식마다 하나). 문단 역할 → 양식의 문단 모양·스타일·글자 모양 ID.

ID 는 양식 파일에서 그 역할로 가장 많이 쓰인 것을 골랐다(tools/roles.py 로 조사). 역할별 머리(번호·탭)는
양식 견본 문단의 XML 을 그대로 옮겼다({n} 자리에 번호).
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Role:
    ps: int
    st: int
    cs: int
    head_cs: Optional[int] = None     # 머리(번호·라벨) 글자 모양. None 이면 cs

    @property
    def hcs(self):
        return self.cs if self.head_cs is None else self.head_cs


@dataclass
class TableStyle:
    """자료표: 제목·단위·주석은 표 밖 문단, 칸은 양식 칸 모양."""
    title: Role
    unit: Role
    note: Role
    cell: Role                  # 가운데 맞춤 칸
    cell_right: Role            # 오른쪽 맞춤(자릿수가 다른 숫자 열) — 오른쪽 여백 있는 문단 모양
    cell_left: Role             # 왼쪽 맞춤(긴 글 칸)
    border: int                 # 칸 테두리(사방 실선)
    head_border: int            # 머리행 칸(같아도 됨)
    cell_margin: tuple = (1.41, 1.41, 1.41, 1.41)    # 왼·오·위·아래 pt
    title_gap: float = 0.0      # 제목·단위 문단 사이 여백(줄 간격으로 처리)
    frame_top: int = 0          # 0 이 아니면 제목·단위를 표의 첫 행(열 전체 합친 칸, 이 테두리)으로 넣는다 — 자료해석 자체 양식
    frame_bottom: int = 0       # 0 이 아니면 주석(※)을 표의 끝 행(열 전체 합친 칸, 이 테두리)으로 넣는다
    frame_top_margin: tuple = (0.0, 0.0, 1.41, 1.41)
    frame_bottom_margin: tuple = (1.41, 1.41, 1.41, 1.41)


@dataclass
class PsatStyle:
    name: str                   # 프로필 이름
    subject: str                # 표지·머리 글(예: 언어논리)
    template: str               # 프로필 폴더 안 양식 파일 이름
    title_text: str             # 양식 머리말에 든 시험명(바꿀 자리)
    stem: Role
    stem_head1: str             # 한 자리 번호 머리 XML ({n})
    stem_head2: str             # 두 자리 번호 머리 XML ({n})
    choice: Role
    choice_head: str            # 선지 머리 XML ({m})
    spacer_top: Role            # 단 맨 위 빈 줄(130%)
    spacer_between: Role        # 한 단에 이어 놓는 문항 사이 빈 줄
    holder: Role                # 상자·표·그림을 담는 문단
    holder_head: str            # 그 문단의 개체 앞 탭 XML
    sethead: Role               # [19～20] 다음 글을 읽고 …
    box_text: Role              # 상자 안 줄글
    box_text_head: str          # 줄글 첫머리(공식 양식: 빈칸 두 개, 자체 양식: 첫 줄 들여쓰기라 "")
    lbox_text: Role             # 제목 상자(<상황> 등) 안 줄글
    lbox_title: Role            # <보  기> 제목
    bogi: Role                  # ㄱ. ㄴ. ㄷ.
    dialog: Role                # 갑: …  甲: …  A: …
    bullet: Role                # ○ …
    law: Role                   # 제○○조(…) …
    lawitem: Role               # ② …
    ho: Role                    # 1. …
    mok: Role                   # 가. …
    note: Role                  # ※ …
    subtitle: Role              # 상자 안 가운데 소제목 <…>
    figure: Role                # 그림 문단(가운데)
    figure_title: Role          # <그림> 제목
    box_needle: str = 'rowCnt="1" colCnt="1"'          # 제목 없는 상자 견본 찾기
    lbox_needle: str = "&lt;보  기&gt;"                # 제목 상자 견본 찾기
    table: Optional[TableStyle] = None
    choice2: Optional[Role] = None                      # 두 개씩 놓는 선지(자료해석 자체 양식)
    choice2_head: str = ""                              # ({m1} {t1} {m2} {t2})
    fw: float = 2.79                                    # 고정폭 빈칸 폭(pt) — 라벨 내어쓰기 계산
    max_items: int = 40
    holder_extra: float = 6.8                           # 개체 문단: 개체 높이 밖에 더해지는 줄 여유
    first_unit_lead: bool = False                       # 첫 문항 앞에 단 맨 위 빈 줄을 넣는가(머리 문단이 이미 빈 줄이면 False)
    pack_short_choices: bool = False                    # 짧은 선지를 두 개씩(choice2)
    use_top_spacer: bool = True                         # 새 단 맨 위에 빈 줄(130%)을 두는가
    extra: dict = field(default_factory=dict)
