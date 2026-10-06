"""Compute blueprints from item-level data, not uncalculated workbook formulas."""
from collections import Counter
from fractions import Fraction
import re

from .corpus import Corpus


def allocate(weights: dict[str, int], total: int) -> dict[str, int]:
    if total < 1 or not weights or any(v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("Positive total and nonnegative weights required")
    quotas = {k: Fraction(v * total, sum(weights.values())) for k, v in weights.items()}
    result = {k: int(v) for k, v in quotas.items()}
    order = sorted(weights, key=lambda k: (-(quotas[k] - result[k]), k))
    for k in order[:total - sum(result.values())]:
        result[k] += 1
    return result


def blueprint(corpus: Corpus, exam: str, subject: str, since=2024, until=2026,
              exclude_extra=False, product="full") -> dict:
    if (exam == "leet") != (subject == "추리논증"):
        raise ValueError("시험·과목 조합 오류")
    if product not in {"full", "bridge"} or (product == "bridge" and exam != "leet"):
        raise ValueError("브릿지는 LEET 20문항 제품입니다")
    records = []
    for row in corpus.rows(exam):
        f = row["fields"]
        year_match = re.search(r"20\d\d", str(f.get("연도", f.get("학년도", ""))))
        if not year_match or not since <= int(year_match.group()) <= until:
            continue
        if f.get("과목") != subject or f.get("통계 구분") == "참고":
            continue
        if exam == "leet" and not f.get("지문"):
            continue
        if exclude_extra and "추가" in str(f.get("회차", "")):
            continue
        records.append(row)
    if not records:
        raise ValueError("해당 시험·과목의 문항 데이터가 없습니다. 먼저 import 하세요.")
    total = 20 if product == "bridge" else 25 if exam == "psat7" else 40
    key = lambda f: f"{f['내용영역']} / {f['문항유형']}" if exam == "leet" else f["문항유형"]
    counts = Counter(key(r["fields"]) for r in records)
    sessions = sorted({str(r["fields"].get("회차", r["fields"].get("연도", r["fields"].get("학년도")))) for r in records})
    allocation = allocate(dict(counts), total - 1 if product == "bridge" else total)
    positions = {}
    for r in records:
        f = r["fields"]
        t = key(f)
        positions.setdefault(t, []).append(int(f["문항 번호"]))
    ordered = sorted(allocation, key=lambda t: (sum(positions[t]) / len(positions[t]), t))
    slots = [{"number": i + 1, "type": t} for i, t in enumerate(t for t in ordered for _ in range(allocation[t]))]
    if product == "bridge":
        slots.append({"number": None, "type": "논증 구조", "state": "reserved", "note": "별도 엔진용 1자리. 실제 번호는 편집자가 정함; 미제작 슬롯이다."})
    return {"exam": exam, "subject": subject, "total": total, "product": product,
            "period": [since, until], "sessions": sessions, "session_count": len(sessions),
            "observations": len(records), "allocation": allocation, "slots": slots,
            "method": "문항별 빈도에서 최대잔여법으로 정수 배분. 원자료의 AI 분류는 미검증. 제안값이며 고정 할당량 아님.",
            "source_ids": [r["source_id"] for r in records],
            "set_policy": "2문항 공통지문 1세트, 위치 검토 필요" if exam == "psat7" else
                          "2문항 공통지문 2세트, 과목별 위치 검토 필요" if exam == "psat5" else "공유 지문 필요 여부를 회차별로 결정",
            "notes": ["슬롯은 유형 평균 위치에 따른 초안. 소재·난도·정답·공유지문 배치를 편집자가 조정.",
                      "5급과 7급의 같은 원문 ID는 서로 다른 문항이다. exam과 함께 식별.",
                      "체감 난도는 추정값이며 실측 정답률이 아니다."]}
