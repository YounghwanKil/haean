# -*- coding: utf-8 -*-
"""글자 폭 모형 하나(v1 에서 둘로 갈라져 있던 것을 합침).

값은 기준 글자(프로필이 정함)에서의 진행폭(pt)이다. 프로필이 값 표와 배율을 정하고(각 프로필 layout.py),
근거와 보정 기록은 프로필의 calibration.md 에 둔다. 보정 루프는 tools/calibrate.py.

줄 맞추기(자간): 조판기가 어절 단위로 줄을 정하고, 한글이 스스로 같은 자리에서 줄을 바꾸게 만든다 — 강제 줄 나눔은 쓰지 않는다
(한글은 강제 줄 나눔으로 끝난 줄을 양쪽 맞춤하지 않는다). 정한 줄이 한글 규칙으로는 넘칠 때 그 줄의 글자들에 음수 자간을 넣어
`avail × (1 − margin)` 안에 들어가게 하면, 한글은 그 줄을 다 담고 다음 어절은 담지 못해 정확히 거기서 줄을 접으며 양쪽 맞춤한다
(기출이 넘치는 줄을 자간 −4~−6%로 눌러 넣는 것과 같다). 헐거운 줄은 늘리지 않는다 — 양쪽 맞춤이 빈칸으로 메운다.
  한글 규칙: 자연 폭 − 빈칸 압축(공백 최소값, shrink) ≤ 줄 폭 이면 그 줄에 들어간다.
  우리 규칙(한 줄에 넣을 수 있는 조건): 자연 폭 − 빈칸 압축 − 글자 수 × 글자 크기 × compress ≤ 목표 폭.
  줄의 자간 = −⌈(자연 폭 − 빈칸 압축 − 목표 폭) / (글자 수 × 글자 크기) × 100⌉ % (넘칠 때만, −compress 까지).
"""
import math
import re
from dataclasses import dataclass

from .inline import plain

HANGUL_LIKE = "①②③④⑤⑥⑦⑧⑨⑩○◦＝·…※"   # 그 밖의 전각 기호(□■◇◆△▲▽▼☆★◎●, 전각 영숫자)는 char_w 의 범위 검사


