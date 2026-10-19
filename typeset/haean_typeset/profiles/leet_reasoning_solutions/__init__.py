# -*- coding: utf-8 -*-
"""LEET 추리논증 해설지 프로필 (A4: 1구역 정답표 한 쪽, 2구역 2단 해설).

문제지와 같은 원고(문항마다 `해설`)에서 만든다. 양식 메모(작성 안내)는 결과물에서 지운다.
- 문항: '제재 / 주제'(자동 번호) → 정답·난이도·내용 영역·문항 유형 표 → 출제자의 논평 표(둘 중 하나·없음)
  → '정오 판단' 표지 → 판정 줄(〈보기〉·선지 원문 + (○)/(×)) 과 '↳' 설명 줄.
- 메모 ⑤: 문항이 단 경계에서 애매하게 끊기면 다음 단으로(높이 어림).
"""
import os
import re

from ...core.context import Ctx
from ...core.diagnostics import Diag
from ...core.hwpx import (top_paragraphs, strip_memos, drop_linesegs, fresh_ids, cells, set_cell, cell_text,
                          run_xml, first_element, replace_text_across)
from ...core.inline import runs, plain
from ...core.template import TemplateDoc, TemplateError
from ...core.width import words
from ..leet_reasoning import layout as PL

HERE = os.path.dirname(os.path.abspath(__file__))

# ── 양식 번호
PS_HEAD = 27; ST_HEAD = 8; CS_HEAD = 16              # 제재 / 주제
PS_JUDGE = {"ㄱ": 6, "ㄴ": 23, "ㄷ": 24}
PS_JUDGE_DEFAULT = 6
ST_JUDGE = 9; CS_JUDGE = 11                            # 정오판단_선지: 신명 중명조 8pt
PS_EXPL = 38; ST_EXPL = 10; CS_EXPL = 32; CS_EXPL_B = 4
PS_COMMENT = 17; ST_COMMENT = 29; CS_COMMENT = 30
CS_COMMENT_TITLE = 19
PS_REVIEW = 31; ST_REVIEW = 4; CS_REVIEW = 44; CS_REVIEW_B = 54
PS_END = 10; CS_END = 53
EXPECT = {("paraPr", PS_HEAD): ("intent", 0), ("paraPr", PS_EXPL): ("left", 1350),
          ("charPr", CS_JUDGE): ("height", 800), ("charPr", CS_EXPL): ("height", 800)}

AREAS = ("규범", "인문", "사회", "논리학·수학", "과학기술")
TYPES = ("언어 추리", "논쟁 및 반론", "논증 분석", "논증 평가 및 문제 해결", "모형 추리")   # 법전협 5유형
CIRCLED = "①②③④⑤"
TITLE_PLACEHOLDER = "2027학년도 시대인재 LEET 시험지명 X회"
NEG = re.compile(r"않은|않는|없는|아닌|틀린|부적절한")

# ── 높이 어림 (A4 2단, pt)
COL_H = 841.89 - 2 * 28.34 - 2 * 42.52
COL_W = (595.28 - 2 * 42.51 - 22.68) / 2               # 243.8
L8 = 8 * 1.6
WIDTH = PL.WIDTH.scaled(7.2 / 9.9)                      # 8pt 장평 95% 자간 −5%


BOGI = "ㄱㄴㄷㄹㅁㅂㅅㅇ"


def answer_of(item):
    """정답이 1~5 정수면 그 수, 아니면 None(해설 조립이 멈추지 않게)."""
    a = item.get("정답")
    return a if isinstance(a, int) and not isinstance(a, bool) and 1 <= a <= 5 else None


def stars(lv):
    return ("★" * lv + "☆" * (5 - lv)) if isinstance(lv, int) and not isinstance(lv, bool) and 1 <= lv <= 5 else ""


def check_fields(n, item, sol, diag):
    if item.get("정답") is not None and answer_of(item) is None:
        diag.error("ANSWER_INVALID", "정답은 1~5 정수여야 합니다(지금 %r)" % (item.get("정답"),), item=n, where=("정답",))
    lv = sol.get("난이도") if isinstance(sol, dict) else None
    if lv is not None and not stars(lv):
        diag.error("DIFFICULTY_INVALID", "난이도는 1~5 정수여야 합니다(지금 %r)" % (lv,), item=n, where=("해설", "난이도"))


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def mark(v):
    s = str(v).strip()
    if s in ("○", "O", "o", "0", "True", "true", "옳음", "참"):
        return "○"
    if s in ("×", "X", "x", "False", "false", "그름", "거짓"):
        return "×"
    return None


