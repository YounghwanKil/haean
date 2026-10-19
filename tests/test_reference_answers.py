"""Synthetic audit fixtures; no official questions, answers or private paths."""
import json
from pathlib import Path
import zipfile

import pytest

from haean import reference_answers
from haean.corpus import Corpus
from haean.question_sources import import_questions
from haean.reference_bridge import export
from haean.tracks.core.references import RefQuery, ReferenceIndex
from test_reference_bridge import corpus_data, sha, save


@pytest.fixture
def audit(corpus_data, tmp_path, monkeypatch, request):
    d = corpus_data
    packet = json.loads(d["packet"].read_text())
    questions = {}
    for item in packet["items"]:
        grade = int(item["exam"][-1])
        item["year"], item["booklet"] = 2032, "다"
        if getattr(request, "param", None) == "no_booklet":
            item.pop("booklet")
        elif getattr(request, "param", None) == "wrong_booklet":
            item["booklet"] = "라"
        pdf = tmp_path / f"synthetic-question-{grade}.pdf"
        pdf.write_text(f"2032년도 국가공무원 {grade}급 공채 등 필기시험 언어논리영역 다 책형 1쪽\n합성 문항", encoding="utf-8")
        item["source"]["pdf_path"], item["source"]["pdf_sha256"] = str(pdf), sha(pdf)
        questions[grade] = pdf
    save(d["packet"], packet)
    d["corpus"] = tmp_path / "new-corpus.sqlite"
    db = Corpus(d["corpus"])
    import_questions(db, d["packet"])
    d["rows"] = [dict(r) for r in db.db.execute("SELECT * FROM records ORDER BY exam")]
    db.db.close()
    save(d["selection"], {"schema_version": 1, "usage": "development", "records": [
        {"id": row["id"], "track": "psat_verbal", "grade": grade, "usage": "development"}
        for row, grade in zip(d["rows"], (5, 7))]})
    export(d["corpus"], d["selection"], d["out"])
    refs = d["out"] / "refs.jsonl"
    records = [json.loads(line) for line in refs.read_text().splitlines()]
    answer_downloads, question_downloads, sources, mappings = [], [], [], []
    answer_download_path, question_download_path = tmp_path / "answer-downloads.json", tmp_path / "question-downloads.json"
    for grade, record in zip((5, 7), records):
        answer_pdf, answer_txt = tmp_path / f"answer-{grade}.pdf", tmp_path / f"answer-{grade}.txt"
        answer_text = f"2032년도 국가공무원 {grade}급 공개경쟁채용\n정답표\n영역 언어논리 책형 다 책형\n문번 정답 문번 정답\n 1 2 21 4\n\f"
        answer_pdf.write_text(answer_text, encoding="utf-8")
        answer_txt.write_text(answer_text, encoding="utf-8")
        html = tmp_path / f"post-{grade}.html"
        html.write_text("<p>합성 최종정답 확정</p>\n", encoding="utf-8")
        metadata = tmp_path / f"attachments-{grade}.json"
        attachment = {"atchFileId": f"synthetic-{grade}", "atchFileSn": 1,
                      "strgFileNm": "합성 최종정답.pdf", "filePathNm": f"/synthetic/{grade}.pdf",
                      "atchFileSz": answer_pdf.stat().st_size}
        save(metadata, [attachment])
        endpoint = "https://example.invalid/download"
        answer_downloads.append({"path": str(answer_pdf), "sha256": sha(answer_pdf), "size": answer_pdf.stat().st_size,
                                 "endpoint": endpoint, "attachment": attachment, "request_method": "POST"})
        question_pdf = tmp_path / f"official-question-{grade}.pdf"
        question_pdf.write_bytes(questions[grade].read_bytes())
        question_download = {"path": str(question_pdf), "sha256": sha(question_pdf), "grade": grade}
        member = None
        if grade == 7:
            member = "언어논리-다.pdf"
            archive = tmp_path / "questions.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr(member, question_pdf.read_bytes())
            question_downloads.append({"path": str(archive), "sha256": sha(archive), "grade": grade,
                                       "endpoint": endpoint, "request_method": "POST"})
            question_download["zip_member"] = member
        else:
            question_download.update(endpoint=endpoint, attachment={"strgFileNm": "언어논리-다.pdf"})
        question_downloads.append(question_download)
        image = tmp_path / f"synthetic-render-{grade}.png"
        image.write_bytes(f"synthetic visual evidence {grade}".encode())
        source = {"source_id": f"synthetic-source-{grade}", "source_type": "official_primary_final_answer",
                  "grade": grade, "year": 2032, "booklet": "다", "booklet_printed": "다", "visually_reviewed": True,
                  "relevant_physical_pages": [1], "official_post_url": "https://example.invalid/post",
                  "download_endpoint": endpoint, "download_manifest_path": str(answer_download_path),
                  "attachment_id": attachment["atchFileId"], "attachment_sequence": 1,
                  "original_attachment_filename": attachment["strgFileNm"],
                  "original_attachment_server_path": attachment["filePathNm"],
                  "answer_pdf_size": answer_pdf.stat().st_size,
                  "finalization_statement": "합성 최종정답 확정", "finalization_statement_html_line": 1}
        for stem, path in (("answer_pdf", answer_pdf), ("answer_text", answer_txt), ("html", html), ("attachment_metadata", metadata)):
            source[stem + "_path"], source[stem + "_sha256"] = str(path), sha(path)
        sources.append(source)
        mappings.append({"id": record["id"], "exam": f"psat{grade}", "grade": grade, "year": 2032,
            "track": "psat_verbal", "subject": "언어논리", "booklet": "다", "number": 1, "answer": 2,
            "answer_verified": True, "verification_status": reference_answers.STATUS,
            "classification_status": "provisional", "source_id": source["source_id"],
            "answer_locator": {"physical_pdf_page": 1, "question_number_row": 1, "column": "정답",
                "table": "좌측 문번/정답 표", "raw_text_row": " 1 2 21 4", "page_text_line_1based": 5,
                "global_text_line_1based": 5},
            "answer_visual_evidence": {"path": str(image), "sha256": sha(image),
                "reviewed_fields": ["시험명", "영역", "책형", "문번 행", "정답 열"],
                "independent_answer_solve": False, "reviewer": "synthetic reviewer"},
            "question_correspondence": {"source_record_locator": record["provenance"]["locator"],
                "original_ref_jsonl_path": str(refs), "original_ref_jsonl_sha256": sha(refs),
                "original_ref_jsonl_line_1based": len(mappings) + 1, "original_pdf_path": str(questions[grade]),
                "original_pdf_sha256": sha(questions[grade]), "official_pdf_path": str(question_pdf),
                "official_pdf_sha256": sha(question_pdf), "official_bytes_verified": True,
                "booklet_header_visually_verified": True, "question_pages": [1],
                "header_render_path": str(image), "header_render_sha256": sha(image),
                "question_download_manifest_path": str(question_download_path), "zip_member": member}})
    save(answer_download_path, answer_downloads)
    save(question_download_path, question_downloads)
    manifest_path = tmp_path / "mapping.json"
    save(manifest_path, {"schema_version": 1, "usage": "development", "sources": sources, "records": mappings})
    calls = []

    def synthetic_extract(path, cache):
        if path not in cache:
            calls.append(path)
            cache[path] = path.read_text(encoding="utf-8")
        return cache[path]

    monkeypatch.setattr(reference_answers, "_pdf_text", synthetic_extract)
    return {**d, "refs": refs, "manifest": manifest_path, "new": tmp_path / "enriched", "calls": calls}


