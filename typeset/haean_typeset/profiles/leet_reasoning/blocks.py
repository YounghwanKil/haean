# -*- coding: utf-8 -*-
"""LEET 추리논증 원고 블록 → 문단·표·그림 계획."""
import os
import re

from ...core.inline import runs, FW, NB, TAB, plain
from ...core.linebreak import count_lines
from ...core.model import Para, Table, Figure, Cell
from ...core.png import png_info
from . import ids as I
from . import layout as L

LISTY = {"나열", "목록", "호", "항"}          # 문단 아래 5pt 를 부르는 블록
OBJ_KEYS = ("문단", "소제목", "라벨", "조건", "나열", "실험", "원리", "목록", "조문", "항", "호", "의안", "표", "그림")
TABLE_KEYS = {"표", "제목", "단위", "주석", "머리행"}
FIG_KEYS = {"그림", "폭"}

PATTERNS = [
    ("의안", re.compile(r"^<\s*의안\s*(\d+)\s*>\s*(.*)$", re.S)),
    ("소제목", re.compile(r"^(<[^<>]{1,15}>|\[[^\[\]]{1,15}\])$")),
    ("원리", re.compile(r"^\[원리\]\s*(.+)$", re.S)),
    ("조문", re.compile(r"^(제\s*(?:\d+|○)\s*조(?:의\s*\d+)?(?:\([^)]{1,20}\))?)\s*(.*)$", re.S)),
    ("항", re.compile(r"^([②-⑳])\s*(.+)$", re.S)),
    ("호", re.compile(r"^(\d{1,2})\.\s+(.+)$", re.S)),
    ("조건", re.compile(r"^◦\s*조건\s*(\d+)\s*:\s*(.*)$", re.S)),
    ("나열", re.compile(r"^◦\s*(.+)$", re.S)),
    ("실험", re.compile(r"^실험\s*(\d+)\s*:\s*(.*)$", re.S)),
    ("목록", re.compile(r"^\((\d{1,2})\)\s*(.+)$", re.S)),
    ("발언", re.compile(r"^([가-힣](?:\s*\d{1,2})?|[A-Z]\d{0,2})\s*:\s*(.*)$", re.S)),
    # 양식에 없는 꼴의 라벨(예: 'A 가설 :', '주장 1 :'): 발언으로 보고 UNKNOWN_LABEL 로 알린다
    ("발언", re.compile(r"^(\S{1,6}(?: \S{1,4})?)\s*:\s+(.+)$", re.S)),
]
LABELISH = re.compile(r"^[^\s.,!?\"'‘’“”()]{1,6}(?: [^\s.,!?\"'‘’“”()]{1,4})?$")
FULLWIDTH_HEAD = re.compile(r"^〈[^〈〉]{1,15}〉$")


def classify(block):
    """블록 → (종류, 라벨, 글). 표 → ("표", None, 블록 dict), 그림 → ("그림", None, 블록 dict),
    모르는 객체 → ("?", None, 블록)."""
    if isinstance(block, dict):
        if "표" in block:
            return "표", None, block
        if "그림" in block:
            return "그림", None, block
        if "라벨" in block:
            return "발언", block["라벨"], block.get("글", "")
        for k in ("조건", "실험", "목록", "조문", "항", "호", "의안"):
            if k in block:
                return k, block[k], block.get("글", "")
        for k in ("문단", "소제목", "나열", "원리"):
            if k in block:
                return k, None, block[k]
        return "?", None, block
    s = block.strip()
    for kind, rx in PATTERNS:
        m = rx.match(s)
        if not m:
            continue
        if kind == "소제목":
            return kind, None, s
        if kind in ("원리", "나열"):
            return kind, None, m.group(1)
        if kind == "발언" and (not LABELISH.match(m.group(1)) or re.fullmatch(r"[\d ]+", m.group(1))
                               or (m.group(1)[-1].isdigit() and m.group(2)[:1].isdigit())):
            continue                                    # 라벨처럼 보이지 않으면(문장 속 쌍점·비율 1 : 2) 일반 문단
        return kind, m.group(1), m.group(2)
    return "문단", None, s