def lines_of(text, first_w, rest_w):
    ws = words(re.sub(r"\s*\n\s*", " ", plain(text)))
    n, cur, avail = 1, 0.0, first_w
    for w in ws:
        ww = WIDTH.word_w(w)
        add = ww if cur == 0 else WIDTH.space * WIDTH.scale + ww
        if cur and cur + add > avail:
            n, cur, avail = n + 1, ww, rest_w
        else:
            cur += add
    return n


class SolTemplate:
    def __init__(self, path, ctx):
        self.doc = TemplateDoc(path)
        self.doc.verify_ids(EXPECT)
        if "Contents/section1.xml" not in self.doc.names:
            raise TemplateError("TEMPLATE_OPEN", "해설 양식이 아닙니다(2구역이 없음): %s" % path)
        self.sec0 = self.doc.read("Contents/section0.xml")
        s1 = self.doc.read("Contents/section1.xml")
        self.sec1 = s1
        tops = top_paragraphs(s1)
        starts = [i for i, (a, b) in enumerate(tops) if 'paraPrIDRef="%d" styleIDRef="%d"' % (PS_HEAD, ST_HEAD) in s1[a:a + 200]]
        if not starts:
            raise TemplateError("TEMPLATE_ITEM", "해설 양식에서 '제재 / 주제' 문단을 찾지 못했습니다")
        self.first_item = tops[starts[0]][0]
        P = [s1[a:b] for a, b in tops]
        self.head = P[:starts[0]]
        item = P[starts[0]:starts[1] if len(starts) > 1 else len(P)]
        clean = lambda x: drop_linesegs(strip_memos(x))
        find = lambda pred: next(clean(x) for x in item if pred(x))
        self.t_answer = find(lambda x: 'rowCnt="2" colCnt="4"' in x)
        self.t_comment_big = find(lambda x: 'rowCnt="3" colCnt="2"' in x)
        self.t_comment_small = find(lambda x: 'rowCnt="1" colCnt="2"' in x)
        self.t_judge_mark = find(lambda x: "<hp:rect" in x and "판단" in re.sub(r"<[^>]+>", "", x))
        self.tail = s1[s1.rfind("</hs:sec>"):]
        ctx.reserve([self.sec0, self.sec1] + [self.doc.read(n) for n in self.doc.masters()])


def para(ps, st, rs, ctx, column_break=False, pid="2147483648"):
    body = "".join(run_xml(cs, pcs, ctx) for cs, pcs in rs) or '<hp:run charPrIDRef="%d"/>' % CS_END
    return ('<hp:p id="%s" paraPrIDRef="%d" styleIDRef="%d" pageBreak="0" columnBreak="%d" merged="0">%s</hp:p>'
            % (pid, ps, st, int(column_break), body))


def styled(text, base, bold, ctx):
    """<b> 를 이 자리의 강조 글자 모양으로. 줄바꿈 \\n 은 빈칸(해설은 한글이 줄을 나눈다)."""
    saved = ctx.style_cs.get("b")
    ctx.style_cs["b"] = bold
    try:
        return runs(re.sub(r"\s*\n\s*", " ", text), base, ctx)
    finally:
        ctx.style_cs["b"] = saved


def choice_text(c):
    return c if isinstance(c, str) else str(c.get("글", "") or "(그림)")


