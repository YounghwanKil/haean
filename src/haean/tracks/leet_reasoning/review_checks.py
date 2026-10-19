"""LEET 추리논증 내용 검수 — 기계로 잡을 수 있는 부분(편집 검토 보조).

사람 검수 사례에서 반복된 지적과 수정 부작용을 규칙으로 옮긴다. 사례가 쌓이면 규칙도 늘린다
(1차 근거: 서바6회 자체 제작 9문항의 AI 초안 → 팀장 마감 → 대면검수 3조 → 1차 반영 대조정리).
의미상 정답을 증명하지 않는다. errors는 출제자에게 되돌리는 사유, warnings는 편집 검토자가 읽는 단서다.
입력은 트랙 공용 Item(check_item_model) 또는 조판 원고 JSON 문항(check_manuscript_item). 표준 라이브러리만 쓴다.

검사 ID(docs/leet_reasoning/검수원칙_v1.md §5와 같다)
  검수-01 해설 인용·근거 문장 미동기화   검수-02 보기 가정 사건의 시점 미확정   검수-03 미사용 조문·수치
  검수-04 쉬운 보기 우회                 검수-05 보기 결론절의 지문 밖 새 개념    검수-06 '판단 불가'를 ×의 근거로
  검수-07 합답형 선지 배열               검수-08 표기(숫자-단위·수사 혼용·법률 지시어·띄어쓰기 변이·동의어 혼용·지문-보기 용어 괴리)
  검수-09 논평 형식                      검수-10 해설 형식(인용·길이·위치 표지 대신 논리)  검수-11 난이도 표기 재점검
  검수-12 계산·정보량                    검수-13 구어·풀어쓰기 표현(격식 어휘표)
"""
from __future__ import annotations

import json
import re
from fractions import Fraction
from itertools import combinations
from pathlib import Path

HEADS = "ㄱㄴㄷㄹㅁ"
CIRCLED = "①②③④⑤"
PATTERNS = {
    "P1": ["ㄱ", "ㄴ", "ㄱㄷ", "ㄴㄷ", "ㄱㄴㄷ"],
    "P2": ["ㄱ", "ㄷ", "ㄱㄴ", "ㄴㄷ", "ㄱㄴㄷ"],
    "P3": ["ㄴ", "ㄷ", "ㄱㄴ", "ㄱㄷ", "ㄱㄴㄷ"],
}
LAW_KINDS = {"조문", "항", "호", "의안"}
LISTED_KINDS = {"조문", "항", "호", "의안", "조건", "실험", "목록", "나열", "원리"}
LEXICON_PATH = Path(__file__).with_name("review_lexicon.json")
# 원문에서 추출한 치환 자료는 이식하지 않는다. 모델·자료 경로와 연결하는
# 후속 작업 전에는 로컬에 동명 파일이 생겨도 암묵적으로 읽지 않는다.
LEXICON_ENABLED = False