def speaker(label):
    """발언 라벨 꼴 → (문단 모양, 내어쓰기, 머리). 양식에 없는 꼴이면 None."""
    lab = re.sub(r"\s+", " ", label.strip())
    if re.fullmatch(r"[가-힣]", lab):
        return I.PS_SPK_HAN, 20.6, lab + FW + ":" + NB
    if re.fullmatch(r"[가-힣]\d+", lab):
        return I.PS_SPK_HAN_NUM, 25.8, lab + FW + ":" + NB
    if re.fullmatch(r"[가-힣] \d+", lab):
        a, b = lab.split(" ")
        return I.PS_SPK_HAN_TAB, 26.18, a + TAB + b + FW + ":" + NB
    if re.fullmatch(r"[A-Z]", lab):
        ps, ind = (I.PS_SPK_LAT_X, 18.52) if lab in "WXYZ" else (I.PS_SPK_LAT, 18.38)
        return ps, ind, lab + TAB + ":" + NB
    if re.fullmatch(r"[A-Z]\d+", lab):
        return I.PS_SPK_LAT_NUM, 22.44, lab + FW + ":" + NB
    return None


def box_para(ps, st, r, kind, text, src, head="", **kw):
    p = Para(ps, st, r, kind, text=text, src=src, head=head, container=L.PASSAGE_W, left_pt=8.5, right_pt=8.5,
             gap_after=3.0, line_pt=L.LINE)
    for k, v in kw.items():
        setattr(p, k, v)
    return p


# ── 그림
def load_figure(spec, where, diag, base_dir, inner_w):
    """그림 블록 → Figure (없거나 깨졌으면 None, FIGURE_MISSING)."""
    path = spec.get("그림") if isinstance(spec, dict) else spec
    if not isinstance(path, str) or not path:
        diag.error("FIGURE_MISSING", "그림 경로가 없습니다", where=where)
        return None
    full = path if os.path.isabs(path) else os.path.join(base_dir or ".", path)
    if not os.path.isfile(full):
        diag.error("FIGURE_MISSING", "그림 파일이 없습니다: %s" % path, where=where, path=path)
        return None
    try:
        pw, ph, dx, dy = png_info(full)
    except (OSError, ValueError) as e:
        diag.error("FIGURE_MISSING", "그림을 읽을 수 없습니다(%s): %s" % (e, path), where=where, path=path)
        return None
    nat = (pw / dx * 72.0, ph / dy * 72.0)
    want = spec.get("폭") if isinstance(spec, dict) else None
    w = float(want) if want else inner_w
    if w > inner_w:
        diag.warning("FIGURE_WIDE", "그림 폭 %.0fpt가 놓을 자리 %.0fpt보다 넓어 줄였습니다" % (w, inner_w),
                     where=where, width=w, limit=inner_w)
        w = inner_w
    h = w * ph / pw
    scale = w / nat[0]
    if scale < L.FIG_SMALL:
        diag.warning("FIGURE_SMALL", "그림을 원본의 %.0f%%로 줄여 그림 안 글자가 작아집니다" % (scale * 100),
                     where=where, scale=round(scale, 2))
    return Figure(path=path, abspath=full, width_pt=w, height_pt=h, px=(pw, ph), natural_pt=nat, src=where)


