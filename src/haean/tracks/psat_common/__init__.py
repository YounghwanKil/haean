"""PSAT 세 트랙이 공유하는 급수 규칙(5급 40문항 · 7급 25문항, 2문항 공통지문 세트 허용)과 표기(ㆍ · '년')."""
import json
from pathlib import Path

from ..core.track import Track


class PsatTrack(Track):
    grades = (5, 7)
    set_size = 2
    set_mixed_types = True   # 2문항 세트의 두 문항은 유형·응답 형식이 다를 수 있다(명세 '혼합')
    middot = "ㆍ"   # PSAT 기출 표기(composition manuscript_check·윤문 기준서와 같음)
    year_label = "년"   # 공식 표기 '2026년도 5급 공채' → 참고 기출은 '2026년 14번'
    vocab = {"area": None, "item_type": None, "item_format": None, "discourse": None}
    _principle_type: dict | None = None

    def max_items(self, grade=None):
        return 25 if grade == 7 else 40

    def principle_type(self) -> dict:
        """해설 '문항유형' 칸의 원리 이름(내용 일치·규범 요건·예외 포섭 …) → 트랙 유형 어휘. 설계가 없는 조판 원고(exam.json 등)를 되읽을 때 쓴다.
        composition/format_rules.json 의 codes 에서 만든다(없으면 빈 dict)."""
        if self._principle_type is None:
            out = {}
            path = Path(__file__).resolve().parents[1] / self.name / "composition" / "format_rules.json"
            if path.exists():
                codes = (json.loads(path.read_text(encoding="utf-8")).get("codes") or {})
                names = {v: k for k, v in (codes.get("type") or {}).items()}                     # 번호 → 유형
                for tnum, principles in (codes.get("principle_names") or {}).items():            # 언어논리: {"1": {"1": "내용 일치"}}
                    for name in (principles or {}).values():
                        if names.get(int(tnum)):
                            out[name] = names[int(tnum)]
                for spec in (codes.get("principles") or {}).values():                            # 상황판단: {"11": {"name", "type"}}
                    if isinstance(spec, dict) and spec.get("name") and spec.get("type"):
                        out[spec["name"]] = spec["type"]
            self._principle_type = out
        return self._principle_type

    def import_facets(self, q):
        """생성틀 설계 키가 기준(상황판단은 영역·분석유형). 유형 칸에 해설의 원리 이름이 오면 유형 어휘로 바꾼다."""
        d, hs = q.get("설계") or {}, q.get("해설") or {}
        area = d.get("내용영역") or d.get("영역") or hs.get("내용영역") or ""
        typ = d.get("유형") or d.get("분석유형") or hs.get("문항유형") or ""
        allowed = self.vocab.get("item_type") or []
        if typ and allowed and typ not in allowed:
            typ = self.principle_type().get(typ, typ)
        return area, typ, "합답형" if q.get("보기") else "일반"