@dataclass
class WidthModel:
    han: float            # 한글·한자·원문자 등 전각
    space: float          # 빈칸·묶음 빈칸
    fw_space: float       # 고정폭 빈칸
    tab: float
    punct: float          # .,:;'`!|‘’"“”
    bracket: float        # ()[]<>{}
    digit: float
    upper: float
    lower: float          # 영문 소문자·그 밖의 글자
    other: float
    eq_char: float        # 수식 글자 하나
    shrink: float         # 한글 공백 최소값(문단 모양 condense)이 양쪽 맞춤 때 빈칸을 줄일 수 있는 몫 — 한글의 줄 규칙을 흉내 낸다
    loose: float          # 자연 폭이 줄 폭의 이 배 미만이면 헐거운 줄(경고)
    scale: float = 1.0    # 글자 크기 배율(예: 8pt 해설 = 7.2/9.9)
    pt: float = 11.0      # 기준 글자 크기(pt). 자간 1% = pt/100 pt 가 글자마다 더해진다
    compress: float = 0.04   # 줄을 맞출 때 자간을 이만큼(글자 크기의 비율)까지 줄인다(−4%, 기출 손조판 −4~−6%의 아래쪽)
    margin: float = 0.015    # 목표 폭 = 줄 폭 × (1 − margin). 폭 모형 오차를 흡수해 한글이 먼저 줄을 접지 않게 한다
    stretch: float = 0.0     # 헐거운 줄의 자간을 이만큼(글자 크기의 비율)까지 늘린다. 한글은 글자 단위로 줄을 채우므로 다음 글자가
                             # 들어갈 자리가 남으면 끌어올린다 — 늘려서 그 자리를 없앤다(기출 손조판 +1~+8%). 0 이면 옛 방식(줄이기만)
    spacing_by_width: bool = False   # True: 자간 1% = 그 글자 폭의 1%(한글 실측 — 2026 기출 PDF: 한글 0.101/10.07, 숫자 0.071/6.24, 빈칸도 비례).
                                     # False: 자간 1% = 글자 크기의 1%(옛 모형, 추리논증 프로필이 아직 이 값으로 보정돼 있다)
    wide: float = 0.0        # 전각 기호·한자·자모(甲·ㄱ·ㆍ·○·～)의 폭. 0 이면 han 과 같게 본다(함초롬바탕 11pt·95%: 한글 10.07, 전각 10.45)
    circ: float = 0.0        # 원문자 ①~⑩ (0 이면 wide/han)
    dquote: float = 0.0      # 큰따옴표 “ ” (0 이면 punct)
    cjk_bracket: float = 0.0 # ｢｣「」 (0 이면 other)
    pct: float = 0.0         # % (0 이면 other)

    def char_w(self, ch):
        o = ord(ch)
        wide = self.wide or self.han
        if 0xAC00 <= o <= 0xD7A3:
            w = self.han
        elif 0x2460 <= o <= 0x2473 or ch in "①②③④⑤⑥⑦⑧⑨⑩":
            w = self.circ or wide
        elif ch in "“”":
            w = self.dquote or self.punct
        elif ch in "｢｣「」『』":
            w = self.cjk_bracket or self.other
        elif ch == "%":
            w = self.pct or self.other
        elif (0x3131 <= o <= 0x318E or 0x4E00 <= o <= 0x9FFF or ch in HANGUL_LIKE
                or 0x2474 <= o <= 0x24FF or 0x2500 <= o <= 0x26FF or 0x3000 <= o <= 0x303F or 0xFF01 <= o <= 0xFF60):
            w = wide                      # 한자·자모·도형(□■◇△☆※ 등)·CJK 문장 부호·전각 영숫자: 함초롬바탕에서 전각
        elif ch in (" ", "\u00a0", "\x1e"):
            w = self.space
        elif ch == "\x1f":
            w = self.fw_space
        elif ch == "\t":
            w = self.tab
        elif ch in ".,:;'`!|‘’\"“”":
            w = self.punct
        elif ch in "()[]<>{}":
            w = self.bracket
        elif ch.isdigit():
            w = self.digit
        elif "A" <= ch <= "Z":
            w = self.upper
        elif ch.isalpha():
            w = self.lower
        else:
            w = self.other
        return w * self.scale

    def eq_w(self, src):
        vis = re.sub(r"\\[A-Za-z]+|[{}_^\s]", "", src)
        return self.eq_char * max(len(vis), 1) * self.scale

    def word_w(self, word):
        w = 0.0
        for m in re.finditer(r"\$([^$]*)\$|([^$]+)", word):
            if m.group(1) is not None:
                w += self.eq_w(m.group(1))
            else:
                w += sum(self.char_w(c) for c in plain(m.group(2)))
        return w

    def text_w(self, text):
        """한 줄로 늘어놓은 자연 폭(빈칸 포함)."""
        ws = words(text)
        return sum(self.word_w(w) for w in ws) + self.space * self.scale * (len(ws) - 1)

    def natural(self, ws):
        return sum(self.word_w(w) for w in ws) + self.space * self.scale * (len(ws) - 1)

    # ── 자간으로 줄 맞추기
    def font_pt(self):
        return self.pt * self.scale

    def spaced_chars(self, ws):
        """자간이 붙는 글자 수(수식·탭은 빼고, 어절 사이 빈칸은 넣는다)."""
        n = 0
        for w in ws:
            for m in re.finditer(r"\$([^$]*)\$|([^$]+)", w):
                if m.group(2) is not None:
                    n += len(plain(m.group(2)).replace("\t", ""))
        return n + max(len(ws) - 1, 0)

    def target(self, avail):
        return avail * (1.0 - self.margin)

    def slack(self, ws):
        """한글이 양쪽 맞춤 때 줄일 수 있는 빈칸 폭(공백 최소값)."""
        return self.space * self.scale * self.shrink * max(len(ws) - 1, 0)

    def spaced_width(self, ws):
        """자간이 붙는 글자들의 폭 합(빈칸 포함, 수식·탭 제외) — spacing_by_width 모형에서 자간 1% = 이 값의 1%."""
        tot = 0.0
        for w in ws:
            for m in re.finditer(r"\$([^$]*)\$|([^$]+)", w):
                if m.group(2) is not None:
                    tot += sum(self.char_w(c) for c in plain(m.group(2)) if c != "\t")
        return tot + self.space * self.scale * max(len(ws) - 1, 0)

    def per_pct(self, ws):
        """자간 1% 가 줄 폭에 더하는 pt."""
        if self.spacing_by_width:
            return self.spaced_width(ws) / 100.0
        return self.spaced_chars(ws) * self.font_pt() / 100.0

    def compressible(self, ws):
        return self.per_pct(ws) * 100.0 * self.compress

    def hangul_fits(self, ws, avail):
        """한글 규칙: 빈칸을 공백 최소값까지 줄여서 들어가는가(자간 그대로)."""
        return self.natural(ws) - self.slack(ws) <= avail

    def fits(self, ws, avail):
        """우리 규칙: 자간을 compress 까지 줄이면 목표 폭 안에 들어가는가(한글 규칙보다 늘 너그럽다 — 한글이 담는 줄은 우리도 담는다)."""
        return self.natural(ws) - self.slack(ws) - self.compressible(ws) <= self.target(avail)

    def next_char_w(self, next_line):
        """다음 줄 첫 글자가 이 줄 끝에 들어가는 데 필요한 폭(어절 사이 빈칸 + 글자)."""
        t = plain(next_line.strip()) if next_line else ""
        return (self.space * self.scale + self.char_w(t[0])) if t else 0.0

    def pull_limit(self, avail):
        """한글이 다음 글자를 끌어올리지 못하게 할 줄 폭 하한의 기준(모형 오차 margin 만큼 여유)."""
        return avail * (1.0 + self.margin)

    def line_delta(self, ws, avail, last=False, next_w=0.0):
        """한 줄의 자간(%, 정수) → (delta, 상태). 상태: 'ok' | 'over'(최대 압축으로도 넘침) | 'loose'(헐거움 — 한글이 다음 글자를 끌어올릴 수 있음).
        next_w 는 다음 줄 첫 글자(빈칸 포함)의 폭 — stretch 가 있으면 그 글자가 못 들어오게 자간을 늘린다."""
        nat, unit = self.natural(ws), self.per_pct(ws)
        eff, tgt = nat - self.slack(ws), self.target(avail)
        if unit <= 0:
            return 0, ("over" if eff > avail else "ok")
        if eff > tgt:
            need = -math.ceil((eff - tgt) / unit)
            cap = -int(round(self.compress * 100))
            return (need, "ok") if need >= cap else (cap, "over")
        if not last and self.stretch > 0 and next_w > 0 and eff + next_w <= self.pull_limit(avail):
            need = math.ceil((self.pull_limit(avail) - next_w - eff) / unit)
            cap = int(round(self.stretch * 100))
            return (need, "ok") if need <= cap else (cap, "loose")
        if not last and nat < self.loose * avail:
            return 0, "loose"
        return 0, "ok"

    def line_cost(self, ws, avail, last=False, next_w=0.0):
        """줄 배치 최적화용 비용(자간 비율의 제곱) — 넣을 수 없는 줄은 None."""
        delta, state = self.line_delta(ws, avail, last, next_w)
        if state == "over" or (state == "loose" and self.stretch > 0 and not last and next_w > 0):
            return None
        cap = self.compress if delta < 0 else self.stretch
        return (delta / 100.0 / cap) ** 2 if cap > 0 and delta else 0.0

    def scaled(self, scale):
        d = dict(self.__dict__)
        d["scale"] = scale
        return WidthModel(**d)

    def with_shrink(self, shrink):
        d = dict(self.__dict__)
        d["shrink"] = shrink
        return WidthModel(**d)


def words(text):
    """빈칸(수식 안 빈칸은 빼고)으로 어절을 나눈다."""
    out, cur = [], ""
    for m in re.finditer(r"\$[^$]*\$|[^ $]+|\$|( )", text):
        if m.group(1):
            out.append(cur)
            cur = ""
        else:
            cur += m.group(0)
    out.append(cur)
    return out