def enrich(d):
    return reference_answers.enrich(d["refs"], d["manifest"], d["new"])


def test_enrich_freezes_official_evidence_preserves_originals_and_staged_sources(audit):
    from haean.staged_authoring import _source_files
    d = audit
    protected = {p: p.read_bytes() for p in (d["corpus"], d["packet"], d["refs"])}
    receipt = enrich(d)
    assert receipt["exported"] == 2 and receipt["answer_verified"] is True
    assert receipt["human_approved"] is False and receipt["semantic_accuracy_verified"] is False
    assert all(p.read_bytes() == data for p, data in protected.items())
    # Original official audit files can change without changing the frozen audit.
    manifest = json.loads(d["manifest"].read_text())
    for source in manifest["sources"]:
        Path(source["answer_pdf_path"]).write_bytes(b"later correction")
    d["manifest"].write_text("later corrected audit")
    with ReferenceIndex(d["new"] / "index.sqlite") as index:
        assert index.build(d["new"] / "refs.jsonl")["indexed"] == 2
        for grade in (5, 7):
            result = index.search(RefQuery(track="psat_verbal", grade=grade))
            hit = result["hits"][0]
            assert hit["answer"] == 2 and hit["answer_verified"] is True
            assert hit["corpus_evidence"]["answer_verified"] is False
            assert hit["corpus_evidence"]["original_meta"]["fields"]["정답"] is None
            assert hit["corpus_evidence"]["label_status"] == "provisional"
            sources = _source_files({"design": {"examples": result}})
            official = hit["official_answer_evidence"]
            assert {v["file"] for v in official["files"].values()} <= sources.keys()
            assert official["manifest"]["file"] in sources and official["source_refs"]["file"] in sources


