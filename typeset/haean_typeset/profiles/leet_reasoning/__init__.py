# -*- coding: utf-8 -*-
"""LEET 추리논증 문제지 프로필 (A3 2단, 한 단 한 문항, 40문항 20쪽).

core 는 이 프로필의 값·규칙을 이 객체를 통해서만 쓴다.
"""
import copy
import os
import re

from ...core.context import Ctx
from ...core.hwpx import (top_paragraphs, find_element, drop_linesegs, esc, first_element)
from ...core.fit import fit_paragraph
from ...core.headeredit import HeaderEditor
from ...core.linebreak import wrap, check_lines
from ...core.model import Table, Figure
from ...core.template import TemplateDoc, TemplateError
from . import blocks as B
from . import ids as I
from . import layout as L
from . import writer as W

HERE = os.path.dirname(os.path.abspath(__file__))


class LeetReasoning:
    name = "leet_reasoning"
    template_path = None
    ids = I
    max_items = L.MAX_ITEMS
    line_pt = L.LINE
    width = L.WIDTH
    solution_profile = "leet_reasoning_solutions"

    # ── 컨텍스트
    def new_ctx(self):
        return Ctx(style_cs=I.STYLE_CS, char_style=I.CHAR_STYLE, eq_base=1100)

    # ── 원고 검사
    def validate_item(self, number, item, diag, base_dir=None):
        """필드·대응 검사(블록 꼴·라벨·그림·수식은 plan_item 이 함께 알린다). False 면 조판에서 뺀다."""
        ok = True
        if "세트" in item:
            diag.error("SET_NOT_ALLOWED", "LEET 추리논증은 공통지문 세트를 쓰지 않습니다", where=("세트",))
        for k in ("발문", "지문", "선지"):
            if not item.get(k):
                diag.error("MISSING_FIELD", "'%s'이(가) 비어 있습니다" % k, where=(k,), field=k)
                ok = False
        if not ok:
            return False
        bogi = item.get("보기") or []
        texts = [c if isinstance(c, str) else str(c.get("글", "")) for c in item["선지"]]
        used = set(re.findall(r"[ㄱ-ㅁ]", " ".join(texts)))
        have = set("ㄱㄴㄷㄹㅁ"[:len(bogi)])
        if used and not bogi:
            diag.error("BOGI_MISMATCH", "선지에 ㄱ·ㄴ·ㄷ이 있는데 <보기>가 없습니다", where=("선지",))
        elif used - have:
            diag.error("BOGI_MISMATCH", "선지의 %s가 <보기>에 없습니다" % ", ".join(sorted(used - have)),
                       where=("선지",), missing=sorted(used - have))
        if bogi and "<보기>" not in item["발문"]:
            diag.warning("BOGI_NOT_IN_STEM", "<보기>가 있는데 발문에 '<보기>'가 없습니다", where=("발문",))
        return True

    # ── 계획
    def plan_item(self, number, item, diag, ctx, base_dir=None):
        before = len(ctx.unknown_tex)
        plan, = (B.item_plan(number, item, diag, ctx, self.width, base_dir),)
        for name in sorted(set(ctx.unknown_tex[before:])):
            diag.error("UNKNOWN_TEX", "모르는 LaTeX 명령 \\%s" % name.lstrip("\\"), command=name)
        return plan

    plan_paras = staticmethod(B.plan_paras)
    plan_objects = staticmethod(B.plan_objects)
    set_source = staticmethod(B.set_source)
    unwrap = staticmethod(B.unwrap)

    # ── 줄
    def wrap_item(self, number, item, diag, ctx, base_dir=None, check=True):
        """줄이 정해지지 않은 문단을 어절 단위로 나눈 새 원고. 정해진 줄은 점검(LINE_OVERFLOW/LOOSE)."""
        new = copy.deepcopy(item)
        from ...core.diagnostics import Diag
        plan = self.plan_item(number, item, Diag(number), ctx, base_dir)
        for p in self.plan_paras(plan):
            first, rest = p.widths()
            if "\n" in p.text:
                if check:
                    for k, what, nat, avail in check_lines(p.text.split("\n"), first, rest, self.width):
                        if what == "over":
                            diag.warning("LINE_OVERFLOW", "%d째 줄이 넘쳐 한글이 다시 나눕니다(자연 폭 %.0f / 줄 폭 %.0fpt)"
                                         % (k, nat, avail), where=p.src, line=k, natural=round(nat, 1), avail=round(avail, 1))
                        else:
                            diag.warning("LINE_LOOSE", "%d째 줄이 헐겁습니다(자연 폭 %.0f / 줄 폭 %.0fpt)"
                                         % (k, nat, avail), where=p.src, line=k, natural=round(nat, 1), avail=round(avail, 1))
                continue
            caps = (L.line_cap(p.kind, p.indent_pt, True), L.line_cap(p.kind, p.indent_pt, False))
            lines = wrap(p.text, first, rest, self.width, max_chars=caps)
            if len(lines) > 1:
                self.set_source(new, p.src, "\n".join(lines)[len(p.head):])
        return new

    # ── 높이
    def para_h(self, p):
        return p.n_lines() * L.LINE + p.gap_before + p.gap_after

    def block_h(self, plan):
        h = 0.0
        for x in plan:
            if isinstance(x, Table):
                h += x.height
            elif isinstance(x, Figure):
                h += x.height_pt + L.FIG_PARA
            else:
                h += self.para_h(x)
        return h

    def item_height(self, plan):
        h = self.para_h(plan["stem"])
        h += self.block_h(plan["passage"]) + L.BOX_PAD + L.BOX_AFTER
        if plan["bogi"]:
            h += L.BOGI_TITLE + self.block_h(plan["bogi"]) + L.BOX_PAD + L.BOX_AFTER
        h += sum(self.para_h(c) for c in plan["choices"])
        if plan["choice_figs"]:
            h += W.picture_choices_height(plan["choice_figs"], plan["layout"]) + L.FIG_PARA
        return h

    def check_box(self, total):
        return total in L.CHECK_COUNTS

    def capacity(self, number=None, total=None):
        cap = L.COL_H - L.START.get(number, 0.0)
        if number is not None and total is not None and number == total and self.check_box(total):
            cap -= L.CHECK_BOX
        return cap

    def strict_slots(self, number, total):
        return number in (1, 2) or (number == total and self.check_box(total))

    def pages(self, n_items):
        return (n_items + 1) // 2

    # ── 양식
    def open_template(self, ctx, path=None):
        return LeetTemplate(path or self.template_path, ctx)

    def item_xml(self, number, plan, ctx, first, tpl):
        return W.item_xml(number, plan, ctx, first, tpl.pic_skeleton)

    def line_guide(self):
        """입력(작성) 단계 안내: 기출 실측 줄당 글자수·문항 줄 상한(layout.LINE_GUIDE)."""
        return dict(L.LINE_GUIDE)

    def fit_lines(self, plan, ctx, original, keep_breaks=False):
        """정한 줄마다 자간을 입힌다. 예측 줄은 빈칸으로 되돌려(강제 줄 나눔 없음) 한글이 같은 자리에서 접게 하고,
        원고에 처음부터 있던 \\n(작성자가 정한 줄)은 강제 줄 나눔으로 둔다."""
        for p in self.plan_paras(plan):
            first, rest = p.widths()
            authored = "\n" in (B.get_source(original, p.src) or "")
            p.runs, _ = fit_paragraph(p.runs, p.text, first, rest, self.width, ctx, keep_breaks=keep_breaks or authored)