# ── 표
def table_cells(rows, where, diag):
    """원고 행 → (Cell 목록, 열 수). 합친 칸 {"글","가로","세로"}."""
    taken, out, ncols = set(), [], 0
    for r, row in enumerate(rows):
        c = 0
        for v in row:
            while (r, c) in taken:
                c += 1
            if isinstance(v, dict):
                text, cs, rs = str(v.get("글", "")), int(v.get("가로", 1)), int(v.get("세로", 1))
            else:
                text, cs, rs = str(v), 1, 1
            for dr in range(rs):
                for dc in range(cs):
                    taken.add((r + dr, c + dc))
            out.append(Cell(text, c, r, cs, rs))
            c += cs
            ncols = max(ncols, c)
    ncols = max([ncols] + [c + 1 for (_, c) in taken])
    nrows = len(rows)
    for r in range(nrows):
        for c in range(ncols):
            if (r, c) not in taken:
                out.append(Cell("", c, r))
    out.sort(key=lambda x: (x.row, x.col))
    return out, ncols


def plan_table(block, where, diag, wm):
    rows = block["표"]
    if not isinstance(rows, list) or not rows or not all(isinstance(r, list) for r in rows):
        diag.error("UNKNOWN_BLOCK", "표는 행 목록이어야 합니다", where=where)
        return None
    cells, ncols = table_cells(rows, where, diag)
    need = [L.COL_MIN] * ncols
    for c in cells:
        if c.colspan == 1:
            need[c.col] = max(need[c.col], wm.text_w(plain(c.text)) + 12)
    widths = [w * L.DATA_TABLE_W / sum(need) for w in need]
    heights = [L.ROW_H] * len(rows)
    for c in cells:
        if c.rowspan == 1:
            w = sum(widths[c.col:c.col + c.colspan]) - 2 * L.CELL_PAD_X
            n = count_lines(c.text, w, w, wm) if c.text else 1
            heights[c.row] = max(heights[c.row], n * L.CELL_LINE + 2 * L.CELL_PAD_Y)
    t = Table(rows=rows, title=str(block.get("제목", "") or ""), unit=str(block.get("단위", "") or ""),
              note=str(block.get("주석", "") or ""), header=bool(block.get("머리행", False)), src=where,
              cells=cells, col_widths=widths, row_heights=heights, ncols=ncols)
    extra = [k for k in block if k not in TABLE_KEYS]
    if extra:
        diag.warning("UNKNOWN_BLOCK", "표 블록의 모르는 키 %s 는 무시했습니다" % ", ".join(extra), where=where)
    inner = L.BOX_TEXT_INNER
    t.height = sum(heights) + L.TABLE_AFTER
    for s in (t.title, t.unit):
        if s:
            t.height += count_lines(s, inner, inner, wm) * L.CELL_LINE
    if t.note:
        t.height += count_lines(t.note, inner, inner, wm) * L.LINE + 3.0
    return t


