# -*- coding: utf-8 -*-
"""글 안 표기 → 조각·런.

조각: ("t", 글) ("nb",) 묶음 빈칸 ("fw",) 고정폭 빈칸 ("tab",) ("br",) ("eq", 한글 수식 스크립트)
런: (글자 모양 ID, [조각...])

표기: <u> <b> <i> <sup> <sub> (프로필이 ctx.style_cs 로 글자 모양을 정함), $LaTeX$ (한글 수식으로 변환),
      ` = `·`＝` → 전각 등호 앞뒤 고정폭 빈칸, `1 : 2` → 비율 쌍점 앞뒤 고정폭 빈칸,
      \\n → 강제 줄 나눔, 표시 문자 \\x1f 고정폭 빈칸 · \\x1e 묶음 빈칸 · \\t 탭.
"""
import re

from . import latex2eqn as L2E

L2E.KICE_REL_GAPS = False          # 평가원 수학 문제지용 관계 기호 간격 보정은 쓰지 않는다(설정값, 상태 아님)

FW, NB, TAB = "\x1f", "\x1e", "\t"
TAG = re.compile(r"(</?(?:u|b|i|sup|sub)>|\$[^$]+\$)")
EQ_SIGN = re.compile(r" *[=＝] *")
RATIO = re.compile(r"(\d)( *):( *)(\d+)( ?)")


def text_pieces(s):
    out = []

    def ratio(m):
        if not (m.group(2) or m.group(3)):
            return m.group(0)
        return "%s\x1f:\x1f%s%s" % (m.group(1), m.group(4), "\x1f" if m.group(5) else "")

    s = EQ_SIGN.sub("\x1f＝\x1f", RATIO.sub(ratio, s))
    buf = ""
    for ch in s:
        if ch in ("\x1f", "\x1e", "\u00a0", "\t", "\n"):
            if buf:
                out.append(("t", buf))
                buf = ""
            out.append({"\x1f": ("fw",), "\x1e": ("nb",), "\u00a0": ("nb",), "\t": ("tab",), "\n": ("br",)}[ch])
        else:
            buf += ch
    if buf:
        out.append(("t", buf))
    return out


def runs(text, base_cs, ctx):
    """표기가 섞인 글 → 런 목록. 꾸밈 태그는 겹치지 않는다고 본다(안쪽 태그가 이긴다)."""
    result, stack = [], []
    for tok in TAG.split(text or ""):
        if not tok:
            continue
        m = re.fullmatch(r"<(/?)(u|b|i|sup|sub)>", tok)
        if m:
            if m.group(1):
                if stack and stack[-1] == m.group(2):
                    stack.pop()
            else:
                stack.append(m.group(2))
            continue
        cs = ctx.styled(base_cs, stack[-1]) if stack else base_cs
        if tok.startswith("$") and tok.endswith("$") and len(tok) > 2:
            pieces = [("eq", L2E.conv(tok[1:-1].strip(), ctx.unknown_tex))]
        else:
            pieces = text_pieces(tok)
        if result and result[-1][0] == cs:
            result[-1][1].extend(pieces)
        else:
            result.append((cs, list(pieces)))
    return result


def unknown_tex(text):
    """글 안 $LaTeX$ 의 모르는 명령(검사용, 런을 만들지 않음)."""
    out = []
    for m in re.finditer(r"\$([^$]+)\$", text or ""):
        L2E.conv(m.group(1).strip(), out)
    return out


def plain(text):
    """폭 어림·점검용 맨 글(꾸밈 태그를 지우고 수식은 글자만 남긴다)."""
    t = re.sub(r"</?(?:u|b|i|sup|sub)>", "", text or "")
    return re.sub(r"\$([^$]+)\$", lambda m: re.sub(r"[{}_^\\]|rm|it", "", m.group(1)), t)