# 보기·해설에서 소재 토큰으로 세지 않는 말(평가 용어·기능어·인물 기호)
STOP = set("""것 경우 때 수 등 및 또는 그리고 따라 따르면 대한 관한 위한 이에 다음 보기 선지 지문 사례 상황 규정 규칙 조항 조문 견해 입장 주장 결론 근거 전제 논거 가설 원리 사실
강화 약화 지지 반박 비판 옳다 옳은 적절 추론 판단 판정 평가 분석 적용 설명 해석 비교 가능 불가능 필요 충분 조건 관계 이유 결과 원인 모두 각각 서로 자신 상대 상대방 하나 둘 사이 이상 이하 초과 미만 이전 이후 전부 일부
있다 없다 있는 없는 있을 없을 한다 된다 아니다 때문 그러나 따라서 그런데 또한 한편 이때 이러한 이런 그런 모든 해당 다른 같은 어떤 무엇 누구 언제 어디 반드시 언제나 항상 오직 다만 특히 역시 바로 매우 더욱 가장 이미 아직 경우에 때에 관해 관하여 대해 대하여 위해 위하여 통해 통하여 따라 의해 의하여 그렇 이렇 저렇 내용 사항 여부 정도 이상 이하
갑 을 병 정 무 기 경 신 임 계 갑국 을국 병국 정국 무국 A B C D E P Q X Y Z""".split())
PARTICLES = ["이라는", "라는", "다는", "으로는", "에서는", "에게는", "으로써", "으로서", "에서", "에게", "에는", "에도", "까지", "부터", "보다", "처럼", "마다", "조차", "으로", "로", "은", "는", "이", "가", "을", "를", "의", "와", "과", "도", "만", "에"]
VERB_TAILS = ["되었다는", "하였다는", "함으로써", "함으로", "함", "할", "한", "된", "하기", "되기", "인지", "이란", "란", "인", "임", "었는데", "는데", "되지", "지", "하다", "되다", "하므로", "되므로", "므로", "되었다", "하였다", "했다는", "한다는", "않는다", "않았다", "않으면", "않고", "않는", "않은", "하지", "하는", "하여", "하면", "한다", "했다", "된다", "되는", "되어", "되면", "될", "있다", "있는", "있어", "없다", "없는", "이다", "였다", "이며", "하고", "해야", "되어야", "하여야", "일", "된"]
ASSUME = re.compile(r"(다면|라면|이면|경우|때)[,]?\s")
EXPLICIT_TIME = re.compile(r"\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}|\d{4}년\s*\d{1,2}월|\d+\s*(년|개월|달|일|주|시간)\s*(이내|안에|내에|후|뒤|전|지나|경과|만에|되는 날|째)|(이내|안에|내에)에?\b|지나도록|지난 뒤|경과한? [뒤후]|당일|같은 날|즉시|동시에|직후|직전|전에 |후에 |이전에|이후에 ")
PERIOD_RULE = re.compile(r"(\d+|[일이삼사오육칠팔구십]+)\s*(개월|달|일|년|주)\s*(이내|안에|내에|이|가|을|이 지나|지나|경과)|(날|때|일)(부터|로부터)|지나도록|기산|경과하면|경과한 날")
TIMED_ACT = re.compile(r"이의|제기|통지|통고|신고|신청|철회|제출|발송|가입|선언|납부|등록|거절|승낙|수락|수리|청구|해지|해제|취소|이행")
ASSUMED_IN_EXPL = re.compile(r"만일|만약|가정|않았다면|않은 경우|않는다면|하지 않았다면|이내에 .*않|경우에는")
UNDETERMINED = re.compile(r"(판정|판단|확정|단정|결정)할 수 없|알 수 없|정해지지 않|확정되지 않")
ASSERT_RELATION = re.compile(r"(판단|판정|결론|견해|입장)[을이가은는]?\s*(달리|다르|같|일치)|단정|반드시|언제나|항상")
AFTER_UNIT = r"(?=$|[^가-힣]|[을를이가은는의과와도만에씩]|으로|에서|부터|까지|이다|이며|이고)"   # 단위 뒤에는 조사만 허용
NUM_UNIT_SPACE = re.compile(r"(?<=\d)\s+(건|명|개|원|회|배|팀|곳|가지|장|개월|년|월|일|시간|분|초|%|㎡|km|kg|cm|mm)" + AFTER_UNIT)
HANGUL_NUMERAL = re.compile(r"(?<![가-힣])(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|열한|열두|열다섯|스무|서른|마흔|쉰)\s?(개|명|팀|차례|번|가지|곳|사람|마리|대|장|시간|달|해)" + AFTER_UNIT)
ARABIC_COUNT = re.compile(r"\d+\s?(개|명|팀|차례|번|가지|곳|사람|마리|대|장|시간)" + AFTER_UNIT)
LEGAL_DEICTIC = re.compile(r"후단|전단|각 호|각호|전항|동조|동항")
RELATION = re.compile(r"비례|나눈 값|곱한 값|곱한|제곱|제곱근|배율|합과 같|같아지면|계수|할인율|현재가치|수익률|밀도|농도")
SENT_END = re.compile(r"(?<=[.?!])\s+")
SYNONYMS = [("지금 시점", "현재 시점"), ("알아볼 수", "식별할 수"), ("세 번 곱한", "세제곱"), ("관측되지 않음", "미관측"),
            ("상대의", "상대방의"), ("상대를", "상대방을"), ("상대가", "상대방이"), ("사망자", "피상속인"), ("상댓값", "상대값"),
            ("거쳐야", "통하여야"), ("재판으로", "재판에 의하여"), ("자료 A", "정보 A"), ("자료 B", "정보 B")]
IMPERATIVE_TITLE = re.compile(r"(라|어라|아라|마라|지어라|하세요|십시오|할 것)$")
GUIDE_TONE = re.compile(r"십시오|시기 바랍니다|보세요|마세요|두십시오|하세요|해 보십시오|시작하십시오")
LAW_REF = re.compile(r"제\s*\d+\s*조")
PROVENANCE = re.compile(r"^이 문항은 .*(바탕으로|구성하였다|가상)")   # 생성틀 논평 첫 문단(출처 문장)


# ── 정규화 ──────────────────────────────────────────────────────────

def squash(s: str) -> str:
    s = str(s).replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", "", s)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_END.split(str(text)) if len(s.strip()) >= 8]


def grams(s: str):
    t = squash(s)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def dice(a: str, b: str) -> float:
    ga, gb = grams(a), grams(b)
    return 2 * len(ga & gb) / (len(ga) + len(gb)) if ga and gb else 0.0


PERSON = set("갑을병정무기경신임계")
FUNC1 = {"등", "및", "각", "그", "즉", "둘", "셋", "넷", "곧", "뿐", "때", "수", "것", "데"}
PRED = re.compile(r"^(않|못하)")   # 부정 술어는 소재가 아니다
PRED_WORDS = set("""받은 받지 받아 받는 받으면 같다 같은 같이 달리 다르 다른 다르다 많은 많다 적은 적다 크다 작다 높다 낮다 있는 없는 되는 하는 보는 본다 둔다 들어 따라 따른 따르면
이루 가지 가진 주는 오는 쓰는 알게 말한 말하 본다 둔다 돌린 넘는 남긴 막는 내는 쌓여 끌어 따로 늘어 줄어 바라 생기 생긴 나타 떠올 옮겨 맡는 놓고 빼고 넣어 읽는 듣는 묻는 답한 얻는 잃는 열어 닫는 택하 택한 고른 갈리 갈라 나뉘 해당 이르 만나 만날 만들 틀리 맞는 어긋""".split())


