# -*- coding: utf-8 -*-
"""PSAT 문제지 조판 엔진(언어논리·상황판단·자료해석 공통). 양식별 값은 PsatStyle.

원고 → 계획(TP·Box·DataTable·Fig) → 흐름 블록(core.flow) → 양식 hwpx.
- 문항은 한 단에서 시작한다(공식 기출 배치). 문항에 "이어붙이기": true 면 앞 문항 단에 다 들어갈 때 이어 놓는다.
- 공통지문 세트: {"세트": {"안내": …, "지문": […]}, "문항": [문항, …]} — 머리 [a～b] + 지문, 이어서 문항들.
- 상자 안 글은 어절 단위로 줄을 정해 강제 줄 나눔으로 넣는다(원고에 \\n 이 있으면 그대로).
"""
import copy
import math
import os
import re

from ...core.context import Ctx
from ...core.diagnostics import Diag
from ...core.flow import Block, Unit, place
from ...core.header import Header
from ...core.fit import fit_runs
from ...core.headeredit import HeaderEditor
from ...core.linebreak import line_deltas
from ...core.hwpx import esc, run_xml, top_paragraphs, drop_linesegs, strip_memos, fresh_ids, pic_xml, hu, \
    replace_text_across
from ...core.inline import runs, unknown_tex, FW
from ...core.linebreak import check_lines
from ...core.png import png_info
from ...core.source import set_body, unwrap
from ...core.tables import outer_table, top_cells, cell_info, table_info, replace_cell_content, set_cell_size, \
    set_cell_margin, set_table_size
from ...core.template import TemplateDoc, TemplateError
from .model import TP, Box, DataTable, Fig

TIGHT_LINES = 2.0
MARKS = "①②③④⑤"
BOGI_HEADS = "ㄱㄴㄷㄹㅁㅂㅅㅇ"

DIALOG = re.compile(r"^([甲乙丙丁戊己庚辛壬癸]|[갑을병정무기]|[A-Z]{1,2}\d{0,2})\s*[:：]\s*(.+)$", re.S)
BULLET = re.compile(r"^([○◦●ㆍ•□■△▲◇◆])\s*(.+)$", re.S)
LAW = re.compile(r"^(제[○□△◇0-9]+조(?:의\s?\d+)?(?:\([^)]*\))?)\s*(.*)$", re.S)
LAWITEM = re.compile(r"^([①-⑳])\s*(.+)$", re.S)
HO = re.compile(r"^(\d{1,2}\.)\s+(.+)$", re.S)
MOK = re.compile(r"^([가-하]\.)\s+(.+)$", re.S)
NOTE = re.compile(r"^(※(?:\s*\d+\))?)\s*(.+)$", re.S)
SUBTITLE = re.compile(r"^<([^<>]{1,40})>$")
FULLWIDTH_HEAD = re.compile(r"^〈[^〈〉]{1,20}〉$")
OBJ_KINDS = ("문단", "라벨", "나열", "조문", "항", "호", "목", "주석", "소제목")
NUMERIC = re.compile(r"^[-－+]?[\d,]+(?:\.\d+)?%?$")


def tilde(text):
    """키보드 물결(~)을 전각 물결(～)로(수식 $…$ 안은 그대로). PSAT 양식은 범위·[19～20] 에 ～ 를 쓴다."""
    return re.sub(r"(\$[^$]*\$)|~", lambda m: m.group(1) or "～", text or "")


def natural_lines_h(n, pitch, font):
    """한글이 스스로 잡는 칸(상자·표) 높이의 글 부분: (n−1)×줄간격 + 글자 크기 + min(줄간격 − 글자 크기, 0.5145×글자 크기).
    양식 실측: 11pt 170%/160% 한 줄 칸 1948 = 1100 + 566 + 여백 282, 120% 두 줄 제목 칸 2922 = 1320×2 + 282 (여분 220 < 566 이면 그대로)."""
    n = max(int(n), 1)
    return (n - 1) * pitch + font + min(max(pitch - font, 0.0), 0.5145 * font)


def spaced_title(t):
    """두 글자 제목은 글자 사이 빈칸 두 개(<보  기>), 나머지는 그대로."""
    t = t.strip().strip("<>〈〉").strip()
    return "  ".join(t) if len(t) == 2 and " " not in t else t


class Geometry:
    """양식에서 읽은 크기·문단 모양(읽기 전용, 프로필당 한 번)."""

    def __init__(self, style, path):
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
        tops = top_paragraphs(sec)
        self.tops = [sec[a:b] for a, b in tops]
        # 제목 상자 견본
        lb = next((p for p in self.tops[1:] if style.lbox_needle in p and 'rowCnt="3" colCnt="3"' in p), None)
        if lb is None:
            raise TemplateError("TEMPLATE_ITEM", "양식에서 제목 상자(<보  기>) 견본을 찾지 못했습니다")
        a, b = outer_table(lb)
        self.lbox = lb[a:b]
        ti = table_info(self.lbox)
        self.box_w = ti["width"]
        self.box_out = ti["out"]
        self.box_in = ti["in"]
        cc = top_cells(self.lbox)
        content = self.lbox[cc[(2, 0)][0]:cc[(2, 0)][1]]
        ci = cell_info(content)
        m = ci["margin"] if ci["has_margin"] else ti["in"]
        self.lbox_margin = m
        self.lbox_inner = ci["width"] - m[0] - m[1]
        t0 = cell_info(self.lbox[cc[(0, 0)][0]:cc[(0, 0)][1]])
        t1 = cell_info(self.lbox[cc[(1, 0)][0]:cc[(1, 0)][1]])
        self.lbox_title_h = t0["height"] + t1["height"]
        self.lbox_title_w = cell_info(self.lbox[cc[(0, 1)][0]:cc[(0, 1)][1]])["width"]
        self.box_inner = self.box_w - self.box_in[0] - self.box_in[1]
        pm = re.search(r"<hp:pic\b.*?</hp:pic>", sec, re.S)
        if pm is None:
            for name in doc.masters():
                pm = re.search(r"<hp:pic\b.*?</hp:pic>", doc.read(name), re.S)
                if pm:
                    break
        self.pic = pm.group(0) if pm else None


