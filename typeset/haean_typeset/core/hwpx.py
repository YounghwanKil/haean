# -*- coding: utf-8 -*-
"""hwpx(OWPML) 조각을 쓰는 범용 함수. 양식 번호·pt 상수는 인자로 받는다."""
import re
import zipfile

COLPR = ('<hp:ctrl><hp:colPr id="" type="NEWSPAPER" layout="LEFT" colCount="1" sameSz="1" sameGap="0"/>'
         '</hp:ctrl>')
INLINE_POS = ('<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0"'
              ' vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>')


def hu(pt):
    return int(round(pt * 100))


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── 글
def eq_xml(script, ctx):
    vis = len(script.replace(" ", "")) or 1
    w, h, base = max(500, 520 * vis), 1100, 85
    if " over " in script:
        h, base = 2400, 68
    return ('<hp:equation id="%d" zOrder="0" numberingType="EQUATION" textWrap="TOP_AND_BOTTOM"'
            ' textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" version="Equation Version 60"'
            ' baseLine="%d" textColor="#000000" baseUnit="%d" lineMode="CHAR" font="HYhwpEQ">'
            '<hp:sz width="%d" widthRelTo="ABSOLUTE" height="%d" heightRelTo="ABSOLUTE" protect="0"/>'
            '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0"'
            ' vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
            '<hp:outMargin left="56" right="56" top="0" bottom="0"/>'
            '<hp:shapeComment>수식입니다.</hp:shapeComment><hp:script>%s</hp:script></hp:equation>'
            % (ctx.nid(), base, ctx.eq_base, w, h, esc(script)))


def run_xml(cs, pieces, ctx):
    out, text = [], []
    t_open = '<hp:t charStyleIDRef="%d">' % ctx.char_style[cs] if cs in ctx.char_style else "<hp:t>"

    def flush():
        if text:
            out.append(t_open + "".join(text) + "</hp:t>")
            text.clear()

    for p in pieces:
        k = p[0]
        if k == "t":
            text.append(esc(p[1]))
        elif k == "nb":
            text.append("<hp:nbSpace/>")
        elif k == "fw":
            text.append("<hp:fwSpace/>")
        elif k == "tab":
            text.append('<hp:tab width="1000" leader="0" type="1"/>')
        elif k == "br":
            text.append("<hp:lineBreak/>")
        elif k == "eq":
            flush()
            out.append(eq_xml(p[1], ctx))
        elif k == "raw":
            flush()
            out.append(p[1])
    flush()
    if not out:
        return '<hp:run charPrIDRef="%d"/>' % cs
    return '<hp:run charPrIDRef="%d">%s</hp:run>' % (cs, "".join(out))


def p_xml(para, ctx, column_break=False, colpr=False, pid="2147483648", page_break=False):
    body = "".join(run_xml(cs, pcs, ctx) for cs, pcs in para.runs)
    if colpr:
        body = '<hp:run charPrIDRef="%d">%s</hp:run>' % (para.runs[0][0], COLPR) + body
    return ('<hp:p id="%s" paraPrIDRef="%d" styleIDRef="%d" pageBreak="%d" columnBreak="%d" merged="0">%s</hp:p>'
            % (pid, para.ps, para.st, int(page_break), int(column_break), body))


# ── 표
def tc_xml(inner, col, row, w, h, bf, margin=None, colspan=1, rowspan=1, valign="CENTER", has_margin=None,
           header=False):
    m = margin or (0, 0, 0, 0)
    if has_margin is None:
        has_margin = margin is not None
    return ('<hp:tc name="" header="%d" hasMargin="%d" protect="0" editable="0" dirty="0" borderFillIDRef="%d">'
            '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="%s" linkListIDRef="0"'
            ' linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">%s</hp:subList>'
            '<hp:cellAddr colAddr="%d" rowAddr="%d"/><hp:cellSpan colSpan="%d" rowSpan="%d"/>'
            '<hp:cellSz width="%d" height="%d"/>'
            '<hp:cellMargin left="%d" right="%d" top="%d" bottom="%d"/></hp:tc>'
            % (int(header), int(has_margin), bf, valign, inner, col, row, colspan, rowspan, hu(w), hu(h),
               *[hu(x) for x in m]))


def tbl_xml(rows, nrows, ncols, w, h, ctx, in_margin=(0, 0, 0, 0), bf=1, page_break="NONE", pos=INLINE_POS):
    return ('<hp:tbl id="%d" zOrder="1" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES"'
            ' lock="0" dropcapstyle="None" pageBreak="%s" repeatHeader="1" rowCnt="%d" colCnt="%d"'
            ' cellSpacing="0" borderFillIDRef="%d" noAdjust="0">'
            '<hp:sz width="%d" widthRelTo="ABSOLUTE" height="%d" heightRelTo="ABSOLUTE" protect="0"/>%s'
            '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
            '<hp:inMargin left="%d" right="%d" top="%d" bottom="%d"/>%s</hp:tbl>'
            % (ctx.nid(), page_break, nrows, ncols, bf, hu(w), hu(h), pos, *[hu(x) for x in in_margin],
               "".join("<hp:tr>%s</hp:tr>" % r for r in rows)))


