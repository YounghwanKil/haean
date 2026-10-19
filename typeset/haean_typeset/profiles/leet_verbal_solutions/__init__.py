# -*- coding: utf-8 -*-
"""LEET 언어이해 해설지. 양식: 시대인재 LEET 언어이해 해설 양식(메모 114개, 한 구역: 정답표 한 쪽 + 2단 해설).

짜임(양식 메모 그대로):
- 1쪽: 시험명 · '언어이해 영역 정답표'(13×6, 30문항)
- 2쪽: 머리 상자 · ● 정답(빠른 정답 11×6) · ● 총평(원고에 '총평'이 있을 때만; 그때 세트 해설은 다음 쪽부터)
- 세트마다(새 단에서 시작): 세트 머리 표(번호 범위 · 글의 주제 · 정답 세 개(번호 사이 고정폭 빈칸) · 난이도 별 ·
  내용 영역) → 지문 총평 표 → 10pt 빈 줄 둘
- 문항마다: 번호 → 정답·문항 유형 표 → 출제자의 논평 표(큰 것·작은 것 중 하나 또는 없음) → '정오 판단' 표지 →
  선지 ①~⑤ 판정 줄(정답 선지는 밑줄, 끝에 (○)/(×)) + '↳' 설명 줄
- 메모 ①: 문항이 단·쪽 경계에서 애매하게 끊기면 다음 단으로(높이를 어림해 단 나누기).

원고: 세트 {"세트": {"지문": …, "해설": {"제재", "난이도", "내용영역", "지문총평"}}, "문항": [{…, "해설": {"문항유형",
"논평", "정오판단"(5개 또는 <보기> 수), "선지판단"}}]}.
"""
import os
import re

from ...core.context import Ctx
from ...core.diagnostics import Diag
from ...core.headeredit import HeaderEditor
from ...core.hwpx import top_paragraphs, strip_memos, drop_linesegs, fresh_ids, run_xml, esc, cell_text, \
    replace_text_across
from ...core.inline import runs
from ...core.tables import outer_table, top_cells, replace_cell_content
from ...core.template import TemplateDoc, TemplateError
from ..leet_reasoning_solutions import mark, as_list, lines_of, L8, CIRCLED, NEG, BOGI, answer_of, stars, check_fields

HERE = os.path.dirname(os.path.abspath(__file__))
TITLE_PLACEHOLDER = "2027학년도 시대인재 LEET 시험지명 X회"
AREAS = ("법철학", "인문", "사회", "과학기술", "예술", "법", "경제", "철학", "언어", "역사")

PS_JUDGE, ST_JUDGE, CS_JUDGE, CS_JUDGE_U = 6, 6, 55, 56
PS_EXPL, ST_EXPL, CS_EXPL = 25, 7, 57
PS_GAP, CS_GAP = 0, 31
NUM_FIRST = (37, 19, 52)
NUM_REST = (7, 1, 8)
CS_COMMENT, PS_COMMENT, ST_COMMENT = 22, 17, 5
CS_COMMENT_TITLE = 13
CS_SET_REVIEW, PS_SET_REVIEW, ST_SET_REVIEW = 30, 17, 4
PS_REVIEW, ST_REVIEW, CS_REVIEW = 16, 33, 21

COL_H = 841.86 - 2 * 28.34 - 2 * 42.52
COL_W = (595.28 - 2 * 42.51 - 22.7) / 2


def para(ps, st, rs, cs_empty=CS_GAP, column_break=False, page_break=False, ctx=None):
    body = "".join(run_xml(cs, pcs, ctx) for cs, pcs in rs) or '<hp:run charPrIDRef="%d"/>' % cs_empty
    return ('<hp:p id="2147483648" paraPrIDRef="%d" styleIDRef="%d" pageBreak="%d" columnBreak="%d" merged="0">%s'
            '</hp:p>' % (ps, st, int(page_break), int(column_break), body))


def oneline(text):
    return re.sub(r"\s*\n\s*", " ", text or "")


