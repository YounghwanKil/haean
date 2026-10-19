# -*- coding: utf-8 -*-
"""PSAT 해설지(언어논리·상황판단·자료해석, 5급·7급 공통). LEET 추리논증 해설 양식과 짜임을 그대로 쓴다.

과목 이름만 바꾼다(정답표 제목 '○○ 영역 정답표', 해설 머리 상자). 내용 영역·문항 유형은 자유 글(검사하지 않음).
원고 '해설' 형식은 LEET 와 같다: 제재 · 난이도 · 내용영역 · 문항유형 · 논평 · 정오판단(· 선지판단).
"""
from ..leet_reasoning_solutions import LeetReasoningSolutions


class PsatSolutions(LeetReasoningSolutions):
    areas = None
    types = None

    def __init__(self, name, subject):
        self.name = name
        self.subject = subject


LANGUAGE = PsatSolutions("psat_solutions.LANGUAGE", "언어논리")
SITUATION = PsatSolutions("psat_solutions.SITUATION", "상황판단")
DATA = PsatSolutions("psat_solutions.DATA", "자료해석")
PROFILE = LANGUAGE
