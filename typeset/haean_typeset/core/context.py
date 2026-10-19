# -*- coding: utf-8 -*-
"""조판 1회 컨텍스트. 전역 상태 대신 이 객체를 넘긴다(같은 프로세스에서 여러 번 불러도 결과가 같게).

- 개체 ID·instid 카운터: 양식에 이미 있는 값보다 큰 수부터(한글은 ID가 겹치면 문서 변조로 본다)
- 모르는 LaTeX 명령 모음
- 글 안 꾸밈(<u> <b> <i> <sup> <sub>) → 글자 모양 ID 사상, 글자 모양 → 글자 스타일 ID 사상(프로필이 정함)
- 수식 기준 크기(HWPUNIT)
"""
import re


class Ctx:
    ID_START = 1900000000
    INST_START = 1000000000
    ID_CAP = 2000000000          # 이보다 큰 id(문단 id 2147483648 등)는 개체 ID로 보지 않는다

    def __init__(self, style_cs=None, char_style=None, eq_base=1100):
        self.style_cs = dict(style_cs or {})
        self.char_style = dict(char_style or {})
        self.eq_base = eq_base
        self.unknown_tex = []
        self.variants = None         # CharVariants: 기준 글자 모양별 꾸밈 변형(있으면 style_cs 보다 먼저)
        self.header_editor = None    # HeaderEditor: 줄 맞추기 자간 변형(프로필이 양식을 열 때 넣는다)
        self.line_mode = "fit"       # fit: 예측 줄 + 자간(강제 줄 나눔 없음) · force: 예측 줄을 강제 줄 나눔으로 · none: 한글에 맡김
        self._spaced = {}            # 자간 변형 ID → (기준 ID, delta)
        self._next_id = self.ID_START
        self._next_inst = self.INST_START

    def styled(self, base_cs, tag):
        """꾸밈 태그(u·b·i·sup·sub) → 글자 모양 ID. 자간 변형 위의 꾸밈은 '기준 꾸밈 + 같은 자간'으로 합성한다."""
        if base_cs in self._spaced:
            base0, delta = self._spaced[base_cs]
            return self.spaced(self.styled(base0, tag), delta)
        if self.variants is not None:
            return self.variants.variant(base_cs, tag)
        return self.style_cs.get(tag, base_cs)

    def spaced(self, base_cs, delta):
        """글자 모양 base_cs 에 자간 delta(%)를 더한 변형 ID(양식 편집기가 없으면 base_cs)."""
        if not delta or self.header_editor is None:
            return base_cs
        if base_cs in self._spaced:
            base_cs, d0 = self._spaced[base_cs]
            delta += d0
        cs = self.header_editor.spacing_variant(base_cs, delta)
        if cs != base_cs:
            self._spaced[cs] = (base_cs, delta)
        return cs

    # ── ID
    def reserve(self, xml_texts):
        ids = [int(x) for t in xml_texts for x in re.findall(r'<hp:\w+ id="(\d+)"', t)]
        inst = [int(x) for t in xml_texts for x in re.findall(r'instid="(\d+)"', t)]
        self._next_id = max([x for x in ids if x < self.ID_CAP] + [self.ID_START, self._next_id - 1]) + 1
        self._next_inst = max(inst + [self.INST_START, self._next_inst - 1]) + 1

    def nid(self):
        self._next_id += 1
        return self._next_id - 1

    def inst_id(self):
        self._next_inst += 1
        return self._next_inst - 1
