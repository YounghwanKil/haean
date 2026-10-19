# -*- coding: utf-8 -*-
"""양식 header 에 모양 변형 찾기/만들기.

- 글자 모양 변형(밑줄·굵게·기울임·위첨자·아래첨자): 양식마다 '본문 글자 모양 + 밑줄' 같은 변형이 있을 수도 없을 수도
  있다. 같은 모양이 header 에 있으면 그 ID를, 없으면 기준 글자 모양을 복사해 속성만 바꾼 새 charPr 를 붙인다.
- 문단 모양 변형(내어쓰기·여백): 라벨 폭에 맞춘 내어쓰기 등. 같은 방식으로 paraPr 를 복사해 붙인다.
새 항목은 목록 끝에 붙이고 itemCnt 를 갱신한다. 기존 ID 는 바뀌지 않는다.
"""
import re

FLAGS = ("u", "b", "i", "sup", "sub")


def _body(xml):
    """비교용: id 를 뺀 charPr 본문."""
    return re.sub(r'^<hh:charPr id="\d+"', "<hh:charPr", xml)


def _apply(xml, flag):
    if flag == "u":
        xml = re.sub(r'<hh:underline type="\w+"', '<hh:underline type="BOTTOM"', xml)
    elif flag == "b":
        if "<hh:bold/>" not in xml:
            xml = xml.replace("<hh:underline", "<hh:bold/><hh:underline", 1)
    elif flag == "i":
        if "<hh:italic/>" not in xml:
            xml = xml.replace("<hh:underline", "<hh:italic/><hh:underline", 1)
    elif flag in ("sup", "sub"):
        xml = xml.replace("<hh:supscript/>", "").replace("<hh:subscript/>", "")
        tag = "<hh:supscript/>" if flag == "sup" else "<hh:subscript/>"
        xml = xml.replace("</hh:charPr>", tag + "</hh:charPr>")
    return xml


