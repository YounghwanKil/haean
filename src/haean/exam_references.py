"""Explicit development reference selection for a fresh legacy exam plan.

The bridge validates the live index evidence once, freezes those bytes locally,
then binds the full student/source objects through authoring_sources. It neither
infers slot matches nor certifies the quality of the user's stated application.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from .authoring_sources import _loads, _student_valid, supplied_source_ids
from .full_exam import load_plan
from .models import StrictModel
from .tracks.core.references import ReferenceIndex, _allowed_source

TRACKS = {"추리논증": "leet_reasoning", "언어논리": "psat_verbal",
          "자료해석": "psat_data", "상황판단": "psat_situation"}
STUDENT_FIELDS = {"stem", "passage", "choices", "statements", "tables", "conditions",
                  "additional_passage", "shared_passage", "experiments", "results"}
LIMITS = [
    "명시적 선택과 원문·정답·분류 증거의 수집 시점 검증이며, 슬롯과의 의미상 적합성·독창성·전문가 승인 검증이 아닙니다.",
    "실행 시에는 selected_reference_input 패킷과 source 파일 바이트를 재검증합니다. 원래 색인·corpus를 다시 조회하지 않습니다.",
    "PSAT는 검증된 corpus 전사, LEET는 명시적인 완전 student JSON만 지원합니다. native Block 변환·검토 사례 변환은 지원하지 않습니다.",
]


class SlotSelection(StrictModel):
    slot_id: str = Field(min_length=1)
    reference_ids: list[str]
    application: str = Field(min_length=1)
    match_scope: str = Field(min_length=1)
    gaps: list[str] = Field(default_factory=list)

    @field_validator("slot_id", "application", "match_scope")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("슬롯 ID·적용·일치 범위는 비울 수 없습니다")
        return value

    @field_validator("reference_ids", "gaps")
    @classmethod
    def strings(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError("빈 참고 ID·결손은 허용하지 않습니다")
        if len(values) != len(set(values)):
            raise ValueError("선택 참고 ID·결손이 중복됩니다")
        return values


class Selection(StrictModel):
    schema_version: Literal[1]
    usage: Literal["development"]
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    slots: list[SlotSelection]


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _student(record):
    if record.role != "item" or record.item is not None:
        raise ValueError(f"{record.id}: item 역할의 전사만 지원합니다. case·native Block 변환은 지원하지 않습니다")
    if record.corpus_evidence:
        fields = json.loads(record.text)
        student = {"stem": fields["발문"], "passage": fields["지문"], "choices": fields["선지"],
                   "statements": fields["보기"], "tables": fields["표"]}
        extra = fields.get("전사 부가정보", {})
        for key in STUDENT_FIELDS - set(student):
            if key in extra:
                student[key] = extra[key]
        if any(extra.get(key) for key in ("figures", "blocks", "own_blocks", "sets")):
            raise ValueError(f"{record.id}: 그림·Block·세트 원문은 자동 변환하지 않습니다")
    elif record.track == "leet_reasoning":
        try:
            value = _loads(record.text)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{record.id}: 명시적인 완전 student JSON이 필요합니다") from exc
        student = value.get("student") if isinstance(value, dict) else None
    else:
        raise ValueError(f"{record.id}: PSAT는 corpus 증거가 있는 실제 전사만 지원합니다")
    if (not _student_valid(student) or set(student) - STUDENT_FIELDS
            or any(not isinstance(value, dict) or set(value) != {"number", "text"}
                   for value in student.get("choices", []))):
        raise ValueError(f"{record.id}: 정답·해설 없는 완전 student(발문·지문/표·다섯 선지)가 필요합니다")
    return copy.deepcopy(student)


def _provenances(record):
    yield record.provenance
    if record.corpus_evidence:
        yield from record.corpus_evidence.files()
    for evidence in (record.official_answer_evidence, record.classification_evidence):
        if evidence:
            yield from evidence.provenances()


def _source_identity(source):
    """Compare bridge provenance while ignoring only copied-byte locations.

    Original locators, labels, answer/evidence and every file digest still have
    to match. A matching ID or PDF digest alone cannot establish this identity.
    """
    identity = copy.deepcopy(source)
    identity.pop("path", None)
    files = identity.get("evidence_files")
    if isinstance(files, dict):
        for value in files.values():
            if isinstance(value, dict):
                value.pop("path", None)
    return identity


def bind_exam_references(plan_path, index_path, selection_path, out) -> Path:
    """Write out/plan.json plus a local packet and coverage, never update a plan.

    A slot may explicitly select zero references to record a gap. Missing slots
    stay unchanged and appear in coverage. A previously supplied reference block
    cannot be replaced, even by an identical selection. Source/application are
    separate so one reference can have different uses in different slots.
    """
    plan_path, index_path, selection_path, out = (
        Path(path).resolve() for path in (plan_path, index_path, selection_path, out))
    for path in (plan_path, index_path, selection_path, out):
        _allowed_source(str(path))
    if out.exists():
        raise ValueError("기존 결과를 덮어쓰지 않습니다. 새 --out 디렉터리를 지정하세요")
    plan_bytes, selection_bytes = plan_path.read_bytes(), selection_path.read_bytes()
    plan = load_plan(plan_path)
    if _loads(plan_bytes) != plan:
        raise ValueError("계획 원문이 읽는 동안 변경되었습니다")
    selection = Selection.model_validate(_loads(selection_bytes))
    if selection.plan_sha256 != _sha(plan_bytes):
        raise ValueError("선택 명세와 원본 plan SHA256 불일치")
    chosen = {row.slot_id: row for row in selection.slots}
    if len(chosen) != len(selection.slots):
        raise ValueError("선택 슬롯 ID 중복")
    by_id = {slot["id"]: slot for slot in plan["slots"]}
    if set(chosen) - set(by_id):
        raise ValueError("계획에 없는 선택 슬롯 ID: " + ", ".join(sorted(set(chosen) - set(by_id))))
    # Existing explicit facts/references must remain usable, even for unselected slots.
    supplied_source_ids({"references": [], "exam_assignment": plan["slots"]})
    existing_references = {}
    for slot in plan["slots"]:
        resolution = slot.get("composition_resolution")
        if not isinstance(resolution, dict):
            continue
        block = resolution.get("selected_reference_input", {})
        for reference in block.get("references", []):
            existing_references[reference["reference_id"]] = reference
    for slot_id in chosen:
        resolution = by_id[slot_id].get("composition_resolution", {})
        if not isinstance(resolution, dict):
            raise ValueError(f"{slot_id}: composition_resolution은 객체여야 합니다")
        if "selected_reference_input" in resolution:
            raise ValueError(f"{slot_id}: 기존 selected_reference_input 선택을 덮어쓰지 않습니다")
    track = TRACKS[plan["subject"]]
    grade = None if plan["exam"] == "leet" else int(plan["exam"][-1])
    ids = list(dict.fromkeys(source_id for row in selection.slots for source_id in row.reference_ids))
    with ReferenceIndex(index_path, readonly=True) as index:
        records = index.select_ids(track=track, grade=grade, ids=ids) if ids else []
    students = {record.id: _student(record) for record in records}
    snapshots = {}
    for record in records:
        if record.answer_verified and not record.official_answer_evidence:
            raise ValueError(f"{record.id}: 전달할 검증 정답의 공식 근거가 없습니다")
        for provenance in _provenances(record):
            path = Path(provenance.file).resolve()
            raw = path.read_bytes()
            if _sha(raw) != provenance.sha256:
                raise ValueError("참고 증거가 선택 후 변경되었습니다: " + path.name)
            if path in snapshots and snapshots[path][0] != provenance.sha256:
                raise ValueError("같은 참고 출처의 해시 충돌")
            snapshots[path] = (provenance.sha256, raw)
    if plan_path.read_bytes() != plan_bytes or selection_path.read_bytes() != selection_bytes:
        raise ValueError("연결 중 계획·선택 원문이 변경되었습니다")
    out.mkdir(parents=True, exist_ok=False)
    try:
        (out / "source-plan.json").write_bytes(plan_bytes)
        (out / "selection.json").write_bytes(selection_bytes)
        (out / "evidence").mkdir()
        frozen = {}
        for original, (digest, raw) in snapshots.items():
            target = out / "evidence" / (digest + original.suffix)
            if not target.exists():
                target.write_bytes(raw)
            frozen[str(original)] = {"path": str(target), "sha256": digest}
        references = []
        for record in records:
            source = {**frozen[str(Path(record.provenance.file).resolve())],
                "original_path": record.provenance.file, "locator": record.provenance.locator,
                "usage": "development", "track": record.track, "grade": record.grade,
                "year": record.year, "number": record.number, "source_name": record.source,
                "labels": {key: getattr(record, key) for key in
                           ("area", "item_type", "item_format", "discourse", "stem_type")},
                "official_answer": {"answer": record.answer if record.answer_verified else None,
                    "answer_verified": record.answer_verified,
                    "evidence": record.official_answer_evidence.model_dump() if record.official_answer_evidence else None},
                "evidence_files": {str(Path(p.file).resolve()): frozen[str(Path(p.file).resolve())]
                                   for p in _provenances(record)},
                "corpus_evidence": record.corpus_evidence.model_dump() if record.corpus_evidence else None,
                "classification_evidence": record.classification_evidence.model_dump() if record.classification_evidence else None}
            existing = existing_references.get(record.id)
            if existing is not None:
                if (existing["student"] != students[record.id]
                        or _source_identity(existing["source"]) != _source_identity(source)):
                    raise ValueError(f"{record.id}: 기존 선택과 이번 색인의 student·출처·정답 증거가 다릅니다")
                # Source identity is shared across slots. Keep the existing
                # validated canonical paths; copied evidence also stays here.
                source = copy.deepcopy(existing["source"])
            references.append({"reference_id": record.id, "student": students[record.id], "source": source})
        packet = {"schema_version": 1, "usage": "development", "kind": "exam_selected_references",
                  "references": references, "evidence_files": frozen, "source_plan_sha256": _sha(plan_bytes),
                  "selection_sha256": _sha(selection_bytes), "limits": LIMITS,
                  "human_approved": False, "semantic_accuracy_verified": False}
        packet_path = out / "references.json"
        _write(packet_path, packet)
        lookup = {row["reference_id"]: row for row in references}
        coverage = []
        for slot in plan["slots"]:
            row = chosen.get(slot["id"])
            resolution = slot.get("composition_resolution")
            existing = resolution.get("selected_reference_input") if isinstance(resolution, dict) else None
            if row and row.reference_ids:
                slot.setdefault("composition_resolution", {})["selected_reference_input"] = {
                    "packet_path": str(packet_path), "packet_sha256": _sha(packet_path.read_bytes()),
                    "references": [lookup[source_id] for source_id in row.reference_ids],
                    "application": row.application, "match_scope": row.match_scope, "gaps": row.gaps}
                status, slot_ids, gaps = "attached", row.reference_ids, row.gaps
            elif existing and existing.get("references"):
                status = "existing_preserved"
                slot_ids = [value["reference_id"] for value in existing["references"]]
                gaps = existing.get("gaps", [])
            else:
                status, slot_ids = "gap", []
                gaps = [*(row.gaps if row else []), "명시적으로 선택한 참고가 없습니다."]
            coverage.append({"slot_id": slot["id"], "number": slot["number"], "status": status,
                "reference_ids": slot_ids, "application": row.application if row else (existing or {}).get("application"),
                "match_scope": row.match_scope if row else (existing or {}).get("match_scope"), "gaps": gaps})
        supplied_source_ids({"references": [], "exam_assignment": plan["slots"]})
        _write(out / "selected-records.json", [record.model_dump() for record in records])
        _write(out / "coverage.json", {"schema_version": 1, "usage": "development", "slots": coverage,
            "total_slots": len(coverage), "attached_slots": sum(row["status"] == "attached" for row in coverage),
            "gap_slots": sum(row["status"] == "gap" for row in coverage),
            "existing_preserved_slots": sum(row["status"] == "existing_preserved" for row in coverage),
            "new_reference_uses": sum(len(row.reference_ids) for row in selection.slots),
            "new_unique_reference_count": len(records),
            "plan_reference_uses": sum(len(row["reference_ids"]) for row in coverage),
            "plan_unique_reference_count": len({source_id for row in coverage for source_id in row["reference_ids"]}),
            "limits": LIMITS,
            "human_approved": False, "semantic_accuracy_verified": False, "generation_executed": False,
            "quality_verified": False, "task_fit_verified": False})
        _write(out / "plan.json", plan)
    except Exception as exc:
        _write(out / "failure.json", {"error": str(exc), "usable_plan": False})
        raise
    return out / "plan.json"
