"""Explicit, read-only PSAT corpus transcription export. No schema migration.

This deliberately does not turn statistics, reviews or inferred classifications
into question examples. All outputs remain local and answers remain unverified.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictInt

from .models import StrictModel
from .question_sources import QuestionSource
from .tracks.core.references import CorpusEvidence, RefRecord, ReferenceProvenance, _allowed_source

SUBJECTS = {"psat_verbal": "언어논리", "psat_data": "자료해석", "psat_situation": "상황판단"}


class SelectedRecord(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    track: Literal["psat_verbal", "psat_data", "psat_situation"]
    grade: StrictInt
    usage: Literal["development"]


class Selection(StrictModel):
    schema_version: Literal[1]
    usage: Literal["development"]
    records: list[SelectedRecord] = Field(min_length=1, max_length=1000)
    source_root: str | None = None


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _save(path, value):
    path.write_bytes(_bytes(value) + b"\n")


def _provenance(path, digest, locator):
    return ReferenceProvenance(file=str(path), sha256=digest, locator=locator, usage="development")


def _check_usage(value):
    """Reject explicit held-out declarations anywhere in source metadata."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"usage", "split", "partition"} and child not in (None, "", "development", "dev"):
                raise ValueError("development 외 분할은 내보낼 수 없습니다")
            _check_usage(child)
    elif isinstance(value, list):
        for child in value:
            _check_usage(child)
    elif isinstance(value, str):
        _allowed_source(value)


def _fields(item):
    # Preserve the import_questions contract exactly, including extra metadata.
    return {"과목": item.subject, "연도": item.year, "회차": str(item.year), "문항 번호": item.number,
            "문항유형": item.item_type, "발문": item.stem, "지문": item.passage, "보기": item.statements,
            "표": [t.model_dump() for t in item.tables], "선지": [o.model_dump() for o in item.options],
            "정답": None, "정답 검증": False, "분류 검증": "provisional", "출처": item.source.model_dump(),
            "전사 대조": item.verification_note, "전사 부가정보": item.model_extra or {}}


def verify_packet_transcription(row, meta, packet_bytes, source_root, pdf):
    """Bind a row's actual content to the unchanged packet, including at search."""
    _check_usage(meta)
    fields = meta["fields"]
    packet = json.loads(packet_bytes)
    _check_usage({k: v for k, v in packet.items() if k != "items"})
    matches = [i for i in packet["items"] if i.get("exam") == row["exam"]
               and i.get("subject") == fields["과목"] and i.get("year") == fields["연도"]
               and i.get("number") == fields["문항 번호"]]
    if len(matches) != 1:
        raise ValueError("패킷 안의 문항 대응이 유일하지 않습니다: " + row["id"])
    _check_usage(matches[0])
    item = QuestionSource.model_validate(matches[0])
    if item.exam == "psat7" and item.number > 25:
        raise ValueError("7급 PSAT 문항 번호는 25를 넘을 수 없습니다")
    if not item.stem.strip() or not all(o.text.strip() for o in item.options):
        raise ValueError("발문과 다섯 선지 전문이 필요합니다")
    if not item.passage.strip() and not item.tables:
        raise ValueError("지문 또는 완전한 표가 필요합니다")
    if any(not t.rows for t in item.tables):
        raise ValueError("빈 표는 완전한 전사가 아닙니다")
    source_path = Path(item.source.pdf_path)
    source_path = (source_path if source_path.is_absolute() else source_root / source_path).resolve()
    locator = f"{pdf.name}#{item.exam}:{item.year}:{item.subject}:{item.number:02d}"
    if (source_path != pdf or item.source.pdf_sha256 != row["sha"] or locator != row["locator"]
            or fields != _fields(item) or json.loads(row["text"]) != fields
            or meta["source"] != item.source.model_dump()
            or item.source.model_dump().get("official_bytes_verified", False) is not False):
        raise ValueError("corpus·패킷·PDF 출처 또는 전사 본문이 다릅니다: " + row["id"])
    return item