# ── 지문
def passage_paras(blocks, diag, ctx, wm, base_dir=None):
    items = []
    for k, b in enumerate(blocks):
        kind, label, text = classify(b)
        where = ("지문", k)
        if kind == "?":
            diag.error("UNKNOWN_BLOCK", "모르는 블록 키 %s" % ", ".join(sorted(b)), where=where, keys=sorted(b))
            continue
        if isinstance(b, dict) and kind not in ("표", "그림"):
            bad = [x for x in b if x not in OBJ_KEYS + ("글",)]
            if bad:
                diag.error("UNKNOWN_BLOCK", "블록의 모르는 키 %s" % ", ".join(bad), where=where, keys=bad)
        if kind == "문단" and isinstance(b, str) and FULLWIDTH_HEAD.match(b.strip()):
            diag.error("NONCANONICAL_BRACKET", "전각 꺾쇠 '%s'는 소제목으로 쓰지 않습니다. 반각 < >로 쓰십시오"
                       % b.strip(), where=where)
        items.append((k, kind, label, text))
    out = []
    for i, (k, kind, label, text) in enumerate(items):
        nxt = items[i + 1][1] if i + 1 < len(items) else None
        where = ("지문", k)
        body = I.CS_BODY
        if kind == "표":
            t = plan_table(text, where, diag, wm)
            if t:
                out.append(t)
            continue
        if kind == "그림":
            f = load_figure(text, where, diag, base_dir, L.BOX_TEXT_INNER)
            if f:
                out.append(f)
            continue
        if kind == "문단":
            if nxt in (None, "문단"):
                ps, gap = I.PS_BOXTEXT_0, 0.0
            elif nxt in LISTY:
                ps, gap = I.PS_BOXTEXT_5, 5.0
            else:
                ps, gap = I.PS_BOXTEXT_10, 10.0
            out.append(box_para(ps, I.ST_BOXTEXT, runs(text, body, ctx), kind, text, where, first_pt=10.4,
                                gap_after=gap))
            continue
        if kind == "소제목":
            out.append(box_para(I.PS_CASEHEAD, I.ST_CASEHEAD, runs(text, I.CS_CASEHEAD, ctx), kind, text, where,
                                gap_before=8.0))
            continue
        if kind == "발언":
            sp = speaker(label)
            if sp is None:
                diag.error("UNKNOWN_LABEL", "라벨 '%s'은 양식에 없는 꼴입니다(허용: 갑 : · 갑1 : · 을 1 : · A : · X : · P1 :)"
                           % label, where=where, label=label)
                ps, ind, head = I.PS_SPK_HAN, 20.6, label.strip() + FW + ":" + NB
            else:
                ps, ind, head = sp
            out.append(box_para(ps, I.ST_BOXITEM, runs(head + text, body, ctx), kind, head + text, where, head=head,
                                indent_pt=ind))
            continue
        simple = {
            "조건": (I.PS_COND, 51.36, lambda: "◦" + FW + "조건" + FW + label + FW + ":" + NB),
            "나열": (I.PS_BULLET, 13.04, lambda: "◦" + FW),
            "실험": (I.PS_EXPER, 38.32, lambda: "실험" + FW + label + FW + ":" + NB),
            "원리": (I.PS_PRINCIPLE, 32.4, lambda: "[원리]" + NB),
            "목록": (I.PS_LIST, 18.4, lambda: "(%s)" % label + NB),
            "호": (I.PS_ITEM, 0.0, lambda: "%s." % label + NB),
            "항": (I.PS_CLAUSE, 0.0, lambda: label + " "),
        }
        if kind in simple:
            ps, ind, head = simple[kind]
            h = head()
            out.append(box_para(ps, I.ST_BOXITEM, runs(h + text, body, ctx), kind, h + text, where, head=h,
                                indent_pt=ind, left_pt={"호": 30.8, "항": 26.3}.get(kind, 8.5),
                                gap_after=13.0 if kind == "원리" else 3.0))
            continue
        if kind == "조문":
            head = re.sub(r"^제\s*(\d+|○)\s*조", r"제\1조", label.strip())
            r = [(I.CS_ARTICLE, [("t", head)])] + runs(NB + text, body, ctx)
            out.append(box_para(I.PS_ARTICLE, I.ST_BOXITEM, r, kind, head + NB + text, where, head=head + NB,
                                indent_pt=17.72))
            continue
        if kind == "의안":
            r = [(I.CS_BOLD, [("t", "<의안"), ("fw",), ("t", "%s>" % label)])] + runs(NB + text, body, ctx)
            h = "<의안" + FW + label + ">" + NB
            out.append(box_para(I.PS_BILL, I.ST_BOXITEM, r, kind, h + text, where, head=h, indent_pt=18.2,
                                gap_before=10.0))
            continue
        raise AssertionError(kind)
    if out and isinstance(out[-1], Para) and out[-1].kind == "문단":
        out[-1].gap_after = 0.0
    return out


BOGI_HEADS = "ㄱㄴㄷㄹㅁ"


