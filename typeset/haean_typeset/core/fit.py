# -*- coding: utf-8 -*-
"""줄 맞추기 — 정한 줄마다 자간 변형 글자 모양을 입힌다.

런 목록 [(글자 모양 ID, [조각...])] 은 ("br",) 조각에서 줄이 바뀐다. 줄 k 의 자간 delta_k 가 0 이 아니면
그 줄의 런을 ctx.spaced(cs, delta_k) 로 바꾼다(꾸밈 변형은 ctx.styled 가 자간과 합성한다).
keep_breaks=False(fit 모드) 면 예측 줄 경계의 ("br",) 을 빈칸으로 되돌린다 — 강제 줄 나눔 없이 한글이 같은 자리에서
줄을 접게(자간이 그것을 보장) 하고 양쪽 맞춤을 살린다. keep_breaks=True 는 작성자가 정한 줄(원고 \\n)용.
"""
from .linebreak import line_deltas


def fit_runs(runs, deltas, ctx, keep_breaks=True):
    """런을 줄 단위로 쪼개 자간 변형을 입힌 새 런 목록."""
    if not any(deltas) and keep_breaks:
        return runs
    out, k = [], 0

    def put(cs, piece):
        d = deltas[k] if k < len(deltas) else 0
        cs2 = ctx.spaced(cs, d) if d else cs
        if out and out[-1][0] == cs2:
            if piece[0] == "t" and out[-1][1] and out[-1][1][-1][0] == "t":
                out[-1][1][-1] = ("t", out[-1][1][-1][1] + piece[1])
            else:
                out[-1][1].append(piece)
        else:
            out.append((cs2, [piece]))

    for cs, pieces in runs:
        for piece in pieces:
            if piece[0] == "br":
                put(cs, piece if keep_breaks else ("t", " "))
                k += 1
            else:
                put(cs, piece)
    return out


def fit_paragraph(runs, text, first_w, rest_w, wm, ctx, keep_breaks=False):
    """문단 글(머리 포함, 줄은 \\n)과 그 런 → 줄마다 자간을 입힌 런. → (런, 자간 목록)"""
    if "\n" not in text:
        return runs, []
    lines = text.split("\n")
    deltas = line_deltas(lines, first_w, rest_w, wm) if ctx.header_editor is not None else [0] * len(lines)
    return fit_runs(runs, deltas, ctx, keep_breaks=keep_breaks), deltas