def strip_tail(w: str) -> str:
    for _ in range(3):
        before = w
        for t in sorted(VERB_TAILS, key=len, reverse=True):
            rest = w[:-len(t)] if w.endswith(t) else None
            if rest and (len(rest) >= 2 or rest in PERSON or rest in FUNC1):
                w = rest
                break
        for p in sorted(PARTICLES, key=len, reverse=True):
            rest = w[:-len(p)] if w.endswith(p) else None
            # '갑과'→'갑', '등의'→'등', '쪽은'→'쪽'(1자만 남으면 버려진다). '의'는 명사 끝(이의·동의)일 수 있어 2자 이상만
            if rest and (len(rest) >= 2 or rest in PERSON or rest in FUNC1 or p != "의"):
                w = rest
                break
        if w == before:
            break
    return w


def stems(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[가-힣A-Za-z0-9]+", str(text)):
        if re.fullmatch(r"[A-Za-z0-9]+", w):
            continue
        s = strip_tail(w)
        if len(s) >= 2 and s not in STOP and s not in FUNC1 and s not in PRED_WORDS and re.fullmatch(r"[가-힣]+", s) and not PRED.match(s):
            out.add(s)
    return out


def norm_combo(opt: str) -> str:
    return re.sub(r"[,\s]", "", str(opt))


def is_combo(view) -> bool:
    return len(view["statements"]) in (3, 4) and all(re.fullmatch(r"[ㄱㄴㄷㄹ]+", norm_combo(o) or "-") for o in view["options"])


# ── 입력 어댑터: 공통 뷰 ─────────────────────────────────────────────
# view = {id, stem, area, item_type, blocks:[(kind,label,text)], passage, statements:[str], options:[str], answer,
#         judgments:[(mark, text)], comment_title, comment:[str], level, calculations:[(expr, expected)]}

def _ms_block(b, out):
    if isinstance(b, str):
        m = re.match(r"^(제\s*\d+\s*조[^ ]*)\s+(.*)$", b)
        if m:
            out.append(("조문", m.group(1), m.group(2)))
        elif re.match(r"^[①-⑮]\s", b):
            out.append(("항", b[0], b[1:].strip()))
        elif re.match(r"^<[^>]+>$|^\[[^\]]+\]$", b.strip()):
            out.append(("소제목", "", b))
        elif re.match(r"^◦\s*조건\s*\S+\s*:", b):
            out.append(("조건", "", b))
        elif b.startswith("◦"):
            out.append(("나열", "", b.lstrip("◦ ")))
        elif re.match(r"^실험\s*\S+\s*:", b):
            out.append(("실험", "", b))
        elif b.startswith("[원리]"):
            out.append(("원리", "", b[4:].strip()))
        elif re.match(r"^\S{1,4}\s*:\s", b):
            out.append(("발언", b.split(":")[0].strip(), b.split(":", 1)[1].strip()))
        else:
            out.append(("문단", "", b))
        return
    if not isinstance(b, dict):
        return
    if "상자" in b:
        for c in b.get("내용", []):
            _ms_block(c, out)
        return
    if "표" in b:
        rows = b["표"]
        text = " ".join(" | ".join(c["글"] if isinstance(c, dict) else str(c) for c in r) for r in rows)
        out.append(("표", b.get("제목", ""), " ".join(x for x in (b.get("제목", ""), b.get("단위", ""), text, str(b.get("주석", ""))) if x)))
        return
    if "그림" in b:
        out.append(("그림", "", b.get("제목", "")))
        return
    if "라벨" in b:
        out.append(("발언", b["라벨"], b.get("글", "")))
        return
    for kind in ("조문", "항", "호", "의안", "조건", "실험", "목록", "목"):
        if kind in b:
            out.append((kind, str(b[kind]), b.get("글", "")))
            return
    for kind in ("문단", "소제목", "나열", "원리", "주석"):
        if kind in b:
            out.append((kind, "", b[kind]))
            return


def _judges_ms(js):
    out = []
    for j in js or []:
        ex = j.get("설명", "")
        out.append((j.get("판정", ""), " ".join(ex) if isinstance(ex, list) else str(ex)))
    return out


def view_from_manuscript(q: dict) -> dict:
    blocks = []
    for b in q.get("지문", []) or []:
        _ms_block(b, blocks)
    hs = q.get("해설", {}) or {}
    comment = hs.get("논평", "")
    title = ""
    if isinstance(comment, dict):
        title, comment = comment.get("제목", ""), comment.get("글", "")
    if isinstance(comment, str):
        comment = [comment] if comment else []
    statements = [s["글"] if isinstance(s, dict) else str(s) for s in q.get("보기", []) or []]
    options = [o if isinstance(o, str) else "" for o in q.get("선지", [])]
    judg = _judges_ms(hs.get("정오판단")) if statements else _judges_ms(hs.get("정오판단") or hs.get("선지판단"))
    if statements and not judg:
        judg = _judges_ms(hs.get("선지판단"))
    return {"id": q.get("id", ""), "stem": q.get("발문", ""), "area": re.sub(r"\s*[(（].*$", "", str(hs.get("내용영역", ""))),   # '과학기술(생명)' → 대분류 "item_type": hs.get("문항유형", ""),
            "blocks": blocks, "passage": "\n".join(t for _, _, t in blocks), "statements": statements, "options": options,
            "answer": int(q.get("정답", 0) or 0), "judgments": judg, "comment_title": title or "", "comment": list(comment),
            "level": hs.get("난이도", 0) if isinstance(hs.get("난이도"), int) else 0,
            "calculations": [(c.get("식") or c.get("expression", ""), c.get("값") or c.get("expected", ""))
                             for c in (q.get("계산") or (q.get("설계") or {}).get("계산") or []) if isinstance(c, dict)]}


def view_from_item(item) -> dict:
    blocks = []

    def walk(bs):
        for b in bs:
            if b.kind == "상자":
                walk(b.children)
            elif b.kind == "표":
                text = " ".join(" | ".join(c.text for c in r) for r in b.rows)
                blocks.append(("표", b.title, " ".join(x for x in (b.title, b.unit, text, b.note) if x)))
            elif b.kind == "그림":
                blocks.append(("그림", b.figure_id, b.title))
            else:
                blocks.append((b.kind, b.label, b.text))
    walk(item.passage)
    s = item.solution
    judg = [(j.mark, " ".join(j.explanation)) for j in (s.statement_judgments if item.statements else s.option_judgments)]
    return {"id": item.id, "stem": item.stem, "area": item.area, "item_type": item.item_type, "blocks": blocks,
            "passage": "\n".join(t for _, _, t in blocks), "statements": [x.text for x in item.statements],
            "options": [c.text for c in item.options], "answer": item.answer, "judgments": judg,
            "comment_title": s.comment_title, "comment": list(s.comment), "level": s.level,
            "calculations": [(c.expression, c.expected) for c in item.calculations]}


# ── 개별 검사 ────────────────────────────────────────────────────────

def _public(v):
    return v["stem"] + "\n" + v["passage"] + "\n" + "\n".join(v["statements"])


def rv01_explanation_sync(v, *, quotes=True):
    """해설 문장이 지문 문장과 비슷하지만 자구가 다른 경우(미동기화 의심, 경고). 따옴표 인용 자체는 해설 원칙이 금지한다."""
    errs, warns = [], []
    pub = squash(_public(v))
    psents = sentences(v["passage"])
    for k, (_, ex) in enumerate(v["judgments"]):
        tag = HEADS[k] if v["statements"] else CIRCLED[k] if k < 5 else str(k + 1)
        # 따옴표 인용은 해설 원칙(core/explanations)이 전 과목에서 금지한다 — 여기서는 인용 없이 지문을 풀어 쓴 해설이 현행 지문과 어긋나는지만 본다
        for es in sentences(ex):
            if len(squash(es)) < 18 or squash(es) in pub:
                continue
            best = max(psents, key=lambda s: dice(es, s), default="")
            if not best:
                continue
            sim = dice(es, best)
            if 0.6 <= sim < 0.95 and squash(best) not in squash(es) and squash(es) not in squash(best):
                warns.append(f"[검수-01] {tag} 해설 문장이 지문 문장과 비슷하나 자구가 다름(미동기화 의심, 유사 {sim:.2f}): '{es[:36]}…' / 지문 '{best[:36]}…'")
    return errs, warns


def rv02_undated_assumption(v):
    """기간 규정이 있는 지문에서 보기의 가정 사건(이의·통지·가입 등)에 시점이 없음. 해설이 그 시점을 가정하면 오류."""
    errs, warns = [], []
    if not PERIOD_RULE.search(v["passage"]):
        return errs, warns
    for k, st in enumerate(v["statements"]):
        m = ASSUME.search(st)
        if not m or not TIMED_ACT.search(st):
            continue
        cond = re.sub(r"[“\"][^”\"]*[”\"]", " ", st[:m.end()])   # 인용된 선언 내용은 사건이 아니다
        # 가정절을 절 단위로 나눠, 시점 민감 행위(이의·통지·철회…)가 있는 절마다 날짜·기간이 있는지 본다('하며'는 같은 사건의 동시 서술이라 나누지 않는다)
        clauses = [c for c in re.split(r"(?:하였고|했고|였고|았고|었고|하였으며|했으며|였으며)\s+|,\s*", cond) if c.strip()]
        undated = [c for c in clauses if TIMED_ACT.search(c) and not EXPLICIT_TIME.search(c)]
        if not undated or (len(clauses) == 1 and EXPLICIT_TIME.search(cond)):
            continue
        ex = v["judgments"][k][1] if k < len(v["judgments"]) else ""
        if ASSUMED_IN_EXPL.search(ex):
            errs.append(f"[검수-02] 보기 {HEADS[k]}: 기간 규정이 있는데 가정 사건의 시점이 문면에 없고, 해설이 보기에 없는 시점을 가정해 판정함 — 날짜를 명시하거나 판정 구조를 바꾼다(A)")
        else:
            warns.append(f"[검수-02] 보기 {HEADS[k]}: 기간 규정이 있는 지문에서 가정 사건의 시점이 문면에 없음 — '이후' 한 단어로는 닫히지 않는다. 날짜(예: 2024. 4. 1.)를 쓴다")
    return errs, warns


def _law_groups(blocks):
    """조문을 머리로 항·호를 묶는다. [(label, text_all, kinds)]"""
    groups, cur = [], None
    for kind, label, text in blocks:
        if kind == "조문" or (kind in LISTED_KINDS - {"항", "호"} and cur is None) or kind not in LAW_KINDS:
            if kind in LISTED_KINDS:
                cur = [label, text, kind]
                groups.append(cur)
            else:
                cur = None
            continue
        if cur is not None and cur[2] in LAW_KINDS | {"조문"}:
            cur[1] += " " + text
        else:
            cur = [label, text, kind]
            groups.append(cur)
    return groups


def rv03_unused_rules(v):
    """어느 보기·해설에도 쓰이지 않는 조문·조건·수치. 삭제하거나 보기에 쓴다(검수: '제4조는 활용될 수 있다', '제5조는 잉여')."""
    warns = []
    target = " ".join(v["statements"]) + " " + " ".join(t for _, t in v["judgments"]) + " " + " ".join(v["comment"])
    tstems = stems(target)
    tsq = squash(target)
    groups = _law_groups(v["blocks"])
    for label, text, kind in groups:
        m = re.search(r"제\s*(\d+)\s*조", label)
        if m and re.search(rf"제\s*{m.group(1)}\s*조", target):
            continue
        if kind in {"조건", "실험", "목록"} and label and re.search(rf"(조건|실험)\s*{re.escape(label)}\b", target):
            continue
        # 이 블록만이 가진 어간(다른 지문 블록에 없는 말). 그것이 보기·해설에 하나도 없으면 미사용으로 본다.
        others = stems(" ".join(t for k, l, t in v["blocks"] if t not in text))
        distinct = stems(text) - others
        symbols = set(re.findall(r"(?<![A-Za-z])[A-Z]\d?(?![A-Za-z])", label + " " + text))
        if symbols and symbols & set(re.findall(r"(?<![A-Za-z])[A-Z]\d?(?![A-Za-z])", target)):
            continue   # P·Q·A 같은 기호로 보기·해설이 가리키는 블록
        need = 2 if kind in LAW_KINDS else 3   # 조문은 고유 어간 2개, 나열·조건·실험은 3개부터
        if len(distinct) >= need and not (distinct & tstems):
            warns.append(f"[검수-03] {kind} '{(label or text)[:18]}' — 고유 내용 {sorted(distinct)[:3]}이 보기·해설 어디에도 쓰이지 않음. 삭제하거나 보기 하나의 판정에 쓴다(미사용 조문은 검수에서 잉여·활용 제안으로 돌아옴)")
    # 수치(표 밖)
    for kind, _, text in v["blocks"]:
        if kind in {"표", "그림"}:
            continue
        for num, unit in re.findall(r"(\d[\d,.]*)\s*(명|개|팀|억|만|원|%|회|건|시간|분|배|km|kg)", text):
            raw = num.replace(",", "").rstrip(".")
            if not raw or raw in tsq or any(raw in squash(e) for e, _ in v["calculations"]):
                continue
            if re.search(rf"{re.escape(num)}\s*{unit}", target):
                continue
            warns.append(f"[검수-03] 수치 '{num}{unit}' — 보기·해설·계산 어디에도 쓰이지 않음(판정에 안 쓰이는 표본 수치는 마감본에서 삭제됨)")
    return [], warns


def rv04_bypass(v):
    """합답형: 어느 보기를 판정하지 않아도 나머지 둘로 정답이 확정되는지."""
    warns = []
    if not is_combo(v) or len(v["judgments"]) != len(v["statements"]):
        return [], warns
    marks = [m for m, _ in v["judgments"]]
    combos = [set(norm_combo(o)) for o in v["options"]]
    n = len(v["statements"])
    pins = []
    for i, j in combinations(range(n), 2):
        ok = [c for c in combos if all(((HEADS[k] in c) == (marks[k] == "○")) for k in (i, j))]
        if len(ok) == 1:
            pins.append((i, j))
    lengths = [len(squash(t)) for _, t in v["judgments"]]
    hardest = lengths.index(max(lengths)) if lengths else -1
    parts, flag_hard = [], False
    for k in range(n):
        by = [p for p in pins if k not in p]
        if by:
            i, j = by[0]
            parts.append(f"{HEADS[k]}({HEADS[i]}·{HEADS[j]}만으로 확정{'·해설 최장' if k == hardest else ''})")
            flag_hard |= k == hardest
    if parts:
        ans = CIRCLED[v["answer"] - 1] if 1 <= v["answer"] <= 5 else "?"
        tail = " — 해설이 가장 긴 보기가 우회되므로 핵심 판단 우회 의심(B). 보기나 선지 배열을 다시 설계" if flag_hard else " — 우회되는 보기가 핵심 판단이 아니어야 한다(설계 4항)"
        warns.append(f"[검수-04] 정답 {ans}: 판정 없이도 되는 보기 " + ", ".join(parts) + tail)
    return [], warns


def rv05_new_concepts(v):
    """보기 결론절이 지문(과 발문)에 없는 개념으로 판정됨. 정답 보기면 '새 개념으로 쉽게 갈린다'는 지적 유형."""
    warns = []
    base = squash(_public(v).replace("\n".join(v["statements"]), ""))
    for k, st in enumerate(v["statements"]):
        parts = ASSUME.split(st, maxsplit=1)
        tail = parts[-1] if len(parts) > 1 else st
        mark = v["judgments"][k][0] if k < len(v["judgments"]) else ""
        if mark != "○":
            continue
        new = sorted(s for s in stems(tail) if s not in base and not any(s in squash(o) for o in v["statements"][:k]) and len(s) >= 2)
        if len(new) >= 3:
            warns.append(f"[검수-05] 정답 보기 {HEADS[k]}의 결론절에 지문 밖 개념 {new[:4]} — 새 개념만으로 정오가 갈리면 이중 부정 서술이라도 너무 쉽게 풀림. 판정 발판이 지문 안 요소에 걸려 있는지 확인")
    return [], warns


def rv06_undetermined_as_false(v):
    """'을로는 판정할 수 없다'를 근거로 보기를 ×로 만드는 구조. 검수: '알 수 없다를 참일 수도 거짓일 수도 있다로 처리하는 것은 위험'."""
    warns = []
    for k, st in enumerate(v["statements"]):
        if k >= len(v["judgments"]):
            break
        mark, ex = v["judgments"][k]
        if mark == "×" and ASSERT_RELATION.search(st) and UNDETERMINED.search(ex) and not UNDETERMINED.search(st):
            warns.append(f"[검수-06] 보기 {HEADS[k]}: 해설이 '판정할 수 없다'를 근거로 ×를 냄 — 판단 불가를 거짓 처리하는 구조(B). 보기를 '판정할 수 없다' 서술(○)로 두거나 보기를 교체한다")
    return [], warns


def rv07_option_pattern(v):
    errs, warns = [], []
    if not is_combo(v):
        return errs, warns
    if len(v["statements"]) != 3:
        warns.append(f"[검수-07] 보기 {len(v['statements'])}개 — 추리논증 합답형은 ㄱㄴㄷ 3개(형식 규칙)")
        return errs, warns
    normed = [norm_combo(o) for o in v["options"]]
    pat = next((p for p, arr in PATTERNS.items() if arr == normed), None)
    if pat is None:
        errs.append(f"[검수-07] 합답형 선지 배열 {normed}이 관측 배열(P1·P2·P3) 밖 — 초안에서 비관측 배열이 나오면 마감본은 P3(ㄴ/ㄷ/ㄱ,ㄴ/ㄱ,ㄷ/ㄱ,ㄴ,ㄷ)로 바꿨다")
    return errs, warns


def rv08_notation(v):
    warns = []
    full = _public(v) + "\n" + " ".join(t for _, t in v["judgments"])
    seen = set()
    for m in NUM_UNIT_SPACE.finditer(full):
        frag = full[max(0, m.start() - 6):m.end()]
        if frag not in seen:
            seen.add(frag)
            warns.append(f"[검수-08] 숫자와 단위 사이 띄어쓰기 '{frag.strip()}' — '6,000건'처럼 붙인다")
    hn, an = HANGUL_NUMERAL.findall(_public(v)), ARABIC_COUNT.findall(_public(v))
    if hn and an:
        warns.append(f"[검수-08] 수사 표기 혼용 — 한글 수사 {len(hn)}곳(예: {''.join(hn[0])}) / 아라비아 숫자 {len(an)}곳. 하나로 통일(실험 서술과 보기가 어긋난 사례)")
    has_law = any(k in LAW_KINDS for k, _, _ in v["blocks"]) or LAW_REF.search(v["passage"])
    deictic = set(LEGAL_DEICTIC.findall(_public(v)))
    if has_law and re.search(r"단서", _public(v)):
        deictic.add("단서")
    if deictic:
        warns.append(f"[검수-08] 법률 지시어 {sorted(deictic)} — 배경지식 없는 수험생은 가리키는 곳을 모른다. '뒷부분', '제○조의 예외' 등으로 풀어 쓴다(C)")
    toks = re.findall(r"[가-힣]{2,}", full)
    tokset = set(toks)
    particle_like = set(PARTICLES) | {"로서", "에서는", "에게는", "으로써", "이라고", "이라는", "이라", "에서의", "에게서"}
    for a, b in zip(toks, toks[1:]):
        if len(a) + len(b) < 4 or len(a) < 2 or len(b) < 2 or b in particle_like or any(b.startswith(x) for x in ("으로", "에서", "에게", "로서")):
            continue
        joined = a + b
        if joined in tokset or any(t.startswith(joined) and len(t) - len(joined) <= 2 for t in tokset):
            key = f"{a} {b}"
            if key not in seen:
                seen.add(key)
                warns.append(f"[검수-08] 띄어쓰기 변이 '{a} {b}' / '{joined}' — 한 표기로 통일")
    for a, b in SYNONYMS:
        if a in full and b in full:
            warns.append(f"[검수-08] 동의어 혼용 '{a}' / '{b}' — 한 용어로 통일")
    # 지문-보기 용어 괴리(보기의 어간이 지문엔 더 긴 꼴로만 있음: 상대/상대방)
    psq = squash(v["passage"])
    ptoks = stems(v["passage"])
    gaps = []
    for st in v["statements"]:
        for s in stems(st):
            if s in psq or len(s) < 2 or s in STOP:
                continue
            longer = [p for p in ptoks if p.startswith(s) and 1 <= len(p) - len(s) <= 2]
            if longer:
                gaps.append(f"보기 '{s}' / 지문 '{longer[0]}'")
    for g in sorted(set(gaps))[:3]:
        warns.append(f"[검수-08] 지문-보기 용어 대응 어긋남: {g} — 판정 논리가 느슨한 문항일수록 표현 대응을 맞춘다(C)")
    return [], warns


def rv09_comment(v):
    warns = []
    paras = [p for p in v["comment"] if str(p).strip()]
    if paras and PROVENANCE.match(str(paras[0]).strip()):
        paras = paras[1:]                 # 생성틀 논평 첫 문단(출처 문장)은 형식 검사에서 뺀다
    body = " ".join(paras).strip()
    if not body:
        return [], warns
    title = (v["comment_title"] or "").strip()
    if not title:
        warns.append("[검수-09] 논평 제목 없음 — 마감본은 명사구 제목(예: '성립·허용·효과의 순서') + 1~2문장")
    else:
        if len(squash(title)) > 15:
            warns.append(f"[검수-09] 논평 제목이 긺({len(squash(title))}자) — 12자 이내 명사구")
        if IMPERATIVE_TITLE.search(title) or title.endswith("라"):
            warns.append(f"[검수-09] 논평 제목이 명령문 '{title}' — 풀이 요령을 제목에 노출하지 않는다(마감본은 개념 명사구로 교체)")
        tkeys = sorted(stems(title))
        if tkeys and not any(t in body for t in tkeys):
            warns.append(f"[검수-09] 논평 제목 핵심어 {tkeys}가 본문에 없음 — 제목·본문 불일치")
    n_sent = len(sentences(body)) or 1
    if n_sent > 3 or len(squash(body)) > 220:
        warns.append(f"[검수-09] 논평 {n_sent}문장·{len(squash(body))}자 — 마감본 관행은 1~2문장(55~130자): 갈리는 지점·실수하기 쉬운 보기만")
    if GUIDE_TONE.search(body):
        warns.append("[검수-09] 논평이 안내·명령투('~십시오', '~시기 바랍니다') — '~문항입니다 / ~해야 합니다' 서술로")
    if re.search(r"정답[은이]?\s*[①-⑤]", body):
        warns.append("[검수-09] 논평에 정답 번호 — 논평은 정답을 적지 않는다")
    return [], warns


def rv10_explanation_form(v):
    """해설 형식 — 길이와 '위치 표지 대신 논리'(v2: 근거가 어디에 있는지는 쓰지 않는다. 조건→적용→결론).
    위치 표지 자체는 전 과목 공용 `core/explanations.py`가 오류로 잡는다; 여기서는 × 해설이 지문의 어느 조건이 어긋나는지를 내용으로 말하는지 본다."""
    warns = []
    has_law = any(k in LAW_KINDS for k, _, _ in v["blocks"])
    for k, (mark, ex) in enumerate(v["judgments"]):
        tag = HEADS[k] if v["statements"] else CIRCLED[k] if k < 5 else str(k + 1)
        n = len(squash(ex))
        if n > 350 and not v["calculations"]:
            warns.append(f"[검수-10] {tag} 해설 {n}자 — 마감본은 보기당 70~170자(결론과 결정적 논리만). 오류 경로·교훈 부연은 뺀다")
        if has_law and mark == "×" and not re.search(r"요건|효과|예외|단서|기한|기간|의무|금지|허용|권한|책임|충족|해당|위반|적용|성립|무효|취소|효력|불가|없으므로|않으므로|아니므로", ex):
            warns.append(f"[검수-10] {tag} × 판정 해설이 어느 요건·효과가 어긋나는지를 말하지 않음 — 규정의 조건을 자기 문장으로 말하고 보기의 사실에 적용한다(조문 번호·위치 표지가 아니라 논리로)")
    return [], warns


def rv11_level(v):
    warns = []
    lv = v["level"]
    if not lv:
        return [], warns
    rel = sum(1 for s in sentences(v["passage"]) if RELATION.search(s))
    calc = len(v["calculations"])
    if lv <= 2 and (calc >= 3 or rel >= 3):
        warns.append(f"[검수-11] 난이도 ★{lv}인데 관계식 {rel}문장·계산 {calc}건 — 대입 단계가 많은 문항은 검수 3조가 ★4를 요구했다. 상향 검토")
    has_law = any(k in LAW_KINDS for k, _, _ in v["blocks"])
    if lv >= 4 and has_law and v["statements"] and all(ASSUME.search(s) for s in v["statements"]) and not calc:
        warns.append(f"[검수-11] 난이도 ★{lv} — 가정형 보기로 규정을 적용하는 문항은 마감본에서 ★3 이하로 조정됨. AI 초안은 한 단계 과대평가 경향")
    return [], warns


def rv12_load(v):
    warns = []
    rel = sum(1 for s in sentences(v["passage"]) if RELATION.search(s))
    if rel >= 3 and v["area"] in ("과학기술", "사회"):
        warns.append(f"[검수-12] 관계식·수식 문장 {rel}개 — 기출 과학·사회 지문보다 수학적 추론이 많다는 지적 유형. 보기 하나는 계산 없는 조건 판정형으로")
    calc = v["calculations"]
    if len(calc) >= 6:
        warns.append(f"[검수-12] 계산 {len(calc)}건 — 모든 계산을 다 해야만 풀리는지 확인. 직관적 수치로 일부 보기는 계산 없이 갈리게")
    for expr, expected in calc:
        if re.search(r"/\s*\(?\s*1\.\d+\s*\)?\s*/\s*\(?\s*1\.\d+", expr) or re.search(r"/\s*\(\s*1\.\d+\s*\*\s*1\.\d+\s*\)", expr):
            warns.append(f"[검수-12] 같은 소수로 두 번 나누는 계산 '{expr[:30]}' — '252를 두 번 나누는 계산은 과합니다'. 수치를 바꿔 한 번에 떨어지게")
        try:
            val = Fraction(str(expected))
            if val.denominator not in (1, 2, 4, 5, 8, 10, 20, 25, 50, 100):
                warns.append(f"[검수-12] 계산 결과 {expected}가 간단한 수로 떨어지지 않음 — 수치 재설계 검토")
        except (ValueError, ZeroDivisionError):
            pass
    if len(squash(v["passage"])) > 1000 and v["area"] == "과학기술":
        warns.append(f"[검수-12] 과학기술 지문 {len(squash(v['passage']))}자 — 정보량 과다 지적 유형(보기에 쓰이지 않는 설명을 먼저 뺀다)")
    return [], warns


def load_lexicon(path=LEXICON_PATH):
    if not LEXICON_ENABLED:
        return []
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))["entries"]
    except (OSError, KeyError, ValueError):
        return []


