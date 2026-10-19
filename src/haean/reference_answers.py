"""Frozen answer overlays for explicitly audited PSAT transcription references.

The supported input is the version-1 sources/records official-answer audit.
Local integrity and PDF row checks do not authenticate a website or constitute
an independent solve, a classification review, or human approval.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
from pathlib import Path
import re
import subprocess
import unicodedata
from urllib.parse import urlsplit
import zipfile

from .tracks.core.references import (OfficialAnswerEvidence, RefRecord, ReferenceProvenance,
                                     _allowed_source, verify_corpus_evidence)

SUBJECTS = {"psat_verbal": "언어논리", "psat_data": "자료해석", "psat_situation": "상황판단"}
STATUS = "official_final_answer_row_visually_verified_and_question_bytes_matched"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _path(value, base):
    path = Path(value)
    path = (path if path.is_absolute() else Path(base) / path).resolve()
    _allowed_source(str(path))
    return path


def _norm(text):
    return "".join(unicodedata.normalize("NFKC", text).split())


def _require(condition, message):
    if not condition:
        raise ValueError("공식 정답 근거: " + message)


def _integer(value, minimum=1, maximum=None):
    return type(value) is int and value >= minimum and (maximum is None or value <= maximum)


def _pdf_text(path, cache):
    if path not in cache:
        try:
            result = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                                    check=True, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("공식 정답 PDF 검증에는 실행 가능한 pdftotext가 필요합니다") from exc
        cache[path] = result.stdout.decode("utf-8")
    return cache[path]


def _verify_answer_header(row, page):
    """Recognize complete modern headers or the audited split-line 5급 header."""
    lines = [_norm(line) for line in page.splitlines() if line.strip()]
    header = []
    for line in lines[:5]:
        if line in ("문번정답", "문번정답문번정답"):
            break
        header.append(line)
    else:
        _require(False, "정답표 실제 PDF의 시험·과목·책형 머리글 불일치")
    identities = re.findall(r"([0-9]+)년도국가공무원([0-9]+)급", header[0] if header else "")
    identity = f"{row['year']}년도국가공무원{row['grade']}급"
    subject, booklet = _norm(row["subject"]), _norm(row["booklet"])
    modern = ["정답표", f"영역{subject}책형{booklet}책형"]
    # The legacy PDF extracts its circle and enclosed booklet on separate lines.
    legacy = ["정답표", f"과목및책형:{subject}◯", f"{booklet}책형"]
    continued_title = bool(header) and header[0].endswith("및")
    # The audited modern 5급 title continues with the court exam on a second line.
    if continued_title:
        modern = ["법원행정고등고시제1차시험", *modern]
    _require(bool(header) and header[0].startswith(identity)
             and identities == [(str(row["year"]), str(row["grade"]))]
             and not any(label in header[0] for label in ("영역", "과목", "책형", *SUBJECTS.values()))
             and (header[1:] == modern and (not continued_title or row["grade"] == 5)
                  or row["grade"] == 5 and not continued_title and header[1:] == legacy),
             "정답표 실제 PDF의 시험·과목·책형 머리글 불일치")


def _verify_question_filename(row, filename):
    """Accept audited subject/booklet basenames, including terminal parentheses."""
    name = Path(filename)
    subject, booklet = re.escape(_norm(row["subject"])), re.escape(_norm(row["booklet"]))
    pattern = rf"(?:[0-9]+[._-]*)?{subject}(?:영역)?(?:[-_]?{booklet}|\({booklet}\))"
    _require(name.suffix.lower() == ".pdf" and re.fullmatch(pattern, _norm(name.stem)),
             "공식 문제 첨부의 과목·책형 불일치")


def _verify_answer_row(row, page):
    """Match an explicit table side and its complete, unique PDF text row."""
    locator, number = row["answer_locator"], row["number"]
    left = locator["table"] == "좌측 문번/정답 표" and _integer(number, 1, 20)
    right = (locator["table"] == "우측 문번/정답 표" and row["grade"] == 5
             and _integer(number, 21, 40))
    _require(locator["question_number_row"] == number and locator["column"] == "정답"
             and (left or right), "지원하는 정답표 방향·급수·문번이 아닙니다")
    raw_row = locator["raw_text_row"]
    _require(isinstance(raw_row, str) and bool(raw_row.strip()),
             "정답표 원문 행은 비어 있지 않은 문자열이어야 합니다")
    cells = raw_row.split()
    _require((len(cells) == 4 if right else len(cells) in (2, 4))
             and all(c.isdecimal() for c in cells), "답행 숫자·셀 수 불일치")
    values = [int(c) for c in cells]
    if right:
        _require(values[0] == number - 20 and 1 <= values[1] <= 5
                 and values[2:4] == [number, row["answer"]], "답행 숫자 불일치")
    else:
        _require(values[:2] == [number, row["answer"]], "답행 숫자 불일치")
    first_number = str(number - 20 if right else number)
    page_rows = []
    for line in page.splitlines():
        tokens = line.split()
        if tokens and (tokens[0] == first_number
                       or (right and len(tokens) >= 3 and tokens[2] == str(number))):
            page_rows.append(tokens)
    _require(page_rows == [cells], "실제 PDF 정답 행이 없거나 중복되거나 다릅니다")
    return raw_row


def _manifest(data):
    value = json.loads(data)
    _require(isinstance(value, dict), "감사 manifest는 객체여야 합니다")
    _require(value.get("schema_version") == 1 and value.get("usage") == "development",
             "지원하는 development 감사 manifest가 아닙니다")
    _require(isinstance(value.get("sources"), list) and isinstance(value.get("records"), list)
             and value["sources"] and value["records"], "sources·records가 필요합니다")
    _require(all(isinstance(item, dict) for item in value["sources"] + value["records"]),
             "sources·records의 원소는 객체여야 합니다")
    _require(len({s["source_id"] for s in value["sources"]}) == len(value["sources"]), "중복 source_id")
    _require(len({r["id"] for r in value["records"]}) == len(value["records"]), "중복 문항 ID")
    return value


def _declared_files(manifest, base):
    """Known audit files only; never execute or follow instructions in inputs."""
    files = {}

    def add(path, digest=None):
        resolved = _path(path, base)
        previous = files.get(resolved)
        _require(not previous or not digest or previous == digest, "같은 출처의 해시 선언이 다릅니다")
        files[resolved] = digest or previous

    for source in manifest["sources"]:
        for stem in ("html", "attachment_metadata", "answer_pdf", "answer_text"):
            add(source[stem + "_path"], source[stem + "_sha256"])
        add(source["download_manifest_path"])
    for row in manifest["records"]:
        visual, question = row["answer_visual_evidence"], row["question_correspondence"]
        add(visual["path"], visual["sha256"])
        add(question["official_pdf_path"], question["official_pdf_sha256"])
        add(question["header_render_path"], question["header_render_sha256"])
        add(question["question_download_manifest_path"])
    # Download manifests also bind archive bytes to their declared members.
    for path in list(files):
        if any(path == _path(s["download_manifest_path"], base) for s in manifest["sources"]) or any(
                path == _path(r["question_correspondence"]["question_download_manifest_path"], base)
                for r in manifest["records"]):
            for entry in json.loads(path.read_bytes()):
                add(entry["path"], entry["sha256"])
    return files


def verify_official_answer_evidence(record, base, verified, extracted=None):
    """Recheck immutable source, audit identity, PDF header and numeric answer row."""
    evidence = record.official_answer_evidence
    if evidence is None:
        return
    extracted = {} if extracted is None else extracted
    for source in evidence.provenances():
        path = _path(source.file, base)
        if path not in verified:
            verified[path] = _sha(path.read_bytes())
        _require(verified[path] == source.sha256, "스냅샷 파일 SHA256 불일치: " + path.name)
        source.file = str(path)

    def read(provenance):
        data = Path(provenance.file).read_bytes()
        _require(_sha(data) == provenance.sha256, "읽는 동안 근거가 바뀌었습니다")
        return data

    def frozen(original, expected=None):
        key = str(_path(original, evidence.manifest_base))
        _require(key in evidence.files, "출처 파일 스냅샷 누락")
        source = evidence.files[key]
        data = read(source)
        _require(expected is None or source.sha256 == expected, "manifest와 출처 SHA256이 다릅니다")
        return Path(source.file), data

    manifest = _manifest(read(evidence.manifest))
    matches = [r for r in manifest["records"] if r["id"] == record.id]
    _require(len(matches) == 1, "문항 대응이 유일하지 않습니다")
    row = matches[0]
    matches = [s for s in manifest["sources"] if s["source_id"] == row["source_id"]]
    _require(len(matches) == 1 and row["source_id"] == evidence.source_id, "source_id 불일치")
    source = matches[0]
    question, locator = row["question_correspondence"], row["answer_locator"]
    _require(_integer(row["answer"], 1, 5) and _integer(row["grade"], 5, 7)
             and _integer(row["year"], 1900) and _integer(row["number"], 1, 25 if record.grade == 7 else 40),
             "답·급수·연도·문번은 지원 범위의 정수여야 합니다")
    _require((row["track"], row["grade"], row["year"], row["number"], row["answer"]) ==
             (record.track, record.grade, record.year, record.number, record.answer)
             and row["exam"] == f"psat{record.grade}" and row["subject"] == SUBJECTS[record.track]
             and row["answer_verified"] is True and record.answer_verified
             and row["verification_status"] == STATUS and row["classification_status"] == "provisional",
             "문항·시험·정답·분류 상태 불일치")
    _require(source["source_type"] == "official_primary_final_answer"
             and (source["grade"], source["year"], source["booklet"]) ==
             (row["grade"], row["year"], row["booklet"])
             and _norm(source["booklet_printed"]) == _norm(row["booklet"])
             and source["visually_reviewed"] is True, "공식 정답 출처의 시험·책형 불일치")
    _require(row["booklet"] and row["booklet"].strip() == row["booklet"], "책형 누락")
    original_bytes = read(evidence.source_refs)
    _require(_sha(original_bytes) == question["original_ref_jsonl_sha256"]
             and _path(question["original_ref_jsonl_path"], evidence.manifest_base) ==
             Path(evidence.source_refs_original_path), "이전 refs 연결 불일치")
    line_number = question["original_ref_jsonl_line_1based"]
    original_lines = original_bytes.decode("utf-8").splitlines()
    _require(_integer(line_number) and line_number <= len(original_lines), "이전 refs 행 위치 불일치")
    original = RefRecord.model_validate_json(original_lines[line_number - 1])
    _require(original.corpus_evidence is not None and original.official_answer_evidence is None and original.answer is None
             and original.answer_verified is False, "미확인 전사 refs만 보강할 수 있습니다")
    # Normalize paths only. Every other original field, including corpus metadata,
    # text, provisional classification and notes remains exactly unchanged.
    original.provenance.file = str(_path(original.provenance.file, Path(evidence.source_refs_original_path).parent))
    for item in original.corpus_evidence.files():
        item.file = str(_path(item.file, Path(evidence.source_refs_original_path).parent))
    expected = record.model_dump(exclude={"answer", "answer_verified", "official_answer_evidence"})
    _require(original.model_dump(exclude={"answer", "answer_verified", "official_answer_evidence"}) == expected,
             "원래 전사 refs와 새 레코드가 다릅니다")
    _require(question["source_record_locator"] == record.provenance.locator
             and _path(question["original_pdf_path"], evidence.manifest_base) == Path(record.provenance.file)
             and question["original_pdf_sha256"] == question["official_pdf_sha256"] == record.provenance.sha256
             and question["official_bytes_verified"] is True
             and question["booklet_header_visually_verified"] is True
             and record.corpus_evidence.original_meta["fields"]["전사 부가정보"].get("booklet", row["booklet"]) == row["booklet"]
             and question["question_pages"] == record.corpus_evidence.original_meta["source"]["pages"],
             "공식 문제지와 원래 문항 출처 대응 불일치")
    answer_pdf, _ = frozen(source["answer_pdf_path"], source["answer_pdf_sha256"])
    _, text_bytes = frozen(source["answer_text_path"], source["answer_text_sha256"])
    answer_text = _pdf_text(answer_pdf, extracted)
    pages = answer_text.split("\f")
    page_number = locator["physical_pdf_page"]
    _require(_integer(page_number) and page_number <= len(pages)
             and page_number in source["relevant_physical_pages"], "정답표 PDF 쪽 위치 불일치")
    page = pages[page_number - 1]
    _verify_answer_header(row, page)
    raw_row = _verify_answer_row(row, page)
    # Stored extraction line locations remain auditable; actual PDF comparison
    # ignores whitespace variation between Poppler versions.
    stored = text_bytes.decode("utf-8")
    stored_pages = stored.split("\f")
    _require(page_number <= len(stored_pages), "보존된 정답표 텍스트 쪽 누락")
    for lines, position in ((stored.split("\n"), locator["global_text_line_1based"]),
                            (stored_pages[page_number - 1].split("\n"), locator["page_text_line_1based"])):
        _require(_integer(position) and position <= len(lines) and lines[position - 1] == raw_row,
                 "보존된 정답표 텍스트 줄 위치 불일치")
    question_pdf, _ = frozen(question["official_pdf_path"], question["official_pdf_sha256"])
    question_lines = _pdf_text(question_pdf, extracted).split("\f")[0].splitlines()
    _require(bool(question_lines), "문제 PDF 첫 쪽 머리글 누락")
    question_header = _norm(question_lines[0])
    _require(f"{row['year']}년도국가공무원{row['grade']}급" in question_header
             and row["subject"] + "영역" in question_header and "책형" in question_header,
             "실제 문제 PDF의 시험·연도·과목 머리글 불일치")
    printed = re.search(re.escape(row["subject"]) + r"영역(.+?)책형", question_header)
    _require(printed is None or _norm(printed.group(1)) == _norm(row["booklet"]), "문제 PDF 책형 불일치")
    visual = row["answer_visual_evidence"]
    _require(set(visual["reviewed_fields"]) >= {"시험명", "영역", "책형", "문번 행", "정답 열"}
             and visual["independent_answer_solve"] is False
             and isinstance(visual["reviewer"], str) and bool(visual["reviewer"].strip()), "시각 대조 범위 누락")
    frozen(visual["path"], visual["sha256"])
    frozen(question["header_render_path"], question["header_render_sha256"])
    _, html_bytes = frozen(source["html_path"], source["html_sha256"])
    html_lines = html_bytes.decode("utf-8").splitlines()
    statement_line = source["finalization_statement_html_line"]
    _require(_integer(statement_line) and statement_line <= len(html_lines)
             and "최종정답" in _norm(source["finalization_statement"])
             and "확정" in _norm(source["finalization_statement"])
             and _norm(source["finalization_statement"]) in _norm(html.unescape(re.sub(r"<[^>]+>", "", html_lines[statement_line - 1]))),
             "최종정답 공개 문구 위치 불일치")
    _require(urlsplit(source["official_post_url"]).scheme == "https"
             and urlsplit(source["download_endpoint"]).scheme == "https"
             and bool(urlsplit(source["official_post_url"]).netloc)
             and urlsplit(source["official_post_url"]).netloc == urlsplit(source["download_endpoint"]).netloc,
             "공개 게시물·다운로드 출처 연결 불일치")
    _, metadata = frozen(source["attachment_metadata_path"], source["attachment_metadata_sha256"])
    attachments = [a for a in json.loads(metadata) if a["atchFileId"] == source["attachment_id"]
                   and a["atchFileSn"] == source["attachment_sequence"]]
    _require(len(attachments) == 1
             and attachments[0]["strgFileNm"] == source["original_attachment_filename"]
             and attachments[0]["filePathNm"] == source["original_attachment_server_path"]
             and attachments[0]["atchFileSz"] == source["answer_pdf_size"] == answer_pdf.stat().st_size,
             "공식 첨부 식별자·이름·크기 불일치")
    _, downloads = frozen(source["download_manifest_path"])
    downloads = [d for d in json.loads(downloads) if _path(d["path"], evidence.manifest_base) == _path(source["answer_pdf_path"], evidence.manifest_base)]
    _require(len(downloads) == 1 and downloads[0]["sha256"] == source["answer_pdf_sha256"]
             and downloads[0]["attachment"] == attachments[0]
             and downloads[0]["size"] == source["answer_pdf_size"]
             and downloads[0]["request_method"] == "POST"
             and downloads[0]["endpoint"] == source["download_endpoint"], "공식 정답 다운로드 기록 불일치")
    _, question_downloads = frozen(question["question_download_manifest_path"])
    question_downloads = json.loads(question_downloads)
    question_matches = [d for d in question_downloads if _path(d["path"], evidence.manifest_base) == _path(question["official_pdf_path"], evidence.manifest_base)]
    _require(len(question_matches) == 1 and question_matches[0]["sha256"] == question["official_pdf_sha256"]
             and question_matches[0]["grade"] == record.grade, "공식 문제 다운로드 기록 불일치")
    download = question_matches[0]
    if question.get("zip_member"):
        _require(download.get("zip_member") == question["zip_member"], "공식 ZIP 문항 연결 불일치")
        archives = [d for d in question_downloads if Path(d["path"]).suffix.lower() == ".zip" and d["grade"] == record.grade]
        _require(len(archives) == 1 and archives[0]["endpoint"] == source["download_endpoint"]
                 and archives[0]["request_method"] == "POST", "공식 문제 ZIP 대응이 유일하지 않습니다")
        _, archive_bytes = frozen(archives[0]["path"], archives[0]["sha256"])
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                _require(archive.namelist().count(question["zip_member"]) == 1
                         and _sha(archive.read(question["zip_member"])) == question["official_pdf_sha256"], "공식 ZIP 멤버 바이트 불일치")
        except zipfile.BadZipFile as exc:
            raise ValueError("공식 정답 근거: 문제 ZIP을 읽을 수 없습니다") from exc
        filename = question["zip_member"]
    else:
        filename = download["attachment"]["strgFileNm"]
        _require(download["endpoint"] == source["download_endpoint"], "공식 문제 다운로드 endpoint 불일치")
    _verify_question_filename(row, filename)


def enrich(source_refs, evidence_manifest, out):
    """Validate a complete selected audit and publish only into a new directory."""
    source_refs, evidence_manifest, out = (_path(p, Path.cwd()) for p in (source_refs, evidence_manifest, out))
    if out.exists():
        raise ValueError("기존 결과를 덮어쓰지 않습니다. 새 --out 디렉터리를 지정하세요.")
    refs_bytes, manifest_bytes = source_refs.read_bytes(), evidence_manifest.read_bytes()
    out.mkdir(parents=True, exist_ok=False)
    receipt = {"schema_version": 1, "usage": "development", "source_refs": str(source_refs),
               "source_refs_sha256": _sha(refs_bytes), "evidence_manifest": str(evidence_manifest),
               "evidence_manifest_sha256": _sha(manifest_bytes), "exported": 0, "errors": [],
               "requires_official_answer_evidence_support": True, "human_approved": False,
               "semantic_accuracy_verified": False, "classification_status": "provisional",
               "verification_scope": "official_answer_row_and_question_bytes"}
    try:
        (out / "source-refs.jsonl").write_bytes(refs_bytes)
        (out / "answer-mapping.json").write_bytes(manifest_bytes)
        manifest = _manifest(manifest_bytes)
        records = [RefRecord.model_validate_json(line) for line in refs_bytes.decode("utf-8").splitlines() if line.strip()]
        _require(len({r.id for r in records}) == len(records), "refs 중복 ID")
        _require({r.id for r in records} == {r["id"] for r in manifest["records"]}, "refs와 감사 문항 집합 불일치")
        originals = {source_refs: refs_bytes, evidence_manifest: manifest_bytes}
        file_map = {}
        (out / "evidence").mkdir()
        for path, expected in _declared_files(manifest, evidence_manifest.parent).items():
            _require(path != out and out not in path.parents, "출력을 입력 출처로 쓸 수 없습니다")
            data = path.read_bytes()
            digest = _sha(data)
            _require(expected is None or expected == digest, "입력 출처 SHA256 불일치: " + path.name)
            originals[path] = data
            snapshot = out / "evidence" / (digest + path.suffix.lower())
            if not snapshot.exists():
                snapshot.write_bytes(data)
            file_map[str(path)] = ReferenceProvenance(file=str(snapshot), locator="audit file: " + path.name,
                                                      sha256=digest, usage="development")
        verified, extracted = {}, {}
        for record in records:
            _require(record.corpus_evidence is not None and record.answer is None and record.answer_verified is False
                     and record.official_answer_evidence is None, "미확인 corpus 전사만 지원합니다")
            record.provenance.file = str(_path(record.provenance.file, source_refs.parent))
            _require(_sha(Path(record.provenance.file).read_bytes()) == record.provenance.sha256, "문제 출처 SHA256 불일치")
            verify_corpus_evidence(record, source_refs.parent, verified)
            audit = next(r for r in manifest["records"] if r["id"] == record.id)
            record.answer, record.answer_verified = audit["answer"], True
            record.official_answer_evidence = OfficialAnswerEvidence(
                manifest=ReferenceProvenance(file=str(out / "answer-mapping.json"), locator="records.id=" + record.id,
                                             sha256=_sha(manifest_bytes), usage="development"),
                source_refs=ReferenceProvenance(file=str(out / "source-refs.jsonl"), locator="id=" + record.id,
                                                sha256=_sha(refs_bytes), usage="development"),
                manifest_base=str(evidence_manifest.parent), source_refs_original_path=str(source_refs),
                source_id=audit["source_id"], files=file_map)
            record = RefRecord.model_validate(record.model_dump())
            verify_official_answer_evidence(record, out, verified, extracted)
        for path, data in originals.items():
            _require(path.read_bytes() == data, "검사 도중 입력 출처가 바뀌었습니다")
        pending = out / ".refs.jsonl.pending"
        pending.write_text("\n".join(r.model_dump_json() for r in records) + "\n", encoding="utf-8")
        receipt.update(exported=len(records), answer_verified=True, refs_sha256=_sha(pending.read_bytes()),
                       evidence_files=len(file_map), original_corpus_answer_verified=False)
        _save(out / "receipt.json", receipt)
        pending.rename(out / "refs.jsonl")
        return receipt
    except Exception as exc:
        receipt.update(exported=0, errors=[str(exc)])
        _save(out / "failure.json", receipt)
        raise ValueError("공식 정답 보강 실패: " + str(exc)) from exc