class VerbalSolTemplate:
    def __init__(self, path, ctx):
        self.doc = TemplateDoc(path)
        s = drop_linesegs(strip_memos(self.doc.read("Contents/section0.xml")))
        self.sec = s
        tops = top_paragraphs(s)
        P = [s[a:b] for a, b in tops]
        T = lambda x: re.sub(r"<[^>]+>", "", x)
        sets = [k for k, p in enumerate(P) if "<hp:tbl" in p and re.search(r"\d+~\d+", T(p)[:20])
                and "글의 주제" in T(p)]
        if not sets:
            raise TemplateError("TEMPLATE_ITEM", "해설 양식에서 세트 머리 표를 찾지 못했습니다")
        k0 = sets[0]
        self.head = P[:k0]
        self.tail = s[tops[-1][1]:]
        blk = P[k0:sets[1]] if len(sets) > 1 else P[k0:]
        find = lambda pred: next(x for x in blk if pred(x))
        self.t_set = blk[0]
        self.t_set_review = find(lambda x: "<hp:tbl" in x and "지문 총평" in T(x))
        self.t_answer = find(lambda x: "<hp:tbl" in x and 'rowCnt="2" colCnt="2"' in x and "문항 유형" in T(x))
        self.t_comment_big = find(lambda x: 'rowCnt="3" colCnt="2"' in x)
        self.t_comment_small = find(lambda x: 'rowCnt="1" colCnt="2"' in x and "논평" in T(x))
        self.t_judge_mark = find(lambda x: "<hp:rect" in x and "판단" in T(x))
        ctx.reserve([s] + [self.doc.read(n) for n in self.doc.masters()])


def table_of(p):
    a, b = outer_table(p)
    return p[:a], p[a:b], p[b:]


def set_text(tbl, rc, text, cs=None, extra_runs=None):
    """칸 첫 문단 모양 그대로 글만 바꾼다(cs 를 주면 그 글자 모양)."""
    a, b = top_cells(tbl)[rc]
    tc = tbl[a:b]
    p = re.search(r"<hp:p [^>]*>", tc).group(0)
    c = cs if cs is not None else int(re.search(r'<hp:run charPrIDRef="(\d+)"', tc).group(1))
    body = extra_runs if extra_runs is not None else (
        '<hp:run charPrIDRef="%d"><hp:t>%s</hp:t></hp:run>' % (c, esc(text)) if text else '<hp:run charPrIDRef="%d"/>' % c)
    return replace_cell_content(tbl, rc, p + body + "</hp:p>")


