"""Immutable, source-grounded PSAT classification overlays for development.

Quotes establish traceability, not the semantic correctness of the labels.
The original corpus and official-answer validators remain the authority for
every field outside the explicitly declared classification facets.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import Field, StrictStr, field_validator, model_validator

from .models import StrictModel
from .tracks import get
from .tracks.core.references import (
    ClassificationEvidence, RefRecord, ReferenceProvenance, _allowed_source,
    verify_reference_evidence,
)

Facet = Literal["area", "item_type", "item_format", "discourse", "stem_type"]
# Exact top-level question-content keys emitted by question_sources.import_questions.
# Metadata may supplement these quotations but cannot support a facet alone.
QUESTION_CONTENT_FIELDS = frozenset({"발문", "지문", "보기", "표", "선지"})


def _require(condition, message):
    if not condition:
        raise ValueError("분류 근거: " + message)


def _nonempty(value):
    if value is not None:
        _require(bool(value.strip()), "빈 문자열은 사용할 수 없습니다")
    return value


class QuoteEvidence(StrictModel):
    pointer: StrictStr
    quote: StrictStr = Field(min_length=1)

    @field_validator("quote")
    @classmethod
    def nonempty(cls, value):
        return _nonempty(value)


class ClassifiedField(StrictModel):
    value: StrictStr = Field(min_length=1)
    rationale: StrictStr = Field(min_length=1)
    evidence: list[QuoteEvidence] = Field(min_length=1)

    @field_validator("value", "rationale")
    @classmethod
    def nonempty(cls, value):
        return _nonempty(value)


class ClassificationRow(StrictModel):
    id: StrictStr = Field(min_length=1)
    source_record_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    fields: dict[Facet, ClassifiedField] = Field(min_length=1)

    @model_validator(mode="after")
    def development(self):
        _nonempty(self.id)
        _allowed_source(self.id)
        for field in self.fields.values():
            _allowed_source(field.value)
        return self


class ClassificationManifest(StrictModel):
    schema_version: Literal[1]
    usage: Literal["development"]
    origin: Literal["model", "human"]
    actual_model: StrictStr | None
    status: Literal["source_grounded_model_curation", "source_grounded_human_curation"]
    human_approved: Literal[False]
    semantic_accuracy_verified: Literal[False]
    records: list[ClassificationRow] = Field(min_length=1)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        _require(type(value) is int, "schema_version은 정수여야 합니다")
        return value

    @field_validator("human_approved", "semantic_accuracy_verified", mode="before")
    @classmethod
    def false_only(cls, value):
        _require(value is False, "승인·의미 정확성 검증 상태는 false여야 합니다")
        return value

    @field_validator("actual_model")
    @classmethod
    def nonempty(cls, value):
        return _nonempty(value)

    @model_validator(mode="after")
    def identity(self):
        _require(self.status == f"source_grounded_{self.origin}_curation", "origin과 status가 다릅니다")
        _require(len({row.id for row in self.records}) == len(self.records), "중복 문항 ID")
        return self


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def record_sha256(row):
    """Digest the original JSONL object, before model defaults or path changes."""
    return _sha(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _path(value, base):
    path = Path(value)
    path = (path if path.is_absolute() else Path(base) / path).resolve()
    _allowed_source(str(path))
    return path


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "중복 JSON 키: " + key)
        result[key] = value
    return result


def _manifest(data):
    return ClassificationManifest.model_validate(json.loads(data, object_pairs_hook=_unique_object))


def _original_rows(data):
    rows = [json.loads(line, object_pairs_hook=_unique_object)
            for line in data.decode("utf-8").splitlines() if line.strip()]
    _require(rows and all(isinstance(row, dict) for row in rows), "원본 refs 행이 필요합니다")
    ids = [row.get("id") for row in rows]
    _require(all(isinstance(identity, str) and identity.strip() for identity in ids), "원본 refs ID 누락")
    _require(len(set(ids)) == len(ids), "원본 refs 중복 ID")
    return {row["id"]: row for row in rows}


def _pointer(document, pointer):
    """Resolve RFC 6901 without fuzzy paths, recursive search, or coercion."""
    _require(pointer == "" or pointer.startswith("/"), "JSON Pointer는 /로 시작해야 합니다")
    current = document
    for raw in pointer.split("/")[1:] if pointer else ():
        _require(re.search(r"~(?:[^01]|$)", raw) is None, "JSON Pointer 이스케이프 오류")
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            _require(token in current, "JSON Pointer 키가 없습니다: " + pointer)
            current = current[token]
        elif isinstance(current, list):
            _require(re.fullmatch(r"0|[1-9][0-9]*", token) is not None, "JSON Pointer 배열 위치 오류")
            index = int(token)
            _require(index < len(current), "JSON Pointer 배열 범위 초과")
            current = current[index]
        else:
            raise ValueError("분류 근거: JSON Pointer가 값 안으로 내려갑니다")
    _require(isinstance(current, str), "JSON Pointer는 정확한 문자열을 가리켜야 합니다")
    return current


def _validate_fields(row, original):
    document = json.loads(original.text)
    vocabulary = get(original.track).vocab
    for facet, field in row.fields.items():
        if facet in ("area", "item_type"):
            _require(field.value in vocabulary[facet], f"{original.track} {facet} 어휘 밖의 값: {field.value}")
        has_content_quote = False
        for evidence in field.evidence:
            _require(evidence.quote in _pointer(document, evidence.pointer),
                     f"{facet} 인용문이 지정한 원문 문자열에 없습니다: {evidence.pointer}")
            root = evidence.pointer.split("/", 2)[1] if evidence.pointer.startswith("/") else ""
            root = root.replace("~1", "/").replace("~0", "~")
            has_content_quote |= root in QUESTION_CONTENT_FIELDS
        _require(has_content_quote,
                 f"{facet}에는 실제 문항 본문(발문·지문·보기·표·선지)의 문자열 인용이 필요합니다")


def _source_record(raw, original_path, verified, extracted):
    original = RefRecord.model_validate(raw)
    _require(original.track.startswith("psat_") and original.role == "item"
             and original.official_answer_evidence is not None
             and original.classification_evidence is None,
             "기존 분류 오버레이가 없는 공식 정답 PSAT item refs만 지원합니다")
    original.provenance.file = str(_path(original.provenance.file, original_path.parent))
    source = Path(original.provenance.file)
    if source not in verified:
        verified[source] = _sha(source.read_bytes())
    _require(verified[source] == original.provenance.sha256, "문제 출처 SHA256 불일치")
    # This is a single-layer overlay. Nested overlays were rejected above, so
    # routing here invokes only the unchanged corpus and official validators.
    verify_reference_evidence(original, original_path.parent, verified, extracted)
    return original


def verify_classification_evidence(record, base, verified, extracted=None):
    evidence = record.classification_evidence
    if evidence is None:
        return
    extracted = {} if extracted is None else extracted

    def read(provenance):
        path = _path(provenance.file, base)
        data = path.read_bytes()
        _require(_sha(data) == provenance.sha256, "스냅샷 파일 SHA256 불일치: " + path.name)
        verified[path] = provenance.sha256
        provenance.file = str(path)
        return data

    manifest = _manifest(read(evidence.manifest))
    originals = _original_rows(read(evidence.source_refs))
    _require(set(originals) == {row.id for row in manifest.records}, "refs와 manifest 문항 집합 불일치")
    _require(record.id in originals, "원본 refs 문항 ID 누락")
    row = next(row for row in manifest.records if row.id == record.id)
    raw = originals[record.id]
    _require(record_sha256(raw) == row.source_record_sha256 == evidence.source_record_sha256,
             "원본 refs 행 canonical SHA256 불일치")
    for name in ("origin", "actual_model", "status", "human_approved", "semantic_accuracy_verified"):
        _require(getattr(evidence, name) == getattr(manifest, name), "manifest와 분류 상태 불일치: " + name)
    original = _source_record(raw, _path(evidence.source_refs_original_path, base), verified, extracted)
    _validate_fields(row, original)
    for facet, field in row.fields.items():
        _require(getattr(record, facet) == field.value, "manifest와 분류 값 불일치: " + facet)
    excluded = {"classification_evidence", *row.fields}
    _require(record.model_dump(exclude=excluded) == original.model_dump(exclude=excluded),
             "명시한 분류 필드 외의 원본 refs 값이 바뀌었습니다")


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def curate(source_refs, classification_manifest, out):
    """Validate the full selection and publish only into a fresh directory."""
    source_refs, classification_manifest, out = (
        _path(path, Path.cwd()) for path in (source_refs, classification_manifest, out))
    if out.exists():
        raise ValueError("기존 결과를 덮어쓰지 않습니다. 새 --out 디렉터리를 지정하세요.")
    out.mkdir(parents=True, exist_ok=False)
    receipt = {"schema_version": 1, "usage": "development", "source_refs": str(source_refs),
               "classification_manifest": str(classification_manifest), "exported": 0, "errors": [],
               "requires_classification_evidence_support": True, "human_approved": False,
               "semantic_accuracy_verified": False}
    try:
        refs_bytes, manifest_bytes = source_refs.read_bytes(), classification_manifest.read_bytes()
        receipt.update(source_refs_sha256=_sha(refs_bytes), classification_manifest_sha256=_sha(manifest_bytes))
        (out / "source-refs.jsonl").write_bytes(refs_bytes)
        (out / "classification.json").write_bytes(manifest_bytes)
        manifest, originals = _manifest(manifest_bytes), _original_rows(refs_bytes)
        _require(set(originals) == {row.id for row in manifest.records}, "refs와 manifest 문항 집합 불일치")
        receipt.update(origin=manifest.origin, actual_model=manifest.actual_model, status=manifest.status)
        records, verified, extracted = [], {}, {}
        for row in manifest.records:
            raw = originals[row.id]
            _require(record_sha256(raw) == row.source_record_sha256, "원본 refs 행 canonical SHA256 불일치")
            original = _source_record(raw, source_refs, verified, extracted)
            _validate_fields(row, original)
            record = original.model_copy(deep=True)
            for facet, field in row.fields.items():
                setattr(record, facet, field.value)
            record.classification_evidence = ClassificationEvidence(
                manifest=ReferenceProvenance(file=str(out / "classification.json"), locator="records.id=" + row.id,
                                             sha256=_sha(manifest_bytes), usage="development"),
                source_refs=ReferenceProvenance(file=str(out / "source-refs.jsonl"), locator="id=" + row.id,
                                                sha256=_sha(refs_bytes), usage="development"),
                source_refs_original_path=str(source_refs), source_record_sha256=row.source_record_sha256,
                origin=manifest.origin, actual_model=manifest.actual_model, status=manifest.status)
            record = RefRecord.model_validate(record.model_dump())
            verify_reference_evidence(record, out, verified, extracted)
            records.append(record)
        _require(source_refs.read_bytes() == refs_bytes and classification_manifest.read_bytes() == manifest_bytes,
                 "검사 도중 입력 파일이 바뀌었습니다")
        for path, digest in verified.items():
            _require(_sha(path.read_bytes()) == digest, "검사 도중 출처 파일이 바뀌었습니다: " + path.name)
        pending = out / ".refs.jsonl.pending"
        pending.write_text("\n".join(record.model_dump_json() for record in records) + "\n", encoding="utf-8")
        receipt.update(exported=len(records), refs_sha256=_sha(pending.read_bytes()))
        _save(out / "receipt.json", receipt)
        pending.rename(out / "refs.jsonl")
        return receipt
    except Exception as exc:
        receipt.update(exported=0, errors=[str(exc)])
        _save(out / "failure.json", receipt)
        raise ValueError("분류 보강 실패: " + str(exc)) from exc
