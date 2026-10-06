from __future__ import annotations

import ast
from difflib import SequenceMatcher
from fractions import Fraction
import re

from .models import Brief, Draft, BlindReview, EditorialReview


def arithmetic(expression: str) -> Fraction:
    """Bounded arithmetic only. Never evaluate generated Python."""
    if len(expression) > 250:
        raise ValueError("Expression too long")
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 80:
        raise ValueError("Expression too complex")
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            value = Fraction(str(node.value))
            if abs(value) > 10**18:
                raise ValueError("Number too large")
            return value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return a + b
            if isinstance(node.op, ast.Sub): return a - b
            if isinstance(node.op, ast.Mult): return a * b
            if isinstance(node.op, ast.Div): return a / b
        raise ValueError("Only numbers, +, -, *, / and parentheses are allowed")
    return visit(tree.body)


def public_item(item):
    """Answer/design/reference-free payload for independent solving."""
    return {key: item.model_dump()[key] for key in
            ("id", "stem", "passage", "statements", "tables", "options", "shared_passage_id")}


def validate(draft: Draft, brief: Brief, allowed_sources: set[str]) -> list[str]:
    errors = []
    if len(draft.items) != brief.count:
        errors.append("문항 수가 요청과 다릅니다")
    ids = [i.id for i in draft.items]
    if len(set(ids)) != len(ids): errors.append("문항 ID 중복")
    if brief.shared_passage:
        if len({i.shared_passage_id for i in draft.items}) != 1 or any(not i.shared_passage_id for i in draft.items):
            errors.append("세트 공통지문 ID 불일치")
        if len({i.passage for i in draft.items}) != 1 or len({str(i.tables) for i in draft.items}) != 1:
            errors.append("세트 공통지문·표가 서로 다릅니다")
    elif any(i.shared_passage_id for i in draft.items):
        errors.append("단독 문항에 공유 지문 ID가 있습니다")
    for item in draft.items:
        prefix = item.id + ": "
        if item.subject != brief.subject or item.item_type != brief.item_type:
            errors.append(prefix + "시험 명세와 과목·유형 불일치")
        if not item.source_ids or set(item.source_ids) - allowed_sources:
            errors.append(prefix + "근거 자료 ID 누락 또는 미등록")
        targets = [j.target for j in item.judgments]
        if any(str(n) not in targets for n in range(1, 6)):
            errors.append(prefix + "1~5번 선지별 판단 누락")
        if brief.subject == "자료해석" and (not item.tables or not item.calculations):
            errors.append(prefix + "자료해석 표 또는 재계산 명세 누락")
        for calc in item.calculations:
            try:
                if arithmetic(calc.expression) != arithmetic(calc.expected):
                    errors.append(prefix + "계산 불일치: " + calc.label)
            except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
                errors.append(prefix + "계산 검증 실패: " + calc.label)
        # Direct quotations must exist in the current public question.
        public_text = " ".join([item.passage, item.stem, *item.statements, *(o.text for o in item.options)])
        for quote in re.findall(r'[“\"]([^“”\"]{10,})[”\"]', item.explanation):
            if quote not in public_text:
                errors.append(prefix + "해설 인용이 현행 문항에 없음: " + quote[:50])
    return errors


def review_gate(draft: Draft, blind: BlindReview, editorial: EditorialReview) -> list[str]:
    errors = []
    expected = {i.id for i in draft.items}
    if len(blind.solutions) != len(expected) or {s.item_id for s in blind.solutions} != expected:
        errors.append("독립 풀이 문항 누락·중복")
    for item in draft.items:
        matches = [s for s in blind.solutions if s.item_id == item.id]
        if len(matches) == 1:
            s = matches[0]
            if not s.uniquely_answerable or s.answer != item.answer or s.missing_conditions:
                errors.append(item.id + ": 독립 풀이 불일치·조건 부족")
    for issue in [*blind.issues, *editorial.issues]:
        if issue.severity in {"A", "B"}:
            errors.append(f"{issue.item_id}: {issue.severity} {issue.category}: {issue.problem}")
    return errors


def similarity(draft: Draft, references: list[dict]) -> list[dict]:
    """Lexical triage, not proof of semantic originality."""
    hits = []
    for item in draft.items:
        a = re.sub(r"\s+", "", item.passage)
        if len(a) < 40: continue
        for ref in references:
            b = re.sub(r"\s+", "", ref["text"])
            match = SequenceMatcher(None, a, b, autojunk=False).find_longest_match()
            if match.size >= 80:
                hits.append({"item_id": item.id, "source_id": ref["id"], "shared_characters": match.size})
    return hits
