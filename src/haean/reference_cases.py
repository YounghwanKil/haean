"""Frozen, line-addressed historical feedback for development-only authoring.

The selection is a curator's claim, not an authenticated expert review. Exact
source snapshots let readers inspect disagreements and partial changes without
turning an old answer or a reported fix into a certified example.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator

from .models import StrictModel
from .tracks import get
from .tracks.core.references import (
    RefRecord, ReferenceProvenance, ReviewCaseEvidence, _allowed_source, _identity,
)


def _require(condition, message):
    if not condition:
        raise ValueError("검토 사례 근거: " + message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _nonempty(value):
    if value is not None:
        _require(bool(value.strip()), "빈 문자열은 사용할 수 없습니다")
    return value


def _path(value, base):
    _allowed_source(str(value))
    path = Path(value)
    path = (path if path.is_absolute() else Path(base) / path).resolve()
    _allowed_source(str(path))
    return path


class Span(StrictModel):
    file: StrictStr = Field(min_length=1)
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    start_line: StrictInt = Field(ge=1)
    end_line: StrictInt = Field(ge=1)
    excerpt_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def valid(self):
        _nonempty(self.file)
        _allowed_source(self.file)
        _require(self.end_line >= self.start_line, "행 범위가 역순입니다")
        return self


class Attribution(StrictModel):
    origin: Literal["human_reported", "human", "model", "unknown"]
    label: StrictStr = Field(min_length=1)

    @field_validator("label")
    @classmethod
    def nonempty(cls, value):
        return _nonempty(value)


class Before(StrictModel):
    version_label: StrictStr = Field(min_length=1)
    author: Attribution
    text: Span
    public_text: Span

    @field_validator("version_label")
    @classmethod
    def nonempty(cls, value):
        return _nonempty(value)


class After(StrictModel):
    kind: Literal["full", "delta"]
    version_label: StrictStr = Field(min_length=1)
    author: Attribution
    text: Span
    public_text: Span | None = None

    @field_validator("version_label")
    @classmethod
    def nonempty(cls, value):
        return _nonempty(value)

    @model_validator(mode="after")
    def complete_question(self):
        _require((self.kind == "full") == (self.public_text is not None),
                 "full after에는 public_text가 필요하며 delta에는 지정할 수 없습니다")
        return self


class Reviewer(Attribution):
    text: Span


class CaseSelection(StrictModel):
    case_key: StrictStr = Field(min_length=1)
    family_id: StrictStr = Field(min_length=1)
    track: StrictStr
    grade: Literal[5, 7] | None
    area: StrictStr
    item_type: StrictStr
    item_format: StrictStr
    discourse: StrictStr
    stem_type: StrictStr
    source: StrictStr = Field(min_length=1)
    year: StrictInt | None = None
    number: StrictInt | None = None
    status: Literal["unresolved", "partially_resolved", "reported_resolved"]
    before: Before
    reviewers: list[Reviewer] = Field(min_length=1)
    after: After | None = None

    @model_validator(mode="after")
    def identity(self):
        _identity(self.track, self.grade)
        for name in ("case_key", "family_id", "source"):
            _nonempty(getattr(self, name))
            _allowed_source(getattr(self, name))
        for name in ("case_key", "family_id"):
            _require(getattr(self, name) == getattr(self, name).strip(), "안정 키의 앞뒤 공백: " + name)
        vocab = get(self.track).vocab
        for facet in ("area", "item_type", "item_format", "discourse"):
            value = getattr(self, facet)
            _nonempty(value)
            _allowed_source(value)
            _require(vocab[facet] is None or value in vocab[facet], f"{self.track} {facet} 어휘 밖의 값: {value}")
        return self


class CaseManifest(StrictModel):
    schema_version: Literal[1]
    usage: Literal["development"]
    origin: Literal["model", "human"]
    actual_model: StrictStr | None
    human_approved: Literal[False]
    semantic_accuracy_verified: Literal[False]
    records: list[CaseSelection] = Field(min_length=1)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        _require(type(value) is int, "schema_version은 정수여야 합니다")
        return value

    @field_validator("human_approved", "semantic_accuracy_verified", mode="before")
    @classmethod
    def false_only(cls, value):
        _require(value is False, "사람 승인·의미 정확성 검증은 false여야 합니다")
        return value

    @field_validator("actual_model")
    @classmethod
    def nonempty(cls, value):
        return _nonempty(value)

    @model_validator(mode="after")
    def distinct(self):
        for field in ("case_key", "family_id"):
            _require(len({getattr(row, field) for row in self.records}) == len(self.records),
                     "중복 " + field)
        return self


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "중복 JSON 키: " + key)
        result[key] = value
    return result


def _manifest(data):
    return CaseManifest.model_validate(json.loads(data, object_pairs_hook=_unique_object))


def _spans(row):
    spans = [row.before.text, row.before.public_text, *(r.text for r in row.reviewers)]
    if row.after:
        spans.append(row.after.text)
        if row.after.public_text:
            spans.append(row.after.public_text)
    return spans


def _excerpt(span, base, source_bytes):
    path = _path(span.file, base)
    data = source_bytes[str(path)]
    _require(_sha(data) == span.sha256, "원본 파일 SHA256 불일치: " + path.name)
    # Decode first so UTF-8 errors outside the selected range are also rejected.
    data.decode("utf-8")
    # Preserve CRLF, BOM, final newline and every byte of the selected lines.
    lines = data.splitlines(keepends=True)
    _require(span.end_line <= len(lines), "행 범위를 벗어났습니다: " + path.name)
    selected = b"".join(lines[span.start_line - 1:span.end_line])
    _require(_sha(selected) == span.excerpt_sha256, "발췌 SHA256 불일치: " + path.name)
    quote = selected.decode("utf-8")
    _require(bool(quote.strip()), "빈 발췌문")
    return {"source": str(path), "start_line": span.start_line, "end_line": span.end_line,
            "sha256": span.sha256, "excerpt_sha256": span.excerpt_sha256, "text": quote}


def _version(version, base, source_bytes):
    value = {"version_label": version.version_label, "author": version.author.model_dump(),
             "text": _excerpt(version.text, base, source_bytes),
             "public_text": _excerpt(version.public_text, base, source_bytes) if version.public_text else None}
    if isinstance(version, After):
        value["kind"] = version.kind
    if version.public_text:
        public, full = value["public_text"], value["text"]
        _require(public["source"] == full["source"] and public["sha256"] == full["sha256"]
                 and full["start_line"] <= public["start_line"] <= public["end_line"] <= full["end_line"],
                 "public_text는 같은 버전 text 안의 학생용 문항 범위여야 합니다")
    return value


def _render(row, manifest, base, source_bytes):
    return json.dumps({
        "kind": "historical_review_case", "usage": "development", "case_key": row.case_key,
        "family_id": row.family_id, "status": row.status,
        "status_scope": "curator_reported_not_verified",
        "curation": {"origin": manifest.origin, "actual_model": manifest.actual_model},
        "attribution_scope": "reported_source_labels_not_authenticated_expert_identity",
        "human_approved": False, "semantic_accuracy_verified": False, "answer_verified": False,
        "before": _version(row.before, base, source_bytes),
        "reviewers": [{"origin": r.origin, "label": r.label,
                       "text": _excerpt(r.text, base, source_bytes)} for r in row.reviewers],
        "after": _version(row.after, base, source_bytes) if row.after else None,
        "limits": ["과거 의견의 타당성은 현행 문항에서 다시 판단한다.",
                   "상반 의견과 부분 수정·미해소 상태를 보존한다.",
                   "delta는 완전한 수정본이 아니며 재구성하거나 정답 예시로 승인하지 않는다."]
    }, ensure_ascii=False, sort_keys=True, indent=2)


def _record(row, manifest, evidence, source_bytes):
    return RefRecord(id="case-" + _sha(row.case_key.encode("utf-8"))[:24], track=row.track,
        role="case", provenance=evidence.manifest.model_copy(deep=True), source=row.source,
        year=row.year, number=row.number, grade=row.grade, area=row.area, item_type=row.item_type,
        item_format=row.item_format, discourse=row.discourse, stem_type=row.stem_type,
        text=_render(row, manifest, evidence.selection_base, source_bytes),
        tags=["source_backed_review_case", "development_only"],
        notes="출처가 연결된 과거 검토 의견. 사람 승인·전문가 인증·정답 보증이 아님.",
        review_case_evidence=evidence)


def verify_review_case_evidence(record, base, verified):
    evidence = record.review_case_evidence
    if evidence is None:
        return
    selection_base = _path(evidence.selection_base, base)
    _require(str(selection_base) == evidence.selection_base, "selection_base는 절대 경로여야 합니다")

    def read(provenance):
        path = _path(provenance.file, base)
        data = path.read_bytes()
        _require(_sha(data) == provenance.sha256, "스냅샷 파일 SHA256 불일치: " + path.name)
        verified[path] = provenance.sha256
        provenance.file = str(path)
        return data

    manifest = _manifest(read(evidence.manifest))
    rows = [row for row in manifest.records if row.case_key == evidence.case_key]
    _require(len(rows) == 1, "선택 manifest에 사례가 없습니다")
    row = rows[0]
    expected_sources = {_path(span.file, selection_base): span.sha256 for span in _spans(row)}
    _require(set(map(str, expected_sources)) == set(evidence.source_files), "선택 사례와 출처 파일 목록이 다릅니다")
    source_bytes = {}
    for original, digest in expected_sources.items():
        source = evidence.source_files[str(original)]
        _require(source.sha256 == digest and source.locator == str(original), "원본 경로·해시와 스냅샷 연결 불일치")
        source_bytes[str(original)] = read(source)
    _require(evidence.family_id == row.family_id and evidence.origin == manifest.origin
             and evidence.actual_model == manifest.actual_model, "manifest와 사례 신원·분류 출처가 다릅니다")
    expected = _record(row, manifest, evidence, source_bytes)
    record.provenance.file = str(_path(record.provenance.file, base))
    _require(record.model_dump() == expected.model_dump(), "manifest와 참고 사례 본문·분류·신원·정답 상태가 다릅니다")


def originality_texts(hit):
    """Question-only projections; never compare editor comments as questions."""
    if not hit.get("review_case_evidence"):
        return []
    content = json.loads(hit["text"])
    texts = [("before", content["before"]["public_text"]["text"])]
    after = content["after"]
    if after and after["kind"] == "full":
        texts.append(("after", after["public_text"]["text"]))
    return [{"id": f"track:{hit['track']}:{hit['grade']}:{hit['id']}:{version}", "text": text}
            for version, text in texts]


def verify_case_collection(records):
    """An explicit selection cannot become an apparently complete partial import."""
    groups = {}
    for record in records:
        evidence = record.review_case_evidence
        if evidence:
            key = (evidence.manifest.file, evidence.manifest.sha256)
            groups.setdefault(key, set()).add(evidence.case_key)
    for (file, digest), imported in groups.items():
        data = Path(file).read_bytes()
        _require(_sha(data) == digest, "모음 검증 중 manifest가 바뀌었습니다")
        selected = {row.case_key for row in _manifest(data).records}
        _require(imported == selected, "선택 manifest의 전체 사례 집합과 색인 입력이 다릅니다. 부분 선택은 새 selection으로 내보내세요")


def export(selection, out):
    selection = _path(selection, Path.cwd())
    out = _path(out, Path.cwd())
    _require(not out.exists(), "기존 출력 경로를 덮어쓰지 않습니다")
    selection_bytes = selection.read_bytes()
    manifest = _manifest(selection_bytes)
    sources = {}
    for row in manifest.records:
        for span in _spans(row):
            path = _path(span.file, selection.parent)
            if str(path) not in sources:
                sources[str(path)] = path.read_bytes()
            _excerpt(span, selection.parent, sources)
        _render(row, manifest, selection.parent, sources)
    # All source reads and schema checks complete before creating a new export.
    out.mkdir(parents=True, exist_ok=False)
    (out / "selection.json").write_bytes(selection_bytes)
    (out / "sources").mkdir()
    snapshots = {}
    for i, (original, data) in enumerate(sorted(sources.items())):
        target = out / "sources" / f"{i:04d}-{_sha(data)[:16]}.txt"
        target.write_bytes(data)
        snapshots[original] = ReferenceProvenance(file=str(target), locator=original,
                                                 sha256=_sha(data), usage="development")
    manifest_provenance = ReferenceProvenance(file=str(out / "selection.json"), locator=str(selection),
                                            sha256=_sha(selection_bytes), usage="development")
    records = []
    for row in manifest.records:
        needed = {str(_path(span.file, selection.parent)) for span in _spans(row)}
        evidence = ReviewCaseEvidence(manifest=manifest_provenance.model_copy(deep=True),
            selection_base=str(selection.parent), case_key=row.case_key, family_id=row.family_id,
            origin=manifest.origin, actual_model=manifest.actual_model,
            source_files={key: snapshots[key].model_copy(deep=True) for key in sorted(needed)})
        record = _record(row, manifest, evidence, sources)
        verify_review_case_evidence(record, out, {})
        records.append(record)
    refs = out / "refs.jsonl"
    pending = out / ".refs.jsonl.pending"
    with pending.open("xb") as stream:
        stream.write("".join(row.model_dump_json() + "\n" for row in records).encode("utf-8"))
    # Publish only complete JSONL; a write interruption leaves no usable refs.
    os.link(pending, refs)
    pending.unlink()
    return {"refs": str(refs), "records": len(records), "usage": "development",
            "selection_sha256": _sha(selection_bytes), "source_files": len(sources),
            "human_approved": False, "semantic_accuracy_verified": False, "answer_verified": False,
            "source_files_preserved": True}
