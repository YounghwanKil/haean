# -*- coding: utf-8 -*-
"""PSAT 자료해석(5급 공채 심화) 문제지. 양식: 시대인재 PSAT 심화 자료해석 자체 양식(메모 9개).

양식 메모 반영: 최상단 줄간격 130% · 문항 사이 줄간격 170% · 표 제목과 단위 사이 120% ·
동일 열 숫자 자릿수가 같으면 가운데, 다르면 오른쪽 맞춤 + 오른쪽 여백 · 빈 칸은 빈칸 4개 ·
주석은 음슴체(원고 몫) · 주석과 표 사이 5pt · 물결은 키보드 ~ 대신 ～.
"""
import os

from ..psat_common import Role, TableStyle, PsatStyle, PsatProfile, WIDTH

TAB2 = '<hp:tab width="1510" leader="0" type="2"/><hp:tab width="560" leader="0" type="1"/>'

STYLE = PsatStyle(
    name="psat5_data", subject="자료해석", template="template.hwpx",
    title_text="2027년도 시대인재 PSAT 심화 서바이벌 모의고사",
    stem=Role(170, 0, 12, head_cs=33),
    stem_head1='<hp:tab width="622" leader="0" type="2"/>{n}.<hp:tab width="560" leader="0" type="1"/>',
    stem_head2='{n}.<hp:tab width="26" leader="0" type="2"/><hp:tab width="560" leader="0" type="1"/>',
    choice=Role(5, 0, 12),
    choice_head=TAB2 + '{m}<hp:tab width="618" leader="0" type="1"/>',
    choice2=Role(36, 0, 12),
    choice2_head=TAB2 + '{m1}<hp:tab width="618" leader="0" type="1"/>{t1}<hp:tab width="13439" leader="0" type="1"/>'
                        '{m2}<hp:tab width="687" leader="0" type="1"/>{t2}',
    pack_short_choices=True,
    spacer_top=Role(184, 0, 12), spacer_between=Role(174, 0, 12),
    holder=Role(5, 0, 12), holder_head=TAB2,
    sethead=Role(119, 0, 52),
    box_text=Role(172, 0, 12), box_text_head="",
    lbox_text=Role(172, 0, 12),
    lbox_title=Role(2, 0, 12),
    bogi=Role(181, 0, 12),
    dialog=Role(177, 0, 12),
    bullet=Role(178, 0, 12),
    law=Role(6, 0, 12), lawitem=Role(6, 0, 12),
    ho=Role(121, 0, 12), mok=Role(121, 0, 12),
    note=Role(141, 0, 6),
    subtitle=Role(2, 0, 12),
    figure=Role(2, 0, 12), figure_title=Role(19, 0, 12),
    table=TableStyle(title=Role(19, 0, 12), unit=Role(20, 0, 12), note=Role(176, 0, 6),
                     cell=Role(2, 0, 12), cell_right=Role(240, 0, 12), cell_left=Role(6, 0, 12),      # 칸 160%(자체 양식 1948 칸의 다수 = 2·194); 자릿수 다른 숫자 열은 오른쪽(양식 메모)
                     border=4, head_border=4,
                     frame_top=6, frame_bottom=68),                                                 # 제목·단위 = 첫 행(아래선만), 주석 = 끝 행(윗선만) — 자체 양식 표 구조
    extra={"box_border": 4, "tilde": True, "empty_cell": "    ", "note_nominal": True},
)

# 자간 −4%: 폭 모형을 4% 좁힌다
from ..psat_solutions import DATA as SOLUTIONS

PROFILE = PsatProfile(STYLE, os.path.dirname(os.path.abspath(__file__)), solution_profile=SOLUTIONS,
                      width=WIDTH.scaled(0.96))
