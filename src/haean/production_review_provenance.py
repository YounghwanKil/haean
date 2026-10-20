"""Read-only, item-scoped review provenance for saved production runs.

A status flag and a hash of its own candidate are claims, not review evidence.
This reader never creates bindings or repairs legacy review records.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import BlindReview, Draft, EditorialReview
from .revision_feedback import load_revision_feedback, requires_revision


MAX_PARENT_DEPTH = 20


class EvidenceError(ValueError):
    def __init__(self, reason, detail=""):
        self.reason, self.detail = reason, detail
        super().__init__(detail or reason)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path, kind):
    try:
        value = json.loads(path.read_bytes())
    except FileNotFoundError as exc:
        raise EvidenceError(f"missing_{kind}", str(path)) from exc
    except (OSError, ValueError) as exc:
        raise EvidenceError(f"malformed_{kind}", str(exc)) from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"malformed_{kind}", str(path))
    return value


def _draft(path):
    value = _json(path, "candidate" if path.name == "candidate.json" else "draft")
    try:
        draft = Draft.model_validate(value)
    except ValueError as exc:
        raise EvidenceError("malformed_candidate" if path.name == "candidate.json" else "malformed_draft", str(exc)) from exc
    ids = [item.id for item in draft.items]
    if len(ids) != len(set(ids)) or any(not item_id.strip() for item_id in ids):
        raise EvidenceError("duplicate_or_empty_item_id", str(path))
    return draft, {item.id: item.model_dump(mode="json") for item in draft.items}


def _parent_path(value, run):
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError("malformed_parent", str(run / "status.json"))
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    local = (run / path).resolve()
    return local if local.exists() else path.resolve()


def _pair(record, draft):
    """Validate full review structure; retain issue/error scope for each item."""
    try:
        blind = BlindReview.model_validate(record["blind"])
        editor = EditorialReview.model_validate(record["editorial"])
    except (ValueError, KeyError, TypeError) as exc:
        raise EvidenceError("malformed_review", str(exc)) from exc
    expected = {item.id for item in draft.items}
    if (len(blind.solutions) != len(expected)
            or {solution.item_id for solution in blind.solutions} != expected
            or any(not _issue_ids(issue.item_id) <= expected or len(_issue_ids(issue.item_id)) != len(issue.item_id.split(","))
                   for issue in [*blind.issues, *editor.issues])):
        raise EvidenceError("review_item_ids_mismatch")
    errors = record.get("errors")
    if not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
        raise EvidenceError("malformed_review_errors")
    return blind, editor, errors


def _issue_ids(value):
    return {part.strip() for part in value.split(",")}


def _item_gate(item_id, item, pair):
    blind, editor, saved_errors = pair
    solution = next(solution for solution in blind.solutions if solution.item_id == item_id)
    issues = [issue.model_dump() for issue in [*blind.issues, *editor.issues] if item_id in _issue_ids(issue.item_id)]
    # Pipeline errors with a precise known ID prefix apply only to that item.
    # Unscoped mechanical errors cannot safely be attributed to another item.
    ids = {solution.item_id for solution in blind.solutions}
    errors = []
    for error in saved_errors:
        prefix, separator, _ = error.partition(":")
        scoped_ids = _issue_ids(prefix)
        if separator and scoped_ids <= ids and item_id not in scoped_ids:
            continue
        errors.append(error)
    if not solution.uniquely_answerable or solution.answer != item["answer"] or solution.missing_conditions:
        errors.append("독립 풀이 불일치·조건 부족")
    if any(issue["severity"] in {"A", "B"} for issue in issues):
        errors.append("미해결 A/B 검토 의견")
    return {"review_passed": not errors, "errors": errors, "issues": issues}


def _manual(run, record, draft, candidate_sha):
    from .review_evidence import load_bound_review, verify_editor_blind_pair
    if not record.get("candidate_sha256") or not isinstance(record.get("evidence"), dict):
        raise EvidenceError("legacy_record_found", "검토 당시 candidate 해시·binding이 없는 기록")
    if record["candidate_sha256"] != candidate_sha:
        raise EvidenceError("manual_candidate_hash_mismatch")
    pair = _pair(record, draft)
    try:
        evidence = record["evidence"]
        blind_path = Path(evidence["editorial"]["input_binding"]["blind_review"]["snapshot_path"])
        blind, blind_receipt = load_bound_review(blind_path, run, "blind")
        digest = evidence["editorial"]["result_file_sha256"]
        if "source_paths" in record:
            paths = record["source_paths"]
            value = paths.get("editorial") if isinstance(paths, dict) else None
            if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
                raise EvidenceError("manual_source_path_invalid", "편집 검토 원본의 절대 경로 필요")
            editor_path = Path(value)
            if not editor_path.is_file():
                raise EvidenceError("manual_result_file_missing", str(editor_path))
            if _sha(editor_path) != digest:
                raise EvidenceError("manual_result_file_hash_mismatch", str(editor_path))
        else:
            # Older receipts lack the original path. Only discover an existing
            # local envelope by its saved digest; do not synthesize a binding.
            candidates = [path for path in run.glob("*.json") if _sha(path) == digest]
            if not candidates:
                raise EvidenceError("manual_result_file_missing", "편집 검토 envelope 원본을 확인할 수 없음")
            editor_path = candidates[0]
        editor, editor_receipt = load_bound_review(editor_path, run, "editor")
        verify_editor_blind_pair(run, blind_path, blind_receipt, editor_path, editor_receipt)
        if (blind.model_dump() != pair[0].model_dump() or editor.model_dump() != pair[1].model_dump()
                or blind_receipt != evidence["blind"] or editor_receipt != evidence["editorial"]):
            raise EvidenceError("manual_result_receipt_mismatch")
    except EvidenceError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        raise EvidenceError("manual_binding_invalid", str(exc)) from exc
    return pair, {"source_kind": "manual", "assurance": {
        "blind": blind_receipt["assurance"], "editorial": editor_receipt["assurance"]},
        "result_paths": [str(blind_path), str(editor_path)]}


def _feedback(run, draft, item_id):
    packet = load_revision_feedback(run, draft.model_dump())
    if packet is None:
        return False
    selected = []
    for record in packet["records"]:
        entry = record["entry"]
        if entry.get("item_id") == item_id or item_id in entry.get("item_ids", []):
            selected.append(record)
    return bool(selected and requires_revision({**packet, "records": selected}))


def _resolve_item(run, current_item, *, max_depth):
    item_id = current_item["id"]
    result = {"item_id": item_id, "verified": False, "review_passed": False,
              "origin": None, "source_kind": None, "assurance": None,
              "source_run": None, "source_path": None, "source_revision": None,
              "chain": [], "records_found": [], "reason": "review_not_found",
              "errors": [], "issues": [], "pending_revision_feedback": False,
              "feedback_error": None}
    seen = set()
    for depth in range(max_depth + 1):
        if run in seen:
            result["reason"] = "parent_cycle"
            break
        seen.add(run)
        node = {"run": str(run), "candidate_path": str(run / "candidate.json"),
                "item_content_matches": False, "candidate_hash_matches_status": False}
        result["chain"].append(node)
        try:
            draft, items = _draft(run / "candidate.json")
            if item_id not in items:
                raise EvidenceError("item_id_missing")
            if items[item_id] != current_item:
                raise EvidenceError("item_content_changed")
            node["item_content_matches"] = True
            node["candidate_sha256"] = _sha(run / "candidate.json")
            # Preserve discovery even if status is absent, stale or malformed.
            found = sorted(run.glob("review-r*.json")) + ([run / "manual-review.json"] if (run / "manual-review.json").exists() else [])
            result["records_found"].extend(str(path) for path in found)
            state = _json(run / "status.json", "status")
            node["candidate_hash_matches_status"] = state.get("candidate_sha256") == node["candidate_sha256"]
            if not node["candidate_hash_matches_status"]:
                raise EvidenceError("candidate_hash_mismatch")
            if state.get("state") not in {"awaiting_human_review", "needs_revision"}:
                raise EvidenceError("review_state_unverified", str(state.get("state")))
            try:
                if _feedback(run, draft, item_id):
                    result["pending_revision_feedback"] = True
            except (OSError, ValueError, TypeError, KeyError) as exc:
                result["pending_revision_feedback"] = None
                result["feedback_error"] = f"{type(exc).__name__}: {exc}"
            revision = state.get("revision")
            if type(revision) is int and revision >= 0:
                source_path = run / f"review-r{revision}.json"
                result.update(origin="direct" if depth == 0 else "inherited", source_kind="automatic",
                              source_run=str(run), source_path=str(source_path), source_revision=revision)
                if source_path.exists():
                    record = _json(source_path, "review")
                    if type(record.get("revision")) is not int or record["revision"] != revision:
                        raise EvidenceError("review_revision_mismatch")
                    review_draft, reviewed_items = _draft(run / f"draft-r{revision}.json")
                    if set(reviewed_items) != set(items):
                        raise EvidenceError("review_item_ids_mismatch")
                    if reviewed_items[item_id] != current_item:
                        raise EvidenceError("reviewed_item_content_changed")
                    pair = _pair(record, review_draft)
                    metadata = {"source_kind": "automatic", "assurance": "saved-pipeline-review; model execution not verified"}
                elif state.get("parent_review_run") and not found and not any(run.glob("draft-r*.json")):
                    # Assembled split views retain the parent's revision number
                    # but never copy its draft/review files. Their parent is the
                    # evidence source, after every hop's whole-item comparison.
                    pair = None
                    result.update(origin=None, source_kind=None, source_run=None,
                                  source_path=None, source_revision=None)
                else:
                    raise EvidenceError("missing_review", str(source_path))
            else:
                pair = None
            if pair is None and (run / "manual-review.json").exists():
                source_path = run / "manual-review.json"
                record = _json(source_path, "review")
                result.update(source_run=str(run), source_path=str(source_path), source_kind="manual")
                pair, metadata = _manual(run, record, draft, node["candidate_sha256"])
                revision = None
            if pair is not None:
                result.update(verified=True, reason=None, origin="direct" if depth == 0 else "inherited",
                              source_run=str(run), source_path=str(source_path), source_revision=revision,
                              source_sha256=_sha(source_path),
                              **metadata, **_item_gate(item_id, current_item, pair))
                break
            if found:
                raise EvidenceError("review_revision_missing", "현 run 검토 기록의 revision 연결을 확인할 수 없음")
            parent = state.get("parent_review_run")
            if parent is None:
                result["reason"] = "review_revision_missing" if found else "review_not_found"
                break
            if depth == max_depth:
                raise EvidenceError("parent_depth_limit")
            run = _parent_path(parent, run)
        except EvidenceError as exc:
            result["reason"], result["detail"] = exc.reason, exc.detail
            if exc.reason == "legacy_record_found":
                result.update(source_kind="legacy", assurance="unbound legacy record; not a verified review",
                              origin="direct" if depth == 0 else "inherited")
            break
        except (OSError, ValueError, TypeError, KeyError) as exc:
            result.update(reason="unreadable_evidence", detail=f"{type(exc).__name__}: {exc}")
            break
    return result


def review_provenance(run, *, max_depth=MAX_PARENT_DEPTH):
    """Return current-item evidence, not a claim that the whole parent bundle passed."""
    run = Path(run).resolve()
    try:
        _, items = _draft(run / "candidate.json")
    except EvidenceError as exc:
        return {"items": [], "error": exc.reason, "detail": exc.detail}
    return {"items": [_resolve_item(run, item, max_depth=max_depth) for item in items.values()],
            "error": None, "scope": "current items only; no human approval or model execution attestation"}