class HeaderEditor:
    def __init__(self, header_xml):
        self.header = header_xml
        self.added = 0
        self._cache = {}

    def _all(self):
        return {int(m.group(1)): m.group(0)
                for m in re.finditer(r'<hh:charPr id="(\d+)".*?</hh:charPr>', self.header, re.S)}

    def variant(self, base, flag):
        key = (base, flag)
        if key in self._cache:
            return self._cache[key]
        allc = self._all()
        if base not in allc:
            return base
        want = _apply(allc[base], flag)
        wb = _body(want)
        for i, x in allc.items():
            if _body(x) == wb:
                self._cache[key] = i
                return i
        new_id = max(allc) + 1
        new = re.sub(r'^<hh:charPr id="\d+"', '<hh:charPr id="%d"' % new_id, want)
        self.header = self.header.replace("</hh:charProperties>", new + "</hh:charProperties>", 1)
        self.header = re.sub(r'<hh:charProperties itemCnt="(\d+)"',
                             lambda m: '<hh:charProperties itemCnt="%d"' % (int(m.group(1)) + 1), self.header, count=1)
        self.added += 1
        self._cache[key] = new_id
        return new_id

    def spacing_variant(self, base, delta):
        """글자 모양 base 에 자간(모든 글자 종류) delta(%)를 더한 것. 0 이면 base 그대로."""
        if not delta:
            return base
        key = ("sp", base, int(delta))
        if key in self._cache:
            return self._cache[key]
        allc = self._all()
        if base not in allc:
            return base
        want = re.sub(r'(<hh:spacing [^>]*/>)',
                      lambda m: re.sub(r'="(-?\d+)"', lambda v: '="%d"' % (int(v.group(1)) + int(delta)), m.group(1)),
                      allc[base], count=1)
        wb = _body(want)
        for i, x in allc.items():
            if _body(x) == wb:
                self._cache[key] = i
                return i
        new_id = max(allc) + 1
        new = re.sub(r'^<hh:charPr id="\d+"', '<hh:charPr id="%d"' % new_id, want)
        self.header = self.header.replace("</hh:charProperties>", new + "</hh:charProperties>", 1)
        self.header = re.sub(r'<hh:charProperties itemCnt="(\d+)"',
                             lambda m: '<hh:charProperties itemCnt="%d"' % (int(m.group(1)) + 1), self.header, count=1)
        self.added += 1
        self._cache[key] = new_id
        return new_id

    def style_map(self, base):
        """inline.runs 용 {표기: 글자 모양 ID}."""
        return {f: self.variant(base, f) for f in FLAGS}

    # ── 문단 모양
    def _paras(self):
        return {int(m.group(1)): m.group(0)
                for m in re.finditer(r'<hh:paraPr id="(\d+)".*?</hh:paraPr>', self.header, re.S)}

    def para_variant(self, base, indent=None, left=None, right=None, prev=None, next=None, align=None):
        """문단 모양 base 를 복사해 여백(pt)·정렬만 바꾼 것. hp:case(HWPUNIT) 와 hp:default(2배) 를 함께 고친다."""
        changes = {k: v for k, v in (("intent", indent), ("left", left), ("right", right), ("prev", prev),
                                     ("next", next)) if v is not None}
        key = ("p", base, align) + tuple(sorted((k, round(v, 2)) for k, v in changes.items()))
        if key in self._cache:
            return self._cache[key]
        allp = self._paras()
        if base not in allp or not (changes or align):
            return base
        x = allp[base]
        if align:
            x = re.sub(r'<hh:align horizontal="\w+"', '<hh:align horizontal="%s"' % align, x, count=1)

        def setv(block, factor):
            for k, v in changes.items():
                block = re.sub(r'(<hc:%s value=")-?\d+(")' % k,
                               lambda m: "%s%d%s" % (m.group(1), int(round(v * factor)), m.group(2)), block, count=1)
            return block

        if "<hp:switch>" in x:
            x = re.sub(r"<hp:case\b.*?</hp:case>", lambda m: setv(m.group(0), 100), x, flags=re.S)
            x = re.sub(r"<hp:default>.*?</hp:default>", lambda m: setv(m.group(0), 200), x, flags=re.S)
        else:
            x = setv(x, 200)
        body = re.sub(r'^<hh:paraPr id="\d+"', "<hh:paraPr", x)
        for i, y in allp.items():
            if re.sub(r'^<hh:paraPr id="\d+"', "<hh:paraPr", y) == body:
                self._cache[key] = i
                return i
        new_id = max(allp) + 1
        new = '<hh:paraPr id="%d"' % new_id + body[len("<hh:paraPr"):]
        self.header = self.header.replace("</hh:paraProperties>", new + "</hh:paraProperties>", 1)
        self.header = re.sub(r'<hh:paraProperties itemCnt="(\d+)"',
                             lambda m: '<hh:paraProperties itemCnt="%d"' % (int(m.group(1)) + 1), self.header, count=1)
        self.added += 1
        self._cache[key] = new_id
        return new_id

    # ── 테두리/배경
    def border_fill(self, base, keep=()):
        """borderFill base 를 복사해 keep 에 든 변(left·right·top·bottom)만 남기고 나머지 선을 없앤 것."""
        key = ("bf", base, tuple(sorted(keep)))
        if key in self._cache:
            return self._cache[key]
        allb = {int(m.group(1)): m.group(0)
                for m in re.finditer(r'<hh:borderFill id="(\d+)".*?</hh:borderFill>', self.header, re.S)}
        if base not in allb:
            return base
        x = allb[base]
        for side in ("left", "right", "top", "bottom"):
            if side not in keep:
                x = re.sub(r'<hh:%sBorder type="\w+"' % side, '<hh:%sBorder type="NONE"' % side, x, count=1)
        x = re.sub(r'<hh:diagonal type="\w+"', '<hh:diagonal type="NONE"', x)
        body = re.sub(r'^<hh:borderFill id="\d+"', "<hh:borderFill", x)
        for i, y in allb.items():
            if re.sub(r'^<hh:borderFill id="\d+"', "<hh:borderFill", y) == body:
                self._cache[key] = i
                return i
        new_id = max(allb) + 1
        new = '<hh:borderFill id="%d"' % new_id + body[len("<hh:borderFill"):]
        self.header = self.header.replace("</hh:borderFills>", new + "</hh:borderFills>", 1)
        self.header = re.sub(r'<hh:borderFills itemCnt="(\d+)"',
                             lambda m: '<hh:borderFills itemCnt="%d"' % (int(m.group(1)) + 1), self.header, count=1)
        self.added += 1
        self._cache[key] = new_id
        return new_id
