# -*- coding: utf-8 -*-
"""양식 header.xml 읽기: 문단 모양·글자 모양·글꼴 → pt 값.

문단 여백(hc:left·right·intent·prev·next)은 한글이 HWPUNIT 의 두 배로 저장하므로 200 으로 나눈다
(문단 모양 대화상자 값 = 저장 값 / 200 pt). 글자 크기(height)는 100 으로 나눈다.
"""
import re
from dataclasses import dataclass


@dataclass
class ParaShape:
    id: int
    align: str
    ls_type: str
    ls_value: int
    left: float
    right: float
    indent: float      # 음수면 내어쓰기(둘째 줄부터 |indent| 만큼 들어감), 양수면 들여쓰기(첫 줄만)
    prev: float
    next: float
    border_fill: int
    tab_pr: int
    condense: int = 0     # 공백 최소값(%): 양쪽 맞춤 때 빈칸을 이만큼까지 줄일 수 있다

    def pitch(self, font_pt):
        """줄 간격(pt). PERCENT 는 글자 크기 × 비율, FIXED/BETWEEN_LINES 는 값/100."""
        if self.ls_type == "PERCENT":
            return font_pt * self.ls_value / 100.0
        if self.ls_type == "FIXED":
            return self.ls_value / 100.0
        return font_pt + self.ls_value / 100.0

    def offsets(self):
        """(첫 줄 시작, 둘째 줄부터 시작) — 문단 왼쪽 여백 기준 pt."""
        if self.indent >= 0:
            return self.left + self.indent, self.left
        return self.left, self.left - self.indent


@dataclass
class CharShape:
    id: int
    pt: float
    font: str
    ratio: int
    spacing: int
    bold: bool
    underline: bool


class Header:
    def __init__(self, xml):
        self.xml = xml
        self.fonts = {}
        for fl in re.finditer(r'<hh:fontface lang="(\w+)"[^>]*>(.*?)</hh:fontface>', xml, re.S):
            self.fonts[fl.group(1)] = {int(m.group(1)): m.group(2)
                                       for m in re.finditer(r'<hh:font id="(\d+)" face="([^"]*)"', fl.group(2))}
        self.para = {}
        for m in re.finditer(r'<hh:paraPr id="(\d+)"([^>]*)>(.*?)</hh:paraPr>', xml, re.S):
            attrs, b = m.group(2), m.group(3)
            b1 = b.split("<hp:default>")[-1] if "<hp:switch>" in b else b

            def v(k, src=b1):
                mm = re.search(r'<hc:%s value="(-?\d+)"' % k, src)
                return int(mm.group(1)) / 200.0 if mm else 0.0

            ls = re.search(r'<hh:lineSpacing type="(\w+)" value="(-?\d+)"', b1)
            bd = re.search(r'<hh:border borderFillIDRef="(\d+)"', b)
            tp = re.search(r'tabPrIDRef="(\d+)"', attrs)
            cd = re.search(r'condense="(\d+)"', attrs)
            self.para[int(m.group(1))] = ParaShape(
                int(m.group(1)), re.search(r'<hh:align horizontal="(\w+)"', b).group(1),
                ls.group(1) if ls else "PERCENT", int(ls.group(2)) if ls else 160,
                v("left"), v("right"), v("intent"), v("prev"), v("next"),
                int(bd.group(1)) if bd else 0, int(tp.group(1)) if tp else 0, int(cd.group(1)) if cd else 0)
        self.char = {}
        for m in re.finditer(r'<hh:charPr id="(\d+)" height="(\d+)"[^>]*?(?:/>|>(.*?)</hh:charPr>)', xml, re.S):
            b = m.group(3) or ""
            fr = re.search(r'<hh:fontRef hangul="(\d+)"', b)
            ra = re.search(r'<hh:ratio hangul="(\d+)"', b)
            sp = re.search(r'<hh:spacing hangul="(-?\d+)"', b)
            self.char[int(m.group(1))] = CharShape(
                int(m.group(1)), int(m.group(2)) / 100.0,
                self.fonts.get("HANGUL", {}).get(int(fr.group(1)), "") if fr else "",
                int(ra.group(1)) if ra else 100, int(sp.group(1)) if sp else 0,
                "<hh:bold/>" in b, bool(re.search(r'<hh:underline type="(?!NONE)', b)))
        self.styles = {}
        for m in re.finditer(r'<hh:style id="(\d+)" type="(\w+)" name="([^"]*)"[^>]*paraPrIDRef="(\d+)"'
                             r' charPrIDRef="(\d+)"', xml):
            self.styles[int(m.group(1))] = (m.group(3), int(m.group(4)), int(m.group(5)))
        self.border_fills = {int(m.group(1)) for m in re.finditer(r'<hh:borderFill id="(\d+)"', xml)}

    def pitch(self, ps, cs):
        return self.para[ps].pitch(self.char[cs].pt)

    def missing(self, ps=(), cs=(), st=(), bf=()):
        """없는 ID 목록(양식 확인용)."""
        out = ["paraPr %d" % i for i in ps if i not in self.para]
        out += ["charPr %d" % i for i in cs if i not in self.char]
        out += ["style %d" % i for i in st if i not in self.styles]
        out += ["borderFill %d" % i for i in bf if i not in self.border_fills]
        return out
