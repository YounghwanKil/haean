# -*- coding: utf-8 -*-
"""PSAT 글자 폭 모형(함초롬바탕 11pt 장평 95%). 값은 2026 5급 공채 PSAT 기출 PDF(한글 2010 출력)의 글자 진행폭 — 양식 hwpx 의 런(자간)과
글자 단위로 대조해 잰 값(2026-10-18, 상황판단 455줄 · 한글 4,940자).

- 한글 10.07 · 전각(한자·자모·ㆍ·○□·～·－) 10.45 · 원문자 ①~⑩ 10.55 · 빈칸 5.16(늘어나지 않은 빈칸) · 고정폭 빈칸 2.64
- 문장 부호 .,:; 3.05 · 작은따옴표 3.0 · 큰따옴표 5.16 · 괄호 3.96 · ｢｣ 6.48 · 숫자 6.24 · 영문 대문자 7.67 · 소문자 5.8 · % 8.5
- 자간 1% = 그 글자 폭의 1%(spacing_by_width): 한글 0.101pt, 한자 0.104, 숫자 0.071 — 글자 크기 기준(0.11)이 아니다. 빈칸도 비례.
- shrink 는 문단 모양의 '공백 최소값'(condense)을 따른다(문단마다 TP.shrink). 공식 양식은 0, 자체 양식 75.
보정 절차는 각 과목 프로필 calibration.md.
"""
from ...core.width import WidthModel

WIDTH = WidthModel(han=10.07, wide=10.45, circ=10.55, space=5.16, fw_space=2.64, tab=10.0, punct=3.05, bracket=3.96,
                   cjk_bracket=6.48, dquote=5.16, digit=6.24, upper=7.67, lower=5.8, pct=8.5, other=7.0, eq_char=5.5,
                   shrink=0.0, loose=0.80, spacing_by_width=True,
                   compress=0.07, stretch=0.08)     # 자간 −7 ~ +8%: 공식 양식 손조판의 범위(−1~−7 이 대부분, +1~+8). 한글은 글자 단위로
                                                    # 줄을 채우므로 줄마다 자간으로 '다음 글자가 못 들어오게' 맞춰야 같은 자리에서 접힌다

HANGUL_SHARE = 0.77     # 줄글에서 빈칸이 아닌 글자 비율(추리논증 기출 실측 27/35). 줄당 글자수 어림에 쓴다


def chars_per_line(avail_pt, wm=WIDTH):
    """줄 폭(pt) → 줄당 글자수 어림(빈칸 포함): 한글 77%·빈칸 23% 가정. PSAT 는 실측 표가 아직 없어 기하에서 어림한다."""
    avg = HANGUL_SHARE * wm.han * wm.scale + (1 - HANGUL_SHARE) * wm.space * wm.scale
    return int(avail_pt / avg)