@pytest.mark.parametrize("audit", ["no_booklet", "wrong_booklet"], indirect=True)
def test_original_booklet_unknown_is_preserved_but_explicit_conflict_rejected(audit):
    d = audit
    original = json.loads(d["refs"].read_text().splitlines()[0])
    extra = original["corpus_evidence"]["original_meta"]["fields"]["전사 부가정보"]
    if "booklet" in extra:
        with pytest.raises(ValueError, match="문항 출처 대응"):
            enrich(d)
    else:
        assert enrich(d)["exported"] == 2
        new = json.loads((d["new"] / "refs.jsonl").read_text().splitlines()[0])
        assert new["corpus_evidence"]["original_meta"] == original["corpus_evidence"]["original_meta"]


@pytest.mark.parametrize("field,value", [("answer", True), ("answer", 6), ("answer", 3), ("grade", 7),
    ("year", 2033), ("track", "psat_data"), ("subject", "자료해석"), ("booklet", "라"),
    ("number", 2), ("source_id", "missing"), ("exam", "psat7")])
def test_invalid_audit_never_publishes_partial_refs(audit, field, value):
    d = audit
    manifest = json.loads(d["manifest"].read_text())
    manifest["records"][0][field] = value
    save(d["manifest"], manifest)
    with pytest.raises(ValueError, match="공식 정답 보강 실패"):
        enrich(d)
    assert not (d["new"] / "refs.jsonl").exists()
    assert json.loads((d["new"] / "failure.json").read_text())["exported"] == 0


@pytest.mark.parametrize("target", ["manifest", "source_refs", "answer_pdf", "answer_text", "html", "attachment_metadata",
                                     "download_manifest", "official_pdf", "header_render", "question_download_manifest", "archive"])
@pytest.mark.parametrize("when", ["build", "search"])
def test_frozen_evidence_changes_fail_build_and_search(audit, target, when):
    d = audit
    enrich(d)
    records = [json.loads(line) for line in (d["new"] / "refs.jsonl").read_text().splitlines()]
    evidence = records[0]["official_answer_evidence"]
    manifest = json.loads(Path(evidence["manifest"]["file"]).read_text())
    if target in ("manifest", "source_refs"):
        path = Path(evidence[target]["file"])
    else:
        source, question = manifest["sources"][0], manifest["records"][0]["question_correspondence"]
        if target == "archive":
            original = next(k for k in evidence["files"] if k.endswith(".zip"))
        else:
            original = source[target + "_path"] if target + "_path" in source else question[target + "_path"]
        path = Path(evidence["files"][original]["file"])
    with ReferenceIndex(d["new"] / "index.sqlite") as index:
        if when == "search":
            assert index.build(d["new"] / "refs.jsonl")["indexed"] == 2
        path.write_bytes(path.read_bytes() + b"changed")
        if when == "build":
            assert index.build(d["new"] / "refs.jsonl")["indexed"] == 0
        else:
            with pytest.raises(ValueError, match="참고 자료를 사용할 수 없습니다"):
                index.search(RefQuery(track="psat_verbal", grade=5))