def bogi_paras(items, diag, ctx, base_dir=None):
    out = []
    for k, v in enumerate(items):
        text = v if isinstance(v, str) else str(v.get("글", ""))
        text = re.sub(r"^\s*[ㄱ-ㅁ]\s*\.\s*", "", text)
        ps = I.PS_BOGI_G if k == 0 else I.PS_BOGI_N if k == 1 else I.PS_BOGI_REST
        ind = 17.92 if k == 0 else 18.16 if k == 1 else 18.2
        head = BOGI_HEADS[k] + "." + NB
        out.append(Para(ps, I.ST_BOXITEM, runs(head + text, I.CS_BODY, ctx), "보기", indent_pt=ind, text=head + text,
                        container=L.BOGI_W, left_pt=8.5, right_pt=8.5, gap_after=3.0, src=("보기", k), head=head,
                        line_pt=L.LINE))
        if isinstance(v, dict) and "그림" in v:
            f = load_figure(v, ("보기", k), diag, base_dir, L.BOGI_TEXT_INNER)
            if f:
                out.append(f)
    return out


MARKS = "①②③④⑤"


def choice_paras(choices, diag, ctx, wm, base_dir=None, layout_hint=None):
    """→ (문단 목록, 배치, 그림 선지 Figure 목록)."""
    if len(choices) != 5:
        diag.error("CHOICE_COUNT", "선지가 %d개입니다(5개여야 함)" % len(choices), where=("선지",), count=len(choices))
    figs = [isinstance(c, dict) and "그림" in c for c in choices]
    if any(figs):
        if not all(figs):
            diag.error("CHOICE_FIGURE_MIXED", "그림 선지와 글 선지가 섞여 있습니다", where=("선지",))
        fl = []
        for k, c in enumerate(choices):
            if isinstance(c, dict) and "그림" in c:
                f = load_figure(c, ("선지", k), diag, base_dir, 1e9)      # 폭은 배치를 정한 뒤 맞춘다
                if f:
                    fl.append(f)
        layout = layout_hint if layout_hint in ("2열", "1열") else \
            ("1열" if fl and all(f.px[0] / f.px[1] >= L.WIDE for f in fl) else "2열")
        cell_w = L.PIC2_COLS[1] if layout == "2열" else L.PIC1_COLS[1]
        for f in fl:
            want = None
            for c in choices:
                if isinstance(c, dict) and c.get("그림") == f.path and c.get("폭"):
                    want = float(c["폭"])
            w = min(want or cell_w, cell_w)
            f.width_pt, f.height_pt = w, w * f.px[1] / f.px[0]
            if w / f.natural_pt[0] < L.FIG_SMALL:
                diag.warning("FIGURE_SMALL", "그림 선지를 원본의 %.0f%%로 줄여 글자가 작아집니다"
                             % (w / f.natural_pt[0] * 100), where=f.src, scale=round(w / f.natural_pt[0], 2))
            f.kind = "그림선지"
        return [], "그림 " + layout, fl
    cleaned = [re.sub(r"^\s*[①-⑤]\s*", "", c if isinstance(c, str) else str(c.get("글", ""))) for c in choices]
    widest = max((wm.text_w(MARKS[0] + " " + c) for c in cleaned), default=0)
    if widest <= L.CHOICE_SLOT and len(cleaned) == 5:
        out = []
        for li, line in enumerate([cleaned[:3], cleaned[3:]]):
            r = []
            for j, c in enumerate(line):
                if j:
                    r.append(TAB)
                r.append(MARKS[li * 3 + j] + NB + c)
            txt = "".join(r)
            out.append(Para(I.PS_CHOICE_32, I.ST_CHOICE, runs(txt, I.CS_CHOICE, ctx), "선지3+2", left_pt=10.4,
                            container=L.COL_W, text=txt, gap_after=3.0, line_pt=L.LINE))
        return out, "3+2", []
    out = []
    for k, c in enumerate(cleaned[:5]):
        txt = MARKS[k] + NB + c
        out.append(Para(I.PS_CHOICE_1, I.ST_CHOICE, runs(txt, I.CS_CHOICE, ctx), "선지", indent_pt=15.64,
                        left_pt=10.4, container=L.COL_W, text=txt, src=("선지", k), head=MARKS[k] + NB,
                        gap_after=3.0, line_pt=L.LINE))
    return out, "한 줄에 하나", []


