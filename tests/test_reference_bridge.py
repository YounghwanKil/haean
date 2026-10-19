"""Synthetic read-only corpus exports; no production questions or model calls."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from haean.corpus import Corpus
from haean.question_sources import import_questions
from haean.reference_bridge import export
from haean.tracks.core.references import RefQuery, ReferenceIndex
from test_track_cli import invoke


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def corpus_data(tmp_path):
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"synthetic PDF fixture, no real question")
    packet = tmp_path / "packet.json"
    items = [{"exam": f"psat{grade}", "subject": "언어논리", "year": 2026, "number": 1,
              "item_type": "합성 잠정 유형", "stem": "합성 발문", "passage": "합성 지문",
              "statements": [], "tables": [],
              "options": [{"number": n, "text": f"합성 선지 {n}"} for n in range(1, 6)],
              "answer": None, "answer_verified": False, "transcription_verified": True,
              "verification_note": "합성 전사 근거",
              "source": {"pdf_path": str(pdf), "pdf_sha256": sha(pdf), "pages": [1],
                         "url": "https://example.invalid/synthetic", "publisher": "합성",
                         "mirror": True, "official_bytes_verified": False}}
             for grade in (5, 7)]
    save(packet, {"items": items})
    corpus = tmp_path / "corpus.sqlite"
    db = Corpus(corpus)
    import_questions(db, packet)
    rows = [dict(r) for r in db.db.execute("SELECT * FROM records ORDER BY exam")]
    db.db.close()
    selection = tmp_path / "selection.json"
    save(selection, {"schema_version": 1, "usage": "development", "records": [
        {"id": row["id"], "track": "psat_verbal", "grade": grade, "usage": "development"}
        for row, grade in zip(rows, (5, 7))]})
    return {"corpus": corpus, "packet": packet, "pdf": pdf, "selection": selection,
            "out": tmp_path / "export", "rows": rows}


def run_export(data):
    return export(data["corpus"], data["selection"], data["out"])


def update_record(data, **values):
    with sqlite3.connect(data["corpus"]) as db:
        for key, value in values.items():
            db.execute(f"UPDATE records SET {key}=? WHERE id=?", (value, data["rows"][0]["id"]))


def test_real_cli_preserves_corpus_and_evidence_then_filters_grade(corpus_data):
    d = corpus_data
    before = sha(d["corpus"])
    result = invoke("ref-export", "--corpus", d["corpus"], "--selection", d["selection"], "--out", d["out"])
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["exported"] == 2 and receipt["requires_corpus_evidence_support"] is True
    assert sha(d["corpus"]) == before
    assert (d["out"] / "selection.json").read_bytes() == d["selection"].read_bytes()
    index_path = d["out"].parent / "index.sqlite"
    built = invoke("ref-build", d["out"] / "refs.jsonl", "--out", index_path)
    assert built.returncode == 0, built.stderr
    with ReferenceIndex(index_path, readonly=True) as index:
        for grade, row in zip((5, 7), d["rows"]):
            hits = index.search(RefQuery(track="psat_verbal", grade=grade))["hits"]
            assert len(hits) == 1 and hits[0]["id"] == row["id"] and hits[0]["grade"] == grade
            hit = hits[0]
            assert hit["text"] == row["text"] and hit["item"] is None
            assert hit["answer"] is None and hit["answer_verified"] is False
            assert hit["item_type"] == "합성 잠정 유형" and hit["area"] == ""
            assert hit["corpus_evidence"]["original_meta"] == json.loads(row["meta"])
            assert hit["corpus_evidence"]["label_status"] == "provisional"
            assert not hit["corpus_evidence"]["official_bytes_verified"]
        # Unknown facets remain unknown; search never silently broadens them.
        assert index.search(RefQuery(track="psat_verbal", grade=5, area="인문"))["hits"] == []
    assert sha(d["corpus"]) == before


@pytest.mark.parametrize("which", ["packet", "pdf", "row_snapshot", "selection_snapshot"])
@pytest.mark.parametrize("when", ["build", "search"])
def test_changed_source_or_export_evidence_rejected(corpus_data, which, when):
    d = corpus_data
    run_export(d)
    refs = d["out"] / "refs.jsonl"
    target = {"packet": d["packet"], "pdf": d["pdf"],
              "row_snapshot": next((d["out"] / "selected-rows").glob("*.json")),
              "selection_snapshot": d["out"] / "selection.json"}[which]
    with ReferenceIndex(d["out"].parent / "index.sqlite") as index:
        if when == "search":
            assert index.build(refs)["indexed"] == 2
        target.write_bytes(target.read_bytes() + b"changed")
        if when == "build":
            assert index.build(refs)["indexed"] == 0
        else:
            # Both grades cover whichever selected-row snapshot glob returned.
            with pytest.raises(ValueError, match="참고 자료를 사용할 수 없습니다"):
                for grade in (5, 7):
                    index.search(RefQuery(track="psat_verbal", grade=grade))


def test_mutable_original_corpus_is_not_runtime_dependency(corpus_data):
    d = corpus_data
    run_export(d)
    with ReferenceIndex(d["out"].parent / "index.sqlite") as index:
        assert index.build(d["out"] / "refs.jsonl")["indexed"] == 2
        d["corpus"].unlink()
        assert len(index.search(RefQuery(track="psat_verbal", grade=5))["hits"]) == 1


@pytest.mark.parametrize("failure", ["duplicate", "missing", "grade", "subject", "role", "metadata",
                                      "unverified", "answer", "label", "holdout", "usage", "leet",
                                      "packet_hash", "pdf_hash", "rawtext", "four_options", "empty_passage"])
def test_selection_preflight_rejects_incomplete_or_wrong_identity(corpus_data, failure):
    d = corpus_data
    selection = json.loads(d["selection"].read_text())
    meta = json.loads(d["rows"][0]["meta"])
    if failure == "duplicate":
        selection["records"].append(selection["records"][0])
    elif failure == "missing":
        selection["records"][1]["id"] = "not-found"
    elif failure == "grade":
        selection["records"][0]["grade"] = 7
    elif failure == "subject":
        selection["records"][0]["track"] = "psat_data"
    elif failure in ("role", "metadata"):
        update_record(d, role="feedback" if failure == "role" else "metadata")
    elif failure == "unverified":
        meta["transcription_verified"] = False
    elif failure == "answer":
        meta["fields"]["정답"] = 1
    elif failure == "label":
        meta["label_status"] = "verified"
    elif failure == "holdout":
        meta["source"]["split"] = "holdout"
    elif failure == "usage":
        selection["usage"] = "holdout"
    elif failure == "leet":
        selection["records"][0]["track"] = "leet_reasoning"
    elif failure == "packet_hash":
        d["packet"].write_text("{}")
    elif failure == "pdf_hash":
        d["pdf"].write_bytes(b"changed")
    elif failure == "rawtext":
        update_record(d, text='{"altered":"text"}')
    elif failure in ("four_options", "empty_passage"):
        packet = json.loads(d["packet"].read_text())
        if failure == "four_options":
            packet["items"][0]["options"].pop()
        else:
            packet["items"][0]["passage"] = ""
        save(d["packet"], packet)
        meta["packet_sha256"] = sha(d["packet"])
    save(d["selection"], selection)
    update_record(d, meta=json.dumps(meta, ensure_ascii=False))
    before = sha(d["corpus"])
    with pytest.raises(ValueError, match="내보내기 실패"):
        run_export(d)
    assert sha(d["corpus"]) == before
    assert not (d["out"] / "refs.jsonl").exists()
    assert json.loads((d["out"] / "failure.json").read_text())["exported"] == 0
    assert (d["out"] / "selection.json").exists()


def test_missing_corpus_and_existing_output_are_not_modified(corpus_data):
    d = corpus_data
    d["out"].mkdir()
    marker = d["out"] / "preserve.txt"
    marker.write_text("preserve")
    with pytest.raises(ValueError, match="덮어쓰지"):
        run_export(d)
    assert list(d["out"].iterdir()) == [marker] and marker.read_text() == "preserve"
    absent = d["out"].parent / "absent" / "corpus.sqlite"
    with pytest.raises(FileNotFoundError):
        export(absent, d["selection"], d["out"].parent / "new")
    assert not absent.parent.exists()


def test_staged_input_capture_includes_all_export_evidence(corpus_data):
    from haean.staged_authoring import _source_files
    d = corpus_data
    run_export(d)
    with ReferenceIndex(d["out"].parent / "index.sqlite") as index:
        index.build(d["out"] / "refs.jsonl")
        hits = index.search(RefQuery(track="psat_verbal", grade=5))
    sources = _source_files({"design": {"examples": hits}})
    assert set(sources) == {str(d["pdf"]), str(d["packet"]), str(d["out"] / "selection.json"),
                           hits["hits"][0]["corpus_evidence"]["source_record"]["file"]}
    assert all(sha(Path(path)) == digest for path, digest in sources.items())


@pytest.mark.parametrize("field,value", [("year", 2020), ("number", 9), ("area", "추정한 영역"),
                                        ("answer", 1), ("answer_verified", True)])
def test_reference_payload_cannot_silently_upgrade_or_reclassify_transcription(corpus_data, field, value):
    d = corpus_data
    run_export(d)
    refs = d["out"] / "refs.jsonl"
    records = [json.loads(line) for line in refs.read_text().splitlines()]
    records[0][field] = value
    refs.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records))
    with ReferenceIndex(d["out"].parent / "index.sqlite") as index:
        result = index.build(refs)
    assert result["indexed"] == 0 and result["errors"]


def test_fake_corpus_id_cannot_duplicate_same_source_item(corpus_data):
    d = corpus_data
    with sqlite3.connect(d["corpus"]) as db:
        db.execute("UPDATE records SET id='invented-id' WHERE id=?", (d["rows"][0]["id"],))
    selection = json.loads(d["selection"].read_text())
    selection["records"][0]["id"] = "invented-id"
    save(d["selection"], selection)
    with pytest.raises(ValueError, match="corpus ID"):
        run_export(d)
    assert not (d["out"] / "refs.jsonl").exists()


@pytest.mark.parametrize("when", ["build", "search"])
def test_resealed_changed_row_cannot_disagree_with_unchanged_packet(corpus_data, when):
    d = corpus_data
    run_export(d)
    refs = d["out"] / "refs.jsonl"
    records = [json.loads(line) for line in refs.read_text().splitlines()]
    packet_before, pdf_before = sha(d["packet"]), sha(d["pdf"])
    with ReferenceIndex(d["out"].parent / "index.sqlite") as index:
        if when == "search":
            assert index.build(refs)["indexed"] == 2
        record = records[0]
        evidence = record["corpus_evidence"]
        snapshot_path = Path(evidence["source_record"]["file"])
        snapshot = json.loads(snapshot_path.read_text())
        row = snapshot["record"]
        meta = json.loads(row["meta"])
        meta["fields"]["지문"] = "변조된 합성 지문"
        row["meta"] = json.dumps(meta, ensure_ascii=False)
        row["text"] = json.dumps(meta["fields"], ensure_ascii=False)
        save(snapshot_path, snapshot)
        record["text"] = row["text"]
        evidence["original_meta"] = meta
        evidence["source_record"]["sha256"] = sha(snapshot_path)
        evidence["source_record_sha256"] = hashlib.sha256(json.dumps(
            row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if when == "build":
            refs.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records))
            assert index.build(refs)["indexed"] == 0
        else:
            with index.db:
                index.db.execute("UPDATE track_refs SET record=? WHERE id=?", (json.dumps(record), record["id"]))
            with pytest.raises(ValueError, match="전사 본문이 다릅니다"):
                index.search(RefQuery(track="psat_verbal", grade=5))
    assert sha(d["packet"]) == packet_before and sha(d["pdf"]) == pdf_before


def test_receipt_write_failure_never_publishes_usable_references(corpus_data, monkeypatch):
    from haean import reference_bridge
    d = corpus_data
    before = sha(d["corpus"])
    real_save = reference_bridge._save

    def fail_receipt(path, value):
        if path.name == "receipt.json":
            path.write_bytes(b'{"partial":')
            raise OSError("synthetic receipt write failure")
        return real_save(path, value)

    monkeypatch.setattr(reference_bridge, "_save", fail_receipt)
    with pytest.raises(ValueError, match="synthetic receipt write failure"):
        run_export(d)
    assert not (d["out"] / "refs.jsonl").exists()
    assert (d["out"] / ".refs.jsonl.pending").is_file()
    assert (d["out"] / "receipt.json").read_bytes() == b'{"partial":'
    failure = json.loads((d["out"] / "failure.json").read_text())
    assert failure["exported"] == 0 and failure["errors"]
    assert (d["out"] / "selection.json").read_bytes() == d["selection"].read_bytes()
    assert len(list((d["out"] / "selected-rows").glob("*.json"))) == 2
    assert sha(d["corpus"]) == before
