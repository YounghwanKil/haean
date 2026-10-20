"""Explicit, immutable revision requests for an already reviewed exam version.

A request is an instruction to revisit a candidate, never a finding, score or
expert approval. Original run files and the feedback ledger are read only.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .models import Brief, Draft
from .resume_selection import selected_slots


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": _sha(path)}


def _build(previous, *, slots, text, reviewer, origin, severity):
    from .exam_resume import _selection_preflight, seed_from
    from .full_exam import load_plan
    from .revision_feedback import _draft_sha, load_revision_feedback

    if any(not isinstance(value, str) or not value.strip() for value in (text, reviewer)):
        raise ValueError("수정 요청 원문과 요청자를 입력하세요")
    if origin not in {"human", "model", "unknown"} or severity not in {"A", "B", "C"}:
        raise ValueError("수정 요청 origin 또는 severity 형식 오류")
    previous = Path(previous).resolve()
    production = _read(previous / "production.json")
    plan = load_plan(previous / "plan.json")
    jobs = production["jobs"]
    selected = selected_slots(plan, jobs, slots)
    if selected is None:
        raise ValueError("수정 요청은 전체 묶음의 slots를 명시해야 합니다")
    composition = ("composition" in production or any("composition" in job or
        (Path(job["run"]) / "composition.json").exists() or
        (Path(job["run"]) / "composition-binding.json").exists() for job in jobs))
    if composition:
        from .composition_resume import preflight
        preflight(previous)
    else:
        _selection_preflight(jobs, {slot["id"]: slot for slot in plan["slots"]})
    bundles = []
    for job in jobs:
        if not selected.intersection(job["slots"]):
            continue
        run = Path(job["run"]).resolve()
        state = _read(run / "status.json")
        if state.get("state") not in {"awaiting_human_review", "needs_revision"}:
            raise ValueError("수정 요청에는 검토가 저장된 현재 후보가 필요합니다")
        candidate = Draft.model_validate_json((run / "candidate.json").read_text())
        brief = Brief.model_validate_json((run / "brief.json").read_text())
        if brief.exam != plan["exam"] or brief.subject != plan["subject"] or brief.count != len(job["ids"]):
            raise ValueError("수정 요청 후보의 시험·과목·문항 수 불일치")
        seed, review, seed_path = seed_from(run)
        if (seed is None or review is None or seed_path.name == "inherited-draft.json"
                or _draft_sha(seed) != _draft_sha(candidate)):
            raise ValueError("수정 요청 candidate와 검토된 최신 초안 불일치")
        if state.get("candidate_sha256") != _sha(run / "candidate.json"):
            raise ValueError("수정 요청 candidate 검토 해시 불일치")
        revision = int(seed_path.stem.split("-r")[1])
        if state.get("revision") is not None and (type(state["revision"]) is not int or state["revision"] != revision):
            raise ValueError("수정 요청 검토 revision 불일치")
        if not isinstance(review, dict) or not isinstance(review.get("errors"), list):
            raise ValueError("수정 요청 최신 검토 원본 형식 오류")
        if [item.id for item in candidate.items] != job["ids"]:
            raise ValueError("수정 요청 후보 ID·순서 불일치")
        # Read and validate the complete matching local opinion before binding it.
        load_revision_feedback(run, candidate, _inherit=False)
        feedback = run.parent / "feedback.jsonl"
        bundles.append({"run": str(run), "ids": job["ids"], "slots": job["slots"],
            "candidate": _ref(run / "candidate.json"), "brief": _ref(run / "brief.json"),
            "context": _ref(run / "context.json"), "draft": _ref(seed_path),
            "review": _ref(seed_path.with_name(seed_path.name.replace("draft-", "review-"))),
            "inputs": {str(path): _sha(path) for path in sorted(run.glob("*.json"))},
            "feedback": {"path": str(feedback), "sha256": _sha(feedback) if feedback.exists() else None}})
    return {"schema_version": 1, "intent": "request_revision", "previous": str(previous),
        "exam": plan["exam"], "subject": plan["subject"], "selected_slots": sorted(selected),
        "source_exam": {name: _ref(previous / name) for name in ("plan.json", "production.json")},
        "bundles": bundles, "text": text, "reviewer": reviewer, "origin": origin,
        "severity": severity, "expert_verified": False}


def create_request(previous, out, *, slots, text, reviewer, origin, severity="C"):
    """Write a new request, without modifying or approving the source exam."""
    try:
        packet = _build(previous, slots=slots, text=text, reviewer=reviewer, origin=origin, severity=severity)
        out = Path(out).resolve()
        if out.exists():
            raise ValueError("새 수정 요청 파일 경로가 필요합니다")
        jobs = _read(Path(packet["previous"]) / "production.json")["jobs"]
        protected = [Path(packet["previous"]), *(Path(job["run"]).resolve() for job in jobs)]
        ledgers = {Path(job["run"]).resolve().parent / "feedback.jsonl" for job in jobs}
        if any(out == root or out.is_relative_to(root) for root in protected) or out in ledgers:
            raise ValueError("수정 요청은 원 회차·run 및 원본 feedback.jsonl 밖에 저장해야 합니다")
        packet["created_at"] = datetime.now(timezone.utc).isoformat()
        out.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also protects against a concurrently created request.
        with out.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
        return packet
    except (OSError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"수정 요청 입력 불완전: {exc}") from exc


def load_request(path):
    """Revalidate source files as well as the request's exact captured contents."""
    try:
        path = Path(path).resolve()
        packet = _read(path)
        if (not isinstance(packet, dict) or packet.get("schema_version") != 1
                or packet.get("intent") != "request_revision"
                or not isinstance(packet.get("created_at"), str) or not packet["created_at"]):
            raise ValueError("수정 요청 패킷 형식 오류")
        expected = _build(packet["previous"], slots=packet["selected_slots"], text=packet["text"],
            reviewer=packet["reviewer"], origin=packet["origin"], severity=packet["severity"])
        if {key: value for key, value in packet.items() if key != "created_at"} != expected:
            raise ValueError("수정 요청의 원본·해시·배정 연결 변경 또는 불일치")
        return {"path": str(path), "sha256": _sha(path), "packet": packet}
    except (OSError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"수정 요청 입력 불완전: {exc}") from exc


def bind_requests(previous, requested, revision_requests):
    """Return one validated request per source bundle, before output exists."""
    if not isinstance(revision_requests, (tuple, list)):
        raise ValueError("revision_requests는 수정 요청 경로 목록이어야 합니다")
    if not revision_requests:
        return {}
    if requested is None:
        raise ValueError("revision_requests에는 slots 선택을 함께 지정해야 합니다")
    previous = str(Path(previous).resolve())
    bindings = {}
    for path in revision_requests:
        ref = load_request(path)
        packet = ref["packet"]
        if packet["previous"] != previous:
            raise ValueError("다른 회차의 수정 요청은 적용할 수 없습니다")
        if not set(packet["selected_slots"]).issubset(requested):
            raise ValueError("수정 요청 범위가 선택한 slots 밖에 있습니다")
        for bundle in packet["bundles"]:
            if bundle["run"] in bindings:
                raise ValueError("동일 묶음에 대한 수정 요청 중복")
            bindings[bundle["run"]] = ref
    return bindings