def export(corpus_path, selection_path, out):
    """Reserve a fresh output, preflight every selection, then publish references.

    Failure keeps the selection snapshot and failure receipt, never a usable
    partial refs.jsonl. Relative legacy source paths use source_root or the
    captured invocation directory; no track/type/grade inference is performed.
    """
    corpus, selection_path, out = (Path(p).resolve() for p in (corpus_path, selection_path, out))
    for path in (corpus, selection_path, out):
        _allowed_source(str(path))
    if out.exists():
        raise ValueError("기존 내보내기를 덮어쓰지 않습니다. 새 --out 디렉터리를 지정하세요.")
    if not corpus.is_file():
        raise FileNotFoundError("읽기 전용 corpus가 없습니다: " + str(corpus))
    selection_bytes = selection_path.read_bytes()
    out.mkdir(parents=True, exist_ok=False)
    (out / "selection.json").write_bytes(selection_bytes)
    receipt = {"schema_version": 1, "evidence_version": 1, "requires_corpus_evidence_support": True,
               "corpus": str(corpus), "corpus_open_mode": "ro", "selection": str(selection_path),
               "selection_sha256": _sha(selection_bytes), "exported": 0, "errors": [],
               "usage": "development", "answer_verified": False, "semantic_accuracy_verified": False,
               "official_bytes_verified": False, "human_approved": False}
    try:
        selection = Selection.model_validate_json(selection_bytes)
        _check_usage(selection.model_dump())
        if len({r.id for r in selection.records}) != len(selection.records):
            raise ValueError("선택 ID가 중복됩니다")
        if any(r.grade not in (5, 7) for r in selection.records):
            raise ValueError("PSAT 급수는 5 또는 7이어야 합니다")
        source_root = Path(selection.source_root).resolve() if selection.source_root else Path.cwd().resolve()
        receipt["source_root"] = str(source_root)
        cached = {}

        def checked(path, expected):
            path = Path(path)
            path = (path if path.is_absolute() else source_root / path).resolve()
            _allowed_source(str(path))
            if path == out or out in path.parents:
                raise ValueError("출력 디렉터리를 입력 출처로 사용할 수 없습니다")
            if path not in cached:
                cached[path] = path.read_bytes()
            if _sha(cached[path]) != expected:
                raise ValueError("출처 SHA256 불일치: " + path.name)
            return path, cached[path]

        accepted = []
        db = sqlite3.connect(corpus.as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN")  # Consistent selected-row snapshot, with no writes.
            for selected in selection.records:
                row = db.execute("SELECT id,sha,locator,exam,role,text,meta FROM records WHERE id=?", (selected.id,)).fetchone()
                if row is None:
                    raise ValueError("선택 ID가 없습니다: " + selected.id)
                row = dict(row)
                stable_locator = row["locator"].split("::", 1)[1] if "::" in row["locator"] else row["locator"].split("#", 1)[-1]
                if row["id"] != _sha((row["sha"] + "#" + stable_locator).encode())[:24]:
                    raise ValueError("corpus ID와 출처·locator 식별식이 다릅니다: " + selected.id)
                if row["role"] != "example" or row["exam"] != f"psat{selected.grade}":
                    raise ValueError("전사 example 역할·급수가 일치하지 않습니다: " + selected.id)
                meta = json.loads(row["meta"])
                _check_usage(meta)
                _allowed_source(row["locator"])
                fields = meta["fields"]
                if (fields["과목"] != SUBJECTS[selected.track]
                        or meta.get("transcription_verified") is not True
                        or meta.get("answer_verified") is not False
                        or meta.get("label_status") != "provisional"
                        or fields.get("정답") is not None or fields.get("정답 검증") is not False):
                    raise ValueError("전사·정답·과목 상태가 이 경로의 범위와 다릅니다: " + selected.id)
                source = db.execute("SELECT sha,name,path,status,detail FROM sources WHERE sha=?", (row["sha"],)).fetchone()
                if source is None:
                    raise ValueError("corpus 원본 출처가 없습니다: " + selected.id)
                source = dict(source)
                _check_usage(source)
                pdf, _ = checked(source["path"], row["sha"])
                if pdf.suffix.lower() != ".pdf":
                    raise ValueError("현재 export는 PDF 문제 전사만 지원합니다")
                packet_path, packet_bytes = checked(meta["packet_path"], meta["packet_sha256"])
                item = verify_packet_transcription(row, meta, packet_bytes, source_root, pdf)
                accepted.append((selected, row, source, meta, item, pdf, packet_path))
        finally:
            db.close()

        # All records passed before any references are emitted.
        (out / "selected-rows").mkdir()
        records, summaries = [], []
        for selected, row, source, meta, item, pdf, packet_path in accepted:
            snapshot = out / "selected-rows" / (selected.id + ".json")
            _save(snapshot, {"record": row, "source": source, "source_path_base": str(source_root)})
            row_sha = _sha(_bytes(row))
            evidence = CorpusEvidence(source_record_id=row["id"], source_record_sha256=row_sha,
                source_record=_provenance(snapshot, _sha(snapshot.read_bytes()), "records.id=" + row["id"]),
                packet=_provenance(packet_path, meta["packet_sha256"], row["locator"]),
                selection=_provenance(out / "selection.json", _sha(selection_bytes), "records.id=" + row["id"]),
                original_meta=meta, transcription_verified=True, answer_verified=False, label_status="provisional")
            record = RefRecord(id=row["id"], track=selected.track, grade=selected.grade, role="item",
                provenance=_provenance(pdf, row["sha"], row["locator"]), source=source["name"],
                year=item.year, number=item.number, item_type=item.item_type, text=row["text"],
                corpus_evidence=evidence, notes="화면 대조 전사. 유형 provisional, 정답·공식 원본 바이트·의미 정확성 미검증. 미확인 facet은 비워 둠.")
            records.append(record)
            summaries.append({"id": row["id"], "track": selected.track, "grade": selected.grade,
                              "source_record_sha256": row_sha, "source_sha256": row["sha"],
                              "packet_sha256": meta["packet_sha256"], "locator": row["locator"]})
        # Detect changed inputs before publishing the complete export.
        for path, data in cached.items():
            if path.read_bytes() != data:
                raise ValueError("검사 도중 출처가 바뀌었습니다: " + path.name)
        refs = ("\n".join(r.model_dump_json() for r in records) + "\n").encode()
        pending = out / ".refs.jsonl.pending"
        pending.write_bytes(refs)
        receipt.update(exported=len(records), refs=str(out / "refs.jsonl"), refs_sha256=_sha(refs), records=summaries,
                       unknown_facets=["area", "item_format", "discourse", "stem_type"],
                       index_built=False, generation_executed=False)
        _save(out / "receipt.json", receipt)
        # Publish only after every required evidence/receipt write succeeded.
        # Same-directory rename is atomic; failed writes keep the pending bytes
        # for diagnosis but never expose the usable refs.jsonl entry point.
        pending.rename(out / "refs.jsonl")
        return receipt
    except Exception as exc:
        receipt["exported"] = 0
        receipt["errors"] = [f"{type(exc).__name__}: {exc}"]
        _save(out / "failure.json", receipt)
        raise ValueError("참고 자료 내보내기 실패; 입력·실패 기록 보존: " + str(out / "failure.json") + ": " + str(exc)) from exc