def holder(ps, st, cs, inner, pid="2147483648"):
    """개체 하나를 글자처럼 담은 문단."""
    return ('<hp:p id="%s" paraPrIDRef="%d" styleIDRef="%d" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="%d">%s<hp:t/></hp:run></hp:p>' % (pid, ps, st, cs, inner))


# ── 그림
def pic_xml(skeleton, fig, ctx):
    """양식의 <hp:pic> 뼈대에서 그림 참조·크기만 바꾼다(글자처럼 놓기 유지).
    imgDim 은 96dpi 기준 원본 크기(px × 75 HWPUNIT), 놓을 크기는 orgSz·curSz·sz·imgRect."""
    w, h = hu(fig.width_pt), hu(fig.height_pt)
    dw, dh = fig.px[0] * 75, fig.px[1] * 75
    x = skeleton
    x = re.sub(r'(<hp:pic id=")\d+(")', lambda m: "%s%d%s" % (m.group(1), ctx.nid(), m.group(2)), x, count=1)
    x = re.sub(r'(instid=")\d+(")', lambda m: "%s%d%s" % (m.group(1), ctx.inst_id(), m.group(2)), x, count=1)
    x = re.sub(r'binaryItemIDRef="[^"]*"', 'binaryItemIDRef="%s"' % fig.bin_id, x, count=1)
    x = re.sub(r'<hp:orgSz [^>]*/>', '<hp:orgSz width="%d" height="%d"/>' % (w, h), x, count=1)
    x = re.sub(r'<hp:curSz [^>]*/>', '<hp:curSz width="%d" height="%d"/>' % (w, h), x, count=1)
    x = re.sub(r'<hp:rotationInfo angle="0" centerX="\d+" centerY="\d+"',
               '<hp:rotationInfo angle="0" centerX="%d" centerY="%d"' % (w // 2, h // 2), x, count=1)
    x = re.sub(r'<hc:scaMatrix [^>]*/>', '<hc:scaMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>', x, count=1)
    x = re.sub(r'<hp:imgRect>.*?</hp:imgRect>',
               '<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="%d" y="0"/><hc:pt2 x="%d" y="%d"/><hc:pt3 x="0" y="%d"/>'
               '</hp:imgRect>' % (w, w, h, h), x, count=1, flags=re.S)
    x = re.sub(r'<hp:imgClip [^>]*/>', '<hp:imgClip left="0" right="%d" top="0" bottom="%d"/>' % (dw, dh), x, count=1)
    x = re.sub(r'<hp:imgDim [^>]*/>', '<hp:imgDim dimwidth="%d" dimheight="%d"/>' % (dw, dh), x, count=1)
    x = re.sub(r'<hp:sz width="\d+" widthRelTo="ABSOLUTE" height="\d+"',
               '<hp:sz width="%d" widthRelTo="ABSOLUTE" height="%d"' % (w, h), x, count=1)
    x = re.sub(r'<hp:shapeComment>.*?</hp:shapeComment>',
               '<hp:shapeComment>그림입니다.\n원본 그림의 이름: %s\n원본 그림의 크기: 가로 %dpixel, 세로 %dpixel'
               '</hp:shapeComment>' % (esc(fig.path.replace("\\", "/").split("/")[-1]), fig.px[0], fig.px[1]),
               x, count=1, flags=re.S)
    return x


# ── 양식 다루기
def top_paragraphs(sec):
    """구역 바로 아래 문단들의 (시작, 끝). 표 안 문단은 건너뛴다."""
    tops, depth, start = [], 0, None
    for m in re.finditer(r"<hp:p\b|</hp:p>", sec):
        if m.group(0) == "<hp:p":
            if depth == 0:
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                tops.append((start, m.end()))
    return tops


def find_element(xml, tag, needle):
    """needle 글을 품은 가장 바깥 <tag>…</tag> 의 (시작, 끝)."""
    depth, start = 0, None
    for m in re.finditer(r"<%s\b|</%s>" % (tag, tag), xml):
        if not m.group(0).startswith("</"):
            if depth == 0:
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0 and needle in re.sub(r"<[^>]+>", "", xml[start:m.end()]):
                return start, m.end()
    return None


def first_element(xml, tag):
    a = xml.index("<%s " % tag)
    depth = 0
    for m in re.finditer(r"<%s\b|</%s>" % (tag, tag), xml[a:]):
        depth += 1 if not m.group(0).startswith("</") else -1
        if depth == 0:
            return a, a + m.end()
    raise ValueError("%s 가 닫히지 않았습니다" % tag)


def drop_linesegs(xml):
    """줄 배치 정보 삭제. 글을 바꾼 문단에 옛 정보가 남으면 한글이 문서 변조로 본다."""
    return re.sub(r"<hp:linesegarray>.*?</hp:linesegarray>", "", xml, flags=re.S)


def strip_memos(xml):
    """메모 필드를 지우고 메모가 달렸던 글은 남긴다."""
    ids = re.findall(r'<hp:fieldBegin id="(\d+)" type="MEMO"', xml)
    xml = re.sub(r'<hp:ctrl><hp:fieldBegin [^>]*type="MEMO".*?</hp:fieldBegin></hp:ctrl>', '', xml, flags=re.S)
    for i in ids:
        xml = re.sub(r'<hp:ctrl><hp:fieldEnd beginIDRef="%s"[^>]*/></hp:ctrl>' % i, '', xml)
    return xml.replace("</hp:t><hp:t>", "")


OBJ_ID = re.compile(r'(<hp:(?:tbl|rect|pic|equation|line|ellipse|container|arc|polygon|curve) id=")(\d+)(")')
INST_ID = re.compile(r'(instid=")(\d+)(")')


def fresh_ids(xml, ctx):
    """복제한 개체에 새 ID를 매긴다."""
    xml = OBJ_ID.sub(lambda m: "%s%d%s" % (m.group(1), ctx.nid(), m.group(3)), xml)
    return INST_ID.sub(lambda m: "%s%d%s" % (m.group(1), ctx.inst_id(), m.group(3)), xml)


def cells(tbl):
    """표 XML → {(행, 열): (시작, 끝)} (칸 안에 표가 없는 표만)."""
    out = {}
    for m in re.finditer(r"<hp:tc .*?</hp:tc>", tbl, re.S):
        c, r = re.search(r'cellAddr colAddr="(\d+)" rowAddr="(\d+)"', m.group(0)).groups()
        out[(int(r), int(c))] = (m.start(), m.end())
    return out


def set_cell(tbl, rc, paras_xml):
    a, b = cells(tbl)[rc]
    tc = tbl[a:b]
    i, j = tc.index(">", tc.index("<hp:subList")) + 1, tc.index("</hp:subList>")
    return tbl[:a] + tc[:i] + paras_xml + tc[j:] + tbl[b:]


def cell_text(tbl, rc, text):
    """칸 첫 문단의 모양을 그대로 두고 글만 바꾼다."""
    a, b = cells(tbl)[rc]
    tc = tbl[a:b]
    p = re.search(r"<hp:p [^>]*>", tc).group(0)
    cs = re.search(r'<hp:run charPrIDRef="(\d+)"', tc).group(1)
    body = '<hp:run charPrIDRef="%s"><hp:t>%s</hp:t></hp:run>' % (cs, esc(text)) if text else \
        '<hp:run charPrIDRef="%s"/>' % cs
    return set_cell(tbl, rc, p + body + "</hp:p>")


def zinfo(info):
    """양식 zip 항목 정보의 사본. 원본 ZipInfo 로 writestr 하면 원본이 바뀐다."""
    ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    ni.compress_type = info.compress_type
    ni.external_attr = info.external_attr
    ni.create_system = info.create_system
    return ni


def replace_text_across(xml, old, new):
    """글 old 를 new 로 바꾼다. old 가 컨트롤(<hp:ctrl>) 등으로 여러 <hp:t> 에 나뉘어 있어도 된다.
    new 는 old 가 시작하는 조각에 넣고, 이어지는 조각에서는 old 부분을 지운다. → (새 xml, 바꾼 수)"""
    old_e, new_e = esc(old), esc(new)
    segs = [[m.start(1), m.end(1), m.group(1)] for m in re.finditer(r"<hp:t(?:\s[^>]*)?>([^<]*)</hp:t>", xml)]
    joined, owner = "", []
    for k, (a, b, t) in enumerate(segs):
        joined += t
        owner += [(k, j) for j in range(len(t))]
    hits, pos = [], joined.find(old_e)
    while pos >= 0:
        hits.append(pos)
        pos = joined.find(old_e, pos + len(old_e))
    hits = [p for p in hits if "</hp:p>" not in xml[segs[owner[p][0]][1]:segs[owner[p + len(old_e) - 1][0]][0]]]
    for pos in reversed(hits):
        (s0, o0), (s1, o1) = owner[pos], owner[pos + len(old_e) - 1]
        if s0 == s1:
            t = segs[s0][2]
            segs[s0][2] = t[:o0] + new_e + t[o1 + 1:]
        else:
            segs[s0][2] = segs[s0][2][:o0] + new_e
            for k in range(s0 + 1, s1):
                segs[k][2] = ""
            segs[s1][2] = segs[s1][2][o1 + 1:]
    if not hits:
        return xml, 0
    out, last = [], 0
    for a, b, t in segs:
        out.append(xml[last:a] + t)
        last = b
    out.append(xml[last:])
    return "".join(out), len(hits)
