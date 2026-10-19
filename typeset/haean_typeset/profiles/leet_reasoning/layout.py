# -*- coding: utf-8 -*-
"""LEET 추리논증 문제지 판 상수 (pt). 근거는 spec.md."""
import re

from ...core.width import WidthModel

MAX_ITEMS = 40
CHECK_COUNTS = (20, 40)             # 확인 사항 상자를 찍는 문항 수: 하프 20 · 풀 40

# ── 단
LINE = 11.0 * 1.65                  # 본문 줄 간격 165% (기출 실측 18.0)
COL_W = 318.9
COL_H = 919.8                       # 1190.52 − 위 157.32 − 아래 76.53 − 꼬리말 36.85
START = {1: 219.5, 2: 90.1}         # 1번은 표지 아래, 2번은 표지 표 아래에서 시작(양식 실측)
CHECK_BOX = 63.32 + 6.0             # 마지막 단의 확인 사항 상자 + 틈

# ── 상자
PASSAGE_W = 308.09                  # 지문 박스 폭
BOGI_W = 306.14                     # <보기> 내용 칸 폭
BOX_PAD = 8.5 + 7.08                # 상자 안쪽 위·아래 여백
BOX_AFTER = 8.7                     # 상자를 담은 문단 아래 간격
BOGI_TITLE = 12.12                  # <보 기> 제목 줄
BOX_TEXT_INNER = PASSAGE_W - 2 * 8.5   # 지문 박스 안 글 폭 291.09
BOGI_TEXT_INNER = BOGI_W - 2 * 8.5     # <보기> 칸 안 글 폭 289.14

# ── 표
DATA_TABLE_W = 290.54
ROW_H = 19.49
CELL_PAD_X = 5.1                    # 칸 여백 좌우
CELL_PAD_Y = 1.41
CELL_LINE = 11.0 * 1.30             # 표 칸 줄 간격 130%
TABLE_AFTER = 3.0
COL_MIN = 30.0

# ── 그림
FIG_PARA = 4.0                      # 그림 문단의 위아래 여유
FIG_SMALL = 0.6                     # 원본 크기 대비 이보다 작게 줄이면 경고
PIC2_COLS = (17.1, 124.6, 22.6, 17.1, 124.6)   # 그림 선지 2열(양식 견본 표 그대로)
PIC1_COLS = (17.1, 289.0)                      # 그림 선지 1열
PIC_GAP_ROW = 19.5                  # 그림 선지 줄 사이 빈 줄
PIC_PAD_Y = 2.83
WIDE = 1.6                          # 가로/세로가 모두 이 이상이면 그래프로 보고 1열

# ── 선지
CHOICE_SLOT = 95.0                  # 3+2 한 칸에 들어갈 폭(①·빈칸 포함)

# ── 줄당 글자수(빈칸 포함, 2027 기출 20쪽 실측 `exam_line_stats.txt`): (최소, 5%, 중앙, 95%, 최대)
#    줄을 정할 때 '최대'를 글자 수 상한으로 함께 본다(폭 모형이 틀려도 기출에 없던 긴 줄은 만들지 않는다).
#    입력(작성) 단계에는 '중앙'을 줄당 글자수 기준으로 준다(글자수 ↔ 줄 수 환산).
LINE_CHARS = {
    "발문 첫 줄": (37, 37, 38, 40, 40),
    "발문 이어짐": (36, 36, 38, 38, 38),
    "박스 첫 줄": (29, 30, 33, 37, 42),
    "박스 이어짐": (27, 32, 35, 38, 43),
    "내어쓰기 이어짐": (7, 29, 32, 34, 36),      # ㄱ.·A :·갑 :·P1 : 아래 줄
    "선지 이어짐": (36, 36, 36, 36, 36),
}


LINE_CHARS_N = {"발문 첫 줄": 37, "발문 이어짐": 8, "박스 첫 줄": 103, "박스 이어짐": 553, "내어쓰기 이어짐": 150, "선지 이어짐": 1}
CAP_MIN_SAMPLES = 100           # 표본이 이보다 적은 자리(발문·선지)는 '최대'를 상한으로 쓰지 않는다(폭 모형만)


def line_chars(kind, indent_pt=0.0, first=True):
    """문단 종류·줄 위치 → 실측 자리 이름."""
    if kind == "발문":
        return "발문 첫 줄" if first else "발문 이어짐"
    if kind.startswith("선지"):
        return "발문 이어짐" if first else "선지 이어짐"
    if indent_pt > 0 and not first:
        return "내어쓰기 이어짐"
    return "박스 첫 줄" if first else "박스 이어짐"


def line_cap(kind, indent_pt=0.0, first=True):
    """줄 글자 수 상한(기출 실측 최대) — 표본이 충분한 자리만, 아니면 None."""
    name = line_chars(kind, indent_pt, first)
    return LINE_CHARS[name][4] if LINE_CHARS_N[name] >= CAP_MIN_SAMPLES else None


# 입력(작성) 단계 안내: 줄당 글자수 중앙값 · 문항 줄 상한(spec.md 4장, 상자·간격 뺀 대략값)
LINE_GUIDE = {
    "줄당_글자수(빈칸 포함, 중앙)": {"발문": 38, "지문": 35, "지문 첫 줄": 33, "보기·발언(내어쓰기)": 32, "선지": 36},
    "줄당_글자수(빈칸 뺀, 중앙)": {"발문": 30, "지문": 27, "보기·발언(내어쓰기)": 25},
    "문항_줄_상한(보기 있는 문항, 대략)": {"1번": 34, "2번": 41, "마지막(20·40)": 42, "그 밖": 46},
    "줄_간격_pt": round(LINE, 2), "단_높이_pt": COL_H,
    "비고": "글자수는 숫자·영문·문장부호가 섞이면 달라진다. 조판기는 폭으로 줄을 정하고 이 표는 상한·환산 기준이다.",
}

# ── 양식 자리
TITLE_PLACEHOLDER = "2026학년도 시대인재 LEET 시험지명 X회"
COUNT_TEXT = re.compile(r"(?<=<hp:t>)\d+(?=문항</hp:t>)")
TOTAL_PAGES = re.compile(r'(paraPrIDRef="2" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                         r'<hp:run charPrIDRef="6"><hp:t>)\d+(</hp:t>)')

# ── 폭 모형 (11pt·장평 95%·자간 −5%, 2027 기출 실측. 보정 기록은 calibration.md)
#    자간 1% = 그 글자 폭의 1%(spacing_by_width — PSAT 기출 PDF 실측으로 확인한 한글 규칙, 글자 크기 기준이 아니다).
#    한글은 글자 단위로 줄을 채우므로 줄마다 자간을 [−6%, +8%] 안에서 '넘치면 줄이고, 다음 글자가 못 들어오게 늘려서' 맞추고
#    문단 전체에서 줄 자리를 고른다(core/linebreak.wrap_fit). 양식 자간이 이미 −5% 라 줄이는 쪽 한도는 PSAT(−7)보다 좁게.
WIDTH = WidthModel(han=9.9, space=4.7, fw_space=5.0, tab=10.0, punct=3.0, bracket=3.6, digit=5.0,
                   upper=6.6, lower=5.0, other=6.0, eq_char=5.5, shrink=0.45, loose=0.90,
                   spacing_by_width=True, compress=0.06, stretch=0.08)
