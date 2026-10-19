"""LEET 추리논증 트랙. 문항 유형은 법전협 5유형(composition 형식 설계·조판기 해설지와 같은 목록)."""
from ..core.track import Track
from .review_checks import check_item_model


class LeetReasoning(Track):
    name = "leet_reasoning"
    label = "LEET 추리논증"
    typeset_profiles = {None: "leet_reasoning"}
    style_note = "발언 라벨: 기출 원문 전사는 '갑: '(붙임)이지만 조판기는 라벨 뒤 띄움(\\s*:\\s*)을 모두 받아 양식 꼴(갑+고정폭 빈칸+:+빈칸)로 다시 찍는다. 원고는 라벨 객체 {\"라벨\": \"갑\", \"글\": …} 또는 '갑 : …'(조판기 README 예)로 쓰고 윤문 대상이 아니다. 라벨 꼴은 갑·갑1·을 1·A·P1만(밖이면 UNKNOWN_LABEL). 가운뎃점은 · (U+00B7) 하나로 통일."
    polish_note = '상세 원칙·범주·DPO 스키마는 `docs/leet_reasoning/윤문마스터_v0.md`(2019~2027 360문항 기준). 규범 조문은 `해야 한다`형(상황판단과 반대).'
    vocab = {
        "area": ["규범", "인문", "사회", "논리학·수학", "과학기술"],
        "item_type": ["언어 추리", "논쟁 및 반론", "논증 분석", "논증 평가 및 문제 해결", "모형 추리"],
        "item_format": ["합답형", "일반", "도식", "빈칸"],
        "discourse": ["평서문", "대화형", "규정·사례", "실험", "혼합"],
    }

    # 내용 영역 표기 — 해설 양식 메모의 옵션이 최종(하드코딩): 규범(법) / 인문(법,철학,논리,역사) / 사회(경제,경영) / 논리학·수학 /
    # 과학기술(물리/화학/생명/지구). 괄호로 포섭되지 않으면 대분류만 쓴다('인문', '사회', '과학기술'). 목록 밖 세부는 만들지 않는다
    area_details = {
        "규범": ["법"],
        "인문": ["법", "철학", "논리", "역사"],
        "사회": ["경제", "경영"],
        "논리학·수학": [],
        "과학기술": ["물리", "화학", "생명", "지구"]
    }

    diagram_options = True   # 원고 `설계.도식선지`(논증 구조 5개) → 그림 선지의 argument 그림(트랙 검사·블라인드 풀이가 구조를 본다)

    def max_items(self, grade=None):
        return 40

    def import_facets(self, q):
        """해설 칸(내용영역·문항유형)이 기준. 응답 형식은 설계.하네스응답형식, 없으면 보기→합답형 · 그림 선지→도식 · 그 밖→일반."""
        d, hs = q.get("설계") or {}, q.get("해설") or {}
        figs_opt = any(isinstance(o, dict) and "그림" in o for o in q.get("선지", []))
        fmt = d.get("하네스응답형식") or ("합답형" if q.get("보기") else "도식" if figs_opt else "일반")
        return hs.get("내용영역") or "", hs.get("문항유형") or "", fmt

    def check_item(self, item, brief):
        errors, warnings = [], []
        if item.item_format == "합답형" and not item.statements:
            errors.append(item.id + ": 합답형인데 보기가 없습니다")
        if item.item_format == "도식" and not all(c.figure_id for c in item.options):
            errors.append(item.id + ": 도식 문항은 다섯 선지가 모두 그림(논증 도식)이어야 합니다")
        if item.item_format == "도식" and any(f.kind != "argument" for f in item.figures if f.placement.startswith("option_")):
            if "설계 없음" in item.design.reference_use:      # 설계 없는 조판 원고(exam.json)의 그림 파일 도식은 구조를 알 수 없다 — 경고
                warnings.append(item.id + ": 도식 선지가 그림 파일이라 구조(argument)를 검사하지 못했습니다")
            else:
                errors.append(item.id + ": 도식 선지는 argument 그림이어야 합니다")
        if item.item_format == "도식" and item.item_type != "논증 분석":
            errors.append(item.id + ": 논증 구조 도식 문항의 유형은 '논증 분석'입니다")
        # 내용 검수 기계 검사(사람 검수 사례에서 뽑은 규칙): 해설 미동기화·보기 시점 미확정·미사용 조문·우회·표기 등(review_checks.py)
        e, w = check_item_model(item)
        errors += [item.id + ": " + x for x in e]
        return errors, warnings + [item.id + ": " + x for x in w]


TRACK = LeetReasoning()
