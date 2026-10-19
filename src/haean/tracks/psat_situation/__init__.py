"""PSAT 상황판단 트랙. 5급 표준 40문항 회차는 composition(문번 골격 + 원형 번들 → 형식·내용 설계)이 만든다."""
from ..psat_common import PsatTrack


class PsatSituation(PsatTrack):
    name = "psat_situation"
    label = "PSAT 상황판단"
    typeset_profiles = {5: "psat5_situation", 7: "psat7_situation"}   # 7급 양식은 도착 예정
    style_note = "상황판단 발언 라벨은 甲:·乙:(한자) 또는 A:. marks_total의 '한자 인물'과 '한글 인물' 비교. 블록은 <상황>·<보기>·<대화>, 불릿 ○, 주석 ※, 조문 제○○조 ①."
    polish_note = '범주·블록별 적용표는 `docs/psat_situation/윤문기준선_v0.md`. 조문은 `하여야 한다`형, 인물 甲乙丙, 가운뎃점 ㆍ, 물결 ～.'
    # 어휘 = composition 형식 설계 코드(format_rules.codes: 영역 9 · 분석 유형 5). 원리 20·응답 형식·합답 배열은 생성틀 설계 키에 둔다
    vocab = {
        "area": ["법·제도(실제)", "행정·공공(가상)", "생활·일상(가상)", "게임·퍼즐(소재 무관)", "과학·기술",
                 "사회·문화", "역사·전통", "경제·금융", "국제·외교"],
        "item_type": ["규범 판단", "정보 이해·적용", "수리 모델링", "조건 추론", "실무 기준 적용"],
        "item_format": None,
        "discourse": None,
    }


TRACK = PsatSituation()
