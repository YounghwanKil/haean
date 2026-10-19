# -*- coding: utf-8 -*-
"""PSAT 언어논리(5급 공채 심화) 문제지. 양식: 2026 5급 공채 언어논리 공식 hwpx(본문을 지우고 머리말·모양만 씀)."""
import os

from ..psat_common import Role, TableStyle, PsatStyle, PsatProfile, WIDTH

TAB2 = '<hp:tab width="1510" leader="0" type="2"/><hp:tab width="560" leader="0" type="1"/>'

STYLE = PsatStyle(
    name="psat5_language", subject="언어논리", template="template.hwpx",
    title_text="2026년도 국가공무원 5급 공채 등 필기시험",
    stem=Role(2, 0, 1, head_cs=2),
    stem_head1='<hp:tab width="586" leader="0" type="2"/>{n}.<hp:tab width="560" leader="0" type="1"/>',
    stem_head2='{n}.<hp:tab width="526" leader="0" type="1"/>',
    choice=Role(4, 0, 1),
    choice_head=TAB2 + '{m}<hp:tab width="546" leader="0" type="1"/>',
    spacer_top=Role(21, 0, 1), spacer_between=Role(21, 0, 1),
    holder=Role(2, 0, 1), holder_head=TAB2,
    sethead=Role(26, 0, 2),
    box_text=Role(20, 0, 1), box_text_head="  ",
    lbox_text=Role(20, 0, 1),
    lbox_title=Role(1, 0, 1),
    bogi=Role(8, 0, 1),
    dialog=Role(42, 0, 1),
    bullet=Role(23, 0, 1),
    law=Role(20, 0, 1), lawitem=Role(20, 0, 1),
    ho=Role(9, 0, 1), mok=Role(9, 0, 1),
    note=Role(9, 0, 1),
    subtitle=Role(22, 0, 1),
    figure=Role(1, 0, 1), figure_title=Role(1, 0, 1),
    table=TableStyle(title=Role(1, 0, 1), unit=Role(38, 0, 1), note=Role(9, 0, 1),
                     cell=Role(1, 0, 1), cell_right=Role(1, 0, 1), cell_left=Role(1, 0, 1),
                     border=3, head_border=3),
    extra={"box_border": 3, "tilde": True, "box_fit_pt": -7.72, "box_gap_pt": 2.83},   # 상자: 마지막 줄 여분(7.72pt)을 덜고 위아래 칸 여백 +2.83pt(양식 실측 첫 줄 위 간격)
)

from ..psat_solutions import LANGUAGE as SOLUTIONS

PROFILE = PsatProfile(STYLE, os.path.dirname(os.path.abspath(__file__)), solution_profile=SOLUTIONS, width=WIDTH)