def stem_para(number, text, ctx):
    r = [(I.CS_NUM, [("t", "%d." % number)])] + runs(NB + text, I.CS_BODY, ctx)
    head = "%d." % number + NB
    return Para(I.PS_STEM, I.ST_STEM, r, "발문", indent_pt=10.4, container=L.COL_W, gap_after=5.7,
                text=head + text, src=("발문",), head=head, line_pt=L.LINE)


def item_plan(number, item, diag, ctx, wm, base_dir=None):
    choices, layout, figs = choice_paras(item.get("선지") or [], diag, ctx, wm, base_dir, item.get("그림선지배치"))
    return dict(stem=stem_para(number, item.get("발문", ""), ctx),
                passage=passage_paras(item.get("지문") or [], diag, ctx, wm, base_dir),
                bogi=bogi_paras(item.get("보기") or [], diag, ctx, base_dir),
                choices=choices, choice_figs=figs, layout=layout)


def plan_paras(plan):
    """원고 자리가 있는 문단(줄 나눔·줄 수 대상)."""
    out = [plan["stem"]] + [x for x in plan["passage"] if isinstance(x, Para)] + \
          [x for x in plan["bogi"] if isinstance(x, Para)] + plan["choices"]
    return [p for p in out if p.src]


def plan_objects(plan):
    return [x for x in plan["passage"] + plan["bogi"] if not isinstance(x, Para)] + plan["choice_figs"]


def set_source(item, src, body):
    """원고의 src 자리 글을 body(머리 뺀 글)로 바꾼다. 문자열 블록은 라벨 부분을 그대로 둔다."""
    field = src[0]
    if field == "발문":
        item["발문"] = body
        return
    if field in ("보기", "선지"):
        v = item[field][src[1]]
        if isinstance(v, dict):
            v["글"] = body
        else:
            item[field][src[1]] = body
        return
    k = src[1]
    blk = item["지문"][k]
    if isinstance(blk, dict):
        key = "글" if "글" in blk else next(x for x in blk if x not in ("표", "그림"))
        blk[key] = body
        return
    s = blk.strip()
    _, _, text = classify(s)
    item["지문"][k] = s[:len(s) - len(text)] + body


def get_source(item, src):
    """원고의 src 자리 글(머리 뺀 글). set_source 의 역."""
    try:
        field = src[0]
        if field == "발문":
            return item.get("발문", "")
        if field in ("보기", "선지"):
            v = item[field][src[1]]
            return v.get("글", "") if isinstance(v, dict) else v
        blk = item["지문"][src[1]]
        if isinstance(blk, dict):
            key = "글" if "글" in blk else next((x for x in blk if x not in ("표", "그림", "폭")), None)
            return blk.get(key, "") if key else ""
        return blk
    except (KeyError, IndexError, TypeError):
        return ""


def unwrap(item):
    """원고의 문단 안 줄바꿈(\\n)을 빈칸으로(다시 나누기 전)."""
    j = lambda s: re.sub(r"\s*\n\s*", " ", s) if isinstance(s, str) else s
    if isinstance(item.get("발문"), str):
        item["발문"] = j(item["발문"])
    for key in ("보기", "선지"):
        for k, v in enumerate(item.get(key) or []):
            if isinstance(v, str):
                item[key][k] = j(v)
            elif isinstance(v, dict) and "글" in v:
                v["글"] = j(v["글"])
    for k, b in enumerate(item.get("지문") or []):
        if isinstance(b, str):
            item["지문"][k] = j(b)
        elif isinstance(b, dict):
            for key in b:
                if key not in ("표", "그림", "폭") and isinstance(b[key], str):
                    b[key] = j(b[key])
