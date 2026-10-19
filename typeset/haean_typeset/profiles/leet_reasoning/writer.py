# -*- coding: utf-8 -*-
"""LEET 추리논증 문항 XML (지문 박스·<보기> 상자·자료표·그림·그림 선지·선지)."""
from ...core.hwpx import p_xml, tc_xml, tbl_xml, holder, pic_xml, COLPR
from ...core.inline import runs
from ...core.model import Para, Table, Figure
from . import ids as I
from . import layout as L


def paras_xml(plan, ctx, pic_skeleton):
    """상자 칸 안 문단들. 첫 문단에 단 정의를 단다(양식과 같게)."""
    out = []
    for k, x in enumerate(plan):
        if isinstance(x, Table):
            out.append(data_table_xml(x, ctx, colpr=(k == 0)))
        elif isinstance(x, Figure):
            out.append(figure_para(x, ctx, pic_skeleton, colpr=(k == 0)))
        else:
            out.append(p_xml(x, ctx, colpr=(k == 0)))
    return "".join(out)


def figure_para(fig, ctx, pic_skeleton, colpr=False):
    run = (COLPR if colpr else "") + pic_xml(pic_skeleton, fig, ctx)
    return holder(I.PS_FIGURE, I.ST_FIGURE, I.CS_FIGURE, run)


def data_table_xml(t, ctx, colpr=False):
    """자료표: 사방 실선(테두리 3), 칸 여백 좌우 5.1·위아래 1.41. 제목(위 가운데)·단위(위 오른쪽)·주석(아래)."""
    trs = []
    for r in range(len(t.row_heights)):
        tcs = ""
        for c in [c for c in t.cells if c.row == r]:
            cell = Para(I.PS_TABLE_CELL, I.ST_TABLE, runs(c.text, I.CS_TABLE, ctx))
            w = sum(t.col_widths[c.col:c.col + c.colspan])
            h = sum(t.row_heights[c.row:c.row + c.rowspan])
            tcs += tc_xml(p_xml(cell, ctx), c.col, c.row, w, h, I.BF_TABLE,
                          margin=(L.CELL_PAD_X, L.CELL_PAD_X, L.CELL_PAD_Y, L.CELL_PAD_Y),
                          colspan=c.colspan, rowspan=c.rowspan, header=(t.header and r == 0))
        trs.append(tcs)
    tb = tbl_xml(trs, len(t.row_heights), t.ncols, L.DATA_TABLE_W, sum(t.row_heights), ctx, bf=I.BF_TABLE,
                 page_break="CELL")
    out = []
    first = colpr
    if t.title:
        out.append(p_xml(Para(I.PS_TABLE_TITLE, I.ST_TABLE, runs(t.title, I.CS_TABLE, ctx)), ctx, colpr=first))
        first = False
    if t.unit:
        out.append(p_xml(Para(I.PS_TABLE_UNIT, I.ST_TABLE_UNIT, runs(t.unit, I.CS_TABLE, ctx)), ctx, colpr=first))
        first = False
    out.append(holder(I.PS_TABLE_PARA, I.ST_BOXITEM, I.CS_BODY, (COLPR if first else "") + tb))
    if t.note:
        out.append(p_xml(Para(I.PS_TABLE_NOTE, I.ST_BOXITEM, runs(t.note, I.CS_BODY, ctx)), ctx))
    return "".join(out)


def passage_box_xml(plan, ctx, pic_skeleton):
    cell = tc_xml(paras_xml(plan, ctx, pic_skeleton), 0, 0, L.PASSAGE_W, 11.0, I.BF_PASSAGE)
    t = tbl_xml([cell], 1, 1, L.PASSAGE_W, 26.58, ctx, in_margin=(0, 0, 8.5, 7.08), bf=7)
    return holder(I.PS_BOX, I.ST_BOX, I.CS_BOX, t)


