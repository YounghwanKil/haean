"""PSAT 자료해석 트랙: 표 또는 수치 그래프와 재계산식이 필수. 5급 표준 40문항 회차는 composition(형식·내용 설계)이 만든다."""
from ..psat_common import PsatTrack


class PsatData(PsatTrack):
    name = "psat_data"
    label = "PSAT 자료해석"
    typeset_profiles = {5: "psat5_data", 7: "psat7_data"}   # 7급 양식은 도착 예정
    polish_note = '자료해석은 지문이 표·그래프·보고서라 문장 지표가 작다. 보고서·각주 문장과 보기 진술 위주로 본다. 수치·단위는 윤문 대상이 아니다.'
    # 어휘 = composition 명세의 소재 분야(§15.1)·해설서 유형(§7). 발문 계열(B·S·M…)·형식은 생성틀 설계 키에 둔다
    vocab = {
        "area": ["산업·기업·무역", "문화·관광·체육·미디어", "행정·정치·법·안전", "인구·가구·노동", "보건·의료·복지",
                 "환경·에너지·기상", "교육·학술", "교통·물류·건설·주택", "농림수산·식품", "과학기술·정보통신",
                 "경제·재정·금융", "역사", "국방·안보", "기타"],
        "item_type": ["단순확인", "공식·조건", "빈칸", "전환", "복수의 표", "매칭", "종합", "표와 그림", "추가로 필요한 자료", "수리퀴즈"],
        "item_format": None,
        "discourse": None,
    }

    def check_item(self, item, brief):
        errors = []
        has_table = any(b.kind == "표" for b in item.passage)
        numeric = any(f.kind in {"bar", "line"} and f.placement in {"passage", "statements"} for f in item.figures)
        if not (has_table or numeric):
            errors.append(item.id + ": 자료해석은 지문에 표나 수치 그래프가 필요합니다")
        if not item.calculations:
            errors.append(item.id + ": 자료해석은 선지 판단의 재계산식(calculations)이 필요합니다")
        for b in item.passage:
            if b.kind == "표" and not b.unit:
                errors.append(item.id + ": 표에 단위(unit)를 적습니다")
        return errors, []


TRACK = PsatData()