class PsatProfile:
    flow = True
    shows_total_pages = False           # 표지·바탕쪽에 전체 쪽 수가 있는 양식(언어이해)

    def after_place(self, ncols, over):
        """배치가 끝난 뒤(파일을 쓰기 전) 프로필이 쪽 수 등을 정할 자리."""

    def __init__(self, style, folder, solution_profile=None, width=None):
        self.style = style
        self.name = style.name
        self.template_path = None
        self.max_items = style.max_items
        self.width = width
        self.solution_profile = solution_profile
        self._geo = None

    # ── 양식
    def geo(self):
        if self._geo is None:
            self._geo = Geometry(self.style, self.template_path)
        return self._geo

    def new_ctx(self):
        return Ctx(eq_base=1100)

    def line_pt(self):
        S, G = self.style, self.geo()
        return G.H.pitch(S.stem.ps, S.stem.cs)

    # ── 문단 계획
    def _tp(self, role, body, container, kind, src=(), prefix="", head="", raw_head="", indent=None, wrap_lines=True,
            tab_head=False):
        G = self.geo()
        P = G.H.para[role.ps]
        font = G.H.char[role.cs].pt if role.cs in G.H.char else 11.0
        ind = P.indent if indent is None else indent
        base = container - P.left - P.right
        hang = -ind if ind < 0 else 0.0
        if raw_head or tab_head:
            first = rest = base - hang
        elif ind >= 0:
            first, rest = base - ind, base
        else:
            first, rest = base, base - hang
        tp = TP(kind, role.ps, role.st, role.cs, role.hcs, head, raw_head, body, first, rest, P.pitch(font),
                P.prev + P.next, P.condense / 100.0, src, prefix, wrap_lines)
        if indent is not None:
            tp.variant = (role.ps, indent)
        return tp

    def _label_indent(self, label):
        return -(self.width.word_w(label) + 2 * self.style.fw)

    def text_block(self, b, container, src, diag, boxed=True, lbox=False):
        """문자열/글 객체 블록 → TP."""
        S = self.style
        if isinstance(b, dict):
            kind = next((k for k in OBJ_KINDS if k in b), None)
            if kind is None:
                diag.error("UNKNOWN_BLOCK", "알 수 없는 블록입니다: %s" % ", ".join(b), where=src)
                kind = "문단"
                b = {"문단": ""}
            body = str(b.get("글", b.get(kind, "")) if kind in ("라벨", "조문", "항", "호", "목") else b.get(kind, ""))
            label = str(b.get(kind, "")) if kind in ("라벨", "조문", "항", "호", "목") else ""
            prefix = ""
        else:
            s = b.strip()
            if FULLWIDTH_HEAD.match(s):
                diag.error("NONCANONICAL_BRACKET", "전각 꺾쇠 '%s'는 쓰지 않습니다. 반각 < >로 쓰십시오" % s, where=src)
            kind, label, body, prefix = "문단", "", s, ""
            for k, rx in (("라벨", DIALOG), ("나열", BULLET), ("조문", LAW), ("항", LAWITEM), ("호", HO),
                          ("목", MOK), ("주석", NOTE)):
                m = rx.match(s)
                if m:
                    kind, label, body = k, m.group(1), m.group(2)
                    prefix = s[:len(s) - len(body)]
                    break
            else:
                m = SUBTITLE.match(s)
                if m:
                    kind, body, prefix = "소제목", s, ""
        if kind == "라벨":
            head = label + ":" + FW + FW
            return self._tp(S.dialog, body, container, "발언", src, prefix, head=head,
                            indent=self._label_indent(label + ":"))
        if kind == "나열":
            mark = label if label else "○"
            return self._tp(S.bullet, body, container, "나열", src, prefix, head=mark + FW + FW)
        if kind == "조문":
            m = LAWITEM.match(body)
            if m:
                body2 = m.group(2)
                head = label + " " + m.group(1) + FW + FW
                pre = (body[:len(body) - len(body2)] if isinstance(b, dict)
                       else b.strip()[:len(b.strip()) - len(body2)])
                return self._tp(S.law, body2, container, "조문", src, pre, head=head)
            return self._tp(S.law, body, container, "조문", src, prefix, head=(label + " ") if label else "")
        if kind == "항":
            return self._tp(S.lawitem, body, container, "항", src, prefix, head=label + FW + FW)
        if kind == "호":
            lab = label if label.endswith(".") else label + "."
            return self._tp(S.ho, body, container, "호", src, prefix, head=" " + lab + FW + FW)
        if kind == "목":
            lab = label if label.endswith(".") else label + "."
            return self._tp(S.mok, body, container, "목", src, prefix, head=lab + FW + FW)
        if kind == "주석":
            lab = label if label else "※"
            return self._tp(S.note, body, container, "주석", src, prefix, head=lab + FW + FW)
        if kind == "소제목":
            return self._tp(S.subtitle, body, container, "소제목", src, prefix, wrap_lines=False)
        role = S.lbox_text if lbox else S.box_text
        return self._tp(role, body, container, "문단", src, prefix, head=S.box_text_head if boxed else "")

    # ── 그림·표
    def load_figure(self, spec, src, diag, base_dir, avail):
        path = spec.get("그림") if isinstance(spec, dict) else spec
        p = path if os.path.isabs(path) else os.path.join(base_dir or ".", path)
        try:
            w, h, dx, dy = png_info(p)
        except (OSError, ValueError) as e:
            diag.error("FIGURE_MISSING", "그림을 읽을 수 없습니다: %s (%s)" % (path, e), where=src, path=path)
            return None
        nat_w, nat_h = w * 72.0 / dx, h * 72.0 / dy
        want = float(spec.get("폭")) if isinstance(spec, dict) and spec.get("폭") else min(nat_w, avail)
        if want > avail + 0.5:
            diag.warning("FIGURE_WIDE", "그림 폭 %.0fpt가 칸 폭 %.0fpt보다 넓어 줄였습니다" % (want, avail), where=src)
            want = avail
        if want < nat_w * 0.6:
            diag.warning("FIGURE_SMALL", "그림을 원본의 %.0f%%로 줄였습니다(흐려질 수 있음)" % (100 * want / nat_w), where=src)
        f = Fig(path, os.path.abspath(p), want, want * nat_h / nat_w, (w, h), src)
        title = spec.get("제목") if isinstance(spec, dict) else None
        if title:
            f.title_tp = self._tp(self.style.figure_title, str(title), avail, "그림 제목", src + ("제목",),
                                  wrap_lines=False)
        return f

    def plan_table(self, block, container, src, diag):
        S = self.style
        T = S.table
        rows = block.get("표")
        if not isinstance(rows, list) or not rows or not all(isinstance(r, list) for r in rows):
            diag.error("UNKNOWN_BLOCK", "표는 행 목록이어야 합니다", where=src)
            return None
        unit = str(block.get("단위", "") or "").strip()
        if unit and not unit.startswith(("(", "（")):                 # 원고가 "일"처럼 단위만 적어도 양식대로 "(단위: 일)"
            unit = "(단위: %s)" % unit
        t = DataTable(rows, str(block.get("제목", "") or ""), unit, src=src)
        note = block.get("주석") or []
        t.note = [note] if isinstance(note, str) else list(note)
        hr = block.get("머리행", 1)
        t.header_rows = int(hr) if not isinstance(hr, bool) else (1 if hr else 0)
        # 칸 펼치기(합친 칸)
        taken, cells, ncols = set(), [], 0
        for r, row in enumerate(rows):
            c = 0
            for v in row:
                while (r, c) in taken:
                    c += 1
                if isinstance(v, dict):
                    text, cs, rs = str(v.get("글", "")), int(v.get("가로", 1)), int(v.get("세로", 1))
                else:
                    text, cs, rs = ("" if v is None else str(v)), 1, 1
                for dr in range(rs):
                    for dc in range(cs):
                        taken.add((r + dr, c + dc))
                cells.append([r, c, cs, rs, text])
                c += cs
                ncols = max(ncols, c)
        t.ncols, t.nrows = ncols, len(rows)
        for c in cells:
            if c[0] + c[3] > t.nrows:
                diag.warning("TABLE_SHAPE", "합친 칸(세로 %d)이 표 아래로 넘쳐 줄였습니다" % c[3], where=src)
                c[3] = t.nrows - c[0]
        covered = {r: sum(c[2] for c in cells if c[0] <= r < c[0] + c[3]) for r in range(t.nrows)}
        if len(set(covered.values())) > 1:
            diag.warning("TABLE_SHAPE", "행마다 칸 수가 다릅니다(%s) — 빈 칸으로 채웠습니다"
                         % ", ".join(str(covered[r]) for r in range(t.nrows)), where=src)
        taken = {(c[0] + dr, c[1] + dc) for c in cells for dr in range(c[3]) for dc in range(c[2])}
        for r in range(t.nrows):
            for c in range(ncols):
                if (r, c) not in taken:
                    cells.append([r, c, 1, 1, ""])
        cells.sort(key=lambda x: (x[0], x[1]))
        t.cells = cells
        width = container
        t.width = width
        ml, mr, mt, mb = T.cell_margin
        wm = self.width
        given = block.get("열폭")
        if given and len(given) == ncols:
            tot = float(sum(given))
            t.col_widths = [width * g / tot for g in given]
        else:
            need = [24.0] * ncols
            for r, c, cs, rs, text in cells:
                if cs == 1:
                    longest = max((wm.text_w(x) for x in text.split("\n")), default=0)
                    need[c] = max(need[c], min(longest, 140.0) + ml + mr + 6)
            tot = sum(need)
            t.col_widths = [width * x / tot for x in need]
        # 정렬: 숫자 열은 자릿수가 같으면 가운데, 다르면 오른쪽(양식 메모)
        given_al = block.get("정렬")
        if given_al and len(given_al) == ncols:
            t.align = [str(a)[:1].upper() for a in given_al]
        else:
            t.align = []
            for c in range(ncols):
                vals = [x[4] for x in cells if x[1] == c and x[0] >= t.header_rows and x[2] == 1 and x[4]]
                if vals and all(NUMERIC.match(v.replace(" ", "")) for v in vals):
                    lens = {len(v.replace(",", "").split(".")[0].lstrip("-－+")) for v in vals}
                    t.align.append("C" if len(lens) == 1 else "R")
                else:
                    t.align.append("C")
        # 행 높이 — 한글이 스스로 잡는 칸 높이는 줄 간격 합 − 2.06pt + 여백(양식 실측: 상자·표 칸 모두). 한 줄 칸은 공식 양식·자체 양식
        # 모두 19.48pt(170% 한 줄의 자연 높이)로 맞춰져 있어 그 값을 하한으로 둔다(extra.table_row_pt).
        G = self.geo()
        pitch = G.H.pitch(T.cell.ps, T.cell.cs)
        font = G.H.char[T.cell.cs].pt if T.cell.cs in G.H.char else 11.0
        row_min = float(S.extra.get("table_row_pt", 19.48))

        def nat(n):                       # 한글 자연 칸 높이: 마지막 줄 아래는 줄 간격 여분과 글자 크기 × 0.5145 중 작은 쪽
            return natural_lines_h(n, pitch, font) + mt + mb
        heights = [0.0] * t.nrows
        for r, c, cs, rs, text in cells:
            w = sum(t.col_widths[c:c + cs]) - ml - mr - 2
            n = sum(max(1, math.ceil(wm.text_w(x) / max(w, 10))) for x in (text.split("\n") if text else [""]))
            h = nat(n)
            if rs == 1:
                heights[r] = max(heights[r], h)
        for r, c, cs, rs, text in cells:
            if rs > 1:
                w = sum(t.col_widths[c:c + cs]) - ml - mr - 2
                n = sum(max(1, math.ceil(wm.text_w(x) / max(w, 10))) for x in (text.split("\n") if text else [""]))
                need = nat(n)
                have_h = sum(heights[r:r + rs])
                if need > have_h:
                    heights[r + rs - 1] += need - have_h
        t.row_heights = [max(h, row_min) for h in heights]
        t.height = sum(t.row_heights)
        if t.title:
            t.title_tp = self._tp(T.title, t.title, container, "표 제목", src + ("제목",), wrap_lines=False)
        if t.unit:
            t.unit_tp = self._tp(T.unit, t.unit, container, "표 단위", src + ("단위",), wrap_lines=False)
        for k, n in enumerate(t.note):
            n = str(n)
            if self.style.extra.get("note_nominal") and re.search(r"(다|요)\.?\s*$", n.strip()):
                diag.warning("NOTE_STYLE", "주석은 음슴체(명사형 종결)로 씁니다: '%s'" % n.strip()[-12:],
                             where=src + ("주석", k))
            s0 = n.strip()
            m = NOTE.match(s0)
            lab, body = (m.group(1), m.group(2)) if m else ("※", s0)
            prefix = s0[:len(s0) - len(body)]
            t.note_tps.append(self._tp(T.note, body, container, "주석", src + ("주석", k), prefix, head=lab + " "))
        return t

    # ── 문항 계획
    def body_blocks(self, blocks, diag, base_dir, path=("지문",)):
        """지문 블록 목록 → [Box | DataTable | Fig]. 글 블록이 이어지면 제목 없는 상자 하나로 묶는다."""
        G = self.geo()
        out, cur = [], None
        for k, b in enumerate(blocks):
            src = path + (k,)
            if isinstance(b, dict) and "상자" in b:
                cur = None
                title = b.get("상자") or ""
                content = b.get("내용") or []
                if isinstance(content, str):
                    content = [content]
                box = Box(spaced_title(title) if title else "", [], src)
                inner = G.lbox_inner if title else G.box_inner
                box.inner_w = inner
                for j, x in enumerate(content):
                    self._box_item(box, x, inner, src + ("내용", j), diag, base_dir, lbox=bool(title))
                out.append(box)
                continue
            if isinstance(b, dict) and ("표" in b or "그림" in b):
                if cur is not None:
                    self._box_item(cur, b, cur.inner_w, src, diag, base_dir)
                    continue
                if "표" in b:
                    t = self.plan_table(b, G.box_w, src, diag)
                    if t:
                        out.append(t)
                else:
                    f = self.load_figure(b, src, diag, base_dir, G.col_w - 20)
                    if f:
                        out.append(f)
                continue
            if isinstance(b, dict) and not any(k2 in b for k2 in OBJ_KINDS):
                diag.error("UNKNOWN_BLOCK", "알 수 없는 블록입니다: %s" % ", ".join(b), where=src)
                continue
            if cur is None:
                cur = Box("", [], src)
                cur.inner_w = G.box_inner
                out.append(cur)
            self._box_item(cur, b, cur.inner_w, src, diag, base_dir)
        return out

    def _box_item(self, box, x, inner, src, diag, base_dir, lbox=False):
        if isinstance(x, dict) and "표" in x:
            t = self.plan_table(x, inner - 20, src, diag)
            if t:
                box.content.append(t)
        elif isinstance(x, dict) and "그림" in x:
            f = self.load_figure(x, src, diag, base_dir, inner - 20)
            if f:
                box.content.append(f)
        elif isinstance(x, (str, dict)):
            box.content.append(self.text_block(x, inner, src, diag, lbox=lbox))
        else:
            diag.error("UNKNOWN_BLOCK", "알 수 없는 블록입니다", where=src)

    def bogi_box(self, items, diag=None, base_dir=None):
        G, S = self.geo(), self.style
        box = Box("보  기", [], ("보기",))
        box.inner_w = G.lbox_inner
        for k, v in enumerate(items):
            text = v if isinstance(v, str) else str(v.get("글", ""))
            m = re.match(r"^\s*([ㄱ-ㅇ])\s*\.\s*", text)
            prefix = m.group(0) if m else ""
            body = text[len(m.group(0)):] if m else text
            head = BOGI_HEADS[min(k, len(BOGI_HEADS) - 1)] + "." + FW + FW
            box.content.append(self._tp(S.bogi, body, G.lbox_inner, "보기", ("보기", k), prefix, head=head))
            if isinstance(v, dict) and v.get("그림"):
                f = self.load_figure(v, ("보기", k), diag or Diag(), base_dir, G.lbox_inner - 20)
                if f:
                    box.content.append(f)
        return box

    def choice_plan(self, n, choices, diag, base_dir, item):
        S, G = self.style, self.geo()
        if len(choices) != 5:
            diag.error("CHOICE_COUNT", "선지가 %d개입니다(5개여야 함)" % len(choices), where=("선지",),
                       count=len(choices))
        out = []
        texts = [c if isinstance(c, str) else c.get("글", "") for c in choices]
        objs = [isinstance(c, dict) and ("그림" in c or "표" in c) for c in choices]
        if (S.pack_short_choices and S.choice2 is not None and not any(objs) and len(choices) == 5
                and all("\n" not in t for t in texts)):
            half = (G.col_w - 36.6) / 2 - 16
            if all(self.width.text_w(re.sub(r"^\s*[①-⑤]\s*", "", t)) <= half for t in texts):
                clean = [re.sub(r"^\s*[①-⑤]\s*", "", t) for t in texts]
                for a in range(0, 5, 2):
                    pair = [(MARKS[a], clean[a])] + ([(MARKS[a + 1], clean[a + 1])] if a + 1 < 5 else [])
                    out.append(("pair", pair))
                return out, "2열"
        for k, c in enumerate(choices):
            text = texts[k]
            m = re.match(r"^\s*[①-⑤]\s*", text) if isinstance(c, str) else None
            prefix = m.group(0) if m else ""
            body = text[len(prefix):]
            tp = self._tp(S.choice, body, G.col_w, "선지", ("선지", k), prefix,
                          raw_head=S.choice_head.replace("{m}", MARKS[k] if k < 5 else "⑥"))
            out.append(("tp", tp))
            if objs[k]:
                if "표" in c:
                    t = self.plan_table(c, G.box_w - 20, ("선지", k), diag)
                    if t:
                        out.append(("obj", t))
                else:
                    f = self.load_figure(c, ("선지", k), diag, base_dir, G.col_w - 40)
                    if f:
                        out.append(("obj", f))
        return out, "한 줄에 하나"

    def stem_tp(self, n, text):
        S, G = self.style, self.geo()
        head = (S.stem_head1 if n < 10 else S.stem_head2).replace("{n}", str(n))
        return self._tp(S.stem, text, G.col_w, "발문", ("발문",), raw_head=head)

    def plan_item(self, n, item, diag, ctx, base_dir=None):
        plan = {"number": n, "stem": self.stem_tp(n, item.get("발문", "")),
                "body": self.body_blocks(item.get("지문") or [], diag, base_dir),
                "bogi": self.bogi_box(item["보기"], diag, base_dir) if item.get("보기") else None}
        plan["choices"], plan["layout"] = self.choice_plan(n, item.get("선지") or [], diag, base_dir, item)
        for name in sorted(set(unknown_tex(str(item.get("발문", ""))) + self._tex_all(item))):
            diag.error("UNKNOWN_TEX", "모르는 LaTeX 명령 \\%s" % name.lstrip("\\"), command=name)
        return plan

    def _tex_all(self, item):
        out = []

        def walk(x):
            if isinstance(x, str):
                out.extend(unknown_tex(x))
            elif isinstance(x, list):
                for y in x:
                    walk(y)
            elif isinstance(x, dict):
                for k, v in x.items():
                    if k not in ("그림", "해설"):
                        walk(v)
        walk({k: v for k, v in item.items() if k != "발문"})
        return out

    def plan_set(self, first, last, s, diag, base_dir):
        S, G = self.style, self.geo()
        guide = s.get("안내") or "다음 글을 읽고 물음에 답하시오."
        head = "[%d%s～%s%d]%s%s" % (first, FW, FW, last, FW, FW)
        tp = self._tp(S.sethead, guide, G.col_w, "세트 머리", ("세트", "안내"), head=head)
        body = self.body_blocks(s.get("지문") or [], diag, base_dir, path=("세트", "지문"))
        self._tex_check(s, diag)
        return {"head": tp, "body": body}

    def _tex_check(self, s, diag):
        bad = []

        def walk(x):
            if isinstance(x, str):
                bad.extend(unknown_tex(x))
            elif isinstance(x, list):
                for y in x:
                    walk(y)
            elif isinstance(x, dict):
                for k, v in x.items():
                    if k not in ("그림", "해설"):
                        walk(v)
        walk(s)
        for name in sorted(set(bad)):
            diag.error("UNKNOWN_TEX", "세트: 모르는 LaTeX 명령 \\%s" % name.lstrip("\\"), command=name)

    # ── 문단 목록(줄 나눔·측정용)
    def all_tps(self, plan):
        out = []

        def walk(x):
            if isinstance(x, TP):
                out.append(x)
            elif isinstance(x, Box):
                for y in x.content:
                    walk(y)
            elif isinstance(x, DataTable):
                for y in [x.title_tp, x.unit_tp] + x.note_tps:
                    if y is not None:
                        out.append(y)
            elif isinstance(x, Fig):
                if x.title_tp is not None:
                    out.append(x.title_tp)
        if "stem" in plan:
            walk(plan["stem"])
        if "head" in plan:
            walk(plan["head"])
        for x in plan.get("body", []):
            walk(x)
        if plan.get("bogi"):
            walk(plan["bogi"])
        for kind, x in plan.get("choices", []):
            if kind == "tp":
                walk(x)
            elif kind == "obj":
                walk(x)
        return out

    def all_objects(self, plan):
        out = []

        def walk(x):
            if isinstance(x, (DataTable, Fig)):
                out.append(x)
            if isinstance(x, Box):
                for y in x.content:
                    walk(y)
        for x in plan.get("body", []) + ([plan["bogi"]] if plan.get("bogi") else []):
            walk(x)
        for kind, x in plan.get("choices", []):
            if kind == "obj":
                walk(x)
        return out

    # ── 높이
    def measure_plan_tps(self, plan):
        for tp in self.all_tps(plan):
            tp.measure(self.width)

    def box_height(self, box):
        G = self.geo()
        inner = 0.0
        for x in box.content:
            if isinstance(x, TP):
                inner += x.height
            elif isinstance(x, DataTable):
                inner += self.table_block_height(x, inside=True)
            elif isinstance(x, Fig):
                inner += x.height_pt + 6.0 + (x.title_tp.height if x.title_tp else 0)
        # 첫 줄 위·마지막 줄 아래 여백은 칸 여백으로 만든다(box_gap_pt). 공식 양식은 칸이 가운데 맞춤이고 한글이 잡은 칸 높이가
        # 글 바닥보다 5.66pt 커서 그 절반(2.83pt)이 위아래로 가는데, 그 방식은 한글이 줄을 다시 나누면(칸이 늘어나면) 사라진다.
        # 칸 여백으로 두면 줄이 늘어도 간격이 남는다. box_fit_pt 는 마지막 줄의 줄 간격 여분(줄 간격 − 글자 크기)을 덜어
        # 칸 높이를 글 바닥 + 여백으로 맞추는 값(11pt·170% = −7.72).
        inner += float(self.style.extra.get("box_fit_pt", 0.0))
        gap = float(self.style.extra.get("box_gap_pt", 0.0))
        if box.title:
            m = G.lbox_margin
            box.height = G.lbox_title_h + inner + m[2] + m[3] + 2 * gap
        else:
            box.height = inner + G.box_in[2] + G.box_in[3] + 2 * gap
        return box.height

    def holder_h(self, obj_h):
        G = self.geo()
        return obj_h + G.box_out[2] + G.box_out[3] + self.style.holder_extra

    def frame_heights(self, t):
        """자체 양식 표: 제목·단위 행과 주석 행의 높이(없으면 0). 칸 높이 = 문단 높이 합 + 위아래 여백."""
        T = self.style.table
        top = bottom = 0.0
        G = self.geo()

        def nat(tps):                    # 문단들의 자연 높이 합(마지막 문단의 마지막 줄만 여분을 줄인다)
            tot = 0.0
            for i, x in enumerate(tps):
                font = G.H.char[x.cs].pt if x.cs in G.H.char else 11.0
                tot += (natural_lines_h(x.lines, x.pitch, font) if i == len(tps) - 1 else x.lines * x.pitch) + x.gap
            return tot
        if T.frame_top and (t.title_tp or t.unit_tp):
            top = nat([x for x in (t.title_tp, t.unit_tp) if x]) + T.frame_top_margin[2] + T.frame_top_margin[3]
        if T.frame_bottom and t.note_tps:
            bottom = nat(t.note_tps) + T.frame_bottom_margin[2] + T.frame_bottom_margin[3]
        return top, bottom

    def table_block_height(self, t, inside=False):
        top, bottom = self.frame_heights(t)
        h = t.height + top + bottom
        if not (self.style.table.frame_top and (t.title_tp or t.unit_tp)):
            h += (t.title_tp.height if t.title_tp else 0) + (t.unit_tp.height if t.unit_tp else 0)
        if not (self.style.table.frame_bottom and t.note_tps):
            h += sum(x.height for x in t.note_tps)
        return h + (6.0 if inside else self.style.holder_extra + 2.8)

    # ── XML
    def tp_xml(self, tp, ctx, editor, auto_break="fit"):
        ps = tp.ps
        if getattr(tp, "variant", None) and editor is not None:
            ps = editor.para_variant(tp.variant[0], indent=tp.variant[1])
        mode = auto_break if isinstance(auto_break, str) else ("force" if auto_break else "none")
        authored = "\n" in tp.body
        body = tp.broken(self.width) if mode != "none" else tp.body
        if self.style.extra.get("tilde"):
            body = tilde(body)
        parts = []
        if tp.raw_head:
            parts.append('<hp:run charPrIDRef="%d"><hp:t>%s</hp:t></hp:run>' % (tp.hcs, tp.raw_head))
        head_rs = runs(tp.head, tp.hcs if tp.raw_head else tp.cs, ctx) if tp.head else []
        rs = runs(body, tp.cs, ctx)
        if "\n" in body and mode != "none":          # 정한 줄마다 자간(넘치는 줄만 음수); 예측 줄은 강제 줄 나눔 없이
            lines = (tp.head + body).split("\n")
            deltas = line_deltas(lines, tp.first_w, tp.rest_w, self.width.with_shrink(tp.shrink)) if ctx.header_editor is not None else [0] * len(lines)
            # 첫 줄 자간은 머리(라벨)까지 포함해 계산했으므로 머리 런에도 입힌다 — 몸통에만 입히면 눌러 넣는 폭이 모자라 한글이 먼저 접는다
            rs = fit_runs(head_rs + rs, deltas, ctx, keep_breaks=(mode == "force" or authored))
        else:
            rs = head_rs + rs
        parts.extend(run_xml(cs, pcs, ctx) for cs, pcs in rs)
        if not parts:
            parts.append('<hp:run charPrIDRef="%d"/>' % tp.cs)
        return ('<hp:p id="2147483648" paraPrIDRef="%d" styleIDRef="%d" pageBreak="0" columnBreak="0" merged="0">'
                '%s</hp:p>' % (ps, tp.st, "".join(parts)))

    def empty_xml(self, role):
        return ('<hp:p id="2147483648" paraPrIDRef="%d" styleIDRef="%d" pageBreak="0" columnBreak="0" merged="0">'
                '<hp:run charPrIDRef="%d"/></hp:p>' % (role.ps, role.st, role.cs))

    def holder_xml(self, obj_xml, role=None, head=None):
        S = self.style
        role = role or S.holder
        head = S.holder_head if head is None else head
        lead = "<hp:t>%s</hp:t>" % head if head else ""
        return ('<hp:p id="2147483648" paraPrIDRef="%d" styleIDRef="%d" pageBreak="0" columnBreak="0" merged="0">'
                '<hp:run charPrIDRef="%d">%s%s<hp:t/></hp:run></hp:p>'
                % (role.ps, role.st, role.cs, lead, obj_xml))

    def tbl_open(self, ctx, rows, cols, w, h, bf, out=(1.41, 1.41, 1.41, 1.41), inm=(1.41, 1.41, 1.41, 1.41)):
        return ('<hp:tbl id="%d" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES"'
                ' lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="%d" colCnt="%d"'
                ' cellSpacing="0" borderFillIDRef="%d" noAdjust="0">'
                '<hp:sz width="%d" widthRelTo="ABSOLUTE" height="%d" heightRelTo="ABSOLUTE" protect="0"/>'
                '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0"'
                ' vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
                '<hp:outMargin left="%d" right="%d" top="%d" bottom="%d"/>'
                '<hp:inMargin left="%d" right="%d" top="%d" bottom="%d"/>'
                % (ctx.nid(), rows, cols, bf, hu(w), hu(h), *[hu(x) for x in out], *[hu(x) for x in inm]))

    def tc(self, inner, col, row, w, h, bf, margin=None, colspan=1, rowspan=1, valign="CENTER"):
        m = margin or (1.41, 1.41, 1.41, 1.41)
        return ('<hp:tc name="" header="0" hasMargin="%d" protect="0" editable="0" dirty="0" borderFillIDRef="%d">'
                '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="%s" linkListIDRef="0"'
                ' linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">%s</hp:subList>'
                '<hp:cellAddr colAddr="%d" rowAddr="%d"/><hp:cellSpan colSpan="%d" rowSpan="%d"/>'
                '<hp:cellSz width="%d" height="%d"/><hp:cellMargin left="%d" right="%d" top="%d" bottom="%d"/></hp:tc>'
                % (int(margin is not None), bf, valign, inner, col, row, colspan, rowspan, hu(w), hu(h),
                   *[hu(x) for x in m]))

    def content_xml(self, content, ctx, editor, auto_break):
        out = []
        for x in content:
            if isinstance(x, TP):
                out.append(self.tp_xml(x, ctx, editor, auto_break))
            elif isinstance(x, DataTable):
                out.append(self.table_paras_xml(x, ctx, editor, auto_break, inside=True))
            elif isinstance(x, Fig):
                if x.title_tp:
                    out.append(self.tp_xml(x.title_tp, ctx, editor, False))
                out.append(self.figure_para_xml(x, ctx))
        return "".join(out)

    def box_xml(self, box, ctx, editor, auto_break):
        G, S = self.geo(), self.style
        inner = self.content_xml(box.content, ctx, editor, auto_break) or self.empty_xml(S.box_text)
        if not box.title:
            bf = S.extra.get("box_border", 3)
            gap = float(S.extra.get("box_gap_pt", 0.0))
            m = (G.box_in[0], G.box_in[1], G.box_in[2] + gap, G.box_in[3] + gap) if gap else None
            tc = self.tc(inner, 0, 0, G.box_w, box.height, bf, m, valign=S.extra.get("box_valign", "TOP"))
            return self.tbl_open(ctx, 1, 1, G.box_w, box.height, bf, G.box_out, G.box_in) + \
                "<hp:tr>%s</hp:tr></hp:tbl>" % tc
        t = fresh_ids(G.lbox, ctx)
        cc = top_cells(t)
        # 제목 칸: 글만 바꾸고 폭을 제목에 맞춘다
        a, b = cc[(0, 1)]
        tc_title = t[a:b]
        p_open = re.search(r"<hp:p [^>]*>", tc_title).group(0)
        cs = re.search(r'<hp:run charPrIDRef="(\d+)"', tc_title).group(1)
        title_xml = p_open + '<hp:run charPrIDRef="%s"><hp:t>%s</hp:t></hp:run></hp:p>' % (cs, esc("<%s>" % box.title))
        t = replace_cell_content(t, (0, 1), title_xml)
        tw = max(G.lbox_title_w, self.width.text_w("<%s>" % box.title) + 12.0)
        side = (G.box_w - tw) / 2.0
        t = set_cell_size(t, (0, 1), width=tw)
        for rc in ((0, 0), (0, 2), (1, 0), (1, 2)):
            t = set_cell_size(t, rc, width=side)
        content_h = box.height - G.lbox_title_h
        t = replace_cell_content(t, (2, 0), inner)
        t = set_cell_size(t, (2, 0), height=content_h)
        gap = float(S.extra.get("box_gap_pt", 0.0))
        if gap:
            m = G.lbox_margin
            t = set_cell_margin(t, (2, 0), top=m[2] + gap, bottom=m[3] + gap)
        t = set_table_size(t, height=box.height)
        return t

    def table_xml(self, tb, ctx, editor):
        S = self.style
        T = S.table
        G = self.geo()
        rows_xml = {}
        empty = self.style.extra.get("empty_cell", "")
        for r, c, cs, rs, text in tb.cells:
            if self.style.extra.get("tilde"):
                text = tilde(text)
            if not text.strip() and empty:
                text = empty
            al = tb.align[c] if r >= tb.header_rows else "C"
            role = T.cell if al == "C" else (T.cell_right if al == "R" else T.cell_left)
            paras = "".join(
                '<hp:p id="2147483648" paraPrIDRef="%d" styleIDRef="%d" pageBreak="0" columnBreak="0" merged="0">%s'
                '</hp:p>' % (role.ps, role.st, "".join(run_xml(x, p, ctx) for x, p in runs(line, role.cs, ctx))
                             or '<hp:run charPrIDRef="%d"/>' % role.cs)
                for line in (text.split("\n") if text else [""]))
            w = sum(tb.col_widths[c:c + cs])
            h = sum(tb.row_heights[r:r + rs])
            bf = T.head_border if r < tb.header_rows else T.border
            r_off = r + (1 if (T.frame_top and (tb.title_tp or tb.unit_tp)) else 0)
            rows_xml.setdefault(r, []).append(self.tc(paras, c, r_off, w, h, bf, T.cell_margin, cs, rs))
        # 자체 양식(자료해석): 제목·단위는 첫 행, 주석은 끝 행 — 열 전체를 합친 테두리 없는 칸. 제목이 표 폭 기준으로 가운데에 오고
        # 제목·격자·주석 사이 간격이 칸 여백으로 고정된다(따로 둔 문단은 단 폭 기준 가운데라 표보다 왼쪽으로 치우쳤다)
        top_h, bottom_h = self.frame_heights(tb)
        off = 1 if top_h else 0
        trs = []
        if top_h:
            paras = "".join(self.tp_xml(x, ctx, editor, False) for x in (tb.title_tp, tb.unit_tp) if x)
            trs.append("<hp:tr>%s</hp:tr>" % self.tc(paras, 0, 0, tb.width, top_h, T.frame_top, T.frame_top_margin, tb.ncols, 1))
        trs += ["<hp:tr>%s</hp:tr>" % "".join(rows_xml.get(r, [])) for r in range(tb.nrows)]
        if bottom_h:
            paras = "".join(self.tp_xml(x, ctx, editor, "fit") for x in tb.note_tps)
            trs.append("<hp:tr>%s</hp:tr>" % self.tc(paras, 0, tb.nrows + off, tb.width, bottom_h, T.frame_bottom, T.frame_bottom_margin, tb.ncols, 1))
        nrows = tb.nrows + off + (1 if bottom_h else 0)
        return self.tbl_open(ctx, nrows, tb.ncols, tb.width, tb.height + top_h + bottom_h, T.border, G.box_out, (0, 0, 0, 0)) + \
            "".join(trs) + "</hp:tbl>"

    def table_paras_xml(self, tb, ctx, editor, auto_break, inside=False):
        T = self.style.table
        framed_top = bool(T.frame_top and (tb.title_tp or tb.unit_tp))
        framed_bottom = bool(T.frame_bottom and tb.note_tps)
        out = []
        if tb.title_tp and not framed_top:
            out.append(self.tp_xml(tb.title_tp, ctx, editor, False))
        if tb.unit_tp and not framed_top:
            out.append(self.tp_xml(tb.unit_tp, ctx, editor, False))
        if inside:
            out.append(self.holder_xml(self.table_xml(tb, ctx, editor), role=self.style.figure, head=""))
        else:
            out.append(self.holder_xml(self.table_xml(tb, ctx, editor)))
        if not framed_bottom:
            for n in tb.note_tps:
                out.append(self.tp_xml(n, ctx, editor, auto_break))
        return "".join(out)

    def figure_para_xml(self, f, ctx):
        G, S = self.geo(), self.style
        return self.holder_xml(pic_xml(G.pic, f, ctx), role=S.figure, head="")

    # ── 흐름 블록
    def tp_block(self, tp, ctx, editor, auto_break):
        return Block(self.tp_xml(tp, ctx, editor, auto_break), tp.height, tp.kind, tp.src, tp.lines, tp.pitch,
                     split=True)

    def obj_blocks(self, x, ctx, editor, auto_break):
        if isinstance(x, Box):
            self.box_height(x)
            return [Block(self.holder_xml(self.box_xml(x, ctx, editor, auto_break)), self.holder_h(x.height),
                          "상자" if not x.title else x.title.replace(" ", ""), x.src)]
        if isinstance(x, DataTable):
            T = self.style.table
            top_h, bottom_h = self.frame_heights(x)
            out = []
            if not top_h:
                for tp in (x.title_tp, x.unit_tp):
                    if tp:
                        out.append(self.tp_block(tp, ctx, editor, False))
            out.append(Block(self.holder_xml(self.table_xml(x, ctx, editor)), self.holder_h(x.height + top_h + bottom_h), "표", x.src))
            if not bottom_h:
                out += [self.tp_block(n, ctx, editor, auto_break) for n in x.note_tps]
            return out
        if isinstance(x, Fig):
            out = []
            if x.title_tp:
                out.append(self.tp_block(x.title_tp, ctx, editor, False))
            out.append(Block(self.figure_para_xml(x, ctx), x.height_pt + self.style.holder_extra + 2.8, "그림", x.src))
            return out
        return []

    def item_blocks(self, plan, ctx, editor, auto_break):
        S = self.style
        self.measure_plan_tps(plan)
        bl = [self.tp_block(plan["stem"], ctx, editor, auto_break)]
        for x in plan["body"]:
            bl += self.obj_blocks(x, ctx, editor, auto_break)
        if plan["bogi"]:
            bl += self.obj_blocks(plan["bogi"], ctx, editor, auto_break)
        for kind, x in plan["choices"]:
            if kind == "tp":
                bl.append(self.tp_block(x, ctx, editor, auto_break))
            elif kind == "obj":
                bl += self.obj_blocks(x, ctx, editor, auto_break)
            elif kind == "pair":
                # 머리 XML 을 {t1}·{t2} 자리에서 잘라 탭·번호는 그대로, 선지 글은 표기(밑줄·수식·물결)를 거쳐 넣는다
                h = S.choice2_head
                a1, rest = h.split("{t1}")
                a2, _ = rest.split("{t2}")
                cs = S.choice2.cs
                raw = lambda t: '<hp:run charPrIDRef="%d"><hp:t>%s</hp:t></hp:run>' % (cs, t)
                body = lambda t: "".join(run_xml(c, pcs, ctx) for c, pcs in runs(
                    tilde(t) if S.extra.get("tilde") else t, cs, ctx))
                parts = [raw(a1.replace("{m1}", x[0][0])), body(x[0][1])]
                if len(x) > 1:
                    parts += [raw(a2.replace("{m2}", x[1][0])), body(x[1][1])]
                xml = ('<hp:p id="2147483648" paraPrIDRef="%d" styleIDRef="%d" pageBreak="0" columnBreak="0" merged="0">'
                       '%s</hp:p>' % (S.choice2.ps, S.choice2.st, "".join(parts)))
                pitch = self.geo().H.pitch(S.choice2.ps, S.choice2.cs)
                bl.append(Block(xml, pitch, "선지", ("선지",), 1, pitch, split=True))
        return bl

    def set_blocks(self, sp, ctx, editor, auto_break):
        sp["head"].measure(self.width)
        bl = [self.tp_block(sp["head"], ctx, editor, auto_break)]
        for x in sp["body"]:
            for tp in self._tps_of(x):
                tp.measure(self.width)
            bl += self.obj_blocks(x, ctx, editor, auto_break)
        return bl

    def _tps_of(self, x):
        return self.all_tps({"body": [x]})

    def spacer(self, role):
        G = self.geo()
        return Block(self.empty_xml(role), G.H.pitch(role.ps, role.cs), "빈 줄")

    def capacity(self, col=None):
        return self.geo().col_h

    # ── 원고 묶음(문항·세트) 풀기
    @staticmethod
    def entries(exam):
        """시험 dict → [(종류, 원고, 번호들)] 종류 "item" | "set"."""
        out, n = [], 0
        for e in exam.get("문항") or []:
            if isinstance(e, dict) and "세트" in e and isinstance(e.get("문항"), list):
                nums = list(range(n + 1, n + 1 + len(e["문항"])))
                out.append(("set", e, nums))
                n += len(e["문항"])
            else:
                n += 1
                out.append(("item", e, [n]))
        return out

    # ── 검사
    def validate_item(self, n, item, diag, base_dir=None, in_set=False):
        ok = True
        if not isinstance(item, dict):
            diag.error("MISSING_FIELD", "문항이 객체가 아닙니다")
            return False
        for key in ("발문", "선지") + (() if in_set else ()):
            if not item.get(key):
                diag.error("MISSING_FIELD", "'%s' 항목이 없습니다" % key, where=(key,))
                ok = False
        if not in_set and not item.get("지문") and not item.get("보기"):
            pass                                          # PSAT 은 지문 없는 문항(계산형 등)도 있다
        ans = item.get("정답")
        if ans is not None and not (isinstance(ans, int) and not isinstance(ans, bool) and 1 <= ans <= 5):
            diag.error("ANSWER_INVALID", "정답은 1~5 정수여야 합니다(지금 %r)" % (ans,), where=("정답",))
            ok = False
        sol = item.get("해설")
        if isinstance(sol, dict) and sol.get("난이도") is not None:
            lv = sol.get("난이도")
            if not (isinstance(lv, int) and not isinstance(lv, bool) and 1 <= lv <= 5):
                diag.error("DIFFICULTY_INVALID", "난이도는 1~5 정수여야 합니다(지금 %r)" % (lv,), where=("해설", "난이도"))
                ok = False
        if len(item.get("보기") or []) > len(BOGI_HEADS):
            diag.error("BOGI_COUNT", "<보기>가 %d개입니다(%d개까지)" % (len(item["보기"]), len(BOGI_HEADS)), where=("보기",))
            ok = False
        stem = str(item.get("발문", ""))
        has_bogi = bool(item.get("보기"))
        mentions = bool(re.search(r"<\s*보\s*기\s*>|〈\s*보\s*기\s*〉", stem))
        if mentions and not has_bogi:
            diag.error("BOGI_MISMATCH", "발문이 <보기>를 가리키는데 '보기'가 없습니다", where=("발문",))
        if has_bogi and not mentions:
            diag.warning("BOGI_NOT_IN_STEM", "'보기'가 있는데 발문이 <보기>를 가리키지 않습니다", where=("보기",))
        return ok

    # ── 하네스 API(문항·세트 단위)
    def validate(self, entry, number=None, base_dir=None):
        diag = Diag(number)
        ctx = self.new_ctx()
        if isinstance(entry, dict) and "세트" in entry:
            n0 = number or 1
            if not entry.get("문항"):
                diag.error("SET_EMPTY", "세트에 문항이 없습니다")
            self.plan_set(n0, n0 + max(len(entry.get("문항") or []), 1) - 1, entry["세트"], diag, base_dir)
            for k, it in enumerate(entry.get("문항") or []):
                d = Diag(n0 + k)
                if self.validate_item(n0 + k, it, d, base_dir, in_set=True):
                    self.plan_item(n0 + k, it, d, ctx, base_dir)
                diag.extend(d)
            return diag.as_list()
        if self.validate_item(number or 1, entry, diag, base_dir):
            self.plan_item(number or 1, entry, diag, ctx, base_dir)
        return diag.as_list()

    def wrap(self, entry, rewrap=True, number=None, base_dir=None):
        diag = Diag(number)
        new = copy.deepcopy(entry)
        if rewrap:
            unwrap(new)
        if isinstance(new, dict) and "세트" in new:
            n0 = number or 1
            sp = self.plan_set(n0, n0 + len(new.get("문항") or []) - 1, new["세트"], Diag(), base_dir)
            out = copy.deepcopy(new)
            for tp in self.all_tps(sp):
                self._wrap_tp(tp, out, diag, check=not rewrap)
            for k, it in enumerate(new.get("문항") or []):
                d = Diag(n0 + k)
                out["문항"][k] = self._wrap_item(n0 + k, it, d, base_dir, check=not rewrap)
                diag.extend(d)
            return out, diag.as_list()
        return self._wrap_item(number or 1, new, diag, base_dir, check=not rewrap), diag.as_list()

    def _wrap_item(self, n, item, diag, base_dir, check):
        out = copy.deepcopy(item)
        if not self.validate_item(n, item, Diag(n), base_dir):
            return out
        plan = self.plan_item(n, item, Diag(n), self.new_ctx(), base_dir)
        for tp in self.all_tps(plan):
            self._wrap_tp(tp, out, diag, check)
        return out

    def _wrap_tp(self, tp, out, diag, check):
        if not tp.src or not tp.wrap_lines:
            return
        if "\n" in tp.body:
            if check:
                lines = tp.text.split("\n")
                for k, what, nat, avail in check_lines(lines, tp.first_w, tp.rest_w, self.width.with_shrink(tp.shrink)):
                    code = "LINE_OVERFLOW" if what == "over" else "LINE_LOOSE"
                    msg = "%d째 줄이 넘쳐 한글이 다시 나눕니다" if what == "over" else "%d째 줄이 헐겁습니다"
                    diag.warning(code, (msg % k) + "(자연 폭 %.0f / 줄 폭 %.0fpt)" % (nat, avail), where=tp.src,
                                 line=k, natural=round(nat, 1), avail=round(avail, 1))
            return
        broken = tp.broken(self.width)
        if "\n" not in broken:
            return
        try:
            parent = out
            for k in tp.src[:-1]:
                parent = parent[k]
            if isinstance(parent, str):            # 주석이 문자열 하나일 때 ("주석", 0)
                grand = out
                for k in tp.src[:-2]:
                    grand = grand[k]
                grand[tp.src[-2]] = tp.prefix + broken
                return
            set_body(out, tp.src, tp.prefix, broken)
        except (KeyError, IndexError, TypeError):
            pass

    def measure(self, entry, number=None, total=None, base_dir=None):
        """분량. 문항은 단 맨 위에서 시작한다고 보고(빈 줄 포함) 한 단 높이와 견준다.
        세트는 실제 배치처럼 단에 쌓아 보고 쓰는 단 수(columns)와 넘침을 알린다."""
        G, S = self.geo(), self.style
        ctx = self.new_ctx()
        editor = HeaderEditor(G.doc.header)          # 모양 변형은 버린다(측정용)
        ctx.variants = editor
        pitch = self.line_pt()
        cap = self.capacity()
        top = self.spacer(S.spacer_top) if S.use_top_spacer else None
        if isinstance(entry, dict) and "세트" in entry:
            n0 = number or 1
            its = entry.get("문항") or []
            sp = self.plan_set(n0, n0 + len(its) - 1, entry["세트"], Diag(), base_dir)
            units = [Unit("set", self.set_blocks(sp, ctx, editor, True), "column", top)]
            per = self._per_block(sp)
            for k, it in enumerate(its):
                if self.validate_item(n0 + k, it, Diag(), base_dir, in_set=True):
                    p = self.plan_item(n0 + k, it, Diag(), ctx, base_dir)
                    units.append(Unit(k, self.item_blocks(p, ctx, editor, True), "fit",
                                      self.spacer(S.spacer_top) if S.use_top_spacer else None,
                                      self.spacer(S.spacer_between)))
                    per += self._per_block(p, n0 + k)
            ncols, placed = place(units, lambda c: cap)
            h = sum(p["height"] for p in placed)
            over = any(p["over"] for p in placed)
            spare = (ncols * cap - h) / pitch
            return {"lines": sum(b.lines for u in units for b in u.info["blocks"]), "height_pt": round(h, 1),
                    "capacity_pt": round(cap, 1), "spare_lines": round(spare, 1), "columns": ncols,
                    "per_block": per, "verdict": "over" if over else "ok"}
        if not self.validate_item(number or 1, entry, Diag(), base_dir):
            return {"lines": 0, "height_pt": 0.0, "capacity_pt": round(cap, 1), "spare_lines": None,
                    "per_block": [], "verdict": "invalid"}
        p = self.plan_item(number or 1, entry, Diag(), ctx, base_dir)
        if number == 1 and not S.first_unit_lead:
            top = None                                  # 1번은 머리 문단 바로 뒤(빈 줄 없음)
        blocks = ([top] if top else []) + self.item_blocks(p, ctx, editor, True)
        per = self._per_block(p)
        h = sum(b.height for b in blocks)
        spare = (cap - h) / pitch
        return {"lines": sum(b.lines for b in blocks), "height_pt": round(h, 1), "capacity_pt": round(cap, 1),
                "spare_lines": round(spare, 1), "columns": max(1, math.ceil(h / cap)), "per_block": per,
                "verdict": "over" if spare < 0 else "tight" if spare < TIGHT_LINES else "ok"}

    def _per_block(self, plan, number=None):
        out = []
        for tp in self.all_tps(plan):
            d = {"src": list(tp.src), "lines": tp.lines, "kind": tp.kind}
            if number is not None:
                d["item"] = number
            out.append(d)
        for x in plan.get("body", []):
            if isinstance(x, Box):
                out.append({"src": list(x.src), "height_pt": round(self.box_height(x), 1),
                            "kind": "상자" if not x.title else x.title.replace(" ", "")})
        return out

    # ── 입력 단계 안내
    def line_guide(self):
        """줄당 글자수 어림(빈칸 포함)·단 높이·줄 수 — 작성 단계가 글자수를 줄 수로 환산할 때 쓴다."""
        from .layout import chars_per_line
        G = self.geo()
        S = self.style
        col = G.col_w
        pitch = G.H.pitch(S.box_text.ps, S.box_text.cs)
        stem_w = col - abs(G.H.para[S.stem.ps].offsets()[1]) if S.stem.ps in G.H.para else col - 20.0
        box_w = col - 36.6                       # 상자(보기·보고서·상황) 안 글 폭(상자 테두리·안쪽 여백)
        return {"줄당_글자수(빈칸 포함, 어림)": {"발문·본문": chars_per_line(stem_w, self.width), "상자 안(보기·보고서·상황)": chars_per_line(box_w, self.width)},
                "단_폭_pt": round(col, 1), "단_높이_pt": round(G.col_h, 1), "줄_간격_pt": round(pitch, 2),
                "단당_줄_수(어림)": int(G.col_h // pitch),
                "비고": "PSAT 는 기출 줄당 글자수 실측 표가 아직 없어 글자 폭 모형과 단 폭에서 어림했다(한글 77%·빈칸 23%). 조판기는 폭으로 줄을 정한다."}

    # ── 조판
    def typeset_exam(self, exam, out_path, title=None, strict=False, base_dir=None, auto_break="fit",
                     solution=True, template_path=None, solution_template_path=None):
        title = title or exam.get("시험명")
        diag = Diag()
        result = {"path": None, "pages": None, "items": [], "diagnostics": None, "solution_path": None,
                  "columns": None, "profile": self.name}
        ents = self.entries(exam)
        total = sum(len(e[2]) for e in ents)
        if total > self.max_items:
            diag.error("ITEM_COUNT", "문항이 %d개입니다(%d개까지)" % (total, self.max_items), count=total)
        saved = (self.template_path, self._geo)
        if template_path:
            self.template_path, self._geo = template_path, None
        try:
            return self._typeset_exam(exam, out_path, title, strict, base_dir, auto_break, solution,
                                      solution_template_path, diag, result, ents, total)
        finally:
            self.template_path, self._geo = saved

    def _typeset_exam(self, exam, out_path, title, strict, base_dir, auto_break, solution, solution_template_path,
                      diag, result, ents, total):
        from ...core.api import StrictError, load_profile
        S = self.style
        try:
            G = self.geo()
        except TemplateError as e:
            diag.error(e.code, str(e))
            result["diagnostics"] = diag.as_list()
            raise StrictError(result) if strict else e
        missing = G.H.missing(ps=self._ids("ps"), cs=self._ids("cs"))
        if missing:
            diag.error("TEMPLATE_IDS", "양식에 없는 모양 번호: " + ", ".join(missing[:8]))
            result["diagnostics"] = diag.as_list()
            raise StrictError(result) if strict else TemplateError("TEMPLATE_IDS", diag.items[-1]["message"])
        editor = HeaderEditor(G.doc.header)
        ctx = self.new_ctx()
        ctx.variants = editor
        ctx.header_editor = editor
        ctx.reserve([G.sec] + [G.doc.read(m) for m in G.doc.masters()])
        units, figures, bins = [], [], {}
        reserved = self.reserved_bins(G)
        lead_top, lead_between = (lambda: self.spacer(S.spacer_top)), (lambda: self.spacer(S.spacer_between))
        for kind, e, nums in ents:
            if kind == "set" and not nums:
                diag.error("SET_EMPTY", "세트에 문항이 없습니다")
                continue
            if kind == "set":
                d = Diag(nums[0])
                sp = self.plan_set(nums[0], nums[-1], e["세트"], d, base_dir)
                sfigs = [f for x in sp["body"] for f in self._figs(x)]
                self.assign_bins(sfigs, bins, reserved)
                bl = self.set_blocks(sp, ctx, editor, auto_break)
                units.append(Unit(("set", nums[0]), bl, "column", lead_top(), lead_between(),
                                  "[%d～%d]" % (nums[0], nums[-1]), tuple(nums)))
                figures += sfigs
                diag.extend(d)
                items = list(zip(nums, e.get("문항") or []))
                policy = "fit"
            else:
                items = [(nums[0], e)]
                policy = None
            for n, item in items:
                d = Diag(n)
                if not self.validate_item(n, item, d, base_dir, in_set=(kind == "set")):
                    diag.extend(d)
                    result["items"].append({"number": n, "verdict": "invalid"})
                    continue
                plan = self.plan_item(n, item, d, ctx, base_dir)
                ifigs = [f for x in plan["body"] + ([plan["bogi"]] if plan["bogi"] else []) +
                         [x for k2, x in plan["choices"] if k2 == "obj"] for f in self._figs(x)]
                self.assign_bins(ifigs, bins, reserved)
                bl = self.item_blocks(plan, ctx, editor, auto_break)
                pol = policy or ("fit" if item.get("이어붙이기") else "column")
                if item.get("새단"):
                    pol = "column"
                units.append(Unit(("item", n), bl, pol, lead_top(), lead_between(), "%d번" % n, (n,),
                                  info={"id": item.get("id"), "layout": plan["layout"]}))
                figures += ifigs
                diag.extend(d)
        # 첫 덩이는 머리 문단 바로 뒤(빈 줄은 머리 문단이 맡는다)
        if units and not S.first_unit_lead:
            units[0].lead_top = None
        if not S.use_top_spacer:
            for u in units:
                u.lead_top = None
        ncols, placed = place(units, lambda c: self.capacity(c))
        any_over = any(p["over"] for p in placed)
        self.after_place(ncols, any_over)
        if any_over and self.shows_total_pages:
            diag.error("PAGECOUNT_UNRELIABLE", "넘친 문항이 있어 전체 쪽 수를 바꾸지 않았습니다(양식 값 그대로)")
        pitch = self.line_pt()
        by_key = {p["key"]: p for p in placed}
        for u in units:
            p = by_key[u.key]
            if u.key[0] != "item":
                if p["over"]:
                    diag.error("SET_OVER", "세트 %s 지문 상자가 한 단(%.0fpt)보다 깁니다" % (u.label, self.capacity()),
                               item=u.key[1])
                continue
            n = u.key[1]
            h = p["height"]
            cap = self.capacity(p["start_col"])
            m = {"number": n, "id": u.info.get("id"), "layout": u.info.get("layout"),
                 "lines": sum(b.lines for b in u.info["blocks"]), "height_pt": h, "capacity_pt": round(cap, 1),
                 "spare_lines": round((cap - h) / pitch, 1), "column": p["start_col"] + 1,
                 "page": p["start_col"] // 2 + 1,
                 "verdict": "over" if p["over"] or h > cap else "tight" if (cap - h) / pitch < TIGHT_LINES else "ok"}
            if p["over"] or h > cap + 0.5:
                diag.error("ITEM_OVER", "문항 높이 %.0fpt가 단 높이 %.0fpt를 넘습니다" % (h, cap), item=n,
                           height=h, capacity=round(cap, 1))
            elif p["split"] and u.policy == "column":
                diag.warning("ITEM_SPLIT", "문항이 두 단에 걸칩니다", item=n)
            result["items"].append(m)
        result["items"].sort(key=lambda m: m["number"])
        pages = (ncols + 1) // 2
        result["pages"] = pages
        result["columns"] = ncols
        if strict and diag.errors():
            result["diagnostics"] = diag.as_list()
            raise StrictError(result)
        from ...core.flow import render
        body = render(units)
        self.build(G, editor, out_path, body, figures, title, diag)
        result["path"] = out_path
        if solution and self.solution_profile:
            flat = [it for kind, e, nums in ents for it in ((e.get("문항") or []) if kind == "set" else [e])]
            if any(isinstance(it, dict) and it.get("해설") for it in flat):
                SP = load_profile(self.solution_profile)
                sol_out = out_path[:-5] + "_해설.hwpx" if out_path.endswith(".hwpx") else out_path + "_해설.hwpx"
                kw = {}
                if "sets" in SP.build.__code__.co_varnames:
                    kw["sets"] = [(nums[0], (e.get("문항") or []) if kind == "set" else [e],
                                   e.get("세트") if kind == "set" else {}) for kind, e, nums in ents]
                SP.build(flat, sol_out, title=title, review=exam.get("총평"), diag=diag,
                         template_path=solution_template_path, **kw)
                result["solution_path"] = sol_out
        result["diagnostics"] = diag.as_list()
        if strict and diag.errors():
            raise StrictError(result)
        return result

    def prefix_xml(self, G):
        """본문 앞(머리말·표지) XML."""
        tops = top_paragraphs(G.sec)
        return G.sec[:tops[0][1]]

    def reserved_bins(self, G):
        """양식에서 본문 밖(머리말·바탕쪽·header)이 쓰는 그림 이름 — 새 그림 이름과 겹치면 안 된다."""
        keep = self.prefix_xml(G) + "".join(G.doc.read(m) for m in G.doc.masters()) + G.doc.header
        return set(re.findall(r'binaryItemIDRef="([^"]+)"', keep))

    def assign_bins(self, figs, bins, reserved):
        """그림마다 BinData 이름(imageN)을 정한다. 같은 파일은 한 이름. XML 을 만들기 전에 불러야 한다."""
        for f in figs:
            if f.abspath not in bins:
                k = len(bins) + 1
                used = set(bins.values()) | reserved
                while "image%d" % k in used:
                    k += 1
                bins[f.abspath] = "image%d" % k
            f.bin_id = bins[f.abspath]

    def _figs(self, x):
        if isinstance(x, Fig):
            return [x]
        if isinstance(x, Box):
            return [y for z in x.content for y in self._figs(z)]
        return []

    def _ids(self, kind):
        S = self.style
        roles = [getattr(S, k) for k in S.__dataclass_fields__ if hasattr(getattr(S, k), "ps")]
        if S.table:
            roles += [getattr(S.table, k) for k in S.table.__dataclass_fields__ if hasattr(getattr(S.table, k), "ps")]
        if kind == "ps":
            return sorted({r.ps for r in roles})
        return sorted({r.cs for r in roles} | {r.hcs for r in roles})

    def build(self, G, editor, out_path, body, figures, title, diag):
        S = self.style
        sec = G.sec
        tops = top_paragraphs(sec)
        prefix = sec[:tops[0][1]]
        tail = sec[tops[-1][1]:]
        if title:
            prefix, k = replace_text_across(prefix, S.title_text, title)
            if not k:
                diag.error("TEMPLATE_TITLE", "양식 머리말에서 시험명 자리('%s')를 찾지 못했습니다" % S.title_text)
        new_sec = prefix + body + tail
        reserved = self.reserved_bins(G)        # 머리말·바탕쪽이 쓰는 양식 그림만 남긴다(견본 문항 그림은 지움)
        drop = [n for n in G.doc.bin_names() if os.path.splitext(os.path.basename(n))[0] not in reserved]
        add = []
        seen = set()
        for f in figures:
            if f.bin_id in seen:
                continue
            seen.add(f.bin_id)
            with open(f.abspath, "rb") as fh:
                add.append(("BinData/%s.png" % f.bin_id, fh.read(), "image/png", f.bin_id))
        prv = "%s %s영역" % (title or "", S.subject)
        G.doc.write(out_path, {"Contents/section0.xml": new_sec, "Contents/header.xml": editor.header,
                               "Preview/PrvText.txt": prv.strip()}, add_bins=add, drop_bins=drop)
