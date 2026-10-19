"""Optional, read-only comparison checks for explicitly supplied misread paths."""
from __future__ import annotations

import hashlib
import json
import operator
from pathlib import Path
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import Draft, Item
from .validation import arithmetic


Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Expression = Annotated[str, Field(min_length=1, max_length=250, pattern=r"\S")]
Operator = Literal["==", "!=", "<", "<=", ">", ">="]
OPERATORS = {"==": operator.eq, "!=": operator.ne, "<": operator.lt,
             "<=": operator.le, ">": operator.gt, ">=": operator.ge}


class SidecarModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Comparison(SidecarModel):
    left: Expression
    operator: Operator
    right: Expression


class Check(SidecarModel):
    item_id: Text
    target: Text
    statement_text: Text
    source_locator: Text
    misread_description: Text
    normal: Comparison
    misread: Comparison


class Sidecar(SidecarModel):
    candidate_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    checks: list[Check] = Field(min_length=1)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key: " + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError("non-finite JSON number: " + value)


def _load(raw: bytes, label: str):
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError(f"invalid {label} JSON: {exc}") from exc


def _statement_binding(item: Item, check: Check) -> dict:
    if check.target in {"1", "2", "3", "4", "5"}:
        option = next(o for o in item.options if str(o.number) == check.target)
        if check.statement_text != option.text:
            raise ValueError("statement_text does not exactly match the target option")
        return {"field": "options", "number": option.number, "target_link": "option_number"}
    matches = [i for i, text in enumerate(item.statements) if text == check.statement_text]
    if len(matches) != 1:
        raise ValueError("statement_text must exactly match one candidate statement")
    # Only recognize an explicit label and delimiter, never interpret the claim.
    marker = re.match(r"^\s*([ㄱ-ㅎA-Za-z])\s*[.)．：:、]\s*", check.statement_text)
    target_link = "declared_only"
    if marker and re.fullmatch(r"[ㄱ-ㅎA-Za-z]", check.target):
        if marker[1] != check.target:
            raise ValueError("statement label does not match target")
        target_link = "explicit_label"
    return {"field": "statements", "index": matches[0], "target_link": target_link}


def _compare(comparison: Comparison, context: str) -> dict:
    values = {}
    for side in ("left", "right"):
        try:
            values[side] = arithmetic(getattr(comparison, side))
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, RecursionError) as exc:
            raise ValueError(f"{context}.{side}: invalid arithmetic expression ({exc})") from exc
    return {**comparison.model_dump(), "left_exact": str(values["left"]),
            "right_exact": str(values["right"]),
            "truth": OPERATORS[comparison.operator](values["left"], values["right"])}


def check_distractors(candidate_path: Path, sidecar_path: Path) -> dict:
    """Check a byte-bound sidecar without changing any file or review state."""
    candidate_path, sidecar_path = Path(candidate_path), Path(sidecar_path)
    try:
        candidate_raw, sidecar_raw = candidate_path.read_bytes(), sidecar_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read distractor-check input: {exc}") from exc
    candidate_sha = hashlib.sha256(candidate_raw).hexdigest()
    sidecar = Sidecar.model_validate(_load(sidecar_raw, "sidecar"))
    if sidecar.candidate_sha256 != candidate_sha:
        raise ValueError("candidate_sha256 mismatch: sidecar is not bound to these candidate bytes")
    draft = Draft.model_validate(_load(candidate_raw, "candidate"), strict=True)
    results = []
    for index, check in enumerate(sidecar.checks):
        context = f"checks[{index}] ({check.item_id}, target {check.target})"
        items = [item for item in draft.items if item.id == check.item_id]
        if len(items) != 1:
            raise ValueError(f"{context}: item_id must match exactly one candidate item")
        item = items[0]
        judgments = [judgment for judgment in item.judgments if judgment.target == check.target]
        if len(judgments) != 1:
            raise ValueError(f"{context}: target must match exactly one candidate judgment")
        try:
            binding = _statement_binding(item, check)
        except ValueError as exc:
            raise ValueError(f"{context}: {exc}") from exc
        normal = _compare(check.normal, context + ".normal")
        misread = _compare(check.misread, context + ".misread")
        verdict = judgments[0].verdict
        authored_truth = {"참": True, "거짓": False, "판단불가": None}[verdict]
        matches = None if authored_truth is None else normal["truth"] == authored_truth
        results.append({"index": index, "item_id": check.item_id, "target": check.target,
                        "statement_text": check.statement_text, "statement_binding": binding,
                        "source_locator": check.source_locator,
                        "misread_description": check.misread_description,
                        "normal": normal, "misread": misread,
                        "truth_changed": normal["truth"] != misread["truth"],
                        "authored_verdict": verdict, "authored_truth": authored_truth,
                        "normal_matches_authored_verdict": matches,
                        "authored_verdict_comparison": "not_boolean" if matches is None else
                        ("match" if matches else "mismatch")})
    return {"kind": "distractor_comparison_check",
            "candidate_path": str(candidate_path.absolute()), "candidate_sha256": candidate_sha,
            "sidecar_path": str(sidecar_path.absolute()),
            "sidecar_sha256": hashlib.sha256(sidecar_raw).hexdigest(),
            "scope": "명시한 정상식과 한 오독식의 비교 진위 변화만 계산한 선택 검토 보조지",
            "limitations": [
                "최종 정답·오답 개연성·원자료 전사 정확성·품질 승인에 대한 증명이 아니다.",
                "source_locator와 오독 설명은 작성자 기록이며 도구가 원자료와 대조하지 않는다.",
                "선지·보기와 비교식의 의미 대응은 사람이 검토한다. 비교식을 출제 정답으로 강제하지 않는다.",
                "declared_only인 보기 target 연결은 명시 라벨로 확인되지 않았으므로 사람이 확인한다.",
                "판단불가는 bool로 변환하지 않으며 출제 판정과의 일치 여부는 null이다.",
            ], "checks": results}