@pytest.mark.parametrize("when", ["build", "search"])
def test_resealed_answer_and_text_cannot_override_pdf(audit, when):
    d = audit
    enrich(d)
    refs = d["new"] / "refs.jsonl"
    records = [json.loads(line) for line in refs.read_text().splitlines()]
    record = records[0]
    evidence = record["official_answer_evidence"]
    with ReferenceIndex(d["new"] / "index.sqlite") as index:
        if when == "search":
            assert index.build(refs)["indexed"] == 2
        mapping_path = Path(evidence["manifest"]["file"])
        mapping = json.loads(mapping_path.read_text())
        mapping["records"][0]["answer"] = record["answer"] = 3
        mapping["records"][0]["answer_locator"]["raw_text_row"] = " 1 3 21 4"
        source = mapping["sources"][0]
        txt = evidence["files"][source["answer_text_path"]]
        txt_path = Path(txt["file"])
        txt_path.write_text(txt_path.read_text().replace("1 2 21 4", "1 3 21 4"))
        txt["sha256"] = source["answer_text_sha256"] = sha(txt_path)
        save(mapping_path, mapping)
        evidence["manifest"]["sha256"] = sha(mapping_path)
        if when == "build":
            refs.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records))
            assert index.build(refs)["indexed"] == 0
        else:
            with index.db:
                index.db.execute("UPDATE track_refs SET record=? WHERE id=?", (json.dumps(record), record["id"]))
            with pytest.raises(ValueError, match="실제 PDF 정답 행"):
                index.search(RefQuery(track="psat_verbal", grade=5))


@pytest.mark.parametrize("when", ["build", "search"])
@pytest.mark.parametrize("section,field,error", [
    ("answer_locator", "raw_text_row", "정답표 원문 행"),
    ("answer_visual_evidence", "reviewer", "시각 대조 범위"),
])
def test_resealed_nested_field_type_uses_validation_error_contract(audit, when, section, field, error):
    d = audit
    enrich(d)
    refs = d["new"] / "refs.jsonl"
    records = [json.loads(line) for line in refs.read_text().splitlines()]
    with ReferenceIndex(d["new"] / "index.sqlite") as index:
        assert index.build(refs)["indexed"] == 2
        mapping_path = Path(records[0]["official_answer_evidence"]["manifest"]["file"])
        mapping = json.loads(mapping_path.read_text())
        mapping["records"][0][section][field] = []
        save(mapping_path, mapping)
        for record in records:
            record["official_answer_evidence"]["manifest"]["sha256"] = sha(mapping_path)
        if when == "build":
            refs.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records))
            result = index.build(refs)
            assert result["indexed"] == 0
            assert any(error in entry["error"] for entry in result["errors"])
            assert index.db.execute("SELECT count(*) FROM track_refs").fetchone()[0] == 2
        else:
            with index.db:
                index.db.executemany("UPDATE track_refs SET record=? WHERE id=?",
                                     [(json.dumps(r), r["id"]) for r in records])
            with pytest.raises(ValueError, match=error):
                index.search(RefQuery(track="psat_verbal", grade=5))


def test_no_overwrite_and_receipt_failure_is_not_usable(audit, monkeypatch):
    d = audit
    real_save = reference_answers._save

    def fail(path, value):
        if path.name == "receipt.json":
            raise OSError("synthetic failure")
        real_save(path, value)

    monkeypatch.setattr(reference_answers, "_save", fail)
    with pytest.raises(ValueError, match="synthetic failure"):
        enrich(d)
    assert not (d["new"] / "refs.jsonl").exists()
    assert (d["new"] / ".refs.jsonl.pending").exists()
    before = {p.name: p.read_bytes() for p in d["new"].iterdir() if p.is_file()}
    with pytest.raises(ValueError, match="덮어쓰지"):
        enrich(d)
    assert before == {p.name: p.read_bytes() for p in d["new"].iterdir() if p.is_file()}