class LeetTemplate:
    """문제지 양식: 표지·바탕쪽은 그대로, 1번 문항 앞까지 두고 그 뒤를 원고로 채운다."""

    def __init__(self, path, ctx):
        self.doc = TemplateDoc(path)
        self.doc.verify_ids(I.EXPECT)
        self.section = self.doc.read("Contents/section0.xml")
        self.masters = {n: drop_linesegs(self.doc.read(n)) for n in self.doc.masters()}
        self.tops = top_paragraphs(self.section)
        self.cut = next((k for k, (a, b) in enumerate(self.tops)
                         if 'paraPrIDRef="%d"' % I.PS_STEM in self.section[a:min(b, a + 300)]
                         and 'styleIDRef="%d"' % I.ST_STEM in self.section[a:min(b, a + 300)]), None)
        if self.cut is None:
            raise TemplateError("TEMPLATE_ITEM", "양식에서 1번 문항(문제 스타일 문단)을 찾지 못했습니다")
        self.check_box, self.check_master = None, None
        for name, xml in self.masters.items():
            span = find_element(xml, "hp:tbl", "확인 사항")
            if span:
                self.check_box, self.check_master = xml[span[0]:span[1]], name
                break
        body = self.section[self.tops[self.cut][0]:]
        self.pic_skeleton = drop_linesegs(body[slice(*first_element(body, "hp:pic"))]) if "<hp:pic " in body else None
        self.sample_bins = self.doc.bin_names()          # 견본 문항 그림(견본을 지우므로 같이 지운다)
        self.editor = HeaderEditor(self.doc.header)       # 줄 맞추기 자간 변형이 여기 붙는다
        ctx.header_editor = self.editor
        ctx.reserve([self.section] + list(self.masters.values()))

    def build(self, out_path, items_xml, figures, title, count, pages, check_box, diag):
        sec = self.section
        head = drop_linesegs(sec[:self.tops[self.cut][0]])
        if title:
            if L.TITLE_PLACEHOLDER in head:
                head = head.replace(L.TITLE_PLACEHOLDER, esc(title), 1)
            else:
                diag.error("TEMPLATE_TITLE", "양식에서 시험명 자리('%s')를 찾지 못했습니다" % L.TITLE_PLACEHOLDER)
        head, k = L.COUNT_TEXT.subn(str(count), head, count=1)
        if not k:
            diag.error("TEMPLATE_COUNT", "유의 사항에서 문항 수 자리를 찾지 못했습니다")
        masters = dict(self.masters)
        if pages is not None:
            head, k0 = L.TOTAL_PAGES.subn(r"\g<1>%d\g<2>" % pages, head)
            found = k0
            for n, x in list(masters.items()):
                masters[n], k1 = L.TOTAL_PAGES.subn(r"\g<1>%d\g<2>" % pages, x)
                found += k1
            if not found:
                diag.error("TEMPLATE_PAGECOUNT", "바탕쪽에서 전체 쪽 수 자리를 찾지 못했습니다")
        body = items_xml
        if self.check_box:
            masters[self.check_master] = masters[self.check_master].replace(self.check_box, "", 1)
            if check_box:
                body += check_para(self.check_box)
        elif check_box:
            diag.error("TEMPLATE_CHECKBOX", "양식 바탕쪽에서 확인 사항 표를 찾지 못했습니다")
        new_sec = head + body + sec[sec.rfind("</hs:sec>"):]
        add = [("BinData/%s.png" % f.bin_id, open(f.abspath, "rb").read(), "image/png", f.bin_id) for f in figures]
        replace = {"Contents/section0.xml": new_sec, "Preview/PrvText.txt": title or "추리논증"}
        if self.editor.added:
            replace["Contents/header.xml"] = self.editor.header
        replace.update(masters)
        self.doc.write(out_path, replace, add_bins=add, drop_bins=self.sample_bins)


def check_para(tbl):
    """바탕쪽 확인 사항 표 → 본문 개체: 쪽 아래, 그 단 왼쪽, 자리 차지."""
    t = drop_linesegs(tbl)
    t = re.sub(r"<hp:pos [^>]*/>",
               '<hp:pos treatAsChar="0" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0"'
               ' vertRelTo="PAGE" horzRelTo="COLUMN" vertAlign="BOTTOM" horzAlign="LEFT" vertOffset="0"'
               ' horzOffset="0"/>', t, count=1)
    t = re.sub(r'textWrap="\w+"', 'textWrap="TOP_AND_BOTTOM"', t, count=1)
    t = t.replace('protect="1"', 'protect="0"', 1)
    return ('<hp:p id="0" paraPrIDRef="%d" styleIDRef="%d" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="%d">%s<hp:t/></hp:run></hp:p>' % (I.PS_CHOICE_32, I.ST_CHOICE, I.CS_NOTE_BLANK, t))


PROFILE = LeetReasoning()