def rv13_lexicon(v, entries=None):
    warns = []
    entries = load_lexicon() if entries is None else entries
    text = _public(v)
    hits = []
    for e in entries:
        draft = e["초안"]
        if draft in text and e["마감"] not in text.replace(draft, ""):
            hits.append(f"'{draft}'→'{e['마감']}'")
    if hits:
        warns.append(f"[검수-13] 구어·풀어쓰기 표현 {len(hits)}곳 — 마감본 격식 어휘로: " + ", ".join(hits[:6]) + (" …" if len(hits) > 6 else ""))
    return [], warns


CHECKS = [rv01_explanation_sync, rv02_undated_assumption, rv03_unused_rules, rv04_bypass, rv05_new_concepts,
          rv06_undetermined_as_false, rv07_option_pattern, rv08_notation, rv09_comment, rv10_explanation_form,
          rv11_level, rv12_load, rv13_lexicon]


def run(view: dict, *, quotes=True) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    if "__TODO" in json.dumps(view, ensure_ascii=False):
        return errs, warns
    for fn in CHECKS:
        e, w = fn(view, quotes=quotes) if fn is rv01_explanation_sync else fn(view)
        errs += e
        warns += w
    return errs, warns


def check_item_model(item, *, skip_quotes=True):
    """트랙 Item용. core/check.py가 따옴표 인용 검사를 이미 하므로 기본은 생략."""
    return run(view_from_item(item), quotes=not skip_quotes)


def check_manuscript_item(q: dict):
    return run(view_from_manuscript(q))


if __name__ == "__main__":
    import sys
    m = json.load(open(sys.argv[1], encoding="utf-8"))
    items = m["문항"] if isinstance(m, dict) and "문항" in m else [m]
    total = 0
    for i, q in enumerate(items, 1):
        e, w = check_manuscript_item(q)
        if e or w:
            print(f"── {q.get('id', i)}")
            for x in e:
                print("  오류:", x)
            for x in w:
                print("  경고:", x)
        total += len(e)
    sys.exit(1 if total else 0)