def synthetic_pdf(text):
    """Tiny Unicode PDF fixture, generated here without fonts or exam content."""
    chars = sorted(set(text.replace("\n", "")))
    mappings = "\n".join(f"<{ord(c):04X}> <{ord(c):04X}>" for c in chars)
    cmap = ("/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            "/CMapName /Synthetic def /CMapType 2 def\n1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
            + f"{len(chars)} beginbfchar\n{mappings}\nendbfchar\nendcmap CMapName currentdict /CMap defineresource pop end end")
    content = "BT /F1 10 Tf 18 TL 50 760 Td\n" + "\nT*\n".join(
        "<" + line.encode("utf-16-be").hex() + "> Tj" for line in text.split("\n")) + "\nET"

    def stream(value):
        data = value.encode("ascii")
        return f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"

    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 7 0 R >>",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /Synthetic /Encoding /Identity-H /DescendantFonts [5 0 R] /ToUnicode 6 0 R >>",
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Synthetic /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /DW 500 /FontDescriptor 8 0 R >>",
        stream(cmap), stream(content),
        b"<< /Type /FontDescriptor /FontName /Synthetic /Flags 4 /FontBBox [0 0 1000 1000] /ItalicAngle 0 /Ascent 900 /Descent -100 /CapHeight 700 /StemV 80 >>"]
    result, offsets = b"%PDF-1.4\n", [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(result)
    result += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    result += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    return result + f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()


def test_real_poppler_reads_synthetic_unicode_pdf_and_cache(tmp_path, monkeypatch):
    import shutil
    if not shutil.which("pdftotext"):
        pytest.skip("optional Poppler is unavailable")
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(synthetic_pdf("2032년도 국가공무원 5급\n영역 언어논리 책형 다 책형\n문번 정답\n1 2"))
    cache = {}
    result = reference_answers._pdf_text(pdf, cache)
    assert "2032년도 국가공무원 5급" in result and "영역 언어논리 책형 다 책형" in result
    monkeypatch.setattr(reference_answers.subprocess, "run", lambda *a, **kw: pytest.fail("cached PDF re-extracted"))
    assert reference_answers._pdf_text(pdf, cache) == result


def test_missing_poppler_is_explicit(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("synthetic missing executable")
    monkeypatch.setattr(reference_answers.subprocess, "run", missing)
    with pytest.raises(ValueError, match="pdftotext"):
        reference_answers._pdf_text(tmp_path / "synthetic.pdf", {})


@pytest.mark.parametrize("fault", ["duplicate_record", "duplicate_source", "source_type", "original_line", "page", "global_line", "table", "booklet_source", "attachment_id", "row_duplicate", "zip_member"])
def test_identity_source_and_locator_corruption_fails_closed(audit, fault):
    d = audit
    m = json.loads(d["manifest"].read_text())
    row, source = m["records"][0], m["sources"][0]
    if fault == "duplicate_record":
        m["records"].append(row)
    elif fault == "duplicate_source":
        m["sources"].append(source)
    elif fault == "source_type":
        source["source_type"] = "unverified_mirror"
    elif fault == "original_line":
        row["question_correspondence"]["original_ref_jsonl_line_1based"] = 2
    elif fault == "page":
        row["answer_locator"]["physical_pdf_page"] = 2
    elif fault == "global_line":
        row["answer_locator"]["global_text_line_1based"] = 1
    elif fault == "table":
        row["answer_locator"]["table"] = "우측 문번/정답 표"
    elif fault == "booklet_source":
        source["booklet"] = "라"
    elif fault == "attachment_id":
        source["attachment_id"] = "wrong"
    elif fault == "zip_member":
        m["records"][1]["question_correspondence"]["zip_member"] = "missing.pdf"
    elif fault == "row_duplicate":
        pdf = Path(source["answer_pdf_path"])
        pdf.write_text(pdf.read_text().replace("\f", " 1 2 21 4\n\f"))
        source["answer_pdf_sha256"] = sha(pdf)
    save(d["manifest"], m)
    with pytest.raises(ValueError, match="공식 정답 보강 실패"):
        enrich(d)
    assert not (d["new"] / "refs.jsonl").exists()
