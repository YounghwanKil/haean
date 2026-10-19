# -*- coding: utf-8 -*-
"""LEET 언어이해 문제지(30문항·15쪽 기본). 양식: 시대인재 LEET 언어이해 양식(template.hwpx).

PSAT 엔진(psat_common)의 흐름 조판을 쓰고, 언어이해 양식에 맞게 바꾼 것:
- 공통지문 세트가 기본: [1~3] 머리 → 지문(문단 테두리로 이어지는 상자) → 문항들(한 단에 들어가면 이어서).
- 발문 번호는 양식 문단 모양의 자동 번호(문제 스타일)가 붙인다. 원고 발문에는 번호를 쓰지 않는다.
- 선지: ① + 묶음 빈칸 + 글(답-1 스타일, 내어쓰기).
- <보기>: 제목이 위 테두리에 걸린 상자(양식에 견본이 없어 표로 만든다. 테두리 모양은 header 에 덧붙임).
- 표지: 시험명·문항 수·전체 쪽 수(표지 쪽 번호 상자와 바탕쪽 2곳)를 바꾼다.
"""
import os
import re

from ...core.diagnostics import Diag
from ...core.flow import Block
from ...core.hwpx import esc, run_xml, top_paragraphs, pic_xml, replace_text_across, drop_linesegs
from ...core.inline import runs, NB
from ...core.template import TemplateError
from ..leet_reasoning.layout import WIDTH as REASONING_WIDTH
from ..psat_common.engine import PsatProfile, Geometry, TP, Box, DataTable, Fig, spaced_title
from ..psat_common.style import Role, TableStyle, PsatStyle

HERE = os.path.dirname(os.path.abspath(__file__))
SETHEAD = re.compile(r"^\s*\[\s*\d+\s*[~～]\s*\d+\s*\]")

STYLE = PsatStyle(
    name="leet_verbal", subject="언어이해", template="template.hwpx",
    title_text="2028학년도 시대인재 LEET 시험지명 X회",
    stem=Role(38, 5, 5),
    stem_head1="", stem_head2="",
    choice=Role(7, 10, 5), choice_head="",
    spacer_top=Role(11, 0, 17), spacer_between=Role(11, 0, 17),
    holder=Role(11, 0, 17), holder_head="",
    sethead=Role(1, 1, 4),
    box_text=Role(3, 4, 5), box_text_head="",
    lbox_text=Role(0, 7, 1),
    lbox_title=Role(37, 0, 17),
    bogi=Role(4, 8, 1),
    dialog=Role(26, 18, 5),
    bullet=Role(39, 4, 10),
    law=Role(3, 4, 5), lawitem=Role(3, 4, 5),
    ho=Role(39, 4, 10), mok=Role(39, 4, 10),
    note=Role(39, 4, 10),
    subtitle=Role(40, 4, 5),
    figure=Role(40, 4, 5), figure_title=Role(40, 4, 5),
    table=TableStyle(title=Role(37, 0, 17), unit=Role(6, 13, 8), note=Role(39, 4, 10),
                     cell=Role(37, 0, 17), cell_right=Role(37, 0, 17), cell_left=Role(12, 0, 17),
                     border=3, head_border=3),
    fw=2.6, max_items=30, use_top_spacer=False,
    extra={"box_top": Role(2, 3, 5), "after_box": Role(11, 0, 17), "count_re": r"(?<=<hp:t>)\d+문?항(?=</hp:t>)",
           "pages_re": r'(paraPrIDRef="17" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                       r'<hp:run charPrIDRef="21"><hp:t>)\d+(</hp:t>)',
           "start": {0: 205.0, 1: 88.0}},
)


