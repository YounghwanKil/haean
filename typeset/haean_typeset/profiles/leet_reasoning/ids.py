# -*- coding: utf-8 -*-
"""양식 파일(template.hwpx)의 스타일·문단 모양·글자 모양·테두리 ID.

원본 hwp에서 읽은 번호다. hwp → hwpx 저장 때 번호는 그대로 유지된다.
template.verify_ids()가 양식 파일을 열 때 대표 값(들여쓰기·글자 크기)으로 번호가 맞는지 확인한다.
양식 파일을 고쳐 번호가 바뀌면 이 파일만 고친다.
"""

# ── 스타일 (styleIDRef)
ST_NORMAL = 0        # 바탕글
ST_STEM = 2          # 문제
ST_CHOICE = 3        # 선택지
ST_TABLE = 4         # 표-가운데
ST_BOXTEXT = 5       # 박스내용(들여쓰기)
ST_BOXITEM = 6       # 보기내용(내어쓰기)
ST_CASEHEAD = 7      # <사례견해>
ST_BOX = 8           # 보기박스
ST_NOTICE = 13       # 유의 사항

# ── 글자 모양 (charPrIDRef)
CS_BODY = 0          # 신명 중명조 11pt 95% -5%
CS_NOTE_BLANK = 3    # 바탕글(빈 문단)
CS_NOTICE = 4        # KoPub돋움 Light 11pt (유의·확인 사항)
CS_CHOICE = 17       # 선지
CS_SUP = 18          # 위첨자
CS_BOLD = 19         # 볼드 / 의안 라벨 (한양견명조)
CS_TABLE = 20        # 표 칸
CS_CHECK_STAR = 24   # 확인 사항 별표
CS_ITALIC = 25       # 이탤릭
CS_NUM = 26          # 문항 번호 한양견명조 12pt
CS_BOGI_TINY = 27    # <보기> 표 빈 칸(1pt)
CS_BOGI_TITLE = 28   # <보 기>
CS_ARTICLE = 31      # 조문 머리 KoPub돋움 Light 10pt
CS_BOX = 36          # 보기박스 문단
CS_CASEHEAD = 37     # 소제목(진하게)
CS_UNDERLINE = 39    # 문제 밑줄
CS_SUB = 40          # 하첨자
CS_CHECK_TAIL = 43   # 확인 사항 끝

# ── 문단 모양 (paraPrIDRef)
PS_STEM = 7
PS_BOX = 21              # 지문 박스·<보기> 상자를 담는 문단
PS_BOXTEXT_0 = 22        # 박스 줄글, 아래 0
PS_BOXTEXT_5 = 35        # 아래 5
PS_BOXTEXT_10 = 36       # 아래 10
PS_CASEHEAD = 14         # 소제목
PS_SPK_HAN = 32          # 갑 :
PS_SPK_HAN_NUM = 10      # 갑1 :
PS_SPK_HAN_TAB = 11      # 을⇥1 :
PS_SPK_LAT = 37          # A⇥:
PS_SPK_LAT_X = 20        # X⇥:
PS_SPK_LAT_NUM = 12      # P1 :
PS_COND = 13             # ◦ 조건 1 :
PS_BULLET = 38           # ◦ 내용
PS_EXPER = 40            # 실험 1 :
PS_PRINCIPLE = 16        # [원리]
PS_LIST = 28             # (1)
PS_ARTICLE = 33          # 제○조
PS_CLAUSE = 34           # ② 항
PS_ITEM = 41             # 1. 호
PS_BILL = 39             # <의안 1>
PS_TABLE_PARA = 8        # 박스 안 표를 담는 문단(왼쪽 8.5)
PS_TABLE_CELL = 24       # 표 칸 안 (가운데, 130%)
PS_BOGI_G = 26           # ㄱ.
PS_BOGI_N = 25           # ㄴ.
PS_BOGI_REST = 8         # ㄷ. ㄹ.
PS_BOGI_EMPTY = 54       # <보기> 표 빈 칸
PS_BOGI_TITLE = 57       # <보 기> (배분 정렬)
PS_BLANK = 62            # 빈 문단
PS_CHOICE_32 = 23        # 선지 3+2 (탭)
PS_CHOICE_1 = 9          # 선지 한 줄에 하나
PS_CHECK_HEAD = 6        # 확인 사항 첫 줄
PS_CHECK_BODY = 64       # 확인 사항 둘째 줄

# ── 테두리/배경 (borderFillIDRef)
BF_NONE = 1
BF_TABLE = 3             # 사방 실선 0.12mm (자료표 칸)
BF_CHECK = 6             # 확인 사항 상자
BF_BOGI_TITLE = 8        # <보 기> 칸(선 없음)
BF_BOGI_TOPSIDE = 15     # 1행 양옆: 아랫선 = 상자 위 테두리
BF_BOGI_L = 16           # 2행 왼쪽: 왼·위
BF_BOGI_R = 17           # 2행 오른쪽: 오른·위
BF_BOGI_BODY = 18        # 3행: 왼·오른·아래
BF_PASSAGE = 19          # 지문 박스 칸

# ── 검증용 대표 값: (종류, ID) → (속성, 값)
EXPECT = {
    ("paraPr", PS_STEM): ("intent", -1040),
    ("paraPr", PS_SPK_HAN): ("intent", -2060),
    ("paraPr", PS_COND): ("intent", -5136),
    ("paraPr", PS_CHOICE_1): ("intent", -1564),
    ("paraPr", PS_CLAUSE): ("left", 2630),
    ("charPr", CS_BODY): ("height", 1100),
    ("charPr", CS_NUM): ("height", 1200),
    ("charPr", CS_ARTICLE): ("height", 1000),
}

# ── v2 추가: 그림·표 보강
PS_FIGURE = 24           # 지문·<보기> 안 그림을 담는 문단(가운데, 130%). 양식 '표-가운데' 문단 모양
ST_FIGURE = 4
CS_FIGURE = 20
PS_TABLE_TITLE = 24      # 표 제목: 표 위 가운데(표-가운데)
PS_TABLE_UNIT = 51       # 표 단위: 표 위 오른쪽. 양식에 박스 안 오른쪽 맞춤 문단이 없어 가장 가까운 것(오른쪽 여백 3pt)
ST_TABLE_UNIT = 0
PS_TABLE_NOTE = 18       # 표 주석: 표 아래(보기내용, 왼쪽 8.5 · 아래 3)
BF_CELL_NONE = 4         # 그림 선지 표 칸(선 없음) — 양식 그림 선지 견본과 같음
PS_PIC_CELL = 31         # 그림 선지 칸 문단(선택지)
ST_PIC_CELL = ST_CHOICE
PS_PIC_TABLE = 47        # 그림 선지 표를 담는 문단(바탕글)
CS_PIC_TABLE = CS_NOTE_BLANK

# 글 안 꾸밈 → 글자 모양, 글자 모양 → 글자 스타일(양식이 스타일로 넣은 글자는 같은 스타일을 단다)
STYLE_CS = {"u": CS_UNDERLINE, "b": CS_BOLD, "i": CS_ITALIC, "sup": CS_SUP, "sub": CS_SUB}
CHAR_STYLE = {CS_NUM: 1, CS_ARTICLE: 9, CS_UNDERLINE: 10, CS_ITALIC: 11, CS_BOLD: 12, CS_SUP: 14, CS_SUB: 15}
