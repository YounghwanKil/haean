"""Versioned development-only reference index for the track foundation.

This is a fresh, dedicated schema, not an adapter for corpus.sqlite or the
upstream (track, id) index. Opening for search never creates or migrates a DB.
Raw source content stays local; each record keeps an explicit source locator.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from ...models import StrictModel
from .. import NAMES

SCHEMA_VERSION = "haean-track-references-v1"
FACETS = ("area", "item_type", "item_format", "discourse", "stem_type", "grade")
NONE_GRADE = -1


def _allowed_source(value: str) -> None:
    if "holdout" in value.casefold():
        raise ValueError("holdout 자료는 development 참고 색인에 넣을 수 없습니다")


class ReferenceProvenance(StrictModel):
    file: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    usage: Literal["development"]

    @model_validator(mode="after")
    def development_only(self):
        for value in (self.file, self.locator):
            if not value.strip():
                raise ValueError("출처 파일·locator는 비울 수 없습니다")
            _allowed_source(value)
        return self


class CorpusEvidence(StrictModel):
    """Optional evidence for explicitly selected PSAT transcription exports."""
    version: Literal[1] = 1
    source_record_id: str = Field(min_length=1)
    source_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_record: ReferenceProvenance
    packet: ReferenceProvenance
    selection: ReferenceProvenance
    original_meta: dict
    transcription_verified: Literal[True]
    answer_verified: Literal[False]
    label_status: Literal["provisional"]
    semantic_accuracy_verified: Literal[False] = False
    official_bytes_verified: Literal[False] = False

    def files(self):
        return (self.source_record, self.packet, self.selection)


class OfficialAnswerEvidence(StrictModel):
    """Separate, frozen official-answer audit; never rewrites corpus evidence."""
    version: Literal[1] = 1
    manifest: ReferenceProvenance
    source_refs: ReferenceProvenance
    manifest_base: str = Field(min_length=1)
    source_refs_original_path: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    files: dict[str, ReferenceProvenance] = Field(min_length=1)
    verification_scope: Literal["official_answer_row_and_question_bytes"] = "official_answer_row_and_question_bytes"
    semantic_accuracy_verified: Literal[False] = False
    human_approved: Literal[False] = False

    def provenances(self):
        return (self.manifest, self.source_refs, *self.files.values())


class ClassificationEvidence(StrictModel):
    """Frozen source-grounded labels, separate from official answer evidence."""
    version: Literal[1] = 1
    manifest: ReferenceProvenance
    source_refs: ReferenceProvenance
    source_refs_original_path: str = Field(min_length=1)
    source_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    origin: Literal["model", "human"]
    actual_model: str | None
    status: Literal["source_grounded_model_curation", "source_grounded_human_curation"]
    human_approved: Literal[False] = False
    semantic_accuracy_verified: Literal[False] = False

    def provenances(self):
        return (self.manifest, self.source_refs)


def _identity(track, grade):
    if track not in NAMES:
        raise ValueError("알 수 없는 트랙: " + track)
    if track.startswith("psat_") and grade not in (5, 7):
        raise ValueError("PSAT 참고 자료와 검색에는 5급 또는 7급을 명시해야 합니다")
    if not track.startswith("psat_") and grade is not None:
        raise ValueError("LEET 참고 자료와 검색에는 급수를 쓰지 않습니다")


class RefRecord(StrictModel):
    id: str = Field(min_length=1)
    track: str = Field(min_length=1)
    role: Literal["item", "case"]
    provenance: ReferenceProvenance
    source: str = ""
    year: int | None = None
    number: int | None = None
    grade: Literal[5, 7] | None = None
    area: str = ""
    item_type: str = ""
    item_format: str = ""
    discourse: str = ""
    stem_type: str = ""
    text: str = Field(min_length=1)
    item: dict | None = None
    answer: StrictInt | None = Field(default=None, ge=1, le=5)
    answer_verified: bool = False
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    corpus_evidence: CorpusEvidence | None = None
    official_answer_evidence: OfficialAnswerEvidence | None = None
    classification_evidence: ClassificationEvidence | None = None

    @model_validator(mode="after")
    def identity(self):
        _identity(self.track, self.grade)
        for value in (self.id, self.source, *self.tags):
            _allowed_source(value)
        if self.corpus_evidence:
            if (self.id != self.corpus_evidence.source_record_id or self.role != "item"
                    or not self.track.startswith("psat_") or self.item is not None
                    or (self.official_answer_evidence is None and (self.answer is not None or self.answer_verified))):
                raise ValueError("corpus 전사 증거의 ID·역할·정답 상태가 다릅니다")
        if self.official_answer_evidence and (not self.corpus_evidence or self.answer is None or not self.answer_verified):
            raise ValueError("공식 정답 근거에는 corpus 전사와 별도 정답이 필요합니다")
        if self.classification_evidence and not self.official_answer_evidence:
            raise ValueError("분류 오버레이에는 공식 정답 근거가 필요합니다")
        return self


def verify_corpus_evidence(record, base, verified):
    """Verify export snapshots without reopening or hashing the mutable corpus DB."""
    evidence = record.corpus_evidence
    if evidence is None:
        return
    for source in evidence.files():
        path = Path(source.file)
        path = (path if path.is_absolute() else base / path).resolve()
        _allowed_source(str(path))
        if path not in verified:
            verified[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        if verified[path] != source.sha256:
            raise ValueError("corpus 증거 파일 SHA256 불일치: " + path.name)
        source.file = str(path)
    snapshot_bytes = Path(evidence.source_record.file).read_bytes()
    if hashlib.sha256(snapshot_bytes).hexdigest() != evidence.source_record.sha256:
        raise ValueError("읽는 동안 corpus 행 스냅샷이 바뀌었습니다")
    snapshot = json.loads(snapshot_bytes)
    row = snapshot["record"]
    digest = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()
    meta = json.loads(row["meta"])
    stable_locator = row["locator"].split("::", 1)[1] if "::" in row["locator"] else row["locator"].split("#", 1)[-1]
    expected_id = hashlib.sha256((row["sha"] + "#" + stable_locator).encode()).hexdigest()[:24]
    source_base = Path(snapshot["source_path_base"])
    original_pdf = Path(snapshot["source"]["path"])
    original_pdf = (original_pdf if original_pdf.is_absolute() else source_base / original_pdf).resolve()
    original_packet = Path(meta["packet_path"])
    original_packet = (original_packet if original_packet.is_absolute() else source_base / original_packet).resolve()
    selection_bytes = Path(evidence.selection.file).read_bytes()
    if hashlib.sha256(selection_bytes).hexdigest() != evidence.selection.sha256:
        raise ValueError("읽는 동안 corpus 선택 스냅샷이 바뀌었습니다")
    selection = json.loads(selection_bytes)
    chosen = [r for r in selection["records"] if r.get("id") == record.id]
    if (selection.get("usage") != "development" or len(chosen) != 1
            or chosen[0].get("track") != record.track or chosen[0].get("grade") != record.grade
            or chosen[0].get("usage") != "development"):
        raise ValueError("명시적인 corpus 선택과 참고 자료가 다릅니다")
    subjects = {"psat_verbal": "언어논리", "psat_data": "자료해석", "psat_situation": "상황판단"}
    if (digest != evidence.source_record_sha256 or row["id"] != record.id or row["id"] != expected_id
            or row["text"] != record.text or row["sha"] != record.provenance.sha256
            or row["locator"] != record.provenance.locator or row["role"] != "example"
            or row["exam"] != f"psat{record.grade}" or meta != evidence.original_meta
            or meta["fields"]["과목"] != subjects.get(record.track)
            or meta["fields"]["문항유형"] != record.item_type
            or meta["fields"]["연도"] != record.year or meta["fields"]["문항 번호"] != record.number
            or snapshot["source"]["name"] != record.source
            or snapshot["source"]["sha"] != record.provenance.sha256
            or original_pdf != Path(record.provenance.file).resolve()
            or original_packet != Path(evidence.packet.file).resolve()
            or any((record.area, record.item_format, record.discourse, record.stem_type))
            or meta["packet_sha256"] != evidence.packet.sha256
            or meta.get("transcription_verified") is not True
            or meta.get("answer_verified") is not False
            or meta.get("label_status") != "provisional"
            or meta["fields"].get("정답") is not None
            or meta["fields"].get("정답 검증") is not False
            or meta["source"].get("official_bytes_verified", False) is not False):
        raise ValueError("corpus 전사 원본과 참고 레코드가 다릅니다")
    packet_bytes = Path(evidence.packet.file).read_bytes()
    if hashlib.sha256(packet_bytes).hexdigest() != evidence.packet.sha256:
        raise ValueError("읽는 동안 corpus 전사 패킷이 바뀌었습니다")
    from ...reference_bridge import verify_packet_transcription
    verify_packet_transcription(row, meta, packet_bytes, source_base, original_pdf)


def verify_reference_evidence(record, base, verified, extracted=None):
    """Route overlays through unchanged original corpus and answer checks."""
    if record.classification_evidence:
        from ...reference_curation import verify_classification_evidence
        verify_classification_evidence(record, base, verified, extracted)
        return
    verify_corpus_evidence(record, base, verified)
    if record.official_answer_evidence:
        from ...reference_answers import verify_official_answer_evidence
        verify_official_answer_evidence(record, base, verified, extracted)


class RefQuery(StrictModel):
    track: str
    role: Literal["item", "case"] = "item"
    area: str | None = None
    item_type: str | None = None
    item_format: str | None = None
    discourse: str | None = None
    stem_type: str | None = None
    grade: Literal[5, 7] | None = None
    text: str = ""
    k: int = Field(default=4, ge=1, le=50)
    exclude_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def identity(self):
        _identity(self.track, self.grade)
        return self


def norm(value):
    return " ".join(str(value).split()) if value not in (None, "") else None


def grams(text):
    text = "".join(str(text).split())
    return Counter(text[i:i + 2] for i in range(len(text) - 1))


def overlap(a, b):
    if not a or not b:
        return 0.0
    return sum((a & b).values()) / (sum(a.values()) ** 0.5 * sum(b.values()) ** 0.5)


class ReferenceIndex:
    def __init__(self, path, readonly=False):
        self.path = Path(path).resolve()
        self.readonly = readonly
        exists = self.path.exists()
        if readonly and not exists:
            raise FileNotFoundError("참고 색인이 없습니다(검색은 DB를 생성하지 않습니다): " + str(self.path))
        if not exists:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        uri = self.path.as_uri() + ("?mode=ro" if readonly else "?mode=rwc")
        self.db = sqlite3.connect(uri, uri=True)
        try:
            if not exists:
                with self.db:
                    self.db.execute("CREATE TABLE track_index_meta (version TEXT NOT NULL)")
                    self.db.execute("INSERT INTO track_index_meta VALUES (?)", (SCHEMA_VERSION,))
                    self.db.execute("""CREATE TABLE track_refs (
                        track TEXT NOT NULL, grade INTEGER NOT NULL CHECK(grade IN (-1,5,7)),
                        id TEXT NOT NULL, role TEXT NOT NULL, area TEXT, item_type TEXT,
                        item_format TEXT, discourse TEXT, stem_type TEXT, year INTEGER,
                        record TEXT NOT NULL, PRIMARY KEY(track, grade, id))""")
            self._check_schema()
        except Exception:
            self.db.close()
            raise

    def _check_schema(self):
        try:
            versions = self.db.execute("SELECT version FROM track_index_meta").fetchall()
            columns = self.db.execute("PRAGMA table_info(track_refs)").fetchall()
        except sqlite3.DatabaseError as exc:
            raise ValueError("기존·알 수 없는 참고 색인 스키마입니다. 새 전용 DB를 사용하세요.") from exc
        expected = ["track", "grade", "id", "role", "area", "item_type", "item_format", "discourse", "stem_type", "year", "record"]
        primary = [row[1] for row in sorted(columns, key=lambda r: r[5]) if row[5]]
        if versions != [(SCHEMA_VERSION,)] or [row[1] for row in columns] != expected or primary != ["track", "grade", "id"]:
            raise ValueError("참고 색인 버전·스키마가 다릅니다. 제자리 변환하지 말고 새 전용 DB를 만드세요.")

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def build(self, jsonl, tracks=None):
        """Explicit development records only; validate every row before replacement.

        Relative provenance.file paths resolve against the JSONL's directory.
        The fresh index stores their absolute paths and verified source hashes.
        """
        if self.readonly:
            raise ValueError("읽기 전용 참고 색인에는 쓸 수 없습니다")
        paths = [jsonl] if isinstance(jsonl, (str, Path)) else list(jsonl)
        records, errors, verified, extracted = [], [], {}, {}
        for raw in paths:
            path = Path(raw).resolve()
            _allowed_source(str(path))
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    row = RefRecord.model_validate_json(line)
                    if tracks is not None and row.track not in tracks:
                        raise ValueError("지정한 범위 밖 트랙: " + row.track)
                    source = Path(row.provenance.file)
                    source = (source if source.is_absolute() else path.parent / source).resolve()
                    _allowed_source(str(source))
                    if not source.is_file():
                        raise ValueError("출처 파일이 없습니다")
                    if source not in verified:
                        verified[source] = hashlib.sha256(source.read_bytes()).hexdigest()
                    if verified[source] != row.provenance.sha256:
                        raise ValueError("출처 파일 SHA256 불일치")
                    row.provenance.file = str(source)
                    verify_reference_evidence(row, path.parent, verified, extracted)
                    records.append(row)
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    errors.append({"line": number, "file": str(path), "error": str(exc)[:300]})
        duplicate = [key for key, count in Counter((r.track, r.grade, r.id) for r in records).items() if count > 1]
        if duplicate:
            errors.append({"line": None, "error": "같은 트랙·급수 안의 중복 ID", "identities": duplicate})
        if errors:
            return {"schema_version": SCHEMA_VERSION, "indexed": 0, "errors": errors}
        rows = [(r.track, r.grade if r.grade is not None else NONE_GRADE, r.id, r.role,
                 norm(r.area), norm(r.item_type), norm(r.item_format), norm(r.discourse), norm(r.stem_type),
                 r.year, r.model_dump_json()) for r in records]
        with self.db:
            self.db.execute("DELETE FROM track_refs")
            self.db.executemany("INSERT INTO track_refs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
        return {"schema_version": SCHEMA_VERSION, "indexed": len(rows), "errors": [], "vocabulary": self.vocabulary()}

    def vocabulary(self, track=None):
        if track is not None and track not in NAMES:
            raise ValueError("알 수 없는 트랙: " + track)
        where, args = ("WHERE track = ?", [track]) if track else ("", [])
        out = {}
        for facet in ("track", "role") + FACETS:
            out[facet] = {("None" if facet == "grade" and value == NONE_GRADE else str(value)): count
                          for value, count in self.db.execute(
                              f"SELECT {facet}, count(*) FROM track_refs {where} "
                              f"{'AND' if where else 'WHERE'} {facet} IS NOT NULL GROUP BY {facet} ORDER BY 2 DESC", args)}
        return out

    def search(self, query: RefQuery):
        query = RefQuery.model_validate(query.model_dump())
        where, args = ["track = ?", "grade = ?", "role = ?"], [query.track, query.grade if query.grade is not None else NONE_GRADE, query.role]
        for facet in FACETS:
            if facet == "grade":
                continue
            value = getattr(query, facet)
            if value not in (None, ""):
                where.append(f"{facet} = ?")
                args.append(norm(value))
        records = []
        # Match every indexed field, including ID and facet values, against the
        # payload so a damaged index cannot bypass filtering or exclusions.
        for row in self.db.execute(
                "SELECT track, grade, id, role, area, item_type, item_format, discourse, stem_type, year, record "
                "FROM track_refs WHERE " + " AND ".join(where), args):
            record = RefRecord.model_validate_json(row[-1])
            expected = (record.track, record.grade if record.grade is not None else NONE_GRADE, record.id,
                        record.role, norm(record.area), norm(record.item_type), norm(record.item_format),
                        norm(record.discourse), norm(record.stem_type), record.year)
            if row[:-1] != expected:
                raise ValueError("참고 색인 행의 ID·분류 값과 저장 본문이 다릅니다. 색인을 다시 검토하세요.")
            _allowed_source(str(Path(record.provenance.file).resolve()))
            records.append(record)
        records = [r for r in records if r.id not in set(query.exclude_ids)]
        target = grams(query.text) if query.text else None
        records.sort(key=lambda r: (-(overlap(target, grams(r.text)) if target else 0), -(r.year or 0), r.id))
        hits = records[:query.k]
        verified_sources, extracted = {}, {}
        for record in hits:
            source = Path(record.provenance.file).resolve()
            if source not in verified_sources:
                if not source.is_file():
                    raise ValueError(f"{record.id}: 현재 출처 파일이 없어 참고 자료를 사용할 수 없습니다")
                try:
                    verified_sources[source] = hashlib.sha256(source.read_bytes()).hexdigest()
                except OSError as exc:
                    raise ValueError(f"{record.id}: 현재 출처 파일을 확인하지 못해 참고 자료를 사용할 수 없습니다") from exc
            if verified_sources[source] != record.provenance.sha256:
                raise ValueError(f"{record.id}: 출처 파일 SHA256이 바뀌어 참고 자료를 사용할 수 없습니다. 재검토 후 새 색인을 만드세요.")
            try:
                verify_reference_evidence(record, self.path.parent, verified_sources, extracted)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                raise ValueError(f"{record.id}: corpus 증거를 확인하지 못해 참고 자료를 사용할 수 없습니다: {exc}") from exc
        used = {f: getattr(query, f) for f in FACETS if getattr(query, f) not in (None, "")}
        missing = [] if len(hits) >= query.k else [f"{query.track} {query.role} 사례가 조건 {used}에서 {len(hits)}개뿐입니다(요청 {query.k}). 완화하지 않았습니다."]
        return {"schema_version": SCHEMA_VERSION, "usage": "development", "query": query.model_dump(),
                "hits": [r.model_dump() for r in hits], "missing": missing,
                "verified_source_files": len(verified_sources), "semantic_accuracy_verified": False}


def gather(index: ReferenceIndex | None, track, brief, stage):
    queries = track.stage_queries(brief, stage)
    if index is None:
        return {name: {"query": q.model_dump(), "hits": [], "missing": ["참고 색인 없음"]} for name, q in queries.items()}
    return {name: index.search(query) for name, query in queries.items()}