class VerbalGeometry(Geometry):
    """언어이해 양식: 지문 상자가 표가 아니라 문단 테두리라 상자 견본이 없다."""

    def __init__(self, style, path):
        from ...core.template import TemplateDoc
        from ...core.header import Header
        from ...core.hwpx import drop_linesegs, strip_memos
        doc = TemplateDoc(path)
        self.doc = doc
        self.H = Header(doc.header)
        sec = drop_linesegs(strip_memos(doc.read("Contents/section0.xml")))
        self.sec = sec
        sp = re.search(r"<hp:pagePr[^>]*>.*?</hp:pagePr>", sec, re.S).group(0)
        mg = {k: int(v) / 100.0 for k, v in re.findall(r'(\w+)="(\d+)"', re.search(r"<hp:margin [^>]*/>", sp).group(0))}
        pw = int(re.search(r'width="(\d+)"', sp).group(1)) / 100.0
        ph = int(re.search(r'height="(\d+)"', sp).group(1)) / 100.0
        col = re.search(r'<hp:colPr[^>]*colCount="(\d+)"[^>]*sameGap="(\d+)"', sec)
        n, gap = int(col.group(1)), int(col.group(2)) / 100.0
        self.col_w = (pw - mg["left"] - mg["right"] - gap * (n - 1)) / n
        self.col_h = ph - mg["top"] - mg["bottom"] - mg["header"] - mg["footer"]
        self.tops = [sec[a:b] for a, b in top_paragraphs(sec)]
        cut = next((k for k, p in enumerate(self.tops) if SETHEAD.match(re.sub(r"<[^>]+>", "", p))), None)
        if cut is None:
            raise TemplateError("TEMPLATE_ITEM", "양식에서 첫 세트 머리([1~3])를 찾지 못했습니다")
        self.cut = cut
        tops = top_paragraphs(sec)
        self.prefix = sec[:tops[cut][0]]
        self.tail = sec[tops[-1][1]:]
        self.box_w = self.col_w - 12.74            # <보기> 상자 폭(LEET 기출: 단 폭보다 좁게, 가운데)
        self.box_out = (0.0, 0.0, 1.41, 1.41)
        self.box_in = (0.0, 0.0, 8.5, 7.08)
        self.lbox_margin = (0.0, 0.0, 8.5, 7.08)       # 좌우 여백은 문단 모양(8.5)이 맡는다
        self.lbox_title_h = 13.82
        self.lbox_title_w = 48.75
        self.lbox_inner = self.box_w
        self.box_inner = self.col_w                 # 지문(문단 테두리): 문단 모양 여백이 안쪽 폭을 정한다
        self.lbox = None
        pm = re.search(r"<hp:pic\b.*?</hp:pic>", sec, re.S)
        self.pic = pm.group(0) if pm else None
        if self.pic is None:
            ref = os.path.join(os.path.dirname(HERE), "leet_reasoning", "template.hwpx")
            try:
                import zipfile
                pm = re.search(r"<hp:pic\b.*?</hp:pic>", zipfile.ZipFile(ref).read("Contents/section0.xml").decode(),
                               re.S)
                self.pic = pm.group(0) if pm else None
            except (OSError, KeyError):
                self.pic = None


