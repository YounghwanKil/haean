# -*- coding: utf-8 -*-
"""PSAT 상황판단(5급 공채 심화) 문제지. 양식: 2026 5급 공채 상황판단 공식 hwpx(본문을 지우고 머리말·모양만 씀)."""
import os

from ..psat_common import Role, TableStyle, PsatStyle, PsatProfile, WIDTH

TAB2 = '<hp:tab width="1510" leader="0" type="2"/><hp:tab width="560" leader="0" type="1"/>'

STYLE = PsatStyle(
    name="psat5_situation", subject="상황판단", template="template.hwpx",
    title_text="2026년도 국가공무원 5급 공채 등 필기시험",
    stem=Role(5, 0, 10, head_cs=12),
    stem_head1='<hp:tab width="586" leader="0" type="2"/>{n}.<hp:tab width="560" leader="0" type="1"/>',
    stem_head2='{n}.<hp:tab width="526" leader="0" type="1"/>',
    choice=Role(7, 0, 10),
    choice_head=TAB2 + '{m}<hp:tab width="546" leader="0" type="1"/>',
    spacer_top=Role(10, 0, 10), spacer_between=Role(10, 0, 10),
    holder=Role(5, 0, 14), holder_head=TAB2,
    sethead=Role(5, 0, 12),
    # 상자 안 줄글: 공식 양식은 조문과 같은 6(양쪽 맞춤 170%, 좌우 여백 1000). 20은 표 칸(가운데 130%)이라
    # 줄글이 상자 왼쪽에 붙고 첫 줄이 테두리에 가까워진다.
    box_text=Role(6, 0, 10), box_text_head="  ",
    lbox_text=Role(6, 0, 10),
    lbox_title=Role(8, 0, 18),
    bogi=Role(11, 0, 10),
    dialog=Role(53, 0, 10),
    bullet=Role(34, 0, 10),
    law=Role(6, 0, 10), lawitem=Role(6, 0, 10),
    ho=Role(16, 0, 10), mok=Role(17, 0, 10),
    note=Role(58, 0, 21),
    subtitle=Role(43, 0, 10),
    figure=Role(8, 0, 10), figure_title=Role(45, 0, 10),
    table=TableStyle(title=Role(45, 0, 10), unit=Role(63, 0, 10), note=Role(58, 0, 21),    # 단위: 오른쪽 맞춤(오른쪽 여백 1000 = 표 오른쪽 끝)
                     cell=Role(20, 0, 10), cell_right=Role(20, 0, 10), cell_left=Role(20, 0, 10),
                     border=2, head_border=2),
    extra={"box_border": 2, "tilde": True, "box_fit_pt": -7.72, "box_gap_pt": 2.83},   # 상자: 마지막 줄 여분(7.72pt)을 덜고 위아래 칸 여백 +2.83pt(양식 실측 첫 줄 위 간격)
)

from ..psat_solutions import SITUATION as SOLUTIONS

PROFILE = PsatProfile(STYLE, os.path.dirname(os.path.abspath(__file__)), solution_profile=SOLUTIONS, width=WIDTH)