class LeetReasoningSolutions:
    name = "leet_reasoning_solutions"
    template_path = None
    subject = "추리논증"            # 양식에 든 과목 이름(정답표 제목·머리 상자). 다른 과목 해설은 이것만 바꿔 쓴다
    template_subject = "추리논증"
    areas = AREAS                   # None 이면 내용 영역을 검사하지 않는다
    types = TYPES

    def new_ctx(self):
        # 문제지 양식의 글자 스타일 번호는 해설 양식에서 뜻이 달라 쓰지 않는다
        from ..leet_reasoning import ids as PI
        return Ctx(style_cs=PI.STYLE_CS, char_style={}, eq_base=800)

    # ── 검사
    def check_judgements(self, n, item, sol, diag):
        check_fields(n, item, sol, diag)
        ans = answer_of(item)
        bogi = item.get("보기") or []
        js = sol.get("정오판단") or []
        texts = [choice_text(c) for c in item.get("선지") or []]
        # <보기>가 있어도 선지가 ㄱ·ㄴ 조합이 아니면(순서 나열형·값 선택형 — 보기는 사례·재료) 판정은 선지별이다
        combo = bool(bogi) and all(re.fullmatch(r"[ㄱ-ㅇ](\s*,\s*[ㄱ-ㅇ])*", t.strip()) for t in texts if t.strip())
        if bogi and not combo and not js and sol.get("선지판단"):
            bogi = []
        if bogi:
            if len(js) != len(bogi):
                diag.error("JUDGE_COUNT", "정오판단 %d개, <보기> %d개" % (len(js), len(bogi)), item=n,
                           where=("해설", "정오판단"))
            if ans and len(texts) >= ans:
                want = set(re.findall(r"[ㄱ-ㅇ]", texts[ans - 1]))
                got = {BOGI[k] for k, j in enumerate(js[:len(BOGI)]) if mark(j.get("판정")) == "○"}
                if want != got:
                    diag.error("JUDGE_MISMATCH", "정답 %s(%s)인데 ○ 판정은 %s입니다"
                               % (CIRCLED[ans - 1], ", ".join(sorted(want)), ", ".join(sorted(got)) or "없음"),
                               item=n, where=("해설", "정오판단"))
            cj = sol.get("선지판단") or []
        else:
            cj = js
        if cj:
            if len(cj) != 5:
                diag.error("JUDGE_COUNT", "선지 판단이 %d개입니다" % len(cj), item=n, where=("해설", "정오판단"))
            if ans and len(cj) == 5:
                neg = bool(NEG.search(item.get("발문", "")))
                odd = "×" if neg else "○"
                hits = [k + 1 for k, j in enumerate(cj) if mark(j.get("판정")) == odd]
                if hits != [ans]:
                    diag.error("JUDGE_MISMATCH", "발문이 '%s' 고르기인데 %s 판정이 %s입니다(정답 %s)"
                               % ("옳지 않은 것" if neg else "옳은 것", odd,
                                  ", ".join(CIRCLED[h - 1] for h in hits) or "없음", CIRCLED[ans - 1]),
                               item=n, where=("해설", "정오판단"))
        for k, j in enumerate(js + (sol.get("선지판단") or [])):
            if mark(j.get("판정")) is None:
                diag.error("JUDGE_UNREADABLE", "%d째 판정 '%s'을 ○/×로 읽지 못했습니다" % (k + 1, j.get("판정")),
                           item=n, where=("해설", "정오판단", k))

    # ── 블록
    def judge_block(self, heads, texts, js, ctx):
        xml, h = [], 0.0
        for head, text, j in zip(heads, texts, js):
            m = mark(j.get("판정")) or "?"
            ps = PS_JUDGE.get(head, PS_JUDGE_DEFAULT)
            hd = (head + ".") if head in BOGI else head
            rs = [(CS_JUDGE, [("t", hd), ("nb",)])] + styled(text, CS_JUDGE, CS_JUDGE, ctx)
            rs[-1][1].append(("t", " (%s)" % m))
            xml.append(para(ps, ST_JUDGE, rs, ctx))
            h += lines_of(hd + " " + text + " (○)", COL_W, COL_W - 11.5) * L8
            for k, e in enumerate(as_list(j.get("설명"))):
                pre = "↳ " if k == 0 else ""
                xml.append(para(PS_EXPL, ST_EXPL, [(CS_EXPL, [("t", pre)])] + styled(e, CS_EXPL, CS_EXPL_B, ctx), ctx))
                h += lines_of(pre + e, COL_W - 3.5, COL_W - 13.5) * L8 + 8.0
        return "".join(xml), h

    def item_block(self, n, item, sol, tpl, ctx, diag):
        head = para(PS_HEAD, ST_HEAD, styled(sol.get("제재", ""), CS_HEAD, CS_HEAD, ctx), ctx)
        h = 9 * 1.6
        t = fresh_ids(tpl.t_answer, ctx)
        ans = answer_of(item)
        t = cell_text(t, (0, 1), CIRCLED[ans - 1] if ans else "")
        lv = sol.get("난이도")
        t = cell_text(t, (0, 3), stars(lv))
        area, typ = sol.get("내용영역", ""), sol.get("문항유형", "")
        # 내용 영역은 '대분류(세부)'로 찍는다(양식 메모: 규범(법) / 인문(법,철학,논리,역사) / …). 목록은 대분류만 본다
        if self.areas and area and re.sub(r"\s*[(（].*$", "", area).replace(" ", "") not in [a.replace(" ", "") for a in self.areas]:
            diag.warning("AREA_UNKNOWN", "내용 영역 '%s'은 양식 목록(%s)에 없습니다" % (area, " / ".join(self.areas)),
                         item=n, where=("해설", "내용영역"))
        if self.types and typ and typ not in self.types:
            diag.warning("TYPE_UNKNOWN", "문항 유형 '%s'은 양식 목록(%s)에 없습니다" % (typ, " / ".join(self.types)),
                         item=n, where=("해설", "문항유형"))
        t = cell_text(t, (1, 1), area)
        t = cell_text(t, (1, 3), typ)
        body = [t]
        h += 33.0 + 8.5
        c = sol.get("논평")
        if isinstance(c, dict) and c.get("제목"):
            t = fresh_ids(tpl.t_comment_big, ctx)
            a, b = cells(t)[(0, 1)]
            p0 = re.search(r"<hp:p [^>]*>", t[a:b]).group(0)
            t = set_cell(t, (0, 1), p0 + "".join(run_xml(cs, pc, ctx) for cs, pc in
                                                 styled(c["제목"], CS_COMMENT_TITLE, CS_COMMENT_TITLE, ctx)) + "</hp:p>")
            paras = "".join(para(PS_COMMENT, ST_COMMENT, styled(x, CS_COMMENT, CS_COMMENT, ctx), ctx)
                            for x in as_list(c.get("글")))
            t = set_cell(t, (2, 0), paras)
            body.append(t)
            h += 12.7 + 2.8 + 17.0 + sum(lines_of(x, COL_W - 17, COL_W - 17) * 8 * 1.65 for x in as_list(c.get("글"))) + 8.5
        elif c:
            text = c.get("글") if isinstance(c, dict) else c
            t = fresh_ids(tpl.t_comment_small, ctx)
            paras = "".join(para(PS_COMMENT, ST_COMMENT, styled(x, CS_COMMENT, CS_COMMENT, ctx), ctx)
                            for x in as_list(text))
            t = set_cell(t, (0, 1), paras)
            body.append(t)
            w = 208.5 - 17
            h += max(28.3, 17.0 + sum(lines_of(x, w, w) * 8 * 1.65 for x in as_list(text))) + 8.5
        bogi = [b if isinstance(b, str) else str(b.get("글", "") or "(그림)") for b in item.get("보기") or []]
        texts = [choice_text(x) for x in item.get("선지") or []]
        js = sol.get("정오판단") or []
        if not js and sol.get("선지판단"):      # 보기가 사례·재료인 문항(순서 나열형 등): 선지별 판정만 찍는다
            js, bogi = sol.get("선지판단"), []
        if js:
            body.append(fresh_ids(tpl.t_judge_mark, ctx))
            h += 16.0
            if bogi:
                x, hh = self.judge_block(list(BOGI[:len(bogi)]), bogi, js, ctx)
                body.append(x)
                h += hh
                cj = sol.get("선지판단") or []
                if cj:
                    body.append(para(PS_EXPL, ST_EXPL, [], ctx))
                    x, hh = self.judge_block(list(CIRCLED), texts, cj, ctx)
                    body.append(x)
                    h += hh + L8
            else:
                x, hh = self.judge_block(list(CIRCLED), texts, js, ctx)
                body.append(x)
                h += hh
        body.append('<hp:p id="0" paraPrIDRef="%d" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                    '<hp:run charPrIDRef="%d"/></hp:p>' % (PS_END, CS_END))
        h += 10 * 1.6
        return head, "".join(body), h

    @staticmethod
    def answers_into(tbl, items, first_row, total):
        for k in range(40):
            r, c = first_row + k % 10, 2 * (k // 10)
            if k < total:
                ans = answer_of(items[k])
                tbl = cell_text(tbl, (r, c + 1), CIRCLED[ans - 1] if ans else "")
            else:
                tbl = cell_text(tbl, (r, c), "")
                tbl = cell_text(tbl, (r, c + 1), "")
        return tbl

    @staticmethod
    def replace_table(xml, fn):
        a, b = first_element(xml, "hp:tbl")
        return xml[:a] + fn(xml[a:b]) + xml[b:]

    # ── 조립
    def build(self, items, out_path, title=None, review=None, diag=None, template_path=None):
        diag = diag if diag is not None else Diag()
        ctx = self.new_ctx()
        try:
            tpl = SolTemplate(template_path or self.template_path, ctx)
        except TemplateError as e:
            diag.error(e.code, "해설: " + str(e))
            return None
        total = len(items)

        s0 = drop_linesegs(strip_memos(tpl.sec0))
        if self.subject != self.template_subject:
            s0 = s0.replace(self.template_subject, self.subject)
        if title:
            s0 = replace_text_across(s0, TITLE_PLACEHOLDER, title)[0]
        tops0 = top_paragraphs(s0)
        i_tbl = next(k for k, (a, b) in enumerate(tops0) if 'rowCnt="13"' in s0[a:b])
        a, b = tops0[i_tbl]
        s0 = s0[:a] + self.replace_table(s0[a:b], lambda t: self.answers_into(t, items, 3, total)) + s0[b:]

        head = [drop_linesegs(strip_memos(x)) for x in tpl.head]
        if self.subject != self.template_subject:
            head = [x.replace(self.template_subject, self.subject) for x in head]
        if title:
            head = [replace_text_across(x, TITLE_PLACEHOLDER, title)[0] for x in head]
        out_head, used = [], 0.0
        for x in head:
            if 'rowCnt="11" colCnt="8"' in x:
                x = self.replace_table(x, lambda t: self.answers_into(t, items, 1, total))
                used += 16 + 207.4
            elif "총평" in re.sub(r"<[^>]+>", "", x[:600]) and 'rowCnt="1" colCnt="1"' in x:
                if not review:
                    continue
                paras = "".join(para(PS_REVIEW, ST_REVIEW, styled(r, CS_REVIEW, CS_REVIEW_B, ctx), ctx, pid="0")
                                for r in as_list(review))
                x = self.replace_table(x, lambda t: set_cell(t, (0, 0), paras))
                used += 16 + 338.8
            elif "<hp:rect" in x:
                used += 63.0 + 11.3
            else:
                used += 16.0
            out_head.append(x)

        parts, first = [], True
        for n, item in enumerate(items, 1):
            sol = item.get("해설")
            if not sol:
                diag.warning("SOLUTION_MISSING", "'해설'이 없어 정답표에만 넣었습니다", item=n)
                continue
            self.check_judgements(n, item, sol, diag)
            hx, bx, h = self.item_block(n, item, sol, tpl, ctx, diag)
            # 한 단에 한 문항: 첫 해설만 머리(정답표·총평) 아래에 이어 두고(안 들어가면 다음 단), 나머지는 늘 새 단
            if not first or used + h > COL_H:
                hx = hx.replace('columnBreak="0"', 'columnBreak="1"', 1)
            first = False
            if h > COL_H:
                diag.warning("SOLUTION_LONG", "해설 어림 높이 %.0fpt가 한 단(%.0fpt)보다 길어 다음 단으로 넘칩니다"
                             % (h, COL_H), item=n, height_pt=round(h, 1), capacity_pt=COL_H)
            used = h
            parts.append(hx + bx)
        for name in sorted(set(ctx.unknown_tex)):
            diag.error("UNKNOWN_TEX", "해설: 모르는 LaTeX 명령 \\%s" % name.lstrip("\\"), command=name)

        s1 = drop_linesegs(strip_memos(tpl.sec1[:tpl.first_item]))
        tops1 = top_paragraphs(s1)
        s1 = s1[:tops1[0][0]] + "".join(out_head) + "".join(parts) + tpl.tail
        tpl.doc.write(out_path, {"Contents/section0.xml": s0, "Contents/section1.xml": s1,
                                 "Preview/PrvText.txt": (title or self.subject) + " 정답 및 해설"})
        return out_path


PROFILE = LeetReasoningSolutions()