class LeetVerbal(PsatProfile):
    shows_total_pages = True

    def __init__(self):
        super().__init__(STYLE, HERE, solution_profile="leet_verbal_solutions", width=REASONING_WIDTH)

    def geo(self):
        if self._geo is None:
            self._geo = VerbalGeometry(self.style, self.template_path)
        return self._geo

    def capacity(self, col=None):
        G = self.geo()
        return G.col_h - self.style.extra["start"].get(col, 0.0)

    # ── 계획: 발문(자동 번호)·선지(① + 묶음 빈칸)
    def stem_tp(self, n, text):
        # 번호는 자동 번호(문단 머리)라 첫 줄도 내어쓰기 자리에서 시작한다
        return self._tp(self.style.stem, text, self.geo().col_w, "발문", ("발문",), tab_head=True)

    def choice_plan(self, n, choices, diag, base_dir, item):
        S, G = self.style, self.geo()
        if len(choices) != 5:
            diag.error("CHOICE_COUNT", "선지가 %d개입니다(5개여야 함)" % len(choices), where=("선지",),
                       count=len(choices))
        out = []
        for k, c in enumerate(choices):
            text = c if isinstance(c, str) else str(c.get("글", ""))
            m = re.match(r"^\s*[①-⑤]\s*", text) if isinstance(c, str) else None
            prefix = m.group(0) if m else ""
            out.append(("tp", self._tp(S.choice, text[len(prefix):], G.col_w, "선지", ("선지", k), prefix,
                                       head="①②③④⑤⑥"[min(k, 5)] + NB)))
            if isinstance(c, dict) and ("그림" in c or "표" in c):
                diag.error("CHOICE_FIGURE_MIXED", "언어이해 선지에는 그림·표를 넣지 않습니다", where=("선지", k))
        return out, "한 줄에 하나"

    def bogi_box(self, items, diag=None, base_dir=None):
        """언어이해 <보기>: ㄱ. ㄴ. 이 있으면 내어쓰기 문단, 없으면 줄글(박스내용). 그림을 붙일 수 있다."""
        G, S = self.geo(), self.style
        box = Box("보  기", [], ("보기",))
        box.inner_w = G.lbox_inner
        marked = len(items) > 1
        for k, v in enumerate(items):
            text = v if isinstance(v, str) else str(v.get("글", ""))
            m = re.match(r"^\s*([ㄱ-ㅇ])\s*\.\s*", text)
            prefix = m.group(0) if m else ""
            body = text[len(m.group(0)):] if m else text
            if marked:
                head = "ㄱㄴㄷㄹㅁㅂㅅㅇ"[k] + "." + NB
                box.content.append(self._tp(S.bogi, body, G.lbox_inner, "보기", ("보기", k), prefix,
                                            head=head, indent=-self.width.word_w(head)))
            else:
                box.content.append(self._tp(S.lbox_text, body, G.lbox_inner, "보기", ("보기", k), prefix))
            if isinstance(v, dict) and v.get("그림"):
                f = self.load_figure(v, ("보기", k), diag or Diag(), base_dir, G.lbox_inner - 20)
                if f:
                    box.content.append(f)
        return box

    def text_block(self, b, container, src, diag, boxed=True, lbox=False):
        tp = super().text_block(b, container, src, diag, boxed=boxed, lbox=lbox)
        if tp.kind == "발언":                       # 대화체: 지문(대화체) 문단, 라벨 + 고정폭 빈칸
            tp.variant = None
        return tp

    def plan_set(self, first, last, s, diag, base_dir):
        S, G = self.style, self.geo()
        guide = s.get("안내") or "다음 글을 읽고 물음에 답하시오."
        tp = self._tp(S.sethead, guide, G.col_w, "세트 머리", ("세트", "안내"), wrap_lines=False)
        tp.raw_runs = ('<hp:run charPrIDRef="2"><hp:t charStyleIDRef="2">[</hp:t></hp:run>'
                       '<hp:run charPrIDRef="4"><hp:t>%d~%d</hp:t></hp:run>'
                       '<hp:run charPrIDRef="2"><hp:t charStyleIDRef="2">] </hp:t></hp:run>' % (first, last))
        tp.head = "[%d~%d] " % (first, last)
        blocks = s.get("지문") or []
        box = Box("", [], ("세트", "지문"))
        box.inner_w = G.col_w
        body = []
        for k, b in enumerate(blocks):
            src = ("세트", "지문", k)
            if isinstance(b, dict) and "상자" in b:
                content = b.get("내용") or []
                if isinstance(content, str):
                    content = [content]
                if not (b.get("상자") or "").strip():        # 제목 없는 상자 = 지문 문단으로
                    for j, x in enumerate(content):
                        self._box_item(box, x, G.col_w, src + ("내용", j), diag, base_dir)
                    continue
                inner = Box(spaced_title(b.get("상자")), [], src)
                inner.inner_w = G.lbox_inner
                for j, x in enumerate(content):
                    self._box_item(inner, x, G.lbox_inner, src + ("내용", j), diag, base_dir, lbox=True)
                box.content.append(inner)
                continue
            self._box_item(box, b, G.col_w, src, diag, base_dir)
        body.append(box)
        self._tex_check(s, diag)
        return {"head": tp, "body": body}

    # ── XML
    def tp_xml(self, tp, ctx, editor, auto_break=True):
        if getattr(tp, "raw_runs", None):
            body = "".join(run_xml(cs, pcs, ctx) for cs, pcs in runs(tp.body, tp.cs, ctx))
            return ('<hp:p id="2147483648" paraPrIDRef="%d" styleIDRef="%d" pageBreak="0" columnBreak="0" merged="0">'
                    '%s%s</hp:p>' % (tp.ps, tp.st, tp.raw_runs, body))
        return super().tp_xml(tp, ctx, editor, auto_break)

    def box_height(self, box):
        """지문 상자(문단 테두리): 첫 줄 여백 문단 + 글 문단들."""
        G = self.geo()
        if box.title:
            inner = sum(x.height if isinstance(x, TP) else self.table_block_height(x, True) if isinstance(x, DataTable)
                        else x.height_pt + 10.0 for x in box.content)
            m = G.lbox_margin
            box.height = G.lbox_title_h + inner + m[2] + m[3]
            return box.height
        top = self.style.extra["box_top"]
        h = G.H.pitch(top.ps, top.cs)
        for x in box.content:
            if isinstance(x, TP):
                h += x.height
            elif isinstance(x, Box):
                h += self.box_height(x) + 4.0
            elif isinstance(x, DataTable):
                h += self.table_block_height(x, True)
            elif isinstance(x, Fig):
                h += x.height_pt + 10.0 + (x.title_tp.height if x.title_tp else 0)
        box.height = h
        return h

    def titled_box_xml(self, box, ctx, editor, auto_break):
        """제목이 위 테두리에 걸린 3×3 표(PSAT 제목 상자와 같은 짜임). 테두리 모양은 header 에 덧붙인다."""
        G = self.geo()
        bf_all = 9
        bf = {
            "b": editor.border_fill(bf_all, keep=("bottom",)),
            "lt": editor.border_fill(bf_all, keep=("left", "top")),
            "rt": editor.border_fill(bf_all, keep=("right", "top")),
            "lrb": editor.border_fill(bf_all, keep=("left", "right", "bottom")),
            "none": editor.border_fill(bf_all, keep=()),
        }
        inner = self.content_xml(box.content, ctx, editor, auto_break) or self.empty_xml(self.style.lbox_text)
        title_txt = "<%s>" % box.title
        tw = max(G.lbox_title_w, self.width.text_w(title_txt) + 12.0)
        side = (G.box_w - tw) / 2.0
        half = G.lbox_title_h / 2.0
        T = self.style.lbox_title
        title_p = ('<hp:p id="2147483648" paraPrIDRef="%d" styleIDRef="%d" pageBreak="0" columnBreak="0" merged="0">'
                   '<hp:run charPrIDRef="%d"><hp:t>%s</hp:t></hp:run></hp:p>' % (T.ps, T.st, T.cs, esc(title_txt)))
        empty = '<hp:p id="2147483648" paraPrIDRef="11" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">' \
                '<hp:run charPrIDRef="45"/></hp:p>'
        content_h = box.height - G.lbox_title_h
        m = G.lbox_margin
        r0 = (self.tc(empty, 0, 0, side, half, bf["b"], (0, 0, 0, 0)) +
              self.tc(title_p, 1, 0, tw, G.lbox_title_h, bf["none"], (0, 0, 0, 0), rowspan=2) +
              self.tc(empty, 2, 0, side, half, bf["b"], (0, 0, 0, 0)))
        r1 = (self.tc(empty, 0, 1, side, half, bf["lt"], (0, 0, 0, 0)) +
              self.tc(empty, 2, 1, side, half, bf["rt"], (0, 0, 0, 0)))
        r2 = self.tc(inner, 0, 2, G.box_w, content_h, bf["lrb"], m, colspan=3, valign="TOP")
        return (self.tbl_open(ctx, 3, 3, G.box_w, box.height, bf["none"], G.box_out, (0, 0, 0, 0)) +
                "<hp:tr>%s</hp:tr><hp:tr>%s</hp:tr><hp:tr>%s</hp:tr></hp:tbl>" % (r0, r1, r2))

    def box_xml(self, box, ctx, editor, auto_break):
        return self.titled_box_xml(box, ctx, editor, auto_break)

    def obj_blocks(self, x, ctx, editor, auto_break):
        S, G = self.style, self.geo()
        if isinstance(x, Box) and not x.title:
            # 지문: 위 여백 문단(테두리 시작) + 글 문단들 + 상자 뒤 빈 줄
            self.box_height(x)
            top = S.extra["box_top"]
            out = [Block(self.empty_xml(top), G.H.pitch(top.ps, top.cs), "지문 위", x.src)]
            for y in x.content:
                if isinstance(y, TP):
                    out.append(self.tp_block(y, ctx, editor, auto_break))
                elif isinstance(y, Box):
                    self.box_height(y)
                    xml = self.holder_xml(self.titled_box_xml(y, ctx, editor, auto_break),
                                          role=Role(40, 4, 5), head="")
                    out.append(Block(xml, y.height + 4.0, "상자", y.src))
                elif isinstance(y, DataTable):
                    xml = self.table_paras_xml(y, ctx, editor, auto_break, inside=True)
                    out.append(Block(xml, self.table_block_height(y, True), "표", y.src))
                elif isinstance(y, Fig):
                    xml = ((self.tp_xml(y.title_tp, ctx, editor, False) if y.title_tp else "") +
                           self.holder_xml(pic_xml(G.pic, y, ctx),
                                           role=S.figure, head=""))
                    out.append(Block(xml, y.height_pt + 10.0 + (y.title_tp.height if y.title_tp else 0), "그림", y.src))
            aft = S.extra["after_box"]
            out.append(Block(self.empty_xml(aft), G.H.pitch(aft.ps, aft.cs), "빈 줄"))
            return out
        if isinstance(x, Box):
            self.box_height(x)
            xml = self.holder_xml(self.titled_box_xml(x, ctx, editor, auto_break), role=Role(37, 0, 17), head="")
            return [Block(xml, x.height + 2.82 + 6.0, "보기", x.src)]
        return super().obj_blocks(x, ctx, editor, auto_break)

    def item_blocks(self, plan, ctx, editor, auto_break):
        bl = super().item_blocks(plan, ctx, editor, auto_break)
        return bl

    def prefix_xml(self, G):
        return G.prefix

    # ── 조판 조립(표지)
    def build(self, G, editor, out_path, body, figures, title, diag):
        S = self.style
        prefix, tail = G.prefix, G.tail
        n_items = self._n_items
        pages = self._pages
        if title:
            prefix, k = replace_text_across(prefix, S.title_text, title)
            if not k:
                diag.error("TEMPLATE_TITLE", "양식 표지에서 시험명 자리('%s')를 찾지 못했습니다" % S.title_text)
        prefix, k = re.subn(S.extra["count_re"], "%d문항" % n_items, prefix, count=1)
        if not k:
            diag.error("TEMPLATE_COUNT", "양식 표지에서 문항 수 자리를 찾지 못했습니다")
        pages_re = re.compile(S.extra["pages_re"])
        replace = {}
        if pages is not None:
            prefix, k1 = pages_re.subn(lambda m: "%s%d%s" % (m.group(1), pages, m.group(2)), prefix)
            k2 = 0
            for name in G.doc.masters():
                x = G.doc.read(name)
                x2, kk = pages_re.subn(lambda m: "%s%d%s" % (m.group(1), pages, m.group(2)), x)
                if kk:
                    replace[name] = drop_linesegs(x2)        # 글을 바꾼 문단의 옛 줄 정보는 지운다(변조 판정 방지)
                    k2 += kk
            if not (k1 or k2):
                diag.error("TEMPLATE_PAGECOUNT", "양식에서 전체 쪽 수 자리를 찾지 못했습니다")
        new_sec = prefix + body + tail
        add, seen = [], set()
        for f in figures:
            if f.bin_id in seen:
                continue
            seen.add(f.bin_id)
            with open(f.abspath, "rb") as fh:
                add.append(("BinData/%s.png" % f.bin_id, fh.read(), "image/png", f.bin_id))
        reserved = self.reserved_bins(G)
        drop = [n for n in G.doc.bin_names() if os.path.splitext(os.path.basename(n))[0] not in reserved]
        replace.update({"Contents/section0.xml": new_sec, "Contents/header.xml": editor.header,
                        "Preview/PrvText.txt": ("%s %s" % (title or "", S.subject)).strip()})
        G.doc.write(out_path, replace, add_bins=add, drop_bins=drop)

    def typeset_exam(self, exam, out_path, **kw):
        ents = self.entries(exam)
        self._n_items = sum(len(e[2]) for e in ents)
        res = None
        # 쪽 수는 배치 결과로 정해진다: 먼저 배치하고(파일은 한 번만 쓴다) 넘침이 있으면 쪽 수를 바꾸지 않는다
        self._pages = None
        res = super().typeset_exam(exam, out_path, **kw)
        return res

    def after_place(self, ncols, over):
        self._pages = None if over else (ncols + 1) // 2


PROFILE = LeetVerbal()
