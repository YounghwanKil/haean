# -*- coding: utf-8 -*-
"""표 XML 을 칸 단위로 다루기(칸 안에 표가 든 표도). 양식 견본 표를 복제해 칸만 바꿀 때 쓴다."""
import re


def _scan(xml, tag):
    """xml 안 tag 요소들의 (깊이, 시작, 끝)."""
    out, stack = [], []
    for m in re.finditer(r"<%s\b|</%s>" % (tag, tag), xml):
        if m.group(0).startswith("</"):
            s = stack.pop()
            out.append((len(stack), s, m.end()))
        else:
            stack.append(m.start())
    return out


def outer_table(xml):
    """xml 안 첫 번째 가장 바깥 <hp:tbl> 의 (시작, 끝). 없으면 None."""
    tb = [x for x in _scan(xml, "hp:tbl") if x[0] == 0]
    if not tb:
        return None
    tb.sort(key=lambda x: x[1])
    return tb[0][1], tb[0][2]


def top_cells(tbl):
    """표 XML(바깥 <hp:tbl>…</hp:tbl>) → {(행, 열): (시작, 끝)} 바깥 표의 칸만."""
    inner_start = tbl.index(">") + 1
    body = tbl[inner_start:]
    out = {}
    for depth, a, b in _scan(body, "hp:tc"):
        if depth != 0:
            continue
        tc = body[a:b]
        # 이 칸의 주소는 칸 끝 쪽(안쪽 표 뒤)에 있다: 마지막 cellAddr
        addr = re.findall(r'<hp:cellAddr colAddr="(\d+)" rowAddr="(\d+)"/>', tc)[-1]
        out[(int(addr[1]), int(addr[0]))] = (inner_start + a, inner_start + b)
    return out


def cell_info(tc):
    """칸 XML → dict(width, height, margin=(l,r,t,b) pt, has_margin, span=(cols, rows), bf)."""
    tail = tc[tc.rindex("</hp:subList>"):]
    w, h = re.search(r'<hp:cellSz width="(\d+)" height="(\d+)"/>', tail).groups()
    mg = re.search(r'<hp:cellMargin left="(\d+)" right="(\d+)" top="(\d+)" bottom="(\d+)"/>', tail)
    sp = re.search(r'<hp:cellSpan colSpan="(\d+)" rowSpan="(\d+)"/>', tail)
    head = re.match(r"<hp:tc [^>]*>", tc).group(0)
    return {"width": int(w) / 100.0, "height": int(h) / 100.0,
            "margin": tuple(int(x) / 100.0 for x in mg.groups()) if mg else (0, 0, 0, 0),
            "has_margin": 'hasMargin="1"' in head,
            "span": (int(sp.group(1)), int(sp.group(2))) if sp else (1, 1),
            "bf": int(re.search(r'borderFillIDRef="(\d+)"', head).group(1))}


def table_info(tbl):
    head = re.match(r"<hp:tbl [^>]*>", tbl).group(0)
    sz = re.search(r'<hp:sz width="(\d+)" widthRelTo="\w+" height="(\d+)"', tbl)
    om = re.search(r'<hp:outMargin left="(\d+)" right="(\d+)" top="(\d+)" bottom="(\d+)"/>', tbl)
    im = re.search(r'<hp:inMargin left="(\d+)" right="(\d+)" top="(\d+)" bottom="(\d+)"/>', tbl)
    return {"width": int(sz.group(1)) / 100.0, "height": int(sz.group(2)) / 100.0,
            "out": tuple(int(x) / 100.0 for x in om.groups()) if om else (0, 0, 0, 0),
            "in": tuple(int(x) / 100.0 for x in im.groups()) if im else (0, 0, 0, 0),
            "rows": int(re.search(r'rowCnt="(\d+)"', head).group(1)),
            "cols": int(re.search(r'colCnt="(\d+)"', head).group(1))}


def cell_margin(tbl, tc):
    """칸에 적용되는 여백: 칸 자체 여백(hasMargin=1) 또는 표 안 여백."""
    ci = cell_info(tc)
    return ci["margin"] if ci["has_margin"] else table_info(tbl)["in"]


def replace_cell_content(tbl, rc, paras_xml):
    a, b = top_cells(tbl)[rc]
    tc = tbl[a:b]
    i = tc.index(">", tc.index("<hp:subList")) + 1
    j = tc.rindex("</hp:subList>")
    return tbl[:a] + tc[:i] + paras_xml + tc[j:] + tbl[b:]


def set_cell_size(tbl, rc, width=None, height=None):
    a, b = top_cells(tbl)[rc]
    tc = tbl[a:b]
    j = tc.rindex("</hp:subList>")
    tail = tc[j:]
    if width is not None:
        tail = re.sub(r'(<hp:cellSz width=")\d+(")', lambda m: "%s%d%s" % (m.group(1), int(round(width * 100)), m.group(2)), tail, count=1)
    if height is not None:
        tail = re.sub(r'(<hp:cellSz width="\d+" height=")\d+(")', lambda m: "%s%d%s" % (m.group(1), int(round(height * 100)), m.group(2)), tail, count=1)
    return tbl[:a] + tc[:j] + tail + tbl[b:]


def set_cell_margin(tbl, rc, left=None, right=None, top=None, bottom=None):
    """칸 여백(pt)을 바꾸고 hasMargin=1 로 둔다(표 안 여백 대신 칸 여백이 쓰이게)."""
    a, b = top_cells(tbl)[rc]
    tc = tbl[a:b]
    j = tc.rindex("</hp:subList>")
    head, tail = tc[:j], tc[j:]
    cur = re.search(r'<hp:cellMargin left="(\d+)" right="(\d+)" top="(\d+)" bottom="(\d+)"/>', tail)
    vals = [int(x) for x in cur.groups()] if cur else [0, 0, 0, 0]
    for k, v in enumerate((left, right, top, bottom)):
        if v is not None:
            vals[k] = int(round(v * 100))
    new = '<hp:cellMargin left="%d" right="%d" top="%d" bottom="%d"/>' % tuple(vals)
    tail = tail.replace(cur.group(0), new, 1) if cur else tail.replace("</hp:tc>", new + "</hp:tc>", 1)
    head = re.sub(r'(<hp:tc [^>]*hasMargin=")0(")', r"\g<1>1\2", head, count=1)
    return tbl[:a] + head + tail + tbl[b:]


def set_table_size(tbl, width=None, height=None):
    head_end = tbl.index("<hp:tr>") if "<hp:tr>" in tbl else len(tbl)
    head = tbl[:head_end]
    if width is not None:
        head = re.sub(r'(<hp:sz width=")\d+(")', lambda m: "%s%d%s" % (m.group(1), int(round(width * 100)), m.group(2)), head, count=1)
    if height is not None:
        head = re.sub(r'(<hp:sz width="\d+" widthRelTo="\w+" height=")\d+(")', lambda m: "%s%d%s" % (m.group(1), int(round(height * 100)), m.group(2)), head, count=1)
    return head + tbl[head_end:]