def bogi_box_xml(paras, ctx, pic_skeleton):
    """<보기> 상자: 3×3 표. 1행 가운데 칸(2행까지 합침)에 제목, 양옆 칸 아랫선이 위 테두리."""
    side, mid = 131.81, 44.48
    tiny = lambda ps: p_xml(Para(ps, I.ST_NORMAL, [(I.CS_BOGI_TINY, [])]), ctx)
    title = p_xml(Para(I.PS_BOGI_TITLE, I.ST_NORMAL, [(I.CS_BOGI_TITLE, [("t", "<보 기>")])]), ctx)
    r0 = (tc_xml(tiny(I.PS_BOGI_EMPTY), 0, 0, side, 6.8, I.BF_BOGI_TOPSIDE)
          + tc_xml(title, 1, 0, mid, 12.12, I.BF_BOGI_TITLE, margin=(1.41,) * 4, rowspan=2, valign="TOP",
                   has_margin=False)
          + tc_xml(tiny(I.PS_BLANK), 2, 0, side, 6.8, I.BF_BOGI_TOPSIDE))
    r1 = (tc_xml(tiny(I.PS_BLANK), 0, 1, side, 5.32, I.BF_BOGI_L)
          + tc_xml(tiny(I.PS_BLANK), 2, 1, side, 5.32, I.BF_BOGI_R))
    r2 = tc_xml(paras_xml(paras, ctx, pic_skeleton), 0, 2, L.BOGI_W, 11.0, I.BF_BOGI_BODY,
                margin=(0, 0, 8.5, 7.08), colspan=3)
    t = tbl_xml([r0, r1, r2], 3, 3, 308.10, 81.02, ctx, bf=7)
    return holder(I.PS_BOX, I.ST_BOX, I.CS_BOX, t)


MARKS = "①②③④⑤"


def picture_choices_xml(figs, layout, ctx, pic_skeleton):
    """그림 선지 표(선 없음). 2열: ①② / ③④ / ⑤ (양식 견본과 같은 5열 표: 번호·그림·틈·번호·그림), 1열: 번호·그림."""
    cols = L.PIC2_COLS if layout == "그림 2열" else L.PIC1_COLS
    per = 2 if layout == "그림 2열" else 1
    groups = [figs[i:i + per] for i in range(0, len(figs), per)]
    mark_p = lambda k: p_xml(Para(I.PS_PIC_CELL, I.ST_PIC_CELL, [(I.CS_CHOICE, [("t", MARKS[k]), ("nb",)])]), ctx)
    empty_p = lambda: p_xml(Para(I.PS_PIC_CELL, I.ST_PIC_CELL, [(I.CS_CHOICE, [])]), ctx)
    rows, heights = [], []
    k = 0
    for gi, g in enumerate(groups):
        if gi:
            tcs = "".join(tc_xml(empty_p(), c, len(rows), cols[c], L.PIC_GAP_ROW, I.BF_CELL_NONE, valign="TOP")
                          for c in range(len(cols)))
            rows.append(tcs)
            heights.append(L.PIC_GAP_ROW)
        h = max(f.height_pt for f in g) + 2 * L.PIC_PAD_Y
        tcs, c = "", 0
        for j in range(per):
            if j:
                tcs += tc_xml(empty_p(), c, len(rows), cols[c], h, I.BF_CELL_NONE, valign="TOP")
                c += 1
            if j < len(g):
                tcs += tc_xml(mark_p(k), c, len(rows), cols[c], h, I.BF_CELL_NONE, valign="TOP")
                pic = holder(I.PS_PIC_CELL, I.ST_PIC_CELL, I.CS_CHOICE, pic_xml(pic_skeleton, g[j], ctx))
                tcs += tc_xml(pic, c + 1, len(rows), cols[c + 1], h, I.BF_CELL_NONE,
                              margin=(0, 0, L.PIC_PAD_Y, L.PIC_PAD_Y), valign="TOP")
                k += 1
            else:
                tcs += tc_xml(empty_p(), c, len(rows), cols[c], h, I.BF_CELL_NONE, valign="TOP")
                tcs += tc_xml(empty_p(), c + 1, len(rows), cols[c + 1], h, I.BF_CELL_NONE, valign="TOP")
            c += 2
        rows.append(tcs)
        heights.append(h)
    t = tbl_xml(rows, len(rows), len(cols), sum(cols), sum(heights), ctx, bf=I.BF_TABLE)
    return holder(I.PS_PIC_TABLE, I.ST_NORMAL, I.CS_PIC_TABLE, t), sum(heights)


def item_xml(number, plan, ctx, first, pic_skeleton):
    xml = [p_xml(plan["stem"], ctx, column_break=not first, pid="0")]
    xml.append(passage_box_xml(plan["passage"], ctx, pic_skeleton))
    if plan["bogi"]:
        xml.append(bogi_box_xml(plan["bogi"], ctx, pic_skeleton))
    xml.extend(p_xml(c, ctx) for c in plan["choices"])
    if plan["choice_figs"]:
        xml.append(picture_choices_xml(plan["choice_figs"], plan["layout"], ctx, pic_skeleton)[0])
    return "".join(xml)


def picture_choices_height(figs, layout):
    per = 2 if layout == "그림 2열" else 1
    groups = [figs[i:i + per] for i in range(0, len(figs), per)]
    return sum(max(f.height_pt for f in g) + 2 * L.PIC_PAD_Y for g in groups) + L.PIC_GAP_ROW * (len(groups) - 1)
