# -*- coding: utf-8 -*-
"""어절 단위 줄 나눔과 줄 맞추기. 폭 모형(WidthModel)을 인자로 받는다.

조판기가 줄을 정한다: 문단을 어절 단위로 나눠 `\\n`을 둔다(예측 줄). 조판(fit)은 그 자리에 강제 줄 나눔을 넣지 않고
줄마다 자간을 계산해(WidthModel.line_delta) 넘치는 줄을 눌러 넣는다 — 한글이 스스로 같은 자리에서 줄을 접고 양쪽 맞춤한다.
원고에 처음부터 있던 `\\n`(작성자가 정한 줄)만 강제 줄 나눔이 된다(그 줄은 한글이 양쪽 맞춤하지 않는다).
한 줄에 넣을 수 있는 조건: 자연 폭 − 빈칸 압축 − 자간 압축 한도 ≤ 목표 폭(줄 폭 × (1 − margin)).
"""
from .inline import plain
from .width import words


def wrap(text, first_w, rest_w, wm, max_chars=None):
    """한 문단 글(머리 포함) → 줄 목록. 이미 \\n 이 있으면 그 줄들을 그대로 둔다.
    max_chars: (첫 줄, 이어지는 줄) 글자 수 상한(빈칸 포함) — 기출 실측 최대. 폭으로 들어가도 이보다 길게는 담지 않는다.
    폭 모형에 stretch 가 있으면 문단 전체에서 줄 자리를 고른다(wrap_fit) — 모든 줄이 자간 [−compress, +stretch] 안에서
    한글과 같은 자리에서 접히게. 그런 배치가 없으면 탐욕 배치로 돌아간다."""
    if "\n" in text:
        return text.split("\n")
    if getattr(wm, "stretch", 0) > 0:
        fit = wrap_fit(text, first_w, rest_w, wm, max_chars)
        if fit is not None:
            return fit
    lines, cur, avail = [], [], first_w
    cap = max_chars[0] if max_chars else None
    for w in words(text):
        too_long = cap is not None and bool(cur) and chars(" ".join(cur + [w])) > cap
        if cur and (too_long or not wm.fits(cur + [w], avail)):
            lines.append(" ".join(cur))
            cur, avail = [w], rest_w
            cap = max_chars[1] if max_chars else None
        else:
            cur.append(w)
    lines.append(" ".join(cur))
    return lines


def wrap_fit(text, first_w, rest_w, wm, max_chars=None):
    """어절 자리 최적화: 줄마다 (넘치면 줄이고, 다음 글자가 들어올 자리가 남으면 늘리는) 자간이 한도 안에 들도록 줄 자리를 고른다.
    비용 = Σ(자간/한도)² + 줄 수. 가능한 배치가 없으면 None."""
    ws = words(text)
    n = len(ws)
    if n == 0:
        return None
    INF = float("inf")
    best = [INF] * (n + 1)
    prev = [-1] * (n + 1)
    best[0] = 0.0
    for i in range(n):
        if best[i] == INF:
            continue
        avail = first_w if i == 0 else rest_w
        cap = (max_chars[0] if i == 0 else max_chars[1]) if max_chars else None
        for j in range(i + 1, n + 1):
            seg = ws[i:j]
            if cap is not None and j - i > 1 and chars(" ".join(seg)) > cap:
                break
            last = j == n
            nxt = wm.next_char_w(ws[j]) if not last else 0.0
            c = wm.line_cost(seg, avail, last, nxt)
            if c is None:
                if wm.natural(seg) - wm.slack(seg) - wm.compressible(seg) > wm.target(avail) and j - i > 1:
                    break                       # 더 붙여도 넘친다
                continue
            v = best[i] + c + 1.0
            if v < best[j]:
                best[j], prev[j] = v, i
    if best[n] == INF:
        return None
    out, j = [], n
    while j > 0:
        out.append(" ".join(ws[prev[j]:j]))
        j = prev[j]
    return out[::-1]


def count_lines(text, first_w, rest_w, wm):
    """줄 수 어림(글을 고치지 않음). 원고에 \\n 이 있으면 그 줄 수."""
    return len(wrap(text, first_w, rest_w, wm))


def line_deltas(lines, first_w, rest_w, wm):
    """줄마다 넣을 자간(%, 정수) 목록 — 넘치는 줄은 음수, (stretch 가 있으면) 다음 글자가 들어올 자리가 남는 줄은 양수."""
    out = []
    for k, line in enumerate(lines):
        avail = first_w if k == 0 else rest_w
        last = k == len(lines) - 1
        delta, _ = wm.line_delta(words(line.strip()), avail, last=last, next_w=0.0 if last else wm.next_char_w(lines[k + 1]))
        out.append(delta)
    return out


def check_lines(lines, first_w, rest_w, wm):
    """주어진 줄들 점검 → [(줄 번호, 'over'|'loose', 자연 폭, 줄 폭)].
    over = 자간을 한도까지 줄여도 넘치는 줄(한글이 다시 나눈다), loose = 자간을 한도까지 늘려도 헐거운 줄."""
    bad = []
    for k, line in enumerate(lines):
        avail = first_w if k == 0 else rest_w
        ws = words(line.strip())
        last = k == len(lines) - 1
        _, state = wm.line_delta(ws, avail, last=last, next_w=0.0 if last else wm.next_char_w(lines[k + 1]))
        if state != "ok":
            bad.append((k + 1, state, wm.natural(ws), avail))
    return bad


def chars(line):
    return len(plain(line).replace("\x1f", " ").replace("\x1e", " "))