class LeetVerbalSolutions:
    name = "leet_verbal_solutions"
    template_path = None
    subject = "언어이해"

    def new_ctx(self):
        return Ctx(eq_base=800)

    # ── 검사(문항)
    def check_judgements(self, n, item, sol, diag):
        check_fields(n, item, sol, diag)
        ans = answer_of(item)
        bogi = item.get("보기") or []
        js = sol.get("정오판단") or []
        marked_bogi = len(bogi) > 1
        if marked_bogi and len(js) == len(bogi):
            texts = [c if isinstance(c, str) else str(c.get("글", "")) for c in item.get("선지") or []]
            if ans and len(texts) >= ans:
                want = set(re.findall(r"[ㄱ-ㅇ]", texts[ans - 1]))
                got = {BOGI[k] for k, j in enumerate(js[:len(BOGI)]) if mark(j.get("판정")) == "○"}
                if want and want != got:
                    diag.error("JUDGE_MISMATCH", "정답 %s(%s)인데 ○ 판정은 %s입니다"
                               % (CIRCLED[ans - 1], ", ".join(sorted(want)), ", ".join(sorted(got)) or "없음"),
                               item=n, where=("해설", "정오판단"))
            cj = sol.get("선지판단") or []
        else:
            cj = js
        if cj:
            if len(cj) != 5:
                diag.error("JUDGE_COUNT", "선지 판단이 %d개입니다" % len(cj), item=n, where=("해설", "정오판단"))
            elif ans:
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
    def judge_lines(self, heads, texts, js, ctx, answer_index=None):
        xml, h = [], 0.0
        for k, (head, text, j) in enumerate(zip(heads, texts, js)):
            m = mark(j.get("판정")) or "?"
            hd = (head + ".") if head in BOGI else head
            cs = CS_JUDGE_U if answer_index is not None and k == answer_index else CS_JUDGE
            rs = [(cs, [("t", hd), ("nb",)])] + runs(oneline(text), cs, ctx)      # 선지 글의 밑줄·굵게도 살린다
            rs.append((CS_JUDGE, [("t", " (%s)" % m)]))
            xml.append(para(PS_JUDGE, ST_JUDGE, rs, ctx=ctx))
            h += lines_of(hd + " " + text + " (○)", COL_W, COL_W - 11.0) * L8
            for i, e in enumerate(as_list(j.get("설명"))):
                pre = "↳ " if i == 0 else ""
                xml.append(para(PS_EXPL, ST_EXPL, [(CS_EXPL, [("t", pre)])] + runs(oneline(e), CS_EXPL, ctx), ctx=ctx))
                h += lines_of(pre + e, COL_W - 11.0, COL_W - 11.0) * L8 + 6.0
        return "".join(xml), h

    def item_block(self, n, first_in_set, item, sol, tpl, ctx, diag):
        out, h = [], 0.0
        ps, st, cs = NUM_FIRST if first_in_set else NUM_REST
        out.append(para(ps, st, [(cs, [("t", str(n))])], ctx=ctx))
        h += 15 * 1.6
        pre, t, post = table_of(fresh_ids(tpl.t_answer, ctx))
        ans = answer_of(item)
        t = set_text(t, (0, 1), CIRCLED[ans - 1] if ans else "")
        t = set_text(t, (1, 1), str(sol.get("문항유형", "") or ""))
        out.append(pre + t + post)
        h += 31.0 + 8.5
        c = sol.get("논평")
        if isinstance(c, dict) and c.get("제목"):
            pre, t, post = table_of(fresh_ids(tpl.t_comment_big, ctx))
            t = set_text(t, (0, 1), c["제목"], cs=CS_COMMENT_TITLE)
            paras = "".join(para(PS_COMMENT, ST_COMMENT, runs(oneline(x), CS_COMMENT, ctx), ctx=ctx)
                            for x in as_list(c.get("글")))
            t = replace_cell_content(t, (2, 0), paras)
            out.append(pre + t + post)
            h += 12.7 + 2.8 + 8.0 + sum(lines_of(x, COL_W - 17, COL_W - 12) * 8 * 1.65 for x in as_list(c.get("글"))) + 8.5
        elif c:
            text = c.get("글") if isinstance(c, dict) else c
            pre, t, post = table_of(fresh_ids(tpl.t_comment_small, ctx))
            paras = "".join(para(PS_COMMENT, ST_COMMENT, runs(oneline(x), CS_COMMENT, ctx), ctx=ctx)
                            for x in as_list(text))
            t = replace_cell_content(t, (0, 1), paras)
            out.append(pre + t + post)
            w = 208.5 - 12
            h += max(28.3, 8.0 + sum(lines_of(x, w, w) * 8 * 1.65 for x in as_list(text))) + 8.5
        js = sol.get("정오판단") or []
        if js:
            out.append(fresh_ids(tpl.t_judge_mark, ctx))
            h += 16.0
            bogi = item.get("보기") or []
            choices = [x if isinstance(x, str) else str(x.get("글", "")) for x in item.get("선지") or []]
            if len(bogi) > 1 and len(js) == len(bogi):
                texts = [x if isinstance(x, str) else str(x.get("글", "")) for x in bogi]
                x, hh = self.judge_lines(list(BOGI[:len(bogi)]), texts, js, ctx)
                out.append(x)
                h += hh
                cj = sol.get("선지판단") or []
                if cj:
                    x, hh = self.judge_lines(list(CIRCLED), choices, cj, ctx, answer_index=(ans - 1) if ans else None)
                    out.append(x)
                    h += hh
            else:
                x, hh = self.judge_lines(list(CIRCLED), choices, js, ctx, answer_index=(ans - 1) if ans else None)
                out.append(x)
                h += hh
        return "".join(out), h

    def set_block(self, first, items, sset, tpl, ctx, diag, page_break=False, column_break=False):
        ss = (sset.get("해설") or {}) if isinstance(sset, dict) else {}
        last = first + len(items) - 1
        pre, t, post = table_of(fresh_ids(tpl.t_set, ctx))
        t = set_text(t, (0, 0), "%d~%d" % (first, last))
        t = set_text(t, (0, 1), str(ss.get("제재", "") or ""))
        answers = [answer_of(it) for it in items]
        cs_ans = int(re.search(r'<hp:run charPrIDRef="(\d+)"', t[top_cells(t)[(1, 1)][0]:]).group(1))
        pieces = []
        for k, a in enumerate(answers):
            if k:
                pieces.append(("fw",))
            pieces.append(("t", CIRCLED[a - 1] if a else "?"))
        t = set_text(t, (1, 1), "", extra_runs=run_xml(cs_ans, pieces, ctx))
        lv = ss.get("난이도")
        if lv is not None and not stars(lv):
            diag.error("DIFFICULTY_INVALID", "세트 난이도는 1~5 정수여야 합니다(지금 %r)" % (lv,), item=first,
                       where=("세트", "해설", "난이도"))
        t = set_text(t, (1, 3), stars(lv))
        area = str(ss.get("내용영역", "") or "")
        t = set_text(t, (2, 1), area)
        head = pre + t + post
        head = head.replace('pageBreak="1"', 'pageBreak="%d"' % int(page_break), 1)
        head = re.sub(r'columnBreak="[01]"', 'columnBreak="%d"' % int(column_break), head, count=1)
        out = [head]
        h = 56.5 + 8.5
        pre, t, post = table_of(fresh_ids(tpl.t_set_review, ctx))
        rv = as_list(ss.get("지문총평"))
        paras = "".join(para(PS_SET_REVIEW, ST_SET_REVIEW, runs(oneline(x), CS_SET_REVIEW, ctx), ctx=ctx) for x in rv) \
            or para(PS_SET_REVIEW, ST_SET_REVIEW, [], cs_empty=CS_SET_REVIEW, ctx=ctx)
        t = replace_cell_content(t, (1, 0), paras)
        out.append(pre + t + post)
        h += 19.3 + 8.5 + max(28.3, 4 + sum(lines_of(x, COL_W - 15, COL_W - 10) * 7 * 1.65 for x in rv))
        gap = para(PS_GAP, 0, [], cs_empty=CS_GAP, ctx=ctx)
        out += [gap, gap]
        h += 2 * 10 * 1.6
        return "".join(out), h

    @staticmethod
    def answers_into(tbl, flat, first_row, pairs, rows=10):
        for k in range(pairs * rows):
            r, c = first_row + k % rows, 2 * (k // rows)
            if k < len(flat):
                ans = answer_of(flat[k])
                tbl = cell_text(tbl, (r, c + 1), CIRCLED[ans - 1] if ans else "")
            else:
                tbl = cell_text(tbl, (r, c), "")
                tbl = cell_text(tbl, (r, c + 1), "")
        return tbl

    def build(self, items, out_path, title=None, review=None, diag=None, template_path=None, sets=None):
        """items: 문항 목록(차례대로). sets: [(첫 번호, [문항…], 세트 dict)] — 없으면 문항을 3개씩 묶은 것으로 본다."""
        diag = diag if diag is not None else Diag()
        ctx = self.new_ctx()
        try:
            tpl = VerbalSolTemplate(template_path or self.template_path, ctx)
        except TemplateError as e:
            diag.error(e.code, "해설: " + str(e))
            return None
        editor = HeaderEditor(tpl.doc.header)
        ctx.variants = editor
        if sets is None:
            sets = [(k + 1, items[k:k + 3], {}) for k in range(0, len(items), 3)]
        head = []
        T = lambda x: re.sub(r"<[^>]+>", "", x)
        for k, x in enumerate(tpl.head):
            if title:
                x = replace_text_across(x, TITLE_PLACEHOLDER, title)[0]
            txt = T(x)
            if "<hp:tbl" in x and "정답표" in txt[:40]:
                pre, t, post = table_of(x)
                x = pre + self.answers_into(t, items, 3, 3) + post
            elif "<hp:tbl" in x and txt.lstrip().startswith("● 정답"):
                pre, t, post = table_of(x)
                x = pre + self.answers_into(t, items, 1, 3) + post
            elif "<hp:tbl" in x and "총평" in txt[:10]:
                if not review:
                    continue
                pre, t, post = table_of(x)
                paras = "".join(para(PS_REVIEW, ST_REVIEW, runs(oneline(r), CS_REVIEW, ctx), ctx=ctx)
                                for r in as_list(review))
                x = pre + replace_cell_content(t, (0, 0), paras) + post
            head.append(x)
        parts, used = [], 0.0
        for si, (first, its, sset) in enumerate(sets):
            sx, sh = self.set_block(first, its, sset, tpl, ctx, diag, page_break=(si == 0 and bool(review)),
                                    column_break=(si > 0))
            parts.append(sx)
            used = sh
            for k, it in enumerate(its):
                n = first + k
                sol = it.get("해설")
                if not sol:
                    diag.warning("SOLUTION_MISSING", "'해설'이 없어 정답표에만 넣었습니다", item=n)
                    continue
                self.check_judgements(n, it, sol, diag)
                x, h = self.item_block(n, k == 0, it, sol, tpl, ctx, diag)
                if used + h > COL_H and h <= COL_H:
                    x = x.replace('columnBreak="0"', 'columnBreak="1"', 1)
                    used = 0.0
                if h > COL_H:
                    diag.warning("SOLUTION_LONG", "해설 어림 높이 %.0fpt가 한 단(%.0fpt)보다 깁니다" % (h, COL_H), item=n)
                used = (used + h) % COL_H if used + h > COL_H else used + h
                parts.append(x)
        for name in sorted(set(ctx.unknown_tex)):
            diag.error("UNKNOWN_TEX", "해설: 모르는 LaTeX 명령 \\%s" % name.lstrip("\\"), command=name)
        tops = top_paragraphs(tpl.sec)
        new_sec = tpl.sec[:tops[0][0]] + "".join(head) + "".join(parts) + tpl.tail
        tpl.doc.write(out_path, {"Contents/section0.xml": new_sec, "Contents/header.xml": editor.header,
                                 "Preview/PrvText.txt": (title or self.subject) + " 정답 및 해설"})
        return out_path


PROFILE = LeetVerbalSolutions()
