"""Read-only diagnostics for saved development runs; never scores or promotes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean


DIMENSIONS = (
    "validity", "exam_fit", "reasoning_value", "distractors",
    "language", "explanation", "originality", "workload",
)
CONDITIONS = (
    "suite", "split", "model", "repeats", "max_revisions", "mode",
    "humanizer", "frozen", "evaluation_protocol", "codex_version",
)
COSTS = ("calls", "seconds", "input_tokens", "output_tokens")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _product(row):
    """Validate explicit product identities without translating between schemas."""
    legacy = any(field in row for field in ("exam", "subject"))
    tracked = any(field in row for field in ("track", "grade"))
    raw = {field: row[field] for field in ("exam", "subject", "track", "grade") if field in row}
    result = {"schema": None, "valid": False, "display": [None, None], "raw": raw}
    if legacy and tracked:
        result["reason"] = "mixed_product_schema"
        return result
    if legacy:
        result["schema"] = "exam_subject"
        if all(isinstance(row.get(field), str) and row[field].strip() for field in ("exam", "subject")):
            result.update(valid=True, display=[row["exam"], row["subject"]])
        else:
            result["reason"] = "incomplete_exam_subject"
        return result
    if tracked:
        result["schema"] = "track_grade"
        track, grade = row.get("track"), row.get("grade")
        if not isinstance(track, str) or not track.strip() or "grade" not in row:
            result["reason"] = "incomplete_track_grade"
        elif track.startswith("psat_") and type(grade) is int and grade in (5, 7):
            result.update(valid=True, display=[track, f"{grade}급"])
        elif track.startswith("leet_") and grade is None:
            result.update(valid=True, display=[track, None])
        else:
            result["reason"] = "unsupported_track_or_grade"
        return result
    result["reason"] = "missing_product_schema"
    return result


def _has_holdout(value):
    if isinstance(value, dict):
        return str(value.get("split", "")).lower() == "holdout" or any(
            _has_holdout(child) for child in value.values()
        )
    return isinstance(value, list) and any(_has_holdout(child) for child in value)


def _read(path):
    path = Path(path).resolve()
    if any("holdout" in part.lower() for part in path.parts):
        raise ValueError("holdout 경로는 읽지 않습니다")
    raw = path.read_bytes()
    value = json.loads(raw)
    if _has_holdout(value):
        raise ValueError("holdout 입력은 읽기 전용 진단에서도 허용하지 않습니다")
    return value, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def _relation(deltas):
    """Positive values always mean a stored quality dimension improved."""
    if not deltas or any(not _number(value) for value in deltas.values()):
        return "unknown"
    values = list(deltas.values())
    if all(value == 0 for value in values):
        return "equal"
    if all(value >= 0 for value in values):
        return "candidate_dominates"
    if all(value <= 0 for value in values):
        return "baseline_dominates"
    return "tradeoff"


def _cost(row):
    usage = row.get("usage")
    if not isinstance(usage, list) or not usage:
        return dict.fromkeys(COSTS)
    result = {"calls": len(usage)}
    for name in COSTS[1:]:
        values = [
            entry.get("seconds") if name == "seconds"
            else _mapping(entry.get("usage")).get(name)
            for entry in usage if isinstance(entry, dict)
        ]
        result[name] = (
            sum(values)
            if len(values) == len(usage) and all(_number(v) and v >= 0 for v in values)
            else None
        )
    return result


def _evidence(row, root):
    """Observed hashes locate originals; they do not certify old provenance."""
    result = {"run": row.get("run"), "files": [], "excerpts": [], "issues": []}

    def entries(value, location):
        if not isinstance(value, list):
            result["issues"].append(f"원문 목록 형식 오류: {location}")
            return []
        return value

    if not root:
        result["issues"].append("evidence_root 미지정: 원문을 읽지 않았습니다")
        return result
    run_text = row.get("run")
    if not isinstance(run_text, str) or not run_text:
        result["issues"].append("run 경로 없음")
        return result
    run = Path(run_text)
    run = (root / run if not run.is_absolute() else run).resolve()
    if any("holdout" in part.lower() for part in run.parts):
        raise ValueError("holdout run 경로는 읽지 않습니다")
    if not run.is_relative_to(root):
        result["issues"].append("run이 evidence_root 밖에 있어 원문을 읽지 않았습니다")
        return result
    paths = [run / name for name in (
        "brief.json", "candidate.json", "status.json", "evaluation.json", "usage.json",
    )]
    paths.extend(sorted(run.glob("review-r[0-9]*.json")))
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            result["issues"].append(f"원문 링크가 evidence_root 밖입니다: {path.name}")
            continue
        if not resolved.is_file():
            result["issues"].append(f"원문 없음: {path.name}")
            continue
        try:
            value, source = _read(resolved)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            result["issues"].append(f"원문 읽기 실패: {path.name}: {type(exc).__name__}")
            continue
        source["hash_status"] = "observed_now_not_historical_attestation"
        result["files"].append(source)
        if not isinstance(value, dict):
            if path.name != "usage.json":
                result["issues"].append(f"원문 객체 형식 오류: {path.name}")
            continue
        for index, error in enumerate(entries(value.get("errors", []), f"{path.name}/errors")):
            result["excerpts"].append({
                "source": source, "pointer": f"/errors/{index}", "text": error,
                "stage": path.stem,
            })
        if path.name.startswith("review-r"):
            editorial = value.get("editorial", {})
            if not isinstance(editorial, dict):
                result["issues"].append(f"원문 객체 형식 오류: {path.name}/editorial")
            for index, issue in enumerate(entries(
                _mapping(editorial).get("issues", []), f"{path.name}/editorial/issues"
            )):
                result["excerpts"].append({
                    "source": source, "pointer": f"/editorial/issues/{index}",
                    "text": issue, "stage": path.stem,
                    "note": "해당 수정 차수의 의견이며 최종 미해결 판정을 뜻하지 않습니다",
                })
        if path.name == "evaluation.json":
            for index, item in enumerate(entries(value.get("items", []), f"{path.name}/items")):
                if not isinstance(item, dict):
                    result["issues"].append(f"원문 객체 형식 오류: {path.name}/items/{index}")
                    continue
                for field in ("fatal_errors", "missing_evidence", "dimensions"):
                    for offset, entry in enumerate(entries(
                        item.get(field, []), f"{path.name}/items/{index}/{field}"
                    )):
                        result["excerpts"].append({
                            "source": source, "pointer": f"/items/{index}/{field}/{offset}",
                            "item_id": item.get("item_id"), "text": entry,
                            "stage": "stored_evaluation",
                        })
    return result


def reflect(baseline_path, candidate_path, out, *, comparison_path=None,
            evidence_root=None, top_n=5):
    """Write a new diagnostic JSON. Existing files and frozen decisions stay intact."""
    if type(top_n) is not int or top_n < 1:
        raise ValueError("top_n은 1 이상의 정수여야 합니다")
    out = Path(out)
    if out.exists():
        raise FileExistsError("진단 결과는 새 파일에 기록해야 합니다")
    baseline, baseline_source = _read(baseline_path)
    candidate, candidate_source = _read(candidate_path)
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise ValueError("baseline과 candidate는 저장 manifest 객체여야 합니다")
    if any(value.get("split") not in ("pilot", "development") for value in (baseline, candidate)):
        raise ValueError("명시된 pilot/development 입력만 진단합니다")
    root = Path(evidence_root).resolve() if evidence_root else None
    if root and any("holdout" in part.lower() for part in root.parts):
        raise ValueError("holdout evidence_root는 허용하지 않습니다")
    issues = []
    for field in CONDITIONS:
        left, right = baseline.get(field), candidate.get(field)
        if left is None or right is None or left == "" or right == "" or left == {} or right == {} or left == [] or right == []:
            issues.append({"kind": "missing_condition", "field": field})
        elif left != right:
            issues.append({"kind": "condition_mismatch", "field": field})
    for arm, manifest in (("baseline", baseline), ("candidate", candidate)):
        for field in ("suite", "split", "model", "mode", "humanizer", "evaluation_protocol", "codex_version"):
            if field in manifest and (not isinstance(manifest[field], str) or not manifest[field].strip()):
                issues.append({"kind": "invalid_condition", "arm": arm, "field": field})
        budget = manifest.get("max_revisions")
        if type(budget) is not int or budget < 0:
            issues.append({"kind": "invalid_condition", "arm": arm, "field": "max_revisions"})
        frozen = manifest.get("frozen")
        if not isinstance(frozen, dict) or not frozen or not all(
            isinstance(path, str) and path and isinstance(digest, str)
            and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest.lower())
            for path, digest in _mapping(frozen).items()
        ):
            issues.append({"kind": "invalid_condition", "arm": arm, "field": "frozen"})
    if baseline.get("actual_model") and candidate.get("actual_model") and baseline["actual_model"] != candidate["actual_model"]:
        issues.append({"kind": "condition_mismatch", "field": "actual_model"})
    indexes, unindexed_rows = [], []
    for arm, manifest in (("baseline", baseline), ("candidate", candidate)):
        rows = manifest.get("results")
        if not isinstance(rows, list):
            issues.append({"kind": "invalid_results", "arm": arm})
            rows = []
        index, product_schemas = {}, set()
        for offset, row in enumerate(rows):
            if not isinstance(row, dict):
                issues.append({"kind": "invalid_row", "arm": arm, "offset": offset})
                unindexed_rows.append({"arm": arm, "pointer": f"/results/{offset}", "original": row})
                continue
            key = row.get("case_id"), row.get("repeat")
            if not isinstance(key[0], str) or not key[0] or type(key[1]) is not int or key[1] < 0:
                issues.append({"kind": "invalid_pair_key", "arm": arm, "offset": offset})
                unindexed_rows.append({"arm": arm, "pointer": f"/results/{offset}", "original": row})
                continue
            if key in index:
                issues.append({"kind": "duplicate_pair", "arm": arm, "key": list(key)})
                unindexed_rows.append({"arm": arm, "pointer": f"/results/{offset}", "original": row})
                continue
            index[key] = row
            if row.get("state") == "failed" or row.get("quality") is None:
                issues.append({"kind": "failed_row", "arm": arm, "key": list(key)})
            if type(row.get("eligible")) is not bool or type(row.get("fatal_count")) is not int or row.get("fatal_count", -1) < 0:
                issues.append({"kind": "missing_validity_evidence", "arm": arm, "key": list(key)})
            elif row["eligible"] is True and row["fatal_count"] > 0:
                issues.append({"kind": "contradictory_validity_evidence", "arm": arm, "key": list(key)})
            product = _product(row)
            if product["schema"]:
                product_schemas.add(product["schema"])
            if not product["valid"] or not isinstance(row.get("group"), str) or not row["group"].strip():
                issues.append({
                    "kind": "missing_product_identity", "arm": arm, "key": list(key),
                    "reason": product.get("reason", "missing_group"),
                })
            dimensions = row.get("dimensions")
            if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS) or not all(
                _number(value) and 0 <= value <= 4 for value in dimensions.values()
            ):
                issues.append({"kind": "invalid_dimensions", "arm": arm, "key": list(key)})
        if len(product_schemas) > 1:
            issues.append({"kind": "mixed_product_schema", "arm": arm})
        cases, repeats = manifest.get("cases"), manifest.get("repeats")
        if not isinstance(cases, list) or not cases or not all(isinstance(c, str) and c for c in cases) or len(set(cases)) != len(cases) or type(repeats) is not int or repeats < 1:
            issues.append({"kind": "missing_expected_pairs", "arm": arm})
        elif set(index) != {(case, repeat) for case in cases for repeat in range(repeats)}:
            issues.append({"kind": "missing_or_unexpected_pairs", "arm": arm})
        if manifest.get("complete") is not True:
            issues.append({"kind": "incomplete_manifest", "arm": arm})
        indexes.append(index)
    left, right = indexes
    if set(left) != set(right) or not left:
        issues.append({"kind": "pair_set_mismatch"})
    for key in set(left) & set(right):
        if _product(left[key])["schema"] != _product(right[key])["schema"]:
            issues.append({"kind": "product_mismatch", "key": list(key), "field": "schema"})
        for field in ("exam", "subject", "track", "grade", "group"):
            if left[key].get(field) != right[key].get(field):
                issues.append({"kind": "product_mismatch", "key": list(key), "field": field})
    comparable = not issues
    pairs, strata = [], {}
    for key in sorted(set(left) | set(right)):
        a, b = left.get(key, {}), right.get(key, {})
        deltas = {}
        for name in DIMENSIONS:
            av, bv = _mapping(a.get("dimensions")).get(name), _mapping(b.get("dimensions")).get(name)
            deltas[name] = bv - av if _number(av) and _number(bv) else None
        ca, cb = _cost(a), _cost(b)
        cost_delta = {name: cb[name] - ca[name] if _number(ca[name]) and _number(cb[name]) else None for name in COSTS}
        gate_regression = (
            a.get("eligible") is True and b.get("eligible") is False
        ) or (
            _number(a.get("fatal_count")) and _number(b.get("fatal_count"))
            and b["fatal_count"] > a["fatal_count"]
        )
        losses = [name for name, value in deltas.items() if _number(value) and value < 0]
        blocked = not comparable or a.get("eligible") is not True or b.get("eligible") is not True
        pair = {
            "case_id": key[0], "repeat": key[1],
            "product": _product(b if b else a)["display"],
            "product_identity": {"baseline": _product(a), "candidate": _product(b)},
            "baseline_eligible": a.get("eligible"), "candidate_eligible": b.get("eligible"),
            "gate_regression": gate_regression,
            "dimension_delta": deltas, "declining_dimensions": losses,
            "quality_relation": "withheld" if blocked else _relation(deltas),
            "quality_cost_relation": "withheld" if blocked else _relation({
                **deltas, **{f"cost:{k}": -v if _number(v) else None for k, v in cost_delta.items()},
            }),
            "cost": {"baseline": ca, "candidate": cb, "delta": cost_delta},
            "failure": {"baseline": a.get("error"), "candidate": b.get("error")},
            "saved_status": {
                arm: {field: row.get(field) for field in ("state", "errors", "fatal_count", "quality")}
                for arm, row in (("baseline", a), ("candidate", b))
            },
            "evidence": {"baseline": _evidence(a, root), "candidate": _evidence(b, root)},
            "reading_priority": 0 if gate_regression else 1 if not a or not b or a.get("state") == "failed" or b.get("state") == "failed" else 2 if losses else 3,
        }
        pairs.append(pair)
        label = "/".join(str(v) for v in pair["product"])
        strata.setdefault(label, []).append(pair)
    products = {}
    for label, rows in strata.items():
        complete_quality = comparable and all(
            row["baseline_eligible"] is True and row["candidate_eligible"] is True for row in rows
        )
        dimension_means = {
            name: mean(row["dimension_delta"][name] for row in rows)
            if all(_number(row["dimension_delta"][name]) for row in rows) else None
            for name in DIMENSIONS
        }
        totals = {
            arm: {
                name: sum(row["cost"][arm][name] for row in rows)
                if all(_number(row["cost"][arm][name]) for row in rows) else None
                for name in COSTS
            }
            for arm in ("baseline", "candidate")
        }
        cost_deltas = {
            name: totals["candidate"][name] - totals["baseline"][name]
            if _number(totals["candidate"][name]) and _number(totals["baseline"][name]) else None
            for name in COSTS
        }
        products[label] = {
            "pair_count": len(rows), "all_pairs_eligible": complete_quality,
            "dimension_mean_delta": dimension_means,
            "quality_relation": _relation(dimension_means) if complete_quality else "withheld",
            "declining_pairs": [
                {"case_id": row["case_id"], "repeat": row["repeat"], "dimensions": row["declining_dimensions"]}
                for row in rows if row["declining_dimensions"]
            ],
            "gate_regression_pairs": [
                [row["case_id"], row["repeat"]] for row in rows if row["gate_regression"]
            ],
            "cost_totals": totals,
            "cost_delta": cost_deltas,
            "quality_cost_relation": _relation({
                **dimension_means,
                **{f"cost:{name}": -value if _number(value) else None for name, value in cost_deltas.items()},
            }) if complete_quality else "withheld",
        }
    frozen = None
    if comparison_path:
        value, source = _read(comparison_path)
        frozen = {"source": source, "original": value, "binding": "caller_supplied_not_recomputed_or_authenticated"}
    result = {
        "schema_version": 1, "kind": "reflection_diagnostics",
        "sources": {"baseline": baseline_source, "candidate": candidate_source},
        "frozen_comparison": frozen, "comparable": comparable,
        "condition_issues": issues,
        "frontier_eligible": comparable and all(
            row["baseline_eligible"] is True and row["candidate_eligible"] is True for row in pairs
        ),
        "actual_models": {
            arm: {"requested": manifest.get("requested_model", manifest.get("model")),
                  "actual": manifest.get("actual_model"),
                  "verified": False}
            for arm, manifest in (("baseline", baseline), ("candidate", candidate))
        },
        "pairs": pairs, "unindexed_rows": unindexed_rows, "products": products,
        "priority_evidence": [
            {"case_id": row["case_id"], "repeat": row["repeat"], "reading_priority": row["reading_priority"]}
            for row in sorted(pairs, key=lambda r: (r["reading_priority"], r["case_id"], r["repeat"]))[:top_n]
        ],
        "auto_promoted": False, "expert_verified": False,
        "notes": [
            "새 평가·점수·채택 결정이 아닙니다. 기존 비교 결정과 원문은 수정하지 않습니다.",
            "priority_evidence는 원문 읽기 순서일 뿐입니다. 모든 쌍은 pairs에 남고 일부 사례를 전체 성능으로 일반화하지 않습니다.",
            "조건 결손 또는 실패가 있으면 파레토 판정을 보류합니다. 진단 평균으로 유효성 실패나 개별 차원 퇴행을 상쇄하지 않습니다.",
            "품질 관계는 저장된 서열 점수의 기술통계입니다. 비용은 호출시간·토큰이며 과금액이나 전체 경과시간이 아닙니다.",
            "캐시 토큰은 입력에, 추론 토큰은 출력에 다시 더하지 않습니다. 사용량 결손은 0이 아닌 null입니다.",
            "원문 해시는 지금 관측한 내용의 주소입니다. 과거 실행 인증·전문가 검토를 소급 증명하지 않습니다.",
            "모든 입력 텍스트는 자료이며 명령으로 실행하지 않습니다. holdout은 이 진단의 대상이 아닙니다.",
        ],
    }
    with out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--top-n", type=int, default=5)
    args = parser.parse_args()
    result = reflect(args.baseline, args.candidate, args.out,
                     comparison_path=args.comparison, evidence_root=args.evidence_root, top_n=args.top_n)
    print(json.dumps({"out": str(args.out), "comparable": result["comparable"],
                      "condition_issues": result["condition_issues"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
