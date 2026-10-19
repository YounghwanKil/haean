"""PSAT 언어논리 트랙. 5급 표준 40문항 회차는 composition(형식·내용 설계)이 만든다."""
from ..psat_common import PsatTrack


class PsatVerbal(PsatTrack):
    name = "psat_verbal"
    label = "PSAT 언어논리"
    typeset_profiles = {5: "psat5_language", 7: "psat7_language"}   # 7급 양식은 도착 예정
    polish_note = "가운뎃점 ㆍ. 논증·견해 지문은 '~고 본다/주장한다'형 종결이 기출 관행 — 번역투로 보지 않는다."
    # 어휘 = composition 형식 설계 코드(유형 체계 v2 — 4대분류·9하위유형, composition/taxonomy.py). 원리는 해설 문항유형 칸
    vocab = {
        "area": ["인문", "사회", "과학기술", "공직 상황", "논리"],
        "item_type": ["일치부합", "사례 찾기·적용", "글의 문맥·구조", "빈칸 채우기", "추론", "논리퀴즈", "전제·결론", "견해 비교·대조", "강화·약화", "종합"],
        "item_format": None,
        "discourse": None,
    }
    # 내용영역 세부 = 통합데이터 '세부영역' 14종(괄호 보충은 뺀 표기 — composition format_rules.subarea.area_map 과 같은 대응).
    # 해설 내용영역은 '인문(역사)'·'논리(공직 상황)' 꼴. 형식 설계(2026-10-18~)가 자리마다 세부영역을 정한다(1·2번 역사 등).
    area_details = {
        "인문": ["역사", "철학·윤리", "언어·문학·예술"],
        "사회": ["사회·문화", "법·규범", "경제·경영", "정치·행정", "심리·인지", "논리 기호"],
        "과학기술": ["생명과학", "물리·화학", "지구·환경·천문", "기술·공학·IT"],
        "공직 상황": ["공직 상황"],
        "논리": ["공직 상황", "논리 기호"],
    }


TRACK = PsatVerbal()
